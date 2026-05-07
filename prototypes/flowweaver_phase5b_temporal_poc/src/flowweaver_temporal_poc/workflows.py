"""Deterministic local Temporal workflow for the FlowWeaver Phase 5B POC."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_POC_VERSION
from flowweaver_temporal_poc.payloads import (
    AgentTurnActivityInput,
    AgentTurnActivityResult,
    CancelTransactionUpdate,
    ClaimCheckRefValidationInput,
    ClaimCheckRefValidationResult,
    DeliveryAckUpdate,
    DeliverArtifactActivityInput,
    DeliverArtifactActivityResult,
    HumanDecisionUpdate,
    ResumeUserInputUpdate,
    RuntimeStartPayload,
    build_activity_boundary_summary,
    start_signature_from_payload,
    validate_activity_boundary_summary,
    validate_agent_turn_activity_input,
    validate_agent_turn_activity_result,
    validate_cancel_transaction_update,
    validate_claim_check_ref_validation_input,
    validate_claim_check_ref_validation_result,
    validate_delivery_ack_update,
    validate_deliver_artifact_activity_input,
    validate_deliver_artifact_activity_result,
    validate_human_decision_update,
    validate_resume_user_input_update,
    validate_start_payload,
)

SNAPSHOT_TYPE = "flowweaver.temporal_poc.snapshot.v0"
UPDATE_RESULT_TYPE = "flowweaver.temporal_poc.update_result.v0"
_ACTIVITY_TIMEOUT = timedelta(seconds=5)



@workflow.defn
class FlowWeaverTransactionWorkflow:
    """Own deterministic FlowWeaver transaction state for a local POC only."""

    def __init__(self) -> None:
        self._transaction_id = "runtime_tx_uninitialized"
        self._status = "created"
        self._entry_count = 0
        self._record_counts = {"transactions": 0, "intents": 0, "artifacts": 0, "deliveries": 0}
        self._start_signature: dict[str, Any] = {}
        self._intent_statuses: dict[str, str] = {}
        self._artifact_statuses: dict[str, str] = {}
        self._delivery_statuses: dict[str, str] = {}
        self._event_keys: dict[str, tuple[str, ...]] = {}
        self._resume_count = 0
        self._terminal = False
        self._activity_boundary: dict[str, Any] | None = None

    @workflow.run
    async def run(self, payload: RuntimeStartPayload) -> dict[str, Any]:
        validate_start_payload(payload)
        self._transaction_id = payload.transaction_id
        self._status = "running"
        self._entry_count = payload.entry_count
        self._record_counts = dict(payload.record_counts)
        self._start_signature = start_signature_from_payload(payload)
        delivery_count = payload.record_counts["deliveries"]
        self._intent_statuses = {f"runtime_intent_{index}": "pending" for index in range(payload.entry_count)}
        self._artifact_statuses = {f"runtime_artifact_{index}": "available" for index in range(payload.entry_count)}
        self._delivery_statuses = {f"runtime_delivery_{index}": "planned" for index in range(delivery_count)}
        self._event_keys = {}
        self._resume_count = 0
        self._terminal = False
        self._activity_boundary = None

        validation_input = ClaimCheckRefValidationInput(
            ref="claim_ref_phase5j_start",
            kind="input",
            count=payload.entry_count,
            size=128,
            checksum_hint=payload.claim_policy_digest,
        )
        validate_claim_check_ref_validation_input(validation_input)
        validation_result = await workflow.execute_activity(
            "validate_claim_check_ref",
            validation_input,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            result_type=ClaimCheckRefValidationResult,
        )
        validate_claim_check_ref_validation_result(validation_result)

        agent_input = AgentTurnActivityInput(
            event_id="runtime_event_phase5j_agent",
            intent_id="runtime_intent_0",
            input_ref=validation_result.ref,
            output_artifact_id="runtime_artifact_0",
            output_artifact_ref="claim_ref_phase5j_artifact_0",
        )
        validate_agent_turn_activity_input(agent_input)
        agent_result = await workflow.execute_activity(
            "execute_agent_turn",
            agent_input,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            result_type=AgentTurnActivityResult,
        )
        validate_agent_turn_activity_result(agent_result)

        delivery_input = DeliverArtifactActivityInput(
            event_id="runtime_event_phase5j_delivery",
            artifact_id=agent_result.artifact_id,
            artifact_ref=agent_result.artifact_ref,
            delivery_id="runtime_delivery_0",
            delivery_ref="claim_ref_phase5j_delivery_0",
            surface="prototype",
        )
        validate_deliver_artifact_activity_input(delivery_input)
        delivery_result = await workflow.execute_activity(
            "deliver_artifact",
            delivery_input,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            result_type=DeliverArtifactActivityResult,
        )
        validate_deliver_artifact_activity_result(delivery_result)

        self._activity_boundary = build_activity_boundary_summary(
            validation=validation_result,
            agent_turn=agent_result,
            delivery=delivery_result,
            status="completed",
        )
        validate_activity_boundary_summary(self._activity_boundary)
        workflow.upsert_memo({"activity_boundary": self._activity_boundary})

        await workflow.wait_condition(lambda: self._terminal)
        return self._snapshot()

    @workflow.query
    def query_snapshot(self) -> dict[str, Any]:
        return self._snapshot()

    @workflow.update
    async def record_delivery_ack(self, update: DeliveryAckUpdate) -> dict[str, Any]:
        validate_delivery_ack_update(update)
        event_key = self._delivery_ack_event_key(update)
        if self._event_keys.get(update.delivery_key) == event_key:
            return self._update_result("duplicate")
        self._event_keys[update.delivery_key] = event_key
        self._delivery_statuses[update.target_id] = update.status
        return self._update_result("applied")

    @record_delivery_ack.validator
    def validate_record_delivery_ack(self, update: DeliveryAckUpdate) -> None:
        validate_delivery_ack_update(update)
        if update.target_id not in self._delivery_statuses:
            raise ValueError("invalid_delivery_ack_update")
        self._validate_event_key(update.delivery_key, self._delivery_ack_event_key(update), "invalid_delivery_ack_update")

    @workflow.update
    async def approve_intent(self, update: HumanDecisionUpdate) -> dict[str, Any]:
        validate_human_decision_update(update, expected_decision="approved")
        event_key = self._human_event_key("approve_intent", update)
        if self._event_keys.get(update.event_id) == event_key:
            return self._update_result("duplicate")
        self._event_keys[update.event_id] = event_key
        self._intent_statuses[update.intent_id] = "approved"
        return self._update_result("applied")

    @approve_intent.validator
    def validate_approve_intent(self, update: HumanDecisionUpdate) -> None:
        validate_human_decision_update(update, expected_decision="approved")
        if update.intent_id not in self._intent_statuses:
            raise ValueError("invalid_human_decision_update")
        self._validate_event_key(
            update.event_id,
            self._human_event_key("approve_intent", update),
            "invalid_human_decision_update",
        )

    @workflow.update
    async def reject_intent(self, update: HumanDecisionUpdate) -> dict[str, Any]:
        validate_human_decision_update(update, expected_decision="rejected")
        event_key = self._human_event_key("reject_intent", update)
        if self._event_keys.get(update.event_id) == event_key:
            return self._update_result("duplicate")
        self._event_keys[update.event_id] = event_key
        self._intent_statuses[update.intent_id] = "rejected"
        return self._update_result("applied")

    @reject_intent.validator
    def validate_reject_intent(self, update: HumanDecisionUpdate) -> None:
        validate_human_decision_update(update, expected_decision="rejected")
        if update.intent_id not in self._intent_statuses:
            raise ValueError("invalid_human_decision_update")
        self._validate_event_key(
            update.event_id,
            self._human_event_key("reject_intent", update),
            "invalid_human_decision_update",
        )

    @workflow.update
    async def cancel_transaction(self, update: CancelTransactionUpdate) -> dict[str, Any]:
        validate_cancel_transaction_update(update)
        event_key = self._cancel_event_key(update)
        if self._event_keys.get(update.event_id) == event_key:
            return self._update_result("duplicate")
        self._event_keys[update.event_id] = event_key
        self._status = "canceled"
        self._terminal = True
        return self._update_result("applied")

    @cancel_transaction.validator
    def validate_cancel_transaction(self, update: CancelTransactionUpdate) -> None:
        validate_cancel_transaction_update(update)
        self._validate_event_key(
            update.event_id,
            self._cancel_event_key(update),
            "invalid_cancel_transaction_update",
        )

    @workflow.update
    async def resume_after_user_input(self, update: ResumeUserInputUpdate) -> dict[str, Any]:
        validate_resume_user_input_update(update)
        event_key = self._resume_event_key(update)
        if self._event_keys.get(update.event_id) == event_key:
            return self._update_result("duplicate")
        self._event_keys[update.event_id] = event_key
        self._resume_count += 1
        if self._status == "waiting_for_user":
            self._status = "running"
        return self._update_result("applied")

    @resume_after_user_input.validator
    def validate_resume_after_user_input(self, update: ResumeUserInputUpdate) -> None:
        validate_resume_user_input_update(update)
        self._validate_event_key(
            update.event_id,
            self._resume_event_key(update),
            "invalid_resume_user_input_update",
        )

    def _snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "type": SNAPSHOT_TYPE,
            "version": FLOWWEAVER_TEMPORAL_POC_VERSION,
            "transaction_id": self._transaction_id,
            "status": self._status,
            "entry_count": self._entry_count,
            "record_counts": dict(self._record_counts),
            "start_signature": dict(self._start_signature),
            "counts": {
                "intents": len(self._intent_statuses),
                "artifacts": len(self._artifact_statuses),
                "deliveries": len(self._delivery_statuses),
            },
            "intent_statuses": dict(sorted(self._intent_statuses.items())),
            "artifact_statuses": dict(sorted(self._artifact_statuses.items())),
            "delivery_statuses": dict(sorted(self._delivery_statuses.items())),
            "applied_event_count": len(self._event_keys),
            "resume_count": self._resume_count,
            "side_effects": [],
        }
        if self._activity_boundary is not None:
            snapshot["activity_boundary"] = dict(self._activity_boundary)
        return snapshot

    def _update_result(self, update_status: str) -> dict[str, Any]:
        return {
            "type": UPDATE_RESULT_TYPE,
            "version": FLOWWEAVER_TEMPORAL_POC_VERSION,
            "update_status": update_status,
            "snapshot": self._snapshot(),
            "side_effects": [],
        }

    def _validate_event_key(self, event_id: str, event_key: tuple[str, ...], error: str) -> None:
        existing = self._event_keys.get(event_id)
        if existing is not None and existing != event_key:
            raise ValueError(error)

    def _delivery_ack_event_key(self, update: DeliveryAckUpdate) -> tuple[str, ...]:
        return (
            "record_delivery_ack",
            update.delivery_key,
            update.surface,
            update.target_kind,
            update.target_id,
            update.status,
        )

    def _human_event_key(self, event_type: str, update: HumanDecisionUpdate) -> tuple[str, ...]:
        return (
            event_type,
            update.event_id,
            update.intent_id,
            update.decision,
            update.reason_ref or "",
        )

    def _cancel_event_key(self, update: CancelTransactionUpdate) -> tuple[str, ...]:
        return ("cancel_transaction", update.event_id, update.reason_ref or "")

    def _resume_event_key(self, update: ResumeUserInputUpdate) -> tuple[str, ...]:
        return ("resume_after_user_input", update.event_id, update.input_ref)


__all__ = ["FlowWeaverTransactionWorkflow", "SNAPSHOT_TYPE", "UPDATE_RESULT_TYPE"]
