"""Sachima ``/delegate`` — process-local payload claim-check and coordinator.

Milestone A, task 2 (A1). The host holds the delegated task text; the
dispatcher only ever sees an opaque ref. What is proven here:

* a put/resolve round trip returns the exact text, byte for byte;
* the ref is **opaque** — it never carries the task text, in any casing or
  fragment, and it is shaped like a spine-safe id so it can travel as a
  ``TurnDispatchRequest.payload_ref`` without further sanitizing;
* a discarded ref stops resolving, and discarding twice is not an error;
* an unknown / malformed ref fails with the stable code **and nothing else**
  — the rejected ref is never echoed back through the failure.

Everything is pure local/offline: no Gateway process, adapter, socket, daemon,
or AGENT is started. Forbidden terms in this prose are no-leak boundary
canaries only, never behavior.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from pathlib import Path
from typing import Any

import pytest

import gateway.sachima_delegate as delegate_mod
from gateway.sachima_delegate import (
    _MAX_CONSECUTIVE_OBSERVE_FAILURES,
    SACHIMA_DELEGATE_OBSERVATION_LOST,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
    bind_arsd_execution,
)
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import ArsdRunBindingLedger
from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    ARSD_SUPERVISOR_CONFIG_TYPE,
    EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
    ArsdSupervisorConfig,
)

# The private material a ref must never carry, in any form.
TASK_TEXT_CANARY = "audit the sachima delegate canary payload body"


@pytest.fixture(autouse=True)
def _fresh_store():
    """Every test starts and ends with an empty process-local store."""

    delegate_mod.delegate_payload_store().clear()
    yield
    delegate_mod.delegate_payload_store().clear()


# --------------------------------------------------------------------------- #
# A. Round trip / discard
# --------------------------------------------------------------------------- #
def test_put_then_resolve_returns_the_exact_text():
    store = delegate_mod._PayloadStore()
    ref = store.put(TASK_TEXT_CANARY)
    assert store.resolve(ref) == TASK_TEXT_CANARY


def test_discard_removes_the_payload_and_is_idempotent():
    store = delegate_mod._PayloadStore()
    ref = store.put(TASK_TEXT_CANARY)
    store.discard(ref)
    with pytest.raises(ValueError):
        store.resolve(ref)
    # Discarding an already-discarded ref is a no-op, never a raise: the
    # lifecycle discards on both the failure and the terminal path.
    store.discard(ref)
    assert store.count() == 0


def test_two_puts_of_identical_text_get_distinct_refs():
    store = delegate_mod._PayloadStore()
    first = store.put(TASK_TEXT_CANARY)
    second = store.put(TASK_TEXT_CANARY)
    assert first != second
    assert store.resolve(first) == store.resolve(second) == TASK_TEXT_CANARY
    store.discard(first)
    # Discarding one submission's payload never touches another's.
    assert store.resolve(second) == TASK_TEXT_CANARY


# --------------------------------------------------------------------------- #
# B. The ref is opaque and spine-safe
# --------------------------------------------------------------------------- #
def test_ref_never_carries_the_task_text():
    store = delegate_mod._PayloadStore()
    ref = store.put(TASK_TEXT_CANARY)
    lowered = ref.lower()
    assert TASK_TEXT_CANARY.lower() not in lowered
    for word in TASK_TEXT_CANARY.split():
        assert word not in lowered


def test_ref_is_shaped_like_a_spine_safe_id():
    """The ref rides as ``TurnDispatchRequest.payload_ref``; the spine
    re-validates it with ``_safe_id``, so an unsafe shape would fail closed at
    dispatch instead of here."""

    from sachima_supervisor.runtime_spine.events import _safe_id

    store = delegate_mod._PayloadStore()
    ref = store.put(TASK_TEXT_CANARY)
    assert re.fullmatch(r"[a-z][a-z0-9_]{0,127}", ref)
    assert _safe_id(ref) == ref


# --------------------------------------------------------------------------- #
# C. Unknown / malformed refs fail closed without an echo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "unknown",
    ["dlg_deadbeef", "", "   ", None, 7, b"dlg_deadbeef", TASK_TEXT_CANARY],
)
def test_unknown_ref_fails_with_the_stable_code_and_no_echo(unknown):
    store = delegate_mod._PayloadStore()
    store.put(TASK_TEXT_CANARY)
    with pytest.raises(ValueError) as excinfo:
        store.resolve(unknown)
    message = str(excinfo.value)
    assert message == delegate_mod.SACHIMA_DELEGATE_UNKNOWN_PAYLOAD_REF
    assert message in delegate_mod.SACHIMA_DELEGATE_STABLE_CODES
    # Neither the rejected ref nor any stored payload rides on the failure.
    rendered = str(unknown).strip()
    if rendered:
        assert rendered not in message
    assert TASK_TEXT_CANARY not in message


@pytest.mark.parametrize("bad_text", ["", "   ", None, 7])
def test_put_refuses_material_that_is_not_a_task(bad_text):
    store = delegate_mod._PayloadStore()
    with pytest.raises(ValueError) as excinfo:
        store.put(bad_text)
    assert str(excinfo.value) == delegate_mod.SACHIMA_DELEGATE_INVALID_TASK_TEXT
    assert store.count() == 0


def test_module_level_store_and_resolver_are_the_same_claim_check():
    """The resolver injected into the ARSD bundle resolves exactly what the
    coordinator stored — one process-local store, not two."""

    store = delegate_mod.delegate_payload_store()
    resolver = delegate_mod.delegate_payload_resolver()
    ref = store.put(TASK_TEXT_CANARY)
    assert resolver(ref) == TASK_TEXT_CANARY
    store.discard(ref)
    with pytest.raises(ValueError):
        resolver(ref)


# =========================================================================== #
# Coordinator lifecycle (Milestone A, tasks 5/6/8)
#
# Everything below drives the REAL composed ``arsd`` bundle — one registry,
# backend, port, dispatcher, and bindings store — with the daemon replaced by
# an injected facade double. No socket is opened, no daemon is started, and no
# AGENT is launched.
# =========================================================================== #
V3_OPERATIONS = [
    "run_cancel",
    "run_events",
    "run_status",
    "server_info",
    "session_list",
    "session_status",
    "submit",
]

FINAL_MESSAGE_CANARY = "the delegated agent finished and reported this"


class _Facade:
    """One in-memory arsd daemon, gateable at ``submit``.

    The gate is what makes the capacity proof real: with submits parked, a
    dispatch is genuinely *inside* the daemon, so "two are running and the
    third is waiting" is an observed state rather than a timing guess.
    """

    def __init__(self, *, max_concurrent_runs: int = 10) -> None:
        self.max_concurrent_runs = max_concurrent_runs
        self.calls: list[str] = []
        self.submitted: list[dict[str, Any]] = []
        self.run_ids: list[str] = []
        self.terminals: dict[str, dict[str, Any]] = {}
        self.submit_gate: threading.Event | None = None
        self.submit_error: BaseException | None = None
        self.run_status_error: BaseException | None = None
        self._lock = threading.RLock()
        self._seq = 0

    # -- test controls ------------------------------------------------------ #
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

    # -- the six operations ------------------------------------------------- #
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
        return {
            "run_id": run_id,
            "session_id": f"ARSSESSIONDELEGATE{seq}",
            "accepted_at": "2026-08-18T04:05:06+00:00",
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
        return {"run_id": run_id}

    def session_status(self, session_id: str) -> dict[str, Any]:
        self.calls.append("session_status")
        return {
            "session_id": session_id,
            "owner": "sachima_host",
            "namespace": "sachima_tasks",
            "agent_id": "author-agent",
            "profile_id": None,
            "created_at": "2026-08-18T04:05:06+00:00",
            "updated_at": "2026-08-18T04:05:06+00:00",
            "last_effective_model": None,
            "last_effective_effort": None,
            "quarantine": None,
        }

    def session_list(self) -> dict[str, Any]:
        self.calls.append("session_list")
        return {"sessions": []}


class _Notifier:
    """Records every notification, with the target it was sent to."""

    def __init__(self) -> None:
        self.sent: list[tuple[Any, str]] = []

    async def __call__(self, target, text: str) -> None:
        self.sent.append((target, text))

    def texts(self) -> list[str]:
        return [text for _target, text in self.sent]

    def for_task(self, task_id: str) -> list[str]:
        return [text for _t, text in self.sent if task_id in text]


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
        "agent_by_policy_ref": {"policy_author": "author-agent"},
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
        "grant_capabilities": ("read", "search", "write", "execute"),
        "mcp_snapshot_hashes": ("sha256:" + "c" * 64,),
        "credential_refs": ("cred_author",),
        "evidence_policy_hash": "sha256:" + "d" * 64,
        "recovery_policy_hash": "sha256:" + "e" * 64,
        "enabled": True,
    }
    kwargs.update(overrides)
    return ArsdSupervisorConfig(**kwargs)


def _coordinator(tmp_path: Path, *, facade=None, store=None, **config_overrides):
    facade = _Facade() if facade is None else facade
    config = _config(tmp_path, **config_overrides)
    bundle = bind_arsd_execution(
        config,
        facade=facade,
        ledger=ArsdRunBindingLedger(config.binding_ledger_path),
        payload_resolver=(store or delegate_mod.delegate_payload_store()).resolve,
    )
    coordinator = delegate_mod.SachimaDelegateCoordinator(
        bundle, config, store=store, observe_interval=0.01
    )
    return coordinator, facade


def _target(chat="chat-1", thread=None):
    return delegate_mod.DelegateTarget(
        platform="telegram", chat_id=chat, thread_id=thread
    )


async def _until(predicate, *, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


async def _settle(coordinator, *, timeout=10.0):
    assert await _until(lambda: coordinator.active_count() == 0, timeout=timeout), (
        "the delegate lifecycle never finished"
    )


# --------------------------------------------------------------------------- #
# D. submit_new — identity, payload, policy, and returning early (task 5)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_independent_tasks_get_distinct_task_and_session_identities(tmp_path):
    coordinator, facade = _coordinator(tmp_path)
    notifier = _Notifier()

    first = coordinator.submit_new("first task", target=_target(), notifier=notifier)
    second = coordinator.submit_new("second task", target=_target(), notifier=notifier)

    assert first.task_id != second.task_id
    assert first.session_id != second.session_id
    assert first.payload_ref != second.payload_ref
    assert first.session_id.startswith("sess_")

    assert await _until(lambda: facade.submit_count() == 2)
    facade.terminalize(0)
    facade.terminalize(1)
    await _settle(coordinator)


@pytest.mark.asyncio
async def test_the_exact_task_text_reaches_the_dispatcher_and_nothing_else_does(
    tmp_path,
):
    coordinator, facade = _coordinator(tmp_path)
    notifier = _Notifier()
    text = "read the changelog and 总结 the last three releases"

    submission = coordinator.submit_new(text, target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)
    payload = facade.submitted[0]
    assert payload["prompt_text"] == text
    # The ref travelled, not the text: it is what the durable record keys on.
    assert text not in json.dumps(payload["request"])
    assert submission.payload_ref not in payload["prompt_text"]

    facade.terminalize(0)
    await _settle(coordinator)


@pytest.mark.asyncio
async def test_the_turn_is_dispatched_as_a_prompt_under_the_configured_policy(
    tmp_path,
):
    coordinator, facade = _coordinator(tmp_path)
    notifier = _Notifier()
    coordinator.submit_new("do the thing", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)

    request = facade.submitted[0]["request"]
    assert request["agent_id"] == "author-agent"
    assert request["requested_model"] == "claude-opus-5"
    assert request["requested_effort"] == "xhigh"
    assert request["grant_capabilities"] == ["read", "search", "write", "execute"]
    assert coordinator.launch_refs == (
        "ws_delegate",
        "policy_author",
        "policy_model",
        "policy_effort",
        "policy_limits",
    )

    facade.terminalize(0)
    await _settle(coordinator)


@pytest.mark.asyncio
async def test_a_config_offering_a_choice_has_no_delegate_policy(tmp_path):
    """Milestone A's command surface cannot choose, so it never guesses."""

    facade = _Facade()
    with pytest.raises(ValueError) as excinfo:
        _coordinator(
            tmp_path,
            facade=facade,
            model_by_policy_ref={"policy_a": "claude-opus-5", "policy_b": "claude-sonnet-5"},
        )
    assert str(excinfo.value) == delegate_mod.SACHIMA_DELEGATE_INVALID_POLICY


@pytest.mark.asyncio
async def test_submit_new_returns_before_dispatch_and_leaves_the_lifecycle_running(
    tmp_path,
):
    gate = threading.Event()
    facade = _Facade()
    facade.submit_gate = gate
    coordinator, facade = _coordinator(tmp_path, facade=facade)
    notifier = _Notifier()

    submission = coordinator.submit_new("slow task", target=_target(), notifier=notifier)
    # The handler's answer is already in hand while the daemon has not even
    # been asked yet: nothing about capacity, dispatch, or the terminal was
    # awaited on the way out.
    assert facade.submit_count() == 0
    assert coordinator.active_count() == 1
    assert notifier.sent == []
    assert submission.task_id

    assert await _until(lambda: facade.submit_count() == 1)
    gate.set()
    facade.terminalize(0)
    await _settle(coordinator)


@pytest.mark.asyncio
async def test_submit_new_returns_immediately_even_when_capacity_is_full(tmp_path):
    gate = threading.Event()
    facade = _Facade(max_concurrent_runs=1)
    facade.submit_gate = gate
    coordinator, facade = _coordinator(tmp_path, facade=facade)
    notifier = _Notifier()

    first = coordinator.submit_new("first", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)

    started = time.monotonic()
    second = coordinator.submit_new("second", target=_target(), notifier=notifier)
    assert time.monotonic() - started < 1.0
    assert second.task_id != first.task_id
    assert coordinator.active_count() == 2

    gate.set()
    facade.terminalize(0)
    assert await _until(lambda: facade.submit_count() == 2)
    facade.terminalize(1)
    await _settle(coordinator)


@pytest.mark.asyncio
async def test_the_synchronous_dispatcher_never_blocks_the_event_loop(tmp_path):
    """The whole dispatch is synchronous spine code; running it inline would
    freeze every other conversation in the gateway for its duration."""

    gate = threading.Event()
    facade = _Facade()
    facade.submit_gate = gate
    coordinator, facade = _coordinator(tmp_path, facade=facade)
    notifier = _Notifier()

    ticks = 0

    async def _ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    ticker = asyncio.create_task(_ticker())
    try:
        coordinator.submit_new("parked task", target=_target(), notifier=notifier)
        assert await _until(lambda: facade.submit_count() == 1)
        await asyncio.sleep(0.2)
        assert ticks >= 5, ticks
    finally:
        ticker.cancel()
        gate.set()
    facade.terminalize(0)
    await _settle(coordinator)


@pytest.mark.asyncio
async def test_a_pre_dispatch_failure_discards_the_payload_and_reports_once(tmp_path):
    facade = _Facade()
    facade.submit_error = RuntimeError("daemon refused")
    coordinator, facade = _coordinator(tmp_path, facade=facade)
    notifier = _Notifier()

    submission = coordinator.submit_new("doomed", target=_target(), notifier=notifier)
    await _settle(coordinator)

    assert len(notifier.sent) == 1
    (_target_sent, text), = notifier.sent
    assert submission.task_id in text
    # The claim-check is emptied: a submission that will never dispatch has no
    # reason to keep the private text alive.
    assert delegate_mod.delegate_payload_store().count() == 0
    assert "daemon refused" not in text


# --------------------------------------------------------------------------- #
# E. Capacity through terminal (task 6)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_capacity_is_the_negotiated_limit_and_nothing_else(tmp_path):
    coordinator, _ = _coordinator(tmp_path, facade=_Facade(max_concurrent_runs=3))
    assert coordinator.capacity == 3


@pytest.mark.asyncio
async def test_the_slot_is_held_through_terminal_and_a_terminal_admits_exactly_one(
    tmp_path,
):
    """With a live limit of 2: A and B enter dispatch, C waits in the
    background. An *acceptance* releases nothing — only a terminal does, and it
    admits exactly one waiter."""

    gate = threading.Event()
    facade = _Facade(max_concurrent_runs=2)
    facade.submit_gate = gate
    coordinator, facade = _coordinator(tmp_path, facade=facade)
    notifier = _Notifier()

    a = coordinator.submit_new("task a", target=_target(), notifier=notifier)
    b = coordinator.submit_new("task b", target=_target(), notifier=notifier)
    c = coordinator.submit_new("task c", target=_target(), notifier=notifier)

    # Two dispatches are inside the daemon; the third never reached it.
    assert await _until(lambda: facade.submit_count() == 2)
    await asyncio.sleep(0.1)
    assert facade.submit_count() == 2
    assert notifier.for_task(c.task_id), "the waiting submission was never told"
    assert notifier.for_task(a.task_id) == []
    assert notifier.for_task(b.task_id) == []

    # Both acceptances land. An acceptance is not a terminal, so C still waits.
    gate.set()
    await asyncio.sleep(0.2)
    assert facade.submit_count() == 2, "an acceptance released a slot"

    # A terminal for A admits exactly one more — and B is still holding its own.
    facade.terminalize(0)
    assert await _until(lambda: facade.submit_count() == 3)
    await asyncio.sleep(0.1)
    assert facade.submit_count() == 3

    facade.terminalize(1)
    facade.terminalize(2)
    await _settle(coordinator)
    # One terminal each, plus C's single capacity-wait notice.
    assert len(notifier.for_task(a.task_id)) == 1
    assert len(notifier.for_task(b.task_id)) == 1
    assert len(notifier.for_task(c.task_id)) == 2


@pytest.mark.asyncio
async def test_the_slot_is_released_even_when_the_lifecycle_fails(tmp_path):
    facade = _Facade(max_concurrent_runs=1)
    facade.submit_error = RuntimeError("daemon refused")
    coordinator, facade = _coordinator(tmp_path, facade=facade)
    notifier = _Notifier()

    coordinator.submit_new("doomed", target=_target(), notifier=notifier)
    await _settle(coordinator)

    # The single slot came back, so the next submission dispatches at once.
    facade.submit_error = None
    coordinator.submit_new("next", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 2)
    facade.terminalize(1)
    await _settle(coordinator)


# --------------------------------------------------------------------------- #
# F. Sparse, deduplicated notifications (task 8)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_free_slot_produces_no_waiting_message(tmp_path):
    coordinator, facade = _coordinator(tmp_path)
    notifier = _Notifier()

    submission = coordinator.submit_new("task", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)
    # Repeated nonterminal observations: the observer polls, and says nothing.
    await asyncio.sleep(0.15)
    assert notifier.sent == []

    facade.terminalize(0)
    await _settle(coordinator)
    assert len(notifier.sent) == 1
    assert submission.task_id in notifier.texts()[0]
    assert FINAL_MESSAGE_CANARY in notifier.texts()[0]


@pytest.mark.asyncio
async def test_one_capacity_wait_message_at_most_then_one_terminal(tmp_path):
    """accepted -> waiting -> waiting -> running -> running -> completed:
    exactly one waiting message and exactly one terminal message."""

    gate = threading.Event()
    facade = _Facade(max_concurrent_runs=1)
    facade.submit_gate = gate
    coordinator, facade = _coordinator(tmp_path, facade=facade)
    notifier = _Notifier()

    first = coordinator.submit_new("first", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)
    second = coordinator.submit_new("second", target=_target(), notifier=notifier)

    # It stays waiting across many observation ticks and says so exactly once.
    await asyncio.sleep(0.2)
    assert len(notifier.for_task(second.task_id)) == 1

    gate.set()
    facade.terminalize(0)
    assert await _until(lambda: facade.submit_count() == 2)
    await asyncio.sleep(0.15)
    facade.terminalize(1)
    await _settle(coordinator)

    assert len(notifier.for_task(first.task_id)) == 1
    assert len(notifier.for_task(second.task_id)) == 2


@pytest.mark.parametrize(
    "status", ["failed", "cancelled", "timed_out", "unknown"]
)
@pytest.mark.asyncio
async def test_a_nonsuccess_terminal_is_reported_exactly_once(tmp_path, status):
    coordinator, facade = _coordinator(tmp_path)
    notifier = _Notifier()

    submission = coordinator.submit_new("task", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)
    facade.terminalize(0, status=status, final_message="")
    await _settle(coordinator)

    assert len(notifier.for_task(submission.task_id)) == 1
    # Repeated terminal observations after the fact add nothing.
    await asyncio.sleep(0.1)
    assert len(notifier.for_task(submission.task_id)) == 1


@pytest.mark.asyncio
async def test_a_truncated_answer_says_it_was_truncated(tmp_path):
    coordinator, facade = _coordinator(tmp_path)
    notifier = _Notifier()

    coordinator.submit_new("task", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)
    facade.terminalize(
        0, truncated=True, truncate_reason="max_final_message_bytes"
    )
    await _settle(coordinator)

    (text,) = notifier.texts()
    assert FINAL_MESSAGE_CANARY in text
    assert "max_final_message_bytes" in text


@pytest.mark.asyncio
async def test_every_notification_goes_back_to_the_same_chat_and_thread(tmp_path):
    gate = threading.Event()
    facade = _Facade(max_concurrent_runs=1)
    facade.submit_gate = gate
    coordinator, facade = _coordinator(tmp_path, facade=facade)
    notifier = _Notifier()

    target_a = _target(chat="chat-a", thread="thread-a")
    target_b = _target(chat="chat-b", thread="thread-b")
    a = coordinator.submit_new("first", target=target_a, notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)
    b = coordinator.submit_new("second", target=target_b, notifier=notifier)

    gate.set()
    assert await _until(lambda: facade.submit_count() == 1)
    facade.terminalize(0)
    assert await _until(lambda: facade.submit_count() == 2)
    facade.terminalize(1)
    await _settle(coordinator)

    for sent_target, text in notifier.sent:
        expected = target_a if a.task_id in text else target_b
        assert sent_target is expected
        assert sent_target.platform == "telegram"
    assert {t.chat_id for t, _ in notifier.sent} == {"chat-a", "chat-b"}
    assert b.task_id != a.task_id


@pytest.mark.asyncio
async def test_the_payload_is_discarded_once_the_run_is_terminal(tmp_path):
    store = delegate_mod._PayloadStore()
    coordinator, facade = _coordinator(tmp_path, store=store)
    notifier = _Notifier()

    submission = coordinator.submit_new("task", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)
    assert store.count() == 1

    facade.terminalize(0)
    await _settle(coordinator)
    assert store.count() == 0
    with pytest.raises(ValueError):
        store.resolve(submission.payload_ref)


@pytest.mark.asyncio
async def test_a_notifier_that_raises_never_strands_the_payload_or_the_slot(tmp_path):
    class _Broken:
        async def __call__(self, target, text):
            raise RuntimeError("delivery surface is down")

    store = delegate_mod._PayloadStore()
    coordinator, facade = _coordinator(tmp_path, store=store, facade=_Facade(max_concurrent_runs=1))
    coordinator.submit_new("task", target=_target(), notifier=_Broken())
    assert await _until(lambda: facade.submit_count() == 1)
    facade.terminalize(0)
    await _settle(coordinator)
    assert store.count() == 0

    # The slot came back too.
    notifier = _Notifier()
    coordinator.submit_new("next", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 2)
    facade.terminalize(1)
    await _settle(coordinator)


@pytest.mark.asyncio
async def test_the_notification_text_never_carries_private_run_material(tmp_path):
    coordinator, facade = _coordinator(tmp_path)
    notifier = _Notifier()

    coordinator.submit_new("task", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)
    facade.terminalize(0)
    await _settle(coordinator)

    (text,) = notifier.texts()
    assert "RUN-delegate-1" not in text
    assert "ARSSESSIONDELEGATE1" not in text
    assert str(tmp_path) not in text


# --------------------------------------------------------------------------- #
# G. Observation loss is not terminal evidence
#
# An accepted Run is the daemon's to end. Losing sight of it says nothing about
# whether it stopped, so a run of observation faults may not release the slot,
# discard the payload, or drop the state — otherwise a capacity-1 bundle admits
# a second Run while the first is still executing. The two tests below pin the
# hold and the recovery that ends it.
# --------------------------------------------------------------------------- #
def _observed(facade) -> int:
    """How many times the daemon double has been asked for a Run's status."""

    return facade.calls.count("run_status")


@pytest.mark.asyncio
async def test_observation_faults_never_release_the_slot_while_the_run_is_live(
    tmp_path,
):
    """capacity=1, Run A accepted and nonterminal, observation broken.

    Far more than ``_MAX_CONSECUTIVE_OBSERVE_FAILURES`` faults go by. B must
    not dispatch, because nothing has said A ended.
    """

    store = delegate_mod._PayloadStore()
    facade = _Facade(max_concurrent_runs=1)
    coordinator, facade = _coordinator(tmp_path, facade=facade, store=store)
    notifier = _Notifier()

    a = coordinator.submit_new("first", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)

    # A is accepted with no terminal body, and every observation now fails.
    facade.run_status_error = RuntimeError("observation surface is down")
    b = coordinator.submit_new("second", target=_target(), notifier=notifier)

    # Wait on observed evidence, not on the clock: A has now suffered more
    # than the tolerated run of consecutive faults.
    assert await _until(
        lambda: _observed(facade) >= _MAX_CONSECUTIVE_OBSERVE_FAILURES + 2
    )

    # The whole invariant, at the exact point the old code gave up: no second
    # dispatch, and nothing cleaned up.
    assert facade.submit_count() == 1, "B dispatched while A may still be live"
    assert coordinator.active_count() == 2
    assert store.count() == 2
    assert store.resolve(a.payload_ref) == "first"

    # And the hold is not a one-tick coincidence: it survives many times the
    # threshold, because only a terminal ends it.
    assert await _until(
        lambda: _observed(facade) > _MAX_CONSECUTIVE_OBSERVE_FAILURES * 6
    )
    assert facade.submit_count() == 1
    assert coordinator.active_count() == 2

    # Bounded feedback while blind: A is told once, not once per failed poll.
    assert len(notifier.for_task(a.task_id)) == 1
    assert SACHIMA_DELEGATE_OBSERVATION_LOST in notifier.for_task(a.task_id)[0]
    # B is waiting for the slot, and has been told that exactly once.
    assert len(notifier.for_task(b.task_id)) == 1

    # Recovery ends the hold — and only a real terminal does.
    facade.run_status_error = None
    facade.terminalize(0)
    assert await _until(lambda: facade.submit_count() == 2)

    # The advisory did not consume A's one terminal message.
    assert await _until(lambda: len(notifier.for_task(a.task_id)) == 2)
    assert FINAL_MESSAGE_CANARY in notifier.for_task(a.task_id)[1]

    facade.terminalize(1)
    await _settle(coordinator)
    assert store.count() == 0
    with pytest.raises(ValueError):
        store.resolve(a.payload_ref)

    # Still exactly one advisory and one terminal for A; one wait and one
    # terminal for B. Nothing was said twice.
    assert len(notifier.for_task(a.task_id)) == 2
    assert len(notifier.for_task(b.task_id)) == 2


@pytest.mark.asyncio
async def test_a_transient_observation_fault_is_silent_and_the_terminal_is_truthful(
    tmp_path,
):
    """Below the threshold, a fault is noise: no message at all, and the real
    terminal is still the only thing the chat hears."""

    facade = _Facade(max_concurrent_runs=1)
    coordinator, facade = _coordinator(tmp_path, facade=facade)
    notifier = _Notifier()

    submission = coordinator.submit_new("task", target=_target(), notifier=notifier)
    assert await _until(lambda: facade.submit_count() == 1)

    facade.run_status_error = RuntimeError("one blip")
    start = _observed(facade)
    assert await _until(
        lambda: _observed(facade) >= start + _MAX_CONSECUTIVE_OBSERVE_FAILURES - 1
    )
    facade.run_status_error = None
    facade.terminalize(0)
    await _settle(coordinator)

    (text,) = notifier.for_task(submission.task_id)
    assert FINAL_MESSAGE_CANARY in text
    assert SACHIMA_DELEGATE_OBSERVATION_LOST not in text


# --------------------------------------------------------------------------- #
# H. One policy ref may key several categories
#
# ``ArsdSupervisorConfig`` places no rule that agent/model/effort/run-limits use
# *different* policy refs — the canonical socket-contract fixtures key all four
# with a single ``policy_reader``. The launch refs are a set of choices, not a
# per-category list, so a shared ref must be offered to the backend once: the
# backend matches a ref against each mapping and demands exactly one match, and
# a repeated ref counts as several. Deduplication is what makes a valid
# single-choice config usable; it must not soften the "no choosing" rule.
# --------------------------------------------------------------------------- #
_SHARED_LIMITS = {
    "startup_timeout_seconds": 60.0,
    "turn_timeout_seconds": 600.0,
    "cancel_grace_seconds": 10.0,
    "max_stderr_bytes": 262_144,
    "max_event_bytes": 65_536,
    "max_events": 10_000,
}


def _shared_policy_overrides(ref: str = "policy_reader", **overrides: Any) -> dict:
    """One policy ref keying agent, model, effort and run-limits at once."""

    shared = {
        "agent_by_policy_ref": {ref: "author-agent"},
        "model_by_policy_ref": {ref: "claude-opus-5"},
        "effort_by_policy_ref": {ref: "xhigh"},
        "run_limits_by_policy_ref": {ref: dict(_SHARED_LIMITS)},
    }
    shared.update(overrides)
    return shared


@pytest.mark.asyncio
async def test_one_policy_ref_across_every_category_still_delegates(tmp_path):
    """The canonical single-``policy_reader`` shape reaches a real submit.

    Before deduplication the ref was appended once per mapping, so the backend
    saw four matches for each policy map, denied the policy, and the submission
    died before ARS ever heard about it.
    """

    store = delegate_mod._PayloadStore()
    coordinator, facade = _coordinator(
        tmp_path, store=store, **_shared_policy_overrides()
    )
    notifier = _Notifier()

    # The business failure first: this submission used to die inside
    # ``create_or_attach`` with a backend policy denial, before ARS was ever
    # asked anything.
    submission = coordinator.submit_new(
        "shared policy task", target=_target(), notifier=notifier
    )
    assert await _until(lambda: facade.submit_count() == 1)

    # The shared ref is offered once, the distinct workspace ref beside it.
    assert coordinator.launch_refs == ("ws_delegate", "policy_reader")

    # Every category resolved through that one ref, exactly as configured.
    request = facade.submitted[0]["request"]
    assert request["agent_id"] == "author-agent"
    assert request["requested_model"] == "claude-opus-5"
    assert request["requested_effort"] == "xhigh"
    assert request["limits"] == _SHARED_LIMITS
    assert request["grant_capabilities"] == ["read", "search", "write", "execute"]

    # One submission, and the ordinary lifecycle around it is untouched.
    facade.terminalize(0)
    await _settle(coordinator)
    assert facade.submit_count() == 1
    assert len(notifier.for_task(submission.task_id)) == 1
    assert FINAL_MESSAGE_CANARY in notifier.for_task(submission.task_id)[0]
    assert store.count() == 0


@pytest.mark.asyncio
async def test_a_shared_policy_ref_does_not_excuse_a_category_offering_a_choice(
    tmp_path,
):
    """Deduplication collapses repeats; it never collapses *options*.

    The per-mapping "exactly one configured key" rule is applied before any
    ref is deduplicated, so a second model option is still a config this
    command surface cannot honor — sharing a ref elsewhere changes nothing.
    """

    with pytest.raises(ValueError) as excinfo:
        _coordinator(
            tmp_path,
            facade=_Facade(),
            **_shared_policy_overrides(
                model_by_policy_ref={
                    "policy_reader": "claude-opus-5",
                    "policy_other": "claude-sonnet-5",
                }
            ),
        )
    assert str(excinfo.value) == delegate_mod.SACHIMA_DELEGATE_INVALID_POLICY


def test_a_category_with_no_configured_key_is_still_refused() -> None:
    """The zero-key half of the same rule.

    Reached directly: ``ArsdSupervisorConfig`` already refuses an empty policy
    map at construction, so no real config can carry one this far — and the
    guard must still hold if that ever changes.
    """

    class _NoAgentConfig:
        workspace_by_ref = {"ws_delegate": "/tmp/ws"}
        agent_by_policy_ref: dict = {}
        model_by_policy_ref = {"policy_reader": "claude-opus-5"}
        effort_by_policy_ref = {"policy_reader": "xhigh"}
        run_limits_by_policy_ref = {"policy_reader": dict(_SHARED_LIMITS)}

    with pytest.raises(ValueError) as excinfo:
        delegate_mod._delegate_launch_refs(_NoAgentConfig())
    assert str(excinfo.value) == delegate_mod.SACHIMA_DELEGATE_INVALID_POLICY


def test_distinct_refs_are_unchanged_and_partial_sharing_keeps_first_seen_order() -> None:
    """Dedup is order-stable and a no-op when every ref differs."""

    class _Config:
        workspace_by_ref = {"ws_delegate": "/tmp/ws"}
        agent_by_policy_ref = {"policy_author": "author-agent"}
        model_by_policy_ref = {"policy_model": "claude-opus-5"}
        effort_by_policy_ref = {"policy_effort": "xhigh"}
        run_limits_by_policy_ref = {"policy_limits": dict(_SHARED_LIMITS)}

    assert delegate_mod._delegate_launch_refs(_Config()) == (
        "ws_delegate",
        "policy_author",
        "policy_model",
        "policy_effort",
        "policy_limits",
    )

    # Agent and effort share one ref; model and run-limits have their own. The
    # shared ref keeps the position of its first appearance.
    class _PartlyShared(_Config):
        agent_by_policy_ref = {"policy_shared": "author-agent"}
        effort_by_policy_ref = {"policy_shared": "xhigh"}

    assert delegate_mod._delegate_launch_refs(_PartlyShared()) == (
        "ws_delegate",
        "policy_shared",
        "policy_model",
        "policy_limits",
    )
