"""Phase E local/offline persistent-session lifecycle state machine.

This is the Option A first implementation slice of the Phase E design packet
``docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design.md``.
It implements the caller-owned durable ``SessionRecord`` / ``TurnRecord`` /
``CancellationRequestRecord`` shapes, the lifecycle state machine
(create / send / query / list / close / abort), lease/epoch/binding/
state-version guards, the lease-internal open-state recheck, the lifecycle
guard, stable lock ordering, and the full fail-closed failure taxonomy — with
**injected fakes only**.

Boundaries enforced here (local/offline only; design status DESIGN_ONLY for
any real execution):

  * Default-off with an *exact* Phase E approval token. A disabled or
    mismatched gate fails closed with a stable error code before any work.
  * Caller-owned durable state only. This module never imports or calls the
    supervisor library, a real runner, a package fetcher, a child process, a
    shell, a container, a service, a live messaging surface, or any delivery
    path. Every work-like step (open / turn / close / abort) is an explicitly
    *injected* fake outcome supplied by the caller; there is no default real
    runner — the work callable is a required keyword argument.
  * Cancellation is **request-state only**. ``request_cancellation`` records a
    durable ``cancel_requested`` (or ``rejected``) annotation and is fully
    idempotent; it NEVER interrupts a run, closes a session, calls an interrupt
    API, or implies a cancelled run. Any attempt to *execute* a cancellation
    fails closed with ``activity_cancel_not_approved``.
  * Single in-process store lock. The stable lock order is:
    ``(1) durable session store lock -> (2) per-record lifecycle guard
    (re-read + CAS on lease_epoch + state_version) -> (3) future supervisor
    handle``. The store lock is NEVER held across an injected work callback:
    work-starting operations claim under the lock, release it, invoke the
    injected fake, then finalize under the lock with a lease_epoch /
    state_version CAS. Ambiguity (drift / stale state / undeterminable turn)
    fails closed and is held for operator intervention — never duplicate-
    launched.
  * Durable records, query projections, and any logging carry only stable
    codes, caller-owned ids/refs, counts, digests, and opaque lease/binding
    tokens. Raw prompt/context, model output, tool logs, platform-private ids,
    card/media material, secrets, arbitrary paths, live process identifiers,
    and raw exception text never enter durable state. Resident projections are
    revalidated on every read so poisoned resident material can never be
    projected.

Nothing in this module starts, owns, or signals a real session, runner, or
process. Real session launch, cancellation execution, real agent execution,
controlled flow execution, and any live/IM/production/delivery surface each
require their own separately named approval.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

from .activity import ROLE_KEY_ALLOWLIST
from .local_offline import _value_is_unsafe

# --------------------------------------------------------------------------- #
# Approval token
# --------------------------------------------------------------------------- #
#: Exact approval token required to enable the Phase E local/offline
#: persistent-session lifecycle preflight / state-machine slice. It is
#: deliberately narrower than any session rollout: it approves only a
#: fail-closed local/offline state machine exercised with injected fakes.
SESSION_LIFECYCLE_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_phase_e_persistent_session_lifecycle_"
    "preflight_state_machine_local_offline_implementation_no_real_session_launch_"
    "no_cancellation_execution_no_real_agent_execution_no_live_no_gateway_no_feishu_"
    "no_production_config_no_real_delivery"
)

# --------------------------------------------------------------------------- #
# Lifecycle + status labels
# --------------------------------------------------------------------------- #
_STATE_OPENING = "session_opening"
_STATE_OPEN = "session_open"
_STATE_TURN = "session_turn"
_STATE_CLOSING = "session_closing"
_STATE_CLOSED = "session_closed"
_STATE_ABORTING = "session_aborting"
_STATE_ABORTED = "session_aborted"
_STATE_FAILED = "session_failed"

_TERMINAL_STATES = frozenset({_STATE_CLOSED, _STATE_ABORTED, _STATE_FAILED})
_ALL_LIFECYCLE_STATES = frozenset(
    {
        _STATE_OPENING,
        _STATE_OPEN,
        _STATE_TURN,
        _STATE_CLOSING,
        _STATE_CLOSED,
        _STATE_ABORTING,
        _STATE_ABORTED,
        _STATE_FAILED,
    }
)

_TURN_CLAIMED = "claimed_in_progress"
_TURN_COMPLETED = "completed"
_TURN_FAILED_RETRYABLE = "failed_retryable"
_TURN_FAILED_TERMINAL = "failed_terminal"
_TURN_AMBIGUOUS = "turn_ambiguous"
_TURN_STATUSES = frozenset(
    {
        _TURN_CLAIMED,
        _TURN_COMPLETED,
        _TURN_FAILED_RETRYABLE,
        _TURN_FAILED_TERMINAL,
        _TURN_AMBIGUOUS,
    }
)

_CANCEL_REQUESTED = "cancel_requested"
_CANCEL_REJECTED = "rejected"
_CANCEL_STATUSES = frozenset({_CANCEL_REQUESTED, _CANCEL_REJECTED})

#: Stable failure taxonomy carried by this slice (design taxonomy +
#: inherited). ``activity_cancel_ambiguous`` is defined for taxonomy
#: stability but is never raised here: cancellation execution has no approved
#: path, so there is no run whose stopped/not-stopped state could be
#: ambiguous.
_ERROR_SUPERVISOR_FAILED = "activity_supervisor_failed"
_ERROR_TOCTOU = "activity_session_toctou_conflict"
#: Stable taxonomy values allowed in durable ``error_code`` fields. They are
#: validated by exact membership (stricter than the generic code shape), so a
#: poisoned resident code is rejected while legitimate taxonomy codes — which
#: the generic platform-id heuristic can otherwise false-positive on
#: (``toct``ou_``conflict``) — are accepted only in the ``error_code`` field.
_STORED_ERROR_CODES = frozenset(
    {
        "activity_disabled",
        "activity_approval_mismatch",
        "activity_unsupported_mode",
        "activity_unknown_role",
        "activity_unsafe_material",
        "activity_idempotency_conflict",
        "activity_stale_state",
        "activity_lease_lost",
        "activity_toctou_conflict",
        "activity_retry_ambiguous",
        "activity_precondition_unmet",
        "activity_budget_exceeded",
        _ERROR_SUPERVISOR_FAILED,
        "activity_evidence_write_failed",
        "activity_not_found",
        "activity_runner_provenance_unverified",
        "activity_role_capability_rejected",
        "activity_claim_conflict",
        "activity_session_disabled",
        "activity_session_approval_mismatch",
        "activity_session_already_open",
        "activity_session_not_open",
        "activity_session_binding_mismatch",
        "activity_session_lease_lost",
        "activity_session_stale_state",
        _ERROR_TOCTOU,
        "activity_session_turn_ambiguous",
        "activity_cancel_not_approved",
        "activity_cancel_ambiguous",
        "activity_lifecycle_conflict",
    }
)

_SESSION_TYPE = "sachima.supervisor.session_lifecycle_record.v1"
_TURN_TYPE = "sachima.supervisor.session_turn_record.v1"
_CANCEL_TYPE = "sachima.supervisor.session_cancel_request_record.v1"
_PHASE = "session_lifecycle"
_SESSION_VIEW_PREFIX = "session_lifecycle_view_"
_TURN_VIEW_PREFIX = "session_turn_view_"
_CANCEL_VIEW_PREFIX = "session_cancel_view_"

_STABLE_CODE_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")
_EVIDENCE_REF_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,127}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_REF_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_UNSAFE_MARKERS = ("media_path", "raw_prompt", "prompt_body")

_SESSION_STATE_KEYS = frozenset(
    {
        "type",
        "ok",
        "lifecycle_state",
        "phase",
        "session_id",
        "activity_id",
        "transaction_ref",
        "operation_ref",
        "role_key",
        "role_file_digest",
        "session_binding",
        "idempotency_key",
        "request_fingerprint",
        "lease_id",
        "lease_epoch",
        "lease_holder_ref",
        "state_version",
        "turn_count",
        "open_turn_index",
        "max_turns",
        "max_artifacts_per_turn",
        "supervisor_status",
        "evidence_ref",
        "evidence_digest",
        "caller_verdict",
        "error_code",
        "view_model_ref",
    }
)

_TURN_STATE_KEYS = frozenset(
    {
        "type",
        "ok",
        "status",
        "session_id",
        "activity_id",
        "turn_index",
        "idempotency_key",
        "request_fingerprint",
        "prompt_ref",
        "lease_epoch_at_launch",
        "supervisor_status",
        "evidence_ref",
        "evidence_digest",
        "artifact_ref_count",
        "error_code",
        "view_model_ref",
    }
)

_CANCEL_STATE_KEYS = frozenset(
    {
        "type",
        "ok",
        "status",
        "cancel_id",
        "session_id",
        "activity_id",
        "transaction_ref",
        "operation_ref",
        "turn_index",
        "requested_by_ref",
        "operator_gate",
        "reason_code",
        "idempotency_key",
        "request_fingerprint",
        "lease_id",
        "lease_epoch",
        "lease_holder_ref",
        "evidence_ref",
        "evidence_digest",
        "error_code",
        "view_model_ref",
    }
)


# --------------------------------------------------------------------------- #
# Public error / outcome / requests / results
# --------------------------------------------------------------------------- #
class SessionLifecycleError(Exception):
    """Fail-closed session-lifecycle boundary error carrying a stable code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


@dataclass(frozen=True)
class SessionWorkOutcome:
    """Injected fake outcome for a work-like lifecycle step.

    The caller (in tests) supplies this to represent a session open, a turn,
    a graceful close, or a forced abort. No field is trusted blindly: every
    value is sanitized at the boundary, and any unsafe or malformed field
    collapses the step into a stable sanitized failure rather than leaking.
    """

    ok: bool
    supervisor_status: str | None = None
    session_binding: str | None = None
    evidence_ref: str | None = None
    evidence_digest: str | None = None
    artifact_ref_count: int = 0
    error_code: str | None = None


@dataclass(frozen=True)
class SessionCreateRequest:
    activity_id: str
    transaction_ref: str
    operation_ref: str
    session_id: str
    idempotency_key: str
    role_key: str
    approval_token: str = ""
    enabled: bool = False
    role_file_digest: str | None = None
    prompt_ref: str | None = None
    context_refs: tuple[str, ...] = ()
    cwd_ref: str | None = None
    allowed_roots_ref: str | None = None
    lease_id: str | None = None
    lease_epoch: int = 0
    lease_holder_ref: str | None = None
    expected_state_version: int = 0
    operator_gate: bool = False
    max_turns: int = 0
    max_artifacts_per_turn: int = 0


@dataclass(frozen=True)
class SessionSendRequest:
    activity_id: str
    session_id: str
    transaction_ref: str
    operation_ref: str
    idempotency_key: str
    approval_token: str = ""
    enabled: bool = False
    session_binding: str | None = None
    prompt_ref: str | None = None
    context_refs: tuple[str, ...] = ()
    lease_id: str | None = None
    lease_epoch: int = 0
    lease_holder_ref: str | None = None
    expected_state_version: int = 0
    operator_gate: bool = False


@dataclass(frozen=True)
class SessionCloseRequest:
    activity_id: str
    session_id: str
    transaction_ref: str
    operation_ref: str
    idempotency_key: str
    approval_token: str = ""
    enabled: bool = False
    session_binding: str | None = None
    lease_id: str | None = None
    lease_epoch: int = 0
    lease_holder_ref: str | None = None
    expected_state_version: int = 0
    operator_gate: bool = False


@dataclass(frozen=True)
class SessionAbortRequest:
    activity_id: str
    session_id: str
    transaction_ref: str
    operation_ref: str
    idempotency_key: str
    approval_token: str = ""
    enabled: bool = False
    session_binding: str | None = None
    lease_id: str | None = None
    lease_epoch: int = 0
    lease_holder_ref: str | None = None
    expected_state_version: int = 0
    operator_gate: bool = False


@dataclass(frozen=True)
class CancellationRequest:
    cancel_id: str
    activity_id: str
    session_id: str
    transaction_ref: str
    operation_ref: str
    idempotency_key: str
    approval_token: str = ""
    enabled: bool = False
    session_binding: str | None = None
    requested_by_ref: str | None = None
    reason_code: str | None = None
    turn_index: int | None = None
    lease_id: str | None = None
    lease_epoch: int = 0
    lease_holder_ref: str | None = None
    operator_gate: bool = False
    #: Request-state only. ``True`` means "execute the cancellation now", which
    #: has no approved path and always fails closed.
    execute: bool = False


class _RecordResult:
    """Sanitized, read-only view over a validated durable record."""

    def __init__(self, state: Mapping[str, Any]) -> None:
        self._state: dict[str, Any] = dict(state)

    def to_durable_state(self) -> dict[str, Any]:
        return dict(self._state)


class SessionRecordResult(_RecordResult):
    @property
    def ok(self) -> bool:
        return self._state["ok"]

    @property
    def lifecycle_state(self) -> str:
        return self._state["lifecycle_state"]

    @property
    def session_id(self) -> str:
        return self._state["session_id"]

    @property
    def activity_id(self) -> str:
        return self._state["activity_id"]

    @property
    def session_binding(self) -> str | None:
        return self._state["session_binding"]

    @property
    def state_version(self) -> int:
        return self._state["state_version"]

    @property
    def turn_count(self) -> int:
        return self._state["turn_count"]

    @property
    def open_turn_index(self) -> int | None:
        return self._state["open_turn_index"]

    @property
    def error_code(self) -> str | None:
        return self._state["error_code"]


class TurnRecordResult(_RecordResult):
    @property
    def ok(self) -> bool:
        return self._state["ok"]

    @property
    def status(self) -> str:
        return self._state["status"]

    @property
    def turn_index(self) -> int:
        return self._state["turn_index"]

    @property
    def error_code(self) -> str | None:
        return self._state["error_code"]


class CancellationRequestResult(_RecordResult):
    @property
    def status(self) -> str:
        return self._state["status"]

    @property
    def cancel_id(self) -> str:
        return self._state["cancel_id"]

    @property
    def error_code(self) -> str | None:
        return self._state["error_code"]


@dataclass(frozen=True)
class _LeaseRecord:
    lease_id: str | None
    lease_epoch: int
    lease_holder_ref: str | None
    state_version: int


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
@dataclass
class SessionLifecycleStore:
    """Caller-owned, in-process durable session store with a single lock.

    All durable session / turn / cancellation state lives here. Every
    compound check-and-set runs under one reentrant store mutex; the lock is
    never held across an injected work callback. Resident projections are
    revalidated on every read.
    """

    _sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    _session_idem: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)
    _turns: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _turn_idem: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)
    _cancels: dict[str, dict[str, Any]] = field(default_factory=dict)
    _cancel_idem: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)
    _leases: dict[str, _LeaseRecord] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def grant_lease(
        self,
        *,
        activity_id: str,
        lease_id: str | None,
        lease_epoch: int,
        lease_holder_ref: str | None,
        state_version: int = 0,
    ) -> None:
        with self._lock:
            self._leases[activity_id] = _LeaseRecord(
                lease_id=lease_id,
                lease_epoch=lease_epoch,
                lease_holder_ref=lease_holder_ref,
                state_version=state_version,
            )

    def get_session(self, activity_id: str) -> dict[str, Any] | None:
        with self._lock:
            raw = self._sessions.get(activity_id)
            return None if raw is None else _validate_session_projection(raw)


# --------------------------------------------------------------------------- #
# Shared request-shape validation (lock-free)
# --------------------------------------------------------------------------- #
def _check_enabled_and_approved(request: Any) -> None:
    if request.enabled is not True:
        raise SessionLifecycleError(
            "activity_session_disabled", "session lifecycle is default-off"
        )
    if request.approval_token != SESSION_LIFECYCLE_APPROVAL_TOKEN:
        raise SessionLifecycleError(
            "activity_session_approval_mismatch",
            "exact session lifecycle approval token required",
        )


def _check_operator_gate(request: Any) -> None:
    if request.operator_gate is not True:
        raise SessionLifecycleError(
            "activity_precondition_unmet", "operator gate is required"
        )


def _resolve_role_key(role_key: str) -> None:
    if ROLE_KEY_ALLOWLIST.get(role_key) is None:
        raise SessionLifecycleError(
            "activity_unknown_role", "role key is not in the caller-owned allowlist"
        )


def _unsafe_material() -> SessionLifecycleError:
    return SessionLifecycleError(
        "activity_unsafe_material", "unsafe material rejected at session boundary"
    )


def _check_required_refs(values: tuple[Any, ...]) -> None:
    for value in values:
        if not _is_required_safe_ref(value):
            raise _unsafe_material()


def _check_optional_refs(values: tuple[Any, ...]) -> None:
    for value in values:
        if (
            _value_is_unsafe(value)
            or _has_unsafe_marker(value)
            or not _is_safe_ref_or_none(value)
        ):
            raise _unsafe_material()


def _check_digest(value: Any) -> None:
    if type(value) is not str or _SHA256_DIGEST_RE.fullmatch(value) is None:
        raise _unsafe_material()


def _check_create_material(request: SessionCreateRequest) -> None:
    if type(request.context_refs) is not tuple:
        raise _unsafe_material()
    _check_required_refs(
        (
            request.activity_id,
            request.session_id,
            request.transaction_ref,
            request.operation_ref,
            request.idempotency_key,
        )
    )
    _check_digest(request.role_file_digest)
    _check_optional_refs(
        (
            request.prompt_ref,
            request.cwd_ref,
            request.allowed_roots_ref,
            request.lease_id,
            request.lease_holder_ref,
            *request.context_refs,
        )
    )


def _check_send_material(request: SessionSendRequest) -> None:
    if type(request.context_refs) is not tuple:
        raise _unsafe_material()
    _check_required_refs(
        (
            request.activity_id,
            request.session_id,
            request.transaction_ref,
            request.operation_ref,
            request.idempotency_key,
        )
    )
    _check_optional_refs(
        (
            request.prompt_ref,
            request.lease_id,
            request.lease_holder_ref,
            *request.context_refs,
        )
    )


def _check_lifecycle_material(request: SessionCloseRequest | SessionAbortRequest) -> None:
    _check_required_refs(
        (
            request.activity_id,
            request.session_id,
            request.transaction_ref,
            request.operation_ref,
            request.idempotency_key,
        )
    )
    _check_optional_refs((request.lease_id, request.lease_holder_ref))


def _check_cancel_material(request: CancellationRequest) -> None:
    _check_required_refs(
        (
            request.cancel_id,
            request.activity_id,
            request.session_id,
            request.transaction_ref,
            request.operation_ref,
            request.idempotency_key,
        )
    )
    _check_optional_refs((request.requested_by_ref, request.lease_id, request.lease_holder_ref))
    reason = request.reason_code
    if reason is not None and (
        type(reason) is not str
        or _value_is_unsafe(reason)
        or _has_unsafe_marker(reason)
        or _STABLE_CODE_RE.fullmatch(reason) is None
    ):
        raise _unsafe_material()


def _check_create_budget(request: SessionCreateRequest) -> None:
    if not _is_int_at_least(request.max_turns, 1):
        raise SessionLifecycleError("activity_budget_exceeded", "invalid max_turns budget")
    if not _is_int_at_least(request.max_artifacts_per_turn, 0):
        raise SessionLifecycleError(
            "activity_budget_exceeded", "invalid max_artifacts_per_turn budget"
        )


# --------------------------------------------------------------------------- #
# Resident-state-dependent guards (caller holds the store lock)
# --------------------------------------------------------------------------- #
def _check_lease(request: Any, store: SessionLifecycleStore) -> _LeaseRecord:
    if not _is_required_safe_ref(request.lease_id) or not _is_required_safe_ref(
        request.lease_holder_ref
    ):
        raise SessionLifecycleError(
            "activity_session_lease_lost", "request lease refs are invalid"
        )
    if not _is_int_at_least(request.lease_epoch, 0):
        raise SessionLifecycleError("activity_session_lease_lost", "invalid lease epoch")
    lease = store._leases.get(request.activity_id)
    if lease is None:
        raise SessionLifecycleError(
            "activity_session_lease_lost", "no current lease for activity"
        )
    if not _is_required_safe_ref(lease.lease_id) or not _is_required_safe_ref(
        lease.lease_holder_ref
    ):
        raise SessionLifecycleError(
            "activity_session_lease_lost", "stored lease refs are invalid"
        )
    if not _is_int_at_least(lease.lease_epoch, 0):
        raise SessionLifecycleError(
            "activity_session_lease_lost", "stored lease epoch is invalid"
        )
    if request.lease_epoch < lease.lease_epoch:
        raise SessionLifecycleError("activity_session_stale_state", "lease epoch is stale")
    if (
        request.lease_id != lease.lease_id
        or request.lease_epoch != lease.lease_epoch
        or request.lease_holder_ref != lease.lease_holder_ref
    ):
        raise SessionLifecycleError(
            "activity_session_lease_lost", "caller no longer owns the lease"
        )
    return lease


def _check_state_version_baseline(request: SessionCreateRequest, lease: _LeaseRecord) -> None:
    if not _is_int_at_least(request.expected_state_version, 0):
        raise SessionLifecycleError(
            "activity_session_stale_state", "invalid expected state version"
        )
    if request.expected_state_version != lease.state_version:
        raise SessionLifecycleError(
            "activity_session_stale_state", "state version drifted from lease baseline"
        )


def _check_state_version_current(request: Any, session: Mapping[str, Any]) -> None:
    if not _is_int_at_least(request.expected_state_version, 0):
        raise SessionLifecycleError(
            "activity_session_stale_state", "invalid expected state version"
        )
    if request.expected_state_version != session["state_version"]:
        raise SessionLifecycleError(
            "activity_session_stale_state", "session state version drifted"
        )


def _check_session_binding(request: Any, session: Mapping[str, Any]) -> None:
    if (
        not _is_required_safe_ref(request.session_binding)
        or request.session_binding != session["session_binding"]
    ):
        raise SessionLifecycleError(
            "activity_session_binding_mismatch", "session binding does not match"
        )


def _resident_session(store: SessionLifecycleStore, activity_id: str) -> dict[str, Any] | None:
    raw = store._sessions.get(activity_id)
    return None if raw is None else _validate_session_projection(raw)


def _resident_turn(
    store: SessionLifecycleStore, activity_id: str, turn_index: int
) -> dict[str, Any] | None:
    for raw in store._turns.get(activity_id, ()):
        validated = _validate_turn_projection(raw)
        if validated["turn_index"] == turn_index:
            return validated
    return None


def _store_session(store: SessionLifecycleStore, state: dict[str, Any], *, fingerprint: str) -> None:
    validated = _validate_session_projection(state)
    store._sessions[validated["activity_id"]] = validated
    store._session_idem[validated["idempotency_key"]] = (fingerprint, validated)


def _store_turn(store: SessionLifecycleStore, state: dict[str, Any], *, fingerprint: str) -> None:
    validated = _validate_turn_projection(state)
    activity_id = validated["activity_id"]
    turns = store._turns.setdefault(activity_id, [])
    for index, existing in enumerate(turns):
        if existing["turn_index"] == validated["turn_index"]:
            if (
                existing["idempotency_key"] == validated["idempotency_key"]
                and existing["status"] == _TURN_CLAIMED
            ):
                turns[index] = validated
                break
            if existing == validated:
                break
            raise SessionLifecycleError(
                "activity_idempotency_conflict",
                "turn index already belongs to a finalized durable turn",
            )
            break
    else:
        turns.append(validated)
    store._turn_idem[validated["idempotency_key"]] = (fingerprint, validated)


# --------------------------------------------------------------------------- #
# create_session
# --------------------------------------------------------------------------- #
def create_session(
    request: SessionCreateRequest,
    *,
    store: SessionLifecycleStore,
    open_session: Callable[[SessionCreateRequest], SessionWorkOutcome],
) -> SessionRecordResult:
    """Open exactly one local session for an activity via an injected fake.

    Every gate fails closed before the atomic claim. The claim writes a
    ``session_opening`` record under the store lock; the lock is then released
    and the injected ``open_session`` fake runs; finalize re-reads under the
    lock and, on a clean lease/state-version CAS, transitions to
    ``session_open`` (or ``session_failed`` if the fake fails or returns an
    unsafe binding). At most one non-terminal session may exist per activity;
    identical replays return the resident projection without a second open.
    """

    _check_enabled_and_approved(request)
    _check_operator_gate(request)
    _resolve_role_key(request.role_key)
    _check_create_material(request)
    _check_create_budget(request)
    fingerprint = _create_fingerprint(request)

    with store._lock:
        existing = _resident_idem(store._session_idem, request.idempotency_key, _validate_session_projection)
        if existing is not None:
            existing_fp, existing_state = existing
            if existing_fp != fingerprint:
                raise SessionLifecycleError(
                    "activity_idempotency_conflict",
                    "idempotency key maps to an incompatible session create",
                )
            return SessionRecordResult(existing_state)
        if _resident_session(store, request.activity_id) is not None:
            raise SessionLifecycleError(
                "activity_session_already_open",
                "a session already exists for this activity",
            )
        lease = _check_lease(request, store)
        _check_state_version_baseline(request, lease)
        claimed = _new_session(
            request,
            fingerprint=fingerprint,
            lifecycle_state=_STATE_OPENING,
            session_binding=None,
            state_version=request.expected_state_version,
            turn_count=0,
            open_turn_index=None,
            supervisor_status=None,
            evidence_ref=None,
            evidence_digest=None,
            error_code=None,
            ok=False,
        )
        _store_session(store, claimed, fingerprint=fingerprint)
        launch_epoch = lease.lease_epoch
        claimed_version = request.expected_state_version

    outcome = _safe_call(open_session, request)

    with store._lock:
        resident = _resident_session(store, request.activity_id)
        _assert_no_finalize_drift(
            resident,
            store,
            request.activity_id,
            expected_state=_STATE_OPENING,
            claimed_version=claimed_version,
            launch_epoch=launch_epoch,
        )
        binding = _safe_ref_value(getattr(outcome, "session_binding", None)) if outcome else None
        if outcome is not None and getattr(outcome, "ok", None) is True and binding is not None:
            final = _new_session(
                request,
                fingerprint=fingerprint,
                lifecycle_state=_STATE_OPEN,
                session_binding=binding,
                state_version=claimed_version + 1,
                turn_count=0,
                open_turn_index=None,
                supervisor_status=_safe_code(getattr(outcome, "supervisor_status", None)),
                evidence_ref=_safe_evidence_ref(getattr(outcome, "evidence_ref", None)),
                evidence_digest=_safe_digest(getattr(outcome, "evidence_digest", None)),
                error_code=None,
                ok=True,
            )
        else:
            final = _new_session(
                request,
                fingerprint=fingerprint,
                lifecycle_state=_STATE_FAILED,
                session_binding=None,
                state_version=claimed_version + 1,
                turn_count=0,
                open_turn_index=None,
                supervisor_status=None,
                evidence_ref=None,
                evidence_digest=None,
                error_code=_ERROR_SUPERVISOR_FAILED,
                ok=False,
            )
        _store_session(store, final, fingerprint=fingerprint)
        return SessionRecordResult(final)


# --------------------------------------------------------------------------- #
# send_session_turn
# --------------------------------------------------------------------------- #
def send_session_turn(
    request: SessionSendRequest,
    *,
    store: SessionLifecycleStore,
    run_turn: Callable[[SessionSendRequest], SessionWorkOutcome],
) -> TurnRecordResult:
    """Claim and run exactly one turn against an open session via a fake.

    Under the store lock the session is re-read and required to be
    ``session_open`` with no in-flight turn before the turn is claimed
    (``claimed_in_progress``) and the session moves to ``session_turn``. The
    lock is released, the injected ``run_turn`` fake runs, and finalize
    re-reads under the lock: a clean CAS completes the turn and returns the
    session to ``session_open``; lease/state-version drift fails closed and
    holds the turn ``turn_ambiguous`` for operator intervention; a failed or
    unsafe fake outcome collapses to a sanitized terminal turn.
    """

    _check_enabled_and_approved(request)
    _check_operator_gate(request)
    _check_send_material(request)
    fingerprint = _turn_fingerprint(request)

    with store._lock:
        existing = _resident_idem(store._turn_idem, request.idempotency_key, _validate_turn_projection)
        if existing is not None:
            existing_fp, existing_state = existing
            if existing_fp != fingerprint:
                raise SessionLifecycleError(
                    "activity_idempotency_conflict",
                    "idempotency key maps to an incompatible turn",
                )
            return TurnRecordResult(existing_state)
        session = _resident_session(store, request.activity_id)
        if session is None:
            raise SessionLifecycleError("activity_not_found", "no session for activity id")
        _check_session_binding(request, session)
        lease = _check_lease(request, store)
        _check_state_version_current(request, session)
        if session["lifecycle_state"] != _STATE_OPEN or session["open_turn_index"] is not None:
            raise SessionLifecycleError(
                "activity_session_not_open", "session is not open for a new turn"
            )
        if session["turn_count"] >= session["max_turns"]:
            raise SessionLifecycleError(
                "activity_budget_exceeded", "session turn budget exceeded"
            )
        turn_index = session["turn_count"] + 1
        claimed_turn = _new_turn(
            request,
            fingerprint=fingerprint,
            turn_index=turn_index,
            status=_TURN_CLAIMED,
            lease_epoch_at_launch=lease.lease_epoch,
            supervisor_status=None,
            evidence_ref=None,
            evidence_digest=None,
            artifact_ref_count=0,
            error_code=None,
            ok=False,
        )
        _store_turn(store, claimed_turn, fingerprint=fingerprint)
        claimed_version = session["state_version"]
        in_turn_session = _session_with(
            session, lifecycle_state=_STATE_TURN, open_turn_index=turn_index, ok=True
        )
        _store_session(store, in_turn_session, fingerprint=session["request_fingerprint"])
        launch_epoch = lease.lease_epoch

    outcome = _safe_call(run_turn, request)

    with store._lock:
        session = _resident_session(store, request.activity_id)
        lease = store._leases.get(request.activity_id)
        drift = (
            session is None
            or session["lifecycle_state"] != _STATE_TURN
            or session["open_turn_index"] != turn_index
            or session["state_version"] != claimed_version
            or lease is None
            or lease.lease_epoch != launch_epoch
        )
        if drift:
            ambiguous = _turn_with(
                claimed_turn, status=_TURN_AMBIGUOUS, ok=False, error_code=_ERROR_TOCTOU
            )
            _store_turn(store, ambiguous, fingerprint=fingerprint)
            if (
                session is not None
                and session["lifecycle_state"] == _STATE_TURN
                and session["open_turn_index"] == turn_index
            ):
                held = _session_with(session, ok=False, error_code=_ERROR_TOCTOU)
                _store_session(store, held, fingerprint=session["request_fingerprint"])
            raise SessionLifecycleError(
                _ERROR_TOCTOU, "session drifted before turn finalize"
            )
        assert session is not None
        terminal_turn = _turn_from_outcome(
            claimed_turn,
            outcome,
            max_artifacts_per_turn=session["max_artifacts_per_turn"],
        )
        _store_turn(store, terminal_turn, fingerprint=fingerprint)
        next_session = _session_with(
            session,
            lifecycle_state=_STATE_OPEN,
            open_turn_index=None,
            turn_count=session["turn_count"] + 1,
            state_version=session["state_version"] + 1,
            ok=True,
        )
        _store_session(store, next_session, fingerprint=session["request_fingerprint"])
        return TurnRecordResult(terminal_turn)


# --------------------------------------------------------------------------- #
# close_session / abort_session
# --------------------------------------------------------------------------- #
def close_session(
    request: SessionCloseRequest,
    *,
    store: SessionLifecycleStore,
    apply_close: Callable[[SessionCloseRequest], SessionWorkOutcome],
) -> SessionRecordResult:
    """Gracefully close an open session via an injected fake.

    The lifecycle guard re-reads the session inside the lock. Close is valid
    only from ``session_open`` with no in-flight turn; an in-flight turn or a
    non-closed terminal state fails closed with ``activity_lifecycle_conflict``.
    An already-closed (or closing) session replays idempotently without a
    second close.
    """

    return _lifecycle_terminal_transition(
        request,
        store=store,
        work=apply_close,
        claim_state=_STATE_CLOSING,
        terminal_state=_STATE_CLOSED,
        idempotent_states=(_STATE_CLOSED, _STATE_CLOSING),
        valid_from=(_STATE_OPEN,),
        allow_in_flight_turn=False,
    )


def abort_session(
    request: SessionAbortRequest,
    *,
    store: SessionLifecycleStore,
    apply_abort: Callable[[SessionAbortRequest], SessionWorkOutcome],
) -> SessionRecordResult:
    """Force a session to a terminal aborted state via an injected fake.

    Operator-gated. Abort records the ``session_aborting`` intent before the
    injected fake runs and never performs a real process kill. It is valid
    from ``session_open`` or ``session_turn`` — including a ``session_turn``
    with an in-flight turn, since a forced terminal must be able to pre-empt a
    running turn (the in-flight turn's own finalize then fails closed and is
    held ``turn_ambiguous`` rather than duplicate-launching). Any already-
    terminal or already-aborting session replays idempotently (no double-abort).
    """

    return _lifecycle_terminal_transition(
        request,
        store=store,
        work=apply_abort,
        claim_state=_STATE_ABORTING,
        terminal_state=_STATE_ABORTED,
        idempotent_states=(_STATE_CLOSED, _STATE_ABORTED, _STATE_FAILED, _STATE_ABORTING),
        valid_from=(_STATE_OPEN, _STATE_TURN),
        allow_in_flight_turn=True,
    )


def _lifecycle_terminal_transition(
    request: SessionCloseRequest | SessionAbortRequest,
    *,
    store: SessionLifecycleStore,
    work: Callable[[Any], SessionWorkOutcome],
    claim_state: str,
    terminal_state: str,
    idempotent_states: tuple[str, ...],
    valid_from: tuple[str, ...],
    allow_in_flight_turn: bool,
) -> SessionRecordResult:
    _check_enabled_and_approved(request)
    _check_operator_gate(request)
    _check_lifecycle_material(request)

    with store._lock:
        session = _resident_session(store, request.activity_id)
        if session is None:
            raise SessionLifecycleError("activity_not_found", "no session for activity id")
        _check_session_binding(request, session)
        _check_lease(request, store)
        state = session["lifecycle_state"]
        if state in idempotent_states:
            return SessionRecordResult(session)
        in_flight_turn = session["open_turn_index"] is not None
        if state not in valid_from or (in_flight_turn and not allow_in_flight_turn):
            raise SessionLifecycleError(
                "activity_lifecycle_conflict",
                "lifecycle operation is not valid from the current state",
            )
        _check_state_version_current(request, session)
        claimed = _session_with(session, lifecycle_state=claim_state, ok=True)
        _store_session(store, claimed, fingerprint=session["request_fingerprint"])
        claimed_version = session["state_version"]
        launch_epoch = store._leases[request.activity_id].lease_epoch

    outcome = _safe_call(work, request)

    with store._lock:
        session = _resident_session(store, request.activity_id)
        _assert_no_finalize_drift(
            session,
            store,
            request.activity_id,
            expected_state=claim_state,
            claimed_version=claimed_version,
            launch_epoch=launch_epoch,
        )
        if outcome is not None and getattr(outcome, "ok", None) is True:
            final = _session_with(
                session,
                lifecycle_state=terminal_state,
                open_turn_index=None,
                state_version=session["state_version"] + 1,
                supervisor_status=_safe_code(getattr(outcome, "supervisor_status", None)),
                evidence_ref=_safe_evidence_ref(getattr(outcome, "evidence_ref", None)),
                evidence_digest=_safe_digest(getattr(outcome, "evidence_digest", None)),
                error_code=None,
                ok=True,
            )
        else:
            final = _session_with(
                session,
                lifecycle_state=_STATE_FAILED,
                state_version=session["state_version"] + 1,
                supervisor_status=None,
                evidence_ref=None,
                evidence_digest=None,
                error_code=_ERROR_SUPERVISOR_FAILED,
                ok=False,
            )
        _store_session(store, final, fingerprint=session["request_fingerprint"])
        return SessionRecordResult(final)


# --------------------------------------------------------------------------- #
# query / list (read-only)
# --------------------------------------------------------------------------- #
def query_session(store: SessionLifecycleStore, *, activity_id: str) -> SessionRecordResult:
    """Return the sanitized durable session projection by ``activity_id``."""

    state = store.get_session(activity_id)
    if state is None:
        raise SessionLifecycleError("activity_not_found", "no session for activity id")
    return SessionRecordResult(state)


def list_sessions(
    store: SessionLifecycleStore,
    *,
    transaction_ref: str | None = None,
    lifecycle_state: str | None = None,
) -> list[SessionRecordResult]:
    """Return sanitized session projections filtered by ref / lifecycle state."""

    with store._lock:
        results: list[SessionRecordResult] = []
        for raw in store._sessions.values():
            state = _validate_session_projection(raw)
            if transaction_ref is not None and state["transaction_ref"] != transaction_ref:
                continue
            if lifecycle_state is not None and state["lifecycle_state"] != lifecycle_state:
                continue
            results.append(SessionRecordResult(state))
        return results


def list_session_turns(
    store: SessionLifecycleStore, *, activity_id: str
) -> list[TurnRecordResult]:
    """Return sanitized turn projections for a session, ascending by index."""

    with store._lock:
        turns = [_validate_turn_projection(raw) for raw in store._turns.get(activity_id, ())]
        turns.sort(key=lambda state: state["turn_index"])
        return [TurnRecordResult(state) for state in turns]


# --------------------------------------------------------------------------- #
# request_cancellation (request-state only; NO execution)
# --------------------------------------------------------------------------- #
def request_cancellation(
    request: CancellationRequest, *, store: SessionLifecycleStore
) -> CancellationRequestResult:
    """Record a durable cancellation *request* against a session/turn.

    This is request-state only: it records ``cancel_requested`` (or
    ``rejected`` when the target is already terminal), is idempotent, and never
    interrupts a run, closes a session, or implies a cancelled run. Any attempt
    to *execute* the cancellation (``execute=True``) fails closed with
    ``activity_cancel_not_approved`` and records nothing.
    """

    _check_enabled_and_approved(request)
    if request.execute is not False:
        raise SessionLifecycleError(
            "activity_cancel_not_approved", "cancellation execution has no approved path"
        )
    _check_operator_gate(request)
    _check_cancel_material(request)
    fingerprint = _cancel_fingerprint(request)

    with store._lock:
        existing = _resident_idem(store._cancel_idem, request.idempotency_key, _validate_cancel_projection)
        if existing is not None:
            existing_fp, existing_state = existing
            if existing_fp != fingerprint:
                raise SessionLifecycleError(
                    "activity_idempotency_conflict",
                    "idempotency key maps to an incompatible cancellation request",
                )
            return CancellationRequestResult(existing_state)
        session = _resident_session(store, request.activity_id)
        if session is None or request.session_id != session["session_id"]:
            raise SessionLifecycleError("activity_not_found", "no session for cancellation target")
        _check_session_binding(request, session)
        _check_lease(request, store)
        _check_cancel_turn_scope(request, session)
        status = (
            _CANCEL_REJECTED
            if session["lifecycle_state"] in _TERMINAL_STATES
            else _CANCEL_REQUESTED
        )
        record = _new_cancel(request, fingerprint=fingerprint, status=status)
        validated = _validate_cancel_projection(record)
        store._cancels[request.cancel_id] = validated
        store._cancel_idem[request.idempotency_key] = (fingerprint, validated)
        return CancellationRequestResult(validated)


def _check_cancel_turn_scope(request: CancellationRequest, session: Mapping[str, Any]) -> None:
    if request.turn_index is None:
        return
    if not _is_int_at_least(request.turn_index, 1):
        raise SessionLifecycleError(
            "activity_not_found", "cancellation turn index is invalid"
        )
    in_range = request.turn_index <= session["turn_count"] or (
        request.turn_index == session["open_turn_index"]
    )
    if not in_range:
        raise SessionLifecycleError(
            "activity_not_found", "cancellation turn index is out of range"
        )


# --------------------------------------------------------------------------- #
# Record builders
# --------------------------------------------------------------------------- #
def _materialize(core: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {**core, "view_model_ref": prefix + _digest_hex(core)[:16]}


def _new_session(
    request: SessionCreateRequest,
    *,
    fingerprint: str,
    lifecycle_state: str,
    session_binding: str | None,
    state_version: int,
    turn_count: int,
    open_turn_index: int | None,
    supervisor_status: str | None,
    evidence_ref: str | None,
    evidence_digest: str | None,
    error_code: str | None,
    ok: bool,
) -> dict[str, Any]:
    core = {
        "type": _SESSION_TYPE,
        "ok": ok,
        "lifecycle_state": lifecycle_state,
        "phase": _PHASE,
        "session_id": request.session_id,
        "activity_id": request.activity_id,
        "transaction_ref": request.transaction_ref,
        "operation_ref": request.operation_ref,
        "role_key": request.role_key,
        "role_file_digest": request.role_file_digest,
        "session_binding": session_binding,
        "idempotency_key": request.idempotency_key,
        "request_fingerprint": fingerprint,
        "lease_id": request.lease_id,
        "lease_epoch": request.lease_epoch,
        "lease_holder_ref": request.lease_holder_ref,
        "state_version": state_version,
        "turn_count": turn_count,
        "open_turn_index": open_turn_index,
        "max_turns": request.max_turns,
        "max_artifacts_per_turn": request.max_artifacts_per_turn,
        "supervisor_status": supervisor_status,
        "evidence_ref": evidence_ref,
        "evidence_digest": evidence_digest,
        "caller_verdict": None,
        "error_code": error_code,
    }
    return _materialize(core, _SESSION_VIEW_PREFIX)


def _session_with(session: Mapping[str, Any], **changes: Any) -> dict[str, Any]:
    core = {key: value for key, value in session.items() if key != "view_model_ref"}
    core.update(changes)
    return _materialize(core, _SESSION_VIEW_PREFIX)


def _new_turn(
    request: SessionSendRequest,
    *,
    fingerprint: str,
    turn_index: int,
    status: str,
    lease_epoch_at_launch: int,
    supervisor_status: str | None,
    evidence_ref: str | None,
    evidence_digest: str | None,
    artifact_ref_count: int,
    error_code: str | None,
    ok: bool,
) -> dict[str, Any]:
    core = {
        "type": _TURN_TYPE,
        "ok": ok,
        "status": status,
        "session_id": request.session_id,
        "activity_id": request.activity_id,
        "turn_index": turn_index,
        "idempotency_key": request.idempotency_key,
        "request_fingerprint": fingerprint,
        "prompt_ref": request.prompt_ref,
        "lease_epoch_at_launch": lease_epoch_at_launch,
        "supervisor_status": supervisor_status,
        "evidence_ref": evidence_ref,
        "evidence_digest": evidence_digest,
        "artifact_ref_count": artifact_ref_count,
        "error_code": error_code,
    }
    return _materialize(core, _TURN_VIEW_PREFIX)


def _turn_with(turn: Mapping[str, Any], **changes: Any) -> dict[str, Any]:
    core = {key: value for key, value in turn.items() if key != "view_model_ref"}
    core.update(changes)
    return _materialize(core, _TURN_VIEW_PREFIX)


def _new_cancel(request: CancellationRequest, *, fingerprint: str, status: str) -> dict[str, Any]:
    core = {
        "type": _CANCEL_TYPE,
        "ok": True,
        "status": status,
        "cancel_id": request.cancel_id,
        "session_id": request.session_id,
        "activity_id": request.activity_id,
        "transaction_ref": request.transaction_ref,
        "operation_ref": request.operation_ref,
        "turn_index": request.turn_index,
        "requested_by_ref": request.requested_by_ref,
        "operator_gate": request.operator_gate,
        "reason_code": request.reason_code,
        "idempotency_key": request.idempotency_key,
        "request_fingerprint": fingerprint,
        "lease_id": request.lease_id,
        "lease_epoch": request.lease_epoch,
        "lease_holder_ref": request.lease_holder_ref,
        "evidence_ref": None,
        "evidence_digest": None,
        "error_code": None,
    }
    return _materialize(core, _CANCEL_VIEW_PREFIX)


def _turn_from_outcome(
    claimed_turn: Mapping[str, Any],
    outcome: SessionWorkOutcome | None,
    *,
    max_artifacts_per_turn: int,
) -> dict[str, Any]:
    if outcome is None:
        return _turn_with(
            claimed_turn,
            status=_TURN_FAILED_RETRYABLE,
            ok=False,
            error_code=_ERROR_SUPERVISOR_FAILED,
        )
    status_raw = getattr(outcome, "supervisor_status", None)
    supervisor_status = _safe_code(status_raw)
    evidence_ref_raw = getattr(outcome, "evidence_ref", None)
    evidence_ref = _safe_evidence_ref(evidence_ref_raw)
    evidence_digest_raw = getattr(outcome, "evidence_digest", None)
    evidence_digest = _safe_digest(evidence_digest_raw)
    artifact_ref_count = _safe_artifact_ref_count(getattr(outcome, "artifact_ref_count", None))
    error_code_raw = getattr(outcome, "error_code", None)
    error_code = _safe_code(error_code_raw)

    unsafe = (
        type(getattr(outcome, "ok", None)) is not bool
        or artifact_ref_count is None
        or artifact_ref_count > max_artifacts_per_turn
        or (status_raw is not None and supervisor_status is None)
        or (evidence_ref_raw is not None and evidence_ref is None)
        or (evidence_digest_raw is not None and evidence_digest is None)
        or (error_code_raw is not None and error_code is None)
    )
    if unsafe:
        return _turn_with(
            claimed_turn,
            status=_TURN_FAILED_TERMINAL,
            ok=False,
            error_code=_ERROR_SUPERVISOR_FAILED,
        )
    if error_code is not None or outcome.ok is not True:
        return _turn_with(
            claimed_turn,
            status=_TURN_FAILED_RETRYABLE,
            ok=False,
            error_code=_ERROR_SUPERVISOR_FAILED,
        )
    return _turn_with(
        claimed_turn,
        status=_TURN_COMPLETED,
        ok=True,
        supervisor_status=supervisor_status,
        evidence_ref=evidence_ref,
        evidence_digest=evidence_digest,
        artifact_ref_count=artifact_ref_count,
        error_code=None,
    )


# --------------------------------------------------------------------------- #
# Finalize drift + fakes
# --------------------------------------------------------------------------- #
def _assert_no_finalize_drift(
    resident: Mapping[str, Any] | None,
    store: SessionLifecycleStore,
    activity_id: str,
    *,
    expected_state: str,
    claimed_version: int,
    launch_epoch: int,
) -> None:
    lease = store._leases.get(activity_id)
    if (
        resident is None
        or resident["lifecycle_state"] != expected_state
        or resident["state_version"] != claimed_version
        or lease is None
        or lease.lease_epoch != launch_epoch
    ):
        if resident is not None and resident["lifecycle_state"] == expected_state:
            failed = _session_with(
                resident,
                lifecycle_state=_STATE_FAILED,
                open_turn_index=None,
                state_version=resident["state_version"] + 1,
                supervisor_status=None,
                evidence_ref=None,
                evidence_digest=None,
                error_code=_ERROR_TOCTOU,
                ok=False,
            )
            _store_session(store, failed, fingerprint=resident["request_fingerprint"])
        raise SessionLifecycleError(
            _ERROR_TOCTOU, "session drifted before lifecycle finalize"
        )


def _safe_call(work: Callable[[Any], SessionWorkOutcome], request: Any) -> SessionWorkOutcome | None:
    """Invoke an injected work fake outside the store lock, no-throw.

    A raising fake collapses to ``None`` (a stable failure); raw exception
    text never propagates into durable state.
    """

    try:
        return work(request)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Fingerprints
# --------------------------------------------------------------------------- #
def _create_fingerprint(request: SessionCreateRequest) -> str:
    return _digest_hex(
        {
            "kind": "session_create",
            "activity_id": request.activity_id,
            "transaction_ref": request.transaction_ref,
            "operation_ref": request.operation_ref,
            "session_id": request.session_id,
            "role_key": request.role_key,
            "role_file_digest": request.role_file_digest,
            "prompt_ref": request.prompt_ref,
            "context_refs": list(request.context_refs),
            "cwd_ref": request.cwd_ref,
            "allowed_roots_ref": request.allowed_roots_ref,
            "lease_id": request.lease_id,
            "lease_epoch": request.lease_epoch,
            "lease_holder_ref": request.lease_holder_ref,
            "expected_state_version": request.expected_state_version,
            "operator_gate": request.operator_gate,
            "max_turns": request.max_turns,
            "max_artifacts_per_turn": request.max_artifacts_per_turn,
        }
    )


def _turn_fingerprint(request: SessionSendRequest) -> str:
    return _digest_hex(
        {
            "kind": "session_send",
            "activity_id": request.activity_id,
            "session_id": request.session_id,
            "transaction_ref": request.transaction_ref,
            "operation_ref": request.operation_ref,
            "session_binding": request.session_binding,
            "prompt_ref": request.prompt_ref,
            "context_refs": list(request.context_refs),
            "lease_id": request.lease_id,
            "lease_epoch": request.lease_epoch,
            "lease_holder_ref": request.lease_holder_ref,
            "expected_state_version": request.expected_state_version,
            "operator_gate": request.operator_gate,
        }
    )


def _cancel_fingerprint(request: CancellationRequest) -> str:
    return _digest_hex(
        {
            "kind": "session_cancel",
            "cancel_id": request.cancel_id,
            "activity_id": request.activity_id,
            "session_id": request.session_id,
            "transaction_ref": request.transaction_ref,
            "operation_ref": request.operation_ref,
            "session_binding": request.session_binding,
            "requested_by_ref": request.requested_by_ref,
            "reason_code": request.reason_code,
            "turn_index": request.turn_index,
            "lease_id": request.lease_id,
            "lease_epoch": request.lease_epoch,
            "lease_holder_ref": request.lease_holder_ref,
            "operator_gate": request.operator_gate,
        }
    )


# --------------------------------------------------------------------------- #
# Sanitization primitives + resident validation
# --------------------------------------------------------------------------- #
def _digest_hex(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_safe_ref(value: Any) -> bool:
    return type(value) is str and _REF_RE.fullmatch(value) is not None


def _is_safe_ref_or_none(value: Any) -> bool:
    return value is None or _is_safe_ref(value)


def _is_required_safe_ref(value: Any) -> bool:
    return _is_safe_ref(value) and _state_string_is_safe(value)


def _safe_ref_value(value: Any) -> str | None:
    return value if (type(value) is str and _is_required_safe_ref(value)) else None


def _has_unsafe_marker(value: Any) -> bool:
    return type(value) is str and any(marker in value.lower() for marker in _UNSAFE_MARKERS)


def _state_string_is_safe(value: str) -> bool:
    return not _value_is_unsafe(value) and not _has_unsafe_marker(value)


def _is_int_at_least(value: Any, minimum: int) -> bool:
    return type(value) is int and value >= minimum


def _is_safe_fingerprint(value: Any) -> bool:
    return type(value) is str and _FINGERPRINT_RE.fullmatch(value) is not None


def _safe_code(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _value_is_unsafe(value) or _STABLE_CODE_RE.fullmatch(value) is None:
        return None
    return value


def _is_safe_stored_error_code(value: Any) -> bool:
    """A durable ``error_code`` is restricted to the stable stored taxonomy.

    Membership in ``_STORED_ERROR_CODES`` is stricter than the generic code
    shape and intentionally bypasses the platform-id heuristic, which
    false-positives on legitimate taxonomy codes — e.g.
    ``activity_session_toctou_conflict`` contains an ``ou_`` run. A resident
    ``error_code`` that is not exactly one of the stored taxonomy codes is
    rejected as poisoned.
    """

    return value in _STORED_ERROR_CODES


def _safe_evidence_ref(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _value_is_unsafe(value) or _EVIDENCE_REF_RE.fullmatch(value) is None:
        return None
    return value


def _safe_digest(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _SHA256_DIGEST_RE.fullmatch(value) is None:
        return None
    return value


def _safe_artifact_ref_count(value: Any) -> int | None:
    if type(value) is not int or value < 0:
        return None
    return value


def _resident_idem(
    table: Mapping[str, tuple[str, dict[str, Any]]],
    idempotency_key: str,
    validator: Callable[[Mapping[str, Any]], dict[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    existing = table.get(idempotency_key)
    if existing is None:
        return None
    fingerprint, state = existing
    if not _is_safe_fingerprint(fingerprint):
        raise _unsafe_material()
    return fingerprint, validator(state)


def _reject_unsafe_state() -> SessionLifecycleError:
    return SessionLifecycleError("activity_unsafe_material", "unsafe durable session state rejected")


def _assert_all_strings_safe(projected: Mapping[str, Any]) -> None:
    for key, value in projected.items():
        if type(value) is not str:
            continue
        if key == "error_code" and _is_safe_stored_error_code(value):
            continue
        if not _state_string_is_safe(value):
            raise _reject_unsafe_state()


def _validate_session_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    if type(state) is not dict or set(state) != _SESSION_STATE_KEYS:
        raise _reject_unsafe_state()
    projected = dict(state)
    if (
        projected["type"] != _SESSION_TYPE
        or projected["phase"] != _PHASE
        or projected["lifecycle_state"] not in _ALL_LIFECYCLE_STATES
        or type(projected["ok"]) is not bool
        or ROLE_KEY_ALLOWLIST.get(projected["role_key"]) is None
        or not _is_safe_fingerprint(projected["request_fingerprint"])
        or _safe_digest(projected["role_file_digest"]) is None
        or not projected["view_model_ref"].startswith(_SESSION_VIEW_PREFIX)
    ):
        raise _reject_unsafe_state()
    for key in (
        "session_id",
        "activity_id",
        "transaction_ref",
        "operation_ref",
        "role_key",
        "idempotency_key",
        "lease_id",
        "lease_holder_ref",
        "view_model_ref",
    ):
        if not _is_required_safe_ref(projected[key]):
            raise _reject_unsafe_state()
    if projected["session_binding"] is not None and not _is_required_safe_ref(
        projected["session_binding"]
    ):
        raise _reject_unsafe_state()
    for key, minimum in (
        ("lease_epoch", 0),
        ("state_version", 0),
        ("turn_count", 0),
        ("max_turns", 1),
        ("max_artifacts_per_turn", 0),
    ):
        if not _is_int_at_least(projected[key], minimum):
            raise _reject_unsafe_state()
    open_turn_index = projected["open_turn_index"]
    if open_turn_index is not None and not _is_int_at_least(open_turn_index, 1):
        raise _reject_unsafe_state()
    if (
        (projected["supervisor_status"] is not None and _safe_code(projected["supervisor_status"]) is None)
        or (projected["evidence_ref"] is not None and _safe_evidence_ref(projected["evidence_ref"]) is None)
        or (projected["evidence_digest"] is not None and _safe_digest(projected["evidence_digest"]) is None)
        or (projected["caller_verdict"] is not None and _safe_code(projected["caller_verdict"]) is None)
        or (
            projected["error_code"] is not None
            and not _is_safe_stored_error_code(projected["error_code"])
        )
    ):
        raise _reject_unsafe_state()
    _assert_all_strings_safe(projected)
    return projected


def _validate_turn_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    if type(state) is not dict or set(state) != _TURN_STATE_KEYS:
        raise _reject_unsafe_state()
    projected = dict(state)
    if (
        projected["type"] != _TURN_TYPE
        or projected["status"] not in _TURN_STATUSES
        or type(projected["ok"]) is not bool
        or not _is_safe_fingerprint(projected["request_fingerprint"])
        or not projected["view_model_ref"].startswith(_TURN_VIEW_PREFIX)
    ):
        raise _reject_unsafe_state()
    for key in ("session_id", "activity_id", "idempotency_key", "view_model_ref"):
        if not _is_required_safe_ref(projected[key]):
            raise _reject_unsafe_state()
    if not _is_safe_ref_or_none(projected["prompt_ref"]) or not _state_string_is_safe(
        projected["prompt_ref"] if type(projected["prompt_ref"]) is str else ""
    ):
        raise _reject_unsafe_state()
    for key, minimum in (("turn_index", 1), ("lease_epoch_at_launch", 0), ("artifact_ref_count", 0)):
        if not _is_int_at_least(projected[key], minimum):
            raise _reject_unsafe_state()
    if (
        (projected["supervisor_status"] is not None and _safe_code(projected["supervisor_status"]) is None)
        or (projected["evidence_ref"] is not None and _safe_evidence_ref(projected["evidence_ref"]) is None)
        or (projected["evidence_digest"] is not None and _safe_digest(projected["evidence_digest"]) is None)
        or (
            projected["error_code"] is not None
            and not _is_safe_stored_error_code(projected["error_code"])
        )
    ):
        raise _reject_unsafe_state()
    _assert_all_strings_safe(projected)
    return projected


def _validate_cancel_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    if type(state) is not dict or set(state) != _CANCEL_STATE_KEYS:
        raise _reject_unsafe_state()
    projected = dict(state)
    if (
        projected["type"] != _CANCEL_TYPE
        or projected["status"] not in _CANCEL_STATUSES
        or projected["ok"] is not True
        or projected["operator_gate"] is not True
        or projected["evidence_ref"] is not None
        or projected["evidence_digest"] is not None
        or not _is_safe_fingerprint(projected["request_fingerprint"])
        or not projected["view_model_ref"].startswith(_CANCEL_VIEW_PREFIX)
    ):
        raise _reject_unsafe_state()
    for key in (
        "cancel_id",
        "session_id",
        "activity_id",
        "transaction_ref",
        "operation_ref",
        "idempotency_key",
        "lease_id",
        "lease_holder_ref",
        "view_model_ref",
    ):
        if not _is_required_safe_ref(projected[key]):
            raise _reject_unsafe_state()
    if not _is_safe_ref_or_none(projected["requested_by_ref"]):
        raise _reject_unsafe_state()
    if not _is_int_at_least(projected["lease_epoch"], 0):
        raise _reject_unsafe_state()
    turn_index = projected["turn_index"]
    if turn_index is not None and not _is_int_at_least(turn_index, 1):
        raise _reject_unsafe_state()
    reason = projected["reason_code"]
    if reason is not None and _safe_code(reason) is None:
        raise _reject_unsafe_state()
    if projected["error_code"] is not None and not _is_safe_stored_error_code(
        projected["error_code"]
    ):
        raise _reject_unsafe_state()
    _assert_all_strings_safe(projected)
    return projected
