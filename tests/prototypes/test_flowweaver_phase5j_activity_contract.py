"""RED contract tests for FlowWeaver Phase 5J Activity claim-check boundaries."""

from __future__ import annotations

from dataclasses import is_dataclass, replace
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_temporal_poc.payloads import build_runtime_start_payload, start_signature_from_payload  # noqa: E402


ACTIVITY_BOUNDARY_TYPE = "flowweaver.temporal_poc.activity_boundary.v0"
ACTIVITY_RESULT_TYPE = "flowweaver.temporal_poc.activity_result.v0"
POC_VERSION = "flowweaver.temporal_poc.v0"
VALID_RUNTIME_SIG = "runtime_sig_" + ("0" * 64)
SAFE_TRANSACTION_ID = "runtime_tx_phase5j_contract"
SAFE_START_EVENT_ID = "runtime_event_start_phase5j_contract"


FORBIDDEN_RENDER_MARKERS = (
    "raw_snapshot",
    "raw_capture",
    "full_agent_result",
    "raw_" + "prompt",
    "tool_" + "output",
    "card_" + "json",
    "platform_" + "payload",
    "platform_" + "id",
    "chat_" + "id",
    "user_" + "id",
    "message_" + "id",
    "om_" + "phase5j_private_message",
    "oc_" + "phase5j_private_chat",
    "ou_" + "phase5j_private_user",
    "unsafe-" + "to" + "ken" + "-phase5j",
    "sk" + "-" + "phase5j_probe",
)


SAFE_START_PAYLOAD = build_runtime_start_payload(
    transaction_id=SAFE_TRANSACTION_ID,
    idempotency_key=SAFE_START_EVENT_ID,
    entry_count=1,
    record_counts={"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
    allowed_runtime_events=(
        "start_transaction",
        "record_operation",
        "publish_artifact",
        "plan_delivery",
        "record_delivery_ack",
        "approve_intent",
        "reject_intent",
        "cancel_transaction",
        "resume_after_user_input",
    ),
    claim_check_policy={
        "mode": "references_only",
        "allowed_reference_fields": ("ref", "kind", "count", "size", "checksum_hint"),
        "forbidden_material": (
            "raw_snapshot",
            "raw_capture",
            "full_agent_result",
            "raw_prompt",
            "raw_command",
            "stdout",
            "stderr",
            "tool_output",
            "card_json",
            "media_bytes",
            "media_path",
            "platform_payload",
            "platform_id",
            "chat_id",
            "user_id",
            "message_id",
            "delivery_ack_payload",
            "credential",
            "to" + "ken",
            "se" + "cret",
        ),
    },
)


def _phase5j_payload_surface() -> SimpleNamespace:
    from flowweaver_temporal_poc.payloads import (  # noqa: PLC0415
        ACTIVITY_BOUNDARY_TYPE as exported_boundary_type,
        ACTIVITY_RESULT_TYPE as exported_result_type,
        AgentTurnActivityInput,
        AgentTurnActivityResult,
        ClaimCheckRefValidationInput,
        ClaimCheckRefValidationResult,
        DeliverArtifactActivityInput,
        DeliverArtifactActivityResult,
        build_activity_boundary_summary,
        validate_activity_boundary_summary,
        validate_agent_turn_activity_input,
        validate_agent_turn_activity_result,
        validate_claim_check_ref_validation_input,
        validate_claim_check_ref_validation_result,
        validate_deliver_artifact_activity_input,
        validate_deliver_artifact_activity_result,
    )

    return SimpleNamespace(
        ACTIVITY_BOUNDARY_TYPE=exported_boundary_type,
        ACTIVITY_RESULT_TYPE=exported_result_type,
        AgentTurnActivityInput=AgentTurnActivityInput,
        AgentTurnActivityResult=AgentTurnActivityResult,
        ClaimCheckRefValidationInput=ClaimCheckRefValidationInput,
        ClaimCheckRefValidationResult=ClaimCheckRefValidationResult,
        DeliverArtifactActivityInput=DeliverArtifactActivityInput,
        DeliverArtifactActivityResult=DeliverArtifactActivityResult,
        build_activity_boundary_summary=build_activity_boundary_summary,
        validate_activity_boundary_summary=validate_activity_boundary_summary,
        validate_agent_turn_activity_input=validate_agent_turn_activity_input,
        validate_agent_turn_activity_result=validate_agent_turn_activity_result,
        validate_claim_check_ref_validation_input=validate_claim_check_ref_validation_input,
        validate_claim_check_ref_validation_result=validate_claim_check_ref_validation_result,
        validate_deliver_artifact_activity_input=validate_deliver_artifact_activity_input,
        validate_deliver_artifact_activity_result=validate_deliver_artifact_activity_result,
    )


def _safe_activity_inputs(surface: SimpleNamespace) -> tuple[object, object, object]:
    return (
        surface.ClaimCheckRefValidationInput(
            ref="claim_ref_phase5j_start",
            kind="input",
            count=1,
            size=128,
            checksum_hint=VALID_RUNTIME_SIG,
        ),
        surface.AgentTurnActivityInput(
            event_id="runtime_event_phase5j_agent",
            intent_id="runtime_intent_0",
            input_ref="claim_ref_phase5j_start",
            output_artifact_id="runtime_artifact_0",
            output_artifact_ref="claim_ref_phase5j_artifact_0",
        ),
        surface.DeliverArtifactActivityInput(
            event_id="runtime_event_phase5j_delivery",
            artifact_id="runtime_artifact_0",
            artifact_ref="claim_ref_phase5j_artifact_0",
            delivery_id="runtime_delivery_0",
            delivery_ref="claim_ref_phase5j_delivery_0",
            surface="prototype",
        ),
    )


def _safe_activity_results(surface: SimpleNamespace) -> tuple[object, object, object]:
    return (
        surface.ClaimCheckRefValidationResult(
            activity_type="validate_claim_check_ref",
            ref="claim_ref_phase5j_start",
            kind="input",
            status="validated",
            checksum_hint=VALID_RUNTIME_SIG,
        ),
        surface.AgentTurnActivityResult(
            activity_type="execute_agent_turn",
            event_id="runtime_event_phase5j_agent",
            intent_id="runtime_intent_0",
            artifact_id="runtime_artifact_0",
            artifact_ref="claim_ref_phase5j_artifact_0",
            status="completed",
        ),
        surface.DeliverArtifactActivityResult(
            activity_type="deliver_artifact",
            event_id="runtime_event_phase5j_delivery",
            artifact_id="runtime_artifact_0",
            delivery_id="runtime_delivery_0",
            delivery_ref="claim_ref_phase5j_delivery_0",
            surface="prototype",
            status="planned",
        ),
    )


def _safe_activity_boundary() -> dict[str, object]:
    return {
        "type": ACTIVITY_BOUNDARY_TYPE,
        "version": POC_VERSION,
        "status": "completed",
        "activities": {
            "validate_claim_check_ref": "validated",
            "execute_agent_turn": "completed",
            "deliver_artifact": "planned",
        },
        "refs": {
            "input_ref": "claim_ref_phase5j_start",
            "artifact_ref": "claim_ref_phase5j_artifact_0",
            "delivery_ref": "claim_ref_phase5j_delivery_0",
        },
        "side_effects": [],
    }


def _safe_snapshot(*, activity_boundary: dict[str, object] | None = None) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "type": "flowweaver.temporal_poc.snapshot.v0",
        "version": POC_VERSION,
        "transaction_id": SAFE_TRANSACTION_ID,
        "status": "running",
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
        "start_signature": start_signature_from_payload(SAFE_START_PAYLOAD),
        "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
        "intent_statuses": {"runtime_intent_0": "pending"},
        "artifact_statuses": {"runtime_artifact_0": "available"},
        "delivery_statuses": {"runtime_delivery_0": "planned"},
        "applied_event_count": 0,
        "resume_count": 0,
        "side_effects": [],
    }
    if activity_boundary is not None:
        snapshot["activity_boundary"] = activity_boundary
    return snapshot


def _assert_no_forbidden_material(value: object) -> None:
    rendered = repr(value).lower()
    for marker in FORBIDDEN_RENDER_MARKERS:
        assert marker.lower() not in rendered


def test_phase5j_activity_contract_defines_safe_stub_inputs_results_and_summary() -> None:
    surface = _phase5j_payload_surface()
    assert surface.ACTIVITY_BOUNDARY_TYPE == ACTIVITY_BOUNDARY_TYPE
    assert surface.ACTIVITY_RESULT_TYPE == ACTIVITY_RESULT_TYPE
    dataclass_types = (
        surface.ClaimCheckRefValidationInput,
        surface.ClaimCheckRefValidationResult,
        surface.AgentTurnActivityInput,
        surface.AgentTurnActivityResult,
        surface.DeliverArtifactActivityInput,
        surface.DeliverArtifactActivityResult,
    )
    assert all(is_dataclass(dataclass_type) for dataclass_type in dataclass_types)
    assert all(dataclass_type.__dataclass_params__.frozen for dataclass_type in dataclass_types)

    claim_input, agent_input, delivery_input = _safe_activity_inputs(surface)
    claim_result, agent_result, delivery_result = _safe_activity_results(surface)
    surface.validate_claim_check_ref_validation_input(claim_input)
    surface.validate_agent_turn_activity_input(agent_input)
    surface.validate_deliver_artifact_activity_input(delivery_input)
    surface.validate_claim_check_ref_validation_result(claim_result)
    surface.validate_agent_turn_activity_result(agent_result)
    surface.validate_deliver_artifact_activity_result(delivery_result)

    summary = surface.build_activity_boundary_summary(
        validation=claim_result,
        agent_turn=agent_result,
        delivery=delivery_result,
        status="completed",
    )

    assert summary == _safe_activity_boundary()
    surface.validate_activity_boundary_summary(summary)
    _assert_no_forbidden_material({"inputs": (claim_input, agent_input, delivery_input), "results": summary})


def test_phase5j_activity_contract_rejects_raw_prompt_tool_output_card_json_platform_ids_and_secret_values() -> None:
    surface = _phase5j_payload_surface()
    claim_input, agent_input, delivery_input = _safe_activity_inputs(surface)
    claim_result, agent_result, delivery_result = _safe_activity_results(surface)
    invalid_cases = (
        (surface.validate_claim_check_ref_validation_input, replace(claim_input, ref="claim_ref_" + "raw_" + "prompt")),
        (surface.validate_agent_turn_activity_input, replace(agent_input, input_ref="claim_ref_" + "tool_" + "output")),
        (surface.validate_deliver_artifact_activity_input, replace(delivery_input, delivery_ref="claim_ref_" + "card_" + "json")),
        (surface.validate_agent_turn_activity_input, replace(agent_input, event_id="runtime_event_" + "oc_" + "private")),
        (surface.validate_deliver_artifact_activity_input, replace(delivery_input, delivery_ref="claim_ref_" + "to" + "ken")),
        (surface.validate_claim_check_ref_validation_result, replace(claim_result, ref="claim_ref_" + "platform_" + "id")),
        (surface.validate_agent_turn_activity_result, replace(agent_result, artifact_ref="claim_ref_" + "platform_" + "payload")),
        (surface.validate_deliver_artifact_activity_result, replace(delivery_result, delivery_ref="claim_ref_" + "se" + "cret")),
    )

    for validator, value in invalid_cases:
        with pytest.raises(ValueError) as exc_info:
            validator(value)
        assert str(exc_info.value) in {"invalid_activity_input", "invalid_activity_result", "unsafe_activity_boundary"}
        _assert_no_forbidden_material(str(exc_info.value))


def test_phase5j_activity_contract_rejects_invalid_kind_activity_type_count_and_size_values() -> None:
    surface = _phase5j_payload_surface()
    claim_input, _agent_input, _delivery_input = _safe_activity_inputs(surface)
    claim_result, agent_result, delivery_result = _safe_activity_results(surface)
    invalid_cases = (
        (surface.validate_claim_check_ref_validation_input, replace(claim_input, kind="prompt")),
        (surface.validate_claim_check_ref_validation_input, replace(claim_input, count=True)),
        (surface.validate_claim_check_ref_validation_input, replace(claim_input, count=-1)),
        (surface.validate_claim_check_ref_validation_input, replace(claim_input, count=21)),
        (surface.validate_claim_check_ref_validation_input, replace(claim_input, size=False)),
        (surface.validate_claim_check_ref_validation_input, replace(claim_input, size=-1)),
        (surface.validate_claim_check_ref_validation_input, replace(claim_input, size=1_048_577)),
        (surface.validate_claim_check_ref_validation_result, replace(claim_result, activity_type="execute_agent_turn")),
        (surface.validate_agent_turn_activity_result, replace(agent_result, activity_type="deliver_artifact")),
        (surface.validate_deliver_artifact_activity_result, replace(delivery_result, activity_type="validate_claim_check_ref")),
    )

    for validator, value in invalid_cases:
        with pytest.raises(ValueError) as exc_info:
            validator(value)
        assert str(exc_info.value) in {"invalid_activity_input", "invalid_activity_result"}
        _assert_no_forbidden_material(str(exc_info.value))


def test_phase5j_activity_contract_requires_runtime_sig_digest_for_checksum_hint() -> None:
    surface = _phase5j_payload_surface()
    claim_input, _agent_input, _delivery_input = _safe_activity_inputs(surface)
    claim_result, _agent_result, _delivery_result = _safe_activity_results(surface)
    bad_hints = (
        "claim_ref_not_a_digest",
        "runtime_sig_" + ("0" * 63),
        "runtime_sig_" + ("0" * 65),
        "runtime_sig_" + ("g" * 64),
        "runtime_sig_" + ("A" * 64),
    )

    for checksum_hint in bad_hints:
        with pytest.raises(ValueError) as input_exc:
            surface.validate_claim_check_ref_validation_input(replace(claim_input, checksum_hint=checksum_hint))
        assert str(input_exc.value) == "invalid_activity_input"
        _assert_no_forbidden_material(str(input_exc.value))

        with pytest.raises(ValueError) as result_exc:
            surface.validate_claim_check_ref_validation_result(replace(claim_result, checksum_hint=checksum_hint))
        assert str(result_exc.value) == "invalid_activity_result"
        _assert_no_forbidden_material(str(result_exc.value))


def test_phase5j_activity_contract_rejects_unknown_nested_activity_boundary_fields() -> None:
    from flowweaver_runtime_client.contracts import make_success_result  # noqa: PLC0415

    for boundary in (
        {
            **_safe_activity_boundary(),
            "refs": {**_safe_activity_boundary()["refs"], "extra_ref": "claim_ref_phase5j_extra"},
        },
        {
            **_safe_activity_boundary(),
            "activities": {**_safe_activity_boundary()["activities"], "unexpected_activity": "completed"},
        },
    ):
        with pytest.raises(ValueError) as exc_info:
            make_success_result(
                operation="query_snapshot",
                workflow_id=SAFE_TRANSACTION_ID,
                snapshot=_safe_snapshot(activity_boundary=boundary),
            )
        assert str(exc_info.value) == "unsafe_activity_boundary"
        _assert_no_forbidden_material(str(exc_info.value))


def test_phase5j_activity_summary_is_schema_compatible_with_snapshot_sanitizer() -> None:
    from flowweaver_runtime_client.contracts import make_success_result  # noqa: PLC0415

    activity_boundary = _safe_activity_boundary()
    result = make_success_result(
        operation="query_snapshot",
        workflow_id=SAFE_TRANSACTION_ID,
        snapshot=_safe_snapshot(activity_boundary=activity_boundary),
    )

    assert result["snapshot"]["activity_boundary"] == activity_boundary
    assert set(result["snapshot"]["activity_boundary"]) == {
        "type",
        "version",
        "status",
        "activities",
        "refs",
        "side_effects",
    }
    _assert_no_forbidden_material(result)

