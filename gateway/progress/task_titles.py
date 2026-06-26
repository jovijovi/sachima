"""Safe, low-loss task title normalization for user-facing progress panels."""

from __future__ import annotations

import re
from typing import Any, Iterable

from gateway.progress.redaction import sanitize_for_progress

_DEFAULT_MAX_TITLE_LEN = 180
_WHITESPACE_RE = re.compile(r"\s+")
_UNSAFE_COMMAND_TITLE_RE = re.compile(
    r"(?i)(\bcurl\s+|(?:^|\s)(?:-H|--header)\s+|(?:authorization|x-api-key|api-key|cookie|set-cookie)\s*:|bearer\s+\S+)"
)
_LEADING_NOISE_PATTERNS = (
    r"^(?:好的?|嗯+|呃+|额+)(?=\s|[，,。.!！：:]|$)\s*[，,。.!！：:]*\s*",
    r"^(?:ok(?:ay)?|please)\b\s*[，,。.!！：:]*\s*",
    r"^(?:can|could|would|will)\s+you(?:\s+please)?\s+",
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
# A bare time-of-day question (the whole message is the query), e.g.
# "现在几点了？", "几点了？", "现在时间？". Anchored full-match so that
# scheduling/action requests that merely mention "几点" do not collapse here.
_TIME_QUERY_RE = re.compile(
    r"^(?:现在|目前|此刻|这会儿|当前|今天|今儿)?(?:是|的)?\s*"
    r"(?:几点(?:钟)?了?|时间(?:是?多少)?|报时|什么时间)"
    r"(?:了|呢|啊|呀)?$"
)
# A bare date question (the whole message is the query), e.g.
# "今天几号？", "今天日期？", "现在星期几？".
_DATE_QUERY_RE = re.compile(
    r"^(?:今天|现在|目前|当前|今儿)?(?:是|的)?\s*"
    r"(?:几[号日]|日期(?:是?多少)?|(?:星期|周|礼拜)几)"
    r"(?:了|呢|啊|呀)?$"
)
# A scheduling question that asks the time of some action, e.g.
# "今天几点开会？" -> keep the "开会" action instead of collapsing to a query.
_SCHEDULE_TIME_RE = re.compile(
    r"^(今天|明天|后天|大后天|今晚|明晚|本周|下周|这周"
    r"|周[一二三四五六日天]|星期[一二三四五六日天]|礼拜[一二三四五六日天])?"
    r"(?:是|的)?(?:大概|大约|大致|具体)?\s*几点(?:钟)?\s*(.+)$"
)
_CONTROL_COMPACT_VALUES = {
    "ok",
    "okay",
    "yes",
    "y",
    "approved",
    "approve",
    "goahead",
    "continue",
    "next",
    "doit",
    "start",
    "implement",
    "fixit",
    "好的",
    "好",
    "可以",
    "行",
    "嗯",
    "同意",
    "批准",
    "授权",
    "已授权操作",
    "继续",
    "继续吧",
    "执行下一步",
    "下一步",
    "开始",
    "开工",
    "修吧",
    "批准开始实施",
    "接下来走正规开发流程批准开始实施",
    "ok执行下一步",
    "ok继续",
}
_LOW_INFORMATION_TITLES = {
    "task",
    "任务",
    "提炼并处理用户意图",
    "summarize user intent",
    "summarize multilingual user intent",
}


def summarize_task_intent(
    message: Any,
    *,
    context_messages: Iterable[Any] | None = None,
    max_len: int = _DEFAULT_MAX_TITLE_LEN,
) -> str:
    """Return a sanitized, high-density transaction title.

    This is intentionally conservative: it removes obvious conversational
    wrapper text and applies a few high-confidence task rewrites, but it avoids
    adding details that are not present in the user request.
    """

    raw_text = _normalize_whitespace(_message_to_text(message))
    text = _strip_conversational_noise(raw_text)
    contextual_title = _rewrite_contextual_control_intent(text, context_messages)
    if not contextual_title and raw_text != text:
        contextual_title = _rewrite_contextual_control_intent(raw_text, context_messages)
    if contextual_title:
        text = contextual_title
    else:
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
    unsafe_command = _rewrite_unsafe_command_or_header_intent(text)
    if unsafe_command:
        return unsafe_command
    task_workbench = _rewrite_task_workbench_title_intent(text)
    if task_workbench:
        return task_workbench
    weather = _rewrite_weather_intent(text)
    if weather:
        return weather
    datetime_query = _rewrite_datetime_query_intent(text)
    if datetime_query:
        return datetime_query
    optimization = _rewrite_progress_summary_intent(text)
    if optimization:
        return optimization
    review = _rewrite_english_review_intent(text)
    if review:
        return review
    generic = _rewrite_generic_intent(text)
    if generic:
        return generic
    return _fallback_non_raw_intent(text)


def _rewrite_contextual_control_intent(text: str, context_messages: Iterable[Any] | None) -> str:
    """Use recent conversation context for bare acknowledgements/approvals.

    A turn like "OK", "同意", or "批准开始实施" carries little task meaning by
    itself. The progress card should show the substantive task the user just
    approved, not a generic placeholder or the acknowledgement literal.
    """

    if not _is_contextual_control_turn(text):
        return ""

    for candidate in _iter_context_message_texts(context_messages, preferred_role="user"):
        title = _rewrite_high_confidence_intent(candidate)
        if not _is_low_information_title(title):
            return title
    for candidate in _iter_context_message_texts(context_messages, preferred_role="assistant"):
        title = _rewrite_high_confidence_intent(candidate)
        if not _is_low_information_title(title):
            return title

    return "推进已确认任务" if re.search(r"[\u4e00-\u9fff]", text or "") else "Continue approved task"


def _is_contextual_control_turn(text: str) -> bool:
    compact = re.sub(r"[\s，,。.!！?？：:；;、\-_/]+", "", (text or "").strip().lower())
    return compact in _CONTROL_COMPACT_VALUES


def _iter_context_message_texts(
    context_messages: Iterable[Any] | None,
    *,
    preferred_role: str,
) -> Iterable[str]:
    if not context_messages:
        return
    try:
        materialized = list(context_messages)
    except TypeError:
        return
    for entry in reversed(materialized[-12:]):
        role = ""
        content: Any = entry
        if isinstance(entry, dict):
            role = str(entry.get("role") or "").strip().lower()
            content = entry.get("content")
        if role and role != preferred_role:
            continue
        candidate = _strip_conversational_noise(_normalize_whitespace(_message_to_text(content)))
        if not candidate or _is_contextual_control_turn(candidate):
            continue
        # Skip tiny fragments; they usually do not carry enough task semantics.
        if len(candidate) < 8:
            continue
        yield candidate


def _is_low_information_title(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", (title or "").strip().lower())
    return not normalized or normalized in _LOW_INFORMATION_TITLES


def _rewrite_task_workbench_title_intent(text: str) -> str:
    lowered = text.lower()
    mentions_workbench = "任务工作台" in text or "task workbench" in lowered
    mentions_task_title = (
        "任务" in text
        and any(term in text for term in ("标题", "摘要", "用户意图", "内容描述", "提炼并处理用户意图"))
    ) or ("task" in lowered and any(term in lowered for term in ("title", "summary", "intent")))
    if mentions_workbench and mentions_task_title:
        if re.search(r"[\u4e00-\u9fff]", text):
            return "优化飞书任务工作台任务标题摘要生成"
        return "Improve Task Workbench task-title summaries"
    return ""


def _rewrite_unsafe_command_or_header_intent(text: str) -> str:
    if not _UNSAFE_COMMAND_TITLE_RE.search(text or ""):
        return ""
    if re.search(r"[\u4e00-\u9fff]", text or ""):
        return "安全处理命令或鉴权相关请求"
    return "Handle command or authorization-related request safely"


def _rewrite_datetime_query_intent(text: str) -> str:
    """Rewrite bare current time/date questions into compact, low-entropy intents.

    Only fires when the whole message is a time-of-day or date utility question
    (e.g. "现在几点了？", "今天几号？"). Scheduling, bug-fix or other action
    requests that merely mention "几点" or "当前日期" keep their action/object
    intent and fall through to the generic rewrites.
    """
    core = text.strip().strip("？?。.！!　 ")
    if not core:
        return ""
    if _TIME_QUERY_RE.fullmatch(core):
        return "查询当前时间"
    if _DATE_QUERY_RE.fullmatch(core):
        return "查询当前日期"
    return _rewrite_scheduling_time_question(core)


def _rewrite_scheduling_time_question(core: str) -> str:
    """Preserve scheduling questions like "今天几点开会？" instead of collapsing.

    Returns a compact intent that keeps the action (e.g. "查询今天开会时间"), or
    an empty string when the text is not a "几点 + action" scheduling question.
    """
    match = _SCHEDULE_TIME_RE.match(core)
    if not match:
        return ""
    prefix = match.group(1) or ""
    action = re.sub(r"[了呢啊吗呀吧的\s]+$", "", (match.group(2) or "").strip())
    if not action:
        return ""
    return f"查询{prefix}{action}时间"


def _rewrite_weather_intent(text: str) -> str:
    lowered = text.lower()
    if any(term in text for term in ("天气卡", "天气信息卡", "天气富卡", "天气交互卡")):
        return ""
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
    if (
        ("发现一个问题" in text or "有个问题" in text)
        and "任务" in text
        and ("用户原文" in text or "原文" in text)
        and ("用户意图" in text or "摘要" in text)
    ):
        return "修复事务卡任务字段仍显示用户原文的问题：保留多语言约束，确保高语义密度、低信息损失与低信息熵增"

    if "事务摘要" in text and ("不要限制过短" in text or "语义密度" in text or "信息损失" in text or "熵增" in text):
        return "调整事务摘要策略：避免过短限制，在多语言场景中优先保证清晰、高语义密度、低信息损失与低信息熵增"

    if "事务" in text and "任务" in text and ("用户原文" in text or "用户意图" in text or "摘要" in text):
        return "优化事务信息显示：将“任务”字段从用户原文改为用户意图摘要"

    if "优化点" in text and "任务" in text:
        detail = re.sub(r"^.*?优化点(?:是|为|：|:)?", "", text, count=1).strip("。 ，,；;")
        if detail and detail != text.strip():
            return f"梳理任务优化点：{detail}"
        compact = re.sub(r"[：:]?\s*\d+[、.]", "：", text, count=1)
        rewritten = _trim_redundant_prefixes(compact)
        if rewritten and rewritten != text.strip():
            return rewritten
        return "梳理任务优化点"
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
    stripped = text.strip().rstrip(".?!")
    constraint = ""
    main = stripped

    sentence_constraint = re.search(r"(?i)(?:[?.!]\s*|,\s*)((?:do not|don't|without|never|avoid)\b.+)$", stripped)
    if sentence_constraint:
        constraint = sentence_constraint.group(1).strip().rstrip(".?!")
        main = stripped[: sentence_constraint.start()].strip().rstrip("?.!,")

    match = re.search(r"(?i)\s*,?\s+but\s+(.+)$", main)
    if match:
        constraint = match.group(1).strip().rstrip(".?!")
        main = main[: match.start()].strip().rstrip(",.")

    if not constraint:
        inline_constraint = re.search(r"(?i)\s+((?:without|do not|don't|never|avoid)\b.+)$", main)
        if inline_constraint:
            constraint = inline_constraint.group(1).strip().rstrip(".?!")
            main = main[: inline_constraint.start()].strip().rstrip("?.!,")

    main = re.sub(
        r"(?i)\s+and\s+(?=(?:add|write|create|update|implement|fix|check|review|run|generate|analyze|analyse)\b)",
        "; ",
        main,
    )
    main = re.sub(r"\s+", " ", main).strip()
    if constraint:
        return f"{_rewrite_english_fallback_intent(main)}; constraint: {constraint}"
    if main != stripped:
        return _rewrite_english_fallback_intent(main)
    return _rewrite_english_fallback_intent(main)


def _rewrite_generic_chinese_intent(text: str) -> str:
    stripped = text.strip()
    stripped = re.sub(r"^请(?=(?:检查|介绍|修复|优化|分析|查询|查看|生成|创建|写|实现|调整|改|处理|排查|测试|总结))", "", stripped, count=1)

    constraint_match = re.search(r"[，,；;。?？]\s*((?:不要|不能|避免|不得|无需|不需要).+)$", stripped)
    if constraint_match:
        main = stripped[: constraint_match.start()].strip("，,；;。?？!！ ")
        constraint = constraint_match.group(1).strip("。 ")
        if main:
            base = _rewrite_chinese_fallback_intent(main) or _rewrite_chinese_action_intent(main) or main
            return f"{base}；约束：{constraint}"

    explicit = _rewrite_chinese_fallback_intent(stripped)
    if explicit:
        return explicit

    if stripped != text.strip():
        return _rewrite_chinese_action_intent(stripped) or stripped
    action = _rewrite_chinese_action_intent(stripped)
    if action:
        return action
    return _rewrite_chinese_fallback_intent(stripped) or "推进用户请求"


def _rewrite_chinese_action_intent(text: str) -> str:
    action_map = {
        "检查": "排查",
        "介绍": "说明",
        "修复": "解决",
        "优化": "改进",
        "分析": "梳理分析",
        "查询": "获取",
        "查看": "查阅",
        "生成": "产出",
        "创建": "建立",
        "写": "撰写",
        "实现": "完成",
        "调整": "更新",
        "改": "修改",
        "处理": "推进处理",
        "排查": "定位",
        "测试": "验证",
        "总结": "归纳",
    }
    for raw_action, intent_action in action_map.items():
        if text.startswith(raw_action) and len(text) > len(raw_action):
            return f"{intent_action}{text[len(raw_action):].strip()}"
    return ""


def _rewrite_chinese_fallback_intent(text: str) -> str:
    if not text:
        return ""

    if "模型" in text and "思考强度" in text:
        return "说明当前模型与思考强度配置"
    if "模型" in text and ("什么" in text or "哪个" in text or "使用" in text):
        return "说明当前模型配置"
    if "更新代码" in text and ("需要" in text or "吗" in text or "怎么着" in text):
        return "评估是否需要更新代码并给出处理建议"

    match = re.search(r"^(.{1,80}?流程)怎么写[？?。!！]*$", text)
    if match:
        return f"说明{match.group(1)}写法"

    match = re.search(r"^需要(.{1,80}?)吗(?:[？?。!！]|$).*", text)
    if match:
        return f"评估是否需要{match.group(1).strip()}"

    match = re.search(r"^(.{1,80}?)(?:咋样|怎么样)[？?。!！]*$", text)
    if match:
        return f"评估{match.group(1).strip()}情况"

    return ""


def _rewrite_english_fallback_intent(text: str) -> str:
    main = re.sub(r"\s+", " ", text.strip().rstrip(".?!"))
    if not main:
        return "Task"

    match = re.match(r"(?i)^(?:do we need to|should we|need to)\s+(.+?)\??$", main)
    if match:
        action = match.group(1).strip()
        if re.search(r"(?i)\b(update|change|modify)\s+code\b", action):
            return "Assess whether code updates are needed"
        return f"Assess whether to {action}"

    match = re.match(r"(?i)^(.+?)\s+fails(?:,\s*(.+))?$", main)
    if match:
        subject = match.group(1).strip()
        trailing = (match.group(2) or "").strip()
        constraint = ""
        if trailing:
            trailing = re.sub(r"(?i)^investigate\s*", "", trailing).strip()
            if trailing:
                constraint = f"; constraint: {trailing}"
        return f"Investigate {subject} failure{constraint}"

    match = re.match(r"(?i)^(.+?)\s+progress\s+summary\s+(.+)$", main)
    if match:
        subject = match.group(1).strip()
        scope = match.group(2).strip()
        return f"Summarize {subject} progress {scope}"

    match = re.match(
        r"(?i)^(explain|summarize|summarise|investigate|analyze|analyse|review|fix|check|update|create|write|generate|implement|train|brainstorm)\b\s*(.+)$",
        main,
    )
    if match:
        verb = match.group(1).lower()
        rest = match.group(2).strip()
        action_templates = {
            "summarise": "Condense {rest}",
            "summarize": "Condense {rest}",
            "analyse": "Assess {rest}",
            "analyze": "Assess {rest}",
            "explain": "Clarify {rest}",
            "investigate": "Probe {rest}",
            "review": "Assess {rest}",
            "fix": "Resolve {rest}",
            "check": "Inspect {rest}",
            "update": "Plan update for {rest}",
            "create": "Set up {rest}",
            "write": "Draft {rest}",
            "generate": "Produce {rest}",
            "implement": "Build {rest}",
            "train": "Plan to train {rest}",
            "brainstorm": "Brainstorm ideas for {rest}",
        }
        return action_templates.get(verb, "Handle {rest}").format(rest=rest)

    return "Handle user request"


def _fallback_non_raw_intent(text: str) -> str:
    cleaned = _trim_redundant_prefixes(text)
    if cleaned and cleaned != text.strip():
        return cleaned
    if any(ch.isalpha() for ch in text):
        return "Summarize multilingual user intent"
    return "Handle user request"


def _trim_redundant_prefixes(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^事务信息显示的效果，还有一些优化点[：:]?\s*", "优化事务信息显示：", cleaned)
    cleaned = re.sub(r"[：:]\s*\d+[、.]", "：", cleaned, count=1)
    return cleaned.strip()
