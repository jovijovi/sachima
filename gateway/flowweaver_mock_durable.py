"""Pure in-memory FlowWeaver mock durable consumer projection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from gateway.flowweaver_shadow import (
    FLOWWEAVER_SHADOW_AUDIT_TYPE,
    FLOWWEAVER_SHADOW_CAPTURE_KEY,
    FLOWWEAVER_SHADOW_CAPTURE_TYPE,
    FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE,
    FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED,
    FLOWWEAVER_SHADOW_REPLAY_REJECTED,
    FLOWWEAVER_SHADOW_REPLAY_REPLAYED,
    FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH,
    FLOWWEAVER_SHADOW_REPLAY_TYPE,
    FLOWWEAVER_SHADOW_REPLAY_UNSAFE,
    FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
)

FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE = "flowweaver.gateway.mock_durable_consumer.v0"
FLOWWEAVER_MOCK_DURABLE_ACCEPTED = "accepted"
FLOWWEAVER_MOCK_DURABLE_REJECTED = "rejected"
_EXPECTED_DESCRIPTOR_KEYS = {
    "type",
    "contract_version",
    "snapshot_key",
    "capture_key",
    "capture_type",
    "audit_type",
    "replay_type",
    "allowed_consumer_inputs",
    "allowed_consumers",
    "replay_verdicts",
    "forbidden_output_fields",
    "forbidden_side_effects",
    "bounds",
    "side_effects",
}
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
_EXPECTED_REPLAY_VERDICTS = [
    FLOWWEAVER_SHADOW_REPLAY_REPLAYED,
    FLOWWEAVER_SHADOW_REPLAY_REJECTED,
    FLOWWEAVER_SHADOW_REPLAY_UNSAFE,
    FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH,
    FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED,
]
_EXPECTED_FORBIDDEN_OUTPUT_FIELDS = [
    "snapshot",
    "capture",
    "transaction",
    "deliveries",
    "artifacts",
    "source",
    "raw_command",
    "raw_output",
    "stdout",
    "stderr",
    "card_json",
    "platform",
    "chat_id",
    "user_id",
    "message_id",
    "delivery_ack",
]
_EXPECTED_FORBIDDEN_SIDE_EFFECTS = ["send", "edit", "render", "persist", "temporal", "log"]
_EXPECTED_BOUNDS = {
    "default_replay_attempts": 2,
    "max_replay_attempts": 5,
    "max_corpus_entries": 20,
}


def consume_flowweaver_shadow_corpus_as_mock_durable_state(
    contract_descriptor: Mapping[str, Any],
    replay_corpus: Mapping[str, Any],
) -> dict[str, Any]:
    """Project safe shadow descriptor/corpus output into synthetic durable records."""

    try:
        if not _contract_descriptor_valid(contract_descriptor):
            return _rejected(reason="invalid_contract")
        if _corpus_not_passed(replay_corpus):
            return _rejected(reason="corpus_not_passed")
        entry_indexes = _validated_corpus_entry_indexes(replay_corpus)
        if entry_indexes is None:
            return _rejected(reason="invalid_corpus")
        records = _build_records(entry_indexes)
        return {
            "type": FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE,
            "verdict": FLOWWEAVER_MOCK_DURABLE_ACCEPTED,
            "reason": "ok",
            "contract_type": FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE,
            "contract_version": "flowweaver.v0",
            "corpus_type": FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE,
            "corpus_verdict": FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED,
            "entry_count": len(entry_indexes),
            "records": records,
            "checks": {
                "contract_descriptor_valid": True,
                "corpus_valid": True,
                "corpus_passed": True,
                "record_counts_match_entries": _record_counts_match(entry_indexes, records),
                "payloads_absent": True,
                "side_effects_absent": True,
            },
            "side_effects": [],
        }
    except Exception:
        return _rejected(reason="invalid_corpus")


def _has_exact_string_keys(value: dict[Any, Any], expected: set[str]) -> bool:
    keys = list(value.keys())
    return all(type(key) is str for key in keys) and set(keys) == expected


def _empty_plain_list(value: object) -> bool:
    return type(value) is list and len(value) == 0


def _plain_string_list_equals(value: object, expected: list[str]) -> bool:
    return (
        type(value) is list
        and len(value) == len(expected)
        and all(type(item) is str for item in value)
        and value == expected
    )


def _plain_int_dict_equals(value: object, expected: dict[str, int]) -> bool:
    return (
        type(value) is dict
        and _has_exact_string_keys(value, set(expected.keys()))
        and all(type(value.get(key)) is int and value.get(key) == expected[key] for key in expected)
    )


def _contract_descriptor_valid(value: object) -> bool:
    try:
        if type(value) is not dict or not _has_exact_string_keys(value, _EXPECTED_DESCRIPTOR_KEYS):
            return False
        descriptor_type = value.get("type")
        contract_version = value.get("contract_version")
        snapshot_key = value.get("snapshot_key")
        capture_key = value.get("capture_key")
        capture_type = value.get("capture_type")
        audit_type = value.get("audit_type")
        replay_type = value.get("replay_type")
        side_effects = value.get("side_effects")
        return (
            type(descriptor_type) is str
            and descriptor_type == FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE
            and type(contract_version) is str
            and contract_version == "flowweaver.v0"
            and type(snapshot_key) is str
            and snapshot_key == FLOWWEAVER_SHADOW_SNAPSHOT_KEY
            and type(capture_key) is str
            and capture_key == FLOWWEAVER_SHADOW_CAPTURE_KEY
            and type(capture_type) is str
            and capture_type == FLOWWEAVER_SHADOW_CAPTURE_TYPE
            and type(audit_type) is str
            and audit_type == FLOWWEAVER_SHADOW_AUDIT_TYPE
            and type(replay_type) is str
            and replay_type == FLOWWEAVER_SHADOW_REPLAY_TYPE
            and _plain_string_list_equals(value.get("allowed_consumer_inputs"), ["agent_result_mapping"])
            and _plain_string_list_equals(
                value.get("allowed_consumers"),
                ["in_memory_test_probe", "future_flowweaver_runtime"],
            )
            and _plain_string_list_equals(value.get("replay_verdicts"), _EXPECTED_REPLAY_VERDICTS)
            and _plain_string_list_equals(value.get("forbidden_output_fields"), _EXPECTED_FORBIDDEN_OUTPUT_FIELDS)
            and _plain_string_list_equals(value.get("forbidden_side_effects"), _EXPECTED_FORBIDDEN_SIDE_EFFECTS)
            and _plain_int_dict_equals(value.get("bounds"), _EXPECTED_BOUNDS)
            and _empty_plain_list(side_effects)
        )
    except Exception:
        return False


def _corpus_not_passed(value: object) -> bool:
    try:
        if type(value) is not dict or not _has_exact_string_keys(value, _EXPECTED_CORPUS_KEYS):
            return False
        corpus_type = value.get("type")
        verdict = value.get("verdict")
        return (
            type(corpus_type) is str
            and corpus_type == FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE
            and type(verdict) is str
            and verdict in {FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED, FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED}
        )
    except Exception:
        return False


def _validated_corpus_entry_indexes(value: object) -> list[int] | None:
    try:
        if type(value) is not dict or not _has_exact_string_keys(value, _EXPECTED_CORPUS_KEYS):
            return None
        corpus_type = value.get("type")
        verdict = value.get("verdict")
        reason = value.get("reason")
        side_effects = value.get("side_effects")
        entries = value.get("entries")
        entry_count = value.get("entry_count")
        if not (
            type(corpus_type) is str
            and corpus_type == FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE
            and type(verdict) is str
            and verdict == FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED
            and type(reason) is str
            and reason == "ok"
            and _empty_plain_list(side_effects)
            and type(entries) is list
            and type(entry_count) is int
            and entry_count == len(entries)
            and 1 <= len(entries) <= 20
        ):
            return None
        if not all(_corpus_entry_valid(index, entry) for index, entry in enumerate(entries)):
            return None
        return list(range(len(entries)))
    except Exception:
        return None


def _corpus_entry_valid(index: int, value: object) -> bool:
    try:
        if type(value) is not dict or not _has_exact_string_keys(value, _EXPECTED_ENTRY_KEYS):
            return False
        entry_index = value.get("index")
        verdict = value.get("verdict")
        reason = value.get("reason")
        side_effects = value.get("side_effects")
        checks = value.get("checks")
        return (
            type(entry_index) is int
            and entry_index == index
            and type(verdict) is str
            and verdict == FLOWWEAVER_SHADOW_REPLAY_REPLAYED
            and type(reason) is str
            and reason == "ok"
            and _empty_plain_list(side_effects)
            and type(checks) is dict
            and _has_exact_string_keys(checks, _EXPECTED_ENTRY_CHECK_KEYS)
            and all(
                type(checks.get(key)) is bool and checks.get(key) is True
                for key in _EXPECTED_ENTRY_CHECK_KEYS
            )
        )
    except Exception:
        return False


def _build_records(entry_indexes: Sequence[int]) -> dict[str, Any]:
    intents: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    deliveries: list[dict[str, Any]] = []
    for index in entry_indexes:
        intent_id = f"mock_intent_{index}"
        artifact_id = f"mock_artifact_{index}"
        intents.append(
            {
                "intent_id": intent_id,
                "source_entry_index": index,
                "status": "succeeded",
                "replay_verdict": FLOWWEAVER_SHADOW_REPLAY_REPLAYED,
            }
        )
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "intent_id": intent_id,
                "kind": "shadow_replay_verdict",
                "status": "available",
            }
        )
        deliveries.append(
            {
                "delivery_id": f"mock_delivery_{index}",
                "artifact_id": artifact_id,
                "surface": "mock_consumer",
                "status": "observed",
            }
        )
    return {
        "transaction": {
            "record_id": "mock_tx_replay_corpus",
            "status": "succeeded",
            "entry_count": len(entry_indexes),
        },
        "intents": intents,
        "artifacts": artifacts,
        "deliveries": deliveries,
    }


def _record_counts_match(entry_indexes: Sequence[int], records: Mapping[str, Any]) -> bool:
    try:
        expected = len(entry_indexes)
        return (
            isinstance(records.get("transaction"), Mapping)
            and records["transaction"].get("entry_count") == expected
            and len(records.get("intents", [])) == expected
            and len(records.get("artifacts", [])) == expected
            and len(records.get("deliveries", [])) == expected
        )
    except Exception:
        return False


def _rejected(*, reason: str) -> dict[str, Any]:
    return {
        "type": FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE,
        "verdict": FLOWWEAVER_MOCK_DURABLE_REJECTED,
        "reason": reason,
        "contract_type": None,
        "contract_version": None,
        "corpus_type": None,
        "corpus_verdict": None,
        "entry_count": 0,
        "records": {
            "transaction": None,
            "intents": [],
            "artifacts": [],
            "deliveries": [],
        },
        "checks": {
            "contract_descriptor_valid": False,
            "corpus_valid": False,
            "corpus_passed": False,
            "record_counts_match_entries": False,
            "payloads_absent": True,
            "side_effects_absent": True,
        },
        "side_effects": [],
    }


__all__ = [
    "FLOWWEAVER_MOCK_DURABLE_ACCEPTED",
    "FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE",
    "FLOWWEAVER_MOCK_DURABLE_REJECTED",
    "consume_flowweaver_shadow_corpus_as_mock_durable_state",
]
