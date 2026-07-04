"""R5 controlled canary / product hardening contract tests."""

from __future__ import annotations

import json

import pytest

from sachima_supervisor.runtime_spine import (
    build_bounded_canary_packet,
    build_canary_dry_run_report,
    serialize_canary_dry_run_report,
    serialize_canary_request_packet,
    validate_canary_dry_run_report,
    validate_canary_request_packet,
)
from sachima_supervisor.runtime_spine.canary import (
    CANARY_PACKET_TYPE,
    CANARY_REPORT_TYPE,
    RUNTIME_CANARY_NOT_AUTHORIZED,
    RUNTIME_INVALID_CANARY_PACKET,
    CanaryDryRunReport,
    CanaryRequestPacket,
)
from sachima_supervisor.runtime_spine.events import SpineError, scan_for_leak


def _packet() -> CanaryRequestPacket:
    return build_bounded_canary_packet(
        task_id="task_r5_canary",
        gate_ref="r5_gate_ref",
        target_ref="safe_r5_canary_target_01",
        receiver_bridge_ref="safe_r5_receiver_bridge_01",
        artifact_ref="artifact_r5_final_text",
        evidence_ref="evidence_r5_dry_run",
        rollback_ref="rollback_r5_disable_canary",
    )


def test_canary_packet_is_default_off_dry_run_single_surface_and_single_attempt() -> None:
    packet = _packet()
    data = packet.as_dict()

    assert data == {
        "type": CANARY_PACKET_TYPE,
        "task_id": "task_r5_canary",
        "gate_ref": "r5_gate_ref",
        "target_ref": "safe_r5_canary_target_01",
        "receiver_bridge_ref": "safe_r5_receiver_bridge_01",
        "artifact_ref": "artifact_r5_final_text",
        "evidence_ref": "evidence_r5_dry_run",
        "rollback_ref": "rollback_r5_disable_canary",
        "surface": "final_text",
        "max_attempts": 1,
        "default_off": True,
        "dry_run_only": True,
        "execution_authorized": False,
        "receiver_mapping_exposed": False,
        "stop_conditions": [
            "approval_missing",
            "duplicate_attempt",
            "leak_detected",
            "receiver_unavailable",
            "unexpected_surface",
        ],
    }
    assert scan_for_leak(data) is None
    rendered = json.dumps(data, sort_keys=True)
    assert "receiver_mapping" not in data
    assert "safe_targets" not in rendered
    assert "delivery_url" not in rendered
    assert serialize_canary_request_packet(packet) == serialize_canary_request_packet(
        validate_canary_request_packet(packet)
    )


def test_canary_packet_rejects_raw_receiver_mapping_platform_values_and_widening() -> None:
    for unsafe_label in (
        "safecanarystuck",
        "safe_gateway_target",
        "safe_live_target",
        "safe_platform_target",
        "safe_write_target",
    ):
        with pytest.raises(SpineError) as label_error:
            build_bounded_canary_packet(
                task_id="task_r5_canary",
                gate_ref="r5_gate_ref",
                target_ref=unsafe_label,
                receiver_bridge_ref="safe_r5_receiver_bridge_01",
                artifact_ref="artifact_r5_final_text",
                evidence_ref="evidence_r5_dry_run",
                rollback_ref="rollback_r5_disable_canary",
            )
        assert label_error.value.code == RUNTIME_INVALID_CANARY_PACKET

    unsafe_target = "oc" + "_46f5cf118709db22e411e2dddcb9efe5"
    with pytest.raises(SpineError) as target_error:
        build_bounded_canary_packet(
            task_id="task_r5_canary",
            gate_ref="r5_gate_ref",
            target_ref=unsafe_target,
            receiver_bridge_ref="safe_r5_receiver_bridge_01",
            artifact_ref="artifact_r5_final_text",
            evidence_ref="evidence_r5_dry_run",
            rollback_ref="rollback_r5_disable_canary",
        )
    assert target_error.value.code == RUNTIME_INVALID_CANARY_PACKET

    unsafe_bridge = "safe_receiver_" + "chat" + "_id"
    with pytest.raises(SpineError) as bridge_error:
        build_bounded_canary_packet(
            task_id="task_r5_canary",
            gate_ref="r5_gate_ref",
            target_ref="safe_r5_canary_target_01",
            receiver_bridge_ref=unsafe_bridge,
            artifact_ref="artifact_r5_final_text",
            evidence_ref="evidence_r5_dry_run",
            rollback_ref="rollback_r5_disable_canary",
        )
    assert bridge_error.value.code == RUNTIME_INVALID_CANARY_PACKET

    with pytest.raises(SpineError) as surface_error:
        build_bounded_canary_packet(
            task_id="task_r5_canary",
            gate_ref="r5_gate_ref",
            target_ref="safe_r5_canary_target_01",
            receiver_bridge_ref="safe_r5_receiver_bridge_01",
            artifact_ref="artifact_r5_final_text",
            evidence_ref="evidence_r5_dry_run",
            rollback_ref="rollback_r5_disable_canary",
            surface="rich_card",
        )
    assert surface_error.value.code == RUNTIME_CANARY_NOT_AUTHORIZED

    with pytest.raises(SpineError) as attempts_error:
        build_bounded_canary_packet(
            task_id="task_r5_canary",
            gate_ref="r5_gate_ref",
            target_ref="safe_r5_canary_target_01",
            receiver_bridge_ref="safe_r5_receiver_bridge_01",
            artifact_ref="artifact_r5_final_text",
            evidence_ref="evidence_r5_dry_run",
            rollback_ref="rollback_r5_disable_canary",
            max_attempts=2,
        )
    assert attempts_error.value.code == RUNTIME_CANARY_NOT_AUTHORIZED


def test_canary_packet_revalidates_forged_public_surface_without_echoing_raw_material() -> None:
    forged = object.__new__(CanaryRequestPacket)
    object.__setattr__(forged, "type", CANARY_PACKET_TYPE)
    object.__setattr__(forged, "task_id", "task_r5_canary")
    object.__setattr__(forged, "gate_ref", "r5_gate_ref")
    object.__setattr__(forged, "target_ref", "safe_r5_canary_target_01")
    object.__setattr__(forged, "receiver_bridge_ref", "safe_r5_receiver_bridge_01")
    object.__setattr__(forged, "artifact_ref", "artifact_r5_final_text")
    object.__setattr__(forged, "evidence_ref", "evidence_r5_dry_run")
    object.__setattr__(forged, "rollback_ref", "rollback_r5_disable_canary")
    object.__setattr__(forged, "surface", "final_text")
    object.__setattr__(forged, "max_attempts", 1)
    object.__setattr__(forged, "default_off", True)
    object.__setattr__(forged, "dry_run_only", True)
    object.__setattr__(forged, "execution_authorized", True)
    object.__setattr__(forged, "receiver_mapping_exposed", False)
    object.__setattr__(forged, "stop_conditions", ("approval_missing",))

    with pytest.raises(SpineError) as error:
        validate_canary_request_packet(forged)
    assert error.value.code == RUNTIME_CANARY_NOT_AUTHORIZED
    assert "raw" not in str(error.value).lower()


def test_dry_run_report_is_observable_refs_only_and_never_reports_a_send() -> None:
    packet = _packet()
    report = build_canary_dry_run_report(packet, report_ref="report_r5_dry_run_ready")
    data = report.as_dict()

    assert data == {
        "type": CANARY_REPORT_TYPE,
        "task_id": "task_r5_canary",
        "report_ref": "report_r5_dry_run_ready",
        "target_ref": "safe_r5_canary_target_01",
        "surface": "final_text",
        "status": "dry_run_ready",
        "max_attempts": 1,
        "send_attempts": 0,
        "receiver_mapping_exposed": False,
        "rollback_ref": "rollback_r5_disable_canary",
        "evidence_ref": "evidence_r5_dry_run",
        "error_code": None,
        "counters": {
            "blocked": 0,
            "dry_run_ready": 1,
            "rolled_back": 0,
            "sent": 0,
        },
    }
    assert scan_for_leak(data) is None
    assert serialize_canary_dry_run_report(report) == serialize_canary_dry_run_report(
        validate_canary_dry_run_report(report)
    )


def test_dry_run_report_rejects_forged_delivery_success_or_receiver_mapping() -> None:
    packet = _packet()
    report = build_canary_dry_run_report(packet, report_ref="report_r5_dry_run_ready")

    forged_send = object.__new__(CanaryDryRunReport)
    for key, value in report.as_dict().items():
        object.__setattr__(forged_send, key, value)
    object.__setattr__(forged_send, "send_attempts", 1)
    object.__setattr__(forged_send, "counters", {"sent": 1})

    with pytest.raises(SpineError) as send_error:
        validate_canary_dry_run_report(forged_send)
    assert send_error.value.code == RUNTIME_CANARY_NOT_AUTHORIZED

    forged_mapping = object.__new__(CanaryDryRunReport)
    for key, value in report.as_dict().items():
        object.__setattr__(forged_mapping, key, value)
    object.__setattr__(forged_mapping, "receiver_mapping_exposed", True)
    object.__setattr__(forged_mapping, "evidence_ref", "raw" + "_prompt")

    with pytest.raises(SpineError) as mapping_error:
        validate_canary_dry_run_report(forged_mapping)
    assert mapping_error.value.code in {
        RUNTIME_INVALID_CANARY_PACKET,
        RUNTIME_CANARY_NOT_AUTHORIZED,
    }
