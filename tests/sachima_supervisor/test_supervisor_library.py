"""Tests for the agent_run_supervisor availability / exact-pin checker.

The checker is a Phase D smoke provisioning *prerequisite*: a later smoke may
proceed only when the real library is importable and its installed
distribution version equals the expected exact pin. These tests use injected
probes only — they never require the library on this host and never install,
import-execute, or invoke anything real.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from sachima_supervisor.supervisor_library import (
    AGENT_RUN_SUPERVISOR_DISTRIBUTION,
    AGENT_RUN_SUPERVISOR_IMPORT_NAME,
    EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
    SupervisorLibraryPinStatus,
    check_supervisor_library_pin,
)


def _counting_import(calls: list[str], *, raises: Exception | None = None) -> Any:
    def _probe(name: str) -> object:
        calls.append(name)
        if raises is not None:
            raise raises
        return object()

    return _probe


def _counting_version(calls: list[str], value: Any, *, raises: Exception | None = None) -> Any:
    def _probe(name: str) -> Any:
        calls.append(name)
        if raises is not None:
            raise raises
        return value

    return _probe


def test_expected_pin_matches_current_agent_run_supervisor_pyproject_version() -> None:
    assert EXPECTED_AGENT_RUN_SUPERVISOR_VERSION == "0.0.0"
    assert AGENT_RUN_SUPERVISOR_IMPORT_NAME == "agent_run_supervisor"
    assert AGENT_RUN_SUPERVISOR_DISTRIBUTION == "agent-run-supervisor"


def test_importable_and_exact_pin_reports_ready() -> None:
    import_calls: list[str] = []
    version_calls: list[str] = []

    status = check_supervisor_library_pin(
        import_probe=_counting_import(import_calls),
        version_probe=_counting_version(version_calls, "0.0.0"),
    )

    assert isinstance(status, SupervisorLibraryPinStatus)
    assert status.importable is True
    assert status.version_pinned is True
    assert status.ready is True
    assert status.error_code is None
    assert status.expected_version == "0.0.0"
    assert status.observed_version == "0.0.0"
    assert import_calls == ["agent_run_supervisor"]
    assert version_calls == ["agent-run-supervisor"]


def test_missing_library_fails_closed_without_version_probe() -> None:
    import_calls: list[str] = []
    version_calls: list[str] = []

    status = check_supervisor_library_pin(
        import_probe=_counting_import(import_calls, raises=ImportError("missing")),
        version_probe=_counting_version(version_calls, "0.0.0"),
    )

    assert status.importable is False
    assert status.version_pinned is False
    assert status.ready is False
    assert status.error_code == "supervisor_library_unavailable"
    assert status.observed_version is None
    assert version_calls == []


def test_version_probe_failure_fails_closed_as_version_unknown() -> None:
    status = check_supervisor_library_pin(
        import_probe=_counting_import([]),
        version_probe=_counting_version(
            [], None, raises=RuntimeError("raw metadata failure detail")
        ),
    )

    assert status.importable is True
    assert status.version_pinned is False
    assert status.ready is False
    assert status.error_code == "supervisor_library_version_unknown"
    assert status.observed_version is None
    assert "metadata failure" not in repr(status)


def test_wrong_version_fails_closed_as_mismatch() -> None:
    status = check_supervisor_library_pin(
        import_probe=_counting_import([]),
        version_probe=_counting_version([], "9.9.9"),
    )

    assert status.importable is True
    assert status.version_pinned is False
    assert status.ready is False
    assert status.error_code == "supervisor_library_version_mismatch"
    assert status.observed_version == "9.9.9"


@pytest.mark.parametrize(
    "observed",
    [None, 7, "", "0.0.0 with secret tok" + "en detail", "0.0.0\nextra-line"],
)
def test_unsanitary_observed_version_is_dropped_not_leaked(observed: Any) -> None:
    status = check_supervisor_library_pin(
        import_probe=_counting_import([]),
        version_probe=_counting_version([], observed),
    )

    assert status.version_pinned is False
    assert status.ready is False
    assert status.error_code == "supervisor_library_version_unknown"
    assert status.observed_version is None
    assert "secret" not in repr(status)


@pytest.mark.parametrize("expected", ["", "not a version!!", "0.0.0\n", None, 7])
def test_invalid_expected_pin_fails_closed_before_any_probe(expected: Any) -> None:
    import_calls: list[str] = []
    version_calls: list[str] = []

    status = check_supervisor_library_pin(
        expected_version=expected,
        import_probe=_counting_import(import_calls),
        version_probe=_counting_version(version_calls, "0.0.0"),
    )

    assert status.importable is False
    assert status.version_pinned is False
    assert status.ready is False
    assert status.error_code == "supervisor_library_expected_version_invalid"
    assert import_calls == []
    assert version_calls == []


def test_default_probes_fail_closed_when_library_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ``None`` in sys.modules makes ``import agent_run_supervisor`` raise,
    # mirroring a host where the library is genuinely absent.
    monkeypatch.setitem(sys.modules, "agent_run_supervisor", None)

    status = check_supervisor_library_pin()

    assert status.importable is False
    assert status.ready is False
    assert status.error_code == "supervisor_library_unavailable"
