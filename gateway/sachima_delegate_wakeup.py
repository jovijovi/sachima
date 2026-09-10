"""Thin durable bridge from a Sachima terminal to the owning Gateway turn.

The coordinator remains the result authority and the Gateway remains the
session/queue authority. This module only claims result-associated wake intents,
batches those for one recorded conversation, and asks the Gateway to inject one
trusted internal event. It owns no poller, daemon, task database, or model loop.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
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
    "DelegateWakeupBatch",
    "MAX_WAKEUP_ATTEMPTS",
    "SACHIMA_WAKEUP_RETRYABLE",
    "SACHIMA_WAKEUP_SUPERSEDED",
    "SACHIMA_WAKEUP_UNROUTABLE",
    "SachimaDelegateWakeupDispatcher",
    "WAKEUP_DELIVERY_ACCEPTED",
    "WAKEUP_DELIVERY_BLOCKED",
    "WAKEUP_DELIVERY_RETRY",
    "WAKEUP_DELIVERY_SUPERSEDED",
]
