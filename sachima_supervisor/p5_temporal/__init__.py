"""First-class P5 Temporal PR B runtime package (Slice 1).

Promotes the proven FlowWeaver Temporal prototypes into governed
``sachima_supervisor`` modules that attach the WP4 controlled AI FLOW
``StepExecutor`` seam to a real Temporal durable backend under a hermetic-local
merge gate — default-off, controlled-deterministic step body, ops-owned Worker,
caller-supplied Temporal client, and production traffic / P6 real agent execution
separately gated.

Import discipline:

* The token, the sanitized ``contracts`` trust boundary, and the
  ``P5TemporalStepExecutor`` admission surface import **no** ``temporalio`` — they
  are pure local/offline Python and always importable.
* The ``temporalio``-dependent surfaces (runtime client, control surface,
  workflow, activities, ops-owned Worker) are resolved lazily via ``__getattr__``
  so a clean import of this package never transitively starts a Temporal service,
  Worker, or socket, and so non-runtime callers never pay the dependency.
"""

from __future__ import annotations

from typing import Any

from . import contracts
from .contracts import (
    P5_TEMPORAL_TASK_QUEUE,
    StartRequest,
    UpdatePayload,
)
from .step_executor import (
    P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    P5TemporalStepExecutor,
)

# Lazily-resolved, temporalio-dependent public names → (module, attribute).
_LAZY_EXPORTS = {
    "P5TemporalRuntimeClient": ("runtime_client", "P5TemporalRuntimeClient"),
    "P5TemporalControlSurface": ("control_surface", "P5TemporalControlSurface"),
    "StepWorkflow": ("workflow", "StepWorkflow"),
    "p5_step_activity": ("activities", "p5_step_activity"),
    "P5_TEMPORAL_ACTIVITIES": ("activities", "P5_TEMPORAL_ACTIVITIES"),
    "build_p5_temporal_worker": ("p5_temporal_worker", "build_p5_temporal_worker"),
    "run_p5_temporal_worker": ("p5_temporal_worker", "run_p5_temporal_worker"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    import importlib

    module = importlib.import_module(f".{module_name}", __name__)
    return getattr(module, attribute)


__all__ = [
    "contracts",
    "P5_TEMPORAL_TASK_QUEUE",
    "P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN",
    "P5TemporalStepExecutor",
    "P5TemporalRuntimeClient",
    "P5TemporalControlSurface",
    "StepWorkflow",
    "p5_step_activity",
    "P5_TEMPORAL_ACTIVITIES",
    "build_p5_temporal_worker",
    "run_p5_temporal_worker",
    "StartRequest",
    "UpdatePayload",
]
