"""Pure FlowWeaver runtime identity derivation for Gateway shadow refs."""

from __future__ import annotations

import hashlib
import json

FLOWWEAVER_RUNTIME_IDENTITY_TYPE = "flowweaver.gateway.runtime_identity.v0"
FLOWWEAVER_RUNTIME_IDENTITY_ACCEPTED = "accepted"
FLOWWEAVER_RUNTIME_IDENTITY_REJECTED = "rejected"
FLOWWEAVER_RUNTIME_IDENTITY_STRATEGY = "shadow_ref_hash_v0"

_SNAPSHOT_KEY = "flowweaver_shadow_snapshot"
_EXPECTED_KEYS = {"snapshot_key", "transaction_id", "correlation_id", "snapshot_id"}
_EXPECTED_KEYS_WITH_CREATED_AT = _EXPECTED_KEYS | {"created_at"}
_REQUIRED_PREFIXES = {
    "transaction_id": "tx_",
    "correlation_id": "turn_",
    "snapshot_id": "snap_",
}
_PLATFORM_MARKERS = (
    "om_",
    "oc_",
    "ou_",
    "chat",
    "message",
    "platform",
    "feishu",
    "lark",
    "telegram",
    "private",
)
_SECRET_MARKERS = (
    "token",
    "secret",
    "password",
    "credential",
    "api_key",
    "apikey",
    "bearer",
    "sk-",
)
_INVALID = object()
_UNSAFE = object()


def derive_flowweaver_runtime_identity(snapshot_ref: object) -> dict[str, object]:
    """Return an opaque deterministic runtime identity for a safe shadow ref.

    The helper is intentionally side-effect-free and exports only synthetic IDs.
    Raw ``tx_``/``turn_``/``snap_`` source values are validation input only.
    """

    try:
        safe_ref = _safe_snapshot_ref(snapshot_ref)
        if safe_ref is _INVALID:
            return _rejected(reason="invalid_snapshot_ref")
        if safe_ref is _UNSAFE:
            return _rejected(reason="unsafe_runtime_identity")
        if _contains_unsafe_marker(safe_ref):
            return _rejected(reason="unsafe_runtime_identity")
        digest_source = json.dumps(
            safe_ref,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        suffix = hashlib.sha256(digest_source).hexdigest()[:20]
        transaction_id = f"runtime_tx_shadow_{suffix}"
        idempotency_key = f"runtime_event_start_shadow_{suffix}"
        return {
            "type": FLOWWEAVER_RUNTIME_IDENTITY_TYPE,
            "verdict": FLOWWEAVER_RUNTIME_IDENTITY_ACCEPTED,
            "reason": "ok",
            "strategy": FLOWWEAVER_RUNTIME_IDENTITY_STRATEGY,
            "transaction_id": transaction_id,
            "workflow_id": transaction_id,
            "idempotency_key": idempotency_key,
            "checks": {
                "snapshot_ref_valid": True,
                "ids_synthetic": True,
                "private_markers_absent": True,
                "secret_markers_absent": True,
                "source_values_not_exported": True,
            },
            "side_effects": [],
        }
    except Exception:
        return _rejected(reason="runtime_identity_error")


def _safe_snapshot_ref(value: object) -> dict[str, str] | object:
    if type(value) is not dict:
        return _INVALID
    keys = list(value.keys())
    if not all(type(key) is str for key in keys):
        return _INVALID
    key_set = set(keys)
    if key_set != _EXPECTED_KEYS and key_set != _EXPECTED_KEYS_WITH_CREATED_AT:
        return _INVALID
    result: dict[str, str] = {}
    for key in ("snapshot_key", "transaction_id", "correlation_id", "snapshot_id"):
        item = value[key]
        if type(item) is not str:
            return _INVALID
        if not item or len(item) > 128:
            return _INVALID
        result[key] = item
    if result["snapshot_key"] != _SNAPSHOT_KEY:
        return _INVALID
    for key, prefix in _REQUIRED_PREFIXES.items():
        item = result[key]
        if not item.startswith(prefix):
            return _INVALID
        if _unsafe_marker_for_value(item, prefix=prefix):
            return _UNSAFE
        if not all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in item):
            return _INVALID
        if len(item) <= len(prefix):
            return _INVALID
    if "created_at" in value:
        created_at = value["created_at"]
        if type(created_at) is not str or not _safe_created_at(created_at):
            return _INVALID
        result["created_at"] = created_at
    return result


def _safe_created_at(value: str) -> bool:
    if not value or len(value) > 64:
        return False
    lowered = value.lower()
    if any(marker in lowered for marker in _PLATFORM_MARKERS) or any(marker in lowered for marker in _SECRET_MARKERS):
        return False
    return all(char.isdigit() or char in "tTzZ:+-._" for char in value)


def _unsafe_marker_for_value(value: str, *, prefix: str) -> bool:
    lowered = value.lower()
    body = lowered[len(prefix) :]
    return any(marker in body for marker in _PLATFORM_MARKERS) or any(marker in lowered for marker in _SECRET_MARKERS)


def _contains_unsafe_marker(snapshot_ref: dict[str, str]) -> bool:
    for key, prefix in _REQUIRED_PREFIXES.items():
        if _unsafe_marker_for_value(snapshot_ref[key], prefix=prefix):
            return True
    created_at = snapshot_ref.get("created_at")
    return type(created_at) is str and not _safe_created_at(created_at)


def _rejected(*, reason: str) -> dict[str, object]:
    return {
        "type": FLOWWEAVER_RUNTIME_IDENTITY_TYPE,
        "verdict": FLOWWEAVER_RUNTIME_IDENTITY_REJECTED,
        "reason": reason,
        "strategy": None,
        "transaction_id": None,
        "workflow_id": None,
        "idempotency_key": None,
        "checks": {
            "snapshot_ref_valid": False,
            "ids_synthetic": False,
            "private_markers_absent": True,
            "secret_markers_absent": True,
            "source_values_not_exported": True,
        },
        "side_effects": [],
    }


__all__ = [
    "FLOWWEAVER_RUNTIME_IDENTITY_ACCEPTED",
    "FLOWWEAVER_RUNTIME_IDENTITY_REJECTED",
    "FLOWWEAVER_RUNTIME_IDENTITY_STRATEGY",
    "FLOWWEAVER_RUNTIME_IDENTITY_TYPE",
    "derive_flowweaver_runtime_identity",
]
