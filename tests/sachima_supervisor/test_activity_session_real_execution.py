"""Phase E-2 bounded real persistent-session execution bridge tests.

These exercise the Sachima-owned local/offline bridge that wires the Phase E
state machine (``create_session`` / ``send_session_turn`` / ``close_session``)
to a real ``agent_run_supervisor.session_runtime.SessionRuntime`` — while
keeping the committed source default-off, fail-closed, CI-safe, and free of any
``agent_run_supervisor`` import at module-import time.

Every runtime touch in these tests goes through an *injected fake backend*; the
real backend (which lazily imports ``agent_run_supervisor``) is never loaded
here, proving the module imports and validates safely without the external
package installed. A separate, explicitly provisioned real smoke (run by the
operator) exercises the default backend.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from inspect import signature
from pathlib import Path
from typing import Any

import pytest

from sachima_supervisor.activity_session_lifecycle import (
    SESSION_INTERRUPT_API_APPROVAL_TOKEN,
    SESSION_LIFECYCLE_APPROVAL_TOKEN,
    CancellationRequest,
    CancellationRequestResult,
    SessionCloseRequest,
    SessionCreateRequest,
    SessionInterruptOutcome,
    SessionInterruptRequest,
    SessionLifecycleStore,
    SessionRecordResult,
    SessionSendRequest,
    SessionWorkOutcome,
    TurnRecordResult,
    apply_session_interrupt,
    close_session,
    create_session,
    list_session_turns,
    query_session,
    request_cancellation,
    send_session_turn,
)
from sachima_supervisor.activity_session_real_execution import (
    _AgentRunSupervisorBackend,
    PHASE_E2_REAL_SESSION_APPROVAL_TOKEN,
    RealPersistentSessionConfig,
    RealSessionExecutionError,
    ResolvedRealSessionConfig,
    bind_close_session,
    bind_open_session,
    bind_run_turn,
    best_effort_close_real_session,
    close_real_persistent_session,
    execute_real_cancellation,
    open_real_persistent_session,
    run_real_persistent_session_turn,
    validate_real_session_config,
)

ROLE_KEY = "sachima.session_worker"
REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_ROLE = REPO_ROOT / "sachima_supervisor" / "roles" / "session_worker_persistent_v1.json"

FORBIDDEN_RENDER_TOKENS = (
    "raw prompt",
    "prompt body",
    "final_message",
    "final message",
    "oc_private",
    "ou_private",
    "card_json",
    "media path",
    "/tmp/",
    "secret token",
    "traceback",
    "gateway",
    "feishu",
    "webhook",
)


# --------------------------------------------------------------------------- #
# Fake backend (lazy runtime stand-in; no agent_run_supervisor import)
# --------------------------------------------------------------------------- #
@dataclass
class FakeBackend:
    """In-process stand-in for the lazy SessionRuntime backend.

    It deliberately mirrors only the *neutral* projection the real backend is
    allowed to surface — never a final message, raw prompt, or tool output.
    """

    acpx_session_id: str = "fakesess0001"
    turn_completed: bool = True
    artifact_count: int = 3
    create_calls: int = 0
    send_calls: int = 0
    close_calls: int = 0
    best_effort_calls: int = 0
    raise_on_create: bool = False
    raise_on_send: bool = False
    raise_on_close: bool = False
    closed: bool = False
    prompts: list[str] = field(default_factory=list)

    def create(self, resolved: ResolvedRealSessionConfig) -> Any:
        from sachima_supervisor.activity_session_real_execution import _RuntimeCreateResult

        self.create_calls += 1
        if self.raise_on_create:
            raise RuntimeError("fake create boom")
        return _RuntimeCreateResult(acpx_session_id=self.acpx_session_id, state="open")

    def send(self, resolved: ResolvedRealSessionConfig, prompt: str) -> Any:
        from sachima_supervisor.activity_session_real_execution import _RuntimeTurnResult

        self.send_calls += 1
        self.prompts.append(prompt)
        if self.raise_on_send:
            raise RuntimeError("fake send boom")
        return _RuntimeTurnResult(
            completed=self.turn_completed,
            status_label="completed" if self.turn_completed else "runner_error",
            turn_id="faketurn0001",
            artifact_count=self.artifact_count,
        )

    def close(self, resolved: ResolvedRealSessionConfig) -> Any:
        from sachima_supervisor.activity_session_real_execution import _RuntimeCloseResult

        self.close_calls += 1
        if self.raise_on_close:
            raise RuntimeError("fake close boom")
        self.closed = True
        return _RuntimeCloseResult(closed=True, state="closed")

    def best_effort_close(self, resolved: ResolvedRealSessionConfig) -> None:
        self.best_effort_calls += 1
        if self.raise_on_close:
            raise RuntimeError("fake best-effort close boom")
        self.closed = True


class ExplodingBackend:
    """Backend whose every method fails the test if invoked.

    Used to prove gate/config failures short-circuit *before* any runtime load.
    """

    def create(self, resolved: ResolvedRealSessionConfig) -> Any:
        raise AssertionError("backend.create must not run when the gate fails closed")

    def send(self, resolved: ResolvedRealSessionConfig, prompt: str) -> Any:
        raise AssertionError("backend.send must not run when the gate fails closed")

    def close(self, resolved: ResolvedRealSessionConfig) -> Any:
        raise AssertionError("backend.close must not run when the gate fails closed")

    def best_effort_close(self, resolved: ResolvedRealSessionConfig) -> None:
        raise AssertionError("backend.best_effort_close must not run on a closed gate")

    def abort(self, resolved: ResolvedRealSessionConfig) -> Any:
        raise AssertionError("backend.abort must not run when the gate fails closed")


# --------------------------------------------------------------------------- #
# WP3b fake abort backend
# --------------------------------------------------------------------------- #
_WP3B_CANCEL_TOKEN_SENTINEL = (
    "approve_agent_run_supervisor_sachima_phase_e2_bounded_real_cancellation_execution_"
    "local_offline_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery"
)


@dataclass
class _FakeAbortResult:
    cancelled: bool
    state: str | None = None


@dataclass
class FakeAbortBackend(FakeBackend):
    """FakeBackend extended with a fake abort() for WP3b cancellation execution tests."""

    abort_calls: int = 0
    abort_cancelled: bool = True
    raise_on_abort: bool = False

    def abort(self, resolved: ResolvedRealSessionConfig) -> Any:
        self.abort_calls += 1
        if self.raise_on_abort:
            raise RuntimeError("fake abort boom")
        return _FakeAbortResult(
            cancelled=self.abort_cancelled,
            state="cancelled" if self.abort_cancelled else "abort_failed",
        )


# --------------------------------------------------------------------------- #
# Role / config builders
# --------------------------------------------------------------------------- #
def _persistent_role(acpx_binary: str | None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "role_id": "sachima.session_worker.persistent",
        "display_name": "Sachima session worker (persistent, read-only)",
        "description": "Local persistent-session worker. Operator overlay pins acpx.",
        "runner": {
            "type": "acpx",
            "acpx_version": "0.10.0",
            "acpx_binary": acpx_binary,
            "adapter_agent": "codex",
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
        "session": {"strategy": "persistent"},
        "limits": {"timeout_seconds": 900, "max_turns": 8, "max_output_bytes": 2000000},
        "prompt": {
            "role_instruction": "Be brief. Read-only review only.",
            "output_contract": "Return the requested token only.",
        },
        "redaction": {
            "suppress_reads": True,
            "redact_prompt": True,
            "redact_stderr": True,
            "redact_metadata": True,
            "redact_env": True,
        },
    }


def _digest_of(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_role(tmp_path: Path, role: dict[str, Any], name: str = "role.json") -> Path:
    role_path = tmp_path / name
    role_path.write_text(json.dumps(role, indent=2), encoding="utf-8")
    return role_path


def _fake_acpx_binary(tmp_path: Path, name: str = "acpx") -> Path:
    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    acpx = bin_dir / name
    acpx.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    acpx.chmod(0o755)
    return acpx


def _config(
    tmp_path: Path,
    *,
    acpx_binary: str | None = None,
    role: dict[str, Any] | None = None,
    enabled: bool = True,
    approval_token: str | None = None,
    acpx_sha256: str | None = None,
    role_file: str | None = None,
    expected_role_digest: str | None = None,
    sessions_dir: str | None = None,
    evidence_dir: str | None = None,
    work_dir: str | None = None,
) -> RealPersistentSessionConfig:
    acpx_path = acpx_binary or str(_fake_acpx_binary(tmp_path))
    role_mapping = role if role is not None else _persistent_role(acpx_path)
    if role_file is None:
        role_path = _write_role(tmp_path, role_mapping)
        role_file = str(role_path)
        digest = _digest_of(role_path)
    else:
        digest = expected_role_digest or _digest_of(Path(role_file))
    work = work_dir or str((tmp_path / "work"))
    Path(work).mkdir(parents=True, exist_ok=True)
    return RealPersistentSessionConfig(
        enabled=enabled,
        approval_token=(
            approval_token if approval_token is not None else PHASE_E2_REAL_SESSION_APPROVAL_TOKEN
        ),
        role_file=role_file,
        expected_role_digest=expected_role_digest or digest,
        sessions_dir=sessions_dir or str(tmp_path / "sessions"),
        evidence_dir=evidence_dir or str(tmp_path / "evidence"),
        work_dir=work,
        runtime_session_id="e2-smoke-session",
        session_name="e2-smoke-session-name",
        acpx_sha256=acpx_sha256,
    )


# --------------------------------------------------------------------------- #
# State-machine request builders (binding threaded by the caller)
# --------------------------------------------------------------------------- #
def _store() -> SessionLifecycleStore:
    store = SessionLifecycleStore()
    store.grant_lease(
        activity_id="activity_e2_001",
        lease_id="lease_e2_001",
        lease_epoch=1,
        lease_holder_ref="controller_ref_sachima_e2",
        state_version=0,
    )
    return store


def _create_request(**overrides: Any) -> SessionCreateRequest:
    base: dict[str, Any] = {
        "activity_id": "activity_e2_001",
        "transaction_ref": "claim_txn_e2_001",
        "operation_ref": "claim_op_e2_001",
        "session_id": "session_e2_001",
        "idempotency_key": "idem_e2_create_001",
        "role_key": ROLE_KEY,
        "approval_token": SESSION_LIFECYCLE_APPROVAL_TOKEN,
        "enabled": True,
        "role_file_digest": "sha256:" + "f" * 64,
        "prompt_ref": "claim_prompt_e2_001",
        "context_refs": ("claim_context_e2_001",),
        "cwd_ref": "workspace_ref_sachima_release",
        "allowed_roots_ref": "allowed_roots_ref_sachima_release",
        "lease_id": "lease_e2_001",
        "lease_epoch": 1,
        "lease_holder_ref": "controller_ref_sachima_e2",
        "expected_state_version": 0,
        "operator_gate": True,
        "max_turns": 4,
        "max_artifacts_per_turn": 8,
    }
    base.update(overrides)
    return SessionCreateRequest(**base)


def _send_request(binding: str, **overrides: Any) -> SessionSendRequest:
    base: dict[str, Any] = {
        "activity_id": "activity_e2_001",
        "session_id": "session_e2_001",
        "transaction_ref": "claim_txn_e2_001",
        "operation_ref": "claim_op_e2_001",
        "idempotency_key": "idem_e2_turn_001",
        "approval_token": SESSION_LIFECYCLE_APPROVAL_TOKEN,
        "enabled": True,
        "session_binding": binding,
        "prompt_ref": "claim_prompt_turn_e2_001",
        "context_refs": ("claim_context_turn_e2_001",),
        "lease_id": "lease_e2_001",
        "lease_epoch": 1,
        "lease_holder_ref": "controller_ref_sachima_e2",
        "expected_state_version": 1,
        "operator_gate": True,
    }
    base.update(overrides)
    return SessionSendRequest(**base)


def _close_request(binding: str, **overrides: Any) -> SessionCloseRequest:
    base: dict[str, Any] = {
        "activity_id": "activity_e2_001",
        "session_id": "session_e2_001",
        "transaction_ref": "claim_txn_e2_001",
        "operation_ref": "claim_op_e2_001",
        "idempotency_key": "idem_e2_close_001",
        "approval_token": SESSION_LIFECYCLE_APPROVAL_TOKEN,
        "enabled": True,
        "session_binding": binding,
        "lease_id": "lease_e2_001",
        "lease_epoch": 1,
        "lease_holder_ref": "controller_ref_sachima_e2",
        "expected_state_version": 2,
        "operator_gate": True,
    }
    base.update(overrides)
    return SessionCloseRequest(**base)


def _assert_no_leaks(state: dict[str, Any]) -> None:
    rendered = repr(state).lower()
    for token in FORBIDDEN_RENDER_TOKENS:
        assert token not in rendered, f"leak token present: {token}"


def _wp3b_cancel_token() -> str:
    """Returns the WP3b cancel token; falls back to sentinel if not yet defined."""
    try:
        from sachima_supervisor.activity_session_real_execution import (
            PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN,
        )
        return PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN
    except (ImportError, AttributeError):
        return _WP3B_CANCEL_TOKEN_SENTINEL


def _cancel_config(tmp_path: Path, **overrides: Any) -> RealPersistentSessionConfig:
    """Config with WP3b cancellation execution approval token."""
    return _config(tmp_path, approval_token=_wp3b_cancel_token(), **overrides)


def _interrupt_request_e2(**overrides: Any) -> SessionInterruptRequest:
    """Minimal SessionInterruptRequest scoped to the e2 test activity."""
    base: dict[str, Any] = {
        "cancel_id": "cancel_e2_wp3b_001",
        "activity_id": "activity_e2_001",
        "session_id": "session_e2_001",
        "transaction_ref": "claim_txn_e2_001",
        "operation_ref": "claim_op_e2_001",
        "idempotency_key": "idem_e2_wp3b_interrupt_001",
        "approval_token": SESSION_INTERRUPT_API_APPROVAL_TOKEN,
        "enabled": True,
        "session_binding": None,
        "requested_by_ref": "operator_ref_wp3b_test",
        "reason_code": "operator_requested_stop",
        "turn_index": None,
        "lease_id": "lease_e2_001",
        "lease_epoch": 1,
        "lease_holder_ref": "controller_ref_sachima_e2",
        "operator_gate": True,
    }
    base.update(overrides)
    return SessionInterruptRequest(**base)


def _e2_cancel_request(binding: str, **overrides: Any) -> CancellationRequest:
    """CancellationRequest for the e2 test session context (request-state only)."""
    base: dict[str, Any] = {
        "cancel_id": "cancel_e2_wp3b_001",
        "activity_id": "activity_e2_001",
        "session_id": "session_e2_001",
        "transaction_ref": "claim_txn_e2_001",
        "operation_ref": "claim_op_e2_001",
        "idempotency_key": "idem_e2_cancel_001",
        "approval_token": SESSION_LIFECYCLE_APPROVAL_TOKEN,
        "enabled": True,
        "session_binding": binding,
        "requested_by_ref": "operator_ref_wp3b_test",
        "reason_code": "operator_requested_stop",
        "turn_index": None,
        "lease_id": "lease_e2_001",
        "lease_epoch": 1,
        "lease_holder_ref": "controller_ref_sachima_e2",
        "operator_gate": True,
        "execute": False,
    }
    base.update(overrides)
    return CancellationRequest(**base)


# --------------------------------------------------------------------------- #
# Import safety
# --------------------------------------------------------------------------- #
def test_module_import_does_not_require_agent_run_supervisor() -> None:
    # Import the bridge in a clean subprocess and prove it never transitively
    # pulls in the external package (which is not installed in normal CI).
    code = (
        "import sys\n"
        "import sachima_supervisor.activity_session_real_execution as m\n"
        "leaked = sorted(k for k in sys.modules if k.startswith('agent_run_supervisor'))\n"
        "assert not leaked, leaked\n"
        "assert m.PHASE_E2_REAL_SESSION_APPROVAL_TOKEN\n"
        "print('import-ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "import-ok" in result.stdout


def test_approval_token_is_the_exact_phase_e2_token() -> None:
    assert PHASE_E2_REAL_SESSION_APPROVAL_TOKEN == (
        "approve_agent_run_supervisor_sachima_phase_e2_bounded_real_persistent_session_"
        "execution_local_offline_smoke_no_live_no_gateway_no_feishu_no_production_config_"
        "no_real_delivery"
    )


def test_phase_e2_token_differs_from_phase_e_state_machine_token() -> None:
    assert PHASE_E2_REAL_SESSION_APPROVAL_TOKEN != SESSION_LIFECYCLE_APPROVAL_TOKEN


# --------------------------------------------------------------------------- #
# Gate fail-closed before runtime load
# --------------------------------------------------------------------------- #
def test_disabled_config_fails_closed_before_runtime_load(tmp_path: Path) -> None:
    config = _config(tmp_path, enabled=False)
    with pytest.raises(RealSessionExecutionError) as exc:
        open_real_persistent_session(_create_request(), config, backend=ExplodingBackend())
    assert exc.value.error_code == "activity_session_disabled"


def test_wrong_token_fails_closed_before_runtime_load(tmp_path: Path) -> None:
    config = _config(tmp_path, approval_token="approve_wrong_scope")
    with pytest.raises(RealSessionExecutionError) as exc:
        open_real_persistent_session(_create_request(), config, backend=ExplodingBackend())
    assert exc.value.error_code == "activity_session_approval_mismatch"


def test_empty_token_fails_closed(tmp_path: Path) -> None:
    config = _config(tmp_path, approval_token="")
    with pytest.raises(RealSessionExecutionError) as exc:
        validate_real_session_config(config)
    assert exc.value.error_code == "activity_session_approval_mismatch"


def test_cancellation_execution_always_fails_closed(tmp_path: Path) -> None:
    # Phase E2 session config (not the WP3b cancel token) must reject cancellation execution.
    config = _config(tmp_path)  # PHASE_E2_REAL_SESSION_APPROVAL_TOKEN — wrong for cancel
    with pytest.raises(RealSessionExecutionError) as exc:
        execute_real_cancellation(_interrupt_request_e2(), config, backend=ExplodingBackend())
    assert exc.value.error_code == "activity_cancel_not_approved"


def test_cancellation_execution_fails_closed_even_when_disabled(tmp_path: Path) -> None:
    # Disabled WP3b cancel config must still fail before any backend touch.
    config = _cancel_config(tmp_path, enabled=False)
    with pytest.raises(RealSessionExecutionError) as exc:
        execute_real_cancellation(_interrupt_request_e2(), config, backend=ExplodingBackend())
    assert exc.value.error_code in {"activity_cancel_not_approved", "activity_session_disabled"}


# --------------------------------------------------------------------------- #
# Config validation: role / runner / binary / paths
# --------------------------------------------------------------------------- #
def test_valid_config_resolves(tmp_path: Path) -> None:
    config = _config(tmp_path)
    resolved = validate_real_session_config(config)
    assert isinstance(resolved, ResolvedRealSessionConfig)
    assert resolved.role_mapping["session"]["strategy"] == "persistent"
    assert Path(resolved.acpx_binary).is_absolute()
    assert resolved.runtime_session_id == "e2-smoke-session"


def test_committed_null_binary_role_is_rejected_non_runnable() -> None:
    # The committed portable role must be non-runnable by construction.
    role = json.loads(COMMITTED_ROLE.read_text(encoding="utf-8"))
    assert role["runner"]["acpx_binary"] is None
    assert role["session"]["strategy"] == "persistent"
    config = RealPersistentSessionConfig(
        enabled=True,
        approval_token=PHASE_E2_REAL_SESSION_APPROVAL_TOKEN,
        role_file=str(COMMITTED_ROLE),
        expected_role_digest=_digest_of(COMMITTED_ROLE),
        sessions_dir="/var/tmp/e2-sessions",
        evidence_dir="/var/tmp/e2-evidence",
        work_dir="/var/tmp/e2-work",
        runtime_session_id="e2-smoke-session",
        session_name="e2-smoke",
    )
    with pytest.raises(RealSessionExecutionError) as exc:
        validate_real_session_config(config)
    assert exc.value.error_code == "activity_runner_provenance_unverified"


@pytest.mark.parametrize("basename", ["npx", "npm", "pnpm", "yarn", "bunx", "bun", "node", "sh", "bash"])
def test_runner_basename_blocklist_rejected(tmp_path: Path, basename: str) -> None:
    config = _config(tmp_path, acpx_binary=f"/usr/local/bin/{basename}")
    with pytest.raises(RealSessionExecutionError) as exc:
        validate_real_session_config(config)
    assert exc.value.error_code == "activity_runner_provenance_unverified"


def test_relative_binary_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path, acpx_binary="node_modules/.bin/acpx")
    with pytest.raises(RealSessionExecutionError) as exc:
        validate_real_session_config(config)
    assert exc.value.error_code == "activity_runner_provenance_unverified"


def test_acpx_sha_mismatch_rejected(tmp_path: Path) -> None:
    acpx = _fake_acpx_binary(tmp_path)
    config = _config(tmp_path, acpx_binary=str(acpx), acpx_sha256="sha256:" + "0" * 64)
    with pytest.raises(RealSessionExecutionError) as exc:
        validate_real_session_config(config)
    assert exc.value.error_code == "activity_runner_provenance_unverified"


def test_acpx_sha_match_accepted(tmp_path: Path) -> None:
    acpx = _fake_acpx_binary(tmp_path)
    sha = "sha256:" + hashlib.sha256(acpx.read_bytes()).hexdigest()
    config = _config(tmp_path, acpx_binary=str(acpx), acpx_sha256=sha)
    resolved = validate_real_session_config(config)
    assert resolved.acpx_binary == str(acpx)


def test_role_digest_mismatch_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path, expected_role_digest="sha256:" + "1" * 64)
    with pytest.raises(RealSessionExecutionError) as exc:
        validate_real_session_config(config)
    assert exc.value.error_code == "activity_runner_provenance_unverified"


def test_non_persistent_strategy_rejected(tmp_path: Path) -> None:
    role = _persistent_role(str(_fake_acpx_binary(tmp_path)))
    role["session"] = {"strategy": "exec"}
    config = _config(tmp_path, role=role)
    with pytest.raises(RealSessionExecutionError) as exc:
        validate_real_session_config(config)
    assert exc.value.error_code == "activity_role_capability_rejected"


@pytest.mark.parametrize(
    "patch",
    [
        {"type": "shell"},
        {"acpx_version": "0.9.0"},
        {"adapter_agent": "claude"},
    ],
)
def test_runner_identity_mismatch_rejected(tmp_path: Path, patch: dict[str, Any]) -> None:
    role = _persistent_role(str(_fake_acpx_binary(tmp_path)))
    role["runner"].update(patch)
    config = _config(tmp_path, role=role)
    with pytest.raises(RealSessionExecutionError) as exc:
        validate_real_session_config(config)
    assert exc.value.error_code == "activity_runner_provenance_unverified"


def test_sessions_dir_inside_repo_rejected(tmp_path: Path) -> None:
    inside = str(REPO_ROOT / "sachima_supervisor" / "e2-sessions-should-not-be-here")
    config = _config(tmp_path, sessions_dir=inside)
    with pytest.raises(RealSessionExecutionError) as exc:
        validate_real_session_config(config)
    assert exc.value.error_code == "activity_precondition_unmet"


def test_gateway_or_feishu_string_in_role_rejected(tmp_path: Path) -> None:
    role = _persistent_role(str(_fake_acpx_binary(tmp_path)))
    role["description"] = "delivers to the feishu gateway webhook"
    config = _config(tmp_path, role=role)
    with pytest.raises(RealSessionExecutionError) as exc:
        validate_real_session_config(config)
    assert exc.value.error_code == "activity_unsafe_material"


# --------------------------------------------------------------------------- #
# Lazy fake-backend lifecycle through the real state machine
# --------------------------------------------------------------------------- #
def test_full_lifecycle_maps_into_state_machine_with_fake_backend(tmp_path: Path) -> None:
    store = _store()
    backend = FakeBackend()
    config = _config(tmp_path)

    create_res = create_session(
        _create_request(), store=store, open_session=bind_open_session(config, backend=backend)
    )
    assert isinstance(create_res, SessionRecordResult)
    assert create_res.ok is True
    assert create_res.lifecycle_state == "session_open"
    binding = create_res.session_binding
    assert binding is not None and binding.startswith("sbind_")
    create_state = create_res.to_durable_state()
    assert create_state["supervisor_status"] == "session_open"
    assert create_state["evidence_digest"].startswith("sha256:")
    _assert_no_leaks(create_state)

    send_res = send_session_turn(
        _send_request(binding),
        store=store,
        run_turn=bind_run_turn(config, "Read-only review turn. Reply with a short token.", backend=backend),
    )
    assert isinstance(send_res, TurnRecordResult)
    assert send_res.ok is True
    assert send_res.status == "completed"
    turn_state = send_res.to_durable_state()
    assert turn_state["artifact_ref_count"] == backend.artifact_count
    _assert_no_leaks(turn_state)

    close_res = close_session(
        _close_request(binding),
        store=store,
        apply_close=bind_close_session(config, backend=backend),
    )
    assert close_res.ok is True
    assert close_res.lifecycle_state == "session_closed"
    _assert_no_leaks(close_res.to_durable_state())

    assert backend.create_calls == 1
    assert backend.send_calls == 1
    assert backend.close_calls == 1
    # The read-only prompt reached the runtime but was never persisted durably.
    assert backend.prompts == ["Read-only review turn. Reply with a short token."]


def test_final_message_and_raw_prompt_never_persisted(tmp_path: Path) -> None:
    store = _store()
    backend = FakeBackend()
    config = _config(tmp_path)

    create_res = create_session(
        _create_request(), store=store, open_session=bind_open_session(config, backend=backend)
    )
    binding = create_res.session_binding
    send_session_turn(
        _send_request(binding),
        store=store,
        run_turn=bind_run_turn(
            config,
            "SECRET FINAL ANSWER text that must never be durably stored",
            backend=backend,
        ),
    )

    for turn in list_session_turns(store, activity_id="activity_e2_001"):
        state = turn.to_durable_state()
        rendered = repr(state).lower()
        assert "secret final answer" not in rendered
        assert "final_message" not in state
        _assert_no_leaks(state)


def test_neutral_turn_result_cannot_carry_a_final_message() -> None:
    from sachima_supervisor.activity_session_real_execution import _RuntimeTurnResult

    fields = set(signature(_RuntimeTurnResult).parameters)
    assert "final_message" not in fields
    assert "prompt" not in fields


def test_open_outcome_is_sanitized_session_work_outcome(tmp_path: Path) -> None:
    config = _config(tmp_path)
    backend = FakeBackend(acpx_session_id="acpxsess-abc-123")
    outcome = open_real_persistent_session(_create_request(), config, backend=backend)
    assert isinstance(outcome, SessionWorkOutcome)
    assert outcome.ok is True
    assert outcome.session_binding is not None
    assert outcome.session_binding.startswith("sbind_")
    # The raw acpx session id is never echoed; only a derived opaque binding.
    assert "acpxsess-abc-123" not in (outcome.session_binding or "")
    assert outcome.evidence_digest is not None and outcome.evidence_digest.startswith("sha256:")


def test_binding_is_deterministic_for_same_acpx_session(tmp_path: Path) -> None:
    config = _config(tmp_path)
    o1 = open_real_persistent_session(
        _create_request(), config, backend=FakeBackend(acpx_session_id="stable-sess")
    )
    o2 = open_real_persistent_session(
        _create_request(), config, backend=FakeBackend(acpx_session_id="stable-sess")
    )
    assert o1.session_binding == o2.session_binding


# --------------------------------------------------------------------------- #
# Failure + cleanup paths
# --------------------------------------------------------------------------- #
def test_create_backend_failure_triggers_best_effort_cleanup_and_failed_outcome(tmp_path: Path) -> None:
    config = _config(tmp_path)
    backend = FakeBackend(raise_on_create=True)
    outcome = open_real_persistent_session(_create_request(), config, backend=backend)
    assert outcome.ok is False
    assert backend.best_effort_calls == 1


def test_failed_turn_maps_to_failed_outcome(tmp_path: Path) -> None:
    config = _config(tmp_path)
    store = _store()
    backend = FakeBackend(turn_completed=False)
    create_res = create_session(
        _create_request(), store=store, open_session=bind_open_session(config, backend=backend)
    )
    send_res = send_session_turn(
        _send_request(create_res.session_binding),
        store=store,
        run_turn=bind_run_turn(config, "read-only", backend=backend),
    )
    assert send_res.ok is False
    assert send_res.status in {"failed_retryable", "failed_terminal"}


def test_replay_does_not_create_extra_runtime_calls(tmp_path: Path) -> None:
    store = _store()
    backend = FakeBackend()
    config = _config(tmp_path)
    open_work = bind_open_session(config, backend=backend)

    first = create_session(_create_request(), store=store, open_session=open_work)
    second = create_session(_create_request(), store=store, open_session=open_work)

    assert first.to_durable_state() == second.to_durable_state()
    assert backend.create_calls == 1


def test_double_close_does_not_double_call_backend(tmp_path: Path) -> None:
    store = _store()
    backend = FakeBackend()
    config = _config(tmp_path)
    create_res = create_session(
        _create_request(), store=store, open_session=bind_open_session(config, backend=backend)
    )
    binding = create_res.session_binding
    close_work = bind_close_session(config, backend=backend)

    # No send in this test, so the session is at state_version 1 after create.
    first = close_session(
        _close_request(binding, expected_state_version=1), store=store, apply_close=close_work
    )
    second = close_session(
        _close_request(binding, expected_state_version=1), store=store, apply_close=close_work
    )

    assert first.lifecycle_state == "session_closed"
    assert second.lifecycle_state == "session_closed"
    assert backend.close_calls == 1


def test_best_effort_close_helper_swallows_backend_errors(tmp_path: Path) -> None:
    config = _config(tmp_path)
    backend = FakeBackend(raise_on_close=True)
    # Must not raise even though the underlying close would fail.
    best_effort_close_real_session(config, backend=backend)


def test_best_effort_close_helper_fails_closed_when_disabled(tmp_path: Path) -> None:
    config = _config(tmp_path, enabled=False)
    backend = ExplodingBackend()
    with pytest.raises(RealSessionExecutionError):
        best_effort_close_real_session(config, backend=backend)


# --------------------------------------------------------------------------- #
# Direct public function signatures
# --------------------------------------------------------------------------- #
def test_public_function_signatures() -> None:
    assert tuple(signature(open_real_persistent_session).parameters)[:2] == ("request", "config")
    assert tuple(signature(run_real_persistent_session_turn).parameters)[:3] == (
        "request",
        "config",
        "prompt",
    )
    assert tuple(signature(close_real_persistent_session).parameters)[:2] == ("request", "config")


# --------------------------------------------------------------------------- #
# Smoke-script wiring (deterministic, fake backend; no acpx required)
# --------------------------------------------------------------------------- #
def _load_smoke_module() -> Any:
    import importlib.util

    path = REPO_ROOT / "scripts" / "sachima_phase_e2_persistent_session_smoke.py"
    spec = importlib.util.spec_from_file_location("e2_smoke_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_run_lifecycle_with_fake_backend(tmp_path: Path) -> None:
    smoke = _load_smoke_module()
    backend = FakeBackend(artifact_count=1)
    config = _config(tmp_path)

    lifecycle = smoke.run_lifecycle(config=config, backend=backend)
    pipeline = lifecycle["execution_pipeline"]
    assert pipeline["create"]["lifecycle_state"] == "session_open"
    assert pipeline["turn"]["status"] == "completed"
    assert pipeline["turn"]["final_message_persisted"] is False
    assert pipeline["close"]["lifecycle_state"] == "session_closed"
    assert lifecycle["business_task"] == {"business_verdict": None, "cancellation_executed": False}

    store = lifecycle["_store"]
    verify = smoke.post_verify(store=store, config=config, mode="self_test")
    smoke.assert_post_verify(verify, mode="self_test")
    assert verify["closed"] is True
    assert verify["turn_count_state_machine"] == 1
    assert verify["npx_in_runner"] is False
    assert backend.create_calls == 1
    assert backend.send_calls == 1
    assert backend.close_calls == 1


def test_smoke_real_post_verify_requires_business_marker(tmp_path: Path) -> None:
    smoke = _load_smoke_module()
    config = _config(tmp_path)
    backend = FakeBackend(artifact_count=1)

    assert config.runtime_session_id is not None
    assert config.sessions_dir is not None
    lifecycle = smoke.run_lifecycle(config=config, backend=backend)
    store = lifecycle["_store"]

    turn_dir = Path(config.sessions_dir) / config.runtime_session_id / "turns" / "turn_001"
    turn_dir.mkdir(parents=True)
    session_json = Path(config.sessions_dir) / config.runtime_session_id / "session.json"
    session_json.parent.mkdir(parents=True, exist_ok=True)
    session_json.write_text(
        json.dumps({"state": "closed", "acpx_version": "0.10.0", "adapter_agent": "codex", "role_id": "sachima.session_worker.persistent"}),
        encoding="utf-8",
    )
    (turn_dir / "result.json").write_text(
        json.dumps({"final_message": smoke.TURN_MARKER}), encoding="utf-8"
    )

    verify = smoke.post_verify(store=store, config=config, mode="real")
    smoke.assert_post_verify(verify, mode="real")
    assert verify["business_marker_checked"] is True
    assert verify["business_marker_matches"] is True


def test_smoke_real_post_verify_rejects_wrong_business_marker(tmp_path: Path) -> None:
    smoke = _load_smoke_module()
    config = _config(tmp_path)
    backend = FakeBackend(artifact_count=1)

    assert config.runtime_session_id is not None
    assert config.sessions_dir is not None
    lifecycle = smoke.run_lifecycle(config=config, backend=backend)
    store = lifecycle["_store"]

    turn_dir = Path(config.sessions_dir) / config.runtime_session_id / "turns" / "turn_001"
    turn_dir.mkdir(parents=True)
    session_json = Path(config.sessions_dir) / config.runtime_session_id / "session.json"
    session_json.parent.mkdir(parents=True, exist_ok=True)
    session_json.write_text(
        json.dumps({"state": "closed", "acpx_version": "0.10.0", "adapter_agent": "codex", "role_id": "sachima.session_worker.persistent"}),
        encoding="utf-8",
    )
    (turn_dir / "result.json").write_text(
        json.dumps({"final_message": "WRONG_MARKER"}), encoding="utf-8"
    )

    verify = smoke.post_verify(store=store, config=config, mode="real")
    with pytest.raises(smoke.SmokeError, match="final_message did not match"):
        smoke.assert_post_verify(verify, mode="real")


# --------------------------------------------------------------------------- #
# WP2: bounded multi-turn session
# --------------------------------------------------------------------------- #
def test_smoke_multi_turn_lifecycle_with_fake_backend(tmp_path: Path) -> None:
    """WP2: run_lifecycle accepts turn_prompts and drives N turns in one session."""
    smoke = _load_smoke_module()
    backend = FakeBackend(artifact_count=1)
    config = _config(tmp_path)

    # Desired WP2 API: turn_prompts drives multiple turns within a single session.
    lifecycle = smoke.run_lifecycle(
        config=config,
        backend=backend,
        turn_prompts=("turn1", "turn2"),
    )

    assert lifecycle.get("turn_count") == 2
    # One session created, two turns sent — no second session opened.
    assert backend.create_calls == 1
    assert backend.send_calls == 2


def test_smoke_post_verify_reports_multi_turn(tmp_path: Path) -> None:
    """WP2: post_verify and assert_post_verify accept and validate N-turn sessions."""
    smoke = _load_smoke_module()
    backend = FakeBackend(artifact_count=1)
    config = _config(tmp_path)

    # Build a 2-turn session manually through the state machine.
    store = SessionLifecycleStore()
    store.grant_lease(
        activity_id=smoke.ACTIVITY_ID,
        lease_id=smoke.LEASE_ID,
        lease_epoch=1,
        lease_holder_ref=smoke.LEASE_HOLDER,
        state_version=0,
    )

    create_res = create_session(
        SessionCreateRequest(
            activity_id=smoke.ACTIVITY_ID,
            transaction_ref=smoke.TXN_REF,
            operation_ref=smoke.OP_REF,
            session_id=smoke.SESSION_REF,
            idempotency_key="idem_wp2_pv_create",
            role_key=ROLE_KEY,
            approval_token=SESSION_LIFECYCLE_APPROVAL_TOKEN,
            enabled=True,
            role_file_digest=config.expected_role_digest,
            prompt_ref="claim_prompt_wp2_pv_create",
            context_refs=("claim_context_wp2_pv",),
            cwd_ref="workspace_ref_phase_e2_smoke",
            allowed_roots_ref="allowed_roots_ref_phase_e2_smoke",
            lease_id=smoke.LEASE_ID,
            lease_epoch=1,
            lease_holder_ref=smoke.LEASE_HOLDER,
            expected_state_version=0,
            operator_gate=True,
            max_turns=4,
            max_artifacts_per_turn=8,
        ),
        store=store,
        open_session=bind_open_session(config, backend=backend),
    )
    assert create_res.ok
    binding = create_res.session_binding

    for i, prompt in enumerate(("wp2-turn1", "wp2-turn2"), start=1):
        turn_res = send_session_turn(
            SessionSendRequest(
                activity_id=smoke.ACTIVITY_ID,
                session_id=smoke.SESSION_REF,
                transaction_ref=smoke.TXN_REF,
                operation_ref=smoke.OP_REF,
                idempotency_key=f"idem_wp2_pv_send_{i:03d}",
                approval_token=SESSION_LIFECYCLE_APPROVAL_TOKEN,
                enabled=True,
                session_binding=binding,
                prompt_ref=f"claim_prompt_wp2_pv_send_{i:03d}",
                context_refs=(f"claim_context_wp2_pv_send_{i:03d}",),
                lease_id=smoke.LEASE_ID,
                lease_epoch=1,
                lease_holder_ref=smoke.LEASE_HOLDER,
                expected_state_version=i,
                operator_gate=True,
            ),
            store=store,
            run_turn=bind_run_turn(config, prompt, backend=backend),
        )
        assert turn_res.ok, f"turn {i} failed: {turn_res.status}"

    close_res = close_session(
        SessionCloseRequest(
            activity_id=smoke.ACTIVITY_ID,
            session_id=smoke.SESSION_REF,
            transaction_ref=smoke.TXN_REF,
            operation_ref=smoke.OP_REF,
            idempotency_key="idem_wp2_pv_close",
            approval_token=SESSION_LIFECYCLE_APPROVAL_TOKEN,
            enabled=True,
            session_binding=binding,
            lease_id=smoke.LEASE_ID,
            lease_epoch=1,
            lease_holder_ref=smoke.LEASE_HOLDER,
            expected_state_version=3,
            operator_gate=True,
        ),
        store=store,
        apply_close=bind_close_session(config, backend=backend),
    )
    assert close_res.ok

    verify = smoke.post_verify(store=store, config=config, mode="self_test")
    assert verify["turn_count_state_machine"] == 2

    smoke.assert_post_verify(verify, mode="self_test")


def test_smoke_empty_turn_prompts_rejected_before_runtime_session(tmp_path: Path) -> None:
    """WP2: run_lifecycle(turn_prompts=()) raises SmokeError before any backend call."""
    smoke = _load_smoke_module()
    backend = ExplodingBackend()  # any backend touch is a test failure
    config = _config(tmp_path)

    with pytest.raises(smoke.SmokeError, match=r"(?i)(at least 1 turn|turn_prompts)"):
        smoke.run_lifecycle(config=config, backend=backend, turn_prompts=())


def test_smoke_real_post_verify_n_turn_checks_all_results(tmp_path: Path) -> None:
    """WP2: post_verify real-mode checks business_marker across all N turn result files."""
    smoke = _load_smoke_module()
    config = _config(tmp_path)
    backend = FakeBackend(artifact_count=1)

    lifecycle = smoke.run_lifecycle(config=config, backend=backend, turn_prompts=("turn1", "turn2"))

    sessions_root = Path(config.sessions_dir)
    session_dir = sessions_root / config.runtime_session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "session.json").write_text(
        json.dumps({"state": "closed"}), encoding="utf-8"
    )
    for turn_name in ("turn_001", "turn_002"):
        turn_dir = session_dir / "turns" / turn_name
        turn_dir.mkdir(parents=True)
        (turn_dir / "result.json").write_text(
            json.dumps({"final_message": smoke.TURN_MARKER}), encoding="utf-8"
        )

    verify = smoke.post_verify(store=lifecycle["_store"], config=config, mode="real")

    assert verify["supervisor_turn_count"] == 2
    assert verify["business_marker_checked"] is True
    assert verify["business_marker_matches"] is True
    smoke.assert_post_verify(verify, mode="real")


def test_wp2_cli_turn_count_flag(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """WP2 CLI: --turn-count 2 drives two turns through the bounded smoke CLI."""
    smoke = _load_smoke_module()

    exit_code = smoke.main([
        "--self-test",
        "--sessions-dir", str(tmp_path / "sessions"),
        "--evidence-dir", str(tmp_path / "evidence"),
        "--work-dir", str(tmp_path / "work"),
        "--allow-repo-paths",
        "--turn-count", "2",
    ])

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert exit_code == 0
    assert summary["turn_count"] == 2
    assert summary["post_verify"]["turn_count_state_machine"] == 2
    assert summary["execution_pipeline"]["close"]["lifecycle_state"] == "session_closed"


def test_wp3b_cli_cancel_during_turn_self_test(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """WP3b CLI: --cancel-during-turn exercises bounded cancellation wiring in self-test mode."""
    smoke = _load_smoke_module()

    exit_code = smoke.main([
        "--self-test",
        "--sessions-dir", str(tmp_path / "sessions"),
        "--evidence-dir", str(tmp_path / "evidence"),
        "--work-dir", str(tmp_path / "work"),
        "--allow-repo-paths",
        "--cancel-during-turn",
    ])

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert exit_code == 0
    assert summary["cancel_during_turn"] is True
    assert summary["execution_pipeline"]["cancel_request"]["status"] == "cancel_requested"
    assert summary["execution_pipeline"]["interrupt"]["status"] == "cancelled"
    assert summary["business_task"]["cancellation_executed"] is True
    assert summary["business_task"]["cleanup_verified"] is True
    assert summary["business_task"]["backend_abort_calls"] == 1
    assert summary["execution_pipeline"]["close"]["lifecycle_state"] == "session_closed"


def test_wp3b_cli_cancel_during_turn_real_mode_is_not_claimed(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """WP3b CLI: real acpx cancel smoke is fail-closed until host/ACP semantics are proven."""
    smoke = _load_smoke_module()

    exit_code = smoke.main([
        "--sessions-dir", str(tmp_path / "sessions"),
        "--evidence-dir", str(tmp_path / "evidence"),
        "--work-dir", str(tmp_path / "work"),
        "--allow-repo-paths",
        "--cancel-during-turn",
    ])

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert exit_code == 2
    assert summary["ok"] is False
    assert "self-test only" in summary["skipped"]


# --------------------------------------------------------------------------- #
# WP3b: bounded real cancellation execution
# --------------------------------------------------------------------------- #

def test_wp3b_cancel_approval_token_is_defined_and_distinct() -> None:
    """WP3b must export a distinct cancel-execution approval token."""
    import sachima_supervisor.activity_session_real_execution as _m

    assert hasattr(_m, "PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN"), (
        "WP3b production must define PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN"
    )
    token = _m.PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN
    assert token, "token must be non-empty"
    assert token != PHASE_E2_REAL_SESSION_APPROVAL_TOKEN, "cancel token must differ from session token"
    assert token != SESSION_LIFECYCLE_APPROVAL_TOKEN, "cancel token must differ from lifecycle token"
    assert token != SESSION_INTERRUPT_API_APPROVAL_TOKEN, "cancel token must differ from interrupt token"


def test_wp3b_execute_real_cancellation_signature_accepts_request_and_config() -> None:
    """execute_real_cancellation must accept (request, config, *, backend) not just (config)."""
    params = tuple(signature(execute_real_cancellation).parameters)
    assert params[:2] == ("request", "config"), (
        f"execute_real_cancellation must accept (request, config, ...) but parameters are {params}"
    )


def test_wp3b_bind_real_cancellation_is_exported() -> None:
    """bind_real_cancellation must be exported from the real-execution module."""
    import sachima_supervisor.activity_session_real_execution as _m

    assert hasattr(_m, "bind_real_cancellation"), (
        "WP3b production must export bind_real_cancellation"
    )
    fn = _m.bind_real_cancellation
    params = tuple(signature(fn).parameters)
    assert "config" in params, f"bind_real_cancellation must accept 'config'; got {params}"


def test_wp3b_default_backend_abort_uses_session_runtime_cancelled_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default backend maps SessionRuntime.abort(...).cancelled, not a nonexistent record.state."""
    config = _config(tmp_path)
    resolved = validate_real_session_config(config)
    backend = _AgentRunSupervisorBackend()
    calls: list[dict[str, Any]] = []

    class RuntimeWithAbort:
        def abort(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return _FakeAbortResult(cancelled=True)

    monkeypatch.setattr(
        backend,
        "_runtime_and_role",
        lambda _resolved_config: (RuntimeWithAbort(), object()),
    )

    result = backend.abort(resolved)

    assert result.cancelled is True
    assert result.state == "cancelled"
    assert len(calls) == 1
    assert calls[0]["session_id"] == resolved.runtime_session_id
    assert calls[0]["cwd"] == resolved.work_dir


# --- gate: wrong token does not touch backend --------------------------------

def test_wp3b_phase_e2_session_token_rejected_for_cancel(tmp_path: Path) -> None:
    """Phase E2 session config (wrong token) must fail before backend.abort is touched."""
    config = _config(tmp_path)  # PHASE_E2_REAL_SESSION_APPROVAL_TOKEN — not the cancel token
    with pytest.raises(RealSessionExecutionError) as exc:
        execute_real_cancellation(_interrupt_request_e2(), config, backend=ExplodingBackend())
    assert exc.value.error_code == "activity_cancel_not_approved"


def test_wp3b_disabled_cancel_config_does_not_touch_backend(tmp_path: Path) -> None:
    """Disabled WP3b cancel config must fail before backend.abort is touched."""
    config = _cancel_config(tmp_path, enabled=False)
    with pytest.raises(RealSessionExecutionError):
        execute_real_cancellation(_interrupt_request_e2(), config, backend=ExplodingBackend())


def test_wp3b_invalid_role_digest_does_not_touch_backend(tmp_path: Path) -> None:
    """Config with tampered role digest must fail before backend.abort is touched."""
    config = _cancel_config(tmp_path, expected_role_digest="sha256:" + "1" * 64)
    with pytest.raises(RealSessionExecutionError):
        execute_real_cancellation(_interrupt_request_e2(), config, backend=ExplodingBackend())


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"enabled": False}, "activity_session_disabled"),
        ({"approval_token": "wrong"}, "activity_session_approval_mismatch"),
        ({"operator_gate": False}, "activity_precondition_unmet"),
    ],
)
def test_wp3b_interrupt_request_gate_fail_closed_before_backend(
    tmp_path: Path, overrides: dict[str, Any], error_code: str
) -> None:
    """Direct execute_real_cancellation must validate SessionInterruptRequest gates too."""
    config = _cancel_config(tmp_path)
    with pytest.raises(RealSessionExecutionError) as exc:
        execute_real_cancellation(
            _interrupt_request_e2(**overrides), config, backend=ExplodingBackend()
        )
    assert exc.value.error_code == error_code


# --- happy path: backend.abort called once, returns SessionInterruptOutcome --

def test_wp3b_backend_abort_called_once_returns_interrupted_outcome(tmp_path: Path) -> None:
    """Successful cancel: backend.abort called once; outcome has interrupted=True."""
    import sachima_supervisor.activity_session_real_execution as _m
    if not hasattr(_m, "PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN"):
        pytest.fail("WP3b production missing: PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN not defined")

    config = _cancel_config(tmp_path)
    abort_backend = FakeAbortBackend()
    outcome = execute_real_cancellation(_interrupt_request_e2(), config, backend=abort_backend)

    assert isinstance(outcome, SessionInterruptOutcome), (
        f"execute_real_cancellation must return SessionInterruptOutcome, got {type(outcome)}"
    )
    assert outcome.interrupted is True
    assert outcome.cleanup_verified is True
    assert outcome.supervisor_status == "session_cancelled"
    assert outcome.evidence_digest is not None
    assert outcome.evidence_digest.startswith("sha256:")
    assert abort_backend.abort_calls == 1


def test_wp3b_backend_abort_not_cancelled_returns_not_interrupted(tmp_path: Path) -> None:
    """backend.abort returns cancelled=False → outcome interrupted=False, cleanup_verified=False."""
    import sachima_supervisor.activity_session_real_execution as _m
    if not hasattr(_m, "PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN"):
        pytest.fail("WP3b production missing: PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN not defined")

    config = _cancel_config(tmp_path)
    abort_backend = FakeAbortBackend(abort_cancelled=False)
    outcome = execute_real_cancellation(_interrupt_request_e2(), config, backend=abort_backend)

    assert isinstance(outcome, SessionInterruptOutcome)
    assert outcome.interrupted is False
    assert outcome.cleanup_verified is False
    assert abort_backend.abort_calls == 1


def test_wp3b_backend_abort_exception_gives_ambiguous_outcome(tmp_path: Path) -> None:
    """backend.abort raising must produce an ambiguous outcome (not propagate the exception)."""
    import sachima_supervisor.activity_session_real_execution as _m
    if not hasattr(_m, "PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN"):
        pytest.fail("WP3b production missing: PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN not defined")

    config = _cancel_config(tmp_path)
    abort_backend = FakeAbortBackend(raise_on_abort=True)
    outcome = execute_real_cancellation(_interrupt_request_e2(), config, backend=abort_backend)

    assert isinstance(outcome, SessionInterruptOutcome)
    # ambiguous=True causes apply_session_interrupt to leave cancel_ambiguous
    assert outcome.ambiguous is True
    assert abort_backend.abort_calls == 1  # abort was attempted before it raised


# --- integration: apply_session_interrupt wired through bind_real_cancellation -

def test_wp3b_integration_real_cancellation_via_apply_session_interrupt(tmp_path: Path) -> None:
    """End-to-end: create_session → request_cancellation → apply_session_interrupt with
    bind_real_cancellation records status='cancelled' and abort called exactly once."""
    import sachima_supervisor.activity_session_real_execution as _m
    if not hasattr(_m, "bind_real_cancellation"):
        pytest.fail("WP3b production missing: bind_real_cancellation not defined")
    bind_real_cancellation = _m.bind_real_cancellation

    store = _store()
    session_backend = FakeBackend()
    config = _config(tmp_path)
    cancel_config = _cancel_config(tmp_path)
    abort_backend = FakeAbortBackend()

    # Step 1: create real session (fake backend)
    create_res = create_session(
        _create_request(), store=store, open_session=bind_open_session(config, backend=session_backend)
    )
    assert create_res.ok
    binding = create_res.session_binding

    # Step 2: record cancellation request (state machine — request state only)
    cancel_res = request_cancellation(_e2_cancel_request(binding), store=store)
    assert cancel_res.status == "cancel_requested"

    # Step 3: apply interrupt via WP3b real cancel path
    result = apply_session_interrupt(
        _interrupt_request_e2(session_binding=binding),
        store=store,
        apply_interrupt=bind_real_cancellation(cancel_config, backend=abort_backend),
    )
    state = result.to_durable_state()

    assert isinstance(result, CancellationRequestResult)
    assert state["status"] == "cancelled"
    assert state["ok"] is True
    assert abort_backend.abort_calls == 1
    _assert_no_leaks(state)


def test_wp3b_replay_does_not_abort_twice(tmp_path: Path) -> None:
    """apply_session_interrupt idempotency: replaying the same interrupt does not call abort twice."""
    import sachima_supervisor.activity_session_real_execution as _m
    if not hasattr(_m, "bind_real_cancellation"):
        pytest.fail("WP3b production missing: bind_real_cancellation not defined")
    bind_real_cancellation = _m.bind_real_cancellation

    store = _store()
    config = _config(tmp_path)
    cancel_config = _cancel_config(tmp_path)
    abort_backend = FakeAbortBackend()

    create_res = create_session(
        _create_request(), store=store, open_session=bind_open_session(config, backend=FakeBackend())
    )
    binding = create_res.session_binding
    request_cancellation(_e2_cancel_request(binding), store=store)

    apply_fn = bind_real_cancellation(cancel_config, backend=abort_backend)

    first = apply_session_interrupt(
        _interrupt_request_e2(session_binding=binding), store=store, apply_interrupt=apply_fn
    )
    second = apply_session_interrupt(
        _interrupt_request_e2(session_binding=binding), store=store, apply_interrupt=apply_fn
    )

    assert first.to_durable_state() == second.to_durable_state()
    assert abort_backend.abort_calls == 1  # idempotent: abort fired only once


def test_wp3b_cancel_durable_state_has_no_leaks(tmp_path: Path) -> None:
    """Durable cancel state after real cancellation must not carry leaky tokens."""
    import sachima_supervisor.activity_session_real_execution as _m
    if not hasattr(_m, "bind_real_cancellation"):
        pytest.fail("WP3b production missing: bind_real_cancellation not defined")
    bind_real_cancellation = _m.bind_real_cancellation

    store = _store()
    config = _config(tmp_path)
    cancel_config = _cancel_config(tmp_path)

    create_res = create_session(
        _create_request(), store=store, open_session=bind_open_session(config, backend=FakeBackend())
    )
    binding = create_res.session_binding
    request_cancellation(_e2_cancel_request(binding), store=store)

    result = apply_session_interrupt(
        _interrupt_request_e2(session_binding=binding),
        store=store,
        apply_interrupt=bind_real_cancellation(cancel_config, backend=FakeAbortBackend()),
    )
    _assert_no_leaks(result.to_durable_state())
