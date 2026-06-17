"""RED/GREEN tests for the WP4 controlled AI FLOW workflow-spec validator.

Local/offline only. Exercises ``validate_workflow_spec`` against the canonical
bounded linear read-only flow and every fail-closed rejection class from the
architecture packet (PRD FR1).
"""

from __future__ import annotations

import copy

import pytest

from sachima_supervisor.ai_flow_spec import (
    SCHEMA_VERSION,
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


def _canonical() -> dict:
    return canonical_read_only_workflow_mapping()


# --------------------------------------------------------------------------- #
# Accept the canonical bounded linear read-only flow
# --------------------------------------------------------------------------- #
def test_accepts_canonical_bounded_linear_read_only_flow() -> None:
    spec = validate_workflow_spec(_canonical())
    assert isinstance(spec, WorkflowSpec)
    assert spec.schema_version == SCHEMA_VERSION
    assert tuple(step.step_id for step in spec.steps) == (
        "architect",
        "programmer_candidate",
        "reviewer",
    )
    assert all(isinstance(role, RoleBinding) for role in spec.roles)
    assert all(isinstance(step, StepSpec) for step in spec.steps)
    assert isinstance(spec.bounds, WorkflowBounds)
    # every step binds a read-only role key
    role_by_logical = {role.logical_role: role for role in spec.roles}
    for step in spec.steps:
        binding = role_by_logical[step.logical_role]
        assert binding.capabilities == ("read", "search")


def test_digests_are_deterministic_and_distinct() -> None:
    spec = validate_workflow_spec(_canonical())
    d1 = workflow_spec_digest(spec)
    d2 = workflow_spec_digest(validate_workflow_spec(_canonical()))
    assert d1 == d2
    assert d1.startswith("sha256:")
    rbd = role_binding_digest(spec)
    assert rbd.startswith("sha256:")
    assert rbd != d1


# --------------------------------------------------------------------------- #
# Fail-closed rejections (each must raise AiFlowSpecError)
# --------------------------------------------------------------------------- #
def test_rejects_wrong_schema_version() -> None:
    raw = _canonical()
    raw["schema_version"] = "sachima.ai_flow.local.v2"
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_cycle() -> None:
    raw = _canonical()
    # Make architect depend on reviewer -> a cycle, with matching edges.
    raw["steps"][0]["depends_on"] = ["reviewer"]
    raw["edges"] = [
        ["reviewer", "architect"],
        ["architect", "programmer_candidate"],
        ["programmer_candidate", "reviewer"],
    ]
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_duplicate_step_id() -> None:
    raw = _canonical()
    raw["steps"][1]["step_id"] = "architect"
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_edge_to_unknown_node() -> None:
    raw = _canonical()
    raw["edges"] = [["architect", "ghost_step"], ["programmer_candidate", "reviewer"]]
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_edges_not_derivable_from_dependencies() -> None:
    raw = _canonical()
    # Drop the second edge so edges no longer match declared depends_on.
    raw["edges"] = [["architect", "programmer_candidate"]]
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_too_many_steps_for_bounds() -> None:
    raw = _canonical()
    raw["bounds"]["max_steps"] = 2
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_fan_out_beyond_linear() -> None:
    raw = _canonical()
    # Both programmer_candidate and reviewer depend on architect -> architect
    # has out-degree 2 (fan-out), which slice 1 rejects.
    raw["bounds"]["max_steps"] = 8
    raw["steps"][2]["depends_on"] = ["architect"]
    raw["steps"][2]["input_refs"] = ["architecture_packet"]
    raw["edges"] = [
        ["architect", "programmer_candidate"],
        ["architect", "reviewer"],
    ]
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_missing_role_binding() -> None:
    raw = _canonical()
    del raw["roles"]["reviewer"]
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_role_key_not_in_allowlist() -> None:
    raw = _canonical()
    raw["roles"]["architect"]["role_key"] = "sachima.unknown.role"
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_future_role_key() -> None:
    raw = _canonical()
    # A documented-but-not-runnable future write-capable role.
    raw["roles"]["architect"]["role_key"] = "sachima.claude.main_programmer"
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_capability_outside_read_search() -> None:
    raw = _canonical()
    raw["roles"]["reviewer"]["capabilities"] = ["read", "write"]
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_empty_output_contract() -> None:
    raw = _canonical()
    raw["steps"][0]["output_contract"] = ""
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_input_ref_not_produced_upstream() -> None:
    raw = _canonical()
    # reviewer consumes something no ancestor ever produced.
    raw["steps"][2]["input_refs"] = ["never_produced_contract"]
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_str_subclass_field() -> None:
    class HostileStr(str):
        pass

    raw = _canonical()
    raw["workflow_id"] = HostileStr("wf_controlled_ai_flow_local_v1")
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_dict_subclass_root() -> None:
    class HostileDict(dict):
        pass

    raw = HostileDict(_canonical())
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_list_subclass_steps() -> None:
    class HostileList(list):
        pass

    raw = _canonical()
    raw["steps"] = HostileList(raw["steps"])
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_non_positive_bounds() -> None:
    raw = _canonical()
    raw["bounds"]["max_runtime_seconds"] = 0
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_rejects_bool_where_int_required() -> None:
    raw = _canonical()
    raw["bounds"]["max_steps"] = True  # bool must not satisfy an int bound
    with pytest.raises(AiFlowSpecError):
        validate_workflow_spec(raw)


def test_canonical_mapping_is_independent_copy() -> None:
    a = canonical_read_only_workflow_mapping()
    b = canonical_read_only_workflow_mapping()
    a["steps"][0]["step_id"] = "mutated"
    assert b["steps"][0]["step_id"] == "architect"
    # and a deep copy of the canonical still validates
    assert validate_workflow_spec(copy.deepcopy(b)) is not None
