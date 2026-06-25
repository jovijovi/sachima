"""P6-A hermetic-local harness (merge-blocking gate).

Reuses the **ops-owned** P5 Temporal hermetic harness — a real Worker inside
``WorkflowEnvironment.start_time_skipping()`` under an isolated namespace, no
production / staging cluster — and wires it into a P6-A composition session via
the existing ``P5TemporalStepExecutor`` seam. The controlled-deterministic step
body is unchanged; P6-A only composes WP4 + the Temporal executor here.

The WP4 orchestrator is synchronous, so the P6 session is driven on a worker
thread (``asyncio.to_thread``) while the real Temporal Worker keeps running on the
env's event loop; the executor's own sync->async bridge then drives the durable
backend without blocking the Worker loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sachima_supervisor.ai_flow_store import AiFlowRunStore
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.step_executor import (
    P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    P5TemporalStepExecutor,
)
from sachima_supervisor.p6_controlled_ai_flow import (
    P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
    P6ControlledAiFlowSession,
)

from tests.sachima_supervisor.p5_temporal.hermetic._harness import (
    control_surface_for,
    p5_worker_env,
    run_async,
    runtime_client_for,
)
from tests.sachima_supervisor.p6_controlled_ai_flow._support import SPEC


def temporal_executor(env: Any) -> P5TemporalStepExecutor:
    return P5TemporalStepExecutor(
        control_surface=control_surface_for(env),
        enabled=True,
        approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    )


def temporal_session(
    env: Any, *, executor: Any = None, store: Any = None
) -> tuple[P6ControlledAiFlowSession, P5TemporalStepExecutor]:
    executor = executor if executor is not None else temporal_executor(env)
    session = P6ControlledAiFlowSession(
        spec=SPEC,
        store=store if store is not None else AiFlowRunStore(),
        executor=executor,
        enabled=True,
        approval_token=P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
        operator_gate=True,
    )
    return session, executor


def architect_workflow_id() -> str:
    """Deterministic durable workflow id for the canonical architect step."""

    return C.workflow_id_from_refs(C.safe_ref("run_p6_alpha"), C.safe_ref("architect"))


async def in_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous P6 call off the Worker's event loop."""

    return await asyncio.to_thread(lambda: func(*args, **kwargs))


__all__ = [
    "temporal_executor",
    "temporal_session",
    "architect_workflow_id",
    "in_thread",
    "control_surface_for",
    "p5_worker_env",
    "run_async",
    "runtime_client_for",
]
