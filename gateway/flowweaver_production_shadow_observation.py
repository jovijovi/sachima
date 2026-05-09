"""Bounded default-off FlowWeaver production-shadow observation sidecar."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from gateway.flowweaver_temporal_observation_bridge import (
    FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION,
    TEMPORAL_OBSERVATION_BRIDGE_POLICY_TYPE,
    TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE,
    TEMPORAL_OBSERVATION_SUCCESS_VERDICT,
    observe_gateway_turn_for_flowweaver_temporal,
)

FLOWWEAVER_PRODUCTION_SHADOW_OBSERVATION_VERSION = "flowweaver.production_shadow_observation.v0"
PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE = "flowweaver.gateway.production_shadow_observation_result.v0"
PRODUCTION_SHADOW_OBSERVATION_POLICY_TYPE = "flowweaver.gateway.production_shadow_observation_policy.v0"
PRODUCTION_SHADOW_OBSERVATION_SUCCESS_VERDICT = "ready_for_separate_delivery_or_agent_execution_design"

_OPERATION = "observe_gateway_turn_for_flowweaver_production_shadow"
_REQUIRED_TURN_FIELDS = {
    "platform",
    "session_key",
    "session_id",
    "message_id",
    "turn_started_at_ns",
    "turn_sequence",
    "history_length",
    "api_call_count",
    "final_text_present",
    "rich_card_count",
    "media_count",
}
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
    "observation_summary",
    "delivery",
    "counters",
    "error_code",
    "side_effects",
}
_COUNTER_KEYS = ("disabled", "skipped", "started", "query_failed", "unsafe_runtime_output", "timeout")
_ALLOWED_ERROR_CODES = {
    "disabled",
    "platform_not_allowlisted",
    "no_visible_surface",
    "runtime_control_surface_required",
    "runtime_start_failed",
    "runtime_query_failed",
    "unsafe_runtime_output",
    "timeout",
    "invalid_shadow_policy",
    "invalid_gateway_turn",
}
_UNSAFE_RENDER_MARKERS = (
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
    "callback payload",
    "oc_",
    "ou_",
    "om_",
    "unsafe-" + "token",
    "sk" + "-",
    "bearer ",
    "password" + "=",
    "secret" + "=",
    "api" + "_key=",
    "traceback",
    "valueerror:",
    "runtimeerror:",
    "allowed_runtime_events",
    "claim_check_policy",
    "forbidden_material",
)


async def observe_gateway_turn_for_flowweaver_production_shadow(
    *,
    gateway_turn: object,
    runtime_control_surface: object,
    shadow_policy: object,
) -> dict[str, object]:
    """Mirror one reduced Gateway turn into FlowWeaver runtime state when enabled."""

    try:
        policy = _validate_shadow_policy(shadow_policy)
    except ValueError:
        return _error_result("invalid_shadow_policy")
    if policy["enabled"] is False:
        return _disabled_result()

    try:
        turn = _validate_gateway_turn(gateway_turn)
    except ValueError:
        return _error_result("invalid_gateway_turn")
    if turn["platform"] not in policy["allow_platforms"]:
        return _skipped_result("platform_not_allowlisted")

    handle = getattr(runtime_control_surface, "handle", None)
    if not callable(handle):
        return _error_result("runtime_control_surface_required")

    try:
        observation = _build_temporal_observation(turn)
    except ValueError:
        return _error_result("no_visible_surface")

    bridge_policy = _temporal_bridge_policy()
    try:
        bridge_result = await asyncio.wait_for(
            observe_gateway_turn_for_flowweaver_temporal(
                observation=observation,
                runtime_control_surface=runtime_control_surface,
                bridge_policy=bridge_policy,
            ),
            timeout=float(policy["timeout_ms"]) / 1000.0,
        )
    except TimeoutError:
        return _error_result("timeout")
    except Exception:
        return _error_result("runtime_query_failed")

    try:
        bridge = _validate_bridge_result(bridge_result)
    except ValueError as exc:
        return _error_result(_safe_error_code(str(exc)))

    result = {
        "type": PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE,
        "version": FLOWWEAVER_PRODUCTION_SHADOW_OBSERVATION_VERSION,
        "ok": True,
        "verdict": PRODUCTION_SHADOW_OBSERVATION_SUCCESS_VERDICT,
        "operation": _OPERATION,
        "workflow_id": bridge["workflow_id"],
        "transaction_id": bridge["transaction_id"],
        "start_status": bridge["start_status"],
        "query_status": bridge["query_status"],
        "runtime_call_counts": {"start_transaction": 1, "query_transaction": 1},
        "observation_summary": {
            "entry_count": observation["entry_count"],
            "surfaces": list(observation["surfaces"]),
            "record_counts": dict(observation["record_counts"]),
        },
        "delivery": {"ack_updates": 0, "control": "unchanged"},
        "counters": _counters(started=1),
        "side_effects": [],
    }
    return _checked_result(result)


def production_shadow_observation_policy_from_config(config: object, *, platform: object) -> dict[str, object]:
    """Build the exact default-off Phase 21 policy from a read-only config object."""

    platform_value = _safe_platform(platform)
    shadow_config: object = {}
    if type(config) is dict:
        flowweaver = config.get("flowweaver")
        if type(flowweaver) is dict:
            shadow_config = flowweaver.get("production_shadow_observation", {})
    if type(shadow_config) is not dict:
        shadow_config = {}

    enabled = shadow_config.get("enabled") is True
    allow_platforms = _safe_platform_list(shadow_config.get("platform_allowlist"))
    timeout_ms = _safe_timeout_ms(shadow_config.get("timeout_ms"))
    if not enabled:
        return {
            "type": PRODUCTION_SHADOW_OBSERVATION_POLICY_TYPE,
            "enabled": False,
            "mode": "default_off",
            "allow_runtime_start": False,
            "allow_runtime_query": False,
            "allow_platforms": [],
            "timeout_ms": timeout_ms,
            "side_effects": [],
        }
    return {
        "type": PRODUCTION_SHADOW_OBSERVATION_POLICY_TYPE,
        "enabled": True,
        "mode": "production_shadow_observation",
        "allow_runtime_start": True,
        "allow_runtime_query": True,
        "allow_platforms": [item for item in allow_platforms if item == platform_value],
        "timeout_ms": timeout_ms,
        "side_effects": [],
    }


def _validate_shadow_policy(policy: object) -> dict[str, object]:
    safe = _plain_dict(policy, error="invalid_shadow_policy")
    if set(safe) != {
        "type",
        "enabled",
        "mode",
        "allow_runtime_start",
        "allow_runtime_query",
        "allow_platforms",
        "timeout_ms",
        "side_effects",
    }:
        _raise("invalid_shadow_policy")
    if safe["type"] != PRODUCTION_SHADOW_OBSERVATION_POLICY_TYPE:
        _raise("invalid_shadow_policy")
    _empty_list(safe["side_effects"], error="invalid_shadow_policy")
    allow_platforms = _safe_platform_list(safe["allow_platforms"])
    timeout_ms = _safe_timeout_ms(safe["timeout_ms"])
    if safe["enabled"] is False:
        if safe["mode"] != "default_off" or safe["allow_runtime_start"] is not False or safe["allow_runtime_query"] is not False:
            _raise("invalid_shadow_policy")
        return {**safe, "allow_platforms": [], "timeout_ms": timeout_ms}
    if safe["enabled"] is True:
        if safe["mode"] != "production_shadow_observation" or safe["allow_runtime_start"] is not True or safe["allow_runtime_query"] is not True:
            _raise("invalid_shadow_policy")
        return {**safe, "allow_platforms": allow_platforms, "timeout_ms": timeout_ms}
    _raise("invalid_shadow_policy")


def _validate_gateway_turn(value: object) -> dict[str, object]:
    turn = _plain_dict(value, error="invalid_gateway_turn")
    if not _REQUIRED_TURN_FIELDS.issubset(turn):
        _raise("invalid_gateway_turn")
    platform = _safe_platform(turn["platform"])
    final_text_present = _exact_bool(turn["final_text_present"], error="invalid_gateway_turn")
    rich_card_count = _bounded_int(turn["rich_card_count"], minimum=0, maximum=20, error="invalid_gateway_turn")
    media_count = _bounded_int(turn["media_count"], minimum=0, maximum=20, error="invalid_gateway_turn")
    safe = {
        "platform": platform,
        "session_key": _required_text(turn["session_key"], error="invalid_gateway_turn"),
        "session_id": _required_text(turn["session_id"], error="invalid_gateway_turn"),
        "message_id": _required_text(turn["message_id"], error="invalid_gateway_turn"),
        "turn_started_at_ns": _bounded_int(turn["turn_started_at_ns"], minimum=1, maximum=10**21, error="invalid_gateway_turn"),
        "turn_sequence": _bounded_int(turn["turn_sequence"], minimum=0, maximum=10**9, error="invalid_gateway_turn"),
        "history_length": _bounded_int(turn["history_length"], minimum=0, maximum=10**7, error="invalid_gateway_turn"),
        "api_call_count": _bounded_int(turn["api_call_count"], minimum=0, maximum=10**5, error="invalid_gateway_turn"),
        "final_text_present": final_text_present,
        "rich_card_count": rich_card_count,
        "media_count": media_count,
    }
    return safe


def _build_temporal_observation(turn: dict[str, object]) -> dict[str, object]:
    surfaces: list[str] = []
    if turn["final_text_present"] is True:
        surfaces.append("final_text")
    if int(turn["rich_card_count"]) > 0:
        surfaces.append("rich_card")
    if int(turn["media_count"]) > 0:
        surfaces.append("media")
    if not surfaces:
        _raise("no_visible_surface")
    identity = {
        "platform": turn["platform"],
        "session_key": turn["session_key"],
        "session_id": turn["session_id"],
        "message_id": turn["message_id"],
        "turn_started_at_ns": turn["turn_started_at_ns"],
        "turn_sequence": turn["turn_sequence"],
        "history_length": turn["history_length"],
        "api_call_count": turn["api_call_count"],
        "surfaces": surfaces,
    }
    session_digest = _digest({"platform": turn["platform"], "session_key": turn["session_key"], "session_id": turn["session_id"]})
    turn_digest = _digest(identity)
    delivery_count = len(surfaces)
    return {
        "type": "flowweaver.gateway.temporal_observation.v0",
        "version": "flowweaver.gateway.temporal_observation.v0",
        "source": "controlled_gateway_observation",
        "session_label": f"safe_session_phase21_{session_digest}",
        "turn_label": f"safe_turn_phase21_{turn_digest}",
        "turn_discriminator": f"safe_discriminator_{turn_digest}_{_digest({'turn': turn_digest, 'ns': turn['turn_started_at_ns']})}",
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": delivery_count},
        "claim_refs": {
            "input_ref": f"claim_ref_phase21_input_{turn_digest}",
            "artifact_ref": f"claim_ref_phase21_artifact_{turn_digest}",
            "delivery_ref": f"claim_ref_phase21_delivery_{turn_digest}",
        },
        "surfaces": surfaces,
        "checks": {
            "payloads_absent": True,
            "claim_check_refs_only": True,
            "side_effects_absent": True,
            "source_ids_sanitized": True,
        },
        "side_effects": [],
    }


def _temporal_bridge_policy() -> dict[str, object]:
    return {
        "type": TEMPORAL_OBSERVATION_BRIDGE_POLICY_TYPE,
        "enabled": True,
        "mode": "controlled_observation",
        "allow_runtime_start": True,
        "allow_runtime_query": True,
        "side_effects": [],
    }


def _validate_bridge_result(value: object) -> dict[str, object]:
    result = _plain_dict(value, error="runtime_query_failed")
    if result.get("ok") is not True:
        code = _safe_error_code(result.get("error_code"))
        _raise(code)
    if not (
        result.get("type") == TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE
        and result.get("version") == FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION
        and result.get("verdict") == TEMPORAL_OBSERVATION_SUCCESS_VERDICT
        and result.get("operation") == "observe_gateway_turn_for_flowweaver_temporal"
        and type(result.get("workflow_id")) is str
        and result.get("transaction_id") == result.get("workflow_id")
        and result.get("runtime_call_counts") == {"start_transaction": 1, "query_transaction": 1}
        and result.get("side_effects") == []
    ):
        _raise("runtime_query_failed")
    start_status = result.get("start_status")
    query_status = result.get("query_status")
    if start_status not in {"started", "running"} or query_status not in {"created", "running", "waiting_for_user", "canceled", "completed", "failed"}:
        _raise("runtime_query_failed")
    _assert_no_forbidden_rendered_material(result, allow_policy_metadata=False)
    return {
        "workflow_id": result["workflow_id"],
        "transaction_id": result["transaction_id"],
        "start_status": start_status,
        "query_status": query_status,
    }


def _safe_platform(value: object) -> str:
    if type(value) is not str or not (1 <= len(value) <= 32):
        _raise("invalid_shadow_policy")
    lowered = value.strip().lower()
    if lowered != value or not all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in value):
        _raise("invalid_shadow_policy")
    return value


def _safe_platform_list(value: object) -> list[str]:
    if value is None:
        return []
    if type(value) is not list or len(value) > 20:
        return []
    safe: list[str] = []
    for item in value:
        try:
            platform = _safe_platform(item)
        except ValueError:
            return []
        if platform not in safe:
            safe.append(platform)
    return safe


def _safe_timeout_ms(value: object) -> int:
    if type(value) is not int:
        return 250
    if value < 1:
        return 1
    if value > 1000:
        return 1000
    return value


def _bounded_int(value: object, *, minimum: int, maximum: int, error: str) -> int:
    if type(value) is not int or not (minimum <= value <= maximum):
        _raise(error)
    return value


def _exact_bool(value: object, *, error: str) -> bool:
    if value is True:
        return True
    if value is False:
        return False
    _raise(error)


def _required_text(value: object, *, error: str) -> str:
    if type(value) is not str or not (1 <= len(value) <= 512):
        _raise(error)
    return value


def _digest(value: object) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:20]


def _plain_dict(value: object, *, error: str) -> dict[str, object]:
    if type(value) is not dict:
        _raise(error)
    copied: dict[str, object] = {}
    for key, item in value.items():
        if type(key) is not str:
            _raise(error)
        copied[key] = item
    return copied


def _empty_list(value: object, *, error: str) -> list[object]:
    if value != []:
        _raise(error)
    return []


def _disabled_result() -> dict[str, object]:
    return _checked_result(
        {
            "type": PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE,
            "version": FLOWWEAVER_PRODUCTION_SHADOW_OBSERVATION_VERSION,
            "ok": False,
            "operation": _OPERATION,
            "status": "disabled",
            "error_code": "disabled",
            "counters": _counters(disabled=1),
            "side_effects": [],
        }
    )


def _skipped_result(error_code: str) -> dict[str, object]:
    return _checked_result(
        {
            "type": PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE,
            "version": FLOWWEAVER_PRODUCTION_SHADOW_OBSERVATION_VERSION,
            "ok": False,
            "operation": _OPERATION,
            "status": "skipped",
            "error_code": _safe_error_code(error_code),
            "counters": _counters(skipped=1),
            "side_effects": [],
        }
    )


def _error_result(error_code: str) -> dict[str, object]:
    safe_code = _safe_error_code(error_code)
    return _checked_result(
        {
            "type": PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE,
            "version": FLOWWEAVER_PRODUCTION_SHADOW_OBSERVATION_VERSION,
            "ok": False,
            "operation": _OPERATION,
            "error_code": safe_code,
            "counters": _counters(**_counter_for_error(safe_code)),
            "side_effects": [],
        }
    )


def _counter_for_error(error_code: str) -> dict[str, int]:
    if error_code == "timeout":
        return {"timeout": 1}
    if error_code == "unsafe_runtime_output":
        return {"unsafe_runtime_output": 1}
    if error_code == "runtime_query_failed":
        return {"query_failed": 1}
    return {"skipped": 1}


def _counters(**overrides: int) -> dict[str, int]:
    counters = {key: 0 for key in _COUNTER_KEYS}
    for key, value in overrides.items():
        if key in counters:
            counters[key] = int(value)
    return counters


def _safe_error_code(value: object) -> str:
    return value if type(value) is str and value in _ALLOWED_ERROR_CODES else "runtime_query_failed"


def _checked_result(result: dict[str, object]) -> dict[str, object]:
    if set(result) - _RESULT_FIELDS:
        raise RuntimeError("unsafe_output")
    _assert_no_forbidden_rendered_material(result, allow_policy_metadata=False)
    return result


def _assert_no_forbidden_rendered_material(value: object, *, allow_policy_metadata: bool) -> None:
    rendered = repr(value).lower()
    forbidden = list(_UNSAFE_RENDER_MARKERS)
    if allow_policy_metadata:
        forbidden = [
            marker
            for marker in forbidden
            if marker not in {"allowed_runtime_events", "claim_check_policy", "forbidden_material"}
        ]
    if any(marker in rendered for marker in forbidden):
        _raise("unsafe_output")


def _raise(error: str) -> None:
    raise ValueError(error) from None


__all__ = [
    "FLOWWEAVER_PRODUCTION_SHADOW_OBSERVATION_VERSION",
    "PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE",
    "PRODUCTION_SHADOW_OBSERVATION_SUCCESS_VERDICT",
    "observe_gateway_turn_for_flowweaver_production_shadow",
    "production_shadow_observation_policy_from_config",
]
