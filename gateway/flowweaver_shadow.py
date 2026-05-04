"""Default-off FlowWeaver shadow tap for Gateway lifecycle tests.

The tap is deliberately inert: it performs no platform I/O, persistence, service
startup, or rendering. It only attaches the Phase-4A sanitized v0 snapshot to the
in-memory ``agent_result`` dict when explicitly enabled by config.
"""

from __future__ import annotations

from collections.abc import Mapping
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
_FORBIDDEN_CAPTURE_SIDE_EFFECTS = ["send", "edit", "render", "persist", "temporal"]
_ALLOWED_CAPTURE_CONSUMERS = ["in_memory_test_probe", "future_flowweaver_runtime"]


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
        return {
            "snapshot_ref": {
                "snapshot_key": FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
                "transaction_id": expected["transaction_id"],
                "correlation_id": expected["correlation_id"],
                "snapshot_id": expected["snapshot_id"],
            },
            "capture": capture,
        }
    except Exception:
        return None


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
    "FLOWWEAVER_SHADOW_CAPTURE_KEY",
    "FLOWWEAVER_SHADOW_CAPTURE_TYPE",
    "FLOWWEAVER_SHADOW_CONFIG_KEY",
    "FLOWWEAVER_SHADOW_SNAPSHOT_KEY",
    "attach_flowweaver_shadow_snapshot",
    "get_flowweaver_shadow_capture",
    "is_flowweaver_shadow_enabled",
]
