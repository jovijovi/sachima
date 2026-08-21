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
    render_accepted_receipt,
    render_result_body,
    settle_send_result,
)
from gateway.sachima_delegate_state import DelegateStateStore

ANSWER_CANARY = "the external agent's full answer, which is long and specific"


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
# C. One bounded body that still carries the ref (I8 / A16)
# --------------------------------------------------------------------------- #
def test_a_small_answer_is_rendered_whole_with_the_ref():
    envelope = _envelope()
    body = render_result_body(envelope, ANSWER_CANARY, limit=8000)
    assert ANSWER_CANARY in body
    assert envelope.full_result_ref in body
    assert RESULT_TRUNCATED_NOTICE not in body
    assert envelope.task_ref in body


def test_an_oversized_answer_becomes_one_bounded_body_that_still_points_at_it(
    tmp_path,
):
    store = DelegateStateStore(str(tmp_path / "state"))
    huge = "长" * 5000 + ANSWER_CANARY
    full_ref, clipped = store.put_full_result(huge)
    assert clipped is False

    envelope = _envelope(full_result_ref=full_ref)
    body = render_result_body(envelope, huge, limit=400)

    assert len(body) <= 400
    assert body.count("\n\n") >= 1
    assert full_ref in body
    assert RESULT_TRUNCATED_NOTICE in body
    # The claim-check still reads back the untruncated answer.
    assert store.read_full_result(full_ref) == huge
    assert len(store.read_full_result(full_ref)) > len(body)


def test_the_ref_survives_even_when_the_bound_leaves_no_room_for_an_answer():
    envelope = _envelope()
    body = render_result_body(envelope, ANSWER_CANARY, limit=40)
    assert envelope.full_result_ref in body


def test_the_platforms_own_length_metric_is_what_bounds_the_body():
    envelope = _envelope()

    def _double(text: str) -> int:
        return 2 * len(text)

    body = render_result_body(envelope, ANSWER_CANARY, limit=400, measure=_double)
    assert _double(body) <= 400 + 2 * len(envelope.full_result_ref)
    assert envelope.full_result_ref in body


def test_an_empty_answer_says_so_rather_than_looking_silent():
    body = render_result_body(_envelope(), "   ", limit=8000)
    assert "（无输出）" in body


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
def test_every_terminal_renders_one_body_with_the_ref(terminal):
    envelope = _envelope(terminal=terminal)
    body = render_result_body(envelope, ANSWER_CANARY, limit=8000)
    assert envelope.full_result_ref in body
    assert envelope.task_ref in body


def test_an_unknown_terminal_cannot_become_an_envelope():
    with pytest.raises(ValueError) as excinfo:
        _envelope(terminal="timed_out")
    assert str(excinfo.value) == SACHIMA_DELEGATE_SEND_INVALID_RESULT


# --------------------------------------------------------------------------- #
# D. The envelope and the Hermes projection
# --------------------------------------------------------------------------- #
def test_the_envelope_is_versioned_and_carries_one_identity():
    payload = _envelope().as_dict()
    assert payload["type"] == DELEGATE_RESULT_ENVELOPE_TYPE
    assert payload["version"] == DELEGATE_RESULT_ENVELOPE_VERSION
    assert payload["event_id"] == "devt_1"
    assert payload["turn_ref"] == "run_deadbeef"
    assert payload["full_result_ref"].startswith("dres_")


def test_the_hermes_projection_is_bounded_and_names_the_ref():
    envelope = _envelope()
    context = build_hermes_context(envelope, "x" * 5000)
    assert envelope.full_result_ref in context
    assert envelope.task_ref in context
    assert "completed" in context
    assert len(context) < 2000
    assert RESULT_TRUNCATED_NOTICE in context


def test_the_hermes_projection_of_an_empty_answer_is_just_the_header():
    context = build_hermes_context(_envelope(), "")
    assert context.startswith("[external-agent-result]")
    assert "\n" not in context
