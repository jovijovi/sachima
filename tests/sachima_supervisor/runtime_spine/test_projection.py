"""R1 — deterministic Status Projection (design §6, §11.3).

RED/GREEN tests for the pure, byte-stable replay function from an ordered event
list to a status projection. The projection is a read-only consumer: it assigns
no seq, appends no events, launches no work, and carries only refs / counts /
status / stable codes.
"""

from __future__ import annotations

import json

import pytest

from sachima_supervisor.runtime_spine import (
    ALLOWED_PROJECTION_KEYS,
    PROJECTION_TYPE,
    RUNTIME_INVALID_EVENT,
    RUNTIME_INVALID_PROJECTION,
    RUNTIME_SEQ_VIOLATION,
    STABLE_CODES,
    SpineError,
    TaskEvent,
    TaskEventLog,
    build_event_body,
    project,
    scan_for_leak,
    serialize_projection,
)


def _build_log() -> TaskEventLog:
    log = TaskEventLog()
    log.append("task_alpha", build_event_body(event_type="task_created", status="created",
                                               flags={"needs_agent": True, "needs_durable": False}))
    log.append("task_alpha", build_event_body(event_type="progress", status="running",
                                               refs=("evidence_ref_2",), counts={"tool_calls": 1}))
    log.append("task_alpha", build_event_body(event_type="permission_requested", status="permission_wait",
                                               refs=("permission_ref_3",)))
    log.append("task_alpha", build_event_body(event_type="completed", status="completed",
                                               refs=("artifact_ref_4",)))
    return log


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_projection_is_byte_stable_for_same_events() -> None:
    events = _build_log().events_for("task_alpha")
    a = serialize_projection(project(events))
    b = serialize_projection(project(events))
    assert a == b
    assert isinstance(a, bytes)
    # A fresh, independently-built identical event list yields identical bytes.
    rebuilt = _build_log().events_for("task_alpha")
    assert serialize_projection(project(rebuilt)) == a


def test_projection_dict_equality_is_deterministic() -> None:
    events = _build_log().events_for("task_alpha")
    assert project(events) == project(events)


# --------------------------------------------------------------------------- #
# Tracked fields
# --------------------------------------------------------------------------- #
def test_projection_tracks_required_fields() -> None:
    proj = project(_build_log().events_for("task_alpha"))
    assert proj["type"] == PROJECTION_TYPE
    assert proj["task_id"] == "task_alpha"
    assert proj["last_seq"] == 4
    assert proj["event_count"] == 4
    assert proj["status"] == "completed"
    assert proj["terminal"] is True
    assert proj["flags"] == {"needs_agent": True, "needs_durable": False}
    assert proj["error_code"] is None
    # refs are surfaced, deterministically ordered, de-duplicated
    assert proj["refs"] == ["artifact_ref_4", "evidence_ref_2", "permission_ref_3"]
    assert proj["event_type_counts"]["progress"] == 1


def test_projection_status_tracks_last_status_and_error_code() -> None:
    log = TaskEventLog()
    log.append("task_beta", build_event_body(event_type="task_created", status="created"))
    log.append("task_beta", build_event_body(event_type="progress", status="running"))
    log.append("task_beta", build_event_body(event_type="failed", status="failed",
                                             error_code=RUNTIME_INVALID_EVENT))
    proj = project(log.events_for("task_beta"))
    assert proj["status"] == "failed"
    assert proj["terminal"] is True
    assert proj["error_code"] == RUNTIME_INVALID_EVENT


def test_projection_keys_are_allowlisted_and_leak_free() -> None:
    proj = project(_build_log().events_for("task_alpha"))
    assert set(proj).issubset(ALLOWED_PROJECTION_KEYS)
    assert scan_for_leak(proj) is None


def test_empty_projection_requires_task_id() -> None:
    proj = project((), task_id="task_empty")
    assert proj["task_id"] == "task_empty"
    assert proj["last_seq"] == 0
    assert proj["event_count"] == 0
    assert proj["status"] is None
    assert proj["terminal"] is False
    assert proj["flags"] == {"needs_agent": False, "needs_durable": False}
    with pytest.raises(SpineError) as exc:
        project(())
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


# --------------------------------------------------------------------------- #
# Read-only / fail-closed replay
# --------------------------------------------------------------------------- #
def test_projection_does_not_mutate_or_append_to_log() -> None:
    log = _build_log()
    before = log.event_count("task_alpha")
    project(log.events_for("task_alpha"))
    assert log.event_count("task_alpha") == before  # projection never appends


def test_projection_rejects_gapped_or_reordered_events() -> None:
    events = list(_build_log().events_for("task_alpha"))
    for broken in (events[:1] + events[2:], list(reversed(events))):
        with pytest.raises(SpineError) as exc:
            project(broken)
        assert exc.value.code == RUNTIME_SEQ_VIOLATION


def test_projection_task_id_mismatch_rejected() -> None:
    events = _build_log().events_for("task_alpha")
    with pytest.raises(SpineError):
        project(events, task_id="task_other")


# --------------------------------------------------------------------------- #
# Fail-closed against hostile / directly-constructed TaskEvent instances
# --------------------------------------------------------------------------- #
def test_project_rejects_new_forged_invalid_event() -> None:
    # Codex repro: project([TaskEvent(event_type="unknown_event",
    # flags=(("needs_write", True),))]). These fields are NOT no-leak markers, so
    # the projection-level leak scan does not catch them — the replay path itself
    # must re-validate every event and fail closed. A forged event (built via
    # object.__new__, bypassing __post_init__) proves the boundary cannot rely on
    # the append path or a bare type() gate.
    forged = object.__new__(TaskEvent)
    for name, value in (
        ("task_id", "task_alpha"),
        ("seq", 1),
        ("event_type", "unknown_event"),
        ("status", None),
        ("refs", ()),
        ("digests", ()),
        ("counts", ()),
        ("flags", (("needs_write", True),)),
        ("error_code", None),
    ):
        object.__setattr__(forged, name, value)
    assert type(forged) is TaskEvent  # passes a naive identity gate
    with pytest.raises(SpineError) as exc:
        project([forged])
    assert exc.value.code in STABLE_CODES


def test_project_rejects_new_forged_unsafe_ref_event() -> None:
    forged = object.__new__(TaskEvent)
    for name, value in (
        ("task_id", "task_alpha"),
        ("seq", 1),
        ("event_type", "progress"),
        ("status", "running"),
        ("refs", ("ref_raw_prompt",)),
        ("digests", ()),
        ("counts", ()),
        ("flags", ()),
        ("error_code", None),
    ):
        object.__setattr__(forged, name, value)
    with pytest.raises(SpineError) as exc:
        project([forged])
    assert exc.value.code in STABLE_CODES
    assert "raw_prompt" not in str(exc.value)


def test_project_rejects_partial_forged_event_with_stable_code() -> None:
    forged = object.__new__(TaskEvent)
    object.__setattr__(forged, "task_id", "task_alpha")
    object.__setattr__(forged, "seq", 1)
    with pytest.raises(SpineError) as exc:
        project([forged])
    assert exc.value.code == RUNTIME_INVALID_EVENT
    assert str(exc.value) == RUNTIME_INVALID_EVENT


def test_project_rejects_hostile_subclass_event() -> None:
    class _HostileEvent(TaskEvent):
        def __post_init__(self) -> None:  # skip the fail-closed validation
            return None

    hostile = _HostileEvent(
        task_id="task_alpha", seq=1, event_type="unknown_event", flags=(("needs_write", True),)
    )
    with pytest.raises(SpineError) as exc:
        project([hostile])
    assert exc.value.code in STABLE_CODES


# --------------------------------------------------------------------------- #
# serialize_projection fails closed on VALUE shape + no-leak, not just keys
#
# Codex blocker: ``serialize_projection`` only checked the projection key
# allowlist before JSON. A caller can hand-build / mutate a projection whose keys
# are all allowlisted but whose *values* are unsafe (raw refs, platform material,
# malformed flags/counts/status, a forged type marker) and serialize it. The
# public serialization surface must validate value shape and no-leak, not just
# keys — exactly like ``TaskEvent``/``validate_event_body`` do for events.
# --------------------------------------------------------------------------- #
def _clean_projection() -> dict:
    """A real, clean projection (all allowlisted keys, safe values) to mutate."""

    return dict(project(_build_log().events_for("task_alpha")))


def test_clean_projection_baseline_has_only_allowlisted_keys() -> None:
    # Guards the mutation tests below: the baseline itself must be key-clean, so a
    # rejection can only come from an unsafe VALUE, never a stray key.
    assert set(_clean_projection()) == set(ALLOWED_PROJECTION_KEYS)


@pytest.mark.parametrize(
    "bad_ref",
    [
        "ref_raw_prompt_body",   # raw payload marker
        "card_json_ref",         # card material
        "oc_open_chat_1",        # platform channel id
        "ou_open_user_1",        # platform open id
    ],
)
def test_serialize_rejects_allowed_key_projection_with_unsafe_refs(bad_ref: str) -> None:
    proj = _clean_projection()
    proj["refs"] = [bad_ref]
    # Keys still look fine — only the ref VALUE is unsafe.
    assert set(proj).issubset(ALLOWED_PROJECTION_KEYS)
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION
    # No-leak: the rejected material never rides out in the error text (the
    # message is exactly the stable code).
    assert str(exc.value) == RUNTIME_INVALID_PROJECTION
    assert bad_ref not in str(exc.value)


def test_serialize_rejects_projection_with_private_path_ref() -> None:
    proj = _clean_projection()
    proj["refs"] = ["/tmp/agent_scratch/secret"]
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION
    assert "/tmp/" not in str(exc.value)


@pytest.mark.parametrize(
    "bad_flags",
    [
        {"needs_agent": True},                              # missing needs_durable
        {"needs_agent": True, "needs_durable": False, "needs_write": True},  # unknown flag key
        {"needs_agent": "true", "needs_durable": False},    # non-bool flag value
        {"needs_agent": 1, "needs_durable": 0},             # int posing as bool
    ],
)
def test_serialize_rejects_projection_with_malformed_flags(bad_flags: dict) -> None:
    proj = _clean_projection()
    proj["flags"] = bad_flags
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


@pytest.mark.parametrize(
    "bad_counts",
    [
        {"progress": -1},              # negative count
        {"progress": True},           # bool posing as count
        {"progress": "1"},            # non-int count
        {"not_an_event_type": 1},     # unknown event-type key
    ],
)
def test_serialize_rejects_projection_with_malformed_event_type_counts(bad_counts: dict) -> None:
    proj = _clean_projection()
    proj["event_type_counts"] = bad_counts
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


def test_serialize_rejects_projection_with_unknown_status() -> None:
    proj = _clean_projection()
    proj["status"] = "exfiltrating"
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


def test_serialize_rejects_projection_with_unknown_error_code() -> None:
    proj = _clean_projection()
    proj["error_code"] = "totally_made_up_code"
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


@pytest.mark.parametrize("bad_task_id", ["Task_Alpha", "task-alpha", "1task", "", "task_alpha "])
def test_serialize_rejects_projection_with_malformed_task_id(bad_task_id: str) -> None:
    proj = _clean_projection()
    proj["task_id"] = bad_task_id
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("last_seq", -1),
        ("last_seq", True),      # bool posing as seq
        ("last_seq", "4"),       # non-int
        ("event_count", -1),
        ("event_count", True),
        ("event_count", 1.0),    # float
    ],
)
def test_serialize_rejects_projection_with_bad_seq_or_count(field: str, bad_value: object) -> None:
    proj = _clean_projection()
    proj[field] = bad_value
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


def test_serialize_rejects_projection_with_wrong_type_marker() -> None:
    proj = _clean_projection()
    proj["type"] = "sachima.runtime_spine.some_other_projection.v9"
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


def test_serialize_rejects_projection_with_inconsistent_terminal_flag() -> None:
    proj = _clean_projection()  # status="completed", terminal=True
    proj["status"] = "running"  # non-terminal, but terminal left True → inconsistent
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


def test_serialize_rejects_projection_with_non_bool_terminal_flag() -> None:
    proj = _clean_projection()
    proj["terminal"] = "yes"
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


def test_serialize_still_accepts_clean_projection_and_is_byte_stable() -> None:
    proj = _clean_projection()
    out = serialize_projection(proj)
    assert isinstance(out, bytes)
    # Validation must not mutate the projection it serializes.
    assert proj == _clean_projection()
    # Still byte-stable across repeated serialization and round-trips cleanly.
    assert serialize_projection(proj) == out
    assert json.loads(out) == proj


def test_validate_projection_accepts_clean_output_and_returns_it() -> None:
    # ``validate_projection`` is the projection-level fail-closed check that
    # ``serialize_projection`` runs before JSON. It is not re-exported from the
    # package ``__init__`` (out of scope for this fix); import it from the module.
    from sachima_supervisor.runtime_spine.projection import validate_projection

    proj = _clean_projection()
    assert validate_projection(proj) == proj
    # scan-for-leak clean, keys allowlisted — the accept path is unchanged.
    assert scan_for_leak(proj) is None


# --------------------------------------------------------------------------- #
# serialize_projection fails closed on projection CONSISTENCY, not just per-value
# shape.
#
# Codex blocker: value-shape validation still accepts forged-but-allowlisted
# projections that ``project()`` could never emit — every value is individually
# well-formed, yet the cross-field invariants are broken:
#   * ``last_seq != event_count`` (project() replays a 1..N gap-free run, so the
#     last seq always equals the event count);
#   * ``sum(event_type_counts.values()) != event_count`` (each replayed event
#     contributes exactly one to its type count, so the total equals the count);
#   * duplicate or unsorted ``refs`` (project() emits ``sorted(set(refs))``).
# Such hand-mutated snapshots serialize today and could publish a forged status.
# The public serialization surface must fail closed on these invariants, not just
# on per-field shape, with the stable ``runtime_invalid_projection`` code only.
# --------------------------------------------------------------------------- #
def test_serialize_rejects_projection_with_last_seq_not_matching_event_count() -> None:
    proj = _clean_projection()  # last_seq == event_count == 4
    proj["last_seq"] = 99  # individually a valid non-negative int, but forged
    assert set(proj).issubset(ALLOWED_PROJECTION_KEYS)
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION
    assert str(exc.value) == RUNTIME_INVALID_PROJECTION


def test_serialize_rejects_projection_with_event_type_counts_total_mismatch() -> None:
    proj = _clean_projection()  # counts total == event_count == 4
    # Every entry stays individually valid (known type, positive int) — only the
    # TOTAL now contradicts event_count, a shape project() never emits.
    proj["event_type_counts"] = dict(proj["event_type_counts"])
    proj["event_type_counts"]["progress"] += 1  # total 5 != event_count 4
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


def test_serialize_rejects_projection_with_duplicate_refs() -> None:
    proj = _clean_projection()
    # Each ref is individually a safe id and leak-free — only the duplication is
    # unsafe (project() de-dupes via a set, so it can never emit a repeat).
    proj["refs"] = ["artifact_ref_4", "artifact_ref_4", "evidence_ref_2", "permission_ref_3"]
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


def test_serialize_rejects_projection_with_unsorted_refs() -> None:
    proj = _clean_projection()
    # A permutation of the clean, de-duped refs — every element is safe, but the
    # order is not the canonical sorted order project() emits.
    proj["refs"] = ["permission_ref_3", "evidence_ref_2", "artifact_ref_4"]
    assert sorted(proj["refs"]) != proj["refs"]
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION


def test_clean_project_output_satisfies_consistency_invariants_and_stays_byte_stable() -> None:
    # Guard the fix against over-rejecting: genuine project() output must satisfy
    # every consistency invariant and still serialize byte-stably.
    proj = _clean_projection()
    assert proj["last_seq"] == proj["event_count"]
    assert sum(proj["event_type_counts"].values()) == proj["event_count"]
    assert proj["refs"] == sorted(set(proj["refs"]))
    out = serialize_projection(proj)
    assert isinstance(out, bytes)
    assert serialize_projection(proj) == out
    # An empty projection is consistent too (0 == 0, empty refs/counts).
    empty = project((), task_id="task_empty")
    assert empty["last_seq"] == empty["event_count"] == 0
    assert serialize_projection(empty) == serialize_projection(project((), task_id="task_empty"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "running"),
        ("error_code", RUNTIME_INVALID_EVENT),
        ("refs", ["evidence_ref_1"]),
        ("event_type_counts", {"progress": 0}),
        ("flags", {"needs_agent": True, "needs_durable": False}),
    ],
)
def test_serialize_rejects_empty_projection_with_forged_carried_state(
    field: str, value: object
) -> None:
    # project((), task_id=...) emits a fully empty snapshot: no status, no refs,
    # no counts, no error, default-false flags. Any carried state on event_count=0
    # is forged even if it is individually well-formed.
    proj = project((), task_id="task_empty")
    proj[field] = value
    if field == "status":
        proj["terminal"] = False  # keep terminal consistency so the empty-state invariant is tested
    with pytest.raises(SpineError) as exc:
        serialize_projection(proj)
    assert exc.value.code == RUNTIME_INVALID_PROJECTION
