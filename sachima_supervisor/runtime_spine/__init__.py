"""Sachima Private Hermes Runtime Spine — R1 core (local/offline).

The minimal runtime backbone: one ``task_id`` spine, a refs-only Task Event Log
that is the single monotonic ``seq`` authority, a deterministic Status Projection,
a log-derived Task Registry snapshot cache, a static Capability Registry, and a
typed, fail-closed LaunchSpec.

Everything here is pure local/offline Python. Importing this package starts no
subprocess, socket, Docker, daemon, Temporal service/Worker/client, Gateway,
Feishu, or network call, launches no OS process or agent (acpx/npx), and wires no
supervisor execution port (that is R2). Forbidden terms appear only as no-leak
denylist canaries, never as behavior. See
``docs/architecture/private-hermes-runtime-spine-design.md``.
"""

from __future__ import annotations

from .capabilities import (
    CAPABILITY_FIELDS,
    Capability,
    get_capability,
    known_agent_kinds,
)
from .events import (
    ALLOWED_EVENT_BODY_KEYS,
    EVENT_TYPES,
    FORBIDDEN_MARKERS,
    KNOWN_FLAG_KEYS,
    RUNTIME_EVENT_LEAK_DETECTED,
    RUNTIME_INVALID_EVENT,
    RUNTIME_INVALID_LAUNCH_SPEC,
    RUNTIME_INVALID_PROJECTION,
    RUNTIME_INVALID_TASK_ID,
    RUNTIME_INVALID_TASK_RECORD,
    RUNTIME_SEQ_VIOLATION,
    RUNTIME_UNKNOWN_CAPABILITY,
    STABLE_CODES,
    STATUS_VALUES,
    TERMINAL_STATUSES,
    SpineError,
    TaskEvent,
    TaskEventLog,
    build_event_body,
    event_projection,
    safe_error_code,
    safe_role_key,
    safe_task_id,
    scan_for_leak,
    validate_event_body,
    verify_seq_contiguous,
)
from .execution_port import (
    LIVE_SESSION_STATES,
    PORT_STABLE_CODES,
    REAPABLE_SESSION_STATES,
    RUNTIME_INVALID_SESSION,
    SESSION_STATES,
    TERMINAL_SESSION_STATES,
    ExecutionPort,
    LivenessState,
    SessionRef,
    SessionStatus,
    validate_liveness_state,
    validate_session_ref,
    validate_session_status,
)
from .fake_supervisor_port import FakeSupervisorPort
from .launch_spec import (
    KNOWN_MODE_FLAGS,
    LaunchSpec,
    build_launch_spec,
    validate_launch_spec,
)
from .projection import (
    ALLOWED_PROJECTION_KEYS,
    PROJECTION_TYPE,
    project,
    serialize_projection,
)
from .registry import TaskRecord, TaskRegistry
from .temporal_bridge import (
    BRIDGE_PHASES,
    BRIDGE_STABLE_CODES,
    RUNTIME_INVALID_TEMPORAL_BRIDGE,
    AgentRunActivityInput,
    AgentRunActivityResult,
    HeartbeatPayload,
    TemporalAttachOnlyBridge,
    TemporalWorkflowContract,
    validate_agent_run_activity_input,
    validate_heartbeat_payload,
    validate_workflow_contract,
)

__all__ = [
    # errors / stable codes
    "SpineError",
    "STABLE_CODES",
    "RUNTIME_INVALID_TASK_ID",
    "RUNTIME_INVALID_EVENT",
    "RUNTIME_SEQ_VIOLATION",
    "RUNTIME_EVENT_LEAK_DETECTED",
    "RUNTIME_INVALID_PROJECTION",
    "RUNTIME_INVALID_TASK_RECORD",
    "RUNTIME_UNKNOWN_CAPABILITY",
    "RUNTIME_INVALID_LAUNCH_SPEC",
    "RUNTIME_INVALID_SESSION",
    "PORT_STABLE_CODES",
    # events / log
    "FORBIDDEN_MARKERS",
    "EVENT_TYPES",
    "STATUS_VALUES",
    "TERMINAL_STATUSES",
    "ALLOWED_EVENT_BODY_KEYS",
    "KNOWN_FLAG_KEYS",
    "TaskEvent",
    "TaskEventLog",
    "build_event_body",
    "validate_event_body",
    "event_projection",
    "verify_seq_contiguous",
    "scan_for_leak",
    "safe_task_id",
    "safe_role_key",
    "safe_error_code",
    # execution port
    "SESSION_STATES",
    "LIVE_SESSION_STATES",
    "TERMINAL_SESSION_STATES",
    "REAPABLE_SESSION_STATES",
    "ExecutionPort",
    "SessionRef",
    "LivenessState",
    "SessionStatus",
    "validate_session_ref",
    "validate_liveness_state",
    "validate_session_status",
    "FakeSupervisorPort",
    # projection
    "PROJECTION_TYPE",
    "ALLOWED_PROJECTION_KEYS",
    "project",
    "serialize_projection",
    # registry
    "TaskRecord",
    "TaskRegistry",
    # temporal attach-only bridge (R3)
    "RUNTIME_INVALID_TEMPORAL_BRIDGE",
    "BRIDGE_STABLE_CODES",
    "BRIDGE_PHASES",
    "HeartbeatPayload",
    "AgentRunActivityInput",
    "AgentRunActivityResult",
    "TemporalWorkflowContract",
    "TemporalAttachOnlyBridge",
    "validate_heartbeat_payload",
    "validate_agent_run_activity_input",
    "validate_workflow_contract",
    # capabilities
    "Capability",
    "CAPABILITY_FIELDS",
    "get_capability",
    "known_agent_kinds",
    # launch spec
    "LaunchSpec",
    "KNOWN_MODE_FLAGS",
    "build_launch_spec",
    "validate_launch_spec",
]
