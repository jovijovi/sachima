"""R4 Runtime Spine — Isolated Workspace single-writer lease (local/offline).

A run's Isolated Workspace carries a **single-writer lease**: at most one writer
may mutate one ``task_id``'s workspace at a time. The lease is the *invariant*,
not git — a git worktree is merely one implementation for code tasks — so the
store makes no filesystem, process, or platform assumption. Duplicate acquire by
the same holder is idempotent (there is no silent renewal); a conflicting acquire
fails closed without mutating state; release requires the exact holder + token;
expiry is deterministic against a passed logical tick, and an expired lease is
reclaimable only through the explicit policy path.

Everything here is pure local/offline Python: importing/using it launches no
external runtime, opens no listener, touches no filesystem, and wires no platform
or delivery surface. Every lease field is validated as a safe id — never raw
prompt/context, tool output, platform id, or private path material.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, NoReturn

from .events import SpineError, _safe_id, safe_task_id

# --------------------------------------------------------------------------- #
# Stable error-code family (fail-closed; the message is the code, never input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_WORKSPACE_LEASE = "runtime_invalid_workspace_lease"
RUNTIME_WORKSPACE_LEASE_CONFLICT = "runtime_workspace_lease_conflict"

WORKSPACE_STABLE_CODES = frozenset(
    {RUNTIME_INVALID_WORKSPACE_LEASE, RUNTIME_WORKSPACE_LEASE_CONFLICT}
)


def _invalid() -> NoReturn:
    """Fail closed with the single stable invalid-lease code — never echoing input."""

    raise SpineError(RUNTIME_INVALID_WORKSPACE_LEASE)


def _safe_lease_ref(value: Any) -> str:
    """A refs-only lease field — a safe id, never path/platform/raw material."""

    return _safe_id(value, code=RUNTIME_INVALID_WORKSPACE_LEASE)


def _check_tick(value: Any) -> int:
    """A logical tick — a non-negative int (``bool`` excluded, no float)."""

    if type(value) is not int or value < 0:
        _invalid()
    return value


def _check_ttl(value: Any) -> int:
    """A time-to-live — a strictly positive int (``bool`` excluded, no float)."""

    if type(value) is not int or value < 1:
        _invalid()
    return value


def _check_lease_fields(lease: Any) -> None:
    """Exact fail-closed validation of a lease's fields.

    Fails closed on: an unsafe ``task_id``; an unsafe/path/platform/raw
    ``holder`` / ``token`` / ``workspace_ref``; a bad ``acquired_at`` /
    ``expires_at`` tick; or an impossible ``expires_at <= acquired_at`` ordering.
    """

    try:
        task_id = lease.task_id
        holder = lease.holder
        token = lease.token
        workspace_ref = lease.workspace_ref
        acquired_at = lease.acquired_at
        expires_at = lease.expires_at
    except AttributeError:
        _invalid()
    safe_task_id(task_id, code=RUNTIME_INVALID_WORKSPACE_LEASE)
    _safe_lease_ref(holder)
    _safe_lease_ref(token)
    _safe_lease_ref(workspace_ref)
    _check_tick(acquired_at)
    _check_tick(expires_at)
    # A lease that expires at or before it was acquired is impossible.
    if expires_at <= acquired_at:
        _invalid()


@dataclass(frozen=True)
class WorkspaceLease:
    """Frozen single-writer lease over one ``task_id``'s Isolated Workspace.

    ``WorkspaceLease`` is exported public surface, so construction alone is never
    grounds for trust: ``__post_init__`` re-runs the full refs-only allowlist so a
    direct ``WorkspaceLease(...)`` carrying a path/platform ref or a bad time
    ordering fails closed instead of being trusted.
    """

    task_id: str
    holder: str
    token: str
    workspace_ref: str
    acquired_at: int
    expires_at: int

    def __post_init__(self) -> None:
        _check_lease_fields(self)

    def is_expired(self, now: int) -> bool:
        """Deterministic, side-effect-free expiry against a logical tick."""

        return _check_tick(now) >= self.expires_at


def validate_workspace_lease(lease: Any) -> WorkspaceLease:
    """Re-validate a lease at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type, an unsafe/path/platform/raw ref, or a bad
    time ordering all fail closed with the stable code only — never echoing the
    rejected material.
    """

    if type(lease) is not WorkspaceLease:
        _invalid()
    _check_lease_fields(lease)
    return lease


@dataclass
class WorkspaceLeaseStore:
    """In-memory, lock-guarded single-writer lease table keyed by ``task_id``.

    Zero-arg: the store owns its own state — no registry / clock / path / port is
    a constructor parameter. It holds at most one active lease per ``task_id`` and
    mints deterministic ``lease_<n>`` tokens from an internal monotonic counter.

    Internal state (``_leases`` / ``_counter`` / ``_lock``) is ``init=False`` — the
    store owns it and none of it is a constructor parameter, so a caller cannot
    seed a pre-existing lease or inject a lock: the only construction is zero-arg
    ``WorkspaceLeaseStore()``.
    """

    _leases: dict[str, WorkspaceLease] = field(default_factory=dict, init=False)
    _counter: int = field(default=0, init=False)
    _lock: threading.RLock = field(
        default_factory=threading.RLock, init=False, repr=False, compare=False
    )

    def active_count(self) -> int:
        with self._lock:
            return len(self._leases)

    def current(self, task_id: str) -> WorkspaceLease | None:
        with self._lock:
            return self._leases.get(task_id)


def _check_store(store: Any) -> WorkspaceLeaseStore:
    if type(store) is not WorkspaceLeaseStore:
        _invalid()
    return store


def acquire_workspace_lease(
    store: WorkspaceLeaseStore,
    *,
    task_id: str,
    holder: str,
    workspace_ref: str,
    now: int,
    ttl: int,
) -> WorkspaceLease:
    """Grant the single-writer lease for ``task_id`` or fail closed.

    Same holder → idempotent: returns the existing lease unchanged (no silent
    renewal). A different holder → :data:`RUNTIME_WORKSPACE_LEASE_CONFLICT` with no
    state mutation, even when the held lease is already expired (an expired lease is
    reclaimed only through :func:`reclaim_expired_workspace_lease`).
    """

    _check_store(store)
    safe_task = safe_task_id(task_id, code=RUNTIME_INVALID_WORKSPACE_LEASE)
    safe_holder = _safe_lease_ref(holder)
    safe_ref = _safe_lease_ref(workspace_ref)
    _check_tick(now)
    _check_ttl(ttl)
    with store._lock:
        existing = store._leases.get(safe_task)
        if existing is not None:
            if existing.holder == safe_holder:
                return existing
            raise SpineError(RUNTIME_WORKSPACE_LEASE_CONFLICT)
        store._counter += 1
        lease = WorkspaceLease(
            task_id=safe_task,
            holder=safe_holder,
            token=f"lease_{store._counter}",
            workspace_ref=safe_ref,
            acquired_at=now,
            expires_at=now + ttl,
        )
        store._leases[safe_task] = lease
        return lease


def release_workspace_lease(
    store: WorkspaceLeaseStore, *, task_id: str, holder: str, token: str
) -> WorkspaceLease:
    """Release the lease for ``task_id`` — the exact holder + token are required.

    A missing lease, a wrong holder, or a wrong token all fail closed with
    :data:`RUNTIME_INVALID_WORKSPACE_LEASE` and leave the held lease untouched.
    """

    _check_store(store)
    safe_task = safe_task_id(task_id, code=RUNTIME_INVALID_WORKSPACE_LEASE)
    safe_holder = _safe_lease_ref(holder)
    safe_token = _safe_lease_ref(token)
    with store._lock:
        existing = store._leases.get(safe_task)
        if existing is None or existing.holder != safe_holder or existing.token != safe_token:
            _invalid()
        del store._leases[safe_task]
        return existing


def reclaim_expired_workspace_lease(
    store: WorkspaceLeaseStore, *, task_id: str, now: int
) -> WorkspaceLease:
    """Reclaim an **expired** lease for ``task_id`` — the only steal path.

    A missing lease or a still-live lease at ``now`` fails closed with
    :data:`RUNTIME_INVALID_WORKSPACE_LEASE` and leaves state untouched; a genuinely
    expired lease is removed and returned so the slot can be re-acquired.
    """

    _check_store(store)
    safe_task = safe_task_id(task_id, code=RUNTIME_INVALID_WORKSPACE_LEASE)
    _check_tick(now)
    with store._lock:
        existing = store._leases.get(safe_task)
        if existing is None or not existing.is_expired(now):
            _invalid()
        del store._leases[safe_task]
        return existing
