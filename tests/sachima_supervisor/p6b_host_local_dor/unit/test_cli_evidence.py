"""CLI + evidence writer: out-of-repo sanitized JSON, controlled BLOCKED default.

The CLI writes a sanitized JSON evidence bundle under an out-of-repo evidence
root and never mutates the tracked repo. With no acpx binary provided (the
default posture on this host) it completes as a controlled ``blocked`` evidence
report and exits 0 rather than erroring or launching. With a temp fake executable
and ``--probe`` the argv-list/no-shell version probe pins the runner to ``pass``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sachima_supervisor.p6b_host_local_dor import (
    P6B_HOST_LOCAL_DOR_APPROVAL_TOKEN,
    REQUIRED_ACPX_VERSION,
    assess_p6b_host_local_dor,
    write_p6b_host_local_dor_evidence,
)
from sachima_supervisor.p5_temporal import contracts as C

from tools.p6b_host_local_dor import default_acpx_version_probe, main

from .._support import build_request, make_fake_acpx, pinned_params


# --------------------------------------------------------------------------- #
# Evidence writer (module-level)
# --------------------------------------------------------------------------- #
def test_evidence_writer_writes_out_of_repo_json(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    report = assess_p6b_host_local_dor(build_request(), repo_root=str(repo))

    evidence_path = write_p6b_host_local_dor_evidence(
        report, evidence_root=str(outside / "evidence"), repo_root=str(repo)
    )

    assert Path(evidence_path).is_file()
    assert str(repo) not in str(evidence_path)
    loaded = json.loads(Path(evidence_path).read_text())
    assert loaded["status"] == "blocked"
    assert C.scan_projection_for_leak(loaded) is None


def test_evidence_writer_refuses_inside_repo(tmp_path):
    repo = tmp_path / "repo"
    report = assess_p6b_host_local_dor(build_request(), repo_root=str(repo))

    with pytest.raises(ValueError):
        write_p6b_host_local_dor_evidence(
            report, evidence_root=str(repo / "evidence"), repo_root=str(repo)
        )


# --------------------------------------------------------------------------- #
# argv-list / no-shell probe against a temp fake executable
# --------------------------------------------------------------------------- #
def test_default_probe_reads_temp_fake_executable(tmp_path):
    binary = make_fake_acpx(tmp_path, version=REQUIRED_ACPX_VERSION)

    text = default_acpx_version_probe(str(binary))

    assert REQUIRED_ACPX_VERSION in text


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _argv(repo: Path, evidence_root: Path, *extra: str) -> list[str]:
    return [
        "--enabled",
        "--approval-token",
        P6B_HOST_LOCAL_DOR_APPROVAL_TOKEN,
        "--repo-root",
        str(repo),
        "--evidence-root",
        str(evidence_root),
        *extra,
    ]


def _find_evidence(evidence_root: Path) -> Path:
    files = list(evidence_root.glob("*.json"))
    assert len(files) == 1
    return files[0]


def test_cli_default_no_binary_is_blocked_and_writes_evidence(tmp_path, capsys):
    repo = tmp_path / "repo"
    evidence_root = tmp_path / "outside" / "evidence"

    rc = main(_argv(repo, evidence_root))

    assert rc == 0
    captured = capsys.readouterr().out
    assert str(evidence_root) not in captured
    assert "evidence_written_ref" in captured
    loaded = json.loads(_find_evidence(evidence_root).read_text())
    assert loaded["status"] == "blocked"
    assert loaded["crash_proof_status"] == "pass"
    assert C.scan_projection_for_leak(loaded) is None


def test_cli_full_params_with_probe_passes(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    params = pinned_params(outside)
    evidence_root = Path(params["evidence_root"])

    rc = main(
        _argv(
            repo,
            evidence_root,
            "--role-key",
            params["role_key"],
            "--role-overlay-path",
            params["role_overlay_path"],
            "--role-overlay-digest",
            params["role_overlay_digest"],
            "--acpx-binary",
            params["acpx_binary"],
            "--acpx-version",
            params["acpx_version"],
            "--acpx-binary-sha256",
            params["acpx_binary_sha256"],
            "--artifact-sink-root",
            params["artifact_sink_root"],
            "--probe",
        )
    )

    assert rc == 0
    loaded = json.loads(_find_evidence(evidence_root).read_text())
    assert loaded["status"] == "pass"
    assert loaded["runner_pinning_status"] == "pass"
    assert C.scan_projection_for_leak(loaded) is None


def test_cli_does_not_mutate_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tracked.txt").write_text("untouched\n")
    evidence_root = tmp_path / "outside" / "evidence"

    main(_argv(repo, evidence_root))

    # The only repo content is the pre-existing tracked file; evidence is outside.
    assert [p.name for p in repo.iterdir()] == ["tracked.txt"]
    assert (repo / "tracked.txt").read_text() == "untouched\n"
