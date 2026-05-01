"""Text renderers for gateway transaction progress panels."""

from __future__ import annotations

import ast
import re
import shlex
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

from gateway.progress.events import ProgressOperation, TransactionSnapshot
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
    "running": "⏳ 正在处理",
    "pending": "⏳ 等待中",
    "completed": "完成",
    "failed": "失败",
    "blocked": "等待确认",
    "cancelled": "已取消",
}

_FEISHU_LIVELY_TITLES = {
    "running": ("🐾", "小沙工作台 · 运行中"),
    "pending": ("🐾", "小沙准备中"),
    "completed": ("✅", "小沙收工"),
    "failed": ("⚠️", "小沙卡了一下"),
    "blocked": ("⛔", "小沙等你确认"),
    "cancelled": ("⚪", "小沙已停止"),
}

_FEISHU_NEUTRAL_TITLES = {
    "running": ("🔄", "Progress · Running"),
    "pending": ("⏳", "Progress · Pending"),
    "completed": ("✅", "Progress · Completed"),
    "failed": ("⚠️", "Progress · Failed"),
    "blocked": ("⛔", "Progress · Blocked"),
    "cancelled": ("⚪", "Progress · Cancelled"),
}

_SCRIPT_TOKEN_RE = re.compile(
    r"(?P<token>(?:[A-Za-z]:[\\/]|/|\./|\.\./|~/)?[^\s'\"`]+"
    r"\.(?:py|js|ts|tsx|jsx|sh|bash|zsh|rb|pl|php|go|rs|java|kt|scala|sql|ya?ml|json|toml|md|txt))"
)
_SHELL_WORD_RE = re.compile(r"[^\s'\"`]+")
_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+:-]{0,119}$")
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


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

    title = sanitize_for_progress(snapshot.title or "Task", max_len=160)
    status = snapshot.status or "running"
    status_icon = _STATUS_ICONS.get(status, "🔄")
    status_label = _STATUS_LABELS.get(status, status.title())

    lines = [
        f"📌 **Transaction:** {title}",
        f"{status_icon} **Status:** {status_label}",
    ]

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
) -> dict:
    """Render a sanitized Feishu interactive-card payload for task progress.

    The card intentionally shows only summary labels. It never renders raw
    command lines, argument previews, outputs, headers, tokens, or arbitrary
    metadata dumps; those remain available in backend logs/dashboard only.
    """

    mode = _normalize_progress_mode(tool_progress_mode)
    status = snapshot.status or "running"
    title = sanitize_for_progress(snapshot.title or "Task", max_len=120)
    status_label = sanitize_for_progress(_FEISHU_STATUS_LABELS.get(status, status.title()), max_len=80)

    details = [
        f"**任务：** {_feishu_escape_markdown_text(title)}",
        f"**状态：** {_feishu_escape_markdown_text(status_label)}",
    ]
    total_duration = _snapshot_duration(snapshot)
    if total_duration:
        details.append(f"**耗时：** {total_duration}")

    elements: list[dict] = [{"tag": "markdown", "content": "\n".join(details)}]

    if mode != "off":
        operation_lines = list(
            _iter_feishu_operation_lines(
                snapshot.recent_operations or (),
                mode=mode,
                max_operations=max_operations,
                emoji=emoji,
            )
        )
        elements.append(
            {
                "tag": "markdown",
                "content": "**最近动作：**\n" + ("\n".join(operation_lines) if operation_lines else "暂无动作"),
            }
        )

    elements.append({"tag": "markdown", "content": _feishu_footer_copy(status, style=style)})

    progress_link = _safe_progress_dashboard_url(dashboard_url)
    if progress_link:
        elements.append(
            {
                "tag": "markdown",
                "content": f"[打开进度面板]({_feishu_escape_url(progress_link)})",
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": _feishu_header_title(status, style=style, emoji=emoji),
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


def _feishu_header_template(status: str) -> str:
    return _FEISHU_HEADER_TEMPLATES.get(status or "running", "blue")


def _feishu_header_title(status: str, *, style: object, emoji: bool) -> str:
    titles = _FEISHU_LIVELY_TITLES if _normalize_feishu_style(style) == "lively" else _FEISHU_NEUTRAL_TITLES
    icon, text = titles.get(status or "running", titles["running"])
    content = f"{icon} {text}" if emoji else text
    return sanitize_for_progress(content, max_len=80)


def _feishu_footer_copy(status: str, *, style: object) -> str:
    lively = _normalize_feishu_style(style) == "lively"
    if status == "failed":
        text = "详情已记录，不刷屏。" if lively else "Details are recorded without showing raw output here."
    elif status == "completed":
        text = "完整调用链已记录，飞书只显示摘要。" if lively else "Full trace recorded; this card shows a summary only."
    elif status == "cancelled":
        text = "任务已停止，详情已记录。" if lively else "Task stopped; details are recorded."
    else:
        text = "完整调用链已记录，飞书只显示摘要。" if lively else "Full trace is recorded; this card shows a summary only."
    return sanitize_for_progress(text, max_len=160)


def _snapshot_duration(snapshot: TransactionSnapshot) -> str:
    if snapshot.completed_at is None or not snapshot.started_at:
        return ""
    try:
        elapsed = float(snapshot.completed_at) - float(snapshot.started_at)
    except Exception:
        return ""
    if elapsed < 0:
        return ""
    return _format_duration(elapsed)


def _iter_feishu_operation_lines(
    operations: Iterable[ProgressOperation],
    *,
    mode: str,
    max_operations: int,
    emoji: bool,
) -> Iterable[str]:
    try:
        limit = max(0, int(max_operations))
    except Exception:
        limit = 5
    if limit == 0:
        return

    rendered: list[str] = []
    previous_tool = object()
    for operation in operations:
        tool_key = operation.tool_name or operation.event_type
        if mode == "new" and tool_key == previous_tool:
            continue
        previous_tool = tool_key
        line = _feishu_operation_line(operation, emoji=emoji)
        if line:
            rendered.append(line)

    for line in rendered[-limit:]:
        yield line


def _feishu_operation_line(operation: ProgressOperation, *, emoji: bool) -> str:
    command_name = _safe_command_name(operation)
    tool_name = _safe_display_label(operation.tool_name, max_len=80)
    duration = _format_duration(operation.duration)

    if command_name:
        icon = "🖥️ " if emoji else ""
        if tool_name:
            line = f"{icon}命令：{command_name}（{tool_name}）"
        else:
            line = f"{icon}命令：{command_name}"
    else:
        name = tool_name or _safe_display_label(_operation_name(operation), max_len=100) or "operation"
        icon = _operation_icon(operation, emoji=emoji)
        prefix = _operation_prefix(operation)
        line = f"{icon}{prefix}：{name}"

    if duration:
        line = f"{line}（{duration}）"
    return sanitize_for_progress(line, max_len=180)


def _operation_icon(operation: ProgressOperation, *, emoji: bool) -> str:
    if not emoji:
        return ""
    if operation.event_type.startswith("subagent"):
        return "📚 "
    return "🛠️ "


def _operation_prefix(operation: ProgressOperation) -> str:
    if operation.event_type.startswith("subagent"):
        return "技能"
    return "工具"


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
