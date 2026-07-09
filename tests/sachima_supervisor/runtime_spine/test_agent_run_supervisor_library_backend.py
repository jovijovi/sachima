"""ARS-INT — real agent-run-supervisor *library* backend behind the port seam.

Tests for the default-off :class:`AgentRunSupervisorLibraryConfig` gate and the
:class:`AgentRunSupervisorLibraryBackend` (an ``AgentRunSupervisorBackend``
implementation driven by an injected library facade). Everything here is pure
local/offline: the default test path injects deterministic facade doubles and
imports no ``agent_run_supervisor`` module; no acpx, AGENT, subprocess, socket,
Gateway, Feishu, or Temporal surface is started. Forbidden terms in this prose
are no-leak boundary canaries only, never behavior.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sachima_supervisor.runtime_spine import (
    LaunchSpec,
    SpineError,
    TaskRegistry,
    build_launch_spec,
    scan_for_leak,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend import (
    ARS_LIBRARY_CONFIG_TYPE,
    ARS_LIBRARY_STABLE_CODES,
    RUNTIME_ARS_LIBRARY_DISABLED,
    RUNTIME_ARS_LIBRARY_UNAVAILABLE,
    RUNTIME_INVALID_ARS_LIBRARY_CONFIG,
    AgentRunSupervisorLibraryBackend,
    AgentRunSupervisorLibraryConfig,
    derive_ars_session_id,
    derive_backend_handle,
    validate_agent_run_supervisor_library_config,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    RUNTIME_SUPERVISOR_BACKEND_FAILURE,
    AgentRunSupervisorBackend,
    AgentRunSupervisorPort,
)
from sachima_supervisor.runtime_spine.execution_port import RUNTIME_INVALID_SESSION

# --------------------------------------------------------------------------- #
# Config fixtures
# --------------------------------------------------------------------------- #


def _role_mapping(acpx_binary: str | None = None) -> dict[str, Any]:
    """A minimal read-only persistent role mapping (shape-level, ARS-agnostic)."""

    return {
        "schema_version": 1,
        "role_id": "readonly-reviewer",
        "display_name": "Read-only reviewer",
        "description": "Read-only supervised reviewer role.",
        "runner": {
            "type": "acpx",
            "acpx_version": "0.12.0",
            "acpx_binary": acpx_binary,
            "adapter_agent": "codex",
            "model": "gpt-5.5[low]",
        },
        "workspace": {
            "default_cwd": "/srv/ars-int/work",
            "allowed_roots": ["/srv/ars-int/work"],
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
        "session": {"strategy": "persistent"},
        "limits": {
            "timeout_seconds": 60,
            "max_turns": 1,
            "max_output_bytes": 10_485_760,
        },
        "prompt": {"role_instruction": "Be brief.", "output_contract": "Text."},
        "redaction": {
            "suppress_reads": True,
            "redact_prompt": True,
            "redact_stderr": True,
            "redact_metadata": True,
            "redact_env": True,
        },
    }


@pytest.fixture()
def acpx_binary(tmp_path: Path) -> str:
    binary = tmp_path / "bin" / "acpx"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    return str(binary)


def _config_kwargs(tmp_path: Path, default_acpx: str, **overrides: Any) -> dict[str, Any]:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    kwargs: dict[str, Any] = {
        "type": ARS_LIBRARY_CONFIG_TYPE,
        "enabled": True,
        "approval_ref": "approval_arsint_s2",
        "sessions_dir": str(tmp_path / "sessions"),
        "workspace_by_ref": {"ws_arsint": str(work)},
        "role_by_ref": {"policy_read_only": _role_mapping()},
        "session_prefix": "sachima",
        "acpx_binary": default_acpx,
        "stale_after_seconds": 900,
    }
    kwargs.update(overrides)
    return kwargs


@pytest.fixture()
def valid_config(tmp_path: Path, acpx_binary: str) -> AgentRunSupervisorLibraryConfig:
    return AgentRunSupervisorLibraryConfig(**_config_kwargs(tmp_path, acpx_binary))


# --------------------------------------------------------------------------- #
# A. Config gate — default-off, exact, fail-closed
# --------------------------------------------------------------------------- #


def test_stable_code_family_is_closed() -> None:
    assert ARS_LIBRARY_STABLE_CODES == frozenset(
        {
            RUNTIME_ARS_LIBRARY_DISABLED,
            RUNTIME_ARS_LIBRARY_UNAVAILABLE,
            RUNTIME_INVALID_ARS_LIBRARY_CONFIG,
        }
    )


def test_valid_config_constructs_and_validates(valid_config) -> None:
    assert validate_agent_run_supervisor_library_config(valid_config) is valid_config
    assert valid_config.enabled is True


def test_enabled_defaults_to_false(tmp_path: Path, acpx_binary: str) -> None:
    kwargs = _config_kwargs(tmp_path, acpx_binary)
    kwargs.pop("enabled")
    config = AgentRunSupervisorLibraryConfig(**kwargs)
    assert config.enabled is False


def test_backend_construction_fails_closed_when_disabled(
    tmp_path: Path, acpx_binary: str
) -> None:
    config = AgentRunSupervisorLibraryConfig(
        **_config_kwargs(tmp_path, acpx_binary, enabled=False)
    )
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryBackend(config)
    assert exc.value.code == RUNTIME_ARS_LIBRARY_DISABLED


@pytest.mark.parametrize("enabled", [1, "true", None])
def test_non_bool_enabled_fails_closed(tmp_path, acpx_binary, enabled) -> None:
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, enabled=enabled)
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


def test_forged_type_tag_fails_closed(tmp_path, acpx_binary) -> None:
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, type="sachima.other.v1")
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


@pytest.mark.parametrize(
    "approval_ref",
    ["", "arsint", "approval-arsint", "Approval_X", "approval_" + "x" * 200, None],
)
def test_bad_approval_ref_fails_closed(tmp_path, acpx_binary, approval_ref) -> None:
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, approval_ref=approval_ref)
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


@pytest.mark.parametrize("sessions_dir", ["", "relative/dir", None])
def test_bad_sessions_dir_fails_closed(tmp_path, acpx_binary, sessions_dir) -> None:
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, sessions_dir=sessions_dir)
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


def test_repo_internal_sessions_dir_fails_closed(tmp_path, acpx_binary) -> None:
    repo_internal = str(Path(__file__).resolve().parents[3] / "scratch_sessions")
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, sessions_dir=repo_internal)
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


@pytest.mark.parametrize(
    "workspace_by_ref",
    [
        {},
        {"workspace_alpha": "/srv/w"},
        {"ws_UPPER": "/srv/w"},
        {"ws_ok": ""},
        {"ws_ok": "relative"},
        "not-a-mapping",
    ],
)
def test_bad_workspace_map_fails_closed(tmp_path, acpx_binary, workspace_by_ref) -> None:
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, workspace_by_ref=workspace_by_ref)
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


def test_role_map_requires_policy_prefix(tmp_path, acpx_binary) -> None:
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(
                tmp_path, acpx_binary, role_by_ref={"role_read": _role_mapping()}
            )
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


@pytest.mark.parametrize(
    "capability", ["write", "execute", "terminal", "delete", "move", "fetch", "other"]
)
def test_write_capable_role_mapping_fails_closed(tmp_path, acpx_binary, capability) -> None:
    mapping = _role_mapping()
    mapping["permissions"][capability] = True
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, role_by_ref={"policy_x": mapping})
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


def test_non_persistent_role_strategy_fails_closed(tmp_path, acpx_binary) -> None:
    mapping = _role_mapping()
    mapping["session"] = {"strategy": "exec"}
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, role_by_ref={"policy_x": mapping})
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


def test_forbidden_surface_marker_in_role_fails_closed(tmp_path, acpx_binary) -> None:
    mapping = _role_mapping()
    mapping["prompt"]["role_instruction"] = "post results via web" + "hook"
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, role_by_ref={"policy_x": mapping})
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


def test_missing_acpx_pin_fails_closed(tmp_path, acpx_binary) -> None:
    # Neither a config-level pin nor a role-level pin: the npx fetch path must
    # be structurally unreachable, so validation refuses.
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, acpx_binary=None)
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


def test_launcher_basename_acpx_pin_fails_closed(tmp_path, acpx_binary) -> None:
    launcher = tmp_path / "bin" / "npx"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, acpx_binary=str(launcher))
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


def test_missing_acpx_binary_file_fails_closed(tmp_path, acpx_binary) -> None:
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(
                tmp_path, acpx_binary, acpx_binary=str(tmp_path / "bin" / "missing")
            )
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


def test_conflicting_role_and_config_acpx_pins_fail_closed(tmp_path, acpx_binary) -> None:
    other = tmp_path / "bin" / "acpx-other"
    other.write_text("#!/bin/sh\n", encoding="utf-8")
    mapping = _role_mapping(acpx_binary=str(other))
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, role_by_ref={"policy_x": mapping})
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


@pytest.mark.parametrize("prefix", ["", "Sachima", "sa-chima", "9x", None])
def test_bad_session_prefix_fails_closed(tmp_path, acpx_binary, prefix) -> None:
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, session_prefix=prefix)
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


@pytest.mark.parametrize("stale", [0, -1, True, "900", 10**9])
def test_bad_stale_after_seconds_fails_closed(tmp_path, acpx_binary, stale) -> None:
    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorLibraryConfig(
            **_config_kwargs(tmp_path, acpx_binary, stale_after_seconds=stale)
        )
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


def test_config_repr_never_leaks_private_paths(valid_config, tmp_path) -> None:
    surface = repr(valid_config) + str(valid_config)
    assert str(tmp_path) not in surface
    assert valid_config.sessions_dir not in surface
    assert "approval_arsint_s2" in surface  # safe fields stay debuggable


def test_config_has_no_serialization_surface(valid_config) -> None:
    for attr in ("as_dict", "to_dict", "serialize", "json"):
        assert not hasattr(valid_config, attr)


def test_config_mutation_is_rejected(valid_config) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        valid_config.enabled = False  # type: ignore[misc]


def test_config_is_insulated_from_caller_mutation(tmp_path, acpx_binary) -> None:
    kwargs = _config_kwargs(tmp_path, acpx_binary)
    role_map = kwargs["role_by_ref"]
    config = AgentRunSupervisorLibraryConfig(**kwargs)
    role_map["policy_read_only"]["permissions"]["write"] = True
    kwargs["workspace_by_ref"]["ws_arsint"] = "/srv/hijacked"
    assert validate_agent_run_supervisor_library_config(config) is config


def test_forged_config_object_fails_closed(valid_config) -> None:
    forged = object.__new__(AgentRunSupervisorLibraryConfig)
    for field in dataclasses.fields(AgentRunSupervisorLibraryConfig):
        object.__setattr__(forged, field.name, getattr(valid_config, field.name))
    object.__setattr__(forged, "enabled", True)
    object.__setattr__(forged, "approval_ref", "approval_ok")
    object.__setattr__(forged, "session_prefix", "bad prefix with spaces")
    with pytest.raises(SpineError) as exc:
        validate_agent_run_supervisor_library_config(forged)
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG


def test_hostile_config_subclass_fails_closed(tmp_path, acpx_binary) -> None:
    class Hostile(AgentRunSupervisorLibraryConfig):
        def __post_init__(self) -> None:  # skip validation
            pass

    hostile = Hostile(**_config_kwargs(tmp_path, acpx_binary))
    with pytest.raises(SpineError) as exc:
        validate_agent_run_supervisor_library_config(hostile)
    assert exc.value.code == RUNTIME_INVALID_ARS_LIBRARY_CONFIG
    with pytest.raises(SpineError):
        AgentRunSupervisorLibraryBackend(hostile)


def test_session_id_and_handle_derivation_is_deterministic_and_safe(valid_config) -> None:
    ars_id_one = derive_ars_session_id(valid_config, "task_alpha")
    ars_id_two = derive_ars_session_id(valid_config, "task_alpha")
    handle = derive_backend_handle("task_alpha")
    assert ars_id_one == ars_id_two
    assert ars_id_one.startswith("sachima_")
    assert re.fullmatch(r"[a-z][a-z0-9_]*", ars_id_one)
    assert handle == derive_backend_handle("task_alpha")
    assert handle.startswith("arsh_")
    assert re.fullmatch(r"[a-z][a-z0-9_]*", handle)
    assert derive_backend_handle("task_beta") != handle


# --------------------------------------------------------------------------- #
# B. Backend behavior over injected facade doubles (no ARS import, no spawn)
# --------------------------------------------------------------------------- #

from sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend import (  # noqa: E402
    LibraryTurnResult,
    LibraryUnavailableError,
)


def _view(
    *,
    exists: bool = True,
    state: str | None = "open",
    lease_held: bool = False,
    holder_liveness: str | None = None,
    lease_recoverable: bool = False,
    latest_turn_status: str | None = None,
    progress: Any = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        exists=exists,
        state=state,
        lease_held=lease_held,
        holder_liveness=holder_liveness,
        lease_recoverable=lease_recoverable,
        latest_turn_status=latest_turn_status,
        progress=progress,
    )


def _progress(state: str = "running", updated_at: str = "2026-07-09T10:00:00+00:00"):
    return SimpleNamespace(state=state, updated_at=updated_at)


class _FakeFacade:
    """Deterministic in-memory double of the backend's library facade."""

    def __init__(self) -> None:
        self.records: dict[str, SimpleNamespace] = {}
        self.views: dict[str, SimpleNamespace] = {}
        self.role_hashes: dict[str, str] = {}
        self.created: list[str] = []
        self.sent: list[tuple[str, str]] = []
        self.aborts: list[str] = []
        self.closes: list[str] = []
        self.compiled: list[str] = []
        self.binding_ok = True
        self.send_result: tuple[str, str, str] = (
            "turn_20260709T100000Z_ab12cd34",
            "/srv/private/turns/turn_20260709T100000Z_ab12cd34",
            "completed",
        )
        self.send_error: BaseException | None = None
        self.abort_error: BaseException | None = None
        self.inspect_error: BaseException | None = None

    # role/workspace ------------------------------------------------------
    def load_role(self, mapping):
        return SimpleNamespace(role_id=mapping.get("role_id", "role"), mapping=mapping)

    def role_hash(self, role) -> str:
        return self.role_hashes.get(role.role_id, f"hash_{role.role_id}")

    def validate_workspace(self, role, work_dir: str):
        return SimpleNamespace(effective_cwd=work_dir)

    # store ----------------------------------------------------------------
    def open_record(self, sessions_dir: str, ars_session_id: str):
        return self.records.get(ars_session_id)

    def binding_matches(self, sessions_dir, record, role, workspace) -> bool:
        return self.binding_ok

    def create_session(self, sessions_dir, role, ars_session_id, session_name, work_dir):
        self.created.append(ars_session_id)
        self.records[ars_session_id] = SimpleNamespace(
            state="open", role_hash=self.role_hash(role)
        )
        # A freshly created real session inspects as an open, turn-less view.
        self.views.setdefault(ars_session_id, _view())

    # runtime ----------------------------------------------------------------
    def send(self, sessions_dir, role, ars_session_id, prompt, work_dir):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append((ars_session_id, prompt))
        return self.send_result

    def abort(self, sessions_dir, role, ars_session_id, work_dir) -> bool:
        if self.abort_error is not None:
            raise self.abort_error
        self.aborts.append(ars_session_id)
        return True

    def close(self, sessions_dir, role, ars_session_id, work_dir) -> None:
        self.closes.append(ars_session_id)
        record = self.records.get(ars_session_id)
        if record is not None:
            record.state = "closed"

    def compile_goal(self, role, goal_text: str) -> str:
        self.compiled.append(goal_text)
        return f"[goal-contract/v1] Standing goal for this supervised run:\n\n{goal_text}"

    # inspection -------------------------------------------------------------
    def inspect(self, sessions_dir: str, ars_session_id: str):
        if self.inspect_error is not None:
            raise self.inspect_error
        return self.views.get(ars_session_id)


_REFS = ("ws_arsint", "policy_read_only")


def _backend(valid_config, facade=None, **kwargs):
    facade = facade if facade is not None else _FakeFacade()
    return (
        AgentRunSupervisorLibraryBackend(valid_config, facade=facade, **kwargs),
        facade,
    )


def test_backend_satisfies_port_protocol(valid_config) -> None:
    backend, _ = _backend(valid_config)
    assert isinstance(backend, AgentRunSupervisorBackend)


def test_create_or_attach_creates_session_and_returns_safe_handle(
    valid_config,
) -> None:
    backend, facade = _backend(valid_config)
    handle = backend.create_or_attach("task_alpha", _REFS)
    assert handle == derive_backend_handle("task_alpha")
    assert facade.created == [derive_ars_session_id(valid_config, "task_alpha")]
    ars_id = facade.created[0]
    facade.views[ars_id] = _view()
    assert backend.status(handle) == "running"


def test_create_or_attach_is_idempotent_per_task(valid_config) -> None:
    backend, facade = _backend(valid_config)
    first = backend.create_or_attach("task_alpha", _REFS)
    second = backend.create_or_attach("task_alpha", _REFS)
    assert first == second
    assert len(facade.created) == 1


def test_create_or_attach_attaches_existing_open_record_without_create(
    valid_config,
) -> None:
    backend, facade = _backend(valid_config)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.records[ars_id] = SimpleNamespace(state="open", role_hash="hash_readonly-reviewer")
    handle = backend.create_or_attach("task_alpha", _REFS)
    assert handle == derive_backend_handle("task_alpha")
    assert facade.created == []


def test_create_or_attach_refuses_closed_record(valid_config) -> None:
    backend, facade = _backend(valid_config)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.records[ars_id] = SimpleNamespace(state="closed", role_hash="hash_readonly-reviewer")
    with pytest.raises(SpineError) as exc:
        backend.create_or_attach("task_alpha", _REFS)
    assert exc.value.code == RUNTIME_INVALID_SESSION
    assert facade.created == []


def test_create_or_attach_refuses_binding_drift(valid_config) -> None:
    backend, facade = _backend(valid_config)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.records[ars_id] = SimpleNamespace(state="open", role_hash="hash_readonly-reviewer")
    facade.binding_ok = False
    with pytest.raises(SpineError) as exc:
        backend.create_or_attach("task_alpha", _REFS)
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE


@pytest.mark.parametrize(
    "refs",
    [
        (),
        ("ws_arsint",),
        ("policy_read_only",),
        ("ws_unknown", "policy_read_only"),
        ("ws_arsint", "policy_unknown"),
    ],
)
def test_create_or_attach_requires_resolvable_refs(valid_config, refs) -> None:
    backend, facade = _backend(valid_config)
    with pytest.raises(SpineError):
        backend.create_or_attach("task_alpha", refs)
    assert facade.created == []


def test_attach_existing_fails_closed_without_record(valid_config) -> None:
    backend, _ = _backend(valid_config)
    with pytest.raises(SpineError) as exc:
        backend.attach_existing("task_alpha")
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_attach_existing_rebinds_from_record_role_hash(valid_config) -> None:
    backend, facade = _backend(valid_config)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.records[ars_id] = SimpleNamespace(state="open", role_hash="hash_readonly-reviewer")
    handle = backend.attach_existing("task_alpha")
    assert handle == derive_backend_handle("task_alpha")
    facade.views[ars_id] = _view(latest_turn_status="completed", state="closed")
    assert backend.status(handle) == "completed"


def test_attach_existing_refuses_unmatchable_binding(valid_config) -> None:
    backend, facade = _backend(valid_config)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.records[ars_id] = SimpleNamespace(state="open", role_hash="hash_of_foreign_role")
    facade.binding_ok = False
    with pytest.raises(SpineError) as exc:
        backend.attach_existing("task_alpha")
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE


def test_status_unknown_handle_fails_closed(valid_config) -> None:
    backend, _ = _backend(valid_config)
    with pytest.raises(SpineError) as exc:
        backend.status("arsh_deadbeefdeadbeef")
    assert exc.value.code == RUNTIME_INVALID_SESSION


# ---- §6.1 state synthesis matrix ------------------------------------------ #

_T_NOW = "2026-07-09T12:00:00+00:00"


@pytest.mark.parametrize(
    "view_kwargs, expected",
    [
        # row 1: terminal completed turn + closed session
        (dict(state="closed", latest_turn_status="completed"), "completed"),
        # row 2: every failing turn status maps failed (open or closed)
        (dict(latest_turn_status="runner_error"), "failed"),
        (dict(latest_turn_status="invalid_invocation"), "failed"),
        (dict(latest_turn_status="timed_out"), "failed"),
        (dict(latest_turn_status="no_session"), "failed"),
        (dict(latest_turn_status="permission_denied"), "failed"),
        (dict(latest_turn_status="protocol_error"), "failed"),
        (dict(latest_turn_status="infrastructure_error"), "failed"),
        (dict(latest_turn_status="policy_error"), "failed"),
        (dict(state="closed", latest_turn_status="no_op"), "failed"),
        # no_op is never success even while open (S2 semantics)
        (dict(latest_turn_status="no_op"), "failed"),
        # row 3: interrupted turn maps cancelled
        (dict(latest_turn_status="interrupted"), "cancelled"),
        # row 4: closed without a decidable terminal turn is honest ambiguity
        (dict(state="closed"), "ambiguous"),
        (dict(state=None), "ambiguous"),
        # row 5: held lease with a provably crashed holder is orphaned
        (
            dict(lease_held=True, holder_liveness="crashed", lease_recoverable=True),
            "orphaned",
        ),
        # a live or unproven holder is NOT orphaned
        (dict(lease_held=True, holder_liveness="alive"), "running"),
        (dict(lease_held=True, holder_liveness="unknown"), "running"),
        # row 6: no lease + stale running progress is orphaned
        (
            dict(progress=_progress(state="running", updated_at="2026-07-09T10:00:00+00:00")),
            "orphaned",
        ),
        # fresh progress stays running
        (
            dict(progress=_progress(state="running", updated_at="2026-07-09T11:56:00+00:00")),
            "running",
        ),
        # unparseable freshness never fabricates an orphan
        (
            dict(progress=_progress(state="running", updated_at="not-a-time")),
            "running",
        ),
        # row 7 (phase B forward-compat): permission wait from progress
        (
            dict(progress=_progress(state="waiting_for_permission", updated_at=_T_NOW)),
            "waiting_for_permission",
        ),
        # row 8: open session, idle or in flight
        (dict(), "running"),
        (dict(latest_turn_status="completed"), "running"),
    ],
)
def test_state_synthesis_matrix(valid_config, view_kwargs, expected) -> None:
    backend, facade = _backend(
        valid_config,
        clock=lambda: __import__("datetime").datetime.fromisoformat(_T_NOW),
    )
    handle = backend.create_or_attach("task_alpha", _REFS)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.views[ars_id] = _view(**view_kwargs)
    assert backend.status(handle) == expected
    assert backend.liveness(handle) == expected


def test_ledger_turn_status_takes_precedence_over_disk(valid_config) -> None:
    backend, facade = _backend(valid_config)
    handle = backend.create_or_attach("task_alpha", _REFS)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.views[ars_id] = _view(latest_turn_status=None)
    facade.send_result = ("turn_x", "/srv/private/turn_x", "no_op")
    backend.run_turn("task_alpha", turn_kind="prompt", payload_text="do nothing")
    assert backend.status(handle) == "failed"


def test_inspect_failure_collapses_to_backend_failure_and_recovers(valid_config) -> None:
    backend, facade = _backend(valid_config)
    handle = backend.create_or_attach("task_alpha", _REFS)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.inspect_error = RuntimeError("store exploded with /private/path detail")
    with pytest.raises(SpineError) as exc:
        backend.status(handle)
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE
    assert "/private/path" not in str(exc.value)
    facade.inspect_error = None
    facade.views[ars_id] = _view()
    assert backend.status(handle) == "running"


def test_missing_view_fails_closed(valid_config) -> None:
    backend, facade = _backend(valid_config)
    handle = backend.create_or_attach("task_alpha", _REFS)
    facade.views.clear()  # the session's on-disk view has vanished
    with pytest.raises(SpineError) as exc:
        backend.status(handle)
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE


def test_signal_is_fail_closed_in_phase_a(valid_config) -> None:
    backend, facade = _backend(valid_config)
    handle = backend.create_or_attach("task_alpha", _REFS)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.views[ars_id] = _view(
        progress=_progress(state="waiting_for_permission")
    )
    assert backend.status(handle) == "waiting_for_permission"
    with pytest.raises(SpineError) as exc:
        backend.signal(handle, "decision_allow")
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE


def test_kill_aborts_closes_and_reports_cancelled(valid_config) -> None:
    backend, facade = _backend(valid_config)
    handle = backend.create_or_attach("task_alpha", _REFS)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.views[ars_id] = _view()
    assert backend.kill(handle, "ref_cancelled") == "cancelled"
    assert facade.aborts == [ars_id]
    assert facade.closes == [ars_id]
    assert backend.status(handle) == "cancelled"
    assert backend.liveness(handle) == "cancelled"


def test_kill_tolerates_abort_failure_but_still_closes(valid_config) -> None:
    backend, facade = _backend(valid_config)
    handle = backend.create_or_attach("task_alpha", _REFS)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.views[ars_id] = _view()
    facade.abort_error = RuntimeError("cancel path broke")
    assert backend.kill(handle, "ref_cancelled") == "cancelled"
    assert facade.closes == [ars_id]


def test_kill_on_terminal_session_returns_existing_state_without_side_effects(
    valid_config,
) -> None:
    backend, facade = _backend(valid_config)
    handle = backend.create_or_attach("task_alpha", _REFS)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.views[ars_id] = _view(state="closed", latest_turn_status="completed")
    assert backend.kill(handle, "ref_cancelled") == "completed"
    assert facade.aborts == []
    assert facade.closes == []


def test_library_unavailable_collapses_to_stable_code(valid_config) -> None:
    backend, facade = _backend(valid_config)
    handle = backend.create_or_attach("task_alpha", _REFS)
    facade.inspect_error = LibraryUnavailableError()
    with pytest.raises(SpineError) as exc:
        backend.status(handle)
    assert exc.value.code == RUNTIME_ARS_LIBRARY_UNAVAILABLE


# ---- run_turn (the dispatcher's single library entry) ---------------------- #


def test_run_turn_prompt_kind_sends_payload_and_updates_ledger(valid_config) -> None:
    backend, facade = _backend(valid_config)
    backend.create_or_attach("task_alpha", _REFS)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    result = backend.run_turn("task_alpha", turn_kind="prompt", payload_text="hello work")
    assert isinstance(result, LibraryTurnResult)
    assert facade.sent == [(ars_id, "hello work")]
    assert result.status == "completed"
    assert result.turn_id == "turn_20260709T100000Z_ab12cd34"
    assert result.turn_index == 1
    second = backend.run_turn("task_alpha", turn_kind="prompt", payload_text="again")
    assert second.turn_index == 2


def test_run_turn_goal_kind_compiles_goal_contract_not_literal_slash(valid_config) -> None:
    backend, facade = _backend(valid_config)
    backend.create_or_attach("task_alpha", _REFS)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    backend.run_turn("task_alpha", turn_kind="goal", payload_text="ship the feature")
    assert facade.compiled == ["ship the feature"]
    ((sent_session, sent_prompt),) = facade.sent
    assert sent_session == ars_id
    assert not sent_prompt.startswith("/goal")
    assert "ship the feature" in sent_prompt


def test_run_turn_unknown_task_fails_closed(valid_config) -> None:
    backend, _ = _backend(valid_config)
    with pytest.raises(SpineError) as exc:
        backend.run_turn("task_alpha", turn_kind="prompt", payload_text="x")
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_run_turn_after_kill_fails_closed(valid_config) -> None:
    backend, facade = _backend(valid_config)
    handle = backend.create_or_attach("task_alpha", _REFS)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.views[ars_id] = _view()
    backend.kill(handle, "ref_cancelled")
    with pytest.raises(SpineError) as exc:
        backend.run_turn("task_alpha", turn_kind="prompt", payload_text="x")
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_run_turn_off_vocabulary_status_fails_closed(valid_config) -> None:
    backend, facade = _backend(valid_config)
    backend.create_or_attach("task_alpha", _REFS)
    facade.send_result = ("turn_x", "/srv/private/turn_x", "made_up_status")
    with pytest.raises(SpineError) as exc:
        backend.run_turn("task_alpha", turn_kind="prompt", payload_text="x")
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE


def test_run_turn_send_crash_collapses_without_leaking(valid_config) -> None:
    backend, facade = _backend(valid_config)
    backend.create_or_attach("task_alpha", _REFS)
    canary = "raw-payload-canary-77aa"
    facade.send_error = RuntimeError("boom with " + canary)
    with pytest.raises(SpineError) as exc:
        backend.run_turn("task_alpha", turn_kind="prompt", payload_text=canary)
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE
    assert canary not in str(exc.value)


def test_backend_surfaces_never_retain_payload_or_private_paths(valid_config) -> None:
    backend, facade = _backend(valid_config)
    backend.create_or_attach("task_alpha", _REFS)
    canary = "payload-canary-93bb"
    result = backend.run_turn("task_alpha", turn_kind="prompt", payload_text=canary)
    assert canary not in repr(result)
    assert result.turn_dir not in repr(result)
    assert canary not in repr(vars(backend))


def test_turn_result_status_is_scan_clean(valid_config) -> None:
    backend, facade = _backend(valid_config)
    backend.create_or_attach("task_alpha", _REFS)
    result = backend.run_turn("task_alpha", turn_kind="prompt", payload_text="x")
    assert scan_for_leak(
        {"turn_id": result.turn_id, "status": result.status, "turn_index": result.turn_index}
    ) is None


# ---- through the real port (regression posture) ---------------------------- #


def _launch_spec(task_id: str = "task_alpha") -> LaunchSpec:
    return build_launch_spec(
        task_id=task_id,
        agent_kind="local_agent",
        mode_flags={"needs_agent": True},
        roles=("read_only",),
        refs=_REFS,
    )


def test_port_over_library_backend_attach_and_reattach(valid_config) -> None:
    registry = TaskRegistry()
    backend, facade = _backend(valid_config)
    port = AgentRunSupervisorPort(registry, backend)
    ref = port.create_or_attach("task_alpha", _launch_spec())
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.views[ars_id] = _view()
    status = port.status(ref)
    assert status.state == "running"

    rebuilt = AgentRunSupervisorPort(registry, backend)
    ref_two = rebuilt.create_or_attach("task_alpha", _launch_spec())
    assert ref_two.session_id == ref.session_id
    attach_events = [
        e for e in registry.log.events_for("task_alpha") if e.event_type == "agent_attached"
    ]
    assert len(attach_events) == 1


def test_port_read_failure_is_transient_and_never_mutates(valid_config) -> None:
    registry = TaskRegistry()
    backend, facade = _backend(valid_config)
    port = AgentRunSupervisorPort(registry, backend)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.views[ars_id] = _view()
    ref = port.create_or_attach("task_alpha", _launch_spec())
    before = registry.log.last_seq("task_alpha")

    facade.inspect_error = RuntimeError("transient store fault")
    with pytest.raises(SpineError) as exc:
        port.status(ref)
    assert exc.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE
    assert registry.log.last_seq("task_alpha") == before

    facade.inspect_error = None
    assert port.status(ref).state == "running"


def test_port_kill_over_library_backend_appends_single_cancelled_event(
    valid_config,
) -> None:
    registry = TaskRegistry()
    backend, facade = _backend(valid_config)
    port = AgentRunSupervisorPort(registry, backend)
    ars_id = derive_ars_session_id(valid_config, "task_alpha")
    facade.views[ars_id] = _view()
    ref = port.create_or_attach("task_alpha", _launch_spec())
    status = port.kill(ref, "ref_cancelled")
    assert status.state == "cancelled"
    cancelled = [
        e for e in registry.log.events_for("task_alpha") if e.event_type == "cancelled"
    ]
    assert len(cancelled) == 1


def test_module_has_no_top_level_ars_import(valid_config) -> None:
    import sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*(import|from)\s+agent_run_supervisor", src) is None
    for token in ("subprocess.", "os.system(", ".popen(", "socket.socket("):
        assert token not in src.lower(), token


def test_double_driven_flow_never_imports_ars(valid_config) -> None:
    import builtins

    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "agent_run_supervisor" or name.startswith("agent_run_supervisor."):
            raise AssertionError("double-driven backend flow must not import ARS")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = _blocking_import
    try:
        backend, facade = _backend(valid_config)
        handle = backend.create_or_attach("task_alpha", _REFS)
        ars_id = derive_ars_session_id(valid_config, "task_alpha")
        facade.views[ars_id] = _view()
        assert backend.status(handle) == "running"
        backend.run_turn("task_alpha", turn_kind="goal", payload_text="do the thing")
        assert backend.kill(handle, "ref_done") == "cancelled"
    finally:
        builtins.__import__ = real_import


# --------------------------------------------------------------------------- #
# C. Real pinned-library contract (skipped when the extra is not installed;
#    still zero subprocess: only local store/record/goal surfaces are touched)
# --------------------------------------------------------------------------- #

import importlib  # noqa: E402


def _real_ars_session_module():
    try:
        return importlib.import_module("agent_run_supervisor.session")
    except Exception:
        return None


_REAL_ARS = _real_ars_session_module()
_requires_real_ars = pytest.mark.skipif(
    _REAL_ARS is None,
    reason=(
        "agent_run_supervisor not importable — install the pinned distribution "
        "via `uv sync --extra dev`; double-driven tests still run"
    ),
)


def _real_role_and_workspace(config, work_dir: str):
    role_mod = importlib.import_module("agent_run_supervisor.role")
    workspace_mod = importlib.import_module("agent_run_supervisor.workspace")
    mapping = json.loads(json.dumps(config.role_by_ref["policy_read_only"]))
    mapping["workspace"] = {
        "default_cwd": work_dir,
        "allowed_roots": [work_dir],
        "allowed_roots_security_boundary": False,
    }
    if mapping["runner"]["acpx_binary"] is None:
        mapping["runner"]["acpx_binary"] = config.acpx_binary
    role = role_mod.load_role(mapping)
    workspace = workspace_mod.validate_effective_cwd(role, work_dir)
    return role, workspace


def _real_config(tmp_path: Path, acpx_binary: str) -> AgentRunSupervisorLibraryConfig:
    work = tmp_path / "work"
    mapping = _role_mapping()
    mapping["workspace"] = {
        "default_cwd": str(work),
        "allowed_roots": [str(work)],
        "allowed_roots_security_boundary": False,
    }
    return AgentRunSupervisorLibraryConfig(
        **_config_kwargs(
            tmp_path, acpx_binary, role_by_ref={"policy_read_only": mapping}
        )
    )


@_requires_real_ars
def test_real_library_attach_existing_fails_closed_without_record(
    tmp_path, acpx_binary, monkeypatch
) -> None:
    import subprocess

    def _forbidden(*args, **kwargs):
        raise AssertionError("routine library-backend path must never spawn")

    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    config = _real_config(tmp_path, acpx_binary)
    backend = AgentRunSupervisorLibraryBackend(config)
    with pytest.raises(SpineError) as exc:
        backend.attach_existing("task_alpha")
    assert exc.value.code == RUNTIME_INVALID_SESSION


@_requires_real_ars
def test_real_library_attach_rebinds_persisted_record_without_spawning(
    tmp_path, acpx_binary, monkeypatch
) -> None:
    import subprocess

    config = _real_config(tmp_path, acpx_binary)
    role, workspace = _real_role_and_workspace(config, str(tmp_path / "work"))
    store = _REAL_ARS.SessionStore(base_dir=Path(config.sessions_dir))
    ars_id = derive_ars_session_id(config, "task_alpha")
    store.create_session(session_id=ars_id, role=role, workspace_result=workspace)

    def _forbidden(*args, **kwargs):
        raise AssertionError("routine library-backend path must never spawn")

    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    backend = AgentRunSupervisorLibraryBackend(config)
    handle = backend.attach_existing("task_alpha")
    assert handle == derive_backend_handle("task_alpha")
    assert backend.status(handle) == "running"
    assert backend.liveness(handle) == "running"


@_requires_real_ars
def test_real_library_status_reports_closed_record_as_ambiguous(
    tmp_path, acpx_binary
) -> None:
    config = _real_config(tmp_path, acpx_binary)
    role, workspace = _real_role_and_workspace(config, str(tmp_path / "work"))
    store = _REAL_ARS.SessionStore(base_dir=Path(config.sessions_dir))
    ars_id = derive_ars_session_id(config, "task_alpha")
    store.create_session(session_id=ars_id, role=role, workspace_result=workspace)
    store.mark_closed(ars_id)

    backend = AgentRunSupervisorLibraryBackend(config)
    handle = backend.attach_existing("task_alpha")
    assert backend.status(handle) == "ambiguous"


@_requires_real_ars
def test_real_library_goal_compilation_is_contract_text_not_literal_slash(
    tmp_path, acpx_binary
) -> None:
    import sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend as mod

    config = _real_config(tmp_path, acpx_binary)
    role, _ = _real_role_and_workspace(config, str(tmp_path / "work"))
    prompt = mod._DefaultLibraryFacade().compile_goal(role, "ship the integration")
    assert not prompt.startswith("/goal")
    assert "goal-contract/v1" in prompt
    assert "GOAL_STATUS" in prompt
    assert "ship the integration" in prompt
