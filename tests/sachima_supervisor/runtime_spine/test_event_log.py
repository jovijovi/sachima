"""R1 — single seq authority + refs-only Task Event Log (design §11.1, §11.2).

RED/GREEN tests for the spine's canonical truth: an append-only, per-``task_id``
event log that is the **single monotonic seq authority**, plus the refs-only
no-leak boundary for event bodies. The module under test is pure local/offline
Python — importing it starts no subprocess, socket, Temporal service, Worker,
Gateway, or network call.
"""

from __future__ import annotations

import threading

import pytest

from sachima_supervisor.runtime_spine import (
    RUNTIME_EVENT_LEAK_DETECTED,
    RUNTIME_INVALID_EVENT,
    RUNTIME_INVALID_TASK_ID,
    RUNTIME_SEQ_VIOLATION,
    STABLE_CODES,
    SpineError,
    TaskEvent,
    TaskEventLog,
    build_event_body,
    event_projection,
    scan_for_leak,
    validate_event_body,
    verify_seq_contiguous,
)

# The exact canary set the R1 gate requires in event-body no-leak tests.
_LEAK_CANARIES = (
    "raw_prompt",
    "agent_stdout",
    "tool_output",
    "card_json",
    "chat_id",
    "oc_",
    "ou_",
    "/tmp/",
    "sk-",
    "bearer ",
)


# --------------------------------------------------------------------------- #
# A. Single seq authority
# --------------------------------------------------------------------------- #
def test_append_assigns_monotonic_seq_1_to_n() -> None:
    log = TaskEventLog()
    events = [log.append("task_alpha", build_event_body(event_type="progress")) for _ in range(5)]
    assert [e.seq for e in events] == [1, 2, 3, 4, 5]
    assert log.last_seq("task_alpha") == 5
    assert log.event_count("task_alpha") == 5
    assert all(type(e) is TaskEvent for e in events)
    assert all(e.task_id == "task_alpha" for e in events)


def test_seq_authority_is_per_task_independent() -> None:
    log = TaskEventLog()
    a1 = log.append("task_alpha", build_event_body(event_type="progress"))
    b1 = log.append("task_beta", build_event_body(event_type="progress"))
    a2 = log.append("task_alpha", build_event_body(event_type="progress"))
    assert (a1.seq, a2.seq) == (1, 2)
    assert b1.seq == 1
    assert log.last_seq("task_beta") == 1


def test_returned_event_is_frozen() -> None:
    log = TaskEventLog()
    event = log.append("task_alpha", build_event_body(event_type="task_created"))
    with pytest.raises(Exception):
        event.seq = 99  # type: ignore[misc]


def test_caller_cannot_supply_seq_material() -> None:
    # A body carrying a caller-chosen ``seq`` is caller-supplied seq material and
    # must fail closed — only the log assigns seq.
    log = TaskEventLog()
    with pytest.raises(SpineError) as exc:
        log.append("task_alpha", {"event_type": "progress", "seq": 7})
    assert exc.value.code == RUNTIME_INVALID_EVENT


def test_body_with_unknown_or_identity_key_rejected() -> None:
    log = TaskEventLog()
    for bad in ({"event_type": "progress", "task_id": "task_alpha"}, {"event_type": "progress", "extra": 1}):
        with pytest.raises(SpineError) as exc:
            log.append("task_alpha", bad)
        assert exc.value.code == RUNTIME_INVALID_EVENT


def test_unknown_event_type_rejected() -> None:
    log = TaskEventLog()
    with pytest.raises(SpineError) as exc:
        log.append("task_alpha", {"event_type": "launch_subprocess"})
    assert exc.value.code == RUNTIME_INVALID_EVENT


def test_invalid_task_id_rejected() -> None:
    log = TaskEventLog()
    for bad in ("", "Task-Alpha", "task alpha", "1task", "chat_id_task"):
        with pytest.raises(SpineError) as exc:
            log.append(bad, build_event_body(event_type="progress"))
        assert exc.value.code in {RUNTIME_INVALID_TASK_ID, RUNTIME_EVENT_LEAK_DETECTED}


def test_verify_seq_contiguous_accepts_clean_and_rejects_gap_dup_reorder() -> None:
    log = TaskEventLog()
    good = [log.append("task_alpha", build_event_body(event_type="progress")) for _ in range(4)]
    verify_seq_contiguous(good)  # no raise

    for broken in (
        good[:2] + good[3:],       # gap (missing seq 3)
        good + [good[-1]],          # duplicate last
        [good[1], good[0]] + good[2:],  # out of order
    ):
        with pytest.raises(SpineError) as exc:
            verify_seq_contiguous(broken)
        assert exc.value.code == RUNTIME_SEQ_VIOLATION


def test_verify_seq_contiguous_rejects_mixed_task_ids() -> None:
    log = TaskEventLog()
    a = log.append("task_alpha", build_event_body(event_type="progress"))
    b = log.append("task_beta", build_event_body(event_type="progress"))
    with pytest.raises(SpineError) as exc:
        verify_seq_contiguous([a, b])
    assert exc.value.code == RUNTIME_SEQ_VIOLATION


def test_concurrent_appends_are_monotonic_and_gap_free() -> None:
    log = TaskEventLog()
    n = 64
    barrier = threading.Barrier(n)
    seqs: list[int] = []
    seqs_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        event = log.append("task_alpha", build_event_body(event_type="progress"))
        with seqs_lock:
            seqs.append(event.seq)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(seqs) == list(range(1, n + 1))  # strictly monotonic, gap-free, no dup
    assert log.last_seq("task_alpha") == n
    verify_seq_contiguous(log.events_for("task_alpha"))


def test_error_carries_only_stable_code_no_raw_material() -> None:
    log = TaskEventLog()
    secret = "raw_prompt: launch the missiles now"
    with pytest.raises(SpineError) as exc:
        log.append("task_alpha", build_event_body(event_type="progress", refs=(secret,)))
    assert exc.value.code in STABLE_CODES
    # The exception surfaces the stable code ONLY — never the raw material.
    assert str(exc.value) == exc.value.code
    assert "missiles" not in str(exc.value)


# --------------------------------------------------------------------------- #
# B. Refs-only events / no-leak
# --------------------------------------------------------------------------- #
def test_clean_refs_only_body_accepted() -> None:
    log = TaskEventLog()
    event = log.append(
        "task_alpha",
        build_event_body(
            event_type="milestone",
            status="running",
            refs=("claim_ref_input_0", "evidence_ref_9"),
            digests=("sha256:" + "a" * 64,),
            counts={"tool_calls": 3},
            error_code=None,
        ),
    )
    assert event.status == "running"
    assert event.refs == ("claim_ref_input_0", "evidence_ref_9")
    assert event.digests == ("sha256:" + "a" * 64,)
    assert scan_for_leak(build_event_body(event_type="milestone", refs=("claim_ref_input_0",))) is None


@pytest.mark.parametrize("canary", _LEAK_CANARIES)
def test_leak_canary_in_ref_value_rejected(canary: str) -> None:
    log = TaskEventLog()
    with pytest.raises(SpineError) as exc:
        log.append("task_alpha", {"event_type": "progress", "refs": (f"ref_{canary}_x",)})
    assert exc.value.code == RUNTIME_EVENT_LEAK_DETECTED


@pytest.mark.parametrize("canary", _LEAK_CANARIES)
def test_leak_canary_in_body_key_rejected(canary: str) -> None:
    # Unsafe KEYS must be rejected too, not just unsafe string values.
    log = TaskEventLog()
    with pytest.raises(SpineError) as exc:
        log.append("task_alpha", {"event_type": "progress", canary: "x"})
    assert exc.value.code in {RUNTIME_EVENT_LEAK_DETECTED, RUNTIME_INVALID_EVENT}


@pytest.mark.parametrize("canary", _LEAK_CANARIES)
def test_scan_for_leak_detects_value_and_key(canary: str) -> None:
    assert scan_for_leak({"note": f"x{canary}y"}) == RUNTIME_EVENT_LEAK_DETECTED
    assert scan_for_leak({canary: "clean"}) == RUNTIME_EVENT_LEAK_DETECTED
    assert scan_for_leak({"nested": ["a", {"deep": f"z{canary}"}]}) == RUNTIME_EVENT_LEAK_DETECTED


def test_scan_for_leak_supports_extra_canaries() -> None:
    assert scan_for_leak({"x": "clean_ref"}) is None
    assert (
        scan_for_leak({"x": "CANARY_marker_7e3f"}, canaries=("CANARY_marker_7e3f",))
        == RUNTIME_EVENT_LEAK_DETECTED
    )


def test_status_and_error_code_are_allowlisted_only() -> None:
    log = TaskEventLog()
    with pytest.raises(SpineError):
        log.append("task_alpha", {"event_type": "progress", "status": "launching_agent"})
    with pytest.raises(SpineError):
        log.append("task_alpha", {"event_type": "failed", "error_code": "arbitrary_freeform_code"})
    ok = log.append("task_alpha", {"event_type": "failed", "status": "failed", "error_code": RUNTIME_INVALID_EVENT})
    assert ok.error_code == RUNTIME_INVALID_EVENT


def test_digests_must_be_sha256() -> None:
    log = TaskEventLog()
    with pytest.raises(SpineError):
        log.append("task_alpha", {"event_type": "progress", "digests": ("md5:" + "a" * 32,)})
    with pytest.raises(SpineError):
        log.append("task_alpha", {"event_type": "progress", "digests": ("sha256:" + "A" * 64,)})


def test_counts_must_be_nonnegative_ints_with_safe_keys() -> None:
    log = TaskEventLog()
    with pytest.raises(SpineError):
        log.append("task_alpha", {"event_type": "progress", "counts": {"tool_calls": -1}})
    with pytest.raises(SpineError):
        log.append("task_alpha", {"event_type": "progress", "counts": {"tool_calls": "3"}})
    with pytest.raises(SpineError):
        log.append("task_alpha", {"event_type": "progress", "counts": {"chat_id": 1}})


def test_validate_event_body_is_pure_and_normalizing() -> None:
    fields = validate_event_body({"event_type": "progress", "counts": {"b": 2, "a": 1}})
    # counts normalized to a sorted, hashable tuple of pairs (byte-stable downstream)
    assert fields["counts"] == (("a", 1), ("b", 2))


# --------------------------------------------------------------------------- #
# C. Exported TaskEvent is fail-closed against direct / hostile construction
# --------------------------------------------------------------------------- #
# ``TaskEvent`` is exported public surface. It must never be trustable purely
# because it was constructed — direct, ``__new__``-forged, or subclassed hostile
# instances must fail closed at construction and at every event/projection
# boundary, never relying on ``TaskEventLog.append`` / ``validate_event_body``.
def test_clean_direct_taskevent_construction_is_accepted() -> None:
    # The fix is fail-CLOSED, not fail-shut: a fully allowlisted direct
    # construction must still succeed and project cleanly.
    event = TaskEvent(
        task_id="task_alpha",
        seq=1,
        event_type="progress",
        status="running",
        refs=("claim_ref_0", "evidence_ref_1"),
        digests=("sha256:" + "a" * 64,),
        counts=(("tool_calls", 3),),
        flags=(("needs_agent", True),),
        error_code=RUNTIME_INVALID_EVENT,
    )
    view = event_projection(event)
    assert view["refs"] == ["claim_ref_0", "evidence_ref_1"]
    assert view["counts"] == {"tool_calls": 3}
    assert view["flags"] == {"needs_agent": True}


@pytest.mark.parametrize("canary", _LEAK_CANARIES)
def test_direct_taskevent_with_unsafe_ref_fails_closed(canary: str) -> None:
    # Codex repro: event_projection(TaskEvent(... refs=("raw_prompt_secret",))).
    # Construction itself must fail closed so no unsafe ref can reach a view.
    with pytest.raises(SpineError) as exc:
        TaskEvent(task_id="task_alpha", seq=1, event_type="progress", refs=(f"ref_{canary}",))
    assert exc.value.code in STABLE_CODES
    assert str(exc.value) == exc.value.code  # stable code only, never raw material
    assert canary.strip() not in str(exc.value)


def test_direct_taskevent_with_unknown_event_type_fails_closed() -> None:
    with pytest.raises(SpineError) as exc:
        TaskEvent(task_id="task_alpha", seq=1, event_type="unknown_event")
    assert exc.value.code == RUNTIME_INVALID_EVENT


def test_direct_taskevent_with_unknown_status_or_error_code_fails_closed() -> None:
    with pytest.raises(SpineError) as exc:
        TaskEvent(task_id="task_alpha", seq=1, event_type="progress", status="launching_agent")
    assert exc.value.code == RUNTIME_INVALID_EVENT
    with pytest.raises(SpineError) as exc:
        TaskEvent(task_id="task_alpha", seq=1, event_type="failed", error_code="arbitrary_code")
    assert exc.value.code == RUNTIME_INVALID_EVENT


def test_direct_taskevent_with_unknown_flag_key_fails_closed() -> None:
    # Codex repro: flags=(("needs_write", True),) implies write capability (out of
    # R1) and must never construct.
    with pytest.raises(SpineError) as exc:
        TaskEvent(task_id="task_alpha", seq=1, event_type="progress", flags=(("needs_write", True),))
    assert exc.value.code == RUNTIME_INVALID_EVENT
    # a known flag key with a non-bool value is also rejected
    with pytest.raises(SpineError):
        TaskEvent(task_id="task_alpha", seq=1, event_type="progress", flags=(("needs_agent", 1),))  # type: ignore[arg-type]


def test_direct_taskevent_with_invalid_counts_or_digests_fails_closed() -> None:
    for bad in ((("tool_calls", -1),), (("tool_calls", True),), (("chat_id", 1),)):
        with pytest.raises(SpineError) as exc:
            TaskEvent(task_id="task_alpha", seq=1, event_type="progress", counts=bad)
        assert exc.value.code in STABLE_CODES
    with pytest.raises(SpineError):
        TaskEvent(task_id="task_alpha", seq=1, event_type="progress", digests=("md5:" + "a" * 32,))
    with pytest.raises(SpineError):
        TaskEvent(task_id="task_alpha", seq=1, event_type="progress", digests=("sha256:" + "A" * 64,))


def test_direct_taskevent_with_invalid_seq_fails_closed() -> None:
    # seq must be an exact int >= 1 (bool is not an int here). The log is the only
    # seq authority; a forged non-positive / mistyped seq fails closed.
    for bad_seq in (0, -1, True, "1"):
        with pytest.raises(SpineError) as exc:
            TaskEvent(task_id="task_alpha", seq=bad_seq, event_type="progress")  # type: ignore[arg-type]
        assert exc.value.code == RUNTIME_INVALID_EVENT


def test_direct_taskevent_with_unsafe_task_id_fails_closed() -> None:
    for bad in ("Task-Alpha", "chat_id_task", "1task"):
        with pytest.raises(SpineError) as exc:
            TaskEvent(task_id=bad, seq=1, event_type="progress")
        assert exc.value.code in {RUNTIME_INVALID_TASK_ID, RUNTIME_INVALID_EVENT, RUNTIME_EVENT_LEAK_DETECTED}


def test_event_projection_rejects_new_forged_event() -> None:
    # An attacker can bypass __init__/__post_init__ via object.__new__ +
    # object.__setattr__ (frozen). ``type(forged) is TaskEvent`` holds, so a bare
    # type() gate is not enough — event_projection must RE-VALIDATE the fields.
    forged = object.__new__(TaskEvent)
    for name, value in (
        ("task_id", "task_alpha"),
        ("seq", 1),
        ("event_type", "progress"),
        ("status", None),
        ("refs", ("ref_raw_prompt",)),
        ("digests", ()),
        ("counts", ()),
        ("flags", ()),
        ("error_code", None),
    ):
        object.__setattr__(forged, name, value)
    assert type(forged) is TaskEvent  # passes a naive identity gate
    with pytest.raises(SpineError) as exc:
        event_projection(forged)
    assert exc.value.code in STABLE_CODES
    assert "raw_prompt" not in str(exc.value)


def test_event_projection_rejects_partial_forged_event_with_stable_code() -> None:
    # Missing attributes on a forged TaskEvent should still fail closed with a
    # stable SpineError code, not leak an AttributeError from the trust boundary.
    forged = object.__new__(TaskEvent)
    object.__setattr__(forged, "task_id", "task_alpha")
    object.__setattr__(forged, "seq", 1)
    with pytest.raises(SpineError) as exc:
        event_projection(forged)
    assert exc.value.code == RUNTIME_INVALID_EVENT
    assert str(exc.value) == RUNTIME_INVALID_EVENT


def test_event_projection_rejects_hostile_subclass() -> None:
    class _HostileEvent(TaskEvent):
        def __post_init__(self) -> None:  # skip the fail-closed validation
            return None

    hostile = _HostileEvent(
        task_id="task_alpha", seq=1, event_type="unknown_event", flags=(("needs_write", True),)
    )
    with pytest.raises(SpineError) as exc:
        event_projection(hostile)
    assert exc.value.code in STABLE_CODES


# --------------------------------------------------------------------------- #
# D. TaskEventLog internal state is not constructor-injectable
# --------------------------------------------------------------------------- #
# ``TaskEventLog`` is the SOLE monotonic seq authority. Its generated dataclass
# ``__init__`` must not accept its internal fields (``_events`` / ``_lock``):
# a caller able to seed ``_events`` with pre-numbered events would bypass the
# log as the single seq authority, and an injected lock would break the
# concurrency guarantee. Internal state must be owned, not seedable.
def _forged_event(*, seq: int) -> TaskEvent:
    forged = object.__new__(TaskEvent)
    for name, value in (
        ("task_id", "task_alpha"),
        ("seq", seq),
        ("event_type", "progress"),
        ("status", None),
        ("refs", ()),
        ("digests", ()),
        ("counts", ()),
        ("flags", ()),
        ("error_code", None),
    ):
        object.__setattr__(forged, name, value)
    return forged


def test_task_event_log_rejects_seeded_events_via_constructor() -> None:
    # A caller pre-numbering events (seq=99) and seeding them through the
    # constructor would make the log no longer the sole seq authority. The
    # internal ``_events`` field must not be a constructor parameter.
    with pytest.raises(TypeError):
        TaskEventLog(_events={"task_alpha": [_forged_event(seq=99)]})  # type: ignore[call-arg]


def test_task_event_log_rejects_injected_lock_via_constructor() -> None:
    with pytest.raises(TypeError):
        TaskEventLog(_lock=threading.RLock())  # type: ignore[call-arg]


def test_task_event_log_zero_arg_construction_remains_the_only_seq_authority() -> None:
    # Normal zero-arg construction is unchanged and the log alone assigns seq
    # strictly 1..N — no pre-seeded state leaks in.
    log = TaskEventLog()
    assert log.has_task("task_alpha") is False
    events = [log.append("task_alpha", build_event_body(event_type="progress")) for _ in range(3)]
    assert [e.seq for e in events] == [1, 2, 3]
    assert log.last_seq("task_alpha") == 3
