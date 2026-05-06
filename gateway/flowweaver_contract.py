"""Pure Gateway progress -> FlowWeaver v0 contract adapter.

This module deliberately has no runtime wiring and performs no platform I/O. It
only translates the existing sanitized Gateway progress/delivery state into the
Phase-3-compatible ``flowweaver.handle.v0`` snapshot shape used by tests and
future seams.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
import hashlib
import math
import re
from typing import Any

from gateway.progress.events import ProgressOperation, TransactionSnapshot
from gateway.progress.redaction import sanitize_for_progress, sanitize_value_for_progress

FLOWWEAVER_CONTRACT_VERSION = "flowweaver.v0"
FLOWWEAVER_HANDLE_TYPE = "flowweaver.handle.v0"
FLOWWEAVER_ADAPTER = "mock"

_INTENT_ID = "task"
_MAX_PROGRESS_ITEMS = 10
_MAX_RENDER_TEXT_CHARS = 1200
_REDACTED = "[REDACTED]"

_STATUS_MAP = {
    "pending": "pending",
    "running": "running",
    "completed": "succeeded",
    "complete": "succeeded",
    "succeeded": "succeeded",
    "success": "succeeded",
    "failed": "failed",
    "failure": "failed",
    "error": "failed",
    "blocked": "blocked",
    "block": "blocked",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "skipped": "skipped",
}

_BEARER_VALUE_RE = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")
_SK_VALUE_RE = re.compile(r"\bsk-[A-Za-z0-9.]{6,}\b", re.IGNORECASE)
_FAKE_SECRET_VALUE_RE = re.compile(
    r"\bfake-[A-Za-z0-9_.-]*(?:token|secret|password)\b",
    re.IGNORECASE,
)
_SECRET_FLAG_VALUE_RE = re.compile(
    r"(?P<lead>--?(?:api[-_]?key|token|secret|password|passwd|authorization)\b(?:[=\s]+))"
    r"(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)
_RISKY_SUMMARY_RE = re.compile(
    r"(?i)(?:\b(?:authorization|bearer|api[-_\s]?key|token|secret|password|passwd|"
    r"raw[-_\s]?(?:args|command|output)|stdout|stderr|feishu[-_\s]?card[-_\s]?json)\b|--[a-z0-9][a-z0-9_-]*)"
)
_FEISHU_MESSAGE_ID_RE = re.compile(r"^om_[a-z0-9_]+$")
_PRIVATE_IDENTIFIER_RE = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:feishu|lark|telegram|discord|slack|whatsapp|wecom|dingtalk|"
    r"chat|user|thread|topic|oc_|ou_|om_|open_id|union_id)"
)
_SENSITIVE_SLUG_FRAGMENT_RE = re.compile(
    r"(?:authorization|apikey|api_key|api_key|token|secret|password|passwd|bearer|"
    r"credential|privatekey|private_key|webhook|raw_args|raw_command|raw_output|stdout|stderr|"
    r"feishu_card_json)",
    re.IGNORECASE,
)


def build_flowweaver_v0_snapshot(
    progress_snapshot: TransactionSnapshot,
    *,
    source: dict[str, Any] | None = None,
    delivery_state: dict[str, Any] | None = None,
    final_text: str | None = None,
) -> dict[str, Any]:
    """Return a sanitized ``flowweaver.handle.v0`` snapshot for Gateway state.

    The adapter is intentionally pure: it performs no sends, edits, persistence,
    service startup, or imports from the FlowWeaver prototype. ``source`` is
    accepted for the future seam but is not copied into the contract document so
    platform credentials or chat identifiers cannot leak.
    """

    del source  # Deliberately not exported in the public contract snapshot.

    base_id = _public_base_id(progress_snapshot.transaction_id)
    transaction_id = _prefixed_id("tx", base_id, fallback="transaction")
    correlation_id = _prefixed_id("turn", base_id, fallback="transaction")
    snapshot_id = _prefixed_id("snap", base_id, fallback="transaction")
    final_text_id = _prefixed_id("final_text", base_id, fallback="transaction")

    status = _status_to_flowweaver(progress_snapshot.status)
    title = _safe_text(progress_snapshot.title, max_len=120) or "Task"
    user_request_summary = _safe_text(progress_snapshot.title, max_len=240) or title

    final_text_record, final_text_delivery = _final_text_record_and_delivery(
        final_text_id=final_text_id,
        final_text=final_text,
        delivery_state=delivery_state,
    )
    artifacts, rich_card_deliveries, rich_card_coverage = _rich_card_records(delivery_state)

    deliveries = [*rich_card_deliveries]
    if final_text_delivery is not None:
        deliveries.append(final_text_delivery)

    coverage = _intent_coverage(
        status=status,
        final_text_delivery=final_text_delivery,
        rich_card_coverage=rich_card_coverage,
    )

    operations = [
        _operation_to_record(operation)
        for operation in progress_snapshot.recent_operations
    ]
    progress = _progress_items(status=status, title=title, operations=operations)
    render_text = _render_text(status=status, title=title, progress=progress)

    return {
        "type": FLOWWEAVER_HANDLE_TYPE,
        "transaction_id": transaction_id,
        "workflow_id": None,
        "run_id": None,
        "correlation_id": correlation_id,
        "snapshot_id": snapshot_id,
        "adapter": FLOWWEAVER_ADAPTER,
        "created_at": _safe_iso_time(progress_snapshot.updated_at),
        "contract_version": FLOWWEAVER_CONTRACT_VERSION,
        "transaction": {
            "transaction_id": transaction_id,
            "status": status,
            "user_request_summary": user_request_summary,
            "intents": [
                {
                    "intent_id": _INTENT_ID,
                    "order_index": 0,
                    "title": title,
                    "status": status,
                    "dependencies": [],
                }
            ],
            "operations": operations,
            "artifacts": artifacts,
            "deliveries": deliveries,
            "intent_coverage": [coverage],
            "final_text": final_text_record,
        },
        "snapshot": {
            "snapshot_id": snapshot_id,
            "transaction_id": transaction_id,
            "status": status,
            "safe_to_render": True,
            "ordered_intent_ids": [_INTENT_ID],
            "progress": progress,
            "render_text": render_text,
            "bounds": {
                "max_progress_items": _MAX_PROGRESS_ITEMS,
                "max_render_text_chars": _MAX_RENDER_TEXT_CHARS,
            },
        },
    }


def _status_to_flowweaver(status: Any, *, is_error: bool = False) -> str:
    if is_error:
        return "failed"
    try:
        normalized = str(status or "").strip().lower()
    except Exception:
        normalized = ""
    return _STATUS_MAP.get(normalized, "pending")


def _operation_to_record(operation: ProgressOperation) -> dict[str, Any]:
    status = _status_to_flowweaver(operation.status, is_error=operation.is_error)
    return {
        "operation_id": _prefixed_id("op", operation.id, fallback="operation"),
        "intent_id": _INTENT_ID,
        "kind": _operation_kind(operation),
        "status": status,
        "attempted_at": _safe_iso_time(operation.started_at or operation.updated_at),
        "summary": _operation_summary(operation, status=status),
    }


def _operation_kind(operation: ProgressOperation) -> str:
    tool = _slugify(operation.tool_name or "tool", fallback="tool", sensitive_fallback="tool")
    event = _slugify(operation.event_type or "event", fallback="event", sensitive_fallback="event")
    kind = f"{tool}_{event}".strip("_")
    if not kind or not kind[0].isalpha():
        kind = f"tool_{kind}" if kind else "tool_event"
    return kind[:120].strip("_") or "tool_event"


def _operation_summary(operation: ProgressOperation, *, status: str) -> str:
    tool_label = _safe_text(operation.tool_name or "tool", max_len=80) or "tool"
    event_label = _safe_text(operation.event_type or "operation", max_len=80) or "operation"
    if _RISKY_SUMMARY_RE.search(tool_label):
        tool_label = "tool"
    if _RISKY_SUMMARY_RE.search(event_label):
        event_label = "operation"
    return _cap(f"{tool_label} {event_label} {status}.", 280)


def _final_text_record_and_delivery(
    *,
    final_text_id: str,
    final_text: str | None,
    delivery_state: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    state = delivery_state if isinstance(delivery_state, Mapping) else {}
    final_state = state.get("final_text")
    final_sent = isinstance(final_state, Mapping) and final_state.get("sent") is True
    final_status = "succeeded" if final_sent else "pending"
    text = _safe_text(final_text or "", max_len=1200)
    record = {
        "final_text_id": final_text_id,
        "status": final_status,
        "text": text,
        "covers_intent_ids": [_INTENT_ID] if final_sent else [],
    }
    if not final_sent:
        return record, None

    delivery_key = f"feishu:om_final_text:final_text:{_INTENT_ID}"
    return record, {
        "delivery_idempotency_key": delivery_key,
        "surface": "final_text",
        "platform": "feishu",
        "status": "sent",
        "message_id": "om_final_text",
        "target": {"kind": "final_text", "id": final_text_id},
        "reason": None,
    }


def _rich_card_records(
    delivery_state: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str] | None]:
    state = delivery_state if isinstance(delivery_state, Mapping) else {}
    artifacts: list[dict[str, Any]] = []
    deliveries: list[dict[str, Any]] = []
    coverage: dict[str, str] | None = None
    seen_artifact_ids: set[str] = set()

    for index, record in enumerate(_iter_rich_cards(state.get("rich_cards_sent")), start=1):
        raw_type = record.get("type")
        raw_message_id = record.get("message_id")
        card_type = _safe_text(raw_type, max_len=120) or f"rich_card_{index}"
        message_id = _safe_message_id(raw_message_id)
        if not message_id:
            continue

        artifact_id = _unique_id(
            _prefixed_id("artifact", card_type, fallback=f"rich_card_{index}"),
            seen_artifact_ids,
        )
        content_summary = _cap(f"Rich card delivered: {card_type}", 360)
        artifact = {
            "artifact_id": artifact_id,
            "intent_id": _INTENT_ID,
            "kind": "rich_card",
            "status": "succeeded",
            "title": _cap(card_type, 120) or "rich_card",
            "content_summary": content_summary or "Rich card delivered.",
            "covers_intent_ids": [_INTENT_ID],
        }
        delivery_key = f"feishu:{message_id}:rich_card:{artifact_id}"
        delivery = {
            "delivery_idempotency_key": delivery_key,
            "surface": "rich_card",
            "platform": "feishu",
            "status": "sent",
            "message_id": message_id,
            "target": {"kind": "artifact", "id": artifact_id},
            "reason": None,
        }
        artifacts.append(artifact)
        deliveries.append(delivery)
        if coverage is None:
            coverage = {
                "artifact_id": artifact_id,
                "delivery_idempotency_key": delivery_key,
            }

    return artifacts, deliveries, coverage


def _intent_coverage(
    *,
    status: str,
    final_text_delivery: dict[str, Any] | None,
    rich_card_coverage: dict[str, str] | None,
) -> dict[str, Any]:
    if final_text_delivery is not None:
        return {
            "intent_id": _INTENT_ID,
            "mode": "answered",
            "artifact_id": None,
            "delivery_idempotency_key": final_text_delivery["delivery_idempotency_key"],
            "reason": None,
        }
    if rich_card_coverage is not None:
        return {
            "intent_id": _INTENT_ID,
            "mode": "delivered_artifact",
            "artifact_id": rich_card_coverage["artifact_id"],
            "delivery_idempotency_key": rich_card_coverage["delivery_idempotency_key"],
            "reason": None,
        }
    if status == "failed":
        mode = "failed"
    elif status == "cancelled":
        mode = "skipped"
    else:
        mode = "blocked_waiting_for_user"
    return {
        "intent_id": _INTENT_ID,
        "mode": mode,
        "artifact_id": None,
        "delivery_idempotency_key": None,
        "reason": None,
    }


def _progress_items(
    *,
    status: str,
    title: str,
    operations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if operations:
        summary = operations[-1]["summary"]
    else:
        summary = title
    return [
        {
            "intent_id": _INTENT_ID,
            "status": status,
            "summary": _cap(summary or title or "Task", 180),
        }
    ][:_MAX_PROGRESS_ITEMS]


def _render_text(*, status: str, title: str, progress: list[dict[str, Any]]) -> str:
    summary = progress[-1]["summary"] if progress else title
    return _safe_text(f"{status}: {summary}", max_len=_MAX_RENDER_TEXT_CHARS) or status


def _iter_rich_cards(value: Any) -> Iterable[Mapping[str, Any]]:
    if not isinstance(value, list):
        return ()
    return (item for item in value if isinstance(item, Mapping))


def _safe_message_id(value: Any) -> str | None:
    if value is None:
        return None
    text = _safe_text(value, max_len=160).strip()
    for separator in ("?", "#", "&", ";"):
        if separator in text:
            text = text.split(separator, 1)[0]
    if not _FEISHU_MESSAGE_ID_RE.fullmatch(text):
        return None
    return text


def _prefixed_id(prefix: str, raw: Any, *, fallback: str) -> str:
    slug = _slugify(raw, fallback=fallback, max_len=96)
    prefix_with_sep = f"{prefix}_"
    if slug == prefix or slug.startswith(prefix_with_sep):
        return slug
    return f"{prefix_with_sep}{slug}"


def _public_base_id(value: Any) -> str:
    text = _safe_text(value, max_len=240)
    if _PRIVATE_IDENTIFIER_RE.search(text):
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
        return f"transaction_{digest}"
    return _slugify(text, fallback="transaction", sensitive_fallback="transaction", max_len=96)


def _unique_id(candidate: str, seen: set[str]) -> str:
    base = candidate
    index = 2
    while candidate in seen:
        candidate = f"{base}_{index}"
        index += 1
    seen.add(candidate)
    return candidate


def _slugify(
    value: Any,
    *,
    fallback: str,
    sensitive_fallback: str | None = None,
    max_len: int = 80,
) -> str:
    text = _safe_text(value, max_len=max_len * 2)
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if _SENSITIVE_SLUG_FRAGMENT_RE.search(slug):
        slug = sensitive_fallback or fallback
    if not slug:
        slug = fallback
    if not slug[0].isalpha():
        slug = f"{fallback}_{slug}"
    return slug[:max_len].strip("_") or fallback


def _safe_text(value: Any, *, max_len: int) -> str:
    rendered = sanitize_value_for_progress(value, max_len=max_len)
    # Re-run the public progress sanitizer for string values so callers benefit
    # from both Gateway redaction entry points before strict contract scrubbing.
    rendered = sanitize_for_progress(rendered, max_len=max_len)
    rendered = _redact_secret_shapes(rendered)
    return _cap(rendered, max_len)


def _redact_secret_shapes(text: str) -> str:
    text = _BEARER_VALUE_RE.sub(r"\1" + _REDACTED, text)
    text = _SECRET_FLAG_VALUE_RE.sub(lambda match: f"{match.group('lead')}{_REDACTED}", text)
    text = _SK_VALUE_RE.sub(_REDACTED, text)
    return _FAKE_SECRET_VALUE_RE.sub(_REDACTED, text)


def _cap(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len == 1:
        return "…"
    return text[: max_len - 1] + "…"


def _safe_iso_time(value: Any) -> str:
    try:
        timestamp = float(value)
    except Exception:
        timestamp = 0.0
    if not math.isfinite(timestamp) or timestamp < 0:
        timestamp = 0.0
    return datetime.fromtimestamp(timestamp, UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


__all__ = [
    "FLOWWEAVER_ADAPTER",
    "FLOWWEAVER_CONTRACT_VERSION",
    "FLOWWEAVER_HANDLE_TYPE",
    "build_flowweaver_v0_snapshot",
]
