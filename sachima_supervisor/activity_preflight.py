"""Durable-state preflight gate for supervised local Activity inputs.

This module implements the next local/offline Sachima-owned gate after the
controlled dry-run evidence phase. It records only sanitized preflight state
and proves that a future local execution request has enough durable-state
preconditions to be considered later; it does **not** execute agents, start a
runtime, call platform adapters, deliver messages, or run controlled AI FLOW.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from .activity import ROLE_KEY_ALLOWLIST
from .activity_evidence import build_controlled_local_dry_run_evidence
from .local_offline import _value_is_unsafe


DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_supervised_local_activity_"
    "durable_state_preflight_implementation_no_live_no_gateway_no_real_delivery_"
    "no_real_agent_execution_no_controlled_ai_flow_execution"
)

_STATE_TYPE = "sachima.supervisor.activity_durable_state_preflight.v1"
_PHASE = "durable_state_preflight"
_STATUS = "preflight_passed"
_VIEW_MODEL_REF_PREFIX = "durable_state_preflight_view_"
_SUPPORTED_MODE = "exec_dry_run"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_REF_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_PREFLIGHT_UNSAFE_MARKERS = ("media_path", "raw_prompt", "prompt_body")
_DURABLE_STATE_KEYS = frozenset(
    {
        "type",
        "ok",
        "status",
        "phase",
        "activity_id",
        "transaction_ref",
        "operation_ref",
        "role_key",
        "mode",
        "idempotency_key",
        "prior_dry_run_evidence_digest",
        "lease_id",
        "lease_epoch",
        "lease_holder_ref",
        "state_version",
        "attempt_index",
        "attempt_count",
        "artifact_ref_count",
        "evidence_ref",
        "evidence_digest",
        "caller_verdict",
        "error_code",
        "retryable",
        "view_model_ref",
    }
)


class DurableStatePreflightError(Exception):
    """Fail-closed preflight boundary error carrying a stable error code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


@dataclass(frozen=True)
class DurableStatePreflightRequest:
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
    prior_dry_run_evidence_digest: str | None = None
    lease_id: str | None = None
    lease_epoch: int = 0
    lease_holder_ref: str | None = None
    expected_state_version: int = 0
    operator_gate: bool = False
    max_attempts: int = 1
    max_artifact_refs: int = 0
    max_evidence_bytes: int = 0


class DurableStatePreflightResult:
    def __init__(self, state: Mapping[str, Any]) -> None:
        self._state = dict(state)

    @property
    def ok(self) -> bool:
        return self._state["ok"]

    @property
    def status(self) -> str:
        return self._state["status"]

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
    def role_key(self) -> str:
        return self._state["role_key"]

    @property
    def mode(self) -> str:
        return self._state["mode"]

    @property
    def idempotency_key(self) -> str:
        return self._state["idempotency_key"]

    @property
    def prior_dry_run_evidence_digest(self) -> str:
        return self._state["prior_dry_run_evidence_digest"]

    @property
    def lease_id(self) -> str:
        return self._state["lease_id"]

    @property
    def lease_epoch(self) -> int:
        return self._state["lease_epoch"]

    @property
    def lease_holder_ref(self) -> str:
        return self._state["lease_holder_ref"]

    @property
    def state_version(self) -> int:
        return self._state["state_version"]

    @property
    def attempt_index(self) -> int:
        return self._state["attempt_index"]

    @property
    def attempt_count(self) -> int:
        return self._state["attempt_count"]

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
        return dict(self._state)


@dataclass(frozen=True)
class _LeaseRecord:
    lease_id: str | None
    lease_epoch: int
    lease_holder_ref: str | None
    state_version: int


@dataclass
class DurableStatePreflightStore:
    _by_activity: dict[str, dict[str, Any]] = field(default_factory=dict)
    _by_idempotency: dict[str, tuple[str, dict[str, Any]]] = field(
        default_factory=dict
    )
    _leases: dict[str, _LeaseRecord] = field(default_factory=dict)

    def grant_lease(
        self,
        *,
        activity_id: str,
        lease_id: str | None,
        lease_epoch: int,
        lease_holder_ref: str | None,
        state_version: int = 0,
    ) -> None:
        self._leases[activity_id] = _LeaseRecord(
            lease_id=lease_id,
            lease_epoch=lease_epoch,
            lease_holder_ref=lease_holder_ref,
            state_version=state_version,
        )

    def get_by_activity(self, activity_id: str) -> dict[str, Any] | None:
        state = self._by_activity.get(activity_id)
        return None if state is None else _validate_durable_state_projection(state)

    def get_idempotent(self, idempotency_key: str) -> tuple[str, dict[str, Any]] | None:
        existing = self._by_idempotency.get(idempotency_key)
        if existing is None:
            return None
        fingerprint, state = existing
        if not _is_safe_fingerprint(fingerprint):
            raise DurableStatePreflightError(
                "activity_unsafe_material", "unsafe durable preflight state rejected"
            )
        return fingerprint, _validate_durable_state_projection(state)

    def get_lease(self, activity_id: str) -> _LeaseRecord | None:
        return self._leases.get(activity_id)

    def put(
        self,
        *,
        activity_id: str,
        idempotency_key: str,
        fingerprint: str,
        state: dict[str, Any],
    ) -> None:
        stored = _validate_durable_state_projection(state)
        if (
            activity_id != stored["activity_id"]
            or idempotency_key != stored["idempotency_key"]
            or not _is_safe_fingerprint(fingerprint)
        ):
            raise DurableStatePreflightError(
                "activity_unsafe_material", "unsafe durable preflight state rejected"
            )
        self._by_activity[activity_id] = stored
        self._by_idempotency[idempotency_key] = (fingerprint, stored)


def run_durable_state_preflight(
    request: DurableStatePreflightRequest, store: DurableStatePreflightStore
) -> DurableStatePreflightResult:
    _check_enabled_and_approved(request)
    _check_mode(request)
    _resolve_role_key(request.role_key)
    _check_material(request)
    _check_prior_evidence_digest(request.prior_dry_run_evidence_digest)
    _check_operator_gate(request)
    _check_budgets(request)
    lease = _check_lease(request, store)
    _check_state_version(request, lease)

    fingerprint = _fingerprint(request)
    existing = store.get_idempotent(request.idempotency_key)
    if existing is not None:
        existing_fingerprint, existing_state = existing
        if existing_fingerprint != fingerprint:
            raise DurableStatePreflightError(
                "activity_idempotency_conflict",
                "idempotency key maps to an incompatible preflight",
            )
        return DurableStatePreflightResult(existing_state)

    prior_state = store.get_by_activity(request.activity_id)
    next_attempt = 1 if prior_state is None else prior_state["attempt_count"] + 1
    if next_attempt > request.max_attempts:
        raise DurableStatePreflightError(
            "activity_budget_exceeded", "preflight attempt budget exceeded"
        )

    state = _build_state(request, lease=lease, attempt_index=next_attempt)
    store.put(
        activity_id=request.activity_id,
        idempotency_key=request.idempotency_key,
        fingerprint=fingerprint,
        state=state,
    )
    return DurableStatePreflightResult(state)


def query_durable_state_preflight(
    store: DurableStatePreflightStore, *, activity_id: str
) -> DurableStatePreflightResult:
    state = store.get_by_activity(activity_id)
    if state is None:
        raise DurableStatePreflightError(
            "activity_not_found", "no durable preflight state for activity id"
        )
    return DurableStatePreflightResult(state)


def _check_enabled_and_approved(request: DurableStatePreflightRequest) -> None:
    if request.enabled is not True:
        raise DurableStatePreflightError(
            "activity_disabled", "durable-state preflight is default-off"
        )
    if request.approval_token != DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN:
        raise DurableStatePreflightError(
            "activity_approval_mismatch", "exact preflight approval token required"
        )


def _check_mode(request: DurableStatePreflightRequest) -> None:
    if request.mode != _SUPPORTED_MODE:
        raise DurableStatePreflightError(
            "activity_unsupported_mode", "preflight accepts exec_dry_run only"
        )


def _resolve_role_key(role_key: str) -> None:
    if ROLE_KEY_ALLOWLIST.get(role_key) is None:
        raise DurableStatePreflightError(
            "activity_unknown_role", "role key is not in the Activity allowlist"
        )


def _check_material(request: DurableStatePreflightRequest) -> None:
    if type(request.context_refs) is not tuple:
        raise DurableStatePreflightError(
            "activity_unsafe_material",
            "unsafe material rejected at preflight boundary",
        )
    values: list[Any] = [
        request.activity_id,
        request.transaction_ref,
        request.operation_ref,
        request.idempotency_key,
        request.prompt_ref,
        request.cwd_ref,
        request.allowed_roots_ref,
        request.lease_id,
        request.lease_holder_ref,
    ]
    values.extend(request.context_refs)
    for value in values:
        if (
            _value_is_unsafe(value)
            or _has_preflight_unsafe_marker(value)
            or not _is_safe_ref_or_none(value)
        ):
            raise DurableStatePreflightError(
                "activity_unsafe_material",
                "unsafe material rejected at preflight boundary",
            )


def _check_prior_evidence_digest(digest: str | None) -> None:
    if type(digest) is not str or _DIGEST_RE.fullmatch(digest) is None:
        raise DurableStatePreflightError(
            "activity_precondition_unmet",
            "prior dry-run evidence digest is missing or malformed",
        )
    expected = build_controlled_local_dry_run_evidence()["fixture_digest"]
    if digest != expected:
        raise DurableStatePreflightError(
            "activity_precondition_unmet",
            "prior dry-run evidence digest does not match",
        )


def _check_operator_gate(request: DurableStatePreflightRequest) -> None:
    if request.operator_gate is not True:
        raise DurableStatePreflightError(
            "activity_precondition_unmet", "operator gate is required"
        )


def _check_budgets(request: DurableStatePreflightRequest) -> None:
    if not _is_int_at_least(request.max_attempts, 1):
        raise DurableStatePreflightError(
            "activity_budget_exceeded", "invalid max_attempts budget"
        )
    if not _is_int_at_least(request.max_artifact_refs, 0):
        raise DurableStatePreflightError(
            "activity_budget_exceeded", "invalid max_artifact_refs budget"
        )
    if not _is_int_at_least(request.max_evidence_bytes, 0):
        raise DurableStatePreflightError(
            "activity_budget_exceeded", "invalid max_evidence_bytes budget"
        )


def _check_lease(
    request: DurableStatePreflightRequest, store: DurableStatePreflightStore
) -> _LeaseRecord:
    if not _is_required_safe_ref(request.lease_id) or not _is_required_safe_ref(
        request.lease_holder_ref
    ):
        raise DurableStatePreflightError(
            "activity_lease_lost", "request lease refs are invalid"
        )
    if not _is_int_at_least(request.lease_epoch, 0):
        raise DurableStatePreflightError("activity_lease_lost", "invalid lease epoch")
    lease = store.get_lease(request.activity_id)
    if lease is None:
        raise DurableStatePreflightError(
            "activity_lease_lost", "no current lease for activity"
        )
    if not _is_required_safe_ref(lease.lease_id) or not _is_required_safe_ref(
        lease.lease_holder_ref
    ):
        raise DurableStatePreflightError(
            "activity_lease_lost", "stored lease refs are invalid"
        )
    if not _is_int_at_least(lease.lease_epoch, 0):
        raise DurableStatePreflightError(
            "activity_lease_lost", "stored lease epoch is invalid"
        )
    if request.lease_epoch < lease.lease_epoch:
        raise DurableStatePreflightError(
            "activity_stale_state", "lease epoch is stale"
        )
    if (
        request.lease_id != lease.lease_id
        or request.lease_epoch != lease.lease_epoch
        or request.lease_holder_ref != lease.lease_holder_ref
    ):
        raise DurableStatePreflightError(
            "activity_lease_lost", "caller no longer owns the lease"
        )
    return lease


def _check_state_version(
    request: DurableStatePreflightRequest, lease: _LeaseRecord
) -> None:
    if not _is_int_at_least(request.expected_state_version, 0):
        raise DurableStatePreflightError(
            "activity_toctou_conflict", "invalid expected state version"
        )
    if not _is_int_at_least(lease.state_version, 0):
        raise DurableStatePreflightError(
            "activity_toctou_conflict", "stored state version is invalid"
        )
    if request.expected_state_version != lease.state_version:
        raise DurableStatePreflightError(
            "activity_toctou_conflict", "state version drifted"
        )


def _build_state(
    request: DurableStatePreflightRequest,
    *,
    lease: _LeaseRecord,
    attempt_index: int,
) -> dict[str, Any]:
    core: dict[str, Any] = {
        "type": _STATE_TYPE,
        "ok": True,
        "status": _STATUS,
        "phase": _PHASE,
        "activity_id": request.activity_id,
        "transaction_ref": request.transaction_ref,
        "operation_ref": request.operation_ref,
        "role_key": request.role_key,
        "mode": request.mode,
        "idempotency_key": request.idempotency_key,
        "prior_dry_run_evidence_digest": request.prior_dry_run_evidence_digest,
        "lease_id": lease.lease_id,
        "lease_epoch": lease.lease_epoch,
        "lease_holder_ref": lease.lease_holder_ref,
        "state_version": lease.state_version,
        "attempt_index": attempt_index,
        "attempt_count": attempt_index,
        "artifact_ref_count": 0,
        "evidence_ref": None,
        "evidence_digest": None,
        "caller_verdict": None,
        "error_code": None,
        "retryable": False,
    }
    view_model_ref = _VIEW_MODEL_REF_PREFIX + _digest_hex(core)[:16]
    return {**core, "view_model_ref": view_model_ref}


def _fingerprint(request: DurableStatePreflightRequest) -> str:
    role_file = ROLE_KEY_ALLOWLIST[request.role_key]
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
        "prior_dry_run_evidence_digest": request.prior_dry_run_evidence_digest,
        "lease_id": request.lease_id,
        "lease_epoch": request.lease_epoch,
        "lease_holder_ref": request.lease_holder_ref,
        "expected_state_version": request.expected_state_version,
        "operator_gate": request.operator_gate,
        "max_attempts": request.max_attempts,
        "max_artifact_refs": request.max_artifact_refs,
        "max_evidence_bytes": request.max_evidence_bytes,
    }
    return _digest_hex(payload)


def _validate_durable_state_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    if type(state) is not dict or set(state) != _DURABLE_STATE_KEYS:
        raise DurableStatePreflightError(
            "activity_unsafe_material", "unsafe durable preflight state rejected"
        )
    projected = dict(state)
    if (
        projected["type"] != _STATE_TYPE
        or projected["ok"] is not True
        or projected["status"] != _STATUS
        or projected["phase"] != _PHASE
        or projected["mode"] != _SUPPORTED_MODE
        or projected["retryable"] is not False
    ):
        raise DurableStatePreflightError(
            "activity_unsafe_material", "unsafe durable preflight state rejected"
        )
    safe_ref_keys = (
        "activity_id",
        "transaction_ref",
        "operation_ref",
        "role_key",
        "idempotency_key",
        "lease_id",
        "lease_holder_ref",
        "view_model_ref",
    )
    if any(not _is_required_safe_ref(projected[key]) for key in safe_ref_keys):
        raise DurableStatePreflightError(
            "activity_unsafe_material", "unsafe durable preflight state rejected"
        )
    if ROLE_KEY_ALLOWLIST.get(projected["role_key"]) is None:
        raise DurableStatePreflightError(
            "activity_unsafe_material", "unsafe durable preflight state rejected"
        )
    digest = projected["prior_dry_run_evidence_digest"]
    if (
        type(digest) is not str
        or _DIGEST_RE.fullmatch(digest) is None
        or digest != build_controlled_local_dry_run_evidence()["fixture_digest"]
        or not _state_string_is_safe(digest)
    ):
        raise DurableStatePreflightError(
            "activity_unsafe_material", "unsafe durable preflight state rejected"
        )
    int_minimums = {
        "lease_epoch": 0,
        "state_version": 0,
        "attempt_index": 1,
        "attempt_count": 1,
        "artifact_ref_count": 0,
    }
    if any(
        not _is_int_at_least(projected[key], minimum)
        for key, minimum in int_minimums.items()
    ):
        raise DurableStatePreflightError(
            "activity_unsafe_material", "unsafe durable preflight state rejected"
        )
    if (
        projected["attempt_count"] != projected["attempt_index"]
        or projected["artifact_ref_count"] != 0
        or not projected["view_model_ref"].startswith(_VIEW_MODEL_REF_PREFIX)
    ):
        raise DurableStatePreflightError(
            "activity_unsafe_material", "unsafe durable preflight state rejected"
        )
    if any(
        projected[key] is not None
        for key in ("evidence_ref", "evidence_digest", "caller_verdict", "error_code")
    ):
        raise DurableStatePreflightError(
            "activity_unsafe_material", "unsafe durable preflight state rejected"
        )
    if any(
        type(value) is str and not _state_string_is_safe(value)
        for value in projected.values()
    ):
        raise DurableStatePreflightError(
            "activity_unsafe_material", "unsafe durable preflight state rejected"
        )
    return projected


def _digest_hex(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_required_safe_ref(value: Any) -> bool:
    return _is_safe_ref(value) and _state_string_is_safe(value)


def _is_safe_fingerprint(value: Any) -> bool:
    return type(value) is str and _FINGERPRINT_RE.fullmatch(value) is not None


def _is_safe_ref(value: Any) -> bool:
    return type(value) is str and _REF_RE.fullmatch(value) is not None


def _is_safe_ref_or_none(value: Any) -> bool:
    if value is None:
        return True
    return _is_safe_ref(value)


def _has_preflight_unsafe_marker(value: Any) -> bool:
    return type(value) is str and any(
        marker in value.lower() for marker in _PREFLIGHT_UNSAFE_MARKERS
    )


def _state_string_is_safe(value: str) -> bool:
    return not _value_is_unsafe(value) and not _has_preflight_unsafe_marker(value)


def _is_int_at_least(value: Any, minimum: int) -> bool:
    return type(value) is int and value >= minimum
