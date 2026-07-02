"""S5 downstream delivery reconnect implementation contract (RED first).

These tests pin the separately approved S5 implementation gate: consume the
already-sanitized S4 ``ActivityOutput`` and reconnect it to the default-off P7
``SachimaP7DeliveryAckController`` through an injected/fake send seam only.

The contract deliberately requires an S5-owned durable pre-claim **before**
``deliver_slot(...)`` so duplicate/recover/retry never double-send. The tests are
pure offline unit tests: no real send, no Gateway/Feishu/live/default-on/public
 ingress, no production config, no Worker/service/runtime/subprocess startup, and
no write-capable roles.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from temporalio.exceptions import ApplicationError

from gateway.sachima_delivery_ack import SACHIMA_P7_ACK_EVENT_TYPE, SACHIMA_P7_DELIVERY_RESULT_TYPE
from sachima_supervisor.p5_temporal import contracts as C

# Future module under contract — RED: importing it is expected to fail until the
# S5 reconnect source lands.
from sachima_supervisor.p5_temporal.s5_downstream_delivery_reconnect import (
    S5_DOWNSTREAM_DELIVERY_RECONNECT_APPROVAL_TOKEN,
    S5DeliveryReconnectController,
    S5DurableDeliveryClaimStore,
    build_s5_delivery_reconnect_request,
    describe_sachima_s5_downstream_delivery_reconnect_contract,
    s5_delivery_failure_for_code,
    scan_sachima_s5_no_leak,
)

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64


def _activity_output(*, artifact_kind: str = "architecture_packet") -> C.ActivityOutput:
    output = C.ActivityOutput(
        schema_version=C.SCHEMA_VERSION,
        status="completed",
        artifact_ref=C.StepArtifactRef(
            artifact_id="p5_artifact_s5_demo_0001",
            producer_step_id="architect",
            content_digest=_DIGEST_A,
            artifact_kind=artifact_kind,
            byte_count=128,
            created_at_ref="created_at_ref_s5_demo_0001",
        ),
        evidence_ref="p5_evidence_s5_demo_0001",
        evidence_digest=_DIGEST_B,
    )
    C.validate_activity_output(output)
    return output


def _request(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        activity_output=_activity_output(),
        intent_class="architecture_packet",
        target_ref="safe_recipient_group_a",
        surfaces=("final_text",),
        delivery_role_key="sachima_delivery_read_only_reporter",
        idempotency_key="p7key_s5_final_text_0",
    )
    base.update(overrides)
    return build_s5_delivery_reconnect_request(**base)


class FakeSendAdapter:
    """Injected fake send seam; records calls and optionally checks pre-claim."""

    def __init__(self, *, outcome: str = "accepted", receipt_ref: str | None = "runtime_delivery_ack_0", store=None) -> None:
        self.outcome = outcome
        self.receipt_ref = receipt_ref
        self.store = store
        self.calls: list[dict[str, Any]] = []

    def __call__(self, send_request: dict[str, Any]) -> dict[str, Any]:
        if self.store is not None:
            resident = self.store.query()["claims"][send_request["idempotency_key"]]
            assert resident["state"] == "claimed"
            assert resident["terminal"] is False
        self.calls.append(dict(send_request))
        return {
            "outcome": self.outcome,
            "delivery_ref": send_request["delivery_ref"],
            "surface": send_request["surface"],
            "receipt_ref": self.receipt_ref if self.outcome == "accepted" else None,
        }


def _controller(*, store=None, enabled: bool = True, approval_token: str = S5_DOWNSTREAM_DELIVERY_RECONNECT_APPROVAL_TOKEN):
    return S5DeliveryReconnectController(
        enabled=enabled,
        approval_token=approval_token,
        claim_store=store or S5DurableDeliveryClaimStore(),
        approved_targets=("safe_recipient_group_a", "safe_recipient_group_b"),
        allowed_surfaces=("final_text", "rich_card"),
        delivery_url_class="safe_delivery_url_class_a",
        max_attempts=2,
    )


def test_contract_descriptor_keeps_gateway_and_real_send_out_of_scope() -> None:
    contract = describe_sachima_s5_downstream_delivery_reconnect_contract()

    assert contract["default_off"] is True
    assert contract["send_seam"] == "injected_fake_only"
    assert contract["gateway_temporal_caller"] is False
    assert contract["gateway_lifecycle_owner"] is False
    assert contract["gateway_worker_owner"] is False
    assert contract["real_send_approved"] is False
    assert contract["preclaim_before_deliver_slot"] is True
    for marker in [
        "gateway_restart",
        "platform_adapter_construction",
        "public_ingress",
        "production_config_write",
        "write_capable_roles",
        "worker_lifecycle",
    ]:
        assert marker in contract["forbidden_side_effects"]
    assert contract["side_effects"] == []


def test_default_off_token_mismatch_and_missing_adapter_make_zero_send_calls() -> None:
    request = _request()
    for controller, expected in [
        (_controller(enabled=False), "p7_delivery_disabled"),
        (_controller(approval_token="wrong_s5_token"), "p7_delivery_disabled"),
    ]:
        adapter = FakeSendAdapter()
        result = controller.deliver(request=request, adapter=adapter)
        assert result["status"] == "disabled"
        assert result["error_code"] == expected
        assert adapter.calls == []

    controller = _controller()
    result = controller.deliver(request=request, adapter=None)
    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_invalid_request"


def test_reconnect_projects_s4_output_to_p7_request_and_records_ack_from_receipt_only() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    adapter = FakeSendAdapter(store=store)

    result = controller.deliver(request=_request(), adapter=adapter)

    assert result["type"] == SACHIMA_P7_DELIVERY_RESULT_TYPE
    assert result["status"] == "delivered"
    assert result["error_code"] is None
    assert result["ack"] is not None
    assert result["ack"]["source"] == "send_response"
    assert len(adapter.calls) == 1
    sent = adapter.calls[0]
    assert sent["delivery_ref"] == "runtime_delivery_0"
    assert sent["surface"] == "final_text"
    assert sent["target_ref"] == "safe_recipient_group_a"
    assert sent["artifact_ref"] == "runtime_artifact_0"
    assert sent["idempotency_key"] == "p7key_s5_final_text_0"
    assert sent["delivery_url_class"] == "safe_delivery_url_class_a"
    assert scan_sachima_s5_no_leak(result)["passed"] is True
    assert C.scan_projection_for_leak(controller.query()) is None


def test_s5_durable_preclaim_blocks_crash_recover_from_double_send() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    request = _request()

    # Simulate a process crash after S5 wrote the durable pre-claim but before P7
    # could return a terminal projection. Recovery must reattach to WATCH and must
    # not call the send seam.
    preclaim = controller.preclaim(request=request)
    assert preclaim["state"] == "claimed"
    assert preclaim["terminal"] is False

    adapter = FakeSendAdapter(store=store)
    recovered = controller.deliver(request=request, adapter=adapter)

    assert recovered["status"] == "watch"
    assert recovered["error_code"] == "p7_send_unknown"
    assert recovered["ack"] is None
    assert adapter.calls == []
    assert scan_sachima_s5_no_leak(recovered)["passed"] is True


def test_cancel_after_durable_preclaim_is_watch_and_preserves_resident_claim() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    request = _request(idempotency_key="p7key_s5_cancel_after_preclaim_0")

    # A durable pre-claim exists but no terminal projection has landed yet: the
    # send may have already crossed the pre-claim boundary, so cancellation must
    # resolve to WATCH, never a clean not-sent result, and must touch neither the
    # send seam nor the resident claim.
    preclaim = controller.preclaim(request=request)
    assert preclaim["state"] == "claimed"
    assert preclaim["terminal"] is False

    cancelled = controller.cancel(request=request)

    assert cancelled["status"] == "watch"
    assert cancelled["error_code"] == "p7_send_unknown"
    assert cancelled["ack"] is None
    assert scan_sachima_s5_no_leak(cancelled)["passed"] is True

    query = store.query()
    claims = query["claims"]
    assert isinstance(claims, dict)
    resident = claims["p7key_s5_cancel_after_preclaim_0"]
    assert isinstance(resident, dict)
    assert resident["state"] == "claimed"
    assert resident["terminal"] is False


def test_cancel_replays_clean_terminal_projection_and_rejects_divergent_request() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    adapter = FakeSendAdapter(store=store)
    request = _request(idempotency_key="p7key_s5_cancel_terminal_0")

    first = controller.deliver(request=request, adapter=adapter)
    replay = controller.cancel(request=request)
    divergent = controller.cancel(
        request=_request(idempotency_key="p7key_s5_cancel_terminal_0", target_ref="safe_recipient_group_b")
    )

    assert first["status"] == "delivered"
    assert replay == first
    assert divergent["status"] == "rejected"
    assert divergent["error_code"] == "p7_divergent_replay"
    assert len(adapter.calls) == 1


def test_cancel_malformed_resident_terminal_projection_fails_closed() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    adapter = FakeSendAdapter(store=store)
    request = _request(idempotency_key="p7key_s5_cancel_malformed_terminal_0")

    first = controller.deliver(request=request, adapter=adapter)
    claims = store.query()["claims"]
    assert isinstance(claims, dict)
    resident_claim = claims["p7key_s5_cancel_malformed_terminal_0"]
    assert isinstance(resident_claim, dict)
    resident_claim["projection"] = {
        "type": SACHIMA_P7_DELIVERY_RESULT_TYPE,
        "version": "sachima.p7.delivery_ack_controller.v0",
        "status": "delivered",
        "delivery_ref": "runtime_delivery_9",
        "surface": "rich_card",
        "attempt_id": "runtime_delivery_attempt_9",
        "idempotency_key": "p7key_clean_other",
        "slot_state": "acked",
        "ack": {
            "type": SACHIMA_P7_ACK_EVENT_TYPE,
            "ack_ref": "runtime_delivery_ack_0",
            "delivery_ref": "runtime_delivery_9",
            "surface": "rich_card",
            "status": "acknowledged",
            "source": "send_response",
            "duplicate": False,
            "state_version": 1,
            "side_effects": [],
        },
        "error_code": None,
        "side_effects": [],
    }
    forged_store = S5DurableDeliveryClaimStore(initial={"p7key_s5_cancel_malformed_terminal_0": resident_claim})

    recovered = _controller(store=forged_store).cancel(request=request)

    assert first["status"] == "delivered"
    assert recovered["status"] == "watch"
    assert recovered["error_code"] == "p7_send_unknown"
    assert scan_sachima_s5_no_leak(recovered)["passed"] is True
    assert len(adapter.calls) == 1


def test_cancel_terminal_projection_requires_stable_error_and_slot_state() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    adapter = FakeSendAdapter(store=store)
    request = _request(idempotency_key="p7key_s5_cancel_bad_failed_terminal_0")

    first = controller.deliver(request=request, adapter=adapter)
    claims = store.query()["claims"]
    assert isinstance(claims, dict)
    resident_claim = claims["p7key_s5_cancel_bad_failed_terminal_0"]
    assert isinstance(resident_claim, dict)
    resident_claim["projection"] = {
        "type": SACHIMA_P7_DELIVERY_RESULT_TYPE,
        "version": "sachima.p7.delivery_ack_controller.v0",
        "status": "failed",
        "delivery_ref": "runtime_delivery_0",
        "surface": "final_text",
        "attempt_id": "runtime_delivery_attempt_0",
        "idempotency_key": "p7key_s5_cancel_bad_failed_terminal_0",
        "slot_state": "acked",
        "ack": None,
        "error_code": "clean_but_not_stable",
        "side_effects": [],
    }
    forged_store = S5DurableDeliveryClaimStore(initial={"p7key_s5_cancel_bad_failed_terminal_0": resident_claim})

    recovered = _controller(store=forged_store).cancel(request=request)

    assert first["status"] == "delivered"
    assert recovered["status"] == "watch"
    assert recovered["error_code"] == "p7_send_unknown"
    assert scan_sachima_s5_no_leak(recovered)["passed"] is True
    assert len(adapter.calls) == 1


def test_cancel_terminal_projection_rejects_duplicate_ack_replay() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    adapter = FakeSendAdapter(store=store)
    request = _request(idempotency_key="p7key_s5_cancel_duplicate_ack_0")

    first = controller.deliver(request=request, adapter=adapter)
    claims = store.query()["claims"]
    assert isinstance(claims, dict)
    resident_claim = claims["p7key_s5_cancel_duplicate_ack_0"]
    assert isinstance(resident_claim, dict)
    projection = resident_claim["projection"]
    assert isinstance(projection, dict)
    ack = projection["ack"]
    assert isinstance(ack, dict)
    ack["duplicate"] = True
    forged_store = S5DurableDeliveryClaimStore(initial={"p7key_s5_cancel_duplicate_ack_0": resident_claim})

    recovered = _controller(store=forged_store).cancel(request=request)

    assert first["status"] == "delivered"
    assert recovered["status"] == "watch"
    assert recovered["error_code"] == "p7_send_unknown"
    assert scan_sachima_s5_no_leak(recovered)["passed"] is True
    assert len(adapter.calls) == 1


def test_identical_replay_returns_resident_projection_and_divergent_replay_fails_closed() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    adapter = FakeSendAdapter(store=store)
    first_request = _request(idempotency_key="p7key_s5_replay_0")

    first = controller.deliver(request=first_request, adapter=adapter)
    second = controller.deliver(request=first_request, adapter=adapter)
    divergent = controller.deliver(
        request=_request(idempotency_key="p7key_s5_replay_0", target_ref="safe_recipient_group_b"),
        adapter=adapter,
    )

    assert first["status"] == "delivered"
    assert second == first
    assert divergent["status"] == "rejected"
    assert divergent["error_code"] == "p7_divergent_replay"
    assert len(adapter.calls) == 1


def test_dirty_resident_terminal_projection_fails_closed_without_resend() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    adapter = FakeSendAdapter(store=store)
    request = _request(idempotency_key="p7key_s5_dirty_replay_0")

    first = controller.deliver(request=request, adapter=adapter)
    resident_claims = store.query()["claims"]
    assert isinstance(resident_claims, dict)
    resident_claim = resident_claims["p7key_s5_dirty_replay_0"]
    assert isinstance(resident_claim, dict)
    resident_projection = resident_claim["projection"]
    assert isinstance(resident_projection, dict)
    resident_projection["message_id"] = "om_" + "private_platform_id"
    resident_projection["card_json"] = "raw card payload"
    forged_store = S5DurableDeliveryClaimStore(initial={"p7key_s5_dirty_replay_0": resident_claim})
    recovered_adapter = FakeSendAdapter(store=forged_store)
    recovered = _controller(store=forged_store).deliver(request=request, adapter=recovered_adapter)

    assert first["status"] == "delivered"
    assert recovered["status"] == "watch"
    assert recovered["error_code"] == "p7_send_unknown"
    assert scan_sachima_s5_no_leak(recovered)["passed"] is True
    assert recovered_adapter.calls == []
    assert len(adapter.calls) == 1


def test_multi_surface_reconnect_preclaims_every_attempt_before_any_send_and_replays() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    adapter = FakeSendAdapter(store=store)
    request = _request(surfaces=("final_text", "rich_card"), idempotency_key="p7key_s5_multi_0")

    first = controller.deliver(request=request, adapter=adapter)
    second = controller.deliver(request=request, adapter=adapter)
    claims = store.query()["claims"]

    assert first["status"] == "delivered"
    assert second["status"] == "delivered"
    assert len(adapter.calls) == 2
    assert set(claims) == {"p7key_s5_multi_0", "p7key_s5_richcard_1"}
    assert all(claim["terminal"] is True for claim in claims.values())


def test_nested_attempt_policy_is_validated_before_any_surface_send() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = S5DeliveryReconnectController(
        enabled=True,
        approval_token=S5_DOWNSTREAM_DELIVERY_RECONNECT_APPROVAL_TOKEN,
        claim_store=store,
        approved_targets=("safe_recipient_group_a",),
        allowed_surfaces=("final_text", "rich_card"),
        delivery_url_class="safe_delivery_url_class_a",
        max_attempts=2,
    )
    request = _request(surfaces=("final_text", "rich_card"), idempotency_key="p7key_s5_nested_0")
    request["delivery_attempts"][1]["target_ref"] = "safe_recipient_group_z"
    adapter = FakeSendAdapter(store=store)

    result = controller.deliver(request=request, adapter=adapter)

    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_delivery_target_not_approved"
    assert adapter.calls == []
    assert store.query()["claims"] == {}


def test_malformed_later_attempt_is_rejected_before_first_surface_send() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    request = _request(surfaces=("final_text", "rich_card"), idempotency_key="p7key_s5_bad_attempt_0")
    request["delivery_attempts"][1]["attempt_id"] = "bad_attempt_id"
    adapter = FakeSendAdapter(store=store)

    result = controller.deliver(request=request, adapter=adapter)

    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_invalid_request"
    assert adapter.calls == []
    assert store.query()["claims"] == {}


def test_later_attempt_extra_field_is_rejected_before_first_surface_send() -> None:
    store = S5DurableDeliveryClaimStore()
    controller = _controller(store=store)
    request = _request(surfaces=("final_text", "rich_card"), idempotency_key="p7key_s5_extra_attempt_0")
    request["delivery_attempts"][1]["extra"] = "safe_but_not_allowed"
    adapter = FakeSendAdapter(store=store)

    result = controller.deliver(request=request, adapter=adapter)

    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_invalid_request"
    assert adapter.calls == []
    assert store.query()["claims"] == {}


def test_live_default_on_delivery_url_class_is_rejected_before_controller_admission() -> None:
    with pytest.raises(ValueError):
        S5DeliveryReconnectController(
            enabled=True,
            approval_token=S5_DOWNSTREAM_DELIVERY_RECONNECT_APPROVAL_TOKEN,
            claim_store=S5DurableDeliveryClaimStore(),
            approved_targets=("safe_recipient_group_a",),
            allowed_surfaces=("final_text",),
            delivery_url_class="safe_live_default_on",
            max_attempts=1,
        )


def test_idempotency_key_with_raw_material_marker_is_rejected_by_internal_guard() -> None:
    with pytest.raises(ValueError):
        _request(idempotency_key="p7key_raw_context")


@pytest.mark.parametrize(
    "overrides",
    [
        {"activity_output": _activity_output(artifact_kind="write_action")},
        {"target_ref": "oc_" + "private_chat"},
        {"target_ref": "safe_live_default_on"},
        {"surfaces": ("approve",)},
        {"delivery_role_key": "sachima_delivery_write_role"},
        {"delivery_role_key": "platform_derived_delivery_role"},
    ],
)
def test_closed_mapping_rejects_unknown_platform_write_and_live_values_before_send(overrides: dict[str, Any]) -> None:
    adapter = FakeSendAdapter()
    controller = _controller()

    with pytest.raises(ValueError):
        build_s5_delivery_reconnect_request(**dict(
            activity_output=overrides.pop("activity_output", _activity_output()),
            intent_class="architecture_packet",
            target_ref=overrides.pop("target_ref", "safe_recipient_group_a"),
            surfaces=overrides.pop("surfaces", ("final_text",)),
            delivery_role_key=overrides.pop("delivery_role_key", "sachima_delivery_read_only_reporter"),
            idempotency_key="p7key_s5_closed_mapping_0",
            **overrides,
        ))
    assert adapter.calls == []


def test_accepted_without_receipt_timeout_unknown_and_cancellation_are_watch_not_delivered() -> None:
    for adapter, expected_code in [
        (FakeSendAdapter(outcome="accepted", receipt_ref=None), "p7_ack_missing"),
        (FakeSendAdapter(outcome="timeout"), "p7_send_timeout"),
        (FakeSendAdapter(outcome="unknown"), "p7_send_unknown"),
    ]:
        controller = _controller(store=S5DurableDeliveryClaimStore())
        result = controller.deliver(request=_request(idempotency_key=f"p7key_s5_{expected_code}"), adapter=adapter)
        assert result["status"] == "watch"
        assert result["error_code"] == expected_code
        assert result["ack"] is None
        assert len(adapter.calls) == 1

    cancelled = _controller(store=S5DurableDeliveryClaimStore()).cancel(request=_request())
    assert cancelled["status"] == "cancelled"
    assert cancelled["error_code"] == "delivery_cancelled"
    assert cancelled["ack"] is None


def test_failure_retryability_splits_deterministic_from_transient_codes() -> None:
    deterministic = s5_delivery_failure_for_code("p7_delivery_disabled")
    transient = s5_delivery_failure_for_code("p7_send_timeout")
    cancelled = s5_delivery_failure_for_code("delivery_cancelled")

    assert isinstance(deterministic, ApplicationError)
    assert deterministic.type == "p7_delivery_disabled"
    assert deterministic.non_retryable is True
    assert transient.type == "p7_send_timeout"
    assert transient.non_retryable is False
    assert cancelled.type == "delivery_cancelled"
    assert cancelled.non_retryable is True


def test_no_leak_scans_reject_seeded_canaries_in_projection_and_bytes() -> None:
    controller = _controller(store=S5DurableDeliveryClaimStore())
    result = controller.deliver(request=_request(), adapter=FakeSendAdapter())
    projection = {"result": result, "query": controller.query(), "export": controller.export_state()}
    rendered = json.dumps(projection, sort_keys=True).encode("utf-8")

    assert scan_sachima_s5_no_leak(projection)["passed"] is True
    assert C.scan_projection_for_leak(projection, canaries=("raw_prompt_private", "oc_" + "private_chat", "card_json")) is None
    assert C.scan_bytes_for_leak(rendered, canaries=("raw_prompt_private", "oc_" + "private_chat", "card_json")) is None
    for forbidden in [b"raw_prompt", b"card_json", b"oc_", b"message_id", b"/tmp/", b"traceback"]:
        assert forbidden not in rendered.lower()


def test_forbidden_live_surface_static_contract_keeps_gateway_worker_and_platform_adapter_absent() -> None:
    contract = describe_sachima_s5_downstream_delivery_reconnect_contract()
    rendered = json.dumps(contract, sort_keys=True)

    assert "injected_fake_only" in rendered
    assert contract["gateway_temporal_caller"] is False
    assert contract["gateway_lifecycle_owner"] is False
    assert contract["gateway_worker_owner"] is False
    assert contract["platform_adapter_constructed"] is False
    assert contract["worker_started_by_s5"] is False
    assert contract["real_send_approved"] is False
