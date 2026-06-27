"""CLI for the P6-B Stage-2 host-local DoR / crash-no-relaunch proof.

Produces a sanitized JSON evidence bundle under an out-of-repo evidence root and
prints a sanitized summary. It never launches a real agent, real smoke, Gateway,
Feishu, network, or live surface.

On this host, with no acpx binary / role overlay provided, it completes as a
controlled ``blocked`` evidence report (exit 0) — it does not error and does not
launch. The optional ``--probe`` path runs an **argv-list / no-shell** version
probe against the operator-supplied binary; only pass it for an
operator-pinned local executable (tests pass a temp fake executable). This host
currently has no acpx on PATH.

Usage (controlled BLOCKED default on this host)::

    python tools/p6b_host_local_dor.py \
        --enabled --approval-token <exact token> \
        --evidence-root /out/of/repo/evidence

Usage (pin + probe an operator-supplied local executable)::

    python tools/p6b_host_local_dor.py \
        --enabled --approval-token <exact token> \
        --role-key sachima.claude.read_only_reviewer \
        --role-overlay-path /out/of/repo/role_overlay.json \
        --role-overlay-digest sha256:... \
        --acpx-binary /opt/.../acpx --acpx-version 0.10.0 \
        --acpx-binary-sha256 sha256:... \
        --evidence-root /out/of/repo/evidence \
        --artifact-sink-root /out/of/repo/sink \
        --probe
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Sequence

from sachima_supervisor.p6b_host_local_dor import (
    P6BHostLocalDorRequest,
    assess_p6b_host_local_dor,
    write_p6b_host_local_dor_evidence,
)

#: Bounded single-line probe budget. Anything larger is treated as unusable.
_PROBE_TIMEOUT_SECONDS = 5.0
_PROBE_TEXT_MAX_CHARS = 256


def default_acpx_version_probe(
    binary_path: str, *, timeout_seconds: float = _PROBE_TIMEOUT_SECONDS
) -> str:
    """Read a single sanitized version line via an argv-list / no-shell call.

    Runs ``[binary_path, "--version"]`` with ``shell=False`` (no interpolation,
    no PATH lookup of a launcher, no network) and returns the first non-empty
    line, bounded. The downstream provenance verifier re-screens the text and
    fails closed on anything unsafe or version-mismatched.
    """

    completed = subprocess.run(  # noqa: S603 - argv list, shell=False, bounded, no network
        [binary_path, "--version"],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        shell=False,
        check=False,
    )
    raw = completed.stdout or completed.stderr or ""
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_PROBE_TEXT_MAX_CHARS]
    return ""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="p6b_host_local_dor",
        description="P6-B Stage-2 host-local DoR / crash-no-relaunch proof (no real agent launch).",
    )
    parser.add_argument("--enabled", action="store_true", help="Arm the DoR (default off).")
    parser.add_argument("--approval-token", default="", help="Exact P6-B Stage-2 DoR approval token.")
    parser.add_argument("--role-key", default=None, help="Read-only controlled role key.")
    parser.add_argument("--role-overlay-path", default=None, help="Out-of-repo role overlay JSON path.")
    parser.add_argument("--role-overlay-digest", default=None, help="Expected sha256 of the role overlay.")
    parser.add_argument("--acpx-binary", default=None, help="Operator-pinned absolute local acpx path.")
    parser.add_argument("--acpx-version", default=None, help="Pinned acpx version (must be 0.10.0).")
    parser.add_argument("--acpx-binary-sha256", default=None, help="Expected sha256 of the acpx binary.")
    parser.add_argument("--evidence-root", default=None, help="Out-of-repo evidence root to write JSON into.")
    parser.add_argument("--artifact-sink-root", default=None, help="Out-of-repo artifact sink root.")
    parser.add_argument("--repo-root", default=None, help="Repo root for the outside-repo check (auto-detected).")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Run the argv-list/no-shell version probe against --acpx-binary (temp fake only).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    request = P6BHostLocalDorRequest(
        enabled=args.enabled,
        approval_token=args.approval_token,
        role_key=args.role_key,
        role_overlay_path=args.role_overlay_path,
        role_overlay_digest=args.role_overlay_digest,
        acpx_binary=args.acpx_binary,
        acpx_version=args.acpx_version,
        acpx_binary_sha256=args.acpx_binary_sha256,
        evidence_root=args.evidence_root,
        artifact_sink_root=args.artifact_sink_root,
    )
    version_probe = default_acpx_version_probe if args.probe else None
    report = assess_p6b_host_local_dor(
        request, repo_root=args.repo_root, version_probe=version_probe
    )
    projection = report.to_projection()

    if args.evidence_root is not None:
        out_path = write_p6b_host_local_dor_evidence(
            report, evidence_root=args.evidence_root, repo_root=args.repo_root
        )
        print(f"evidence_written: {out_path}")

    print(
        json.dumps(
            {
                "status": projection["status"],
                "runner_pinning_status": projection["runner_pinning_status"],
                "crash_proof_status": projection["crash_proof_status"],
                "blockers": projection["blockers"],
                "limitation": projection["limitation"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
