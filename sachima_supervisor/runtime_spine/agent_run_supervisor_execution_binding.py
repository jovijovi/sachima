"""ARS-INT Runtime Spine — one-call formal execution binding bundle.

:func:`bind_agent_run_supervisor_execution` is the composition root for the
formal Sachima ↔ agent-run-supervisor integration: from one validated,
explicitly enabled :class:`AgentRunSupervisorLibraryConfig` it assembles the
whole seam —

```text
TaskRegistry (single seq authority)
  + AgentRunSupervisorLibraryBackend (real library, injected-facade seam)
  + AgentRunSupervisorPort (existing ExecutionPort adapter, unchanged)
  + AgentRunSupervisorTurnDispatcher (single-flight goal/prompt turns,
        auto LiveProgressSourceBindings registration per turn)
  + LiveProgressQueryService (LS4-A default-off activation gate)
  + LiveProgressDisplayService (closed-template rendering)
```

— sharing one registry / one bindings store, so dispatcher-created source
bindings feed the display chain directly and no hand-written bindings file or
copy script is needed.

Default-off is layered, not assumed: a disabled/forged config refuses to
compose (the backend constructor is the gate); a composed bundle without an
explicit activation ``gate`` keeps the query/display chain fail-closed with
``runtime_live_progress_query_disabled``; and without an injected
``payload_resolver`` the dispatcher refuses every dispatch — a display-only
composition can never be driven into running turns.

Importing and calling this module starts no process, socket, Gateway, Feishu,
IM, or Temporal surface, performs no ``agent_run_supervisor`` import (the
library is reached lazily through the backend facade), and enables nothing
live or default-on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .agent_run_supervisor_library_backend import (
    AgentRunSupervisorLibraryBackend,
    AgentRunSupervisorLibraryConfig,
)
from .agent_run_supervisor_port import AgentRunSupervisorPort
from .agent_run_supervisor_turn_dispatcher import AgentRunSupervisorTurnDispatcher
from .events import SpineError
from .execution_port import RUNTIME_INVALID_SESSION
from .live_progress_display import LiveProgressDisplayService
from .live_progress_projection import DefaultLiveProgressReader, LiveProgressReader
from .live_progress_query import (
    LiveProgressQueryActivationGate,
    LiveProgressQueryService,
)
from .live_progress_sources import LiveProgressSourceBindings
from .registry import TaskRegistry


@dataclass(frozen=True)
class AgentRunSupervisorExecutionBinding:
    """The composed formal seam: one shared spine per enabled config.

    Frozen so a composed bundle cannot be partially rewired; construction
    re-checks the concrete types so a forged bundle fails closed.
    """

    registry: TaskRegistry
    backend: AgentRunSupervisorLibraryBackend
    port: AgentRunSupervisorPort
    bindings: LiveProgressSourceBindings
    dispatcher: AgentRunSupervisorTurnDispatcher
    query_service: LiveProgressQueryService
    display_service: LiveProgressDisplayService

    def __post_init__(self) -> None:
        checks = (
            (self.registry, TaskRegistry),
            (self.backend, AgentRunSupervisorLibraryBackend),
            (self.port, AgentRunSupervisorPort),
            (self.bindings, LiveProgressSourceBindings),
            (self.dispatcher, AgentRunSupervisorTurnDispatcher),
            (self.query_service, LiveProgressQueryService),
            (self.display_service, LiveProgressDisplayService),
        )
        for value, expected in checks:
            if type(value) is not expected:
                raise SpineError(RUNTIME_INVALID_SESSION)


def bind_agent_run_supervisor_execution(
    config: AgentRunSupervisorLibraryConfig,
    *,
    gate: LiveProgressQueryActivationGate | None = None,
    payload_resolver: Callable[[str], str] | None = None,
    facade: Any | None = None,
    progress_reader: LiveProgressReader | None = None,
) -> AgentRunSupervisorExecutionBinding:
    """Compose the formal execution seam from one enabled config, or fail closed.

    ``gate=None`` (the default) leaves the query/display chain default-off;
    pass an explicit LS4-A gate (e.g. ``hermes_internal_query_gate()``) to
    activate the approved internal surface. ``payload_resolver=None`` leaves
    the dispatcher fail-closed (display-only posture). ``facade`` /
    ``progress_reader`` are deterministic-test injection seams; the defaults
    reach the pinned library lazily and never at compose time.
    """

    backend = AgentRunSupervisorLibraryBackend(config, facade=facade)
    registry = TaskRegistry()
    port = AgentRunSupervisorPort(registry, backend)
    bindings = LiveProgressSourceBindings()
    dispatcher = AgentRunSupervisorTurnDispatcher(
        port, backend, bindings, registry, payload_resolver
    )
    reader: LiveProgressReader = (
        progress_reader if progress_reader is not None else DefaultLiveProgressReader()
    )
    query_service = LiveProgressQueryService(bindings, registry, port, reader, gate=gate)
    display_service = LiveProgressDisplayService(query_service=query_service)
    return AgentRunSupervisorExecutionBinding(
        registry=registry,
        backend=backend,
        port=port,
        bindings=bindings,
        dispatcher=dispatcher,
        query_service=query_service,
        display_service=display_service,
    )


__all__ = [
    "AgentRunSupervisorExecutionBinding",
    "bind_agent_run_supervisor_execution",
]
