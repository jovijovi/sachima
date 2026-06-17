"""RED/GREEN tests for the WP4 controlled AI FLOW evidence projection (FR7)."""

from __future__ import annotations

import pytest

from sachima_supervisor.ai_flow_evidence import (
    FINAL_VERDICTS,
    AiFlowEvidenceError,
    WorkflowEvidence,
    _walk_strings,
    build_workflow_evidence,
    default_non_approval_flags,
)

_WSD = "sha256:" + "a" * 64
_RBD = "sha256:" + "b" * 64


def _evidence(**overrides) -> WorkflowEvidence:
    base = dict(
        workflow_id="wf_controlled_ai_flow_local_v1",
        workflow_spec_digest=_WSD,
        role_binding_digest=_RBD,
        state_transitions=[
            {"step_id": "architect", "status": "completed", "attempt_index": 1, "error_code": None},
            {"step_id": "reviewer", "status": "completed", "attempt_index": 1, "error_code": None},
        ],
        step_fingerprints={"architect": "c" * 64, "reviewer": "d" * 64},
        role_binding_refs=[
            {"logical_role": "architect", "role_key": "sachima.claude.read_only_reviewer"},
        ],
        gate_decisions=[
            {"gate_type": "pre_step", "gate_ref": "gate_ref_ok", "status": "granted", "step_id": "architect"},
        ],
        artifact_refs=[
            {"artifact_id": "artifact_architecture_packet", "content_digest": _WSD,
             "artifact_kind": "architecture_packet", "byte_count": 12, "producer_step_id": "architect"},
        ],
        error_codes=[],
        active_run_cancellation_watch=False,
        final_verdict="succeeded",
    )
    base.update(overrides)
    return build_workflow_evidence(**base)


def test_evidence_contains_refs_and_codes_only_no_raw_material() -> None:
    evidence = _evidence()
    rendered = "\n".join(_walk_strings(evidence.to_durable_state())).lower()
    for marker in (
        "raw_prompt", "prompt_body", "media_path", "card_json", "signed_url",
        "tool_output", "bearer ", "api_key", "traceback",
    ):
        assert marker not in rendered


def test_evidence_is_deterministic_for_identical_input() -> None:
    a = _evidence().to_durable_state()
    b = _evidence().to_durable_state()
    assert a == b
    assert a["evidence_digest"] == b["evidence_digest"]


def test_evidence_carries_non_approval_flags() -> None:
    evidence = _evidence()
    flags = evidence.to_durable_state()["non_approval_flags"]
    assert flags == default_non_approval_flags()
    assert flags["real_workflow_execution"] is False
    assert flags["additional_acpx_invocation"] is False
    assert flags["write_capable_roles"] is False


def test_evidence_surfaces_active_run_watch_marker_when_set() -> None:
    evidence = _evidence(active_run_cancellation_watch=True, final_verdict="ambiguous_fail_closed")
    state = evidence.to_durable_state()
    assert state["active_run_cancellation_watch"] is True
    assert state["cancellation_summary"]["active_run_cancellation_watch"] is True
    assert evidence.active_run_cancellation_watch is True


def test_final_verdict_must_be_in_allowed_set() -> None:
    with pytest.raises(AiFlowEvidenceError):
        _evidence(final_verdict="totally_done")
    assert set(FINAL_VERDICTS) == {
        "succeeded", "failed", "cancelled", "parked", "ambiguous_fail_closed",
    }


def test_rejects_raw_material_in_inputs() -> None:
    with pytest.raises(AiFlowEvidenceError):
        _evidence(
            state_transitions=[
                {"step_id": "architect", "status": "completed", "attempt_index": 1,
                 "error_code": "raw_prompt_leak"},
            ],
        )
