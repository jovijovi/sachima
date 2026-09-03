"""R2 — deterministic offline fake ``agent-run-supervisor`` execution port.

RED/GREEN tests for the ``FakeSupervisorPort`` adapter (design §4/§7/§8/§11,
plan §6). It proves the execution-port contract against a *fake, offline,
deterministic* supervisor: ``create_or_attach`` yields at most one live session
per ``task_id`` (duplicate calls attach, never spawn), ``permission-wait`` is a
live state, ``kill`` / terminal / reap append refs-only events into the R1 Task
Event Log, the simulated event stream flows through the deterministic Status
Projection, and the orphan-reaper policy runs only against fake liveness.

The module under test is pure local/offline Python. It launches no real
``agent-run-supervisor``, no agent / acpx / npx runtime, no OS process, no
subprocess, Docker, daemon, socket, Temporal Worker/service, Gateway, or Feishu
surface, and makes no network call. Forbidden terms are no-leak canaries only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import sachima_supervisor.runtime_spine.execution_port as execution_port_mod
import sachima_supervisor.runtime_spine.fake_supervisor_port as fake_mod
from sachima_supervisor.runtime_spine import (
    RUNTIME_EVENT_LEAK_DETECTED,
    RUNTIME_INVALID_EVENT,
    RUNTIME_INVALID_LAUNCH_SPEC,
    RUNTIME_INVALID_TASK_ID,
    STABLE_CODES,
    ExecutionPort,
    FakeSupervisorPort,
    LivenessState,
    SessionRef,
    SessionStatus,
    SpineError,
    TaskRegistry,
    build_launch_spec,
    event_projection,
    project,
    scan_for_leak,
    serialize_projection,
)
from sachima_supervisor.runtime_spine.execution_port import RUNTIME_INVALID_SESSION

_ALL_FAIL_CODES = set(STABLE_CODES) | {RUNTIME_INVALID_SESSION}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _agent_spec(task_id: str = "task_alpha", *, refs: tuple[str, ...] = ()):
    """A valid live-agent LaunchSpec (needs_agent → liveness-capable kind)."""

    return build_launch_spec(
        task_id=task_id,
        agent_kind="local_agent",
        mode_flags={"needs_agent": True},
        refs=refs,
    )


def _new_port() -> tuple[FakeSupervisorPort, TaskRegistry]:
    reg = TaskRegistry()
    return FakeSupervisorPort(reg), reg


def _event_types(reg: TaskRegistry, task_id: str) -> list[str]:
    return [e.event_type for e in reg.log.events_for(task_id)]


# --------------------------------------------------------------------------- #
# A. Construction — the port is a genuine ExecutionPort over a genuine registry
# --------------------------------------------------------------------------- #
def test_fake_port_is_an_execution_port() -> None:
    port, _ = _new_port()
    assert isinstance(port, ExecutionPort)


def test_fake_port_rejects_hostile_registry() -> None:
    class _HostileRegistry(TaskRegistry):
        pass

    for bad in (None, object(), {}, _HostileRegistry()):
        with pytest.raises(SpineError) as exc:
            FakeSupervisorPort(bad)  # type: ignore[arg-type]
        assert exc.value.code in _ALL_FAIL_CODES


# --------------------------------------------------------------------------- #
# B. create_or_attach — ≤1 live session per task_id; duplicate attaches
# --------------------------------------------------------------------------- #
def test_create_or_attach_returns_session_ref_and_runs() -> None:
    port, reg = _new_port()
    ref = port.create_or_attach("task_alpha", _agent_spec())
    assert type(ref) is SessionRef
    assert ref.task_id == "task_alpha"
    assert ref.session_id.startswith("sess_")
    # The task record + a running attach event now live in the canonical log.
    assert reg.has_task("task_alpha") is True
    assert "agent_attached" in _event_types(reg, "task_alpha")
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["status"] == "running"


def test_duplicate_create_or_attach_returns_same_session_no_spawn() -> None:
    port, reg = _new_port()
    ref1 = port.create_or_attach("task_alpha", _agent_spec())
    seq_after_first = reg.log.last_seq("task_alpha")
    ref2 = port.create_or_attach("task_alpha", _agent_spec())
    # Same session ref, and NOT a second session (≤1 live session per task_id).
    assert ref1 == ref2
    assert ref1.session_id == ref2.session_id
    assert port.session_count() == 1
    # The second call attaches to the existing session — it appends NO new events
    # (no second spawn), so the log is byte-for-byte unchanged.
    assert reg.log.last_seq("task_alpha") == seq_after_first
    assert _event_types(reg, "task_alpha").count("agent_attached") == 1


def test_create_or_attach_rejects_existing_non_agent_task_without_attach() -> None:
    port, reg = _new_port()
    reg.create_task("task_alpha", needs_agent=False, needs_durable=False)
    seq_before = reg.log.last_seq("task_alpha")
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _agent_spec())
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC
    assert port.session_count() == 0
    assert reg.log.last_seq("task_alpha") == seq_before
    assert "agent_attached" not in _event_types(reg, "task_alpha")


def test_duplicate_create_or_attach_rejects_conflicting_launch_spec() -> None:
    port, reg = _new_port()
    ref = port.create_or_attach("task_alpha", _agent_spec(refs=("ref_plan",)))
    seq_after_first = reg.log.last_seq("task_alpha")
    conflicting = build_launch_spec(
        task_id="task_alpha",
        agent_kind="local_agent",
        mode_flags={"needs_agent": True, "needs_durable": True},
        refs=("ref_other",),
    )
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", conflicting)
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC
    assert port.session_count() == 1
    assert port.status(ref).state == "running"
    assert reg.log.last_seq("task_alpha") == seq_after_first


def test_create_or_attach_single_session_under_repeated_calls() -> None:
    port, _ = _new_port()
    refs = {port.create_or_attach("task_alpha", _agent_spec()) for _ in range(6)}
    assert len(refs) == 1
    assert port.session_count() == 1
    live = port.liveness("task_alpha")
    assert live.alive is True


def test_create_or_attach_rejects_unsafe_task_id() -> None:
    port, _ = _new_port()
    for bad in ("Task Alpha", "chat_id_1", "1bad", ""):
        with pytest.raises(SpineError) as exc:
            port.create_or_attach(bad, _agent_spec("task_alpha"))
        assert exc.value.code in {RUNTIME_INVALID_TASK_ID, RUNTIME_INVALID_SESSION, RUNTIME_INVALID_LAUNCH_SPEC}


def test_create_or_attach_rejects_wrong_launch_spec_type() -> None:
    port, _ = _new_port()
    for bad in (None, {}, "local_agent", object(), 42):
        with pytest.raises(SpineError) as exc:
            port.create_or_attach("task_alpha", bad)  # type: ignore[arg-type]
        assert exc.value.code in _ALL_FAIL_CODES


def test_create_or_attach_rejects_mismatched_task_id_spec() -> None:
    port, _ = _new_port()
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _agent_spec("task_beta"))
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


def test_create_or_attach_rejects_non_agent_spec() -> None:
    port, _ = _new_port()
    # A non-agent (inline_tool) spec never routes through the supervisor.
    inline = build_launch_spec(task_id="task_alpha", agent_kind="inline_tool")
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", inline)
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


def test_create_or_attach_rejects_hostile_launch_spec_subclass() -> None:
    from sachima_supervisor.runtime_spine import LaunchSpec

    class _Hostile(LaunchSpec):
        def __post_init__(self) -> None:  # skip fail-closed validation
            return None

    hostile = _Hostile(
        task_id="task_alpha",
        agent_kind="local_agent",
        needs_agent=True,
        needs_durable=False,
        required_capabilities=(),
        roles=(),
        refs=(),
    )
    port, _ = _new_port()
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", hostile)
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


# --------------------------------------------------------------------------- #
# C. stream — refs-only, deterministic replay of the supervisor's events
# --------------------------------------------------------------------------- #
def test_stream_returns_refs_only_deterministic_events() -> None:
    port, reg = _new_port()
    ref = port.create_or_attach("task_alpha", _agent_spec(refs=("ref_plan",)))
    stream1 = port.stream(ref)
    stream2 = port.stream(ref)
    assert stream1 == stream2  # deterministic
    assert all(isinstance(chunk, dict) for chunk in stream1)
    # Each chunk equals the R1 refs-only event view; no raw material.
    log_view = tuple(event_projection(e) for e in reg.log.events_for("task_alpha"))
    assert stream1 == log_view
    assert scan_for_leak(list(stream1)) is None


def test_stream_accepts_task_id_and_rejects_forged_ref() -> None:
    port, _ = _new_port()
    ref = port.create_or_attach("task_alpha", _agent_spec())
    assert port.stream("task_alpha") == port.stream(ref)
    # A forged ref whose session_id does not match the live session fails closed.
    forged = SessionRef(task_id="task_alpha", session_id="sess_999")
    with pytest.raises(SpineError) as exc:
        port.stream(forged)
    assert exc.value.code == RUNTIME_INVALID_SESSION
    # Unknown task fails closed too.
    with pytest.raises(SpineError):
        port.stream("task_missing")


# --------------------------------------------------------------------------- #
# D. liveness — permission-wait is ALIVE, not stalled
# --------------------------------------------------------------------------- #
def test_liveness_running_is_alive() -> None:
    port, _ = _new_port()
    port.create_or_attach("task_alpha", _agent_spec())
    live = port.liveness("task_alpha")
    assert type(live) is LivenessState
    assert live.state == "running"
    assert live.alive is True
    assert live.permission_wait is False
    assert live.reapable is False


def test_liveness_permission_wait_is_alive_not_reapable() -> None:
    port, _ = _new_port()
    port.create_or_attach("task_alpha", _agent_spec())
    port.request_permission("task_alpha", "ref_perm_prompt")
    live = port.liveness("task_alpha")
    assert live.state == "permission_wait"
    assert live.alive is True  # NOT stalled — an expected live state
    assert live.permission_wait is True
    assert live.reapable is False


def test_liveness_rejects_forged_ref() -> None:
    port, _ = _new_port()
    port.create_or_attach("task_alpha", _agent_spec())
    with pytest.raises(SpineError) as exc:
        port.liveness(SessionRef(task_id="task_alpha", session_id="sess_forged"))
    assert exc.value.code == RUNTIME_INVALID_SESSION


# --------------------------------------------------------------------------- #
# E. signal — the permission roundtrip returns via signal(task_id, decision/ref)
# --------------------------------------------------------------------------- #
def test_permission_roundtrip_request_then_signal() -> None:
    port, reg = _new_port()
    port.create_or_attach("task_alpha", _agent_spec())
    port.request_permission("task_alpha", "ref_perm_prompt")
    assert "permission_requested" in _event_types(reg, "task_alpha")
    snap_wait = reg.snapshot("task_alpha")
    assert snap_wait is not None
    assert snap_wait["status"] == "permission_wait"

    status = port.signal("task_alpha", "ref_decision_allow")
    assert type(status) is SessionStatus
    assert status.state == "running"
    assert "permission_answered" in _event_types(reg, "task_alpha")
    # Back to a live, non-waiting state.
    live = port.liveness("task_alpha")
    assert live.alive is True
    assert live.permission_wait is False


def test_signal_without_pending_permission_fails_closed() -> None:
    port, _ = _new_port()
    port.create_or_attach("task_alpha", _agent_spec())
    # No permission_requested is pending — nothing to answer.
    with pytest.raises(SpineError) as exc:
        port.signal("task_alpha", "ref_decision_allow")
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_signal_on_unknown_task_fails_closed() -> None:
    port, _ = _new_port()
    with pytest.raises(SpineError) as exc:
        port.signal("task_missing", "ref_decision_allow")
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_signal_rejects_leaky_decision_ref() -> None:
    port, _ = _new_port()
    port.create_or_attach("task_alpha", _agent_spec())
    port.request_permission("task_alpha", "ref_perm_prompt")
    for leaky in ("raw_prompt_here", "chat_id", "oc_secret", "Bad Ref"):
        with pytest.raises(SpineError) as exc:
            port.signal("task_alpha", leaky)
        assert exc.value.code in {RUNTIME_INVALID_EVENT, RUNTIME_EVENT_LEAK_DETECTED, RUNTIME_INVALID_SESSION}
        assert "raw_prompt" not in str(exc.value)


# --------------------------------------------------------------------------- #
# F. status — projection-derived session status
# --------------------------------------------------------------------------- #
def test_status_reflects_projection() -> None:
    port, reg = _new_port()
    ref = port.create_or_attach("task_alpha", _agent_spec())
    status = port.status(ref)
    assert type(status) is SessionStatus
    assert status.state == "running"
    assert status.alive is True
    assert status.terminal is False
    proj = project(reg.log.events_for("task_alpha"), task_id="task_alpha")
    assert status.last_seq == proj["last_seq"]
    assert status.projected_status == proj["status"]
    # status(task_id) and status(ref) agree.
    assert port.status("task_alpha") == status


def test_status_rejects_forged_ref_and_unknown_task() -> None:
    port, _ = _new_port()
    port.create_or_attach("task_alpha", _agent_spec())
    with pytest.raises(SpineError) as exc:
        port.status(SessionRef(task_id="task_alpha", session_id="sess_bogus"))
    assert exc.value.code == RUNTIME_INVALID_SESSION
    with pytest.raises(SpineError):
        port.status("task_missing")


# --------------------------------------------------------------------------- #
# G. kill — appends refs-only terminal events; idempotent
# --------------------------------------------------------------------------- #
def test_kill_appends_refs_only_terminal_event() -> None:
    port, reg = _new_port()
    ref = port.create_or_attach("task_alpha", _agent_spec())
    status = port.kill(ref, reason_ref="ref_operator_kill")
    assert status.terminal is True
    assert status.alive is False
    # A terminal (cancelled) event now lives in the canonical log, refs-only.
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["status"] == "cancelled"
    assert snap["terminal"] is True
    for e in reg.log.events_for("task_alpha"):
        assert scan_for_leak(event_projection(e)) is None
    # liveness after kill: dead, and NOT reapable (cleanly terminal, not orphaned).
    live = port.liveness("task_alpha")
    assert live.alive is False
    assert live.reapable is False


def test_kill_is_idempotent() -> None:
    port, reg = _new_port()
    ref = port.create_or_attach("task_alpha", _agent_spec())
    port.kill(ref)
    seq_after_kill = reg.log.last_seq("task_alpha")
    status2 = port.kill(ref)  # killing an already-terminal session is a no-op
    assert status2.terminal is True
    assert reg.log.last_seq("task_alpha") == seq_after_kill


def test_kill_rejects_forged_ref_and_leaky_reason() -> None:
    port, _ = _new_port()
    ref = port.create_or_attach("task_alpha", _agent_spec())
    with pytest.raises(SpineError) as exc:
        port.kill(SessionRef(task_id="task_alpha", session_id="sess_forged"))
    assert exc.value.code == RUNTIME_INVALID_SESSION
    with pytest.raises(SpineError) as exc2:
        port.kill(ref, reason_ref="agent_stdout_dump")
    assert exc2.value.code in {RUNTIME_INVALID_EVENT, RUNTIME_EVENT_LEAK_DETECTED}
    assert "agent_stdout" not in str(exc2.value)


def test_create_or_attach_after_kill_never_respawns() -> None:
    # No agent-death respawn in R2 — a terminal task returns its same (terminal)
    # ref and never spawns a second session.
    port, reg = _new_port()
    ref = port.create_or_attach("task_alpha", _agent_spec())
    port.kill(ref)
    seq_after_kill = reg.log.last_seq("task_alpha")
    ref2 = port.create_or_attach("task_alpha", _agent_spec())
    assert ref2 == ref
    assert port.session_count() == 1
    assert reg.log.last_seq("task_alpha") == seq_after_kill  # no respawn events


# --------------------------------------------------------------------------- #
# H. Orphan reaper — defined + tested ONLY against fake liveness
# --------------------------------------------------------------------------- #
def test_orphan_reaper_reaps_dead_session_and_emits_terminal() -> None:
    port, reg = _new_port()
    ref = port.create_or_attach("task_alpha", _agent_spec())
    port.simulate_orphan("task_alpha")  # fake: the live session died, no clean exit
    live = port.liveness("task_alpha")
    assert live.state == "orphaned"
    assert live.alive is False
    assert live.reapable is True

    reaped = port.reap_orphans()
    assert ref in reaped
    # Reaping reconciles the dead session into the log with a terminal event.
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["terminal"] is True
    after = port.liveness("task_alpha")
    assert after.alive is False
    assert after.reapable is False  # already reclaimed


def test_orphan_reaper_never_reaps_permission_wait() -> None:
    port, reg = _new_port()
    port.create_or_attach("task_alpha", _agent_spec())
    port.request_permission("task_alpha", "ref_perm_prompt")
    seq_before = reg.log.last_seq("task_alpha")
    reaped = port.reap_orphans()
    assert reaped == ()
    # A legitimately-waiting session is never reaped and never gets a terminal event.
    assert reg.log.last_seq("task_alpha") == seq_before
    assert port.liveness("task_alpha").alive is True


def test_orphan_reaper_never_reaps_running() -> None:
    port, reg = _new_port()
    port.create_or_attach("task_alpha", _agent_spec())
    seq_before = reg.log.last_seq("task_alpha")
    assert port.reap_orphans() == ()
    assert reg.log.last_seq("task_alpha") == seq_before


def test_orphan_reaper_is_idempotent() -> None:
    port, reg = _new_port()
    port.create_or_attach("task_alpha", _agent_spec())
    port.simulate_orphan("task_alpha")
    port.reap_orphans()
    seq_after = reg.log.last_seq("task_alpha")
    assert port.reap_orphans() == ()  # nothing left to reap
    assert reg.log.last_seq("task_alpha") == seq_after


def test_simulate_orphan_requires_running_session() -> None:
    port, _ = _new_port()
    # No session yet — nothing to orphan.
    with pytest.raises(SpineError) as exc:
        port.simulate_orphan("task_alpha")
    assert exc.value.code == RUNTIME_INVALID_SESSION


# --------------------------------------------------------------------------- #
# I. Determinism — events flow through the R1 log + Status Projection
# --------------------------------------------------------------------------- #
def _drive(port: FakeSupervisorPort) -> None:
    port.create_or_attach("task_alpha", _agent_spec(refs=("ref_plan",)))
    port.emit_progress("task_alpha", refs=("ref_step_one",))
    port.request_permission("task_alpha", "ref_perm_prompt")
    port.signal("task_alpha", "ref_decision_allow")
    port.complete("task_alpha", result_ref="ref_result")


def test_events_flow_through_projection_and_snapshot_agrees() -> None:
    port, reg = _new_port()
    _drive(port)
    fresh = project(reg.log.events_for("task_alpha"), task_id="task_alpha")
    snap = reg.snapshot("task_alpha")
    assert snap == fresh
    assert fresh["status"] == "completed"
    assert fresh["terminal"] is True


def test_projection_is_byte_stable_and_port_independent() -> None:
    port_a, reg_a = _new_port()
    port_b, reg_b = _new_port()
    _drive(port_a)
    _drive(port_b)
    proj_a = project(reg_a.log.events_for("task_alpha"), task_id="task_alpha")
    proj_b = project(reg_b.log.events_for("task_alpha"), task_id="task_alpha")
    # Same operation sequence → byte-identical serialized projection.
    assert serialize_projection(proj_a) == serialize_projection(proj_b)
    assert serialize_projection(proj_a) == serialize_projection(proj_a)


def test_no_event_body_leaks_raw_material() -> None:
    port, reg = _new_port()
    _drive(port)
    port.create_or_attach("task_beta", _agent_spec("task_beta"))
    port.kill("task_beta", reason_ref="ref_stop")
    for task in ("task_alpha", "task_beta"):
        for e in reg.log.events_for(task):
            assert scan_for_leak(event_projection(e)) is None


# --------------------------------------------------------------------------- #
# J. Structural guard — the source wires NO real runtime / process / network
# --------------------------------------------------------------------------- #
_FORBIDDEN_CODE_TOKENS = (
    "subprocess.",
    "import subprocess",
    "import socket",
    "socket.socket",
    ".Popen(",
    "os.system(",
    "os.popen(",
    "create_subprocess",
    "multiprocessing",
    "import temporalio",
    "from temporalio",
    "acpx",
    " npx",
    "asyncio.create",
)


@pytest.mark.parametrize("module", (execution_port_mod, fake_mod))
def test_source_wires_no_real_runtime(module) -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")
    for token in _FORBIDDEN_CODE_TOKENS:
        assert token not in source, f"forbidden wiring token {token!r} in {module.__name__}"
    # No network/runtime client libraries imported.
    import_lines = [ln for ln in source.splitlines() if re.match(r"^\s*(import|from)\s", ln)]
    denied_roots = ("subprocess", "socket", "temporal", "gateway", "feishu", "lark", "httpx", "requests", "urllib", "aiohttp", "docker", "multiprocessing", "asyncio")
    for line in import_lines:
        for root in denied_roots:
            assert root not in line, f"forbidden import {root!r} in {module.__name__}: {line!r}"
