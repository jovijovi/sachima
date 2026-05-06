"""Deterministic local Temporal workflow for the FlowWeaver Phase 5B POC."""

from __future__ import annotations

from typing import Any

from temporalio import workflow

from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_POC_VERSION
from flowweaver_temporal_poc.payloads import (
    CancelTransactionUpdate,
    DeliveryAckUpdate,
    HumanDecisionUpdate,
    ResumeUserInputUpdate,
    RuntimeStartPayload,
    validate_cancel_transaction_update,
    validate_delivery_ack_update,
    validate_human_decision_update,
    validate_resume_user_input_update,
    validate_start_payload,
)

SNAPSHOT_TYPE = "flowweaver.temporal_poc.snapshot.v0"
UPDATE_RESULT_TYPE = "flowweaver.temporal_poc.update_result.v0"


@workflow.defn
class FlowWeaverTransactionWorkflow:
    """Own deterministic FlowWeaver transaction state for a local POC only."""

    def __init__(self) -> None:
        self._transaction_id = "runtime_tx_uninitialized"
        self._status = "created"
        self._entry_count = 0
        self._record_counts = {"transactions": 0, "intents": 0, "artifacts": 0, "deliveries": 0}
        self._intent_statuses: dict[str, str] = {}
        self._artifact_statuses: dict[str, str] = {}
        self._delivery_statuses: dict[str, str] = {}
        self._event_fingerprints: dict[str, tuple[str, ...]] = {}
        self._resume_count = 0
        self._terminal = False

    @workflow.run
    async def run(self, payload: RuntimeStartPayload) -> dict[str, Any]:
        validate_start_payload(payload)
        self._transaction_id = payload.transaction_id
        self._status = "running"
        self._entry_count = payload.entry_count
        self._record_counts = dict(payload.record_counts)
        delivery_count = payload.record_counts["deliveries"]
        self._intent_statuses = {f"runtime_intent_{index}": "pending" for index in range(payload.entry_count)}
        self._artifact_statuses = {f"runtime_artifact_{index}": "available" for index in range(payload.entry_count)}
        self._delivery_statuses = {f"runtime_delivery_{index}": "planned" for index in range(delivery_count)}
        self._event_fingerprints = {}
        self._resume_count = 0
        self._terminal = False

        await workflow.wait_condition(lambda: self._terminal)
        return self._snapshot()

    @workflow.query
    def query_snapshot(self) -> dict[str, Any]:
        return self._snapshot()

    @workflow.update
    async def record_delivery_ack(self, update: DeliveryAckUpdate) -> dict[str, Any]:
        validate_delivery_ack_update(update)
        fingerprint = self._delivery_ack_fingerprint(update)
        if self._event_fingerprints.get(update.delivery_key) == fingerprint:
            return self._update_result("duplicate")
        self._event_fingerprints[update.delivery_key] = fingerprint
        self._delivery_statuses[update.target_id] = update.status
        return self._update_result("applied")

    @record_delivery_ack.validator
    def validate_record_delivery_ack(self, update: DeliveryAckUpdate) -> None:
        validate_delivery_ack_update(update)
        if update.target_id not in self._delivery_statuses:
            raise ValueError("invalid_delivery_ack_update")
        self._validate_event_fingerprint(update.delivery_key, self._delivery_ack_fingerprint(update), "invalid_delivery_ack_update")

    @workflow.update
    async def approve_intent(self, update: HumanDecisionUpdate) -> dict[str, Any]:
        validate_human_decision_update(update, expected_decision="approved")
        fingerprint = self._human_fingerprint("approve_intent", update)
        if self._event_fingerprints.get(update.event_id) == fingerprint:
            return self._update_result("duplicate")
        self._event_fingerprints[update.event_id] = fingerprint
        self._intent_statuses[update.intent_id] = "approved"
        return self._update_result("applied")

    @approve_intent.validator
    def validate_approve_intent(self, update: HumanDecisionUpdate) -> None:
        validate_human_decision_update(update, expected_decision="approved")
        if update.intent_id not in self._intent_statuses:
            raise ValueError("invalid_human_decision_update")
        self._validate_event_fingerprint(
            update.event_id,
            self._human_fingerprint("approve_intent", update),
            "invalid_human_decision_update",
        )

    @workflow.update
    async def reject_intent(self, update: HumanDecisionUpdate) -> dict[str, Any]:
        validate_human_decision_update(update, expected_decision="rejected")
        fingerprint = self._human_fingerprint("reject_intent", update)
        if self._event_fingerprints.get(update.event_id) == fingerprint:
            return self._update_result("duplicate")
        self._event_fingerprints[update.event_id] = fingerprint
        self._intent_statuses[update.intent_id] = "rejected"
        return self._update_result("applied")

    @reject_intent.validator
    def validate_reject_intent(self, update: HumanDecisionUpdate) -> None:
        validate_human_decision_update(update, expected_decision="rejected")
        if update.intent_id not in self._intent_statuses:
            raise ValueError("invalid_human_decision_update")
        self._validate_event_fingerprint(
            update.event_id,
            self._human_fingerprint("reject_intent", update),
            "invalid_human_decision_update",
        )

    @workflow.update
    async def cancel_transaction(self, update: CancelTransactionUpdate) -> dict[str, Any]:
        validate_cancel_transaction_update(update)
        fingerprint = self._cancel_fingerprint(update)
        if self._event_fingerprints.get(update.event_id) == fingerprint:
            return self._update_result("duplicate")
        self._event_fingerprints[update.event_id] = fingerprint
        self._status = "canceled"
        self._terminal = True
        return self._update_result("applied")

    @cancel_transaction.validator
    def validate_cancel_transaction(self, update: CancelTransactionUpdate) -> None:
        validate_cancel_transaction_update(update)
        self._validate_event_fingerprint(
            update.event_id,
            self._cancel_fingerprint(update),
            "invalid_cancel_transaction_update",
        )

    @workflow.update
    async def resume_after_user_input(self, update: ResumeUserInputUpdate) -> dict[str, Any]:
        validate_resume_user_input_update(update)
        fingerprint = self._resume_fingerprint(update)
        if self._event_fingerprints.get(update.event_id) == fingerprint:
            return self._update_result("duplicate")
        self._event_fingerprints[update.event_id] = fingerprint
        self._resume_count += 1
        if self._status == "waiting_for_user":
            self._status = "running"
        return self._update_result("applied")

    @resume_after_user_input.validator
    def validate_resume_after_user_input(self, update: ResumeUserInputUpdate) -> None:
        validate_resume_user_input_update(update)
        self._validate_event_fingerprint(
            update.event_id,
            self._resume_fingerprint(update),
            "invalid_resume_user_input_update",
        )

    def _snapshot(self) -> dict[str, Any]:
        return {
            "type": SNAPSHOT_TYPE,
            "version": FLOWWEAVER_TEMPORAL_POC_VERSION,
            "transaction_id": self._transaction_id,
            "status": self._status,
            "entry_count": self._entry_count,
            "record_counts": dict(self._record_counts),
            "counts": {
                "intents": len(self._intent_statuses),
                "artifacts": len(self._artifact_statuses),
                "deliveries": len(self._delivery_statuses),
            },
            "intent_statuses": dict(sorted(self._intent_statuses.items())),
            "artifact_statuses": dict(sorted(self._artifact_statuses.items())),
            "delivery_statuses": dict(sorted(self._delivery_statuses.items())),
            "applied_event_count": len(self._event_fingerprints),
            "resume_count": self._resume_count,
            "side_effects": [],
        }

    def _update_result(self, update_status: str) -> dict[str, Any]:
        return {
            "type": UPDATE_RESULT_TYPE,
            "version": FLOWWEAVER_TEMPORAL_POC_VERSION,
            "update_status": update_status,
            "snapshot": self._snapshot(),
            "side_effects": [],
        }

    def _validate_event_fingerprint(self, event_id: str, fingerprint: tuple[str, ...], error: str) -> None:
        existing = self._event_fingerprints.get(event_id)
        if existing is not None and existing != fingerprint:
            raise ValueError(error)

    def _delivery_ack_fingerprint(self, update: DeliveryAckUpdate) -> tuple[str, ...]:
        return (
            "record_delivery_ack",
            update.delivery_key,
            update.surface,
            update.target_kind,
            update.target_id,
            update.status,
        )

    def _human_fingerprint(self, event_type: str, update: HumanDecisionUpdate) -> tuple[str, ...]:
        return (
            event_type,
            update.event_id,
            update.intent_id,
            update.decision,
            update.reason_ref or "",
        )

    def _cancel_fingerprint(self, update: CancelTransactionUpdate) -> tuple[str, ...]:
        return ("cancel_transaction", update.event_id, update.reason_ref or "")

    def _resume_fingerprint(self, update: ResumeUserInputUpdate) -> tuple[str, ...]:
        return ("resume_after_user_input", update.event_id, update.input_ref)


__all__ = ["FlowWeaverTransactionWorkflow", "SNAPSHOT_TYPE", "UPDATE_RESULT_TYPE"]
