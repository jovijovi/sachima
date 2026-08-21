"""Sachima ``/delegate`` — accepted receipts, result envelopes, delivery settlement.

Three primitives, all pure, all usable before any coordinator exists:

1. **The accepted receipt.** Its three value fields are named exactly
   ``requested_agent`` / ``requested_model`` / ``requested_effort`` and are
   sourced from the resolved selected-profile request. They state what Sachima
   asked for. They are never an effective-runtime readback and are never
   rendered as one — ARS's per-Run effective configuration is a separate,
   unproven evidence gate, and a receipt that quietly claimed it would be
   asserting something nobody observed.
2. **The result envelope.** One versioned ``external_agent_result`` per settled
   terminal, carrying the durable full-result claim-check ref. The same envelope
   drives both sinks, which is what makes "one terminal, one message, one
   projection" a property of the data rather than of two code paths agreeing.
3. **Delivery settlement.** :func:`settle_send_result` is total over
   ``SendResult``: every branch, including the legitimate
   ``success=True, message_id=None`` that Feishu really does return, lands in a
   documented durable state. ``success`` is authoritative; an optional message id
   is *not* a second success predicate, and no valid branch leaves a send
   ``in_flight``.

The visible IM body is bounded **before** the send: it reserves room for the
full-result ref, truncates the answer to the platform's one-message text bound,
and says it truncated. The untruncated answer stays behind its ref. Splitting
afterwards would turn one terminal into several messages, and provider-visible
exactly-once is not something a host can claim — what it can guarantee is one
durable result, one logical body per attempt, and a settled record of every
attempt.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

__all__ = [
    "UNCERTAIN_SETTLEMENT",
    "DELEGATE_RESULT_ENVELOPE_TYPE",
    "DELEGATE_RESULT_ENVELOPE_VERSION",
    "SEND_SETTLEMENT_STATES",
    "SACHIMA_DELEGATE_SEND_FAILED",
    "SACHIMA_DELEGATE_SEND_INVALID_RESULT",
    "SACHIMA_DELEGATE_SEND_UNCERTAIN",
    "DelegateAcceptedReceipt",
    "DelegateResultEnvelope",
    "SendSettlement",
    "build_hermes_context",
    "build_result_envelope",
    "perform_settled_send",
    "render_accepted_receipt",
    "render_result_body",
    "settle_send_result",
]

DELEGATE_RESULT_ENVELOPE_TYPE = "external_agent_result"
DELEGATE_RESULT_ENVELOPE_VERSION = 1

#: The durable settlement vocabulary shared by accepted receipts and terminal
#: IM sinks (plan I6). ``in_flight`` is deliberately absent: it is the state a
#: send is persisted in *before* the attempt, never one an outcome maps to.
SEND_SETTLEMENT_STATES = ("confirmed", "failed", "uncertain")

SACHIMA_DELEGATE_SEND_FAILED = "sachima_delegate_send_failed"
SACHIMA_DELEGATE_SEND_UNCERTAIN = "sachima_delegate_send_uncertain"
SACHIMA_DELEGATE_SEND_INVALID_RESULT = "sachima_delegate_send_invalid_result"

#: The closed terminal vocabulary a result envelope may carry. ``cancelled`` is
#: a terminal in its own right; every non-success ARS terminal has already been
#: mapped to ``failed`` by the spine before it gets here.
DELEGATE_TERMINALS = ("completed", "failed", "cancelled")

RECEIPT_TEMPLATE = (
    "已接受任务 {task_ref}\n"
    "AGENT：{requested_agent}\n"
    "模型：{requested_model}\n"
    "强度：{requested_effort}\n"
    "完成后会在这里回复。"
)
RESULT_HEADER_TEMPLATE = {
    "completed": "任务 {task_ref} 已完成：",
    "failed": "任务 {task_ref} 执行失败：",
    "cancelled": "任务 {task_ref} 已取消。",
}
RESULT_REF_TEMPLATE = "完整结果：{full_result_ref}"
RESULT_TRUNCATED_NOTICE = "（输出已截断）"
RESULT_EMPTY_BODY = "（无输出）"
HERMES_CONTEXT_TEMPLATE = (
    "[external-agent-result] task={task_ref} terminal={terminal} "
    "full_result_ref={full_result_ref}"
)

#: How much of the answer the next Hermes turn sees inline. The rest stays
#: behind the ref, readable on request — a context injection is a notification,
#: not a transcript.
HERMES_CONTEXT_EXCERPT_CHARS = 800


@dataclass(frozen=True)
class DelegateAcceptedReceipt:
    """What Sachima says once — and only once — a Run is durably accepted.

    The three value fields are named for what they are. Nothing here observes a
    Run; nothing here is an effective readback.
    """

    task_ref: str
    requested_agent: str
    requested_model: str
    requested_effort: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_ref": self.task_ref,
            "requested_agent": self.requested_agent,
            "requested_model": self.requested_model,
            "requested_effort": self.requested_effort,
        }


def render_accepted_receipt(receipt: DelegateAcceptedReceipt) -> str:
    """The one visible acceptance line for a durably accepted Run."""

    if type(receipt) is not DelegateAcceptedReceipt:
        raise ValueError(SACHIMA_DELEGATE_SEND_INVALID_RESULT)
    return RECEIPT_TEMPLATE.format(**receipt.as_dict())


@dataclass(frozen=True)
class DelegateResultEnvelope:
    """One canonical, versioned result identity for one settled terminal."""

    event_id: str
    task_ref: str
    turn_ref: str | None
    session_id: str
    terminal: str
    full_result_ref: str
    truncated: bool = False
    truncate_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": DELEGATE_RESULT_ENVELOPE_TYPE,
            "version": DELEGATE_RESULT_ENVELOPE_VERSION,
            "event_id": self.event_id,
            "task_ref": self.task_ref,
            "turn_ref": self.turn_ref,
            "session_id": self.session_id,
            "terminal": self.terminal,
            "full_result_ref": self.full_result_ref,
            "truncated": self.truncated,
            "truncate_reason": self.truncate_reason,
        }


def build_result_envelope(
    *,
    event_id: str,
    task_ref: str,
    turn_ref: str | None,
    session_id: str,
    terminal: str,
    full_result_ref: str,
    truncated: bool = False,
    truncate_reason: str | None = None,
) -> DelegateResultEnvelope:
    """Build the one envelope a terminal produces, or fail closed."""

    if terminal not in DELEGATE_TERMINALS:
        raise ValueError(SACHIMA_DELEGATE_SEND_INVALID_RESULT)
    return DelegateResultEnvelope(
        event_id=event_id,
        task_ref=task_ref,
        turn_ref=turn_ref,
        session_id=session_id,
        terminal=terminal,
        full_result_ref=full_result_ref,
        truncated=bool(truncated),
        truncate_reason=truncate_reason,
    )


def render_result_body(
    envelope: DelegateResultEnvelope,
    full_result_text: str,
    *,
    limit: int,
    measure: Callable[[str], int] = len,
) -> str:
    """One bounded plain-text body that always carries the full-result ref.

    The ref's room is reserved *first*. Truncating the answer and then finding
    there is no space left for the pointer to the untruncated one would produce
    exactly the message this design exists to avoid: a clipped answer with no
    way back to the rest of it.
    """

    if type(envelope) is not DelegateResultEnvelope:
        raise ValueError(SACHIMA_DELEGATE_SEND_INVALID_RESULT)
    if isinstance(limit, bool) or type(limit) is not int or limit < 1:
        raise ValueError(SACHIMA_DELEGATE_SEND_INVALID_RESULT)

    header = RESULT_HEADER_TEMPLATE[envelope.terminal].format(task_ref=envelope.task_ref)
    ref_line = RESULT_REF_TEMPLATE.format(full_result_ref=envelope.full_result_ref)
    answer = full_result_text if type(full_result_text) is str else ""
    answer = answer.strip() or RESULT_EMPTY_BODY

    frame = f"{header}\n\n{ref_line}"
    available = limit - measure(frame) - measure("\n\n")
    notice_cost = measure(RESULT_TRUNCATED_NOTICE) + measure("\n")

    if available <= 0:
        # No room for any answer at all: the pointer still goes out, because a
        # reachable result beats a body that fits.
        return frame

    if measure(answer) <= available:
        body = answer
        truncated = envelope.truncated
    else:
        body = _clip(answer, max(available - notice_cost, 0), measure)
        truncated = True

    parts = [header, "", body]
    if truncated:
        parts.append(RESULT_TRUNCATED_NOTICE)
    parts.extend(["", ref_line])
    return "\n".join(parts)


def _clip(text: str, budget: int, measure: Callable[[str], int]) -> str:
    """Clip ``text`` to ``budget`` under the platform's own length metric."""

    if budget <= 0:
        return ""
    if measure(text) <= budget:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if measure(text[:middle]) <= budget:
            low = middle
        else:
            high = middle - 1
    return text[:low]


def build_hermes_context(
    envelope: DelegateResultEnvelope, full_result_text: str
) -> str:
    """The next-turn Hermes projection of one result.

    Deliberately a bounded excerpt plus the ref, not the whole answer: this text
    joins the *next ordinary turn*, so it must not grow a conversation's context
    by however large an external agent's output happened to be. The ref is how
    the model reads the rest, on purpose.
    """

    if type(envelope) is not DelegateResultEnvelope:
        raise ValueError(SACHIMA_DELEGATE_SEND_INVALID_RESULT)
    header = HERMES_CONTEXT_TEMPLATE.format(
        task_ref=envelope.task_ref,
        terminal=envelope.terminal,
        full_result_ref=envelope.full_result_ref,
    )
    answer = (full_result_text if type(full_result_text) is str else "").strip()
    if not answer:
        return header
    excerpt = answer[:HERMES_CONTEXT_EXCERPT_CHARS]
    if len(answer) > HERMES_CONTEXT_EXCERPT_CHARS:
        excerpt = excerpt + RESULT_TRUNCATED_NOTICE
    return f"{header}\n{excerpt}"


# --------------------------------------------------------------------------- #
# Delivery settlement (I6) — total over SendResult
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SendSettlement:
    """One send attempt's durable outcome. ``state`` is never ``in_flight``."""

    state: str
    message_id: str | None = field(default=None, repr=False)
    diagnostic: str | None = None

    @property
    def confirmed(self) -> bool:
        return self.state == "confirmed"


#: The settlement a caller seeds before an attempt and keeps if the attempt
#: never returns one. Persisting it in a ``finally`` is what makes "no valid
#: branch leaves a send ``in_flight``" hold through cancellation too, without
#: this module having to swallow a ``CancelledError`` to say so.
UNCERTAIN_SETTLEMENT = SendSettlement(
    state="uncertain", diagnostic=SACHIMA_DELEGATE_SEND_UNCERTAIN
)


def settle_send_result(result: Any) -> SendSettlement:
    """Map one adapter return value to its durable settlement.

    ``success`` is the whole predicate. A confirmed send with no message id is
    still confirmed — Feishu legitimately returns one — and an id on a failed
    send does not rescue it. Anything that is not a well-formed result is
    ``uncertain``: the adapter may or may not have delivered, and inventing
    either answer would be worse than admitting the gap.
    """

    success = getattr(result, "success", None)
    message_id = getattr(result, "message_id", None)
    if type(success) is not bool:
        return SendSettlement(
            state="uncertain", diagnostic=SACHIMA_DELEGATE_SEND_INVALID_RESULT
        )
    if message_id is not None and type(message_id) is not str:
        return SendSettlement(
            state="uncertain", diagnostic=SACHIMA_DELEGATE_SEND_INVALID_RESULT
        )
    if success:
        return SendSettlement(state="confirmed", message_id=message_id)
    return SendSettlement(
        state="failed",
        message_id=message_id,
        diagnostic=SACHIMA_DELEGATE_SEND_FAILED,
    )


async def perform_settled_send(
    send: Callable[[], Awaitable[Any]],
) -> SendSettlement:
    """Run one send attempt and settle it, whatever it does.

    An exception is ``uncertain`` rather than failed: a raised send may still
    have reached the platform, and the two are not the same fact. Cancellation
    settles the same way and then propagates — the record of the attempt is what
    must survive, not the cancellation being swallowed.
    """

    try:
        return settle_send_result(await send())
    except asyncio.CancelledError:
        raise
    except BaseException:
        # One stable diagnostic — never the adapter's exception text, which can
        # carry chat ids, tokens, and remote message bodies.
        return SendSettlement(
            state="uncertain", diagnostic=SACHIMA_DELEGATE_SEND_UNCERTAIN
        )
