"""R1 Runtime Spine — deterministic Status Projection.

``project`` is a **pure, deterministic** function of an ordered ``TaskEvent``
sequence: same events in → same projection out, and ``serialize_projection``
gives byte-stable output. The projection is a read-only consumer — it assigns no
seq, appends no events, launches no work, and carries only allowlisted refs /
counts / status / stable codes (never raw payloads). It fails closed if handed a
gapped / duplicated / out-of-order event run.

Pure local/offline Python — no runtime, IM/Gateway, or delivery surface is
imported or wired here (the projection *would* drive IM in a later phase; R1 only
produces the deterministic snapshot).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .events import (
    EVENT_TYPES,
    KNOWN_FLAG_KEYS,
    RUNTIME_INVALID_PROJECTION,
    STABLE_CODES,
    STATUS_VALUES,
    TERMINAL_STATUSES,
    SpineError,
    TaskEvent,
    _safe_id,
    safe_task_id,
    scan_for_leak,
    verify_seq_contiguous,
)

PROJECTION_TYPE = "sachima.runtime_spine.status_projection.v1"

ALLOWED_PROJECTION_KEYS = frozenset(
    {
        "type",
        "task_id",
        "last_seq",
        "event_count",
        "status",
        "terminal",
        "flags",
        "refs",
        "event_type_counts",
        "error_code",
    }
)

_DEFAULT_FLAGS = {"needs_agent": False, "needs_durable": False}


def project(events: Sequence[TaskEvent], *, task_id: str | None = None) -> dict[str, Any]:
    """Deterministically replay ordered events into an allowlist-only projection."""

    events = tuple(events)
    # Fail closed on any gap / duplicate / reorder / mixed-task run.
    verify_seq_contiguous(events, task_id=task_id)

    if events:
        resolved_task = events[0].task_id
    elif task_id is not None:
        resolved_task = safe_task_id(task_id)
    else:
        # An empty replay has no task identity to project — fail closed rather than
        # fabricate one.
        raise SpineError(RUNTIME_INVALID_PROJECTION)

    status: str | None = None
    error_code: str | None = None
    flags = dict(_DEFAULT_FLAGS)
    refs: set[str] = set()
    event_type_counts: dict[str, int] = {}

    for event in events:
        if event.status is not None:
            status = event.status
        if event.error_code is not None:
            error_code = event.error_code
        for key, value in event.flags:
            flags[key] = value
        refs.update(event.refs)
        event_type_counts[event.event_type] = event_type_counts.get(event.event_type, 0) + 1

    projection: dict[str, Any] = {
        "type": PROJECTION_TYPE,
        "task_id": resolved_task,
        "last_seq": events[-1].seq if events else 0,
        "event_count": len(events),
        "status": status,
        "terminal": status in TERMINAL_STATUSES,
        "flags": dict(flags),
        "refs": sorted(refs),
        "event_type_counts": dict(sorted(event_type_counts.items())),
        "error_code": error_code,
    }

    # Defense in depth: the projection must fail closed on key allowlist, value
    # shape, AND no-leak — the same gate every external caller passes through.
    validate_projection(projection)
    return projection


def validate_projection(projection: Mapping[str, Any]) -> dict[str, Any]:
    """Exact fail-closed validation of a Status Projection's keys AND values.

    ``project`` builds a safe projection, but ``serialize_projection`` is exported
    public surface: a caller can hand-build or mutate a projection whose keys are
    all inside :data:`ALLOWED_PROJECTION_KEYS` yet whose *values* are unsafe — raw
    refs / platform material, a forged ``type`` marker, malformed
    ``flags`` / ``event_type_counts`` / ``status`` / ``error_code``, a bad
    ``task_id`` / ``last_seq`` / ``event_count``. Validating keys alone would let
    that through, so this checks value shape and runs the refs-only no-leak scan
    as well. Per-field shape is still not enough on its own: a caller can forge an
    allowlisted projection whose every value is well-formed yet whose cross-field
    invariants are broken (``last_seq`` out of step with ``event_count``,
    ``event_type_counts`` whose total contradicts ``event_count``, duplicate or
    unsorted ``refs``) — a snapshot ``project`` could never emit. So this also
    enforces the consistency invariants of ``project``'s 1..N append-only replay.
    It fails closed with the stable ``runtime_invalid_projection`` code only —
    never echoing the rejected material — and mutates nothing.
    """

    if not isinstance(projection, Mapping):
        raise SpineError(RUNTIME_INVALID_PROJECTION)
    # Keys: exactly the allowlist — no missing key, no extra key.
    if set(projection) != set(ALLOWED_PROJECTION_KEYS):
        raise SpineError(RUNTIME_INVALID_PROJECTION)
    # No-leak first: catches any forbidden marker in a key or string value (incl.
    # a raw/platform-derived ref) before per-field shape checks.
    if scan_for_leak(projection) is not None:
        raise SpineError(RUNTIME_INVALID_PROJECTION)

    if projection["type"] != PROJECTION_TYPE:
        raise SpineError(RUNTIME_INVALID_PROJECTION)

    safe_task_id(projection["task_id"], code=RUNTIME_INVALID_PROJECTION)

    for count_key in ("last_seq", "event_count"):
        value = projection[count_key]
        # bool is an int subclass — exclude it so a flag can't pose as a seq/count.
        if type(value) is not int or value < 0:
            raise SpineError(RUNTIME_INVALID_PROJECTION)

    event_count = projection["event_count"]
    # Consistency, not just shape: project() replays a strictly 1..N gap-free run,
    # so genuine output always has last_seq == event_count. A forged-but-allowlisted
    # projection with last_seq out of step with event_count is one project() could
    # never emit — fail closed rather than serialize it.
    if projection["last_seq"] != event_count:
        raise SpineError(RUNTIME_INVALID_PROJECTION)

    status = projection["status"]
    if status is not None and status not in STATUS_VALUES:
        raise SpineError(RUNTIME_INVALID_PROJECTION)

    terminal = projection["terminal"]
    if type(terminal) is not bool or terminal is not (status in TERMINAL_STATUSES):
        raise SpineError(RUNTIME_INVALID_PROJECTION)

    flags = projection["flags"]
    if not isinstance(flags, Mapping) or set(flags) != set(KNOWN_FLAG_KEYS):
        raise SpineError(RUNTIME_INVALID_PROJECTION)
    for flag_value in flags.values():
        if type(flag_value) is not bool:
            raise SpineError(RUNTIME_INVALID_PROJECTION)

    refs = projection["refs"]
    if not isinstance(refs, list):
        raise SpineError(RUNTIME_INVALID_PROJECTION)
    for ref in refs:
        _safe_id(ref, code=RUNTIME_INVALID_PROJECTION)
    # Every ref is now a validated safe id (hashable str). project() emits
    # sorted(set(refs)) — de-duped and in canonical, byte-stable order — so a
    # duplicate or out-of-order refs list is a forged shape project() never emits.
    if refs != sorted(set(refs)):
        raise SpineError(RUNTIME_INVALID_PROJECTION)

    counts = projection["event_type_counts"]
    if not isinstance(counts, Mapping):
        raise SpineError(RUNTIME_INVALID_PROJECTION)
    for count_type, count_value in counts.items():
        if count_type not in EVENT_TYPES:
            raise SpineError(RUNTIME_INVALID_PROJECTION)
        # bool excluded (int subclass); no negative counts.
        if type(count_value) is not int or count_value < 0:
            raise SpineError(RUNTIME_INVALID_PROJECTION)
    # Every count is now a validated non-negative int. project() increments exactly
    # one type-count per replayed event, so the total always equals event_count. A
    # total that contradicts event_count is a forged shape project() never emits.
    if sum(counts.values()) != event_count:
        raise SpineError(RUNTIME_INVALID_PROJECTION)

    error_code = projection["error_code"]
    if error_code is not None and error_code not in STABLE_CODES:
        raise SpineError(RUNTIME_INVALID_PROJECTION)

    if event_count == 0:
        # Empty replay output is fully pinned by project(): no status/error, no
        # refs, no event counts, and default false mode flags. A hand-built empty
        # projection with any carried state is forged, even if each field is
        # individually well-formed.
        if status is not None or error_code is not None or refs or counts:
            raise SpineError(RUNTIME_INVALID_PROJECTION)
        if flags != _DEFAULT_FLAGS:
            raise SpineError(RUNTIME_INVALID_PROJECTION)

    return dict(projection)


def serialize_projection(projection: dict[str, Any]) -> bytes:
    """Byte-stable canonical serialization of a *validated* projection.

    Fails closed on value shape and no-leak before JSON — not just the key
    allowlist — so a hand-built or mutated projection carrying unsafe values can
    never be serialized (see :func:`validate_projection`).
    """

    validate_projection(projection)
    return json.dumps(projection, sort_keys=True, separators=(",", ":")).encode("utf-8")
