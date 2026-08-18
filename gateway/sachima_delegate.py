"""Sachima ``/delegate`` — host claim-check and the single delegate coordinator.

This module is the Gateway-side seam for Milestone A of the Sachima delegate
plan. It owns two things and deliberately nothing else:

1. **A process-local payload claim-check** (:class:`_PayloadStore`). The
   delegated task text is private host material: it is held here, and every
   surface that crosses into the Runtime Spine — the dispatch request, the
   durable binding ledger, the canonical event log — carries only an opaque
   ``dlg_<digest>`` ref. The store hands the exact text back to exactly one
   caller (the bundle's injected payload resolver) and discards it the moment
   the submission can no longer need it: on a pre-dispatch failure, or on the
   Run's terminal.

2. **One :class:`SachimaDelegateCoordinator` per bound execution bundle.** It
   is the single source of delegate submissions — the ``/delegate`` command
   today, and the semantic controls a later milestone adds — so there is never
   a second registry, backend, port, dispatcher, or bindings store beside the
   one the host already composed. The coordinator *uses* the bound bundle; it
   never builds one.

Capacity is not a number this module owns. The concurrency bound comes from the
validated live ``server_info.limits.max_concurrent_runs`` the composed backend
negotiated, and there is deliberately no fallback: a host whose daemon never
told it how many Runs it will hold has no business admitting any.

Pure local/offline on import: no process, socket, daemon, Gateway, IM surface,
or AGENT is started here, and no ``agent_run_supervisor`` import happens at any
level — the daemon is reached only through the composed bundle's own lazy
facade. Forbidden terms in this prose are no-leak boundary canaries only, never
behavior.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

__all__ = [
    "DELEGATE_ACCEPTED_TEMPLATE",
    "DELEGATE_CANCELLED_TEMPLATE",
    "DELEGATE_COMPLETED_TEMPLATE",
    "DELEGATE_EMPTY_FINAL_MESSAGE",
    "DELEGATE_FAILED_TEMPLATE",
    "DELEGATE_LOST_TEMPLATE",
    "DELEGATE_REFUSED",
    "DELEGATE_SUBMIT_FAILED_TEMPLATE",
    "DELEGATE_TRUNCATED_SUFFIX",
    "DELEGATE_UNAVAILABLE",
    "DELEGATE_USAGE",
    "DELEGATE_WAITING_TEMPLATE",
    "SACHIMA_DELEGATE_INVALID_POLICY",
    "SACHIMA_DELEGATE_INVALID_TARGET",
    "SACHIMA_DELEGATE_INVALID_TASK_TEXT",
    "SACHIMA_DELEGATE_STABLE_CODES",
    "SACHIMA_DELEGATE_UNBOUND",
    "SACHIMA_DELEGATE_UNKNOWN_PAYLOAD_REF",
    "DelegateSubmission",
    "DelegateTarget",
    "SachimaDelegateCoordinator",
    "bind_delegate_coordinator",
    "bound_delegate_coordinator",
    "delegate_payload_resolver",
    "delegate_payload_store",
    "unbind_delegate_coordinator",
]

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
SACHIMA_DELEGATE_UNBOUND = "sachima_delegate_unbound"
SACHIMA_DELEGATE_UNKNOWN_PAYLOAD_REF = "sachima_delegate_unknown_payload_ref"
SACHIMA_DELEGATE_INVALID_TASK_TEXT = "sachima_delegate_invalid_task_text"
SACHIMA_DELEGATE_INVALID_POLICY = "sachima_delegate_invalid_policy"
SACHIMA_DELEGATE_INVALID_TARGET = "sachima_delegate_invalid_target"
SACHIMA_DELEGATE_DISPATCH_FAILED = "sachima_delegate_dispatch_failed"
SACHIMA_DELEGATE_OBSERVATION_LOST = "sachima_delegate_observation_lost"

SACHIMA_DELEGATE_STABLE_CODES = frozenset(
    {
        SACHIMA_DELEGATE_UNBOUND,
        SACHIMA_DELEGATE_UNKNOWN_PAYLOAD_REF,
        SACHIMA_DELEGATE_INVALID_TASK_TEXT,
        SACHIMA_DELEGATE_INVALID_POLICY,
        SACHIMA_DELEGATE_INVALID_TARGET,
        SACHIMA_DELEGATE_DISPATCH_FAILED,
        SACHIMA_DELEGATE_OBSERVATION_LOST,
    }
)

# --------------------------------------------------------------------------- #
# The complete set of things Sachima ever says about a delegated task.
#
# A submission sends at most three: the acceptance the handler returns, one
# capacity-wait notice *only* when a slot was genuinely unavailable, and
# exactly one terminal. A fourth is possible but rare — one notice that
# observation has gone blind, sent at most once per submission and only after
# an unbroken run of faults. It is explicitly **not** a terminal: the Run is
# still the daemon's to end, the slot is still held, and the real terminal is
# still owed once Sachima can see again. There is deliberately no progress,
# event, or heartbeat message — the observer polls in silence, because a chat
# is not a log.
# --------------------------------------------------------------------------- #
DELEGATE_USAGE = "用法：/delegate <任务>"
DELEGATE_UNAVAILABLE = "外部执行通道未启用，无法委派任务。"
DELEGATE_REFUSED = "任务未能提交，请检查委派配置。"
DELEGATE_ACCEPTED_TEMPLATE = "已接受任务 {task_ref}，完成后会在这里回复。"
DELEGATE_WAITING_TEMPLATE = "任务 {task_ref} 正在等待执行席位…"
DELEGATE_COMPLETED_TEMPLATE = "任务 {task_ref} 已完成：\n{final_message}"
DELEGATE_FAILED_TEMPLATE = "任务 {task_ref} 执行失败（{status}）。"
DELEGATE_CANCELLED_TEMPLATE = "任务 {task_ref} 已取消。"
DELEGATE_SUBMIT_FAILED_TEMPLATE = "任务 {task_ref} 提交失败（{code}）。"
DELEGATE_LOST_TEMPLATE = "任务 {task_ref} 暂时无法确认状态（{code}），仍在等待结果。"
DELEGATE_TRUNCATED_SUFFIX = "\n（输出已截断：{truncate_reason}）"
DELEGATE_EMPTY_FINAL_MESSAGE = "（无输出）"

#: How often the background lifecycle asks whether the Run has ended. Socket
#: API v3 has no push surface, so a bounded poll is the only honest way to
#: learn a terminal — and it stays silent until it finds one.
_DEFAULT_OBSERVE_INTERVAL_SECONDS = 2.0

#: Consecutive observation faults tolerated before Sachima *says* it has gone
#: blind. A disconnect is not evidence a Run ended, so a single fault retries
#: silently; an unbroken run of them is worth one notice. It bounds the
#: speaking only — never the slot, which an accepted Run holds until the
#: daemon says it ended.
_MAX_CONSECUTIVE_OBSERVE_FAILURES = 5

#: Milestone A dispatches plain prompt turns. Standing goals are a separate
#: turn kind and a separate decision.
_DELEGATE_TURN_KIND = "prompt"

#: The claim-check ref prefix. The rest is a random digest, so a ref is opaque
#: by construction: there is no encoding of the task in it to decode, and the
#: whole ref is ``_safe_id``-shaped so the spine accepts it as a payload ref
#: without any further sanitizing on the way in.
_PAYLOAD_REF_PREFIX = "dlg_"

#: The spine roles/agent kind a delegated supervised session is admitted under.
#: They are the port's own admission vocabulary, not the ARS grant: what the
#: external AGENT may do comes from the frozen ``grant_capabilities`` in the
#: host's private config, and nothing here widens it.
_DELEGATE_AGENT_KIND = "local_agent"
_DELEGATE_ROLES = ("read_only",)


class _PayloadStore:
    """One process-local claim-check for delegated task text.

    In-memory only, and deliberately so: the text is never written to the
    binding ledger, the canonical event log, a summary, or a log line, so a
    process that dies with a submission in flight loses the text rather than
    leaving it on disk. What survives a restart is what ARS already recorded —
    which is the durable Run, not Sachima's copy of the prompt.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._payloads: dict[str, str] = {}

    def put(self, text: Any) -> str:
        """Store one task text and return its opaque ref."""

        if type(text) is not str or not text.strip():
            raise ValueError(SACHIMA_DELEGATE_INVALID_TASK_TEXT)
        ref = _PAYLOAD_REF_PREFIX + uuid.uuid4().hex
        with self._lock:
            self._payloads[ref] = text
        return ref

    def resolve(self, payload_ref: Any) -> str:
        """The exact text for ``payload_ref``, or fail closed.

        The failure carries the stable code and nothing else — not the ref that
        was presented, and certainly not a stored payload. A caller with an
        unknown ref learns only that it is unknown.
        """

        text: str | None = None
        if type(payload_ref) is str:
            with self._lock:
                text = self._payloads.get(payload_ref)
        if text is None:
            raise ValueError(SACHIMA_DELEGATE_UNKNOWN_PAYLOAD_REF)
        return text

    def discard(self, payload_ref: Any) -> None:
        """Forget one payload. Idempotent: both cleanup paths may reach it."""

        if type(payload_ref) is not str:
            return
        with self._lock:
            self._payloads.pop(payload_ref, None)

    def clear(self) -> None:
        with self._lock:
            self._payloads.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._payloads)


#: The one store per process. The resolver injected into the composed bundle
#: and the coordinator that fills it are two views of *this* object; a second
#: store would mean a dispatch resolving a ref nobody put there.
_PAYLOAD_STORE = _PayloadStore()


def delegate_payload_store() -> _PayloadStore:
    """The process-local claim-check store."""

    return _PAYLOAD_STORE


def delegate_payload_resolver() -> Callable[[str], str]:
    """The resolver a composed ``arsd`` bundle dispatches through.

    Handing over the bound method rather than the store is the point: the
    dispatcher gets exactly one capability — turn a ref it was given into the
    text it names — and no way to enumerate, store, or discard anything.
    """

    return _PAYLOAD_STORE.resolve


def _delegate_launch_refs(config: Any) -> tuple[str, ...]:
    """The distinct policy refs a delegated session is admitted under.

    Milestone A's command surface is exactly ``/delegate <task>`` — no agent,
    model, effort, or workspace selector — so there is nothing that could
    *choose* between two configured options. A config that offers a choice is
    therefore not one this path can honor, and it fails closed rather than
    picking for the operator: silently taking "the first" workspace or agent is
    how a delegated Run lands somewhere nobody approved.

    That rule is per mapping, and it is checked before anything else happens:
    each of the five must have exactly one configured key. What the backend
    then wants is the *set* of refs to resolve against, not one entry per
    category — it matches the refs against each mapping and demands exactly one
    match, so a ref repeated five times reads as five matches and is denied.
    Nothing in the config contract says the categories use different refs, and
    the canonical fixtures key agent, model, effort and run-limits with a
    single ``policy_`` ref, so the repeat is the ordinary case rather than the
    odd one. Refs are therefore collapsed to first-seen order.

    Collapsing repeats is not the same as collapsing options: the
    exactly-one-key check above has already run per mapping, so a category
    offering two refs is refused before it can be deduplicated into one.
    Workspace and policy refs cannot collide into each other either — the
    config grammar prefixes them ``ws_`` and ``policy_``.
    """

    refs: list[str] = []
    for mapping in (
        getattr(config, "workspace_by_ref", None),
        getattr(config, "agent_by_policy_ref", None),
        getattr(config, "model_by_policy_ref", None),
        getattr(config, "effort_by_policy_ref", None),
        getattr(config, "run_limits_by_policy_ref", None),
    ):
        keys = list(mapping) if isinstance(mapping, dict) or hasattr(mapping, "keys") else []
        if len(keys) != 1:
            raise ValueError(SACHIMA_DELEGATE_INVALID_POLICY)
        if keys[0] not in refs:
            refs.append(keys[0])
    return tuple(refs)


@dataclass(frozen=True)
class DelegateTarget:
    """Where one submission's sparse feedback goes back to.

    Platform / chat / thread and nothing else. It is host routing material: it
    is never handed to the spine, never persisted, and never carried on a
    dispatch request — every notification about a task lands exactly where the
    task was asked for.
    """

    platform: str
    chat_id: str = field(repr=False)
    thread_id: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class DelegateSubmission:
    """What the handler gets back the moment a submission is registered.

    It names the task and the canonical Session it was admitted under, so the
    handler's acceptance can identify the work without waiting for it — which
    is the whole point: this object exists *before* the capacity wait, the
    dispatch, and the terminal.
    """

    task_id: str
    session_id: str
    payload_ref: str = field(repr=False)


@dataclass
class _DelegateState:
    """One in-flight submission, host-side only."""

    task_id: str
    session_id: str
    payload_ref: str = field(repr=False)
    handle: str = field(repr=False)
    target: DelegateTarget = field(repr=False)
    notifier: Any = field(repr=False)
    waiting_notified: bool = False
    terminal_notified: bool = False
    lifecycle: Any = field(default=None, repr=False)


def _new_task_id() -> str:
    """One fresh spine task id per submission.

    Fresh, deliberately: two ``/delegate`` calls are two independent tasks that
    may run side by side, and the dispatcher's existing single-flight guard
    stays exactly what it was — one in-flight turn *per task*.
    """

    return "delegate_" + uuid.uuid4().hex[:12]


class SachimaDelegateCoordinator:
    """The single source of Sachima delegate submissions for one bound bundle.

    It holds the composed execution bundle, the host's claim-check store, and
    the concurrency bound the bundle's backend negotiated — and it composes
    nothing. Every submission runs through the bundle's own dispatcher, port,
    registry, and source bindings, so a delegated Run and the live-progress
    read chain are always looking at the same spine.

    The division of labour is the design: :meth:`submit_new` does only what has
    to happen before an answer can be given — mint the identities, hold the
    text, register the state, start the background lifecycle — and everything
    that can block (waiting for a slot, the synchronous dispatch, waiting for
    the terminal) happens in that lifecycle, off the caller's path and off the
    event loop.
    """

    def __init__(
        self,
        binding: Any,
        config: Any,
        *,
        store: _PayloadStore | None = None,
        observe_interval: float = _DEFAULT_OBSERVE_INTERVAL_SECONDS,
    ) -> None:
        self._binding = binding
        self._config = config
        self._store = _PAYLOAD_STORE if store is None else store
        self._launch_refs = _delegate_launch_refs(config)
        # The one admissible source of capacity: what the daemon said, as
        # validated by the negotiation the composed backend already passed.
        self._capacity = int(binding.backend.negotiated_server_info.max_concurrent_runs)
        self._observe_interval = float(observe_interval)
        self._semaphore = asyncio.Semaphore(self._capacity)
        self._lock = threading.RLock()
        self._states: dict[str, _DelegateState] = {}

    # -- read-only identity ------------------------------------------------- #
    @property
    def binding(self) -> Any:
        """The composed execution bundle this coordinator drives."""

        return self._binding

    @property
    def capacity(self) -> int:
        """The negotiated ``max_concurrent_runs`` bound — never a default."""

        return self._capacity

    @property
    def launch_refs(self) -> tuple[str, ...]:
        """The policy refs every delegated session is admitted under."""

        return self._launch_refs

    def active_count(self) -> int:
        """How many delegated submissions this coordinator is still tracking."""

        with self._lock:
            return len(self._states)

    # -- submission --------------------------------------------------------- #
    def submit_new(
        self,
        task_text: str,
        *,
        target: DelegateTarget,
        notifier: Callable[[DelegateTarget, str], Awaitable[None]],
    ) -> DelegateSubmission:
        """Register one delegated task and return **before** any waiting.

        What happens here is only what an acceptance needs to be truthful: the
        text is claim-checked, a fresh task identity is minted, the supervised
        session is created through the bundle's own port, and the background
        lifecycle is started. Capacity, dispatch, and the terminal all belong to
        that lifecycle — so a full daemon delays the *work*, never the answer.

        A failure before the lifecycle starts discards the payload and raises:
        nothing is registered, nothing is dispatched, and the caller is the one
        that reports it, because at that point there is no background task to
        report from.
        """

        from sachima_supervisor.runtime_spine.arsd_supervisor_backend import (
            derive_arsd_backend_handle,
        )
        from sachima_supervisor.runtime_spine.launch_spec import build_launch_spec

        if type(target) is not DelegateTarget:
            raise ValueError(SACHIMA_DELEGATE_INVALID_TARGET)
        if not callable(notifier):
            raise ValueError(SACHIMA_DELEGATE_INVALID_TARGET)

        payload_ref = self._store.put(task_text)
        task_id = _new_task_id()
        try:
            spec = build_launch_spec(
                task_id=task_id,
                agent_kind=_DELEGATE_AGENT_KIND,
                mode_flags={"needs_agent": True},
                roles=_DELEGATE_ROLES,
                refs=self._launch_refs,
            )
            session = self._binding.port.create_or_attach(task_id, spec)
            handle = derive_arsd_backend_handle(task_id)
        except BaseException:
            self._store.discard(payload_ref)
            raise

        state = _DelegateState(
            task_id=task_id,
            session_id=session.session_id,
            payload_ref=payload_ref,
            handle=handle,
            target=target,
            notifier=notifier,
        )
        with self._lock:
            self._states[task_id] = state
        # Tracked in the state, so the task is strongly referenced for its
        # whole life and cannot be collected mid-flight.
        state.lifecycle = asyncio.create_task(self._run_lifecycle(state))
        return DelegateSubmission(
            task_id=task_id, session_id=state.session_id, payload_ref=payload_ref
        )

    # -- the background lifecycle ------------------------------------------- #
    async def _run_lifecycle(self, state: _DelegateState) -> None:
        """Wait for a slot, dispatch, wait for the terminal, report once.

        The slot is acquired **inside** here and released in ``finally`` — held
        across the dispatch *and* the whole observation, because a Run that has
        been accepted is a Run the daemon is still executing. Releasing on
        acceptance would let Sachima admit far more concurrent Runs than the
        daemon said it would hold.
        """

        try:
            await self._acquire_capacity(state)
            try:
                dispatched = await self._dispatch(state)
                if not dispatched:
                    await self._notify_terminal(
                        state,
                        DELEGATE_SUBMIT_FAILED_TEMPLATE.format(
                            task_ref=state.task_id,
                            code=SACHIMA_DELEGATE_DISPATCH_FAILED,
                        ),
                    )
                    return
                await self._await_terminal(state)
            finally:
                self._semaphore.release()
        except asyncio.CancelledError:
            raise
        except BaseException:
            # One stable code only — never the offending value or exception
            # text, and never a silent disappearance.
            logger.warning(SACHIMA_DELEGATE_DISPATCH_FAILED)
            await self._notify_terminal(
                state,
                DELEGATE_SUBMIT_FAILED_TEMPLATE.format(
                    task_ref=state.task_id, code=SACHIMA_DELEGATE_DISPATCH_FAILED
                ),
            )
        finally:
            # Both cleanup paths meet here: the private text outlives neither a
            # failure nor a terminal.
            self._store.discard(state.payload_ref)
            with self._lock:
                self._states.pop(state.task_id, None)

    async def _acquire_capacity(self, state: _DelegateState) -> None:
        """Take one slot, saying so **only** if the wait is real."""

        if self._semaphore.locked():
            await self._notify(
                state, DELEGATE_WAITING_TEMPLATE.format(task_ref=state.task_id)
            )
            state.waiting_notified = True
        await self._semaphore.acquire()

    async def _dispatch(self, state: _DelegateState) -> bool:
        """Drive one turn through the bundle's dispatcher, off the event loop.

        The dispatcher is synchronous spine code that talks to a socket, so it
        runs on a worker thread: inline, it would freeze every other
        conversation in the gateway for the length of an admission.
        """

        from sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher import (
            TurnDispatchRequest,
        )

        try:
            request = TurnDispatchRequest(
                task_id=state.task_id,
                session_id=state.session_id,
                turn_kind=_DELEGATE_TURN_KIND,
                payload_ref=state.payload_ref,
            )
            outcome = await asyncio.to_thread(
                self._binding.dispatcher.dispatch, request
            )
        except asyncio.CancelledError:
            raise
        except BaseException:
            logger.warning(SACHIMA_DELEGATE_DISPATCH_FAILED)
            return False
        return getattr(outcome, "error_code", SACHIMA_DELEGATE_DISPATCH_FAILED) is None

    async def _await_terminal(self, state: _DelegateState) -> None:
        """Poll in silence until the Run *ends*, then report that exactly once.

        The only thing that ends this loop is authoritative terminal evidence
        from the daemon. Observation faults settle nothing: a socket that
        dropped is not a Run that stopped, and an accepted Run stays the
        daemon's to finish whether or not Sachima can currently see it. So a
        run of faults never returns — returning would release the slot,
        discard the payload and drop the state while the Run is still
        executing, and at capacity 1 that admits a second Run beside a live
        first one. Holding is the honest failure: Sachima under-uses the
        daemon rather than over-admitting to it.

        Going blind is still worth saying once, so after an unbroken run of
        faults one advisory goes out — through :meth:`_notify`, deliberately
        not :meth:`_notify_terminal`, so it neither claims to be a verdict nor
        consumes the single terminal message the submission is still owed when
        observation recovers. The latch makes it at most one per submission,
        so a long outage stays silent instead of narrating every failed poll.
        """

        failures = 0
        blindness_reported = False
        while True:
            try:
                result = await asyncio.to_thread(
                    self._binding.backend.observe_run_result, state.handle
                )
            except asyncio.CancelledError:
                raise
            except BaseException:
                failures += 1
                if (
                    failures >= _MAX_CONSECUTIVE_OBSERVE_FAILURES
                    and not blindness_reported
                ):
                    blindness_reported = True
                    logger.warning(SACHIMA_DELEGATE_OBSERVATION_LOST)
                    await self._notify(
                        state,
                        DELEGATE_LOST_TEMPLATE.format(
                            task_ref=state.task_id,
                            code=SACHIMA_DELEGATE_OBSERVATION_LOST,
                        ),
                    )
            else:
                failures = 0
                if result is not None:
                    await self._notify_terminal(
                        state, _terminal_text(state.task_id, result)
                    )
                    return
            await asyncio.sleep(self._observe_interval)

    # -- notification ------------------------------------------------------- #
    async def _notify_terminal(self, state: _DelegateState, text: str) -> None:
        """Send the one terminal message this submission is owed — once.

        The guard is not defensive tidiness: the failure path and the terminal
        path can both be reached for one submission (a lifecycle that raises
        after reporting a terminal, say), and a chat told twice that its task
        finished has been told something false the second time.
        """

        with self._lock:
            if state.terminal_notified:
                return
            state.terminal_notified = True
        await self._notify(state, text)

    async def _notify(self, state: _DelegateState, text: str) -> None:
        """Deliver one message, and never let delivery break the lifecycle.

        A delivery surface that is down is not a reason to strand a slot or
        leak the private text: the failure is logged as a stable code and the
        lifecycle carries on to its cleanup.
        """

        try:
            await state.notifier(state.target, text)
        except asyncio.CancelledError:
            raise
        except BaseException:
            logger.warning(SACHIMA_DELEGATE_UNBOUND)


def _terminal_text(task_ref: str, result: Any) -> str:
    """The one terminal message, from the bounded projection and nothing else."""

    status = result.status
    if status == "completed":
        body = DELEGATE_COMPLETED_TEMPLATE.format(
            task_ref=task_ref,
            final_message=result.final_message or DELEGATE_EMPTY_FINAL_MESSAGE,
        )
    elif status == "cancelled":
        body = DELEGATE_CANCELLED_TEMPLATE.format(task_ref=task_ref)
    else:
        body = DELEGATE_FAILED_TEMPLATE.format(task_ref=task_ref, status=status)
        if result.final_message:
            body = f"{body}\n{result.final_message}"
    if result.truncated:
        body += DELEGATE_TRUNCATED_SUFFIX.format(
            truncate_reason=result.truncate_reason or "-"
        )
    return body


# --------------------------------------------------------------------------- #
# Host-held binding (cleared on every unbind path the composition takes)
# --------------------------------------------------------------------------- #
_coordinator: SachimaDelegateCoordinator | None = None


def bound_delegate_coordinator() -> SachimaDelegateCoordinator | None:
    """The coordinator for the currently bound bundle, or ``None``."""

    return _coordinator


def bind_delegate_coordinator(
    binding: Any, config: Any
) -> SachimaDelegateCoordinator:
    """Bind one coordinator over an already-composed execution bundle."""

    global _coordinator
    _coordinator = SachimaDelegateCoordinator(binding, config)
    return _coordinator


def unbind_delegate_coordinator() -> None:
    """Drop the coordinator and every payload it was still holding.

    A stale coordinator would keep dispatching into a bundle the host has
    retired, so unbinding is total: the tracked submissions go, and so does
    their private text.
    """

    global _coordinator
    _coordinator = None
    _PAYLOAD_STORE.clear()
