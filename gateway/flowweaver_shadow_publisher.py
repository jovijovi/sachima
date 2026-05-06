"""Pure default-off FlowWeaver Gateway shadow runtime publisher helper."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gateway.flowweaver_mock_durable import consume_flowweaver_shadow_corpus_as_mock_durable_state
from gateway.flowweaver_runtime_contract import (
    FLOWWEAVER_RUNTIME_ACCEPTED,
    FLOWWEAVER_RUNTIME_ENVELOPE_TYPE,
    FLOWWEAVER_RUNTIME_MODEL_VERSION,
    build_flowweaver_runtime_ingress_envelope,
)
from gateway.flowweaver_runtime_identity import (
    FLOWWEAVER_RUNTIME_IDENTITY_ACCEPTED,
    FLOWWEAVER_RUNTIME_IDENTITY_STRATEGY,
    FLOWWEAVER_RUNTIME_IDENTITY_TYPE,
    derive_flowweaver_runtime_identity,
)
from gateway.flowweaver_shadow import (
    FLOWWEAVER_SHADOW_CAPTURE_KEY,
    FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
    describe_flowweaver_shadow_consumer_contract,
    get_flowweaver_shadow_capture,
    is_flowweaver_shadow_enabled,
    replay_flowweaver_shadow_corpus,
)
from gateway.flowweaver_shadow_dry_run import (
    FLOWWEAVER_SHADOW_DRY_RUN_PASSED,
    FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY,
    is_flowweaver_shadow_dry_run_enabled,
)
from utils import is_truthy_value

FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_CONFIG_KEY = "flowweaver_shadow_runtime_publish"
FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY = "flowweaver_shadow_runtime_publication"
FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_TYPE = "flowweaver.gateway.shadow_runtime_publication.v0"
FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY = "ready"
FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_REJECTED = "rejected"

_TRANSACTION_ID = "runtime_tx_replay_corpus"
_START_OPERATION = "start_transaction"
_ACK_OPERATION = "record_delivery_ack"
_ALLOWED_ACK_STATUSES = {"sent", "failed", "acknowledged"}
_ALLOWED_ACK_SURFACES = {"final_text", "rich_card", "progress_card", "media", "prototype"}
_ZERO_RECORD_COUNTS = {"transactions": 0, "intents": 0, "artifacts": 0, "deliveries": 0}


def is_flowweaver_shadow_runtime_publish_enabled(task_tracker_config: object) -> bool:
    """Return True only under the full shadow + dry-run + publish gate."""

    if not isinstance(task_tracker_config, Mapping):
        return False
    return (
        is_flowweaver_shadow_enabled(task_tracker_config)
        and is_flowweaver_shadow_dry_run_enabled(task_tracker_config)
        and is_truthy_value(
            task_tracker_config.get(FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_CONFIG_KEY),
            default=False,
        )
    )


def build_flowweaver_delivery_ack_updates(delivery_state: object) -> list[dict[str, str]]:
    """Project Gateway-owned delivery state into synthetic ACK update requests."""

    state = _plain_copy_dict(delivery_state)
    if state is None:
        return []

    updates: list[dict[str, str]] = []
    final_text = state.get("final_text")
    if type(final_text) is dict and _plain_string_keys(final_text) and final_text.get("sent") is True:
        updates.append(_ack_update(surface="final_text", surface_index=0, target_index=len(updates), status="sent"))

    rich_cards = state.get("rich_cards_sent")
    if type(rich_cards) is list:
        rich_index = 0
        for item in rich_cards:
            if len(updates) >= 20:
                break
            if type(item) is not dict or not _plain_string_keys(item):
                continue
            updates.append(
                _ack_update(
                    surface="rich_card",
                    surface_index=rich_index,
                    target_index=len(updates),
                    status="sent",
                )
            )
            rich_index += 1
    return updates


def build_flowweaver_shadow_runtime_publication(agent_result: object) -> dict[str, object]:
    """Build a safe shadow runtime-start + delivery-ACK publication summary."""

    safe_agent_result = _plain_copy_dict(agent_result)
    if safe_agent_result is None:
        return _rejected(reason="invalid_shadow")

    if not _shadow_capture_present(safe_agent_result):
        return _rejected(reason="invalid_shadow")

    dry_run_summary = safe_agent_result.get(FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY)
    if not _dry_run_ready(dry_run_summary):
        return _rejected(reason="dry_run_missing")

    delivery_state = safe_agent_result.get("delivery_state")
    if delivery_state is not None and type(delivery_state) is not dict:
        return _rejected(reason="unsafe_delivery_state")

    try:
        shadow_capture = get_flowweaver_shadow_capture(safe_agent_result)
        if type(shadow_capture) is not dict:
            return _rejected(reason="invalid_shadow")
        identity_ref = _runtime_identity_ref_from_shadow_capture(shadow_capture)
        if identity_ref is None:
            return _rejected(reason="invalid_shadow")
        identity = derive_flowweaver_runtime_identity(identity_ref)
        if identity.get("type") != FLOWWEAVER_RUNTIME_IDENTITY_TYPE or identity.get("verdict") != FLOWWEAVER_RUNTIME_IDENTITY_ACCEPTED:
            return _rejected(reason="runtime_identity_rejected")
        descriptor = describe_flowweaver_shadow_consumer_contract()
        corpus = replay_flowweaver_shadow_corpus([safe_agent_result], attempts=2)
        projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)
        envelope = build_flowweaver_runtime_ingress_envelope(
            descriptor,
            corpus,
            projection,
            dry_run_summary,
            runtime_identity=identity,
        )
        if envelope.get("type") != FLOWWEAVER_RUNTIME_ENVELOPE_TYPE or envelope.get("verdict") != FLOWWEAVER_RUNTIME_ACCEPTED:
            return _rejected(reason="runtime_envelope_rejected")
        ack_updates = build_flowweaver_delivery_ack_updates(delivery_state or {})
        start_request = _start_request_from_envelope(envelope, ack_update_count=len(ack_updates))
        if start_request is None:
            return _rejected(reason="runtime_envelope_rejected")
        transaction_id = start_request["workflow_id"]
        return {
            "type": FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_TYPE,
            "verdict": FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY,
            "reason": "ok",
            "runtime_model_version": FLOWWEAVER_RUNTIME_MODEL_VERSION,
            "runtime_envelope_type": FLOWWEAVER_RUNTIME_ENVELOPE_TYPE,
            "transaction_id": transaction_id,
            "workflow_id": transaction_id,
            "runtime_identity": _runtime_identity_metadata(identity),
            "start_request": start_request,
            "ack_bridge": {
                "status": FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY,
                "updates": ack_updates,
            },
            "checks": {
                "shadow_capture_present": True,
                "dry_run_summary_valid": True,
                "runtime_envelope_valid": True,
                "start_request_safe": True,
                "delivery_ack_updates_safe": True,
                "payloads_absent": True,
                "visible_side_effects_absent": True,
                "runtime_side_effects_absent": True,
            },
            "side_effects": [],
        }
    except Exception:
        return _rejected(reason="runtime_envelope_rejected")


def attach_flowweaver_shadow_runtime_publication(
    agent_result: dict[str, Any],
    *,
    enabled: bool,
) -> dict[str, object] | None:
    """Attach a ready publication summary only under the explicit Phase 5D gate."""

    if type(agent_result) is not dict:
        return None
    if not enabled:
        agent_result.pop(FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY, None)
        return None
    summary = build_flowweaver_shadow_runtime_publication(agent_result)
    if summary.get("verdict") == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY:
        agent_result[FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY] = summary
    else:
        agent_result.pop(FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY, None)
    return summary


def _start_request_from_envelope(envelope: dict[str, object], *, ack_update_count: int) -> dict[str, object] | None:
    record_counts = _safe_record_counts(envelope.get("record_counts"))
    entry_count = envelope.get("entry_count")
    idempotency = envelope.get("idempotency")
    allowed_events = envelope.get("allowed_runtime_events")
    claim_check_policy = envelope.get("claim_check_policy")
    if not (
        type(entry_count) is int
        and entry_count > 0
        and type(idempotency) is dict
        and type(allowed_events) is list
        and all(type(event) is str for event in allowed_events)
        and _START_OPERATION in allowed_events
        and _ACK_OPERATION in allowed_events
        and type(claim_check_policy) is dict
    ):
        return None
    delivery_slot_count = _delivery_slot_count(record_counts, entry_count=entry_count, ack_update_count=ack_update_count)
    if delivery_slot_count is None:
        return None
    runtime_record_counts = dict(record_counts)
    runtime_record_counts["deliveries"] = delivery_slot_count
    transaction_key = idempotency.get("transaction_key")
    start_event_key = idempotency.get("start_event_key")
    if _legacy_idempotency(idempotency):
        transaction_key = _TRANSACTION_ID
        start_event_key = f"runtime_event_start_{_TRANSACTION_ID}"
    if not (_safe_runtime_transaction_id(transaction_key) and _safe_runtime_start_event_key(start_event_key)):
        return None
    return {
        "operation": _START_OPERATION,
        "workflow_id": transaction_key,
        "start_payload": {
            "transaction_id": transaction_key,
            "idempotency_key": start_event_key,
            "entry_count": entry_count,
            "record_counts": runtime_record_counts,
            "allowed_runtime_events": list(allowed_events),
            "claim_check_policy": _plain_copy_dict(claim_check_policy) or {},
        },
    }


def _runtime_identity_metadata(identity: dict[str, object]) -> dict[str, object]:
    return {
        "type": FLOWWEAVER_RUNTIME_IDENTITY_TYPE,
        "strategy": FLOWWEAVER_RUNTIME_IDENTITY_STRATEGY,
        "transaction_id": identity.get("transaction_id"),
        "workflow_id": identity.get("workflow_id"),
        "idempotency_key": identity.get("idempotency_key"),
    }


def _runtime_identity_ref_from_shadow_capture(shadow_capture: dict[str, object]) -> dict[str, object] | None:
    snapshot_ref = _plain_copy_dict(shadow_capture.get("snapshot_ref"))
    capture = _plain_copy_dict(shadow_capture.get("capture"))
    if snapshot_ref is None or capture is None:
        return None
    created_at = capture.get("created_at")
    if type(created_at) is not str:
        return None
    identity_ref = dict(snapshot_ref)
    identity_ref["created_at"] = created_at
    return identity_ref


def _legacy_idempotency(value: dict[str, object]) -> bool:
    return (
        value.get("strategy") == "synthetic_index_v0"
        and value.get("transaction_key") == _TRANSACTION_ID
        and value.get("intent_key_prefix") == "runtime_intent_"
        and value.get("artifact_key_prefix") == "runtime_artifact_"
        and value.get("delivery_key_prefix") == "runtime_delivery_"
        and "start_event_key" not in value
    )


def _safe_runtime_transaction_id(value: object) -> bool:
    if type(value) is not str:
        return False
    if value == _TRANSACTION_ID:
        return True
    prefix = "runtime_tx_shadow_"
    suffix = value[len(prefix) :] if value.startswith(prefix) else ""
    return len(suffix) == 20 and all(("0" <= char <= "9") or ("a" <= char <= "f") for char in suffix)


def _safe_runtime_start_event_key(value: object) -> bool:
    if type(value) is not str:
        return False
    if value == f"runtime_event_start_{_TRANSACTION_ID}":
        return True
    prefix = "runtime_event_start_shadow_"
    suffix = value[len(prefix) :] if value.startswith(prefix) else ""
    return len(suffix) == 20 and all(("0" <= char <= "9") or ("a" <= char <= "f") for char in suffix)


def _ack_update(*, surface: str, surface_index: int, target_index: int, status: str) -> dict[str, str]:
    safe_surface = surface if surface in _ALLOWED_ACK_SURFACES else "prototype"
    safe_status = status if status in _ALLOWED_ACK_STATUSES else "sent"
    return {
        "event_type": _ACK_OPERATION,
        "delivery_key": f"runtime_event_delivery_ack_{safe_surface}_{surface_index}",
        "surface": safe_surface,
        "target_kind": "delivery",
        "target_id": f"runtime_delivery_{target_index}",
        "status": safe_status,
    }


def _shadow_capture_present(value: dict[str, object]) -> bool:
    return type(value.get(FLOWWEAVER_SHADOW_SNAPSHOT_KEY)) is dict and type(value.get(FLOWWEAVER_SHADOW_CAPTURE_KEY)) is dict


def _dry_run_ready(value: object) -> bool:
    if type(value) is not dict or not _plain_string_keys(value):
        return False
    return value.get("verdict") == FLOWWEAVER_SHADOW_DRY_RUN_PASSED and value.get("reason") == "ok"


def _safe_record_counts(value: object) -> dict[str, int]:
    if type(value) is not dict or not _plain_string_keys(value):
        return dict(_ZERO_RECORD_COUNTS)
    result: dict[str, int] = {}
    for key in ("transactions", "intents", "artifacts", "deliveries"):
        item = value.get(key)
        if type(item) is not int or item < 0:
            return dict(_ZERO_RECORD_COUNTS)
        result[key] = item
    return result


def _delivery_slot_count(record_counts: dict[str, int], *, entry_count: int, ack_update_count: int) -> int | None:
    if type(ack_update_count) is not int or not (0 <= ack_update_count <= 20):
        return None
    if not (
        record_counts.get("transactions") == 1
        and record_counts.get("intents") == entry_count
        and record_counts.get("artifacts") == entry_count
        and type(record_counts.get("deliveries")) is int
    ):
        return None
    slot_count = max(record_counts["deliveries"], ack_update_count)
    if not (entry_count <= slot_count <= 20):
        return None
    return slot_count


def _plain_copy_dict(value: object) -> dict[str, object] | None:
    if type(value) is not dict:
        return None
    copied = _plain_copy(value)
    return copied if type(copied) is dict else None


def _plain_copy(value: object) -> object:
    if value is None or type(value) in {str, bool, int, float}:
        return value
    if type(value) is list:
        copied_items: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_items.append(copied)
        return copied_items
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


def _plain_string_keys(value: dict[str, object]) -> bool:
    return all(type(key) is str for key in value.keys())


_INVALID = object()


def _rejected(*, reason: str) -> dict[str, object]:
    return {
        "type": FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_TYPE,
        "verdict": FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_REJECTED,
        "reason": reason,
        "runtime_model_version": FLOWWEAVER_RUNTIME_MODEL_VERSION,
        "runtime_envelope_type": FLOWWEAVER_RUNTIME_ENVELOPE_TYPE,
        "transaction_id": None,
        "workflow_id": None,
        "start_request": None,
        "ack_bridge": {"status": FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_REJECTED, "updates": []},
        "checks": {
            "shadow_capture_present": False,
            "dry_run_summary_valid": False,
            "runtime_envelope_valid": False,
            "start_request_safe": False,
            "delivery_ack_updates_safe": True,
            "payloads_absent": True,
            "visible_side_effects_absent": True,
            "runtime_side_effects_absent": True,
        },
        "side_effects": [],
    }


__all__ = [
    "FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_CONFIG_KEY",
    "FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY",
    "FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_REJECTED",
    "FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY",
    "FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_TYPE",
    "attach_flowweaver_shadow_runtime_publication",
    "build_flowweaver_delivery_ack_updates",
    "build_flowweaver_shadow_runtime_publication",
    "is_flowweaver_shadow_runtime_publish_enabled",
]
