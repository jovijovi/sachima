"""One-call ``arsd`` execution binding bundle (port + dispatcher + sink).

Tests for :func:`bind_arsd_execution`: the composition root that builds the
execution seam (registry + the ``arsd`` backend + port + turn dispatcher +
the host's read-model source sink) from one validated, explicitly enabled
config.

The retired ``library`` composition root this file used to cover is gone (plan
P5, seam S-1), and with it any path that could compose one. Default-off posture
is preserved at every layer: a disabled config refuses to compose, the seam
composes no query or display surface at all, and composing a bundle submits
**no** Run. Pure local/offline: the daemon is reached only through an injected
facade double, so no test opens a socket, starts a daemon, reaches the
network, or launches a real AGENT.
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
    SpineError,
    build_launch_spec,
    scan_for_leak,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
    AgentRunSupervisorExecutionBinding,
    bind_arsd_execution,
)
from sachima_supervisor.runtime_spine import TaskRegistry
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import ArsdRunBindingLedger
from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    ARSD_SUPERVISOR_CONFIG_TYPE,
    RUNTIME_ARSD_DISABLED,
    ArsdSupervisorConfig,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    AgentRunSupervisorPort,
)
from sachima_supervisor.runtime_spine import supervisor_turn_backend as turns
from sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher import (
    AgentRunSupervisorTurnDispatcher,
)
from sachima_supervisor.runtime_spine.arsd_supervisor_backend import (
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


class _SourceSinkDouble:
    """A ``TurnSourceSink`` double — the contract the dispatcher publishes into.

    The execution seam composes a sink it does not implement, so these tests
    exercise the contract rather than any one read-model implementation. It
    keeps only what the identity assertions below need.
    """

    def __init__(self) -> None:
        self.bound: dict[tuple[str, str], tuple[str, str, str, int | None]] = {}

    def bind_source(
        self,
        task_id: str,
        session_id: str,
        source_kind: str,
        private_locator: str,
        artifact_ref: str,
        *,
        last_seen_cursor: int | None = None,
    ) -> None:
        self.bound[(task_id, session_id)] = (
            source_kind,
            private_locator,
            artifact_ref,
            last_seen_cursor,
        )

    def update_last_seen_cursor(
        self, task_id: str, cursor: int, session_id: str
    ) -> None:
        kind, locator, ref, _ = self.bound[(task_id, session_id)]
        self.bound[(task_id, session_id)] = (kind, locator, ref, cursor)

    def artifact_ref(self, task_id: str, session_id: str) -> str:
        return self.bound[(task_id, session_id)][2]


@pytest.fixture(autouse=True)
def _admit_the_sink_double(monkeypatch: pytest.MonkeyPatch) -> None:
    """Admit the double through the sink's own exact-type factory allowlist.

    The production admission gate is not weakened: the double is admitted by
    being *named* in the allowlist, exactly as a real sink is, so every
    composition below still passes ``validate_turn_source_sink``.
    """

    monkeypatch.setattr(
        turns,
        "_SOURCE_SINK_FACTORY_ALLOWLIST",
        (("test_double", __name__, "_SourceSinkDouble"),),
    )


def _bundle(tmp_path: Path, *, payload_resolver=None, bindings=None):
    facade = _FacadeDouble()
    bundle = bind_arsd_execution(
        _config(tmp_path),
        payload_resolver=payload_resolver,
        facade=facade,
        ledger=ArsdRunBindingLedger(str(tmp_path / "ledger.json")),
        bindings=_SourceSinkDouble() if bindings is None else bindings,
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
    assert bundle.dispatcher.registry is bundle.registry
    assert bundle.dispatcher.port is bundle.port
    assert bundle.dispatcher.bindings is bundle.bindings
    assert bundle.port._registry is bundle.registry


def test_composing_the_bundle_submits_no_run(tmp_path: Path) -> None:
    """A composed host has not started work — it has only proven the contract."""

    bundle, facade = _bundle(tmp_path)
    assert facade.submitted == []
    assert facade.ops("submit") == 0
    # Composition negotiates the contract, and does nothing else on the wire.
    assert facade.calls == ["server_info"]
    # Even attaching a task submits nothing: a Session is not a Run.
    _attach(bundle)
    assert facade.ops("submit") == 0


def test_the_execution_seam_composes_no_query_or_display_surface(
    tmp_path: Path,
) -> None:
    """Composing execution never brings a read/query surface with it.

    The LS4 query gate and the display renderer are a separately approved,
    default-off surface that *extends* this bundle. A composition root that
    built them itself would make "compose the execution seam" and "expose a
    live-progress surface" the same act, which is exactly the coupling the
    separate approval exists to prevent.
    """

    bundle, _ = _bundle(tmp_path)
    for surface in ("query_service", "display_service", "progress_reader"):
        assert not hasattr(bundle, surface), surface

    import sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    for token in ("LiveProgressQueryService", "LiveProgressDisplayService"):
        assert token not in src, token


def test_an_execution_only_bundle_composes_without_a_sink(tmp_path: Path) -> None:
    """No read model composed means no sink — not an invented empty one."""

    facade = _FacadeDouble()
    bundle = bind_arsd_execution(
        _config(tmp_path),
        facade=facade,
        ledger=ArsdRunBindingLedger(str(tmp_path / "ledger.json")),
    )
    assert bundle.bindings is None
    assert bundle.dispatcher.bindings is None
    assert facade.ops("submit") == 0


def test_the_sink_is_admitted_only_through_the_factory_allowlist(
    tmp_path: Path,
) -> None:
    """A sink is exact-type admitted, exactly as a backend is.

    The private locator is written into whatever the sink is, so a
    protocol-shaped object that merely *looks* like one is refused rather than
    handed a task's private material.
    """

    class _ProtocolShapedSink:
        def bind_source(
            self,
            task_id,
            session_id,
            source_kind,
            private_locator,
            artifact_ref,
            *,
            last_seen_cursor=None,
        ): ...

    class _HostileSubclass(_SourceSinkDouble):
        pass

    for refused in (_ProtocolShapedSink(), _HostileSubclass(), object()):
        with pytest.raises(SpineError) as exc:
            bind_arsd_execution(
                _config(tmp_path),
                facade=_FacadeDouble(),
                ledger=ArsdRunBindingLedger(str(tmp_path / "ledger.json")),
                bindings=refused,
            )
        assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH


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


def test_dispatch_stays_fail_closed_without_payload_resolver(tmp_path: Path) -> None:
    bundle, facade = _bundle(tmp_path)
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


def test_a_dispatched_turn_publishes_into_the_composed_sink(tmp_path: Path) -> None:
    """The composed seam end to end: one turn, one binding, refs-only events.

    The dispatcher's own suite proves the binding semantics; what is proven
    here is that the *composition root* wires the sink it published on the
    bundle to the dispatcher that writes into it, so a host that composed one
    bundle does not have to hand-copy bindings between two.
    """

    payloads = {"payload_goal_1": "ship the integration"}
    bundle, facade = _bundle(tmp_path, payload_resolver=payloads.__getitem__)
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

    # The bundle's own sink is the one that received the turn.
    bound = bundle.bindings.bound[("task_alpha", ref.session_id)]
    source_kind, private_locator, artifact_ref, last_seen_cursor = bound
    assert source_kind == "arsd_run"
    assert artifact_ref == outcome.artifact_ref
    # A new turn is a new read-model stream: the foreign cursor starts unset.
    assert last_seen_cursor is None

    # The private locator reached the sink and nothing else: not the outcome,
    # not the canonical log, not the bundle's own repr.
    surfaces = [
        json.dumps(dataclasses.asdict(outcome)),
        json.dumps(list(bundle.port.stream(ref))),
        repr(bundle),
    ]
    for surface in surfaces:
        assert scan_for_leak(surface) is None, surface
        for canary in (
            _RUN_ID_CANARY,
            _ARS_SESSION_CANARY,
            _SOCKET_CANARY,
            "never surfaced",
            private_locator,
            str(tmp_path),
        ):
            assert canary not in surface, canary


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
        tmp_path, payload_resolver=payloads.__getitem__
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

    # The caller follows the first turn's stream and advances its cursor.
    assert bundle.bindings.artifact_ref("task_alpha", ref.session_id) == first.turn_ref
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
    _kind, locator, artifact_ref, cursor = bundle.bindings.bound[
        ("task_alpha", ref.session_id)
    ]
    assert artifact_ref == second.turn_ref
    # The advanced cursor belonged to the first turn's stream; the second turn
    # is a new stream, so it starts unset rather than inheriting position 2.
    assert cursor is None
    assert locator == f"{_RUN_ID_CANARY}-2"

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
        tmp_path, payload_resolver=_resolver
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

    # And it published like any acceptance: same sink, same binding shape, so
    # a recovered turn is readable exactly as an ordinary one is.
    kind, _locator, artifact_ref, cursor = bundle.bindings.bound[
        ("task_alpha", ref.session_id)
    ]
    assert (kind, artifact_ref, cursor) == ("arsd_run", recovered.turn_ref, None)
    assert scan_for_leak(json.dumps(dataclasses.asdict(recovered))) is None
    assert _RUN_ID_CANARY not in json.dumps(dataclasses.asdict(recovered))


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
        tmp_path, payload_resolver=payloads.__getitem__
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
    fresh_bindings = _SourceSinkDouble()
    fresh_facade = _FacadeDouble()
    fresh = bind_arsd_execution(
        _config(tmp_path),
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
    kind, locator, artifact_ref, cursor = fresh_bindings.bound[
        ("task_alpha", fresh_ref.session_id)
    ]
    assert (kind, artifact_ref, cursor) == ("arsd_run", turn_ref, None)
    # The private locator came back from the durable ledger and stayed private.
    assert locator.startswith(_RUN_ID_CANARY)
    assert _RUN_ID_CANARY not in turn_ref


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
    bindings = _SourceSinkDouble()
    dispatcher = AgentRunSupervisorTurnDispatcher(
        port, backend, bindings, registry, lambda ref: "x"
    )
    return SimpleNamespace(
        backend=backend,
        registry=registry,
        port=port,
        bindings=bindings,
        dispatcher=dispatcher,
    )


def test_a_composed_bundle_is_one_graph_sharing_one_lock_provider(
    tmp_path: Path,
) -> None:
    """Every part is the same object as every other part's view of it."""

    bundle, facade = _bundle(tmp_path)

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

    bundle, _facade = _bundle(tmp_path)
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
        payload_resolver=payloads.__getitem__,
        facade=facade,
        ledger=ArsdRunBindingLedger(str(tmp_path / "ledger.json")),
        bindings=_SourceSinkDouble(),
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

    # ...and the turn really was published into this bundle's own sink.
    assert ("task_alpha", ref.session_id) in bundle.bindings.bound


def test_a_bundle_whose_sink_belongs_to_another_graph_fails_closed(
    tmp_path: Path,
) -> None:
    """The sink the bundle publishes has to be the one its dispatcher writes to.

    A bundle holding one sink while its dispatcher writes into another
    type-checks perfectly, and everything downstream then reads a store this
    task never wrote to: the bindings are on one object and the reader is on
    the other. So it is checked by identity, exactly as the rest of the graph
    is.
    """

    bundle, facade = _bundle(tmp_path)
    other = _second_spine(tmp_path)
    fields = {f.name: getattr(bundle, f.name) for f in dataclasses.fields(bundle)}
    fields["bindings"] = other.bindings

    with pytest.raises(SpineError) as exc:
        AgentRunSupervisorExecutionBinding(**fields)
    assert exc.value.code == RUNTIME_INVALID_SESSION

    # Refused at construction: nothing was dispatched or submitted.
    assert facade.ops("submit") == 0
    assert facade.ops("run_events") == 0


def test_a_composed_bundle_sink_is_this_bundles_own(tmp_path: Path) -> None:
    """The positive control: the bundle's sink is the dispatcher's sink."""

    bundle, _facade = _bundle(tmp_path)
    assert bundle.dispatcher.bindings is bundle.bindings
    assert bundle.dispatcher.registry is bundle.registry
    assert bundle.dispatcher.port is bundle.port
