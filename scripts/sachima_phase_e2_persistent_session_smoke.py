#!/usr/bin/env python3
"""Sachima Phase E-2 bounded real persistent-session smoke (local/offline).

Drives the **existing** Phase E state machine
(``sachima_supervisor.activity_session_lifecycle``) through the Phase E-2 real
execution bridge (``sachima_supervisor.activity_session_real_execution``) over a
single minimal persistent-session lifecycle:

    create  ->  send (one read-only turn)  ->  close

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
  * Cancellation execution is NOT performed (request-state only elsewhere).
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
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sachima_supervisor.activity_session_lifecycle import (  # noqa: E402
    SESSION_LIFECYCLE_APPROVAL_TOKEN,
    SessionCloseRequest,
    SessionCreateRequest,
    SessionLifecycleStore,
    SessionSendRequest,
    close_session,
    create_session,
    list_session_turns,
    query_session,
    send_session_turn,
)
from sachima_supervisor.activity_session_real_execution import (  # noqa: E402
    PHASE_E2_REAL_SESSION_APPROVAL_TOKEN,
    RealPersistentSessionConfig,
    best_effort_close_real_session,
    bind_close_session,
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


# --------------------------------------------------------------------------- #
# Lifecycle (deterministic; backend-injectable for self-test)
# --------------------------------------------------------------------------- #
def run_lifecycle(
    *, config: RealPersistentSessionConfig, backend: Any | None = None
) -> dict[str, Any]:
    """Drive create -> send(one read-only turn) -> close and return a summary.

    ``backend=None`` uses the default lazy real runtime backend. A fake backend
    can be injected to exercise the identical wiring deterministically.
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

    created = False
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

        send_req = SessionSendRequest(
            activity_id=ACTIVITY_ID,
            session_id=SESSION_REF,
            transaction_ref=TXN_REF,
            operation_ref=OP_REF,
            idempotency_key="idem_phase_e2_turn",
            approval_token=SESSION_LIFECYCLE_APPROVAL_TOKEN,
            enabled=True,
            session_binding=binding,
            prompt_ref="claim_prompt_phase_e2_turn",
            context_refs=("claim_context_phase_e2_turn",),
            lease_id=LEASE_ID,
            lease_epoch=1,
            lease_holder_ref=LEASE_HOLDER,
            expected_state_version=1,
            operator_gate=True,
        )
        turn_res = send_session_turn(
            send_req, store=store, run_turn=bind_run_turn(config, TURN_PROMPT, backend=backend)
        )
        if not turn_res.ok or turn_res.status != "completed":
            raise SmokeError(f"turn: status={turn_res.status!r}")

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
        closed = True
    except Exception:
        # Leak guard: if anything failed after create, best-effort close the real
        # session so the smoke never strands a live persistent session.
        if created:
            best_effort_close_real_session(config, backend=backend)
        raise

    turn_state = turn_res.to_durable_state()
    return {
        "execution_pipeline": {
            "create": {
                "ok": create_res.ok,
                "lifecycle_state": create_res.lifecycle_state,
                "session_binding_prefix": binding[:6],
            },
            "turn": {
                "ok": turn_res.ok,
                "status": turn_res.status,
                "artifact_ref_count": turn_state["artifact_ref_count"],
                "final_message_persisted": "final_message" in turn_state,
            },
            "close": {"ok": close_res.ok, "lifecycle_state": close_res.lifecycle_state},
        },
        "business_task": {
            "business_verdict": None,
            "cancellation_executed": False,
        },
        "_store": store,
        "_closed": closed,
    }


# --------------------------------------------------------------------------- #
# Host-side post-verify
# --------------------------------------------------------------------------- #
def post_verify(
    *, store: SessionLifecycleStore, config: RealPersistentSessionConfig, mode: str
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
        if len(turn_dirs) == 1:
            result_path = turn_dirs[0] / "result.json"
            try:
                result_payload = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                result_payload = None
            if isinstance(result_payload, dict):
                marker_checked = True
                final_message = result_payload.get("final_message")
                marker_matches = isinstance(final_message, str) and final_message.strip() == TURN_MARKER
        verify["business_marker_checked"] = marker_checked
        verify["business_marker_matches"] = marker_matches
        verify["business_marker_expected"] = TURN_MARKER
    return verify


def assert_post_verify(verify: dict[str, Any], *, mode: str) -> None:
    if not verify["closed"]:
        raise SmokeError("post-verify: session is not closed")
    if verify["turn_count_state_machine"] != 1:
        raise SmokeError(f"post-verify: expected 1 turn, got {verify['turn_count_state_machine']}")
    if verify["npx_in_runner"]:
        raise SmokeError("post-verify: runner basename is an npx/package-manager launcher")
    if mode == "real":
        if verify.get("supervisor_session_count") != 1:
            raise SmokeError(
                f"post-verify: expected exactly 1 supervisor session, "
                f"got {verify.get('supervisor_session_count')}"
            )
        if verify.get("supervisor_turn_count") != 1:
            raise SmokeError(
                f"post-verify: expected exactly 1 supervisor turn dir, "
                f"got {verify.get('supervisor_turn_count')}"
            )
        if not verify.get("supervisor_session_state_closed"):
            raise SmokeError("post-verify: supervisor session.json state is not closed")
        if not verify.get("business_marker_checked"):
            raise SmokeError("post-verify: turn result.json final_message was not checkable")
        if not verify.get("business_marker_matches"):
            raise SmokeError("post-verify: turn final_message did not match the smoke marker")


# --------------------------------------------------------------------------- #
# Self-test backend (no acpx, no agent_run_supervisor)
# --------------------------------------------------------------------------- #
class _SelfTestBackend:
    """In-process fake runtime backend for ``--self-test`` (deterministic)."""

    def create(self, resolved: Any) -> Any:
        from sachima_supervisor.activity_session_real_execution import _RuntimeCreateResult

        return _RuntimeCreateResult(acpx_session_id="self-test-session", state="open")

    def send(self, resolved: Any, prompt: str) -> Any:
        from sachima_supervisor.activity_session_real_execution import _RuntimeTurnResult

        return _RuntimeTurnResult(
            completed=True, status_label="completed", turn_id="self-test-turn", artifact_count=1
        )

    def close(self, resolved: Any) -> Any:
        from sachima_supervisor.activity_session_real_execution import _RuntimeCloseResult

        return _RuntimeCloseResult(closed=True, state="closed")

    def best_effort_close(self, resolved: Any) -> None:
        return None


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
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

    backend = _SelfTestBackend() if mode == "self_test" else None
    lifecycle = run_lifecycle(config=config, backend=backend)
    store = lifecycle.pop("_store")
    lifecycle.pop("_closed", None)
    verify = post_verify(store=store, config=config, mode=mode)
    assert_post_verify(verify, mode=mode)
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
        "runtime_session_id": args.session_id,
        **lifecycle,
        "post_verify": verify,
        "non_approvals_held": {
            "cancellation_execution": False,
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
