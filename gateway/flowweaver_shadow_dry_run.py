"""Pure in-memory FlowWeaver Gateway shadow dry-run helper."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gateway.flowweaver_mock_durable import (
    FLOWWEAVER_MOCK_DURABLE_ACCEPTED,
    consume_flowweaver_shadow_corpus_as_mock_durable_state,
)
from gateway.flowweaver_shadow import (
    FLOWWEAVER_SHADOW_CAPTURE_KEY,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED,
    FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
    describe_flowweaver_shadow_consumer_contract,
    is_flowweaver_shadow_enabled,
    replay_flowweaver_shadow_corpus,
)
from utils import is_truthy_value

FLOWWEAVER_SHADOW_DRY_RUN_CONFIG_KEY = "flowweaver_shadow_dry_run"
FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY = "flowweaver_shadow_dry_run"
FLOWWEAVER_SHADOW_DRY_RUN_TYPE = "flowweaver.gateway.shadow_dry_run.v0"
FLOWWEAVER_SHADOW_DRY_RUN_PASSED = "passed"
FLOWWEAVER_SHADOW_DRY_RUN_REJECTED = "rejected"
_ZERO_RECORD_COUNTS = {"intents": 0, "artifacts": 0, "deliveries": 0}


def is_flowweaver_shadow_dry_run_enabled(task_tracker_config: object) -> bool:
    """Return True only when shadow capture and dry-run are both explicitly enabled."""

    if not isinstance(task_tracker_config, Mapping):
        return False
    return is_flowweaver_shadow_enabled(task_tracker_config) and is_truthy_value(
        task_tracker_config.get(FLOWWEAVER_SHADOW_DRY_RUN_CONFIG_KEY),
        default=False,
    )


def run_flowweaver_gateway_shadow_dry_run(agent_result: Mapping[str, Any]) -> dict[str, Any]:
    """Run the safe shadow replay + mock durable chain and return a narrow summary."""

    try:
        if not _plain_shadow_agent_result(agent_result):
            return _rejected(reason="invalid_shadow")
        descriptor = describe_flowweaver_shadow_consumer_contract()
        corpus = replay_flowweaver_shadow_corpus([agent_result], attempts=2)
        if corpus.get("verdict") != FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED:
            return _rejected(reason="replay_failed", replay_corpus_verdict=_safe_verdict(corpus.get("verdict")))
        projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)
        if projection.get("verdict") != FLOWWEAVER_MOCK_DURABLE_ACCEPTED:
            return _rejected(
                reason="mock_durable_rejected",
                replay_corpus_verdict=FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED,
                mock_durable_verdict=_safe_verdict(projection.get("verdict")),
            )
        entry_count = _safe_nonnegative_int(projection.get("entry_count"))
        record_counts = _safe_record_counts(projection.get("records"))
        counts_match = (
            entry_count > 0
            and record_counts["intents"] == entry_count
            and record_counts["artifacts"] == entry_count
            and record_counts["deliveries"] == entry_count
        )
        if not counts_match:
            return _rejected(
                reason="mock_durable_rejected",
                replay_corpus_verdict=FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED,
                mock_durable_verdict=FLOWWEAVER_MOCK_DURABLE_ACCEPTED,
            )
        return {
            "type": FLOWWEAVER_SHADOW_DRY_RUN_TYPE,
            "verdict": FLOWWEAVER_SHADOW_DRY_RUN_PASSED,
            "reason": "ok",
            "entry_count": entry_count,
            "replay_corpus_verdict": FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED,
            "mock_durable_verdict": FLOWWEAVER_MOCK_DURABLE_ACCEPTED,
            "record_counts": record_counts,
            "checks": {
                "shadow_capture_present": True,
                "consumer_contract_valid": True,
                "replay_corpus_passed": True,
                "mock_durable_accepted": True,
                "record_counts_match_entries": counts_match,
                "payloads_absent": True,
                "visible_side_effects_absent": True,
            },
            "side_effects": [],
        }
    except Exception:
        return _rejected(reason="invalid_shadow")


def attach_flowweaver_gateway_shadow_dry_run(
    agent_result: dict[str, Any],
    *,
    enabled: bool,
) -> dict[str, Any] | None:
    """Attach an accepted dry-run summary under the explicit runtime gate."""

    if type(agent_result) is not dict:
        return None
    if not enabled:
        agent_result.pop(FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY, None)
        return None
    summary = run_flowweaver_gateway_shadow_dry_run(agent_result)
    if summary.get("verdict") == FLOWWEAVER_SHADOW_DRY_RUN_PASSED:
        agent_result[FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY] = summary
    else:
        agent_result.pop(FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY, None)
    return summary


def _plain_shadow_agent_result(value: object) -> bool:
    try:
        if type(value) is not dict:
            return False
        if not all(type(key) is str for key in value.keys()):
            return False
        snapshot = value.get(FLOWWEAVER_SHADOW_SNAPSHOT_KEY)
        capture = value.get(FLOWWEAVER_SHADOW_CAPTURE_KEY)
        return (
            type(snapshot) is dict
            and type(capture) is dict
            and _plain_data_tree(snapshot)
            and _plain_data_tree(capture)
        )
    except Exception:
        return False


def _plain_data_tree(value: object) -> bool:
    if value is None or type(value) in {str, bool, int, float}:
        return True
    if type(value) is list:
        return all(_plain_data_tree(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _plain_data_tree(item) for key, item in value.items())
    return False


def _safe_nonnegative_int(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


def _safe_record_counts(records: object) -> dict[str, int]:
    if type(records) is not dict:
        return dict(_ZERO_RECORD_COUNTS)
    return {
        "intents": len(records.get("intents")) if type(records.get("intents")) is list else 0,
        "artifacts": len(records.get("artifacts")) if type(records.get("artifacts")) is list else 0,
        "deliveries": len(records.get("deliveries")) if type(records.get("deliveries")) is list else 0,
    }


def _safe_verdict(value: object) -> str | None:
    return value if type(value) is str and value in {"passed", "failed", "rejected", "accepted"} else None


def _rejected(
    *,
    reason: str,
    replay_corpus_verdict: str | None = None,
    mock_durable_verdict: str | None = None,
) -> dict[str, Any]:
    return {
        "type": FLOWWEAVER_SHADOW_DRY_RUN_TYPE,
        "verdict": FLOWWEAVER_SHADOW_DRY_RUN_REJECTED,
        "reason": reason,
        "entry_count": 0,
        "replay_corpus_verdict": replay_corpus_verdict,
        "mock_durable_verdict": mock_durable_verdict,
        "record_counts": dict(_ZERO_RECORD_COUNTS),
        "checks": {
            "shadow_capture_present": False,
            "consumer_contract_valid": True,
            "replay_corpus_passed": False,
            "mock_durable_accepted": False,
            "record_counts_match_entries": False,
            "payloads_absent": True,
            "visible_side_effects_absent": True,
        },
        "side_effects": [],
    }


__all__ = [
    "FLOWWEAVER_SHADOW_DRY_RUN_CONFIG_KEY",
    "FLOWWEAVER_SHADOW_DRY_RUN_PASSED",
    "FLOWWEAVER_SHADOW_DRY_RUN_REJECTED",
    "FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY",
    "FLOWWEAVER_SHADOW_DRY_RUN_TYPE",
    "attach_flowweaver_gateway_shadow_dry_run",
    "is_flowweaver_shadow_dry_run_enabled",
    "run_flowweaver_gateway_shadow_dry_run",
]
