"""Small platform-neutral rich result envelopes for gateway delivery."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import Any, Iterable

from gateway.config import Platform
from gateway.platforms.base import SendResult
from gateway.progress.redaction import REDACTION_TEXT, sanitize_for_progress

RICH_RESULT_BEGIN = "HERMES_RICH_RESULT_JSON_BEGIN"
RICH_RESULT_END = "HERMES_RICH_RESULT_JSON_END"
_MAX_BLOCK_CHARS = 8 * 1024
_MARKER_RE = re.compile(
    re.escape(RICH_RESULT_BEGIN) + r"\s*(?P<json>.*?)\s*" + re.escape(RICH_RESULT_END),
    re.DOTALL,
)
_URL_RE = re.compile(r"https?://[^\s)\]>]+", re.IGNORECASE)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]{0,160})\]\([^)]*\)")
_AUTH_PREFIX_RE = re.compile(r"(?i)\bauthorization\s*:\s*(?:bearer|basic|token)?\s*\[REDACTED\]\s*")
_SENSITIVE_WORD_RE = re.compile(r"(?i)\b(api[-_]?key|token|secret|password|passwd|authorization|bearer|credential)\b")
_WEATHER_HELPER_PATH = "/home/ubuntu/workspace/hermes/skills/productivity/weather-query/scripts/weather_query.py"
_SHELL_OPERATOR_RE = re.compile(r"[;&|<>`$#]|[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class RichResult:
    type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class RichResultDelivery:
    response_text: str
    card_sent: bool = False
    message_id: str | None = None
    error: str | None = None


def extract_rich_results_from_text(text: str | None) -> list[RichResult]:
    if not text:
        return []
    results: list[RichResult] = []
    for match in _MARKER_RE.finditer(str(text)):
        block = match.group("json") or ""
        if len(block) > _MAX_BLOCK_CHARS:
            continue
        try:
            raw = json.loads(block)
        except Exception:
            continue
        result = _validate_rich_result(raw)
        if result is not None:
            results.append(result)
    return results


def extract_rich_results_from_messages(messages: Iterable[dict[str, Any]] | None) -> list[RichResult]:
    message_list = [msg for msg in (messages or []) if isinstance(msg, dict)]
    trusted_tool_call_ids = _trusted_weather_tool_call_ids(message_list)
    results: list[RichResult] = []
    for msg in message_list:
        role = str(msg.get("role") or "").lower()
        if role != "tool":
            continue
        tool_call_id = str(msg.get("tool_call_id") or "")
        if tool_call_id not in trusted_tool_call_ids:
            continue
        content = msg.get("content")
        if isinstance(content, str):
            results.extend(_extract_rich_results_from_tool_content(content))
    return results


def _extract_rich_results_from_tool_content(content: str) -> list[RichResult]:
    """Extract rich results from direct tool text and common JSON wrappers.

    Hermes terminal tool results are persisted as JSON strings such as
    ``{"output": "...HERMES_RICH_RESULT_JSON_BEGIN..."}``.  Scan the direct
    content first for older/plain tools, then decode the wrapper and scan stdout
    style text fields.
    """

    results = extract_rich_results_from_text(content)
    wrapped = _parse_json_object_prefix(content)
    if not isinstance(wrapped, dict):
        return results
    for key in ("output", "stdout", "result", "content", "text", "message"):
        value = wrapped.get(key)
        if isinstance(value, str) and RICH_RESULT_BEGIN in value:
            results.extend(extract_rich_results_from_text(value))
    return results


def _parse_json_object_prefix(content: str) -> dict[str, Any] | None:
    """Parse a JSON object wrapper, tolerating non-JSON text appended after it."""

    try:
        wrapped = json.loads(content)
    except Exception:
        try:
            wrapped, _ = json.JSONDecoder().raw_decode(content)
        except Exception:
            return None
    return wrapped if isinstance(wrapped, dict) else None


def _trusted_weather_tool_call_ids(messages: list[dict[str, Any]]) -> set[str]:
    trusted: set[str] = set()
    for msg in messages:
        if str(msg.get("role") or "").lower() != "assistant":
            continue
        for call in msg.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            call_id = str(call.get("id") or "")
            if not call_id:
                continue
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(fn.get("name") or call.get("name") or "").strip().lower()
            if name == "weather_query":
                trusted.add(call_id)
                continue
            if name != "terminal":
                continue
            args = _parse_tool_arguments(fn.get("arguments") if "arguments" in fn else call.get("arguments"))
            if _is_direct_weather_helper_command(args.get("command")):
                trusted.add(call_id)
    return trusted


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _is_direct_weather_helper_command(command: Any) -> bool:
    if not isinstance(command, str) or not command.strip():
        return False
    if _SHELL_OPERATOR_RE.search(command):
        return False
    try:
        parts = shlex.split(command)
    except Exception:
        return False
    if len(parts) < 2:
        return False
    if parts[0] not in {"python", "python3"}:
        return False
    if parts[1] != _WEATHER_HELPER_PATH:
        return False
    return True


def _clipped_marker_block_index(text: str) -> int:
    """Index of a BEGIN sentinel that opens a clipped marker block, or -1.

    A real marker block is the sentinel followed by a JSON object, so a bare
    BEGIN only signals a clipped block when a ``{`` (or nothing at all)
    follows it. A final answer may instead *mention* the sentinel name in
    prose — e.g. a diagnostic reply quoting `HERMES_RICH_RESULT_JSON_BEGIN`
    in backticks — and truncating there silently drops the rest of the
    answer (live Feishu incident: 1615 chars cut to the 511-char prefix).
    """
    search_from = 0
    while True:
        idx = text.find(RICH_RESULT_BEGIN, search_from)
        if idx < 0:
            return -1
        tail = text[idx + len(RICH_RESULT_BEGIN):]
        if not tail.strip() or tail.lstrip().startswith("{"):
            return idx
        search_from = idx + 1


def strip_rich_result_blocks(text: str | None) -> str:
    if not text:
        return ""
    stripped = _MARKER_RE.sub("", str(text))
    # If a marker block was clipped before its END sentinel, drop everything
    # from BEGIN onward. Better to lose a little fallback prose than expose
    # raw JSON or URLs to a chat surface. Prose mentions of the sentinel name
    # are kept — see _clipped_marker_block_index.
    begin_idx = _clipped_marker_block_index(stripped)
    if begin_idx >= 0:
        stripped = stripped[:begin_idx]
    stripped = re.sub(r"\n?" + re.escape(RICH_RESULT_END) + r"\n?", "\n", stripped)
    return "\n".join(line.rstrip() for line in stripped.splitlines()).strip()


async def maybe_deliver_weather_result(
    *,
    adapter: Any,
    platform: Platform | str | None,
    chat_id: str,
    response_text: str,
    messages: Iterable[dict[str, Any]] | None,
    mode: str = "auto",
    metadata: dict[str, Any] | None = None,
    reply_to: str | None = None,
) -> RichResultDelivery:
    """Deliver the latest weather rich result as a Feishu card when supported.

    The normal text remains the fallback. Marker blocks are never exposed.
    """

    cleaned_response = strip_rich_result_blocks(response_text)
    mode = (mode or "auto").strip().lower()
    if mode == "off":
        return RichResultDelivery(response_text=cleaned_response)

    results = extract_rich_results_from_messages(messages)
    weather = next((result.payload for result in reversed(results) if result.type == "weather.v1"), None)
    if weather is None:
        return RichResultDelivery(response_text=cleaned_response)

    from gateway.renderers.weather import format_weather_markdown, render_feishu_weather_card

    fallback_text = format_weather_markdown(weather)
    platform_value = platform.value if isinstance(platform, Platform) else str(platform or "")
    wants_card = mode == "card" or (mode == "auto" and platform_value == Platform.FEISHU.value)
    if wants_card and platform_value == Platform.FEISHU.value and hasattr(adapter, "send_interactive_card"):
        card = render_feishu_weather_card(weather)
        try:
            result = await adapter.send_interactive_card(
                chat_id,
                card,
                reply_to=reply_to,
                metadata=metadata,
            )
        except Exception as exc:
            result = SendResult(success=False, error=str(exc))
        if getattr(result, "success", False):
            return RichResultDelivery(
                response_text=cleaned_response or fallback_text,
                card_sent=True,
                message_id=getattr(result, "message_id", None),
            )
        return RichResultDelivery(
            response_text=fallback_text,
            card_sent=False,
            error=getattr(result, "error", None),
        )

    return RichResultDelivery(response_text=cleaned_response or fallback_text)


def _validate_rich_result(raw: Any) -> RichResult | None:
    if not isinstance(raw, dict):
        return None
    result_type = raw.get("type")
    if result_type != "weather.v1":
        return None
    payload = _sanitize_weather_report(raw)
    if not payload:
        return None
    payload["type"] = "weather.v1"
    return RichResult(type="weather.v1", payload=payload)


def _sanitize_weather_report(raw: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    location = raw.get("location") if isinstance(raw.get("location"), dict) else {}
    location_payload: dict[str, Any] = {}
    for key in ("label", "country", "timezone"):
        value = _clean_text(location.get(key), max_len=80)
        if value:
            location_payload[key] = value
    if location_payload:
        payload["location"] = location_payload

    for key in ("period", "generated_at", "summary"):
        value = _clean_text(raw.get(key), max_len=220 if key == "summary" else 80)
        if value:
            payload[key] = value

    for key in ("temperature", "precipitation", "wind"):
        if isinstance(raw.get(key), dict):
            nested = _numbers_dict(raw[key], max_items=8)
            if nested:
                payload[key] = nested

    humidity = _number(raw.get("humidity_pct"))
    if humidity is not None:
        payload["humidity_pct"] = humidity

    highlights = []
    for item in raw.get("hourly_highlights") or []:
        if not isinstance(item, dict):
            continue
        row: dict[str, Any] = {}
        for key in ("time", "condition"):
            value = _clean_text(item.get(key), max_len=80)
            if value:
                row[key] = value
        for key in ("temp_c", "precip_probability_pct"):
            number = _number(item.get(key))
            if number is not None:
                row[key] = number
        if row:
            highlights.append(row)
        if len(highlights) >= 6:
            break
    if highlights:
        payload["hourly_highlights"] = highlights

    advice = []
    for item in raw.get("advice") or []:
        value = _clean_text(item, max_len=100)
        if value and REDACTION_TEXT not in value and not _SENSITIVE_WORD_RE.search(value):
            advice.append(value)
        if len(advice) >= 3:
            break
    if advice:
        payload["advice"] = advice

    return payload


def _numbers_dict(raw: dict[str, Any], *, max_items: int) -> dict[str, float | int]:
    result: dict[str, float | int] = {}
    for key, value in raw.items():
        if len(result) >= max_items:
            break
        if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_]{1,40}", key):
            continue
        number = _number(value)
        if number is not None:
            result[key] = number
    return result


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    return None


def _clean_text(value: Any, *, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    text = sanitize_for_progress(value, max_len=max_len)
    text = _MARKDOWN_LINK_RE.sub(lambda m: m.group(1), text)
    text = _AUTH_PREFIX_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = re.sub(r"[<>]", "", text)
    text = text.replace("@all", "all").replace("@here", "here")
    return " ".join(text.split()).strip()
