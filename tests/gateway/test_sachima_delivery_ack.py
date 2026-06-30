"""Focused, offline TDD tests for the P7 default-off delivery/ACK controller.

These tests exercise the controller through a caller-supplied fake adapter seam
only. No real delivery, network, Gateway, runtime, or platform adapter is
touched. They assert the P7 closure semantics: default-off, bounded
target/surface approval, surface separation, ACK source-of-truth, retry /
duplicate idempotency, WATCH-on-unknown, and rollback.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from gateway.sachima_delivery_ack import (
    SACHIMA_P7_ACK_EVENT_TYPE,
    SACHIMA_P7_CONTRACT_TYPE,
    SACHIMA_P7_DELIVERY_ACK_VERSION,
    SACHIMA_P7_DELIVERY_ATTEMPT_TYPE,
    SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
    SACHIMA_P7_DELIVERY_POLICY_TYPE,
    SACHIMA_P7_DELIVERY_RESULT_TYPE,
    SACHIMA_P7_DELIVERY_SLOT_TYPE,
    SACHIMA_P7_STATE_PROJECTION_TYPE,
    SACHIMA_P7_SUCCESS_VERDICT,
    SachimaP7DeliveryAckController,
    describe_sachima_p7_delivery_ack_contract,
    sachima_p7_delivery_policy,
    scan_sachima_p7_no_leak,
)


def _policy(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        enabled=True,
        approval_token=SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
        approved_targets=["safe_recipient_group_a", "safe_recipient_group_b"],
        allowed_surfaces=["progress_card", "rich_card", "final_text", "media", "artifact"],
        delivery_url_class="safe_delivery_url_class_a",
        max_attempts=2,
    )
    base.update(overrides)
    return sachima_p7_delivery_policy(**base)


def _slot(
    *,
    delivery_ref: str = "runtime_delivery_0",
    surface: str = "final_text",
    artifact_ref: str | None = None,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "type": SACHIMA_P7_DELIVERY_SLOT_TYPE,
        "delivery_ref": delivery_ref,
        "surface": surface,
        "artifact_ref": artifact_ref,
        "required": required,
        "side_effects": [],
    }


def _attempt(
    *,
    attempt_id: str = "runtime_delivery_attempt_0",
    delivery_ref: str = "runtime_delivery_0",
    surface: str = "final_text",
    idempotency_key: str = "p7key_final_text_0",
    target_ref: str = "safe_recipient_group_a",
    artifact_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "type": SACHIMA_P7_DELIVERY_ATTEMPT_TYPE,
        "attempt_id": attempt_id,
        "delivery_ref": delivery_ref,
        "surface": surface,
        "idempotency_key": idempotency_key,
        "target_ref": target_ref,
        "artifact_ref": artifact_ref,
        "side_effects": [],
    }


class FakeAdapter:
    """Caller-supplied fake send seam recording every request it receives."""

    def __init__(
        self,
        *,
        outcome: str = "accepted",
        receipt_ref: str | None = "runtime_delivery_ack_0",
        response_override: dict[str, Any] | None = None,
        raises: bool = False,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.outcome = outcome
        self.receipt_ref = receipt_ref
        self.response_override = response_override
        self.raises = raises

    def __call__(self, send_request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(send_request))
        if self.raises:
            raise RuntimeError("adapter private failure should not leak: bearer abc123")
        if self.response_override is not None:
            return dict(self.response_override)
        return {
            "outcome": self.outcome,
            "delivery_ref": send_request["delivery_ref"],
            "surface": send_request["surface"],
            "receipt_ref": self.receipt_ref if self.outcome == "accepted" else None,
        }


def _deliver(
    *,
    policy: dict[str, Any],
    slots: list[dict[str, Any]],
    attempt: dict[str, Any],
    adapter: Callable[[dict[str, Any]], Any],
) -> tuple[SachimaP7DeliveryAckController, dict[str, Any]]:
    controller = SachimaP7DeliveryAckController(policy=policy)
    for slot in slots:
        controller.initialize_slot(slot)
    result = controller.deliver_slot(attempt=attempt, adapter=adapter)
    return controller, result


def test_contract_descriptor_keeps_boundaries_explicit() -> None:
    contract = describe_sachima_p7_delivery_ack_contract()

    assert contract["type"] == SACHIMA_P7_CONTRACT_TYPE
    assert contract["version"] == SACHIMA_P7_DELIVERY_ACK_VERSION
    assert contract["default_off"] is True
    assert contract["verdict"] == SACHIMA_P7_SUCCESS_VERDICT
    assert contract["allowed_surfaces"] == ["progress_card", "rich_card", "final_text", "media", "artifact"]
    assert contract["ack_sources"] == ["send_response", "approved_receipt"]
    assert contract["future_canary_approval_required"] is True
    for approval in [
        "bounded_recipient_canary_send",
        "limited_live_pilot",
        "live_default_on_behavior",
        "public_ingress",
        "production_config_write",
        "gateway_restart_or_reload",
        "gateway_owned_temporal_worker_lifecycle",
        "platform_adapter_mutation",
        "real_agent_execution",
        "write_capable_roles",
        "production_traffic",
    ]:
        assert approval in contract["separate_approvals"]
    assert contract["side_effects"] == []


def test_disabled_policy_makes_zero_adapter_calls() -> None:
    adapter = FakeAdapter()
    controller, result = _deliver(
        policy=sachima_p7_delivery_policy(enabled=False),
        slots=[_slot()],
        attempt=_attempt(),
        adapter=adapter,
    )

    assert result["type"] == SACHIMA_P7_DELIVERY_RESULT_TYPE
    assert result["status"] == "disabled"
    assert result["error_code"] == "p7_delivery_disabled"
    assert result["ack"] is None
    assert adapter.calls == []
    assert controller.query()["enabled"] is False


def test_enabled_without_delivery_url_class_is_unconfigured() -> None:
    adapter = FakeAdapter()
    controller, result = _deliver(
        policy=_policy(delivery_url_class=""),
        slots=[_slot()],
        attempt=_attempt(),
        adapter=adapter,
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_delivery_url_unconfigured"
    assert adapter.calls == []


def test_unapproved_target_fails_before_adapter_call() -> None:
    adapter = FakeAdapter()
    controller, result = _deliver(
        policy=_policy(),
        slots=[_slot()],
        attempt=_attempt(target_ref="safe_recipient_group_unapproved"),
        adapter=adapter,
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_delivery_target_not_approved"
    assert adapter.calls == []


def test_unapproved_surface_fails_before_adapter_call() -> None:
    adapter = FakeAdapter()
    controller, result = _deliver(
        policy=_policy(allowed_surfaces=["final_text"]),
        slots=[_slot(delivery_ref="runtime_delivery_3", surface="media")],
        attempt=_attempt(delivery_ref="runtime_delivery_3", surface="media", idempotency_key="p7key_media_3"),
        adapter=adapter,
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_delivery_surface_not_approved"
    assert adapter.calls == []


def test_ack_for_uninitialized_slot_is_rejected() -> None:
    adapter = FakeAdapter()
    controller = SachimaP7DeliveryAckController(policy=_policy())

    result = controller.deliver_slot(attempt=_attempt(), adapter=adapter)

    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_ack_target_mismatch"
    assert adapter.calls == []


def test_attempt_surface_must_match_initialized_slot() -> None:
    adapter = FakeAdapter()
    controller, result = _deliver(
        policy=_policy(),
        slots=[_slot(surface="final_text")],
        attempt=_attempt(surface="rich_card"),
        adapter=adapter,
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_ack_target_mismatch"
    assert adapter.calls == []


def test_accepted_send_records_ack_only_for_initialized_slot() -> None:
    adapter = FakeAdapter(outcome="accepted", receipt_ref="runtime_delivery_ack_0")
    controller, result = _deliver(
        policy=_policy(),
        slots=[_slot()],
        attempt=_attempt(),
        adapter=adapter,
    )

    assert result["status"] == "delivered"
    assert result["error_code"] is None
    assert result["slot_state"] == "acked"
    assert len(adapter.calls) == 1
    ack = result["ack"]
    assert ack is not None
    assert ack["type"] == SACHIMA_P7_ACK_EVENT_TYPE
    assert ack["delivery_ref"] == "runtime_delivery_0"
    assert ack["surface"] == "final_text"
    assert ack["status"] == "acknowledged"
    assert ack["source"] == "send_response"
    assert ack["duplicate"] is False
    # The adapter never receives raw recipient material — only safe refs/labels.
    sent = adapter.calls[0]
    assert sent["delivery_ref"] == "runtime_delivery_0"
    assert sent["target_ref"] == "safe_recipient_group_a"
    assert sent["delivery_url_class"] == "safe_delivery_url_class_a"


def test_rich_card_ack_does_not_imply_final_text_delivery() -> None:
    adapter = FakeAdapter(outcome="accepted", receipt_ref="runtime_delivery_ack_0")
    controller = SachimaP7DeliveryAckController(policy=_policy())
    controller.initialize_slot(_slot(delivery_ref="runtime_delivery_0", surface="rich_card"))
    controller.initialize_slot(_slot(delivery_ref="runtime_delivery_1", surface="final_text"))

    result = controller.deliver_slot(
        attempt=_attempt(delivery_ref="runtime_delivery_0", surface="rich_card", idempotency_key="p7key_rich_0"),
        adapter=adapter,
    )

    assert result["status"] == "delivered"
    assert result["surface"] == "rich_card"

    projection = controller.query()
    states = {slot["delivery_ref"]: slot["state"] for slot in projection["slots"]}
    assert states["runtime_delivery_0"] == "acked"
    assert states["runtime_delivery_1"] == "initialized"
    ack_surfaces = [event["surface"] for event in projection["ack_events"]]
    assert ack_surfaces == ["rich_card"]
    assert "final_text" not in ack_surfaces


def test_failed_send_records_no_ack() -> None:
    adapter = FakeAdapter(outcome="failed")
    controller, result = _deliver(
        policy=_policy(),
        slots=[_slot()],
        attempt=_attempt(),
        adapter=adapter,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "p7_send_rejected"
    assert result["slot_state"] == "failed"
    assert result["ack"] is None
    assert len(adapter.calls) == 1
    assert controller.query()["ack_events"] == []


def test_timeout_outcome_becomes_watch_not_success() -> None:
    adapter = FakeAdapter(outcome="timeout")
    controller, result = _deliver(
        policy=_policy(),
        slots=[_slot()],
        attempt=_attempt(),
        adapter=adapter,
    )

    assert result["status"] == "watch"
    assert result["error_code"] == "p7_send_timeout"
    assert result["slot_state"] == "watch"
    assert result["ack"] is None


def test_unknown_outcome_becomes_watch_not_success() -> None:
    adapter = FakeAdapter(outcome="unknown")
    controller, result = _deliver(
        policy=_policy(),
        slots=[_slot()],
        attempt=_attempt(),
        adapter=adapter,
    )

    assert result["status"] == "watch"
    assert result["error_code"] == "p7_send_unknown"
    assert result["slot_state"] == "watch"
    assert result["ack"] is None


def test_accepted_send_without_receipt_ref_is_ack_missing() -> None:
    adapter = FakeAdapter(outcome="accepted", receipt_ref=None)
    controller, result = _deliver(
        policy=_policy(),
        slots=[_slot()],
        attempt=_attempt(),
        adapter=adapter,
    )

    assert result["status"] == "watch"
    assert result["error_code"] == "p7_ack_missing"
    assert result["ack"] is None
    assert len(adapter.calls) == 1


def test_identical_replay_is_idempotent_and_returns_stored_projection() -> None:
    adapter = FakeAdapter(outcome="accepted", receipt_ref="runtime_delivery_ack_0")
    controller = SachimaP7DeliveryAckController(policy=_policy())
    controller.initialize_slot(_slot())

    first = controller.deliver_slot(attempt=_attempt(), adapter=adapter)
    second = controller.deliver_slot(attempt=_attempt(), adapter=adapter)

    assert first["status"] == "delivered"
    assert second == first
    assert len(adapter.calls) == 1
    assert controller.query()["counts"]["duplicate_replays"] == 1


def test_divergent_replay_fails_closed_before_adapter_call() -> None:
    adapter = FakeAdapter(outcome="accepted", receipt_ref="runtime_delivery_ack_0")
    controller = SachimaP7DeliveryAckController(policy=_policy())
    controller.initialize_slot(_slot())

    first = controller.deliver_slot(attempt=_attempt(), adapter=adapter)
    divergent = controller.deliver_slot(
        attempt=_attempt(target_ref="safe_recipient_group_b"),
        adapter=adapter,
    )

    assert first["status"] == "delivered"
    assert divergent["status"] == "rejected"
    assert divergent["error_code"] == "p7_divergent_replay"
    assert len(adapter.calls) == 1


def test_distinct_attempt_on_acked_slot_is_duplicate_ack() -> None:
    adapter = FakeAdapter(outcome="accepted", receipt_ref="runtime_delivery_ack_0")
    controller = SachimaP7DeliveryAckController(policy=_policy())
    controller.initialize_slot(_slot())

    first = controller.deliver_slot(attempt=_attempt(), adapter=adapter)
    again = controller.deliver_slot(
        attempt=_attempt(attempt_id="runtime_delivery_attempt_1", idempotency_key="p7key_final_text_1"),
        adapter=adapter,
    )

    assert first["status"] == "delivered"
    assert again["status"] == "rejected"
    assert again["error_code"] == "p7_ack_duplicate"
    assert len(adapter.calls) == 1


def test_max_attempts_exceeded_blocks_further_sends() -> None:
    adapter = FakeAdapter(outcome="timeout")
    controller = SachimaP7DeliveryAckController(policy=_policy(max_attempts=1))
    controller.initialize_slot(_slot())

    first = controller.deliver_slot(attempt=_attempt(), adapter=adapter)
    retry = controller.deliver_slot(
        attempt=_attempt(attempt_id="runtime_delivery_attempt_1", idempotency_key="p7key_final_text_1"),
        adapter=adapter,
    )

    assert first["status"] == "watch"
    assert retry["status"] == "rejected"
    assert retry["error_code"] == "p7_max_attempts_exceeded"
    assert len(adapter.calls) == 1


def test_rollback_disables_new_sends_but_preserves_query_export() -> None:
    adapter = FakeAdapter(outcome="accepted", receipt_ref="runtime_delivery_ack_0")
    controller = SachimaP7DeliveryAckController(policy=_policy())
    controller.initialize_slot(_slot(delivery_ref="runtime_delivery_0", surface="final_text"))
    controller.initialize_slot(_slot(delivery_ref="runtime_delivery_1", surface="rich_card"))

    delivered = controller.deliver_slot(attempt=_attempt(), adapter=adapter)
    rollback = controller.rollback()
    blocked = controller.deliver_slot(
        attempt=_attempt(
            attempt_id="runtime_delivery_attempt_1",
            delivery_ref="runtime_delivery_1",
            surface="rich_card",
            idempotency_key="p7key_rich_1",
        ),
        adapter=adapter,
    )

    assert delivered["status"] == "delivered"
    assert rollback["rolled_back"] is True
    assert blocked["status"] == "rolled_back"
    assert blocked["error_code"] == "p7_rollback_active"
    assert len(adapter.calls) == 1

    projection = controller.query()
    assert projection["type"] == SACHIMA_P7_STATE_PROJECTION_TYPE
    assert projection["rolled_back"] is True
    # Existing delivered state and ACK evidence survive rollback for query/export.
    states = {slot["delivery_ref"]: slot["state"] for slot in projection["slots"]}
    assert states["runtime_delivery_0"] == "acked"
    assert states["runtime_delivery_1"] == "initialized"
    assert [event["delivery_ref"] for event in projection["ack_events"]] == ["runtime_delivery_0"]
    assert scan_sachima_p7_no_leak(projection)["passed"] is True


def test_policy_builder_rejects_enabled_without_exact_token() -> None:
    with pytest.raises(ValueError):
        sachima_p7_delivery_policy(
            enabled=True,
            approval_token="not_the_real_token",
            approved_targets=["safe_recipient_group_a"],
            allowed_surfaces=["final_text"],
            delivery_url_class="safe_delivery_url_class_a",
        )


def test_disabled_policy_builder_is_inert_default_off_shape() -> None:
    policy = sachima_p7_delivery_policy(enabled=False)

    assert policy["type"] == SACHIMA_P7_DELIVERY_POLICY_TYPE
    assert policy["enabled"] is False
    assert policy["mode"] == "default_off"
    assert policy["approved_targets"] == []
    assert policy["allowed_surfaces"] == []
    assert policy["delivery_url_class"] == ""
    assert policy["approval_token"] == ""
    assert policy["side_effects"] == []
