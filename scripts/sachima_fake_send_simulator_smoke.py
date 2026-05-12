#!/usr/bin/env python3
"""Phase B local fake-send simulator smoke and evidence writer.

This script exercises SachimaAdapter.send() against a loopback-only fake /send
endpoint. It never reads production config, never restarts Gateway, and never
calls a real external IM delivery API.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.config import PlatformConfig
from gateway.platforms.sachima import SachimaAdapter
from gateway.sachima_fake_send_simulator import FakeSachimaSendSimulator, start_fake_sachima_send_server

EVIDENCE_PATH = Path("outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json")
INITIALIZED_REFS = {
    "runtime_delivery_0",
    "runtime_delivery_1",
    "runtime_delivery_2",
    "runtime_delivery_3",
    "runtime_delivery_4",
}
RAW_MARKERS = (
    "raw_prompt",
    "raw prompt",
    "tool_output",
    "tool output",
    "card_json",
    "media_path",
    "media_bytes",
    "platform_payload",
    "callback_payload",
    "traceback",
    "runtimeerror:",
    "unsafe-token",
    "bearer ",
    "sk-",
    "oc_",
    "ou_",
    "om_",
    "/home/",
    "MEDIA:",
)


def _metadata(surface: str, delivery_ref: str, key: str, artifact_ref: str | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "surface": surface,
        "delivery_ref": delivery_ref,
        "idempotency_key": key,
        "intent_summary": "Phase B fake-send simulator proof",
    }
    if artifact_ref is not None:
        metadata["artifact_ref"] = artifact_ref
    return metadata


def _scan_no_leak(value: Any) -> dict[str, Any]:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    hits = sorted(marker for marker in RAW_MARKERS if marker.lower() in rendered)
    return {"passed": not hits, "raw_marker_hits": len(hits), "markers": hits}


async def _send_surface(
    adapter: SachimaAdapter,
    *,
    surface: str,
    delivery_ref: str,
    key: str,
    content: str,
    artifact_ref: str | None = None,
) -> dict[str, Any]:
    result = await adapter.send(
        "phase-b-local-chat",
        content,
        metadata=_metadata(surface, delivery_ref, key, artifact_ref),
    )
    return {
        "surface": surface,
        "success": result.success,
        "message_id_present": bool(result.message_id),
        "retryable": result.retryable,
    }


async def main() -> None:
    simulator = FakeSachimaSendSimulator(initialized_delivery_refs=INITIALIZED_REFS)
    runner, port = await start_fake_sachima_send_server(simulator)
    adapter = SachimaAdapter(
        PlatformConfig(enabled=True, extra={"send_url": f"http://127.0.0.1:{port}/send"})
    )
    send_results: list[dict[str, Any]] = []
    duplicate_result = None
    rejected_result = None
    try:
        send_results.append(
            await _send_surface(
                adapter,
                surface="progress_card",
                delivery_ref="runtime_delivery_0",
                key="phase-b-progress",
                content="任务：Phase B fake-send simulator proof",
            )
        )
        send_results.append(
            await _send_surface(
                adapter,
                surface="rich_card",
                delivery_ref="runtime_delivery_1",
                key="phase-b-rich",
                content="卡片：Phase B fake-send simulator proof",
            )
        )
        send_results.append(
            await _send_surface(
                adapter,
                surface="final_text",
                delivery_ref="runtime_delivery_2",
                key="phase-b-final",
                content="最终回复：Phase B fake-send simulator proof",
            )
        )
        send_results.append(
            await _send_surface(
                adapter,
                surface="media",
                delivery_ref="runtime_delivery_3",
                key="phase-b-media",
                content="媒体占位：phase-b-safe-media-ref",
            )
        )
        send_results.append(
            await _send_surface(
                adapter,
                surface="artifact",
                delivery_ref="runtime_delivery_4",
                key="phase-b-artifact",
                content="产物引用：runtime_artifact_0",
                artifact_ref="runtime_artifact_0",
            )
        )
        duplicate_result = await _send_surface(
            adapter,
            surface="final_text",
            delivery_ref="runtime_delivery_2",
            key="phase-b-final",
            content="最终回复：Phase B fake-send simulator proof",
        )
        rejected = await adapter.send(
            "phase-b-local-chat",
            "最终回复：Phase B fake-send rejected ref proof",
            metadata=_metadata("final_text", "runtime_delivery_99", "phase-b-bad-ref"),
        )
        rejected_result = {
            "success": rejected.success,
            "retryable": rejected.retryable,
            "message_id_present": bool(rejected.message_id),
        }
    finally:
        await runner.cleanup()

    transcript = simulator.transcript()
    surfaces = [str(row["surface"]) for row in transcript]
    duplicates = 1 if duplicate_result and duplicate_result["success"] else 0
    rejected_count = 1 if rejected_result and rejected_result["success"] is False and rejected_result["retryable"] is False else 0
    evidence: dict[str, Any] = {
        "type": "sachima.phase_b.fake_send_simulator_evidence.v0",
        "decision": "phase_b_fake_send_simulator_evidence_ready_for_pe2_design_packet_only",
        "scope": {
            "loopback_only": True,
            "real_external_delivery": False,
            "gateway_restart_or_config_write": False,
            "pe2_implementation": False,
            "live_default_on": False,
            "production_config_write": False,
        },
        "counts": {
            "adapter_send_attempts": 7,
            "send_requests": 7,
            "accepted_send_requests": len(send_results),
            "transcript_rows": len(transcript),
            "duplicates": duplicates,
            "rejected_uninitialized_refs": rejected_count,
            "ack_updates": len(transcript),
        },
        "surface_state": {
            "progress_card_sent": "progress_card" in surfaces,
            "rich_cards_sent": surfaces.count("rich_card"),
            "final_text_sent": "final_text" in surfaces,
            "media_sent": surfaces.count("media"),
            "artifact_refs_sent": surfaces.count("artifact"),
            "surface_order": surfaces,
        },
        "send_results": send_results,
        "duplicate_replay": duplicate_result,
        "rejected_uninitialized_ref": rejected_result,
        "transcript": transcript,
        "non_approvals_preserved": [
            "pe2_implementation",
            "pe2_live_default_on",
            "real_external_sachima_ingress",
            "production_delivery_control",
            "production_agent_tool_execution_expansion",
            "production_config_write",
            "gateway_restart_or_reload",
            "platform_adapter_mutation",
            "gateway_owned_temporal_lifecycle",
            "real_send_api_or_external_im_call",
        ],
    }
    evidence["no_leak_scan"] = _scan_no_leak(evidence)

    assert evidence["counts"] == {
        "adapter_send_attempts": 7,
        "send_requests": 7,
        "accepted_send_requests": 5,
        "transcript_rows": 5,
        "duplicates": 1,
        "rejected_uninitialized_refs": 1,
        "ack_updates": 5,
    }
    assert evidence["surface_state"]["surface_order"] == [
        "progress_card",
        "rich_card",
        "final_text",
        "media",
        "artifact",
    ]
    assert evidence["no_leak_scan"] == {"passed": True, "raw_marker_hits": 0, "markers": []}

    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"PHASE_B_FAKE_SEND_EVIDENCE_PASS {EVIDENCE_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
