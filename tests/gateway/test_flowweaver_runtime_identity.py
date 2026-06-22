"""Tests for FlowWeaver Phase 5E runtime identity derivation."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping

from gateway.flowweaver_runtime_identity import (
    FLOWWEAVER_RUNTIME_IDENTITY_ACCEPTED,
    FLOWWEAVER_RUNTIME_IDENTITY_REJECTED,
    FLOWWEAVER_RUNTIME_IDENTITY_TYPE,
    derive_flowweaver_runtime_identity,
)


_RUNTIME_TX_RE = re.compile(r"^runtime_tx_shadow_[a-f0-9]{20}$")
_RUNTIME_EVENT_RE = re.compile(r"^runtime_event_start_shadow_[a-f0-9]{20}$")


def safe_snapshot_ref(*, index: int = 0, created_at: str | None = None) -> dict[str, str]:
    ref = {
        "snapshot_key": "flowweaver_shadow_snapshot",
        "transaction_id": f"tx_runtime_identity_{index}",
        "correlation_id": f"turn_runtime_identity_{index}",
        "snapshot_id": f"snap_runtime_identity_{index}",
    }
    if created_at is not None:
        ref["created_at"] = created_at
    return ref


def assert_safe_rejection(identity: dict[str, object], *, reason: str, forbidden: str | None = None) -> None:
    rendered = repr(identity).lower()
    assert identity["type"] == FLOWWEAVER_RUNTIME_IDENTITY_TYPE
    assert identity["verdict"] == FLOWWEAVER_RUNTIME_IDENTITY_REJECTED
    assert identity["reason"] == reason
    assert identity["transaction_id"] is None
    assert identity["workflow_id"] is None
    assert identity["idempotency_key"] is None
    assert identity["side_effects"] == []
    if forbidden is not None:
        assert forbidden.lower() not in rendered


def test_runtime_identity_is_deterministic_variable_synthetic_and_opaque() -> None:
    snapshot_ref = safe_snapshot_ref(index=1)

    first = derive_flowweaver_runtime_identity(snapshot_ref)
    second = derive_flowweaver_runtime_identity(dict(snapshot_ref))
    different = derive_flowweaver_runtime_identity(safe_snapshot_ref(index=2))
    rendered = repr(first).lower()

    assert first["type"] == FLOWWEAVER_RUNTIME_IDENTITY_TYPE
    assert first["verdict"] == FLOWWEAVER_RUNTIME_IDENTITY_ACCEPTED
    assert first["reason"] == "ok"
    assert first["strategy"] == "shadow_ref_hash_v0"
    assert first["checks"] == {
        "snapshot_ref_valid": True,
        "ids_synthetic": True,
        "private_markers_absent": True,
        "secret_markers_absent": True,
        "source_values_not_exported": True,
    }
    assert first["side_effects"] == []
    assert first["transaction_id"] == second["transaction_id"]
    assert first["workflow_id"] == second["workflow_id"]
    assert first["idempotency_key"] == second["idempotency_key"]
    assert first["workflow_id"] == first["transaction_id"]
    assert first["transaction_id"] != different["transaction_id"]
    assert _RUNTIME_TX_RE.fullmatch(first["transaction_id"])
    assert _RUNTIME_TX_RE.fullmatch(first["workflow_id"])
    assert _RUNTIME_EVENT_RE.fullmatch(first["idempotency_key"])
    for raw_value in snapshot_ref.values():
        assert raw_value not in rendered


def test_runtime_identity_uses_safe_created_at_to_distinguish_same_snapshot_ref_turns() -> None:
    first_ref = safe_snapshot_ref(index=7, created_at="2026-05-06t00_00_01z")
    second_ref = safe_snapshot_ref(index=7, created_at="2026-05-06t00_00_02z")

    first = derive_flowweaver_runtime_identity(first_ref)
    first_again = derive_flowweaver_runtime_identity(dict(first_ref))
    second = derive_flowweaver_runtime_identity(second_ref)
    rendered = repr(first).lower() + repr(second).lower()

    assert first["verdict"] == FLOWWEAVER_RUNTIME_IDENTITY_ACCEPTED
    assert second["verdict"] == FLOWWEAVER_RUNTIME_IDENTITY_ACCEPTED
    assert first["transaction_id"] == first_again["transaction_id"]
    assert first["transaction_id"] != second["transaction_id"]
    assert first_ref["created_at"] not in rendered
    assert second_ref["created_at"] not in rendered


def test_runtime_identity_rejects_invalid_snapshot_ref_shapes_without_echo() -> None:
    unsafe_value = "om_" + "private_message"
    cases: list[object] = [
        None,
        {},
        {"snapshot_key": "flowweaver_shadow_snapshot"},
        {**safe_snapshot_ref(index=3), "extra": "value"},
        {**safe_snapshot_ref(index=3), "snapshot_key": "flowweaver_shadow_capture"},
        {**safe_snapshot_ref(index=3), "transaction_id": "runtime_tx_not_a_shadow_ref"},
        {**safe_snapshot_ref(index=3), "correlation_id": "tx_wrong_prefix"},
        {**safe_snapshot_ref(index=3), "snapshot_id": "om_" + "private_message"},
    ]

    for candidate in cases:
        assert_safe_rejection(
            derive_flowweaver_runtime_identity(candidate),
            reason="invalid_snapshot_ref",
            forbidden=unsafe_value,
        )


def test_runtime_identity_rejects_embedded_platform_and_secret_markers_without_echo() -> None:
    marker_cases = (
        ("transaction_id", "tx_safe_oc_private"),
        ("transaction_id", "tx_safe_ou_private"),
        ("correlation_id", "turn_safe_chat_marker"),
        ("correlation_id", "turn_safe_message_marker"),
        ("snapshot_id", "snap_safe_platform_marker"),
        ("snapshot_id", "snap_safe_feishu_marker"),
        ("snapshot_id", "snap_safe_lark_marker"),
        ("snapshot_id", "snap_safe_telegram_marker"),
        ("transaction_id", "tx_safe_private_marker"),
        ("transaction_id", "tx_safe_" + "token" + "_marker"),
        ("transaction_id", "tx_safe_" + "secret" + "_marker"),
        ("correlation_id", "turn_safe_" + "password" + "_marker"),
        ("snapshot_id", "snap_safe_" + "api" + "_key_marker"),
        ("snapshot_id", "snap_safe_bearer_marker"),
        ("snapshot_id", "snap_safe_sk" + "-marker"),
    )

    for key, unsafe_value in marker_cases:
        candidate = safe_snapshot_ref(index=4)
        candidate[key] = unsafe_value
        identity = derive_flowweaver_runtime_identity(candidate)
        assert_safe_rejection(identity, reason="unsafe_runtime_identity", forbidden=unsafe_value)


class HostileMapping(Mapping[str, object]):
    def __iter__(self) -> Iterator[str]:
        raise AssertionError("identity helper must reject Mapping before iteration")

    def __len__(self) -> int:
        raise AssertionError("identity helper must reject Mapping before length")

    def __getitem__(self, key: str) -> object:
        raise AssertionError("identity helper must reject Mapping before lookup")


class MutatingString(str):
    def __new__(cls, value: str, touched: list[str]) -> "MutatingString":
        obj = str.__new__(cls, value)
        obj.touched = touched
        return obj

    def __eq__(self, other: object) -> bool:  # pragma: no cover - test fails if called
        self.touched.append("eq")
        return super().__eq__(other)


class MutatingValue:
    def __init__(self) -> None:
        self.touched: list[str] = []

    def __eq__(self, other: object) -> bool:  # pragma: no cover - test fails if called
        self.touched.append("eq")
        return False

    def __repr__(self) -> str:
        return "om_" + "private_message"


def test_runtime_identity_rejects_hostile_mappings_str_subclasses_and_mutating_values_first() -> None:
    assert_safe_rejection(
        derive_flowweaver_runtime_identity(HostileMapping()),
        reason="invalid_snapshot_ref",
    )

    touched: list[str] = []
    str_subclass_candidate = safe_snapshot_ref(index=5)
    str_subclass_candidate["transaction_id"] = MutatingString("tx_runtime_identity_5", touched)
    assert_safe_rejection(
        derive_flowweaver_runtime_identity(str_subclass_candidate),
        reason="invalid_snapshot_ref",
    )
    assert touched == []

    mutating_value = MutatingValue()
    mutating_candidate: dict[str, object] = safe_snapshot_ref(index=6)
    mutating_candidate["correlation_id"] = mutating_value
    assert_safe_rejection(
        derive_flowweaver_runtime_identity(mutating_candidate),
        reason="invalid_snapshot_ref",
        forbidden="om_" + "private_message",
    )
    assert mutating_value.touched == []
