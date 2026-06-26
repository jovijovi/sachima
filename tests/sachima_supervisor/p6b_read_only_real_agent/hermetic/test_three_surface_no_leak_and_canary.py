"""P6-B three-surface no-leak + canary (FR7, merge-blocking).

Seeds raw-prompt / signed-url / traceback / bearer / host-path / card-json canaries
at each P6-B boundary (resolved inputs, the prompt materializer, the output sink)
and asserts they appear in **none** of the surfaces — the executor history
(projection + serialized bytes), the durable controlled-exec claim state, and the
P6 evidence packet — and that each path fails closed with a stable code.
"""

from __future__ import annotations

from sachima_supervisor.activity_controlled_exec import (
    ControlledLocalExecClaimStore,
    query_controlled_local_exec,
)
from sachima_supervisor.ai_flow_store import AiFlowRunStore
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p6_controlled_ai_flow import (
    P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
    P6ControlledAiFlowSession,
)
from sachima_supervisor.p6b_read_only_real_agent import (
    P6B_OUTPUT_UNSAFE,
    P6B_PRECONDITION_UNMET,
    P6B_PROMPT_MATERIALIZATION_FAILED,
)

from .._support import (
    SPEC,
    CountingArtifactSink,
    CountingSupervisor,
    build_executor,
    expected_activity_id,
    planning_report_ref,
    role_binding,
    run_request,
    step_request,
)

_CANARY_MARKERS = ("raw_prompt", "/home/", "card_json", "bearer ", "signed_url", "traceback")


def _assert_no_canary(*objects):
    for obj in objects:
        text = repr(obj).lower()
        for marker in _CANARY_MARKERS:
            assert marker not in text, f"canary {marker!r} leaked into a surface"


def _session(executor):
    return P6ControlledAiFlowSession(
        spec=SPEC,
        store=AiFlowRunStore(),
        executor=executor,
        enabled=True,
        approval_token=P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
        operator_gate=True,
    )


def test_canary_in_resolved_inputs_never_reaches_any_surface(tmp_path):
    supervisor = CountingSupervisor()
    executor = build_executor(tmp_path, invoke_supervisor=supervisor)
    leaky_input = {
        "artifact_id": "upstream_summary",
        "producer_step_id": "upstream_step",
        "content_digest": "sha256:" + "a" * 64,
        "artifact_kind": "summary",
        "byte_count": 16,
        "created_at_ref": "/home/secret/raw_prompt_dump.txt",
    }

    outcome = executor.execute(
        step_request(), role_binding=role_binding(), resolved_inputs=(leaky_input,)
    )

    assert outcome.ok is False
    assert outcome.error_code == P6B_PRECONDITION_UNMET
    assert supervisor.calls == 0
    history = executor.history_projection()
    assert C.scan_projection_for_leak(history) is None
    assert C.scan_bytes_for_leak(executor.serialized_history_bytes()) is None
    _assert_no_canary(outcome, history)


def test_canary_in_prompt_materializer_never_enters_durable_state(tmp_path):
    supervisor = CountingSupervisor()
    store = ControlledLocalExecClaimStore()

    def leaky(_request):
        return "leak bearer secret-token-zzz and a signed_url now"

    executor = build_executor(
        tmp_path, prompt_materializer=leaky, invoke_supervisor=supervisor, controlled_exec_store=store
    )

    outcome = executor.execute(step_request(), role_binding=role_binding(), resolved_inputs=())

    assert outcome.ok is False
    assert outcome.error_code == P6B_PROMPT_MATERIALIZATION_FAILED
    assert supervisor.calls == 0
    result = query_controlled_local_exec(store, activity_id=expected_activity_id())
    _assert_no_canary(result.to_durable_state(), executor.history_projection())


def test_canary_in_artifact_sink_never_reaches_p6_evidence(tmp_path):
    supervisor = CountingSupervisor()
    sink = CountingArtifactSink(
        refs_factory=lambda request, result, binding: (
            planning_report_ref(step_id=request.step_id, created_at_ref="created_at_ref_card_json"),
        )
    )
    executor = build_executor(tmp_path, invoke_supervisor=supervisor, artifact_sink=sink)
    session = _session(executor)

    outcome = session.run_linear(
        run_request(), [step_request()], terminal_gate_ref="terminal_ref_ok"
    )

    assert outcome.ok is False
    assert outcome.final_verdict == "failed"
    ev = outcome.evidence
    assert C.scan_projection_for_leak(ev) is None
    assert ev["artifact_refs"] == []
    _assert_no_canary(ev, executor.history_projection())
