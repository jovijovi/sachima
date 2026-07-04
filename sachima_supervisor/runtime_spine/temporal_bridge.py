"""R3 Runtime Spine — Temporal attach-only durable bridge contract (local/offline).

This module models a durable orchestrator layered over an *existing* supervisor
session. Its single activity — ``agent_run_attach_existing`` — only ever attaches
to a session that already exists: it takes an exact
:class:`~sachima_supervisor.runtime_spine.execution_port.SessionRef` and must
never create, spawn, or relaunch an AGENT, never start a durable runner / service
/ background loop, and never touch any live platform or delivery surface. It
records liveness by appending exactly one refs-only progress event through the R1
Task Registry, and returns a refs-only, stable-code-sanitized result.

Everything here is pure local/offline Python. Importing it starts no OS process,
opens no listeners, wires no live platform, and runs no agent. The tokens the R3
static tripwire forbids appear nowhere in this file — not even as denylist
canaries; the R3-specific no-leak markers below are deliberately narrow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NoReturn

from .events import (
    SpineError,
    _safe_count,
    _safe_id,
    _safe_kind,
    build_event_body,
    safe_task_id,
    scan_for_leak,
)
from .execution_port import (
    ExecutionPort,
    SessionRef,
    validate_liveness_state,
    validate_session_ref,
    validate_session_status,
)
from .registry import TaskRegistry

# --------------------------------------------------------------------------- #
# Stable error-code family (fail-closed; the message is the code, never input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_TEMPORAL_BRIDGE = "runtime_invalid_temporal_bridge"
BRIDGE_STABLE_CODES = frozenset({RUNTIME_INVALID_TEMPORAL_BRIDGE})

#: Closed heartbeat phase vocabulary. Attach/observe phases only — nothing that
#: implies creating a session or starting a durable runner/service.
BRIDGE_PHASES = frozenset(
    {"attaching", "running", "permission_wait", "draining", "completed", "failed", "cancelled"}
)

#: Exact key set a mapping heartbeat may carry — refs-only, no launch material.
_HEARTBEAT_KEYS = frozenset({"cursor_ref", "phase", "counters", "refs"})

#: Extra no-leak markers layered on top of the R1 denylist: raw material and
#: session-lifecycle verbs must never appear inside an attach-only heartbeat ref.
_BRIDGE_EXTRA_MARKERS = ("raw_", "spawn", "relaunch")


class _FrozenCounterDict(dict):
    """Dict-shaped immutable counter bag for heartbeat public surfaces."""

    def _readonly(self, *_args: Any, **_kwargs: Any) -> NoReturn:
        raise TypeError("heartbeat counters are immutable")

    def __setitem__(self, key: Any, value: Any) -> None:
        self._readonly(key, value)

    def __delitem__(self, key: Any) -> None:
        self._readonly(key)

    def clear(self) -> None:
        self._readonly()

    def pop(self, key: Any, default: Any = None) -> Any:
        self._readonly(key, default)

    def popitem(self) -> Any:
        self._readonly()

    def setdefault(self, key: Any, default: Any = None) -> Any:
        self._readonly(key, default)

    def update(self, *args: Any, **kwargs: Any) -> None:
        self._readonly(*args, **kwargs)

    def __ior__(self, other: Any) -> "_FrozenCounterDict":
        self._readonly(other)


#: Statuses a live, attached session may report back through the bridge result.
_RESULT_STATUSES = frozenset({"running", "permission_wait"})


def _invalid() -> NoReturn:
    """Fail closed with the single stable R3 code — never echoing raw material."""

    raise SpineError(RUNTIME_INVALID_TEMPORAL_BRIDGE)


# --------------------------------------------------------------------------- #
# Heartbeat payload — refs-only, exact shape, fail-closed validation
# --------------------------------------------------------------------------- #
def _validate_heartbeat_fields(
    cursor_ref: Any, phase: Any, counters: Any, refs: Any
) -> tuple[dict[str, int], tuple[str, ...]]:
    """Validate the four heartbeat fields and return sanitized counters/refs.

    Fails closed on: a non-mapping ``counters`` or non-tuple ``refs``; any
    forbidden/raw marker in a key or value; an unsafe ``cursor_ref``; an unknown
    ``phase``; a non-``str`` counter key or non-``int`` (bool excluded) counter
    value; an unsafe ref. Returns a fresh counters dict + refs tuple so the stored
    payload can never alias caller-owned mutable material.
    """

    if type(counters) not in {dict, _FrozenCounterDict} or type(refs) is not tuple:
        _invalid()
    material = {"cursor_ref": cursor_ref, "phase": phase, "counters": counters, "refs": refs}
    if scan_for_leak(material, canaries=_BRIDGE_EXTRA_MARKERS) is not None:
        _invalid()
    _safe_id(cursor_ref, code=RUNTIME_INVALID_TEMPORAL_BRIDGE)
    if phase not in BRIDGE_PHASES:
        _invalid()
    safe_counters = _FrozenCounterDict(
        {
            _safe_kind(key, code=RUNTIME_INVALID_TEMPORAL_BRIDGE): _safe_count(
                value, code=RUNTIME_INVALID_TEMPORAL_BRIDGE
            )
            for key, value in counters.items()
        }
    )
    safe_refs = tuple(_safe_id(ref, code=RUNTIME_INVALID_TEMPORAL_BRIDGE) for ref in refs)
    return safe_counters, safe_refs


@dataclass(frozen=True)
class HeartbeatPayload:
    """A refs-only heartbeat: a cursor ref, a safe phase, counters, and refs.

    ``HeartbeatPayload`` is exported public surface, so construction alone must
    never be grounds for trust: ``__post_init__`` re-runs the full refs-only
    allowlist and stores freshly sanitized ``counters`` / ``refs`` so a direct
    ``HeartbeatPayload(...)`` carrying unsafe / raw / launch material fails closed
    instead of leaking.
    """

    cursor_ref: str
    phase: str
    counters: dict[str, int] = field(default_factory=dict)
    refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        safe_counters, safe_refs = _validate_heartbeat_fields(
            self.cursor_ref, self.phase, self.counters, self.refs
        )
        object.__setattr__(self, "counters", safe_counters)
        object.__setattr__(self, "refs", safe_refs)


def validate_heartbeat_payload(payload: Any) -> HeartbeatPayload:
    """Validate a heartbeat and return a sanitized :class:`HeartbeatPayload`.

    A mapping input is validated for its *exact* key set (so no launch/create
    field and no smuggled marker key slips in) then normalized into a payload; an
    existing ``HeartbeatPayload`` is re-validated in place (defense against
    ``object.__new__`` forgery). Anything else fails closed.
    """

    if type(payload) is HeartbeatPayload:
        safe_counters, safe_refs = _validate_heartbeat_fields(
            payload.cursor_ref, payload.phase, payload.counters, payload.refs
        )
        object.__setattr__(payload, "counters", safe_counters)
        object.__setattr__(payload, "refs", safe_refs)
        return payload
    if type(payload) is dict:
        if set(payload) != _HEARTBEAT_KEYS:
            _invalid()
        return HeartbeatPayload(
            cursor_ref=payload["cursor_ref"],
            phase=payload["phase"],
            counters=payload["counters"],
            refs=payload["refs"],
        )
    _invalid()


# --------------------------------------------------------------------------- #
# AgentRunActivity input — attach-existing only, no launch/create fields
# --------------------------------------------------------------------------- #
def _check_activity_input_fields(activity_input: Any) -> None:
    """Exact fail-closed validation of an attach-only activity input."""

    try:
        task_id = activity_input.task_id
        session_ref = activity_input.session_ref
        heartbeat = activity_input.heartbeat
    except AttributeError:
        _invalid()
    safe_task_id(task_id, code=RUNTIME_INVALID_TEMPORAL_BRIDGE)
    if type(session_ref) is not SessionRef:
        _invalid()
    try:
        validate_session_ref(session_ref)
    except SpineError:
        _invalid()
    # attach-existing: the input's task must be the session ref's own task.
    if session_ref.task_id != task_id:
        _invalid()
    if type(heartbeat) is not HeartbeatPayload:
        _invalid()
    validate_heartbeat_payload(heartbeat)


@dataclass(frozen=True)
class AgentRunActivityInput:
    """Input to the attach-existing agent-run activity.

    Deliberately carries only ``task_id`` + an exact ``session_ref`` + a refs-only
    ``heartbeat`` — no ``launch_spec`` / ``command`` / spawn / relaunch field — so
    the activity can only ever attach to a session that already exists.
    """

    task_id: str
    session_ref: SessionRef
    heartbeat: HeartbeatPayload

    def __post_init__(self) -> None:
        _check_activity_input_fields(self)


def validate_agent_run_activity_input(activity_input: Any) -> AgentRunActivityInput:
    """Re-validate an :class:`AgentRunActivityInput` and return it unchanged."""

    if type(activity_input) is not AgentRunActivityInput:
        _invalid()
    _check_activity_input_fields(activity_input)
    return activity_input


# --------------------------------------------------------------------------- #
# AgentRunActivity result — refs-only, stable-code sanitized
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgentRunActivityResult:
    """Refs-only outcome of one attach-existing activity execution.

    Declares ``side_effects == ()``: the activity created/relaunched nothing and
    owns no process — it only observed liveness and appended one progress event.
    """

    task_id: str
    session_id: str
    status: str
    alive: bool
    heartbeat: HeartbeatPayload
    appended_event_seq: int
    side_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        safe_task_id(self.task_id, code=RUNTIME_INVALID_TEMPORAL_BRIDGE)
        _safe_id(self.session_id, code=RUNTIME_INVALID_TEMPORAL_BRIDGE)
        if self.status not in _RESULT_STATUSES:
            _invalid()
        if type(self.alive) is not bool:
            _invalid()
        if type(self.heartbeat) is not HeartbeatPayload:
            _invalid()
        safe_counters, safe_refs = _validate_heartbeat_fields(
            self.heartbeat.cursor_ref,
            self.heartbeat.phase,
            self.heartbeat.counters,
            self.heartbeat.refs,
        )
        object.__setattr__(
            self,
            "heartbeat",
            HeartbeatPayload(
                cursor_ref=self.heartbeat.cursor_ref,
                phase=self.heartbeat.phase,
                counters=safe_counters,
                refs=safe_refs,
            ),
        )
        # bool is an int subclass — exclude it so a flag can't pose as a seq.
        if type(self.appended_event_seq) is not int or self.appended_event_seq < 1:
            _invalid()
        if self.side_effects != ():
            _invalid()


# --------------------------------------------------------------------------- #
# Workflow contract — orchestrator, not producer
# --------------------------------------------------------------------------- #
def _check_contract_fields(contract: Any) -> None:
    if (
        contract.role != "orchestrator"
        or contract.allowed_activity != "agent_run_attach_existing"
        or contract.attach_only is not True
        or contract.creates_session is not False
        or contract.owns_process is not False
        or contract.starts_worker is not False
        or contract.appends_events is not False
        or contract.side_effects != ()
    ):
        _invalid()


@dataclass(frozen=True)
class TemporalWorkflowContract:
    """The durable workflow's self-declared contract: it orchestrates, it does not
    produce. It attaches only, creates no session, owns no process, starts no
    durable runner, appends no events itself, and has no side effects."""

    role: str = "orchestrator"
    allowed_activity: str = "agent_run_attach_existing"
    attach_only: bool = True
    creates_session: bool = False
    owns_process: bool = False
    starts_worker: bool = False
    appends_events: bool = False
    side_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _check_contract_fields(self)


def validate_workflow_contract(contract: Any) -> TemporalWorkflowContract:
    """Re-validate a :class:`TemporalWorkflowContract` and return it unchanged."""

    if type(contract) is not TemporalWorkflowContract:
        _invalid()
    _check_contract_fields(contract)
    return contract


# --------------------------------------------------------------------------- #
# Attach-only bridge — attach to an existing session, append one progress event
# --------------------------------------------------------------------------- #
class TemporalAttachOnlyBridge:
    """Durable orchestration bridge over an already-running supervisor session.

    Its one activity attaches to an existing session (via the read-only
    execution-port liveness/status surface), records a single refs-only progress
    event through the Task Registry, and returns a refs-only result. It never
    creates, spawns, relaunches, signals, or kills a session — repeated calls
    (durable retries/replays) may append further progress events but must never
    bring a session into being.
    """

    def __init__(self, *, registry: TaskRegistry, execution_port: ExecutionPort) -> None:
        if type(registry) is not TaskRegistry:
            _invalid()
        if not isinstance(execution_port, ExecutionPort):
            _invalid()
        self._registry = registry
        self._execution_port = execution_port
        # Pin the orchestrator contract at construction; a tampered contract fails
        # closed here rather than being silently honored later.
        self._contract = validate_workflow_contract(TemporalWorkflowContract())

    @property
    def contract(self) -> TemporalWorkflowContract:
        return self._contract

    def run_agent_activity(self, activity_input: AgentRunActivityInput) -> AgentRunActivityResult:
        inp = validate_agent_run_activity_input(activity_input)

        # 1. The task must already exist and be an agent + durable task. We never
        #    create it here — a missing or mismatched record fails closed.
        record = self._registry.get_record(inp.task_id)
        if record is None or record.needs_agent is not True or record.needs_durable is not True:
            _invalid()

        # 2. Attach to the existing session using the read-only liveness/status
        #    surface only. A missing / dead / non-live session fails closed before
        #    any event is appended — the bridge never respawns a session.
        try:
            liveness = validate_liveness_state(self._execution_port.liveness(inp.session_ref))
        except SpineError:
            _invalid()
        if (
            liveness.task_id != inp.task_id
            or liveness.session_id != inp.session_ref.session_id
            or liveness.alive is not True
            or liveness.reapable is not False
        ):
            _invalid()
        try:
            status = validate_session_status(self._execution_port.status(inp.session_ref))
        except SpineError:
            _invalid()
        if (
            status.task_id != inp.task_id
            or status.session_id != inp.session_ref.session_id
            or status.alive is not True
            or status.terminal is not False
            or status.state not in _RESULT_STATUSES
        ):
            _invalid()

        # 3. Append exactly one refs-only progress event through the registry.
        heartbeat = inp.heartbeat
        event = self._registry.append_event(
            inp.task_id,
            build_event_body(
                event_type="progress",
                status=status.state,
                refs=(inp.session_ref.session_id, heartbeat.cursor_ref, *heartbeat.refs),
                counts=heartbeat.counters,
            ),
        )

        # 4. Refs-only, stable-code-sanitized result — no process/session side effect.
        return AgentRunActivityResult(
            task_id=inp.task_id,
            session_id=inp.session_ref.session_id,
            status=status.state,
            alive=status.alive,
            heartbeat=heartbeat,
            appended_event_seq=event.seq,
            side_effects=(),
        )
