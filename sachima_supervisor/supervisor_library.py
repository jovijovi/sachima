"""agent_run_supervisor availability / exact-pin checker (smoke prerequisite).

The Phase D readiness gate (PR #117) recorded that the ``agent_run_supervisor``
Python library is absent on this host — the third independent execution
blocker for a real local smoke. This module prepares the *checker* for that
provisioning prerequisite: a later, separately approved smoke may proceed only
when the library is importable **and** its installed distribution version
equals the expected exact pin (the agent-run-supervisor repo currently ships
pyproject version ``0.0.0``).

Boundaries:

  * Deliberately NOT a runtime dependency: ``agent-run-supervisor`` is not
    added to this repo's ``pyproject.toml``. Installing/pinning it stays an
    operator provisioning step under the repo exact-pin dependency policy.
  * The checker never raises on a missing/odd installation; it returns a
    sanitized status with a stable error code. Raw import/metadata exception
    text and unsanitary version strings never enter the status.
  * Probes are injectable so tests never need the real library installed and
    never install, fetch, or execute anything.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import re
from dataclasses import dataclass
from typing import Any, Callable

AGENT_RUN_SUPERVISOR_IMPORT_NAME = "agent_run_supervisor"
AGENT_RUN_SUPERVISOR_DISTRIBUTION = "agent-run-supervisor"
#: Exact expected pin. Matches the current agent-run-supervisor repo
#: ``pyproject.toml`` version; bump only through an explicitly reviewed
#: provisioning update.
EXPECTED_AGENT_RUN_SUPERVISOR_VERSION = "0.0.0"

#: Sanitized version shape (PEP 440-ish, single line, bounded). Anything else
#: is treated as unknown and never echoed back.
_VERSION_RE = re.compile(r"^[0-9][0-9A-Za-z._+-]{0,31}$")


@dataclass(frozen=True)
class SupervisorLibraryPinStatus:
    """Sanitized availability/pin status for the supervisor library."""

    importable: bool
    version_pinned: bool
    expected_version: str | None
    observed_version: str | None
    error_code: str | None

    @property
    def ready(self) -> bool:
        return self.importable and self.version_pinned and self.error_code is None


def check_supervisor_library_pin(
    *,
    expected_version: Any = EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
    import_probe: Callable[[str], Any] | None = None,
    version_probe: Callable[[str], Any] | None = None,
) -> SupervisorLibraryPinStatus:
    """Check that ``agent_run_supervisor`` is importable and exactly pinned.

    Fail-closed checker, not a gate: every miss returns a status carrying a
    stable error code (``supervisor_library_expected_version_invalid`` /
    ``supervisor_library_unavailable`` / ``supervisor_library_version_unknown``
    / ``supervisor_library_version_mismatch``) instead of raising, and no raw
    probe detail leaks. Defaults probe via ``importlib`` only — nothing is
    installed, fetched, or executed.
    """

    if type(expected_version) is not str or _VERSION_RE.fullmatch(expected_version) is None:
        return SupervisorLibraryPinStatus(
            importable=False,
            version_pinned=False,
            expected_version=None,
            observed_version=None,
            error_code="supervisor_library_expected_version_invalid",
        )
    resolve_import = import_probe if import_probe is not None else importlib.import_module
    resolve_version = (
        version_probe if version_probe is not None else importlib.metadata.version
    )
    try:
        resolve_import(AGENT_RUN_SUPERVISOR_IMPORT_NAME)
    except Exception:
        return SupervisorLibraryPinStatus(
            importable=False,
            version_pinned=False,
            expected_version=expected_version,
            observed_version=None,
            error_code="supervisor_library_unavailable",
        )
    try:
        observed = resolve_version(AGENT_RUN_SUPERVISOR_DISTRIBUTION)
    except Exception:
        observed = None
    if type(observed) is not str or _VERSION_RE.fullmatch(observed) is None:
        return SupervisorLibraryPinStatus(
            importable=True,
            version_pinned=False,
            expected_version=expected_version,
            observed_version=None,
            error_code="supervisor_library_version_unknown",
        )
    if observed != expected_version:
        return SupervisorLibraryPinStatus(
            importable=True,
            version_pinned=False,
            expected_version=expected_version,
            observed_version=observed,
            error_code="supervisor_library_version_mismatch",
        )
    return SupervisorLibraryPinStatus(
        importable=True,
        version_pinned=True,
        expected_version=expected_version,
        observed_version=observed,
        error_code=None,
    )
