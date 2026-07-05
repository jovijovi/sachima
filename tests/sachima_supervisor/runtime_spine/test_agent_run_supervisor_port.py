"""PR1 — Sachima ``AgentRunSupervisorPort`` adapter over an injected backend.

RED/GREEN tests for the Sachima-side :class:`AgentRunSupervisorPort`, an
``ExecutionPort`` implementation that wraps an *injected* agent-run-supervisor
caller/runtime surface (``AgentRunSupervisorBackend``). The default injected
backend is a deterministic in-memory fake: it launches no real agent runtime, no
OS process, no subprocess, socket, Temporal Worker/service, Gateway, or Feishu
surface, and makes no network call.

The adapter proves, refs-only and fail-closed:

* the same ``task_id`` yields at most one live session (duplicate ``create_or_attach``
  attaches, it never spawns a second backend session or a second event);
* ``permission_wait`` is a live state, never a stall;
* ``signal`` requires an existing ``permission_wait`` session and never creates one;
* ``kill`` is terminal and idempotent;
* ``stream`` returns only the R1 refs-only registry projections (``scan_for_leak``
  must pass);
* a backend exception / unsafe backend material collapses to a stable code with no
  raw echo and no half-written session/event;
* an unknown / non-``read_only`` role and missing workspace/policy refs fail closed
  before any backend call.

Forbidden terms below are no-leak canaries only, never behavior.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import sachima_supervisor.runtime_spine.agent_run_supervisor_port as adapter_mod
from sachima_supervisor.runtime_spine import (
    RUNTIME_EVENT_LEAK_DETECTED,
    RUNTIME_INVALID_EVENT,
    RUNTIME_INVALID_LAUNCH_SPEC,
    RUNTIME_INVALID_TASK_ID,
    RUNTIME_INVALID_TASK_RECORD,
    STABLE_CODES,
    ExecutionPort,
    LaunchSpec,
    LivenessState,
    SessionRef,
    SessionStatus,
    SpineError,
    TaskRegistry,
    build_event_body,
    build_launch_spec,
    event_projection,
    project,
    scan_for_leak,
    serialize_projection,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    RUNTIME_SUPERVISOR_BACKEND_FAILURE,
    RUNTIME_SUPERVISOR_POLICY_DENIED,
    SUPERVISOR_PORT_STABLE_CODES,
    AgentRunSupervisorBackend,
    AgentRunSupervisorPort,
    DefaultAgentRunSupervisorBackend,
)
from sachima_supervisor.runtime_spine.execution_port import RUNTIME_INVALID_SESSION

_ALL_FAIL_CODES = (
    set(STABLE_CODES) | {RUNTIME_INVALID_SESSION} | set(SUPERVISOR_PORT_STABLE_CODES)
)

_SAFE_REFS = ("ws_alpha", "policy_default")
_SECRET_PREFIX = "sk" + "-"
_SECRET_SHAPED = _SECRET_PREFIX + "deadbeef"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _spec(
    task_id: str = "task_alpha",
    *,
    roles: tuple[str, ...] = ("read_only",),
    refs: tuple[str, ...] = _SAFE_REFS,
    needs_agent: bool = True,
    agent_kind: str = "local_agent",
) -> LaunchSpec:
    """A read_only, workspace+policy-scoped, live-agent LaunchSpec."""

    return build_launch_spec(
        task_id=task_id,
        agent_kind=agent_kind,
        mode_flags={"needs_agent": needs_agent},
        roles=roles,
        refs=refs,
    )


def _new_port() -> tuple[AgentRunSupervisorPort, TaskRegistry, DefaultAgentRunSupervisorBackend]:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    return AgentRunSupervisorPort(reg, backend), reg, backend


def _event_types(reg: TaskRegistry, task_id: str) -> list[str]:
    return [e.event_type for e in reg.log.events_for(task_id)]


# --------------------------------------------------------------------------- #
# failure-injecting backends (all implement the backend protocol surface)
# --------------------------------------------------------------------------- #
class _RaisingCreateBackend:
    def create_or_attach(self, task_id, refs):
        raise RuntimeError("boom raw_prompt /tmp/secret " + _SECRET_SHAPED + " agent_stdout")

    def attach_existing(self, task_id):
        raise RuntimeError("boom raw_prompt /tmp/secret " + _SECRET_SHAPED + " agent_stdout")

    def status(self, handle):
        return "active"

    def signal(self, handle, decision_ref):
        return "active"

    def kill(self, handle, reason_ref):
        return "killed"

    def liveness(self, handle):
        return "active"


class _UnknownStateBackend(DefaultAgentRunSupervisorBackend):
    def status(self, handle):  # unmapped backend token on the create read
        return "who_knows_raw_prompt"

class _CompletedOnAttachBackend(DefaultAgentRunSupervisorBackend):
    def status(self, handle):
        return "completed"

class _AmbiguousOnAttachBackend(DefaultAgentRunSupervisorBackend):
    def status(self, handle):
        return "ambiguous"

class _CompletedThenRunningBackend(DefaultAgentRunSupervisorBackend):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def status(self, handle):
        self.calls += 1
        return "completed" if self.calls == 1 else "running"

    def liveness(self, handle):
        return "running"


class _SignalCompletesBackend(DefaultAgentRunSupervisorBackend):
    def signal(self, handle, decision_ref):
        _ = decision_ref
        session = self._get(handle)
        session.state = "completed"
        return session.state


class _KillRaceCompletedBackend(DefaultAgentRunSupervisorBackend):
    def kill(self, handle, reason_ref):
        _ = reason_ref
        session = self._get(handle)
        session.state = "completed"
        return session.state


class _RaisingLivenessBackend(DefaultAgentRunSupervisorBackend):
    def liveness(self, handle):
        raise RuntimeError("kaboom stderr dump chat_id oc_secret")

class _RaisingSpineBackend(DefaultAgentRunSupervisorBackend):
    def create_or_attach(self, task_id, refs):
        raise SpineError(RUNTIME_EVENT_LEAK_DETECTED, "raw_prompt /tmp/secret " + _SECRET_SHAPED)

class _FalseyBackend(DefaultAgentRunSupervisorBackend):
    def __init__(self) -> None:
        super().__init__()
        self.called = False

    def __bool__(self) -> bool:
        return False

    def create_or_attach(self, task_id, refs):
        self.called = True
        return super().create_or_attach(task_id, refs)

class _IncompleteBackend:
    def create_or_attach(self, task_id, refs):
        return "arsjob_1"

    # deliberately missing status/signal/kill/liveness


# --------------------------------------------------------------------------- #
# A. Construction — a genuine ExecutionPort over a genuine registry + backend
# --------------------------------------------------------------------------- #
def test_adapter_is_an_execution_port() -> None:
    port, _, _ = _new_port()
    assert isinstance(port, ExecutionPort)


def test_adapter_defaults_to_injected_fake_backend() -> None:
    reg = TaskRegistry()
    port = AgentRunSupervisorPort(reg)  # no backend → deterministic default fake
    ref = port.create_or_attach("task_alpha", _spec())
    assert type(ref) is SessionRef
    assert ref.session_id.startswith("sess_")


def test_adapter_rejects_hostile_registry() -> None:
    class _HostileRegistry(TaskRegistry):
        pass

    for bad in (None, object(), {}, _HostileRegistry()):
        with pytest.raises(SpineError) as exc:
            AgentRunSupervisorPort(bad)  # type: ignore[arg-type]
        assert exc.value.code in _ALL_FAIL_CODES


def test_adapter_rejects_backend_missing_surface() -> None:
    reg = TaskRegistry()
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorPort(reg, _IncompleteBackend())  # type: ignore[arg-type]
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE


def test_default_backend_satisfies_protocol() -> None:
    assert isinstance(DefaultAgentRunSupervisorBackend(), AgentRunSupervisorBackend)


def test_adapter_preserves_explicit_falsey_backend() -> None:
    reg = TaskRegistry()
    backend = _FalseyBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    assert ref.task_id == "task_alpha"
    assert backend.called is True
    assert backend.session_count() == 1


# --------------------------------------------------------------------------- #
# B. create_or_attach — ≤1 live session per task_id; duplicate attaches
# --------------------------------------------------------------------------- #
def test_create_or_attach_returns_session_ref_and_runs() -> None:
    port, reg, backend = _new_port()
    ref = port.create_or_attach("task_alpha", _spec())
    assert type(ref) is SessionRef
    assert ref.task_id == "task_alpha"
    assert ref.session_id.startswith("sess_")
    assert reg.has_task("task_alpha") is True
    assert "agent_attached" in _event_types(reg, "task_alpha")
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["status"] == "running"
    assert backend.session_count() == 1


def test_duplicate_create_or_attach_returns_same_session_no_spawn() -> None:
    port, reg, backend = _new_port()
    ref1 = port.create_or_attach("task_alpha", _spec())
    seq_after_first = reg.log.last_seq("task_alpha")
    ref2 = port.create_or_attach("task_alpha", _spec())
    assert ref1 == ref2
    assert ref1.session_id == ref2.session_id
    assert port.session_count() == 1
    assert backend.session_count() == 1  # no second backend session spawned
    # No second attach event — the log is byte-for-byte unchanged.
    assert reg.log.last_seq("task_alpha") == seq_after_first
    assert _event_types(reg, "task_alpha").count("agent_attached") == 1


def test_duplicate_create_or_attach_normalizes_ref_order() -> None:
    port, reg, backend = _new_port()
    ref1 = port.create_or_attach("task_alpha", _spec(refs=("ws_alpha", "policy_default")))
    seq_after_first = reg.log.last_seq("task_alpha")
    ref2 = port.create_or_attach("task_alpha", _spec(refs=("policy_default", "ws_alpha")))
    assert ref2 == ref1
    assert port.session_count() == 1
    assert backend.session_count() == 1
    assert reg.log.last_seq("task_alpha") == seq_after_first


def test_create_or_attach_recovers_from_registry_create_race(monkeypatch) -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    original_create_task = reg.create_task

    def racing_create_task(task_id, *, needs_agent=False, needs_durable=False, refs=()):
        record = original_create_task(
            task_id,
            needs_agent=needs_agent,
            needs_durable=needs_durable,
            refs=refs,
        )
        reg.append_event(
            task_id,
            build_event_body(
                event_type="agent_attached",
                status="running",
                refs=("sess_race",),
            ),
        )
        raise SpineError(RUNTIME_INVALID_TASK_RECORD)

    monkeypatch.setattr(reg, "create_task", racing_create_task)
    ref = port.create_or_attach("task_alpha", _spec())
    assert ref == SessionRef(task_id="task_alpha", session_id="sess_race")
    assert port.session_count() == 1
    assert backend.session_count() == 1
    assert _event_types(reg, "task_alpha").count("agent_attached") == 1


def test_create_or_attach_single_session_under_repeated_calls() -> None:
    port, _, backend = _new_port()
    refs = {port.create_or_attach("task_alpha", _spec()) for _ in range(6)}
    assert len(refs) == 1
    assert port.session_count() == 1
    assert backend.session_count() == 1
    assert port.liveness("task_alpha").alive is True


def test_duplicate_create_or_attach_rejects_conflicting_launch_spec() -> None:
    port, reg, _ = _new_port()
    ref = port.create_or_attach("task_alpha", _spec(refs=("ws_alpha", "policy_default", "ref_plan")))
    seq_after_first = reg.log.last_seq("task_alpha")
    conflicting = build_launch_spec(
        task_id="task_alpha",
        agent_kind="local_agent",
        mode_flags={"needs_agent": True, "needs_durable": True},
        roles=("read_only",),
        refs=_SAFE_REFS,
    )
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", conflicting)
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC
    assert port.session_count() == 1
    assert port.status(ref).state == "running"
    assert reg.log.last_seq("task_alpha") == seq_after_first


def test_create_or_attach_existing_task_requires_same_workspace_policy_refs() -> None:
    port, reg, backend = _new_port()
    reg.create_task(
        "task_alpha",
        needs_agent=True,
        needs_durable=False,
        refs=("ws_alpha", "policy_default"),
    )
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _spec(refs=("ws_other", "policy_other")))
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC
    assert backend.session_count() == 0
    assert port.session_count() == 0
    assert "agent_attached" not in _event_types(reg, "task_alpha")


def test_create_or_attach_existing_task_allows_same_refs() -> None:
    port, reg, backend = _new_port()
    reg.create_task(
        "task_alpha",
        needs_agent=True,
        needs_durable=False,
        refs=("ws_alpha", "policy_default"),
    )
    ref = port.create_or_attach("task_alpha", _spec(refs=("policy_default", "ws_alpha")))
    assert ref.task_id == "task_alpha"
    assert backend.session_count() == 1
    assert "agent_attached" in _event_types(reg, "task_alpha")


def test_reconstructed_port_attaches_existing_registry_session_without_new_event() -> None:
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    first = AgentRunSupervisorPort(reg, backend)
    spec = _spec(refs=("ws_alpha", "policy_default"))
    ref1 = first.create_or_attach("task_alpha", spec)
    seq_after_first = reg.log.last_seq("task_alpha")

    second = AgentRunSupervisorPort(reg, backend)
    ref2 = second.create_or_attach("task_alpha", spec)
    assert ref2 == ref1
    assert second.session_count() == 1
    assert backend.session_count() == 1
    assert reg.log.last_seq("task_alpha") == seq_after_first
    assert _event_types(reg, "task_alpha").count("agent_attached") == 1


def test_reconstructed_port_with_fresh_backend_fails_closed_no_respawn() -> None:
    reg = TaskRegistry()
    first_backend = DefaultAgentRunSupervisorBackend()
    first = AgentRunSupervisorPort(reg, first_backend)
    spec = _spec(refs=("ws_alpha", "policy_default"))
    first.create_or_attach("task_alpha", spec)
    first_backend.fake_enter_permission_wait("task_alpha")
    first.status("task_alpha")
    seq_after_permission = reg.log.last_seq("task_alpha")
    snap_before = reg.snapshot("task_alpha")
    assert snap_before is not None
    assert snap_before["status"] == "permission_wait"

    fresh_backend = DefaultAgentRunSupervisorBackend()
    second = AgentRunSupervisorPort(reg, fresh_backend)
    with pytest.raises(SpineError) as exc:
        second.create_or_attach("task_alpha", spec)
    assert exc.value.code == RUNTIME_INVALID_SESSION
    assert second.session_count() == 0
    assert fresh_backend.session_count() == 0
    assert reg.log.last_seq("task_alpha") == seq_after_permission
    snap_after = reg.snapshot("task_alpha")
    assert snap_after is not None
    assert snap_after["status"] == "permission_wait"


def test_create_or_attach_rejects_pre_attach_terminal_task_no_respawn() -> None:
    port, reg, backend = _new_port()
    reg.create_task("task_alpha", needs_agent=True, needs_durable=False, refs=_SAFE_REFS)
    reg.append_event(
        "task_alpha",
        build_event_body(
            event_type="failed",
            status="failed",
            refs=("ref_preflight_denied",),
        ),
    )
    seq_before = reg.log.last_seq("task_alpha")
    snap_before = reg.snapshot("task_alpha")
    assert snap_before is not None
    assert snap_before["terminal"] is True

    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _spec())
    assert exc.value.code == RUNTIME_INVALID_SESSION
    assert port.session_count() == 0
    assert backend.session_count() == 0
    assert reg.log.last_seq("task_alpha") == seq_before
    snap_after = reg.snapshot("task_alpha")
    assert snap_after is not None
    assert snap_after["status"] == "failed"
    assert snap_after["terminal"] is True


def test_create_or_attach_rejects_mismatched_task_id_spec() -> None:
    port, _, _ = _new_port()
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _spec("task_beta"))
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


def test_create_or_attach_rejects_non_agent_spec() -> None:
    port, _, backend = _new_port()
    non_agent = _spec(needs_agent=False)  # needs_agent False never routes to the supervisor
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", non_agent)
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC
    assert port.session_count() == 0
    assert backend.session_count() == 0


def test_create_or_attach_rejects_durable_activity_kind() -> None:
    port, reg, backend = _new_port()
    durable_spec = _spec(agent_kind="durable_activity")
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", durable_spec)
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC
    _assert_no_side_effects(port, reg, backend)


def test_create_or_attach_rejects_wrong_launch_spec_type() -> None:
    port, _, _ = _new_port()
    for bad in (None, {}, "local_agent", object(), 42):
        with pytest.raises(SpineError) as exc:
            port.create_or_attach("task_alpha", bad)  # type: ignore[arg-type]
        assert exc.value.code in _ALL_FAIL_CODES


def test_create_or_attach_rejects_hostile_launch_spec_subclass() -> None:
    class _Hostile(LaunchSpec):
        def __post_init__(self) -> None:  # skip fail-closed validation
            return None

    hostile = _Hostile(
        task_id="task_alpha",
        agent_kind="local_agent",
        needs_agent=True,
        needs_durable=False,
        required_capabilities=(),
        roles=("read_only",),
        refs=_SAFE_REFS,
    )
    port, _, backend = _new_port()
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", hostile)
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC
    assert backend.session_count() == 0


# --------------------------------------------------------------------------- #
# C. role / workspace / policy fail-closed (read_only maximum, default-deny)
# --------------------------------------------------------------------------- #
def _assert_no_side_effects(port, reg, backend) -> None:
    assert port.session_count() == 0
    assert backend.session_count() == 0
    assert reg.has_task("task_alpha") is False


def test_create_or_attach_requires_read_only_role() -> None:
    port, reg, backend = _new_port()
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _spec(roles=()))
    assert exc.value.code == RUNTIME_SUPERVISOR_POLICY_DENIED
    _assert_no_side_effects(port, reg, backend)


def test_create_or_attach_rejects_non_read_only_role() -> None:
    port, reg, backend = _new_port()
    # 'observer' passes the R1 role-key sanitizer (no write marker) yet is NOT the
    # single permitted read_only role — default-deny.
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _spec(roles=("observer",)))
    assert exc.value.code == RUNTIME_SUPERVISOR_POLICY_DENIED
    _assert_no_side_effects(port, reg, backend)


def test_create_or_attach_rejects_extra_role_alongside_read_only() -> None:
    port, reg, backend = _new_port()
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _spec(roles=("read_only", "observer")))
    assert exc.value.code == RUNTIME_SUPERVISOR_POLICY_DENIED
    _assert_no_side_effects(port, reg, backend)


def test_create_or_attach_requires_workspace_ref() -> None:
    port, reg, backend = _new_port()
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _spec(refs=("policy_default",)))
    assert exc.value.code == RUNTIME_SUPERVISOR_POLICY_DENIED
    _assert_no_side_effects(port, reg, backend)


def test_create_or_attach_requires_policy_ref() -> None:
    port, reg, backend = _new_port()
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _spec(refs=("ws_alpha",)))
    assert exc.value.code == RUNTIME_SUPERVISOR_POLICY_DENIED
    _assert_no_side_effects(port, reg, backend)


# --------------------------------------------------------------------------- #
# D. stream — refs-only, deterministic replay of the R1 registry projection
# --------------------------------------------------------------------------- #
def test_stream_returns_refs_only_deterministic_events() -> None:
    port, reg, _ = _new_port()
    ref = port.create_or_attach("task_alpha", _spec())
    stream1 = port.stream(ref)
    stream2 = port.stream(ref)
    assert stream1 == stream2
    assert all(isinstance(chunk, dict) for chunk in stream1)
    log_view = tuple(event_projection(e) for e in reg.log.events_for("task_alpha"))
    assert tuple(stream1) == log_view
    assert scan_for_leak(list(stream1)) is None


def test_stream_accepts_task_id_and_rejects_forged_ref() -> None:
    port, _, _ = _new_port()
    ref = port.create_or_attach("task_alpha", _spec())
    assert port.stream("task_alpha") == port.stream(ref)
    forged = SessionRef(task_id="task_alpha", session_id="sess_999")
    with pytest.raises(SpineError) as exc:
        port.stream(forged)
    assert exc.value.code == RUNTIME_INVALID_SESSION
    with pytest.raises(SpineError):
        port.stream("task_missing")


# --------------------------------------------------------------------------- #
# E. liveness — permission_wait is ALIVE (mapped from the backend), not stalled
# --------------------------------------------------------------------------- #
def test_liveness_running_is_alive() -> None:
    port, _, _ = _new_port()
    port.create_or_attach("task_alpha", _spec())
    live = port.liveness("task_alpha")
    assert type(live) is LivenessState
    assert live.state == "running"
    assert live.alive is True
    assert live.permission_wait is False
    assert live.reapable is False


def test_liveness_permission_wait_is_alive_not_reapable() -> None:
    port, _, backend = _new_port()
    port.create_or_attach("task_alpha", _spec())
    backend.fake_enter_permission_wait("task_alpha")  # supervisor reports a pending permission
    live = port.liveness("task_alpha")
    assert live.state == "permission_wait"
    assert live.alive is True  # NOT stalled — an expected live state
    assert live.permission_wait is True
    assert live.reapable is False


def test_liveness_maps_orphaned_reapable() -> None:
    port, _, backend = _new_port()
    port.create_or_attach("task_alpha", _spec())
    backend.fake_orphan("task_alpha")  # supervisor lost the session
    live = port.liveness("task_alpha")
    assert live.state == "orphaned"
    assert live.alive is False
    assert live.reapable is True


def test_liveness_rejects_forged_ref() -> None:
    port, _, _ = _new_port()
    port.create_or_attach("task_alpha", _spec())
    with pytest.raises(SpineError) as exc:
        port.liveness(SessionRef(task_id="task_alpha", session_id="sess_forged"))
    assert exc.value.code == RUNTIME_INVALID_SESSION


# --------------------------------------------------------------------------- #
# F. signal — requires an existing permission_wait session; never creates one
# --------------------------------------------------------------------------- #
def test_signal_roundtrip_request_then_signal() -> None:
    port, reg, backend = _new_port()
    port.create_or_attach("task_alpha", _spec())
    backend.fake_enter_permission_wait("task_alpha")
    status = port.signal("task_alpha", "ref_decision_allow")
    assert type(status) is SessionStatus
    assert status.state == "running"
    assert "permission_answered" in _event_types(reg, "task_alpha")
    live = port.liveness("task_alpha")
    assert live.alive is True
    assert live.permission_wait is False


def test_signal_accepts_backend_terminal_completion() -> None:
    reg = TaskRegistry()
    backend = _SignalCompletesBackend()
    port = AgentRunSupervisorPort(reg, backend)
    port.create_or_attach("task_alpha", _spec())
    backend.fake_enter_permission_wait("task_alpha")
    status = port.signal("task_alpha", "ref_decision_allow")
    assert status.state == "completed"
    assert status.terminal is True
    assert "permission_answered" in _event_types(reg, "task_alpha")
    assert reg.log.events_for("task_alpha")[-1].event_type == "completed"
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["status"] == "completed"
    assert snap["terminal"] is True


def test_signal_rejects_terminal_projection_without_mutating_log() -> None:
    port, reg, backend = _new_port()
    port.create_or_attach("task_alpha", _spec())
    reg.append_event(
        "task_alpha",
        build_event_body(
            event_type="completed",
            status="completed",
            refs=("ref_already_done",),
        ),
    )
    backend.fake_enter_permission_wait("task_alpha")
    seq_before = reg.log.last_seq("task_alpha")
    with pytest.raises(SpineError) as exc:
        port.signal("task_alpha", "ref_decision_allow")
    assert exc.value.code == RUNTIME_INVALID_SESSION
    assert reg.log.last_seq("task_alpha") == seq_before
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["status"] == "completed"


def test_signal_on_unknown_task_never_creates_session() -> None:
    port, reg, backend = _new_port()
    with pytest.raises(SpineError) as exc:
        port.signal("task_missing", "ref_decision_allow")
    assert exc.value.code == RUNTIME_INVALID_SESSION
    # signal must never bring a session into being.
    assert port.session_count() == 0
    assert backend.session_count() == 0
    assert reg.has_task("task_missing") is False


def test_signal_without_pending_permission_fails_closed() -> None:
    port, reg, _ = _new_port()
    port.create_or_attach("task_alpha", _spec())
    seq_before = reg.log.last_seq("task_alpha")
    with pytest.raises(SpineError) as exc:
        port.signal("task_alpha", "ref_decision_allow")
    assert exc.value.code == RUNTIME_INVALID_SESSION
    assert reg.log.last_seq("task_alpha") == seq_before  # no answer event appended


def test_signal_rejects_leaky_decision_ref() -> None:
    port, reg, backend = _new_port()
    port.create_or_attach("task_alpha", _spec())
    backend.fake_enter_permission_wait("task_alpha")
    seq_before = reg.log.last_seq("task_alpha")
    for leaky in ("raw_prompt_here", "chat_id", "oc_secret", "Bad Ref"):
        with pytest.raises(SpineError) as exc:
            port.signal("task_alpha", leaky)
        assert exc.value.code in {
            RUNTIME_INVALID_EVENT,
            RUNTIME_EVENT_LEAK_DETECTED,
            RUNTIME_INVALID_SESSION,
        }
        assert "raw_prompt" not in str(exc.value)
    assert reg.log.last_seq("task_alpha") == seq_before


# --------------------------------------------------------------------------- #
# G. status — projection-derived + backend-mapped live state
# --------------------------------------------------------------------------- #
def test_status_reflects_projection() -> None:
    port, reg, _ = _new_port()
    ref = port.create_or_attach("task_alpha", _spec())
    status = port.status(ref)
    assert type(status) is SessionStatus
    assert status.state == "running"
    assert status.alive is True
    assert status.terminal is False
    proj = project(reg.log.events_for("task_alpha"), task_id="task_alpha")
    assert status.last_seq == proj["last_seq"]
    assert status.projected_status == proj["status"]
    assert port.status("task_alpha") == status


def test_status_maps_backend_permission_wait() -> None:
    port, reg, backend = _new_port()
    ref = port.create_or_attach("task_alpha", _spec())
    backend.fake_enter_permission_wait("task_alpha")
    status = port.status(ref)
    assert status.state == "permission_wait"
    assert status.alive is True
    assert status.terminal is False
    assert status.projected_status == "permission_wait"
    assert "permission_requested" in _event_types(reg, "task_alpha")
    permission_snap = reg.snapshot("task_alpha")
    assert permission_snap is not None
    assert permission_snap["status"] == "permission_wait"


def test_stream_syncs_backend_terminal_state_into_projection() -> None:
    reg = TaskRegistry()
    backend = _CompletedOnAttachBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    stream = port.stream(ref)
    assert stream[-1]["event_type"] == "completed"
    assert stream[-1]["status"] == "completed"
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["status"] == "completed"
    assert snap["terminal"] is True
    status = port.status(ref)
    assert status.state == "completed"
    assert status.projected_status == "completed"


def test_ambiguous_backend_state_projects_terminal_failed_event() -> None:
    reg = TaskRegistry()
    backend = _AmbiguousOnAttachBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    status = port.status(ref)
    assert status.state == "failed"
    assert status.terminal is True
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["status"] == "failed"
    assert snap["terminal"] is True
    assert reg.log.events_for("task_alpha")[-1].event_type == "failed"


def test_status_honors_terminal_projection_over_backend_running() -> None:
    reg = TaskRegistry()
    backend = _CompletedThenRunningBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    status = port.status(ref)
    assert status.state == "completed"
    assert status.projected_status == "completed"
    assert status.alive is False
    assert status.terminal is True
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["status"] == "completed"
    assert snap["terminal"] is True


def test_liveness_honors_terminal_projection_over_backend_running() -> None:
    reg = TaskRegistry()
    backend = _CompletedThenRunningBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    live = port.liveness(ref)
    assert live.state == "completed"
    assert live.alive is False
    assert live.permission_wait is False
    assert live.reapable is False


def test_status_rejects_forged_ref_and_unknown_task() -> None:
    port, _, _ = _new_port()
    port.create_or_attach("task_alpha", _spec())
    with pytest.raises(SpineError) as exc:
        port.status(SessionRef(task_id="task_alpha", session_id="sess_bogus"))
    assert exc.value.code == RUNTIME_INVALID_SESSION
    with pytest.raises(SpineError):
        port.status("task_missing")


# --------------------------------------------------------------------------- #
# H. kill — terminal, refs-only, idempotent
# --------------------------------------------------------------------------- #
def test_kill_appends_refs_only_terminal_event() -> None:
    port, reg, _ = _new_port()
    ref = port.create_or_attach("task_alpha", _spec())
    status = port.kill(ref, reason_ref="ref_operator_kill")
    assert status.terminal is True
    assert status.alive is False
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["status"] == "cancelled"
    assert snap["terminal"] is True
    for e in reg.log.events_for("task_alpha"):
        assert scan_for_leak(event_projection(e)) is None
    live = port.liveness("task_alpha")
    assert live.alive is False
    assert live.reapable is False


def test_kill_accepts_backend_terminal_race_completion() -> None:
    reg = TaskRegistry()
    backend = _KillRaceCompletedBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    status = port.kill(ref, reason_ref="ref_operator_kill")
    assert status.state == "completed"
    assert status.terminal is True
    assert "cancelled" not in _event_types(reg, "task_alpha")
    assert reg.log.events_for("task_alpha")[-1].event_type == "completed"
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["status"] == "completed"


def test_kill_preserves_terminal_projection_without_backend_mutation() -> None:
    port, reg, backend = _new_port()
    ref = port.create_or_attach("task_alpha", _spec())
    reg.append_event(
        "task_alpha",
        build_event_body(
            event_type="completed",
            status="completed",
            refs=("ref_already_done",),
        ),
    )
    seq_before = reg.log.last_seq("task_alpha")
    status = port.kill(ref, reason_ref="ref_operator_kill")
    assert status.state == "completed"
    assert status.terminal is True
    assert reg.log.last_seq("task_alpha") == seq_before
    assert "cancelled" not in _event_types(reg, "task_alpha")
    assert backend.status(backend.attach_existing("task_alpha")) == "running"


def test_kill_is_idempotent() -> None:
    port, reg, _ = _new_port()
    ref = port.create_or_attach("task_alpha", _spec())
    port.kill(ref)
    seq_after_kill = reg.log.last_seq("task_alpha")
    status2 = port.kill(ref)
    assert status2.terminal is True
    assert reg.log.last_seq("task_alpha") == seq_after_kill


def test_kill_rejects_forged_ref_and_leaky_reason() -> None:
    port, _, _ = _new_port()
    ref = port.create_or_attach("task_alpha", _spec())
    with pytest.raises(SpineError) as exc:
        port.kill(SessionRef(task_id="task_alpha", session_id="sess_forged"))
    assert exc.value.code == RUNTIME_INVALID_SESSION
    with pytest.raises(SpineError) as exc2:
        port.kill(ref, reason_ref="agent_stdout_dump")
    assert exc2.value.code in {RUNTIME_INVALID_EVENT, RUNTIME_EVENT_LEAK_DETECTED}
    assert "agent_stdout" not in str(exc2.value)


def test_create_or_attach_after_kill_never_respawns() -> None:
    port, reg, backend = _new_port()
    ref = port.create_or_attach("task_alpha", _spec())
    port.kill(ref)
    seq_after_kill = reg.log.last_seq("task_alpha")
    ref2 = port.create_or_attach("task_alpha", _spec())
    assert ref2 == ref
    assert port.session_count() == 1
    assert backend.session_count() == 1
    assert reg.log.last_seq("task_alpha") == seq_after_kill  # no respawn events


# --------------------------------------------------------------------------- #
# I. Backend failure / unsafe material — stable code only, no leak, no partial
# --------------------------------------------------------------------------- #
def test_backend_failure_on_create_collapses_to_stable_code_no_leak() -> None:
    reg = TaskRegistry()
    backend = _RaisingCreateBackend()
    port = AgentRunSupervisorPort(reg, backend)  # type: ignore[arg-type]
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _spec())
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE
    text = str(exc.value)
    for leak in ("raw_prompt", "/tmp/", _SECRET_PREFIX, "agent_stdout", "boom"):
        assert leak not in text
    # No half-written session/event.
    assert port.session_count() == 0
    assert reg.has_task("task_alpha") is False


def test_backend_spine_error_collapses_to_stable_code_no_leak() -> None:
    reg = TaskRegistry()
    backend = _RaisingSpineBackend()
    port = AgentRunSupervisorPort(reg, backend)
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _spec())
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE
    for leak in ("raw_prompt", "/tmp/", _SECRET_SHAPED):
        assert leak not in str(exc.value)
    assert port.session_count() == 0
    assert reg.has_task("task_alpha") is False


def test_unknown_backend_state_collapses_to_stable_code() -> None:
    reg = TaskRegistry()
    backend = _UnknownStateBackend()
    port = AgentRunSupervisorPort(reg, backend)
    with pytest.raises(SpineError) as exc:
        port.create_or_attach("task_alpha", _spec())
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE
    assert "raw_prompt" not in str(exc.value)
    assert port.session_count() == 0
    assert reg.has_task("task_alpha") is False
    handle = backend.attach_existing("task_alpha")
    assert backend.liveness(handle) == "cancelled"


def test_backend_failure_on_liveness_collapses_to_stable_code_no_leak() -> None:
    reg = TaskRegistry()
    backend = _RaisingLivenessBackend()
    port = AgentRunSupervisorPort(reg, backend)
    port.create_or_attach("task_alpha", _spec())
    with pytest.raises(SpineError) as exc:
        port.liveness("task_alpha")
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE
    for leak in ("chat_id", "oc_secret", "stderr", "kaboom"):
        assert leak not in str(exc.value)


def test_supervisor_stable_codes_are_port_side_only() -> None:
    # Port-side stable codes are raised as SpineError; they are NOT R1 event codes
    # and must never be storable as an event error_code.
    assert RUNTIME_SUPERVISOR_BACKEND_FAILURE in SUPERVISOR_PORT_STABLE_CODES
    assert RUNTIME_SUPERVISOR_POLICY_DENIED in SUPERVISOR_PORT_STABLE_CODES
    assert SUPERVISOR_PORT_STABLE_CODES.isdisjoint(STABLE_CODES)


# --------------------------------------------------------------------------- #
# J. Determinism + no-leak across a driven scenario
# --------------------------------------------------------------------------- #
def _drive(port: AgentRunSupervisorPort, backend: DefaultAgentRunSupervisorBackend) -> None:
    port.create_or_attach("task_alpha", _spec(refs=("ws_alpha", "policy_default", "ref_plan")))
    backend.fake_enter_permission_wait("task_alpha")
    port.signal("task_alpha", "ref_decision_allow")
    port.kill("task_alpha", reason_ref="ref_done")


def test_no_event_body_leaks_raw_material() -> None:
    port, reg, backend = _new_port()
    _drive(port, backend)
    for e in reg.log.events_for("task_alpha"):
        assert scan_for_leak(event_projection(e)) is None


def test_projection_is_byte_stable_and_port_independent() -> None:
    port_a, reg_a, backend_a = _new_port()
    port_b, reg_b, backend_b = _new_port()
    _drive(port_a, backend_a)
    _drive(port_b, backend_b)
    proj_a = project(reg_a.log.events_for("task_alpha"), task_id="task_alpha")
    proj_b = project(reg_b.log.events_for("task_alpha"), task_id="task_alpha")
    assert serialize_projection(proj_a) == serialize_projection(proj_b)


# --------------------------------------------------------------------------- #
# K. Structural guard — the adapter wires NO real runtime / process / network
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


def test_source_wires_no_real_runtime() -> None:
    source = Path(adapter_mod.__file__).read_text(encoding="utf-8")
    for token in _FORBIDDEN_CODE_TOKENS:
        assert token not in source, f"forbidden wiring token {token!r} in adapter"
    import_lines = [ln for ln in source.splitlines() if re.match(r"^\s*(import|from)\s", ln)]
    denied_roots = (
        "subprocess",
        "socket",
        "temporal",
        "gateway",
        "feishu",
        "lark",
        "httpx",
        "requests",
        "urllib",
        "aiohttp",
        "docker",
        "multiprocessing",
        "asyncio",
    )
    for line in import_lines:
        for root in denied_roots:
            assert root not in line, f"forbidden import {root!r}: {line!r}"
