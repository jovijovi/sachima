"""Optional binary version probe + sha pin, exercised with a temp fake executable.

The probe is injected (argv-list/no-shell in the CLI; a pure fake here) and must
read the pinned version as an exact standalone token from a temp fake executable
— never the real ``acpx``. A correct probe + matching binary sha pins the runner
to ``dor_pass``. A binary-sha mismatch or a wrong probe version fails closed.
"""

from __future__ import annotations

from sachima_supervisor.p6b_host_local_dor import (
    P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED,
    assess_p6b_host_local_dor,
)

from .._support import build_request, fake_version_probe, pinned_params


def _assess(tmp_path, *, probe, params_kwargs=None, request_overrides=None):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    params = pinned_params(outside, **(params_kwargs or {}))
    if request_overrides:
        params.update(request_overrides)
    return assess_p6b_host_local_dor(
        build_request(**params), repo_root=str(repo), version_probe=probe
    )


def test_temp_fake_probe_and_sha_pin_pass(tmp_path):
    report = _assess(tmp_path, probe=fake_version_probe())

    assert report.status == "pass"
    assert report.runner_pinning_status == "pass"
    assert report.blockers == ()
    assert report.checks["binary_version_probe"] == "pass"
    assert report.checks["binary_sha_pin"] == "pass"
    # Sanitized provenance: digests only, never the raw host path.
    prov = report.runner_provenance
    assert prov["acpx_version"] == "0.10.0"
    assert prov["acpx_binary_sha256"].startswith("sha256:")
    assert prov["acpx_binary_path_digest"].startswith("sha256:")
    assert report.crash_proof_status == "pass"


def test_binary_sha_mismatch_fails_closed(tmp_path):
    report = _assess(
        tmp_path,
        probe=fake_version_probe(),
        params_kwargs={"acpx_binary_sha256": "sha256:" + "1" * 64},
    )

    assert report.status == "failed"
    assert P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED in report.blockers
    assert report.checks["binary_sha_pin"] == "fail"


def test_probe_wrong_version_fails_closed(tmp_path):
    report = _assess(tmp_path, probe=fake_version_probe("acpx 0.9.0"))

    assert report.status == "failed"
    assert P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED in report.blockers
    assert report.checks["binary_version_probe"] == "fail"


def test_no_probe_leaves_version_probe_skipped_but_overlay_valid(tmp_path):
    report = _assess(tmp_path, probe=None)

    # Shape is valid; the binary identity is simply not re-verified.
    assert report.checks["binary_version_probe"] == "skipped"
    assert report.checks["role_overlay_valid"] == "pass"
    assert P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED not in report.blockers
