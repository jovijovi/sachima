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
from .s2_supervisor_adapter import (
    S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN,
    ActivitySeamOutcome,
    FakeDeterministicSupervisorSeam,
    S2LocalOfflineSupervisorAdapter,
    SupervisorSeam,
    SupervisorStepResult,
)

# Lazily-resolved, temporalio-dependent public names → (module, attribute).
_LAZY_EXPORTS = {
    "S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN": ("s3_activity_controller", "S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN"),
    "INTENT_CLASS_TO_ROLE_KEY": ("s3_activity_controller", "INTENT_CLASS_TO_ROLE_KEY"),
    "S3SupervisorActivityBody": ("s3_activity_controller", "S3SupervisorActivityBody"),
    "S3TemporalActivityController": ("s3_activity_controller", "S3TemporalActivityController"),
    "S4_READ_ONLY_REAL_AGENT_STEP_APPROVAL_TOKEN": (
        "s4_read_only_real_agent_step",
        "S4_READ_ONLY_REAL_AGENT_STEP_APPROVAL_TOKEN",
    ),
    "S4_HISTORY_SAFE_ROLE_TO_CONTROLLED_EXEC_ROLE": (
        "s4_read_only_real_agent_step",
        "S4_HISTORY_SAFE_ROLE_TO_CONTROLLED_EXEC_ROLE",
    ),
    "S4ReadOnlyRealAgentSupervisorSeam": ("s4_read_only_real_agent_step", "S4ReadOnlyRealAgentSupervisorSeam"),
    "s4_activity_failure_for_code": ("s4_read_only_real_agent_step", "s4_activity_failure_for_code"),
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
    "S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN",
    "S2LocalOfflineSupervisorAdapter",
    "SupervisorSeam",
    "SupervisorStepResult",
    "ActivitySeamOutcome",
    "FakeDeterministicSupervisorSeam",
    "S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN",
    "INTENT_CLASS_TO_ROLE_KEY",
    "S3SupervisorActivityBody",
    "S3TemporalActivityController",
    "S4_READ_ONLY_REAL_AGENT_STEP_APPROVAL_TOKEN",
    "S4_HISTORY_SAFE_ROLE_TO_CONTROLLED_EXEC_ROLE",
    "S4ReadOnlyRealAgentSupervisorSeam",
    "s4_activity_failure_for_code",
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
