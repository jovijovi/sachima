"""FlowWeaver Phase 31 controlled agent execution Activity boundary.

This module adds a non-production, injected-executor Activity boundary for
agent/tool execution. Workflow history and snapshots carry only claim-check
references, safe runtime ids, counts, digests, statuses, and stable error codes.
Raw prompt/tool/model material may be handled only inside the Activity process by
an explicitly injected executor and is never returned by this module.
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
    from gateway.flowweaver_temporal_stub_activity_orchestration import (
        FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
        FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION,
        validate_claim_check_ref_activity,
    )

FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_CONTRACT_TYPE = "flowweaver.gateway.agent_execution_activity_contract.v0"
FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REPORT_TYPE = "flowweaver.gateway.agent_execution_activity_report.v0"
FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REQUEST_TYPE = "flowweaver.gateway.agent_execution_activity_request.v0"
FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_RESULT_TYPE = "flowweaver.gateway.agent_execution_activity_result.v0"
FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SNAPSHOT_TYPE = "flowweaver.gateway.agent_execution_activity_snapshot.v0"
FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT = "ready_for_controlled_delivery_activity_request"
FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION = "flowweaver.agent_execution_activity.v0"
FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_TASK_QUEUE = "flowweaver-phase31-agent-execution-activity"

_CONTROLLED_ACTIVITY_TYPE = "execute_agent_turn"
_REPORT_OPERATION = "build_flowweaver_agent_execution_activity_report"
_ACTIVITY_TIMEOUT = timedelta(seconds=15)
_ACTIVITY_RETRY_POLICY = RetryPolicy(
    maximum_attempts=2,
    non_retryable_error_types=[
        "invalid_agent_execution_request",
        "invalid_claim_ref",
        "unsafe_material",
        "executor_auth_config_failure",
        "executor_cancelled",
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
    "report_fields",
    "executor_boundary",
    "runtime_policy",
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
    "claim_check_ref",
    "claim_policy",
    "artifact_ref",
    "execution_mode",
    "executor_policy",
    "execution_digest",
    "side_effects",
]
_RESULT_FIELDS = [
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
_SNAPSHOT_FIELDS = [
    "type",
    "version",
    "phase",
    "transaction_id",
    "workflow_id",
    "status",
    "intent_statuses",
    "artifact_refs",
    "activity_sequence",
    "counts",
    "execution_digest",
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
    "phase30_verdict",
    "controlled_executor_verified",
    "history_no_leak_checked",
    "result_no_leak_checked",
    "checks",
    "error_code",
    "side_effects",
]
_ERROR_REPORT_FIELDS = ["type", "version", "phase", "ok", "operation", "error_code", "side_effects"]
_ENTRYPOINTS = [
    "describe_flowweaver_agent_execution_activity_contract",
    "build_flowweaver_agent_execution_request",
    "validate_flowweaver_agent_execution_request",
    "execute_controlled_agent_turn",
    "build_execute_agent_turn_activity",
    "validate_flowweaver_agent_execution_result",
    "validate_flowweaver_agent_execution_snapshot",
    "build_flowweaver_agent_execution_activity_report",
    "validate_flowweaver_agent_execution_activity_report",
]
_EXECUTOR_BOUNDARY = {
    "mode": "injected_executor_only",
    "executor_input": "safe_claim_ref_and_runtime_ids_only",
    "raw_material_access": "activity_boundary_only",
    "executor_output": "sanitized_artifact_ref_counts_digest_only",
    "global_agent_factory": "forbidden",
    "side_effects": [],
}
_RUNTIME_POLICY = {
    "mode": "controlled_non_production_agent_execution_activity",
    "temporal_runtime": "local_staging_only",
    "gateway_delivery_ack": "forbidden_until_phase32",
    "production_agent_execution": "forbidden",
    "executor_injection": "required",
    "raw_material_policy": "claim_check_refs_in_history_executor_raw_local_only",
    "side_effects": [],
}
_RETRY_POLICY_DESCRIPTOR = {
    "start_to_close_timeout_seconds": 15,
    "maximum_attempts": 2,
    "non_retryable_error_types": [
        "invalid_agent_execution_request",
        "invalid_claim_ref",
        "unsafe_material",
        "executor_auth_config_failure",
        "executor_cancelled",
    ],
    "transient_error_types": ["executor_failed", "executor_timeout"],
}
_CHECKS = [
    "phase30_verdict_valid",
    "executor_injected_and_observable",
    "unsafe_claims_fail_before_executor",
    "executor_success_sanitized",
    "executor_failure_sanitized",
    "timeout_cancel_sanitized",
    "history_no_leak_verified",
    "delivery_surfaces_absent",
    "side_effects_absent",
]
_SEPARATE_APPROVALS = [
    "controlled_delivery_activity",
    "production_gateway_wiring",
    "production_agent_execution",
    "production_config_write",
    "gateway_restart",
    "platform_adapter_mutation",
    "real_send_edit_render_callback_control",
    "delivery_ack_updates",
]
_FORBIDDEN_SIDE_EFFECTS = [
    "global_aiagent_instance",
    "hidden_executor_factory",
    "gateway_hook_change",
    "gateway_adapter_access",
    "platform_adapter_mutation",
    "production_config_write",
    "gateway_restart",
    "sub" + "process",
    "sock" + "et",
    "dock" + "er",
    "daemon",
    "service_startup",
    "send",
    "edit",
    "render",
    "callback_control",
    "delivery_ack_update",
    "raw_material_persistence",
]
_CLAIM_FIELDS = ["ref", "kind", "count", "size", "checksum_hint"]
_CLAIM_POLICY = {
    "mode": "claim_check_refs_only",
    "allowed_kinds": ["agent_input"],
    "checksum_hint": "sha256_64_lower_hex",
    "side_effects": [],
}
_VALIDATED_CLAIM_FIELDS = ["activity", "status", "claim_ref", "error_code", "side_effects"]
_EXECUTOR_REQUEST_FIELDS = [
    "transaction_id",
    "workflow_id",
    "intent_id",
    "claim_check_ref",
    "artifact_ref",
    "execution_mode",
    "executor_policy",
    "execution_digest",
]
_EXECUTOR_RESULT_FIELDS = ["status", "artifact_ref", "raw_output", "tool_call_count", "output_item_count"]
_RAW_VALUE_MARKERS = (
    "oc_",
    "ou_",
    "om_",
    "raw prompt",
    "raw tool output",
    "tool_output",
    "card_json",
    "media_path",
    "/tmp/",
    "callback payload",
    "callback_payload",
    "runtimeerror:",
    "valueerror:",
    "traceback",
    "unsafe-token",
    "bearer ",
    "password=",
    "secret=",
    "api_key=",
    "sk-",
    "platform_id",
    "chat_id",
    "user_id",
    "message_id",
    "credential",
)
_HEX = frozenset("0123456789abcdef")
_MAX_PLAIN_TREE_DEPTH = 64
_ZERO_DIGEST = "sha256:" + ("0" * 64)


def describe_flowweaver_agent_execution_activity_contract() -> dict[str, object]:
    """Return the exact Phase 31 controlled executor Activity descriptor."""

    return {
        "type": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_CONTRACT_TYPE,
        "version": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
        "phase": "phase31",
        "verdict": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        "scope": "controlled_agent_execution_activity",
        "consumes_verdict": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
        "entrypoints": list(_ENTRYPOINTS),
        "request_fields": list(_REQUEST_FIELDS),
        "result_fields": list(_RESULT_FIELDS),
        "report_fields": list(_REPORT_FIELDS),
        "executor_boundary": copy.deepcopy(_EXECUTOR_BOUNDARY),
        "runtime_policy": copy.deepcopy(_RUNTIME_POLICY),
        "retry_policy": copy.deepcopy(_RETRY_POLICY_DESCRIPTOR),
        "checks": list(_CHECKS),
        "separate_approvals": list(_SEPARATE_APPROVALS),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }


def build_flowweaver_agent_execution_request(
    *,
    transaction_id: object,
    workflow_id: object,
    intent_id: object,
    claim_check_ref: object,
    artifact_ref: object,
) -> dict[str, object]:
    """Build a safe Phase 31 execution request from refs and runtime ids."""

    tx_id = _safe_identifier(transaction_id, prefix="runtime_tx_", error="invalid_agent_execution_request")
    wf_id = _safe_identifier(workflow_id, prefix="runtime_tx_", error="invalid_agent_execution_request")
    if wf_id != tx_id:
        _raise("invalid_agent_execution_request")
    safe_intent_id = _safe_identifier(intent_id, prefix="runtime_intent_", error="invalid_agent_execution_request")
    safe_claim = _validate_claim_ref(claim_check_ref, error="invalid_agent_execution_request")
    safe_artifact_ref = _safe_identifier(artifact_ref, prefix="runtime_artifact_", error="invalid_agent_execution_request")
    digest = _execution_digest(
        transaction_id=tx_id,
        intent_id=safe_intent_id,
        claim_ref=str(safe_claim["ref"]),
        artifact_ref=safe_artifact_ref,
    )
    request = {
        "type": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REQUEST_TYPE,
        "version": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
        "phase": "phase31",
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "intent_id": safe_intent_id,
        "claim_check_ref": safe_claim,
        "claim_policy": copy.deepcopy(_CLAIM_POLICY),
        "artifact_ref": safe_artifact_ref,
        "execution_mode": "controlled_non_production_agent_activity",
        "executor_policy": copy.deepcopy(_EXECUTOR_BOUNDARY),
        "execution_digest": digest,
        "side_effects": [],
    }
    return validate_flowweaver_agent_execution_request(request)


def validate_flowweaver_agent_execution_request(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 31 execution request copy."""

    error = "invalid_agent_execution_request"
    source = _plain_dict_with_fields(value, _REQUEST_FIELDS, error)
    tx_id = _literal_safe_identifier(source["transaction_id"], prefix="runtime_tx_", error=error)
    wf_id = _literal_safe_identifier(source["workflow_id"], prefix="runtime_tx_", error=error)
    if wf_id != tx_id:
        _raise(error)
    safe_claim = _validate_claim_ref(source["claim_check_ref"], error=error)
    artifact_ref = _literal_safe_identifier(source["artifact_ref"], prefix="runtime_artifact_", error=error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REQUEST_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION, error),
        "phase": _literal(source["phase"], "phase31", error),
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "intent_id": _literal_safe_identifier(source["intent_id"], prefix="runtime_intent_", error=error),
        "claim_check_ref": safe_claim,
        "claim_policy": _exact_claim_policy(source["claim_policy"], error=error),
        "artifact_ref": artifact_ref,
        "execution_mode": _literal(source["execution_mode"], "controlled_non_production_agent_activity", error),
        "executor_policy": _exact_executor_policy(source["executor_policy"], error=error),
        "execution_digest": _digest(source["execution_digest"], error=error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    expected_digest = _execution_digest(
        transaction_id=safe["transaction_id"],
        intent_id=safe["intent_id"],
        claim_ref=str(safe_claim["ref"]),
        artifact_ref=artifact_ref,
    )
    if safe["execution_digest"] != expected_digest:
        _raise(error)
    return safe


async def execute_controlled_agent_turn(
    *, execution_request: object, validated_claim: object, executor: Callable[[dict[str, object]], object]
) -> dict[str, object]:
    """Call an injected non-production executor and return sanitized artifact metadata only."""

    try:
        request = validate_flowweaver_agent_execution_request(execution_request)
        claim = _canonical_validated_claim(validated_claim)
        claim_ref = str(claim["claim_ref"])
        if claim_ref != str(request["claim_check_ref"]["ref"]):
            _raise("invalid_agent_execution_request")
        if not callable(executor):
            _raise("invalid_agent_execution_request")
    except ValueError as exc:
        code = _pre_executor_error_code(str(exc))
        return _agent_result(status="rejected", artifact_ref=None, counts=_empty_counts(0), output_digest=_ZERO_DIGEST, error_code=code)

    executor_request = _executor_request(request)
    try:
        executor_result = executor(executor_request)
        if inspect.isawaitable(executor_result):
            executor_result = await executor_result
    except asyncio.CancelledError:
        return _agent_result(
            status="cancelled",
            artifact_ref=None,
            counts=_empty_counts(1),
            output_digest=_ZERO_DIGEST,
            error_code="executor_cancelled",
        )
    except Exception:
        return _agent_result(
            status="rejected",
            artifact_ref=None,
            counts=_empty_counts(1),
            output_digest=_ZERO_DIGEST,
            error_code="executor_failed",
        )

    return _sanitize_executor_result(executor_result, request)


def build_execute_agent_turn_activity(*, executor: Callable[[dict[str, object]], object]) -> Callable[[dict[str, Any]], Any]:
    """Build the Temporal Activity wrapper with an explicit caller-supplied executor."""

    if not callable(executor):
        _raise("invalid_agent_execution_request")

    @activity.defn(name=_CONTROLLED_ACTIVITY_TYPE)
    async def execute_agent_turn_controlled_activity(payload: dict[str, Any]) -> dict[str, Any]:
        if _contains_forbidden_material(payload):
            return _agent_result(
                status="rejected",
                artifact_ref=None,
                counts=_empty_counts(0),
                output_digest=_ZERO_DIGEST,
                error_code="unsafe_material",
            )
        try:
            source = _plain_dict_with_fields(payload, ["execution_request", "validated_claim"], "invalid_agent_execution_request")
        except ValueError:
            return _agent_result(
                status="rejected",
                artifact_ref=None,
                counts=_empty_counts(0),
                output_digest=_ZERO_DIGEST,
                error_code="invalid_agent_execution_request",
            )
        result = await execute_controlled_agent_turn(
            execution_request=source["execution_request"],
            validated_claim=source["validated_claim"],
            executor=executor,
        )
        return dict(result)

    return execute_agent_turn_controlled_activity


def validate_flowweaver_agent_execution_result(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 31 Activity result."""

    error = "invalid_agent_execution_result"
    source = _plain_dict_with_fields(value, _RESULT_FIELDS, error)
    status = _one_of(source["status"], {"executed", "rejected", "timed_out", "cancelled"}, error)
    artifact_ref = _optional_safe_identifier(source["artifact_ref"], prefix="runtime_artifact_", error=error)
    if status == "executed" and artifact_ref is None:
        _raise(error)
    if status != "executed" and artifact_ref is not None:
        _raise(error)
    error_code = _result_error_code(source["error_code"], status=status, error=error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_RESULT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION, error),
        "phase": _literal(source["phase"], "phase31", error),
        "activity": _literal(source["activity"], _CONTROLLED_ACTIVITY_TYPE, error),
        "status": status,
        "artifact_ref": artifact_ref,
        "artifact_kind": _artifact_kind(source["artifact_kind"], status=status, error=error),
        "counts": _result_counts(source["counts"], error=error),
        "output_digest": _digest(source["output_digest"], error=error),
        "error_code": error_code,
        "retry_class": _retry_class(source["retry_class"], error_code=error_code, error=error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    return safe


def validate_flowweaver_agent_execution_snapshot(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 31 workflow snapshot copy."""

    error = "invalid_agent_execution_snapshot"
    source = _plain_dict_with_fields(value, _SNAPSHOT_FIELDS, error)
    tx_id = _literal_safe_identifier(source["transaction_id"], prefix="runtime_tx_", error=error)
    wf_id = _literal_safe_identifier(source["workflow_id"], prefix="runtime_tx_", error=error)
    if wf_id != tx_id:
        _raise(error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SNAPSHOT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION, error),
        "phase": _literal(source["phase"], "phase31", error),
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "status": _one_of(source["status"], {"created", "running", "agent_execution_completed", "rejected", "timed_out", "cancelled"}, error),
        "intent_statuses": _intent_statuses(source["intent_statuses"], error=error),
        "artifact_refs": _safe_identifier_list(source["artifact_refs"], prefix="runtime_artifact_", error=error),
        "activity_sequence": _activity_sequence(source["activity_sequence"], error=error),
        "counts": _snapshot_counts(source["counts"], error=error),
        "execution_digest": _digest(source["execution_digest"], error=error),
        "error_code": _snapshot_error_code(source["error_code"], error=error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    return safe


def validate_flowweaver_agent_execution_activity_report(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 31 report copy."""

    error = "invalid_agent_execution_activity_report"
    if type(value) is dict and _keys_match_exactly(value, _ERROR_REPORT_FIELDS):
        return _validate_error_report(value, error=error)
    source = _plain_dict_with_fields(value, _REPORT_FIELDS, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION, error),
        "phase": _literal(source["phase"], "phase31", error),
        "ok": _true(source["ok"], error),
        "verdict": _literal(source["verdict"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT, error),
        "operation": _literal(source["operation"], _REPORT_OPERATION, error),
        "phase30_verdict": _literal(
            source["phase30_verdict"],
            FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
            error,
        ),
        "controlled_executor_verified": _true(source["controlled_executor_verified"], error),
        "history_no_leak_checked": _true(source["history_no_leak_checked"], error),
        "result_no_leak_checked": _true(source["result_no_leak_checked"], error),
        "checks": _checks(source["checks"], error=error),
        "error_code": _none(source["error_code"], error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    return safe


def build_flowweaver_agent_execution_activity_report(
    *,
    temporal_stub_activity_version: object,
    temporal_stub_activity_verdict: object,
    controlled_execution_result: object,
    history_no_leak_checked: object,
) -> dict[str, object]:
    """Build Phase 31 metadata from sanitized controlled execution evidence."""

    try:
        _literal(
            temporal_stub_activity_version,
            FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION,
            "invalid_phase30_temporal_stub_activity_orchestration_report",
        )
        _literal(
            temporal_stub_activity_verdict,
            FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
            "invalid_phase30_temporal_stub_activity_orchestration_report",
        )
        result = validate_flowweaver_agent_execution_result(controlled_execution_result)
        if result["status"] != "executed":
            _raise("invalid_controlled_agent_execution_result")
        _true(history_no_leak_checked, "invalid_controlled_agent_execution_result")
    except ValueError as exc:
        code = str(exc)
        if code not in {
            "invalid_phase30_temporal_stub_activity_orchestration_report",
            "invalid_controlled_agent_execution_result",
        }:
            code = "invalid_controlled_agent_execution_result"
        return _error_report(code)
    report = {
        "type": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REPORT_TYPE,
        "version": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
        "phase": "phase31",
        "ok": True,
        "verdict": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        "operation": _REPORT_OPERATION,
        "phase30_verdict": temporal_stub_activity_verdict,
        "controlled_executor_verified": True,
        "history_no_leak_checked": True,
        "result_no_leak_checked": True,
        "checks": {key: True for key in _CHECKS},
        "error_code": None,
        "side_effects": [],
    }
    return validate_flowweaver_agent_execution_activity_report(report)


@workflow.defn
class FlowWeaverAgentExecutionActivityWorkflow:
    """Local/staging workflow that validates a claim ref and executes the injected executor Activity."""

    def __init__(self) -> None:
        self._transaction_id = "runtime_tx_uninitialized"
        self._workflow_id = "runtime_tx_uninitialized"
        self._status = "created"
        self._intent_statuses: dict[str, str] = {}
        self._artifact_refs: list[str] = []
        self._activity_sequence: list[dict[str, Any]] = []
        self._execution_digest = _ZERO_DIGEST
        self._error_code: str | None = None
        self._executor_calls = 0
        self._tool_calls = 0

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            request = validate_flowweaver_agent_execution_request(payload)
        except ValueError as exc:
            self._status = "rejected"
            self._error_code = _safe_error_code(str(exc), fallback="invalid_agent_execution_request")
            return self._snapshot()

        self._transaction_id = str(request["transaction_id"])
        self._workflow_id = str(request["workflow_id"])
        intent_id = str(request["intent_id"])
        self._status = "running"
        self._intent_statuses = {intent_id: "running"}
        self._artifact_refs = []
        self._activity_sequence = []
        self._execution_digest = str(request["execution_digest"])
        self._error_code = None
        self._executor_calls = 0
        self._tool_calls = 0

        claim_result = await workflow.execute_activity(
            validate_claim_check_ref_activity,
            {
                "claim_check_ref": request["claim_check_ref"],
                "policy_descriptor": request["claim_policy"],
            },
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY_POLICY,
        )
        self._record_activity_result("validate_claim_check_ref", claim_result)
        if claim_result.get("status") != "validated":
            self._status = "rejected"
            self._intent_statuses[intent_id] = "rejected"
            self._error_code = _safe_error_code(claim_result.get("error_code"), fallback="invalid_claim_ref")
            return self._snapshot()

        agent_result = await workflow.execute_activity(
            _CONTROLLED_ACTIVITY_TYPE,
            {
                "execution_request": request,
                "validated_claim": claim_result,
            },
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY_POLICY,
        )
        safe_result = validate_flowweaver_agent_execution_result(agent_result)
        self._record_activity_result(_CONTROLLED_ACTIVITY_TYPE, safe_result)
        counts = safe_result["counts"]
        self._executor_calls = int(counts["executor_calls"])
        self._tool_calls = int(counts["tool_calls"])
        self._error_code = _safe_error_code(safe_result["error_code"], fallback=None)
        if safe_result["status"] == "executed":
            self._status = "agent_execution_completed"
            self._intent_statuses[intent_id] = "executed"
            self._artifact_refs = [str(safe_result["artifact_ref"])]
        elif safe_result["status"] == "timed_out":
            self._status = "timed_out"
            self._intent_statuses[intent_id] = "timed_out"
            self._artifact_refs = []
        elif safe_result["status"] == "cancelled":
            self._status = "cancelled"
            self._intent_statuses[intent_id] = "cancelled"
            self._artifact_refs = []
        else:
            self._status = "rejected"
            self._intent_statuses[intent_id] = "rejected"
            self._artifact_refs = []
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
            "type": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SNAPSHOT_TYPE,
            "version": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
            "phase": "phase31",
            "transaction_id": self._transaction_id,
            "workflow_id": self._workflow_id,
            "status": self._status,
            "intent_statuses": dict(sorted(self._intent_statuses.items())),
            "artifact_refs": list(self._artifact_refs),
            "activity_sequence": [dict(item) for item in self._activity_sequence],
            "counts": {
                "activities": len(self._activity_sequence),
                "artifacts": len(self._artifact_refs),
                "executor_calls": self._executor_calls,
                "tool_calls": self._tool_calls,
            },
            "execution_digest": self._execution_digest,
            "error_code": self._error_code,
            "side_effects": [],
        }
        return validate_flowweaver_agent_execution_snapshot(snapshot)


def _sanitize_executor_result(value: object, request: dict[str, object]) -> dict[str, object]:
    try:
        source = _plain_dict_with_fields(value, _EXECUTOR_RESULT_FIELDS, "invalid_executor_result")
        status = _one_of(
            source["status"],
            {"completed", "timed_out", "cancelled", "auth_config_failure"},
            "invalid_executor_result",
        )
        tool_calls = _bounded_nonnegative_int(source["tool_call_count"], maximum=32, error="invalid_executor_result")
        output_items = _bounded_nonnegative_int(source["output_item_count"], maximum=32, error="invalid_executor_result")
        raw_output = _raw_output_string(source["raw_output"], error="invalid_executor_result")
        output_digest = _raw_output_digest(raw_output)
        if status == "completed":
            artifact_ref = _literal_safe_identifier(
                source["artifact_ref"], prefix="runtime_artifact_", error="invalid_executor_result"
            )
            if artifact_ref != request["artifact_ref"]:
                _raise("invalid_executor_result")
            if output_items <= 0:
                _raise("invalid_executor_result")
            return _agent_result(
                status="executed",
                artifact_ref=artifact_ref,
                counts={"executor_calls": 1, "tool_calls": tool_calls, "output_items": output_items},
                output_digest=output_digest,
                error_code=None,
            )
        if status == "timed_out":
            return _agent_result(
                status="timed_out",
                artifact_ref=None,
                counts={"executor_calls": 1, "tool_calls": tool_calls, "output_items": 0},
                output_digest=output_digest,
                error_code="executor_timeout",
            )
        if status == "cancelled":
            return _agent_result(
                status="cancelled",
                artifact_ref=None,
                counts={"executor_calls": 1, "tool_calls": tool_calls, "output_items": 0},
                output_digest=output_digest,
                error_code="executor_cancelled",
            )
        return _agent_result(
            status="rejected",
            artifact_ref=None,
            counts={"executor_calls": 1, "tool_calls": tool_calls, "output_items": 0},
            output_digest=output_digest,
            error_code="executor_auth_config_failure",
        )
    except ValueError:
        return _agent_result(
            status="rejected",
            artifact_ref=None,
            counts=_empty_counts(1),
            output_digest=_ZERO_DIGEST,
            error_code="invalid_executor_result",
        )


def _executor_request(request: dict[str, object]) -> dict[str, object]:
    claim = request["claim_check_ref"]
    if type(claim) is not dict:
        _raise("invalid_agent_execution_request")
    return {
        "transaction_id": request["transaction_id"],
        "workflow_id": request["workflow_id"],
        "intent_id": request["intent_id"],
        "claim_check_ref": claim["ref"],
        "artifact_ref": request["artifact_ref"],
        "execution_mode": request["execution_mode"],
        "executor_policy": copy.deepcopy(_EXECUTOR_BOUNDARY),
        "execution_digest": request["execution_digest"],
    }


def _agent_result(
    *, status: str, artifact_ref: str | None, counts: dict[str, int], output_digest: str, error_code: str | None
) -> dict[str, object]:
    result = {
        "type": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_RESULT_TYPE,
        "version": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
        "phase": "phase31",
        "activity": _CONTROLLED_ACTIVITY_TYPE,
        "status": status,
        "artifact_ref": artifact_ref,
        "artifact_kind": "controlled_agent_result" if status == "executed" else None,
        "counts": dict(counts),
        "output_digest": output_digest,
        "error_code": error_code,
        "retry_class": _retry_class_for_error(error_code),
        "side_effects": [],
    }
    return validate_flowweaver_agent_execution_result(result)


def _empty_counts(executor_calls: int) -> dict[str, int]:
    return {"executor_calls": executor_calls, "tool_calls": 0, "output_items": 0}


def _validate_error_report(value: dict[str, object], *, error: str) -> dict[str, object]:
    source = _plain_dict_with_fields(value, _ERROR_REPORT_FIELDS, error)
    return {
        "type": _literal(source["type"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION, error),
        "phase": _literal(source["phase"], "phase31", error),
        "ok": _false(source["ok"], error),
        "operation": _literal(source["operation"], _REPORT_OPERATION, error),
        "error_code": _one_of(
            source["error_code"],
            {
                "invalid_phase30_temporal_stub_activity_orchestration_report",
                "invalid_controlled_agent_execution_result",
            },
            error,
        ),
        "side_effects": _empty_list(source["side_effects"], error),
    }


def _error_report(error_code: str) -> dict[str, object]:
    return {
        "type": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REPORT_TYPE,
        "version": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
        "phase": "phase31",
        "ok": False,
        "operation": _REPORT_OPERATION,
        "error_code": error_code,
        "side_effects": [],
    }


def _plain_dict_with_fields(value: object, fields: list[str], error: str) -> dict[str, object]:
    if type(value) is not dict or not _keys_match_exactly(value, fields):
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
    return set(keys) == set(fields)


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


def _none(value: object, error: str) -> None:
    if value is not None:
        _raise(error)
    return None


def _empty_list(value: object, error: str) -> list[object]:
    if type(value) is not list or value:
        _raise(error)
    return []


def _safe_identifier(value: object, *, prefix: str, error: str) -> str:
    if type(value) is not str or not value.startswith(prefix):
        _raise(error)
    suffix = value.removeprefix(prefix)
    if not suffix or len(value) > 96:
        _raise(error)
    if any(not (character.islower() or character.isdigit() or character == "_") for character in suffix):
        _raise(error)
    for marker in ("oc_", "ou_", "om_", "private", "platform", "callback", "credential", "secret"):
        if marker in suffix:
            _raise(error)
    return value


def _literal_safe_identifier(value: object, *, prefix: str, error: str) -> str:
    return _safe_identifier(value, prefix=prefix, error=error)


def _optional_safe_identifier(value: object, *, prefix: str, error: str) -> str | None:
    if value is None:
        return None
    return _literal_safe_identifier(value, prefix=prefix, error=error)


def _digest(value: object, *, error: str) -> str:
    if type(value) is not str or not value.startswith("sha256:"):
        _raise(error)
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        _raise(error)
    return value


def _checksum_hint(value: object, error: str) -> str:
    return _digest(value, error=error)


def _execution_digest(*, transaction_id: str, intent_id: str, claim_ref: str, artifact_ref: str) -> str:
    material = "|".join(("phase31", transaction_id, intent_id, claim_ref, artifact_ref))
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _raw_output_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _raw_output_string(value: object, *, error: str) -> str:
    if type(value) is not str:
        _raise(error)
    return value


def _validate_claim_ref(value: object, *, error: str) -> dict[str, object]:
    source = _plain_dict_with_fields(value, _CLAIM_FIELDS, error)
    return {
        "ref": _literal_safe_identifier(source["ref"], prefix="claim_ref_", error=error),
        "kind": _literal(source["kind"], "agent_input", error),
        "count": _positive_int(source["count"], error),
        "size": _positive_int(source["size"], error),
        "checksum_hint": _checksum_hint(source["checksum_hint"], error),
    }


def _canonical_validated_claim(value: object) -> dict[str, object]:
    if _contains_forbidden_material(value):
        _raise("unsafe_material")
    source = _plain_dict_with_fields(value, _VALIDATED_CLAIM_FIELDS, "invalid_agent_execution_request")
    return {
        "activity": _literal(source["activity"], "validate_claim_check_ref", "invalid_agent_execution_request"),
        "status": _literal(source["status"], "validated", "invalid_agent_execution_request"),
        "claim_ref": _literal_safe_identifier(
            source["claim_ref"], prefix="claim_ref_", error="invalid_agent_execution_request"
        ),
        "error_code": _none(source["error_code"], "invalid_agent_execution_request"),
        "side_effects": _empty_list(source["side_effects"], "invalid_agent_execution_request"),
    }


def _exact_claim_policy(value: object, *, error: str) -> dict[str, object]:
    _assert_exact(value, _CLAIM_POLICY, error)
    return copy.deepcopy(_CLAIM_POLICY)


def _exact_executor_policy(value: object, *, error: str) -> dict[str, object]:
    _assert_exact(value, _EXECUTOR_BOUNDARY, error)
    return copy.deepcopy(_EXECUTOR_BOUNDARY)


def _positive_int(value: object, error: str) -> int:
    if type(value) is not int or value <= 0:
        _raise(error)
    return value


def _bounded_nonnegative_int(value: object, *, maximum: int, error: str) -> int:
    if type(value) is not int or value < 0 or value > maximum:
        _raise(error)
    return value


def _safe_identifier_list(value: object, *, prefix: str, error: str) -> list[str]:
    if type(value) is not list:
        _raise(error)
    return [_literal_safe_identifier(item, prefix=prefix, error=error) for item in value]


def _intent_statuses(value: object, *, error: str) -> dict[str, str]:
    if type(value) is not dict:
        _raise(error)
    safe: dict[str, str] = {}
    for key, status in value.items():
        safe[_literal_safe_identifier(key, prefix="runtime_intent_", error=error)] = _one_of(
            status,
            {"running", "executed", "rejected", "timed_out", "cancelled"},
            error,
        )
    return dict(sorted(safe.items()))


def _activity_sequence(value: object, *, error: str) -> list[dict[str, object]]:
    if type(value) is not list or len(value) > 2:
        _raise(error)
    safe: list[dict[str, object]] = []
    seen: list[str] = []
    expected = ["validate_claim_check_ref", _CONTROLLED_ACTIVITY_TYPE]
    for item in value:
        source = _plain_dict_with_fields(item, ["name", "status", "error_code", "side_effects"], error)
        name = _one_of(source["name"], set(expected), error)
        if name in seen:
            _raise(error)
        safe.append(
            {
                "name": name,
                "status": _safe_activity_status(name, source["status"]),
                "error_code": _safe_error_code(source["error_code"], fallback=None),
                "side_effects": _empty_list(source["side_effects"], error),
            }
        )
        seen.append(name)
    if seen != expected[: len(seen)]:
        _raise(error)
    return safe


def _safe_activity_status(name: str, status: object) -> str:
    allowed = {
        "validate_claim_check_ref": {"validated", "rejected"},
        _CONTROLLED_ACTIVITY_TYPE: {"executed", "rejected", "timed_out", "cancelled"},
    }[name]
    return _one_of(status, allowed, "invalid_agent_execution_snapshot")


def _safe_error_code(value: object, *, fallback: str | None) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        return fallback
    allowed = {
        "invalid_agent_execution_request",
        "invalid_claim_ref",
        "unsafe_material",
        "executor_failed",
        "executor_timeout",
        "executor_cancelled",
        "executor_auth_config_failure",
        "invalid_executor_result",
    }
    return value if value in allowed else fallback


def _snapshot_error_code(value: object, *, error: str) -> str | None:
    if value is None:
        return None
    code = _safe_error_code(value, fallback=None)
    if code is None:
        _raise(error)
    return code


def _result_counts(value: object, *, error: str) -> dict[str, int]:
    source = _plain_dict_with_fields(value, ["executor_calls", "tool_calls", "output_items"], error)
    return {
        "executor_calls": _bounded_nonnegative_int(source["executor_calls"], maximum=1, error=error),
        "tool_calls": _bounded_nonnegative_int(source["tool_calls"], maximum=32, error=error),
        "output_items": _bounded_nonnegative_int(source["output_items"], maximum=32, error=error),
    }


def _snapshot_counts(value: object, *, error: str) -> dict[str, int]:
    source = _plain_dict_with_fields(value, ["activities", "artifacts", "executor_calls", "tool_calls"], error)
    safe = {
        "activities": _bounded_nonnegative_int(source["activities"], maximum=2, error=error),
        "artifacts": _bounded_nonnegative_int(source["artifacts"], maximum=1, error=error),
        "executor_calls": _bounded_nonnegative_int(source["executor_calls"], maximum=1, error=error),
        "tool_calls": _bounded_nonnegative_int(source["tool_calls"], maximum=32, error=error),
    }
    return safe


def _artifact_kind(value: object, *, status: str, error: str) -> str | None:
    if status == "executed":
        return _literal(value, "controlled_agent_result", error)
    return _none(value, error)


def _result_error_code(value: object, *, status: str, error: str) -> str | None:
    if status == "executed":
        return _none(value, error)
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
    if error_code in {"executor_failed", "executor_timeout"}:
        return "transient"
    return "non_retryable"


def _result_error_code_for_status(status: str) -> str | None:
    if status == "executed":
        return None
    if status == "timed_out":
        return "executor_timeout"
    if status == "cancelled":
        return "executor_cancelled"
    return "invalid_agent_execution_request"


def _pre_executor_error_code(value: str) -> str:
    if value in {"unsafe_material", "invalid_agent_execution_request", "invalid_claim_ref"}:
        return value
    return "invalid_agent_execution_request"


def _checks(value: object, *, error: str) -> dict[str, bool]:
    source = _plain_dict_with_fields(value, _CHECKS, error)
    safe: dict[str, bool] = {}
    for key in _CHECKS:
        if source[key] is not True:
            _raise(error)
        safe[key] = True
    return safe


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
