"""FlowWeaver Phase 32 controlled artifact delivery and ACK Activity.

This module adds a non-production, injected delivery Activity boundary after
Phase 31 agent execution. Workflow history and snapshots carry only safe runtime
ids, artifact refs, delivery refs, ACK status summaries, counts, and stable error
codes. Raw platform/card/media/callback/credential material may only exist
inside caller-injected surfaces and is never returned by this module.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
from datetime import timedelta
from typing import Any, Callable

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from gateway.flowweaver_agent_execution_activity import (
        FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
        validate_flowweaver_agent_execution_result,
    )

FLOWWEAVER_DELIVERY_ACTIVITY_CONTRACT_TYPE = "flowweaver.gateway.delivery_activity_contract.v0"
FLOWWEAVER_DELIVERY_ACTIVITY_REPORT_TYPE = "flowweaver.gateway.delivery_activity_report.v0"
FLOWWEAVER_DELIVERY_ACTIVITY_REQUEST_TYPE = "flowweaver.gateway.delivery_activity_request.v0"
FLOWWEAVER_DELIVERY_ACTIVITY_RESULT_TYPE = "flowweaver.gateway.delivery_activity_result.v0"
FLOWWEAVER_DELIVERY_ACTIVITY_SNAPSHOT_TYPE = "flowweaver.gateway.delivery_activity_snapshot.v0"
FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT = "ready_for_narrow_ai_flow_pilot_request"
FLOWWEAVER_DELIVERY_ACTIVITY_VERSION = "flowweaver.delivery_activity.v0"
FLOWWEAVER_DELIVERY_ACTIVITY_TASK_QUEUE = "flowweaver-phase32-delivery-activity"

_CONTROLLED_ACTIVITY_TYPE = "deliver_artifact"
_REPORT_OPERATION = "build_flowweaver_delivery_activity_report"
_ACTIVITY_TIMEOUT = timedelta(seconds=15)
_ACTIVITY_RETRY_POLICY = RetryPolicy(
    maximum_attempts=2,
    non_retryable_error_types=[
        "invalid_delivery_activity_request",
        "invalid_agent_execution_result",
        "invalid_delivery_slot",
        "delivery_policy_disabled",
        "delivery_surface_required",
        "runtime_control_surface_required",
        "uninitialized_ack_target",
        "delivery_target_mismatch",
        "invalid_ack_update",
        "unsafe_material",
        "delivery_cancelled",
    ],
)
_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_verdict",
    "entrypoints",
    "request_fields",
    "result_fields",
    "snapshot_fields",
    "report_fields",
    "delivery_surface_boundary",
    "runtime_policy",
    "ack_policy",
    "retry_policy",
    "checks",
    "separate_approvals",
    "forbidden_side_effects",
    "side_effects",
]
_REQUEST_FIELDS = [
    "type",
    "version",
    "phase",
    "transaction_id",
    "workflow_id",
    "intent_id",
    "agent_execution_result",
    "initialized_delivery_slots",
    "delivery_policy",
    "required_surfaces",
    "delivery_digest",
    "side_effects",
]
_RESULT_FIELDS = [
    "type",
    "version",
    "phase",
    "activity",
    "status",
    "artifact_ref",
    "delivery_refs",
    "surface_state",
    "ack_updates",
    "ack_results",
    "counts",
    "delivery_digest",
    "error_code",
    "retry_class",
    "side_effects",
]
_SNAPSHOT_FIELDS = [
    "type",
    "version",
    "phase",
    "transaction_id",
    "workflow_id",
    "status",
    "intent_statuses",
    "artifact_refs",
    "delivery_refs",
    "surface_state",
    "activity_sequence",
    "counts",
    "delivery_digest",
    "error_code",
    "side_effects",
]
_REPORT_FIELDS = [
    "type",
    "version",
    "phase",
    "ok",
    "verdict",
    "operation",
    "phase31_verdict",
    "controlled_delivery_verified",
    "ack_reconciliation_verified",
    "history_no_leak_checked",
    "result_no_leak_checked",
    "checks",
    "error_code",
    "side_effects",
]
_ERROR_REPORT_FIELDS = ["type", "version", "phase", "ok", "operation", "error_code", "side_effects"]
_ENTRYPOINTS = [
    "describe_flowweaver_delivery_activity_contract",
    "build_flowweaver_delivery_activity_request",
    "validate_flowweaver_delivery_activity_request",
    "deliver_controlled_artifact",
    "build_deliver_artifact_activity",
    "validate_flowweaver_delivery_activity_result",
    "validate_flowweaver_delivery_activity_snapshot",
    "build_flowweaver_delivery_activity_report",
    "validate_flowweaver_delivery_activity_report",
]
_DELIVERY_SURFACE_BOUNDARY = {
    "mode": "injected_delivery_surface_only",
    "surface_input": "safe_artifact_ref_delivery_slots_and_runtime_ids_only",
    "raw_material_access": "delivery_surface_boundary_only",
    "surface_output": "sanitized_ack_updates_only",
    "gateway_adapter_factory": "forbidden",
    "side_effects": [],
}
_RUNTIME_POLICY = {
    "mode": "controlled_non_production_delivery_ack_activity",
    "temporal_runtime": "local_staging_only",
    "gateway_delivery": "injected_surface_only",
    "runtime_ack_reconciliation": "injected_control_surface_required_when_enabled",
    "production_gateway_wiring": "forbidden",
    "surface_state_separation": "required",
    "side_effects": [],
}
_ACK_POLICY = {
    "initialized_slots_only": True,
    "target_order": "deterministic_bounded_prefix",
    "allowed_surfaces": ["progress_card", "rich_card", "final_text", "media"],
    "allowed_ack_statuses": ["sent", "failed", "acknowledged"],
    "runtime_result_statuses": ["applied", "duplicate", "rejected"],
    "rich_card_never_implies_final_text": True,
    "side_effects": [],
}
_RETRY_POLICY_DESCRIPTOR = {
    "start_to_close_timeout_seconds": 15,
    "maximum_attempts": 2,
    "non_retryable_error_types": [
        "invalid_delivery_activity_request",
        "invalid_agent_execution_result",
        "invalid_delivery_slot",
        "delivery_policy_disabled",
        "delivery_surface_required",
        "runtime_control_surface_required",
        "uninitialized_ack_target",
        "delivery_target_mismatch",
        "invalid_ack_update",
        "unsafe_material",
        "delivery_cancelled",
    ],
    "transient_error_types": [
        "delivery_surface_failed",
        "delivery_surface_timeout",
        "runtime_query_failed",
        "runtime_reconciliation_failed",
        "unsafe_runtime_output",
    ],
}
_CHECKS = [
    "phase31_verdict_valid",
    "delivery_surface_injected_and_observable",
    "default_off_zero_delivery_calls",
    "ack_targets_initialized_only",
    "ack_prefix_order_verified",
    "ack_replay_idempotent",
    "surface_state_separated",
    "rich_card_does_not_suppress_final_text",
    "failure_timeout_cancel_preserve_delivery_state",
    "history_no_leak_verified",
    "gateway_wiring_absent",
    "side_effects_absent",
]
_SEPARATE_APPROVALS = [
    "narrow_ai_flow_pilot",
    "production_gateway_wiring",
    "production_delivery_enablement",
    "production_agent_execution",
    "production_config_write",
    "gateway_restart",
    "platform_adapter_mutation",
    "gateway_owned_worker_lifecycle",
]
_FORBIDDEN_SIDE_EFFECTS = [
    "gateway_run_change",
    "gateway_platform_adapter_access",
    "gateway_adapter_factory",
    "platform_adapter_mutation",
    "production_config_write",
    "gateway_restart",
    "client_connect_factory",
    "workflow_environment_factory",
    "worker_lifecycle",
    "sub" + "process",
    "sock" + "et",
    "dock" + "er",
    "daemon",
    "service_startup",
    "raw_material_persistence",
]
_DELIVERY_POLICY_SURFACES = ["progress_card", "rich_card", "final_text", "media"]
_DELIVERY_POLICY_MODE = "controlled_non_production_delivery_activity"
_DELIVERY_SLOT_FIELDS = ["delivery_ref", "surface", "artifact_ref", "required"]
_SURFACE_REQUEST_FIELDS = [
    "transaction_id",
    "workflow_id",
    "intent_id",
    "artifact_ref",
    "artifact_kind",
    "initialized_delivery_slots",
    "required_surfaces",
    "delivery_policy",
    "delivery_digest",
]
_SURFACE_RESPONSE_FIELDS = ["status", "ack_updates"]
_ACK_UPDATE_FIELDS = ["delivery_ref", "surface", "status", "ack_ref"]
_ACK_RESULT_FIELDS = ["status", "delivery_ref", "surface", "error_code", "side_effects"]
_AGENT_RESULT_FIELDS = [
    "type",
    "version",
    "phase",
    "activity",
    "status",
    "artifact_ref",
    "artifact_kind",
    "counts",
    "output_digest",
    "error_code",
    "retry_class",
    "side_effects",
]
_AGENT_RESULT_COUNT_FIELDS = ["executor_calls", "tool_calls", "output_items"]
_SURFACE_STATE_FIELDS = ["progress_card_sent", "rich_cards_sent", "final_text_sent", "media_sent"]
_RESULT_COUNT_FIELDS = ["delivery_calls", "ack_updates", "ack_applied", "ack_duplicates", "ack_rejected"]
_SNAPSHOT_COUNT_FIELDS = ["activities", "artifacts", "deliveries", "ack_updates", "ack_applied", "ack_duplicates", "ack_rejected"]
_RAW_VALUE_MARKERS = (
    "oc_",
    "ou_",
    "om_",
    "raw prompt",
    "raw tool output",
    "tool_output",
    "raw_output",
    "card_json",
    "media_path",
    "media_bytes",
    "/tmp/",
    "callback payload",
    "callback_payload",
    "delivery_ack_payload",
    "runtimeerror:",
    "valueerror:",
    "traceback",
    "unsafe-token",
    "bearer ",
    "password" + "=",
    "secret" + "=",
    "api_" + "key=",
    "sk" + "-",
    "platform_id",
    "chat_id",
    "user_id",
    "message_id",
    "credential",
    "private",
)
_NON_RETRYABLE_ERRORS = {
    "invalid_delivery_activity_request",
    "invalid_agent_execution_result",
    "invalid_delivery_slot",
    "delivery_policy_disabled",
    "delivery_surface_required",
    "runtime_control_surface_required",
    "uninitialized_ack_target",
    "delivery_target_mismatch",
    "invalid_ack_update",
    "unsafe_material",
    "delivery_cancelled",
}
_TRANSIENT_ERRORS = {
    "delivery_surface_failed",
    "delivery_surface_timeout",
    "runtime_query_failed",
    "runtime_reconciliation_failed",
    "unsafe_runtime_output",
    "final_text_delivery_missing",
}
_SAFE_ERROR_CODES = _NON_RETRYABLE_ERRORS | _TRANSIENT_ERRORS
_HEX = frozenset("0123456789abcdef")
_MAX_PLAIN_TREE_DEPTH = 64
_ZERO_DIGEST = "sha256:" + ("0" * 64)


def describe_flowweaver_delivery_activity_contract() -> dict[str, object]:
    """Return the exact Phase 32 controlled delivery Activity descriptor."""

    return {
        "type": FLOWWEAVER_DELIVERY_ACTIVITY_CONTRACT_TYPE,
        "version": FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
        "phase": "phase32",
        "verdict": FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT,
        "scope": "controlled_delivery_activity_ack_reconciliation",
        "consumes_verdict": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        "entrypoints": list(_ENTRYPOINTS),
        "request_fields": list(_REQUEST_FIELDS),
        "result_fields": list(_RESULT_FIELDS),
        "snapshot_fields": list(_SNAPSHOT_FIELDS),
        "report_fields": list(_REPORT_FIELDS),
        "delivery_surface_boundary": copy.deepcopy(_DELIVERY_SURFACE_BOUNDARY),
        "runtime_policy": copy.deepcopy(_RUNTIME_POLICY),
        "ack_policy": copy.deepcopy(_ACK_POLICY),
        "retry_policy": copy.deepcopy(_RETRY_POLICY_DESCRIPTOR),
        "checks": list(_CHECKS),
        "separate_approvals": list(_SEPARATE_APPROVALS),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }


def build_flowweaver_delivery_activity_request(
    *,
    transaction_id: object,
    workflow_id: object,
    intent_id: object,
    agent_execution_result: object,
    initialized_delivery_slots: object,
    enabled: object = False,
) -> dict[str, object]:
    """Build a safe Phase 32 delivery request from Phase 31 artifact metadata."""

    is_enabled = _bool(enabled, "invalid_delivery_activity_request")
    tx_id = _safe_identifier(transaction_id, prefix="runtime_tx_", error="invalid_delivery_activity_request")
    wf_id = _safe_identifier(workflow_id, prefix="runtime_tx_", error="invalid_delivery_activity_request")
    if wf_id != tx_id:
        _raise("invalid_delivery_activity_request")
    safe_intent_id = _safe_identifier(intent_id, prefix="runtime_intent_", error="invalid_delivery_activity_request")
    safe_agent_result = _validated_agent_result(
        agent_execution_result,
        error="invalid_agent_execution_result",
        exact_order=True,
    )
    artifact_ref = str(safe_agent_result["artifact_ref"])
    safe_slots = _delivery_slots(
        initialized_delivery_slots,
        artifact_ref=artifact_ref,
        error="invalid_delivery_slot",
        exact_order=True,
    )
    required_surfaces = _required_surfaces(safe_slots)
    digest = _delivery_digest(
        transaction_id=tx_id,
        intent_id=safe_intent_id,
        artifact_ref=artifact_ref,
        delivery_refs=[str(slot["delivery_ref"]) for slot in safe_slots],
        required_surfaces=required_surfaces,
        enabled=is_enabled,
    )
    request = {
        "type": FLOWWEAVER_DELIVERY_ACTIVITY_REQUEST_TYPE,
        "version": FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
        "phase": "phase32",
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "intent_id": safe_intent_id,
        "agent_execution_result": safe_agent_result,
        "initialized_delivery_slots": safe_slots,
        "delivery_policy": _delivery_policy(is_enabled),
        "required_surfaces": required_surfaces,
        "delivery_digest": digest,
        "side_effects": [],
    }
    return validate_flowweaver_delivery_activity_request(request)


def validate_flowweaver_delivery_activity_request(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 32 delivery request copy."""

    return _validate_flowweaver_delivery_activity_request(value, exact_order=True)


def _validate_flowweaver_delivery_activity_request(value: object, *, exact_order: bool) -> dict[str, object]:
    error = "invalid_delivery_activity_request"
    source = (
        _plain_dict_with_fields(value, _REQUEST_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _REQUEST_FIELDS, error)
    )
    tx_id = _safe_identifier(source["transaction_id"], prefix="runtime_tx_", error=error)
    wf_id = _safe_identifier(source["workflow_id"], prefix="runtime_tx_", error=error)
    if wf_id != tx_id:
        _raise(error)
    safe_intent_id = _safe_identifier(source["intent_id"], prefix="runtime_intent_", error=error)
    safe_agent_result = _validated_agent_result(
        source["agent_execution_result"],
        error="invalid_agent_execution_result",
        exact_order=exact_order,
    )
    artifact_ref = str(safe_agent_result["artifact_ref"])
    safe_slots = _delivery_slots(
        source["initialized_delivery_slots"],
        artifact_ref=artifact_ref,
        error="invalid_delivery_slot",
        exact_order=exact_order,
    )
    enabled = _delivery_policy_enabled(source["delivery_policy"], error=error, exact_order=exact_order)
    required_surfaces = _required_surfaces(safe_slots)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_DELIVERY_ACTIVITY_REQUEST_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_DELIVERY_ACTIVITY_VERSION, error),
        "phase": _literal(source["phase"], "phase32", error),
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "intent_id": safe_intent_id,
        "agent_execution_result": safe_agent_result,
        "initialized_delivery_slots": safe_slots,
        "delivery_policy": _exact_delivery_policy(source["delivery_policy"], enabled=enabled, error=error, exact_order=exact_order),
        "required_surfaces": _exact_string_list(source["required_surfaces"], required_surfaces, error),
        "delivery_digest": _digest(source["delivery_digest"], error=error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    expected_digest = _delivery_digest(
        transaction_id=tx_id,
        intent_id=safe_intent_id,
        artifact_ref=artifact_ref,
        delivery_refs=[str(slot["delivery_ref"]) for slot in safe_slots],
        required_surfaces=required_surfaces,
        enabled=enabled,
    )
    if safe["delivery_digest"] != expected_digest:
        _raise(error)
    return safe


async def deliver_controlled_artifact(
    *,
    delivery_request: object,
    delivery_surface: Callable[[dict[str, object]], object],
    runtime_control_surface: object,
) -> dict[str, object]:
    """Call injected delivery and runtime surfaces and return sanitized ACK state."""

    return await _deliver_controlled_artifact(
        delivery_request=delivery_request,
        delivery_surface=delivery_surface,
        runtime_control_surface=runtime_control_surface,
        exact_order=True,
    )


async def _deliver_controlled_artifact(
    *,
    delivery_request: object,
    delivery_surface: Callable[[dict[str, object]], object],
    runtime_control_surface: object,
    exact_order: bool,
) -> dict[str, object]:

    if _contains_forbidden_material(delivery_request):
        return _delivery_result(
            status="rejected",
            artifact_ref=None,
            delivery_refs=[],
            surface_state=_empty_surface_state(),
            ack_updates=[],
            ack_results=[],
            counts=_empty_result_counts(0),
            delivery_digest=_ZERO_DIGEST,
            error_code="unsafe_material",
        )
    try:
        request = _validate_flowweaver_delivery_activity_request(delivery_request, exact_order=exact_order)
    except ValueError as exc:
        code = _pre_delivery_error_code(str(exc))
        return _delivery_result(
            status="rejected",
            artifact_ref=None,
            delivery_refs=[],
            surface_state=_empty_surface_state(),
            ack_updates=[],
            ack_results=[],
            counts=_empty_result_counts(0),
            delivery_digest=_ZERO_DIGEST,
            error_code=code,
        )

    artifact_ref = str(request["agent_execution_result"]["artifact_ref"])
    delivery_digest = str(request["delivery_digest"])
    if request["delivery_policy"]["enabled"] is False:
        return _delivery_result(
            status="disabled",
            artifact_ref=artifact_ref,
            delivery_refs=[],
            surface_state=_empty_surface_state(),
            ack_updates=[],
            ack_results=[],
            counts=_empty_result_counts(0),
            delivery_digest=delivery_digest,
            error_code="delivery_policy_disabled",
        )
    if not callable(delivery_surface):
        return _delivery_result(
            status="rejected",
            artifact_ref=artifact_ref,
            delivery_refs=[],
            surface_state=_empty_surface_state(),
            ack_updates=[],
            ack_results=[],
            counts=_empty_result_counts(0),
            delivery_digest=delivery_digest,
            error_code="delivery_surface_required",
        )
    if not _has_runtime_reconciler(runtime_control_surface):
        return _delivery_result(
            status="rejected",
            artifact_ref=artifact_ref,
            delivery_refs=[],
            surface_state=_empty_surface_state(),
            ack_updates=[],
            ack_results=[],
            counts=_empty_result_counts(0),
            delivery_digest=delivery_digest,
            error_code="runtime_control_surface_required",
        )

    surface_request = _surface_request(request)
    try:
        surface_response = delivery_surface(surface_request)
        if inspect.isawaitable(surface_response):
            surface_response = await surface_response
    except asyncio.CancelledError:
        return _delivery_result(
            status="cancelled",
            artifact_ref=artifact_ref,
            delivery_refs=[],
            surface_state=_empty_surface_state(),
            ack_updates=[],
            ack_results=[],
            counts=_empty_result_counts(1),
            delivery_digest=delivery_digest,
            error_code="delivery_cancelled",
        )
    except Exception:
        return _delivery_result(
            status="rejected",
            artifact_ref=artifact_ref,
            delivery_refs=[],
            surface_state=_empty_surface_state(),
            ack_updates=[],
            ack_results=[],
            counts=_empty_result_counts(1),
            delivery_digest=delivery_digest,
            error_code="delivery_surface_failed",
        )

    try:
        surface_status, ack_updates = _surface_result(surface_response, request)
    except ValueError as exc:
        code = _surface_output_error_code(str(exc))
        return _delivery_result(
            status="rejected",
            artifact_ref=artifact_ref,
            delivery_refs=[],
            surface_state=_empty_surface_state(),
            ack_updates=[],
            ack_results=[],
            counts=_empty_result_counts(1),
            delivery_digest=delivery_digest,
            error_code=code,
        )

    if surface_status == "timed_out":
        return _delivery_result(
            status="timed_out",
            artifact_ref=artifact_ref,
            delivery_refs=[],
            surface_state=_empty_surface_state(),
            ack_updates=[],
            ack_results=[],
            counts=_empty_result_counts(1),
            delivery_digest=delivery_digest,
            error_code="delivery_surface_timeout",
        )

    ack_results: list[dict[str, object]] = []
    for update in ack_updates:
        stable_update = copy.deepcopy(update)
        try:
            runtime_result = runtime_control_surface.reconcile_delivery_ack(copy.deepcopy(stable_update))
            if inspect.isawaitable(runtime_result):
                runtime_result = await runtime_result
            ack_results.append(_ack_result(runtime_result, update=stable_update, error="unsafe_runtime_output"))
        except asyncio.CancelledError:
            reconciled_updates = copy.deepcopy(ack_updates[: len(ack_results)])
            return _delivery_result(
                status="cancelled",
                artifact_ref=artifact_ref,
                delivery_refs=[str(item["delivery_ref"]) for item in reconciled_updates],
                surface_state=_surface_state(reconciled_updates),
                ack_updates=reconciled_updates,
                ack_results=ack_results,
                counts=_counts_from_ack_results(1, reconciled_updates, ack_results),
                delivery_digest=delivery_digest,
                error_code="delivery_cancelled",
            )
        except Exception:
            reconciled_updates = copy.deepcopy(ack_updates[: len(ack_results)])
            return _delivery_result(
                status="rejected",
                artifact_ref=artifact_ref,
                delivery_refs=[str(item["delivery_ref"]) for item in reconciled_updates],
                surface_state=_surface_state(reconciled_updates),
                ack_updates=reconciled_updates,
                ack_results=ack_results,
                counts=_counts_from_ack_results(1, reconciled_updates, ack_results),
                delivery_digest=delivery_digest,
                error_code="runtime_reconciliation_failed",
            )

    surface_state = _surface_state(ack_updates)
    delivery_refs = [str(item["delivery_ref"]) for item in ack_updates]
    counts = _counts_from_ack_results(1, ack_updates, ack_results)
    if any(result["status"] == "rejected" for result in ack_results):
        return _delivery_result(
            status="rejected",
            artifact_ref=artifact_ref,
            delivery_refs=delivery_refs,
            surface_state=surface_state,
            ack_updates=ack_updates,
            ack_results=ack_results,
            counts=counts,
            delivery_digest=delivery_digest,
            error_code="runtime_reconciliation_failed",
        )
    if any(update["status"] == "failed" for update in ack_updates):
        return _delivery_result(
            status="partially_delivered",
            artifact_ref=artifact_ref,
            delivery_refs=delivery_refs,
            surface_state=surface_state,
            ack_updates=ack_updates,
            ack_results=ack_results,
            counts=counts,
            delivery_digest=delivery_digest,
            error_code="runtime_reconciliation_failed",
        )
    if request["delivery_policy"]["final_text_required"] is True and surface_state["final_text_sent"] is False:
        return _delivery_result(
            status="partially_delivered",
            artifact_ref=artifact_ref,
            delivery_refs=delivery_refs,
            surface_state=surface_state,
            ack_updates=ack_updates,
            ack_results=ack_results,
            counts=counts,
            delivery_digest=delivery_digest,
            error_code="final_text_delivery_missing",
        )
    if len(ack_updates) < len(request["initialized_delivery_slots"]) or surface_status == "partial":
        return _delivery_result(
            status="partially_delivered",
            artifact_ref=artifact_ref,
            delivery_refs=delivery_refs,
            surface_state=surface_state,
            ack_updates=ack_updates,
            ack_results=ack_results,
            counts=counts,
            delivery_digest=delivery_digest,
            error_code="runtime_reconciliation_failed",
        )
    return _delivery_result(
        status="delivered",
        artifact_ref=artifact_ref,
        delivery_refs=delivery_refs,
        surface_state=surface_state,
        ack_updates=ack_updates,
        ack_results=ack_results,
        counts=counts,
        delivery_digest=delivery_digest,
        error_code=None,
    )


def build_deliver_artifact_activity(
    *,
    delivery_surface: Callable[[dict[str, object]], object],
    runtime_control_surface: object,
) -> Callable[[dict[str, Any]], Any]:
    """Build the Temporal Activity wrapper with explicit caller-supplied surfaces."""

    if not callable(delivery_surface):
        _raise("delivery_surface_required")
    if not _has_runtime_reconciler(runtime_control_surface):
        _raise("runtime_control_surface_required")

    @activity.defn(name=_CONTROLLED_ACTIVITY_TYPE)
    async def deliver_artifact_controlled_activity(payload: dict[str, Any]) -> dict[str, Any]:
        if _contains_forbidden_material(payload):
            return _delivery_result(
                status="rejected",
                artifact_ref=None,
                delivery_refs=[],
                surface_state=_empty_surface_state(),
                ack_updates=[],
                ack_results=[],
                counts=_empty_result_counts(0),
                delivery_digest=_ZERO_DIGEST,
                error_code="unsafe_material",
            )
        result = await _deliver_controlled_artifact(
            delivery_request=payload,
            delivery_surface=delivery_surface,
            runtime_control_surface=runtime_control_surface,
            exact_order=False,
        )
        return dict(result)

    return deliver_artifact_controlled_activity


def validate_flowweaver_delivery_activity_result(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 32 Activity result."""

    return _validate_flowweaver_delivery_activity_result(value, exact_order=True)


def _validate_flowweaver_delivery_activity_result(value: object, *, exact_order: bool) -> dict[str, object]:
    error = "invalid_delivery_activity_result"
    source = (
        _plain_dict_with_fields(value, _RESULT_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _RESULT_FIELDS, error)
    )
    status = _one_of(source["status"], {"delivered", "partially_delivered", "disabled", "rejected", "timed_out", "cancelled"}, error)
    error_code = _result_error_code(source["error_code"], status=status, error=error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_DELIVERY_ACTIVITY_RESULT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_DELIVERY_ACTIVITY_VERSION, error),
        "phase": _literal(source["phase"], "phase32", error),
        "activity": _literal(source["activity"], _CONTROLLED_ACTIVITY_TYPE, error),
        "status": status,
        "artifact_ref": _optional_safe_identifier(source["artifact_ref"], prefix="runtime_artifact_", error=error),
        "delivery_refs": _safe_identifier_list(source["delivery_refs"], prefix="runtime_delivery_", error=error, strict_numeric_suffix=True),
        "surface_state": _surface_state_value(source["surface_state"], error=error, exact_order=exact_order),
        "ack_updates": _ack_updates_for_validation(source["ack_updates"], error=error, exact_order=exact_order),
        "ack_results": _ack_results_for_validation(source["ack_results"], error=error, exact_order=exact_order),
        "counts": _result_counts(source["counts"], error=error, exact_order=exact_order),
        "delivery_digest": _digest(source["delivery_digest"], error=error),
        "error_code": error_code,
        "retry_class": _retry_class(source["retry_class"], error_code=error_code, error=error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    _validate_result_semantics(safe, error=error)
    return safe


def _validate_result_semantics(result: dict[str, object], *, error: str) -> None:
    status = str(result["status"])
    delivery_refs = result["delivery_refs"]
    ack_updates = result["ack_updates"]
    ack_results = result["ack_results"]
    counts = result["counts"]
    surface_state = result["surface_state"]
    if type(delivery_refs) is not list or type(ack_updates) is not list or type(ack_results) is not list:
        _raise(error)
    if type(counts) is not dict or type(surface_state) is not dict:
        _raise(error)
    if len(set(delivery_refs)) != len(delivery_refs):
        _raise(error)
    update_refs = [item["delivery_ref"] for item in ack_updates if type(item) is dict]
    if delivery_refs != update_refs:
        _raise(error)
    if len(ack_results) != len(ack_updates):
        _raise(error)
    for update, ack_result in zip(ack_updates, ack_results):
        if type(update) is not dict or type(ack_result) is not dict:
            _raise(error)
        if update["delivery_ref"] != ack_result["delivery_ref"] or update["surface"] != ack_result["surface"]:
            _raise(error)
    expected_counts = _counts_from_ack_results(int(counts["delivery_calls"]), ack_updates, ack_results)
    if counts != expected_counts:
        _raise(error)
    if surface_state != _surface_state(ack_updates):
        _raise(error)
    if status == "delivered":
        if result["artifact_ref"] is None:
            _raise(error)
        if counts["delivery_calls"] != 1 or not delivery_refs:
            _raise(error)
        if surface_state["final_text_sent"] is not True:
            _raise(error)
        if any(update["status"] == "failed" for update in ack_updates):
            _raise(error)
        if any(ack_result["status"] == "rejected" for ack_result in ack_results):
            _raise(error)
    if status == "disabled":
        if counts["delivery_calls"] != 0 or delivery_refs or ack_updates or ack_results:
            _raise(error)
        if surface_state != _empty_surface_state() or result["error_code"] != "delivery_policy_disabled":
            _raise(error)


def validate_flowweaver_delivery_activity_snapshot(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 32 workflow snapshot copy."""

    return _validate_flowweaver_delivery_activity_snapshot(value, exact_order=True)


def _validate_flowweaver_delivery_activity_snapshot(value: object, *, exact_order: bool) -> dict[str, object]:
    error = "invalid_delivery_activity_snapshot"
    source = (
        _plain_dict_with_fields(value, _SNAPSHOT_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _SNAPSHOT_FIELDS, error)
    )
    tx_id = _safe_identifier(source["transaction_id"], prefix="runtime_tx_", error=error)
    wf_id = _safe_identifier(source["workflow_id"], prefix="runtime_tx_", error=error)
    if wf_id != tx_id:
        _raise(error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_DELIVERY_ACTIVITY_SNAPSHOT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_DELIVERY_ACTIVITY_VERSION, error),
        "phase": _literal(source["phase"], "phase32", error),
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "status": _one_of(
            source["status"],
            {"created", "running", "delivery_completed", "partially_delivered", "disabled", "rejected", "timed_out", "cancelled"},
            error,
        ),
        "intent_statuses": _intent_statuses(source["intent_statuses"], error=error),
        "artifact_refs": _safe_identifier_list(source["artifact_refs"], prefix="runtime_artifact_", error=error),
        "delivery_refs": _safe_identifier_list(source["delivery_refs"], prefix="runtime_delivery_", error=error, strict_numeric_suffix=True),
        "surface_state": _surface_state_value(source["surface_state"], error=error, exact_order=exact_order),
        "activity_sequence": _activity_sequence(source["activity_sequence"], error=error, exact_order=exact_order),
        "counts": _snapshot_counts(source["counts"], error=error, exact_order=exact_order),
        "delivery_digest": _digest(source["delivery_digest"], error=error),
        "error_code": _snapshot_error_code(source["error_code"], error=error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    return safe


def validate_flowweaver_delivery_activity_report(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 32 report copy."""

    error = "invalid_delivery_activity_report"
    if type(value) is dict and _keys_match_exactly(value, _ERROR_REPORT_FIELDS):
        return _validate_error_report(value, error=error)
    source = _plain_dict_with_fields(value, _REPORT_FIELDS, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_DELIVERY_ACTIVITY_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_DELIVERY_ACTIVITY_VERSION, error),
        "phase": _literal(source["phase"], "phase32", error),
        "ok": _true(source["ok"], error),
        "verdict": _literal(source["verdict"], FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT, error),
        "operation": _literal(source["operation"], _REPORT_OPERATION, error),
        "phase31_verdict": _literal(source["phase31_verdict"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT, error),
        "controlled_delivery_verified": _true(source["controlled_delivery_verified"], error),
        "ack_reconciliation_verified": _true(source["ack_reconciliation_verified"], error),
        "history_no_leak_checked": _true(source["history_no_leak_checked"], error),
        "result_no_leak_checked": _true(source["result_no_leak_checked"], error),
        "checks": _checks(source["checks"], error=error),
        "error_code": _none(source["error_code"], error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    return safe


def build_flowweaver_delivery_activity_report(
    *,
    agent_execution_activity_version: object,
    agent_execution_activity_verdict: object,
    delivery_result: object,
    history_no_leak_checked: object,
) -> dict[str, object]:
    """Build Phase 32 metadata from sanitized controlled delivery evidence."""

    try:
        _literal(
            agent_execution_activity_version,
            FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
            "invalid_phase31_agent_execution_activity_report",
        )
        _literal(
            agent_execution_activity_verdict,
            FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
            "invalid_phase31_agent_execution_activity_report",
        )
        result = validate_flowweaver_delivery_activity_result(delivery_result)
        if result["status"] != "delivered":
            _raise("invalid_controlled_delivery_result")
        _true(history_no_leak_checked, "invalid_controlled_delivery_result")
    except ValueError as exc:
        code = str(exc)
        if code not in {"invalid_phase31_agent_execution_activity_report", "invalid_controlled_delivery_result"}:
            code = "invalid_controlled_delivery_result"
        return _error_report(code)
    report = {
        "type": FLOWWEAVER_DELIVERY_ACTIVITY_REPORT_TYPE,
        "version": FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
        "phase": "phase32",
        "ok": True,
        "verdict": FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT,
        "operation": _REPORT_OPERATION,
        "phase31_verdict": agent_execution_activity_verdict,
        "controlled_delivery_verified": True,
        "ack_reconciliation_verified": True,
        "history_no_leak_checked": True,
        "result_no_leak_checked": True,
        "checks": {key: True for key in _CHECKS},
        "error_code": None,
        "side_effects": [],
    }
    return validate_flowweaver_delivery_activity_report(report)


@workflow.defn
class FlowWeaverDeliveryActivityWorkflow:
    """Local/staging workflow that executes injected delivery and ACK reconciliation."""

    def __init__(self) -> None:
        self._transaction_id = "runtime_tx_uninitialized"
        self._workflow_id = "runtime_tx_uninitialized"
        self._status = "created"
        self._intent_statuses: dict[str, str] = {}
        self._artifact_refs: list[str] = []
        self._delivery_refs: list[str] = []
        self._surface_state = _empty_surface_state()
        self._activity_sequence: list[dict[str, Any]] = []
        self._counts = _empty_snapshot_counts(0, 0)
        self._delivery_digest = _ZERO_DIGEST
        self._error_code: str | None = None

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            request = _validate_flowweaver_delivery_activity_request(payload, exact_order=False)
        except ValueError as exc:
            self._status = "rejected"
            self._error_code = _safe_error_code(str(exc), fallback="invalid_delivery_activity_request")
            return self._snapshot()

        self._transaction_id = str(request["transaction_id"])
        self._workflow_id = str(request["workflow_id"])
        intent_id = str(request["intent_id"])
        artifact_ref = str(request["agent_execution_result"]["artifact_ref"])
        self._status = "running"
        self._intent_statuses = {intent_id: "running"}
        self._artifact_refs = [artifact_ref]
        self._delivery_refs = []
        self._surface_state = _empty_surface_state()
        self._activity_sequence = []
        self._counts = _empty_snapshot_counts(0, 1)
        self._delivery_digest = str(request["delivery_digest"])
        self._error_code = None

        activity_result = await workflow.execute_activity(
            _CONTROLLED_ACTIVITY_TYPE,
            request,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY_POLICY,
        )
        safe_result = _validate_flowweaver_delivery_activity_result(activity_result, exact_order=False)
        self._record_activity_result(_CONTROLLED_ACTIVITY_TYPE, safe_result)
        self._delivery_refs = [str(item) for item in safe_result["delivery_refs"]]
        self._surface_state = _surface_state_value(safe_result["surface_state"], error="invalid_delivery_activity_snapshot")
        self._counts = _snapshot_counts_from_result(safe_result)
        self._delivery_digest = str(safe_result["delivery_digest"])
        self._error_code = _safe_error_code(safe_result["error_code"], fallback=None)
        if safe_result["status"] == "delivered":
            self._status = "delivery_completed"
            self._intent_statuses[intent_id] = "delivered"
        elif safe_result["status"] == "partially_delivered":
            self._status = "partially_delivered"
            self._intent_statuses[intent_id] = "partially_delivered"
        elif safe_result["status"] == "disabled":
            self._status = "disabled"
            self._intent_statuses[intent_id] = "disabled"
        elif safe_result["status"] == "timed_out":
            self._status = "timed_out"
            self._intent_statuses[intent_id] = "timed_out"
        elif safe_result["status"] == "cancelled":
            self._status = "cancelled"
            self._intent_statuses[intent_id] = "cancelled"
        else:
            self._status = "rejected"
            self._intent_statuses[intent_id] = "rejected"
        return self._snapshot()

    @workflow.query
    def query_snapshot(self) -> dict[str, Any]:
        return self._snapshot()

    def _record_activity_result(self, name: str, result: dict[str, Any]) -> None:
        self._activity_sequence.append(
            {
                "name": name,
                "status": _safe_activity_status(name, result.get("status")),
                "error_code": _safe_error_code(result.get("error_code"), fallback=None),
                "side_effects": [],
            }
        )

    def _snapshot(self) -> dict[str, Any]:
        snapshot = {
            "type": FLOWWEAVER_DELIVERY_ACTIVITY_SNAPSHOT_TYPE,
            "version": FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
            "phase": "phase32",
            "transaction_id": self._transaction_id,
            "workflow_id": self._workflow_id,
            "status": self._status,
            "intent_statuses": dict(sorted(self._intent_statuses.items())),
            "artifact_refs": list(self._artifact_refs),
            "delivery_refs": list(self._delivery_refs),
            "surface_state": dict(self._surface_state),
            "activity_sequence": [dict(item) for item in self._activity_sequence],
            "counts": dict(self._counts),
            "delivery_digest": self._delivery_digest,
            "error_code": self._error_code,
            "side_effects": [],
        }
        return _validate_flowweaver_delivery_activity_snapshot(snapshot, exact_order=True)


def _surface_request(request: dict[str, object]) -> dict[str, object]:
    agent_result = request["agent_execution_result"]
    if type(agent_result) is not dict:
        _raise("invalid_delivery_activity_request")
    return {
        "transaction_id": request["transaction_id"],
        "workflow_id": request["workflow_id"],
        "intent_id": request["intent_id"],
        "artifact_ref": agent_result["artifact_ref"],
        "artifact_kind": agent_result["artifact_kind"],
        "initialized_delivery_slots": copy.deepcopy(request["initialized_delivery_slots"]),
        "required_surfaces": list(request["required_surfaces"]),
        "delivery_policy": copy.deepcopy(request["delivery_policy"]),
        "delivery_digest": request["delivery_digest"],
    }


def _surface_result(value: object, request: dict[str, object]) -> tuple[str, list[dict[str, object]]]:
    if _contains_forbidden_material(value):
        _raise("unsafe_runtime_output")
    source = _plain_dict_with_fields(value, _SURFACE_RESPONSE_FIELDS, "invalid_ack_update")
    status = _one_of(source["status"], {"completed", "partial", "timed_out"}, "invalid_ack_update")
    if status == "timed_out":
        return status, []
    return status, _ack_updates(source["ack_updates"], request=request, error="invalid_ack_update")


def _ack_updates(value: object, *, request: dict[str, object], error: str) -> list[dict[str, object]]:
    if type(value) is not list or len(value) > len(request["initialized_delivery_slots"]):
        _raise(error)
    slots = request["initialized_delivery_slots"]
    if type(slots) is not list:
        _raise(error)
    initialized_refs = {str(slot["delivery_ref"]) for slot in slots if type(slot) is dict}
    safe: list[dict[str, object]] = []
    for index, item in enumerate(value):
        update = _ack_update(item, error=error)
        delivery_ref = str(update["delivery_ref"])
        if delivery_ref not in initialized_refs:
            _raise("uninitialized_ack_target")
        expected_slot = slots[index]
        if type(expected_slot) is not dict:
            _raise(error)
        if delivery_ref != expected_slot["delivery_ref"] or update["surface"] != expected_slot["surface"]:
            _raise("delivery_target_mismatch")
        safe.append(update)
    return safe


def _ack_update(value: object, *, error: str, exact_order: bool = True) -> dict[str, object]:
    source = (
        _plain_dict_with_fields(value, _ACK_UPDATE_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _ACK_UPDATE_FIELDS, error)
    )
    return {
        "delivery_ref": _safe_identifier(source["delivery_ref"], prefix="runtime_delivery_", error=error, strict_numeric_suffix=True),
        "surface": _one_of(source["surface"], set(_DELIVERY_POLICY_SURFACES), error),
        "status": _one_of(source["status"], {"sent", "failed", "acknowledged"}, error),
        "ack_ref": _safe_identifier(source["ack_ref"], prefix="runtime_event_", error=error),
    }


def _ack_result(value: object, *, update: dict[str, object], error: str) -> dict[str, object]:
    if _contains_forbidden_material(value):
        _raise(error)
    source = _plain_dict_with_fields(value, _ACK_RESULT_FIELDS, error)
    delivery_ref = _safe_identifier(source["delivery_ref"], prefix="runtime_delivery_", error=error, strict_numeric_suffix=True)
    surface = _one_of(source["surface"], set(_DELIVERY_POLICY_SURFACES), error)
    if delivery_ref != update["delivery_ref"] or surface != update["surface"]:
        _raise(error)
    status = _one_of(source["status"], {"applied", "duplicate", "rejected"}, error)
    error_code = _runtime_error_code(source["error_code"], status=status, error=error)
    return {
        "status": status,
        "delivery_ref": delivery_ref,
        "surface": surface,
        "error_code": error_code,
        "side_effects": _empty_list(source["side_effects"], error),
    }


def _delivery_result(
    *,
    status: str,
    artifact_ref: str | None,
    delivery_refs: list[str],
    surface_state: dict[str, object],
    ack_updates: list[dict[str, object]],
    ack_results: list[dict[str, object]],
    counts: dict[str, int],
    delivery_digest: str,
    error_code: str | None,
) -> dict[str, object]:
    result = {
        "type": FLOWWEAVER_DELIVERY_ACTIVITY_RESULT_TYPE,
        "version": FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
        "phase": "phase32",
        "activity": _CONTROLLED_ACTIVITY_TYPE,
        "status": status,
        "artifact_ref": artifact_ref,
        "delivery_refs": list(delivery_refs),
        "surface_state": dict(surface_state),
        "ack_updates": [dict(item) for item in ack_updates],
        "ack_results": [dict(item) for item in ack_results],
        "counts": dict(counts),
        "delivery_digest": delivery_digest,
        "error_code": error_code,
        "retry_class": _retry_class_for_error(error_code),
        "side_effects": [],
    }
    return validate_flowweaver_delivery_activity_result(result)


def _validated_agent_result(value: object, *, error: str, exact_order: bool) -> dict[str, object]:
    if _contains_forbidden_material(value):
        _raise(error)
    try:
        result = validate_flowweaver_agent_execution_result(
            value if exact_order else _canonical_agent_result_for_temporal(value, error=error)
        )
    except ValueError:
        _raise(error)
    if result["status"] != "executed":
        _raise(error)
    return result


def _canonical_agent_result_for_temporal(value: object, *, error: str) -> dict[str, object]:
    source = _plain_dict_with_key_set(value, _AGENT_RESULT_FIELDS, error)
    counts = _plain_dict_with_key_set(source["counts"], _AGENT_RESULT_COUNT_FIELDS, error)
    return {
        "type": source["type"],
        "version": source["version"],
        "phase": source["phase"],
        "activity": source["activity"],
        "status": source["status"],
        "artifact_ref": source["artifact_ref"],
        "artifact_kind": source["artifact_kind"],
        "counts": {
            "executor_calls": counts["executor_calls"],
            "tool_calls": counts["tool_calls"],
            "output_items": counts["output_items"],
        },
        "output_digest": source["output_digest"],
        "error_code": source["error_code"],
        "retry_class": source["retry_class"],
        "side_effects": source["side_effects"],
    }


def _delivery_slots(value: object, *, artifact_ref: str, error: str, exact_order: bool) -> list[dict[str, object]]:
    if type(value) is not list or not value or len(value) > 16:
        _raise(error)
    safe: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value:
        source = (
            _plain_dict_with_fields(item, _DELIVERY_SLOT_FIELDS, error)
            if exact_order
            else _plain_dict_with_key_set(item, _DELIVERY_SLOT_FIELDS, error)
        )
        delivery_ref = _safe_identifier(source["delivery_ref"], prefix="runtime_delivery_", error=error, strict_numeric_suffix=True)
        if delivery_ref in seen:
            _raise(error)
        seen.add(delivery_ref)
        slot_artifact_ref = _safe_identifier(source["artifact_ref"], prefix="runtime_artifact_", error=error)
        if slot_artifact_ref != artifact_ref:
            _raise(error)
        safe.append(
            {
                "delivery_ref": delivery_ref,
                "surface": _one_of(source["surface"], set(_DELIVERY_POLICY_SURFACES), error),
                "artifact_ref": slot_artifact_ref,
                "required": _bool(source["required"], error),
            }
        )
    return safe


def _required_surfaces(slots: list[dict[str, object]]) -> list[str]:
    surfaces: list[str] = []
    for slot in slots:
        if slot["required"] is True and str(slot["surface"]) not in surfaces:
            surfaces.append(str(slot["surface"]))
    return surfaces


def _delivery_policy(enabled: bool) -> dict[str, object]:
    return {
        "enabled": enabled,
        "mode": _DELIVERY_POLICY_MODE,
        "ack_reconciliation": "runtime_control_surface_required",
        "surfaces": list(_DELIVERY_POLICY_SURFACES),
        "final_text_required": True,
        "rich_card_does_not_suppress_final_text": True,
        "side_effects": [],
    }


def _delivery_policy_enabled(value: object, *, error: str, exact_order: bool) -> bool:
    source = _delivery_policy_source(value, error=error, exact_order=exact_order)
    return _bool(source["enabled"], error)


def _exact_delivery_policy(value: object, *, enabled: bool, error: str, exact_order: bool) -> dict[str, object]:
    source = _delivery_policy_source(value, error=error, exact_order=exact_order)
    expected = _delivery_policy(enabled)
    if _bool(source["enabled"], error) is not enabled:
        _raise(error)
    _literal(source["mode"], _DELIVERY_POLICY_MODE, error)
    _literal(source["ack_reconciliation"], "runtime_control_surface_required", error)
    _exact_string_list(source["surfaces"], list(_DELIVERY_POLICY_SURFACES), error)
    _true(source["final_text_required"], error)
    _true(source["rich_card_does_not_suppress_final_text"], error)
    _empty_list(source["side_effects"], error)
    return copy.deepcopy(expected)


def _delivery_policy_source(value: object, *, error: str, exact_order: bool) -> dict[str, object]:
    fields = [
        "enabled",
        "mode",
        "ack_reconciliation",
        "surfaces",
        "final_text_required",
        "rich_card_does_not_suppress_final_text",
        "side_effects",
    ]
    return (
        _plain_dict_with_fields(value, fields, error)
        if exact_order
        else _plain_dict_with_key_set(value, fields, error)
    )


def _delivery_digest(
    *,
    transaction_id: str,
    intent_id: str,
    artifact_ref: str,
    delivery_refs: list[str],
    required_surfaces: list[str],
    enabled: bool,
) -> str:
    material = "|".join(
        (
            "phase32",
            transaction_id,
            intent_id,
            artifact_ref,
            ",".join(delivery_refs),
            ",".join(required_surfaces),
            "enabled" if enabled else "disabled",
        )
    )
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _surface_state(ack_updates: list[dict[str, object]]) -> dict[str, object]:
    state = _empty_surface_state()
    for update in ack_updates:
        if update["status"] == "failed":
            continue
        surface = update["surface"]
        if surface == "progress_card":
            state["progress_card_sent"] = True
        elif surface == "rich_card":
            state["rich_cards_sent"] = int(state["rich_cards_sent"]) + 1
        elif surface == "final_text":
            state["final_text_sent"] = True
        elif surface == "media":
            state["media_sent"] = int(state["media_sent"]) + 1
    return state


def _empty_surface_state() -> dict[str, object]:
    return {
        "progress_card_sent": False,
        "rich_cards_sent": 0,
        "final_text_sent": False,
        "media_sent": 0,
    }


def _empty_result_counts(delivery_calls: int) -> dict[str, int]:
    return {
        "delivery_calls": delivery_calls,
        "ack_updates": 0,
        "ack_applied": 0,
        "ack_duplicates": 0,
        "ack_rejected": 0,
    }


def _counts_from_ack_results(
    delivery_calls: int,
    ack_updates: list[dict[str, object]],
    ack_results: list[dict[str, object]],
) -> dict[str, int]:
    return {
        "delivery_calls": delivery_calls,
        "ack_updates": len(ack_updates),
        "ack_applied": sum(1 for item in ack_results if item["status"] == "applied"),
        "ack_duplicates": sum(1 for item in ack_results if item["status"] == "duplicate"),
        "ack_rejected": sum(1 for item in ack_results if item["status"] == "rejected"),
    }


def _empty_snapshot_counts(activities: int, artifacts: int) -> dict[str, int]:
    return {
        "activities": activities,
        "artifacts": artifacts,
        "deliveries": 0,
        "ack_updates": 0,
        "ack_applied": 0,
        "ack_duplicates": 0,
        "ack_rejected": 0,
    }


def _snapshot_counts_from_result(result: dict[str, object]) -> dict[str, int]:
    counts = result["counts"]
    if type(counts) is not dict:
        _raise("invalid_delivery_activity_snapshot")
    return {
        "activities": 1,
        "artifacts": 1 if result["artifact_ref"] is not None else 0,
        "deliveries": len(result["delivery_refs"]) if type(result["delivery_refs"]) is list else 0,
        "ack_updates": int(counts["ack_updates"]),
        "ack_applied": int(counts["ack_applied"]),
        "ack_duplicates": int(counts["ack_duplicates"]),
        "ack_rejected": int(counts["ack_rejected"]),
    }


def _surface_state_value(value: object, *, error: str, exact_order: bool = True) -> dict[str, object]:
    source = (
        _plain_dict_with_fields(value, _SURFACE_STATE_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _SURFACE_STATE_FIELDS, error)
    )
    return {
        "progress_card_sent": _bool(source["progress_card_sent"], error),
        "rich_cards_sent": _bounded_nonnegative_int(source["rich_cards_sent"], maximum=16, error=error),
        "final_text_sent": _bool(source["final_text_sent"], error),
        "media_sent": _bounded_nonnegative_int(source["media_sent"], maximum=16, error=error),
    }


def _result_counts(value: object, *, error: str, exact_order: bool = True) -> dict[str, int]:
    source = (
        _plain_dict_with_fields(value, _RESULT_COUNT_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _RESULT_COUNT_FIELDS, error)
    )
    return {
        "delivery_calls": _bounded_nonnegative_int(source["delivery_calls"], maximum=1, error=error),
        "ack_updates": _bounded_nonnegative_int(source["ack_updates"], maximum=16, error=error),
        "ack_applied": _bounded_nonnegative_int(source["ack_applied"], maximum=16, error=error),
        "ack_duplicates": _bounded_nonnegative_int(source["ack_duplicates"], maximum=16, error=error),
        "ack_rejected": _bounded_nonnegative_int(source["ack_rejected"], maximum=16, error=error),
    }


def _snapshot_counts(value: object, *, error: str, exact_order: bool = True) -> dict[str, int]:
    source = (
        _plain_dict_with_fields(value, _SNAPSHOT_COUNT_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _SNAPSHOT_COUNT_FIELDS, error)
    )
    return {
        "activities": _bounded_nonnegative_int(source["activities"], maximum=1, error=error),
        "artifacts": _bounded_nonnegative_int(source["artifacts"], maximum=1, error=error),
        "deliveries": _bounded_nonnegative_int(source["deliveries"], maximum=16, error=error),
        "ack_updates": _bounded_nonnegative_int(source["ack_updates"], maximum=16, error=error),
        "ack_applied": _bounded_nonnegative_int(source["ack_applied"], maximum=16, error=error),
        "ack_duplicates": _bounded_nonnegative_int(source["ack_duplicates"], maximum=16, error=error),
        "ack_rejected": _bounded_nonnegative_int(source["ack_rejected"], maximum=16, error=error),
    }


def _ack_updates_for_validation(value: object, *, error: str, exact_order: bool = True) -> list[dict[str, object]]:
    if type(value) is not list or len(value) > 16:
        _raise(error)
    return [_ack_update(item, error=error, exact_order=exact_order) for item in value]


def _ack_results_for_validation(value: object, *, error: str, exact_order: bool = True) -> list[dict[str, object]]:
    if type(value) is not list or len(value) > 16:
        _raise(error)
    safe: list[dict[str, object]] = []
    for item in value:
        source = (
            _plain_dict_with_fields(item, _ACK_RESULT_FIELDS, error)
            if exact_order
            else _plain_dict_with_key_set(item, _ACK_RESULT_FIELDS, error)
        )
        status = _one_of(source["status"], {"applied", "duplicate", "rejected"}, error)
        safe.append(
            {
                "status": status,
                "delivery_ref": _safe_identifier(source["delivery_ref"], prefix="runtime_delivery_", error=error, strict_numeric_suffix=True),
                "surface": _one_of(source["surface"], set(_DELIVERY_POLICY_SURFACES), error),
                "error_code": _runtime_error_code(source["error_code"], status=status, error=error),
                "side_effects": _empty_list(source["side_effects"], error),
            }
        )
    return safe


def _runtime_error_code(value: object, *, status: str, error: str) -> str | None:
    if status in {"applied", "duplicate"}:
        return _none(value, error)
    code = _safe_error_code(value, fallback=None)
    if code not in {"runtime_reconciliation_failed", "runtime_query_failed"}:
        _raise(error)
    return code


def _result_error_code(value: object, *, status: str, error: str) -> str | None:
    if status == "delivered":
        return _none(value, error)
    code = _safe_error_code(value, fallback=None)
    if code is None:
        _raise(error)
    return code


def _snapshot_error_code(value: object, *, error: str) -> str | None:
    if value is None:
        return None
    code = _safe_error_code(value, fallback=None)
    if code is None:
        _raise(error)
    return code


def _retry_class(value: object, *, error_code: str | None, error: str) -> str:
    expected = _retry_class_for_error(error_code)
    return _literal(value, expected, error)


def _retry_class_for_error(error_code: str | None) -> str:
    if error_code is None:
        return "none"
    if error_code in _TRANSIENT_ERRORS:
        return "transient"
    return "non_retryable"


def _pre_delivery_error_code(value: str) -> str:
    if value in {"invalid_agent_execution_result", "invalid_delivery_slot", "unsafe_material"}:
        return value
    return "invalid_delivery_activity_request"


def _surface_output_error_code(value: str) -> str:
    if value in {"uninitialized_ack_target", "delivery_target_mismatch"}:
        return value
    if value == "unsafe_runtime_output":
        return value
    return "invalid_ack_update"


def _safe_error_code(value: object, *, fallback: str | None) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        return fallback
    return value if value in _SAFE_ERROR_CODES else fallback


def _intent_statuses(value: object, *, error: str) -> dict[str, str]:
    if type(value) is not dict:
        _raise(error)
    safe: dict[str, str] = {}
    for key, status in value.items():
        safe[_safe_identifier(key, prefix="runtime_intent_", error=error)] = _one_of(
            status,
            {"running", "delivered", "partially_delivered", "disabled", "rejected", "timed_out", "cancelled"},
            error,
        )
    return dict(sorted(safe.items()))


def _activity_sequence(value: object, *, error: str, exact_order: bool = True) -> list[dict[str, object]]:
    if type(value) is not list or len(value) > 1:
        _raise(error)
    safe: list[dict[str, object]] = []
    for item in value:
        source = (
            _plain_dict_with_fields(item, ["name", "status", "error_code", "side_effects"], error)
            if exact_order
            else _plain_dict_with_key_set(item, ["name", "status", "error_code", "side_effects"], error)
        )
        name = _literal(source["name"], _CONTROLLED_ACTIVITY_TYPE, error)
        safe.append(
            {
                "name": name,
                "status": _safe_activity_status(name, source["status"]),
                "error_code": _safe_error_code(source["error_code"], fallback=None),
                "side_effects": _empty_list(source["side_effects"], error),
            }
        )
    return safe


def _safe_activity_status(name: str, status: object) -> str:
    _literal(name, _CONTROLLED_ACTIVITY_TYPE, "invalid_delivery_activity_snapshot")
    return _one_of(status, {"delivered", "partially_delivered", "disabled", "rejected", "timed_out", "cancelled"}, "invalid_delivery_activity_snapshot")


def _validate_error_report(value: dict[str, object], *, error: str) -> dict[str, object]:
    source = _plain_dict_with_fields(value, _ERROR_REPORT_FIELDS, error)
    return {
        "type": _literal(source["type"], FLOWWEAVER_DELIVERY_ACTIVITY_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_DELIVERY_ACTIVITY_VERSION, error),
        "phase": _literal(source["phase"], "phase32", error),
        "ok": _false(source["ok"], error),
        "operation": _literal(source["operation"], _REPORT_OPERATION, error),
        "error_code": _one_of(
            source["error_code"],
            {"invalid_phase31_agent_execution_activity_report", "invalid_controlled_delivery_result"},
            error,
        ),
        "side_effects": _empty_list(source["side_effects"], error),
    }


def _error_report(error_code: str) -> dict[str, object]:
    return {
        "type": FLOWWEAVER_DELIVERY_ACTIVITY_REPORT_TYPE,
        "version": FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
        "phase": "phase32",
        "ok": False,
        "operation": _REPORT_OPERATION,
        "error_code": error_code,
        "side_effects": [],
    }


def _checks(value: object, *, error: str) -> dict[str, bool]:
    source = _plain_dict_with_fields(value, _CHECKS, error)
    safe: dict[str, bool] = {}
    for key in _CHECKS:
        if source[key] is not True:
            _raise(error)
        safe[key] = True
    return safe


def _has_runtime_reconciler(value: object) -> bool:
    method = getattr(value, "reconcile_delivery_ack", None)
    return callable(method)


def _plain_dict_with_fields(value: object, fields: list[str], error: str) -> dict[str, object]:
    if type(value) is not dict or not _keys_match_exactly(value, fields):
        _raise(error)
    return value


def _plain_dict_with_key_set(value: object, fields: list[str], error: str) -> dict[str, object]:
    if type(value) is not dict or len(value) != len(fields):
        _raise(error)
    keys: set[str] = set()
    for key in value.keys():
        if type(key) is not str:
            _raise(error)
        keys.add(key)
    if keys != set(fields):
        _raise(error)
    return value


def _keys_match_exactly(value: dict[object, object], fields: list[str]) -> bool:
    if len(value) != len(fields):
        return False
    keys: list[str] = []
    for key in value.keys():
        if type(key) is not str:
            return False
        keys.append(key)
    return keys == fields


def _literal(value: object, expected: str, error: str) -> str:
    if type(value) is not str or value != expected:
        _raise(error)
    return value


def _one_of(value: object, allowed: set[str], error: str) -> str:
    if type(value) is not str or value not in allowed:
        _raise(error)
    return value


def _true(value: object, error: str) -> bool:
    if value is not True:
        _raise(error)
    return True


def _false(value: object, error: str) -> bool:
    if value is not False:
        _raise(error)
    return False


def _bool(value: object, error: str) -> bool:
    if value is True:
        return True
    if value is False:
        return False
    _raise(error)


def _none(value: object, error: str) -> None:
    if value is not None:
        _raise(error)
    return None


def _empty_list(value: object, error: str) -> list[object]:
    if type(value) is not list or value:
        _raise(error)
    return []


def _safe_identifier(value: object, *, prefix: str, error: str, strict_numeric_suffix: bool = False) -> str:
    if type(value) is not str or not value.startswith(prefix):
        _raise(error)
    suffix = value.removeprefix(prefix)
    if not suffix or len(value) > 96:
        _raise(error)
    if strict_numeric_suffix:
        if not suffix.isdigit() or (len(suffix) > 1 and suffix.startswith("0")):
            _raise(error)
    elif any(not (character.islower() or character.isdigit() or character == "_") for character in suffix):
        _raise(error)
    for marker in ("oc_", "ou_", "om_", "private", "platform", "callback", "credential", "secret"):
        if marker in suffix:
            _raise(error)
    return value


def _optional_safe_identifier(value: object, *, prefix: str, error: str) -> str | None:
    if value is None:
        return None
    return _safe_identifier(value, prefix=prefix, error=error)


def _safe_identifier_list(
    value: object,
    *,
    prefix: str,
    error: str,
    strict_numeric_suffix: bool = False,
) -> list[str]:
    if type(value) is not list:
        _raise(error)
    return [
        _safe_identifier(item, prefix=prefix, error=error, strict_numeric_suffix=strict_numeric_suffix)
        for item in value
    ]


def _exact_string_list(value: object, expected: list[str], error: str) -> list[str]:
    if type(value) is not list or len(value) != len(expected):
        _raise(error)
    safe: list[str] = []
    for item, expected_item in zip(value, expected, strict=True):
        safe.append(_literal(item, expected_item, error))
    return safe


def _bounded_nonnegative_int(value: object, *, maximum: int, error: str) -> int:
    if type(value) is not int or value < 0 or value > maximum:
        _raise(error)
    return value


def _digest(value: object, *, error: str) -> str:
    if type(value) is not str or not value.startswith("sha256:"):
        _raise(error)
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        _raise(error)
    return value


def _assert_exact(value: object, expected: object, error: str) -> None:
    if type(expected) is dict:
        if type(value) is not dict or not _keys_match_exactly(value, list(expected)):
            _raise(error)
        for key, expected_item in expected.items():
            _assert_exact(value[key], expected_item, error)
        return
    if type(expected) is list:
        if type(value) is not list or len(value) != len(expected):
            _raise(error)
        for item, expected_item in zip(value, expected, strict=True):
            _assert_exact(item, expected_item, error)
        return
    if type(expected) is str:
        _literal(value, expected, error)
        return
    if type(expected) is bool:
        if value is not expected:
            _raise(error)
        return
    if expected is None:
        _none(value, error)
        return
    if value != expected:
        _raise(error)


def _contains_forbidden_material(value: object) -> bool:
    return _contains_forbidden_material_inner(value, seen=set(), depth=0)


def _contains_forbidden_material_inner(value: object, *, seen: set[int], depth: int) -> bool:
    if depth > _MAX_PLAIN_TREE_DEPTH:
        return True
    if type(value) is str:
        lowered = value.lower()
        return any(marker in lowered for marker in _RAW_VALUE_MARKERS)
    if type(value) in (bool, int) or value is None:
        return False
    if type(value) is list:
        marker = id(value)
        if marker in seen:
            return True
        seen.add(marker)
        try:
            return any(_contains_forbidden_material_inner(item, seen=seen, depth=depth + 1) for item in value)
        finally:
            seen.remove(marker)
    if type(value) is dict:
        marker = id(value)
        if marker in seen:
            return True
        seen.add(marker)
        try:
            for key, item in value.items():
                if type(key) is not str:
                    return True
                if _contains_forbidden_material_inner(key, seen=seen, depth=depth + 1):
                    return True
                if _contains_forbidden_material_inner(item, seen=seen, depth=depth + 1):
                    return True
            return False
        finally:
            seen.remove(marker)
    return True


def _raise(error: str) -> None:
    raise ValueError(error)
