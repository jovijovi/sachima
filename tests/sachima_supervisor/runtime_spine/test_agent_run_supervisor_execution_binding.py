"""One-call ``arsd`` execution binding bundle (port + dispatcher + display).

Tests for :func:`bind_arsd_execution`: the composition root that builds the
full seam (registry + the ``arsd`` backend + port + turn dispatcher + source
bindings + LS4-A-gated query service + display service) from one validated,
explicitly enabled config.

The retired ``library`` composition root this file used to cover is gone (plan
P5, seam S-1), and with it any path that could compose one. Default-off posture
is preserved at every layer: a disabled config refuses to compose, a composed
bundle without an explicit activation gate keeps the query/display chain
fail-closed, and composing a bundle submits **no** Run. Pure local/offline: the
daemon is reached only through an injected facade double, so no test opens a
socket, starts a daemon, reaches the network, or launches a real AGENT.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sachima_supervisor.runtime_spine import (
    RUNTIME_INVALID_SESSION,
    RUNTIME_LIVE_PROGRESS_QUERY_DISABLED,
    SpineError,
    build_launch_spec,
    hermes_internal_query_gate,
    scan_for_leak,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
    AgentRunSupervisorExecutionBinding,
    bind_arsd_execution,
)
from sachima_supervisor.runtime_spine import LiveProgressSourceBindings, TaskRegistry
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import ArsdRunBindingLedger
from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    ARSD_SUPERVISOR_CONFIG_TYPE,
    RUNTIME_ARSD_DISABLED,
    ArsdSupervisorConfig,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    AgentRunSupervisorPort,
)
from sachima_supervisor.runtime_spine.live_progress_display import (
    LiveProgressDisplayService,
)
from sachima_supervisor.runtime_spine.live_progress_query import (
    LiveProgressQueryService,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher import (
    AgentRunSupervisorTurnDispatcher,
)
from sachima_supervisor.runtime_spine.arsd_supervisor_backend import (
    ArsdLiveProgressReader,
    ArsdSupervisorBackend,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher import (
    RUNTIME_INVALID_TURN_DISPATCH,
    TurnDispatchRequest,
)

# --------------------------------------------------------------------------- #
# Rig: an enabled config + a facade double that answers real event pages
# --------------------------------------------------------------------------- #
_REFS = ("ws_arsint", "policy_agent", "policy_model", "policy_effort", "policy_limits")
_SOCKET_CANARY = "/srv/private/sachima-arsd.sock"
_RUN_ID_CANARY = "RUN-binding-canary-7c1e"
_ARS_SESSION_CANARY = "SESSBINDINGCANARY7c1e"
_ACCEPTED_AT = "2026-08-17T04:05:06+00:00"

#: The canonical roster the fake daemon reports, in the daemon's own
#: ``tuple(sorted(entries))`` order.
REGISTERED_AGENT_IDS = ("claude", "codex", "cursor", "oh-my-pi", "opencode")

V3_OPERATIONS = [
    "agent_list",
    "run_cancel",
    "run_events",
    "run_status",
    "server_info",
    "session_list",
    "session_status",
    "submit",
]


def _config(tmp_path: Path, *, enabled: bool = True) -> ArsdSupervisorConfig:
    work = tmp_path / "work"
    work.mkdir(parents=True, exist_ok=True)
    return ArsdSupervisorConfig(
        type=ARSD_SUPERVISOR_CONFIG_TYPE,
        approval_ref="approval_arsd_binding_offline",
        owner="sachima_host",
        namespace="sachima_tasks",
        socket_path=_SOCKET_CANARY,
        binding_ledger_path=str(tmp_path / "arsd-run-bindings.json"),
        agent_by_policy_ref={"policy_agent": "reader-agent"},
        model_by_policy_ref={"policy_model": "claude-sonnet-5"},
        effort_by_policy_ref={"policy_effort": "medium"},
        workspace_by_ref={"ws_arsint": str(work)},
        run_limits_by_policy_ref={
            "policy_limits": {
                "startup_timeout_seconds": 60.0,
                "turn_timeout_seconds": 600.0,
                "cancel_grace_seconds": 10.0,
                "max_stderr_bytes": 262_144,
                "max_event_bytes": 65_536,
                "max_events": 10_000,
            }
        },
        grant_ref="grant_reader_v1",
        grant_hash="sha256:" + "a" * 64,
        grant_role_hash="sha256:" + "b" * 64,
        grant_capabilities=("read", "search"),
        mcp_snapshot_hashes=("sha256:" + "c" * 64,),
        credential_refs=("cred_reader_github",),
        evidence_policy_hash="sha256:" + "d" * 64,
        recovery_policy_hash="sha256:" + "e" * 64,
        enabled=enabled,
    )


class _FacadeDouble:
    """One in-memory daemon: it records what it was asked and answers pages."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.submitted: list[tuple[str, dict[str, Any]]] = []
        #: What ``run_status`` reports about a Run. ``None`` is "accepted, no
        #: terminal yet" — which the §7.4 exclusion reads as still running.
        self.run_status_payload: dict[str, Any] | None = None
        self.submit_error: BaseException | None = None
        self.admitted: dict[str, dict[str, Any]] = {}
        self._run_seq = 0

    def run_ended(self, status: str = "completed") -> None:
        """Trusted terminal truth, so the next turn may be admitted."""

        self.run_status_payload = {"result": {"status": status}}

    def _log(self, op: str) -> None:
        self.calls.append(op)

    def ops(self, op: str) -> int:
        return self.calls.count(op)

    def server_info(self) -> dict[str, Any]:
        self._log("server_info")
        return {
            "version": "0.7.8",
            "api_version": 3,
            "supported_api_versions": [3],
            "operations": list(V3_OPERATIONS),
            "limits": {
                "max_concurrent_runs": 4,
                "max_frame_bytes": 1_048_576,
                "max_prompt_bytes": 262_144,
                "events_page_limit": 256,
                "event_follow_queue_size": 1024,
                "max_run_event_budget_bytes": 2_147_483_648,
            },
        }

    def submit(self, *, request_id: str, payload: Any) -> dict[str, Any]:
        self._log("submit")
        self.submitted.append((request_id, json.loads(json.dumps(dict(payload)))))
        # The daemon records the admission BEFORE it answers, so a raise after
        # this point is a genuinely lost ack rather than a refused submission.
        if request_id not in self.admitted:
            self._run_seq += 1
            self.admitted[request_id] = {
                "run_id": f"{_RUN_ID_CANARY}-{self._run_seq}",
                "session_id": _ARS_SESSION_CANARY,
                "accepted_at": _ACCEPTED_AT,
            }
        if self.submit_error is not None:
            raise self.submit_error
        return dict(self.admitted[request_id])

    def run_status(self, run_id: str) -> dict[str, Any]:
        self._log("run_status")
        payload = dict(self.run_status_payload or {})
        payload["run_id"] = run_id
        payload.setdefault("session_id", _ARS_SESSION_CANARY)
        return payload

    def run_events(
        self, run_id: str, *, from_seq: int, limit: int | None = None
    ) -> dict[str, Any]:
        self._log("run_events")
        events: list[dict[str, Any]] = [
            {"seq": 1, "type": "run_started", "kind": "lifecycle", "status": "running",
             "text_length": 0, "summary": "never surfaced"},
            {"seq": 2, "type": "agent_message", "kind": "assistant", "status": "running",
             "text_length": 21, "summary": "never surfaced"},
        ]
        page = [event for event in events if int(event["seq"]) > from_seq]
        page = page[: (limit or 100)]
        return {
            "run_id": run_id,
            "events": page,
            "next_from_seq": int(page[-1]["seq"]) if page else from_seq,
            "exhausted": True,
        }

    def run_cancel(self, run_id: str) -> dict[str, Any]:
        self._log("run_cancel")
        return {"run_id": run_id}

    def session_status(self, session_id: str) -> dict[str, Any]:
        self._log("session_status")
        return {
            "session_id": session_id,
            "owner": "sachima_host",
            "namespace": "sachima_tasks",
            "agent_id": "reader-agent",
            "profile_id": None,
            "created_at": _ACCEPTED_AT,
            "updated_at": _ACCEPTED_AT,
            "last_effective_model": None,
            "last_effective_effort": None,
            "quarantine": None,
        }

    def session_list(self) -> dict[str, Any]:
        self._log("session_list")
        return {"sessions": []}

    def agent_list(self) -> dict[str, Any]:
        self._log("agent_list")
        return {"agent_ids": list(REGISTERED_AGENT_IDS)}


def _bundle(tmp_path: Path, *, gate=None, payload_resolver=None, reader=None):
    facade = _FacadeDouble()
    bundle = bind_arsd_execution(
        _config(tmp_path),
        gate=gate,
        payload_resolver=payload_resolver,
        facade=facade,
        ledger=ArsdRunBindingLedger(str(tmp_path / "ledger.json")),
        progress_reader=reader,
    )
    return bundle, facade


def _attach(bundle) -> Any:
    return bundle.port.create_or_attach(
        "task_alpha",
        build_launch_spec(
            task_id="task_alpha",
            agent_kind="local_agent",
            mode_flags={"needs_agent": True},
            roles=("read_only",),
            refs=_REFS,
        ),
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_disabled_config_refuses_to_compose(tmp_path: Path) -> None:
    with pytest.raises(SpineError) as exc:
        bind_arsd_execution(_config(tmp_path, enabled=False), facade=_FacadeDouble())
    assert exc.value.code == RUNTIME_ARSD_DISABLED


def test_the_retired_library_composition_root_is_gone() -> None:
    import sachima_supervisor.runtime_spine as spine
    import sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding as mod

    assert not hasattr(mod, "bind_agent_run_supervisor_execution")
    assert not hasattr(spine, "bind_agent_run_supervisor_execution")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for retired in ("AgentRunSupervisorLibraryBackend", "AgentRunSupervisorLibraryConfig"):
        assert retired not in src, retired


def test_bundle_composes_shared_spine_objects(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    assert isinstance(bundle, AgentRunSupervisorExecutionBinding)
    assert bundle.query_service.bindings is bundle.bindings
    assert bundle.query_service.registry is bundle.registry
    assert bundle.query_service.port is bundle.port
    assert bundle.display_service.query_service is bundle.query_service


def test_composing_the_display_service_submits_no_run(tmp_path: Path) -> None:
    """A composed host has not started work — it has only proven the contract."""

    bundle, facade = _bundle(tmp_path, gate=hermes_internal_query_gate())
    assert facade.submitted == []
    assert facade.ops("submit") == 0
    # Composition negotiates the contract, and does nothing else on the wire.
    assert facade.calls == ["server_info"]
    # Even attaching a task submits nothing: a Session is not a Run.
    _attach(bundle)
    assert facade.ops("submit") == 0


def test_the_default_read_model_is_the_arsd_reader(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    assert isinstance(bundle.query_service.progress_reader, ArsdLiveProgressReader)


def test_bundle_admits_a_backend_only_through_the_factory_allowlist(tmp_path: Path) -> None:
    """``__post_init__`` names no concrete backend class — it validates one."""

    class _ProtocolShapedBackend:
        def create_or_attach(self, task_id, refs): ...
        def attach_existing(self, task_id): ...
        def run_turn(self, task_id, *, turn_kind, payload_text, dispatch_ref, payload_ref): ...
        def recover_uncertain_submission(self, task_id, dispatch_ref): ...
        def latest_accepted_turn(self, task_id): ...
        def status(self, handle): ...
        def signal(self, handle, decision_ref): ...
        def kill(self, handle, reason_ref): ...
        def liveness(self, handle): ...

    # The bundle itself names no concrete backend class; only the factory
    # below it may, which is precisely what an exact-type allowlist is for.
    bundle_source = inspect.getsource(AgentRunSupervisorExecutionBinding)
    assert "ArsdSupervisorBackend" not in bundle_source

    bundle, _ = _bundle(tmp_path)
    fields = {f.name: getattr(bundle, f.name) for f in dataclasses.fields(bundle)}
    for refused in (_ProtocolShapedBackend(), None, object()):
        with pytest.raises(SpineError) as exc:
            AgentRunSupervisorExecutionBinding(**{**fields, "backend": refused})
        assert exc.value.code == RUNTIME_INVALID_SESSION


def test_query_chain_stays_default_off_without_gate(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    with pytest.raises(SpineError) as exc:
        bundle.query_service.query_task_live_progress("task_alpha", "sess_1")
    assert exc.value.code == RUNTIME_LIVE_PROGRESS_QUERY_DISABLED


def test_dispatch_stays_fail_closed_without_payload_resolver(tmp_path: Path) -> None:
    bundle, facade = _bundle(tmp_path, gate=hermes_internal_query_gate())
    ref = _attach(bundle)
    request = TurnDispatchRequest(
        task_id="task_alpha",
        session_id=ref.session_id,
        turn_kind="goal",
        payload_ref="payload_goal_1",
    )
    with pytest.raises(SpineError) as exc:
        bundle.dispatcher.dispatch(request)
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH
    # Fail-closed means nothing was sent, not that nothing was answered.
    assert facade.ops("submit") == 0


def test_dispatched_turn_feeds_display_chain_end_to_end(tmp_path: Path) -> None:
    payloads = {"payload_goal_1": "ship the integration"}
    bundle, facade = _bundle(
        tmp_path, gate=hermes_internal_query_gate(), payload_resolver=payloads.__getitem__
    )
    ref = _attach(bundle)
    outcome = bundle.dispatcher.dispatch(
        TurnDispatchRequest(
            task_id="task_alpha",
            session_id=ref.session_id,
            turn_kind="goal",
            payload_ref="payload_goal_1",
        )
    )
    assert outcome.supervisor_status == "accepted"
    assert facade.ops("submit") == 1

    display = bundle.display_service.display_task_live_progress(
        "task_alpha", ref.session_id
    )
    payload = display.as_dict()
    assert payload["task_id"] == "task_alpha"
    assert payload["session_id"] == ref.session_id
    assert payload["artifact_ref"] == outcome.artifact_ref
    assert payload["progress_available"] is True
    assert payload["observed_event_count"] == 2
    assert isinstance(payload["display_lines"], list) and payload["display_lines"]

    # Refs, counts and coarse tokens only — never the private run id, the
    # socket path, the prompt, or remote free text.
    assert scan_for_leak(payload) is None
    rendered = json.dumps(payload)
    for canary in (_RUN_ID_CANARY, _ARS_SESSION_CANARY, _SOCKET_CANARY, "never surfaced"):
        assert canary not in rendered, canary
    assert str(tmp_path) not in rendered


def test_two_turns_run_in_one_ars_session_without_the_task_going_terminal(
    tmp_path: Path,
) -> None:
    """The end-to-end multi-turn regression, through the composed seam.

    Same Sachima task and Session: the first Run completes, the second turn
    dispatches, exactly two Runs are submitted, and the second request reuses
    the one ARS Session verbatim. The task stays nonterminal throughout —
    a Run ending is not a Session ending, and ARS has no Session close — and
    each turn keeps its own turn ref and its own read-model cursor.
    """

    payloads = {"payload_turn_1": "ship the integration", "payload_turn_2": "now review it"}
    bundle, facade = _bundle(
        tmp_path, gate=hermes_internal_query_gate(), payload_resolver=payloads.__getitem__
    )
    ref = _attach(bundle)

    def _dispatch(payload_ref: str):
        return bundle.dispatcher.dispatch(
            TurnDispatchRequest(
                task_id="task_alpha",
                session_id=ref.session_id,
                turn_kind="prompt",
                payload_ref=payload_ref,
            )
        )

    first = _dispatch("payload_turn_1")
    assert first.supervisor_status == "accepted"
    assert bundle.port.status(ref).terminal is False

    # The caller reads the first turn's stream and advances its cursor.
    display = bundle.display_service.display_task_live_progress("task_alpha", ref.session_id)
    assert display.as_dict()["observed_event_count"] == 2
    bundle.bindings.update_last_seen_cursor("task_alpha", 2, ref.session_id)

    # The first Run ends. The task does not.
    facade.run_ended()
    status_between = bundle.port.status(ref)
    assert status_between.state == "running"
    assert status_between.terminal is False
    assert status_between.alive is True
    assert bundle.registry.snapshot("task_alpha")["terminal"] is False

    second = _dispatch("payload_turn_2")
    assert second.supervisor_status == "accepted"

    # Exactly two Runs, one ARS Session, and the second request reuses it.
    assert facade.ops("submit") == 2
    (_first_id, first_payload), (_second_id, second_payload) = facade.submitted
    assert "session_id" not in first_payload["request"]  # create by omission
    assert second_payload["request"]["session_id"] == _ARS_SESSION_CANARY
    assert first_payload["prompt_text"] == "ship the integration"
    assert second_payload["prompt_text"] == "now review it"

    # Distinct turn refs, and a cursor that did not bleed across the turns.
    assert first.turn_ref != second.turn_ref
    source = bundle.bindings.resolve_source("task_alpha", ref.session_id)
    assert source.artifact_ref == second.turn_ref
    assert source.last_seen_cursor is None
    assert bundle.bindings.resolve("task_alpha", ref.session_id).artifact_dir == (
        f"{_RUN_ID_CANARY}-2"
    )

    # Still nonterminal after the second turn, and still one Session.
    assert bundle.port.status(ref).terminal is False
    assert bundle.registry.snapshot("task_alpha")["terminal"] is False


class _TransportLoss(Exception):
    """A local transport failure the official client would raise, doubled."""


def test_a_lost_ack_is_recovered_through_the_composed_seam(tmp_path: Path) -> None:
    """The composed path can finish what an uncertain submit started.

    This is what the claim-check ref buys: the dispatcher hands the backend
    one ref that is both the durable dispatch identity and the persisted
    prompt ref, so a recovery resolves the exact prompt through the same
    injected resolver without any caller holding the text.
    """

    payloads = {"payload_turn_1": "ship the integration"}
    resolved: list[str] = []

    def _resolver(payload_ref: str) -> str:
        resolved.append(payload_ref)
        return payloads[payload_ref]

    bundle, facade = _bundle(
        tmp_path, gate=hermes_internal_query_gate(), payload_resolver=_resolver
    )
    ref = _attach(bundle)
    request = TurnDispatchRequest(
        task_id="task_alpha",
        session_id=ref.session_id,
        turn_kind="prompt",
        payload_ref="payload_turn_1",
    )

    facade.submit_error = _TransportLoss("reply never read")
    lost = bundle.dispatcher.dispatch(request)
    assert lost.error_code is not None
    assert facade.ops("submit") == 1

    facade.submit_error = None
    recovered = bundle.dispatcher.recover_dispatch(request)
    assert recovered.error_code is None
    assert recovered.supervisor_status == "accepted"

    # The resend was the identical frozen payload under the same request id.
    assert facade.ops("submit") == 2
    assert facade.submitted[0][0] == facade.submitted[1][0]
    assert facade.submitted[0][1] == facade.submitted[1][1]
    # Resolved through the injected resolver, by the request's own ref.
    assert resolved == ["payload_turn_1", "payload_turn_1"]

    # And it published like any acceptance: the display chain can read it.
    display = bundle.display_service.display_task_live_progress("task_alpha", ref.session_id)
    payload = display.as_dict()
    assert payload["artifact_ref"] == recovered.turn_ref
    assert payload["progress_available"] is True
    assert scan_for_leak(payload) is None
    assert _RUN_ID_CANARY not in json.dumps(payload)


def test_a_recomposed_bundle_rehydrates_the_accepted_run_without_submitting(
    tmp_path: Path,
) -> None:
    """A restart reads the live Run's stream; it does not start another.

    The composition root accepts the registry and bindings a host already
    holds, so persisted Sachima task/session state and the durable ledger can
    be reconciled instead of a second, empty spine being invented beside them.
    """

    payloads = {"payload_turn_1": "ship the integration"}
    bundle, facade = _bundle(
        tmp_path, gate=hermes_internal_query_gate(), payload_resolver=payloads.__getitem__
    )
    ref = _attach(bundle)
    first = bundle.dispatcher.dispatch(
        TurnDispatchRequest(
            task_id="task_alpha",
            session_id=ref.session_id,
            turn_kind="prompt",
            payload_ref="payload_turn_1",
        )
    )
    assert facade.ops("submit") == 1

    # A brand-new process over the same durable ledger, and the host's own
    # registry/bindings handed in rather than re-invented.
    fresh_registry = TaskRegistry()
    fresh_bindings = LiveProgressSourceBindings()
    fresh_facade = _FacadeDouble()
    fresh = bind_arsd_execution(
        _config(tmp_path),
        gate=hermes_internal_query_gate(),
        facade=fresh_facade,
        ledger=ArsdRunBindingLedger(str(tmp_path / "ledger.json")),
        registry=fresh_registry,
        bindings=fresh_bindings,
    )
    assert fresh.registry is fresh_registry
    assert fresh.bindings is fresh_bindings
    fresh_ref = _attach(fresh)
    calls_before = list(fresh_facade.calls)

    turn_ref = fresh.dispatcher.rehydrate_source_binding("task_alpha", fresh_ref.session_id)
    assert turn_ref == first.turn_ref

    # A usable read-model source, straight from the ledger: no submit, no
    # daemon operation, no fabricated task state.
    assert fresh_facade.ops("submit") == 0
    assert fresh_facade.calls == calls_before
    display = fresh.display_service.display_task_live_progress(
        "task_alpha", fresh_ref.session_id
    )
    payload = display.as_dict()
    assert payload["artifact_ref"] == turn_ref
    assert payload["progress_available"] is True
    assert payload["observed_event_count"] == 2
    assert scan_for_leak(payload) is None


# --------------------------------------------------------------------------- #
# The composed graph is one graph — checked by identity, not by type
# --------------------------------------------------------------------------- #
def _second_spine(tmp_path: Path):
    """A whole second, valid spine — every part a different object."""

    facade = _FacadeDouble()
    backend = ArsdSupervisorBackend(
        _config(tmp_path / "other"),
        facade,
        ArsdRunBindingLedger(str(tmp_path / "other-ledger.json")),
    )
    registry = TaskRegistry()
    port = AgentRunSupervisorPort(registry, backend)
    bindings = LiveProgressSourceBindings()
    dispatcher = AgentRunSupervisorTurnDispatcher(
        port, backend, bindings, registry, lambda ref: "x"
    )
    query_service = LiveProgressQueryService(
        bindings, registry, port, ArsdLiveProgressReader(facade)
    )
    return SimpleNamespace(
        backend=backend,
        registry=registry,
        port=port,
        bindings=bindings,
        dispatcher=dispatcher,
        query_service=query_service,
        display_service=LiveProgressDisplayService(query_service=query_service),
    )


def test_a_composed_bundle_is_one_graph_sharing_one_lock_provider(
    tmp_path: Path,
) -> None:
    """Every part is the same object as every other part's view of it."""

    bundle, facade = _bundle(tmp_path, gate=hermes_internal_query_gate())

    assert bundle.dispatcher.backend is bundle.backend
    assert bundle.dispatcher.port is bundle.port
    assert bundle.dispatcher.registry is bundle.registry
    assert bundle.dispatcher.bindings is bundle.bindings
    assert bundle.port._backend is bundle.backend
    assert bundle.port._registry is bundle.registry
    # One task operation lock provider across the whole graph — the invariant
    # that makes admission and publication one section.
    assert bundle.dispatcher.task_locks is bundle.backend.task_locks
    assert facade.ops("submit") == 0


@pytest.mark.parametrize(
    "swapped",
    ["backend", "port", "registry", "bindings", "dispatcher"],
)
def test_a_bundle_assembled_from_two_graphs_fails_closed(
    tmp_path: Path, swapped: str
) -> None:
    """A part from another spine is refused, by identity and not by type.

    Every substitute here is a perfectly valid object of exactly the right
    type — which is the point. Type checks admit a graph whose dispatcher
    guards one lock provider while its backend guards another, and that graph
    is precisely the one where a cancel can interleave with a publication.
    """

    bundle, _facade = _bundle(tmp_path, gate=hermes_internal_query_gate())
    other = _second_spine(tmp_path)
    fields = {f.name: getattr(bundle, f.name) for f in dataclasses.fields(bundle)}
    fields[swapped] = getattr(other, swapped)

    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorExecutionBinding(**fields)
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_the_composed_graph_dispatches_on_a_real_executor(tmp_path: Path) -> None:
    """The enforced graph is the one that actually works, end to end."""

    payloads = {"payload_turn_1": "ship the integration"}
    pool = ThreadPoolExecutor(max_workers=1)
    facade = _FacadeDouble()
    bundle = bind_arsd_execution(
        _config(tmp_path),
        gate=hermes_internal_query_gate(),
        payload_resolver=payloads.__getitem__,
        facade=facade,
        ledger=ArsdRunBindingLedger(str(tmp_path / "ledger.json")),
        executor=pool,
    )
    ref = bundle.port.create_or_attach(
        "task_alpha",
        build_launch_spec(
            task_id="task_alpha",
            agent_kind="local_agent",
            mode_flags={"needs_agent": True},
            roles=("read_only",),
            refs=_REFS,
        ),
    )
    box: dict[str, Any] = {}

    def _run() -> None:
        box["outcome"] = bundle.dispatcher.dispatch(
            TurnDispatchRequest(
                task_id="task_alpha",
                session_id=ref.session_id,
                turn_kind="prompt",
                payload_ref="payload_turn_1",
            )
        )

    thread = threading.Thread(target=_run)
    thread.start()
    thread.join(timeout=10.0)
    try:
        assert not thread.is_alive(), "the composed dispatch deadlocked"
    finally:
        pool.shutdown(wait=True)

    assert box["outcome"].error_code is None
    assert facade.ops("submit") == 1
    assert bundle.dispatcher.task_locks is bundle.backend.task_locks

    # ...and the read chain the identity checks admitted really does read it.
    display = bundle.display_service.display_task_live_progress(
        "task_alpha", ref.session_id
    )
    payload = display.as_dict()
    assert payload["artifact_ref"] == box["outcome"].turn_ref
    assert payload["progress_available"] is True
    assert payload["observed_event_count"] == 2
    assert scan_for_leak(payload) is None


def _read_model(bundle) -> Any:
    """The reader a bundle's own query service uses."""

    return bundle.query_service.progress_reader


@pytest.mark.parametrize(
    "forge",
    [
        "display_only",
        "query_and_display",
        "query_with_foreign_bindings",
        "query_with_foreign_registry",
        "query_with_foreign_port",
    ],
)
def test_a_bundle_whose_read_chain_belongs_to_another_graph_fails_closed(
    tmp_path: Path, forge: str
) -> None:
    """The read chain has to be reading THIS bundle's spine.

    A display service that renders another bundle's query service, or a query
    service pointed at another bundle's bindings/registry/port, type-checks
    perfectly and answers about a different conversation: it would read a Run
    this task never dispatched, or miss the one it did. The mixed cases are the
    subtle ones — a query service built from this graph's parts with exactly
    one foreign — and the coherent ``query_and_display`` pair is subtler still,
    because it is internally consistent and only disagrees with the bundle.
    """

    bundle, facade = _bundle(tmp_path, gate=hermes_internal_query_gate())
    other = _second_spine(tmp_path)
    fields = {f.name: getattr(bundle, f.name) for f in dataclasses.fields(bundle)}

    if forge == "display_only":
        fields["display_service"] = other.display_service
    elif forge == "query_and_display":
        fields["query_service"] = other.query_service
        fields["display_service"] = other.display_service
    else:
        parts = {
            "bindings": bundle.bindings,
            "registry": bundle.registry,
            "port": bundle.port,
        }
        parts[forge.removeprefix("query_with_foreign_")] = getattr(
            other, forge.removeprefix("query_with_foreign_")
        )
        forged_query = LiveProgressQueryService(
            parts["bindings"],
            parts["registry"],
            parts["port"],
            _read_model(bundle),
            gate=hermes_internal_query_gate(),
        )
        fields["query_service"] = forged_query
        fields["display_service"] = LiveProgressDisplayService(
            query_service=forged_query
        )

    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorExecutionBinding(**fields)
    assert exc.value.code == RUNTIME_INVALID_SESSION

    # Refused at construction: nothing was dispatched, queried, or submitted.
    assert facade.ops("submit") == 0
    assert facade.ops("run_events") == 0


def test_a_composed_bundle_read_chain_is_this_bundles_own(tmp_path: Path) -> None:
    """The positive control for the whole read chain, by identity."""

    bundle, _facade = _bundle(tmp_path, gate=hermes_internal_query_gate())
    assert bundle.query_service.bindings is bundle.bindings
    assert bundle.query_service.registry is bundle.registry
    assert bundle.query_service.port is bundle.port
    assert bundle.display_service.query_service is bundle.query_service
