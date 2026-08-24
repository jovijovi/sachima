"""Gateway host binding — P5 composition: exactly ``fake`` or ``arsd``.

Focused RED/GREEN acceptance tests for the P5 slice of the ARS 0.7.6 Socket
API v3 integration plan
(``docs/plans/2026-08-17-ars-0.7.6-socket-api-v3-integration-plan.md`` §11).
This file is the former ``library``-mode binding suite, re-anchored on the
retirement: the seam it used to prove is gone, and what it proves now is that
selecting it fails closed.

What is proven here:

* the implicit default and the explicit ``fake`` value keep today's static
  bindings-file composition, and the ``fake`` path imports **no**
  ``agent_run_supervisor`` at all — proven in a fresh interpreter (A-21, P5-e);
* ``library`` — from the backend env or from a library-shaped config file —
  yields its own **distinct** stable migration code naming ``fake`` and
  ``arsd``, binds nothing, dispatches nothing, launches nothing, and is never
  silently rewritten to another backend (A-18, P5-a/P5-e);
* ``arsd`` is triple default-off: it needs the exact ``hermes_internal``
  surface gate AND an explicit private config file AND ``enabled`` exactly
  ``True``; every failure path leaves the tool unbound with one stable code and
  never falls back to another backend (A-21, P5-c/P5-e);
* the backend vocabulary is exactly ``("fake", "arsd")`` — nothing else, in
  either case, is admitted.

Pure local/offline: no Gateway process, Feishu/IM/delivery surface, listener,
Temporal Worker, daemon, or socket is started, and no test composes an
**enabled** ``arsd`` config, so no daemon operation is ever attempted.
Forbidden terms in this prose are no-leak boundary canaries only, never
behavior.
"""

from __future__ import annotations

import importlib
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

import gateway.sachima_live_progress_binding as binding_mod
import tools.sachima_live_progress_tool as tool_mod
from tools.registry import invalidate_check_fn_cache, registry
from sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend import (
    ARS_LIBRARY_CONFIG_TYPE,
    LIBRARY_MIGRATION_MESSAGE,
    RUNTIME_LIBRARY_BACKEND_RETIRED,
)
from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    ARSD_SUPERVISOR_CONFIG_TYPE,
    EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
)

_SURFACE_ENV = tool_mod.SACHIMA_LIVE_PROGRESS_SURFACE_ENV
_FILE_ENV = binding_mod.SACHIMA_LIVE_PROGRESS_BINDINGS_FILE_ENV
_BACKEND_ENV = binding_mod.SACHIMA_LIVE_PROGRESS_BACKEND_ENV
_ARSD_CONFIG_ENV = binding_mod.SACHIMA_ARSD_CONFIG_FILE_ENV
_TOOL = tool_mod.TOOL_NAME

_DISABLED = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED
_ABSENT = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT
_INVALID = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID
_BOUND = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND
_RETIRED = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_RETIRED


@pytest.fixture(autouse=True)
def _default_off(monkeypatch):
    for env in (_SURFACE_ENV, _FILE_ENV, _BACKEND_ENV, _ARSD_CONFIG_ENV):
        monkeypatch.delenv(env, raising=False)
    tool_mod.unbind_live_progress_display_service()
    invalidate_check_fn_cache()
    yield
    # Clear the envs BEFORE the reset rebind so the disabled path runs and
    # deterministically drops both the tool service and any bound bundle.
    for env in (_SURFACE_ENV, _FILE_ENV, _BACKEND_ENV, _ARSD_CONFIG_ENV):
        monkeypatch.delenv(env, raising=False)
    binding_mod.bind_live_progress_display_from_env()
    tool_mod.unbind_live_progress_display_service()
    invalidate_check_fn_cache()


def _write_library_config(tmp_path: Path, *, enabled: bool = True) -> str:
    """A file in the shape the retired ``library`` mode used to consume.

    It exists to prove that presenting one now fails closed with the migration
    code: the composition never parses it, never resolves a role/workspace, and
    never reaches a supervisor library.
    """

    payload = {
        "type": ARS_LIBRARY_CONFIG_TYPE,
        "enabled": enabled,
        "approval_ref": "approval_arsint_s3",
        "sessions_dir": str(tmp_path / "sessions"),
        "workspace_by_ref": {"ws_arsint": str(tmp_path / "work")},
        "role_by_ref": {
            "policy_read_only": {
                "schema_version": 1,
                "role_id": "readonly-reviewer",
                "runner": {"type": "acpx", "acpx_version": "0.12.0", "acpx_binary": None},
                "permissions": {"read": True, "search": True},
                "session": {"strategy": "persistent"},
            }
        },
        "session_prefix": "sachima",
        "stale_after_seconds": 900,
    }
    config_file = tmp_path / "ars_library_config.json"
    config_file.write_text(json.dumps(payload), encoding="utf-8")
    return str(config_file)


def _arsd_payload(tmp_path: Path, *, enabled: bool) -> dict:
    return {
        "type": ARSD_SUPERVISOR_CONFIG_TYPE,
        "approval_ref": "approval_arsd_p5_offline",
        "owner": "sachima_host",
        "namespace": "sachima_tasks",
        "socket_path": str(tmp_path / "private" / "arsd.sock"),
        "binding_ledger_path": str(tmp_path / "private" / "arsd-run-bindings.json"),
        "agent_by_policy_ref": {"policy_agent": "reader-agent"},
        "model_by_policy_ref": {"policy_model": "claude-sonnet-5"},
        "effort_by_policy_ref": {"policy_effort": "medium"},
        "workspace_by_ref": {"ws_main": str(tmp_path / "private" / "workspace")},
        "run_limits_by_policy_ref": {
            "policy_limits": {
                "startup_timeout_seconds": 60.0,
                "turn_timeout_seconds": 600.0,
                "cancel_grace_seconds": 10.0,
                "max_stderr_bytes": 262_144,
                "max_event_bytes": 65_536,
                "max_events": 10_000,
            }
        },
        "grant_ref": "grant_reader_v1",
        "grant_hash": "sha256:" + "a" * 64,
        "grant_role_hash": "sha256:" + "b" * 64,
        "grant_capabilities": ["read", "search"],
        "mcp_snapshot_hashes": ["sha256:" + "c" * 64],
        "credential_refs": ["cred_reader_github"],
        "evidence_policy_hash": "sha256:" + "d" * 64,
        "recovery_policy_hash": "sha256:" + "e" * 64,
        "expected_package_version": EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
        "required_api_version": 3,
        "enabled": enabled,
    }


def _write_arsd_config(tmp_path: Path, *, enabled: bool = False, **overrides) -> str:
    """A private ``arsd`` config file.

    ``enabled`` defaults to **False** on purpose: an enabled config would make
    the composition negotiate with a daemon, and no test in this file is
    allowed to reach one. The enabled variant is only ever written for gates
    that refuse *before* the config is read.
    """

    payload = _arsd_payload(tmp_path, enabled=enabled)
    payload.update(overrides)
    config_file = tmp_path / "arsd_config.json"
    config_file.write_text(json.dumps(payload), encoding="utf-8")
    return str(config_file)


def _call_tool(args: dict) -> dict:
    return json.loads(registry.dispatch(_TOOL, args))


# --------------------------------------------------------------------------- #
# A. The fake backend stays the default; the summary names the backend
# --------------------------------------------------------------------------- #
def test_default_backend_is_fake_and_named_in_summary(monkeypatch, tmp_path):
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    cfg = tmp_path / "bindings.json"
    cfg.write_text(
        json.dumps(
            {
                "bindings": [
                    {
                        "task_id": "task_live_smoke",
                        "artifact_dir": str(artifact_dir),
                        "artifact_ref": "artifact_live_smoke_0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, str(cfg))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _BOUND
    assert summary["backend"] == "fake"
    assert summary["binding_count"] == 1
    assert binding_mod.bound_execution_binding() is None


@pytest.mark.parametrize("value", ["fake", "  fake  ", "", "   "])
def test_unset_or_blank_or_explicit_fake_all_stay_fake(monkeypatch, value):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, value)
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _ABSENT
    assert summary["backend"] == "fake"


def test_valid_backends_are_exactly_fake_and_arsd():
    assert binding_mod._VALID_BACKENDS == ("fake", "arsd")


@pytest.mark.parametrize("backend", ["real", "cli", "LIBRARY", "1", "acpx"])
def test_unknown_backend_value_fails_closed(monkeypatch, backend, caplog):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, backend)
    with caplog.at_level(logging.WARNING, logger=binding_mod.__name__):
        summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert tool_mod._bound_service() is None
    assert binding_mod.bound_execution_binding() is None
    if backend not in ("1",):
        assert backend not in caplog.text  # never echo the denied value


# --------------------------------------------------------------------------- #
# B. ``library`` is retired behind its own distinct migration code (P5-a/P5-e)
# --------------------------------------------------------------------------- #
def test_library_selection_yields_the_distinct_migration_code(monkeypatch, caplog):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "library")
    with caplog.at_level(logging.WARNING, logger=binding_mod.__name__):
        summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _RETIRED == RUNTIME_LIBRARY_BACKEND_RETIRED
    assert summary["backend"] == "library"
    # Distinct from "the daemon is down" and from "your config is malformed":
    # an operator can tell "you selected a retired mode" from either.
    assert summary["code"] not in (_INVALID, _ABSENT, _DISABLED, _BOUND)


def test_library_selection_names_the_supported_choices_without_echoing_input(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "library")
    monkeypatch.setenv(_ARSD_CONFIG_ENV, _write_library_config(tmp_path))
    with caplog.at_level(logging.WARNING, logger=binding_mod.__name__):
        summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _RETIRED
    assert "fake" in LIBRARY_MIGRATION_MESSAGE and "arsd" in LIBRARY_MIGRATION_MESSAGE
    assert LIBRARY_MIGRATION_MESSAGE.startswith(RUNTIME_LIBRARY_BACKEND_RETIRED)
    assert LIBRARY_MIGRATION_MESSAGE in caplog.text
    # The migration notice is a fixed literal: no path, no value, no body.
    assert str(tmp_path) not in caplog.text


def test_library_selection_binds_nothing_and_dispatches_nothing(monkeypatch, tmp_path):
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    static = tmp_path / "bindings.json"
    static.write_text(
        json.dumps(
            {
                "bindings": [
                    {
                        "task_id": "task_live_smoke",
                        "artifact_dir": str(artifact_dir),
                        "artifact_ref": "artifact_live_smoke_0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "library")
    # Both a static bindings file AND a library config file are present: a
    # retired selection consumes neither.
    monkeypatch.setenv(_FILE_ENV, str(static))

    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _RETIRED
    assert summary["binding_count"] == 0 and summary["bindings"] == []
    assert tool_mod._bound_service() is None
    assert binding_mod.bound_execution_binding() is None

    # Nothing is dispatchable: the tool itself still fails closed.
    invalidate_check_fn_cache()
    assert _call_tool({"task_id": "task_alpha", "session_id": "sess_1"}) == {
        "error": "sachima_live_progress_display_unbound"
    }


def test_library_selection_is_never_rewritten_to_fake_or_arsd(monkeypatch, tmp_path):
    """No silent rewrite: a bound fake service is dropped, not kept or reused."""

    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    cfg = tmp_path / "bindings.json"
    cfg.write_text(
        json.dumps(
            {
                "bindings": [
                    {
                        "task_id": "task_live_smoke",
                        "artifact_dir": str(artifact_dir),
                        "artifact_ref": "artifact_live_smoke_0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, str(cfg))
    assert binding_mod.bind_live_progress_display_from_env()["code"] == _BOUND
    assert tool_mod._bound_service() is not None

    monkeypatch.setenv(_BACKEND_ENV, "library")
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _RETIRED
    assert summary["backend"] == "library"
    assert tool_mod._bound_service() is None


def test_library_config_file_env_knob_is_gone(monkeypatch, tmp_path):
    """The old private-config knob no longer exists, and setting it is inert."""

    assert not hasattr(binding_mod, "SACHIMA_ARS_LIBRARY_CONFIG_FILE_ENV")
    assert "SACHIMA_ARS_LIBRARY_CONFIG_FILE" not in binding_mod.__all__
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "library")
    monkeypatch.setenv("SACHIMA_ARS_LIBRARY_CONFIG_FILE", _write_library_config(tmp_path))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _RETIRED
    assert binding_mod.bound_execution_binding() is None


def test_the_migration_code_is_in_the_modules_stable_code_set():
    assert _RETIRED in binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_STABLE_CODES
    # The gateway mirrors the spine's one migration seam rather than minting a
    # second code that could drift away from it.
    assert _RETIRED == RUNTIME_LIBRARY_BACKEND_RETIRED


# --------------------------------------------------------------------------- #
# C. ``arsd`` is triple default-off (P5-c/P5-e)
# --------------------------------------------------------------------------- #
def test_arsd_is_unreachable_without_exact_enabled_true_and_the_surface_gate(
    monkeypatch, tmp_path
):
    # (1) enabled=True but NO surface gate: refused before the file is read.
    monkeypatch.setenv(_BACKEND_ENV, "arsd")
    monkeypatch.setenv(_ARSD_CONFIG_ENV, _write_arsd_config(tmp_path, enabled=True))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _DISABLED
    assert tool_mod._bound_service() is None
    assert binding_mod.bound_execution_binding() is None

    # (2) the surface gate, an explicit config file, but enabled is not True.
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_ARSD_CONFIG_ENV, _write_arsd_config(tmp_path, enabled=False))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert summary["backend"] == "arsd"
    assert tool_mod._bound_service() is None
    assert binding_mod.bound_execution_binding() is None

    # (3) the surface gate and enabled=True, but no config file at all.
    monkeypatch.delenv(_ARSD_CONFIG_ENV, raising=False)
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _ABSENT
    assert summary["backend"] == "arsd"
    assert tool_mod._bound_service() is None
    assert binding_mod.bound_execution_binding() is None


@pytest.mark.parametrize("blank", ["", "   "])
def test_arsd_with_a_blank_config_path_reports_absent(monkeypatch, blank):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "arsd")
    monkeypatch.setenv(_ARSD_CONFIG_ENV, blank)
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _ABSENT
    assert summary["backend"] == "arsd"


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        json.dumps(["not", "a", "dict"]),
        json.dumps({"unexpected_key": True}),
    ],
)
def test_arsd_malformed_config_fails_closed(monkeypatch, tmp_path, payload, caplog):
    config_file = tmp_path / "bad_arsd_config.json"
    config_file.write_text(payload, encoding="utf-8")
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "arsd")
    monkeypatch.setenv(_ARSD_CONFIG_ENV, str(config_file))
    with caplog.at_level(logging.WARNING, logger=binding_mod.__name__):
        summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert summary["backend"] == "arsd"
    assert tool_mod._bound_service() is None
    assert binding_mod.bound_execution_binding() is None
    assert str(config_file) not in caplog.text


def test_a_library_config_file_under_the_arsd_knob_yields_the_migration_code(
    monkeypatch, tmp_path, caplog
):
    """Selecting the retired backend *via config* answers with the same code.

    An operator who repoints the new knob at the old file learns that the mode
    is retired, not that their file is malformed — and nothing is migrated,
    converted, or composed on the way to saying so.
    """

    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "arsd")
    monkeypatch.setenv(_ARSD_CONFIG_ENV, _write_library_config(tmp_path))
    with caplog.at_level(logging.WARNING, logger=binding_mod.__name__):
        summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _RETIRED
    assert tool_mod._bound_service() is None
    assert binding_mod.bound_execution_binding() is None


def test_a_failed_arsd_composition_never_falls_back_to_fake(monkeypatch, tmp_path):
    """No automatic fallback: a static bindings file is not a consolation prize."""

    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    static = tmp_path / "bindings.json"
    static.write_text(
        json.dumps(
            {
                "bindings": [
                    {
                        "task_id": "task_live_smoke",
                        "artifact_dir": str(artifact_dir),
                        "artifact_ref": "artifact_live_smoke_0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "arsd")
    monkeypatch.setenv(_FILE_ENV, str(static))
    monkeypatch.setenv(_ARSD_CONFIG_ENV, _write_arsd_config(tmp_path, enabled=False))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert summary["backend"] == "arsd"
    assert summary["binding_count"] == 0
    assert tool_mod._bound_service() is None


def test_rebind_from_arsd_to_fake_clears_any_bundle(monkeypatch, tmp_path):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "arsd")
    monkeypatch.setenv(_ARSD_CONFIG_ENV, _write_arsd_config(tmp_path, enabled=False))
    assert binding_mod.bind_live_progress_display_from_env()["code"] == _INVALID
    assert binding_mod.bound_execution_binding() is None

    monkeypatch.setenv(_BACKEND_ENV, "fake")
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["backend"] == "fake"
    assert summary["code"] == _ABSENT
    assert binding_mod.bound_execution_binding() is None


# --------------------------------------------------------------------------- #
# D. Import purity on the default path (A-1 final enumeration, P5-e)
# --------------------------------------------------------------------------- #
_FAKE_PATH_PROBE = """
import json, os, sys

os.environ["SACHIMA_LIVE_PROGRESS_DISPLAY_SURFACE"] = "hermes_internal"
os.environ["SACHIMA_LIVE_PROGRESS_BINDINGS_FILE"] = sys.argv[1]
os.environ.pop("SACHIMA_LIVE_PROGRESS_BACKEND", None)

import gateway.sachima_live_progress_binding as binding_mod

summary = binding_mod.bind_live_progress_display_from_env()
leaked = sorted(name for name in sys.modules if name.split(".")[0] == "agent_run_supervisor")
print(json.dumps({"code": summary["code"], "backend": summary["backend"], "leaked": leaked}))
"""


def test_fake_is_the_default_and_needs_no_agent_run_supervisor_import(tmp_path):
    """A-21/A-1: the default path is green with the producer never imported.

    Run in a fresh interpreter, because an unrelated test in the same session
    may already have imported the distribution for its own drift lock.
    """

    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    (artifact_dir / "progress.json").write_text(
        json.dumps({"schema_version": 1, "state": "running", "last_seq": 0, "event_count": 0}),
        encoding="utf-8",
    )
    bindings_file = tmp_path / "bindings.json"
    bindings_file.write_text(
        json.dumps(
            {
                "bindings": [
                    {
                        "task_id": "task_live_smoke",
                        "artifact_dir": str(artifact_dir),
                        "artifact_ref": "artifact_live_smoke_0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-c", _FAKE_PATH_PROBE, str(bindings_file)],
        cwd=str(Path(binding_mod.__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout.strip().splitlines()[-1])
    assert observed["code"] == _BOUND
    assert observed["backend"] == "fake"
    assert observed["leaked"] == []


def test_binding_module_has_no_direct_ars_import_and_no_retired_module_name():
    import re

    src = Path(binding_mod.__file__).read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*(import|from)\s+agent_run_supervisor", src) is None
    assert "sys.path" not in src
    for retired in ("session_runtime", "session_inspect", "hermes_caller", "acpx"):
        assert retired not in src


def test_the_arsd_config_key_allowlist_matches_the_config_dataclass() -> None:
    """A drifted allowlist is how a grant field gets silently dropped.

    The gateway refuses unknown keys rather than ignoring them, so the
    allowlist has to be the config's exact field set — a field added upstream
    and forgotten here would make every valid file invalid, and a stale extra
    key would let a typo through.
    """

    import dataclasses

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ArsdSupervisorConfig,
    )

    assert binding_mod._ARSD_CONFIG_KEYS == frozenset(
        field.name for field in dataclasses.fields(ArsdSupervisorConfig)
    )


# --------------------------------------------------------------------------- #
# E. The delegate seam (Milestone A, task 3): one bundle, one payload resolver
# --------------------------------------------------------------------------- #
class _MinimalFacade:
    """A Socket API v3 facade double — the only "daemon" in this section.

    Composition performs exactly one operation (``server_info``), so that is
    the only one this double ever has to answer for real. The rest exist
    because the injected boundary is a Protocol: a partial implementation
    would not satisfy ``isinstance`` and would fail the composition for the
    wrong reason.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def server_info(self):
        self.calls.append("server_info")
        return {
            "version": EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
            "api_version": 3,
            "supported_api_versions": [3],
            "operations": [
                "agent_list",
                "run_cancel",
                "run_events",
                "run_status",
                "server_info",
                "session_list",
                "session_status",
                "submit",
            ],
            "limits": {
                "max_concurrent_runs": 10,
                "max_frame_bytes": 1_048_576,
                "max_prompt_bytes": 262_144,
                "events_page_limit": 256,
                "event_follow_queue_size": 1024,
                "max_run_event_budget_bytes": 2_147_483_648,
            },
        }

    def submit(self, *, request_id, payload):
        raise AssertionError("no submit may run here")

    def run_status(self, run_id):
        raise AssertionError("no run_status may run here")

    def run_events(self, run_id, *, from_seq, limit=None):
        raise AssertionError("no run_events may run here")

    def run_cancel(self, run_id):
        raise AssertionError("no run_cancel may run here")

    def session_status(self, session_id):
        raise AssertionError("no session_status may run here")

    def session_list(self):
        raise AssertionError("no session_list may run here")

    def agent_list(self):
        raise AssertionError("no agent_list may run here")


def _compose_arsd(monkeypatch, tmp_path, *, facade=None):
    """Bind the ``arsd`` backend with an injected facade, and capture kwargs.

    ``bind_arsd_execution`` is patched at its **source** module (the binding
    imports it per call), so the real composition root still runs — this
    substitutes the daemon, not the seam under test.
    """

    from sachima_supervisor.runtime_spine import (
        agent_run_supervisor_execution_binding as compose_mod,
    )

    facade = _MinimalFacade() if facade is None else facade
    captured: dict = {}
    real_bind = compose_mod.bind_arsd_execution

    def _bind(config, **kwargs):
        captured.update(kwargs)
        captured["config"] = config
        return real_bind(config, facade=facade, **kwargs)

    monkeypatch.setattr(compose_mod, "bind_arsd_execution", _bind)
    (tmp_path / "private").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "arsd")
    monkeypatch.setenv(_ARSD_CONFIG_ENV, _write_arsd_config(tmp_path, enabled=True))
    summary = binding_mod.bind_live_progress_display_from_env()
    return summary, captured, facade


def test_arsd_binding_injects_the_delegate_payload_resolver(monkeypatch, tmp_path):
    """A-1: the composed bundle's dispatcher resolves through the host's own
    claim-check store, so the exact task text never rides on a request.

    The store is the coordinator's durable state, and the injected resolver is
    late-bound on purpose: composition hands the bundle a callable *before* the
    coordinator that owns the store exists, and it still finds that one store
    when it is actually called.
    """

    import gateway.sachima_delegate as delegate_mod

    summary, captured, _ = _compose_arsd(monkeypatch, tmp_path)
    assert summary["code"] == _BOUND and summary["backend"] == "arsd"

    resolver = captured["payload_resolver"]
    assert resolver is not None
    coordinator = delegate_mod.bound_delegate_coordinator()
    ref = coordinator.state.put_payload("private delegate task text")
    assert resolver(ref) == "private delegate task text"
    coordinator.state.discard_payload(ref)


def test_delegate_and_live_progress_share_exactly_one_bundle(monkeypatch, tmp_path):
    """A-1: no second registry / backend / port / dispatcher / bindings.

    The delegate coordinator and the live-progress read chain are two views of
    one spine; composing a second one would let a Run be dispatched into a
    conversation the display service knows nothing about.
    """

    import gateway.sachima_delegate as delegate_mod

    summary, _, _ = _compose_arsd(monkeypatch, tmp_path)
    assert summary["code"] == _BOUND

    bundle = binding_mod.bound_execution_binding()
    coordinator = delegate_mod.bound_delegate_coordinator()
    assert bundle is not None and coordinator is not None
    assert coordinator.binding is bundle
    assert coordinator.binding.dispatcher is bundle.dispatcher
    assert bundle.dispatcher.registry is bundle.registry
    assert bundle.dispatcher.bindings is bundle.bindings
    assert bundle.query_service.registry is bundle.registry
    assert bundle.query_service.port is bundle.port
    assert bundle.display_service is tool_mod._bound_service()


def test_the_bound_coordinator_capacity_comes_from_the_live_negotiation(
    monkeypatch, tmp_path
):
    """A-1: ``server_info.limits.max_concurrent_runs`` and nothing else.

    The negotiated number is no longer carried as a bare int: it is the bound
    of a :class:`DelegateCapacity` permit ledger, which is what actually keeps
    admission from exceeding what the daemon said it will hold.
    """

    import gateway.sachima_delegate as delegate_mod
    from gateway.sachima_delegate_state import DelegateCapacity

    summary, _, facade = _compose_arsd(monkeypatch, tmp_path)
    assert summary["code"] == _BOUND
    coordinator = delegate_mod.bound_delegate_coordinator()
    assert isinstance(coordinator.capacity, DelegateCapacity)
    assert coordinator.capacity.capacity == 10
    assert coordinator.capacity.held() == 0
    assert facade.calls == ["server_info"]


@pytest.mark.parametrize("backend_value", ["", "fake"])
def test_the_fake_backend_binds_no_delegate_coordinator(
    monkeypatch, tmp_path, backend_value
):
    """Default-off is unchanged: the fake path composes no execution bundle,
    so there is nothing for delegation to drive."""

    import gateway.sachima_delegate as delegate_mod

    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    bindings_file = tmp_path / "bindings.json"
    bindings_file.write_text(
        json.dumps(
            {
                "bindings": [
                    {
                        "task_id": "task_live_smoke",
                        "artifact_dir": str(artifact_dir),
                        "artifact_ref": "artifact_live_smoke_0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, backend_value)
    monkeypatch.setenv(_FILE_ENV, str(bindings_file))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _BOUND and summary["backend"] == "fake"
    assert binding_mod.bound_execution_binding() is None
    assert delegate_mod.bound_delegate_coordinator() is None


def test_a_disabled_or_failed_arsd_config_binds_no_delegate_coordinator(
    monkeypatch, tmp_path
):
    import gateway.sachima_delegate as delegate_mod

    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "arsd")
    monkeypatch.setenv(_ARSD_CONFIG_ENV, _write_arsd_config(tmp_path, enabled=False))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert binding_mod.bound_execution_binding() is None
    assert delegate_mod.bound_delegate_coordinator() is None


def test_rebinding_away_from_arsd_drops_the_delegate_coordinator(monkeypatch, tmp_path):
    """A stale coordinator would keep dispatching into a retired bundle."""

    import gateway.sachima_delegate as delegate_mod

    summary, _, _ = _compose_arsd(monkeypatch, tmp_path)
    assert summary["code"] == _BOUND
    assert delegate_mod.bound_delegate_coordinator() is not None

    monkeypatch.setenv(_BACKEND_ENV, "fake")
    monkeypatch.delenv(_FILE_ENV, raising=False)
    assert binding_mod.bind_live_progress_display_from_env()["code"] == _ABSENT
    assert binding_mod.bound_execution_binding() is None
    assert delegate_mod.bound_delegate_coordinator() is None


def test_composing_the_bundle_still_submits_nothing(monkeypatch, tmp_path):
    """Composition is not a dispatch: a bound coordinator has started no Run."""

    import gateway.sachima_delegate as delegate_mod

    summary, _, facade = _compose_arsd(monkeypatch, tmp_path)
    assert summary["code"] == _BOUND
    assert facade.calls == ["server_info"]
    coordinator = delegate_mod.bound_delegate_coordinator()
    assert coordinator.active_count() == 0
    # Nothing was claim-checked, bound, or admitted into the durable state
    # either: composing wrote no delegate work of any kind.
    assert coordinator.state.list_turns() == ()
    assert coordinator.state.list_tasks() == ()


def test_the_binding_composes_and_the_coordinator_owns_restoration():
    """Composing is not recovering — but Revision 9 does recover.

    Milestone A read this as "no ``rehydrate_source_binding`` anywhere", which
    is now obsolete: restart restoration and dispatch recovery are required, and
    they live behind the coordinator's explicit restore barrier. What survives
    is the split the old test was really protecting — the host binding composes
    a bundle, it does not reattach a prior process's Runs.
    """

    src = Path(binding_mod.__file__).read_text(encoding="utf-8")
    assert "rehydrate_source_binding" not in src
    assert "recover_dispatch" not in src

    delegate_mod = importlib.import_module("gateway.sachima_delegate")
    delegate_src = Path(delegate_mod.__file__).read_text(encoding="utf-8")
    assert "rehydrate_source_binding" in delegate_src
    assert "recover_dispatch" in delegate_src
    assert hasattr(delegate_mod.SachimaDelegateCoordinator, "restore")
