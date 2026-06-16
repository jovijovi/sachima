"""Phase E-2 bounded *real* persistent-session execution bridge (local/offline).

This module is the next narrow slice after the Phase E local/offline lifecycle
state machine (``activity_session_lifecycle``). It lets a local Sachima /
FlowWeaver / Hermes controller drive the **existing** Phase E state machine with
work outcomes produced by a *real*
``agent_run_supervisor.session_runtime.SessionRuntime`` — open a persistent
session, run one read-only turn, and close it — while keeping the committed
source default-off, fail-closed, and CI-safe.

What this slice is, and is deliberately NOT:

  * **Default-off + exact approval token.** Every entry point validates an exact
    Phase E-2 approval token and ``enabled is True`` before anything else; a
    missing / false / mismatched gate fails closed with a stable error code
    *before* any optional dependency is imported or any runtime is touched.
  * **Bounded real execution, local/offline only.** The only real surface is a
    pinned local ``acpx`` persistent session through ``SessionRuntime``. There is
    no Gateway, Feishu, IM delivery, public ingress, live/default-on behavior,
    production config write, service restart, platform-adapter mutation, or real
    delivery anywhere in this module.
  * **Pinned local acpx only.** The runner provenance gate requires
    ``runner.acpx_binary`` to be a non-null *absolute local* path whose basename
    is not a package-manager / shell launcher (``npx``/``npm``/``pnpm``/``yarn``/
    ``bunx``/``bun``/``node``/``sh``/…). A committed role with ``acpx_binary:
    null`` is therefore non-runnable by construction until an operator local
    overlay pins a verified local acpx. There is no npx/network fallback.
  * **Cancellation execution is separately gated.** ``execute_real_cancellation``
    requires the distinct WP3b cancellation approval token before it can call the
    local supervisor abort path. Without that exact gate, cancellation still
    fails closed with ``activity_cancel_not_approved`` before runtime touch.
  * **Lazy import.** ``agent_run_supervisor`` is imported lazily, only inside the
    default runtime backend's methods. Importing this module — and validating a
    config — never requires the external package, so normal CI is unaffected.
  * **Sanitized projections only.** Runtime outcomes are mapped to the state
    machine's ``SessionWorkOutcome`` carrying only stable codes, an opaque
    derived ``session_binding`` (a hash of the runtime/acpx session id, never the
    raw id), safe evidence refs/digests, and counts. The final message, raw
    prompt/context, tool output, and raw exception text never cross into durable
    Sachima state.

The state machine still owns durability, idempotency, leases, and the lock
ordering; this module only supplies the injected work callables and the
fail-closed config gate around the real runtime.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .activity_session_lifecycle import (
    SESSION_INTERRUPT_API_APPROVAL_TOKEN,
    SessionCloseRequest,
    SessionCreateRequest,
    SessionInterruptOutcome,
    SessionInterruptRequest,
    SessionSendRequest,
    SessionWorkOutcome,
    _safe_interrupt_call as _lifecycle_safe_interrupt_call,
    apply_session_interrupt as _lifecycle_apply_session_interrupt,
)

# --------------------------------------------------------------------------- #
# Approval token
# --------------------------------------------------------------------------- #
#: Exact approval token required to enable Phase E-2 bounded real
#: persistent-session execution. It is deliberately narrower and distinct from
#: the Phase E lifecycle state-machine token: it approves a *bounded local
#: real* persistent session (create / one read-only turn / close) and an
#: explicit minimal real smoke — and nothing live, Gateway, Feishu, production,
#: or delivery related.
PHASE_E2_REAL_SESSION_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_phase_e2_bounded_real_persistent_session_"
    "execution_local_offline_smoke_no_live_no_gateway_no_feishu_no_production_config_"
    "no_real_delivery"
)

#: Exact approval token required for WP3b bounded real cancellation execution.
#: Deliberately narrower and distinct from both the session token and the lifecycle
#: token: it approves a *bounded local cancel* (abort with cleanup proof) and
#: nothing live, Gateway, Feishu, production-write, or real-delivery related.
PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_bounded_cancellation_execution_local_offline_"
    "with_cleanup_proof_operator_gated_read_only_sessions_only_no_write_roles_no_live_"
    "no_gateway_no_feishu_no_production_config_no_real_delivery"
)

# --------------------------------------------------------------------------- #
# Stable error taxonomy (subset of the lifecycle stored taxonomy)
# --------------------------------------------------------------------------- #
_ERROR_DISABLED = "activity_session_disabled"
_ERROR_APPROVAL = "activity_session_approval_mismatch"
_ERROR_CANCEL_NOT_APPROVED = "activity_cancel_not_approved"
_ERROR_PROVENANCE = "activity_runner_provenance_unverified"
_ERROR_ROLE_CAPABILITY = "activity_role_capability_rejected"
_ERROR_PRECONDITION = "activity_precondition_unmet"
_ERROR_UNSAFE = "activity_unsafe_material"
_ERROR_SUPERVISOR_FAILED = "activity_supervisor_failed"
_ERROR_CANCEL_AMBIGUOUS = "activity_cancel_ambiguous"

# Stable supervisor-status labels surfaced into the sanitized outcome. These are
# Sachima-owned codes, never raw runtime/model text.
_STATUS_OPEN = "session_open"
_STATUS_TURN = "turn_completed"
_STATUS_CLOSED = "session_closed"
_STATUS_CANCELLED = "session_cancelled"

#: Runner identity required by this first slice.
_REQUIRED_RUNNER_TYPE = "acpx"
_REQUIRED_ACPX_VERSION = "0.10.0"
_REQUIRED_ADAPTER = "codex"

#: Launcher basenames that must never be treated as a runnable acpx binary. A
#: pinned local acpx executable is required; package-manager / shell / runtime
#: launchers would (re)introduce a network-fetch or indirection path.
_FORBIDDEN_BINARY_BASENAMES = frozenset(
    {
        "npx",
        "npm",
        "pnpm",
        "yarn",
        "bunx",
        "bun",
        "node",
        "deno",
        "sh",
        "bash",
        "zsh",
        "dash",
        "fish",
        "env",
        "python",
        "python3",
        "uv",
        "uvx",
        "pipx",
    }
)

#: Forbidden delivery / live-surface markers. Their presence in a role file or a
#: config path is a hard fail: this slice is local/offline only.
_FORBIDDEN_SURFACE_MARKERS = (
    "gateway",
    "feishu",
    "lark_im",
    "webhook",
    "ingress",
    "im_delivery",
    "real_delivery",
)

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_PATH_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

#: Repo root of the committed tree. Caller-provided runtime/evidence/scratch
#: paths must live outside it (unless a test explicitly overrides), so a real
#: session never writes sessions/turns/evidence into the tracked worktree.
_REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Public error / config / resolved config
# --------------------------------------------------------------------------- #
class RealSessionExecutionError(Exception):
    """Fail-closed Phase E-2 boundary error carrying a stable, non-leaking code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


@dataclass(frozen=True)
class RealPersistentSessionConfig:
    """Caller-owned config for one bounded real persistent-session lifecycle.

    Every path is caller-provided. ``role_file`` points at a *resolved* role JSON
    (the committed portable role merged with the operator local overlay that
    pins ``runner.acpx_binary``); its bytes must hash to ``expected_role_digest``.
    """

    enabled: bool = False
    approval_token: str = ""
    role_file: str | None = None
    expected_role_digest: str | None = None
    sessions_dir: str | None = None
    evidence_dir: str | None = None
    work_dir: str | None = None
    runtime_session_id: str | None = None
    session_name: str | None = None
    #: Optional expected sha256 (``sha256:<hex>``) of the acpx binary bytes.
    acpx_sha256: str | None = None
    #: Test-only escape hatch: allow runtime/evidence paths inside the repo tree.
    allow_repo_paths: bool = False


@dataclass(frozen=True)
class ResolvedRealSessionConfig:
    """Validated, parsed view handed to a runtime backend.

    Holds the parsed role mapping and the resolved absolute acpx binary so a
    backend never re-reads or re-validates untrusted config.
    """

    role_mapping: dict[str, Any]
    role_file: str
    role_digest: str
    acpx_binary: str
    sessions_dir: str
    evidence_dir: str
    work_dir: str
    runtime_session_id: str
    session_name: str


# --------------------------------------------------------------------------- #
# Neutral runtime results (the only shapes a backend may surface)
# --------------------------------------------------------------------------- #
# These deliberately carry NO final message, raw prompt, tool output, or raw
# exception text — only the neutral facts the Sachima boundary is allowed to
# project into durable state.
@dataclass(frozen=True)
class _RuntimeCreateResult:
    acpx_session_id: str | None
    state: str | None


@dataclass(frozen=True)
class _RuntimeTurnResult:
    completed: bool
    status_label: str
    turn_id: str | None
    artifact_count: int


@dataclass(frozen=True)
class _RuntimeCloseResult:
    closed: bool
    state: str | None


@dataclass(frozen=True)
class _RuntimeAbortResult:
    cancelled: bool
    state: str | None = None


# --------------------------------------------------------------------------- #
# Fail-closed config validation (stdlib only; no agent_run_supervisor import)
# --------------------------------------------------------------------------- #
def validate_real_session_config(config: RealPersistentSessionConfig) -> ResolvedRealSessionConfig:
    """Validate the gate, role provenance, runner pinning, and paths.

    Fails closed with a stable :class:`RealSessionExecutionError` code on the
    first problem. Performs no import of ``agent_run_supervisor`` and starts no
    runtime — it is safe to call in CI without the external package installed.
    """

    _check_enabled_and_approved(config)
    return _validate_config_body(config)


def _validate_config_body(config: RealPersistentSessionConfig) -> ResolvedRealSessionConfig:
    """Validate role provenance, runner pinning, and paths — no approval gate."""

    role_file = _require_str(config.role_file, _ERROR_PRECONDITION, "role_file is required")
    role_path = Path(role_file)
    if not role_path.is_absolute():
        raise RealSessionExecutionError(_ERROR_PRECONDITION, "role_file must be an absolute path")
    try:
        role_bytes = role_path.read_bytes()
    except OSError:
        raise RealSessionExecutionError(
            _ERROR_PROVENANCE, "role_file is not readable"
        ) from None
    role_digest = "sha256:" + hashlib.sha256(role_bytes).hexdigest()
    expected_digest = _require_str(
        config.expected_role_digest, _ERROR_PROVENANCE, "expected_role_digest is required"
    )
    if _SHA256_RE.fullmatch(expected_digest) is None:
        raise RealSessionExecutionError(_ERROR_PROVENANCE, "expected_role_digest is malformed")
    if role_digest != expected_digest:
        raise RealSessionExecutionError(_ERROR_PROVENANCE, "role file digest does not match")

    try:
        role_mapping = json.loads(role_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise RealSessionExecutionError(_ERROR_PROVENANCE, "role file is not valid JSON") from None
    if not isinstance(role_mapping, dict):
        raise RealSessionExecutionError(_ERROR_PROVENANCE, "role file must be a JSON object")

    _check_no_forbidden_surface(role_bytes.decode("utf-8", errors="replace"))
    _check_session_strategy(role_mapping)
    acpx_binary = _check_runner_and_binary(role_mapping, config)

    runtime_session_id = _require_safe_component(
        config.runtime_session_id, "runtime_session_id"
    )
    session_name = _require_safe_component(
        config.session_name or config.runtime_session_id, "session_name"
    )
    sessions_dir = _require_offline_dir(config.sessions_dir, "sessions_dir", config.allow_repo_paths)
    evidence_dir = _require_offline_dir(config.evidence_dir, "evidence_dir", config.allow_repo_paths)
    work_dir = _require_offline_dir(config.work_dir, "work_dir", config.allow_repo_paths)

    return ResolvedRealSessionConfig(
        role_mapping=role_mapping,
        role_file=role_file,
        role_digest=role_digest,
        acpx_binary=acpx_binary,
        sessions_dir=sessions_dir,
        evidence_dir=evidence_dir,
        work_dir=work_dir,
        runtime_session_id=runtime_session_id,
        session_name=session_name,
    )


def _check_enabled_and_approved(config: RealPersistentSessionConfig) -> None:
    if config.enabled is not True:
        raise RealSessionExecutionError(
            _ERROR_DISABLED, "phase E-2 real session execution is default-off"
        )
    if config.approval_token != PHASE_E2_REAL_SESSION_APPROVAL_TOKEN:
        raise RealSessionExecutionError(
            _ERROR_APPROVAL, "exact phase E-2 real session approval token required"
        )


def _check_no_forbidden_surface(text: str) -> None:
    lowered = text.lower()
    for marker in _FORBIDDEN_SURFACE_MARKERS:
        if marker in lowered:
            raise RealSessionExecutionError(
                _ERROR_UNSAFE, "forbidden live/delivery surface marker in role"
            )


def _check_session_strategy(role_mapping: dict[str, Any]) -> None:
    session = role_mapping.get("session")
    strategy = session.get("strategy") if isinstance(session, dict) else None
    if strategy != "persistent":
        raise RealSessionExecutionError(
            _ERROR_ROLE_CAPABILITY, "role session strategy must be 'persistent'"
        )


def _check_runner_and_binary(
    role_mapping: dict[str, Any], config: RealPersistentSessionConfig
) -> str:
    runner = role_mapping.get("runner")
    if not isinstance(runner, dict):
        raise RealSessionExecutionError(_ERROR_PROVENANCE, "role runner block is missing")
    if runner.get("type") != _REQUIRED_RUNNER_TYPE:
        raise RealSessionExecutionError(_ERROR_PROVENANCE, "runner type must be 'acpx'")
    if runner.get("acpx_version") != _REQUIRED_ACPX_VERSION:
        raise RealSessionExecutionError(_ERROR_PROVENANCE, "runner acpx_version must be 0.10.0")
    if runner.get("adapter_agent") != _REQUIRED_ADAPTER:
        raise RealSessionExecutionError(_ERROR_PROVENANCE, "runner adapter_agent must be 'codex'")

    acpx_binary = runner.get("acpx_binary")
    if not isinstance(acpx_binary, str) or not acpx_binary:
        raise RealSessionExecutionError(
            _ERROR_PROVENANCE,
            "runner.acpx_binary must be a non-null absolute local path (committed null role is "
            "non-runnable until an operator overlay pins a verified local acpx)",
        )
    if not os.path.isabs(acpx_binary):
        raise RealSessionExecutionError(_ERROR_PROVENANCE, "runner.acpx_binary must be absolute")
    basename = os.path.basename(acpx_binary).lower()
    if basename in _FORBIDDEN_BINARY_BASENAMES:
        raise RealSessionExecutionError(
            _ERROR_PROVENANCE, "runner.acpx_binary basename is a launcher, not a pinned acpx"
        )
    _check_no_forbidden_surface(acpx_binary)

    binary_path = Path(acpx_binary)
    if not binary_path.is_file():
        raise RealSessionExecutionError(
            _ERROR_PROVENANCE, "runner.acpx_binary does not point at an existing file"
        )

    if config.acpx_sha256 is not None:
        expected = config.acpx_sha256
        if _SHA256_RE.fullmatch(expected) is None:
            raise RealSessionExecutionError(_ERROR_PROVENANCE, "acpx_sha256 is malformed")
        actual = "sha256:" + hashlib.sha256(binary_path.read_bytes()).hexdigest()
        if actual != expected:
            raise RealSessionExecutionError(_ERROR_PROVENANCE, "acpx binary sha256 does not match")
    return acpx_binary


def _require_str(value: Any, error_code: str, message: str) -> str:
    if not isinstance(value, str) or not value:
        raise RealSessionExecutionError(error_code, message)
    return value


def _require_safe_component(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SAFE_PATH_COMPONENT_RE.fullmatch(value) is None:
        raise RealSessionExecutionError(
            _ERROR_PRECONDITION, f"{label} must be a safe path component"
        )
    return value


def _require_offline_dir(value: Any, label: str, allow_repo_paths: bool) -> str:
    path_str = _require_str(value, _ERROR_PRECONDITION, f"{label} is required")
    path = Path(path_str)
    if not path.is_absolute():
        raise RealSessionExecutionError(_ERROR_PRECONDITION, f"{label} must be an absolute path")
    _check_no_forbidden_surface(path_str)
    if not allow_repo_paths:
        resolved = path.resolve()
        if resolved == _REPO_ROOT or resolved.is_relative_to(_REPO_ROOT):
            raise RealSessionExecutionError(
                _ERROR_PRECONDITION,
                f"{label} must live outside the tracked repo (use a caller-owned dir)",
            )
    return path_str


# --------------------------------------------------------------------------- #
# Runtime backends (the only place agent_run_supervisor is imported)
# --------------------------------------------------------------------------- #
class _AgentRunSupervisorBackend:
    """Default backend: lazily imports ``agent_run_supervisor`` and drives a
    real local ``SessionRuntime``. Only the neutral runtime-result shapes leave
    this class — never a final message, raw prompt, or tool output."""

    def _runtime_and_role(self, resolved: ResolvedRealSessionConfig) -> tuple[Any, Any]:
        from agent_run_supervisor.role import load_role  # lazy: not needed in CI
        from agent_run_supervisor.session_runtime import SessionRuntime

        role = load_role(resolved.role_mapping)
        runtime = SessionRuntime(sessions_dir=Path(resolved.sessions_dir))
        return runtime, role

    def create(self, resolved: ResolvedRealSessionConfig) -> _RuntimeCreateResult:
        runtime, role = self._runtime_and_role(resolved)
        outcome = runtime.create_session(
            role=role,
            session_id=resolved.runtime_session_id,
            session_name=resolved.session_name,
            cwd=resolved.work_dir,
        )
        return _RuntimeCreateResult(
            acpx_session_id=outcome.record.acpx_session_id, state=outcome.record.state
        )

    def send(self, resolved: ResolvedRealSessionConfig, prompt: str) -> _RuntimeTurnResult:
        runtime, role = self._runtime_and_role(resolved)
        outcome = runtime.send(
            role=role,
            session_id=resolved.runtime_session_id,
            prompt=prompt,
            cwd=resolved.work_dir,
        )
        status_value = getattr(outcome.status, "value", outcome.status)
        completed = status_value == "completed"
        artifact_count = 0
        try:
            artifact_count = sum(1 for p in Path(outcome.turn_dir).iterdir() if p.is_file())
        except OSError:
            artifact_count = 0
        return _RuntimeTurnResult(
            completed=completed,
            status_label=str(status_value),
            turn_id=outcome.turn_id,
            artifact_count=artifact_count,
        )

    def close(self, resolved: ResolvedRealSessionConfig) -> _RuntimeCloseResult:
        runtime, role = self._runtime_and_role(resolved)
        outcome = runtime.close(
            role=role, session_id=resolved.runtime_session_id, cwd=resolved.work_dir
        )
        return _RuntimeCloseResult(
            closed=outcome.record.state == "closed", state=outcome.record.state
        )

    def best_effort_close(self, resolved: ResolvedRealSessionConfig) -> None:
        # Graceful, swallowing close used as a leak guard. Never aborts/kills,
        # never raises: a cleanup failure must not mask the original error.
        try:
            self.close(resolved)
        except Exception:
            pass

    def abort(self, resolved: ResolvedRealSessionConfig) -> _RuntimeAbortResult:
        runtime, role = self._runtime_and_role(resolved)
        outcome = runtime.abort(
            role=role,
            session_id=resolved.runtime_session_id,
            cwd=resolved.work_dir,
        )
        cancelled = getattr(outcome, "cancelled", False) is True
        return _RuntimeAbortResult(
            cancelled=cancelled,
            state="cancelled" if cancelled else None,
        )


def _resolve_backend(backend: Any | None) -> Any:
    return backend if backend is not None else _AgentRunSupervisorBackend()


# --------------------------------------------------------------------------- #
# Sanitized projection helpers (Sachima-owned boundary)
# --------------------------------------------------------------------------- #
def _digest_hex(parts: list[str]) -> str:
    canonical = json.dumps(parts, separators=(",", ":"), sort_keys=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _session_binding(acpx_session_id: str | None, runtime_session_id: str) -> str:
    # An opaque, deterministic binding derived from the runtime/acpx session id.
    # The raw acpx session id never leaves this function.
    seed = f"{runtime_session_id}\x1f{acpx_session_id or ''}"
    return "sbind_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def _evidence_ref(kind: str, resolved: ResolvedRealSessionConfig) -> str:
    return "real_session_" + kind + "_evidence_" + _digest_hex(
        [kind, resolved.runtime_session_id, resolved.role_digest]
    )[:12]


def _evidence_digest(parts: list[str]) -> str:
    return "sha256:" + _digest_hex(parts)


def _safe_count(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _failed_outcome() -> SessionWorkOutcome:
    return SessionWorkOutcome(
        ok=False, supervisor_status=None, error_code=_ERROR_SUPERVISOR_FAILED
    )


# --------------------------------------------------------------------------- #
# Public work callables (compatible with the Phase E state machine)
# --------------------------------------------------------------------------- #
def open_real_persistent_session(
    request: SessionCreateRequest,
    config: RealPersistentSessionConfig,
    *,
    backend: Any | None = None,
) -> SessionWorkOutcome:
    """Open one real local persistent session and return a sanitized outcome.

    Gate/config problems fail closed (raise). A runtime failure is mapped to a
    sanitized ``ok=False`` outcome after a best-effort close, so a session that
    acpx may have created before the failure is not leaked.
    """

    resolved = validate_real_session_config(config)
    backend = _resolve_backend(backend)
    try:
        result = backend.create(resolved)
    except Exception:
        try:
            backend.best_effort_close(resolved)
        except Exception:
            pass
        return _failed_outcome()

    binding = _session_binding(
        getattr(result, "acpx_session_id", None), resolved.runtime_session_id
    )
    return SessionWorkOutcome(
        ok=True,
        supervisor_status=_STATUS_OPEN,
        session_binding=binding,
        evidence_ref=_evidence_ref("create", resolved),
        evidence_digest=_evidence_digest([_STATUS_OPEN, resolved.runtime_session_id, binding]),
        artifact_ref_count=0,
    )


def run_real_persistent_session_turn(
    request: SessionSendRequest,
    config: RealPersistentSessionConfig,
    prompt: str | Callable[[SessionSendRequest], str],
    *,
    backend: Any | None = None,
) -> SessionWorkOutcome:
    """Run exactly one real read-only turn and return a sanitized outcome.

    The prompt is handed to the runtime (which persists only redacted turn
    artifacts on disk) but is never returned or stored in durable Sachima state.
    The final message is never read here.
    """

    resolved = validate_real_session_config(config)
    prompt_text = _resolve_prompt(prompt, request)
    backend = _resolve_backend(backend)
    try:
        result = backend.send(resolved, prompt_text)
    except Exception:
        return _failed_outcome()

    if not getattr(result, "completed", False):
        return _failed_outcome()
    artifact_count = _safe_count(getattr(result, "artifact_count", 0))
    return SessionWorkOutcome(
        ok=True,
        supervisor_status=_STATUS_TURN,
        evidence_ref=_evidence_ref("turn", resolved),
        evidence_digest=_evidence_digest(
            [_STATUS_TURN, resolved.runtime_session_id, str(artifact_count)]
        ),
        artifact_ref_count=artifact_count,
    )


def close_real_persistent_session(
    request: SessionCloseRequest,
    config: RealPersistentSessionConfig,
    *,
    backend: Any | None = None,
) -> SessionWorkOutcome:
    """Gracefully close the real local persistent session (sanitized outcome)."""

    resolved = validate_real_session_config(config)
    backend = _resolve_backend(backend)
    try:
        result = backend.close(resolved)
    except Exception:
        return _failed_outcome()

    if not getattr(result, "closed", False):
        return _failed_outcome()
    return SessionWorkOutcome(
        ok=True,
        supervisor_status=_STATUS_CLOSED,
        evidence_ref=_evidence_ref("close", resolved),
        evidence_digest=_evidence_digest([_STATUS_CLOSED, resolved.runtime_session_id]),
        artifact_ref_count=0,
    )


def best_effort_close_real_session(
    config: RealPersistentSessionConfig, *, backend: Any | None = None
) -> None:
    """Best-effort leak guard: gracefully close a real session, swallowing errors.

    The gate is still enforced (a disabled/unapproved config fails closed before
    any runtime touch), but once past the gate a close failure never raises — the
    caller uses this in a ``finally`` so it must not mask the original failure.
    """

    resolved = validate_real_session_config(config)
    backend = _resolve_backend(backend)
    try:
        backend.best_effort_close(resolved)
    except Exception:
        pass


def _check_interrupt_request_gate(request: SessionInterruptRequest) -> None:
    """Validate the interrupt request's own gate before any real abort touch."""

    if request.enabled is not True:
        raise RealSessionExecutionError(
            _ERROR_DISABLED, "session interrupt request is disabled"
        )
    if request.approval_token != SESSION_INTERRUPT_API_APPROVAL_TOKEN:
        raise RealSessionExecutionError(
            _ERROR_APPROVAL, "session interrupt request approval token mismatch"
        )
    if request.operator_gate is not True:
        raise RealSessionExecutionError(
            _ERROR_PRECONDITION, "session interrupt request requires operator gate"
        )


def execute_real_cancellation(
    request: SessionInterruptRequest,
    config: RealPersistentSessionConfig,
    *,
    backend: Any | None = None,
) -> SessionInterruptOutcome:
    """WP3b public cancellation entrypoint: validate gates, then fail closed.

    Real backend abort is intentionally not reachable from this public function.
    It is invoked only by the proven callback registered by
    ``bind_real_cancellation`` and selected by ``apply_session_interrupt`` after
    durable ``cancel_requested`` + active in-flight-turn checks.
    """

    _check_interrupt_request_gate(request)
    if config.approval_token != PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN:
        raise RealSessionExecutionError(
            _ERROR_CANCEL_NOT_APPROVED,
            "WP3b cancel execution requires the exact cancel approval token",
        )
    if config.enabled is not True:
        raise RealSessionExecutionError(
            _ERROR_DISABLED, "phase E-2 cancel execution is default-off"
        )
    _validate_config_body(config)
    _ = backend
    raise RealSessionExecutionError(
        _ERROR_PRECONDITION,
        "WP3b cancellation execution requires lifecycle state-machine in-flight turn proof",
    )


# --------------------------------------------------------------------------- #
# Binders: produce single-arg callables for the state machine
# --------------------------------------------------------------------------- #
def _called_from_lifecycle_apply_session_interrupt(expected_apply_interrupt: object) -> bool:
    frame = inspect.currentframe()
    method_frame = frame.f_back if frame is not None else None
    safe_call_frame = method_frame.f_back if method_frame is not None else None
    apply_frame = safe_call_frame.f_back if safe_call_frame is not None else None
    return bool(
        safe_call_frame is not None
        and safe_call_frame.f_code is _lifecycle_safe_interrupt_call.__code__
        and apply_frame is not None
        and apply_frame.f_code is _lifecycle_apply_session_interrupt.__code__
        and apply_frame.f_locals.get("apply_interrupt") is expected_apply_interrupt
    )


class _BoundRealCancellation:
    """Callable whose real-abort path only opens from apply_session_interrupt."""

    __slots__ = ("_backend", "_config")

    def __init__(self, config: RealPersistentSessionConfig, backend: Any | None) -> None:
        self._config = config
        self._backend = backend

    def __call__(self, request: SessionInterruptRequest) -> SessionInterruptOutcome:
        return execute_real_cancellation(request, self._config, backend=self._backend)

    def _apply_after_lifecycle_validation(
        self, request: SessionInterruptRequest
    ) -> SessionInterruptOutcome:
        if not _called_from_lifecycle_apply_session_interrupt(self):
            raise RealSessionExecutionError(
                _ERROR_PRECONDITION,
                "WP3b cancellation execution requires lifecycle state-machine in-flight turn proof",
            )
        _check_interrupt_request_gate(request)
        if self._config.approval_token != PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN:
            raise RealSessionExecutionError(
                _ERROR_CANCEL_NOT_APPROVED,
                "WP3b cancel execution requires the exact cancel approval token",
            )
        if self._config.enabled is not True:
            raise RealSessionExecutionError(
                _ERROR_DISABLED, "phase E-2 cancel execution is default-off"
            )

        resolved = _validate_config_body(self._config)
        resolved_backend = _resolve_backend(self._backend)
        try:
            result = resolved_backend.abort(resolved)
        except Exception:
            return SessionInterruptOutcome(
                interrupted=True,
                cleanup_verified=False,
                ambiguous=True,
                error_code=_ERROR_CANCEL_AMBIGUOUS,
            )

        if getattr(result, "cancelled", False):
            return SessionInterruptOutcome(
                interrupted=True,
                cleanup_verified=True,
                supervisor_status=_STATUS_CANCELLED,
                evidence_ref=_evidence_ref("cancel", resolved),
                evidence_digest=_evidence_digest([_STATUS_CANCELLED, resolved.runtime_session_id]),
            )
        return SessionInterruptOutcome(
            interrupted=False,
            cleanup_verified=False,
            supervisor_status="cancel_not_confirmed",
        )


def bind_open_session(
    config: RealPersistentSessionConfig, *, backend: Any | None = None
) -> Callable[[SessionCreateRequest], SessionWorkOutcome]:
    def _work(request: SessionCreateRequest) -> SessionWorkOutcome:
        return open_real_persistent_session(request, config, backend=backend)

    return _work


def bind_run_turn(
    config: RealPersistentSessionConfig,
    prompt: str | Callable[[SessionSendRequest], str],
    *,
    backend: Any | None = None,
) -> Callable[[SessionSendRequest], SessionWorkOutcome]:
    def _work(request: SessionSendRequest) -> SessionWorkOutcome:
        return run_real_persistent_session_turn(request, config, prompt, backend=backend)

    return _work


def bind_close_session(
    config: RealPersistentSessionConfig, *, backend: Any | None = None
) -> Callable[[SessionCloseRequest], SessionWorkOutcome]:
    def _work(request: SessionCloseRequest) -> SessionWorkOutcome:
        return close_real_persistent_session(request, config, backend=backend)

    return _work


def bind_real_cancellation(
    config: RealPersistentSessionConfig, *, backend: Any | None = None
) -> Callable[[SessionInterruptRequest], SessionInterruptOutcome]:
    """Return a single-arg callable wiring WP3b cancellation into the state machine."""

    return _BoundRealCancellation(config, backend)


def _resolve_prompt(
    prompt: str | Callable[[SessionSendRequest], str], request: SessionSendRequest
) -> str:
    resolved = prompt(request) if callable(prompt) else prompt
    if not isinstance(resolved, str) or not resolved.strip():
        raise RealSessionExecutionError(
            _ERROR_PRECONDITION, "turn prompt must resolve to a non-empty string"
        )
    return resolved
