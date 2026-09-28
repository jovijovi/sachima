"""R3 — Temporal attach-only durable bridge contract (local/offline).

RED/GREEN tests for the Private Hermes Runtime Spine R3 gate. The future
``temporal_bridge`` module must model Temporal as a durable orchestrator over an
existing supervisor session. It must never create/spawn/relaunch an AGENT,
start a Worker/service/test server, or touch Gateway/Feishu/live/delivery.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path
from typing import Any

import pytest

from sachima_supervisor.runtime_spine import (
    LivenessState,
    RUNTIME_INVALID_SESSION,
    SessionRef,
    SessionStatus,
    SpineError,
    TaskRegistry,
    scan_for_leak,
)
from sachima_supervisor.runtime_spine.execution_port import ExecutionPort


_LEAK_CANARIES = (
    "raw_prompt",
    "raw_context",
    "tool_output",
    "agent_stdout",
    "raw_exception",
    "card_json",
    "chat_id",
    "oc_",
    "ou_",
    "/tmp/",
    "sk" + "-",
    "bearer ",
)


def _bridge_mod():
    return importlib.import_module("sachima_supervisor.runtime_spine.temporal_bridge")


def _session_ref() -> SessionRef:
    return SessionRef(task_id="task_alpha", session_id="sess_1")


class _SpyExecutionPort(ExecutionPort):
    """Read-only spy: status/liveness are allowed; create is forbidden."""

    def __init__(
        self, ref: SessionRef | None = None, *, alive: bool = True, raise_liveness: bool = False
    ) -> None:
        self.ref = ref or _session_ref()
        self.alive = alive
        self.raise_liveness = raise_liveness
        self.create_or_attach_calls = 0
        self.stream_calls = 0
        self.signal_calls = 0
        self.status_calls = 0
        self.kill_calls = 0
        self.liveness_calls = 0
        self.seen_refs: list[SessionRef] = []

    def create_or_attach(self, task_id: str, launch_spec: Any) -> SessionRef:
        self.create_or_attach_calls += 1
        raise AssertionError("R3 bridge must never create_or_attach")

    def stream(self, ref: str | SessionRef):
        self.stream_calls += 1
        return ()

    def signal(self, task_id: str, decision_ref: str) -> SessionStatus:
        self.signal_calls += 1
        raise AssertionError("R3 bridge must not signal supervisor")

    def status(self, ref: str | SessionRef) -> SessionStatus:
        self.status_calls += 1
        assert ref == self.ref
        self.seen_refs.append(self.ref)
        return SessionStatus(
            task_id=self.ref.task_id,
            session_id=self.ref.session_id,
            state="running" if self.alive else "failed",
            alive=self.alive,
            terminal=not self.alive,
            last_seq=0,
            projected_status="running" if self.alive else "failed",
        )

    def kill(self, ref: str | SessionRef, reason_ref: str = "ref_cancelled") -> SessionStatus:
        self.kill_calls += 1
        raise AssertionError("R3 bridge must not kill supervisor sessions")

    def liveness(self, ref: str | SessionRef) -> LivenessState:
        self.liveness_calls += 1
        assert ref == self.ref
        self.seen_refs.append(self.ref)
        if self.raise_liveness:
            raise SpineError(RUNTIME_INVALID_SESSION)
        return LivenessState(
            task_id=self.ref.task_id,
            session_id=self.ref.session_id,
            state="running" if self.alive else "failed",
            alive=self.alive,
            permission_wait=False,
            reapable=False,
        )


# --------------------------------------------------------------------------- #
# A. Public surface and stable error family
# --------------------------------------------------------------------------- #
def test_temporal_bridge_public_surface_is_exported() -> None:
    mod = _bridge_mod()
    assert mod.RUNTIME_INVALID_TEMPORAL_BRIDGE == "runtime_invalid_temporal_bridge"
    assert mod.RUNTIME_INVALID_TEMPORAL_BRIDGE in mod.BRIDGE_STABLE_CODES
    for name in (
        "HeartbeatPayload",
        "AgentRunActivityInput",
        "AgentRunActivityResult",
        "TemporalWorkflowContract",
        "TemporalAttachOnlyBridge",
        "validate_heartbeat_payload",
        "validate_agent_run_activity_input",
        "validate_workflow_contract",
    ):
        assert hasattr(mod, name)


def test_temporal_bridge_symbols_are_available_from_runtime_spine_package() -> None:
    runtime_spine = importlib.import_module("sachima_supervisor.runtime_spine")
    for name in (
        "RUNTIME_INVALID_TEMPORAL_BRIDGE",
        "HeartbeatPayload",
        "AgentRunActivityInput",
        "TemporalWorkflowContract",
        "TemporalAttachOnlyBridge",
    ):
        assert hasattr(runtime_spine, name)


# --------------------------------------------------------------------------- #
# B. Heartbeat payload — refs-only, exact shape, stable validation
# --------------------------------------------------------------------------- #
def test_heartbeat_payload_accepts_only_refs_phase_counters_cursor() -> None:
    mod = _bridge_mod()
    payload = mod.validate_heartbeat_payload(
        {
            "cursor_ref": "cursor_ref_1",
            "phase": "running",
            "counters": {"events_seen": 2, "heartbeat_count": 1},
            "refs": ("claim_ref_input_1", "evidence_ref_stream_1"),
        }
    )
    assert type(payload) is mod.HeartbeatPayload
    assert payload.cursor_ref == "cursor_ref_1"
    assert payload.phase == "running"
    assert payload.counters == {"events_seen": 2, "heartbeat_count": 1}
    assert payload.refs == ("claim_ref_input_1", "evidence_ref_stream_1")
    assert scan_for_leak(dataclasses.asdict(payload)) is None


@pytest.mark.parametrize("canary", _LEAK_CANARIES)
def test_heartbeat_payload_rejects_raw_material_in_values(canary: str) -> None:
    mod = _bridge_mod()
    with pytest.raises(SpineError) as exc:
        mod.validate_heartbeat_payload(
            {
                "cursor_ref": "cursor_ref_1",
                "phase": "running",
                "counters": {"events_seen": 1},
                "refs": (f"claim_ref_{canary}_x",),
            }
        )
    assert exc.value.code == mod.RUNTIME_INVALID_TEMPORAL_BRIDGE
    assert str(exc.value) == mod.RUNTIME_INVALID_TEMPORAL_BRIDGE


def test_heartbeat_payload_rejects_extra_missing_or_wrong_typed_fields() -> None:
    mod = _bridge_mod()
    valid = {
        "cursor_ref": "cursor_ref_1",
        "phase": "running",
        "counters": {"events_seen": 1},
        "refs": ("claim_ref_1",),
    }

    class _HostileMapping(dict):
        pass

    class _HostileCounters(dict):
        pass

    bad_payloads = (
        {**valid, "tool_output": "claim_ref_1"},
        {k: v for k, v in valid.items() if k != "cursor_ref"},
        {**valid, "phase": "launching_worker"},
        {**valid, "counters": {"events_seen": True}},
        {**valid, "counters": _HostileCounters({"events_seen": 1})},
        {**valid, "refs": ["claim_ref_1"]},
        _HostileMapping(valid),
        object(),
    )
    for bad in bad_payloads:
        with pytest.raises(SpineError) as exc:
            mod.validate_heartbeat_payload(bad)
        assert exc.value.code == mod.RUNTIME_INVALID_TEMPORAL_BRIDGE


# --------------------------------------------------------------------------- #
# C. AgentRunActivity input — attach-existing only, no launch/create fields
# --------------------------------------------------------------------------- #
def test_agent_run_activity_input_is_attach_existing_only() -> None:
    mod = _bridge_mod()
    payload = mod.HeartbeatPayload(
        cursor_ref="cursor_ref_1",
        phase="running",
        counters={"events_seen": 1},
        refs=("claim_ref_1",),
    )
    activity_input = mod.AgentRunActivityInput(
        task_id="task_alpha",
        session_ref=_session_ref(),
        heartbeat=payload,
    )
    assert mod.validate_agent_run_activity_input(activity_input) is activity_input
    assert {field.name for field in dataclasses.fields(activity_input)} == {
        "task_id",
        "session_ref",
        "heartbeat",
    }
    forbidden = {"launch_spec", "create", "spawn", "relaunch", "command", "task_queue"}
    assert forbidden.isdisjoint({field.name for field in dataclasses.fields(activity_input)})


def test_agent_run_activity_input_rejects_forged_or_raw_session_material() -> None:
    mod = _bridge_mod()
    payload = mod.HeartbeatPayload(
        cursor_ref="cursor_ref_1",
        phase="running",
        counters={"events_seen": 1},
        refs=("claim_ref_1",),
    )
    with pytest.raises(SpineError) as exc:
        mod.AgentRunActivityInput(
            task_id="task_alpha",
            session_ref="sess_raw_prompt_leak",
            heartbeat=payload,
        )
    assert exc.value.code == mod.RUNTIME_INVALID_TEMPORAL_BRIDGE


def test_heartbeat_payload_counters_are_immutable_after_validation() -> None:
    mod = _bridge_mod()
    payload = mod.HeartbeatPayload(
        cursor_ref="cursor_ref_1",
        phase="running",
        counters={"events_seen": 1},
        refs=("claim_ref_1",),
    )

    with pytest.raises(TypeError):
        payload.counters["raw_prompt"] = 1


def test_agent_run_activity_result_revalidates_heartbeat_payload() -> None:
    mod = _bridge_mod()
    payload = mod.HeartbeatPayload(
        cursor_ref="cursor_ref_1",
        phase="running",
        counters={"events_seen": 1},
        refs=("claim_ref_1",),
    )
    object.__setattr__(payload, "counters", {"events_seen": 1, "raw_prompt": 1})

    with pytest.raises(SpineError) as exc:
        mod.AgentRunActivityResult(
            task_id="task_alpha",
            session_id="sess_1",
            status="running",
            alive=True,
            heartbeat=payload,
            appended_event_seq=1,
        )
    assert exc.value.code == mod.RUNTIME_INVALID_TEMPORAL_BRIDGE


def test_agent_run_activity_result_freezes_revalidated_heartbeat_payload() -> None:
    mod = _bridge_mod()
    payload = mod.HeartbeatPayload(
        cursor_ref="cursor_ref_1",
        phase="running",
        counters={"events_seen": 1},
        refs=("claim_ref_1",),
    )
    object.__setattr__(payload, "counters", {"events_seen": 1})

    result = mod.AgentRunActivityResult(
        task_id="task_alpha",
        session_id="sess_1",
        status="running",
        alive=True,
        heartbeat=payload,
        appended_event_seq=1,
    )

    with pytest.raises(TypeError):
        result.heartbeat.counters["raw_prompt"] = 1
    assert scan_for_leak(dataclasses.asdict(result)) is None


def test_validate_heartbeat_payload_freezes_revalidated_payload() -> None:
    mod = _bridge_mod()
    payload = mod.HeartbeatPayload(
        cursor_ref="cursor_ref_1",
        phase="running",
        counters={"events_seen": 1},
        refs=("claim_ref_1",),
    )
    object.__setattr__(payload, "counters", {"events_seen": 1})

    assert mod.validate_heartbeat_payload(payload) is payload
    with pytest.raises(TypeError):
        payload.counters["raw_prompt"] = 1
    assert scan_for_leak(dataclasses.asdict(payload)) is None


def test_agent_run_activity_input_freezes_revalidated_heartbeat_payload() -> None:
    mod = _bridge_mod()
    payload = mod.HeartbeatPayload(
        cursor_ref="cursor_ref_1",
        phase="running",
        counters={"events_seen": 1},
        refs=("claim_ref_1",),
    )
    object.__setattr__(payload, "counters", {"events_seen": 1})

    activity_input = mod.AgentRunActivityInput(
        task_id="task_alpha",
        session_ref=_session_ref(),
        heartbeat=payload,
    )

    with pytest.raises(TypeError):
        activity_input.heartbeat.counters["raw_prompt"] = 1
    assert scan_for_leak(dataclasses.asdict(activity_input.heartbeat)) is None


# --------------------------------------------------------------------------- #
# D. Workflow contract — orchestrator, not producer
# --------------------------------------------------------------------------- #
def test_workflow_contract_is_orchestrator_not_producer() -> None:
    mod = _bridge_mod()
    contract = mod.validate_workflow_contract(mod.TemporalWorkflowContract())
    assert contract.role == "orchestrator"
    assert contract.allowed_activity == "agent_run_attach_existing"
    assert contract.attach_only is True
    assert contract.creates_session is False
    assert contract.owns_process is False
    assert contract.starts_worker is False
    assert contract.appends_events is False
    assert contract.side_effects == ()


# --------------------------------------------------------------------------- #
# E. Bridge activity — attach to existing session, append refs-only event, no spawn
# --------------------------------------------------------------------------- #
def test_bridge_run_agent_activity_attaches_existing_and_appends_refs_only_event() -> None:
    mod = _bridge_mod()
    registry = TaskRegistry()
    registry.create_task("task_alpha", needs_agent=True, needs_durable=True, refs=("claim_ref_plan",))
    spy = _SpyExecutionPort()
    bridge = mod.TemporalAttachOnlyBridge(registry=registry, execution_port=spy)
    activity_input = mod.AgentRunActivityInput(
        task_id="task_alpha",
        session_ref=spy.ref,
        heartbeat=mod.HeartbeatPayload(
            cursor_ref="cursor_ref_1",
            phase="running",
            counters={"events_seen": 1, "heartbeat_count": 1},
            refs=("claim_ref_input_1", "evidence_ref_stream_1"),
        ),
    )

    result = bridge.run_agent_activity(activity_input)

    assert type(result) is mod.AgentRunActivityResult
    assert result.task_id == "task_alpha"
    assert result.session_id == "sess_1"
    assert result.status == "running"
    assert result.alive is True
    assert result.side_effects == ()
    assert result.heartbeat == activity_input.heartbeat
    assert result.appended_event_seq == registry.log.last_seq("task_alpha")
    assert spy.create_or_attach_calls == 0
    assert spy.kill_calls == 0
    assert spy.signal_calls == 0
    assert spy.liveness_calls == 1
    assert spy.status_calls == 1
    events = registry.log.events_for("task_alpha")
    assert [event.event_type for event in events] == ["task_created", "progress"]
    progress = events[-1]
    assert progress.refs == ("sess_1", "cursor_ref_1", "claim_ref_input_1", "evidence_ref_stream_1")
    # TaskEvent normalizes counts to a sorted tuple of (name, value) pairs (R1
    # canonical event shape); compare its dict view to the heartbeat counters.
    assert dict(progress.counts) == {"events_seen": 1, "heartbeat_count": 1}
    assert scan_for_leak([event.__dict__ for event in events]) is None


def test_bridge_retry_replay_never_creates_or_relaunches_session() -> None:
    mod = _bridge_mod()
    registry = TaskRegistry()
    registry.create_task("task_alpha", needs_agent=True, needs_durable=True)
    spy = _SpyExecutionPort()
    bridge = mod.TemporalAttachOnlyBridge(registry=registry, execution_port=spy)
    activity_input = mod.AgentRunActivityInput(
        task_id="task_alpha",
        session_ref=spy.ref,
        heartbeat=mod.HeartbeatPayload(
            cursor_ref="cursor_ref_1",
            phase="running",
            counters={"events_seen": 1},
            refs=("claim_ref_input_1",),
        ),
    )

    first = bridge.run_agent_activity(activity_input)
    second = bridge.run_agent_activity(activity_input)

    assert first.session_id == second.session_id == "sess_1"
    assert spy.create_or_attach_calls == 0
    assert spy.seen_refs == [spy.ref, spy.ref, spy.ref, spy.ref]
    assert [event.event_type for event in registry.log.events_for("task_alpha")].count("progress") == 2


def test_bridge_missing_or_dead_session_fails_closed_without_create() -> None:
    mod = _bridge_mod()
    for spy in (_SpyExecutionPort(alive=False), _SpyExecutionPort(raise_liveness=True)):
        registry = TaskRegistry()
        registry.create_task("task_alpha", needs_agent=True, needs_durable=True)
        bridge = mod.TemporalAttachOnlyBridge(registry=registry, execution_port=spy)
        activity_input = mod.AgentRunActivityInput(
            task_id="task_alpha",
            session_ref=spy.ref,
            heartbeat=mod.HeartbeatPayload(
                cursor_ref="cursor_ref_1",
                phase="running",
                counters={"events_seen": 1},
                refs=("claim_ref_input_1",),
            ),
        )

        with pytest.raises(SpineError) as exc:
            bridge.run_agent_activity(activity_input)

        assert exc.value.code == mod.RUNTIME_INVALID_TEMPORAL_BRIDGE
        assert spy.create_or_attach_calls == 0
        assert registry.log.last_seq("task_alpha") == 1
        assert [event.event_type for event in registry.log.events_for("task_alpha")] == ["task_created"]


def test_bridge_rejects_non_durable_or_non_agent_task_without_create() -> None:
    mod = _bridge_mod()
    registry = TaskRegistry()
    registry.create_task("task_alpha", needs_agent=True, needs_durable=False)
    spy = _SpyExecutionPort()
    bridge = mod.TemporalAttachOnlyBridge(registry=registry, execution_port=spy)
    activity_input = mod.AgentRunActivityInput(
        task_id="task_alpha",
        session_ref=spy.ref,
        heartbeat=mod.HeartbeatPayload(
            cursor_ref="cursor_ref_1",
            phase="running",
            counters={"events_seen": 1},
            refs=("claim_ref_input_1",),
        ),
    )

    with pytest.raises(SpineError) as exc:
        bridge.run_agent_activity(activity_input)

    assert exc.value.code == mod.RUNTIME_INVALID_TEMPORAL_BRIDGE
    assert spy.create_or_attach_calls == 0
    assert registry.log.last_seq("task_alpha") == 1


# --------------------------------------------------------------------------- #
# F. Static source tripwire — no hidden runtime/lifecycle/live surfaces
# --------------------------------------------------------------------------- #
def test_temporal_bridge_source_has_no_forbidden_runtime_surface() -> None:
    path = Path("sachima_supervisor/runtime_spine/temporal_bridge.py")
    if not path.exists():
        pytest.skip("temporal_bridge.py not implemented yet; RED import tests cover absence")
    text = path.read_text(encoding="utf-8")
    forbidden = (
        "temporalio",
        "WorkflowEnvironment",
        "Worker(",
        "task_queue",
        "subprocess",
        "socket",
        "acpx",
        "npx",
        "gateway",
        "feishu",
        "send(",
    )
    hits = [token for token in forbidden if token in text]
    assert hits == []
