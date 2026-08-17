"""Phase E-2 bounded real persistent-session execution bridge tests.

These exercise the Sachima-owned local/offline bridge that wires the Phase E
state machine (``create_session`` / ``send_session_turn`` / ``close_session``)
to an injected persistent-session runtime backend — while keeping the committed
source default-off, fail-closed, CI-safe, and free of any producer import.

The in-tree default backend, and the goal-turn composition that delegated to
the producer's goal compiler, are **retired** (ARS 0.7.6 plan §11, seam S-2):
the modules they called were removed upstream at 0.7.x. What is proven here is
that the bridge is fake/offline-only — every runtime touch goes through an
*injected* backend, and asking for the retired default or a composed goal turn
fails closed with a stable code instead of degrading to a launcher or emulating
a compiler.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import types
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
    SessionLifecycleError,
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
    PHASE_E2_REAL_SESSION_APPROVAL_TOKEN,
    RealPersistentSessionConfig,
    RealSessionExecutionError,
    ResolvedRealSessionConfig,
    bind_real_cancellation,
    bind_close_session,
    bind_open_session,
    bind_run_turn,
    best_effort_close_real_session,
    close_real_persistent_session,
    compose_goal_turn_prompt,
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
    #: Explicit supervisor status label override (e.g. "no_op"); None derives
    #: the label from ``turn_completed`` like the pre-S2 fake did.
    turn_status_label: str | None = None
    #: Mirrors the additive agent-run-supervisor `observed_effect` result key:
    #: True/False when the library (>= 0.1.4) reports it, None for pre-0.1.4
    #: payloads.
    turn_observed_effect: bool | None = None
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
            status_label=self.turn_status_label
            or ("completed" if self.turn_completed else "runner_error"),
            turn_id="faketurn0001",
            artifact_count=self.artifact_count,
            observed_effect=self.turn_observed_effect,
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
    block_send_until_abort: bool = False
    send_entered: threading.Event = field(default_factory=threading.Event)
    release_send: threading.Event = field(default_factory=threading.Event)
    abort_released_turn: bool = False

    def send(self, resolved: ResolvedRealSessionConfig, prompt: str) -> Any:
        if not self.block_send_until_abort:
            return super().send(resolved, prompt)

        from sachima_supervisor.activity_session_real_execution import _RuntimeTurnResult

        self.send_calls += 1
        self.prompts.append(prompt)
        self.send_entered.set()
        if not self.release_send.wait(timeout=5.0):
            raise RuntimeError("fake send timed out waiting for abort")
        return _RuntimeTurnResult(
            completed=False,
            status_label="cancelled_by_abort",
            turn_id="faketurn0001",
            artifact_count=0,
        )

    def abort(self, resolved: ResolvedRealSessionConfig) -> Any:
        self.abort_calls += 1
        if self.raise_on_abort:
            raise RuntimeError("fake abort boom")
        if self.block_send_until_abort:
            self.abort_released_turn = True
            self.release_send.set()
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
            "acpx_version": "0.12.0",
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


def _start_in_flight_turn(
    tmp_path: Path,
    *,
    backend: FakeAbortBackend | None = None,
) -> tuple[
    SessionLifecycleStore,
    str,
    RealPersistentSessionConfig,
    FakeAbortBackend,
    threading.Thread,
    dict[str, Any],
    list[BaseException],
]:
    """Create a session and hold one turn in-flight until backend.abort() releases it."""

    store = _store()
    config = _config(tmp_path)
    active_backend = backend or FakeAbortBackend(block_send_until_abort=True)
    create_res = create_session(
        _create_request(), store=store, open_session=bind_open_session(config, backend=active_backend)
    )
    assert create_res.ok
    binding = create_res.session_binding
    assert binding is not None

    turn_result: dict[str, Any] = {}
    turn_errors: list[BaseException] = []

    def _run_turn() -> None:
        try:
            turn_result["value"] = send_session_turn(
                _send_request(binding),
                store=store,
                run_turn=bind_run_turn(config, "cancel me", backend=active_backend),
            )
        except BaseException as exc:  # pragma: no cover - asserted by caller
            turn_errors.append(exc)

    thread = threading.Thread(target=_run_turn)
    thread.start()
    assert active_backend.send_entered.wait(timeout=5.0), "turn did not enter fake backend"
    return store, binding, config, active_backend, thread, turn_result, turn_errors


def _finish_in_flight_turn(
    thread: threading.Thread,
    backend: FakeAbortBackend,
    turn_result: dict[str, Any],
    turn_errors: list[BaseException],
) -> TurnRecordResult:
    backend.release_send.set()
    thread.join(timeout=5.0)
    assert not thread.is_alive(), "in-flight turn thread did not finish"
    assert not turn_errors, turn_errors
    result = turn_result.get("value")
    assert isinstance(result, TurnRecordResult)
    return result


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


# --------------------------------------------------------------------------- #
# ARS S2 no-op fail-closed consumption (upstream `no_op` + empty completed)
# --------------------------------------------------------------------------- #
def test_no_op_turn_status_fails_closed_with_distinct_error(tmp_path: Path) -> None:
    # agent-run-supervisor (>= 0.1.4) classifies silent exit-0 turns as
    # "no_op"; the Sachima boundary must surface that as its own stable
    # failure code — never as a completed turn.
    config = _config(tmp_path)
    backend = FakeBackend(turn_completed=False, turn_status_label="no_op")

    outcome = run_real_persistent_session_turn(
        _send_request("sbind_x"), config, "goal turn", backend=backend
    )

    assert outcome.ok is False
    assert outcome.error_code == "activity_turn_no_op"


def test_completed_turn_without_observed_effect_fails_closed_as_no_op(
    tmp_path: Path,
) -> None:
    # Defense in depth: a backend claiming "completed" while the supervisor
    # evidence says nothing was produced (observed_effect=False) is a no-op
    # and must fail closed at the Sachima boundary too.
    config = _config(tmp_path)
    backend = FakeBackend(turn_completed=True, turn_observed_effect=False)

    outcome = run_real_persistent_session_turn(
        _send_request("sbind_x"), config, "goal turn", backend=backend
    )

    assert outcome.ok is False
    assert outcome.error_code == "activity_turn_no_op"


def test_completed_turn_with_observed_effect_succeeds(tmp_path: Path) -> None:
    config = _config(tmp_path)
    backend = FakeBackend(turn_completed=True, turn_observed_effect=True)

    outcome = run_real_persistent_session_turn(
        _send_request("sbind_x"), config, "read-only turn", backend=backend
    )

    assert outcome.ok is True
    assert outcome.supervisor_status == "turn_completed"


def test_completed_turn_with_unknown_observed_effect_stays_compatible(
    tmp_path: Path,
) -> None:
    # Pre-0.1.4 agent-run-supervisor result payloads carry no observed_effect
    # key (None = unknown); the boundary stays compatible with such payloads
    # instead of failing closed on a missing key.
    config = _config(tmp_path)
    backend = FakeBackend(turn_completed=True, turn_observed_effect=None)

    outcome = run_real_persistent_session_turn(
        _send_request("sbind_x"), config, "read-only turn", backend=backend
    )

    assert outcome.ok is True


# --------------------------------------------------------------------------- #
# Goal-turn composition — retired (seam S-2)
# --------------------------------------------------------------------------- #
def test_compose_goal_turn_prompt_is_retired_and_fails_closed() -> None:
    """No compiler, no template, no unvalidated ``/goal`` text.

    It delegated to the producer's role-aware goal compiler, which 0.7.x
    removed. Composing the contract text locally would send something a
    non-native adapter silently no-ops, so the seam refuses with the stable
    code it always used for "no compiler available".
    """

    with pytest.raises(RealSessionExecutionError) as excinfo:
        compose_goal_turn_prompt("ship the report")
    assert excinfo.value.error_code == "activity_goal_unsupported"
    # It composed nothing on the way out: no template text is returned anywhere.
    assert "/goal" not in str(excinfo.value)




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
# Smoke-script wiring — the Phase E-2 smoke script is retired (seam S-6)
# --------------------------------------------------------------------------- #
def test_the_phase_e2_persistent_session_smoke_script_is_retired() -> None:
    """It drove the removed session runtime; it is deleted, not re-pointed."""

    assert not (REPO_ROOT / "scripts" / "sachima_phase_e2_persistent_session_smoke.py").exists()


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


def test_the_default_runtime_backend_is_retired_and_must_be_injected(
    tmp_path: Path,
) -> None:
    """No default backend, and no stub standing in for one (seam S-2).

    The default drove the removed session runtime. Rather than emulate it or
    return something whose failures would surface later and elsewhere, the
    bridge refuses at the boundary — so a caller learns it must inject a
    backend before anything is attempted.
    """

    import sachima_supervisor.activity_session_real_execution as _m

    assert not hasattr(_m, "_AgentRunSupervisorBackend")
    with pytest.raises(RealSessionExecutionError) as excinfo:
        _m._resolve_backend(None)
    assert excinfo.value.error_code == "activity_supervisor_failed"

    # And it really is only the default that is gone: an injected backend is
    # returned untouched.
    injected = FakeBackend()
    assert _m._resolve_backend(injected) is injected


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


# --- state-machine proof: direct abort is closed; in-flight path executes ----

def test_wp3b_direct_execute_real_cancellation_requires_state_machine_proof(
    tmp_path: Path,
) -> None:
    """Direct execute_real_cancellation must not fire backend.abort without in-flight proof."""

    config = _cancel_config(tmp_path)
    abort_backend = FakeAbortBackend()

    with pytest.raises(RealSessionExecutionError) as exc:
        execute_real_cancellation(_interrupt_request_e2(turn_index=1), config, backend=abort_backend)

    assert exc.value.error_code == "activity_precondition_unmet"
    assert abort_backend.abort_calls == 0


def test_wp3b_direct_bound_real_cancellation_requires_state_machine_call_path(
    tmp_path: Path,
) -> None:
    """Calling the bound WP3b callable directly must not smuggle the private proof."""

    config = _cancel_config(tmp_path)
    abort_backend = FakeAbortBackend()
    bound = bind_real_cancellation(config, backend=abort_backend)
    assert not hasattr(bound, "_sachima_requires_in_flight_turn")
    assert not hasattr(bound, "_sachima_call_with_in_flight_proof"), (
        "bound cancellation callable must not expose a direct proof callable"
    )

    with pytest.raises(RealSessionExecutionError) as exc:
        bound(_interrupt_request_e2(turn_index=1))

    assert exc.value.error_code == "activity_precondition_unmet"
    assert abort_backend.abort_calls == 0

    with pytest.raises(RealSessionExecutionError) as direct_method_exc:
        bound._apply_after_lifecycle_validation(_interrupt_request_e2(turn_index=1))  # type: ignore[attr-defined]

    assert direct_method_exc.value.error_code == "activity_precondition_unmet"
    assert abort_backend.abort_calls == 0

    fake_lifecycle_globals: dict[str, Any] = {
        "__name__": "sachima_supervisor.activity_session_lifecycle",
    }
    exec(
        "def _safe_interrupt_call(work, request):\n"
        "    return work(request)\n"
        "def apply_session_interrupt(work, request):\n"
        "    return _safe_interrupt_call(work, request)\n",
        fake_lifecycle_globals,
    )
    with pytest.raises(RealSessionExecutionError) as forged_stack_exc:
        fake_lifecycle_globals["apply_session_interrupt"](
            bound._apply_after_lifecycle_validation,  # type: ignore[attr-defined]
            _interrupt_request_e2(turn_index=1),
        )

    assert forged_stack_exc.value.error_code == "activity_precondition_unmet"
    assert abort_backend.abort_calls == 0


def test_wp3b_bound_method_cannot_be_passed_as_interrupt_callable(tmp_path: Path) -> None:
    """Passing the exposed bound method itself must not bypass in-flight scope checks."""

    store, binding, _config_unused, backend, thread, turn_result, turn_errors = _start_in_flight_turn(tmp_path)
    cancel_config = _cancel_config(tmp_path)
    request_cancellation(_e2_cancel_request(binding, turn_index=None), store=store)
    bound = bind_real_cancellation(cancel_config, backend=backend)

    try:
        with pytest.raises(SessionLifecycleError) as exc:
            apply_session_interrupt(
                _interrupt_request_e2(session_binding=binding, turn_index=None),
                store=store,
                apply_interrupt=bound._apply_after_lifecycle_validation,  # type: ignore[attr-defined]
            )
        assert exc.value.error_code == "activity_cancel_ambiguous"
        assert backend.abort_calls == 0
    finally:
        _finish_in_flight_turn(thread, backend, turn_result, turn_errors)


def test_wp3b_forged_in_flight_attribute_cannot_enable_real_abort(tmp_path: Path) -> None:
    """A fake callable attribute must not be enough to enter the real abort path."""

    store, binding, _config_unused, backend, thread, turn_result, turn_errors = _start_in_flight_turn(tmp_path)
    cancel_config = _cancel_config(tmp_path)
    request_cancellation(_e2_cancel_request(binding, turn_index=1), store=store)

    def forged_apply(request: SessionInterruptRequest) -> SessionInterruptOutcome:
        return execute_real_cancellation(request, cancel_config, backend=backend)

    forged_apply._sachima_requires_in_flight_turn = True  # type: ignore[attr-defined]

    try:
        with pytest.raises(SessionLifecycleError) as exc:
            apply_session_interrupt(
                _interrupt_request_e2(session_binding=binding, turn_index=1),
                store=store,
                apply_interrupt=forged_apply,
            )
        assert exc.value.error_code == "activity_cancel_ambiguous"
        assert backend.abort_calls == 0
    finally:
        _finish_in_flight_turn(thread, backend, turn_result, turn_errors)


def test_wp3b_apply_interrupt_requires_named_in_flight_turn(tmp_path: Path) -> None:
    """Cancellation execution must target the currently in-flight turn, not session-wide/old turns."""

    store, binding, _config_unused, backend, thread, turn_result, turn_errors = _start_in_flight_turn(tmp_path)
    cancel_config = _cancel_config(tmp_path)
    request_cancellation(_e2_cancel_request(binding, turn_index=1), store=store)

    try:
        with pytest.raises(SessionLifecycleError) as exc:
            apply_session_interrupt(
                _interrupt_request_e2(session_binding=binding, turn_index=None),
                store=store,
                apply_interrupt=bind_real_cancellation(cancel_config, backend=backend),
            )
        assert exc.value.error_code == "activity_not_found"
        assert backend.abort_calls == 0
    finally:
        _finish_in_flight_turn(thread, backend, turn_result, turn_errors)


def test_wp3b_apply_interrupt_rejects_completed_turn_target(tmp_path: Path) -> None:
    """A completed prior turn is not an in-flight cancellation target."""

    store = _store()
    config = _config(tmp_path)
    backend = FakeAbortBackend()
    create_res = create_session(
        _create_request(), store=store, open_session=bind_open_session(config, backend=backend)
    )
    assert create_res.ok
    binding = create_res.session_binding
    assert binding is not None
    turn = send_session_turn(
        _send_request(binding),
        store=store,
        run_turn=bind_run_turn(config, "already done", backend=backend),
    )
    assert turn.status == "completed"
    request_cancellation(_e2_cancel_request(binding, turn_index=1), store=store)

    with pytest.raises(SessionLifecycleError) as exc:
        apply_session_interrupt(
            _interrupt_request_e2(session_binding=binding, turn_index=1),
            store=store,
            apply_interrupt=bind_real_cancellation(_cancel_config(tmp_path), backend=backend),
        )

    assert exc.value.error_code == "activity_not_found"
    assert backend.abort_calls == 0


def test_wp3b_backend_abort_called_once_returns_interrupted_outcome(tmp_path: Path) -> None:
    """Successful cancel: apply_session_interrupt fires abort only for an in-flight turn."""

    store, binding, _config_unused, backend, thread, turn_result, turn_errors = _start_in_flight_turn(tmp_path)
    cancel_config = _cancel_config(tmp_path)
    request_cancellation(_e2_cancel_request(binding, turn_index=1), store=store)

    result = apply_session_interrupt(
        _interrupt_request_e2(session_binding=binding, turn_index=1),
        store=store,
        apply_interrupt=bind_real_cancellation(cancel_config, backend=backend),
    )
    turn = _finish_in_flight_turn(thread, backend, turn_result, turn_errors)

    assert result.status == "cancelled"
    assert result.to_durable_state()["ok"] is True
    assert backend.abort_calls == 1
    assert backend.abort_released_turn is True
    assert turn.status != "completed"


def test_wp3b_backend_abort_not_cancelled_returns_not_interrupted(tmp_path: Path) -> None:
    """backend.abort returns cancelled=False → durable cancel status is cancel_failed."""

    backend = FakeAbortBackend(block_send_until_abort=True, abort_cancelled=False)
    store, binding, _config_unused, backend, thread, turn_result, turn_errors = _start_in_flight_turn(
        tmp_path, backend=backend
    )
    cancel_config = _cancel_config(tmp_path)
    request_cancellation(_e2_cancel_request(binding, turn_index=1), store=store)

    result = apply_session_interrupt(
        _interrupt_request_e2(session_binding=binding, turn_index=1),
        store=store,
        apply_interrupt=bind_real_cancellation(cancel_config, backend=backend),
    )
    _finish_in_flight_turn(thread, backend, turn_result, turn_errors)

    assert result.status == "cancel_failed"
    assert result.to_durable_state()["ok"] is False
    assert backend.abort_calls == 1


def test_wp3b_backend_abort_exception_gives_ambiguous_outcome(tmp_path: Path) -> None:
    """backend.abort raising must hold the cancellation ambiguous and not leak raw errors."""

    backend = FakeAbortBackend(block_send_until_abort=True, raise_on_abort=True)
    store, binding, _config_unused, backend, thread, turn_result, turn_errors = _start_in_flight_turn(
        tmp_path, backend=backend
    )
    cancel_config = _cancel_config(tmp_path)
    request_cancellation(_e2_cancel_request(binding, turn_index=1), store=store)

    try:
        with pytest.raises(SessionLifecycleError) as exc:
            apply_session_interrupt(
                _interrupt_request_e2(session_binding=binding, turn_index=1),
                store=store,
                apply_interrupt=bind_real_cancellation(cancel_config, backend=backend),
            )
        assert exc.value.error_code == "activity_cancel_ambiguous"
        assert backend.abort_calls == 1
    finally:
        _finish_in_flight_turn(thread, backend, turn_result, turn_errors)


# --- integration: apply_session_interrupt wired through bind_real_cancellation -

def test_wp3b_integration_real_cancellation_via_apply_session_interrupt(tmp_path: Path) -> None:
    """End-to-end: in-flight turn → request_cancellation → apply_session_interrupt."""

    store, binding, _config_unused, backend, thread, turn_result, turn_errors = _start_in_flight_turn(tmp_path)
    cancel_config = _cancel_config(tmp_path)

    cancel_res = request_cancellation(_e2_cancel_request(binding, turn_index=1), store=store)
    assert cancel_res.status == "cancel_requested"

    result = apply_session_interrupt(
        _interrupt_request_e2(session_binding=binding, turn_index=1),
        store=store,
        apply_interrupt=bind_real_cancellation(cancel_config, backend=backend),
    )
    _finish_in_flight_turn(thread, backend, turn_result, turn_errors)
    state = result.to_durable_state()

    assert isinstance(result, CancellationRequestResult)
    assert state["status"] == "cancelled"
    assert state["ok"] is True
    assert backend.abort_calls == 1
    _assert_no_leaks(state)


def test_wp3b_replay_does_not_abort_twice(tmp_path: Path) -> None:
    """apply_session_interrupt idempotency: replaying the same interrupt does not call abort twice."""

    store, binding, _config_unused, backend, thread, turn_result, turn_errors = _start_in_flight_turn(tmp_path)
    cancel_config = _cancel_config(tmp_path)
    request_cancellation(_e2_cancel_request(binding, turn_index=1), store=store)

    apply_fn = bind_real_cancellation(cancel_config, backend=backend)

    first = apply_session_interrupt(
        _interrupt_request_e2(session_binding=binding, turn_index=1),
        store=store,
        apply_interrupt=apply_fn,
    )
    _finish_in_flight_turn(thread, backend, turn_result, turn_errors)
    second = apply_session_interrupt(
        _interrupt_request_e2(session_binding=binding, turn_index=1),
        store=store,
        apply_interrupt=apply_fn,
    )

    assert first.to_durable_state() == second.to_durable_state()
    assert backend.abort_calls == 1  # idempotent: abort fired only once


def test_wp3b_cancel_durable_state_has_no_leaks(tmp_path: Path) -> None:
    """Durable cancel state after real cancellation must not carry leaky tokens."""

    store, binding, _config_unused, backend, thread, turn_result, turn_errors = _start_in_flight_turn(tmp_path)
    cancel_config = _cancel_config(tmp_path)
    request_cancellation(_e2_cancel_request(binding, turn_index=1), store=store)

    result = apply_session_interrupt(
        _interrupt_request_e2(session_binding=binding, turn_index=1),
        store=store,
        apply_interrupt=bind_real_cancellation(cancel_config, backend=backend),
    )
    _finish_in_flight_turn(thread, backend, turn_result, turn_errors)
    _assert_no_leaks(result.to_durable_state())
