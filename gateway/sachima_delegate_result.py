"""Sachima delegation — accepted receipts, result envelopes, delivery settlement.

Three primitives, all pure, all usable before any coordinator exists:

1. **The accepted receipt.** Its three value fields are named exactly
   ``requested_agent`` / ``requested_model`` / ``requested_effort`` and are
   sourced from the admitted execution preset's request. They state what Sachima
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

Both projections show the **same** durable derivative. What the user reads and
what the next ordinary Hermes turn reads come from one persisted
:class:`~gateway.sachima_delegate_summary.DelegateResultSummary`, explicitly
labelled as Sachima's own reading — never from the external AGENT's wording, and
never from two independently generated summaries that could disagree about one
terminal. A summary that is not ``ready``, or that is bound to a different
source than the envelope names, projects as an honest "summary unavailable"; it
never degrades into the answer's first characters, which is the behavior this
module exists to retire.

The visible IM body is bounded **before** the send: it reserves room for the
full-result ref, clips the *summary* to the platform's one-message text bound,
and says it clipped. The original answer stays behind its ref on every path,
including the one where nothing else fits. Splitting afterwards would turn one
terminal into several messages, and provider-visible exactly-once is not
something a host can claim — what it can guarantee is one durable result, one
logical body per attempt, and a settled record of every attempt.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from gateway.sachima_delegate_summary import (
    SUMMARY_CONTEXT_BUDGET_CHARS,
    SUMMARY_REASON_SOURCE_DRIFT,
    SUMMARY_REASON_SOURCE_INCOMPLETE,
    SUMMARY_REASON_SOURCE_MISSING,
    SUMMARY_REASON_SUMMARY_MISSING,
    SUMMARY_SOURCE,
    DelegateResultSummary,
    summary_binds_source,
)

__all__ = [
    "UNCERTAIN_SETTLEMENT",
    "DELEGATE_RESULT_ENVELOPE_TYPE",
    "DELEGATE_RESULT_ENVELOPE_VERSION",
    "SEND_SETTLEMENT_STATES",
    "SACHIMA_DELEGATE_SEND_FAILED",
    "SACHIMA_DELEGATE_SEND_INVALID_RESULT",
    "SACHIMA_DELEGATE_SEND_UNCERTAIN",
    "RESULT_SUMMARY_LABEL",
    "DelegateAcceptedReceipt",
    "DelegateResultEnvelope",
    "SendSettlement",
    "build_hermes_context",
    "build_result_envelope",
    "perform_settled_send",
    "projected_summary_reason",
    "projected_summary_text",
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
#: The header states the terminal truth. A failed or cancelled Run says so even
#: when a summary of its output exists.
RESULT_HEADER_TEMPLATE = {
    "completed": "外部 AGENT 已完成任务 {task_ref}",
    "failed": "外部 AGENT 执行任务 {task_ref} 失败",
    "cancelled": "外部 AGENT 任务 {task_ref} 已取消",
}
#: Attribution, not decoration. The summary is Sachima's reading of the answer,
#: and a derivative that could pass as the AGENT's own wording would be a claim
#: nobody made.
RESULT_SUMMARY_LABEL = "Sachima 摘要："
RESULT_SUMMARY_UNAVAILABLE_SUFFIX = "，摘要暂不可用"
RESULT_REF_TEMPLATE = "完整原文：{full_result_ref}"
RESULT_TRUNCATED_NOTICE = "（输出已截断）"
HERMES_CONTEXT_TEMPLATE = (
    "[external-agent-result] task={task_ref} terminal={terminal} "
    "full_result_ref={full_result_ref}"
)
HERMES_SUMMARY_READY_TEMPLATE = f"summary_source={SUMMARY_SOURCE} summary_status=ready"
HERMES_SUMMARY_UNAVAILABLE_TEMPLATE = (
    f"summary_source={SUMMARY_SOURCE} summary_status=unavailable reason={{reason}}"
)


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


def projected_summary_text(
    summary: Any, *, full_result_ref: str, source_digest: str
) -> str | None:
    """The one summary text both sinks may show, or ``None`` if there is none.

    Fails closed on every doubt: a record that is not ``ready``, is not bound to
    the source the envelope names, or somehow exceeds the shared budget projects
    as nothing at all. There is deliberately no repair branch — a summary this
    function is unsure about is one the user should be told is unavailable.
    """

    text, _reason = _validated_summary_projection(
        summary,
        full_result_ref=full_result_ref,
        source_digest=source_digest,
        source_truncated=False,
    )
    return text


def projected_summary_reason(
    summary: Any, *, full_result_ref: str, source_digest: str
) -> str:
    """The stable code that explains an unavailable projection."""

    _text, reason = _validated_summary_projection(
        summary,
        full_result_ref=full_result_ref,
        source_digest=source_digest,
        source_truncated=False,
    )
    return reason or SUMMARY_REASON_SUMMARY_MISSING


def _validated_summary_projection(
    summary: Any,
    *,
    full_result_ref: str,
    source_digest: str,
    source_truncated: bool,
) -> tuple[str | None, str | None]:
    """Return the one summary projection both sinks are allowed to expose."""

    if type(summary) is not DelegateResultSummary:
        return None, SUMMARY_REASON_SUMMARY_MISSING
    if summary.source_full_result_ref != full_result_ref:
        return None, SUMMARY_REASON_SOURCE_DRIFT
    if summary.summary_status == "unavailable" and summary.unavailable_reason:
        return None, summary.unavailable_reason
    if not source_digest:
        return None, SUMMARY_REASON_SOURCE_MISSING
    if not summary_binds_source(
        summary,
        full_result_ref=full_result_ref,
        source_digest=source_digest,
    ):
        return None, SUMMARY_REASON_SOURCE_DRIFT
    if not summary.ready:
        return None, SUMMARY_REASON_SUMMARY_MISSING
    if source_truncated:
        return None, SUMMARY_REASON_SOURCE_INCOMPLETE
    text = summary.summary_text
    if type(text) is not str or not text.strip():
        return None, SUMMARY_REASON_SUMMARY_MISSING
    if len(text) > SUMMARY_CONTEXT_BUDGET_CHARS:
        return None, SUMMARY_REASON_SUMMARY_MISSING
    return text, None


def render_result_body(
    envelope: DelegateResultEnvelope,
    summary: Any,
    *,
    source_digest: str,
    limit: int,
    measure: Callable[[str], int] = len,
) -> str:
    """One bounded plain-text body that always carries the full-result ref.

    The ref's room is reserved *first*. Clipping the summary and then finding
    there is no space left for the pointer to the original would produce exactly
    the message this design exists to avoid: a partial reading with no way back
    to what it was read from. When not even the label fits, the header and the
    ref still go out — a reachable original beats a body that fits.

    Only the presentation is clipped. The stored derivative is never rewritten,
    and an unavailable summary never becomes the answer's first characters.
    """

    if type(envelope) is not DelegateResultEnvelope:
        raise ValueError(SACHIMA_DELEGATE_SEND_INVALID_RESULT)
    if isinstance(limit, bool) or type(limit) is not int or limit < 1:
        raise ValueError(SACHIMA_DELEGATE_SEND_INVALID_RESULT)

    header = RESULT_HEADER_TEMPLATE[envelope.terminal].format(task_ref=envelope.task_ref)
    ref_line = RESULT_REF_TEMPLATE.format(full_result_ref=envelope.full_result_ref)
    text, _reason = _validated_summary_projection(
        summary,
        full_result_ref=envelope.full_result_ref,
        source_digest=source_digest,
        source_truncated=envelope.truncated,
    )

    if text is None:
        return f"{header}{RESULT_SUMMARY_UNAVAILABLE_SUFFIX}\n\n{ref_line}"

    frame = f"{header}\n\n{RESULT_SUMMARY_LABEL}\n\n{ref_line}"
    available = limit - measure(frame)
    notice_cost = measure(RESULT_TRUNCATED_NOTICE)

    if available <= 0:
        return f"{header}\n\n{ref_line}"

    if measure(text) <= available:
        body = text
        clipped = False
    else:
        body = _clip(text, max(available - notice_cost, 0), measure)
        clipped = True
    if not body:
        return f"{header}\n\n{ref_line}"

    labelled = RESULT_SUMMARY_LABEL + body + (RESULT_TRUNCATED_NOTICE if clipped else "")
    return f"{header}\n\n{labelled}\n\n{ref_line}"


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
    envelope: DelegateResultEnvelope, summary: Any, *, source_digest: str
) -> str:
    """The next-turn Hermes projection of one result.

    The **same** persisted derivative the user was shown, plus the control facts
    and the ref — never a second reading, and never a slice of the original. This
    text joins the *next ordinary turn*, so what bounds it is the summary budget
    the record already satisfied rather than however large the external agent's
    output happened to be. The ref is how the model reads the rest, on purpose.
    """

    if type(envelope) is not DelegateResultEnvelope:
        raise ValueError(SACHIMA_DELEGATE_SEND_INVALID_RESULT)
    header = HERMES_CONTEXT_TEMPLATE.format(
        task_ref=envelope.task_ref,
        terminal=envelope.terminal,
        full_result_ref=envelope.full_result_ref,
    )
    text, reason = _validated_summary_projection(
        summary,
        full_result_ref=envelope.full_result_ref,
        source_digest=source_digest,
        source_truncated=envelope.truncated,
    )
    if text is None:
        reason = reason or SUMMARY_REASON_SUMMARY_MISSING
        return f"{header}\n{HERMES_SUMMARY_UNAVAILABLE_TEMPLATE.format(reason=reason)}"
    return f"{header}\n{HERMES_SUMMARY_READY_TEMPLATE}\n{text}"


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
