"""PR-LS1 — ARS live-progress + task workbench composite view acceptance tests.

Focused RED/GREEN tests for the PR-LS1 slice that composes the PR4
``AgentRunSupervisorWorkbenchView`` (Status Projection + persistent lifecycle for
one locally tracked supervised session) with the PR3 ``LiveProgressProjection``
(a refs-only, fail-closed read-model of an agent-run-supervisor artifact's live
progress) into a single combined workbench surface. Everything here stays pure
local/offline Python over the deterministic in-memory backend + in-test fake
progress readers: no real AGENT / process / network / durable service / listener
is started, and no Gateway / Temporal Worker is touched. Building or serializing
the combined view is read-only — it appends no event, launches no work, and calls
no backend / IM / delivery surface.

The PR-LS1 semantics proven here, refs-only and fail-closed:

* **Composition** — a combined view carries the safe workbench dict, the safe live
  progress dict, and top-level mirror fields (task/session identity,
  ``progress_available`` / ``progress_error_code`` / ``resume_cursor`` /
  ``has_more`` / ``stale``); the live projection's ``task_id`` matches the
  workbench ``task_id``.
* **Resume** — an ``after_seq`` is forwarded to the injected reader and the
  top-level ``resume_cursor`` / ``has_more`` mirror the live projection.
* **Degraded live progress** — missing / corrupt / stale live progress composes
  over a still-valid workbench as unavailable / corrupt / stale (observation
  only), never faking success and never blocking the workbench.
* **Fail closed** — a task/session mismatch, a projection ``task_id`` mismatch, or
  a forged combined / nested workbench / nested live-progress object fails closed
  with the stable ``runtime_invalid_live_workbench_view`` code and never echoes
  bad material; serialized bytes carry no path / platform / raw-text canaries.

Forbidden terms below are no-leak canaries only, never behavior.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from sachima_supervisor.runtime_spine import (
    LaunchSpec,
    SessionRef,
    SpineError,
    TaskRegistry,
    build_launch_spec,
    scan_for_leak,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    AgentRunSupervisorPort,
    DefaultAgentRunSupervisorBackend,
)
from sachima_supervisor.runtime_spine.execution_port import RUNTIME_INVALID_SESSION

_SAFE_REFS = ("ws_alpha", "policy_default")


def _mod():
    return importlib.import_module(
        "sachima_supervisor.runtime_spine.agent_run_supervisor_live_workbench"
    )


# --------------------------------------------------------------------------- #
# Workbench-side fixtures (mirrors test_agent_run_supervisor_workbench_view.py)
# --------------------------------------------------------------------------- #
def _spec(
    task_id: str = "task_alpha",
    *,
    roles: tuple[str, ...] = ("read_only",),
    refs: tuple[str, ...] = _SAFE_REFS,
    needs_agent: bool = True,
    needs_durable: bool = False,
    agent_kind: str = "local_agent",
) -> LaunchSpec:
    mode_flags = {"needs_agent": needs_agent}
    if needs_durable:
        mode_flags["needs_durable"] = True
    return build_launch_spec(
        task_id=task_id,
        agent_kind=agent_kind,
        mode_flags=mode_flags,
        roles=roles,
        refs=refs,
    )


def _running_port():
    reg = TaskRegistry()
    backend = DefaultAgentRunSupervisorBackend()
    port = AgentRunSupervisorPort(reg, backend)
    ref = port.create_or_attach("task_alpha", _spec())
    return reg, backend, port, ref


# --------------------------------------------------------------------------- #
# Live-progress-side fakes (mirrors test_live_progress_projection.py)
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
        schema_version=schema_version, state=state, last_seq=last_seq, event_count=event_count
    )


def _rec(seq, *, family="tool", kind="tool_call", status="running", text_length=0, **extra):
    return _FakeRec(seq=seq, family=family, kind=kind, status=status, text_length=text_length, **extra)


def _running_reader():
    return _FakeReader(
        _progress("running", last_seq=3, event_count=3),
        _FakePage(
            (
                _rec(1, family="lifecycle", kind="agent_started", status="running", text_length=0),
                _rec(2, family="tool", kind="tool_call", status="running", text_length=42),
                _rec(3, family="step", kind="progress", status="running", text_length=7),
            ),
            next_cursor=3,
            has_more=False,
        ),
    )


def _build(mod, reg, port, ref, reader, *, artifact_dir="/tmp/run/abc", artifact_ref="artifact_local_0", **kw):
    return mod.build_agent_run_supervisor_live_workbench_view(
        reg, port, ref, reader, artifact_dir, artifact_ref, **kw
    )


def _compose_kwargs(mod, workbench, live_progress, **over):
    base = dict(
        type=mod.LIVE_WORKBENCH_VIEW_TYPE,
        task_id=workbench["task_id"],
        session_id=workbench["session_id"],
        workbench=workbench,
        live_progress=live_progress,
        progress_available=live_progress["available"],
        progress_error_code=live_progress["error_code"],
        resume_cursor=live_progress["resume_cursor"],
        has_more=live_progress["has_more"],
        stale=live_progress["stale"],
    )
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# A. Public surface
# --------------------------------------------------------------------------- #
def test_live_workbench_public_surface_is_exported():
    mod = _mod()
    assert mod.RUNTIME_INVALID_LIVE_WORKBENCH_VIEW == "runtime_invalid_live_workbench_view"
    assert mod.RUNTIME_INVALID_LIVE_WORKBENCH_VIEW in mod.LIVE_WORKBENCH_STABLE_CODES
    assert (
        mod.LIVE_WORKBENCH_VIEW_TYPE
        == "sachima.runtime_spine.agent_run_supervisor_live_workbench_view.v1"
    )
    for name in (
        "AgentRunSupervisorLiveWorkbenchView",
        "build_agent_run_supervisor_live_workbench_view",
        "validate_agent_run_supervisor_live_workbench_view",
        "serialize_agent_run_supervisor_live_workbench_view",
    ):
        assert hasattr(mod, name)


def test_live_workbench_symbols_available_from_runtime_spine_package():
    spine = importlib.import_module("sachima_supervisor.runtime_spine")
    for name in (
        "RUNTIME_INVALID_LIVE_WORKBENCH_VIEW",
        "LIVE_WORKBENCH_STABLE_CODES",
        "LIVE_WORKBENCH_VIEW_TYPE",
        "AgentRunSupervisorLiveWorkbenchView",
        "build_agent_run_supervisor_live_workbench_view",
        "validate_agent_run_supervisor_live_workbench_view",
        "serialize_agent_run_supervisor_live_workbench_view",
    ):
        assert hasattr(spine, name), name


# --------------------------------------------------------------------------- #
# B. Happy path — combines workbench + live progress; top-level fields mirror both
# --------------------------------------------------------------------------- #
def test_composes_workbench_and_live_progress_refs_only():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    view = _build(mod, reg, port, ref, _running_reader())
    assert type(view) is mod.AgentRunSupervisorLiveWorkbenchView

    data = view.as_dict()
    assert data["type"] == mod.LIVE_WORKBENCH_VIEW_TYPE
    assert data["task_id"] == "task_alpha"
    assert data["session_id"] == ref.session_id

    # nested workbench dict mirrors the standalone workbench view
    wb = data["workbench"]
    assert wb["type"] == "sachima.runtime_spine.agent_run_supervisor_workbench_view.v1"
    assert wb["task_id"] == "task_alpha"
    assert wb["session_id"] == ref.session_id
    assert wb["status"] == "running"

    # nested live progress dict + task_id association matches the workbench
    lp = data["live_progress"]
    assert lp["type"] == "sachima.runtime_spine.live_progress_projection.v1"
    assert lp["task_id"] == "task_alpha"
    assert lp["artifact_ref"] == "artifact_local_0"
    assert lp["available"] is True

    # top-level mirrors of the live projection
    assert data["progress_available"] is True
    assert data["progress_error_code"] is None
    assert data["resume_cursor"] == lp["resume_cursor"] == 3
    assert data["has_more"] is False
    assert data["stale"] is False
    assert scan_for_leak(data) is None


def test_live_progress_task_id_is_forced_to_workbench_task_id():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    # The builder passes the workbench task_id into the projection; the caller
    # never supplies a projection task_id directly, so the two always agree.
    view = _build(mod, reg, port, ref, _running_reader())
    data = view.as_dict()
    assert data["live_progress"]["task_id"] == data["workbench"]["task_id"] == data["task_id"]


# --------------------------------------------------------------------------- #
# C. after_seq resume is forwarded; top-level resume_cursor / has_more mirror
# --------------------------------------------------------------------------- #
def test_after_seq_forwarded_and_resume_fields_mirror_live_progress():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    page2 = _FakePage(
        (
            _rec(3, family="message", kind="assistant", status="running"),
            _rec(5, family="message", kind="assistant", status="running"),
        ),
        next_cursor=5,
        has_more=True,
    )
    reader = _CursorAwareReader(_progress(last_seq=5, event_count=5), {2: page2})

    view = _build(mod, reg, port, ref, reader, after_seq=2)
    data = view.as_dict()
    assert [r["seq"] for r in data["live_progress"]["records"]] == [3, 5]
    assert data["resume_cursor"] == 5
    assert data["has_more"] is True
    assert data["progress_available"] is True
    assert scan_for_leak(data) is None


# --------------------------------------------------------------------------- #
# D. Missing progress composes over a valid workbench as unavailable (no fake ok)
# --------------------------------------------------------------------------- #
def test_missing_progress_composes_unavailable_over_valid_workbench():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    reader = _FakeReader(None, _FakePage((), None, False))

    view = _build(mod, reg, port, ref, reader)
    data = view.as_dict()
    # workbench is still fully valid and renderable
    assert data["workbench"]["status"] == "running"
    assert data["workbench"]["task_id"] == "task_alpha"
    # live progress degraded, not faked
    assert data["progress_available"] is False
    assert data["progress_error_code"] == "live_progress_unavailable"
    assert data["live_progress"]["available"] is False
    assert data["live_progress"]["task_id"] == "task_alpha"  # safe task carried
    assert data["live_progress"]["artifact_ref"] == "artifact_local_0"
    assert data["resume_cursor"] is None
    assert data["has_more"] is False
    assert data["stale"] is False
    assert scan_for_leak(data) is None


# --------------------------------------------------------------------------- #
# E. Corrupt reader/page composes as corrupt without raw exception / path text
# --------------------------------------------------------------------------- #
def test_corrupt_reader_composes_corrupt_without_leaking_paths():
    mod = _mod()
    reg, backend, port, ref = _running_port()

    class _Boom:
        def load_progress(self, d):
            raise ValueError("bad int at /home/user/run/progress.json")

        def read_event_page(self, d, **k):
            raise AssertionError("not reached")

    view = _build(mod, reg, port, ref, _Boom(), artifact_dir="/tmp/private/run")
    data = view.as_dict()
    assert data["progress_available"] is False
    assert data["progress_error_code"] == "live_progress_corrupt"
    assert data["workbench"]["status"] == "running"
    assert scan_for_leak(data) is None
    blob = mod.serialize_agent_run_supervisor_live_workbench_view(view)
    for marker in (b"/home/", b"/tmp/", b"secret", b"progress.json"):
        assert marker not in blob


# --------------------------------------------------------------------------- #
# F. Stale progress is observation only — sets stale, does not block workbench
# --------------------------------------------------------------------------- #
def test_stale_progress_is_observation_only():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    # progress.last_seq=1 but the read page frontier is seq=3 → stale, still available
    reader = _FakeReader(
        _progress("running", last_seq=1, event_count=1),
        _FakePage((_rec(1), _rec(2), _rec(3)), next_cursor=3, has_more=True),
    )
    view = _build(mod, reg, port, ref, reader)
    data = view.as_dict()
    assert data["stale"] is True
    assert data["progress_available"] is True
    # the workbench half is unaffected / not blocked by a stale live frontier
    assert data["workbench"]["status"] == "running"
    assert data["workbench"]["terminal"] is False
    assert scan_for_leak(data) is None


# --------------------------------------------------------------------------- #
# G. task/session mismatch fails closed (forged ref through the workbench half)
# --------------------------------------------------------------------------- #
def test_forged_session_ref_fails_closed():
    mod = _mod()
    reg, backend, port, _ref = _running_port()
    with pytest.raises(SpineError) as exc:
        _build(
            mod,
            reg,
            port,
            SessionRef(task_id="task_alpha", session_id="sess_forged"),
            _running_reader(),
        )
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_registry_port_mismatch_fails_closed():
    mod = _mod()
    _reg, _backend, port, ref = _running_port()
    other_registry = TaskRegistry()  # does not know task_alpha
    with pytest.raises(SpineError):
        _build(mod, other_registry, port, ref, _running_reader())


# --------------------------------------------------------------------------- #
# H. Forged combined / nested workbench / nested live-progress fail closed
# --------------------------------------------------------------------------- #
def _good_children(mod):
    reg, backend, port, ref = _running_port()
    view = _build(mod, reg, port, ref, _running_reader())
    return dict(view.workbench.as_dict()), dict(view.live_progress.as_dict())


def test_valid_direct_construction_baseline():
    # Guards the forgery tests below: a faithfully-composed pair constructs, so a
    # raised SpineError there is caused by the mutated field, not the baseline.
    mod = _mod()
    wb, lp = _good_children(mod)
    view = mod.AgentRunSupervisorLiveWorkbenchView(**_compose_kwargs(mod, wb, lp))
    assert view.as_dict()["type"] == mod.LIVE_WORKBENCH_VIEW_TYPE


def test_projection_task_id_mismatch_fails_closed():
    mod = _mod()
    wb, lp = _good_children(mod)
    bad_lp = dict(lp)
    bad_lp["task_id"] = "task_other"  # a valid id, but not the workbench's task
    with pytest.raises(SpineError) as exc:
        mod.AgentRunSupervisorLiveWorkbenchView(**_compose_kwargs(mod, wb, bad_lp))
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_WORKBENCH_VIEW


def test_top_level_task_id_mismatch_fails_closed():
    mod = _mod()
    wb, lp = _good_children(mod)
    with pytest.raises(SpineError) as exc:
        mod.AgentRunSupervisorLiveWorkbenchView(
            **_compose_kwargs(mod, wb, lp, task_id="task_other")
        )
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_WORKBENCH_VIEW


def test_progress_available_flag_must_mirror_live_progress():
    mod = _mod()
    wb, lp = _good_children(mod)  # available projection
    with pytest.raises(SpineError) as exc:
        mod.AgentRunSupervisorLiveWorkbenchView(
            **_compose_kwargs(mod, wb, lp, progress_available=False)
        )
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_WORKBENCH_VIEW


def test_progress_error_code_must_be_exact_string_when_unavailable():
    mod = _mod()
    wb, lp = _good_children(mod)
    missing_lp = dict(lp)
    missing_lp.update(
        available=False,
        supervisor_state="unknown",
        schema_version=0,
        progress_last_seq=0,
        progress_event_count=0,
        observed_last_seq=0,
        observed_event_count=0,
        resume_cursor=None,
        has_more=False,
        stale=False,
        records=[],
        error_code="live_progress_unavailable",
    )

    class _HostileStr(str):
        def __eq__(self, other):
            return True

    with pytest.raises(SpineError) as exc:
        mod.AgentRunSupervisorLiveWorkbenchView(
            **_compose_kwargs(
                mod,
                wb,
                missing_lp,
                progress_available=False,
                progress_error_code=_HostileStr("live_progress_unavailable"),
            )
        )
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_WORKBENCH_VIEW


def test_forged_nested_workbench_fails_closed_without_echo():
    mod = _mod()
    wb, lp = _good_children(mod)
    bad_wb = dict(wb)
    bad_wb["refs"] = ["ref_raw_prompt_dump"]  # leak canary in a nested ref
    with pytest.raises(SpineError) as exc:
        mod.AgentRunSupervisorLiveWorkbenchView(
            **_compose_kwargs(mod, bad_wb, lp, task_id=bad_wb["task_id"])
        )
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_WORKBENCH_VIEW
    assert "raw_prompt" not in str(exc.value)


def test_forged_nested_live_progress_fails_closed_without_echo():
    mod = _mod()
    wb, lp = _good_children(mod)
    bad_lp = dict(lp)
    # a leaky token in a nested record must fail closed and never be carried
    bad_lp["records"] = [
        {"seq": 1, "family": "tool", "kind": "chat_id", "observed_status": "active", "text_length": 0}
    ]
    with pytest.raises(SpineError) as exc:
        mod.AgentRunSupervisorLiveWorkbenchView(**_compose_kwargs(mod, wb, bad_lp))
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_WORKBENCH_VIEW
    assert "chat_id" not in str(exc.value)


def test_validate_rejects_forged_object_new():
    mod = _mod()
    wb, lp = _good_children(mod)
    forged = object.__new__(mod.AgentRunSupervisorLiveWorkbenchView)
    # available projection but a forged progress_available=False → inconsistent
    for name, value in _compose_kwargs(mod, wb, lp, progress_available=False).items():
        object.__setattr__(forged, name, value)
    assert type(forged) is mod.AgentRunSupervisorLiveWorkbenchView
    with pytest.raises(SpineError) as exc:
        mod.validate_agent_run_supervisor_live_workbench_view(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_WORKBENCH_VIEW


def test_serialize_revalidates_forged_view_without_echo():
    mod = _mod()
    wb, lp = _good_children(mod)
    bad_wb = dict(wb)
    bad_wb["refs"] = ["chat_id_leak_ref"]
    forged = object.__new__(mod.AgentRunSupervisorLiveWorkbenchView)
    for name, value in _compose_kwargs(mod, bad_wb, lp, task_id=bad_wb["task_id"]).items():
        object.__setattr__(forged, name, value)
    with pytest.raises(SpineError) as exc:
        mod.serialize_agent_run_supervisor_live_workbench_view(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_WORKBENCH_VIEW
    assert "chat_id" not in str(exc.value)


def test_view_keeps_nested_children_immutable_against_raw_material_mutation():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    view = _build(mod, reg, port, ref, _running_reader())
    with pytest.raises(AttributeError):
        view.workbench.refs.append("raw_prompt_dump")
    with pytest.raises(AttributeError):
        view.live_progress.records.append({"kind": "chat_id"})
    data = view.as_dict()
    assert "raw_prompt" not in str(data)
    assert "chat_id" not in str(data)
    assert scan_for_leak(data) is None


# --------------------------------------------------------------------------- #
# I. Serialization is byte-stable and leak-free
# --------------------------------------------------------------------------- #
def test_serialize_is_byte_stable_and_leak_free():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    view = _build(mod, reg, port, ref, _running_reader(), artifact_dir="/tmp/private/run/abc")
    encoded = mod.serialize_agent_run_supervisor_live_workbench_view(view)
    assert type(encoded) is bytes
    assert encoded == mod.serialize_agent_run_supervisor_live_workbench_view(view)
    # safe public handles are present
    assert b"artifact_local_0" in encoded
    assert b"task_alpha" in encoded
    # no path / platform / raw-text canaries — note "text_length" is a safe count
    # field name, so we assert the raw ``"text"`` key (with quotes) is absent.
    for marker in (
        b"/home/",
        b"/tmp/",
        b"summary",
        b"content",
        b"message",
        b"chat_id",
        b"oc_",
        b"ou_",
        b"platform_id",
        b'"text"',
        b"raw_prompt",
        b"agent_stdout",
    ):
        assert marker not in encoded


# --------------------------------------------------------------------------- #
# J. Read-only: building / serializing appends no event, launches no work
# --------------------------------------------------------------------------- #
def test_building_and_serializing_appends_no_events_or_backend_work():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    before = reg.log.last_seq("task_alpha")
    backend_sessions = backend.session_count()

    for _ in range(3):
        view = _build(mod, reg, port, ref, _running_reader())
        mod.serialize_agent_run_supervisor_live_workbench_view(view)

    assert reg.log.last_seq("task_alpha") == before  # no appended events
    assert backend.session_count() == backend_sessions  # no respawn / launch
    assert port.session_count() == 1


def test_live_progress_cursor_never_enters_the_canonical_log():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    reader = _FakeReader(
        _progress("running", last_seq=9, event_count=9),
        _FakePage((_rec(1), _rec(2)), next_cursor=2, has_more=False),
    )
    seq_before = reg.log.last_seq("task_alpha")
    view = _build(mod, reg, port, ref, reader)
    # the foreign ARS resume cursor is surfaced but never written into the log
    assert view.as_dict()["resume_cursor"] == 2
    assert reg.log.last_seq("task_alpha") == seq_before


# --------------------------------------------------------------------------- #
# K. Static boundary scan — no real runtime / IM / delivery / ARS import wiring
# --------------------------------------------------------------------------- #
_FORBIDDEN_SOURCE_TOKENS = (
    "subprocess",
    "socket",
    ".Popen(",
    "os.system",
    "create_subprocess",
    "import temporalio",
    "acpx",
    " npx",
    "asyncio.create",
    "gateway",
    "feishu",
    "lark",
    "send(",
    "edit_message",
    "im_send",
    "delivery_payload",
)


def test_source_wires_no_real_runtime_or_delivery_surface():
    mod = _mod()
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert [token for token in _FORBIDDEN_SOURCE_TOKENS if token in source] == []
    # no top-level (or any) direct import of the ARS producer library
    assert re.search(r"(?m)^\s*(import|from)\s+agent_run_supervisor", source) is None
    import_lines = [ln for ln in source.splitlines() if ln.startswith(("import ", "from "))]
    for line in import_lines:
        for root in (
            "subprocess",
            "socket",
            "temporal",
            "gateway",
            "feishu",
            "lark",
            "httpx",
            "requests",
            "urllib",
            "docker",
            "asyncio",
        ):
            assert root not in line, f"forbidden import {root!r}: {line!r}"
