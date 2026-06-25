"""P6-A three-surface no-leak + canary (FR6, merge-blocking).

No raw material may appear in any of the three surfaces — (1) the P6 evidence
projection, (2) the executor's sanitized local history, and (3) the **real**
Temporal serialized event-history bytes + JSON. A canary seeded at the executor
input boundary must be rejected fail-closed **before** any Temporal call, so it
never reaches Temporal history at all. The detectors are proven to have teeth.
"""

from __future__ import annotations

from types import SimpleNamespace

from sachima_supervisor.p5_temporal import contracts as C

from tests.sachima_supervisor.p6_controlled_ai_flow._support import (
    run_request,
    step_requests_in_order,
)
from tests.sachima_supervisor.p6_controlled_ai_flow.hermetic._harness import (
    architect_workflow_id,
    in_thread,
    p5_worker_env,
    run_async,
    runtime_client_for,
    temporal_executor,
    temporal_session,
)


def test_three_surface_no_leak_on_clean_run():
    async def scenario():
        async with p5_worker_env() as env:
            session, executor = temporal_session(env)
            outcome = await in_thread(
                session.run_linear,
                run_request(),
                step_requests_in_order(),
                terminal_gate_ref="terminal_ref_ok",
            )
            runtime_client = runtime_client_for(env)
            wid = architect_workflow_id()
            temporal_bytes = await runtime_client.serialized_event_history_bytes(workflow_id=wid)
            temporal_json = await runtime_client.event_history_json(workflow_id=wid)
            return (
                outcome,
                executor.history_projection(),
                executor.serialized_history_bytes(),
                temporal_bytes,
                temporal_json,
            )

    outcome, hist_proj, hist_bytes, temporal_bytes, temporal_json = run_async(scenario())

    assert outcome.final_verdict == "succeeded"
    # Surface 3 — P6 evidence projection.
    assert C.scan_projection_for_leak(outcome.evidence) is None
    # Surface 2 — executor sanitized local history (SCAN 1 + SCAN 2).
    assert C.scan_projection_for_leak(hist_proj) is None
    assert C.scan_bytes_for_leak(hist_bytes) is None
    # Surface 1' — real Temporal serialized event history (SCAN 2) + JSON (SCAN 1).
    assert C.scan_bytes_for_leak(temporal_bytes) is None
    assert C.scan_projection_for_leak(temporal_json) is None


def test_seeded_canary_is_rejected_before_any_temporal_call():
    canary = "raw_prompt_canary_do_not_persist"
    unsafe_input = {
        "artifact_id": "claim_ref_input_0",
        "producer_step_id": "root",
        "content_digest": "sha256:" + "a" * 64,
        "artifact_kind": "input",
        "byte_count": 64,
        "created_at_ref": "created_at_ref_0001",
        "raw_prompt": canary,
    }

    async def scenario():
        async with p5_worker_env() as env:
            executor = temporal_executor(env)
            request = SimpleNamespace(
                run_id="run_p6_canary",
                step_id="architect",
                attempt_index=1,
                idempotency_key="idem_canary",
                transaction_ref="tx_canary",
                operation_ref="op_canary",
                input_artifact_digests=("sha256:" + "a" * 64,),
            )
            role = SimpleNamespace(role_key="sachima_claude_read_only_reviewer")
            outcome = await executor.aexecute(
                request, role_binding=role, resolved_inputs=(unsafe_input,)
            )
            runtime_client = runtime_client_for(env)
            wid = C.workflow_id_from_refs(C.safe_ref("run_p6_canary"), C.safe_ref("architect"))
            query = await runtime_client.query(workflow_id=wid)
            return outcome, executor.history_projection(), query

    outcome, history, query = run_async(scenario())

    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_UNSAFE_MATERIAL
    # No Temporal workflow was ever started for the rejected step.
    assert query["ok"] is False
    assert query["error_code"] == C.RUNTIME_NOT_FOUND
    # The canary never reached the sanitized history (stable code only).
    assert C.scan_projection_for_leak(history) is None
    assert canary not in str(history)
    assert "raw_prompt" not in str(history).lower()


def test_no_leak_detectors_have_teeth():
    assert C.scan_projection_for_leak({"x": "embeds a raw_prompt here"}) == C.RUNTIME_HISTORY_LEAK_DETECTED
    assert C.scan_bytes_for_leak(b"leaked signed_url=https://x/y") == C.RUNTIME_HISTORY_LEAK_DETECTED
    # A clean sanitized projection passes.
    assert C.scan_projection_for_leak({"ref": "run_p6_alpha", "digest": "sha256:" + "a" * 64}) is None
