"""Sachima x agent-run-supervisor local/offline integration seam.

This is a **default-off, local/offline, caller-owned** seam. A local
Sachima/FlowWeaver/Hermes controller (the caller — explicitly *not* the
Hermes Gateway) can use it to:

  * build an ``agent_run_supervisor.caller.CallerInvocationSpec`` from a
    sanitized request assembled out of claim-check refs,
  * call ``invoke_caller`` (starting with dry-run / config-preview),
  * map the returned ``CallerResult`` into a caller-owned offline view model,
  * and write a sanitized local JSON evidence file.

Boundaries enforced here (see the design packet
``docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md``):

  * Invocation is default-off and requires the exact implementation approval
    token; a missing/false/mismatched gate fails closed with a stable error
    code, before any optional dependency is imported or the supervisor called.
  * Only a fixed allowlist of modes is accepted (no cancel/rollback).
  * The supervisor library is imported lazily inside the invocation path only,
    so importing this module never requires ``agent_run_supervisor``. Tests
    inject fakes instead.
  * ``business_verdict`` from the library always stays ``None``; only a
    caller-supplied ``caller_verdict`` may travel in the offline view model.
  * Raw prompt/context, platform-private ids, card JSON, media paths, tool
    output, credentials, and raw exception text never enter the returned view
    model or the evidence file.

There is no network, no send API, no IM/Feishu delivery, and no Gateway
involvement in this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# --------------------------------------------------------------------------- #
# Approval token + allowlists
# --------------------------------------------------------------------------- #
IMPLEMENTATION_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_local_offline_integration_"
    "implementation_no_live_no_gateway_no_real_delivery"
)

# Mode allowlist. Cancellation and rollback are deliberately absent — they are
# future implementation concerns per the design packet.
SUPPORTED_MODES: frozenset[str] = frozenset(
    {
        "exec_dry_run",
        "exec",
        "session_create",
        "session_send",
        "session_status",
        "session_close",
    }
)

# Caller-owned lifecycle phase per mode, used for the sanitized view model.
_MODE_PHASES: dict[str, str] = {
    "exec_dry_run": "dry_run",
    "exec": "exec",
    "session_create": "session",
    "session_send": "session",
    "session_status": "session",
    "session_close": "session",
}

# Platform-private / credential metadata keys that must never cross the generic
# boundary. Matched as case-insensitive substrings so ``x_chat_id`` is caught.
FORBIDDEN_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "chat_id",
        "user_id",
        "open_id",
        "union_id",
        "message_id",
        "card_json",
        "media_path",
        "media_bytes",
        "token",
        "secret",
        "password",
        "passwd",
        "authorization",
        "cookie",
        "signature",
        "credential",
        "api_key",
        "apikey",
    }
)

# Substrings that flag obvious unsafe material inside scanned string values
# (prompt/context/metadata values/refs/labels). Conservative + fail-closed.
_UNSAFE_VALUE_MARKERS: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "passwd",
    "authorization",
    "cookie",
    "bearer ",
    "api_key",
    "apikey",
    "private_key",
    "-----begin",
    "card_json",
    '"type":"card"',
    '"type": "card"',
    "media:",
    "/tmp/",
    ".png",
    ".jpg",
    ".jpeg",
    ".mp4",
    ".mov",
)

# Platform-id-shaped tokens (e.g. Feishu ``oc_``/``ou_``/``om_`` ids).
_PLATFORM_ID_PREFIXES: tuple[str, ...] = ("oc_", "ou_", "om_")
_PLATFORM_ID_MIN_TAIL = 6

_VIEW_MODEL_TYPE = "sachima.supervisor.local_offline_view_model.v1"
_STABLE_CODE_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")


# --------------------------------------------------------------------------- #
# Public dataclasses + error
# --------------------------------------------------------------------------- #
class LocalOfflineSupervisorError(Exception):
    """Fail-closed boundary error carrying a stable, non-leaking error code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


@dataclass(frozen=True)
class LocalOfflineSupervisorRequest:
    """Caller-owned, sanitized invocation request.

    ``prompt``/``context`` are assembled by the caller from claim-check refs and
    sanitized text; they are handed to the supervisor spec but never persisted
    into the returned view model or the evidence file.
    """

    mode: str
    correlation_label: str
    role: Any | None = None
    role_file: str | None = None
    enabled: bool = False
    approval_token: str = ""
    prompt: str | None = None
    context: str | None = None
    claim_check_refs: tuple[str, ...] = ()
    cwd: str | None = None
    runs_dir: str | None = None
    sessions_dir: str | None = None
    session_id: str | None = None
    session_name: str | None = None
    allowed_roots: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    caller_verdict: str | None = None
    evidence_dir: str | None = None


@dataclass(frozen=True)
class LocalOfflineSupervisorOutcome:
    """Caller-owned offline outcome. ``business_verdict`` is always ``None``."""

    status: str
    mode: str
    phase: str
    supervisor_status: str | None
    correlation_label: str
    error_code: str | None
    business_verdict: None
    caller_verdict: str | None
    artifact_ref_count: int
    evidence_ref: str
    evidence_digest: str
    evidence_path: str | None
    view_model: dict[str, Any]


# --------------------------------------------------------------------------- #
# Boundary validation
# --------------------------------------------------------------------------- #
def _check_enabled_and_approved(request: LocalOfflineSupervisorRequest) -> None:
    if not request.enabled:
        raise LocalOfflineSupervisorError(
            "supervisor_disabled", "local/offline supervisor seam is default-off"
        )
    if request.approval_token != IMPLEMENTATION_APPROVAL_TOKEN:
        raise LocalOfflineSupervisorError(
            "approval_token_mismatch", "exact implementation approval token required"
        )


def _validate_mode(mode: str) -> None:
    if mode not in SUPPORTED_MODES:
        raise LocalOfflineSupervisorError(
            "unsupported_mode", "mode is not in the local/offline allowlist"
        )


def _validate_role_source(request: LocalOfflineSupervisorRequest) -> None:
    role_source_count = int(request.role is not None) + int(request.role_file is not None)
    if role_source_count != 1:
        raise LocalOfflineSupervisorError(
            "role_source_required", "exactly one role source is required"
        )


def _scanned_values(request: LocalOfflineSupervisorRequest) -> Iterator[Any]:
    """Yield caller-supplied values that must be screened for unsafe material.

    Filesystem fields (``cwd``/``allowed_roots``/``runs_dir``/``sessions_dir``) are
    intentionally excluded: they are legitimate local paths needed to run, and
    they never enter the view model or evidence.
    """

    yield request.role if isinstance(request.role, str) else None
    yield request.role_file
    yield request.correlation_label
    yield request.prompt
    yield request.context
    yield request.caller_verdict
    yield from request.claim_check_refs
    yield from request.metadata.values()


def _value_is_unsafe(value: Any) -> bool:
    if value is None:
        return False
    if not isinstance(value, str):
        # Non-string structured material (e.g. a card dict) is itself unsafe.
        return True
    lowered = value.lower()
    if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
        return True
    for prefix in _PLATFORM_ID_PREFIXES:
        index = lowered.find(prefix)
        while index != -1:
            tail = value[index + len(prefix) : index + len(prefix) + _PLATFORM_ID_MIN_TAIL]
            if len(tail) >= _PLATFORM_ID_MIN_TAIL and tail.replace("_", "").isalnum():
                return True
            index = lowered.find(prefix, index + 1)
    return False


def _validate_boundary(request: LocalOfflineSupervisorRequest) -> None:
    for key in request.metadata:
        normalized = str(key).strip().lower()
        if any(forbidden in normalized for forbidden in FORBIDDEN_METADATA_KEYS):
            raise LocalOfflineSupervisorError(
                "forbidden_metadata_key", "platform-private metadata key rejected"
            )
    for value in _scanned_values(request):
        if _value_is_unsafe(value):
            raise LocalOfflineSupervisorError(
                "unsafe_material", "obvious unsafe material rejected at boundary"
            )


# --------------------------------------------------------------------------- #
# Lazy optional dependency resolution (only inside the invocation path)
# --------------------------------------------------------------------------- #
def _resolve_spec_factory(spec_factory: Callable[..., Any] | None) -> Callable[..., Any]:
    if spec_factory is not None:
        return spec_factory
    try:
        from agent_run_supervisor.caller import CallerInvocationSpec
    except Exception:
        raise LocalOfflineSupervisorError(
            "supervisor_library_unavailable",
            "agent_run_supervisor is not installed",
        ) from None
    return CallerInvocationSpec


def _resolve_invoke_caller(invoke_caller: Callable[[Any], Any] | None) -> Callable[[Any], Any]:
    if invoke_caller is not None:
        return invoke_caller
    try:
        from agent_run_supervisor.caller import invoke_caller as resolved_invoke_caller
    except Exception:
        raise LocalOfflineSupervisorError(
            "supervisor_library_unavailable",
            "agent_run_supervisor is not installed",
        ) from None
    return resolved_invoke_caller


# --------------------------------------------------------------------------- #
# Spec building
# --------------------------------------------------------------------------- #
def build_caller_invocation_spec(
    request: LocalOfflineSupervisorRequest,
    *,
    spec_factory: Callable[..., Any] | None = None,
) -> Any:
    """Validate the request and build a ``CallerInvocationSpec``.

    The default-off gate, mode allowlist, and boundary checks all run *before*
    any optional dependency is resolved, so a rejected request never imports or
    touches the supervisor library.
    """

    _check_enabled_and_approved(request)
    _validate_mode(request.mode)
    _validate_role_source(request)
    _validate_boundary(request)

    factory = _resolve_spec_factory(spec_factory)
    fields: dict[str, Any] = {
        "mode": request.mode,
        "role": request.role,
        "role_file": request.role_file,
        "prompt": request.prompt,
        "context": request.context,
        "cwd": request.cwd,
        "runs_dir": request.runs_dir,
        "sessions_dir": request.sessions_dir,
        "session_id": request.session_id,
        "session_name": request.session_name,
    }
    try:
        return factory(**fields)
    except LocalOfflineSupervisorError:
        raise
    except Exception:
        raise LocalOfflineSupervisorError(
            "spec_build_failed", "failed to build caller invocation spec"
        ) from None


# --------------------------------------------------------------------------- #
# CallerResult -> sanitized offline view model
# --------------------------------------------------------------------------- #
def _sanitize_supervisor_status(status: str | None) -> str | None:
    if status is None:
        return None
    if _value_is_unsafe(status) or _STABLE_CODE_RE.fullmatch(status) is None:
        return "invalid_supervisor_status"
    return status


def _sanitize_payload_code(value: str | None, *, fallback: str) -> str | None:
    if value is None:
        return None
    if _value_is_unsafe(value) or _STABLE_CODE_RE.fullmatch(value) is None:
        return fallback
    return value


def _read_supervisor_status(caller_result: Any) -> str | None:
    status = getattr(caller_result, "supervisor_status", None)
    if status is None:
        status = getattr(caller_result, "status", None)
    if status is None:
        result = getattr(caller_result, "result", None)
        if isinstance(result, Mapping):
            status = result.get("status")
    raw_status = None if status is None else str(status)
    return _sanitize_supervisor_status(raw_status)


def _read_artifact_ref_count(caller_result: Any) -> int:
    refs = getattr(caller_result, "artifact_refs", None)
    if refs is not None:
        try:
            return len(refs)
        except TypeError:
            return 0
    return sum(
        1
        for value in (
            getattr(caller_result, "artifact_dir", None),
            getattr(caller_result, "run_dir", None),
            getattr(caller_result, "session_dir", None),
        )
        if value is not None
    )


def _digest(core: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        core, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_offline_view_model(
    request: LocalOfflineSupervisorRequest,
    caller_result: Any,
    *,
    status: str = "observed",
    error_code: str | None = None,
) -> dict[str, Any]:
    """Map a ``CallerResult`` into a sanitized, caller-owned offline view model.

    The returned dict carries only sanitized fields. ``business_verdict`` is
    forced to ``None`` (the library never owns the verdict and its value is
    never propagated); the caller's own ``caller_verdict`` travels separately.
    No raw prompt/context, platform ids, card/media material, tool output, or
    exception text is included.
    """

    _validate_mode(request.mode)
    _validate_role_source(request)
    _validate_boundary(request)

    safe_status = _sanitize_payload_code(status, fallback="error")
    safe_error_code = _sanitize_payload_code(error_code, fallback="invalid_error_code")
    if safe_status != status and safe_error_code is None:
        safe_error_code = "invalid_status_code"

    supervisor_status = None if safe_error_code is not None else _read_supervisor_status(caller_result)
    artifact_ref_count = 0 if caller_result is None else _read_artifact_ref_count(caller_result)

    core: dict[str, Any] = {
        "type": _VIEW_MODEL_TYPE,
        "mode": request.mode,
        "phase": _MODE_PHASES.get(request.mode, "unknown"),
        "status": safe_status,
        "supervisor_status": supervisor_status,
        "correlation_label": request.correlation_label,
        "error_code": safe_error_code,
        "business_verdict": None,
        "caller_verdict": request.caller_verdict,
        "artifact_ref_count": artifact_ref_count,
    }
    digest = _digest(core)
    evidence_ref = "local_offline_supervisor_evidence_" + digest.split(":", 1)[1][:16]
    return {**core, "evidence_ref": evidence_ref, "evidence_digest": digest}


def _write_evidence(evidence_dir: str, evidence_ref: str, payload: Mapping[str, Any]) -> str:
    directory = Path(evidence_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{evidence_ref}.json"
    path.write_text(
        json.dumps(dict(payload), sort_keys=True, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)


def _outcome_from_payload(
    payload: Mapping[str, Any], evidence_path: str | None
) -> LocalOfflineSupervisorOutcome:
    return LocalOfflineSupervisorOutcome(
        status=payload["status"],
        mode=payload["mode"],
        phase=payload["phase"],
        supervisor_status=payload["supervisor_status"],
        correlation_label=payload["correlation_label"],
        error_code=payload["error_code"],
        business_verdict=None,
        caller_verdict=payload["caller_verdict"],
        artifact_ref_count=payload["artifact_ref_count"],
        evidence_ref=payload["evidence_ref"],
        evidence_digest=payload["evidence_digest"],
        evidence_path=evidence_path,
        view_model=dict(payload),
    )


# --------------------------------------------------------------------------- #
# Top-level invocation
# --------------------------------------------------------------------------- #
def invoke_local_offline_supervisor(
    request: LocalOfflineSupervisorRequest,
    *,
    spec_factory: Callable[..., Any] | None = None,
    invoke_caller: Callable[[Any], Any] | None = None,
) -> LocalOfflineSupervisorOutcome:
    """Run the default-off local/offline supervisor seam end to end.

    Gate/boundary failures fail closed by raising
    :class:`LocalOfflineSupervisorError`. A supervisor invocation error is
    caught (no-throw) and mapped to a stable error code in the outcome, with no
    raw exception text leaking into the view model or evidence.
    """

    spec = build_caller_invocation_spec(request, spec_factory=spec_factory)
    caller = _resolve_invoke_caller(invoke_caller)

    try:
        caller_result = caller(spec)
    except LocalOfflineSupervisorError:
        raise
    except Exception:
        payload = build_offline_view_model(
            request, None, status="error", error_code="supervisor_invocation_failed"
        )
    else:
        payload = build_offline_view_model(
            request, caller_result, status="observed", error_code=None
        )

    evidence_path: str | None = None
    if request.evidence_dir is not None:
        evidence_path = _write_evidence(request.evidence_dir, payload["evidence_ref"], payload)

    return _outcome_from_payload(payload, evidence_path)
