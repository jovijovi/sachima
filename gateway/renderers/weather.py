"""Weather rich-result renderers for gateway platforms."""

from __future__ import annotations

import re
from typing import Any

from gateway.progress.redaction import REDACTION_TEXT, sanitize_for_progress

_SENSITIVE_WORD_RE = re.compile(r"(?i)\b(api[-_]?key|token|secret|password|passwd|authorization|bearer|credential)\b")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]{0,160})\]\([^)]*\)")
_URL_RE = re.compile(r"https?://[^\s)\]>]+", re.IGNORECASE)

_PERIOD_ZH = {
    "now": "现在天气",
    "today": "今天天气",
    "tonight": "今晚天气",
    "tomorrow": "明天天气",
}


def render_feishu_weather_card(report: dict[str, Any]) -> dict[str, Any]:
    label = _location_label(report)
    period_text = _period_text(report.get("period"))
    summary = _safe_text(report.get("summary"), 220)
    temp = _temperature_text(report.get("temperature"))
    rain = _rain_text(report.get("precipitation"))
    wind = _wind_text(report.get("wind"), report.get("humidity_pct"))
    highlights = _highlight_lines(report.get("hourly_highlights"))
    advice = _advice_text(report.get("advice"))

    lines = []
    if summary:
        lines.append(f"**概况：** {summary}")
    if temp:
        lines.append(f"🌡️ **温度：** {temp}")
    if rain:
        lines.append(f"🌧️ **降雨：** {rain}")
    if wind:
        lines.append(f"💨 **环境：** {wind}")
    if highlights:
        lines.append("🕒 **分时：**\n" + "\n".join(f"- {line}" for line in highlights))
    if advice:
        lines.append(f"🎒 **建议：** {advice}")

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": _template_for_weather(report),
            "title": {"tag": "plain_text", "content": f"🌦️ {label}{period_text}"},
        },
        "elements": [{"tag": "markdown", "content": "\n\n".join(lines) or "天气数据暂时不完整。"}],
    }


def format_weather_markdown(report: dict[str, Any]) -> str:
    label = _location_label(report)
    period_text = _period_text(report.get("period"))
    summary = _safe_text(report.get("summary"), 220)
    temp = _temperature_text(report.get("temperature"))
    rain = _rain_text(report.get("precipitation"))
    highlights = _highlight_lines(report.get("hourly_highlights"))
    advice = _advice_text(report.get("advice"))

    lines = [f"🌦️ **{label}{period_text}**"]
    if summary:
        lines.append(f"- 概况：{summary}")
    if temp:
        lines.append(f"- 温度：{temp}")
    if rain:
        lines.append(f"- 降雨：{rain}")
    if highlights:
        lines.append("- 分时：" + "；".join(highlights[:3]))
    if advice:
        lines.append(f"- 建议：{advice}")
    return "\n".join(lines)


def _location_label(report: dict[str, Any]) -> str:
    location = report.get("location") if isinstance(report.get("location"), dict) else {}
    label = _safe_text(location.get("label"), 80)
    return label or "当地"


def _period_text(period: Any) -> str:
    period = str(period or "today").strip().lower()
    return _PERIOD_ZH.get(period, "天气")


def _temperature_text(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    min_c = _fmt_number(raw.get("min_c"), decimals=0)
    max_c = _fmt_number(raw.get("max_c"), decimals=0)
    current = _fmt_number(raw.get("current_c"), decimals=1)
    feels = _fmt_number(raw.get("feels_like_c"), decimals=1)
    parts = []
    if min_c and max_c:
        parts.append(f"{min_c}–{max_c}°C")
    elif current:
        parts.append(f"当前 {current}°C")
    if feels:
        parts.append(f"体感 {feels}°C")
    return " · ".join(parts)


def _rain_text(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    pop = _fmt_number(raw.get("max_probability_pct"), decimals=0)
    amount = _fmt_number(raw.get("amount_mm"), decimals=1)
    parts = []
    if pop:
        parts.append(f"最高 {pop}%")
    if amount:
        parts.append(f"预计 {amount} mm")
    return " · ".join(parts)


def _wind_text(raw: Any, humidity: Any = None) -> str:
    parts = []
    if isinstance(raw, dict):
        speed = _fmt_number(raw.get("speed_kmh"), decimals=0)
        if speed:
            parts.append(f"风速约 {speed} km/h")
    hum = _fmt_number(humidity, decimals=0)
    if hum:
        parts.append(f"湿度约 {hum}%")
    return " · ".join(parts)


def _highlight_lines(raw: Any) -> list[str]:
    lines: list[str] = []
    if not isinstance(raw, list):
        return lines
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        time = _safe_text(item.get("time"), 40)
        condition = _safe_text(item.get("condition"), 80)
        temp = _fmt_number(item.get("temp_c"), decimals=1)
        pop = _fmt_number(item.get("precip_probability_pct"), decimals=0)
        bits = []
        if time:
            bits.append(time)
        if condition:
            bits.append(condition)
        if temp:
            bits.append(f"{temp}°C")
        if pop:
            bits.append(f"降雨 {pop}%")
        if bits:
            lines.append("，".join(bits))
    return lines


def _advice_text(raw: Any) -> str:
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        items = raw[:3]
    else:
        items = []
    cleaned = []
    for item in items:
        text = _safe_text(item, 100)
        if text and REDACTION_TEXT not in text and not _SENSITIVE_WORD_RE.search(text):
            cleaned.append(text)
    return "；".join(cleaned)


def _fmt_number(value: Any, *, decimals: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    if value != value or value in (float("inf"), float("-inf")):
        return ""
    if decimals == 0:
        return f"{value:.0f}"
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".")


def _template_for_weather(report: dict[str, Any]) -> str:
    precipitation = report.get("precipitation") if isinstance(report.get("precipitation"), dict) else {}
    pop = precipitation.get("max_probability_pct")
    amount = precipitation.get("amount_mm")
    try:
        if (pop is not None and float(pop) >= 50) or (amount is not None and float(amount) >= 1):
            return "orange"
    except Exception:
        pass
    return "blue"


def _safe_text(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    # Parser already sanitizes valid rich results, but renderers are user-facing
    # surfaces too; keep a second defensive pass here.
    text = sanitize_for_progress(value, max_len=max_len)
    text = _MARKDOWN_LINK_RE.sub(lambda match: match.group(1), text)
    text = _URL_RE.sub("", text)
    text = text.replace("@all", "all").replace("@here", "here")
    for ch in "<>[]()":
        text = text.replace(ch, "")
    return " ".join(text.split()).strip()
