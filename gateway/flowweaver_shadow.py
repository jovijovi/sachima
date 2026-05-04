"""Default-off FlowWeaver shadow tap for Gateway lifecycle tests.

The tap is deliberately inert: it performs no platform I/O, persistence, service
startup, or rendering. It only attaches the Phase-4A sanitized v0 snapshot to the
in-memory ``agent_result`` dict when explicitly enabled by config.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
FLOWWEAVER_SHADOW_REPLAY_TYPE = "flowweaver.gateway.shadow_replay_probe.v0"
FLOWWEAVER_SHADOW_AUDIT_READY = "ready"
FLOWWEAVER_SHADOW_AUDIT_REJECTED = "rejected"
FLOWWEAVER_SHADOW_AUDIT_UNSAFE = "unsafe"
FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH = "schema_mismatch"
FLOWWEAVER_SHADOW_REPLAY_REPLAYED = "replayed"
FLOWWEAVER_SHADOW_REPLAY_REJECTED = "rejected"
FLOWWEAVER_SHADOW_REPLAY_UNSAFE = "unsafe"
FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH = "schema_mismatch"
FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED = "drift_detected"
FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE = "flowweaver.gateway.shadow_consumer_contract.v0"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE = "flowweaver.gateway.shadow_replay_corpus.v0"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED = "passed"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED = "failed"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED = "rejected"
_FORBIDDEN_CAPTURE_SIDE_EFFECTS = ["send", "edit", "render", "persist", "temporal"]
_ALLOWED_CAPTURE_CONSUMERS = ["in_memory_test_probe", "future_flowweaver_runtime"]
_SAFE_SHADOW_REF_RE = re.compile(r"^(?:tx|turn|snap)_[a-z0-9][a-z0-9_]{0,127}$")
_OPAQUE_PLATFORM_REF_RE = re.compile(
    r"^(?:tx|turn|snap)_(?:[ucgd][0-9][a-z0-9]{4,}|transaction_[0-9]{12,}|[0-9]{12,})$"
)
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


def describe_flowweaver_shadow_consumer_contract() -> dict[str, Any]:
    """Return the static safe contract for shadow consumers.

    The descriptor is intentionally metadata-only: it does not read live
    Gateway state, does not expose sample payloads, and does not authorize any
    side effects. It gives future consumers a narrow contract to satisfy before
    durable orchestration is considered.
    """

    return {
        "type": FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE,
        "contract_version": FLOWWEAVER_CONTRACT_VERSION,
        "snapshot_key": FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
        "capture_key": FLOWWEAVER_SHADOW_CAPTURE_KEY,
        "capture_type": FLOWWEAVER_SHADOW_CAPTURE_TYPE,
        "audit_type": FLOWWEAVER_SHADOW_AUDIT_TYPE,
        "replay_type": FLOWWEAVER_SHADOW_REPLAY_TYPE,
        "allowed_consumer_inputs": ["agent_result_mapping"],
        "allowed_consumers": list(_ALLOWED_CAPTURE_CONSUMERS),
        "replay_verdicts": [
            FLOWWEAVER_SHADOW_REPLAY_REPLAYED,
            FLOWWEAVER_SHADOW_REPLAY_REJECTED,
            FLOWWEAVER_SHADOW_REPLAY_UNSAFE,
            FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH,
            FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED,
        ],
        "forbidden_output_fields": [
            "snapshot",
            "capture",
            "transaction",
            "deliveries",
            "artifacts",
            "source",
            "raw_command",
            "raw_output",
            "stdout",
            "stderr",
            "card_json",
            "platform",
            "chat_id",
            "user_id",
            "message_id",
            "delivery_ack",
        ],
        "forbidden_side_effects": [
            "send",
            "edit",
            "render",
            "persist",
            "temporal",
            "log",
        ],
        "bounds": {
            "default_replay_attempts": 2,
            "max_replay_attempts": 5,
            "max_corpus_entries": 20,
        },
        "side_effects": [],
    }


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


def replay_flowweaver_shadow_capture(
    agent_result: Mapping[str, Any],
    *,
    attempts: int = 2,
) -> dict[str, Any]:
    """Repeatedly read the shadow consumer seam through safe audit projections."""

    try:
        if not isinstance(agent_result, Mapping) or not _valid_replay_attempts(attempts):
            return _shadow_replay_result(
                verdict=FLOWWEAVER_SHADOW_REPLAY_REJECTED,
                reason="missing_or_invalid_consumer_view",
            )

        projections: list[dict[str, Any]] = []
        for _ in range(attempts):
            audit = audit_flowweaver_shadow_capture(agent_result)
            projection = _shadow_replay_audit_projection(audit)
            audit_verdict = projection["verdict"]
            if audit_verdict == FLOWWEAVER_SHADOW_AUDIT_REJECTED:
                return _shadow_replay_result(
                    verdict=FLOWWEAVER_SHADOW_REPLAY_REJECTED,
                    reason="missing_or_invalid_consumer_view",
                )
            if audit_verdict == FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH:
                return _shadow_replay_result(
                    verdict=FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH,
                    reason="schema_mismatch",
                )
            if audit_verdict == FLOWWEAVER_SHADOW_AUDIT_UNSAFE:
                return _shadow_replay_result(
                    verdict=FLOWWEAVER_SHADOW_REPLAY_UNSAFE,
                    reason="unsafe_snapshot",
                    snapshot_ref=projection["snapshot_ref"],
                    replay_count=len(projections) + 1,
                    checks=_shadow_replay_checks_from_audit(
                        projection,
                        snapshot_ref_stable=True,
                        audit_stable=True,
                    ),
                )
            if audit_verdict != FLOWWEAVER_SHADOW_AUDIT_READY:
                return _shadow_replay_result(
                    verdict=FLOWWEAVER_SHADOW_REPLAY_REJECTED,
                    reason="missing_or_invalid_consumer_view",
                )
            projections.append(projection)

        first = projections[0]
        snapshot_ref_stable = all(
            projection["snapshot_ref"] == first["snapshot_ref"]
            for projection in projections
        )
        audit_stable = all(projection == first for projection in projections)
        if not snapshot_ref_stable or not audit_stable:
            return _shadow_replay_result(
                verdict=FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED,
                reason="drift_detected",
                replay_count=len(projections),
                checks=_shadow_replay_checks_from_audit(
                    first,
                    snapshot_ref_stable=snapshot_ref_stable,
                    audit_stable=audit_stable,
                ),
            )

        return _shadow_replay_result(
            verdict=FLOWWEAVER_SHADOW_REPLAY_REPLAYED,
            reason="ok",
            snapshot_ref=first["snapshot_ref"],
            replay_count=len(projections),
            checks=_shadow_replay_checks_from_audit(
                first,
                snapshot_ref_stable=True,
                audit_stable=True,
            ),
        )
    except Exception:
        return _shadow_replay_result(
            verdict=FLOWWEAVER_SHADOW_REPLAY_REJECTED,
            reason="missing_or_invalid_consumer_view",
        )


def replay_flowweaver_shadow_corpus(
    agent_results: Sequence[Mapping[str, Any]],
    *,
    attempts: int = 2,
) -> dict[str, Any]:
    """Replay a bounded in-memory corpus through the safe replay projection."""

    try:
        if not _valid_replay_corpus(agent_results, attempts=attempts):
            return _shadow_replay_corpus_result(
                verdict=FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED,
                reason="invalid_corpus",
            )

        entries: list[dict[str, Any]] = []
        failed = False
        for index, agent_result in enumerate(agent_results):
            replay = replay_flowweaver_shadow_capture(agent_result, attempts=attempts)
            entry = _shadow_replay_corpus_entry(index=index, replay=replay)
            entries.append(entry)
            if entry["verdict"] != FLOWWEAVER_SHADOW_REPLAY_REPLAYED:
                failed = True

        if failed:
            return _shadow_replay_corpus_result(
                verdict=FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED,
                reason="entry_failed",
                entries=entries,
            )
        return _shadow_replay_corpus_result(
            verdict=FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED,
            reason="ok",
            entries=entries,
        )
    except Exception:
        return _shadow_replay_corpus_result(
            verdict=FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED,
            reason="invalid_corpus",
        )


def _valid_replay_attempts(attempts: int) -> bool:
    return isinstance(attempts, int) and not isinstance(attempts, bool) and 1 <= attempts <= 5


def _valid_replay_corpus(agent_results: object, *, attempts: int) -> bool:
    try:
        return (
            _valid_replay_attempts(attempts)
            and isinstance(agent_results, Sequence)
            and not isinstance(agent_results, (str, bytes, bytearray))
            and 1 <= len(agent_results) <= 20
            and all(isinstance(agent_result, Mapping) for agent_result in agent_results)
        )
    except Exception:
        return False


def _shadow_replay_corpus_entry(*, index: int, replay: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "index": index,
        "verdict": _safe_replay_verdict(replay.get("verdict")),
        "reason": _safe_replay_reason(replay.get("reason")),
        "checks": _safe_replay_checks(replay.get("checks")),
        "side_effects": [],
    }


def _safe_replay_verdict(value: object) -> str:
    if value in {
        FLOWWEAVER_SHADOW_REPLAY_REPLAYED,
        FLOWWEAVER_SHADOW_REPLAY_REJECTED,
        FLOWWEAVER_SHADOW_REPLAY_UNSAFE,
        FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH,
        FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED,
    }:
        return str(value)
    return FLOWWEAVER_SHADOW_REPLAY_REJECTED


def _safe_replay_reason(value: object) -> str:
    if value in {
        "ok",
        "missing_or_invalid_consumer_view",
        "unsafe_snapshot",
        "schema_mismatch",
        "drift_detected",
    }:
        return str(value)
    return "missing_or_invalid_consumer_view"


def _safe_replay_checks(value: object) -> dict[str, bool]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "audit_ready": source.get("audit_ready") is True,
        "consumer_view_valid": source.get("consumer_view_valid") is True,
        "snapshot_ref_stable": source.get("snapshot_ref_stable") is True,
        "audit_stable": source.get("audit_stable") is True,
        "input_not_mutated": source.get("input_not_mutated") is True,
        "side_effects_absent": source.get("side_effects_absent") is True,
    }


def _shadow_replay_corpus_result(
    *,
    verdict: str,
    reason: str,
    entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    safe_entries = entries or []
    return {
        "type": FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE,
        "verdict": verdict,
        "reason": reason,
        "entry_count": len(safe_entries),
        "entries": safe_entries,
        "side_effects": [],
    }


def _shadow_replay_audit_projection(audit: Mapping[str, Any]) -> dict[str, Any]:
    checks = audit.get("checks") if isinstance(audit.get("checks"), Mapping) else {}
    side_effects = audit.get("side_effects")
    return {
        "verdict": audit.get("verdict"),
        "reason": audit.get("reason"),
        "snapshot_ref": audit.get("snapshot_ref") if isinstance(audit.get("snapshot_ref"), Mapping) else None,
        "checks": {key: bool(value) for key, value in dict(checks).items()},
        "side_effects_absent": side_effects == [],
    }


def _shadow_replay_checks_from_audit(
    audit_projection: Mapping[str, Any],
    *,
    snapshot_ref_stable: bool,
    audit_stable: bool,
) -> dict[str, bool]:
    checks = audit_projection.get("checks") if isinstance(audit_projection.get("checks"), Mapping) else {}
    return {
        "audit_ready": audit_projection.get("verdict") == FLOWWEAVER_SHADOW_AUDIT_READY,
        "consumer_view_valid": checks.get("consumer_view_valid") is True,
        "snapshot_ref_stable": snapshot_ref_stable,
        "audit_stable": audit_stable,
        "input_not_mutated": True,
        "side_effects_absent": (
            checks.get("side_effects_absent") is True
            and audit_projection.get("side_effects_absent") is True
        ),
    }


def _shadow_replay_result(
    *,
    verdict: str,
    reason: str,
    snapshot_ref: dict[str, str] | None = None,
    replay_count: int = 0,
    checks: dict[str, bool] | None = None,
) -> dict[str, Any]:
    return {
        "type": FLOWWEAVER_SHADOW_REPLAY_TYPE,
        "verdict": verdict,
        "reason": reason,
        "snapshot_ref": snapshot_ref,
        "replay_count": replay_count,
        "checks": checks or _default_shadow_replay_checks(),
        "side_effects": [],
    }


def _default_shadow_replay_checks() -> dict[str, bool]:
    return {
        "audit_ready": False,
        "consumer_view_valid": False,
        "snapshot_ref_stable": False,
        "audit_stable": False,
        "input_not_mutated": True,
        "side_effects_absent": True,
    }


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
        and _OPAQUE_PLATFORM_REF_RE.fullmatch(value) is None
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
    "FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE",
    "FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED",
    "FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED",
    "FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED",
    "FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE",
    "FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED",
    "FLOWWEAVER_SHADOW_REPLAY_REJECTED",
    "FLOWWEAVER_SHADOW_REPLAY_REPLAYED",
    "FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH",
    "FLOWWEAVER_SHADOW_REPLAY_TYPE",
    "FLOWWEAVER_SHADOW_REPLAY_UNSAFE",
    "FLOWWEAVER_SHADOW_SNAPSHOT_KEY",
    "attach_flowweaver_shadow_snapshot",
    "audit_flowweaver_shadow_capture",
    "describe_flowweaver_shadow_consumer_contract",
    "get_flowweaver_shadow_capture",
    "is_flowweaver_shadow_enabled",
    "replay_flowweaver_shadow_capture",
    "replay_flowweaver_shadow_corpus",
]
