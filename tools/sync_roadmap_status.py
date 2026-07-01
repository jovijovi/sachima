#!/usr/bin/env python3
"""Guard roadmap/current-status.md as a lean AGENT dashboard.

Historically this tool synchronized a machine-owned dynamic block containing git/GitHub
facts. That conflicts with the current-status discipline: the status document is a
project/task dashboard, not a version-control ledger. The tool is kept as a compatibility
entry point for existing workflows, but it now only detects or removes the legacy block.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

START_MARKER = "<!-- sachima-status-sync:start -->"
END_MARKER = "<!-- sachima-status-sync:end -->"
LEGACY_HEADING = "## Machine-owned dynamic status"
DEFAULT_STATUS_FILE = Path("docs/roadmap/current-status.md")


class StatusGuardError(RuntimeError):
    """Raised when the status document cannot be safely guarded."""


def strip_legacy_machine_block(document: str) -> tuple[str, bool]:
    """Remove the legacy machine-owned status block if present."""
    if START_MARKER not in document and END_MARKER not in document:
        return document, False
    if START_MARKER not in document or END_MARKER not in document:
        raise StatusGuardError("status sync markers are malformed")

    start = document.find(START_MARKER)
    end = document.find(END_MARKER)
    if end < start:
        raise StatusGuardError("status sync markers are malformed")

    block_start = document.rfind(LEGACY_HEADING, 0, start)
    if block_start == -1:
        block_start = _line_start(document, start)
    end_line = document.find("\n", end)
    block_end = len(document) if end_line == -1 else end_line + 1

    before = document[:block_start].rstrip()
    after = document[block_end:].lstrip("\n")
    if before and after:
        updated = before + "\n\n" + after
    elif before:
        updated = before + "\n"
    else:
        updated = after
    return updated, True


def has_legacy_machine_block(document: str) -> bool:
    """Return True when the old generated block is present."""
    return START_MARKER in document or END_MARKER in document or LEGACY_HEADING in document


def check_file(path: Path) -> bool:
    """Return True when the file has no legacy machine-owned status block."""
    return not has_legacy_machine_block(path.read_text(encoding="utf-8"))


def write_file(path: Path) -> bool:
    """Remove the legacy machine-owned block. Return True when changed."""
    original = path.read_text(encoding="utf-8")
    updated, changed = strip_legacy_machine_block(original)
    if changed:
        path.write_text(updated, encoding="utf-8")
    return changed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_STATUS_FILE)
    parser.add_argument("--repo", default=None, help="accepted for backwards compatibility; ignored")
    parser.add_argument("--base-branch", default=None, help="accepted for backwards compatibility; ignored")
    parser.add_argument("--base-remote", default=None, help="accepted for backwards compatibility; ignored")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail if a legacy machine block remains")
    mode.add_argument("--write", action="store_true", help="remove a legacy machine block if present")
    mode.add_argument("--print", action="store_true", help="print the guard policy")
    args = parser.parse_args(argv)

    try:
        if args.print:
            print("current-status.md is a lean task dashboard; no machine-owned git/GitHub block is rendered.")
            return 0
        if args.check:
            if check_file(args.file):
                print(f"{args.file}: no legacy machine status block")
                return 0
            print(f"{args.file}: legacy machine status block present; run with --write", file=sys.stderr)
            return 1
        changed = write_file(args.file)
        print(f"{args.file}: {'legacy machine status block removed' if changed else 'no legacy machine status block'}")
        return 0
    except (OSError, StatusGuardError) as exc:
        print(f"status guard failed: {_safe_error(exc)}", file=sys.stderr)
        return 2


def _line_start(document: str, index: int) -> int:
    previous = document.rfind("\n", 0, index)
    return 0 if previous == -1 else previous + 1


def _safe_error(exc: BaseException) -> str:
    text = str(exc)
    for marker in ("token", "secret", "password", "authorization"):
        text = text.replace(marker, "[redacted]")
    return text


if __name__ == "__main__":
    raise SystemExit(main())
