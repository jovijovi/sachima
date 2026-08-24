"""Refs-only goal/prompt turn dispatcher over the ``arsd`` backend.

Tests for :class:`AgentRunSupervisorTurnDispatcher`: the product seam that
turns a refs-only request into one supervised turn, auto-binds the produced
private read-model locator into ``LiveProgressSourceBindings`` (cursor reset
per turn), appends refs-only events to the canonical log, and never leaks the
private payload text or raw ``run_id`` anywhere.

The retired ``library`` backend used to be this file's rig (plan P5, seam S-1).
The ``arsd`` Socket API v3 adapter is the only turn backend the factory
allowlist admits now, so it is the rig: everything runs pure local/offline over
the real port + real backend + real durable ledger driven by an injected facade
double — no ``agent_run_supervisor`` import, no socket, no daemon, no AGENT, no
subprocess, no Gateway, Feishu, or Temporal surface. Forbidden terms in this
prose are no-leak boundary canaries only, never behavior.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import re
import importlib
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
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
from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
    prompt_resolver_from_payload_resolver,
)
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import ArsdRunBindingLedger
from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    ARSD_SUPERVISOR_CONFIG_TYPE,
    ArsdSupervisorConfig,
)
from sachima_supervisor.runtime_spine.arsd_supervisor_backend import (
    ArsdSupervisorBackend,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    AgentRunSupervisorPort,
)
from sachima_supervisor.runtime_spine.supervisor_turn_backend import (
    SUPERVISOR_TURN_STATUSES,
    TaskOperationLocks,
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
# Offline composition: real port + real arsd backend + injected facade double
# --------------------------------------------------------------------------- #
_REFS = ("ws_arsint", "policy_agent", "policy_model", "policy_effort", "policy_limits")
_SOCKET_CANARY = "/srv/private/sachima-arsd.sock"
_RUN_ID_CANARY = "RUN-dispatcher-canary-3f9a"
_ARS_SESSION_CANARY = "SESSDISPATCHERCANARY3f9a"
_ACCEPTED_AT = "2026-08-17T04:05:06+00:00"

#: The canonical roster the fake daemon reports, in the daemon's own
#: ``tuple(sorted(entries))`` order.
REGISTERED_AGENT_IDS = ("claude", "codex", "cursor", "oh-my-pi", "opencode")

V3_OPERATIONS = [
    "agent_list",
    "run_cancel",
    "run_events",
    "run_status",
    "server_info",
    "session_list",
    "session_status",
    "submit",
]


class _TransportLoss(Exception):
    """A local transport failure the official client would raise, doubled."""


class _FacadeDouble:
    """The only daemon surface in this file: an in-memory, recording double."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.submitted: list[tuple[str, dict[str, Any]]] = []
        self.submit_error: BaseException | None = None
        #: Held open to keep one dispatch inside the admission sequence but
        #: BEFORE its pending intent lands, which is the only window in which
        #: the dispatcher's own single-flight guard is the thing that answers.
        self.server_info_gate: threading.Event | None = None
        self.server_info_started: threading.Event = threading.Event()
        #: What ``run_status`` reports about the recorded Run. ``None`` is
        #: "accepted, no terminal yet" — which the §7.4 active-Run exclusion
        #: reads as still running.
        self.run_status_payload: dict[str, Any] | None = None
        self.run_cancel_payload: dict[str, Any] | None = None
        self.admitted: dict[str, dict[str, Any]] = {}
        #: The instant the daemon says it accepted. Two Runs sharing one
        #: instant are irreconcilable by design (no lexical tiebreak), so a
        #: fixture with two turns moves it.
        self.accepted_at = _ACCEPTED_AT
        #: Parks the winner *inside* its submit — the one window where its
        #: pending intent is already on disk and its ack is not yet read.
        self.submit_gate: threading.Event | None = None
        self.submit_started: threading.Event = threading.Event()
        self._run_seq = 0

    def _log(self, op: str) -> None:
        self.calls.append(op)

    def ops(self, op: str) -> int:
        return self.calls.count(op)

    def run_ended(self, status: str = "completed") -> None:
        """Trusted terminal truth, so the next turn may be admitted."""

        self.run_status_payload = {"result": {"status": status}}

    def server_info(self) -> dict[str, Any]:
        self._log("server_info")
        self.server_info_started.set()
        if self.server_info_gate is not None:
            self.server_info_gate.wait(timeout=10)
        return {
            "version": "0.7.8",
            "api_version": 3,
            "supported_api_versions": [3],
            "operations": list(V3_OPERATIONS),
            "limits": {
                "max_concurrent_runs": 4,
                "max_frame_bytes": 1_048_576,
                "max_prompt_bytes": 262_144,
                "events_page_limit": 256,
                "event_follow_queue_size": 1024,
                "max_run_event_budget_bytes": 2_147_483_648,
            },
        }

    def submit(self, *, request_id: str, payload: Any) -> dict[str, Any]:
        self._log("submit")
        self.submitted.append((request_id, json.loads(json.dumps(dict(payload)))))
        self.submit_started.set()
        if self.submit_gate is not None:
            self.submit_gate.wait(timeout=10)
        # The daemon records the admission BEFORE it answers: a raise after
        # this point is a genuinely lost ack, not a refused submission.
        if request_id not in self.admitted:
            self._run_seq += 1
            self.admitted[request_id] = {
                "run_id": f"{_RUN_ID_CANARY}-{self._run_seq}",
                "session_id": _ARS_SESSION_CANARY,
                "accepted_at": self.accepted_at,
            }
        if self.submit_error is not None:
            raise self.submit_error
        return dict(self.admitted[request_id])

    def run_status(self, run_id: str) -> dict[str, Any]:
        self._log("run_status")
        payload = dict(self.run_status_payload or {})
        payload["run_id"] = run_id
        payload.setdefault("session_id", _ARS_SESSION_CANARY)
        return payload

    def run_events(
        self, run_id: str, *, from_seq: int, limit: int | None = None
    ) -> dict[str, Any]:
        self._log("run_events")
        return {
            "run_id": run_id,
            "events": [],
            "next_from_seq": from_seq,
            "exhausted": True,
        }

    def run_cancel(self, run_id: str) -> dict[str, Any]:
        self._log("run_cancel")
        payload = dict(self.run_cancel_payload or {})
        payload["run_id"] = run_id
        return payload

    def session_status(self, session_id: str) -> dict[str, Any]:
        self._log("session_status")
        return {
            "session_id": session_id,
            "owner": "sachima_host",
            "namespace": "sachima_tasks",
            "agent_id": "reader-agent",
            "profile_id": None,
            "created_at": _ACCEPTED_AT,
            "updated_at": _ACCEPTED_AT,
            "last_effective_model": None,
            "last_effective_effort": None,
            "quarantine": None,
        }

    def session_list(self) -> dict[str, Any]:
        self._log("session_list")
        return {"sessions": []}

    def agent_list(self) -> dict[str, Any]:
        self._log("agent_list")
        return {"agent_ids": list(REGISTERED_AGENT_IDS)}


def _config(tmp_path: Path) -> ArsdSupervisorConfig:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    return ArsdSupervisorConfig(
        type=ARSD_SUPERVISOR_CONFIG_TYPE,
        approval_ref="approval_arsd_dispatcher_offline",
        owner="sachima_host",
        namespace="sachima_tasks",
        socket_path=_SOCKET_CANARY,
        binding_ledger_path=str(tmp_path / "arsd-run-bindings.json"),
        agent_by_policy_ref={"policy_agent": "reader-agent"},
        model_by_policy_ref={"policy_model": "claude-sonnet-5"},
        effort_by_policy_ref={"policy_effort": "medium"},
        workspace_by_ref={"ws_arsint": str(work)},
        run_limits_by_policy_ref={
            "policy_limits": {
                "startup_timeout_seconds": 60.0,
                "turn_timeout_seconds": 600.0,
                "cancel_grace_seconds": 10.0,
                "max_stderr_bytes": 262_144,
                "max_event_bytes": 65_536,
                "max_events": 10_000,
            }
        },
        grant_ref="grant_reader_v1",
        grant_hash="sha256:" + "a" * 64,
        grant_role_hash="sha256:" + "b" * 64,
        grant_capabilities=("read", "search"),
        mcp_snapshot_hashes=("sha256:" + "c" * 64,),
        credential_refs=("cred_reader_github",),
        evidence_policy_hash="sha256:" + "d" * 64,
        recovery_policy_hash="sha256:" + "e" * 64,
        enabled=True,
    )


@pytest.fixture()
def rig(tmp_path: Path):
    facade = _FacadeDouble()
    payloads: dict[str, str] = {"payload_goal_1": "ship the integration"}
    resolver_calls: list[str] = []

    def resolver(payload_ref: str) -> str:
        resolver_calls.append(payload_ref)
        return payloads[payload_ref]

    # Composed exactly as `bind_arsd_execution` does it: one shared task
    # operation lock across both layers, and a recovery that resolves the
    # frozen prompt back through the same claim-check resolver the dispatch
    # used.
    task_locks = TaskOperationLocks()
    backend = ArsdSupervisorBackend(
        _config(tmp_path),
        facade,
        ArsdRunBindingLedger(str(tmp_path / "ledger.json")),
        prompt_resolver=prompt_resolver_from_payload_resolver(resolver),
        task_locks=task_locks,
    )
    registry = TaskRegistry()
    port = AgentRunSupervisorPort(registry, backend)
    bindings = LiveProgressSourceBindings()

    dispatcher = AgentRunSupervisorTurnDispatcher(
        port, backend, bindings, registry, resolver, task_locks=task_locks
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
        facade=facade,
        backend=backend,
        registry=registry,
        port=port,
        bindings=bindings,
        payloads=payloads,
        resolver_calls=resolver_calls,
        dispatcher=dispatcher,
        ref=ref,
        task_locks=task_locks,
        ledger_path=str(tmp_path / "ledger.json"),
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
            turn_ref="run_ab12cd34",
            supervisor_status=None,
            artifact_ref="run_ab12cd34",
            error_code=RUNTIME_ARS_TURN_FAILED,
        )
    # off-vocabulary supervisor status is refused
    with pytest.raises(SpineError):
        TurnDispatchOutcome(
            task_id="task_alpha",
            session_id="sess_1",
            turn_ref="run_ab12cd34",
            supervisor_status="did_great",
            artifact_ref="run_ab12cd34",
            error_code=None,
        )


def test_forged_outcome_fails_closed() -> None:
    forged = object.__new__(TurnDispatchOutcome)
    for name, value in (
        ("task_id", "task_alpha"),
        ("session_id", "sess_1"),
        ("turn_ref", "/srv/private/turn"),
        ("supervisor_status", "completed"),
        ("artifact_ref", "run_ab12cd34"),
        ("error_code", None),
    ):
        object.__setattr__(forged, name, value)
    with pytest.raises(SpineError) as exc:
        validate_turn_dispatch_outcome(forged)
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH


# --------------------------------------------------------------------------- #
# B. Dispatch — submit, auto-binding, cursor reset, refs-only events
# --------------------------------------------------------------------------- #
def test_goal_dispatch_binds_the_private_run_locator_and_reports(rig) -> None:
    outcome = rig.dispatcher.dispatch(_request(rig))

    assert validate_turn_dispatch_outcome(outcome) is outcome
    assert outcome.task_id == "task_alpha"
    assert outcome.session_id == rig.ref.session_id
    # A durable acceptance, not a terminal: terminal truth arrives later.
    assert outcome.supervisor_status == "accepted"
    assert outcome.error_code is None
    assert re.fullmatch(r"run_[0-9a-f]{8}", outcome.turn_ref)
    assert outcome.artifact_ref == outcome.turn_ref

    # The payload text reached the wire verbatim — never a literal ``/goal``
    # slash prompt, which a non-native adapter would silently no-op.
    ((_request_id, payload),) = rig.facade.submitted
    assert payload["prompt_text"] == "ship the integration"
    assert not payload["prompt_text"].startswith("/goal")

    # The private run locator is bound, tagged, for the live chain.
    resolved = rig.bindings.resolve("task_alpha", rig.ref.session_id)
    assert resolved.artifact_dir == f"{_RUN_ID_CANARY}-1"
    assert resolved.source.artifact_ref == outcome.turn_ref
    assert resolved.source.source_kind == "arsd_run"
    assert resolved.source.last_seen_cursor is None


def test_the_requests_payload_ref_is_the_durable_dispatch_key(rig) -> None:
    """P5: ``dispatch_ref`` is mandatory, and the dispatcher supplies it.

    It is the request's own claim-check ref, so the durable binding a recovery
    would resolve is addressable from the request alone.
    """

    rig.dispatcher.dispatch(_request(rig))
    ledger = ArsdRunBindingLedger(rig.ledger_path)
    handle = rig.backend.create_or_attach("task_alpha", _REFS)
    binding = ledger.resolve("task_alpha", handle, "payload_goal_1")
    assert binding is not None
    assert binding.dispatch_ref == "payload_goal_1"
    assert binding.state == "accepted"

    signature = inspect.signature(rig.backend.run_turn)
    assert signature.parameters["dispatch_ref"].default is inspect.Parameter.empty


def test_dispatcher_admits_a_backend_only_through_the_factory_allowlist(rig) -> None:
    """The constructor names no concrete backend class — it validates one."""

    class _ProtocolShapedBackend:
        def create_or_attach(self, task_id, refs): ...
        def attach_existing(self, task_id): ...
        def run_turn(self, task_id, *, turn_kind, payload_text, dispatch_ref, payload_ref): ...
        def recover_uncertain_submission(self, task_id, dispatch_ref): ...
        def latest_accepted_turn(self, task_id): ...
        def status(self, handle): ...
        def signal(self, handle, decision_ref): ...
        def kill(self, handle, reason_ref): ...
        def liveness(self, handle): ...

    dispatcher_source = inspect.getsource(AgentRunSupervisorTurnDispatcher)
    assert "ArsdSupervisorBackend" not in dispatcher_source

    for refused in (_ProtocolShapedBackend(), None, object()):
        with pytest.raises(SpineError) as exc:
            AgentRunSupervisorTurnDispatcher(
                rig.port, refused, rig.bindings, rig.registry
            )
        assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH


def test_prompt_dispatch_sends_payload_verbatim(rig) -> None:
    rig.payloads["payload_prompt_1"] = "please summarize the diff"
    outcome = rig.dispatcher.dispatch(
        _request(rig, turn_kind="prompt", payload_ref="payload_prompt_1")
    )
    assert outcome.supervisor_status == "accepted"
    ((_request_id, payload),) = rig.facade.submitted
    assert payload["prompt_text"] == "please summarize the diff"


def test_each_dispatch_rebinds_new_locator_and_resets_cursor(rig) -> None:
    """Two turns, one Session: the binding follows the newest Run.

    A Run ending is not the task ending, so the second turn is dispatchable
    through the port — and each turn is a fresh read-model stream, so the
    foreign cursor a caller advanced on the first does not bleed into it.
    """

    first = rig.dispatcher.dispatch(_request(rig))
    rig.bindings.update_last_seen_cursor("task_alpha", 41, rig.ref.session_id)
    assert (
        rig.bindings.resolve_source("task_alpha", rig.ref.session_id).last_seen_cursor
        == 41
    )

    # A second turn is a second Run, so the first has to be over first (§7.4).
    rig.facade.run_ended()
    rig.payloads["payload_goal_2"] = "and now the follow-up"
    second = rig.dispatcher.dispatch(_request(rig, payload_ref="payload_goal_2"))

    assert second.turn_ref != first.turn_ref
    assert re.fullmatch(r"run_[0-9a-f]{8}", second.turn_ref)
    source = rig.bindings.resolve_source("task_alpha", rig.ref.session_id)
    assert source.artifact_ref == second.turn_ref
    assert source.last_seen_cursor is None
    resolved = rig.bindings.resolve("task_alpha", rig.ref.session_id)
    assert resolved.artifact_dir == f"{_RUN_ID_CANARY}-2"

    # Two Runs, one ARS Session, and the task never went terminal between them.
    assert rig.facade.ops("submit") == 2
    assert rig.facade.submitted[1][1]["request"]["session_id"] == _ARS_SESSION_CANARY
    assert rig.port.status(rig.ref).terminal is False


def test_a_second_turn_against_an_unfinished_run_is_a_turn_stage_failure(rig) -> None:
    """The backend's §7.4 exclusion surfaces as a failure-shaped outcome.

    The dispatcher does not translate it into a success, and the previous
    binding is left exactly as it was.
    """

    first = rig.dispatcher.dispatch(_request(rig))
    prior = rig.bindings.resolve("task_alpha", rig.ref.session_id)
    rig.payloads["payload_goal_2"] = "and now the follow-up"

    outcome = rig.dispatcher.dispatch(_request(rig, payload_ref="payload_goal_2"))
    assert outcome.error_code == RUNTIME_ARS_TURN_FAILED
    assert outcome.turn_ref is None
    assert rig.facade.ops("submit") == 1

    after = rig.bindings.resolve("task_alpha", rig.ref.session_id)
    assert after.source.artifact_ref == prior.source.artifact_ref == first.turn_ref
    assert after.artifact_dir == prior.artifact_dir


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


def test_accepted_turn_keeps_the_session_running(rig) -> None:
    rig.dispatcher.dispatch(_request(rig))
    status = rig.port.status(rig.ref)
    assert status.state == "running"
    assert status.alive is True


def test_a_failed_run_is_reported_without_ending_the_task(rig) -> None:
    """An honest failure on the Run surface; a live Session on the task's.

    The Run failed, and the backend says so. What it does not do is close a
    durable Session that ARS has no close operation for, so the next turn is
    still dispatchable and nothing terminal is appended to the canonical log.
    """

    rig.facade.run_ended("failed")
    outcome = rig.dispatcher.dispatch(_request(rig))
    # The transport's own terminal token never reaches a dispatch outcome: the
    # outcome carries the neutral acceptance of the submit.
    assert outcome.supervisor_status == "accepted"
    assert outcome.supervisor_status in SUPERVISOR_TURN_STATUSES
    assert outcome.error_code is None

    # Run-facing truth is the failure...
    handle = rig.backend.create_or_attach("task_alpha", _REFS)
    assert rig.backend.observe_run(handle) == "failed"
    # ...and the task is still live.
    status = rig.port.status(rig.ref)
    assert status.state == "running"
    assert status.terminal is False
    assert [
        e for e in rig.registry.log.events_for("task_alpha") if e.event_type == "failed"
    ] == []


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
    rig.dispatcher.dispatch(_request(rig))
    rig.facade.run_cancel_payload = {
        "status": "cancelled",
        "result": {"status": "cancelled"},
    }
    rig.port.kill(rig.ref, "ref_cancelled")
    submits_before = rig.facade.ops("submit")

    rig.payloads["payload_goal_2"] = "and now the follow-up"
    with pytest.raises(SpineError) as exc:
        rig.dispatcher.dispatch(_request(rig, payload_ref="payload_goal_2"))
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH
    assert rig.facade.ops("submit") == submits_before


def test_unresolvable_payload_fails_closed_without_echo(rig) -> None:
    request = _request(rig, payload_ref="payload_missing")
    with pytest.raises(SpineError) as exc:
        rig.dispatcher.dispatch(request)
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH
    assert "payload_missing" not in str(exc.value) or str(exc.value) == exc.value.code
    assert rig.facade.submitted == []


def test_turn_crash_returns_error_outcome_and_binds_nothing(rig) -> None:
    """A turn that dies inside the backend leaves no binding and no echo."""

    rig.facade.submit_error = RuntimeError("the daemon blew up with /srv/private detail")
    outcome = rig.dispatcher.dispatch(_request(rig))
    assert outcome.error_code == RUNTIME_ARS_TURN_FAILED
    assert outcome.supervisor_status is None
    assert outcome.turn_ref is None
    assert outcome.artifact_ref is None

    # No half-bound state: nothing was bound at all.
    with pytest.raises(SpineError):
        rig.bindings.resolve("task_alpha", rig.ref.session_id)
    assert "/srv/private" not in repr(outcome)


def test_single_flight_rejects_concurrent_dispatch_for_same_task(rig) -> None:
    # Hold the first dispatch inside its negotiation: its pending intent has
    # not landed yet, so the single-flight guard — not the backend's own
    # unresolved-intent refusal — is what answers the second attempt.
    #
    # Composing the backend already negotiated once, so the "started" signal is
    # cleared first: waiting on a set event would race the worker into the slot
    # instead of waiting for it to arrive.
    rig.facade.server_info_started.clear()
    rig.facade.server_info_gate = threading.Event()
    results: list[Any] = []

    def _first() -> None:
        results.append(rig.dispatcher.dispatch(_request(rig)))

    worker = threading.Thread(target=_first)
    worker.start()
    assert rig.facade.server_info_started.wait(timeout=5)
    assert rig.dispatcher.in_flight("task_alpha") is True
    with pytest.raises(SpineError) as exc:
        rig.dispatcher.dispatch(_request(rig))
    assert exc.value.code == RUNTIME_TURN_DISPATCH_BUSY

    rig.facade.server_info_gate.set()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert rig.dispatcher.in_flight("task_alpha") is False
    (outcome,) = results
    assert outcome.supervisor_status == "accepted"
    assert rig.facade.ops("submit") == 1


def test_in_flight_clears_after_turn_crash(rig) -> None:
    rig.facade.submit_error = RuntimeError("boom")
    rig.dispatcher.dispatch(_request(rig))
    assert rig.dispatcher.in_flight("task_alpha") is False


# --------------------------------------------------------------------------- #
# D. No-leak: payload text, raw ids, and private paths never escape
# --------------------------------------------------------------------------- #
def test_payload_and_private_material_never_leak_into_any_surface(rig) -> None:
    canary = "payload-canary-51ee-never-echo"
    rig.payloads["payload_canary"] = canary
    outcome = rig.dispatcher.dispatch(_request(rig, payload_ref="payload_canary"))

    surfaces = [repr(outcome), repr(rig.dispatcher)]
    events = rig.registry.log.events_for("task_alpha")
    surfaces.extend(json.dumps(_event_dict(event)) for event in events)
    source = rig.bindings.resolve_source("task_alpha", rig.ref.session_id)
    surfaces.append(serialize_live_progress_source(source).decode("utf-8"))
    surfaces.append(json.dumps(dataclasses.asdict(rig.port.status(rig.ref))))
    combined = "\n".join(surfaces)
    assert canary not in combined
    assert _SOCKET_CANARY not in combined
    assert _RUN_ID_CANARY not in combined
    assert _ARS_SESSION_CANARY not in combined
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


# --------------------------------------------------------------------------- #
# E. Reservation order and event honesty (final-review blocker 2)
# --------------------------------------------------------------------------- #
def _events(rig) -> list[str]:
    return [e.event_type for e in rig.registry.log.events_for("task_alpha")]


def test_a_busy_dispatch_says_busy_and_has_zero_backend_port_and_log_effects(
    rig,
) -> None:
    """Busy is answered from the slot alone, before anything is touched.

    The slot has to be taken the moment the request validates. Reading the
    port first — as this used to — means a concurrent dispatch runs a backend
    observation before it is told it is busy, and during the one window that
    matters most it does not even get told: the winner's pending intent is
    already on disk while its ack is unread, so the port's own read fails
    closed and the loser is handed ``runtime_invalid_turn_dispatch`` instead
    of ``runtime_turn_dispatch_busy``. A slot taken first is both honest and
    free.
    """

    rig.facade.submit_gate = threading.Event()
    results: list[Any] = []

    def _first() -> None:
        results.append(rig.dispatcher.dispatch(_request(rig)))

    worker = threading.Thread(target=_first)
    worker.start()
    assert rig.facade.submit_started.wait(timeout=5)

    calls_before = list(rig.facade.calls)
    events_before = _events(rig)
    resolver_before = list(rig.resolver_calls)
    with pytest.raises(SpineError) as exc:
        rig.dispatcher.dispatch(_request(rig))
    assert exc.value.code == RUNTIME_TURN_DISPATCH_BUSY

    # Nothing was read, submitted, resolved, or appended on the busy path.
    assert rig.facade.calls == calls_before
    assert _events(rig) == events_before
    assert rig.resolver_calls == resolver_before

    rig.facade.submit_gate.set()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert results and results[0].supervisor_status == "accepted"


def test_a_refused_turn_appends_no_canonical_event(rig) -> None:
    """A turn that never became a Run leaves no trace claiming it did.

    The §7.4 active-Run refusal happens inside the backend, so the dispatcher
    used to have already appended ``progress/running`` by then — a canonical
    event asserting work started for a turn that was refused before a submit.
    """

    rig.dispatcher.dispatch(_request(rig))
    events_after_first = _events(rig)
    rig.payloads["payload_goal_2"] = "and now the follow-up"

    outcome = rig.dispatcher.dispatch(_request(rig, payload_ref="payload_goal_2"))
    assert outcome.error_code == RUNTIME_ARS_TURN_FAILED
    assert _events(rig) == events_after_first
    assert rig.facade.ops("submit") == 1


def test_progress_and_milestone_are_appended_only_after_a_durable_acceptance(
    rig,
) -> None:
    """The canonical log records turns that started, not turns that were tried."""

    rig.facade.submit_error = _TransportLoss("the daemon never answered")
    outcome = rig.dispatcher.dispatch(_request(rig))
    assert outcome.error_code == RUNTIME_ARS_TURN_FAILED
    assert _events(rig) == ["task_created", "agent_attached"]

    # The acceptance that does arrive publishes both, in order — and it
    # arrives through the explicit recovery, because an uncertain submit is
    # exactly the state that must not resolve itself.
    rig.facade.submit_error = None
    accepted = rig.dispatcher.recover_dispatch(_request(rig))
    assert accepted.error_code is None
    assert _events(rig)[-2:] == ["progress", "milestone"]


# --------------------------------------------------------------------------- #
# F. Explicit recovery and restart rehydration (final-review blocker 3)
# --------------------------------------------------------------------------- #
def test_a_lost_ack_is_recovered_through_the_dispatcher_and_published_once(
    rig,
) -> None:
    """The composed path can finish what an uncertain submit started.

    The prompt is resolved through the same injected resolver, from the
    ``prompt_ref`` the intent persisted — which is the request's own
    claim-check ref — so recovery rebuilds the byte-identical payload without
    the caller holding the text.
    """

    rig.facade.submit_error = _TransportLoss("reply never read")
    outcome = rig.dispatcher.dispatch(_request(rig))
    assert outcome.error_code == RUNTIME_ARS_TURN_FAILED
    assert _events(rig) == ["task_created", "agent_attached"]
    assert rig.facade.ops("submit") == 1

    # Nothing automatic acts on it. The ordinary path cannot even read the
    # task while the intent is unresolved — the port's own status fails closed
    # — so a re-dispatch is refused outright rather than quietly resending.
    rig.facade.submit_error = None
    with pytest.raises(SpineError) as blocked:
        rig.dispatcher.dispatch(_request(rig))
    assert blocked.value.code == RUNTIME_INVALID_TURN_DISPATCH
    assert rig.facade.ops("submit") == 1

    recovered = rig.dispatcher.recover_dispatch(_request(rig))
    assert recovered.error_code is None
    assert recovered.supervisor_status == "accepted"
    assert rig.facade.ops("submit") == 2
    # The resend carried the identical frozen payload.
    assert rig.facade.submitted[-1][1]["prompt_text"] == "ship the integration"

    # Published exactly like an ordinary acceptance.
    kinds = _events(rig)
    assert kinds[-2:] == ["progress", "milestone"]
    source = rig.bindings.resolve_source("task_alpha", rig.ref.session_id)
    assert source.artifact_ref == recovered.turn_ref
    assert source.source_kind == "arsd_run"
    assert source.last_seen_cursor is None


def test_recovery_without_a_pending_intent_is_a_turn_stage_failure(rig) -> None:
    rig.dispatcher.dispatch(_request(rig))
    events_before = _events(rig)
    outcome = rig.dispatcher.recover_dispatch(_request(rig))
    assert outcome.error_code == RUNTIME_ARS_TURN_FAILED
    assert _events(rig) == events_before
    assert rig.facade.ops("submit") == 1


def test_a_recomposed_dispatcher_rehydrates_the_accepted_run_without_submitting(
    rig, tmp_path: Path
) -> None:
    """A restart can read the live Run's stream without starting anything.

    The durable ledger already names the accepted Run; rehydration turns that
    into a read-model source binding through refs-only derivation and the
    private locator, with no submit and no daemon operation at all.
    """

    first = rig.dispatcher.dispatch(_request(rig))

    # A brand-new process: same ledger path and same task, empty in-memory
    # binding store and a fresh facade that would record any daemon touch.
    fresh_facade = _FacadeDouble()
    fresh_locks = TaskOperationLocks()
    fresh_backend = ArsdSupervisorBackend(
        _config(tmp_path),
        fresh_facade,
        ArsdRunBindingLedger(rig.ledger_path),
        task_locks=fresh_locks,
    )
    fresh_registry = TaskRegistry()
    fresh_port = AgentRunSupervisorPort(fresh_registry, fresh_backend)
    fresh_bindings = LiveProgressSourceBindings()
    fresh_dispatcher = AgentRunSupervisorTurnDispatcher(
        fresh_port,
        fresh_backend,
        fresh_bindings,
        fresh_registry,
        lambda ref: "x",
        task_locks=fresh_locks,
    )
    ref = fresh_port.create_or_attach(
        "task_alpha",
        build_launch_spec(
            task_id="task_alpha",
            agent_kind="local_agent",
            mode_flags={"needs_agent": True},
            roles=("read_only",),
            refs=_REFS,
        ),
    )
    calls_before = list(fresh_facade.calls)

    turn_ref = fresh_dispatcher.rehydrate_source_binding("task_alpha", ref.session_id)
    assert turn_ref == first.turn_ref

    source = fresh_bindings.resolve_source("task_alpha", ref.session_id)
    assert source.artifact_ref == turn_ref
    assert source.source_kind == "arsd_run"
    assert source.last_seen_cursor is None
    resolved = fresh_bindings.resolve("task_alpha", ref.session_id)
    assert resolved.artifact_dir == f"{_RUN_ID_CANARY}-1"

    # Refs-only derivation: no submit, no daemon operation, no fabricated event.
    assert fresh_facade.calls == calls_before
    assert fresh_facade.ops("submit") == 0
    assert [e.event_type for e in fresh_registry.log.events_for("task_alpha")] == [
        "task_created",
        "agent_attached",
    ]


def test_rehydration_of_a_task_with_nothing_accepted_binds_nothing(rig) -> None:
    assert rig.dispatcher.rehydrate_source_binding("task_alpha", rig.ref.session_id) is None
    with pytest.raises(SpineError):
        rig.bindings.resolve("task_alpha", rig.ref.session_id)


# --------------------------------------------------------------------------- #
# G. One task operation critical section across both layers
#    (final cross-layer architecture repair)
# --------------------------------------------------------------------------- #
def test_a_cancel_cannot_interleave_between_acceptance_and_publication(
    rig, tmp_path: Path
) -> None:
    """Publication and admission are one task operation, or neither is safe.

    A durable acceptance that Sachima has not published yet is exactly as
    cancellable as one it has — but the publication must not land *after* the
    cancel, or the canonical log ends with a task that was cancelled and then
    started running.

    The window is opened deliberately: publication is parked at its first step
    and the cancel is given a bounded chance to finish. Inside one shared task
    operation it cannot take that chance; outside one it takes it every time.
    """

    rig.facade.run_cancel_payload = {
        "status": "cancelled",
        "result": {"status": "cancelled"},
    }
    real_bind = rig.bindings.bind_source
    reached_publish = threading.Event()
    release_publish = threading.Event()
    held_the_section: list[bool] = []
    task_lock = rig.task_locks.for_task("task_alpha")

    def _parked_bind(*args: Any, **kwargs: Any) -> Any:
        held_the_section.append(task_lock._is_owned())
        reached_publish.set()
        release_publish.wait(timeout=10)
        return real_bind(*args, **kwargs)

    rig.bindings.bind_source = _parked_bind  # type: ignore[method-assign]
    outcomes: dict[str, Any] = {}
    cancel_finished = threading.Event()

    def _dispatch_turn() -> None:
        outcomes["dispatch"] = rig.dispatcher.dispatch(_request(rig))

    def _cancel() -> None:
        try:
            outcomes["kill"] = rig.port.kill(rig.ref, "ref_cancelled").state
        except SpineError as exc:  # pragma: no cover - asserted below
            outcomes["kill"] = exc
        finally:
            cancel_finished.set()

    worker = threading.Thread(target=_dispatch_turn)
    worker.start()
    assert reached_publish.wait(timeout=5)

    canceller = threading.Thread(target=_cancel)
    canceller.start()
    # The cancel gets a real, bounded chance to land first. Holding the same
    # section is the only reason it cannot.
    assert cancel_finished.wait(timeout=1.0) is False

    release_publish.set()
    for thread in (worker, canceller):
        thread.join(timeout=30)
        assert not thread.is_alive()

    # Publication really did run inside the section the admission held.
    assert held_the_section == [True]
    assert outcomes["dispatch"].error_code is None
    assert outcomes["kill"] == "cancelled"

    kinds = _events(rig)
    assert kinds[-3:] == ["progress", "milestone", "cancelled"]
    assert rig.facade.ops("submit") == 1
    assert rig.facade.ops("run_cancel") == 1


def test_rehydration_cannot_be_overtaken_into_a_stale_source_binding(rig) -> None:
    """A rebind must never publish an older Run over a newer one.

    A restart reads "the latest accepted Run" and then binds it. Split that
    read from that bind and a turn landing in between makes the rebind publish
    the Run it superseded — so a rebind is a task operation like any other: it
    takes the same slot and the same section a dispatch does, and while one is
    in flight it is refused outright rather than allowed to read a world that
    is about to change.

    The window is opened where it actually exists: a second turn parked inside
    its submit, with its acceptance not yet durable, so a rebind reading right
    then would still see the FIRST Run.
    """

    first = rig.dispatcher.dispatch(_request(rig))
    rig.facade.run_ended()
    # Two Runs need two acceptance instants: "latest" is the instant the daemon
    # stated, and a tie is irreconcilable rather than broken by key order.
    rig.facade.accepted_at = "2026-08-17T06:07:08+00:00"
    rig.payloads["payload_goal_2"] = "and now the follow-up"

    # A read taken during the second turn would have handed a rebind the OLD Run.
    stale = rig.backend.latest_accepted_turn(
        "task_alpha", session_ref=rig.ref.session_id
    )
    assert stale is not None and stale.result.run_ref == first.turn_ref

    rig.facade.submit_gate = threading.Event()
    outcomes: dict[str, Any] = {}

    def _second_turn() -> None:
        outcomes["second"] = rig.dispatcher.dispatch(
            _request(rig, payload_ref="payload_goal_2")
        )

    worker = threading.Thread(target=_second_turn)
    worker.start()
    assert rig.facade.submit_started.wait(timeout=5)

    # Refused, not served a stale view — and nothing is bound on the way out.
    bound_before = rig.bindings.resolve_source("task_alpha", rig.ref.session_id)
    with pytest.raises(SpineError) as exc:
        rig.dispatcher.rehydrate_source_binding("task_alpha", rig.ref.session_id)
    assert exc.value.code == RUNTIME_TURN_DISPATCH_BUSY
    assert (
        rig.bindings.resolve_source("task_alpha", rig.ref.session_id).artifact_ref
        == bound_before.artifact_ref
    )

    rig.facade.submit_gate.set()
    worker.join(timeout=30)
    assert not worker.is_alive()

    second = outcomes["second"]
    assert second.error_code is None
    assert second.turn_ref != first.turn_ref

    # Once the turn is over, a rebind sees the world after it — never before.
    assert rig.dispatcher.rehydrate_source_binding(
        "task_alpha", rig.ref.session_id
    ) == second.turn_ref
    source = rig.bindings.resolve_source("task_alpha", rig.ref.session_id)
    assert source.artifact_ref == second.turn_ref
    assert rig.bindings.resolve("task_alpha", rig.ref.session_id).artifact_dir == (
        f"{_RUN_ID_CANARY}-2"
    )


def test_rehydration_under_a_different_canonical_session_is_fail_closed(rig) -> None:
    """The ledger's Session and the canonical one must be the same Session.

    A rebind under another Session would attach a Run to a conversation it
    never ran in. It is refused with zero mutation: nothing bound, nothing
    appended, nothing asked of the daemon.
    """

    rig.dispatcher.dispatch(_request(rig))
    events_before = _events(rig)
    calls_before = list(rig.facade.calls)

    with pytest.raises(SpineError) as exc:
        rig.dispatcher.rehydrate_source_binding("task_alpha", "sess_9")
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH

    assert _events(rig) == events_before
    assert rig.facade.calls == calls_before
    source = rig.bindings.resolve_source("task_alpha", rig.ref.session_id)
    assert source.artifact_ref == rig.bindings.resolve_source(
        "task_alpha", rig.ref.session_id
    ).artifact_ref
    with pytest.raises(SpineError):
        rig.bindings.resolve("task_alpha", "sess_9")


# --------------------------------------------------------------------------- #
# H. A real executor, and a reentrant lock that never crosses a thread hand-off
# --------------------------------------------------------------------------- #
#: Every test in this section is bounded: a deadlock shows up as a timeout
#: assertion, never as a hung suite.
_BOUND = 10.0


def _pooled(rig) -> tuple[AgentRunSupervisorTurnDispatcher, ThreadPoolExecutor]:
    """A dispatcher whose turns really do run on another thread."""

    pool = ThreadPoolExecutor(max_workers=1)
    dispatcher = AgentRunSupervisorTurnDispatcher(
        rig.port,
        rig.backend,
        rig.bindings,
        rig.registry,
        rig.payloads.__getitem__,
        executor=pool,
        task_locks=rig.task_locks,
    )
    return dispatcher, pool


def _finishes(target: Any, *args: Any) -> Any:
    """Run ``target`` on its own thread and require it to finish, bounded."""

    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["value"] = target(*args)
        except BaseException as exc:  # pragma: no cover - surfaced by the caller
            box["error"] = exc

    thread = threading.Thread(target=_run)
    thread.start()
    thread.join(timeout=_BOUND)
    assert not thread.is_alive(), "the operation never finished — deadlock"
    if "error" in box:
        raise box["error"]
    return box["value"]


def test_a_dispatch_on_a_real_executor_completes_and_publishes_exactly_once(
    rig,
) -> None:
    """The section is acquired in the worker, so the hand-off is survivable.

    A caller that held the task lock and then waited on a worker would be
    waiting for a thread that cannot acquire what the caller holds — a
    reentrant lock is thread-affine, so it would never be handed over. The
    whole operation therefore runs in the worker, and this proves it in
    bounded time rather than hanging.
    """

    dispatcher, pool = _pooled(rig)
    try:
        outcome = _finishes(dispatcher.dispatch, _request(rig))
    finally:
        pool.shutdown(wait=True)

    assert outcome.error_code is None
    assert outcome.supervisor_status == "accepted"
    assert rig.facade.ops("submit") == 1
    assert _events(rig)[-2:] == ["progress", "milestone"]
    source = rig.bindings.resolve_source("task_alpha", rig.ref.session_id)
    assert source.artifact_ref == outcome.turn_ref
    # The section really was the shared one, and it is free again.
    assert rig.task_locks.for_task("task_alpha").acquire(timeout=1)
    rig.task_locks.for_task("task_alpha").release()


def test_a_lost_ack_recovery_on_a_real_executor_completes_and_publishes_once(
    rig,
) -> None:
    dispatcher, pool = _pooled(rig)
    try:
        rig.facade.submit_error = _TransportLoss("reply never read")
        lost = _finishes(dispatcher.dispatch, _request(rig))
        assert lost.error_code == RUNTIME_ARS_TURN_FAILED
        assert _events(rig) == ["task_created", "agent_attached"]

        rig.facade.submit_error = None
        recovered = _finishes(dispatcher.recover_dispatch, _request(rig))
    finally:
        pool.shutdown(wait=True)

    assert recovered.error_code is None
    assert recovered.supervisor_status == "accepted"
    # One request id, resent byte-identically, published exactly once.
    assert rig.facade.ops("submit") == 2
    assert rig.facade.submitted[0] == rig.facade.submitted[1]
    assert _events(rig)[-2:] == ["progress", "milestone"]
    assert rig.bindings.resolve_source(
        "task_alpha", rig.ref.session_id
    ).artifact_ref == recovered.turn_ref


def test_the_kill_publication_race_stays_serialized_on_a_real_executor(rig) -> None:
    """The prior guarantee is unchanged when the operation runs off-thread."""

    dispatcher, pool = _pooled(rig)
    rig.facade.run_cancel_payload = {
        "status": "cancelled",
        "result": {"status": "cancelled"},
    }
    real_bind = rig.bindings.bind_source
    reached_publish = threading.Event()
    release_publish = threading.Event()
    held_the_section: list[bool] = []
    task_lock = rig.task_locks.for_task("task_alpha")

    def _parked_bind(*args: Any, **kwargs: Any) -> Any:
        held_the_section.append(task_lock._is_owned())
        reached_publish.set()
        release_publish.wait(timeout=_BOUND)
        return real_bind(*args, **kwargs)

    rig.bindings.bind_source = _parked_bind  # type: ignore[method-assign]
    outcomes: dict[str, Any] = {}
    cancel_finished = threading.Event()

    def _dispatch_turn() -> None:
        outcomes["dispatch"] = dispatcher.dispatch(_request(rig))

    def _cancel() -> None:
        try:
            outcomes["kill"] = rig.port.kill(rig.ref, "ref_cancelled").state
        finally:
            cancel_finished.set()

    worker = threading.Thread(target=_dispatch_turn)
    worker.start()
    try:
        assert reached_publish.wait(timeout=_BOUND)
        canceller = threading.Thread(target=_cancel)
        canceller.start()
        assert cancel_finished.wait(timeout=1.0) is False
        release_publish.set()
        for thread in (worker, canceller):
            thread.join(timeout=_BOUND)
            assert not thread.is_alive()
    finally:
        release_publish.set()
        pool.shutdown(wait=True)

    # The worker held the shared section while publishing, so the cancel could
    # only land after it.
    assert held_the_section == [True]
    assert outcomes["dispatch"].error_code is None
    assert outcomes["kill"] == "cancelled"
    assert _events(rig)[-3:] == ["progress", "milestone", "cancelled"]
    assert rig.facade.ops("submit") == 1


class _TimingOutExecutor:
    """A real worker, and a caller that stops waiting for it."""

    def __init__(self, pool: ThreadPoolExecutor) -> None:
        self._pool = pool
        self.futures: list[Any] = []

    def submit(self, run: Any) -> Any:
        future = self._pool.submit(run)
        self.futures.append(future)

        class _GaveUp:
            def result(self_inner) -> Any:
                raise TimeoutError("the caller stopped waiting")

        return _GaveUp()


def test_a_caller_timeout_frees_the_slot_but_never_the_section(rig) -> None:
    """The slot bounds concurrency; the section bounds correctness.

    A caller that gives up gets the failure-shaped outcome and releases the
    single-flight slot — it has to, or the task would be wedged forever. What
    it must NOT do is release the task operation: the worker is still inside
    it, and everything the operation owns stays owned until it finishes.
    """

    pool = ThreadPoolExecutor(max_workers=2)
    timing_out = _TimingOutExecutor(pool)
    dispatcher = AgentRunSupervisorTurnDispatcher(
        rig.port,
        rig.backend,
        rig.bindings,
        rig.registry,
        rig.payloads.__getitem__,
        executor=timing_out,
        task_locks=rig.task_locks,
    )
    rig.facade.submit_gate = threading.Event()
    rig.payloads["payload_goal_2"] = "and now the follow-up"
    task_lock = rig.task_locks.for_task("task_alpha")

    try:
        # The caller gives up while the worker is still inside its submit.
        timed_out = _finishes(dispatcher.dispatch, _request(rig))
        assert timed_out.error_code == RUNTIME_ARS_TURN_FAILED
        assert rig.facade.submit_started.wait(timeout=_BOUND)
        assert not timing_out.futures[0].done()

        # The slot is released — it must be, or the task is wedged forever...
        assert rig.dispatcher.in_flight("task_alpha") is False
        # ...and the section is NOT. The worker still owns it.
        assert task_lock.acquire(blocking=True, timeout=0.2) is False

        # So a second dispatch reserving the freed slot changes nothing. It is
        # refused before the daemon is reached at all: the worker's pending
        # intent is on disk with its ack unread, which makes the port's own
        # read fail closed — the precondition catches it without ever
        # contending for the section.
        with pytest.raises(SpineError) as refused:
            _finishes(
                rig.dispatcher.dispatch, _request(rig, payload_ref="payload_goal_2")
            )
        assert refused.value.code == RUNTIME_INVALID_TURN_DISPATCH
        assert rig.facade.ops("submit") == 1
        assert _events(rig) == ["task_created", "agent_attached"]

        rig.facade.submit_gate.set()
        assert timing_out.futures[0].exception(timeout=_BOUND) is None
    finally:
        rig.facade.submit_gate.set()
        pool.shutdown(wait=True)

    # Exactly one acceptance, published exactly once — by the worker the caller
    # stopped waiting for, and by nothing else.
    assert rig.facade.ops("submit") == 1
    assert [event for event in _events(rig) if event == "milestone"] == ["milestone"]
    assert _events(rig)[-2:] == ["progress", "milestone"]
    # And the section is free again now that the worker is done.
    assert task_lock.acquire(blocking=True, timeout=_BOUND) is True
    task_lock.release()


# --------------------------------------------------------------------------- #
# I. The shared lock graph is an enforced invariant, not a convention
# --------------------------------------------------------------------------- #
def test_the_dispatcher_derives_the_backends_lock_provider_by_default(rig) -> None:
    """A composition root cannot forget to share it, because it cannot choose.

    "Pass the same provider to both" is a convention, and a convention is a
    thing a future caller gets wrong once and reopens the kill/publication race
    with. The provider is the backend's, and the dispatcher takes it from
    there.
    """

    dispatcher = AgentRunSupervisorTurnDispatcher(
        rig.port, rig.backend, rig.bindings, rig.registry, rig.payloads.__getitem__
    )
    assert dispatcher.task_locks is rig.backend.task_locks
    assert dispatcher.task_locks is rig.task_locks
    # The graph is readable, so a composed bundle can check it rather than
    # trust it.
    assert dispatcher.backend is rig.backend
    assert dispatcher.port is rig.port
    assert dispatcher.registry is rig.registry
    assert dispatcher.bindings is rig.bindings


def test_an_explicit_lock_provider_must_be_the_backends_own(rig) -> None:
    """A different provider is two lock graphs, and it is refused before use."""

    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorTurnDispatcher(
            rig.port,
            rig.backend,
            rig.bindings,
            rig.registry,
            rig.payloads.__getitem__,
            task_locks=TaskOperationLocks(),
        )
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH

    # The backend's own provider is of course accepted.
    shared = AgentRunSupervisorTurnDispatcher(
        rig.port,
        rig.backend,
        rig.bindings,
        rig.registry,
        rig.payloads.__getitem__,
        task_locks=rig.backend.task_locks,
    )
    assert shared.task_locks is rig.backend.task_locks


def test_a_backend_publishes_its_lock_provider_on_the_neutral_contract(rig) -> None:
    """The dispatcher reads it off the contract, never off a concrete type."""

    assert isinstance(rig.backend.task_locks, TaskOperationLocks)
    source = Path(
        importlib.import_module(
            "sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher"
        ).__file__
    ).read_text(encoding="utf-8")
    assert "ArsdSupervisorBackend" not in source


# --------------------------------------------------------------------------- #
# J. A resolver fault is the dispatcher's own stable code, and nothing else
# --------------------------------------------------------------------------- #
_RESOLVER_CANARY = "sachima-canary-resolver-private-detail-/srv/private/prompt.txt"


def _resolver_faults() -> list[tuple[str, BaseException]]:
    hostile = SpineError("some_private_backend_code", _RESOLVER_CANARY)
    with_cause = RuntimeError(_RESOLVER_CANARY)
    with_cause.__cause__ = ValueError(_RESOLVER_CANARY)
    return [
        ("spine_error", hostile),
        ("plain", RuntimeError(_RESOLVER_CANARY)),
        ("with_cause", with_cause),
        ("base", KeyboardInterrupt(_RESOLVER_CANARY)),
    ]


@pytest.mark.parametrize(
    "fault", [fault for _name, fault in _resolver_faults()],
    ids=[name for name, _fault in _resolver_faults()],
)
def test_a_resolver_fault_collapses_to_the_stable_code_with_no_leak(
    rig, fault: BaseException
) -> None:
    """Whatever the host's resolver raises, the dispatcher says one thing.

    An injected resolver is host code: it may raise a ``SpineError`` of its
    own, carrying its own code and its own private message. Re-raising that
    would publish a stable code this dispatcher never owned and a message it
    never sanitized, so every fault — including that one — collapses to a
    freshly constructed ``runtime_invalid_turn_dispatch`` with no cause, no
    context, and nothing of the original in it.
    """

    def _hostile(payload_ref: str) -> str:
        raise fault

    dispatcher = AgentRunSupervisorTurnDispatcher(
        rig.port, rig.backend, rig.bindings, rig.registry, _hostile
    )
    calls_before = list(rig.facade.calls)
    events_before = _events(rig)

    with pytest.raises(SpineError) as exc:
        dispatcher.dispatch(_request(rig))

    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH
    assert str(exc.value) == RUNTIME_INVALID_TURN_DISPATCH
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None
    rendered = "".join(traceback.format_exception(exc.value))
    assert _RESOLVER_CANARY not in rendered
    assert "some_private_backend_code" not in rendered

    # Nothing was attempted: no daemon call, no ledger record, no event, no bind.
    assert rig.facade.calls == calls_before
    assert rig.facade.ops("submit") == 0
    assert _events(rig) == events_before
    with pytest.raises(SpineError):
        rig.bindings.resolve("task_alpha", rig.ref.session_id)


def test_a_resolver_fault_collapses_the_same_way_on_a_real_executor(rig) -> None:
    """The worker changes where it happens, never what is said about it."""

    def _hostile(payload_ref: str) -> str:
        raise SpineError("some_private_backend_code", _RESOLVER_CANARY)

    pool = ThreadPoolExecutor(max_workers=1)
    dispatcher = AgentRunSupervisorTurnDispatcher(
        rig.port, rig.backend, rig.bindings, rig.registry, _hostile, executor=pool
    )
    try:
        with pytest.raises(SpineError) as exc:
            _finishes(dispatcher.dispatch, _request(rig))
    finally:
        pool.shutdown(wait=True)

    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH
    assert str(exc.value) == RUNTIME_INVALID_TURN_DISPATCH
    rendered = "".join(traceback.format_exception(exc.value))
    assert _RESOLVER_CANARY not in rendered
    assert "some_private_backend_code" not in rendered
    assert rig.facade.ops("submit") == 0
    assert _events(rig) == ["task_created", "agent_attached"]
