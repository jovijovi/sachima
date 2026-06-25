"""T4 hermetic workflow semantics (FR3, Gate C).

Real-Worker proof of the deterministic ``StepWorkflow``: sanitized query
snapshot, the pinned Slice 1 update set ``{resume, request_cancel}`` with
event-key idempotency (duplicate → no-op), cooperative cancel terminalization,
and that delivery / approval / rejection updates are absent (deferred).
"""

from __future__ import annotations

from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.workflow import StepWorkflow

from tests.sachima_supervisor.p5_temporal.hermetic._harness import (
    TASK_QUEUE,
    make_start_request,
    p5_worker_env,
    run_async,
)


def test_query_snapshot_and_pinned_updates():
    async def scenario():
        async with p5_worker_env() as env:
            req = make_start_request()
            wid = C.deterministic_workflow_id(req)
            handle = await env.client.start_workflow(
                StepWorkflow.run, req, id=wid, task_queue=TASK_QUEUE
            )

            resume = C.build_update_payload(event_key="evt_resume_0001", event_type="resume", ref="claim_ref_resume_0")
            applied = await handle.execute_update(StepWorkflow.resume, resume)
            duplicate = await handle.execute_update(StepWorkflow.resume, resume)  # idempotent no-op
            snap = await handle.query(StepWorkflow.snapshot)

            cancel = C.build_update_payload(event_key="evt_cancel_0001", event_type="request_cancel", ref=None)
            cancelled = await handle.execute_update(StepWorkflow.request_cancel, cancel)
            final = await handle.result()
            return applied, duplicate, snap, cancelled, final

    applied, duplicate, snap, cancelled, final = run_async(scenario())

    assert applied["update_status"] == "applied"
    assert duplicate["update_status"] == "duplicate"
    assert snap["resume_count"] == 1  # duplicate did not double-count
    assert snap["state"] == "completed"
    assert C.scan_projection_for_leak(snap) is None

    assert cancelled["update_status"] == "applied"
    assert cancelled["snapshot"]["active_run_watch"] is True
    assert final["state"] == "cancelled"
    assert C.scan_projection_for_leak(final) is None


def test_deferred_updates_absent_from_workflow():
    # Slice 1 pins {resume, request_cancel}; delivery/approval/rejection are deferred.
    update_names = {
        name
        for name in dir(StepWorkflow)
        if not name.startswith("_")
    }
    assert "resume" in update_names
    assert "request_cancel" in update_names
    for deferred in ("deliver", "delivery", "approve", "approve_intent", "reject", "reject_intent"):
        assert deferred not in update_names, deferred
