#!/usr/bin/env python3
"""PE-2A local controlled-runtime + fake-delivery smoke/evidence writer.

Runs only in a local test process. It uses a caller-supplied in-memory runtime
surface and the Phase B fake Sachima send simulator. It does not read production
config, start Gateway, own runtime lifecycle, or contact a real delivery API.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.flowweaver_pe2_controlled_runtime_delivery_bridge import (  # noqa: E402
    FlowWeaverPE2AControlledRuntimeDeliveryBridge,
    build_flowweaver_pe2a_evidence,
    pe2a_controlled_runtime_delivery_policy,
    run_flowweaver_pe2a_controlled_runtime_delivery,
    scan_pe2a_no_leak,
)
from gateway.sachima_fake_send_simulator import FakeSachimaSendSimulator  # noqa: E402

EVIDENCE_PATH = Path(
    "outputs/sachima/pe2a-controlled-runtime-fake-delivery/pe2a_controlled_runtime_fake_delivery_evidence.json"
)
INITIALIZED_REFS = {"runtime_delivery_0", "runtime_delivery_1"}


class LocalRuntimeControlSurface:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.ack_refs: list[str] = []

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(request))
        operation = str(request["operation"])
        workflow_id = str(request.get("workflow_id"))
        if operation == "start_transaction":
            return _runtime_result(operation, workflow_id, status="started")
        if operation == "record_operation":
            return _runtime_result(operation, workflow_id, status="recorded")
        if operation == "plan_delivery":
            result = _runtime_result(operation, workflow_id, status="planned")
            result["delivery_refs"] = list(request["delivery_refs"])
            result["surfaces"] = list(request["surfaces"])
            return result
        if operation == "record_delivery_ack":
            self.ack_refs.append(str(request["ack_ref"]))
            result = _runtime_result(operation, workflow_id, status="sent")
            result["delivery_ref"] = request["delivery_ref"]
            result["surface"] = request["surface"]
            result["ack_ref"] = request["ack_ref"]
            return result
        if operation == "query_transaction":
            result = _runtime_result(operation, workflow_id, status="running")
            result["counts"] = {"acks": len(self.ack_refs), "operations": len(self.calls)}
            return result
        return {"ok": False, "operation": operation, "error_code": "unexpected_operation", "side_effects": []}


def _runtime_result(operation: str, workflow_id: str, *, status: str) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": operation,
        "workflow_id": workflow_id,
        "transaction_id": workflow_id,
        "status": status,
        "side_effects": [],
    }


def _envelope(*, discriminator: str, delivery_refs: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "flowweaver.pe2.sachima_ingress_envelope.v0",
        "platform": "sachima",
        "source": "loopback_or_synthetic_pe2a",
        "session_label": "safe_session_pe2a_smoke",
        "turn_label": "safe_turn_pe2a_smoke",
        "turn_discriminator": discriminator,
        "auth": {"hmac_verified": True, "policy_label": "allowlisted_test_operator"},
        "visible_surfaces": {"final_text": True, "rich_card_count": 1, "media_count": 0},
        "claim_refs": {
            "input_ref": "runtime_input_0",
            "delivery_refs": delivery_refs or ["runtime_delivery_0", "runtime_delivery_1"],
            "artifact_refs": ["runtime_artifact_0"],
        },
        "side_effects": [],
    }


def _merge_counts(*results: dict[str, Any]) -> dict[str, int]:
    keys = {
        "accepted_ingress_envelopes",
        "runtime_start_requests",
        "runtime_delivery_plan_requests",
        "fake_send_requests",
        "runtime_ack_updates",
        "duplicates",
        "rejected_probes",
    }
    merged = {key: 0 for key in keys}
    for result in results:
        counts = result.get("counts", {})
        for key in keys:
            merged[key] += int(counts.get(key, 0))
    return merged


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run PE-2A local smoke/evidence gate.")
    parser.add_argument("--base-sha", default=os.environ.get("PE2A_BASE_SHA", "84f6a9010d72"))
    parser.add_argument("--evidence-path", type=Path, default=EVIDENCE_PATH)
    args = parser.parse_args()

    runtime = LocalRuntimeControlSurface()
    fake_send = FakeSachimaSendSimulator(initialized_delivery_refs=INITIALIZED_REFS)
    bridge = FlowWeaverPE2AControlledRuntimeDeliveryBridge()

    positive = await bridge.run(
        ingress_envelope=_envelope(discriminator="safe_discriminator_pe2a_smoke_001"),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )
    duplicate = await bridge.run(
        ingress_envelope=_envelope(discriminator="safe_discriminator_pe2a_smoke_001"),
        runtime_control_surface=runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )
    disabled_runtime = LocalRuntimeControlSurface()
    disabled = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(discriminator="safe_discriminator_pe2a_disabled"),
        runtime_control_surface=disabled_runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(enabled=False),
    )
    missing_fake_runtime = LocalRuntimeControlSurface()
    missing_fake = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(discriminator="safe_discriminator_pe2a_missing_fake"),
        runtime_control_surface=missing_fake_runtime,
        fake_send_surface=None,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )
    rejected_runtime = LocalRuntimeControlSurface()
    rejected_fake = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(
            discriminator="safe_discriminator_pe2a_rejected_ref",
            delivery_refs=["runtime_delivery_9", "runtime_delivery_1"],
        ),
        runtime_control_surface=rejected_runtime,
        fake_send_surface=FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0"}),
        policy=pe2a_controlled_runtime_delivery_policy(),
    )
    restore_runtime = LocalRuntimeControlSurface()
    restore = await run_flowweaver_pe2a_controlled_runtime_delivery(
        ingress_envelope=_envelope(discriminator="safe_discriminator_pe2a_restore"),
        runtime_control_surface=restore_runtime,
        fake_send_surface=fake_send,
        policy=pe2a_controlled_runtime_delivery_policy(),
    )

    assert positive["ok"] is True
    assert duplicate["ok"] is True
    assert duplicate["duplicate"] is True
    assert disabled["error_code"] == "disabled" and disabled_runtime.calls == []
    assert missing_fake["error_code"] == "fake_send_surface_required" and missing_fake_runtime.calls == []
    assert rejected_fake["error_code"] == "fake_send_rejected"
    assert "record_delivery_ack" not in [call["operation"] for call in rejected_runtime.calls]
    assert restore["ok"] is True

    aggregate = dict(positive)
    aggregate["counts"] = _merge_counts(positive, duplicate, disabled, missing_fake, rejected_fake, restore)
    aggregate["runtime_operations"] = (
        list(positive["runtime_operations"])
        + list(duplicate["runtime_operations"])
        + list(disabled["runtime_operations"])
        + list(missing_fake["runtime_operations"])
        + list(rejected_fake["runtime_operations"])
        + list(restore["runtime_operations"])
    )
    aggregate["delivery_ack_refs"] = list(positive["delivery_ack_refs"]) + list(restore["delivery_ack_refs"])
    aggregate["delivery_events"] = (
        list(positive["delivery_events"])
        + list(duplicate["delivery_events"])
        + list(disabled["delivery_events"])
        + list(missing_fake["delivery_events"])
        + list(rejected_fake["delivery_events"])
        + list(restore["delivery_events"])
    )
    aggregate["duplicate_ingress_refs"] = (
        list(positive["duplicate_ingress_refs"])
        + list(duplicate["duplicate_ingress_refs"])
        + list(disabled["duplicate_ingress_refs"])
        + list(missing_fake["duplicate_ingress_refs"])
        + list(rejected_fake["duplicate_ingress_refs"])
        + list(restore["duplicate_ingress_refs"])
    )
    aggregate["rejected_probe_codes"] = ["fake_send_surface_required", "fake_send_rejected"]
    aggregate["negative_probes"] = {
        "disabled_policy": "zero_runtime_and_fake_send_calls",
        "missing_fake_send_surface": "zero_runtime_calls",
        "rejected_uninitialized_delivery_ref": "zero_runtime_ack_updates",
    }
    aggregate["rollback_restore"] = {"restore_positive": "one_additional_controlled_chain"}

    evidence = build_flowweaver_pe2a_evidence(aggregate, base_sha=str(args.base_sha))
    evidence["runtime_call_order"] = [call["operation"] for call in runtime.calls]
    evidence["fake_send_transcript_rows"] = len(fake_send.transcript())
    evidence["no_leak_scan"] = scan_pe2a_no_leak(evidence)

    assert evidence["no_leak_scan"] == {"passed": True, "raw_marker_hits": 0, "markers": []}
    assert evidence["counts"]["runtime_ack_updates"] == 4
    assert evidence["counts"]["fake_send_requests"] == 5
    assert evidence["counts"]["duplicates"] == 1
    assert evidence["counts"]["rejected_probes"] == 2
    assert evidence["scope"]["real_external_ingress"] is False
    assert evidence["scope"]["real_external_delivery"] is False

    args.evidence_path.parent.mkdir(parents=True, exist_ok=True)
    args.evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"PE2A_CONTROLLED_RUNTIME_FAKE_DELIVERY_EVIDENCE_PASS {args.evidence_path}")
    print("PE2A_FINAL_GATE_PASS")


if __name__ == "__main__":
    asyncio.run(main())
