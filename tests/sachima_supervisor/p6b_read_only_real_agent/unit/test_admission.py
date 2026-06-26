"""P6-B admission gate (FR1, Gate 1 — default-off, fail closed before any launch).

``enabled is not True``, an approval-token mismatch, or any missing required seam
(controlled-exec store, preflight store, prompt materializer, artifact sink) must
each return a sanitized ``StepExecutionOutcome(ok=False, error_code=p6b_*)`` and
perform **zero** read-only-runner launches and **zero** artifact-sink calls.
"""

from __future__ import annotations

from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.p6b_read_only_real_agent import (
    P6B_APPROVAL_MISMATCH,
    P6B_EXECUTION_DISABLED,
    P6B_PRECONDITION_UNMET,
    P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN,
)

from .._support import (
    CountingArtifactSink,
    CountingSupervisor,
    build_executor,
    role_binding,
    step_request,
)


def _execute(executor):
    return executor.execute(step_request(), role_binding=role_binding(), resolved_inputs=())


def test_disabled_fails_closed_with_zero_launch(tmp_path):
    supervisor, sink = CountingSupervisor(), CountingArtifactSink()
    executor = build_executor(
        tmp_path, enabled=False, invoke_supervisor=supervisor, artifact_sink=sink
    )

    outcome = _execute(executor)

    assert isinstance(outcome, StepExecutionOutcome)
    assert outcome.ok is False
    assert outcome.error_code == P6B_EXECUTION_DISABLED
    assert outcome.artifact_refs == ()
    assert supervisor.calls == 0
    assert sink.calls == 0


def test_approval_mismatch_fails_closed_with_zero_launch(tmp_path):
    supervisor, sink = CountingSupervisor(), CountingArtifactSink()
    executor = build_executor(
        tmp_path,
        **{"approval_" + "token": "approve_" + "something_else"},
        invoke_supervisor=supervisor,
        artifact_sink=sink,
    )

    outcome = _execute(executor)

    assert outcome.ok is False
    assert outcome.error_code == P6B_APPROVAL_MISMATCH
    assert supervisor.calls == 0
    assert sink.calls == 0


def test_missing_controlled_exec_store_fails_precondition(tmp_path):
    supervisor, sink = CountingSupervisor(), CountingArtifactSink()
    executor = build_executor(
        tmp_path, controlled_exec_store=None, invoke_supervisor=supervisor, artifact_sink=sink
    )

    outcome = _execute(executor)

    assert outcome.ok is False
    assert outcome.error_code == P6B_PRECONDITION_UNMET
    assert supervisor.calls == 0
    assert sink.calls == 0


def test_missing_preflight_store_fails_precondition(tmp_path):
    supervisor, sink = CountingSupervisor(), CountingArtifactSink()
    executor = build_executor(
        tmp_path, preflight_store=None, invoke_supervisor=supervisor, artifact_sink=sink
    )

    outcome = _execute(executor)

    assert outcome.ok is False
    assert outcome.error_code == P6B_PRECONDITION_UNMET
    assert supervisor.calls == 0
    assert sink.calls == 0


def test_missing_prompt_materializer_fails_precondition_no_run(tmp_path):
    # The default ``prompt_materializer=None`` posture must fail closed: a
    # null materializer means no agent run can start.
    supervisor, sink = CountingSupervisor(), CountingArtifactSink()
    executor = build_executor(
        tmp_path, prompt_materializer=None, invoke_supervisor=supervisor, artifact_sink=sink
    )

    outcome = _execute(executor)

    assert outcome.ok is False
    assert outcome.error_code == P6B_PRECONDITION_UNMET
    assert supervisor.calls == 0
    assert sink.calls == 0


def test_missing_artifact_sink_fails_precondition(tmp_path):
    supervisor = CountingSupervisor()
    executor = build_executor(
        tmp_path, artifact_sink=None, invoke_supervisor=supervisor
    )

    outcome = _execute(executor)

    assert outcome.ok is False
    assert outcome.error_code == P6B_PRECONDITION_UNMET
    assert supervisor.calls == 0


def test_armed_executor_exposes_enabled_and_execute_for_p6_admission(tmp_path):
    executor = build_executor(tmp_path)

    assert executor.enabled is True
    assert callable(executor.execute)
    assert executor.approval_token == P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN
