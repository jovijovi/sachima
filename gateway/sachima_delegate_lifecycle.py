"""Sachima delegation — the one owner of a composed graph's lifetime.

Private to :mod:`gateway.sachima_delegate`. The coordinator used to keep the
same question in several places at once: a ``_closed`` flag, a ``_restored``
flag, an owned-task set, and each one guarded a different slice of "may this
graph still take work, and when has it really stopped". :class:`GraphLifecycle`
is that question asked once.

Five states, one direction::

    COMPOSED -> RESTORING -> OPEN -> CLOSING -> CLOSED
        \\_______________________________/

A graph may close from any state; a failed restoration returns to
``COMPOSED`` so a later caller can restore again. Nothing re-opens a graph
that has begun closing.

Three kinds of work are accounted for under one guard:

* **admissions** — public coordinator operations, admitted before any durable
  or card side effect and released when they return, however they return.
  Each admission knows its owner (the loop it runs on, or a worker thread),
  so one whose owner loop has terminated — and therefore can never release —
  is retired by a later closer instead of holding the graph in ``CLOSING``;
* **tasks** — owner and observer tasks the graph spawned on its own loop;
* **futures** — synchronous daemon/spine calls registered *before* they are
  submitted to a worker thread, released by their own terminal callback.

``close`` is the one drain. The first closer flips the graph to ``CLOSING`` and
claims the drain start; every closer, including that first one, awaits the
same completion. The drain runs on the graph's home loop — the bound lifecycle
loop, or the loop that first owned work here — because that is where the
owned tasks live; a closer on any other loop hands the start there and joins
through a loop-local bridge, never through a future attached to a foreign
loop. A hand-off is only a *claim* until the home loop acknowledges it by
creating the drain task. If the home loop stops before the drain has run to
completion — whether it never acknowledged the start, or acknowledged it and
then stopped before the drain task could run or finish — a repeated closer
reclaims the drain under the guard with a new generation; a stale hand-off or
a stale drain task checks that generation and no-ops if its loop ever runs
again, so there is never a second drain owner and the shared completion is
settled exactly once. The drain cancels owned tasks and any
registered future that has not started, then waits until every admission has
released, every task has finished and every future has settled — a running
thread is joined, never interrupted — and only then publishes ``CLOSED``. Work
owned by a loop that has terminated can never finish: it is asked to unwind
and released, so the completion settles instead of stranding every waiter. No
deadline is imposed here: the drain is bounded by whatever bounds the calls it
is waiting on.

Pure local on import: no loop, thread, socket, or daemon is touched here.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from typing import Any, Callable, Coroutine

__all__ = [
    "CLOSED",
    "CLOSING",
    "COMPOSED",
    "OPEN",
    "RESTORING",
    "GraphLifecycle",
    "LifecycleRefused",
]

COMPOSED = "composed"
RESTORING = "restoring"
OPEN = "open"
CLOSING = "closing"
CLOSED = "closed"

_ADMITTING = frozenset({COMPOSED, RESTORING, OPEN})


def _alive(loop: asyncio.AbstractEventLoop | None) -> bool:
    """Can *loop* still run a callback handed to it?"""

    return loop is not None and not loop.is_closed() and loop.is_running()


class LifecycleRefused(RuntimeError):
    """Work offered to a graph that has begun closing.

    The message *is* the stable code the graph was composed with, so a caller
    that already answers ``RuntimeError`` with that code keeps doing so.
    """


class _Admission:
    """One public operation's stay inside the graph, released exactly once.

    An admission knows its owner: the event loop the entry runs on, or no
    loop at all for a synchronous entry on a worker thread. A thread always
    leaves its ``with`` block, so a thread-owned admission always releases; a
    loop-owned one can only release while its loop keeps running, which is
    what lets a later closer retire it once that loop has terminated.
    """

    __slots__ = ("_lifecycle", "_owner", "_held")

    def __init__(self, lifecycle: "GraphLifecycle") -> None:
        self._lifecycle = lifecycle
        self._owner: asyncio.AbstractEventLoop | None = None
        self._held = False

    def __enter__(self) -> "_Admission":
        try:
            owner: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            owner = None
        self._owner = owner
        self._lifecycle._admit(self)
        self._held = True
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self._held:
            self._held = False
            self._lifecycle._release(self)
        return False

    @property
    def dead(self) -> bool:
        """True once the loop that owns this admission can no longer run it."""

        return self._owner is not None and not _alive(self._owner)


class _Restoration:
    """The startup barrier: ``COMPOSED`` to ``OPEN``, or back on failure."""

    __slots__ = ("_lifecycle",)

    def __init__(self, lifecycle: "GraphLifecycle") -> None:
        self._lifecycle = lifecycle

    def __enter__(self) -> "_Restoration":
        self._lifecycle._begin_restore()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        self._lifecycle._end_restore(succeeded=exc_type is None)
        return False


class GraphLifecycle:
    """The state machine one composed delegation graph lives inside."""

    def __init__(self, refusal: str, invariant: str = "sachima_delegate_invariant") -> None:
        self._refusal = str(refusal)
        self._invariant = str(invariant)
        self._guard = threading.RLock()
        self._state = COMPOSED
        self._admissions: set[_Admission] = set()
        self._tasks: set[asyncio.Task] = set()
        self._futures: set[concurrent.futures.Future] = set()
        # The home loop: bound by the host, or adopted from the first owned
        # work. Owned tasks live there, so the drain must run there.
        self._home_loop: asyncio.AbstractEventLoop | None = None
        # The loop the drain is actually running on, and its wait.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._quiescent: asyncio.Future | None = None
        # The drain-start claim: a generation per claim, acknowledged only
        # when the loop it was handed to creates the drain task.
        self._drain_generation = 0
        self._drain_task: asyncio.Task | None = None
        # The one loop-agnostic completion every closer joins.
        self._drain_done: concurrent.futures.Future | None = None

    # -- observation -------------------------------------------------------- #
    @property
    def state(self) -> str:
        with self._guard:
            return self._state

    @property
    def fresh(self) -> bool:
        """True until the first restoration has completed.

        Only a fresh graph may reclassify durable ``in_flight`` attempts: the
        process that owned them is gone, and nothing but a later observation
        can settle them.
        """

        with self._guard:
            return self._state in (COMPOSED, RESTORING)

    @property
    def closing(self) -> bool:
        """True once closing has begun, whether or not the drain is done."""

        with self._guard:
            return self._state in (CLOSING, CLOSED)

    @property
    def closed(self) -> bool:
        """True only once every admitted piece of work has drained."""

        with self._guard:
            return self._state == CLOSED

    @property
    def admitted(self) -> int:
        with self._guard:
            return len(self._admissions)

    @property
    def tasks(self) -> frozenset[asyncio.Task]:
        with self._guard:
            return frozenset(self._tasks)

    @property
    def futures(self) -> frozenset[concurrent.futures.Future]:
        with self._guard:
            return frozenset(self._futures)

    # -- the home loop ------------------------------------------------------ #
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Name the loop this graph's work and its drain belong to."""

        with self._guard:
            self._home_loop = loop

    # -- admission ---------------------------------------------------------- #
    def admission(self) -> _Admission:
        """A context every public operation enters before any side effect.

        Entering after closing has begun raises :class:`LifecycleRefused`
        with the stable code; nothing durable can then have been touched.
        """

        return _Admission(self)

    def restoring(self) -> _Restoration:
        """The one restoration barrier, entered by the caller that runs it."""

        return _Restoration(self)

    def _refuse_if_closing(self) -> None:
        if self._state not in _ADMITTING:
            raise LifecycleRefused(self._refusal)

    def _admit(self, admission: _Admission) -> None:
        with self._guard:
            self._refuse_if_closing()
            self._admissions.add(admission)

    def _release(self, admission: _Admission) -> None:
        with self._guard:
            # An admission retired earlier — its loop terminated and a closer
            # gave up on it — releasing late because that loop ran again is
            # a no-op: it changes nothing about the graph's accounting.
            self._admissions.discard(admission)
        self._notify()

    def _retire_dead_admissions_locked(self) -> None:
        """Under the guard: drop every admission whose owner loop terminated.

        Such an admission can never release on its own, so keeping it would
        hold the graph in ``CLOSING`` forever. Thread-owned admissions and
        admissions on loops that are still running are untouched: they will
        release, and the drain waits for them.
        """

        for admission in [entry for entry in self._admissions if entry.dead]:
            self._admissions.discard(admission)

    def _begin_restore(self) -> None:
        with self._guard:
            self._refuse_if_closing()
            if self._state != COMPOSED:
                raise RuntimeError(self._invariant)
            self._state = RESTORING

    def _end_restore(self, *, succeeded: bool) -> None:
        with self._guard:
            # A graph that began closing mid-restoration stays closing: the
            # restoration's own outcome no longer decides anything.
            if self._state == RESTORING:
                self._state = OPEN if succeeded else COMPOSED

    # -- registration ------------------------------------------------------- #
    def spawn(self, factory: Callable[[], Coroutine[Any, Any, Any]]) -> asyncio.Task:
        """Create and own one task, atomically with the closing check.

        Split apart, a task created just before closing and registered just
        after would never appear in the drain's snapshot and would outlive the
        retirement. Either it registers before the fence closes and the drain
        owns it, or the fence is already closed and no coroutine is created.
        """

        with self._guard:
            self._refuse_if_closing()
            loop = asyncio.get_running_loop()
            if self._home_loop is None:
                self._home_loop = loop
            task = loop.create_task(factory())
            self._tasks.add(task)
        task.add_done_callback(self._forget_task)
        return task

    def register_future(self, future: concurrent.futures.Future) -> None:
        """Own one synchronous call's future *before* it is submitted.

        The future's own terminal callback releases the registration, so a
        call cancelled before it ever started is accounted for exactly like
        one that ran to completion.
        """

        with self._guard:
            self._refuse_if_closing()
            self._futures.add(future)
        future.add_done_callback(self._forget_future)

    def _forget_task(self, task: asyncio.Task) -> None:
        with self._guard:
            self._tasks.discard(task)
        self._notify()

    def _forget_future(self, future: concurrent.futures.Future) -> None:
        with self._guard:
            self._futures.discard(future)
        self._notify()

    # -- the one drain ------------------------------------------------------ #
    async def close(self) -> None:
        """Begin closing, or join the closing already under way.

        The first caller flips the graph to ``CLOSING`` and claims the drain
        start for the home loop — handed there when the caller is on another
        loop. The claim is acknowledged only when the home loop actually
        creates the drain task, and the drain owns the retirement only while
        that loop keeps running. A repeated closer that finds the home loop
        no longer running before the completion has settled — the start never
        acknowledged, or acknowledged and then stranded — reclaims the drain
        under the guard with a new generation, so a stale hand-off or drain
        task can never become a second owner. Every caller then awaits the
        same completion through a bridge local to its own loop, and that
        completion cannot be cancelled through the bridge: a closer that
        gives up cannot cancel the retirement it started.
        """

        current = asyncio.get_running_loop()
        with self._guard:
            claim = None
            if self._drain_done is None:
                self._state = CLOSING
                done: concurrent.futures.Future = concurrent.futures.Future()
                # Running from the outset: a bridge that is cancelled cannot
                # cancel the drain behind it.
                done.set_running_or_notify_cancel()
                self._drain_done = done
                claim = self._claim_drain_start(current)
            elif not self._drain_done.done() and not _alive(self._home_loop):
                # The drain belongs to a home loop that terminated — whether
                # it never acknowledged the start, or acknowledged it and then
                # stopped before the drain task could run or finish. Nothing
                # can complete it there: take it over here.
                claim = self._claim_drain_start(current)
            # A closer is the one thing that can notice an owner loop has
            # died while the drain waits on that loop's admission.
            self._retire_dead_admissions_locked()
            done = self._drain_done
            assert done is not None
        if claim is not None:
            self._start_drain(*claim, current=current)
        self._notify()
        await asyncio.wrap_future(done, loop=current)

    def _claim_drain_start(
        self, current: asyncio.AbstractEventLoop
    ) -> tuple[asyncio.AbstractEventLoop, int]:
        """Under the guard: claim the drain start for a loop that can run it.

        Each claim is a new generation. The acknowledgement that creates the
        drain task must carry the same generation, which is what makes a
        hand-off left queued on an earlier, stopped loop recognisably stale.
        """

        self._drain_generation += 1
        # Whatever task an earlier generation created belongs to a loop that
        # can no longer run it; the new generation acknowledges afresh.
        self._drain_task = None
        home = self._home_loop
        if not _alive(home):
            home = self._home_loop = current
        return home, self._drain_generation

    def _start_drain(
        self,
        home: asyncio.AbstractEventLoop,
        generation: int,
        *,
        current: asyncio.AbstractEventLoop,
    ) -> None:
        """Hand the claimed start to the home loop, or take it right here."""

        if home is current:
            self._acknowledge_drain_start(generation)
            return

        def _on_home() -> None:
            self._acknowledge_drain_start(generation)

        try:
            home.call_soon_threadsafe(_on_home)
        except RuntimeError:
            # The home loop closed between the check and the hand-off. The
            # only loop left that can run the drain is this one — unless a
            # later closer has already reclaimed the start.
            with self._guard:
                if generation != self._drain_generation:
                    return
                _home, generation = self._claim_drain_start(current)
            self._acknowledge_drain_start(generation)

    def _acknowledge_drain_start(self, generation: int) -> None:
        """Create the drain task for *this* generation's claim, exactly once.

        Runs on the loop the start was handed to. A stale hand-off — an
        older generation, or a claim already acknowledged — no-ops here
        instead of becoming a second drain owner.
        """

        with self._guard:
            if generation != self._drain_generation or self._drain_task is not None:
                return
            self._drain_task = asyncio.get_running_loop().create_task(
                self._drain_work(generation)
            )

    async def _drain_work(self, generation: int) -> None:
        loop = asyncio.get_running_loop()
        with self._guard:
            if generation != self._drain_generation:
                # A stale drain: its loop stopped before it could run and a
                # later closer reclaimed the retirement. It owns nothing here
                # and settles nothing.
                return
            self._loop = loop
            self._quiescent = loop.create_future()
            self._retire_dead_admissions_locked()
            tasks = list(self._tasks)
            futures = list(self._futures)
            quiescent = self._quiescent
            done = self._drain_done
        assert done is not None
        try:
            local: list[asyncio.Task] = []
            for task in tasks:
                if task.get_loop() is loop:
                    task.cancel()
                    local.append(task)
                    continue
                # Owned by a loop this drain is not running on — which only
                # happens once that loop terminated and a closer reclaimed
                # the start. The task can never finish there, so it is asked
                # to unwind should its loop ever run again, and it stops
                # being owned: nothing can drain it, and keeping it
                # registered would strand every closer instead.
                try:
                    task.cancel()
                except RuntimeError:
                    pass
                self._forget_task(task)
            for future in futures:
                # Only a future that has not started can be cancelled. A
                # running one is a thread inside daemon/spine code: it is
                # joined below, never interrupted.
                future.cancel()
            if local:
                finished, _pending = await asyncio.wait(local)
                for task in finished:
                    # A retiring task's outcome settles nothing; retrieving
                    # it only keeps the loop from reporting it as never
                    # retrieved.
                    if not task.cancelled():
                        task.exception()
            self._notify()
            await quiescent
            with self._guard:
                if generation != self._drain_generation:
                    # Reclaimed while this drain waited: the newer owner
                    # publishes CLOSED and settles the completion, not this.
                    return
                self._state = CLOSED
        except asyncio.CancelledError:
            # Loop shutdown cancels this generation's task, not the graph's
            # retirement. Leave the shared completion pending so a later
            # closer can reclaim after the home loop stops, and still join
            # any running work before publishing CLOSED.
            raise
        except BaseException as exc:
            # Non-cancellation failures still answer every closer, unless a
            # later generation already took the retirement over.
            with self._guard:
                owner = generation == self._drain_generation
            if owner and not done.done():
                done.set_exception(exc)
            raise
        else:
            if not done.done():
                done.set_result(None)

    def _notify(self) -> None:
        """Wake the drain once nothing admitted, owned, or registered remains."""

        with self._guard:
            if (
                self._quiescent is None
                or self._admissions
                or self._tasks
                or self._futures
            ):
                return
            loop = self._loop
            quiescent = self._quiescent
        assert loop is not None

        def _settle() -> None:
            if not quiescent.done():
                quiescent.set_result(None)

        try:
            loop.call_soon_threadsafe(_settle)
        except RuntimeError:
            # The loop is already closed: there is nothing left to publish
            # CLOSED to, and a shutdown must not be the thing that raises.
            pass
