"""Runtime Spine — one-call ``arsd`` execution binding bundle.

:func:`bind_arsd_execution` is the composition root for the Sachima ↔ ARS
Socket API v3 integration: from one validated, explicitly enabled
:class:`~.arsd_socket_contract.ArsdSupervisorConfig` it assembles the whole
seam —

```text
TaskRegistry (single seq authority)
  + an allowlisted SupervisorTurnBackend (the arsd adapter)
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
compose (``require_enabled_arsd_supervisor_config`` runs before any client is
built, and the backend constructor is the second gate); a composed bundle
without an explicit activation ``gate`` keeps the query/display chain
fail-closed with ``runtime_live_progress_query_disabled``; and without an
injected ``payload_resolver`` the dispatcher refuses every dispatch — a
display-only composition can never be driven into running turns, so **composing
this bundle submits no Run**.

The retired ``library`` composition this module used to offer is gone (plan
P5-a/S-1): there is exactly one migration seam,
:func:`~.agent_run_supervisor_library_backend.library_backend_retired`, and no
path here falls back to it, to a CLI, or to another API version.

Importing this module starts no process, socket, Gateway, Feishu, IM, or
Temporal surface and performs no ``agent_run_supervisor`` import — the official
client is reached lazily inside the facade, and only when a daemon operation is
actually made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .agent_run_supervisor_port import AgentRunSupervisorPort
from .agent_run_supervisor_turn_dispatcher import AgentRunSupervisorTurnDispatcher
from .arsd_run_binding_ledger import ArsdRunBindingLedger
from .arsd_socket_contract import (
    ArsdSupervisorConfig,
    DefaultArsdClientFacade,
    require_enabled_arsd_supervisor_config,
)
from .arsd_supervisor_backend import ArsdLiveProgressReader, ArsdSupervisorBackend
from .events import SpineError
from .execution_port import RUNTIME_INVALID_SESSION
from .live_progress_display import LiveProgressDisplayService
from .live_progress_projection import LiveProgressReader
from .live_progress_query import (
    LiveProgressQueryActivationGate,
    LiveProgressQueryService,
)
from .live_progress_sources import LiveProgressSourceBindings
from .registry import TaskRegistry
from .supervisor_turn_backend import (
    SupervisorTurnBackend,
    validate_supervisor_turn_backend,
)


@dataclass(frozen=True)
class AgentRunSupervisorExecutionBinding:
    """The composed seam: one shared spine per enabled config.

    Frozen so a composed bundle cannot be partially rewired; construction
    re-checks every element so a forged bundle fails closed. The backend is
    named only by the neutral contract here — it is admitted by the exact-type
    factory allowlist, never by a concrete-class check.

    Construction checks **object identity**, not just types. A bundle whose
    parts each have the right type but come from two different spines is the
    dangerous one: its dispatcher would guard one task operation lock while its
    backend guarded another, which is exactly the graph where a cancel can land
    between a durable acceptance and its canonical publication. There is no
    supported way to assemble that graph — every part must be the same object
    as every other part's view of it, and the whole graph must share one task
    operation lock provider.

    The read chain is checked the same way, and for the same kind of reason. A
    query service pointed at another spine's bindings, registry, or port
    answers about a different conversation — reading a Run this task never
    dispatched, or missing the one it did — and a display service wrapping
    another bundle's query service renders that answer. Both type-check
    perfectly, so both are checked by identity.
    """

    registry: TaskRegistry
    backend: SupervisorTurnBackend
    port: AgentRunSupervisorPort
    bindings: LiveProgressSourceBindings
    dispatcher: AgentRunSupervisorTurnDispatcher
    query_service: LiveProgressQueryService
    display_service: LiveProgressDisplayService
    #: The durable binding ledger this graph classifies against. Published on
    #: the bundle so a coordinator reads the backend's **own** ledger object
    #: rather than constructing a second one over the same path: two instances
    #: agree about the bytes but not about the lock, and a classification that
    #: races a finalize on a different lock is exactly the two-read window the
    #: exact snapshot exists to close.
    ledger: ArsdRunBindingLedger | None = None

    def __post_init__(self) -> None:
        try:
            validate_supervisor_turn_backend(self.backend)
        except SpineError:
            raise SpineError(RUNTIME_INVALID_SESSION) from None
        checks = (
            (self.registry, TaskRegistry),
            (self.port, AgentRunSupervisorPort),
            (self.bindings, LiveProgressSourceBindings),
            (self.dispatcher, AgentRunSupervisorTurnDispatcher),
            (self.query_service, LiveProgressQueryService),
            (self.display_service, LiveProgressDisplayService),
        )
        for value, expected in checks:
            if type(value) is not expected:
                raise SpineError(RUNTIME_INVALID_SESSION)

        # One graph, by identity. Each pair is a way a bundle could be
        # assembled from two spines while every type still checks out.
        identities = (
            (self.dispatcher.backend, self.backend),
            (self.dispatcher.port, self.port),
            (self.dispatcher.registry, self.registry),
            (self.dispatcher.bindings, self.bindings),
            (self.port._backend, self.backend),
            (self.port._registry, self.registry),
            # The invariant this is all for: admission and publication guard
            # the same section, so a cancel cannot land between them.
            (self.dispatcher.task_locks, self.backend.task_locks),
            # The read chain reads THIS spine: the same bindings the dispatcher
            # publishes into, the same registry that is the seq authority, and
            # the same port that owns the sessions being asked about.
            (self.query_service.bindings, self.bindings),
            (self.query_service.registry, self.registry),
            (self.query_service.port, self.port),
            (self.display_service.query_service, self.query_service),
        )
        for actual, expected_object in identities:
            if actual is not expected_object:
                raise SpineError(RUNTIME_INVALID_SESSION)

        if self.ledger is not None:
            if type(self.ledger) is not ArsdRunBindingLedger:
                raise SpineError(RUNTIME_INVALID_SESSION)
            # One ledger object for the whole graph, by identity — the same
            # rule, and the same reason, as the task operation lock above.
            if getattr(self.backend, "_ledger", None) is not self.ledger:
                raise SpineError(RUNTIME_INVALID_SESSION)


def prompt_resolver_from_payload_resolver(
    payload_resolver: Callable[[str], str],
) -> Callable[[Any], str]:
    """Adapt a host's claim-check payload resolver into a prompt resolver.

    A pending intent persists the dispatch's ``prompt_ref`` and never the
    prompt text, so an explicit recovery rebuilds the frozen payload by
    resolving that ref back through the **same** resolver the dispatch used.
    Without this adapter a composed host writes recoverable intents it cannot
    actually recover — the ref is on disk and nothing can turn it back into a
    prompt.
    """

    def _resolve(resolver_refs: Any) -> str:
        return payload_resolver(resolver_refs["prompt_ref"])

    return _resolve


def bind_arsd_execution(
    config: ArsdSupervisorConfig,
    *,
    gate: LiveProgressQueryActivationGate | None = None,
    payload_resolver: Callable[[str], str] | None = None,
    facade: Any | None = None,
    ledger: Any | None = None,
    prompt_resolver: Callable[[Any], str] | None = None,
    progress_reader: LiveProgressReader | None = None,
    registry: TaskRegistry | None = None,
    bindings: LiveProgressSourceBindings | None = None,
    executor: Any | None = None,
) -> AgentRunSupervisorExecutionBinding:
    """Compose the ``arsd`` execution seam from one enabled config, or fail closed.

    ``gate=None`` (the default) leaves the query/display chain default-off;
    pass an explicit LS4-A gate (e.g. ``hermes_internal_query_gate()``) to
    activate the approved internal surface. ``payload_resolver=None`` leaves
    the dispatcher fail-closed (display-only posture), so composing a bundle
    never submits a Run.

    ``registry`` / ``bindings`` let a host hand in the spine state it already
    holds instead of having a second, empty one invented beside it. That is
    what makes a **recomposition** reconcilable: the durable ledger and the
    host's own task/session state meet in one bundle, and
    ``dispatcher.rehydrate_source_binding()`` can turn an accepted Run into a
    readable source without submitting anything. Nothing is fabricated — a
    task neither side knows stays unknown.

    ``executor`` lets a host run each whole turn operation on its own worker.
    The task operation lock is acquired inside that worker, never across the
    hand-off, so a real thread pool is safe here.

    ``facade`` / ``ledger`` / ``prompt_resolver`` / ``progress_reader`` are
    deterministic-test injection seams; the defaults reach the daemon through
    the official client lazily and never at compose time beyond the one
    contract negotiation the backend constructor performs. A ``prompt_resolver``
    is derived from ``payload_resolver`` when one is not given, so the
    recovery path resolves prompts exactly the way the dispatch path does.

    The composed graph shares one task operation lock provider by construction:
    the dispatcher derives it from the backend, and the bundle re-checks that
    identity. There is no argument here that could split it.
    """

    enabled = require_enabled_arsd_supervisor_config(config)
    client = facade if facade is not None else DefaultArsdClientFacade(enabled)
    bindings_ledger = (
        ledger if ledger is not None else ArsdRunBindingLedger(enabled.binding_ledger_path)
    )
    if prompt_resolver is None and payload_resolver is not None:
        prompt_resolver = prompt_resolver_from_payload_resolver(payload_resolver)
    backend = ArsdSupervisorBackend(
        enabled, client, bindings_ledger, prompt_resolver=prompt_resolver
    )
    task_registry = registry if registry is not None else TaskRegistry()
    port = AgentRunSupervisorPort(task_registry, backend)
    source_bindings = bindings if bindings is not None else LiveProgressSourceBindings()
    # The dispatcher derives the shared section from the backend, so admitting
    # a Run and publishing it are one task operation by construction rather
    # than by a caller remembering to pass the same object twice.
    dispatcher = AgentRunSupervisorTurnDispatcher(
        port,
        backend,
        source_bindings,
        task_registry,
        payload_resolver,
        executor=executor,
    )
    reader: LiveProgressReader = (
        progress_reader if progress_reader is not None else ArsdLiveProgressReader(client)
    )
    query_service = LiveProgressQueryService(
        source_bindings, task_registry, port, reader, gate=gate
    )
    display_service = LiveProgressDisplayService(query_service=query_service)
    return AgentRunSupervisorExecutionBinding(
        registry=task_registry,
        backend=backend,
        port=port,
        bindings=source_bindings,
        dispatcher=dispatcher,
        query_service=query_service,
        display_service=display_service,
        ledger=bindings_ledger if type(bindings_ledger) is ArsdRunBindingLedger else None,
    )


__all__ = [
    "AgentRunSupervisorExecutionBinding",
    "bind_arsd_execution",
    "prompt_resolver_from_payload_resolver",
]
