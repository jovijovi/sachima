"""R1 Runtime Spine — Task Registry + derived snapshot cache.

The registry keeps per-``task_id`` metadata (the two mode flags ``needs_agent`` /
``needs_durable``) and a **snapshot cache** that is *derived* from the event log
via the deterministic projection (design §4: "the snapshot is a derived/cached
view for fast reads — **not a second source of truth**. Canonical truth is the
Event Log.").

The cache is versioned by the log's ``last_seq``: reads reuse the cached
projection while ``last_seq`` is unchanged, and any new event invalidates it so
the next read refreshes from the log. Pure local/offline Python — no runtime,
process, network, or delivery surface.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .events import (
    RUNTIME_INVALID_TASK_RECORD,
    SpineError,
    TaskEvent,
    TaskEventLog,
    build_event_body,
    safe_task_id,
)
from .projection import project


@dataclass(frozen=True)
class TaskRecord:
    """Frozen per-task metadata: safe ``task_id`` + the two mode flags."""

    task_id: str
    needs_agent: bool
    needs_durable: bool


@dataclass
class TaskRegistry:
    """Task records + a log-derived, seq-versioned snapshot cache.

    The registry owns one ``TaskEventLog`` (the canonical truth). ``snapshot``
    returns the deterministic projection of that log, cached per ``task_id`` and
    keyed on ``last_seq`` so it always reflects — and never diverges from — the
    log.

    All internal state (``log`` / ``_records`` / ``_snap_cache`` / ``_lock``) is
    ``init=False`` — the registry owns it and none of it is a constructor
    parameter. A caller cannot inject a pre-seeded ``log`` / ``_records`` (unowned
    state) or a hostile ``_snap_cache`` (which would become a second source of
    truth serving stale/raw material instead of the derived projection): the only
    construction is zero-arg ``TaskRegistry()``.
    """

    log: TaskEventLog = field(default_factory=TaskEventLog, init=False)
    _records: dict[str, TaskRecord] = field(default_factory=dict, init=False)
    _snap_cache: dict[str, tuple[int, dict[str, Any]]] = field(default_factory=dict, init=False)
    _lock: threading.RLock = field(
        default_factory=threading.RLock, init=False, repr=False, compare=False
    )

    def create_task(
        self,
        task_id: str,
        *,
        needs_agent: bool = False,
        needs_durable: bool = False,
        refs: tuple[str, ...] = (),
    ) -> TaskRecord:
        safe_task = safe_task_id(task_id)
        if type(needs_agent) is not bool or type(needs_durable) is not bool:
            raise SpineError(RUNTIME_INVALID_TASK_RECORD)
        with self._lock:
            if safe_task in self._records:
                raise SpineError(RUNTIME_INVALID_TASK_RECORD)
            # The creation event carries the flags into the canonical log, so the
            # projection/snapshot surfaces them from truth — not from the record.
            self.log.append(
                safe_task,
                build_event_body(
                    event_type="task_created",
                    status="created",
                    refs=tuple(refs),
                    flags={"needs_agent": needs_agent, "needs_durable": needs_durable},
                ),
            )
            record = TaskRecord(task_id=safe_task, needs_agent=needs_agent, needs_durable=needs_durable)
            self._records[safe_task] = record
            return record

    def append_event(self, task_id: str, body: Mapping[str, Any]) -> TaskEvent:
        safe_task = safe_task_id(task_id)
        with self._lock:
            if safe_task not in self._records:
                raise SpineError(RUNTIME_INVALID_TASK_RECORD)
            event = self.log.append(safe_task, body)
            # Invalidate the derived snapshot; the next read refreshes from the log.
            self._snap_cache.pop(safe_task, None)
            return event

    def get_record(self, task_id: str) -> TaskRecord | None:
        safe_task = safe_task_id(task_id)
        with self._lock:
            return self._records.get(safe_task)

    def has_task(self, task_id: str) -> bool:
        safe_task = safe_task_id(task_id)
        with self._lock:
            return safe_task in self._records

    def snapshot(self, task_id: str) -> dict[str, Any] | None:
        safe_task = safe_task_id(task_id)
        with self._lock:
            if safe_task not in self._records:
                return None
            last_seq = self.log.last_seq(safe_task)
            cached = self._snap_cache.get(safe_task)
            if cached is not None and cached[0] == last_seq:
                # Hand out a defensive deep copy — the cached projection is a derived
                # view, not a second source of truth, so a caller mutating what it
                # gets back (top-level or nested ``flags``/``refs``/counts) must never
                # poison the cache or the next read.
                return copy.deepcopy(cached[1])
            snapshot = project(self.log.events_for(safe_task), task_id=safe_task)
            self._snap_cache[safe_task] = (last_seq, snapshot)
            return copy.deepcopy(snapshot)
