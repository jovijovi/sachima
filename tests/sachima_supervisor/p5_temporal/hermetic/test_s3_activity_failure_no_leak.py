"""S3 Activity failure semantics: non-retryable stable codes, no history leak.

Regression coverage for the S3 Activity body under a real hermetic-local
Temporal Worker. The body is registered under the same ``p5_step_activity`` name
that ``StepWorkflow`` schedules, but remains default-off, so it must fail once
with a non-retryable stable code, call no S2 seam body, and keep SCAN 1 / SCAN 2
clean.
"""

from __future__ import annotations

import asyncio

import temporalio.api.history.v1
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.s2_supervisor_adapter import (
    S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN,
    S2LocalOfflineSupervisorAdapter,
)
from sachima_supervisor.p5_temporal.s3_activity_controller import S3SupervisorActivityBody
from sachima_supervisor.p5_temporal.workflow import StepWorkflow
from tests.sachima_supervisor.p5_temporal.hermetic._harness import passthrough_runner, run_async

TASK_QUEUE = "s3_activity_failure_no_leak_queue"


class _CountingSeam:
    def __init__(self) -> None:
        self.calls = 0

    def run_step(self, activity_input):  # pragma: no cover - default-off must prevent this call
        self.calls += 1
        raise AssertionError("default-off S3 body must not call the S2 seam")


def _stable_cause(exc: BaseException) -> ApplicationError | None:
    cause = exc.__cause__
    while cause is not None:
        if isinstance(cause, ApplicationError):
            return cause
        cause = cause.__cause__
    return None


def _failed_activity_count(history) -> int:
    return sum(1 for event in history.events if event.HasField("activity_task_failed_event_attributes"))


def test_s3_default_off_activity_failure_is_non_retryable_and_history_clean():
    async def scenario():
        env = await WorkflowEnvironment.start_time_skipping()
        seam = _CountingSeam()
        adapter = S2LocalOfflineSupervisorAdapter(
            seam=seam,
            enabled=True,
            approval_token=S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN,
        )
        body = S3SupervisorActivityBody(adapter=adapter, enabled=False, approval_token="")
        try:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[StepWorkflow],
                activities=[body.run],
                workflow_runner=passthrough_runner(),
            ):
                req = C.build_start_request(
                    run_ref="run_s3_activity_failure_0001",
                    workflow_ref="tx_s3_activity_failure_0001",
                    step_ref="architect",
                    attempt_index=1,
                    role_keys=("sachima_claude_read_only_reviewer",),
                    input_claim_refs=(
                        {
                            "ref": "claim_ref_input_0",
                            "digest": "sha256:" + "a" * 64,
                            "kind": "input",
                            "byte_count": 64,
                        },
                    ),
                    idempotency_material="idem_s3_activity_failure_0001",
                )
                wid = C.deterministic_workflow_id(req)
                handle = await env.client.start_workflow(StepWorkflow.run, req, id=wid, task_queue=TASK_QUEUE)
                try:
                    await asyncio.wait_for(handle.result(), timeout=5)
                except WorkflowFailureError as exc:
                    app_error = _stable_cause(exc)
                else:  # pragma: no cover - failure is required
                    raise AssertionError("default-off S3 Activity unexpectedly succeeded")
                history = await handle.fetch_history()
                raw = temporalio.api.history.v1.History(events=history.events).SerializeToString()
                return seam.calls, app_error, history, raw, history.to_json_dict()
        finally:
            await env.shutdown()

    seam_calls, app_error, history, raw_history, history_json = run_async(scenario())

    assert seam_calls == 0
    assert app_error is not None
    assert app_error.type == C.RUNTIME_DISABLED
    assert app_error.non_retryable is True
    assert _failed_activity_count(history) == 1
    assert C.scan_bytes_for_leak(raw_history) is None
    assert C.scan_projection_for_leak(history_json) is None
    assert "Traceback" not in str(history_json)
