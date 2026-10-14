"""The upstream-import record: exactly the listed inherited findings pass, and only against its base.

Runs the real ratchet (scripts/code_health.cli.run) on tiny git repos, and checks the committed
record keeps the shape and the reviewed set it was written with.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from scripts.code_health import cli, import_exceptions
from scripts.code_health.config import METRIC_FIX, RULES_BY_ID

REPO = Path(__file__).resolve().parents[2]
_LEGACY = "def legacy(x):\n" + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(21))
_GROWN = _LEGACY + "    if x == 99:\n        return 99\n"
_SWALLOW = "def swallow():\n    try:\n        pass\n    except Exception:\n        pass\n"
_TWO_UNDEFINED = "def twice():\n    return undefined_a + undefined_b\n"


def _git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    proc = subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8",
                          stdin=subprocess.DEVNULL, timeout=60, check=False)
    assert proc.returncode == 0, (args, proc.stderr)
    return proc.stdout.strip()


def _commit(repo: Path, files: dict[str, str]) -> str:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-q", "-m", "step")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def judged(tmp_path: Path) -> tuple[Path, str, str]:
    """A base with one over-target function, and a head that adds five blocking findings."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    shutil.copy(REPO / "pyproject.toml", repo / "pyproject.toml")
    (repo / "scripts/ci").mkdir(parents=True)
    shutil.copy2(REPO / "scripts/ci/profile_scope_patterns.json", repo / "scripts/ci/")
    base = _commit(repo, {"pkg/a.py": _LEGACY})
    head = _commit(repo, {"pkg/a.py": _GROWN, "pkg/b.py": _SWALLOW, "pkg/c.py": _TWO_UNDEFINED})
    return repo, base, head


def _findings(repo: Path, base: str, head: str, capsys, record: dict | None = None) -> list[dict]:
    cli.run(repo, base, head, as_json=True, record=record or {})
    return json.loads(capsys.readouterr().out)


def _record(base: str, rows: list[dict]) -> dict:
    return {"base": base, "findings": [[r["path"], r["rule"], r["scope"], r["line"], "upstream"] for r in rows]}


def test_listed_findings_are_accepted_visibly_and_counted_apart(judged, capsys):
    repo, base, head = judged
    rows = _findings(repo, base, head, capsys)
    assert len(rows) == 5 and all(r["blocking"] for r in rows), rows
    assert cli.run(repo, base, head, record=_record(base, rows)) == 0
    out = capsys.readouterr().out
    assert "0 blocking, 0 advisory, 5 accepted as inherited from the upstream import" in out
    accepted = out.split("Accepted as inherited from the upstream import")[1]
    for r in rows:  # each accepted finding is still printed, with its measured detail
        assert f"{r['path']}:{r['line']}  {r['rule']}  {r['scope']}  -- upstream" in accepted
        assert r["detail"] in accepted
    data = _findings(repo, base, head, capsys, record=_record(base, rows))
    assert [r["inherited"] for r in data] == ["upstream"] * 5


def test_a_finding_the_record_does_not_list_still_blocks(judged, capsys):
    repo, base, head = judged
    rows = _findings(repo, base, head, capsys)
    missing = next(r for r in rows if r["rule"] == "CC")
    assert cli.run(repo, base, head, record=_record(base, [r for r in rows if r is not missing])) == 1
    out = capsys.readouterr().out
    assert "1 blocking, 0 advisory, 4 accepted" in out
    assert out.startswith(f"{missing['path']}:{missing['line']}  CC  {missing['scope']}")


def test_each_listed_finding_is_accepted_only_as_often_as_listed(judged, capsys):
    repo, base, head = judged
    rows = _findings(repo, base, head, capsys)
    twice = [r for r in rows if r["path"] == "pkg/c.py"]
    assert len(twice) == 2 and len({(r["rule"], r["scope"], r["line"]) for r in twice}) == 1
    once = [r for r in rows if r["path"] != "pkg/c.py"] + twice[:1]
    assert cli.run(repo, base, head, record=_record(base, once)) == 1
    assert "1 blocking, 0 advisory, 4 accepted" in capsys.readouterr().out


def test_the_record_is_inert_against_any_other_base(judged, capsys):
    repo, base, head = judged
    rows = _findings(repo, base, head, capsys)
    assert cli.run(repo, base, head, record=_record("0" * 40, rows)) == 1
    out = capsys.readouterr().out
    assert "5 blocking, 0 advisory (" in out and "Accepted as inherited" not in out


def test_a_comment_allowed_finding_keeps_its_reason_and_is_not_counted_as_inherited(judged, capsys):
    repo, base, _ = judged
    allowed = _SWALLOW.replace("except Exception:", "except Exception:  # health: allow BLE001 S110 -- boundary")
    head = _commit(repo, {"pkg/b.py": allowed})
    rows = _findings(repo, base, head, capsys)
    assert cli.run(repo, base, head, record=_record(base, rows)) == 0
    assert "Allowed by comment" in capsys.readouterr().out
    data = _findings(repo, base, head, capsys, record=_record(base, rows))
    by_rule = {(r["path"], r["rule"]): r for r in data}
    assert by_rule["pkg/b.py", "BLE001"]["allowed_reason"] == "boundary"
    assert by_rule["pkg/b.py", "BLE001"]["inherited"] is None
    assert Counter(r["inherited"] is not None for r in data) == Counter({True: 3, False: 2})


def test_committed_record_is_the_reviewed_v0217_import_set():
    record = import_exceptions.load()
    assert record is not None
    assert record["base"] == "6f1a8572114e77079c762f2aa4107857b9760416"
    assert record["upstream"] == "71d34bad1045610252eda02ee79549436896e784"
    rows = record["findings"]
    assert len(rows) == 1241
    assert Counter(r[4] for r in rows) == Counter({
        "upstream file, byte-identical": 1199,
        "upstream finding in a merged file": 30,
        "release/sachima finding carried from before the ratchet": 12,
    })
    for path, rule, scope, line, _ in rows:
        assert rule in RULES_BY_ID or rule in METRIC_FIX, rule
        assert isinstance(line, int) and line >= 1 and path and scope
