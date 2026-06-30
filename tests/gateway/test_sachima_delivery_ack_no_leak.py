"""Hostile-input / no-leak tests for the P7 delivery/ACK controller.

Every test here feeds the controller raw platform material, private ids, or
exception text through the slot, the attempt, or the fake adapter response, and
asserts the controller fails closed with a stable code and never echoes the
unsafe material into any returned projection or export.
"""

from __future__ import annotations

from typing import Any

import pytest

from gateway.sachima_delivery_ack import (
    SACHIMA_P7_DELIVERY_ATTEMPT_TYPE,
    SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
    SACHIMA_P7_DELIVERY_SLOT_TYPE,
    SachimaP7DeliveryAckController,
    sachima_p7_delivery_policy,
    scan_sachima_p7_no_leak,
)


def _policy(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        enabled=True,
        approval_token=SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
        approved_targets=["safe_recipient_group_a"],
        allowed_surfaces=["progress_card", "rich_card", "final_text", "media", "artifact"],
        delivery_url_class="safe_delivery_url_class_a",
        max_attempts=2,
    )
    base.update(overrides)
    return sachima_p7_delivery_policy(**base)


def _slot(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "type": SACHIMA_P7_DELIVERY_SLOT_TYPE,
        "delivery_ref": "runtime_delivery_0",
        "surface": "final_text",
        "artifact_ref": None,
        "required": True,
        "side_effects": [],
    }
    base.update(overrides)
    return base


def _attempt(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "type": SACHIMA_P7_DELIVERY_ATTEMPT_TYPE,
        "attempt_id": "runtime_delivery_attempt_0",
        "delivery_ref": "runtime_delivery_0",
        "surface": "final_text",
        "idempotency_key": "p7key_final_text_0",
        "target_ref": "safe_recipient_group_a",
        "artifact_ref": None,
        "side_effects": [],
    }
    base.update(overrides)
    return base


def _initialized_controller() -> SachimaP7DeliveryAckController:
    controller = SachimaP7DeliveryAckController(policy=_policy())
    controller.initialize_slot(_slot())
    return controller


def test_no_leak_scan_detects_planted_private_id() -> None:
    scan = scan_sachima_p7_no_leak({"leaked": {"chat_id": "oc_secret_chat"}})

    assert scan["passed"] is False
    assert scan["raw_marker_hits"] >= 1
    assert "chat_id" in scan["markers"]


def test_clean_projection_passes_no_leak_scan() -> None:
    scan = scan_sachima_p7_no_leak(
        {"slots": [{"delivery_ref": "runtime_delivery_0", "surface": "final_text", "state": "acked"}]}
    )

    assert scan == {"passed": True, "raw_marker_hits": 0, "markers": []}


def test_initialize_slot_rejects_raw_card_material() -> None:
    controller = SachimaP7DeliveryAckController(policy=_policy())

    with pytest.raises(ValueError):
        controller.initialize_slot(_slot(card_json={"blocks": ["secret"]}))


def test_unsafe_attempt_material_rejected_before_adapter_call() -> None:
    controller = _initialized_controller()

    class Tripwire:
        calls: list[Any] = []

        def __call__(self, send_request: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - must not run
            Tripwire.calls.append(send_request)
            return {"outcome": "accepted", "delivery_ref": "runtime_delivery_0", "surface": "final_text", "receipt_ref": "runtime_delivery_ack_0"}

    adapter = Tripwire()
    result = controller.deliver_slot(
        attempt=_attempt(callback_payload={"chat_id": "oc_private"}),
        adapter=adapter,
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_ack_unsafe_material"
    assert Tripwire.calls == []
    assert scan_sachima_p7_no_leak(result)["passed"] is True


def test_adapter_raw_payload_response_rejected_as_unsafe() -> None:
    controller = _initialized_controller()

    def adapter(send_request: dict[str, Any]) -> dict[str, Any]:
        return {
            "outcome": "accepted",
            "delivery_ref": "runtime_delivery_0",
            "surface": "final_text",
            "receipt_ref": "runtime_delivery_ack_0",
            "card_json": {"blocks": ["leak"]},
            "chat_id": "oc_private_chat",
        }

    result = controller.deliver_slot(attempt=_attempt(), adapter=adapter)

    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_ack_unsafe_material"
    assert result["ack"] is None
    assert scan_sachima_p7_no_leak(result)["passed"] is True


def test_unsafe_receipt_ref_is_rejected() -> None:
    controller = _initialized_controller()

    def adapter(send_request: dict[str, Any]) -> dict[str, Any]:
        return {
            "outcome": "accepted",
            "delivery_ref": "runtime_delivery_0",
            "surface": "final_text",
            "receipt_ref": "oc_private_message_id",
        }

    result = controller.deliver_slot(attempt=_attempt(), adapter=adapter)

    assert result["status"] == "rejected"
    assert result["error_code"] == "p7_ack_unsafe_material"
    assert result["ack"] is None


def test_adapter_exception_text_is_not_leaked_and_becomes_watch() -> None:
    controller = _initialized_controller()

    def adapter(send_request: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("private traceback bearer sk-secret /home/user/secret should not leak")

    result = controller.deliver_slot(attempt=_attempt(), adapter=adapter)

    rendered = repr(result).lower()
    assert result["status"] == "watch"
    assert result["error_code"] == "p7_send_unknown"
    assert result["ack"] is None
    assert "traceback" not in rendered
    assert "bearer" not in rendered
    assert "sk-secret" not in rendered
    assert scan_sachima_p7_no_leak(result)["passed"] is True


def test_full_query_export_is_sanitized_after_delivery() -> None:
    controller = _initialized_controller()

    def adapter(send_request: dict[str, Any]) -> dict[str, Any]:
        return {
            "outcome": "accepted",
            "delivery_ref": "runtime_delivery_0",
            "surface": "final_text",
            "receipt_ref": "runtime_delivery_ack_0",
        }

    controller.deliver_slot(attempt=_attempt(), adapter=adapter)
    projection = controller.query()

    scan = scan_sachima_p7_no_leak(projection)
    assert scan["passed"] is True
    # The approval token / url secrets must never appear in an export.
    rendered = repr(projection).lower()
    assert "approval_token" not in rendered
    assert SACHIMA_P7_DELIVERY_ENABLE_TOKEN.lower() not in rendered


# --- Hostile public-builder inputs: type-confused token and untrusted sequences ---


class _LyingToken(str):
    """A ``str`` subclass that claims equality with everything.

    Models a caller who does NOT hold the real approval token but overrides
    comparison so that a naive ``approval_token != EXPECTED`` guard sees a match.
    The public builder must reject it by exact-type check, never trust ``==``.
    """

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = str.__hash__


class _HostileSequence:
    """A non-``list`` object that records any iteration or truth-test.

    If the public builder coerces it with ``list(x or [])`` these counters fire,
    proving an untrusted ``__iter__`` / ``__bool__`` ran during policy admission.
    A safe builder rejects it by exact-type check *before* any of them run. The
    stored items would pass downstream validation if iterated, so rejection
    before iteration is the only thing that can stop it.
    """

    def __init__(self, items: list[str]) -> None:
        self._items = items
        self.iter_calls = 0
        self.bool_calls = 0

    def __iter__(self):  # pragma: no cover - must not run
        self.iter_calls += 1
        return iter(self._items)

    def __bool__(self) -> bool:  # pragma: no cover - must not run
        self.bool_calls += 1
        return True

    def __len__(self) -> int:  # pragma: no cover - must not run
        self.bool_calls += 1
        return len(self._items)


def test_policy_builder_rejects_lying_str_subclass_token() -> None:
    hostile = _LyingToken("definitely_not_the_real_token")
    # The hostile token defeats a plain ``!=`` comparison ...
    assert (hostile != SACHIMA_P7_DELIVERY_ENABLE_TOKEN) is False

    # ... but the builder must still refuse to enable a policy off it.
    with pytest.raises(ValueError):
        sachima_p7_delivery_policy(
            enabled=True,
            approval_token=hostile,
            approved_targets=["safe_recipient_group_a"],
            allowed_surfaces=["final_text"],
            delivery_url_class="safe_delivery_url_class_a",
        )


def test_lying_str_subclass_token_cannot_enable_controller() -> None:
    hostile = _LyingToken("definitely_not_the_real_token")

    # End to end: the public enable path (builder -> controller) must raise on a
    # token the caller never actually presented; no enabled controller may come
    # up off a laundered approval token.
    with pytest.raises(ValueError):
        policy = sachima_p7_delivery_policy(
            enabled=True,
            approval_token=hostile,
            approved_targets=["safe_recipient_group_a"],
            allowed_surfaces=["final_text"],
            delivery_url_class="safe_delivery_url_class_a",
        )
        SachimaP7DeliveryAckController(policy=policy)


def test_policy_builder_rejects_hostile_iterable_targets_without_iterating() -> None:
    hostile = _HostileSequence(["safe_recipient_group_a"])

    with pytest.raises(ValueError):
        sachima_p7_delivery_policy(
            enabled=True,
            approval_token=SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
            approved_targets=hostile,
            allowed_surfaces=["final_text"],
            delivery_url_class="safe_delivery_url_class_a",
        )

    # The hostile object's iteration / truth-testing must never have run.
    assert hostile.iter_calls == 0
    assert hostile.bool_calls == 0


def test_policy_builder_rejects_hostile_iterable_surfaces_without_iterating() -> None:
    hostile = _HostileSequence(["final_text"])

    with pytest.raises(ValueError):
        sachima_p7_delivery_policy(
            enabled=True,
            approval_token=SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
            approved_targets=["safe_recipient_group_a"],
            allowed_surfaces=hostile,
            delivery_url_class="safe_delivery_url_class_a",
        )

    assert hostile.iter_calls == 0
    assert hostile.bool_calls == 0
