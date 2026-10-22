"""PR3 — persistent session lifecycle hardening on ``AgentRunSupervisorPort``.

Focused RED/GREEN tests for the PR3 persistent-lifecycle slice layered on the
already-merged PR1 adapter and PR2 read-only smoke harness. Everything here stays
pure local/offline Python over the deterministic in-memory
``DefaultAgentRunSupervisorBackend``: no real agent/process/network/durable
service/delivery/listener is started, and no Gateway/Temporal Worker is touched.

The PR3 semantics proven here, refs-only and fail-closed:

* **Persistent create/attach** — a port reconstructed over the *same* registry +
  backend re-attaches an existing session (running or ``permission_wait``) with no
  duplicate ``agent_attached`` event; reconstructing over a *fresh/missing* backend
  fails closed and never respawns; a task keeps at most one live session.
* **Stream cursor / resume** — ``stream(ref, since_seq=cursor)`` resumes only the
  events after the cursor (no duplicate replay), and a refs-only
  ``lifecycle_snapshot`` exposes ``last_seq`` / ``event_count`` / ``attach_count``
  safe resume data — with ``attach_count == 1`` across a lifecycle re-attach.
* **Signal / kill / close** — ``close`` is an adapter-local, default-off port
  handoff that drops local tracking only (no backend kill, no event, no registry
  mutation); ``signal`` still requires an existing ``permission_wait`` and cannot
  resurrect a terminal/closed session; ``kill`` stays terminal/idempotent.
* **Liveness / status backend-failure policy (Codex WATCH)** — a later
  status/liveness backend read failure collapses to a stable code and never marks,
  kills, orphans, or mutates the existing persisted session/log; an ``orphaned``
  backend state is reapable via liveness but is NOT auto-marked terminal in the
  canonical log.
* **Lease / task binding** — no role or workspace-ref drift can attach to an
  existing session; a re-attach preserves the read-only role + workspace/policy
  binding.

Forbidden terms below are no-leak canaries only, never behavior.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import sachima_supervisor.runtime_spine.agent_run_supervisor_port as adapter_mod
from sachima_supervisor.runtime_spine import (
    ExecutionPort,
    LaunchSpec,
    SessionRef,
    SpineError,
    TaskRegistry,
    build_launch_spec,
    event_projection,
    scan_for_leak,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    LIFECYCLE_SNAPSHOT_TYPE,
    RUNTIME_SUPERVISOR_BACKEND_FAILURE,
    RUNTIME_SUPERVISOR_POLICY_DENIED,
    AgentRunSupervisorPort,
    DefaultAgentRunSupervisorBackend,
    LifecycleSnapshot,
    validate_lifecycle_snapshot,
)
from sachima_supervisor.runtime_spine.execution_port import RUNTIME_INVALID_SESSION
from sachima_supervisor.runtime_spine.events import RUNTIME_INVALID_LAUNCH_SPEC

_SAFE_REFS = ("ws_alpha", "policy_default")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
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


def _event_types(reg: TaskRegistry, task_id: str) -> list[str]:
    return [e.event_type for e in reg.log.events_for(task_id)]


def _attach_count(reg: TaskRegistry, task_id: str) -> int:
    return _event_types(reg, task_id).count("agent_attached")


class _FlakyStatusBackend(DefaultAgentRunSupervisorBackend):
    """Default backend whose ``status``/``liveness`` fail while a toggle is set."""

    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def status(self, handle):
        if self.fail:
            raise RuntimeError("transient boom stderr chat_id oc_secret /tmp/x")
        return super().status(handle)

    def liveness(self, handle):
        if self.fail:
            raise RuntimeError("transient boom stderr chat_id oc_secret /tmp/x")
        return super().liveness(handle)


# --------------------------------------------------------------------------- #
# A. Persistent create/attach lifecycle
# --------------------------------------------------------------------------- #
def test_reconstructed_port_reattaches_persisted_permission_wait_state() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    first = AgentRunSupervisorPort(reg, backend)
    spec = _spec()
    ref1 = first.create_or_attach("task_alpha", spec)
    backend.fake_enter_permission_wait("task_alpha")
    first.status("task_alpha")  # persist permission_wait into the log
    seq_after = reg.log.last_seq("task_alpha")

    second = AgentRunSupervisorPort(reg, backend)
    ref2 = second.create_or_attach("task_alpha", spec)
    assert ref2 == ref1
    assert second.session_count() == 1
    assert backend.session_count() == 1
    # No duplicate attach event and no new event at all from the re-attach.
    assert reg.log.last_seq("task_alpha") == seq_after
    assert _attach_count(reg, "task_alpha") == 1
    snap = second.lifecycle_snapshot("task_alpha")
    assert snap.state == "permission_wait"
    assert snap.alive is True
    assert snap.attach_count == 1


def test_reconstructed_port_over_fresh_backend_running_fails_closed_no_respawn() -> None:
    reg = TaskRegistry()
    first_backend = DefaultAgentRunSupervisorBackend()
    first = AgentRunSupervisorPort(reg, first_backend)
    spec = _spec()
    first.create_or_attach("task_alpha", spec)
    seq_before = reg.log.last_seq("task_alpha")

    fresh_backend = DefaultAgentRunSupervisorBackend()  # missing the session
    second = AgentRunSupervisorPort(reg, fresh_backend)
    with pytest.raises(SpineError) as exc:
        second.create_or_attach("task_alpha", spec)
    assert exc.value.code == RUNTIME_INVALID_SESSION
    assert second.session_count() == 0
    assert fresh_backend.session_count() == 0  # never respawned
    assert reg.log.last_seq("task_alpha") == seq_before


def test_reattach_keeps_at_most_one_live_session_across_ports() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    spec = _spec()
    refs = set()
    for _ in range(4):
        port = AgentRunSupervisorPort(reg, backend)
        refs.add(port.create_or_attach("task_alpha", spec))
    assert len(refs) == 1
    assert backend.session_count() == 1
    assert _attach_count(reg, "task_alpha") == 1


# --------------------------------------------------------------------------- #
# B. Stream cursor / resume — no duplicate replay
# --------------------------------------------------------------------------- #
def test_stream_resumes_from_cursor_without_duplicates() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    full = port.stream(ref)
    cursor = full[-1]["seq"]

    backend.fake_enter_permission_wait("task_alpha")
    resumed = port.stream(ref, since_seq=cursor)
    # Only events strictly after the cursor — no overlap with what was already seen.
    assert resumed
    assert all(chunk["seq"] > cursor for chunk in resumed)
    assert resumed[-1]["event_type"] == "permission_requested"
    # The resumed slice equals the tail of a full replay (no duplicate, no gap).
    assert tuple(resumed) == tuple(port.stream(ref, since_seq=cursor))
    assert tuple(port.stream(ref))[: len(full)] == full


def test_stream_cursor_at_head_returns_empty_no_replay() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    head = reg.log.last_seq("task_alpha")
    assert port.stream(ref, since_seq=head) == ()


def test_stream_rejects_invalid_cursor() -> None:
    reg = TaskRegistry()
    port = AgentRunSupervisorPort(reg, DefaultAgentRunSupervisorBackend())
    ref = port.create_or_attach("task_alpha", _spec())
    for bad in (-1, True, 1.5, "1", object()):
        with pytest.raises(SpineError) as exc:
            port.stream(ref, since_seq=bad)  # type: ignore[arg-type]
        assert exc.value.code == RUNTIME_INVALID_SESSION


def test_lifecycle_attach_replays_no_duplicate_events() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    first = AgentRunSupervisorPort(reg, backend)
    ref = first.create_or_attach("task_alpha", _spec())
    cursor = reg.log.last_seq("task_alpha")

    second = AgentRunSupervisorPort(reg, backend)
    ref2 = second.create_or_attach("task_alpha", _spec())
    assert ref2 == ref
    # A lifecycle re-attach adds no events, so a resume from the pre-attach cursor
    # yields nothing to replay.
    assert second.stream(ref2, since_seq=cursor) == ()
    assert _attach_count(reg, "task_alpha") == 1


# --------------------------------------------------------------------------- #
# C. lifecycle_snapshot — refs-only safe resume data
# --------------------------------------------------------------------------- #
def test_lifecycle_snapshot_exposes_safe_resume_data() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    snap = port.lifecycle_snapshot(ref)
    assert type(snap) is LifecycleSnapshot
    assert snap.task_id == "task_alpha"
    assert snap.session_id == ref.session_id
    assert snap.state == "running"
    assert snap.alive is True
    assert snap.terminal is False
    assert snap.resumable is True
    assert snap.attach_count == 1
    assert snap.last_seq == reg.log.last_seq("task_alpha")
    assert snap.event_count == snap.last_seq
    validate_lifecycle_snapshot(snap)


def test_lifecycle_snapshot_projection_is_refs_only_and_deterministic() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    first = port.lifecycle_snapshot(ref).to_projection()
    second = port.lifecycle_snapshot(ref).to_projection()
    assert first == second
    assert first["type"] == LIFECYCLE_SNAPSHOT_TYPE
    assert scan_for_leak(first) is None


def test_lifecycle_snapshot_is_stable_read_during_backend_failure() -> None:
    # The snapshot reads persisted Sachima state only (no backend call), so it is a
    # stable resume-data read even while the injected backend is unreachable.
    reg = TaskRegistry()
    backend = _FlakyStatusBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    backend.fail = True
    snap = port.lifecycle_snapshot(ref)
    assert snap.state == "running"
    assert snap.attach_count == 1
    assert snap.last_seq == reg.log.last_seq("task_alpha")


def test_lifecycle_snapshot_rejects_forged_ref() -> None:
    reg = TaskRegistry()
    port = AgentRunSupervisorPort(reg, DefaultAgentRunSupervisorBackend())
    port.create_or_attach("task_alpha", _spec())
    with pytest.raises(SpineError) as exc:
        port.lifecycle_snapshot(SessionRef(task_id="task_alpha", session_id="sess_forged"))
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_forged_lifecycle_snapshot_fails_closed() -> None:
    class _Hostile(LifecycleSnapshot):
        def __post_init__(self) -> None:  # skip fail-closed validation
            return None

    # alive/terminal inconsistent with state, and last_seq != event_count.
    hostile = _Hostile(
        task_id="task_alpha",
        session_id="sess_1",
        state="running",
        alive=False,
        terminal=True,
        permission_wait=False,
        resumable=False,
        last_seq=2,
        event_count=5,
        attach_count=9,
    )
    with pytest.raises(SpineError) as exc:
        validate_lifecycle_snapshot(hostile)
    assert exc.value.code == RUNTIME_INVALID_SESSION


# --------------------------------------------------------------------------- #
# D. close — adapter-local, default-off port handoff
# --------------------------------------------------------------------------- #
def test_close_is_adapter_local_and_preserves_backend_session() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    seq_before = reg.log.last_seq("task_alpha")

    snap = port.close(ref)
    assert type(snap) is LifecycleSnapshot
    assert snap.state == "running"
    # Local tracking dropped, but the backend session and log are untouched.
    assert port.session_count() == 0
    assert backend.session_count() == 1
    assert reg.log.last_seq("task_alpha") == seq_before
    assert "cancelled" not in _event_types(reg, "task_alpha")


def test_close_then_reconstructed_port_reattaches_live_session() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    port.close(ref)
    seq_after_close = reg.log.last_seq("task_alpha")

    reopened = AgentRunSupervisorPort(reg, backend)
    ref2 = reopened.create_or_attach("task_alpha", _spec())
    assert ref2 == ref
    assert reopened.session_count() == 1
    assert backend.session_count() == 1
    assert reg.log.last_seq("task_alpha") == seq_after_close  # no respawn events
    assert _attach_count(reg, "task_alpha") == 1


def test_close_requires_tracked_session_and_is_not_resurrectable() -> None:
    reg = TaskRegistry()
    port = AgentRunSupervisorPort(reg, DefaultAgentRunSupervisorBackend())
    ref = port.create_or_attach("task_alpha", _spec())
    port.close(ref)
    # A second close (now untracked) fails closed — close never resurrects.
    with pytest.raises(SpineError) as exc:
        port.close(ref)
    assert exc.value.code == RUNTIME_INVALID_SESSION
    # signal cannot resurrect a closed (untracked) session either.
    with pytest.raises(SpineError) as exc2:
        port.signal("task_alpha", "ref_decision_allow")
    assert exc2.value.code == RUNTIME_INVALID_SESSION


def test_close_is_default_off_never_called_by_normal_lifecycle() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    backend.fake_enter_permission_wait("task_alpha")
    port.status(ref)
    port.stream(ref)
    port.signal("task_alpha", "ref_decision_allow")
    port.kill(ref)
    # A full drive never auto-invokes close: the session stays locally tracked.
    assert port.session_count() == 1
    assert type(port.lifecycle_snapshot(ref)) is LifecycleSnapshot


# --------------------------------------------------------------------------- #
# E. Status / liveness backend-failure policy (Codex WATCH, made explicit)
# --------------------------------------------------------------------------- #
def test_status_backend_failure_collapses_to_stable_code_and_preserves_session() -> None:
    reg = TaskRegistry()
    backend = _FlakyStatusBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    seq_before = reg.log.last_seq("task_alpha")

    backend.fail = True
    with pytest.raises(SpineError) as exc:
        port.status(ref)
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE
    for leak in ("chat_id", "oc_secret", "/tmp/", "boom", "stderr"):
        assert leak not in str(exc.value)
    # The existing session/log is neither marked, killed, nor mutated.
    assert reg.log.last_seq("task_alpha") == seq_before
    assert port.session_count() == 1

    backend.fail = False
    recovered = port.status(ref)  # the preserved session resumes cleanly
    assert recovered.state == "running"
    assert recovered.alive is True


def test_liveness_backend_failure_does_not_mark_or_kill_session() -> None:
    reg = TaskRegistry()
    backend = _FlakyStatusBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    seq_before = reg.log.last_seq("task_alpha")

    backend.fail = True
    with pytest.raises(SpineError) as exc:
        port.liveness(ref)
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE
    assert reg.log.last_seq("task_alpha") == seq_before
    assert "cancelled" not in _event_types(reg, "task_alpha")

    backend.fail = False
    assert port.liveness(ref).alive is True


def test_orphaned_state_is_reapable_but_not_auto_marked_in_log() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    seq_before = reg.log.last_seq("task_alpha")
    backend.fake_orphan("task_alpha")

    live = port.liveness(ref)
    assert live.state == "orphaned"
    assert live.reapable is True
    assert live.alive is False
    # The orphan is a liveness-health signal for a reaper; it is NOT auto-written
    # as a terminal event into the canonical log (deliberate projection decision).
    status = port.status(ref)
    assert status.state == "orphaned"
    assert status.terminal is False
    assert reg.log.last_seq("task_alpha") == seq_before


# --------------------------------------------------------------------------- #
# F. Lease / task binding — no role or workspace drift on re-attach
# --------------------------------------------------------------------------- #
def test_reconstructed_port_rejects_workspace_ref_drift_no_attach() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    first = AgentRunSupervisorPort(reg, backend)
    first.create_or_attach("task_alpha", _spec(refs=("ws_alpha", "policy_default")))
    seq_before = reg.log.last_seq("task_alpha")

    second = AgentRunSupervisorPort(reg, backend)
    with pytest.raises(SpineError) as exc:
        second.create_or_attach("task_alpha", _spec(refs=("ws_other", "policy_other")))
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC
    assert second.session_count() == 0
    assert backend.session_count() == 1  # existing session untouched
    assert reg.log.last_seq("task_alpha") == seq_before


def test_reconstructed_port_rejects_role_drift_no_attach() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    first = AgentRunSupervisorPort(reg, backend)
    first.create_or_attach("task_alpha", _spec())
    seq_before = reg.log.last_seq("task_alpha")

    second = AgentRunSupervisorPort(reg, backend)
    with pytest.raises(SpineError) as exc:
        second.create_or_attach("task_alpha", _spec(roles=("read_only", "observer")))
    assert exc.value.code == RUNTIME_SUPERVISOR_POLICY_DENIED
    assert second.session_count() == 0
    assert backend.session_count() == 1
    assert reg.log.last_seq("task_alpha") == seq_before


def test_reattach_preserves_workspace_policy_binding() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    first = AgentRunSupervisorPort(reg, backend)
    first.create_or_attach("task_alpha", _spec(refs=("ws_alpha", "policy_default")))

    second = AgentRunSupervisorPort(reg, backend)
    ref = second.create_or_attach("task_alpha", _spec(refs=("policy_default", "ws_alpha")))
    # Re-attach preserves the original binding: a drifted durable flag is rejected.
    conflicting = _spec(refs=("ws_alpha", "policy_default"), needs_durable=True)
    with pytest.raises(SpineError) as exc:
        second.create_or_attach("task_alpha", conflicting)
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC
    assert second.status(ref).state == "running"
    # The original workspace/policy refs still project through the re-attached port.
    stream_refs = {r for chunk in second.stream(ref) for r in chunk["refs"]}
    assert {"ws_alpha", "policy_default"} <= stream_refs


# --------------------------------------------------------------------------- #
# G. No-leak / clean source additions
# --------------------------------------------------------------------------- #
def test_persistent_lifecycle_drive_leaks_no_raw_material() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec(refs=("ws_alpha", "policy_default", "ref_plan")))
    backend.fake_enter_permission_wait("task_alpha")
    port.signal("task_alpha", "ref_decision_allow")
    snap = port.lifecycle_snapshot(ref)
    port.close(ref)
    assert scan_for_leak(snap.to_projection()) is None
    for e in reg.log.events_for("task_alpha"):
        assert scan_for_leak(event_projection(e)) is None


def test_adapter_is_still_execution_port() -> None:
    port = AgentRunSupervisorPort(TaskRegistry(), DefaultAgentRunSupervisorBackend())
    assert isinstance(port, ExecutionPort)


_FORBIDDEN_CODE_TOKENS = (
    "subprocess.",
    "import subprocess",
    "import socket",
    ".Popen(",
    "os.system(",
    "create_subprocess",
    "import temporalio",
    "acpx",
    " npx",
    "asyncio.create",
)


def test_pr3_source_wires_no_real_runtime() -> None:
    source = Path(adapter_mod.__file__).read_text(encoding="utf-8")
    for token in _FORBIDDEN_CODE_TOKENS:
        assert token not in source, f"forbidden wiring token {token!r} in adapter"
    import_lines = [ln for ln in source.splitlines() if re.match(r"^\s*(import|from)\s", ln)]
    for line in import_lines:
        for root in ("subprocess", "socket", "temporal", "gateway", "feishu", "lark", "httpx", "requests", "urllib", "docker", "asyncio"):
            assert root not in line, f"forbidden import {root!r}: {line!r}"
