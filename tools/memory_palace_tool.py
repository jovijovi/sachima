#!/usr/bin/env python3
"""Profile-scoped memory palace tools.

This module exposes narrow file operations for a profile's memory palace.  It is
not a general filesystem tool: every operation is rooted under the active
``HERMES_HOME`` and defaults to ``$HERMES_HOME/memories/palace``.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from hermes_constants import get_hermes_home
from tools.registry import registry
from utils import atomic_replace

_DEFAULT_CONFIG = {
    "root": "memories/palace",
    "mode": "read_write",
    "allowed_extensions": [".md"],
    "max_file_bytes": 32_768,
    "max_output_chars": 12_000,
    "backups": True,
    "allow_absolute_root": False,
    "scan": {
        "secrets": True,
        "prompt_injection": True,
    },
}

_SECRET_SHAPED_RE = re.compile(
    r"(?i)\b("
    r"api[_-]?key|token|secret|password|authorization|bearer|oauth|"
    r"webhook[_-]?secret|app[_-]?secret|client[_-]?secret"
    r")\b\s*[:=]\s*\S+"
)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _error(message: str, **extra: Any) -> str:
    payload = {"success": False, "error": message}
    payload.update(extra)
    return _json(payload)


def _load_config() -> dict[str, Any]:
    cfg = dict(_DEFAULT_CONFIG)
    cfg["scan"] = dict(_DEFAULT_CONFIG["scan"])

    config_path = get_hermes_home() / "config.yaml"
    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            section = raw.get("memory_palace") if isinstance(raw, dict) else None
            if isinstance(section, dict):
                for key, value in section.items():
                    if key == "scan" and isinstance(value, dict):
                        cfg["scan"].update(value)
                    else:
                        cfg[key] = value
        except Exception:
            # Config errors should not expose arbitrary filesystem access.
            pass

    if not isinstance(cfg.get("allowed_extensions"), list):
        cfg["allowed_extensions"] = [".md"]
    cfg["allowed_extensions"] = [str(ext) for ext in cfg["allowed_extensions"]]
    try:
        cfg["max_file_bytes"] = int(cfg.get("max_file_bytes") or 32_768)
    except (TypeError, ValueError):
        cfg["max_file_bytes"] = 32_768
    try:
        cfg["max_output_chars"] = int(cfg.get("max_output_chars") or 12_000)
    except (TypeError, ValueError):
        cfg["max_output_chars"] = 12_000
    return cfg


def _palace_root(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or _load_config()
    home = get_hermes_home().resolve()
    root_value = str(cfg.get("root") or "memories/palace").strip()
    root_path = Path(root_value)
    if root_path.is_absolute():
        if not bool(cfg.get("allow_absolute_root", False)):
            raise ValueError("memory_palace.root must be relative to HERMES_HOME unless allow_absolute_root is true")
        root = root_path.resolve()
        try:
            root.relative_to(home)
        except ValueError as exc:
            raise ValueError("absolute memory_palace.root must remain inside HERMES_HOME") from exc
        return root
    return (home / root_path).resolve()


def _safe_relative_path(path: str) -> Path:
    value = str(path or "").strip()
    if not value:
        raise ValueError("path is required")
    rel = Path(value)
    if rel.is_absolute():
        raise ValueError("absolute paths are not allowed")
    if any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError("path traversal is not allowed")
    return rel


def _resolve_target(path: str, *, must_exist: bool = False) -> tuple[Path, Path, dict[str, Any]]:
    cfg = _load_config()
    root = _palace_root(cfg)
    rel = _safe_relative_path(path)
    allowed = set(cfg.get("allowed_extensions") or [".md"])
    if rel.suffix not in allowed:
        raise ValueError(f"only these extensions are allowed: {', '.join(sorted(allowed))}")

    root.mkdir(parents=True, exist_ok=True)
    target = root / rel
    if must_exist and not target.exists():
        raise FileNotFoundError(str(rel))

    # Resolve parents first so a symlinked directory cannot escape the palace.
    parent_resolved = target.parent.resolve()
    try:
        parent_resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes memory palace root") from exc

    if target.exists():
        if target.is_symlink():
            raise ValueError("symlink targets are not allowed")
        target_resolved = target.resolve()
        try:
            target_resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError("path escapes memory palace root") from exc
    else:
        target_resolved = parent_resolved / target.name

    return root, target_resolved, cfg


def _relative_label(root: Path, target: Path) -> str:
    return target.relative_to(root).as_posix()


def _check_write_mode(cfg: dict[str, Any]) -> None:
    if str(cfg.get("mode", "read_write")) != "read_write":
        raise PermissionError("memory palace is configured read-only")


def _scan_content(content: str, cfg: dict[str, Any]) -> str | None:
    raw_scan_cfg = cfg.get("scan")
    scan_cfg: dict[str, Any] = raw_scan_cfg if isinstance(raw_scan_cfg, dict) else {}
    if scan_cfg.get("secrets", True) and _SECRET_SHAPED_RE.search(content):
        return "content contains secret-shaped text"
    if scan_cfg.get("prompt_injection", True):
        try:
            from tools.threat_patterns import first_threat_message
            finding = first_threat_message(content, scope="strict")
            if finding:
                return f"content contains prompt-injection pattern: {finding}"
        except Exception:
            # If the scanner is unavailable, keep a small built-in fallback.
            if re.search(r"(?i)ignore\s+previous\s+instructions", content):
                return "content contains prompt-injection pattern"
    return None


def _atomic_text_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        atomic_replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _make_backup(target: Path, enabled: bool) -> str | None:
    if not enabled or not target.exists():
        return None
    backup = target.with_name(f"{target.name}.bak.{int(time.time())}")
    backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    return str(backup)


def palace_list(path: str = "", recursive: bool = True, task_id: str | None = None) -> str:
    """List markdown files under the active profile's memory palace."""
    try:
        cfg = _load_config()
        root = _palace_root(cfg)
        root.mkdir(parents=True, exist_ok=True)
        base = root
        if path:
            base_rel = _safe_relative_path(path)
            base = (root / base_rel).resolve()
            base.relative_to(root)
        if not base.exists():
            return _json({"success": True, "root": str(root), "files": []})
        globber = base.rglob if recursive else base.glob
        files = [
            p.relative_to(root).as_posix()
            for p in globber("*")
            if p.is_file() and not p.is_symlink() and p.suffix in set(cfg.get("allowed_extensions") or [".md"])
        ]
        return _json({"success": True, "root": str(root), "files": sorted(files)})
    except Exception as exc:
        return _error(str(exc))


def palace_read(path: str, offset: int = 1, limit: int = 500, task_id: str | None = None) -> str:
    """Read one markdown palace note with line pagination."""
    try:
        root, target, cfg = _resolve_target(path, must_exist=True)
        size = target.stat().st_size
        if size > int(cfg["max_file_bytes"]):
            return _error("file exceeds configured max_file_bytes", size=size)
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(int(offset or 1), 1)
        count = max(min(int(limit or 500), 2000), 1)
        selected = lines[start - 1:start - 1 + count]
        content = "\n".join(f"{i}|{line}" for i, line in enumerate(selected, start))
        max_chars = int(cfg["max_output_chars"])
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars]
        return _json({
            "success": True,
            "path": _relative_label(root, target),
            "content": content,
            "total_lines": len(lines),
            "truncated": truncated,
        })
    except Exception as exc:
        return _error(str(exc))


def palace_search(pattern: str, path: str = "", max_results: int = 50, task_id: str | None = None) -> str:
    """Search markdown palace notes with a regular expression."""
    try:
        cfg = _load_config()
        root = _palace_root(cfg)
        root.mkdir(parents=True, exist_ok=True)
        base = root
        if path:
            base = (root / _safe_relative_path(path)).resolve()
            base.relative_to(root)
        regex = re.compile(pattern)
        allowed = set(cfg.get("allowed_extensions") or [".md"])
        matches: list[dict[str, Any]] = []
        for note in sorted(p for p in base.rglob("*") if p.is_file() and not p.is_symlink() and p.suffix in allowed):
            if note.stat().st_size > int(cfg["max_file_bytes"]):
                continue
            for lineno, line in enumerate(note.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if regex.search(line):
                    matches.append({"path": note.relative_to(root).as_posix(), "line": lineno, "content": line})
                    if len(matches) >= int(max_results or 50):
                        return _json({"success": True, "matches": matches, "truncated": True})
        return _json({"success": True, "matches": matches, "truncated": False})
    except Exception as exc:
        return _error(str(exc))


def palace_write(path: str, content: str, overwrite: bool = True, task_id: str | None = None) -> str:
    """Create or overwrite a markdown palace note."""
    try:
        root, target, cfg = _resolve_target(path, must_exist=False)
        _check_write_mode(cfg)
        if target.exists() and not overwrite:
            return _error("file exists and overwrite=false", path=_relative_label(root, target))
        encoded = content.encode("utf-8")
        if len(encoded) > int(cfg["max_file_bytes"]):
            return _error("content exceeds configured max_file_bytes", bytes=len(encoded))
        finding = _scan_content(content, cfg)
        if finding:
            return _error(finding)
        backup = _make_backup(target, bool(cfg.get("backups", True)))
        _atomic_text_write(target, content)
        payload = {"success": True, "path": _relative_label(root, target), "bytes": len(encoded)}
        if backup:
            payload["backup"] = backup
        return _json(payload)
    except Exception as exc:
        return _error(str(exc))


def palace_patch(
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    task_id: str | None = None,
) -> str:
    """Patch a markdown palace note by replacing a string."""
    try:
        root, target, cfg = _resolve_target(path, must_exist=True)
        _check_write_mode(cfg)
        original = target.read_text(encoding="utf-8", errors="replace")
        count = original.count(old_string)
        if not old_string:
            return _error("old_string is required")
        if count == 0:
            return _error("old_string not found")
        if not replace_all and count != 1:
            return _error("old_string is not unique; pass replace_all=true to replace all", occurrences=count)
        updated = original.replace(old_string, new_string, -1 if replace_all else 1)
        encoded = updated.encode("utf-8")
        if len(encoded) > int(cfg["max_file_bytes"]):
            return _error("patched content exceeds configured max_file_bytes", bytes=len(encoded))
        finding = _scan_content(updated, cfg)
        if finding:
            return _error(finding)
        backup = _make_backup(target, bool(cfg.get("backups", True)))
        _atomic_text_write(target, updated)
        payload = {
            "success": True,
            "path": _relative_label(root, target),
            "replacements": count if replace_all else 1,
            "bytes": len(encoded),
        }
        if backup:
            payload["backup"] = backup
        return _json(payload)
    except Exception as exc:
        return _error(str(exc))


def check_memory_palace_requirements() -> bool:
    return True


_PATH_PROP = {
    "type": "string",
    "description": "Relative .md path under the active profile's memory palace, e.g. INDEX.md or domains/comfort.md. Absolute paths and ../ are rejected.",
}

PALACE_LIST_SCHEMA = {
    "name": "palace_list",
    "description": "List markdown notes in the active profile's profile-scoped memory palace.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Optional relative directory path under the palace root."},
            "recursive": {"type": "boolean", "description": "Whether to recurse into subdirectories. Default true."},
        },
        "required": [],
    },
}

PALACE_READ_SCHEMA = {
    "name": "palace_read",
    "description": "Read one markdown note from the active profile's memory palace with line pagination.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": _PATH_PROP,
            "offset": {"type": "integer", "description": "1-indexed start line. Default 1."},
            "limit": {"type": "integer", "description": "Max lines to return. Default 500, max 2000."},
        },
        "required": ["path"],
    },
}

PALACE_SEARCH_SCHEMA = {
    "name": "palace_search",
    "description": "Search markdown notes in the active profile's memory palace using a regular expression.",
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for."},
            "path": {"type": "string", "description": "Optional relative directory/file path under the palace root."},
            "max_results": {"type": "integer", "description": "Maximum matches to return. Default 50."},
        },
        "required": ["pattern"],
    },
}

PALACE_WRITE_SCHEMA = {
    "name": "palace_write",
    "description": "Create or overwrite a markdown note in the active profile's memory palace. Writes are profile-scoped and scanned for secret-shaped/prompt-injection content.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": _PATH_PROP,
            "content": {"type": "string", "description": "Complete markdown content to write."},
            "overwrite": {"type": "boolean", "description": "Allow overwriting an existing file. Default true."},
        },
        "required": ["path", "content"],
    },
}

PALACE_PATCH_SCHEMA = {
    "name": "palace_patch",
    "description": "Patch a markdown note in the active profile's memory palace by replacing text. Creates a backup when enabled.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": _PATH_PROP,
            "old_string": {"type": "string", "description": "Text to find. Must be unique unless replace_all=true."},
            "new_string": {"type": "string", "description": "Replacement text."},
            "replace_all": {"type": "boolean", "description": "Replace all occurrences instead of requiring uniqueness. Default false."},
        },
        "required": ["path", "old_string", "new_string"],
    },
}

registry.register(
    name="palace_list",
    toolset="memory_palace",
    schema=PALACE_LIST_SCHEMA,
    handler=lambda args, **kw: palace_list(path=args.get("path", ""), recursive=args.get("recursive", True), task_id=kw.get("task_id")),
    check_fn=check_memory_palace_requirements,
    emoji="🏰",
)

registry.register(
    name="palace_read",
    toolset="memory_palace",
    schema=PALACE_READ_SCHEMA,
    handler=lambda args, **kw: palace_read(path=args.get("path", ""), offset=args.get("offset", 1), limit=args.get("limit", 500), task_id=kw.get("task_id")),
    check_fn=check_memory_palace_requirements,
    emoji="🏰",
)

registry.register(
    name="palace_search",
    toolset="memory_palace",
    schema=PALACE_SEARCH_SCHEMA,
    handler=lambda args, **kw: palace_search(pattern=args.get("pattern", ""), path=args.get("path", ""), max_results=args.get("max_results", 50), task_id=kw.get("task_id")),
    check_fn=check_memory_palace_requirements,
    emoji="🏰",
)

registry.register(
    name="palace_write",
    toolset="memory_palace",
    schema=PALACE_WRITE_SCHEMA,
    handler=lambda args, **kw: palace_write(path=args.get("path", ""), content=args.get("content", ""), overwrite=args.get("overwrite", True), task_id=kw.get("task_id")),
    check_fn=check_memory_palace_requirements,
    emoji="🏰",
)

registry.register(
    name="palace_patch",
    toolset="memory_palace",
    schema=PALACE_PATCH_SCHEMA,
    handler=lambda args, **kw: palace_patch(path=args.get("path", ""), old_string=args.get("old_string", ""), new_string=args.get("new_string", ""), replace_all=args.get("replace_all", False), task_id=kw.get("task_id")),
    check_fn=check_memory_palace_requirements,
    emoji="🏰",
)
