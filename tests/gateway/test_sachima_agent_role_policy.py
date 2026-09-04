"""Sachima role/division policy — the deterministic half of "who does this?".

"找一个适合做架构设计的 AGENT" is two questions wearing one sentence. *What
role does architecture design need?* is language, and Hermes owns it. *Which
registered, executable AGENT holds that role?* is arithmetic over three
explicit facts, and that is all this module does.

The split matters more than the answer. Role policy is kept out of the
execution preset on purpose: a preset is a permission to run, and the moment
it also carried "who is good at what" it would become a router, with every
temptation that follows — priority fields, aliases, fuzzy matches, a default
AGENT for when nothing matched. None of those exist here either. The
intersection is exact, and a role that fits zero or several AGENTs is a
question for the user, not a tie to break.

What is proven here:

* the catalog carries exactly ``agent_id`` → division + roles, and refuses a
  document that tries to carry ranking, weight, priority, aliases, platform
  identity or a default;
* the eligibility view is ``live roster`` left-joined with execution presets
  and role policy: every registered AGENT appears, and one missing either
  half is visible as registered-and-unavailable rather than absent;
* an AGENT never inherits another's roles or execution configuration;
* exact role/division selection admits one candidate, and refuses zero or
  several with a stable code and the candidate list Hermes clarifies from;
* matching is exact — no fuzzy, no substring, no priority, no alphabetical
  tie-break.

Pure local/offline: no adapter, socket, daemon, Session, task, or AGENT.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from gateway.sachima_agent_execution_presets import (
    AGENT_EXECUTION_PRESETS_TYPE,
    ENGINEERING_BASELINE_PERMISSIONS,
    build_agent_execution_presets,
    empty_agent_execution_presets,
)
from gateway.sachima_agent_role_policy import (
    AGENT_ROLE_POLICY_TYPE,
    SACHIMA_AGENT_ROLE_AMBIGUOUS,
    SACHIMA_AGENT_ROLE_INVALID_POLICY,
    SACHIMA_AGENT_ROLE_NO_CANDIDATE,
    SACHIMA_AGENT_ROLE_STABLE_CODES,
    AgentRolePolicy,
    RolePolicyError,
    build_agent_role_policy,
    build_agent_eligibility_view,
    empty_agent_role_policy,
    load_agent_role_policy,
    select_agent_by_role,
)

LIVE_ROSTER = ("claude", "codex", "cursor", "oh-my-pi", "opencode")


class _Config:
    def __init__(self, **maps: Any):
        self.workspace_by_ref = {"ws_main": "/tmp/ws"}
        self.agent_by_policy_ref = {
            "policy_claude": "claude",
            "policy_codex": "codex",
            "policy_cursor": "cursor",
        }
        self.model_by_policy_ref = {"policy_model": "claude-opus-5"}
        self.effort_by_policy_ref = {"policy_effort": "xhigh"}
        self.run_limits_by_policy_ref = {"policy_limits": {}}
        self.grant_capabilities = ("execute", "read", "search", "write")
        self.grant_by_policy_ref = {
            "policy_claude": ENGINEERING_BASELINE_PERMISSIONS,
            "policy_codex": ENGINEERING_BASELINE_PERMISSIONS,
            "policy_cursor": ENGINEERING_BASELINE_PERMISSIONS,
        }
        for name, value in maps.items():
            setattr(self, name, value)


def _presets(*agent_ids: str):
    config = _Config()
    return build_agent_execution_presets(
        {
            "type": AGENT_EXECUTION_PRESETS_TYPE,
            "presets": [
                {
                    "agent_id": agent_id,
                    "workspace_ref": "ws_main",
                    "agent_policy_ref": f"policy_{agent_id}",
                    "model_policy_ref": "policy_model",
                    "effort_policy_ref": "policy_effort",
                    "run_limits_policy_ref": "policy_limits",
                    "permissions": list(ENGINEERING_BASELINE_PERMISSIONS),
                }
                for agent_id in agent_ids
            ],
        },
        config,
    )


def _assignment(agent_id: str, division: str, *roles: str) -> dict[str, Any]:
    return {"agent_id": agent_id, "division": division, "roles": list(roles)}


def _policy(*assignments: dict[str, Any]) -> AgentRolePolicy:
    return build_agent_role_policy(
        {"type": AGENT_ROLE_POLICY_TYPE, "assignments": list(assignments)}
    )


#: The shape the rest of the file selects against: three registered AGENTs
#: with presets, of which two hold roles; ``oh-my-pi`` and ``opencode`` are
#: registered with neither.
def _world():
    return (
        _presets("codex", "cursor", "claude"),
        _policy(
            _assignment("codex", "engineering", "architecture_design", "code_review"),
            _assignment("cursor", "engineering", "implementation"),
        ),
    )


# --------------------------------------------------------------------------- #
# A. The role/division document
# --------------------------------------------------------------------------- #
def test_an_assignment_carries_one_division_and_its_roles() -> None:
    policy = _policy(
        _assignment("codex", "engineering", "architecture_design", "code_review")
    )
    (assignment,) = policy.assignments
    assert assignment.agent_id == "codex"
    assert assignment.division == "engineering"
    assert assignment.roles == ("architecture_design", "code_review")


def test_roles_are_canonically_ordered_and_deduplicated_at_build_time() -> None:
    with pytest.raises(RolePolicyError):
        _policy(_assignment("codex", "engineering", "code_review", "code_review"))

    (assignment,) = _policy(
        _assignment("codex", "engineering", "code_review", "architecture_design")
    ).assignments
    assert assignment.roles == ("architecture_design", "code_review")


def test_one_agent_may_hold_at_most_one_assignment() -> None:
    with pytest.raises(RolePolicyError):
        _policy(
            _assignment("codex", "engineering", "code_review"),
            _assignment("codex", "research", "analysis"),
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"agent_id": "Codex"},
        {"agent_id": ""},
        {"agent_id": None},
        {"division": "Engineering"},
        {"division": ""},
        {"division": None},
        {"division": "engineering team"},
        {"roles": []},
        {"roles": "code_review"},
        {"roles": None},
        {"roles": ["Code_Review"]},
        {"roles": ["code review"]},
        {"roles": [""]},
        {"roles": [None]},
        {"roles": ["a" * 65]},
    ],
    ids=[
        "uppercase_agent_id",
        "empty_agent_id",
        "none_agent_id",
        "uppercase_division",
        "empty_division",
        "none_division",
        "spaced_division",
        "no_roles",
        "roles_not_a_list",
        "roles_none",
        "uppercase_role",
        "spaced_role",
        "empty_role",
        "none_role",
        "overlong_role",
    ],
)
def test_a_deviating_assignment_fails_closed(overrides) -> None:
    entry = {**_assignment("codex", "engineering", "code_review"), **overrides}
    with pytest.raises(RolePolicyError) as excinfo:
        _policy(entry)
    assert str(excinfo.value) == SACHIMA_AGENT_ROLE_INVALID_POLICY


@pytest.mark.parametrize(
    "retired",
    ["priority", "weight", "rank", "aliases", "mentions", "platform", "default"],
)
def test_a_ranking_or_identity_field_is_refused_rather_than_ignored(retired) -> None:
    """The catalog answers "who holds this role", never "who is best"."""

    entry = {**_assignment("codex", "engineering", "code_review"), retired: 1}
    with pytest.raises(RolePolicyError):
        _policy(entry)


@pytest.mark.parametrize(
    "document",
    [
        {"type": AGENT_ROLE_POLICY_TYPE},
        {"assignments": []},
        {"type": AGENT_ROLE_POLICY_TYPE, "assignments": []},
        {"type": "sachima.gateway.agent_execution_presets.v1", "assignments": []},
        {"type": AGENT_ROLE_POLICY_TYPE, "assignments": {}},
        {"type": AGENT_ROLE_POLICY_TYPE, "assignments": [], "default": "codex"},
        None,
        [],
    ],
)
def test_a_deviating_document_fails_closed(document) -> None:
    with pytest.raises(RolePolicyError) as excinfo:
        build_agent_role_policy(document)
    assert str(excinfo.value) == SACHIMA_AGENT_ROLE_INVALID_POLICY


def test_a_policy_file_is_read_and_validated_and_never_echoed(tmp_path) -> None:
    path = tmp_path / "roles.json"
    path.write_text(
        json.dumps(
            {
                "type": AGENT_ROLE_POLICY_TYPE,
                "assignments": [_assignment("codex", "engineering", "code_review")],
            }
        ),
        encoding="utf-8",
    )
    assert load_agent_role_policy(str(path)).for_agent("codex").division == (
        "engineering"
    )

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(RolePolicyError) as excinfo:
        load_agent_role_policy(str(broken))
    assert str(excinfo.value) == SACHIMA_AGENT_ROLE_INVALID_POLICY
    assert str(broken) not in str(excinfo.value)


def test_an_absent_policy_is_an_empty_catalog_not_a_default() -> None:
    empty = empty_agent_role_policy()
    assert empty.assignments == ()
    assert empty.for_agent("codex") is None


def test_lookup_is_exact_and_never_folds_case() -> None:
    policy = _policy(_assignment("codex", "engineering", "code_review"))
    assert policy.for_agent("codex") is not None
    for miss in ("Codex", "codex ", "cod", "", None, 7):
        assert policy.for_agent(miss) is None


# --------------------------------------------------------------------------- #
# B. The eligibility view — every registered AGENT, and why it can or cannot run
# --------------------------------------------------------------------------- #
def test_the_view_lists_every_live_registered_agent_exactly_once() -> None:
    presets, policy = _world()
    view = build_agent_eligibility_view(
        registered_agent_ids=LIVE_ROSTER, presets=presets, role_policy=policy
    )
    assert [entry.agent_id for entry in view] == list(LIVE_ROSTER)


def test_the_view_reports_each_half_of_eligibility_separately() -> None:
    presets, policy = _world()
    view = {
        entry.agent_id: entry
        for entry in build_agent_eligibility_view(
            registered_agent_ids=LIVE_ROSTER, presets=presets, role_policy=policy
        )
    }

    codex = view["codex"]
    assert codex.registered is True
    assert codex.executable is True
    assert codex.division == "engineering"
    assert codex.roles == ("architecture_design", "code_review")
    assert codex.role_routable is True

    # Preset, no role policy: runnable when named, invisible to role routing.
    claude = view["claude"]
    assert claude.executable is True
    assert claude.division is None and claude.roles == ()
    assert claude.role_routable is False

    # Registered and nothing else: the ``oh-my-pi`` shape.
    ohmypi = view["oh-my-pi"]
    assert ohmypi.registered is True
    assert ohmypi.executable is False
    assert ohmypi.division is None and ohmypi.roles == ()
    assert ohmypi.role_routable is False


def test_a_role_assignment_without_an_execution_preset_is_not_routable() -> None:
    """Holding a role is not permission to run."""

    view = {
        entry.agent_id: entry
        for entry in build_agent_eligibility_view(
            registered_agent_ids=LIVE_ROSTER,
            presets=_presets("codex"),
            role_policy=_policy(
                _assignment("oh-my-pi", "engineering", "architecture_design")
            ),
        )
    }
    assert view["oh-my-pi"].roles == ("architecture_design",)
    assert view["oh-my-pi"].executable is False
    assert view["oh-my-pi"].role_routable is False


def test_an_agent_never_inherits_another_agents_policy() -> None:
    presets, policy = _world()
    view = {
        entry.agent_id: entry
        for entry in build_agent_eligibility_view(
            registered_agent_ids=LIVE_ROSTER, presets=presets, role_policy=policy
        )
    }
    assert view["opencode"].roles == ()
    assert view["opencode"].division is None
    assert view["opencode"].executable is False


def test_a_policy_entry_for_an_unregistered_agent_never_appears() -> None:
    """The live roster is the population; the catalog only annotates it."""

    view = build_agent_eligibility_view(
        registered_agent_ids=("codex",),
        presets=_presets("codex"),
        role_policy=_policy(
            _assignment("codex", "engineering", "code_review"),
            _assignment("cursor", "engineering", "implementation"),
        ),
    )
    assert [entry.agent_id for entry in view] == ["codex"]


def test_the_view_is_read_only_and_serializes_to_refs_and_flags_only() -> None:
    presets, policy = _world()
    (entry,) = [
        item
        for item in build_agent_eligibility_view(
            registered_agent_ids=("codex",), presets=presets, role_policy=policy
        )
    ]
    payload = entry.as_dict()
    assert payload == {
        "agent_id": "codex",
        "registered": True,
        "executable": True,
        "division": "engineering",
        "roles": ["architecture_design", "code_review"],
        "role_routable": True,
    }
    assert json.loads(json.dumps(payload)) == payload


# --------------------------------------------------------------------------- #
# C. Exact role selection — one candidate, or a question
# --------------------------------------------------------------------------- #
def test_one_exact_role_candidate_is_selectable() -> None:
    presets, policy = _world()
    selection = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER,
        presets=presets,
        role_policy=policy,
        role="architecture_design",
    )
    assert selection.agent_id == "codex"
    assert selection.refusal is None
    assert selection.candidates == ("codex",)


def test_no_candidate_is_a_stable_refusal_that_selects_nothing() -> None:
    presets, policy = _world()
    selection = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER,
        presets=presets,
        role_policy=policy,
        role="release_management",
    )
    assert selection.agent_id is None
    assert selection.refusal == SACHIMA_AGENT_ROLE_NO_CANDIDATE
    assert selection.candidates == ()


def test_several_candidates_ask_rather_than_break_the_tie() -> None:
    """No priority, no weight, and deliberately not the alphabetical first."""

    presets = _presets("codex", "cursor")
    policy = _policy(
        _assignment("codex", "engineering", "code_review"),
        _assignment("cursor", "engineering", "code_review"),
    )
    selection = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER,
        presets=presets,
        role_policy=policy,
        role="code_review",
    )
    assert selection.agent_id is None
    assert selection.refusal == SACHIMA_AGENT_ROLE_AMBIGUOUS
    assert selection.candidates == ("codex", "cursor")


def test_a_division_narrows_the_same_exact_match() -> None:
    presets = _presets("codex", "cursor")
    policy = _policy(
        _assignment("codex", "engineering", "code_review"),
        _assignment("cursor", "research", "code_review"),
    )
    selection = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER,
        presets=presets,
        role_policy=policy,
        role="code_review",
        division="research",
    )
    assert selection.agent_id == "cursor"


def test_a_division_alone_selects_when_it_is_unique() -> None:
    presets, policy = _world()
    selection = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER,
        presets=presets,
        role_policy=policy,
        division="engineering",
    )
    assert selection.refusal == SACHIMA_AGENT_ROLE_AMBIGUOUS
    assert selection.candidates == ("codex", "cursor")


def test_selection_without_a_role_or_division_selects_nothing() -> None:
    """There is no "just pick one": a filter is the whole question."""

    presets, policy = _world()
    selection = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER, presets=presets, role_policy=policy
    )
    assert selection.agent_id is None
    assert selection.refusal == SACHIMA_AGENT_ROLE_NO_CANDIDATE


@pytest.mark.parametrize(
    "role",
    [
        "Architecture_Design",
        "architecture",
        "architecture_design ",
        "design",
        "architecture_designs",
        "",
        None,
        7,
    ],
)
def test_role_matching_is_exact_with_no_fuzzy_or_case_fallback(role) -> None:
    presets, policy = _world()
    selection = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER,
        presets=presets,
        role_policy=policy,
        role=role,
    )
    assert selection.agent_id is None
    assert selection.refusal == SACHIMA_AGENT_ROLE_NO_CANDIDATE


def test_an_agent_without_an_execution_preset_is_never_a_candidate() -> None:
    policy = _policy(_assignment("oh-my-pi", "engineering", "architecture_design"))
    selection = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER,
        presets=_presets("codex"),
        role_policy=policy,
        role="architecture_design",
    )
    assert selection.agent_id is None
    assert selection.refusal == SACHIMA_AGENT_ROLE_NO_CANDIDATE


def test_an_agent_off_the_live_roster_is_never_a_candidate() -> None:
    presets, policy = _world()
    selection = select_agent_by_role(
        registered_agent_ids=("claude", "oh-my-pi"),
        presets=presets,
        role_policy=policy,
        role="architecture_design",
    )
    assert selection.refusal == SACHIMA_AGENT_ROLE_NO_CANDIDATE


def test_no_role_policy_at_all_selects_nothing_rather_than_defaulting() -> None:
    selection = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER,
        presets=_presets("codex"),
        role_policy=empty_agent_role_policy(),
        role="architecture_design",
    )
    assert selection.agent_id is None
    assert selection.refusal == SACHIMA_AGENT_ROLE_NO_CANDIDATE


def test_no_presets_at_all_selects_nothing() -> None:
    _, policy = _world()
    selection = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER,
        presets=empty_agent_execution_presets(),
        role_policy=policy,
        role="architecture_design",
    )
    assert selection.refusal == SACHIMA_AGENT_ROLE_NO_CANDIDATE


def test_every_refusal_is_one_of_the_declared_stable_codes() -> None:
    presets, policy = _world()
    contested = _policy(
        _assignment("codex", "engineering", "code_review"),
        _assignment("cursor", "engineering", "code_review"),
    )
    refusals = {
        select_agent_by_role(
            registered_agent_ids=LIVE_ROSTER,
            presets=presets,
            role_policy=catalog,
            role="code_review",
        ).refusal
        for catalog in (empty_agent_role_policy(), contested)
    }
    assert refusals == {SACHIMA_AGENT_ROLE_NO_CANDIDATE, SACHIMA_AGENT_ROLE_AMBIGUOUS}
    assert refusals <= SACHIMA_AGENT_ROLE_STABLE_CODES


def test_selection_writes_nothing_and_reaches_nothing() -> None:
    """A pure decision over three arguments: no store, no daemon, no task."""

    presets, policy = _world()
    first = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER,
        presets=presets,
        role_policy=policy,
        role="architecture_design",
    )
    second = select_agent_by_role(
        registered_agent_ids=LIVE_ROSTER,
        presets=presets,
        role_policy=policy,
        role="architecture_design",
    )
    assert first == second
