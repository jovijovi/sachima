"""Pure FlowWeaver durable runtime ingress contract projection."""

from __future__ import annotations

from collections.abc import Mapping

from gateway.flowweaver_mock_durable import (
    FLOWWEAVER_MOCK_DURABLE_ACCEPTED,
    FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE,
)
from gateway.flowweaver_runtime_identity import (
    FLOWWEAVER_RUNTIME_IDENTITY_ACCEPTED,
    FLOWWEAVER_RUNTIME_IDENTITY_STRATEGY,
    FLOWWEAVER_RUNTIME_IDENTITY_TYPE,
)
from gateway.flowweaver_shadow import (
    FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE,
    FLOWWEAVER_SHADOW_REPLAY_REPLAYED,
    describe_flowweaver_shadow_consumer_contract,
)
from gateway.flowweaver_shadow_dry_run import (
    FLOWWEAVER_SHADOW_DRY_RUN_PASSED,
    FLOWWEAVER_SHADOW_DRY_RUN_TYPE,
)

FLOWWEAVER_RUNTIME_CONTRACT_TYPE = "flowweaver.gateway.runtime_ingress_contract.v0"
FLOWWEAVER_RUNTIME_ENVELOPE_TYPE = "flowweaver.gateway.runtime_ingress_envelope.v0"
FLOWWEAVER_RUNTIME_ACCEPTED = "accepted"
FLOWWEAVER_RUNTIME_REJECTED = "rejected"
FLOWWEAVER_RUNTIME_MODEL_VERSION = "flowweaver.runtime.v0"

_ALLOWED_CONSUMER_INPUTS = [
    "shadow_consumer_contract",
    "shadow_replay_corpus",
    "mock_durable_projection",
    "shadow_dry_run_summary_optional",
]
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
_FORBIDDEN_MATERIAL = [
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
]
_FORBIDDEN_SIDE_EFFECTS = ["send", "edit", "render", "persist", "temporal", "log"]
_CLAIM_CHECK_POLICY = {
    "mode": "references_only",
    "allowed_reference_fields": ["ref", "kind", "count", "size", "checksum_hint"],
    "forbidden_material": list(_FORBIDDEN_MATERIAL),
}
_IDEMPOTENCY = {
    "strategy": "synthetic_index_v0",
    "transaction_key": "runtime_tx_replay_corpus",
    "intent_key_prefix": "runtime_intent_",
    "artifact_key_prefix": "runtime_artifact_",
    "delivery_key_prefix": "runtime_delivery_",
}
_ZERO_RECORD_COUNTS = {"transactions": 0, "intents": 0, "artifacts": 0, "deliveries": 0}
_EXPECTED_CORPUS_KEYS = {"type", "verdict", "reason", "entry_count", "entries", "side_effects"}
_EXPECTED_ENTRY_KEYS = {"index", "verdict", "reason", "checks", "side_effects"}
_EXPECTED_ENTRY_CHECK_KEYS = {
    "audit_ready",
    "consumer_view_valid",
    "snapshot_ref_stable",
    "audit_stable",
    "input_not_mutated",
    "side_effects_absent",
}
_EXPECTED_PROJECTION_KEYS = {
    "type",
    "verdict",
    "reason",
    "contract_type",
    "contract_version",
    "corpus_type",
    "corpus_verdict",
    "entry_count",
    "records",
    "checks",
    "side_effects",
}
_EXPECTED_PROJECTION_CHECK_KEYS = {
    "contract_descriptor_valid",
    "corpus_valid",
    "corpus_passed",
    "record_counts_match_entries",
    "payloads_absent",
    "side_effects_absent",
}
_EXPECTED_DRY_RUN_KEYS = {
    "type",
    "verdict",
    "reason",
    "entry_count",
    "replay_corpus_verdict",
    "mock_durable_verdict",
    "record_counts",
    "checks",
    "side_effects",
}
_EXPECTED_DRY_RUN_CHECK_KEYS = {
    "shadow_capture_present",
    "consumer_contract_valid",
    "replay_corpus_passed",
    "mock_durable_accepted",
    "record_counts_match_entries",
    "payloads_absent",
    "visible_side_effects_absent",
}


def describe_flowweaver_runtime_ingress_contract() -> dict[str, object]:
    """Return the safe runtime-ingress contract descriptor."""

    return {
        "type": FLOWWEAVER_RUNTIME_CONTRACT_TYPE,
        "contract_version": "flowweaver.v0",
        "runtime_model_version": FLOWWEAVER_RUNTIME_MODEL_VERSION,
        "allowed_consumer_inputs": list(_ALLOWED_CONSUMER_INPUTS),
        "accepted_source_types": {
            "shadow_consumer_contract": FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE,
            "shadow_replay_corpus": FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE,
            "mock_durable_projection": FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE,
            "shadow_dry_run_summary": FLOWWEAVER_SHADOW_DRY_RUN_TYPE,
        },
        "allowed_runtime_events": list(_ALLOWED_RUNTIME_EVENTS),
        "claim_check_policy": _claim_check_policy(),
        "idempotency_strategy": dict(_IDEMPOTENCY),
        "forbidden_output_fields": list(_FORBIDDEN_MATERIAL),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }


def build_flowweaver_runtime_ingress_envelope(
    contract_descriptor: Mapping[str, object],
    replay_corpus: Mapping[str, object],
    mock_durable_projection: Mapping[str, object],
    dry_run_summary: Mapping[str, object] | None = None,
    *,
    runtime_identity: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Project safe Phase 4F/4G/4H outputs into a narrow runtime envelope."""

    try:
        descriptor = _plain_copy_dict(contract_descriptor)
        if descriptor is None or not _source_contract_valid(descriptor):
            return _rejected(reason="invalid_contract")

        corpus = _plain_copy_dict(replay_corpus)
        if corpus is None:
            return _rejected(reason="invalid_corpus")
        corpus_entry_count = _validated_corpus_entry_count(corpus)
        if corpus_entry_count is None:
            if _corpus_not_passed(corpus):
                return _rejected(reason="corpus_not_passed")
            return _rejected(reason="invalid_corpus")

        projection = _plain_copy_dict(mock_durable_projection)
        if projection is None:
            return _rejected(reason="mock_durable_rejected")
        projection_counts = _validated_projection_counts(projection, entry_count=corpus_entry_count)
        if projection_counts is None:
            return _rejected(reason="mock_durable_rejected")

        dry_run_type = None
        dry_run_valid = True
        if dry_run_summary is not None:
            dry_run = _plain_copy_dict(dry_run_summary)
            if dry_run is None or not _dry_run_summary_valid(dry_run, entry_count=corpus_entry_count):
                return _rejected(reason="invalid_dry_run")
            dry_run_type = FLOWWEAVER_SHADOW_DRY_RUN_TYPE

        runtime_idempotency = dict(_IDEMPOTENCY)
        if runtime_identity is not None:
            runtime_idempotency = _idempotency_from_runtime_identity(runtime_identity)
            if runtime_idempotency is None:
                return _rejected(reason="runtime_identity_rejected")

        return {
            "type": FLOWWEAVER_RUNTIME_ENVELOPE_TYPE,
            "verdict": FLOWWEAVER_RUNTIME_ACCEPTED,
            "reason": "ok",
            "contract_type": FLOWWEAVER_RUNTIME_CONTRACT_TYPE,
            "contract_version": "flowweaver.v0",
            "runtime_model_version": FLOWWEAVER_RUNTIME_MODEL_VERSION,
            "source_contract_type": FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE,
            "source_corpus_type": FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE,
            "source_mock_durable_type": FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE,
            "source_dry_run_type": dry_run_type,
            "entry_count": corpus_entry_count,
            "record_counts": projection_counts,
            "idempotency": runtime_idempotency,
            "allowed_runtime_events": list(_ALLOWED_RUNTIME_EVENTS),
            "claim_check_policy": _claim_check_policy(),
            "checks": {
                "runtime_contract_valid": True,
                "source_contract_valid": True,
                "replay_corpus_passed": True,
                "mock_durable_accepted": True,
                "dry_run_summary_valid": dry_run_valid,
                "record_counts_match_entries": True,
                "payloads_absent": True,
                "claim_check_references_only": True,
                "side_effects_absent": True,
            },
            "side_effects": [],
        }
    except Exception:
        return _rejected(reason="invalid_contract")


def _claim_check_policy() -> dict[str, object]:
    return {
        "mode": _CLAIM_CHECK_POLICY["mode"],
        "allowed_reference_fields": list(_CLAIM_CHECK_POLICY["allowed_reference_fields"]),
        "forbidden_material": list(_FORBIDDEN_MATERIAL),
    }


def _idempotency_from_runtime_identity(identity: object) -> dict[str, str] | None:
    safe = _plain_copy_dict(identity)
    if safe is None:
        return None
    expected_keys = {
        "type",
        "verdict",
        "reason",
        "strategy",
        "transaction_id",
        "workflow_id",
        "idempotency_key",
        "checks",
        "side_effects",
    }
    if not _has_exact_string_keys(safe, expected_keys):
        return None
    transaction_id = safe.get("transaction_id")
    workflow_id = safe.get("workflow_id")
    idempotency_key = safe.get("idempotency_key")
    checks = safe.get("checks")
    if not (
        safe.get("type") == FLOWWEAVER_RUNTIME_IDENTITY_TYPE
        and safe.get("verdict") == FLOWWEAVER_RUNTIME_IDENTITY_ACCEPTED
        and safe.get("reason") == "ok"
        and safe.get("strategy") == FLOWWEAVER_RUNTIME_IDENTITY_STRATEGY
        and type(transaction_id) is str
        and workflow_id == transaction_id
        and type(idempotency_key) is str
        and _runtime_shadow_transaction_id(transaction_id)
        and _runtime_shadow_start_event_key(idempotency_key)
        and _identity_checks_valid(checks)
        and _empty_plain_list(safe.get("side_effects"))
    ):
        return None
    return {
        "strategy": FLOWWEAVER_RUNTIME_IDENTITY_STRATEGY,
        "transaction_key": transaction_id,
        "start_event_key": idempotency_key,
        "intent_key_prefix": "runtime_intent_",
        "artifact_key_prefix": "runtime_artifact_",
        "delivery_key_prefix": "runtime_delivery_",
    }


def _identity_checks_valid(value: object) -> bool:
    expected = {
        "snapshot_ref_valid",
        "ids_synthetic",
        "private_markers_absent",
        "secret_markers_absent",
        "source_values_not_exported",
    }
    return type(value) is dict and _has_exact_string_keys(value, expected) and all(value.get(key) is True for key in expected)


def _runtime_shadow_transaction_id(value: str) -> bool:
    prefix = "runtime_tx_shadow_"
    suffix = value[len(prefix) :] if value.startswith(prefix) else ""
    return len(suffix) == 20 and all(("0" <= char <= "9") or ("a" <= char <= "f") for char in suffix)


def _runtime_shadow_start_event_key(value: str) -> bool:
    prefix = "runtime_event_start_shadow_"
    suffix = value[len(prefix) :] if value.startswith(prefix) else ""
    return len(suffix) == 20 and all(("0" <= char <= "9") or ("a" <= char <= "f") for char in suffix)


def _plain_copy_dict(value: object) -> dict[str, object] | None:
    if type(value) is not dict:
        return None
    copied = _plain_copy(value)
    return copied if type(copied) is dict else None


def _plain_copy(value: object) -> object | None:
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


_INVALID = object()


def _has_exact_string_keys(value: dict[str, object], expected: set[str]) -> bool:
    keys = list(value.keys())
    return all(type(key) is str for key in keys) and set(keys) == expected


def _empty_plain_list(value: object) -> bool:
    return type(value) is list and len(value) == 0


def _source_contract_valid(value: dict[str, object]) -> bool:
    try:
        expected = describe_flowweaver_shadow_consumer_contract()
        copied_expected = _plain_copy_dict(expected)
        return copied_expected is not None and value == copied_expected
    except Exception:
        return False


def _corpus_not_passed(value: dict[str, object]) -> bool:
    return (
        _has_exact_string_keys(value, _EXPECTED_CORPUS_KEYS)
        and value.get("type") == FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE
        and value.get("verdict") in {"failed", "rejected"}
    )


def _validated_corpus_entry_count(value: dict[str, object]) -> int | None:
    try:
        if not _has_exact_string_keys(value, _EXPECTED_CORPUS_KEYS):
            return None
        entries = value.get("entries")
        entry_count = value.get("entry_count")
        if not (
            value.get("type") == FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE
            and value.get("verdict") == FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED
            and value.get("reason") == "ok"
            and _empty_plain_list(value.get("side_effects"))
            and type(entries) is list
            and type(entry_count) is int
            and entry_count == len(entries)
            and 1 <= entry_count <= 20
        ):
            return None
        if not all(_corpus_entry_valid(index, entry) for index, entry in enumerate(entries)):
            return None
        return entry_count
    except Exception:
        return None


def _corpus_entry_valid(index: int, value: object) -> bool:
    if type(value) is not dict or not _has_exact_string_keys(value, _EXPECTED_ENTRY_KEYS):
        return False
    checks = value.get("checks")
    return (
        value.get("index") == index
        and value.get("verdict") == FLOWWEAVER_SHADOW_REPLAY_REPLAYED
        and value.get("reason") == "ok"
        and _empty_plain_list(value.get("side_effects"))
        and type(checks) is dict
        and _has_exact_string_keys(checks, _EXPECTED_ENTRY_CHECK_KEYS)
        and all(checks.get(key) is True for key in _EXPECTED_ENTRY_CHECK_KEYS)
    )


def _validated_projection_counts(value: dict[str, object], *, entry_count: int) -> dict[str, int] | None:
    try:
        if not _has_exact_string_keys(value, _EXPECTED_PROJECTION_KEYS):
            return None
        records = value.get("records")
        checks = value.get("checks")
        if not (
            value.get("type") == FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE
            and value.get("verdict") == FLOWWEAVER_MOCK_DURABLE_ACCEPTED
            and value.get("reason") == "ok"
            and value.get("contract_type") == FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE
            and value.get("contract_version") == "flowweaver.v0"
            and value.get("corpus_type") == FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE
            and value.get("corpus_verdict") == FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED
            and value.get("entry_count") == entry_count
            and _empty_plain_list(value.get("side_effects"))
            and type(records) is dict
            and _projection_checks_valid(checks)
        ):
            return None
        if not _records_valid(records, entry_count=entry_count):
            return None
        return {"transactions": 1, "intents": entry_count, "artifacts": entry_count, "deliveries": entry_count}
    except Exception:
        return None


def _projection_checks_valid(value: object) -> bool:
    return (
        type(value) is dict
        and _has_exact_string_keys(value, _EXPECTED_PROJECTION_CHECK_KEYS)
        and all(value.get(key) is True for key in _EXPECTED_PROJECTION_CHECK_KEYS)
    )


def _records_valid(records: dict[str, object], *, entry_count: int) -> bool:
    try:
        if not _has_exact_string_keys(records, {"transaction", "intents", "artifacts", "deliveries"}):
            return False
        transaction = records.get("transaction")
        intents = records.get("intents")
        artifacts = records.get("artifacts")
        deliveries = records.get("deliveries")
        if not (
            type(transaction) is dict
            and _has_exact_string_keys(transaction, {"record_id", "status", "entry_count"})
            and transaction.get("record_id") == "mock_tx_replay_corpus"
            and transaction.get("status") == "succeeded"
            and transaction.get("entry_count") == entry_count
            and type(intents) is list
            and type(artifacts) is list
            and type(deliveries) is list
            and len(intents) == len(artifacts) == len(deliveries) == entry_count
        ):
            return False
        for index in range(entry_count):
            if not _intent_valid(intents[index], index=index):
                return False
            if not _artifact_valid(artifacts[index], index=index):
                return False
            if not _delivery_valid(deliveries[index], index=index):
                return False
        return True
    except Exception:
        return False


def _intent_valid(value: object, *, index: int) -> bool:
    return (
        type(value) is dict
        and _has_exact_string_keys(value, {"intent_id", "source_entry_index", "status", "replay_verdict"})
        and value.get("intent_id") == f"mock_intent_{index}"
        and value.get("source_entry_index") == index
        and value.get("status") == "succeeded"
        and value.get("replay_verdict") == FLOWWEAVER_SHADOW_REPLAY_REPLAYED
    )


def _artifact_valid(value: object, *, index: int) -> bool:
    return (
        type(value) is dict
        and _has_exact_string_keys(value, {"artifact_id", "intent_id", "kind", "status"})
        and value.get("artifact_id") == f"mock_artifact_{index}"
        and value.get("intent_id") == f"mock_intent_{index}"
        and value.get("kind") == "shadow_replay_verdict"
        and value.get("status") == "available"
    )


def _delivery_valid(value: object, *, index: int) -> bool:
    return (
        type(value) is dict
        and _has_exact_string_keys(value, {"delivery_id", "artifact_id", "surface", "status"})
        and value.get("delivery_id") == f"mock_delivery_{index}"
        and value.get("artifact_id") == f"mock_artifact_{index}"
        and value.get("surface") == "mock_consumer"
        and value.get("status") == "observed"
    )


def _dry_run_summary_valid(value: dict[str, object], *, entry_count: int) -> bool:
    try:
        record_counts = value.get("record_counts")
        checks = value.get("checks")
        return (
            _has_exact_string_keys(value, _EXPECTED_DRY_RUN_KEYS)
            and value.get("type") == FLOWWEAVER_SHADOW_DRY_RUN_TYPE
            and value.get("verdict") == FLOWWEAVER_SHADOW_DRY_RUN_PASSED
            and value.get("reason") == "ok"
            and value.get("entry_count") == entry_count
            and value.get("replay_corpus_verdict") == FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED
            and value.get("mock_durable_verdict") == FLOWWEAVER_MOCK_DURABLE_ACCEPTED
            and _empty_plain_list(value.get("side_effects"))
            and type(record_counts) is dict
            and _has_exact_string_keys(record_counts, {"intents", "artifacts", "deliveries"})
            and record_counts.get("intents") == entry_count
            and record_counts.get("artifacts") == entry_count
            and record_counts.get("deliveries") == entry_count
            and type(checks) is dict
            and _has_exact_string_keys(checks, _EXPECTED_DRY_RUN_CHECK_KEYS)
            and all(checks.get(key) is True for key in _EXPECTED_DRY_RUN_CHECK_KEYS)
        )
    except Exception:
        return False


def _rejected(*, reason: str) -> dict[str, object]:
    return {
        "type": FLOWWEAVER_RUNTIME_ENVELOPE_TYPE,
        "verdict": FLOWWEAVER_RUNTIME_REJECTED,
        "reason": reason,
        "contract_type": None,
        "contract_version": None,
        "runtime_model_version": FLOWWEAVER_RUNTIME_MODEL_VERSION,
        "source_contract_type": None,
        "source_corpus_type": None,
        "source_mock_durable_type": None,
        "source_dry_run_type": None,
        "entry_count": 0,
        "record_counts": dict(_ZERO_RECORD_COUNTS),
        "idempotency": None,
        "allowed_runtime_events": [],
        "claim_check_policy": _claim_check_policy(),
        "checks": {
            "runtime_contract_valid": False,
            "source_contract_valid": False,
            "replay_corpus_passed": False,
            "mock_durable_accepted": False,
            "dry_run_summary_valid": False,
            "record_counts_match_entries": False,
            "payloads_absent": True,
            "claim_check_references_only": True,
            "side_effects_absent": True,
        },
        "side_effects": [],
    }


__all__ = [
    "FLOWWEAVER_RUNTIME_ACCEPTED",
    "FLOWWEAVER_RUNTIME_CONTRACT_TYPE",
    "FLOWWEAVER_RUNTIME_ENVELOPE_TYPE",
    "FLOWWEAVER_RUNTIME_MODEL_VERSION",
    "FLOWWEAVER_RUNTIME_REJECTED",
    "build_flowweaver_runtime_ingress_envelope",
    "describe_flowweaver_runtime_ingress_contract",
]
