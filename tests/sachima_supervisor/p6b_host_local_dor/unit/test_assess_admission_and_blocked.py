"""Admission + default-off / scope-widen / runner-missing BLOCKED behavior.

Default-off, an approval-token mismatch, or any ``allow_*`` scope-widen flag must
fail closed as a controlled ``blocked`` report with **no** crash proof and **no**
launch. With admission satisfied but the exact runner parameters absent, the DoR
must still report a controlled ``blocked`` runner-pinning status while running the
fail-closed crash proof with a zero supervisor launch count.
"""

from __future__ import annotations

from sachima_supervisor.p6b_host_local_dor import (
    P6B_DOR_APPROVAL_MISMATCH,
    P6B_DOR_DISABLED,
    P6B_DOR_RUNNER_PARAMS_MISSING,
    P6B_DOR_SCOPE_WIDENED,
    assess_p6b_host_local_dor,
)

from .._support import build_request, pinned_params


def test_default_off_is_blocked_with_no_crash_proof():
    report = assess_p6b_host_local_dor(build_request(enabled=False))

    assert report.status == "blocked"
    assert report.approval_ok is False
    assert P6B_DOR_DISABLED in report.blockers
    assert report.crash_proof_status == "skipped"
    assert report.runner_pinning_status == "not_assessed"


def test_approval_mismatch_is_blocked():
    report = assess_p6b_host_local_dor(
        build_request(approval_token="approve_" + "something_else")
    )

    assert report.status == "blocked"
    assert report.approval_ok is False
    assert P6B_DOR_APPROVAL_MISMATCH in report.blockers
    assert report.crash_proof_status == "skipped"


def test_scope_widen_allow_flag_is_blocked():
    report = assess_p6b_host_local_dor(build_request(allow_real_agent_launch=True))

    assert report.status == "blocked"
    assert report.approval_ok is True
    assert report.scope_ok is False
    assert P6B_DOR_SCOPE_WIDENED in report.blockers
    assert report.crash_proof_status == "skipped"


def test_missing_runner_params_blocked_with_zero_launch_but_crash_proof_runs():
    # Admission satisfied, but no runner parameters pinned at all (the default
    # posture on this host: no acpx binary / role overlay provided).
    report = assess_p6b_host_local_dor(build_request())

    assert report.status == "blocked"
    assert report.approval_ok is True
    assert report.scope_ok is True
    assert report.runner_pinning_status == "blocked"
    assert P6B_DOR_RUNNER_PARAMS_MISSING in report.blockers
    # The crash / no-relaunch proof is independent of runner pinning and still runs.
    assert report.crash_proof_status == "pass"
    assert report.crash_proof["supervisor_launch_count"] == 0


def test_partial_runner_params_missing_acpx_binary_is_blocked(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    params = pinned_params(outside)
    params["acpx_binary"] = None  # role overlay pinned, but no binary identity

    report = assess_p6b_host_local_dor(
        build_request(**params), repo_root=str(repo)
    )

    assert report.status == "blocked"
    assert report.runner_pinning_status == "blocked"
    assert P6B_DOR_RUNNER_PARAMS_MISSING in report.blockers
    assert report.crash_proof["supervisor_launch_count"] == 0
