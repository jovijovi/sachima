"""RED/GREEN tests for FlowWeaver Phase 29 callable stub Activity implementation."""

from __future__ import annotations

import ast
import copy
import inspect
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gateway.flowweaver_delivery_agent_execution_contract import (
    FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
    describe_flowweaver_delivery_agent_execution_contract,
)
from gateway.flowweaver_stub_activity_boundary_contract import (
    build_flowweaver_stub_activity_boundary_contract_report,
    describe_flowweaver_stub_activity_boundary_contract,
)
from gateway.flowweaver_stub_activity_boundary_contract_validation import (
    build_flowweaver_stub_activity_boundary_contract_validation_report,
    describe_flowweaver_stub_activity_boundary_contract_validation_contract,
)
from gateway.flowweaver_stub_activity_implementation import (
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_CONTRACT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION,
    build_flowweaver_stub_activity_implementation_report,
    deliver_artifact,
    describe_flowweaver_stub_activity_implementation_contract,
    execute_agent_turn,
    validate_claim_check_ref,
    validate_flowweaver_stub_activity_implementation_report,
)
from gateway.flowweaver_stub_activity_implementation_design import (
    build_flowweaver_stub_activity_implementation_design_report,
    describe_flowweaver_stub_activity_implementation_design_contract,
)
from gateway.flowweaver_stub_activity_implementation_validation import (
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_CONTRACT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT,
    build_flowweaver_stub_activity_implementation_validation_report,
    describe_flowweaver_stub_activity_implementation_validation_contract,
)
from gateway.flowweaver_stub_activity_orchestration import (
    describe_flowweaver_stub_activity_orchestration_contract,
    orchestrate_flowweaver_stub_activities,
)
from gateway.flowweaver_stub_activity_orchestration_validation import (
    build_flowweaver_stub_activity_orchestration_validation_report,
    describe_flowweaver_stub_activity_orchestration_validation_contract,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_SOURCE = ROOT / "gateway" / "flowweaver_stub_activity_implementation.py"
PLAN_DOC = ROOT / "docs" / "plans" / "2026-05-09-flowweaver-phase29-stub-activity-implementation.md"
DEV_LOG = ROOT / "docs" / "dev_log" / "2026-05-09-flowweaver-phase29-stub-activity-implementation.md"
RUNBOOK = ROOT / "docs" / "runbooks" / "flowweaver-stub-activity-implementation.md"
ROADMAP_PLAN = ROOT / "docs" / "plans" / "2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md"
ROADMAP_DEV_LOG = ROOT / "docs" / "dev_log" / "2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md"

EXPECTED_ACTIVITY_NAMES = ["validate_claim_check_ref", "execute_agent_turn", "deliver_artifact"]
EXPECTED_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_contract",
    "consumes_report",
    "entrypoints",
    "report_fields",
    "activity_functions",
    "implementation_policy",
    "validation_policy",
    "checks",
    "separate_approvals",
    "forbidden_side_effects",
    "side_effects",
]
EXPECTED_REPORT_FIELDS = [
    "type",
    "version",
    "phase",
    "ok",
    "verdict",
    "operation",
    "phase28_verdict",
    "activity_function_names",
    "implementation_policy",
    "validation_policy",
    "checks",
    "error_code",
    "side_effects",
]
EXPECTED_ACTIVITY_FUNCTIONS = [
    {
        "name": "validate_claim_check_ref",
        "implementation_mode": "plain_callable_stub_no_external_effects",
        "input_fields": ["claim_check_ref", "policy_descriptor"],
        "result_fields": ["activity", "status", "claim_ref", "error_code", "side_effects"],
        "allowed_statuses": ["validated", "rejected"],
        "error_codes": ["invalid_claim_ref", "noncanonical_claim_kind", "unsafe_material"],
        "runtime_calls": [],
        "side_effects": [],
    },
    {
        "name": "execute_agent_turn",
        "implementation_mode": "plain_callable_stub_no_external_effects",
        "input_fields": ["execution_request", "validated_claim"],
        "result_fields": ["activity", "status", "artifact_ref", "error_code", "side_effects"],
        "allowed_statuses": ["stubbed", "rejected"],
        "error_codes": ["invalid_agent_activity_input", "unsafe_material", "agent_execution_not_approved"],
        "runtime_calls": [],
        "side_effects": [],
    },
    {
        "name": "deliver_artifact",
        "implementation_mode": "plain_callable_stub_no_external_effects",
        "input_fields": ["artifact", "delivery_plan"],
        "result_fields": ["activity", "status", "delivery_ref", "error_code", "side_effects"],
        "allowed_statuses": ["planned", "rejected"],
        "error_codes": ["invalid_delivery_activity_input", "unsafe_material", "delivery_execution_not_approved"],
        "runtime_calls": [],
        "side_effects": [],
    },
]
EXPECTED_IMPLEMENTATION_POLICY = {
    "mode": "plain_callable_stubs_only",
    "temporal_sdk": "forbidden_in_phase29",
    "activity_decorators": "forbidden_in_phase29",
    "agent_tool_execution": "stubbed_not_executed",
    "gateway_delivery_ack": "stubbed_not_executed",
    "claim_check_storage_io": "forbidden_in_phase29",
    "side_effects": [],
}
EXPECTED_VALIDATION_POLICY = {
    "mode": "exact_inputs_sanitized_stub_outputs",
    "required_next_phase": "local_temporal_stub_activity_orchestration",
    "exact_key_validation": "required",
    "raw_material_policy": "reject_and_do_not_echo",
    "side_effects": [],
}
EXPECTED_CHECKS = [
    "phase28_contract_valid",
    "phase28_report_valid",
    "activity_functions_callable",
    "implementation_policy_plain_stubs_only",
    "validation_policy_exact_inputs",
    "separate_approvals_preserved",
    "side_effects_absent",
    "raw_material_absent",
]
EXPECTED_SEPARATE_APPROVALS = [
    "local_temporal_stub_activity_orchestration",
    "temporal_activity_definition",
    "worker_lifecycle",
    "real_agent_tool_execution",
    "real_send_edit_render_callback_control",
    "delivery_ack_updates",
    "production_config_write",
    "gateway_restart",
]
EXPECTED_FORBIDDEN_SIDE_EFFECTS = [
    "temporal_sdk_import",
    "temporal_client",
    "worker_lifecycle",
    "workflow_environment",
    "activity_definition",
    "workflow_execute_activity",
    "gateway_hook_change",
    "gateway_adapter_access",
    "config_write",
    "claim_check_storage_io",
    "file_write",
    "subprocess",
    "socket",
    "docker",
    "daemon",
    "service_startup",
    "send",
    "edit",
    "render",
    "callback_control",
    "delivery_ack_update",
    "agent_execution",
    "tool_execution",
    "prototype_import",
    "implementation_validation_builder_invocation",
    "implementation_design_builder_invocation",
    "orchestrator_invocation",
]
PRIVATE_CHAT_ID = "oc_" + "phase29_private_chat"
PRIVATE_USER_ID = "ou_" + "phase29_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase29_private_message"
RAW_PROMPT_VALUE = "raw prompt phase29 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase29 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase29"}'
MEDIA_PATH_VALUE = "/tmp/phase29-private.png"
CALLBACK_VALUE = "callback payload phase29 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase29 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "material" + "-phase29"
BEARER_VALUE = "Bearer " + "phase29-private"
OPENAI_KEY_VALUE = "sk-" + "phase29-private"


class SneakyDict(dict[str, object]):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


class SneakyStr(str):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


class SneakyKeyStr(str):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True

    def __hash__(self) -> int:  # pragma: no cover - dict-key attack fixture
        return str.__hash__(self)


class ExplodingKeyStr(str):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        raise RuntimeError("key equality executed")

    def __hash__(self) -> int:  # pragma: no cover - dict-key attack fixture
        return str.__hash__(self)


class SneakyList(list[object]):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


class HostileRepr:
    def __repr__(self) -> str:  # pragma: no cover - assertion trap
        raise RuntimeError("raw hostile repr leak")


class SideEffectRepr:
    calls = 0

    def __repr__(self) -> str:  # pragma: no cover - assertion trap
        type(self).calls += 1
        return "apparently_safe"


def claim_ref() -> dict[str, object]:
    return {
        "ref": "claim_ref_phase29_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    }


def claim_policy() -> dict[str, object]:
    return {
        "mode": "claim_check_refs_only",
        "allowed_kinds": ["agent_input"],
        "checksum_hint": "sha256_64_lower_hex",
        "side_effects": [],
    }


def execution_request() -> dict[str, object]:
    return {
        "transaction_id": "runtime_tx_phase29_1",
        "workflow_id": "runtime_tx_phase29_1",
        "intent_id": "runtime_intent_0",
        "input_ref": "claim_ref_phase29_0",
        "artifact_ref": "runtime_artifact_0",
        "execution_mode": "stub_activity_implementation",
    }


def artifact() -> dict[str, object]:
    return {
        "artifact_ref": "runtime_artifact_0",
        "kind": "stub_agent_result",
        "status": "stubbed",
    }


def delivery_plan() -> dict[str, object]:
    return {
        "transaction_id": "runtime_tx_phase29_1",
        "workflow_id": "runtime_tx_phase29_1",
        "delivery_ref": "runtime_delivery_0",
        "artifact_ref": "runtime_artifact_0",
        "surface": "final_text",
    }


def deeply_nested_list(depth: int) -> list[object]:
    current: list[object] = []
    root = current
    for _ in range(depth):
        child: list[object] = []
        current.append(child)
        current = child
    return root


def phase24_report() -> dict[str, object]:
    phase23_result = orchestrate_flowweaver_stub_activities(
        execution_request={
            "type": "FlowWeaverExecutionRequest",
            "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
            "transaction_id": "runtime_tx_phase29_1",
            "workflow_id": "runtime_tx_phase29_1",
            "intent_id": "runtime_intent_0",
            "execution_mode": "stub_activity_orchestration",
            "input_refs": [claim_ref()],
            "delivery_refs": ["runtime_delivery_0"],
            "approval_gates": [
                "live_config_writes",
                "gateway_restart",
                "production_enablement",
                "real_send_edit_render_callback_control",
                "real_agent_tool_execution",
            ],
            "side_effects": [],
        },
        contract_descriptor=describe_flowweaver_delivery_agent_execution_contract(),
    )
    return build_flowweaver_stub_activity_orchestration_validation_report(
        contract_descriptor=describe_flowweaver_stub_activity_orchestration_contract(),
        orchestration_result=phase23_result,
    )


def phase25_report() -> dict[str, object]:
    return build_flowweaver_stub_activity_boundary_contract_report(
        validation_contract_descriptor=describe_flowweaver_stub_activity_orchestration_validation_contract(),
        validation_report=phase24_report(),
    )


def phase26_report() -> dict[str, object]:
    return build_flowweaver_stub_activity_boundary_contract_validation_report(
        boundary_contract_descriptor=describe_flowweaver_stub_activity_boundary_contract(),
        boundary_contract_report=phase25_report(),
    )


def phase27_report() -> dict[str, object]:
    return build_flowweaver_stub_activity_implementation_design_report(
        boundary_contract_validation_descriptor=describe_flowweaver_stub_activity_boundary_contract_validation_contract(),
        boundary_contract_validation_report=phase26_report(),
    )


def phase28_report() -> dict[str, object]:
    return build_flowweaver_stub_activity_implementation_validation_report(
        implementation_design_contract_descriptor=describe_flowweaver_stub_activity_implementation_design_contract(),
        implementation_design_report=phase27_report(),
    )


def phase28_error_report() -> dict[str, object]:
    return build_flowweaver_stub_activity_implementation_validation_report(
        implementation_design_contract_descriptor={"bad": RAW_PROMPT_VALUE},
        implementation_design_report=phase27_report(),
    )


def expected_error_report(error_code: str) -> dict[str, object]:
    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION,
        "phase": "phase29",
        "ok": False,
        "operation": "implement_flowweaver_stub_activities",
        "error_code": error_code,
        "side_effects": [],
    }


def expected_success_report() -> dict[str, object]:
    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION,
        "phase": "phase29",
        "ok": True,
        "verdict": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT,
        "operation": "implement_flowweaver_stub_activities",
        "phase28_verdict": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT,
        "activity_function_names": EXPECTED_ACTIVITY_NAMES,
        "implementation_policy": EXPECTED_IMPLEMENTATION_POLICY,
        "validation_policy": EXPECTED_VALIDATION_POLICY,
        "checks": {key: True for key in EXPECTED_CHECKS},
        "error_code": None,
        "side_effects": [],
    }


def expected_claim_result() -> dict[str, object]:
    return {
        "activity": "validate_claim_check_ref",
        "status": "validated",
        "claim_ref": "claim_ref_phase29_0",
        "error_code": None,
        "side_effects": [],
    }


def expected_agent_result() -> dict[str, object]:
    return {
        "activity": "execute_agent_turn",
        "status": "stubbed",
        "artifact_ref": "runtime_artifact_0",
        "error_code": None,
        "side_effects": [],
    }


def expected_delivery_result() -> dict[str, object]:
    return {
        "activity": "deliver_artifact",
        "status": "planned",
        "delivery_ref": "runtime_delivery_0",
        "error_code": None,
        "side_effects": [],
    }


def assert_no_raw_values(value: object) -> None:
    rendered = repr(value).lower()
    for marker in (
        PRIVATE_CHAT_ID.lower(),
        PRIVATE_USER_ID.lower(),
        PRIVATE_MESSAGE_ID.lower(),
        RAW_PROMPT_VALUE,
        RAW_TOOL_VALUE,
        CARD_JSON_VALUE.lower(),
        MEDIA_PATH_VALUE.lower(),
        CALLBACK_VALUE,
        RAW_EXCEPTION_VALUE.lower(),
        SENSITIVE_SENTINEL.lower(),
        BEARER_VALUE.lower(),
        OPENAI_KEY_VALUE.lower(),
        "flowweaverexecutionrequest",
        "execution_request",
        "runtime_tx_phase29_1_private",
        "claim_ref_phase29_private",
        FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE,
    ):
        assert marker not in rendered


def mutate_list(values: list[Any], mode: str) -> list[Any]:
    if mode == "missing":
        return values[:-1]
    if mode == "extra":
        return [*values, "unexpected_field"]
    if mode == "reordered":
        return [values[1], values[0], *values[2:]]
    if mode == "duplicated":
        return [*values, values[-1]]
    if mode == "bogus":
        return [*values[:-1], "bogus_field"]
    raise AssertionError(mode)


def rebuilt_with_fields(value: dict[str, Any], fields: list[str]) -> dict[str, object]:
    return {field: value.get(field, "unexpected") for field in fields}


def test_phase29_exposes_plain_synchronous_keyword_only_entrypoints() -> None:
    signatures = {
        build_flowweaver_stub_activity_implementation_report: [
            "implementation_validation_descriptor",
            "implementation_validation_report",
        ],
        validate_claim_check_ref: ["claim_check_ref", "policy_descriptor"],
        execute_agent_turn: ["execution_request", "validated_claim"],
        deliver_artifact: ["artifact", "delivery_plan"],
    }
    for helper, expected_parameters in signatures.items():
        signature = inspect.signature(helper)
        assert list(signature.parameters) == expected_parameters
        assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
        assert signature.return_annotation == "dict[str, object]"
        assert not inspect.iscoroutinefunction(helper)

    for helper in (
        describe_flowweaver_stub_activity_implementation_contract,
        validate_flowweaver_stub_activity_implementation_report,
    ):
        assert not inspect.iscoroutinefunction(helper)


def test_phase29_contract_descriptor_freezes_callable_stub_scope_and_success_verdict() -> None:
    contract = describe_flowweaver_stub_activity_implementation_contract()

    assert list(contract) == EXPECTED_CONTRACT_FIELDS
    assert contract["type"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_CONTRACT_TYPE
    assert contract["version"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION
    assert contract["phase"] == "phase29"
    assert contract["verdict"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT
    assert contract["verdict"] == "ready_for_local_temporal_stub_activity_orchestration"
    assert contract["scope"] == "stub_activity_implementation"
    assert contract["consumes_contract"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_CONTRACT_TYPE
    assert contract["consumes_report"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE
    assert contract["entrypoints"] == [
        "describe_flowweaver_stub_activity_implementation_contract",
        "validate_flowweaver_stub_activity_implementation_report",
        "build_flowweaver_stub_activity_implementation_report",
        "validate_claim_check_ref",
        "execute_agent_turn",
        "deliver_artifact",
    ]
    assert contract["report_fields"] == EXPECTED_REPORT_FIELDS
    assert contract["activity_functions"] == EXPECTED_ACTIVITY_FUNCTIONS
    assert contract["implementation_policy"] == EXPECTED_IMPLEMENTATION_POLICY
    assert contract["validation_policy"] == EXPECTED_VALIDATION_POLICY
    assert contract["checks"] == EXPECTED_CHECKS
    assert contract["separate_approvals"] == EXPECTED_SEPARATE_APPROVALS
    assert contract["forbidden_side_effects"] == EXPECTED_FORBIDDEN_SIDE_EFFECTS
    assert contract["side_effects"] == []


def test_phase29_happy_path_builds_safe_implementation_report_from_phase28_validation_report() -> None:
    report = build_flowweaver_stub_activity_implementation_report(
        implementation_validation_descriptor=describe_flowweaver_stub_activity_implementation_validation_contract(),
        implementation_validation_report=phase28_report(),
    )

    assert report == expected_success_report()
    assert_no_raw_values(report)


def test_phase29_validator_returns_sanitized_deep_copy() -> None:
    report = expected_success_report()
    safe = validate_flowweaver_stub_activity_implementation_report(report)
    safe["activity_function_names"].append("mutated")  # type: ignore[union-attr]
    safe["implementation_policy"]["mode"] = "mutated"  # type: ignore[index]
    safe["validation_policy"]["mode"] = "mutated"  # type: ignore[index]
    safe["checks"]["phase28_contract_valid"] = False  # type: ignore[index]

    assert report == expected_success_report()


def test_phase29_rejects_invalid_phase28_contract_with_sanitized_error_report() -> None:
    result = build_flowweaver_stub_activity_implementation_report(
        implementation_validation_descriptor={"type": RAW_PROMPT_VALUE},
        implementation_validation_report=phase28_report(),
    )

    assert result == expected_error_report("invalid_phase28_stub_activity_implementation_validation_contract")
    assert_no_raw_values(result)


def test_phase29_rejects_invalid_phase28_report_with_sanitized_error_report() -> None:
    report = copy.deepcopy(phase28_report())
    report["activity_design_unit_names"][0] = RAW_PROMPT_VALUE  # type: ignore[index]

    result = build_flowweaver_stub_activity_implementation_report(
        implementation_validation_descriptor=describe_flowweaver_stub_activity_implementation_validation_contract(),
        implementation_validation_report=report,
    )

    assert result == expected_error_report("invalid_phase28_stub_activity_implementation_validation_report")
    assert_no_raw_values(result)


def test_phase29_rejects_phase28_error_report_with_sanitized_error_report() -> None:
    result = build_flowweaver_stub_activity_implementation_report(
        implementation_validation_descriptor=describe_flowweaver_stub_activity_implementation_validation_contract(),
        implementation_validation_report=phase28_error_report(),
    )

    assert result == expected_error_report("invalid_phase28_stub_activity_implementation_validation_report")
    assert_no_raw_values(result)


def test_phase29_builder_rejects_cyclic_phase28_report_with_sanitized_error_report() -> None:
    report = phase28_report()
    report["cycle"] = report

    result = build_flowweaver_stub_activity_implementation_report(
        implementation_validation_descriptor=describe_flowweaver_stub_activity_implementation_validation_contract(),
        implementation_validation_report=report,
    )

    assert result == expected_error_report("invalid_phase28_stub_activity_implementation_validation_report")
    assert_no_raw_values(result)


def test_phase29_builder_rejects_deeply_nested_phase28_report_with_sanitized_error_report() -> None:
    report = phase28_report()
    report["deep"] = deeply_nested_list(1200)

    result = build_flowweaver_stub_activity_implementation_report(
        implementation_validation_descriptor=describe_flowweaver_stub_activity_implementation_validation_contract(),
        implementation_validation_report=report,
    )

    assert result == expected_error_report("invalid_phase28_stub_activity_implementation_validation_report")
    assert_no_raw_values(result)


def test_phase29_callable_stubs_return_deterministic_safe_results() -> None:
    claim_result = validate_claim_check_ref(claim_check_ref=claim_ref(), policy_descriptor=claim_policy())
    assert claim_result == expected_claim_result()

    agent_result = execute_agent_turn(execution_request=execution_request(), validated_claim=claim_result)
    assert agent_result == expected_agent_result()

    delivery_result = deliver_artifact(artifact=artifact(), delivery_plan=delivery_plan())
    assert delivery_result == expected_delivery_result()

    assert_no_raw_values({"claim": claim_result, "agent": agent_result, "delivery": delivery_result})


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda value: {**value, "ref": PRIVATE_CHAT_ID}, "unsafe_material"),
        (lambda value: {**value, "kind": "message_text"}, "noncanonical_claim_kind"),
        (lambda value: {**value, "count": 0}, "invalid_claim_ref"),
        (lambda value: {**value, "count": True}, "invalid_claim_ref"),
        (lambda value: {**value, "checksum_hint": "sha256:" + ("g" * 64)}, "invalid_claim_ref"),
        (lambda value: {SneakyKeyStr(key): item for key, item in value.items()}, "unsafe_material"),
    ],
)
def test_phase29_validate_claim_check_ref_fails_closed_without_echoing_raw_input(mutator: Any, expected: str) -> None:
    source = claim_ref()
    result = validate_claim_check_ref(claim_check_ref=mutator(source), policy_descriptor=claim_policy())

    assert result == {
        "activity": "validate_claim_check_ref",
        "status": "rejected",
        "claim_ref": None,
        "error_code": expected,
        "side_effects": [],
    }
    assert_no_raw_values(result)


def test_phase29_callable_stubs_fail_closed_on_hostile_repr_without_raw_exception_leak() -> None:
    assert validate_claim_check_ref(claim_check_ref=HostileRepr(), policy_descriptor=claim_policy()) == {
        "activity": "validate_claim_check_ref",
        "status": "rejected",
        "claim_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }
    assert execute_agent_turn(execution_request=HostileRepr(), validated_claim=expected_claim_result()) == {
        "activity": "execute_agent_turn",
        "status": "rejected",
        "artifact_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }
    assert deliver_artifact(artifact=HostileRepr(), delivery_plan=delivery_plan()) == {
        "activity": "deliver_artifact",
        "status": "rejected",
        "delivery_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }


def test_phase29_callable_stubs_fail_closed_without_invoking_hostile_repr_side_effects() -> None:
    SideEffectRepr.calls = 0

    assert validate_claim_check_ref(claim_check_ref=SideEffectRepr(), policy_descriptor=claim_policy()) == {
        "activity": "validate_claim_check_ref",
        "status": "rejected",
        "claim_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }
    assert execute_agent_turn(execution_request=SideEffectRepr(), validated_claim=expected_claim_result()) == {
        "activity": "execute_agent_turn",
        "status": "rejected",
        "artifact_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }
    assert deliver_artifact(artifact=SideEffectRepr(), delivery_plan=delivery_plan()) == {
        "activity": "deliver_artifact",
        "status": "rejected",
        "delivery_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }
    assert SideEffectRepr.calls == 0


def test_phase29_callable_stubs_fail_closed_on_cyclic_plain_containers() -> None:
    cyclic_claim = claim_ref()
    cyclic_claim["cycle"] = cyclic_claim
    assert validate_claim_check_ref(claim_check_ref=cyclic_claim, policy_descriptor=claim_policy()) == {
        "activity": "validate_claim_check_ref",
        "status": "rejected",
        "claim_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }

    cyclic_request: list[object] = []
    cyclic_request.append(cyclic_request)
    assert execute_agent_turn(execution_request=cyclic_request, validated_claim=expected_claim_result()) == {
        "activity": "execute_agent_turn",
        "status": "rejected",
        "artifact_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }

    cyclic_artifact: dict[str, object] = {}
    cyclic_artifact["cycle"] = cyclic_artifact
    assert deliver_artifact(artifact=cyclic_artifact, delivery_plan=delivery_plan()) == {
        "activity": "deliver_artifact",
        "status": "rejected",
        "delivery_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }


def test_phase29_callable_stubs_fail_closed_on_deeply_nested_plain_containers() -> None:
    assert validate_claim_check_ref(claim_check_ref=deeply_nested_list(1200), policy_descriptor=claim_policy()) == {
        "activity": "validate_claim_check_ref",
        "status": "rejected",
        "claim_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }
    assert execute_agent_turn(execution_request=deeply_nested_list(1200), validated_claim=expected_claim_result()) == {
        "activity": "execute_agent_turn",
        "status": "rejected",
        "artifact_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }
    assert deliver_artifact(artifact=deeply_nested_list(1200), delivery_plan=delivery_plan()) == {
        "activity": "deliver_artifact",
        "status": "rejected",
        "delivery_ref": None,
        "error_code": "unsafe_material",
        "side_effects": [],
    }


def test_phase29_execute_agent_turn_fails_closed_without_real_agent_or_tool_execution() -> None:
    request = execution_request()
    request["workflow_id"] = "runtime_tx_phase29_mismatch"
    assert execute_agent_turn(execution_request=request, validated_claim=expected_claim_result()) == {
        "activity": "execute_agent_turn",
        "status": "rejected",
        "artifact_ref": None,
        "error_code": "invalid_agent_activity_input",
        "side_effects": [],
    }

    request = execution_request()
    request["input_ref"] = RAW_TOOL_VALUE
    result = execute_agent_turn(execution_request=request, validated_claim=expected_claim_result())
    assert result["error_code"] == "unsafe_material"
    assert_no_raw_values(result)


def test_phase29_deliver_artifact_fails_closed_without_gateway_delivery_or_ack_updates() -> None:
    plan = delivery_plan()
    plan["surface"] = "rich_card"
    assert deliver_artifact(artifact=artifact(), delivery_plan=plan) == {
        "activity": "deliver_artifact",
        "status": "rejected",
        "delivery_ref": None,
        "error_code": "invalid_delivery_activity_input",
        "side_effects": [],
    }

    plan = delivery_plan()
    plan["delivery_ref"] = CALLBACK_VALUE
    result = deliver_artifact(artifact=artifact(), delivery_plan=plan)
    assert result["error_code"] == "unsafe_material"
    assert_no_raw_values(result)


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "bogus"])
def test_phase29_validator_rejects_report_field_mutations(mode: str) -> None:
    report = rebuilt_with_fields(expected_success_report(), mutate_list(EXPECTED_REPORT_FIELDS, mode))

    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_report"):
        validate_flowweaver_stub_activity_implementation_report(report)


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "duplicated", "bogus"])
def test_phase29_contract_descriptor_rejects_report_field_and_activity_list_mutations(mode: str) -> None:
    contract = describe_flowweaver_stub_activity_implementation_contract()
    contract["report_fields"] = mutate_list(EXPECTED_REPORT_FIELDS, mode)

    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_contract"):
        validate_flowweaver_stub_activity_implementation_contract_descriptor_for_test(contract)

    contract = describe_flowweaver_stub_activity_implementation_contract()
    contract["activity_functions"] = mutate_list(EXPECTED_ACTIVITY_FUNCTIONS, mode)
    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_contract"):
        validate_flowweaver_stub_activity_implementation_contract_descriptor_for_test(contract)


@pytest.mark.parametrize("key", EXPECTED_CHECKS)
def test_phase29_validator_rejects_check_bool_impersonators(key: str) -> None:
    report = expected_success_report()
    report["checks"][key] = 1  # type: ignore[index]

    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_report"):
        validate_flowweaver_stub_activity_implementation_report(report)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("type",), SneakyStr(FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE)),
        (("ok",), 1),
        (("phase28_verdict",), SneakyStr(FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT)),
        (("activity_function_names",), SneakyList(EXPECTED_ACTIVITY_NAMES)),
        (("activity_function_names", 0), SneakyStr("validate_claim_check_ref")),
        (("implementation_policy",), SneakyDict(EXPECTED_IMPLEMENTATION_POLICY)),
        (("validation_policy",), SneakyDict(EXPECTED_VALIDATION_POLICY)),
        (("checks",), SneakyDict({key: True for key in EXPECTED_CHECKS})),
        (("side_effects",), SneakyList()),
    ],
)
def test_phase29_validator_rejects_hostile_subclass_values(path: tuple[str | int, ...], replacement: object) -> None:
    report = expected_success_report()
    target: Any = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement

    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_report"):
        validate_flowweaver_stub_activity_implementation_report(report)


def test_phase29_validator_rejects_hostile_top_level_and_nested_keys() -> None:
    report = {SneakyKeyStr(key): value for key, value in expected_success_report().items()}
    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_report"):
        validate_flowweaver_stub_activity_implementation_report(report)

    report = {ExplodingKeyStr(key): value for key, value in expected_error_report("invalid_phase28_stub_activity_implementation_validation_contract").items()}
    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_report"):
        validate_flowweaver_stub_activity_implementation_report(report)

    report = expected_success_report()
    report["implementation_policy"] = {SneakyKeyStr(key): value for key, value in EXPECTED_IMPLEMENTATION_POLICY.items()}
    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_report"):
        validate_flowweaver_stub_activity_implementation_report(report)

    report = expected_success_report()
    report["checks"] = {SneakyKeyStr(key): True for key in EXPECTED_CHECKS}
    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_report"):
        validate_flowweaver_stub_activity_implementation_report(report)


def test_phase29_error_report_validator_accepts_only_sanitized_error_codes() -> None:
    safe = validate_flowweaver_stub_activity_implementation_report(
        expected_error_report("invalid_phase28_stub_activity_implementation_validation_contract")
    )
    assert safe == expected_error_report("invalid_phase28_stub_activity_implementation_validation_contract")

    bad = expected_error_report(RAW_PROMPT_VALUE)
    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_report"):
        validate_flowweaver_stub_activity_implementation_report(bad)


def test_phase29_source_has_no_temporal_gateway_agent_delivery_or_lifecycle_escape_hatches() -> None:
    source = MODULE_SOURCE.read_text()
    tree = ast.parse(source)

    forbidden_import_fragments = ("temporalio", "gateway.platforms", "run_agent", "model_tools", "tools.", "prototypes")
    forbidden_modules = {
        "gateway.flowweaver_stub_activity_implementation_design",
        "gateway.flowweaver_stub_activity_boundary_contract_validation",
        "gateway.flowweaver_stub_activity_boundary_contract",
        "gateway.flowweaver_stub_activity_orchestration",
        "gateway.flowweaver_stub_activity_orchestration_validation",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(fragment in alias.name for fragment in forbidden_import_fragments)
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not any(fragment in module for fragment in forbidden_import_fragments)
            assert module not in forbidden_modules
            imported = {alias.name for alias in node.names}
            assert "build_flowweaver_stub_activity_implementation_validation_report" not in imported
        if isinstance(node, ast.AsyncFunctionDef):
            raise AssertionError(f"async function forbidden in Phase 29: {node.name}")
        if isinstance(node, ast.Call):
            called = ""
            if isinstance(node.func, ast.Name):
                called = node.func.id
            elif isinstance(node.func, ast.Attribute):
                called = node.func.attr
            assert called not in {
                "Client",
                "Worker",
                "WorkflowEnvironment",
                "execute_activity",
                "start_workflow",
                "get_workflow_handle",
                "execute_update",
                "connect",
                "send",
                "edit",
                "render",
                "print",
                "open",
                "write_text",
                "write_bytes",
                "system",
                "run",
                "Popen",
            }
        if isinstance(node, ast.Name):
            assert node.id not in {"Client", "Worker", "WorkflowEnvironment"}


def test_phase29_changed_file_guard_allows_only_implementation_files_and_roadmap_docs() -> None:
    changed = _changed_files()
    allowed = {
        "docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md",
        "docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md",
        "docs/plans/2026-05-09-flowweaver-phase29-stub-activity-implementation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase29-stub-activity-implementation.md",
        "docs/runbooks/flowweaver-stub-activity-implementation.md",
        "gateway/flowweaver_stub_activity_implementation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation.py",
        "docs/plans/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md",
        "docs/dev_log/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md",
        "docs/runbooks/flowweaver-temporal-stub-activity-orchestration.md",
        "gateway/flowweaver_temporal_stub_activity_orchestration.py",
        "tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_design.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py",
        "tests/gateway/test_flowweaver_temporal_observation_bridge.py",
        "tests/gateway/test_flowweaver_temporal_observation_validation_gate.py",
        "tests/gateway/test_flowweaver_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
    }
    forbidden_exact = {"run_agent.py", "model_tools.py", "toolsets.py", "mcp_serve.py", "gateway/run.py"}
    forbidden_prefixes = ("gateway/platforms/", "tools/", "hermes_cli/", "prototypes/")

    assert changed <= allowed
    assert not [path for path in changed if path.startswith(forbidden_prefixes) or path in forbidden_exact]


def test_phase29_docs_record_verdict_boundaries_and_verification() -> None:
    for path in (PLAN_DOC, DEV_LOG, RUNBOOK):
        text = path.read_text()
        assert "ready_for_local_temporal_stub_activity_orchestration" in text
        assert "No Temporal SDK" in text
        assert "No `Client`, `Worker`, `WorkflowEnvironment`" in text
        assert "No Gateway restart" in text
        assert "No real agent or tool execution" in text
        assert "No real delivery ACK updates" in text
        assert "No `@activity.defn`" in text
        assert "tests/gateway/test_flowweaver_stub_activity_implementation.py" in text

    assert ROADMAP_PLAN.exists()
    assert ROADMAP_DEV_LOG.exists()


def validate_flowweaver_stub_activity_implementation_contract_descriptor_for_test(value: object) -> dict[str, object]:
    """Local test copy of the expected P29 descriptor strictness."""

    expected = describe_flowweaver_stub_activity_implementation_contract()
    if type(value) is not dict or not _keys_match_exactly(value, EXPECTED_CONTRACT_FIELDS):
        raise ValueError("invalid_stub_activity_implementation_contract")
    if value != expected:
        raise ValueError("invalid_stub_activity_implementation_contract")
    return copy.deepcopy(value)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _changed_files() -> set[str]:
    base = _git("merge-base", "HEAD", "origin/feature/sachima-channel")
    committed = set(_git("diff", "--name-only", f"{base}...HEAD").splitlines())
    worktree = set(_git("diff", "--name-only").splitlines())
    cached = set(_git("diff", "--cached", "--name-only").splitlines())
    untracked = set(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return {name for name in committed | worktree | cached | untracked if name}


def _keys_match_exactly(value: dict[object, object], expected_keys: list[str]) -> bool:
    actual_keys = list(value.keys())
    if len(actual_keys) != len(expected_keys):
        return False
    for actual, expected in zip(actual_keys, expected_keys, strict=True):
        if type(actual) is not str or actual != expected:
            return False
    return True
