"""R2 Runtime Spine — supervisor execution-port contract (local/offline).

This module defines the small, transport-neutral boundary the spine uses to talk
about supervised AGENT sessions. It is pure Python value objects + an abstract
interface: importing it launches nothing, opens no listeners, and wires no live
platform or delivery surface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

from .events import SpineError, _safe_id, safe_task_id

RUNTIME_INVALID_SESSION = "runtime_invalid_session"
PORT_STABLE_CODES = frozenset({RUNTIME_INVALID_SESSION})

SESSION_STATES = frozenset(
    {
        "running",
        "permission_wait",
        "completed",
        "failed",
        "cancelled",
        "ambiguous",
        "orphaned",
    }
)
LIVE_SESSION_STATES = frozenset({"running", "permission_wait"})
TERMINAL_SESSION_STATES = frozenset({"completed", "failed", "cancelled", "ambiguous"})
REAPABLE_SESSION_STATES = frozenset({"orphaned"})

_PROJECTED_STATUSES = frozenset({"created", "running", "permission_wait", "completed", "failed", "cancelled"})


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_SESSION)


def _safe_session_id(value: Any) -> str:
    if type(value) is not str or not value.startswith("sess_"):
        _invalid()
    try:
        return _safe_id(value, code=RUNTIME_INVALID_SESSION)
    except SpineError as exc:
        if exc.code == RUNTIME_INVALID_SESSION:
            raise
        _invalid()
    raise AssertionError("unreachable")


def _safe_ref(value: Any) -> str:
    try:
        return _safe_id(value, code=RUNTIME_INVALID_SESSION)
    except SpineError as exc:
        if exc.code == RUNTIME_INVALID_SESSION:
            raise
        _invalid()
    raise AssertionError("unreachable")


def _safe_state(value: Any) -> str:
    if type(value) is not str or value not in SESSION_STATES:
        _invalid()
    return value


def _bool(value: Any) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


@dataclass(frozen=True)
class SessionRef:
    """Stable ref to one simulated supervisor session."""

    task_id: str
    session_id: str

    def __post_init__(self) -> None:
        _check_session_ref_fields(self)


@dataclass(frozen=True)
class LivenessState:
    """Closed liveness view for fake session reaping policy."""

    task_id: str
    session_id: str
    state: str
    alive: bool
    permission_wait: bool
    reapable: bool

    def __post_init__(self) -> None:
        _check_liveness_fields(self)


@dataclass(frozen=True)
class SessionStatus:
    """Projection-derived status summary for a session."""

    task_id: str
    session_id: str
    state: str
    alive: bool
    terminal: bool
    last_seq: int
    projected_status: str | None

    def __post_init__(self) -> None:
        _check_session_status_fields(self)


def _check_session_ref_fields(ref: SessionRef) -> None:
    try:
        task_id = ref.task_id
        session_id = ref.session_id
    except AttributeError:
        _invalid()
    safe_task_id(task_id, code=RUNTIME_INVALID_SESSION)
    _safe_session_id(session_id)


def validate_session_ref(ref: SessionRef) -> SessionRef:
    if type(ref) is not SessionRef:
        _invalid()
    _check_session_ref_fields(ref)
    return ref


def _check_liveness_fields(state: LivenessState) -> None:
    safe_task_id(state.task_id, code=RUNTIME_INVALID_SESSION)
    _safe_session_id(state.session_id)
    session_state = _safe_state(state.state)
    alive = _bool(state.alive)
    permission_wait = _bool(state.permission_wait)
    reapable = _bool(state.reapable)

    if permission_wait is not (session_state == "permission_wait"):
        _invalid()
    if session_state in LIVE_SESSION_STATES:
        if alive is not True or reapable is not False:
            _invalid()
    elif session_state in TERMINAL_SESSION_STATES:
        if alive is not False or reapable is not False:
            _invalid()
    elif session_state in REAPABLE_SESSION_STATES:
        if alive is not False or reapable is not True:
            _invalid()
    else:
        _invalid()


def validate_liveness_state(state: LivenessState) -> LivenessState:
    if type(state) is not LivenessState:
        _invalid()
    _check_liveness_fields(state)
    return state


def _check_session_status_fields(status: SessionStatus) -> None:
    safe_task_id(status.task_id, code=RUNTIME_INVALID_SESSION)
    _safe_session_id(status.session_id)
    session_state = _safe_state(status.state)
    alive = _bool(status.alive)
    terminal = _bool(status.terminal)
    if type(status.last_seq) is not int or status.last_seq < 0:
        _invalid()
    if status.projected_status is not None and status.projected_status not in _PROJECTED_STATUSES:
        _invalid()
    if terminal is not (session_state in TERMINAL_SESSION_STATES):
        _invalid()
    if alive is not (session_state in LIVE_SESSION_STATES):
        _invalid()


def validate_session_status(status: SessionStatus) -> SessionStatus:
    if type(status) is not SessionStatus:
        _invalid()
    _check_session_status_fields(status)
    return status


class ExecutionPort(ABC):
    """Producer-facing execution-port interface for supervised session semantics."""

    @abstractmethod
    def create_or_attach(self, task_id: str, launch_spec: Any) -> SessionRef:
        """Create or attach to the single session for ``task_id``."""

    @abstractmethod
    def stream(self, ref: str | SessionRef) -> Sequence[dict[str, Any]]:
        """Return deterministic refs-only event views for a session/task."""

    @abstractmethod
    def signal(self, task_id: str, decision_ref: str) -> SessionStatus:
        """Apply a refs-only operator decision to a pending session."""

    @abstractmethod
    def status(self, ref: str | SessionRef) -> SessionStatus:
        """Return projection-derived session status."""

    @abstractmethod
    def kill(self, ref: str | SessionRef, reason_ref: str = "ref_cancelled") -> SessionStatus:
        """Mark the session cancelled with a refs-only reason."""

    @abstractmethod
    def liveness(self, ref: str | SessionRef) -> LivenessState:
        """Return fake liveness state for local policy tests only."""
