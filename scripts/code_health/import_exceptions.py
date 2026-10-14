"""Findings an upstream import inherits, recorded one by one for that import.

Merging an upstream release brings code the release already shipped, and with it findings that
were not introduced by the merge. ``import_exceptions.json`` lists them exactly (path, rule,
scope, line, and where each came from) and names the base commit the import is judged against.
Only a run against exactly that base reads it, so it never reaches another PR. Each listed
finding is accepted at most as many times as it is listed and stays in the report; anything not
listed, or listed fewer times, still blocks.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from scripts.code_health.model import Finding

RECORD = Path(__file__).with_name("import_exceptions.json")


def load(path: Path = RECORD) -> dict | None:
    """The committed record, or None when this tree has none."""
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def apply_import_exceptions(findings: list[Finding], base: str, record: dict | None) -> int:
    """Mark the blocking findings ``record`` lists as inherited when judging ``base``; returns how
    many it accepted. A comment-allowed finding keeps its own reason and is never counted here."""
    if not record or record.get("base") != base:
        return 0
    budget: Counter[tuple[str, str, str, int]] = Counter()
    origin: dict[tuple[str, str, str, int], str] = {}
    for path, rule, scope, line, where in record["findings"]:
        budget[path, rule, scope, line] += 1
        origin[path, rule, scope, line] = where
    accepted = 0
    for finding in findings:
        key = (finding.path, finding.rule, finding.scope, finding.line)
        if finding.blocking and finding.allowed_reason is None and budget[key] > 0:
            budget[key] -= 1
            finding.inherited = origin[key]
            accepted += 1
    return accepted
