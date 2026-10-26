"""Startup recovery of delegation history must not hold the Gateway loop.

Regression for the Sachima startup failure in which the loop-liveness watchdog
fired inside ``recover -> _reconcile_continuation_operations``: every startup
rescanned every Turn once per accepted continuation and rewrote (fsync'd) every
settled operation, and ``restore`` rescanned every result once per Task, all on
the Gateway loop without a yield. The restore summary/sink passes and the wake
dispatcher's recovery also read every historical result and summary on the loop.

The startup composition is the real one, ``GatewayRunner._start_sachima_delegate_host``:
declared composition documents, the production coordinator, state store and
binding ledger under a disposable ``HERMES_HOME``. Only the arsd transport is the
in-memory facade and the wake transport is a recording stand-in.
"""

from __future__ import annotations

import asyncio
import threading
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import gateway.run as run_mod
import gateway.sachima_delegate as delegate_mod
import gateway.sachima_delegate_state as state_mod
import gateway.sachima_delegate_wakeup as wakeup_mod
from gateway.sachima_delegate_state import DelegateStateStore
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import ArsdRunBindingLedger
from tests.gateway.test_sachima_delegate_coordinator import _config
from tests.gateway.test_sachima_delegate_gateway import (
    AGENT_ID,
    _bind,
    _composition_files,
    _declare_composition,
    _Host,
    _origin_for,
)
from tests.waiting import async_wait_until

#: Settled continuations in the representative history. Kept small: the claim is
#: that per-record work does not grow with this number, not a load test.
SETTLED_CONTINUATIONS = 8

#: Test hang bound for one blocked read waiting for the loop to answer. A free
#: loop answers in milliseconds; only a read that holds the loop itself ever
#: waits this long. Unrelated to the Gateway's liveness-probe policy.
LOOP_ANSWER_BOUND_SECONDS = 15.0

#: Reads of one settled Turn record during one startup recovery: the restore
#: snapshot, its identity pass, the reconcile index, the re-read of a matched
#: operation Turn, and one fresh scan for an operation whose Turn was never
#: created. A count that grew with the number of operations is the defect.
READS_PER_SETTLED_TURN_BOUND = 5

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _unbound():
    delegate_mod.unbind_delegate_coordinator()
    yield
    delegate_mod.unbind_delegate_coordinator()


# --------------------------------------------------------------------------- #
# The history, written through the real coordinator's public path
# --------------------------------------------------------------------------- #
async def _terminal_event(coordinator, turn_key):
    def _settled():
        event = coordinator.state.result_for_turn(turn_key)
        summary = event and coordinator.state.summary_for_event(event.event_id)
        return event if summary is not None and summary.settled else None

    return await async_wait_until(_settled, what="terminal result with a settled summary")


async def _claimed_terminal(host, coordinator, facade, name, *, continuation=True):
    """One Task's terminal, read and confirmed by the main model of its own Session."""

    origin = _origin_for(host, chat_id=name, anchor=f"m-{name}")
    text = f"delegated work {name}"
    admission = coordinator.admit_agent(AGENT_ID, task_text=text)
    authority = (
        {
            "authorization_ref": origin.reply_anchor,
            "continuation_task": f"one authorized follow-up for {name}",
            "continuation_round_title": "执行一次已批准的后续",
            "continuation_summary": "Exactly one follow-up is authorized.",
        }
        if continuation
        else {}
    )
    created = await coordinator.create(
        task_text=text, preset=admission.preset, origin=origin, **authority
    )
    facade.terminalize(facade.submit_count() - 1, final_message=f"exact result {name}")
    event = await _terminal_event(coordinator, created.turn_key)
    claim = coordinator.claim_hermes_context(origin.session_id)
    coordinator.confirm_hermes_context(
        origin.session_id, processing_id=claim.processing_id, event_ids=claim.event_ids
    )
    return origin, coordinator.state.read_result(event.event_id), claim.processing_id


async def _settled_continuation(host, coordinator, facade, index):
    """Continued, finished and reported: what years of ordinary use leave behind."""

    origin, source, processing_id = await _claimed_terminal(
        host, coordinator, facade, f"settled-{index}"
    )
    receipt = await coordinator.continue_authorized(
        task_ref=source.task_ref,
        turn_key=source.turn_key,
        event_id=source.event_id,
        processing_id=processing_id,
        origin=origin,
    )
    assert receipt["operation_state"] == "accepted", receipt
    facade.terminalize(facade.submit_count() - 1, final_message=f"follow-up {index}")
    report = await _terminal_event(coordinator, receipt["turn_key"])
    claim = coordinator.claim_hermes_context(origin.session_id)
    coordinator.confirm_hermes_context(
        origin.session_id, processing_id=claim.processing_id, event_ids=claim.event_ids
    )
    coordinator.settle_result(
        task_ref=report.task_ref,
        turn_key=report.turn_key,
        event_id=report.event_id,
        processing_id=claim.processing_id,
        conclusion="reported",
        evidence_ref=report.full_result_ref,
    )
    assert coordinator.complete_report_delivery((report.event_id,), delivered=True) == 1
    return SimpleNamespace(
        task_ref=source.task_ref,
        source_turn_key=source.turn_key,
        source_event_id=source.event_id,
        operation_turn_key=receipt["turn_key"],
        report_event_id=report.event_id,
    )


def _claim_operation(coordinator, source):
    """The stable operation claim ``continue_authorized`` persists before any Turn."""

    binding = coordinator.state.read_task(source.task_ref)
    operation_id = coordinator._authorized_operation_id(source, binding)
    coordinator.state.update_result(
        source.event_id, operation_id=operation_id, operation_state="in_flight"
    )
    return binding, operation_id


async def _history(tmp_path):
    config = _config(tmp_path)
    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path, config=config)
    coordinator._configure_completion_wakeup(True)

    settled = [
        await _settled_continuation(host, coordinator, facade, index)
        for index in range(SETTLED_CONTINUATIONS)
    ]

    # Crash after the operation claim, before its Turn existed: not submitted.
    _origin, unsubmitted, _ = await _claimed_terminal(host, coordinator, facade, "crash-unsubmitted")
    _claim_operation(coordinator, unsubmitted)

    # Crash after the operation's Run was accepted, before the receipt was written.
    origin, admitted, _ = await _claimed_terminal(host, coordinator, facade, "crash-admitted")
    binding, operation_id = _claim_operation(coordinator, admitted)
    text = coordinator.state.read_payload(binding.continuation_payload_ref)
    operation_turn = await coordinator.continue_task(
        binding.task_ref,
        text,
        preset=coordinator.admit_agent(binding.agent_id, task_text=text).preset,
        origin=origin,
        operation_id=operation_id,
        authorized_event_id=admitted.event_id,
        round_title=binding.continuation_round_title,
    )
    assert operation_turn.lifecycle == "admitted"

    # Crash after a report was staged, before the adapter receipt.
    _origin, staged, processing_id = await _claimed_terminal(
        host, coordinator, facade, "crash-staged", continuation=False
    )
    coordinator.settle_result(
        task_ref=staged.task_ref,
        turn_key=staged.turn_key,
        event_id=staged.event_id,
        processing_id=processing_id,
        conclusion="reported",
        evidence_ref=staged.full_result_ref,
    )

    root = Path(coordinator.state.root)
    settled_events = [
        event_id
        for chain in settled
        for event_id in (chain.source_event_id, chain.report_event_id)
    ]
    summaries = {
        event_id: coordinator.state.summary_path(
            coordinator.state.summary_for_event(event_id).summary_ref
        )
        for event_id in settled_events
    }
    await coordinator.close()
    delegate_mod.unbind_delegate_coordinator()
    settled_turns = {
        root / "turns" / key
        for chain in settled
        for key in (chain.source_turn_key, chain.operation_turn_key)
    }
    return SimpleNamespace(
        config=config,
        facade=facade,
        root=root,
        settled=settled,
        settled_turns=settled_turns,
        summaries=summaries,
        settled_files=settled_turns
        | {root / "tasks" / chain.task_ref for chain in settled}
        | {root / "results" / f"{event_id}.json" for event_id in settled_events}
        | set(summaries.values()),
        unsubmitted_event_id=unsubmitted.event_id,
        admitted_event_id=admitted.event_id,
        admitted_turn_key=operation_turn.turn_key,
        staged_event_id=staged.event_id,
    )


# --------------------------------------------------------------------------- #
# The real startup composition, offline
# --------------------------------------------------------------------------- #
def _declare_offline_composition(monkeypatch, tmp_path, history):
    """Declared documents and the production bind; only the daemon socket is the facade."""

    import sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding as binding_mod

    _declare_composition(monkeypatch, *_composition_files(tmp_path, history.config))
    real = binding_mod.bind_arsd_execution

    def _offline(config, **kwargs):
        kwargs.setdefault("facade", history.facade)
        kwargs.setdefault("ledger", ArsdRunBindingLedger(config.binding_ledger_path))
        return real(config, **kwargs)

    monkeypatch.setattr(binding_mod, "bind_arsd_execution", _offline)


def _runner(deliveries):
    from gateway.config import GatewayConfig

    runner: Any = object.__new__(run_mod.GatewayRunner)
    runner.config = GatewayConfig(sachima_completion_wakeup_enabled=True)
    runner._owned_delegate_coordinator = None
    runner._sachima_delegate_wakeup = None

    async def _deliver(batch):  # the wake transport: recorded, accepted
        deliveries.append(batch)
        return "accepted"

    runner._deliver_sachima_delegate_wakeup = _deliver
    return runner


async def _start(runner):
    await runner._start_sachima_delegate_host()
    # Both set only when composition, restore() and recover() all completed;
    # the startup failure path retires and clears them.
    assert runner._owned_delegate_coordinator is not None
    assert runner._sachima_delegate_wakeup is not None
    return runner._owned_delegate_coordinator


async def _stop(runner):
    await runner._close_sachima_delegate_wakeup()
    await runner._retire_owned_delegate_coordinator()


class _StoreIo:
    """Counts the real store's file reads and writes, per path, from any thread."""

    def __init__(self, monkeypatch):
        self._lock = threading.Lock()
        self.reads: Counter[Path] = Counter()
        self.written: set[Path] = set()
        real_read = DelegateStateStore._read_bytes
        real_write = DelegateStateStore._write_bytes
        real_create = DelegateStateStore._create_document

        def _read(store, path):
            with self._lock:
                self.reads[path] += 1
            return real_read(store, path)

        def _write(store, path, payload):
            with self._lock:
                self.written.add(path)
            return real_write(store, path, payload)

        def _create(store, path, kind, document):
            with self._lock:
                self.written.add(path)
            return real_create(store, path, kind, document)

        monkeypatch.setattr(DelegateStateStore, "_read_bytes", _read)
        monkeypatch.setattr(DelegateStateStore, "_write_bytes", _write)
        monkeypatch.setattr(DelegateStateStore, "_create_document", _create)

    def reset(self):
        with self._lock:
            self.reads.clear()
            self.written.clear()


class _LoopRendezvous:
    """Every read of one historical record waits until the Gateway loop answers.

    The answer is a callback posted with ``call_soon_threadsafe`` — the same probe
    the loop-liveness watchdog uses. A read performed on the loop thread cannot be
    answered while it waits, so it is recorded as holding the loop, released by
    the hang bound, and the rendezvous disarms so the run finishes.
    """

    def __init__(self, loop, path):
        self._loop = loop
        self._path = path
        self._lock = threading.Lock()
        self._waiting: set[threading.Event] = set()
        self._armed = True
        self.phase = "restore"
        self.answered: list[str] = []
        self.held: list[str] = []

    def install(self, monkeypatch):
        real_read = DelegateStateStore._read_bytes

        def _read(store, path):
            if path == self._path and self._armed and not self.held:
                self._await_loop()
            return real_read(store, path)

        monkeypatch.setattr(DelegateStateStore, "_read_bytes", _read)

    def _await_loop(self):
        released = threading.Event()
        with self._lock:
            self._waiting.add(released)
        try:
            self._loop.call_soon_threadsafe(released.set)
            if released.wait(timeout=LOOP_ANSWER_BOUND_SECONDS):
                self.answered.append(self.phase)
            else:
                self.held.append(self.phase)
        finally:
            with self._lock:
                self._waiting.discard(released)

    def release_all(self):
        """Disarm, so the test's own reads on the loop pass, and free every waiter."""

        self._armed = False
        with self._lock:
            for released in self._waiting:
                released.set()


def _assert_worktree_modules():
    for module in (run_mod, delegate_mod, state_mod, wakeup_mod):
        assert Path(module.__file__).resolve().is_relative_to(_REPO_ROOT), module.__file__


# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #
def _settled_record(history, record_kind):
    """One settled chain's record of each kind every startup history pass reads."""

    chain = history.settled[0]
    return {
        "turn": history.root / "turns" / chain.operation_turn_key,
        "result": history.root / "results" / f"{chain.source_event_id}.json",
        "summary": history.summaries[chain.source_event_id],
    }[record_kind]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record_kind", "phases"),
    [
        ("turn", {"restore", "recover"}),
        # Results feed the restore turn/summary/sink passes and every wake
        # recovery scan; summaries are read by the restore summary pass.
        ("result", {"restore", "recover"}),
        ("summary", {"restore"}),
    ],
)
async def test_startup_recovery_keeps_the_loop_answering_while_history_io_is_blocked(
    tmp_path, monkeypatch, record_kind, phases
):
    _assert_worktree_modules()
    history = await _history(tmp_path)
    _declare_offline_composition(monkeypatch, tmp_path, history)
    designated = _settled_record(history, record_kind)
    rendezvous = _LoopRendezvous(asyncio.get_running_loop(), designated)
    rendezvous.install(monkeypatch)
    real_recover = wakeup_mod.SachimaDelegateWakeupDispatcher.recover

    async def _recover(dispatcher):
        rendezvous.phase = "recover"
        return await real_recover(dispatcher)

    monkeypatch.setattr(wakeup_mod.SachimaDelegateWakeupDispatcher, "recover", _recover)

    deliveries = []
    runner = _runner(deliveries)
    try:
        coordinator = await _start(runner)
        held, answered = list(rendezvous.held), set(rendezvous.answered)
        rendezvous.release_all()
        assert held == [], f"historical {record_kind} I/O held the Gateway loop in {held}"
        assert phases <= answered, answered
        state = coordinator.state
        chain = history.settled[0]
        event = state.read_result(chain.source_event_id)
        assert (event.operation_state, event.business_state, event.wakeup_state) == (
            "accepted",
            "continued",
            "settled",
        )
        assert event.operation_turn_key == chain.operation_turn_key
        assert history.facade.submit_count() == 2 * SETTLED_CONTINUATIONS + 4
    finally:
        rendezvous.release_all()
        await _stop(runner)


@pytest.mark.asyncio
async def test_repeated_startup_recovery_keeps_settled_history_without_rewrites(
    tmp_path, monkeypatch
):
    _assert_worktree_modules()
    history = await _history(tmp_path)
    _declare_offline_composition(monkeypatch, tmp_path, history)
    io = _StoreIo(monkeypatch)
    submitted = history.facade.submit_count()

    for restart in (1, 2):
        deliveries = []
        runner = _runner(deliveries)
        io.reset()
        try:
            coordinator = await _start(runner)
            state = coordinator.state

            for chain in history.settled:
                event = state.read_result(chain.source_event_id)
                assert (event.operation_state, event.business_state, event.wakeup_state) == (
                    "accepted",
                    "continued",
                    "settled",
                )
                assert event.operation_turn_key == chain.operation_turn_key
                assert state.read_task(chain.task_ref).continuation_disposition == "consumed"
                assert state.read_result(chain.report_event_id).business_state == "reported"

            # Accepted Run, lost receipt: the operation Turn is the receipt.
            admitted = state.read_result(history.admitted_event_id)
            assert (admitted.operation_state, admitted.business_state) == ("accepted", "continued")
            assert admitted.operation_turn_key == history.admitted_turn_key

            # Claimed but never submitted: back to the bounded wake path, once per restart.
            unsubmitted = state.read_result(history.unsubmitted_event_id)
            assert unsubmitted.operation_state == "none"
            assert unsubmitted.business_state == "pending"
            assert [batch.event_ids for batch in deliveries] == [
                (history.unsubmitted_event_id,)
            ]
            assert unsubmitted.wakeup_attempts == restart

            # A staged report whose delivery is unknown is never sent again.
            staged = state.read_result(history.staged_event_id)
            assert staged.business_state == "blocked"
            assert staged.business_diagnostic == (
                delegate_mod.SACHIMA_DELEGATE_REPORT_DELIVERY_UNKNOWN
            )

            # No replay and no new Run, ever.
            assert history.facade.submit_count() == submitted

            # Settled history is read, never rewritten, and each record is read a
            # bounded number of times however many operations the history holds.
            rewritten = io.written & history.settled_files
            busiest = max(io.reads[path] for path in history.settled_turns)
            assert not rewritten and busiest <= READS_PER_SETTLED_TURN_BOUND, (
                f"settled records rewritten: {len(rewritten)}; "
                f"reads of the busiest settled Turn: {busiest}"
            )
        finally:
            await _stop(runner)
