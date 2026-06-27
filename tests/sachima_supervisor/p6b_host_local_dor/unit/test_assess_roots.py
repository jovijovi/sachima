"""Role overlay / evidence / artifact-sink roots must live outside the repo root.

A root resolving inside the repo fails closed (a kill criterion: the artifact
sink may never write inside the tracked worktree). Roots outside the repo pass and
are projected as path digests only — never raw host paths.
"""

from __future__ import annotations

from sachima_supervisor.p6b_host_local_dor import (
    P6B_DOR_ROOT_INSIDE_REPO,
    assess_p6b_host_local_dor,
)

from .._support import build_request, fake_version_probe, pinned_params


def test_outside_repo_roots_pass(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    params = pinned_params(outside)

    report = assess_p6b_host_local_dor(
        build_request(**params), repo_root=str(repo), version_probe=fake_version_probe()
    )

    assert P6B_DOR_ROOT_INSIDE_REPO not in report.blockers
    assert report.roots["evidence_root"]["outside_repo"] is True
    assert report.roots["artifact_sink_root"]["outside_repo"] is True
    assert report.roots["role_overlay"]["outside_repo"] is True
    # Path digests only.
    assert report.roots["evidence_root"]["path_digest"].startswith("sha256:")
    assert "path" not in report.roots["evidence_root"]


def test_evidence_root_inside_repo_fails(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    params = pinned_params(outside)
    params["evidence_root"] = str(repo / "evidence")  # inside the repo

    report = assess_p6b_host_local_dor(
        build_request(**params), repo_root=str(repo), version_probe=fake_version_probe()
    )

    assert report.status == "failed"
    assert P6B_DOR_ROOT_INSIDE_REPO in report.blockers
    assert report.roots["evidence_root"]["outside_repo"] is False


def test_artifact_sink_inside_repo_fails(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    params = pinned_params(outside)
    params["artifact_sink_root"] = str(repo / "sink")  # inside the repo

    report = assess_p6b_host_local_dor(
        build_request(**params), repo_root=str(repo), version_probe=fake_version_probe()
    )

    assert report.status == "failed"
    assert P6B_DOR_ROOT_INSIDE_REPO in report.blockers


def test_role_overlay_inside_repo_fails(tmp_path):
    repo = tmp_path / "repo"
    # Write the overlay INSIDE the repo root.
    params = pinned_params(repo)

    report = assess_p6b_host_local_dor(
        build_request(**params), repo_root=str(repo), version_probe=fake_version_probe()
    )

    assert report.status == "failed"
    assert P6B_DOR_ROOT_INSIDE_REPO in report.blockers
