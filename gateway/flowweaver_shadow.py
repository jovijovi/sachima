"""Default-off FlowWeaver shadow tap for Gateway lifecycle tests.

The tap is deliberately inert: it performs no platform I/O, persistence, service
startup, or rendering. It only attaches the Phase-4A sanitized v0 snapshot to the
in-memory ``agent_result`` dict when explicitly enabled by config.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gateway.delivery_state import ensure_delivery_state
from gateway.flowweaver_contract import build_flowweaver_v0_snapshot
from gateway.progress.events import TransactionSnapshot
from utils import is_truthy_value

FLOWWEAVER_SHADOW_CONFIG_KEY = "flowweaver_shadow"
FLOWWEAVER_SHADOW_SNAPSHOT_KEY = "flowweaver_shadow_snapshot"


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
        agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY] = snapshot
        return snapshot
    except Exception:
        agent_result.pop(FLOWWEAVER_SHADOW_SNAPSHOT_KEY, None)
        return None


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
    "FLOWWEAVER_SHADOW_CONFIG_KEY",
    "FLOWWEAVER_SHADOW_SNAPSHOT_KEY",
    "attach_flowweaver_shadow_snapshot",
    "is_flowweaver_shadow_enabled",
]
