"""Default-off FlowWeaver Gateway observation to Temporal bridge."""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any

FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION = "flowweaver.temporal_observation_bridge.v0"
TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE = "flowweaver.gateway.temporal_observation_bridge_result.v0"
TEMPORAL_OBSERVATION_BRIDGE_POLICY_TYPE = "flowweaver.gateway.temporal_observation_bridge_policy.v0"
TEMPORAL_OBSERVATION_TYPE = "flowweaver.gateway.temporal_observation.v0"
TEMPORAL_OBSERVATION_VERSION = "flowweaver.gateway.temporal_observation.v0"
TEMPORAL_OBSERVATION_SUCCESS_VERDICT = "ready_for_guarded_temporal_observation_validation"

_OPERATION = "observe_gateway_turn_for_flowweaver_temporal"
_POLICY_FIELDS = {
    "type",
    "enabled",
    "mode",
    "allow_runtime_start",
    "allow_runtime_query",
    "side_effects",
}
_OBSERVATION_FIELDS = {
    "type",
    "version",
    "source",
    "session_label",
    "turn_label",
    "turn_discriminator",
    "entry_count",
    "record_counts",
    "claim_refs",
    "surfaces",
    "checks",
    "side_effects",
}
_RECORD_COUNT_KEYS = {"transactions", "intents", "artifacts", "deliveries"}
_CLAIM_REF_KEYS = {"input_ref", "artifact_ref", "delivery_ref"}
_CHECK_KEYS = {"payloads_absent", "claim_check_refs_only", "side_effects_absent", "source_ids_sanitized"}
_ALLOWED_SURFACES = ("final_text", "rich_card", "progress_card", "media")
_ALLOWED_RUNTIME_EVENTS = [
    "start_transaction",
    "record_operation",
    "publish_artifact",
    "plan_delivery",
    "record_delivery_ack",
    "approve_intent",
    "reject_intent",
    "cancel_transaction",
    "resume_after_user_input",
]
_CLAIM_CHECK_POLICY = {
    "mode": "references_only",
    "allowed_reference_fields": ["ref", "kind", "count", "size", "checksum_hint"],
    "forbidden_material": [
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
        "token",
        "secret",
    ],
}
_SNAPSHOT_REQUIRED_FIELDS = {
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
_ALLOWED_SNAPSHOT_STATUSES = ("created", "running", "waiting_for_user", "canceled", "completed", "failed")
_RESULT_FIELDS = {
    "type",
    "version",
    "ok",
    "verdict",
    "operation",
    "workflow_id",
    "transaction_id",
    "status",
    "start_status",
    "query_status",
    "runtime_call_counts",
    "snapshot_summary",
    "checks",
    "error_code",
    "side_effects",
}
_UNSAFE_KEY_SUBSTRINGS = (
    "raw_",
    "tool_output",
    "card_json",
    "media_path",
    "media_bytes",
    "platform_payload",
    "platform_id",
    "chat_id",
    "user_id",
    "message_id",
    "delivery_ack_payload",
    "callback",
    "credential",
    "password",
    "api_key",
    "bearer",
    "connection_string",
)
_UNSAFE_EXACT_KEYS = {"token", "secret"}
_PRIVATE_PREFIXES = ("om_", "oc_", "ou_", "chat_", "message_", "platform_", "feishu_", "lark_", "telegram_")
_UNSAFE_VALUE_MARKERS = (
    "unsafe-" + "token",
    "sk" + "-",
    "bearer ",
    "password" + "=",
    "secret" + "=",
    "api" + "_key=",
    "traceback",
    "exception",
    "valueerror:",
    "runtimeerror:",
    "callback payload",
)
_SYNTHETIC_FORBIDDEN_SUBSTRINGS = (
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
    "sk" + "-",
)
_INVALID = object()


async def observe_gateway_turn_for_flowweaver_temporal(
    *,
    observation: object,
    runtime_control_surface: object,
    bridge_policy: object,
) -> dict[str, object]:
    """Observe a reduced Gateway turn through a caller-supplied runtime control surface."""

    try:
        policy_enabled = _validate_policy(bridge_policy)
    except ValueError:
        return _error_result("invalid_bridge_policy")
    if not policy_enabled:
        return _disabled_result()

    handle = getattr(runtime_control_surface, "handle", None)
    if not callable(handle):
        return _error_result("runtime_control_surface_required")

    try:
        safe_observation = _validate_observation(observation)
        workflow_id = _runtime_workflow_id(safe_observation)
        start_payload = _start_payload(workflow_id=workflow_id, observation=safe_observation)
    except ValueError:
        return _error_result("invalid_observation")

    start_request = {"operation": "start_transaction", "workflow_id": workflow_id, "start_payload": start_payload}
    try:
        start_result = await _invoke_handle(handle, start_request)
    except Exception:
        return _error_result("runtime_start_failed")
    if not _start_result_ok(start_result, workflow_id=workflow_id):
        return _error_result("runtime_start_failed")
    start_status = _status_from_result(start_result, default="started")

    query_request = {"operation": "query_transaction", "workflow_id": workflow_id}
    try:
        query_result = await _invoke_handle(handle, query_request)
        snapshot_summary = _snapshot_summary_from_query_result(query_result, workflow_id=workflow_id)
    except ValueError:
        return _error_result("unsafe_runtime_output")
    except Exception:
        return _error_result("runtime_query_failed")

    result: dict[str, object] = {
        "type": TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION,
        "ok": True,
        "verdict": TEMPORAL_OBSERVATION_SUCCESS_VERDICT,
        "operation": _OPERATION,
        "workflow_id": workflow_id,
        "transaction_id": workflow_id,
        "start_status": start_status,
        "query_status": snapshot_summary["status"],
        "runtime_call_counts": {"start_transaction": 1, "query_transaction": 1},
        "snapshot_summary": snapshot_summary,
        "checks": {
            "policy_enabled": True,
            "observation_safe": True,
            "start_payload_safe": True,
            "query_snapshot_safe": True,
            "runtime_side_effects_absent": True,
        },
        "side_effects": [],
    }
    return _checked_result(result)


def _validate_policy(policy: object) -> bool:
    safe = _plain_dict(policy, error="invalid_bridge_policy")
    _reject_unsafe_material(safe, error="invalid_bridge_policy")
    if set(safe) != _POLICY_FIELDS or safe["type"] != TEMPORAL_OBSERVATION_BRIDGE_POLICY_TYPE:
        _raise("invalid_bridge_policy")
    _empty_list(safe["side_effects"], error="invalid_bridge_policy")
    enabled = safe["enabled"]
    if enabled is False:
        if not (
            safe["mode"] == "default_off"
            and safe["allow_runtime_start"] is False
            and safe["allow_runtime_query"] is False
        ):
            _raise("invalid_bridge_policy")
        return False
    if enabled is True:
        if not (
            safe["mode"] == "controlled_observation"
            and safe["allow_runtime_start"] is True
            and safe["allow_runtime_query"] is True
        ):
            _raise("invalid_bridge_policy")
        return True
    _raise("invalid_bridge_policy")


def _validate_observation(observation: object) -> dict[str, object]:
    safe = _plain_dict(observation, error="invalid_observation")
    _reject_unsafe_material(safe, error="invalid_observation")
    if set(safe) != _OBSERVATION_FIELDS:
        _raise("invalid_observation")
    if not (
        safe["type"] == TEMPORAL_OBSERVATION_TYPE
        and safe["version"] == TEMPORAL_OBSERVATION_VERSION
        and safe["source"] == "controlled_gateway_observation"
    ):
        _raise("invalid_observation")
    entry_count = _entry_count(safe["entry_count"])
    record_counts = _record_counts(safe["record_counts"], entry_count=entry_count, error="invalid_observation")
    claim_refs = _claim_refs(safe["claim_refs"])
    checks = _checks(safe["checks"])
    result: dict[str, object] = {
        "type": TEMPORAL_OBSERVATION_TYPE,
        "version": TEMPORAL_OBSERVATION_VERSION,
        "source": "controlled_gateway_observation",
        "session_label": _safe_label(safe["session_label"], error="invalid_observation"),
        "turn_label": _safe_label(safe["turn_label"], error="invalid_observation"),
        "turn_discriminator": _safe_label(safe["turn_discriminator"], error="invalid_observation"),
        "entry_count": entry_count,
        "record_counts": record_counts,
        "claim_refs": claim_refs,
        "surfaces": _surfaces(safe["surfaces"]),
        "checks": checks,
        "side_effects": _empty_list(safe["side_effects"], error="invalid_observation"),
    }
    _assert_no_forbidden_rendered_material(result, error="invalid_observation")
    return result


def _runtime_workflow_id(observation: dict[str, object]) -> str:
    identity_material = {
        "session_label": observation["session_label"],
        "turn_label": observation["turn_label"],
        "turn_discriminator": observation["turn_discriminator"],
        "entry_count": observation["entry_count"],
        "record_counts": observation["record_counts"],
        "claim_refs": observation["claim_refs"],
        "surfaces": observation["surfaces"],
    }
    digest = hashlib.sha256(_stable_json(identity_material)).hexdigest()[:20]
    workflow_id = f"runtime_tx_gateway_observation_{digest}"
    _synthetic_id(workflow_id, prefixes=("runtime_tx_",), error="invalid_observation")
    return workflow_id


def _start_payload(*, workflow_id: str, observation: dict[str, object]) -> dict[str, object]:
    record_counts = dict(observation["record_counts"])
    return {
        "transaction_id": workflow_id,
        "idempotency_key": "runtime_event_start_gateway_observation_" + workflow_id.removeprefix("runtime_tx_gateway_observation_"),
        "entry_count": observation["entry_count"],
        "record_counts": record_counts,
        "allowed_runtime_events": list(_ALLOWED_RUNTIME_EVENTS),
        "claim_check_policy": _plain_copy(_CLAIM_CHECK_POLICY),
    }


async def _invoke_handle(handle: Any, request: dict[str, object]) -> dict[str, object]:
    result = handle(request)
    if not inspect.isawaitable(result):
        _raise("runtime_error")
    awaited = await result
    if type(awaited) is not dict:
        _raise("runtime_error")
    return awaited


def _start_result_ok(result: dict[str, object], *, workflow_id: str) -> bool:
    if result.get("ok") is not True:
        return False
    if result.get("operation") != "start_transaction":
        return False
    if result.get("workflow_id") not in {None, workflow_id}:
        return False
    if result.get("transaction_id") not in {None, workflow_id}:
        return False
    status = result.get("status")
    return status is None or status in {"started", "running"}


def _status_from_result(result: dict[str, object], *, default: str) -> str:
    status = result.get("status")
    if type(status) is str and status in {"started", "running"}:
        return status
    return default


def _snapshot_summary_from_query_result(query_result: object, *, workflow_id: str) -> dict[str, object]:
    result = _plain_dict(query_result, error="unsafe_runtime_output")
    _reject_unsafe_material(result, error="unsafe_runtime_output")
    if not (result.get("ok") is True and result.get("operation") == "query_transaction"):
        _raise("unsafe_runtime_output")
    if result.get("workflow_id") not in {None, workflow_id}:
        _raise("unsafe_runtime_output")
    if result.get("transaction_id") not in {None, workflow_id}:
        _raise("unsafe_runtime_output")
    snapshot = _plain_dict(result.get("snapshot"), error="unsafe_runtime_output")
    _reject_unsafe_material(snapshot, error="unsafe_runtime_output")
    if not _SNAPSHOT_REQUIRED_FIELDS.issubset(snapshot):
        _raise("unsafe_runtime_output")
    if not (
        snapshot["type"] == "flowweaver.temporal_poc.snapshot.v0"
        and snapshot["version"] == "flowweaver.temporal_poc.v0"
        and snapshot["transaction_id"] == workflow_id
        and snapshot["status"] in _ALLOWED_SNAPSHOT_STATUSES
    ):
        _raise("unsafe_runtime_output")
    entry_count = _entry_count(snapshot["entry_count"], error="unsafe_runtime_output")
    record_counts = _record_counts(snapshot["record_counts"], entry_count=entry_count, error="unsafe_runtime_output")
    counts = _counts(snapshot["counts"], entry_count=entry_count, delivery_count=record_counts["deliveries"])
    _empty_list(snapshot["side_effects"], error="unsafe_runtime_output")
    _assert_no_forbidden_rendered_material(snapshot, error="unsafe_runtime_output", allow_runtime_start_signature=True)
    return {
        "status": snapshot["status"],
        "entry_count": entry_count,
        "record_counts": record_counts,
        "counts": counts,
        "side_effects": [],
    }


def _entry_count(value: object, *, error: str = "invalid_observation") -> int:
    if type(value) is not int or not (1 <= value <= 20):
        _raise(error)
    return value


def _record_counts(value: object, *, entry_count: int, error: str) -> dict[str, int]:
    counts = _plain_dict(value, error=error)
    if set(counts) != _RECORD_COUNT_KEYS:
        _raise(error)
    if not all(type(counts[key]) is int for key in _RECORD_COUNT_KEYS):
        _raise(error)
    if not (
        counts["transactions"] == 1
        and counts["intents"] == entry_count
        and counts["artifacts"] == entry_count
        and entry_count <= counts["deliveries"] <= 20
    ):
        _raise(error)
    return {key: counts[key] for key in ("transactions", "intents", "artifacts", "deliveries")}


def _counts(value: object, *, entry_count: int, delivery_count: int) -> dict[str, int]:
    counts = _plain_dict(value, error="unsafe_runtime_output")
    if set(counts) != {"intents", "artifacts", "deliveries"}:
        _raise("unsafe_runtime_output")
    if not all(type(counts[key]) is int for key in counts):
        _raise("unsafe_runtime_output")
    if not (counts["intents"] == entry_count and counts["artifacts"] == entry_count and counts["deliveries"] == delivery_count):
        _raise("unsafe_runtime_output")
    return {key: counts[key] for key in ("intents", "artifacts", "deliveries")}


def _claim_refs(value: object) -> dict[str, str]:
    refs = _plain_dict(value, error="invalid_observation")
    if set(refs) != _CLAIM_REF_KEYS:
        _raise("invalid_observation")
    return {key: _synthetic_id(refs[key], prefixes=("claim_ref_",), error="invalid_observation") for key in sorted(refs)}


def _surfaces(value: object) -> list[str]:
    surfaces = _plain_list(value, error="invalid_observation")
    if not (1 <= len(surfaces) <= 20):
        _raise("invalid_observation")
    safe: list[str] = []
    for surface in surfaces:
        if type(surface) is not str or surface not in _ALLOWED_SURFACES:
            _raise("invalid_observation")
        if surface in safe:
            _raise("invalid_observation")
        safe.append(surface)
    return safe


def _checks(value: object) -> dict[str, bool]:
    checks = _plain_dict(value, error="invalid_observation")
    if set(checks) != _CHECK_KEYS:
        _raise("invalid_observation")
    if not all(checks[key] is True for key in _CHECK_KEYS):
        _raise("invalid_observation")
    return {key: True for key in sorted(_CHECK_KEYS)}


def _safe_label(value: object, *, error: str) -> str:
    if type(value) is not str or not (1 <= len(value) <= 96):
        _raise(error)
    lowered = value.lower()
    if not lowered.startswith("safe_"):
        _raise(error)
    if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
        _raise(error)
    if any(marker in lowered for marker in _SYNTHETIC_FORBIDDEN_SUBSTRINGS):
        _raise(error)
    if any(marker in lowered for marker in ("om_", "oc_", "ou_", "chat", "message", "platform", "feishu", "lark", "telegram", "private")):
        _raise(error)
    if not all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in value):
        _raise(error)
    return value


def _synthetic_id(value: object, *, prefixes: tuple[str, ...], error: str) -> str:
    if type(value) is not str or not value or len(value) > 128:
        _raise(error)
    lowered = value.lower()
    if not lowered.startswith(prefixes):
        _raise(error)
    if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
        _raise(error)
    body_prefix = next((prefix for prefix in prefixes if lowered.startswith(prefix)), "")
    body = lowered[len(body_prefix) :]
    if any(marker in body for marker in ("om_", "oc_", "ou_", "chat", "message", "platform", "feishu", "lark", "telegram", "private")):
        _raise(error)
    if any(marker in lowered for marker in _SYNTHETIC_FORBIDDEN_SUBSTRINGS):
        _raise(error)
    if not all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in value):
        _raise(error)
    return value


def _reject_unsafe_material(value: object, *, error: str) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _raise(error)
            lowered = key.lower()
            if lowered in _UNSAFE_EXACT_KEYS or any(marker in lowered for marker in _UNSAFE_KEY_SUBSTRINGS):
                _raise(error)
            _reject_unsafe_material(item, error=error)
        return
    if type(value) is list:
        for item in value:
            _reject_unsafe_material(item, error=error)
        return
    if type(value) is str:
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
            _raise(error)
        if "/" in lowered or "\\" in lowered:
            _raise(error)
        if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
            _raise(error)
        return
    if type(value) in {bool, int} or value is None:
        return
    _raise(error)


def _plain_dict(value: object, *, error: str) -> dict[str, object]:
    copied = _plain_copy(value)
    if type(copied) is not dict:
        _raise(error)
    return copied


def _plain_list(value: object, *, error: str) -> list[object]:
    copied = _plain_copy(value)
    if type(copied) is not list:
        _raise(error)
    return copied


def _plain_copy(value: object) -> object:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is list:
        copied_list: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_list.append(copied)
        return copied_list
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


def _empty_list(value: object, *, error: str) -> list[object]:
    copied = _plain_copy(value)
    if copied != []:
        _raise(error)
    return []


def _stable_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _disabled_result() -> dict[str, object]:
    return _checked_result(
        {
            "type": TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE,
            "version": FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION,
            "ok": False,
            "operation": _OPERATION,
            "status": "disabled",
            "error_code": "disabled",
            "side_effects": [],
        }
    )


def _error_result(error_code: str) -> dict[str, object]:
    return _checked_result(
        {
            "type": TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE,
            "version": FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION,
            "ok": False,
            "operation": _OPERATION,
            "error_code": _safe_error_code(error_code),
            "side_effects": [],
        }
    )


def _safe_error_code(value: object) -> str:
    allowed = {
        "disabled",
        "invalid_bridge_policy",
        "invalid_observation",
        "runtime_control_surface_required",
        "runtime_start_failed",
        "runtime_query_failed",
        "unsafe_runtime_output",
    }
    return value if type(value) is str and value in allowed else "runtime_query_failed"


def _checked_result(result: dict[str, object]) -> dict[str, object]:
    if not set(result) <= _RESULT_FIELDS:
        raise RuntimeError("unsafe_output")
    _assert_no_forbidden_rendered_material(result, error="unsafe_output")
    return result


def _assert_no_forbidden_rendered_material(
    value: object,
    *,
    error: str,
    allow_runtime_start_signature: bool = False,
) -> None:
    rendered = repr(value).lower()
    forbidden = [
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
        "card_json",
        "media_path",
        "media_bytes",
        "oc_private",
        "ou_private",
        "om_private",
        "unsafe-" + "token",
        "sk" + "-",
        "bearer ",
    ]
    if not allow_runtime_start_signature:
        forbidden.extend(["allowed_runtime_events", "claim_check_policy", "forbidden_material"])
    if any(marker in rendered for marker in forbidden):
        _raise(error)


def _raise(error: str) -> None:
    raise ValueError(error) from None


__all__ = [
    "FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION",
    "TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE",
    "TEMPORAL_OBSERVATION_SUCCESS_VERDICT",
    "observe_gateway_turn_for_flowweaver_temporal",
]
