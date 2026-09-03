"""PR1 AgentRunSupervisorPort — injected supervisor backend adapter.

This module is the Sachima-side ``ExecutionPort`` implementation for an
agent-run-supervisor-shaped caller boundary. It deliberately depends on an
injected backend surface: the default backend is an in-memory deterministic fake,
and importing or using this module starts no real runtime, process, platform,
delivery, or durable service.

The adapter owns the Sachima spine mapping: validate a read-only/default-deny
``LaunchSpec``, call the backend only after role/workspace/policy admission,
store a single ``SessionRef`` per ``task_id``, append refs-only events to the
``TaskRegistry``, and collapse backend failures to stable port-side codes without
leaking raw backend material.

PR3 persistent session lifecycle hardening layers on this without widening the
surface: a port reconstructed over the *same* ``TaskRegistry`` + backend re-attaches
an existing session (running or ``permission_wait``) with no duplicate
``agent_attached`` event, while reconstruction over a fresh/missing backend fails
closed and never respawns. ``stream`` accepts an optional ``since_seq`` cursor so a
caller can resume only the events after a last-seen seq (no duplicate replay), and
:class:`LifecycleSnapshot` / :meth:`AgentRunSupervisorPort.lifecycle_snapshot`
expose refs-only ``last_seq`` / ``event_count`` / ``attach_count`` safe resume data
read from persisted Sachima state alone (no backend call). :meth:`close` is an
adapter-local, default-off port handoff that drops local tracking only — it kills
no backend session, appends no event, and mutates no registry state, so the
supervisor keeps owning the real session lifecycle. **PR3 status/liveness
read-failure policy (made explicit):** a *later* status/liveness backend read
failure on an existing session collapses to the stable
``runtime_supervisor_backend_failure`` code and never marks, kills, orphans, or
otherwise mutates that persisted session/log — it is a transient read fault, and a
subsequent successful read resumes the preserved session. An ``orphaned`` backend
state is surfaced as reapable via ``liveness`` but is deliberately NOT auto-written
as a terminal event into the canonical log; that reap decision belongs to a reaper.
"""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass
from typing import Any, Protocol, cast, runtime_checkable

from .events import (
    RUNTIME_INVALID_EVENT,
    RUNTIME_INVALID_LAUNCH_SPEC,
    RUNTIME_INVALID_TASK_RECORD,
    SpineError,
    _safe_id,
    build_event_body,
    event_projection,
    safe_task_id,
)
from .execution_port import (
    LIVE_SESSION_STATES,
    RUNTIME_INVALID_SESSION,
    TERMINAL_SESSION_STATES,
    ExecutionPort,
    LivenessState,
    SessionRef,
    SessionStatus,
    _safe_ref,
    validate_session_ref,
)
from .launch_spec import LaunchSpec, validate_launch_spec
from .registry import TaskRegistry

RUNTIME_SUPERVISOR_BACKEND_FAILURE = "runtime_supervisor_backend_failure"
RUNTIME_SUPERVISOR_POLICY_DENIED = "runtime_supervisor_policy_denied"
SUPERVISOR_PORT_STABLE_CODES = frozenset(
    {RUNTIME_SUPERVISOR_BACKEND_FAILURE, RUNTIME_SUPERVISOR_POLICY_DENIED}
)

_ALLOWED_ROLE = "read_only"
_SUPERVISOR_AGENT_KIND = "local_agent"
_WORKSPACE_REF_PREFIX = "ws_"
_POLICY_REF_PREFIX = "policy_"

_BACKEND_TO_SESSION_STATE = {
    "active": "running",
    "running": "running",
    "permission_wait": "permission_wait",
    "waiting_for_permission": "permission_wait",
    "completed": "completed",
    "succeeded": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
    "killed": "cancelled",
    "ambiguous": "ambiguous",
    "orphaned": "orphaned",
}

_PROJECTED_STATUSES = frozenset({"created", "running", "permission_wait", "completed", "failed", "cancelled"})


@runtime_checkable
class AgentRunSupervisorBackend(Protocol):
    """Injected minimal backend surface used by ``AgentRunSupervisorPort``."""

    def create_or_attach(self, task_id: str, refs: tuple[str, ...]) -> str: ...

    def attach_existing(self, task_id: str) -> str: ...

    def status(self, handle: str) -> str: ...

    def signal(self, handle: str, decision_ref: str) -> str: ...

    def kill(self, handle: str, reason_ref: str) -> str: ...

    def liveness(self, handle: str) -> str: ...


@dataclass
class _BackendSession:
    task_id: str
    handle: str
    state: str = "running"


class DefaultAgentRunSupervisorBackend:
    """Deterministic in-memory backend used by default tests.

    It implements the same narrow backend surface the real caller adapter will
    implement later, but it only mutates local Python state. Test-only helpers
    with a ``fake_`` prefix let unit tests model permission-wait and orphaned
    states without widening the production adapter API.
    """

    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self._sessions_by_task: dict[str, _BackendSession] = {}
        self._sessions_by_handle: dict[str, _BackendSession] = {}
        self._lock = threading.RLock()

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions_by_task)

    def create_or_attach(self, task_id: str, refs: tuple[str, ...]) -> str:
        safe_task = safe_task_id(task_id, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        safe_refs = tuple(_safe_ref(ref) for ref in refs)
        _ = safe_refs
        with self._lock:
            existing = self._sessions_by_task.get(safe_task)
            if existing is not None:
                return existing.handle
            handle = f"arsjob_{next(self._ids)}"
            _safe_id(handle, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
            session = _BackendSession(task_id=safe_task, handle=handle)
            self._sessions_by_task[safe_task] = session
            self._sessions_by_handle[handle] = session
            return handle

    def attach_existing(self, task_id: str) -> str:
        return self._get_by_task(task_id).handle

    def status(self, handle: str) -> str:
        return self._get(handle).state

    def signal(self, handle: str, decision_ref: str) -> str:
        _safe_ref(decision_ref)
        session = self._get(handle)
        if session.state != "permission_wait":
            raise SpineError(RUNTIME_INVALID_SESSION)
        session.state = "running"
        return session.state

    def kill(self, handle: str, reason_ref: str) -> str:
        _safe_ref(reason_ref)
        session = self._get(handle)
        if session.state not in TERMINAL_SESSION_STATES:
            session.state = "cancelled"
        return session.state

    def liveness(self, handle: str) -> str:
        return self._get(handle).state

    def fake_enter_permission_wait(self, task_id: str) -> None:
        session = self._get_by_task(task_id)
        if session.state not in LIVE_SESSION_STATES:
            raise SpineError(RUNTIME_INVALID_SESSION)
        session.state = "permission_wait"

    def fake_orphan(self, task_id: str) -> None:
        session = self._get_by_task(task_id)
        if session.state not in LIVE_SESSION_STATES:
            raise SpineError(RUNTIME_INVALID_SESSION)
        session.state = "orphaned"

    def _get_by_task(self, task_id: str) -> _BackendSession:
        safe_task = safe_task_id(task_id, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        with self._lock:
            session = self._sessions_by_task.get(safe_task)
            if session is None:
                raise SpineError(RUNTIME_INVALID_SESSION)
            return session

    def _get(self, handle: str) -> _BackendSession:
        safe_handle = _safe_id(handle, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        with self._lock:
            session = self._sessions_by_handle.get(safe_handle)
            if session is None:
                raise SpineError(RUNTIME_INVALID_SESSION)
            return session


#: The persisted lifecycle states a snapshot can carry — the projection statuses
#: the adapter ever mirrors into the canonical log (``orphaned``/``ambiguous`` are
#: transient/health states, never a persisted lifecycle state).
_LIFECYCLE_STATES = frozenset(
    {"running", "permission_wait", "completed", "failed", "cancelled"}
)

LIFECYCLE_SNAPSHOT_TYPE = "sachima.runtime_spine.agent_run_supervisor_lifecycle_snapshot.v1"


def _check_lifecycle_snapshot_fields(snap: Any) -> None:
    """Exact fail-closed validation of a lifecycle snapshot's fields.

    Fails closed on: an unsafe ``task_id`` / ``session_id``; a non-lifecycle
    ``state``; a non-``bool`` flag; a flag inconsistent with ``state``; a negative /
    non-``int`` count; or the cross-field invariants a genuine snapshot always holds
    (``last_seq == event_count`` for a gap-free ``1..N`` log, ``attach_count`` never
    exceeding ``event_count``). It never echoes the rejected material.
    """

    try:
        task_id = snap.task_id
        session_id = snap.session_id
        state = snap.state
        alive = snap.alive
        terminal = snap.terminal
        permission_wait = snap.permission_wait
        resumable = snap.resumable
        last_seq = snap.last_seq
        event_count = snap.event_count
        attach_count = snap.attach_count
    except AttributeError as exc:
        raise SpineError(RUNTIME_INVALID_SESSION) from exc

    safe_task_id(task_id, code=RUNTIME_INVALID_SESSION)
    if type(session_id) is not str or not session_id.startswith("sess_"):
        raise SpineError(RUNTIME_INVALID_SESSION)
    _safe_id(session_id, code=RUNTIME_INVALID_SESSION)
    if state not in _LIFECYCLE_STATES:
        raise SpineError(RUNTIME_INVALID_SESSION)
    for flag in (alive, terminal, permission_wait, resumable):
        if type(flag) is not bool:
            raise SpineError(RUNTIME_INVALID_SESSION)
    if alive is not (state in LIVE_SESSION_STATES):
        raise SpineError(RUNTIME_INVALID_SESSION)
    if terminal is not (state in TERMINAL_SESSION_STATES):
        raise SpineError(RUNTIME_INVALID_SESSION)
    if permission_wait is not (state == "permission_wait"):
        raise SpineError(RUNTIME_INVALID_SESSION)
    if resumable is not alive:
        raise SpineError(RUNTIME_INVALID_SESSION)
    # bool is an int subclass — exclude it so a flag can't pose as a count.
    for count in (last_seq, event_count, attach_count):
        if type(count) is not int or count < 0:
            raise SpineError(RUNTIME_INVALID_SESSION)
    if last_seq != event_count or attach_count > event_count:
        raise SpineError(RUNTIME_INVALID_SESSION)


@dataclass(frozen=True)
class LifecycleSnapshot:
    """Refs-only persistent-lifecycle snapshot for safe stream resume.

    Built by :meth:`AgentRunSupervisorPort.lifecycle_snapshot` / :meth:`close` from
    persisted Sachima state only (the Status Projection + Task Event Log) — it makes
    no backend call and mutates nothing, so it is a stable read even while the
    injected backend is unreachable. It carries only refs / counts / states /
    booleans: ``last_seq`` (the cursor a caller passes to ``stream(since_seq=...)``),
    ``event_count`` (equal to ``last_seq`` for a gap-free ``1..N`` log), and
    ``attach_count`` (the number of ``agent_attached`` events, which stays ``1``
    across a lifecycle re-attach — proof that reconstruction replays no duplicate
    attach). ``__post_init__`` re-runs the full allowlist so a directly constructed
    or forged snapshot fails closed instead of being trusted.
    """

    task_id: str
    session_id: str
    state: str
    alive: bool
    terminal: bool
    permission_wait: bool
    resumable: bool
    last_seq: int
    event_count: int
    attach_count: int

    def __post_init__(self) -> None:
        _check_lifecycle_snapshot_fields(self)

    def to_projection(self) -> dict[str, Any]:
        """Deterministic refs-only projection, safe to surface as evidence."""

        return {
            "type": LIFECYCLE_SNAPSHOT_TYPE,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "state": self.state,
            "alive": self.alive,
            "terminal": self.terminal,
            "permission_wait": self.permission_wait,
            "resumable": self.resumable,
            "last_seq": self.last_seq,
            "event_count": self.event_count,
            "attach_count": self.attach_count,
        }


def validate_lifecycle_snapshot(snap: LifecycleSnapshot) -> LifecycleSnapshot:
    """Re-validate a snapshot at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type or any unsafe / inconsistent field fails
    closed with the stable ``runtime_invalid_session`` code, never echoing material.
    """

    if type(snap) is not LifecycleSnapshot:
        raise SpineError(RUNTIME_INVALID_SESSION)
    _check_lifecycle_snapshot_fields(snap)
    return snap


@dataclass
class _PortSession:
    ref: SessionRef
    handle: str
    launch_key: tuple[Any, ...]
    emitted_state: str = "running"


class AgentRunSupervisorPort(ExecutionPort):
    """ExecutionPort adapter over an injected agent-run-supervisor backend."""

    def __init__(
        self,
        registry: TaskRegistry,
        backend: AgentRunSupervisorBackend | None = None,
    ) -> None:
        if type(registry) is not TaskRegistry:
            raise SpineError(RUNTIME_INVALID_SESSION)
        self._backend: AgentRunSupervisorBackend = (
            DefaultAgentRunSupervisorBackend() if backend is None else backend
        )
        if not isinstance(self._backend, AgentRunSupervisorBackend):
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        self._registry = registry
        self._sessions: dict[str, _PortSession] = {}
        self._ids = itertools.count(1)
        self._lock = threading.RLock()

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def create_or_attach(self, task_id: str, launch_spec: LaunchSpec) -> SessionRef:
        safe_task = safe_task_id(task_id)
        self._validate_launch_for_supervisor(safe_task, launch_spec)
        launch_key = self._launch_key(launch_spec)
        with self._lock:
            existing = self._sessions.get(safe_task)
            if existing is not None:
                if existing.launch_key != launch_key:
                    raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
                return existing.ref
            record = self._registry.get_record(safe_task)
            existing_session_id = self._attached_session_id(safe_task)
            if record is not None:
                existing_refs = self._task_creation_refs(safe_task)
                if (
                    record.needs_agent is not launch_spec.needs_agent
                    or record.needs_durable is not launch_spec.needs_durable
                    or existing_refs != frozenset(launch_spec.refs)
                ):
                    raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)

            if (
                existing_session_id is None
                and self._projected_terminal_state(safe_task) is not None
            ):
                raise SpineError(RUNTIME_INVALID_SESSION)

            new_backend_handle = existing_session_id is None
            if existing_session_id is not None:
                handle = self._attached_handle(safe_task)
                if handle is None:
                    raise SpineError(RUNTIME_INVALID_SESSION)
                state = self._backend_state(handle, op="status")
            else:
                handle = self._backend_create_or_attach(safe_task, launch_spec.refs)
                try:
                    state = self._backend_state(handle, op="status")
                except SpineError:
                    self._best_effort_backend_kill(handle, "ref_backend_status_failed")
                    raise
            # Validate the backend state before mutating Sachima state. A bad
            # backend response must not leave a half-written task/session.
            session_id = existing_session_id or f"sess_{next(self._ids)}"
            try:
                self._status_fields(safe_task, session_id, state, 0, None)

                if record is None:
                    try:
                        self._registry.create_task(
                            safe_task,
                            needs_agent=launch_spec.needs_agent,
                            needs_durable=launch_spec.needs_durable,
                            refs=tuple(launch_spec.refs),
                        )
                    except SpineError as exc:
                        if exc.code != RUNTIME_INVALID_TASK_RECORD:
                            raise
                        record = self._registry.get_record(safe_task)
                        if record is None:
                            raise SpineError(RUNTIME_INVALID_TASK_RECORD) from None
                        existing_refs = self._task_creation_refs(safe_task)
                        if (
                            record.needs_agent is not launch_spec.needs_agent
                            or record.needs_durable is not launch_spec.needs_durable
                            or existing_refs != frozenset(launch_spec.refs)
                        ):
                            raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC) from None
                        raced_session_id = self._attached_session_id(safe_task)
                        if raced_session_id is not None:
                            existing_session_id = raced_session_id
                            session_id = raced_session_id
                        elif self._projected_terminal_state(safe_task) is not None:
                            raise SpineError(RUNTIME_INVALID_SESSION) from None
                if existing_session_id is None:
                    self._registry.append_event(
                        safe_task,
                        build_event_body(
                            event_type="agent_attached",
                            status="running",
                            refs=(session_id,),
                        ),
                    )
            except SpineError:
                if new_backend_handle:
                    self._best_effort_backend_kill(handle, "ref_create_aborted")
                raise
            ref = SessionRef(task_id=safe_task, session_id=session_id)
            session = _PortSession(
                ref=ref,
                handle=handle,
                launch_key=launch_key,
                emitted_state=self._projected_session_state(safe_task),
            )
            self._sessions[safe_task] = session
            self._sync_backend_state_locked(safe_task, session, state)
            return ref

    def restore_attached(
        self, task_id: str, launch_spec: LaunchSpec, *, session_id: str
    ) -> SessionRef:
        """Re-attach a **sealed** session after a restart. Creates nothing.

        ``create_or_attach`` is the admission door: it will mint a backend
        session when it finds none, which is exactly right for a new task and
        exactly wrong for a restart. A restored task already *has* a Session —
        the durable record names it — so this door only reconnects to one:
        it asks the backend to attach an existing task and fails closed if the
        backend cannot, rather than starting a second Session beside a Run that
        may still be executing.

        The sealed ``session_id`` comes from the host's own durable record, not
        from this port's counter. Minting a fresh ``sess_N`` here would give the
        restored conversation a different identity from the one its accepted Run,
        its result envelope, and its recovery record all name.

        Idempotent: restoring twice attaches once and appends one
        ``agent_attached`` event, so a repeated startup scan cannot make a task
        look like it attached twice.
        """

        safe_task = safe_task_id(task_id)
        self._validate_launch_for_supervisor(safe_task, launch_spec)
        sealed = _safe_id(session_id, code=RUNTIME_INVALID_SESSION)
        if not sealed.startswith("sess_"):
            raise SpineError(RUNTIME_INVALID_SESSION)
        launch_key = self._launch_key(launch_spec)
        with self._lock:
            existing = self._sessions.get(safe_task)
            if existing is not None:
                if existing.launch_key != launch_key or existing.ref.session_id != sealed:
                    raise SpineError(RUNTIME_INVALID_SESSION)
                return existing.ref

            handle = self._attached_handle(safe_task)
            if handle is None:
                # No backend session to attach to. Restoration never creates
                # one: that decision belongs to an admission, not a restart.
                raise SpineError(RUNTIME_INVALID_SESSION)

            record = self._registry.get_record(safe_task)
            if record is None:
                self._registry.create_task(
                    safe_task,
                    needs_agent=launch_spec.needs_agent,
                    needs_durable=launch_spec.needs_durable,
                    refs=tuple(launch_spec.refs),
                )
            else:
                existing_refs = self._task_creation_refs(safe_task)
                if (
                    record.needs_agent is not launch_spec.needs_agent
                    or record.needs_durable is not launch_spec.needs_durable
                    or existing_refs != frozenset(launch_spec.refs)
                ):
                    raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)

            attached = self._attached_session_id(safe_task)
            if attached is None:
                self._registry.append_event(
                    safe_task,
                    build_event_body(
                        event_type="agent_attached",
                        status="running",
                        refs=(sealed,),
                    ),
                )
            elif attached != sealed:
                # The log already names a different session for this task; a
                # restore may reconnect, never re-identify.
                raise SpineError(RUNTIME_INVALID_SESSION)

            ref = SessionRef(task_id=safe_task, session_id=sealed)
            self._sessions[safe_task] = _PortSession(
                ref=ref,
                handle=handle,
                launch_key=launch_key,
                emitted_state=self._projected_session_state(safe_task),
            )
            return ref

    def stream(
        self, ref: str | SessionRef, *, since_seq: int | None = None
    ) -> tuple[dict[str, Any], ...]:
        """Return refs-only registry projections, optionally resumed from a cursor.

        ``since_seq`` is a resume cursor (a last-seen ``seq``): when given, only
        events with ``seq > since_seq`` are returned, so a caller resumes exactly the
        tail it has not seen with no duplicate replay. A lifecycle re-attach appends
        no events, so resuming from the pre-attach ``last_seq`` yields nothing.
        """

        safe_task = self._resolve_task(ref)
        cursor = self._validate_cursor(since_seq)
        with self._lock:
            session = self._get_session(safe_task)
            state = self._backend_state(session.handle, op="status")
            self._sync_backend_state_locked(safe_task, session, state)
            events = self._registry.log.events_for(safe_task)
            if cursor is not None:
                events = tuple(event for event in events if event.seq > cursor)
            return tuple(event_projection(event) for event in events)

    def signal(self, task_id: str, decision_ref: str) -> SessionStatus:
        safe_task = safe_task_id(task_id)
        safe_decision_ref = _safe_ref(decision_ref)
        with self._lock:
            session = self._get_session(safe_task)
            if self._projected_terminal_state(safe_task) is not None:
                raise SpineError(RUNTIME_INVALID_SESSION)
            current = self._backend_state(session.handle, op="status")
            if current != "permission_wait":
                raise SpineError(RUNTIME_INVALID_SESSION)
            self._sync_backend_state_locked(safe_task, session, current)
            next_state = self._backend_signal(session.handle, safe_decision_ref)
            if next_state != "running" and next_state not in TERMINAL_SESSION_STATES:
                raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)
            self._registry.append_event(
                safe_task,
                build_event_body(
                    event_type="permission_answered",
                    status="running",
                    refs=(session.ref.session_id, safe_decision_ref),
                ),
            )
            session.emitted_state = "running"
            if next_state in TERMINAL_SESSION_STATES:
                self._sync_backend_state_locked(safe_task, session, next_state)
            return self.status(session.ref)

    def status(self, ref: str | SessionRef) -> SessionStatus:
        """Return projection-derived + backend-mapped status for a session.

        PR3 read-failure policy: a backend status read fault collapses to the stable
        ``runtime_supervisor_backend_failure`` code (raised by ``_backend_state``)
        before anything is appended, so the existing persisted session/log is neither
        marked, killed, nor mutated; a subsequent successful read resumes it.
        """

        safe_task = self._resolve_task(ref)
        with self._lock:
            session = self._get_session(safe_task)
            state = self._backend_state(session.handle, op="status")
            self._sync_backend_state_locked(safe_task, session, state)
            snapshot = self._registry.snapshot(safe_task)
            projected_status = snapshot["status"] if snapshot is not None else None
            last_seq = snapshot["last_seq"] if snapshot is not None else 0
            terminal_state = self._projected_terminal_state(safe_task)
            effective_state = terminal_state or state
            return self._status_fields(
                safe_task, session.ref.session_id, effective_state, last_seq, projected_status
            )

    def kill(self, ref: str | SessionRef, reason_ref: str = "ref_cancelled") -> SessionStatus:
        safe_task = self._resolve_task(ref)
        safe_reason = _safe_id(reason_ref, code=RUNTIME_INVALID_EVENT)
        with self._lock:
            session = self._get_session(safe_task)
            if self._projected_terminal_state(safe_task) is not None:
                return self.status(session.ref)
            current = self._backend_state(session.handle, op="status")
            if current in TERMINAL_SESSION_STATES:
                self._sync_backend_state_locked(safe_task, session, current)
                return self.status(session.ref)
            next_state = self._backend_kill(session.handle, safe_reason)
            if next_state == "cancelled":
                self._registry.append_event(
                    safe_task,
                    build_event_body(
                        event_type="cancelled",
                        status="cancelled",
                        refs=(session.ref.session_id, safe_reason),
                    ),
                )
                session.emitted_state = "cancelled"
                return self.status(session.ref)
            if next_state in TERMINAL_SESSION_STATES:
                self._sync_backend_state_locked(safe_task, session, next_state)
                return self.status(session.ref)
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)

    def liveness(self, ref: str | SessionRef) -> LivenessState:
        """Return liveness for an existing session; ``permission_wait`` is alive.

        PR3 read-failure policy: a backend liveness read fault collapses to the
        stable ``runtime_supervisor_backend_failure`` code (raised by
        ``_backend_liveness``) and never marks, kills, or orphans the existing
        session — nothing is appended, so a later successful read resumes it. An
        ``orphaned`` backend state is surfaced as ``reapable`` here but is not
        auto-written to the canonical log; the reap decision belongs to a reaper.
        """

        safe_task = self._resolve_task(ref)
        session = self._get_session(safe_task)
        terminal_state = self._projected_terminal_state(safe_task)
        state = terminal_state or self._backend_liveness(session.handle)
        return LivenessState(
            task_id=safe_task,
            session_id=session.ref.session_id,
            state=state,
            alive=state in LIVE_SESSION_STATES,
            permission_wait=state == "permission_wait",
            reapable=state == "orphaned",
        )

    def lifecycle_snapshot(self, ref: str | SessionRef) -> LifecycleSnapshot:
        """Refs-only persistent-lifecycle snapshot (no backend call, no mutation).

        Reads persisted Sachima state only (Status Projection + log), so it is a
        stable resume-data read even while the injected backend is unreachable — the
        PR3 policy that a transient backend read failure never marks/kills/mutates an
        existing session holds here by construction (there is no backend call). The
        snapshot's ``last_seq`` is the cursor to pass to ``stream(since_seq=...)``.
        """

        safe_task = self._resolve_task(ref)
        with self._lock:
            return self._lifecycle_snapshot_locked(safe_task)

    def close(self, ref: str | SessionRef) -> LifecycleSnapshot:
        """Adapter-local, default-off port handoff — drop local tracking only.

        Releases *this* port's in-memory tracking for ``task_id`` WITHOUT killing the
        backend session, appending any event, or mutating the registry, so a port
        reconstructed over the same registry + backend re-attaches the still-live
        session (no respawn, no duplicate ``agent_attached``). It is never called
        automatically anywhere in the adapter — the supervisor owns the real session
        lifecycle — and fails closed on an untracked/forged ref, so it can never
        resurrect a session and a second ``close`` is rejected. Returns the refs-only
        snapshot captured just before the drop.
        """

        safe_task = self._resolve_task(ref)
        with self._lock:
            snapshot = self._lifecycle_snapshot_locked(safe_task)
            self._sessions.pop(safe_task, None)
            return snapshot

    def _lifecycle_snapshot_locked(self, safe_task: str) -> LifecycleSnapshot:
        session = self._get_session(safe_task)  # fail closed unless locally tracked
        state = self._projected_session_state(safe_task)
        snapshot = self._registry.snapshot(safe_task)
        last_seq = snapshot["last_seq"] if snapshot is not None else 0
        event_count = snapshot["event_count"] if snapshot is not None else 0
        return LifecycleSnapshot(
            task_id=safe_task,
            session_id=session.ref.session_id,
            state=state,
            alive=state in LIVE_SESSION_STATES,
            terminal=state in TERMINAL_SESSION_STATES,
            permission_wait=state == "permission_wait",
            resumable=state in LIVE_SESSION_STATES,
            last_seq=last_seq,
            event_count=event_count,
            attach_count=self._attach_event_count(safe_task),
        )

    def _attach_event_count(self, safe_task: str) -> int:
        return sum(
            1
            for event in self._registry.log.events_for(safe_task)
            if event.event_type == "agent_attached"
        )

    @staticmethod
    def _validate_cursor(since_seq: int | None) -> int | None:
        if since_seq is None:
            return None
        # bool is an int subclass — exclude it so a flag can't pose as a cursor.
        if type(since_seq) is not int or since_seq < 0:
            raise SpineError(RUNTIME_INVALID_SESSION)
        return since_seq

    @staticmethod
    def _validate_launch_for_supervisor(safe_task: str, spec: LaunchSpec) -> None:
        try:
            validate_launch_spec(spec)
        except SpineError:
            raise
        if (
            spec.task_id != safe_task
            or spec.needs_agent is not True
            or spec.agent_kind != _SUPERVISOR_AGENT_KIND
        ):
            raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
        if spec.roles != (_ALLOWED_ROLE,):
            raise SpineError(RUNTIME_SUPERVISOR_POLICY_DENIED)
        refs = tuple(spec.refs)
        if not any(ref.startswith(_WORKSPACE_REF_PREFIX) for ref in refs):
            raise SpineError(RUNTIME_SUPERVISOR_POLICY_DENIED)
        if not any(ref.startswith(_POLICY_REF_PREFIX) for ref in refs):
            raise SpineError(RUNTIME_SUPERVISOR_POLICY_DENIED)

    @staticmethod
    def _launch_key(spec: LaunchSpec) -> tuple[Any, ...]:
        return (
            spec.agent_kind,
            spec.needs_agent,
            spec.needs_durable,
            spec.required_capabilities,
            spec.roles,
            frozenset(spec.refs),
        )

    def _resolve_task(self, ref: str | SessionRef) -> str:
        if type(ref) is str:
            safe_task = safe_task_id(ref)
            if safe_task not in self._sessions:
                raise SpineError(RUNTIME_INVALID_SESSION)
            return safe_task
        session_ref = validate_session_ref(cast(SessionRef, ref))
        session = self._sessions.get(session_ref.task_id)
        if session is None or session.ref != session_ref:
            raise SpineError(RUNTIME_INVALID_SESSION)
        return session_ref.task_id

    def _get_session(self, safe_task: str) -> _PortSession:
        session = self._sessions.get(safe_task)
        if session is None:
            raise SpineError(RUNTIME_INVALID_SESSION)
        return session

    def _task_creation_refs(self, safe_task: str) -> frozenset[str]:
        for event in self._registry.log.events_for(safe_task):
            if event.event_type == "task_created":
                return frozenset(event.refs)
        raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)

    def _attached_session_id(self, safe_task: str) -> str | None:
        attached: str | None = None
        for event in self._registry.log.events_for(safe_task):
            if event.event_type != "agent_attached":
                continue
            for ref in event.refs:
                if ref.startswith("sess_"):
                    attached = ref
        return attached

    def _attached_handle(self, safe_task: str) -> str | None:
        try:
            handle = self._backend.attach_existing(safe_task)
        except SpineError as exc:
            if exc.code == RUNTIME_INVALID_SESSION:
                return None
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE) from None
        except BaseException:
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE) from None
        return _safe_id(handle, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)

    def _projected_session_state(self, safe_task: str) -> str:
        snapshot = self._registry.snapshot(safe_task)
        status = snapshot["status"] if snapshot is not None else None
        if status in {"running", "permission_wait", "completed", "failed", "cancelled"}:
            return cast(str, status)
        return "running"

    def _projected_terminal_state(self, safe_task: str) -> str | None:
        snapshot = self._registry.snapshot(safe_task)
        if snapshot is None or snapshot["terminal"] is not True:
            return None
        status = snapshot["status"]
        if status in TERMINAL_SESSION_STATES:
            return cast(str, status)
        raise SpineError(RUNTIME_INVALID_SESSION)

    def _sync_backend_state_locked(
        self, safe_task: str, session: _PortSession, state: str
    ) -> None:
        """Mirror observable backend lifecycle transitions into the event log.

        The Task Event Log is the canonical projection source, so a backend state
        discovered by ``status``/``stream`` must not live only in the transient
        ``SessionStatus`` return value. This method appends one refs-only event
        per meaningful state transition and is idempotent for repeated reads.
        """
        if state == session.emitted_state:
            return
        terminal_state = self._projected_terminal_state(safe_task)
        if terminal_state is not None:
            session.emitted_state = terminal_state
            return
        if session.emitted_state in TERMINAL_SESSION_STATES:
            return
        event_body = self._event_for_backend_state(session.ref.session_id, state)
        if event_body is None:
            return
        self._registry.append_event(safe_task, event_body)
        session.emitted_state = state

    @staticmethod
    def _event_for_backend_state(session_id: str, state: str) -> dict[str, Any] | None:
        if state == "running":
            return build_event_body(
                event_type="progress", status="running", refs=(session_id,)
            )
        if state == "permission_wait":
            return build_event_body(
                event_type="permission_requested",
                status="permission_wait",
                refs=(session_id,),
            )
        if state == "completed":
            return build_event_body(
                event_type="completed", status="completed", refs=(session_id,)
            )
        if state == "failed":
            return build_event_body(
                event_type="failed", status="failed", refs=(session_id,)
            )
        if state == "cancelled":
            return build_event_body(
                event_type="cancelled", status="cancelled", refs=(session_id,)
            )
        if state == "ambiguous":
            return build_event_body(
                event_type="failed", status="failed", refs=(session_id,)
            )
        # ``orphaned`` is a session-health state with no R1 projection status.
        # Keep it on SessionStatus/LivenessState only until a reaper decides.
        return None

    @staticmethod
    def _map_backend_state(value: Any) -> str:
        if type(value) is not str:
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        mapped = _BACKEND_TO_SESSION_STATE.get(value)
        if mapped is None:
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        return mapped

    def _backend_create_or_attach(self, safe_task: str, refs: tuple[str, ...]) -> str:
        try:
            handle = self._backend.create_or_attach(safe_task, tuple(refs))
        except BaseException:  # noqa: BLE001 - injected backend no-leak boundary
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE) from None
        return _safe_id(handle, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)

    def _best_effort_backend_kill(self, handle: str, reason_ref: str) -> None:
        try:
            safe_handle = _safe_id(handle, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
            safe_reason = _safe_ref(reason_ref)
            self._backend.kill(safe_handle, safe_reason)
        except BaseException:
            return None

    def _backend_state(self, handle: str, *, op: str) -> str:
        try:
            if op == "status":
                value = self._backend.status(handle)
            else:  # pragma: no cover - internal call guard
                raise AssertionError("unknown backend state op")
        except BaseException:
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE) from None
        return self._map_backend_state(value)

    def _backend_signal(self, handle: str, decision_ref: str) -> str:
        try:
            value = self._backend.signal(handle, decision_ref)
        except BaseException:
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE) from None
        return self._map_backend_state(value)

    def _backend_kill(self, handle: str, reason_ref: str) -> str:
        try:
            value = self._backend.kill(handle, reason_ref)
        except BaseException:
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE) from None
        return self._map_backend_state(value)

    def _backend_liveness(self, handle: str) -> str:
        try:
            value = self._backend.liveness(handle)
        except BaseException:
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE) from None
        return self._map_backend_state(value)

    @staticmethod
    def _status_fields(
        task_id: str,
        session_id: str,
        state: str,
        last_seq: int,
        projected_status: str | None,
    ) -> SessionStatus:
        if projected_status is not None and projected_status not in _PROJECTED_STATUSES:
            raise SpineError(RUNTIME_INVALID_SESSION)
        return SessionStatus(
            task_id=task_id,
            session_id=session_id,
            state=state,
            alive=state in LIVE_SESSION_STATES,
            terminal=state in TERMINAL_SESSION_STATES,
            last_seq=last_seq,
            projected_status=projected_status,
        )


__all__ = [
    "RUNTIME_SUPERVISOR_BACKEND_FAILURE",
    "RUNTIME_SUPERVISOR_POLICY_DENIED",
    "SUPERVISOR_PORT_STABLE_CODES",
    "LIFECYCLE_SNAPSHOT_TYPE",
    "AgentRunSupervisorBackend",
    "DefaultAgentRunSupervisorBackend",
    "AgentRunSupervisorPort",
    "LifecycleSnapshot",
    "validate_lifecycle_snapshot",
]
