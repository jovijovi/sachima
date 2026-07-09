"""ARS-INT Runtime Spine — refs-only goal/prompt turn dispatcher.

The ``ExecutionPort`` keeps lifecycle purity; *making the AGENT work* is this
separate product seam. :class:`AgentRunSupervisorTurnDispatcher` accepts a
refs-only :class:`TurnDispatchRequest`, resolves the private goal/prompt text
host-side through an injected ``payload_resolver`` (a claim-check — the text
never appears in requests, outcomes, events, logs, or serialized state),
drives exactly one supervised library turn through the
:class:`~.agent_run_supervisor_library_backend.AgentRunSupervisorLibraryBackend`,
and then:

* **auto-binds** the produced private turn artifact directory into the
  host-owned ``LiveProgressSourceBindings`` under a fresh safe ``turn_ref``
  (``turn_<n>_<digest8>``), resetting the foreign ``last_seen_cursor`` to
  ``None`` — each turn is a new read-model stream, so cursors never bleed
  across turns and the manual bindings-file copy step is retired;
* appends **refs-only** canonical events (a ``progress`` marker when the turn
  is accepted, a ``milestone`` carrying the ``turn_ref`` after it lands) —
  terminal states keep flowing through the port's own backend-state sync, so
  the Task Event Log stays the single seq authority and the ARS cursor never
  enters it;
* enforces **single-flight per task**: one in-flight turn at a time (the ARS
  session lease is the second, library-level guard), with the stable
  ``runtime_turn_dispatch_busy`` code for concurrent attempts.

Goal turns preserve the supervisor's 0.1.6 goal-contract semantics: the payload is compiled
through the role-aware ARS ``GoalSpec``/``compile_goal_prompt`` (via the
backend facade) — never a literal ``/goal`` slash prompt that a non-native
adapter would silently no-op.

Failure hygiene: precondition violations (unknown/terminal session, forged or
unsafe request, unresolvable payload, busy slot) raise stable codes before any
library touch; a turn that crashes inside the library yields a
``runtime_ars_turn_failed`` outcome and leaves the previous binding fully
intact — never a half-bound state, never an echoed path or payload byte.

Pure local/offline Python: importing this module starts no process, socket,
Gateway, Feishu, or Temporal surface and performs no ``agent_run_supervisor``
import — the library is reached only through the injected backend. Forbidden
terms in this prose are no-leak boundary canaries only, never behavior.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Any, Callable, NoReturn

from .agent_run_supervisor_library_backend import (
    AgentRunSupervisorLibraryBackend,
    LibraryTurnResult,
)
from .agent_run_supervisor_port import AgentRunSupervisorPort
from .events import SpineError, _safe_id, build_event_body, safe_task_id
from .live_progress_sources import LiveProgressSourceBindings
from .registry import TaskRegistry

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_TURN_DISPATCH = "runtime_invalid_turn_dispatch"
RUNTIME_TURN_DISPATCH_BUSY = "runtime_turn_dispatch_busy"
RUNTIME_ARS_TURN_FAILED = "runtime_ars_turn_failed"

TURN_DISPATCH_STABLE_CODES = frozenset(
    {
        RUNTIME_INVALID_TURN_DISPATCH,
        RUNTIME_TURN_DISPATCH_BUSY,
        RUNTIME_ARS_TURN_FAILED,
    }
)

#: Closed request vocabulary: a turn either carries a standing goal or a plain
#: prompt. Anything else fails closed.
TURN_KINDS = frozenset({"goal", "prompt"})

#: The supervisor's closed turn-status vocabulary an outcome may carry
#: (mirrors the library backend's contract with the pinned ARS package).
_OUTCOME_SUPERVISOR_STATUSES = frozenset(
    {
        "completed",
        "no_op",
        "runner_error",
        "invalid_invocation",
        "timed_out",
        "no_session",
        "permission_denied",
        "interrupted",
        "protocol_error",
        "infrastructure_error",
        "policy_error",
    }
)


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_TURN_DISPATCH)


def _safe_dispatch_task_id(value: Any) -> str:
    return safe_task_id(value, code=RUNTIME_INVALID_TURN_DISPATCH)


def _safe_dispatch_session_id(value: Any) -> str:
    if type(value) is not str or not value.startswith("sess_"):
        _invalid()
    return _safe_id(value, code=RUNTIME_INVALID_TURN_DISPATCH)


def _safe_dispatch_ref(value: Any) -> str:
    return _safe_id(value, code=RUNTIME_INVALID_TURN_DISPATCH)


# --------------------------------------------------------------------------- #
# Refs-only value objects
# --------------------------------------------------------------------------- #
def _check_request_fields(request: Any) -> None:
    try:
        task_id = request.task_id
        session_id = request.session_id
        turn_kind = request.turn_kind
        payload_ref = request.payload_ref
    except AttributeError:
        _invalid()
    _safe_dispatch_task_id(task_id)
    _safe_dispatch_session_id(session_id)
    if turn_kind not in TURN_KINDS:
        _invalid()
    _safe_dispatch_ref(payload_ref)


@dataclass(frozen=True)
class TurnDispatchRequest:
    """One refs-only turn request: identity + kind + a payload claim-check ref.

    ``payload_ref`` names private goal/prompt text held by the host's own
    evidence surface; the text itself never rides on this object.
    ``__post_init__`` re-runs the full allowlist so a directly constructed or
    forged request fails closed instead of being trusted.
    """

    task_id: str
    session_id: str
    turn_kind: str
    payload_ref: str

    def __post_init__(self) -> None:
        _check_request_fields(self)


def validate_turn_dispatch_request(request: TurnDispatchRequest) -> TurnDispatchRequest:
    """Re-validate a request at the trust boundary and return it unchanged."""

    if type(request) is not TurnDispatchRequest:
        _invalid()
    _check_request_fields(request)
    return request


def _check_outcome_fields(outcome: Any) -> None:
    try:
        task_id = outcome.task_id
        session_id = outcome.session_id
        turn_ref = outcome.turn_ref
        supervisor_status = outcome.supervisor_status
        artifact_ref = outcome.artifact_ref
        error_code = outcome.error_code
    except AttributeError:
        _invalid()
    _safe_dispatch_task_id(task_id)
    _safe_dispatch_session_id(session_id)
    if error_code is None:
        # A dispatched turn: refs and a closed-vocabulary observation required.
        if supervisor_status not in _OUTCOME_SUPERVISOR_STATUSES:
            _invalid()
        _safe_dispatch_ref(turn_ref)
        _safe_dispatch_ref(artifact_ref)
        if artifact_ref != turn_ref:
            _invalid()
    else:
        # A turn-stage failure: a stable code and nothing else.
        if error_code not in TURN_DISPATCH_STABLE_CODES:
            _invalid()
        if supervisor_status is not None or turn_ref is not None or artifact_ref is not None:
            _invalid()


@dataclass(frozen=True)
class TurnDispatchOutcome:
    """One dispatch's refs-only outcome — runtime observation, never a verdict.

    Exactly one of the two shapes holds: a dispatched turn (``turn_ref`` +
    ``artifact_ref`` + a closed-vocabulary ``supervisor_status``; no error
    code) or a turn-stage failure (a stable ``error_code`` and nothing else).
    Payload text and private artifact paths are structurally absent.
    """

    task_id: str
    session_id: str
    turn_ref: str | None
    supervisor_status: str | None
    artifact_ref: str | None
    error_code: str | None

    def __post_init__(self) -> None:
        _check_outcome_fields(self)


def validate_turn_dispatch_outcome(outcome: TurnDispatchOutcome) -> TurnDispatchOutcome:
    """Re-validate an outcome at the trust boundary and return it unchanged."""

    if type(outcome) is not TurnDispatchOutcome:
        _invalid()
    _check_outcome_fields(outcome)
    return outcome


def derive_turn_ref(turn_index: int, turn_id: str) -> str:
    """The safe public turn ref: ``turn_<n>_<digest8>`` — never the raw id.

    Supervisor turn ids carry uppercase timestamp material and are not safe
    spine refs; the digest keeps the public handle stable, unique, and
    ``_safe_id``-shaped.
    """

    if type(turn_index) is not int or turn_index < 1:
        _invalid()
    if type(turn_id) is not str or not turn_id:
        _invalid()
    digest = hashlib.sha256(turn_id.encode("utf-8")).hexdigest()[:8]
    return _safe_dispatch_ref(f"turn_{turn_index}_{digest}")


# --------------------------------------------------------------------------- #
# The dispatcher
# --------------------------------------------------------------------------- #
def _fail_closed_payload_resolver(payload_ref: str) -> str:
    """Default resolver for display-only compositions: dispatch stays closed."""

    _ = payload_ref
    _invalid()
    raise AssertionError("unreachable")


class AgentRunSupervisorTurnDispatcher:
    """Single-flight, refs-only turn dispatch over the library backend."""

    def __init__(
        self,
        port: AgentRunSupervisorPort,
        backend: AgentRunSupervisorLibraryBackend,
        bindings: LiveProgressSourceBindings,
        registry: TaskRegistry,
        payload_resolver: Callable[[str], str] | None = None,
        *,
        executor: Any | None = None,
    ) -> None:
        if type(port) is not AgentRunSupervisorPort:
            _invalid()
        if type(backend) is not AgentRunSupervisorLibraryBackend:
            _invalid()
        if type(bindings) is not LiveProgressSourceBindings:
            _invalid()
        if type(registry) is not TaskRegistry:
            _invalid()
        # The port's canonical log and the dispatcher's must be the same object,
        # or turn events would fork away from the single seq authority.
        if registry is not port._registry:
            _invalid()
        if payload_resolver is not None and not callable(payload_resolver):
            _invalid()
        self._port = port
        self._backend = backend
        self._bindings = bindings
        self._registry = registry
        self._payload_resolver = (
            payload_resolver if payload_resolver is not None else _fail_closed_payload_resolver
        )
        self._executor = executor
        self._lock = threading.RLock()
        self._in_flight: set[str] = set()

    def in_flight(self, task_id: str) -> bool:
        safe_task = _safe_dispatch_task_id(task_id)
        with self._lock:
            return safe_task in self._in_flight

    def dispatch(self, request: TurnDispatchRequest) -> TurnDispatchOutcome:
        """Dispatch exactly one goal/prompt turn for a live, tracked session.

        Precondition violations raise stable codes before any library touch;
        a turn that crashes inside the library returns the failure-shaped
        outcome with ``runtime_ars_turn_failed`` and leaves the previous
        source binding fully intact.
        """

        validate_turn_dispatch_request(request)
        status = self._port_status(request.task_id)
        if status.session_id != request.session_id or status.terminal is not False:
            _invalid()

        with self._lock:
            if request.task_id in self._in_flight:
                raise SpineError(RUNTIME_TURN_DISPATCH_BUSY)
            self._in_flight.add(request.task_id)
        try:
            payload_text = self._resolve_payload(request.payload_ref)
            self._append_event(
                request.task_id,
                build_event_body(
                    event_type="progress",
                    status="running",
                    refs=(request.session_id,),
                ),
            )
            result = self._run_turn(request, payload_text)
            if result is None:
                return TurnDispatchOutcome(
                    task_id=request.task_id,
                    session_id=request.session_id,
                    turn_ref=None,
                    supervisor_status=None,
                    artifact_ref=None,
                    error_code=RUNTIME_ARS_TURN_FAILED,
                )
            turn_ref = derive_turn_ref(result.turn_index, result.turn_id)
            self._bindings.bind(
                request.task_id,
                request.session_id,
                result.turn_dir,
                turn_ref,
            )
            self._append_event(
                request.task_id,
                build_event_body(
                    event_type="milestone",
                    refs=(request.session_id, turn_ref),
                ),
            )
            # Let the port mirror the new backend state (completed/failed/...)
            # into the canonical log through its own idempotent sync.
            self._sync_port_state(request.task_id)
            return TurnDispatchOutcome(
                task_id=request.task_id,
                session_id=request.session_id,
                turn_ref=turn_ref,
                supervisor_status=result.status,
                artifact_ref=turn_ref,
                error_code=None,
            )
        finally:
            with self._lock:
                self._in_flight.discard(request.task_id)

    # -- internals ------------------------------------------------------------

    def _port_status(self, task_id: str) -> Any:
        try:
            return self._port.status(task_id)
        except SpineError:
            _invalid()

    def _resolve_payload(self, payload_ref: str) -> str:
        try:
            payload_text = self._payload_resolver(payload_ref)
        except SpineError:
            raise
        except BaseException:
            # Never chain/echo resolver faults — the ref itself is the only
            # material a caller needs to investigate host-side.
            _invalid()
        if type(payload_text) is not str or not payload_text.strip():
            _invalid()
        return payload_text

    def _run_turn(
        self, request: TurnDispatchRequest, payload_text: str
    ) -> LibraryTurnResult | None:
        def _run() -> LibraryTurnResult:
            return self._backend.run_turn(
                request.task_id,
                turn_kind=request.turn_kind,
                payload_text=payload_text,
            )

        try:
            if self._executor is None:
                result = _run()
            else:
                result = self._executor.submit(_run).result()
        except BaseException:
            # Turn-stage failure: reported through the failure-shaped outcome;
            # the previous binding stays untouched (no half-bound state).
            return None
        if type(result) is not LibraryTurnResult:
            return None
        return result

    def _append_event(self, task_id: str, body: dict[str, Any]) -> None:
        try:
            self._registry.append_event(task_id, body)
        except SpineError:
            _invalid()

    def _sync_port_state(self, task_id: str) -> None:
        try:
            self._port.status(task_id)
        except SpineError:
            # A post-turn status read fault is transient (PR3 policy); the
            # outcome still reports the turn's own observation.
            return


__all__ = [
    "RUNTIME_ARS_TURN_FAILED",
    "RUNTIME_INVALID_TURN_DISPATCH",
    "RUNTIME_TURN_DISPATCH_BUSY",
    "TURN_DISPATCH_STABLE_CODES",
    "TURN_KINDS",
    "AgentRunSupervisorTurnDispatcher",
    "TurnDispatchOutcome",
    "TurnDispatchRequest",
    "derive_turn_ref",
    "validate_turn_dispatch_outcome",
    "validate_turn_dispatch_request",
]
