"""PE-2A controlled runtime plus fake-delivery bridge.

This module is intentionally default-off and test/local only. It connects a
sanitized Sachima ingress envelope to a caller-supplied runtime control surface
and the existing fake Sachima send simulator. It never owns Gateway lifecycle,
constructs Temporal clients, reads production config, or calls real IM delivery.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from typing import Any

FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_VERSION = "flowweaver.pe2a.controlled_runtime_delivery_bridge.v0"
FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_RESULT_TYPE = (
    "flowweaver.pe2a.controlled_runtime_delivery_result.v0"
)
FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_POLICY_TYPE = (
    "flowweaver.pe2a.controlled_runtime_delivery_policy.v0"
)
FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_SUCCESS_VERDICT = (
    "pe2a_evidence_ready_for_external_ingress_design_request_only"
)
PE2A_INGRESS_ENVELOPE_TYPE = "flowweaver.pe2.sachima_ingress_envelope.v0"
PE2A_CONTRACT_TYPE = "flowweaver.pe2a.controlled_runtime_delivery_contract.v0"
_OPERATION = "run_flowweaver_pe2a_controlled_runtime_delivery"
_ALLOWED_RUNTIME_OPERATIONS = (
    "start_transaction",
    "record_operation",
    "plan_delivery",
    "record_delivery_ack",
    "query_transaction",
    "cancel_transaction",
)
_BRIDGE_RUNTIME_OPERATIONS = (
    "start_transaction",
    "record_operation",
    "plan_delivery",
    "record_delivery_ack",
    "query_transaction",
)
_ALLOWED_SURFACES = ("progress_card", "rich_card", "final_text", "media", "artifact")
_SEPARATE_APPROVAL_REQUIRED = (
    "real_external_sachima_ingress",
    "real_external_delivery",
    "production_config_write",
    "gateway_restart_or_reload",
    "gateway_owned_temporal_lifecycle",
    "production_agent_tool_execution_expansion",
)
_POLICY_FIELDS = {
    "type",
    "enabled",
    "mode",
    "platform_allowlist",
    "allow_runtime_operations",
    "delivery_boundary",
    "timeout_ms",
    "side_effects",
}
_ENVELOPE_FIELDS = {
    "type",
    "platform",
    "source",
    "session_label",
    "turn_label",
    "turn_discriminator",
    "auth",
    "visible_surfaces",
    "claim_refs",
    "side_effects",
}
_AUTH_FIELDS = {"hmac_verified", "policy_label"}
_VISIBLE_SURFACE_FIELDS = {"final_text", "rich_card_count", "media_count"}
_CLAIM_REF_FIELDS = {"input_ref", "delivery_refs", "artifact_refs"}
_RUNTIME_COUNTS_KEYS = {
    "start_transaction",
    "record_operation",
    "plan_delivery",
    "record_delivery_ack",
    "query_transaction",
    "cancel_transaction",
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
    "duplicate",
    "runtime_operations",
    "runtime_call_counts",
    "delivery_surface_state",
    "delivery_ack_refs",
    "delivery_events",
    "duplicate_ingress_refs",
    "rejected_probe_codes",
    "counts",
    "negative_probes",
    "rollback_restore",
    "error_code",
    "side_effects",
}
_EVIDENCE_TYPE = "flowweaver.pe2a.controlled_runtime_fake_delivery_evidence.v0"
_DELIVERY_REF_RE = re.compile(r"^runtime_delivery_(0|[1-9][0-9]*)$")
_ARTIFACT_REF_RE = re.compile(r"^runtime_artifact_(0|[1-9][0-9]*)$")
_INPUT_REF_RE = re.compile(r"^runtime_input_(0|[1-9][0-9]*)$")
_SAFE_LABEL_RE = re.compile(r"^safe_[a-z0-9_]{1,91}$")
_UNSAFE_KEY_MARKERS = (
    "raw_",
    "raw",
    "prompt",
    "body",
    "payload",
    "card_json",
    "media_path",
    "media_bytes",
    "tool_output",
    "stdout",
    "stderr",
    "callback",
    "credential",
    "password",
    "api_key",
    "bearer",
)
_UNSAFE_EXACT_KEYS = {"token", "secret", "signature", "headers", "chat_id", "user_id", "message_id"}
_PRIVATE_PREFIXES = ("oc_", "ou_", "om_", "chat_", "message_", "platform_", "feishu_", "lark_", "telegram_")
_UNSAFE_VALUE_MARKERS = (
    "raw_prompt",
    "raw prompt",
    "tool_output",
    "tool output",
    "card_json",
    "media_path",
    "media_bytes",
    "platform_payload",
    "callback_payload",
    "traceback",
    "exception",
    "runtimeerror:",
    "valueerror:",
    "unsafe-" + "token",
    "bearer ",
    "sk" + "-",
    "password" + "=",
    "secret" + "=",
    "api" + "_key=",
    "/tmp/",
    "/home/",
    "media:",
)
_NO_LEAK_MARKERS = (
    "raw_prompt",
    "raw prompt",
    "tool_output",
    "tool output",
    "card_json",
    "media_path",
    "media_bytes",
    "platform_payload",
    "callback_payload",
    "traceback",
    "runtimeerror:",
    "unsafe-" + "token",
    "bearer ",
    "sk" + "-",
    "oc_",
    "ou_",
    "om_",
    "/home/",
    "media:",
)
_INVALID = object()


class FlowWeaverPE2AControlledRuntimeDeliveryBridge:
    """Stateful PE-2A bridge with duplicate-ingress memory."""

    def __init__(self) -> None:
        self._completed_turns: dict[str, dict[str, object]] = {}

    async def run(
        self,
        *,
        ingress_envelope: object,
        runtime_control_surface: object,
        fake_send_surface: object,
        policy: object,
    ) -> dict[str, object]:
        try:
            safe_policy = _validate_policy(policy)
        except ValueError:
            return _error_result("invalid_pe2a_policy")
        if safe_policy["enabled"] is False:
            return _error_result("disabled", status="disabled")

        try:
            envelope = _validate_ingress_envelope(ingress_envelope)
        except ValueError:
            return _error_result("invalid_ingress_envelope")
        if envelope["platform"] not in safe_policy["platform_allowlist"]:
            return _error_result("platform_not_allowlisted", status="skipped")

        fake_record = getattr(fake_send_surface, "record_send", None)
        if not callable(fake_record):
            return _error_result("fake_send_surface_required")

        handle = getattr(runtime_control_surface, "handle", None)
        if not callable(handle):
            return _error_result("runtime_control_surface_required")

        turn_discriminator = str(envelope["turn_discriminator"])
        if turn_discriminator in self._completed_turns:
            previous = self._completed_turns[turn_discriminator]
            return _duplicate_result(previous)

        workflow_id = _workflow_id(envelope)
        runtime_counts = _runtime_counts()
        try:
            start_result = await _runtime_call(
                handle,
                _start_transaction_request(workflow_id=workflow_id, envelope=envelope),
                expected_operation="start_transaction",
                workflow_id=workflow_id,
                timeout_ms=int(safe_policy["timeout_ms"]),
            )
            runtime_counts["start_transaction"] += 1
            _validate_runtime_result(start_result, expected_operation="start_transaction", workflow_id=workflow_id)

            record_result = await _runtime_call(
                handle,
                _record_operation_request(workflow_id=workflow_id, envelope=envelope),
                expected_operation="record_operation",
                workflow_id=workflow_id,
                timeout_ms=int(safe_policy["timeout_ms"]),
            )
            runtime_counts["record_operation"] += 1
            _validate_runtime_result(record_result, expected_operation="record_operation", workflow_id=workflow_id)

            delivery_plan = _delivery_plan_from_envelope(envelope)
            plan_result = await _runtime_call(
                handle,
                _plan_delivery_request(workflow_id=workflow_id, delivery_plan=delivery_plan),
                expected_operation="plan_delivery",
                workflow_id=workflow_id,
                timeout_ms=int(safe_policy["timeout_ms"]),
            )
            runtime_counts["plan_delivery"] += 1
            _validate_plan_result(plan_result, workflow_id=workflow_id, delivery_plan=delivery_plan)
        except RuntimeOperationFailed:
            return _error_result("runtime_operation_failed", runtime_counts=runtime_counts)
        except UnsafeRuntimeOutput:
            return _error_result("unsafe_runtime_output", runtime_counts=runtime_counts)
        except Exception:
            return _error_result("runtime_operation_failed", runtime_counts=runtime_counts)

        ack_refs: list[str] = []
        fake_send_attempts = 0
        ack_pairs: list[tuple[dict[str, object], dict[str, object]]] = []
        try:
            for item in delivery_plan:
                fake_send_attempts += 1
                fake_response = fake_record(_fake_send_payload(item))
                ack_pairs.append((item, _validate_fake_send_response(fake_response, item)))
        except FakeSendRejected:
            return _error_result(
                "fake_send_rejected",
                runtime_counts=runtime_counts,
                delivery_events=[_rejected_delivery_event(item)],
                rejected_probe_codes=["fake_send_rejected"],
                counts=_counts(
                    accepted=0,
                    runtime_counts=runtime_counts,
                    fake_send_requests=fake_send_attempts,
                    ack_updates=0,
                    rejected=1,
                ),
            )
        except Exception:
            return _error_result("runtime_operation_failed", runtime_counts=runtime_counts)

        try:
            delivery_events: list[dict[str, object]] = []
            for item, ack in ack_pairs:
                if ack["duplicate"] is True:
                    delivery_events.append(_sent_delivery_event(item=item, ack_ref=str(ack["ack_ref"]), duplicate=True))
                    continue
                ack_result = await _runtime_call(
                    handle,
                    _record_delivery_ack_request(workflow_id=workflow_id, item=item, ack=ack),
                    expected_operation="record_delivery_ack",
                    workflow_id=workflow_id,
                    timeout_ms=int(safe_policy["timeout_ms"]),
                )
                runtime_counts["record_delivery_ack"] += 1
                _validate_ack_result(ack_result, workflow_id=workflow_id, item=item, ack=ack)
                ack_refs.append(str(ack["ack_ref"]))
                delivery_events.append(_sent_delivery_event(item=item, ack_ref=str(ack["ack_ref"]), duplicate=False))
        except RuntimeOperationFailed:
            return _error_result("runtime_operation_failed", runtime_counts=runtime_counts)
        except UnsafeRuntimeOutput:
            return _error_result("unsafe_runtime_output", runtime_counts=runtime_counts)
        except Exception:
            return _error_result("runtime_operation_failed", runtime_counts=runtime_counts)

        try:
            query_result = await _runtime_call(
                handle,
                _query_transaction_request(workflow_id=workflow_id),
                expected_operation="query_transaction",
                workflow_id=workflow_id,
                timeout_ms=int(safe_policy["timeout_ms"]),
            )
            runtime_counts["query_transaction"] += 1
            _validate_runtime_result(query_result, expected_operation="query_transaction", workflow_id=workflow_id)
        except RuntimeOperationFailed:
            return _error_result("runtime_operation_failed", runtime_counts=runtime_counts)
        except UnsafeRuntimeOutput:
            return _error_result("unsafe_runtime_output", runtime_counts=runtime_counts)
        except Exception:
            return _error_result("runtime_operation_failed", runtime_counts=runtime_counts)

        result = _success_result(
            workflow_id=workflow_id,
            delivery_plan=delivery_plan,
            ack_refs=ack_refs,
            delivery_events=delivery_events,
            runtime_counts=runtime_counts,
            fake_send_requests=fake_send_attempts,
        )
        self._completed_turns[turn_discriminator] = result
        return result


async def run_flowweaver_pe2a_controlled_runtime_delivery(
    *,
    ingress_envelope: object,
    runtime_control_surface: object,
    fake_send_surface: object,
    policy: object,
) -> dict[str, object]:
    """Run one stateless PE-2A bridge invocation."""

    bridge = FlowWeaverPE2AControlledRuntimeDeliveryBridge()
    return await bridge.run(
        ingress_envelope=ingress_envelope,
        runtime_control_surface=runtime_control_surface,
        fake_send_surface=fake_send_surface,
        policy=policy,
    )


def describe_flowweaver_pe2a_contract() -> dict[str, object]:
    """Return the machine-readable PE-2A boundary contract."""

    return {
        "type": PE2A_CONTRACT_TYPE,
        "version": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_VERSION,
        "allowed_runtime_operations": list(_ALLOWED_RUNTIME_OPERATIONS),
        "delivery_boundary": "fake_send_only",
        "gateway_lifecycle_ownership": "forbidden",
        "runtime_lifecycle_ownership": "caller_supplied_control_surface_only",
        "real_external_ingress": False,
        "real_external_delivery": False,
        "production_config_write": False,
        "gateway_restart_or_reload": False,
        "platform_adapter_mutation": False,
        "next_allowed_decision": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_SUCCESS_VERDICT,
        "separate_approval_required": list(_SEPARATE_APPROVAL_REQUIRED),
        "side_effects": [],
    }


def pe2a_controlled_runtime_delivery_policy(
    *,
    enabled: bool = True,
    platform_allowlist: list[str] | tuple[str, ...] | None = ("sachima",),
    timeout_ms: int = 250,
) -> dict[str, object]:
    """Build a default-off-compatible local PE-2A policy."""

    if enabled is False:
        return {
            "type": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_POLICY_TYPE,
            "enabled": False,
            "mode": "default_off",
            "platform_allowlist": [],
            "allow_runtime_operations": [],
            "delivery_boundary": "disabled",
            "timeout_ms": _safe_timeout_ms(timeout_ms),
            "side_effects": [],
        }
    return {
        "type": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_POLICY_TYPE,
        "enabled": True,
        "mode": "controlled_runtime_fake_delivery",
        "platform_allowlist": list(platform_allowlist or []),
        "allow_runtime_operations": list(_BRIDGE_RUNTIME_OPERATIONS),
        "delivery_boundary": "fake_send_only",
        "timeout_ms": _safe_timeout_ms(timeout_ms),
        "side_effects": [],
    }


def build_flowweaver_pe2a_evidence(result: object, *, base_sha: str) -> dict[str, object]:
    """Build sanitized PE-2A evidence from a checked bridge result."""

    safe_result = _plain_dict(result, error="invalid_pe2a_result")
    _reject_unsafe_material(safe_result, error="invalid_pe2a_result")
    if not (
        safe_result.get("type") == FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_RESULT_TYPE
        and safe_result.get("version") == FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_VERSION
        and safe_result.get("ok") is True
    ):
        _raise("invalid_pe2a_result")
    _empty_list(safe_result.get("side_effects", []), error="invalid_pe2a_result")
    counts = _plain_dict(safe_result.get("counts"), error="invalid_pe2a_result")
    expected_count_keys = {
        "accepted_ingress_envelopes",
        "runtime_start_requests",
        "runtime_delivery_plan_requests",
        "fake_send_requests",
        "runtime_ack_updates",
        "duplicates",
        "rejected_probes",
    }
    if set(counts) != expected_count_keys or not all(type(counts[key]) is int and counts[key] >= 0 for key in expected_count_keys):
        _raise("invalid_pe2a_result")
    runtime_operations = _safe_runtime_operations(safe_result.get("runtime_operations"))
    delivery_ack_refs = _safe_delivery_ack_refs(safe_result.get("delivery_ack_refs"))
    delivery_events = _safe_delivery_events(safe_result.get("delivery_events"))
    duplicate_ingress_refs = _safe_duplicate_ingress_refs(safe_result.get("duplicate_ingress_refs"))
    rejected_probe_codes = _safe_rejected_probe_codes(safe_result.get("rejected_probe_codes"))
    derived_fake_send_requests = len(delivery_events)
    derived_runtime_ack_updates = sum(1 for event in delivery_events if event["status"] == "sent" and event["duplicate"] is False)
    derived_fake_duplicates = sum(1 for event in delivery_events if event["status"] == "sent" and event["duplicate"] is True)
    if counts["runtime_start_requests"] != runtime_operations.count("start_transaction"):
        _raise("invalid_pe2a_result")
    if counts["runtime_delivery_plan_requests"] != runtime_operations.count("plan_delivery"):
        _raise("invalid_pe2a_result")
    if counts["runtime_ack_updates"] != runtime_operations.count("record_delivery_ack"):
        _raise("invalid_pe2a_result")
    if counts["runtime_ack_updates"] != len(delivery_ack_refs):
        _raise("invalid_pe2a_result")
    if counts["runtime_ack_updates"] != derived_runtime_ack_updates:
        _raise("invalid_pe2a_result")
    if counts["fake_send_requests"] != derived_fake_send_requests:
        _raise("invalid_pe2a_result")
    if counts["duplicates"] != len(duplicate_ingress_refs) + derived_fake_duplicates:
        _raise("invalid_pe2a_result")
    if counts["rejected_probes"] != len(rejected_probe_codes):
        _raise("invalid_pe2a_result")
    if any(event["status"] == "rejected" for event in delivery_events) and "fake_send_rejected" not in rejected_probe_codes:
        _raise("invalid_pe2a_result")
    evidence: dict[str, object] = {
        "type": _EVIDENCE_TYPE,
        "base_sha": _safe_base_sha(base_sha),
        "scope": {
            "loopback_or_synthetic_only": True,
            "real_external_ingress": False,
            "real_external_delivery": False,
            "gateway_restart_or_config_write": False,
            "gateway_owned_temporal_lifecycle": False,
            "production_agent_tool_execution_expansion": False,
        },
        "counts": {key: counts[key] for key in sorted(expected_count_keys)},
        "runtime_operations": runtime_operations,
        "delivery_events": delivery_events,
        "delivery_surface_state": _safe_plain_mapping(safe_result.get("delivery_surface_state")),
        "negative_probes": _safe_plain_mapping(safe_result.get("negative_probes", {})),
        "rollback_restore": _safe_plain_mapping(safe_result.get("rollback_restore", {})),
        "decision": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_SUCCESS_VERDICT,
    }
    evidence["no_leak_scan"] = scan_pe2a_no_leak(evidence)
    if evidence["no_leak_scan"] != {"passed": True, "raw_marker_hits": 0, "markers": []}:
        _raise("unsafe_evidence")
    return evidence


def scan_pe2a_no_leak(value: object) -> dict[str, object]:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).lower()
    hits = sorted(marker for marker in _NO_LEAK_MARKERS if marker.lower() in rendered)
    return {"passed": not hits, "raw_marker_hits": len(hits), "markers": hits}


def _validate_policy(policy: object) -> dict[str, object]:
    safe = _plain_dict(policy, error="invalid_pe2a_policy")
    _reject_unsafe_material(safe, error="invalid_pe2a_policy")
    if set(safe) != _POLICY_FIELDS or safe["type"] != FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_POLICY_TYPE:
        _raise("invalid_pe2a_policy")
    _empty_list(safe["side_effects"], error="invalid_pe2a_policy")
    timeout_ms = _safe_timeout_ms(safe["timeout_ms"])
    if safe["enabled"] is False:
        if not (
            safe["mode"] == "default_off"
            and safe["platform_allowlist"] == []
            and safe["allow_runtime_operations"] == []
            and safe["delivery_boundary"] == "disabled"
        ):
            _raise("invalid_pe2a_policy")
        return {**safe, "timeout_ms": timeout_ms}
    if safe["enabled"] is True:
        allowlist = _safe_platform_allowlist(safe["platform_allowlist"])
        operations = _safe_runtime_operations(safe["allow_runtime_operations"])
        if not (
            safe["mode"] == "controlled_runtime_fake_delivery"
            and safe["delivery_boundary"] == "fake_send_only"
            and operations == list(_BRIDGE_RUNTIME_OPERATIONS)
        ):
            _raise("invalid_pe2a_policy")
        return {**safe, "platform_allowlist": allowlist, "allow_runtime_operations": operations, "timeout_ms": timeout_ms}
    _raise("invalid_pe2a_policy")


def _validate_ingress_envelope(value: object) -> dict[str, object]:
    safe = _plain_dict(value, error="invalid_ingress_envelope")
    _reject_unsafe_material(safe, error="invalid_ingress_envelope")
    if set(safe) != _ENVELOPE_FIELDS:
        _raise("invalid_ingress_envelope")
    if safe["type"] != PE2A_INGRESS_ENVELOPE_TYPE:
        _raise("invalid_ingress_envelope")
    if safe["platform"] != "sachima" or safe["source"] != "loopback_or_synthetic_pe2a":
        _raise("invalid_ingress_envelope")
    auth = _plain_dict(safe["auth"], error="invalid_ingress_envelope")
    if set(auth) != _AUTH_FIELDS or auth["hmac_verified"] is not True:
        _raise("invalid_ingress_envelope")
    policy_label = _safe_operator_label(auth["policy_label"])
    visible = _visible_surfaces(safe["visible_surfaces"])
    refs = _claim_refs(safe["claim_refs"])
    _empty_list(safe["side_effects"], error="invalid_ingress_envelope")
    result = {
        "type": PE2A_INGRESS_ENVELOPE_TYPE,
        "platform": "sachima",
        "source": "loopback_or_synthetic_pe2a",
        "session_label": _safe_label(safe["session_label"]),
        "turn_label": _safe_label(safe["turn_label"]),
        "turn_discriminator": _safe_label(safe["turn_discriminator"]),
        "auth": {"hmac_verified": True, "policy_label": policy_label},
        "visible_surfaces": visible,
        "claim_refs": refs,
        "side_effects": [],
    }
    _assert_no_forbidden_rendered_material(result, error="invalid_ingress_envelope")
    return result


def _visible_surfaces(value: object) -> dict[str, object]:
    safe = _plain_dict(value, error="invalid_ingress_envelope")
    if set(safe) != _VISIBLE_SURFACE_FIELDS:
        _raise("invalid_ingress_envelope")
    final_text = _exact_bool(safe["final_text"], error="invalid_ingress_envelope")
    rich_count = _bounded_int(safe["rich_card_count"], minimum=0, maximum=5, error="invalid_ingress_envelope")
    media_count = _bounded_int(safe["media_count"], minimum=0, maximum=5, error="invalid_ingress_envelope")
    if not final_text and rich_count == 0 and media_count == 0:
        _raise("invalid_ingress_envelope")
    return {"final_text": final_text, "rich_card_count": rich_count, "media_count": media_count}


def _claim_refs(value: object) -> dict[str, object]:
    safe = _plain_dict(value, error="invalid_ingress_envelope")
    if set(safe) != _CLAIM_REF_FIELDS:
        _raise("invalid_ingress_envelope")
    delivery_refs = _plain_list(safe["delivery_refs"], error="invalid_ingress_envelope")
    artifact_refs = _plain_list(safe["artifact_refs"], error="invalid_ingress_envelope")
    if not (1 <= len(delivery_refs) <= 10):
        _raise("invalid_ingress_envelope")
    safe_delivery_refs = [_safe_ref(item, regex=_DELIVERY_REF_RE, error="invalid_ingress_envelope") for item in delivery_refs]
    if len(set(safe_delivery_refs)) != len(safe_delivery_refs):
        _raise("invalid_ingress_envelope")
    safe_artifact_refs = [_safe_ref(item, regex=_ARTIFACT_REF_RE, error="invalid_ingress_envelope") for item in artifact_refs]
    return {
        "input_ref": _safe_ref(safe["input_ref"], regex=_INPUT_REF_RE, error="invalid_ingress_envelope"),
        "delivery_refs": safe_delivery_refs,
        "artifact_refs": safe_artifact_refs,
    }


def _delivery_plan_from_envelope(envelope: dict[str, object]) -> list[dict[str, object]]:
    visible = envelope["visible_surfaces"]
    assert type(visible) is dict
    refs = envelope["claim_refs"]
    assert type(refs) is dict
    delivery_refs = refs["delivery_refs"]
    artifact_refs = refs["artifact_refs"]
    assert type(delivery_refs) is list
    assert type(artifact_refs) is list
    surfaces: list[str] = []
    for _ in range(int(visible["rich_card_count"])):
        surfaces.append("rich_card")
    for _ in range(int(visible["media_count"])):
        surfaces.append("media")
    if visible["final_text"] is True:
        surfaces.append("final_text")
    if len(delivery_refs) < len(surfaces):
        _raise("invalid_ingress_envelope")
    plan: list[dict[str, object]] = []
    for index, surface in enumerate(surfaces):
        artifact_ref = artifact_refs[0] if artifact_refs and surface in {"artifact", "media"} else None
        plan.append(
            {
                "surface": surface,
                "delivery_ref": delivery_refs[index],
                "artifact_ref": artifact_ref,
                "idempotency_key": f"pe2a_{str(envelope['turn_discriminator']).removeprefix('safe_')}_{index}",
            }
        )
    return plan


def _start_transaction_request(*, workflow_id: str, envelope: dict[str, object]) -> dict[str, object]:
    return {
        "operation": "start_transaction",
        "workflow_id": workflow_id,
        "transaction_id": workflow_id,
        "input_ref": envelope["claim_refs"]["input_ref"],  # type: ignore[index]
        "turn_discriminator": envelope["turn_discriminator"],
        "side_effects": [],
    }


def _record_operation_request(*, workflow_id: str, envelope: dict[str, object]) -> dict[str, object]:
    visible = envelope["visible_surfaces"]
    assert type(visible) is dict
    return {
        "operation": "record_operation",
        "workflow_id": workflow_id,
        "transaction_id": workflow_id,
        "event_ref": "runtime_event_operation_" + _digest_text(str(envelope["turn_discriminator"])),
        "kind": "ingress_envelope_accepted",
        "surface_counts": {
            "final_text": 1 if visible["final_text"] is True else 0,
            "rich_card": visible["rich_card_count"],
            "media": visible["media_count"],
        },
        "side_effects": [],
    }


def _plan_delivery_request(*, workflow_id: str, delivery_plan: list[dict[str, object]]) -> dict[str, object]:
    return {
        "operation": "plan_delivery",
        "workflow_id": workflow_id,
        "transaction_id": workflow_id,
        "delivery_refs": [item["delivery_ref"] for item in delivery_plan],
        "surfaces": [item["surface"] for item in delivery_plan],
        "side_effects": [],
    }


def _record_delivery_ack_request(
    *,
    workflow_id: str,
    item: dict[str, object],
    ack: dict[str, object],
) -> dict[str, object]:
    return {
        "operation": "record_delivery_ack",
        "workflow_id": workflow_id,
        "transaction_id": workflow_id,
        "delivery_ref": item["delivery_ref"],
        "ack_ref": ack["ack_ref"],
        "surface": item["surface"],
        "status": "sent",
        "side_effects": [],
    }


def _query_transaction_request(*, workflow_id: str) -> dict[str, object]:
    return {
        "operation": "query_transaction",
        "workflow_id": workflow_id,
        "transaction_id": workflow_id,
        "side_effects": [],
    }


def _fake_send_payload(item: dict[str, object]) -> dict[str, object]:
    surface = str(item["surface"])
    content_by_surface = {
        "progress_card": "任务：PE-2A controlled runtime fake delivery proof",
        "rich_card": "卡片：PE-2A controlled runtime fake delivery proof",
        "final_text": "最终回复：PE-2A controlled runtime fake delivery proof",
        "media": "媒体占位：pe2a_safe_media_ref",
        "artifact": "产物引用：runtime_artifact_0",
    }
    metadata: dict[str, object] = {
        "surface": surface,
        "delivery_ref": item["delivery_ref"],
        "idempotency_key": item["idempotency_key"],
        "intent_summary": "PE-2A controlled runtime fake delivery proof",
    }
    if item.get("artifact_ref"):
        metadata["artifact_ref"] = item["artifact_ref"]
    return {
        "chat_id": "pe2a_local_chat",
        "content": content_by_surface[surface],
        "reply_to": "pe2a_local_turn",
        "metadata": metadata,
    }


async def _runtime_call(
    handle: Any,
    request: dict[str, object],
    *,
    expected_operation: str,
    workflow_id: str,
    timeout_ms: int,
) -> dict[str, object]:
    _reject_unsafe_material(request, error="unsafe_runtime_request")
    try:
        result = handle(request)
        if not inspect.isawaitable(result):
            raise RuntimeOperationFailed()
        awaited = await asyncio.wait_for(result, timeout=timeout_ms / 1000.0)
    except TimeoutError as exc:
        raise RuntimeOperationFailed() from exc
    except RuntimeOperationFailed:
        raise
    except Exception as exc:
        raise RuntimeOperationFailed() from exc
    if type(awaited) is not dict:
        raise UnsafeRuntimeOutput()
    try:
        _reject_unsafe_material(awaited, error="unsafe_runtime_output")
    except ValueError as exc:
        raise UnsafeRuntimeOutput() from exc
    if awaited.get("operation") != expected_operation:
        raise UnsafeRuntimeOutput()
    if awaited.get("workflow_id") != workflow_id:
        raise UnsafeRuntimeOutput()
    if awaited.get("transaction_id") != workflow_id:
        raise UnsafeRuntimeOutput()
    return awaited


def _validate_runtime_result(result: dict[str, object], *, expected_operation: str, workflow_id: str) -> None:
    if result.get("ok") is not True or result.get("operation") != expected_operation:
        raise RuntimeOperationFailed()
    if result.get("workflow_id") != workflow_id or result.get("transaction_id") != workflow_id:
        raise UnsafeRuntimeOutput()
    _empty_list(result.get("side_effects", []), error="unsafe_runtime_output")


def _validate_plan_result(
    result: dict[str, object],
    *,
    workflow_id: str,
    delivery_plan: list[dict[str, object]],
) -> None:
    _validate_runtime_result(result, expected_operation="plan_delivery", workflow_id=workflow_id)
    expected_refs = [item["delivery_ref"] for item in delivery_plan]
    if result.get("delivery_refs") is not None and result.get("delivery_refs") != expected_refs:
        raise UnsafeRuntimeOutput()
    expected_surfaces = [item["surface"] for item in delivery_plan]
    if result.get("surfaces") is not None and result.get("surfaces") != expected_surfaces:
        raise UnsafeRuntimeOutput()


def _validate_ack_result(
    result: dict[str, object],
    *,
    workflow_id: str,
    item: dict[str, object],
    ack: dict[str, object],
) -> None:
    _validate_runtime_result(result, expected_operation="record_delivery_ack", workflow_id=workflow_id)
    if result.get("delivery_ref") != item["delivery_ref"]:
        raise UnsafeRuntimeOutput()
    if result.get("ack_ref") != ack["ack_ref"]:
        raise UnsafeRuntimeOutput()
    if result.get("surface") != item["surface"]:
        raise UnsafeRuntimeOutput()


def _validate_fake_send_response(response: object, item: dict[str, object]) -> dict[str, object]:
    safe = _plain_dict(response, error="fake_send_rejected")
    if safe.get("ok") is not True:
        raise FakeSendRejected()
    if set(safe) != {"ok", "message_id", "delivery_ref", "surface", "ack_ref", "duplicate"}:
        raise FakeSendRejected()
    message_id = safe.get("message_id")
    if type(message_id) is not str or re.fullmatch(r"fake-sachima-send-[0-9]{4}", message_id) is None:
        raise FakeSendRejected()
    if safe.get("delivery_ref") != item["delivery_ref"] or safe.get("surface") != item["surface"]:
        raise FakeSendRejected()
    ack_ref = _safe_ref(safe.get("ack_ref"), regex=re.compile(r"^runtime_event_delivery_ack_[0-9]{4}$"), error="fake_send_rejected")
    duplicate = _exact_bool(safe.get("duplicate", False), error="fake_send_rejected")
    return {"ack_ref": ack_ref, "duplicate": duplicate}


def _success_result(
    *,
    workflow_id: str,
    delivery_plan: list[dict[str, object]],
    ack_refs: list[str],
    delivery_events: list[dict[str, object]],
    runtime_counts: dict[str, int],
    fake_send_requests: int,
) -> dict[str, object]:
    surfaces = [str(item["surface"]) for item in delivery_plan]
    result = {
        "type": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_RESULT_TYPE,
        "version": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_VERSION,
        "ok": True,
        "verdict": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_SUCCESS_VERDICT,
        "operation": _OPERATION,
        "workflow_id": workflow_id,
        "transaction_id": workflow_id,
        "status": "completed",
        "duplicate": False,
        "runtime_operations": _operations_from_counts(runtime_counts),
        "runtime_call_counts": dict(runtime_counts),
        "delivery_surface_state": _delivery_surface_state(surfaces),
        "delivery_ack_refs": list(ack_refs),
        "delivery_events": list(delivery_events),
        "duplicate_ingress_refs": [],
        "rejected_probe_codes": [],
        "counts": _counts(
            accepted=1,
            runtime_counts=runtime_counts,
            fake_send_requests=fake_send_requests,
            ack_updates=len(ack_refs),
            duplicate=sum(1 for event in delivery_events if event.get("duplicate") is True),
            rejected=0,
        ),
        "negative_probes": {},
        "rollback_restore": {},
        "side_effects": [],
    }
    return _checked_result(result)


def _duplicate_result(previous: dict[str, object]) -> dict[str, object]:
    workflow_id = _safe_ref(previous.get("workflow_id"), regex=re.compile(r"^flowweaver_pe2a_[a-f0-9]{20}$"), error="invalid_pe2a_result")
    result = {
        "type": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_RESULT_TYPE,
        "version": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_VERSION,
        "ok": True,
        "verdict": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_SUCCESS_VERDICT,
        "operation": _OPERATION,
        "workflow_id": workflow_id,
        "transaction_id": workflow_id,
        "status": "duplicate",
        "duplicate": True,
        "runtime_operations": [],
        "runtime_call_counts": _runtime_counts(),
        "delivery_surface_state": _safe_plain_mapping(previous.get("delivery_surface_state")),
        "delivery_ack_refs": [],
        "delivery_events": [],
        "duplicate_ingress_refs": [workflow_id],
        "rejected_probe_codes": [],
        "counts": _counts(
            accepted=0,
            runtime_counts=_runtime_counts(),
            fake_send_requests=0,
            ack_updates=0,
            duplicate=1,
            rejected=0,
        ),
        "negative_probes": {},
        "rollback_restore": {},
        "side_effects": [],
    }
    return _checked_result(result)


def _error_result(
    error_code: str,
    *,
    status: str = "error",
    runtime_counts: dict[str, int] | None = None,
    counts: dict[str, int] | None = None,
    delivery_events: list[dict[str, object]] | None = None,
    duplicate_ingress_refs: list[str] | None = None,
    rejected_probe_codes: list[str] | None = None,
) -> dict[str, object]:
    safe_code = _safe_error_code(error_code)
    runtime_counts = dict(runtime_counts or _runtime_counts())
    result = {
        "type": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_RESULT_TYPE,
        "version": FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_VERSION,
        "ok": False,
        "operation": _OPERATION,
        "status": status,
        "error_code": safe_code,
        "runtime_operations": _operations_from_counts(runtime_counts),
        "runtime_call_counts": runtime_counts,
        "delivery_surface_state": _empty_delivery_surface_state(),
        "delivery_ack_refs": [],
        "delivery_events": delivery_events or [],
        "duplicate_ingress_refs": duplicate_ingress_refs or [],
        "rejected_probe_codes": rejected_probe_codes or ([safe_code] if safe_code not in {"disabled", "platform_not_allowlisted"} else []),
        "counts": counts or _counts(
            accepted=0,
            runtime_counts=runtime_counts,
            fake_send_requests=0,
            ack_updates=0,
            rejected=0 if safe_code in {"disabled", "platform_not_allowlisted"} else 1,
        ),
        "negative_probes": {},
        "rollback_restore": {},
        "side_effects": [],
    }
    return _checked_result(result)


def _sent_delivery_event(*, item: dict[str, object], ack_ref: str, duplicate: bool) -> dict[str, object]:
    return {
        "delivery_ref": item["delivery_ref"],
        "surface": item["surface"],
        "status": "sent",
        "ack_ref": ack_ref,
        "duplicate": duplicate,
    }


def _rejected_delivery_event(item: dict[str, object]) -> dict[str, object]:
    return {
        "delivery_ref": item["delivery_ref"],
        "surface": item["surface"],
        "status": "rejected",
        "error_code": "fake_send_rejected",
    }


def _counts(
    *,
    accepted: int,
    runtime_counts: dict[str, int],
    fake_send_requests: int,
    ack_updates: int,
    duplicate: int = 0,
    rejected: int,
) -> dict[str, int]:
    return {
        "accepted_ingress_envelopes": accepted,
        "runtime_start_requests": int(runtime_counts.get("start_transaction", 0)),
        "runtime_delivery_plan_requests": int(runtime_counts.get("plan_delivery", 0)),
        "fake_send_requests": fake_send_requests,
        "runtime_ack_updates": ack_updates,
        "duplicates": duplicate,
        "rejected_probes": rejected,
    }


def _operations_from_counts(counts: dict[str, int]) -> list[str]:
    operations: list[str] = []
    for operation in _BRIDGE_RUNTIME_OPERATIONS:
        operations.extend([operation] * int(counts.get(operation, 0)))
    return operations


def _runtime_counts() -> dict[str, int]:
    return {key: 0 for key in _RUNTIME_COUNTS_KEYS}


def _delivery_surface_state(surfaces: list[str]) -> dict[str, object]:
    return {
        "progress_card_sent": surfaces.count("progress_card"),
        "rich_cards_sent": surfaces.count("rich_card"),
        "final_text_sent": "final_text" in surfaces,
        "media_sent": surfaces.count("media"),
        "artifact_refs_sent": surfaces.count("artifact"),
        "surface_order": list(surfaces),
    }


def _empty_delivery_surface_state() -> dict[str, object]:
    return _delivery_surface_state([])


def _workflow_id(envelope: dict[str, object]) -> str:
    material = {
        "session_label": envelope["session_label"],
        "turn_label": envelope["turn_label"],
        "turn_discriminator": envelope["turn_discriminator"],
        "claim_refs": envelope["claim_refs"],
        "visible_surfaces": envelope["visible_surfaces"],
    }
    return "flowweaver_pe2a_" + hashlib.sha256(_stable_json(material)).hexdigest()[:20]


def _safe_runtime_operations(value: object) -> list[str]:
    operations = _plain_list(value, error="invalid_pe2a_result")
    safe: list[str] = []
    for operation in operations:
        if type(operation) is not str or operation not in _ALLOWED_RUNTIME_OPERATIONS:
            _raise("invalid_pe2a_result")
        safe.append(operation)
    return safe


def _safe_delivery_ack_refs(value: object) -> list[str]:
    refs = _plain_list(value, error="invalid_pe2a_result")
    safe: list[str] = []
    ack_re = re.compile(r"^runtime_event_delivery_ack_[0-9]{4}$")
    for ref in refs:
        safe.append(_safe_ref(ref, regex=ack_re, error="invalid_pe2a_result"))
    if len(set(safe)) != len(safe):
        _raise("invalid_pe2a_result")
    return safe


def _safe_delivery_events(value: object) -> list[dict[str, object]]:
    events = _plain_list(value, error="invalid_pe2a_result")
    safe: list[dict[str, object]] = []
    seen_ack_refs: set[str] = set()
    for event in events:
        item = _plain_dict(event, error="invalid_pe2a_result")
        status = item.get("status")
        if status == "sent":
            if set(item) != {"delivery_ref", "surface", "status", "ack_ref", "duplicate"}:
                _raise("invalid_pe2a_result")
            ack_ref = _safe_ref(item["ack_ref"], regex=re.compile(r"^runtime_event_delivery_ack_[0-9]{4}$"), error="invalid_pe2a_result")
            if ack_ref in seen_ack_refs:
                _raise("invalid_pe2a_result")
            seen_ack_refs.add(ack_ref)
            safe.append(
                {
                    "delivery_ref": _safe_ref(item["delivery_ref"], regex=_DELIVERY_REF_RE, error="invalid_pe2a_result"),
                    "surface": _safe_surface(item["surface"], error="invalid_pe2a_result"),
                    "status": "sent",
                    "ack_ref": ack_ref,
                    "duplicate": _exact_bool(item["duplicate"], error="invalid_pe2a_result"),
                }
            )
            continue
        if status == "rejected":
            if set(item) != {"delivery_ref", "surface", "status", "error_code"}:
                _raise("invalid_pe2a_result")
            if item["error_code"] != "fake_send_rejected":
                _raise("invalid_pe2a_result")
            safe.append(
                {
                    "delivery_ref": _safe_ref(item["delivery_ref"], regex=_DELIVERY_REF_RE, error="invalid_pe2a_result"),
                    "surface": _safe_surface(item["surface"], error="invalid_pe2a_result"),
                    "status": "rejected",
                    "error_code": "fake_send_rejected",
                }
            )
            continue
        _raise("invalid_pe2a_result")
    return safe


def _safe_duplicate_ingress_refs(value: object) -> list[str]:
    refs = _plain_list(value, error="invalid_pe2a_result")
    safe: list[str] = []
    ref_re = re.compile(r"^flowweaver_pe2a_[a-f0-9]{20}$")
    for ref in refs:
        safe.append(_safe_ref(ref, regex=ref_re, error="invalid_pe2a_result"))
    if len(set(safe)) != len(safe):
        _raise("invalid_pe2a_result")
    return safe


def _safe_rejected_probe_codes(value: object) -> list[str]:
    codes = _plain_list(value, error="invalid_pe2a_result")
    allowed = {"fake_send_surface_required", "fake_send_rejected", "runtime_operation_failed", "unsafe_runtime_output", "invalid_ingress_envelope"}
    safe: list[str] = []
    for code in codes:
        if type(code) is not str or code not in allowed:
            _raise("invalid_pe2a_result")
        safe.append(code)
    return safe


def _safe_platform_allowlist(value: object) -> list[str]:
    items = _plain_list(value, error="invalid_pe2a_policy")
    safe: list[str] = []
    for item in items:
        if type(item) is not str or item != "sachima":
            _raise("invalid_pe2a_policy")
        if item not in safe:
            safe.append(item)
    return safe


def _safe_plain_mapping(value: object) -> dict[str, object]:
    safe = _plain_dict(value, error="invalid_pe2a_result")
    _reject_unsafe_material(safe, error="invalid_pe2a_result")
    return safe


def _safe_surface(value: object, *, error: str) -> str:
    if type(value) is not str or value not in _ALLOWED_SURFACES:
        _raise(error)
    return value


def _safe_operator_label(value: object) -> str:
    if type(value) is not str or not (1 <= len(value) <= 64):
        _raise("invalid_ingress_envelope")
    if value != "allowlisted_test_operator":
        _raise("invalid_ingress_envelope")
    return value


def _safe_label(value: object) -> str:
    if type(value) is not str or not _SAFE_LABEL_RE.fullmatch(value):
        _raise("invalid_ingress_envelope")
    lowered = value.lower()
    if any(prefix in lowered for prefix in _PRIVATE_PREFIXES):
        _raise("invalid_ingress_envelope")
    if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
        _raise("invalid_ingress_envelope")
    return value


def _safe_ref(value: object, *, regex: re.Pattern[str], error: str) -> str:
    if type(value) is not str or regex.fullmatch(value) is None:
        _raise(error)
    lowered = value.lower()
    if any(prefix in lowered for prefix in _PRIVATE_PREFIXES):
        _raise(error)
    if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
        _raise(error)
    return value


def _safe_base_sha(value: object) -> str:
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{7,40}", value):
        _raise("invalid_base_sha")
    return value


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


def _reject_unsafe_material(value: object, *, error: str) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _raise(error)
            lowered = key.lower()
            if lowered in _UNSAFE_EXACT_KEYS or any(marker in lowered for marker in _UNSAFE_KEY_MARKERS):
                _raise(error)
            _reject_unsafe_material(item, error=error)
        return
    if type(value) is list:
        for item in value:
            _reject_unsafe_material(item, error=error)
        return
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is str:
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
            _raise(error)
        if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
            _raise(error)
        return
    _raise(error)


def _assert_no_forbidden_rendered_material(value: object, *, error: str) -> None:
    rendered = repr(value).lower()
    if any(marker in rendered for marker in _NO_LEAK_MARKERS):
        _raise(error)


def _checked_result(result: dict[str, object]) -> dict[str, object]:
    if set(result) - _RESULT_FIELDS:
        raise RuntimeError("unsafe_output")
    _assert_no_forbidden_rendered_material(result, error="unsafe_output")
    return result


def _safe_error_code(value: object) -> str:
    allowed = {
        "disabled",
        "platform_not_allowlisted",
        "invalid_pe2a_policy",
        "invalid_ingress_envelope",
        "runtime_control_surface_required",
        "fake_send_surface_required",
        "runtime_operation_failed",
        "unsafe_runtime_output",
        "fake_send_rejected",
    }
    return value if type(value) is str and value in allowed else "runtime_operation_failed"


def _stable_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _raise(error: str) -> None:
    raise ValueError(error) from None


class RuntimeOperationFailed(Exception):
    pass


class UnsafeRuntimeOutput(Exception):
    pass


class FakeSendRejected(Exception):
    pass


__all__ = [
    "FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_RESULT_TYPE",
    "FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_SUCCESS_VERDICT",
    "FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_VERSION",
    "FlowWeaverPE2AControlledRuntimeDeliveryBridge",
    "build_flowweaver_pe2a_evidence",
    "describe_flowweaver_pe2a_contract",
    "pe2a_controlled_runtime_delivery_policy",
    "run_flowweaver_pe2a_controlled_runtime_delivery",
    "scan_pe2a_no_leak",
]
