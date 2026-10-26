"""Startup recovery must close a Run that ended while the Gateway was down.

Regression for the completion branch of Sachima startup recovery. Restoration
re-arms the observer of every accepted Run, and an observer whose Run already
ended closes that terminal while restoration still holds the startup barrier.
The closure looked the result up and inserted it by scanning every historical
result on the Gateway loop, and the insertion held the store's update lock for
the whole scan. The same closure could overlap the restore sink pass, which
decided from a stale snapshot, and it notified the wake bridge, whose superseded
path waits on the very barrier restoration holds.

The composition is the real ``GatewayRunner._start_sachima_delegate_host`` over
the history ``test_sachima_delegate_startup_recovery`` writes through the
coordinator's public path. Only the arsd transport is the in-memory facade; the
wake transport and the origins' plain-text sender are recording stand-ins, so a
result body is counted where the user would receive it.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

import gateway.sachima_delegate as delegate_mod
from gateway.platforms.base import SendResult
from gateway.sachima_delegate_state import DelegateResultEvent, DelegateStateStore
from gateway.sachima_delegate_wakeup import (
    WAKEUP_DELIVERY_ACCEPTED,
    WAKEUP_DELIVERY_SUPERSEDED,
)
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import derive_run_ref
from tests.gateway.test_sachima_delegate_startup_recovery import (
    LOOP_ANSWER_BOUND_SECONDS,
    READS_PER_SETTLED_TURN_BOUND,
    _assert_worktree_modules,
    _declare_offline_composition,
    _history,
    _LoopRendezvous,
    _runner,
    _settled_record,
    _start,
    _stop,
    _StoreIo,
)
from tests.waiting import async_wait_until, wait_until

#: What the accepted follow-up Run answers with when it ends.
FOLLOW_UP_RESULT = "exact result of the authorized follow-up"

#: Test hang bound for one controlled step — the restored observer reaching its
#: closure, a held worker call being joined, startup finishing. A healthy run
#: crosses each in well under a second; only a hang ever waits this long.
STEP_BOUND_SECONDS = 30.0

#: How long restoration is held open for the recovered closure. A closure whose
#: read holds the loop is still released by the rendezvous after its own bound.
CLOSURE_BOUND_SECONDS = 4 * LOOP_ANSWER_BOUND_SECONDS

#: Set for the span of the observer's terminal closure, and the closure step
#: (``lookup`` / ``insertion``) under way. Context variables travel with the
#: coordinator's worker seam, so a read is attributed whichever thread makes it.
_IN_CLOSURE: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "in_closure", default=False
)
_CLOSURE_STEP: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "closure_step", default=None
)


@pytest.fixture(autouse=True)
def _unbound():
    delegate_mod.unbind_delegate_coordinator()
    yield
    delegate_mod.unbind_delegate_coordinator()
    delegate_mod.set_delegate_delivery_factory(None)


# --------------------------------------------------------------------------- #
# Host stand-ins and witnesses
# --------------------------------------------------------------------------- #
class _PlainTextIm:
    """The origins' plain-text delivery, registered as the host's factory.

    Records every result body it is asked to send; ``gate`` holds a body send
    open until the test releases it.
    """

    def __init__(self) -> None:
        self.bodies: list[str] = []
        self.sending = asyncio.Event()
        self.gate: asyncio.Event | None = None

    def install(self) -> None:
        delegate_mod.set_delegate_delivery_factory(self._channel)

    def _channel(self, _origin):
        return delegate_mod.DelegateDelivery(
            send_text=self._send_text, send_plain_text_once=self._send_body
        )

    async def _send_text(self, _text: str) -> Any:
        return SendResult(success=True, message_id="om_text")

    async def _send_body(self, text: str) -> Any:
        self.bodies.append(text)
        self.sending.set()
        if self.gate is not None:
            await self.gate.wait()
        return SendResult(success=True, message_id=None)


class _HeldSummariser:
    """The host's summary provider, holding its one call open until released.

    The coordinator runs a provider on its own isolated worker loop, so the
    hold and its signals are thread-safe events.
    """

    generator_ref = "startup-recovery-stub"

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    async def summarize(self, _request: Any) -> str:
        self.entered.set()
        await asyncio.to_thread(self.release.wait, STEP_BOUND_SECONDS)
        return "Sachima 的结论：已批准的后续已经完成。"


def _compose_with_summariser(monkeypatch, provider) -> None:
    """Hand the composed coordinator a summary provider through its bind seam."""

    real = delegate_mod.bind_delegate_coordinator

    def _bind(binding, config, **kwargs):
        kwargs.setdefault("summary_provider", provider)
        return real(binding, config, **kwargs)

    monkeypatch.setattr(delegate_mod, "bind_delegate_coordinator", _bind)


class _ClosureWitness:
    """The restored observer's terminal closure, as it actually ran.

    Records each closure with the barrier state at its entry and exit, and the
    two store calls inside it that scan every historical result.
    """

    def __init__(self, monkeypatch) -> None:
        self.calls: list[tuple[str, bool, bool]] = []
        self.steps: list[str] = []
        self.finished = asyncio.Event()
        self._lock = threading.Lock()
        coordinator_cls = delegate_mod.SachimaDelegateCoordinator
        real_close = coordinator_cls._close_terminal
        real_lookup = DelegateStateStore.result_for_turn
        real_insert = DelegateStateStore.put_result

        async def _close(coordinator, turn_key, result):
            restored_at_entry = coordinator.restored
            token = _IN_CLOSURE.set(True)
            try:
                return await real_close(coordinator, turn_key, result)
            finally:
                _IN_CLOSURE.reset(token)
                self.calls.append((turn_key, restored_at_entry, coordinator.restored))
                self.finished.set()

        monkeypatch.setattr(coordinator_cls, "_close_terminal", _close)
        monkeypatch.setattr(
            DelegateStateStore,
            "result_for_turn",
            lambda store, turn_key: self._step("lookup", real_lookup, store, turn_key),
        )
        monkeypatch.setattr(
            DelegateStateStore,
            "put_result",
            lambda store, event: self._step("insertion", real_insert, store, event),
        )

    def _step(self, name, call, store, argument):
        if not _IN_CLOSURE.get():
            return call(store, argument)
        with self._lock:
            self.steps.append(name)
        token = _CLOSURE_STEP.set(name)
        try:
            return call(store, argument)
        finally:
            _CLOSURE_STEP.reset(token)


class _ClosureRendezvous(_LoopRendezvous):
    """The startup rendezvous, naming the closure step behind each blocked read."""

    @property
    def phase(self) -> str:
        return _CLOSURE_STEP.get() or self._phase

    @phase.setter
    def phase(self, value: str) -> None:
        self._phase = value


def _hold_restoration_until(monkeypatch, released: asyncio.Event) -> SimpleNamespace:
    """Keep restoration open at a real restore await until *released* is set."""

    hold = SimpleNamespace(expired=False, restored=None)
    real = delegate_mod.SachimaDelegateCoordinator._restore_summaries

    async def _held(coordinator):
        hold.restored = coordinator.restored
        try:
            await asyncio.wait_for(released.wait(), timeout=CLOSURE_BOUND_SECONDS)
        except TimeoutError:
            hold.expired = True
        return await real(coordinator)

    monkeypatch.setattr(
        delegate_mod.SachimaDelegateCoordinator, "_restore_summaries", _held
    )
    return hold


class _SinkSnapshot:
    """The restore sink pass's history snapshot, taken while the observer is held.

    Armed once. On the worker taking the snapshot it records what was selected
    for the follow-up Turn, releases the held observer, and hands the snapshot
    back only once the observer's own delivery has settled — so the pass decides
    after the record has moved on, which is the overlap a startup can produce.
    """

    def __init__(self, monkeypatch, turn_key: str, release: Callable[[], Any]) -> None:
        self.armed = False
        self.selected: list[DelegateResultEvent] = []
        self.overtaken = False
        real_list = DelegateStateStore.list_results

        def _list(store):
            snapshot = real_list(store)
            if not self.armed:
                return snapshot
            self.armed = False
            self.selected = [event for event in snapshot if event.turn_key == turn_key]
            release()
            if self.selected:
                event_id = self.selected[0].event_id
                try:
                    wait_until(
                        lambda: store.read_result(event_id).im_sink == "confirmed",
                        timeout=STEP_BOUND_SECONDS,
                        what="the observer's own delivery to settle",
                    )
                    self.overtaken = True
                except AssertionError:
                    pass
            return snapshot

        monkeypatch.setattr(DelegateStateStore, "list_results", _list)


def _accepted_run_index(history) -> int:
    """The facade index of the accepted follow-up Run the history left running."""

    turn = DelegateStateStore(str(history.root)).read_turn(history.admitted_turn_key)
    return next(
        index
        for index, run_id in enumerate(history.facade.run_ids)
        if derive_run_ref(run_id) == turn.turn_ref
    )


def _crash_after_the_result_write(history) -> DelegateResultEvent:
    """What a process that died right after the result write leaves behind.

    The follow-up Run ended and its result identity is durable with its wake
    intent admitted, but the Turn never became terminal: the canonical crash
    boundary a restart completes from this same event id.
    """

    store = DelegateStateStore(str(history.root))
    turn = store.read_turn(history.admitted_turn_key)
    assert store.read_task(turn.task_ref).completion_wakeup is True
    history.facade.terminalize(
        _accepted_run_index(history), final_message=FOLLOW_UP_RESULT
    )
    full_ref, _clipped = store.put_full_result(FOLLOW_UP_RESULT)
    return store.put_result(
        DelegateResultEvent(
            event_id=store.new_event_id(),
            turn_key=turn.turn_key,
            task_ref=turn.task_ref,
            session_id=turn.origin.session_id,
            terminal="completed",
            full_result_ref=full_ref,
            terminal_at=datetime.now(UTC).isoformat(timespec="seconds"),
            wakeup_state="pending",
        )
    )


def _results_for(state, turn_key: str) -> list[DelegateResultEvent]:
    return [event for event in state.list_results() if event.turn_key == turn_key]


def _delivered(deliveries, event_id: str) -> list[Any]:
    return [batch for batch in deliveries if event_id in batch.event_ids]


def _delivered_terminal(state, turn_key: str) -> DelegateResultEvent | None:
    """The Turn's one result once its body was sent and its wake accepted."""

    events = _results_for(state, turn_key)
    if (
        len(events) == 1
        and events[0].im_sink == "confirmed"
        and events[0].wakeup_state == "queued"
    ):
        return events[0]
    return None


# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_run_that_ended_while_down_closes_during_restore_off_the_loop(
    tmp_path, monkeypatch
):
    _assert_worktree_modules()
    history = await _history(tmp_path)
    _declare_offline_composition(monkeypatch, tmp_path, history)
    # The accepted follow-up Run ends after the original graph closed, so the
    # restored observer's first poll finds the terminal.
    history.facade.terminalize(
        _accepted_run_index(history), final_message=FOLLOW_UP_RESULT
    )
    io = _StoreIo(monkeypatch)
    rendezvous = _ClosureRendezvous(
        asyncio.get_running_loop(), _settled_record(history, "result")
    )
    rendezvous.install(monkeypatch)
    closure = _ClosureWitness(monkeypatch)
    hold = _hold_restoration_until(monkeypatch, closure.finished)
    im = _PlainTextIm()
    im.install()
    submitted = history.facade.submit_count()
    deliveries = []
    runner = _runner(deliveries)
    try:
        coordinator = await _start(runner)
        held, answered = list(rendezvous.held), set(rendezvous.answered)
        rendezvous.release_all()
        assert held == [], f"the recovered terminal closure held the Gateway loop at {held}"
        assert not hold.expired and hold.restored is False
        # It ran once, start to finish, while the barrier was still closed, and
        # both of its history scans met the rendezvous and were answered.
        assert closure.calls == [(history.admitted_turn_key, False, False)]
        assert closure.steps == ["lookup", "insertion"]
        assert {"lookup", "insertion"} <= answered, answered

        state = coordinator.state
        (event,) = _results_for(state, history.admitted_turn_key)
        turn = state.read_turn(history.admitted_turn_key)
        assert (turn.lifecycle, turn.terminal_status) == ("terminal", "completed")
        assert state.read_full_result(event.full_result_ref) == FOLLOW_UP_RESULT
        assert state.summary_for_event(event.event_id).settled
        assert event.im_sink == "confirmed"
        assert len(im.bodies) == 1 and event.task_ref in im.bodies[0]
        assert history.facade.submit_count() == submitted
        source = state.read_result(history.admitted_event_id)
        assert (source.operation_state, source.business_state) == ("accepted", "continued")
        assert source.operation_turn_key == history.admitted_turn_key
        assert not io.written & history.settled_files
    finally:
        rendezvous.release_all()
        await _stop(runner)


@pytest.mark.asyncio
async def test_restarts_after_a_recovered_terminal_neither_resend_nor_rewrite_it(
    tmp_path, monkeypatch
):
    _assert_worktree_modules()
    history = await _history(tmp_path)
    _declare_offline_composition(monkeypatch, tmp_path, history)
    history.facade.terminalize(
        _accepted_run_index(history), final_message=FOLLOW_UP_RESULT
    )
    io = _StoreIo(monkeypatch)
    im = _PlainTextIm()
    submitted = history.facade.submit_count()

    # The first restart closes the Run, sends its one body and wakes its
    # conversation once; the main model then reports it, as in ordinary use.
    deliveries = []
    runner = _runner(deliveries)
    im.install()
    try:
        coordinator = await _start(runner)
        state = coordinator.state
        event = await async_wait_until(
            lambda: _delivered_terminal(state, history.admitted_turn_key),
            timeout=STEP_BOUND_SECONDS,
            what="the recovered terminal's body and wake",
        )
        assert len(_delivered(deliveries, event.event_id)) == 1
        assert event.wakeup_attempts == 1
        session_id = state.read_turn(history.admitted_turn_key).origin.session_id
        claim = coordinator.claim_hermes_context(session_id)
        assert claim.event_ids == (event.event_id,)
        coordinator.confirm_hermes_context(
            session_id, processing_id=claim.processing_id, event_ids=claim.event_ids
        )
        coordinator.settle_result(
            task_ref=event.task_ref,
            turn_key=event.turn_key,
            event_id=event.event_id,
            processing_id=claim.processing_id,
            conclusion="reported",
            evidence_ref=event.full_result_ref,
        )
        assert coordinator.complete_report_delivery((event.event_id,), delivered=True) == 1
        settled = state.read_result(event.event_id)
        result_count = len(state.list_results())
        new_turn = history.root / "turns" / history.admitted_turn_key
        fully_settled = history.settled_files | {
            new_turn,
            history.root / "results" / f"{event.event_id}.json",
            state.summary_path(state.summary_for_event(event.event_id).summary_ref),
        }
    finally:
        await _stop(runner)
    assert (settled.business_state, settled.wakeup_state, settled.hermes_sink) == (
        "reported",
        "settled",
        "confirmed",
    )

    for restart in (2, 3):
        deliveries = []
        runner = _runner(deliveries)
        im.install()
        io.reset()
        try:
            coordinator = await _start(runner)
            rewritten = io.written & fully_settled
            busiest = max(io.reads[path] for path in history.settled_turns | {new_turn})
            state = coordinator.state
            assert not rewritten, (restart, sorted(map(str, rewritten)))
            assert busiest <= READS_PER_SETTLED_TURN_BOUND, (restart, busiest)
            assert state.read_result(event.event_id) == settled
            assert _results_for(state, history.admitted_turn_key) == [settled]
            assert len(state.list_results()) == result_count
            assert _delivered(deliveries, event.event_id) == []
            assert len(im.bodies) == 1
            assert history.facade.submit_count() == submitted
        finally:
            await _stop(runner)


@pytest.mark.asyncio
async def test_closing_during_an_off_loop_result_insertion_joins_it_and_restarts_once(
    tmp_path, monkeypatch
):
    _assert_worktree_modules()
    history = await _history(tmp_path)
    _declare_offline_composition(monkeypatch, tmp_path, history)
    index = _accepted_run_index(history)
    im = _PlainTextIm()
    submitted = history.facade.submit_count()
    inserting = threading.Event()
    release = threading.Event()
    real_insert = DelegateStateStore.put_result

    def _insert(store, event):
        if event.turn_key == history.admitted_turn_key and not release.is_set():
            inserting.set()
            release.wait(timeout=STEP_BOUND_SECONDS)
        return real_insert(store, event)

    monkeypatch.setattr(DelegateStateStore, "put_result", _insert)
    deliveries = []
    runner = _runner(deliveries)
    im.install()
    closing = None
    try:
        coordinator = await _start(runner)
        lifecycle = coordinator._lifecycle
        # The Run ends while the graph is open; its observer's insertion is held
        # inside the store call on the worker.
        history.facade.terminalize(index, final_message=FOLLOW_UP_RESULT)
        await async_wait_until(
            inserting.is_set,
            timeout=STEP_BOUND_SECONDS,
            what="the result insertion on its worker",
        )
        closing = asyncio.ensure_future(_stop(runner))
        # Closing cancels the observer and its owner task; what remains is the
        # running worker call, and the graph is not closed while it runs.
        await async_wait_until(
            lambda: lifecycle.closing and not lifecycle.tasks,
            timeout=STEP_BOUND_SECONDS,
            what="the drain to retire the owned tasks",
        )
        assert lifecycle.futures, "the running insertion is not owned by the drain"
        assert coordinator.closed is False and not closing.done()
        assert _results_for(coordinator.state, history.admitted_turn_key) == []
    finally:
        release.set()
        if closing is not None:
            await asyncio.wait_for(closing, timeout=STEP_BOUND_SECONDS)
        else:
            await _stop(runner)
    assert coordinator.closed is True

    # The joined insertion finished: the result is the crash boundary, the Turn
    # was never terminalized and nothing was sent.
    (written,) = _results_for(coordinator.state, history.admitted_turn_key)
    assert coordinator.state.read_turn(history.admitted_turn_key).lifecycle == "admitted"
    assert im.bodies == []

    deliveries = []
    runner = _runner(deliveries)
    im.install()
    try:
        restarted = await _start(runner)
        state = restarted.state
        (event,) = _results_for(state, history.admitted_turn_key)
        assert event.event_id == written.event_id
        assert state.read_turn(history.admitted_turn_key).lifecycle == "terminal"
        assert event.im_sink == "confirmed" and len(im.bodies) == 1
        assert len(_delivered(deliveries, event.event_id)) == 1
        assert history.facade.submit_count() == submitted
        assert restarted.capacity.held() == 0
    finally:
        await _stop(runner)


@pytest.mark.asyncio
@pytest.mark.parametrize("interleaving", ["stale_pending", "in_flight_overtaken"])
async def test_a_terminal_published_during_the_sink_pass_is_delivered_once(
    tmp_path, monkeypatch, interleaving
):
    """The sink pass and a restored observer settle one body between them.

    ``stale_pending``: the pass snapshots the result while the observer is still
    producing its summary, so the IM sink reads ``pending``; deciding from that
    snapshot sent the body a second time. ``in_flight_overtaken``: the pass
    snapshots while the observer's send is in flight; deciding from it rewrote
    the confirmed delivery as ``uncertain``, which a later ``/status`` resends.
    """

    _assert_worktree_modules()
    history = await _history(tmp_path)
    _declare_offline_composition(monkeypatch, tmp_path, history)
    index = _accepted_run_index(history)
    submitted = history.facade.submit_count()
    loop = asyncio.get_running_loop()
    im = _PlainTextIm()
    im.gate = asyncio.Event()
    summariser = _HeldSummariser()
    if interleaving == "stale_pending":
        im.gate.set()
        held, release, selected = summariser.entered.is_set, summariser.release.set, "pending"
    else:
        summariser.release.set()
        held, selected = im.sending.is_set, "in_flight"
        release = functools.partial(loop.call_soon_threadsafe, im.gate.set)
    _compose_with_summariser(monkeypatch, summariser)
    closure = _ClosureWitness(monkeypatch)
    snapshot = _SinkSnapshot(monkeypatch, history.admitted_turn_key, release)
    real_sinks = delegate_mod.SachimaDelegateCoordinator._restore_sinks
    reached = SimpleNamespace(held=False)

    async def _sinks(coordinator):
        # The Run ends after the summary pass. The restored observer publishes
        # it and is held mid-closure while the sink pass takes its snapshot.
        history.facade.terminalize(index, final_message=FOLLOW_UP_RESULT)
        try:
            await async_wait_until(
                held, timeout=STEP_BOUND_SECONDS, what="the observer's held step"
            )
            reached.held = True
        except AssertionError:
            pass
        snapshot.armed = True
        return await real_sinks(coordinator)

    monkeypatch.setattr(delegate_mod.SachimaDelegateCoordinator, "_restore_sinks", _sinks)
    im.install()
    deliveries = []
    runner = _runner(deliveries)
    try:
        coordinator = await _start(runner)
        assert reached.held, "the restored observer never reached its held step"
        assert [event.im_sink for event in snapshot.selected] == [selected]
        assert snapshot.overtaken, "the observer's delivery did not settle first"
        assert closure.calls == [(history.admitted_turn_key, False, False)]
        state = coordinator.state
        (event,) = _results_for(state, history.admitted_turn_key)
        assert state.summary_for_event(event.event_id).settled
        assert event.im_sink == "confirmed"
        assert len(im.bodies) == 1, f"{len(im.bodies)} result bodies were sent"
        assert history.facade.submit_count() == submitted
    finally:
        summariser.release.set()
        im.gate.set()
        await _stop(runner)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [WAKEUP_DELIVERY_SUPERSEDED, WAKEUP_DELIVERY_ACCEPTED])
async def test_a_crash_boundary_wake_is_left_to_recovery_and_delivered_once(
    tmp_path, monkeypatch, outcome
):
    """A result restoration finishes is woken by the recovery that follows it.

    ``superseded``: the conversation was closed, and settling that waits for the
    startup barrier — which the restoration delivering the wake still held, so
    startup never finished. ``accepted``: a wake delivered from inside
    restoration was found ``queued`` by the recovery right after it, taken for a
    previous process's interrupted delivery, and delivered again.
    """

    _assert_worktree_modules()
    history = await _history(tmp_path)
    _declare_offline_composition(monkeypatch, tmp_path, history)
    event = _crash_after_the_result_write(history)
    deliveries = []
    runner = _runner(deliveries)

    async def _deliver(batch):
        deliveries.append(batch)
        return outcome

    runner._deliver_sachima_delegate_wakeup = _deliver
    starting = asyncio.ensure_future(_start(runner))
    try:
        done, _pending = await asyncio.wait({starting}, timeout=STEP_BOUND_SECONDS)
        assert starting in done, "startup never finished: a wake waited on the restore barrier"
        state = starting.result().state
        current = state.read_result(event.event_id)
        assert state.read_turn(history.admitted_turn_key).lifecycle == "terminal"
        assert _results_for(state, history.admitted_turn_key) == [current]
        assert len(_delivered(deliveries, event.event_id)) == 1
        assert current.wakeup_attempts == 1
        if outcome == WAKEUP_DELIVERY_SUPERSEDED:
            superseded = delegate_mod.SACHIMA_DELEGATE_CONTINUATION_SUPERSEDED
            assert (current.business_state, current.business_diagnostic) == (
                "blocked",
                superseded,
            )
            assert (current.wakeup_state, current.wakeup_diagnostic) == (
                "blocked",
                superseded,
            )
        else:
            assert (current.business_state, current.wakeup_state) == ("pending", "queued")
    finally:
        if not starting.done():
            starting.cancel()
        await asyncio.gather(starting, return_exceptions=True)
        await _stop(runner)


@pytest.mark.asyncio
@pytest.mark.parametrize("closed_by", ["restored_observer", "crash_boundary"])
async def test_a_turn_closed_before_the_identity_pass_stays_usable(
    tmp_path, monkeypatch, closed_by
):
    """A Turn restoration closed answers, reads and continues as completed.

    ``restored_observer``: restoration reattached the accepted Run and armed its
    observer; the Run had ended, so the observer closed the Turn before the
    identity pass reached its Task — the order a Task sorting late in
    ``list_tasks`` gets naturally. The pass attached that Run's identity a
    second time, the backend refused it as a conflict with the binding the
    observer had just settled, and the completed Turn was stamped blocked:
    ``/status`` and the latest result answered blocked and continuation was
    refused until another restart. ``crash_boundary``: a Turn restoration
    finalized from its durable result was never reattached, so its identity
    still comes from the identity pass.
    """

    _assert_worktree_modules()
    history = await _history(tmp_path)
    _declare_offline_composition(monkeypatch, tmp_path, history)
    if closed_by == "restored_observer":
        history.facade.terminalize(
            _accepted_run_index(history), final_message=FOLLOW_UP_RESULT
        )
    else:
        _crash_after_the_result_write(history)
    turn_key = history.admitted_turn_key
    met: list[str] = []
    real_results = delegate_mod.results_by_turn

    def _results_once_closed(state):
        # The identity pass's one result scan runs on the worker seam, so the
        # loop keeps running the restored observer while it waits here.
        wait_until(
            lambda: state.read_turn(turn_key).lifecycle == "terminal",
            timeout=STEP_BOUND_SECONDS,
            what="the Turn to close before the identity pass",
        )
        met.append(state.read_turn(turn_key).lifecycle)
        return real_results(state)

    monkeypatch.setattr(delegate_mod, "results_by_turn", _results_once_closed)
    im = _PlainTextIm()
    im.install()
    submitted = history.facade.submit_count()
    deliveries = []
    runner = _runner(deliveries)
    try:
        coordinator = await _start(runner)
        state = coordinator.state
        event = await async_wait_until(
            lambda: _delivered_terminal(state, turn_key),
            timeout=STEP_BOUND_SECONDS,
            what="the recovered terminal's body and wake",
        )
        assert met == ["terminal"]
        turn = state.read_turn(turn_key)
        assert (turn.terminal_status, turn.diagnostic) == ("completed", None)
        status = await coordinator.status(event.task_ref)
        assert (status.lifecycle, status.terminal, status.diagnostic) == (
            "terminal",
            "completed",
            None,
        ), status.as_dict()
        latest = coordinator.result(event.task_ref)
        assert (latest.get("event_id"), latest.get("full_result")) == (
            event.event_id,
            FOLLOW_UP_RESULT,
        ), latest
        assert len(im.bodies) == 1
        assert len(_delivered(deliveries, event.event_id)) == 1
        assert history.facade.submit_count() == submitted

        # Continuable: the next Run is accepted under the same Task and Sessions.
        continued = await coordinator.continue_task(event.task_ref, "one more round")
        assert (continued.lifecycle, continued.diagnostic) == (
            "admitted",
            None,
        ), continued.as_dict()
        assert history.facade.submit_count() == submitted + 1
        next_turn = state.read_turn(continued.turn_key)
        assert (
            next_turn.task_id,
            next_turn.spine_session_id,
            next_turn.backend_handle,
        ) == (turn.task_id, turn.spine_session_id, turn.backend_handle)
    finally:
        await _stop(runner)
