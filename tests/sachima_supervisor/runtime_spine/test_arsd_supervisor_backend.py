"""ARS 0.7.6 P4 — ``arsd`` backend: submit, observe, cancel, terminal truth.

Focused RED/GREEN acceptance tests for the P4 slice of the ARS 0.7.6 Socket
API v3 integration plan
(``docs/plans/2026-08-17-ars-0.7.6-socket-api-v3-integration-plan.md`` §10).

What is proven here:

* the default-off gate — constructing the backend *is* the gate (P4-a);
* the R-6 three-hop terminal mapping, one independent row per ARS terminal,
  and the disjointness of the transport vocabulary from Sachima's canonical
  ``STATUS_VALUES`` (A-12);
* untrusted terminal evidence, an unproven cancel, a disconnect, and a
  ``PERMISSION_VIOLATION`` terminal, each on its **own** fixture so none can
  collapse into another (A-13/A-14/A-15/A-26);
* one submit per dispatch, the pending intent written **before** it, the
  atomic accepted pair after it, and no automatic replay of an indeterminate
  or lost-ack submission (A-7/A-8);
* the explicit recovery entry point: same ``request_id``, byte-equivalent
  frozen payload, no negotiation, no current-budget pre-check, exactly one
  finalize — and a digest mismatch that fails closed with **zero** socket
  calls (A-8/A-24);
* a fresh ``server_info`` negotiation immediately before every **new**
  admission's pre-check and submit, against that admission's own budget
  (A-23);
* per-Run ``(requested_model, requested_effort)`` re-resolution, never read
  back from ``last_effective_*``, and no surface presenting Sachima's own
  request literal as the Run's effective configuration (A-25);
* the ``arsd_run`` read model over ``run_events`` only, whose foreign cursor
  never becomes ``TaskEventLog.seq`` (A-9/A-10);
* the no-leak sweep over reprs, ``str()``, serialized projections, event
  payloads, and exception text (A-20), including a remote error message at
  the contract maximum (R-4).

Everything is hermetic and offline: every daemon operation goes through an
injected facade double, and no test opens a socket, starts a daemon, reaches
the network, or launches a real AGENT. No test asserts, implies, or names an
effective-configuration read-back — that is gate E-9/E-10. Forbidden terms in
this prose are no-leak boundary canaries only, never behavior.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import pytest

from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    RUNTIME_SUPERVISOR_BACKEND_FAILURE,
    AgentRunSupervisorPort,
)
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import (
    ARSD_BINDING_ACCEPTED,
    ARSD_BINDING_PENDING,
    RUNTIME_ARSD_BINDING_CONFLICT,
    ArsdRunBindingLedger,
    derive_run_ref,
)
from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    ARSD_MAX_ERROR_MESSAGE_CHARS,
    ARSD_PERMISSION_VIOLATION_REASON,
    ARSD_SUPERVISOR_CONFIG_TYPE,
    ARSD_TERMINAL_STATUSES,
    RUNTIME_ARSD_INTERNAL,
    RUNTIME_ARSD_INVALID_REQUEST,
    RUNTIME_ARSD_POLICY_DENIED,
    RUNTIME_ARSD_PROTOCOL_VIOLATION,
    RUNTIME_ARSD_SUBMISSION_INDETERMINATE,
    RUNTIME_ARSD_UNAVAILABLE,
    ArsdSupervisorConfig,
    arsd_submit_payload_digest,
    derive_arsd_request_id,
)
from sachima_supervisor.runtime_spine.events import STATUS_VALUES, SpineError, scan_for_leak
from sachima_supervisor.runtime_spine.execution_port import RUNTIME_INVALID_SESSION
from sachima_supervisor.runtime_spine.launch_spec import build_launch_spec
from sachima_supervisor.runtime_spine.live_progress_projection import (
    build_live_progress_projection,
    serialize_live_progress_projection,
)
from sachima_supervisor.runtime_spine.registry import TaskRegistry
from sachima_supervisor.runtime_spine.arsd_supervisor_backend import (
    derive_arsd_backend_handle,
)
from sachima_supervisor.runtime_spine.supervisor_turn_backend import (
    SOURCE_KIND_ARSD_RUN,
    SUPERVISOR_TURN_STATUSES,
    DispatchedSupervisorTurn,
    serialize_supervisor_turn_result,
)

# --------------------------------------------------------------------------- #
# Lazy module handle — the P4 module must not be needed to COLLECT this file,
# so each test fails for its own stated reason rather than at import time.
# --------------------------------------------------------------------------- #
_BACKEND_MODULE = "sachima_supervisor.runtime_spine.arsd_supervisor_backend"


def _mod():
    return importlib.import_module(_BACKEND_MODULE)


# --------------------------------------------------------------------------- #
# Canaries — material that must never reach a public surface, in any state.
# --------------------------------------------------------------------------- #
SOCKET_CANARY = "/tmp/sachima-canary-p4/arsd-private.sock"
WORKSPACE_CANARY = "/tmp/sachima-canary-p4/private-workspace"
PROMPT_CANARY = "sachima-canary-p4-prompt-body-never-persisted"
RUN_ID_CANARY = "RUN-canary-p4-9f2c1a7b"
ARS_SESSION_CANARY = "SESSCANARYP49f2c1a7b"
REMOTE_TEXT_CANARY = ("sachima-canary-remote-daemon-error-text-" * 32)[
    :ARSD_MAX_ERROR_MESSAGE_CHARS
]
OTHER_WORKSPACE_CANARY = "/tmp/sachima-canary-p4/private-workspace-other"
MODEL_A = "claude-sonnet-5"
MODEL_B = "claude-opus-5"
EFFORT_A = "medium"
EFFORT_B = "high"

#: The canonical Sachima Session refs a dispatch is identified by.
SESSION_REF = "sess_p4_alpha"
OTHER_SESSION_REF = "sess_p4_beta"

TASK_ID = "task_p4_alpha"
OTHER_TASK_ID = "task_p4_beta"
DISPATCH_ONE = "turn_1_ab12cd34"
DISPATCH_TWO = "turn_2_ef56ab78"
PROMPT_REF = "prompt_alpha"
ACCEPTED_AT = "2026-08-17T04:05:06+00:00"

#: A plausible operator-configured negotiated budget — never the 4 GiB
#: deployment default, which no test may equality-assert (Δ-9 / A-22).
NEGOTIATED_EVENT_BUDGET = 2_147_483_648
#: Below the frozen ``max_event_bytes * max_events`` product of the admitted
#: run-limits entry (65_536 * 10_000 = 655_360_000).
LOWERED_EVENT_BUDGET = 1_048_576
FROZEN_LIMIT_PRODUCT = 65_536 * 10_000

REFS = ("ws_main", "policy_agent", "policy_model_a", "policy_effort_a", "policy_limits")
#: Same task, a changed STABLE identity — refused across a restart.
REFS_OTHER_WORKSPACE = (
    "ws_other",
    "policy_agent",
    "policy_model_a",
    "policy_effort_a",
    "policy_limits",
)
REFS_OTHER_AGENT = (
    "ws_main",
    "policy_agent_other",
    "policy_model_a",
    "policy_effort_a",
    "policy_limits",
)
REFS_SECOND_PAIR = (
    "ws_main",
    "policy_agent",
    "policy_model_b",
    "policy_effort_b",
    "policy_limits",
)

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


def _run_limits() -> dict[str, Any]:
    return {
        "startup_timeout_seconds": 60.0,
        "turn_timeout_seconds": 600.0,
        "cancel_grace_seconds": 10.0,
        "max_stderr_bytes": 262_144,
        "max_event_bytes": 65_536,
        "max_events": 10_000,
    }


def _config(tmp_path: Path, **overrides: Any) -> ArsdSupervisorConfig:
    kwargs: dict[str, Any] = {
        "type": ARSD_SUPERVISOR_CONFIG_TYPE,
        "approval_ref": "approval_arsd_p4_offline",
        "owner": "sachima_host",
        "namespace": "sachima_tasks",
        "socket_path": SOCKET_CANARY,
        "binding_ledger_path": str(tmp_path / "arsd-run-bindings.json"),
        "agent_by_policy_ref": {
            "policy_agent": "reader-agent",
            "policy_agent_other": "other-reader-agent",
        },
        "model_by_policy_ref": {"policy_model_a": MODEL_A, "policy_model_b": MODEL_B},
        "effort_by_policy_ref": {
            "policy_effort_a": EFFORT_A,
            "policy_effort_b": EFFORT_B,
        },
        "workspace_by_ref": {
            "ws_main": WORKSPACE_CANARY,
            "ws_other": OTHER_WORKSPACE_CANARY,
        },
        "run_limits_by_policy_ref": {"policy_limits": _run_limits()},
        "grant_ref": "grant_reader_v1",
        "grant_hash": "sha256:" + "a" * 64,
        "grant_role_hash": "sha256:" + "b" * 64,
        "grant_capabilities": ("read", "search"),
        "mcp_snapshot_hashes": ("sha256:" + "c" * 64,),
        "credential_refs": ("cred_reader_github",),
        "evidence_policy_hash": "sha256:" + "d" * 64,
        "recovery_policy_hash": "sha256:" + "e" * 64,
        "enabled": True,
    }
    kwargs.update(overrides)
    return ArsdSupervisorConfig(**kwargs)


# --------------------------------------------------------------------------- #
# The injected facade double — the ONLY daemon surface in this file.
# --------------------------------------------------------------------------- #
class _TransportLoss(Exception):
    """A local transport failure the official client would raise, doubled."""


class _RemoteError(Exception):
    """A daemon-declared failure carrying remote message text, doubled."""


class _FacadeDouble:
    """One in-memory arsd daemon: it records what it admitted and answers.

    It is deliberately idempotent on ``request_id`` — that is the durable
    admission record a same-request recovery resolves against — and it logs
    every operation in call order so a test can prove what was, and was not,
    sent.
    """

    def __init__(self, *, budget: int = NEGOTIATED_EVENT_BUDGET) -> None:
        self.calls: list[str] = []
        self.submitted: list[tuple[str, dict[str, Any]]] = []
        self.admitted: dict[str, dict[str, Any]] = {}
        self.budget = budget
        #: When set, every operation records the attempt and then fails the
        #: test — the double for a ZERO-socket-call proof.
        self.hostile = False
        self.server_info_error: BaseException | None = None
        #: Held open to park an admission mid-sequence — after the active-Run
        #: exclusion has answered and before anything durable is written, which
        #: is the exact window a concurrent cancel could otherwise overtake.
        self.server_info_gate: threading.Event | None = None
        self.server_info_started: threading.Event = threading.Event()
        self.submit_error: BaseException | None = None
        #: Seconds a submit dwells inside the daemon before answering. Only a
        #: race test sets it, to hold the window a second dispatch would have
        #: to squeeze through open long enough to be real.
        self.submit_dwell_seconds = 0.0
        self.submit_raises_from_call: int | None = None
        self.run_status_error: BaseException | None = None
        self.run_status_payload: dict[str, Any] | None = None
        self.run_cancel_payload: dict[str, Any] | None = None
        self.run_events_payload: dict[str, Any] | None = None
        self.session_view_overrides: dict[str, Any] = {}
        #: The daemon's startup roster snapshot, and a way to make the
        #: roster read fail the way a real one can.
        self.registered_agent_ids: tuple[str, ...] = REGISTERED_AGENT_IDS
        self.agent_list_error: BaseException | None = None
        self.ars_session_id = ARS_SESSION_CANARY
        self.accepted_at = ACCEPTED_AT
        #: Every Run-scoped operation and the raw id it targeted.
        self.run_targets: list[tuple[str, str]] = []
        self._run_seq = 0

    # -- helpers ---------------------------------------------------------- #
    def _log(self, op: str) -> None:
        self.calls.append(op)
        if self.hostile:
            raise AssertionError(f"no socket operation may run here: {op}")

    def ops(self, op: str) -> int:
        return self.calls.count(op)

    def session_view(self, session_id: str) -> dict[str, Any]:
        view = {
            "session_id": session_id,
            "owner": "sachima_host",
            "namespace": "sachima_tasks",
            "agent_id": "reader-agent",
            "profile_id": None,
            "created_at": ACCEPTED_AT,
            "updated_at": ACCEPTED_AT,
            "last_effective_model": None,
            "last_effective_effort": None,
            "quarantine": None,
        }
        view.update(self.session_view_overrides)
        return view

    # -- the six operations ------------------------------------------------ #
    def server_info(self) -> dict[str, Any]:
        self._log("server_info")
        self.server_info_started.set()
        if self.server_info_gate is not None:
            self.server_info_gate.wait(timeout=10)
        if self.server_info_error is not None:
            raise self.server_info_error
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
                "max_run_event_budget_bytes": self.budget,
            },
        }

    def submit(self, *, request_id: str, payload: Any) -> dict[str, Any]:
        self._log("submit")
        self.submitted.append((request_id, json.loads(json.dumps(dict(payload)))))
        if self.submit_dwell_seconds:
            time.sleep(self.submit_dwell_seconds)
        # The daemon records the admission BEFORE it answers: a raise after
        # this point is a genuinely lost ack, not a refused submission.
        if request_id not in self.admitted:
            self._run_seq += 1
            self.admitted[request_id] = {
                "run_id": f"{RUN_ID_CANARY}-{self._run_seq}",
                "session_id": self.ars_session_id,
                "accepted_at": self.accepted_at,
            }
        if self.submit_raises_from_call is not None and (
            self.ops("submit") >= self.submit_raises_from_call
        ):
            raise AssertionError("submit must not be reached on this call")
        if self.submit_error is not None:
            raise self.submit_error
        return dict(self.admitted[request_id])

    def run_status(self, run_id: str) -> dict[str, Any]:
        self._log("run_status")
        self.run_targets.append(("run_status", run_id))
        if self.run_status_error is not None:
            raise self.run_status_error
        if self.run_status_payload is None:
            return {"run_id": run_id, "session_id": self.ars_session_id}
        payload = dict(self.run_status_payload)
        payload["run_id"] = run_id
        payload.setdefault("session_id", self.ars_session_id)
        return payload

    def run_events(
        self, run_id: str, *, from_seq: int, limit: int | None = None
    ) -> dict[str, Any]:
        self._log("run_events")
        self.run_targets.append(("run_events", run_id))
        if self.run_events_payload is None:
            return {
                "run_id": run_id,
                "events": [],
                "next_from_seq": from_seq,
                "exhausted": True,
            }
        payload = dict(self.run_events_payload)
        payload["run_id"] = run_id
        return payload

    def run_cancel(self, run_id: str) -> dict[str, Any]:
        self._log("run_cancel")
        self.run_targets.append(("run_cancel", run_id))
        if self.run_cancel_payload is None:
            return {"run_id": run_id}
        payload = dict(self.run_cancel_payload)
        payload["run_id"] = run_id
        return payload

    def session_status(self, session_id: str) -> dict[str, Any]:
        self._log("session_status")
        return self.session_view(session_id)

    def session_list(self) -> dict[str, Any]:
        self._log("session_list")
        return {"sessions": [self.session_view(self.ars_session_id)]}

    def agent_list(self) -> dict[str, Any]:
        self._log("agent_list")
        if self.agent_list_error is not None:
            raise self.agent_list_error
        return {"agent_ids": list(self.registered_agent_ids)}


class _PromptResolver:
    """The injected resolver a recovery rebuilds the frozen prompt through."""

    def __init__(self, prompts: dict[str, str]) -> None:
        self.prompts = dict(prompts)
        self.calls = 0

    def __call__(self, resolver_refs: Any) -> str:
        self.calls += 1
        return self.prompts[resolver_refs["prompt_ref"]]


# --------------------------------------------------------------------------- #
# Composition helpers
# --------------------------------------------------------------------------- #
def _ledger(tmp_path: Path) -> ArsdRunBindingLedger:
    tmp_path.mkdir(parents=True, exist_ok=True)
    return ArsdRunBindingLedger(str(tmp_path / "arsd-run-bindings.json"))


def _backend(
    tmp_path: Path,
    facade: Any | None = None,
    *,
    resolver: Any | None = None,
    **config_overrides: Any,
):
    mod = _mod()
    facade = _FacadeDouble() if facade is None else facade
    resolver = _PromptResolver({PROMPT_REF: PROMPT_CANARY}) if resolver is None else resolver
    backend = mod.ArsdSupervisorBackend(
        _config(tmp_path, **config_overrides),
        facade,
        _ledger(tmp_path),
        prompt_resolver=resolver,
    )
    return backend, facade, resolver


def _attach(backend, task_id: str = TASK_ID, refs: tuple[str, ...] = REFS) -> str:
    return backend.create_or_attach(task_id, refs)


def _dispatch(
    backend,
    *,
    task_id: str = TASK_ID,
    dispatch_ref: str = DISPATCH_ONE,
    payload_ref: str = PROMPT_REF,
    prompt: str = PROMPT_CANARY,
    turn_kind: str = "prompt",
    session_ref: str = SESSION_REF,
) -> DispatchedSupervisorTurn:
    return backend.run_turn(
        task_id,
        turn_kind=turn_kind,
        payload_text=prompt,
        dispatch_ref=dispatch_ref,
        payload_ref=payload_ref,
        session_ref=session_ref,
    )


def _spec(task_id: str = TASK_ID, refs: tuple[str, ...] = REFS):
    return build_launch_spec(
        task_id=task_id,
        agent_kind="local_agent",
        mode_flags={"needs_agent": True},
        roles=("read_only",),
        refs=refs,
    )


def _port_bundle(tmp_path: Path, facade: Any | None = None):
    backend, facade, resolver = _backend(tmp_path, facade)
    registry = TaskRegistry()
    port = AgentRunSupervisorPort(registry, backend=backend)
    ref = port.create_or_attach(TASK_ID, _spec())
    return backend, facade, registry, port, ref


def _terminal_result(status: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"status": status}
    body.update(extra)
    return body


def _run_ended(facade, status: str = "completed") -> None:
    """Let the facade answer that this task's recorded Run is over.

    The §7.4 active-Run exclusion asks the daemon for trusted terminal truth
    before it admits a second dispatch, so every fixture that runs a second
    turn has to say the first one ended — which is exactly what happens between
    two turns of a real conversation.
    """

    facade.run_status_payload = {"result": _terminal_result(status)}


def _rendered(excinfo) -> str:
    err = excinfo.value
    return (
        repr(err)
        + str(err)
        + repr(err.args)
        + "".join(traceback.format_exception(err))
    )


# --------------------------------------------------------------------------- #
# A. Composition IS the gate (P4-a)
# --------------------------------------------------------------------------- #
def test_constructing_the_backend_is_the_default_off_gate(tmp_path: Path) -> None:
    mod = _mod()
    facade = _FacadeDouble()
    with pytest.raises(SpineError) as excinfo:
        mod.ArsdSupervisorBackend(
            _config(tmp_path, enabled=False), facade, _ledger(tmp_path)
        )
    assert excinfo.value.code == mod.RUNTIME_ARSD_DISABLED
    # A refused composition reaches no daemon operation at all.
    assert facade.calls == []


def test_composition_negotiates_server_info_once_and_fails_closed_on_mismatch(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    assert facade.calls == ["server_info"]

    unreachable = _FacadeDouble()
    unreachable.server_info_error = _TransportLoss("daemon unreachable")
    with pytest.raises(SpineError) as excinfo:
        _backend(tmp_path, unreachable)
    # One stable backend-unavailable verdict; never a fallback to library/CLI.
    assert excinfo.value.code == RUNTIME_ARSD_UNAVAILABLE
    assert "daemon unreachable" not in _rendered(excinfo)


def test_composed_backend_retains_the_negotiated_typed_info(tmp_path: Path) -> None:
    """The negotiation the constructor already performed stays readable.

    A composed backend has *proven* the contract; throwing that proof away
    would force every later reader either to negotiate again — a socket call
    for a value already known — or to mirror a default beside it, which is a
    fallback wearing a constant's name.
    """

    from sachima_supervisor.runtime_spine.arsd_socket_contract import ArsdServerInfo

    backend, facade, _ = _backend(tmp_path)
    info = backend.negotiated_server_info
    assert type(info) is ArsdServerInfo
    assert info.api_version == 3
    assert info.max_concurrent_runs == 4

    # Reading it is a read: no second negotiation, no socket operation at all.
    before = list(facade.calls)
    for _ in range(5):
        assert backend.negotiated_server_info.max_concurrent_runs == 4
    assert facade.calls == before


def test_a_failed_negotiation_leaves_no_backend_and_no_capacity_to_read(
    tmp_path: Path,
) -> None:
    """No fallback number: a backend that cannot negotiate never exists, so
    there is nothing to read a capacity off."""

    unreachable = _FacadeDouble()
    unreachable.server_info_error = _TransportLoss("daemon unreachable")
    with pytest.raises(SpineError) as excinfo:
        _backend(tmp_path, unreachable)
    assert excinfo.value.code == RUNTIME_ARSD_UNAVAILABLE


def test_backend_source_carries_no_mirrored_concurrency_default() -> None:
    """The one admissible source of capacity is the live negotiation."""

    mod = _mod()
    for name in dir(mod):
        value = getattr(mod, name)
        if "CONCURRENT" in name.upper() and isinstance(value, int):
            raise AssertionError(f"mirrored concurrency constant: {name}")


def test_backend_module_imports_without_agent_run_supervisor() -> None:
    for name in list(sys.modules):
        if name.startswith("agent_run_supervisor"):
            del sys.modules[name]
    importlib.import_module(_BACKEND_MODULE)
    leaked = [name for name in sys.modules if name.startswith("agent_run_supervisor")]
    assert leaked == [], leaked


# --------------------------------------------------------------------------- #
# B. R-6 — the three-hop terminal mapping, one independent row per terminal
# --------------------------------------------------------------------------- #
_THREE_HOP_ROWS = [
    # (ARS terminal, neutral token). The third hop is deliberately uniform: a
    # Run terminal of ANY kind leaves the task running, because ending a task
    # is not something a Run gets to decide (Spec §6 — Sessions have no close).
    ("completed", "completed"),
    ("failed", "failed"),
    ("cancelled", "cancelled"),
    ("timed_out", "timed_out"),
    ("unknown", "unknown"),
]


@pytest.mark.parametrize(
    "ars_terminal,neutral", _THREE_HOP_ROWS, ids=[row[0] for row in _THREE_HOP_ROWS]
)
def test_each_ars_terminal_maps_through_all_three_hops(
    tmp_path: Path, ars_terminal: str, neutral: str
) -> None:
    """ARS terminal -> transport-neutral -> observed Run status -> canonical log.

    Five independent rows, and the last hop is where the R-6 boundary really
    bites: no transport token becomes a canonical status, and no Run terminal
    becomes the task's.
    """

    mod = _mod()
    backend, facade, registry, port, ref = _port_bundle(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)

    # Hop 1 -> 2: the transport-neutral token, from the mapping the backend uses.
    assert mod.map_arsd_terminal_to_neutral(ars_terminal) == neutral
    assert neutral in SUPERVISOR_TURN_STATUSES

    # Hop 2 -> 3: the backend reports exactly that token for the Run.
    facade.run_status_payload = {"result": _terminal_result(ars_terminal)}
    assert backend.observe_run(handle) == neutral

    # Hop 3 -> 4: the canonical TaskEventLog never receives it. The Session is
    # live, the task is not terminal, and the transport vocabulary stays out.
    observed = port.status(ref)
    assert observed.state == "running"
    assert observed.terminal is False
    snapshot = registry.snapshot(TASK_ID)
    assert snapshot["status"] == "running"
    assert neutral not in json.dumps(snapshot)


def test_transport_terminal_vocabulary_is_disjoint_from_canonical_status_values() -> None:
    mod = _mod()
    # Every ARS terminal has exactly one neutral token, and the five map 1:1.
    assert set(mod.ARSD_TERMINAL_TO_NEUTRAL_STATUS) == set(ARSD_TERMINAL_STATUSES)
    assert set(mod.ARSD_TERMINAL_TO_NEUTRAL_STATUS.values()) <= SUPERVISOR_TURN_STATUSES

    # A transport token can never be appended as a canonical status.
    for transport_only in ("timed_out", "unknown", "accepted"):
        assert transport_only not in STATUS_VALUES
    assert SUPERVISOR_TURN_STATUSES - STATUS_VALUES == {
        "timed_out",
        "unknown",
        "accepted",
    }
    # Nor can a port session state that has no canonical member.
    assert "ambiguous" not in STATUS_VALUES
    # And there is no table left that could quietly reintroduce one: hop 2 -> 3
    # is not a mapping, it is the absence of one.
    assert not hasattr(mod, "NEUTRAL_TO_SESSION_STATE")


def test_absent_terminal_with_progress_leaves_the_task_running(tmp_path: Path) -> None:
    backend, facade, registry, port, ref = _port_bundle(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)

    facade.run_status_payload = {"progress": {"phase": "tooling", "count": 3}}
    assert backend.status(handle) == "running"
    assert port.status(ref).state == "running"
    assert registry.snapshot(TASK_ID)["status"] == "running"
    assert registry.snapshot(TASK_ID)["terminal"] is False


# --------------------------------------------------------------------------- #
# C. A-13 / A-14 / A-15 / A-26 — four fixtures, deliberately not shared
# --------------------------------------------------------------------------- #
def _untrusted_terminal_fixture(tmp_path: Path):
    """A-13: a terminal body whose evidence is NOT on the closed vocabulary."""

    bundle = _port_bundle(tmp_path)
    backend, facade = bundle[0], bundle[1]
    _attach(backend)
    _dispatch(backend)
    facade.run_status_payload = {"result": {"status": "probably_fine", "note": 1}}
    return bundle


def _disconnect_fixture(tmp_path: Path):
    """A-15: no terminal was read at all — the observation itself failed."""

    bundle = _port_bundle(tmp_path)
    backend, facade = bundle[0], bundle[1]
    _attach(backend)
    _dispatch(backend)
    facade.run_status_error = _TransportLoss("connection reset by peer")
    return bundle


def _unproven_cancel_fixture(tmp_path: Path):
    """A-14: a cancel accepted, with no trusted terminal evidence yet."""

    bundle = _port_bundle(tmp_path)
    backend, facade = bundle[0], bundle[1]
    _attach(backend)
    _dispatch(backend)
    facade.run_cancel_payload = {}
    facade.run_status_payload = {"progress": {"phase": "draining"}}
    return bundle


def _permission_violation_fixture(tmp_path: Path, *, carried_status: str = "completed"):
    """A-26: trusted terminal evidence of a policy-denied failure."""

    bundle = _port_bundle(tmp_path)
    backend, facade = bundle[0], bundle[1]
    _attach(backend)
    _dispatch(backend)
    facade.run_status_payload = {
        "result": _terminal_result(
            carried_status, reason=ARSD_PERMISSION_VIOLATION_REASON
        )
    }
    return bundle


def test_untrusted_terminal_is_a_contained_internal_failure_not_a_success(
    tmp_path: Path,
) -> None:
    backend, facade, registry, port, ref = _untrusted_terminal_fixture(tmp_path)
    handle = _attach(backend)

    with pytest.raises(SpineError) as excinfo:
        backend.status(handle)
    assert excinfo.value.code == RUNTIME_ARSD_INTERNAL
    assert "probably_fine" not in _rendered(excinfo)

    # The port contains it as a read failure: nothing is marked, and no
    # success is fabricated.
    with pytest.raises(SpineError) as port_excinfo:
        port.status(ref)
    assert port_excinfo.value.code == RUNTIME_SUPERVISOR_BACKEND_FAILURE
    snapshot = registry.snapshot(TASK_ID)
    assert snapshot["status"] == "running"
    assert snapshot["terminal"] is False
    # Distinct from A-15: observation loss carries a different stable code.
    assert RUNTIME_ARSD_INTERNAL != RUNTIME_ARSD_UNAVAILABLE


def test_disconnect_does_not_mutate_canonical_state_or_redispatch(
    tmp_path: Path,
) -> None:
    backend, facade, registry, port, ref = _disconnect_fixture(tmp_path)
    handle = _attach(backend)
    before = registry.snapshot(TASK_ID)
    submits_before = facade.ops("submit")

    with pytest.raises(SpineError) as excinfo:
        backend.status(handle)
    assert excinfo.value.code == RUNTIME_ARSD_UNAVAILABLE
    assert "connection reset" not in _rendered(excinfo)
    with pytest.raises(SpineError):
        port.status(ref)

    assert registry.snapshot(TASK_ID) == before
    # Never re-dispatch on observation loss.
    assert facade.ops("submit") == submits_before

    # A later successful read resumes the preserved session: the Run's verdict
    # is readable again, and the Session it ran in is still live.
    facade.run_status_error = None
    facade.run_status_payload = {"result": _terminal_result("completed")}
    assert backend.observe_run(handle) == "completed"
    assert backend.status(handle) == "running"


def test_kill_issues_run_cancel_only_and_never_a_session_operation(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    facade.run_cancel_payload = {
        "status": "cancelled",
        "result": _terminal_result("cancelled"),
    }
    before = len(facade.calls)

    assert backend.kill(handle, "ref_cancelled") == "cancelled"

    during = facade.calls[before:]
    assert during.count("run_cancel") == 1
    assert "session_status" not in during
    assert "session_list" not in during
    assert "submit" not in during
    # There is no Session close operation to reach for in the first place.
    assert not hasattr(backend, "close_session")


def test_cancel_without_trusted_evidence_is_never_a_claimed_cancel(
    tmp_path: Path,
) -> None:
    backend, facade, registry, port, ref = _unproven_cancel_fixture(tmp_path)
    handle = _attach(backend)

    verdict = backend.kill(handle, "ref_cancelled")
    assert verdict == "ambiguous"
    assert verdict != "cancelled"
    # A bounded re-query happened, and it still proved nothing.
    assert facade.ops("run_status") >= 1
    assert registry.snapshot(TASK_ID)["status"] != "cancelled"

    # Trusted evidence, and only trusted evidence, promotes it.
    facade.run_status_payload = {"result": _terminal_result("cancelled")}
    assert backend.kill(handle, "ref_cancelled") == "cancelled"


def test_permission_violation_terminal_moves_status_through_the_trusted_path(
    tmp_path: Path,
) -> None:
    """A-26: denied by policy is a trusted FAILURE, not untrusted evidence."""

    backend, facade, registry, port, ref = _permission_violation_fixture(tmp_path)
    handle = _attach(backend)

    # Ordinary trusted-terminal path: a verdict, not a contained failure.
    assert backend.observe_run(handle) == "failed"
    # It is the RUN that failed. The Session it ran in is untouched.
    assert backend.status(handle) == "running"
    assert port.status(ref).terminal is False

    # Distinct from A-13 (untrusted evidence) and A-15 (no observation).
    untrusted = _untrusted_terminal_fixture(tmp_path / "untrusted")
    with pytest.raises(SpineError) as untrusted_exc:
        untrusted[0].observe_run(_attach(untrusted[0]))
    assert untrusted_exc.value.code == RUNTIME_ARSD_INTERNAL
    disconnected = _disconnect_fixture(tmp_path / "disconnect")
    with pytest.raises(SpineError) as disconnect_exc:
        disconnected[0].observe_run(_attach(disconnected[0]))
    assert disconnect_exc.value.code == RUNTIME_ARSD_UNAVAILABLE

    # The categorical reason never becomes user-visible text.
    payload = json.dumps(registry.snapshot(TASK_ID))
    assert ARSD_PERMISSION_VIOLATION_REASON not in payload
    assert ARSD_PERMISSION_VIOLATION_REASON.lower() not in payload.lower()


def test_permission_violation_does_not_retry_or_mint_a_new_request_id(
    tmp_path: Path,
) -> None:
    backend, facade, registry, port, ref = _permission_violation_fixture(tmp_path)
    handle = _attach(backend)
    submitted_before = list(facade.submitted)

    assert backend.observe_run(handle) == "failed"
    for _ in range(3):
        backend.observe_run(handle)

    # Non-retryable: no second submit, no new request_id, no retry_of_run_id.
    assert facade.submitted == submitted_before
    assert len({request_id for request_id, _ in facade.submitted}) == 1
    assert facade.submitted[0][1]["retry_of_run_id"] is None


def test_permission_violation_leaves_the_session_reusable_and_unquarantined(
    tmp_path: Path,
) -> None:
    """The over-defensive implementation that discards a healthy Session fails."""

    backend, facade, registry, port, ref = _permission_violation_fixture(tmp_path)
    handle = _attach(backend)
    assert backend.observe_run(handle) == "failed"
    # The Session is reusable — stated outright, not merely implied by the
    # next dispatch happening to work.
    assert backend.status(handle) == "running"

    # The next turn reuses the SAME recorded Session, verbatim. The
    # permission-violation terminal is itself the trusted evidence that the
    # previous Run ended, so the §7.4 exclusion admits this one.
    second = _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert isinstance(second, DispatchedSupervisorTurn)
    request_id, payload = facade.submitted[-1]
    assert payload["request"]["session_id"] == ARS_SESSION_CANARY
    # No second Session was created and the binding was never marked broken.
    assert len({entry["session_id"] for entry in facade.admitted.values()}) == 1


# --------------------------------------------------------------------------- #
# D. Submit lifecycle — one record per dispatch, written before the submit
# --------------------------------------------------------------------------- #
def _ledger_document(tmp_path: Path) -> dict[str, Any]:
    return json.loads(
        (tmp_path / "arsd-run-bindings.json").read_text(encoding="utf-8")
    )


class _IntentProbingFacade(_FacadeDouble):
    """Reads the durable ledger from disk at the moment of the submit."""

    def __init__(self, tmp_path: Path) -> None:
        super().__init__()
        self._tmp_path = tmp_path
        self.ledger_at_submit: dict[str, Any] | None = None

    def submit(self, *, request_id: str, payload: Any) -> dict[str, Any]:
        self.ledger_at_submit = _ledger_document(self._tmp_path)
        return super().submit(request_id=request_id, payload=payload)


def test_pending_intent_lands_before_the_submit_and_is_finalized_in_place(
    tmp_path: Path,
) -> None:
    facade = _IntentProbingFacade(tmp_path)
    backend, _, _ = _backend(tmp_path, facade)
    handle = _attach(backend)
    ledger = _ledger(tmp_path)

    dispatched = _dispatch(backend)

    # The intent was durably on disk before the first socket submit.
    assert facade.ledger_at_submit is not None
    intents = facade.ledger_at_submit["bindings"]
    assert len(intents) == 1
    assert intents[0]["state"] == ARSD_BINDING_PENDING
    assert intents[0]["request_id"] == derive_arsd_request_id(
        TASK_ID, handle, DISPATCH_ONE
    )
    assert intents[0]["run_id"] is None and intents[0]["ars_session_id"] is None

    # The validated ack finalized THAT record — one logical record, never two.
    document = _ledger_document(tmp_path)
    assert len(document["bindings"]) == 1
    assert document["bindings"][0]["state"] == ARSD_BINDING_ACCEPTED
    assert document["bindings"][0]["request_id"] == intents[0]["request_id"]
    assert document["bindings"][0]["payload_digest"] == intents[0]["payload_digest"]

    binding = ledger.resolve(TASK_ID, handle, DISPATCH_ONE)
    assert binding is not None
    assert binding.run_id is not None and binding.ars_session_id is not None
    assert dispatched.result.supervisor_status == "accepted"
    assert dispatched.result.source_kind == SOURCE_KIND_ARSD_RUN
    assert dispatched.result.run_ref == derive_run_ref(binding.run_id)
    assert dispatched.private_locator == binding.run_id
    # A submit acknowledgement is not a terminal: it does not block on AGENT.
    assert facade.ops("submit") == 1
    assert facade.ops("run_status") == 0


def test_first_turn_creates_a_session_and_later_turns_reuse_the_recorded_id(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    _attach(backend)

    _dispatch(backend)
    _, first_payload = facade.submitted[0]
    # Create is the structural ABSENCE of session_id — never a present null.
    assert "session_id" not in first_payload["request"]

    _run_ended(facade)
    _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    _, second_payload = facade.submitted[1]
    assert second_payload["request"]["session_id"] == ARS_SESSION_CANARY
    assert facade.ops("submit") == 2


def test_indeterminate_submit_does_not_retry_or_mint_a_new_request_id(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    handle = _attach(backend)
    ledger = _ledger(tmp_path)
    facade.submit_error = _TransportLoss("write failed before a reply was read")

    with pytest.raises(SpineError) as excinfo:
        _dispatch(backend)
    assert excinfo.value.code == RUNTIME_ARSD_SUBMISSION_INDETERMINATE
    assert "write failed" not in _rendered(excinfo)

    # Exactly one submit, and the intent survives fail-closed.
    assert facade.ops("submit") == 1
    intent = ledger.resolve_pending(TASK_ID, handle, DISPATCH_ONE)
    assert intent is not None and intent.state == ARSD_BINDING_PENDING
    assert intent.request_id == derive_arsd_request_id(TASK_ID, handle, DISPATCH_ONE)
    assert ledger.resolve(TASK_ID, handle, DISPATCH_ONE) is None

    # No automatic path acts on it, and none reports around it either:
    # status, liveness and kill all fail closed while it is unresolved.
    for probe in (
        lambda: backend.status(handle),
        lambda: backend.liveness(handle),
        lambda: backend.kill(handle, "ref_cancelled"),
    ):
        with pytest.raises(SpineError) as probe_excinfo:
            probe()
        assert probe_excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT
    assert facade.ops("submit") == 1
    assert facade.ops("run_status") == 0
    assert facade.ops("run_cancel") == 0
    assert ledger.resolve_pending(TASK_ID, handle, DISPATCH_ONE) is not None


def test_quarantined_session_blocks_reuse_and_never_reaches_a_public_surface(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    _attach(backend)
    _dispatch(backend)
    _run_ended(facade)
    facade.session_view_overrides = {
        "quarantine": {
            "reason_code": "UNTRUSTED_TERMINAL_EVIDENCE",
            "source_run_id": RUN_ID_CANARY,
            "recorded_at": ACCEPTED_AT,
        }
    }
    submits_before = facade.ops("submit")

    with pytest.raises(SpineError) as excinfo:
        _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert excinfo.value.code == RUNTIME_ARSD_POLICY_DENIED

    # Never auto-healed, auto-recreated, or retried into.
    assert facade.ops("submit") == submits_before
    rendered = _rendered(excinfo)
    assert "UNTRUSTED_TERMINAL_EVIDENCE" not in rendered
    assert ARS_SESSION_CANARY not in rendered
    assert RUN_ID_CANARY not in rendered


def test_signal_stays_fail_closed_and_invents_no_permission_transition(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    before = list(facade.calls)

    with pytest.raises(SpineError) as excinfo:
        backend.signal(handle, "decision_allow")
    assert excinfo.value.code == RUNTIME_ARSD_POLICY_DENIED
    # No operation exists to deliver a decision, so none was attempted.
    assert facade.calls == before
    assert backend.status(handle) != "permission_wait"


# --------------------------------------------------------------------------- #
# E. A-9 / A-10 — the arsd read model, and the foreign cursor's boundary
# --------------------------------------------------------------------------- #
FOREIGN_CURSOR = 4242


def _event(seq: int, **overrides: Any) -> dict[str, Any]:
    event = {
        "seq": seq,
        "type": "agent_message",
        "kind": "assistant",
        "status": "running",
        "text_length": 12,
    }
    event.update(overrides)
    return event


def test_no_path_maps_the_foreign_cursor_into_task_event_log_seq(
    tmp_path: Path,
) -> None:
    mod = _mod()
    backend, facade, registry, port, ref = _port_bundle(tmp_path)
    _attach(backend)
    dispatched = _dispatch(backend)
    facade.run_events_payload = {
        "events": [_event(FOREIGN_CURSOR - 1), _event(FOREIGN_CURSOR)],
        "next_from_seq": FOREIGN_CURSOR,
        "exhausted": False,
    }

    reader = mod.ArsdLiveProgressReader(facade)
    projection = build_live_progress_projection(
        reader,
        dispatched.private_locator,
        "artifact_run_0",
        task_id=TASK_ID,
        limit=100,
    )

    # next_from_seq -> resume_cursor, exhausted -> has_more = not exhausted.
    assert projection.available is True
    assert projection.resume_cursor == FOREIGN_CURSOR
    assert projection.has_more is True
    assert projection.observed_last_seq == FOREIGN_CURSOR
    assert facade.ops("run_events") >= 1

    # The canonical log never learns that number.
    canonical = port.stream(ref)
    assert canonical
    assert all(event["seq"] != FOREIGN_CURSOR for event in canonical)
    assert registry.log.last_seq(TASK_ID) < FOREIGN_CURSOR
    assert str(FOREIGN_CURSOR) not in json.dumps(list(canonical))

    # Structurally: the backend module never reaches the canonical log at all.
    source = Path(mod.__file__).read_text(encoding="utf-8")
    for token in ("TaskEventLog", "append_event", "TaskRegistry"):
        assert token not in source, token


def test_arsd_reader_reads_only_run_events_and_never_a_daemon_directory(
    tmp_path: Path,
) -> None:
    mod = _mod()
    backend, facade, _ = _backend(tmp_path)
    _attach(backend)
    dispatched = _dispatch(backend)
    facade.run_events_payload = {
        "events": [_event(1), _event(2)],
        "next_from_seq": 2,
        "exhausted": True,
    }
    before = len(facade.calls)

    reader = mod.ArsdLiveProgressReader(facade)
    page = reader.read_event_page(dispatched.private_locator, after_seq=None, limit=50)
    during = facade.calls[before:]

    assert set(during) == {"run_events"}
    assert page.next_cursor == 2
    assert page.has_more is False
    assert tuple(record.seq for record in page.records) == (1, 2)

    source = Path(mod.__file__).read_text(encoding="utf-8")
    for token in ("native-runs", "run_dir", "os.listdir", "glob("):
        assert token not in source, token


# --------------------------------------------------------------------------- #
# F. R-4 — a remote message at the contract maximum is discarded entirely
# --------------------------------------------------------------------------- #
def test_remote_error_message_at_the_contract_maximum_is_fully_discarded(
    tmp_path: Path,
) -> None:
    assert len(REMOTE_TEXT_CANARY) == ARSD_MAX_ERROR_MESSAGE_CHARS == 512
    backend, facade, _ = _backend(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    facade.run_status_error = _RemoteError(REMOTE_TEXT_CANARY)

    with pytest.raises(SpineError) as excinfo:
        backend.status(handle)

    err = excinfo.value
    assert err.args == (err.code,)
    assert err.__cause__ is None
    assert err.__suppress_context__ or err.__context__ is None
    rendered = _rendered(excinfo)
    assert REMOTE_TEXT_CANARY not in rendered
    # Not even a fragment survives.
    assert REMOTE_TEXT_CANARY[:48] not in rendered
    assert "sachima-canary-remote" not in rendered


# --------------------------------------------------------------------------- #
# G. A-20 — the no-leak sweep over every surface this stage produces
# --------------------------------------------------------------------------- #
def test_no_leak_sweep_over_reprs_projections_events_and_exception_text(
    tmp_path: Path,
) -> None:
    mod = _mod()
    backend, facade, registry, port, ref = _port_bundle(tmp_path)
    handle = _attach(backend)
    dispatched = _dispatch(backend)
    ledger = _ledger(tmp_path)
    binding = ledger.resolve(TASK_ID, handle, DISPATCH_ONE)
    assert binding is not None

    facade.run_events_payload = {
        "events": [_event(1), _event(2)],
        "next_from_seq": 2,
        "exhausted": True,
    }
    projection = build_live_progress_projection(
        mod.ArsdLiveProgressReader(facade),
        dispatched.private_locator,
        "artifact_run_0",
        task_id=TASK_ID,
    )
    facade.run_status_payload = {"result": _terminal_result("completed")}
    port.status(ref)

    with pytest.raises(SpineError) as excinfo:
        backend.signal(handle, "decision_allow")

    canaries = (
        PROMPT_CANARY,
        SOCKET_CANARY,
        WORKSPACE_CANARY,
        binding.run_id,
        ARS_SESSION_CANARY,
        MODEL_A,
        EFFORT_A,
    )
    # The rendered exception chain is swept for the canaries only: it is a
    # test instrument whose own frame text ("Traceback") is a denylist marker.
    rendered = _rendered(excinfo)
    for canary in canaries:
        assert canary not in rendered, canary
    assert excinfo.value.args == (excinfo.value.code,)

    surfaces = (
        repr(dispatched),
        repr(dispatched.result),
        str(dispatched.result),
        serialize_supervisor_turn_result(dispatched.result).decode("utf-8"),
        json.dumps(dispatched.result.as_dict()),
        repr(binding),
        str(binding),
        json.dumps(binding.as_dict()),
        json.dumps(projection.as_dict()),
        serialize_live_progress_projection(projection).decode("utf-8"),
        json.dumps(list(port.stream(ref))),
        json.dumps(registry.snapshot(TASK_ID)),
        repr(backend),
    )
    for surface in surfaces:
        assert scan_for_leak(surface, canaries=canaries) is None, surface
        for canary in canaries:
            assert canary not in surface, (canary, surface)

    # The safe handles that DO appear are Sachima-derived refs.
    assert dispatched.result.run_ref == derive_run_ref(binding.run_id)
    assert dispatched.result.run_ref.startswith("run_")


# --------------------------------------------------------------------------- #
# H. A-25 — per-Run model/effort, re-resolved for every Run
# --------------------------------------------------------------------------- #
def test_reuse_turn_re_resolves_model_and_effort_rather_than_reusing_the_first_pair(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    _attach(backend, refs=REFS)
    _dispatch(backend)
    _, first = facade.submitted[0]
    assert first["request"]["requested_model"] == MODEL_A
    assert first["request"]["requested_effort"] == EFFORT_A

    # The same task, the same ARS Session, a second policy pair.
    _run_ended(facade)
    _attach(backend, refs=REFS_SECOND_PAIR)
    _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    _, second = facade.submitted[1]
    assert second["request"]["requested_model"] == MODEL_B
    assert second["request"]["requested_effort"] == EFFORT_B
    assert second["request"]["session_id"] == ARS_SESSION_CANARY
    # The pair is a property of the Run, never cached onto the binding.
    assert second["request"]["agent_id"] == first["request"]["agent_id"]


def test_backend_never_reads_last_effective_values_into_request_construction(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    _attach(backend)
    _dispatch(backend)
    _run_ended(facade)
    facade.session_view_overrides = {
        "last_effective_model": "wrong-model-from-the-last-run",
        "last_effective_effort": "wrong-effort-from-the-last-run",
    }

    _dispatch(backend, dispatch_ref=DISPATCH_TWO)

    # Non-vacuity: the Session view really was read on the reuse path.
    assert facade.ops("session_status") >= 1
    _, second = facade.submitted[1]
    assert second["request"]["requested_model"] == MODEL_A
    assert second["request"]["requested_effort"] == EFFORT_A
    blob = json.dumps(second)
    assert "wrong-model-from-the-last-run" not in blob
    assert "wrong-effort-from-the-last-run" not in blob


def test_no_surface_presents_the_built_request_literal_as_effective_configuration(
    tmp_path: Path,
) -> None:
    mod = _mod()
    backend, facade, registry, port, ref = _port_bundle(tmp_path)
    handle = _attach(backend)
    dispatched = _dispatch(backend)
    facade.run_status_payload = {"result": _terminal_result("completed")}
    observed_state = backend.status(handle)
    port.status(ref)
    ledger = _ledger(tmp_path)
    binding = ledger.resolve(TASK_ID, handle, DISPATCH_ONE)
    assert binding is not None

    with pytest.raises(SpineError) as excinfo:
        backend.signal(handle, "decision_allow")

    surfaces = (
        observed_state,
        repr(dispatched.result),
        serialize_supervisor_turn_result(dispatched.result).decode("utf-8"),
        json.dumps(binding.as_dict()),
        repr(binding),
        json.dumps(list(port.stream(ref))),
        json.dumps(registry.snapshot(TASK_ID)),
        json.dumps(dataclasses.asdict(port.status(ref))),
    )
    for surface in surfaces:
        for token in (MODEL_A, MODEL_B, EFFORT_A, EFFORT_B):
            assert token not in surface, (token, surface)
        for token in ("requested_model", "requested_effort", "effective"):
            assert token not in surface.lower(), (token, surface)

    # Exception text carries neither the pair nor the request field names.
    # (The rendered chain is a test instrument: its own frame text names this
    # very test, so only the literals are asserted against it.)
    rendered = _rendered(excinfo)
    for token in (MODEL_A, MODEL_B, EFFORT_A, EFFORT_B, "requested_model", "requested_effort"):
        assert token not in rendered, token

    # The only per-Run configuration statement Sachima makes is the request it
    # built — and it lives on the wire payload alone.
    assert facade.submitted[0][1]["request"]["requested_model"] == MODEL_A
    assert facade.submitted[0][1]["request"]["requested_effort"] == EFFORT_A


# --------------------------------------------------------------------------- #
# I. A-23 — a fresh negotiation immediately before every NEW admission
# --------------------------------------------------------------------------- #
def test_every_new_admission_renegotiates_server_info_before_its_pre_check(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    _attach(backend)
    assert facade.calls == ["server_info"], "composition negotiates exactly once"

    _dispatch(backend)
    _run_ended(facade)
    _dispatch(backend, dispatch_ref=DISPATCH_TWO)

    after_composition = facade.calls[1:]
    assert after_composition.count("server_info") == 2
    assert after_composition.count("submit") == 2
    # Each negotiation sits immediately before its own submit: nothing in
    # between could change the budget under the pre-check.
    for index, op in enumerate(after_composition):
        if op == "submit":
            assert after_composition[index - 1] == "server_info"


def test_a_lowered_budget_on_the_second_negotiation_rejects_the_second_new_admission_before_submit(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    handle = _attach(backend)
    ledger = _ledger(tmp_path)
    _dispatch(backend)
    assert facade.ops("submit") == 1

    _run_ended(facade)
    facade.budget = LOWERED_EVENT_BUDGET
    facade.submit_raises_from_call = 2  # a second submit fails the test outright

    with pytest.raises(SpineError) as excinfo:
        _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST

    # It renegotiated, refused, and never spent a submit.
    assert facade.ops("server_info") == 3
    assert facade.ops("submit") == 1
    # A refused pre-check writes no intent either.
    assert ledger.resolve_pending(TASK_ID, handle, DISPATCH_TWO) is None
    assert len(_ledger_document(tmp_path)["bindings"]) == 1


def test_admission_pre_check_uses_the_currently_negotiated_budget(
    tmp_path: Path,
) -> None:
    assert LOWERED_EVENT_BUDGET < FROZEN_LIMIT_PRODUCT <= NEGOTIATED_EVENT_BUDGET
    backend, facade, _ = _backend(tmp_path)
    _attach(backend)

    # A stale (composition-time) budget would admit this; the current one refuses.
    facade.budget = LOWERED_EVENT_BUDGET
    with pytest.raises(SpineError) as excinfo:
        _dispatch(backend)
    assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST
    assert facade.ops("submit") == 0

    facade.budget = NEGOTIATED_EVENT_BUDGET
    _dispatch(backend)
    assert facade.ops("submit") == 1


# --------------------------------------------------------------------------- #
# J. A-8 / A-24 — the explicit recovery entry point
# --------------------------------------------------------------------------- #
def _lose_the_ack(backend, facade, **dispatch_kwargs: Any):
    """Drive a genuinely lost ack: the daemon records, then the reply is lost."""

    facade.submit_error = _TransportLoss("reply never read")
    with pytest.raises(SpineError) as excinfo:
        _dispatch(backend, **dispatch_kwargs)
    assert excinfo.value.code == RUNTIME_ARSD_SUBMISSION_INDETERMINATE
    facade.submit_error = None
    return excinfo


def test_lost_ack_leaves_a_pending_intent_that_explicit_recovery_finalizes_exactly_once(
    tmp_path: Path,
) -> None:
    """A-8, in four beats, driven from a genuinely lost ack."""

    backend, facade, _ = _backend(tmp_path)
    handle = _attach(backend)

    # (1) the daemon accepts and records, then the reply is lost.
    _lose_the_ack(backend, facade)
    assert len(facade.admitted) == 1
    assert facade.ops("submit") == 1

    # (2) the intent written BEFORE that submit survives, read from a FRESH
    #     ledger instance over the same path.
    intent = _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_ONE)
    assert intent is not None
    assert intent.state == ARSD_BINDING_PENDING
    assert intent.request_id == derive_arsd_request_id(TASK_ID, handle, DISPATCH_ONE)
    assert intent.payload_digest == arsd_submit_payload_digest(facade.submitted[0][1])
    assert dict(intent.resolver_refs)["prompt_ref"] == PROMPT_REF
    assert _ledger(tmp_path).resolve(TASK_ID, handle, DISPATCH_ONE) is None

    # (3) the EXPLICIT recovery resends the byte-identical payload under the
    #     same request_id and the same digest.
    recovered = backend.recover_uncertain_submission(TASK_ID, DISPATCH_ONE, session_ref=SESSION_REF, turn_kind="prompt")
    assert facade.ops("submit") == 2
    first_request_id, first_payload = facade.submitted[0]
    second_request_id, second_payload = facade.submitted[1]
    assert second_request_id == first_request_id == intent.request_id
    assert second_payload == first_payload
    assert arsd_submit_payload_digest(second_payload) == intent.payload_digest

    # (4) it finalized THAT intent — one logical record — and a second
    #     recovery attempt fails closed.
    document = _ledger_document(tmp_path)
    assert len(document["bindings"]) == 1
    assert document["bindings"][0]["state"] == ARSD_BINDING_ACCEPTED
    binding = _ledger(tmp_path).resolve(TASK_ID, handle, DISPATCH_ONE)
    assert binding is not None
    assert recovered.result.run_ref == derive_run_ref(binding.run_id)
    assert recovered.result.supervisor_status == "accepted"
    with pytest.raises(SpineError) as second_attempt:
        backend.recover_uncertain_submission(TASK_ID, DISPATCH_ONE, session_ref=SESSION_REF, turn_kind="prompt")
    assert second_attempt.value.code == RUNTIME_ARSD_BINDING_CONFLICT
    assert facade.ops("submit") == 2


def test_same_request_recovery_does_not_renegotiate_and_bypasses_the_new_admission_pre_check(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    _attach(backend)
    _lose_the_ack(backend, facade)

    # Any negotiation on the recovery path fails the test outright, and the
    # budget that would refuse a NEW admission is in force.
    facade.server_info_error = AssertionError("recovery must not negotiate")
    facade.budget = LOWERED_EVENT_BUDGET
    negotiations_before = facade.ops("server_info")

    recovered = backend.recover_uncertain_submission(TASK_ID, DISPATCH_ONE, session_ref=SESSION_REF, turn_kind="prompt")

    assert recovered.result.supervisor_status == "accepted"
    assert facade.ops("server_info") == negotiations_before
    assert facade.ops("submit") == 2


def test_retry_after_a_budget_change_sends_the_identical_payload_digest(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    handle = _attach(backend)
    _lose_the_ack(backend, facade)
    intent = _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_ONE)
    assert intent is not None

    # The operator lowered the daemon's event budget in between.
    facade.budget = LOWERED_EVENT_BUDGET
    backend.recover_uncertain_submission(TASK_ID, DISPATCH_ONE, session_ref=SESSION_REF, turn_kind="prompt")

    first_payload = facade.submitted[0][1]
    second_payload = facade.submitted[1][1]
    assert second_payload == first_payload
    assert arsd_submit_payload_digest(second_payload) == intent.payload_digest
    # The frozen payload is never re-tuned to the new budget.
    assert second_payload["request"]["limits"] == _run_limits()


def test_uncertain_submission_recovery_bypasses_the_current_budget_pre_check(
    tmp_path: Path,
) -> None:
    """The non-vacuous scope proof for A-23/A-24, in four beats.

    Beat 1's submission is durably admitted **by the daemon** while Sachima
    never reads the reply — that is what leaves a recoverable intent carrying
    the ``request_id`` and payload digest beats 3 and 4 are measured against.
    """

    backend, facade, _ = _backend(tmp_path)
    handle = _attach(backend)

    # (1) admitted under the then-negotiated budget; request_id + digest recorded.
    _lose_the_ack(backend, facade)
    intent = _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_ONE)
    assert intent is not None
    assert len(facade.admitted) == 1

    # (2) the next negotiation returns a budget BELOW the frozen product.
    facade.budget = LOWERED_EVENT_BUDGET

    # (3) recovery resends the frozen payload unchanged and resolves through
    #     the daemon's durable admission record — no pre-check refusal.
    recovered = backend.recover_uncertain_submission(TASK_ID, DISPATCH_ONE, session_ref=SESSION_REF, turn_kind="prompt")
    assert recovered.result.supervisor_status == "accepted"
    assert facade.submitted[1] == (intent.request_id, facade.submitted[0][1])
    assert arsd_submit_payload_digest(facade.submitted[1][1]) == intent.payload_digest

    # (4) a DIFFERENT dispatch from the same run-limits entry still fails the
    #     current-budget pre-check, before any submit. The recovered Run is
    #     terminal, so §7.4 is not what refuses this one.
    _run_ended(facade)
    facade.submit_raises_from_call = 3
    with pytest.raises(SpineError) as excinfo:
        _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST
    assert facade.ops("submit") == 2
    assert _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_TWO) is None


def test_recovery_with_a_reconstruction_digest_mismatch_makes_zero_socket_calls(
    tmp_path: Path,
) -> None:
    backend, facade, resolver = _backend(tmp_path)
    handle = _attach(backend)
    _lose_the_ack(backend, facade)

    # The resolver no longer rebuilds what was recorded.
    resolver.prompts[PROMPT_REF] = "a prompt that is not the one we submitted"
    facade.hostile = True
    calls_before = list(facade.calls)

    with pytest.raises(SpineError) as excinfo:
        backend.recover_uncertain_submission(TASK_ID, DISPATCH_ONE, session_ref=SESSION_REF, turn_kind="prompt")
    assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT

    # ZERO socket calls: the mismatch is caught before any I/O.
    assert facade.calls == calls_before
    assert facade.ops("submit") == 1
    # The intent is left exactly as written — fail closed, never downgraded.
    intent = _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_ONE)
    assert intent is not None and intent.state == ARSD_BINDING_PENDING


# --------------------------------------------------------------------------- #
# K. A-25 — a reported CONFIG_FIDELITY terminal is an ordinary trusted failure
# --------------------------------------------------------------------------- #
def _config_fidelity_fixture(tmp_path: Path):
    """Its own fixture: never shared with A-13's or A-15's."""

    bundle = _port_bundle(tmp_path)
    backend, facade = bundle[0], bundle[1]
    _attach(backend)
    _dispatch(backend)
    facade.run_status_payload = {
        "result": _terminal_result("failed", reason="CONFIG_FIDELITY")
    }
    return bundle


def test_config_fidelity_terminal_is_an_ordinary_trusted_failure_with_no_agent_work_claimed(
    tmp_path: Path,
) -> None:
    backend, facade, registry, port, ref = _config_fidelity_fixture(tmp_path)
    handle = _attach(backend)
    submitted_before = list(facade.submitted)

    assert backend.observe_run(handle) == "failed"
    # The RUN failed. The Session it was configured for is untouched — the
    # mismatch is a reason to not run, never a reason to close a Session ARS
    # has no close operation for.
    assert backend.status(handle) == "running"
    observed = port.status(ref)
    assert observed.terminal is False

    # No agent work or partial progress is claimed: the Prompt was never sent.
    projected = list(port.stream(ref))
    types = [event["event_type"] for event in projected]
    assert types == ["task_created", "agent_attached"]
    assert all(event["counts"] == {} for event in projected)
    assert facade.ops("run_events") == 0

    # No automatic retry, no new request_id, no retry_of_run_id.
    assert facade.submitted == submitted_before
    assert facade.submitted[0][1]["retry_of_run_id"] is None

    # The token itself takes no branch: the same terminal without it is
    # exactly as failed.
    assert "CONFIG_FIDELITY" not in json.dumps(projected)
    facade.run_status_payload = {"result": _terminal_result("failed")}
    assert backend.observe_run(handle) == "failed"


# --------------------------------------------------------------------------- #
# L. Package surface — exported, and still not composed anywhere
# --------------------------------------------------------------------------- #
def test_p4_public_surface_is_exported_from_the_package() -> None:
    spine = importlib.import_module("sachima_supervisor.runtime_spine")
    mod = _mod()
    for name in (
        "ARSD_BACKEND_STABLE_CODES",
        "ARSD_TERMINAL_TO_NEUTRAL_STATUS",
        "ArsdLiveProgressReader",
        "ArsdSupervisorBackend",
        "derive_arsd_backend_handle",
        "map_arsd_terminal_to_neutral",
    ):
        assert getattr(spine, name) is getattr(mod, name), name
        assert name in spine.__all__, name
        assert name in mod.__all__, name

    # Every code this backend raises is a closed, Sachima-owned stable code.
    for code in mod.ARSD_BACKEND_STABLE_CODES:
        assert code == code.lower() and code.startswith("runtime_")


def test_arsd_is_the_only_admissible_turn_backend_after_the_retirement(
    tmp_path: Path,
) -> None:
    """P5 wires the backend — into exactly one composition root, still off.

    P4 could assert "composed by nothing"; P5 is the stage that composes it, so
    what is provable now is narrower and more useful: it is the *only* backend
    the factory allowlist admits, the dispatcher still names no concrete type,
    and the gateway still reaches it only through the composition root behind
    its own explicit knobs.
    """

    mod = _mod()
    turn_backend = importlib.import_module(
        "sachima_supervisor.runtime_spine.supervisor_turn_backend"
    )
    backend, _facade, _resolver = _backend(tmp_path)
    assert turn_backend.validate_supervisor_turn_backend(backend) is backend
    assert [kind for kind, _module, _attr in turn_backend._BACKEND_FACTORY_ALLOWLIST] == [
        "arsd"
    ]
    assert turn_backend._allowed_backend_types() == (mod.ArsdSupervisorBackend,)

    # The dispatcher names no concrete backend, and the gateway names none
    # either: it composes through the one root, which is where the enabled-only
    # gate lives.
    for module_name in (
        "sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher",
        "gateway.sachima_live_progress_binding",
    ):
        source = Path(
            importlib.import_module(module_name).__file__
        ).read_text(encoding="utf-8")
        assert "ArsdSupervisorBackend" not in source, module_name
        assert "arsd_supervisor_backend" not in source, module_name

    # And composing that root without an enabled config is refused outright.
    binding_mod = importlib.import_module(
        "sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding"
    )
    with pytest.raises(SpineError) as excinfo:
        binding_mod.bind_arsd_execution(_config(tmp_path, enabled=False))
    assert excinfo.value.code == "runtime_arsd_disabled"


def test_an_unresolved_intent_blocks_the_next_turn_until_recovery_resolves_it(
    tmp_path: Path,
) -> None:
    """Spec §7.3.1: the dispatch stays blocked until an EXPLICIT decision.

    The ordinary path may neither resend the uncertain dispatch nor fork a
    second Run around it — both would double-dispatch work the daemon may
    already be running.
    """

    backend, facade, _ = _backend(tmp_path)
    _attach(backend)
    _lose_the_ack(backend, facade)
    assert facade.ops("submit") == 1

    # Re-dispatching the same turn is not that decision.
    with pytest.raises(SpineError) as same_dispatch:
        _dispatch(backend)
    assert same_dispatch.value.code == RUNTIME_ARSD_BINDING_CONFLICT
    # Nor is dispatching a different turn of the same task.
    with pytest.raises(SpineError) as other_dispatch:
        _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert other_dispatch.value.code == RUNTIME_ARSD_BINDING_CONFLICT
    # Both refusals are decided before any socket call is made.
    assert facade.ops("submit") == 1
    assert facade.ops("session_status") == 0

    # The explicit entry point resolves it, and — once that Run is over — the
    # task dispatches again.
    backend.recover_uncertain_submission(TASK_ID, DISPATCH_ONE, session_ref=SESSION_REF, turn_kind="prompt")
    _run_ended(facade)
    _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert facade.ops("submit") == 3


# --------------------------------------------------------------------------- #
# M. Durable reattachment — a restart observes the persisted Run, never a
#    fabricated one (formal-review blocker 1)
# --------------------------------------------------------------------------- #
def _persisted_run(tmp_path: Path) -> str:
    """Dispatch one accepted turn, then let that backend instance go."""

    backend, _facade, _resolver = _backend(tmp_path)
    _attach(backend)
    return _dispatch(backend).private_locator


def test_a_fresh_backend_attaching_an_existing_task_observes_the_persisted_run(
    tmp_path: Path,
) -> None:
    run_id = _persisted_run(tmp_path)

    # A brand-new process: same ledger path, empty in-memory state.
    fresh, facade, _resolver = _backend(tmp_path)
    handle = fresh.attach_existing(TASK_ID)
    facade.run_status_payload = {"result": _terminal_result("completed")}

    observed = fresh.observe_run(handle)

    # It read the durable binding and asked about THAT run — it did not
    # fabricate a verdict from an empty entry.
    assert facade.ops("run_status") == 1
    assert facade.run_targets == [("run_status", run_id)]
    assert observed == "completed"
    # And the Session that Run ran in survived the restart with it.
    assert fresh.status(handle) == "running"


def test_a_fresh_backend_cancels_the_persisted_run_by_its_recorded_id(
    tmp_path: Path,
) -> None:
    run_id = _persisted_run(tmp_path)

    fresh, facade, _resolver = _backend(tmp_path)
    handle = fresh.attach_existing(TASK_ID)
    facade.run_cancel_payload = {
        "status": "cancelled",
        "result": _terminal_result("cancelled"),
    }

    assert fresh.kill(handle, "ref_cancelled") == "cancelled"
    assert ("run_cancel", run_id) in facade.run_targets
    assert facade.ops("run_cancel") == 1


def test_create_or_attach_over_an_existing_ledger_hydrates_the_persisted_run(
    tmp_path: Path,
) -> None:
    """The port's own attach path reconciles too, not just attach_existing."""

    run_id = _persisted_run(tmp_path)

    fresh, facade, _resolver = _backend(tmp_path)
    handle = _attach(fresh)
    facade.run_status_payload = {"result": _terminal_result("failed")}

    assert fresh.observe_run(handle) == "failed"
    assert facade.run_targets == [("run_status", run_id)]


def test_reattachment_targets_the_latest_accepted_binding_not_the_lexical_last(
    tmp_path: Path,
) -> None:
    """`latest` is the acceptance instant, not the key that sorts last."""

    backend, facade, _resolver = _backend(tmp_path)
    _attach(backend)
    # The lexically LAST dispatch ref is accepted FIRST, and earlier.
    facade.accepted_at = "2026-08-17T04:05:06+00:00"
    first = _dispatch(backend, dispatch_ref=DISPATCH_TWO).private_locator
    _run_ended(facade)
    facade.accepted_at = "2026-08-17T06:07:08+00:00"
    latest = _dispatch(backend, dispatch_ref=DISPATCH_ONE).private_locator
    assert first != latest

    fresh, fresh_facade, _fresh_resolver = _backend(tmp_path)
    handle = fresh.attach_existing(TASK_ID)
    fresh_facade.run_status_payload = {"progress": {"phase": "tooling"}}
    fresh.status(handle)

    assert fresh_facade.run_targets == [("run_status", latest)]


def test_attaching_a_task_with_no_accepted_binding_still_fails_closed(
    tmp_path: Path,
) -> None:
    """Hydration never invents a Session for a task that has none."""

    fresh, facade, _resolver = _backend(tmp_path)
    with pytest.raises(SpineError) as excinfo:
        fresh.attach_existing(TASK_ID)
    assert excinfo.value.code == "runtime_invalid_session"
    assert facade.ops("run_status") == 0


# --------------------------------------------------------------------------- #
# N. Ack correlation — a reuse ack must name the Session we asked for
#    (formal-review blocker 2)
# --------------------------------------------------------------------------- #
OTHER_ARS_SESSION = "SESSCANARYP40e5d4c3b"


def test_a_reuse_ack_naming_a_different_session_is_a_protocol_violation(
    tmp_path: Path,
) -> None:
    backend, facade, _resolver = _backend(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    ledger = _ledger(tmp_path)
    assert ledger.resolve(TASK_ID, handle, DISPATCH_ONE) is not None

    # The reuse submit names the recorded Session; the ack names another one.
    _run_ended(facade)
    facade.ars_session_id = OTHER_ARS_SESSION
    with pytest.raises(SpineError) as excinfo:
        _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert excinfo.value.code == "runtime_arsd_protocol_violation"
    assert OTHER_ARS_SESSION not in _rendered(excinfo)

    # The request really did ask for the recorded Session...
    assert facade.submitted[-1][1]["request"]["session_id"] == ARS_SESSION_CANARY
    # ...and the intent is left exactly as written: pending, never finalized.
    intent = _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_TWO)
    assert intent is not None and intent.state == ARSD_BINDING_PENDING
    assert _ledger(tmp_path).resolve(TASK_ID, handle, DISPATCH_TWO) is None


def test_recovery_ack_naming_a_different_session_is_a_protocol_violation(
    tmp_path: Path,
) -> None:
    backend, facade, _resolver = _backend(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    _run_ended(facade)
    # A reuse turn whose ack is lost, then recovered against a wrong Session.
    _lose_the_ack(backend, facade, dispatch_ref=DISPATCH_TWO)
    facade.ars_session_id = OTHER_ARS_SESSION
    facade.admitted.clear()

    with pytest.raises(SpineError) as excinfo:
        backend.recover_uncertain_submission(TASK_ID, DISPATCH_TWO, session_ref=SESSION_REF, turn_kind="prompt")
    assert excinfo.value.code == "runtime_arsd_protocol_violation"

    intent = _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_TWO)
    assert intent is not None and intent.state == ARSD_BINDING_PENDING


def test_create_mode_accepts_the_session_the_ack_creates(tmp_path: Path) -> None:
    """Omission has nothing to correlate: the ack's Session is the answer."""

    backend, facade, _resolver = _backend(tmp_path)
    handle = _attach(backend)
    facade.ars_session_id = OTHER_ARS_SESSION

    _dispatch(backend)

    assert "session_id" not in facade.submitted[0][1]["request"]
    binding = _ledger(tmp_path).resolve(TASK_ID, handle, DISPATCH_ONE)
    assert binding is not None
    assert binding.ars_session_id == OTHER_ARS_SESSION


# --------------------------------------------------------------------------- #
# O. Durable identity reconciliation — a restart may not re-bind a task's
#    stable identity underneath it (second formal-review blocker 1)
# --------------------------------------------------------------------------- #
def _pending_intent_task(tmp_path: Path) -> None:
    """Leave one task holding an unresolved pending intent and nothing else."""

    backend, facade, _resolver = _backend(tmp_path)
    _attach(backend)
    _lose_the_ack(backend, facade)


def test_a_fresh_backend_refuses_a_persisted_task_under_a_changed_workspace(
    tmp_path: Path,
) -> None:
    _persisted_run(tmp_path)

    fresh, facade, _resolver = _backend(tmp_path)
    before = list(facade.calls)
    with pytest.raises(SpineError) as excinfo:
        fresh.create_or_attach(TASK_ID, REFS_OTHER_WORKSPACE)

    assert excinfo.value.code == RUNTIME_ARSD_POLICY_DENIED
    # Refused before any Session or Run operation is attempted.
    assert facade.calls == before
    assert OTHER_WORKSPACE_CANARY not in _rendered(excinfo)


def test_a_fresh_backend_refuses_a_persisted_task_under_a_changed_agent(
    tmp_path: Path,
) -> None:
    _persisted_run(tmp_path)

    fresh, facade, _resolver = _backend(tmp_path)
    before = list(facade.calls)
    with pytest.raises(SpineError) as excinfo:
        fresh.create_or_attach(TASK_ID, REFS_OTHER_AGENT)

    assert excinfo.value.code == RUNTIME_ARSD_POLICY_DENIED
    assert facade.calls == before


def test_a_fresh_backend_refuses_a_persisted_task_under_a_changed_grant(
    tmp_path: Path,
) -> None:
    """Grant identity is host config, not a caller ref — and it is checked."""

    _persisted_run(tmp_path)

    fresh, facade, _resolver = _backend(
        tmp_path, grant_hash="sha256:" + "f" * 64
    )
    before = list(facade.calls)
    with pytest.raises(SpineError) as excinfo:
        _attach(fresh)

    assert excinfo.value.code == RUNTIME_ARSD_POLICY_DENIED
    assert facade.calls == before


def test_a_pending_intent_task_is_refused_under_a_changed_identity_before_recovery(
    tmp_path: Path,
) -> None:
    """The explicit-recovery path is unreachable under a changed identity.

    A task whose only durable record is a pending intent still states the
    workspace/agent/grant it was admitted under; a restart that disagrees
    fails closed at attach, so recovery never resends under an identity the
    operator has since changed.
    """

    _pending_intent_task(tmp_path)

    fresh, facade, _resolver = _backend(tmp_path)
    before = list(facade.calls)
    with pytest.raises(SpineError) as excinfo:
        fresh.create_or_attach(TASK_ID, REFS_OTHER_WORKSPACE)
    assert excinfo.value.code == RUNTIME_ARSD_POLICY_DENIED
    assert facade.calls == before
    assert facade.ops("submit") == 0

    # And with the identity unchanged, recovery still works normally.
    same, same_facade, _same_resolver = _backend(tmp_path)
    handle = _attach(same)
    recovered = same.recover_uncertain_submission(TASK_ID, DISPATCH_ONE, session_ref=SESSION_REF, turn_kind="prompt")
    assert recovered.result.supervisor_status == "accepted"
    assert _ledger(tmp_path).resolve(TASK_ID, handle, DISPATCH_ONE) is not None


def test_per_run_refs_may_still_change_across_a_restart(tmp_path: Path) -> None:
    """Positive control: model / effort / run-limits are per-Run, not identity."""

    _persisted_run(tmp_path)

    fresh, facade, _resolver = _backend(tmp_path)
    handle = fresh.create_or_attach(TASK_ID, REFS_SECOND_PAIR)
    assert handle == derive_arsd_backend_handle(TASK_ID)

    _run_ended(facade)
    _dispatch(fresh, dispatch_ref=DISPATCH_TWO)
    _request_id, payload = facade.submitted[-1]
    assert payload["request"]["requested_model"] == MODEL_B
    assert payload["request"]["requested_effort"] == EFFORT_B
    assert payload["request"]["session_id"] == ARS_SESSION_CANARY


# --------------------------------------------------------------------------- #
# P. Equal acceptance instants — no lexical guess (blocker 2)
# --------------------------------------------------------------------------- #
def test_equal_acceptance_timestamps_fail_closed_rather_than_guessing_a_latest(
    tmp_path: Path,
) -> None:
    """Two accepted Runs, one instant, reverse lexical order: no target is guessed.

    The lexically last key belongs to the run accepted FIRST here, so a key
    tiebreak would not merely be arbitrary — it would observe and cancel the
    wrong Run.
    """

    backend, facade, _resolver = _backend(tmp_path)
    _attach(backend)
    older = _dispatch(backend, dispatch_ref=DISPATCH_TWO).private_locator
    _run_ended(facade)
    newer = _dispatch(backend, dispatch_ref=DISPATCH_ONE).private_locator
    assert older != newer
    # Both acks carried the same instant, and the lexical last is the older.
    document = _ledger_document(tmp_path)
    stamps = {record["accepted_at"] for record in document["bindings"]}
    assert len(stamps) == 1

    fresh, fresh_facade, _fresh_resolver = _backend(tmp_path)
    with pytest.raises(SpineError) as attach_exc:
        fresh.attach_existing(TASK_ID)
    assert attach_exc.value.code == RUNTIME_ARSD_BINDING_CONFLICT

    other, other_facade, _other_resolver = _backend(tmp_path)
    with pytest.raises(SpineError) as create_exc:
        _attach(other)
    assert create_exc.value.code == RUNTIME_ARSD_BINDING_CONFLICT

    # No Run was observed or cancelled — right one or wrong one.
    assert fresh_facade.run_targets == []
    assert other_facade.run_targets == []


def test_a_single_accepted_run_at_that_instant_still_reattaches(
    tmp_path: Path,
) -> None:
    """Non-vacuity: the tie guard fires on a tie, not on every restart."""

    run_id = _persisted_run(tmp_path)
    fresh, facade, _resolver = _backend(tmp_path)
    handle = fresh.attach_existing(TASK_ID)
    facade.run_status_payload = {"progress": {"phase": "tooling"}}
    assert fresh.status(handle) == "running"
    assert facade.run_targets == [("run_status", run_id)]


# --------------------------------------------------------------------------- #
# Q. An unresolved intent makes the task's CURRENT Run unknowable — nothing is
#    observed or cancelled until recovery says which Run it is (third
#    formal-review blocker 1)
# --------------------------------------------------------------------------- #
def _accepted_then_pending(tmp_path: Path, *, cause: str):
    """One accepted Run A, then a dispatch B left pending by `cause`."""

    backend, facade, _resolver = _backend(tmp_path)
    handle = _attach(backend)
    facade.accepted_at = "2026-08-17T04:05:06+00:00"
    accepted = _dispatch(backend).private_locator
    _run_ended(facade)
    facade.accepted_at = "2026-08-17T06:07:08+00:00"

    if cause == "lost_ack":
        _lose_the_ack(backend, facade, dispatch_ref=DISPATCH_TWO)
    else:
        # A reuse ack naming another Session: refused, intent left pending.
        facade.ars_session_id = OTHER_ARS_SESSION
        with pytest.raises(SpineError) as excinfo:
            _dispatch(backend, dispatch_ref=DISPATCH_TWO)
        assert excinfo.value.code == "runtime_arsd_protocol_violation"
        facade.ars_session_id = ARS_SESSION_CANARY
        facade.admitted.clear()

    assert _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_TWO) is not None
    return backend, facade, handle, accepted


@pytest.mark.parametrize("cause", ["lost_ack", "mismatched_session"])
def test_a_pending_intent_after_an_accepted_run_blocks_observation_and_cancel(
    tmp_path: Path, cause: str
) -> None:
    """The older Run is not this task's answer while a newer one is uncertain.

    The pending submit may have been accepted remotely, so observing or
    cancelling the older Run would report — or end — the wrong one.
    """

    backend, facade, handle, accepted = _accepted_then_pending(tmp_path, cause=cause)
    facade.run_targets.clear()
    status_before = facade.ops("run_status")
    cancel_before = facade.ops("run_cancel")

    for probe in (
        lambda: backend.status(handle),
        lambda: backend.liveness(handle),
        lambda: backend.kill(handle, "ref_cancelled"),
    ):
        with pytest.raises(SpineError) as excinfo:
            probe()
        assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT

    # Zero observation, zero cancellation: not of the older Run, not of any.
    assert facade.ops("run_status") == status_before
    assert facade.ops("run_cancel") == cancel_before
    assert facade.run_targets == []

    # Explicit recovery is what resolves it — and then B is the target.
    newer = backend.recover_uncertain_submission(TASK_ID, DISPATCH_TWO, session_ref=SESSION_REF, turn_kind="prompt").private_locator
    assert newer != accepted
    facade.run_status_payload = {"progress": {"phase": "tooling"}}
    assert backend.status(handle) == "running"
    assert facade.run_targets == [("run_status", newer)]

    facade.run_cancel_payload = {
        "status": "cancelled",
        "result": _terminal_result("cancelled"),
    }
    assert backend.kill(handle, "ref_cancelled") == "cancelled"
    assert ("run_cancel", newer) in facade.run_targets
    assert ("run_cancel", accepted) not in facade.run_targets


def test_a_fresh_backend_also_blocks_observation_while_an_intent_is_unresolved(
    tmp_path: Path,
) -> None:
    """A restart inherits the ambiguity from the ledger, not from memory."""

    _accepted_then_pending(tmp_path, cause="lost_ack")

    fresh, facade, _resolver = _backend(tmp_path)
    # Attaching still works: recovery has to stay reachable after a restart.
    handle = fresh.attach_existing(TASK_ID)

    for probe in (
        lambda: fresh.status(handle),
        lambda: fresh.liveness(handle),
        lambda: fresh.kill(handle, "ref_cancelled"),
    ):
        with pytest.raises(SpineError) as excinfo:
            probe()
        assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT
    assert facade.run_targets == []

    newer = fresh.recover_uncertain_submission(
        TASK_ID, DISPATCH_TWO, session_ref=SESSION_REF, turn_kind="prompt"
    ).private_locator
    facade.run_status_payload = {"progress": {"phase": "tooling"}}
    assert fresh.status(handle) == "running"
    assert facade.run_targets == [("run_status", newer)]


# --------------------------------------------------------------------------- #
# R. Spec §7.4 — at most one ACTIVE Run per task/Session (P5 hard pre-wiring)
#
#    P4 left this open: it needs terminal truth, and no P4 row named it. P5
#    closes it, because the composition root that wires the backend is where a
#    second dispatch becomes reachable.
# --------------------------------------------------------------------------- #
def _accepted_nonterminal(tmp_path: Path):
    """One accepted Run that the daemon reports as still going."""

    backend, facade, _resolver = _backend(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    facade.run_status_payload = {"progress": {"phase": "tooling"}}
    return backend, facade, handle


def test_a_second_dispatch_is_refused_while_the_recorded_run_is_not_terminal(
    tmp_path: Path,
) -> None:
    """An accepted, unfinished Run blocks the next one — locally, before I/O."""

    backend, facade, handle = _accepted_nonterminal(tmp_path)
    submits_before = facade.ops("submit")
    facade.submit_raises_from_call = 2  # a second submit fails the test outright

    with pytest.raises(SpineError) as excinfo:
        _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT

    # Nothing was spent and nothing durable was written: no second intent, no
    # second submit, one record.
    assert facade.ops("submit") == submits_before
    assert _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_TWO) is None
    assert len(_ledger_document(tmp_path)["bindings"]) == 1
    # The refusal is decided before the admission sequence starts: no fresh
    # negotiation and no Session read were spent on a dispatch that cannot run.
    assert facade.ops("server_info") == 2  # composition + the first admission
    assert RUN_ID_CANARY not in _rendered(excinfo)


def test_the_exclusion_admits_the_next_dispatch_once_the_run_is_proven_over(
    tmp_path: Path,
) -> None:
    """Non-vacuity: the guard fires on an active Run, not on every second turn."""

    backend, facade, handle = _accepted_nonterminal(tmp_path)
    with pytest.raises(SpineError):
        _dispatch(backend, dispatch_ref=DISPATCH_TWO)

    _run_ended(facade)
    second = _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert second.result.supervisor_status == "accepted"
    assert facade.ops("submit") == 2
    assert _ledger(tmp_path).resolve(TASK_ID, handle, DISPATCH_TWO) is not None


@pytest.mark.parametrize(
    "payload, error",
    [
        # An observation that failed is not evidence the Run ended.
        (None, RUNTIME_ARSD_UNAVAILABLE),
        # A body with no status on the closed vocabulary is untrusted.
        ("untrusted", RUNTIME_ARSD_INTERNAL),
    ],
)
def test_observation_uncertainty_refuses_the_next_dispatch_rather_than_admitting(
    tmp_path: Path, payload: Any, error: str
) -> None:
    """Not knowing whether a Run ended is never a licence to start another."""

    backend, facade, handle = _accepted_nonterminal(tmp_path)
    if payload is None:
        facade.run_status_error = _TransportLoss("the daemon went away mid-read")
    else:
        facade.run_status_payload = {"result": {"phase": "who knows"}}
    facade.submit_raises_from_call = 2

    with pytest.raises(SpineError) as excinfo:
        _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert excinfo.value.code == error

    assert facade.ops("submit") == 1
    assert _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_TWO) is None
    assert len(_ledger_document(tmp_path)["bindings"]) == 1
    assert "the daemon went away mid-read" not in _rendered(excinfo)


def test_concurrent_dispatches_of_one_task_yield_one_record_and_one_submit(
    tmp_path: Path,
) -> None:
    """The race the exclusion exists for: two dispatches, one Run.

    Both threads enter ``run_turn`` at the same instant against a task with no
    Run yet, so nothing but the backend's own serialization can stop them both
    from admitting one. Whichever wins, the other must find its Run and fail
    closed — never write a second pending intent, never spend a second submit.
    """

    backend, facade, _resolver = _backend(tmp_path)
    handle = _attach(backend)
    # The Run the winner starts is reported as still going, so the loser's
    # exclusion has an active Run to find. The winner dwells inside its submit,
    # which is precisely the window an unserialized second dispatch would use:
    # the record that would stop it does not exist yet.
    facade.run_status_payload = {"progress": {"phase": "tooling"}}
    facade.submit_dwell_seconds = 0.25

    start = threading.Barrier(2)
    outcomes: list[Any] = []
    lock = threading.Lock()

    def _race(dispatch_ref: str) -> None:
        start.wait(timeout=10)
        try:
            result = _dispatch(backend, dispatch_ref=dispatch_ref)
        except SpineError as exc:  # noqa: PERF203 - one attempt per thread
            result = exc
        with lock:
            outcomes.append(result)

    threads = [
        threading.Thread(target=_race, args=(ref,))
        for ref in (DISPATCH_ONE, DISPATCH_TWO)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    accepted = [item for item in outcomes if isinstance(item, DispatchedSupervisorTurn)]
    refused = [item for item in outcomes if isinstance(item, SpineError)]
    assert len(accepted) == 1 and len(refused) == 1
    assert refused[0].code == RUNTIME_ARSD_BINDING_CONFLICT

    # One submit, one ledger record, one Run.
    assert facade.ops("submit") == 1
    document = _ledger_document(tmp_path)
    assert len(document["bindings"]) == 1
    assert document["bindings"][0]["state"] == ARSD_BINDING_ACCEPTED
    assert len(facade.admitted) == 1
    # The loser wrote no intent under its own key either.
    for dispatch_ref in (DISPATCH_ONE, DISPATCH_TWO):
        assert _ledger(tmp_path).resolve_pending(TASK_ID, handle, dispatch_ref) is None


# --------------------------------------------------------------------------- #
# S. A Run terminal is not a Session terminal (P5 core repair)
#
#    Spec §6 gives ARS Sessions no close operation, and §7.4 bounds *Runs*, not
#    Sessions. So the Session-facing surface the port drives must not project a
#    Run's terminal as the task's: a task whose Run ended is a task with a live,
#    reusable Session and nothing running in it. The Run's own terminal stays
#    honest on the Run-facing surface.
# --------------------------------------------------------------------------- #
def _completed_run(tmp_path: Path):
    """One dispatched Run the daemon reports as completed."""

    backend, facade, registry, port, ref = _port_bundle(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    facade.run_status_payload = {"result": _terminal_result("completed")}
    return backend, facade, registry, port, ref, handle


def test_a_run_terminal_leaves_the_durable_session_live_and_reusable(
    tmp_path: Path,
) -> None:
    backend, facade, registry, port, ref, handle = _completed_run(tmp_path)

    # Run-facing: the real neutral terminal, undiluted.
    assert backend.observe_run(handle) == "completed"
    # Session-facing: the Session is live, because ARS never closed it and
    # Sachima has no close operation to reach for.
    assert backend.status(handle) == "running"
    assert backend.liveness(handle) == "running"

    observed = port.status(ref)
    assert observed.state == "running"
    assert observed.terminal is False
    assert observed.alive is True
    snapshot = registry.snapshot(TASK_ID)
    assert snapshot["status"] == "running"
    assert snapshot["terminal"] is False


@pytest.mark.parametrize("terminal", list(ARSD_TERMINAL_STATUSES))
def test_no_run_terminal_of_any_kind_terminalizes_the_task(
    tmp_path: Path, terminal: str
) -> None:
    """All five, including the ones that used to reach `failed`/`ambiguous`."""

    backend, facade, registry, port, ref = _port_bundle(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    facade.run_status_payload = {"result": _terminal_result(terminal)}

    # The Run's own terminal is reported exactly, on the Run-facing surface.
    assert backend.observe_run(handle) == terminal
    # The task is not over because a Run is.
    assert backend.status(handle) == "running"
    assert port.status(ref).terminal is False
    assert registry.snapshot(TASK_ID)["terminal"] is False


def test_terminal_truth_clears_the_active_run_and_admits_the_next_one(
    tmp_path: Path,
) -> None:
    """§7.4 bounds concurrency, not conversation length."""

    backend, facade, _registry, _port, _ref, handle = _completed_run(tmp_path)
    ledger = _ledger(tmp_path)

    # Reconciling through the Session-facing surface is enough to clear it.
    assert backend.status(handle) == "running"
    second = _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert second.result.supervisor_status == "accepted"
    assert facade.ops("submit") == 2

    # Two Runs, one Session, two durable records.
    assert ledger.resolve(TASK_ID, handle, DISPATCH_ONE) is not None
    assert ledger.resolve(TASK_ID, handle, DISPATCH_TWO) is not None
    assert facade.submitted[1][1]["request"]["session_id"] == ARS_SESSION_CANARY
    assert len({entry["session_id"] for entry in facade.admitted.values()}) == 1


def test_a_dispatch_admits_itself_without_a_prior_status_read(tmp_path: Path) -> None:
    """The exclusion reconciles for itself: no caller has to poll first."""

    backend, facade, _registry, _port, _ref, _handle = _completed_run(tmp_path)
    _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert facade.ops("submit") == 2


def test_a_cancelled_run_terminal_nobody_asked_for_does_not_end_the_task(
    tmp_path: Path,
) -> None:
    """Only Sachima's own explicit cancel is a task lifecycle decision."""

    backend, facade, registry, port, ref = _port_bundle(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    facade.run_status_payload = {"result": _terminal_result("cancelled")}

    assert backend.observe_run(handle) == "cancelled"
    assert backend.status(handle) == "running"
    assert port.status(ref).terminal is False
    assert facade.ops("run_cancel") == 0


def test_only_an_explicit_kill_terminalizes_the_task(tmp_path: Path) -> None:
    backend, facade, registry, port, ref = _port_bundle(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    facade.run_cancel_payload = {
        "status": "cancelled",
        "result": _terminal_result("cancelled"),
    }

    assert backend.kill(handle, "ref_cancelled") == "cancelled"
    assert backend.status(handle) == "cancelled"
    assert port.status(ref).terminal is True
    assert registry.snapshot(TASK_ID)["status"] == "cancelled"
    # It cancelled the Run and nothing else — there is no Session operation.
    assert facade.ops("run_cancel") == 1
    assert facade.ops("session_status") <= 1


def test_kill_between_turns_ends_the_task_without_inventing_a_session_close(
    tmp_path: Path,
) -> None:
    """With no Run live there is nothing to cancel remotely — and no close.

    Ending the task is Sachima's own decision about its own Session binding:
    it stops dispatching into it. Reaching for a Session operation to make it
    feel terminal would be inventing one ARS does not have.
    """

    backend, facade, _registry, port, ref, handle = _completed_run(tmp_path)
    assert backend.status(handle) == "running"
    cancels_before = facade.ops("run_cancel")

    assert backend.kill(handle, "ref_cancelled") == "cancelled"
    assert facade.ops("run_cancel") == cancels_before
    assert facade.ops("session_list") == 0
    assert backend.status(handle) == "cancelled"
    assert port.status(ref).terminal is True


def test_observe_run_reports_accepted_while_the_run_is_still_going(
    tmp_path: Path,
) -> None:
    backend, facade, _registry, _port, _ref = _port_bundle(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    facade.run_status_payload = {"progress": {"phase": "tooling"}}

    assert backend.observe_run(handle) == "accepted"
    assert backend.observe_run(handle) in SUPERVISOR_TURN_STATUSES
    assert backend.status(handle) == "running"


def test_observe_run_keeps_the_terminal_after_the_session_reconciled_it_away(
    tmp_path: Path,
) -> None:
    """The Run's verdict outlives the Run being cleared as the active one."""

    backend, facade, _registry, _port, _ref, handle = _completed_run(tmp_path)
    assert backend.status(handle) == "running"  # clears the active Run
    reads_before = facade.ops("run_status")

    assert backend.observe_run(handle) == "completed"
    # It is remembered, not re-asked: the daemon may already have forgotten it.
    assert facade.ops("run_status") == reads_before


def test_observe_run_on_a_task_that_has_dispatched_nothing_is_not_a_verdict(
    tmp_path: Path,
) -> None:
    backend, _facade, _resolver = _backend(tmp_path)
    handle = _attach(backend)
    assert backend.observe_run(handle) is None
    assert backend.status(handle) == "running"


def test_an_observation_failure_still_refuses_rather_than_reporting_live(
    tmp_path: Path,
) -> None:
    """Session-facing does not mean optimistic: not observing is not knowing."""

    backend, facade, _registry, _port, _ref = _port_bundle(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    facade.run_status_error = _TransportLoss("connection reset")

    for probe in (
        lambda: backend.status(handle),
        lambda: backend.liveness(handle),
        lambda: backend.observe_run(handle),
    ):
        with pytest.raises(SpineError) as excinfo:
            probe()
        assert excinfo.value.code == RUNTIME_ARSD_UNAVAILABLE
        assert "connection reset" not in _rendered(excinfo)


def test_an_explicitly_cancelled_task_refuses_a_new_dispatch(tmp_path: Path) -> None:
    """The other side of the Session/Run split: kill really does end the task.

    Making a Run terminal harmless to the Session opens exactly one hole — a
    dispatch after an explicit cancel would silently resurrect work an upper
    layer ended. It is refused before any socket call, with the spine's
    no-session code.
    """

    backend, facade, _resolver = _backend(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)
    facade.run_cancel_payload = {
        "status": "cancelled",
        "result": _terminal_result("cancelled"),
    }
    assert backend.kill(handle, "ref_cancelled") == "cancelled"
    submits_before = facade.ops("submit")

    with pytest.raises(SpineError) as excinfo:
        _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert excinfo.value.code == RUNTIME_INVALID_SESSION
    assert facade.ops("submit") == submits_before
    assert _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_TWO) is None
    assert len(_ledger_document(tmp_path)["bindings"]) == 1


# --------------------------------------------------------------------------- #
# T. Admission vs cancel — one per-task lock covers both (final-review blocker 1)
# --------------------------------------------------------------------------- #
def test_a_kill_cannot_be_overtaken_by_an_admission_already_in_flight(
    tmp_path: Path,
) -> None:
    """An in-flight admission and a cancel are one decision, not two.

    The dangerous interleaving is narrow and real: a ``run_turn`` parked
    between the active-Run exclusion and its first durable write looks, to a
    concurrent ``kill``, exactly like a task with nothing running. If the
    cancel decides on that view it ends an empty task, returns ``cancelled``,
    and then the parked admission submits anyway and clears the cancel on its
    way through — a Run started after the task was ended, and reported as
    running.

    Both sequences therefore run under the same per-task admission lock: the
    cancel waits for the admission it cannot see, and then cancels the Run it
    produced.
    """

    backend, facade, _resolver = _backend(tmp_path)
    handle = _attach(backend)
    facade.run_cancel_payload = {
        "status": "cancelled",
        "result": _terminal_result("cancelled"),
    }
    # Composition already negotiated once; only a dispatch-time negotiation
    # should be waited on.
    facade.server_info_started.clear()
    facade.server_info_gate = threading.Event()

    outcomes: dict[str, Any] = {}

    def _admit() -> None:
        try:
            outcomes["dispatch"] = _dispatch(backend)
        except SpineError as exc:  # pragma: no cover - a failure is asserted below
            outcomes["dispatch"] = exc

    def _cancel() -> None:
        try:
            outcomes["kill"] = backend.kill(handle, "ref_cancelled")
        except SpineError as exc:  # pragma: no cover - a failure is asserted below
            outcomes["kill"] = exc

    admit = threading.Thread(target=_admit)
    admit.start()
    assert facade.server_info_started.wait(timeout=5)
    cancel = threading.Thread(target=_cancel)
    cancel.start()
    facade.server_info_gate.set()
    for thread in (admit, cancel):
        thread.join(timeout=30)
        assert not thread.is_alive()

    assert isinstance(outcomes["dispatch"], DispatchedSupervisorTurn)
    assert outcomes["kill"] == "cancelled"

    # One submit, and the cancel really cancelled the Run that submit created —
    # it did not end an empty task and leave a live Run behind it.
    assert facade.ops("submit") == 1
    assert facade.ops("run_cancel") == 1
    assert facade.calls.index("submit") < facade.calls.index("run_cancel")

    # The task stays ended, and nothing may be submitted into it afterwards.
    assert backend.status(handle) == "cancelled"
    with pytest.raises(SpineError) as excinfo:
        _dispatch(backend, dispatch_ref=DISPATCH_TWO)
    assert excinfo.value.code == RUNTIME_INVALID_SESSION
    assert facade.ops("submit") == 1


def test_the_durable_handoff_of_the_latest_accepted_run_needs_no_socket_call(
    tmp_path: Path,
) -> None:
    """What a restart rebinds a read-model source from (blocker 3).

    It is a ledger read and nothing else: refs-only public half, the private
    ``run_id`` on the handoff, zero daemon operations, and no submit.
    """

    run_id = _persisted_run(tmp_path)

    fresh, facade, _resolver = _backend(tmp_path)
    handle = fresh.attach_existing(TASK_ID)
    calls_before = list(facade.calls)

    handoff = fresh.latest_accepted_turn(TASK_ID, session_ref=SESSION_REF)
    assert isinstance(handoff, DispatchedSupervisorTurn)
    assert handoff.private_locator == run_id
    assert handoff.result.source_kind == SOURCE_KIND_ARSD_RUN
    assert handoff.result.run_ref.startswith("run_")
    assert handoff.result.foreign_cursor is None
    assert facade.calls == calls_before
    assert facade.ops("submit") == 0

    # The raw id never reaches the safe half.
    assert run_id not in serialize_supervisor_turn_result(handoff.result).decode("utf-8")
    _ = handle


def test_a_task_with_nothing_accepted_has_no_durable_handoff(tmp_path: Path) -> None:
    backend, facade, _resolver = _backend(tmp_path)
    _attach(backend)
    assert backend.latest_accepted_turn(TASK_ID, session_ref=SESSION_REF) is None
    assert facade.ops("submit") == 0


def test_the_durable_handoff_fails_closed_while_an_intent_is_unresolved(
    tmp_path: Path,
) -> None:
    """An older Run is not the answer while a newer one is uncertain."""

    backend, _facade, handle, _accepted = _accepted_then_pending(
        tmp_path, cause="lost_ack"
    )
    with pytest.raises(SpineError) as excinfo:
        backend.latest_accepted_turn(TASK_ID, session_ref=SESSION_REF)
    assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT
    _ = handle


# --------------------------------------------------------------------------- #
# U. One task operation critical section, and an identity-bound recovery
#    (final cross-layer architecture repair)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_ref", [None, "", "   ", "/srv/private/prompt.txt", 7])
def test_a_dispatch_without_a_usable_prompt_ref_has_zero_side_effects(
    tmp_path: Path, bad_ref: Any
) -> None:
    """An unrecoverable dispatch is refused before anything durable happens.

    ``payload_ref`` is what a recovery resolves the frozen prompt from. A
    dispatch that cannot name its prompt could be admitted and then never
    rebuilt, so it is refused at the boundary — before the ledger is written
    and before the daemon is touched, not after.
    """

    backend, facade, _resolver = _backend(tmp_path)
    handle = _attach(backend)
    calls_before = list(facade.calls)

    with pytest.raises(SpineError) as excinfo:
        backend.run_turn(
            TASK_ID,
            turn_kind="prompt",
            payload_text=PROMPT_CANARY,
            dispatch_ref=DISPATCH_ONE,
            payload_ref=bad_ref,
            session_ref=SESSION_REF,
        )
    assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST

    assert facade.calls == calls_before
    assert facade.ops("submit") == 0
    assert _ledger(tmp_path).resolve_for_task(TASK_ID) == ()
    assert not (tmp_path / "arsd-run-bindings.json").exists()
    _ = handle


def test_every_accepted_intent_persists_the_prompt_ref_unconditionally(
    tmp_path: Path,
) -> None:
    """There is no path that writes an intent nothing can rebuild."""

    backend, _facade, _resolver = _backend(tmp_path)
    handle = _attach(backend)
    _dispatch(backend)

    binding = _ledger(tmp_path).resolve(TASK_ID, handle, DISPATCH_ONE)
    assert binding is not None
    refs = dict(binding.resolver_refs)
    assert refs["prompt_ref"] == PROMPT_REF
    assert refs["session_ref"] == SESSION_REF
    assert refs["turn_kind"] == "prompt"


def _uncertain(tmp_path: Path, *, turn_kind: str = "prompt"):
    backend, facade, resolver = _backend(tmp_path)
    _attach(backend)
    facade.submit_error = _TransportLoss("reply never read")
    with pytest.raises(SpineError):
        _dispatch(backend, turn_kind=turn_kind)
    facade.submit_error = None
    return backend, facade, resolver


@pytest.mark.parametrize(
    "overrides",
    [
        {"session_ref": OTHER_SESSION_REF},
        {"turn_kind": "goal"},
        {"session_ref": OTHER_SESSION_REF, "turn_kind": "goal"},
    ],
    ids=["other_session", "other_turn_kind", "both"],
)
def test_recovery_under_a_different_identity_is_refused_before_anything_runs(
    tmp_path: Path, overrides: dict[str, str]
) -> None:
    """A recovery resends a frozen request; it must be the *same* request.

    Same ``request_id``, same digest — and therefore the same Session and the
    same kind of turn. Presenting another Session or another turn kind is not
    a recovery of this dispatch, so it is refused before the resolver is
    called, before the daemon is touched, and before anything is bound.
    """

    backend, facade, resolver = _uncertain(tmp_path)
    calls_before = list(facade.calls)
    resolver_calls_before = resolver.calls

    kwargs: dict[str, Any] = {"session_ref": SESSION_REF, "turn_kind": "prompt"}
    kwargs.update(overrides)
    with pytest.raises(SpineError) as excinfo:
        backend.recover_uncertain_submission(TASK_ID, DISPATCH_ONE, **kwargs)
    assert excinfo.value.code == RUNTIME_ARSD_BINDING_CONFLICT

    # Nothing resolved, nothing sent, nothing observed.
    assert resolver.calls == resolver_calls_before
    assert facade.calls == calls_before
    assert facade.ops("submit") == 1
    # And the intent is left exactly as written, still recoverable.
    handle = derive_arsd_backend_handle(TASK_ID)
    intent = _ledger(tmp_path).resolve_pending(TASK_ID, handle, DISPATCH_ONE)
    assert intent is not None and intent.state == ARSD_BINDING_PENDING


def test_recovery_under_the_original_identity_still_resends_the_frozen_request(
    tmp_path: Path,
) -> None:
    """Non-vacuity: the identity check refuses impostors, not recoveries."""

    backend, facade, _resolver = _uncertain(tmp_path)
    recovered = backend.recover_uncertain_submission(
        TASK_ID, DISPATCH_ONE, session_ref=SESSION_REF, turn_kind="prompt"
    )
    assert recovered.result.supervisor_status == "accepted"
    assert facade.ops("submit") == 2
    assert facade.submitted[0] == facade.submitted[1]


# --------------------------------------------------------------------------- #
# Bounded terminal result (Milestone A, task 7): the Run-facing surface a
# delegated submission reports from. It reads what ARS already returned and
# browses nothing — no artifact dir, no new operation, no rehydrate.
# --------------------------------------------------------------------------- #
FINAL_MESSAGE_CANARY = "the delegated agent finished and reported this"


def _terminal_body(status: str = "completed", **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "run_id": RUN_ID_CANARY,
        "status": status,
        "final_message": FINAL_MESSAGE_CANARY,
        "truncated": False,
        "truncate_reason": None,
        "run_dir": WORKSPACE_CANARY,
    }
    body.update(overrides)
    return body


def _dispatched_task(tmp_path: Path):
    backend, facade, _ = _backend(tmp_path)
    _attach(backend)
    _dispatch(backend)
    return backend, facade, derive_arsd_backend_handle(TASK_ID)


def test_a_nonterminal_run_has_no_final_message(tmp_path: Path) -> None:
    """Accepted, or progress with no terminal: there is nothing to report yet,
    and inventing an empty answer would read as "it finished, silently"."""

    backend, facade, handle = _dispatched_task(tmp_path)
    assert backend.observe_run(handle) == "accepted"
    assert backend.observe_run_result(handle) is None

    facade.run_status_payload = {"progress": {"state": "running"}}
    assert backend.observe_run(handle) == "accepted"
    assert backend.observe_run_result(handle) is None


def test_a_task_that_dispatched_nothing_has_no_terminal_result(tmp_path: Path) -> None:
    backend, _, _ = _backend(tmp_path)
    _attach(backend)
    handle = derive_arsd_backend_handle(TASK_ID)
    assert backend.observe_run(handle) is None
    assert backend.observe_run_result(handle) is None


def test_a_completed_run_exposes_the_bounded_final_message(tmp_path: Path) -> None:
    backend, facade, handle = _dispatched_task(tmp_path)
    facade.run_status_payload = {"result": _terminal_body("completed")}

    projected = backend.observe_run_result(handle)
    assert projected is not None
    assert projected.status == "completed"
    assert projected.final_message == FINAL_MESSAGE_CANARY
    assert projected.truncated is False
    assert projected.truncate_reason is None
    # The private locator and run dir stay behind: this is a projection, not
    # the body it was projected from.
    rendered = repr(projected) + str(projected)
    assert RUN_ID_CANARY not in rendered
    assert WORKSPACE_CANARY not in rendered


def test_a_truncated_final_message_keeps_its_marker(tmp_path: Path) -> None:
    backend, facade, handle = _dispatched_task(tmp_path)
    facade.run_status_payload = {
        "result": _terminal_body(
            "completed", truncated=True, truncate_reason="max_final_message_bytes"
        )
    }

    projected = backend.observe_run_result(handle)
    assert projected.truncated is True
    assert projected.truncate_reason == "max_final_message_bytes"


@pytest.mark.parametrize("terminal", ["failed", "cancelled", "timed_out", "unknown"])
def test_a_failed_run_preserves_its_stable_terminal_classification(
    tmp_path: Path, terminal: str
) -> None:
    """The neutral terminal the R-6 mapping derived is the one projected —
    the projection never re-reads the body's own status token."""

    backend, facade, handle = _dispatched_task(tmp_path)
    facade.run_status_payload = {"result": _terminal_body(terminal, final_message="")}

    projected = backend.observe_run_result(handle)
    assert projected.status == terminal
    assert backend.observe_run(handle) == terminal


def test_a_permission_violation_completed_run_is_projected_as_failed(
    tmp_path: Path,
) -> None:
    """A denied tool call reported ``completed`` must never read as success —
    on the terminal projection exactly as on ``observe_run`` (Spec §10.7)."""

    backend, facade, handle = _dispatched_task(tmp_path)
    facade.run_status_payload = {
        "result": _terminal_body("completed", reason=ARSD_PERMISSION_VIOLATION_REASON)
    }

    projected = backend.observe_run_result(handle)
    assert projected.status == "failed"
    assert ARSD_PERMISSION_VIOLATION_REASON not in repr(projected)


def test_a_settled_terminal_outlives_the_run_being_cleared(tmp_path: Path) -> None:
    """The daemon may forget a Run Sachima still has to report on.

    Once trusted evidence settled the verdict, the projection is remembered
    rather than re-asked for — otherwise the one notification a delegated
    submission owes its chat could be lost to a forgotten Run.
    """

    backend, facade, handle = _dispatched_task(tmp_path)
    facade.run_status_payload = {"result": _terminal_body("completed")}
    first = backend.observe_run_result(handle)
    assert first.final_message == FINAL_MESSAGE_CANARY

    calls_before = list(facade.calls)
    again = backend.observe_run_result(handle)
    assert again == first
    # No active Run left to observe, so no further socket operation happens.
    assert facade.calls == calls_before


def test_an_untrusted_terminal_body_yields_no_projection(tmp_path: Path) -> None:
    """Evidence that cannot be read is contained, never projected as an
    answer with an empty message."""

    backend, facade, handle = _dispatched_task(tmp_path)
    facade.run_status_payload = {"result": {"status": "not_a_terminal"}}
    with pytest.raises(SpineError) as excinfo:
        backend.observe_run_result(handle)
    assert excinfo.value.code == RUNTIME_ARSD_INTERNAL


def test_the_terminal_projection_reads_no_artifact_and_adds_no_operation(
    tmp_path: Path,
) -> None:
    """A-1: no artifact browsing, no API change. The whole terminal answer
    comes from the ``run_status`` reply that was already being read."""

    backend, facade, handle = _dispatched_task(tmp_path)
    facade.run_status_payload = {"result": _terminal_body("completed")}
    backend.observe_run_result(handle)
    assert set(facade.calls) <= {"server_info", "submit", "run_status", "session_status"}
    assert "run_events" not in facade.calls


# --------------------------------------------------------------------------- #
# The live roster read (0.7.8 ``agent_list``)
#
# Registration is a fact about the daemon this backend already negotiated
# with. The backend is the only place that fact enters Sachima, it enters
# validated, and it enters without changing what admission means: reading the
# roster submits nothing and creates no Session.
# --------------------------------------------------------------------------- #
def test_the_backend_reads_the_live_roster_through_one_bounded_operation(
    tmp_path: Path,
) -> None:
    backend, facade, _ = _backend(tmp_path)
    calls_before = list(facade.calls)

    assert backend.list_registered_agents() == REGISTERED_AGENT_IDS

    assert facade.calls == calls_before + ["agent_list"]
    assert "submit" not in facade.calls
    assert "session_status" not in facade.calls


def test_the_roster_read_is_live_rather_than_negotiated_once(
    tmp_path: Path,
) -> None:
    """Two reads ask the daemon twice: a roster is not a composition constant.

    A daemon that was restarted onto a different registry must be able to
    answer differently, so nothing caches the first answer.
    """

    backend, facade, _ = _backend(tmp_path)
    assert backend.list_registered_agents() == REGISTERED_AGENT_IDS

    facade.registered_agent_ids = ("claude", "codex")
    assert backend.list_registered_agents() == ("claude", "codex")
    assert facade.calls.count("agent_list") == 2


def test_an_empty_roster_is_an_answer_rather_than_a_failure(tmp_path: Path) -> None:
    backend, facade, _ = _backend(tmp_path)
    facade.registered_agent_ids = ()
    assert backend.list_registered_agents() == ()


def test_a_forged_roster_reply_is_a_protocol_violation(tmp_path: Path) -> None:
    """Validation is the backend's, not the caller's: an off-contract reply
    never reaches a decision."""

    backend, facade, _ = _backend(tmp_path)
    facade.registered_agent_ids = ("Codex", "codex")
    with pytest.raises(SpineError) as excinfo:
        backend.list_registered_agents()
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


def test_an_unreachable_daemon_makes_the_roster_unavailable(tmp_path: Path) -> None:
    """A transport failure is ``unavailable`` — never an empty roster.

    An empty tuple would read as "nothing is registered", which is a
    statement about the daemon's registry, not about our inability to ask.
    """

    backend, facade, _ = _backend(tmp_path)
    facade.agent_list_error = ConnectionError("socket gone")
    with pytest.raises(SpineError) as excinfo:
        backend.list_registered_agents()
    assert excinfo.value.code == RUNTIME_ARSD_UNAVAILABLE


def test_a_daemon_that_does_not_know_the_operation_stays_a_stable_code(
    tmp_path: Path,
) -> None:
    """A roster-less peer refuses through the ordinary ``UNKNOWN_OP`` mapping
    — there is no feature-specific code and no degraded answer."""

    backend, facade, _ = _backend(tmp_path)
    facade.agent_list_error = SpineError(RUNTIME_ARSD_PROTOCOL_VIOLATION)
    with pytest.raises(SpineError) as excinfo:
        backend.list_registered_agents()
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


# --------------------------------------------------------------------------- #
# The sealed grant survives dispatch and recovery
#
# The capability set is resolved from the config through the same
# ``agent_policy_ref`` a recovery already rebuilds from, so a resend is
# byte-identical without the grant being carried anywhere durable of its own.
# --------------------------------------------------------------------------- #
def test_a_dispatch_submits_the_policys_narrowed_grant(tmp_path: Path) -> None:
    backend, facade, _ = _backend(
        tmp_path,
        grant_capabilities=("execute", "read", "search", "write"),
        grant_by_policy_ref={"policy_agent": ["read", "search"]},
    )
    _attach(backend)
    _dispatch(backend)

    request = facade.submitted[0][1]["request"]
    assert request["grant_capabilities"] == ["read", "search"]
    assert request["grant_ref"] != "grant_reader_v1"


def test_a_recovery_resends_the_identical_sealed_grant(tmp_path: Path) -> None:
    """Byte-identity holds with a derived identity, because it is derived."""

    backend, facade, _ = _backend(
        tmp_path,
        grant_capabilities=("execute", "read", "search", "write"),
        grant_by_policy_ref={"policy_agent": ["read", "search"]},
    )
    _attach(backend)
    facade.submit_error = _TransportLoss("reply never read")
    with pytest.raises(SpineError):
        _dispatch(backend)
    facade.submit_error = None

    recovered = backend.recover_uncertain_submission(
        TASK_ID, DISPATCH_ONE, session_ref=SESSION_REF, turn_kind="prompt"
    )
    assert recovered.result.supervisor_status == "accepted"
    assert facade.submitted[0] == facade.submitted[1]
    assert facade.submitted[1][1]["request"]["grant_capabilities"] == ["read", "search"]
