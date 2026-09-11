"""Role routing at the real Sachima boundaries: create, continue, recover, restore, wakeup.

Every test drives the **real** composed ``arsd`` execution bundle — registry,
backend, port, dispatcher, ledger, and durable store — with the daemon replaced
by an injected facade double, exactly as the coordinator suite does. No socket
is opened, no daemon is started, and no AGENT is launched.

What is proven:

* a role-bearing create/continue submits the matrix route's exact literals in
  the **payload** — not merely on the card — and seals them with the matrix
  digest on the durable Turn; explicit AGENT + role runs the role's route, not
  the AGENT-wide preset;
* two roles on one AGENT select their own pair with no cross-contamination,
  including the literal ``N/A`` effort;
* a matrix edit applies to the next new Run and to nothing already admitted;
* a lost ack recovers byte-identically under the original literals after the
  matrix changed — in-process and across a restart — and a restored accepted
  Run never resubmits while its continuation reads the matrix as it is now;
* unconfigured / invalid / missing / paused each refuse with one stable code
  before anything durable exists;
* the non-role path is untouched and never reads the matrix;
* an authorized (wakeup) continuation pins its (AGENT, role) combination —
  including an AGENT switch into a linked task — and takes that combination's
  model from the matrix current at continuation time;
* the two new durable fields round-trip and validate.

Forbidden terms in this prose are no-leak boundary canaries only.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

import gateway.sachima_delegate as delegate_mod
from gateway.sachima_agent_execution_presets import (
    AGENT_EXECUTION_PRESETS_TYPE,
    ENGINEERING_BASELINE_PERMISSIONS,
    build_agent_execution_presets,
)
from gateway.sachima_agent_role_routing_matrix import (
    SACHIMA_ROLE_ROUTE_MISSING,
    SACHIMA_ROLE_ROUTE_PAUSED,
    SACHIMA_ROLE_ROUTING_MATRIX_INVALID,
    SACHIMA_ROLE_ROUTING_MATRIX_UNCONFIGURED,
    RoleRoutingMatrixSource,
)
from gateway.sachima_delegate import (
    SACHIMA_DELEGATE_RECOVERY_REQUIRED,
    SachimaDelegateCoordinator,
)
from gateway.sachima_delegate_state import (
    DelegateOrigin,
    DelegateStateError,
    DelegateStateStore,
    DelegateTaskBinding,
    DelegateTurnRecord,
    delegate_state_root,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
    bind_arsd_execution,
)
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import ArsdRunBindingLedger
from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    ARSD_SUPERVISOR_CONFIG_TYPE,
    EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
    ArsdSupervisorConfig,
    arsd_submit_payload_digest,
)

FINAL_MESSAGE_CANARY = "the delegated agent finished and reported this"
TASK_TEXT_CANARY = "audit the sachima role routing canary payload body"

#: The AGENT-wide preset pair in ``_config``: what a non-role Run submits.
PRESET_MODEL = "claude-opus-5"
PRESET_EFFORT = "xhigh"
LEAD_MODEL = "codex-lead-model[1m]"
LEAD_MODEL_NEXT = "codex-lead-model-next[1m]"
REVIEW_MODEL = "codex-review-model"
PM_MODEL = "codex-pm-model"
CURSOR_LEAD_MODEL = "cursor-lead-model[effort=high,fast=true]"

MATRIX_YAML = f"""\
schema_version: 1
default_agents:
  lead_developer: codex
routes:
  - agent_id: codex
    role_id: lead_developer
    availability: Available
    model: "{LEAD_MODEL}"
    effort: xhigh
    fallback: null
  - agent_id: codex
    role_id: code_reviewer
    availability: Available
    model: "{REVIEW_MODEL}"
    effort: "N/A"
    fallback:
      model: "codex-review-fallback"
      effort: max
  - agent_id: codex
    role_id: project_manager
    availability: Paused
    model: "{PM_MODEL}"
    effort: medium
    fallback: null
  - agent_id: cursor
    role_id: lead_developer
    availability: Available
    model: "{CURSOR_LEAD_MODEL}"
    effort: "N/A"
    fallback: null
"""

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
SEAL_KEYS = ("requested_model_digest", "requested_effort_digest", "route_source_digest")


class _Facade:
    """One in-memory arsd daemon: records submits, answers terminals on demand."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.submitted: list[dict[str, Any]] = []
        self.run_ids: list[str] = []
        self.terminals: dict[str, dict[str, Any]] = {}
        self.submit_swallow_ack = False
        self._lock = threading.RLock()
        self._seq = 0

    def submit_count(self) -> int:
        with self._lock:
            return len(self.submitted)

    def terminalize(self, index: int, *, status: str = "completed") -> None:
        with self._lock:
            run_id = self.run_ids[index]
            self.terminals[run_id] = {
                "run_id": run_id,
                "status": status,
                "final_message": FINAL_MESSAGE_CANARY,
                "truncated": False,
                "truncate_reason": None,
            }

    def server_info(self) -> dict[str, Any]:
        self.calls.append("server_info")
        return {
            "version": EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
            "api_version": 3,
            "supported_api_versions": [3],
            "operations": list(V3_OPERATIONS),
            "limits": {
                "max_concurrent_runs": 10,
                "max_frame_bytes": 1_048_576,
                "max_prompt_bytes": 262_144,
                "events_page_limit": 256,
                "event_follow_queue_size": 1024,
                "max_run_event_budget_bytes": 2_147_483_648,
            },
        }

    def submit(self, *, request_id: str, payload: Any) -> dict[str, Any]:
        self.calls.append("submit")
        with self._lock:
            self._seq += 1
            seq = self._seq
            run_id = f"RUN-routing-{seq}"
            self.submitted.append(json.loads(json.dumps(dict(payload))))
            self.run_ids.append(run_id)
        if self.submit_swallow_ack:
            raise ConnectionError("reply lost")
        requested = dict(payload).get("request", {}).get("session_id")
        return {
            "run_id": run_id,
            "session_id": requested or f"ARSSESSIONROUTING{seq}",
            "accepted_at": f"2026-09-11T06:05:{seq:02d}+00:00",
        }

    def run_status(self, run_id: str) -> dict[str, Any]:
        self.calls.append("run_status")
        with self._lock:
            terminal = self.terminals.get(run_id)
        body: dict[str, Any] = {"run_id": run_id, "session_id": "ARSSESSIONROUTING1"}
        if terminal is not None:
            body["result"] = dict(terminal)
        return body

    def run_events(self, run_id: str, *, from_seq: int, limit: int | None = None):
        self.calls.append("run_events")
        return {"run_id": run_id, "events": [], "next_from_seq": from_seq, "exhausted": True}

    def run_cancel(self, run_id: str) -> dict[str, Any]:
        self.calls.append("run_cancel")
        return {"run_id": run_id}

    def session_status(self, session_id: str) -> dict[str, Any]:
        self.calls.append("session_status")
        return {
            "session_id": session_id,
            "owner": "sachima_host",
            "namespace": "sachima_tasks",
            "agent_id": "codex",
            "profile_id": None,
            "created_at": "2026-09-11T06:05:06+00:00",
            "updated_at": "2026-09-11T06:05:06+00:00",
            "last_effective_model": None,
            "last_effective_effort": None,
            "quarantine": None,
        }

    def session_list(self) -> dict[str, Any]:
        self.calls.append("session_list")
        return {"sessions": []}

    def agent_list(self) -> dict[str, Any]:
        self.calls.append("agent_list")
        return {"agent_ids": list(REGISTERED_AGENT_IDS)}


def _config(tmp_path: Path) -> ArsdSupervisorConfig:
    private = tmp_path / "private"
    private.mkdir(parents=True, exist_ok=True)
    return ArsdSupervisorConfig(
        type=ARSD_SUPERVISOR_CONFIG_TYPE,
        approval_ref="approval_delegate_offline",
        owner="sachima_host",
        namespace="sachima_tasks",
        socket_path=str(private / "arsd.sock"),
        binding_ledger_path=str(private / "arsd-run-bindings.json"),
        agent_by_policy_ref={"policy_codex": "codex", "policy_cursor": "cursor"},
        model_by_policy_ref={"policy_model": PRESET_MODEL},
        effort_by_policy_ref={"policy_effort": PRESET_EFFORT},
        workspace_by_ref={"ws_delegate": str(private / "workspace")},
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
        grant_ref="grant_author_v1",
        grant_hash="sha256:" + "a" * 64,
        grant_role_hash="sha256:" + "b" * 64,
        grant_capabilities=("execute", "read", "search"),
        grant_by_policy_ref={
            "policy_codex": ENGINEERING_BASELINE_PERMISSIONS,
            "policy_cursor": ENGINEERING_BASELINE_PERMISSIONS,
        },
        mcp_snapshot_hashes=("sha256:" + "c" * 64,),
        credential_refs=("cred_author",),
        evidence_policy_hash="sha256:" + "d" * 64,
        recovery_policy_hash="sha256:" + "e" * 64,
        enabled=True,
    )


def _origin(session_id: str = "20260911_000000_abcd1234") -> DelegateOrigin:
    return DelegateOrigin(
        platform="feishu",
        chat_id="oc_chat",
        thread_id=None,
        session_key="feishu:oc_chat",
        session_id=session_id,
        reply_anchor="om_anchor",
    )


def _catalog(config, *agent_ids: str):
    return build_agent_execution_presets(
        {
            "type": AGENT_EXECUTION_PRESETS_TYPE,
            "presets": [
                {
                    "agent_id": agent_id,
                    "workspace_ref": "ws_delegate",
                    "agent_policy_ref": f"policy_{agent_id}",
                    "model_policy_ref": "policy_model",
                    "effort_policy_ref": "policy_effort",
                    "run_limits_policy_ref": "policy_limits",
                    "permissions": list(ENGINEERING_BASELINE_PERMISSIONS),
                }
                for agent_id in (agent_ids or ("codex", "cursor"))
            ],
        },
        config,
    )


def _matrix_path(tmp_path: Path) -> Path:
    return tmp_path / "routing-matrix.yaml"


def _write_matrix(tmp_path: Path, text: str = MATRIX_YAML) -> Path:
    path = _matrix_path(tmp_path)
    path.write_text(text, encoding="utf-8")
    return path


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _literal_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _coordinator(
    tmp_path: Path,
    *,
    facade: _Facade | None = None,
    matrix: bool | str = True,
) -> tuple[SachimaDelegateCoordinator, _Facade]:
    """A real composed bundle plus coordinator over ``tmp_path``'s state.

    ``matrix=True`` declares the standard matrix file (writing it if absent),
    a text declares that text, ``False`` composes no matrix at all. Calling it
    again over the same ``tmp_path`` is a genuinely fresh composition over the
    same durable state — a restart.
    """

    facade = _Facade() if facade is None else facade
    config = _config(tmp_path)
    bundle = bind_arsd_execution(
        config,
        facade=facade,
        ledger=ArsdRunBindingLedger(config.binding_ledger_path),
        payload_resolver=delegate_mod.delegate_payload_resolver(),
    )
    source = None
    if matrix is not False:
        path = _matrix_path(tmp_path)
        if matrix is not True:
            path.write_text(matrix, encoding="utf-8")
        elif not path.exists():
            _write_matrix(tmp_path)
        source = RoleRoutingMatrixSource(str(path))
    coordinator = SachimaDelegateCoordinator(
        bundle,
        config,
        presets=_catalog(config),
        routing_matrix=source,
        state=DelegateStateStore(delegate_state_root(config.binding_ledger_path)),
        observe_interval=0.01,
        summary_provider=None,
    )
    delegate_mod._coordinator = coordinator
    return coordinator, facade


@pytest.fixture(autouse=True)
def _unbind():
    delegate_mod.unbind_delegate_coordinator()
    yield
    delegate_mod.unbind_delegate_coordinator()


def _preset(coordinator, agent_id: str = "codex"):
    preset = coordinator.presets.preset(agent_id)
    assert preset is not None
    return preset


async def _until(predicate, *, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


async def _create(coordinator, *, role: str | None = None, **extra):
    return await coordinator.create(
        task_text=TASK_TEXT_CANARY,
        preset=_preset(coordinator),
        origin=_origin(),
        admitted_role=role,
        task_title="核对角色路由",
        round_title="第一轮",
        **extra,
    )


async def _terminal(coordinator, facade, turn_key: str, index: int) -> None:
    facade.terminalize(index)
    assert await _until(
        lambda: coordinator.state.read_turn(turn_key).lifecycle == "terminal"
    )


def _ledger_refs(coordinator, turn) -> dict[str, str]:
    record = coordinator.ledger.snapshot_exact(*turn.ledger_key)
    assert record is not None
    return dict(record.resolver_refs)


def _durable_files(coordinator, folder: str) -> int:
    directory = Path(coordinator.state.root) / folder
    if not directory.exists():
        return 0
    return len([p for p in directory.iterdir() if p.is_file() and not p.name.endswith(".tmp")])


# --------------------------------------------------------------------------- #
# A. A role-bearing admission submits and seals the matrix route
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_role_bearing_create_submits_the_route_literals_and_seals_them(tmp_path):
    coordinator, facade = _coordinator(tmp_path)
    outcome = await _create(coordinator, role="lead_developer")
    assert outcome.lifecycle == "admitted", outcome.diagnostic

    # The actual submission — not merely the card — carries the route.
    request = facade.submitted[0]["request"]
    assert request["requested_model"] == LEAD_MODEL
    assert request["requested_effort"] == "xhigh"
    assert PRESET_MODEL not in json.dumps(facade.submitted[0])
    # Everything but the pair is the AGENT-wide preset's: the explicit AGENT
    # selection did not override the role's policy, and the role did not
    # touch the identity.
    assert request["agent_id"] == "codex"
    assert request["grant_ref"] == "grant_author_v1"

    turn = coordinator.state.read_turn(outcome.turn_key)
    assert turn.admitted_role == "lead_developer"
    assert turn.requested_agent == "codex"
    assert turn.requested_model == LEAD_MODEL
    assert turn.requested_effort == "xhigh"
    assert turn.route_source_digest == _file_digest(_matrix_path(tmp_path))
    assert turn.launch_refs == _preset(coordinator).launch_refs

    # The ledger carries digests of the literals, never the literals.
    refs = _ledger_refs(coordinator, turn)
    assert refs["requested_model_digest"] == _literal_digest(LEAD_MODEL)
    assert refs["requested_effort_digest"] == _literal_digest("xhigh")
    assert refs["route_source_digest"] == turn.route_source_digest
    ledger_text = Path(coordinator.state.root).parent.joinpath(
        "arsd-run-bindings.json"
    ).read_text(encoding="utf-8")
    assert LEAD_MODEL not in ledger_text
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_two_roles_on_one_agent_select_their_own_pair(tmp_path):
    coordinator, facade = _coordinator(tmp_path)
    first = await _create(coordinator, role="lead_developer")
    await _terminal(coordinator, facade, first.turn_key, 0)

    second = await coordinator.continue_task(
        first.task_ref, "review it", admitted_role="code_reviewer", round_title="第二轮"
    )
    assert second.lifecycle == "admitted", second.diagnostic
    review = facade.submitted[1]["request"]
    assert review["requested_model"] == REVIEW_MODEL
    assert review["requested_effort"] == "N/A"
    # Same task, same ARS Session, a different pair — and the first Run's
    # sealed record is exactly what it was.
    assert review["session_id"] == facade.submitted[0].get("session_id", review["session_id"])
    assert coordinator.state.read_turn(second.turn_key).admitted_role == "code_reviewer"
    first_turn = coordinator.state.read_turn(first.turn_key)
    assert first_turn.requested_model == LEAD_MODEL
    assert first_turn.admitted_role == "lead_developer"
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_a_matrix_edit_applies_to_the_next_new_run_and_to_nothing_admitted(tmp_path):
    coordinator, facade = _coordinator(tmp_path)
    first = await _create(coordinator, role="lead_developer")
    await _terminal(coordinator, facade, first.turn_key, 0)
    first_digest = coordinator.state.read_turn(first.turn_key).route_source_digest

    _write_matrix(tmp_path, MATRIX_YAML.replace(LEAD_MODEL, LEAD_MODEL_NEXT))

    second = await coordinator.continue_task(
        first.task_ref, "continue", admitted_role="lead_developer", round_title="第二轮"
    )
    assert second.lifecycle == "admitted", second.diagnostic
    assert facade.submitted[1]["request"]["requested_model"] == LEAD_MODEL_NEXT
    second_turn = coordinator.state.read_turn(second.turn_key)
    assert second_turn.requested_model == LEAD_MODEL_NEXT
    assert second_turn.route_source_digest == _file_digest(_matrix_path(tmp_path))
    assert second_turn.route_source_digest != first_digest
    # No Gateway restart, no re-composition: the same coordinator read the edit.
    first_turn = coordinator.state.read_turn(first.turn_key)
    assert first_turn.requested_model == LEAD_MODEL
    assert first_turn.route_source_digest == first_digest
    facade.terminalize(1)


# --------------------------------------------------------------------------- #
# B. Recovery and restart keep an admitted Run pinned
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_lost_ack_recovers_byte_identically_after_the_matrix_changed(tmp_path):
    facade = _Facade()
    facade.submit_swallow_ack = True
    coordinator, _ = _coordinator(tmp_path, facade=facade)
    outcome = await _create(coordinator, role="lead_developer")
    assert outcome.lifecycle == "recovery_required"
    assert outcome.diagnostic == SACHIMA_DELEGATE_RECOVERY_REQUIRED
    first_payload = facade.submitted[0]

    # The matrix moves while the submission is uncertain.
    _write_matrix(tmp_path, MATRIX_YAML.replace(LEAD_MODEL, LEAD_MODEL_NEXT))
    facade.submit_swallow_ack = False

    recovered = await coordinator.recover(outcome.task_ref)
    assert recovered.lifecycle == "admitted", recovered.diagnostic
    assert facade.submit_count() == 2
    assert facade.submitted[1] == first_payload
    assert facade.submitted[1]["request"]["requested_model"] == LEAD_MODEL
    record = coordinator.ledger.snapshot_exact(
        *coordinator.state.read_turn(outcome.turn_key).ledger_key
    )
    assert record.state == "accepted"
    assert arsd_submit_payload_digest(facade.submitted[1]) == record.payload_digest
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_a_restart_recovers_a_sealed_pending_intent_from_the_durable_turn(tmp_path):
    facade = _Facade()
    facade.submit_swallow_ack = True
    coordinator, _ = _coordinator(tmp_path, facade=facade)
    outcome = await _create(coordinator, role="lead_developer")
    assert outcome.lifecycle == "recovery_required"
    first_payload = facade.submitted[0]

    # A fresh process, a changed matrix, and the durable Turn as the only
    # memory of what was requested.
    _write_matrix(tmp_path, MATRIX_YAML.replace(LEAD_MODEL, LEAD_MODEL_NEXT))
    facade.submit_swallow_ack = False
    fresh, _ = _coordinator(tmp_path, facade=facade)
    report = await fresh.restore()
    assert report["restored"] == 1
    assert facade.submit_count() == 1  # restoration resends nothing

    recovered = await fresh.recover(outcome.task_ref)
    assert recovered.lifecycle == "admitted", recovered.diagnostic
    assert facade.submit_count() == 2
    assert facade.submitted[1] == first_payload
    assert facade.submitted[1]["request"]["requested_model"] == LEAD_MODEL
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_a_restored_accepted_run_never_resubmits_and_its_continuation_reads_now(
    tmp_path,
):
    coordinator, facade = _coordinator(tmp_path)
    first = await _create(coordinator, role="lead_developer")
    assert first.lifecycle == "admitted"
    for observer in list(coordinator._observers.values()):
        observer.cancel()

    _write_matrix(tmp_path, MATRIX_YAML.replace(LEAD_MODEL, LEAD_MODEL_NEXT))
    fresh, _ = _coordinator(tmp_path, facade=facade)
    report = await fresh.restore()
    assert report["restored"] == 1
    assert facade.submit_count() == 1
    restored = fresh.state.read_turn(first.turn_key)
    assert restored.lifecycle == "admitted"
    assert restored.requested_model == LEAD_MODEL

    await _terminal(fresh, facade, first.turn_key, 0)
    second = await fresh.continue_task(
        first.task_ref, "continue", admitted_role="lead_developer", round_title="第二轮"
    )
    assert second.lifecycle == "admitted", second.diagnostic
    assert facade.submitted[1]["request"]["requested_model"] == LEAD_MODEL_NEXT
    assert fresh.state.read_turn(first.turn_key).requested_model == LEAD_MODEL
    facade.terminalize(1)


# --------------------------------------------------------------------------- #
# C. Refusals: one stable code each, nothing durable, nothing AGENT-wide
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("matrix", "role", "code"),
    [
        (False, "lead_developer", SACHIMA_ROLE_ROUTING_MATRIX_UNCONFIGURED),
        ("routes: [\n", "lead_developer", SACHIMA_ROLE_ROUTING_MATRIX_INVALID),
        (True, "documentation_engineer", SACHIMA_ROLE_ROUTE_MISSING),
        (True, "Lead Developer", SACHIMA_ROLE_ROUTE_MISSING),
        (True, 5, SACHIMA_ROLE_ROUTE_MISSING),
        (True, ["lead_developer"], SACHIMA_ROLE_ROUTE_MISSING),
        (True, "project_manager", SACHIMA_ROLE_ROUTE_PAUSED),
    ],
)
async def test_an_unroutable_role_is_refused_before_anything_durable_exists(
    tmp_path, matrix, role, code
):
    coordinator, facade = _coordinator(tmp_path, matrix=matrix)
    outcome = await _create(coordinator, role=role)
    assert outcome.diagnostic == code
    assert outcome.task_ref is None and outcome.turn_key is None and outcome.lifecycle is None
    assert facade.submit_count() == 0
    assert "submit" not in facade.calls
    assert not coordinator.state.list_tasks()
    assert not coordinator.state.list_turns()
    assert _durable_files(coordinator, "payloads") == 0
    assert coordinator.capacity.held() == 0


@pytest.mark.asyncio
async def test_an_unroutable_role_on_continuation_is_refused_and_the_task_stays_continuable(
    tmp_path,
):
    coordinator, facade = _coordinator(tmp_path)
    first = await _create(coordinator, role="lead_developer")
    await _terminal(coordinator, facade, first.turn_key, 0)
    binding_before = coordinator.state.read_task(first.task_ref)

    refused = await coordinator.continue_task(
        first.task_ref, "manage it", admitted_role="project_manager", round_title="第二轮"
    )
    assert refused.diagnostic == SACHIMA_ROLE_ROUTE_PAUSED
    assert refused.task_ref == first.task_ref and refused.turn_key is None
    assert facade.submit_count() == 1
    assert coordinator.state.read_task(first.task_ref) == binding_before

    # The same task continues under a routable role right after.
    second = await coordinator.continue_task(
        first.task_ref, "review it", admitted_role="code_reviewer", round_title="第二轮"
    )
    assert second.lifecycle == "admitted", second.diagnostic
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_the_non_role_path_is_untouched_and_never_reads_the_matrix(tmp_path):
    # An unreadable matrix would refuse every role-bearing admission; a
    # non-role admission never asks it anything.
    coordinator, facade = _coordinator(tmp_path, matrix="not: [valid\n")
    outcome = await _create(coordinator)
    assert outcome.lifecycle == "admitted", outcome.diagnostic
    request = facade.submitted[0]["request"]
    assert request["requested_model"] == PRESET_MODEL
    assert request["requested_effort"] == PRESET_EFFORT
    turn = coordinator.state.read_turn(outcome.turn_key)
    assert turn.admitted_role is None
    assert turn.route_source_digest is None
    assert turn.requested_model == PRESET_MODEL
    refs = _ledger_refs(coordinator, turn)
    assert not any(key in refs for key in SEAL_KEYS)
    # Blank and whitespace roles are "no role", not a role to route.
    await _terminal(coordinator, facade, outcome.turn_key, 0)
    second = await coordinator.continue_task(
        outcome.task_ref, "again", admitted_role="   ", round_title="第二轮"
    )
    assert second.lifecycle == "admitted", second.diagnostic
    assert facade.submitted[1]["request"]["requested_model"] == PRESET_MODEL
    facade.terminalize(1)


# --------------------------------------------------------------------------- #
# D. The authorized continuation pins its (AGENT, role) combination
# --------------------------------------------------------------------------- #
async def _authorized_first_round(coordinator, facade, **continuation):
    outcome = await _create(
        coordinator,
        role="lead_developer",
        authorization_ref="om_anchor",
        continuation_task="perform the already-approved next step",
        continuation_summary="User approved exactly one follow-up.",
        continuation_round_title="已授权的后续轮次",
        **continuation,
    )
    assert outcome.lifecycle == "admitted", outcome.diagnostic
    await _terminal(coordinator, facade, outcome.turn_key, 0)
    event = None

    def _settled() -> bool:
        nonlocal event
        event = coordinator.state.result_for_turn(outcome.turn_key)
        if event is None:
            return False
        summary = coordinator.state.summary_for_event(event.event_id)
        return summary is not None and summary.settled

    assert await _until(_settled)
    claim = coordinator.claim_hermes_context(_origin().session_id)
    assert claim is not None and event.event_id in claim.event_ids
    assert coordinator.confirm_hermes_context(
        _origin().session_id, processing_id=claim.processing_id, event_ids=claim.event_ids
    ) == len(claim.event_ids)
    return outcome, event, claim


@pytest.mark.asyncio
async def test_an_authorized_continuation_pins_the_named_role_on_the_current_matrix(
    tmp_path,
):
    coordinator, facade = _coordinator(tmp_path)
    outcome, event, claim = await _authorized_first_round(
        coordinator, facade, continuation_role="code_reviewer"
    )
    assert coordinator.state.read_task(outcome.task_ref).continuation_role == "code_reviewer"
    _write_matrix(tmp_path, MATRIX_YAML.replace(REVIEW_MODEL, "codex-review-model-next"))

    receipt = await coordinator.continue_authorized(
        task_ref=outcome.task_ref,
        turn_key=outcome.turn_key,
        event_id=event.event_id,
        processing_id=claim.processing_id,
        origin=_origin(),
    )
    assert receipt["operation_state"] == "accepted", receipt
    follow_up = coordinator.state.read_turn(receipt["turn_key"])
    assert follow_up.admitted_role == "code_reviewer"
    assert follow_up.requested_model == "codex-review-model-next"
    assert facade.submitted[1]["request"]["requested_model"] == "codex-review-model-next"
    assert facade.submitted[1]["request"]["requested_effort"] == "N/A"
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_an_authorized_agent_switch_runs_the_pinned_role_on_the_new_agent(tmp_path):
    coordinator, facade = _coordinator(tmp_path)
    outcome, event, claim = await _authorized_first_round(
        coordinator, facade, continuation_agent_id="cursor"
    )
    # No role named: the follow-up inherits the source round's role, on the
    # AGENT the authorization named — a linked new task, in its own Session.
    receipt = await coordinator.continue_authorized(
        task_ref=outcome.task_ref,
        turn_key=outcome.turn_key,
        event_id=event.event_id,
        processing_id=claim.processing_id,
        origin=_origin(),
    )
    assert receipt["operation_state"] == "accepted", receipt
    assert receipt["task_ref"] != outcome.task_ref
    linked = coordinator.state.read_task(receipt["task_ref"])
    assert linked.agent_id == "cursor"
    assert linked.linked_from == event.event_id
    follow_up = coordinator.state.read_turn(receipt["turn_key"])
    assert follow_up.admitted_role == "lead_developer"
    assert follow_up.requested_model == CURSOR_LEAD_MODEL
    request = facade.submitted[1]["request"]
    assert request["agent_id"] == "cursor"
    assert request["requested_model"] == CURSOR_LEAD_MODEL
    assert request["requested_effort"] == "N/A"
    assert "session_id" not in request
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_an_authorized_continuation_whose_route_vanished_is_blocked_not_borrowed(
    tmp_path,
):
    coordinator, facade = _coordinator(tmp_path)
    outcome, event, claim = await _authorized_first_round(coordinator, facade)
    _write_matrix(tmp_path, MATRIX_YAML.replace(f'model: "{LEAD_MODEL}"', 'model: "x"').replace(
        "role_id: lead_developer\n    availability: Available\n    model: \"x\"",
        "role_id: lead_developer\n    availability: Paused\n    model: \"x\"",
    ))

    receipt = await coordinator.continue_authorized(
        task_ref=outcome.task_ref,
        turn_key=outcome.turn_key,
        event_id=event.event_id,
        processing_id=claim.processing_id,
        origin=_origin(),
    )
    assert receipt["refusal"] == SACHIMA_ROLE_ROUTE_PAUSED
    assert facade.submit_count() == 1
    settled = coordinator.state.read_result(event.event_id)
    assert settled.business_state == "blocked"
    assert settled.operation_state == "uncertain"
    assert settled.business_diagnostic == SACHIMA_ROLE_ROUTE_PAUSED


# --------------------------------------------------------------------------- #
# E. The two new durable fields
# --------------------------------------------------------------------------- #
def _turn(**overrides) -> DelegateTurnRecord:
    fields: dict[str, Any] = dict(
        turn_key="dturn_" + "1" * 32,
        task_ref="dtask_" + "2" * 32,
        task_id="delegate_abcdef123456",
        backend_handle="arsd_11223344",
        dispatch_ref="dlg_" + "3" * 32,
        payload_ref="dlg_" + "3" * 32,
        spine_session_id="sess_1",
        agent_id="codex",
        launch_refs=("ws_delegate", "policy_codex"),
        requested_agent="codex",
        requested_model=LEAD_MODEL,
        requested_effort="xhigh",
        origin=_origin(),
    )
    fields.update(overrides)
    return DelegateTurnRecord(**fields)


def test_the_route_source_digest_round_trips_and_validates():
    digest = "sha256:" + "f" * 64
    sealed = _turn(route_source_digest=digest, admitted_role="lead_developer")
    assert DelegateTurnRecord.from_dict(sealed.as_dict()) == sealed
    assert sealed.as_dict()["route_source_digest"] == digest
    # A record written before the field carries none, and reads.
    legacy = sealed.as_dict()
    del legacy["route_source_digest"]
    assert DelegateTurnRecord.from_dict(legacy).route_source_digest is None
    for bad in ("sha256:short", LEAD_MODEL, 5, ""):
        with pytest.raises(DelegateStateError):
            _turn(route_source_digest=bad)


def test_the_continuation_role_round_trips_and_validates():
    binding = DelegateTaskBinding(
        task_ref="dtask_" + "2" * 32,
        task_id="delegate_abcdef123456",
        backend_handle="arsd_11223344",
        spine_session_id="sess_1",
        agent_id="codex",
        origin=_origin(),
        continuation_role="code_reviewer",
    )
    assert DelegateTaskBinding.from_dict(binding.as_dict()) == binding
    legacy = binding.as_dict()
    del legacy["continuation_role"]
    assert DelegateTaskBinding.from_dict(legacy).continuation_role is None
    for bad in ("Code Reviewer", "", 5, "review-er"):
        with pytest.raises(DelegateStateError):
            DelegateTaskBinding(
                task_ref="dtask_" + "2" * 32,
                task_id="delegate_abcdef123456",
                backend_handle="arsd_11223344",
                spine_session_id="sess_1",
                agent_id="codex",
                origin=_origin(),
                continuation_role=bad,
            )
