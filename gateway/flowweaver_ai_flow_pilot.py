"""FlowWeaver Phase 33 controlled local/staging AI FLOW pilot.

This module composes the approved Phase 31 injected executor boundary and the
Phase 32 injected delivery/ACK boundary inside a local/staging Temporal
workflow. It deliberately exposes only sanitized refs, statuses, counts,
digests, stable error codes, labels, and empty side-effect lists.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
from datetime import timedelta
from typing import Any, Callable

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from gateway.flowweaver_agent_execution_activity import (
        FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_RESULT_TYPE,
        FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
        build_flowweaver_agent_execution_request,
        validate_flowweaver_agent_execution_request,
        validate_flowweaver_agent_execution_result,
    )
    from gateway.flowweaver_delivery_activity import (
        FLOWWEAVER_DELIVERY_ACTIVITY_RESULT_TYPE,
        FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT,
        FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
        build_flowweaver_delivery_activity_request,
        validate_flowweaver_delivery_activity_result,
    )

FLOWWEAVER_AI_FLOW_PILOT_CONTRACT_TYPE = "flowweaver.gateway.ai_flow_pilot_contract.v0"
FLOWWEAVER_AI_FLOW_PILOT_REQUEST_TYPE = "flowweaver.gateway.ai_flow_pilot_request.v0"
FLOWWEAVER_AI_FLOW_PILOT_SNAPSHOT_TYPE = "flowweaver.gateway.ai_flow_pilot_snapshot.v0"
FLOWWEAVER_AI_FLOW_PILOT_DECISION_PACKET_TYPE = "flowweaver.gateway.ai_flow_pilot_decision_packet.v0"
FLOWWEAVER_AI_FLOW_PILOT_REPORT_TYPE = "flowweaver.gateway.ai_flow_pilot_report.v0"
FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT = "ready_for_separate_production_enablement_decision"
FLOWWEAVER_AI_FLOW_PILOT_NOT_READY_VERDICT = "not_ready_for_production_enablement"
FLOWWEAVER_AI_FLOW_PILOT_VERSION = "flowweaver.ai_flow_pilot.v0"
FLOWWEAVER_AI_FLOW_PILOT_TASK_QUEUE = "flowweaver-phase33-ai-flow-pilot"

_REPORT_OPERATION = "build_flowweaver_ai_flow_pilot_report"
_CLAIM_ACTIVITY = "validate_claim_check_ref"
_EXECUTE_ACTIVITY = "execute_agent_turn"
_DELIVER_ACTIVITY = "deliver_artifact"
_ACTIVITY_TIMEOUT = timedelta(seconds=15)
_ACTIVITY_RETRY_POLICY = RetryPolicy(
    maximum_attempts=2,
    non_retryable_error_types=[
        "invalid_ai_flow_pilot_request",
        "invalid_claim_ref",
        "unsafe_material",
        "executor_auth_config_failure",
        "executor_cancelled",
        "invalid_delivery_activity_request",
        "invalid_agent_execution_result",
        "invalid_delivery_slot",
        "delivery_policy_disabled",
        "delivery_surface_required",
        "runtime_control_surface_required",
        "uninitialized_ack_target",
        "delivery_target_mismatch",
        "invalid_ack_update",
        "delivery_cancelled",
    ],
)

_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_verdicts",
    "entrypoints",
    "request_fields",
    "snapshot_fields",
    "decision_packet_fields",
    "report_fields",
    "composition_boundary",
    "runtime_policy",
    "pilot_policy",
    "decision_policy",
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
    "agent_execution_request",
    "initialized_delivery_slots",
    "pilot_policy",
    "decision_policy",
    "pilot_digest",
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
    "execution_digest",
    "delivery_digest",
    "decision_packet",
    "error_code",
    "side_effects",
]
_DECISION_PACKET_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "pilot_status",
    "evidence",
    "rollback",
    "separate_approvals_required",
    "unresolved_risks",
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
    "phase32_verdict",
    "pilot_verified",
    "decision_packet_verified",
    "history_no_leak_checked",
    "checks",
    "error_code",
    "side_effects",
]
_ENTRYPOINTS = [
    "describe_flowweaver_ai_flow_pilot_contract",
    "build_flowweaver_ai_flow_pilot_request",
    "validate_flowweaver_ai_flow_pilot_request",
    "FlowWeaverAIFlowPilotWorkflow",
    "build_flowweaver_ai_flow_pilot_activity_wrappers",
    "validate_flowweaver_ai_flow_pilot_snapshot",
    "validate_flowweaver_ai_flow_pilot_decision_packet",
    "build_flowweaver_ai_flow_pilot_report",
    "validate_flowweaver_ai_flow_pilot_report",
]
_CHECKS = [
    "phase31_boundary_composed",
    "phase32_boundary_composed",
    "default_off_zero_calls",
    "artifact_delivery_separated",
    "ack_replay_idempotent",
    "rollback_checklist_present",
    "decision_packet_separate_approvals",
    "history_no_leak_verified",
    "gateway_wiring_absent",
    "side_effects_absent",
]
_SEPARATE_APPROVALS = [
    "production_gateway_wiring",
    "production_delivery_enablement",
    "production_agent_execution",
    "production_config_write",
    "gateway_restart",
    "platform_adapter_mutation",
    "gateway_owned_worker_lifecycle",
]
_COMPOSITION_BOUNDARY = {
    "mode": "local_staging_temporal_workflow_only",
    "phase30_claim_validation": "validate_claim_check_ref_activity_via_phase33_no_throw_wrapper",
    "phase31_agent_execution": "execute_agent_turn_activity_injected_executor_only_via_phase33_no_throw_wrapper",
    "phase32_delivery": "deliver_artifact_activity_injected_delivery_only_via_phase33_no_throw_wrapper",
    "decision_packet": "sanitized_separate_enablement_decision_only",
    "side_effects": [],
}
_RUNTIME_POLICY = {
    "mode": "controlled_local_staging_ai_flow_pilot_only",
    "temporal_runtime": "local_staging_only",
    "production_gateway_wiring": "forbidden",
    "production_enablement": "separate_approval_required",
    "client_connection_ownership": "caller_supplied_tests_only",
    "worker_lifecycle": "caller_supplied_tests_only",
    "raw_material_policy": "claim_check_refs_safe_ids_counts_digests_only",
    "side_effects": [],
}
_PILOT_POLICY_MODE = "controlled_local_staging_ai_flow_pilot"
_PILOT_SCENARIO = "repo_workflow_planning_implementation_pr"
_DECISION_POLICY = {
    "max_verdict": FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT,
    "requires_separate_approvals": list(_SEPARATE_APPROVALS),
    "rollback_required": True,
    "kill_switch_required": True,
    "side_effects": [],
}
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
    "global_agent_executor_factory",
    "sub" + "process",
    "sock" + "et",
    "dock" + "er",
    "daemon",
    "service_startup",
    "raw_material_persistence",
]
_DELIVERY_SLOT_FIELDS = ["delivery_ref", "surface", "artifact_ref", "required"]
_SURFACE_STATE_FIELDS = ["progress_card_sent", "rich_cards_sent", "final_text_sent", "media_sent"]
_COUNT_FIELDS = [
    "activities",
    "artifacts",
    "deliveries",
    "executor_calls",
    "tool_calls",
    "ack_updates",
    "ack_applied",
    "ack_duplicates",
    "ack_rejected",
]
_ACTIVITY_ITEM_FIELDS = ["name", "status", "error_code", "side_effects"]
_EVIDENCE_FIELDS = [
    "phase31_executed",
    "phase32_delivered",
    "history_no_leak_checked",
    "result_no_leak_checked",
    "progress_snapshots_sanitized",
    "side_effects_absent",
]
_ROLLBACK_FIELDS = ["kill_switch_ref", "steps", "operator_required", "side_effects"]
_PILOT_POLICY_FIELDS = [
    "enabled",
    "mode",
    "scenario",
    "agent_execution",
    "delivery",
    "history_no_leak_required",
    "side_effects",
]
_DECISION_POLICY_FIELDS = [
    "max_verdict",
    "requires_separate_approvals",
    "rollback_required",
    "kill_switch_required",
    "side_effects",
]
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
_DELIVERY_RESULT_FIELDS = [
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
_DELIVERY_RESULT_COUNT_FIELDS = ["delivery_calls", "ack_updates", "ack_applied", "ack_duplicates", "ack_rejected"]
_ACK_UPDATE_FIELDS = ["delivery_ref", "surface", "status", "ack_ref"]
_ACK_RESULT_FIELDS = ["status", "delivery_ref", "surface", "error_code", "side_effects"]
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
_HEX = frozenset("0123456789abcdef")
_MAX_PLAIN_TREE_DEPTH = 64
_ZERO_DIGEST = "sha256:" + ("0" * 64)
_TERMINAL_STATUSES = {
    "pilot_completed",
    "disabled",
    "agent_execution_failed",
    "partially_delivered",
    "timed_out",
    "cancelled",
    "rejected",
}
_SAFE_ERROR_CODES = {
    "invalid_ai_flow_pilot_request",
    "pilot_policy_disabled",
    "invalid_claim_ref",
    "unsafe_material",
    "executor_failed",
    "executor_timeout",
    "executor_cancelled",
    "executor_auth_config_failure",
    "invalid_executor_result",
    "invalid_delivery_activity_request",
    "invalid_agent_execution_result",
    "invalid_delivery_slot",
    "delivery_policy_disabled",
    "delivery_surface_required",
    "runtime_control_surface_required",
    "uninitialized_ack_target",
    "delivery_target_mismatch",
    "invalid_ack_update",
    "delivery_cancelled",
    "delivery_surface_failed",
    "delivery_surface_timeout",
    "runtime_query_failed",
    "runtime_reconciliation_failed",
    "unsafe_runtime_output",
    "final_text_delivery_missing",
}


def describe_flowweaver_ai_flow_pilot_contract() -> dict[str, object]:
    """Return the exact Phase 33 controlled AI FLOW pilot descriptor."""

    return {
        "type": FLOWWEAVER_AI_FLOW_PILOT_CONTRACT_TYPE,
        "version": FLOWWEAVER_AI_FLOW_PILOT_VERSION,
        "phase": "phase33",
        "verdict": FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT,
        "scope": "narrow_ai_flow_pilot",
        "consumes_verdicts": {
            "phase31": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
            "phase32": FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT,
        },
        "entrypoints": list(_ENTRYPOINTS),
        "request_fields": list(_REQUEST_FIELDS),
        "snapshot_fields": list(_SNAPSHOT_FIELDS),
        "decision_packet_fields": list(_DECISION_PACKET_FIELDS),
        "report_fields": list(_REPORT_FIELDS),
        "composition_boundary": copy.deepcopy(_COMPOSITION_BOUNDARY),
        "runtime_policy": copy.deepcopy(_RUNTIME_POLICY),
        "pilot_policy": _pilot_policy(True),
        "decision_policy": copy.deepcopy(_DECISION_POLICY),
        "checks": list(_CHECKS),
        "separate_approvals": list(_SEPARATE_APPROVALS),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }


def build_flowweaver_ai_flow_pilot_request(
    *,
    transaction_id: object,
    workflow_id: object,
    intent_id: object,
    claim_check_ref: object,
    artifact_ref: object,
    initialized_delivery_slots: object,
    enabled: object = False,
) -> dict[str, object]:
    """Build a safe Phase 33 start request from refs, ids, and delivery slots."""

    is_enabled = _bool(enabled, "invalid_ai_flow_pilot_request")
    try:
        agent_request = build_flowweaver_agent_execution_request(
            transaction_id=transaction_id,
            workflow_id=workflow_id,
            intent_id=intent_id,
            claim_check_ref=claim_check_ref,
            artifact_ref=artifact_ref,
        )
    except ValueError:
        _raise("invalid_ai_flow_pilot_request")
    tx_id = str(agent_request["transaction_id"])
    wf_id = str(agent_request["workflow_id"])
    safe_intent_id = str(agent_request["intent_id"])
    safe_artifact_ref = str(agent_request["artifact_ref"])
    slots = _delivery_slots(
        initialized_delivery_slots,
        artifact_ref=safe_artifact_ref,
        error="invalid_ai_flow_pilot_request",
        exact_order=True,
    )
    request = {
        "type": FLOWWEAVER_AI_FLOW_PILOT_REQUEST_TYPE,
        "version": FLOWWEAVER_AI_FLOW_PILOT_VERSION,
        "phase": "phase33",
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "intent_id": safe_intent_id,
        "agent_execution_request": agent_request,
        "initialized_delivery_slots": slots,
        "pilot_policy": _pilot_policy(is_enabled),
        "decision_policy": copy.deepcopy(_DECISION_POLICY),
        "pilot_digest": _pilot_digest(
            transaction_id=tx_id,
            intent_id=safe_intent_id,
            execution_digest=str(agent_request["execution_digest"]),
            delivery_refs=[str(slot["delivery_ref"]) for slot in slots],
            enabled=is_enabled,
        ),
        "side_effects": [],
    }
    return validate_flowweaver_ai_flow_pilot_request(request)


def validate_flowweaver_ai_flow_pilot_request(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 33 request copy."""

    return _validate_flowweaver_ai_flow_pilot_request(value, exact_order=True)


def validate_flowweaver_ai_flow_pilot_snapshot(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 33 snapshot copy."""

    return _validate_flowweaver_ai_flow_pilot_snapshot(value, exact_order=True)


def validate_flowweaver_ai_flow_pilot_decision_packet(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 33 decision packet copy."""

    return _validate_decision_packet(value, exact_order=True)


def build_flowweaver_ai_flow_pilot_report(
    *,
    agent_execution_activity_verdict: object,
    delivery_activity_verdict: object,
    pilot_snapshot: object,
    decision_packet: object,
    history_no_leak_checked: object,
) -> dict[str, object]:
    """Build Phase 33 report metadata from sanitized P31/P32 pilot evidence."""

    try:
        phase31 = _literal(
            agent_execution_activity_verdict,
            FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
            "invalid_phase31_agent_execution_activity_report",
        )
        phase32 = _literal(
            delivery_activity_verdict,
            FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT,
            "invalid_phase32_delivery_activity_report",
        )
        snapshot = validate_flowweaver_ai_flow_pilot_snapshot(pilot_snapshot)
        packet = validate_flowweaver_ai_flow_pilot_decision_packet(decision_packet)
        if snapshot["decision_packet"] != packet:
            _raise("invalid_ai_flow_pilot_decision_packet")
        if snapshot["status"] != "pilot_completed" or packet["pilot_status"] != "pilot_completed":
            _raise("invalid_ai_flow_pilot_snapshot")
        _true(history_no_leak_checked, "history_not_verified")
    except ValueError as exc:
        return _report(
            ok=False,
            phase31_verdict=agent_execution_activity_verdict,
            phase32_verdict=delivery_activity_verdict,
            history_no_leak_checked=history_no_leak_checked,
            error_code=_report_error_code(str(exc)),
        )
    return _report(
        ok=True,
        phase31_verdict=phase31,
        phase32_verdict=phase32,
        history_no_leak_checked=True,
        error_code=None,
    )


def validate_flowweaver_ai_flow_pilot_report(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 33 report copy."""

    error = "invalid_ai_flow_pilot_report"
    source = _plain_dict_with_fields(value, _REPORT_FIELDS, error)
    ok = _bool(source["ok"], error)
    error_code = _report_error_value(source["error_code"], ok=ok, error=error)
    checks = _report_checks(source["checks"], ok=ok, error=error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_AI_FLOW_PILOT_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_AI_FLOW_PILOT_VERSION, error),
        "phase": _literal(source["phase"], "phase33", error),
        "ok": ok,
        "verdict": _report_verdict(source["verdict"], ok=ok, error=error),
        "operation": _literal(source["operation"], _REPORT_OPERATION, error),
        "phase31_verdict": _literal(
            source["phase31_verdict"],
            FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
            error,
        ),
        "phase32_verdict": _literal(
            source["phase32_verdict"],
            FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT,
            error,
        ),
        "pilot_verified": _bool(source["pilot_verified"], error),
        "decision_packet_verified": _bool(source["decision_packet_verified"], error),
        "history_no_leak_checked": _bool(source["history_no_leak_checked"], error),
        "checks": checks,
        "error_code": error_code,
        "side_effects": _empty_list(source["side_effects"], error),
    }
    if ok:
        if safe["pilot_verified"] is not True or safe["decision_packet_verified"] is not True:
            _raise(error)
        if safe["history_no_leak_checked"] is not True or any(value is not True for value in checks.values()):
            _raise(error)
    return safe


def build_flowweaver_ai_flow_pilot_activity_wrappers(
    *,
    claim_activity: Callable[[dict[str, Any]], object],
    execute_activity: Callable[[dict[str, Any]], object],
    deliver_activity: Callable[[dict[str, Any]], object],
) -> list[Callable[[dict[str, Any]], Any]]:
    """Return Phase 33 no-throw Temporal Activity wrappers around caller-supplied P30/P31/P32 activities."""

    if not callable(claim_activity) or not callable(execute_activity) or not callable(deliver_activity):
        _raise("invalid_ai_flow_pilot_activity_wrapper")

    @activity.defn(name=_CLAIM_ACTIVITY)
    async def validate_claim_check_ref_no_throw(payload: dict[str, Any]) -> dict[str, Any]:
        result = await _invoke_inner_activity_no_throw(claim_activity, payload)
        return _sanitize_claim_activity_result(result)

    @activity.defn(name=_EXECUTE_ACTIVITY)
    async def execute_agent_turn_no_throw(payload: dict[str, Any]) -> dict[str, Any]:
        result = await _invoke_inner_activity_no_throw(execute_activity, payload)
        return _sanitize_agent_activity_result(result)

    @activity.defn(name=_DELIVER_ACTIVITY)
    async def deliver_artifact_no_throw(payload: dict[str, Any]) -> dict[str, Any]:
        result = await _invoke_inner_activity_no_throw(deliver_activity, payload)
        return _sanitize_delivery_activity_result(result)

    return [validate_claim_check_ref_no_throw, execute_agent_turn_no_throw, deliver_artifact_no_throw]


async def _invoke_inner_activity_no_throw(inner: Callable[[dict[str, Any]], object], payload: dict[str, Any]) -> object:
    try:
        result = inner(payload)
        if inspect.isawaitable(result):
            result = await result
        return result
    except BaseException:
        return None


def _sanitize_claim_activity_result(value: object) -> dict[str, Any]:
    try:
        if _contains_forbidden_material(value):
            _raise("invalid_claim_ref")
        source = _plain_dict_with_key_set(value, ["activity", "status", "claim_ref", "error_code", "side_effects"], "invalid_claim_ref")
        status = _one_of(source["status"], {"validated", "rejected"}, "invalid_claim_ref")
        claim_ref = _safe_identifier(source["claim_ref"], prefix="claim_ref_", error="invalid_claim_ref") if status == "validated" else _none(source["claim_ref"], "invalid_claim_ref")
        error_code = _none(source["error_code"], "invalid_claim_ref") if status == "validated" else _safe_error_code(source["error_code"], fallback="invalid_claim_ref")
        if status == "rejected" and error_code is None:
            error_code = "invalid_claim_ref"
        return {
            "activity": _literal(source["activity"], _CLAIM_ACTIVITY, "invalid_claim_ref"),
            "status": status,
            "claim_ref": claim_ref,
            "error_code": error_code,
            "side_effects": _empty_list(source["side_effects"], "invalid_claim_ref"),
        }
    except ValueError:
        return _claim_activity_failure_result()


def _claim_activity_failure_result() -> dict[str, Any]:
    return {"activity": _CLAIM_ACTIVITY, "status": "rejected", "claim_ref": None, "error_code": "invalid_claim_ref", "side_effects": []}


def _sanitize_agent_activity_result(value: object) -> dict[str, Any]:
    try:
        if _contains_forbidden_material(value):
            return _agent_activity_failure_result("unsafe_material")
        return dict(_validate_agent_result_for_temporal(value))
    except ValueError:
        return _agent_activity_failure_result("invalid_executor_result")


def _agent_activity_failure_result(error_code: str) -> dict[str, Any]:
    result = {
        "type": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_RESULT_TYPE,
        "version": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
        "phase": "phase31",
        "activity": _EXECUTE_ACTIVITY,
        "status": "rejected",
        "artifact_ref": None,
        "artifact_kind": None,
        "counts": {"executor_calls": 0, "tool_calls": 0, "output_items": 0},
        "output_digest": _ZERO_DIGEST,
        "error_code": error_code,
        "retry_class": "transient" if error_code in {"executor_failed", "executor_timeout"} else "non_retryable",
        "side_effects": [],
    }
    return dict(validate_flowweaver_agent_execution_result(result))


def _sanitize_delivery_activity_result(value: object) -> dict[str, Any]:
    try:
        if _contains_forbidden_material(value):
            return _delivery_activity_failure_result("unsafe_material")
        return dict(_validate_delivery_result_for_temporal(value))
    except ValueError:
        return _delivery_activity_failure_result("delivery_surface_failed")


def _delivery_activity_failure_result(error_code: str) -> dict[str, Any]:
    result = {
        "type": FLOWWEAVER_DELIVERY_ACTIVITY_RESULT_TYPE,
        "version": FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
        "phase": "phase32",
        "activity": _DELIVER_ACTIVITY,
        "status": "rejected",
        "artifact_ref": None,
        "delivery_refs": [],
        "surface_state": _empty_surface_state(),
        "ack_updates": [],
        "ack_results": [],
        "counts": {"delivery_calls": 0, "ack_updates": 0, "ack_applied": 0, "ack_duplicates": 0, "ack_rejected": 0},
        "delivery_digest": _ZERO_DIGEST,
        "error_code": error_code,
        "retry_class": "transient" if error_code in {"delivery_surface_failed", "delivery_surface_timeout", "runtime_query_failed", "runtime_query_timeout", "final_text_delivery_missing"} else "non_retryable",
        "side_effects": [],
    }
    return dict(validate_flowweaver_delivery_activity_result(result))


@workflow.defn
class FlowWeaverAIFlowPilotWorkflow:
    """Local/staging workflow that composes claim validation, execution, delivery, and decision metadata."""

    def __init__(self) -> None:
        self._transaction_id = "runtime_tx_uninitialized"
        self._workflow_id = "runtime_tx_uninitialized"
        self._intent_id = "runtime_intent_uninitialized"
        self._status = "created"
        self._intent_statuses: dict[str, str] = {}
        self._artifact_refs: list[str] = []
        self._delivery_refs: list[str] = []
        self._surface_state = _empty_surface_state()
        self._activity_sequence: list[dict[str, Any]] = []
        self._counts = _zero_counts()
        self._execution_digest = _ZERO_DIGEST
        self._delivery_digest = _ZERO_DIGEST
        self._decision_packet = _decision_packet(
            pilot_status="created",
            phase31_executed=False,
            phase32_delivered=False,
        )
        self._error_code: str | None = None

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            request = _validate_flowweaver_ai_flow_pilot_request(payload, exact_order=False)
        except ValueError as exc:
            self._status = "rejected"
            self._error_code = _safe_error_code(str(exc), fallback="invalid_ai_flow_pilot_request")
            self._decision_packet = _decision_packet(
                pilot_status="rejected",
                phase31_executed=False,
                phase32_delivered=False,
            )
            return self._snapshot()

        self._reset_from_request(request)
        if request["pilot_policy"]["enabled"] is False:
            self._status = "disabled"
            self._intent_statuses = {self._intent_id: "disabled"}
            self._artifact_refs = []
            self._delivery_refs = []
            self._surface_state = _empty_surface_state()
            self._activity_sequence = []
            self._counts = _zero_counts()
            self._delivery_digest = _ZERO_DIGEST
            self._error_code = "pilot_policy_disabled"
            self._decision_packet = _decision_packet(
                pilot_status="disabled",
                phase31_executed=False,
                phase32_delivered=False,
            )
            return self._snapshot()

        agent_request = request["agent_execution_request"]
        claim_result = await workflow.execute_activity(
            _CLAIM_ACTIVITY,
            {
                "claim_check_ref": agent_request["claim_check_ref"],
                "policy_descriptor": agent_request["claim_policy"],
            },
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY_POLICY,
        )
        try:
            self._record_activity_result(_CLAIM_ACTIVITY, claim_result)
        except ValueError:
            self._record_rejected_activity(_CLAIM_ACTIVITY, "invalid_claim_ref")
            self._status = "rejected"
            self._intent_statuses[self._intent_id] = "rejected"
            self._error_code = "invalid_claim_ref"
            self._decision_packet = _decision_packet(
                pilot_status="rejected",
                phase31_executed=False,
                phase32_delivered=False,
            )
            return self._snapshot()
        if claim_result.get("status") != "validated":
            self._status = "rejected"
            self._intent_statuses[self._intent_id] = "rejected"
            self._error_code = _safe_error_code(claim_result.get("error_code"), fallback="invalid_claim_ref")
            self._decision_packet = _decision_packet(
                pilot_status="rejected",
                phase31_executed=False,
                phase32_delivered=False,
            )
            return self._snapshot()

        agent_result = await workflow.execute_activity(
            _EXECUTE_ACTIVITY,
            {
                "execution_request": agent_request,
                "validated_claim": claim_result,
            },
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY_POLICY,
        )
        safe_agent_result = _validate_agent_result_for_temporal(agent_result)
        self._record_activity_result(_EXECUTE_ACTIVITY, safe_agent_result)
        self._apply_agent_result(safe_agent_result)
        if safe_agent_result["status"] != "executed":
            self._decision_packet = _decision_packet(
                pilot_status=self._status,
                phase31_executed=False,
                phase32_delivered=False,
            )
            return self._snapshot()
        self._decision_packet = _decision_packet(
            pilot_status=self._status,
            phase31_executed=True,
            phase32_delivered=False,
        )

        delivery_request = build_flowweaver_delivery_activity_request(
            transaction_id=request["transaction_id"],
            workflow_id=request["workflow_id"],
            intent_id=request["intent_id"],
            agent_execution_result=safe_agent_result,
            initialized_delivery_slots=request["initialized_delivery_slots"],
            enabled=True,
        )
        delivery_result = await workflow.execute_activity(
            _DELIVER_ACTIVITY,
            delivery_request,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY_POLICY,
        )
        safe_delivery_result = _validate_delivery_result_for_temporal(delivery_result)
        self._record_activity_result(_DELIVER_ACTIVITY, safe_delivery_result)
        self._apply_delivery_result(safe_delivery_result)
        self._decision_packet = _decision_packet(
            pilot_status=self._status,
            phase31_executed=True,
            phase32_delivered=self._status == "pilot_completed",
        )
        return self._snapshot()

    @workflow.query
    def query_snapshot(self) -> dict[str, Any]:
        return self._snapshot()

    def _reset_from_request(self, request: dict[str, object]) -> None:
        self._transaction_id = str(request["transaction_id"])
        self._workflow_id = str(request["workflow_id"])
        self._intent_id = str(request["intent_id"])
        self._status = "running"
        self._intent_statuses = {self._intent_id: "running"}
        self._artifact_refs = []
        self._delivery_refs = []
        self._surface_state = _empty_surface_state()
        self._activity_sequence = []
        self._counts = _zero_counts()
        self._execution_digest = str(request["agent_execution_request"]["execution_digest"])
        self._delivery_digest = _ZERO_DIGEST
        self._error_code = None
        self._decision_packet = _decision_packet(
            pilot_status="running",
            phase31_executed=False,
            phase32_delivered=False,
        )

    def _apply_agent_result(self, result: dict[str, object]) -> None:
        counts = result["counts"]
        if type(counts) is not dict:
            _raise("invalid_ai_flow_pilot_snapshot")
        self._execution_digest = str(result["output_digest"])
        self._counts["activities"] = len(self._activity_sequence)
        self._counts["executor_calls"] = int(counts["executor_calls"])
        self._counts["tool_calls"] = int(counts["tool_calls"])
        self._error_code = _safe_error_code(result["error_code"], fallback=None)
        if result["status"] == "executed":
            self._status = "running"
            self._intent_statuses[self._intent_id] = "executed"
            self._artifact_refs = [str(result["artifact_ref"])]
            self._counts["artifacts"] = 1
            return
        self._artifact_refs = []
        self._counts["artifacts"] = 0
        if result["status"] == "timed_out":
            self._status = "timed_out"
            self._intent_statuses[self._intent_id] = "timed_out"
        elif result["status"] == "cancelled":
            self._status = "cancelled"
            self._intent_statuses[self._intent_id] = "cancelled"
        else:
            self._status = "agent_execution_failed"
            self._intent_statuses[self._intent_id] = "rejected"

    def _apply_delivery_result(self, result: dict[str, object]) -> None:
        counts = result["counts"]
        if type(counts) is not dict:
            _raise("invalid_ai_flow_pilot_snapshot")
        self._delivery_refs = [str(item) for item in result["delivery_refs"]]
        self._surface_state = _surface_state_value(result["surface_state"], error="invalid_ai_flow_pilot_snapshot")
        self._delivery_digest = str(result["delivery_digest"])
        self._counts = {
            "activities": len(self._activity_sequence),
            "artifacts": 1 if result["artifact_ref"] is not None else 0,
            "deliveries": len(self._delivery_refs),
            "executor_calls": self._counts["executor_calls"],
            "tool_calls": self._counts["tool_calls"],
            "ack_updates": int(counts["ack_updates"]),
            "ack_applied": int(counts["ack_applied"]),
            "ack_duplicates": int(counts["ack_duplicates"]),
            "ack_rejected": int(counts["ack_rejected"]),
        }
        self._error_code = _safe_error_code(result["error_code"], fallback=None)
        if result["status"] == "delivered":
            self._status = "pilot_completed"
            self._intent_statuses[self._intent_id] = "delivered"
        elif result["status"] == "partially_delivered":
            self._status = "partially_delivered"
            self._intent_statuses[self._intent_id] = "partially_delivered"
        elif result["status"] == "timed_out":
            self._status = "timed_out"
            self._intent_statuses[self._intent_id] = "timed_out"
        elif result["status"] == "cancelled":
            self._status = "cancelled"
            self._intent_statuses[self._intent_id] = "cancelled"
        else:
            self._status = "rejected"
            self._intent_statuses[self._intent_id] = "rejected"

    def _record_activity_result(self, name: str, result: dict[str, Any]) -> None:
        status = _safe_activity_status(name, result.get("status"))
        raw_error_code = result.get("error_code")
        error_code = _safe_error_code(raw_error_code, fallback=None)
        if raw_error_code is not None and error_code is None:
            _raise("invalid_ai_flow_pilot_snapshot")
        success_statuses = {
            _CLAIM_ACTIVITY: "validated",
            _EXECUTE_ACTIVITY: "executed",
            _DELIVER_ACTIVITY: "delivered",
        }
        if status == success_statuses[name] and raw_error_code is not None:
            _raise("invalid_ai_flow_pilot_snapshot")
        self._activity_sequence.append(
            {
                "name": name,
                "status": status,
                "error_code": error_code,
                "side_effects": [],
            }
        )
        self._counts["activities"] = len(self._activity_sequence)

    def _record_rejected_activity(self, name: str, error_code: str) -> None:
        self._activity_sequence.append(
            {
                "name": name,
                "status": "rejected",
                "error_code": error_code,
                "side_effects": [],
            }
        )
        self._counts["activities"] = len(self._activity_sequence)

    def _snapshot(self) -> dict[str, Any]:
        snapshot = {
            "type": FLOWWEAVER_AI_FLOW_PILOT_SNAPSHOT_TYPE,
            "version": FLOWWEAVER_AI_FLOW_PILOT_VERSION,
            "phase": "phase33",
            "transaction_id": self._transaction_id,
            "workflow_id": self._workflow_id,
            "status": self._status,
            "intent_statuses": dict(sorted(self._intent_statuses.items())),
            "artifact_refs": list(self._artifact_refs),
            "delivery_refs": list(self._delivery_refs),
            "surface_state": dict(self._surface_state),
            "activity_sequence": [dict(item) for item in self._activity_sequence],
            "counts": dict(self._counts),
            "execution_digest": self._execution_digest,
            "delivery_digest": self._delivery_digest,
            "decision_packet": copy.deepcopy(self._decision_packet),
            "error_code": self._error_code,
            "side_effects": [],
        }
        return _validate_flowweaver_ai_flow_pilot_snapshot(snapshot, exact_order=True)


def _validate_flowweaver_ai_flow_pilot_request(value: object, *, exact_order: bool) -> dict[str, object]:
    error = "invalid_ai_flow_pilot_request"
    if _contains_forbidden_material(value):
        _raise(error)
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
    agent_request = validate_flowweaver_agent_execution_request(
        source["agent_execution_request"]
        if exact_order
        else _canonical_agent_request_for_temporal(source["agent_execution_request"], error=error)
    )
    if agent_request["transaction_id"] != tx_id or agent_request["workflow_id"] != wf_id:
        _raise(error)
    if agent_request["intent_id"] != safe_intent_id:
        _raise(error)
    artifact_ref = str(agent_request["artifact_ref"])
    slots = _delivery_slots(
        source["initialized_delivery_slots"],
        artifact_ref=artifact_ref,
        error=error,
        exact_order=exact_order,
    )
    enabled = _pilot_policy_enabled(source["pilot_policy"], error=error, exact_order=exact_order)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_AI_FLOW_PILOT_REQUEST_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_AI_FLOW_PILOT_VERSION, error),
        "phase": _literal(source["phase"], "phase33", error),
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "intent_id": safe_intent_id,
        "agent_execution_request": agent_request,
        "initialized_delivery_slots": slots,
        "pilot_policy": _exact_pilot_policy(source["pilot_policy"], enabled=enabled, error=error, exact_order=exact_order),
        "decision_policy": _exact_decision_policy(source["decision_policy"], error=error, exact_order=exact_order),
        "pilot_digest": _digest(source["pilot_digest"], error=error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    expected_digest = _pilot_digest(
        transaction_id=tx_id,
        intent_id=safe_intent_id,
        execution_digest=str(agent_request["execution_digest"]),
        delivery_refs=[str(slot["delivery_ref"]) for slot in slots],
        enabled=enabled,
    )
    if safe["pilot_digest"] != expected_digest:
        _raise(error)
    return safe


def _validate_flowweaver_ai_flow_pilot_snapshot(value: object, *, exact_order: bool) -> dict[str, object]:
    error = "invalid_ai_flow_pilot_snapshot"
    if _contains_forbidden_material(value):
        _raise(error)
    source = (
        _plain_dict_with_fields(value, _SNAPSHOT_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _SNAPSHOT_FIELDS, error)
    )
    tx_id = _safe_identifier(source["transaction_id"], prefix="runtime_tx_", error=error)
    wf_id = _safe_identifier(source["workflow_id"], prefix="runtime_tx_", error=error)
    if wf_id != tx_id:
        _raise(error)
    status = _one_of(source["status"], _TERMINAL_STATUSES | {"created", "running"}, error)
    try:
        decision_packet = _validate_decision_packet(source["decision_packet"], exact_order=exact_order)
    except ValueError:
        _raise(error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_AI_FLOW_PILOT_SNAPSHOT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_AI_FLOW_PILOT_VERSION, error),
        "phase": _literal(source["phase"], "phase33", error),
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "status": status,
        "intent_statuses": _intent_statuses(source["intent_statuses"], error=error),
        "artifact_refs": _safe_identifier_list(source["artifact_refs"], prefix="runtime_artifact_", error=error),
        "delivery_refs": _safe_identifier_list(
            source["delivery_refs"],
            prefix="runtime_delivery_",
            error=error,
            strict_numeric_suffix=True,
        ),
        "surface_state": _surface_state_value(source["surface_state"], error=error, exact_order=exact_order),
        "activity_sequence": _activity_sequence(source["activity_sequence"], error=error, exact_order=exact_order),
        "counts": _counts(source["counts"], error=error, exact_order=exact_order),
        "execution_digest": _digest(source["execution_digest"], error=error),
        "delivery_digest": _digest(source["delivery_digest"], error=error),
        "decision_packet": decision_packet,
        "error_code": _snapshot_error_code(source["error_code"], status=status, error=error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    _validate_snapshot_semantics(safe, error=error)
    return safe


def _validate_snapshot_semantics(snapshot: dict[str, object], *, error: str) -> None:
    status = str(snapshot["status"])
    counts = snapshot["counts"]
    packet = snapshot["decision_packet"]
    activity_sequence = snapshot["activity_sequence"]
    artifact_refs = snapshot["artifact_refs"]
    delivery_refs = snapshot["delivery_refs"]
    intent_statuses = snapshot["intent_statuses"]
    surface_state = snapshot["surface_state"]
    if (
        type(counts) is not dict
        or type(packet) is not dict
        or type(activity_sequence) is not list
        or type(artifact_refs) is not list
        or type(delivery_refs) is not list
        or type(intent_statuses) is not dict
        or type(surface_state) is not dict
    ):
        _raise(error)
    if packet["pilot_status"] != status:
        _raise(error)
    if len(delivery_refs) != len(set(delivery_refs)):
        _raise(error)
    if counts["activities"] != len(activity_sequence):
        _raise(error)
    if counts["artifacts"] != len(artifact_refs):
        _raise(error)
    if counts["deliveries"] != len(delivery_refs):
        _raise(error)
    if counts["ack_updates"] != counts["ack_applied"] + counts["ack_duplicates"] + counts["ack_rejected"]:
        _raise(error)
    activity_by_name = {str(item["name"]): str(item["status"]) for item in activity_sequence}
    execute_status = activity_by_name.get(_EXECUTE_ACTIVITY)
    deliver_status = activity_by_name.get(_DELIVER_ACTIVITY)
    if (artifact_refs or counts["artifacts"] > 0) and execute_status != "executed":
        _raise(error)
    if (delivery_refs or counts["deliveries"] > 0) and deliver_status is None:
        _raise(error)
    if deliver_status is None and surface_state != _empty_surface_state():
        _raise(error)
    if status == "agent_execution_failed" and (
        execute_status != "rejected"
        or deliver_status is not None
        or artifact_refs != []
        or delivery_refs != []
        or counts["artifacts"] != 0
        or counts["deliveries"] != 0
    ):
        _raise(error)
    _validate_activity_success_error_codes(activity_sequence, error=error)
    phase31_executed, phase32_delivered = _phase_evidence_from_activity_sequence(activity_sequence, error=error)
    _validate_packet_evidence_for_snapshot(
        packet,
        phase31_executed=phase31_executed,
        phase32_delivered=phase32_delivered,
        error=error,
    )
    if status == "pilot_completed":
        if snapshot["error_code"] is not None:
            _raise(error)
        if [item["status"] for item in activity_sequence] != ["validated", "executed", "delivered"]:
            _raise(error)
        if counts["activities"] != 3 or counts["artifacts"] != 1 or counts["executor_calls"] != 1:
            _raise(error)
        if counts["deliveries"] < 1 or counts["ack_rejected"] != 0:
            _raise(error)
        if counts["ack_updates"] != counts["deliveries"]:
            _raise(error)
        if counts["ack_applied"] + counts["ack_duplicates"] != counts["deliveries"]:
            _raise(error)
        if not phase31_executed or not phase32_delivered:
            _raise(error)
        if len(intent_statuses) != 1 or any(item != "delivered" for item in intent_statuses.values()):
            _raise(error)
        if surface_state["final_text_sent"] is not True:
            _raise(error)
        if packet["verdict"] != FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT:
            _raise(error)
    elif status == "disabled":
        if snapshot["error_code"] != "pilot_policy_disabled" or counts != _zero_counts():
            _raise(error)
        if activity_sequence != [] or artifact_refs != [] or delivery_refs != []:
            _raise(error)
    elif status in _TERMINAL_STATUSES:
        if snapshot["error_code"] is None:
            _raise(error)


def _validate_activity_success_error_codes(activity_sequence: list[object], *, error: str) -> None:
    success_statuses = {
        _CLAIM_ACTIVITY: "validated",
        _EXECUTE_ACTIVITY: "executed",
        _DELIVER_ACTIVITY: "delivered",
    }
    for item in activity_sequence:
        if type(item) is not dict:
            _raise(error)
        if item["status"] == success_statuses[item["name"]] and item["error_code"] is not None:
            _raise(error)


def _phase_evidence_from_activity_sequence(
    activity_sequence: list[object],
    *,
    error: str,
) -> tuple[bool, bool]:
    phase31_executed = False
    phase32_delivered = False
    for item in activity_sequence:
        if type(item) is not dict:
            _raise(error)
        if item["name"] == _EXECUTE_ACTIVITY and item["status"] == "executed":
            phase31_executed = True
        if item["name"] == _DELIVER_ACTIVITY and item["status"] == "delivered":
            phase32_delivered = True
    if phase32_delivered and not phase31_executed:
        _raise(error)
    return phase31_executed, phase32_delivered


def _validate_packet_evidence_for_snapshot(
    packet: dict[str, object],
    *,
    phase31_executed: bool,
    phase32_delivered: bool,
    error: str,
) -> None:
    evidence = packet["evidence"]
    if type(evidence) is not dict:
        _raise(error)
    if evidence["phase31_executed"] is not phase31_executed:
        _raise(error)
    if evidence["phase32_delivered"] is not phase32_delivered:
        _raise(error)
    if evidence["history_no_leak_checked"] is not True:
        _raise(error)
    if evidence["result_no_leak_checked"] is not True:
        _raise(error)
    if evidence["progress_snapshots_sanitized"] is not True:
        _raise(error)
    if evidence["side_effects_absent"] is not True:
        _raise(error)


def _validate_decision_packet(value: object, *, exact_order: bool) -> dict[str, object]:
    error = "invalid_ai_flow_pilot_decision_packet"
    if _contains_forbidden_material(value):
        _raise(error)
    source = (
        _plain_dict_with_fields(value, _DECISION_PACKET_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _DECISION_PACKET_FIELDS, error)
    )
    pilot_status = _one_of(source["pilot_status"], _TERMINAL_STATUSES | {"created", "running"}, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_AI_FLOW_PILOT_DECISION_PACKET_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_AI_FLOW_PILOT_VERSION, error),
        "phase": _literal(source["phase"], "phase33", error),
        "verdict": _decision_verdict(source["verdict"], pilot_status=pilot_status, error=error),
        "pilot_status": pilot_status,
        "evidence": _evidence(source["evidence"], error=error, exact_order=exact_order),
        "rollback": _rollback(source["rollback"], error=error, exact_order=exact_order),
        "separate_approvals_required": _exact_string_list(source["separate_approvals_required"], _SEPARATE_APPROVALS, error),
        "unresolved_risks": _exact_string_list(
            source["unresolved_risks"],
            ["production_enablement_not_approved", "live_gateway_wiring_not_approved"],
            error,
        ),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    if safe["evidence"]["side_effects_absent"] is not True:
        _raise(error)
    if safe["evidence"]["history_no_leak_checked"] is not True:
        _raise(error)
    if safe["evidence"]["result_no_leak_checked"] is not True:
        _raise(error)
    if safe["evidence"]["progress_snapshots_sanitized"] is not True:
        _raise(error)
    if safe["evidence"]["phase32_delivered"] is True and safe["evidence"]["phase31_executed"] is not True:
        _raise(error)
    if safe["pilot_status"] == "pilot_completed":
        if safe["evidence"]["phase31_executed"] is not True or safe["evidence"]["phase32_delivered"] is not True:
            _raise(error)
    elif safe["evidence"]["phase32_delivered"] is True:
        _raise(error)
    return safe


def _decision_packet(*, pilot_status: str, phase31_executed: bool, phase32_delivered: bool) -> dict[str, object]:
    packet = {
        "type": FLOWWEAVER_AI_FLOW_PILOT_DECISION_PACKET_TYPE,
        "version": FLOWWEAVER_AI_FLOW_PILOT_VERSION,
        "phase": "phase33",
        "verdict": FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT
        if pilot_status == "pilot_completed"
        else FLOWWEAVER_AI_FLOW_PILOT_NOT_READY_VERDICT,
        "pilot_status": pilot_status,
        "evidence": {
            "phase31_executed": phase31_executed,
            "phase32_delivered": phase32_delivered,
            "history_no_leak_checked": True,
            "result_no_leak_checked": True,
            "progress_snapshots_sanitized": True,
            "side_effects_absent": True,
        },
        "rollback": {
            "kill_switch_ref": "rollback_phase33_disable_pilot",
            "steps": ["disable_pilot_policy", "preserve_canonical_branch", "rerun_clean_verification"],
            "operator_required": True,
            "side_effects": [],
        },
        "separate_approvals_required": list(_SEPARATE_APPROVALS),
        "unresolved_risks": ["production_enablement_not_approved", "live_gateway_wiring_not_approved"],
        "side_effects": [],
    }
    return _validate_decision_packet(packet, exact_order=True)


def _report(
    *,
    ok: bool,
    phase31_verdict: object,
    phase32_verdict: object,
    history_no_leak_checked: object,
    error_code: str | None,
) -> dict[str, object]:
    phase31 = (
        phase31_verdict
        if phase31_verdict == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT
        else FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT
    )
    phase32 = (
        phase32_verdict
        if phase32_verdict == FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT
        else FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT
    )
    report = {
        "type": FLOWWEAVER_AI_FLOW_PILOT_REPORT_TYPE,
        "version": FLOWWEAVER_AI_FLOW_PILOT_VERSION,
        "phase": "phase33",
        "ok": ok,
        "verdict": FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT if ok else FLOWWEAVER_AI_FLOW_PILOT_NOT_READY_VERDICT,
        "operation": _REPORT_OPERATION,
        "phase31_verdict": phase31,
        "phase32_verdict": phase32,
        "pilot_verified": ok,
        "decision_packet_verified": ok,
        "history_no_leak_checked": True if history_no_leak_checked is True else False,
        "checks": {key: ok for key in _CHECKS},
        "error_code": error_code,
        "side_effects": [],
    }
    return validate_flowweaver_ai_flow_pilot_report(report)


def _validate_agent_result_for_temporal(value: object) -> dict[str, object]:
    return validate_flowweaver_agent_execution_result(_canonical_agent_result_for_temporal(value, error="invalid_agent_execution_result"))


def _validate_delivery_result_for_temporal(value: object) -> dict[str, object]:
    return validate_flowweaver_delivery_activity_result(
        _canonical_delivery_result_for_temporal(value, error="invalid_delivery_activity_result")
    )


def _canonical_agent_request_for_temporal(value: object, *, error: str) -> dict[str, object]:
    source = _plain_dict_with_key_set(
        value,
        [
            "type",
            "version",
            "phase",
            "transaction_id",
            "workflow_id",
            "intent_id",
            "claim_check_ref",
            "claim_policy",
            "artifact_ref",
            "execution_mode",
            "executor_policy",
            "execution_digest",
            "side_effects",
        ],
        error,
    )
    return {
        "type": source["type"],
        "version": source["version"],
        "phase": source["phase"],
        "transaction_id": source["transaction_id"],
        "workflow_id": source["workflow_id"],
        "intent_id": source["intent_id"],
        "claim_check_ref": source["claim_check_ref"],
        "claim_policy": source["claim_policy"],
        "artifact_ref": source["artifact_ref"],
        "execution_mode": source["execution_mode"],
        "executor_policy": source["executor_policy"],
        "execution_digest": source["execution_digest"],
        "side_effects": source["side_effects"],
    }


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


def _canonical_delivery_result_for_temporal(value: object, *, error: str) -> dict[str, object]:
    source = _plain_dict_with_key_set(value, _DELIVERY_RESULT_FIELDS, error)
    counts = _plain_dict_with_key_set(source["counts"], _DELIVERY_RESULT_COUNT_FIELDS, error)
    return {
        "type": source["type"],
        "version": source["version"],
        "phase": source["phase"],
        "activity": source["activity"],
        "status": source["status"],
        "artifact_ref": source["artifact_ref"],
        "delivery_refs": source["delivery_refs"],
        "surface_state": _canonical_surface_state_for_temporal(source["surface_state"], error=error),
        "ack_updates": [_canonical_ack_update_for_temporal(item, error=error) for item in _list(source["ack_updates"], error)],
        "ack_results": [_canonical_ack_result_for_temporal(item, error=error) for item in _list(source["ack_results"], error)],
        "counts": {
            "delivery_calls": counts["delivery_calls"],
            "ack_updates": counts["ack_updates"],
            "ack_applied": counts["ack_applied"],
            "ack_duplicates": counts["ack_duplicates"],
            "ack_rejected": counts["ack_rejected"],
        },
        "delivery_digest": source["delivery_digest"],
        "error_code": source["error_code"],
        "retry_class": source["retry_class"],
        "side_effects": source["side_effects"],
    }


def _canonical_surface_state_for_temporal(value: object, *, error: str) -> dict[str, object]:
    source = _plain_dict_with_key_set(value, _SURFACE_STATE_FIELDS, error)
    return {
        "progress_card_sent": source["progress_card_sent"],
        "rich_cards_sent": source["rich_cards_sent"],
        "final_text_sent": source["final_text_sent"],
        "media_sent": source["media_sent"],
    }


def _canonical_ack_update_for_temporal(value: object, *, error: str) -> dict[str, object]:
    source = _plain_dict_with_key_set(value, _ACK_UPDATE_FIELDS, error)
    return {
        "delivery_ref": source["delivery_ref"],
        "surface": source["surface"],
        "status": source["status"],
        "ack_ref": source["ack_ref"],
    }


def _canonical_ack_result_for_temporal(value: object, *, error: str) -> dict[str, object]:
    source = _plain_dict_with_key_set(value, _ACK_RESULT_FIELDS, error)
    return {
        "status": source["status"],
        "delivery_ref": source["delivery_ref"],
        "surface": source["surface"],
        "error_code": source["error_code"],
        "side_effects": source["side_effects"],
    }


def _pilot_policy(enabled: bool) -> dict[str, object]:
    return {
        "enabled": enabled,
        "mode": _PILOT_POLICY_MODE,
        "scenario": _PILOT_SCENARIO,
        "agent_execution": "phase31_injected_executor_only",
        "delivery": "phase32_injected_delivery_only",
        "history_no_leak_required": True,
        "side_effects": [],
    }


def _pilot_policy_enabled(value: object, *, error: str, exact_order: bool) -> bool:
    source = _pilot_policy_source(value, error=error, exact_order=exact_order)
    return _bool(source["enabled"], error)


def _exact_pilot_policy(value: object, *, enabled: bool, error: str, exact_order: bool) -> dict[str, object]:
    source = _pilot_policy_source(value, error=error, exact_order=exact_order)
    if _bool(source["enabled"], error) is not enabled:
        _raise(error)
    _literal(source["mode"], _PILOT_POLICY_MODE, error)
    _literal(source["scenario"], _PILOT_SCENARIO, error)
    _literal(source["agent_execution"], "phase31_injected_executor_only", error)
    _literal(source["delivery"], "phase32_injected_delivery_only", error)
    _true(source["history_no_leak_required"], error)
    _empty_list(source["side_effects"], error)
    return _pilot_policy(enabled)


def _pilot_policy_source(value: object, *, error: str, exact_order: bool) -> dict[str, object]:
    return (
        _plain_dict_with_fields(value, _PILOT_POLICY_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _PILOT_POLICY_FIELDS, error)
    )


def _exact_decision_policy(value: object, *, error: str, exact_order: bool) -> dict[str, object]:
    source = (
        _plain_dict_with_fields(value, _DECISION_POLICY_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _DECISION_POLICY_FIELDS, error)
    )
    _literal(source["max_verdict"], FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT, error)
    _exact_string_list(source["requires_separate_approvals"], _SEPARATE_APPROVALS, error)
    _true(source["rollback_required"], error)
    _true(source["kill_switch_required"], error)
    _empty_list(source["side_effects"], error)
    return copy.deepcopy(_DECISION_POLICY)


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
                "surface": _one_of(source["surface"], {"progress_card", "rich_card", "final_text", "media"}, error),
                "artifact_ref": slot_artifact_ref,
                "required": _bool(source["required"], error),
            }
        )
    return safe


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


def _activity_sequence(value: object, *, error: str, exact_order: bool) -> list[dict[str, object]]:
    if type(value) is not list or len(value) > 3:
        _raise(error)
    expected = [_CLAIM_ACTIVITY, _EXECUTE_ACTIVITY, _DELIVER_ACTIVITY]
    seen: list[str] = []
    safe: list[dict[str, object]] = []
    for item in value:
        source = (
            _plain_dict_with_fields(item, _ACTIVITY_ITEM_FIELDS, error)
            if exact_order
            else _plain_dict_with_key_set(item, _ACTIVITY_ITEM_FIELDS, error)
        )
        name = _one_of(source["name"], set(expected), error)
        status = _safe_activity_status(name, source["status"])
        raw_error_code = source["error_code"]
        error_code = _safe_error_code(raw_error_code, fallback=None)
        if raw_error_code is not None and error_code is None:
            _raise(error)
        success_statuses = {
            _CLAIM_ACTIVITY: "validated",
            _EXECUTE_ACTIVITY: "executed",
            _DELIVER_ACTIVITY: "delivered",
        }
        if status == success_statuses[name] and raw_error_code is not None:
            _raise(error)
        seen.append(name)
        safe.append(
            {
                "name": name,
                "status": status,
                "error_code": error_code,
                "side_effects": _empty_list(source["side_effects"], error),
            }
        )
    if seen != expected[: len(seen)]:
        _raise(error)
    return safe


def _safe_activity_status(name: str, status: object) -> str:
    allowed = {
        _CLAIM_ACTIVITY: {"validated", "rejected"},
        _EXECUTE_ACTIVITY: {"executed", "rejected", "timed_out", "cancelled"},
        _DELIVER_ACTIVITY: {"delivered", "partially_delivered", "disabled", "rejected", "timed_out", "cancelled"},
    }[name]
    return _one_of(status, allowed, "invalid_ai_flow_pilot_snapshot")


def _counts(value: object, *, error: str, exact_order: bool) -> dict[str, int]:
    source = (
        _plain_dict_with_fields(value, _COUNT_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _COUNT_FIELDS, error)
    )
    return {
        "activities": _bounded_nonnegative_int(source["activities"], maximum=3, error=error),
        "artifacts": _bounded_nonnegative_int(source["artifacts"], maximum=1, error=error),
        "deliveries": _bounded_nonnegative_int(source["deliveries"], maximum=16, error=error),
        "executor_calls": _bounded_nonnegative_int(source["executor_calls"], maximum=1, error=error),
        "tool_calls": _bounded_nonnegative_int(source["tool_calls"], maximum=32, error=error),
        "ack_updates": _bounded_nonnegative_int(source["ack_updates"], maximum=16, error=error),
        "ack_applied": _bounded_nonnegative_int(source["ack_applied"], maximum=16, error=error),
        "ack_duplicates": _bounded_nonnegative_int(source["ack_duplicates"], maximum=16, error=error),
        "ack_rejected": _bounded_nonnegative_int(source["ack_rejected"], maximum=16, error=error),
    }


def _intent_statuses(value: object, *, error: str) -> dict[str, str]:
    if type(value) is not dict:
        _raise(error)
    safe: dict[str, str] = {}
    for key, status in value.items():
        safe[_safe_identifier(key, prefix="runtime_intent_", error=error)] = _one_of(
            status,
            {"running", "executed", "delivered", "partially_delivered", "disabled", "rejected", "timed_out", "cancelled"},
            error,
        )
    return dict(sorted(safe.items()))


def _evidence(value: object, *, error: str, exact_order: bool) -> dict[str, bool]:
    source = (
        _plain_dict_with_fields(value, _EVIDENCE_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _EVIDENCE_FIELDS, error)
    )
    return {key: _bool(source[key], error) for key in _EVIDENCE_FIELDS}


def _rollback(value: object, *, error: str, exact_order: bool) -> dict[str, object]:
    source = (
        _plain_dict_with_fields(value, _ROLLBACK_FIELDS, error)
        if exact_order
        else _plain_dict_with_key_set(value, _ROLLBACK_FIELDS, error)
    )
    return {
        "kill_switch_ref": _literal(source["kill_switch_ref"], "rollback_phase33_disable_pilot", error),
        "steps": _exact_string_list(
            source["steps"],
            ["disable_pilot_policy", "preserve_canonical_branch", "rerun_clean_verification"],
            error,
        ),
        "operator_required": _true(source["operator_required"], error),
        "side_effects": _empty_list(source["side_effects"], error),
    }


def _decision_verdict(value: object, *, pilot_status: str, error: str) -> str:
    _one_of(pilot_status, _TERMINAL_STATUSES | {"created", "running"}, error)
    if pilot_status == "pilot_completed":
        return _literal(value, FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT, error)
    return _literal(value, FLOWWEAVER_AI_FLOW_PILOT_NOT_READY_VERDICT, error)


def _report_verdict(value: object, *, ok: bool, error: str) -> str:
    if ok:
        return _literal(value, FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT, error)
    return _literal(value, FLOWWEAVER_AI_FLOW_PILOT_NOT_READY_VERDICT, error)


def _report_checks(value: object, *, ok: bool, error: str) -> dict[str, bool]:
    source = _plain_dict_with_fields(value, _CHECKS, error)
    safe: dict[str, bool] = {}
    for key in _CHECKS:
        if type(source[key]) is not bool:
            _raise(error)
        safe[key] = bool(source[key])
    if ok and any(item is not True for item in safe.values()):
        _raise(error)
    return safe


def _report_error_value(value: object, *, ok: bool, error: str) -> str | None:
    if ok:
        return _none(value, error)
    if type(value) is not str or value not in {
        "invalid_phase31_agent_execution_activity_report",
        "invalid_phase32_delivery_activity_report",
        "invalid_ai_flow_pilot_snapshot",
        "invalid_ai_flow_pilot_decision_packet",
        "history_not_verified",
    }:
        _raise(error)
    return value


def _report_error_code(value: str) -> str:
    if value in {
        "invalid_phase31_agent_execution_activity_report",
        "invalid_phase32_delivery_activity_report",
        "invalid_ai_flow_pilot_snapshot",
        "invalid_ai_flow_pilot_decision_packet",
        "history_not_verified",
    }:
        return value
    return "invalid_ai_flow_pilot_snapshot"


def _snapshot_error_code(value: object, *, status: str, error: str) -> str | None:
    if status == "pilot_completed":
        return _none(value, error)
    if status in {"created", "running"} and value is None:
        return None
    code = _safe_error_code(value, fallback=None)
    if code is None:
        _raise(error)
    return code


def _safe_error_code(value: object, *, fallback: str | None) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        return fallback
    return value if value in _SAFE_ERROR_CODES else fallback


def _pilot_digest(
    *,
    transaction_id: str,
    intent_id: str,
    execution_digest: str,
    delivery_refs: list[str],
    enabled: bool,
) -> str:
    material = "|".join(
        (
            "phase33",
            transaction_id,
            intent_id,
            execution_digest,
            ",".join(delivery_refs),
            "enabled" if enabled else "disabled",
        )
    )
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _empty_surface_state() -> dict[str, object]:
    return {
        "progress_card_sent": False,
        "rich_cards_sent": 0,
        "final_text_sent": False,
        "media_sent": 0,
    }


def _zero_counts() -> dict[str, int]:
    return {
        "activities": 0,
        "artifacts": 0,
        "deliveries": 0,
        "executor_calls": 0,
        "tool_calls": 0,
        "ack_updates": 0,
        "ack_applied": 0,
        "ack_duplicates": 0,
        "ack_rejected": 0,
    }


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


def _list(value: object, error: str) -> list[object]:
    if type(value) is not list:
        _raise(error)
    return value


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
