"""ARS-INT — refs-only goal/prompt turn dispatcher over the library backend.

Tests for :class:`AgentRunSupervisorTurnDispatcher`: the product seam that
turns a refs-only request into one supervised library turn, auto-binds the
produced turn artifact dir into ``LiveProgressSourceBindings`` (cursor reset
per turn), appends refs-only events to the canonical log, and never leaks the
private payload text or artifact path anywhere. Everything runs pure
local/offline over the real port + real library backend driven by an injected
facade double — no ARS import, no acpx, no AGENT, no subprocess, no Gateway,
Feishu, or Temporal surface. Forbidden terms in this prose are no-leak
boundary canaries only, never behavior.
"""

from __future__ import annotations

import dataclasses
import json
import re
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sachima_supervisor.runtime_spine import (
    LiveProgressSourceBindings,
    SpineError,
    TaskRegistry,
    build_launch_spec,
    scan_for_leak,
    serialize_live_progress_source,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend import (
    AgentRunSupervisorLibraryBackend,
    AgentRunSupervisorLibraryConfig,
    ARS_LIBRARY_CONFIG_TYPE,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    AgentRunSupervisorPort,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher import (
    RUNTIME_ARS_TURN_FAILED,
    RUNTIME_INVALID_TURN_DISPATCH,
    RUNTIME_TURN_DISPATCH_BUSY,
    TURN_DISPATCH_STABLE_CODES,
    AgentRunSupervisorTurnDispatcher,
    TurnDispatchOutcome,
    TurnDispatchRequest,
    validate_turn_dispatch_outcome,
    validate_turn_dispatch_request,
)

# --------------------------------------------------------------------------- #
# Offline composition: real port + real backend + fake library facade
# --------------------------------------------------------------------------- #


def _view(**kwargs: Any) -> SimpleNamespace:
    view = SimpleNamespace(
        exists=True,
        state="open",
        lease_held=False,
        holder_liveness=None,
        lease_recoverable=False,
        latest_turn_status=None,
        progress=None,
    )
    for key, value in kwargs.items():
        setattr(view, key, value)
    return view


class _FakeFacade:
    def __init__(self) -> None:
        self.records: dict[str, SimpleNamespace] = {}
        self.views: dict[str, SimpleNamespace] = {}
        self.sent: list[tuple[str, str]] = []
        self.compiled: list[str] = []
        self.aborts: list[str] = []
        self.closes: list[str] = []
        self.send_error: BaseException | None = None
        self.send_gate: threading.Event | None = None
        self.send_started: threading.Event = threading.Event()
        self.turn_seq = 0
        self.turn_status = "completed"

    def load_role(self, mapping):
        return SimpleNamespace(role_id=mapping.get("role_id", "role"))

    def role_hash(self, role) -> str:
        return f"hash_{role.role_id}"

    def validate_workspace(self, role, work_dir: str):
        return SimpleNamespace(effective_cwd=work_dir)

    def open_record(self, sessions_dir, ars_session_id):
        return self.records.get(ars_session_id)

    def binding_matches(self, sessions_dir, record, role, workspace) -> bool:
        return True

    def create_session(self, sessions_dir, role, ars_session_id, session_name, work_dir):
        self.records[ars_session_id] = SimpleNamespace(
            state="open", role_hash=self.role_hash(role)
        )
        self.views.setdefault(ars_session_id, _view())

    def send(self, sessions_dir, role, ars_session_id, prompt, work_dir):
        self.send_started.set()
        if self.send_gate is not None:
            self.send_gate.wait(timeout=10)
        if self.send_error is not None:
            raise self.send_error
        self.sent.append((ars_session_id, prompt))
        self.turn_seq += 1
        turn_id = f"turn_20260709T10000{self.turn_seq}Z_ab12cd3{self.turn_seq}"
        return (turn_id, f"/srv/private/turns/{turn_id}", self.turn_status)

    def abort(self, sessions_dir, role, ars_session_id, work_dir) -> bool:
        self.aborts.append(ars_session_id)
        return True

    def close(self, sessions_dir, role, ars_session_id, work_dir) -> None:
        self.closes.append(ars_session_id)
        record = self.records.get(ars_session_id)
        if record is not None:
            record.state = "closed"

    def compile_goal(self, role, goal_text: str) -> str:
        self.compiled.append(goal_text)
        return f"[goal-contract/v1] Standing goal:\n\n{goal_text}\n\nGOAL_STATUS: ..."

    def inspect(self, sessions_dir, ars_session_id):
        return self.views.get(ars_session_id)


_REFS = ("ws_arsint", "policy_read_only")


def _role_mapping() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "role_id": "readonly-reviewer",
        "runner": {"type": "acpx", "acpx_version": "0.12.0", "acpx_binary": None},
        "permissions": {"read": True, "search": True},
        "session": {"strategy": "persistent"},
    }


@pytest.fixture()
def rig(tmp_path: Path):
    binary = tmp_path / "bin" / "acpx"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    config = AgentRunSupervisorLibraryConfig(
        type=ARS_LIBRARY_CONFIG_TYPE,
        enabled=True,
        approval_ref="approval_arsint_s2",
        sessions_dir=str(tmp_path / "sessions"),
        workspace_by_ref={"ws_arsint": str(work)},
        role_by_ref={"policy_read_only": _role_mapping()},
        session_prefix="sachima",
        acpx_binary=str(binary),
        stale_after_seconds=900,
    )
    facade = _FakeFacade()
    backend = AgentRunSupervisorLibraryBackend(config, facade=facade)
    registry = TaskRegistry()
    port = AgentRunSupervisorPort(registry, backend)
    bindings = LiveProgressSourceBindings()
    payloads: dict[str, str] = {"payload_goal_1": "ship the integration"}
    resolver_calls: list[str] = []

    def resolver(payload_ref: str) -> str:
        resolver_calls.append(payload_ref)
        return payloads[payload_ref]

    dispatcher = AgentRunSupervisorTurnDispatcher(
        port, backend, bindings, registry, resolver
    )
    ref = port.create_or_attach(
        "task_alpha",
        build_launch_spec(
            task_id="task_alpha",
            agent_kind="local_agent",
            mode_flags={"needs_agent": True},
            roles=("read_only",),
            refs=_REFS,
        ),
    )
    return SimpleNamespace(
        config=config,
        facade=facade,
        backend=backend,
        registry=registry,
        port=port,
        bindings=bindings,
        payloads=payloads,
        resolver_calls=resolver_calls,
        dispatcher=dispatcher,
        ref=ref,
    )


def _request(rig, *, turn_kind: str = "goal", payload_ref: str = "payload_goal_1"):
    return TurnDispatchRequest(
        task_id="task_alpha",
        session_id=rig.ref.session_id,
        turn_kind=turn_kind,
        payload_ref=payload_ref,
    )


# --------------------------------------------------------------------------- #
# A. Request / outcome value objects — refs-only, fail-closed
# --------------------------------------------------------------------------- #


def test_stable_code_family_is_closed() -> None:
    assert TURN_DISPATCH_STABLE_CODES == frozenset(
        {
            RUNTIME_INVALID_TURN_DISPATCH,
            RUNTIME_TURN_DISPATCH_BUSY,
            RUNTIME_ARS_TURN_FAILED,
        }
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(task_id="Task Alpha"),
        dict(task_id=""),
        dict(session_id="session_1"),
        dict(session_id="sess-1"),
        dict(turn_kind="chat"),
        dict(turn_kind=""),
        dict(payload_ref="/srv/private/goal.txt"),
        dict(payload_ref=""),
    ],
)
def test_request_field_validation_fails_closed(kwargs) -> None:
    base = dict(
        task_id="task_alpha",
        session_id="sess_1",
        turn_kind="goal",
        payload_ref="payload_goal_1",
    )
    base.update(kwargs)
    with pytest.raises(SpineError) as exc:
        TurnDispatchRequest(**base)
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH


def test_forged_request_fails_closed() -> None:
    forged = object.__new__(TurnDispatchRequest)
    object.__setattr__(forged, "task_id", "task_alpha")
    object.__setattr__(forged, "session_id", "sess_1")
    object.__setattr__(forged, "turn_kind", "goal")
    object.__setattr__(forged, "payload_ref", "raw text payload not a ref " * 8)
    with pytest.raises(SpineError) as exc:
        validate_turn_dispatch_request(forged)
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH


def test_hostile_request_subclass_fails_closed(rig) -> None:
    class Hostile(TurnDispatchRequest):
        def __post_init__(self) -> None:
            pass

    hostile = Hostile(
        task_id="task_alpha",
        session_id=rig.ref.session_id,
        turn_kind="goal",
        payload_ref="payload_goal_1",
    )
    with pytest.raises(SpineError) as exc:
        rig.dispatcher.dispatch(hostile)
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH


def test_outcome_invariants_fail_closed() -> None:
    # success shape must carry turn/artifact refs and no error code
    with pytest.raises(SpineError):
        TurnDispatchOutcome(
            task_id="task_alpha",
            session_id="sess_1",
            turn_ref=None,
            supervisor_status="completed",
            artifact_ref=None,
            error_code=None,
        )
    # failure shape must not carry refs or a status
    with pytest.raises(SpineError):
        TurnDispatchOutcome(
            task_id="task_alpha",
            session_id="sess_1",
            turn_ref="turn_1_ab12cd34",
            supervisor_status=None,
            artifact_ref="turn_1_ab12cd34",
            error_code=RUNTIME_ARS_TURN_FAILED,
        )
    # off-vocabulary supervisor status is refused
    with pytest.raises(SpineError):
        TurnDispatchOutcome(
            task_id="task_alpha",
            session_id="sess_1",
            turn_ref="turn_1_ab12cd34",
            supervisor_status="did_great",
            artifact_ref="turn_1_ab12cd34",
            error_code=None,
        )


def test_forged_outcome_fails_closed() -> None:
    forged = object.__new__(TurnDispatchOutcome)
    for name, value in (
        ("task_id", "task_alpha"),
        ("session_id", "sess_1"),
        ("turn_ref", "/srv/private/turn"),
        ("supervisor_status", "completed"),
        ("artifact_ref", "turn_1_ab12cd34"),
        ("error_code", None),
    ):
        object.__setattr__(forged, name, value)
    with pytest.raises(SpineError) as exc:
        validate_turn_dispatch_outcome(forged)
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH


# --------------------------------------------------------------------------- #
# B. Dispatch — goal compilation, auto-binding, cursor reset, refs-only events
# --------------------------------------------------------------------------- #


def test_goal_dispatch_compiles_contract_binds_artifact_and_reports(rig) -> None:
    outcome = rig.dispatcher.dispatch(_request(rig))

    assert validate_turn_dispatch_outcome(outcome) is outcome
    assert outcome.task_id == "task_alpha"
    assert outcome.session_id == rig.ref.session_id
    assert outcome.supervisor_status == "completed"
    assert outcome.error_code is None
    assert re.fullmatch(r"turn_1_[0-9a-f]{8}", outcome.turn_ref)
    assert outcome.artifact_ref == outcome.turn_ref

    # goal text went through the role-aware compiler, never a literal /goal
    assert rig.facade.compiled == ["ship the integration"]
    ((_, sent_prompt),) = rig.facade.sent
    assert not sent_prompt.startswith("/goal")

    # the produced private turn dir is bound for the live-progress chain
    resolved = rig.bindings.resolve("task_alpha", rig.ref.session_id)
    assert resolved.artifact_dir.endswith(rig.facade.sent and "1" or "")
    assert resolved.source.artifact_ref == outcome.turn_ref
    assert resolved.source.last_seen_cursor is None


def test_prompt_dispatch_sends_payload_verbatim(rig) -> None:
    rig.payloads["payload_prompt_1"] = "please summarize the diff"
    outcome = rig.dispatcher.dispatch(
        _request(rig, turn_kind="prompt", payload_ref="payload_prompt_1")
    )
    assert outcome.supervisor_status == "completed"
    ((_, sent_prompt),) = rig.facade.sent
    assert sent_prompt == "please summarize the diff"
    assert rig.facade.compiled == []


def test_each_dispatch_rebinds_new_artifact_and_resets_cursor(rig) -> None:
    first = rig.dispatcher.dispatch(_request(rig))
    rig.bindings.update_last_seen_cursor("task_alpha", 41, rig.ref.session_id)
    assert (
        rig.bindings.resolve_source("task_alpha", rig.ref.session_id).last_seen_cursor
        == 41
    )

    second = rig.dispatcher.dispatch(_request(rig))
    assert second.turn_ref != first.turn_ref
    assert re.fullmatch(r"turn_2_[0-9a-f]{8}", second.turn_ref)
    source = rig.bindings.resolve_source("task_alpha", rig.ref.session_id)
    assert source.artifact_ref == second.turn_ref
    assert source.last_seen_cursor is None
    resolved = rig.bindings.resolve("task_alpha", rig.ref.session_id)
    assert resolved.artifact_dir.endswith("2")


def test_dispatch_appends_refs_only_progress_and_milestone_events(rig) -> None:
    before = rig.registry.log.last_seq("task_alpha")
    outcome = rig.dispatcher.dispatch(_request(rig))
    events = rig.registry.log.events_for("task_alpha")[before:]
    kinds = [event.event_type for event in events]
    assert "progress" in kinds
    assert "milestone" in kinds
    milestone = next(e for e in events if e.event_type == "milestone")
    assert outcome.turn_ref in milestone.refs
    assert rig.ref.session_id in milestone.refs
    for event in events:
        assert scan_for_leak(
            {"refs": list(event.refs), "type": event.event_type, "status": event.status}
        ) is None


def test_completed_turn_keeps_open_session_running(rig) -> None:
    rig.dispatcher.dispatch(_request(rig))
    status = rig.port.status(rig.ref)
    assert status.state == "running"
    assert status.alive is True


def test_no_op_turn_maps_failed_through_port(rig) -> None:
    rig.facade.turn_status = "no_op"
    outcome = rig.dispatcher.dispatch(_request(rig))
    assert outcome.supervisor_status == "no_op"
    assert outcome.error_code is None
    status = rig.port.status(rig.ref)
    assert status.state == "failed"
    failed_events = [
        e for e in rig.registry.log.events_for("task_alpha") if e.event_type == "failed"
    ]
    assert len(failed_events) == 1


# --------------------------------------------------------------------------- #
# C. Fail-closed preconditions and failure hygiene
# --------------------------------------------------------------------------- #


def test_dispatch_unknown_task_fails_closed(rig) -> None:
    request = TurnDispatchRequest(
        task_id="task_ghost",
        session_id="sess_1",
        turn_kind="goal",
        payload_ref="payload_goal_1",
    )
    with pytest.raises(SpineError) as exc:
        rig.dispatcher.dispatch(request)
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH


def test_dispatch_mismatched_session_id_fails_closed(rig) -> None:
    request = TurnDispatchRequest(
        task_id="task_alpha",
        session_id="sess_999",
        turn_kind="goal",
        payload_ref="payload_goal_1",
    )
    with pytest.raises(SpineError) as exc:
        rig.dispatcher.dispatch(request)
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH


def test_dispatch_on_terminal_task_fails_closed(rig) -> None:
    rig.port.kill(rig.ref, "ref_cancelled")
    with pytest.raises(SpineError) as exc:
        rig.dispatcher.dispatch(_request(rig))
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH
    assert rig.facade.sent == []


def test_unresolvable_payload_fails_closed_without_echo(rig) -> None:
    request = _request(rig, payload_ref="payload_missing")
    with pytest.raises(SpineError) as exc:
        rig.dispatcher.dispatch(request)
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH
    assert "payload_missing" not in str(exc.value) or str(exc.value) == exc.value.code
    assert rig.facade.sent == []


def test_turn_crash_returns_error_outcome_and_leaves_no_half_binding(rig) -> None:
    first = rig.dispatcher.dispatch(_request(rig))
    prior = rig.bindings.resolve("task_alpha", rig.ref.session_id)

    rig.facade.send_error = RuntimeError("acpx blew up with /srv/private detail")
    outcome = rig.dispatcher.dispatch(_request(rig))
    assert outcome.error_code == RUNTIME_ARS_TURN_FAILED
    assert outcome.supervisor_status is None
    assert outcome.turn_ref is None
    assert outcome.artifact_ref is None

    # the previous good binding is untouched — no half-bound state
    after = rig.bindings.resolve("task_alpha", rig.ref.session_id)
    assert after.source.artifact_ref == prior.source.artifact_ref == first.turn_ref
    assert after.artifact_dir == prior.artifact_dir
    assert "/srv/private" not in repr(outcome)


def test_single_flight_rejects_concurrent_dispatch_for_same_task(rig) -> None:
    rig.facade.send_gate = threading.Event()
    results: list[Any] = []

    def _first() -> None:
        results.append(rig.dispatcher.dispatch(_request(rig)))

    worker = threading.Thread(target=_first)
    worker.start()
    assert rig.facade.send_started.wait(timeout=5)
    assert rig.dispatcher.in_flight("task_alpha") is True
    with pytest.raises(SpineError) as exc:
        rig.dispatcher.dispatch(_request(rig))
    assert exc.value.code == RUNTIME_TURN_DISPATCH_BUSY

    rig.facade.send_gate.set()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert rig.dispatcher.in_flight("task_alpha") is False
    (outcome,) = results
    assert outcome.supervisor_status == "completed"
    # the slot is free again
    second = rig.dispatcher.dispatch(_request(rig))
    assert second.supervisor_status == "completed"


def test_in_flight_clears_after_turn_crash(rig) -> None:
    rig.facade.send_error = RuntimeError("boom")
    rig.dispatcher.dispatch(_request(rig))
    assert rig.dispatcher.in_flight("task_alpha") is False


# --------------------------------------------------------------------------- #
# D. No-leak: payload text and private dirs never escape
# --------------------------------------------------------------------------- #


def test_payload_and_private_dir_never_leak_into_any_surface(rig) -> None:
    canary = "payload-canary-51ee-never-echo"
    rig.payloads["payload_canary"] = canary
    outcome = rig.dispatcher.dispatch(_request(rig, payload_ref="payload_canary"))

    surfaces = [repr(outcome), repr(rig.dispatcher)]
    events = rig.registry.log.events_for("task_alpha")
    surfaces.extend(json.dumps(_event_dict(event)) for event in events)
    source = rig.bindings.resolve_source("task_alpha", rig.ref.session_id)
    surfaces.append(serialize_live_progress_source(source).decode("utf-8"))
    combined = "\n".join(surfaces)
    assert canary not in combined
    assert "/srv/private" not in combined
    assert scan_for_leak(json.loads(serialize_live_progress_source(source))) is None
    assert rig.resolver_calls.count("payload_canary") == 1


def _event_dict(event) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "status": event.status,
        "refs": list(event.refs),
        "digests": list(event.digests),
    }


def test_dispatcher_module_has_no_ars_import_or_spawn_surface() -> None:
    import sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*(import|from)\s+agent_run_supervisor", src) is None
    for token in ("subprocess.", "os.system(", ".popen(", "socket.socket("):
        assert token not in src.lower(), token
