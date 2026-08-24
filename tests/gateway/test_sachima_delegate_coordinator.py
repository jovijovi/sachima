"""S5 — the delegate coordinator's state machine, over the real composed bundle.

Every test here drives the **real** ``arsd`` execution bundle — one registry,
backend, port, dispatcher, ledger, and bindings store — with the daemon replaced
by an injected facade double. No socket is opened, no daemon is started, and no
AGENT is launched.

What is proven:

* every §5.2 row (no record / pending / accepted / unreadable) is reached
  through **one** exact-key snapshot, in normal, recovery, and fresh-startup
  modes, and the coordinator's ledger is the bundle's own object;
* a dispatch outcome never decides anything: a success-shaped return with no
  record is a failed admission, and an exception with an accepted record is an
  accepted Run;
* the accepted receipt settles *before* the observer is armed, once, for every
  ``SendResult`` branch;
* a repeated create/recover finds the evidence and performs no second submit;
* cancel is Run-scoped, is not issued twice, survives a crash as ``uncertain``,
  and blocks continuation until a trusted terminal closes it;
* one terminal produces one envelope, one release, and two independent sinks —
  and a completion that won a cancel race is not rewritten as cancelled;
* capacity is held by pending, accepted, unreadable, and uncertain work, and
  released exactly once;
* only a fresh graph reclassifies a found ``in_flight``.

Forbidden terms in this prose are no-leak boundary canaries only, never behavior.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import gateway.sachima_delegate as delegate_mod
from gateway.platforms.base import SendResult
from gateway.sachima_delegate import (
    SACHIMA_DELEGATE_BLOCKED,
    SACHIMA_DELEGATE_DISPATCH_FAILED,
    SACHIMA_DELEGATE_NOT_CONTINUABLE,
    SACHIMA_DELEGATE_RECOVERY_REQUIRED,
    DelegateDelivery,
    SachimaDelegateCoordinator,
)
from gateway.sachima_agent_execution_presets import (
    AGENT_EXECUTION_PRESETS_TYPE,
    ENGINEERING_BASELINE_PERMISSIONS,
    build_agent_execution_presets,
)
from gateway.sachima_delegate_state import (
    DelegateOrigin,
    DelegateStateStore,
    delegate_state_root,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
    bind_arsd_execution,
)
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import (
    ARSD_BINDING_STABLE_CODES,
    ArsdRunBindingLedger,
)
from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    ARSD_SUPERVISOR_CONFIG_TYPE,
    EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
    ArsdSupervisorConfig,
)

FINAL_MESSAGE_CANARY = "the delegated agent finished and reported this"
TASK_TEXT_CANARY = "audit the sachima delegate canary payload body"

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


class _Facade:
    """One in-memory arsd daemon, gateable and faultable at every operation."""

    def __init__(self, *, max_concurrent_runs: int = 10) -> None:
        self.max_concurrent_runs = max_concurrent_runs
        self.calls: list[str] = []
        self.submitted: list[dict[str, Any]] = []
        self.run_ids: list[str] = []
        self.terminals: dict[str, dict[str, Any]] = {}
        self.cancel_replies: dict[str, dict[str, Any]] = {}
        self.submit_gate: threading.Event | None = None
        self.submit_error: BaseException | None = None
        self.submit_swallow_ack = False
        self.run_status_error: BaseException | None = None
        self._lock = threading.RLock()
        self._seq = 0

    def submit_count(self) -> int:
        with self._lock:
            return len(self.submitted)

    def terminalize(
        self,
        index: int,
        *,
        status: str = "completed",
        final_message: str = FINAL_MESSAGE_CANARY,
        **extra: Any,
    ) -> None:
        with self._lock:
            run_id = self.run_ids[index]
            body = {
                "run_id": run_id,
                "status": status,
                "final_message": final_message,
                "truncated": False,
                "truncate_reason": None,
            }
            body.update(extra)
            self.terminals[run_id] = body

    def server_info(self) -> dict[str, Any]:
        self.calls.append("server_info")
        return {
            "version": EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
            "api_version": 3,
            "supported_api_versions": [3],
            "operations": list(V3_OPERATIONS),
            "limits": {
                "max_concurrent_runs": self.max_concurrent_runs,
                "max_frame_bytes": 1_048_576,
                "max_prompt_bytes": 262_144,
                "events_page_limit": 256,
                "event_follow_queue_size": 1024,
                "max_run_event_budget_bytes": 2_147_483_648,
            },
        }

    def submit(self, *, request_id: str, payload: Any) -> dict[str, Any]:
        self.calls.append("submit")
        with self._lock:
            self._seq += 1
            seq = self._seq
            run_id = f"RUN-delegate-{seq}"
            self.submitted.append(json.loads(json.dumps(dict(payload))))
            self.run_ids.append(run_id)
        if self.submit_gate is not None:
            self.submit_gate.wait(timeout=10)
        if self.submit_error is not None:
            raise self.submit_error
        if self.submit_swallow_ack:
            # The daemon accepted it; the reply never arrived.
            raise ConnectionError("reply lost")
        # A reuse turn names its Session and the daemon answers about that same
        # one; only a create-by-omission turn gets a new id.
        requested = dict(payload).get("request", {}).get("session_id")
        session_id = requested or f"ARSSESSIONDELEGATE{seq}"
        return {
            "run_id": run_id,
            "session_id": session_id,
            "accepted_at": f"2026-08-19T04:05:{seq:02d}+00:00",
        }

    def run_status(self, run_id: str) -> dict[str, Any]:
        self.calls.append("run_status")
        if self.run_status_error is not None:
            raise self.run_status_error
        with self._lock:
            terminal = self.terminals.get(run_id)
        body: dict[str, Any] = {"run_id": run_id, "session_id": "ARSSESSIONDELEGATE1"}
        if terminal is not None:
            body["result"] = dict(terminal)
        return body

    def run_events(self, run_id: str, *, from_seq: int, limit: int | None = None):
        self.calls.append("run_events")
        return {"run_id": run_id, "events": [], "next_from_seq": from_seq, "exhausted": True}

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
            "agent_id": "codex",
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

    def agent_list(self) -> dict[str, Any]:
        self.calls.append("agent_list")
        return {"agent_ids": list(REGISTERED_AGENT_IDS)}


class _Delivery:
    """Records every send, and can fail any of them on demand."""

    def __init__(self) -> None:
        self.receipts: list[str] = []
        self.terminals: list[str] = []
        self.notices: list[str] = []
        self.receipt_result: Any = SendResult(success=True, message_id="om_receipt")
        self.terminal_result: Any = SendResult(success=True, message_id=None)
        self.receipt_error: BaseException | None = None
        self.terminal_error: BaseException | None = None

    def channel(self, limit: int = 4000) -> DelegateDelivery:
        return DelegateDelivery(
            send_text=self._send_text,
            send_plain_text_once=self._send_once,
            limit=limit,
        )

    async def _send_text(self, text: str) -> Any:
        if "已接受任务" in text:
            self.receipts.append(text)
            if self.receipt_error is not None:
                raise self.receipt_error
            return self.receipt_result
        self.notices.append(text)
        return SendResult(success=True, message_id="om_notice")

    async def _send_once(self, text: str) -> Any:
        self.terminals.append(text)
        if self.terminal_error is not None:
            raise self.terminal_error
        return self.terminal_result


def _config(tmp_path: Path, **overrides: Any) -> ArsdSupervisorConfig:
    private = tmp_path / "private"
    private.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {
        "type": ARSD_SUPERVISOR_CONFIG_TYPE,
        "approval_ref": "approval_delegate_offline",
        "owner": "sachima_host",
        "namespace": "sachima_tasks",
        "socket_path": str(private / "arsd.sock"),
        "binding_ledger_path": str(private / "arsd-run-bindings.json"),
        "agent_by_policy_ref": {"policy_codex": "codex"},
        "model_by_policy_ref": {"policy_model": "claude-opus-5"},
        "effort_by_policy_ref": {"policy_effort": "xhigh"},
        "workspace_by_ref": {"ws_delegate": str(private / "workspace")},
        "run_limits_by_policy_ref": {
            "policy_limits": {
                "startup_timeout_seconds": 60.0,
                "turn_timeout_seconds": 600.0,
                "cancel_grace_seconds": 10.0,
                "max_stderr_bytes": 262_144,
                "max_event_bytes": 65_536,
                "max_events": 10_000,
            }
        },
        "grant_ref": "grant_author_v1",
        "grant_hash": "sha256:" + "a" * 64,
        "grant_role_hash": "sha256:" + "b" * 64,
        "grant_capabilities": ("execute", "read", "search"),
        "grant_by_policy_ref": {
            "policy_codex": ENGINEERING_BASELINE_PERMISSIONS,
            "policy_cursor": ENGINEERING_BASELINE_PERMISSIONS,
        },
        "mcp_snapshot_hashes": ("sha256:" + "c" * 64,),
        "credential_refs": ("cred_author",),
        "evidence_policy_hash": "sha256:" + "d" * 64,
        "recovery_policy_hash": "sha256:" + "e" * 64,
        "enabled": True,
    }
    kwargs.update(overrides)
    return ArsdSupervisorConfig(**kwargs)


def _origin(session_id: str = "20260819_000000_abcd1234") -> DelegateOrigin:
    return DelegateOrigin(
        platform="feishu",
        chat_id="oc_chat",
        thread_id=None,
        session_key="feishu:oc_chat",
        session_id=session_id,
    )


#: One preset per canonical AGENT this offline host may run. It carries the
#: engineering baseline (read + search + execute) and nothing that could pick
#: an AGENT — the tests name the one they mean.
def _catalog(config, *agent_ids: str):
    return build_agent_execution_presets(
        {
            "type": AGENT_EXECUTION_PRESETS_TYPE,
            "presets": [
                {
                    "agent_id": agent_id,
                    "workspace_ref": "ws_delegate",
                    "agent_policy_ref": f"policy_{agent_id}",
                    "model_policy_ref": "policy_model",
                    "effort_policy_ref": "policy_effort",
                    "run_limits_policy_ref": "policy_limits",
                    "permissions": list(ENGINEERING_BASELINE_PERMISSIONS),
                }
                for agent_id in (agent_ids or ("codex",))
            ],
        },
        config,
    )


def _coordinator(tmp_path: Path, *, facade=None, delivery=None, **config_overrides):
    facade = _Facade() if facade is None else facade
    config = _config(tmp_path, **config_overrides)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    bundle = bind_arsd_execution(
        config,
        facade=facade,
        ledger=ledger,
        payload_resolver=delegate_mod.delegate_payload_resolver(),
    )
    coordinator = SachimaDelegateCoordinator(
        bundle,
        config,
        presets=_catalog(config),
        state=DelegateStateStore(delegate_state_root(config.binding_ledger_path)),
        delivery_factory=(lambda _origin: delivery.channel()) if delivery else None,
        observe_interval=0.01,
    )
    delegate_mod._coordinator = coordinator
    return coordinator, facade


@pytest.fixture(autouse=True)
def _unbind():
    delegate_mod.unbind_delegate_coordinator()
    yield
    delegate_mod.unbind_delegate_coordinator()


def _preset(coordinator):
    (preset,) = coordinator.presets.presets
    return preset


async def _until(predicate, *, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


async def _await_composed(coro, *, timeout=10.0):
    task = asyncio.create_task(coro)
    assert await _until(task.done, timeout=timeout)
    return await task


# --------------------------------------------------------------------------- #
# A. The durable prefix and the accepted row (I4 / §5.2 / A6, A11)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_created_task_is_durable_before_anything_could_submit(tmp_path):
    facade = _Facade()
    facade.submit_gate = threading.Event()
    delivery = _Delivery()
    coordinator, _ = _coordinator(tmp_path, facade=facade, delivery=delivery)

    created = asyncio.create_task(
        coordinator.create(
            task_text=TASK_TEXT_CANARY,
            preset=_preset(coordinator),
            origin=_origin(),
            delivery=delivery.channel(),
        )
    )
    assert await _until(lambda: facade.submit_count() == 1)

    # The submit is parked *inside* the daemon; everything identity-shaped is
    # already on disk.
    turns = coordinator.state.list_turns()
    assert len(turns) == 1
    (turn,) = turns
    assert turn.lifecycle == "prepared"
    assert turn.ledger_key == (turn.task_id, turn.backend_handle, turn.dispatch_ref)
    assert coordinator.state.read_payload(turn.payload_ref) == TASK_TEXT_CANARY
    assert coordinator.state.read_task(turn.task_ref).current_turn_key == turn.turn_key

    facade.submit_gate.set()
    outcome = await created
    assert outcome.lifecycle == "admitted"
    assert outcome.turn_ref is not None


@pytest.mark.asyncio
async def test_the_accepted_receipt_carries_the_requested_triple_and_settles_once(
    tmp_path,
):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    assert outcome.receipt == "confirmed"
    assert len(delivery.receipts) == 1
    receipt = delivery.receipts[0]
    assert "codex" in receipt
    assert "claude-opus-5" in receipt
    assert "xhigh" in receipt
    assert TASK_TEXT_CANARY not in receipt

    turn = coordinator.state.read_turn(outcome.turn_key)
    assert turn.receipt == "confirmed"
    assert turn.receipt_message_id == "om_receipt"
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_the_receipt_settles_before_the_observer_is_armed(tmp_path):
    """A terminal must never be able to arrive before the acceptance it answers."""

    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    order: list[str] = []

    original = coordinator._arm_observer

    def _record(turn_key):
        order.append("observer")
        return original(turn_key)

    coordinator._arm_observer = _record  # type: ignore[method-assign]

    async def _send_text(text: str):
        order.append("receipt")
        return SendResult(success=True, message_id="om_receipt")

    channel = DelegateDelivery(
        send_text=_send_text, send_plain_text_once=delivery._send_once, limit=4000
    )
    await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=channel,
    )
    assert order == ["receipt", "observer"]
    facade.terminalize(0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result,expected",
    [
        (SendResult(success=True, message_id="om_1"), "confirmed"),
        (SendResult(success=True, message_id=None), "confirmed"),
        (SendResult(success=False, error="nope"), "failed"),
        ("not a send result", "uncertain"),
    ],
)
async def test_every_send_branch_settles_the_receipt_through_the_real_closure(
    tmp_path, result, expected
):
    delivery = _Delivery()
    delivery.receipt_result = result
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    assert outcome.receipt == expected
    assert coordinator.state.read_turn(outcome.turn_key).receipt == expected
    # Whatever the receipt did, the Run was still admitted and observed.
    assert outcome.lifecycle == "admitted"
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_a_raising_receipt_send_is_uncertain_and_does_not_block_the_run(tmp_path):
    delivery = _Delivery()
    delivery.receipt_error = RuntimeError("chat oc_secret rejected")
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    assert outcome.receipt == "uncertain"
    assert outcome.lifecycle == "admitted"
    facade.terminalize(0)


# --------------------------------------------------------------------------- #
# B. Evidence, not return codes (I5 / A8)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_coordinator_classifies_through_the_bundles_own_ledger(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    assert coordinator.ledger is coordinator.binding.ledger
    assert coordinator.binding.backend._ledger is coordinator.ledger

    snapshots: list[tuple] = []
    original = coordinator.ledger.snapshot_exact

    def _spy(task_id, handle, dispatch):
        snapshots.append((task_id, handle, dispatch))
        return original(task_id, handle, dispatch)

    coordinator.ledger.snapshot_exact = _spy  # type: ignore[method-assign]

    resolves: list[str] = []
    original_resolve = coordinator.ledger.resolve
    original_pending = coordinator.ledger.resolve_pending

    def _resolve_spy(*args, **kwargs):
        resolves.append("resolve")
        return original_resolve(*args, **kwargs)

    def _pending_spy(*args, **kwargs):
        resolves.append("resolve_pending")
        return original_pending(*args, **kwargs)

    coordinator.ledger.resolve = _resolve_spy  # type: ignore[method-assign]
    coordinator.ledger.resolve_pending = _pending_spy  # type: ignore[method-assign]

    await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    # A preflight snapshot and a post-operation snapshot; no classification via
    # the two-read pair.
    assert len(snapshots) >= 2
    assert resolves == []
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_a_success_shaped_dispatch_with_no_record_is_a_failed_admission(tmp_path):
    """The classifier is the only exit — a cheerful return value is not one."""

    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)

    def _lying_dispatch(request):
        from sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher import (
            TurnDispatchOutcome,
        )

        return TurnDispatchOutcome(
            task_id=request.task_id,
            session_id=request.session_id,
            turn_ref="run_deadbeef",
            supervisor_status="accepted",
            artifact_ref="run_deadbeef",
            error_code=None,
        )

    coordinator.binding.dispatcher.dispatch = _lying_dispatch  # type: ignore[method-assign]
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    assert outcome.lifecycle == "admission_failed"
    assert outcome.diagnostic == SACHIMA_DELEGATE_DISPATCH_FAILED
    assert delivery.receipts == []
    assert facade.submit_count() == 0
    assert coordinator.capacity.held() == 0
    assert coordinator.state.list_turns() == ()


@pytest.mark.asyncio
async def test_a_lost_ack_leaves_a_pending_intent_that_holds_its_permit(tmp_path):
    facade = _Facade()
    facade.submit_swallow_ack = True
    delivery = _Delivery()
    coordinator, _ = _coordinator(tmp_path, facade=facade, delivery=delivery)

    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    assert outcome.lifecycle == "recovery_required"
    assert outcome.diagnostic == SACHIMA_DELEGATE_RECOVERY_REQUIRED
    assert delivery.receipts == []
    # The permit stays held: the daemon may hold a Run nobody can name.
    assert coordinator.capacity.held() == 1
    assert coordinator.capacity.holds(outcome.turn_key)


@pytest.mark.asyncio
async def test_an_unreadable_ledger_blocks_and_keeps_everything(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    ledger_path = Path(coordinator.ledger.path)

    damaged = b'{"type": "sachima.runtime_spine.arsd_run_binding_ledger.v1", "bind'

    def _damage_then_dispatch(request):
        ledger_path.write_bytes(damaged)
        raise RuntimeError("dispatch blew up")

    coordinator.binding.dispatcher.dispatch = _damage_then_dispatch  # type: ignore[method-assign]
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    assert outcome.lifecycle == "blocked"
    # The ledger's own stable code is preserved rather than flattened: it says
    # *why* the evidence could not be read, and it is still only a code.
    assert outcome.diagnostic in (
        ARSD_BINDING_STABLE_CODES | {SACHIMA_DELEGATE_BLOCKED}
    )
    assert "bind" not in (outcome.diagnostic or "").replace("binding", "")
    assert delivery.receipts == []
    assert coordinator.capacity.held() == 1
    assert ledger_path.read_bytes() == damaged
    assert coordinator.state.read_turn(outcome.turn_key) is not None


@pytest.mark.asyncio
async def test_a_second_create_entry_over_existing_evidence_never_submits_twice(
    tmp_path,
):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    assert facade.submit_count() == 1

    # Re-driving the same turn finds accepted evidence and closes it again,
    # without a second submit or a second receipt.
    again = await coordinator._exclusive(
        outcome.turn_key,
        lambda: coordinator._drive(outcome.turn_key, mode="dispatch", delivery=delivery.channel()),
    )
    assert again.lifecycle == "admitted"
    assert facade.submit_count() == 1
    assert len(delivery.receipts) == 1
    facade.terminalize(0)


# --------------------------------------------------------------------------- #
# C. Terminal closure and the two sinks (I8 / A16)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_one_terminal_makes_one_envelope_one_release_and_two_sinks(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    facade.terminalize(0)
    assert await _until(lambda: len(delivery.terminals) == 1)

    event = coordinator.state.result_for_turn(outcome.turn_key)
    assert event is not None
    assert event.terminal == "completed"
    assert event.im_sink == "confirmed"
    assert event.hermes_sink == "pending"
    assert coordinator.state.read_full_result(event.full_result_ref) == FINAL_MESSAGE_CANARY
    body = delivery.terminals[0]
    assert event.full_result_ref in body
    assert FINAL_MESSAGE_CANARY in body

    # Exactly one release, and the private text is gone.
    assert coordinator.capacity.held() == 0
    assert coordinator.capacity.release(outcome.turn_key) is False
    assert len(coordinator.state.list_results()) == 1

    # The Hermes sink is still owed, and becomes visible at the next turn.
    lines = coordinator.pending_hermes_context(_origin().session_id)
    assert len(lines) == 1 and event.full_result_ref in lines[0]
    assert coordinator.confirm_hermes_context(_origin().session_id) == 1
    assert coordinator.state.read_result(event.event_id).hermes_sink == "confirmed"


@pytest.mark.asyncio
async def test_an_im_delivery_failure_never_erases_the_hermes_projection(tmp_path):
    delivery = _Delivery()
    delivery.terminal_result = SendResult(success=False, error="down")
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    facade.terminalize(0)
    assert await _until(lambda: len(delivery.terminals) == 1)

    event = coordinator.state.result_for_turn(outcome.turn_key)
    assert event.im_sink == "failed"
    assert event.hermes_sink == "pending"
    assert coordinator.pending_hermes_context(_origin().session_id)
    # A failed IM sink still released the permit: the result is durable.
    assert coordinator.capacity.held() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected",
    [
        ("completed", "completed"),
        ("failed", "failed"),
        ("cancelled", "cancelled"),
        ("timed_out", "failed"),
        ("unknown", "failed"),
    ],
)
async def test_every_ars_terminal_reaches_one_of_the_three_envelope_terminals(
    tmp_path, status, expected
):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    facade.terminalize(0, status=status)
    assert await _until(lambda: len(delivery.terminals) == 1)
    assert coordinator.state.result_for_turn(outcome.turn_key).terminal == expected


@pytest.mark.asyncio
async def test_observation_failure_does_not_release_the_permit(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    facade.run_status_error = ConnectionError("socket gone")
    await asyncio.sleep(0.1)
    assert coordinator.capacity.holds(outcome.turn_key)
    assert delivery.terminals == []

    facade.run_status_error = None
    facade.terminalize(0)
    assert await _until(lambda: len(delivery.terminals) == 1)
    assert coordinator.capacity.held() == 0


# --------------------------------------------------------------------------- #
# D. Cancel, continuation, and the Run/Session split (§2.4 / A14)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_proven_cancel_settles_once_and_leaves_the_task_continuable(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    facade.cancel_replies["RUN-delegate-1"] = {
        "status": "cancelled",
        "result": {
            "run_id": "RUN-delegate-1",
            "status": "cancelled",
            "final_message": "stopped early",
            "truncated": False,
            "truncate_reason": None,
        },
    }
    cancelled = await coordinator.cancel(outcome.task_ref)
    assert cancelled.lifecycle == "terminal"
    assert cancelled.cancellation == "settled"
    assert cancelled.terminal == "cancelled"
    assert facade.calls.count("run_cancel") == 1

    # Same task, same Sessions, same AGENT — a later Run, not a new task.
    followup = await coordinator.continue_task(outcome.task_ref, "carry on")
    assert followup.lifecycle == "admitted"
    assert followup.task_ref == outcome.task_ref
    binding = coordinator.state.read_task(outcome.task_ref)
    assert len(binding.turn_keys) == 2
    assert binding.spine_session_id == coordinator.state.read_turn(
        followup.turn_key
    ).spine_session_id
    assert facade.submit_count() == 2
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_an_unproven_cancel_is_uncertain_and_blocks_continuation(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    first = await coordinator.cancel(outcome.task_ref)
    assert first.cancellation == "uncertain"
    assert coordinator.capacity.holds(outcome.turn_key)

    # A repeated cancel joins the existing state; it issues no second cancel.
    issued = facade.calls.count("run_cancel")
    second = await coordinator.cancel(outcome.task_ref)
    assert second.cancellation == "uncertain"
    assert facade.calls.count("run_cancel") == issued

    blocked = await coordinator.continue_task(outcome.task_ref, "carry on")
    assert blocked.diagnostic == SACHIMA_DELEGATE_NOT_CONTINUABLE
    assert facade.submit_count() == 1

    # Later observation settles it through the one canonical closure.
    facade.terminalize(0)
    settled = await coordinator.status(outcome.task_ref)
    assert settled.lifecycle == "terminal"
    assert settled.cancellation == "settled"
    assert coordinator.capacity.held() == 0


@pytest.mark.asyncio
async def test_a_completion_that_won_the_cancel_race_is_not_rewritten(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    # The Run finished before the cancel could land.
    facade.terminalize(0, status="completed")
    facade.cancel_replies["RUN-delegate-1"] = {
        "status": "completed",
        "result": dict(facade.terminals["RUN-delegate-1"]),
    }
    cancelled = await coordinator.cancel(outcome.task_ref)
    assert cancelled.terminal == "completed"
    assert coordinator.state.result_for_turn(outcome.turn_key).terminal == "completed"


@pytest.mark.asyncio
async def test_continuation_is_refused_while_the_run_is_still_live(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    refused = await coordinator.continue_task(outcome.task_ref, "and also this")
    assert refused.diagnostic == SACHIMA_DELEGATE_NOT_CONTINUABLE
    assert facade.submit_count() == 1
    facade.terminalize(0)


# --------------------------------------------------------------------------- #
# E. Explicit recovery (I5 / A13)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_explicit_recovery_resends_the_identical_request_exactly_once(tmp_path):
    facade = _Facade()
    facade.submit_swallow_ack = True
    delivery = _Delivery()
    coordinator, _ = _coordinator(tmp_path, facade=facade, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    assert outcome.lifecycle == "recovery_required"
    first_payload = facade.submitted[0]

    facade.submit_swallow_ack = False
    recovered = await coordinator.recover(outcome.task_ref, delivery=delivery.channel())
    assert recovered.lifecycle == "admitted"
    assert facade.submit_count() == 2
    # The identical frozen payload went back out.
    assert facade.submitted[1] == first_payload
    assert len(delivery.receipts) == 1
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_recovery_over_accepted_evidence_closes_without_submitting(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    recovered = await coordinator.recover(outcome.task_ref, delivery=delivery.channel())
    assert recovered.lifecycle == "admitted"
    assert facade.submit_count() == 1
    assert len(delivery.receipts) == 1
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_two_concurrent_recover_calls_serialize_into_one_closure(tmp_path):
    facade = _Facade()
    facade.submit_swallow_ack = True
    delivery = _Delivery()
    coordinator, _ = _coordinator(tmp_path, facade=facade, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    facade.submit_swallow_ack = False

    first, second = await asyncio.gather(
        coordinator.recover(outcome.task_ref, delivery=delivery.channel()),
        coordinator.recover(outcome.task_ref, delivery=delivery.channel()),
    )
    assert {first.lifecycle, second.lifecycle} == {"admitted"}
    # One recovery submit, one receipt, one observer.
    assert facade.submit_count() == 2
    assert len(delivery.receipts) == 1
    assert coordinator.active_count() <= 1
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_cancelling_a_waiter_cannot_release_the_section_early(tmp_path):
    """The owner keeps going; the exclusion it holds keeps holding."""

    facade = _Facade()
    facade.submit_gate = threading.Event()
    delivery = _Delivery()
    coordinator, _ = _coordinator(tmp_path, facade=facade, delivery=delivery)

    waiter = asyncio.create_task(
        coordinator.create(
            task_text=TASK_TEXT_CANARY,
            preset=_preset(coordinator),
            origin=_origin(),
            delivery=delivery.channel(),
        )
    )
    assert await _until(lambda: facade.submit_count() == 1)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    facade.submit_gate.set()
    # The owner completes the admission anyway: the durable commit, the receipt,
    # and the observer all still happen.
    assert await _until(lambda: len(delivery.receipts) == 1, timeout=10)
    (turn,) = coordinator.state.list_turns()
    assert turn.lifecycle == "admitted"
    assert turn.receipt == "confirmed"
    facade.terminalize(0)


# --------------------------------------------------------------------------- #
# F. Fresh-startup restoration (I3, I7 / A10, A12)
# --------------------------------------------------------------------------- #
def _recompose(tmp_path: Path, *, facade, delivery):
    """A genuinely fresh composition graph over the same durable state."""

    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    bundle = bind_arsd_execution(
        config,
        facade=facade,
        ledger=ledger,
        payload_resolver=delegate_mod.delegate_payload_resolver(),
    )
    coordinator = SachimaDelegateCoordinator(
        bundle,
        config,
        presets=_catalog(config),
        state=DelegateStateStore(delegate_state_root(config.binding_ledger_path)),
        delivery_factory=lambda _origin: delivery.channel(),
        observe_interval=0.01,
    )
    delegate_mod._coordinator = coordinator
    return coordinator


@pytest.mark.asyncio
async def test_a_restart_restores_an_accepted_turn_without_submitting_again(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    for observer in list(coordinator._observers.values()):
        observer.cancel()

    fresh_facade = _Facade()
    fresh_facade.run_ids = list(facade.run_ids)
    fresh = _recompose(tmp_path, facade=fresh_facade, delivery=delivery)
    baseline_submits = fresh_facade.submit_count()

    report = await fresh.restore()
    assert report["restored"] == 1
    assert fresh_facade.submit_count() == baseline_submits == 0
    assert fresh.capacity.holds(outcome.turn_key)
    turn = fresh.state.read_turn(outcome.turn_key)
    assert turn.lifecycle == "admitted"
    # The receipt was already confirmed before the restart; it is not resent.
    assert turn.receipt == "confirmed"
    assert len(delivery.receipts) == 1

    fresh_facade.terminals["RUN-delegate-1"] = {
        "run_id": "RUN-delegate-1",
        "status": "completed",
        "final_message": FINAL_MESSAGE_CANARY,
        "truncated": False,
        "truncate_reason": None,
    }
    assert await _until(lambda: len(delivery.terminals) == 1)
    assert fresh.capacity.held() == 0


@pytest.mark.asyncio
async def test_restart_finishes_a_result_event_left_before_turn_terminalization(tmp_path):
    """A crash between event write and turn update reuses one event identity."""

    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await _await_composed(
        coordinator.create(
            task_text=TASK_TEXT_CANARY,
            preset=_preset(coordinator),
            origin=_origin(),
            delivery=delivery.channel(),
        )
    )
    observers = list(coordinator._observers.values())
    for observer in observers:
        observer.cancel()
    await asyncio.gather(*observers, return_exceptions=True)

    original_update = coordinator.state.update_turn

    def _crash_before_terminal_turn(turn_key, **fields):
        if fields.get("lifecycle") == "terminal":
            raise RuntimeError("simulated process crash")
        return original_update(turn_key, **fields)

    coordinator.state.update_turn = _crash_before_terminal_turn  # type: ignore[method-assign]
    terminal = SimpleNamespace(
        status="completed",
        final_message=FINAL_MESSAGE_CANARY,
        truncated=False,
        truncate_reason=None,
    )
    with pytest.raises(RuntimeError, match="simulated process crash"):
        await coordinator._exclusive(
            outcome.turn_key,
            lambda: coordinator._close_terminal(outcome.turn_key, terminal),
        )

    (event_before,) = coordinator.state.list_results()
    assert coordinator.state.read_turn(outcome.turn_key).lifecycle == "admitted"
    assert delivery.terminals == []

    fresh = _recompose(tmp_path, facade=_Facade(), delivery=delivery)
    await _await_composed(fresh.restore())

    (event_after,) = fresh.state.list_results()
    assert event_after.event_id == event_before.event_id
    assert fresh.state.read_turn(outcome.turn_key).lifecycle == "terminal"
    assert len(delivery.terminals) == 1
    assert fresh.capacity.held() == 0


@pytest.mark.asyncio
async def test_accepted_identity_restore_failure_stays_blocked_without_observer(tmp_path):
    delivery = _Delivery()
    coordinator, _facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await _await_composed(
        coordinator.create(
            task_text=TASK_TEXT_CANARY,
            preset=_preset(coordinator),
            origin=_origin(),
            delivery=delivery.channel(),
        )
    )
    observers = list(coordinator._observers.values())
    for observer in observers:
        observer.cancel()
    await asyncio.gather(*observers, return_exceptions=True)

    fresh_facade = _Facade()
    fresh = _recompose(tmp_path, facade=fresh_facade, delivery=delivery)
    fresh.binding.backend.attach_existing = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("mismatch"))
    )
    await _await_composed(fresh.restore())

    turn = fresh.state.read_turn(outcome.turn_key)
    assert turn.lifecycle == "blocked"
    assert turn.diagnostic == SACHIMA_DELEGATE_BLOCKED
    assert fresh.active_count() == 0
    assert len(delivery.receipts) == 1
    baseline = list(fresh_facade.calls)
    status = await fresh.status(outcome.task_ref)
    assert status.diagnostic == SACHIMA_DELEGATE_BLOCKED
    assert fresh_facade.calls == baseline


@pytest.mark.asyncio
async def test_pending_identity_restore_failure_blocks_recovery(tmp_path):
    facade = _Facade()
    facade.submit_swallow_ack = True
    delivery = _Delivery()
    coordinator, _ = _coordinator(tmp_path, facade=facade, delivery=delivery)
    outcome = await _await_composed(
        coordinator.create(
            task_text=TASK_TEXT_CANARY,
            preset=_preset(coordinator),
            origin=_origin(),
            delivery=delivery.channel(),
        )
    )
    assert outcome.lifecycle == "recovery_required"

    fresh_facade = _Facade()
    fresh = _recompose(tmp_path, facade=fresh_facade, delivery=delivery)
    fresh.binding.backend.rehydrate_pending_intent = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("mismatch"))
    )
    await _await_composed(fresh.restore())

    turn = fresh.state.read_turn(outcome.turn_key)
    assert turn.lifecycle == "blocked"
    baseline = fresh_facade.submit_count()
    recovered = await fresh.recover(outcome.task_ref)
    assert recovered.diagnostic == SACHIMA_DELEGATE_BLOCKED
    assert fresh_facade.submit_count() == baseline == 0


@pytest.mark.asyncio
async def test_terminal_identity_restore_failure_blocks_continuation(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await _await_composed(
        coordinator.create(
            task_text=TASK_TEXT_CANARY,
            preset=_preset(coordinator),
            origin=_origin(),
            delivery=delivery.channel(),
        )
    )
    facade.terminalize(0)
    assert await _until(
        lambda: coordinator.state.read_turn(outcome.turn_key).lifecycle == "terminal"
    )

    fresh_facade = _Facade()
    fresh = _recompose(tmp_path, facade=fresh_facade, delivery=delivery)
    fresh.binding.backend.attach_existing = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("mismatch"))
    )
    await _await_composed(fresh.restore())

    turn = fresh.state.read_turn(outcome.turn_key)
    assert turn.lifecycle == "terminal"
    assert turn.diagnostic == SACHIMA_DELEGATE_BLOCKED
    continued = await fresh.continue_task(outcome.task_ref, "must not run")
    assert continued.diagnostic == SACHIMA_DELEGATE_BLOCKED
    assert fresh.result(outcome.task_ref)["diagnostic"] == SACHIMA_DELEGATE_BLOCKED
    assert fresh_facade.submit_count() == 0


@pytest.mark.asyncio
async def test_a_restart_turns_an_in_flight_receipt_into_uncertain_without_resending(
    tmp_path,
):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    for observer in list(coordinator._observers.values()):
        observer.cancel()
    coordinator.state.update_turn(outcome.turn_key, receipt="in_flight")

    fresh = _recompose(tmp_path, facade=_Facade(), delivery=delivery)
    await fresh.restore()
    assert fresh.state.read_turn(outcome.turn_key).receipt == "uncertain"
    assert len(delivery.receipts) == 1


@pytest.mark.asyncio
async def test_a_restart_restores_a_pending_intent_and_reserves_its_permit(tmp_path):
    facade = _Facade()
    facade.submit_swallow_ack = True
    delivery = _Delivery()
    coordinator, _ = _coordinator(tmp_path, facade=facade, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    assert outcome.lifecycle == "recovery_required"

    fresh_facade = _Facade()
    fresh = _recompose(tmp_path, facade=fresh_facade, delivery=delivery)
    await fresh.restore()

    assert fresh_facade.submit_count() == 0
    assert fresh.capacity.holds(outcome.turn_key)
    assert fresh.state.read_turn(outcome.turn_key).lifecycle == "recovery_required"
    assert delivery.receipts == []
    # No read-model source is bound for a pending dispatch: there is no Run this
    # process can name, so there is nothing to read.
    turn = fresh.state.read_turn(outcome.turn_key)
    with pytest.raises(Exception):
        fresh.binding.bindings.resolve(turn.task_id, turn.spine_session_id)
    # And no observer was armed either.
    assert fresh.active_count() == 0


@pytest.mark.asyncio
async def test_a_restart_restores_a_crashed_cancel_as_uncertain(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    for observer in list(coordinator._observers.values()):
        observer.cancel()
    coordinator.state.update_turn(outcome.turn_key, cancellation="in_flight")

    fresh_facade = _Facade()
    fresh = _recompose(tmp_path, facade=fresh_facade, delivery=delivery)
    await fresh.restore()
    assert fresh.state.read_turn(outcome.turn_key).cancellation == "uncertain"
    # No second cancel was issued, and continuation stays refused.
    assert fresh_facade.calls.count("run_cancel") == 0
    blocked = await fresh.continue_task(outcome.task_ref, "carry on")
    assert blocked.diagnostic == SACHIMA_DELEGATE_NOT_CONTINUABLE


@pytest.mark.asyncio
async def test_a_restart_retries_a_pending_sink_once_with_the_same_event_id(tmp_path):
    delivery = _Delivery()
    coordinator, _facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await _await_composed(
        coordinator.create(
            task_text=TASK_TEXT_CANARY,
            preset=_preset(coordinator),
            origin=_origin(),
            delivery=delivery.channel(),
        )
    )
    observers = list(coordinator._observers.values())
    for observer in observers:
        observer.cancel()
    await asyncio.gather(*observers, return_exceptions=True)

    async def _crash_before_im_send(_event, _turn):
        raise RuntimeError("simulated process crash")

    coordinator._reconcile_im_sink = _crash_before_im_send  # type: ignore[method-assign]
    terminal = SimpleNamespace(
        status="completed",
        final_message=FINAL_MESSAGE_CANARY,
        truncated=False,
        truncate_reason=None,
    )
    with pytest.raises(RuntimeError, match="simulated process crash"):
        await coordinator._exclusive(
            outcome.turn_key,
            lambda: coordinator._close_terminal(outcome.turn_key, terminal),
        )

    event = coordinator.state.result_for_turn(outcome.turn_key)
    assert event.im_sink == "pending"
    assert delivery.terminals == []

    fresh = _recompose(tmp_path, facade=_Facade(), delivery=delivery)
    await _await_composed(fresh.restore())

    restored = fresh.state.read_result(event.event_id)
    assert restored.im_sink == "confirmed"
    assert len(delivery.terminals) == 1
    assert fresh.state.list_results() == (restored,)
    assert restored.event_id == event.event_id
    assert fresh.capacity.held() == 0


@pytest.mark.asyncio
async def test_a_restart_marks_an_in_flight_sink_uncertain_without_resending(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await _await_composed(
        coordinator.create(
            task_text=TASK_TEXT_CANARY,
            preset=_preset(coordinator),
            origin=_origin(),
            delivery=delivery.channel(),
        )
    )
    facade.terminalize(0)
    assert await _until(lambda: len(delivery.terminals) == 1)
    assert await _until(lambda: coordinator.active_count() == 0)
    event = coordinator.state.result_for_turn(outcome.turn_key)
    coordinator.state.update_result(
        event.event_id, im_sink="in_flight", hermes_sink="in_flight"
    )

    fresh = _recompose(tmp_path, facade=_Facade(), delivery=delivery)
    await _await_composed(fresh.restore())
    restored = fresh.state.read_result(event.event_id)
    assert restored.im_sink == "uncertain"
    assert restored.hermes_sink == "pending"
    assert len(delivery.terminals) == 1
    assert fresh.state.list_results() == (restored,)
    assert restored.event_id == event.event_id
    # A terminal turn reserves no permit.
    assert fresh.capacity.held() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("sink_state", ["failed", "uncertain"])
async def test_a_restart_does_not_retry_failed_or_uncertain_sinks(tmp_path, sink_state):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await _await_composed(
        coordinator.create(
            task_text=TASK_TEXT_CANARY,
            preset=_preset(coordinator),
            origin=_origin(),
            delivery=delivery.channel(),
        )
    )
    facade.terminalize(0)
    assert await _until(lambda: len(delivery.terminals) == 1)
    assert await _until(lambda: coordinator.active_count() == 0)
    event = coordinator.state.result_for_turn(outcome.turn_key)
    coordinator.state.update_result(event.event_id, im_sink=sink_state)

    fresh = _recompose(tmp_path, facade=_Facade(), delivery=delivery)
    await _await_composed(fresh.restore())

    restored = fresh.state.read_result(event.event_id)
    assert restored.im_sink == sink_state
    assert len(delivery.terminals) == 1
    assert restored.event_id == event.event_id


@pytest.mark.asyncio
@pytest.mark.parametrize("sink_state", ["failed", "uncertain"])
async def test_status_explicitly_retries_failed_or_uncertain_sink_with_same_event_id(
    tmp_path, sink_state
):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await _await_composed(
        coordinator.create(
            task_text=TASK_TEXT_CANARY,
            preset=_preset(coordinator),
            origin=_origin(),
            delivery=delivery.channel(),
        )
    )
    facade.terminalize(0)
    assert await _until(lambda: len(delivery.terminals) == 1)
    assert await _until(lambda: coordinator.active_count() == 0)
    event = coordinator.state.result_for_turn(outcome.turn_key)
    coordinator.state.update_result(event.event_id, im_sink=sink_state)

    fresh = _recompose(tmp_path, facade=_Facade(), delivery=delivery)
    await _await_composed(fresh.restore())
    assert len(delivery.terminals) == 1

    settled = await fresh.status(outcome.task_ref)

    restored = fresh.state.read_result(event.event_id)
    assert settled.terminal == event.terminal
    assert restored.im_sink == "confirmed"
    assert len(delivery.terminals) == 2
    assert fresh.state.list_results() == (restored,)
    assert restored.event_id == event.event_id


@pytest.mark.asyncio
async def test_only_a_fresh_graph_reclassifies_a_found_in_flight(tmp_path):
    delivery = _Delivery()
    coordinator, facade = _coordinator(tmp_path, delivery=delivery)
    outcome = await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    coordinator.state.update_turn(outcome.turn_key, receipt="in_flight")

    # A live graph seeing in_flight retains it: it neither resends nor rewrites.
    again = await coordinator._exclusive(
        outcome.turn_key,
        lambda: coordinator._drive(outcome.turn_key, mode="reconcile", delivery=delivery.channel()),
    )
    assert again.receipt == "in_flight"
    assert len(delivery.receipts) == 1
    facade.terminalize(0)


# --------------------------------------------------------------------------- #
# G. Capacity (I7 / A15)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_capacity_bounds_admissions_and_says_so_only_when_it_waits(tmp_path):
    facade = _Facade(max_concurrent_runs=1)
    delivery = _Delivery()
    coordinator, _ = _coordinator(tmp_path, facade=facade, delivery=delivery)
    first = await coordinator.create(
        task_text="first task",
        preset=_preset(coordinator),
        origin=_origin(),
        delivery=delivery.channel(),
    )
    assert delivery.notices == []
    assert coordinator.capacity.held() == 1

    waiting = asyncio.create_task(
        coordinator.create(
            task_text="second task",
            preset=_preset(coordinator),
            origin=_origin(),
            delivery=delivery.channel(),
        )
    )
    assert await _until(lambda: len(delivery.notices) == 1)
    assert facade.submit_count() == 1

    facade.terminalize(0)
    second = await asyncio.wait_for(waiting, timeout=10)
    assert second.lifecycle == "admitted"
    assert facade.submit_count() == 2
    facade.terminalize(1)
