"""S1/S2 — the Sachima-derived result summary: contract, gate, and attempt.

The summary is a *derivative*. It is bound to the exact stored source bytes it
was read from, it is generated at most once per result identity, and it may say
``ready`` only when the source it read was complete, readable, and non-empty.

What is proven here:

* the ``pending → in_flight → ready|unavailable`` machine, with both terminals
  immutable and every backwards/sideways move refused;
* ``source_digest`` binds one summary to one exact stored answer, and a drifted
  source is rejected rather than summarised over;
* the record is a strict closed document: unknown keys, foreign statuses, and
  out-of-vocabulary reasons never round-trip;
* the completeness gate maps missing / incomplete / empty / no-provider sources
  to stable codes without ever reaching a provider;
* one provider call per attempt, and timeout, cancellation, exception, empty
  output, over-budget output, and a non-text return all settle to a stable
  ``unavailable`` that carries no provider text.

Pure local/offline: no coordinator, store, adapter, socket, daemon, or AGENT.
Forbidden terms in this prose are no-leak boundary canaries only, never
behavior.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

import pytest

from gateway.sachima_delegate_summary import (
    SACHIMA_DELEGATE_SUMMARY_INVALID,
    SUMMARY_CONTEXT_BUDGET_CHARS,
    SUMMARY_REASON_ATTEMPT_ABANDONED,
    SUMMARY_REASON_NO_PROVIDER,
    SUMMARY_REASON_SOURCE_DRIFT,
    SUMMARY_REASON_SOURCE_EMPTY,
    SUMMARY_REASON_SOURCE_INCOMPLETE,
    SUMMARY_REASON_SOURCE_MISSING,
    SUMMARY_REASON_SUMMARY_EMPTY,
    SUMMARY_REASON_SUMMARY_FAILED,
    SUMMARY_REASON_SUMMARY_OVER_BUDGET,
    SUMMARY_STATUSES,
    SUMMARY_TASK_DESCRIPTION_BUDGET_CHARS,
    SUMMARY_TERMINAL_STATUSES,
    SUMMARY_UNAVAILABLE_REASONS,
    DelegateResultSummary,
    DelegateResultSummaryRequest,
    DelegateSummaryError,
    build_summary_request,
    claimed_summary,
    compute_source_digest,
    derive_summary_ref,
    pending_summary,
    ready_summary,
    sanitize_task_description,
    settle_summary_attempt,
    source_gate_reason,
    summary_binds_source,
    summary_transition_allowed,
    unavailable_summary,
)

EVENT_ID = "devt_" + "a" * 16
FULL_RESULT_REF = "dres_" + "b" * 16
SOURCE_CANARY = "外部 AGENT 的完整原文 with a specific conclusion at the end."
SUMMARY_CANARY = "结论：改动可以合并；证据：三个受影响测试全绿。"


def _pending(**overrides) -> DelegateResultSummary:
    fields = {
        "event_id": EVENT_ID,
        "full_result_ref": FULL_RESULT_REF,
        "source_digest": compute_source_digest(SOURCE_CANARY),
    }
    fields.update(overrides)
    return pending_summary(**fields)


def _request(**overrides) -> DelegateResultSummaryRequest:
    fields = {
        "task_ref": "dtask_abc",
        "terminal": "completed",
        "full_result_ref": FULL_RESULT_REF,
        "source_text": SOURCE_CANARY,
        "source_digest": compute_source_digest(SOURCE_CANARY),
    }
    fields.update(overrides)
    return build_summary_request(**fields)


class _Provider:
    """One injected no-tool summariser, faultable at the one call it gets."""

    def __init__(self, *, text: str = SUMMARY_CANARY, error: BaseException | None = None):
        self.text = text
        self.error = error
        self.requests: list[DelegateResultSummaryRequest] = []
        self.generator_ref = "test-summariser"

    async def summarize(self, request: DelegateResultSummaryRequest) -> str:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.text


# --------------------------------------------------------------------------- #
# A. The derivative record and its closed vocabulary
# --------------------------------------------------------------------------- #
def test_a_pending_record_is_bound_to_its_source_and_says_nothing_yet():
    record = _pending()
    assert record.summary_status == "pending"
    assert record.summary_text is None
    assert record.unavailable_reason is None
    assert record.generator_ref is None
    assert record.source_full_result_ref == FULL_RESULT_REF
    assert record.source_digest == compute_source_digest(SOURCE_CANARY)
    assert record.summary_ref == derive_summary_ref(EVENT_ID)
    assert record.summary_ref.startswith("dsum_")


def test_the_summary_ref_is_deterministic_for_one_result_identity():
    assert derive_summary_ref(EVENT_ID) == derive_summary_ref(EVENT_ID)
    assert derive_summary_ref(EVENT_ID) != derive_summary_ref("devt_" + "c" * 16)


def test_the_status_and_reason_vocabularies_are_closed():
    assert SUMMARY_STATUSES == ("pending", "in_flight", "ready", "unavailable")
    assert SUMMARY_TERMINAL_STATUSES == ("ready", "unavailable")
    assert SUMMARY_REASON_SOURCE_MISSING in SUMMARY_UNAVAILABLE_REASONS
    with pytest.raises(DelegateSummaryError):
        DelegateResultSummary(
            summary_status="summarising",
            summary_ref=derive_summary_ref(EVENT_ID),
            source_full_result_ref=FULL_RESULT_REF,
            source_digest=compute_source_digest(SOURCE_CANARY),
        )
    with pytest.raises(DelegateSummaryError):
        unavailable_summary(_pending(), reason="because the model felt like it")


def test_a_ready_record_needs_text_and_an_unavailable_one_needs_a_reason():
    ready = ready_summary(claimed_summary(_pending()), summary_text=SUMMARY_CANARY)
    assert ready.summary_status == "ready"
    assert ready.summary_text == SUMMARY_CANARY
    assert ready.unavailable_reason is None

    with pytest.raises(DelegateSummaryError):
        DelegateResultSummary(
            summary_status="ready",
            summary_ref=derive_summary_ref(EVENT_ID),
            source_full_result_ref=FULL_RESULT_REF,
            source_digest=compute_source_digest(SOURCE_CANARY),
            summary_text=None,
        )
    with pytest.raises(DelegateSummaryError):
        DelegateResultSummary(
            summary_status="unavailable",
            summary_ref=derive_summary_ref(EVENT_ID),
            source_full_result_ref=FULL_RESULT_REF,
            source_digest="",
            unavailable_reason=None,
        )


def test_a_ready_record_cannot_be_bound_to_an_unreadable_source():
    """No digest means no bytes were read; that can never be a ready summary."""

    with pytest.raises(DelegateSummaryError):
        DelegateResultSummary(
            summary_status="ready",
            summary_ref=derive_summary_ref(EVENT_ID),
            source_full_result_ref=FULL_RESULT_REF,
            source_digest="",
            summary_text=SUMMARY_CANARY,
        )


def test_the_record_is_a_strict_closed_document_that_round_trips():
    record = ready_summary(
        claimed_summary(_pending()),
        summary_text=SUMMARY_CANARY,
        generator_ref="test-summariser",
    )
    document = record.as_dict()
    assert set(document) == {
        "summary_status",
        "summary_text",
        "summary_ref",
        "source_full_result_ref",
        "source_digest",
        "generator_ref",
        "unavailable_reason",
    }
    assert DelegateResultSummary.from_dict(document) == record

    for bad in (
        dict(document, provider_response="raw provider payload"),
        {key: value for key, value in document.items() if key != "source_digest"},
        "not a mapping",
    ):
        with pytest.raises(DelegateSummaryError) as excinfo:
            DelegateResultSummary.from_dict(bad)
        assert str(excinfo.value) == SACHIMA_DELEGATE_SUMMARY_INVALID


def test_the_digest_is_over_the_exact_utf8_source_bytes():
    assert compute_source_digest(SOURCE_CANARY).startswith("sha256:")
    assert compute_source_digest(SOURCE_CANARY) == compute_source_digest(SOURCE_CANARY)
    assert compute_source_digest("长") != compute_source_digest("长 ")
    assert compute_source_digest("") != compute_source_digest("x")


def test_a_summary_only_binds_the_source_it_actually_read():
    record = ready_summary(claimed_summary(_pending()), summary_text=SUMMARY_CANARY)
    assert summary_binds_source(record, full_result_ref=FULL_RESULT_REF)
    assert summary_binds_source(
        record,
        full_result_ref=FULL_RESULT_REF,
        source_digest=compute_source_digest(SOURCE_CANARY),
    )
    assert not summary_binds_source(record, full_result_ref="dres_" + "f" * 16)
    assert not summary_binds_source(
        record,
        full_result_ref=FULL_RESULT_REF,
        source_digest=compute_source_digest(SOURCE_CANARY + " drifted"),
    )


# --------------------------------------------------------------------------- #
# B. The state machine: one claim, two immutable terminals
# --------------------------------------------------------------------------- #
def test_only_forward_transitions_are_allowed():
    assert summary_transition_allowed("pending", "in_flight")
    assert summary_transition_allowed("pending", "unavailable")
    assert summary_transition_allowed("in_flight", "ready")
    assert summary_transition_allowed("in_flight", "unavailable")
    for terminal in SUMMARY_TERMINAL_STATUSES:
        for following in SUMMARY_STATUSES:
            assert not summary_transition_allowed(terminal, following)
    assert not summary_transition_allowed("in_flight", "pending")
    assert not summary_transition_allowed("in_flight", "in_flight")


def test_a_settled_summary_cannot_be_claimed_or_re_settled():
    settled = unavailable_summary(_pending(), reason=SUMMARY_REASON_SOURCE_EMPTY)
    assert settled.settled is True
    for step in (
        lambda: claimed_summary(settled),
        lambda: ready_summary(settled, summary_text=SUMMARY_CANARY),
        lambda: unavailable_summary(settled, reason=SUMMARY_REASON_SUMMARY_FAILED),
    ):
        with pytest.raises(DelegateSummaryError):
            step()


def test_a_claim_keeps_the_source_binding_and_stays_silent():
    claimed = claimed_summary(_pending())
    assert claimed.summary_status == "in_flight"
    assert claimed.settled is False
    assert claimed.summary_text is None
    assert claimed.summary_ref == _pending().summary_ref
    assert claimed.source_digest == _pending().source_digest


# --------------------------------------------------------------------------- #
# C. The completeness gate (plan §3.3)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "source,truncated,has_provider,expected",
    [
        (None, False, True, SUMMARY_REASON_SOURCE_MISSING),
        ("", False, True, SUMMARY_REASON_SOURCE_EMPTY),
        ("   \n\t  ", False, True, SUMMARY_REASON_SOURCE_EMPTY),
        (SOURCE_CANARY, True, True, SUMMARY_REASON_SOURCE_INCOMPLETE),
        (SOURCE_CANARY, False, False, SUMMARY_REASON_NO_PROVIDER),
        (SOURCE_CANARY, False, True, None),
    ],
)
def test_the_gate_answers_one_stable_code_or_lets_the_source_through(
    source, truncated, has_provider, expected
):
    assert (
        source_gate_reason(
            source_text=source, truncated=truncated, has_provider=has_provider
        )
        == expected
    )


def test_an_incomplete_source_is_refused_before_emptiness_is_even_asked():
    """Upstream truncation is a completeness fact, not a content judgement."""

    assert (
        source_gate_reason(source_text="", truncated=True, has_provider=True)
        == SUMMARY_REASON_SOURCE_INCOMPLETE
    )


# --------------------------------------------------------------------------- #
# D. The request handed to the provider
# --------------------------------------------------------------------------- #
def test_the_request_carries_the_whole_source_the_budget_and_the_inert_notice():
    request = _request()
    assert request.source_text == SOURCE_CANARY
    assert request.budget_chars == SUMMARY_CONTEXT_BUDGET_CHARS == 800
    assert request.full_result_ref == FULL_RESULT_REF
    assert request.terminal == "completed"
    assert request.source_digest == compute_source_digest(SOURCE_CANARY)
    # The answer is data. The request says so, in the request itself.
    assert request.untrusted_source_notice
    assert "untrusted" in request.untrusted_source_notice.lower()
    assert "tool" in request.untrusted_source_notice.lower()


def test_the_request_never_renders_the_source_into_a_log_line():
    request = _request()
    assert SOURCE_CANARY not in repr(request)
    assert FULL_RESULT_REF in repr(request)


# --------------------------------------------------------------------------- #
# E. One attempt, one provider call, one stable settlement
# --------------------------------------------------------------------------- #
def test_a_complete_source_reaches_the_provider_exactly_once_and_becomes_ready():
    provider = _Provider()
    claimed = claimed_summary(_pending())
    settled = asyncio.run(
        settle_summary_attempt(claimed, request=_request(), provider=provider)
    )
    assert len(provider.requests) == 1
    assert settled.summary_status == "ready"
    assert settled.summary_text == SUMMARY_CANARY
    assert settled.generator_ref == "test-summariser"
    assert settled.source_digest == claimed.source_digest


def test_the_provider_output_is_ordinary_text_and_is_never_parsed_as_json():
    provider = _Provider(text='{"verdict": "ship it"}')
    settled = asyncio.run(
        settle_summary_attempt(
            claimed_summary(_pending()), request=_request(), provider=provider
        )
    )
    assert settled.summary_status == "ready"
    assert settled.summary_text == '{"verdict": "ship it"}'


@pytest.mark.parametrize(
    "provider,expected",
    [
        (_Provider(text="   \n  "), SUMMARY_REASON_SUMMARY_EMPTY),
        (
            _Provider(text="摘" * (SUMMARY_CONTEXT_BUDGET_CHARS + 1)),
            SUMMARY_REASON_SUMMARY_OVER_BUDGET,
        ),
        (
            _Provider(error=RuntimeError("token sk-live-abcdef rejected")),
            SUMMARY_REASON_SUMMARY_FAILED,
        ),
        (_Provider(error=TimeoutError()), SUMMARY_REASON_SUMMARY_FAILED),
    ],
)
def test_every_bad_attempt_settles_unavailable_with_a_stable_code(provider, expected):
    settled = asyncio.run(
        settle_summary_attempt(
            claimed_summary(_pending()), request=_request(), provider=provider
        )
    )
    assert settled.summary_status == "unavailable"
    assert settled.unavailable_reason == expected
    assert settled.summary_text is None
    serialized = json.dumps(settled.as_dict(), ensure_ascii=False)
    assert "sk-live" not in serialized
    assert "rejected" not in serialized


def test_an_exactly_budget_sized_summary_is_still_ready():
    provider = _Provider(text="摘" * SUMMARY_CONTEXT_BUDGET_CHARS)
    settled = asyncio.run(
        settle_summary_attempt(
            claimed_summary(_pending()), request=_request(), provider=provider
        )
    )
    assert settled.summary_status == "ready"
    assert len(settled.summary_text) == SUMMARY_CONTEXT_BUDGET_CHARS


@pytest.mark.parametrize("returned", [None, 7, b"bytes", {"summary": "x"}])
def test_a_non_text_provider_return_is_a_failure_not_a_summary(returned):
    class _Weird:
        async def summarize(self, request):
            return returned

    settled = asyncio.run(
        settle_summary_attempt(
            claimed_summary(_pending()), request=_request(), provider=_Weird()
        )
    )
    assert settled.summary_status == "unavailable"
    assert settled.unavailable_reason == SUMMARY_REASON_SUMMARY_FAILED


def test_a_slow_provider_times_out_into_an_honest_unavailable():
    class _Slow:
        async def summarize(self, request):
            await asyncio.sleep(10)
            return SUMMARY_CANARY

    settled = asyncio.run(
        settle_summary_attempt(
            claimed_summary(_pending()),
            request=_request(),
            provider=_Slow(),
            timeout=0.01,
        )
    )
    assert settled.summary_status == "unavailable"
    assert settled.unavailable_reason == SUMMARY_REASON_SUMMARY_FAILED


def test_a_cancelled_attempt_propagates_rather_than_inventing_a_summary():
    async def _drive():
        class _Hang:
            async def summarize(self, request):
                await asyncio.sleep(10)

        task = asyncio.create_task(
            settle_summary_attempt(
                claimed_summary(_pending()), request=_request(), provider=_Hang()
            )
        )
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_drive())


def test_an_attempt_can_only_start_from_a_claimed_record():
    provider = _Provider()
    for record in (
        _pending(),
        unavailable_summary(_pending(), reason=SUMMARY_REASON_SOURCE_EMPTY),
    ):
        with pytest.raises(DelegateSummaryError):
            asyncio.run(
                settle_summary_attempt(record, request=_request(), provider=provider)
            )
    assert provider.requests == []


def test_a_provenance_ref_that_is_not_a_stable_token_is_dropped():
    class _Leaky:
        generator_ref = "Bearer sk-live-abcdef / https://api.example/v1"

        async def summarize(self, request):
            return SUMMARY_CANARY

    settled = asyncio.run(
        settle_summary_attempt(
            claimed_summary(_pending()), request=_request(), provider=_Leaky()
        )
    )
    assert settled.summary_status == "ready"
    assert settled.generator_ref is None
    assert "sk-live" not in json.dumps(settled.as_dict(), ensure_ascii=False)


# --------------------------------------------------------------------------- #
# F. Source drift and abandoned attempts fail closed
# --------------------------------------------------------------------------- #
def test_a_drifted_source_is_a_stable_unavailable_not_a_re_read():
    drifted = unavailable_summary(_pending(), reason=SUMMARY_REASON_SOURCE_DRIFT)
    assert drifted.summary_status == "unavailable"
    assert drifted.unavailable_reason == SUMMARY_REASON_SOURCE_DRIFT
    assert drifted.summary_text is None


def test_an_abandoned_in_flight_attempt_settles_without_replay():
    abandoned = unavailable_summary(
        claimed_summary(_pending()), reason=SUMMARY_REASON_ATTEMPT_ABANDONED
    )
    assert abandoned.summary_status == "unavailable"
    assert abandoned.unavailable_reason == SUMMARY_REASON_ATTEMPT_ABANDONED


# --------------------------------------------------------------------------- #
# G. The deadline is ours, not the provider's
# --------------------------------------------------------------------------- #
LATE_CANARY = "A SUMMARY THE PROVIDER PRODUCED AFTER ITS DEADLINE"


class _SwallowsCancelAndReturns:
    """Catches its own deadline cancellation and answers anyway."""

    def __init__(self) -> None:
        self.absorbed = 0
        self.generator_ref = "swallower"

    async def summarize(self, request: Any) -> str:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            self.absorbed += 1
            return LATE_CANARY
        return "unreached"


class _SwallowsCancelAndKeepsWaiting:
    """Catches cancellation and goes straight back to waiting."""

    def __init__(self) -> None:
        self.absorbed = 0
        self.generator_ref = "swallower"

    async def summarize(self, request: Any) -> str:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            self.absorbed += 1
        # The deadline was never the provider's to honour.
        await asyncio.sleep(30)
        return LATE_CANARY


class _SwallowsEveryCancellation:
    """A hostile provider that never cooperates with task cancellation."""

    def __init__(self) -> None:
        self.absorbed = 0
        self.generator_ref = "persistent-swallower"

    async def summarize(self, request: Any) -> str:
        while True:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                self.absorbed += 1


def _in_a_watched_thread(coro_factory, *, guard: float = 5.0):
    """Drive one coroutine on its own loop, so a hung provider fails the test.

    A provider that absorbs cancellation can otherwise wedge the event loop —
    and ``asyncio.run``'s own shutdown with it — which would hang the suite
    instead of reporting a regression.
    """

    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["value"] = asyncio.run(coro_factory())
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            box["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    started = time.monotonic()
    thread.start()
    thread.join(guard)
    elapsed = time.monotonic() - started
    assert not thread.is_alive(), "the attempt never settled within the guard"
    if "error" in box:
        raise box["error"]
    return box["value"], elapsed


def test_a_provider_that_swallows_its_deadline_cancellation_cannot_become_ready():
    """The late answer is discarded; the deadline is not the provider's to waive."""

    provider = _SwallowsCancelAndReturns()
    settled, elapsed = _in_a_watched_thread(
        lambda: settle_summary_attempt(
            claimed_summary(_pending()),
            request=_request(),
            provider=provider,
            timeout=0.05,
        )
    )
    assert settled.summary_status == "unavailable"
    assert settled.unavailable_reason == SUMMARY_REASON_SUMMARY_FAILED
    assert settled.summary_text is None
    assert LATE_CANARY not in json.dumps(settled.as_dict(), ensure_ascii=False)
    assert elapsed < 5.0
    # It really was asked to stop; it simply does not get the last word.
    assert provider.absorbed == 1


def test_a_provider_that_ignores_cancellation_cannot_block_the_deadline():
    provider = _SwallowsCancelAndKeepsWaiting()
    settled, elapsed = _in_a_watched_thread(
        lambda: settle_summary_attempt(
            claimed_summary(_pending()),
            request=_request(),
            provider=provider,
            timeout=0.05,
        )
    )
    assert settled.summary_status == "unavailable"
    assert settled.unavailable_reason == SUMMARY_REASON_SUMMARY_FAILED
    assert settled.summary_text is None
    # Bounded by our own wall clock, not by whatever the provider decides to do.
    assert elapsed < 5.0
    assert provider.absorbed == 1


def test_a_provider_that_swallows_every_cancel_cannot_block_loop_shutdown():
    provider = _SwallowsEveryCancellation()
    settled, elapsed = _in_a_watched_thread(
        lambda: settle_summary_attempt(
            claimed_summary(_pending()),
            request=_request(),
            provider=provider,
            timeout=0.05,
        ),
        guard=1.0,
    )
    assert settled.summary_status == "unavailable"
    assert settled.unavailable_reason == SUMMARY_REASON_SUMMARY_FAILED
    assert elapsed < 1.0
    assert provider.absorbed >= 1


def test_caller_cancellation_is_not_absorbable_by_the_provider():
    """A cancelled caller stops here, whatever the provider does with its cancel."""

    provider = _SwallowsCancelAndKeepsWaiting()

    async def _drive():
        task = asyncio.create_task(
            settle_summary_attempt(
                claimed_summary(_pending()),
                request=_request(),
                provider=provider,
                timeout=30.0,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return "cancelled"
        return "not cancelled"

    outcome, elapsed = _in_a_watched_thread(_drive)
    assert outcome == "cancelled"
    assert elapsed < 5.0


def test_a_late_result_never_reaches_a_second_attempt_or_the_record():
    provider = _SwallowsCancelAndReturns()
    settled, _elapsed = _in_a_watched_thread(
        lambda: settle_summary_attempt(
            claimed_summary(_pending()),
            request=_request(),
            provider=provider,
            timeout=0.05,
        )
    )
    for surface in (json.dumps(settled.as_dict(), ensure_ascii=False), repr(settled)):
        assert LATE_CANARY not in surface
    assert settled.settled is True


def test_a_prompt_provider_still_wins_its_race_against_the_deadline():
    """The deadline bounds failure; it must not truncate a healthy attempt."""

    settled, _elapsed = _in_a_watched_thread(
        lambda: settle_summary_attempt(
            claimed_summary(_pending()),
            request=_request(),
            provider=_Provider(),
            timeout=5.0,
        )
    )
    assert settled.summary_status == "ready"
    assert settled.summary_text == SUMMARY_CANARY


# --------------------------------------------------------------------------- #
# H. The bounded, sanitized original-task description
# --------------------------------------------------------------------------- #
def test_a_task_description_is_bounded_and_whitespace_collapsed():
    described = sanitize_task_description(
        "  audit the\n\n release notes\tand   summarise  "
    )
    assert described == "audit the release notes and summarise"

    long_task = "审计 " * 400
    clipped = sanitize_task_description(long_task)
    assert len(clipped) <= SUMMARY_TASK_DESCRIPTION_BUDGET_CHARS
    assert SUMMARY_TASK_DESCRIPTION_BUDGET_CHARS < SUMMARY_CONTEXT_BUDGET_CHARS


@pytest.mark.parametrize(
    "value", [None, "", "   ", "\n\t\r ", "\x00\x01\x02", 7, b"bytes", object()]
)
def test_a_task_description_that_carries_nothing_is_none(value):
    assert sanitize_task_description(value) is None


def test_a_task_description_keeps_no_control_characters():
    described = sanitize_task_description("do\x00 the\x07 thing\x1b[31m now")
    assert described is not None
    for forbidden in ("\x00", "\x07", "\x1b"):
        assert forbidden not in described
    assert "do the thing" in described.replace("[31m", "")


def test_the_request_carries_the_description_but_never_renders_it():
    described = "audit the private delegate canary payload body"
    request = _request(task_description=described)
    assert request.task_description == described
    assert described not in repr(request)
    assert request.full_result_ref in repr(request)


def test_a_provider_cannot_turn_private_task_context_into_the_summary(caplog):
    described = "PRIVATE ORIGINAL TASK CANARY 7f3d5a"

    class _EchoesTaskContext:
        async def summarize(self, request):
            assert request.task_description == described
            return request.task_description

    settled = asyncio.run(
        settle_summary_attempt(
            claimed_summary(_pending()),
            request=_request(task_description=described),
            provider=_EchoesTaskContext(),
        )
    )

    assert settled.summary_status == "unavailable"
    assert settled.unavailable_reason == SUMMARY_REASON_SUMMARY_FAILED
    assert settled.summary_text is None
    for surface in (
        repr(settled),
        json.dumps(settled.as_dict(), ensure_ascii=False),
        caplog.text,
    ):
        assert described not in surface


def test_a_request_without_a_description_is_still_valid():
    request = _request()
    assert request.task_description is None
