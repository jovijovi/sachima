"""Real import-compatibility smokes for the pinned agent-run-supervisor.

D0 of the ARS 0.6.3 Socket integration plan
(``docs/plans/2026-08-05-ars-0.6.3-socket-integration-plan.md``): the library
facade modules Sachima lazily imports today (``session_runtime``, ``session``,
``role``, ``workspace``, ``goal``, ``session_inspect``,
``hermes_caller.events``) and the official Socket API v2 client module
(``agent_run_supervisor.arsd.client``) must import for real from the installed
exact-pinned distribution — injected-double tests alone cannot prove the
packaged module layout. Importing must open no daemon/socket connection and
leave no runtime side effect.

These smokes skip only on lean environments without the distribution; with the
distribution installed (the CI dev posture) a failed import is a loud failure,
never a silent skip.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sachima_supervisor.supervisor_library import AGENT_RUN_SUPERVISOR_DISTRIBUTION

#: Library facade modules the existing backend/readers lazily import, plus the
#: official Socket API v2 client module the D1 offline adapter binds to.
FACADE_MODULES = (
    "agent_run_supervisor.session_runtime",
    "agent_run_supervisor.session",
    "agent_run_supervisor.role",
    "agent_run_supervisor.workspace",
    "agent_run_supervisor.goal",
    "agent_run_supervisor.session_inspect",
    "agent_run_supervisor.hermes_caller.events",
    "agent_run_supervisor.arsd.client",
)


def _distribution_installed() -> bool:
    try:
        importlib.metadata.version(AGENT_RUN_SUPERVISOR_DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


_requires_distribution = pytest.mark.skipif(
    not _distribution_installed(),
    reason=(
        "agent-run-supervisor distribution not installed — provision via "
        "`uv sync --extra dev` (or --extra agent-run-supervisor)"
    ),
)


@_requires_distribution
@pytest.mark.parametrize("module_name", FACADE_MODULES)
def test_facade_module_imports_for_real(module_name: str) -> None:
    """Distribution present ⇒ every consumed module imports — no silent skip."""

    module = importlib.import_module(module_name)
    assert module.__name__ == module_name


@_requires_distribution
def test_official_arsd_client_class_importable() -> None:
    """The D1 adapter's only client entrypoint exists in the pinned package."""

    client_mod = importlib.import_module("agent_run_supervisor.arsd.client")
    arsd_client = getattr(client_mod, "ArsdClient", None)
    assert isinstance(arsd_client, type), (
        "agent_run_supervisor.arsd.client.ArsdClient must be a class in the "
        "pinned distribution — the Socket API v2 adapter depends on it"
    )


_IMPORT_PROBE_SCRIPT = """\
import json
import socket
import sys

attempts = []


def _trap(*args, **kwargs):
    attempts.append("connect")
    raise AssertionError("connection attempt during import")


socket.socket.connect = _trap
socket.socket.connect_ex = _trap
socket.create_connection = _trap

import importlib

for name in sys.argv[1].split(","):
    importlib.import_module(name)

print(json.dumps({"attempts": attempts}))
"""


@_requires_distribution
def test_importing_facade_modules_opens_no_connection_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """Import/collection causes no daemon connection or runtime side effect.

    A fresh interpreter with every ``socket`` connection primitive replaced by
    a recording trap, HOME pointed at an empty sandbox, and an empty working
    directory imports every facade module (including the official ArsdClient
    module). Zero connection attempts may occur and both sandboxes must stay
    empty — a daemon probe, config write, or state-dir creation at import time
    fails here.
    """

    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()

    completed = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE_SCRIPT, ",".join(FACADE_MODULES)],
        cwd=work,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, (
        "importing the facade modules must succeed without daemon/runtime "
        f"access; stderr tail: {completed.stderr[-2000:]!r}"
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["attempts"] == [], (
        "importing the facade modules attempted a socket connection"
    )
    assert sorted(home.iterdir()) == [], (
        "importing the facade modules wrote into HOME"
    )
    assert sorted(work.iterdir()) == [], (
        "importing the facade modules wrote into the working directory"
    )
