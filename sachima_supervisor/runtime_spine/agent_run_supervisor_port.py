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

    def stream(self, ref: str | SessionRef) -> tuple[dict[str, Any], ...]:
        safe_task = self._resolve_task(ref)
        with self._lock:
            session = self._get_session(safe_task)
            state = self._backend_state(session.handle, op="status")
            self._sync_backend_state_locked(safe_task, session, state)
            return tuple(event_projection(event) for event in self._registry.log.events_for(safe_task))

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
    "AgentRunSupervisorBackend",
    "DefaultAgentRunSupervisorBackend",
    "AgentRunSupervisorPort",
]
