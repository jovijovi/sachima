"""T4 determinism replay gate (FR3/FR8, Gate C/H, merge-blocking).

Re-runs a recorded ``StepWorkflow`` history through ``temporalio.worker.Replayer``.
Any non-determinism in workflow code (wall-clock, randomness, ordering, hidden
I/O) raises during replay and blocks merge. The workflow is driven to a terminal
state first so the recorded history is complete.
"""

from __future__ import annotations

from temporalio.worker import Replayer

from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.workflow import StepWorkflow

from tests.sachima_supervisor.p5_temporal.hermetic._harness import (
    TASK_QUEUE,
    make_start_request,
    p5_worker_env,
    passthrough_runner,
    run_async,
)


def test_recorded_history_replays_deterministically():
    async def scenario():
        async with p5_worker_env() as env:
            req = make_start_request()
            wid = C.deterministic_workflow_id(req)
            handle = await env.client.start_workflow(
                StepWorkflow.run, req, id=wid, task_queue=TASK_QUEUE
            )
            # Exercise an update, then terminalize so the history is complete.
            await handle.execute_update(
                StepWorkflow.resume,
                C.build_update_payload(event_key="evt_resume_0001", event_type="resume", ref="claim_ref_resume_0"),
            )
            await handle.execute_update(
                StepWorkflow.request_cancel,
                C.build_update_payload(event_key="evt_cancel_0001", event_type="request_cancel", ref=None),
            )
            await handle.result()
            return await handle.fetch_history()

    history = run_async(scenario())

    # Replay the recorded history with the same sandbox passthrough runner the ops
    # Worker uses; a NondeterminismError here would fail the merge gate.
    replayer = Replayer(workflows=[StepWorkflow], workflow_runner=passthrough_runner())
    run_async(replayer.replay_workflow(history))
