"""The one control surface: ``sachima_delegate_control`` over a real coordinator.

This is where Hermes's semantic choice meets Sachima's deterministic one. The
tool takes a canonical ``agent_id`` — the id Hermes already resolved, clarified
or refused to guess at — and admits it only against ``live roster ∩ execution
preset``. Everything proven here is at the actual tool boundary, over the real
composed ``arsd`` bundle with an injected facade double, so a refusal is proven
by the *absence* of durable state and of a submit rather than by a return value.

What is proven:

* an exact id present in both halves creates exactly one task and one submit;
* an unknown id, a roster-only id, a preset-only id, a malformed id, and a
  daemon whose roster cannot be read each refuse **before** any durable task,
  payload, turn record, or submit exists;
* a selection resolves case-insensitively but otherwise exactly against the
  live roster, and the canonical roster spelling is what gets stored;
* nothing else falls back: no trimming, no nearest match, no default AGENT,
  and no inherited configuration;
* continuation keeps the AGENT by default, switches AGENT into a *linked* task
  without ever rewriting the old binding, and re-proves eligibility every time
  it would submit;
* ``status`` / ``cancel`` / ``recover`` / ``result`` still answer for a task
  whose AGENT is no longer eligible — an old task stays readable even when it
  can no longer run.

Everything is hermetic and offline: no socket, no daemon, no IM adapter, no
provider, and no AGENT. Forbidden terms in this prose are no-leak boundary
canaries only, never behavior.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import gateway.sachima_delegate as delegate_mod
import tools.sachima_delegate_control_tool as control_mod
from gateway.sachima_agent_execution_presets import (
    AGENT_EXECUTION_PRESETS_TYPE,
    ENGINEERING_BASELINE_PERMISSIONS,
    IMPLEMENTATION_PERMISSIONS,
    SACHIMA_AGENT_INVALID_ID,
    SACHIMA_AGENT_NO_PRESET,
    SACHIMA_AGENT_NOT_REGISTERED,
    SACHIMA_AGENT_ROSTER_UNAVAILABLE,
    build_agent_execution_presets,
)
from gateway.sachima_agent_role_policy import (
    AGENT_ROLE_POLICY_TYPE,
    SACHIMA_AGENT_ROLE_AMBIGUOUS,
    SACHIMA_AGENT_ROLE_NO_CANDIDATE,
    build_agent_role_policy,
)
from gateway.sachima_delegate import SachimaDelegateCoordinator
from gateway.sachima_delegate_state import DelegateStateStore, delegate_state_root
from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
    bind_arsd_execution,
)
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import (
    ArsdRunBindingLedger,
)
from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    ARSD_SUPERVISOR_CONFIG_TYPE,
    EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
    ArsdSupervisorConfig,
)
from tools.registry import registry

TASK_TEXT_CANARY = "audit the sachima delegation canary payload body"
#: The short TODO-style line the card shows; the AGENT still receives the full
#: task text above, which is what makes "shown" and "executed" provably distinct.
TASK_TITLE_CANARY = "核对委派卡展示标题"
#: The short line one *round* is displayed under in the card's execution log.
#: It is supplied per create/continue, so it is neither the Task's headline
#: above nor the full task text the AGENT actually executes.
ROUND_TITLE_CANARY = "核对第一轮的执行说明"
LIVE_ROSTER = ("claude", "codex", "cursor", "oh-my-pi", "opencode")

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


class _Facade:
    """One in-memory arsd daemon: roster, submits, and terminals."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.submitted: list[dict[str, Any]] = []
        self.run_ids: list[str] = []
        self.terminals: dict[str, dict[str, Any]] = {}
        self.registered_agent_ids: tuple[str, ...] = LIVE_ROSTER
        self.agent_list_error: BaseException | None = None
        self._seq = 0

    # -- operations ------------------------------------------------------- #
    def server_info(self) -> dict[str, Any]:
        self.calls.append("server_info")
        return {
            "version": EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
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

    def agent_list(self) -> dict[str, Any]:
        self.calls.append("agent_list")
        if self.agent_list_error is not None:
            raise self.agent_list_error
        return {"agent_ids": list(self.registered_agent_ids)}

    def submit(self, *, request_id: str, payload: Any) -> dict[str, Any]:
        self.calls.append("submit")
        self._seq += 1
        run_id = f"RUN-control-{self._seq}"
        self.submitted.append(json.loads(json.dumps(dict(payload))))
        self.run_ids.append(run_id)
        requested = dict(payload).get("request", {}).get("session_id")
        return {
            "run_id": run_id,
            "session_id": requested or f"ARSSESSIONCONTROL{self._seq}",
            "accepted_at": f"2026-08-23T04:05:{self._seq:02d}+00:00",
        }

    def run_status(self, run_id: str) -> dict[str, Any]:
        self.calls.append("run_status")
        body: dict[str, Any] = {"run_id": run_id, "session_id": "ARSSESSIONCONTROL1"}
        terminal = self.terminals.get(run_id)
        if terminal is not None:
            body["result"] = dict(terminal)
        return body

    def run_events(self, run_id: str, *, from_seq: int, limit: int | None = None):
        self.calls.append("run_events")
        return {
            "run_id": run_id,
            "events": [],
            "next_from_seq": from_seq,
            "exhausted": True,
        }

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
            "created_at": "2026-08-23T04:05:06+00:00",
            "updated_at": "2026-08-23T04:05:06+00:00",
            "last_effective_model": None,
            "last_effective_effort": None,
            "quarantine": None,
        }

    def session_list(self) -> dict[str, Any]:
        self.calls.append("session_list")
        return {"sessions": []}

    # -- helpers ---------------------------------------------------------- #
    def terminalize(self, index: int, *, status: str = "completed") -> None:
        self.terminals[self.run_ids[index]] = {
            "run_id": self.run_ids[index],
            "status": status,
            "final_message": "the delegated agent finished and reported this",
            "truncated": False,
            "truncate_reason": None,
        }

    def submit_count(self) -> int:
        return len(self.submitted)


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
        model_by_policy_ref={"policy_model": "claude-opus-5"},
        effort_by_policy_ref={"policy_effort": "xhigh"},
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
        grant_ref="grant_engineering_v1",
        grant_hash="sha256:" + "a" * 64,
        grant_role_hash="sha256:" + "b" * 64,
        grant_capabilities=("execute", "read", "search", "write"),
        grant_by_policy_ref={
            "policy_codex": list(ENGINEERING_BASELINE_PERMISSIONS),
            "policy_cursor": list(IMPLEMENTATION_PERMISSIONS),
        },
        mcp_snapshot_hashes=("sha256:" + "c" * 64,),
        credential_refs=("cred_engineering",),
        evidence_policy_hash="sha256:" + "d" * 64,
        recovery_policy_hash="sha256:" + "e" * 64,
        enabled=True,
    )


#: ``codex`` reviews and ``cursor`` implements, so the two presets in this
#: harness declare different capability sets and must therefore submit under
#: different sealed grants.
PRESET_PERMISSIONS_BY_AGENT = {
    "codex": ENGINEERING_BASELINE_PERMISSIONS,
    "cursor": IMPLEMENTATION_PERMISSIONS,
}


def _preset_entry(agent_id: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "workspace_ref": "ws_delegate",
        "agent_policy_ref": f"policy_{agent_id}",
        "model_policy_ref": "policy_model",
        "effort_policy_ref": "policy_effort",
        "run_limits_policy_ref": "policy_limits",
        "permissions": list(PRESET_PERMISSIONS_BY_AGENT[agent_id]),
    }


SESSION_ID = "20260823_000000_abcd1234"
SESSION_KEY = "feishu:oc_chat"


class _SessionEntry:
    session_id = SESSION_ID
    session_key = SESSION_KEY
    origin = SimpleNamespace(
        platform=SimpleNamespace(value="feishu"), chat_id="oc_chat", thread_id=None
    )


class _SessionStore:
    def lookup_by_session_id(self, session_id):
        return _SessionEntry() if session_id == SESSION_ID else None

    def lookup_by_session_key(self, session_key):
        return _SessionEntry() if session_key == SESSION_KEY else None


@pytest.fixture
def control(tmp_path, monkeypatch):
    """The tool, its env gate, a bound coordinator, and a running loop."""

    import asyncio
    import threading

    monkeypatch.setenv(control_mod.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    monkeypatch.setattr(
        "gateway.session_context.get_session_env",
        lambda name, default="": {
            "HERMES_SESSION_ID": SESSION_ID,
            "HERMES_SESSION_KEY": SESSION_KEY,
            "HERMES_SESSION_MESSAGE_ID": "om_anchor",
        }.get(name, default),
    )
    control_mod.bind_delegate_control_session_store(_SessionStore())

    facade = _Facade()
    config = _config(tmp_path)
    bundle = bind_arsd_execution(
        config,
        facade=facade,
        ledger=ArsdRunBindingLedger(config.binding_ledger_path),
        payload_resolver=delegate_mod.delegate_payload_resolver(),
    )
    presets = build_agent_execution_presets(
        {
            "type": AGENT_EXECUTION_PRESETS_TYPE,
            "presets": [_preset_entry("codex"), _preset_entry("cursor")],
        },
        config,
    )
    role_policy = build_agent_role_policy(
        {
            "type": AGENT_ROLE_POLICY_TYPE,
            "assignments": [
                {
                    "agent_id": "codex",
                    "division": "engineering",
                    "roles": ["architecture_design", "code_review"],
                },
                {
                    "agent_id": "cursor",
                    "division": "engineering",
                    "roles": ["code_review", "implementation"],
                },
            ],
        }
    )
    coordinator = SachimaDelegateCoordinator(
        bundle,
        config,
        presets=presets,
        role_policy=role_policy,
        state=DelegateStateStore(delegate_state_root(config.binding_ledger_path)),
        observe_interval=0.01,
    )
    delegate_mod._coordinator = coordinator

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    coordinator.bind_lifecycle_loop(loop)
    try:
        yield SimpleNamespace(
            coordinator=coordinator, facade=facade, config=config, presets=presets
        )
    finally:
        # Retire the coordinator's own lifecycle tasks before the loop goes,
        # so a still-polling observer is cancelled rather than orphaned.
        async def _drain():
            pending = [
                task
                for task in asyncio.all_tasks(loop)
                if task is not asyncio.current_task()
            ]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

        asyncio.run_coroutine_threadsafe(_drain(), loop).result(timeout=5)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        loop.close()
        delegate_mod.unbind_delegate_coordinator()
        control_mod.bind_delegate_control_session_store(None)


def _call(**args) -> dict[str, Any]:
    """One *well-formed* control call, as Hermes is required to make it.

    ``create`` and ``continue`` both name the round they are opening, so this
    helper supplies that line whenever a test is not itself about the argument.
    A test that proves the argument is required calls the handler directly.
    """

    if args.get("action") in {"create", "continue"}:
        args.setdefault("round_title", ROUND_TITLE_CANARY)
    return json.loads(control_mod._handle_delegate_control(dict(args)))


def _durable_records(coordinator, folder: str) -> int:
    """Records committed under one state folder, counted the store's own way.

    Every write in ``DelegateStateStore`` is ``temp sibling → os.replace``, so a
    ``<key>.tmp`` is visible for as long as one write is in flight — and the
    lifecycle observer keeps rewriting a turn on its own loop thread after that
    turn reads terminal. Counting raw directory entries therefore counts a
    record twice whenever the observer happens to be mid-write, which is a fact
    about timing rather than about what was committed. ``_list`` skips those
    siblings for exactly this reason; a test that proves a refusal by absence
    has to read the ledger by the same rule the ledger uses.
    """

    directory = Path(coordinator.state.root) / folder
    if not directory.exists():
        return 0
    return len(
        [
            path
            for path in directory.iterdir()
            if path.is_file() and not path.name.endswith((".tmp", ".json"))
        ]
    )


def _durable_counts(coordinator) -> tuple[int, int]:
    """(tasks, turns) actually on disk — a refusal is proven by absence."""

    return _durable_records(coordinator, "tasks"), _durable_records(coordinator, "turns")


def _payload_count(coordinator) -> int:
    """Task bytes actually on disk — the first durable effect a create has."""

    return _durable_records(coordinator, "payloads")


# --------------------------------------------------------------------------- #
# A. The tool's argument surface
# --------------------------------------------------------------------------- #
def test_the_schema_takes_a_canonical_agent_id_and_no_profile_argument() -> None:
    properties = control_mod.DELEGATE_CONTROL_SCHEMA["parameters"]["properties"]
    assert "agent_id" in properties
    assert "requested_profile_id" not in properties
    serialized = json.dumps(control_mod.DELEGATE_CONTROL_SCHEMA)
    assert "requested_profile_id" not in serialized
    assert "profile" not in serialized


def test_the_schema_separates_the_displayed_title_from_the_executed_task() -> None:
    """Two arguments, two jobs: one is shown, the other is executed.

    The card's ``任务`` row is a TODO-style line a person reads; the AGENT still
    receives the whole ``task``. A surface with only one field forces the card
    to either show an execution prompt or truncate one, and both were the
    problem this argument exists to remove.
    """

    properties = control_mod.DELEGATE_CONTROL_SCHEMA["parameters"]["properties"]
    assert properties["task_title"]["type"] == "string"
    title_description = properties["task_title"]["description"]
    assert "create" in title_description
    # The two descriptions must not read alike, or a model will fill them alike.
    assert title_description != properties["task"]["description"]


def test_the_schema_asks_for_a_round_line_on_both_create_and_continue() -> None:
    """Three arguments, three jobs: the Task's name, this round's, the work.

    The execution log needs one short sentence per round, and the only honest
    source for it is the caller that opened the round. Deriving it from ``task``
    would put a clipped execution prompt in the log — the same defect the
    Task-level title already exists to remove — so it is asked for explicitly,
    under one name, on both actions that open a round.
    """

    properties = control_mod.DELEGATE_CONTROL_SCHEMA["parameters"]["properties"]
    assert properties["round_title"]["type"] == "string"
    description = properties["round_title"]["description"]
    assert "create" in description and "continue" in description
    # Three arguments a model must not fill alike.
    assert description != properties["task"]["description"]
    assert description != properties["task_title"]["description"]


def test_the_registered_tool_is_still_the_one_default_off_control_surface() -> None:
    assert registry.get_entry(control_mod.TOOL_NAME) is not None
    assert control_mod.TOOLSET_NAME == "sachima_delegate_control"
    assert set(control_mod._ACTIONS) == {
        "agents",
        "create",
        "status",
        "cancel",
        "continue",
        "recover",
        "result",
    }
    # Discovery is read-only and needs no task of its own; everything that
    # touches an existing task still proves the task is this conversation's.
    assert control_mod._TASKLESS_ACTIONS == {"agents", "create"}


# --------------------------------------------------------------------------- #
# B. Create — the exact intersection admits, everything else refuses
# --------------------------------------------------------------------------- #
def test_an_exact_id_in_both_halves_creates_one_task_and_one_submit(control) -> None:
    answer = _call(
        action="create",
        agent_id="codex",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )

    assert answer["type"] == control_mod.DELEGATE_CONTROL_ENVELOPE_TYPE
    assert answer["action"] == "create"
    result = answer["result"]
    assert result["task_ref"].startswith("dtask_")
    assert result["lifecycle"] in {"in_flight", "admitted", "terminal"}
    assert control.facade.submit_count() == 1
    assert _durable_counts(control.coordinator) == (1, 1)

    binding = control.coordinator.state.read_task(result["task_ref"])
    assert binding.agent_id == "codex"
    # The submitted Run names the same AGENT the preset was keyed on.
    assert control.facade.submitted[0]["request"]["agent_id"] == "codex"


@pytest.mark.parametrize(
    ("agent_id", "refusal"),
    [
        ("oh-my-pi", SACHIMA_AGENT_NO_PRESET),
        ("OH-MY-PI", SACHIMA_AGENT_NO_PRESET),
        ("claude", SACHIMA_AGENT_NO_PRESET),
        ("tom", SACHIMA_AGENT_NOT_REGISTERED),
        ("Tom", SACHIMA_AGENT_NOT_REGISTERED),
        ("codex ", SACHIMA_AGENT_INVALID_ID),
        (" codex", SACHIMA_AGENT_INVALID_ID),
        ("cod", SACHIMA_AGENT_NOT_REGISTERED),
        ("codexx", SACHIMA_AGENT_NOT_REGISTERED),
        ("../codex", SACHIMA_AGENT_INVALID_ID),
    ],
)
def test_an_ineligible_id_refuses_before_anything_durable_exists(
    control, agent_id, refusal
) -> None:
    answer = _call(
        action="create",
        agent_id=agent_id,
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )

    assert answer["result"]["refusal"] == refusal
    assert control.facade.submit_count() == 0
    assert _durable_counts(control.coordinator) == (0, 0)


def test_a_registered_agent_without_a_preset_is_reported_as_registered(
    control,
) -> None:
    """Registered-and-unavailable is a different answer from "no such AGENT",
    and Hermes needs the difference to say something true."""

    absent = _call(
        action="create",
        agent_id="oh-my-pi",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )
    unknown = _call(
        action="create",
        agent_id="tom",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )

    assert absent["result"] == {
        "refusal": SACHIMA_AGENT_NO_PRESET,
        "agent_id": "oh-my-pi",
        "registered": True,
    }
    assert unknown["result"] == {
        "refusal": SACHIMA_AGENT_NOT_REGISTERED,
        "agent_id": "tom",
        "registered": False,
    }


def test_a_preset_whose_agent_left_the_roster_stops_submitting(control) -> None:
    control.facade.registered_agent_ids = ("claude", "cursor")
    answer = _call(
        action="create",
        agent_id="codex",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )

    assert answer["result"]["refusal"] == SACHIMA_AGENT_NOT_REGISTERED
    assert control.facade.submit_count() == 0
    assert _durable_counts(control.coordinator) == (0, 0)


def test_an_unreadable_roster_refuses_rather_than_assuming_anything(control) -> None:
    control.facade.agent_list_error = ConnectionError("socket gone")
    answer = _call(
        action="create",
        agent_id="codex",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )

    assert answer["result"]["refusal"] == SACHIMA_AGENT_ROSTER_UNAVAILABLE
    assert control.facade.submit_count() == 0
    assert _durable_counts(control.coordinator) == (0, 0)


def test_create_without_an_agent_id_never_picks_one(control) -> None:
    """There is no default AGENT to fall back to, so an omitted id is invalid
    input rather than an invitation to route."""

    answer = control_mod._handle_delegate_control(
        {
            "action": "create",
            "task": TASK_TEXT_CANARY,
            "task_title": TASK_TITLE_CANARY,
        }
    )
    assert json.loads(answer)["error"] == control_mod.SACHIMA_DELEGATE_CONTROL_INVALID
    assert control.facade.submit_count() == 0
    assert _durable_counts(control.coordinator) == (0, 0)


def test_an_empty_task_creates_nothing_even_for_an_eligible_agent(control) -> None:
    answer = control_mod._handle_delegate_control(
        {
            "action": "create",
            "agent_id": "codex",
            "task": "   ",
            "task_title": TASK_TITLE_CANARY,
        }
    )
    assert json.loads(answer)["error"] == control_mod.SACHIMA_DELEGATE_CONTROL_INVALID
    assert _durable_counts(control.coordinator) == (0, 0)


@pytest.mark.parametrize(
    "title",
    [None, "", "   ", 7, ["核对委派卡展示标题"]],
)
def test_create_without_a_usable_title_creates_nothing(control, title) -> None:
    """The displayed line is required input, never derived from the prompt.

    Falling back to a clipped ``task`` is exactly the behaviour this argument
    replaces: a truncated execution prompt reads as a sentence the user never
    wrote. With no title there is nothing honest to show, so nothing is created.
    """

    args = {"action": "create", "agent_id": "codex", "task": TASK_TEXT_CANARY}
    if title is not None:
        args["task_title"] = title
    answer = control_mod._handle_delegate_control(args)

    assert json.loads(answer)["error"] == control_mod.SACHIMA_DELEGATE_CONTROL_INVALID
    assert control.facade.submit_count() == 0
    assert _durable_counts(control.coordinator) == (0, 0)


@pytest.mark.parametrize("title", ["\x00\x07", "\x1b\x1b", "\x7f", "\x00 \x1b\t"])
def test_a_title_that_survives_nothing_visible_creates_nothing(control, title) -> None:
    """"Non-empty string" is not the contract — "renders a line" is.

    A title made only of control characters passes a raw emptiness check and
    then sanitizes away to nothing, which would submit a Run and leave the card
    saying ``未提供`` about a task the user did name. The refusal has to be
    decided on the cleaned line, and it has to land before admission: nothing
    is asked of the roster, nothing durable is written, and nothing is
    submitted.
    """

    answer = control_mod._handle_delegate_control(
        {
            "action": "create",
            "agent_id": "codex",
            "task": TASK_TEXT_CANARY,
            "task_title": title,
        }
    )

    assert json.loads(answer)["error"] == control_mod.SACHIMA_DELEGATE_CONTROL_INVALID
    assert control.facade.calls.count("agent_list") == 0
    assert control.facade.submit_count() == 0
    assert _durable_counts(control.coordinator) == (0, 0)
    assert control.coordinator.state.list_tasks() == ()


@pytest.mark.parametrize(
    "round_title",
    [None, "", "   ", 7, ["核对第一轮的执行说明"], "\x00\x07", "\x1b\x1b", "\x7f"],
)
def test_create_without_a_usable_round_line_creates_nothing(control, round_title) -> None:
    """The log line is required input, decided on the line it would render.

    A missing one, a wrongly typed one, and one that sanitizes away to nothing
    are the same fact: there is no sentence to put in the execution log. The
    refusal therefore lands before admission — nothing is asked of the roster,
    no payload, Session, turn, task, or card is written, and nothing submits.
    """

    args = {
        "action": "create",
        "agent_id": "codex",
        "task": TASK_TEXT_CANARY,
        "task_title": TASK_TITLE_CANARY,
    }
    if round_title is not None:
        args["round_title"] = round_title
    answer = control_mod._handle_delegate_control(args)

    assert json.loads(answer)["error"] == control_mod.SACHIMA_DELEGATE_CONTROL_INVALID
    assert control.facade.calls.count("agent_list") == 0
    assert control.facade.submit_count() == 0
    assert _durable_counts(control.coordinator) == (0, 0)
    assert control.coordinator.state.list_tasks() == ()
    assert _payload_count(control.coordinator) == 0


def test_a_title_that_still_renders_after_cleaning_is_created_from_that_line(
    control,
) -> None:
    """The stored line is the sanitized one: single line, bounded, redacted."""

    from gateway.sachima_delegate_card import (
        CARD_TEXT_BUDGET_CHARS,
        sanitize_card_line,
    )

    raw = "核对 dtask_0f3c9a11b2c34d5e6f70 的\n多行\x07标题 " + "长" * 300
    task_ref = _call(
        action="create", agent_id="codex", task=TASK_TEXT_CANARY, task_title=raw
    )["result"]["task_ref"]

    stored = control.coordinator.state.read_task(task_ref).task_title
    # The tool applies the card layer's own rule rather than a second one.
    assert stored == sanitize_card_line(raw)
    assert len(stored) == CARD_TEXT_BUDGET_CHARS
    assert "\n" not in stored and "\x07" not in stored
    assert "dtask_0f3c9a11b2c34d5e6f70" not in stored
    assert control.facade.submit_count() == 1


def test_the_agent_receives_the_whole_task_while_the_task_keeps_the_title(
    control,
) -> None:
    """One create, two durable facts: the executed prompt and the shown line."""

    answer = _call(
        action="create",
        agent_id="codex",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )
    task_ref = answer["result"]["task_ref"]

    binding = control.coordinator.state.read_task(task_ref)
    assert binding.task_title == TASK_TITLE_CANARY
    # The AGENT's instruction is untouched by the display decision.
    assert control.facade.submitted[0]["prompt_text"] == TASK_TEXT_CANARY
    # And the Turn still carries the full ask as its execution/summary context.
    turn = control.coordinator.state.read_turn(binding.current_turn_key)
    assert turn.task_description == TASK_TEXT_CANARY
    assert turn.task_description != binding.task_title


def test_a_surrounding_whitespace_title_is_stored_as_the_line_it_renders(
    control,
) -> None:
    task_ref = _call(
        action="create",
        agent_id="codex",
        task=TASK_TEXT_CANARY,
        task_title="  核对委派卡展示标题  ",
    )["result"]["task_ref"]

    assert control.coordinator.state.read_task(task_ref).task_title == (
        "核对委派卡展示标题"
    )


def test_the_roster_is_read_live_for_every_create(control) -> None:
    _call(
        action="create",
        agent_id="codex",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )
    first = control.facade.calls.count("agent_list")
    _call(
        action="create",
        agent_id="codex",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )
    assert control.facade.calls.count("agent_list") == first + 1


# --------------------------------------------------------------------------- #
# C. Continuation — keep, switch, and re-prove
# --------------------------------------------------------------------------- #
def _completed_task(control) -> str:
    """One task driven to its terminal, so a continuation is legal.

    The wait is a wall-clock deadline rather than an iteration count: the
    observer runs on its own loop, so a loaded machine must be allowed to be
    slow without turning that into a failure about continuation.
    """

    task_ref = _call(
        action="create",
        agent_id="codex",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )[
        "result"
    ]["task_ref"]
    control.facade.terminalize(0)
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        status = _call(action="status", task_ref=task_ref)["result"]
        if status["lifecycle"] == "terminal":
            return task_ref
        time.sleep(0.02)
    raise AssertionError("the first Run never reached a terminal")


def test_continuation_keeps_the_same_task_session_and_agent(control) -> None:
    task_ref = _completed_task(control)
    answer = _call(action="continue", task_ref=task_ref, task="and now the second half")

    assert answer["result"]["task_ref"] == task_ref
    binding = control.coordinator.state.read_task(task_ref)
    assert binding.agent_id == "codex"
    assert len(binding.turn_keys) == 2
    assert control.facade.submit_count() == 2


def test_continuation_restates_the_same_agent_without_forking_the_task(
    control,
) -> None:
    task_ref = _completed_task(control)
    answer = _call(
        action="continue",
        task_ref=task_ref,
        agent_id="codex",
        task="and now the second half",
    )
    assert answer["result"]["task_ref"] == task_ref
    assert len(control.coordinator.state.read_task(task_ref).turn_keys) == 2


@pytest.mark.parametrize(
    "round_title",
    [None, "", "   ", 7, ["继续这个任务的第二段"], "\x00\x07", "\x7f"],
)
def test_continuation_without_a_usable_round_line_runs_nothing(
    control, round_title
) -> None:
    """A continuation opens a round too, so it names one or it does not run.

    The refusal lands before eligibility is re-proven and before the new turn
    exists: the task keeps exactly the turns it already had, and no second Run
    is submitted.
    """

    task_ref = _completed_task(control)
    before = control.coordinator.state.read_task(task_ref)
    submits = control.facade.submit_count()
    turns = _durable_counts(control.coordinator)
    payloads = _payload_count(control.coordinator)
    roster_reads = control.facade.calls.count("agent_list")

    args = {"action": "continue", "task_ref": task_ref, "task": "第二段的完整执行指令"}
    if round_title is not None:
        args["round_title"] = round_title
    answer = control_mod._handle_delegate_control(args)

    assert json.loads(answer)["error"] == control_mod.SACHIMA_DELEGATE_CONTROL_INVALID
    assert control.facade.calls.count("agent_list") == roster_reads
    assert control.facade.submit_count() == submits
    assert _durable_counts(control.coordinator) == turns
    assert _payload_count(control.coordinator) == payloads
    assert control.coordinator.state.read_task(task_ref) == before


def test_each_round_is_logged_under_the_line_that_opened_it(control) -> None:
    """One round, one sealed sentence — never the prompt, never the last one.

    The Turn keeps the complete instruction for the AGENT and the summariser;
    what the card's execution log reads is the short line supplied with that
    same call. The two are separately owned, and a later round supplies its own.
    """

    task_ref = _completed_task(control)
    first_key = control.coordinator.state.read_task(task_ref).current_turn_key
    _call(
        action="continue",
        task_ref=task_ref,
        task="第二段的完整执行指令",
        round_title="核对第二轮的执行说明",
    )
    second_key = control.coordinator.state.read_task(task_ref).current_turn_key

    first = control.coordinator.state.read_turn(first_key)
    second = control.coordinator.state.read_turn(second_key)
    assert first.round_title == ROUND_TITLE_CANARY
    assert second.round_title == "核对第二轮的执行说明"
    # Each half stays what it is: the executed prompt, the Task's headline, and
    # this round's own line are three different durable facts.
    assert second.task_description == "第二段的完整执行指令"
    assert second.round_title != second.task_description
    assert second.round_title != control.coordinator.state.read_task(task_ref).task_title


def test_a_continuation_never_rewrites_the_title_at_the_top_of_the_card(
    control,
) -> None:
    """One Task, one title. A later round adds a row; it never retitles.

    The header line names the Task, and the Task is the same one the user
    started. Letting a continuation move it would rewrite history in place:
    the rounds already on the card would suddenly answer a different question.
    """

    task_ref = _completed_task(control)
    _call(
        action="continue",
        task_ref=task_ref,
        task="and now the second half",
        task_title="第二段的新标题",
    )

    assert control.coordinator.state.read_task(task_ref).task_title == (
        TASK_TITLE_CANARY
    )


def test_switching_agent_carries_the_title_into_the_linked_task(control) -> None:
    """A switch is the same work under another AGENT, so it keeps the title.

    The linked Task inherits the source Task's persisted title verbatim — the
    one explicit rule here. It is neither re-derived from the continuation's
    prompt nor left blank, because both would make the two cards of one piece
    of work disagree about what that work is.
    """

    task_ref = _completed_task(control)
    linked_ref = _call(
        action="continue",
        task_ref=task_ref,
        agent_id="cursor",
        task="take it from here",
        task_title="调用方另给的标题",
    )["result"]["task_ref"]

    assert linked_ref != task_ref
    linked = control.coordinator.state.read_task(linked_ref)
    assert linked.task_title == TASK_TITLE_CANARY
    assert control.coordinator.state.read_task(task_ref).task_title == (
        TASK_TITLE_CANARY
    )


def test_switching_agent_creates_a_linked_task_and_leaves_the_old_one_alone(
    control,
) -> None:
    task_ref = _completed_task(control)
    before = control.coordinator.state.read_task(task_ref)

    answer = _call(
        action="continue",
        task_ref=task_ref,
        agent_id="cursor",
        task="take it from here",
    )
    linked_ref = answer["result"]["task_ref"]

    assert linked_ref != task_ref
    linked = control.coordinator.state.read_task(linked_ref)
    assert linked.agent_id == "cursor"
    assert linked.linked_from is not None
    # The old binding is untouched: same AGENT, same turns, same Session.
    after = control.coordinator.state.read_task(task_ref)
    assert after.agent_id == before.agent_id == "codex"
    assert after.turn_keys == before.turn_keys
    assert after.spine_session_id == before.spine_session_id


@pytest.mark.parametrize(
    ("agent_id", "refusal"),
    [
        ("oh-my-pi", SACHIMA_AGENT_NO_PRESET),
        ("tom", SACHIMA_AGENT_NOT_REGISTERED),
        ("cur sor", SACHIMA_AGENT_INVALID_ID),
    ],
)
def test_switching_to_an_ineligible_agent_submits_nothing(
    control, agent_id, refusal
) -> None:
    task_ref = _completed_task(control)
    submits = control.facade.submit_count()
    tasks, turns = _durable_counts(control.coordinator)

    answer = _call(
        action="continue", task_ref=task_ref, agent_id=agent_id, task="take it from here"
    )

    assert answer["result"]["refusal"] == refusal
    assert control.facade.submit_count() == submits
    assert _durable_counts(control.coordinator) == (tasks, turns)


def test_a_continuation_re_proves_eligibility_even_when_the_agent_is_unchanged(
    control,
) -> None:
    """An AGENT that left the roster stops receiving Runs on an existing task
    too — eligibility is a fact about now, not about when the task started."""

    task_ref = _completed_task(control)
    control.facade.registered_agent_ids = ("claude", "cursor")
    submits = control.facade.submit_count()

    answer = _call(action="continue", task_ref=task_ref, task="one more thing")

    assert answer["result"]["refusal"] == SACHIMA_AGENT_NOT_REGISTERED
    assert control.facade.submit_count() == submits


def test_a_task_whose_agent_became_ineligible_is_still_readable(control) -> None:
    """Old tasks keep answering: only *new* Runs need current eligibility."""

    task_ref = _completed_task(control)
    control.facade.registered_agent_ids = ("claude",)

    status = _call(action="status", task_ref=task_ref)["result"]
    assert status["task_ref"] == task_ref
    assert status["lifecycle"] == "terminal"

    result = _call(action="result", task_ref=task_ref)["result"]
    assert result["terminal"] == "completed"

    cancelled = _call(action="cancel", task_ref=task_ref)["result"]
    assert cancelled["task_ref"] == task_ref


def test_a_read_only_action_never_reads_the_roster(control) -> None:
    task_ref = _completed_task(control)
    before = control.facade.calls.count("agent_list")

    _call(action="status", task_ref=task_ref)
    _call(action="result", task_ref=task_ref)

    assert control.facade.calls.count("agent_list") == before


def test_another_conversations_task_is_never_reachable(control) -> None:
    task_ref = _completed_task(control)
    binding = control.coordinator.state.read_task(task_ref)
    control.coordinator.state.put_task(
        type(binding)(
            **{
                **{
                    field: getattr(binding, field)
                    for field in (
                        "task_ref",
                        "task_id",
                        "backend_handle",
                        "spine_session_id",
                        "agent_id",
                        "turn_keys",
                        "current_turn_key",
                        "terminal",
                        "linked_from",
                    )
                },
                "origin": type(binding.origin)(
                    platform="feishu",
                    chat_id="oc_other",
                    thread_id=None,
                    session_key="feishu:oc_other",
                    session_id="20260823_000000_ffff9999",
                ),
            }
        )
    )
    answer = json.loads(control_mod._handle_delegate_control(
        {"action": "status", "task_ref": task_ref}
    ))
    assert answer["error"] == control_mod.SACHIMA_DELEGATE_CONTROL_FORBIDDEN


# --------------------------------------------------------------------------- #
# D. A person writes ``Codex``
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spelling", ["codex", "Codex", "CODEX", "CoDeX"])
def test_a_cased_selection_creates_under_the_canonical_roster_id(
    control, spelling
) -> None:
    answer = _call(
        action="create",
        agent_id=spelling,
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )
    task_ref = answer["result"]["task_ref"]

    assert control.coordinator.state.read_task(task_ref).agent_id == "codex"
    assert control.facade.submitted[0]["request"]["agent_id"] == "codex"


def test_a_cased_switch_targets_the_canonical_roster_id(control) -> None:
    task_ref = _completed_task(control)
    answer = _call(
        action="continue",
        task_ref=task_ref,
        agent_id="CURSOR",
        task="take it from here",
    )
    linked = control.coordinator.state.read_task(answer["result"]["task_ref"])
    assert linked.agent_id == "cursor"


def test_restating_the_same_agent_in_another_case_does_not_fork_the_task(
    control,
) -> None:
    """``Codex`` and ``codex`` are the same AGENT, so this is a continuation."""

    task_ref = _completed_task(control)
    answer = _call(
        action="continue",
        task_ref=task_ref,
        agent_id="Codex",
        task="and now the second half",
    )
    assert answer["result"]["task_ref"] == task_ref
    assert len(control.coordinator.state.read_task(task_ref).turn_keys) == 2


# --------------------------------------------------------------------------- #
# E. The grant a Run actually executes under
#
# ``grant_capabilities`` is not documentation: the daemon's permission bridge
# freezes exactly that set for the Run and gates the write-family tools off
# it. A review preset whose Run still carried the config-wide ``write`` would
# be a review AGENT with authorship, no matter what its document said.
# --------------------------------------------------------------------------- #
def _submitted_grant(control, index: int = 0) -> dict[str, Any]:
    request = control.facade.submitted[index]["request"]
    return {
        key: request[key]
        for key in ("grant_ref", "grant_hash", "grant_role_hash", "grant_capabilities")
    }


def test_a_review_preset_submits_without_write(control) -> None:
    _call(
        action="create",
        agent_id="codex",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )

    grant = _submitted_grant(control)
    assert grant["grant_capabilities"] == list(ENGINEERING_BASELINE_PERMISSIONS)
    assert "write" not in grant["grant_capabilities"]


def test_an_implementation_preset_submits_with_write(control) -> None:
    _call(
        action="create",
        agent_id="cursor",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )

    grant = _submitted_grant(control)
    assert grant["grant_capabilities"] == list(IMPLEMENTATION_PERMISSIONS)


def test_the_two_presets_never_share_a_sealed_grant_identity(control) -> None:
    """Two Runs with different authority must be distinguishable afterwards."""

    _call(
        action="create",
        agent_id="codex",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )
    _call(
        action="create",
        agent_id="cursor",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )

    review = _submitted_grant(control, 0)
    author = _submitted_grant(control, 1)

    assert review["grant_capabilities"] != author["grant_capabilities"]
    assert review["grant_ref"] != author["grant_ref"]
    assert review["grant_hash"] != author["grant_hash"]
    assert review["grant_role_hash"] != author["grant_role_hash"]
    # The narrowed one does not travel under the operator's wide identity.
    assert review["grant_ref"] != control.config.grant_ref
    assert author["grant_ref"] == control.config.grant_ref


def test_every_continuation_resubmits_under_the_same_sealed_grant(control) -> None:
    task_ref = _completed_task(control)
    _call(action="continue", task_ref=task_ref, task="and now the second half")

    assert _submitted_grant(control, 0) == _submitted_grant(control, 1)
    assert "write" not in _submitted_grant(control, 1)["grant_capabilities"]


def test_a_switch_carries_the_new_agents_grant_not_the_old_ones(control) -> None:
    task_ref = _completed_task(control)
    _call(
        action="continue",
        task_ref=task_ref,
        agent_id="cursor",
        task="take it from here",
    )

    assert _submitted_grant(control, 0)["grant_capabilities"] == list(
        ENGINEERING_BASELINE_PERMISSIONS
    )
    assert _submitted_grant(control, 1)["grant_capabilities"] == list(
        IMPLEMENTATION_PERMISSIONS
    )


def test_the_sealed_grant_is_reproducible_from_the_config_alone(control) -> None:
    """An auditor recomputes the identity rather than trusting it."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        derive_arsd_sealed_grant,
    )

    _call(
        action="create",
        agent_id="codex",
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )
    grant = _submitted_grant(control)
    expected = derive_arsd_sealed_grant(
        control.config, ENGINEERING_BASELINE_PERMISSIONS
    )

    assert grant["grant_ref"] == expected.grant_ref
    assert grant["grant_hash"] == expected.grant_hash
    assert grant["grant_role_hash"] == expected.grant_role_hash
    assert grant["grant_capabilities"] == list(expected.capabilities)


# --------------------------------------------------------------------------- #
# F. Discovery: the one read-only action that closes automatic role routing
#
# "Find an AGENT suited to architecture design" needs three facts Hermes
# cannot otherwise see: who is registered right now, who this host may run,
# and who holds which role. This action returns exactly those, and — when
# asked with an exact role — the single candidate or the question to ask.
# It writes nothing, so a zero-or-several answer costs no task and no Run.
# --------------------------------------------------------------------------- #
def test_the_agents_action_reports_every_registered_agent(control) -> None:
    answer = _call(action="agents")

    assert answer["action"] == "agents"
    agents = answer["result"]["agents"]
    assert [entry["agent_id"] for entry in agents] == list(LIVE_ROSTER)
    assert answer["result"]["selection"] is None


def test_the_agents_action_separates_registration_from_executability(control) -> None:
    view = {entry["agent_id"]: entry for entry in _call(action="agents")["result"]["agents"]}

    assert view["codex"] == {
        "agent_id": "codex",
        "registered": True,
        "executable": True,
        "division": "engineering",
        "roles": ["architecture_design", "code_review"],
        "role_routable": True,
    }
    # Registered, no preset and no role: visible, and unavailable both ways.
    assert view["oh-my-pi"]["registered"] is True
    assert view["oh-my-pi"]["executable"] is False
    assert view["oh-my-pi"]["role_routable"] is False
    assert view["oh-my-pi"]["roles"] == []
    assert view["oh-my-pi"]["division"] is None


def test_one_exact_role_candidate_comes_back_selectable(control) -> None:
    answer = _call(action="agents", role="architecture_design")

    assert answer["result"]["selection"] == {
        "agent_id": "codex",
        "refusal": None,
        "candidates": ["codex"],
    }
    # Discovery is read-only: naming the AGENT is still a separate, explicit,
    # auditable create.
    assert control.facade.submit_count() == 0
    assert _durable_counts(control.coordinator) == (0, 0)


def test_a_role_nobody_holds_is_a_clarification_not_a_guess(control) -> None:
    answer = _call(action="agents", role="release_management")

    selection = answer["result"]["selection"]
    assert selection["agent_id"] is None
    assert selection["refusal"] == SACHIMA_AGENT_ROLE_NO_CANDIDATE
    assert selection["candidates"] == []
    assert _durable_counts(control.coordinator) == (0, 0)


def test_a_role_several_agents_hold_asks_which(control) -> None:
    answer = _call(action="agents", role="code_review")

    selection = answer["result"]["selection"]
    assert selection["agent_id"] is None
    assert selection["refusal"] == SACHIMA_AGENT_ROLE_AMBIGUOUS
    assert selection["candidates"] == ["codex", "cursor"]
    assert control.facade.submit_count() == 0
    assert _durable_counts(control.coordinator) == (0, 0)


def test_the_discovered_agent_is_then_created_by_its_canonical_name(control) -> None:
    """The whole product path, end to end, with the semantic step in Hermes."""

    selection = _call(action="agents", role="architecture_design")["result"]["selection"]
    assert selection["agent_id"] == "codex"

    created = _call(
        action="create",
        agent_id=selection["agent_id"],
        task=TASK_TEXT_CANARY,
        task_title=TASK_TITLE_CANARY,
    )
    task_ref = created["result"]["task_ref"]
    assert control.coordinator.state.read_task(task_ref).agent_id == "codex"
    assert control.facade.submit_count() == 1


def test_an_agent_off_the_roster_disappears_from_the_view(control) -> None:
    control.facade.registered_agent_ids = ("claude", "cursor")
    agents = _call(action="agents")["result"]["agents"]

    assert [entry["agent_id"] for entry in agents] == ["claude", "cursor"]
    assert _call(action="agents", role="architecture_design")["result"]["selection"][
        "refusal"
    ] == SACHIMA_AGENT_ROLE_NO_CANDIDATE


def test_an_unreadable_roster_reports_no_agents_rather_than_none_registered(
    control,
) -> None:
    control.facade.agent_list_error = ConnectionError("socket gone")
    answer = _call(action="agents")
    assert answer["result"] == {"refusal": SACHIMA_AGENT_ROSTER_UNAVAILABLE}


def test_the_agents_action_reads_the_roster_live_every_time(control) -> None:
    _call(action="agents")
    first = control.facade.calls.count("agent_list")
    _call(action="agents")
    assert control.facade.calls.count("agent_list") == first + 1


@pytest.mark.parametrize(
    "filters",
    [
        {"role": "Architecture_Design"},
        {"role": "architecture"},
        {"role": "design"},
        {"role": ""},
        {"division": "Engineering"},
        {"division": "eng"},
        {"role": "architecture_design", "division": "research"},
    ],
)
def test_role_and_division_filters_never_resemble(control, filters) -> None:
    selection = _call(action="agents", **filters)["result"]["selection"]
    assert selection["agent_id"] is None
    assert selection["refusal"] == SACHIMA_AGENT_ROLE_NO_CANDIDATE


def test_discovery_never_returns_refs_permissions_or_task_text(control) -> None:
    """The view is flags and closed tokens: nothing about how a Run is built."""

    raw = control_mod._handle_delegate_control({"action": "agents"})
    for private in ("ws_", "policy_", "grant_", "permissions", "sha256:", "socket"):
        assert private not in raw
