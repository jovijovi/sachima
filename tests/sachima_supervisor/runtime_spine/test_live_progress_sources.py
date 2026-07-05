"""PR-LS2 — host-owned live-progress source binding acceptance tests.

Focused RED/GREEN tests for the PR-LS2 slice that adds a local/offline,
host-owned ``LiveProgressSource`` binding layer over the PR-LS1
``AgentRunSupervisorLiveWorkbenchView`` composition. A binding resolves a
tracked ``(task_id, session_id)`` / ``SessionRef`` to:

* a **private** ``artifact_dir`` (a real path, reader-only — never serialized,
  logged, or scanned into any public projection / source output),
* a **safe** ``artifact_ref`` public handle, and
* a foreign ``last_seen_cursor`` (an agent-run-supervisor live-progress cursor,
  never a Sachima ``TaskEventLog`` seq).

Everything here stays pure local/offline Python over the deterministic in-memory
backend + in-test fake progress readers: no real AGENT / process / network /
durable service / listener is started, and no Gateway / Temporal Worker is
touched. Binding, resolving, building, and serializing are read-only — they
append no event, launch no work, and call no backend / IM / delivery surface.

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

_SAFE_REFS = ("ws_alpha", "policy_default")
_PRIVATE_DIR = "/tmp/private/run/abc"
_SAFE_HANDLE = "artifact_local_0"


def _mod():
    return importlib.import_module(
        "sachima_supervisor.runtime_spine.live_progress_sources"
    )


# --------------------------------------------------------------------------- #
# Workbench-side fixtures (mirrors test_agent_run_supervisor_live_workbench.py)
# --------------------------------------------------------------------------- #
def _spec(
    task_id: str = "task_alpha",
    *,
    roles: tuple[str, ...] = ("read_only",),
    refs: tuple[str, ...] = _SAFE_REFS,
    needs_agent: bool = True,
) -> LaunchSpec:
    return build_launch_spec(
        task_id=task_id,
        agent_kind="local_agent",
        mode_flags={"needs_agent": needs_agent},
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


class _CapturingReader:
    """Records the ``artifact_dir`` / ``after_seq`` it is called with."""

    def __init__(self, progress, page):
        self._p, self._page = progress, page
        self.load_dirs: list = []
        self.page_calls: list = []

    def load_progress(self, artifact_dir):
        self.load_dirs.append(artifact_dir)
        return self._p

    def read_event_page(self, artifact_dir, *, after_seq=None, limit=100):
        self.page_calls.append((artifact_dir, after_seq))
        return self._page


class _CursorAwareReader:
    """Serves the page keyed by the ``after_seq`` the builder forwards."""

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


def _rec(seq, *, family="tool", kind="tool_call", status="running", text_length=0):
    return _FakeRec(seq=seq, family=family, kind=kind, status=status, text_length=text_length)


def _running_reader():
    return _CapturingReader(
        _progress("running", last_seq=3, event_count=3),
        _FakePage(
            (
                _rec(1, family="lifecycle", kind="agent_started", text_length=0),
                _rec(2, family="tool", kind="tool_call", text_length=42),
                _rec(3, family="step", kind="progress", text_length=7),
            ),
            next_cursor=3,
            has_more=False,
        ),
    )


def _bindings_with(mod, ref, *, artifact_dir=_PRIVATE_DIR, artifact_ref=_SAFE_HANDLE, last_seen_cursor=None):
    bindings = mod.LiveProgressSourceBindings()
    bindings.bind(
        ref.task_id, ref.session_id, artifact_dir, artifact_ref, last_seen_cursor=last_seen_cursor
    )
    return bindings


# --------------------------------------------------------------------------- #
# A. Public surface + package exports
# --------------------------------------------------------------------------- #
def test_live_progress_source_public_surface_is_exported():
    mod = _mod()
    assert mod.RUNTIME_INVALID_LIVE_PROGRESS_SOURCE == "runtime_invalid_live_progress_source"
    assert mod.RUNTIME_INVALID_LIVE_PROGRESS_SOURCE in mod.LIVE_PROGRESS_SOURCE_STABLE_CODES
    assert mod.LIVE_PROGRESS_SOURCE_TYPE == "sachima.runtime_spine.live_progress_source.v1"
    for name in (
        "LiveProgressSource",
        "LiveProgressSourceBindings",
        "ResolvedLiveProgressSource",
        "build_agent_run_supervisor_live_workbench_from_source",
        "validate_live_progress_source",
        "serialize_live_progress_source",
    ):
        assert hasattr(mod, name), name


def test_symbols_available_from_runtime_spine_package():
    spine = importlib.import_module("sachima_supervisor.runtime_spine")
    for name in (
        "RUNTIME_INVALID_LIVE_PROGRESS_SOURCE",
        "LIVE_PROGRESS_SOURCE_STABLE_CODES",
        "LIVE_PROGRESS_SOURCE_TYPE",
        "LiveProgressSource",
        "LiveProgressSourceBindings",
        "ResolvedLiveProgressSource",
        "build_agent_run_supervisor_live_workbench_from_source",
        "validate_live_progress_source",
        "serialize_live_progress_source",
    ):
        assert hasattr(spine, name), name


# --------------------------------------------------------------------------- #
# B. Binding resolves identity to private artifact_dir + safe artifact_ref + cursor
# --------------------------------------------------------------------------- #
def test_bind_resolves_private_dir_and_safe_metadata():
    mod = _mod()
    _reg, _backend, _port, ref = _running_port()
    bindings = mod.LiveProgressSourceBindings()
    source = bindings.bind(ref.task_id, ref.session_id, _PRIVATE_DIR, _SAFE_HANDLE, last_seen_cursor=2)
    # bind returns the safe public metadata
    assert type(source) is mod.LiveProgressSource
    assert source.task_id == "task_alpha"
    assert source.session_id == ref.session_id
    assert source.artifact_ref == _SAFE_HANDLE
    assert source.last_seen_cursor == 2

    resolved = bindings.resolve(ref)
    assert type(resolved) is mod.ResolvedLiveProgressSource
    # the private path is only reachable via the resolved handoff, not the metadata
    assert resolved.artifact_dir == _PRIVATE_DIR
    assert resolved.source.artifact_ref == _SAFE_HANDLE
    assert resolved.source.last_seen_cursor == 2


def test_resolve_by_task_id_and_session_id_pair():
    mod = _mod()
    _reg, _backend, _port, ref = _running_port()
    bindings = _bindings_with(mod, ref, last_seen_cursor=None)
    resolved = bindings.resolve(ref.task_id, ref.session_id)
    assert resolved.artifact_dir == _PRIVATE_DIR
    assert resolved.source.last_seen_cursor is None
    # resolve_source returns only the safe metadata object
    safe = bindings.resolve_source(ref)
    assert type(safe) is mod.LiveProgressSource
    assert safe.artifact_ref == _SAFE_HANDLE


# --------------------------------------------------------------------------- #
# C. Public source dict / bytes carry safe handle + cursor, never artifact_dir
# --------------------------------------------------------------------------- #
def test_source_dict_and_bytes_never_leak_artifact_dir_or_paths():
    mod = _mod()
    _reg, _backend, _port, ref = _running_port()
    bindings = _bindings_with(mod, ref, last_seen_cursor=5)
    source = bindings.resolve_source(ref)

    data = source.as_dict()
    assert data["type"] == mod.LIVE_PROGRESS_SOURCE_TYPE
    assert data["task_id"] == "task_alpha"
    assert data["session_id"] == ref.session_id
    assert data["artifact_ref"] == _SAFE_HANDLE
    assert data["last_seen_cursor"] == 5
    assert "artifact_dir" not in data
    assert scan_for_leak(data) is None

    blob = mod.serialize_live_progress_source(source)
    assert type(blob) is bytes
    assert blob == mod.serialize_live_progress_source(source)
    assert b"artifact_local_0" in blob
    assert b"task_alpha" in blob
    for marker in (b"/tmp/", b"/home/", b"private", b"artifact_dir", b"secret", b"abc"):
        assert marker not in blob


def test_resolved_source_repr_never_leaks_private_artifact_dir():
    mod = _mod()
    _reg, _backend, _port, ref = _running_port()
    bindings = _bindings_with(mod, ref, artifact_dir="/tmp/private/run/repr_canary")
    resolved = bindings.resolve(ref)

    for text in (repr(resolved), repr(bindings)):
        assert "/tmp/" not in text
        assert "private" not in text
        assert "repr_canary" not in text


# --------------------------------------------------------------------------- #
# D. Builder uses bound artifact_dir for reader, artifact_ref, after_seq=cursor
# --------------------------------------------------------------------------- #
def test_builder_uses_bound_dir_ref_and_cursor():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    reader = _running_reader()
    bindings = _bindings_with(mod, ref, artifact_dir="/tmp/private/run/xyz")

    view = mod.build_agent_run_supervisor_live_workbench_from_source(
        bindings, reg, port, ref, reader
    )
    data = view.as_dict()
    # artifact_dir went only to the reader (both calls), never into the view
    assert reader.load_dirs == ["/tmp/private/run/xyz"]
    assert reader.page_calls == [("/tmp/private/run/xyz", None)]
    # artifact_ref is the safe public handle in the projection half
    assert data["live_progress"]["artifact_ref"] == _SAFE_HANDLE
    assert data["workbench"]["task_id"] == "task_alpha"
    assert data["progress_available"] is True
    assert scan_for_leak(data) is None
    # the private path never reaches the serialized combined view
    from sachima_supervisor.runtime_spine.agent_run_supervisor_live_workbench import (
        serialize_agent_run_supervisor_live_workbench_view,
    )
    encoded = serialize_agent_run_supervisor_live_workbench_view(view)
    for marker in (b"/tmp/", b"/home/", b"xyz", b"private"):
        assert marker not in encoded


def test_builder_forwards_last_seen_cursor_as_after_seq():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    page2 = _FakePage(
        (
            _rec(3, family="message", kind="assistant"),
            _rec(5, family="message", kind="assistant"),
        ),
        next_cursor=5,
        has_more=True,
    )
    reader = _CursorAwareReader(_progress(last_seq=5, event_count=5), {2: page2})
    bindings = _bindings_with(mod, ref, last_seen_cursor=2)

    view = mod.build_agent_run_supervisor_live_workbench_from_source(
        bindings, reg, port, ref, reader
    )
    data = view.as_dict()
    assert [r["seq"] for r in data["live_progress"]["records"]] == [3, 5]
    assert data["resume_cursor"] == 5
    assert data["has_more"] is True


# --------------------------------------------------------------------------- #
# E. Cursor update from view.resume_cursor stored, never touches TaskEventLog
# --------------------------------------------------------------------------- #
def test_update_last_seen_cursor_from_view_without_touching_event_log():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(mod, ref, last_seen_cursor=None)

    view = mod.build_agent_run_supervisor_live_workbench_from_source(
        bindings, reg, port, ref, _running_reader()
    )
    cursor = view.as_dict()["resume_cursor"]
    assert cursor == 3

    before = reg.log.last_seq("task_alpha")
    updated = bindings.update_last_seen_cursor(ref, cursor)
    assert type(updated) is mod.LiveProgressSource
    assert updated.last_seen_cursor == 3
    # persisted into the binding for the next resume
    assert bindings.resolve(ref).source.last_seen_cursor == 3
    assert bindings.resolve_source(ref).last_seen_cursor == 3
    # the foreign ARS cursor never became a canonical TaskEventLog seq
    assert reg.log.last_seq("task_alpha") == before


def test_update_last_seen_cursor_accepts_none_reset():
    mod = _mod()
    _reg, _backend, _port, ref = _running_port()
    bindings = _bindings_with(mod, ref, last_seen_cursor=7)
    updated = bindings.update_last_seen_cursor(ref, None)
    assert updated.last_seen_cursor is None
    assert bindings.resolve(ref).source.last_seen_cursor is None


# --------------------------------------------------------------------------- #
# F. Missing / forged / mismatched fails closed with a stable code, no raw echo
# --------------------------------------------------------------------------- #
def test_resolve_missing_binding_fails_closed():
    mod = _mod()
    _reg, _backend, _port, ref = _running_port()
    bindings = mod.LiveProgressSourceBindings()  # nothing bound
    with pytest.raises(SpineError) as exc:
        bindings.resolve(ref)
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_SOURCE


def test_resolve_mismatched_session_fails_closed():
    mod = _mod()
    _reg, _backend, _port, ref = _running_port()
    bindings = _bindings_with(mod, ref)
    with pytest.raises(SpineError) as exc:
        bindings.resolve("task_alpha", "sess_not_bound")
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_SOURCE


def test_resolve_forged_session_ref_fails_closed():
    mod = _mod()
    _reg, _backend, _port, ref = _running_port()
    bindings = _bindings_with(mod, ref)
    forged = object.__new__(SessionRef)
    object.__setattr__(forged, "task_id", "task_alpha")
    object.__setattr__(forged, "session_id", "not_a_session")  # missing sess_ prefix
    with pytest.raises(SpineError) as exc:
        bindings.resolve(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_SOURCE


def test_builder_with_ref_untracked_by_port_fails_closed_no_echo():
    mod = _mod()
    reg, _backend, port, _ref = _running_port()
    # a well-formed but port-untracked ref; bind it so resolve succeeds, so the
    # failure must come from the workbench half validating ref against the port.
    forged_ref = SessionRef(task_id="task_alpha", session_id="sess_forged")
    bindings = _bindings_with(mod, forged_ref)
    with pytest.raises(SpineError) as exc:
        mod.build_agent_run_supervisor_live_workbench_from_source(
            bindings, reg, port, forged_ref, _running_reader()
        )
    assert exc.value.code  # a stable code, not a raw message
    assert "sess_forged" not in str(exc.value)


# --------------------------------------------------------------------------- #
# G. Unsafe task_id / session_id / artifact_ref / cursor rejected; bool rejected
# --------------------------------------------------------------------------- #
def test_bind_rejects_unsafe_task_id():
    mod = _mod()
    bindings = mod.LiveProgressSourceBindings()
    with pytest.raises(SpineError) as exc:
        bindings.bind("Task-Alpha", "sess_a", _PRIVATE_DIR, _SAFE_HANDLE)
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_SOURCE


def test_bind_rejects_unsafe_session_id():
    mod = _mod()
    bindings = mod.LiveProgressSourceBindings()
    with pytest.raises(SpineError):
        bindings.bind("task_alpha", "session_no_prefix", _PRIVATE_DIR, _SAFE_HANDLE)


def test_bind_rejects_leaky_or_pathlike_artifact_ref():
    mod = _mod()
    bindings = mod.LiveProgressSourceBindings()
    for bad_ref in ("chat_id", "/tmp/run/artifact", "artifact local"):
        with pytest.raises(SpineError) as exc:
            bindings.bind("task_alpha", "sess_a", _PRIVATE_DIR, bad_ref)
        assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_SOURCE
        assert str(bad_ref) not in str(exc.value)


def test_bind_rejects_empty_private_dir():
    mod = _mod()
    bindings = mod.LiveProgressSourceBindings()
    with pytest.raises(SpineError) as exc:
        bindings.bind("task_alpha", "sess_a", "", _SAFE_HANDLE)
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_SOURCE
    with pytest.raises(SpineError):
        bindings.bind("task_alpha", "sess_a", None, _SAFE_HANDLE)


def test_bind_rejects_bool_and_negative_cursor():
    mod = _mod()
    bindings = mod.LiveProgressSourceBindings()
    with pytest.raises(SpineError) as exc:
        bindings.bind("task_alpha", "sess_a", _PRIVATE_DIR, _SAFE_HANDLE, last_seen_cursor=True)
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_SOURCE
    with pytest.raises(SpineError):
        bindings.bind("task_alpha", "sess_a", _PRIVATE_DIR, _SAFE_HANDLE, last_seen_cursor=-1)


def test_update_cursor_rejects_bool():
    mod = _mod()
    _reg, _backend, _port, ref = _running_port()
    bindings = _bindings_with(mod, ref)
    with pytest.raises(SpineError) as exc:
        bindings.update_last_seen_cursor(ref, True)
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_SOURCE


def test_validate_rejects_forged_object_new_source():
    mod = _mod()
    forged = object.__new__(mod.LiveProgressSource)
    object.__setattr__(forged, "type", mod.LIVE_PROGRESS_SOURCE_TYPE)
    object.__setattr__(forged, "task_id", "task_alpha")
    object.__setattr__(forged, "session_id", "sess_a")
    object.__setattr__(forged, "artifact_ref", "chat_id")  # leaky handle
    object.__setattr__(forged, "last_seen_cursor", None)
    with pytest.raises(SpineError) as exc:
        mod.validate_live_progress_source(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_SOURCE
    assert "chat_id" not in str(exc.value)


def test_direct_construction_of_forged_source_fails_closed():
    mod = _mod()
    with pytest.raises(SpineError):
        mod.LiveProgressSource(
            type="wrong.type",
            task_id="task_alpha",
            session_id="sess_a",
            artifact_ref=_SAFE_HANDLE,
            last_seen_cursor=None,
        )


# --------------------------------------------------------------------------- #
# H. Local/offline: no event append, no backend spawn; static no-wiring scan
# --------------------------------------------------------------------------- #
def test_bind_resolve_build_serialize_appends_no_events_or_backend_work():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    bindings = _bindings_with(mod, ref)
    before = reg.log.last_seq("task_alpha")
    backend_sessions = backend.session_count()

    for _ in range(3):
        view = mod.build_agent_run_supervisor_live_workbench_from_source(
            bindings, reg, port, ref, _running_reader()
        )
        cursor = view.as_dict()["resume_cursor"]
        bindings.update_last_seen_cursor(ref, cursor)
        src = bindings.resolve_source(ref)
        mod.serialize_live_progress_source(src)

    assert reg.log.last_seq("task_alpha") == before
    assert backend.session_count() == backend_sessions
    assert port.session_count() == 1


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
