"""Text renderers for gateway transaction progress panels."""

from __future__ import annotations

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
