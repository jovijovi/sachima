"""ARS-INT Runtime Spine — refs-only goal/prompt turn dispatcher.

The ``ExecutionPort`` keeps lifecycle purity; *making the AGENT work* is this
separate product seam. :class:`AgentRunSupervisorTurnDispatcher` accepts a
refs-only :class:`TurnDispatchRequest`, resolves the private goal/prompt text
host-side through an injected ``payload_resolver`` (a claim-check — the text
never appears in requests, outcomes, events, logs, or serialized state),
drives exactly one supervised turn through an allowlisted
:class:`~.supervisor_turn_backend.SupervisorTurnBackend` — the neutral,
Sachima-owned contract; no concrete backend type is named here — and then:

* **auto-binds** the turn's tagged private read-model locator into the
  host-owned ``LiveProgressSourceBindings`` under a fresh safe ``turn_ref``
  (``turn_<n>_<digest8>``), resetting the foreign ``last_seen_cursor`` to
  ``None`` — each turn is a new read-model stream, so cursors never bleed
  across turns and the manual bindings-file copy step is retired;
* appends **refs-only** canonical events (a ``progress`` marker when the turn
  is accepted, a ``milestone`` carrying the ``turn_ref`` after it lands) —
  terminal states keep flowing through the port's own backend-state sync, so
  the Task Event Log stays the single seq authority and the ARS cursor never
  enters it;
* enforces **single-flight per task**: one in-flight turn at a time, with the
  stable ``runtime_turn_dispatch_busy`` code for concurrent attempts. It is the
  outer guard only — the backend's own active-Run exclusion (Spec §7.4) is what
  refuses a second Run against a Run that has not been proven terminal.

The request's ``payload_ref`` is also this dispatch's ``dispatch_ref``: the
backend's durable Run/Session binding key (Spec §8.1). One claim-check ref is
one turn to dispatch, so re-dispatching the same request after an uncertain
submit resolves against the same durable record instead of minting a second.

Failure hygiene: precondition violations (unknown/terminal session, forged or
unsafe request, unresolvable payload, busy slot) raise stable codes before any
backend touch; a turn that crashes inside the backend yields a
``runtime_ars_turn_failed`` outcome and leaves the previous binding fully
intact — never a half-bound state, never an echoed path or payload byte.

Pure local/offline Python: importing this module starts no process, socket,
Gateway, Feishu, or Temporal surface and performs no ``agent_run_supervisor``
import — the daemon is reached only through the injected backend. Forbidden
terms in this prose are no-leak boundary canaries only, never behavior.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, NoReturn

from .agent_run_supervisor_port import AgentRunSupervisorPort
from .events import SpineError, _safe_id, build_event_body, safe_task_id
from .live_progress_sources import LiveProgressSourceBindings
from .registry import TaskRegistry
from .supervisor_turn_backend import (
    SUPERVISOR_TURN_STATUSES,
    DispatchedSupervisorTurn,
    SupervisorTurnBackend,
    TaskOperationLocks,
    derive_turn_ref,
    validate_supervisor_turn_backend,
    validate_supervisor_turn_result,
)

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

#: The transport-neutral turn vocabulary an outcome may carry. A backend's own
#: vocabulary is collapsed into this closed set before it reaches a dispatch
#: outcome, so no backend-private token is ever published here.
_OUTCOME_SUPERVISOR_STATUSES = SUPERVISOR_TURN_STATUSES


#: The one value a failed resolver produces. A sentinel rather than an
#: exception re-raise, so the stable failure is raised with no active exception
#: to become its context.
_RESOLVER_FAILED = object()


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


# --------------------------------------------------------------------------- #
# The dispatcher
# --------------------------------------------------------------------------- #
def _fail_closed_payload_resolver(payload_ref: str) -> str:
    """Default resolver for display-only compositions: dispatch stays closed."""

    _ = payload_ref
    _invalid()
    raise AssertionError("unreachable")


class AgentRunSupervisorTurnDispatcher:
    """Single-flight, refs-only turn dispatch over an allowlisted backend."""

    def __init__(
        self,
        port: AgentRunSupervisorPort,
        backend: SupervisorTurnBackend,
        bindings: LiveProgressSourceBindings,
        registry: TaskRegistry,
        payload_resolver: Callable[[str], str] | None = None,
        *,
        executor: Any | None = None,
        task_locks: TaskOperationLocks | None = None,
    ) -> None:
        if type(port) is not AgentRunSupervisorPort:
            _invalid()
        try:
            validate_supervisor_turn_backend(backend)
        except SpineError:
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
        # The shared section is DERIVED from the backend, never chosen here.
        # Admitting a Run and publishing it are one task operation, and "pass
        # the same provider to both" is a convention a future caller gets wrong
        # once — reopening the cancel-between-acceptance-and-publication race
        # with a graph that type-checks perfectly. An explicit provider is
        # accepted only when it IS the backend's own, and it is checked before
        # anything is used.
        backend_locks = getattr(backend, "task_locks", None)
        if type(backend_locks) is not TaskOperationLocks:
            _invalid()
        if task_locks is not None and task_locks is not backend_locks:
            _invalid()
        self._task_locks = backend_locks
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

    # -- graph identity (read-only; a composed bundle checks, never trusts) -- #
    @property
    def backend(self) -> SupervisorTurnBackend:
        return self._backend

    @property
    def port(self) -> AgentRunSupervisorPort:
        return self._port

    @property
    def registry(self) -> TaskRegistry:
        return self._registry

    @property
    def bindings(self) -> LiveProgressSourceBindings:
        return self._bindings

    @property
    def task_locks(self) -> TaskOperationLocks:
        """The shared task operation lock provider — the backend's own."""

        return self._task_locks

    def in_flight(self, task_id: str) -> bool:
        safe_task = _safe_dispatch_task_id(task_id)
        with self._lock:
            return safe_task in self._in_flight

    def dispatch(self, request: TurnDispatchRequest) -> TurnDispatchOutcome:
        """Dispatch exactly one goal/prompt turn for a live, tracked session.

        The single-flight slot is taken **first**, the moment the request
        validates and before anything is read, resolved, submitted, or
        appended. That ordering is what makes "busy" both honest and free: a
        losing dispatch performs no backend observation and no port sync, and
        it is told it is busy even during the one window where the winner's
        pending intent is on disk with its ack unread — the window in which a
        port read of its own would fail closed and mislabel the loser.

        Precondition violations raise stable codes before any backend touch;
        a turn that crashes inside the backend returns the failure-shaped
        outcome with ``runtime_ars_turn_failed`` and leaves the previous
        source binding fully intact.
        """

        validate_turn_dispatch_request(request)
        with self._reserved(request.task_id):
            return self._run_operation(request, self._dispatch_operation)

    def recover_dispatch(self, request: TurnDispatchRequest) -> TurnDispatchOutcome:
        """Explicitly recover one uncertain dispatch — never automatic.

        Same request, same claim-check ref, same injected payload resolver: it
        asks the backend to resolve the pending intent that request left
        behind, and publishes the result through the *same* binding and event
        path an ordinary acceptance takes. Nothing calls it on a caller's
        behalf; a dispatch left uncertain stays blocked until someone decides.

        It deliberately does not run ``dispatch``'s port precondition. An
        unresolved intent makes the port's own read fail closed — that is the
        state being recovered from, not a reason to refuse — so the check would
        make recovery unreachable exactly when it is needed. The backend still
        refuses anything that is not a genuine pending intent of this task.
        """

        validate_turn_dispatch_request(request)
        with self._reserved(request.task_id):
            return self._run_operation(request, self._recovery_operation)

    def rehydrate_source_binding(
        self, task_id: str, session_id: str, *, binding: Any = None
    ) -> str | None:
        """Rebind the durable Run's read-model source after a restart.

        A recomposed host holds the same durable ledger and the same task, but
        an empty binding store. This turns what the ledger already recorded
        into a usable read-model source — refs-only derivation plus the private
        locator, straight from the accepted binding — and returns the safe turn
        ref it bound, or ``None`` when the task has nothing accepted.

        ``binding`` names the exact accepted record to rebind. A restoration
        that already read its own durable current turn passes it, and the
        task-wide "latest" is never consulted — binding a task's newest Run when
        its current turn is an older one would attach the caller's stream to
        work it is not waiting for. Without a ``binding`` the previous
        latest-accepted behavior is unchanged.

        It submits nothing, opens nothing, and appends **no** canonical event:
        rebinding is Sachima catching up with what already happened, not a new
        turn. It never fabricates task state either — a task the ledger does
        not know stays unbound.
        """

        safe_task = _safe_dispatch_task_id(task_id)
        safe_session = _safe_dispatch_session_id(session_id)
        with self._reserved(safe_task), self._task_locks.hold(safe_task):
            # Read and bind inside the same task operation. Split them and a
            # turn that lands in between makes this publish the Run it
            # superseded, so the "latest" it binds is always the latest as of
            # the moment it binds.
            if binding is None:
                handoff = self._latest_accepted(safe_task, safe_session)
            else:
                handoff = self._accepted_for_binding(safe_task, safe_session, binding)
            if handoff is None:
                return None
            return self._bind_source(safe_task, safe_session, handoff)

    def _accepted_for_binding(
        self, task_id: str, session_id: str, binding: Any
    ) -> DispatchedSupervisorTurn | None:
        """The handoff for one named accepted record, or a precondition failure."""

        try:
            handoff = self._backend.accepted_turn_for_binding(
                task_id, binding, session_ref=session_id
            )
        except SpineError:
            _invalid()
        if handoff is None:
            return None
        if type(handoff) is not DispatchedSupervisorTurn:
            _invalid()
        return handoff

    # -- internals ------------------------------------------------------------

    @contextmanager
    def _reserved(self, task_id: str) -> Iterator[None]:
        """Hold this task's single-flight slot, or refuse before touching it."""

        with self._lock:
            if task_id in self._in_flight:
                raise SpineError(RUNTIME_TURN_DISPATCH_BUSY)
            self._in_flight.add(task_id)
        try:
            yield
        finally:
            with self._lock:
                self._in_flight.discard(task_id)

    def _latest_accepted(
        self, task_id: str, session_id: str
    ) -> DispatchedSupervisorTurn | None:
        """This task's latest accepted handoff, for **this** canonical Session.

        The backend refuses a Session that is not the one the accepted Run was
        dispatched under, so a rebind can never attach a Run to a conversation
        it never ran in. That refusal is a precondition violation here, not a
        turn-stage failure: nothing was attempted, so nothing failed.
        """

        try:
            handoff = self._backend.latest_accepted_turn(task_id, session_ref=session_id)
        except SpineError:
            _invalid()
        if handoff is None:
            return None
        if type(handoff) is not DispatchedSupervisorTurn:
            _invalid()
        return handoff

    def _turn_failed(self, request: TurnDispatchRequest) -> TurnDispatchOutcome:
        """The failure-shaped outcome — and deliberately nothing else.

        A turn the backend refused (an active Run, an unresolved intent) or
        lost (an uncertain submit) never became work, so no canonical event
        claims it did and no binding moves.
        """

        return TurnDispatchOutcome(
            task_id=request.task_id,
            session_id=request.session_id,
            turn_ref=None,
            supervisor_status=None,
            artifact_ref=None,
            error_code=RUNTIME_ARS_TURN_FAILED,
        )

    def _publish(
        self, request: TurnDispatchRequest, dispatched: DispatchedSupervisorTurn
    ) -> TurnDispatchOutcome:
        """Bind, append, and report — one path for every acceptance.

        A durable acceptance from a first submit and one from an explicit
        recovery are the same event in the world, so they publish through the
        same code: the same source binding and the same refs-only ``progress``
        and ``milestone`` pair. The events land only here, which is what keeps
        the canonical log a record of turns that actually started.

        This runs inside the task operation lock the backend's admission also
        held, so a cancel cannot land between "the daemon accepted" and
        "Sachima said so" — the canonical log can never show a task cancelled
        and then running. The port sync is deliberately not here: it is a port
        call, and the caller makes it after leaving the section.
        """

        result = validate_supervisor_turn_result(dispatched.result)
        turn_ref = self._bind_source(request.task_id, request.session_id, dispatched)
        self._append_event(
            request.task_id,
            build_event_body(
                event_type="progress",
                status="running",
                refs=(request.session_id,),
            ),
        )
        self._append_event(
            request.task_id,
            build_event_body(
                event_type="milestone",
                refs=(request.session_id, turn_ref),
            ),
        )
        return TurnDispatchOutcome(
            task_id=request.task_id,
            session_id=request.session_id,
            turn_ref=turn_ref,
            supervisor_status=result.supervisor_status,
            artifact_ref=result.source_ref,
            error_code=None,
        )

    def _bind_source(
        self, task_id: str, session_id: str, dispatched: DispatchedSupervisorTurn
    ) -> str:
        """Bind the turn's tagged private locator and return its safe ref."""

        result = dispatched.result
        self._bindings.bind_source(
            task_id,
            session_id,
            result.source_kind,
            dispatched.private_locator,
            result.source_ref,
            last_seen_cursor=result.foreign_cursor,
        )
        return result.run_ref

    # -- internals ------------------------------------------------------------

    def _run_operation(
        self,
        request: TurnDispatchRequest,
        operation: Callable[[TurnDispatchRequest], TurnDispatchOutcome],
    ) -> TurnDispatchOutcome:
        """Run one whole task operation — in whichever thread will hold the lock.

        The task operation lock is **reentrant, and therefore thread-affine**.
        A caller that took it and then waited on a worker would be waiting for
        a thread that can never acquire what the caller is holding: the classic
        RLock-across-an-executor deadlock. So the caller holds nothing but the
        single-flight slot, and the operation — precondition, resolver, backend
        run or recover, durable acceptance, binding and canonical publication —
        is one callable that acquires and releases the section entirely inside
        the thread that runs it. With no executor that thread is this one; with
        an executor it is the worker, and the callable is the same either way.

        The port sync stays out here on purpose. It is a port call, and the
        rule that keeps the port and the task lock from closing a cycle is that
        the dispatcher never holds the section across one — by this point the
        operation has released it.

        A caller that stops waiting (an executor whose ``result`` times out)
        gets the failure-shaped outcome, and the worker keeps going: the slot
        is released but the *section* is not, so nothing else can interleave
        with work that is still running. The slot bounds concurrency; the lock
        is what bounds correctness.
        """

        if self._executor is None:
            outcome = operation(request)
        else:
            def _operation() -> TurnDispatchOutcome:
                return operation(request)

            try:
                outcome = self._executor.submit(_operation).result()
            except SpineError:
                # A precondition violation is the caller's answer, not a turn
                # that failed: it is raised, exactly as the inline path raises.
                raise
            except BaseException:
                # Anything else — including a caller that timed out on a worker
                # still running — is reported as a turn-stage failure, never as
                # a success and never with an echo.
                outcome = self._turn_failed(request)
        if outcome.error_code is None:
            self._sync_port_state(request.task_id)
        return outcome

    def _dispatch_operation(self, request: TurnDispatchRequest) -> TurnDispatchOutcome:
        """The whole dispatch, from precondition to publication."""

        # The port is read OUTSIDE the task operation lock, deliberately.
        # ``port.kill`` holds the port's own lock while it calls into the
        # backend, which then takes the task lock; holding the section while
        # waiting on the port would close that cycle. The precondition loses
        # nothing by sitting here: the backend re-checks everything that
        # matters and refuses a task an interleaved cancel has ended, so a
        # stale "not terminal" cannot admit a Run.
        status = self._port_status(request.task_id)
        if status.session_id != request.session_id or status.terminal is not False:
            _invalid()
        with self._task_locks.hold(request.task_id):
            payload_text = self._resolve_payload(request.payload_ref)
            dispatched = self._run_turn(request, payload_text)
            if dispatched is None:
                return self._turn_failed(request)
            return self._publish(request, dispatched)

    def _recovery_operation(self, request: TurnDispatchRequest) -> TurnDispatchOutcome:
        """The whole recovery, from identity to publication."""

        with self._task_locks.hold(request.task_id):
            recovered = self._recover_turn(request)
            if recovered is None:
                return self._turn_failed(request)
            return self._publish(request, recovered)

    def _port_status(self, task_id: str) -> Any:
        try:
            return self._port.status(task_id)
        except SpineError:
            _invalid()

    def _resolve_payload(self, payload_ref: str) -> str:
        """Resolve the private payload, or fail with this seam's own code.

        **Every** fault collapses, a ``SpineError`` from the resolver included.
        An injected resolver is host code: it may raise a stable error of its
        own, carrying its own code and its own unsanitized message. Re-raising
        that would publish a code this dispatcher does not own and text it
        never checked — so the collapse is total, and the ref is the only
        material a caller needs to investigate host-side.

        The failure is raised **outside** the ``except`` block, deliberately:
        raised inside one, the collapsed error would carry the original as its
        ``__context__`` and leak it through any rendered traceback. Out here
        there is no active exception to attach, so the error that leaves has no
        cause and no context at all.
        """

        resolved: Any = _RESOLVER_FAILED
        try:
            resolved = self._payload_resolver(payload_ref)
        except BaseException:
            resolved = _RESOLVER_FAILED
        if resolved is _RESOLVER_FAILED:
            _invalid()
        if type(resolved) is not str or not resolved.strip():
            _invalid()
        return resolved

    def _run_turn(
        self, request: TurnDispatchRequest, payload_text: str
    ) -> DispatchedSupervisorTurn | None:
        def _run() -> DispatchedSupervisorTurn:
            return self._backend.run_turn(
                request.task_id,
                turn_kind=request.turn_kind,
                payload_text=payload_text,
                # The request's own claim-check ref serves as both refs the
                # backend needs (Spec §8.1). As the dispatch identity, it makes
                # a re-dispatch of the same request land on the *same* durable
                # binding rather than mint a second. As the prompt ref, it is
                # what the intent persists, so an explicit recovery resolves the
                # exact prompt back through this same injected resolver — the
                # host never has to hold the text to be able to recover.
                dispatch_ref=request.payload_ref,
                payload_ref=request.payload_ref,
                # The canonical Session this turn belongs to, so a later
                # recovery can prove it is a recovery of THIS dispatch.
                session_ref=request.session_id,
            )

        return self._attempt(_run)

    def _recover_turn(
        self, request: TurnDispatchRequest
    ) -> DispatchedSupervisorTurn | None:
        def _recover() -> DispatchedSupervisorTurn:
            return self._backend.recover_uncertain_submission(
                request.task_id,
                request.payload_ref,
                session_ref=request.session_id,
                turn_kind=request.turn_kind,
            )

        return self._attempt(_recover)

    def _attempt(
        self, run: Callable[[], DispatchedSupervisorTurn]
    ) -> DispatchedSupervisorTurn | None:
        """One backend call, inside the section the caller already holds.

        It deliberately does **not** hand the call to the executor: the whole
        operation was already routed there, and re-routing from inside the
        section is exactly the thread hand-off an RLock cannot survive.
        """

        try:
            result = run()
        except BaseException:
            # Turn-stage failure: reported through the failure-shaped outcome;
            # the previous binding stays untouched (no half-bound state).
            return None
        if type(result) is not DispatchedSupervisorTurn:
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
