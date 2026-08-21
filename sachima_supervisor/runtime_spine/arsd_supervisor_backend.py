"""P4 default-off ``arsd`` backend: submit, observe, cancel, terminal truth.

This module is the ARS 0.7.6 Socket API v3 integration plan's P4 slice
(``docs/plans/2026-08-17-ars-0.7.6-socket-api-v3-integration-plan.md`` §10): the
behavioral core that consumes P1's offline contract, P2's durable binding
ledger, and P3's neutral turn seam. It submits once, observes honestly, cancels
precisely, and never fabricates an outcome.

Boundaries:

* **Default-off, and constructing it is the gate.**
  :func:`require_enabled_arsd_supervisor_config` fails closed unless ``enabled``
  is exactly ``True``, before any daemon operation is attempted. Nothing here is
  composed into Runtime Spine or Gateway — that is P5.
* **Injected everything.** The daemon is reached only through the injected
  :class:`~.arsd_socket_contract.ArsdClientFacade`; identity is stored only in
  the injected :class:`~.arsd_run_binding_ledger.ArsdRunBindingLedger`; the
  frozen prompt is rebuilt for a recovery only through the injected resolver.
  Importing this module imports no ``agent_run_supervisor``, opens no socket,
  and starts nothing.
* **Negotiate -> pre-check -> submit, per new admission.** ``server_info`` is
  negotiated at composition and again immediately before **every new**
  admission, and that admission's pre-check runs against **its own** negotiated
  ``max_run_event_budget_bytes`` — never a cached, defaulted, or guessed one
  (Spec §5.3.1). A negotiation failure is one stable backend-unavailable
  verdict; there is no fallback to a library, a CLI, or another API version.
* **One record per dispatch.** The pending submission intent is written and
  durably landed **before** the first socket submit, and the validated
  three-key ack finalizes that same record in place with both ``run_id`` and
  ``ars_session_id`` (Spec §7.3.1). ``run_turn`` returns on durable acceptance
  with ``supervisor_status="accepted"``; it does not block until the AGENT
  terminates (Spec §8.3).
* **One active Run per task/Session — a concurrency bound, not a turn budget.**
  Before a second dispatch may write an intent or submit, this task's recorded
  Run must be proven terminal (Spec §7.4). An accepted Run with no terminal
  blocks it, and so does an observation that failed or could not be trusted —
  uncertainty refuses, it never admits. Trusted terminal truth clears it, and
  the next turn reuses the same Session. The exclusion and the write it guards
  run under one per-task admission lock, so concurrent dispatches yield one
  record and one submit.
* **A Run terminal is not a Session terminal.** Spec §6 gives ARS Sessions no
  close operation and §7.4 bounds *Runs*, so a finished Run leaves a live,
  reusable Session behind. The two questions therefore have two surfaces:
  :meth:`ArsdSupervisorBackend.observe_run` answers about the Run (the neutral
  token, terminals included — a ``PERMISSION_VIOLATION`` or ``CONFIG_FIDELITY``
  Run stays ``failed`` there), and :meth:`ArsdSupervisorBackend.status` /
  ``liveness`` answer about the Session the port drives, which stays ``running``
  until :meth:`ArsdSupervisorBackend.kill` — the one explicit task-lifecycle
  action — ends the task. Nothing else terminalizes a task, and nothing
  fabricates a Session close ARS does not have.
* **No automatic replay.** An indeterminate submit — including a genuinely lost
  ack — leaves the intent exactly as written, fail-closed. Only
  :meth:`ArsdSupervisorBackend.recover_uncertain_submission`, which no automatic
  path calls, may act on one: it rebuilds the payload through the same resolver
  from the intent's refs, refuses with zero socket calls if the rebuilt digest
  differs, and otherwise resends the identical ``request_id`` with the
  byte-equivalent frozen payload — no negotiation, no current-budget pre-check
  (Spec §5.6.2, Δ-12).
* **Per-Run configuration.** Every Run, including every reuse turn, re-resolves
  its own ``(requested_model, requested_effort)`` pair from the config's policy
  maps. The pair is never cached onto the Session binding and never read back
  from a Session's ``last_effective_*`` observation (Spec §5.5.4). A built
  request states what Sachima requested; nothing here claims what a Run
  executed under.
* **No-leak.** Raw ``run_id`` / ``ars_session_id`` / prompt text / private paths
  / remote message text never reach a public surface: results carry
  Sachima-derived refs, the private locator rides only on the
  :class:`~.supervisor_turn_backend.DispatchedSupervisorTurn` handoff, and every
  failure raises :class:`SpineError` whose message IS the stable code.
* **Foreign cursor only.** :class:`ArsdLiveProgressReader` reads strictly
  through ``run_events`` and translates ``next_from_seq``/``exhausted`` into the
  read model's ``resume_cursor``/``has_more``. That cursor is never mapped into
  Sachima's canonical per-task event sequence, and no daemon-private storage
  directory is ever read, named, or modeled (Spec §8.2, §9.2).

Ledger key note: the durable key is the full ``(task_id, session_id,
dispatch_ref)`` triple, where ``session_id`` is **this backend's handle** for
the task — the Sachima-side session identity minted at
:meth:`ArsdSupervisorBackend.create_or_attach`. The ARS Session id is a separate,
private value learned only from a validated ack.

Forbidden terms in this prose are no-leak boundary canaries only, never
behavior.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, NoReturn

from .arsd_run_binding_ledger import (
    ARSD_BINDING_ACCEPTED,
    ARSD_BINDING_STABLE_CODES,
    RUNTIME_ARSD_BINDING_CONFLICT,
    ArsdRunBinding,
    ArsdRunBindingLedger,
)
from .arsd_socket_contract import (
    ARSD_PERMISSION_VIOLATION_REASON,
    ARSD_SPEC_SCHEMA_VERSION,
    ARSD_STABLE_CODES,
    ARSD_TERMINAL_STATUSES,
    RUNTIME_ARSD_DISABLED,
    RUNTIME_ARSD_INTERNAL,
    RUNTIME_ARSD_INVALID_REQUEST,
    RUNTIME_ARSD_POLICY_DENIED,
    RUNTIME_ARSD_PROTOCOL_VIOLATION,
    RUNTIME_ARSD_SUBMISSION_INDETERMINATE,
    RUNTIME_ARSD_UNAVAILABLE,
    RUNTIME_ARSD_UNKNOWN_TARGET,
    RUNTIME_INVALID_ARSD_CONFIG,
    ArsdClientFacade,
    ArsdRunStatusObservation,
    ArsdServerInfo,
    ArsdSubmitAccepted,
    ArsdSupervisorConfig,
    ArsdTerminalResult,
    _safe_wire_token,
    arsd_submit_payload_digest,
    build_arsd_submit_payload,
    check_arsd_admission_event_budget,
    derive_arsd_request_id,
    project_arsd_terminal_result,
    require_enabled_arsd_supervisor_config,
    validate_arsd_run_cancel_result,
    validate_arsd_run_events_page,
    validate_arsd_run_status,
    validate_arsd_server_info,
    validate_arsd_session_view,
    validate_arsd_submit_result,
)
from .events import SpineError, _safe_digest, _safe_id, safe_task_id, scan_for_leak
from .execution_port import RUNTIME_INVALID_SESSION
from .supervisor_turn_backend import (
    SOURCE_KIND_ARSD_RUN,
    DispatchedSupervisorTurn,
    SupervisorTurnResult,
    TaskOperationLocks,
)

__all__ = [
    "ARSD_BACKEND_STABLE_CODES",
    "ARSD_TERMINAL_TO_NEUTRAL_STATUS",
    "ArsdLiveProgressReader",
    "ArsdRunCancelOutcome",
    "ArsdRunEventPage",
    "ArsdRunEventRecord",
    "ArsdRunProgressSnapshot",
    "ArsdSupervisorBackend",
    "derive_arsd_backend_handle",
    "map_arsd_terminal_to_neutral",
]

#: The closed failure surface of this backend: P1's contract codes, P2's
#: binding codes, and the spine's own no-session code. Nothing else is raised,
#: and every message IS its code.
ARSD_BACKEND_STABLE_CODES = frozenset(
    ARSD_STABLE_CODES | ARSD_BINDING_STABLE_CODES | {RUNTIME_INVALID_SESSION}
)

# --------------------------------------------------------------------------- #
# R-6 — the terminal mapping, hop by hop
# --------------------------------------------------------------------------- #
#: Hop 1 -> 2: the five-member ARS Native ACP terminal vocabulary into the
#: transport-neutral turn vocabulary (Spec §8.3). It is deliberately identity:
#: the neutral set carries ``timed_out`` and ``unknown`` so no collapse happens
#: before Sachima's own state mapping gets to see them.
ARSD_TERMINAL_TO_NEUTRAL_STATUS: Mapping[str, str] = MappingProxyType(
    {terminal: terminal for terminal in ARSD_TERMINAL_STATUSES}
)

#: Hop 2 -> 3 is deliberately **not** a table any more. A neutral Run terminal
#: used to be projected into a port session state, which made every finished
#: Run finish the task with it — and ARS has no Session close operation to
#: justify that (Spec §6). The Run-facing answer is the neutral token itself
#: (:meth:`ArsdSupervisorBackend.observe_run`); the Session-facing answer is
#: that the Session is live and reusable until an explicit cancel says
#: otherwise. Nothing maps one onto the other.

#: Terminal *reasons* that are evidence of a failure whatever status carries
#: them (Spec §10.7): a denied tool call later reported completed must never be
#: read as success. This is not a sixth terminal status and never becomes
#: user-visible text. ``CONFIG_FIDELITY`` is deliberately **not** here: a
#: reported configuration-fidelity failure already arrives as a failure and
#: needs no branch of its own.
_FAILURE_TERMINAL_REASONS = frozenset({ARSD_PERMISSION_VIOLATION_REASON})

_TERMINAL_STATUS_KEY = "status"
_TERMINAL_REASON_KEY = "reason"

_HANDLE_PREFIX = "arsd_"
_HANDLE_DIGEST_CHARS = 8
_TURN_KINDS = frozenset({"goal", "prompt"})
_SESSION_MODE_CREATE = "create"
_SESSION_MODE_REUSE = "reuse"
#: One bounded re-query after a cancel that produced no trusted evidence yet.
#: Sachima waits within its own bounded policy and then says ``ambiguous`` —
#: it never claims a successful cancel it cannot prove (Spec §10.4).
_CANCEL_REQUERIES = 1
#: The page size the progress probe reads; the caller's own ``limit`` governs
#: the event page it asks for.
_DEFAULT_PAGE_LIMIT = 100
_MAX_TEXT_LENGTH = 1_000_000_000
#: The observation token charset the safe read model admits (matches the
#: projection's own bounded token allowlist).
_OBSERVATION_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_UNKNOWN_OBSERVATION_TOKEN = "unknown"


# Every stable raiser suppresses exception context (``from None`` semantics):
# these run inside ``except`` blocks around injected-facade calls, and an
# unsuppressed ``__context__`` would render remote text through the chain.
def _invalid_request() -> NoReturn:
    raise SpineError(RUNTIME_ARSD_INVALID_REQUEST) from None


def _policy_denied() -> NoReturn:
    raise SpineError(RUNTIME_ARSD_POLICY_DENIED) from None


def _binding_conflict() -> NoReturn:
    raise SpineError(RUNTIME_ARSD_BINDING_CONFLICT) from None


def _unavailable() -> NoReturn:
    raise SpineError(RUNTIME_ARSD_UNAVAILABLE) from None


def map_arsd_terminal_to_neutral(status: Any, *, reason: Any = None) -> str:
    """Hop 1 -> 2: one ARS terminal (plus its reason) into the neutral token.

    A status outside the closed five-member vocabulary is not a terminal this
    adapter can read: it is untrusted evidence, and it fails closed with the
    contained-internal code rather than being guessed at or echoed.
    """

    if type(status) is not str or status not in ARSD_TERMINAL_TO_NEUTRAL_STATUS:
        raise SpineError(RUNTIME_ARSD_INTERNAL) from None
    if type(reason) is str and reason in _FAILURE_TERMINAL_REASONS:
        return "failed"
    return ARSD_TERMINAL_TO_NEUTRAL_STATUS[status]


def _trusted_terminal(result: Any) -> str | None:
    """The neutral terminal a trusted result body states, or ``None``.

    ``None`` means the evidence is not trustworthy — a body with no status on
    the closed vocabulary. The caller contains that as an internal failure; it
    is never read as a success and never echoed.
    """

    if not isinstance(result, Mapping):
        return None
    status = result.get(_TERMINAL_STATUS_KEY)
    if type(status) is not str or status not in ARSD_TERMINAL_TO_NEUTRAL_STATUS:
        return None
    return map_arsd_terminal_to_neutral(
        status, reason=result.get(_TERMINAL_REASON_KEY)
    )


def derive_arsd_backend_handle(task_id: Any) -> str:
    """The deterministic, ``_safe_id``-shaped backend handle for one task.

    It is also the ``session_id`` component of this task's ledger key, so the
    durable binding is addressable from a handle alone after a restart.
    """

    safe_task = safe_task_id(task_id, code=RUNTIME_ARSD_INVALID_REQUEST)
    digest = hashlib.sha256(safe_task.encode("utf-8")).hexdigest()
    return _safe_id(
        _HANDLE_PREFIX + digest[:_HANDLE_DIGEST_CHARS],
        code=RUNTIME_ARSD_INVALID_REQUEST,
    )


# --------------------------------------------------------------------------- #
# The arsd read model (P4-b) — run_events only, foreign cursor only
# --------------------------------------------------------------------------- #
def _observation_token(value: Any) -> str | None:
    """One bounded, non-leaky observation token, or ``None``.

    Remote event bodies are foreign material: only a token on the closed safe
    charset survives into the read model, and everything else becomes ``None``
    rather than carrying remote text onto a Sachima surface.
    """

    if type(value) is not str or _OBSERVATION_TOKEN_RE.fullmatch(value) is None:
        return None
    if scan_for_leak(value) is not None:
        return None
    return value


def _observation_count(value: Any) -> int | None:
    if isinstance(value, bool) or type(value) is not int:
        return None
    if value < 0 or value > _MAX_TEXT_LENGTH:
        return None
    return value


@dataclass(frozen=True)
class ArsdRunEventRecord:
    """One safe, refs-only projection of a remote run event.

    Carries the sequence, closed coarse tokens, and a text length — never the
    event body, its text, or any remote free-form material.
    """

    seq: int
    family: str
    kind: str | None
    status: str | None
    text_length: int | None


@dataclass(frozen=True)
class ArsdRunProgressSnapshot:
    """The progress summary the read model derives from a bounded event page.

    ``state`` is deliberately ``None``: this reader observes events, and run
    state is terminal truth that belongs to
    :meth:`ArsdSupervisorBackend.status`. It claims nothing it did not read.
    """

    schema_version: int
    state: str | None
    last_seq: int
    event_count: int


@dataclass(frozen=True)
class ArsdRunEventPage:
    """One bounded page in the shape the live-progress projection consumes.

    ``next_cursor`` is the foreign ``next_from_seq`` and ``has_more`` is
    ``not exhausted``. Both are foreign read-model values only.
    """

    records: tuple[ArsdRunEventRecord, ...] = field(repr=False)
    next_cursor: int
    has_more: bool


class ArsdLiveProgressReader:
    """``LiveProgressReader`` over an ``arsd`` Run, keyed by its private id.

    The locator is the private ``run_id`` the dispatched handoff carried. Every
    read goes through ``run_events(from_seq=..., limit=..., follow=False)`` and
    nothing else: no daemon-private storage location is read, named, or
    modeled, and no follow stream is opened.
    """

    def __init__(self, facade: Any, *, page_limit: int = _DEFAULT_PAGE_LIMIT) -> None:
        if not isinstance(facade, ArsdClientFacade):
            raise SpineError(RUNTIME_INVALID_ARSD_CONFIG)
        if isinstance(page_limit, bool) or type(page_limit) is not int or page_limit < 1:
            _invalid_request()
        self._facade = facade
        self._page_limit = page_limit

    def load_progress(self, artifact_dir: str) -> ArsdRunProgressSnapshot:
        """The summary for one Run, read from its own bounded event page."""

        page = self._page(artifact_dir, from_seq=0, limit=self._page_limit)
        return ArsdRunProgressSnapshot(
            schema_version=ARSD_SPEC_SCHEMA_VERSION,
            state=None,
            last_seq=page.next_cursor,
            event_count=len(page.records),
        )

    def read_event_page(
        self, artifact_dir: str, *, after_seq: int | None = None, limit: int = 100
    ) -> ArsdRunEventPage:
        """One page strictly after ``after_seq`` (the foreign cursor)."""

        from_seq = 0 if after_seq is None else after_seq
        return self._page(artifact_dir, from_seq=from_seq, limit=limit)

    def _page(self, run_id: Any, *, from_seq: Any, limit: Any) -> ArsdRunEventPage:
        token = _safe_wire_token(run_id, code=RUNTIME_ARSD_INVALID_REQUEST)
        if isinstance(from_seq, bool) or type(from_seq) is not int or from_seq < 0:
            _invalid_request()
        if isinstance(limit, bool) or type(limit) is not int or limit < 1:
            _invalid_request()
        try:
            raw = self._facade.run_events(token, from_seq=from_seq, limit=limit)
        except SpineError:
            raise
        except Exception:
            _unavailable()
        page = validate_arsd_run_events_page(raw, run_id=token, from_seq=from_seq)
        return ArsdRunEventPage(
            records=tuple(_map_event(event) for event in page.events),
            next_cursor=page.resume_cursor,
            has_more=page.has_more,
        )


def _map_event(event: Mapping[str, Any]) -> ArsdRunEventRecord:
    family = _observation_token(event.get("type"))
    return ArsdRunEventRecord(
        seq=event["seq"],
        family=_UNKNOWN_OBSERVATION_TOKEN if family is None else family,
        kind=_observation_token(event.get("kind")),
        status=_observation_token(event.get("status")),
        text_length=_observation_count(event.get("text_length")),
    )


# --------------------------------------------------------------------------- #
# Per-task policy binding (in-memory, host-owned, never serialized)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _RunPolicy:
    """The refs one Run resolves its request from — never resolved values."""

    workspace_ref: str
    agent_policy_ref: str
    model_policy_ref: str
    effort_policy_ref: str
    run_limits_policy_ref: str


@dataclass(frozen=True)
class ArsdRunCancelOutcome:
    """What one Run-scoped cancel actually proved.

    ``settled`` is the whole predicate, and it means *trusted terminal
    evidence*, not "the cancel call returned". An unsettled outcome carries no
    status and no answer, because a cancel that could not be proven has ended
    nothing — the Run may still be executing, and reporting it cancelled would
    be a claim about the daemon nobody made.
    """

    settled: bool
    run_status: str | None = None
    result: ArsdTerminalResult | None = field(default=None, repr=False)


@dataclass
class _TaskEntry:
    """One attached task. The active ``run_id`` is private and repr-excluded.

    This task's critical section is **not** here: it is the shared
    :class:`~.supervisor_turn_backend.TaskOperationLocks` lock, so the layer
    that publishes a turn holds the same section the layer that admitted it
    did.
    """

    task_id: str
    handle: str
    policy: _RunPolicy
    active_run_id: str | None = field(default=None, repr=False)
    #: The neutral terminal of the last Run proven over, remembered so a
    #: settled verdict outlives the Run being cleared as the active one — the
    #: daemon may already have forgotten a Run Sachima still has to report.
    last_run_status: str | None = None
    #: The bounded terminal answer that came with that verdict, remembered for
    #: the same reason and repr-excluded for the same reason its free-form
    #: field is: it is a payload to deliver, not diagnostic material.
    last_terminal_result: ArsdTerminalResult | None = field(default=None, repr=False)
    cancel_confirmed: bool = False


# --------------------------------------------------------------------------- #
# The backend
# --------------------------------------------------------------------------- #
class ArsdSupervisorBackend:
    """The default-off ``arsd`` Socket API v3 backend.

    Constructing it *is* the activation gate: a forged/invalid config fails
    closed with ``runtime_invalid_arsd_config`` and a disabled one with
    ``runtime_arsd_disabled``, before any daemon operation is attempted. It
    then negotiates ``server_info`` once, so a composed backend is one that
    has proven it is talking to the reviewed contract.

    It implements the neutral :class:`~.supervisor_turn_backend.
    SupervisorTurnBackend` surface, and the port-facing
    ``create_or_attach``/``attach_existing``/``status``/``signal``/``kill``/
    ``liveness`` methods return the same closed session-state vocabulary the
    spine's port already maps.
    """

    def __init__(
        self,
        config: ArsdSupervisorConfig,
        facade: Any,
        ledger: Any,
        *,
        prompt_resolver: Any | None = None,
        task_locks: Any | None = None,
    ) -> None:
        # The gate first: a disabled or forged config reaches no daemon.
        self._config = require_enabled_arsd_supervisor_config(config)
        if not isinstance(facade, ArsdClientFacade):
            raise SpineError(RUNTIME_INVALID_ARSD_CONFIG)
        if type(ledger) is not ArsdRunBindingLedger:
            raise SpineError(RUNTIME_INVALID_ARSD_CONFIG)
        if prompt_resolver is not None and not callable(prompt_resolver):
            raise SpineError(RUNTIME_INVALID_ARSD_CONFIG)
        if task_locks is not None and type(task_locks) is not TaskOperationLocks:
            raise SpineError(RUNTIME_INVALID_ARSD_CONFIG)
        # One provider per composed spine. A backend built without one owns its
        # own, which is right for a backend nothing else drives — but a
        # composition root injects the provider it also gives the dispatcher, so
        # both layers hold the *same* section for the same task.
        self._task_locks = TaskOperationLocks() if task_locks is None else task_locks
        self._facade = facade
        self._ledger = ledger
        self._prompt_resolver = prompt_resolver
        self._lock = threading.RLock()
        self._by_task: dict[str, _TaskEntry] = {}
        self._by_handle: dict[str, _TaskEntry] = {}
        #: The most recent negotiation this backend actually passed. Set by
        #: :meth:`_negotiate` itself, so it is never a value nobody validated.
        self._server_info: ArsdServerInfo | None = None
        # Composition-time negotiation: a backend that cannot prove the
        # contract never becomes composable (Spec §5.3.1).
        self._negotiate()

    @property
    def negotiated_server_info(self) -> ArsdServerInfo:
        """The last ``server_info`` this backend negotiated and validated.

        A composed backend has already proven the contract; retaining that
        proof is what lets a caller read a negotiated limit — the concurrency
        bound in particular — without either spending a socket call to re-ask
        or mirroring a default beside it. Reading it negotiates nothing: it is
        the answer of the most recent admission (or of composition, for a
        backend that has not admitted one yet), never a fresh question.
        """

        info = self._server_info
        if info is None:  # pragma: no cover - construction negotiates first
            _unavailable()
        return info

    @property
    def task_locks(self) -> TaskOperationLocks:
        """This backend's task operation lock provider (neutral contract).

        A composition root reads the shared section off here instead of being
        handed one and trusted to have handed the same one to both layers.
        """

        return self._task_locks

    # -- port surface ------------------------------------------------------- #
    def create_or_attach(self, task_id: str, refs: tuple[str, ...]) -> str:
        """Bind this task's refs and return its stable handle.

        A later call may carry a different model / effort / run-limits policy
        ref for the same task: those are per-**Run** choices re-resolved on
        every submit. A different workspace or agent is a different binding
        entirely and is refused rather than silently re-bound.
        """

        safe_task = safe_task_id(task_id, code=RUNTIME_ARSD_INVALID_REQUEST)
        policy = self._resolve_refs(refs)
        handle = derive_arsd_backend_handle(safe_task)
        with self._lock:
            existing = self._by_task.get(safe_task)
            if existing is not None:
                if (
                    existing.policy.workspace_ref != policy.workspace_ref
                    or existing.policy.agent_policy_ref != policy.agent_policy_ref
                ):
                    _policy_denied()
                existing.policy = policy
                return existing.handle
            # A first attachment in THIS process is not a first attachment of
            # the task: reconcile whatever the durable ledger already holds.
            return self._register(safe_task, handle, policy)

    def attach_existing(self, task_id: str, *, binding: Any = None) -> str:
        """Re-attach a task from its durable binding alone — never respawn.

        A task with no accepted binding has no Session to attach to, and this
        never creates one: it fails closed with the spine's no-session code.

        ``binding`` names the **exact** accepted record to attach. A restoration
        already knows which turn is current, so it passes that record and the
        task's own latest is never consulted: with two accepted Runs, choosing
        "the newest" would attach the wrong one whenever the current turn is not
        the newest, and would do it silently. A record the ledger no longer
        agrees with blocks rather than falling back.

        Called with no ``binding`` — the port's own protocol call — the previous
        latest-accepted behavior is unchanged.
        """

        safe_task = safe_task_id(task_id, code=RUNTIME_ARSD_INVALID_REQUEST)
        record = (
            self._require_accepted_binding(safe_task, binding)
            if binding is not None
            else None
        )
        with self._lock:
            existing = self._by_task.get(safe_task)
            if existing is not None:
                if record is not None and existing.active_run_id != record.run_id:
                    _binding_conflict()
                return existing.handle
        if record is None:
            record = self._latest_accepted(safe_task)
            if record is None:
                raise SpineError(RUNTIME_INVALID_SESSION)
        policy = self._policy_from_refs(record.resolver_refs)
        with self._lock:
            existing = self._by_task.get(safe_task)
            if existing is not None:
                if existing.active_run_id != record.run_id:
                    _binding_conflict()
                return existing.handle
            return self._register(
                safe_task,
                derive_arsd_backend_handle(safe_task),
                policy,
                active_binding=record,
            )

    def rehydrate_pending_intent(self, task_id: str, dispatch_ref: str) -> str:
        """Rebuild this task's entry from one **exact** pending intent. No I/O.

        A fresh process holds the durable ledger and nothing else. This turns one
        recorded intent back into an attachable task: the identity it was
        admitted under is re-derived from the intent's own refs and reconciled
        against the current config, and the entry is registered with **no**
        active Run — a pending dispatch has none, and adopting the task's latest
        accepted Run here would attach a Run this uncertain submission may
        already have superseded.

        It opens no socket, writes nothing to the ledger, and creates nothing:
        the whole point of a pending record is that only an explicit recovery
        may act on it, and restoration is not that decision.
        """

        safe_task = safe_task_id(task_id, code=RUNTIME_ARSD_INVALID_REQUEST)
        dispatch = _safe_id(dispatch_ref, code=RUNTIME_ARSD_INVALID_REQUEST)
        handle = derive_arsd_backend_handle(safe_task)
        with self._lock:
            existing = self._by_task.get(safe_task)
            if existing is not None:
                return existing.handle

        record = self._ledger.snapshot_exact(safe_task, handle, dispatch)
        if record is None or record.state == ARSD_BINDING_ACCEPTED:
            # No intent, or an acceptance: neither is a pending dispatch, and an
            # accepted record is never re-sent through this door.
            _binding_conflict()
        policy = self._policy_from_refs(record.resolver_refs)
        self._reconcile_durable_identity(policy, (record,))
        with self._lock:
            existing = self._by_task.get(safe_task)
            if existing is not None:
                return existing.handle
            entry = _TaskEntry(task_id=safe_task, handle=handle, policy=policy)
            self._by_task[safe_task] = entry
            self._by_handle[handle] = entry
            return handle

    def accepted_turn_for_binding(
        self, task_id: str, binding: Any, *, session_ref: str
    ) -> DispatchedSupervisorTurn:
        """The durable handoff for **one named** accepted binding.

        The exact-record variant of :meth:`latest_accepted_turn`. A restoration
        already knows which turn is current — it read it from its own durable
        record — so asking the ledger for "the latest" here would let a task with
        two accepted Runs bind the wrong stream, silently, on the strength of an
        ordering the coordinator never asked about.
        """

        entry = self._require_task(task_id)
        session = _safe_id(session_ref, code=RUNTIME_ARSD_INVALID_REQUEST)
        record = self._require_accepted_binding(entry.task_id, binding)
        if dict(record.resolver_refs).get("session_ref") != session:
            _binding_conflict()
        return self._accepted_handoff(record)

    def cancel_run(self, handle: str) -> "ArsdRunCancelOutcome":
        """Cancel **this Run** — and nothing wider.

        The narrow user-facing cancel seam. It reuses the same ``run_cancel``
        validation and bounded re-query the task-lifecycle ``kill`` does, and
        then stops: it never calls a Session operation, never sets the task
        terminal, and never reaches :meth:`kill`. A cancelled Run leaves a live,
        reusable Session behind, which is exactly what makes "cancel this piece
        of work, then continue the conversation" possible at all.

        Trusted terminal evidence — from the cancel reply or from one bounded
        re-query — is fed through the same reconciliation an ordinary
        observation uses, so the terminal that actually happened is the one that
        gets reported. A completion that won the race stays a completion; it is
        not rewritten as ``cancelled``.

        Without trusted evidence the outcome is honestly unsettled. Nothing is
        mutated, the Run stays this task's Run, and the caller keeps its permit
        and its refusal to continue until a later observation settles it.

        Runs under this task's admission lock, so a cancel cannot land between a
        dispatch's acceptance and its publication.
        """

        entry = self._require_handle(handle)
        with self._task_locks.hold(entry.task_id):
            self._require_no_unresolved_intent(entry.task_id)
            with self._lock:
                run_id = entry.active_run_id
                remembered = entry.last_run_status
                remembered_result = entry.last_terminal_result
            if run_id is None:
                # Nothing live. A remembered verdict is a settled answer; no
                # verdict at all is not, and neither is a reason to cancel.
                if remembered is None:
                    return ArsdRunCancelOutcome(settled=False)
                return ArsdRunCancelOutcome(
                    settled=True, run_status=remembered, result=remembered_result
                )

            try:
                raw = self._facade.run_cancel(run_id)
            except SpineError:
                raise
            except Exception:
                _unavailable()
            observation = validate_arsd_run_cancel_result(raw, run_id=run_id)
            if observation.status is not None:
                neutral = map_arsd_terminal_to_neutral(
                    observation.status, reason=self._reason_of(observation.result)
                )
                return self._settle_cancelled_run(
                    entry, run_id, neutral, observation.result
                )

            for _ in range(_CANCEL_REQUERIES):
                requery = self._observe(run_id)
                if requery.result is not None:
                    neutral = _trusted_terminal(requery.result)
                    if neutral is None:
                        raise SpineError(RUNTIME_ARSD_INTERNAL) from None
                    return self._settle_cancelled_run(
                        entry, run_id, neutral, requery.result
                    )
            return ArsdRunCancelOutcome(settled=False)

    def _settle_cancelled_run(
        self,
        entry: _TaskEntry,
        run_id: str,
        neutral: str,
        result_body: Any,
    ) -> "ArsdRunCancelOutcome":
        """Record the terminal a cancel proved, without ending the task."""

        projected = project_arsd_terminal_result(result_body, status=neutral)
        with self._lock:
            if entry.active_run_id == run_id:
                entry.active_run_id = None
                entry.last_run_status = neutral
                entry.last_terminal_result = projected
        return ArsdRunCancelOutcome(settled=True, run_status=neutral, result=projected)

    def _require_accepted_binding(self, safe_task: str, binding: Any) -> ArsdRunBinding:
        """Admit only a binding the ledger still agrees with, at its own key."""

        if type(binding) is not ArsdRunBinding:
            _binding_conflict()
        if binding.state != ARSD_BINDING_ACCEPTED or binding.run_id is None:
            _binding_conflict()
        handle = derive_arsd_backend_handle(safe_task)
        if binding.task_id != safe_task or binding.session_id != handle:
            _binding_conflict()
        record = self._ledger.snapshot_exact(safe_task, handle, binding.dispatch_ref)
        if record is None or record != binding:
            # A record that no longer matches is not the one this restoration
            # was told about; substituting the ledger's version would silently
            # rebind a different Run.
            _binding_conflict()
        return record

    def status(self, handle: str) -> str:
        """The **Session**-facing state of this task, honestly observed.

        This is what the port drives, and the port owns the *task* lifecycle —
        so what it needs to know is whether this task's durable ARS Session is
        still usable, not how the last Run happened to end. A Run reaching a
        terminal is reconciled here (it stops being the active Run, and its
        verdict is remembered), and the answer is still ``running``: the
        Session is live, reusable, and the next turn will pass its recorded id
        verbatim. Ending a task is an explicit decision an upper layer makes
        through :meth:`kill`, and that is the only path to ``cancelled``.

        Observing is still honest. While an unresolved intent exists there is
        no answer to give: the uncertain submit may have been accepted
        remotely, so the recorded Run is not known to be this task's current
        Run and observing it would report the wrong one (Spec §7.3.1, §10.3).
        An observation failure raises a transient stable code and mutates
        nothing: a disconnect means Sachima did not observe, never that the
        Session is gone (Spec §10.2).
        """

        entry = self._require_handle(handle)
        self._require_no_unresolved_intent(entry.task_id)
        with self._lock:
            if entry.cancel_confirmed:
                return "cancelled"
        # Reconcile for real — a read failure or untrusted evidence must not be
        # laundered into a cheerful "running".
        self._reconcile_active_run(entry)
        return "running"

    def observe_run(self, handle: str) -> str | None:
        """The **Run**-facing neutral status of this task's latest Run.

        ``accepted`` while a Run is still going, one of the five terminals once
        trusted evidence says it ended, and ``None`` for a task that has
        dispatched nothing. This is where a failure stays a failure: a
        ``PERMISSION_VIOLATION`` or ``CONFIG_FIDELITY`` Run is reported as
        ``failed`` here, without that verdict being spent on closing a Session
        nobody closed.
        """

        entry = self._require_handle(handle)
        self._require_no_unresolved_intent(entry.task_id)
        return self._reconcile_active_run(entry)

    def observe_run_result(self, handle: str) -> ArsdTerminalResult | None:
        """This task's bounded terminal answer, or ``None`` while there is none.

        ``None`` is the honest answer for a task that dispatched nothing and
        for a Run that is still going: a projection with an empty message would
        read as "it finished, silently", which is the one thing a delegated
        submission must never report.

        It reads exactly the ``run_status`` reply :meth:`observe_run` already
        reads — no artifact directory, no extra operation, no rehydrate — and
        the settled answer outlives the Run being cleared, because the daemon
        may forget a Run before Sachima has reported it.
        """

        entry = self._require_handle(handle)
        self._require_no_unresolved_intent(entry.task_id)
        self._reconcile_active_run(entry)
        with self._lock:
            return entry.last_terminal_result

    def liveness(self, handle: str) -> str:
        """Liveness is the Session's, for the same reason ``status`` is."""

        return self.status(handle)

    def signal(self, handle: str, decision_ref: str) -> str:
        """Fail closed: Socket API v3 has no permission-decision operation.

        Sachima supplies a frozen grant at submit and never an ACP mode, so
        there is no decision to deliver and no ``permission_wait -> running``
        transition to invent (Spec §10.6).
        """

        self._require_handle(handle)
        _safe_id(decision_ref, code=RUNTIME_ARSD_INVALID_REQUEST)
        _policy_denied()

    def kill(self, handle: str, reason_ref: str) -> str:
        """End this task — the one explicit path to a terminal task state.

        Cancels exactly this Run and never a Session operation. With no Run
        live there is nothing to cancel remotely and nothing to close: ARS has
        no Session close (Spec §6), so ending the task is Sachima's own
        decision about its own binding — it stops dispatching into it. Reaching
        for a Session operation to make that feel terminal would be inventing a
        state ARS does not have.

        While an unresolved intent exists this cancels nothing at all: the
        recorded Run may not be the one the task is actually running, and
        ending the older one would leave an uncertain Run alive while reporting
        the work cancelled. It fails closed until recovery says which Run this
        is (Spec §7.3.1).

        A cancel is only *claimed* on trusted terminal evidence; without it,
        one bounded re-query, then honest ``ambiguous`` — and the task is left
        exactly as it was, because an unproven cancel has ended nothing.

        The whole decision — the view it is taken on, the cancel, the bounded
        re-query, and the task-end — runs under this task's **admission lock**,
        the same one an admission holds. Without that, a ``run_turn`` parked
        between the active-Run exclusion and its first durable write is
        invisible here: the cancel would see a task with nothing running, end
        an empty task, return ``cancelled``, and then the parked admission
        would submit anyway and clear the cancel on its way through. Ending a
        task and starting a Run in it are one decision, so they take one lock.
        """

        entry = self._require_handle(handle)
        _safe_id(reason_ref, code=RUNTIME_ARSD_INVALID_REQUEST)
        with self._task_locks.hold(entry.task_id):
            self._require_no_unresolved_intent(entry.task_id)
            with self._lock:
                run_id = entry.active_run_id
                confirmed = entry.cancel_confirmed
            if confirmed:
                return "cancelled"
            if run_id is None:
                return self._end_task(entry)

            try:
                raw = self._facade.run_cancel(run_id)
            except SpineError:
                raise
            except Exception:
                _unavailable()
            observation = validate_arsd_run_cancel_result(raw, run_id=run_id)
            if observation.status is not None:
                return self._end_task(
                    entry,
                    run_status=map_arsd_terminal_to_neutral(
                        observation.status, reason=self._reason_of(observation.result)
                    ),
                )

            # No trusted evidence yet: re-query within Sachima's own bounded
            # policy, and otherwise say so.
            for _ in range(_CANCEL_REQUERIES):
                requery = self._observe(run_id)
                if requery.result is not None:
                    neutral = _trusted_terminal(requery.result)
                    if neutral is None:
                        raise SpineError(RUNTIME_ARSD_INTERNAL) from None
                    return self._end_task(entry, run_status=neutral)
            return "ambiguous"

    # -- turn surface ------------------------------------------------------- #
    def run_turn(
        self,
        task_id: str,
        *,
        turn_kind: str,
        payload_text: str,
        dispatch_ref: str,
        payload_ref: str,
        session_ref: str,
    ) -> DispatchedSupervisorTurn:
        """Submit one turn, once, and return on durable acceptance.

        The sequence is fixed: exclude an unresolved intent and an unfinished
        Run, resolve the Session, negotiate ``server_info`` afresh for this
        **new** admission, build the frozen payload and its digest, pre-check
        the admission product against **that** negotiation's budget, land the
        pending intent on disk, and only then submit. The ack finalizes that
        same record in place.

        The whole sequence runs under this task's admission lock, so two
        concurrent dispatches produce one ledger record and one submit: the
        second finds the first's Run and fails closed rather than starting a
        Run beside it.

        ``payload_text`` is private wire material: it is handed to the facade
        and never stored, echoed, or carried on the result. The three refs are
        this dispatch's whole identity and are all **required**: ``payload_ref``
        is the claim-check handle a recovery rebuilds the identical prompt from,
        ``dispatch_ref`` is the durable binding key, and ``session_ref`` is the
        canonical Sachima Session the turn belongs to. All three are validated
        here — before the ledger is written and before the daemon is touched —
        and all three are persisted, so a later recovery can prove it is a
        recovery of *this* dispatch and not of some other one.
        """

        entry = self._require_task(task_id)
        dispatch = _safe_id(dispatch_ref, code=RUNTIME_ARSD_INVALID_REQUEST)
        # A dispatch that cannot name its prompt or its Session cannot be
        # recovered, so it is refused at the boundary rather than admitted into
        # an unrecoverable state.
        prompt_ref = _safe_id(payload_ref, code=RUNTIME_ARSD_INVALID_REQUEST)
        session = _safe_id(session_ref, code=RUNTIME_ARSD_INVALID_REQUEST)
        kind = self._turn_kind(turn_kind)
        prompt = self._prompt_text(payload_text)

        # One admission at a time for this task. Everything from the two
        # exclusions through the finalize runs under it, so a concurrent
        # dispatch cannot slip between "no active Run" and the record that
        # creates one.
        with self._task_locks.hold(entry.task_id):
            with self._lock:
                policy = entry.policy

            # An uncertain submission blocks this task's next Run, before any
            # socket call: the ordinary path may neither resend that dispatch
            # nor start a second Run alongside a Run the daemon may already
            # hold.
            self._require_no_unresolved_intent(entry.task_id)
            # And an accepted Run that is not *proven* over blocks it too
            # (Spec §7.4). This is the only place that answer is derived, and
            # it is derived before anything durable is written.
            self._require_no_active_run(entry)
            ars_session_id = self._reusable_session(entry.task_id)
            info = self._negotiate()
            payload = self._build_payload(
                policy, prompt=prompt, ars_session_id=ars_session_id
            )
            digest = arsd_submit_payload_digest(payload)
            # A run-limits choice this daemon would refuse fails closed here,
            # before a submit is spent on learning it (Spec §5.6.2).
            check_arsd_admission_event_budget(
                payload["request"]["limits"],
                max_run_event_budget_bytes=info.max_run_event_budget_bytes,
            )

            request_id = derive_arsd_request_id(entry.task_id, entry.handle, dispatch)
            self._ledger.begin_pending(
                entry.task_id,
                entry.handle,
                dispatch,
                request_id=request_id,
                payload_digest=digest,
                resolver_refs=self._resolver_refs(
                    policy,
                    turn_kind=kind,
                    ars_session_id=ars_session_id,
                    prompt=prompt,
                    prompt_ref=prompt_ref,
                    session_ref=session,
                ),
            )
            ack = self._submit(request_id, payload)
            return self._finalize(
                entry, dispatch, ack, expected_session_id=ars_session_id
            )

    def latest_accepted_turn(
        self, task_id: str, *, session_ref: str
    ) -> DispatchedSupervisorTurn | None:
        """The durable handoff for this task's latest accepted Run, or ``None``.

        A **ledger read and nothing else**: no submit, no daemon operation, no
        state fabricated. It is what a restart rebinds a read-model source
        from — the safe refs on one half, the private ``run_id`` on the other,
        exactly as an acceptance would have handed them over.

        While an unresolved intent exists it fails closed for the same reason
        observation does: the uncertain submit may already hold a newer Run, so
        the latest *accepted* one is not known to be this task's current Run
        and binding its stream would show the wrong one (Spec §7.3.1).
        """

        entry = self._require_task(task_id)
        session = _safe_id(session_ref, code=RUNTIME_ARSD_INVALID_REQUEST)
        with self._task_locks.hold(entry.task_id):
            self._require_no_unresolved_intent(entry.task_id)
            latest = self._latest_accepted(entry.task_id)
            if latest is None or latest.run_id is None or latest.run_ref is None:
                return None
            # The Run has to belong to the Session the caller is rebinding. A
            # Run attached to a conversation it never ran in is worse than no
            # binding at all, so a mismatch fails closed rather than binding.
            if dict(latest.resolver_refs).get("session_ref") != session:
                _binding_conflict()
            return self._accepted_handoff(latest)

    @staticmethod
    def _accepted_handoff(latest: ArsdRunBinding) -> DispatchedSupervisorTurn:
        # ``run_ref``/``run_id`` are optional on the record because a pending
        # one has neither; on an accepted one both are required, and the
        # ledger re-validates that on every read. They are bound here rather
        # than narrowed away, so a record that somehow reached this point
        # without them fails closed on the binding-conflict code instead of
        # producing a handoff that names no Run.
        run_ref = latest.run_ref
        run_id = latest.run_id
        if type(run_ref) is not str or type(run_id) is not str:  # pragma: no cover
            _binding_conflict()
        return DispatchedSupervisorTurn(
            result=SupervisorTurnResult(
                run_ref=run_ref,
                source_kind=SOURCE_KIND_ARSD_RUN,
                source_ref=run_ref,
                # A durable acceptance is what the ledger recorded; terminal
                # truth is observation's job, not a rebind's.
                supervisor_status="accepted",
                # A rebound stream is read from its start: the cursor a caller
                # had advanced belonged to a process that is gone.
                foreign_cursor=None,
            ),
            private_locator=run_id,
        )

    def recover_uncertain_submission(
        self, task_id: str, dispatch_ref: str, *, session_ref: str, turn_kind: str
    ) -> DispatchedSupervisorTurn:
        """Explicitly recover one uncertain submission — never automatic.

        Reads the pending intent, rebuilds its payload through the **same**
        resolver from its own refs, and fails closed with
        ``runtime_arsd_binding_conflict`` and **zero** socket calls when the
        rebuilt digest differs from the recorded one, because byte-equivalence
        can no longer be proven. On a match it resends the identical
        ``request_id`` with the byte-equivalent frozen payload — no
        negotiation, no current-budget pre-check, no re-tuning to a changed
        budget — and the resulting durable ack finalizes that same intent
        exactly once (Spec §7.3.1, §5.6.2, Δ-12).
        """

        entry = self._require_task(task_id)
        dispatch = _safe_id(dispatch_ref, code=RUNTIME_ARSD_INVALID_REQUEST)
        session = _safe_id(session_ref, code=RUNTIME_ARSD_INVALID_REQUEST)
        kind = self._turn_kind(turn_kind)
        # Under the same task operation lock as ``run_turn``: a recovery
        # resolves the very intent that blocks new admissions, so the two must
        # not interleave.
        with self._task_locks.hold(entry.task_id):
            intent = self._ledger.resolve_pending(entry.task_id, entry.handle, dispatch)
            if intent is None:
                # Nothing pending: there is no uncertain submission to recover,
                # and an accepted record is never re-sent.
                _binding_conflict()
            # Identity first, before the resolver runs and before the daemon is
            # touched: a resend under another Session or another turn kind is
            # not a recovery of this dispatch, whatever it does to the digest.
            self._require_recorded_identity(intent, session_ref=session, turn_kind=kind)

            payload = self._rebuild_payload(entry.task_id, intent)
            if arsd_submit_payload_digest(payload) != intent.payload_digest:
                _binding_conflict()

            ack = self._submit(intent.request_id, payload)
            # The frozen payload states what this recovery asked for; the ack
            # must answer about that same Session.
            return self._finalize(
                entry,
                dispatch,
                ack,
                expected_session_id=payload["request"].get("session_id"),
            )

    @staticmethod
    def _require_recorded_identity(
        intent: ArsdRunBinding, *, session_ref: str, turn_kind: str
    ) -> None:
        """Refuse a recovery that is not of the dispatch it names.

        A recovery resends a frozen request under its original ``request_id``,
        so it has to *be* the original request: the same canonical Session and
        the same kind of turn. Presenting another is refused here — before the
        resolver is called, before any socket call, and before anything is
        bound — because the point at which a mismatch is cheap to catch is
        before it has cost anything.

        A record written before this identity existed cannot be checked, so it
        is refused too rather than waved through.
        """

        recorded = dict(intent.resolver_refs)
        if recorded.get("session_ref") != session_ref:
            _binding_conflict()
        if recorded.get("turn_kind") != turn_kind:
            _binding_conflict()

    # -- internals: identity and policy ------------------------------------- #
    def _register(
        self,
        safe_task: str,
        handle: str,
        policy: _RunPolicy,
        *,
        active_binding: ArsdRunBinding | None = None,
    ) -> str:
        """Reconcile against this task's durable records, then track it.

        Two things happen here that a fresh process cannot skip. Its stable
        identity is reconciled against what the ledger says every record of
        this task was admitted under, so a restart can never re-bind a live
        conversation to a different workspace, agent, or grant. And an empty
        in-memory entry is not treated as evidence that the task has no Run:
        the latest accepted binding's ``run_id`` is adopted as the active Run,
        so ``status`` asks the daemon about *that* Run and ``kill`` cancels it
        (Spec §7.3 rule 2). ``cancel_confirmed`` is deliberately not restored:
        an unproven cancel is re-observed, never remembered.
        """

        bindings = self._ledger.resolve_for_task(safe_task)
        self._reconcile_durable_identity(policy, bindings)
        entry = _TaskEntry(task_id=safe_task, handle=handle, policy=policy)
        # A caller that named the record adopts THAT Run; only a caller that did
        # not asks the ledger which one is newest.
        adopted = (
            active_binding
            if active_binding is not None
            else self._select_latest_accepted(bindings)
        )
        if adopted is not None:
            entry.active_run_id = adopted.run_id
        self._by_task[safe_task] = entry
        self._by_handle[handle] = entry
        return handle

    def _reconcile_durable_identity(
        self, policy: _RunPolicy, bindings: tuple[ArsdRunBinding, ...]
    ) -> None:
        """Refuse a stable-identity change against ANY durable record.

        The stable identity is the workspace, the agent, and the frozen grant:
        change one and this is a different conversation, whatever the ledger
        says the task is bound to. Sachima declares no profile source — the
        agent policy ref is the only agent-facing choice it makes (Spec
        §10.6.1, §12.4) — so that ref *is* the agent/profile identity here.
        Model, effort, and run-limits refs are deliberately absent: those are
        per-Run choices, re-resolved on every submit (Spec §5.5.4).

        Both record states are checked. A pending intent states the identity
        its uncertain submission was admitted under just as an accepted
        binding does, so a restart under a changed identity fails here rather
        than at the explicit recovery that would otherwise resend under it.
        A record that cannot state its identity is not reconcilable and is
        refused too.
        """

        current = {
            "workspace_ref": policy.workspace_ref,
            "agent_policy_ref": policy.agent_policy_ref,
            "grant_ref": self._config.grant_ref,
            "grant_hash": self._config.grant_hash,
            "grant_role_hash": self._config.grant_role_hash,
            "grant_capabilities_digest": _capabilities_digest(
                self._config.grant_capabilities
            ),
        }
        for binding in bindings:
            recorded = dict(binding.resolver_refs)
            for key, value in current.items():
                if recorded.get(key) != value:
                    _policy_denied()

    def _latest_accepted(self, safe_task: str) -> ArsdRunBinding | None:
        return self._select_latest_accepted(self._ledger.resolve_for_task(safe_task))

    @staticmethod
    def _select_latest_accepted(
        bindings: tuple[ArsdRunBinding, ...],
    ) -> ArsdRunBinding | None:
        """This task's most recently accepted binding, or ``None``.

        Ordered **only** by the daemon's own ``accepted_at`` instant — the one
        statement about time either side made. There is deliberately no
        tiebreak: the ledger key is a lexical accident, not a chronology, and
        breaking a tie with it would not merely be arbitrary, it would pick a
        Run to observe and cancel on the strength of how its dispatch ref
        happens to sort. Two acceptances sharing the newest instant are
        therefore irreconcilable, and Sachima says so instead of guessing.
        """

        accepted = [
            binding
            for binding in bindings
            if binding.state == ARSD_BINDING_ACCEPTED and binding.run_id is not None
        ]
        if not accepted:
            return None
        newest_instant = max(_acceptance_instant(binding) for binding in accepted)
        newest = [
            binding
            for binding in accepted
            if _acceptance_instant(binding) == newest_instant
        ]
        if len(newest) != 1:
            _binding_conflict()
        return newest[0]

    def _require_task(self, task_id: Any) -> _TaskEntry:
        safe_task = safe_task_id(task_id, code=RUNTIME_ARSD_INVALID_REQUEST)
        with self._lock:
            entry = self._by_task.get(safe_task)
        if entry is None:
            raise SpineError(RUNTIME_INVALID_SESSION)
        return entry

    def _require_handle(self, handle: Any) -> _TaskEntry:
        safe_handle = _safe_id(handle, code=RUNTIME_ARSD_INVALID_REQUEST)
        with self._lock:
            entry = self._by_handle.get(safe_handle)
        if entry is None:
            raise SpineError(RUNTIME_INVALID_SESSION)
        return entry

    def _resolve_refs(self, refs: Any) -> _RunPolicy:
        if not isinstance(refs, (list, tuple)):
            _invalid_request()
        safe_refs = tuple(
            _safe_id(ref, code=RUNTIME_ARSD_INVALID_REQUEST) for ref in refs
        )
        return _RunPolicy(
            workspace_ref=self._exactly_one(safe_refs, self._config.workspace_by_ref),
            agent_policy_ref=self._exactly_one(
                safe_refs, self._config.agent_by_policy_ref
            ),
            model_policy_ref=self._exactly_one(
                safe_refs, self._config.model_by_policy_ref
            ),
            effort_policy_ref=self._exactly_one(
                safe_refs, self._config.effort_by_policy_ref
            ),
            run_limits_policy_ref=self._exactly_one(
                safe_refs, self._config.run_limits_by_policy_ref
            ),
        )

    @staticmethod
    def _exactly_one(safe_refs: tuple[str, ...], mapping: Mapping[str, Any]) -> str:
        matches = [ref for ref in safe_refs if ref in mapping]
        if len(matches) != 1:
            _policy_denied()
        return matches[0]

    def _policy_from_refs(self, resolver_refs: Mapping[str, str]) -> _RunPolicy:
        try:
            policy = _RunPolicy(
                workspace_ref=resolver_refs["workspace_ref"],
                agent_policy_ref=resolver_refs["agent_policy_ref"],
                model_policy_ref=resolver_refs["model_policy_ref"],
                effort_policy_ref=resolver_refs["effort_policy_ref"],
                run_limits_policy_ref=resolver_refs["run_limits_policy_ref"],
            )
        except KeyError:
            _binding_conflict()
        for ref, mapping in (
            (policy.workspace_ref, self._config.workspace_by_ref),
            (policy.agent_policy_ref, self._config.agent_by_policy_ref),
            (policy.model_policy_ref, self._config.model_by_policy_ref),
            (policy.effort_policy_ref, self._config.effort_by_policy_ref),
            (policy.run_limits_policy_ref, self._config.run_limits_by_policy_ref),
        ):
            if ref not in mapping:
                _invalid_request()
        return policy

    @staticmethod
    def _turn_kind(value: Any) -> str:
        if type(value) is not str or value not in _TURN_KINDS:
            _invalid_request()
        return value

    @staticmethod
    def _prompt_text(value: Any) -> str:
        # Bounds and encoding are the request builder's job; emptiness is a
        # caller error worth naming here.
        if type(value) is not str or not value.strip():
            _invalid_request()
        return value

    def _resolver_refs(
        self,
        policy: _RunPolicy,
        *,
        turn_kind: str,
        ars_session_id: str | None,
        prompt: str,
        prompt_ref: str,
        session_ref: str,
    ) -> dict[str, str]:
        """The refs a recovery rebuilds — and re-identifies — this payload from.

        Refs and digests only: no prompt body, no ARS Session id (which the
        recovery reads from the durable binding), and nothing a rebuild does
        not need. ``prompt_ref``, ``session_ref`` and ``turn_kind`` are written
        unconditionally: they are what makes a later resend provably the same
        request rather than a new one wearing its ``request_id``.
        """

        refs = {
            "workspace_ref": policy.workspace_ref,
            "agent_policy_ref": policy.agent_policy_ref,
            "model_policy_ref": policy.model_policy_ref,
            "effort_policy_ref": policy.effort_policy_ref,
            "run_limits_policy_ref": policy.run_limits_policy_ref,
            # The grant this dispatch was admitted under (Spec §7.3.1). It is
            # host config rather than a caller ref, so the record is the only
            # thing that can prove a later process still carries the same one.
            "grant_ref": self._config.grant_ref,
            "grant_hash": self._config.grant_hash,
            "grant_role_hash": self._config.grant_role_hash,
            "grant_capabilities_digest": _capabilities_digest(
                self._config.grant_capabilities
            ),
            "turn_kind": turn_kind,
            # The canonical Sachima Session this turn belongs to. A recovery
            # that names another Session is not a recovery of this dispatch.
            "session_ref": session_ref,
            "session_mode": (
                _SESSION_MODE_CREATE if ars_session_id is None else _SESSION_MODE_REUSE
            ),
            "prompt_digest": _prompt_digest(prompt),
            "prompt_ref": prompt_ref,
        }
        return refs

    def _build_payload(
        self, policy: _RunPolicy, *, prompt: str, ars_session_id: str | None
    ) -> dict[str, Any]:
        """The exact submit payload for one Run.

        ``requested_model`` / ``requested_effort`` are re-resolved from the
        policy maps here, on every Run: they are properties of the Run, never
        of the Session, and nothing observed from a past Run feeds back in.
        """

        session_kwargs: dict[str, Any] = (
            {} if ars_session_id is None else {"session_id": ars_session_id}
        )
        return build_arsd_submit_payload(
            self._config,
            agent_policy_ref=policy.agent_policy_ref,
            model_policy_ref=policy.model_policy_ref,
            effort_policy_ref=policy.effort_policy_ref,
            workspace_ref=policy.workspace_ref,
            run_limits_policy_ref=policy.run_limits_policy_ref,
            prompt_text=prompt,
            **session_kwargs,
        )

    def _rebuild_payload(self, safe_task: str, intent: ArsdRunBinding) -> dict[str, Any]:
        refs = dict(intent.resolver_refs)
        if self._prompt_resolver is None:
            _binding_conflict()
        try:
            prompt = self._prompt_resolver(dict(refs))
        except Exception:
            _binding_conflict()
        if type(prompt) is not str or not prompt:
            _binding_conflict()

        ars_session_id = None
        if refs.get("session_mode") == _SESSION_MODE_REUSE:
            ars_session_id = self._recorded_session(safe_task)
            if ars_session_id is None:
                _binding_conflict()
        try:
            return self._build_payload(
                self._policy_from_refs(refs),
                prompt=prompt,
                ars_session_id=ars_session_id,
            )
        except SpineError:
            _binding_conflict()

    # -- internals: daemon operations --------------------------------------- #
    def _negotiate(self) -> ArsdServerInfo:
        try:
            raw = self._facade.server_info()
        except SpineError:
            raise
        except Exception:
            _unavailable()
        info = validate_arsd_server_info(raw, config=self._config)
        # Retained only after it validated: a failed negotiation must leave the
        # previously proven answer standing rather than half-replace it.
        self._server_info = info
        return info

    def _require_no_unresolved_intent(self, safe_task: str) -> None:
        """Refuse while any dispatch of this task is still uncertain.

        One rule for every path that would otherwise act on the task: a new
        admission may not be submitted, and the recorded Run may not be
        observed or cancelled, because an uncertain submit may already hold a
        Run this process cannot name. Only the explicit recovery entry point
        reads a pending intent, and only it may resolve one (Spec §7.3.1).
        """

        for binding in self._ledger.resolve_for_task(safe_task):
            if binding.state != ARSD_BINDING_ACCEPTED:
                _binding_conflict()

    def _require_no_active_run(self, entry: _TaskEntry) -> None:
        """At most one **active** Run per task/Session (Spec §7.4).

        A second dispatch may only be admitted once this task's recorded Run is
        known to be over, and "known" means trusted terminal evidence. Every
        other answer refuses:

        * a Run with no terminal yet is simply still running, so admitting a
          second one would put two Runs on one Session — the state Spec §7.4
          forbids and the state a reader would silently misattribute;
        * an observation that fails is not evidence that the Run ended. Sachima
          did not observe, so it does not know, and not knowing is not a
          licence to start another Run (Spec §10.2);
        * a body that carries no readable status is evidence it cannot trust,
          and untrusted evidence is contained rather than read as "probably
          finished".

        A terminal, on the other hand, admits: the exclusion bounds how many
        Runs may be live at once, not how many turns a conversation may have.
        The refusal happens **before** ``begin_pending`` and before any submit,
        so a blocked dispatch writes no second pending intent and spends no
        admission. The first dispatch of a task has no recorded Run and reaches
        the daemon for nothing here.
        """

        with self._lock:
            if entry.cancel_confirmed:
                # An explicitly cancelled task has no Session to dispatch into;
                # a new Run would silently resurrect work an upper layer ended.
                raise SpineError(RUNTIME_INVALID_SESSION)
        if self._reconcile_active_run(entry) == "accepted":
            _binding_conflict()

    def _recorded_session(self, safe_task: str) -> str | None:
        """The ARS Session this task is bound to, from the durable ledger.

        Deliberately independent of Run ordering: the ledger already refuses
        to record a second Session for a task, so every accepted binding names
        the same one. Which Run is *current* can be ambiguous (see
        :meth:`_select_latest_accepted`); which Session to reuse cannot be.
        """

        for binding in self._ledger.resolve_for_task(safe_task):
            if binding.state == ARSD_BINDING_ACCEPTED and binding.ars_session_id:
                return binding.ars_session_id
        return None

    def _reusable_session(self, safe_task: str) -> str | None:
        """The recorded Session id to reuse, or ``None`` to create one.

        A quarantined or unknown Session is never auto-healed, auto-recreated,
        or retried into: the turn fails closed and no new Session is started in
        its place (Spec §10.5).
        """

        recorded = self._recorded_session(safe_task)
        if recorded is None:
            return None
        try:
            raw = self._facade.session_status(recorded)
        except SpineError:
            raise
        except Exception:
            _unavailable()
        view = validate_arsd_session_view(raw)
        if view.session_id != recorded:
            raise SpineError(RUNTIME_ARSD_PROTOCOL_VIOLATION) from None
        if not view.is_reusable:
            _policy_denied()
        # ``last_effective_model`` / ``last_effective_effort`` are observations
        # of that Session's last Run. They are deliberately read for nothing:
        # the next Run re-resolves its own pair from the policy maps.
        return recorded

    def _submit(self, request_id: str, payload: Mapping[str, Any]) -> ArsdSubmitAccepted:
        """One submit. A lost reply is indeterminate, never retried here."""

        try:
            raw = self._facade.submit(request_id=request_id, payload=payload)
        except SpineError:
            # A daemon-declared verdict is already a stable code.
            raise
        except Exception:
            # The frame may have reached the daemon with its reply unread: the
            # outcome is unknown, the intent stays exactly as written, and no
            # automatic path replays it (Spec §10.3).
            raise SpineError(RUNTIME_ARSD_SUBMISSION_INDETERMINATE) from None
        return validate_arsd_submit_result(raw)

    def _observe(self, run_id: str) -> ArsdRunStatusObservation:
        try:
            raw = self._facade.run_status(run_id)
        except SpineError:
            raise
        except Exception:
            _unavailable()
        return validate_arsd_run_status(raw, run_id=run_id)

    # -- internals: projection ---------------------------------------------- #
    @staticmethod
    def _reason_of(result: Any) -> Any:
        if not isinstance(result, Mapping):
            return None
        return result.get(_TERMINAL_REASON_KEY)

    def _reconcile_active_run(self, entry: _TaskEntry) -> str | None:
        """Settle what is known about this task's Run, and remember it.

        Returns the neutral Run status — ``accepted`` while it is still going,
        one of the five terminals once trusted evidence says it ended — or
        ``None`` for a task that has dispatched nothing.

        A terminal clears the active Run: a Run that ended is not this task's
        current work any more, so it stops blocking the next admission and
        stops being what an observation is about. What this deliberately does
        **not** do is touch the Session. Spec §7.4 bounds concurrent *Runs*,
        and Spec §6 gives Sessions no close operation, so a finished Run leaves
        a live Session behind and the next turn passes its recorded id
        verbatim.

        Uncertainty is not settlement: an observation that failed propagates
        its transient code, and a body carrying no readable status is contained
        as an internal failure. Neither is read as "probably over".
        """

        with self._lock:
            run_id = entry.active_run_id
            remembered = entry.last_run_status
        if run_id is None:
            # Nothing live. A remembered verdict is returned rather than
            # re-asked for: the daemon may already have forgotten that Run.
            return remembered
        observation = self._observe(run_id)
        if observation.result is None:
            # Accepted, or progress with no terminal: the Run is still going.
            return "accepted"
        neutral = _trusted_terminal(observation.result)
        if neutral is None:
            # Evidence we cannot trust is a contained internal failure — never
            # a fabricated terminal, and never confused with observation loss.
            raise SpineError(RUNTIME_ARSD_INTERNAL) from None
        # Projected from the *neutral* terminal, so a PERMISSION_VIOLATION Run
        # reported ``completed`` stays ``failed`` on the answer as well as on
        # the status.
        projected = project_arsd_terminal_result(observation.result, status=neutral)
        with self._lock:
            if entry.active_run_id == run_id:
                entry.active_run_id = None
                entry.last_run_status = neutral
                entry.last_terminal_result = projected
        return neutral

    def _end_task(self, entry: _TaskEntry, *, run_status: str | None = None) -> str:
        """Terminalize the task on the explicit cancel path — and only there.

        This is the one place a task becomes terminal, because it is the one
        place an upper layer asked for it. The Run's own terminal is remembered
        rather than published as the task's state: ``kill`` answers about the
        task it was told to end, never about what the Run happened to finish
        as. That verdict stays readable on :meth:`observe_run`.
        """

        with self._lock:
            entry.cancel_confirmed = True
            entry.active_run_id = None
            if run_status is not None:
                entry.last_run_status = run_status
        return "cancelled"

    def _finalize(
        self,
        entry: _TaskEntry,
        dispatch: str,
        ack: ArsdSubmitAccepted,
        *,
        expected_session_id: str | None,
    ) -> DispatchedSupervisorTurn:
        """Correlate the ack, then promote the intent in place.

        When the request named a Session, the ack must name the same one: a
        reply about some other Session is not an answer to what was asked, and
        binding it would silently move the task's conversation. That is a
        protocol violation, raised **before** any ledger write, so the pending
        intent is left exactly as written for an explicit decision. A create
        request named none, so the Session the ack reports is the answer and
        there is nothing to correlate (Spec §6.3).
        """

        if expected_session_id is not None and ack.session_id != expected_session_id:
            raise SpineError(RUNTIME_ARSD_PROTOCOL_VIOLATION) from None

        binding = self._ledger.finalize_accepted(
            entry.task_id,
            entry.handle,
            dispatch,
            run_id=ack.run_id,
            ars_session_id=ack.session_id,
            accepted_at=ack.accepted_at,
        )
        with self._lock:
            entry.active_run_id = ack.run_id
            entry.last_run_status = None
            # A new Run's answer is not the previous Run's: the remembered
            # terminal goes with the verdict it belonged to.
            entry.last_terminal_result = None
            entry.cancel_confirmed = False
        run_ref = binding.run_ref
        if run_ref is None:  # pragma: no cover - an accepted record always has one
            _binding_conflict()
        return DispatchedSupervisorTurn(
            result=SupervisorTurnResult(
                run_ref=run_ref,
                source_kind=SOURCE_KIND_ARSD_RUN,
                source_ref=run_ref,
                # A durable acceptance, not a terminal: terminal truth arrives
                # later through status observation (Spec §8.3).
                supervisor_status="accepted",
                # A fresh Run is a fresh read-model stream.
                foreign_cursor=None,
            ),
            private_locator=ack.run_id,
        )


def _acceptance_instant(binding: ArsdRunBinding) -> _dt.datetime:
    """The instant the daemon said it accepted this Run.

    Timezone-aware by the ledger's own validation, so instants from different
    offsets compare correctly.
    """

    try:
        return _dt.datetime.fromisoformat(str(binding.accepted_at))
    except (TypeError, ValueError):  # pragma: no cover - validated on write/read
        _binding_conflict()


def _capabilities_digest(capabilities: Any) -> str:
    """A stable digest of the frozen grant's capability set.

    Recorded so a later process can prove the grant identity is unchanged
    without the record carrying the capability list itself.
    """

    material = json.dumps(sorted(str(item) for item in capabilities), separators=(",", ":"))
    return _safe_digest(
        "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest(),
        code=RUNTIME_ARSD_INVALID_REQUEST,
    )


def _prompt_digest(prompt: str) -> str:
    """The recorded witness of the prompt — never the prompt body itself."""

    return _safe_digest(
        "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        code=RUNTIME_ARSD_INVALID_REQUEST,
    )
