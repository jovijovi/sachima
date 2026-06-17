"""RED/GREEN tests for WP4 controlled AI FLOW operator gates (FR2/FR6)."""

from __future__ import annotations

import pytest

from sachima_supervisor.ai_flow_gates import (
    GATE_TYPES,
    AiFlowGateError,
    GateDecision,
    _walk_strings,
    check_gate,
    gate_decision_projection,
)


def test_each_gate_type_grants_on_exact_operator_gate_and_matching_ref() -> None:
    for gate_type in GATE_TYPES:
        decision = check_gate(
            gate_type,
            operator_gate=True,
            gate_ref="gate_ref_ok",
            expected_ref="gate_ref_ok",
            step_id="architect",
        )
        assert isinstance(decision, GateDecision)
        assert decision.status == "granted"
        assert decision.granted is True
        assert decision.gate_type == gate_type


def test_grants_without_expected_ref_when_present_and_safe() -> None:
    decision = check_gate("admission", operator_gate=True, gate_ref="admission_ref_1")
    assert decision.granted is True


def test_fails_closed_when_operator_gate_not_true() -> None:
    for value in (False, None, 1, "true"):
        decision = check_gate("pre_step", operator_gate=value, gate_ref="gate_ref_ok")
        assert decision.granted is False
        assert decision.status == "missing"


def test_fails_closed_on_missing_ref() -> None:
    decision = check_gate("pre_step", operator_gate=True, gate_ref=None)
    assert decision.granted is False
    assert decision.status == "missing"


def test_fails_closed_on_mismatched_ref() -> None:
    decision = check_gate(
        "post_step", operator_gate=True, gate_ref="actual_ref", expected_ref="approved_ref"
    )
    assert decision.granted is False
    assert decision.status == "mismatch"


def test_fails_closed_on_ambiguous_unsafe_ref() -> None:
    decision = check_gate("terminal", operator_gate=True, gate_ref="NOT A SAFE REF!!")
    assert decision.granted is False
    assert decision.status == "ambiguous"
    # the unsafe ref must not be retained on the record
    assert decision.gate_ref is None


def test_unknown_gate_type_raises() -> None:
    with pytest.raises(AiFlowGateError):
        check_gate("auto_route", operator_gate=True, gate_ref="x")


def test_decision_projection_is_sanitized() -> None:
    decision = check_gate(
        "pre_step", operator_gate=True, gate_ref="raw_prompt_ref", expected_ref="raw_prompt_ref"
    )
    # gate_ref carries a forbidden marker -> treated as ambiguous, not stored raw
    assert decision.status == "ambiguous"
    projection = gate_decision_projection(decision)
    rendered = "\n".join(_walk_strings(projection)).lower()
    assert "raw_prompt" not in rendered
    assert projection["type"].startswith("sachima.supervisor.ai_flow_gate_record")
