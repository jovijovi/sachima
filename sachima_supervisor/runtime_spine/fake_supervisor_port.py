"""R2 Runtime Spine — deterministic fake supervisor execution port.

The fake port models supervised session semantics over the R1 Task Registry and
Event Log. It is local/offline and deterministic: no real supervisor transport,
no external service, and no live platform integration.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, cast

from .events import (
    RUNTIME_INVALID_LAUNCH_SPEC,
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


@dataclass
class _FakeSession:
    ref: SessionRef
    state: str
    launch_key: tuple[Any, ...]
    pending_permission: bool = False
    orphan_reaped: bool = False


class FakeSupervisorPort(ExecutionPort):
    """Deterministic offline adapter for R2 execution-port tests."""

    def __init__(self, registry: TaskRegistry) -> None:
        if type(registry) is not TaskRegistry:
            raise SpineError(RUNTIME_INVALID_SESSION)
        self._registry = registry
        self._sessions: dict[str, _FakeSession] = {}
        self._ids = itertools.count(1)

    def session_count(self) -> int:
        return len(self._sessions)

    def create_or_attach(self, task_id: str, launch_spec: LaunchSpec) -> SessionRef:
        safe_task = safe_task_id(task_id)
        try:
            validate_launch_spec(launch_spec)
        except SpineError:
            raise
        if launch_spec.task_id != safe_task or launch_spec.needs_agent is not True:
            raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
        launch_key = self._launch_key(launch_spec)
        existing = self._sessions.get(safe_task)
        if existing is not None:
            if existing.launch_key != launch_key:
                raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
            return existing.ref

        record = self._registry.get_record(safe_task)
        if record is not None:
            if (
                record.needs_agent is not launch_spec.needs_agent
                or record.needs_durable is not launch_spec.needs_durable
            ):
                raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
        else:
            self._registry.create_task(
                safe_task,
                needs_agent=launch_spec.needs_agent,
                needs_durable=launch_spec.needs_durable,
                refs=tuple(launch_spec.refs),
            )
        session_id = f"sess_{next(self._ids)}"
        ref = SessionRef(task_id=safe_task, session_id=session_id)
        self._registry.append_event(
            safe_task,
            build_event_body(
                event_type="agent_attached",
                status="running",
                refs=(session_id,),
            ),
        )
        self._sessions[safe_task] = _FakeSession(ref=ref, state="running", launch_key=launch_key)
        return ref

    def stream(self, ref: str | SessionRef) -> tuple[dict[str, Any], ...]:
        safe_task = self._resolve_task(ref)
        return tuple(event_projection(event) for event in self._registry.log.events_for(safe_task))

    def signal(self, task_id: str, decision_ref: str) -> SessionStatus:
        safe_task = safe_task_id(task_id)
        session = self._get_session(safe_task)
        if session.pending_permission is not True or session.state != "permission_wait":
            raise SpineError(RUNTIME_INVALID_SESSION)
        safe_decision_ref = _safe_ref(decision_ref)
        self._registry.append_event(
            safe_task,
            build_event_body(
                event_type="permission_answered",
                status="running",
                refs=(session.ref.session_id, safe_decision_ref),
            ),
        )
        session.pending_permission = False
        session.state = "running"
        return self.status(session.ref)

    def status(self, ref: str | SessionRef) -> SessionStatus:
        safe_task = self._resolve_task(ref)
        session = self._get_session(safe_task)
        snapshot = self._registry.snapshot(safe_task)
        projected_status = snapshot["status"] if snapshot is not None else None
        last_seq = snapshot["last_seq"] if snapshot is not None else 0
        return SessionStatus(
            task_id=safe_task,
            session_id=session.ref.session_id,
            state=session.state,
            alive=session.state in LIVE_SESSION_STATES,
            terminal=session.state in TERMINAL_SESSION_STATES,
            last_seq=last_seq,
            projected_status=projected_status,
        )

    def kill(self, ref: str | SessionRef, reason_ref: str = "ref_cancelled") -> SessionStatus:
        safe_task = self._resolve_task(ref)
        session = self._get_session(safe_task)
        safe_reason = _safe_id(reason_ref)
        if session.state in TERMINAL_SESSION_STATES:
            return self.status(session.ref)
        self._registry.append_event(
            safe_task,
            build_event_body(
                event_type="cancelled",
                status="cancelled",
                refs=(session.ref.session_id, safe_reason),
            ),
        )
        session.pending_permission = False
        session.state = "cancelled"
        return self.status(session.ref)

    def liveness(self, ref: str | SessionRef) -> LivenessState:
        safe_task = self._resolve_task(ref)
        session = self._get_session(safe_task)
        state = session.state
        if state == "orphaned" and session.orphan_reaped:
            state = "failed"
        return LivenessState(
            task_id=safe_task,
            session_id=session.ref.session_id,
            state=state,
            alive=state in LIVE_SESSION_STATES,
            permission_wait=state == "permission_wait",
            reapable=state == "orphaned",
        )

    def request_permission(self, ref: str | SessionRef, prompt_ref: str) -> SessionStatus:
        safe_task = self._resolve_task(ref)
        session = self._get_session(safe_task)
        if session.state not in LIVE_SESSION_STATES:
            raise SpineError(RUNTIME_INVALID_SESSION)
        safe_prompt = _safe_ref(prompt_ref)
        self._registry.append_event(
            safe_task,
            build_event_body(
                event_type="permission_requested",
                status="permission_wait",
                refs=(session.ref.session_id, safe_prompt),
            ),
        )
        session.pending_permission = True
        session.state = "permission_wait"
        return self.status(session.ref)

    def emit_progress(self, ref: str | SessionRef, *, refs: tuple[str, ...] = ()) -> SessionStatus:
        safe_task = self._resolve_task(ref)
        session = self._get_session(safe_task)
        if session.state not in LIVE_SESSION_STATES:
            raise SpineError(RUNTIME_INVALID_SESSION)
        safe_refs = tuple(_safe_ref(item) for item in refs)
        self._registry.append_event(
            safe_task,
            build_event_body(
                event_type="progress",
                status=session.state,
                refs=(session.ref.session_id, *safe_refs),
            ),
        )
        return self.status(session.ref)

    def complete(self, ref: str | SessionRef, *, result_ref: str) -> SessionStatus:
        safe_task = self._resolve_task(ref)
        session = self._get_session(safe_task)
        if session.state in TERMINAL_SESSION_STATES:
            return self.status(session.ref)
        safe_result = _safe_ref(result_ref)
        self._registry.append_event(
            safe_task,
            build_event_body(
                event_type="completed",
                status="completed",
                refs=(session.ref.session_id, safe_result),
            ),
        )
        session.pending_permission = False
        session.state = "completed"
        return self.status(session.ref)

    def simulate_orphan(self, ref: str | SessionRef) -> LivenessState:
        safe_task = self._resolve_task(ref)
        session = self._get_session(safe_task)
        if session.state != "running":
            raise SpineError(RUNTIME_INVALID_SESSION)
        session.state = "orphaned"
        session.pending_permission = False
        session.orphan_reaped = False
        return self.liveness(session.ref)

    def reap_orphans(self) -> tuple[SessionRef, ...]:
        reaped: list[SessionRef] = []
        for safe_task in sorted(self._sessions):
            session = self._sessions[safe_task]
            if session.state != "orphaned" or session.orphan_reaped:
                continue
            self._registry.append_event(
                safe_task,
                build_event_body(
                    event_type="failed",
                    status="failed",
                    refs=(session.ref.session_id, "ref_orphan_reaped"),
                ),
            )
            session.state = "failed"
            session.orphan_reaped = True
            reaped.append(session.ref)
        return tuple(reaped)

    @staticmethod
    def _launch_key(spec: LaunchSpec) -> tuple[Any, ...]:
        return (
            spec.agent_kind,
            spec.needs_agent,
            spec.needs_durable,
            spec.required_capabilities,
            spec.roles,
            spec.refs,
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

    def _get_session(self, safe_task: str) -> _FakeSession:
        session = self._sessions.get(safe_task)
        if session is None:
            raise SpineError(RUNTIME_INVALID_SESSION)
        return session
