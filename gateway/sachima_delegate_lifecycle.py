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
  or card side effect and released when they return, however they return;
* **tasks** — owner and observer tasks the graph spawned on its own loop;
* **futures** — synchronous daemon/spine calls registered *before* they are
  submitted to a worker thread, released by their own terminal callback.

``close`` is the one drain. The first closer flips the graph to ``CLOSING`` and
starts the drain; every closer, including that first one, awaits the same
drain future. The drain cancels owned tasks and any registered future that has
not started, then waits until every admission has released, every task has
finished and every future has settled — a running thread is joined, never
interrupted — and only then publishes ``CLOSED``. No deadline is imposed here:
the drain is bounded by whatever bounds the calls it is waiting on.

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


class LifecycleRefused(RuntimeError):
    """Work offered to a graph that has begun closing.

    The message *is* the stable code the graph was composed with, so a caller
    that already answers ``RuntimeError`` with that code keeps doing so.
    """


class _Admission:
    """One public operation's stay inside the graph, released exactly once."""

    __slots__ = ("_lifecycle", "_held")

    def __init__(self, lifecycle: "GraphLifecycle") -> None:
        self._lifecycle = lifecycle
        self._held = False

    def __enter__(self) -> "_Admission":
        self._lifecycle._admit()
        self._held = True
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self._held:
            self._held = False
            self._lifecycle._release()
        return False


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
        self._admitted = 0
        self._tasks: set[asyncio.Task] = set()
        self._futures: set[concurrent.futures.Future] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._quiescent: asyncio.Future | None = None
        self._drain: asyncio.Task | None = None

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
            return self._admitted

    @property
    def tasks(self) -> frozenset[asyncio.Task]:
        with self._guard:
            return frozenset(self._tasks)

    @property
    def futures(self) -> frozenset[concurrent.futures.Future]:
        with self._guard:
            return frozenset(self._futures)

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

    def _admit(self) -> None:
        with self._guard:
            self._refuse_if_closing()
            self._admitted += 1

    def _release(self) -> None:
        with self._guard:
            self._admitted -= 1
        self._notify()

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
            task = asyncio.get_running_loop().create_task(factory())
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

        The first caller flips the graph to ``CLOSING`` and starts the drain on
        its own loop; every caller awaits that same drain, shielded, so a
        closer that gives up cannot cancel the retirement it started.
        """

        with self._guard:
            if self._drain is None:
                loop = asyncio.get_running_loop()
                self._state = CLOSING
                self._loop = loop
                self._quiescent = loop.create_future()
                self._drain = loop.create_task(self._drain_work())
            drain = self._drain
        await asyncio.shield(drain)

    async def _drain_work(self) -> None:
        with self._guard:
            tasks = list(self._tasks)
            futures = list(self._futures)
            quiescent = self._quiescent
        for task in tasks:
            task.cancel()
        for future in futures:
            # Only a future that has not started can be cancelled. A running
            # one is a thread inside daemon/spine code: it is joined below,
            # never interrupted.
            future.cancel()
        if tasks:
            done, _pending = await asyncio.wait(tasks)
            for task in done:
                # A retiring task's outcome settles nothing; retrieving it
                # only keeps the loop from reporting it as never retrieved.
                if not task.cancelled():
                    task.exception()
        self._notify()
        assert quiescent is not None
        await quiescent
        with self._guard:
            self._state = CLOSED

    def _notify(self) -> None:
        """Wake the drain once nothing admitted, owned, or registered remains."""

        with self._guard:
            if (
                self._quiescent is None
                or self._admitted
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
