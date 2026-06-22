"""Sachima x agent-run-supervisor local/offline integration seam (default-off).

Caller-owned, local/offline only. No live behavior, no Gateway involvement, no
real delivery. See ``sachima_supervisor.local_offline`` for the public API and
``docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md``
for the design boundaries.
"""

from __future__ import annotations

from sachima_supervisor.activity_controlled_exec import (
    CONTROLLED_EXEC_FUTURE_ROLE_KEYS,
    CONTROLLED_EXEC_MODE,
    CONTROLLED_EXEC_MODES,
    CONTROLLED_EXEC_ROLE_ALLOWLIST,
    CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN,
    FORBIDDEN_RUNNER_BASENAMES,
    ControlledLocalExecClaimStore,
    ControlledLocalExecError,
    ControlledLocalExecRequest,
    ControlledLocalExecResult,
    PinnedLocalAcpxProvenance,
    query_controlled_local_exec,
    start_controlled_local_exec,
    verify_pinned_local_acpx_binary,
)
from sachima_supervisor.smoke_prompt import (
    PHASE_D_SMOKE_PROMPT_FIXTURE_RELATIVE_PATH,
    PHASE_D_SMOKE_PROMPT_MAX_CHARS,
    PHASE_D_SMOKE_PROMPT_REF,
    PHASE_D_SMOKE_PROMPT_TYPE,
    PhaseDSmokePromptError,
    build_phase_d_smoke_prompt,
    materialize_phase_d_smoke_prompt,
)
from sachima_supervisor.supervisor_library import (
    AGENT_RUN_SUPERVISOR_DISTRIBUTION,
    AGENT_RUN_SUPERVISOR_IMPORT_NAME,
    EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
    SupervisorLibraryPinStatus,
    check_supervisor_library_pin,
)
from sachima_supervisor.activity import (
    ACTIVITY_IMPLEMENTATION_APPROVAL_TOKEN,
    FIRST_SLICE_MODES,
    ROLE_KEY_ALLOWLIST,
    ActivityStateStore,
    SupervisedLocalActivityError,
    SupervisedLocalActivityRequest,
    SupervisedLocalActivityResult,
    query_supervised_local_activity,
    start_supervised_local_activity,
)
from sachima_supervisor.activity_evidence import (
    CONTROLLED_DRY_RUN_EVIDENCE_APPROVAL_MARKER,
    build_controlled_local_dry_run_evidence,
    write_controlled_local_dry_run_evidence,
)
from sachima_supervisor.activity_preflight import (
    DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
    DurableStatePreflightError,
    DurableStatePreflightRequest,
    DurableStatePreflightResult,
    DurableStatePreflightStore,
    query_durable_state_preflight,
    run_durable_state_preflight,
)
from sachima_supervisor.local_offline import (
    FORBIDDEN_METADATA_KEYS,
    IMPLEMENTATION_APPROVAL_TOKEN,
    SUPPORTED_MODES,
    LocalOfflineSupervisorError,
    LocalOfflineSupervisorOutcome,
    LocalOfflineSupervisorRequest,
    build_caller_invocation_spec,
    build_offline_view_model,
    invoke_local_offline_supervisor,
)

# WP4 controlled AI FLOW local/offline orchestration (slice 1; injected fakes
# only; read-only roles; bounded static linear graph; no real workflow
# execution; no acpx/npx; no Gateway/Feishu/live/production config/real delivery)
from sachima_supervisor.ai_flow_spec import (
    SCHEMA_VERSION as AI_FLOW_SCHEMA_VERSION,
    AiFlowSpecError,
    RoleBinding,
    StepSpec,
    WorkflowBounds,
    WorkflowSpec,
    canonical_read_only_workflow_mapping,
    role_binding_digest,
    validate_workflow_spec,
    workflow_spec_digest,
)
from sachima_supervisor.ai_flow_artifacts import (
    AiFlowArtifactError,
    ArtifactRef,
    artifact_ref_projection,
    verify_artifact_ref,
)
from sachima_supervisor.ai_flow_gates import (
    GATE_TYPES,
    AiFlowGateError,
    GateDecision,
    check_gate,
    gate_decision_projection,
)
from sachima_supervisor.ai_flow_store import (
    AiFlowError,
    AiFlowRunStore,
    build_cancel_state,
    build_run_state,
    build_step_state,
    step_fingerprint,
)
from sachima_supervisor.ai_flow_executor import (
    StepExecutionOutcome,
    StepExecutor,
)
from sachima_supervisor.p5_runtime_adapter import (
    P5LocalOfflineDurableClaimStore,
    P5LocalOfflineRuntimeAdapter,
    P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN,
)
from sachima_supervisor.ai_flow_evidence import (
    FINAL_VERDICTS,
    AiFlowEvidenceError,
    WorkflowEvidence,
    build_workflow_evidence,
    default_non_approval_flags,
)
from sachima_supervisor.activity_ai_flow_orchestration import (
    AI_FLOW_APPROVAL_TOKEN,
    AiFlowOrchestrationError,
    CancellationRecordResult,
    StepAttemptRequest,
    StepRecordResult,
    WorkflowCancellationRequest,
    WorkflowRunRequest,
    WorkflowRunResult,
    create_workflow_run,
    list_workflow_steps,
    query_workflow_run,
    request_workflow_cancellation,
    step_workflow_run,
    summarize_workflow_run,
)

__all__ = [
    # local/offline seam (PR #97)
    "FORBIDDEN_METADATA_KEYS",
    "IMPLEMENTATION_APPROVAL_TOKEN",
    "SUPPORTED_MODES",
    "LocalOfflineSupervisorError",
    "LocalOfflineSupervisorOutcome",
    "LocalOfflineSupervisorRequest",
    "build_caller_invocation_spec",
    "build_offline_view_model",
    "invoke_local_offline_supervisor",
    # supervised local Activity wrapper (first slice)
    "ACTIVITY_IMPLEMENTATION_APPROVAL_TOKEN",
    "FIRST_SLICE_MODES",
    "ROLE_KEY_ALLOWLIST",
    "ActivityStateStore",
    "SupervisedLocalActivityError",
    "SupervisedLocalActivityRequest",
    "SupervisedLocalActivityResult",
    "query_supervised_local_activity",
    "start_supervised_local_activity",
    # controlled local Activity dry-run evidence (PR #100)
    "CONTROLLED_DRY_RUN_EVIDENCE_APPROVAL_MARKER",
    "build_controlled_local_dry_run_evidence",
    "write_controlled_local_dry_run_evidence",
    # durable-state preflight (local/offline)
    "DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN",
    "DurableStatePreflightError",
    "DurableStatePreflightRequest",
    "DurableStatePreflightResult",
    "DurableStatePreflightStore",
    "query_durable_state_preflight",
    "run_durable_state_preflight",
    # controlled local one-shot exec (Phase C first slice; local/offline,
    # default-off, pinned local acpx provenance required, Codex read-only role)
    "CONTROLLED_EXEC_FUTURE_ROLE_KEYS",
    "CONTROLLED_EXEC_MODE",
    "CONTROLLED_EXEC_MODES",
    "CONTROLLED_EXEC_ROLE_ALLOWLIST",
    "CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN",
    "ControlledLocalExecClaimStore",
    "ControlledLocalExecError",
    "ControlledLocalExecRequest",
    "ControlledLocalExecResult",
    "query_controlled_local_exec",
    "start_controlled_local_exec",
    # Phase D smoke prerequisites (preparation only; no smoke, no AGENT,
    # no acpx/npx, no Gateway/Feishu/live, no production config)
    "FORBIDDEN_RUNNER_BASENAMES",
    "PinnedLocalAcpxProvenance",
    "verify_pinned_local_acpx_binary",
    "PHASE_D_SMOKE_PROMPT_FIXTURE_RELATIVE_PATH",
    "PHASE_D_SMOKE_PROMPT_MAX_CHARS",
    "PHASE_D_SMOKE_PROMPT_REF",
    "PHASE_D_SMOKE_PROMPT_TYPE",
    "PhaseDSmokePromptError",
    "build_phase_d_smoke_prompt",
    "materialize_phase_d_smoke_prompt",
    "AGENT_RUN_SUPERVISOR_DISTRIBUTION",
    "AGENT_RUN_SUPERVISOR_IMPORT_NAME",
    "EXPECTED_AGENT_RUN_SUPERVISOR_VERSION",
    "SupervisorLibraryPinStatus",
    "check_supervisor_library_pin",
    # WP4 controlled AI FLOW local/offline orchestration (slice 1; injected
    # fakes only; read-only roles; no real workflow execution; no acpx/npx;
    # no Gateway/Feishu/live/production config/real delivery)
    "AI_FLOW_SCHEMA_VERSION",
    "AiFlowSpecError",
    "RoleBinding",
    "StepSpec",
    "WorkflowBounds",
    "WorkflowSpec",
    "canonical_read_only_workflow_mapping",
    "role_binding_digest",
    "validate_workflow_spec",
    "workflow_spec_digest",
    "AiFlowArtifactError",
    "ArtifactRef",
    "artifact_ref_projection",
    "verify_artifact_ref",
    "GATE_TYPES",
    "AiFlowGateError",
    "GateDecision",
    "check_gate",
    "gate_decision_projection",
    "AiFlowError",
    "AiFlowRunStore",
    "build_cancel_state",
    "build_run_state",
    "build_step_state",
    "step_fingerprint",
    "StepExecutionOutcome",
    "StepExecutor",
    "P5LocalOfflineDurableClaimStore",
    "P5LocalOfflineRuntimeAdapter",
    "P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN",
    "FINAL_VERDICTS",
    "AiFlowEvidenceError",
    "WorkflowEvidence",
    "build_workflow_evidence",
    "default_non_approval_flags",
    "AI_FLOW_APPROVAL_TOKEN",
    "AiFlowOrchestrationError",
    "CancellationRecordResult",
    "StepAttemptRequest",
    "StepRecordResult",
    "WorkflowCancellationRequest",
    "WorkflowRunRequest",
    "WorkflowRunResult",
    "create_workflow_run",
    "list_workflow_steps",
    "query_workflow_run",
    "request_workflow_cancellation",
    "step_workflow_run",
    "summarize_workflow_run",
]
