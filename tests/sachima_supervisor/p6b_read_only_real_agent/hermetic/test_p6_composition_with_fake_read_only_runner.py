"""P6-B hermetic composition with an injected fake read-only runner (no Temporal).

Drives the **unmodified** WP4 entrypoints through the **unmodified** P6-A
composition session with the P6-B bridge in front of an injected fake read-only
runner. Proves the single bounded read-only planning/report step succeeds
end-to-end, evidence stays sanitized, and the WP4 claim replay never invokes the
executor (and therefore never relaunches the read-only runner) a second time.
"""

from __future__ import annotations

from sachima_supervisor.ai_flow_store import AiFlowRunStore
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p6_controlled_ai_flow import (
    P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
    P6ControlledAiFlowSession,
)

from .._support import (
    OUTPUT_CONTRACT,
    SPEC,
    CountingArtifactSink,
    CountingSupervisor,
    build_executor,
    role_binding,
    run_request,
    step_request,
)


def _session(executor):
    return P6ControlledAiFlowSession(
        spec=SPEC,
        store=AiFlowRunStore(),
        executor=executor,
        enabled=True,
        approval_token=P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
        operator_gate=True,
    )


def test_single_planning_report_step_succeeds_through_fake_runner(tmp_path):
    supervisor = CountingSupervisor()
    sink = CountingArtifactSink()
    executor = build_executor(tmp_path, invoke_supervisor=supervisor, artifact_sink=sink)
    session = _session(executor)

    outcome = session.run_linear(
        run_request(), [step_request()], terminal_gate_ref="terminal_ref_ok"
    )

    assert outcome.admitted is True
    assert outcome.ok is True
    assert outcome.final_verdict == "succeeded"
    assert outcome.active_run_watch is False
    # The injected fake read-only runner launched exactly once.
    assert supervisor.calls == 1
    assert sink.calls == 1

    ev = outcome.evidence
    assert C.scan_projection_for_leak(ev) is None
    assert ev["p6_admission"] == {"enabled": True, "approved": True, "admission_code": None}
    assert len(ev["artifact_refs"]) == 1
    assert ev["artifact_refs"][0]["artifact_kind"] == OUTPUT_CONTRACT
    assert ev["evidence_digest"].startswith("sha256:")


def test_wp4_claim_replay_never_invokes_executor_twice(tmp_path):
    supervisor = CountingSupervisor()
    sink = CountingArtifactSink()
    executor = build_executor(tmp_path, invoke_supervisor=supervisor, artifact_sink=sink)
    session = _session(executor)

    session.create_run(run_request())
    first = session.step(step_request())
    second = session.step(step_request())

    assert first.status == "completed"
    assert first.durable_state == second.durable_state
    # WP4 returns the resident projection on replay; the executor — and the
    # read-only runner — is never invoked a second time.
    assert supervisor.calls == 1
    assert sink.calls == 1


def test_executor_is_admitted_as_an_armed_runtime_by_p6(tmp_path):
    # P6-A's _executor_is_armed requires .enabled is True + callable .execute.
    executor = build_executor(tmp_path)
    session = _session(executor)
    admission = session.admit()
    assert admission.ok is True
    assert admission.error_code is None
