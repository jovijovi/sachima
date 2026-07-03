"""R1 — Task Registry + derived snapshot cache (design §4, §11.3, plan §5.4).

RED/GREEN tests for the registry: safe ``task_id`` records carrying the two mode
flags, plus a snapshot cache that is *derived* from the log/projection, versioned
by ``last_seq``, and refreshed (never a second source of truth) when new events
arrive.
"""

from __future__ import annotations

import threading

import pytest

from sachima_supervisor.runtime_spine import (
    RUNTIME_INVALID_TASK_ID,
    SpineError,
    TaskEventLog,
    TaskRecord,
    TaskRegistry,
    build_event_body,
    project,
)


def test_create_task_stores_safe_id_and_mode_flags() -> None:
    reg = TaskRegistry()
    record = reg.create_task("task_alpha", needs_agent=True, needs_durable=False)
    assert type(record) is TaskRecord
    assert record.task_id == "task_alpha"
    assert record.needs_agent is True
    assert record.needs_durable is False
    assert reg.get_record("task_alpha") == record
    assert reg.has_task("task_alpha") is True


def test_create_task_defaults_flags_false() -> None:
    reg = TaskRegistry()
    record = reg.create_task("task_beta")
    assert record.needs_agent is False
    assert record.needs_durable is False


def test_create_task_rejects_unsafe_task_id() -> None:
    reg = TaskRegistry()
    for bad in ("", "Task Alpha", "chat_id_1", "1bad"):
        with pytest.raises(SpineError) as exc:
            reg.create_task(bad)
        assert exc.value.code in SpineError_codes()


def test_snapshot_is_derived_and_matches_fresh_projection() -> None:
    reg = TaskRegistry()
    reg.create_task("task_alpha", needs_agent=True)
    reg.append_event("task_alpha", build_event_body(event_type="progress", status="running"))
    snap = reg.snapshot("task_alpha")
    # Snapshot is not a second source of truth — it equals a fresh projection of
    # the log's events.
    fresh = project(reg.log.events_for("task_alpha"), task_id="task_alpha")
    assert snap is not None
    assert snap == fresh
    assert snap["flags"] == {"needs_agent": True, "needs_durable": False}
    assert snap["status"] == "running"


def test_snapshot_is_versioned_and_cached_by_last_seq() -> None:
    reg = TaskRegistry()
    reg.create_task("task_alpha")
    first = reg.snapshot("task_alpha")
    again = reg.snapshot("task_alpha")
    # Same last_seq → equal projection *content* is served from the cache, but as a
    # fresh defensive copy each read — never the same mutable object (the cache is a
    # derived view, not a handle callers may mutate). Pin behavior, not identity.
    assert first is not None
    assert again is not None
    assert again == first
    assert again is not first
    assert first["last_seq"] == 1


def test_snapshot_return_is_isolated_from_cache_poisoning() -> None:
    reg = TaskRegistry()
    reg.create_task("task_alpha")
    first = reg.snapshot("task_alpha")
    # An external caller mutating the returned snapshot — top-level and nested —
    # must not poison the derived cache or the next read. The snapshot is a cached
    # view of the Event Log, never a second source of truth.
    assert first is not None
    first["status"] = "corrupted_by_external_caller"
    first["flags"]["needs_agent"] = True
    first["refs"].append("leaked_ref")
    first["event_type_counts"]["task_created"] = 999
    again = reg.snapshot("task_alpha")
    assert again is not None
    assert again["status"] != "corrupted_by_external_caller"
    assert again["flags"] == {"needs_agent": False, "needs_durable": False}
    assert again["refs"] == []
    assert again["event_type_counts"] == {"task_created": 1}
    # And the served snapshot still equals a fresh projection of the canonical log.
    fresh = project(reg.log.events_for("task_alpha"), task_id="task_alpha")
    assert again == fresh


def test_snapshot_invalidates_and_refreshes_after_new_event() -> None:
    reg = TaskRegistry()
    reg.create_task("task_alpha")
    v1 = reg.snapshot("task_alpha")
    assert v1 is not None
    assert v1["last_seq"] == 1
    reg.append_event("task_alpha", build_event_body(event_type="completed", status="completed"))
    v2 = reg.snapshot("task_alpha")
    assert v2 is not None
    assert v2 is not v1
    assert v2["last_seq"] == 2
    assert v2["status"] == "completed"
    assert v1["status"] != v2["status"]


def test_append_event_requires_existing_task() -> None:
    reg = TaskRegistry()
    with pytest.raises(SpineError):
        reg.append_event("task_missing", build_event_body(event_type="progress"))


def test_snapshot_and_record_for_unknown_task_is_none() -> None:
    reg = TaskRegistry()
    assert reg.snapshot("task_missing") is None
    assert reg.get_record("task_missing") is None
    assert reg.has_task("task_missing") is False


def test_duplicate_create_fails_closed() -> None:
    reg = TaskRegistry()
    reg.create_task("task_alpha")
    with pytest.raises(SpineError):
        reg.create_task("task_alpha")


# --------------------------------------------------------------------------- #
# Internal state is registry-owned, never constructor-injectable
# --------------------------------------------------------------------------- #
# The registry OWNS its log (canonical truth), records, derived snapshot cache,
# and lock. None may be seeded through the generated dataclass ``__init__`` — an
# injected ``log``/``_records`` pre-seeds unowned state, and an injected
# ``_snap_cache`` becomes a second source of truth that can serve stale or raw
# material instead of the deterministic projection of the log.
def test_task_registry_rejects_injected_log_via_constructor() -> None:
    with pytest.raises(TypeError):
        TaskRegistry(log=TaskEventLog())  # type: ignore[call-arg]


def test_task_registry_rejects_injected_records_via_constructor() -> None:
    with pytest.raises(TypeError):
        TaskRegistry(_records={})  # type: ignore[call-arg]


def test_task_registry_rejects_injected_lock_via_constructor() -> None:
    with pytest.raises(TypeError):
        TaskRegistry(_lock=threading.RLock())  # type: ignore[call-arg]


def test_task_registry_rejects_malicious_snap_cache_via_constructor() -> None:
    # A poisoned cache keyed on the real ``last_seq`` (1 after create_task) would
    # make ``snapshot`` return attacker-controlled raw material as a "cache hit"
    # instead of the derived projection. Constructor injection must fail closed.
    poisoned = {"task_alpha": (1, {"status": "raw_prompt: leaked", "refs": ["/tmp/secret"]})}
    with pytest.raises(TypeError):
        TaskRegistry(_snap_cache=poisoned)  # type: ignore[call-arg]


def test_snapshot_serves_derived_projection_not_injected_material() -> None:
    # With the constructor sealed, a zero-arg registry can only ever serve the
    # deterministic projection of its own canonical log — never seeded material.
    reg = TaskRegistry()
    reg.create_task("task_alpha")
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["status"] != "raw_prompt: leaked"
    assert snap["refs"] == []
    assert snap == project(reg.log.events_for("task_alpha"), task_id="task_alpha")


def test_task_registry_zero_arg_construction_remains_valid() -> None:
    reg = TaskRegistry()
    record = reg.create_task("task_alpha", needs_agent=True)
    assert record.needs_agent is True
    snap = reg.snapshot("task_alpha")
    assert snap is not None
    assert snap["flags"] == {"needs_agent": True, "needs_durable": False}


def SpineError_codes() -> set[str]:
    from sachima_supervisor.runtime_spine import STABLE_CODES

    # unsafe task ids fail closed with a task-id or leak stable code
    return set(STABLE_CODES) | {RUNTIME_INVALID_TASK_ID}
