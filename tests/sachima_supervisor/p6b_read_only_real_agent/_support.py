"""Shared P6-B test builders / fakes (no Temporal, no real agent).

Reuses the merged WP4 + controlled-exec + preflight surfaces **unmodified** to
drive the P6-B read-only real-agent bridge with an **injected fake** read-only
runner. Nothing here imports ``temporalio``, Gateway, Feishu, a platform adapter,
or invokes a real ``acpx``/agent. The role file is written into a temp dir with a
pinned **placeholder** binary path so the controlled-exec provenance wall is
satisfied without any local executable ever being run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from sachima_supervisor.ai_flow_spec import (
    RoleBinding,
    SCHEMA_VERSION,
    role_binding_digest,
    validate_workflow_spec,
    workflow_spec_digest,
)
from sachima_supervisor.activity_ai_flow_orchestration import (
    AI_FLOW_APPROVAL_TOKEN,
    StepAttemptRequest,
    WorkflowCancellationRequest,
    WorkflowRunRequest,
)
from sachima_supervisor.activity_controlled_exec import (
    CONTROLLED_EXEC_ROLE_ALLOWLIST,
    ControlledLocalExecClaimStore,
)
from sachima_supervisor.activity_evidence import build_controlled_local_dry_run_evidence
from sachima_supervisor.activity_preflight import (
    DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
    DurableStatePreflightRequest,
    DurableStatePreflightStore,
    run_durable_state_preflight,
)
from sachima_supervisor.local_offline import (
    LocalOfflineSupervisorOutcome,
    LocalOfflineSupervisorRequest,
)
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p6b_planning_report_prompt import (
    materialize_p6b_planning_report_prompt,
)
from sachima_supervisor.p6b_read_only_real_agent import (
    P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN,
    P6BReadOnlyRealAgentStepExecutor,
)

# --------------------------------------------------------------------------- #
# Single bounded read-only planning/report workflow
# --------------------------------------------------------------------------- #
ROLE_KEY = "sachima.claude.read_only_reviewer"
ROLE_FILE_REF = CONTROLLED_EXEC_ROLE_ALLOWLIST[ROLE_KEY]
LOGICAL_ROLE = "planner"
STEP_ID = "planning_report_step"
OUTPUT_CONTRACT = "planning_report"
RUN_ID = "run_p6b_alpha"

# Shared transaction / lease identity bound by the durable-state preflight record.
TXN = "txn_p6b_planning"
OP = "op_p6b_planning"
LEASE_ID = "lease_p6b_001"
LEASE_EPOCH = 3
LEASE_HOLDER = "controller_ref_sachima_p6b"
STATE_VERSION = 0
PREFLIGHT_ACTIVITY_ID = "activity_preflight_for_p6b_001"

# A pinned placeholder runner path: absolute, non-launcher basename. It is never
# executed — the fake supervisor is injected — so no local binary need exist.
PINNED_PLACEHOLDER_BINARY = "/opt/sachima/runners/acpx-0.10.0/acpx"


def p6b_workflow_mapping() -> dict[str, Any]:
    """A fresh single-step bounded read-only planning/report workflow mapping."""

    return {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": "wf_p6b_read_only_planning_report_v1",
        "approval_ref": "p6b_read_only_planning_report_approval_v1",
        "bounds": {
            "max_steps": 1,
            "max_retries_per_step": 1,
            "max_artifact_bytes": 65536,
            "max_runtime_seconds": 900,
        },
        "roles": {
            LOGICAL_ROLE: {"role_key": ROLE_KEY, "capabilities": ["read", "search"]},
        },
        "steps": [
            {
                "step_id": STEP_ID,
                "logical_role": LOGICAL_ROLE,
                "input_refs": [],
                "output_contract": OUTPUT_CONTRACT,
                "depends_on": [],
            },
        ],
        "edges": [],
    }


SPEC = validate_workflow_spec(p6b_workflow_mapping())
WSD = workflow_spec_digest(SPEC)
RBD = role_binding_digest(SPEC)


def evidence_digest() -> str:
    digest = build_controlled_local_dry_run_evidence()["fixture_digest"]
    assert isinstance(digest, str)
    return digest


def expected_activity_id(run_id: str = RUN_ID, step_id: str = STEP_ID) -> str:
    """The deterministic controlled-exec activity id the bridge derives."""

    suffix = C.workflow_id_from_refs(C.safe_ref(run_id), C.safe_ref(step_id))[len("p5wf_"):]
    return "p6b_exec_" + suffix


def role_binding(**overrides: Any) -> RoleBinding:
    base: dict[str, Any] = {
        "logical_role": LOGICAL_ROLE,
        "role_key": ROLE_KEY,
        "capabilities": ("read", "search"),
    }
    base.update(overrides)
    return RoleBinding(**base)


def run_request(**overrides: Any) -> WorkflowRunRequest:
    base: dict[str, Any] = dict(
        run_id=RUN_ID,
        workflow_id=SPEC.workflow_id,
        workflow_spec_digest=WSD,
        role_binding_digest=RBD,
        approval_ref=SPEC.approval_ref,
        transaction_ref=TXN,
        operation_ref=OP,
        idempotency_key="idem_run_p6b",
        admission_gate_ref="admission_ref_ok",
        approval_token=AI_FLOW_APPROVAL_TOKEN,
        enabled=True,
        operator_gate=True,
        lease_id=LEASE_ID,
        lease_epoch=LEASE_EPOCH,
        lease_holder_ref=LEASE_HOLDER,
        expected_state_version=STATE_VERSION,
    )
    base.update(overrides)
    return WorkflowRunRequest(**base)


def step_request(**overrides: Any) -> StepAttemptRequest:
    base: dict[str, Any] = dict(
        run_id=RUN_ID,
        step_id=STEP_ID,
        attempt_index=1,
        workflow_spec_digest=WSD,
        role_binding_digest=RBD,
        input_artifact_digests=(),
        pre_step_gate_ref="pre_planning",
        post_step_gate_ref="post_planning",
        transaction_ref=TXN,
        operation_ref=OP,
        idempotency_key="idem_planning_p6b",
        approval_token=AI_FLOW_APPROVAL_TOKEN,
        enabled=True,
        operator_gate=True,
        lease_id=LEASE_ID,
        lease_epoch=LEASE_EPOCH,
        lease_holder_ref=LEASE_HOLDER,
        expected_state_version=STATE_VERSION,
    )
    base.update(overrides)
    return StepAttemptRequest(**base)


def cancel_request(**overrides: Any) -> WorkflowCancellationRequest:
    base: dict[str, Any] = dict(
        cancel_id="cancel_p6b_0001",
        run_id=RUN_ID,
        scope="active_run",
        transaction_ref=TXN,
        operation_ref=OP,
        idempotency_key="idem_cancel_p6b",
        step_id=STEP_ID,
        reason_code="operator_requested",
        approval_token=AI_FLOW_APPROVAL_TOKEN,
        enabled=True,
        operator_gate=True,
    )
    base.update(overrides)
    return WorkflowCancellationRequest(**base)


# --------------------------------------------------------------------------- #
# Role file + durable-state preflight record
# --------------------------------------------------------------------------- #
def role_mapping(**overrides: Any) -> dict[str, Any]:
    mapping: dict[str, Any] = {
        "schema_version": 1,
        "role_id": ROLE_KEY,
        "display_name": "Sachima read-only reviewer (P6-B planning/report)",
        "description": "Read-only one-shot reviewer pinned for the P6-B fake-runner test.",
        "runner": {
            "type": "acpx",
            "acpx_version": "0.10.0",
            "acpx_binary": PINNED_PLACEHOLDER_BINARY,
            "adapter_agent": "claude",
            "model": None,
        },
        "workspace": {
            "default_cwd": "/workspace/sachima",
            "allowed_roots": ["/workspace/sachima"],
            "allowed_roots_security_boundary": False,
        },
        "permissions": {
            "read": True,
            "search": True,
            "write": False,
            "execute": False,
            "terminal": False,
            "delete": False,
            "move": False,
            "fetch": False,
            "switch_mode": False,
            "other": False,
        },
        "session": {"strategy": "exec"},
        "limits": {"timeout_seconds": 900, "max_turns": 8, "max_output_bytes": 2000000},
        "prompt": {
            "role_instruction": "Read-only planning/report reviewer.",
            "output_contract": "Report VERDICT: PASS or VERDICT: BLOCKERS with findings.",
        },
        "redaction": {
            "suppress_reads": True,
            "redact_prompt": True,
            "redact_stderr": True,
            "redact_metadata": True,
            "redact_env": True,
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(mapping.get(key), dict):
            mapping[key] = {**mapping[key], **value}
        else:
            mapping[key] = value
    return mapping


def write_role(tmp_path: Path, mapping: dict[str, Any] | None = None) -> tuple[Path, str]:
    mapping = mapping if mapping is not None else role_mapping()
    role_path = tmp_path / ROLE_FILE_REF
    role_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(mapping, indent=2, sort_keys=True).encode("utf-8")
    role_path.write_bytes(payload)
    return tmp_path, "sha256:" + hashlib.sha256(payload).hexdigest()


def preflight_request(**overrides: Any) -> DurableStatePreflightRequest:
    base: dict[str, Any] = {
        "activity_id": PREFLIGHT_ACTIVITY_ID,
        "transaction_ref": TXN,
        "operation_ref": OP,
        "idempotency_key": "idem_preflight_p6b",
        "mode": "exec_dry_run",
        "role_key": "sachima.primary_reviewer",
        "approval_token": DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
        "enabled": True,
        "prompt_ref": "claim_prompt_p6b",
        "context_refs": ("claim_context_p6b",),
        "cwd_ref": "workspace_ref_sachima_release",
        "allowed_roots_ref": "allowed_roots_ref_sachima_release",
        "prior_dry_run_evidence_digest": evidence_digest(),
        "lease_id": LEASE_ID,
        "lease_epoch": LEASE_EPOCH,
        "lease_holder_ref": LEASE_HOLDER,
        "expected_state_version": STATE_VERSION,
        "operator_gate": True,
        "max_attempts": 1,
        "max_artifact_refs": 0,
        "max_evidence_bytes": 0,
    }
    base.update(overrides)
    return DurableStatePreflightRequest(**base)


def preflight_store_with_record() -> DurableStatePreflightStore:
    request = preflight_request()
    store = DurableStatePreflightStore()
    store.grant_lease(
        activity_id=request.activity_id,
        lease_id=request.lease_id,
        lease_epoch=request.lease_epoch,
        lease_holder_ref=request.lease_holder_ref,
        state_version=STATE_VERSION,
    )
    run_durable_state_preflight(request, store)
    return store


# --------------------------------------------------------------------------- #
# Injected fake read-only runner (supervisor seam) + output artifact sink
# --------------------------------------------------------------------------- #
def success_supervisor_outcome(
    seam_request: LocalOfflineSupervisorRequest,
) -> LocalOfflineSupervisorOutcome:
    return LocalOfflineSupervisorOutcome(
        status="observed",
        mode=seam_request.mode,
        phase="exec",
        supervisor_status="completed",
        correlation_label=seam_request.correlation_label,
        error_code=None,
        business_verdict=None,
        caller_verdict=None,
        artifact_ref_count=1,
        evidence_ref="local_offline_supervisor_evidence_p6b",
        evidence_digest="sha256:" + "a" * 64,
        evidence_path=None,
        view_model={"status": "observed"},
    )


class CountingSupervisor:
    """Injected fake read-only runner. Counts launches; records the seam request.

    Proves a default-off / fail-closed path performs **zero** launches and that
    a controlled-exec replay never launches a second time.
    """

    def __init__(
        self,
        outcome_factory: Callable[
            [LocalOfflineSupervisorRequest], LocalOfflineSupervisorOutcome
        ] = success_supervisor_outcome,
    ) -> None:
        self.calls = 0
        self.last_request: LocalOfflineSupervisorRequest | None = None
        self._outcome_factory = outcome_factory

    def __call__(
        self, seam_request: LocalOfflineSupervisorRequest
    ) -> LocalOfflineSupervisorOutcome:
        self.calls += 1
        self.last_request = seam_request
        return self._outcome_factory(seam_request)


def planning_report_ref(*, step_id: str = STEP_ID, kind: str = OUTPUT_CONTRACT, **overrides: Any) -> dict[str, Any]:
    body = b"sanitized planning report claim-check body"
    ref = {
        "artifact_id": "p6b_planning_report_artifact_0001",
        "producer_step_id": step_id,
        "content_digest": "sha256:" + hashlib.sha256(body).hexdigest(),
        "artifact_kind": kind,
        "byte_count": len(body),
        "created_at_ref": "created_at_ref_p6b_0001",
    }
    ref.update(overrides)
    return ref


class CountingArtifactSink:
    """Injected fake out-of-repo claim-check sink. Returns refs only (no bytes)."""

    def __init__(
        self,
        refs_factory: Callable[[Any, Any, Any], Any] | None = None,
    ) -> None:
        self.calls = 0
        self._refs_factory = refs_factory or (
            lambda request, result, binding: (planning_report_ref(step_id=request.step_id),)
        )

    def __call__(self, request: Any, *, result: Any, role_binding: Any) -> Any:
        self.calls += 1
        return self._refs_factory(request, result, role_binding)


# --------------------------------------------------------------------------- #
# Executor builder
# --------------------------------------------------------------------------- #
def build_executor(tmp_path: Path, **overrides: Any) -> P6BReadOnlyRealAgentStepExecutor:
    """Build a fully-wired (or partially-wired, for negative tests) bridge.

    Pass any seam explicitly — including ``None`` — to exercise fail-closed
    admission; otherwise sensible fakes/digests are supplied.
    """

    mapping = overrides.pop("role_mapping", None)
    role_root, digest = write_role(tmp_path, mapping)
    defaults: dict[str, Any] = dict(
        enabled=True,
        approval_token=P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN,
        controlled_exec_store=ControlledLocalExecClaimStore(),
        preflight_store=preflight_store_with_record(),
        prompt_materializer=materialize_p6b_planning_report_prompt,
        artifact_sink=CountingArtifactSink(),
        invoke_supervisor=CountingSupervisor(),
        role_file_digest=digest,
        preflight_activity_id=PREFLIGHT_ACTIVITY_ID,
        prior_dry_run_evidence_digest=evidence_digest(),
        role_root=role_root,
        max_artifact_bytes=65536,
    )
    defaults.update(overrides)
    return P6BReadOnlyRealAgentStepExecutor(**defaults)
