"""Sachima supervisor package root.

Right now this holds exactly one thing: the version of the external
``agent-run-supervisor`` distribution this repository is calibrated against.

It lives here, and not in ``pyproject.toml`` alone, because the value is read
at runtime as well as at install time: the daemon handshake compares the
version it reports against this constant exactly, so a repository whose
packaging says one version and whose code expects another fails admission
rather than talking a protocol it has not been reviewed for.  Keeping the
constant beside the packaging pin means the drift is caught by a test instead
of by a live handshake.

Bump this, the ``agent-run-supervisor`` extra, its ``dev`` mirror, and the
``uv.lock`` entry together.  ``tests/test_packaging_metadata.py`` fails if any
one of them moves alone.
"""

#: Exact version of the ``agent-run-supervisor`` distribution this repository
#: is calibrated against.  The distribution is the only sanctioned way to
#: reach that subsystem — never a source checkout, ``sys.path`` shim, or
#: ``PYTHONPATH`` entry.
EXPECTED_AGENT_RUN_SUPERVISOR_VERSION = "0.7.8"

__all__ = ["EXPECTED_AGENT_RUN_SUPERVISOR_VERSION"]
