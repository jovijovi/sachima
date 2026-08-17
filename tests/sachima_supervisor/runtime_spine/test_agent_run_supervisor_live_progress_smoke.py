"""Artifact-shape live-progress smoke tests (local/offline).

These tests exercise the *local/offline* smoke seam
(``agent_run_supervisor_live_progress_smoke``), which reads **synthetic**
artifacts through the real default reader and maps them into Sachima's
already-validated refs-only read-models (``LiveProgressProjection`` / the
combined live workbench view) plus a small stable smoke report. Nothing here
launches a real AGENT or child process, opens a socket, starts a runtime /
Temporal service, or touches a Gateway / Feishu / IM / delivery surface — the
smoke only ever reads two files from a temp dir.

The **caller-API compatibility** framing is retired (ARS 0.7.6 plan §11, seams
S-5/S-14). The producer's caller/read API was removed upstream at 0.7.x and the
default reader became Sachima's own stdlib JSON/JSONL reader over the same
artifact shapes, so there is no external API left to be compatible *with* — and
no distribution left to gate on. The eight formerly ``@_requires_real_api``
tests are re-anchored on that reader and now **run** instead of skipping
forever: what they always really locked is the artifact-shape contract
(available projection + combined view, ``has_more`` / ``next_cursor`` /
``after_seq`` cursor alignment, nullable ``kind`` / ``status`` / ``text_length``
normalization, legacy no-``seq`` 1-based line-cursor fallback, and corrupt
fail-closed), and that contract still matters.

Two families of test:

* **Safety / absent-artifact tests** — driven with in-test fake readers or an
  absent artifact dir, they prove the smoke fails closed to a stable
  ``live_progress_unavailable`` / ``live_progress_corrupt`` report / projection
  with no raw error text, path, or ``summary`` free text in any serialized
  surface, and that forged report objects fail closed.
* **Artifact-shape tests** — they write synthetic ``progress.json`` +
  ``normalized-events.jsonl`` to a temp dir and read them through the real
  default reader.

Synthetic-artifact schema note (the single format assumption): the real caller
API is outside this worktree's read sandbox, so the on-disk shapes below are built
from the Hermes-provided PR #38 field contract — ``progress.json`` carries
``schema_version`` / ``state`` / ``last_seq`` / ``event_count`` / ``updated_at``;
each ``normalized-events.jsonl`` line carries the ``EventRecord`` fields
(``seq`` / ``family`` / ``kind`` / ``status`` / ``text_length`` / ``summary``).
Because the event-type token's on-disk key is the one genuinely ambiguous field
(the producer names it the event ``type``), each synthetic event line carries the
type token under BOTH ``family`` and ``type`` so it parses whichever key the real
API reads. If a real-API run ever shows a schema mismatch, the fix is localized to
``_event`` / ``_write_progress`` here. Forbidden terms in this prose are no-leak /
forbidden-surface canaries only, never behavior.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

from sachima_supervisor.runtime_spine import (
    LIVE_PROGRESS_CORRUPT,
    LIVE_PROGRESS_UNAVAILABLE,
    DefaultLiveProgressReader,
    SpineError,
    TaskRegistry,
    build_launch_spec,
    scan_for_leak,
    serialize_agent_run_supervisor_live_workbench_view,
    serialize_live_progress_projection,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    AgentRunSupervisorPort,
    DefaultAgentRunSupervisorBackend,
)

_SMOKE = "sachima_supervisor.runtime_spine.agent_run_supervisor_live_progress_smoke"
_PROJECTION = "sachima_supervisor.runtime_spine.live_progress_projection"


def _mod():
    return importlib.import_module(_SMOKE)


# --------------------------------------------------------------------------- #
# The producer caller-API gate is retired with the seam it guarded (S-5/S-14).
# ``test_real_caller_api_importable_when_distribution_installed`` went first
# (plan P1-k): it asserted "distribution installed => the caller module must
# import", a premise 0.7.x killed. The ``@_requires_real_api`` skip mark it
# shared went with the rest of the seam here — a gate on a module that can
# never exist again is a test that can never run again.


# --------------------------------------------------------------------------- #
# Synthetic artifact writers (the smoke module is read-only; the test owns writes)
# --------------------------------------------------------------------------- #
_OMIT = object()


def _write_progress(
    artifact_dir: Path,
    *,
    schema_version=1,
    state="running",
    last_seq=3,
    event_count=3,
    updated_at="2026-07-06T00:00:00Z",
):
    payload = {
        "schema_version": schema_version,
        "state": state,
        "last_seq": last_seq,
        "event_count": event_count,
        "updated_at": updated_at,
    }
    (artifact_dir / "progress.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_progress_raw(artifact_dir: Path, payload: dict):
    (artifact_dir / "progress.json").write_text(json.dumps(payload), encoding="utf-8")


def _event(*, seq=_OMIT, event_family="tool", kind=_OMIT, status=_OMIT, text_length=_OMIT, summary="ok"):
    rec: dict = {}
    if seq is not _OMIT:
        rec["seq"] = seq
    if event_family is not _OMIT:
        # Carry the event-type token under both keys — see the module docstring.
        rec["family"] = event_family
        rec["type"] = event_family
    if kind is not _OMIT:
        rec["kind"] = kind
    if status is not _OMIT:
        rec["status"] = status
    if text_length is not _OMIT:
        rec["text_length"] = text_length
    if summary is not _OMIT:
        rec["summary"] = summary
    return rec


def _write_events(artifact_dir: Path, events):
    body = "".join(json.dumps(e) + "\n" for e in events)
    (artifact_dir / "normalized-events.jsonl").write_text(body, encoding="utf-8")


# --------------------------------------------------------------------------- #
# In-test fakes modeling the ARS caller shapes (for safety tests, no real lib)
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


def _progress(state="running", *, schema_version=1, last_seq=3, event_count=3):
    return _FakeProgress(
        schema_version=schema_version, state=state, last_seq=last_seq, event_count=event_count
    )


def _rec(seq, *, family="tool", kind="tool_call", status="running", text_length=0, **extra):
    return _FakeRec(seq=seq, family=family, kind=kind, status=status, text_length=text_length, **extra)


# --------------------------------------------------------------------------- #
# Workbench-side fixtures (mirror test_agent_run_supervisor_live_workbench.py)
# --------------------------------------------------------------------------- #
def _spec(task_id="task_alpha"):
    return build_launch_spec(
        task_id=task_id,
        agent_kind="local_agent",
        mode_flags={"needs_agent": True},
        roles=("read_only",),
        refs=("ws_alpha", "policy_default"),
    )


def _running_port():
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    return reg, port, ref


# --------------------------------------------------------------------------- #
# A. Public surface is exported (module + package)
# --------------------------------------------------------------------------- #
def test_smoke_public_surface_is_exported():
    m = _mod()
    assert m.RUNTIME_INVALID_LIVE_PROGRESS_SMOKE == "runtime_invalid_live_progress_smoke"
    assert m.RUNTIME_INVALID_LIVE_PROGRESS_SMOKE in m.LIVE_PROGRESS_SMOKE_STABLE_CODES
    assert (
        m.LIVE_PROGRESS_SMOKE_REPORT_TYPE
        == "sachima.runtime_spine.agent_run_supervisor_live_progress_smoke_report.v1"
    )
    assert m.SMOKE_OUTCOMES == frozenset({"available", "unavailable", "corrupt"})
    for name in (
        "LiveProgressSmokeReport",
        "smoke_live_progress_projection",
        "smoke_live_workbench_view",
        "smoke_live_progress_report",
        "build_live_progress_smoke_report",
        "validate_live_progress_smoke_report",
        "serialize_live_progress_smoke_report",
    ):
        assert hasattr(m, name), name


def test_smoke_symbols_available_from_runtime_spine_package():
    spine = importlib.import_module("sachima_supervisor.runtime_spine")
    for name in (
        "RUNTIME_INVALID_LIVE_PROGRESS_SMOKE",
        "LIVE_PROGRESS_SMOKE_STABLE_CODES",
        "LIVE_PROGRESS_SMOKE_REPORT_TYPE",
        "SMOKE_OUTCOMES",
        "LiveProgressSmokeReport",
        "smoke_live_progress_projection",
        "smoke_live_workbench_view",
        "smoke_live_progress_report",
        "build_live_progress_smoke_report",
        "validate_live_progress_smoke_report",
        "serialize_live_progress_smoke_report",
    ):
        assert hasattr(spine, name), name


# --------------------------------------------------------------------------- #
# B. Unreadable artifact → unavailable projection / blocked report, no raw path
# --------------------------------------------------------------------------- #
def _absent_artifact_dir(tmp_path):
    """A private path with no artifact in it, carrying a leak canary."""

    return str(tmp_path / "secret" / "run_absent")


def test_absent_artifact_projection_is_unavailable(tmp_path):
    m = _mod()
    # reader=None → the smoke wires the real DefaultLiveProgressReader, which
    # fails closed because there is no artifact to read.
    artifact_dir = _absent_artifact_dir(tmp_path)
    proj = m.smoke_live_progress_projection(artifact_dir, "artifact_local_0")
    assert proj.available is False
    assert proj.error_code == LIVE_PROGRESS_UNAVAILABLE
    assert proj.records == ()
    assert scan_for_leak(proj.as_dict()) is None
    # The private path handed to the reader never reaches the safe surface.
    blob = serialize_live_progress_projection(proj)
    assert b"secret" not in blob
    assert artifact_dir.encode("utf-8") not in blob


def test_absent_artifact_report_is_blocked_unavailable(tmp_path):
    m = _mod()
    artifact_dir = _absent_artifact_dir(tmp_path)
    report = m.smoke_live_progress_report(artifact_dir, "artifact_local_0", task_id="task_alpha")
    assert report.outcome == "unavailable"
    assert report.available is False
    assert report.error_code == LIVE_PROGRESS_UNAVAILABLE
    assert report.task_id == "task_alpha"
    assert report.artifact_ref == "artifact_local_0"
    assert report.observed_event_count == 0
    assert report.resume_cursor is None and report.has_more is False and report.stale is False
    assert scan_for_leak(report.as_dict()) is None
    # The private artifact path never surfaces, in any form.
    blob = m.serialize_live_progress_smoke_report(report)
    for marker in (b"secret", b"/home/", b"/tmp/", artifact_dir.encode("utf-8")):
        assert marker not in blob


def test_smoke_module_default_reader_is_the_real_reader():
    m = _mod()
    # With no injected reader the smoke must use the real DefaultLiveProgressReader
    # — never a fake — so the artifact-shape tests exercise the real thing.
    proj = m.smoke_live_progress_projection("/tmp/does/not/matter", "artifact_local_0")
    # A nonexistent dir carries no progress: a clean unavailable/corrupt
    # projection, never a raise.
    assert proj.available is False
    assert proj.error_code in (LIVE_PROGRESS_UNAVAILABLE, LIVE_PROGRESS_CORRUPT)


# --------------------------------------------------------------------------- #
# C. Corrupt reader (ValueError w/ a path) → corrupt report, no raw leak
# --------------------------------------------------------------------------- #
def test_corrupt_reader_report_is_corrupt_without_leak(tmp_path):
    m = _mod()

    class _Boom:
        def load_progress(self, d):
            raise ValueError("bad int at /home/user/run/progress.json")

        def read_event_page(self, d, **k):
            raise AssertionError("not reached")

    report = m.smoke_live_progress_report(str(tmp_path), "artifact_local_0", reader=_Boom())
    assert report.outcome == "corrupt"
    assert report.available is False
    assert report.error_code == LIVE_PROGRESS_CORRUPT
    assert scan_for_leak(report.as_dict()) is None
    blob = m.serialize_live_progress_smoke_report(report)
    for marker in (b"/home/", b"progress.json", b"bad int"):
        assert marker not in blob


# --------------------------------------------------------------------------- #
# D. No-leak bytes scan across all three surfaces (projection / workbench / report)
# --------------------------------------------------------------------------- #
def test_no_leak_bytes_across_projection_workbench_and_report(tmp_path):
    m = _mod()
    reg, port, ref = _running_port()
    reader = _FakeReader(
        _progress("running", last_seq=1, event_count=1),
        _FakePage(
            (
                _rec(
                    1,
                    family="turn",
                    kind="assistant",
                    status="running",
                    text_length=9,
                    summary="visit /home/user/secret oc_platform_id chat_id",
                    text="RAW_TEXT_THAT_MUST_NOT_LEAK",
                    content="RAW_CONTENT_THAT_MUST_NOT_LEAK",
                    message="RAW_MESSAGE_THAT_MUST_NOT_LEAK",
                    body="RAW_BODY_THAT_MUST_NOT_LEAK",
                    stdout="RAW_STDOUT_THAT_MUST_NOT_LEAK",
                    stderr="RAW_STDERR_THAT_MUST_NOT_LEAK",
                    prompt="RAW_PROMPT_THAT_MUST_NOT_LEAK",
                    tool_output="RAW_TOOL_OUTPUT_THAT_MUST_NOT_LEAK",
                    **{
                        "to" + "ken": "RAW_" + "TOKEN_THAT_MUST_NOT_LEAK",
                        "sec" + "ret": "RAW_" + "SECRET_THAT_MUST_NOT_LEAK",
                    },
                ),
            ),
            next_cursor=1,
            has_more=False,
        ),
    )
    proj = m.smoke_live_progress_projection(
        str(tmp_path / "private" / "run"), "artifact_local_0", reader=reader, task_id="task_alpha"
    )
    view = m.smoke_live_workbench_view(
        reg, port, ref, str(tmp_path / "private" / "run"), "artifact_local_0", reader=reader
    )
    report = m.build_live_progress_smoke_report(proj)

    assert proj.available is True and view.progress_available is True and report.outcome == "available"
    surfaces = (
        serialize_live_progress_projection(proj),
        serialize_agent_run_supervisor_live_workbench_view(view),
        m.serialize_live_progress_smoke_report(report),
    )
    for blob in surfaces:
        for marker in (
            b"/home/",
            b"/tmp/",
            b"secret",
            b"summary",
            b"content",
            b"message",
            b'"text"',
            b"chat_id",
            b"oc_",
            b"ou_",
            b"platform_id",
        ):
            assert marker not in blob, marker
    for data in (proj.as_dict(), view.as_dict(), report.as_dict()):
        assert scan_for_leak(data) is None


# --------------------------------------------------------------------------- #
# E. Report invariants + forgery / oversized fail-closed
# --------------------------------------------------------------------------- #
def _available_report(m, tmp_path):
    reader = _FakeReader(
        _progress("running", last_seq=2, event_count=2),
        _FakePage((_rec(1), _rec(2, status="completed")), next_cursor=2, has_more=True),
    )
    proj = m.smoke_live_progress_projection(str(tmp_path), "artifact_local_0", reader=reader)
    return m.build_live_progress_smoke_report(proj), proj


def test_available_report_mirrors_projection(tmp_path):
    m = _mod()
    report, proj = _available_report(m, tmp_path)
    assert report.outcome == "available"
    assert report.available is True and report.error_code is None
    assert report.observed_event_count == proj.observed_event_count == 2
    assert report.resume_cursor == proj.resume_cursor == 2
    assert report.has_more is True and report.stale == proj.stale
    # byte-stable + revalidation returns the same object
    assert m.serialize_live_progress_smoke_report(report) == m.serialize_live_progress_smoke_report(report)
    assert m.validate_live_progress_smoke_report(report) is report


def test_forged_report_fails_closed(tmp_path):
    m = _mod()
    forged = object.__new__(m.LiveProgressSmokeReport)
    with pytest.raises(SpineError):
        m.validate_live_progress_smoke_report(forged)


def test_report_available_outcome_must_agree_with_flag():
    m = _mod()
    # available True but a non-None error_code is contradictory → fail closed.
    with pytest.raises(SpineError):
        m.LiveProgressSmokeReport(
            type=m.LIVE_PROGRESS_SMOKE_REPORT_TYPE,
            outcome="available",
            available=True,
            error_code=LIVE_PROGRESS_CORRUPT,
            artifact_ref="artifact_local_0",
            task_id=None,
            observed_event_count=0,
            resume_cursor=None,
            has_more=False,
            stale=False,
        )


def test_report_unavailable_outcome_requires_clean_fields():
    m = _mod()
    # unavailable but carrying observed events / a cursor is contradictory.
    with pytest.raises(SpineError):
        m.LiveProgressSmokeReport(
            type=m.LIVE_PROGRESS_SMOKE_REPORT_TYPE,
            outcome="unavailable",
            available=False,
            error_code=LIVE_PROGRESS_UNAVAILABLE,
            artifact_ref="artifact_local_0",
            task_id=None,
            observed_event_count=3,
            resume_cursor=3,
            has_more=True,
            stale=False,
        )


def test_report_rejects_unsafe_artifact_ref(tmp_path):
    m = _mod()
    reader = _FakeReader(_progress(), _FakePage((), None, False))
    with pytest.raises(SpineError):
        m.smoke_live_progress_report(str(tmp_path), "/home/user/secret", reader=reader)


def test_report_oversized_count_fails_closed():
    m = _mod()
    with pytest.raises(SpineError):
        m.LiveProgressSmokeReport(
            type=m.LIVE_PROGRESS_SMOKE_REPORT_TYPE,
            outcome="available",
            available=True,
            error_code=None,
            artifact_ref="artifact_local_0",
            task_id=None,
            observed_event_count=1_000_000_001,
            resume_cursor=None,
            has_more=False,
            stale=False,
        )


# --------------------------------------------------------------------------- #
# F. Static boundary scan — no real runtime / delivery / ARS-import wiring
# --------------------------------------------------------------------------- #
def test_smoke_source_wires_no_real_runtime_or_delivery():
    m = _mod()
    src = Path(m.__file__).read_text(encoding="utf-8")
    lowered = src.lower()
    for token in (
        "subprocess",
        "acpx",
        " npx",
        "os.system",
        ".popen(",
        "socket.socket",
        "create_subprocess",
    ):
        assert token not in lowered, token
    # No top-level (or any) direct import of the ARS producer library — it is
    # reached only lazily inside DefaultLiveProgressReader.
    assert re.search(r"(?m)^\s*(import|from)\s+agent_run_supervisor", src) is None
    import_lines = [ln for ln in src.splitlines() if ln.startswith(("import ", "from "))]
    for line in import_lines:
        for root in ("subprocess", "socket", "temporal", "gateway", "feishu", "lark", "httpx", "requests", "asyncio"):
            assert root not in line, f"forbidden import {root!r}: {line!r}"


# --------------------------------------------------------------------------- #
# G. Artifact-shape smoke over the real default reader (always runs)
# --------------------------------------------------------------------------- #
def test_stdlib_reader_happy_path_projection_available(tmp_path):
    m = _mod()
    _write_progress(tmp_path, state="running", last_seq=3, event_count=3)
    _write_events(
        tmp_path,
        [
            _event(seq=1, event_family="run_started", kind="lifecycle", status="running", text_length=0),
            _event(seq=2, event_family="tool_started", kind="read", status="running", text_length=42),
            _event(seq=3, event_family="agent_message", kind="assistant", status="running", text_length=120),
        ],
    )
    proj = m.smoke_live_progress_projection(str(tmp_path), "artifact_local_0")
    assert proj.available is True and proj.error_code is None
    assert proj.supervisor_state == "active"
    assert [r.seq for r in proj.records] == [1, 2, 3]
    assert proj.observed_event_count == 3 and proj.observed_last_seq == 3
    assert proj.has_more is False
    assert all(not hasattr(r, "summary") for r in proj.records)
    assert scan_for_leak(proj.as_dict()) is None


def test_stdlib_reader_cursor_alignment(tmp_path):
    m = _mod()
    _write_progress(tmp_path, last_seq=5, event_count=5)
    _write_events(tmp_path, [_event(seq=i, event_family="tool", kind="call", status="running", text_length=i) for i in range(1, 6)])

    page1 = m.smoke_live_progress_projection(str(tmp_path), "artifact_local_0", limit=2)
    assert [r.seq for r in page1.records] == [1, 2]
    assert page1.resume_cursor == 2 and page1.has_more is True

    page2 = m.smoke_live_progress_projection(str(tmp_path), "artifact_local_0", after_seq=2, limit=2)
    assert [r.seq for r in page2.records] == [3, 4]
    assert all(s > 2 for s in [r.seq for r in page2.records])
    assert page2.resume_cursor == 4 and page2.has_more is True


def test_stdlib_reader_nullable_fields_normalize(tmp_path):
    m = _mod()
    _write_progress(tmp_path, last_seq=2, event_count=2)
    _write_events(
        tmp_path,
        [
            # kind / status / text_length omitted entirely (nullable producer fields)
            _event(seq=1, event_family="run_started"),
            _event(seq=2, event_family="agent_message_delta", text_length=128),
        ],
    )
    proj = m.smoke_live_progress_projection(str(tmp_path), "artifact_local_0")
    assert proj.available is True and proj.error_code is None
    by_seq = {r.seq: r for r in proj.records}
    assert by_seq[1].kind == "unknown"  # None → closed safe token
    assert by_seq[1].observed_status == "unknown"  # None → unknown
    assert by_seq[1].text_length == 0  # None → 0
    assert by_seq[2].text_length == 128  # present value preserved
    blob = serialize_live_progress_projection(proj)
    assert b"None" not in blob and b"summary" not in blob


def test_stdlib_reader_legacy_no_seq_line_cursor_fallback(tmp_path):
    m = _mod()
    _write_progress(tmp_path, last_seq=3, event_count=3)
    # No ``seq`` field → the caller API falls back to a 1-based line cursor.
    _write_events(
        tmp_path,
        [
            _event(event_family="run_started", kind="lifecycle", status="running", text_length=0),
            _event(event_family="tool", kind="call", status="running", text_length=5),
            _event(event_family="agent_message", kind="assistant", status="running", text_length=9),
        ],
    )
    proj = m.smoke_live_progress_projection(str(tmp_path), "artifact_local_0")
    assert proj.available is True and proj.error_code is None
    assert [r.seq for r in proj.records] == [1, 2, 3]

    # Resume by the derived line cursor: after_seq=1 yields only higher positions.
    resumed = m.smoke_live_progress_projection(str(tmp_path), "artifact_local_0", after_seq=1)
    assert [r.seq for r in resumed.records] == [2, 3]
    assert all(s > 1 for s in [r.seq for r in resumed.records])


def test_stdlib_reader_corrupt_progress_fails_closed(tmp_path):
    m = _mod()
    # A non-integer where the caller API expects an int → ValueError on load.
    _write_progress_raw(
        tmp_path,
        {
            "schema_version": 1,
            "state": "running",
            "last_seq": "not-an-int",
            "event_count": 3,
            "updated_at": "2026-07-06T00:00:00Z",
        },
    )
    _write_events(tmp_path, [_event(seq=1, event_family="tool", kind="call", status="running", text_length=0)])
    report = m.smoke_live_progress_report(str(tmp_path), "artifact_local_0")
    assert report.outcome == "corrupt"
    assert report.error_code == LIVE_PROGRESS_CORRUPT
    assert scan_for_leak(report.as_dict()) is None
    assert b"not-an-int" not in m.serialize_live_progress_smoke_report(report)


def test_stdlib_reader_corrupt_event_fails_closed(tmp_path):
    m = _mod()
    _write_progress(tmp_path, last_seq=2, event_count=2)
    # Second event carries a present-but-invalid text_length (negative): the caller
    # API surfaces the well-formed line (so it is not silently skipped), and
    # Sachima's refs-only allowlist rejects the negative count — or the API raises
    # on it. Either path fails the page closed as corrupt.
    _write_events(
        tmp_path,
        [
            _event(seq=1, event_family="tool", kind="call", status="running", text_length=0),
            _event(seq=2, event_family="tool", kind="call", status="running", text_length=-5),
        ],
    )
    proj = m.smoke_live_progress_projection(str(tmp_path), "artifact_local_0")
    assert proj.available is False
    assert proj.error_code == LIVE_PROGRESS_CORRUPT
    assert proj.records == ()


def test_stdlib_reader_combined_workbench_view_available(tmp_path):
    m = _mod()
    reg, port, ref = _running_port()
    _write_progress(tmp_path, last_seq=2, event_count=2)
    _write_events(
        tmp_path,
        [
            _event(seq=1, event_family="run_started", kind="lifecycle", status="running", text_length=0),
            _event(seq=2, event_family="tool", kind="call", status="running", text_length=7),
        ],
    )
    view = m.smoke_live_workbench_view(reg, port, ref, str(tmp_path), "artifact_local_0")
    data = view.as_dict()
    assert data["task_id"] == "task_alpha"
    assert data["workbench"]["status"] == "running"
    assert data["progress_available"] is True
    assert data["live_progress"]["available"] is True
    assert data["live_progress"]["task_id"] == "task_alpha"
    assert [r["seq"] for r in data["live_progress"]["records"]] == [1, 2]
    assert scan_for_leak(data) is None


def test_stdlib_reader_report_available_over_synthetic_dir(tmp_path):
    m = _mod()
    _write_progress(tmp_path, last_seq=1, event_count=1)
    _write_events(tmp_path, [_event(seq=1, event_family="tool", kind="call", status="running", text_length=0)])
    report = m.smoke_live_progress_report(str(tmp_path), "artifact_local_0", task_id="task_alpha")
    assert report.outcome == "available"
    assert report.available is True and report.error_code is None
    assert report.observed_event_count == 1
    assert scan_for_leak(report.as_dict()) is None
