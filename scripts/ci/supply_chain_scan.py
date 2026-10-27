#!/usr/bin/env python3
"""Scan the lines a PR adds for critical supply-chain patterns (supply-chain-audit.yml).

Two narrow, high-signal patterns, on the added lines of ``git diff BASE...HEAD`` (lockfiles
excluded), the same ones the workflow grepped for inline:

* a base64 decode and an exec/eval call on the same line (the litellm payload shape);
* a ``subprocess`` call whose line carries base64, ``\\x..`` escapes or ``chr(``.

Every hit is printed. A hit passes only when ``.github/supply-chain-acknowledged.json`` names it
exactly: the path, the git blob of that file at HEAD, the sha256 of the added line, and how many
times the line may appear. Edit the file, copy the line elsewhere or add another copy, and it is
a finding again. The record is CODEOWNERS-reviewed (/.github/).

    python scripts/ci/supply_chain_scan.py --base BASE --head HEAD [--findings FILE]

Exit codes: 0 = no unacknowledged hit, 1 = at least one, 2 = git or usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ACKNOWLEDGED = ".github/supply-chain-acknowledged.json"
_EXCLUDES = (":!uv.lock", ":!*.lock", ":!package-lock.json", ":!yarn.lock")
_B64 = re.compile(r"base64\.(b64decode|decodebytes|urlsafe_b64decode)", re.IGNORECASE)
_EXEC = re.compile(r"exec\(|eval\(", re.IGNORECASE)
_SUBPROCESS = re.compile(r"subprocess\.(Popen|call|run)\s*\(")
_ENCODED = re.compile(r"base64|\\x[0-9a-f]{2}|chr\(", re.IGNORECASE)
_KINDS = {
    "b64-exec": ("base64 decode + exec/eval combo",
                 "Base64-decoded strings passed directly to exec/eval — the signature of hidden "
                 "credential-stealing payloads."),
    "subprocess-encoded": ("subprocess with encoded/obfuscated command",
                           "Subprocess calls whose command strings are base64- or hex-encoded are a "
                           "strong indicator of payload execution."),
}


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Hit:
    kind: str
    path: str
    text: str  # the added line, without its leading "+"

    @property
    def line_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8", "surrogateescape")).hexdigest()


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", errors="surrogateescape",
                          stdin=subprocess.DEVNULL, timeout=600, check=False)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def find_hits(diff: str) -> list[Hit]:
    """Every added line of ``diff`` that matches a pattern, with the path it was added to."""
    hits: list[Hit] = []
    path = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        if not line.startswith("+"):
            continue
        if _B64.search(line) and _EXEC.search(line):
            hits.append(Hit("b64-exec", path, line[1:]))
        if _SUBPROCESS.search(line) and _ENCODED.search(line):
            hits.append(Hit("subprocess-encoded", path, line[1:]))
    return hits


def _head_blobs(repo: Path, head: str, paths: set[str]) -> dict[str, str]:
    blobs: dict[str, str] = {}
    for path in sorted(paths):
        out = _git(repo, "ls-tree", "-z", head, "--", path).rstrip("\0")
        if out:  # "<mode> <type> <sha>\t<path>"
            blobs[path] = out.split("\t", 1)[0].split()[2]
    return blobs


def judge(hits: list[Hit], record: list[dict], blobs: dict[str, str]) -> list[tuple[Hit, dict | None]]:
    """Pair each hit with the record entry that acknowledges it, or None."""
    budget = Counter()
    entries: dict[tuple[str, str, str], dict] = {}
    for entry in record:
        key = (entry["path"], entry["blob"], entry["line_sha256"])
        budget[key] += int(entry["count"])
        entries[key] = entry
    judged: list[tuple[Hit, dict | None]] = []
    for hit in hits:
        key = (hit.path, blobs.get(hit.path, ""), hit.line_sha256)
        if budget[key] > 0:
            budget[key] -= 1
            judged.append((hit, entries[key]))
        else:
            judged.append((hit, None))
    return judged


def load_record(repo: Path, head: str) -> list[dict]:
    """The acknowledgements as HEAD holds them (none when HEAD has no record)."""
    try:
        text = _git(repo, "show", f"{head}:{ACKNOWLEDGED}")
    except GitError:
        return []
    return json.loads(text)["acknowledged"]


def findings_markdown(open_hits: list[Hit]) -> str:
    parts = []
    for kind, (title, why) in _KINDS.items():
        lines = [f"{h.path}: +{h.text}" for h in open_hits if h.kind == kind]
        if lines:
            body = "\n".join(lines)
            parts.append(f"### 🚨 CRITICAL: {title}\n{why}\n\n**Matches:**\n```\n{body}\n```\n")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--findings", type=Path, help="write the unacknowledged hits here (markdown)")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    try:
        diff = _git(repo, "diff", f"{args.base}...{args.head}", "--", ".", *_EXCLUDES)
        hits = find_hits(diff)
        judged = judge(hits, load_record(repo, args.head), _head_blobs(repo, args.head, {h.path for h in hits}))
    except GitError as exc:
        print(f"supply_chain_scan: {exc}", file=sys.stderr)
        return 2
    for hit, entry in judged:
        verdict = f"acknowledged: {entry['class']} — {entry['reason']}" if entry else "UNACKNOWLEDGED"
        print(f"[{verdict}] {hit.kind} {hit.path}: +{hit.text}")
    open_hits = [hit for hit, entry in judged if entry is None]
    print(f"supply_chain_scan: {len(hits)} hit(s), {len(hits) - len(open_hits)} acknowledged, "
          f"{len(open_hits)} unacknowledged")
    if not open_hits:
        return 0
    if args.findings:
        args.findings.write_text(findings_markdown(open_hits), encoding="utf-8")
    return 1


if __name__ == "__main__":
    sys.exit(main())
