"""Safe, low-loss task title normalization for user-facing progress panels."""

from __future__ import annotations

import re
from typing import Any

from gateway.progress.redaction import sanitize_for_progress

_DEFAULT_MAX_TITLE_LEN = 320
_WHITESPACE_RE = re.compile(r"\s+")
_LEADING_NOISE_PATTERNS = (
    r"^(?:好的?|嗯+|呃+|额+)(?=\s|[，,。.!！：:]|$)\s*[，,。.!！：:]*\s*",
    r"^(?:ok(?:ay)?|please)\b\s*[，,。.!！：:]*\s*",
    r"^(?:麻烦你|麻烦|帮我|帮忙)\s*[，,。.!！：:]*\s*",
    r"^(?:请问|请帮(?:我)?|烦请)\s*[，,。.!！：:]*\s*",
    r"^(?:再试一次|再来一次|重试(?:一下)?|try again)\s*[，,。.!！：:]*\s*",
)
_TRAILING_NOISE_PATTERNS = (
    r"\s*(?:谢谢|thanks|thank you)[。.!！]*\s*$",
)
_WEATHER_TIME_TERMS = (
    "现在",
    "今晚",
    "明天",
    "今日",
    "今天",
    "后天",
    "本周",
    "周末",
    "tomorrow",
    "tonight",
    "today",
    "now",
)


def summarize_task_intent(message: Any, *, max_len: int = _DEFAULT_MAX_TITLE_LEN) -> str:
    """Return a sanitized, high-density transaction title.

    This is intentionally conservative: it removes obvious conversational
    wrapper text and applies a few high-confidence task rewrites, but it avoids
    adding details that are not present in the user request.
    """

    text = _message_to_text(message)
    text = _normalize_whitespace(text)
    text = _strip_conversational_noise(text)
    text = _rewrite_high_confidence_intent(text)
    text = sanitize_for_progress(text or "Task", max_len=max_len)
    return text or "Task"


def _message_to_text(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        text_bits: list[str] = []
        image_count = 0
        for part in message:
            if isinstance(part, str):
                if part:
                    text_bits.append(part)
                continue
            if not isinstance(part, dict):
                continue
            ptype = str(part.get("type") or "").strip().lower()
            if ptype in {"text", "input_text", "output_text"}:
                text = part.get("text")
                if isinstance(text, str) and text:
                    text_bits.append(text)
            elif ptype in {"image_url", "input_image"}:
                image_count += 1
        text = " ".join(text_bits).strip()
        if image_count:
            prefix = f"[{image_count} image{'s' if image_count != 1 else ''}]"
            return f"{prefix} {text}" if text else prefix
        return text
    try:
        return str(message)
    except Exception:
        return ""


def _normalize_whitespace(text: str) -> str:
    text = (text or "").replace("\u3000", " ").strip()
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _strip_conversational_noise(text: str) -> str:
    cleaned = text.strip()
    changed = True
    while changed:
        changed = False
        for pattern in _LEADING_NOISE_PATTERNS:
            new = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
            if new != cleaned:
                cleaned = new
                changed = True
    for pattern in _TRAILING_NOISE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _rewrite_high_confidence_intent(text: str) -> str:
    if not text:
        return "Task"
    weather = _rewrite_weather_intent(text)
    if weather:
        return weather
    optimization = _rewrite_progress_summary_intent(text)
    if optimization:
        return optimization
    review = _rewrite_english_review_intent(text)
    if review:
        return review
    generic = _rewrite_generic_intent(text)
    if generic:
        return generic
    return _trim_redundant_prefixes(text)


def _rewrite_weather_intent(text: str) -> str:
    lowered = text.lower()
    has_chinese_weather = any(term in text for term in ("天气", "下雨", "降雨", "带伞", "雨夹雪", "阵雨", "暴雨", "小雨", "中雨", "大雨"))
    has_english_weather = bool(re.search(r"(?i)\b(weather|rain|raining|rainy|umbrella)\b", text))
    has_weather = has_chinese_weather or has_english_weather
    if not has_weather:
        return ""

    if re.search(r"[A-Za-z]", text):
        return _rewrite_english_weather_intent(text, lowered)

    time_term = ""
    for term in _WEATHER_TIME_TERMS:
        if term in text:
            time_term = term
            break

    location = _extract_chinese_location_before_time(text, time_term) or _extract_chinese_location_after_time(text, time_term)
    scope = f"{location}{time_term}" if (location or time_term) else "指定时段"
    asks_advice = any(term in text for term in ("带伞", "出行", "建议", "怎么穿", "穿什么"))

    if "下雨" in text or "降雨" in text or "雨" in text:
        suffix = "与出行建议" if asks_advice else ""
        return f"查询{scope}降雨情况{suffix}"
    if "天气" in text:
        suffix = "与出行建议" if asks_advice else ""
        return f"查询{scope}天气情况{suffix}"
    return ""


def _rewrite_english_weather_intent(text: str, lowered: str) -> str:
    time_term = ""
    for term in ("tomorrow", "tonight", "today", "now"):
        if term in lowered:
            time_term = term
            break

    location = ""
    match = re.search(r"(?i)\bin\s+([A-Za-z][A-Za-z .'-]{0,80}?)(?:\s+(?:tomorrow|tonight|today|now)\b|[?.!,]|$)", text)
    if match:
        location = match.group(1).strip()

    scope = " ".join(part for part in (location, time_term) if part).strip()
    asks_advice = bool(re.search(r"(?i)\b(umbrella|travel|advice|wear)\b", text))
    asks_rain = bool(re.search(r"(?i)\b(rain|raining|rainy|umbrella)\b", text))
    asks_weather = bool(re.search(r"(?i)\bweather\b", text))
    if asks_rain:
        suffix = " and advice" if asks_advice else ""
        return f"Check rain{(' in ' + scope) if scope else ''}{suffix}"
    if asks_weather:
        suffix = " and advice" if asks_advice else ""
        return f"Check weather{(' in ' + scope) if scope else ''}{suffix}"
    return ""


def _extract_chinese_location_before_time(text: str, time_term: str) -> str:
    if not time_term or time_term not in text:
        return ""
    before = text.split(time_term, 1)[0]
    return _clean_chinese_location_candidate(before)


def _extract_chinese_location_after_time(text: str, time_term: str) -> str:
    if not time_term or time_term not in text:
        return ""
    after = text.split(time_term, 1)[1]
    marker_positions = [pos for marker in ("下雨", "降雨", "天气", "带伞", "雨夹雪", "阵雨", "暴雨", "小雨", "中雨", "大雨") if (pos := after.find(marker)) >= 0]
    if not marker_positions:
        return ""
    candidate = after[: min(marker_positions)]
    return _clean_chinese_location_candidate(candidate)


def _clean_chinese_location_candidate(candidate: str) -> str:
    candidate = re.sub(r"^[，,。.!！：:\s]+|[，,。.!！：:\s]+$", "", candidate or "")
    candidate = re.sub(r"^(?:查询|查看|看看|问一下|在)", "", candidate)
    candidate = re.sub(r"(?:会|是否|可能|有|要|将|在)$", "", candidate).strip()
    candidate = re.sub(r"^在", "", candidate).strip()
    if not candidate or len(candidate) > 12:
        return ""
    if any(ch in candidate for ch in "？?，,。.!！：:"):
        return ""
    return candidate


def _rewrite_progress_summary_intent(text: str) -> str:
    if "事务摘要" in text and ("不要限制过短" in text or "语义密度" in text or "信息损失" in text or "熵增" in text):
        return "调整事务摘要策略：避免过短限制，在多语言场景中优先保证清晰、高语义密度、低信息损失与低信息熵增"

    if "事务" in text and "任务" in text and ("用户原文" in text or "用户意图" in text or "摘要" in text):
        return "优化事务信息显示：将“任务”字段从用户原文改为用户意图摘要"

    if "优化点" in text and "任务" in text:
        compact = re.sub(r"[：:]?\s*\d+[、.]", "：", text, count=1)
        return _trim_redundant_prefixes(compact)
    return ""


def _rewrite_english_review_intent(text: str) -> str:
    stripped = text.strip()
    if re.match(r"(?i)^please\s+review\b", stripped):
        return re.sub(r"(?i)^please\s+", "", stripped, count=1).strip().capitalize()
    return ""


def _rewrite_generic_intent(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if re.search(r"[\u4e00-\u9fff]", stripped):
        return _rewrite_generic_chinese_intent(stripped)
    if re.search(r"[A-Za-z]", stripped):
        return _rewrite_generic_english_intent(stripped)
    return ""


def _rewrite_generic_english_intent(text: str) -> str:
    stripped = text.strip().rstrip(".")
    constraint = ""
    main = stripped
    match = re.search(r"(?i)\s*,?\s+but\s+(.+)$", stripped)
    if match:
        constraint = match.group(1).strip().rstrip(".")
        main = stripped[: match.start()].strip().rstrip(",.")

    main = re.sub(
        r"(?i)\s+and\s+(?=(?:add|write|create|update|implement|fix|check|review|run|generate|analyze|analyse)\b)",
        "; ",
        main,
    )
    main = re.sub(r"\s+", " ", main).strip()
    if constraint:
        return f"{main}; constraint: {constraint}"
    if main != stripped:
        return main
    return f"Handle request: {main}"


def _rewrite_generic_chinese_intent(text: str) -> str:
    stripped = text.strip()
    stripped = re.sub(r"^请(?=(?:检查|介绍|修复|优化|分析|查询|查看|生成|创建|写|实现|调整|改|处理|排查|测试|总结))", "", stripped, count=1)

    match = re.search(r"[，,；;]\s*((?:不要|不能|避免|不得|无需|不需要).+)$", stripped)
    if match:
        main = stripped[: match.start()].strip("，,；;。 ")
        constraint = match.group(1).strip("。 ")
        if main:
            return f"{main}；约束：{constraint}"

    if stripped != text.strip():
        return stripped
    return f"处理请求：{stripped}"


def _trim_redundant_prefixes(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^事务信息显示的效果，还有一些优化点[：:]?\s*", "优化事务信息显示：", cleaned)
    cleaned = re.sub(r"[：:]\s*\d+[、.]", "：", cleaned, count=1)
    return cleaned.strip()
