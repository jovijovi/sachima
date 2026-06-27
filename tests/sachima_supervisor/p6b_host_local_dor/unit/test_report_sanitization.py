"""The report / evidence projection carries only sanitized refs/digests/counts.

No raw host path, role overlay body, prompt, output, platform id, or secret may
appear in the JSON projection. Paths are hashed to digests; the projection is
leak-scan clean and serializes to canonical JSON. The explicit limitation about
the missing durable cross-process claim store is recorded.
"""

from __future__ import annotations

import json

from sachima_supervisor.p6b_host_local_dor import (
    P6B_HOST_LOCAL_DOR_LIMITATION,
    assess_p6b_host_local_dor,
)
from sachima_supervisor.p5_temporal import contracts as C

from .._support import build_request, fake_version_probe, pinned_params


def _pass_report(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    params = pinned_params(outside)
    return assess_p6b_host_local_dor(
        build_request(**params), repo_root=str(repo), version_probe=fake_version_probe()
    ), params


def test_projection_is_leak_clean(tmp_path):
    report, _ = _pass_report(tmp_path)
    projection = report.to_projection()

    assert C.scan_projection_for_leak(projection) is None


def test_projection_does_not_contain_raw_host_paths(tmp_path):
    report, params = _pass_report(tmp_path)
    projection = report.to_projection()
    blob = json.dumps(projection)

    for raw in (
        params["acpx_binary"],
        params["role_overlay_path"],
        params["evidence_root"],
        params["artifact_sink_root"],
    ):
        assert raw not in blob


def test_projection_serializes_canonically_and_records_limitation(tmp_path):
    report, _ = _pass_report(tmp_path)
    projection = report.to_projection()

    # Canonical JSON round-trips without raising.
    raw = C.canonical_json_bytes(projection)
    assert json.loads(raw)["status"] == "pass"
    assert projection["limitation"] == P6B_HOST_LOCAL_DOR_LIMITATION
    assert "durable" in projection["limitation"]


def test_blocked_report_is_also_leak_clean(tmp_path):
    report = assess_p6b_host_local_dor(build_request())
    projection = report.to_projection()

    assert C.scan_projection_for_leak(projection) is None
    assert projection["status"] == "blocked"
