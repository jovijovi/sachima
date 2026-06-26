"""P6-B output artifact claim-check (FR3 — exactly one sanitized ArtifactRef).

The injected sink must return exactly one sanitized ``ArtifactRef`` projection;
zero / extra / oversized / unsafe / wrong-producer refs fail closed with
``p6b_output_unsafe``. Only the 6-key projection survives into the outcome — bytes
never enter durable state.
"""

from __future__ import annotations

from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p6b_read_only_real_agent import P6B_OUTPUT_UNSAFE

from .._support import (
    CountingArtifactSink,
    CountingSupervisor,
    OUTPUT_CONTRACT,
    STEP_ID,
    build_executor,
    planning_report_ref,
    role_binding,
    step_request,
)


def _execute(executor):
    return executor.execute(step_request(), role_binding=role_binding(), resolved_inputs=())


def test_exactly_one_ref_projects_into_the_outcome(tmp_path):
    executor = build_executor(tmp_path, invoke_supervisor=CountingSupervisor())

    outcome = _execute(executor)

    assert outcome.ok is True
    assert len(outcome.artifact_refs) == 1
    projection = outcome.artifact_refs[0]
    assert set(projection) == set(C.ALLOWED_ARTIFACT_REF_KEYS)
    assert projection["artifact_kind"] == OUTPUT_CONTRACT
    assert projection["producer_step_id"] == STEP_ID
    assert C.scan_projection_for_leak(projection) is None


def _sink(factory):
    return CountingArtifactSink(refs_factory=factory)


def test_zero_refs_fails_closed(tmp_path):
    sink = _sink(lambda request, result, binding: ())
    executor = build_executor(tmp_path, invoke_supervisor=CountingSupervisor(), artifact_sink=sink)
    outcome = _execute(executor)
    assert outcome.ok is False
    assert outcome.error_code == P6B_OUTPUT_UNSAFE


def test_extra_refs_fail_closed(tmp_path):
    sink = _sink(
        lambda request, result, binding: (
            planning_report_ref(step_id=request.step_id),
            planning_report_ref(step_id=request.step_id, artifact_id="p6b_extra_artifact_0002"),
        )
    )
    executor = build_executor(tmp_path, invoke_supervisor=CountingSupervisor(), artifact_sink=sink)
    outcome = _execute(executor)
    assert outcome.ok is False
    assert outcome.error_code == P6B_OUTPUT_UNSAFE


def test_oversized_ref_fails_closed(tmp_path):
    sink = _sink(lambda request, result, binding: (planning_report_ref(step_id=request.step_id, byte_count=10**9),))
    executor = build_executor(
        tmp_path, invoke_supervisor=CountingSupervisor(), artifact_sink=sink, max_artifact_bytes=65536
    )
    outcome = _execute(executor)
    assert outcome.ok is False
    assert outcome.error_code == P6B_OUTPUT_UNSAFE


def test_wrong_producer_ref_fails_closed(tmp_path):
    sink = _sink(lambda request, result, binding: (planning_report_ref(step_id="some_other_step"),))
    executor = build_executor(tmp_path, invoke_supervisor=CountingSupervisor(), artifact_sink=sink)
    outcome = _execute(executor)
    assert outcome.ok is False
    assert outcome.error_code == P6B_OUTPUT_UNSAFE


def test_unsafe_ref_field_fails_closed(tmp_path):
    sink = _sink(
        lambda request, result, binding: (
            planning_report_ref(step_id=request.step_id, created_at_ref="created_at_ref_card_json"),
        )
    )
    executor = build_executor(tmp_path, invoke_supervisor=CountingSupervisor(), artifact_sink=sink)
    outcome = _execute(executor)
    assert outcome.ok is False
    assert outcome.error_code == P6B_OUTPUT_UNSAFE


def test_sink_exception_fails_closed(tmp_path):
    def boom(request, result, binding):
        raise RuntimeError("must not surface")

    sink = _sink(boom)
    executor = build_executor(tmp_path, invoke_supervisor=CountingSupervisor(), artifact_sink=sink)
    outcome = _execute(executor)
    assert outcome.ok is False
    assert outcome.error_code == P6B_OUTPUT_UNSAFE
