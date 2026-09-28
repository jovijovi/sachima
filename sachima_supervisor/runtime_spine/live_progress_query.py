"""PR-LS4-A Runtime Spine — default-off local/offline live-progress query gate.

This module is the **controlled query entrypoint** over the PR-LS2
``LiveProgressSourceBindings`` + PR-LS1 ``AgentRunSupervisorLiveWorkbenchView``
composition. It answers a ``(task_id, session_id)`` query for one locally tracked
session's live progress, but only through a **default-off activation gate**:

* :func:`query_task_live_progress` is disabled unless the caller presents an
  explicit :class:`LiveProgressQueryActivationGate`. With no gate the query fails
  closed with the stable ``runtime_live_progress_query_disabled`` code and never
  calls the injected live-progress reader, appends no ``TaskEventLog`` event,
  updates no binding cursor, and launches nothing.
* The only activated surfaces are **local/offline** — ``local_offline`` and
  ``hermes_internal``. The gate is an exact allowlist: any other surface
  (Gateway, Feishu, IM, delivery, public ingress, Temporal Worker, production
  config, a real AGENT / external runner, a default-on posture) is rejected /
  denied with the stable ``runtime_invalid_live_progress_query`` code. Those
  future, non-approved surfaces are documentation boundaries only, never active
  code paths here.

When a valid local/offline gate is presented the query resolves the binding,
uses the resolved **private** ``artifact_dir`` only for the injected reader (it is
never stored / serialized / logged / echoed), uses the safe ``artifact_ref`` as
the public handle, and returns the safe combined workbench view. ``after_seq``
(when provided) overrides for this one read; otherwise the binding's foreign
``last_seen_cursor`` is used. The query is **read-only**: it never advances the
binding cursor and never appends to ``TaskEventLog`` — cursor advancement stays
the caller's explicit PR-LS2 ``update_last_seen_cursor`` step, so the foreign
agent-run-supervisor read-model cursor never becomes a Sachima ``seq`` and the
supervisor's terminal state stays a runtime observation, not a business verdict.

Everything here is pure local/offline Python. Importing this module starts no OS
process, network listener, container, daemon, Temporal service / Worker / client,
Gateway, Feishu, network call, or delivery surface, launches no external runner,
and wires none of those surfaces — the producer library is reached only through
the injected reader the builder receives (no top-level ``agent_run_supervisor``
import). Forbidden terms in this prose are no-leak / denied-surface boundary
canaries only, never behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn

from .agent_run_supervisor_live_workbench import (
    AgentRunSupervisorLiveWorkbenchView,
    build_agent_run_supervisor_live_workbench_view,
)
from .agent_run_supervisor_port import AgentRunSupervisorPort
from .events import SpineError, _safe_id, safe_task_id, scan_for_leak
from .execution_port import LivenessState, SessionRef
from .live_progress_projection import LiveProgressReader
from .live_progress_sources import LiveProgressSourceBindings
from .registry import TaskRegistry

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_LIVE_PROGRESS_QUERY = "runtime_invalid_live_progress_query"
RUNTIME_LIVE_PROGRESS_QUERY_DISABLED = "runtime_live_progress_query_disabled"

LIVE_PROGRESS_QUERY_STABLE_CODES = frozenset(
    {RUNTIME_INVALID_LIVE_PROGRESS_QUERY, RUNTIME_LIVE_PROGRESS_QUERY_DISABLED}
)

#: Canonical gate type — an exact string, never dynamically discovered.
LIVE_PROGRESS_QUERY_GATE_TYPE = "sachima.runtime_spine.live_progress_query_activation_gate.v1"

#: The only two surfaces this slice activates. Both are local/offline. Anything
#: outside this exact allowlist (Gateway / Feishu / IM / delivery / public
#: ingress / Temporal Worker / production / default-on / a real runner) is denied.
LOCAL_OFFLINE_QUERY_SURFACE = "local_offline"
HERMES_INTERNAL_QUERY_SURFACE = "hermes_internal"
APPROVED_QUERY_SURFACES = frozenset(
    {LOCAL_OFFLINE_QUERY_SURFACE, HERMES_INTERNAL_QUERY_SURFACE}
)

#: Bounds shared with the projection's cursor / limit validation.
_MAX_CURSOR = 1_000_000_000
_MAX_LIMIT = 1000


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_LIVE_PROGRESS_QUERY)


def _disabled() -> NoReturn:
    raise SpineError(RUNTIME_LIVE_PROGRESS_QUERY_DISABLED)


# --------------------------------------------------------------------------- #
# Field-level sanitizers (each fails closed with the module's invalid code)
# --------------------------------------------------------------------------- #
def _safe_query_task_id(value: Any) -> str:
    return safe_task_id(value, code=RUNTIME_INVALID_LIVE_PROGRESS_QUERY)


def _safe_query_session_id(value: Any) -> str:
    if type(value) is not str or not value.startswith("sess_"):
        _invalid()
    return _safe_id(value, code=RUNTIME_INVALID_LIVE_PROGRESS_QUERY)


def _safe_query_after_seq(value: Any) -> int | None:
    # bool is an int subclass — exclude it so a flag can't pose as a cursor.
    if value is None:
        return None
    if type(value) is not int or value < 0 or value > _MAX_CURSOR:
        _invalid()
    return value


def _safe_query_limit(value: Any) -> int:
    # bool is an int subclass — exclude it so a flag can't pose as a limit.
    if type(value) is not int or value < 1 or value > _MAX_LIMIT:
        _invalid()
    return value


# --------------------------------------------------------------------------- #
# Default-off activation gate — an exact local/offline allowlist
# --------------------------------------------------------------------------- #
def _raw_gate_dict(gate: Any) -> dict[str, Any]:
    return {"type": gate.type, "surface": gate.surface, "enabled": gate.enabled}


def _check_gate_fields(gate: Any) -> None:
    """Exact fail-closed validation of an activation gate's fields.

    Construction alone is never grounds for trust: a directly constructed or
    ``object.__new__``-forged gate with a forged ``type``, a surface outside the
    exact :data:`APPROVED_QUERY_SURFACES` allowlist (a denied Gateway / Feishu /
    IM / delivery / public-ingress / Temporal-Worker / production / default-on
    surface), or a non-``True`` ``enabled`` posture fails closed with the stable
    ``runtime_invalid_live_progress_query`` code. It never echoes the rejected
    surface.
    """

    try:
        gate_type = gate.type
        surface = gate.surface
        enabled = gate.enabled
    except AttributeError:
        _invalid()

    if type(gate_type) is not str or gate_type != LIVE_PROGRESS_QUERY_GATE_TYPE:
        _invalid()
    # Exact allowlist: only the two local/offline surfaces are activated.
    if type(surface) is not str or surface not in APPROVED_QUERY_SURFACES:
        _invalid()
    # A gate is an explicit activation — the enabled posture is pinned to True, so
    # a False / non-bool "gate" can never pose as an activation.
    if type(enabled) is not bool or enabled is not True:
        _invalid()
    # Defense in depth: the projected gate shape must pass the refs-only no-leak
    # scan (catches a Feishu / Lark / private marker smuggled into a field).
    if scan_for_leak(_raw_gate_dict(gate)) is not None:
        _invalid()


@dataclass(frozen=True)
class LiveProgressQueryActivationGate:
    """A frozen, explicit, default-off local/offline query activation gate.

    Presenting a gate is the *only* way to activate :func:`query_task_live_progress`.
    The gate is pinned to an approved local/offline ``surface`` and an ``enabled``
    posture of ``True``; ``__post_init__`` re-runs the full allowlist so a directly
    constructed or forged gate (denied surface, forged type, non-``True`` enabled)
    fails closed instead of being trusted. Boundary consumers additionally call
    :func:`validate_live_progress_query_activation_gate` to defend against
    ``object.__new__`` forgery and hostile subclasses that skip ``__post_init__``.
    """

    type: str
    surface: str
    enabled: bool

    def __post_init__(self) -> None:
        _check_gate_fields(self)

    def as_dict(self) -> dict[str, Any]:
        validate_live_progress_query_activation_gate(self)
        return {"type": self.type, "surface": self.surface, "enabled": self.enabled}


def validate_live_progress_query_activation_gate(
    gate: Any,
) -> LiveProgressQueryActivationGate:
    """Re-validate an activation gate at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type or any denied surface / flipped posture
    fails closed with the stable ``runtime_invalid_live_progress_query`` code,
    never echoing the rejected surface.
    """

    if type(gate) is not LiveProgressQueryActivationGate:
        _invalid()
    _check_gate_fields(gate)
    return gate


def build_live_progress_query_activation_gate(surface: str) -> LiveProgressQueryActivationGate:
    """Build an enabled activation gate for one approved local/offline ``surface``.

    ``surface`` must be exactly ``local_offline`` or ``hermes_internal``; any other
    (denied / unknown) surface fails closed with the stable
    ``runtime_invalid_live_progress_query`` code without echoing it.
    """

    if type(surface) is not str or surface not in APPROVED_QUERY_SURFACES:
        _invalid()
    return validate_live_progress_query_activation_gate(
        LiveProgressQueryActivationGate(
            type=LIVE_PROGRESS_QUERY_GATE_TYPE, surface=surface, enabled=True
        )
    )


def local_offline_query_gate() -> LiveProgressQueryActivationGate:
    """The local/offline activation gate — reads run in-process over fixtures only."""

    return build_live_progress_query_activation_gate(LOCAL_OFFLINE_QUERY_SURFACE)


def hermes_internal_query_gate() -> LiveProgressQueryActivationGate:
    """The Hermes-internal activation gate — a private, non-public query helper."""

    return build_live_progress_query_activation_gate(HERMES_INTERNAL_QUERY_SURFACE)


def _require_enabled_gate(gate: Any) -> LiveProgressQueryActivationGate:
    """Fail closed unless an explicit, valid local/offline gate is presented.

    A missing gate (``None``) is the default-off posture and fails closed with the
    stable ``runtime_live_progress_query_disabled`` code *before* any binding /
    reader access. A presented-but-denied / forged gate fails closed with the
    stable ``runtime_invalid_live_progress_query`` code. Either way the reader is
    never called.
    """

    if gate is None:
        _disabled()
    return validate_live_progress_query_activation_gate(gate)


# --------------------------------------------------------------------------- #
# The controlled query entrypoint — default-off, read-only, local/offline
# --------------------------------------------------------------------------- #
def query_task_live_progress(
    bindings: LiveProgressSourceBindings,
    registry: TaskRegistry,
    port: AgentRunSupervisorPort,
    progress_reader: LiveProgressReader,
    task_id: str,
    session_id: str,
    *,
    gate: LiveProgressQueryActivationGate | None = None,
    after_seq: int | None = None,
    limit: int = 100,
    liveness: LivenessState | None = None,
) -> AgentRunSupervisorLiveWorkbenchView:
    """Query one session's live progress through the default-off activation gate.

    The activation ``gate`` is checked **first**: with no gate the query fails
    closed with ``runtime_live_progress_query_disabled`` and never calls
    ``progress_reader``, appends no ``TaskEventLog`` event, updates no binding
    cursor, and launches nothing. A presented-but-denied / forged gate fails closed
    with ``runtime_invalid_live_progress_query`` — again before any read.

    With a valid local/offline gate the ``(task_id, session_id)`` pair is validated
    and its PR-LS2 binding resolved; the resolved **private** ``artifact_dir`` is
    passed only to the injected reader (never stored / serialized / echoed) with the
    safe ``artifact_ref`` handle. ``after_seq`` overrides for this read when given,
    else the binding's foreign ``last_seen_cursor`` is used. A missing / forged /
    mismatched binding, an unsafe id / cursor / limit, or an untracked session all
    fail closed with a stable ``runtime_invalid_live_progress_query`` code and never
    echo the offending value / path. This query is read-only: it advances no binding
    cursor and appends no event, so the foreign read-model cursor never enters
    ``TaskEventLog``.
    """

    # 1. Activation gate first — the default-off boundary, before any read.
    _require_enabled_gate(gate)

    # 2. Validate the query inputs exactly (fail closed, never echo).
    if type(bindings) is not LiveProgressSourceBindings:
        _invalid()
    safe_task = _safe_query_task_id(task_id)
    safe_session = _safe_query_session_id(session_id)
    safe_after = _safe_query_after_seq(after_seq)
    safe_limit = _safe_query_limit(limit)

    # 3. Resolve the binding and compose the combined view. Any resolution /
    #    composition contract violation collapses to the single stable query code
    #    so the controlled surface never leaks which inner layer failed or its
    #    offending id / path / value.
    try:
        resolved = bindings.resolve(safe_task, safe_session)
        source = resolved.source
        # after_seq overrides for this read; otherwise the foreign binding cursor.
        effective_after_seq = safe_after if safe_after is not None else source.last_seen_cursor
        ref = SessionRef(task_id=source.task_id, session_id=source.session_id)
        return build_agent_run_supervisor_live_workbench_view(
            registry,
            port,
            ref,
            progress_reader,
            resolved.artifact_dir,
            source.artifact_ref,
            after_seq=effective_after_seq,
            limit=safe_limit,
            liveness=liveness,
        )
    except SpineError:
        _invalid()


# --------------------------------------------------------------------------- #
# Dependency-injection service — bundles deps + a default-off gate
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LiveProgressQueryService:
    """A default-off DI wrapper over :func:`query_task_live_progress`.

    Bundles the host-owned ``bindings`` / ``registry`` / ``port`` /
    ``progress_reader`` with an optional activation ``gate``. The service is
    **disabled by default** (``gate=None``): its :meth:`query_task_live_progress`
    fails closed with ``runtime_live_progress_query_disabled`` until it is
    constructed with an explicit local/offline gate. A forged gate fails closed at
    construction.
    """

    bindings: LiveProgressSourceBindings
    registry: TaskRegistry
    port: AgentRunSupervisorPort
    progress_reader: LiveProgressReader
    gate: LiveProgressQueryActivationGate | None = None

    def __post_init__(self) -> None:
        if self.gate is not None:
            validate_live_progress_query_activation_gate(self.gate)

    def query_task_live_progress(
        self,
        task_id: str,
        session_id: str,
        *,
        after_seq: int | None = None,
        limit: int = 100,
        liveness: LivenessState | None = None,
    ) -> AgentRunSupervisorLiveWorkbenchView:
        """Query one session's live progress using this service's bundled gate."""

        return query_task_live_progress(
            self.bindings,
            self.registry,
            self.port,
            self.progress_reader,
            task_id,
            session_id,
            gate=self.gate,
            after_seq=after_seq,
            limit=limit,
            liveness=liveness,
        )


__all__ = [
    "RUNTIME_INVALID_LIVE_PROGRESS_QUERY",
    "RUNTIME_LIVE_PROGRESS_QUERY_DISABLED",
    "LIVE_PROGRESS_QUERY_STABLE_CODES",
    "LIVE_PROGRESS_QUERY_GATE_TYPE",
    "LOCAL_OFFLINE_QUERY_SURFACE",
    "HERMES_INTERNAL_QUERY_SURFACE",
    "APPROVED_QUERY_SURFACES",
    "LiveProgressQueryActivationGate",
    "LiveProgressQueryService",
    "query_task_live_progress",
    "build_live_progress_query_activation_gate",
    "local_offline_query_gate",
    "hermes_internal_query_gate",
    "validate_live_progress_query_activation_gate",
]
