"""P6-B bridge translation (WP4 request -> sanitized controlled-exec request).

The bridge turns the WP4 ``request`` / ``role_binding`` / ``resolved_inputs`` into a
``ControlledLocalExecRequest`` of claim-check refs only: a deterministic activity
id, the planning/report prompt **ref** (never raw text), and the upstream inputs
projected to claim-check refs. Raw / unsafe resolved-input material fails closed
before any launch.
"""

from __future__ import annotations

from sachima_supervisor.p6b_planning_report_prompt import P6B_PLANNING_REPORT_PROMPT_REF
from sachima_supervisor.p6b_read_only_real_agent import P6B_PRECONDITION_UNMET

from .._support import (
    CountingArtifactSink,
    CountingSupervisor,
    OP,
    TXN,
    build_executor,
    expected_activity_id,
    role_binding,
    step_request,
)


def _clean_input(**overrides):
    base = {
        "artifact_id": "upstream_summary_artifact",
        "producer_step_id": "upstream_step",
        "content_digest": "sha256:" + "b" * 64,
        "artifact_kind": "high_density_summary",
        "byte_count": 128,
        "created_at_ref": "created_at_ref_upstream_0001",
    }
    base.update(overrides)
    return base


def test_translation_passes_only_claim_check_refs_to_the_seam(tmp_path):
    supervisor = CountingSupervisor()
    executor = build_executor(tmp_path, invoke_supervisor=supervisor, artifact_sink=CountingArtifactSink())

    outcome = executor.execute(
        step_request(), role_binding=role_binding(), resolved_inputs=(_clean_input(),)
    )

    assert outcome.ok is True
    assert supervisor.calls == 1
    seam = supervisor.last_request
    # Deterministic activity id derived from sanitized WP4 refs.
    assert seam.correlation_label == expected_activity_id()
    # Only claim-check refs cross the seam: txn, op, the prompt *ref*, and the
    # upstream input projected to a claim-check ref. No raw prompt body / digest.
    assert TXN in seam.claim_check_refs
    assert OP in seam.claim_check_refs
    assert P6B_PLANNING_REPORT_PROMPT_REF in seam.claim_check_refs
    assert "upstream_summary_artifact" in seam.claim_check_refs
    assert seam.context is None


def test_raw_or_unsafe_resolved_input_fails_closed_before_launch(tmp_path):
    supervisor = CountingSupervisor()
    executor = build_executor(tmp_path, invoke_supervisor=supervisor)
    leaky = _clean_input(created_at_ref="/home/secret/raw_prompt_dump.txt")

    outcome = executor.execute(
        step_request(), role_binding=role_binding(), resolved_inputs=(leaky,)
    )

    assert outcome.ok is False
    assert outcome.error_code == P6B_PRECONDITION_UNMET
    assert supervisor.calls == 0


def test_non_sequence_resolved_inputs_fails_closed(tmp_path):
    supervisor = CountingSupervisor()
    executor = build_executor(tmp_path, invoke_supervisor=supervisor)

    outcome = executor.execute(
        step_request(), role_binding=role_binding(), resolved_inputs="not-a-sequence"
    )

    assert outcome.ok is False
    assert outcome.error_code == P6B_PRECONDITION_UNMET
    assert supervisor.calls == 0
