"""S1 — cross-IM ``/delegate [@AGENT] <task>`` selection and deterministic routing.

What is proven here:

* Feishu **text placeholders and post ``<at>`` elements** both survive
  normalization as neutral occurrences carrying the sender's stable ``open_id``
  and half-open ``[start, end)`` coordinates into the *final* text, through
  titles, rows, newline joins, whitespace collapsing, and leading-self stripping
  — identical display names included;
* the selector takes only the occurrence that starts immediately after the
  command; later mentions of the same display name stay in the task verbatim;
* a raw typed look-alike (no structured provenance) **refuses** rather than
  falling through to automatic routing, and so does an occurrence that maps to
  nothing or to a disabled profile — even when another profile is
  auto-selectable;
* one deterministic router serves every creation path: explicit wins or refuses,
  automatic filters by size/capability, one candidate wins, a priority tie asks
  for clarification;
* the legacy synthesis reproduces today's single profile — and only when the ARS
  config offers no choice.

Everything is pure local/offline: no adapter connection, socket, daemon, Session,
or AGENT is touched. Forbidden terms in this prose are no-leak boundary canaries
only, never behavior.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from gateway.platforms.base import MentionOccurrence
from gateway.platforms.feishu import _FeishuBotIdentity, normalize_feishu_message
from gateway.sachima_delegate_policy import (
    DELEGATE_POLICY_TYPE,
    SACHIMA_DELEGATE_AMBIGUOUS_ROUTE,
    SACHIMA_DELEGATE_INVALID_POLICY,
    SACHIMA_DELEGATE_NO_ROUTE,
    SACHIMA_DELEGATE_TASK_TOO_LARGE,
    SACHIMA_DELEGATE_UNKNOWN_PROFILE,
    SACHIMA_DELEGATE_UNKNOWN_SELECTOR,
    PolicyError,
    build_delegate_policy,
    requested_configuration,
    resolve_route,
    synthesize_legacy_policy,
)
from gateway.sachima_delegate_selector import (
    SACHIMA_DELEGATE_UNVERIFIED_SELECTOR,
    parse_delegate_selection,
)


# --------------------------------------------------------------------------- #
# Feishu fixtures
# --------------------------------------------------------------------------- #
def _mention(key: str, *, open_id: str, name: str):
    return SimpleNamespace(
        key=key, name=name, id=SimpleNamespace(open_id=open_id, user_id="")
    )


BOT = _FeishuBotIdentity(open_id="ou_bot", user_id="u_bot", name="Hermes")


def _text_message(text: str, mentions):
    return normalize_feishu_message(
        message_type="text",
        raw_content=json.dumps({"text": text}),
        mentions=mentions,
        bot=BOT,
    )


def _post_message(payload: dict, mentions):
    return normalize_feishu_message(
        message_type="post",
        raw_content=json.dumps(payload),
        mentions=mentions,
        bot=BOT,
    )


def _assert_coordinates(normalized) -> None:
    """Every occurrence must actually describe the text it is positioned in."""

    for occurrence in normalized.mention_occurrences:
        assert type(occurrence) is MentionOccurrence
        assert occurrence.matches_text(normalized.text_content)


# --------------------------------------------------------------------------- #
# A. Feishu text occurrences
# --------------------------------------------------------------------------- #
def test_text_placeholder_becomes_a_positioned_occurrence_with_open_id():
    normalized = _text_message(
        "/delegate @_user_1 write the release notes",
        [_mention("@_user_1", open_id="ou_alice", name="Alice")],
    )
    assert normalized.text_content == "/delegate @Alice write the release notes"
    _assert_coordinates(normalized)
    (occurrence,) = normalized.mention_occurrences
    assert occurrence.platform_user_id == "ou_alice"
    assert occurrence.rendered == "@Alice"
    assert normalized.text_content[occurrence.start : occurrence.end] == "@Alice"


def test_identical_display_names_keep_distinct_identities_and_positions():
    """A display name is not identity: two Alices are two different AGENTs."""

    normalized = _text_message(
        "/delegate @_user_1 ping @_user_2 about it",
        [
            _mention("@_user_1", open_id="ou_alice_one", name="Alice"),
            _mention("@_user_2", open_id="ou_alice_two", name="Alice"),
        ],
    )
    assert normalized.text_content == "/delegate @Alice ping @Alice about it"
    _assert_coordinates(normalized)
    first, second = sorted(normalized.mention_occurrences, key=lambda o: o.start)
    assert first.platform_user_id == "ou_alice_one"
    assert second.platform_user_id == "ou_alice_two"
    assert first.start < second.start


def test_a_leading_self_mention_is_stripped_and_the_rest_is_remapped():
    """Stripping the bot's own mention must move the survivors, not orphan them."""

    from gateway.platforms.feishu import strip_edge_self_mentions_with_occurrences

    normalized = _text_message(
        "@_user_9 /delegate @_user_1 ship it",
        [
            _mention("@_user_9", open_id="ou_bot", name="Hermes"),
            _mention("@_user_1", open_id="ou_alice", name="Alice"),
        ],
    )
    text, occurrences = strip_edge_self_mentions_with_occurrences(
        normalized.text_content,
        normalized.mentions,
        normalized.mention_occurrences,
    )
    assert text == "/delegate @Alice ship it"
    assert [o.platform_user_id for o in occurrences] == ["ou_alice"]
    (occurrence,) = occurrences
    assert occurrence.matches_text(text)
    assert text[occurrence.start : occurrence.end] == "@Alice"


def test_at_all_is_a_verified_occurrence_that_never_carries_an_identity():
    normalized = _text_message("/delegate @_all everyone", [])
    assert normalized.text_content == "/delegate @all everyone"
    _assert_coordinates(normalized)
    (occurrence,) = normalized.mention_occurrences
    assert occurrence.is_all is True
    assert occurrence.platform_user_id == ""


# --------------------------------------------------------------------------- #
# B. Feishu post occurrences (A3)
# --------------------------------------------------------------------------- #
POST_COMMAND = {
    "zh_cn": {
        "title": "Ops",
        "content": [
            [
                {"tag": "text", "text": "/delegate "},
                {"tag": "at", "user_id": "@_user_1", "user_name": "Alice"},
                {"tag": "text", "text": "  write   the   release notes"},
            ],
            [{"tag": "text", "text": "second row"}],
        ],
    }
}


def test_post_at_elements_keep_open_id_and_final_text_offsets():
    normalized = _post_message(
        POST_COMMAND, [_mention("@_user_1", open_id="ou_alice", name="Alice")]
    )
    assert normalized.text_content == (
        "Ops\n/delegate @Alice write the release notes\nsecond row"
    )
    _assert_coordinates(normalized)
    (occurrence,) = normalized.mention_occurrences
    assert occurrence.platform_user_id == "ou_alice"


def test_equivalent_text_and_post_commands_route_the_same_way():
    text_message = _text_message(
        "/delegate @_user_1 write the release notes",
        [_mention("@_user_1", open_id="ou_alice", name="Alice")],
    )
    post_message = _post_message(
        {
            "zh_cn": {
                "title": "",
                "content": [
                    [
                        {"tag": "text", "text": "/delegate "},
                        {"tag": "at", "user_id": "@_user_1", "user_name": "Alice"},
                        {"tag": "text", "text": " write the release notes"},
                    ]
                ],
            }
        },
        [_mention("@_user_1", open_id="ou_alice", name="Alice")],
    )
    assert post_message.text_content == text_message.text_content

    from_text = parse_delegate_selection(
        text_message.text_content, text_message.mention_occurrences
    )
    from_post = parse_delegate_selection(
        post_message.text_content, post_message.mention_occurrences
    )
    assert from_text == from_post
    assert from_text.platform_user_id == "ou_alice"
    assert from_text.task_text == "write the release notes"


ESCAPED_BOT_NAMES = ("Hermes_Bot", "Hermes*Bot", "Hermes\\Ops[Bot]!")


def _self_bot(name):
    return _FeishuBotIdentity(open_id="ou_bot", user_id="u_bot", name=name)


def _post_with_self_prefix(name, tail_elements, mentions):
    """A post whose first element is the bot's own ``<at>``."""

    return normalize_feishu_message(
        message_type="post",
        raw_content=json.dumps(
            {
                "zh_cn": {
                    "title": "",
                    "content": [
                        [
                            {
                                "tag": "at",
                                "user_id": "@_user_9",
                                "user_name": name,
                            },
                            *tail_elements,
                        ]
                    ],
                }
            }
        ),
        mentions=[
            _mention("@_user_9", open_id="ou_bot", name=name),
            *mentions,
        ],
        bot=_self_bot(name),
    )


@pytest.mark.parametrize("name", ESCAPED_BOT_NAMES)
def test_an_escaped_self_mention_never_hides_the_command(name):
    """Markdown escaping is presentation; it may not cost the user the command."""

    from gateway.platforms.feishu import strip_edge_self_mentions_with_occurrences

    normalized = _post_with_self_prefix(
        name, [{"tag": "text", "text": " /delegate do the task"}], []
    )
    text, occurrences = strip_edge_self_mentions_with_occurrences(
        normalized.text_content, normalized.mentions, normalized.mention_occurrences
    )
    assert text == "/delegate do the task"
    assert occurrences == ()
    assert text.startswith("/") is True
    decision = parse_delegate_selection(text, occurrences)
    assert decision.refused is False
    assert decision.has_selector is False
    assert decision.task_text == "do the task"


@pytest.mark.parametrize("name", ESCAPED_BOT_NAMES)
def test_an_escaped_self_mention_still_leaves_the_selector_verifiable(name):
    from gateway.platforms.feishu import strip_edge_self_mentions_with_occurrences

    normalized = _post_with_self_prefix(
        name,
        [
            {"tag": "text", "text": " /delegate "},
            {"tag": "at", "user_id": "@_user_1", "user_name": "Alice"},
            {"tag": "text", "text": " ship it"},
        ],
        [_mention("@_user_1", open_id="ou_alice", name="Alice")],
    )
    text, occurrences = strip_edge_self_mentions_with_occurrences(
        normalized.text_content, normalized.mentions, normalized.mention_occurrences
    )
    assert text == "/delegate @Alice ship it"
    for occurrence in occurrences:
        assert occurrence.matches_text(text)
    decision = parse_delegate_selection(text, occurrences)
    assert decision.platform_user_id == "ou_alice"
    assert decision.task_text == "ship it"


def test_a_non_self_leading_mention_with_an_escaped_name_still_blocks_the_command():
    """Someone else's mention is task material, not a prefix to remove."""

    from gateway.platforms.feishu import strip_edge_self_mentions_with_occurrences

    normalized = normalize_feishu_message(
        message_type="post",
        raw_content=json.dumps(
            {
                "zh_cn": {
                    "title": "",
                    "content": [
                        [
                            {
                                "tag": "at",
                                "user_id": "@_user_1",
                                "user_name": "Hermes_Bot",
                            },
                            {"tag": "text", "text": " /delegate do the task"},
                        ]
                    ],
                }
            }
        ),
        mentions=[_mention("@_user_1", open_id="ou_impostor", name="Hermes_Bot")],
        bot=_self_bot("Hermes_Bot"),
    )
    text, occurrences = strip_edge_self_mentions_with_occurrences(
        normalized.text_content, normalized.mentions, normalized.mention_occurrences
    )
    assert text == "@Hermes\\_Bot /delegate do the task"
    assert [o.platform_user_id for o in occurrences] == ["ou_impostor"]
    assert text.startswith("/") is False


# --------------------------------------------------------------------------- #
# C. The selector
# --------------------------------------------------------------------------- #
def _occ(start, end, rendered, *, user_id="ou_alice", **flags):
    return MentionOccurrence(
        platform_user_id=user_id, start=start, end=end, rendered=rendered, **flags
    )


def test_no_selector_leaves_the_whole_task_and_routes_automatically():
    decision = parse_delegate_selection("/delegate write the release notes", ())
    assert decision.task_text == "write the release notes"
    assert decision.has_selector is False
    assert decision.refused is False


def test_only_the_occurrence_right_after_the_command_selects():
    text = "/delegate @Alice tell @Alice we shipped"
    occurrences = (
        _occ(10, 16, "@Alice", user_id="ou_alice"),
        _occ(22, 28, "@Alice", user_id="ou_alice"),
    )
    decision = parse_delegate_selection(text, occurrences)
    assert decision.platform_user_id == "ou_alice"
    # The later mention is task material, verbatim.
    assert decision.task_text == "tell @Alice we shipped"


def test_a_raw_typed_look_alike_refuses_and_never_auto_routes():
    decision = parse_delegate_selection("/delegate @Alice ship it", ())
    assert decision.refusal == SACHIMA_DELEGATE_UNVERIFIED_SELECTOR
    assert decision.has_selector is False
    assert decision.task_text == ""


def test_a_stale_occurrence_position_is_discarded_not_trusted():
    """Coordinates that no longer describe the text cannot select an AGENT."""

    decision = parse_delegate_selection(
        "/delegate @Alice ship it", (_occ(10, 16, "@Bob", user_id="ou_bob"),)
    )
    assert decision.refusal == SACHIMA_DELEGATE_UNVERIFIED_SELECTOR


def test_a_self_or_all_occurrence_never_selects_and_stays_in_the_task():
    text = "/delegate @all ship it"
    decision = parse_delegate_selection(
        text, (_occ(10, 14, "@all", user_id="", is_all=True),)
    )
    assert decision.refused is False
    assert decision.has_selector is False
    assert decision.task_text == "@all ship it"


def test_a_non_delegate_command_parses_to_nothing():
    assert parse_delegate_selection("/status", ()).task_text == ""


# --------------------------------------------------------------------------- #
# D. Policy + routing
# --------------------------------------------------------------------------- #
class _Config:
    """The five ARS ref maps a delegate policy must resolve against."""

    def __init__(self, **maps: Any):
        self.workspace_by_ref = maps.get("workspace", {"ws_main": "/tmp/ws"})
        self.agent_by_policy_ref = maps.get(
            "agent",
            {
                "policy_author": "author-agent",
                "policy_review": "review-agent",
                "policy_shared": "shared-agent",
            },
        )
        self.model_by_policy_ref = maps.get(
            "model", {"policy_model": "claude-opus-5", "policy_shared": "claude-opus-5"}
        )
        self.effort_by_policy_ref = maps.get(
            "effort", {"policy_effort": "xhigh", "policy_shared": "xhigh"}
        )
        self.run_limits_by_policy_ref = maps.get("limits", {"policy_limits": {}})


def _profile(profile_id, **overrides):
    entry = {
        "profile_id": profile_id,
        "workspace_ref": "ws_main",
        "agent_policy_ref": "policy_author",
        "model_policy_ref": "policy_model",
        "effort_policy_ref": "policy_effort",
        "run_limits_policy_ref": "policy_limits",
    }
    entry.update(overrides)
    return entry


def _policy(*profiles, config=None):
    return build_delegate_policy(
        {"type": DELEGATE_POLICY_TYPE, "profiles": list(profiles)},
        config or _Config(),
    )


def test_a_profile_collapses_repeated_refs_into_first_seen_order():
    policy = _policy(
        _profile(
            "author",
            agent_policy_ref="policy_shared",
            model_policy_ref="policy_shared",
            effort_policy_ref="policy_shared",
        )
    )
    (profile,) = policy.profiles
    assert profile.launch_refs == ("ws_main", "policy_shared", "policy_limits")


def test_an_unmapped_or_disabled_selector_refuses_even_with_an_auto_profile():
    """A3/A2: explicit selection never silently becomes the automatic profile."""

    policy = _policy(
        _profile("author", auto_selectable=True),
        _profile(
            "review",
            agent_policy_ref="policy_review",
            enabled=False,
            mentions=[{"platform": "feishu", "platform_user_id": "ou_review"}],
        ),
    )
    unmapped = resolve_route(
        policy, platform="feishu", selector_user_id="ou_nobody", task_text="do it"
    )
    assert unmapped.refusal == SACHIMA_DELEGATE_UNKNOWN_SELECTOR
    assert unmapped.routed is False

    disabled = resolve_route(
        policy, platform="feishu", selector_user_id="ou_review", task_text="do it"
    )
    assert disabled.refusal == SACHIMA_DELEGATE_UNKNOWN_SELECTOR
    assert disabled.routed is False
    # The refusal is worth reading: it names what IS available.
    assert "author" in " ".join(disabled.choices)


def test_a_verified_selector_wins_over_the_automatic_candidates():
    policy = _policy(
        _profile("author", priority=10),
        _profile(
            "review",
            agent_policy_ref="policy_review",
            auto_selectable=False,
            mentions=[{"platform": "feishu", "platform_user_id": "ou_review"}],
        ),
    )
    decision = resolve_route(
        policy, platform="feishu", selector_user_id="ou_review", task_text="do it"
    )
    assert decision.profile.profile_id == "review"


def test_the_platform_is_part_of_the_mention_identity():
    policy = _policy(
        _profile(
            "review",
            mentions=[{"platform": "feishu", "platform_user_id": "ou_review"}],
        )
    )
    assert (
        resolve_route(
            policy, platform="telegram", selector_user_id="ou_review", task_text="x"
        ).refusal
        == SACHIMA_DELEGATE_UNKNOWN_SELECTOR
    )


def test_a_trusted_profile_id_wins_or_refuses_and_never_falls_back():
    policy = _policy(_profile("author"))
    assert (
        resolve_route(policy, requested_profile_id="author", task_text="x")
        .profile.profile_id
        == "author"
    )
    missing = resolve_route(policy, requested_profile_id="ghost", task_text="x")
    assert missing.refusal == SACHIMA_DELEGATE_UNKNOWN_PROFILE
    assert missing.routed is False


def test_automatic_routing_filters_by_size_and_capability():
    policy = _policy(
        _profile("small", max_task_bytes=8, capabilities=["code"], priority=9),
        _profile("large", agent_policy_ref="policy_review", capabilities=["code"]),
    )
    small = resolve_route(policy, task_text="tiny", required_capabilities=("code",))
    assert small.profile.profile_id == "small"

    big = resolve_route(
        policy, task_text="x" * 64, required_capabilities=("code",)
    )
    assert big.profile.profile_id == "large"

    unmet = resolve_route(policy, task_text="tiny", required_capabilities=("deploy",))
    assert unmet.refusal == SACHIMA_DELEGATE_NO_ROUTE


def test_a_priority_tie_asks_for_clarification_instead_of_guessing():
    policy = _policy(
        _profile("author", priority=5),
        _profile("review", agent_policy_ref="policy_review", priority=5),
    )
    decision = resolve_route(policy, task_text="do it")
    assert decision.refusal == SACHIMA_DELEGATE_AMBIGUOUS_ROUTE
    assert decision.routed is False

    ranked = _policy(
        _profile("author", priority=9),
        _profile("review", agent_policy_ref="policy_review", priority=5),
    )
    assert resolve_route(ranked, task_text="do it").profile.profile_id == "author"


def test_an_explicit_profile_still_has_to_take_the_task():
    policy = _policy(_profile("author", max_task_bytes=4))
    decision = resolve_route(policy, requested_profile_id="author", task_text="x" * 16)
    assert decision.refusal == SACHIMA_DELEGATE_TASK_TOO_LARGE


def test_a_ref_outside_the_ars_config_fails_closed():
    with pytest.raises(PolicyError) as excinfo:
        _policy(_profile("author", workspace_ref="ws_not_configured"))
    assert str(excinfo.value) == SACHIMA_DELEGATE_INVALID_POLICY


def test_one_occurrence_may_not_map_to_two_agents():
    with pytest.raises(PolicyError):
        _policy(
            _profile(
                "author", mentions=[{"platform": "feishu", "platform_user_id": "ou_a"}]
            ),
            _profile(
                "review",
                agent_policy_ref="policy_review",
                mentions=[{"platform": "feishu", "platform_user_id": "ou_a"}],
            ),
        )


def test_the_requested_triple_comes_from_the_selected_profiles_refs():
    config = _Config()
    policy = _policy(_profile("review", agent_policy_ref="policy_review"), config=config)
    (profile,) = policy.profiles
    assert requested_configuration(config, profile) == (
        "review-agent",
        "claude-opus-5",
        "xhigh",
    )


def test_legacy_synthesis_reproduces_one_profile_and_refuses_a_choice():
    single = _Config(
        agent={"policy_author": "author-agent"},
        model={"policy_model": "claude-opus-5"},
        effort={"policy_effort": "xhigh"},
    )
    policy = synthesize_legacy_policy(single)
    (profile,) = policy.profiles
    assert profile.profile_id == "default"
    assert profile.mention_ids == ()
    # No mention mapping means an explicit selector refuses rather than becoming
    # the legacy profile by default.
    assert (
        resolve_route(
            policy, platform="feishu", selector_user_id="ou_alice", task_text="x"
        ).refusal
        == SACHIMA_DELEGATE_UNKNOWN_SELECTOR
    )
    assert resolve_route(policy, task_text="x").profile.profile_id == "default"

    with pytest.raises(PolicyError):
        synthesize_legacy_policy(_Config())
