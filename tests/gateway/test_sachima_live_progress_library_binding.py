"""Gateway host binding — default-off ``library`` backend mode (ARS-INT S3).

Pins the backend-selection seam added to ``gateway/sachima_live_progress_binding``:

* the implicit default and the explicit ``fake`` value keep today's static
  bindings-file composition byte-for-byte (summary now names the backend);
* ``library`` mode is DOUBLE default-off: it needs the ``hermes_internal``
  surface gate AND an explicit library config file; it then composes the
  formal execution bundle (registry + real library backend + port +
  dispatcher + LS4-A-gated display service) with **no** static bindings file
  and **no** hand-copied artifact dirs;
* every failure path (unknown backend value, missing/malformed/disabled
  config) logs one stable code, unbinds the tool AND the bundle, and never
  echoes a path/value or crashes the gateway startup path.

Pure local/offline: no Gateway process, Feishu/IM/delivery surface, listener,
or Temporal Worker is started, and composing the library bundle launches no
acpx/AGENT/subprocess. Forbidden terms in this prose are no-leak boundary
canaries only, never behavior.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import gateway.sachima_live_progress_binding as binding_mod
import tools.sachima_live_progress_tool as tool_mod
from tools.registry import invalidate_check_fn_cache, registry
from sachima_supervisor.runtime_spine import scan_for_leak
from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
    AgentRunSupervisorExecutionBinding,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend import (
    ARS_LIBRARY_CONFIG_TYPE,
)

_SURFACE_ENV = tool_mod.SACHIMA_LIVE_PROGRESS_SURFACE_ENV
_FILE_ENV = binding_mod.SACHIMA_LIVE_PROGRESS_BINDINGS_FILE_ENV
_BACKEND_ENV = binding_mod.SACHIMA_LIVE_PROGRESS_BACKEND_ENV
_LIBRARY_CONFIG_ENV = binding_mod.SACHIMA_ARS_LIBRARY_CONFIG_FILE_ENV
_TOOL = tool_mod.TOOL_NAME

_DISABLED = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED
_ABSENT = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT
_INVALID = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID
_BOUND = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND


@pytest.fixture(autouse=True)
def _default_off(monkeypatch):
    for env in (_SURFACE_ENV, _FILE_ENV, _BACKEND_ENV, _LIBRARY_CONFIG_ENV):
        monkeypatch.delenv(env, raising=False)
    tool_mod.unbind_live_progress_display_service()
    invalidate_check_fn_cache()
    yield
    # Clear the envs BEFORE the reset rebind so the disabled path runs and
    # deterministically drops both the tool service and the library bundle.
    for env in (_SURFACE_ENV, _FILE_ENV, _BACKEND_ENV, _LIBRARY_CONFIG_ENV):
        monkeypatch.delenv(env, raising=False)
    binding_mod.bind_live_progress_display_from_env()
    tool_mod.unbind_live_progress_display_service()
    invalidate_check_fn_cache()


def _write_library_config(tmp_path: Path, *, enabled: bool = True) -> str:
    binary = tmp_path / "bin" / "acpx"
    binary.parent.mkdir(exist_ok=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    payload = {
        "type": ARS_LIBRARY_CONFIG_TYPE,
        "enabled": enabled,
        "approval_ref": "approval_arsint_s3",
        "sessions_dir": str(tmp_path / "sessions"),
        "workspace_by_ref": {"ws_arsint": str(work)},
        "role_by_ref": {
            "policy_read_only": {
                "schema_version": 1,
                "role_id": "readonly-reviewer",
                "runner": {
                    "type": "acpx",
                    "acpx_version": "0.12.0",
                    "acpx_binary": None,
                },
                "permissions": {"read": True, "search": True},
                "session": {"strategy": "persistent"},
            }
        },
        "session_prefix": "sachima",
        "acpx_binary": str(binary),
        "stale_after_seconds": 900,
    }
    config_file = tmp_path / "ars_library_config.json"
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


def test_explicit_fake_value_keeps_fake_mode(monkeypatch):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "fake")
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _ABSENT
    assert summary["backend"] == "fake"


@pytest.mark.parametrize("backend", ["real", "cli", "LIBRARY", "1"])
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
# B. Library mode is double default-off and fail-closed
# --------------------------------------------------------------------------- #


def test_library_mode_requires_surface_gate(monkeypatch, tmp_path):
    monkeypatch.setenv(_BACKEND_ENV, "library")
    monkeypatch.setenv(_LIBRARY_CONFIG_ENV, _write_library_config(tmp_path))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _DISABLED
    assert tool_mod._bound_service() is None
    assert binding_mod.bound_execution_binding() is None


def test_library_mode_without_config_file_reports_absent(monkeypatch):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "library")
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _ABSENT
    assert summary["backend"] == "library"
    assert tool_mod._bound_service() is None
    assert binding_mod.bound_execution_binding() is None


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        json.dumps(["not", "a", "dict"]),
        json.dumps({"unexpected_key": True}),
    ],
)
def test_library_mode_malformed_config_fails_closed(monkeypatch, tmp_path, payload, caplog):
    config_file = tmp_path / "bad_config.json"
    config_file.write_text(payload, encoding="utf-8")
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "library")
    monkeypatch.setenv(_LIBRARY_CONFIG_ENV, str(config_file))
    with caplog.at_level(logging.WARNING, logger=binding_mod.__name__):
        summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert tool_mod._bound_service() is None
    assert binding_mod.bound_execution_binding() is None
    assert str(config_file) not in caplog.text


def test_library_mode_disabled_config_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "library")
    monkeypatch.setenv(
        _LIBRARY_CONFIG_ENV, _write_library_config(tmp_path, enabled=False)
    )
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert tool_mod._bound_service() is None
    assert binding_mod.bound_execution_binding() is None


# --------------------------------------------------------------------------- #
# C. Library mode bound posture
# --------------------------------------------------------------------------- #


def test_library_mode_binds_bundle_and_display_service(monkeypatch, tmp_path):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "library")
    monkeypatch.setenv(_LIBRARY_CONFIG_ENV, _write_library_config(tmp_path))

    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _BOUND
    assert summary["backend"] == "library"
    assert summary["binding_count"] == 0 and summary["bindings"] == []
    assert scan_for_leak(summary) is None
    assert str(tmp_path) not in json.dumps(summary)

    bundle = binding_mod.bound_execution_binding()
    assert isinstance(bundle, AgentRunSupervisorExecutionBinding)
    assert tool_mod._bound_service() is bundle.display_service

    # No sessions were launched and nothing is bound yet: queries fail closed
    # with the LS4-A stable code, never an exception or raw material.
    invalidate_check_fn_cache()
    result = _call_tool({"task_id": "task_alpha", "session_id": "sess_1"})
    assert result == {"error": "runtime_invalid_live_progress_query"}


def test_library_mode_ignores_static_bindings_file(monkeypatch, tmp_path):
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
    monkeypatch.setenv(_FILE_ENV, str(static))
    monkeypatch.setenv(_LIBRARY_CONFIG_ENV, _write_library_config(tmp_path))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _BOUND
    assert summary["backend"] == "library"
    assert summary["binding_count"] == 0


def test_rebind_from_library_to_fake_clears_bundle(monkeypatch, tmp_path):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_BACKEND_ENV, "library")
    monkeypatch.setenv(_LIBRARY_CONFIG_ENV, _write_library_config(tmp_path))
    assert binding_mod.bind_live_progress_display_from_env()["code"] == _BOUND
    assert binding_mod.bound_execution_binding() is not None

    monkeypatch.setenv(_BACKEND_ENV, "fake")
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["backend"] == "fake"
    assert binding_mod.bound_execution_binding() is None


def test_binding_module_still_has_no_direct_ars_import():
    import re

    src = Path(binding_mod.__file__).read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*(import|from)\s+agent_run_supervisor", src) is None
    assert "sys.path" not in src
