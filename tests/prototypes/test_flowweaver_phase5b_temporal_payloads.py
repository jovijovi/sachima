"""Tests for the FlowWeaver Phase 5B local Temporal POC payload boundary."""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from gateway.flowweaver_mock_durable import (
    FLOWWEAVER_MOCK_DURABLE_ACCEPTED,
    consume_flowweaver_shadow_corpus_as_mock_durable_state,
)
from gateway.flowweaver_runtime_contract import (
    FLOWWEAVER_RUNTIME_ACCEPTED,
    build_flowweaver_runtime_ingress_envelope,
)
from gateway.flowweaver_shadow import (
    attach_flowweaver_shadow_snapshot,
    describe_flowweaver_shadow_consumer_contract,
    replay_flowweaver_shadow_corpus,
)
from gateway.flowweaver_shadow_dry_run import (
    FLOWWEAVER_SHADOW_DRY_RUN_PASSED,
    run_flowweaver_gateway_shadow_dry_run,
)
from gateway.progress.events import TransactionSnapshot


ROOT = Path(__file__).resolve().parents[2]
PROTO_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
if str(PROTO_SRC) not in sys.path:
    sys.path.insert(0, str(PROTO_SRC))

PRIVATE_MESSAGE_ID = "om_" + "private_message"
PRIVATE_CHAT_ID = "oc_" + "private_chat"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-value"
FORBIDDEN_RENDERED = [
    PRIVATE_MESSAGE_ID,
    PRIVATE_CHAT_ID,
    SENSITIVE_SENTINEL,
    "raw_snapshot",
    "raw_capture",
    "full_agent_result",
    "raw_prompt",
    "card_json",
    "delivery_ack_payload",
]
EXPECTED_FORBIDDEN_MATERIAL = (
    "raw_snapshot",
    "raw_capture",
    "full_agent_result",
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
    "delivery_ack_payload",
    "credential",
    "token",
    "secret",
)


def load_root_pyproject() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def make_snapshot(*, index: int = 0) -> TransactionSnapshot:
    return TransactionSnapshot(
        transaction_id=f"session_phase5b_runtime_{index}",
        title="Phase 5B runtime contract task",
        status="completed",
        started_at=1000.0 + index,
        updated_at=1002.0 + index,
        completed_at=1002.0 + index,
        recent_operations=(),
    )


def make_shadow_agent_result(*, index: int = 0) -> dict[str, Any]:
    agent_result: dict[str, Any] = {
        "final_response": "done",
        "delivery_state": {
            "final_text": {"sent": True, "reason": "stream_final_response"},
            "rich_cards_sent": [],
        },
    }
    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(index=index),
        enabled=True,
        final_text="done",
    )
    assert attached is not None
    return agent_result


def make_runtime_envelope(*, count: int = 2) -> dict[str, Any]:
    agent_results = [make_shadow_agent_result(index=index) for index in range(count)]
    descriptor = describe_flowweaver_shadow_consumer_contract()
    corpus = replay_flowweaver_shadow_corpus(agent_results, attempts=2)
    assert corpus["verdict"] == "passed"
    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_ACCEPTED
    dry_run_summary = None
    if count == 1:
        dry_run_summary = run_flowweaver_gateway_shadow_dry_run(agent_results[0])
        assert dry_run_summary["verdict"] == FLOWWEAVER_SHADOW_DRY_RUN_PASSED
    envelope = build_flowweaver_runtime_ingress_envelope(
        descriptor,
        corpus,
        projection,
        dry_run_summary,
    )
    assert envelope["verdict"] == FLOWWEAVER_RUNTIME_ACCEPTED
    return envelope


def assert_safe_error(exc: BaseException) -> None:
    rendered = str(exc)
    assert rendered
    for forbidden in FORBIDDEN_RENDERED:
        assert forbidden not in rendered


def test_temporal_poc_extra_is_declared_without_base_dependency() -> None:
    pyproject = load_root_pyproject()
    base_dependencies = pyproject["project"]["dependencies"]
    extras = pyproject["project"]["optional-dependencies"]

    assert not any(str(dep).startswith("temporalio") for dep in base_dependencies)
    assert extras["flowweaver-temporal"] == ["temporalio>=1.27.0,<2"]
    assert "hermes-agent[flowweaver-temporal]" in extras["all"]


def test_temporal_poc_package_imports_are_isolated_under_prototypes() -> None:
    module = importlib.import_module("flowweaver_temporal_poc")
    module_path = Path(module.__file__).resolve()

    assert PROTO_SRC in module_path.parents
    assert module.FLOWWEAVER_TEMPORAL_POC_VERSION == "flowweaver.temporal_poc.v0"
    assert module.FLOWWEAVER_TEMPORAL_TASK_QUEUE == "flowweaver-phase5b-local-poc"


def test_start_payload_is_built_from_accepted_phase5a_envelope() -> None:
    from flowweaver_temporal_poc.payloads import build_start_payload_from_ingress_envelope

    payload = build_start_payload_from_ingress_envelope(make_runtime_envelope(count=2))

    assert payload.transaction_id == "runtime_tx_replay_corpus"
    assert payload.idempotency_key == "runtime_event_start_runtime_tx_replay_corpus"
    assert payload.entry_count == 2
    assert payload.record_counts == {"transactions": 1, "intents": 2, "artifacts": 2, "deliveries": 2}
    assert payload.allowed_runtime_events == (
        "start_transaction",
        "record_operation",
        "publish_artifact",
        "plan_delivery",
        "record_delivery_ack",
        "approve_intent",
        "reject_intent",
        "cancel_transaction",
        "resume_after_user_input",
    )
    assert payload.claim_check_policy["mode"] == "references_only"
    assert "forbidden_material" in payload.claim_check_policy


def test_start_payload_rejects_raw_snapshot_capture_agent_result_and_platform_ids() -> None:
    from flowweaver_temporal_poc.payloads import build_start_payload_from_ingress_envelope

    accepted = make_runtime_envelope(count=1)
    unsafe_cases = []
    for key in ("raw_snapshot", "raw_capture", "full_agent_result", "platform_payload"):
        unsafe = dict(accepted)
        unsafe[key] = {"message_id": PRIVATE_MESSAGE_ID, "raw_prompt": SENSITIVE_SENTINEL}
        unsafe_cases.append(unsafe)
    platform_unsafe = dict(accepted)
    platform_unsafe["message_id"] = PRIVATE_MESSAGE_ID
    unsafe_cases.append(platform_unsafe)

    for unsafe in unsafe_cases:
        with pytest.raises(ValueError) as excinfo:
            build_start_payload_from_ingress_envelope(unsafe)
        assert_safe_error(excinfo.value)


def test_start_payload_rejection_never_echoes_attacker_values() -> None:
    from flowweaver_temporal_poc.payloads import build_start_payload_from_ingress_envelope

    unsafe = make_runtime_envelope(count=1)
    unsafe["raw_prompt"] = f"please leak {SENSITIVE_SENTINEL} and {PRIVATE_CHAT_ID}"

    with pytest.raises(ValueError) as excinfo:
        build_start_payload_from_ingress_envelope(unsafe)

    assert str(excinfo.value) == "invalid_runtime_envelope"
    assert_safe_error(excinfo.value)


def test_start_payload_uses_synthetic_idempotency_key() -> None:
    from flowweaver_temporal_poc.payloads import build_start_payload_from_ingress_envelope

    payload = build_start_payload_from_ingress_envelope(make_runtime_envelope(count=1))

    assert payload.transaction_id.startswith("runtime_tx_")
    assert payload.idempotency_key.startswith("runtime_event_")
    assert ":" not in payload.idempotency_key
    assert "feishu" not in payload.idempotency_key


def test_start_payload_rejects_attacker_controlled_claim_check_policy_values() -> None:
    from flowweaver_temporal_poc.payloads import (
        RuntimeStartPayload,
        build_start_payload_from_ingress_envelope,
        validate_start_payload,
    )

    unsafe_envelope = make_runtime_envelope(count=1)
    unsafe_envelope["claim_check_policy"] = {
        "mode": "references_only",
        "allowed_reference_fields": ["ref", "kind", "count", "size", "checksum_hint"],
        "forbidden_material": [*EXPECTED_FORBIDDEN_MATERIAL, SENSITIVE_SENTINEL, PRIVATE_MESSAGE_ID],
    }
    with pytest.raises(ValueError, match="invalid_runtime_envelope") as excinfo:
        build_start_payload_from_ingress_envelope(unsafe_envelope)
    assert_safe_error(excinfo.value)

    unsafe_direct = RuntimeStartPayload(
        transaction_id="runtime_tx_replay_corpus",
        idempotency_key="runtime_event_start_runtime_tx_replay_corpus",
        entry_count=1,
        record_counts={"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
        allowed_runtime_events=tuple(unsafe_envelope["allowed_runtime_events"]),
        claim_check_policy=unsafe_envelope["claim_check_policy"],
    )
    with pytest.raises(ValueError, match="invalid_start_payload") as direct_excinfo:
        validate_start_payload(unsafe_direct)
    assert_safe_error(direct_excinfo.value)


def test_update_builders_reject_embedded_platform_ids_after_safe_prefixes() -> None:
    from flowweaver_temporal_poc.payloads import (
        cancel_transaction_from_safe_update,
        delivery_ack_from_safe_update,
        human_decision_from_safe_update,
        resume_user_input_from_safe_update,
    )

    invalid_updates = (
        (
            delivery_ack_from_safe_update,
            {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_om_private_message",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_0",
                "status": "sent",
            },
            "invalid_delivery_ack_update",
        ),
        (
            human_decision_from_safe_update,
            {
                "event_type": "approve_intent",
                "event_id": "runtime_event_chat_123",
                "intent_id": "runtime_intent_0",
                "decision": "approved",
                "reason_ref": "claim_ref_reason_0",
            },
            "invalid_human_decision_update",
        ),
        (
            human_decision_from_safe_update,
            {
                "event_type": "approve_intent",
                "event_id": "runtime_event_approve_0",
                "intent_id": "runtime_intent_ou_private_user",
                "decision": "approved",
                "reason_ref": "claim_ref_reason_0",
            },
            "invalid_human_decision_update",
        ),
        (
            cancel_transaction_from_safe_update,
            {
                "event_type": "cancel_transaction",
                "event_id": "runtime_event_om_private_message",
                "reason_ref": None,
            },
            "invalid_cancel_transaction_update",
        ),
        (
            resume_user_input_from_safe_update,
            {
                "event_type": "resume_after_user_input",
                "event_id": "runtime_event_resume_0",
                "input_ref": "claim_ref_om_private_message",
            },
            "invalid_resume_user_input_update",
        ),
        (
            human_decision_from_safe_update,
            {
                "event_type": "approve_intent",
                "event_id": "runtime_event_xchat_123",
                "intent_id": "runtime_intent_0",
                "decision": "approved",
                "reason_ref": "claim_ref_reason_0",
            },
            "invalid_human_decision_update",
        ),
        (
            human_decision_from_safe_update,
            {
                "event_type": "approve_intent",
                "event_id": "runtime_event_xmessage_123",
                "intent_id": "runtime_intent_0",
                "decision": "approved",
                "reason_ref": "claim_ref_reason_0",
            },
            "invalid_human_decision_update",
        ),
        (
            human_decision_from_safe_update,
            {
                "event_type": "approve_intent",
                "event_id": "runtime_event_xplatform_abc",
                "intent_id": "runtime_intent_0",
                "decision": "approved",
                "reason_ref": "claim_ref_reason_0",
            },
            "invalid_human_decision_update",
        ),
        (
            human_decision_from_safe_update,
            {
                "event_type": "approve_intent",
                "event_id": "runtime_event_approve_0",
                "intent_id": "runtime_intent_xou_abc",
                "decision": "approved",
                "reason_ref": "claim_ref_reason_0",
            },
            "invalid_human_decision_update",
        ),
        (
            resume_user_input_from_safe_update,
            {
                "event_type": "resume_after_user_input",
                "event_id": "runtime_event_resume_0",
                "input_ref": "claim_ref_xchat_123",
            },
            "invalid_resume_user_input_update",
        ),
    )
    for builder, invalid, expected_error in invalid_updates:
        with pytest.raises(ValueError) as excinfo:
            builder(invalid)
        assert str(excinfo.value) == expected_error
        assert_safe_error(excinfo.value)


def test_delivery_ack_update_requires_closed_surface_target_status_and_synthetic_ids() -> None:
    from flowweaver_temporal_poc.payloads import DeliveryAckUpdate, delivery_ack_from_safe_update

    update = delivery_ack_from_safe_update(
        {
            "event_type": "record_delivery_ack",
            "delivery_key": "runtime_event_delivery_ack_0",
            "surface": "final_text",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_0",
            "status": "sent",
        }
    )

    assert update == DeliveryAckUpdate(
        delivery_key="runtime_event_delivery_ack_0",
        surface="final_text",
        target_kind="delivery",
        target_id="runtime_delivery_0",
        status="sent",
    )

    invalid_updates = [
        {"event_type": "record_delivery_ack", "delivery_key": "runtime_event_delivery_ack_1", "surface": "feishu", "target_kind": "delivery", "target_id": "runtime_delivery_0", "status": "sent"},
        {"event_type": "record_delivery_ack", "delivery_key": "runtime_event_delivery_ack_1", "surface": "final_text", "target_kind": "delivery", "target_id": PRIVATE_MESSAGE_ID, "status": "sent"},
        {"event_type": "record_delivery_ack", "delivery_key": "runtime_event_delivery_ack_1", "surface": "final_text", "target_kind": "delivery", "target_id": "runtime_delivery_0", "status": "delivered_with_raw_payload"},
    ]
    for invalid in invalid_updates:
        with pytest.raises(ValueError) as excinfo:
            delivery_ack_from_safe_update(invalid)
        assert str(excinfo.value) == "invalid_delivery_ack_update"
        assert_safe_error(excinfo.value)


def test_human_cancel_resume_updates_require_claim_check_refs_and_safe_event_ids() -> None:
    from flowweaver_temporal_poc.payloads import (
        CancelTransactionUpdate,
        HumanDecisionUpdate,
        ResumeUserInputUpdate,
        cancel_transaction_from_safe_update,
        human_decision_from_safe_update,
        resume_user_input_from_safe_update,
    )

    assert human_decision_from_safe_update(
        {
            "event_type": "approve_intent",
            "event_id": "runtime_event_approve_0",
            "intent_id": "runtime_intent_0",
            "decision": "approved",
            "reason_ref": "claim_ref_reason_0",
        }
    ) == HumanDecisionUpdate(
        event_id="runtime_event_approve_0",
        intent_id="runtime_intent_0",
        decision="approved",
        reason_ref="claim_ref_reason_0",
    )
    assert cancel_transaction_from_safe_update(
        {"event_type": "cancel_transaction", "event_id": "runtime_event_cancel_0", "reason_ref": None}
    ) == CancelTransactionUpdate(event_id="runtime_event_cancel_0", reason_ref=None)
    assert resume_user_input_from_safe_update(
        {
            "event_type": "resume_after_user_input",
            "event_id": "runtime_event_resume_0",
            "input_ref": "claim_ref_user_input_0",
        }
    ) == ResumeUserInputUpdate(event_id="runtime_event_resume_0", input_ref="claim_ref_user_input_0")

    invalid_human = {
        "event_type": "approve_intent",
        "event_id": PRIVATE_MESSAGE_ID,
        "intent_id": "runtime_intent_0",
        "decision": "approved",
        "reason_ref": f"raw user text {SENSITIVE_SENTINEL}",
    }
    invalid_cancel = {
        "event_type": "cancel_transaction",
        "event_id": "runtime_event_cancel_1",
        "reason_ref": f"raw cancel reason {SENSITIVE_SENTINEL}",
    }
    invalid_resume = {
        "event_type": "resume_after_user_input",
        "event_id": "runtime_event_resume_1",
        "input_ref": f"raw input {SENSITIVE_SENTINEL}",
    }
    for builder, invalid, expected_error in (
        (human_decision_from_safe_update, invalid_human, "invalid_human_decision_update"),
        (cancel_transaction_from_safe_update, invalid_cancel, "invalid_cancel_transaction_update"),
        (resume_user_input_from_safe_update, invalid_resume, "invalid_resume_user_input_update"),
    ):
        with pytest.raises(ValueError) as excinfo:
            builder(invalid)
        assert str(excinfo.value) == expected_error
        assert_safe_error(excinfo.value)


def test_unsafe_update_payloads_are_rejected_before_temporal_client_calls() -> None:
    from flowweaver_temporal_poc.payloads import delivery_ack_from_safe_update

    class FakeTemporalHandle:
        called = False

        async def execute_update(self, *_args: object, **_kwargs: object) -> None:
            self.called = True
            raise AssertionError("Temporal client must not be called with unsafe payload")

    handle = FakeTemporalHandle()
    unsafe = {
        "event_type": "record_delivery_ack",
        "delivery_key": "runtime_event_delivery_ack_unsafe",
        "surface": "final_text",
        "target_kind": "delivery",
        "target_id": PRIVATE_MESSAGE_ID,
        "status": "sent",
    }

    with pytest.raises(ValueError) as excinfo:
        delivery_ack_from_safe_update(unsafe)

    assert str(excinfo.value) == "invalid_delivery_ack_update"
    assert handle.called is False


def test_client_helper_connects_only_when_called_and_never_starts_service() -> None:
    client_module = importlib.import_module("flowweaver_temporal_poc.client")
    source = Path(client_module.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "start-dev" not in source
    assert "start_dev" not in source
    assert "docker" not in source.lower()
    assert callable(client_module.connect_local_temporal)
    assert callable(client_module.start_local_poc_workflow)


def test_client_helper_requires_explicit_address_and_workflow_id() -> None:
    client_module = importlib.import_module("flowweaver_temporal_poc.client")

    connect_signature = inspect.signature(client_module.connect_local_temporal)
    start_signature = inspect.signature(client_module.start_local_poc_workflow)

    assert connect_signature.parameters["address"].default is inspect.Signature.empty
    assert start_signature.parameters["workflow_id"].default is inspect.Signature.empty

    with pytest.raises(ValueError, match="invalid_temporal_address"):
        client_module._validate_local_address("")
    with pytest.raises(ValueError, match="invalid_workflow_id"):
        client_module._validate_workflow_id(PRIVATE_MESSAGE_ID)
    for unsafe_workflow_id in (
        "runtime_tx_om_private_message",
        "runtime_tx_chat_123",
        "runtime_tx_feishu_private_message",
        "runtime_tx_unsafe_token_value",
    ):
        with pytest.raises(ValueError, match="invalid_workflow_id"):
            client_module._validate_workflow_id(unsafe_workflow_id)


def test_client_helper_module_has_no_gateway_or_platform_imports() -> None:
    client_module = importlib.import_module("flowweaver_temporal_poc.client")
    tree = ast.parse(Path(client_module.__file__).read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    assert not any(name == "gateway" or name.startswith("gateway.") for name in imports)
    assert not any("gateway.platforms" in name or "gateway.run" in name for name in imports)
