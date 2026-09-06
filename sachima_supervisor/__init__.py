"""Sachima supervisor package root.

The runtime spine itself lives in :mod:`sachima_supervisor.runtime_spine` and
is imported from there. This module deliberately re-exports none of it: a
package root that mirrors its subpackage's surface gives every symbol two
import paths and one of them always drifts, and importing the root would then
drag the whole spine in for callers that wanted one constant.

So the root holds exactly one thing: the version of the external
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
