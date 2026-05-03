"""Low-intrusion delivery-state helpers for gateway agent results."""

from __future__ import annotations

from typing import Any

from gateway.progress.redaction import sanitize_for_progress, sanitize_value_for_progress


def ensure_delivery_state(agent_result: dict) -> dict:
    """Create or normalize ``agent_result['delivery_state']`` in place."""

    existing_state = agent_result.get("delivery_state")
    if not isinstance(existing_state, dict):
        existing_state = {}

    final_text = existing_state.get("final_text")
    if not isinstance(final_text, dict):
        final_text = {}

    final_text_sent = final_text.get("sent") is True
    final_text_reason = _sanitize_optional(final_text.get("reason"))
    if agent_result.get("already_sent") is True:
        normalized_final_text = {
            "sent": True,
            "reason": final_text_reason if final_text_sent and final_text_reason else "legacy_already_sent",
        }
    else:
        normalized_final_text = {
            "sent": final_text_sent,
            "reason": final_text_reason,
        }

    state = {
        "final_text": normalized_final_text,
        "rich_cards_sent": _normalize_rich_card_records(
            existing_state.get("rich_cards_sent")
        ),
        "media_sent": _normalize_media_records(existing_state.get("media_sent")),
    }
    agent_result["delivery_state"] = state
    return state


def record_rich_card_sent(
    agent_result: dict,
    *,
    result_type: str,
    message_id: str | None,
) -> dict:
    """Record a rich-card delivery without marking final text as sent."""

    state = ensure_delivery_state(agent_result)
    record = {
        "type": sanitize_for_progress(result_type),
        "message_id": _sanitize_optional(message_id),
    }

    records: list[dict[str, str | None]] = []
    for candidate in state.get("rich_cards_sent", []):
        _append_unique_record(records, candidate)
    legacy_records = agent_result.get("rich_cards_sent")
    if isinstance(legacy_records, list):
        for candidate in legacy_records:
            _append_unique_record(records, candidate)
    _append_unique_record(records, record)

    state["rich_cards_sent"] = records
    agent_result["rich_cards_sent"] = records
    return record


def mark_final_text_sent(agent_result: dict, *, reason: str) -> None:
    """Mark final text as delivered and update the legacy compatibility flag."""

    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("mark_final_text_sent requires a nonblank reason")

    state = ensure_delivery_state(agent_result)
    state["final_text"] = {
        "sent": True,
        "reason": sanitize_for_progress(reason.strip()),
    }
    agent_result["already_sent"] = True


def should_skip_final_text(agent_result: dict) -> bool:
    """Return True only when final text delivery is explicitly marked sent."""

    state = ensure_delivery_state(agent_result)
    final_text = state.get("final_text")
    return isinstance(final_text, dict) and final_text.get("sent") is True


def _sanitize_optional(value: Any) -> str | None:
    if value is None:
        return None
    return sanitize_for_progress(value)


def _normalize_media_records(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [_sanitize_structured_value(item, seen=set()) for item in value]


def _sanitize_structured_value(
    value: Any,
    *,
    key: Any = None,
    seen: set[int] | None = None,
) -> Any:
    seen = seen if seen is not None else set()
    if key is not None:
        keyed_rendered = sanitize_value_for_progress(value, key=key, max_len=240)
        if keyed_rendered == "[REDACTED]":
            return keyed_rendered
    if isinstance(value, dict):
        value_id = id(value)
        if value_id in seen:
            return "<cycle>"
        seen.add(value_id)
        try:
            return {
                _safe_state_key(item_key): _sanitize_structured_value(
                    item_value,
                    key=item_key,
                    seen=seen,
                )
                for item_key, item_value in value.items()
            }
        finally:
            seen.discard(value_id)
    if isinstance(value, (list, tuple, set, frozenset)):
        value_id = id(value)
        if value_id in seen:
            return "<cycle>"
        seen.add(value_id)
        try:
            return [_sanitize_structured_value(item, seen=seen) for item in value]
        finally:
            seen.discard(value_id)
    if value is None or type(value) in (bool, int, float):
        return value
    return sanitize_value_for_progress(value, key=key, max_len=240)


def _safe_state_key(key: Any) -> str:
    try:
        raw_key = str(key)
    except Exception:
        return "<unprintable-key>"
    return sanitize_for_progress(raw_key, max_len=80)


def _normalize_rich_card_records(value: Any) -> list[dict[str, str | None]]:
    records: list[dict[str, str | None]] = []
    if not isinstance(value, list):
        return records

    for candidate in value:
        _append_unique_record(records, candidate)
    return records


def _append_unique_record(records: list[dict[str, str | None]], candidate: Any) -> None:
    record = _normalize_rich_card_record(candidate)
    if record is not None and record not in records:
        records.append(record)


def _normalize_rich_card_record(candidate: Any) -> dict[str, str | None] | None:
    if not isinstance(candidate, dict):
        return None
    return {
        "type": _sanitize_optional(candidate.get("type")),
        "message_id": _sanitize_optional(candidate.get("message_id")),
    }
