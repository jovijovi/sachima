from __future__ import annotations

from typing import Any

import pytest

from gateway.flowweaver_pe2_controlled_runtime_delivery_bridge import (
    FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_SUCCESS_VERDICT,
    FlowWeaverPE2AControlledRuntimeDeliveryBridge,
    build_flowweaver_pe2a_evidence,
    describe_flowweaver_pe2a_contract,
    pe2a_controlled_runtime_delivery_policy,
    run_flowweaver_pe2a_controlled_runtime_delivery,
)
from gateway.sachima_fake_send_simulator import FakeSachimaSendSimulator


class RecordingRuntimeControlSurface:
    def __init__(
        self,
        *,
        fail_operation: str | None = None,
        unsafe_output: bool = False,
        omit_ack_fields: bool = False,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_operation = fail_operation
        self.unsafe_output = unsafe_output
        self.omit_ack_fields = omit_ack_fields
        self.ack_refs: list[str] = []

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(request))
        operation = request["operation"]
        if operation == self.fail_operation:
            raise RuntimeError("runtime private failure should not leak")
        if self.unsafe_output:
            return {"ok": True, "operation": operation, "raw_" + "prompt": "private"}
        workflow_id = str(request.get("workflow_id"))
        if operation == "start_transaction":
            return {
                "ok": True,
                "operation": operation,
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "status": "started",
                "side_effects": [],
            }
        if operation == "record_operation":
            return {
                "ok": True,
                "operation": operation,
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "status": "recorded",
                "side_effects": [],
            }
        if operation == "plan_delivery":
            return {
                "ok": True,
                "operation": operation,
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "status": "planned",
                "delivery_refs": list(request["delivery_refs"]),
                "surfaces": list(request["surfaces"]),
                "side_effects": [],
            }
        if operation == "record_delivery_ack":
            self.ack_refs.append(str(request["ack_ref"]))
            if self.omit_ack_fields:
                return {
                    "ok": True,
                    "operation": operation,
                    "workflow_id": workflow_id,
                    "transaction_id": workflow_id,
                    "status": "sent",
                    "side_effects": [],
                }
            return {
                "ok": True,
                "operation": operation,
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "delivery_ref": request["delivery_ref"],
                "ack_ref": request["ack_ref"],
                "surface": request["surface"],
                "status": "sent",
                "side_effects": [],
            }
        if operation == "query_transaction":
            return {
                "ok": True,
                "operation": operation,
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "status": "running",
                "counts": {
                    "acks": len(self.ack_refs),
                    "operations": len(self.calls),
                },
                "side_effects": [],
            }
        raise AssertionError(f"unexpected operation {operation}")


def _envelope(*, delivery_refs: list[str] | None = None, final_text: bool = True) -> dict[str, Any]:
    return {
        "type": "flowweaver.pe2.sachima_ingress_envelope.v0",
        "platform": "sachima",
        "source": "loopback_or_synthetic_pe2a",
        "session_label": "safe_session_pe2a_123",
        "turn_label": "safe_turn_pe2a_123",
        "turn_discriminator": "safe_discriminator_pe2a_123",
        "auth": {"hmac_verified": True, "policy_label": "allowlisted_test_operator"},
        "visible_surfaces": {"final_text": final_text, "rich_card_count": 1, "media_count": 0},
        "claim_refs": {
            "input_ref": "runtime_input_0",
            "delivery_refs": delivery_refs or ["runtime_delivery_0", "runtime_delivery_1"],
            "artifact_refs": ["runtime_artifact_0"],
        },
        "side_effects": [],
    }


def test_pe2a_contract_descriptor_keeps_boundaries_explicit() -> None:
    contract = describe_flowweaver_pe2a_contract()

    assert contract["type"] == "flowweaver.pe2a.controlled_runtime_delivery_contract.v0"
    assert contract["allowed_runtime_operations"] == [
        "start_transaction",
        "record_operation",
        "plan_delivery",
        "record_delivery_ack",
        "query_transaction",
        "cancel_transaction",
    ]
    assert contract["delivery_boundary"] == "fake_send_only"
    assert contract["gateway_lifecycle_ownership"] == "forbidden"
    assert contract["next_allowed_decision"] == "pe2a_evidence_ready_for_external_ingress_design_request_only"
    for approval in [
        "real_external_sachima_ingress",
        "real_external_delivery",
        "production_config_write",
        "gateway_restart_or_reload",
        "gateway_owned_temporal_lifecycle",
        "production_agent_tool_execution_expansion",
    ]:
        assert approval in contract["separate_approval_required"]


@pytest.mark.asyncio
async def test_disabled_policy_makes_zero_runtime_or_fake_send_calls() -> None:
    runtime = RecordingRuntimeControlSurface()
    fake_send = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0", "runtime_delivery_1"})

    result = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(enabled=False),
    )

    assert result["ok"] is False
    assert result["error_code"] == "disabled"
    assert runtime.calls == []
    assert fake_send.transcript() == []


@pytest.mark.asyncio
async def test_missing_fake_send_surface_fails_before_runtime_calls() -> None:
    runtime = RecordingRuntimeControlSurface()

    result = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(),
        runtime_control_surface=runtime,
        fake_send_surface=None,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "fake_send_surface_required"
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_rejects_raw_or_private_material_before_runtime_calls() -> None:
    runtime = RecordingRuntimeControlSurface()
    fake_send = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0", "runtime_delivery_1"})
    unsafe = _envelope() | {"platform_payload": {"chat_id": "oc" + "_private"}}

    result = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=unsafe,
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "invalid_ingress_envelope"
    assert runtime.calls == []
    assert fake_send.transcript() == []


@pytest.mark.asyncio
async def test_positive_pe2a_flow_orders_runtime_fake_send_and_ack_updates() -> None:
    runtime = RecordingRuntimeControlSurface()
    fake_send = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0", "runtime_delivery_1"})

    result = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )

    assert result["ok"] is True
    assert result["verdict"] == FLOWWEAVER_PE2A_CONTROLLED_RUNTIME_DELIVERY_SUCCESS_VERDICT
    assert [call["operation"] for call in runtime.calls] == [
        "start_transaction",
        "record_operation",
        "plan_delivery",
        "record_delivery_ack",
        "record_delivery_ack",
        "query_transaction",
    ]
    assert [row["surface"] for row in fake_send.transcript()] == ["rich_card", "final_text"]
    assert result["delivery_surface_state"]["rich_cards_sent"] == 1
    assert result["delivery_surface_state"]["final_text_sent"] is True
    assert result["counts"]["runtime_ack_updates"] == 2
    assert result["counts"]["fake_send_requests"] == 2
    assert result["runtime_call_counts"]["record_delivery_ack"] == 2
    assert result["delivery_ack_refs"] == runtime.ack_refs


@pytest.mark.asyncio
async def test_duplicate_ingress_short_circuits_without_second_runtime_or_fake_send_chain() -> None:
    runtime = RecordingRuntimeControlSurface()
    fake_send = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0", "runtime_delivery_1"})
    bridge = FlowWeaverPE2AControlledRuntimeDeliveryBridge()

    first = await bridge.run(
        ingress_envelope=_envelope(),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )
    second = await bridge.run(
        ingress_envelope=_envelope(),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["duplicate"] is True
    assert [call["operation"] for call in runtime.calls].count("start_transaction") == 1
    assert len(fake_send.transcript()) == 2


@pytest.mark.asyncio
async def test_rejected_fake_send_does_not_record_runtime_ack() -> None:
    runtime = RecordingRuntimeControlSurface()
    fake_send = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0"})

    result = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(delivery_refs=["runtime_delivery_9", "runtime_delivery_1"]),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "fake_send_rejected"
    assert "record_delivery_ack" not in [call["operation"] for call in runtime.calls]
    assert fake_send.transcript() == []


@pytest.mark.asyncio
async def test_runtime_exception_returns_stable_error_without_raw_exception_text() -> None:
    runtime = RecordingRuntimeControlSurface(fail_operation="plan_delivery")
    fake_send = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0", "runtime_delivery_1"})

    result = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )

    rendered = repr(result).lower()
    assert result["ok"] is False
    assert result["error_code"] == "runtime_operation_failed"
    assert "runtime private failure" not in rendered
    assert fake_send.transcript() == []


@pytest.mark.asyncio
async def test_unsafe_runtime_output_is_rejected_without_fake_send() -> None:
    runtime = RecordingRuntimeControlSurface(unsafe_output=True)
    fake_send = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0", "runtime_delivery_1"})

    result = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "unsafe_runtime_output"
    assert fake_send.transcript() == []


def test_evidence_builder_counts_are_derived_from_sanitized_result() -> None:
    result = {
        "type": "flowweaver.pe2a.controlled_runtime_delivery_result.v0",
        "version": "flowweaver.pe2a.controlled_runtime_delivery_bridge.v0",
        "ok": True,
        "runtime_operations": [
            "start_transaction",
            "record_operation",
            "plan_delivery",
            "record_delivery_ack",
            "query_transaction",
        ],
        "delivery_ack_refs": ["runtime_event_delivery_ack_0001"],
        "delivery_events": [
            {
                "delivery_ref": "runtime_delivery_0",
                "surface": "final_text",
                "status": "sent",
                "ack_ref": "runtime_event_delivery_ack_0001",
                "duplicate": False,
            }
        ],
        "duplicate_ingress_refs": [],
        "rejected_probe_codes": [],
        "counts": {
            "accepted_ingress_envelopes": 1,
            "runtime_start_requests": 1,
            "runtime_delivery_plan_requests": 1,
            "fake_send_requests": 1,
            "runtime_ack_updates": 1,
            "duplicates": 0,
            "rejected_probes": 0,
        },
        "delivery_surface_state": {"final_text_sent": True},
        "negative_probes": {"disabled_policy": "zero_calls"},
        "rollback_restore": {"restore_positive": "one_additional_chain"},
        "side_effects": [],
    }

    evidence = build_flowweaver_pe2a_evidence(result, base_sha="84f6a9010d72")

    assert evidence["type"] == "flowweaver.pe2a.controlled_runtime_fake_delivery_evidence.v0"
    assert evidence["scope"] == {
        "loopback_or_synthetic_only": True,
        "real_external_ingress": False,
        "real_external_delivery": False,
        "gateway_restart_or_config_write": False,
        "gateway_owned_temporal_lifecycle": False,
        "production_agent_tool_execution_expansion": False,
    }
    assert evidence["counts"]["runtime_ack_updates"] == evidence["counts"]["fake_send_requests"]
    assert evidence["no_leak_scan"] == {"passed": True, "raw_marker_hits": 0, "markers": []}
    assert evidence["decision"] == "pe2a_evidence_ready_for_external_ingress_design_request_only"


@pytest.mark.asyncio
async def test_later_fake_send_rejection_does_not_record_partial_runtime_ack() -> None:
    runtime = RecordingRuntimeControlSurface()
    fake_send = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0"})

    result = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(delivery_refs=["runtime_delivery_0", "runtime_delivery_1"]),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "fake_send_rejected"
    assert "record_delivery_ack" not in [call["operation"] for call in runtime.calls]
    assert runtime.ack_refs == []


@pytest.mark.asyncio
async def test_runtime_ack_response_must_echo_ack_target_fields() -> None:
    runtime = RecordingRuntimeControlSurface(omit_ack_fields=True)
    fake_send = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0", "runtime_delivery_1"})

    result = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "unsafe_runtime_output"


def test_evidence_builder_rejects_forged_ack_counts() -> None:
    forged = {
        "type": "flowweaver.pe2a.controlled_runtime_delivery_result.v0",
        "version": "flowweaver.pe2a.controlled_runtime_delivery_bridge.v0",
        "ok": True,
        "runtime_operations": ["start_transaction", "record_operation", "plan_delivery", "query_transaction"],
        "delivery_ack_refs": [],
        "counts": {
            "accepted_ingress_envelopes": 1,
            "runtime_start_requests": 1,
            "runtime_delivery_plan_requests": 1,
            "fake_send_requests": 1,
            "runtime_ack_updates": 1,
            "duplicates": 0,
            "rejected_probes": 0,
        },
        "delivery_surface_state": {"final_text_sent": True},
        "negative_probes": {},
        "rollback_restore": {},
        "side_effects": [],
    }

    with pytest.raises(ValueError):
        build_flowweaver_pe2a_evidence(forged, base_sha="84f6a9010d72")


def test_evidence_builder_rejects_forged_fake_send_overclaim() -> None:
    forged = {
        "type": "flowweaver.pe2a.controlled_runtime_delivery_result.v0",
        "version": "flowweaver.pe2a.controlled_runtime_delivery_bridge.v0",
        "ok": True,
        "runtime_operations": [
            "start_transaction",
            "record_operation",
            "plan_delivery",
            "record_delivery_ack",
            "query_transaction",
        ],
        "delivery_ack_refs": ["runtime_event_delivery_ack_0001"],
        "delivery_events": [
            {
                "delivery_ref": "runtime_delivery_0",
                "surface": "final_text",
                "status": "sent",
                "ack_ref": "runtime_event_delivery_ack_0001",
                "duplicate": False,
            }
        ],
        "duplicate_ingress_refs": [],
        "rejected_probe_codes": [],
        "counts": {
            "accepted_ingress_envelopes": 1,
            "runtime_start_requests": 1,
            "runtime_delivery_plan_requests": 1,
            "fake_send_requests": 999,
            "runtime_ack_updates": 1,
            "duplicates": 0,
            "rejected_probes": 0,
        },
        "delivery_surface_state": {"final_text_sent": True},
        "negative_probes": {},
        "rollback_restore": {},
        "side_effects": [],
    }

    with pytest.raises(ValueError):
        build_flowweaver_pe2a_evidence(forged, base_sha="84f6a9010d72")


@pytest.mark.asyncio
async def test_stateless_helper_handles_duplicate_fake_send_without_raw_exception() -> None:
    runtime = RecordingRuntimeControlSurface()
    fake_send = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0", "runtime_delivery_1"})

    first = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )
    second = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["counts"]["runtime_ack_updates"] == 0
    assert second["counts"]["fake_send_requests"] == 2
    assert second["counts"]["duplicates"] == 2
    assert all(event["duplicate"] is True for event in second["delivery_events"])
    assert len(fake_send.transcript()) == 2
