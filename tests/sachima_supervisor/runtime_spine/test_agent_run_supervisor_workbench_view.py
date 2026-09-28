"""PR4 — StatusProjection + task workbench view over the agent-run-supervisor spine.

Focused RED/GREEN tests for the PR4 workbench-view slice layered on the already
merged PR1 adapter, PR2 read-only smoke harness, and PR3 persistent session
lifecycle. Everything here stays pure local/offline Python over the deterministic
in-memory ``DefaultAgentRunSupervisorBackend``: no real agent/process/network/
durable service/delivery/listener is started, and no Gateway/Temporal Worker is
touched. Building or serializing the workbench view is read-only — it appends no
event, launches no work, and calls no backend/Gateway/IM/delivery surface.

The PR4 semantics proven here, refs-only and fail-closed:

* **Composition** — the workbench view composes the R1 ``TaskViewModel`` Status
  Projection surface with the PR3 ``LifecycleSnapshot`` persistent-lifecycle facts
  for a locally tracked session, exposing only safe refs / counts / states /
  booleans / stable codes.
* **Permission wait** — a ``permission_wait`` task surfaces the permission surface
  + operator-decision flag and stays alive / resumable (never auto-terminal).
* **Resume determinism** — ``resume_cursor`` / ``last_seq`` / ``event_count`` /
  ``attach_count`` are stable, and no duplicate attach is shown after a lifecycle
  re-attach or a ``close`` + reconstruct.
* **Fail closed** — an unknown / untracked / forged ref fails closed with a stable
  code and never echoes bad material; direct-constructed / forged / mutated views
  and no-leak canaries are rejected and never serialized.
* **Orphan / reapable** — an optional ``LivenessState`` surfaces ``reapable`` over
  the still-non-terminal projected lifecycle without auto-writing a terminal event
  into the canonical log (PR3 policy preserved).

Forbidden terms below are no-leak canaries only, never behavior.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from sachima_supervisor.runtime_spine import (
    LaunchSpec,
    SessionRef,
    SpineError,
    TaskRegistry,
    build_launch_spec,
    scan_for_leak,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    AgentRunSupervisorPort,
    DefaultAgentRunSupervisorBackend,
)
from sachima_supervisor.runtime_spine.execution_port import (
    RUNTIME_INVALID_SESSION,
    LivenessState,
)
from sachima_supervisor.runtime_spine.view_model import (
    RUNTIME_INVALID_VIEW_MODEL,
    build_task_view_model,
)

_SAFE_REFS = ("ws_alpha", "policy_default")

_LEAK_CANARIES = (
    "raw_prompt",
    "raw_context",
    "tool_output",
    "agent_stdout",
    "card_json",
    "chat_id",
    "oc_",
    "ou_",
    "/tmp/",
    "/home/",
    "sk" + "-",
    "bearer ",
    "feishu",
)


def _workbench_mod():
    return importlib.import_module(
        "sachima_supervisor.runtime_spine.agent_run_supervisor_workbench"
    )


def _spec(
    task_id: str = "task_alpha",
    *,
    roles: tuple[str, ...] = ("read_only",),
    refs: tuple[str, ...] = _SAFE_REFS,
    needs_agent: bool = True,
    needs_durable: bool = False,
    agent_kind: str = "local_agent",
) -> LaunchSpec:
    mode_flags = {"needs_agent": needs_agent}
    if needs_durable:
        mode_flags["needs_durable"] = True
    return build_launch_spec(
        task_id=task_id,
        agent_kind=agent_kind,
        mode_flags=mode_flags,
        roles=roles,
        refs=refs,
    )


def _running_port() -> tuple[TaskRegistry, DefaultAgentRunSupervisorBackend, AgentRunSupervisorPort, SessionRef]:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    return reg, backend, port, ref


def _event_types(reg: TaskRegistry, task_id: str) -> list[str]:
    return [e.event_type for e in reg.log.events_for(task_id)]


def _valid_workbench_kwargs(mod, **over):
    base = dict(
        type=mod.WORKBENCH_VIEW_TYPE,
        task_id="task_alpha",
        session_id="sess_1",
        status="running",
        terminal=False,
        alive=True,
        resumable=True,
        reapable=False,
        permission_state="none",
        requires_operator_decision=False,
        flags={"needs_agent": True, "needs_durable": False},
        refs=["ref_plan", "sess_1"],
        surfaces=["status"],
        resume_cursor=2,
        last_seq=2,
        event_count=2,
        attach_count=1,
        error_code=None,
    )
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# A. Public surface
# --------------------------------------------------------------------------- #
def test_workbench_public_surface_is_exported() -> None:
    mod = _workbench_mod()
    assert mod.RUNTIME_INVALID_WORKBENCH_VIEW == "runtime_invalid_workbench_view"
    assert mod.RUNTIME_INVALID_WORKBENCH_VIEW in mod.WORKBENCH_STABLE_CODES
    assert (
        mod.WORKBENCH_VIEW_TYPE
        == "sachima.runtime_spine.agent_run_supervisor_workbench_view.v1"
    )
    for name in (
        "AgentRunSupervisorWorkbenchView",
        "build_agent_run_supervisor_workbench_view",
        "validate_agent_run_supervisor_workbench_view",
        "serialize_agent_run_supervisor_workbench_view",
    ):
        assert hasattr(mod, name)


def test_workbench_symbols_available_from_runtime_spine_package() -> None:
    runtime_spine = importlib.import_module("sachima_supervisor.runtime_spine")
    for name in (
        "RUNTIME_INVALID_WORKBENCH_VIEW",
        "WORKBENCH_VIEW_TYPE",
        "AgentRunSupervisorWorkbenchView",
        "build_agent_run_supervisor_workbench_view",
        "validate_agent_run_supervisor_workbench_view",
        "serialize_agent_run_supervisor_workbench_view",
    ):
        assert hasattr(runtime_spine, name)


# --------------------------------------------------------------------------- #
# B. Composition for a running supervised task
# --------------------------------------------------------------------------- #
def test_workbench_view_composes_view_model_and_lifecycle_for_running_task() -> None:
    mod = _workbench_mod()
    reg, backend, port, ref = _running_port()

    view = mod.build_agent_run_supervisor_workbench_view(reg, port, ref)
    assert type(view) is mod.AgentRunSupervisorWorkbenchView
    data = view.as_dict()
    assert data["type"] == mod.WORKBENCH_VIEW_TYPE
    assert data["task_id"] == "task_alpha"
    assert data["session_id"] == ref.session_id
    assert data["status"] == "running"
    assert data["terminal"] is False
    assert data["alive"] is True
    assert data["resumable"] is True
    assert data["reapable"] is False
    assert data["permission_state"] == "none"
    assert data["requires_operator_decision"] is False
    assert data["flags"] == {"needs_agent": True, "needs_durable": False}
    assert data["surfaces"] == ["status"]
    assert set(data["refs"]) >= {"ws_alpha", "policy_default", ref.session_id}
    assert data["last_seq"] == reg.log.last_seq("task_alpha")
    assert data["event_count"] == data["last_seq"]
    assert data["resume_cursor"] == data["last_seq"]
    assert data["attach_count"] == 1
    assert data["error_code"] is None

    # The composed fields agree with the two independently-built sources.
    vm = build_task_view_model(reg, "task_alpha").as_dict()
    snap = port.lifecycle_snapshot(ref)
    assert data["status"] == snap.state == vm["status"]
    assert data["terminal"] == snap.terminal == vm["terminal"]
    assert data["last_seq"] == snap.last_seq == vm["last_seq"]
    assert data["attach_count"] == snap.attach_count
    assert scan_for_leak(data) is None


def test_workbench_view_terminal_task_is_terminal_and_not_alive() -> None:
    mod = _workbench_mod()
    reg, backend, port, ref = _running_port()
    port.kill(ref)  # drive to a terminal (cancelled) state through the public API

    view = mod.build_agent_run_supervisor_workbench_view(reg, port, ref)
    data = view.as_dict()
    assert data["status"] == "cancelled"
    assert data["terminal"] is True
    assert data["alive"] is False
    assert data["resumable"] is False
    assert data["reapable"] is False
    assert data["permission_state"] == "none"
    assert data["surfaces"] == ["status"]


# --------------------------------------------------------------------------- #
# C. permission_wait surfaces operator decision + stays alive/resumable
# --------------------------------------------------------------------------- #
def test_workbench_view_permission_wait_surfaces_operator_decision_and_stays_alive() -> None:
    mod = _workbench_mod()
    reg, backend, port, ref = _running_port()
    backend.fake_enter_permission_wait("task_alpha")
    port.status(ref)  # persist permission_wait into the canonical log

    view = mod.build_agent_run_supervisor_workbench_view(reg, port, ref)
    data = view.as_dict()
    assert data["status"] == "permission_wait"
    assert data["permission_state"] == "waiting"
    assert data["requires_operator_decision"] is True
    assert data["surfaces"] == ["status", "permission"]
    assert data["alive"] is True
    assert data["resumable"] is True
    assert data["terminal"] is False
    assert data["reapable"] is False
    assert scan_for_leak(data) is None


# --------------------------------------------------------------------------- #
# D. Resume determinism + no duplicate attach after re-attach / close
# --------------------------------------------------------------------------- #
def test_workbench_view_resume_fields_stable_and_no_duplicate_attach_after_reattach() -> None:
    mod = _workbench_mod()
    reg, backend, first, ref = _running_port()
    before = mod.build_agent_run_supervisor_workbench_view(reg, first, ref).as_dict()
    seq_before = reg.log.last_seq("task_alpha")

    second = AgentRunSupervisorPort(reg, backend)
    ref2 = second.create_or_attach("task_alpha", _spec())
    assert ref2 == ref
    after = mod.build_agent_run_supervisor_workbench_view(reg, second, ref2).as_dict()

    assert reg.log.last_seq("task_alpha") == seq_before  # re-attach appended nothing
    assert after["attach_count"] == 1
    assert after["resume_cursor"] == before["resume_cursor"]
    assert after["last_seq"] == before["last_seq"]
    assert after["event_count"] == before["event_count"]
    assert after == before  # deterministic, byte-identical composition


def test_workbench_view_after_close_and_reattach_is_consistent_without_new_events() -> None:
    mod = _workbench_mod()
    reg, backend, port, ref = _running_port()
    view_before = mod.build_agent_run_supervisor_workbench_view(reg, port, ref).as_dict()
    seq_before = reg.log.last_seq("task_alpha")

    port.close(ref)  # adapter-local handoff: no backend kill, no event
    reopened = AgentRunSupervisorPort(reg, backend)
    ref2 = reopened.create_or_attach("task_alpha", _spec())
    view_after = mod.build_agent_run_supervisor_workbench_view(reg, reopened, ref2).as_dict()

    assert reg.log.last_seq("task_alpha") == seq_before  # no respawn / duplicate events
    assert view_after == view_before
    assert view_after["attach_count"] == 1


# --------------------------------------------------------------------------- #
# E. Unknown / untracked / forged refs fail closed and do not echo material
# --------------------------------------------------------------------------- #
def test_workbench_view_forged_session_ref_fails_closed() -> None:
    mod = _workbench_mod()
    reg, backend, port, _ref = _running_port()
    with pytest.raises(SpineError) as exc:
        mod.build_agent_run_supervisor_workbench_view(
            reg, port, SessionRef(task_id="task_alpha", session_id="sess_forged")
        )
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_workbench_view_untracked_task_fails_closed() -> None:
    mod = _workbench_mod()
    reg, backend, port, _ref = _running_port()
    with pytest.raises(SpineError) as exc:
        mod.build_agent_run_supervisor_workbench_view(reg, port, "task_missing")
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_workbench_view_forbidden_ref_string_does_not_echo_bad_material() -> None:
    mod = _workbench_mod()
    reg, backend, port, _ref = _running_port()
    with pytest.raises(SpineError) as exc:
        mod.build_agent_run_supervisor_workbench_view(reg, port, "chat_id_leak")
    assert "chat_id" not in str(exc.value)


def test_workbench_view_rejects_registry_port_mismatch() -> None:
    mod = _workbench_mod()
    _reg, _backend, port, ref = _running_port()
    other_registry = TaskRegistry()  # does not know task_alpha
    with pytest.raises(SpineError) as exc:
        mod.build_agent_run_supervisor_workbench_view(other_registry, port, ref)
    assert exc.value.code in {RUNTIME_INVALID_VIEW_MODEL, mod.RUNTIME_INVALID_WORKBENCH_VIEW}


def test_workbench_view_rejects_non_registry_or_non_exact_port() -> None:
    mod = _workbench_mod()
    reg, backend, port, ref = _running_port()

    class _PortSubclass(AgentRunSupervisorPort):
        pass

    with pytest.raises(SpineError) as exc:
        mod.build_agent_run_supervisor_workbench_view(object(), port, ref)
    assert exc.value.code == mod.RUNTIME_INVALID_WORKBENCH_VIEW
    with pytest.raises(SpineError) as exc2:
        mod.build_agent_run_supervisor_workbench_view(reg, object(), ref)
    assert exc2.value.code == mod.RUNTIME_INVALID_WORKBENCH_VIEW
    with pytest.raises(SpineError) as exc3:
        mod.build_agent_run_supervisor_workbench_view(reg, _PortSubclass(reg, backend), ref)
    assert exc3.value.code == mod.RUNTIME_INVALID_WORKBENCH_VIEW


# --------------------------------------------------------------------------- #
# F. No-leak / fail-closed trust boundary on the value object
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("canary", _LEAK_CANARIES)
def test_workbench_view_direct_construction_rejects_raw_or_platform_refs(canary: str) -> None:
    mod = _workbench_mod()
    with pytest.raises(SpineError) as exc:
        mod.AgentRunSupervisorWorkbenchView(
            **_valid_workbench_kwargs(mod, refs=[f"ref_{canary}_x"])
        )
    assert exc.value.code == mod.RUNTIME_INVALID_WORKBENCH_VIEW
    assert canary not in str(exc.value)


def test_workbench_view_rejects_inconsistent_liveness_and_terminal_state() -> None:
    mod = _workbench_mod()
    # reapable is only coherent over a live, non-terminal projected lifecycle.
    with pytest.raises(SpineError) as exc:
        mod.AgentRunSupervisorWorkbenchView(
            **_valid_workbench_kwargs(
                mod,
                status="completed",
                terminal=True,
                alive=False,
                resumable=False,
                reapable=True,
            )
        )
    assert exc.value.code == mod.RUNTIME_INVALID_WORKBENCH_VIEW


def test_workbench_view_rejects_broken_resume_counter_invariants() -> None:
    mod = _workbench_mod()
    for bad in (
        {"last_seq": 3, "event_count": 2},  # last_seq != event_count
        {"resume_cursor": 5},               # resume_cursor != last_seq
        {"attach_count": 9},                # attach_count > event_count
        {"attach_count": 0},                # a tracked view always has >= 1 attach
    ):
        with pytest.raises(SpineError) as exc:
            mod.AgentRunSupervisorWorkbenchView(**_valid_workbench_kwargs(mod, **bad))
        assert exc.value.code == mod.RUNTIME_INVALID_WORKBENCH_VIEW


def test_validate_workbench_view_rejects_forged_object_new() -> None:
    mod = _workbench_mod()
    forged = object.__new__(mod.AgentRunSupervisorWorkbenchView)
    for name, value in _valid_workbench_kwargs(
        mod,
        # alive/terminal inconsistent with status, resume counters out of step.
        status="running",
        alive=False,
        terminal=True,
        last_seq=2,
        event_count=5,
    ).items():
        object.__setattr__(forged, name, value)
    assert type(forged) is mod.AgentRunSupervisorWorkbenchView
    with pytest.raises(SpineError) as exc:
        mod.validate_agent_run_supervisor_workbench_view(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_WORKBENCH_VIEW


def test_workbench_view_cannot_be_mutated_to_echo_raw_material() -> None:
    mod = _workbench_mod()
    reg, backend, port, ref = _running_port()
    view = mod.build_agent_run_supervisor_workbench_view(reg, port, ref)
    with pytest.raises((AttributeError, TypeError, SpineError)):
        view.refs.append("raw_prompt_dump")
    assert "raw_prompt" not in str(view.as_dict())
    assert scan_for_leak(view.as_dict()) is None


def test_as_dict_revalidates_mutable_forgery_before_returning() -> None:
    mod = _workbench_mod()
    forged = object.__new__(mod.AgentRunSupervisorWorkbenchView)
    for name, value in _valid_workbench_kwargs(mod, refs=["raw_prompt_dump"]).items():
        object.__setattr__(forged, name, value)
    with pytest.raises(SpineError) as exc:
        forged.as_dict()
    assert exc.value.code == mod.RUNTIME_INVALID_WORKBENCH_VIEW
    assert "raw_prompt" not in str(exc.value)


# --------------------------------------------------------------------------- #
# G. Serialization is byte-stable, revalidating, and leak-free
# --------------------------------------------------------------------------- #
def test_serialize_workbench_view_is_byte_stable_and_leak_free() -> None:
    mod = _workbench_mod()
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach(
        "task_alpha", _spec(refs=("ws_alpha", "policy_default", "ref_plan"))
    )
    view = mod.build_agent_run_supervisor_workbench_view(reg, port, ref)
    encoded = mod.serialize_agent_run_supervisor_workbench_view(view)
    assert type(encoded) is bytes
    assert encoded == mod.serialize_agent_run_supervisor_workbench_view(view)
    assert b"ws_alpha" in encoded and b"policy_default" in encoded
    for leak in (b"raw_prompt", b"chat_id", b"card_json", b"agent_stdout", b"/tmp/"):
        assert leak not in encoded


def test_serialize_workbench_view_revalidates_forged_view() -> None:
    mod = _workbench_mod()
    forged = object.__new__(mod.AgentRunSupervisorWorkbenchView)
    for name, value in _valid_workbench_kwargs(mod, refs=["chat_id_leak_ref"]).items():
        object.__setattr__(forged, name, value)
    with pytest.raises(SpineError) as exc:
        mod.serialize_agent_run_supervisor_workbench_view(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_WORKBENCH_VIEW
    assert "chat_id" not in str(exc.value)


# --------------------------------------------------------------------------- #
# H. Orphan / reapable via optional liveness — no log mutation (PR3 policy)
# --------------------------------------------------------------------------- #
def test_workbench_view_surfaces_reapable_from_liveness_without_mutating_log() -> None:
    mod = _workbench_mod()
    reg, backend, port, ref = _running_port()
    backend.fake_orphan("task_alpha")
    live = port.liveness(ref)
    assert live.state == "orphaned" and live.reapable is True
    seq_before = reg.log.last_seq("task_alpha")

    view = mod.build_agent_run_supervisor_workbench_view(reg, port, ref, liveness=live)
    data = view.as_dict()
    # The projected lifecycle stays alive / non-terminal; orphan is only a hint.
    assert data["status"] == "running"
    assert data["alive"] is True
    assert data["terminal"] is False
    assert data["reapable"] is True
    # No terminal / reap event is auto-written to the canonical log.
    assert reg.log.last_seq("task_alpha") == seq_before
    assert "cancelled" not in _event_types(reg, "task_alpha")
    assert scan_for_leak(data) is None


def test_workbench_view_default_build_omits_reapable() -> None:
    mod = _workbench_mod()
    reg, backend, port, ref = _running_port()
    backend.fake_orphan("task_alpha")
    # Without an explicitly supplied liveness the builder makes no backend call,
    # so it never fabricates a reapable/orphan health signal.
    view = mod.build_agent_run_supervisor_workbench_view(reg, port, ref)
    assert view.as_dict()["reapable"] is False


def test_workbench_view_rejects_mismatched_liveness() -> None:
    mod = _workbench_mod()
    reg, backend, port, ref = _running_port()
    mismatched = LivenessState(
        task_id="task_alpha",
        session_id="sess_999",
        state="orphaned",
        alive=False,
        permission_wait=False,
        reapable=True,
    )
    with pytest.raises(SpineError) as exc:
        mod.build_agent_run_supervisor_workbench_view(reg, port, ref, liveness=mismatched)
    assert exc.value.code == mod.RUNTIME_INVALID_WORKBENCH_VIEW


# --------------------------------------------------------------------------- #
# I. Read-only: building / serializing appends no event, launches no work
# --------------------------------------------------------------------------- #
def test_building_and_serializing_workbench_view_appends_no_events_or_work() -> None:
    mod = _workbench_mod()
    reg, backend, port, ref = _running_port()
    before = reg.log.last_seq("task_alpha")
    backend_sessions = backend.session_count()

    for _ in range(3):
        view = mod.build_agent_run_supervisor_workbench_view(reg, port, ref)
        mod.serialize_agent_run_supervisor_workbench_view(view)
        build_task_view_model(reg, "task_alpha")

    assert reg.log.last_seq("task_alpha") == before  # no appended events
    assert backend.session_count() == backend_sessions  # no respawn / launch
    assert port.session_count() == 1


# --------------------------------------------------------------------------- #
# J. Static boundary scan — no real runtime / IM / delivery wiring in source
# --------------------------------------------------------------------------- #
_FORBIDDEN_SOURCE_TOKENS = (
    "subprocess",
    "socket",
    ".Popen(",
    "os.system",
    "create_subprocess",
    "import temporalio",
    "acpx",
    " npx",
    "asyncio.create",
    "gateway",
    "feishu",
    "lark",
    "send(",
    "edit_message",
    "im_send",
    "delivery_payload",
)


def test_workbench_source_wires_no_real_runtime_or_delivery_surface() -> None:
    mod = _workbench_mod()
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert [token for token in _FORBIDDEN_SOURCE_TOKENS if token in source] == []
    import_lines = [ln for ln in source.splitlines() if ln.startswith(("import ", "from "))]
    for line in import_lines:
        for root in (
            "subprocess",
            "socket",
            "temporal",
            "gateway",
            "feishu",
            "lark",
            "httpx",
            "requests",
            "urllib",
            "docker",
            "asyncio",
        ):
            assert root not in line, f"forbidden import {root!r}: {line!r}"
