"""PR-LS4-A — default-off runtime/query activation-gate acceptance tests.

Focused RED/GREEN tests for the LS4-A slice that adds a local/offline,
**default-off** query entrypoint ``query_task_live_progress`` over the PR-LS2
``LiveProgressSourceBindings`` + PR-LS1 ``AgentRunSupervisorLiveWorkbenchView``
composition.

The query is disabled unless the caller presents an explicit local/offline or
Hermes-internal :class:`LiveProgressQueryActivationGate`. A disabled query fails
closed with a stable code and never calls the injected live-progress reader,
never appends a ``TaskEventLog`` event, never updates binding cursor state, and
launches nothing. An enabled local/offline query resolves the binding, uses the
private ``artifact_dir`` only for the injected reader, and returns the safe
combined workbench view — the private path is never serialized/echoed.

Everything here stays pure local/offline Python over the deterministic in-memory
backend + in-test fake progress readers: no real AGENT / process / network /
durable service / listener is started, and no Gateway / Feishu / IM / delivery /
Temporal Worker surface is touched. Forbidden terms below are no-leak / denied
boundary canaries only, never behavior.
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
from sachima_supervisor.runtime_spine.agent_run_supervisor_live_workbench import (
    serialize_agent_run_supervisor_live_workbench_view,
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
        "sachima_supervisor.runtime_spine.live_progress_query"
    )


def _sources_mod():
    return importlib.import_module(
        "sachima_supervisor.runtime_spine.live_progress_sources"
    )


# --------------------------------------------------------------------------- #
# Workbench-side fixtures (mirrors test_live_progress_sources.py)
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
        self.page_calls: list = []

    def load_progress(self, artifact_dir):
        return self._p

    def read_event_page(self, artifact_dir, *, after_seq=None, limit=100):
        self.page_calls.append(after_seq)
        assert after_seq in self._pages, after_seq
        return self._pages[after_seq]


class _BoomReader:
    """A reader that raises internally — reader corruption must compose closed."""

    def __init__(self):
        self.load_dirs: list = []

    def load_progress(self, artifact_dir):
        self.load_dirs.append(artifact_dir)
        raise ValueError("corrupt-progress-internal-detail")

    def read_event_page(self, artifact_dir, *, after_seq=None, limit=100):
        raise ValueError("corrupt-page-internal-detail")


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


def _bindings_with(ref, *, artifact_dir=_PRIVATE_DIR, artifact_ref=_SAFE_HANDLE, last_seen_cursor=None):
    sources = _sources_mod()
    bindings = sources.LiveProgressSourceBindings()
    bindings.bind(
        ref.task_id, ref.session_id, artifact_dir, artifact_ref, last_seen_cursor=last_seen_cursor
    )
    return bindings


def _local_gate():
    return _mod().local_offline_query_gate()


# --------------------------------------------------------------------------- #
# A. Public surface + package exports
# --------------------------------------------------------------------------- #
def test_live_progress_query_public_surface_is_exported():
    mod = _mod()
    assert mod.RUNTIME_INVALID_LIVE_PROGRESS_QUERY == "runtime_invalid_live_progress_query"
    assert mod.RUNTIME_LIVE_PROGRESS_QUERY_DISABLED == "runtime_live_progress_query_disabled"
    assert mod.RUNTIME_INVALID_LIVE_PROGRESS_QUERY in mod.LIVE_PROGRESS_QUERY_STABLE_CODES
    assert mod.RUNTIME_LIVE_PROGRESS_QUERY_DISABLED in mod.LIVE_PROGRESS_QUERY_STABLE_CODES
    assert (
        mod.LIVE_PROGRESS_QUERY_GATE_TYPE
        == "sachima.runtime_spine.live_progress_query_activation_gate.v1"
    )
    assert mod.APPROVED_QUERY_SURFACES == frozenset({"local_offline", "hermes_internal"})
    for name in (
        "LiveProgressQueryActivationGate",
        "LiveProgressQueryService",
        "query_task_live_progress",
        "build_live_progress_query_activation_gate",
        "local_offline_query_gate",
        "hermes_internal_query_gate",
        "validate_live_progress_query_activation_gate",
    ):
        assert hasattr(mod, name), name


def test_symbols_available_from_runtime_spine_package():
    spine = importlib.import_module("sachima_supervisor.runtime_spine")
    for name in (
        "RUNTIME_INVALID_LIVE_PROGRESS_QUERY",
        "RUNTIME_LIVE_PROGRESS_QUERY_DISABLED",
        "LIVE_PROGRESS_QUERY_STABLE_CODES",
        "LIVE_PROGRESS_QUERY_GATE_TYPE",
        "APPROVED_QUERY_SURFACES",
        "LiveProgressQueryActivationGate",
        "LiveProgressQueryService",
        "query_task_live_progress",
        "build_live_progress_query_activation_gate",
        "local_offline_query_gate",
        "hermes_internal_query_gate",
        "validate_live_progress_query_activation_gate",
    ):
        assert hasattr(spine, name), name


# --------------------------------------------------------------------------- #
# B. Default-off: disabled query fails closed, reader untouched, no side effect
# --------------------------------------------------------------------------- #
def test_query_disabled_by_default_without_gate_fails_closed_and_reader_untouched():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    bindings = _bindings_with(ref, last_seen_cursor=3)
    reader = _running_reader()
    before_seq = reg.log.last_seq("task_alpha")
    before_sessions = port.session_count()

    with pytest.raises(SpineError) as exc:
        mod.query_task_live_progress(
            bindings, reg, port, reader, ref.task_id, ref.session_id
        )
    assert exc.value.code == mod.RUNTIME_LIVE_PROGRESS_QUERY_DISABLED

    # The disabled read never touched the reader / log / cursor / backend.
    assert reader.load_dirs == []
    assert reader.page_calls == []
    assert reg.log.last_seq("task_alpha") == before_seq
    assert port.session_count() == before_sessions
    assert bindings.resolve_source(ref).last_seen_cursor == 3


def test_query_disabled_when_gate_is_explicitly_none():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref)
    reader = _running_reader()
    with pytest.raises(SpineError) as exc:
        mod.query_task_live_progress(
            bindings, reg, port, reader, ref.task_id, ref.session_id, gate=None
        )
    assert exc.value.code == mod.RUNTIME_LIVE_PROGRESS_QUERY_DISABLED
    assert reader.load_dirs == []


def test_service_is_disabled_by_default():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref)
    reader = _running_reader()
    service = mod.LiveProgressQueryService(bindings, reg, port, reader)
    with pytest.raises(SpineError) as exc:
        service.query_task_live_progress(ref.task_id, ref.session_id)
    assert exc.value.code == mod.RUNTIME_LIVE_PROGRESS_QUERY_DISABLED
    assert reader.load_dirs == []


# --------------------------------------------------------------------------- #
# C. Activation gate value object — local/offline & hermes internal only
# --------------------------------------------------------------------------- #
def test_local_offline_and_hermes_internal_gates_build_and_validate():
    mod = _mod()
    for builder, surface in (
        (mod.local_offline_query_gate, "local_offline"),
        (mod.hermes_internal_query_gate, "hermes_internal"),
    ):
        gate = builder()
        assert type(gate) is mod.LiveProgressQueryActivationGate
        assert gate.type == mod.LIVE_PROGRESS_QUERY_GATE_TYPE
        assert gate.surface == surface
        assert gate.enabled is True
        assert mod.validate_live_progress_query_activation_gate(gate) is gate
        data = gate.as_dict()
        assert data["surface"] == surface
        assert data["enabled"] is True
        assert scan_for_leak(data) is None

    built = mod.build_live_progress_query_activation_gate("hermes_internal")
    assert built.surface == "hermes_internal"


def test_gate_rejects_denied_and_unknown_surfaces():
    mod = _mod()
    for surface in (
        "gateway",
        "gateway_route",
        "feishu_card",
        "im_delivery",
        "public_ingress",
        "temporal_worker",
        "production",
        "default_on",
        "live_stream",
        "unknown_surface",
        "LOCAL_OFFLINE",
    ):
        with pytest.raises(SpineError) as exc:
            mod.build_live_progress_query_activation_gate(surface)
        assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_QUERY
        assert surface not in str(exc.value)


def test_gate_direct_construction_of_denied_surface_fails_closed():
    mod = _mod()
    with pytest.raises(SpineError):
        mod.LiveProgressQueryActivationGate(
            type=mod.LIVE_PROGRESS_QUERY_GATE_TYPE, surface="gateway", enabled=True
        )
    # a non-True / non-bool enabled cannot pose as an activation
    with pytest.raises(SpineError):
        mod.LiveProgressQueryActivationGate(
            type=mod.LIVE_PROGRESS_QUERY_GATE_TYPE, surface="local_offline", enabled=False
        )
    with pytest.raises(SpineError):
        mod.LiveProgressQueryActivationGate(
            type=mod.LIVE_PROGRESS_QUERY_GATE_TYPE, surface="local_offline", enabled=1
        )
    # forged type
    with pytest.raises(SpineError):
        mod.LiveProgressQueryActivationGate(
            type="wrong.type", surface="local_offline", enabled=True
        )


def test_validate_rejects_forged_object_new_gate():
    mod = _mod()
    forged = object.__new__(mod.LiveProgressQueryActivationGate)
    object.__setattr__(forged, "type", mod.LIVE_PROGRESS_QUERY_GATE_TYPE)
    object.__setattr__(forged, "surface", "gateway")  # denied surface
    object.__setattr__(forged, "enabled", True)
    with pytest.raises(SpineError) as exc:
        mod.validate_live_progress_query_activation_gate(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_QUERY
    assert "gateway" not in str(exc.value)


def test_query_with_denied_gate_object_does_not_read():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref)
    reader = _running_reader()
    forged = object.__new__(mod.LiveProgressQueryActivationGate)
    object.__setattr__(forged, "type", mod.LIVE_PROGRESS_QUERY_GATE_TYPE)
    object.__setattr__(forged, "surface", "feishu_card")
    object.__setattr__(forged, "enabled", True)
    with pytest.raises(SpineError):
        mod.query_task_live_progress(
            bindings, reg, port, reader, ref.task_id, ref.session_id, gate=forged
        )
    assert reader.load_dirs == []
    assert reader.page_calls == []


# --------------------------------------------------------------------------- #
# D. Enabled local/offline query builds the combined live workbench view
# --------------------------------------------------------------------------- #
def test_enabled_local_offline_query_builds_combined_view():
    mod = _mod()
    from sachima_supervisor.runtime_spine.agent_run_supervisor_live_workbench import (
        AgentRunSupervisorLiveWorkbenchView,
    )

    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref, artifact_dir="/tmp/private/run/xyz")
    reader = _running_reader()

    view = mod.query_task_live_progress(
        bindings, reg, port, reader, ref.task_id, ref.session_id, gate=_local_gate()
    )
    assert type(view) is AgentRunSupervisorLiveWorkbenchView
    data = view.as_dict()
    assert data["task_id"] == "task_alpha"
    assert data["session_id"] == ref.session_id
    assert data["workbench"]["task_id"] == "task_alpha"
    assert data["progress_available"] is True
    assert data["live_progress"]["artifact_ref"] == _SAFE_HANDLE
    assert scan_for_leak(data) is None
    # artifact_dir went only to the reader, never into the view
    assert reader.load_dirs == ["/tmp/private/run/xyz"]
    assert reader.page_calls == [("/tmp/private/run/xyz", None)]


def test_enabled_query_via_service_with_hermes_internal_gate():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref)
    reader = _running_reader()
    service = mod.LiveProgressQueryService(
        bindings, reg, port, reader, gate=mod.hermes_internal_query_gate()
    )
    view = service.query_task_live_progress(ref.task_id, ref.session_id)
    data = view.as_dict()
    assert data["workbench"]["task_id"] == "task_alpha"
    assert data["progress_available"] is True
    assert scan_for_leak(data) is None


def test_query_by_task_id_session_id_pair_no_private_dir_leak():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref, artifact_dir="/tmp/private/run/leak_canary")
    reader = _running_reader()

    view = mod.query_task_live_progress(
        bindings, reg, port, reader, ref.task_id, ref.session_id, gate=_local_gate()
    )
    data = view.as_dict()
    assert scan_for_leak(data) is None
    encoded = serialize_agent_run_supervisor_live_workbench_view(view)
    assert type(encoded) is bytes
    for marker in (b"/tmp/", b"/home/", b"/var/", b"leak_canary", b"private"):
        assert marker not in encoded


# --------------------------------------------------------------------------- #
# E. after_seq override forwarded; absent after_seq uses last_seen_cursor
# --------------------------------------------------------------------------- #
def test_after_seq_override_is_forwarded_over_binding_cursor():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    page4 = _FakePage(
        (_rec(5, family="message", kind="assistant"),),
        next_cursor=5,
        has_more=False,
    )
    reader = _CursorAwareReader(_progress(last_seq=5, event_count=5), {4: page4})
    # binding cursor is 2, but the explicit after_seq=4 must win for this query
    bindings = _bindings_with(ref, last_seen_cursor=2)

    view = mod.query_task_live_progress(
        bindings, reg, port, reader, ref.task_id, ref.session_id,
        gate=_local_gate(), after_seq=4,
    )
    data = view.as_dict()
    assert reader.page_calls == [4]
    assert [r["seq"] for r in data["live_progress"]["records"]] == [5]
    # the explicit after_seq did not overwrite the stored binding cursor
    assert bindings.resolve_source(ref).last_seen_cursor == 2


def test_absent_after_seq_uses_binding_last_seen_cursor():
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
    bindings = _bindings_with(ref, last_seen_cursor=2)

    view = mod.query_task_live_progress(
        bindings, reg, port, reader, ref.task_id, ref.session_id, gate=_local_gate()
    )
    data = view.as_dict()
    assert reader.page_calls == [2]
    assert [r["seq"] for r in data["live_progress"]["records"]] == [3, 5]
    assert data["resume_cursor"] == 5
    assert data["has_more"] is True


# --------------------------------------------------------------------------- #
# F. Read-only: query updates neither binding cursor nor TaskEventLog
# --------------------------------------------------------------------------- #
def test_query_does_not_update_binding_cursor_or_event_log():
    mod = _mod()
    reg, backend, port, ref = _running_port()
    bindings = _bindings_with(ref, last_seen_cursor=None)
    before_seq = reg.log.last_seq("task_alpha")
    before_sessions = backend.session_count()

    for _ in range(3):
        view = mod.query_task_live_progress(
            bindings, reg, port, _running_reader(), ref.task_id, ref.session_id,
            gate=_local_gate(),
        )
        # the freshly observed frontier is surfaced but not silently committed
        assert view.as_dict()["resume_cursor"] == 3
        assert bindings.resolve_source(ref).last_seen_cursor is None

    assert reg.log.last_seq("task_alpha") == before_seq
    assert backend.session_count() == before_sessions
    assert port.session_count() == 1


# --------------------------------------------------------------------------- #
# G. Missing / mismatched / forged / unsafe inputs fail closed, no raw echo
# --------------------------------------------------------------------------- #
def test_query_missing_binding_fails_closed_reader_untouched():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _sources_mod().LiveProgressSourceBindings()  # nothing bound
    reader = _running_reader()
    with pytest.raises(SpineError) as exc:
        mod.query_task_live_progress(
            bindings, reg, port, reader, ref.task_id, ref.session_id, gate=_local_gate()
        )
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_QUERY
    assert reader.load_dirs == []


def test_query_mismatched_session_fails_closed():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref)
    with pytest.raises(SpineError) as exc:
        mod.query_task_live_progress(
            bindings, reg, port, _running_reader(), "task_alpha", "sess_not_bound",
            gate=_local_gate(),
        )
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_QUERY


def test_query_forged_session_untracked_by_port_fails_closed_no_echo():
    mod = _mod()
    reg, _backend, port, _ref = _running_port()
    forged_ref = SessionRef(task_id="task_alpha", session_id="sess_forged")
    bindings = _bindings_with(forged_ref)  # bound so resolve passes
    with pytest.raises(SpineError) as exc:
        mod.query_task_live_progress(
            bindings, reg, port, _running_reader(), "task_alpha", "sess_forged",
            gate=_local_gate(),
        )
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_QUERY
    assert "sess_forged" not in str(exc.value)


def test_query_rejects_unsafe_task_id_and_session_id():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref)
    reader = _running_reader()
    for task_id, session_id in (
        ("Task-Alpha", ref.session_id),
        ("../etc", ref.session_id),
        ("task_alpha", "session_no_prefix"),
        ("task_alpha", "sess with space"),
        ("task_alpha", "/tmp/run"),
    ):
        with pytest.raises(SpineError) as exc:
            mod.query_task_live_progress(
                bindings, reg, port, reader, task_id, session_id, gate=_local_gate()
            )
        assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_QUERY
        assert str(task_id) not in str(exc.value)
        assert str(session_id) not in str(exc.value)
    assert reader.load_dirs == []


def test_query_rejects_unsafe_after_seq_and_limit():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref)
    reader = _running_reader()
    for after_seq in (True, -1, 1.5, "3", 10**12):
        with pytest.raises(SpineError) as exc:
            mod.query_task_live_progress(
                bindings, reg, port, reader, ref.task_id, ref.session_id,
                gate=_local_gate(), after_seq=after_seq,
            )
        assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_QUERY
    for limit in (0, -5, True, 1001, "100", 2.0):
        with pytest.raises(SpineError) as exc:
            mod.query_task_live_progress(
                bindings, reg, port, reader, ref.task_id, ref.session_id,
                gate=_local_gate(), limit=limit,
            )
        assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_QUERY
    assert reader.load_dirs == []


def test_query_rejects_non_bindings_object():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    with pytest.raises(SpineError) as exc:
        mod.query_task_live_progress(
            {}, reg, port, _running_reader(), ref.task_id, ref.session_id, gate=_local_gate()
        )
    assert exc.value.code == mod.RUNTIME_INVALID_LIVE_PROGRESS_QUERY


# --------------------------------------------------------------------------- #
# H. Reader corruption composes fail-closed without leaking raw material
# --------------------------------------------------------------------------- #
def test_reader_corruption_composes_unavailable_without_leak():
    mod = _mod()
    from sachima_supervisor.runtime_spine.live_progress_projection import (
        LIVE_PROGRESS_STABLE_CODES,
    )

    reg, _backend, port, ref = _running_port()
    bindings = _bindings_with(ref)
    view = mod.query_task_live_progress(
        bindings, reg, port, _BoomReader(), ref.task_id, ref.session_id, gate=_local_gate()
    )
    data = view.as_dict()
    # corrupt live progress is an observation, not a raised exception
    assert data["progress_available"] is False
    assert data["progress_error_code"] in LIVE_PROGRESS_STABLE_CODES
    assert data["workbench"]["task_id"] == "task_alpha"
    assert scan_for_leak(data) is None
    encoded = serialize_agent_run_supervisor_live_workbench_view(view)
    for marker in (b"corrupt-progress-internal-detail", b"corrupt-page-internal-detail"):
        assert marker not in encoded


# --------------------------------------------------------------------------- #
# I. No-leak byte scan over a canary-laden private dir
# --------------------------------------------------------------------------- #
def test_query_result_bytes_never_leak_canaries():
    mod = _mod()
    reg, _backend, port, ref = _running_port()
    # a private dir stuffed with every no-leak canary the gate must keep private
    bindings = _bindings_with(
        ref, artifact_dir="/home/agent/tmp/var/secret/summary/body/stdout/token"
    )
    view = mod.query_task_live_progress(
        bindings, reg, port, _running_reader(), ref.task_id, ref.session_id, gate=_local_gate()
    )
    assert scan_for_leak(view.as_dict()) is None
    encoded = serialize_agent_run_supervisor_live_workbench_view(view)
    # ``text`` is intentionally omitted: the safe ``text_length`` field name (an int
    # length signal, never raw text) legitimately contains that substring and is
    # allowed by the spine's own no-leak scan. Every other canary must be absent.
    for marker in (
        b"/home/",
        b"/tmp/",
        b"/var/",
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
# J. Static source scan — no forbidden side-effect imports/calls in the module
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


def test_query_module_wires_no_side_effect_or_delivery_surface():
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
