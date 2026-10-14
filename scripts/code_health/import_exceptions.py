"""Findings an upstream import inherits, recorded one by one for that import.

Merging an upstream release brings code the release already shipped, and with it findings that
were not introduced by the merge. ``import_exceptions.json`` lists them exactly (path, rule,
scope, line, and where each came from), the reviewed bytes of every file they sit in (git blob
ids), and the one pull request and base commit the import is judged in. Only a run of that pull
request against exactly that base reads it, so it never reaches another PR. A listed finding is
accepted only while its file still has the reviewed bytes: any edit to the file, even one that
keeps a finding at the same place, makes its findings block like any others. Each listed finding
is accepted at most as many times as it is listed and stays in the report; anything not listed,
or listed fewer times, still blocks.

The pull request is GitHub Actions' own context: ``GITHUB_REPOSITORY`` and ``GITHUB_REF``
(``refs/pull/<n>/merge``). Set both to reproduce that PR's CI run locally.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from scripts.code_health import gitio
from scripts.code_health.model import Finding

RECORD = Path(__file__).with_name("import_exceptions.json")


def load(path: Path = RECORD) -> dict | None:
    """The committed record, or None when this tree has none."""
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def pull_request() -> str | None:
    """``owner/repo#<n>`` of the pull request this GitHub Actions run judges, else None."""
    match = re.fullmatch(r"refs/pull/(\d+)/merge", os.environ.get("GITHUB_REF", ""))
    repository = os.environ.get("GITHUB_REPOSITORY")
    return f"{repository}#{match.group(1)}" if match and repository else None


def apply_import_exceptions(findings: list[Finding], repo: Path, base: str, head: str | None,
                            record: dict | None, pull_request: str | None) -> int:
    """Mark the blocking findings ``record`` lists as inherited when judging ``head`` against
    ``base`` in ``pull_request``, each only while its file at ``head`` has the reviewed blob;
    returns how many it accepted. A comment-allowed finding keeps its own reason and is never
    counted here."""
    if (not record or pull_request is None or record.get("pull_request") != pull_request
            or record.get("base") != base):
        return 0
    reviewed: dict[str, str] = record.get("files") or {}
    budget: Counter[tuple[str, str, str, int]] = Counter()
    origin: dict[tuple[str, str, str, int], str] = {}
    for path, rule, scope, line, where in record["findings"]:
        budget[path, rule, scope, line] += 1
        origin[path, rule, scope, line] = where
    listed = {f.path for f in findings if budget[f.path, f.rule, f.scope, f.line] and f.path in reviewed}
    unchanged = {path for path, blob in gitio.blob_ids(repo, head, sorted(listed)).items()
                 if blob == reviewed[path]}
    accepted = 0
    for finding in findings:
        key = (finding.path, finding.rule, finding.scope, finding.line)
        if (finding.blocking and finding.allowed_reason is None and budget[key] > 0
                and finding.path in unchanged):
            budget[key] -= 1
            finding.inherited = origin[key]
            accepted += 1
    return accepted
