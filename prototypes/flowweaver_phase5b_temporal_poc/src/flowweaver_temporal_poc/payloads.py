"""Safe payload projection for the FlowWeaver Phase 5B Temporal POC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_POC_VERSION, FLOWWEAVER_TEMPORAL_TASK_QUEUE

RUNTIME_ENVELOPE_TYPE = "flowweaver.gateway.runtime_ingress_envelope.v0"
RUNTIME_CONTRACT_TYPE = "flowweaver.gateway.runtime_ingress_contract.v0"
RUNTIME_MODEL_VERSION = "flowweaver.runtime.v0"
RUNTIME_TRANSACTION_ID = "runtime_tx_replay_corpus"
RUNTIME_START_IDEMPOTENCY_KEY = "runtime_event_start_runtime_tx_replay_corpus"

ALLOWED_RUNTIME_EVENTS = (
    "start_transaction",
    "record_operation",
    "publish_artifact",
    "plan_delivery",
    "record_delivery_ack",
    "approve_intent",
    "reject_intent",
    "cancel_transaction",
    "resume_after_user_input",
)
ALLOWED_SURFACES = ("progress_card", "rich_card", "final_text", "media", "prototype")
ALLOWED_TARGET_KINDS = ("delivery", "intent", "artifact", "transaction")
ALLOWED_DELIVERY_STATUSES = ("sent", "failed", "acknowledged")
ALLOWED_DECISIONS = ("approved", "rejected")

_START_ENVELOPE_KEYS = {
    "type",
    "verdict",
    "reason",
    "contract_type",
    "contract_version",
    "runtime_model_version",
    "source_contract_type",
    "source_corpus_type",
    "source_mock_durable_type",
    "source_dry_run_type",
    "entry_count",
    "record_counts",
    "idempotency",
    "allowed_runtime_events",
    "claim_check_policy",
    "checks",
    "side_effects",
}
_RECORD_COUNT_KEYS = {"transactions", "intents", "artifacts", "deliveries"}
_IDEMPOTENCY_REQUIRED_KEYS = {
    "strategy",
    "transaction_key",
    "intent_key_prefix",
    "artifact_key_prefix",
    "delivery_key_prefix",
}
_IDEMPOTENCY_VARIABLE_KEYS = _IDEMPOTENCY_REQUIRED_KEYS | {"start_event_key"}
_CLAIM_CHECK_KEYS = {"mode", "allowed_reference_fields", "forbidden_material"}
_EXPECTED_FORBIDDEN_MATERIAL = (
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
)
_CHECK_KEYS = {
    "runtime_contract_valid",
    "source_contract_valid",
    "replay_corpus_passed",
    "mock_durable_accepted",
    "dry_run_summary_valid",
    "record_counts_match_entries",
    "payloads_absent",
    "claim_check_references_only",
    "side_effects_absent",
}

_PRIVATE_OR_RAW_PREFIXES = (
    "om_",
    "oc_",
    "ou_",
    "chat_",
    "message_",
    "user_",
    "platform_",
    "feishu_",
    "lark_",
    "telegram_",
)
_EMBEDDED_PRIVATE_MARKERS = (
    "om_",
    "oc_",
    "ou_",
    "chat",
    "message",
    "platform",
    "feishu",
    "lark",
    "telegram",
    "private",
)
_FORBIDDEN_SUBSTRINGS = (
    "token",
    "secret",
    "password",
    "credential",
    "api_key",
    "bearer",
    "sk-",
    "raw_",
    "card_json",
    "delivery_ack_payload",
    "platform_payload",
)
_INVALID = object()


@dataclass(frozen=True)
class RuntimeStartPayload:
    transaction_id: str
    idempotency_key: str
    entry_count: int
    record_counts: dict[str, int]
    allowed_runtime_events: tuple[str, ...]
    claim_check_policy: dict[str, Any]


@dataclass(frozen=True)
class DeliveryAckUpdate:
    delivery_key: str
    surface: str
    target_kind: str
    target_id: str
    status: str


@dataclass(frozen=True)
class HumanDecisionUpdate:
    event_id: str
    intent_id: str
    decision: str
    reason_ref: str | None = None


@dataclass(frozen=True)
class CancelTransactionUpdate:
    event_id: str
    reason_ref: str | None = None


@dataclass(frozen=True)
class ResumeUserInputUpdate:
    event_id: str
    input_ref: str


def build_start_payload_from_ingress_envelope(envelope: object) -> RuntimeStartPayload:
    safe = _plain_dict(envelope, error="invalid_runtime_envelope")
    if set(safe) != _START_ENVELOPE_KEYS:
        _raise("invalid_runtime_envelope")
    if not (
        safe["type"] == RUNTIME_ENVELOPE_TYPE
        and safe["verdict"] == "accepted"
        and safe["reason"] == "ok"
        and safe["contract_type"] == RUNTIME_CONTRACT_TYPE
        and safe["contract_version"] == "flowweaver.v0"
        and safe["runtime_model_version"] == RUNTIME_MODEL_VERSION
        and type(safe["entry_count"]) is int
        and 1 <= safe["entry_count"] <= 20
        and safe["side_effects"] == []
    ):
        _raise("invalid_runtime_envelope")

    counts = _record_counts(safe["record_counts"], entry_count=safe["entry_count"], error="invalid_runtime_envelope")
    idempotency = _plain_dict(safe["idempotency"], error="invalid_runtime_envelope")
    transaction_id, idempotency_key = _start_ids_from_idempotency(idempotency)

    allowed_runtime_events = _plain_string_tuple(safe["allowed_runtime_events"], error="invalid_runtime_envelope")
    if allowed_runtime_events != ALLOWED_RUNTIME_EVENTS:
        _raise("invalid_runtime_envelope")

    claim_check_policy = _claim_check_policy(safe["claim_check_policy"], error="invalid_runtime_envelope")
    checks = _plain_dict(safe["checks"], error="invalid_runtime_envelope")
    if set(checks) != _CHECK_KEYS or not all(checks[key] is True for key in _CHECK_KEYS):
        _raise("invalid_runtime_envelope")

    return RuntimeStartPayload(
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        entry_count=safe["entry_count"],
        record_counts=counts,
        allowed_runtime_events=allowed_runtime_events,
        claim_check_policy=claim_check_policy,
    )


def _start_ids_from_idempotency(idempotency: dict[str, object]) -> tuple[str, str]:
    keys = set(idempotency)
    if keys != _IDEMPOTENCY_REQUIRED_KEYS and keys != _IDEMPOTENCY_VARIABLE_KEYS:
        _raise("invalid_runtime_envelope")
    if not (
        idempotency["intent_key_prefix"] == "runtime_intent_"
        and idempotency["artifact_key_prefix"] == "runtime_artifact_"
        and idempotency["delivery_key_prefix"] == "runtime_delivery_"
    ):
        _raise("invalid_runtime_envelope")
    strategy = idempotency["strategy"]
    transaction_key = idempotency["transaction_key"]
    if strategy == "synthetic_index_v0" and keys == _IDEMPOTENCY_REQUIRED_KEYS and transaction_key == RUNTIME_TRANSACTION_ID:
        return RUNTIME_TRANSACTION_ID, RUNTIME_START_IDEMPOTENCY_KEY
    if strategy == "shadow_ref_hash_v0" and keys == _IDEMPOTENCY_VARIABLE_KEYS:
        transaction_id = _synthetic_id(transaction_key, prefixes=("runtime_tx_",), error="invalid_runtime_envelope")
        idempotency_key = _synthetic_id(
            idempotency["start_event_key"], prefixes=("runtime_event_",), error="invalid_runtime_envelope"
        )
        return transaction_id, idempotency_key
    _raise("invalid_runtime_envelope")


def delivery_ack_from_safe_update(update: object) -> DeliveryAckUpdate:
    safe = _plain_dict(update, error="invalid_delivery_ack_update")
    expected = {"event_type", "delivery_key", "surface", "target_kind", "target_id", "status"}
    if set(safe) != expected or safe["event_type"] != "record_delivery_ack":
        _raise("invalid_delivery_ack_update")
    try:
        result = DeliveryAckUpdate(
            delivery_key=_synthetic_id(safe["delivery_key"], prefixes=("runtime_event_",), error="invalid_delivery_ack_update"),
            surface=_closed_string(safe["surface"], ALLOWED_SURFACES, error="invalid_delivery_ack_update"),
            target_kind=_closed_string(safe["target_kind"], ALLOWED_TARGET_KINDS, error="invalid_delivery_ack_update"),
            target_id=_synthetic_id(safe["target_id"], prefixes=("runtime_delivery_",), error="invalid_delivery_ack_update"),
            status=_closed_string(safe["status"], ALLOWED_DELIVERY_STATUSES, error="invalid_delivery_ack_update"),
        )
    except ValueError:
        raise
    validate_delivery_ack_update(result)
    return result


def human_decision_from_safe_update(update: object) -> HumanDecisionUpdate:
    safe = _plain_dict(update, error="invalid_human_decision_update")
    expected = {"event_type", "event_id", "intent_id", "decision", "reason_ref"}
    if set(safe) != expected or safe["event_type"] not in {"approve_intent", "reject_intent"}:
        _raise("invalid_human_decision_update")
    event_type = safe["event_type"]
    decision = _closed_string(safe["decision"], ALLOWED_DECISIONS, error="invalid_human_decision_update")
    if (event_type == "approve_intent" and decision != "approved") or (
        event_type == "reject_intent" and decision != "rejected"
    ):
        _raise("invalid_human_decision_update")
    result = HumanDecisionUpdate(
        event_id=_synthetic_id(safe["event_id"], prefixes=("runtime_event_",), error="invalid_human_decision_update"),
        intent_id=_synthetic_id(safe["intent_id"], prefixes=("runtime_intent_",), error="invalid_human_decision_update"),
        decision=decision,
        reason_ref=_optional_claim_ref(safe["reason_ref"], error="invalid_human_decision_update"),
    )
    validate_human_decision_update(result, expected_decision=decision)
    return result


def cancel_transaction_from_safe_update(update: object) -> CancelTransactionUpdate:
    safe = _plain_dict(update, error="invalid_cancel_transaction_update")
    if set(safe) != {"event_type", "event_id", "reason_ref"} or safe["event_type"] != "cancel_transaction":
        _raise("invalid_cancel_transaction_update")
    result = CancelTransactionUpdate(
        event_id=_synthetic_id(safe["event_id"], prefixes=("runtime_event_",), error="invalid_cancel_transaction_update"),
        reason_ref=_optional_claim_ref(safe["reason_ref"], error="invalid_cancel_transaction_update"),
    )
    validate_cancel_transaction_update(result)
    return result


def resume_user_input_from_safe_update(update: object) -> ResumeUserInputUpdate:
    safe = _plain_dict(update, error="invalid_resume_user_input_update")
    if set(safe) != {"event_type", "event_id", "input_ref"} or safe["event_type"] != "resume_after_user_input":
        _raise("invalid_resume_user_input_update")
    result = ResumeUserInputUpdate(
        event_id=_synthetic_id(safe["event_id"], prefixes=("runtime_event_",), error="invalid_resume_user_input_update"),
        input_ref=_claim_ref(safe["input_ref"], error="invalid_resume_user_input_update"),
    )
    validate_resume_user_input_update(result)
    return result


def snapshot_to_safe_dict(snapshot: object) -> dict[str, object]:
    return _plain_dict(snapshot, error="invalid_temporal_snapshot")


def validate_start_payload(payload: RuntimeStartPayload) -> None:
    if type(payload) is not RuntimeStartPayload:
        _raise("invalid_start_payload")
    _synthetic_id(payload.transaction_id, prefixes=("runtime_tx_",), error="invalid_start_payload")
    _synthetic_id(payload.idempotency_key, prefixes=("runtime_event_",), error="invalid_start_payload")
    if type(payload.entry_count) is not int or not (1 <= payload.entry_count <= 20):
        _raise("invalid_start_payload")
    _record_counts(payload.record_counts, entry_count=payload.entry_count, error="invalid_start_payload")
    if tuple(payload.allowed_runtime_events) != ALLOWED_RUNTIME_EVENTS:
        _raise("invalid_start_payload")
    _claim_check_policy(payload.claim_check_policy, error="invalid_start_payload")


def validate_delivery_ack_update(update: DeliveryAckUpdate) -> None:
    if type(update) is not DeliveryAckUpdate:
        _raise("invalid_delivery_ack_update")
    _synthetic_id(update.delivery_key, prefixes=("runtime_event_",), error="invalid_delivery_ack_update")
    _closed_string(update.surface, ALLOWED_SURFACES, error="invalid_delivery_ack_update")
    _closed_string(update.target_kind, ALLOWED_TARGET_KINDS, error="invalid_delivery_ack_update")
    _synthetic_id(update.target_id, prefixes=("runtime_delivery_",), error="invalid_delivery_ack_update")
    _closed_string(update.status, ALLOWED_DELIVERY_STATUSES, error="invalid_delivery_ack_update")


def validate_human_decision_update(update: HumanDecisionUpdate, *, expected_decision: str | None = None) -> None:
    if type(update) is not HumanDecisionUpdate:
        _raise("invalid_human_decision_update")
    _synthetic_id(update.event_id, prefixes=("runtime_event_",), error="invalid_human_decision_update")
    _synthetic_id(update.intent_id, prefixes=("runtime_intent_",), error="invalid_human_decision_update")
    _closed_string(update.decision, ALLOWED_DECISIONS, error="invalid_human_decision_update")
    if expected_decision is not None and update.decision != expected_decision:
        _raise("invalid_human_decision_update")
    _optional_claim_ref(update.reason_ref, error="invalid_human_decision_update")


def validate_cancel_transaction_update(update: CancelTransactionUpdate) -> None:
    if type(update) is not CancelTransactionUpdate:
        _raise("invalid_cancel_transaction_update")
    _synthetic_id(update.event_id, prefixes=("runtime_event_",), error="invalid_cancel_transaction_update")
    _optional_claim_ref(update.reason_ref, error="invalid_cancel_transaction_update")


def validate_resume_user_input_update(update: ResumeUserInputUpdate) -> None:
    if type(update) is not ResumeUserInputUpdate:
        _raise("invalid_resume_user_input_update")
    _synthetic_id(update.event_id, prefixes=("runtime_event_",), error="invalid_resume_user_input_update")
    _claim_ref(update.input_ref, error="invalid_resume_user_input_update")


def validate_runtime_workflow_id(workflow_id: str) -> str:
    return _synthetic_id(workflow_id, prefixes=("runtime_tx_",), error="invalid_workflow_id")


def _record_counts(value: object, *, entry_count: int, error: str) -> dict[str, int]:
    counts = _plain_dict(value, error=error)
    if set(counts) != _RECORD_COUNT_KEYS:
        _raise(error)
    if not (
        counts["transactions"] == 1
        and counts["intents"] == entry_count
        and counts["artifacts"] == entry_count
        and counts["deliveries"] == entry_count
        and all(type(counts[key]) is int for key in _RECORD_COUNT_KEYS)
    ):
        _raise(error)
    return {key: counts[key] for key in ("transactions", "intents", "artifacts", "deliveries")}


def _claim_check_policy(value: object, *, error: str) -> dict[str, object]:
    policy = _plain_dict(value, error=error)
    if set(policy) != _CLAIM_CHECK_KEYS or policy["mode"] != "references_only":
        _raise(error)
    allowed = _plain_string_tuple(policy["allowed_reference_fields"], error=error)
    forbidden = _plain_string_tuple(policy["forbidden_material"], error=error)
    if allowed != ("ref", "kind", "count", "size", "checksum_hint"):
        _raise(error)
    if forbidden != _EXPECTED_FORBIDDEN_MATERIAL:
        _raise(error)
    return {
        "mode": "references_only",
        "allowed_reference_fields": tuple(allowed),
        "forbidden_material": tuple(forbidden),
    }


def _optional_claim_ref(value: object, *, error: str) -> str | None:
    if value is None:
        return None
    return _claim_ref(value, error=error)


def _claim_ref(value: object, *, error: str) -> str:
    return _synthetic_id(value, prefixes=("claim_ref_",), error=error)


def _closed_string(value: object, allowed: tuple[str, ...], *, error: str) -> str:
    if type(value) is not str or value not in allowed:
        _raise(error)
    return value


def _synthetic_id(value: object, *, prefixes: tuple[str, ...], error: str) -> str:
    if type(value) is not str or not value or len(value) > 128:
        _raise(error)
    if not value.startswith(prefixes):
        _raise(error)
    if any(value.startswith(prefix) for prefix in _PRIVATE_OR_RAW_PREFIXES):
        _raise(error)
    lowered = value.lower()
    matching_prefix = next((prefix for prefix in prefixes if lowered.startswith(prefix)), "")
    body = lowered[len(matching_prefix) :]
    if any(marker in body for marker in _EMBEDDED_PRIVATE_MARKERS):
        _raise(error)
    if any(marker in lowered for marker in _FORBIDDEN_SUBSTRINGS):
        _raise(error)
    if not all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in value):
        _raise(error)
    return value


def _plain_string_tuple(value: object, *, error: str) -> tuple[str, ...]:
    copied = _plain_copy(value)
    if type(copied) is not list or not all(type(item) is str for item in copied):
        _raise(error)
    return tuple(copied)


def _plain_dict(value: object, *, error: str) -> dict[str, object]:
    copied = _plain_copy(value)
    if type(copied) is not dict:
        _raise(error)
    return copied


def _plain_copy(value: object) -> object:
    if value is None or type(value) in {str, bool, int, float}:
        return value
    if type(value) is list:
        result: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            result.append(copied)
        return result
    if type(value) is tuple:
        result = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            result.append(copied)
        return result
    if type(value) is dict:
        result: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                return _INVALID
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            result[key] = copied
        return result
    return _INVALID


def _raise(error: str) -> None:
    raise ValueError(error) from None


__all__ = [
    "ALLOWED_DELIVERY_STATUSES",
    "ALLOWED_RUNTIME_EVENTS",
    "ALLOWED_SURFACES",
    "ALLOWED_TARGET_KINDS",
    "CancelTransactionUpdate",
    "DeliveryAckUpdate",
    "FLOWWEAVER_TEMPORAL_POC_VERSION",
    "FLOWWEAVER_TEMPORAL_TASK_QUEUE",
    "HumanDecisionUpdate",
    "RUNTIME_START_IDEMPOTENCY_KEY",
    "RUNTIME_TRANSACTION_ID",
    "ResumeUserInputUpdate",
    "RuntimeStartPayload",
    "build_start_payload_from_ingress_envelope",
    "cancel_transaction_from_safe_update",
    "delivery_ack_from_safe_update",
    "human_decision_from_safe_update",
    "resume_user_input_from_safe_update",
    "snapshot_to_safe_dict",
    "validate_cancel_transaction_update",
    "validate_delivery_ack_update",
    "validate_human_decision_update",
    "validate_resume_user_input_update",
    "validate_runtime_workflow_id",
    "validate_start_payload",
]
