"""Sachima delegation — the one coordinator that owns a delegated task's life.

This module is the single writer of delegate turn lifecycle and cancellation
state. Everything above it (the gated control tool Hermes reaches through) asks
it questions; everything below it (the durable store, the binding ledger, the
composed ``arsd`` bundle) answers them. There is deliberately no second
coordinator, registry, backend, port, dispatcher, or bindings store beside the
one the host already composed.

Which AGENT a task runs under is settled before any of that, by
:meth:`SachimaDelegateCoordinator.admit_agent`: the live ARS roster intersected
with this host's execution presets, and nothing else. There is no fallback
AGENT, no candidate ranking, and no name matching here — Hermes chose the
canonical ``agent_id`` upstream, and this layer only says yes or no to it.

The four rules that shape every method here:

**Evidence decides, not return codes.** Every dispatch or recovery outcome —
success-shaped, failure-shaped, or an exception — is reduced to a stable
diagnostic and then passed through *one* exact-key ledger snapshot. That
snapshot picks the disposition. A success-shaped outcome with no ledger record
is a failed admission; an exception with an accepted record is an accepted Run
whose reply was lost. Reading the return value instead would clean up durable
Runs and re-submit accepted ones.

**One critical section per turn.** A keyed lock opens before the first
reconciliation and closes after the observer is armed, covering the durable
commit, the receipt, and everything between. The section runs in a
coordinator-owned task that waiters join through cancellation shielding: an IM
caller that gives up cannot cancel the spine work it started or release the
exclusion that is supposed to cover it.

**Identity before any possible submit.** Payload, task binding, turn record, and
the exact ledger key are on disk before anything that could reach the daemon. A
record with no submit is recoverable; a submit with no record is not.

**Capacity is conservative.** One permit per turn that might still be consuming
a Run — pending, accepted, or unreadable — released exactly once, and only when
an exact snapshot proves there is no record or a trusted terminal has produced
its durable result. Observation loss, delivery failure, an uncertain cancel, and
a caller's timeout release nothing.

Pure local/offline on import: no process, socket, daemon, Gateway, IM surface,
or AGENT is started here, and no ``agent_run_supervisor`` import happens at any
level — the daemon is reached only through the composed bundle's own lazy
facade. Forbidden terms in this prose are no-leak boundary canaries only, never
behavior.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping

from gateway.sachima_agent_role_policy import (
    AgentRolePolicy,
    AgentRoleSelection,
    build_agent_eligibility_view,
    empty_agent_role_policy,
    select_agent_by_role,
)
from gateway.sachima_agent_execution_presets import (
    SACHIMA_AGENT_NO_PRESET,
    SACHIMA_AGENT_ROSTER_UNAVAILABLE,
    AgentAdmission,
    AgentExecutionPreset,
    AgentExecutionPresets,
    admit_agent_execution,
    empty_agent_execution_presets,
    requested_configuration,
)
from gateway.sachima_delegate_result import (
    UNCERTAIN_SETTLEMENT,
    DelegateAcceptedReceipt,
    SendSettlement,
    build_hermes_context,
    build_result_envelope,
    perform_settled_send,
    projected_summary_text,
    render_accepted_receipt,
    render_result_body,
)
from gateway.sachima_delegate_summary import (
    SUMMARY_PROVIDER_TIMEOUT_SECONDS,
    SUMMARY_REASON_ATTEMPT_ABANDONED,
    SUMMARY_REASON_SOURCE_DRIFT,
    SUMMARY_REASON_SOURCE_MISSING,
    SUMMARY_REASON_SUMMARY_FAILED,
    DelegateResultSummary,
    DelegateResultSummaryProvider,
    DelegateSummaryError,
    build_summary_request,
    compute_source_digest,
    pending_summary,
    sanitize_task_description,
    settle_summary_attempt,
    source_gate_reason,
    unavailable_summary,
)
from gateway.sachima_delegate_card import (
    CARD_ROUND_WINDOW,
    DelegateCardError,
    DelegateCardProjection,
    advance_round,
    append_round,
    bind_card_message,
    bounded_card_payload,
    derive_session_ref,
    new_card_projection,
    next_projection_revision,
    normalize_running_patch_interval,
    project_session_evidence,
    projected_revision,
    render_delegation_markdown,
    safe_card_instant,
    sanitize_card_line,
    settle_card_sink,
)
from gateway.sachima_delegate_state import (
    DelegateCapacity,
    DelegateOrigin,
    DelegateResultEvent,
    DelegateStateError,
    DelegateStateStore,
    DelegateTaskBinding,
    DelegateTurnRecord,
    delegate_state_root,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DELEGATE_ACCEPTED_TEMPLATE",
    "DELEGATE_BLOCKED_TEMPLATE",
    "DELEGATE_SUBMIT_FAILED_TEMPLATE",
    "DELEGATE_WAITING_TEMPLATE",
    "SACHIMA_AGENT_NO_PRESET",
    "SACHIMA_DELEGATE_BLOCKED",
    "SACHIMA_DELEGATE_CARD_PATCH_INTERVAL_ENV",
    "SACHIMA_DELEGATE_CARD_UNAVAILABLE",
    "SACHIMA_DELEGATE_DISPATCH_FAILED",
    "SACHIMA_DELEGATE_INVALID_TARGET",
    "SACHIMA_DELEGATE_INVALID_TASK_TEXT",
    "SACHIMA_DELEGATE_NO_DELIVERY",
    "SACHIMA_DELEGATE_NOT_CONTINUABLE",
    "SACHIMA_DELEGATE_OBSERVATION_LOST",
    "SACHIMA_DELEGATE_RECOVERY_REQUIRED",
    "SACHIMA_DELEGATE_STABLE_CODES",
    "SACHIMA_DELEGATE_SUMMARY_UNAVAILABLE",
    "SACHIMA_DELEGATE_UNBOUND",
    "SACHIMA_DELEGATE_UNKNOWN_PAYLOAD_REF",
    "SACHIMA_DELEGATE_UNKNOWN_TASK",
    "DelegateDelivery",
    "DelegateOutcome",
    "SachimaDelegateCoordinator",
    "bind_delegate_coordinator",
    "bound_delegate_coordinator",
    "configured_running_patch_interval",
    "delegate_payload_resolver",
    "unbind_delegate_coordinator",
]

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
SACHIMA_DELEGATE_UNBOUND = "sachima_delegate_unbound"
SACHIMA_DELEGATE_UNKNOWN_PAYLOAD_REF = "sachima_delegate_unknown_payload_ref"
SACHIMA_DELEGATE_INVALID_TASK_TEXT = "sachima_delegate_invalid_task_text"
SACHIMA_DELEGATE_INVALID_TARGET = "sachima_delegate_invalid_target"
SACHIMA_DELEGATE_DISPATCH_FAILED = "sachima_delegate_dispatch_failed"
SACHIMA_DELEGATE_OBSERVATION_LOST = "sachima_delegate_observation_lost"
SACHIMA_DELEGATE_BLOCKED = "sachima_delegate_blocked"
SACHIMA_DELEGATE_RECOVERY_REQUIRED = "sachima_delegate_recovery_required"
SACHIMA_DELEGATE_UNKNOWN_TASK = "sachima_delegate_unknown_task"
SACHIMA_DELEGATE_NOT_CONTINUABLE = "sachima_delegate_not_continuable"
SACHIMA_DELEGATE_NO_DELIVERY = "sachima_delegate_no_delivery"
SACHIMA_DELEGATE_INVARIANT = "sachima_delegate_invariant"
SACHIMA_DELEGATE_SUMMARY_UNAVAILABLE = "sachima_delegate_summary_unavailable"
SACHIMA_DELEGATE_CARD_UNAVAILABLE = "sachima_delegate_card_unavailable"

SACHIMA_DELEGATE_STABLE_CODES = frozenset(
    {
        SACHIMA_DELEGATE_UNBOUND,
        SACHIMA_DELEGATE_UNKNOWN_PAYLOAD_REF,
        SACHIMA_DELEGATE_INVALID_TASK_TEXT,
        SACHIMA_DELEGATE_INVALID_TARGET,
        # Owned by the execution-preset module, but reachable from here: a
        # continuation whose sealed AGENT has no preset any more says so with
        # the same code admission would have used.
        SACHIMA_AGENT_NO_PRESET,
        SACHIMA_DELEGATE_DISPATCH_FAILED,
        SACHIMA_DELEGATE_OBSERVATION_LOST,
        SACHIMA_DELEGATE_BLOCKED,
        SACHIMA_DELEGATE_RECOVERY_REQUIRED,
        SACHIMA_DELEGATE_UNKNOWN_TASK,
        SACHIMA_DELEGATE_NOT_CONTINUABLE,
        SACHIMA_DELEGATE_NO_DELIVERY,
        SACHIMA_DELEGATE_INVARIANT,
        SACHIMA_DELEGATE_SUMMARY_UNAVAILABLE,
        SACHIMA_DELEGATE_CARD_UNAVAILABLE,
    }
)

# --------------------------------------------------------------------------- #
# The complete set of things Sachima ever says about a delegated task.
#
# Every line here is about a task that already exists. Refusals — an
# ineligible AGENT, an unreadable roster — are stable codes answered to Hermes
# through the control tool, which puts them into the conversation in the
# user's own language rather than in a fixed string.
# --------------------------------------------------------------------------- #
DELEGATE_ACCEPTED_TEMPLATE = "已接受任务 {task_ref}，完成后会在这里回复。"
DELEGATE_WAITING_TEMPLATE = "任务 {task_ref} 正在等待执行席位…"
DELEGATE_SUBMIT_FAILED_TEMPLATE = "任务 {task_ref} 提交失败（{code}）。"
DELEGATE_BLOCKED_TEMPLATE = "任务 {task_ref} 状态未确认（{code}），已保留，等待显式恢复。"
DELEGATE_LOST_TEMPLATE = "任务 {task_ref} 暂时无法确认状态（{code}），仍在等待结果。"

#: How often the background lifecycle asks whether the Run has ended. Socket
#: API v3 has no push surface, so a bounded poll is the only honest way to learn
#: a terminal — and it stays silent until it finds one.
_DEFAULT_OBSERVE_INTERVAL_SECONDS = 2.0

#: Consecutive observation faults tolerated before Sachima *says* it has gone
#: blind. A disconnect is not evidence a Run ended, so a single fault retries
#: silently. It bounds the speaking only — never the permit.
_MAX_CONSECUTIVE_OBSERVE_FAILURES = 5

#: Milestone A dispatches plain prompt turns. Standing goals are a separate turn
#: kind and a separate decision.
_DELEGATE_TURN_KIND = "prompt"

#: The spine roles/agent kind a delegated supervised session is admitted under.
#: They are the port's own admission vocabulary, not the ARS grant.
_DELEGATE_AGENT_KIND = "local_agent"
_DELEGATE_ROLES = ("read_only",)

#: The §5.2 dispositions, as the classifier names them.
_DISPOSITION_NO_RECORD = "admission_failed"
_DISPOSITION_PENDING = "recovery_required"
_DISPOSITION_ACCEPTED = "admitted"
_DISPOSITION_BLOCKED = "blocked"

#: ARS's five neutral terminals collapse to the three a result envelope carries.
#: ``timed_out`` and ``unknown`` are failures — they are simply failures Sachima
#: can say a little less about.
_TERMINAL_TO_ENVELOPE = {
    "completed": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
    "timed_out": "failed",
    "unknown": "failed",
}

#: The terminals a persisted Turn may carry, as the card's own round states.
#: Derived from the envelope map rather than restated, so a new terminal cannot
#: be readable as a result and unreadable as a round row.
_CARD_TERMINALS = frozenset(_TERMINAL_TO_ENVELOPE.values())

#: How a Run reached its ARS Session, as the admission itself recorded it. The
#: backend writes ``session_mode`` into the accepted binding's ``resolver_refs``
#: from the submit it actually made — ``create`` when it asked the daemon for a
#: new Session, ``reuse`` when it named an existing one — so this is admission
#: evidence rather than a reading of the Task's shape. The two tokens are
#: private to ``arsd_supervisor_backend`` and are therefore mirrored here and
#: drift-locked by ``tests/gateway/test_sachima_delegate_coordinator.py``.
_SESSION_MODE_TO_ORIGIN = {"create": "created", "reuse": "loaded"}

#: The deployment's running-patch cadence, in seconds. It is read once at
#: composition, validated by the one card-layer validator, and answered with the
#: default when it is absent or outside the contract; changing it is a reviewed
#: config change plus a Gateway restart.
SACHIMA_DELEGATE_CARD_PATCH_INTERVAL_ENV = "SACHIMA_DELEGATE_CARD_PATCH_INTERVAL_SECONDS"


@dataclass(frozen=True)
class DelegateDelivery:
    """One origin's delivery capability, injected by the host.

    Two text senders, deliberately: the accepted receipt is an ordinary short
    message, while the terminal result is a single bounded plain-text body that
    must not be chunked or turned into a rich card. ``limit``/``measure`` are the
    platform's own one-message text bound and its own length metric, so the body
    is bounded by what the platform actually enforces rather than by a guess.

    ``send_card`` / ``patch_card`` are the optional rich-card pair. An origin
    that supplies both owns one persistent delegation status card patched in
    place; an origin that supplies neither — every non-Feishu platform, and
    Feishu itself when the adapter is unavailable — keeps the existing plain
    Markdown lifecycle unchanged. There is deliberately no half-capable state:
    a card that could be sent but not patched would become a new message per
    transition, which is the behavior the card exists to retire.
    """

    send_text: Callable[[str], Awaitable[Any]] = field(repr=False)
    send_plain_text_once: Callable[[str], Awaitable[Any]] = field(repr=False)
    limit: int = 4000
    measure: Callable[[str], int] = field(default=len, repr=False)
    send_card: Callable[[dict], Awaitable[Any]] | None = field(default=None, repr=False)
    patch_card: Callable[[str, dict], Awaitable[Any]] | None = field(
        default=None, repr=False
    )

    @property
    def card_capable(self) -> bool:
        """Whether this origin can own one patched-in-place status card."""

        return self.send_card is not None and self.patch_card is not None


@dataclass(frozen=True)
class DelegateOutcome:
    """What one coordinator entry answers with. Refs and codes only."""

    task_ref: str | None = None
    turn_key: str | None = None
    lifecycle: str | None = None
    receipt: str | None = None
    cancellation: str | None = None
    turn_ref: str | None = None
    terminal: str | None = None
    diagnostic: str | None = None
    reply: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_ref": self.task_ref,
            "turn_key": self.turn_key,
            "lifecycle": self.lifecycle,
            "receipt": self.receipt,
            "cancellation": self.cancellation,
            "turn_ref": self.turn_ref,
            "terminal": self.terminal,
            "diagnostic": self.diagnostic,
        }


def _new_task_id() -> str:
    """One fresh spine task id per delegated task."""

    return "delegate_" + uuid.uuid4().hex[:12]


def _utc_status_time() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def configured_running_patch_interval(config: Any = None) -> float:
    """This deployment's running-patch cadence, through the one validator.

    Two sources, in one order: a composed config that declares the cadence
    itself, then the host environment. Both end at
    :func:`normalize_running_patch_interval`, so there is exactly one place that
    decides what is in contract — a mis-typed or out-of-range deployment value
    composes a Gateway at the default rather than either refusing to start or
    being honoured into a patch storm.
    """

    declared = getattr(config, "running_patch_interval_seconds", None)
    if declared is None:
        declared = os.environ.get(SACHIMA_DELEGATE_CARD_PATCH_INTERVAL_ENV)
        if type(declared) is str:
            try:
                declared = float(declared)
            except ValueError:
                # Left as the unparsable text on purpose: the validator owns
                # "this is not a cadence", and it answers with the default.
                pass
    return normalize_running_patch_interval(declared)




class SachimaDelegateCoordinator:
    """The single source of delegate submissions for one bound bundle."""

    def __init__(
        self,
        binding: Any,
        config: Any,
        *,
        presets: AgentExecutionPresets | None = None,
        role_policy: AgentRolePolicy | None = None,
        state: DelegateStateStore | None = None,
        delivery_factory: Callable[[DelegateOrigin], DelegateDelivery | None] | None = None,
        observe_interval: float = _DEFAULT_OBSERVE_INTERVAL_SECONDS,
        summary_provider: DelegateResultSummaryProvider | None = None,
        summary_timeout: float = SUMMARY_PROVIDER_TIMEOUT_SECONDS,
        card_locale: str = "zh",
        running_patch_interval: Any = None,
    ) -> None:
        self._binding = binding
        self._config = config
        self._presets = (
            presets if presets is not None else empty_agent_execution_presets()
        )
        self._role_policy = (
            role_policy if role_policy is not None else empty_agent_role_policy()
        )
        self._state = (
            state
            if state is not None
            else DelegateStateStore(delegate_state_root(config.binding_ledger_path))
        )
        self._ledger = getattr(binding, "ledger", None)
        if self._ledger is None:
            raise ValueError(SACHIMA_DELEGATE_UNBOUND)
        self._delivery_factory = delivery_factory
        self._observe_interval = float(observe_interval)
        # Injected, and legitimately absent. A host with no summariser is a
        # supported composition: it reports ``unavailable`` and keeps the ref,
        # which is the honest answer — never the answer's first characters.
        self._summary_provider = summary_provider
        self._summary_timeout = float(summary_timeout)
        # The one admissible source of capacity: what the daemon said, as
        # validated by the negotiation the composed backend already passed.
        self._capacity = DelegateCapacity(
            int(binding.backend.negotiated_server_info.max_concurrent_runs)
        )
        # One card localization per host: a card is localized consistently, and
        # mixing labels inside one card is exactly what the contract forbids.
        self._card_locale = card_locale if card_locale in ("zh", "en") else "zh"
        # The S0 running-patch cadence contract. It is read once, here, so a
        # change is a reviewed code/config change plus a Gateway restart; the
        # in-memory pacing state below is rebuilt from durable projection state
        # after a restart rather than carried across one.
        self._running_patch_interval = normalize_running_patch_interval(
            running_patch_interval
        )
        self._card_patched_at: dict[str, float] = {}
        self._guard = threading.RLock()
        self._turn_locks: dict[str, asyncio.Lock] = {}
        self._task_gates: dict[str, asyncio.Lock] = {}
        self._card_publications: dict[str, asyncio.Lock] = {}
        self._owned: set[asyncio.Task] = set()
        self._observers: dict[str, asyncio.Task] = {}
        # Only a genuinely fresh composition graph may reclassify a found
        # ``in_flight`` to ``uncertain``, and only while it is restoring. The
        # authority is internal to composition and cannot be requested.
        self._fresh_graph = True
        self._restored = False
        self._restore_lock = asyncio.Lock()
        self._lifecycle_loop: asyncio.AbstractEventLoop | None = None

    # -- read-only identity ------------------------------------------------- #
    @property
    def binding(self) -> Any:
        return self._binding

    @property
    def state(self) -> DelegateStateStore:
        return self._state

    @property
    def presets(self) -> AgentExecutionPresets:
        return self._presets

    @property
    def role_policy(self) -> AgentRolePolicy:
        return self._role_policy

    @property
    def ledger(self) -> Any:
        return self._ledger

    @property
    def capacity(self) -> DelegateCapacity:
        return self._capacity

    @property
    def summary_provider(self) -> DelegateResultSummaryProvider | None:
        return self._summary_provider

    @property
    def running_patch_interval(self) -> float:
        """The seconds this host coalesces running-state card patches by."""

        return self._running_patch_interval

    @property
    def card_locale(self) -> str:
        return self._card_locale

    @property
    def lifecycle_loop(self) -> asyncio.AbstractEventLoop | None:
        """The long-lived Gateway loop that owns coordinator lifecycle tasks."""

        with self._guard:
            return self._lifecycle_loop

    def bind_lifecycle_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind lifecycle work to the one loop owned by this Gateway graph."""

        if not isinstance(loop, asyncio.AbstractEventLoop) or loop.is_closed():
            raise RuntimeError(SACHIMA_DELEGATE_INVARIANT)
        with self._guard:
            existing = self._lifecycle_loop
            if existing is not None and existing is not loop:
                raise RuntimeError(SACHIMA_DELEGATE_INVARIANT)
            self._lifecycle_loop = loop

    def run_on_lifecycle_loop(self, factory: Callable[[], Awaitable[Any]]) -> Any:
        """Run one synchronous control request on the Gateway-owned loop.

        Model tools run in worker threads.  Submitting their coordinator work
        here keeps any observer they arm on the Gateway loop after the sync
        handler returns; a disposable or merely parked tool loop cannot own
        lifecycle tasks.
        """

        with self._guard:
            loop = self._lifecycle_loop
        if loop is None or loop.is_closed() or not loop.is_running():
            raise RuntimeError(SACHIMA_DELEGATE_UNBOUND)
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is loop:
            # A synchronous handler cannot block the loop that must execute it.
            raise RuntimeError(SACHIMA_DELEGATE_INVARIANT)
        return asyncio.run_coroutine_threadsafe(factory(), loop).result()

    def payload_resolver(self) -> Callable[[str], str]:
        """The claim-check the composed bundle dispatches and recovers through."""

        return self._state.read_payload

    def active_count(self) -> int:
        with self._guard:
            return len(self._observers)

    # -- locks -------------------------------------------------------------- #
    def _turn_lock(self, turn_key: str) -> asyncio.Lock:
        with self._guard:
            lock = self._turn_locks.get(turn_key)
            if lock is None:
                lock = asyncio.Lock()
                self._turn_locks[turn_key] = lock
            return lock

    def _task_gate(self, task_ref: str) -> asyncio.Lock:
        with self._guard:
            gate = self._task_gates.get(task_ref)
            if gate is None:
                gate = asyncio.Lock()
                self._task_gates[task_ref] = gate
            return gate

    def _card_publication(self, task_ref: str) -> asyncio.Lock:
        """The one card this Task owns, held by one publisher at a time.

        Scoped to the ``dtask_*`` and to nothing wider: one Task's card is one
        platform message, so two publishers of *that* message are the only pair
        whose completion order can be observed. Two Tasks are two messages and
        stay independent — a shared gate would let one slow adapter call stall
        every other Task's card for no truth-preserving reason.
        """

        with self._guard:
            gate = self._card_publications.get(task_ref)
            if gate is None:
                gate = asyncio.Lock()
                self._card_publications[task_ref] = gate
            return gate

    async def _exclusive(self, turn_key: str, factory: Callable[[], Awaitable[Any]]) -> Any:
        """Run one turn operation in a strongly held, shielded owner task.

        The section is entered *inside* the task, so two callers serialize on
        the same lock. The caller waits on a shield, so a cancelled or timed-out
        waiter cannot cancel the owner mid-operation: the durable commit, the
        receipt settlement, and the observer arm all still happen, which is the
        whole reason the exclusion exists.
        """

        owner_loop = self.lifecycle_loop
        if owner_loop is not None and asyncio.get_running_loop() is not owner_loop:
            raise RuntimeError(SACHIMA_DELEGATE_INVARIANT)
        lock = self._turn_lock(turn_key)

        async def _owner() -> Any:
            async with lock:
                return await factory()

        task = asyncio.create_task(_owner())
        with self._guard:
            self._owned.add(task)
        task.add_done_callback(self._forget_owner)
        return await asyncio.shield(task)

    def _forget_owner(self, task: asyncio.Task) -> None:
        with self._guard:
            self._owned.discard(task)

    # -- classification (§5.2) ---------------------------------------------- #
    def _classify(self, turn: DelegateTurnRecord) -> tuple[str, Any, str | None]:
        """One atomic exact-key observation, and the disposition it implies.

        This is the *only* exit from a dispatch or a recovery. It asks the
        bundle's own ledger object — the same instance the backend writes
        through — for the one record at this turn's exact key, in a single read.
        It never classifies by calling ``resolve_pending()`` and then
        ``resolve()``: that reads the file twice, and a finalize landing between
        the two reports a state that never existed.

        A stable ledger failure is caught here and becomes ``blocked``, the
        conservative disposition. "I could not read the evidence" and "there is
        no evidence" are different facts, and only one of them may clean up.
        """

        try:
            record = self._ledger.snapshot_exact(
                turn.task_id, turn.backend_handle, turn.dispatch_ref
            )
        except BaseException as exc:
            code = getattr(exc, "code", None)
            logger.warning(SACHIMA_DELEGATE_BLOCKED)
            return (
                _DISPOSITION_BLOCKED,
                None,
                code if isinstance(code, str) else SACHIMA_DELEGATE_BLOCKED,
            )
        if record is None:
            return _DISPOSITION_NO_RECORD, None, None
        if record.state != "accepted":
            return _DISPOSITION_PENDING, record, None
        if record.run_ref is None:  # pragma: no cover - the ledger enforces it
            return _DISPOSITION_BLOCKED, None, SACHIMA_DELEGATE_BLOCKED
        return _DISPOSITION_ACCEPTED, record, None

    # -- eligibility: live roster ∩ valid execution preset ------------------ #
    def registered_agent_ids(self) -> tuple[str, ...]:
        """The connected daemon's live roster of canonical agent ids.

        One bounded read-only daemon operation, delegated to the composed
        backend, which validates the reply before it becomes an answer.
        """

        return self._binding.backend.list_registered_agents()

    def admit_agent(self, agent_id: Any, *, task_text: str = "") -> AgentAdmission:
        """Decide whether one canonical ``agent_id`` may execute here.

        The whole of eligibility, in one place: the live roster read plus the
        execution-preset intersection. It is synchronous and side-effect free
        — no Session, no task, no payload, no submit — so a refusal costs
        nothing durable and a caller can ask before it commits to anything.

        A roster this host cannot read is ``roster_unavailable``, never an
        empty roster: "the daemon registered nothing" and "we could not ask"
        are different answers, and only one of them means the AGENT is gone.
        """

        try:
            roster = self.registered_agent_ids()
        except Exception:
            # One stable code only — never the raised text, which can carry
            # private socket paths or remote error bodies.
            logger.debug("delegate roster read failed", exc_info=True)
            return AgentAdmission(refusal=SACHIMA_AGENT_ROSTER_UNAVAILABLE)
        return admit_agent_execution(
            self._presets,
            agent_id=agent_id,
            registered_agent_ids=roster,
            task_text=task_text,
        )

    def agent_eligibility(
        self, *, role: Any = None, division: Any = None
    ) -> tuple[tuple[Any, ...], AgentRoleSelection | None]:
        """The live eligibility view, and the selection an exact role names.

        One read-only daemon operation and two pure joins: the roster
        annotated with execution presets and role assignments, plus — when a
        role or division was asked for — the single candidate or the stable
        clarification code. Nothing here writes a task, a Session, or a Run,
        which is what makes a zero-or-several answer free to ask about.

        Raises whatever the roster read raises; the caller decides what an
        unreadable roster means for the answer it is composing.
        """

        roster = self.registered_agent_ids()
        view = build_agent_eligibility_view(
            registered_agent_ids=roster,
            presets=self._presets,
            role_policy=self._role_policy,
        )
        if role is None and division is None:
            return view, None
        return view, select_agent_by_role(
            registered_agent_ids=roster,
            presets=self._presets,
            role_policy=self._role_policy,
            role=role,
            division=division,
        )

    # -- creation (§5.3, I4) ------------------------------------------------ #
    async def create(
        self,
        *,
        task_text: str,
        preset: AgentExecutionPreset,
        origin: DelegateOrigin,
        delivery: DelegateDelivery | None = None,
        linked_from: str | None = None,
        admitted_role: Any = None,
    ) -> DelegateOutcome:
        """Register one delegated task and drive its first turn to a disposition.

        The durable prefix runs first and in one order: exact task bytes, the
        sealed spine Session, the turn record with its exact ledger key, and the
        task binding. Only then can anything reach the daemon. A failure before
        that point makes no ARS call at all, which is what makes the failure
        recoverable rather than merely reported.
        """

        await self._ensure_restored()
        if (
            type(preset) is not AgentExecutionPreset
            or type(origin) is not DelegateOrigin
        ):
            raise ValueError(SACHIMA_DELEGATE_INVALID_TARGET)

        from sachima_supervisor.runtime_spine.arsd_supervisor_backend import (
            derive_arsd_backend_handle,
        )
        from sachima_supervisor.runtime_spine.launch_spec import build_launch_spec

        requested = requested_configuration(self._config, preset)
        payload_ref = self._state.put_payload(task_text)
        task_id = _new_task_id()
        try:
            spec = build_launch_spec(
                task_id=task_id,
                agent_kind=_DELEGATE_AGENT_KIND,
                mode_flags={"needs_agent": True},
                roles=_DELEGATE_ROLES,
                refs=preset.launch_refs,
            )
            session = self._binding.port.create_or_attach(task_id, spec)
            handle = derive_arsd_backend_handle(task_id)
        except BaseException:
            self._state.discard_payload(payload_ref)
            raise

        task_ref = self._state.new_task_ref()
        turn = self._state.put_turn(
            DelegateTurnRecord(
                turn_key=self._state.new_turn_key(),
                task_ref=task_ref,
                task_id=task_id,
                backend_handle=handle,
                dispatch_ref=payload_ref,
                payload_ref=payload_ref,
                spine_session_id=session.session_id,
                agent_id=preset.agent_id,
                launch_refs=preset.launch_refs,
                requested_agent=requested[0],
                requested_model=requested[1],
                requested_effort=requested[2],
                origin=origin,
                task_description=sanitize_task_description(task_text),
                admitted_role=self._sealed_role(preset.agent_id, admitted_role),
            )
        )
        binding = self._state.put_task(
            DelegateTaskBinding(
                task_ref=task_ref,
                task_id=task_id,
                backend_handle=handle,
                spine_session_id=session.session_id,
                agent_id=preset.agent_id,
                origin=origin,
                turn_keys=(turn.turn_key,),
                current_turn_key=turn.turn_key,
                linked_from=linked_from,
            )
        )
        # The Task/origin binding is durable, so the card — and with it the
        # complete copyable ``dtask_*`` — becomes visible before capacity
        # waiting and before anything could reach the daemon.
        await self._ensure_card(binding, turn, delivery)
        return await self._exclusive(
            turn.turn_key,
            lambda: self._drive(turn.turn_key, mode="dispatch", delivery=delivery),
        )

    async def continue_task(
        self,
        task_ref: str,
        task_text: str,
        *,
        delivery: DelegateDelivery | None = None,
        preset: AgentExecutionPreset | None = None,
        origin: DelegateOrigin | None = None,
        admitted_role: Any = None,
    ) -> DelegateOutcome:
        """Continue the same task, in the same Sessions, under the same AGENT.

        A later Run under the original task, sealed spine Session, ARS Session,
        execution preset, and AGENT — and only once the preceding Run has
        passed the canonical terminal closure. A Run that is live, unresolved,
        or whose cancellation is ``in_flight``/``uncertain`` refuses:
        continuing over an unsettled Run would put two Runs on one Session and
        silently attribute one's output to the other.

        ``preset`` is the already-admitted execution preset. Passing the one
        this task is already sealed under continues it; passing a different
        AGENT's creates a linked new task; omitting it resolves the task's own
        AGENT from the catalog, which is the path a caller that has already
        proven eligibility elsewhere takes.
        """

        await self._ensure_restored()
        # The task gate makes the task read, "which turn is current", and the
        # append/switch decision one operation. Reading before this gate lets
        # two callers append from the same stale binding and lose one turn.
        async with self._task_gate(task_ref):
            binding = self._state.read_task(task_ref)
            if binding is None:
                return DelegateOutcome(diagnostic=SACHIMA_DELEGATE_UNKNOWN_TASK)
            current = (
                self._state.read_turn(binding.current_turn_key)
                if binding.current_turn_key
                else None
            )
            if current is None:
                return DelegateOutcome(
                    task_ref=binding.task_ref, diagnostic=SACHIMA_DELEGATE_UNKNOWN_TASK
                )
            if current.lifecycle == "blocked" or current.diagnostic == SACHIMA_DELEGATE_BLOCKED:
                return self._outcome(current, diagnostic=SACHIMA_DELEGATE_BLOCKED)
            if (
                current.lifecycle != "terminal"
                or current.cancellation in {"in_flight", "uncertain"}
            ):
                return DelegateOutcome(
                    task_ref=binding.task_ref,
                    turn_key=current.turn_key,
                    lifecycle=current.lifecycle,
                    cancellation=current.cancellation,
                    diagnostic=SACHIMA_DELEGATE_NOT_CONTINUABLE,
                )
            if preset is not None and type(preset) is not AgentExecutionPreset:
                return DelegateOutcome(
                    task_ref=binding.task_ref,
                    diagnostic=SACHIMA_DELEGATE_INVALID_TARGET,
                )
            if preset is not None and preset.agent_id != binding.agent_id:
                if type(origin) is not DelegateOrigin or (
                    origin.session_id != binding.origin.session_id
                ):
                    return DelegateOutcome(
                        task_ref=binding.task_ref,
                        diagnostic=SACHIMA_DELEGATE_INVALID_TARGET,
                    )
                try:
                    event = self._state.result_for_turn(current.turn_key)
                except DelegateStateError:
                    event = None
                if event is None:
                    return DelegateOutcome(
                        task_ref=binding.task_ref,
                        turn_key=current.turn_key,
                        diagnostic=SACHIMA_DELEGATE_NOT_CONTINUABLE,
                    )
                # The AGENT is sealed into a task. Switching therefore
                # creates a new linked task; it never rewrites the old binding.
                return await self.create(
                    task_text=task_text,
                    preset=preset,
                    origin=origin,
                    delivery=delivery,
                    linked_from=event.event_id,
                    admitted_role=admitted_role,
                )
            if preset is None:
                preset = self._presets.preset(binding.agent_id)
            if preset is None:
                # The task's own AGENT has no execution preset here any more.
                # A later Run under it would have to invent a configuration,
                # so the task stays readable and simply does not continue.
                return DelegateOutcome(
                    task_ref=binding.task_ref, diagnostic=SACHIMA_AGENT_NO_PRESET
                )
            requested = requested_configuration(self._config, preset)
            payload_ref = self._state.put_payload(task_text)
            turn = self._state.put_turn(
                DelegateTurnRecord(
                    turn_key=self._state.new_turn_key(),
                    task_ref=binding.task_ref,
                    task_id=binding.task_id,
                    backend_handle=binding.backend_handle,
                    dispatch_ref=payload_ref,
                    payload_ref=payload_ref,
                    spine_session_id=binding.spine_session_id,
                    agent_id=binding.agent_id,
                    launch_refs=preset.launch_refs,
                    requested_agent=requested[0],
                    requested_model=requested[1],
                    requested_effort=requested[2],
                    origin=binding.origin,
                    # The round purpose is sealed at continuation time from the
                    # continuation's own ask; it is never inferred later from
                    # opaque result text.
                    task_description=sanitize_task_description(task_text),
                    admitted_role=self._sealed_role(binding.agent_id, admitted_role),
                )
            )
            self._state.update_task(
                binding.task_ref,
                turn_keys=binding.turn_keys + (turn.turn_key,),
                current_turn_key=turn.turn_key,
            )

        # A Task that predates card projection creates its card here, before the
        # continuation becomes user-visible; one that already has a card reuses
        # it and adds exactly one round row.
        await self._ensure_card(binding, turn, delivery)
        return await self._exclusive(
            turn.turn_key,
            lambda: self._drive(turn.turn_key, mode="dispatch", delivery=delivery),
        )

    # -- the turn operation ------------------------------------------------- #
    async def _drive(
        self,
        turn_key: str,
        *,
        mode: str,
        delivery: DelegateDelivery | None,
    ) -> DelegateOutcome:
        """One whole turn operation, inside the section the caller opened."""

        turn = self._state.read_turn(turn_key)
        if turn is None:
            return DelegateOutcome(turn_key=turn_key, diagnostic=SACHIMA_DELEGATE_UNKNOWN_TASK)

        disposition, record, code = self._classify(turn)

        if mode == "dispatch":
            if disposition != _DISPOSITION_NO_RECORD:
                # Evidence already exists for this exact key: a second submit is
                # exactly what must not happen, whatever the caller asked for.
                return await self._apply(turn, disposition, record, code, delivery=delivery)
            await self._acquire_capacity(turn, delivery)
            await self._card_open_round(turn, delivery)
            await self._run_dispatch(turn)
        elif mode == "recover":
            if disposition == _DISPOSITION_PENDING:
                self._capacity.reserve(turn.turn_key)
                await self._run_recovery(turn)
            else:
                return await self._apply(turn, disposition, record, code, delivery=delivery)
        elif mode == "reconcile":
            return await self._apply(turn, disposition, record, code, delivery=delivery)
        else:  # pragma: no cover - internal call guard
            raise ValueError(SACHIMA_DELEGATE_INVARIANT)

        # The post-operation exact snapshot is the only thing that decides.
        turn = self._state.read_turn(turn_key)
        disposition, record, code = self._classify(turn)
        return await self._apply(turn, disposition, record, code, delivery=delivery)

    async def _acquire_capacity(
        self, turn: DelegateTurnRecord, delivery: DelegateDelivery | None
    ) -> None:
        """Take one permit, saying so **only** when the wait is real.

        A card-capable origin is told through its own card rather than through a
        second message: one Task, one surface. Every other origin keeps the
        existing plain notice.
        """

        if self._capacity.would_wait() and not self._capacity.holds(turn.turn_key):
            if self._card_channel(turn.origin, delivery) is not None:
                await self._card_pre_accept(turn, "waiting", delivery)
            else:
                await self._notify(
                    turn,
                    DELEGATE_WAITING_TEMPLATE.format(task_ref=turn.task_ref),
                    delivery,
                )
        await self._capacity.acquire(turn.turn_key)

    async def _run_dispatch(self, turn: DelegateTurnRecord) -> None:
        """Drive one turn through the bundle's dispatcher, off the event loop.

        The dispatcher is synchronous spine code that talks to a socket, so it
        runs on a worker thread: inline, it would freeze every other
        conversation in the gateway for the length of an admission. Its return
        value is deliberately discarded — the snapshot that follows is what
        decides — and a raise is a diagnostic, never a disposition.
        """

        await self._spine_call(lambda: self._dispatch_request(turn))

    async def _run_recovery(self, turn: DelegateTurnRecord) -> None:
        await self._spine_call(lambda: self._recover_request(turn))

    async def _spine_call(self, call: Callable[[], Any]) -> None:
        try:
            await asyncio.to_thread(call)
        except asyncio.CancelledError:
            raise
        except BaseException:
            # One stable code only — never the offending value or exception
            # text, both of which can carry private config refs.
            logger.warning(SACHIMA_DELEGATE_DISPATCH_FAILED)

    def _dispatch_request(self, turn: DelegateTurnRecord) -> Any:
        from sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher import (
            TurnDispatchRequest,
        )

        return self._binding.dispatcher.dispatch(
            TurnDispatchRequest(
                task_id=turn.task_id,
                session_id=turn.spine_session_id,
                turn_kind=_DELEGATE_TURN_KIND,
                payload_ref=turn.payload_ref,
            )
        )

    def _recover_request(self, turn: DelegateTurnRecord) -> Any:
        from sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher import (
            TurnDispatchRequest,
        )

        return self._binding.dispatcher.recover_dispatch(
            TurnDispatchRequest(
                task_id=turn.task_id,
                session_id=turn.spine_session_id,
                turn_kind=_DELEGATE_TURN_KIND,
                payload_ref=turn.payload_ref,
            )
        )

    # -- the §5.2 disposition table ----------------------------------------- #
    async def _apply(
        self,
        turn: DelegateTurnRecord,
        disposition: str,
        record: Any,
        code: str | None,
        *,
        delivery: DelegateDelivery | None,
        restoring: bool = False,
    ) -> DelegateOutcome:
        """Execute exactly one row of the exact-key disposition table."""

        if disposition == _DISPOSITION_NO_RECORD:
            return await self._admission_failed(turn, delivery=delivery)
        if disposition == _DISPOSITION_PENDING:
            outcome = self._recovery_required(turn, restoring=restoring)
            await self._card_round_state(turn, "recovering", delivery)
            return outcome
        if disposition == _DISPOSITION_BLOCKED:
            outcome = self._blocked(turn, code)
            await self._card_round_state(turn, "recovering", delivery)
            return outcome
        return await self._admitted(turn, record, delivery=delivery, restoring=restoring)

    async def _admission_failed(
        self, turn: DelegateTurnRecord, *, delivery: DelegateDelivery | None = None
    ) -> DelegateOutcome:
        """No record: nothing was admitted, so nothing execution-shaped is kept.

        This is the one row that cleans up, and it is safe *because* the
        snapshot proved there is no durable record — not because a return value
        looked like a failure. What it cleans up is execution-only material: the
        task payload and the capacity permit, neither of which anything can
        still be waiting on.

        The identity stays. The ``dtask_*`` was made user-visible by the card
        before this submission could fail, so the Task binding and its Turn
        remain readable in their truthful ``admission_failed`` state: a task
        number a user was shown and can quote back must answer with what
        happened to it, not with ``unknown_task``. Nothing here fabricates the
        Run, Session, or acceptance evidence the snapshot proved does not exist.
        """

        updated = self._state.update_turn(
            turn.turn_key,
            lifecycle="admission_failed",
            diagnostic=SACHIMA_DELEGATE_DISPATCH_FAILED,
        )
        await self._card_round_state(
            turn, "rejected", delivery, settled_at=_utc_status_time()
        )
        self._state.discard_payload(turn.payload_ref)
        self._capacity.release(turn.turn_key)
        return DelegateOutcome(
            task_ref=turn.task_ref,
            turn_key=turn.turn_key,
            lifecycle=updated.lifecycle,
            diagnostic=SACHIMA_DELEGATE_DISPATCH_FAILED,
            reply=DELEGATE_SUBMIT_FAILED_TEMPLATE.format(
                task_ref=turn.task_ref, code=SACHIMA_DELEGATE_DISPATCH_FAILED
            ),
        )

    def _recovery_required(
        self, turn: DelegateTurnRecord, *, restoring: bool
    ) -> DelegateOutcome:
        """A pending intent: retain everything, hold a permit, send nothing.

        The submission may already be a Run the daemon holds. Nothing here
        resends it, cleans it up, or reports it as finished — only the explicit
        recovery entry point may act on a pending intent.
        """

        if restoring:
            try:
                self._restore_pending_identity(turn)
            except BaseException:
                logger.warning(SACHIMA_DELEGATE_BLOCKED)
                return self._blocked(turn, SACHIMA_DELEGATE_BLOCKED)
        updated = self._state.update_turn(
            turn.turn_key,
            lifecycle="recovery_required",
            diagnostic=SACHIMA_DELEGATE_RECOVERY_REQUIRED,
        )
        self._capacity.reserve(turn.turn_key)
        return DelegateOutcome(
            task_ref=turn.task_ref,
            turn_key=turn.turn_key,
            lifecycle=updated.lifecycle,
            receipt=updated.receipt,
            cancellation=updated.cancellation,
            diagnostic=SACHIMA_DELEGATE_RECOVERY_REQUIRED,
            reply=DELEGATE_BLOCKED_TEMPLATE.format(
                task_ref=turn.task_ref, code=SACHIMA_DELEGATE_RECOVERY_REQUIRED
            ),
        )

    def _blocked(self, turn: DelegateTurnRecord, code: str | None) -> DelegateOutcome:
        """The R4-equivalent conservative disposition: keep everything.

        A ledger Sachima cannot read is not a ledger that says "nothing
        happened". Evidence is retained unchanged, a permit is reserved, one
        stable diagnostic is persisted, and no cleanup, observation, submit, or
        create is performed.
        """

        updated = self._state.update_turn(
            turn.turn_key, lifecycle="blocked", diagnostic=code or SACHIMA_DELEGATE_BLOCKED
        )
        self._capacity.reserve(turn.turn_key)
        return DelegateOutcome(
            task_ref=turn.task_ref,
            turn_key=turn.turn_key,
            lifecycle=updated.lifecycle,
            receipt=updated.receipt,
            cancellation=updated.cancellation,
            diagnostic=updated.diagnostic,
            reply=DELEGATE_BLOCKED_TEMPLATE.format(
                task_ref=turn.task_ref, code=updated.diagnostic
            ),
        )

    async def _admitted(
        self,
        turn: DelegateTurnRecord,
        record: Any,
        *,
        delivery: DelegateDelivery | None,
        restoring: bool,
    ) -> DelegateOutcome:
        """An accepted Run: commit, settle the receipt, then arm one observer.

        The order is the contract. A receipt that goes out before the durable
        commit can describe a Run nobody recorded; an observer armed before the
        receipt settles can deliver a terminal ahead of the acceptance it
        answers.
        """

        if restoring:
            try:
                self._restore_accepted_identity(turn, record)
            except BaseException:
                logger.warning(SACHIMA_DELEGATE_BLOCKED)
                return self._blocked(turn, SACHIMA_DELEGATE_BLOCKED)
        updated = self._state.update_turn(
            turn.turn_key,
            lifecycle="admitted",
            turn_ref=record.run_ref,
            accepted_at=(
                turn.accepted_at or getattr(record, "accepted_at", None) or _utc_status_time()
            ),
            diagnostic=None,
        )
        self._capacity.reserve(turn.turn_key)
        # The round's Run/Session evidence is recorded before the acceptance is
        # made visible, so the snapshot the user sees and the evidence the next
        # continuation reasons over are the same durable fact.
        self._card_admitted_round(updated, record)
        updated = await self._settle_receipt(updated, delivery)
        self._arm_observer(updated.turn_key)
        return DelegateOutcome(
            task_ref=updated.task_ref,
            turn_key=updated.turn_key,
            lifecycle=updated.lifecycle,
            receipt=updated.receipt,
            cancellation=updated.cancellation,
            turn_ref=updated.turn_ref,
            reply=DELEGATE_ACCEPTED_TEMPLATE.format(task_ref=updated.task_ref),
        )

    # -- receipts (I6, §5.4) ------------------------------------------------ #
    async def _settle_receipt(
        self, turn: DelegateTurnRecord, delivery: DelegateDelivery | None
    ) -> DelegateTurnRecord:
        """Attempt the one accepted receipt this turn is owed, and settle it.

        A receipt is a moment-in-time message. ``pending`` may be attempted
        once; anything already settled replays unchanged; an ``in_flight`` found
        by a live graph is an invariant error rather than a licence to resend,
        because the other attempt may be about to succeed.

        On a card-capable origin the acceptance *is* the card patch: the same
        durable receipt dimension settles from that one adapter call, so the
        user never gets a card and a redundant acceptance message about one Run.
        """

        if turn.receipt != "pending":
            if turn.receipt == "in_flight" and not self._fresh_graph:
                logger.warning(SACHIMA_DELEGATE_INVARIANT)
            return turn

        self._state.update_turn(turn.turn_key, receipt="in_flight")
        settlement = UNCERTAIN_SETTLEMENT
        try:
            channel = self._delivery_for(turn.origin, delivery)
            if channel is None:
                settlement = SendSettlement(
                    state="failed", diagnostic=SACHIMA_DELEGATE_NO_DELIVERY
                )
            elif channel.card_capable:
                settlement = await self._flush_card(
                    turn.task_ref, turn.origin, channel, force=True
                ) or SendSettlement(
                    state="failed", diagnostic=SACHIMA_DELEGATE_CARD_UNAVAILABLE
                )
            else:
                text = render_accepted_receipt(
                    DelegateAcceptedReceipt(
                        task_ref=turn.task_ref,
                        task_description=turn.task_description,
                        status_time=turn.accepted_at,
                        requested_agent=turn.requested_agent,
                        requested_model=turn.requested_model,
                        requested_effort=turn.requested_effort,
                    )
                )
                settlement = await perform_settled_send(lambda: channel.send_text(text))
        finally:
            # Seeded before the attempt and written in ``finally``: no valid
            # branch, and no cancellation, leaves a receipt ``in_flight``.
            turn = self._state.update_turn(
                turn.turn_key,
                receipt=settlement.state,
                receipt_message_id=settlement.message_id,
            )
        return turn

    # -- observation -------------------------------------------------------- #
    def _arm_observer(self, turn_key: str) -> None:
        """Arm exactly one observer for this turn. A second call does nothing."""

        with self._guard:
            if turn_key in self._observers:
                return
            self._state.update_turn(turn_key, observation="armed")
            task = asyncio.create_task(self._observe_loop(turn_key))
            self._observers[turn_key] = task
        task.add_done_callback(lambda _t: self._forget_observer(turn_key))

    def _forget_observer(self, turn_key: str) -> None:
        with self._guard:
            self._observers.pop(turn_key, None)

    async def _observe_loop(self, turn_key: str) -> None:
        """Poll in silence until the Run *ends*, then close it exactly once.

        Observation faults settle nothing: a socket that dropped is not a Run
        that stopped, and an accepted Run stays the daemon's to finish whether or
        not Sachima can currently see it. So a run of faults never returns —
        returning would release the permit while the Run is still executing.
        """

        turn = self._state.read_turn(turn_key)
        if turn is None:
            return
        # The Run is the daemon's now: the card says so once, forcefully, and
        # every later running snapshot is paced by the cadence contract.
        await self._card_round_state(turn, "running", None)
        failures = 0
        blindness_reported = False
        while True:
            try:
                result = await asyncio.to_thread(
                    self._binding.backend.observe_run_result, turn.backend_handle
                )
            except asyncio.CancelledError:
                raise
            except BaseException:
                failures += 1
                if failures >= _MAX_CONSECUTIVE_OBSERVE_FAILURES and not blindness_reported:
                    blindness_reported = True
                    logger.warning(SACHIMA_DELEGATE_OBSERVATION_LOST)
                    if self._card_channel(turn.origin, None) is not None:
                        await self._card_round_state(turn, "recovering", None)
                    else:
                        await self._notify(
                            turn,
                            DELEGATE_LOST_TEMPLATE.format(
                                task_ref=turn.task_ref,
                                code=SACHIMA_DELEGATE_OBSERVATION_LOST,
                            ),
                            None,
                        )
            else:
                failures = 0
                if result is not None:
                    await self._exclusive(
                        turn_key, lambda: self._close_terminal(turn_key, result)
                    )
                    return
                # A running card's duration keeps moving without the poll
                # becoming a patch storm: this call coalesces by contract.
                await self._flush_card(turn.task_ref, turn.origin, None)
            await asyncio.sleep(self._observe_interval)

    # -- the canonical terminal closure (I8) -------------------------------- #
    async def _close_terminal(self, turn_key: str, result: Any) -> DelegateOutcome:
        """One terminal, one envelope, one release, two independent sinks.

        The observed terminal is preserved exactly as it arrived: a completion
        or failure that won a cancel race stays what it was. Nothing is rewritten
        to ``cancelled`` because a cancel happened to be in flight.
        """

        turn = self._state.read_turn(turn_key)
        if turn is None:
            return DelegateOutcome(turn_key=turn_key, diagnostic=SACHIMA_DELEGATE_UNKNOWN_TASK)
        try:
            existing = self._state.result_for_turn(turn_key)
        except DelegateStateError:
            return self._blocked(turn, SACHIMA_DELEGATE_BLOCKED)
        if existing is not None:
            return await self._finalize_terminal_event(turn, existing)

        terminal = _TERMINAL_TO_ENVELOPE.get(getattr(result, "status", None))
        if terminal is None:
            # Not a terminal this adapter can read: contained, never fabricated.
            return self._blocked(turn, SACHIMA_DELEGATE_BLOCKED)

        full_ref, clipped = self._state.put_full_result(
            getattr(result, "final_message", "") or ""
        )
        event = self._state.put_result(
            DelegateResultEvent(
                event_id=self._state.new_event_id(),
                turn_key=turn.turn_key,
                task_ref=turn.task_ref,
                session_id=turn.origin.session_id,
                terminal=terminal,
                full_result_ref=full_ref,
                terminal_at=_utc_status_time(),
                truncated=bool(getattr(result, "truncated", False)) or clipped,
                truncate_reason=getattr(result, "truncate_reason", None),
            )
        )
        return await self._finalize_terminal_event(turn, event)

    async def _finalize_terminal_event(
        self, turn: DelegateTurnRecord, event: DelegateResultEvent
    ) -> DelegateOutcome:
        """Finish one already-durable result identity, idempotently.

        The result record is the canonical crash boundary.  If a process dies
        after that write, restart completes the turn and both sink obligations
        from this same event id instead of minting another envelope.
        """

        if (
            event.turn_key != turn.turn_key
            or event.task_ref != turn.task_ref
            or event.session_id != turn.origin.session_id
            or event.terminal not in _TERMINAL_TO_ENVELOPE.values()
        ):
            return self._blocked(turn, SACHIMA_DELEGATE_BLOCKED)
        turn = self._state.update_turn(
            turn.turn_key,
            lifecycle="terminal",
            observation="terminal_seen",
            terminal_status=event.terminal,
            diagnostic=None,
            cancellation=(
                "settled" if turn.cancellation in {"in_flight", "uncertain"} else turn.cancellation
            ),
        )
        # The result and both sink intents are durable, so the permit can go
        # back: delivery can still be reconciled after the release.
        self._capacity.release(turn.turn_key)
        try:
            task_description = sanitize_task_description(
                self._state.read_payload(turn.payload_ref)
            )
        except DelegateStateError:
            task_description = None
        self._state.discard_payload(turn.payload_ref)
        # The derivative settles *before* either sink runs. Both sinks project
        # the same durable record, so a user message and the next Hermes turn
        # cannot end up describing one terminal two different ways.
        await self._settle_summary(event, task_description=task_description)
        await self._reconcile_im_sink(event, turn)
        return self._outcome(turn, terminal=event.terminal)

    # -- the derived summary (plan §4, §5) ---------------------------------- #
    def _summary_for_event(
        self, event: DelegateResultEvent
    ) -> DelegateResultSummary | None:
        """This result's derivative record, or ``None`` if it cannot be read."""

        try:
            return self._state.summary_for_event(event.event_id)
        except DelegateStateError:
            logger.warning(SACHIMA_DELEGATE_SUMMARY_UNAVAILABLE)
            return None

    def _persist_summary(
        self, summary: DelegateResultSummary
    ) -> DelegateResultSummary | None:
        """Write one settled derivative, deferring to a slot already settled.

        A durable conflict here means another writer reached the same slot
        first. Its record wins: the slot is derived from the result identity, so
        there is exactly one right answer and overwriting it would be how two
        readings of one answer come to exist.
        """

        try:
            return self._state.advance_summary(summary)
        except (DelegateStateError, DelegateSummaryError):
            logger.warning(SACHIMA_DELEGATE_SUMMARY_UNAVAILABLE)
            try:
                return self._state.read_summary(summary.summary_ref)
            except DelegateStateError:
                return None

    def _settle_unavailable(
        self, record: DelegateResultSummary, reason: str
    ) -> DelegateResultSummary | None:
        return self._persist_summary(unavailable_summary(record, reason=reason))

    def _current_source_digest(self, full_result_ref: str) -> str:
        """Digest the bytes currently behind a result ref, or ``""`` if unreadable."""

        try:
            source_text = self._state.read_full_result(full_result_ref)
        except DelegateStateError:
            return ""
        return compute_source_digest(source_text)

    async def _settle_summary(
        self,
        event: DelegateResultEvent,
        *,
        task_description: str | None = None,
    ) -> DelegateResultSummary | None:
        """Produce the one derivative this result identity is owed, or say why not.

        Runs inside the turn's own exclusion, after the result record is durable
        and before either sink may read it. The order is the contract:
        ``pending`` is on disk before any provider call, so a process that dies
        mid-attempt leaves a slot a restart can settle rather than an unbounded
        licence to ask again.

        Every exit is one durable terminal record or ``None`` for "the durable
        state could not be read", which both sinks treat as not-yet-deliverable.
        No exit is the answer's first characters.
        """

        existing = self._summary_for_event(event)
        if existing is not None and existing.settled:
            return existing
        if existing is not None and existing.summary_status == "in_flight":
            # A claimed attempt this frame did not make. Whether the provider
            # was actually called is unknowable from here, so it fails closed
            # rather than being replayed at a second real cost.
            if not self._fresh_graph:
                logger.warning(SACHIMA_DELEGATE_INVARIANT)
            return self._settle_unavailable(existing, SUMMARY_REASON_ATTEMPT_ABANDONED)

        try:
            source_text: str | None = self._state.read_full_result(
                event.full_result_ref
            )
        except DelegateStateError:
            source_text = None
        digest = "" if source_text is None else compute_source_digest(source_text)

        if existing is None:
            try:
                record = self._state.put_summary(
                    pending_summary(
                        event_id=event.event_id,
                        full_result_ref=event.full_result_ref,
                        source_digest=digest,
                    )
                )
            except (DelegateStateError, DelegateSummaryError):
                logger.warning(SACHIMA_DELEGATE_SUMMARY_UNAVAILABLE)
                return self._summary_for_event(event)
        elif (
            existing.source_full_result_ref != event.full_result_ref
            or existing.source_digest != digest
        ):
            # The bytes behind the ref are not the bytes this slot was opened
            # over. That is not a stale summary, it is a summary of something
            # else, and it fails closed instead of being re-read.
            return self._settle_unavailable(existing, SUMMARY_REASON_SOURCE_DRIFT)
        else:
            record = existing

        reason = source_gate_reason(
            source_text=source_text,
            truncated=event.truncated,
            has_provider=self._summary_provider is not None,
        )
        if reason is not None:
            return self._settle_unavailable(record, reason)

        claimed = self._state.claim_summary_attempt(record.summary_ref)
        if claimed is None:
            # Another writer claimed or settled the slot between the read and
            # the claim. Whatever it decided is the one answer.
            return self._summary_for_event(event)

        try:
            request = build_summary_request(
                task_ref=event.task_ref,
                terminal=event.terminal,
                full_result_ref=event.full_result_ref,
                source_text=source_text or "",
                source_digest=digest,
                task_description=task_description,
            )
        except DelegateSummaryError:
            logger.warning(SACHIMA_DELEGATE_SUMMARY_UNAVAILABLE)
            return self._settle_unavailable(claimed, SUMMARY_REASON_SUMMARY_FAILED)

        # Seeded before the attempt and written in ``finally``: no branch, and
        # no cancellation, leaves a summary ``in_flight`` in this process.
        settled = unavailable_summary(claimed, reason=SUMMARY_REASON_SUMMARY_FAILED)
        try:
            settled = await settle_summary_attempt(
                claimed,
                request=request,
                provider=self._summary_provider,
                timeout=self._summary_timeout,
            )
            if settled.ready:
                current_digest = self._current_source_digest(event.full_result_ref)
                if current_digest != digest:
                    settled = unavailable_summary(
                        claimed,
                        reason=(
                            SUMMARY_REASON_SOURCE_MISSING
                            if not current_digest
                            else SUMMARY_REASON_SOURCE_DRIFT
                        ),
                    )
        finally:
            persisted = self._persist_summary(settled)
        return persisted

    async def _reconcile_im_sink(
        self, event: DelegateResultEvent, turn: DelegateTurnRecord
    ) -> None:
        """One bounded plain-text body per delivery attempt, fully settled.

        A ``failed``/``uncertain`` sink may be retried under explicit
        reconciliation with the *same* event id — each retry is another settled
        attempt, never a claim of provider-visible exactly-once.
        """

        if event.im_sink not in {"pending", "failed", "uncertain"}:
            return
        summary = self._summary_for_event(event)
        if summary is None or not summary.settled:
            # A result whose derivative has not settled is not deliverable yet.
            # Both sinks wait on the same record, which is what stops the chat
            # and the next model turn from describing one terminal differently.
            return
        channel = self._delivery_for(turn.origin, None)
        if channel is None:
            self._state.update_result(
                event.event_id,
                im_sink="failed",
                im_diagnostic=SACHIMA_DELEGATE_NO_DELIVERY,
            )
            return

        if channel.card_capable:
            # One Task, one surface: the terminal is the card's final projection
            # revision rather than another "same task completed" message. The
            # same durable ``im_sink`` settles from that one adapter call.
            self._state.update_result(event.event_id, im_sink="in_flight")
            settlement = UNCERTAIN_SETTLEMENT
            try:
                settlement = await self._card_terminal_round(
                    turn, event, summary, channel
                ) or SendSettlement(
                    state="failed", diagnostic=SACHIMA_DELEGATE_CARD_UNAVAILABLE
                )
            finally:
                self._state.update_result(
                    event.event_id,
                    im_sink=settlement.state,
                    im_message_id=settlement.message_id,
                    im_diagnostic=settlement.diagnostic,
                )
            return

        source_digest = self._current_source_digest(event.full_result_ref)
        self._state.update_result(event.event_id, im_sink="in_flight")
        settlement = UNCERTAIN_SETTLEMENT
        try:
            envelope = build_result_envelope(
                event_id=event.event_id,
                task_ref=event.task_ref,
                turn_ref=turn.turn_ref,
                session_id=event.session_id,
                terminal=event.terminal,
                full_result_ref=event.full_result_ref,
                truncated=event.truncated,
                truncate_reason=event.truncate_reason,
            )
            body = render_result_body(
                envelope,
                summary,
                source_digest=source_digest,
                limit=channel.limit,
                measure=channel.measure,
                task_description=turn.task_description,
                status_time=event.terminal_at,
                requested_agent=turn.requested_agent,
                requested_model=turn.requested_model,
                requested_effort=turn.requested_effort,
            )
            settlement = await perform_settled_send(
                lambda: channel.send_plain_text_once(body)
            )
        finally:
            self._state.update_result(
                event.event_id,
                im_sink=settlement.state,
                im_message_id=settlement.message_id,
                im_diagnostic=settlement.diagnostic,
            )

    # -- Hermes sink (next ordinary turn only) ------------------------------ #
    def pending_hermes_context(self, session_id: str) -> tuple[str, ...]:
        """The result projections this Session's next ordinary turn should see.

        Marks each one ``in_flight`` and returns its bounded text: the control
        facts, the durable ref, and the *same* persisted Sachima summary the
        user was shown. A result whose derivative has not settled stays
        ``pending`` and is owed to a later turn — the model and the chat read one
        record, so they cannot be told two different things about one terminal.

        It never mutates a running turn, never injects a synthetic user message,
        and never touches the long-lived system-prompt prefix — the caller folds
        the text into the *next* real user turn's own context.
        """

        lines: list[str] = []
        for event in self._state.list_results():
            if event.session_id != session_id or event.hermes_sink != "pending":
                continue
            summary = self._summary_for_event(event)
            if summary is None or not summary.settled:
                # Not yet projectable. It stays ``pending`` and is owed to a
                # later turn rather than being handed over half-settled.
                continue
            source_digest = self._current_source_digest(event.full_result_ref)
            self._state.update_result(event.event_id, hermes_sink="in_flight")
            envelope = build_result_envelope(
                event_id=event.event_id,
                task_ref=event.task_ref,
                turn_ref=None,
                session_id=event.session_id,
                terminal=event.terminal,
                full_result_ref=event.full_result_ref,
                truncated=event.truncated,
                truncate_reason=event.truncate_reason,
            )
            lines.append(
                build_hermes_context(
                    envelope,
                    summary,
                    source_digest=source_digest,
                )
            )
        return tuple(lines)

    def confirm_hermes_context(self, session_id: str) -> int:
        """Confirm the handoff **after** the next model turn consumed it."""

        confirmed = 0
        for event in self._state.list_results():
            if event.session_id != session_id or event.hermes_sink != "in_flight":
                continue
            self._state.update_result(event.event_id, hermes_sink="confirmed")
            confirmed += 1
        return confirmed

    def release_hermes_context(self, session_id: str) -> int:
        """Return an interrupted handoff to ``pending`` for a later turn."""

        released = 0
        for event in self._state.list_results():
            if event.session_id != session_id or event.hermes_sink != "in_flight":
                continue
            self._state.update_result(event.event_id, hermes_sink="pending")
            released += 1
        return released

    # -- control operations (§5.3) ------------------------------------------ #
    async def status(self, task_ref: str) -> DelegateOutcome:
        """Reconcile the current turn's evidence and report the durable state."""

        await self._ensure_restored()
        turn = self._current_turn(task_ref)
        if turn is None:
            return DelegateOutcome(diagnostic=SACHIMA_DELEGATE_UNKNOWN_TASK)
        return await self._exclusive(
            turn.turn_key, lambda: self._reconcile(turn.turn_key)
        )

    async def cancel(self, task_ref: str) -> DelegateOutcome:
        """Cancel this task's Run — never the task, never either Session."""

        await self._ensure_restored()
        turn = self._current_turn(task_ref)
        if turn is None:
            return DelegateOutcome(diagnostic=SACHIMA_DELEGATE_UNKNOWN_TASK)
        return await self._exclusive(
            turn.turn_key, lambda: self._cancel_turn(turn.turn_key)
        )

    async def recover(
        self, task_ref: str, *, delivery: DelegateDelivery | None = None
    ) -> DelegateOutcome:
        """Explicitly resolve one uncertain submission. Never automatic."""

        await self._ensure_restored()
        turn = self._current_turn(task_ref)
        if turn is None:
            return DelegateOutcome(diagnostic=SACHIMA_DELEGATE_UNKNOWN_TASK)
        if turn.lifecycle == "blocked" or turn.diagnostic == SACHIMA_DELEGATE_BLOCKED:
            return self._outcome(turn, diagnostic=SACHIMA_DELEGATE_BLOCKED)
        return await self._exclusive(
            turn.turn_key,
            lambda: self._drive(turn.turn_key, mode="recover", delivery=delivery),
        )

    def result(self, task_ref: str) -> dict[str, Any] | None:
        """The durable result of this task's latest settled terminal."""

        binding = self._state.read_task(task_ref)
        if binding is None:
            return None
        if binding.current_turn_key is not None:
            current = self._state.read_turn(binding.current_turn_key)
            if current is not None and (
                current.lifecycle == "blocked"
                or current.diagnostic == SACHIMA_DELEGATE_BLOCKED
            ):
                return self._outcome(
                    current, diagnostic=SACHIMA_DELEGATE_BLOCKED
                ).as_dict()
        for turn_key in reversed(binding.turn_keys):
            event = self._state.result_for_turn(turn_key)
            if event is None:
                continue
            payload = event.as_dict()
            try:
                payload["full_result"] = self._state.read_full_result(
                    event.full_result_ref
                )
            except DelegateStateError:
                payload["full_result"] = ""
            return payload
        return None

    async def _reconcile(self, turn_key: str) -> DelegateOutcome:
        """Reconcile one turn: trusted terminal evidence closes it, or nothing."""

        turn = self._state.read_turn(turn_key)
        if turn is None:
            return DelegateOutcome(turn_key=turn_key, diagnostic=SACHIMA_DELEGATE_UNKNOWN_TASK)
        if turn.lifecycle == "blocked" or turn.diagnostic == SACHIMA_DELEGATE_BLOCKED:
            return self._outcome(turn, diagnostic=SACHIMA_DELEGATE_BLOCKED)
        if turn.lifecycle == "admission_failed":
            # A settled pre-accept failure is read, never re-driven: the exact
            # key already proved there is nothing to find, and re-running the
            # row would only re-time a round that has a frozen terminal.
            return self._outcome(turn, diagnostic=SACHIMA_DELEGATE_DISPATCH_FAILED)
        if turn.lifecycle == "terminal":
            event = self._state.result_for_turn(turn_key)
            if event is not None and event.im_sink in {"failed", "uncertain"}:
                await self._reconcile_im_sink(event, turn)
            return self._outcome(turn, terminal=event.terminal if event else None)
        if turn.lifecycle in {"admitted"}:
            result = await self._observe_once(turn)
            if result is not None:
                return await self._close_terminal(turn_key, result)
            return self._outcome(turn)
        return await self._drive(turn_key, mode="reconcile", delivery=None)

    async def _observe_once(self, turn: DelegateTurnRecord) -> Any:
        try:
            return await asyncio.to_thread(
                self._binding.backend.observe_run_result, turn.backend_handle
            )
        except asyncio.CancelledError:
            raise
        except BaseException:
            logger.warning(SACHIMA_DELEGATE_OBSERVATION_LOST)
            return None

    async def _cancel_turn(self, turn_key: str) -> DelegateOutcome:
        """The user cancel path: reconcile, then one Run-scoped cancel at most."""

        turn = self._state.read_turn(turn_key)
        if turn is None:
            return DelegateOutcome(turn_key=turn_key, diagnostic=SACHIMA_DELEGATE_UNKNOWN_TASK)
        if turn.lifecycle == "blocked" or turn.diagnostic == SACHIMA_DELEGATE_BLOCKED:
            return self._outcome(turn, diagnostic=SACHIMA_DELEGATE_BLOCKED)
        if turn.lifecycle == "terminal":
            event = self._state.result_for_turn(turn_key)
            return self._outcome(turn, terminal=event.terminal if event else None)
        if turn.cancellation in {"in_flight", "uncertain"}:
            # A repeated call joins the existing state: it reconciles, and it
            # never issues a second cancel side effect.
            result = await self._observe_once(turn)
            if result is not None:
                return await self._close_terminal(turn_key, result)
            return self._outcome(turn)
        if turn.lifecycle != "admitted":
            return self._outcome(turn, diagnostic=SACHIMA_DELEGATE_NOT_CONTINUABLE)

        turn = self._state.update_turn(turn_key, cancellation="in_flight")
        try:
            outcome = await asyncio.to_thread(
                self._binding.backend.cancel_run, turn.backend_handle
            )
        except asyncio.CancelledError:
            raise
        except BaseException:
            logger.warning(SACHIMA_DELEGATE_OBSERVATION_LOST)
            outcome = None

        if outcome is not None and getattr(outcome, "settled", False):
            result = getattr(outcome, "result", None)
            if result is not None:
                return await self._close_terminal(turn_key, result)
        turn = self._state.update_turn(turn_key, cancellation="uncertain")
        return self._outcome(turn, diagnostic=SACHIMA_DELEGATE_BLOCKED)

    # -- startup restoration (I7, §5.3) ------------------------------------- #
    async def _ensure_restored(self) -> None:
        async with self._restore_lock:
            if self._restored:
                return
            await self._restore_locked()

    async def restore(self) -> dict[str, Any]:
        """Complete the startup barrier before any new admission is allowed."""

        async with self._restore_lock:
            if self._restored:
                return {"restored": 0, "already": True}
            return await self._restore_locked()

    async def _restore_locked(self) -> dict[str, Any]:
        execution = 0
        identities = 0
        sinks = 0
        try:
            turns = self._state.list_turns()
        except DelegateStateError:
            logger.warning(SACHIMA_DELEGATE_BLOCKED)
            turns = ()

        for turn in turns:
            if turn.lifecycle in {"terminal", "admission_failed"}:
                continue
            execution += 1
            await self._exclusive(
                turn.turn_key, lambda key=turn.turn_key: self._restore_turn(key)
            )

        # Execution restoration can finish a crash-interrupted terminal write,
        # so identities must be selected from a fresh task/turn snapshot.
        for task in self._state.list_tasks():
            if task.current_turn_key is None:
                continue
            turn = self._state.read_turn(task.current_turn_key)
            if turn is None or turn.lifecycle != "terminal":
                continue
            try:
                event = self._state.result_for_turn(turn.turn_key)
            except DelegateStateError:
                event = None
            if event is None:
                self._state.update_turn(
                    turn.turn_key, diagnostic=SACHIMA_DELEGATE_BLOCKED
                )
                continue
            if self._restore_terminal_identity(turn):
                identities += 1

        summaries = await self._restore_summaries()
        sinks = await self._restore_sinks()
        self._restored = True
        self._fresh_graph = False
        return {
            "restored": execution,
            "identities": identities,
            "summaries": summaries,
            "sinks": sinks,
        }

    async def _restore_turn(self, turn_key: str) -> DelegateOutcome:
        """One nonterminal turn, restored under its own section.

        A fresh graph is the only thing that may reclassify a found
        ``in_flight`` to ``uncertain``, and this is where it does it: the process
        that owned those attempts is gone, so nothing can settle them but a
        later observation.
        """

        turn = self._state.read_turn(turn_key)
        if turn is None:
            return DelegateOutcome(turn_key=turn_key, diagnostic=SACHIMA_DELEGATE_UNKNOWN_TASK)
        try:
            event = self._state.result_for_turn(turn_key)
        except DelegateStateError:
            return self._blocked(turn, SACHIMA_DELEGATE_BLOCKED)
        if event is not None:
            return await self._finalize_terminal_event(turn, event)
        if turn.cancellation == "in_flight":
            turn = self._state.update_turn(turn_key, cancellation="uncertain")
        if turn.receipt == "in_flight":
            turn = self._state.update_turn(turn_key, receipt="uncertain")

        disposition, record, code = self._classify(turn)
        return await self._apply(
            turn, disposition, record, code, delivery=None, restoring=True
        )

    def _restore_pending_identity(self, turn: DelegateTurnRecord) -> None:
        """Rebuild only what a pending intent authorizes: intent + identity."""

        self._binding.backend.rehydrate_pending_intent(turn.task_id, turn.dispatch_ref)
        self._restore_port_session(turn)

    def _restore_accepted_identity(self, turn: DelegateTurnRecord, record: Any) -> None:
        """Reattach the accepted backend state and the read-model source.

        Everything is keyed on the record the snapshot returned — never on the
        task's latest — so a task with two accepted Runs rebinds the one this
        turn is actually about.
        """

        self._binding.backend.attach_existing(turn.task_id, binding=record)
        self._restore_port_session(turn)
        self._binding.dispatcher.rehydrate_source_binding(
            turn.task_id, turn.spine_session_id, binding=record
        )

    def _restore_port_session(self, turn: DelegateTurnRecord) -> None:
        from sachima_supervisor.runtime_spine.launch_spec import build_launch_spec

        spec = build_launch_spec(
            task_id=turn.task_id,
            agent_kind=_DELEGATE_AGENT_KIND,
            mode_flags={"needs_agent": True},
            roles=_DELEGATE_ROLES,
            refs=turn.launch_refs,
        )
        self._binding.port.restore_attached(
            turn.task_id, spec, session_id=turn.spine_session_id
        )

    def _restore_terminal_identity(self, turn: DelegateTurnRecord) -> bool:
        """Restore a settled task's sealed identity — no permit, no observer.

        A terminal task is not consuming ARS capacity, but it is still
        continuable, and continuation needs the backend and port to know the
        task. Its own last accepted snapshot is required: missing, pending, or
        unreadable evidence leaves control and continuation blocked, with the
        durable binding and result retained.
        """

        try:
            record = self._ledger.snapshot_exact(
                turn.task_id, turn.backend_handle, turn.dispatch_ref
            )
        except BaseException:
            logger.warning(SACHIMA_DELEGATE_BLOCKED)
            self._state.update_turn(turn.turn_key, diagnostic=SACHIMA_DELEGATE_BLOCKED)
            return False
        if record is None or record.state != "accepted":
            self._state.update_turn(turn.turn_key, diagnostic=SACHIMA_DELEGATE_BLOCKED)
            return False
        try:
            self._binding.backend.attach_existing(turn.task_id, binding=record)
            self._restore_port_session(turn)
        except BaseException:
            logger.warning(SACHIMA_DELEGATE_BLOCKED)
            self._state.update_turn(turn.turn_key, diagnostic=SACHIMA_DELEGATE_BLOCKED)
            return False
        if turn.diagnostic == SACHIMA_DELEGATE_BLOCKED:
            self._state.update_turn(turn.turn_key, diagnostic=None)
        return True

    async def _restore_summaries(self) -> int:
        """Settle every derivative a crash left mid-attempt, before any sink.

        A never-attempted ``pending`` slot is claimed once here — that is the
        one replay startup is allowed. A recovered ``in_flight`` slot settles to
        ``unavailable`` without a second provider call, because a claimed
        attempt whose outcome nobody observed is not an attempt that can safely
        be made again.
        """

        settled = 0
        try:
            events = self._state.list_results()
        except DelegateStateError:
            logger.warning(SACHIMA_DELEGATE_BLOCKED)
            return 0
        for event in events:
            summary = self._summary_for_event(event)
            if summary is not None and summary.settled:
                continue
            turn = self._state.read_turn(event.turn_key)
            if turn is None or turn.lifecycle != "terminal":
                # An unfinished turn's derivative belongs to the terminal
                # closure, under that turn's own exclusion — not to this pass.
                continue
            await self._exclusive(
                turn.turn_key, lambda event=event: self._settle_summary(event)
            )
            settled += 1
        return settled

    async def _restore_sinks(self) -> int:
        """Retry unattempted sinks; reclassify interrupted attempts safely."""

        moved = 0
        try:
            events = self._state.list_results()
        except DelegateStateError:
            logger.warning(SACHIMA_DELEGATE_BLOCKED)
            return 0
        for event in events:
            if event.im_sink == "in_flight":
                event = self._state.update_result(event.event_id, im_sink="uncertain")
                moved += 1
                # An interrupted attempt on a *card* sink is owed the one patch
                # that makes the durable state visible again. A card is patched
                # in place, so unlike a text body it cannot become a second
                # message — which is why this reclassification is followed
                # through instead of being left for an explicit reconciliation.
                if await self._reconcile_restored_card(event):
                    moved += 1
            if event.hermes_sink == "in_flight":
                event = self._state.update_result(event.event_id, hermes_sink="pending")
                moved += 1
            if event.im_sink == "pending":
                turn = self._state.read_turn(event.turn_key)
                if turn is None or turn.lifecycle != "terminal":
                    logger.warning(SACHIMA_DELEGATE_BLOCKED)
                    continue
                await self._exclusive(
                    turn.turn_key,
                    lambda event=event, turn=turn: self._reconcile_im_sink(event, turn),
                )
                moved += 1
        return moved

    async def _reconcile_restored_card(self, event: DelegateResultEvent) -> bool:
        """Patch the one already-bound card whose delivery a restart interrupted.

        Startup may reconcile a *confirmed* card binding from durable state, and
        only that. Three guards say so: a non-card origin is left alone, because
        re-sending a text body is how one terminal becomes two messages; a card
        with no confirmed ``message_id`` is left alone, because the prior send's
        outcome is unknown and sending again is how one Task ends up with two
        cards; and a turn that is not terminal has nothing to reconcile here.

        Nothing in this path resubmits to ARS, re-reads the Run, or re-runs the
        summariser — it projects state that is already durable.
        """

        turn = self._state.read_turn(event.turn_key)
        if turn is None or turn.lifecycle != "terminal":
            return False
        if self._card_channel(turn.origin, None) is None:
            return False
        projection = self._read_card(event.task_ref)
        if projection is None or projection.card_message_id is None:
            return False
        await self._exclusive(
            turn.turn_key,
            lambda: self._reconcile_im_sink(event, turn),
        )
        return True

    # -- the Task status card (plan §4, §5) ---------------------------------- #
    #
    # One card per ``dtask_*``, one round row per Turn, patched in place. The
    # card never decides anything: every method here reads durable state, writes
    # a projection, and makes at most one adapter call. A card that fails is a
    # failed *presentation*, which is why nothing below can change a lifecycle,
    # a permit, a result, or a sink other than the card's own.
    def _card_channel(
        self, origin: DelegateOrigin, delivery: DelegateDelivery | None
    ) -> DelegateDelivery | None:
        """This origin's card capability, or ``None`` for the legacy text path."""

        channel = self._delivery_for(origin, delivery)
        if channel is None or not channel.card_capable:
            return None
        return channel

    def _read_card(self, task_ref: str) -> DelegateCardProjection | None:
        try:
            return self._state.read_card(task_ref)
        except (DelegateStateError, DelegateCardError):
            logger.warning(SACHIMA_DELEGATE_CARD_UNAVAILABLE)
            return None

    def _save_card(
        self, projection: DelegateCardProjection
    ) -> DelegateCardProjection | None:
        """Persist one forward card state as a revision of its own.

        The revision is claimed from the projection *this* caller read, so a
        writer whose snapshot has since been overtaken conflicts and is dropped
        instead of replacing newer state with its own older view of the card.
        A dropped presentation write changes no task truth: the next transition
        rebuilds the snapshot from durable state and projects that.
        """

        try:
            return self._state.advance_card(next_projection_revision(projection))
        except (DelegateStateError, DelegateCardError):
            logger.warning(SACHIMA_DELEGATE_CARD_UNAVAILABLE)
            return None

    def _write_card(
        self, projection: DelegateCardProjection
    ) -> DelegateCardProjection | None:
        """Persist a projection that already selected its own revision."""

        try:
            return self._state.advance_card(projection)
        except (DelegateStateError, DelegateCardError):
            logger.warning(SACHIMA_DELEGATE_CARD_UNAVAILABLE)
            return None

    def _sealed_role(self, agent_id: str, role: Any) -> str | None:
        """The role this AGENT actually holds, or ``None`` — never a guess.

        The card's ``角色`` line is the role sealed into the admitted execution
        contract. A role the validated policy does not assign to this exact
        AGENT is not narrowed, aliased, or accepted "close enough": it simply is
        not sealed, and the card says so rather than inventing one.
        """

        if type(role) is not str or not role.strip():
            return None
        assignment = self._role_policy.for_agent(agent_id)
        if assignment is None or not assignment.holds(role=role, division=None):
            return None
        return role

    async def _ensure_card(
        self,
        binding: DelegateTaskBinding,
        turn: DelegateTurnRecord,
        delivery: DelegateDelivery | None,
    ) -> None:
        """Create this Task's card projection and send the first snapshot.

        Called with the durable Task/origin allocation — before capacity waiting
        and before anything could submit — so the complete copyable ``dtask_*``
        becomes visible through the card rather than through lifecycle text. A
        Task that already has a card (a continuation, a restart) only reuses it;
        nothing here can mint a second one.
        """

        channel = self._card_channel(binding.origin, delivery)
        if channel is None:
            return
        if self._read_card(binding.task_ref) is not None:
            return
        earlier = self._reconstructed_rounds(binding, turn.turn_key)
        try:
            projection = new_card_projection(
                task_ref=binding.task_ref,
                task_created_at=self._task_start_boundary(earlier),
                origin_platform=binding.origin.platform,
                origin_chat_id=binding.origin.chat_id,
                origin_session_id=binding.origin.session_id,
                origin_thread_id=binding.origin.thread_id,
                locale=self._card_locale,
                agent_id=binding.agent_id,
                model=turn.requested_model,
                effort=turn.requested_effort,
                task_description=sanitize_card_line(turn.task_description),
            )
            for row in earlier:
                projection = append_round(
                    projection,
                    turn_key=row["turn_key"],
                    purpose=row["purpose"],
                    admitted_role=row["admitted_role"],
                    started_at=row["started_at"],
                )
                projection = advance_round(
                    projection,
                    row["turn_key"],
                    status=row["status"],
                    settled_at=row["settled_at"],
                )
            self._state.put_card(projection)
        except (DelegateStateError, DelegateCardError):
            logger.warning(SACHIMA_DELEGATE_CARD_UNAVAILABLE)
            return
        await self._flush_card(binding.task_ref, binding.origin, channel, force=True)

    def _reconstructed_rounds(
        self, binding: DelegateTaskBinding, current_turn_key: str
    ) -> list[dict[str, Any]]:
        """Safe persisted round summaries for a Task that predates its card.

        First activation does not backfill settled history, but a Task that
        gains a card on its *next* continuation must still number that round by
        the durable ``turn_keys`` order — a continuation announced as ``第 1 轮``
        would be a plainly untrue header. Only persisted, already-sanitized
        material is reconstructed: the sealed purpose, the sealed role, the
        lifecycle boundaries, and the recorded terminal. Nothing about the
        earlier Runs' ARS Sessions was persisted for the card, so those rows
        make no Session claim at all and cannot become evidence later.
        """

        rows: list[dict[str, Any]] = []
        for turn_key in binding.turn_keys:
            if turn_key == current_turn_key:
                continue
            try:
                prior = self._state.read_turn(turn_key)
            except DelegateStateError:
                prior = None
            if prior is None:
                # The turn_key is durable proof the round happened; this host
                # simply retains nothing readable about it. Keeping the row
                # preserves the numbering and says exactly that, which beats
                # both silently renumbering and inventing a terminal.
                rows.append(
                    {
                        "turn_key": turn_key,
                        "purpose": None,
                        "admitted_role": None,
                        "status": "recovering",
                        "started_at": None,
                        "settled_at": None,
                    }
                )
                continue
            rows.append(
                {
                    "turn_key": turn_key,
                    "purpose": sanitize_card_line(prior.task_description),
                    "admitted_role": sanitize_card_line(prior.admitted_role),
                    "status": self._reconstructed_status(prior),
                    "started_at": safe_card_instant(prior.accepted_at),
                    "settled_at": safe_card_instant(self._terminal_instant(turn_key)),
                }
            )
        return rows

    @staticmethod
    def _reconstructed_status(prior: DelegateTurnRecord) -> str:
        """One persisted Turn lifecycle, as the round state it really reached."""

        if prior.lifecycle == "terminal" and prior.terminal_status in _CARD_TERMINALS:
            return prior.terminal_status
        if prior.lifecycle == "admission_failed":
            return "rejected"
        return "recovering"

    def _terminal_instant(self, turn_key: str) -> str | None:
        try:
            event = self._state.result_for_turn(turn_key)
        except DelegateStateError:
            return None
        return None if event is None else event.terminal_at

    @staticmethod
    def _task_start_boundary(earlier: list[dict[str, Any]]) -> str | None:
        """The Task duration's start: this allocation, or no claim at all.

        Only a genuine first allocation — no earlier round at all — starts now,
        because that instant *is* the Task allocation this method was called
        for. It is the one moment a host can honestly say a Task began.

        A Task that already ran rounds began before anything here observed it,
        and this host retains no Task-level boundary for it. The round
        boundaries it *does* retain are not a substitute: a round's
        ``started_at`` is when a **Turn** was admitted, which is a fact about
        that Turn and says nothing about when the Task was allocated — the
        queue wait, the earlier rounds, and the allocation itself all precede
        it. Borrowing one would silently under-report the Task's whole life as
        a confident number, and a wall-clock reading would invent a start such
        a Task demonstrably did not have. Both are refused: the card renders the
        honest unavailable value instead, which is what a missing boundary is.
        """

        return None if earlier else _utc_status_time()

    async def _card_pre_accept(
        self,
        turn: DelegateTurnRecord,
        status: str,
        delivery: DelegateDelivery | None,
    ) -> None:
        projection = self._read_card(turn.task_ref)
        if projection is None:
            return
        try:
            updated = replace(projection, pre_accept_status=status)
        except DelegateCardError:
            return
        if self._save_card(updated) is None:
            return
        await self._flush_card(turn.task_ref, turn.origin, delivery, force=True)

    async def _card_open_round(
        self, turn: DelegateTurnRecord, delivery: DelegateDelivery | None
    ) -> None:
        """Append this Turn's round row, once, before anything could submit."""

        projection = self._read_card(turn.task_ref)
        if projection is None:
            return
        try:
            updated = append_round(
                replace(projection, pre_accept_status="submitting"),
                turn_key=turn.turn_key,
                purpose=sanitize_card_line(turn.task_description),
                admitted_role=sanitize_card_line(turn.admitted_role),
                started_at=_utc_status_time(),
            )
        except DelegateCardError:
            logger.warning(SACHIMA_DELEGATE_CARD_UNAVAILABLE)
            return
        if updated == projection or self._save_card(updated) is None:
            return
        await self._flush_card(turn.task_ref, turn.origin, delivery, force=True)

    @staticmethod
    def _admitted_session_origin(record: Any) -> str | None:
        """How this Run reached its ARS Session, as the admission recorded it.

        The submit either asked the daemon to create a Session or named one to
        load, and the accepted binding keeps that mode with the dispatch it
        belongs to. That is the only admissible answer. A round's *position* in
        the Task is not evidence: being round one says nothing about what the
        daemon actually served, and a Task whose card was created late has
        rounds whose real first Session nobody here observed. A record that
        carries no mode claims neither origin.
        """

        refs = getattr(record, "resolver_refs", None)
        if not isinstance(refs, Mapping):
            return None
        return _SESSION_MODE_TO_ORIGIN.get(refs.get("session_mode"))

    @staticmethod
    def _earlier_rounds(
        projection: DelegateCardProjection, turn_key: str
    ) -> tuple[Any, ...]:
        """Every round of this Task that opened before the given one."""

        earlier: list[Any] = []
        for row in projection.rounds:
            if row.turn_key == turn_key:
                break
            earlier.append(row)
        return tuple(earlier)

    @staticmethod
    def _round_row(
        projection: DelegateCardProjection, turn: DelegateTurnRecord
    ) -> DelegateCardProjection:
        """This Turn's row, opened from its own record if it is not there yet.

        :meth:`_card_open_round` normally opens the row before anything could
        submit, but the Task/card projection becomes durable *before* that — so
        a host that died in between would otherwise leave the round, and with
        it the terminal, permanently unprojectable. Healing reads the same
        sealed Turn record the normal path reads, so it can neither invent a
        purpose nor renumber a round; ``append_round`` makes it a no-op once
        the row exists.
        """

        return append_round(
            projection,
            turn_key=turn.turn_key,
            purpose=sanitize_card_line(turn.task_description),
            admitted_role=sanitize_card_line(turn.admitted_role),
            started_at=safe_card_instant(turn.accepted_at),
        )

    def _card_admitted_round(
        self, turn: DelegateTurnRecord, record: Any
    ) -> DelegateCardProjection | None:
        """Record this round's Run/Session evidence at the moment of admission.

        The evidence is the ledger's own accepted record — the Run this turn
        really got and the ARS Session the daemon really answered with. Whether
        that adds up to reuse is :func:`project_session_evidence`'s decision,
        never this method's, and never the card's.
        """

        projection = self._read_card(turn.task_ref)
        if projection is None:
            return None
        try:
            projection = self._round_row(projection, turn)
        except DelegateCardError:
            logger.warning(SACHIMA_DELEGATE_CARD_UNAVAILABLE)
            return None
        session_ref = derive_session_ref(getattr(record, "ars_session_id", None))
        run_ref = getattr(record, "run_ref", None)
        earlier = self._earlier_rounds(projection, turn.turn_key)
        session_origin = (
            self._admitted_session_origin(record) if session_ref is not None else None
        )
        try:
            updated = advance_round(
                projection,
                turn.turn_key,
                status="accepted",
                session_ref=session_ref,
                run_ref=run_ref,
                session_origin=session_origin,
                admitted_role=sanitize_card_line(turn.admitted_role),
                session_projection=project_session_evidence(
                    earlier_rounds=earlier,
                    session_ref=session_ref,
                    run_ref=run_ref,
                    session_origin=session_origin,
                    settled=False,
                ),
            )
        except DelegateCardError:
            logger.warning(SACHIMA_DELEGATE_CARD_UNAVAILABLE)
            return None
        return self._save_card(updated)

    async def _card_round_state(
        self,
        turn: DelegateTurnRecord,
        status: str,
        delivery: DelegateDelivery | None,
        *,
        force: bool = True,
        settled_at: str | None = None,
    ) -> None:
        projection = self._read_card(turn.task_ref)
        if projection is None:
            return
        if projection.round_for(turn.turn_key) is None:
            await self._card_pre_accept(turn, status, delivery)
            return
        try:
            updated = advance_round(
                projection, turn.turn_key, status=status, settled_at=settled_at
            )
        except DelegateCardError:
            # A settled round is not reopened by a later transient state.
            return
        if updated == projection:
            await self._flush_card(turn.task_ref, turn.origin, delivery, force=force)
            return
        if self._save_card(updated) is None:
            return
        await self._flush_card(turn.task_ref, turn.origin, delivery, force=force)

    async def _card_terminal_round(
        self,
        turn: DelegateTurnRecord,
        event: DelegateResultEvent,
        summary: Any,
        channel: DelegateDelivery,
    ) -> SendSettlement | None:
        """Settle this round's row and flush the one final projection revision."""

        projection = self._read_card(turn.task_ref)
        if projection is None:
            return None
        try:
            projection = self._round_row(projection, turn)
        except DelegateCardError:
            logger.warning(SACHIMA_DELEGATE_CARD_UNAVAILABLE)
            return None
        row = projection.round_for(turn.turn_key)

        result_summary = None
        if event.terminal == "completed":
            result_summary = sanitize_card_line(
                projected_summary_text(
                    summary,
                    full_result_ref=event.full_result_ref,
                    source_digest=self._current_source_digest(event.full_result_ref),
                )
            )
        earlier = self._earlier_rounds(projection, turn.turn_key)
        try:
            updated = advance_round(
                projection,
                turn.turn_key,
                status=event.terminal,
                settled_at=event.terminal_at,
                result_summary=result_summary,
                session_projection=project_session_evidence(
                    earlier_rounds=earlier,
                    session_ref=row.session_ref,
                    run_ref=row.run_ref,
                    session_origin=row.session_origin,
                    settled=True,
                ),
            )
        except DelegateCardError:
            logger.warning(SACHIMA_DELEGATE_CARD_UNAVAILABLE)
            return None
        if updated != projection and self._save_card(updated) is None:
            return None
        return await self._flush_card(
            turn.task_ref, turn.origin, channel, force=True
        )

    def _card_pacing_allows(self, task_ref: str) -> bool:
        with self._guard:
            last = self._card_patched_at.get(task_ref)
        return (
            last is None
            or (time.monotonic() - last) >= self._running_patch_interval
        )

    async def _flush_card(
        self,
        task_ref: str,
        origin: DelegateOrigin,
        delivery: DelegateDelivery | None,
        *,
        force: bool = False,
    ) -> SendSettlement | None:
        """Make at most one adapter call for one selected projection revision.

        Intermediate updates coalesce; a forced flush — an acceptance, a state
        change, a terminal — never does. The adapter owns transport retry, so
        this performs exactly one call per revision and leaves another attempt
        to later reconciliation or startup recovery.

        The whole publication lives inside this Task's section: the state is
        read, the revision is selected, the create-or-patch decision is made,
        the fail-closed premark is persisted, the one call is issued, and its
        outcome is settled — and only then is the section released. Deciding
        outside it decides from a read another publisher may already have
        overtaken, which is how two flushes each see "no message id yet" and
        each create a card for one Task. Holding it across the call is also what
        makes issue order and platform order the same order: two calls for one
        card can complete in either order, so an older one that was merely slow
        would otherwise land last and un-complete a round the user saw finish.
        """

        channel = self._card_channel(origin, delivery)
        if channel is None:
            return None
        if not force and not self._card_pacing_allows(task_ref):
            return None
        async with self._card_publication(task_ref):
            projection = self._read_card(task_ref)
            if projection is None:
                return None
            if (
                projection.card_message_id is None
                and projection.card_sink_state == "uncertain"
            ):
                # A send may or may not have landed. Sending again is how one
                # Task ends up with two cards, so the uncertain binding is
                # retained for operator reconciliation instead.
                await self._degrade_card(projection, channel)
                return None
            try:
                projection = projected_revision(projection, at=_utc_status_time())
            except DelegateCardError:
                return None
            saved = self._write_card(projection)
            if saved is None:
                return None

            payload, _fallback = bounded_card_payload(
                saved, limit=channel.limit, measure=channel.measure
            )
            with self._guard:
                self._card_patched_at[task_ref] = time.monotonic()
            if payload is None:
                # Fail closed *before* the adapter call: API rejection is not
                # control flow, and a bounded card that cannot be bounded
                # further degrades to the compact Markdown the user still needs.
                await self._degrade_card(saved, channel)
                return SendSettlement(
                    state="failed", diagnostic=SACHIMA_DELEGATE_CARD_UNAVAILABLE
                )

            message_id = saved.card_message_id
            if message_id is None:
                premarked = self._premark_card_send(saved)
                if premarked is None:
                    # The gap could not be recorded, so it must not be opened.
                    return None
                saved = premarked
                settlement = await perform_settled_send(
                    lambda: channel.send_card(payload)
                )
            else:
                settlement = await perform_settled_send(
                    lambda: channel.patch_card(message_id, payload)
                )
            await self._settle_card(saved, settlement, channel)
        return settlement

    def _premark_card_send(
        self, projection: DelegateCardProjection
    ) -> DelegateCardProjection | None:
        """Persist the fail-closed no-id state *before* a card is created.

        A create is the one card call whose side effect this host cannot
        address afterwards: the platform has the message, and the only thing
        that ties it back is a ``message_id`` that arrives with the reply. A
        host that died between the two would restart holding "nothing was ever
        sent" and would send a second card for the same Task — so the gap is
        recorded before it can be opened, and closed by the settlement that
        follows it.

        Recording it is not a guess about the outcome. ``uncertain`` is exactly
        what is true from here until the reply — it may or may not have landed —
        and it is the existing sink state whose meaning already is "keep this
        binding for reconciliation and never send again". Nothing new is
        introduced to carry it: an outbox or a cross-restart send id would be a
        second durable authority over a card this layer only ever projects.
        """

        return self._save_card(settle_card_sink(projection, state="uncertain"))

    async def _settle_card(
        self,
        projection: DelegateCardProjection,
        settlement: SendSettlement,
        channel: DelegateDelivery,
    ) -> None:
        """Persist one card delivery outcome, and degrade at most once.

        The outcome is applied to the projection as it stands *now*, not to the
        snapshot that was rendered: a delivery fact is about the message, and
        writing it back through a stale snapshot would undo whatever the round
        moved on to while the call was in flight. Losing it is worse still — a
        forgotten binding is how the next flush sends this Task a second card —
        so the settlement rides on top of the newest state instead.
        """

        current = self._read_card(projection.task_ref) or projection
        if settlement.confirmed:
            message_id = (
                current.card_message_id
                or projection.card_message_id
                or settlement.message_id
            )
            if message_id is None:
                # Confirmed with no id: the card exists but this host cannot
                # address it, so it is recorded as uncertain rather than bound
                # to nothing.
                self._save_card(settle_card_sink(current, state="uncertain"))
                return
            try:
                bound = bind_card_message(
                    current,
                    message_id=message_id,
                    revision=current.revision,
                    at=current.last_projected_at or _utc_status_time(),
                )
            except DelegateCardError:
                logger.warning(SACHIMA_DELEGATE_CARD_UNAVAILABLE)
                return
            if bound != current:
                self._save_card(bound)
            return

        settled = current
        failed = settle_card_sink(current, state=settlement.state)
        if failed != current:
            settled = self._save_card(failed) or current
        await self._degrade_card(settled, channel)

    async def _degrade_card(
        self, projection: DelegateCardProjection, channel: DelegateDelivery
    ) -> None:
        """One compact sanitized Markdown notice per card-sink failure episode.

        Cardinality, not a rate limit: the notice exists so the complete
        ``dtask_*`` still reaches the user when rich delivery could not. It is
        persisted with the sink settlement, so a restart cannot turn one episode
        into a second notice.
        """

        if projection.degraded_notice:
            return
        try:
            marked = self._save_card(
                settle_card_sink(
                    projection, state=projection.card_sink_state, degraded_notice=True
                )
            )
        except DelegateCardError:
            logger.warning(SACHIMA_DELEGATE_CARD_UNAVAILABLE)
            return
        if marked is None:
            return
        # Compact: the notice carries the same fields in the same order, with
        # as much round history as the platform's own bound allows. The
        # narrowest form keeps the five summary rows — and with them the
        # copyable ``dtask_*`` — which is the whole reason this notice exists.
        body = ""
        for window in (CARD_ROUND_WINDOW, 1, 0):
            body = render_delegation_markdown(marked, window=window)
            if channel.measure(body) <= channel.limit:
                break
        await perform_settled_send(lambda: channel.send_text(body))

    # -- helpers ------------------------------------------------------------ #
    def _current_turn(self, task_ref: Any) -> DelegateTurnRecord | None:
        try:
            binding = self._state.read_task(task_ref)
        except DelegateStateError:
            return None
        if binding is None or binding.current_turn_key is None:
            return None
        return self._state.read_turn(binding.current_turn_key)

    def _delivery_for(
        self, origin: DelegateOrigin, delivery: DelegateDelivery | None
    ) -> DelegateDelivery | None:
        if delivery is not None:
            return delivery
        if self._delivery_factory is None:
            return None
        try:
            return self._delivery_factory(origin)
        except BaseException:
            logger.warning(SACHIMA_DELEGATE_NO_DELIVERY)
            return None

    async def _notify(
        self,
        turn: DelegateTurnRecord,
        text: str,
        delivery: DelegateDelivery | None,
    ) -> None:
        """Deliver one sparse notice, and never let delivery break a lifecycle."""

        channel = self._delivery_for(turn.origin, delivery)
        if channel is None:
            return
        await perform_settled_send(lambda: channel.send_text(text))

    @staticmethod
    def _outcome(
        turn: DelegateTurnRecord,
        *,
        terminal: str | None = None,
        diagnostic: str | None = None,
    ) -> DelegateOutcome:
        return DelegateOutcome(
            task_ref=turn.task_ref,
            turn_key=turn.turn_key,
            lifecycle=turn.lifecycle,
            receipt=turn.receipt,
            cancellation=turn.cancellation,
            turn_ref=turn.turn_ref,
            terminal=terminal or turn.terminal_status,
            diagnostic=diagnostic or turn.diagnostic,
        )


# --------------------------------------------------------------------------- #
# Host-held binding (cleared on every unbind path the composition takes)
# --------------------------------------------------------------------------- #
_coordinator: SachimaDelegateCoordinator | None = None
#: The host's adapter-backed delivery factory. Composition happens from env at
#: startup, which is *before* the Gateway's adapters exist, so the factory is
#: registered separately rather than threaded through the composition root —
#: and a coordinator bound without one still works: it simply records deliveries
#: as failed rather than pretending to have sent them.
_delivery_factory_hook: Callable[[DelegateOrigin], DelegateDelivery | None] | None = None


def set_delegate_delivery_factory(
    factory: Callable[[DelegateOrigin], DelegateDelivery | None] | None,
) -> None:
    """Register the host delivery factory, and give it to a bound coordinator."""

    global _delivery_factory_hook
    _delivery_factory_hook = factory
    if _coordinator is not None:
        _coordinator._delivery_factory = factory


def bound_delegate_coordinator() -> SachimaDelegateCoordinator | None:
    """The coordinator for the currently bound bundle, or ``None``."""

    return _coordinator


def delegate_payload_resolver() -> Callable[[str], str]:
    """The resolver a composed ``arsd`` bundle dispatches and recovers through.

    Late-bound on purpose: composition needs the resolver *before* the
    coordinator that owns the durable store exists, so this hands over a stable
    callable that finds the store when it is actually called. One store, one
    claim-check, no second copy of the task text anywhere.
    """

    def _resolve(payload_ref: str) -> str:
        coordinator = _coordinator
        if coordinator is None:
            raise ValueError(SACHIMA_DELEGATE_UNBOUND)
        return coordinator.state.read_payload(payload_ref)

    return _resolve


def bind_delegate_coordinator(
    binding: Any,
    config: Any,
    *,
    presets: AgentExecutionPresets | None = None,
    role_policy: AgentRolePolicy | None = None,
    delivery_factory: Callable[[DelegateOrigin], DelegateDelivery | None] | None = None,
    summary_provider: DelegateResultSummaryProvider | None = None,
) -> SachimaDelegateCoordinator:
    """Bind one coordinator over an already-composed execution bundle.

    ``summary_provider`` is injected, and omitting it is a valid composition:
    the coordinator then reports every result's summary as ``unavailable`` and
    keeps projecting the durable full-result ref.

    This is also where the deployment's card cadence enters the graph. Reading
    it here rather than defaulting inside the coordinator is what makes it a
    *configured* value: a host that declares one gets it, and the S0 contract
    answers for every host that does not.
    """

    global _coordinator
    _coordinator = SachimaDelegateCoordinator(
        binding,
        config,
        presets=presets,
        role_policy=role_policy,
        delivery_factory=(
            delivery_factory if delivery_factory is not None else _delivery_factory_hook
        ),
        summary_provider=summary_provider,
        running_patch_interval=configured_running_patch_interval(config),
    )
    return _coordinator


def unbind_delegate_coordinator() -> None:
    """Drop the coordinator so a retired bundle stops being dispatched into."""

    global _coordinator
    _coordinator = None
