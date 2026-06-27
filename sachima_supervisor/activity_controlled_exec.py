"""Controlled local one-shot exec slice for the supervised local Activity line.

This is the Phase C first behavior-bearing slice of the agent-run-supervisor ×
Sachima controlled local agent execution mainline (PRD 2026-06-12). It adds a
caller-owned, default-off wrapper that can request a single controlled local
``exec`` through the already-merged ``sachima_supervisor.local_offline`` seam,
guarded by every durable precondition from the durable-runtime design packet
and the PRD review convergence.

Boundaries enforced here (local/offline only):

  * Default-off with an *exact* Phase C approval token; a disabled or
    mismatched gate fails closed with a stable error code before any work.
  * Only the explicit ``exec_controlled`` mode is accepted. ``exec_dry_run``
    keeps its existing path; seam-level ``exec``, session, cancel, live, and
    delivery-shaped modes are rejected here.
  * Only read-only one-shot reviewer roles are runnable: the Codex primary
    reviewer (``adapter_agent=codex``) and the Claude Code read-only reviewer
    (``adapter_agent=claude``). Each role key pins exactly one adapter via
    ``CONTROLLED_EXEC_ROLE_ADAPTER_AGENT``, so a role file can never run under
    the wrong adapter. The write-capable Claude architect / main-programmer /
    docs roles and the Codex blocker-only reviewer are documented future
    mainline keys and fail closed.
  * Pinned local runner provenance: the allowlisted role file must declare a
    non-null absolute local ``acpx_binary`` and the request must carry the
    exact sha256 digest of that role file. A null binary (which would fall
    back to a network-fetching package-runner invocation inside the
    supervisor library) can never pass, so "local/offline" claims stay
    truthful. The committed repo role config keeps ``acpx_binary`` null and is
    therefore not runnable by construction until an operator pins a verified
    local executable.
  * A durable-state preflight record (same transaction/operation, matching
    lease id/epoch/holder and state version), the exact controlled dry-run
    evidence digest, and an exact operator gate are all required preconditions.
  * An atomic pre-launch claim (check-and-set) is written *before* the
    supervisor boundary is invoked. The first-slice claim store serializes
    the whole check-and-set under a single in-process lock, so concurrent
    identical starts resolve to exactly one acquisition and concurrent
    conflicting starts fail closed before any second launch. Identical
    replays of an in-progress or terminal claim return the resident
    sanitized projection and never start a second run; a crashed
    in-progress claim is never auto-relaunched. The file-backed adapter adds
    the approved local cross-process persistence layer for this same CAS
    contract.
  * Only the public ``invoke_local_offline_supervisor`` boundary (or an
    injected equivalent in tests) is ever called. This module never spawns a
    child process, agent CLI, shell, container, service, Gateway, or IM
    delivery surface. By default the seam request carries claim-check refs
    only with a ``None`` prompt, and the caller boundary inside the
    supervisor library fails closed on an empty exec prompt — so no agent
    run can start from the default path. A deterministic prompt may only
    enter through an explicitly injected ``prompt_materializer`` (the Phase D
    smoke prerequisite seam): it runs after the acquired pre-launch claim,
    its output is screened and bounded, it lives only in the in-memory seam
    request, and a failed/unsafe materialization fails closed with no
    supervisor invocation. Raw prompt text never enters durable claim state,
    fingerprints, or query projections. Running a real smoke remains a
    later, separately approved phase.
  * ``business_verdict`` stays ``None`` and caller-owned. It is never
    inferred from exit codes or supervisor status, and a lower layer that
    reports one is collapsed to a stable terminal failure.
  * Durable claim state and query projections carry only stable codes,
    caller-owned refs, counts, and digests. Raw prompt/context, model output,
    platform-private ids, card/media material, tool logs, raw artifact or
    evidence paths, secrets, and raw exception text never enter them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from .activity_evidence import build_controlled_local_dry_run_evidence
from .activity_preflight import (
    DurableStatePreflightError,
    DurableStatePreflightStore,
    query_durable_state_preflight,
)
from .local_offline import (
    IMPLEMENTATION_APPROVAL_TOKEN as LOCAL_OFFLINE_APPROVAL_TOKEN,
    LocalOfflineSupervisorOutcome,
    LocalOfflineSupervisorRequest,
    _value_is_unsafe,
    invoke_local_offline_supervisor,
)

# --------------------------------------------------------------------------- #
# Approval token + allowlists
# --------------------------------------------------------------------------- #
#: Exact approval token required to enable the Phase C controlled local
#: one-shot exec slice. Matches the user-approved scope: pinned local acpx,
#: read-only Codex primary reviewer, one-shot exec only.
CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_controlled_local_agent_execution_"
    "first_slice_one_shot_exec_pinned_local_acpx_read_only_codex_primary_reviewer_"
    "no_live_no_gateway_no_real_delivery_no_satine_no_write_roles_no_persistent_sessions"
)

#: The single caller-facing controlled mode. Deliberately distinct from the
#: seam's ``exec`` and from the dry-run wrapper's ``exec_dry_run`` so the
#: controlled real-exec line can never be reached by overloading older modes.
CONTROLLED_EXEC_MODE = "exec_controlled"
CONTROLLED_EXEC_MODES: frozenset[str] = frozenset({CONTROLLED_EXEC_MODE})

#: Runnable role allowlist. Values are role-config refs relative to the role
#: root (default: this package directory). The read-only Codex primary reviewer
#: (Phase C) and the read-only Claude Code reviewer (WP1a) are the only runnable
#: roles; both stay read/search-only one-shot ``exec`` and are committed
#: null-binary (non-runnable by construction until an operator pins a verified
#: local acpx).
CONTROLLED_EXEC_ROLE_ALLOWLIST: Mapping[str, str] = {
    "sachima.codex.primary_reviewer": "roles/codex_primary_reviewer_exec_controlled_v1.json",
    "sachima.claude.read_only_reviewer": "roles/claude_code_read_only_reviewer_v1.json",
}

#: Per-role required adapter agent. Each runnable role pins exactly one adapter
#: so a role file can never run under the wrong one: the Codex primary reviewer
#: must declare ``adapter_agent=codex`` and the Claude Code read-only reviewer
#: ``adapter_agent=claude``. The map is kept in lockstep with the runnable
#: allowlist (same key set) and disjoint from the future role keys.
CONTROLLED_EXEC_ROLE_ADAPTER_AGENT: Mapping[str, str] = {
    "sachima.codex.primary_reviewer": "codex",
    "sachima.claude.read_only_reviewer": "claude",
}

#: Documented future mainline role keys (per the PRD role map). They are NOT
#: runnable in this slice and fail closed like any unknown role; each needs a
#: separate approval and, for write-capable Claude roles, a separate gate.
CONTROLLED_EXEC_FUTURE_ROLE_KEYS: frozenset[str] = frozenset(
    {
        "sachima.claude.architect",
        "sachima.claude.main_programmer",
        "sachima.claude.docs_engineer",
        "sachima.codex.blocker_only_reviewer",
    }
)

#: Seam-level mode used for the single controlled one-shot exec request.
_SEAM_MODE = "exec"

_STATE_TYPE = "sachima.supervisor.controlled_local_exec_claim.v1"
_PHASE = "controlled_exec"
_APPROVAL_REF = "controlled_local_exec_approval_v1"
_VIEW_MODEL_REF_PREFIX = "controlled_local_exec_view_"
_PREFLIGHT_VIEW_REF_PREFIX = "durable_state_preflight_view_"

_STATUS_CLAIMED = "claimed_in_progress"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED_RETRYABLE = "failed_retryable"
_STATUS_FAILED_TERMINAL = "failed_terminal"
_TERMINAL_STATUSES = frozenset(
    {_STATUS_COMPLETED, _STATUS_FAILED_RETRYABLE, _STATUS_FAILED_TERMINAL}
)
_CLAIM_STATUSES = frozenset({_STATUS_CLAIMED, *_TERMINAL_STATUSES})
#: The only stable error codes a failed claim state may carry. Lower-layer
#: failures collapse to ``activity_supervisor_failed``; a failed/unsafe prompt
#: materialization collapses to ``activity_prompt_materialization_failed``
#: (always terminal, never a supervisor invocation).
_ERROR_SUPERVISOR_FAILED = "activity_supervisor_failed"
_ERROR_PROMPT_MATERIALIZATION_FAILED = "activity_prompt_materialization_failed"
_FAILURE_COLLAPSE_CODES = frozenset(
    {_ERROR_SUPERVISOR_FAILED, _ERROR_PROMPT_MATERIALIZATION_FAILED}
)

_REQUIRED_RUNNER_TYPE = "acpx"
_REQUIRED_ACPX_VERSION = "0.10.0"
_REQUIRED_ROLE_SCHEMA_VERSION = 1
#: Package-runner basename that implies a network fetch; never a pinned local
#: binary.
_FORBIDDEN_RUNNER_BASENAME = "npx"
#: Fetch-shaped package runners and shell/launcher basenames that can never be
#: an operator-pinned local acpx executable. Any of these as the candidate
#: binary basename fails provenance closed before the injected probe runs.
FORBIDDEN_RUNNER_BASENAMES: frozenset[str] = frozenset(
    {
        "npx",
        "npm",
        "pnpm",
        "yarn",
        "bunx",
        "bun",
        "corepack",
        "sh",
        "bash",
        "zsh",
        "dash",
        "ksh",
        "fish",
        "env",
        "node",
    }
)
#: Sanitized single-line probe text only: bounded, printable, no whitespace
#: beyond plain spaces, so raw stderr/exception material can never pass.
_ACPX_PROBE_TEXT_MAX_CHARS = 256
_SAFE_PROBE_TEXT_RE = re.compile(r"^[A-Za-z0-9 ._+:/()-]{1,256}$")
#: Characters that would extend a version token if adjacent to it. The pinned
#: version must stand alone in the probe text: ``0.10.0`` inside ``10.10.0``,
#: ``0.10.0-dev``, ``0.10.0rc1``, or ``0.10.0+build.5`` is a different version
#: and never satisfies the pin.
_VERSION_TOKEN_BOUNDARY_CLASS = r"[A-Za-z0-9._+-]"


def _is_forbidden_runner_basename(basename: str) -> bool:
    lowered = basename.lower()
    return lowered in FORBIDDEN_RUNNER_BASENAMES or lowered.startswith(
        _FORBIDDEN_RUNNER_BASENAME
    )


def _probe_text_has_exact_version(probe_text: str, expected_version: str) -> bool:
    pattern = (
        r"(?<!" + _VERSION_TOKEN_BOUNDARY_CLASS + r")"
        + re.escape(expected_version)
        + r"(?!" + _VERSION_TOKEN_BOUNDARY_CLASS + r")"
    )
    return re.search(pattern, probe_text) is not None


#: Upper bound for a materialized deterministic smoke prompt. Anything larger
#: is treated as unsafe material and fails closed.
_MAX_MATERIALIZED_PROMPT_CHARS = 4096
_READ_ONLY_TRUE_PERMISSIONS = ("read", "search")
_READ_ONLY_FALSE_PERMISSIONS = (
    "write",
    "execute",
    "terminal",
    "delete",
    "move",
    "fetch",
    "switch_mode",
    "other",
)

_STABLE_CODE_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")
_EVIDENCE_REF_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,127}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_REF_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_EXEC_UNSAFE_MARKERS = ("media_path", "raw_prompt", "prompt_body")

_DEFAULT_ROLE_ROOT = Path(__file__).resolve().parent

_CLAIM_STATE_KEYS = frozenset(
    {
        "type",
        "ok",
        "status",
        "mode",
        "phase",
        "activity_id",
        "transaction_ref",
        "operation_ref",
        "role_key",
        "idempotency_key",
        "role_file_digest",
        "prior_dry_run_evidence_digest",
        "preflight_view_ref",
        "approval_ref",
        "lease_id",
        "lease_epoch",
        "lease_holder_ref",
        "state_version",
        "attempt_index",
        "attempt_count",
        "supervisor_status",
        "artifact_ref_count",
        "evidence_ref",
        "evidence_digest",
        "business_verdict",
        "caller_verdict",
        "error_code",
        "retryable",
        "view_model_ref",
    }
)


# --------------------------------------------------------------------------- #
# Public request / result / error / store
# --------------------------------------------------------------------------- #
class ControlledLocalExecError(Exception):
    """Fail-closed controlled-exec boundary error carrying a stable code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


@dataclass(frozen=True)
class ControlledLocalExecRequest:
    """Caller-owned controlled local one-shot exec request.

    Inputs are claim-check refs, digests, and caller-owned ids — never raw
    prompt/context, platform ids, raw role JSON, or arbitrary paths.
    ``enabled`` defaults to ``False`` and ``approval_token`` to ``""`` so the
    slice is default-off by construction.
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
    role_file_digest: str | None = None
    prior_dry_run_evidence_digest: str | None = None
    preflight_activity_id: str | None = None
    lease_id: str | None = None
    lease_epoch: int = 0
    lease_holder_ref: str | None = None
    expected_state_version: int = 0
    operator_gate: bool = False


class ControlledLocalExecResult:
    """Sanitized, read-only view over a durable controlled-exec claim state."""

    def __init__(self, state: Mapping[str, Any]) -> None:
        self._state: dict[str, Any] = dict(state)

    @property
    def ok(self) -> bool:
        return self._state["ok"]

    @property
    def status(self) -> str:
        return self._state["status"]

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
    def role_key(self) -> str:
        return self._state["role_key"]

    @property
    def idempotency_key(self) -> str:
        return self._state["idempotency_key"]

    @property
    def role_file_digest(self) -> str:
        return self._state["role_file_digest"]

    @property
    def prior_dry_run_evidence_digest(self) -> str:
        return self._state["prior_dry_run_evidence_digest"]

    @property
    def preflight_view_ref(self) -> str:
        return self._state["preflight_view_ref"]

    @property
    def approval_ref(self) -> str:
        return self._state["approval_ref"]

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
    def supervisor_status(self) -> str | None:
        return self._state["supervisor_status"]

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
    def business_verdict(self) -> None:
        return self._state["business_verdict"]

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
        """Return a copy of the sanitized durable claim state."""

        return dict(self._state)


@dataclass
class ControlledLocalExecClaimStore:
    """Lock-guarded in-process claim store keyed by activity and idempotency key.

    ``claim`` is the single atomic pre-launch check-and-set boundary: it either
    acquires a fresh ``claimed_in_progress`` claim, replays the resident state
    for an identical fingerprint, or fails closed — all before any launch.
    Every check-and-set critical section (claim, finalize, reads) is serialized
    under one in-process mutex, so concurrent identical starts resolve to
    exactly one acquisition and concurrent conflicting starts fail closed.
    Resident state and fingerprints are revalidated on every read so malicious
    resident material can never be projected. This locked store remains the
    in-process CAS; ``FileControlledLocalExecClaimStore`` below provides the
    same contract with local cross-process persistence.
    """

    _by_activity: dict[str, dict[str, Any]] = field(default_factory=dict)
    _by_idempotency: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)
    #: Reentrant so ``claim``/``finalize`` can reuse ``get_idempotent`` inside
    #: their own critical sections.
    _lock: threading.RLock = field(
        default_factory=threading.RLock, repr=False, compare=False
    )

    def get_by_activity(self, activity_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._by_activity.get(activity_id)
            return None if state is None else _validate_claim_state_projection(state)

    def get_idempotent(self, idempotency_key: str) -> tuple[str, dict[str, Any]] | None:
        with self._lock:
            existing = self._by_idempotency.get(idempotency_key)
            if existing is None:
                return None
            fingerprint, state = existing
            if not _is_safe_fingerprint(fingerprint):
                raise ControlledLocalExecError(
                    "activity_unsafe_material", "unsafe resident claim fingerprint rejected"
                )
            return fingerprint, _validate_claim_state_projection(state)

    def claim(
        self,
        *,
        activity_id: str,
        idempotency_key: str,
        fingerprint: str,
        state: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Atomic pre-launch claim. Returns ``(disposition, state)``.

        ``disposition`` is ``"acquired"`` for a fresh claim or ``"replayed"``
        when an identical request already holds an in-progress or terminal
        claim. A same-key/different-fingerprint replay and a same-activity/
        different-key request both fail closed before any launch. The whole
        read/check/write sequence holds the store mutex, so at most one of any
        set of concurrent callers can ever acquire.
        """

        if not _is_safe_fingerprint(fingerprint):
            raise ControlledLocalExecError(
                "activity_unsafe_material", "unsafe claim fingerprint rejected"
            )
        with self._lock:
            existing = self.get_idempotent(idempotency_key)
            if existing is not None:
                existing_fingerprint, existing_state = existing
                if existing_fingerprint != fingerprint:
                    raise ControlledLocalExecError(
                        "activity_idempotency_conflict",
                        "idempotency key maps to an incompatible controlled exec request",
                    )
                return "replayed", existing_state
            if activity_id in self._by_activity:
                raise ControlledLocalExecError(
                    "activity_claim_conflict",
                    "activity is already claimed under a different idempotency key",
                )
            stored = _validate_claim_state_projection(state)
            if (
                stored["status"] != _STATUS_CLAIMED
                or stored["activity_id"] != activity_id
                or stored["idempotency_key"] != idempotency_key
            ):
                raise ControlledLocalExecError(
                    "activity_unsafe_material", "unsafe claim state rejected"
                )
            self._by_activity[activity_id] = stored
            self._by_idempotency[idempotency_key] = (fingerprint, stored)
            return "acquired", stored

    def finalize(
        self,
        *,
        activity_id: str,
        idempotency_key: str,
        fingerprint: str,
        state: dict[str, Any],
    ) -> None:
        """Transition an in-progress claim to a terminal sanitized state.

        Holds the same store mutex as ``claim`` for the whole match-and-write
        sequence.
        """

        if not _is_safe_fingerprint(fingerprint):
            raise ControlledLocalExecError(
                "activity_unsafe_material", "unsafe claim fingerprint rejected"
            )
        with self._lock:
            existing = self.get_idempotent(idempotency_key)
            if existing is None:
                raise ControlledLocalExecError(
                    "activity_claim_conflict", "no resident claim to finalize"
                )
            existing_fingerprint, existing_state = existing
            if (
                existing_fingerprint != fingerprint
                or existing_state["status"] != _STATUS_CLAIMED
                or existing_state["activity_id"] != activity_id
            ):
                raise ControlledLocalExecError(
                    "activity_claim_conflict", "resident claim does not match this attempt"
                )
            stored = _validate_claim_state_projection(state)
            if (
                stored["status"] not in _TERMINAL_STATUSES
                or stored["activity_id"] != activity_id
                or stored["idempotency_key"] != idempotency_key
            ):
                raise ControlledLocalExecError(
                    "activity_unsafe_material", "unsafe terminal claim state rejected"
                )
            self._by_activity[activity_id] = stored
            self._by_idempotency[idempotency_key] = (fingerprint, stored)


class FileControlledLocalExecClaimStore:
    """File-backed controlled-exec claim store with cross-process locking.

    The persisted file contains only the same sanitized claim projections as the
    in-process store plus idempotency fingerprints. Every read revalidates the
    full JSON payload before projecting state, so tampering or unsafe resident
    material fails closed instead of leaking raw content. Writes happen while an
    OS file lock is held and commit through an atomic ``os.replace``.
    """

    _STORE_TYPE = "sachima.supervisor.controlled_local_exec_claim_store.v1"
    _SCHEMA_VERSION = 1
    _TOP_LEVEL_KEYS = frozenset(
        {"type", "schema_version", "by_activity", "by_idempotency"}
    )
    _IDEMPOTENCY_ENTRY_KEYS = frozenset({"fingerprint", "activity_id"})

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock_path = self._path.with_name(self._path.name + ".lock")
        self._thread_lock = threading.RLock()

    def get_by_activity(self, activity_id: str) -> dict[str, Any] | None:
        with self._locked_payload(write=False) as payload:
            state = payload["by_activity"].get(activity_id)
            return None if state is None else _validate_claim_state_projection(state)

    def get_idempotent(self, idempotency_key: str) -> tuple[str, dict[str, Any]] | None:
        with self._locked_payload(write=False) as payload:
            return self._get_idempotent_from_payload(payload, idempotency_key)

    def claim(
        self,
        *,
        activity_id: str,
        idempotency_key: str,
        fingerprint: str,
        state: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if not _is_safe_fingerprint(fingerprint):
            raise ControlledLocalExecError(
                "activity_unsafe_material", "unsafe claim fingerprint rejected"
            )
        with self._locked_payload(write=True) as payload:
            existing = self._get_idempotent_from_payload(payload, idempotency_key)
            if existing is not None:
                existing_fingerprint, existing_state = existing
                if existing_fingerprint != fingerprint:
                    raise ControlledLocalExecError(
                        "activity_idempotency_conflict",
                        "idempotency key maps to an incompatible controlled exec request",
                    )
                return "replayed", existing_state
            if activity_id in payload["by_activity"]:
                raise ControlledLocalExecError(
                    "activity_claim_conflict",
                    "activity is already claimed under a different idempotency key",
                )
            stored = _validate_claim_state_projection(state)
            if (
                stored["status"] != _STATUS_CLAIMED
                or stored["activity_id"] != activity_id
                or stored["idempotency_key"] != idempotency_key
            ):
                raise ControlledLocalExecError(
                    "activity_unsafe_material", "unsafe claim state rejected"
                )
            payload["by_activity"][activity_id] = stored
            payload["by_idempotency"][idempotency_key] = {
                "fingerprint": fingerprint,
                "activity_id": activity_id,
            }
            return "acquired", stored

    def finalize(
        self,
        *,
        activity_id: str,
        idempotency_key: str,
        fingerprint: str,
        state: dict[str, Any],
    ) -> None:
        if not _is_safe_fingerprint(fingerprint):
            raise ControlledLocalExecError(
                "activity_unsafe_material", "unsafe claim fingerprint rejected"
            )
        with self._locked_payload(write=True) as payload:
            existing = self._get_idempotent_from_payload(payload, idempotency_key)
            if existing is None:
                raise ControlledLocalExecError(
                    "activity_claim_conflict", "no resident claim to finalize"
                )
            existing_fingerprint, existing_state = existing
            if (
                existing_fingerprint != fingerprint
                or existing_state["status"] != _STATUS_CLAIMED
                or existing_state["activity_id"] != activity_id
            ):
                raise ControlledLocalExecError(
                    "activity_claim_conflict", "resident claim does not match this attempt"
                )
            stored = _validate_claim_state_projection(state)
            if (
                stored["status"] not in _TERMINAL_STATUSES
                or stored["activity_id"] != activity_id
                or stored["idempotency_key"] != idempotency_key
            ):
                raise ControlledLocalExecError(
                    "activity_unsafe_material", "unsafe terminal claim state rejected"
                )
            payload["by_activity"][activity_id] = stored
            payload["by_idempotency"][idempotency_key] = {
                "fingerprint": fingerprint,
                "activity_id": activity_id,
            }

    class _LockedPayload:
        def __init__(self, owner: FileControlledLocalExecClaimStore, *, write: bool) -> None:
            self._owner = owner
            self._write = write
            self._lock_file: Any = None
            self.payload: dict[str, Any] | None = None

        def __enter__(self) -> dict[str, Any]:
            owner = self._owner
            owner._path.parent.mkdir(parents=True, exist_ok=True)
            owner._thread_lock.acquire()
            try:
                self._lock_file = owner._lock_path.open("a+b")
                owner._lock_exclusive(self._lock_file)
                self.payload = owner._read_payload_unlocked()
                return self.payload
            except Exception:
                owner._thread_lock.release()
                if self._lock_file is not None:
                    self._lock_file.close()
                raise

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            try:
                if exc_type is None and self._write and self.payload is not None:
                    self._owner._write_payload_unlocked(self.payload)
            finally:
                if self._lock_file is not None:
                    self._owner._unlock(self._lock_file)
                    self._lock_file.close()
                self._owner._thread_lock.release()

    @staticmethod
    def _load_fcntl() -> Any:
        try:
            import fcntl as fcntl_module
        except ModuleNotFoundError:
            raise ControlledLocalExecError(
                "activity_file_lock_unavailable",
                "file-backed claim store requires platform file locking",
            ) from None
        return fcntl_module

    @classmethod
    def _lock_exclusive(cls, lock_file: Any) -> None:
        fcntl_module = cls._load_fcntl()
        fcntl_module.flock(lock_file.fileno(), fcntl_module.LOCK_EX)

    @classmethod
    def _unlock(cls, lock_file: Any) -> None:
        try:
            fcntl_module = cls._load_fcntl()
        except ControlledLocalExecError:
            return
        fcntl_module.flock(lock_file.fileno(), fcntl_module.LOCK_UN)

    def _locked_payload(self, *, write: bool) -> _LockedPayload:
        return self._LockedPayload(self, write=write)

    @classmethod
    def _empty_payload(cls) -> dict[str, Any]:
        return {
            "type": cls._STORE_TYPE,
            "schema_version": cls._SCHEMA_VERSION,
            "by_activity": {},
            "by_idempotency": {},
        }

    def _read_payload_unlocked(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._empty_payload()
        try:
            raw = self._path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, UnicodeDecodeError, ValueError):
            raise _reject_unsafe_state() from None
        return self._validate_payload(payload)

    def _write_payload_unlocked(self, payload: Mapping[str, Any]) -> None:
        canonical = self._validate_payload(payload)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                prefix=self._path.name + ".",
                suffix=".tmp",
                dir=str(self._path.parent),
                text=True,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(canonical, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self._path)
            tmp_path = None
            self._fsync_parent_dir()
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except FileNotFoundError:
                    pass

    def _fsync_parent_dir(self) -> None:
        try:
            fd = os.open(self._path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _get_idempotent_from_payload(
        self, payload: Mapping[str, Any], idempotency_key: str
    ) -> tuple[str, dict[str, Any]] | None:
        entry = payload["by_idempotency"].get(idempotency_key)
        if entry is None:
            return None
        if type(entry) is not dict or set(entry) != self._IDEMPOTENCY_ENTRY_KEYS:
            raise _reject_unsafe_state()
        fingerprint = entry["fingerprint"]
        activity_id = entry["activity_id"]
        if not _is_safe_fingerprint(fingerprint) or not _is_required_safe_ref(activity_id):
            raise _reject_unsafe_state()
        state = payload["by_activity"].get(activity_id)
        if state is None:
            raise _reject_unsafe_state()
        projected = _validate_claim_state_projection(state)
        if projected["idempotency_key"] != idempotency_key:
            raise _reject_unsafe_state()
        return fingerprint, projected

    @classmethod
    def _validate_payload(cls, payload: Mapping[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != cls._TOP_LEVEL_KEYS:
            raise _reject_unsafe_state()
        if (
            payload["type"] != cls._STORE_TYPE
            or payload["schema_version"] != cls._SCHEMA_VERSION
            or type(payload["by_activity"]) is not dict
            or type(payload["by_idempotency"]) is not dict
        ):
            raise _reject_unsafe_state()
        by_activity: dict[str, dict[str, Any]] = {}
        for activity_id, state in payload["by_activity"].items():
            if not _is_required_safe_ref(activity_id):
                raise _reject_unsafe_state()
            projected = _validate_claim_state_projection(state)
            if projected["activity_id"] != activity_id:
                raise _reject_unsafe_state()
            by_activity[activity_id] = projected
        by_idempotency: dict[str, dict[str, str]] = {}
        referenced_activities: set[str] = set()
        for idempotency_key, entry in payload["by_idempotency"].items():
            if not _is_required_safe_ref(idempotency_key):
                raise _reject_unsafe_state()
            if type(entry) is not dict or set(entry) != cls._IDEMPOTENCY_ENTRY_KEYS:
                raise _reject_unsafe_state()
            fingerprint = entry["fingerprint"]
            activity_id = entry["activity_id"]
            if not _is_safe_fingerprint(fingerprint) or not _is_required_safe_ref(
                activity_id
            ):
                raise _reject_unsafe_state()
            state = by_activity.get(activity_id)
            if state is None or state["idempotency_key"] != idempotency_key:
                raise _reject_unsafe_state()
            referenced_activities.add(activity_id)
            by_idempotency[idempotency_key] = {
                "fingerprint": fingerprint,
                "activity_id": activity_id,
            }
        if set(by_activity) != referenced_activities:
            raise _reject_unsafe_state()
        return {
            "type": cls._STORE_TYPE,
            "schema_version": cls._SCHEMA_VERSION,
            "by_activity": by_activity,
            "by_idempotency": by_idempotency,
        }


# --------------------------------------------------------------------------- #
# Boundary validation
# --------------------------------------------------------------------------- #
def _check_enabled_and_approved(request: ControlledLocalExecRequest) -> None:
    if request.enabled is not True:
        raise ControlledLocalExecError(
            "activity_disabled", "controlled local exec is default-off"
        )
    if request.approval_token != CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN:
        raise ControlledLocalExecError(
            "activity_approval_mismatch",
            "exact controlled local exec approval token required",
        )


def _check_mode(request: ControlledLocalExecRequest) -> None:
    if request.mode not in CONTROLLED_EXEC_MODES:
        raise ControlledLocalExecError(
            "activity_unsupported_mode",
            "controlled local exec accepts exec_controlled only",
        )


def _resolve_role_file_ref(role_key: str) -> str:
    role_file_ref = CONTROLLED_EXEC_ROLE_ALLOWLIST.get(role_key)
    if role_file_ref is None:
        raise ControlledLocalExecError(
            "activity_unknown_role",
            "role key is not runnable in the controlled exec first slice",
        )
    return role_file_ref


def _check_material(request: ControlledLocalExecRequest) -> None:
    if type(request.context_refs) is not tuple:
        raise ControlledLocalExecError(
            "activity_unsafe_material",
            "unsafe material rejected at controlled exec boundary",
        )
    required = (
        request.activity_id,
        request.transaction_ref,
        request.operation_ref,
        request.idempotency_key,
    )
    for value in required:
        if not _is_required_safe_ref(value):
            raise ControlledLocalExecError(
                "activity_unsafe_material",
                "unsafe material rejected at controlled exec boundary",
            )
    optional: list[Any] = [
        request.prompt_ref,
        request.cwd_ref,
        request.allowed_roots_ref,
        request.preflight_activity_id,
        request.lease_id,
        request.lease_holder_ref,
    ]
    optional.extend(request.context_refs)
    for value in optional:
        if (
            _value_is_unsafe(value)
            or _has_exec_unsafe_marker(value)
            or not _is_safe_ref_or_none(value)
        ):
            raise ControlledLocalExecError(
                "activity_unsafe_material",
                "unsafe material rejected at controlled exec boundary",
            )


def _check_required_claim_check_refs(request: ControlledLocalExecRequest) -> None:
    if request.prompt_ref is None:
        raise ControlledLocalExecError(
            "activity_precondition_unmet", "prompt claim-check ref is required"
        )
    if request.preflight_activity_id is None:
        raise ControlledLocalExecError(
            "activity_precondition_unmet",
            "prior durable-state preflight reference is required",
        )


def _check_operator_gate(request: ControlledLocalExecRequest) -> None:
    if request.operator_gate is not True:
        raise ControlledLocalExecError(
            "activity_precondition_unmet", "operator gate is required"
        )


def _check_prior_evidence_digest(digest: Any) -> None:
    if type(digest) is not str or _SHA256_DIGEST_RE.fullmatch(digest) is None:
        raise ControlledLocalExecError(
            "activity_precondition_unmet",
            "prior dry-run evidence digest is missing or malformed",
        )
    if digest != _expected_prior_evidence_digest():
        raise ControlledLocalExecError(
            "activity_precondition_unmet",
            "prior dry-run evidence digest does not match",
        )


def _check_preflight_binding(
    request: ControlledLocalExecRequest, preflight_store: DurableStatePreflightStore
) -> dict[str, Any]:
    """Bind the exec request to its durable-state preflight record.

    The preflight record (PR #107 surface) supplies the lease and state
    version this request must still hold; any drift fails closed before the
    claim is even attempted.
    """

    try:
        record = query_durable_state_preflight(
            preflight_store, activity_id=request.preflight_activity_id
        ).to_durable_state()
    except DurableStatePreflightError:
        raise ControlledLocalExecError(
            "activity_precondition_unmet",
            "prior durable-state preflight record is missing or invalid",
        ) from None
    if (
        record["transaction_ref"] != request.transaction_ref
        or record["operation_ref"] != request.operation_ref
    ):
        raise ControlledLocalExecError(
            "activity_precondition_unmet",
            "preflight record does not bind this transaction/operation",
        )
    if not _is_required_safe_ref(request.lease_id) or not _is_required_safe_ref(
        request.lease_holder_ref
    ):
        raise ControlledLocalExecError(
            "activity_lease_lost", "request lease refs are invalid"
        )
    if not _is_int_at_least(request.lease_epoch, 0):
        raise ControlledLocalExecError("activity_lease_lost", "invalid lease epoch")
    if request.lease_epoch < record["lease_epoch"]:
        raise ControlledLocalExecError("activity_stale_state", "lease epoch is stale")
    if (
        request.lease_id != record["lease_id"]
        or request.lease_epoch != record["lease_epoch"]
        or request.lease_holder_ref != record["lease_holder_ref"]
    ):
        raise ControlledLocalExecError(
            "activity_lease_lost", "caller does not hold the preflight lease"
        )
    if (
        not _is_int_at_least(request.expected_state_version, 0)
        or request.expected_state_version != record["state_version"]
    ):
        raise ControlledLocalExecError(
            "activity_toctou_conflict", "state version drifted"
        )
    return record


def _provenance_error() -> ControlledLocalExecError:
    return ControlledLocalExecError(
        "activity_runner_provenance_unverified",
        "pinned local acpx binary provenance is required",
    )


def _check_runner_provenance(
    request: ControlledLocalExecRequest, role_path: Path
) -> dict[str, Any]:
    """Verify pinned, no-fetch local runner provenance before any launch.

    The request must carry the exact sha256 digest of the allowlisted role
    file, and that file must declare a non-null absolute local ``acpx_binary``
    with no whitespace and no fetch-shaped package-runner or shell basename
    (the same ``FORBIDDEN_RUNNER_BASENAMES`` predicate the standalone
    provenance verifier enforces). A null binary would let the supervisor
    library fall back to its network-fetching package-runner prefix, which is
    forbidden for strict local/offline claims.
    """

    if (
        type(request.role_file_digest) is not str
        or _SHA256_DIGEST_RE.fullmatch(request.role_file_digest) is None
    ):
        raise _provenance_error()
    try:
        payload = role_path.read_bytes()
    except OSError:
        raise _provenance_error() from None
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    if digest != request.role_file_digest:
        raise _provenance_error()
    try:
        mapping = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _provenance_error() from None
    if type(mapping) is not dict:
        raise _provenance_error()
    runner = mapping.get("runner")
    if type(runner) is not dict:
        raise _provenance_error()
    if (
        runner.get("type") != _REQUIRED_RUNNER_TYPE
        or runner.get("acpx_version") != _REQUIRED_ACPX_VERSION
    ):
        raise _provenance_error()
    binary = runner.get("acpx_binary")
    if (
        type(binary) is not str
        or not binary
        or not binary.startswith("/")
        or any(ch.isspace() for ch in binary)
        or _is_forbidden_runner_basename(Path(binary).name)
    ):
        raise _provenance_error()
    return mapping


def _capability_error() -> ControlledLocalExecError:
    return ControlledLocalExecError(
        "activity_role_capability_rejected",
        "role config exceeds the read-only one-shot reviewer first slice",
    )


def _check_role_capability(
    request: ControlledLocalExecRequest, mapping: Mapping[str, Any]
) -> None:
    """Reject any role config beyond a read-only one-shot reviewer.

    The role file must declare exactly the adapter agent its role key pins in
    ``CONTROLLED_EXEC_ROLE_ADAPTER_AGENT`` (``codex`` for the Codex primary
    reviewer, ``claude`` for the Claude Code read-only reviewer), so a Codex
    role can never run under the Claude adapter and vice versa.
    """

    required_adapter = CONTROLLED_EXEC_ROLE_ADAPTER_AGENT.get(request.role_key)
    if required_adapter is None:
        raise _capability_error()
    if (
        mapping.get("schema_version") != _REQUIRED_ROLE_SCHEMA_VERSION
        or mapping.get("role_id") != request.role_key
    ):
        raise _capability_error()
    runner = mapping["runner"]
    if runner.get("adapter_agent") != required_adapter:
        raise _capability_error()
    permissions = mapping.get("permissions")
    if type(permissions) is not dict:
        raise _capability_error()
    for kind in _READ_ONLY_TRUE_PERMISSIONS:
        if permissions.get(kind) is not True:
            raise _capability_error()
    for kind in _READ_ONLY_FALSE_PERMISSIONS:
        if permissions.get(kind) is not False:
            raise _capability_error()
    session = mapping.get("session")
    if session is not None:
        if type(session) is not dict or session.get("strategy") != "exec":
            raise _capability_error()


# --------------------------------------------------------------------------- #
# Pinned local acpx binary provenance (Phase D smoke prerequisite)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PinnedLocalAcpxProvenance:
    """Sanitized provenance proof for an operator-pinned local acpx binary.

    Carries only the verified absolute path, the executable's sha256, the
    exact pinned version, and the sanitized single-line probe text. Raw probe
    output, stderr, or exception material never reach this record.
    """

    binary_path: str
    binary_sha256: str
    acpx_version: str
    probe_text: str


def verify_pinned_local_acpx_binary(
    binary_path: Any,
    *,
    version_probe: Callable[[str], str],
    expected_version: str = _REQUIRED_ACPX_VERSION,
) -> PinnedLocalAcpxProvenance:
    """Verify an operator-pinned local acpx executable without invoking it here.

    Preparation helper for a later, separately approved Phase D smoke: the
    candidate path must be absolute, whitespace-free, and not a fetch-shaped
    package runner or shell basename; the file must exist and be executable;
    and the **injected** ``version_probe`` must return sanitized single-line
    text carrying the pinned version (``0.10.0``) as an exact standalone
    token — a substring hit inside ``10.10.0`` or a pre-release/build variant
    like ``0.10.0-dev`` never satisfies the pin. This module never
    executes the binary — how the probe text is produced is the caller's
    responsibility, out of band. Every miss fails closed with the stable
    ``activity_runner_provenance_unverified`` code and no raw detail.
    """

    if expected_version != _REQUIRED_ACPX_VERSION:
        raise _provenance_error()
    if (
        type(binary_path) is not str
        or not binary_path.startswith("/")
        or any(ch.isspace() for ch in binary_path)
    ):
        raise _provenance_error()
    path = Path(binary_path)
    if _is_forbidden_runner_basename(path.name):
        raise _provenance_error()
    try:
        if not path.is_file() or not os.access(binary_path, os.X_OK):
            raise _provenance_error()
        payload = path.read_bytes()
    except OSError:
        raise _provenance_error() from None
    binary_sha256 = "sha256:" + hashlib.sha256(payload).hexdigest()
    try:
        probe_text = version_probe(binary_path)
    except Exception:
        raise _provenance_error() from None
    if (
        type(probe_text) is not str
        or len(probe_text) > _ACPX_PROBE_TEXT_MAX_CHARS
        or _SAFE_PROBE_TEXT_RE.fullmatch(probe_text) is None
        or _value_is_unsafe(probe_text)
        or _has_exec_unsafe_marker(probe_text)
        or not _probe_text_has_exact_version(probe_text, expected_version)
    ):
        raise _provenance_error()
    return PinnedLocalAcpxProvenance(
        binary_path=binary_path,
        binary_sha256=binary_sha256,
        acpx_version=expected_version,
        probe_text=probe_text,
    )


# --------------------------------------------------------------------------- #
# Durable claim-state construction
# --------------------------------------------------------------------------- #
def _digest_hex(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _expected_prior_evidence_digest() -> str:
    return build_controlled_local_dry_run_evidence()["fixture_digest"]


def _fingerprint(request: ControlledLocalExecRequest, role_file_ref: str) -> str:
    payload = {
        "activity_id": request.activity_id,
        "transaction_ref": request.transaction_ref,
        "operation_ref": request.operation_ref,
        "mode": request.mode,
        "role_key": request.role_key,
        "role_file": role_file_ref,
        "role_file_digest": request.role_file_digest,
        "prompt_ref": request.prompt_ref,
        "context_refs": list(request.context_refs),
        "cwd_ref": request.cwd_ref,
        "allowed_roots_ref": request.allowed_roots_ref,
        "prior_dry_run_evidence_digest": request.prior_dry_run_evidence_digest,
        "preflight_activity_id": request.preflight_activity_id,
        "lease_id": request.lease_id,
        "lease_epoch": request.lease_epoch,
        "lease_holder_ref": request.lease_holder_ref,
        "expected_state_version": request.expected_state_version,
        "operator_gate": request.operator_gate,
    }
    return _digest_hex(payload)


def _build_claim_state(
    request: ControlledLocalExecRequest,
    *,
    preflight_view_ref: str,
    ok: bool,
    status: str,
    supervisor_status: str | None,
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
        "mode": request.mode,
        "phase": _PHASE,
        "activity_id": request.activity_id,
        "transaction_ref": request.transaction_ref,
        "operation_ref": request.operation_ref,
        "role_key": request.role_key,
        "idempotency_key": request.idempotency_key,
        "role_file_digest": request.role_file_digest,
        "prior_dry_run_evidence_digest": request.prior_dry_run_evidence_digest,
        "preflight_view_ref": preflight_view_ref,
        "approval_ref": _APPROVAL_REF,
        "lease_id": request.lease_id,
        "lease_epoch": request.lease_epoch,
        "lease_holder_ref": request.lease_holder_ref,
        "state_version": request.expected_state_version,
        "attempt_index": 1,
        "attempt_count": 1,
        "supervisor_status": supervisor_status,
        "artifact_ref_count": artifact_ref_count,
        "evidence_ref": evidence_ref,
        "evidence_digest": evidence_digest,
        "business_verdict": None,
        "caller_verdict": caller_verdict,
        "error_code": error_code,
        "retryable": retryable,
    }
    view_model_ref = _VIEW_MODEL_REF_PREFIX + _digest_hex(core)[:16]
    return {**core, "view_model_ref": view_model_ref}


def _failure_state(
    request: ControlledLocalExecRequest,
    preflight_view_ref: str,
    *,
    status: str,
    retryable: bool,
    error_code: str = _ERROR_SUPERVISOR_FAILED,
) -> dict[str, Any]:
    return _build_claim_state(
        request,
        preflight_view_ref=preflight_view_ref,
        ok=False,
        status=status,
        supervisor_status=None,
        artifact_ref_count=0,
        evidence_ref=None,
        evidence_digest=None,
        caller_verdict=None,
        error_code=error_code,
        retryable=retryable,
    )


def _state_from_supervisor_outcome(
    request: ControlledLocalExecRequest,
    preflight_view_ref: str,
    outcome: LocalOfflineSupervisorOutcome,
) -> dict[str, Any]:
    """Convert a seam outcome into trusted sanitized claim state.

    The seam is still a boundary: any unsafe or malformed outcome field — and
    any non-null ``business_verdict`` from below — collapses the attempt into
    a stable terminal failure rather than persisting raw material. Business
    success is never inferred from supervisor status or exit information.
    """

    status_raw = getattr(outcome, "status", None)
    status = _safe_code(status_raw)
    supervisor_status_raw = getattr(outcome, "supervisor_status", None)
    supervisor_status = _safe_code(supervisor_status_raw)
    caller_verdict_raw = getattr(outcome, "caller_verdict", None)
    caller_verdict = _safe_code(caller_verdict_raw)
    evidence_ref_raw = getattr(outcome, "evidence_ref", None)
    evidence_ref = _safe_evidence_ref(evidence_ref_raw)
    evidence_digest_raw = getattr(outcome, "evidence_digest", None)
    evidence_digest = _safe_digest(evidence_digest_raw)
    artifact_ref_count = _safe_artifact_ref_count(getattr(outcome, "artifact_ref_count", None))
    error_code_raw = getattr(outcome, "error_code", None)
    error_code = _safe_code(error_code_raw)

    unsafe = (
        getattr(outcome, "business_verdict", None) is not None
        or status is None
        or artifact_ref_count is None
        or (supervisor_status_raw is not None and supervisor_status is None)
        or (caller_verdict_raw is not None and caller_verdict is None)
        or (evidence_ref_raw is not None and evidence_ref is None)
        or (evidence_digest_raw is not None and evidence_digest is None)
        or (error_code_raw is not None and error_code is None)
    )
    if unsafe:
        return _failure_state(
            request, preflight_view_ref, status=_STATUS_FAILED_TERMINAL, retryable=False
        )
    if error_code is not None or status == "error":
        return _failure_state(
            request, preflight_view_ref, status=_STATUS_FAILED_RETRYABLE, retryable=True
        )
    return _build_claim_state(
        request,
        preflight_view_ref=preflight_view_ref,
        ok=True,
        status=_STATUS_COMPLETED,
        supervisor_status=supervisor_status,
        artifact_ref_count=artifact_ref_count,
        evidence_ref=evidence_ref,
        evidence_digest=evidence_digest,
        caller_verdict=caller_verdict,
        error_code=None,
        retryable=False,
    )


def _materialize_prompt(
    request: ControlledLocalExecRequest,
    materializer: Callable[[ControlledLocalExecRequest], str],
) -> str:
    """Run an explicitly injected prompt materializer and screen its output.

    Called only after the atomic pre-launch claim is already resident. A
    raising materializer or any non-string, empty, oversized, or
    unsafe-marker output fails closed with a stable code; raw materializer
    detail never propagates.
    """

    try:
        prompt = materializer(request)
    except Exception:
        raise ControlledLocalExecError(
            _ERROR_PROMPT_MATERIALIZATION_FAILED,
            "prompt materialization failed closed",
        ) from None
    if (
        type(prompt) is not str
        or not prompt
        or len(prompt) > _MAX_MATERIALIZED_PROMPT_CHARS
        or _value_is_unsafe(prompt)
        or _has_exec_unsafe_marker(prompt)
    ):
        raise ControlledLocalExecError(
            _ERROR_PROMPT_MATERIALIZATION_FAILED,
            "prompt materialization failed closed",
        )
    return prompt


def _build_local_offline_request(
    request: ControlledLocalExecRequest,
    role_file_path: Path,
    *,
    prompt: str | None = None,
) -> LocalOfflineSupervisorRequest:
    """Assemble the seam request from sanitized claim-check refs.

    ``prompt`` defaults to ``None`` (the Phase C posture): raw material never
    travels from here, and the caller boundary inside the supervisor library
    fails closed on an empty exec prompt, so no agent run can start. A
    non-``None`` prompt is only ever supplied by the materialization-aware
    start path — after the acquired claim and after the ``_materialize_prompt``
    screen — and exists solely in this in-memory seam request: it never enters
    durable claim state, fingerprints, or query projections. ``context`` stays
    ``None`` unconditionally.
    """

    refs: list[str] = [request.transaction_ref, request.operation_ref]
    if request.prompt_ref is not None:
        refs.append(request.prompt_ref)
    refs.extend(request.context_refs)
    return LocalOfflineSupervisorRequest(
        mode=_SEAM_MODE,
        correlation_label=request.activity_id,
        role=None,
        role_file=str(role_file_path),
        enabled=True,
        approval_token=LOCAL_OFFLINE_APPROVAL_TOKEN,
        prompt=prompt,
        context=None,
        claim_check_refs=tuple(refs),
    )


# --------------------------------------------------------------------------- #
# Lifecycle: start + query
# --------------------------------------------------------------------------- #
def start_controlled_local_exec(
    request: ControlledLocalExecRequest,
    *,
    store: ControlledLocalExecClaimStore,
    preflight_store: DurableStatePreflightStore,
    invoke_supervisor: Callable[[LocalOfflineSupervisorRequest], LocalOfflineSupervisorOutcome]
    | None = None,
    role_root: str | Path | None = None,
    prompt_materializer: Callable[[ControlledLocalExecRequest], str] | None = None,
) -> ControlledLocalExecResult:
    """Start one controlled local one-shot exec attempt.

    Every gate (approval, mode, role allowlist, material, operator gate,
    prior evidence digest, preflight/lease/state-version binding, pinned
    runner provenance, read-only capability) fails closed *before* the atomic
    pre-launch claim, and the claim is written before the supervisor boundary
    is invoked. Identical replays return the resident sanitized projection
    without a second launch; conflicting replays fail closed pre-launch. A
    supervisor exception or unsafe outcome collapses to a stable sanitized
    failure state with no raw detail.

    ``prompt_materializer`` is the Phase D smoke prerequisite seam: when
    ``None`` (the default) the seam request keeps ``prompt=None`` exactly as
    in Phase C, so no agent run can start. When explicitly injected, it runs
    only after the acquired claim and before the single supervisor call; its
    screened output travels solely in the in-memory seam request and never
    enters durable state. A failed or unsafe materialization finalizes the
    claim as a terminal sanitized failure and never invokes the supervisor.
    """

    _check_enabled_and_approved(request)
    _check_mode(request)
    role_file_ref = _resolve_role_file_ref(request.role_key)
    _check_material(request)
    _check_required_claim_check_refs(request)
    _check_operator_gate(request)
    _check_prior_evidence_digest(request.prior_dry_run_evidence_digest)
    preflight_record = _check_preflight_binding(request, preflight_store)
    root = Path(role_root) if role_root is not None else _DEFAULT_ROLE_ROOT
    role_file_path = root / role_file_ref
    role_mapping = _check_runner_provenance(request, role_file_path)
    _check_role_capability(request, role_mapping)

    fingerprint = _fingerprint(request, role_file_ref)
    preflight_view_ref = preflight_record["view_model_ref"]
    claim_state = _build_claim_state(
        request,
        preflight_view_ref=preflight_view_ref,
        ok=False,
        status=_STATUS_CLAIMED,
        supervisor_status=None,
        artifact_ref_count=0,
        evidence_ref=None,
        evidence_digest=None,
        caller_verdict=None,
        error_code=None,
        retryable=False,
    )
    disposition, resident_state = store.claim(
        activity_id=request.activity_id,
        idempotency_key=request.idempotency_key,
        fingerprint=fingerprint,
        state=claim_state,
    )
    if disposition == "replayed":
        # In-progress (e.g. post-crash) and terminal claims both replay the
        # resident projection; a second launch — and a second prompt
        # materialization — never happens here.
        return ControlledLocalExecResult(resident_state)

    prompt: str | None = None
    if prompt_materializer is not None:
        try:
            prompt = _materialize_prompt(request, prompt_materializer)
        except ControlledLocalExecError as exc:
            final_state = _failure_state(
                request,
                preflight_view_ref,
                status=_STATUS_FAILED_TERMINAL,
                retryable=False,
                error_code=exc.error_code,
            )
            store.finalize(
                activity_id=request.activity_id,
                idempotency_key=request.idempotency_key,
                fingerprint=fingerprint,
                state=final_state,
            )
            return ControlledLocalExecResult(final_state)

    invoke = invoke_supervisor if invoke_supervisor is not None else invoke_local_offline_supervisor
    seam_request = _build_local_offline_request(request, role_file_path, prompt=prompt)
    try:
        outcome = invoke(seam_request)
    except Exception:
        final_state = _failure_state(
            request, preflight_view_ref, status=_STATUS_FAILED_RETRYABLE, retryable=True
        )
    else:
        final_state = _state_from_supervisor_outcome(request, preflight_view_ref, outcome)

    store.finalize(
        activity_id=request.activity_id,
        idempotency_key=request.idempotency_key,
        fingerprint=fingerprint,
        state=final_state,
    )
    return ControlledLocalExecResult(final_state)


def query_controlled_local_exec(
    store: ControlledLocalExecClaimStore, *, activity_id: str
) -> ControlledLocalExecResult:
    """Return the durable sanitized claim projection by ``activity_id``.

    Query is local resident state only; it never re-invokes the supervisor
    and never rehydrates raw material.
    """

    state = store.get_by_activity(activity_id)
    if state is None:
        raise ControlledLocalExecError(
            "activity_not_found", "no durable claim state for the given activity id"
        )
    return ControlledLocalExecResult(state)


# --------------------------------------------------------------------------- #
# Sanitization helpers + resident-state validation
# --------------------------------------------------------------------------- #
def _safe_code(value: Any) -> str | None:
    if value is None:
        return None
    if (
        type(value) is not str
        or _value_is_unsafe(value)
        or _STABLE_CODE_RE.fullmatch(value) is None
    ):
        return None
    return value


def _safe_evidence_ref(value: Any) -> str | None:
    if value is None:
        return None
    if (
        type(value) is not str
        or _value_is_unsafe(value)
        or _EVIDENCE_REF_RE.fullmatch(value) is None
    ):
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


def _is_safe_fingerprint(value: Any) -> bool:
    return type(value) is str and _FINGERPRINT_RE.fullmatch(value) is not None


def _is_safe_ref(value: Any) -> bool:
    return type(value) is str and _REF_RE.fullmatch(value) is not None


def _is_safe_ref_or_none(value: Any) -> bool:
    return value is None or _is_safe_ref(value)


def _is_required_safe_ref(value: Any) -> bool:
    return _is_safe_ref(value) and _state_string_is_safe(value)


def _has_exec_unsafe_marker(value: Any) -> bool:
    return type(value) is str and any(
        marker in value.lower() for marker in _EXEC_UNSAFE_MARKERS
    )


def _state_string_is_safe(value: str) -> bool:
    return not _value_is_unsafe(value) and not _has_exec_unsafe_marker(value)


def _is_int_at_least(value: Any, minimum: int) -> bool:
    return type(value) is int and value >= minimum


def _reject_unsafe_state() -> ControlledLocalExecError:
    return ControlledLocalExecError(
        "activity_unsafe_material", "unsafe durable claim state rejected"
    )


def _validate_claim_state_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    if type(state) is not dict or set(state) != _CLAIM_STATE_KEYS:
        raise _reject_unsafe_state()
    projected = dict(state)
    if (
        projected["type"] != _STATE_TYPE
        or projected["mode"] != CONTROLLED_EXEC_MODE
        or projected["phase"] != _PHASE
        or projected["approval_ref"] != _APPROVAL_REF
        or projected["status"] not in _CLAIM_STATUSES
        or projected["business_verdict"] is not None
        or type(projected["ok"]) is not bool
        or type(projected["retryable"]) is not bool
    ):
        raise _reject_unsafe_state()
    safe_ref_keys = (
        "activity_id",
        "transaction_ref",
        "operation_ref",
        "role_key",
        "idempotency_key",
        "lease_id",
        "lease_holder_ref",
        "view_model_ref",
        "preflight_view_ref",
    )
    if any(not _is_required_safe_ref(projected[key]) for key in safe_ref_keys):
        raise _reject_unsafe_state()
    if CONTROLLED_EXEC_ROLE_ALLOWLIST.get(projected["role_key"]) is None:
        raise _reject_unsafe_state()
    if not projected["view_model_ref"].startswith(_VIEW_MODEL_REF_PREFIX):
        raise _reject_unsafe_state()
    if not projected["preflight_view_ref"].startswith(_PREFLIGHT_VIEW_REF_PREFIX):
        raise _reject_unsafe_state()
    if _safe_digest(projected["role_file_digest"]) is None:
        raise _reject_unsafe_state()
    prior_digest = projected["prior_dry_run_evidence_digest"]
    if (
        _safe_digest(prior_digest) is None
        or prior_digest != _expected_prior_evidence_digest()
    ):
        raise _reject_unsafe_state()
    int_minimums = {
        "lease_epoch": 0,
        "state_version": 0,
        "artifact_ref_count": 0,
    }
    if any(
        not _is_int_at_least(projected[key], minimum)
        for key, minimum in int_minimums.items()
    ):
        raise _reject_unsafe_state()
    if projected["attempt_index"] != 1 or projected["attempt_count"] != 1:
        raise _reject_unsafe_state()

    status = projected["status"]
    if status == _STATUS_COMPLETED:
        if (
            projected["ok"] is not True
            or projected["error_code"] is not None
            or projected["retryable"] is not False
            or (
                projected["supervisor_status"] is not None
                and _safe_code(projected["supervisor_status"]) is None
            )
            or (
                projected["evidence_ref"] is not None
                and _safe_evidence_ref(projected["evidence_ref"]) is None
            )
            or (
                projected["evidence_digest"] is not None
                and _safe_digest(projected["evidence_digest"]) is None
            )
            or (
                projected["caller_verdict"] is not None
                and _safe_code(projected["caller_verdict"]) is None
            )
        ):
            raise _reject_unsafe_state()
    else:
        # claimed_in_progress and both failure states carry no lower-layer
        # payload at all; failures carry only a stable collapse code. A
        # materialization failure is always terminal (the supervisor was
        # never invoked, so a retryable variant would be untruthful).
        if status == _STATUS_CLAIMED:
            error_code_is_valid = projected["error_code"] is None
        elif status == _STATUS_FAILED_TERMINAL:
            error_code_is_valid = projected["error_code"] in _FAILURE_COLLAPSE_CODES
        else:
            error_code_is_valid = projected["error_code"] == _ERROR_SUPERVISOR_FAILED
        expected_retryable = status == _STATUS_FAILED_RETRYABLE
        if (
            projected["ok"] is not False
            or not error_code_is_valid
            or projected["retryable"] is not expected_retryable
            or projected["supervisor_status"] is not None
            or projected["artifact_ref_count"] != 0
            or projected["evidence_ref"] is not None
            or projected["evidence_digest"] is not None
            or projected["caller_verdict"] is not None
        ):
            raise _reject_unsafe_state()

    if any(
        type(value) is str and not _state_string_is_safe(value)
        for value in projected.values()
    ):
        raise _reject_unsafe_state()
    return projected
