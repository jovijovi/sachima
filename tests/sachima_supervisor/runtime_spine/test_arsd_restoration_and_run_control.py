"""S4 — no-create spine restoration and the Run-scoped cancel seam.

What is proven here, against a **fresh object graph** each time (the thing a
Gateway restart actually produces):

* restoring a *pending* dispatch rebuilds only the backend intent and the sealed
  port/registry identity — no ``create_or_attach``, no submit, no Session
  creation, no source binding, and the ledger bytes are untouched;
* restoring an *accepted* dispatch attaches the exact durable binding it was
  given. With two accepted records for one task it binds **that** record, never
  the task-wide latest, and a contradictory key blocks instead of substituting;
* a fresh graph's construction-time ``server_info`` is the measurement baseline:
  restoration adds zero operations on top of it;
* user cancel is Run-scoped: exactly one ``run_cancel``, no Session operation, no
  port ``kill()``, no task terminalization. Trusted terminal evidence settles it
  and leaves the original ARS Session reusable for the next turn; no evidence is
  honest uncertainty that settles nothing.

Everything runs against injected doubles: no socket is opened, no daemon is
started, and no AGENT is launched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import (
    ARSD_BINDING_ACCEPTED,
    RUNTIME_ARSD_BINDING_CONFLICT,
    ArsdRunBindingLedger,
)
from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    ARSD_SUPERVISOR_CONFIG_TYPE,
    EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
    ArsdSupervisorConfig,
    derive_arsd_request_id,
)
from sachima_supervisor.runtime_spine.arsd_supervisor_backend import (
    ArsdSupervisorBackend,
    derive_arsd_backend_handle,
)
from sachima_supervisor.runtime_spine.events import SpineError
from sachima_supervisor.runtime_spine.execution_port import RUNTIME_INVALID_SESSION

TASK_ID = "delegate_restore_one"
V3_OPERATIONS = [
    "run_cancel",
    "run_events",
    "run_status",
    "server_info",
    "session_list",
    "session_status",
    "submit",
]


class _Facade:
    """One in-memory daemon that counts every operation it is asked for."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.terminals: dict[str, dict[str, Any]] = {}
        self.cancel_replies: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def server_info(self) -> dict[str, Any]:
        self.calls.append("server_info")
        return {
            "version": EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
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
        self.calls.append("submit")
        self._seq += 1
        return {
            "run_id": f"RUN-{self._seq}",
            "session_id": "ARSSESSIONRESTORE",
            "accepted_at": f"2026-08-19T04:05:0{self._seq}+00:00",
        }

    def run_status(self, run_id: str) -> dict[str, Any]:
        self.calls.append("run_status")
        body: dict[str, Any] = {"run_id": run_id, "session_id": "ARSSESSIONRESTORE"}
        terminal = self.terminals.get(run_id)
        if terminal is not None:
            body["result"] = dict(terminal)
        return body

    def run_events(self, run_id: str, *, from_seq: int, limit: int | None = None):
        self.calls.append("run_events")
        return {
            "run_id": run_id,
            "events": [],
            "next_from_seq": from_seq,
            "exhausted": True,
        }

    def run_cancel(self, run_id: str) -> dict[str, Any]:
        self.calls.append("run_cancel")
        reply = self.cancel_replies.get(run_id)
        if reply is not None:
            return dict(reply, run_id=run_id)
        return {"run_id": run_id}

    def session_status(self, session_id: str) -> dict[str, Any]:
        self.calls.append("session_status")
        return {
            "session_id": session_id,
            "owner": "sachima_host",
            "namespace": "sachima_tasks",
            "agent_id": "author-agent",
            "profile_id": None,
            "created_at": "2026-08-19T04:05:06+00:00",
            "updated_at": "2026-08-19T04:05:06+00:00",
            "last_effective_model": None,
            "last_effective_effort": None,
            "quarantine": None,
        }

    def session_list(self) -> dict[str, Any]:
        self.calls.append("session_list")
        return {"sessions": []}

    def counts(self) -> dict[str, int]:
        return {name: self.calls.count(name) for name in set(self.calls)}


def _config(tmp_path: Path) -> ArsdSupervisorConfig:
    private = tmp_path / "private"
    private.mkdir(parents=True, exist_ok=True)
    return ArsdSupervisorConfig(
        type=ARSD_SUPERVISOR_CONFIG_TYPE,
        approval_ref="approval_delegate_offline",
        owner="sachima_host",
        namespace="sachima_tasks",
        socket_path=str(private / "arsd.sock"),
        binding_ledger_path=str(private / "arsd-run-bindings.json"),
        agent_by_policy_ref={"policy_author": "author-agent"},
        model_by_policy_ref={"policy_model": "claude-opus-5"},
        effort_by_policy_ref={"policy_effort": "xhigh"},
        workspace_by_ref={"ws_delegate": str(private / "workspace")},
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
        grant_ref="grant_author_v1",
        grant_hash="sha256:" + "a" * 64,
        grant_role_hash="sha256:" + "b" * 64,
        grant_capabilities=("read", "search"),
        mcp_snapshot_hashes=("sha256:" + "c" * 64,),
        credential_refs=("cred_author",),
        evidence_policy_hash="sha256:" + "d" * 64,
        recovery_policy_hash="sha256:" + "e" * 64,
        enabled=True,
    )


REFS = ("ws_delegate", "policy_author", "policy_model", "policy_effort", "policy_limits")


def _backend(config, facade, ledger, **kwargs) -> ArsdSupervisorBackend:
    return ArsdSupervisorBackend(config, facade, ledger, **kwargs)


def _submit_one(config, facade, ledger, dispatch_ref: str) -> Any:
    """Drive one real acceptance so the ledger holds a genuine record."""

    backend = _backend(config, facade, ledger)
    backend.create_or_attach(TASK_ID, REFS)
    return backend.run_turn(
        TASK_ID,
        turn_kind="prompt",
        payload_text="do the thing",
        dispatch_ref=dispatch_ref,
        payload_ref=dispatch_ref,
        session_ref="sess_1",
    )


def _pending_only(config, ledger, dispatch_ref: str) -> None:
    """Write a pending intent the way a dispatch would, with no submit."""

    handle = derive_arsd_backend_handle(TASK_ID)
    ledger.begin_pending(
        TASK_ID,
        handle,
        dispatch_ref,
        request_id=derive_arsd_request_id(TASK_ID, handle, dispatch_ref),
        payload_digest="sha256:" + "b" * 64,
        resolver_refs={
            "workspace_ref": "ws_delegate",
            "agent_policy_ref": "policy_author",
            "model_policy_ref": "policy_model",
            "effort_policy_ref": "policy_effort",
            "run_limits_policy_ref": "policy_limits",
            "grant_ref": config.grant_ref,
            "grant_hash": config.grant_hash,
            "grant_role_hash": config.grant_role_hash,
            "grant_capabilities_digest": _capabilities_digest(config),
            "turn_kind": "prompt",
            "session_ref": "sess_1",
            "session_mode": "create",
            "prompt_digest": "sha256:" + "c" * 64,
            "prompt_ref": dispatch_ref,
        },
    )


def _capabilities_digest(config) -> str:
    from sachima_supervisor.runtime_spine.arsd_supervisor_backend import (
        _capabilities_digest as digest,
    )

    return digest(config.grant_capabilities)


# --------------------------------------------------------------------------- #
# A. Pending restoration (I7 / A12)
# --------------------------------------------------------------------------- #
def test_pending_restoration_rebuilds_the_intent_and_touches_nothing_else(tmp_path):
    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    dispatch = "dlg_" + "a" * 32
    _pending_only(config, ledger, dispatch)
    before = Path(ledger.path).read_bytes()

    # A genuinely fresh graph: new facade, new backend, empty memory.
    facade = _Facade()
    backend = _backend(config, facade, ArsdRunBindingLedger(config.binding_ledger_path))
    baseline = facade.counts()
    assert baseline == {"server_info": 1}

    handle = backend.rehydrate_pending_intent(TASK_ID, dispatch)
    assert handle == derive_arsd_backend_handle(TASK_ID)
    # Zero operations beyond the construction-time negotiation.
    assert facade.counts() == baseline
    assert Path(ledger.path).read_bytes() == before
    # The task is attachable now, and still has no Run to observe.
    assert backend.attach_existing(TASK_ID) == handle


def test_pending_restoration_refuses_a_key_with_no_pending_intent(tmp_path):
    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    facade = _Facade()
    backend = _backend(config, facade, ledger)
    with pytest.raises(SpineError) as excinfo:
        backend.rehydrate_pending_intent(TASK_ID, "dlg_" + "f" * 32)
    assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT
    assert facade.counts() == {"server_info": 1}


def test_pending_restoration_refuses_an_accepted_record(tmp_path):
    """An accepted dispatch is not a pending intent, and is never re-sent."""

    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    dispatch = "dlg_" + "a" * 32
    _submit_one(config, _Facade(), ledger, dispatch)

    backend = _backend(config, _Facade(), ArsdRunBindingLedger(config.binding_ledger_path))
    with pytest.raises(SpineError) as excinfo:
        backend.rehydrate_pending_intent(TASK_ID, dispatch)
    assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT


# --------------------------------------------------------------------------- #
# B. Accepted restoration binds the EXACT record (I2 / A7 / A12)
# --------------------------------------------------------------------------- #
def _two_accepted(config, ledger) -> tuple[Any, Any]:
    facade = _Facade()
    first = "dlg_" + "a" * 32
    second = "dlg_" + "b" * 32
    backend = _backend(config, facade, ledger)
    backend.create_or_attach(TASK_ID, REFS)
    backend.run_turn(
        TASK_ID,
        turn_kind="prompt",
        payload_text="first",
        dispatch_ref=first,
        payload_ref=first,
        session_ref="sess_1",
    )
    facade.terminals["RUN-1"] = {
        "run_id": "RUN-1",
        "status": "completed",
        "final_message": "one",
        "truncated": False,
        "truncate_reason": None,
    }
    backend.observe_run(derive_arsd_backend_handle(TASK_ID))
    backend.run_turn(
        TASK_ID,
        turn_kind="prompt",
        payload_text="second",
        dispatch_ref=second,
        payload_ref=second,
        session_ref="sess_1",
    )
    handle = derive_arsd_backend_handle(TASK_ID)
    older = ledger.snapshot_exact(TASK_ID, handle, first)
    newer = ledger.snapshot_exact(TASK_ID, handle, second)
    assert older.state == ARSD_BINDING_ACCEPTED
    assert newer.state == ARSD_BINDING_ACCEPTED
    return older, newer


def test_accepted_restoration_binds_the_given_record_not_the_latest(tmp_path):
    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    older, newer = _two_accepted(config, ledger)
    assert older.run_id != newer.run_id

    facade = _Facade()
    fresh = _backend(config, facade, ArsdRunBindingLedger(config.binding_ledger_path))
    baseline = facade.counts()
    handle = fresh.attach_existing(TASK_ID, binding=older)
    assert handle == derive_arsd_backend_handle(TASK_ID)
    assert facade.counts() == baseline

    # It observes the record it was given — the older Run — not the newest.
    facade.terminals[older.run_id] = {
        "run_id": older.run_id,
        "status": "completed",
        "final_message": "the older run",
        "truncated": False,
        "truncate_reason": None,
    }
    assert fresh.observe_run(handle) == "completed"
    assert fresh.observe_run_result(handle).final_message == "the older run"


def test_a_contradictory_binding_blocks_instead_of_substituting(tmp_path):
    """A record about another task, or one the ledger no longer holds, blocks.

    The dangerous failure is not a rejection — it is a *substitution*: attaching
    the task's newest Run because the named one did not check out. Both cases
    here have an obvious "latest" available, and neither is allowed to use it.
    """

    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    older, _newer = _two_accepted(config, ledger)

    # (1) An accepted record that belongs to a different task entirely.
    other_task = "delegate_restore_two"
    other_handle = derive_arsd_backend_handle(other_task)
    other_facade = _Facade()
    other_backend = _backend(config, other_facade, ledger)
    other_backend.create_or_attach(other_task, REFS)
    other_backend.run_turn(
        other_task,
        turn_kind="prompt",
        payload_text="elsewhere",
        dispatch_ref="dlg_" + "c" * 32,
        payload_ref="dlg_" + "c" * 32,
        session_ref="sess_1",
    )
    foreign = ledger.snapshot_exact(other_task, other_handle, "dlg_" + "c" * 32)
    assert foreign.state == ARSD_BINDING_ACCEPTED

    fresh = _backend(config, _Facade(), ArsdRunBindingLedger(config.binding_ledger_path))
    with pytest.raises(SpineError) as excinfo:
        fresh.attach_existing(TASK_ID, binding=foreign)
    assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT

    # (2) A stale record captured while the dispatch was still pending.
    stale_dispatch = "dlg_" + "d" * 32
    _pending_only(config, ledger, stale_dispatch)
    stale = ledger.snapshot_exact(TASK_ID, derive_arsd_backend_handle(TASK_ID), stale_dispatch)
    another = _backend(config, _Facade(), ArsdRunBindingLedger(config.binding_ledger_path))
    with pytest.raises(SpineError) as excinfo:
        another.attach_existing(TASK_ID, binding=stale)
    assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT
    # Nothing was attached in either case — no silent latest substitution.
    assert another._by_task == {}


def test_a_pre_attached_backend_still_validates_the_supplied_exact_binding(tmp_path):
    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    older, newer = _two_accepted(config, ledger)
    fresh = _backend(config, _Facade(), ArsdRunBindingLedger(config.binding_ledger_path))

    fresh.attach_existing(TASK_ID, binding=older)
    with pytest.raises(SpineError) as excinfo:
        fresh.attach_existing(TASK_ID, binding=newer)

    assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT
    assert fresh._by_task[TASK_ID].active_run_id == older.run_id


def test_the_accepted_handoff_for_a_binding_never_reads_the_latest(tmp_path):
    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    older, newer = _two_accepted(config, ledger)

    fresh = _backend(config, _Facade(), ArsdRunBindingLedger(config.binding_ledger_path))
    fresh.attach_existing(TASK_ID, binding=older)
    handoff = fresh.accepted_turn_for_binding(TASK_ID, older, session_ref="sess_1")
    assert handoff.private_locator == older.run_id
    assert handoff.result.run_ref == older.run_ref
    assert handoff.result.supervisor_status == "accepted"
    assert handoff.result.foreign_cursor is None

    with pytest.raises(SpineError) as excinfo:
        fresh.accepted_turn_for_binding(TASK_ID, newer, session_ref="sess_other")
    assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT


# --------------------------------------------------------------------------- #
# C. Sealed port restoration (I7 / A12)
# --------------------------------------------------------------------------- #
def _launch_spec():
    from sachima_supervisor.runtime_spine.launch_spec import build_launch_spec

    return build_launch_spec(
        task_id=TASK_ID,
        agent_kind="local_agent",
        mode_flags={"needs_agent": True},
        roles=("read_only",),
        refs=REFS,
    )


def test_the_port_restores_a_sealed_session_without_creating_a_backend_one(tmp_path):
    from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
        AgentRunSupervisorPort,
    )
    from sachima_supervisor.runtime_spine.registry import TaskRegistry

    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    dispatch = "dlg_" + "a" * 32
    _pending_only(config, ledger, dispatch)

    facade = _Facade()
    backend = _backend(config, facade, ArsdRunBindingLedger(config.binding_ledger_path))
    backend.rehydrate_pending_intent(TASK_ID, dispatch)

    class _NoCreate(ArsdSupervisorBackend):
        pass

    created: list[str] = []
    original = backend.create_or_attach

    def _refuse(task_id, refs):
        created.append(task_id)
        raise AssertionError("restoration must not create a backend session")

    backend.create_or_attach = _refuse  # type: ignore[method-assign]

    registry = TaskRegistry()
    port = AgentRunSupervisorPort(registry, backend)
    ref = port.restore_attached(TASK_ID, _launch_spec(), session_id="sess_1")
    assert ref.task_id == TASK_ID
    assert ref.session_id == "sess_1"
    assert created == []

    # Idempotent: a second restore attaches the same sealed session.
    again = port.restore_attached(TASK_ID, _launch_spec(), session_id="sess_1")
    assert again == ref
    attach_events = [
        event
        for event in registry.log.events_for(TASK_ID)
        if event.event_type == "agent_attached"
    ]
    assert len(attach_events) == 1
    backend.create_or_attach = original  # type: ignore[method-assign]


def test_the_port_refuses_to_restore_a_task_the_backend_cannot_attach(tmp_path):
    from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
        AgentRunSupervisorPort,
    )
    from sachima_supervisor.runtime_spine.registry import TaskRegistry

    config = _config(tmp_path)
    backend = _backend(config, _Facade(), ArsdRunBindingLedger(config.binding_ledger_path))
    port = AgentRunSupervisorPort(TaskRegistry(), backend)
    with pytest.raises(SpineError) as excinfo:
        port.restore_attached(TASK_ID, _launch_spec(), session_id="sess_1")
    assert excinfo.value.code in {RUNTIME_INVALID_SESSION, "runtime_supervisor_backend_failure"}


# --------------------------------------------------------------------------- #
# D. The Run-scoped cancel seam (§2.4 / A14)
# --------------------------------------------------------------------------- #
def test_cancel_run_issues_one_run_cancel_and_never_a_session_operation(tmp_path):
    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    facade = _Facade()
    backend = _backend(config, facade, ledger)
    backend.create_or_attach(TASK_ID, REFS)
    backend.run_turn(
        TASK_ID,
        turn_kind="prompt",
        payload_text="do it",
        dispatch_ref="dlg_" + "a" * 32,
        payload_ref="dlg_" + "a" * 32,
        session_ref="sess_1",
    )
    handle = derive_arsd_backend_handle(TASK_ID)
    facade.cancel_replies["RUN-1"] = {
        "status": "cancelled",
        "result": {
            "run_id": "RUN-1",
            "status": "cancelled",
            "final_message": "stopped",
            "truncated": False,
            "truncate_reason": None,
        },
    }
    before = list(facade.calls)
    outcome = backend.cancel_run(handle)

    assert outcome.settled is True
    assert outcome.run_status == "cancelled"
    assert outcome.result.final_message == "stopped"
    issued = facade.calls[len(before) :]
    assert issued.count("run_cancel") == 1
    assert "session_status" not in issued
    assert "session_list" not in issued

    # The task is NOT terminal: the Session is still live and reusable.
    assert backend.status(handle) == "running"
    assert backend.observe_run(handle) == "cancelled"


def test_a_cancel_without_trusted_evidence_settles_nothing(tmp_path):
    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    facade = _Facade()
    backend = _backend(config, facade, ledger)
    backend.create_or_attach(TASK_ID, REFS)
    backend.run_turn(
        TASK_ID,
        turn_kind="prompt",
        payload_text="do it",
        dispatch_ref="dlg_" + "a" * 32,
        payload_ref="dlg_" + "a" * 32,
        session_ref="sess_1",
    )
    handle = derive_arsd_backend_handle(TASK_ID)
    outcome = backend.cancel_run(handle)

    assert outcome.settled is False
    assert outcome.run_status is None
    # Uncertainty terminalizes nothing: the Run is still this task's Run.
    assert backend.status(handle) == "running"
    assert backend.observe_run(handle) == "accepted"


def test_a_cancelled_run_leaves_the_original_session_reusable(tmp_path):
    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    facade = _Facade()
    backend = _backend(config, facade, ledger)
    backend.create_or_attach(TASK_ID, REFS)
    first = backend.run_turn(
        TASK_ID,
        turn_kind="prompt",
        payload_text="first",
        dispatch_ref="dlg_" + "a" * 32,
        payload_ref="dlg_" + "a" * 32,
        session_ref="sess_1",
    )
    handle = derive_arsd_backend_handle(TASK_ID)
    facade.cancel_replies["RUN-1"] = {
        "status": "cancelled",
        "result": {
            "run_id": "RUN-1",
            "status": "cancelled",
            "final_message": "",
            "truncated": False,
            "truncate_reason": None,
        },
    }
    assert backend.cancel_run(handle).settled is True

    second = backend.run_turn(
        TASK_ID,
        turn_kind="prompt",
        payload_text="second",
        dispatch_ref="dlg_" + "b" * 32,
        payload_ref="dlg_" + "b" * 32,
        session_ref="sess_1",
    )
    assert second.result.run_ref != first.result.run_ref
    # The same ARS Session was reused verbatim: the second submit named it.
    reuse = json.loads(json.dumps(facade.calls))
    assert reuse.count("submit") == 2
    assert "session_status" in reuse


def test_cancel_run_never_reaches_the_port_kill_path(tmp_path):
    """User cancel is Run-scoped; ``kill`` is the separate task-lifecycle action."""

    config = _config(tmp_path)
    facade = _Facade()
    backend = _backend(config, facade, ArsdRunBindingLedger(config.binding_ledger_path))
    backend.create_or_attach(TASK_ID, REFS)
    backend.run_turn(
        TASK_ID,
        turn_kind="prompt",
        payload_text="do it",
        dispatch_ref="dlg_" + "a" * 32,
        payload_ref="dlg_" + "a" * 32,
        session_ref="sess_1",
    )
    handle = derive_arsd_backend_handle(TASK_ID)

    killed: list[str] = []
    original_kill = backend.kill

    def _tripwire(handle_value, reason_ref):
        killed.append(handle_value)
        return original_kill(handle_value, reason_ref)

    backend.kill = _tripwire  # type: ignore[method-assign]
    backend.cancel_run(handle)
    assert killed == []
    backend.kill = original_kill  # type: ignore[method-assign]
