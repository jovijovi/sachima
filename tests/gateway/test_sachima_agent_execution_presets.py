"""Sachima execution presets — the deterministic half of AGENT eligibility.

Hermes owns understanding: it reads the conversation, picks or clarifies, and
hands one canonical ``agent_id`` down. Everything proven here is what happens
*after* that — a decision with no language in it at all:

* a preset binds one exact canonical ``agent_id`` to the approved execution
  configuration (workspace / agent-policy / model / effort / run-limits refs
  plus the declared permission set) and to nothing else. There is no mention
  mapping, no platform identity, no alias, no priority, no
  ``auto_selectable``, no capability ranking, and no default preset to
  inherit from;
* eligibility is exactly ``live roster ∩ valid preset``. A registered AGENT
  with no preset is reported registered-and-unavailable; a preset whose
  ``agent_id`` is absent from the live roster is unavailable. Neither ever
  submits, and neither ever reads a registry file;
* config lookup is exact and canonical: a *preset document* naming ``Codex``
  is invalid, because preset ids are configuration;
* *selection* lookup is case-insensitive exact against the live roster, so a
  person writing ``Codex`` reaches ``codex`` and the canonical roster
  spelling is what gets admitted and stored. Case is the only thing forgiven:
  ``codex ``, ``cod`` and ``code x`` resolve to nothing, and Sachima never
  guesses past that.

Everything is pure local/offline: no adapter, socket, daemon, Session, task,
or AGENT is touched, and no roster is read from anywhere but the injected
tuple. Forbidden terms in this prose are no-leak boundary canaries only,
never behavior.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from gateway.sachima_agent_execution_presets import (
    AGENT_EXECUTION_PRESETS_TYPE,
    ENGINEERING_BASELINE_PERMISSIONS,
    IMPLEMENTATION_PERMISSIONS,
    SACHIMA_AGENT_ID_PATTERN,
    SACHIMA_AGENT_INVALID_ID,
    SACHIMA_AGENT_INVALID_PRESETS,
    SACHIMA_AGENT_NO_PRESET,
    SACHIMA_AGENT_NOT_REGISTERED,
    SACHIMA_AGENT_PRESET_STABLE_CODES,
    SACHIMA_AGENT_TASK_TOO_LARGE,
    AgentExecutionPreset,
    AgentExecutionPresets,
    PresetError,
    admit_agent_execution,
    build_agent_execution_presets,
    canonical_agent_id,
    empty_agent_execution_presets,
    load_agent_execution_presets,
    requested_configuration,
    resolve_selected_agent_id,
)

#: The roster the deployed daemon actually answered with, in its own
#: ``tuple(sorted(entries))`` order.
LIVE_ROSTER = ("claude", "codex", "cursor", "oh-my-pi", "opencode")


class _Config:
    """The five ARS ref maps plus the operator's approved capability grant."""

    def __init__(self, **maps: Any):
        self.workspace_by_ref = maps.get("workspace", {"ws_main": "/tmp/ws"})
        self.agent_by_policy_ref = maps.get(
            "agent",
            {
                "policy_codex": "codex",
                "policy_claude": "claude",
                "policy_cursor": "cursor",
                "policy_mismatched": "claude",
            },
        )
        self.model_by_policy_ref = maps.get("model", {"policy_model": "claude-opus-5"})
        self.effort_by_policy_ref = maps.get("effort", {"policy_effort": "xhigh"})
        self.run_limits_by_policy_ref = maps.get("limits", {"policy_limits": {}})
        self.grant_capabilities = maps.get(
            "grant", ("execute", "read", "search", "write")
        )
        #: Per-policy sealed grants. Every preset's policy needs one: it is
        #: the exact capability set that policy's Runs are submitted under.
        self.grant_by_policy_ref = maps.get(
            "grant_by_policy",
            {
                "policy_codex": ENGINEERING_BASELINE_PERMISSIONS,
                "policy_claude": ENGINEERING_BASELINE_PERMISSIONS,
                "policy_cursor": ENGINEERING_BASELINE_PERMISSIONS,
                "policy_mismatched": ENGINEERING_BASELINE_PERMISSIONS,
                "policy_shared": ENGINEERING_BASELINE_PERMISSIONS,
            },
        )


def _entry(agent_id: str, **overrides: Any) -> dict[str, Any]:
    entry = {
        "agent_id": agent_id,
        "workspace_ref": "ws_main",
        "agent_policy_ref": f"policy_{agent_id}",
        "model_policy_ref": "policy_model",
        "effort_policy_ref": "policy_effort",
        "run_limits_policy_ref": "policy_limits",
        "permissions": list(ENGINEERING_BASELINE_PERMISSIONS),
    }
    entry.update(overrides)
    return entry


def _presets(*entries: dict[str, Any], config=None) -> AgentExecutionPresets:
    return build_agent_execution_presets(
        {"type": AGENT_EXECUTION_PRESETS_TYPE, "presets": list(entries)},
        config or _Config(),
    )


def _admit(presets, agent_id, *, roster=LIVE_ROSTER, task_text="do the thing"):
    return admit_agent_execution(
        presets,
        agent_id=agent_id,
        registered_agent_ids=roster,
        task_text=task_text,
    )


# --------------------------------------------------------------------------- #
# A. The preset document
# --------------------------------------------------------------------------- #
def test_a_preset_binds_one_canonical_agent_id_to_its_approved_refs() -> None:
    presets = _presets(_entry("codex"))
    (preset,) = presets.presets

    assert preset.agent_id == "codex"
    assert preset.workspace_ref == "ws_main"
    assert preset.agent_policy_ref == "policy_codex"
    assert preset.permissions == ENGINEERING_BASELINE_PERMISSIONS
    assert preset.launch_refs == (
        "ws_main",
        "policy_codex",
        "policy_model",
        "policy_effort",
        "policy_limits",
    )


def test_a_preset_collapses_repeated_refs_into_first_seen_order() -> None:
    """The backend matches the ref *set* against five maps and demands one
    match per map, so a ref serving several categories appears once."""

    config = _Config(
        agent={"policy_shared": "codex"},
        model={"policy_shared": "claude-opus-5"},
        effort={"policy_shared": "xhigh"},
        limits={"policy_shared": {}},
    )
    presets = _presets(
        _entry(
            "codex",
            agent_policy_ref="policy_shared",
            model_policy_ref="policy_shared",
            effort_policy_ref="policy_shared",
            run_limits_policy_ref="policy_shared",
        ),
        config=config,
    )
    (preset,) = presets.presets
    assert preset.launch_refs == ("ws_main", "policy_shared")


def test_the_requested_triple_comes_from_the_presets_own_refs() -> None:
    config = _Config()
    (preset,) = _presets(_entry("codex"), config=config).presets
    assert requested_configuration(config, preset) == (
        "codex",
        "claude-opus-5",
        "xhigh",
    )


def test_an_implementation_preset_declares_write_over_the_baseline() -> None:
    authoring = _Config(
        grant_by_policy={"policy_codex": IMPLEMENTATION_PERMISSIONS}
    )
    (preset,) = _presets(
        _entry("codex", permissions=list(IMPLEMENTATION_PERMISSIONS)),
        config=authoring,
    ).presets
    assert preset.permissions == IMPLEMENTATION_PERMISSIONS
    assert preset.writes_workspace is True

    (review,) = _presets(_entry("codex")).presets
    assert review.writes_workspace is False


def test_permissions_are_canonically_ordered_rather_than_as_typed() -> None:
    """A preset's identity may not depend on the order someone typed."""

    (preset,) = _presets(
        _entry("codex", permissions=["search", "execute", "read"])
    ).presets
    assert preset.permissions == ENGINEERING_BASELINE_PERMISSIONS


@pytest.mark.parametrize(
    "overrides",
    [
        {"agent_id": "Codex"},
        {"agent_id": "codex "},
        {"agent_id": "-codex"},
        {"agent_id": "a" * 65},
        {"agent_id": ""},
        {"agent_id": None},
        {"agent_id": 7},
        {"workspace_ref": "ws_not_configured"},
        {"agent_policy_ref": "policy_not_configured"},
        {"model_policy_ref": "policy_not_configured"},
        {"effort_policy_ref": "policy_not_configured"},
        {"run_limits_policy_ref": "policy_not_configured"},
        {"workspace_ref": "policy_codex"},
        {"agent_policy_ref": "ws_main"},
        {"permissions": []},
        {"permissions": ["read", "search"]},
        {"permissions": ["read", "search", "execute", "delete"]},
        {"permissions": ["read", "search", "execute", "read"]},
        {"permissions": "read search execute"},
        {"permissions": None},
        {"max_task_bytes": 0},
        {"max_task_bytes": -1},
        {"max_task_bytes": 32_769},
        {"max_task_bytes": True},
        {"max_task_bytes": "32768"},
    ],
    ids=[
        "uppercase_id",
        "trailing_space_id",
        "leading_hyphen_id",
        "overlong_id",
        "empty_id",
        "none_id",
        "int_id",
        "workspace_ref_absent_from_config",
        "agent_policy_ref_absent_from_config",
        "model_policy_ref_absent_from_config",
        "effort_policy_ref_absent_from_config",
        "run_limits_policy_ref_absent_from_config",
        "workspace_ref_wrong_prefix",
        "agent_policy_ref_wrong_prefix",
        "no_permissions",
        "permissions_below_the_engineering_baseline",
        "permission_outside_the_closed_vocabulary",
        "duplicate_permission",
        "permissions_not_a_list",
        "permissions_none",
        "zero_task_bound",
        "negative_task_bound",
        "task_bound_over_the_ceiling",
        "bool_task_bound",
        "string_task_bound",
    ],
)
def test_a_deviating_preset_entry_fails_closed(overrides: dict) -> None:
    with pytest.raises(PresetError) as excinfo:
        _presets({**_entry("codex"), **overrides})
    assert str(excinfo.value) == SACHIMA_AGENT_INVALID_PRESETS


def test_a_preset_may_not_declare_more_than_the_operator_granted() -> None:
    """A preset chooses *among* what the operator approved; never above it.

    The wire grant is config-wide, so a preset claiming ``write`` under a
    read-only grant would be a declaration the deployment cannot honor.
    """

    config = _Config(grant=("execute", "read", "search"))
    _presets(_entry("codex"), config=config)  # baseline fits the grant

    with pytest.raises(PresetError) as excinfo:
        _presets(
            _entry("codex", permissions=list(IMPLEMENTATION_PERMISSIONS)),
            config=config,
        )
    assert str(excinfo.value) == SACHIMA_AGENT_INVALID_PRESETS


def test_a_preset_must_point_at_the_agent_policy_that_resolves_to_its_id() -> None:
    """The binding is checked, not assumed.

    ``agent_id`` is what the roster and the user talk about; the submitted
    Run's AGENT comes from ``agent_by_policy_ref``. A preset where those two
    disagree would name one AGENT and run another.
    """

    with pytest.raises(PresetError) as excinfo:
        _presets(_entry("codex", agent_policy_ref="policy_mismatched"))
    assert str(excinfo.value) == SACHIMA_AGENT_INVALID_PRESETS


@pytest.mark.parametrize(
    "document",
    [
        {"type": AGENT_EXECUTION_PRESETS_TYPE},
        {"presets": []},
        {"type": "sachima.gateway.delegate_policy.v1", "presets": []},
        {"type": AGENT_EXECUTION_PRESETS_TYPE, "presets": []},
        {"type": AGENT_EXECUTION_PRESETS_TYPE, "presets": {}},
        {"type": AGENT_EXECUTION_PRESETS_TYPE, "presets": None},
        {"type": AGENT_EXECUTION_PRESETS_TYPE, "presets": [], "default": "claude"},
        None,
        [],
        "codex",
    ],
    ids=[
        "no_presets_key",
        "no_type_key",
        "retired_policy_document_type",
        "empty_preset_list",
        "presets_is_a_mapping",
        "presets_is_none",
        "extra_top_level_key",
        "none",
        "bare_list",
        "bare_string",
    ],
)
def test_a_deviating_preset_document_fails_closed(document) -> None:
    with pytest.raises(PresetError) as excinfo:
        build_agent_execution_presets(document, _Config())
    assert str(excinfo.value) == SACHIMA_AGENT_INVALID_PRESETS


def test_an_unknown_preset_key_fails_closed_rather_than_being_ignored() -> None:
    """A typo may not silently drop a field, and a retired routing field may
    not be quietly accepted and ignored."""

    for retired in (
        "profile_id",
        "mentions",
        "auto_selectable",
        "priority",
        "capabilities",
        "enabled",
        "summary",
    ):
        with pytest.raises(PresetError):
            _presets(_entry("codex", **{retired: "whatever"}))


def test_two_presets_may_not_claim_one_agent_id() -> None:
    with pytest.raises(PresetError):
        _presets(_entry("codex"), _entry("codex"))


def test_a_preset_file_is_read_and_validated_and_never_echoed(tmp_path) -> None:
    path = tmp_path / "presets.json"
    path.write_text(
        json.dumps(
            {"type": AGENT_EXECUTION_PRESETS_TYPE, "presets": [_entry("codex")]}
        ),
        encoding="utf-8",
    )
    presets = load_agent_execution_presets(str(path), _Config())
    assert presets.agent_ids() == ("codex",)

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(PresetError) as excinfo:
        load_agent_execution_presets(str(broken), _Config())
    assert str(excinfo.value) == SACHIMA_AGENT_INVALID_PRESETS
    assert str(broken) not in str(excinfo.value)


def test_an_absent_preset_file_is_an_empty_catalog_not_a_synthesized_default() -> None:
    """No configuration means nothing is eligible — never a default AGENT.

    A synthesized single preset is exactly the "inherit the Claude/default
    configuration" behavior this catalog exists to remove, so the empty
    catalog is a real answer rather than a fallback.
    """

    empty = empty_agent_execution_presets()
    assert empty.presets == ()
    assert empty.agent_ids() == ()
    assert empty.preset("claude") is None
    assert _admit(empty, "claude").refusal == SACHIMA_AGENT_NO_PRESET


# --------------------------------------------------------------------------- #
# B. Lookup is exact
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "requested",
    ["Codex", "CODEX", " codex", "codex ", "cod", "codexx", "code x", "", None, 7],
)
def test_catalog_lookup_never_resembles_and_never_folds_case(requested) -> None:
    """The catalog is keyed on canonical ids only.

    Case folding belongs to selection, one layer up, where the roster supplies
    the canonical spelling this lookup is then given.
    """

    presets = _presets(_entry("codex"))
    assert presets.preset("codex") is not None
    assert presets.preset(requested) is None


def test_the_catalog_exposes_no_routing_surface() -> None:
    """Nothing here can choose an AGENT: choosing is Hermes's job."""

    presets = _presets(_entry("codex"), _entry("claude"))
    for retired in (
        "by_mention",
        "resolve_route",
        "choices",
        "default",
        "candidates",
        "rank",
    ):
        assert not hasattr(presets, retired)
    for retired in ("mention_ids", "auto_selectable", "priority", "capabilities"):
        assert not hasattr(presets.presets[0], retired)


def test_the_mirrored_agent_id_grammar_is_the_daemons_own() -> None:
    """Drift-lock: the canonical grammar is mirrored from the ARS contract."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_AGENT_ID_PATTERN,
    )

    assert SACHIMA_AGENT_ID_PATTERN == ARSD_AGENT_ID_PATTERN


# --------------------------------------------------------------------------- #
# C. Admission — exactly ``live roster ∩ valid preset``
# --------------------------------------------------------------------------- #
def test_an_exact_id_in_both_the_roster_and_the_catalog_is_admitted() -> None:
    presets = _presets(_entry("codex"))
    admission = _admit(presets, "codex")

    assert admission.admitted is True
    assert admission.refusal is None
    assert admission.registered is True
    assert admission.agent_id == "codex"
    assert admission.preset.agent_id == "codex"


def test_a_registered_agent_with_no_preset_is_registered_but_unavailable() -> None:
    """The ``oh-my-pi`` shape: on the roster, no Sachima preset.

    It is reported as registered so the answer is honest, and it is refused
    so nothing runs. It never borrows another preset's workspace, model,
    effort, limits, or permissions — which is exactly why this change cannot
    silently rewrite an AGENT's existing production configuration.
    """

    presets = _presets(_entry("codex"))
    admission = _admit(presets, "oh-my-pi")

    assert admission.admitted is False
    assert admission.refusal == SACHIMA_AGENT_NO_PRESET
    assert admission.registered is True
    assert admission.agent_id == "oh-my-pi"
    assert admission.preset is None


def test_a_preset_whose_agent_is_absent_from_the_roster_is_unavailable() -> None:
    """No registry file is consulted to make the absence go away."""

    presets = _presets(_entry("codex"))
    admission = _admit(presets, "codex", roster=("claude", "cursor"))

    assert admission.admitted is False
    assert admission.refusal == SACHIMA_AGENT_NOT_REGISTERED
    assert admission.registered is False
    assert admission.preset is None


def test_an_id_in_neither_the_roster_nor_the_catalog_is_unavailable() -> None:
    admission = _admit(_presets(_entry("codex")), "tom")
    assert admission.refusal == SACHIMA_AGENT_NOT_REGISTERED
    assert admission.registered is False


@pytest.mark.parametrize(
    "agent_id",
    ["codex ", " codex", "co dex", "", None, 7, "a" * 65, "../codex"],
)
def test_a_malformed_id_is_refused_before_the_roster_is_even_consulted(
    agent_id,
) -> None:
    """Shape first: something that is not an id cannot be registered.

    ``Codex`` is deliberately absent — differing only by case is what section
    D proves is *resolvable*, not malformed."""

    admission = _admit(_presets(_entry("codex")), agent_id)
    assert admission.admitted is False
    assert admission.refusal == SACHIMA_AGENT_INVALID_ID
    assert admission.registered is False
    # A value that failed the grammar is never carried back out.
    assert admission.agent_id is None


def test_a_task_over_the_presets_bound_is_refused_before_anything_exists() -> None:
    presets = _presets(_entry("codex", max_task_bytes=16))
    assert _admit(presets, "codex", task_text="x" * 16).admitted is True

    oversized = _admit(presets, "codex", task_text="x" * 17)
    assert oversized.admitted is False
    assert oversized.refusal == SACHIMA_AGENT_TASK_TOO_LARGE
    assert oversized.registered is True


def test_the_task_bound_is_measured_in_utf8_bytes() -> None:
    presets = _presets(_entry("codex", max_task_bytes=4))
    assert _admit(presets, "codex", task_text="abcd").admitted is True
    assert _admit(presets, "codex", task_text="漢字").admitted is False


@pytest.mark.parametrize(
    "roster",
    [None, "codex", ["codex"], (b"codex",), ("codex", 7), ("Codex",)],
)
def test_a_roster_that_is_not_a_validated_tuple_of_ids_admits_nothing(roster) -> None:
    """Admission trusts the contract validator's output, not any tuple.

    A caller that hands over an unvalidated roster gets a refusal rather
    than an admission built on material nobody checked.
    """

    admission = admit_agent_execution(
        _presets(_entry("codex")),
        agent_id="codex",
        registered_agent_ids=roster,
        task_text="do the thing",
    )
    assert admission.admitted is False
    assert admission.refusal == SACHIMA_AGENT_NOT_REGISTERED


def test_every_refusal_is_one_of_the_declared_stable_codes() -> None:
    presets = _presets(_entry("codex", max_task_bytes=16))
    refusals = {
        _admit(presets, "oh-my-pi").refusal,
        _admit(presets, "codex", roster=("claude",)).refusal,
        _admit(presets, "co dex").refusal,
        _admit(presets, "codex", task_text="x" * 17).refusal,
    }
    assert refusals <= SACHIMA_AGENT_PRESET_STABLE_CODES
    assert len(refusals) == 4


def test_admission_is_a_pure_decision_with_no_io_of_its_own() -> None:
    """It opens nothing, writes nothing, and reaches no daemon.

    The roster is an argument precisely so this stays true: the one live read
    belongs to the backend, and the intersection is arithmetic.
    """

    presets = _presets(_entry("codex"))
    first = _admit(presets, "codex")
    second = _admit(presets, "codex")
    assert first.preset is second.preset
    assert isinstance(first.preset, AgentExecutionPreset)


# --------------------------------------------------------------------------- #
# D. Selection input is case-insensitive **exact**; stored identity is canonical
#
# Two different questions were being answered by one function. A preset
# document is configuration — its ids are canonical, lowercase, and wrong if
# they are not. A selection is a person naming an AGENT through Hermes, and a
# person writes ``Codex``. Case-insensitive *exact* matching against the live
# roster resolves the second without loosening the first, and the canonical
# roster spelling is what gets carried, admitted and stored.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spelling", ["codex", "Codex", "CODEX", "CoDeX"])
def test_a_selection_resolves_case_insensitively_to_the_roster_spelling(
    spelling,
) -> None:
    assert resolve_selected_agent_id(spelling, LIVE_ROSTER) == "codex"


def test_a_hyphenated_roster_id_resolves_the_same_way() -> None:
    assert resolve_selected_agent_id("Oh-My-Pi", LIVE_ROSTER) == "oh-my-pi"


@pytest.mark.parametrize(
    "spelling",
    [
        "codex ",
        " codex",
        "\tcodex",
        "codex\n",
        "cod",
        "codexx",
        "code x",
        "co*dex",
        "",
        None,
        7,
        "a" * 65,
        "../codex",
    ],
    ids=[
        "trailing_space",
        "leading_space",
        "leading_tab",
        "newline",
        "prefix",
        "suffix_extra",
        "inner_space",
        "wildcard",
        "empty",
        "none",
        "int",
        "too_long",
        "traversal",
    ],
)
def test_selection_never_trims_and_never_matches_partially(spelling) -> None:
    """Exact means exact: only letter case is forgiven."""

    assert resolve_selected_agent_id(spelling, LIVE_ROSTER) is None


def test_a_casefold_collision_in_the_roster_fails_closed() -> None:
    """Upstream validation should make this impossible; it still refuses.

    Two roster entries that differ only by case cannot both be "the one the
    user meant", so neither is chosen.
    """

    assert resolve_selected_agent_id("codex", ("Codex", "codex")) is None
    assert resolve_selected_agent_id("Codex", ("Codex", "codex")) is None
    # The unaffected neighbours still resolve.
    assert resolve_selected_agent_id("Claude", ("Codex", "claude", "codex")) == "claude"


def test_preset_documents_still_demand_strict_canonical_ids() -> None:
    """The config half did not loosen: ``Codex`` is not a preset id."""

    with pytest.raises(PresetError):
        _presets({**_entry("codex"), "agent_id": "Codex"})
    assert canonical_agent_id("Codex") is None
    assert canonical_agent_id("codex") == "codex"


@pytest.mark.parametrize("spelling", ["Codex", "CODEX", "CoDeX"])
def test_admission_accepts_a_cased_selection_and_stores_the_canonical_id(
    spelling,
) -> None:
    admission = _admit(_presets(_entry("codex")), spelling)

    assert admission.admitted is True
    assert admission.agent_id == "codex"
    assert admission.preset.agent_id == "codex"


def test_a_cased_selection_of_a_registered_agent_without_a_preset_still_reports_it() -> None:
    admission = _admit(_presets(_entry("codex")), "OH-MY-PI")
    assert admission.refusal == SACHIMA_AGENT_NO_PRESET
    assert admission.registered is True
    assert admission.agent_id == "oh-my-pi"


def test_an_unregistered_name_is_echoed_as_the_user_wrote_it() -> None:
    """Hermes has to be able to say *which* name it could not find."""

    admission = _admit(_presets(_entry("codex")), "Tom")
    assert admission.refusal == SACHIMA_AGENT_NOT_REGISTERED
    assert admission.registered is False
    assert admission.agent_id == "Tom"


def test_a_shape_violating_selection_is_never_echoed_back() -> None:
    admission = _admit(_presets(_entry("codex")), "../../etc/passwd")
    assert admission.refusal == SACHIMA_AGENT_INVALID_ID
    assert admission.agent_id is None


def test_a_casefold_collision_refuses_with_its_own_code() -> None:
    admission = admit_agent_execution(
        _presets(_entry("codex")),
        agent_id="codex",
        registered_agent_ids=("Codex", "codex"),
        task_text="do the thing",
    )
    assert admission.admitted is False
    assert admission.refusal == SACHIMA_AGENT_NOT_REGISTERED


# --------------------------------------------------------------------------- #
# E. A preset's declared permissions ARE the grant its Runs are sealed under
#
# The declaration and the wire used to be two unconnected facts: a preset
# could say ``read/search/execute`` while every Run it produced carried the
# config-wide ``write`` as well. The document a human reviews and the
# capability set a Run executes under are now the same object, and a preset
# whose declaration does not match its policy's approved grant does not build.
# --------------------------------------------------------------------------- #
def test_a_presets_permissions_must_equal_its_policys_approved_grant() -> None:
    config = _Config(
        grant_by_policy={
            "policy_codex": ENGINEERING_BASELINE_PERMISSIONS,
            "policy_claude": IMPLEMENTATION_PERMISSIONS,
        }
    )
    (review,) = _presets(_entry("codex"), config=config).presets
    assert review.permissions == ENGINEERING_BASELINE_PERMISSIONS

    (author,) = _presets(
        _entry("claude", permissions=list(IMPLEMENTATION_PERMISSIONS)),
        config=config,
    ).presets
    assert author.permissions == IMPLEMENTATION_PERMISSIONS


@pytest.mark.parametrize(
    "declared",
    [
        list(IMPLEMENTATION_PERMISSIONS),
        ["read", "search", "execute"],
    ],
    ids=["declares_more_than_the_grant", "declares_the_grant_in_another_order"],
)
def test_a_declaration_that_does_not_match_the_sealed_grant(declared) -> None:
    """Order is irrelevant; membership is not."""

    config = _Config(grant_by_policy={"policy_codex": ("execute", "read", "search")})
    if sorted(declared) == sorted(ENGINEERING_BASELINE_PERMISSIONS):
        (preset,) = _presets(
            {**_entry("codex"), "permissions": declared}, config=config
        ).presets
        assert preset.permissions == ENGINEERING_BASELINE_PERMISSIONS
        return
    with pytest.raises(PresetError) as excinfo:
        _presets({**_entry("codex"), "permissions": declared}, config=config)
    assert str(excinfo.value) == SACHIMA_AGENT_INVALID_PRESETS


def test_a_policy_with_no_sealed_grant_cannot_carry_a_preset() -> None:
    """No sealed grant means the Run would inherit the config-wide one.

    That is the exact silent widening this check exists to make impossible, so
    the preset does not build rather than building and over-granting.
    """

    config = _Config(grant_by_policy={"policy_claude": ENGINEERING_BASELINE_PERMISSIONS})
    with pytest.raises(PresetError) as excinfo:
        _presets(_entry("codex"), config=config)
    assert str(excinfo.value) == SACHIMA_AGENT_INVALID_PRESETS


def test_a_preset_still_cannot_exceed_the_operator_grant() -> None:
    """Both gates hold: the per-policy grant *and* the config-wide ceiling."""

    config = _Config(
        grant=("execute", "read", "search"),
        grant_by_policy={"policy_codex": IMPLEMENTATION_PERMISSIONS},
    )
    with pytest.raises(PresetError):
        _presets(
            {**_entry("codex"), "permissions": list(IMPLEMENTATION_PERMISSIONS)},
            config=config,
        )
