"""Thin durable bridge from a Sachima terminal to the owning Gateway turn.

The coordinator remains the result authority and the Gateway remains the
session/queue authority. This module only claims result-associated wake intents,
batches those for one recorded conversation, and asks the Gateway to inject one
trusted internal event. It owns no poller, daemon, task database, or model loop.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from gateway.sachima_delegate_state import DelegateOrigin, DelegateResultEvent

logger = logging.getLogger(__name__)

WAKEUP_DELIVERY_ACCEPTED = "accepted"
WAKEUP_DELIVERY_RETRY = "retry"
WAKEUP_DELIVERY_SUPERSEDED = "superseded"
WAKEUP_DELIVERY_BLOCKED = "blocked"
WAKEUP_DELIVERY_OUTCOMES = frozenset({
    WAKEUP_DELIVERY_ACCEPTED,
    WAKEUP_DELIVERY_RETRY,
    WAKEUP_DELIVERY_SUPERSEDED,
    WAKEUP_DELIVERY_BLOCKED,
})

SACHIMA_WAKEUP_RETRYABLE = "sachima_delegate_wakeup_retryable"
SACHIMA_WAKEUP_UNROUTABLE = "sachima_delegate_wakeup_unroutable"
SACHIMA_WAKEUP_SUPERSEDED = "sachima_delegate_wakeup_superseded"

# A terminal callback attempts once. Each normal restart may reconcile one
# more time, up to this durable cap; there is no retry loop in this module.
MAX_WAKEUP_ATTEMPTS = 3


def _chat_type_from_session_key(session_key: str, thread_id: str | None) -> str:
    parts = session_key.split(":")
    if len(parts) >= 5 and parts[0:2] == ["agent", "main"]:
        return parts[3]
    return "thread" if thread_id else "dm"


@dataclass(frozen=True)
class DelegateWakeupBatch:
    """One claimed set of exact terminal identities for one recorded origin."""

    claim_id: str
    event_ids: tuple[str, ...]
    task_refs: tuple[str, ...]
    turn_keys: tuple[str, ...]
    session_key: str
    origin_session_id: str
    platform: str
    chat_type: str
    chat_id: str
    thread_id: str | None
    user_id: str | None = None
    continuation_refs: tuple[str, ...] = ()

    def as_gateway_event(self) -> dict[str, Any]:
        """Return routing data consumed by the existing internal event seam."""

        return {
            "type": "sachima_delegate",
            "claim_id": self.claim_id,
            "event_ids": list(self.event_ids),
            "task_refs": list(self.task_refs),
            "turn_keys": list(self.turn_keys),
            "sachima_delegate_continuation_refs": list(self.continuation_refs),
            "session_key": self.session_key,
            "origin_session_id": self.origin_session_id,
            "parent_session_id": self.origin_session_id,
            "platform": self.platform,
            "chat_type": self.chat_type,
            "chat_id": self.chat_id,
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            # The key is exact host routing material. The physical Session id
            # is intentionally non-strict so the existing compression-lineage
            # resolver can move it to a proven successor. /new is rejected by
            # the Gateway's parent-session preflight before injection.
            "gateway_session_key": self.session_key,
            "gateway_session_strict": False,
            "allow_gateway_control": False,
            # This is an internal correlation id, not a platform message id.
            # Keep it on MessageEvent for event identity while excluding it
            # from native reply construction.
            "message_id_is_reply_anchor": False,
            "message_id": f"sachima-wakeup-{self.claim_id}",
        }

    def message_text(self) -> str:
        refs = ", ".join(self.event_ids)
        return (
            "[Sachima delegation terminal notification]\n"
            f"Exact result event ids: {refs}.\n"
            "This trusted internal event is a request to verify and report "
            "already-authorized work; it is not a new user authorization. "
            "Read each exact event through sachima_delegate_control before "
            "settling it or using any stored continuation authority."
        )


_WAKE_IDENTITY_KEYS = (
    "sachima_delegate_event_ids",
    "sachima_delegate_task_refs",
    "sachima_delegate_turn_keys",
    "sachima_delegate_continuation_refs",
)


def is_delegate_wake(event: Any) -> bool:
    ids = (getattr(event, "metadata", None) or {}).get("sachima_delegate_event_ids")
    return getattr(event, "internal", False) is True and isinstance(ids, list) and bool(ids)


def _absorb_wake(target: Any, wake: Any) -> None:
    """``run_busy``'s takeover: the user's event carries the wake's exact identities and its
    one-shot receipt; text, user identity and gateway-control authority stay the user's."""

    if not isinstance(getattr(target, "metadata", None), dict):
        target.metadata = {}
    wake_metadata = wake.metadata or {}
    for key in _WAKE_IDENTITY_KEYS:
        values = wake_metadata.get(key)
        if isinstance(values, list):
            merged = list(target.metadata.get(key) or [])
            merged.extend(item for item in values if isinstance(item, str) and item not in merged)
            target.metadata[key] = merged
    callback = wake_metadata.get("_gateway_processing_outcome_callback")
    if callable(callback):
        target.metadata["_gateway_processing_outcome_callback"] = callback


@dataclass(eq=False)
class _PendingHuman:
    """A user message committed to the durable FIFO whose turn has not started yet."""

    event: Any
    session_key: str
    wakes: list = field(default_factory=list)


def _pending_humans(runner: Any) -> dict[str, list[_PendingHuman]]:
    return runner.__dict__.setdefault("_sachima_pending_humans", {})


def take_wake_for_pending_human(runner: Any, session_key: str, event: Any) -> bool:
    """A wake for a route whose committed user message has not started joins that turn."""

    pending = _pending_humans(runner).get(session_key)
    if not pending or not is_delegate_wake(event):
        return False
    _absorb_wake(pending[0].event, event)
    pending[0].wakes.append(event)
    event._gateway_accepted = True
    return True


def _human_committed(runner: Any, pending: _PendingHuman) -> None:
    route = _pending_humans(runner).setdefault(pending.session_key, [])
    route.append(pending)
    if route[0] is not pending:
        return  # an earlier committed message already owns the route's next turn
    adapter = runner._delivery_adapter_for(pending.event.source)
    slot = getattr(adapter, "_pending_messages", None)
    if not isinstance(slot, dict):
        return
    key = pending.session_key
    state = runner._peek_session_state(key)
    overflow = state.conversation.queued_events if state is not None else []
    taken = [slot.pop(key)] if is_delegate_wake(slot.get(key)) else []
    kept = [queued for queued in overflow if not is_delegate_wake(queued)]
    taken.extend(queued for queued in overflow if is_delegate_wake(queued))
    if len(kept) != len(overflow):
        state.conversation.queued_events = kept
    if key not in slot and state is not None and state.conversation.queued_events:
        slot[key] = state.conversation.queued_events.pop(0)
    for wake in taken:
        _absorb_wake(pending.event, wake)
        pending.wakes.append(wake)


def human_turn_started(runner: Any, event: Any, session_key: str) -> None:
    """The admitted copy of a committed user message started: later wakes queue behind it."""

    if getattr(event, "internal", False):
        return
    route = _pending_humans(runner).get(session_key) or []
    for pending in route:
        original = pending.event
        if original is event or (
            (original.message_id or event.message_id)
            and str(original.message_id or "") == str(event.message_id or "")
        ) or (not original.message_id and not event.message_id and original.text == event.text):
            route.remove(pending)
            break
    if not route:
        _pending_humans(runner).pop(session_key, None)


async def admit_human_message(runner: Any, authority: Any, event: Any, session_key: str) -> Any:
    """``admit_message`` for a user message, with the wake takeover of plan §3.3 D.

    Committing the message (the authority's own ``_on_commit`` point) moves a same-route queued
    wake onto it, and a wake that arrives before its turn starts joins it, so the user's message
    owns the next turn. If the message ends without its turn starting (/stop, /new, a refused
    preflight), the wakes go back to the route: to the next committed message, else to the slot.
    """

    from gateway.session_ingress import admit_message

    pending = _PendingHuman(event, session_key)
    previous = getattr(event, "_on_commit", None)

    def on_commit() -> None:
        if previous is not None:
            previous()
        _human_committed(runner, pending)

    event._on_commit = on_commit
    try:
        return await admit_message(authority, event)
    finally:
        await _human_admission_ended(runner, pending)


async def _human_admission_ended(runner: Any, pending: _PendingHuman) -> None:
    route = _pending_humans(runner).get(pending.session_key) or []
    if pending not in route:
        return  # never committed, or its turn started and owns what it took
    route.remove(pending)
    if not route:
        _pending_humans(runner).pop(pending.session_key, None)
    wakes, pending.wakes = pending.wakes, []
    if not wakes:
        return
    for key in (*_WAKE_IDENTITY_KEYS, "_gateway_processing_outcome_callback"):
        pending.event.metadata.pop(key, None)
    if route:
        for wake in wakes:
            _absorb_wake(route[0].event, wake)
            route[0].wakes.append(wake)
        return
    head = wakes[0]
    for wake in wakes[1:]:
        _absorb_wake(head, wake)
    try:
        await admit_wake_event(runner, runner._delivery_adapter_for(head.source), head)
    except Exception:
        # The coordinator still holds the results as queued; restart recovery re-dispatches them.
        logger.warning("sachima delegate wake could not return to its route", exc_info=True)


#: The one-shot business receipt a turn binds to the event it processed (``run.py``
#: ``_bind_delegate_processing_receipt``) and the model-turn half of its delivery check.
_DELIVERY_RECEIPT_KEYS = (
    "sachima_delegate_event_ids",
    "_gateway_processing_outcome_callback",
    "_gateway_model_turn_completed",
)


def move_delivery_receipt(source: Any, target: Any) -> None:
    """Carry a turn's delegation receipt to the event whose lifecycle sends its reply.

    The session authority runs an admitted message on a ``restore_native`` copy, so the
    receipt the turn bound to that copy travels with its crash marker to the adapter event
    that really sends; otherwise a delivered report stays ``report_pending`` and the next
    restart blocks it as unknown.
    """

    metadata = getattr(source, "metadata", None)
    if not isinstance(metadata, dict) or not callable(
        metadata.get("_gateway_processing_outcome_callback")
    ):
        return
    moved = {key: metadata[key] for key in _DELIVERY_RECEIPT_KEYS if key in metadata}
    for key in moved:
        metadata.pop(key)
    if not isinstance(getattr(target, "metadata", None), dict):
        target.metadata = {}
    target.metadata.update(moved)


async def settle_delivery_receipt(adapter: Any, event: Any, results: list) -> None:
    """Fire the receipt at a send that has no processing hook (busy observer, ``deliver_settled``)."""

    callback_runner = getattr(adapter, "_run_internal_processing_outcome_callback", None)
    if not callable(callback_runner):
        return
    from gateway.platforms.base import ProcessingOutcome

    delivered = any(bool(getattr(result, "success", False)) for result in results if result is not None)
    await callback_runner(
        event, ProcessingOutcome.SUCCESS if delivered else ProcessingOutcome.FAILURE
    )


async def admit_wake_event(runner: Any, adapter: Any, event: Any) -> None:
    """Admit one synthetic wake event into its route on the in-process internal path.

    Raises ``WakeNotAccepted`` when nothing accepted it, exactly like ``admit_internal_event``.
    While the adapter holds the route's guard, the guard's owner drains the wake after its own
    turn. Routed through ``handle_message`` instead, the shared runtime's busy observer would run
    the whole wake turn itself and send its reply with no processing hook, so the report receipt
    never fires and the unacknowledged wake is retried although it ran.
    """

    from gateway.wake import WakeNotAccepted, admit_internal_event

    if adapter._drop_unresolved(event):
        raise WakeNotAccepted()
    session_key = adapter._event_session_key(event)
    if take_wake_for_pending_human(runner, session_key, event):
        return
    if session_key not in adapter._active_sessions:
        await admit_internal_event(adapter, event)
        return
    expected = str((event.metadata or {}).get("gateway_session_key") or "").strip()
    event._gateway_accepted = False
    if not expected or expected == session_key:
        runner._queue_or_replace_pending_event(session_key, event)
    if event._gateway_accepted is not True:
        raise WakeNotAccepted()


class SachimaDelegateWakeupDispatcher:
    """Claim, batch, and inject admitted terminal wake intents."""

    def __init__(
        self,
        coordinator: Any,
        *,
        deliver: Callable[[DelegateWakeupBatch], Awaitable[str | bool | None]],
        enabled: bool,
    ) -> None:
        self._coordinator = coordinator
        self._state = coordinator.state
        self._deliver = deliver
        self._enabled = enabled is True
        self._lock = asyncio.Lock()
        self._closed = False

    async def close(self) -> None:
        self._closed = True
        self._coordinator._set_completion_wakeup_notifier(None)

    async def notify(self, event: DelegateResultEvent) -> None:
        """Coalesce same-loop terminals, then deliver their conversation batch."""

        if self._closed or not self._enabled or event.wakeup_state != "pending":
            return
        # Let sibling observer tasks publish their terminal records before the
        # single group scan. No timer or polling worker is introduced.
        await asyncio.sleep(0)
        async with self._lock:
            await self._dispatch_origin(event)

    async def recover(self) -> dict[str, int]:
        """Recover admitted delivery gaps once, without touching any AGENT Run."""

        counts = {
            "recovered": 0,
            "accepted": 0,
            "blocked": 0,
            "retry": 0,
            "report_unknown": 0,
            "operations_reconciled": 0,
            "operation_retry": 0,
            "operation_uncertain": 0,
        }
        if self._closed:
            return counts
        async with self._lock:
            # A staged report without its adapter receipt straddled the process
            # boundary. Do not guess delivered and do not send it twice.
            report_pending_ids = tuple(
                event.event_id
                for event in self._state.list_results()
                if event.business_state == "report_pending"
            )
            if report_pending_ids:
                counts["report_unknown"] = self._coordinator.complete_report_delivery(
                    report_pending_ids,
                    delivered=None,
                )

            operation_counts = (
                await self._coordinator._reconcile_continuation_operations()
            )
            counts["operations_reconciled"] = operation_counts["reconciled"]
            counts["operation_retry"] = operation_counts["retry"]
            counts["operation_uncertain"] = operation_counts["uncertain"]

            for event in self._state.list_results():
                if (
                    event.business_state == "pending"
                    and event.hermes_sink != "confirmed"
                    and event.wakeup_state
                    in (
                        {"pending", "in_flight", "queued"}
                        if not self._enabled
                        else {"in_flight", "queued"}
                    )
                ):
                    self._state.update_result(
                        event.event_id,
                        wakeup_state=(
                            "not_admitted"
                            if not self._enabled
                            else "pending"
                            if event.wakeup_attempts < MAX_WAKEUP_ATTEMPTS
                            else "blocked"
                        ),
                        wakeup_claim_id=None,
                        wakeup_diagnostic=(
                            None
                            if (
                                not self._enabled
                                or event.wakeup_attempts < MAX_WAKEUP_ATTEMPTS
                            )
                            else SACHIMA_WAKEUP_RETRYABLE
                        ),
                    )
                    counts["recovered"] += 1
            if not self._enabled:
                return counts

            while True:
                pending = next(
                    (
                        item
                        for item in self._state.list_results()
                        if item.wakeup_state == "pending"
                        and item.business_state == "pending"
                    ),
                    None,
                )
                if pending is None:
                    break
                outcome, size = await self._dispatch_origin(pending)
                if outcome == WAKEUP_DELIVERY_ACCEPTED:
                    counts["accepted"] += size
                elif outcome == WAKEUP_DELIVERY_RETRY:
                    counts["retry"] += size
                    # No in-process retry loop. A normal restart or ordinary
                    # user turn is the next opportunity.
                    break
                else:
                    counts["blocked"] += size
            return counts

    def complete_report_delivery(
        self,
        event_ids: tuple[str, ...],
        *,
        delivered: bool | None,
    ) -> int:
        """Forward the adapter's real turn outcome to the result authority."""

        if self._closed:
            return 0
        return self._coordinator.complete_report_delivery(
            event_ids,
            delivered=delivered,
        )

    def _same_origin(self, event: DelegateResultEvent, origin: DelegateOrigin) -> bool:
        try:
            turn = self._state.read_turn(event.turn_key)
        except Exception:
            return False
        return (
            turn is not None
            and turn.origin.session_key == origin.session_key
            and turn.origin.session_id == origin.session_id
        )

    def _claim_batch(self, seed: DelegateResultEvent) -> DelegateWakeupBatch | None:
        try:
            seed_turn = self._state.read_turn(seed.turn_key)
        except Exception:
            return None
        if seed_turn is None:
            return None
        origin = seed_turn.origin
        candidates = [
            event
            for event in self._state.list_results()
            if event.wakeup_state == "pending"
            and event.business_state == "pending"
            and self._same_origin(event, origin)
        ]
        if not candidates:
            return None
        claim_id = self._state.new_wakeup_claim_id()
        claimed: list[DelegateResultEvent] = []
        for event in candidates:
            if event.wakeup_attempts >= MAX_WAKEUP_ATTEMPTS:
                self._state.update_result(
                    event.event_id,
                    wakeup_state="blocked",
                    wakeup_diagnostic=SACHIMA_WAKEUP_RETRYABLE,
                )
                continue
            claimed.append(
                self._state.update_result(
                    event.event_id,
                    wakeup_state="in_flight",
                    wakeup_claim_id=claim_id,
                    wakeup_attempts=event.wakeup_attempts + 1,
                    wakeup_diagnostic=None,
                )
            )
        if not claimed:
            return None
        return DelegateWakeupBatch(
            claim_id=claim_id,
            event_ids=tuple(item.event_id for item in claimed),
            task_refs=tuple(item.task_ref for item in claimed),
            turn_keys=tuple(item.turn_key for item in claimed),
            session_key=origin.session_key,
            origin_session_id=origin.session_id,
            platform=origin.platform,
            chat_type=_chat_type_from_session_key(origin.session_key, origin.thread_id),
            chat_id=origin.chat_id,
            thread_id=origin.thread_id,
            continuation_refs=tuple(
                dict.fromkeys(
                    binding.continuation_payload_ref
                    for item in claimed
                    if (
                        (binding := self._state.read_task(item.task_ref)) is not None
                        and binding.continuation_payload_ref is not None
                    )
                )
            ),
        )

    @staticmethod
    def _delivery_outcome(value: str | bool | None) -> str:
        if value is True:
            return WAKEUP_DELIVERY_ACCEPTED
        if value is False:
            return WAKEUP_DELIVERY_RETRY
        if value in WAKEUP_DELIVERY_OUTCOMES:
            return value
        return WAKEUP_DELIVERY_BLOCKED

    async def _dispatch_origin(self, seed: DelegateResultEvent) -> tuple[str, int]:
        batch = self._claim_batch(seed)
        if batch is None:
            return WAKEUP_DELIVERY_BLOCKED, 0
        try:
            outcome = self._delivery_outcome(await self._deliver(batch))
        except Exception:
            logger.warning("sachima delegate wake delivery failed", exc_info=True)
            outcome = WAKEUP_DELIVERY_RETRY

        if outcome == WAKEUP_DELIVERY_SUPERSEDED:
            await self._coordinator._supersede_wakeup_events(batch.event_ids)

        for event_id in batch.event_ids:
            current = self._state.read_result(event_id)
            if current is None or current.wakeup_claim_id != batch.claim_id:
                continue
            # Adapter ingress may already have let the turn claim the result.
            # Never move a processing/provider state backwards to ``queued``.
            if current.wakeup_state != "in_flight":
                continue
            if outcome == WAKEUP_DELIVERY_ACCEPTED:
                self._state.update_result(
                    event_id,
                    wakeup_state="queued",
                    wakeup_diagnostic=None,
                )
            elif outcome == WAKEUP_DELIVERY_RETRY:
                blocked = current.wakeup_attempts >= MAX_WAKEUP_ATTEMPTS
                self._state.update_result(
                    event_id,
                    wakeup_state="blocked" if blocked else "pending",
                    wakeup_claim_id=None,
                    wakeup_diagnostic=SACHIMA_WAKEUP_RETRYABLE,
                )
            else:
                self._state.update_result(
                    event_id,
                    wakeup_state="blocked",
                    wakeup_diagnostic=(
                        SACHIMA_WAKEUP_SUPERSEDED
                        if outcome == WAKEUP_DELIVERY_SUPERSEDED
                        else SACHIMA_WAKEUP_UNROUTABLE
                    ),
                )
        return outcome, len(batch.event_ids)


__all__ = [
    "MAX_WAKEUP_ATTEMPTS",
    "SACHIMA_WAKEUP_RETRYABLE",
    "SACHIMA_WAKEUP_SUPERSEDED",
    "SACHIMA_WAKEUP_UNROUTABLE",
    "WAKEUP_DELIVERY_ACCEPTED",
    "WAKEUP_DELIVERY_BLOCKED",
    "WAKEUP_DELIVERY_RETRY",
    "WAKEUP_DELIVERY_SUPERSEDED",
    "DelegateWakeupBatch",
    "SachimaDelegateWakeupDispatcher",
]
