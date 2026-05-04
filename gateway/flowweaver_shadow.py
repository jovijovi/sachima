"""Default-off FlowWeaver shadow tap for Gateway lifecycle tests.

The tap is deliberately inert: it performs no platform I/O, persistence, service
startup, or rendering. It only attaches the Phase-4A sanitized v0 snapshot to the
in-memory ``agent_result`` dict when explicitly enabled by config.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from gateway.delivery_state import ensure_delivery_state
from gateway.flowweaver_contract import (
    FLOWWEAVER_CONTRACT_VERSION,
    FLOWWEAVER_HANDLE_TYPE,
    build_flowweaver_v0_snapshot,
)
from gateway.progress.events import TransactionSnapshot
from utils import is_truthy_value

FLOWWEAVER_SHADOW_CONFIG_KEY = "flowweaver_shadow"
FLOWWEAVER_SHADOW_SNAPSHOT_KEY = "flowweaver_shadow_snapshot"
FLOWWEAVER_SHADOW_CAPTURE_KEY = "flowweaver_shadow_capture"
FLOWWEAVER_SHADOW_CAPTURE_TYPE = "flowweaver.gateway.shadow_capture.v0"
FLOWWEAVER_SHADOW_AUDIT_TYPE = "flowweaver.gateway.shadow_audit.v0"
FLOWWEAVER_SHADOW_AUDIT_READY = "ready"
FLOWWEAVER_SHADOW_AUDIT_REJECTED = "rejected"
FLOWWEAVER_SHADOW_AUDIT_UNSAFE = "unsafe"
FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH = "schema_mismatch"
_FORBIDDEN_CAPTURE_SIDE_EFFECTS = ["send", "edit", "render", "persist", "temporal"]
_ALLOWED_CAPTURE_CONSUMERS = ["in_memory_test_probe", "future_flowweaver_runtime"]
_SAFE_SHADOW_REF_RE = re.compile(r"^(?:tx|turn|snap)_[a-z0-9][a-z0-9_]{0,127}$")
_UNSAFE_SHADOW_REF_RE = re.compile(
    r"(?i)(?:^|_)(?:feishu|lark|telegram|discord|slack|whatsapp|wecom|dingtalk|"
    r"chat|user|thread|topic|oc|ou|om|open_id|union_id|authorization|api_key|apikey|"
    r"token|secret|password|passwd|bearer|credential|webhook|raw|stdout|stderr)(?:_|$)"
)


def is_flowweaver_shadow_enabled(task_tracker_config: object) -> bool:
    """Return True only for the explicit task-tracker shadow flag."""

    if not isinstance(task_tracker_config, Mapping):
        return False
    return is_truthy_value(
        task_tracker_config.get(FLOWWEAVER_SHADOW_CONFIG_KEY),
        default=False,
    )


def attach_flowweaver_shadow_snapshot(
    agent_result: dict[str, Any],
    progress_snapshot: TransactionSnapshot,
    *,
    enabled: bool,
    source: object | None = None,
    final_text: str | None = None,
) -> dict[str, Any] | None:
    """Attach a sanitized FlowWeaver v0 snapshot to ``agent_result``.

    Failure is fail-closed for runtime behavior: the Gateway should continue as
    if the tap did not exist. Callers can inspect ``None`` in tests/logging, but
    no exception escapes the shadow seam.
    """

    if not enabled:
        return None
    if not isinstance(agent_result, dict):
        return None
    if not isinstance(progress_snapshot, TransactionSnapshot):
        return None

    try:
        delivery_state = ensure_delivery_state(agent_result)
        snapshot = build_flowweaver_v0_snapshot(
            progress_snapshot,
            source=_safe_source_summary(source),
            delivery_state=delivery_state,
            final_text=final_text,
        )
        capture = _build_flowweaver_shadow_capture(snapshot)
        if capture is None:
            agent_result.pop(FLOWWEAVER_SHADOW_SNAPSHOT_KEY, None)
            agent_result.pop(FLOWWEAVER_SHADOW_CAPTURE_KEY, None)
            return None
        agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY] = snapshot
        agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = capture
        return snapshot
    except Exception:
        agent_result.pop(FLOWWEAVER_SHADOW_SNAPSHOT_KEY, None)
        agent_result.pop(FLOWWEAVER_SHADOW_CAPTURE_KEY, None)
        return None


def get_flowweaver_shadow_capture(agent_result: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the validated in-memory shadow consumer view, or ``None``.

    The consumer seam is intentionally narrow: a future runtime may read the
    capture and a safe snapshot reference only when the sibling capture record
    exactly matches the sanitized snapshot IDs and static side-effect
    boundaries. The full snapshot remains under ``agent_result``; this helper
    deliberately avoids re-exporting delivery ACK payloads.
    """

    try:
        if not isinstance(agent_result, Mapping):
            return None
        snapshot = agent_result.get(FLOWWEAVER_SHADOW_SNAPSHOT_KEY)
        capture = agent_result.get(FLOWWEAVER_SHADOW_CAPTURE_KEY)
        if not isinstance(snapshot, Mapping) or not isinstance(capture, Mapping):
            return None
        expected = _build_flowweaver_shadow_capture(snapshot)
        if expected is None:
            return None
        if dict(capture) != expected:
            return None
        snapshot_ref = _snapshot_ref_from_capture(expected)
        if snapshot_ref is None:
            return None
        return {
            "snapshot_ref": snapshot_ref,
            "capture": capture,
        }
    except Exception:
        return None


def audit_flowweaver_shadow_capture(agent_result: Mapping[str, Any]) -> dict[str, Any]:
    """Return a safe, side-effect-free audit verdict for the shadow consumer seam."""

    try:
        if not isinstance(agent_result, Mapping):
            return _shadow_audit_result(
                verdict=FLOWWEAVER_SHADOW_AUDIT_REJECTED,
                reason="missing_or_invalid_consumer_view",
            )
        snapshot = agent_result.get(FLOWWEAVER_SHADOW_SNAPSHOT_KEY)
        capture = agent_result.get(FLOWWEAVER_SHADOW_CAPTURE_KEY)
        if not isinstance(snapshot, Mapping) or not isinstance(capture, Mapping):
            return _shadow_audit_result(
                verdict=FLOWWEAVER_SHADOW_AUDIT_REJECTED,
                reason="missing_or_invalid_consumer_view",
            )

        if not _shadow_schema_matches(snapshot=snapshot, capture=capture):
            return _shadow_audit_result(
                verdict=FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH,
                reason="schema_mismatch",
            )
        if not _shadow_capture_ids_match(snapshot=snapshot, capture=capture):
            return _shadow_audit_result(
                verdict=FLOWWEAVER_SHADOW_AUDIT_REJECTED,
                reason="missing_or_invalid_consumer_view",
            )

        snapshot_ref = _snapshot_ref_from_capture(capture)
        if snapshot_ref is None:
            return _shadow_audit_result(
                verdict=FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH,
                reason="schema_mismatch",
            )
        checks = _shadow_audit_checks(snapshot=snapshot, capture=capture)
        if not all(checks.values()):
            return _shadow_audit_result(
                verdict=FLOWWEAVER_SHADOW_AUDIT_UNSAFE,
                reason="unsafe_snapshot",
                snapshot_ref=snapshot_ref,
                checks=checks,
            )

        expected = _build_flowweaver_shadow_capture(snapshot)
        if expected is None or dict(capture) != expected:
            return _shadow_audit_result(
                verdict=FLOWWEAVER_SHADOW_AUDIT_REJECTED,
                reason="missing_or_invalid_consumer_view",
            )

        return _shadow_audit_result(
            verdict=FLOWWEAVER_SHADOW_AUDIT_READY,
            reason="ok",
            snapshot_ref=snapshot_ref,
            checks=checks,
        )
    except Exception:
        return _shadow_audit_result(
            verdict=FLOWWEAVER_SHADOW_AUDIT_REJECTED,
            reason="missing_or_invalid_consumer_view",
        )


def _shadow_schema_matches(*, snapshot: Mapping[str, Any], capture: Mapping[str, Any]) -> bool:
    try:
        return (
            snapshot.get("type") == FLOWWEAVER_HANDLE_TYPE
            and snapshot.get("contract_version") == FLOWWEAVER_CONTRACT_VERSION
            and capture.get("type") == FLOWWEAVER_SHADOW_CAPTURE_TYPE
            and capture.get("contract_version") == FLOWWEAVER_CONTRACT_VERSION
        )
    except Exception:
        return False


def _shadow_audit_checks(*, snapshot: Mapping[str, Any], capture: Mapping[str, Any]) -> dict[str, bool]:
    try:
        public_snapshot = snapshot.get("snapshot")
        capture_audit = capture.get("audit")
        lifecycle = capture.get("lifecycle")
        return {
            "consumer_view_valid": True,
            "ids_match": _shadow_capture_ids_match(snapshot=snapshot, capture=capture),
            "contract_version_valid": _shadow_schema_matches(snapshot=snapshot, capture=capture),
            "snapshot_safe_to_render": (
                isinstance(public_snapshot, Mapping)
                and public_snapshot.get("safe_to_render") is True
                and isinstance(capture_audit, Mapping)
                and capture_audit.get("snapshot_safe_to_render") is True
            ),
            "public_schema_unchanged": (
                isinstance(capture_audit, Mapping)
                and capture_audit.get("public_schema_unchanged") is True
            ),
            "source_not_exported": (
                isinstance(capture_audit, Mapping)
                and capture_audit.get("source_exported") is False
            ),
            "side_effects_absent": (
                isinstance(lifecycle, Mapping)
                and lifecycle.get("visible_side_effects") == []
            ),
        }
    except Exception:
        return _default_shadow_audit_checks()


def _shadow_capture_ids_match(*, snapshot: Mapping[str, Any], capture: Mapping[str, Any]) -> bool:
    try:
        return (
            capture.get("transaction_id") == snapshot.get("transaction_id")
            and capture.get("correlation_id") == snapshot.get("correlation_id")
            and capture.get("snapshot_id") == snapshot.get("snapshot_id")
        )
    except Exception:
        return False


def _shadow_audit_result(
    *,
    verdict: str,
    reason: str,
    snapshot_ref: dict[str, str] | None = None,
    checks: dict[str, bool] | None = None,
) -> dict[str, Any]:
    return {
        "type": FLOWWEAVER_SHADOW_AUDIT_TYPE,
        "verdict": verdict,
        "reason": reason,
        "snapshot_ref": snapshot_ref,
        "checks": checks or _default_shadow_audit_checks(),
        "side_effects": [],
    }


def _default_shadow_audit_checks() -> dict[str, bool]:
    return {
        "consumer_view_valid": False,
        "ids_match": False,
        "contract_version_valid": False,
        "snapshot_safe_to_render": False,
        "public_schema_unchanged": False,
        "source_not_exported": False,
        "side_effects_absent": True,
    }


def _snapshot_ref_from_capture(capture: Mapping[str, Any]) -> dict[str, str] | None:
    try:
        transaction_id = str(capture["transaction_id"])
        correlation_id = str(capture["correlation_id"])
        snapshot_id = str(capture["snapshot_id"])
    except Exception:
        return None
    if not _safe_shadow_ref_id(transaction_id, prefix="tx"):
        return None
    if not _safe_shadow_ref_id(correlation_id, prefix="turn"):
        return None
    if not _safe_shadow_ref_id(snapshot_id, prefix="snap"):
        return None
    return {
        "snapshot_key": FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
        "transaction_id": transaction_id,
        "correlation_id": correlation_id,
        "snapshot_id": snapshot_id,
    }


def _safe_shadow_ref_id(value: str, *, prefix: str) -> bool:
    expected_prefix = f"{prefix}_"
    return (
        value.startswith(expected_prefix)
        and _SAFE_SHADOW_REF_RE.fullmatch(value) is not None
        and _UNSAFE_SHADOW_REF_RE.search(value) is None
    )


def _build_flowweaver_shadow_capture(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        if not isinstance(snapshot, Mapping):
            return None
        if snapshot.get("type") != FLOWWEAVER_HANDLE_TYPE:
            return None
        if snapshot.get("contract_version") != FLOWWEAVER_CONTRACT_VERSION:
            return None

        transaction_id = _required_text(snapshot.get("transaction_id"))
        correlation_id = _required_text(snapshot.get("correlation_id"))
        snapshot_id = _required_text(snapshot.get("snapshot_id"))
        created_at = _required_text(snapshot.get("created_at"))
        if not all((transaction_id, correlation_id, snapshot_id, created_at)):
            return None

        public_snapshot = snapshot.get("snapshot")
        snapshot_safe_to_render = (
            isinstance(public_snapshot, Mapping)
            and public_snapshot.get("safe_to_render") is True
        )
        return {
            "type": FLOWWEAVER_SHADOW_CAPTURE_TYPE,
            "contract_version": FLOWWEAVER_CONTRACT_VERSION,
            "snapshot_key": FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
            "transaction_id": transaction_id,
            "correlation_id": correlation_id,
            "snapshot_id": snapshot_id,
            "created_at": created_at,
            "lifecycle": {
                "stage": "gateway_shadow_capture",
                "state": "captured",
                "default_enabled": False,
                "visible_side_effects": [],
            },
            "consumer": {
                "status": "ready",
                "allowed": list(_ALLOWED_CAPTURE_CONSUMERS),
                "forbidden_side_effects": list(_FORBIDDEN_CAPTURE_SIDE_EFFECTS),
            },
            "audit": {
                "snapshot_safe_to_render": snapshot_safe_to_render,
                "public_schema_unchanged": True,
                "source_exported": False,
            },
        }
    except Exception:
        return None


def _required_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _safe_source_summary(source: object | None) -> dict[str, Any] | None:
    """Return only coarse source shape; the v0 adapter still discards it."""

    if source is None:
        return None
    platform = getattr(source, "platform", None)
    platform_value = getattr(platform, "value", platform)
    try:
        platform_text = str(platform_value) if platform_value is not None else None
    except Exception:
        platform_text = None
    return {"platform": platform_text}


__all__ = [
    "FLOWWEAVER_SHADOW_AUDIT_READY",
    "FLOWWEAVER_SHADOW_AUDIT_REJECTED",
    "FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH",
    "FLOWWEAVER_SHADOW_AUDIT_TYPE",
    "FLOWWEAVER_SHADOW_AUDIT_UNSAFE",
    "FLOWWEAVER_SHADOW_CAPTURE_KEY",
    "FLOWWEAVER_SHADOW_CAPTURE_TYPE",
    "FLOWWEAVER_SHADOW_CONFIG_KEY",
    "FLOWWEAVER_SHADOW_SNAPSHOT_KEY",
    "attach_flowweaver_shadow_snapshot",
    "audit_flowweaver_shadow_capture",
    "get_flowweaver_shadow_capture",
    "is_flowweaver_shadow_enabled",
]
