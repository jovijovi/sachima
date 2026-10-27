"""Tests for the conflict-free contributor mapping system.

New contributor email → GitHub login mappings live as one file per email
under contributors/emails/ (additions never merge-conflict). The legacy
AUTHOR_MAP dict in scripts/releases/authors_legacy.py is frozen; authors.py
merges both at import time with the directory winning on duplicates.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from scripts.releases import authors, authors_legacy
from add_contributor import add_contributor, read_mapping_file
import audit_pr_attribution


# ── directory loader behavior ─────────────────────────────────────────


def test_loader_reads_login_from_first_noncomment_line(tmp_path):
    d = tmp_path / "emails"
    d.mkdir()
    (d / "jane@example.com").write_text("# salvage PR #1\njanedoe\n# trailing note\n")
    mapping = authors._load_contributor_dir(d)
    assert mapping == {"jane@example.com": "janedoe"}


def test_effective_map_merges_legacy_and_directory():
    # Invariant: every legacy entry survives into the effective map unless
    # shadowed by a directory entry, and the directory contributes on top.
    assert set(authors_legacy.LEGACY_AUTHOR_MAP) <= (
        set(authors.AUTHOR_MAP) | set(authors._load_contributor_dir())
    )
    for email, login in authors._load_contributor_dir().items():
        assert authors.AUTHOR_MAP[email] == login


# ── commits credited one by one (contributors/commits.tsv) ────────────


def _commit_credits() -> list[list[str]]:
    text = (REPO_ROOT / "contributors" / "commits.tsv").read_text(encoding="utf-8-sig")
    return [line.split("\t") for line in text.splitlines() if line.strip() and not line.startswith("#")]


def test_commit_credits_are_exact_rows_and_their_emails_stay_unmapped():
    # A row credits one commit to its PR's submitter. The email is not proven to be theirs, so
    # no mapping may exist for it: a mapping credits every commit with that address.
    rows = _commit_credits()
    assert rows and len({row[0] for row in rows}) == len(rows)
    for row in rows:
        assert len(row) == 4, row
        sha, email, login, pull_request = row
        assert re.fullmatch(r"[0-9a-f]{40}", sha), row
        assert "@" in email and re.fullmatch(r"[A-Za-z0-9-]+", login), row
        assert re.fullmatch(r"[\w.-]+/[\w.-]+#\d+", pull_request), row
        assert email not in authors.AUTHOR_MAP, row


def test_a_shared_placeholder_email_keeps_each_commits_own_author():
    # git's placeholder identity belongs to nobody: an older upstream commit by lekt9 uses it too.
    assert authors.resolve_author("lekt9", "you@example.com") == "lekt9"


def test_audit_mirrors_the_ci_check_for_credited_commits():
    credited = audit_pr_attribution.credited_commits()
    assert credited == {(row[0], row[1]) for row in _commit_credits()}
    sha, email = sorted(credited)[0]
    assert audit_pr_attribution.unmapped_emails([(sha, email)], credited) == []
    # Another commit with the same email is not credited by that row.
    assert audit_pr_attribution.unmapped_emails([(sha, email), ("f" * 40, email)], credited) == [email]
    assert audit_pr_attribution.unmapped_emails([("f" * 40, "new@example.org")], credited) == ["new@example.org"]
    mapped = next(iter(authors._load_contributor_dir()))
    assert audit_pr_attribution.unmapped_emails([("f" * 40, mapped)], credited) == []


# ── add_contributor.py CLI behavior ───────────────────────────────────


@pytest.fixture()
def emails_dir(tmp_path, monkeypatch):
    import add_contributor

    d = tmp_path / "contributors" / "emails"
    monkeypatch.setattr(add_contributor, "EMAILS_DIR", d)
    return d


def test_add_creates_mapping_file(emails_dir):
    rc = add_contributor("new@example.com", "newperson", "PR #999 salvage")
    assert rc == 0
    path = emails_dir / "new@example.com"
    assert path.is_file()
    assert read_mapping_file(path) == "newperson"
    assert "# PR #999 salvage" in path.read_text()


def test_add_refuses_login_conflicting_with_legacy_map(emails_dir):
    email, login = next(iter(authors_legacy.LEGACY_AUTHOR_MAP.items()))
    assert add_contributor(email, login + "x") == 1
    assert not (emails_dir / email).exists()


def test_add_accepts_legacy_consecutive_hyphen_login(emails_dir):
    # Legacy GitHub accounts with consecutive hyphens are real (Roger--Han);
    # current signup rules forbid them but existing logins remain valid.
    assert add_contributor("roger.hanhong@gmail.com", "Roger--Han") == 0
    assert (emails_dir / "roger.hanhong@gmail.com").read_text(
        encoding="utf-8"
    ).strip().endswith("Roger--Han")


def test_add_strips_at_prefix(emails_dir):
    assert add_contributor("z@z.com", "@zeta") == 0
    assert read_mapping_file(emails_dir / "z@z.com") == "zeta"


def test_cli_entrypoint_end_to_end(tmp_path):
    # Run the real script in a subprocess against a temp repo layout.
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("add_contributor.py",):
        # Explicit encoding: add_contributor.py contains UTF-8 multi-byte
        # characters (an em dash), so the locale-default read_text() raises
        # UnicodeDecodeError on non-UTF-8 Windows locales (e.g. cp950).
        (scripts / name).write_text(
            (SCRIPTS_DIR / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    # Minimal stub author map so the legacy lookup import works
    (scripts / "releases").mkdir()
    (scripts / "releases" / "authors_legacy.py").write_text("LEGACY_AUTHOR_MAP = {}\n")
    proc = subprocess.run(
        [sys.executable, str(scripts / "add_contributor.py"),
         "cli@example.com", "cliperson", "via subprocess"],
        cwd=tmp_path, capture_output=True, text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = (tmp_path / "contributors" / "emails" / "cli@example.com").read_text(encoding="utf-8")
    assert out.splitlines()[0] == "cliperson"


# ── case-insensitive filename collisions ──────────────────────────────
#
# The mapping key IS the filename, so two emails differing only in case are the
# same file on Windows and default macOS; add_contributor must refuse them.
# scripts/check-case-collisions.py enforces the repo-wide invariant in CI.


def test_add_contributor_refuses_case_collision_even_for_same_login(emails_dir, capsys):
    # Same login, different spelling: still refused — the problem is the
    # filename pair, not the login. The exact spelling is what's "present".
    emails_dir.mkdir(parents=True)
    (emails_dir / "Foo@Example.com").write_text("foouser\n")

    assert add_contributor("foo@example.com", "foouser") == 1
    assert "Foo@Example.com" in capsys.readouterr().err
    assert sorted(p.name for p in emails_dir.iterdir()) == ["Foo@Example.com"]
    # Exact-case re-add is the ordinary idempotent path.
    assert add_contributor("Foo@Example.com", "foouser") == 0


def test_case_collision_uses_casefold(emails_dir):
    # casefold, not lower: matches how macOS/Windows fold non-ASCII (ß ~ ss).
    emails_dir.mkdir(parents=True)
    (emails_dir / "strasse@example.com").write_text("someone\n")
    assert add_contributor("STRASSE@example.com", "someone") == 1
    assert add_contributor("straße@example.com", "someone") == 1
