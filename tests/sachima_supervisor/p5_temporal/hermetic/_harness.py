"""Hermetic-local Temporal harness (T9, FR8, Gate H).

Binds the merge-blocking probes to a **real** Temporal Worker running inside a
hermetic ``WorkflowEnvironment.start_time_skipping()`` test server under an
isolated namespace — no production / staging cluster dependency. The same
``P5TemporalRuntimeClient`` / ``P5TemporalControlSurface`` / ``P5TemporalStepExecutor``
that ship in PR B run here against the real Worker.

Tests are written as synchronous functions that drive an async scenario via
``run_async`` so they never depend on a particular pytest-asyncio mode.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from temporalio.testing import WorkflowEnvironment
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.control_surface import P5TemporalControlSurface
from sachima_supervisor.p5_temporal.p5_temporal_worker import build_p5_temporal_worker
from sachima_supervisor.p5_temporal.runtime_client import P5TemporalRuntimeClient

TASK_QUEUE = C.P5_TEMPORAL_TASK_QUEUE


def run_async(coro: Any) -> Any:
    return asyncio.run(coro)


def passthrough_runner() -> SandboxedWorkflowRunner:
    """Sandbox runner matching the ops Worker (for the determinism Replayer)."""

    return SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions.default.with_passthrough_modules("sachima_supervisor")
    )


@asynccontextmanager
async def p5_worker_env():
    """Start a hermetic time-skipping env with the real ops-owned P5 Worker."""

    env = await WorkflowEnvironment.start_time_skipping()
    try:
        async with build_p5_temporal_worker(env.client, task_queue=TASK_QUEUE):
            yield env
    finally:
        await env.shutdown()


def runtime_client_for(env: Any) -> P5TemporalRuntimeClient:
    """Wrap the hermetic env's caller-supplied client (no lifecycle ownership)."""

    return P5TemporalRuntimeClient(env.client, task_queue=TASK_QUEUE)


def control_surface_for(env: Any) -> P5TemporalControlSurface:
    return P5TemporalControlSurface(runtime_client_for(env))


def make_start_request(
    *,
    run_ref: str = "run_p5_hermetic_0001",
    step_ref: str = "architect",
    idempotency: str = "idem_p5_hermetic_0001",
    attempt_index: int = 1,
    canary_free: bool = True,
) -> C.StartRequest:
    return C.build_start_request(
        run_ref=run_ref,
        workflow_ref="tx_p5_hermetic_0001",
        step_ref=step_ref,
        attempt_index=attempt_index,
        role_keys=("sachima_claude_read_only_reviewer",),
        input_claim_refs=(
            {"ref": "claim_ref_input_0", "digest": "sha256:" + "a" * 64, "kind": "input", "byte_count": 64},
        ),
        idempotency_material=idempotency,
    )


__all__ = [
    "TASK_QUEUE",
    "run_async",
    "passthrough_runner",
    "p5_worker_env",
    "runtime_client_for",
    "control_surface_for",
    "make_start_request",
]
