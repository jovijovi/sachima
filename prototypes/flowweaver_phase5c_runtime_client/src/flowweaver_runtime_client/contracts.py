"""Safe contracts for the FlowWeaver Phase 5C runtime client/tool boundary."""

from __future__ import annotations

from flowweaver_temporal_poc.payloads import (
    ALLOWED_DELIVERY_STATUSES,
    ACTIVITY_BOUNDARY_TYPE,
    CancelTransactionUpdate,
    DeliveryAckUpdate,
    HumanDecisionUpdate,
    START_SIGNATURE_TYPE,
    ResumeUserInputUpdate,
    RuntimeStartPayload,
    build_runtime_start_payload,
    validate_activity_boundary_summary,
    validate_runtime_signature_digest,
    validate_runtime_workflow_id as _phase5b_validate_workflow_id,
    validate_start_payload,
)

ALLOWED_OPERATIONS = (
    "start_transaction",
    "query_snapshot",
    "record_delivery_ack",
    "approve_intent",
    "reject_intent",
    "cancel_transaction",
    "resume_after_user_input",
)
ALLOWED_TOP_LEVEL_RESULT_FIELDS = {"ok", "operation", "workflow_id", "transaction_id", "status", "snapshot", "error_code"}
ALLOWED_SNAPSHOT_FIELDS = {
    "type",
    "version",
    "transaction_id",
    "status",
    "entry_count",
    "record_counts",
    "start_signature",
    "counts",
    "intent_statuses",
    "artifact_statuses",
    "delivery_statuses",
    "applied_event_count",
    "resume_count",
    "side_effects",
    "activity_boundary",
}
_ALLOWED_SNAPSHOT_STATUSES = ("created", "running", "waiting_for_user", "canceled", "completed", "failed")
_ALLOWED_INTENT_STATUSES = ("pending", "approved", "rejected", "canceled", "completed", "failed")
_ALLOWED_ARTIFACT_STATUSES = ("available", "planned", "published", "canceled", "failed")
_ALLOWED_DELIVERY_SNAPSHOT_STATUSES = ("planned",) + ALLOWED_DELIVERY_STATUSES
_ALLOWED_UPDATE_STATUSES = ("applied", "duplicate", "rejected")
_ALLOWED_ERROR_CODES = {
    "invalid_cancel_transaction_update",
    "invalid_claim_ref",
    "invalid_delivery_ack_update",
    "invalid_human_decision_update",
    "invalid_operation",
    "invalid_resume_user_input_update",
    "invalid_start_payload",
    "invalid_temporal_address",
    "invalid_workflow_id",
    "missing_required_field",
    "runtime_error",
    "temporal_address_required",
    "unsafe_output",
    "unsafe_request",
}
_UNSAFE_KEY_SUBSTRINGS = (
    "raw_",
    "tool_output",
    "platform_payload",
    "platform_id",
    "chat_id",
    "user_id",
    "message_id",
    "delivery_ack_payload",
    "credential",
    "password",
    "api_key",
    "bearer",
    "connection_string",
)
_UNSAFE_EXACT_KEYS = {"token", "secret"}
_UNSAFE_VALUE_MARKERS = (
    "unsafe-token",
    "sk-",
    "bearer ",
    "password" + "=",
    "secret" + "=",
    "api" + "_key=",
)
_PRIVATE_PREFIXES = ("om_", "oc_", "ou_", "chat_", "message_", "platform_", "feishu_", "lark_", "telegram_")
_SYNTHETIC_ID_FORBIDDEN_SUBSTRINGS = (
    "allowed_runtime_events",
    "claim_check_policy",
    "forbidden_material",
    "raw_",
    "tool_output",
    "platform_payload",
    "token",
    "secret",
    "password",
    "credential",
    "api_key",
    "bearer",
    "sk-",
)
_INVALID = object()


def validate_operation(operation: object) -> str:
    if type(operation) is not str or operation not in ALLOWED_OPERATIONS:
        _raise("invalid_operation")
    return operation


def validate_temporal_address(address: object) -> str:
    if address is None:
        _raise("temporal_address_required")
    if type(address) is not str or not address:
        _raise("invalid_temporal_address")
    if address.startswith("localhost:") or address.startswith("127.0.0.1:"):
        return address
    _raise("invalid_temporal_address")


def validate_workflow_id(workflow_id: object) -> str:
    if type(workflow_id) is not str:
        _raise("invalid_workflow_id")
    try:
        return _phase5b_validate_workflow_id(workflow_id)
    except ValueError:
        _raise("invalid_workflow_id")


def validate_claim_ref(claim_ref: object) -> str:
    return _synthetic_id(claim_ref, prefixes=("claim_ref_",), error="invalid_claim_ref")


def build_start_payload_from_safe_fields(fields: object) -> RuntimeStartPayload:
    safe = _plain_dict(fields, error="invalid_start_payload")
    _reject_unsafe_material(safe, error="invalid_start_payload", allow_claim_policy=True)
    expected = {
        "transaction_id",
        "idempotency_key",
        "entry_count",
        "record_counts",
        "allowed_runtime_events",
        "claim_check_policy",
    }
    if set(safe) != expected:
        _raise("invalid_start_payload")
    try:
        payload = build_runtime_start_payload(
            transaction_id=_expect_plain_string(safe["transaction_id"], error="invalid_start_payload"),
            idempotency_key=_synthetic_id(
                safe["idempotency_key"], prefixes=("runtime_event_",), error="invalid_start_payload"
            ),
            entry_count=_expect_plain_int(safe["entry_count"], error="invalid_start_payload"),
            record_counts=_plain_int_dict(safe["record_counts"], error="invalid_start_payload"),
            allowed_runtime_events=_plain_string_tuple(safe["allowed_runtime_events"], error="invalid_start_payload"),
            claim_check_policy=_claim_check_policy(safe["claim_check_policy"], error="invalid_start_payload"),
        )
        validate_start_payload(payload)
        return payload
    except ValueError:
        _raise("invalid_start_payload")


def sanitize_tool_request(request: object) -> dict[str, object]:
    safe = _plain_dict(request, error="unsafe_request")
    try:
        validate_operation(safe.get("operation"))
    except ValueError:
        _raise("invalid_operation")
    _reject_unsafe_material(safe, error="unsafe_request", allow_claim_policy=True)
    return safe


def make_success_result(
    *,
    operation: object,
    workflow_id: object | None = None,
    transaction_id: object | None = None,
    status: object | None = None,
    snapshot: object | None = None,
) -> dict[str, object]:
    safe_operation = validate_operation(operation)
    result: dict[str, object] = {"ok": True, "operation": safe_operation}
    safe_snapshot: dict[str, object] | None = None
    if workflow_id is not None:
        result["workflow_id"] = validate_workflow_id(workflow_id)
    if snapshot is not None:
        safe_snapshot = sanitize_snapshot(snapshot)
        result["snapshot"] = safe_snapshot
    if transaction_id is not None:
        result["transaction_id"] = validate_workflow_id(transaction_id)
    elif safe_snapshot is not None:
        result["transaction_id"] = safe_snapshot["transaction_id"]
    if status is not None:
        result["status"] = _safe_status_string(status, error="unsafe_tool_output")
    elif safe_snapshot is not None:
        result["status"] = safe_snapshot["status"]
    _assert_result_shape(result)
    return result


def make_update_success_result(*, operation: object, workflow_id: object, update_result: object) -> dict[str, object]:
    update = sanitize_update_result(update_result)
    result: dict[str, object] = {
        "ok": True,
        "operation": validate_operation(operation),
        "workflow_id": validate_workflow_id(workflow_id),
        "status": update["update_status"],
        "snapshot": update["snapshot"],
    }
    _assert_result_shape(result)
    return result


def make_error_result(*, operation: object | None, error_code: object) -> dict[str, object]:
    result: dict[str, object] = {"ok": False, "error_code": _safe_error_code(error_code)}
    if operation is not None:
        try:
            result["operation"] = validate_operation(operation)
        except ValueError:
            pass
    _assert_result_shape(result)
    return result


def sanitize_snapshot(snapshot: object) -> dict[str, object]:
    source = _plain_dict(snapshot, error="unsafe_tool_output")
    required = {
        "type",
        "version",
        "transaction_id",
        "status",
        "entry_count",
        "record_counts",
        "start_signature",
        "counts",
        "intent_statuses",
        "artifact_statuses",
        "delivery_statuses",
        "applied_event_count",
        "resume_count",
        "side_effects",
    }
    if not required.issubset(source):
        _raise("unsafe_tool_output")
    safe = {
        "type": _safe_literal_string(source["type"], allowed=("flowweaver.temporal_poc.snapshot.v0",), error="unsafe_tool_output"),
        "version": _safe_literal_string(source["version"], allowed=("flowweaver.temporal_poc.v0",), error="unsafe_tool_output"),
        "transaction_id": validate_workflow_id(source["transaction_id"]),
        "status": _safe_literal_string(source["status"], allowed=_ALLOWED_SNAPSHOT_STATUSES, error="unsafe_tool_output"),
        "entry_count": _expect_plain_int(source["entry_count"], error="unsafe_tool_output"),
        "record_counts": _record_counts(source["record_counts"], error="unsafe_tool_output"),
        "start_signature": _start_signature(source["start_signature"], error="unsafe_tool_output"),
        "counts": _counts(source["counts"], error="unsafe_tool_output"),
        "intent_statuses": _status_map(
            source["intent_statuses"], key_prefix="runtime_intent_", statuses=_ALLOWED_INTENT_STATUSES, error="unsafe_tool_output"
        ),
        "artifact_statuses": _status_map(
            source["artifact_statuses"], key_prefix="runtime_artifact_", statuses=_ALLOWED_ARTIFACT_STATUSES, error="unsafe_tool_output"
        ),
        "delivery_statuses": _status_map(
            source["delivery_statuses"],
            key_prefix="runtime_delivery_",
            statuses=_ALLOWED_DELIVERY_SNAPSHOT_STATUSES,
            error="unsafe_tool_output",
        ),
        "applied_event_count": _expect_plain_int(source["applied_event_count"], error="unsafe_tool_output"),
        "resume_count": _expect_plain_int(source["resume_count"], error="unsafe_tool_output"),
        "side_effects": _empty_list(source["side_effects"], error="unsafe_tool_output"),
    }
    if "activity_boundary" in source:
        activity_boundary = validate_activity_boundary_summary(source["activity_boundary"])
        if activity_boundary["type"] != ACTIVITY_BOUNDARY_TYPE:
            _raise("unsafe_tool_output")
        safe["activity_boundary"] = activity_boundary
    _assert_no_forbidden_rendered_material(safe, error="unsafe_tool_output")
    return safe


def sanitize_update_result(update_result: object) -> dict[str, object]:
    source = _plain_dict(update_result, error="unsafe_tool_output")
    required = {"type", "version", "update_status", "snapshot", "side_effects"}
    if not required.issubset(source):
        _raise("unsafe_tool_output")
    safe = {
        "type": _safe_literal_string(source["type"], allowed=("flowweaver.temporal_poc.update_result.v0",), error="unsafe_tool_output"),
        "version": _safe_literal_string(source["version"], allowed=("flowweaver.temporal_poc.v0",), error="unsafe_tool_output"),
        "update_status": _safe_literal_string(source["update_status"], allowed=_ALLOWED_UPDATE_STATUSES, error="unsafe_tool_output"),
        "snapshot": sanitize_snapshot(source["snapshot"]),
        "side_effects": _empty_list(source["side_effects"], error="unsafe_tool_output"),
    }
    _assert_no_forbidden_rendered_material(safe, error="unsafe_tool_output")
    return safe


def delivery_ack_from_tool_update(update: object) -> DeliveryAckUpdate:
    safe = sanitize_tool_request({"operation": "record_delivery_ack", "update": update})["update"]
    from flowweaver_temporal_poc.payloads import delivery_ack_from_safe_update

    return delivery_ack_from_safe_update(safe)


def human_decision_from_tool_update(update: object, *, operation: str) -> HumanDecisionUpdate:
    safe = sanitize_tool_request({"operation": operation, "update": update})["update"]
    from flowweaver_temporal_poc.payloads import human_decision_from_safe_update

    return human_decision_from_safe_update(safe)


def cancel_transaction_from_tool_update(update: object) -> CancelTransactionUpdate:
    safe = sanitize_tool_request({"operation": "cancel_transaction", "update": update})["update"]
    from flowweaver_temporal_poc.payloads import cancel_transaction_from_safe_update

    return cancel_transaction_from_safe_update(safe)


def resume_user_input_from_tool_update(update: object) -> ResumeUserInputUpdate:
    safe = sanitize_tool_request({"operation": "resume_after_user_input", "update": update})["update"]
    from flowweaver_temporal_poc.payloads import resume_user_input_from_safe_update

    return resume_user_input_from_safe_update(safe)


def _plain_copy(value: object) -> object:
    if value is None or type(value) in {str, bool, int, float}:
        return value
    if type(value) is list:
        copied_list: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_list.append(copied)
        return copied_list
    if type(value) is tuple:
        copied_tuple: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_tuple.append(copied)
        return copied_tuple
    if type(value) is dict:
        copied_dict: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                return _INVALID
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_dict[key] = copied
        return copied_dict
    return _INVALID


def _plain_dict(value: object, *, error: str) -> dict[str, object]:
    copied = _plain_copy(value)
    if type(copied) is not dict:
        _raise(error)
    return copied


def _plain_string_tuple(value: object, *, error: str) -> tuple[str, ...]:
    copied = _plain_copy(value)
    if type(copied) is not list or not all(type(item) is str for item in copied):
        _raise(error)
    return tuple(copied)


def _plain_int_dict(value: object, *, error: str) -> dict[str, int]:
    copied = _plain_dict(value, error=error)
    if not all(type(key) is str and type(item) is int for key, item in copied.items()):
        _raise(error)
    return {key: item for key, item in copied.items() if type(item) is int}


def _claim_check_policy(value: object, *, error: str) -> dict[str, object]:
    policy = _plain_dict(value, error=error)
    if set(policy) != {"mode", "allowed_reference_fields", "forbidden_material"}:
        _raise(error)
    return {
        "mode": _safe_literal_string(policy["mode"], allowed=("references_only",), error=error),
        "allowed_reference_fields": _plain_string_tuple(policy["allowed_reference_fields"], error=error),
        "forbidden_material": _plain_string_tuple(policy["forbidden_material"], error=error),
    }


def _expect_plain_string(value: object, *, error: str) -> str:
    if type(value) is not str:
        _raise(error)
    return value


def _expect_plain_int(value: object, *, error: str) -> int:
    if type(value) is not int:
        _raise(error)
    return value


def _empty_list(value: object, *, error: str) -> list[object]:
    copied = _plain_copy(value)
    if copied != []:
        _raise(error)
    return []


def _record_counts(value: object, *, error: str) -> dict[str, int]:
    counts = _plain_int_dict(value, error=error)
    if set(counts) != {"transactions", "intents", "artifacts", "deliveries"}:
        _raise(error)
    return {key: counts[key] for key in ("transactions", "intents", "artifacts", "deliveries")}


def _counts(value: object, *, error: str) -> dict[str, int]:
    counts = _plain_int_dict(value, error=error)
    if set(counts) != {"intents", "artifacts", "deliveries"}:
        _raise(error)
    return {key: counts[key] for key in ("intents", "artifacts", "deliveries")}


def _start_signature(value: object, *, error: str) -> dict[str, object]:
    signature = _plain_dict(value, error=error)
    expected = {"type", "version", "idempotency_key", "event_contract_digest", "claim_policy_digest"}
    if set(signature) != expected:
        _raise(error)
    safe = {
        "type": _safe_literal_string(signature["type"], allowed=(START_SIGNATURE_TYPE,), error=error),
        "version": _safe_literal_string(signature["version"], allowed=("flowweaver.temporal_poc.v0",), error=error),
        "idempotency_key": _synthetic_id(signature["idempotency_key"], prefixes=("runtime_event_",), error=error),
        "event_contract_digest": validate_runtime_signature_digest(signature["event_contract_digest"], error=error),
        "claim_policy_digest": validate_runtime_signature_digest(signature["claim_policy_digest"], error=error),
    }
    _assert_no_forbidden_rendered_material(safe, error=error)
    return safe


def _status_map(value: object, *, key_prefix: str, statuses: tuple[str, ...], error: str) -> dict[str, str]:
    mapping = _plain_dict(value, error=error)
    safe: dict[str, str] = {}
    for key, status in mapping.items():
        _synthetic_id(key, prefixes=(key_prefix,), error=error)
        safe[key] = _safe_literal_string(status, allowed=statuses, error=error)
    return dict(sorted(safe.items()))


def _safe_status_string(value: object, *, error: str) -> str:
    if type(value) is not str or not value:
        _raise(error)
    _assert_no_forbidden_rendered_material(value, error=error)
    return value


def _safe_literal_string(value: object, *, allowed: tuple[str, ...], error: str) -> str:
    if type(value) is not str or value not in allowed:
        _raise(error)
    return value


def _safe_error_code(error_code: object) -> str:
    if type(error_code) is not str or not error_code:
        return "runtime_error"
    if error_code == "unsafe_tool_output":
        return "unsafe_output"
    if error_code in _ALLOWED_ERROR_CODES:
        return error_code
    return "runtime_error"


def _synthetic_id(value: object, *, prefixes: tuple[str, ...], error: str) -> str:
    if type(value) is not str or not value or len(value) > 128:
        _raise(error)
    if not value.startswith(prefixes):
        _raise(error)
    lowered = value.lower()
    body_prefix = next((prefix for prefix in prefixes if lowered.startswith(prefix)), "")
    body = lowered[len(body_prefix) :]
    if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
        _raise(error)
    if any(marker in body for marker in ("om_", "oc_", "ou_", "chat", "message", "platform", "feishu", "lark", "telegram", "private")):
        _raise(error)
    if any(marker in lowered for marker in _SYNTHETIC_ID_FORBIDDEN_SUBSTRINGS):
        _raise(error)
    if not all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in value):
        _raise(error)
    return value


def _reject_unsafe_material(value: object, *, error: str, allow_claim_policy: bool = False, path: tuple[str, ...] = ()) -> None:
    if allow_claim_policy and path == ("claim_check_policy", "forbidden_material"):
        return
    if type(value) is dict:
        for key, item in value.items():
            lowered = key.lower()
            if not (allow_claim_policy and path == ("claim_check_policy",) and key == "forbidden_material"):
                if lowered in _UNSAFE_EXACT_KEYS or any(marker in lowered for marker in _UNSAFE_KEY_SUBSTRINGS):
                    _raise(error)
            _reject_unsafe_material(item, error=error, allow_claim_policy=allow_claim_policy, path=path + (key,))
        return
    if type(value) is list:
        for item in value:
            _reject_unsafe_material(item, error=error, allow_claim_policy=allow_claim_policy, path=path)
        return
    if type(value) is str:
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
            _raise(error)
        if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
            _raise(error)


def _assert_result_shape(result: dict[str, object]) -> None:
    if not set(result) <= ALLOWED_TOP_LEVEL_RESULT_FIELDS:
        _raise("unsafe_tool_output")
    _assert_no_forbidden_rendered_material(result, error="unsafe_tool_output")


def _assert_no_forbidden_rendered_material(value: object, *, error: str) -> None:
    rendered = repr(value).lower()
    forbidden = (
        "allowed_runtime_events",
        "claim_check_policy",
        "forbidden_material",
        "raw_payload",
        "raw_capture",
        "raw_prompt",
        "raw_command",
        "tool_output",
        "platform_payload",
        "platform_id",
        "chat_id",
        "user_id",
        "message_id",
        "delivery_ack_payload",
        "oc_private",
        "ou_private",
        "om_private",
        "unsafe-token",
        "sk-",
        "bearer ",
    )
    if any(marker in rendered for marker in forbidden):
        _raise(error)


def _raise(error: str) -> None:
    raise ValueError(error) from None


__all__ = [
    "ALLOWED_OPERATIONS",
    "ALLOWED_TOP_LEVEL_RESULT_FIELDS",
    "build_start_payload_from_safe_fields",
    "cancel_transaction_from_tool_update",
    "delivery_ack_from_tool_update",
    "human_decision_from_tool_update",
    "make_error_result",
    "make_success_result",
    "make_update_success_result",
    "resume_user_input_from_tool_update",
    "sanitize_snapshot",
    "sanitize_tool_request",
    "sanitize_update_result",
    "validate_claim_ref",
    "validate_operation",
    "validate_temporal_address",
    "validate_workflow_id",
]
