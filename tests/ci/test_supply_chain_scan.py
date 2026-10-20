"""scripts/ci/supply_chain_scan.py on real temp git repos: dangerous added lines fail, and only an
exactly acknowledged line (path, file blob, line hash, count) passes.

The payloads are assembled from pieces so that no line of this file is itself a hit.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ci" / "supply_chain_scan.py"
sys.path.insert(0, str(SCRIPT.parent))

import supply_chain_scan as scs

_DECODE = "base64." + "b64decode"
_EXEC = "ex" + "ec"
_RUN = "subprocess." + "run"
# The litellm shape: an opaque blob decoded and executed at import time from a .pth file.
PTH_PAYLOAD = f"import base64;{_EXEC}({_DECODE}('aW1wb3J0IG9zLHVybGxpYi5yZXF1ZXN0'))\n"
LAUNCHER_LINE = f'code = f"import base64; {_EXEC}({_DECODE}(\'{{encoded}}\'))"'


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return env


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, env=_env(), capture_output=True, text=True, encoding="utf-8",
                          stdin=subprocess.DEVNULL, timeout=60, check=False)
    assert proc.returncode == 0, (args, proc.stderr)
    return proc.stdout.strip()


def _commit(repo: Path, files: dict[str, str | None]) -> str:
    for rel, text in files.items():
        if text is None:
            _git(repo, "rm", "-q", "--", rel)
            continue
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
        _git(repo, "add", "--", rel)
    _git(repo, "commit", "-q", "--allow-empty", "-m", "step")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _commit(root, {"pkg/launch.py": "def launch():\n    return None\n"})
    return root


def _scan(repo: Path, base: str, head: str, tmp_path: Path) -> tuple[int, str, str]:
    findings = tmp_path / "findings.md"
    findings.unlink(missing_ok=True)
    proc = subprocess.run([sys.executable, str(SCRIPT), "--base", base, "--head", head,
                           "--findings", str(findings)], cwd=repo, env=_env(), capture_output=True,
                          text=True, encoding="utf-8", stdin=subprocess.DEVNULL, timeout=120, check=False)
    return proc.returncode, proc.stdout, findings.read_text(encoding="utf-8-sig") if findings.exists() else ""


def _acknowledge(repo: Path, head: str, path: str, line: str, count: int = 1) -> dict:
    return {"path": path, "blob": _git(repo, "rev-parse", f"{head}:{path}"),
            "line_sha256": hashlib.sha256(line.encode()).hexdigest(), "count": count,
            "class": "trusted generated launcher", "reason": "reviewed"}


def _with_record(repo: Path, entries: list[dict]) -> str:
    return _commit(repo, {scs.ACKNOWLEDGED: json.dumps({"acknowledged": entries})})


def test_litellm_style_payload_fails_with_the_critical_report(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, {"pkg/evil.pth": PTH_PAYLOAD})
    code, out, findings = _scan(repo, base, head, tmp_path)
    assert code == 1, out
    assert "[UNACKNOWLEDGED] b64-exec pkg/evil.pth" in out
    assert "CRITICAL: base64 decode + exec/eval combo" in findings and "pkg/evil.pth: +" in findings


@pytest.mark.parametrize("line", [
    f"{_RUN}(['sh', '-c', chr(99) + chr(117) + 'rl evil'])\n",
    f"{_RUN}(['bash', '-c', '\\x63\\x75\\x72\\x6c'])\n",
    f"{_RUN}(base64.b64decode(blob).split())\n",
])
def test_encoded_subprocess_command_fails(repo, tmp_path, line):
    base = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, {"pkg/run.py": "import base64, subprocess\n" + line})
    code, out, findings = _scan(repo, base, head, tmp_path)
    assert code == 1, out
    assert "CRITICAL: subprocess with encoded/obfuscated command" in findings


def test_exactly_acknowledged_line_passes_and_stays_visible(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    added = _commit(repo, {"pkg/launch.py": f"def launch():\n    {LAUNCHER_LINE}\n"})
    head = _with_record(repo, [_acknowledge(repo, added, "pkg/launch.py", f"    {LAUNCHER_LINE}")])
    code, out, findings = _scan(repo, base, head, tmp_path)
    assert code == 0, out
    assert "[acknowledged: trusted generated launcher — reviewed] b64-exec pkg/launch.py" in out
    assert "1 hit(s), 1 acknowledged, 0 unacknowledged" in out and findings == ""


def test_acknowledged_line_in_another_file_fails(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    added = _commit(repo, {"pkg/launch.py": f"def launch():\n    {LAUNCHER_LINE}\n",
                           "pkg/other.py": f"def other():\n    {LAUNCHER_LINE}\n"})
    head = _with_record(repo, [_acknowledge(repo, added, "pkg/launch.py", f"    {LAUNCHER_LINE}")])
    code, out, _ = _scan(repo, base, head, tmp_path)
    assert code == 1 and "[UNACKNOWLEDGED] b64-exec pkg/other.py" in out, out


def test_acknowledgement_lapses_when_the_file_changes_elsewhere(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    added = _commit(repo, {"pkg/launch.py": f"def launch():\n    {LAUNCHER_LINE}\n"})
    entry = _acknowledge(repo, added, "pkg/launch.py", f"    {LAUNCHER_LINE}")
    _with_record(repo, [entry])
    head = _commit(repo, {"pkg/launch.py": f"import os\n\n\ndef launch():\n    {LAUNCHER_LINE}\n"})
    code, out, _ = _scan(repo, base, head, tmp_path)
    assert code == 1 and "[UNACKNOWLEDGED] b64-exec pkg/launch.py" in out, out


def test_an_extra_copy_beyond_the_acknowledged_count_fails(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    added = _commit(repo, {"pkg/launch.py": f"def launch():\n    {LAUNCHER_LINE}\n    {LAUNCHER_LINE}\n"})
    head = _with_record(repo, [_acknowledge(repo, added, "pkg/launch.py", f"    {LAUNCHER_LINE}", count=1)])
    code, out, _ = _scan(repo, base, head, tmp_path)
    assert code == 1 and "2 hit(s), 1 acknowledged, 1 unacknowledged" in out, out


def test_lockfiles_and_removed_lines_are_not_scanned(repo, tmp_path):
    base = _commit(repo, {"pkg/old.py": PTH_PAYLOAD})
    head = _commit(repo, {"pkg/old.py": None, "uv.lock": PTH_PAYLOAD, "package-lock.json": PTH_PAYLOAD,
                          "web/yarn.lock": PTH_PAYLOAD})
    code, out, _ = _scan(repo, base, head, tmp_path)
    assert code == 0 and "0 hit(s)" in out, out


def test_an_unknown_revision_is_an_error_not_a_pass(repo, tmp_path):
    head = _git(repo, "rev-parse", "HEAD")
    code, _, _ = _scan(repo, "0" * 40, head, tmp_path)
    assert code == 2


def test_committed_record_names_exact_blobs_and_lines():
    record = json.loads((REPO / scs.ACKNOWLEDGED).read_text(encoding="utf-8-sig"))["acknowledged"]
    assert len(record) == 5 and sum(e["count"] for e in record) == 5
    assert {e["class"] for e in record} == {"trusted generated launcher", "trusted generated snippet", "test fixture"}
    for entry in record:
        assert re.fullmatch(r"[0-9a-f]{40}", entry["blob"]) and re.fullmatch(r"[0-9a-f]{64}", entry["line_sha256"])
        assert entry["path"] and entry["reason"]
