"""Tests for PE-1 controlled Sachima production-shadow observation enablement."""

from __future__ import annotations

import copy

import pytest

from gateway.delivery_state import should_skip_final_text
from gateway.flowweaver_production_shadow_observation import (
    PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE,
    observe_gateway_turn_for_flowweaver_production_shadow,
    pe1_controlled_sachima_shadow_policy_from_config,
)
from gateway.run import GatewayRunner

PRIVATE_CHAT_ID = "oc_" + "pe1_private_chat"
PRIVATE_USER_ID = "ou_" + "pe1_private_user"
PRIVATE_MESSAGE_ID = "om_" + "pe1_private_message"
RAW_PROMPT_VALUE = "raw prompt pe1 value"
RAW_TOOL_OUTPUT_VALUE = "raw " + "tool output pe1 value"
CARD_JSON_VALUE = '{"type":"card_json","body":"pe1"}'
MEDIA_PATH_VALUE = "/tmp/pe1-private.png"
CALLBACK_VALUE = "callback payload pe1 value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw pe1 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-pe1"


class RecordingRuntimeControlSurface:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._payloads: dict[str, dict[str, object]] = {}

    async def handle(self, request: object) -> dict[str, object]:
        assert type(request) is dict
        safe_request = copy.deepcopy(request)
        self.calls.append(safe_request)
        operation = safe_request["operation"]
        workflow_id = str(safe_request["workflow_id"])
        if operation == "start_transaction":
            start_payload = safe_request["start_payload"]
            assert type(start_payload) is dict
            self._payloads[workflow_id] = start_payload
            return {
                "ok": True,
                "operation": "start_transaction",
                "runtime_operation": "start_transaction",
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "status": "started",
            }
        if operation == "query_transaction":
            start_payload = self._payloads[workflow_id]
            return {
                "ok": True,
                "operation": "query_transaction",
                "runtime_operation": "query_snapshot",
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "status": "running",
                "snapshot": {
                    "type": "flowweaver.temporal_poc.snapshot.v0",
                    "version": "flowweaver.temporal_poc.v0",
                    "transaction_id": workflow_id,
                    "status": "running",
                    "entry_count": start_payload["entry_count"],
                    "record_counts": copy.deepcopy(start_payload["record_counts"]),
                    "start_signature": {
                        "type": "flowweaver.temporal_poc.start_signature.v0",
                        "version": "flowweaver.temporal_poc.v0",
                        "idempotency_key": start_payload["idempotency_key"],
                        "event_contract_digest": "runtime_sig_" + "a" * 64,
                        "claim_policy_digest": "runtime_sig_" + "b" * 64,
                    },
                    "counts": {"intents": 1, "artifacts": 1, "deliveries": start_payload["record_counts"]["deliveries"]},
                    "intent_statuses": {"runtime_intent_0": "pending"},
                    "artifact_statuses": {"runtime_artifact_0": "planned"},
                    "delivery_statuses": {"runtime_delivery_0": "planned"},
                    "applied_event_count": 0,
                    "resume_count": 0,
                    "side_effects": [],
                },
            }
        raise AssertionError(f"unexpected runtime operation: {operation}")


class Source:
    def __init__(self, platform: str) -> None:
        self.platform = type("PlatformValue", (), {"value": platform})()


def config(enabled: bool, *, allowlist: list[str] | None = None, timeout_ms: int = 250) -> dict[str, object]:
    return {
        "flowweaver": {
            "production_shadow_observation": {
                "enabled": enabled,
                "platform_allowlist": list(allowlist or []),
                "timeout_ms": timeout_ms,
            }
        }
    }


def agent_result() -> dict[str, object]:
    return {
        "final_response": "pe1 visible reply",
        "api_calls": 2,
        "delivery_state": {
            "final_text": {"sent": False, "reason": None},
            "rich_cards_sent": [{"type": "weather.v1", "message_id": PRIVATE_MESSAGE_ID}],
            "media_sent": [],
        },
    }


def assert_no_forbidden_output(value: object) -> None:
    rendered = repr(value).lower()
    for marker in (
        PRIVATE_CHAT_ID,
        PRIVATE_USER_ID,
        PRIVATE_MESSAGE_ID,
        RAW_PROMPT_VALUE,
        RAW_TOOL_OUTPUT_VALUE,
        CARD_JSON_VALUE,
        MEDIA_PATH_VALUE,
        CALLBACK_VALUE,
        RAW_EXCEPTION_VALUE,
        SENSITIVE_SENTINEL,
        "production_enabled",
        "production_ready",
    ):
        assert marker.lower() not in rendered


def test_pe1_policy_defaults_off_and_requires_exact_sachima_allowlist() -> None:
    default_policy = pe1_controlled_sachima_shadow_policy_from_config({}, platform="sachima")
    assert default_policy["enabled"] is False
    assert default_policy["allow_platforms"] == []

    sachima_policy = pe1_controlled_sachima_shadow_policy_from_config(
        config(True, allowlist=["sachima"], timeout_ms=125),
        platform="sachima",
    )
    assert sachima_policy == {
        "type": "flowweaver.gateway.production_shadow_observation_policy.v0",
        "enabled": True,
        "mode": "production_shadow_observation",
        "allow_runtime_start": True,
        "allow_runtime_query": True,
        "allow_platforms": ["sachima"],
        "timeout_ms": 125,
        "side_effects": [],
    }

    extra_platform_policy = pe1_controlled_sachima_shadow_policy_from_config(
        config(True, allowlist=["sachima", "feishu"]),
        platform="sachima",
    )
    assert extra_platform_policy["enabled"] is True
    assert extra_platform_policy["allow_platforms"] == []

    duplicate_sachima_policy = pe1_controlled_sachima_shadow_policy_from_config(
        config(True, allowlist=["sachima", "sachima"]),
        platform="sachima",
    )
    assert duplicate_sachima_policy["enabled"] is True
    assert duplicate_sachima_policy["allow_platforms"] == []

    non_sachima_policy = pe1_controlled_sachima_shadow_policy_from_config(
        config(True, allowlist=["feishu"]),
        platform="feishu",
    )
    assert non_sachima_policy["enabled"] is True
    assert non_sachima_policy["allow_platforms"] == []


@pytest.mark.asyncio
async def test_pe1_observer_rejects_forged_non_sachima_policy_before_runtime_start() -> None:
    runtime = RecordingRuntimeControlSurface()
    forged_feishu_policy = {
        "type": "flowweaver.gateway.production_shadow_observation_policy.v0",
        "enabled": True,
        "mode": "production_shadow_observation",
        "allow_runtime_start": True,
        "allow_runtime_query": True,
        "allow_platforms": ["feishu"],
        "timeout_ms": 50,
        "side_effects": [],
    }

    result = await observe_gateway_turn_for_flowweaver_production_shadow(
        gateway_turn={
            "platform": "feishu",
            "session_key": f"feishu:{PRIVATE_CHAT_ID}:{PRIVATE_USER_ID}",
            "session_id": "sess_pe1_private_source",
            "message_id": PRIVATE_MESSAGE_ID,
            "turn_started_at_ns": 1_777_777_777_000_123,
            "turn_sequence": 5,
            "history_length": 5,
            "api_call_count": 2,
            "final_text_present": True,
            "rich_card_count": 1,
            "media_count": 0,
        },
        runtime_control_surface=runtime,
        shadow_policy=forged_feishu_policy,
    )

    assert result["type"] == PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE
    assert result["ok"] is False
    assert result["status"] == "skipped"
    assert result["error_code"] == "platform_not_allowlisted"
    assert runtime.calls == []
    assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_pe1_gateway_runner_observes_sachima_only_without_mutating_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = GatewayRunner.__new__(GatewayRunner)
    runtime = RecordingRuntimeControlSurface()
    runner._flowweaver_runtime_control_surface = runtime
    runner._flowweaver_production_shadow_observation_counters = {}
    monkeypatch.setattr(
        "gateway.run._load_gateway_config",
        lambda: config(True, allowlist=["sachima"], timeout_ms=50),
    )
    result_payload = agent_result()
    before_delivery_state = copy.deepcopy(result_payload["delivery_state"])
    before_skip = should_skip_final_text(result_payload)

    result = await runner._maybe_observe_flowweaver_production_shadow(
        source=Source("sachima"),
        session_key=f"sachima:{PRIVATE_CHAT_ID}:{PRIVATE_USER_ID}",
        session_id="sess_pe1_private_source",
        history_length=5,
        agent_result=result_payload,
        response="pe1 visible reply",
        turn_started_at_ns=1_777_777_777_000_123,
    )

    assert result["type"] == PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE
    assert result["ok"] is True
    assert [call["operation"] for call in runtime.calls] == ["start_transaction", "query_transaction"]
    assert "reconcile_delivery_ack" not in [call["operation"] for call in runtime.calls]
    assert result["delivery"] == {"ack_updates": 0, "control": "unchanged"}
    assert result_payload["delivery_state"] == before_delivery_state
    assert should_skip_final_text(result_payload) is before_skip
    assert result_payload.get("already_sent") is None
    assert_no_forbidden_output(result)
    assert_no_forbidden_output(runtime.calls)


@pytest.mark.asyncio
async def test_pe1_gateway_runner_rejects_non_sachima_even_if_operator_allowlists_it(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = GatewayRunner.__new__(GatewayRunner)
    runtime = RecordingRuntimeControlSurface()
    runner._flowweaver_runtime_control_surface = runtime
    runner._flowweaver_production_shadow_observation_counters = {}
    monkeypatch.setattr(
        "gateway.run._load_gateway_config",
        lambda: config(True, allowlist=["feishu"], timeout_ms=50),
    )
    result_payload = agent_result()
    before_delivery_state = copy.deepcopy(result_payload["delivery_state"])
    before_skip = should_skip_final_text(result_payload)

    result = await runner._maybe_observe_flowweaver_production_shadow(
        source=Source("feishu"),
        session_key=f"feishu:{PRIVATE_CHAT_ID}:{PRIVATE_USER_ID}",
        session_id="sess_pe1_private_source",
        history_length=5,
        agent_result=result_payload,
        response="pe1 visible reply",
        turn_started_at_ns=1_777_777_777_000_123,
    )

    assert result["type"] == PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE
    assert result["ok"] is False
    assert result["status"] == "skipped"
    assert result["error_code"] == "platform_not_allowlisted"
    assert runtime.calls == []
    assert result_payload["delivery_state"] == before_delivery_state
    assert should_skip_final_text(result_payload) is before_skip
    assert result_payload.get("already_sent") is None
    assert_no_forbidden_output(result)
