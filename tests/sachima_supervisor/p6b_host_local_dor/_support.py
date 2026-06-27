"""Shared builders for the P6-B Stage-2 host-local DoR / crash-no-relaunch proof.

Nothing here launches a real agent, real ``acpx``, network, Gateway, Feishu, or
any live surface. The host-local runner is represented only by an out-of-repo
**temp fake** executable (a tiny ``/bin/sh`` script that echoes a version string)
and an out-of-repo **role overlay** JSON written into a temp directory. The
committed repo roles stay null-binary and untouched.

The ``outside``/``repo`` split is fully synthetic: tests pass an explicit
``repo_root`` so the "must live outside the repo" check is hermetic and never
depends on the real worktree path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sachima_supervisor.activity_controlled_exec import (
    CONTROLLED_EXEC_ROLE_ADAPTER_AGENT,
)
from sachima_supervisor.p6b_host_local_dor import (
    P6B_HOST_LOCAL_DOR_APPROVAL_TOKEN,
    REQUIRED_ACPX_VERSION,
    P6BHostLocalDorRequest,
)

ROLE_KEY = "sachima.claude.read_only_reviewer"
ADAPTER_AGENT = CONTROLLED_EXEC_ROLE_ADAPTER_AGENT[ROLE_KEY]


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _deep_update(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_update(dict(base[key]), value)
        else:
            base[key] = value
    return base


def overlay_mapping(binary_path: str, **overrides: Any) -> dict[str, Any]:
    """A read-only host-local role overlay declaring a pinned local binary path."""

    mapping: dict[str, Any] = {
        "schema_version": 1,
        "role_id": ROLE_KEY,
        "display_name": "Sachima Claude read-only reviewer (host-local overlay, test)",
        "description": "Host-local read-only role overlay for the P6-B Stage-2 DoR test.",
        "runner": {
            "type": "acpx",
            "acpx_version": REQUIRED_ACPX_VERSION,
            "acpx_binary": binary_path,
            "adapter_agent": ADAPTER_AGENT,
            "model": None,
        },
        "workspace": {
            "default_cwd": "/workspace/sachima",
            "allowed_roots": ["/workspace/sachima"],
            "allowed_roots_security_boundary": False,
        },
        "permissions": {
            "read": True,
            "search": True,
            "write": False,
            "execute": False,
            "terminal": False,
            "delete": False,
            "move": False,
            "fetch": False,
            "switch_mode": False,
            "other": False,
        },
        "session": {"strategy": "exec"},
        "limits": {"timeout_seconds": 900, "max_turns": 8, "max_output_bytes": 2000000},
    }
    return _deep_update(mapping, overrides)


def write_overlay(dir_path: Path, mapping: dict[str, Any]) -> tuple[Path, str]:
    overlay_path = dir_path / "host_local_role_overlay.json"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(mapping, indent=2, sort_keys=True).encode("utf-8")
    overlay_path.write_bytes(payload)
    return overlay_path, "sha256:" + hashlib.sha256(payload).hexdigest()


def make_fake_acpx(
    dir_path: Path,
    *,
    name: str = "acpx",
    version: str = REQUIRED_ACPX_VERSION,
    executable: bool = True,
    prints_version: bool = True,
) -> Path:
    """A temp fake ``acpx`` executable. Never the real runner, never an agent.

    With ``prints_version`` it is a tiny ``/bin/sh`` script that echoes
    ``acpx <version>`` so an argv-list/no-shell probe can read a version line
    without invoking anything real.
    """

    binary = dir_path / "runners" / name
    binary.parent.mkdir(parents=True, exist_ok=True)
    if prints_version:
        binary.write_text(f"#!/bin/sh\necho 'acpx {version}'\n")
    else:
        binary.write_bytes(b"#!/bin/false\nfake pinned local placeholder bytes\n")
    binary.chmod(0o755 if executable else 0o644)
    return binary


def pinned_params(
    outside_dir: Path,
    *,
    binary_path: str | None = None,
    make_binary: bool = True,
    prints_version: bool = True,
    executable: bool = True,
    overlay_overrides: dict[str, Any] | None = None,
    role_overlay_digest: str | None = None,
    acpx_binary_sha256: str | None = None,
    acpx_version: str | None = REQUIRED_ACPX_VERSION,
) -> dict[str, Any]:
    """Build a fully-pinned set of host-local DoR runner params under ``outside_dir``.

    The overlay's declared ``acpx_binary`` and the request's ``acpx_binary`` are
    kept in lockstep so the request-vs-overlay binary cross-check is satisfied by
    default; pass ``overlay_overrides`` to diverge for negative tests.
    """

    if binary_path is None:
        binary = make_fake_acpx(
            outside_dir, executable=executable, prints_version=prints_version
        ) if make_binary else (outside_dir / "runners" / "acpx")
        binary_path = str(binary)
        if acpx_binary_sha256 is None:
            acpx_binary_sha256 = (
                file_sha256(binary) if (make_binary and binary.exists()) else "sha256:" + "0" * 64
            )
    else:
        if acpx_binary_sha256 is None:
            candidate = Path(binary_path)
            acpx_binary_sha256 = (
                file_sha256(candidate) if candidate.exists() else "sha256:" + "0" * 64
            )

    mapping = overlay_mapping(binary_path, **(overlay_overrides or {}))
    overlay_path, computed_digest = write_overlay(outside_dir / "overlay", mapping)
    return {
        "role_key": ROLE_KEY,
        "role_overlay_path": str(overlay_path),
        "role_overlay_digest": role_overlay_digest or computed_digest,
        "acpx_binary": binary_path,
        "acpx_version": acpx_version,
        "acpx_binary_sha256": acpx_binary_sha256,
        "evidence_root": str(outside_dir / "evidence"),
        "artifact_sink_root": str(outside_dir / "sink"),
    }


def build_request(**overrides: Any) -> P6BHostLocalDorRequest:
    base: dict[str, Any] = {
        "enabled": True,
        "approval_token": P6B_HOST_LOCAL_DOR_APPROVAL_TOKEN,
    }
    base.update(overrides)
    return P6BHostLocalDorRequest(**base)


def fake_version_probe(text: str = f"acpx {REQUIRED_ACPX_VERSION} (pinned local build)"):
    """A pure-Python injected probe (no subprocess) returning a fixed version line."""

    def _probe(binary_path: str) -> str:
        return text

    return _probe
