"""Startup recovery passes over the whole delegation history, off the Gateway loop.

Startup restores every settled Task's identity, settles interrupted summaries and
sinks, and reconciles every stored continuation operation. These passes visit
all of history, so each record must cost a bounded number of reads — never one
history scan per record — and none of it may hold the Gateway loop. The
coordinator runs each history scan and each record's work here on its owned
worker seam (``SachimaDelegateCoordinator._sync``) while it keeps that record's
task gate on the loop. The decisions are the coordinator's, unchanged; a settled
record is simply never rewritten with the bytes it already has.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from gateway.sachima_delegate_state import (
    DelegateResultEvent,
    DelegateStateError,
    DelegateStateStore,
    DelegateTaskBinding,
    DelegateTurnRecord,
)


def results_by_turn(state: DelegateStateStore) -> dict[str, DelegateResultEvent]:
    """Every result keyed by its Turn, from one scan.

    Empty when the scan fails: each Task then asks the store itself and fails
    closed exactly as it did when every Task scanned on its own.
    """

    try:
        return {event.turn_key: event for event in state.list_results()}
    except DelegateStateError:
        return {}


def unsettled_summary_events(coordinator: Any) -> list[DelegateResultEvent]:
    """Results whose summary is not settled, or cannot be read, from one scan.

    A failed scan raises, so the summary pass fails closed as before; a settled
    history costs one read per result and summary and yields nothing to settle.
    """

    unsettled = []
    for event in coordinator.state.list_results():
        summary = coordinator._summary_for_event(event)
        if summary is None or not summary.settled:
            unsettled.append(event)
    return unsettled


def restore_task_identity(
    coordinator: Any,
    task: DelegateTaskBinding,
    results: dict[str, DelegateResultEvent],
) -> bool:
    """Restore one settled Task's sealed identity; ``True`` when it was restored.

    A Turn missing from the pass's result snapshot is asked of the store itself,
    so a terminal written after the snapshot is still found.
    """

    from gateway.sachima_delegate import SACHIMA_DELEGATE_BLOCKED

    state = coordinator.state
    turn = state.read_turn(task.current_turn_key)
    if turn is None or turn.lifecycle != "terminal":
        return False
    event = results.get(turn.turn_key)
    if event is None:
        try:
            event = state.result_for_turn(turn.turn_key)
        except DelegateStateError:
            event = None
    if event is None:
        state.update_turn(turn.turn_key, diagnostic=SACHIMA_DELEGATE_BLOCKED)
        return False
    return coordinator._restore_terminal_identity(turn)


class OperationTurns:
    """Turns by continuation ``operation_id``, from one Turn scan per pass.

    The index only says where to look. A hit is re-read by key, so the Turn is
    judged as it is now; a miss — or a key that is gone — is answered by a fresh
    full scan, so an operation whose Turn appeared after the index was taken is
    never mistaken for one that was not submitted.
    """

    def __init__(self, state: DelegateStateStore) -> None:
        self._state = state
        self._keys: dict[str, list[str]] | None = None

    def __call__(self, operation_id: str) -> tuple[DelegateTurnRecord, ...]:
        if self._keys is None:
            self._keys = {}
            for turn in self._state.list_turns():
                if turn.operation_id is not None:
                    self._keys.setdefault(turn.operation_id, []).append(turn.turn_key)
        keys = self._keys.get(operation_id, ())
        turns = tuple(
            turn for key in keys if (turn := self._state.read_turn(key)) is not None
        )
        if turns and len(turns) == len(keys):
            return turns
        return tuple(
            turn for turn in self._state.list_turns() if turn.operation_id == operation_id
        )


def _settle(state: DelegateStateStore, event: DelegateResultEvent, **fields: Any) -> None:
    """Write a reconciled event only when reconciliation changes it.

    A consumed continuation stays ``accepted`` for good, so every later startup
    reaches it again; rewriting the identical record cost one fsync'd write per
    historical operation on every start.
    """

    if replace(event, **fields) != event:
        state.update_result(event.event_id, **fields)


def reconcile_operation(
    coordinator: Any,
    snapshot: DelegateResultEvent,
    operation_turns: OperationTurns,
) -> str | None:
    """Resolve one stored operation's crash window; the count it lands in, or ``None``.

    Runs while the caller holds ``snapshot.task_ref``'s task gate.
    """

    from gateway.sachima_delegate import (
        SACHIMA_DELEGATE_CONTINUATION_PAUSED,
        SACHIMA_DELEGATE_CONTINUATION_SUPERSEDED,
        SACHIMA_DELEGATE_INVARIANT,
        SACHIMA_DELEGATE_NO_CONTINUATION_AUTHORITY,
        SACHIMA_DELEGATE_OPERATION_UNCERTAIN,
        SACHIMA_DELEGATE_RECOVERY_REQUIRED,
    )

    state = coordinator.state
    event = state.read_result(snapshot.event_id)
    binding = state.read_task(snapshot.task_ref)
    if (
        event is None
        or binding is None
        or event.operation_state not in {"in_flight", "accepted"}
    ):
        return None

    expected_operation_id = coordinator._authorized_operation_id(event, binding)
    if event.operation_id != expected_operation_id:
        _settle(
            state,
            event,
            operation_state="uncertain",
            operation_diagnostic=SACHIMA_DELEGATE_OPERATION_UNCERTAIN,
            business_state="blocked",
            business_diagnostic=SACHIMA_DELEGATE_OPERATION_UNCERTAIN,
            wakeup_state="blocked",
            wakeup_claim_id=None,
            wakeup_diagnostic=SACHIMA_DELEGATE_OPERATION_UNCERTAIN,
        )
        return "uncertain"

    matches = operation_turns(event.operation_id)
    if len(matches) > 1:
        _settle(
            state,
            event,
            operation_state="uncertain",
            operation_diagnostic=SACHIMA_DELEGATE_INVARIANT,
            business_state="blocked",
            business_diagnostic=SACHIMA_DELEGATE_INVARIANT,
            wakeup_state="blocked",
            wakeup_claim_id=None,
            wakeup_diagnostic=SACHIMA_DELEGATE_INVARIANT,
        )
        return "uncertain"

    if not matches:
        if event.operation_state == "accepted":
            _settle(
                state,
                event,
                operation_state="uncertain",
                operation_diagnostic=SACHIMA_DELEGATE_OPERATION_UNCERTAIN,
                business_state="blocked",
                business_diagnostic=SACHIMA_DELEGATE_OPERATION_UNCERTAIN,
                wakeup_state="blocked",
                wakeup_claim_id=None,
                wakeup_diagnostic=SACHIMA_DELEGATE_OPERATION_UNCERTAIN,
            )
            return "uncertain"
        if binding.current_turn_key != event.turn_key:
            state.update_task(
                binding.task_ref,
                continuation_disposition="superseded",
            )
            _settle(
                state,
                event,
                operation_state="none",
                operation_task_ref=None,
                operation_turn_key=None,
                operation_diagnostic=SACHIMA_DELEGATE_CONTINUATION_SUPERSEDED,
                business_state="blocked",
                business_processing_id=None,
                business_evidence_ref=None,
                business_diagnostic=SACHIMA_DELEGATE_CONTINUATION_SUPERSEDED,
                wakeup_state="blocked",
                wakeup_claim_id=None,
                wakeup_diagnostic=SACHIMA_DELEGATE_CONTINUATION_SUPERSEDED,
            )
            return "superseded"
        if binding.continuation_disposition != "authorized":
            diagnostic = (
                SACHIMA_DELEGATE_CONTINUATION_PAUSED
                if binding.continuation_disposition == "paused"
                else SACHIMA_DELEGATE_CONTINUATION_SUPERSEDED
                if binding.continuation_disposition == "superseded"
                else SACHIMA_DELEGATE_NO_CONTINUATION_AUTHORITY
            )
            _settle(
                state,
                event,
                operation_state="none",
                operation_task_ref=None,
                operation_turn_key=None,
                operation_diagnostic=diagnostic,
                business_state="pending",
                business_processing_id=None,
                business_evidence_ref=None,
                business_diagnostic=diagnostic,
                wakeup_state="blocked",
                wakeup_claim_id=None,
                wakeup_diagnostic=diagnostic,
            )
            return "superseded"

        # Turn creation precedes every possible submit. Its absence
        # proves the operation did not cross the side-effect
        # boundary; release the old model claim and retry normally.
        _settle(
            state,
            event,
            hermes_sink="pending",
            processing_id=None,
            processing_session_id=None,
            business_state="pending",
            business_processing_id=None,
            business_evidence_ref=None,
            business_diagnostic=None,
            wakeup_state="pending",
            wakeup_claim_id=None,
            wakeup_diagnostic=SACHIMA_DELEGATE_RECOVERY_REQUIRED,
            operation_state="none",
            operation_task_ref=None,
            operation_turn_key=None,
            operation_diagnostic=SACHIMA_DELEGATE_RECOVERY_REQUIRED,
        )
        return "retry"

    operation_turn = matches[0]
    operation_binding = state.read_task(operation_turn.task_ref)
    related = operation_turn.task_ref == binding.task_ref or (
        operation_binding is not None
        and operation_binding.linked_from == event.event_id
    )
    if not related:
        _settle(
            state,
            event,
            operation_state="uncertain",
            operation_diagnostic=SACHIMA_DELEGATE_OPERATION_UNCERTAIN,
            business_state="blocked",
            business_diagnostic=SACHIMA_DELEGATE_OPERATION_UNCERTAIN,
            wakeup_state="blocked",
            wakeup_claim_id=None,
            wakeup_diagnostic=SACHIMA_DELEGATE_OPERATION_UNCERTAIN,
        )
        return "uncertain"

    if operation_turn.lifecycle in {"admitted", "terminal"}:
        _settle(
            state,
            event,
            operation_state="accepted",
            operation_task_ref=operation_turn.task_ref,
            operation_turn_key=operation_turn.turn_key,
            operation_diagnostic=None,
            business_state="continued",
            business_processing_id=event.processing_id,
            business_evidence_ref=operation_turn.turn_key,
            business_diagnostic=None,
            wakeup_state="settled",
            wakeup_claim_id=None,
            wakeup_diagnostic=None,
        )
        if binding.continuation_disposition != "consumed":
            state.update_task(
                binding.task_ref,
                continuation_disposition="consumed",
            )
        return "reconciled"

    if (
        event.operation_state == "in_flight"
        and operation_turn.lifecycle
        in {"prepared", "recovery_required"}
        and binding.continuation_disposition == "authorized"
    ):
        # Re-enter through the main-model claim. continue_task will
        # find this same operation Turn and recover it instead of
        # opening a second Turn or inventing a new operation id.
        _settle(
            state,
            event,
            hermes_sink="pending",
            processing_id=None,
            processing_session_id=None,
            business_state="pending",
            business_processing_id=None,
            business_evidence_ref=None,
            business_diagnostic=None,
            wakeup_state="pending",
            wakeup_claim_id=None,
            wakeup_diagnostic=SACHIMA_DELEGATE_RECOVERY_REQUIRED,
            operation_task_ref=operation_turn.task_ref,
            operation_turn_key=operation_turn.turn_key,
            operation_diagnostic=SACHIMA_DELEGATE_RECOVERY_REQUIRED,
        )
        return "retry"

    diagnostic = (
        operation_turn.diagnostic or SACHIMA_DELEGATE_OPERATION_UNCERTAIN
    )
    _settle(
        state,
        event,
        operation_state="uncertain",
        operation_task_ref=operation_turn.task_ref,
        operation_turn_key=operation_turn.turn_key,
        operation_diagnostic=diagnostic,
        business_state="blocked",
        business_diagnostic=diagnostic,
        wakeup_state="blocked",
        wakeup_claim_id=None,
        wakeup_diagnostic=diagnostic,
    )
    return "uncertain"


__all__ = [
    "OperationTurns",
    "reconcile_operation",
    "restore_task_identity",
    "results_by_turn",
    "unsettled_summary_events",
]
