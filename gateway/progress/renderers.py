"""Text renderers for gateway transaction progress panels."""

from __future__ import annotations

import ast
from datetime import datetime
import json
import re
import shlex
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from gateway.progress.events import ContextUsageSnapshot, ProgressOperation, TransactionSnapshot
from gateway.progress.redaction import sanitize_for_progress

_STATUS_LABELS = {
    "running": "Running",
    "completed": "Completed",
    "failed": "Failed",
    "blocked": "Blocked",
    "cancelled": "Cancelled",
    "pending": "Pending",
}

_STATUS_ICONS = {
    "running": "🔄",
    "completed": "✅",
    "failed": "❌",
    "blocked": "⛔",
    "cancelled": "⚪",
    "pending": "⏳",
}

_EVENT_LABELS = {
    "subagent.start": "subagent start",
    "subagent.complete": "subagent complete",
    "subagent.progress": "subagent progress",
    "subagent.thinking": "subagent thinking",
    "subagent.tool": "subagent tool",
}

_DEFAULT_MAX_LENGTH = 3500

_FEISHU_HEADER_TEMPLATES = {
    "running": "blue",
    "pending": "blue",
    "completed": "green",
    "failed": "red",
    "blocked": "orange",
    "cancelled": "grey",
}

_FEISHU_STATUS_LABELS = {
    "zh": {
        "running": "⏳ 正在处理",
        "pending": "⏳ 等待中",
        "completed": "完成",
        "failed": "失败",
        "blocked": "等待确认",
        "cancelled": "已取消",
    },
    "en": {
        "running": "Running",
        "pending": "Pending",
        "completed": "Completed",
        "failed": "Failed",
        "blocked": "Blocked",
        "cancelled": "Cancelled",
    },
}

_FEISHU_TITLES = {
    "zh": {
        "running": ("🔄", "任务工作台 · 运行中"),
        "pending": ("⏳", "任务工作台 · 等待中"),
        "completed": ("✅", "任务工作台 · 已完成"),
        "failed": ("⚠️", "任务工作台 · 失败"),
        "blocked": ("⛔", "任务工作台 · 等待确认"),
        "cancelled": ("⚪", "任务工作台 · 已取消"),
    },
    "en": {
        "running": ("🔄", "Task Workbench · Running"),
        "pending": ("⏳", "Task Workbench · Pending"),
        "completed": ("✅", "Task Workbench · Completed"),
        "failed": ("⚠️", "Task Workbench · Failed"),
        "blocked": ("⛔", "Task Workbench · Blocked"),
        "cancelled": ("⚪", "Task Workbench · Cancelled"),
    },
}

_SCRIPT_TOKEN_RE = re.compile(
    r"(?P<token>(?:[A-Za-z]:[\\/]|/|\./|\.\./|~/)?[^\s'\"`]+"
    r"\.(?:py|js|ts|tsx|jsx|sh|bash|zsh|rb|pl|php|go|rs|java|kt|scala|sql|ya?ml|json|toml|md|txt))"
)
_SHELL_WORD_RE = re.compile(r"[^\s'\"`]+")
_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+:-]{0,119}$")
_SAFE_SKILL_IDENTIFIER_RE = re.compile(
    r"^(?:[a-z0-9][a-z0-9_-]{0,63}(?:/[a-z0-9][a-z0-9_-]{0,63}){0,4}|"
    r"[a-z0-9][a-z0-9_-]{0,63}:[a-z0-9][a-z0-9_-]{0,63})$"
)
_PATH_LIKE_SKILL_PREFIXES = {
    "assets",
    "dev",
    "etc",
    "home",
    "media",
    "mnt",
    "opt",
    "private",
    "proc",
    "references",
    "root",
    "scripts",
    "sys",
    "templates",
    "tmp",
    "usr",
    "users",
    "var",
}
_TOKEN_LIKE_SKILL_PREFIXES = ("sk-", "sk_", "ghp_", "gho_", "github_pat_", "xox", "hf_", "hf-", "pat_")
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_UNSAFE_FEISHU_TASK_TITLE_RE = re.compile(
    r"(?i)(\bcurl\s+|(?:^|\s)(?:-H|--header)\s+|(?:authorization|x-api-key|api-key|cookie|set-cookie)\s*:|bearer\s+\S+)"
)


def render_text_panel(
    snapshot: TransactionSnapshot,
    *,
    tool_progress_mode: str = "all",
    max_length: int = _DEFAULT_MAX_LENGTH,
    dashboard_url: str | None = None,
) -> str:
    """Render a compact Markdown-compatible transaction progress panel."""

    mode = (tool_progress_mode or "all").strip().lower()
    if mode not in {"off", "new", "all", "verbose"}:
        mode = "all"

    title = sanitize_for_progress(snapshot.title or "Task", max_len=320)
    status = snapshot.status or "running"
    status_icon = _STATUS_ICONS.get(status, "🔄")
    status_label = _STATUS_LABELS.get(status, status.title())

    lines = [
        f"📌 **Transaction:** {title}",
        f"{status_icon} **Status:** {status_label}",
    ]
    context_line = _context_usage_text_line(snapshot.context_usage)
    if context_line:
        lines.append(context_line)

    operations = list(snapshot.recent_operations or ())
    if mode != "off":
        lines.append("")
        lines.append("**Recent operations:**")
        rendered_ops = list(_iter_rendered_operations(operations, mode=mode))
        if rendered_ops:
            lines.extend(rendered_ops)
        else:
            lines.append("- No operations yet")

    progress_link = _safe_progress_dashboard_url(dashboard_url)
    if progress_link:
        lines.append("")
        lines.append(f"🔎 **Dashboard:** {progress_link}")

    text = "\n".join(lines)
    return _cap_panel(text, max_length)


def render_feishu_progress_card(
    snapshot: TransactionSnapshot,
    *,
    tool_progress_mode: str = "all",
    max_operations: int = 5,
    dashboard_url: str | None = None,
    style: str = "lively",
    emoji: bool = True,
    language: str = "zh",
) -> dict:
    """Render a sanitized Feishu interactive-card payload for task progress.

    The card intentionally shows only summary labels. It never renders raw
    command lines, argument previews, outputs, headers, tokens, or arbitrary
    metadata dumps; those remain available in backend logs/dashboard only.
    """

    mode = _normalize_progress_mode(tool_progress_mode)
    lang = _normalize_feishu_language(language)
    status = snapshot.status or "running"
    title = _feishu_safe_task_title(snapshot.title, language=lang)
    status_label = sanitize_for_progress(_feishu_status_label(status, language=lang), max_len=80)
    labels = _feishu_labels(lang)
    status_icon = _feishu_status_icon(status, language=lang)

    details = [
        f"{_feishu_metric_label('📌', labels['task'], lang)} {_feishu_escape_markdown_text(title)}",
        f"{_feishu_metric_label(status_icon, labels['status'], lang)} {_feishu_escape_markdown_text(status_label)}",
    ]
    total_duration = _snapshot_elapsed_duration(snapshot)
    if total_duration:
        details.append(f"{_feishu_metric_label('⏱️', labels['duration'], lang)} {total_duration}")
    context_detail = _context_usage_feishu_line(snapshot.context_usage, language=lang)
    if context_detail:
        details.append(context_detail)

    elements: list[dict] = [{"tag": "markdown", "content": "\n".join(details)}]

    if mode != "off":
        operation_lines = list(
            _iter_feishu_operation_lines(
                snapshot.recent_operations or (),
                mode=mode,
                max_operations=max_operations,
                emoji=emoji,
                language=lang,
            )
        )
        operation_label = f"**{labels['recent_operations']}：**" if lang == "zh" else f"**{labels['recent_operations']}:**"
        empty_copy = "暂无操作" if lang == "zh" else "No operations yet"
        elements.append(
            {
                "tag": "markdown",
                "content": operation_label + "\n" + ("\n".join(operation_lines) if operation_lines else empty_copy),
            }
        )

    progress_link = _safe_progress_dashboard_url(dashboard_url)
    if progress_link:
        link_label = "打开进度面板" if lang == "zh" else "Open progress dashboard"
        elements.append(
            {
                "tag": "markdown",
                "content": f"[{link_label}]({_feishu_escape_url(progress_link)})",
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": _feishu_header_title(status, style=style, emoji=emoji, language=lang),
            },
            "template": _feishu_header_template(status),
        },
        "elements": elements,
    }


def _iter_rendered_operations(
    operations: Iterable[ProgressOperation],
    *,
    mode: str,
) -> Iterable[str]:
    previous_tool = object()
    for operation in operations:
        tool_key = operation.tool_name or operation.event_type
        if mode == "new" and tool_key == previous_tool:
            continue
        previous_tool = tool_key
        yield _render_operation(operation, mode=mode)


def _render_operation(operation: ProgressOperation, *, mode: str) -> str:
    icon = _STATUS_ICONS.get(operation.status, "•")
    name = _operation_name(operation)
    preview = operation.preview or ""
    duration = _format_duration(operation.duration)

    line = f"- {icon} `{name}`"
    if preview:
        line += f": {preview}"
    if duration:
        line += f" ({duration})"

    if mode == "verbose":
        details = []
        if operation.args_preview:
            details.append(f"args={operation.args_preview}")
        if operation.metadata:
            metadata = sanitize_for_progress(operation.metadata, max_len=500)
            if metadata and metadata != "{}":
                details.append(f"metadata={metadata}")
        if details:
            line += "\n  " + "\n  ".join(details)

    return line


def _operation_name(operation: ProgressOperation) -> str:
    if operation.event_type in _EVENT_LABELS:
        label = _EVENT_LABELS[operation.event_type]
        if operation.tool_name and operation.tool_name != "subagent":
            return f"{label}: {operation.tool_name}"
        return label
    return operation.tool_name or operation.event_type or "operation"


def _normalize_progress_mode(tool_progress_mode: object | None) -> str:
    mode = str(tool_progress_mode or "all").strip().lower()
    if mode not in {"off", "new", "all", "verbose"}:
        return "all"
    return mode


def _normalize_feishu_style(style: object | None) -> str:
    normalized = str(style or "lively").strip().lower()
    return normalized if normalized in {"lively", "neutral", "compact"} else "lively"


def _normalize_feishu_language(language: object | None) -> str:
    normalized = str(language or "zh").strip().lower()
    if normalized in {"zh", "zh-cn", "zh_cn", "cn", "chinese"}:
        return "zh"
    if normalized in {"en", "en-us", "en_us", "english"}:
        return "en"
    return "zh"


def _feishu_safe_task_title(title: object, *, language: str) -> str:
    lang = _normalize_feishu_language(language)
    fallback = "Handle user request safely" if lang == "en" else "安全处理用户请求"
    default = "Task" if lang == "en" else "任务"
    raw = str(title or "")
    if _UNSAFE_FEISHU_TASK_TITLE_RE.search(raw):
        return fallback
    safe = sanitize_for_progress(raw or default, max_len=320)
    if _UNSAFE_FEISHU_TASK_TITLE_RE.search(safe):
        return fallback
    return safe or default


def detect_feishu_progress_card_language(message: object, configured: object | None = "auto") -> str:
    """Resolve Feishu progress-card language from config and user text.

    ``configured`` accepts explicit zh/en values. ``auto`` chooses Chinese when
    the current user message contains CJK text and English otherwise.
    """

    configured_text = str(configured or "auto").strip().lower()
    if configured_text not in {"", "auto", "detect"}:
        return _normalize_feishu_language(configured_text)
    text = str(message or "")
    return "zh" if _CJK_RE.search(text) else "en"


def _feishu_labels(language: str) -> dict[str, str]:
    if _normalize_feishu_language(language) == "en":
        return {
            "task": "Task",
            "status": "Status",
            "duration": "Duration",
            "context": "Context",
            "recent_operations": "Recent operations",
            "running": "running",
            "tool": "Tool",
            "command": "Command",
            "skill": "Skill",
        }
    return {
        "task": "任务",
        "status": "状态",
        "duration": "耗时",
        "context": "上下文",
        "recent_operations": "最近操作",
        "running": "进行中",
        "tool": "工具",
        "command": "命令",
        "skill": "技能",
    }


def _feishu_status_label(status: str, *, language: str) -> str:
    labels = _FEISHU_STATUS_LABELS.get(_normalize_feishu_language(language), _FEISHU_STATUS_LABELS["zh"])
    return labels.get(status or "running", str(status or "running").title())


def _feishu_header_template(status: str) -> str:
    return _FEISHU_HEADER_TEMPLATES.get(status or "running", "blue")


def _feishu_header_title(status: str, *, style: object, emoji: bool, language: str) -> str:
    # ``style`` is kept for config compatibility; Feishu progress cards now use
    # neutral workbench copy in every style so the default work profile cannot be
    # confused with the separate Samiya companion bot.
    del style
    lang = _normalize_feishu_language(language)
    titles = _FEISHU_TITLES.get(lang, _FEISHU_TITLES["zh"])
    icon, text = titles.get(status or "running", titles["running"])
    content = f"{icon} {text}" if emoji else text
    return sanitize_for_progress(content, max_len=80)


def _feishu_status_icon(status: str, *, language: str) -> str:
    titles = _FEISHU_TITLES.get(_normalize_feishu_language(language), _FEISHU_TITLES["zh"])
    icon, _ = titles.get(status or "running", titles["running"])
    return icon


def _feishu_metric_label(icon: str, label: str, language: str) -> str:
    separator = "：" if _normalize_feishu_language(language) == "zh" else ":"
    return f"**{icon} {label}{separator}**"


def _context_usage_text_line(usage: ContextUsageSnapshot | None) -> str:
    if usage is None:
        return ""
    body = _context_usage_body(usage, language="en")
    if not body:
        return ""
    return sanitize_for_progress(f"🧠 **Context:** {body}", max_len=240)


def _context_usage_feishu_line(usage: ContextUsageSnapshot | None, *, language: str = "zh") -> str:
    if usage is None:
        return ""
    lang = _normalize_feishu_language(language)
    body = _context_usage_body(usage, language=lang)
    if not body:
        return ""
    label = _feishu_labels(lang)["context"]
    prefix = _feishu_metric_label("🧠", label, lang)
    return sanitize_for_progress(f"{prefix} {body}", max_len=240)


def _context_usage_body(usage: ContextUsageSnapshot, *, language: str) -> str:
    current = _safe_nonnegative_int(getattr(usage, "current_tokens", 0))
    window = _safe_nonnegative_int(getattr(usage, "context_window", 0))
    peak = _safe_nonnegative_int(getattr(usage, "peak_tokens", 0))
    compressions = _safe_nonnegative_int(getattr(usage, "compression_count", 0))
    if not any((current, peak, compressions)):
        return ""

    if current > 0:
        if window > 0:
            percent = (current / window) * 100
            if language == "zh":
                parts = [f"{_format_count(current)} / {_format_count(window)}（{percent:.1f}%）"]
            else:
                parts = [f"{_format_count(current)} / {_format_count(window)} tokens ({percent:.1f}%)"]
        elif language == "zh":
            parts = [f"{_format_count(current)} tokens"]
        else:
            parts = [f"{_format_count(current)} tokens"]
    else:
        parts = []

    if language == "zh":
        if peak > 0:
            parts.append(f"峰值 {_format_count(peak)}")
        if compressions > 0 or current > 0:
            parts.append(f"自动压缩 {compressions} 次")
    else:
        if peak > 0:
            parts.append(f"peak {_format_count(peak)}")
        if compressions > 0 or current > 0:
            parts.append(f"compressions {compressions}")
    return " · ".join(parts)


def _format_count(value: int) -> str:
    return f"{_safe_nonnegative_int(value):,}"


def _safe_nonnegative_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except Exception:
        return 0
    return max(0, number)


def _snapshot_elapsed_duration(snapshot: TransactionSnapshot) -> str:
    end = snapshot.completed_at if snapshot.completed_at is not None else getattr(snapshot, "updated_at", None)
    if end is None or not snapshot.started_at:
        return ""
    try:
        elapsed = float(end) - float(snapshot.started_at)
    except Exception:
        return ""
    if elapsed < 0:
        return ""
    return _format_duration(elapsed)


def _snapshot_duration(snapshot: TransactionSnapshot) -> str:
    return _snapshot_elapsed_duration(snapshot)


def _iter_feishu_operation_lines(
    operations: Iterable[ProgressOperation],
    *,
    mode: str,
    max_operations: int,
    emoji: bool,
    language: str = "zh",
) -> Iterable[str]:
    try:
        limit = max(0, int(max_operations))
    except Exception:
        limit = 5
    if limit == 0:
        return

    rendered: list[str] = []
    previous_tool = object()
    lang = _normalize_feishu_language(language)
    for operation in operations:
        tool_key = operation.tool_name or operation.event_type
        if mode == "new" and tool_key == previous_tool:
            continue
        previous_tool = tool_key
        line = _feishu_operation_line(operation, emoji=emoji, language=lang)
        if line:
            rendered.append(line)

    for line in rendered[-limit:]:
        yield line


def _feishu_operation_line(operation: ProgressOperation, *, emoji: bool, language: str = "zh") -> str:
    lang = _normalize_feishu_language(language)
    labels = _feishu_labels(lang)
    skill_name = _safe_skill_identifier_from_operation(operation)
    command_name = _safe_command_name(operation)
    tool_name = _safe_display_label(operation.tool_name, max_len=80)
    duration = _format_duration(operation.duration)

    if skill_name:
        icon = "📚 " if emoji else ""
        label = labels["skill"]
        line = f"{icon}{label}：{skill_name}" if lang == "zh" else f"{icon}{label}: {skill_name}"
    elif command_name:
        icon = "🖥️ " if emoji else ""
        label = labels["command"]
        if tool_name:
            line = f"{icon}{label}：{command_name}（{tool_name}）" if lang == "zh" else f"{icon}{label}: {command_name} ({tool_name})"
        else:
            line = f"{icon}{label}：{command_name}" if lang == "zh" else f"{icon}{label}: {command_name}"
    else:
        name = tool_name or _safe_display_label(_operation_name(operation), max_len=100) or "operation"
        icon = _operation_icon(operation, emoji=emoji)
        prefix = _operation_prefix(operation, language=lang)
        line = f"{icon}{prefix}：{name}" if lang == "zh" else f"{icon}{prefix}: {name}"

    timing_parts = _feishu_operation_timing_parts(operation, duration=duration, language=lang)
    if timing_parts:
        separator = " · "
        line = f"{line}{separator}{separator.join(timing_parts)}"
    return sanitize_for_progress(line, max_len=260)


def _operation_icon(operation: ProgressOperation, *, emoji: bool) -> str:
    if not emoji:
        return ""
    if operation.event_type.startswith("subagent"):
        return "📚 "
    return "🛠️ "


def _operation_prefix(operation: ProgressOperation, *, language: str = "zh") -> str:
    labels = _feishu_labels(language)
    if operation.event_type.startswith("subagent"):
        return labels["skill"]
    return labels["tool"]


def _feishu_operation_timing_parts(
    operation: ProgressOperation,
    *,
    duration: str,
    language: str,
) -> list[str]:
    # Render timing as a compact start-end interval (e.g. ``22:26:31 - 22:26:33``)
    # instead of separate start/end labels. Running operations use the localized
    # "in progress" marker as the interval's open end.
    labels = _feishu_labels(language)
    started_at = _format_timestamp(getattr(operation, "started_at", 0.0))
    completed_at = getattr(operation, "completed_at", None)
    ended_at = _format_timestamp(completed_at) if completed_at is not None else ""
    is_running = operation.status == "running"

    parts: list[str] = []
    if started_at and ended_at:
        parts.append(f"{started_at} - {ended_at}")
    elif started_at and is_running:
        parts.append(f"{started_at} - {labels['running']}")
    elif started_at:
        parts.append(started_at)
    elif ended_at:
        parts.append(ended_at)

    if duration:
        parts.append(f"{labels['duration']} {duration}")
    elif is_running and not started_at:
        parts.append(labels["running"])
    return parts


def _format_timestamp(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    try:
        timestamp = float(value)
    except Exception:
        return ""
    if timestamp < 0:
        return ""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
    except Exception:
        return ""


def _safe_skill_identifier_from_operation(operation: ProgressOperation) -> str | None:
    tool_name = (operation.tool_name or "").strip().lower()
    if tool_name != "skill_view":
        return None

    candidates: list[object] = [_skill_name_from_args_preview(operation.args_preview)]
    if operation.event_type == "tool.started" or operation.status == "running":
        candidates.append(operation.preview)

    for candidate in candidates:
        label = _safe_skill_identifier(candidate)
        if label:
            return label
    return None


def _skill_name_from_args_preview(args_preview: object) -> str | None:
    if not isinstance(args_preview, str) or not args_preview.strip():
        return None
    text = args_preview.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        try:
            parsed = ast.literal_eval(text)
        except Exception:
            return None
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("name")
    return value if isinstance(value, str) else None


def _safe_skill_identifier(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    label = sanitize_for_progress(value.strip(), max_len=160)
    if not label or "[REDACTED]" in label or any(ch.isspace() for ch in label):
        return None
    if "\\" in label or "?" in label or "&" in label or "=" in label:
        return None
    if label.startswith("/") or label.endswith("/") or "//" in label:
        return None
    if not _SAFE_SKILL_IDENTIFIER_RE.match(label):
        return None
    if label.startswith(_TOKEN_LIKE_SKILL_PREFIXES):
        return None
    first_segment = re.split(r"[/:]", label, maxsplit=1)[0]
    if first_segment in _PATH_LIKE_SKILL_PREFIXES:
        return None
    return label


def _safe_command_name(operation: ProgressOperation) -> str | None:
    # Only command-capable tool events can produce command/script labels. Other
    # previews can be arbitrary user/subagent prose and must not be scanned.
    tool_name = (operation.tool_name or "").strip().lower()
    if tool_name not in {"terminal"}:
        return None

    # `preview` on completed operations is often raw stdout/stderr. Derive
    # command/script names only from explicit args or from the initial running
    # preview, never from completion output.
    sources: list[str | None] = []
    if operation.args_preview:
        sources.append(operation.args_preview)
    if operation.event_type == "tool.started" or operation.status == "running":
        sources.append(operation.preview)

    for source in sources:
        text = sanitize_for_progress(source, max_len=500) if source else ""
        if not text:
            continue
        command_line = _extract_command_line_candidate(text)
        if not command_line:
            continue
        command_name = _extract_command_name_from_line(command_line)
        if command_name:
            return command_name
    return None


def _extract_command_line_candidate(text: str) -> str | None:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = ast.literal_eval(stripped)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            command = parsed.get("command")
            return command if isinstance(command, str) else None
    return stripped


def _extract_command_name_from_line(command_line: str) -> str | None:
    try:
        words = shlex.split(command_line, posix=True)
    except ValueError:
        words = [match.group(0) for match in _SHELL_WORD_RE.finditer(command_line)]
    if not words:
        return None

    index = 0
    while index < len(words) and _ENV_ASSIGNMENT_RE.match(words[index]):
        index += 1
    if index >= len(words):
        return None

    executable = words[index].replace("\\", "/").rsplit("/", 1)[-1]
    executable_label = _safe_display_label(executable, max_len=80)
    if not executable_label:
        return None

    if _looks_like_script(words[index]):
        return executable_label

    if executable_label in {"python", "python3", "node", "deno", "ruby", "bash", "sh", "zsh"}:
        script = _first_positional_script_after_interpreter(words[index + 1 :])
        return script or executable_label

    if executable_label in {"pytest", "git", "go", "npm", "npx", "pnpm", "uv", "yarn"}:
        return executable_label

    # Unknown executables are kept as generic tool labels. Do not scan their
    # arguments for script-like paths because those may be data files/secrets.
    return None


def _looks_like_script(token: str) -> bool:
    basename = token.replace("\\", "/").rsplit("/", 1)[-1]
    return bool(_SCRIPT_TOKEN_RE.fullmatch(basename))


def _first_positional_script_after_interpreter(words: list[str]) -> str | None:
    for word in words:
        if word.startswith("-"):
            # Interpreter options can consume following values. Be conservative:
            # once options are present, show only the interpreter label.
            return None
        if _looks_like_script(word):
            basename = word.replace("\\", "/").rsplit("/", 1)[-1]
            return _safe_display_label(basename, max_len=100)
        return None
    return None


def _safe_display_label(value: object, *, max_len: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    label = sanitize_for_progress(value.strip(), max_len=max_len)
    if not label or "[REDACTED]" in label or any(ch.isspace() for ch in label):
        return None
    if "/" in label or "\\" in label or "?" in label or "&" in label or "=" in label:
        return None
    if not _SAFE_LABEL_RE.match(label):
        return None
    return label


def _feishu_escape_markdown_text(text: object) -> str:
    value = str(text or "")
    value = re.sub(r"\[([^\]\n]{0,200})\]\([^)]*\)", r"\1", value)
    value = re.sub(r"<at\b[^>]*>(.*?)</at>", r"\1", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"https?://\S+", "[link]", value)
    value = sanitize_for_progress(value, max_len=500).replace("\n", " ")
    value = value.replace("<", "‹").replace(">", "›")
    for char in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!"):
        value = value.replace(char, f"\\{char}")
    return value


def _feishu_escape_url(url: str) -> str:
    return sanitize_for_progress(url, max_len=500).replace(")", "%29")


def _format_duration(duration: float | None) -> str:
    if duration is None:
        return ""
    try:
        return f"{float(duration):.2f}s"
    except Exception:
        return ""


def _safe_progress_dashboard_url(url: str | None) -> str | None:
    """Return a sanitized absolute dashboard /progress URL or None.

    Dashboard URLs can point at a protected local server. Never echo query
    strings, fragments, or userinfo back into chat because those are common
    places for session tokens and reverse-proxy secrets.
    """

    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parsed = urlsplit(url.strip())
    except Exception:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None

    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    netloc = host
    if port is not None:
        netloc = f"{netloc}:{port}"
    path = parsed.path.rstrip("/")
    if not path.endswith("/progress"):
        path = f"{path}/progress" if path else "/progress"
    safe = urlunsplit((parsed.scheme, netloc, path, "", ""))
    return sanitize_for_progress(safe, max_len=500)


def _cap_panel(text: str, max_length: int) -> str:
    try:
        max_length = int(max_length)
    except Exception:
        max_length = _DEFAULT_MAX_LENGTH
    if max_length <= 0:
        return ""
    if len(text) <= max_length:
        return text
    suffix = "\n…"
    if max_length <= len(suffix):
        return "…"[:max_length]
    return text[: max_length - len(suffix)] + suffix
