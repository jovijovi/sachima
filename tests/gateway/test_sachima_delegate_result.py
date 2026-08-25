"""S3 — accepted receipts, the result envelope, and total delivery settlement.

Pure primitives, proven before any lifecycle depends on them:

* the accepted receipt's value fields are named **exactly** ``requested_agent`` /
  ``requested_model`` / ``requested_effort``, they come from the resolved
  selected-profile request, and nothing renders them as effective values;
* every ``SendResult`` branch lands in a documented durable settlement — the
  legitimate ``success=True, message_id=None`` included — and none of them
  leaves a send ``in_flight``;
* an oversized answer becomes **one** bounded body that still carries the
  durable full-result ref, while the ref itself reads back the untruncated
  answer.

No coordinator, adapter, Gateway, socket, or daemon is involved.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from gateway.platforms.base import SendResult
from gateway.sachima_delegate_result import (
    DELEGATE_RESULT_ENVELOPE_TYPE,
    DELEGATE_RESULT_ENVELOPE_VERSION,
    RESULT_HEADER_TEMPLATE,
    RESULT_SUMMARY_LABEL,
    RESULT_SUMMARY_UNAVAILABLE_SUFFIX,
    RESULT_TRUNCATED_NOTICE,
    SACHIMA_DELEGATE_SEND_FAILED,
    SACHIMA_DELEGATE_SEND_INVALID_RESULT,
    SACHIMA_DELEGATE_SEND_UNCERTAIN,
    SEND_SETTLEMENT_STATES,
    UNCERTAIN_SETTLEMENT,
    DelegateAcceptedReceipt,
    build_hermes_context,
    build_result_envelope,
    perform_settled_send,
    projected_summary_reason,
    projected_summary_text,
    render_accepted_receipt,
    render_result_body,
    settle_send_result,
)
from gateway.sachima_delegate_state import DelegateStateStore
from gateway.sachima_delegate_summary import (
    SUMMARY_CONTEXT_BUDGET_CHARS,
    SUMMARY_REASON_NO_PROVIDER,
    SUMMARY_REASON_SOURCE_DRIFT,
    SUMMARY_REASON_SOURCE_INCOMPLETE,
    SUMMARY_REASON_SOURCE_MISSING,
    SUMMARY_REASON_SUMMARY_MISSING,
    claimed_summary,
    compute_source_digest,
    pending_summary,
    ready_summary,
    unavailable_summary,
)

ANSWER_CANARY = "the external agent's full answer, which is long and specific"
SUMMARY_CANARY = "Sachima 的结论：可以合并；证据：受影响测试全绿。"
SOURCE_DIGEST = compute_source_digest(ANSWER_CANARY)
EVENT_ID = "devt_1"


def _receipt() -> DelegateAcceptedReceipt:
    return DelegateAcceptedReceipt(
        task_ref="dtask_abc",
        requested_agent="author-agent",
        requested_model="claude-opus-5",
        requested_effort="xhigh",
    )


def _envelope(**overrides):
    fields = {
        "event_id": "devt_1",
        "task_ref": "dtask_abc",
        "turn_ref": "run_deadbeef",
        "session_id": "20260819_000000_abcd1234",
        "terminal": "completed",
        "full_result_ref": "dres_" + "a" * 8,
    }
    fields.update(overrides)
    return build_result_envelope(**fields)


def _pending(full_result_ref: str = "dres_" + "a" * 8):
    return pending_summary(
        event_id=EVENT_ID,
        full_result_ref=full_result_ref,
        source_digest=compute_source_digest(ANSWER_CANARY),
    )


def _claimed(full_result_ref: str = "dres_" + "a" * 8):
    return claimed_summary(_pending(full_result_ref))


def _ready(
    full_result_ref: str = "dres_" + "a" * 8, summary_text: str = SUMMARY_CANARY
):
    return ready_summary(
        _claimed(full_result_ref), summary_text=summary_text, generator_ref="stub"
    )


def _unavailable(reason: str, full_result_ref: str = "dres_" + "a" * 8):
    return unavailable_summary(_pending(full_result_ref), reason=reason)


# --------------------------------------------------------------------------- #
# A. The accepted receipt (A11)
# --------------------------------------------------------------------------- #
def test_the_receipt_names_exactly_the_three_requested_fields():
    payload = _receipt().as_dict()
    assert set(payload) == {
        "task_ref",
        "requested_agent",
        "requested_model",
        "requested_effort",
    }
    assert payload["requested_agent"] == "author-agent"
    assert payload["requested_model"] == "claude-opus-5"
    assert payload["requested_effort"] == "xhigh"


def test_the_receipt_never_describes_its_values_as_effective():
    rendered = render_accepted_receipt(_receipt())
    assert "author-agent" in rendered
    assert "claude-opus-5" in rendered
    assert "xhigh" in rendered
    lowered = rendered.lower()
    assert "effective" not in lowered
    assert "last_effective" not in lowered


def test_the_receipt_refuses_a_forged_object():
    with pytest.raises(ValueError) as excinfo:
        render_accepted_receipt({"task_ref": "dtask_abc"})
    assert str(excinfo.value) == SACHIMA_DELEGATE_SEND_INVALID_RESULT


# --------------------------------------------------------------------------- #
# B. Settlement is total over SendResult (I6 / A11)
# --------------------------------------------------------------------------- #
def test_success_with_a_message_id_is_confirmed_and_keeps_the_id():
    settlement = settle_send_result(SendResult(success=True, message_id="om_1"))
    assert settlement.state == "confirmed"
    assert settlement.message_id == "om_1"
    assert settlement.diagnostic is None


def test_success_without_a_message_id_is_still_confirmed():
    """Feishu really does return this. ``success`` is the whole predicate."""

    settlement = settle_send_result(SendResult(success=True, message_id=None))
    assert settlement.state == "confirmed"
    assert settlement.message_id is None


def test_failure_is_failed_even_when_an_id_came_back():
    settlement = settle_send_result(
        SendResult(success=False, message_id="om_2", error="boom")
    )
    assert settlement.state == "failed"
    assert settlement.diagnostic == SACHIMA_DELEGATE_SEND_FAILED
    # The adapter's own error text is not a stable code and never travels.
    assert "boom" not in json.dumps(
        [settlement.state, settlement.diagnostic, settlement.message_id]
    )


@pytest.mark.parametrize("invalid", [None, object(), "ok", 1, SendResult(success="yes")])
def test_an_invalid_return_is_uncertain_not_a_guess(invalid):
    settlement = settle_send_result(invalid)
    assert settlement.state == "uncertain"
    assert settlement.diagnostic == SACHIMA_DELEGATE_SEND_INVALID_RESULT


def test_every_settlement_state_is_in_the_closed_vocabulary():
    for candidate in (
        SendResult(success=True),
        SendResult(success=False),
        object(),
    ):
        assert settle_send_result(candidate).state in SEND_SETTLEMENT_STATES
        assert settle_send_result(candidate).state != "in_flight"


def test_a_raising_send_settles_uncertain_without_echoing_the_exception():
    async def _boom():
        raise RuntimeError("chat oc_secret rejected token abcdef")

    settlement = asyncio.run(perform_settled_send(_boom))
    assert settlement.state == "uncertain"
    assert settlement.diagnostic == SACHIMA_DELEGATE_SEND_UNCERTAIN
    assert "oc_secret" not in str(settlement.diagnostic)


def test_a_cancelled_send_propagates_and_the_seeded_settlement_is_uncertain():
    """Cancellation is not swallowed; the caller's seeded record is what stands."""

    async def _drive():
        async def _hang():
            await asyncio.sleep(10)

        settlement = UNCERTAIN_SETTLEMENT
        task = asyncio.create_task(perform_settled_send(_hang))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            settlement = await task
        assert settlement.state == "uncertain"
        assert settlement.diagnostic == SACHIMA_DELEGATE_SEND_UNCERTAIN

    asyncio.run(_drive())


def test_a_successful_send_returns_the_adapters_own_settlement():
    async def _ok():
        return SendResult(success=True, message_id="om_9")

    settlement = asyncio.run(perform_settled_send(_ok))
    assert settlement.state == "confirmed" and settlement.message_id == "om_9"


# --------------------------------------------------------------------------- #
# C. One bounded body carrying the Sachima summary and the ref (I8 / A16)
# --------------------------------------------------------------------------- #
def test_a_ready_summary_is_rendered_whole_labelled_and_with_the_ref():
    envelope = _envelope()
    body = render_result_body(
        envelope, _ready(), source_digest=SOURCE_DIGEST, limit=8000
    )
    assert SUMMARY_CANARY in body
    assert RESULT_SUMMARY_LABEL in body
    assert envelope.full_result_ref in body
    assert envelope.task_ref in body
    assert RESULT_TRUNCATED_NOTICE not in body
    # The derivative is attributed. It never passes as the AGENT's own wording.
    assert body.index(RESULT_SUMMARY_LABEL) < body.index(SUMMARY_CANARY)


def test_the_body_shows_the_summary_and_never_the_source_answer():
    body = render_result_body(
        _envelope(), _ready(), source_digest=SOURCE_DIGEST, limit=8000
    )
    assert ANSWER_CANARY not in body
    assert SUMMARY_CANARY in body


@pytest.mark.parametrize(
    "summary",
    [
        None,
        ANSWER_CANARY,
        _unavailable(SUMMARY_REASON_SOURCE_INCOMPLETE),
        _unavailable(SUMMARY_REASON_NO_PROVIDER),
        _claimed(),
        _pending(),
    ],
)
def test_an_unusable_summary_says_so_and_still_points_at_the_original(summary):
    """Never an answer prefix — an honest unavailable, and always the ref."""

    envelope = _envelope()
    body = render_result_body(
        envelope, summary, source_digest=SOURCE_DIGEST, limit=8000
    )
    assert RESULT_SUMMARY_UNAVAILABLE_SUFFIX in body
    assert envelope.full_result_ref in body
    assert RESULT_SUMMARY_LABEL not in body
    assert ANSWER_CANARY not in body


def test_a_summary_bound_to_another_source_is_refused_rather_than_shown():
    drifted = _ready(full_result_ref="dres_" + "f" * 8)
    envelope = _envelope()
    body = render_result_body(
        envelope, drifted, source_digest=SOURCE_DIGEST, limit=8000
    )
    assert SUMMARY_CANARY not in body
    assert RESULT_SUMMARY_UNAVAILABLE_SUFFIX in body
    assert envelope.full_result_ref in body
    assert (
        projected_summary_reason(
            drifted,
            full_result_ref=envelope.full_result_ref,
            source_digest=SOURCE_DIGEST,
        )
        == SUMMARY_REASON_SOURCE_DRIFT
    )


def test_platform_clipping_keeps_the_label_and_the_ref(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    huge = "长" * 5000 + ANSWER_CANARY
    full_ref, clipped = store.put_full_result(huge)
    assert clipped is False

    envelope = _envelope(full_result_ref=full_ref)
    long_summary = "摘" * SUMMARY_CONTEXT_BUDGET_CHARS
    body = render_result_body(
        envelope,
        _ready(full_result_ref=full_ref, summary_text=long_summary),
        source_digest=SOURCE_DIGEST,
        limit=400,
    )

    assert len(body) <= 400
    assert full_ref in body
    assert RESULT_SUMMARY_LABEL in body
    assert RESULT_TRUNCATED_NOTICE in body
    # Presentation was clipped; the stored original is untouched behind its ref.
    assert store.read_full_result(full_ref) == huge
    assert len(store.read_full_result(full_ref)) > len(body)


def test_the_ref_survives_even_when_the_bound_leaves_no_room_for_a_summary():
    envelope = _envelope()
    body = render_result_body(
        envelope, _ready(), source_digest=SOURCE_DIGEST, limit=40
    )
    assert envelope.full_result_ref in body
    assert SUMMARY_CANARY not in body


def test_the_platforms_own_length_metric_is_what_bounds_the_body():
    envelope = _envelope()

    def _double(text: str) -> int:
        return 2 * len(text)

    body = render_result_body(
        envelope,
        _ready(),
        source_digest=SOURCE_DIGEST,
        limit=400,
        measure=_double,
    )
    assert _double(body) <= 400 + 2 * len(envelope.full_result_ref)
    assert envelope.full_result_ref in body


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
def test_every_terminal_renders_one_body_with_the_ref_and_its_own_truth(terminal):
    envelope = _envelope(terminal=terminal)
    body = render_result_body(
        envelope, _ready(), source_digest=SOURCE_DIGEST, limit=8000
    )
    assert envelope.full_result_ref in body
    assert envelope.task_ref in body
    assert body.startswith(
        RESULT_HEADER_TEMPLATE[terminal].format(task_ref=envelope.task_ref)
    )
    # A summary of a failed Run does not make the Run look completed.
    for other in {"completed", "failed", "cancelled"} - {terminal}:
        assert not body.startswith(
            RESULT_HEADER_TEMPLATE[other].format(task_ref=envelope.task_ref)
        )


def test_an_unknown_terminal_cannot_become_an_envelope():
    with pytest.raises(ValueError) as excinfo:
        _envelope(terminal="timed_out")
    assert str(excinfo.value) == SACHIMA_DELEGATE_SEND_INVALID_RESULT


def test_a_forged_envelope_or_bound_is_refused():
    for bad_limit in (0, -1, True, "4000"):
        with pytest.raises(ValueError) as excinfo:
            render_result_body(
                _envelope(), _ready(), source_digest=SOURCE_DIGEST, limit=bad_limit
            )
        assert str(excinfo.value) == SACHIMA_DELEGATE_SEND_INVALID_RESULT
    with pytest.raises(ValueError):
        render_result_body(
            {"terminal": "completed"},
            _ready(),
            source_digest=SOURCE_DIGEST,
            limit=8000,
        )
    with pytest.raises(ValueError):
        build_hermes_context(
            {"terminal": "completed"}, _ready(), source_digest=SOURCE_DIGEST
        )


# --------------------------------------------------------------------------- #
# D. The envelope and the shared Hermes projection
# --------------------------------------------------------------------------- #
def test_the_envelope_is_versioned_and_carries_one_identity():
    payload = _envelope().as_dict()
    assert payload["type"] == DELEGATE_RESULT_ENVELOPE_TYPE
    assert payload["version"] == DELEGATE_RESULT_ENVELOPE_VERSION
    assert payload["event_id"] == "devt_1"
    assert payload["turn_ref"] == "run_deadbeef"
    assert payload["full_result_ref"].startswith("dres_")


def test_the_hermes_projection_names_sachima_the_summary_and_the_ref():
    envelope = _envelope()
    context = build_hermes_context(
        envelope, _ready(), source_digest=SOURCE_DIGEST
    )
    assert envelope.full_result_ref in context
    assert envelope.task_ref in context
    assert "terminal=completed" in context
    assert "summary_source=sachima" in context
    assert "summary_status=ready" in context
    assert context.endswith(SUMMARY_CANARY)
    assert ANSWER_CANARY not in context


@pytest.mark.parametrize(
    "summary,reason",
    [
        (_unavailable(SUMMARY_REASON_SOURCE_INCOMPLETE), SUMMARY_REASON_SOURCE_INCOMPLETE),
        (_unavailable(SUMMARY_REASON_NO_PROVIDER), SUMMARY_REASON_NO_PROVIDER),
        (_pending(), SUMMARY_REASON_SUMMARY_MISSING),
        (None, SUMMARY_REASON_SUMMARY_MISSING),
        (ANSWER_CANARY, SUMMARY_REASON_SUMMARY_MISSING),
    ],
)
def test_an_unavailable_hermes_projection_names_its_reason_and_no_source_prefix(
    summary, reason
):
    envelope = _envelope()
    context = build_hermes_context(
        envelope, summary, source_digest=SOURCE_DIGEST
    )
    assert "summary_status=unavailable" in context
    assert f"reason={reason}" in context
    assert envelope.full_result_ref in context
    # The retired behavior: no slice of the answer survives anywhere here.
    assert ANSWER_CANARY not in context
    assert ANSWER_CANARY[:20] not in context
    assert len(context.splitlines()) == 2


def test_the_hermes_projection_is_bounded_by_the_shared_summary_budget():
    context = build_hermes_context(
        _envelope(),
        _ready(summary_text="摘" * SUMMARY_CONTEXT_BUDGET_CHARS),
        source_digest=SOURCE_DIGEST,
    )
    assert SUMMARY_CONTEXT_BUDGET_CHARS == 800
    assert len(context) < 2 * SUMMARY_CONTEXT_BUDGET_CHARS


def test_the_user_and_the_next_turn_read_the_same_persisted_summary():
    """One derivative, two projections — never two independent readings."""

    envelope = _envelope()
    summary = _ready()
    body = render_result_body(
        envelope, summary, source_digest=SOURCE_DIGEST, limit=8000
    )
    context = build_hermes_context(
        envelope, summary, source_digest=SOURCE_DIGEST
    )
    assert summary.summary_text is not None
    assert summary.summary_text in body
    assert summary.summary_text in context
    assert envelope.full_result_ref in body
    assert envelope.full_result_ref in context
    assert (
        projected_summary_text(
            summary,
            full_result_ref=envelope.full_result_ref,
            source_digest=SOURCE_DIGEST,
        )
        == summary.summary_text
    )


def test_the_retired_fixed_head_excerpt_control_is_gone():
    import gateway.sachima_delegate_result as result_module

    assert not hasattr(result_module, "HERMES_CONTEXT_EXCERPT_CHARS")
    assert not hasattr(result_module, "RESULT_EMPTY_BODY")


# --------------------------------------------------------------------------- #
# E. A ready summary is re-verified against the source at every projection
# --------------------------------------------------------------------------- #
def test_a_ready_summary_is_projected_only_against_its_own_current_source():
    envelope = _envelope()
    summary = _ready()
    current = compute_source_digest(ANSWER_CANARY)
    assert (
        projected_summary_text(
            summary, full_result_ref=envelope.full_result_ref, source_digest=current
        )
        == SUMMARY_CANARY
    )
    assert SUMMARY_CANARY in render_result_body(
        envelope, summary, source_digest=current, limit=8000
    )
    assert SUMMARY_CANARY in build_hermes_context(
        envelope, summary, source_digest=current
    )


@pytest.mark.parametrize(
    "current,reason",
    [
        (compute_source_digest(ANSWER_CANARY + " replaced"), SUMMARY_REASON_SOURCE_DRIFT),
        (compute_source_digest(""), SUMMARY_REASON_SOURCE_DRIFT),
        ("", SUMMARY_REASON_SOURCE_MISSING),
    ],
)
def test_a_ready_summary_over_a_changed_or_gone_source_is_never_projected(
    current, reason
):
    """A derivative outlives its source only as an honest unavailable."""

    envelope = _envelope()
    summary = _ready()
    assert (
        projected_summary_text(
            summary, full_result_ref=envelope.full_result_ref, source_digest=current
        )
        is None
    )
    assert (
        projected_summary_reason(
            summary, full_result_ref=envelope.full_result_ref, source_digest=current
        )
        == reason
    )

    body = render_result_body(envelope, summary, source_digest=current, limit=8000)
    assert SUMMARY_CANARY not in body
    assert RESULT_SUMMARY_LABEL not in body
    assert RESULT_SUMMARY_UNAVAILABLE_SUFFIX in body
    assert envelope.full_result_ref in body

    context = build_hermes_context(envelope, summary, source_digest=current)
    assert SUMMARY_CANARY not in context
    assert "summary_status=unavailable" in context
    assert f"reason={reason}" in context
    assert envelope.full_result_ref in context


def test_a_ready_summary_over_a_now_incomplete_source_is_never_projected():
    """Both sinks re-check completeness, not only the stored source digest."""

    envelope = _envelope(truncated=True, truncate_reason="ars_limit")
    summary = _ready()
    body = render_result_body(envelope, summary, source_digest=SOURCE_DIGEST, limit=8000)
    assert SUMMARY_CANARY not in body
    assert RESULT_SUMMARY_LABEL not in body
    assert RESULT_SUMMARY_UNAVAILABLE_SUFFIX in body
    assert envelope.full_result_ref in body

    context = build_hermes_context(envelope, summary, source_digest=SOURCE_DIGEST)
    assert SUMMARY_CANARY not in context
    assert "summary_status=unavailable" in context
    assert f"reason={SUMMARY_REASON_SOURCE_INCOMPLETE}" in context
    assert envelope.full_result_ref in context


def test_an_unavailable_summary_stays_honest_whatever_the_source_now_is():
    """Its reason never depended on the bytes, so a gone source cannot spoil it."""

    envelope = _envelope()
    summary = _unavailable(SUMMARY_REASON_SOURCE_INCOMPLETE)
    for current in ("", compute_source_digest("something else entirely")):
        context = build_hermes_context(envelope, summary, source_digest=current)
        assert f"reason={SUMMARY_REASON_SOURCE_INCOMPLETE}" in context
        assert envelope.full_result_ref in context
        body = render_result_body(envelope, summary, source_digest=current, limit=8000)
        assert RESULT_SUMMARY_UNAVAILABLE_SUFFIX in body
        assert envelope.full_result_ref in body


def test_the_projection_cannot_be_asked_to_skip_verification():
    """``source_digest`` is required: an unverified projection is unreachable."""

    envelope = _envelope()
    summary = _ready()
    for call in (
        lambda: projected_summary_text(summary, full_result_ref=envelope.full_result_ref),
        lambda: projected_summary_reason(summary, full_result_ref=envelope.full_result_ref),
        lambda: render_result_body(envelope, summary, limit=8000),
        lambda: build_hermes_context(envelope, summary),
    ):
        with pytest.raises(TypeError):
            call()
