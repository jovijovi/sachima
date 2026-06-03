"""Sachima supervised local Activity wrapper around ``sachima_supervisor``.

This is the **first implementation slice** of the supervised local Activity
designed in
``docs/plans/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-design.md``.
It is a caller-owned Sachima/FlowWeaver controller layer on top of the
already-merged, default-off ``sachima_supervisor.local_offline`` seam.

Boundaries enforced here (local/offline only):

  * The Activity is default-off and requires the *exact* Activity
    implementation approval token; a disabled or mismatched gate fails closed
    with a stable error code before any work happens.
  * The first slice accepts only ``exec_dry_run`` and only an *injected*
    supervisor callable. It never default-calls the seam's runtime entrypoint;
    real local execution, sessions, and the seam's own invocation path are out
    of scope for this slice.
  * Role keys resolve through a fixed local allowlist; arbitrary, traversal, or
    platform-shaped role values fail closed.
  * Public claim-check / workspace refs are screened for platform-private,
    secret-shaped, card, or media material at the Activity boundary.
  * Durable state and results carry only sanitized stable codes, caller-owned
    refs, counts, and digests. Raw prompt/context, platform ids, card material,
    media paths, tool output, raw evidence paths, and raw exception text never
    enter durable state, results, or view-model refs.

There is no network, no send API, no IM delivery, and no Gateway involvement in
this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

from sachima_supervisor.local_offline import (
    IMPLEMENTATION_APPROVAL_TOKEN as LOCAL_OFFLINE_APPROVAL_TOKEN,
    LocalOfflineSupervisorOutcome,
    LocalOfflineSupervisorRequest,
    # Reuse the seam's single source of truth for unsafe-material detection so
    # the Activity input boundary can never drift from the seam boundary.
    _value_is_unsafe as _value_is_unsafe,
)

# --------------------------------------------------------------------------- #
# Approval token + allowlists
# --------------------------------------------------------------------------- #
#: Exact approval token required to enable this Activity slice.
ACTIVITY_IMPLEMENTATION_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_supervised_local_activity_"
    "implementation_no_live_no_gateway_no_real_delivery"
)

#: First-slice mode allowlist. Only dry-run is implemented; ``exec``, session,
#: and cancel modes remain design-only until a separately approved slice.
FIRST_SLICE_MODES: frozenset[str] = frozenset({"exec_dry_run"})

#: Caller-owned role allowlist mapping a Sachima intent role key to a sanitized
#: role-file ref. Raw role JSON is never accepted or stored; only this fixed
#: mapping resolves a role. (See the design's Role and Permission Mapping.)
ROLE_KEY_ALLOWLIST: Mapping[str, str] = {
    "sachima.docs_planner": "roles/sachima/docs-planner.json",
    "sachima.coding_worker": "roles/sachima/coding-worker.json",
    "sachima.primary_reviewer": "roles/sachima/primary-reviewer.json",
    "sachima.verifier": "roles/sachima/verifier.json",
    "sachima.session_worker": "roles/sachima/session-worker.json",
}

#: Caller-owned lifecycle phase per supported mode.
_MODE_PHASES: Mapping[str, str] = {"exec_dry_run": "dry_run"}

_STATE_TYPE = "sachima.supervisor.supervised_local_activity_state.v1"
_VIEW_MODEL_REF_PREFIX = "supervised_local_activity_view_"
_STABLE_CODE_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")
_EVIDENCE_REF_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,127}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


# --------------------------------------------------------------------------- #
# Public request / result / error / store
# --------------------------------------------------------------------------- #
class SupervisedLocalActivityError(Exception):
    """Fail-closed Activity boundary error carrying a stable error code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


@dataclass(frozen=True)
class SupervisedLocalActivityRequest:
    """Caller-owned supervised local Activity request.

    Inputs are claim-check refs and caller-owned ids, never raw prompt/context,
    platform ids, or arbitrary paths. ``enabled`` defaults to ``False`` and
    ``approval_token`` to ``""`` so the Activity is default-off by construction.
    """

    activity_id: str
    transaction_ref: str
    operation_ref: str
    idempotency_key: str
    mode: str
    role_key: str
    approval_token: str = ""
    enabled: bool = False
    prompt_ref: str | None = None
    context_refs: tuple[str, ...] = ()
    cwd_ref: str | None = None
    allowed_roots_ref: str | None = None
    session_ref: str | None = None
    dry_run_first: bool = True


class SupervisedLocalActivityResult:
    """Sanitized, queryable view over durable Activity state.

    The result is a thin read-only wrapper around the stored durable-state dict,
    so :meth:`to_durable_state` round-trips exactly and replays/queries return
    state identical to the original run.
    """

    def __init__(self, state: Mapping[str, Any]) -> None:
        self._state: dict[str, Any] = dict(state)

    @property
    def ok(self) -> bool:
        return self._state["ok"]

    @property
    def status(self) -> str:
        return self._state["status"]

    @property
    def supervisor_status(self) -> str | None:
        return self._state["supervisor_status"]

    @property
    def mode(self) -> str:
        return self._state["mode"]

    @property
    def phase(self) -> str:
        return self._state["phase"]

    @property
    def activity_id(self) -> str:
        return self._state["activity_id"]

    @property
    def transaction_ref(self) -> str:
        return self._state["transaction_ref"]

    @property
    def operation_ref(self) -> str:
        return self._state["operation_ref"]

    @property
    def session_ref(self) -> str | None:
        return self._state["session_ref"]

    @property
    def role_key(self) -> str:
        return self._state["role_key"]

    @property
    def artifact_ref_count(self) -> int:
        return self._state["artifact_ref_count"]

    @property
    def evidence_ref(self) -> str | None:
        return self._state["evidence_ref"]

    @property
    def evidence_digest(self) -> str | None:
        return self._state["evidence_digest"]

    @property
    def caller_verdict(self) -> str | None:
        return self._state["caller_verdict"]

    @property
    def error_code(self) -> str | None:
        return self._state["error_code"]

    @property
    def retryable(self) -> bool:
        return self._state["retryable"]

    @property
    def view_model_ref(self) -> str:
        return self._state["view_model_ref"]

    def to_durable_state(self) -> dict[str, Any]:
        """Return a copy of the sanitized durable state."""

        return dict(self._state)


@dataclass
class ActivityStateStore:
    """In-memory durable-state store keyed by activity id and idempotency key.

    Only sanitized durable state is held. The idempotency index also records a
    request fingerprint so a repeat key with an incompatible request fails
    closed instead of silently replaying a different run.
    """

    _by_activity: dict[str, dict[str, Any]] = field(default_factory=dict)
    _by_idempotency: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)

    def get_by_activity(self, activity_id: str) -> dict[str, Any] | None:
        return self._by_activity.get(activity_id)

    def get_idempotent(self, idempotency_key: str) -> tuple[str, dict[str, Any]] | None:
        return self._by_idempotency.get(idempotency_key)

    def put(
        self,
        *,
        activity_id: str,
        idempotency_key: str,
        fingerprint: str,
        state: dict[str, Any],
    ) -> None:
        self._by_activity[activity_id] = state
        self._by_idempotency[idempotency_key] = (fingerprint, state)


# --------------------------------------------------------------------------- #
# Boundary validation
# --------------------------------------------------------------------------- #
def _check_enabled_and_approved(request: SupervisedLocalActivityRequest) -> None:
    if not request.enabled:
        raise SupervisedLocalActivityError(
            "activity_disabled", "supervised local Activity is default-off"
        )
    if request.approval_token != ACTIVITY_IMPLEMENTATION_APPROVAL_TOKEN:
        raise SupervisedLocalActivityError(
            "activity_approval_mismatch", "exact Activity approval token required"
        )


def _check_mode(request: SupervisedLocalActivityRequest) -> None:
    if request.mode not in FIRST_SLICE_MODES:
        raise SupervisedLocalActivityError(
            "activity_unsupported_mode", "first slice accepts exec_dry_run only"
        )
    if not request.dry_run_first:
        raise SupervisedLocalActivityError(
            "activity_dry_run_required", "first slice must run the dry-run path first"
        )


def _check_material(request: SupervisedLocalActivityRequest) -> None:
    """Reject platform-private, secret-shaped, card, or media material.

    Role keys are validated separately through the allowlist; everything else
    that is caller-supplied and travels into durable state is screened here.
    """

    scanned: list[Any] = [
        request.activity_id,
        request.transaction_ref,
        request.operation_ref,
        request.idempotency_key,
        request.prompt_ref,
        request.cwd_ref,
        request.allowed_roots_ref,
        request.session_ref,
    ]
    scanned.extend(request.context_refs)
    for value in scanned:
        if _value_is_unsafe(value):
            raise SupervisedLocalActivityError(
                "activity_unsafe_material", "unsafe material rejected at Activity boundary"
            )


def _resolve_role_file(role_key: str) -> str:
    role_file = ROLE_KEY_ALLOWLIST.get(role_key)
    if role_file is None:
        raise SupervisedLocalActivityError(
            "activity_unknown_role", "role key is not in the Activity allowlist"
        )
    return role_file


# --------------------------------------------------------------------------- #
# Durable-state construction
# --------------------------------------------------------------------------- #
def _digest_hex(core: Mapping[str, Any]) -> str:
    canonical = json.dumps(core, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_durable_state(
    request: SupervisedLocalActivityRequest,
    *,
    role_key: str,
    ok: bool,
    status: str,
    supervisor_status: str | None,
    phase: str,
    artifact_ref_count: int,
    evidence_ref: str | None,
    evidence_digest: str | None,
    caller_verdict: str | None,
    error_code: str | None,
    retryable: bool,
) -> dict[str, Any]:
    core: dict[str, Any] = {
        "type": _STATE_TYPE,
        "ok": ok,
        "status": status,
        "supervisor_status": supervisor_status,
        "mode": request.mode,
        "phase": phase,
        "activity_id": request.activity_id,
        "transaction_ref": request.transaction_ref,
        "operation_ref": request.operation_ref,
        "session_ref": request.session_ref,
        "role_key": role_key,
        "idempotency_key": request.idempotency_key,
        "artifact_ref_count": artifact_ref_count,
        "evidence_ref": evidence_ref,
        "evidence_digest": evidence_digest,
        "caller_verdict": caller_verdict,
        "error_code": error_code,
        "retryable": retryable,
    }
    view_model_ref = _VIEW_MODEL_REF_PREFIX + _digest_hex(core)[:16]
    return {**core, "view_model_ref": view_model_ref}


def _fingerprint(request: SupervisedLocalActivityRequest, role_file: str) -> str:
    payload = {
        "activity_id": request.activity_id,
        "transaction_ref": request.transaction_ref,
        "operation_ref": request.operation_ref,
        "mode": request.mode,
        "role_key": request.role_key,
        "role_file": role_file,
        "prompt_ref": request.prompt_ref,
        "context_refs": list(request.context_refs),
        "cwd_ref": request.cwd_ref,
        "allowed_roots_ref": request.allowed_roots_ref,
        "session_ref": request.session_ref,
        "dry_run_first": request.dry_run_first,
    }
    return _digest_hex(payload)


def _build_local_offline_request(
    request: SupervisedLocalActivityRequest, role_file: str
) -> LocalOfflineSupervisorRequest:
    """Assemble the lower-level seam request from sanitized Activity inputs.

    Only claim-check refs travel; raw prompt/context are intentionally left
    ``None`` in this slice. ``correlation_label`` is the caller-owned activity
    id, and the exact local/offline approval token is supplied.
    """

    refs: list[str] = [request.transaction_ref, request.operation_ref]
    if request.prompt_ref is not None:
        refs.append(request.prompt_ref)
    refs.extend(request.context_refs)

    return LocalOfflineSupervisorRequest(
        mode=request.mode,
        correlation_label=request.activity_id,
        role=None,
        role_file=role_file,
        enabled=True,
        approval_token=LOCAL_OFFLINE_APPROVAL_TOKEN,
        prompt=None,
        context=None,
        claim_check_refs=tuple(refs),
    )


def _safe_code(value: str | None) -> str | None:
    if value is None:
        return None
    if _value_is_unsafe(value) or _STABLE_CODE_RE.fullmatch(value) is None:
        return None
    return value


def _safe_evidence_ref(value: str | None) -> str | None:
    if value is None:
        return None
    if _value_is_unsafe(value) or _EVIDENCE_REF_RE.fullmatch(value) is None:
        return None
    return value


def _safe_digest(value: str | None) -> str | None:
    if value is None:
        return None
    if _value_is_unsafe(value) or _SHA256_DIGEST_RE.fullmatch(value) is None:
        return None
    return value


def _safe_artifact_ref_count(value: int) -> int | None:
    if type(value) is not int or value < 0:
        return None
    return value


def _failure_state(request: SupervisedLocalActivityRequest) -> dict[str, Any]:
    return _build_durable_state(
        request,
        role_key=request.role_key,
        ok=False,
        status="error",
        supervisor_status=None,
        phase=_MODE_PHASES.get(request.mode, "unknown"),
        artifact_ref_count=0,
        evidence_ref=None,
        evidence_digest=None,
        caller_verdict=None,
        error_code="activity_supervisor_failed",
        retryable=True,
    )


def _state_from_supervisor_outcome(
    request: SupervisedLocalActivityRequest, outcome: LocalOfflineSupervisorOutcome
) -> dict[str, Any]:
    """Convert a supervisor outcome into trusted sanitized Activity state.

    The injected supervisor is still a boundary. Do not trust arbitrary strings
    from the lower-level outcome; if any externally supplied field is unsafe or
    malformed, collapse the whole Activity result into a stable retryable error
    rather than persisting raw material.
    """

    status = _safe_code(outcome.status)
    supervisor_status = _safe_code(outcome.supervisor_status)
    caller_verdict = _safe_code(outcome.caller_verdict)
    evidence_ref = _safe_evidence_ref(outcome.evidence_ref)
    evidence_digest = _safe_digest(outcome.evidence_digest)
    artifact_ref_count = _safe_artifact_ref_count(outcome.artifact_ref_count)
    lower_error_code = _safe_code(outcome.error_code)

    if (
        status is None
        or artifact_ref_count is None
        or (outcome.supervisor_status is not None and supervisor_status is None)
        or (outcome.caller_verdict is not None and caller_verdict is None)
        or (outcome.evidence_ref is not None and evidence_ref is None)
        or (outcome.evidence_digest is not None and evidence_digest is None)
        or (outcome.error_code is not None and lower_error_code is None)
    ):
        return _failure_state(request)

    has_lower_error = lower_error_code is not None or status == "error"
    return _build_durable_state(
        request,
        role_key=request.role_key,
        ok=not has_lower_error,
        status=status,
        supervisor_status=None if has_lower_error else supervisor_status,
        phase=_MODE_PHASES.get(request.mode, "unknown"),
        artifact_ref_count=0 if has_lower_error else artifact_ref_count,
        evidence_ref=None if has_lower_error else evidence_ref,
        evidence_digest=None if has_lower_error else evidence_digest,
        caller_verdict=None if has_lower_error else caller_verdict,
        error_code="activity_supervisor_failed" if has_lower_error else None,
        retryable=has_lower_error,
    )


# --------------------------------------------------------------------------- #
# Activity lifecycle: start + query
# --------------------------------------------------------------------------- #
def start_supervised_local_activity(
    request: SupervisedLocalActivityRequest,
    *,
    store: ActivityStateStore,
    invoke_supervisor: Callable[[LocalOfflineSupervisorRequest], LocalOfflineSupervisorOutcome]
    | None = None,
) -> SupervisedLocalActivityResult:
    """Start a supervised local ``exec_dry_run`` Activity.

    Gates, mode, material, and role checks all fail closed by raising
    :class:`SupervisedLocalActivityError`. The first slice requires an injected
    supervisor callable and never default-calls the seam runtime path. A repeat
    idempotency key replays stored sanitized state without re-invoking the
    supervisor; an incompatible repeat fails closed. A supervisor exception is
    caught and mapped to a stable ``activity_supervisor_failed`` result with no
    raw exception text.
    """

    _check_enabled_and_approved(request)
    if invoke_supervisor is None:
        raise SupervisedLocalActivityError(
            "activity_supervisor_injection_required",
            "first slice requires an injected supervisor callable",
        )
    _check_mode(request)
    _check_material(request)
    role_file = _resolve_role_file(request.role_key)

    fingerprint = _fingerprint(request, role_file)
    existing = store.get_idempotent(request.idempotency_key)
    if existing is not None:
        existing_fingerprint, existing_state = existing
        if existing_fingerprint != fingerprint:
            raise SupervisedLocalActivityError(
                "activity_idempotency_conflict",
                "idempotency key maps to an incompatible request",
            )
        return SupervisedLocalActivityResult(existing_state)

    local_request = _build_local_offline_request(request, role_file)
    try:
        outcome = invoke_supervisor(local_request)
    except Exception:
        state = _failure_state(request)
    else:
        state = _state_from_supervisor_outcome(request, outcome)

    store.put(
        activity_id=request.activity_id,
        idempotency_key=request.idempotency_key,
        fingerprint=fingerprint,
        state=state,
    )
    return SupervisedLocalActivityResult(state)


def query_supervised_local_activity(
    store: ActivityStateStore, *, activity_id: str
) -> SupervisedLocalActivityResult:
    """Return durable sanitized Activity state by ``activity_id``.

    Query is local state only; it never re-invokes the supervisor and never
    rehydrates raw material.
    """

    state = store.get_by_activity(activity_id)
    if state is None:
        raise SupervisedLocalActivityError(
            "activity_not_found", "no durable state for the given activity id"
        )
    return SupervisedLocalActivityResult(state)
