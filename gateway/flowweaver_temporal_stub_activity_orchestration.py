"""FlowWeaver Phase 30 local Temporal stub Activity orchestration.

This module wraps the Phase 29 plain callable stubs as Temporal Activities and
provides a local/staging workflow plus caller-supplied-client start facade. It
keeps Gateway-owned lifecycle, production config, platform adapters, real agent
execution, real delivery, and ACK updates out of scope.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
from datetime import timedelta
from typing import Any

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

with workflow.unsafe.imports_passed_through():
    from gateway.flowweaver_stub_activity_implementation import (
        FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_CONTRACT_TYPE,
        FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE,
        FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT,
        describe_flowweaver_stub_activity_implementation_contract,
        deliver_artifact,
        execute_agent_turn,
        validate_claim_check_ref,
        validate_flowweaver_stub_activity_implementation_report,
    )

FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE = (
    "flowweaver.gateway.temporal_stub_activity_orchestration_contract.v0"
)
FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_REPORT_TYPE = (
    "flowweaver.gateway.temporal_stub_activity_orchestration_report.v0"
)
FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_START_PAYLOAD_TYPE = (
    "flowweaver.gateway.temporal_stub_activity_orchestration_start_payload.v0"
)
FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SNAPSHOT_TYPE = (
    "flowweaver.gateway.temporal_stub_activity_orchestration_snapshot.v0"
)
FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT = (
    "ready_for_controlled_agent_activity_implementation_request"
)
FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION = "flowweaver.temporal_stub_activity_orchestration.v0"
FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_TASK_QUEUE = "flowweaver-phase30-temporal-stub-activity"

_OPERATION = "start_or_reconcile_flowweaver_temporal_stub_activity_workflow"
_REPORT_OPERATION = "build_flowweaver_temporal_stub_activity_orchestration_report"
_ACTIVITY_TIMEOUT = timedelta(seconds=5)
_ACTIVITY_SEQUENCE = ["validate_claim_check_ref", "execute_agent_turn", "deliver_artifact"]
_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_contract",
    "consumes_report",
    "entrypoints",
    "workflow",
    "activity_wrappers",
    "start_payload_fields",
    "snapshot_fields",
    "report_fields",
    "activity_sequence",
    "runtime_policy",
    "retry_policy",
    "checks",
    "separate_approvals",
    "forbidden_side_effects",
    "side_effects",
]
_START_PAYLOAD_FIELDS = [
    "type",
    "version",
    "phase",
    "transaction_id",
    "workflow_id",
    "intent_id",
    "claim_check_ref",
    "claim_policy",
    "artifact_ref",
    "delivery_ref",
    "execution_mode",
    "execution_digest",
    "activity_sequence",
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
    "activity_sequence",
    "counts",
    "execution_digest",
    "retry_policy",
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
    "phase29_verdict",
    "workflow",
    "activity_sequence",
    "local_run_status",
    "history_no_leak_checked",
    "snapshot_no_leak_checked",
    "duplicate_start_reconciled",
    "checks",
    "error_code",
    "side_effects",
]
_ERROR_REPORT_FIELDS = ["type", "version", "phase", "ok", "operation", "error_code", "side_effects"]
_ENTRYPOINTS = [
    "describe_flowweaver_temporal_stub_activity_orchestration_contract",
    "build_flowweaver_temporal_stub_activity_start_payload",
    "validate_flowweaver_temporal_stub_activity_start_payload",
    "validate_flowweaver_temporal_stub_activity_snapshot",
    "start_or_reconcile_flowweaver_temporal_stub_activity_workflow",
    "build_flowweaver_temporal_stub_activity_orchestration_report",
    "validate_flowweaver_temporal_stub_activity_orchestration_report",
]
_ACTIVITY_WRAPPERS = [
    {
        "name": "validate_claim_check_ref",
        "wrapper": "validate_claim_check_ref_activity",
        "calls_plain_stub": "validate_claim_check_ref",
        "side_effects": [],
    },
    {
        "name": "execute_agent_turn",
        "wrapper": "execute_agent_turn_activity",
        "calls_plain_stub": "execute_agent_turn",
        "side_effects": [],
    },
    {
        "name": "deliver_artifact",
        "wrapper": "deliver_artifact_activity",
        "calls_plain_stub": "deliver_artifact",
        "side_effects": [],
    },
]
_RUNTIME_POLICY = {
    "mode": "local_staging_temporal_stub_activity_orchestration_only",
    "gateway_worker_lifecycle": "forbidden",
    "client_connection_ownership": "caller_supplied_only",
    "worker_environment_ownership": "tests_only",
    "agent_tool_execution": "forbidden_until_phase31",
    "delivery_execution_ack": "forbidden_until_phase32",
    "raw_material_policy": "claim_check_refs_and_safe_ids_only",
    "side_effects": [],
}
_RETRY_POLICY_DESCRIPTOR = {
    "start_to_close_timeout_seconds": 5,
    "maximum_attempts": 2,
    "non_retryable_error_types": [
        "invalid_start_payload",
        "invalid_claim_ref",
        "invalid_agent_activity_input",
        "invalid_delivery_activity_input",
        "unsafe_material",
    ],
}
_ACTIVITY_RETRY_POLICY = RetryPolicy(
    maximum_attempts=2,
    non_retryable_error_types=list(_RETRY_POLICY_DESCRIPTOR["non_retryable_error_types"]),
)
_CHECKS = [
    "phase29_contract_valid",
    "phase29_report_valid",
    "temporal_activity_wrappers_defined",
    "workflow_executes_fixed_activity_sequence",
    "local_worker_harness_verified",
    "history_no_leak_verified",
    "snapshot_no_leak_verified",
    "duplicate_start_reconciliation_verified",
    "gateway_worker_lifecycle_absent",
    "side_effects_absent",
]
_SEPARATE_APPROVALS = [
    "controlled_agent_activity_implementation",
    "controlled_delivery_activity",
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "platform_adapter_mutation",
    "real_agent_tool_execution",
    "real_send_edit_render_callback_control",
    "delivery_ack_updates",
]
_FORBIDDEN_SIDE_EFFECTS = [
    "gateway_owned_worker_lifecycle",
    "client_connect_factory",
    "workflow_environment_factory",
    "gateway_hook_change",
    "gateway_adapter_access",
    "platform_adapter_mutation",
    "production_config_write",
    "gateway_restart",
    "subprocess",
    "socket",
    "docker",
    "daemon",
    "service_startup",
    "agent_execution",
    "tool_execution",
    "send",
    "edit",
    "render",
    "callback_control",
    "delivery_ack_update",
    "raw_material_persistence",
]
_CLAIM_POLICY = {
    "mode": "claim_check_refs_only",
    "allowed_kinds": ["agent_input"],
    "checksum_hint": "sha256_64_lower_hex",
    "side_effects": [],
}
_CLAIM_FIELDS = ["ref", "kind", "count", "size", "checksum_hint"]
_ACTIVITY_RESULT_FIELDS = ["activity", "status", "error_code", "side_effects"]
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


def describe_flowweaver_temporal_stub_activity_orchestration_contract() -> dict[str, object]:
    """Return the exact Phase 30 local Temporal stub orchestration descriptor."""

    return {
        "type": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION,
        "phase": "phase30",
        "verdict": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
        "scope": "local_temporal_stub_activity_orchestration",
        "consumes_contract": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_CONTRACT_TYPE,
        "consumes_report": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE,
        "entrypoints": list(_ENTRYPOINTS),
        "workflow": "FlowWeaverTemporalStubActivityWorkflow",
        "activity_wrappers": copy.deepcopy(_ACTIVITY_WRAPPERS),
        "start_payload_fields": list(_START_PAYLOAD_FIELDS),
        "snapshot_fields": list(_SNAPSHOT_FIELDS),
        "report_fields": list(_REPORT_FIELDS),
        "activity_sequence": list(_ACTIVITY_SEQUENCE),
        "runtime_policy": copy.deepcopy(_RUNTIME_POLICY),
        "retry_policy": copy.deepcopy(_RETRY_POLICY_DESCRIPTOR),
        "checks": list(_CHECKS),
        "separate_approvals": list(_SEPARATE_APPROVALS),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }


def build_flowweaver_temporal_stub_activity_start_payload(
    *,
    transaction_id: object,
    workflow_id: object,
    intent_id: object,
    claim_check_ref: object,
    artifact_ref: object,
    delivery_ref: object,
) -> dict[str, object]:
    """Build a safe Phase 30 start payload from refs and safe runtime ids."""

    if _contains_forbidden_material(
        {
            "transaction_id": transaction_id,
            "workflow_id": workflow_id,
            "intent_id": intent_id,
            "claim_check_ref": claim_check_ref,
            "artifact_ref": artifact_ref,
            "delivery_ref": delivery_ref,
        }
    ):
        _raise("invalid_start_payload")
    tx_id = _safe_identifier(transaction_id, prefix="runtime_tx_", error="invalid_start_payload")
    wf_id = _safe_identifier(workflow_id, prefix="runtime_tx_", error="invalid_start_payload")
    if wf_id != tx_id:
        _raise("invalid_start_payload")
    safe_intent_id = _safe_identifier(intent_id, prefix="runtime_intent_", error="invalid_start_payload")
    safe_claim = _validate_claim_ref(claim_check_ref, error="invalid_start_payload")
    safe_artifact_ref = _safe_identifier(artifact_ref, prefix="runtime_artifact_", error="invalid_start_payload")
    safe_delivery_ref = _safe_identifier(delivery_ref, prefix="runtime_delivery_", error="invalid_start_payload")
    digest = _execution_digest(
        transaction_id=tx_id,
        intent_id=safe_intent_id,
        claim_ref=str(safe_claim["ref"]),
        artifact_ref=safe_artifact_ref,
        delivery_ref=safe_delivery_ref,
    )
    payload = {
        "type": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_START_PAYLOAD_TYPE,
        "version": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION,
        "phase": "phase30",
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "intent_id": safe_intent_id,
        "claim_check_ref": safe_claim,
        "claim_policy": copy.deepcopy(_CLAIM_POLICY),
        "artifact_ref": safe_artifact_ref,
        "delivery_ref": safe_delivery_ref,
        "execution_mode": "local_temporal_stub_activity_orchestration",
        "execution_digest": digest,
        "activity_sequence": list(_ACTIVITY_SEQUENCE),
        "side_effects": [],
    }
    return validate_flowweaver_temporal_stub_activity_start_payload(payload)


def validate_flowweaver_temporal_stub_activity_start_payload(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 30 start payload copy."""

    error = "invalid_start_payload"
    if _contains_forbidden_material(value):
        _raise(error)
    source = _plain_dict_with_fields(value, _START_PAYLOAD_FIELDS, error)
    tx_id = _literal_safe_identifier(source["transaction_id"], prefix="runtime_tx_", error=error)
    wf_id = _literal_safe_identifier(source["workflow_id"], prefix="runtime_tx_", error=error)
    if wf_id != tx_id:
        _raise(error)
    safe_claim = _validate_claim_ref(source["claim_check_ref"], error=error)
    artifact_ref = _literal_safe_identifier(source["artifact_ref"], prefix="runtime_artifact_", error=error)
    delivery_ref = _literal_safe_identifier(source["delivery_ref"], prefix="runtime_delivery_", error=error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_START_PAYLOAD_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION, error),
        "phase": _literal(source["phase"], "phase30", error),
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "intent_id": _literal_safe_identifier(source["intent_id"], prefix="runtime_intent_", error=error),
        "claim_check_ref": safe_claim,
        "claim_policy": _exact_claim_policy(source["claim_policy"], error=error),
        "artifact_ref": artifact_ref,
        "delivery_ref": delivery_ref,
        "execution_mode": _literal(source["execution_mode"], "local_temporal_stub_activity_orchestration", error),
        "execution_digest": _digest(source["execution_digest"], error=error),
        "activity_sequence": _exact_string_list(source["activity_sequence"], _ACTIVITY_SEQUENCE, error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    expected_digest = _execution_digest(
        transaction_id=safe["transaction_id"],
        intent_id=safe["intent_id"],
        claim_ref=str(safe_claim["ref"]),
        artifact_ref=artifact_ref,
        delivery_ref=delivery_ref,
    )
    if safe["execution_digest"] != expected_digest:
        _raise(error)
    return safe


def validate_flowweaver_temporal_stub_activity_snapshot(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 30 workflow snapshot copy."""

    error = "invalid_temporal_stub_activity_snapshot"
    if _contains_forbidden_material(value):
        _raise(error)
    source = _plain_dict_with_fields(value, _SNAPSHOT_FIELDS, error)
    tx_id = _literal_safe_identifier(source["transaction_id"], prefix="runtime_tx_", error=error)
    wf_id = _literal_safe_identifier(source["workflow_id"], prefix="runtime_tx_", error=error)
    if wf_id != tx_id:
        _raise(error)
    activity_sequence = _activity_sequence(source["activity_sequence"], error=error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SNAPSHOT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION, error),
        "phase": _literal(source["phase"], "phase30", error),
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "status": _one_of(
            source["status"],
            {"created", "running", "stub_sequence_completed", "cancelled", "rejected"},
            error,
        ),
        "intent_statuses": _intent_statuses(source["intent_statuses"], error=error),
        "artifact_refs": _safe_identifier_list(source["artifact_refs"], prefix="runtime_artifact_", error=error),
        "delivery_refs": _safe_identifier_list(source["delivery_refs"], prefix="runtime_delivery_", error=error),
        "activity_sequence": activity_sequence,
        "counts": _counts(source["counts"], error=error),
        "execution_digest": _digest(source["execution_digest"], error=error),
        "retry_policy": _retry_policy(source["retry_policy"], error=error),
        "error_code": _snapshot_error_code(source["error_code"], error=error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    return safe


def validate_flowweaver_temporal_stub_activity_orchestration_report(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 30 report copy."""

    error = "invalid_temporal_stub_activity_orchestration_report"
    if _contains_forbidden_material(value):
        _raise(error)
    if type(value) is dict and _keys_match_exactly(value, _ERROR_REPORT_FIELDS):
        return _validate_error_report(value, error=error)
    source = _plain_dict_with_fields(value, _REPORT_FIELDS, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION, error),
        "phase": _literal(source["phase"], "phase30", error),
        "ok": _true(source["ok"], error),
        "verdict": _literal(source["verdict"], FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT, error),
        "operation": _literal(source["operation"], _REPORT_OPERATION, error),
        "phase29_verdict": _literal(
            source["phase29_verdict"],
            FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT,
            error,
        ),
        "workflow": _literal(source["workflow"], "FlowWeaverTemporalStubActivityWorkflow", error),
        "activity_sequence": _exact_string_list(source["activity_sequence"], _ACTIVITY_SEQUENCE, error),
        "local_run_status": _one_of(source["local_run_status"], {"started", "duplicate"}, error),
        "history_no_leak_checked": _true(source["history_no_leak_checked"], error),
        "snapshot_no_leak_checked": _true(source["snapshot_no_leak_checked"], error),
        "duplicate_start_reconciled": _bool(source["duplicate_start_reconciled"], error),
        "checks": _checks(source["checks"], error=error),
        "error_code": _none(source["error_code"], error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    return safe


def build_flowweaver_temporal_stub_activity_orchestration_report(
    *, implementation_descriptor: object, implementation_report: object, local_run_result: object
) -> dict[str, object]:
    """Build Phase 30 metadata after a sanitized local/staging run result."""

    try:
        _assert_exact(
            implementation_descriptor,
            describe_flowweaver_stub_activity_implementation_contract(),
            "invalid_phase29_stub_activity_implementation_contract",
        )
        phase29 = validate_flowweaver_stub_activity_implementation_report(implementation_report)
        _literal(
            phase29.get("verdict"),
            FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT,
            "invalid_phase29_stub_activity_implementation_report",
        )
        local = _validate_local_run_result(local_run_result)
    except ValueError as exc:
        code = str(exc)
        if code not in {
            "invalid_phase29_stub_activity_implementation_contract",
            "invalid_phase29_stub_activity_implementation_report",
            "invalid_local_temporal_stub_activity_run_result",
        }:
            code = "invalid_local_temporal_stub_activity_run_result"
        return _error_report(code)
    report = {
        "type": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_REPORT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION,
        "phase": "phase30",
        "ok": True,
        "verdict": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
        "operation": _REPORT_OPERATION,
        "phase29_verdict": phase29["verdict"],
        "workflow": "FlowWeaverTemporalStubActivityWorkflow",
        "activity_sequence": list(_ACTIVITY_SEQUENCE),
        "local_run_status": local["status"],
        "history_no_leak_checked": True,
        "snapshot_no_leak_checked": True,
        "duplicate_start_reconciled": local["status"] == "duplicate",
        "checks": {key: True for key in _CHECKS},
        "error_code": None,
        "side_effects": [],
    }
    return validate_flowweaver_temporal_stub_activity_orchestration_report(report)


@activity.defn(name="validate_claim_check_ref")
async def validate_claim_check_ref_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal Activity wrapper for the Phase 29 claim-check stub."""

    if _contains_forbidden_material(payload):
        return _claim_result(status="rejected", claim_ref=None, error_code="unsafe_material")
    try:
        source = _plain_dict_with_fields(payload, ["claim_check_ref", "policy_descriptor"], "invalid_claim_ref")
        claim = _validate_claim_ref(source["claim_check_ref"], error="invalid_claim_ref")
        policy = _exact_claim_policy(source["policy_descriptor"], error="invalid_claim_ref")
    except ValueError:
        return _claim_result(status="rejected", claim_ref=None, error_code="invalid_claim_ref")
    return validate_claim_check_ref(claim_check_ref=claim, policy_descriptor=policy)


@activity.defn(name="execute_agent_turn")
async def execute_agent_turn_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal Activity wrapper for the Phase 29 agent-turn stub."""

    if _contains_forbidden_material(payload):
        return _agent_result(status="rejected", artifact_ref=None, error_code="unsafe_material")
    try:
        source = _plain_dict_with_fields(payload, ["execution_request", "validated_claim"], "invalid_agent_activity_input")
        request = _canonical_execution_request(source["execution_request"])
        claim = _canonical_validated_claim(source["validated_claim"])
    except ValueError as exc:
        code = "unsafe_material" if str(exc) == "unsafe_material" else "invalid_agent_activity_input"
        return _agent_result(status="rejected", artifact_ref=None, error_code=code)
    return execute_agent_turn(execution_request=request, validated_claim=claim)


@activity.defn(name="deliver_artifact")
async def deliver_artifact_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal Activity wrapper for the Phase 29 delivery stub."""

    if _contains_forbidden_material(payload):
        return _delivery_result(status="rejected", delivery_ref=None, error_code="unsafe_material")
    try:
        source = _plain_dict_with_fields(payload, ["artifact", "delivery_plan"], "invalid_delivery_activity_input")
        artifact = _canonical_artifact(source["artifact"])
        plan = _canonical_delivery_plan(source["delivery_plan"])
    except ValueError as exc:
        code = "unsafe_material" if str(exc) == "unsafe_material" else "invalid_delivery_activity_input"
        return _delivery_result(status="rejected", delivery_ref=None, error_code=code)
    return deliver_artifact(artifact=artifact, delivery_plan=plan)


@workflow.defn
class FlowWeaverTemporalStubActivityWorkflow:
    """Local/staging workflow that schedules the three Phase 29 stubs in order."""

    def __init__(self) -> None:
        self._transaction_id = "runtime_tx_uninitialized"
        self._workflow_id = "runtime_tx_uninitialized"
        self._status = "created"
        self._intent_statuses: dict[str, str] = {}
        self._artifact_refs: list[str] = []
        self._delivery_refs: list[str] = []
        self._activity_sequence: list[dict[str, Any]] = []
        self._execution_digest = "sha256:" + ("0" * 64)
        self._error_code: str | None = None
        self._terminal = False

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        start_payload = validate_flowweaver_temporal_stub_activity_start_payload(payload)
        self._transaction_id = str(start_payload["transaction_id"])
        self._workflow_id = str(start_payload["workflow_id"])
        intent_id = str(start_payload["intent_id"])
        self._status = "running"
        self._intent_statuses = {intent_id: "running"}
        self._artifact_refs = []
        self._delivery_refs = []
        self._activity_sequence = []
        self._execution_digest = str(start_payload["execution_digest"])
        self._error_code = None

        claim_result = await workflow.execute_activity(
            validate_claim_check_ref_activity,
            {
                "claim_check_ref": start_payload["claim_check_ref"],
                "policy_descriptor": start_payload["claim_policy"],
            },
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY_POLICY,
        )
        self._record_activity_result("validate_claim_check_ref", claim_result)
        if claim_result.get("status") != "validated":
            self._status = "rejected"
            self._error_code = _safe_error_code(claim_result.get("error_code"), fallback="invalid_claim_ref")
            self._terminal = True
            return self._snapshot()

        agent_result = await workflow.execute_activity(
            execute_agent_turn_activity,
            {
                "execution_request": {
                    "transaction_id": start_payload["transaction_id"],
                    "workflow_id": start_payload["workflow_id"],
                    "intent_id": start_payload["intent_id"],
                    "input_ref": claim_result["claim_ref"],
                    "artifact_ref": start_payload["artifact_ref"],
                    "execution_mode": "stub_activity_implementation",
                },
                "validated_claim": claim_result,
            },
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY_POLICY,
        )
        self._record_activity_result("execute_agent_turn", agent_result)
        if agent_result.get("status") != "stubbed":
            self._status = "rejected"
            self._error_code = _safe_error_code(agent_result.get("error_code"), fallback="invalid_agent_activity_input")
            self._terminal = True
            return self._snapshot()

        self._intent_statuses[intent_id] = "stubbed"
        artifact_ref = str(agent_result["artifact_ref"])
        self._artifact_refs = [artifact_ref]
        delivery_result = await workflow.execute_activity(
            deliver_artifact_activity,
            {
                "artifact": {"artifact_ref": artifact_ref, "kind": "stub_agent_result", "status": "stubbed"},
                "delivery_plan": {
                    "transaction_id": start_payload["transaction_id"],
                    "workflow_id": start_payload["workflow_id"],
                    "delivery_ref": start_payload["delivery_ref"],
                    "artifact_ref": artifact_ref,
                    "surface": "final_text",
                },
            },
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY_POLICY,
        )
        self._record_activity_result("deliver_artifact", delivery_result)
        if delivery_result.get("status") != "planned":
            self._status = "rejected"
            self._error_code = _safe_error_code(delivery_result.get("error_code"), fallback="invalid_delivery_activity_input")
            self._terminal = True
            return self._snapshot()

        self._delivery_refs = [str(delivery_result["delivery_ref"])]
        self._status = "stub_sequence_completed"
        await workflow.wait_condition(lambda: self._terminal)
        return self._snapshot()

    @workflow.query
    def query_snapshot(self) -> dict[str, Any]:
        return self._snapshot()

    @workflow.update
    async def cancel(self, event_id: str) -> dict[str, Any]:
        _safe_identifier(event_id, prefix="runtime_event_", error="invalid_cancel_event")
        self._status = "cancelled"
        self._terminal = True
        return self._snapshot()

    @cancel.validator
    def validate_cancel(self, event_id: str) -> None:
        _safe_identifier(event_id, prefix="runtime_event_", error="invalid_cancel_event")

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
            "type": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SNAPSHOT_TYPE,
            "version": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION,
            "phase": "phase30",
            "transaction_id": self._transaction_id,
            "workflow_id": self._workflow_id,
            "status": self._status,
            "intent_statuses": dict(sorted(self._intent_statuses.items())),
            "artifact_refs": list(self._artifact_refs),
            "delivery_refs": list(self._delivery_refs),
            "activity_sequence": [dict(item) for item in self._activity_sequence],
            "counts": {
                "activities": len(self._activity_sequence),
                "artifacts": len(self._artifact_refs),
                "deliveries": len(self._delivery_refs),
            },
            "execution_digest": self._execution_digest,
            "retry_policy": copy.deepcopy(_RETRY_POLICY_DESCRIPTOR),
            "error_code": self._error_code,
            "side_effects": [],
        }
        return validate_flowweaver_temporal_stub_activity_snapshot(snapshot)


async def start_or_reconcile_flowweaver_temporal_stub_activity_workflow(
    *, temporal_client: Any, start_payload: object, task_queue: object
) -> dict[str, object]:
    """Start or idempotently reconcile a Phase 30 local/staging workflow.

    The client is caller-supplied; this helper never connects clients or owns a
    runtime process. Duplicate start is accepted only after querying a sanitized
    existing snapshot and comparing workflow-observable safe fields.
    """

    try:
        payload = validate_flowweaver_temporal_stub_activity_start_payload(start_payload)
        safe_task_queue = _literal(task_queue, FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_TASK_QUEUE, "invalid_task_queue")
    except ValueError:
        return _start_result(status="rejected", workflow_id=None, snapshot=None, error_code="invalid_start_payload", ok=False)

    workflow_id = str(payload["workflow_id"])
    try:
        handle = await temporal_client.start_workflow(
            FlowWeaverTemporalStubActivityWorkflow.run,
            payload,
            id=workflow_id,
            task_queue=safe_task_queue,
        )
        snapshot = await _query_snapshot_until(handle, status="stub_sequence_completed")
        return _start_result(status="started", workflow_id=workflow_id, snapshot=snapshot, error_code=None, ok=True)
    except Exception as exc:  # Temporal wraps duplicate-start differently across versions/transports.
        if not _is_workflow_already_started_error(exc):
            return _start_result(status="rejected", workflow_id=workflow_id, snapshot=None, error_code="temporal_start_failed", ok=False)

    handle = temporal_client.get_workflow_handle(workflow_id)
    try:
        snapshot = await _query_snapshot_until(handle, status="stub_sequence_completed")
    except Exception:
        return _start_result(status="rejected", workflow_id=workflow_id, snapshot=None, error_code="duplicate_start_snapshot_unavailable", ok=False)
    if _snapshot_matches_payload(snapshot, payload):
        return _start_result(status="duplicate", workflow_id=workflow_id, snapshot=snapshot, error_code=None, ok=True)
    return _start_result(status="rejected", workflow_id=workflow_id, snapshot=None, error_code="duplicate_start_payload_mismatch", ok=False)


def cancel_stub_activity_orchestration() -> str:
    """Return the approved update name for cancelling the local Phase 30 workflow."""

    return "cancel"


async def _query_snapshot_until(handle: Any, *, status: str) -> dict[str, object]:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            snapshot = await handle.query(FlowWeaverTemporalStubActivityWorkflow.query_snapshot)
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.05)
            continue
        safe = validate_flowweaver_temporal_stub_activity_snapshot(snapshot)
        if safe["status"] == status:
            return safe
        await asyncio.sleep(0.05)
    if last_error is not None:
        raise last_error
    _raise("snapshot_unavailable")


def _start_result(
    *, status: str, workflow_id: str | None, snapshot: dict[str, object] | None, error_code: str | None, ok: bool
) -> dict[str, object]:
    return {
        "ok": ok,
        "operation": _OPERATION,
        "status": status,
        "workflow_id": workflow_id,
        "snapshot": copy.deepcopy(snapshot),
        "error_code": error_code,
        "side_effects": [],
    }


def _validate_local_run_result(value: object) -> dict[str, object]:
    error = "invalid_local_temporal_stub_activity_run_result"
    source = _plain_dict_with_fields(
        value,
        ["ok", "operation", "status", "workflow_id", "snapshot", "error_code", "side_effects"],
        error,
    )
    if source["ok"] is not True:
        _raise(error)
    safe = {
        "ok": True,
        "operation": _literal(source["operation"], _OPERATION, error),
        "status": _one_of(source["status"], {"started", "duplicate"}, error),
        "workflow_id": _literal_safe_identifier(source["workflow_id"], prefix="runtime_tx_", error=error),
        "snapshot": validate_flowweaver_temporal_stub_activity_snapshot(source["snapshot"]),
        "error_code": _none(source["error_code"], error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    if safe["workflow_id"] != safe["snapshot"]["workflow_id"]:
        _raise(error)
    return safe


def _snapshot_matches_payload(snapshot: dict[str, object], payload: dict[str, object]) -> bool:
    return (
        snapshot.get("transaction_id") == payload.get("transaction_id")
        and snapshot.get("workflow_id") == payload.get("workflow_id")
        and snapshot.get("execution_digest") == payload.get("execution_digest")
        and snapshot.get("activity_sequence")
        == [
            {"name": "validate_claim_check_ref", "status": "validated", "error_code": None, "side_effects": []},
            {"name": "execute_agent_turn", "status": "stubbed", "error_code": None, "side_effects": []},
            {"name": "deliver_artifact", "status": "planned", "error_code": None, "side_effects": []},
        ]
    )


def _is_workflow_already_started_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    for _ in range(6):
        if current is None:
            return False
        if isinstance(current, WorkflowAlreadyStartedError):
            return True
        name = type(current).__name__
        if name == "WorkflowAlreadyStartedError":
            return True
        current = current.__cause__ if current.__cause__ is not None else current.__context__
    return False


def _validate_error_report(value: dict[str, object], *, error: str) -> dict[str, object]:
    source = _plain_dict_with_fields(value, _ERROR_REPORT_FIELDS, error)
    return {
        "type": _literal(source["type"], FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION, error),
        "phase": _literal(source["phase"], "phase30", error),
        "ok": _false(source["ok"], error),
        "operation": _literal(source["operation"], _REPORT_OPERATION, error),
        "error_code": _one_of(
            source["error_code"],
            {
                "invalid_phase29_stub_activity_implementation_contract",
                "invalid_phase29_stub_activity_implementation_report",
                "invalid_local_temporal_stub_activity_run_result",
            },
            error,
        ),
        "side_effects": _empty_list(source["side_effects"], error),
    }


def _error_report(error_code: str) -> dict[str, object]:
    return {
        "type": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_REPORT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION,
        "phase": "phase30",
        "ok": False,
        "operation": _REPORT_OPERATION,
        "error_code": error_code,
        "side_effects": [],
    }


def _claim_result(*, status: str, claim_ref: str | None, error_code: str | None) -> dict[str, object]:
    return {"activity": "validate_claim_check_ref", "status": status, "claim_ref": claim_ref, "error_code": error_code, "side_effects": []}


def _agent_result(*, status: str, artifact_ref: str | None, error_code: str | None) -> dict[str, object]:
    return {"activity": "execute_agent_turn", "status": status, "artifact_ref": artifact_ref, "error_code": error_code, "side_effects": []}


def _delivery_result(*, status: str, delivery_ref: str | None, error_code: str | None) -> dict[str, object]:
    return {"activity": "deliver_artifact", "status": status, "delivery_ref": delivery_ref, "error_code": error_code, "side_effects": []}


def _canonical_execution_request(value: object) -> dict[str, object]:
    error = "invalid_agent_activity_input"
    if _contains_forbidden_material(value):
        _raise("unsafe_material")
    source = _plain_dict_with_fields(
        value,
        ["transaction_id", "workflow_id", "intent_id", "input_ref", "artifact_ref", "execution_mode"],
        error,
    )
    tx_id = _literal_safe_identifier(source["transaction_id"], prefix="runtime_tx_", error=error)
    wf_id = _literal_safe_identifier(source["workflow_id"], prefix="runtime_tx_", error=error)
    if wf_id != tx_id:
        _raise(error)
    return {
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "intent_id": _literal_safe_identifier(source["intent_id"], prefix="runtime_intent_", error=error),
        "input_ref": _literal_safe_identifier(source["input_ref"], prefix="claim_ref_", error=error),
        "artifact_ref": _literal_safe_identifier(source["artifact_ref"], prefix="runtime_artifact_", error=error),
        "execution_mode": _literal(source["execution_mode"], "stub_activity_implementation", error),
    }


def _canonical_validated_claim(value: object) -> dict[str, object]:
    error = "invalid_agent_activity_input"
    if _contains_forbidden_material(value):
        _raise("unsafe_material")
    source = _plain_dict_with_fields(value, ["activity", "status", "claim_ref", "error_code", "side_effects"], error)
    return {
        "activity": _literal(source["activity"], "validate_claim_check_ref", error),
        "status": _literal(source["status"], "validated", error),
        "claim_ref": _literal_safe_identifier(source["claim_ref"], prefix="claim_ref_", error=error),
        "error_code": _none(source["error_code"], error),
        "side_effects": _empty_list(source["side_effects"], error),
    }


def _canonical_artifact(value: object) -> dict[str, object]:
    error = "invalid_delivery_activity_input"
    if _contains_forbidden_material(value):
        _raise("unsafe_material")
    source = _plain_dict_with_fields(value, ["artifact_ref", "kind", "status"], error)
    return {
        "artifact_ref": _literal_safe_identifier(source["artifact_ref"], prefix="runtime_artifact_", error=error),
        "kind": _literal(source["kind"], "stub_agent_result", error),
        "status": _literal(source["status"], "stubbed", error),
    }


def _canonical_delivery_plan(value: object) -> dict[str, object]:
    error = "invalid_delivery_activity_input"
    if _contains_forbidden_material(value):
        _raise("unsafe_material")
    source = _plain_dict_with_fields(
        value,
        ["transaction_id", "workflow_id", "delivery_ref", "artifact_ref", "surface"],
        error,
    )
    tx_id = _literal_safe_identifier(source["transaction_id"], prefix="runtime_tx_", error=error)
    wf_id = _literal_safe_identifier(source["workflow_id"], prefix="runtime_tx_", error=error)
    if wf_id != tx_id:
        _raise(error)
    return {
        "transaction_id": tx_id,
        "workflow_id": wf_id,
        "delivery_ref": _literal_safe_identifier(source["delivery_ref"], prefix="runtime_delivery_", error=error),
        "artifact_ref": _literal_safe_identifier(source["artifact_ref"], prefix="runtime_artifact_", error=error),
        "surface": _literal(source["surface"], "final_text", error),
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


def _bool(value: object, error: str) -> bool:
    if type(value) is not bool:
        _raise(error)
    return value


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


def _digest(value: object, *, error: str) -> str:
    if type(value) is not str or not value.startswith("sha256:"):
        _raise(error)
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        _raise(error)
    return value


def _checksum_hint(value: object, error: str) -> str:
    return _digest(value, error=error)


def _execution_digest(*, transaction_id: str, intent_id: str, claim_ref: str, artifact_ref: str, delivery_ref: str) -> str:
    material = "|".join(("phase30", transaction_id, intent_id, claim_ref, artifact_ref, delivery_ref))
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _validate_claim_ref(value: object, *, error: str) -> dict[str, object]:
    source = _plain_dict_with_fields(value, _CLAIM_FIELDS, error)
    return {
        "ref": _literal_safe_identifier(source["ref"], prefix="claim_ref_", error=error),
        "kind": _literal(source["kind"], "agent_input", error),
        "count": _positive_int(source["count"], error),
        "size": _positive_int(source["size"], error),
        "checksum_hint": _checksum_hint(source["checksum_hint"], error),
    }


def _positive_int(value: object, error: str) -> int:
    if type(value) is not int or value <= 0:
        _raise(error)
    return value


def _exact_claim_policy(value: object, *, error: str) -> dict[str, object]:
    _assert_exact(value, _CLAIM_POLICY, error)
    return copy.deepcopy(_CLAIM_POLICY)


def _exact_string_list(value: object, expected: list[str], error: str) -> list[str]:
    if type(value) is not list or len(value) != len(expected):
        _raise(error)
    safe: list[str] = []
    for item, expected_item in zip(value, expected, strict=True):
        safe.append(_literal(item, expected_item, error))
    return safe


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
            {"running", "stubbed", "cancelled", "rejected"},
            error,
        )
    return dict(sorted(safe.items()))


def _activity_sequence(value: object, *, error: str) -> list[dict[str, object]]:
    if type(value) is not list or len(value) > 3:
        _raise(error)
    safe: list[dict[str, object]] = []
    seen: list[str] = []
    for item in value:
        source = _plain_dict_with_fields(item, ["name", "status", "error_code", "side_effects"], error)
        name = _one_of(source["name"], set(_ACTIVITY_SEQUENCE), error)
        if name in seen:
            _raise(error)
        status = _safe_activity_status(name, source["status"])
        safe.append(
            {
                "name": name,
                "status": status,
                "error_code": _safe_error_code(source["error_code"], fallback=None),
                "side_effects": _empty_list(source["side_effects"], error),
            }
        )
        seen.append(name)
    if seen != _ACTIVITY_SEQUENCE[: len(seen)]:
        _raise(error)
    return safe


def _safe_activity_status(name: str, status: object) -> str:
    allowed = {
        "validate_claim_check_ref": {"validated", "rejected"},
        "execute_agent_turn": {"stubbed", "rejected"},
        "deliver_artifact": {"planned", "rejected"},
    }[name]
    return _one_of(status, allowed, "invalid_temporal_stub_activity_snapshot")


def _safe_error_code(value: object, *, fallback: str | None) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        return fallback
    allowed = {
        "invalid_claim_ref",
        "noncanonical_claim_kind",
        "unsafe_material",
        "invalid_agent_activity_input",
        "agent_execution_not_approved",
        "invalid_delivery_activity_input",
        "delivery_execution_not_approved",
        "temporal_start_failed",
        "duplicate_start_snapshot_unavailable",
        "duplicate_start_payload_mismatch",
    }
    return value if value in allowed else fallback


def _counts(value: object, *, error: str) -> dict[str, int]:
    source = _plain_dict_with_fields(value, ["activities", "artifacts", "deliveries"], error)
    safe = {
        "activities": _nonnegative_int(source["activities"], error),
        "artifacts": _nonnegative_int(source["artifacts"], error),
        "deliveries": _nonnegative_int(source["deliveries"], error),
    }
    if safe["activities"] > 3 or safe["artifacts"] > 1 or safe["deliveries"] > 1:
        _raise(error)
    return safe


def _nonnegative_int(value: object, error: str) -> int:
    if type(value) is not int or value < 0:
        _raise(error)
    return value


def _retry_policy(value: object, *, error: str) -> dict[str, object]:
    _assert_exact(value, _RETRY_POLICY_DESCRIPTOR, error)
    return copy.deepcopy(_RETRY_POLICY_DESCRIPTOR)


def _snapshot_error_code(value: object, *, error: str) -> str | None:
    if value is None:
        return None
    code = _safe_error_code(value, fallback=None)
    if code is None:
        _raise(error)
    return code


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
