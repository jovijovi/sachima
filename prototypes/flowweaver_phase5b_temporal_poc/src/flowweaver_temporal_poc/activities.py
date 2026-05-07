"""Prototype-only FlowWeaver Phase 5J stub Activities."""

from __future__ import annotations

from temporalio import activity

from flowweaver_temporal_poc.payloads import (
    AgentTurnActivityInput,
    AgentTurnActivityResult,
    ClaimCheckRefValidationInput,
    ClaimCheckRefValidationResult,
    DeliverArtifactActivityInput,
    DeliverArtifactActivityResult,
    validate_agent_turn_activity_input,
    validate_claim_check_ref_validation_input,
    validate_deliver_artifact_activity_input,
)


@activity.defn(name="validate_claim_check_ref")
async def validate_claim_check_ref(value: ClaimCheckRefValidationInput) -> ClaimCheckRefValidationResult:
    validate_claim_check_ref_validation_input(value)
    return ClaimCheckRefValidationResult(
        activity_type="validate_claim_check_ref",
        ref=value.ref,
        kind=value.kind,
        status="validated",
        checksum_hint=value.checksum_hint,
    )


@activity.defn(name="execute_agent_turn")
async def execute_agent_turn(value: AgentTurnActivityInput) -> AgentTurnActivityResult:
    validate_agent_turn_activity_input(value)
    return AgentTurnActivityResult(
        activity_type="execute_agent_turn",
        event_id=value.event_id,
        intent_id=value.intent_id,
        artifact_id=value.output_artifact_id,
        artifact_ref=value.output_artifact_ref,
        status="completed",
    )


@activity.defn(name="deliver_artifact")
async def deliver_artifact(value: DeliverArtifactActivityInput) -> DeliverArtifactActivityResult:
    validate_deliver_artifact_activity_input(value)
    return DeliverArtifactActivityResult(
        activity_type="deliver_artifact",
        event_id=value.event_id,
        artifact_id=value.artifact_id,
        delivery_id=value.delivery_id,
        delivery_ref=value.delivery_ref,
        surface=value.surface,
        status="planned",
    )


__all__ = ["deliver_artifact", "execute_agent_turn", "validate_claim_check_ref"]
