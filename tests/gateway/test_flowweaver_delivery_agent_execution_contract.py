"""RED gate tests for FlowWeaver Phase 22 delivery/agent execution contract."""

from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path
from typing import Any

import pytest

from gateway.flowweaver_delivery_agent_execution_contract import (
    FLOWWEAVER_DELIVERY_AGENT_EXECUTION_CONTRACT_TYPE,
    FLOWWEAVER_DELIVERY_AGENT_EXECUTION_SUCCESS_VERDICT,
    build_flowweaver_delivery_ack_update,
    build_flowweaver_execution_request,
    build_flowweaver_execution_result,
    build_flowweaver_progress_snapshot,
    describe_flowweaver_delivery_agent_execution_contract,
    validate_flowweaver_delivery_agent_execution_contract,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_SOURCE = ROOT / "gateway" / "flowweaver_delivery_agent_execution_contract.py"
PLAN_DOC = ROOT / "docs" / "plans" / "2026-05-09-flowweaver-phase22-delivery-agent-execution-contract-gate.md"
DEV_LOG = ROOT / "docs" / "dev_log" / "2026-05-09-flowweaver-phase22-delivery-agent-execution-contract-gate.md"
RUNBOOK = ROOT / "docs" / "runbooks" / "flowweaver-delivery-agent-execution-contract.md"

CONTRACT_VERSION = "flowweaver.delivery_agent_execution.v0"
EXPECTED_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "contract_objects",
    "canonical_ids",
    "allowed_statuses",
    "claim_check_policy",
    "separate_approvals",
    "ownership_boundaries",
    "forbidden_side_effects",
    "side_effects",
]
EXPECTED_OBJECT_FIELDS = {
    "FlowWeaverExecutionRequest": [
        "type",
        "version",
        "transaction_id",
        "workflow_id",
        "intent_id",
        "execution_mode",
        "input_refs",
        "delivery_refs",
        "approval_gates",
        "side_effects",
    ],
    "FlowWeaverExecutionResult": [
        "type",
        "version",
        "transaction_id",
        "workflow_id",
        "intent_id",
        "status",
        "artifact_refs",
        "delivery_refs",
        "error_code",
        "side_effects",
    ],
    "FlowWeaverDeliveryAckUpdate": [
        "type",
        "version",
        "transaction_id",
        "workflow_id",
        "delivery_id",
        "surface",
        "status",
        "artifact_ref",
        "ack_ref",
        "occurred_at",
        "side_effects",
    ],
    "FlowWeaverProgressSnapshot": [
        "type",
        "version",
        "transaction_id",
        "workflow_id",
        "status",
        "intent_statuses",
        "artifact_refs",
        "delivery_statuses",
        "counts",
        "side_effects",
    ],
}
EXPECTED_REFERENCE_FIELDS = ["ref", "kind", "count", "size", "checksum_hint"]
FORBIDDEN_MATERIAL = [
    "raw_prompt",
    "raw_command",
    "stdout",
    "stderr",
    "tool_output",
    "card_json",
    "media_bytes",
    "media_path",
    "platform_payload",
    "platform_id",
    "chat_id",
    "user_id",
    "message_id",
    "callback_payload",
    "delivery_ack_payload",
    "credential",
    "token",
    "secret",
    "raw_exception_text",
]
SEPARATE_APPROVALS = [
    "live_config_writes",
    "gateway_restart",
    "production_enablement",
    "real_send_edit_render_callback_control",
    "real_agent_tool_execution",
]
FORBIDDEN_SIDE_EFFECTS = [
    "temporal_client",
    "worker_lifecycle",
    "gateway_hook_change",
    "config_write",
    "file_write",
    "subprocess",
    "socket",
    "send",
    "edit",
    "render",
    "callback_control",
    "agent_execution",
    "tool_execution",
]
ALLOWED_STATUSES = {
    "execution_result": ["accepted", "running", "succeeded", "failed", "canceled"],
    "delivery_ack": ["sent", "failed", "acknowledged"],
    "progress_snapshot": ["pending", "running", "waiting_for_user", "completed", "failed", "canceled"],
}

PRIVATE_CHAT_ID = "oc_" + "phase22_private_chat"
PRIVATE_USER_ID = "ou_" + "phase22_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase22_private_message"
RAW_PROMPT_VALUE = "raw prompt phase22 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase22 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase22"}'
MEDIA_PATH_VALUE = "/tmp/phase22-private.png"
CALLBACK_VALUE = "callback payload phase22 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase22 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase22"


class SneakyList(list[str]):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


def claim_ref(index: int = 0) -> dict[str, object]:
    return {
        "ref": f"claim_ref_phase22_{index}",
        "kind": "agent_input",
        "count": 1,
        "size": 128 + index,
        "checksum_hint": "sha256:" + ("a" * 64),
    }


def execution_request() -> dict[str, object]:
    return {
        "type": "FlowWeaverExecutionRequest",
        "version": CONTRACT_VERSION,
        "transaction_id": "runtime_tx_phase22_1",
        "workflow_id": "runtime_tx_phase22_1",
        "intent_id": "runtime_intent_0",
        "execution_mode": "stub_activity_orchestration",
        "input_refs": [claim_ref()],
        "delivery_refs": ["runtime_delivery_0"],
        "approval_gates": list(SEPARATE_APPROVALS),
        "side_effects": [],
    }


def execution_result() -> dict[str, object]:
    return {
        "type": "FlowWeaverExecutionResult",
        "version": CONTRACT_VERSION,
        "transaction_id": "runtime_tx_phase22_1",
        "workflow_id": "runtime_tx_phase22_1",
        "intent_id": "runtime_intent_0",
        "status": "succeeded",
        "artifact_refs": ["runtime_artifact_0"],
        "delivery_refs": ["runtime_delivery_0"],
        "error_code": None,
        "side_effects": [],
    }


def delivery_ack_update() -> dict[str, object]:
    return {
        "type": "FlowWeaverDeliveryAckUpdate",
        "version": CONTRACT_VERSION,
        "transaction_id": "runtime_tx_phase22_1",
        "workflow_id": "runtime_tx_phase22_1",
        "delivery_id": "runtime_delivery_0",
        "surface": "final_text",
        "status": "sent",
        "artifact_ref": "runtime_artifact_0",
        "ack_ref": "runtime_event_delivery_ack_0",
        "occurred_at": "2026-05-09T04:26:27Z",
        "side_effects": [],
    }


def progress_snapshot() -> dict[str, object]:
    return {
        "type": "FlowWeaverProgressSnapshot",
        "version": CONTRACT_VERSION,
        "transaction_id": "runtime_tx_phase22_1",
        "workflow_id": "runtime_tx_phase22_1",
        "status": "running",
        "intent_statuses": {"runtime_intent_0": "running"},
        "artifact_refs": ["runtime_artifact_0"],
        "delivery_statuses": {"runtime_delivery_0": "planned"},
        "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
        "side_effects": [],
    }


def mutate_list(values: list[str], mode: str) -> list[str]:
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


def assert_no_raw_values(value: object) -> None:
    rendered = repr(value).lower()
    for marker in (
        PRIVATE_CHAT_ID.lower(),
        PRIVATE_USER_ID.lower(),
        PRIVATE_MESSAGE_ID.lower(),
        RAW_PROMPT_VALUE,
        RAW_TOOL_VALUE,
        CARD_JSON_VALUE.lower(),
        MEDIA_PATH_VALUE,
        CALLBACK_VALUE,
        RAW_EXCEPTION_VALUE.lower(),
        SENSITIVE_SENTINEL.lower(),
    ):
        assert marker not in rendered


def object_descriptor(contract: dict[str, object], name: str) -> dict[str, object]:
    for candidate in contract["contract_objects"]:
        assert type(candidate) is dict
        if candidate["name"] == name:
            return candidate
    raise AssertionError(f"missing object descriptor: {name}")


def set_nested(value: dict[str, Any], path: tuple[str, ...], replacement: object) -> None:
    current: dict[str, Any] = value
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = replacement


def test_phase22_contract_descriptor_freezes_boundary_and_success_verdict() -> None:
    contract = describe_flowweaver_delivery_agent_execution_contract()

    assert list(contract) == EXPECTED_CONTRACT_FIELDS
    assert contract["type"] == FLOWWEAVER_DELIVERY_AGENT_EXECUTION_CONTRACT_TYPE
    assert contract["version"] == CONTRACT_VERSION
    assert contract["phase"] == "phase22"
    assert contract["verdict"] == FLOWWEAVER_DELIVERY_AGENT_EXECUTION_SUCCESS_VERDICT
    assert contract["verdict"] == "ready_for_stub_activity_orchestration"
    assert contract["scope"] == "delivery_agent_execution_contract_gate"
    assert contract["side_effects"] == []
    assert contract["separate_approvals"] == SEPARATE_APPROVALS
    assert contract["forbidden_side_effects"] == FORBIDDEN_SIDE_EFFECTS
    assert contract["claim_check_policy"] == {
        "mode": "references_only",
        "allowed_reference_fields": EXPECTED_REFERENCE_FIELDS,
        "forbidden_material": FORBIDDEN_MATERIAL,
    }
    assert contract["allowed_statuses"] == ALLOWED_STATUSES
    assert contract["canonical_ids"] == {
        "transaction_id": {"kind": "canonical", "prefix": "runtime_tx_"},
        "workflow_id": {"kind": "transport_alias", "must_equal": "transaction_id"},
        "intent_id": {"kind": "canonical", "prefix": "runtime_intent_", "numeric_suffix": "strict_unpadded"},
        "delivery_id": {"kind": "canonical", "prefix": "runtime_delivery_", "numeric_suffix": "strict_unpadded"},
        "artifact_ref": {"kind": "canonical", "prefix": "runtime_artifact_", "numeric_suffix": "strict_unpadded"},
        "ack_ref": {"kind": "canonical", "prefix": "runtime_event_"},
        "claim_ref": {"kind": "claim_check_reference", "prefix": "claim_ref_"},
    }
    assert contract["ownership_boundaries"] == {
        "temporal": "orchestrates_state_only",
        "hermes_agent": "executes_only_through_future_activity_boundary",
        "gateway": "owns_render_and_delivery_until_separately_approved_ack_control",
    }

    objects = contract["contract_objects"]
    assert [item["name"] for item in objects] == list(EXPECTED_OBJECT_FIELDS)
    for name, fields in EXPECTED_OBJECT_FIELDS.items():
        descriptor = object_descriptor(contract, name)
        assert descriptor == {
            "name": name,
            "fields": fields,
            "side_effects": [],
        }


def test_phase22_contract_validator_accepts_only_the_exact_descriptor() -> None:
    contract = describe_flowweaver_delivery_agent_execution_contract()

    validated = validate_flowweaver_delivery_agent_execution_contract(copy.deepcopy(contract))

    assert validated == contract
    assert validated is not contract


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "bogus"])
def test_phase22_contract_validator_rejects_top_level_field_mutations(mode: str) -> None:
    contract = describe_flowweaver_delivery_agent_execution_contract()
    mutated = copy.deepcopy(contract)
    reordered_fields = mutate_list(EXPECTED_CONTRACT_FIELDS, mode)
    rebuilt = {field: mutated.get(field, "unexpected") for field in reordered_fields}

    with pytest.raises(ValueError, match="invalid_contract"):
        validate_flowweaver_delivery_agent_execution_contract(rebuilt)


@pytest.mark.parametrize("object_name,fields", list(EXPECTED_OBJECT_FIELDS.items()))
@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "duplicated", "bogus"])
def test_phase22_contract_validator_rejects_contract_object_field_mutations(
    object_name: str,
    fields: list[str],
    mode: str,
) -> None:
    contract = describe_flowweaver_delivery_agent_execution_contract()
    mutated = copy.deepcopy(contract)
    object_descriptor(mutated, object_name)["fields"] = mutate_list(fields, mode)

    with pytest.raises(ValueError, match="invalid_contract"):
        validate_flowweaver_delivery_agent_execution_contract(mutated)


@pytest.mark.parametrize(
    "path,expected",
    [
        (("claim_check_policy", "allowed_reference_fields"), EXPECTED_REFERENCE_FIELDS),
        (("claim_check_policy", "forbidden_material"), FORBIDDEN_MATERIAL),
        (("separate_approvals",), SEPARATE_APPROVALS),
        (("forbidden_side_effects",), FORBIDDEN_SIDE_EFFECTS),
        (("allowed_statuses", "execution_result"), ALLOWED_STATUSES["execution_result"]),
        (("allowed_statuses", "delivery_ack"), ALLOWED_STATUSES["delivery_ack"]),
        (("allowed_statuses", "progress_snapshot"), ALLOWED_STATUSES["progress_snapshot"]),
    ],
)
@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "duplicated", "bogus"])
def test_phase22_contract_validator_rejects_list_contract_mutations(
    path: tuple[str, ...],
    expected: list[str],
    mode: str,
) -> None:
    contract = describe_flowweaver_delivery_agent_execution_contract()
    mutated = copy.deepcopy(contract)
    set_nested(mutated, path, mutate_list(expected, mode))

    with pytest.raises(ValueError, match="invalid_contract"):
        validate_flowweaver_delivery_agent_execution_contract(mutated)


def test_phase22_contract_validator_rejects_hostile_list_subclasses() -> None:
    contract = describe_flowweaver_delivery_agent_execution_contract()
    mutated = copy.deepcopy(contract)
    mutated["claim_check_policy"]["allowed_reference_fields"] = SneakyList(EXPECTED_REFERENCE_FIELDS)

    with pytest.raises(ValueError, match="invalid_contract"):
        validate_flowweaver_delivery_agent_execution_contract(mutated)


def test_phase22_raw_field_names_are_policy_metadata_but_raw_values_never_echo() -> None:
    contract = describe_flowweaver_delivery_agent_execution_contract()
    rendered = repr(contract).lower()

    for field_name in FORBIDDEN_MATERIAL:
        assert field_name in rendered
    assert_no_raw_values(contract)

    unsafe = execution_request()
    unsafe["input_refs"] = [
        {
            "ref": PRIVATE_CHAT_ID,
            "kind": "agent_input",
            "count": 1,
            "size": 1,
            "checksum_hint": "sha256:" + ("b" * 64),
        }
    ]
    with pytest.raises(ValueError) as exc_info:
        build_flowweaver_execution_request(unsafe)
    assert str(exc_info.value) == "invalid_execution_request"
    assert_no_raw_values(str(exc_info.value))


def test_phase22_builders_accept_safe_contract_objects_and_preserve_exact_field_order() -> None:
    request = build_flowweaver_execution_request(execution_request())
    result = build_flowweaver_execution_result(execution_result())
    ack = build_flowweaver_delivery_ack_update(delivery_ack_update())
    snapshot = build_flowweaver_progress_snapshot(progress_snapshot())

    assert list(request) == EXPECTED_OBJECT_FIELDS["FlowWeaverExecutionRequest"]
    assert list(result) == EXPECTED_OBJECT_FIELDS["FlowWeaverExecutionResult"]
    assert list(ack) == EXPECTED_OBJECT_FIELDS["FlowWeaverDeliveryAckUpdate"]
    assert list(snapshot) == EXPECTED_OBJECT_FIELDS["FlowWeaverProgressSnapshot"]
    assert request["workflow_id"] == request["transaction_id"]
    assert result["workflow_id"] == result["transaction_id"]
    assert ack["workflow_id"] == ack["transaction_id"]
    assert snapshot["workflow_id"] == snapshot["transaction_id"]
    assert ack["delivery_id"] == "runtime_delivery_0"
    assert snapshot["delivery_statuses"] == {"runtime_delivery_0": "planned"}
    for output in (request, result, ack, snapshot):
        assert output["side_effects"] == []
        assert_no_raw_values(output)


@pytest.mark.parametrize(
    "builder,payload,error_code,mutation",
    [
        (
            build_flowweaver_execution_request,
            execution_request,
            "invalid_execution_request",
            lambda payload: payload.__setitem__("workflow_id", "runtime_tx_phase22_alias"),
        ),
        (
            build_flowweaver_execution_request,
            execution_request,
            "invalid_execution_request",
            lambda payload: payload.__setitem__("delivery_refs", ["runtime_delivery_00"]),
        ),
        (
            build_flowweaver_execution_result,
            execution_result,
            "invalid_execution_result",
            lambda payload: payload.__setitem__("artifact_refs", ["runtime_artifact_00"]),
        ),
        (
            build_flowweaver_delivery_ack_update,
            delivery_ack_update,
            "invalid_delivery_ack_update",
            lambda payload: payload.__setitem__("delivery_id", "runtime_delivery_00"),
        ),
        (
            build_flowweaver_progress_snapshot,
            progress_snapshot,
            "invalid_progress_snapshot",
            lambda payload: payload.__setitem__("intent_statuses", {"runtime_intent_00": "running"}),
        ),
    ],
)
def test_phase22_builders_reject_alias_loopholes_and_padded_numeric_ids(
    builder: Any,
    payload: Any,
    error_code: str,
    mutation: Any,
) -> None:
    unsafe = payload()
    mutation(unsafe)

    with pytest.raises(ValueError) as exc_info:
        builder(unsafe)
    assert str(exc_info.value) == error_code


def test_phase22_module_is_pure_synchronous_and_has_no_runtime_or_gateway_lifecycle() -> None:
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned_imports = {
        "asyncio",
        "temporalio",
        "subprocess",
        "socket",
        "pathlib",
        "gateway.run",
        "gateway.platforms",
        "flowweaver_runtime_client",
    }
    imported_modules = {
        alias.name
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    imported_from = {node.module for node in tree.body if isinstance(node, ast.ImportFrom)}
    assert not (banned_imports & imported_modules)
    assert not (banned_imports & imported_from)
    assert not [node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)]

    banned_call_names = {
        "open",
        "connect",
        "connect_local_temporal",
        "start_workflow",
        "get_workflow_handle",
        "execute_update",
        "Worker",
        "run",
        "send",
        "edit",
        "render",
    }
    call_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                call_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                call_names.add(node.func.attr)
    assert not (banned_call_names & call_names)

    exported_functions = [
        describe_flowweaver_delivery_agent_execution_contract,
        validate_flowweaver_delivery_agent_execution_contract,
        build_flowweaver_execution_request,
        build_flowweaver_execution_result,
        build_flowweaver_delivery_ack_update,
        build_flowweaver_progress_snapshot,
    ]
    assert not [function.__name__ for function in exported_functions if inspect.iscoroutinefunction(function)]


def test_phase22_docs_record_approvals_non_goals_and_next_verdict() -> None:
    for path in (PLAN_DOC, DEV_LOG, RUNBOOK):
        assert path.exists(), path
    combined = "\n".join(path.read_text(encoding="utf-8") for path in (PLAN_DOC, DEV_LOG, RUNBOOK))

    assert "ready_for_stub_activity_orchestration" in combined
    for approval in (
        "live config writes",
        "Gateway restart",
        "production enablement",
        "real send/edit/render/callback control",
        "real agent/tool execution",
    ):
        assert approval in combined
    for non_goal in (
        "No runtime Worker/service lifecycle",
        "No Gateway hook changes",
        "No production config writes",
        "No real agent execution",
        "No real delivery ACK updates",
    ):
        assert non_goal in combined
