"""Gateway host binding for ``sachima_live_progress_display`` — acceptance tests.

Proves the LS4 Gateway/Feishu host binding seam stays default-off and fail-closed:

* default-off — with no env the binding is a no-op (``..._disabled``), the tool
  stays unbound, and the schema stays hidden; a denied / non-``hermes_internal``
  surface value keeps the binding disabled;
* explicit-config-only — with the surface gate on but no bindings file the
  binding reports ``..._absent`` and never crashes; the tool still fails closed
  with its own stable ``sachima_live_progress_display_unbound`` code;
* malformed config — an unreadable / non-JSON / off-shape bindings file, an
  unsafe ``task_id`` / ``artifact_ref``, or an empty ``artifact_dir`` all log
  ONE stable ``..._invalid`` code (never the offending value / path) and leave
  the tool unbound;
* bound posture — valid config builds the full spine composition (bindings +
  registry + port + real lazy reader + LS4-A ``hermes_internal`` gate + display
  service), binds it into the tool, and returns a refs-only summary (task /
  session / artifact_ref — never the private ``artifact_dir``);
* real caller API — with the exact-pinned ``agent-run-supervisor`` distribution
  installed (``uv sync --extra dev`` / ``--extra agent-run-supervisor``; there
  is no source-path fallback), a synthetic ``progress.json`` +
  ``normalized-events.jsonl`` artifact dir is read end-to-end through the REAL
  ``agent_run_supervisor.hermes_caller.events`` reader (never an in-test fake)
  and the tool returns an available ``live_progress_display.v1`` envelope for
  the real ``task_id/session_id``.

Everything runs pure local/offline: no Gateway process, Feishu / IM / delivery
surface, listener, or Temporal Worker is started — the "gateway" here is only
the host-binding module the runner calls. Forbidden terms in this prose are
no-leak boundary canaries only, never behavior.
"""

from __future__ import annotations

import importlib
import json
import logging
import re
from pathlib import Path

import pytest

import gateway.sachima_live_progress_binding as binding_mod
import tools.sachima_live_progress_tool as tool_mod
from tools.registry import invalidate_check_fn_cache, registry
from sachima_supervisor.runtime_spine import scan_for_leak

_SURFACE_ENV = tool_mod.SACHIMA_LIVE_PROGRESS_SURFACE_ENV
_FILE_ENV = binding_mod.SACHIMA_LIVE_PROGRESS_BINDINGS_FILE_ENV
_TOOL = tool_mod.TOOL_NAME

_DISABLED = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED
_ABSENT = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT
_INVALID = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID
_BOUND = binding_mod.SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND


# --------------------------------------------------------------------------- #
# Real caller-API discovery — the installed distribution only, else skip
# (mirrors tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_live_progress_smoke.py,
# which also guards "distribution installed ⇒ API importable" as a hard failure)
# --------------------------------------------------------------------------- #
def _load_real_caller_api():
    try:
        return importlib.import_module("agent_run_supervisor.hermes_caller.events")
    except Exception:
        return None


_REAL_CALLER_API = _load_real_caller_api()
_requires_real_api = pytest.mark.skipif(
    _REAL_CALLER_API is None,
    reason=(
        "agent_run_supervisor.hermes_caller.events not importable — install the "
        "pinned distribution via `uv sync --extra dev` (or --extra "
        "agent-run-supervisor); default-off and fail-closed tests still run"
    ),
)


# --------------------------------------------------------------------------- #
# Fixtures — every test starts (and ends) default-off and unbound
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _default_off(monkeypatch):
    for env in (_SURFACE_ENV, _FILE_ENV):
        monkeypatch.delenv(env, raising=False)
    tool_mod.unbind_live_progress_display_service()
    invalidate_check_fn_cache()
    yield
    tool_mod.unbind_live_progress_display_service()
    invalidate_check_fn_cache()


def _write_bindings_file(tmp_path: Path, payload) -> str:
    cfg = tmp_path / "live_progress_bindings.json"
    cfg.write_text(json.dumps(payload), encoding="utf-8")
    return str(cfg)


def _entry(artifact_dir: str, *, task_id="task_live_smoke", artifact_ref="artifact_live_smoke_0"):
    return {"task_id": task_id, "artifact_dir": artifact_dir, "artifact_ref": artifact_ref}


def _call_tool(args: dict) -> dict:
    return json.loads(registry.dispatch(_TOOL, args))


# Synthetic ARS artifact writers (mirror the PR-LS3 smoke test's single format
# assumption: the event-type token rides under BOTH ``family`` and ``type``).
def _write_progress(artifact_dir: Path, *, state="running", last_seq=3, event_count=3):
    payload = {
        "schema_version": 1,
        "state": state,
        "last_seq": last_seq,
        "event_count": event_count,
        "updated_at": "2026-07-07T00:00:00Z",
    }
    (artifact_dir / "progress.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_events(artifact_dir: Path, events):
    body = "".join(json.dumps(e) + "\n" for e in events)
    (artifact_dir / "normalized-events.jsonl").write_text(body, encoding="utf-8")


def _event(seq, family, *, kind="call", status="running", text_length=0):
    return {
        "seq": seq,
        "family": family,
        "type": family,
        "kind": kind,
        "status": status,
        "text_length": text_length,
        "summary": "ok",
    }


# --------------------------------------------------------------------------- #
# A. Default-off: no env → no-op, tool unbound, schema hidden
# --------------------------------------------------------------------------- #
def test_binding_disabled_without_env():
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _DISABLED
    assert summary["binding_count"] == 0 and summary["bindings"] == []
    assert tool_mod._bound_service() is None
    assert registry.get_definitions({_TOOL}) == []


@pytest.mark.parametrize(
    "denied", ["", "1", "true", "gateway", "feishu", "production", "local_offline"]
)
def test_binding_disabled_for_non_internal_surfaces(monkeypatch, denied, tmp_path):
    # Even with a bindings file configured, only the exact ``hermes_internal``
    # surface activates the HOST binding (``local_offline`` is an approved TOOL
    # surface for offline harnesses, but never a gateway-host binding trigger).
    monkeypatch.setenv(_SURFACE_ENV, denied)
    monkeypatch.setenv(_FILE_ENV, _write_bindings_file(tmp_path, {"bindings": []}))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _DISABLED
    assert tool_mod._bound_service() is None


def test_binding_absent_without_bindings_file(monkeypatch):
    # Acceptance 2: surface gate on, no host binding config → no crash, and the
    # tool still fails closed with its own stable unbound code.
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _ABSENT
    assert tool_mod._bound_service() is None
    result = _call_tool({"task_id": "task_alpha", "session_id": "sess_x"})
    assert result == {"error": "sachima_live_progress_display_unbound"}


def test_absent_or_disabled_rebind_clears_stale_service(monkeypatch, tmp_path):
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, _write_bindings_file(tmp_path, {"bindings": [_entry(str(artifact_dir))]}))
    assert binding_mod.bind_live_progress_display_from_env()["code"] == _BOUND
    assert tool_mod._bound_service() is not None

    monkeypatch.delenv(_FILE_ENV, raising=False)
    assert binding_mod.bind_live_progress_display_from_env()["code"] == _ABSENT
    assert tool_mod._bound_service() is None

    monkeypatch.setenv(_FILE_ENV, _write_bindings_file(tmp_path, {"bindings": [_entry(str(artifact_dir))]}))
    assert binding_mod.bind_live_progress_display_from_env()["code"] == _BOUND
    assert tool_mod._bound_service() is not None

    monkeypatch.setenv(_SURFACE_ENV, "gateway")
    assert binding_mod.bind_live_progress_display_from_env()["code"] == _DISABLED
    assert tool_mod._bound_service() is None


def test_binding_absent_for_blank_bindings_file_env(monkeypatch):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, "   ")
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _ABSENT
    assert tool_mod._bound_service() is None


# --------------------------------------------------------------------------- #
# B. Malformed config → one stable warning code, unbound, never echoed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "payload, marker",
    [
        (["not", "a", "dict"], None),
        ({"bindings": {}}, None),
        ({"bindings": ["not-a-dict"]}, None),
        ({"bindings": [{"task_id": "task_ok", "artifact_ref": "artifact_ok"}]}, None),
        ({"bindings": [_entry("/srv/run/abc", task_id="../../etc/passwd")]}, "etc/passwd"),
        ({"bindings": [_entry("/srv/run/abc", artifact_ref="/srv/user/leak")]}, "/srv/user/leak"),
        ({"bindings": [_entry("")]}, None),
        ({"bindings": [_entry(None)]}, None),
    ],
)
def test_malformed_config_fails_closed_without_echo(monkeypatch, tmp_path, caplog, payload, marker):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, _write_bindings_file(tmp_path, payload))
    with caplog.at_level(logging.WARNING, logger=binding_mod.__name__):
        summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert summary["binding_count"] == 0 and summary["bindings"] == []
    assert tool_mod._bound_service() is None
    assert _INVALID in caplog.text
    if marker is not None:
        assert marker not in caplog.text
    assert str(tmp_path) not in caplog.text


def test_missing_bindings_file_fails_closed_without_echo(monkeypatch, tmp_path, caplog):
    missing = tmp_path / "does_not_exist.json"
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, str(missing))
    with caplog.at_level(logging.WARNING, logger=binding_mod.__name__):
        summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert tool_mod._bound_service() is None
    assert str(missing) not in caplog.text


def test_non_json_bindings_file_fails_closed(monkeypatch, tmp_path):
    cfg = tmp_path / "bad.json"
    cfg.write_text("{nope", encoding="utf-8")
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, str(cfg))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert tool_mod._bound_service() is None


def test_invalid_config_unbinds_any_previously_bound_service(monkeypatch, tmp_path):
    # First a valid bind, then a malformed rebind: the safest posture after a
    # malformed rebind is fail-closed unbound, not a stale service.
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, _write_bindings_file(tmp_path, {"bindings": [_entry(str(artifact_dir))]}))
    assert binding_mod.bind_live_progress_display_from_env()["code"] == _BOUND
    assert tool_mod._bound_service() is not None

    monkeypatch.setenv(_FILE_ENV, _write_bindings_file(tmp_path, {"bindings": "corrupt"}))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert tool_mod._bound_service() is None


def test_binding_function_never_raises_when_bind_seam_explodes(monkeypatch, tmp_path):
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, _write_bindings_file(tmp_path, {"bindings": [_entry(str(artifact_dir))]}))

    def _boom(service):
        raise RuntimeError("bind seam exploded")

    monkeypatch.setattr(tool_mod, "bind_live_progress_display_service", _boom)
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _INVALID
    assert tool_mod._bound_service() is None


# --------------------------------------------------------------------------- #
# C. Valid config binds a real service; summary is refs-only
# --------------------------------------------------------------------------- #
def test_valid_config_binds_service_with_refs_only_summary(monkeypatch, tmp_path):
    artifact_dir = tmp_path / "private_run"
    artifact_dir.mkdir()
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, _write_bindings_file(tmp_path, {"bindings": [_entry(str(artifact_dir))]}))

    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _BOUND
    assert summary["binding_count"] == 1
    (bound,) = summary["bindings"]
    assert set(bound) == {"task_id", "session_id", "artifact_ref"}
    assert bound["task_id"] == "task_live_smoke"
    assert bound["session_id"].startswith("sess_")
    assert bound["artifact_ref"] == "artifact_live_smoke_0"
    # Refs-only: the private artifact dir never enters the summary, and the
    # whole summary passes the spine's no-leak scan.
    assert str(artifact_dir) not in json.dumps(summary)
    assert scan_for_leak(summary) is None
    assert tool_mod._bound_service() is not None

    # The tool now answers for the REAL task/session pair with the sanitized
    # envelope — an empty artifact dir renders the safe unavailable display,
    # never the unbound error and never an exception.
    invalidate_check_fn_cache()
    envelope = _call_tool({"task_id": bound["task_id"], "session_id": bound["session_id"]})
    assert envelope["type"] == "live_progress_display.v1"
    assert envelope["display"]["task_id"] == bound["task_id"]
    assert envelope["display"]["session_id"] == bound["session_id"]
    assert envelope["markdown"] == "\n".join(envelope["display"]["display_lines"])
    raw = json.dumps(envelope)
    assert str(artifact_dir) not in raw
    assert scan_for_leak(envelope) is None


def test_valid_config_with_multiple_entries_binds_each(monkeypatch, tmp_path):
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"
    dir_a.mkdir()
    dir_b.mkdir()
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(
        _FILE_ENV,
        _write_bindings_file(
            tmp_path,
            {
                "bindings": [
                    _entry(str(dir_a), task_id="task_live_a", artifact_ref="artifact_live_a"),
                    _entry(str(dir_b), task_id="task_live_b", artifact_ref="artifact_live_b"),
                ]
            },
        ),
    )
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _BOUND
    assert summary["binding_count"] == 2
    task_ids = [b["task_id"] for b in summary["bindings"]]
    session_ids = [b["session_id"] for b in summary["bindings"]]
    assert task_ids == ["task_live_a", "task_live_b"]
    assert len(set(session_ids)) == 2


def test_empty_bindings_list_binds_empty_safe_service(monkeypatch, tmp_path):
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, _write_bindings_file(tmp_path, {"bindings": []}))
    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _BOUND
    assert summary["binding_count"] == 0
    assert tool_mod._bound_service() is not None
    # Queries against the empty service fail closed with the LS4-A stable code.
    result = _call_tool({"task_id": "task_alpha", "session_id": "sess_x"})
    assert result == {"error": "runtime_invalid_live_progress_query"}


def test_rebind_is_idempotent_and_replaces_service(monkeypatch, tmp_path):
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(_FILE_ENV, _write_bindings_file(tmp_path, {"bindings": [_entry(str(artifact_dir))]}))
    first = binding_mod.bind_live_progress_display_from_env()
    service_one = tool_mod._bound_service()
    second = binding_mod.bind_live_progress_display_from_env()
    service_two = tool_mod._bound_service()
    assert first["code"] == second["code"] == _BOUND
    assert service_one is not None and service_two is not None
    assert service_two is not service_one


# --------------------------------------------------------------------------- #
# D. Static boundaries — wired into the runner, no forbidden imports, no shim
# --------------------------------------------------------------------------- #
def test_binding_module_source_boundaries():
    src = Path(binding_mod.__file__).read_text(encoding="utf-8")
    # No top-level (or any) direct import of the ARS producer library — it is
    # reached only lazily inside DefaultLiveProgressReader.
    assert re.search(r"(?m)^\s*(import|from)\s+agent_run_supervisor", src) is None
    # The source-path shim is retired: the producer resolves only from the
    # installed exact-pinned distribution, never a sys.path-injected checkout.
    assert "sys.path" not in src
    assert "SRC_PATH" not in src
    lowered = src.lower()
    for token in ("subprocess", "os.system", ".popen(", "socket.socket", "create_subprocess"):
        assert token not in lowered, token
    import_lines = [ln for ln in src.splitlines() if ln.startswith(("import ", "from "))]
    for line in import_lines:
        for root in ("subprocess", "socket", "temporal", "feishu", "lark", "httpx", "requests"):
            assert root not in line, f"forbidden import {root!r}: {line!r}"


def test_gateway_runner_wires_binding_behind_guard():
    run_src = Path(importlib.import_module("gateway.run").__file__).read_text(encoding="utf-8")
    assert "bind_live_progress_display_from_env" in run_src


# --------------------------------------------------------------------------- #
# E. Real caller-API end-to-end smoke (skipped when the distribution is absent)
# --------------------------------------------------------------------------- #
@_requires_real_api
def test_real_api_end_to_end_display_available(monkeypatch, tmp_path):
    """Acceptance 3+4: real reader, real task/session, available display."""

    artifact_dir = tmp_path / "ars_run"
    artifact_dir.mkdir()
    _write_progress(artifact_dir, state="running", last_seq=3, event_count=3)
    _write_events(
        artifact_dir,
        [
            _event(1, "run_started", kind="lifecycle", text_length=0),
            _event(2, "tool_started", kind="read", text_length=42),
            _event(3, "agent_message", kind="assistant", text_length=120),
        ],
    )
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(
        _FILE_ENV, _write_bindings_file(tmp_path, {"bindings": [_entry(str(artifact_dir))]})
    )

    summary = binding_mod.bind_live_progress_display_from_env()
    assert summary["code"] == _BOUND
    (bound,) = summary["bindings"]

    invalidate_check_fn_cache()
    definitions = registry.get_definitions({_TOOL})
    assert [d["function"]["name"] for d in definitions] == [_TOOL]

    raw = registry.dispatch(
        _TOOL, {"task_id": bound["task_id"], "session_id": bound["session_id"]}
    )
    envelope = json.loads(raw)
    assert set(envelope) == {"type", "display", "markdown"}
    assert envelope["type"] == "live_progress_display.v1"
    display = envelope["display"]
    assert display["task_id"] == bound["task_id"]
    assert display["session_id"] == bound["session_id"]
    assert display["artifact_ref"] == "artifact_live_smoke_0"
    assert display["task_status"] == "running"
    assert display["progress_available"] is True
    assert display["progress_error_code"] is None
    assert display["progress_event_count"] == 3
    assert display["observed_event_count"] == 3
    # A fully-read page's next_cursor is the last seq (or a legitimate None).
    assert display["resume_cursor"] in (3, None)
    assert envelope["markdown"] == "\n".join(display["display_lines"])

    # Refs/counts/status only — never the private dir, raw text, or markers.
    assert scan_for_leak(envelope) is None
    assert str(artifact_dir) not in raw
    assert "summary" not in json.dumps(display)
    assert "unbound" not in raw
    assert "HERMES_RICH_RESULT_JSON_BEGIN" not in raw


@_requires_real_api
def test_real_api_after_seq_override_pages_forward(monkeypatch, tmp_path):
    artifact_dir = tmp_path / "ars_run"
    artifact_dir.mkdir()
    _write_progress(artifact_dir, last_seq=5, event_count=5)
    _write_events(artifact_dir, [_event(i, "tool", text_length=i) for i in range(1, 6)])
    monkeypatch.setenv(_SURFACE_ENV, "hermes_internal")
    monkeypatch.setenv(
        _FILE_ENV, _write_bindings_file(tmp_path, {"bindings": [_entry(str(artifact_dir))]})
    )
    summary = binding_mod.bind_live_progress_display_from_env()
    (bound,) = summary["bindings"]

    envelope = _call_tool(
        {
            "task_id": bound["task_id"],
            "session_id": bound["session_id"],
            "after_seq": 2,
            "limit": 2,
        }
    )
    display = envelope["display"]
    assert display["progress_available"] is True
    assert display["observed_event_count"] == 2
    assert display["resume_cursor"] == 4
    assert display["has_more"] is True
