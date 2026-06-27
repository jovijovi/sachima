"""Role-overlay validation: exact role/adapter/version/permissions/session/binary.

A fully-pinned read-only overlay with a pinned, non-launcher absolute binary path
passes overlay validation. A write-capable role, a launcher-basename binary, a
relative binary, a digest mismatch, a wrong adapter, a wrong acpx version, or a
non-``exec`` session strategy each fail closed with a stable code — and never
launch.
"""

from __future__ import annotations

import pytest

from sachima_supervisor.p6b_host_local_dor import (
    P6B_DOR_ROLE_OVERLAY_DIGEST_MISMATCH,
    P6B_DOR_ROLE_OVERLAY_INVALID,
    P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED,
    assess_p6b_host_local_dor,
)

from .._support import build_request, pinned_params


def _assess(tmp_path, *, params_kwargs=None, request_overrides=None):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    params = pinned_params(outside, **(params_kwargs or {}))
    if request_overrides:
        params.update(request_overrides)
    return assess_p6b_host_local_dor(build_request(**params), repo_root=str(repo))


def test_pinned_read_only_overlay_passes_overlay_validation(tmp_path):
    report = _assess(tmp_path)

    # Without an injected probe the binary identity is not re-verified, but the
    # overlay shape itself is valid: no overlay/provenance blockers.
    assert P6B_DOR_ROLE_OVERLAY_INVALID not in report.blockers
    assert P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED not in report.blockers
    assert report.checks["role_overlay_valid"] == "pass"
    assert report.crash_proof_status == "pass"
    assert report.crash_proof["supervisor_launch_count"] == 0


def test_write_capable_role_fails_closed(tmp_path):
    report = _assess(
        tmp_path, params_kwargs={"overlay_overrides": {"permissions": {"write": True}}}
    )

    assert report.status == "failed"
    assert P6B_DOR_ROLE_OVERLAY_INVALID in report.blockers
    assert report.checks["role_overlay_valid"] == "fail"


@pytest.mark.parametrize(
    "permission",
    ["execute", "terminal", "delete", "move", "fetch", "switch_mode", "other"],
)
def test_any_dangerous_permission_true_fails_closed(tmp_path, permission):
    report = _assess(
        tmp_path,
        params_kwargs={"overlay_overrides": {"permissions": {permission: True}}},
    )

    assert report.status == "failed"
    assert P6B_DOR_ROLE_OVERLAY_INVALID in report.blockers


def test_read_or_search_false_fails_closed(tmp_path):
    report = _assess(
        tmp_path, params_kwargs={"overlay_overrides": {"permissions": {"read": False}}}
    )

    assert report.status == "failed"
    assert P6B_DOR_ROLE_OVERLAY_INVALID in report.blockers


def test_wrong_adapter_fails_closed(tmp_path):
    report = _assess(
        tmp_path,
        params_kwargs={"overlay_overrides": {"runner": {"adapter_agent": "codex"}}},
    )

    assert report.status == "failed"
    assert P6B_DOR_ROLE_OVERLAY_INVALID in report.blockers


def test_wrong_acpx_version_fails_closed(tmp_path):
    report = _assess(
        tmp_path,
        params_kwargs={"overlay_overrides": {"runner": {"acpx_version": "0.9.0"}}},
    )

    assert report.status == "failed"
    assert P6B_DOR_ROLE_OVERLAY_INVALID in report.blockers


def test_non_exec_session_strategy_fails_closed(tmp_path):
    report = _assess(
        tmp_path,
        params_kwargs={"overlay_overrides": {"session": {"strategy": "persistent"}}},
    )

    assert report.status == "failed"
    assert P6B_DOR_ROLE_OVERLAY_INVALID in report.blockers


def test_unknown_role_key_fails_closed(tmp_path):
    report = _assess(
        tmp_path,
        params_kwargs={"overlay_overrides": {"role_id": "sachima.claude.architect"}},
        request_overrides={"role_key": "sachima.claude.architect"},
    )

    assert report.status == "failed"
    assert P6B_DOR_ROLE_OVERLAY_INVALID in report.blockers


@pytest.mark.parametrize(
    "binary",
    [
        "/usr/local/bin/npx",  # fetch-shaped launcher basename
        "/usr/bin/node",  # interpreter launcher basename
        "relative/acpx",  # not absolute
        "/opt/with space/acpx",  # whitespace in path
    ],
)
def test_launcher_or_unpinned_binary_fails_provenance(tmp_path, binary):
    report = _assess(
        tmp_path, params_kwargs={"binary_path": binary, "make_binary": False}
    )

    assert report.status == "failed"
    assert P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED in report.blockers


def test_role_overlay_digest_mismatch_fails_closed(tmp_path):
    report = _assess(
        tmp_path, params_kwargs={"role_overlay_digest": "sha256:" + "0" * 64}
    )

    assert report.status == "failed"
    assert P6B_DOR_ROLE_OVERLAY_DIGEST_MISMATCH in report.blockers


def test_request_binary_diverges_from_overlay_fails_provenance(tmp_path):
    # Overlay pins one path; the request claims a different one -> provenance miss.
    report = _assess(
        tmp_path, request_overrides={"acpx_binary": "/opt/elsewhere/acpx"}
    )

    assert report.status == "failed"
    assert P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED in report.blockers


def test_request_acpx_version_pin_mismatch_fails_without_probe(tmp_path):
    report = _assess(tmp_path, request_overrides={"acpx_version": "0.9.0"})

    assert report.status == "failed"
    assert report.runner_pinning_status == "failed"
    assert P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED in report.blockers
    assert report.checks["binary_version_pin"] == "fail"


def test_request_acpx_sha_pin_malformed_fails_without_probe(tmp_path):
    report = _assess(tmp_path, request_overrides={"acpx_binary_sha256": "not-a-sha"})

    assert report.status == "failed"
    assert report.runner_pinning_status == "failed"
    assert P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED in report.blockers
    assert report.checks["binary_sha_pin"] == "fail"
