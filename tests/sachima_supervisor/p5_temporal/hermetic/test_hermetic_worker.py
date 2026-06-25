"""T9 hermetic-local real-Worker gate (FR8, Gate H, merge-blocking).

Runs the real ``StepWorkflow`` + ``p5_step_activity`` on a real Temporal Worker
inside a hermetic time-skipping environment (isolated namespace; no production /
staging cluster). Probes: happy path (controlled-deterministic, claim-check refs
only), duplicate-start idempotency + divergent conflict, restart/recovery by
workflow id with no duplicate execution and no auto-relaunch, and the WP3b
active-run cancellation WATCH.
"""

from __future__ import annotations

import asyncio

from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.p5_temporal import (
    P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    P5TemporalStepExecutor,
)
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.workflow import StepWorkflow

from tests.sachima_supervisor.p5_temporal.hermetic._harness import (
    control_surface_for,
    make_start_request,
    p5_worker_env,
    run_async,
    runtime_client_for,
)


def test_happy_path_controlled_deterministic_claim_check_only():
    async def scenario():
        async with p5_worker_env() as env:
            client = runtime_client_for(env)
            req = make_start_request()
            wid = C.deterministic_workflow_id(req)
            result = await client.start(req, workflow_id=wid)
            return result

    result = run_async(scenario())
    assert result["ok"] is True
    snap = result["snapshot"]
    assert snap["state"] == "completed"
    assert snap["mode"] == C.MODE_CONTROLLED_DETERMINISTIC
    assert len(snap["artifact_refs"]) == 1
    ref = snap["artifact_refs"][0]
    assert set(ref) == set(C.ALLOWED_ARTIFACT_REF_KEYS)
    assert C._SHA256_DIGEST_RE.fullmatch(ref["content_digest"])
    # claim-check only — no raw material anywhere in the durable projection
    assert C.scan_projection_for_leak(snap) is None


def test_duplicate_start_identical_replays_and_divergent_conflicts():
    async def scenario():
        async with p5_worker_env() as env:
            client = runtime_client_for(env)
            req = make_start_request(idempotency="idem_p5_hermetic_0001")
            wid = C.deterministic_workflow_id(req)
            # asyncio.wait_for: StepWorkflow stays open after work completes, so a
            # result-first duplicate reconciliation would hang. Bound every start so
            # a future regression fails fast as a timeout instead of hanging the gate.
            first = await asyncio.wait_for(client.start(req, workflow_id=wid), timeout=30)
            identical = await asyncio.wait_for(client.start(req, workflow_id=wid), timeout=30)
            divergent = await asyncio.wait_for(
                client.start(
                    make_start_request(idempotency="idem_p5_hermetic_0002"), workflow_id=wid
                ),
                timeout=30,
            )
            return first, identical, divergent

    first, identical, divergent = run_async(scenario())
    assert first["ok"] is True
    assert identical["ok"] is True and identical["replayed"] is True
    assert divergent["ok"] is False
    assert divergent["error_code"] == C.RUNTIME_IDEMPOTENCY_CONFLICT


def test_terminal_workflow_duplicate_start_reconciles_without_relaunch():
    # Reviewed gap: with the SDK default ALLOW_DUPLICATE a start against a
    # *terminal/closed* deterministic id would create a brand-new execution. With
    # the REJECT_DUPLICATE / FAIL id policies the real server rejects the duplicate
    # and the runtime client reconciles via the closed snapshot — identical replays,
    # divergent conflicts, and nothing is ever relaunched.
    async def scenario():
        async with p5_worker_env() as env:
            req = make_start_request(idempotency="idem_p5_hermetic_terminal_0001")
            wid = C.deterministic_workflow_id(req)
            first = await asyncio.wait_for(
                runtime_client_for(env).start(req, workflow_id=wid), timeout=30
            )
            # Drive the workflow to a TERMINAL/closed state via cooperative cancel.
            cancel = C.build_update_payload(
                event_key="evt_cancel_terminal_0001", event_type="request_cancel", ref=None
            )
            handle = env.client.get_workflow_handle(wid)
            await handle.execute_update(StepWorkflow.request_cancel, cancel)
            final = await asyncio.wait_for(handle.result(), timeout=30)
            # A fresh client (process restart) starts the SAME terminal id again:
            # identical payload must reconcile/replay, never relaunch.
            replay = await asyncio.wait_for(
                runtime_client_for(env).start(req, workflow_id=wid), timeout=30
            )
            # A divergent same-id start against the terminal run must fail closed.
            divergent = await asyncio.wait_for(
                runtime_client_for(env).start(
                    make_start_request(idempotency="idem_p5_hermetic_terminal_0002"),
                    workflow_id=wid,
                ),
                timeout=30,
            )
            return first, final, replay, divergent

    first, final, replay, divergent = run_async(scenario())
    assert first["ok"] is True
    assert final["state"] == "cancelled"  # the deterministic id is now terminal/closed
    assert replay["ok"] is True
    assert replay["replayed"] is True  # reconciled from the terminal run, not relaunched
    assert divergent["ok"] is False
    assert divergent["error_code"] == C.RUNTIME_IDEMPOTENCY_CONFLICT


def test_recovery_reattaches_by_workflow_id_without_relaunch():
    async def scenario():
        async with p5_worker_env() as env:
            req = make_start_request()
            wid = C.deterministic_workflow_id(req)
            # Original caller starts the workflow.
            started = await runtime_client_for(env).start(req, workflow_id=wid)
            # A *fresh* runtime client (simulating a process restart) reattaches by
            # workflow id and reads the durable snapshot — it must not relaunch.
            recovered = await runtime_client_for(env).recover(workflow_id=wid)
            return started, recovered

    started, recovered = run_async(scenario())
    assert started["ok"] is True
    assert recovered["ok"] is True
    assert recovered["op"] == "recover"
    assert recovered["snapshot"]["run_ref"] == "run_p5_hermetic_0001"
    assert recovered["snapshot"]["state"] in {"completed", "running"}


def test_active_run_cancellation_watch_preserved():
    async def scenario():
        async with p5_worker_env() as env:
            executor = P5TemporalStepExecutor(
                control_surface=control_surface_for(env),
                enabled=True,
                approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
            )
            req = make_start_request()
            wid = C.deterministic_workflow_id(req)
            await runtime_client_for(env).start(req, workflow_id=wid)
            # Unconfirmed cancel of an active run must preserve the WATCH.
            watch = await executor.acancel(
                run_id="run_p5_hermetic_0001",
                step_id="architect",
                scope="active_run",
                idempotency_key="idem_cancel_0001",
                interrupt_outcome=None,
            )
            return watch

    watch = run_async(scenario())
    assert isinstance(watch, StepExecutionOutcome)
    assert watch.ok is False
    assert watch.step_status == "cancel_ambiguous"
    assert watch.ambiguous is True
    assert watch.error_code == C.ACTIVE_RUN_CANCELLATION_WATCH
