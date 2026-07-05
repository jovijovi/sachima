"""PR3 — Sachima live progress safe projection acceptance tests.

The module under test consumes agent-run-supervisor's already-merged caller
cursor API shape (``load_progress`` / ``read_event_page`` over an artifact dir)
through an *injected* reader and maps it into a local/offline, refs-only,
byte-stable, validated Sachima read-model. These tests drive it with in-test
fake readers only — no real library, no real artifact I/O — and assert
externally-observable safe behavior: the closed mapping, the fail-closed stable
codes, the no-leak serialized bytes, forgery rejection, and determinism.
"""

from __future__ import annotations

import importlib
import re

import pytest

from sachima_supervisor.runtime_spine import SpineError, TaskEventLog, scan_for_leak


def _mod():
    return importlib.import_module(
        "sachima_supervisor.runtime_spine.live_progress_projection"
    )


# --------------------------------------------------------------------------- #
# Fakes modeling the ARS caller shapes (ProgressSnapshot / EventPage / EventRecord)
# --------------------------------------------------------------------------- #
class _FakeProgress:
    def __init__(self, **k):
        self.__dict__.update(k)


class _FakePage:
    def __init__(self, records, next_cursor, has_more):
        self.records, self.next_cursor, self.has_more = records, next_cursor, has_more


class _FakeRec:
    def __init__(self, **k):
        self.__dict__.update(k)


class _FakeReader:
    def __init__(self, progress, page):
        self._p, self._page = progress, page

    def load_progress(self, artifact_dir):
        return self._p

    def read_event_page(self, artifact_dir, *, after_seq=None, limit=100):
        return self._page


class _CursorAwareReader:
    """Verifies the builder forwards ``after_seq`` and serves the matching page."""

    def __init__(self, progress, pages_by_after):
        self._p, self._pages = progress, pages_by_after

    def load_progress(self, artifact_dir):
        return self._p

    def read_event_page(self, artifact_dir, *, after_seq=None, limit=100):
        assert after_seq in self._pages, after_seq
        return self._pages[after_seq]


def _progress(state="running", *, schema_version=1, last_seq=3, event_count=3):
    return _FakeProgress(
        schema_version=schema_version,
        state=state,
        last_seq=last_seq,
        event_count=event_count,
    )


def _rec(seq, *, family="tool", kind="tool_call", status="running", text_length=0, **extra):
    return _FakeRec(seq=seq, family=family, kind=kind, status=status, text_length=text_length, **extra)


# --------------------------------------------------------------------------- #
# 1. Happy path — progress + cursor page → refs-only projection
# --------------------------------------------------------------------------- #
def test_maps_progress_and_events_refs_only():
    m = _mod()
    reader = _FakeReader(
        _progress("running", last_seq=3, event_count=3),
        _FakePage(
            (
                _rec(1, family="lifecycle", kind="agent_started", status="running", text_length=0),
                _rec(2, family="tool", kind="tool_call", status="running", text_length=42),
                _rec(3, family="message", kind="assistant", status="running", text_length=120),
            ),
            next_cursor=3,
            has_more=False,
        ),
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run/abc", "artifact_local_0")

    assert proj.type == m.LIVE_PROGRESS_PROJECTION_TYPE
    assert proj.available is True
    assert proj.error_code is None
    assert proj.artifact_ref == "artifact_local_0"
    assert proj.task_id is None
    assert proj.supervisor_state == "active"
    assert proj.observed_event_count == 3
    assert proj.observed_last_seq == 3
    assert proj.resume_cursor == 3
    assert proj.has_more is False
    assert proj.stale is False
    assert [r.seq for r in proj.records] == [1, 2, 3]
    assert proj.records[1].family == "tool" and proj.records[1].kind == "tool_call"
    assert proj.records[2].observed_status == "active"
    assert proj.records[2].text_length == 120
    # summary is never carried on a record
    assert all(not hasattr(r, "summary") for r in proj.records)


def test_optional_task_id_association():
    m = _mod()
    reader = _FakeReader(_progress(last_seq=0, event_count=0), _FakePage((), None, False))
    proj = m.build_live_progress_projection(
        reader, "/tmp/run", "artifact_local_1", task_id="task_alpha"
    )
    assert proj.task_id == "task_alpha"


# --------------------------------------------------------------------------- #
# 1b. Nullable ARS producer fields normalize (NOT corrupt)
# The producer's ``EventRecord`` declares ``kind`` / ``status`` / ``text_length``
# nullable; real streams emit ``run_started`` / ``agent_message_delta`` /
# ``run_completed`` records that omit some of them. They must normalize to closed
# safe tokens, never fail the page closed. ``family`` stays required/safe.
# --------------------------------------------------------------------------- #
def test_nullable_producer_fields_normalize_not_corrupt():
    m = _mod()
    # Producer-style sequence (mirrors agent-run-supervisor hermes_caller
    # test_event_cursor.py 49-57): family is the event ``type``; kind/status/
    # text_length are absent/None on the lifecycle + delta records.
    reader = _FakeReader(
        _progress("running", last_seq=5, event_count=5),
        _FakePage(
            (
                _FakeRec(seq=1, family="run_started", kind=None, status=None, text_length=None),
                _FakeRec(seq=2, family="tool_started", kind="read", status=None, text_length=None),
                _FakeRec(seq=3, family="tool_completed", kind=None, status="completed", text_length=None),
                _FakeRec(seq=4, family="agent_message_delta", kind=None, status=None, text_length=128),
                _FakeRec(seq=5, family="run_completed", kind=None, status=None, text_length=None),
            ),
            next_cursor=5,
            has_more=False,
        ),
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run/abc", "artifact_local_0")

    assert proj.available is True and proj.error_code is None
    assert len(proj.records) == 5
    by_seq = {r.seq: r for r in proj.records}
    # kind: None → safe closed token "unknown"; a present safe token is preserved.
    assert by_seq[1].kind == "unknown"
    assert by_seq[2].kind == "read"
    assert by_seq[3].kind == "unknown"
    assert by_seq[5].kind == "unknown"
    # observed_status: None → "unknown"; "completed" → coarse non-verdict "settled".
    assert by_seq[1].observed_status == "unknown"
    assert by_seq[3].observed_status == "settled"
    assert by_seq[4].observed_status == "unknown"
    # text_length: None → 0; a present value is preserved unchanged.
    assert by_seq[1].text_length == 0
    assert by_seq[4].text_length == 128
    assert by_seq[5].text_length == 0
    assert proj.resume_cursor == 5 and proj.has_more is False
    # Normalization introduces no raw material and stringifies no raw None.
    assert scan_for_leak(proj.as_dict()) is None
    blob = m.serialize_live_progress_projection(proj)
    for marker in (b"summary", b"/tmp/", b"/home/", b"None"):
        assert marker not in blob


# --------------------------------------------------------------------------- #
# 2. Resume cursor mapping
# --------------------------------------------------------------------------- #
def test_resume_cursor_maps_and_second_page_only_higher_non_gap_seqs():
    m = _mod()
    page1 = _FakePage(
        (_rec(1, family="lifecycle", kind="agent_started"), _rec(2)),
        next_cursor=2,
        has_more=True,
    )
    proj1 = m.build_live_progress_projection(
        _FakeReader(_progress(last_seq=2, event_count=2), page1), "/tmp/run", "artifact_local_0"
    )
    assert proj1.resume_cursor == 2 and proj1.has_more is True

    # second page resumes after_seq=2, seqs strictly greater and NOT gap-free (3, 5)
    page2 = _FakePage(
        (_rec(3, family="message", kind="assistant"), _rec(5, family="message", kind="assistant", status="completed")),
        next_cursor=5,
        has_more=False,
    )
    reader2 = _CursorAwareReader(_progress(last_seq=5, event_count=4), {2: page2})
    proj2 = m.build_live_progress_projection(
        reader2, "/tmp/run", "artifact_local_0", after_seq=proj1.resume_cursor
    )
    seqs = [r.seq for r in proj2.records]
    assert seqs == [3, 5]  # strictly increasing, all > cursor 2, gaps accepted
    assert all(s > 2 for s in seqs)
    assert proj2.resume_cursor == 5 and proj2.has_more is False


def test_seq_not_strictly_after_cursor_is_corrupt():
    m = _mod()
    # after_seq=5 (exclusive) but the page echoes seq=5 → off-contract → corrupt
    reader = _CursorAwareReader(
        _progress(last_seq=5, event_count=5), {5: _FakePage((_rec(5),), next_cursor=5, has_more=False)}
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0", after_seq=5)
    assert proj.available is False and proj.error_code == "live_progress_corrupt"


def test_non_monotonic_page_is_corrupt():
    m = _mod()
    reader = _FakeReader(
        _progress(last_seq=3, event_count=2),
        _FakePage((_rec(3), _rec(2)), next_cursor=3, has_more=False),
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0")
    assert proj.available is False and proj.error_code == "live_progress_corrupt"
    assert proj.records == ()


# --------------------------------------------------------------------------- #
# 3. Missing progress → unavailable
# --------------------------------------------------------------------------- #
def test_missing_progress_fails_closed_unavailable():
    m = _mod()
    proj = m.build_live_progress_projection(
        _FakeReader(None, _FakePage((), None, False)), "/tmp/run/abc", "artifact_local_0"
    )
    assert proj.available is False
    assert proj.error_code == "live_progress_unavailable"
    assert proj.records == ()
    assert proj.supervisor_state == "unknown"
    assert proj.resume_cursor is None and proj.has_more is False
    assert proj.observed_event_count == 0 and proj.observed_last_seq == 0


def test_progress_present_empty_page_is_available_just_started():
    m = _mod()
    reader = _FakeReader(_progress(last_seq=0, event_count=0), _FakePage((), None, False))
    proj = m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0")
    assert proj.available is True
    assert proj.records == ()
    assert proj.has_more is False and proj.resume_cursor is None
    assert proj.observed_event_count == 0 and proj.stale is False


# --------------------------------------------------------------------------- #
# 4. Lazy default reader with absent library → unavailable, no ImportError escape
# --------------------------------------------------------------------------- #
def test_default_reader_absent_library_unavailable(monkeypatch):
    m = _mod()
    real = m.importlib.import_module

    def _boom(name, *a, **k):
        if name.startswith("agent_run_supervisor"):
            raise ImportError("agent_run_supervisor absent on host")
        return real(name, *a, **k)

    monkeypatch.setattr(m.importlib, "import_module", _boom)
    reader = m.DefaultLiveProgressReader()
    proj = m.build_live_progress_projection(reader, "/tmp/run/abc", "artifact_local_0")
    assert proj.available is False
    assert proj.error_code == "live_progress_unavailable"
    assert proj.records == ()


# --------------------------------------------------------------------------- #
# 5. ValueError / reader exception / bad record shape → corrupt, no raw leak
# --------------------------------------------------------------------------- #
def test_corrupt_progress_valueerror_no_raw_text():
    m = _mod()

    class _Boom:
        def load_progress(self, d):
            raise ValueError("bad int at /home/user/run/progress.json")

        def read_event_page(self, d, **k):
            raise AssertionError("not reached")

    proj = m.build_live_progress_projection(_Boom(), "/tmp/run/abc", "artifact_local_0")
    assert proj.available is False and proj.error_code == "live_progress_corrupt"
    assert scan_for_leak(proj.as_dict()) is None  # "/home/" / "/tmp/" never echoed


def test_generic_reader_exception_is_corrupt():
    m = _mod()

    class _Boom:
        def load_progress(self, d):
            raise RuntimeError("connection blew up: /var/secret/token")

        def read_event_page(self, d, **k):
            raise AssertionError("not reached")

    proj = m.build_live_progress_projection(_Boom(), "/tmp/run", "artifact_local_0")
    assert proj.available is False and proj.error_code == "live_progress_corrupt"
    assert scan_for_leak(proj.as_dict()) is None


def test_bad_record_shape_is_corrupt():
    m = _mod()
    # record missing the ``family`` attribute entirely → off-contract → corrupt
    bad = _FakeRec(seq=1, kind="tool_call", status="running", text_length=0)
    reader = _FakeReader(_progress(last_seq=1, event_count=1), _FakePage((bad,), 1, False))
    proj = m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0")
    assert proj.available is False and proj.error_code == "live_progress_corrupt"


def test_bad_progress_int_is_corrupt():
    m = _mod()
    reader = _FakeReader(
        _progress(schema_version="one", last_seq=1, event_count=1),  # non-int schema_version
        _FakePage((_rec(1),), 1, False),
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0")
    assert proj.available is False and proj.error_code == "live_progress_corrupt"


# --------------------------------------------------------------------------- #
# 6. Path / summary / raw text canaries never appear in dict or serialized bytes
# --------------------------------------------------------------------------- #
def test_path_and_summary_never_leak():
    m = _mod()
    reader = _FakeReader(
        _progress("running", last_seq=1, event_count=1),
        _FakePage(
            (
                _rec(
                    1,
                    family="message",
                    kind="assistant",
                    status="running",
                    text_length=9,
                    summary="visit /home/user/secret",
                ),
            ),
            next_cursor=1,
            has_more=False,
        ),
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run/abc/progress", "artifact_local_0")
    blob = m.serialize_live_progress_projection(proj)
    for marker in (b"/tmp/", b"/home/", b"secret", b"summary"):
        assert marker not in blob
    assert scan_for_leak(proj.as_dict()) is None


# --------------------------------------------------------------------------- #
# 7. Leaky token in family/kind → corrupt, not carried
# --------------------------------------------------------------------------- #
def test_leaky_token_fails_closed():
    m = _mod()
    reader = _FakeReader(
        _progress("running", last_seq=1, event_count=1),
        _FakePage((_rec(1, family="tool", kind="chat_id"),), next_cursor=1, has_more=False),
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0")
    assert proj.available is False and proj.error_code == "live_progress_corrupt"
    assert proj.records == ()
    assert b"chat_id" not in m.serialize_live_progress_projection(proj)


# --------------------------------------------------------------------------- #
# 8. Terminal states collapse to a coarse non-verdict ``settled``
# --------------------------------------------------------------------------- #
def test_terminal_states_are_not_a_verdict():
    m = _mod()
    for ars_state in ("completed", "failed", "cancelled", "killed"):
        proj = m.build_live_progress_projection(
            _FakeReader(_progress(ars_state, last_seq=1, event_count=1), _FakePage((), None, False)),
            "/tmp/run",
            "artifact_local_0",
        )
        assert proj.supervisor_state == "settled"  # no success/failure/cancel verdict


def test_state_and_status_vocabulary_is_closed():
    m = _mod()
    assert m.SUPERVISOR_OBSERVED_STATES == frozenset({"active", "waiting", "settled", "unknown"})
    assert m.OBSERVED_EVENT_STATUSES == frozenset({"active", "waiting", "settled", "unknown"})
    # unmapped / unexpected supervisor state → unknown, never echoed
    proj = m.build_live_progress_projection(
        _FakeReader(_progress("some_unmapped_state", last_seq=0, event_count=0), _FakePage((), None, False)),
        "/tmp/run",
        "artifact_local_0",
    )
    assert proj.supervisor_state == "unknown"
    assert b"some_unmapped_state" not in m.serialize_live_progress_projection(proj)


def test_waiting_states_map_to_waiting():
    m = _mod()
    for ars_state in ("permission_wait", "waiting", "waiting_for_permission", "blocked"):
        proj = m.build_live_progress_projection(
            _FakeReader(_progress(ars_state, last_seq=0, event_count=0), _FakePage((), None, False)),
            "/tmp/run",
            "artifact_local_0",
        )
        assert proj.supervisor_state == "waiting"


# --------------------------------------------------------------------------- #
# 9. Stale flag when progress frontier and observed page disagree
# --------------------------------------------------------------------------- #
def test_stale_when_progress_behind_events():
    m = _mod()
    # progress.last_seq=1 but the read page frontier is seq=3 → stale, still available
    reader = _FakeReader(
        _progress("running", last_seq=1, event_count=1),
        _FakePage((_rec(1), _rec(2), _rec(3)), next_cursor=3, has_more=True),
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0")
    assert proj.available is True
    assert proj.observed_last_seq == 3 and proj.progress_last_seq == 1
    assert proj.stale is True


def test_stale_when_summary_claims_events_the_stream_lacks():
    m = _mod()
    # progress claims last_seq=9 but the exhausted page (has_more False) only reached 2
    reader = _FakeReader(
        _progress("running", last_seq=9, event_count=9),
        _FakePage((_rec(1), _rec(2)), next_cursor=2, has_more=False),
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0")
    assert proj.available is True and proj.stale is True


def test_not_stale_when_frontiers_agree():
    m = _mod()
    reader = _FakeReader(
        _progress("running", last_seq=2, event_count=2),
        _FakePage((_rec(1), _rec(2)), next_cursor=2, has_more=False),
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0")
    assert proj.stale is False


# --------------------------------------------------------------------------- #
# 10. Forged / hostile objects fail closed
# --------------------------------------------------------------------------- #
def test_forged_projection_fails_closed():
    m = _mod()
    forged = object.__new__(m.LiveProgressProjection)
    with pytest.raises(SpineError):
        m.validate_live_progress_projection(forged)


def test_forged_record_fails_closed():
    m = _mod()
    forged = object.__new__(m.LiveProgressEventRecord)
    with pytest.raises(SpineError):
        m.validate_live_progress_event_record(forged)


def test_hostile_subclass_fails_closed():
    m = _mod()

    class _Evil(m.LiveProgressProjection):
        def __post_init__(self):  # skip validation
            pass

    evil = _Evil(
        type=m.LIVE_PROGRESS_PROJECTION_TYPE,
        task_id=None,
        artifact_ref="artifact_local_0",
        available=True,
        supervisor_state="active",
        schema_version=1,
        progress_last_seq=0,
        progress_event_count=0,
        observed_last_seq=0,
        observed_event_count=0,
        resume_cursor=None,
        has_more=False,
        stale=False,
        records=(),
        error_code=None,
    )
    with pytest.raises(SpineError):
        m.validate_live_progress_projection(evil)


def test_projection_with_forged_record_fails_closed():
    m = _mod()
    forged_rec = object.__new__(m.LiveProgressEventRecord)
    with pytest.raises(SpineError):
        m.LiveProgressProjection(
            type=m.LIVE_PROGRESS_PROJECTION_TYPE,
            task_id=None,
            artifact_ref="artifact_local_0",
            available=True,
            supervisor_state="active",
            schema_version=1,
            progress_last_seq=1,
            progress_event_count=1,
            observed_last_seq=1,
            observed_event_count=1,
            resume_cursor=1,
            has_more=False,
            stale=False,
            records=(forged_rec,),
            error_code=None,
        )


# --------------------------------------------------------------------------- #
# 10b. Top-level counts / resume cursor are bounded on direct / forged objects.
# The builder bounds foreign reader values via ``_safe_count``, but a directly
# constructed or forged projection routes through the public dataclass validator
# and must enforce the SAME ``_MAX_COUNT`` (1e9) bound on ``schema_version`` /
# ``progress_event_count`` / ``resume_cursor`` — else an oversized count escapes
# the bounded-int projection contract and the forged-object validator invariant.
# --------------------------------------------------------------------------- #
def _valid_available_kwargs(m, **overrides):
    """A minimal valid ``available`` projection's fields; override one to probe."""
    base = dict(
        type=m.LIVE_PROGRESS_PROJECTION_TYPE,
        task_id=None,
        artifact_ref="artifact_local_0",
        available=True,
        supervisor_state="active",
        schema_version=1,
        progress_last_seq=0,
        progress_event_count=0,
        observed_last_seq=0,
        observed_event_count=0,
        resume_cursor=None,
        has_more=False,
        stale=False,
        records=(),
        error_code=None,
    )
    base.update(overrides)
    return base


def test_valid_baseline_constructs_so_the_bound_is_what_fails():
    # Guards the oversized-count tests below: the baseline itself is a valid
    # projection, so a raised SpineError there is caused by the mutated field.
    m = _mod()
    proj = m.LiveProgressProjection(**_valid_available_kwargs(m))
    assert proj.available is True and proj.schema_version == 1


def test_oversized_schema_version_fails_closed_on_construction():
    m = _mod()
    with pytest.raises(SpineError):
        m.LiveProgressProjection(**_valid_available_kwargs(m, schema_version=1_000_000_001))


def test_oversized_progress_event_count_fails_closed_on_construction():
    m = _mod()
    with pytest.raises(SpineError):
        m.LiveProgressProjection(
            **_valid_available_kwargs(m, progress_event_count=1_000_000_001)
        )


def test_forged_oversized_resume_cursor_revalidated_on_serialize():
    # A forged object skips ``__post_init__``; ``serialize_...`` must revalidate and
    # reject an oversized ``resume_cursor`` that would otherwise be byte-serialized.
    m = _mod()
    rec = m.LiveProgressEventRecord(
        seq=1, family="tool", kind="tool_call", observed_status="active", text_length=0
    )
    fields = _valid_available_kwargs(
        m,
        progress_last_seq=1,
        progress_event_count=1,
        observed_last_seq=1,
        observed_event_count=1,
        resume_cursor=1_000_000_001,  # over _MAX_COUNT; would be valid at 1
        records=(rec,),
    )
    forged = object.__new__(m.LiveProgressProjection)
    for name, value in fields.items():
        object.__setattr__(forged, name, value)
    with pytest.raises(SpineError):
        m.serialize_live_progress_projection(forged)


# --------------------------------------------------------------------------- #
# 11. Serialization is byte-stable and revalidates; no TaskEventLog coupling
# --------------------------------------------------------------------------- #
def test_serialization_byte_stable_and_revalidates():
    m = _mod()
    reader = _FakeReader(
        _progress("running", last_seq=2, event_count=2),
        _FakePage((_rec(1), _rec(2, status="completed")), next_cursor=2, has_more=False),
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0")
    first = m.serialize_live_progress_projection(proj)
    second = m.serialize_live_progress_projection(proj)
    assert first == second
    # revalidation returns the same object unchanged
    assert m.validate_live_progress_projection(proj) is proj


def test_build_appends_nothing_to_task_event_log():
    m = _mod()
    log = TaskEventLog()
    reader = _FakeReader(
        _progress("running", last_seq=1, event_count=1),
        _FakePage((_rec(1),), next_cursor=1, has_more=False),
    )
    proj = m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0", task_id="task_alpha")
    # The ARS cursor is a foreign read-model cursor: it never enters the canonical log.
    assert log.has_task("task_alpha") is False
    assert log.last_seq("task_alpha") == 0
    assert proj.resume_cursor == 1


# --------------------------------------------------------------------------- #
# Caller-input contract — unsafe artifact_ref / cursor rejected (never stored)
# --------------------------------------------------------------------------- #
def test_unsafe_artifact_ref_raises():
    m = _mod()
    reader = _FakeReader(_progress(), _FakePage((), None, False))
    with pytest.raises(SpineError):
        m.build_live_progress_projection(reader, "/tmp/run", "/home/user/secret")


def test_negative_after_seq_raises():
    m = _mod()
    reader = _FakeReader(_progress(), _FakePage((), None, False))
    with pytest.raises(SpineError):
        m.build_live_progress_projection(reader, "/tmp/run", "artifact_local_0", after_seq=-1)


# --------------------------------------------------------------------------- #
# 12. Package exports available from sachima_supervisor.runtime_spine
# --------------------------------------------------------------------------- #
def test_package_exports_available():
    import sachima_supervisor.runtime_spine as spine

    for name in (
        "RUNTIME_INVALID_LIVE_PROGRESS",
        "LIVE_PROGRESS_UNAVAILABLE",
        "LIVE_PROGRESS_CORRUPT",
        "LIVE_PROGRESS_STABLE_CODES",
        "LIVE_PROGRESS_PROJECTION_TYPE",
        "SUPERVISOR_OBSERVED_STATES",
        "OBSERVED_EVENT_STATUSES",
        "LiveProgressReader",
        "DefaultLiveProgressReader",
        "LiveProgressEventRecord",
        "LiveProgressProjection",
        "build_live_progress_projection",
        "validate_live_progress_projection",
        "validate_live_progress_event_record",
        "serialize_live_progress_projection",
    ):
        assert hasattr(spine, name), name
    assert spine.LIVE_PROGRESS_STABLE_CODES == frozenset(
        {"runtime_invalid_live_progress", "live_progress_unavailable", "live_progress_corrupt"}
    )


# --------------------------------------------------------------------------- #
# 13. Static source: no top-level agent_run_supervisor import, no exec tokens
# --------------------------------------------------------------------------- #
def test_no_top_level_ars_import_and_no_execution_tokens():
    m = _mod()
    src = open(m.__file__, encoding="utf-8").read()
    # No top-level (or any) direct import of the ARS library — lazy string only.
    assert re.search(r"(?m)^\s*(import|from)\s+agent_run_supervisor", src) is None
    # The ARS caller module is reached only lazily, as an importlib string literal.
    assert "agent_run_supervisor.hermes_caller.events" in src
    # No real runtime / process / agent-launch primitives in the new behavior.
    lowered = src.lower()
    for token in ("subprocess", "acpx", "npx", "os.system", ".popen(", "socket.socket"):
        assert token not in lowered, token
