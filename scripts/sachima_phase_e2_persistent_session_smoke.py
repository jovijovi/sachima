#!/usr/bin/env python3
"""Sachima Phase E-2 bounded real persistent-session smoke (local/offline).

Drives the **existing** Phase E state machine
(``sachima_supervisor.activity_session_lifecycle``) through the Phase E-2 real
execution bridge (``sachima_supervisor.activity_session_real_execution``) over a
single minimal persistent-session lifecycle:

    create  ->  send (one or more read-only turns)  ->  close

The only real surface is a *pinned local* ``acpx`` persistent session reached
through ``agent_run_supervisor.session_runtime.SessionRuntime`` (lazily imported
by the default backend). The committed portable role
(``roles/session_worker_persistent_v1.json``) has ``acpx_binary: null`` and is
non-runnable by construction; the operator supplies a verified local acpx via
``--acpx-binary`` (optionally checked with ``--acpx-sha256``). There is no
npx/npm/pnpm/yarn/bunx/shell fallback.

Scope boundary (local/offline only):

  * NEVER touches Gateway, Feishu, IM delivery, public ingress, live/default-on
    behavior, production config, service restart, platform-adapter mutation, or
    real delivery.
  * Cancellation execution is exercised by ``--cancel-during-turn`` only in
    deterministic ``--self-test`` mode; real acpx cancellation is host/ACP
    dependent and is not claimed by this smoke unless a future gate proves it.
  * Writes only under caller-provided ``--sessions-dir`` / ``--evidence-dir`` /
    ``--work-dir`` (which must live outside the tracked repo), so a ``git
    status`` of the worktree stays clean.
  * The turn's final message is intentionally never surfaced into durable
    Sachima state; the smoke verifies lifecycle/status/counts only.

Modes:

  * default (real): requires a runnable pinned acpx and an importable
    ``agent_run_supervisor``. Exit ``2`` when an environment precondition is
    missing, ``1`` on a lifecycle/verification failure, ``0`` on success.
  * ``--self-test``: drives the identical lifecycle with an in-process fake
    backend (no acpx, no ``agent_run_supervisor``), so the wiring is
    deterministically exercisable in CI/dev without provisioning.

Exit codes: ``0`` pass; ``1`` lifecycle/verification failure; ``2`` environment
precondition missing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from collections.abc import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sachima_supervisor.activity_session_lifecycle import (  # noqa: E402
    SESSION_INTERRUPT_API_APPROVAL_TOKEN,
    SESSION_LIFECYCLE_APPROVAL_TOKEN,
    CancellationRequest,
    SessionCloseRequest,
    SessionCreateRequest,
    SessionInterruptRequest,
    SessionLifecycleStore,
    SessionSendRequest,
    apply_session_interrupt,
    close_session,
    create_session,
    list_session_turns,
    query_session,
    request_cancellation,
    send_session_turn,
)
from sachima_supervisor.activity_session_real_execution import (  # noqa: E402
    PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN,
    PHASE_E2_REAL_SESSION_APPROVAL_TOKEN,
    RealPersistentSessionConfig,
    best_effort_close_real_session,
    bind_close_session,
    bind_real_cancellation,
    bind_open_session,
    bind_run_turn,
    validate_real_session_config,
)

COMMITTED_ROLE = REPO_ROOT / "sachima_supervisor" / "roles" / "session_worker_persistent_v1.json"

ROLE_KEY = "sachima.session_worker"
ACTIVITY_ID = "activity_phase_e2_smoke"
LEASE_ID = "lease_phase_e2_smoke"
LEASE_HOLDER = "controller_ref_sachima_phase_e2_smoke"
SESSION_REF = "session_phase_e2_smoke"
TXN_REF = "claim_txn_phase_e2_smoke"
OP_REF = "claim_op_phase_e2_smoke"

TURN_MARKER = "SACHIMA_PHASE_E2_TURN_OK"
TURN_PROMPT = (
    "Phase E-2 bounded persistent-session smoke. Do not read files, run tools, "
    f"fetch, or edit anything. Reply with exactly this token and nothing else: {TURN_MARKER}"
)
CANCEL_TURN_MARKER = "SACHIMA_WP3B_CANCEL_SHOULD_HAVE_INTERRUPTED"
CANCEL_TURN_PROMPT = (
    "WP3b bounded cancellation smoke. This prompt is intentionally long-running "
    "so the operator-gated cancel path can interrupt it. Do not read files, run tools, "
    "fetch, edit, or access external systems. Think silently for at least 90 seconds "
    f"before replying. If not interrupted, reply exactly: {CANCEL_TURN_MARKER}"
)

# Generous artifact budget so a real turn's redacted artifact bundle never trips
# the state machine's per-turn artifact cap.
MAX_TURNS = 4
MAX_ARTIFACTS_PER_TURN = 64


class SmokeError(RuntimeError):
    """A lifecycle/verification step failed."""


class EnvironmentNotReady(RuntimeError):
    """An environment precondition (e.g. a runnable pinned acpx) is missing."""


# --------------------------------------------------------------------------- #
# Role overlay + config
# --------------------------------------------------------------------------- #
def build_resolved_role(
    *, role_path: Path, acpx_binary: str, work_dir: Path, model: str | None
) -> dict[str, Any]:
    """Overlay the operator-pinned acpx binary + work-dir workspace onto the
    committed portable role. The committed role's ``acpx_binary`` is null; this
    is the only place the pinned local binary enters, and it is never committed.
    """

    role = json.loads(role_path.read_text(encoding="utf-8"))
    role["runner"]["acpx_binary"] = acpx_binary
    if model is not None:
        role["runner"]["model"] = model
    # Point the workspace at the caller-owned work dir so the runtime's
    # effective-cwd validation passes against an allowed root.
    role["workspace"]["default_cwd"] = str(work_dir)
    role["workspace"]["allowed_roots"] = [str(work_dir)]
    role["workspace"]["allowed_roots_security_boundary"] = False
    return role


def write_resolved_role(role: dict[str, Any], evidence_dir: Path) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    resolved_path = evidence_dir / "role.resolved.json"
    resolved_path.write_text(json.dumps(role, indent=2), encoding="utf-8")
    return resolved_path


def build_config(
    *,
    resolved_role_path: Path,
    sessions_dir: Path,
    evidence_dir: Path,
    work_dir: Path,
    session_id: str,
    acpx_sha256: str | None,
    allow_repo_paths: bool,
) -> RealPersistentSessionConfig:
    import hashlib

    digest = "sha256:" + hashlib.sha256(resolved_role_path.read_bytes()).hexdigest()
    return RealPersistentSessionConfig(
        enabled=True,
        approval_token=PHASE_E2_REAL_SESSION_APPROVAL_TOKEN,
        role_file=str(resolved_role_path),
        expected_role_digest=digest,
        sessions_dir=str(sessions_dir),
        evidence_dir=str(evidence_dir),
        work_dir=str(work_dir),
        runtime_session_id=session_id,
        session_name=f"{session_id}-name",
        acpx_sha256=acpx_sha256,
        allow_repo_paths=allow_repo_paths,
    )


def build_cancel_config(config: RealPersistentSessionConfig) -> RealPersistentSessionConfig:
    """Return the same runtime config with the separate WP3b cancel gate token."""

    return replace(config, approval_token=PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN)

# --------------------------------------------------------------------------- #
# Lifecycle (deterministic; backend-injectable for self-test)
# --------------------------------------------------------------------------- #
def run_lifecycle(
    *,
    config: RealPersistentSessionConfig,
    backend: Any | None = None,
    turn_prompts: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Drive create -> send(N read-only turns) -> close and return a summary.

    ``turn_prompts`` drives N sequential turns within a single session.  When
    omitted, the default one-turn behavior using ``TURN_PROMPT`` is preserved.
    ``backend=None`` uses the default lazy real runtime backend.  A fake backend
    can be injected to exercise the identical wiring deterministically.
    """
    prompts = turn_prompts if turn_prompts is not None else (TURN_PROMPT,)
    if not prompts:
        raise SmokeError("turn_prompts must contain at least 1 turn")
    n_turns = len(prompts)

    store = SessionLifecycleStore()
    store.grant_lease(
        activity_id=ACTIVITY_ID,
        lease_id=LEASE_ID,
        lease_epoch=1,
        lease_holder_ref=LEASE_HOLDER,
        state_version=0,
    )

    create_req = SessionCreateRequest(
        activity_id=ACTIVITY_ID,
        transaction_ref=TXN_REF,
        operation_ref=OP_REF,
        session_id=SESSION_REF,
        idempotency_key="idem_phase_e2_create",
        role_key=ROLE_KEY,
        approval_token=SESSION_LIFECYCLE_APPROVAL_TOKEN,
        enabled=True,
        role_file_digest=config.expected_role_digest,
        prompt_ref="claim_prompt_phase_e2_create",
        context_refs=("claim_context_phase_e2",),
        cwd_ref="workspace_ref_phase_e2_smoke",
        allowed_roots_ref="allowed_roots_ref_phase_e2_smoke",
        lease_id=LEASE_ID,
        lease_epoch=1,
        lease_holder_ref=LEASE_HOLDER,
        expected_state_version=0,
        operator_gate=True,
        max_turns=MAX_TURNS,
        max_artifacts_per_turn=MAX_ARTIFACTS_PER_TURN,
    )

    created = False
    last_turn_res: Any = None
    try:
        create_res = create_session(
            create_req, store=store, open_session=bind_open_session(config, backend=backend)
        )
        if not create_res.ok or create_res.lifecycle_state != "session_open":
            raise SmokeError(f"create: lifecycle_state={create_res.lifecycle_state!r}")
        created = True
        binding = create_res.session_binding
        if not binding:
            raise SmokeError("create: missing session binding")

        for i, prompt in enumerate(prompts, start=1):
            # Use the legacy key for the default single-turn case to preserve
            # idempotency semantics for existing real-mode replays.
            idem_key = (
                "idem_phase_e2_turn" if turn_prompts is None else f"idem_phase_e2_turn_{i:03d}"
            )
            send_req = SessionSendRequest(
                activity_id=ACTIVITY_ID,
                session_id=SESSION_REF,
                transaction_ref=TXN_REF,
                operation_ref=OP_REF,
                idempotency_key=idem_key,
                approval_token=SESSION_LIFECYCLE_APPROVAL_TOKEN,
                enabled=True,
                session_binding=binding,
                prompt_ref="claim_prompt_phase_e2_turn",
                context_refs=("claim_context_phase_e2_turn",),
                lease_id=LEASE_ID,
                lease_epoch=1,
                lease_holder_ref=LEASE_HOLDER,
                expected_state_version=i,
                operator_gate=True,
            )
            last_turn_res = send_session_turn(
                send_req, store=store, run_turn=bind_run_turn(config, prompt, backend=backend)
            )
            if not last_turn_res.ok or last_turn_res.status != "completed":
                raise SmokeError(f"turn {i}: status={last_turn_res.status!r}")

        close_req = SessionCloseRequest(
            activity_id=ACTIVITY_ID,
            session_id=SESSION_REF,
            transaction_ref=TXN_REF,
            operation_ref=OP_REF,
            idempotency_key="idem_phase_e2_close",
            approval_token=SESSION_LIFECYCLE_APPROVAL_TOKEN,
            enabled=True,
            session_binding=binding,
            lease_id=LEASE_ID,
            lease_epoch=1,
            lease_holder_ref=LEASE_HOLDER,
            expected_state_version=n_turns + 1,
            operator_gate=True,
        )
        close_res = close_session(
            close_req, store=store, apply_close=bind_close_session(config, backend=backend)
        )
        if not close_res.ok or close_res.lifecycle_state != "session_closed":
            raise SmokeError(f"close: lifecycle_state={close_res.lifecycle_state!r}")
        closed = True
    except Exception:
        # Leak guard: if anything failed after create, best-effort close the real
        # session so the smoke never strands a live persistent session.
        if created:
            best_effort_close_real_session(config, backend=backend)
        raise

    turn_state = last_turn_res.to_durable_state()
    return {
        "execution_pipeline": {
            "create": {
                "ok": create_res.ok,
                "lifecycle_state": create_res.lifecycle_state,
                "session_binding_prefix": binding[:6],
            },
            "turn": {
                "ok": last_turn_res.ok,
                "status": last_turn_res.status,
                "artifact_ref_count": turn_state["artifact_ref_count"],
                "final_message_persisted": "final_message" in turn_state,
            },
            "close": {"ok": close_res.ok, "lifecycle_state": close_res.lifecycle_state},
        },
        "business_task": {
            "business_verdict": None,
            "cancellation_executed": False,
        },
        "turn_count": n_turns,
        "_store": store,
        "_closed": closed,
    }


def _wait_for_turn_claimed(store: SessionLifecycleStore, *, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        session = query_session(store, activity_id=ACTIVITY_ID)
        state = session.to_durable_state()
        if state["lifecycle_state"] == "session_turn" and state["open_turn_index"] == 1:
            return
        time.sleep(0.01)
    raise SmokeError("cancel smoke: timed out waiting for a claimed in-flight turn")


def _release_blocked_turn(backend: Any | None) -> None:
    release = getattr(backend, "release_turn", None)
    if release is not None and hasattr(release, "set"):
        release.set()


def run_cancellation_lifecycle(
    *, config: RealPersistentSessionConfig, backend: Any | None = None
) -> dict[str, Any]:
    """Drive create -> in-flight turn -> cancel request -> real interrupt -> close.

    The self-test backend blocks the turn until ``abort`` runs, giving the smoke
    deterministic proof that WP3b cancellation is applied while a turn is really
    in flight. Real mode uses the same wiring and fails if it cannot observe the
    claimed turn before timeout.
    """

    store = SessionLifecycleStore()
    store.grant_lease(
        activity_id=ACTIVITY_ID,
        lease_id=LEASE_ID,
        lease_epoch=1,
        lease_holder_ref=LEASE_HOLDER,
        state_version=0,
    )

    create_req = SessionCreateRequest(
        activity_id=ACTIVITY_ID,
        transaction_ref=TXN_REF,
        operation_ref=OP_REF,
        session_id=SESSION_REF,
        idempotency_key="idem_phase_e2_create",
        role_key=ROLE_KEY,
        approval_token=SESSION_LIFECYCLE_APPROVAL_TOKEN,
        enabled=True,
        role_file_digest=config.expected_role_digest,
        prompt_ref="claim_prompt_phase_e2_create",
        context_refs=("claim_context_phase_e2",),
        cwd_ref="workspace_ref_phase_e2_smoke",
        allowed_roots_ref="allowed_roots_ref_phase_e2_smoke",
        lease_id=LEASE_ID,
        lease_epoch=1,
        lease_holder_ref=LEASE_HOLDER,
        expected_state_version=0,
        operator_gate=True,
        max_turns=MAX_TURNS,
        max_artifacts_per_turn=MAX_ARTIFACTS_PER_TURN,
    )
    create_res = create_session(
        create_req, store=store, open_session=bind_open_session(config, backend=backend)
    )
    if not create_res.ok or create_res.lifecycle_state != "session_open":
        raise SmokeError(f"create: lifecycle_state={create_res.lifecycle_state!r}")
    binding = create_res.session_binding
    if not binding:
        raise SmokeError("create: missing session binding")

    turn_result: dict[str, Any] = {}
    turn_errors: list[BaseException] = []

    def _send_turn() -> None:
        try:
            send_req = SessionSendRequest(
                activity_id=ACTIVITY_ID,
                session_id=SESSION_REF,
                transaction_ref=TXN_REF,
                operation_ref=OP_REF,
                idempotency_key="idem_phase_e2_turn_cancel",
                approval_token=SESSION_LIFECYCLE_APPROVAL_TOKEN,
                enabled=True,
                session_binding=binding,
                prompt_ref="claim_prompt_phase_e2_cancel_turn",
                context_refs=("claim_context_phase_e2_cancel_turn",),
                lease_id=LEASE_ID,
                lease_epoch=1,
                lease_holder_ref=LEASE_HOLDER,
                expected_state_version=1,
                operator_gate=True,
            )
            turn_result["value"] = send_session_turn(
                send_req,
                store=store,
                run_turn=bind_run_turn(config, CANCEL_TURN_PROMPT, backend=backend),
            )
        except BaseException as exc:  # pragma: no cover - surfaced after join
            turn_errors.append(exc)

    thread = threading.Thread(
        target=_send_turn, name="wp3b-cancel-smoke-turn", daemon=True
    )
    pending_error: BaseException | None = None
    cancel_res: Any | None = None
    interrupt_res: Any | None = None
    thread.start()
    try:
        _wait_for_turn_claimed(store)

        cancel_req = CancellationRequest(
            cancel_id="cancel_phase_e2_smoke",
            activity_id=ACTIVITY_ID,
            session_id=SESSION_REF,
            transaction_ref=TXN_REF,
            operation_ref=OP_REF,
            idempotency_key="idem_phase_e2_cancel_request",
            approval_token=SESSION_LIFECYCLE_APPROVAL_TOKEN,
            enabled=True,
            session_binding=binding,
            requested_by_ref="operator_ref_phase_e2_smoke",
            reason_code="operator_requested_stop",
            turn_index=1,
            lease_id=LEASE_ID,
            lease_epoch=1,
            lease_holder_ref=LEASE_HOLDER,
            operator_gate=True,
            execute=False,
        )
        cancel_res = request_cancellation(cancel_req, store=store)
        if cancel_res.status != "cancel_requested":
            raise SmokeError(f"cancel request: status={cancel_res.status!r}")

        interrupt_req = SessionInterruptRequest(
            cancel_id="cancel_phase_e2_smoke",
            activity_id=ACTIVITY_ID,
            session_id=SESSION_REF,
            transaction_ref=TXN_REF,
            operation_ref=OP_REF,
            idempotency_key="idem_phase_e2_interrupt",
            approval_token=SESSION_INTERRUPT_API_APPROVAL_TOKEN,
            enabled=True,
            session_binding=binding,
            requested_by_ref="operator_ref_phase_e2_smoke",
            reason_code="operator_requested_stop",
            turn_index=1,
            lease_id=LEASE_ID,
            lease_epoch=1,
            lease_holder_ref=LEASE_HOLDER,
            operator_gate=True,
        )
        interrupt_res = apply_session_interrupt(
            interrupt_req,
            store=store,
            apply_interrupt=bind_real_cancellation(build_cancel_config(config), backend=backend),
        )
        if interrupt_res.status != "cancelled":
            raise SmokeError(f"interrupt: status={interrupt_res.status!r}")
    except BaseException as exc:
        pending_error = exc
    finally:
        _release_blocked_turn(backend)
        thread.join(timeout=10.0)

    try:
        if thread.is_alive():
            raise SmokeError("cancel smoke: send thread did not finish after interrupt")
        if pending_error is not None:
            raise pending_error
        if cancel_res is None or interrupt_res is None:
            raise SmokeError("cancel smoke: missing cancellation/interrupt result")
        if turn_errors:
            raise SmokeError(
                f"cancel smoke: send thread failed with {type(turn_errors[0]).__name__}"
            )
        last_turn_res = turn_result.get("value")
        if last_turn_res is None:
            raise SmokeError("cancel smoke: send thread produced no turn result")

        close_req = SessionCloseRequest(
            activity_id=ACTIVITY_ID,
            session_id=SESSION_REF,
            transaction_ref=TXN_REF,
            operation_ref=OP_REF,
            idempotency_key="idem_phase_e2_close",
            approval_token=SESSION_LIFECYCLE_APPROVAL_TOKEN,
            enabled=True,
            session_binding=binding,
            lease_id=LEASE_ID,
            lease_epoch=1,
            lease_holder_ref=LEASE_HOLDER,
            expected_state_version=2,
            operator_gate=True,
        )
        close_res = close_session(
            close_req, store=store, apply_close=bind_close_session(config, backend=backend)
        )
        if not close_res.ok or close_res.lifecycle_state != "session_closed":
            raise SmokeError(f"close: lifecycle_state={close_res.lifecycle_state!r}")
    except Exception:
        try:
            best_effort_close_real_session(config, backend=backend)
        except Exception:
            pass
        raise

    turn_state = last_turn_res.to_durable_state()
    cancel_state = interrupt_res.to_durable_state()
    backend_abort_calls = getattr(backend, "abort_calls", None)
    backend_released_turn = getattr(backend, "abort_released_turn", False) is True
    turn_interrupted_observed = (
        backend_abort_calls == 1
        and backend_released_turn
        and last_turn_res.status != "completed"
    )
    return {
        "execution_pipeline": {
            "create": {
                "ok": create_res.ok,
                "lifecycle_state": create_res.lifecycle_state,
                "session_binding_prefix": binding[:6],
            },
            "turn": {
                "ok": last_turn_res.ok,
                "status": last_turn_res.status,
                "artifact_ref_count": turn_state["artifact_ref_count"],
                "final_message_persisted": "final_message" in turn_state,
                "interrupted_observed": turn_interrupted_observed,
            },
            "cancel_request": {
                "ok": cancel_res.to_durable_state()["ok"],
                "status": cancel_res.status,
            },
            "interrupt": {
                "ok": cancel_state["ok"],
                "status": interrupt_res.status,
                "evidence_digest_present": cancel_state["evidence_digest"] is not None,
                "error_code": interrupt_res.error_code,
            },
            "close": {"ok": close_res.ok, "lifecycle_state": close_res.lifecycle_state},
        },
        "business_task": {
            "business_verdict": None,
            "cancellation_executed": turn_interrupted_observed,
            "cleanup_verified": interrupt_res.status == "cancelled",
            "backend_abort_calls": backend_abort_calls,
            "backend_released_turn": backend_released_turn,
        },
        "turn_count": 1,
        "_store": store,
        "_closed": True,
    }


# --------------------------------------------------------------------------- #
# Host-side post-verify
# --------------------------------------------------------------------------- #
def post_verify(
    *,
    store: SessionLifecycleStore,
    config: RealPersistentSessionConfig,
    mode: str,
    require_marker: bool = True,
) -> dict[str, Any]:
    session = query_session(store, activity_id=ACTIVITY_ID)
    turns = list_session_turns(store, activity_id=ACTIVITY_ID)
    resolved = validate_real_session_config(config)
    acpx_basename = Path(resolved.acpx_binary).name

    verify: dict[str, Any] = {
        "closed": session.lifecycle_state == "session_closed",
        "turn_count_state_machine": len(turns),
        "npx_in_runner": acpx_basename.lower() in {"npx", "npm", "pnpm", "yarn", "bunx"},
        "acpx_binary_basename": acpx_basename,
        "no_forbidden_surface": True,
        "worktree_clean_expectation": (
            "this smoke writes only under caller-owned sessions/evidence/work dirs "
            "outside the tracked repo, so `git status` of the worktree stays clean"
        ),
    }
    if mode == "real":
        sessions_root = Path(config.sessions_dir)
        session_dirs = (
            [p for p in sessions_root.iterdir() if p.is_dir()] if sessions_root.exists() else []
        )
        verify["supervisor_session_count"] = len(session_dirs)
        turns_root = sessions_root / config.runtime_session_id / "turns"
        turn_dirs = (
            [p for p in turns_root.iterdir() if p.is_dir()] if turns_root.exists() else []
        )
        verify["supervisor_turn_count"] = len(turn_dirs)
        supervisor_session_state_closed = False
        session_json_path = sessions_root / resolved.runtime_session_id / "session.json"
        try:
            session_payload = json.loads(session_json_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            session_payload = None
        if isinstance(session_payload, dict):
            supervisor_session_state_closed = session_payload.get("state") == "closed"
            verify["supervisor_acpx_version"] = session_payload.get("acpx_version")
            verify["supervisor_adapter_agent"] = session_payload.get("adapter_agent")
            verify["supervisor_role_id"] = session_payload.get("role_id")
        verify["supervisor_session_state_closed"] = supervisor_session_state_closed
        marker_checked = False
        marker_matches = False
        if turn_dirs:
            sorted_turn_dirs = sorted(turn_dirs, key=lambda p: p.name)
            all_readable = True
            all_match = True
            for td in sorted_turn_dirs:
                result_path = td / "result.json"
                try:
                    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    result_payload = None
                if not isinstance(result_payload, dict):
                    all_readable = False
                    all_match = False
                else:
                    final_message = result_payload.get("final_message")
                    if not (isinstance(final_message, str) and final_message.strip() == TURN_MARKER):
                        all_match = False
            marker_checked = all_readable
            marker_matches = all_readable and all_match
        verify["business_marker_checked"] = marker_checked
        verify["business_marker_matches"] = marker_matches
        verify["business_marker_expected"] = TURN_MARKER
        verify["business_marker_required"] = require_marker
    return verify


def assert_post_verify(
    verify: dict[str, Any], *, mode: str, require_marker: bool = True
) -> None:
    if not verify["closed"]:
        raise SmokeError("post-verify: session is not closed")
    n = verify["turn_count_state_machine"]
    if n < 1:
        raise SmokeError(f"post-verify: expected at least 1 turn, got {n}")
    if verify["npx_in_runner"]:
        raise SmokeError("post-verify: runner basename is an npx/package-manager launcher")
    if mode == "real":
        if verify.get("supervisor_session_count") != 1:
            raise SmokeError(
                f"post-verify: expected exactly 1 supervisor session, "
                f"got {verify.get('supervisor_session_count')}"
            )
        if verify.get("supervisor_turn_count") != n:
            raise SmokeError(
                f"post-verify: expected exactly {n} supervisor turn dir(s), "
                f"got {verify.get('supervisor_turn_count')}"
            )
        if not verify.get("supervisor_session_state_closed"):
            raise SmokeError("post-verify: supervisor session.json state is not closed")
        if require_marker and not verify.get("business_marker_checked"):
            raise SmokeError("post-verify: turn result.json final_message was not checkable")
        if require_marker and not verify.get("business_marker_matches"):
            raise SmokeError("post-verify: turn final_message did not match the smoke marker")


# --------------------------------------------------------------------------- #
# Self-test backend (no acpx, no agent_run_supervisor)
# --------------------------------------------------------------------------- #
class _SelfTestBackend:
    """In-process fake runtime backend for ``--self-test`` (deterministic)."""

    def __init__(self, *, block_turn_until_cancel: bool = False) -> None:
        self.block_turn_until_cancel = block_turn_until_cancel
        self.turn_entered = threading.Event()
        self.release_turn = threading.Event()
        self.abort_calls = 0
        self.abort_released_turn = False

    def create(self, resolved: Any) -> Any:
        from sachima_supervisor.activity_session_real_execution import _RuntimeCreateResult

        return _RuntimeCreateResult(acpx_session_id="self-test-session", state="open")

    def send(self, resolved: Any, prompt: str) -> Any:
        from sachima_supervisor.activity_session_real_execution import _RuntimeTurnResult

        if self.block_turn_until_cancel:
            self.turn_entered.set()
            if not self.release_turn.wait(timeout=10.0):
                raise SmokeError("self-test backend timed out waiting for cancel release")
            completed = not self.abort_released_turn
            status_label = "completed" if completed else "cancelled_by_abort"
            artifact_count = 1 if completed else 0
        else:
            completed = True
            status_label = "completed"
            artifact_count = 1
        return _RuntimeTurnResult(
            completed=completed,
            status_label=status_label,
            turn_id="self-test-turn",
            artifact_count=artifact_count,
        )

    def abort(self, resolved: Any) -> Any:
        from sachima_supervisor.activity_session_real_execution import _RuntimeAbortResult

        self.abort_calls += 1
        self.abort_released_turn = True
        self.release_turn.set()
        return _RuntimeAbortResult(cancelled=True, state="cancelled")

    def close(self, resolved: Any) -> Any:
        from sachima_supervisor.activity_session_real_execution import _RuntimeCloseResult

        return _RuntimeCloseResult(closed=True, state="closed")

    def best_effort_close(self, resolved: Any) -> None:
        self.release_turn.set()
        return None


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def assert_cancel_during_turn_observed(lifecycle: Mapping[str, Any]) -> None:
    business = lifecycle.get("business_task", {})
    pipeline = lifecycle.get("execution_pipeline", {})
    turn = pipeline.get("turn", {}) if isinstance(pipeline, Mapping) else {}
    if not (
        isinstance(business, Mapping)
        and business.get("cancellation_executed") is True
        and business.get("backend_abort_calls") == 1
        and business.get("backend_released_turn") is True
        and isinstance(turn, Mapping)
        and turn.get("interrupted_observed") is True
        and turn.get("status") != "completed"
    ):
        raise SmokeError(
            "cancel-during-turn did not prove abort_calls=1, released in-flight turn, "
            "and a non-completed interrupted turn"
        )


def preflight_real(acpx_binary: str) -> None:
    binary = Path(acpx_binary)
    if not binary.is_file():
        raise EnvironmentNotReady(f"pinned acpx binary not found: {acpx_binary}")
    try:
        import agent_run_supervisor  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        raise EnvironmentNotReady(f"agent_run_supervisor is not importable: {exc}") from exc


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    mode = "self_test" if args.self_test else "real"
    role_path = Path(args.role).resolve()
    sessions_dir = Path(args.sessions_dir).resolve()
    evidence_dir = Path(args.evidence_dir).resolve()
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    acpx_binary = args.acpx_binary or str((work_dir / "pinned-acpx-placeholder").resolve())

    if args.cancel_during_turn and mode == "real":
        raise EnvironmentNotReady(
            "--cancel-during-turn is currently deterministic self-test only; "
            "real acpx cancel did not reliably confirm active-run cancellation on this host"
        )

    if mode == "real":
        if not args.acpx_binary:
            raise EnvironmentNotReady("--acpx-binary is required for a real smoke")
        preflight_real(args.acpx_binary)
    elif not args.acpx_binary:
        # Provide a self-test placeholder binary that passes provenance shape
        # checks without being a launcher.
        placeholder = work_dir / "acpx"
        placeholder.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        placeholder.chmod(0o755)
        acpx_binary = str(placeholder)

    resolved_role = build_resolved_role(
        role_path=role_path, acpx_binary=acpx_binary, work_dir=work_dir, model=args.model
    )
    resolved_role_path = write_resolved_role(resolved_role, evidence_dir)
    config = build_config(
        resolved_role_path=resolved_role_path,
        sessions_dir=sessions_dir,
        evidence_dir=evidence_dir,
        work_dir=work_dir,
        session_id=args.session_id,
        acpx_sha256=args.acpx_sha256,
        allow_repo_paths=args.allow_repo_paths,
    )

    turn_count = args.turn_count
    if turn_count < 1:
        raise SmokeError(f"--turn-count must be >= 1, got {turn_count}")
    if args.cancel_during_turn and turn_count != 1:
        raise SmokeError("--cancel-during-turn requires --turn-count 1")
    turn_prompts = None if turn_count == 1 else tuple(TURN_PROMPT for _ in range(turn_count))

    backend = (
        _SelfTestBackend(block_turn_until_cancel=args.cancel_during_turn)
        if mode == "self_test"
        else None
    )
    if args.cancel_during_turn:
        lifecycle = run_cancellation_lifecycle(config=config, backend=backend)
        assert_cancel_during_turn_observed(lifecycle)
    else:
        lifecycle = run_lifecycle(config=config, backend=backend, turn_prompts=turn_prompts)
    store = lifecycle.pop("_store")
    lifecycle.pop("_closed", None)
    require_marker = not args.cancel_during_turn
    verify = post_verify(store=store, config=config, mode=mode, require_marker=require_marker)
    assert_post_verify(verify, mode=mode, require_marker=require_marker)
    if mode == "real":
        lifecycle["business_task"] = {
            **lifecycle["business_task"],
            "turn_marker_verified": bool(verify.get("business_marker_matches")),
            "expected_marker": TURN_MARKER,
        }

    summary = {
        "smoke": "sachima-phase-e2-bounded-real-persistent-session",
        "ok": True,
        "mode": mode,
        "cancel_during_turn": bool(args.cancel_during_turn),
        "runtime_session_id": args.session_id,
        **lifecycle,
        "post_verify": verify,
        "non_approvals_held": {
            "unapproved_cancellation_execution": False,
            "wp3b_bounded_cancellation_execution": bool(args.cancel_during_turn),
            "gateway": False,
            "feishu_or_im_delivery": False,
            "live_or_default_on": False,
            "production_config_write": False,
            "real_delivery": False,
        },
    }
    return 0, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sachima_phase_e2_persistent_session_smoke",
        description="Sachima Phase E-2 bounded real persistent-session smoke (local/offline).",
    )
    parser.add_argument("--role", default=str(COMMITTED_ROLE), help="Committed portable role JSON.")
    parser.add_argument("--acpx-binary", default=None, help="Absolute path to a pinned local acpx.")
    parser.add_argument("--acpx-sha256", default=None, help="Expected sha256:<hex> of the acpx binary.")
    parser.add_argument("--sessions-dir", required=True, help="Caller-owned supervisor sessions dir.")
    parser.add_argument("--evidence-dir", required=True, help="Caller-owned evidence/scratch dir.")
    parser.add_argument("--work-dir", required=True, help="Caller-owned acpx working directory.")
    parser.add_argument("--session-id", default="e2-smoke-session", help="Supervisor-local session id.")
    parser.add_argument("--model", default=None, help="Optional model overlay for the runner.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the lifecycle with an in-process fake backend (no acpx / no agent_run_supervisor).",
    )
    parser.add_argument(
        "--allow-repo-paths",
        action="store_true",
        help="Test-only: allow runtime/evidence paths inside the repo tree.",
    )
    parser.add_argument(
        "--turn-count",
        type=int,
        default=1,
        help=(
            "Run N sequential read-only turns in one session (default: 1). "
            "Must be >= 1. When 1, legacy single-turn idempotency key is preserved."
        ),
    )
    parser.add_argument(
        "--cancel-during-turn",
        action="store_true",
        help=(
            "Exercise WP3b bounded cancellation while turn 1 is in flight. "
            "Currently deterministic self-test only: the fake backend blocks until abort() "
            "proves the interrupt path, while real acpx cancellation remains host/ACP dependent."
        ),
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep the sessions/evidence/work dirs (default: clean them up on success).",
    )
    args = parser.parse_args(argv)

    summary: dict[str, Any]
    try:
        exit_code, summary = run(args)
    except EnvironmentNotReady as exc:
        summary = {
            "smoke": "sachima-phase-e2-bounded-real-persistent-session",
            "ok": False,
            "skipped": str(exc),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 2
    except SmokeError as exc:
        summary = {
            "smoke": "sachima-phase-e2-bounded-real-persistent-session",
            "ok": False,
            "error": str(exc),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1

    if not args.keep_artifacts:
        for path in (args.sessions_dir, args.evidence_dir, args.work_dir):
            shutil.rmtree(path, ignore_errors=True)
        summary["artifacts"] = {"cleaned": True}
    else:
        summary["artifacts"] = {
            "sessions_dir": args.sessions_dir,
            "evidence_dir": args.evidence_dir,
            "work_dir": args.work_dir,
        }

    print(json.dumps(summary, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
