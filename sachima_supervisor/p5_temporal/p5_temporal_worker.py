"""Ops-owned P5 Temporal Worker builder / launcher (FR6, Gate F).

This module defines the **ops-owned** Worker lifecycle for the hermetic-local
merge gate and the `sachima-p5-staging` namespace. It is deliberately isolated:

* It MUST NOT be imported, instantiated, started, stopped, scaled, drained, or
  held by Gateway code, inbound-message paths, platform adapters, or Feishu code.
  A static boundary test (``test_gateway_boundary.py``) fails the build on any
  such reference.
* It owns **no** connection lifecycle: the caller (ops) supplies an already
  connected ``temporalio.client.Client``; this module never calls
  ``Client.connect(...)``, never starts a server / subprocess / socket / Docker /
  systemd unit, and never reaches a Gateway request path.

The Worker runs the deterministic ``StepWorkflow`` and the controlled-deterministic
``p5_step_activity`` only — no real ``acpx``/agent execution.
"""

from __future__ import annotations

from typing import Any

from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from . import contracts as C
from .activities import P5_TEMPORAL_ACTIVITIES
from .workflow import StepWorkflow

#: The sandbox transitively imports the heavy ``sachima_supervisor`` package
#: ``__init__`` (which touches the filesystem at import time). ``StepWorkflow`` and
#: ``contracts`` are trusted, deterministic first-party code, so the first-party
#: package is passed through the sandbox (the determinism replay gate still
#: independently blocks any non-determinism). This is the Temporal-recommended
#: pattern for trusted modules and keeps workflow code import-clean.
_PASSTHROUGH_RUNNER = SandboxedWorkflowRunner(
    restrictions=SandboxRestrictions.default.with_passthrough_modules("sachima_supervisor")
)

#: Sanitized, constant Worker identity (FR2: no PIDs / thread ids / host names in
#: Temporal history). Temporal otherwise defaults the Worker identity to
#: ``<pid>@<hostname>``. Ops should likewise connect the caller-supplied client
#: with a sanitized ``identity`` (see the staging runbook) so starter-side events
#: carry no host/pid either.
P5_TEMPORAL_WORKER_IDENTITY = "sachima-p5-temporal-worker"


def build_p5_temporal_worker(
    client: Any,
    *,
    task_queue: str = C.P5_TEMPORAL_TASK_QUEUE,
    identity: str = P5_TEMPORAL_WORKER_IDENTITY,
    **worker_kwargs: Any,
) -> Worker:
    """Build (do not start) an ops-owned Worker over a caller-supplied client.

    ``client`` is an already-connected ``temporalio.client.Client`` supplied by
    ops. No connection, server, or subprocess lifecycle is created here. The
    Worker identity is sanitized to a constant so history carries no host/pid.
    """

    if client is None:
        raise C.ContractError(C.RUNTIME_PRECONDITION_UNMET)
    worker_kwargs.setdefault("workflow_runner", _PASSTHROUGH_RUNNER)
    worker_kwargs.setdefault("identity", identity)
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[StepWorkflow],
        activities=list(P5_TEMPORAL_ACTIVITIES),
        **worker_kwargs,
    )


async def run_p5_temporal_worker(
    client: Any,
    *,
    task_queue: str = C.P5_TEMPORAL_TASK_QUEUE,
    **worker_kwargs: Any,
) -> None:
    """Run an ops-owned Worker until cancelled (ops / staging entry point).

    Intended for an ops-owned process only. Never call this from Gateway,
    inbound-message, platform-adapter, or Feishu code paths.

    ``Worker.run()`` is the SDK's single "run until shut down" entry point: it
    returns only when the worker is shut down (e.g. by cancelling this coroutine).
    The ``async with worker:`` context manager is just a wrapper that *also* calls
    ``run()`` in a background task, so combining the two would start the worker
    twice ("Already started"); we use ``run()`` alone.
    """

    worker = build_p5_temporal_worker(client, task_queue=task_queue, **worker_kwargs)
    await worker.run()


__all__ = ["build_p5_temporal_worker", "run_p5_temporal_worker", "P5_TEMPORAL_WORKER_IDENTITY"]
