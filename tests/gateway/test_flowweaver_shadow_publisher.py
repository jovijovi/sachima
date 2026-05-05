"""Tests for the FlowWeaver Phase 5D shadow runtime publisher helper."""

from __future__ import annotations

import copy
import subprocess
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from gateway.flowweaver_shadow import attach_flowweaver_shadow_snapshot
from gateway.flowweaver_shadow_dry_run import (
    FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY,
    attach_flowweaver_gateway_shadow_dry_run,
)
from gateway.flowweaver_shadow_publisher import (
    FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_CONFIG_KEY,
    FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY,
    FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_REJECTED,
    FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY,
    FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_TYPE,
    attach_flowweaver_shadow_runtime_publication,
    build_flowweaver_delivery_ack_updates,
    build_flowweaver_shadow_runtime_publication,
    is_flowweaver_shadow_runtime_publish_enabled,
)
from gateway.progress.events import TransactionSnapshot

PRIVATE_MESSAGE_ID = "om_" + "private_message"
PRIVATE_CHAT_ID = "oc_" + "private_chat"
PRIVATE_USER_ID = "ou_" + "private_user"
SECRET_SHAPED = "sk-" + "123456789012"


class FlickeringMapping(Mapping[str, Any]):
    def __init__(self, safe: dict[str, Any], unsafe: dict[str, Any]) -> None:
        self._safe = safe
        self._unsafe = unsafe
        self._reads: dict[str, int] = {}

    def __iter__(self) -> Iterator[str]:
        return iter(self._safe)

    def __len__(self) -> int:
        return len(self._safe)

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        self._reads[key] = self._reads.get(key, 0) + 1
        if self._reads[key] > 1 and key in self._unsafe:
            return self._unsafe[key]
        return self._safe.get(key, default)


class MutatingValue:
    def __init__(self) -> None:
        self.comparisons = 0

    def __eq__(self, other: object) -> bool:
        self.comparisons += 1
        return False

    def __repr__(self) -> str:
        return PRIVATE_MESSAGE_ID


def make_snapshot(*, index: int = 0) -> TransactionSnapshot:
    return TransactionSnapshot(
        transaction_id=f"session_shadow_publisher_{index}",
        title="Gateway shadow publisher task",
        status="completed",
        started_at=1000.0 + index,
        updated_at=1002.0 + index,
        completed_at=1002.0 + index,
        recent_operations=(),
    )


def make_shadow_agent_result(
    *,
    index: int = 0,
    final_text_sent: bool = True,
    rich_cards_sent: list[dict[str, Any]] | None = None,
    attach_dry_run: bool = True,
) -> dict[str, Any]:
    agent_result: dict[str, Any] = {
        "final_response": "done",
        "delivery_state": {
            "final_text": {"sent": final_text_sent, "reason": "stream_final_response"},
            "rich_cards_sent": rich_cards_sent or [],
        },
    }
    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(index=index),
        enabled=True,
        final_text="done",
    )
    assert attached is not None
    if attach_dry_run:
        dry_run_summary = attach_flowweaver_gateway_shadow_dry_run(agent_result, enabled=True)
        assert dry_run_summary is not None
        assert dry_run_summary["verdict"] == "passed"
    return agent_result


def test_shadow_runtime_publish_gate_is_default_off_and_requires_shadow_dry_run() -> None:
    assert is_flowweaver_shadow_runtime_publish_enabled({}) is False
    assert is_flowweaver_shadow_runtime_publish_enabled({FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_CONFIG_KEY: True}) is False
    assert (
        is_flowweaver_shadow_runtime_publish_enabled(
            {"flowweaver_shadow": True, FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_CONFIG_KEY: True}
        )
        is False
    )
    assert (
        is_flowweaver_shadow_runtime_publish_enabled(
            {
                "flowweaver_shadow": True,
                "flowweaver_shadow_dry_run": True,
                FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_CONFIG_KEY: True,
            }
        )
        is True
    )


def test_shadow_runtime_publisher_boundary_scans_are_diff_hunk_aware() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    base = subprocess.check_output(
        ["git", "merge-base", "HEAD", "origin/feature/sachima-channel"],
        cwd=repo_root,
        text=True,
    ).strip()
    diff = subprocess.check_output(
        ["git", "diff", "--unified=0", base, "--", "gateway/run.py", "gateway/flowweaver_shadow_publisher.py"],
        cwd=repo_root,
        text=True,
    )
    added_lines = [line[1:].strip() for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
    forbidden_runtime_terms = (
        "import temporalio",
        "flowweaver_runtime_client",
        "flowweaver_temporal_poc",
        "import mcp",
        "from mcp",
        "subprocess",
        "Popen",
        "docker",
        "Client.connect",
        "Worker",
        "start_workflow",
        "execute_update",
    )

    assert not [line for line in added_lines for term in forbidden_runtime_terms if term in line]


def test_shadow_runtime_publisher_changed_file_guard_allows_only_phase5d_files() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    changed = set(
        subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=repo_root, text=True).splitlines()
    )
    changed.update(
        subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo_root, text=True).splitlines()
    )
    allowed = {
        "docs/dev_log/2026-05-05-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge.md",
        "docs/plans/2026-05-05-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge.md",
        "gateway/flowweaver_shadow_publisher.py",
        "gateway/run.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
        "tests/gateway/test_flowweaver_shadow_publisher_run_hook.py",
        "tests/gateway/test_run_progress_topics.py",
    }
    forbidden_prefixes = ("gateway/platforms/", "tools/")
    forbidden_exact = {"run_agent.py", "model_tools.py", "toolsets.py", "mcp_serve.py"}

    assert changed <= allowed
    assert not [path for path in changed if path.startswith(forbidden_prefixes) or path in forbidden_exact]


def test_build_shadow_runtime_publication_returns_ready_safe_start_request() -> None:
    agent_result = make_shadow_agent_result()

    summary = build_flowweaver_shadow_runtime_publication(agent_result)
    rendered = repr(summary).lower()

    assert summary["type"] == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_TYPE
    assert summary["verdict"] == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY
    assert summary["reason"] == "ok"
    assert summary["runtime_model_version"] == "flowweaver.runtime.v0"
    assert summary["runtime_envelope_type"] == "flowweaver.gateway.runtime_ingress_envelope.v0"
    assert summary["transaction_id"] == "runtime_tx_replay_corpus"
    assert summary["workflow_id"] == "runtime_tx_replay_corpus"
    assert summary["side_effects"] == []
    assert summary["checks"] == {
        "shadow_capture_present": True,
        "dry_run_summary_valid": True,
        "runtime_envelope_valid": True,
        "start_request_safe": True,
        "delivery_ack_updates_safe": True,
        "payloads_absent": True,
        "visible_side_effects_absent": True,
        "runtime_side_effects_absent": True,
    }
    assert summary["start_request"]["operation"] == "start_transaction"
    assert summary["start_request"]["workflow_id"] == "runtime_tx_replay_corpus"
    payload = summary["start_request"]["start_payload"]
    assert payload["transaction_id"] == "runtime_tx_replay_corpus"
    assert payload["idempotency_key"] == "runtime_event_start_runtime_tx_replay_corpus"
    assert payload["entry_count"] == 1
    assert payload["record_counts"] == {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1}
    assert payload["claim_check_policy"]["mode"] == "references_only"
    assert "record_delivery_ack" in payload["allowed_runtime_events"]
    assert "flowweaver_shadow_snapshot" not in rendered
    assert "flowweaver_shadow_capture" not in rendered
    assert "session_shadow_publisher" not in rendered
    assert "final_response" not in rendered


def test_build_shadow_runtime_publication_rejects_missing_or_bad_inputs_without_echoing_values() -> None:
    safe = make_shadow_agent_result()
    cases = [
        ({"message_id": PRIVATE_MESSAGE_ID, "raw_command": "curl --" + "token=abc123"}, "invalid_shadow"),
        ({key: value for key, value in safe.items() if key != FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY}, "dry_run_missing"),
        ({**safe, FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY: {"verdict": PRIVATE_MESSAGE_ID}}, "dry_run_missing"),
        ({**safe, FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY: {**safe[FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY], "verdict": "rejected"}}, "dry_run_missing"),
    ]

    for agent_result, reason in cases:
        summary = build_flowweaver_shadow_runtime_publication(agent_result)
        rendered = repr(summary).lower()
        assert summary["verdict"] == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_REJECTED
        assert summary["reason"] == reason
        assert summary["start_request"] is None
        assert summary["ack_bridge"] == {"status": "rejected", "updates": []}
        assert summary["side_effects"] == []
        assert PRIVATE_MESSAGE_ID not in rendered
        assert "abc123" not in rendered
        assert "token=abc123" not in rendered


def test_attach_shadow_runtime_publication_only_mutates_when_enabled_and_ready() -> None:
    agent_result = make_shadow_agent_result()

    disabled = attach_flowweaver_shadow_runtime_publication(agent_result, enabled=False)
    assert disabled is None
    assert FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY not in agent_result

    enabled = attach_flowweaver_shadow_runtime_publication(agent_result, enabled=True)

    assert enabled is not None
    assert enabled["verdict"] == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY
    assert agent_result[FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY] == enabled


def test_delivery_ack_projection_emits_synthetic_final_text_and_rich_card_updates_only() -> None:
    delivery_state = {
        "final_text": {"sent": True, "reason": "stream_final_response", "message_id": PRIVATE_MESSAGE_ID},
        "rich_cards_sent": [
            {"type": "result_card", "message_id": "om_" + "card_1"},
            {"type": "result_card", "message_id": "om_" + "card_2"},
        ],
    }

    updates = build_flowweaver_delivery_ack_updates(delivery_state)
    rendered = repr(updates).lower()

    assert updates == [
        {
            "event_type": "record_delivery_ack",
            "delivery_key": "runtime_event_delivery_ack_final_text_0",
            "surface": "final_text",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_0",
            "status": "sent",
        },
        {
            "event_type": "record_delivery_ack",
            "delivery_key": "runtime_event_delivery_ack_rich_card_0",
            "surface": "rich_card",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_1",
            "status": "sent",
        },
        {
            "event_type": "record_delivery_ack",
            "delivery_key": "runtime_event_delivery_ack_rich_card_1",
            "surface": "rich_card",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_2",
            "status": "sent",
        },
    ]
    assert PRIVATE_MESSAGE_ID not in rendered
    assert "om_card" not in rendered


def test_delivery_ack_projection_omits_unsafe_state_without_leaking_raw_ids_or_secrets() -> None:
    agent_result = make_shadow_agent_result(
        rich_cards_sent=[
            {"type": "result_card", "message_id": PRIVATE_MESSAGE_ID, "card_json": {"chat_id": PRIVATE_CHAT_ID}},
        ],
    )
    agent_result["delivery_state"]["chat_id"] = PRIVATE_CHAT_ID
    agent_result["delivery_state"]["user_id"] = PRIVATE_USER_ID
    agent_result["delivery_state"]["adapter_error"] = "adapter failed with " + SECRET_SHAPED

    summary = build_flowweaver_shadow_runtime_publication(agent_result)
    rendered = repr(summary).lower()

    assert summary["verdict"] == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY
    assert summary["ack_bridge"]["status"] == "ready"
    assert summary["ack_bridge"]["updates"] == [
        {
            "event_type": "record_delivery_ack",
            "delivery_key": "runtime_event_delivery_ack_final_text_0",
            "surface": "final_text",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_0",
            "status": "sent",
        },
        {
            "event_type": "record_delivery_ack",
            "delivery_key": "runtime_event_delivery_ack_rich_card_0",
            "surface": "rich_card",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_1",
            "status": "sent",
        },
    ]
    assert PRIVATE_MESSAGE_ID not in rendered
    assert PRIVATE_CHAT_ID not in rendered
    assert PRIVATE_USER_ID not in rendered
    assert SECRET_SHAPED not in rendered
    assert "adapter failed" not in rendered
    assert "card_json" not in repr(summary["ack_bridge"]).lower()


def test_delivery_ack_projection_rejects_hostile_mapping_and_mutating_values() -> None:
    safe = {"final_text": {"sent": True}, "rich_cards_sent": []}
    hostile = FlickeringMapping(safe, {"final_text": {"sent": True, "message_id": PRIVATE_MESSAGE_ID}})

    assert build_flowweaver_delivery_ack_updates(hostile) == []

    mutating_value = MutatingValue()
    updates = build_flowweaver_delivery_ack_updates({"final_text": {"sent": mutating_value}, "rich_cards_sent": []})

    assert updates == []
    assert mutating_value.comparisons == 0

    mutations: list[str] = []

    class MutatingKey(str):
        def __eq__(self, other: object) -> bool:
            mutations.append("eq")
            return super().__eq__(other)

        def __hash__(self) -> int:
            return str.__hash__(self)

    keyed = dict(safe)
    keyed[MutatingKey("final_text")] = keyed.pop("final_text")
    assert build_flowweaver_delivery_ack_updates(keyed) == []
    assert mutations == []


def test_delivery_ack_projection_is_deterministic_and_does_not_mutate_input() -> None:
    delivery_state = {
        "final_text": {"sent": True},
        "rich_cards_sent": [{"type": "result_card", "message_id": "om_" + "card_1"}],
    }
    before = copy.deepcopy(delivery_state)

    first = build_flowweaver_delivery_ack_updates(delivery_state)
    second = build_flowweaver_delivery_ack_updates(delivery_state)

    assert first == second
    assert delivery_state == before
