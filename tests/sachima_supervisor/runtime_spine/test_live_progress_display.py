"""PR-LS4-B — default-off live-progress display renderer acceptance tests.

Focused RED/GREEN tests for the LS4-B slice that adds the Sachima-side
consumption/display surface over the LS4-A gated query output: a pure, refs-only
``LiveProgressDisplay`` rendered from one ``AgentRunSupervisorLiveWorkbenchView``,
plus a ``display_task_live_progress`` entrypoint that stays behind the LS4-A
default-off ``LiveProgressQueryActivationGate``.

The display carries only closed-vocabulary state tokens, bounded counts, the
foreign resume cursor, stable error codes, and deterministic display lines built
from a closed template vocabulary — never raw stdout / stderr / prompt / tool
output / the ARS summary / platform ids / paths / card JSON. A disabled query
denies before any reader call; corrupt / missing artifacts render as unavailable
with a stable code; rendering mutates nothing.

Everything here stays pure local/offline Python over the deterministic in-memory
backend + in-test fake progress readers: no real AGENT / process / network /
durable service / listener is started, and no Gateway / Feishu / IM / delivery /
Temporal Worker surface is touched. Forbidden terms below are no-leak / denied
boundary canaries only, never behavior.
"""

from __future__ import annotations

import importlib
import json
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
        "sachima_supervisor.runtime_spine.live_progress_display"
    )


def _query_mod():
    return importlib.import_module(
        "sachima_supervisor.runtime_spine.live_progress_query"
    )


def _sources_mod():
    return importlib.import_module(
        "sachima_supervisor.runtime_spine.live_progress_sources"
    )


# --------------------------------------------------------------------------- #
# Workbench-side fixtures (mirrors test_live_progress_query.py)
# --------------------------------------------------------------------------- #
def _spec(task_id: str = "task_alpha") -> LaunchSpec:
    return build_launch_spec(
        task_id=task_id,
        agent_kind="local_agent",
        mode_flags={"needs_agent": True},
        roles=("read_only",),
        refs=_SAFE_REFS,
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
        self.page_calls: list = []

    def load_progress(self, artifact_dir):
        return self._p

    def read_event_page(self, artifact_dir, *, after_seq=None, limit=100):
        self.page_calls.append(after_seq)
        assert after_seq in self._pages, after_seq
        return self._pages[after_seq]


class _BoomReader:
    """A reader that raises internally — reader corruption must render closed."""

    def __init__(self):
        self.load_dirs: list = []

    def load_progress(self, artifact_dir):
        self.load_dirs.append(artifact_dir)
        raise ValueError("corrupt-progress-internal-detail")

    def read_event_page(self, artifact_dir, *, after_seq=None, limit=100):
        raise ValueError("corrupt-page-internal-detail")


class _MissingReader:
    """A reader whose progress artifact is absent — must render unavailable."""

    def load_progress(self, artifact_dir):
        return None

    def read_event_page(self, artifact_dir, *, after_seq=None, limit=100):
        raise AssertionError("must not page a missing progress artifact")


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
                _rec(3, family="tool", kind="tool_call", text_length=7),
            ),
            next_cursor=3,
            has_more=False,
        ),
    )


def _bindings_with(ref, *, artifact_dir=_PRIVATE_DIR, artifact_ref=_SAFE_HANDLE, last_seen_cursor=None):
    bindings = _sources_mod().LiveProgressSourceBindings()
    bindings.bind(
        ref.task_id, ref.session_id, artifact_dir, artifact_ref, last_seen_cursor=last_seen_cursor
    )
    return bindings


def _local_gate():
    return _query_mod().local_offline_query_gate()


def _view_for(ref, reg, port, reader, *, after_seq=None):
    from sachima_supervisor.runtime_spine.agent_run_supervisor_live_workbench import (
        build_agent_run_supervisor_live_workbench_view,
    )

    return build_agent_run_supervisor_live_workbench_view(
        reg, port, ref, reader, _PRIVATE_DIR, _SAFE_HANDLE, after_seq=after_seq
    )


# --------------------------------------------------------------------------- #
# A. Public surface + package exports
# --------------------------------------------------------------------------- #
def test_display_public_surface_is_exported():
    mod = _mod()
    assert mod.RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY == "runtime_invalid_live_progress_display"
    assert mod.LIVE_PROGRESS_DISPLAY_STABLE_CODES == frozenset(
        {"runtime_invalid_live_progress_display"}
    )
    assert mod.LIVE_PROGRESS_DISPLAY_TYPE == "sachima.runtime_spine.live_progress_display.v1"
    for name in (
        "LiveProgressDisplay",
        "LiveProgressDisplayService",
        "render_live_progress_display",
        "display_task_live_progress",
        "validate_live_progress_display",
        "serialize_live_progress_display",
    ):
        assert name in mod.__all__
        assert hasattr(mod, name)


def test_display_symbols_available_from_runtime_spine_package():
    import sachima_supervisor.runtime_spine as spine

    for name in (
        "LiveProgressDisplay",
        "LiveProgressDisplayService",
        "render_live_progress_display",
        "display_task_live_progress",
        "validate_live_progress_display",
        "serialize_live_progress_display",
    ):
        assert name in spine.__all__
        assert hasattr(spine, name)


# --------------------------------------------------------------------------- #
# B. Render happy path — event consumption/display from the safe query output
# --------------------------------------------------------------------------- #
def test_render_running_view_displays_refs_only_fields():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    display = mod.render_live_progress_display(_view_for(ref, reg, port, _running_reader()))

    data = display.as_dict()
    assert data["type"] == mod.LIVE_PROGRESS_DISPLAY_TYPE
    assert data["task_id"] == "task_alpha"
    assert data["session_id"] == ref.session_id
    assert data["artifact_ref"] == _SAFE_HANDLE
    assert data["task_status"] == "running"
    assert data["terminal"] is False
    assert data["supervisor_state"] == "active"
    assert data["progress_available"] is True
    assert data["progress_error_code"] is None
    assert data["progress_event_count"] == 3
    assert data["observed_event_count"] == 3
    assert data["resume_cursor"] == 3
    assert data["has_more"] is False
    assert data["stale"] is False
    # events consumed into a closed per-family aggregation, sorted by family
    assert data["family_counts"] == {"lifecycle": 1, "tool": 2}
    assert scan_for_leak(data) is None


def test_render_display_lines_are_deterministic_closed_templates():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    display = mod.render_live_progress_display(_view_for(ref, reg, port, _running_reader()))

    assert display.display_lines == (
        f"task task_alpha session {ref.session_id} status running",
        "live active events 3 shown 3",
        "cursor 3 more no",
        "families lifecycle 1 tool 2",
    )


def test_serialize_display_is_byte_stable_canonical_json():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    display = mod.render_live_progress_display(_view_for(ref, reg, port, _running_reader()))

    encoded = mod.serialize_live_progress_display(display)
    assert encoded == mod.serialize_live_progress_display(display)
    assert encoded == json.dumps(
        display.as_dict(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


# --------------------------------------------------------------------------- #
# C. Cursor / progress update / resume semantics
# --------------------------------------------------------------------------- #
def _two_page_reader():
    return _CursorAwareReader(
        _progress("running", last_seq=5, event_count=5),
        {
            None: _FakePage(
                (_rec(1), _rec(2), _rec(3)), next_cursor=3, has_more=True
            ),
            3: _FakePage((_rec(4), _rec(5)), next_cursor=5, has_more=False),
        },
    )


def test_display_resume_after_seq_shows_only_new_records():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    bindings = _bindings_with(ref)
    reader = _two_page_reader()

    first = mod.display_task_live_progress(
        bindings, reg, port, reader, ref.task_id, ref.session_id, gate=_local_gate()
    )
    assert first.as_dict()["observed_event_count"] == 3
    assert first.as_dict()["resume_cursor"] == 3
    assert first.as_dict()["has_more"] is True
    assert "cursor 3 more yes" in first.display_lines

    # the caller explicitly advances the binding cursor, then re-displays
    bindings.update_last_seen_cursor(ref, first.resume_cursor)
    second = mod.display_task_live_progress(
        bindings, reg, port, reader, ref.task_id, ref.session_id, gate=_local_gate()
    )
    assert reader.page_calls == [None, 3]
    assert second.as_dict()["observed_event_count"] == 2
    assert second.as_dict()["resume_cursor"] == 5
    assert second.as_dict()["has_more"] is False


def test_display_after_seq_override_wins_over_binding_cursor():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref, last_seen_cursor=0)
    reader = _two_page_reader()

    display = mod.display_task_live_progress(
        bindings, reg, port, reader, ref.task_id, ref.session_id,
        gate=_local_gate(), after_seq=3,
    )
    assert reader.page_calls == [3]
    assert display.as_dict()["observed_event_count"] == 2


def test_display_stale_page_is_marked_as_observation():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    # the summary claims seq 9 but the exhausted stream only reaches 3 → stale
    reader = _CapturingReader(
        _progress("running", last_seq=9, event_count=9),
        _FakePage((_rec(1), _rec(2), _rec(3)), next_cursor=3, has_more=False),
    )
    display = mod.render_live_progress_display(_view_for(ref, reg, port, reader))
    assert display.stale is True
    assert display.progress_available is True
    assert "stale snapshot" in display.display_lines


def test_display_does_not_mutate_cursor_or_event_log():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    bindings = _bindings_with(ref, last_seen_cursor=None)
    before_seq = reg.log.last_seq("task_alpha")

    for _ in range(3):
        display = mod.display_task_live_progress(
            bindings, reg, port, _running_reader(), ref.task_id, ref.session_id,
            gate=_local_gate(),
        )
        assert display.resume_cursor == 3
        assert bindings.resolve_source(ref).last_seen_cursor is None

    assert reg.log.last_seq("task_alpha") == before_seq
    assert backend.session_count() == 1
    assert port.session_count() == 1


# --------------------------------------------------------------------------- #
# D. Terminal / settled states through the existing stable vocabularies
# --------------------------------------------------------------------------- #
def test_display_terminal_cancelled_task_status():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    port.kill(ref)  # drive to a terminal (cancelled) state through the public API

    reader = _CapturingReader(
        _progress("killed", last_seq=3, event_count=3),
        _FakePage((_rec(1), _rec(2), _rec(3, status="killed")), next_cursor=3, has_more=False),
    )
    display = mod.render_live_progress_display(_view_for(ref, reg, port, reader))
    data = display.as_dict()
    assert data["task_status"] == "cancelled"
    assert data["terminal"] is True
    assert data["supervisor_state"] == "settled"
    assert f"task task_alpha session {ref.session_id} status cancelled" in display.display_lines


@pytest.mark.parametrize("ars_state", ["completed", "failed", "cancelled", "killed", "exited"])
def test_display_supervisor_terminal_states_collapse_to_settled(ars_state):
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    reader = _CapturingReader(
        _progress(ars_state, last_seq=1, event_count=1),
        _FakePage((_rec(1, status=ars_state),), next_cursor=1, has_more=False),
    )
    display = mod.render_live_progress_display(_view_for(ref, reg, port, reader))
    assert display.supervisor_state == "settled"
    assert "live settled events 1 shown 1" in display.display_lines


# --------------------------------------------------------------------------- #
# E. Error / unavailable / corrupt / missing artifacts render fail-closed
# --------------------------------------------------------------------------- #
def test_display_missing_progress_renders_unavailable_with_stable_code():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    display = mod.render_live_progress_display(_view_for(ref, reg, port, _MissingReader()))
    data = display.as_dict()
    assert data["progress_available"] is False
    assert data["progress_error_code"] == "live_progress_unavailable"
    assert data["supervisor_state"] == "unknown"
    assert data["observed_event_count"] == 0
    assert data["resume_cursor"] is None
    assert data["family_counts"] == {}
    assert "live unavailable code live_progress_unavailable" in display.display_lines
    # the task workbench half still displays — unavailability never blocks it
    assert data["task_status"] == "running"


def test_display_corrupt_progress_renders_stable_code_without_raw_detail():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    display = mod.render_live_progress_display(_view_for(ref, reg, port, _BoomReader()))
    data = display.as_dict()
    assert data["progress_available"] is False
    assert data["progress_error_code"] == "live_progress_corrupt"
    encoded = mod.serialize_live_progress_display(display)
    assert b"corrupt-progress-internal-detail" not in encoded
    assert b"corrupt-page-internal-detail" not in encoded
    assert b"ValueError" not in encoded


def test_render_rejects_forged_or_non_view_input():
    mod = _mod()

    class _FakeView:
        type = "sachima.runtime_spine.agent_run_supervisor_live_workbench_view.v1"

    for bad in (None, {}, "view", 7, _FakeView()):
        with pytest.raises(SpineError) as exc:
            mod.render_live_progress_display(bad)
        assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY


# --------------------------------------------------------------------------- #
# F. Default-off posture — the display query denies before any reader call
# --------------------------------------------------------------------------- #
def test_display_query_disabled_by_default_fails_closed_reader_untouched():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    bindings = _bindings_with(ref, last_seen_cursor=7)
    reader = _running_reader()
    before_seq = reg.log.last_seq("task_alpha")

    with pytest.raises(SpineError) as exc:
        mod.display_task_live_progress(
            bindings, reg, port, reader, ref.task_id, ref.session_id
        )
    assert exc.value.code == _query_mod().RUNTIME_LIVE_PROGRESS_QUERY_DISABLED
    assert reader.load_dirs == []
    assert reader.page_calls == []
    assert bindings.resolve_source(ref).last_seen_cursor == 7
    assert reg.log.last_seq("task_alpha") == before_seq


def test_display_query_denied_gate_fails_closed_reader_untouched():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref)
    reader = _running_reader()

    class _ForgedGate:
        type = _query_mod().LIVE_PROGRESS_QUERY_GATE_TYPE
        surface = "gateway_public"
        enabled = True

    with pytest.raises(SpineError) as exc:
        mod.display_task_live_progress(
            bindings, reg, port, reader, ref.task_id, ref.session_id, gate=_ForgedGate()
        )
    assert exc.value.code == _query_mod().RUNTIME_INVALID_LIVE_PROGRESS_QUERY
    assert reader.load_dirs == []


def test_display_service_is_disabled_by_default():
    mod = _mod()
    query_mod = _query_mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref)
    reader = _running_reader()

    service = mod.LiveProgressDisplayService(
        query_service=query_mod.LiveProgressQueryService(
            bindings=bindings, registry=reg, port=port, progress_reader=reader
        )
    )
    with pytest.raises(SpineError) as exc:
        service.display_task_live_progress(ref.task_id, ref.session_id)
    assert exc.value.code == query_mod.RUNTIME_LIVE_PROGRESS_QUERY_DISABLED
    assert reader.load_dirs == []


def test_display_service_with_local_gate_renders_display():
    mod = _mod()
    query_mod = _query_mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref)

    service = mod.LiveProgressDisplayService(
        query_service=query_mod.LiveProgressQueryService(
            bindings=bindings, registry=reg, port=port,
            progress_reader=_running_reader(), gate=_local_gate(),
        )
    )
    display = service.display_task_live_progress(ref.task_id, ref.session_id)
    assert type(display) is mod.LiveProgressDisplay
    assert display.as_dict()["progress_available"] is True


def test_display_service_rejects_non_query_service():
    mod = _mod()
    with pytest.raises(SpineError) as exc:
        mod.LiveProgressDisplayService(query_service=object())
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY


# --------------------------------------------------------------------------- #
# G. Forged / tampered displays fail closed
# --------------------------------------------------------------------------- #
def test_validate_rejects_forged_object_new_display():
    mod = _mod()
    forged = object.__new__(mod.LiveProgressDisplay)
    for name, value in (
        ("type", mod.LIVE_PROGRESS_DISPLAY_TYPE),
        ("task_id", "task_alpha"),
        ("session_id", "sess_x"),
        ("artifact_ref", _SAFE_HANDLE),
        ("task_status", "running"),
        ("terminal", False),
        ("supervisor_state", "active"),
        ("progress_available", True),
        ("progress_error_code", None),
        ("progress_event_count", 1),
        ("observed_event_count", 1),
        ("resume_cursor", 1),
        ("has_more", False),
        ("stale", False),
        ("family_counts", (("tool", 1),)),
        # tampered display lines smuggling raw material past the renderer
        ("display_lines", ("raw stdout dump: /home/agent/secret",)),
    ):
        object.__setattr__(forged, name, value)
    with pytest.raises(SpineError) as exc:
        mod.validate_live_progress_display(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY
    assert "/home/agent" not in str(exc.value)


def test_direct_construction_with_tampered_lines_fails_closed():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    display = mod.render_live_progress_display(_view_for(ref, reg, port, _running_reader()))
    fields = display.as_dict()
    with pytest.raises(SpineError) as exc:
        mod.LiveProgressDisplay(
            type=fields["type"],
            task_id=fields["task_id"],
            session_id=fields["session_id"],
            artifact_ref=fields["artifact_ref"],
            task_status=fields["task_status"],
            terminal=fields["terminal"],
            supervisor_state=fields["supervisor_state"],
            progress_available=fields["progress_available"],
            progress_error_code=fields["progress_error_code"],
            progress_event_count=fields["progress_event_count"],
            observed_event_count=fields["observed_event_count"],
            resume_cursor=fields["resume_cursor"],
            has_more=fields["has_more"],
            stale=fields["stale"],
            family_counts=display.family_counts,
            display_lines=display.display_lines + ("free text injected",),
        )
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY


def test_display_rejects_unsafe_family_token_and_status():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    display = mod.render_live_progress_display(_view_for(ref, reg, port, _running_reader()))

    def _rebuild(**overrides):
        kwargs = dict(
            type=display.type,
            task_id=display.task_id,
            session_id=display.session_id,
            artifact_ref=display.artifact_ref,
            task_status=display.task_status,
            terminal=display.terminal,
            supervisor_state=display.supervisor_state,
            progress_available=display.progress_available,
            progress_error_code=display.progress_error_code,
            progress_event_count=display.progress_event_count,
            observed_event_count=display.observed_event_count,
            resume_cursor=display.resume_cursor,
            has_more=display.has_more,
            stale=display.stale,
            family_counts=display.family_counts,
            display_lines=display.display_lines,
        )
        kwargs.update(overrides)
        return mod.LiveProgressDisplay(**kwargs)

    for overrides in (
        {"task_status": "exploded"},
        {"supervisor_state": "supernova"},
        {"terminal": True},  # disagrees with a non-terminal running status
        {"family_counts": (("Bad Family!", 1),)},
        {"family_counts": (("tool", True),)},
        {"progress_error_code": "live_progress_corrupt"},  # code on an available display
    ):
        with pytest.raises(SpineError) as exc:
            _rebuild(**overrides)
        assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY


# --------------------------------------------------------------------------- #
# H. No-leak — serialized display bytes never carry raw material
# --------------------------------------------------------------------------- #
def test_display_bytes_never_leak_canaries():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(
        ref, artifact_dir="/home/agent/tmp/var/secret/summary/body/stdout/token"
    )
    display = mod.display_task_live_progress(
        bindings, reg, port, _running_reader(), ref.task_id, ref.session_id,
        gate=_local_gate(),
    )
    assert scan_for_leak(display.as_dict()) is None
    encoded = mod.serialize_live_progress_display(display)
    for marker in (
        b"/home/",
        b"/tmp/",
        b"/var/",
        b"text",
        b"content",
        b"message",
        b"body",
        b"summary",
        b"stdout",
        b"stderr",
        b"prompt",
        b"tool_output",
        b"chat_id",
        b"open_id",
        b"token",
        b"secret",
        b"signed",
    ):
        assert marker not in encoded


# --------------------------------------------------------------------------- #
# I. Static source scan — no forbidden side-effect imports/calls in the module
# --------------------------------------------------------------------------- #
_FORBIDDEN_SIDE_EFFECT_TOKENS = (
    "subprocess",
    "os.system",
    ".popen(",
    "create_subprocess",
    "socket.socket",
    ".connect(",
    "import temporalio",
    "WorkflowEnvironment",
    "asyncio.create",
    "httpx",
    "requests.",
    "urllib",
    "docker",
    "im_send",
    "edit_message",
    "delivery_payload",
)


def test_display_module_wires_no_side_effect_or_delivery_surface():
    mod = _mod()
    source = Path(mod.__file__).read_text(encoding="utf-8")
    lowered = source.lower()
    assert [token for token in _FORBIDDEN_SIDE_EFFECT_TOKENS if token in lowered] == []
    # no top-level real supervisor / runner import
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
