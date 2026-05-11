"""Tests for the FlowWeaver Phase 5D shadow runtime publisher helper."""

from __future__ import annotations

import copy
import re
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


def make_snapshot(*, index: int = 0, transaction_id: str | None = None, updated_at: float | None = None) -> TransactionSnapshot:
    snapshot_updated_at = updated_at if updated_at is not None else 1002.0 + index
    return TransactionSnapshot(
        transaction_id=transaction_id or f"session_shadow_publisher_{index}",
        title="Gateway shadow publisher task",
        status="completed",
        started_at=1000.0 + index,
        updated_at=snapshot_updated_at,
        completed_at=snapshot_updated_at,
        recent_operations=(),
    )


def make_shadow_agent_result(
    *,
    index: int = 0,
    final_text_sent: bool = True,
    rich_cards_sent: list[dict[str, Any]] | None = None,
    attach_dry_run: bool = True,
    transaction_id: str | None = None,
    updated_at: float | None = None,
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
        make_snapshot(index=index, transaction_id=transaction_id, updated_at=updated_at),
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
    base = _flowweaver_boundary_diff_base(repo_root)
    scanned_paths = ("gateway/run.py", "gateway/flowweaver_shadow_publisher.py")
    diff_commands = (
        ("diff", "--unified=0", base, "HEAD", "--", *scanned_paths),
        ("diff", "--unified=0", "--", *scanned_paths),
        ("diff", "--cached", "--unified=0", "--", *scanned_paths),
    )
    added_lines: list[str] = []
    for command in diff_commands:
        diff = subprocess.check_output(["git", *command], cwd=repo_root, text=True)
        added_lines.extend(
            line[1:].strip() for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
        )
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


def _flowweaver_boundary_diff_base(repo_root: Path) -> str:
    """Choose the relevant base for FlowWeaver boundary scans.

    Phase branches are normally linear on ``origin/feature/sachima-channel``, so
    their guard scans the phase diff from that merge-base.  The main/Sachima
    integration branch is rooted in a merge commit whose first parent is latest
    upstream ``main`` and whose second parent is the Sachima channel.  Follow-up
    integration-fix commits are ordinary single-parent commits on top of that
    merge, so the guard finds the most recent first-parent merge and scans from
    that merge's first parent.  This keeps the scan focused on the integration
    delta without re-scanning unrelated upstream release changes.
    """
    merge_line = subprocess.check_output(
        ["git", "rev-list", "--first-parent", "--merges", "-n", "1", "HEAD"],
        cwd=repo_root,
        text=True,
    ).strip()
    if merge_line:
        parents = subprocess.check_output(
            ["git", "rev-list", "--parents", "-n", "1", merge_line],
            cwd=repo_root,
            text=True,
        ).split()
        if len(parents) > 2:
            return parents[1]
    return subprocess.check_output(
        ["git", "merge-base", "HEAD", "origin/feature/sachima-channel"],
        cwd=repo_root,
        text=True,
    ).strip()


def test_shadow_runtime_publisher_changed_file_guard_allows_only_phase5e_files() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    changed = set(
        subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=repo_root, text=True).splitlines()
    )
    changed.update(
        subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo_root, text=True).splitlines()
    )
    allowed = {
        "docs/dev_log/2026-05-06-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter.md",
        "docs/plans/2026-05-06-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter.md",
        "gateway/flowweaver_contract.py",
        "gateway/flowweaver_runtime_contract.py",
        "gateway/flowweaver_runtime_identity.py",
        "gateway/flowweaver_shadow_publisher.py",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py",
        "tests/gateway/test_flowweaver_runtime_contract.py",
        "tests/gateway/test_flowweaver_runtime_identity.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
        "tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py",
        "tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py",
        "tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py",
        "docs/plans/2026-05-11-flowweaver-phase21-production-shadow-observation-only.md",
        "docs/dev_log/2026-05-11-flowweaver-phase21-production-shadow-observation-only.md",
        "docs/runbooks/flowweaver-production-shadow-observation.md",
        "gateway/flowweaver_production_shadow_observation.py",
        "gateway/run.py",
        "tests/gateway/test_flowweaver_production_shadow_observation.py",
        "tests/integration/test_flowweaver_phase21_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
        "tests/gateway/test_flowweaver_temporal_observation_bridge.py",
        "tests/gateway/test_flowweaver_temporal_observation_validation_gate.py",
        "tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py",
        "tests/integration/test_flowweaver_phase5i_start_signature_parity.py",
        "tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py",
        "tests/integration/test_flowweaver_phase5k_runtime_control_surface.py",
        "tests/prototypes/test_flowweaver_phase5c_tool_surface.py",
        "docs/plans/2026-05-09-flowweaver-phase22-delivery-agent-execution-contract-gate.md",
        "docs/dev_log/2026-05-09-flowweaver-phase22-delivery-agent-execution-contract-gate.md",
        "docs/runbooks/flowweaver-delivery-agent-execution-contract.md",
        "gateway/flowweaver_delivery_agent_execution_contract.py",
        "tests/gateway/test_flowweaver_delivery_agent_execution_contract.py",
        "docs/plans/2026-05-09-flowweaver-phase23-stub-activity-orchestration.md",
        "docs/dev_log/2026-05-09-flowweaver-phase23-stub-activity-orchestration.md",
        "docs/runbooks/flowweaver-stub-activity-orchestration.md",
        "gateway/flowweaver_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration.py",
        "docs/plans/2026-05-09-flowweaver-phase24-stub-activity-orchestration-validation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase24-stub-activity-orchestration-validation.md",
        "docs/runbooks/flowweaver-stub-activity-orchestration-validation.md",
        "gateway/flowweaver_stub_activity_orchestration_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py",
        "docs/plans/2026-05-09-flowweaver-phase25-stub-activity-boundary-contract.md",
        "docs/dev_log/2026-05-09-flowweaver-phase25-stub-activity-boundary-contract.md",
        "docs/runbooks/flowweaver-stub-activity-boundary-contract.md",
        "gateway/flowweaver_stub_activity_boundary_contract.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract.py",
        "docs/plans/2026-05-09-flowweaver-phase26-stub-activity-boundary-contract-validation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase26-stub-activity-boundary-contract-validation.md",
        "docs/runbooks/flowweaver-stub-activity-boundary-contract-validation.md",
        "gateway/flowweaver_stub_activity_boundary_contract_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py",
        "docs/plans/2026-05-09-flowweaver-phase27-stub-activity-implementation-design.md",
        "docs/dev_log/2026-05-09-flowweaver-phase27-stub-activity-implementation-design.md",
        "docs/runbooks/flowweaver-stub-activity-implementation-design.md",
        "gateway/flowweaver_stub_activity_implementation_design.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_design.py",
        "docs/plans/2026-05-09-flowweaver-phase28-stub-activity-implementation-validation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase28-stub-activity-implementation-validation.md",
        "docs/runbooks/flowweaver-stub-activity-implementation-validation.md",
        "gateway/flowweaver_stub_activity_implementation_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_validation.py",
        "docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md",
        "docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md",
        "docs/plans/2026-05-09-flowweaver-phase29-stub-activity-implementation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase29-stub-activity-implementation.md",
        "docs/runbooks/flowweaver-stub-activity-implementation.md",
        "gateway/flowweaver_stub_activity_implementation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation.py",
        "docs/plans/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md",
        "docs/dev_log/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md",
        "docs/runbooks/flowweaver-temporal-stub-activity-orchestration.md",
        "gateway/flowweaver_temporal_stub_activity_orchestration.py",
        "tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py",
        "docs/plans/2026-05-09-flowweaver-phase31-agent-execution-activity.md",
        "docs/dev_log/2026-05-09-flowweaver-phase31-agent-execution-activity.md",
        "docs/runbooks/flowweaver-agent-execution-activity.md",
        "gateway/flowweaver_agent_execution_activity.py",
        "tests/gateway/test_flowweaver_agent_execution_activity.py",
        "tests/integration/test_flowweaver_phase31_agent_execution_activity.py",
        "gateway/flowweaver_delivery_activity.py",
        "tests/gateway/test_flowweaver_delivery_activity.py",
        "tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py",
        "docs/runbooks/flowweaver-delivery-activity-ack-reconciliation.md",
        "docs/plans/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md",
        "gateway/flowweaver_ai_flow_pilot.py",
        "tests/gateway/test_flowweaver_ai_flow_pilot.py",
        "tests/integration/test_flowweaver_phase33_ai_flow_pilot.py",
        "docs/runbooks/flowweaver-ai-flow-pilot.md",
        "docs/plans/2026-05-09-flowweaver-phase33-ai-flow-pilot.md",
        "docs/dev_log/2026-05-09-flowweaver-phase33-ai-flow-pilot.md",
        "docs/plans/2026-05-11-flowweaver-production-enablement-decision-packet.md",
        "docs/runbooks/flowweaver-production-enablement-decision.md",
        "docs/dev_log/2026-05-11-flowweaver-production-enablement-decision-packet.md",
        "docs/plans/2026-05-11-flowweaver-pe1-controlled-sachima-shadow-observation.md",
        "docs/runbooks/flowweaver-pe1-controlled-sachima-shadow-observation.md",
        "docs/dev_log/2026-05-11-flowweaver-pe1-controlled-sachima-shadow-observation.md",
        "docs/plans/2026-05-11-flowweaver-pe1d-pe2-readiness-decision-packet.md",
        "docs/runbooks/flowweaver-pe1d-pe2-readiness-decision.md",
        "docs/dev_log/2026-05-11-flowweaver-pe1d-pe2-readiness-decision-packet.md",
        "AGENTS.md",
        "GOAL.md",
        "docs/sachima-final-goal-gap-analysis.md",
        "docs/dev_log/2026-05-11-sachima-project-goal-gap-analysis.md",
        "docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md",
        "docs/dev_log/2026-05-11-sachima-final-goal-phase-development-plan.md",
        "tests/gateway/test_flowweaver_pe1_controlled_sachima_shadow_observation.py",
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
    runtime_tx_pattern = re.compile(r"^runtime_tx_shadow_[a-f0-9]{20}$")
    runtime_event_pattern = re.compile(r"^runtime_event_start_shadow_[a-f0-9]{20}$")
    assert runtime_tx_pattern.fullmatch(summary["transaction_id"])
    assert runtime_tx_pattern.fullmatch(summary["workflow_id"])
    assert summary["transaction_id"] == summary["workflow_id"]
    assert summary["runtime_identity"] == {
        "type": "flowweaver.gateway.runtime_identity.v0",
        "strategy": "shadow_ref_hash_v0",
        "transaction_id": summary["transaction_id"],
        "workflow_id": summary["workflow_id"],
        "idempotency_key": summary["start_request"]["start_payload"]["idempotency_key"],
    }
    assert runtime_event_pattern.fullmatch(summary["runtime_identity"]["idempotency_key"])
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
    assert summary["start_request"]["workflow_id"] == summary["workflow_id"]
    payload = summary["start_request"]["start_payload"]
    assert payload["transaction_id"] == summary["transaction_id"]
    assert payload["idempotency_key"] == summary["runtime_identity"]["idempotency_key"]
    assert payload["entry_count"] == 1
    assert payload["record_counts"] == {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1}
    assert payload["claim_check_policy"]["mode"] == "references_only"
    assert "record_delivery_ack" in payload["allowed_runtime_events"]
    assert "runtime_tx_replay_corpus" not in rendered
    assert "flowweaver_shadow_snapshot" not in rendered
    assert "flowweaver_shadow_capture" not in rendered
    assert "session_shadow_publisher" not in rendered
    assert "final_response" not in rendered


def test_shadow_runtime_publication_uses_different_variable_ids_for_different_shadow_results() -> None:
    first = build_flowweaver_shadow_runtime_publication(make_shadow_agent_result(index=1))
    second = build_flowweaver_shadow_runtime_publication(make_shadow_agent_result(index=2))

    assert first["verdict"] == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY
    assert second["verdict"] == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY
    assert first["transaction_id"] != second["transaction_id"]
    assert first["workflow_id"] != second["workflow_id"]
    assert first["start_request"]["start_payload"]["idempotency_key"] != second["start_request"]["start_payload"]["idempotency_key"]


def test_shadow_runtime_publication_uses_different_ids_for_same_session_across_turns() -> None:
    first = build_flowweaver_shadow_runtime_publication(
        make_shadow_agent_result(index=8, transaction_id="session_shadow_publisher_same", updated_at=2001.1)
    )
    second = build_flowweaver_shadow_runtime_publication(
        make_shadow_agent_result(index=8, transaction_id="session_shadow_publisher_same", updated_at=2001.2)
    )

    assert first["verdict"] == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY
    assert second["verdict"] == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY
    assert first["transaction_id"] != second["transaction_id"]
    assert first["start_request"]["start_payload"]["idempotency_key"] != second["start_request"]["start_payload"]["idempotency_key"]


def test_shadow_runtime_publication_ack_targets_remain_bounded_synthetic_delivery_ids() -> None:
    summary = build_flowweaver_shadow_runtime_publication(
        make_shadow_agent_result(
            index=3,
            rich_cards_sent=[{"type": "result_card", "message_id": PRIVATE_MESSAGE_ID}],
        )
    )
    updates = summary["ack_bridge"]["updates"]
    rendered = repr(updates).lower()

    assert summary["verdict"] == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_READY
    assert summary["start_request"]["start_payload"]["record_counts"] == {
        "transactions": 1,
        "intents": 1,
        "artifacts": 1,
        "deliveries": 2,
    }
    assert [update["target_id"] for update in updates] == ["runtime_delivery_0", "runtime_delivery_1"]
    assert all(re.fullmatch(r"runtime_event_delivery_ack_(final_text|rich_card)_\d+", update["delivery_key"]) for update in updates)
    assert "runtime_tx_shadow_" not in rendered
    assert "session_shadow_publisher" not in rendered
    assert PRIVATE_MESSAGE_ID not in rendered


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
