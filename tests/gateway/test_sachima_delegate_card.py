"""S0-S2 — the delegation status-card projection: contracts, records, renderer.

Everything here is pure and local/offline: no adapter, socket, daemon, Gateway,
IM surface, or AGENT. What is proven:

* **S0 numeric contracts** are derived from existing source constants rather
  than guessed, and each mirrored input is drift-locked against the module it
  claims to mirror — the Feishu adapter's own transient-retry ladder, the
  coordinator's observation cadence and blindness budget, and the adapter's own
  one-message bound;
* **S1 durable projection** keeps ``task_created_at`` immutable, numbers rounds
  by the durable ``turn_key`` order, is idempotent under duplicate events,
  refuses a foreign origin, refuses a stale revision, binds at most one
  confirmed card message, and never stores raw prompts/results/card JSON;
* **S2 rendering** emits the four confirmed Session-reuse snapshots byte-for-
  byte, keeps the five-field order/punctuation/no-bullet layout in both
  locales, derives duration only from persisted boundaries, renders the exact
  honest fallbacks, bounds the payload before the adapter call, and keeps the
  compact Markdown fallback at parity with the native card.

Forbidden terms in this prose are no-leak boundary canaries only, never behavior.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from gateway.sachima_delegate_card import (
    CARD_ROUND_WINDOW,
    CARD_SINK_STATES,
    CARD_TEXT_BUDGET_CHARS,
    PRE_ACCEPT_STATES,
    ROUND_STATES,
    RUNNING_PATCH_INTERVAL_FLOOR_SECONDS,
    RUNNING_PATCH_INTERVAL_MAX_SECONDS,
    RUNNING_PATCH_INTERVAL_SECONDS,
    SACHIMA_DELEGATE_CARD_CONFLICT,
    SACHIMA_DELEGATE_CARD_INVALID,
    SESSION_PROJECTIONS,
    DelegateCardError,
    DelegateCardProjection,
    DelegateCardRound,
    advance_round,
    append_round,
    bind_card_message,
    bounded_card_payload,
    card_header_template,
    card_title,
    new_card_projection,
    normalize_running_patch_interval,
    project_session_evidence,
    projected_revision,
    render_delegation_card,
    render_delegation_markdown,
    sanitize_card_line,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
TASK_REF = "dtask_0f3c9a11b2c34d5e6f708192a3b4c5d6"
CREATED_AT = "2026-08-26T09:00:00+00:00"


def _projection(**overrides) -> DelegateCardProjection:
    base = dict(
        task_ref=TASK_REF,
        task_created_at=CREATED_AT,
        origin_platform="feishu",
        origin_chat_id="oc_chat",
        origin_session_id="sess_1",
        locale="zh",
        agent_id="oh-my-pi",
        model="glm-5.3",
        effort="max",
        task_description="验证 oh-my-pi 的 Session 复用",
    )
    base.update(overrides)
    return new_card_projection(**base)


def _lines(text: str) -> list[str]:
    return text.split("\n")


def _card_text(card: dict) -> str:
    """The whole card as one comparable block: header title, then its body.

    The native card carries the state title exactly once, in the header, so the
    markdown element holds everything below it. Recomposing the two here is what
    lets a snapshot assertion read like the card the user actually sees.
    """

    elements = card["elements"]
    assert len(elements) == 1, elements
    assert elements[0]["tag"] == "markdown"
    return card["header"]["title"]["content"] + "\n\n" + elements[0]["content"]


# --------------------------------------------------------------------------- #
# S0 — numeric contracts, derived and drift-locked
# --------------------------------------------------------------------------- #
def test_running_patch_interval_is_derived_from_source_constants():
    """Floor, default, and maximum come from arithmetic over real constants."""

    from gateway.platforms.feishu import _FEISHU_SEND_ATTEMPTS
    from gateway.sachima_delegate import (
        _DEFAULT_OBSERVE_INTERVAL_SECONDS,
        _MAX_CONSECUTIVE_OBSERVE_FAILURES,
    )

    # The floor is the adapter's own worst-case in-call transient backoff for
    # one patch: it sleeps 2**attempt between attempts, so a projection layer
    # that patched faster than this would open a second adapter call while the
    # first was still inside its own ladder.
    backoff_budget = float(sum(2**index for index in range(_FEISHU_SEND_ATTEMPTS - 1)))
    assert RUNNING_PATCH_INTERVAL_FLOOR_SECONDS == backoff_budget

    # The default is the smallest whole multiple of the observation cadence
    # that clears the floor: no new running evidence can exist sooner.
    assert RUNNING_PATCH_INTERVAL_SECONDS >= RUNNING_PATCH_INTERVAL_FLOOR_SECONDS
    assert RUNNING_PATCH_INTERVAL_SECONDS % _DEFAULT_OBSERVE_INTERVAL_SECONDS == 0
    assert (
        RUNNING_PATCH_INTERVAL_SECONDS - _DEFAULT_OBSERVE_INTERVAL_SECONDS
        < RUNNING_PATCH_INTERVAL_FLOOR_SECONDS
    )

    # The maximum is the point at which the coordinator itself admits it has
    # gone blind; a card cadence slower than that would keep claiming a state
    # Sachima no longer trusts.
    assert RUNNING_PATCH_INTERVAL_MAX_SECONDS == (
        _MAX_CONSECUTIVE_OBSERVE_FAILURES * _DEFAULT_OBSERVE_INTERVAL_SECONDS
    )
    assert RUNNING_PATCH_INTERVAL_MAX_SECONDS > RUNNING_PATCH_INTERVAL_SECONDS


@pytest.mark.parametrize(
    "value",
    [None, "4", True, float("nan"), float("inf"), -1.0, 0.0, 1.0, 999.0],
)
def test_invalid_running_patch_interval_normalizes_to_the_default(value):
    """An out-of-contract cadence is answered with the default, never accepted."""

    assert normalize_running_patch_interval(value) == RUNNING_PATCH_INTERVAL_SECONDS


def test_in_range_running_patch_interval_is_kept():
    assert normalize_running_patch_interval(RUNNING_PATCH_INTERVAL_FLOOR_SECONDS) == (
        RUNNING_PATCH_INTERVAL_FLOOR_SECONDS
    )
    assert normalize_running_patch_interval(RUNNING_PATCH_INTERVAL_MAX_SECONDS) == (
        RUNNING_PATCH_INTERVAL_MAX_SECONDS
    )


def test_round_window_is_the_product_display_bound():
    """Three rows, per the plan's first-slice display contract."""

    assert CARD_ROUND_WINDOW == 3


def test_the_visible_line_budget_is_the_existing_task_description_budget():
    """No new number: one reviewed budget already bounds delegation lines."""

    from gateway.sachima_delegate_summary import (
        SUMMARY_TASK_DESCRIPTION_BUDGET_CHARS,
        sanitize_task_description,
    )

    assert CARD_TEXT_BUDGET_CHARS == SUMMARY_TASK_DESCRIPTION_BUDGET_CHARS

    # Drift-locked by behaviour as well as by value: the longest description
    # the existing sanitizer can produce is never refused by the durable card
    # boundary, which is what makes these one budget rather than two that
    # happen to agree today.
    longest = sanitize_task_description("目" * (CARD_TEXT_BUDGET_CHARS + 50))
    assert len(longest) == CARD_TEXT_BUDGET_CHARS
    row = append_round(_projection(), turn_key="dturn_budget", purpose=longest).rounds[0]
    assert row.purpose == longest


def test_state_vocabularies_are_closed():
    assert CARD_SINK_STATES == ("pending", "confirmed", "failed", "uncertain")
    assert PRE_ACCEPT_STATES == ("created", "waiting", "submitting", "rejected", "omitted")
    assert SESSION_PROJECTIONS == ("new", "reused", "pending", "unconfirmed", "omitted")
    assert set(ROUND_STATES) == {
        "submitting",
        "rejected",
        "accepted",
        "running",
        "completed",
        "failed",
        "cancelled",
        "recovering",
    }


# --------------------------------------------------------------------------- #
# S1 — durable projection invariants
# --------------------------------------------------------------------------- #
def test_new_projection_seals_identity_and_starts_empty():
    projection = _projection()
    assert projection.task_ref == TASK_REF
    assert projection.task_created_at == CREATED_AT
    assert projection.revision == 0
    assert projection.card_message_id is None
    assert projection.card_sink_state == "pending"
    assert projection.pre_accept_status == "created"
    assert projection.rounds == ()
    assert projection.degraded_notice is False


def test_projection_roundtrips_through_its_document():
    projection = append_round(
        _projection(),
        turn_key="dturn_a1",
        purpose="建立 Session 上下文",
        admitted_role=None,
        started_at="2026-08-26T09:00:05+00:00",
    )
    restored = DelegateCardProjection.from_dict(projection.as_dict())
    assert restored == projection


def test_projection_refuses_unsafe_material():
    with pytest.raises(DelegateCardError) as excinfo:
        _projection(task_ref="not-a-ref")
    assert str(excinfo.value) == SACHIMA_DELEGATE_CARD_INVALID

    with pytest.raises(DelegateCardError):
        _projection(task_created_at="yesterday")

    with pytest.raises(DelegateCardError):
        _projection(locale="fr")


def test_task_created_at_is_immutable_across_the_task_life():
    projection = _projection()
    with pytest.raises(DelegateCardError) as excinfo:
        DelegateCardProjection.from_dict(
            {**projection.as_dict(), "task_created_at": ""}
        )
    assert str(excinfo.value) == SACHIMA_DELEGATE_CARD_INVALID


def test_rounds_are_numbered_by_durable_turn_order_and_are_append_only():
    projection = _projection()
    projection = append_round(projection, turn_key="dturn_a1", purpose="第一步")
    projection = append_round(projection, turn_key="dturn_b2", purpose="第二步")
    assert [row.round_number for row in projection.rounds] == [1, 2]
    assert [row.turn_key for row in projection.rounds] == ["dturn_a1", "dturn_b2"]


def test_duplicate_round_append_is_idempotent():
    """A replayed accepted/terminal event updates its row; it never appends."""

    projection = _projection()
    projection = append_round(projection, turn_key="dturn_a1", purpose="第一步")
    again = append_round(projection, turn_key="dturn_a1", purpose="第一步")
    assert again.rounds == projection.rounds

    # A duplicate carrying a *different* purpose does not silently rewrite the
    # persisted one either: the purpose is sealed at turn creation.
    third = append_round(projection, turn_key="dturn_a1", purpose="改写")
    assert third.rounds[0].purpose == "第一步"


def test_settled_prior_rounds_survive_a_continuation():
    projection = _projection()
    projection = append_round(projection, turn_key="dturn_a1", purpose="第一步")
    projection = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        settled_at="2026-08-26T09:01:00+00:00",
        result_summary="上下文已建立",
    )
    projection = append_round(projection, turn_key="dturn_b2", purpose="第二步")
    projection = advance_round(projection, "dturn_b2", status="running")
    assert projection.rounds[0].status == "completed"
    assert projection.rounds[0].result_summary == "上下文已建立"
    assert projection.rounds[1].status == "running"


def test_a_failed_round_does_not_erase_a_successful_prior_round():
    projection = _projection()
    projection = append_round(projection, turn_key="dturn_a1")
    projection = advance_round(projection, "dturn_a1", status="completed")
    projection = append_round(projection, turn_key="dturn_b2")
    projection = advance_round(projection, "dturn_b2", status="failed")
    assert [row.status for row in projection.rounds] == ["completed", "failed"]


def test_advance_round_refuses_an_unknown_turn():
    with pytest.raises(DelegateCardError) as excinfo:
        advance_round(_projection(), "dturn_missing", status="running")
    assert str(excinfo.value) == SACHIMA_DELEGATE_CARD_CONFLICT


def test_revision_is_monotonic_and_a_stale_projection_is_refused():
    projection = _projection()
    first = projected_revision(projection, at="2026-08-26T09:00:10+00:00")
    assert first.revision == 1
    second = projected_revision(first, at="2026-08-26T09:00:20+00:00")
    assert second.revision == 2
    assert second.last_projected_at == "2026-08-26T09:00:20+00:00"

    with pytest.raises(DelegateCardError) as excinfo:
        # An older retry trying to re-stamp a newer revision.
        projected_revision(second, at="2026-08-26T09:00:15+00:00", revision=1)
    assert str(excinfo.value) == SACHIMA_DELEGATE_CARD_CONFLICT


def test_one_confirmed_card_binding_per_task():
    projection = _projection()
    bound = bind_card_message(
        projection, message_id="om_1", revision=1, at="2026-08-26T09:00:10+00:00"
    )
    assert bound.card_message_id == "om_1"
    assert bound.card_sink_state == "confirmed"
    # The identical binding replays.
    assert bind_card_message(
        bound, message_id="om_1", revision=1, at="2026-08-26T09:00:10+00:00"
    ).card_message_id == "om_1"
    # A second, different message can never become this task's card.
    with pytest.raises(DelegateCardError) as excinfo:
        bind_card_message(
            bound, message_id="om_2", revision=2, at="2026-08-26T09:00:20+00:00"
        )
    assert str(excinfo.value) == SACHIMA_DELEGATE_CARD_CONFLICT


def test_projection_origin_is_sealed():
    projection = _projection()
    assert projection.owns_origin(platform="feishu", chat_id="oc_chat", session_id="sess_1")
    assert not projection.owns_origin(
        platform="feishu", chat_id="oc_other", session_id="sess_1"
    )
    assert not projection.owns_origin(
        platform="telegram", chat_id="oc_chat", session_id="sess_1"
    )
    assert not projection.owns_origin(
        platform="feishu", chat_id="oc_chat", session_id="sess_2"
    )


def test_private_origin_material_is_repr_excluded_and_never_rendered():
    projection = bind_card_message(
        _projection(), message_id="om_secret", revision=1, at=CREATED_AT
    )
    text = repr(projection)
    assert "oc_chat" not in text
    assert "om_secret" not in text
    card = render_delegation_card(projection)
    serialized = json.dumps(card, ensure_ascii=False)
    assert "oc_chat" not in serialized
    assert "om_secret" not in serialized


def test_card_line_sanitization_drops_control_characters_and_bounds_length():
    assert sanitize_card_line("a\x00b\nc") == "ab c"
    assert sanitize_card_line("   ") is None
    assert sanitize_card_line(None) is None
    assert len(sanitize_card_line("x" * 5000)) <= 200


def test_projection_refuses_internal_refs_in_visible_material():
    """A round's visible text can never carry an internal identity."""

    with pytest.raises(DelegateCardError):
        append_round(_projection(), turn_key="dturn_a1", purpose="dres_deadbeef")
    with pytest.raises(DelegateCardError):
        advance_round(
            append_round(_projection(), turn_key="dturn_a1"),
            "dturn_a1",
            status="completed",
            result_summary="run_1234abcd finished",
        )


# --------------------------------------------------------------------------- #
# S1 — Session-reuse evidence
#
# Reuse is a claim about one Task's whole history, so the evidence is that
# Task's ordered rounds rather than whichever row happens to be immediately
# behind: the row behind a second continuation is itself a load, and two loads
# with nothing that created the Session prove only that this host was told
# "loaded" twice.
# --------------------------------------------------------------------------- #
#: "let the helper derive this round's own Run identity", which ``None`` cannot
#: mean here — a round that recorded no Run at all is its own evidence case.
_DERIVED = object()


def _round(
    number: int,
    *,
    status: str = "completed",
    session_ref: str | None = "sess_ref_a",
    run_ref: Any = _DERIVED,
    session_origin: str | None = None,
) -> DelegateCardRound:
    """One earlier round of this Task, as the durable record holds it."""

    return DelegateCardRound(
        turn_key=f"dturn_r{number}",
        round_number=number,
        status=status,
        session_ref=session_ref,
        run_ref=f"run_{number}" if run_ref is _DERIVED else run_ref,
        session_origin=session_origin,
    )


def test_session_reuse_needs_a_settled_created_anchor_in_the_same_task():
    """``created``(settled) → ``loaded``(settled): the whole evidence set."""

    assert (
        project_session_evidence(
            earlier_rounds=(_round(1, session_origin="created"),),
            session_ref="sess_ref_a",
            run_ref="run_2",
            session_origin="loaded",
        )
        == "reused"
    )


def test_the_created_anchor_is_traced_past_an_intervening_loaded_round():
    """``created → loaded → loaded``: both loads confirm against round one."""

    created = _round(1, session_origin="created")
    loaded = _round(2, session_origin="loaded")
    assert (
        project_session_evidence(
            earlier_rounds=(created,),
            session_ref="sess_ref_a",
            run_ref="run_2",
            session_origin="loaded",
        )
        == "reused"
    )
    # The row immediately behind this one is a *load*. Requiring the previous
    # row to be the create would silently unconfirm every round after the second
    # one, and reading only that row is what let a pair of loads claim reuse.
    assert (
        project_session_evidence(
            earlier_rounds=(created, loaded),
            session_ref="sess_ref_a",
            run_ref="run_3",
            session_origin="loaded",
        )
        == "reused"
    )


def test_two_loaded_rounds_alone_can_never_confirm_a_reuse():
    """No round of this Task recorded a create, so nothing anchors the claim."""

    assert (
        project_session_evidence(
            earlier_rounds=(_round(1, session_origin="loaded"),),
            session_ref="sess_ref_a",
            run_ref="run_2",
            session_origin="loaded",
        )
        == "unconfirmed"
    )


def test_an_unsettled_created_anchor_confirms_nothing():
    """``created``(running) → ``loaded``(settled): the anchor never ended.

    A create still in flight has not proven a Session exists to be reused, so
    the round that claims to have loaded it has nothing to be measured against.
    """

    assert (
        project_session_evidence(
            earlier_rounds=(_round(1, status="running", session_origin="created"),),
            session_ref="sess_ref_a",
            run_ref="run_2",
            session_origin="loaded",
        )
        == "unconfirmed"
    )


def test_the_first_round_projects_a_new_session():
    assert (
        project_session_evidence(
            earlier_rounds=(),
            session_ref="sess_ref_a",
            run_ref="run_1",
            session_origin="created",
        )
        == "new"
    )


def test_a_created_round_still_shows_new_while_it_is_running():
    """The confirmed first-round visual: a trusted create says so immediately."""

    assert (
        project_session_evidence(
            earlier_rounds=(),
            session_ref="sess_ref_a",
            run_ref="run_1",
            session_origin="created",
            settled=False,
        )
        == "new"
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        # Same Run identity — one Run cannot prove reuse across two rounds.
        dict(
            earlier_rounds=(_round(1, session_origin="created"),),
            session_ref="sess_ref_a",
            run_ref="run_1",
            session_origin="loaded",
        ),
        # Different ARS Session — not a reuse at all.
        dict(
            earlier_rounds=(_round(1, session_origin="created"),),
            session_ref="sess_ref_b",
            run_ref="run_2",
            session_origin="loaded",
        ),
        # No create-then-load evidence on this round.
        dict(
            earlier_rounds=(_round(1, session_origin="created"),),
            session_ref="sess_ref_a",
            run_ref="run_2",
            session_origin=None,
        ),
        # Missing continuation Session identity.
        dict(
            earlier_rounds=(_round(1, session_origin="created"),),
            session_ref=None,
            run_ref="run_2",
            session_origin="loaded",
        ),
        # An anchor that recorded no Run identity of its own.
        dict(
            earlier_rounds=(_round(1, run_ref=None, session_origin="created"),),
            session_ref="sess_ref_a",
            run_ref="run_2",
            session_origin="loaded",
        ),
        # An anchor whose create was on another Session.
        dict(
            earlier_rounds=(_round(1, session_ref="sess_ref_b", session_origin="created"),),
            session_ref="sess_ref_a",
            run_ref="run_2",
            session_origin="loaded",
        ),
        # A Task with no earlier round at all.
        dict(
            earlier_rounds=(),
            session_ref="sess_ref_a",
            run_ref="run_2",
            session_origin="loaded",
        ),
    ],
)
def test_incomplete_evidence_never_claims_reuse(kwargs):
    assert project_session_evidence(**kwargs) == "unconfirmed"


def test_an_unsettled_continuation_projects_reuse_as_pending():
    """``created``(settled) → ``loaded``(running): confirmation is in progress."""

    assert (
        project_session_evidence(
            earlier_rounds=(_round(1, session_origin="created"),),
            session_ref="sess_ref_a",
            run_ref="run_2",
            session_origin="loaded",
            settled=False,
        )
        == "pending"
    )
    # Including the round that has not recorded its own Run identity yet.
    assert (
        project_session_evidence(
            earlier_rounds=(_round(1, session_origin="created"),),
            session_ref=None,
            run_ref=None,
            session_origin=None,
            settled=False,
        )
        == "pending"
    )


# --------------------------------------------------------------------------- #
# S2 — titles, header templates, and the fixed five-field summary
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "state,round_number,zh,en",
    [
        ("created", None, "委派任务 · 已创建", "Delegated Task · Created"),
        (
            "waiting",
            None,
            "委派任务 · 等待执行槽位",
            "Delegated Task · Waiting for Execution Slot",
        ),
        ("submitting", 1, "委派任务 · 第 1 轮提交中", "Delegated Task · Round 1 Submitting"),
        ("rejected", 1, "委派任务 · 第 1 轮未受理", "Delegated Task · Round 1 Not Admitted"),
        ("accepted", 2, "委派任务 · 第 2 轮已受理", "Delegated Task · Round 2 Admitted"),
        ("running", 2, "委派任务 · 第 2 轮执行中", "Delegated Task · Round 2 Running"),
        ("completed", 2, "委派任务 · 第 2 轮已完成", "Delegated Task · Round 2 Completed"),
        ("failed", 2, "委派任务 · 第 2 轮已失败", "Delegated Task · Round 2 Failed"),
        ("cancelled", 2, "委派任务 · 第 2 轮已取消", "Delegated Task · Round 2 Cancelled"),
        (
            "recovering",
            2,
            "委派任务 · 第 2 轮状态待恢复",
            "Delegated Task · Round 2 Recovery Pending",
        ),
    ],
)
def test_every_required_title_state_renders_in_both_locales(state, round_number, zh, en):
    assert card_title(state, round_number, locale="zh") == zh
    assert card_title(state, round_number, locale="en") == en


def test_the_three_confirmed_header_templates_are_stable():
    assert card_header_template("created") == "blue"
    assert card_header_template("running") == "yellow"
    assert card_header_template("completed") == "green"


def test_every_state_maps_to_a_template_the_adapter_already_uses():
    used_by_adapter = {"blue", "green", "orange", "red", "yellow"}
    for state in ("created", "waiting", *ROUND_STATES):
        assert card_header_template(state) in used_by_adapter


def test_chinese_summary_keeps_the_fixed_order_punctuation_and_no_bullets():
    projection = _projection()
    body = _card_text(render_delegation_card(projection))
    lines = _lines(body)
    assert lines[0] == "委派任务 · 已创建"
    assert lines[1] == ""
    assert lines[2] == "💡 任务： 验证 oh-my-pi 的 Session 复用"
    assert lines[3] == f"🆔 编号： {TASK_REF}"
    assert lines[4] == "⏱️ 耗时： 0秒"
    assert lines[5] == "🤖 执行： oh-my-pi · glm-5.3 · max"
    assert lines[6] == "👤 角色： 未指定"
    # No bullets anywhere, and no blank line between the five field rows.
    for line in lines[2:7]:
        assert not line.startswith("-")
        assert not line.startswith("•")
        assert line.strip()


def test_english_summary_uses_ascii_colons_and_english_labels():
    projection = _projection(locale="en", task_description="Verify oh-my-pi session reuse")
    lines = _lines(_card_text(render_delegation_card(projection)))
    assert lines[0] == "Delegated Task · Created"
    assert lines[2] == "💡 Task: Verify oh-my-pi session reuse"
    assert lines[3] == f"🆔 ID: {TASK_REF}"
    assert lines[4] == "⏱️ Duration: 0s"
    assert lines[5] == "🤖 Execution: oh-my-pi · glm-5.3 · max"
    assert lines[6] == "👤 Role: Not specified"


def test_one_card_never_mixes_locales():
    for locale, foreign in (("zh", ("Task:", "Duration:")), ("en", ("任务：", "耗时："))):
        body = _card_text(render_delegation_card(_projection(locale=locale)))
        for token in foreign:
            assert token not in body


def test_the_full_task_id_is_shown_and_never_shortened():
    body = _card_text(render_delegation_card(_projection()))
    assert TASK_REF in body
    assert "…" not in body
    assert "..." not in body


def test_effort_is_omitted_rather_than_left_dangling():
    body = _card_text(render_delegation_card(_projection(effort="")))
    assert "🤖 执行： oh-my-pi · glm-5.3" in body
    assert "glm-5.3 ·" not in body


def test_canonical_agent_id_is_shown_and_omp_is_never_generated():
    body = _card_text(render_delegation_card(_projection()))
    assert "oh-my-pi" in body
    assert " omp " not in body
    assert "： omp" not in body


def test_admitted_role_is_rendered_from_the_sealed_execution_contract():
    projection = append_round(
        _projection(), turn_key="dturn_a1", admitted_role="session_reuse_verifier"
    )
    body = _card_text(render_delegation_card(projection))
    assert "👤 角色： session_reuse_verifier" in body


def test_absent_role_renders_the_exact_honest_fallback():
    zh = _card_text(render_delegation_card(_projection()))
    assert "👤 角色： 未指定" in zh
    en = _card_text(render_delegation_card(_projection(locale="en")))
    assert "👤 Role: Not specified" in en


def test_missing_task_description_renders_an_honest_unavailable_value():
    zh = _card_text(render_delegation_card(_projection(task_description=None)))
    assert "💡 任务： 未提供" in zh
    en = _card_text(
        render_delegation_card(_projection(locale="en", task_description=None))
    )
    assert "💡 Task: Not provided" in en


# --------------------------------------------------------------------------- #
# S2 — duration from persisted lifecycle boundaries only
# --------------------------------------------------------------------------- #
def test_running_duration_uses_the_persisted_projection_instant():
    projection = projected_revision(
        append_round(_projection(), turn_key="dturn_a1"),
        at="2026-08-26T09:01:30+00:00",
    )
    projection = advance_round(projection, "dturn_a1", status="running")
    assert "⏱️ 耗时： 1分30秒" in _card_text(render_delegation_card(projection))


def test_terminal_duration_is_fixed_at_the_settlement_instant():
    projection = append_round(_projection(), turn_key="dturn_a1")
    projection = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        settled_at="2026-08-26T09:00:45+00:00",
    )
    # A later projection stamp does not move a settled terminal's duration.
    projection = projected_revision(projection, at="2026-08-26T09:30:00+00:00")
    assert "⏱️ 耗时： 45秒" in _card_text(render_delegation_card(projection))


def test_a_continuation_resumes_the_same_task_duration():
    projection = append_round(_projection(), turn_key="dturn_a1")
    projection = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        settled_at="2026-08-26T09:00:45+00:00",
    )
    projection = append_round(projection, turn_key="dturn_b2")
    projection = projected_revision(projection, at="2026-08-26T10:00:00+00:00")
    projection = advance_round(projection, "dturn_b2", status="running")
    # One hour of Task life, not 45 seconds and not a fresh zero.
    assert "⏱️ 耗时： 1小时0分0秒" in _card_text(render_delegation_card(projection))


def test_a_missing_boundary_renders_an_honest_unavailable_duration():
    projection = append_round(_projection(), turn_key="dturn_a1")
    projection = advance_round(projection, "dturn_a1", status="running")
    # Nothing has been projected yet, so there is no persisted end boundary.
    assert "⏱️ 耗时： 未知" in _card_text(render_delegation_card(projection))
    english = append_round(_projection(locale="en"), turn_key="dturn_a1")
    english = advance_round(english, "dturn_a1", status="running")
    assert "⏱️ Duration: Unknown" in _card_text(render_delegation_card(english))


def test_a_negative_interval_is_unavailable_rather_than_invented():
    projection = append_round(_projection(), turn_key="dturn_a1")
    projection = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        settled_at="2026-08-26T08:00:00+00:00",
    )
    assert "⏱️ 耗时： 未知" in _card_text(render_delegation_card(projection))


# --------------------------------------------------------------------------- #
# S2 — the four confirmed Session-reuse snapshots
# --------------------------------------------------------------------------- #
def _snapshot_projection() -> DelegateCardProjection:
    return _projection()


def test_snapshot_1_created():
    projection = _snapshot_projection()
    assert _card_text(render_delegation_card(projection)) == (
        "委派任务 · 已创建\n"
        "\n"
        "💡 任务： 验证 oh-my-pi 的 Session 复用\n"
        f"🆔 编号： {TASK_REF}\n"
        "⏱️ 耗时： 0秒\n"
        "🤖 执行： oh-my-pi · glm-5.3 · max\n"
        "👤 角色： 未指定\n"
        "\n"
        "执行记录\n"
        "⏳ 尚未开始"
    )


def test_snapshot_2_round_1_running():
    projection = append_round(
        _snapshot_projection(), turn_key="dturn_a1", purpose="建立 Session 上下文"
    )
    projection = projected_revision(projection, at="2026-08-26T09:00:20+00:00")
    projection = advance_round(
        projection, "dturn_a1", status="running", session_projection="new"
    )
    assert _card_text(render_delegation_card(projection)) == (
        "委派任务 · 第 1 轮执行中\n"
        "\n"
        "💡 任务： 验证 oh-my-pi 的 Session 复用\n"
        f"🆔 编号： {TASK_REF}\n"
        "⏱️ 耗时： 20秒\n"
        "🤖 执行： oh-my-pi · glm-5.3 · max\n"
        "👤 角色： 未指定\n"
        "\n"
        "执行记录\n"
        "▶️ 第 1 轮：建立 Session 上下文\n"
        "Session：新建\n"
        "状态：执行中"
    )


def _two_round_projection() -> DelegateCardProjection:
    projection = append_round(
        _snapshot_projection(), turn_key="dturn_a1", purpose="建立 Session 上下文"
    )
    projection = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        session_projection="new",
        result_summary="上下文已建立",
        settled_at="2026-08-26T09:00:40+00:00",
    )
    return append_round(projection, turn_key="dturn_b2", purpose="验证 Session 上下文复用")


def test_snapshot_3_round_2_running():
    projection = _two_round_projection()
    projection = projected_revision(projection, at="2026-08-26T09:01:00+00:00")
    projection = advance_round(
        projection, "dturn_b2", status="running", session_projection="pending"
    )
    assert _card_text(render_delegation_card(projection)) == (
        "委派任务 · 第 2 轮执行中\n"
        "\n"
        "💡 任务： 验证 oh-my-pi 的 Session 复用\n"
        f"🆔 编号： {TASK_REF}\n"
        "⏱️ 耗时： 1分0秒\n"
        "🤖 执行： oh-my-pi · glm-5.3 · max\n"
        "👤 角色： 未指定\n"
        "\n"
        "执行记录\n"
        "✅ 第 1 轮：建立 Session 上下文\n"
        "Session：新建\n"
        "结果：上下文已建立\n"
        "\n"
        "▶️ 第 2 轮：验证 Session 上下文复用\n"
        "Session：复用状态确认中\n"
        "状态：执行中"
    )


def test_snapshot_4_round_2_completed():
    projection = _two_round_projection()
    projection = advance_round(
        projection,
        "dturn_b2",
        status="completed",
        session_projection="reused",
        result_summary="上下文验证通过",
        settled_at="2026-08-26T09:01:20+00:00",
    )
    assert _card_text(render_delegation_card(projection)) == (
        "委派任务 · 第 2 轮已完成\n"
        "\n"
        "💡 任务： 验证 oh-my-pi 的 Session 复用\n"
        f"🆔 编号： {TASK_REF}\n"
        "⏱️ 耗时： 1分20秒\n"
        "🤖 执行： oh-my-pi · glm-5.3 · max\n"
        "👤 角色： 未指定\n"
        "\n"
        "执行记录\n"
        "✅ 第 1 轮：建立 Session 上下文\n"
        "Session：新建\n"
        "结果：上下文已建立\n"
        "\n"
        "✅ 第 2 轮：验证 Session 上下文复用\n"
        "Session：已确认复用\n"
        "结果：上下文验证通过"
    )


def test_unconfirmed_reuse_says_so_rather_than_claiming_it():
    projection = _two_round_projection()
    projection = advance_round(
        projection,
        "dturn_b2",
        status="completed",
        session_projection="unconfirmed",
        settled_at="2026-08-26T09:01:20+00:00",
    )
    body = _card_text(render_delegation_card(projection))
    assert "Session：复用状态未确认" in body
    assert "已确认复用" not in body.split("第 2 轮")[1]


def test_an_omitted_session_projection_drops_the_line_entirely():
    projection = append_round(_projection(), turn_key="dturn_a1", purpose="第一步")
    projection = advance_round(
        projection, "dturn_a1", status="running", session_projection="omitted"
    )
    body = _card_text(render_delegation_card(projection))
    assert "Session：" not in body


def test_english_round_history_is_fully_localized():
    projection = append_round(
        _projection(locale="en", task_description="Verify session reuse"),
        turn_key="dturn_a1",
        purpose="Establish session context",
    )
    projection = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        session_projection="new",
        result_summary="Context established",
        settled_at="2026-08-26T09:00:40+00:00",
    )
    body = _card_text(render_delegation_card(projection))
    assert "Execution Log" in body
    assert "✅ Round 1: Establish session context" in body
    assert "Session: New" in body
    assert "Result: Context established" in body
    assert "执行记录" not in body


# --------------------------------------------------------------------------- #
# S2 — bounded history
# --------------------------------------------------------------------------- #
def test_only_the_latest_three_rounds_render_plus_an_overflow_line():
    projection = _projection()
    for index in range(5):
        projection = append_round(
            projection, turn_key=f"dturn_r{index}", purpose=f"第 {index + 1} 步"
        )
        projection = advance_round(
            projection,
            f"dturn_r{index}",
            status="completed",
            settled_at="2026-08-26T09:00:40+00:00",
        )
    body = _card_text(render_delegation_card(projection))
    assert "第 1 轮" not in body
    assert "第 2 轮" not in body
    for number in (3, 4, 5):
        assert f"第 {number} 轮" in body
    assert "另有 2 轮" in body


def test_overflow_line_is_localized():
    projection = _projection(locale="en")
    for index in range(4):
        projection = append_round(projection, turn_key=f"dturn_r{index}")
        projection = advance_round(projection, f"dturn_r{index}", status="completed")
    body = _card_text(render_delegation_card(projection))
    assert "1 more round" in body


# --------------------------------------------------------------------------- #
# S2 — native schema validity, redaction, and the Markdown fallback
# --------------------------------------------------------------------------- #
def test_native_card_schema_matches_the_adapter_contract():
    card = render_delegation_card(_projection())
    assert set(card) == {"config", "header", "elements"}
    assert card["config"] == {"wide_screen_mode": True}
    assert card["header"]["template"] == "blue"
    assert card["header"]["title"]["tag"] == "plain_text"
    assert card["header"]["title"]["content"] == "委派任务 · 已创建"
    assert card["elements"][0]["tag"] == "markdown"
    # Read-only: the first slice adds no action element at all.
    assert all(element["tag"] != "action" for element in card["elements"])
    json.dumps(card, ensure_ascii=False)


def test_the_card_never_exposes_internal_identities():
    projection = _two_round_projection()
    projection = bind_card_message(
        projection, message_id="om_secret", revision=1, at=CREATED_AT
    )
    serialized = json.dumps(render_delegation_card(projection), ensure_ascii=False)
    for forbidden in ("dturn_", "dres_", "dlg_", "run_", "om_secret", "oc_chat", "sess_1"):
        assert forbidden not in serialized


def test_markdown_fallback_is_at_parity_with_the_native_card():
    projection = _two_round_projection()
    projection = advance_round(
        projection,
        "dturn_b2",
        status="completed",
        session_projection="reused",
        result_summary="上下文验证通过",
        settled_at="2026-08-26T09:01:20+00:00",
    )
    card_body = _card_text(render_delegation_card(projection))
    markdown = render_delegation_markdown(projection)
    # Same wording, order, punctuation, duration semantics, and layout — the
    # fallback is the card's own text, not a second rendering of it.
    assert markdown == card_body
    assert render_delegation_card(projection)["header"]["title"]["content"] not in (
        render_delegation_card(projection)["elements"][0]["content"]
    )
    for line in _lines(markdown):
        assert not line.startswith("- ")
        assert not line.startswith("* ")


def test_payload_is_bounded_before_the_adapter_call():
    """Compact first, then fail closed — never rely on API rejection."""

    projection = _projection()
    for index in range(3):
        projection = append_round(
            projection,
            turn_key=f"dturn_r{index}",
            purpose="很长的一段轮次目标描述" * 12,
        )
        projection = advance_round(
            projection,
            f"dturn_r{index}",
            status="completed",
            result_summary="很长的一段结果摘要" * 12,
            settled_at="2026-08-26T09:00:40+00:00",
        )

    full, _ = bounded_card_payload(projection, limit=100_000)
    assert full is not None
    assert full["elements"][0]["content"].count("轮：") == 3

    # A limit that only the compacted card fits keeps the card and drops rows.
    compacted, markdown = bounded_card_payload(projection, limit=900)
    assert compacted is not None
    assert compacted["elements"][0]["content"].count("轮：") < 3
    assert len(json.dumps(compacted, ensure_ascii=False)) <= 900
    assert markdown

    # A limit nothing fits fails closed to the Markdown fallback.
    refused, fallback = bounded_card_payload(projection, limit=120)
    assert refused is None
    assert TASK_REF in fallback


def test_bounded_payload_measures_the_serialized_content_the_adapter_sends():
    projection = _projection()
    card, _ = bounded_card_payload(projection, limit=100_000)
    measured: list[str] = []

    def _measure(text: str) -> int:
        measured.append(text)
        return len(text)

    bounded_card_payload(projection, limit=100_000, measure=_measure)
    assert measured
    assert measured[0] == json.dumps(card, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# S0 — the payload bound, drift-locked against the adapter that enforces it
# --------------------------------------------------------------------------- #
def test_the_payload_bound_is_the_adapters_own_one_message_limit():
    """No guessed constant: the bound is what the delivery already reads."""

    from gateway.platforms.feishu import FeishuAdapter

    limit = int(FeishuAdapter.MAX_MESSAGE_LENGTH)
    # ``single_message_text_limit()`` is the platform-neutral accessor the
    # delegate delivery passes to this module, so the two must agree.
    assert FeishuAdapter.single_message_text_limit(FeishuAdapter) == limit

    # A realistic three-round card fits inside it with room to spare, which is
    # why no verified Feishu constraint requires lowering the round window.
    projection = _projection()
    for index in range(CARD_ROUND_WINDOW):
        projection = append_round(
            projection,
            turn_key=f"dturn_full{index}",
            purpose="x" * 200,
        )
        projection = advance_round(
            projection,
            f"dturn_full{index}",
            status="completed",
            result_summary="y" * 200,
            settled_at="2026-08-26T09:00:40+00:00",
        )
    card, _fallback = bounded_card_payload(projection, limit=limit)
    assert card is not None
    assert card["elements"][0]["content"].count("轮：") == CARD_ROUND_WINDOW


def test_the_projection_layer_makes_one_adapter_call_per_revision():
    """The adapter owns transport retry; this module owns exactly one payload."""

    from gateway.platforms.feishu import _FEISHU_SEND_ATTEMPTS

    # The floor exists so a coalescing window never opens a second adapter call
    # while the first is still inside that ladder.
    assert _FEISHU_SEND_ATTEMPTS >= 2
    assert RUNNING_PATCH_INTERVAL_FLOOR_SECONDS >= float(
        2 ** (_FEISHU_SEND_ATTEMPTS - 2)
    )


# --------------------------------------------------------------------------- #
# S1 — a settled round is sealed
#
# "Independently terminal" is a claim about the *record*, not only about the
# header word: once a round settled, the instant its duration stopped at and the
# conclusion it was settled with are what the user was shown, and a later event
# may only fill in evidence that was still missing.
# --------------------------------------------------------------------------- #
def test_a_settled_round_freezes_the_instant_its_duration_stopped_at():
    projection = append_round(_projection(), turn_key="dturn_a1")
    projection = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        settled_at="2026-08-26T09:00:45+00:00",
        result_summary="上下文已建立",
    )
    frozen = _card_text(render_delegation_card(projection))
    assert "⏱️ 耗时： 45秒" in frozen

    # A later replay of the same terminal carries a new clock reading. Honouring
    # it would restart a duration this Task already finished measuring.
    replayed = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        settled_at="2026-08-26T09:30:00+00:00",
        result_summary="改写后的结论",
    )
    assert replayed.rounds[0].settled_at == "2026-08-26T09:00:45+00:00"
    assert replayed.rounds[0].result_summary == "上下文已建立"
    assert _card_text(render_delegation_card(replayed)) == frozen


def test_a_settled_round_still_accepts_evidence_it_was_missing():
    """Sealed is not opaque: what was never recorded can still be recorded."""

    projection = append_round(_projection(), turn_key="dturn_a1")
    projection = advance_round(
        projection, "dturn_a1", status="completed", settled_at="2026-08-26T09:00:45+00:00"
    )
    filled = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        result_summary="上下文已建立",
        session_projection="new",
    )
    assert filled.rounds[0].result_summary == "上下文已建立"
    assert filled.rounds[0].session_projection == "new"
    assert filled.rounds[0].settled_at == "2026-08-26T09:00:45+00:00"


# --------------------------------------------------------------------------- #
# S2 — the role and the start boundary are read, never guessed
# --------------------------------------------------------------------------- #
def test_the_role_line_is_the_latest_round_and_never_an_earlier_one():
    """A role belongs to the round it was admitted under, not to the Task."""

    projection = append_round(
        _projection(), turn_key="dturn_a1", admitted_role="session_reuse_verifier"
    )
    projection = advance_round(
        projection, "dturn_a1", status="completed", settled_at="2026-08-26T09:00:45+00:00"
    )
    assert "👤 角色： session_reuse_verifier" in _card_text(
        render_delegation_card(projection)
    )

    # The continuation was admitted by direct AGENT selection, so this card must
    # say so rather than re-showing a role the current round does not hold.
    projection = append_round(projection, turn_key="dturn_b2")
    assert "👤 角色： 未指定" in _card_text(render_delegation_card(projection))


def test_a_task_with_no_trustworthy_start_renders_an_unavailable_duration():
    """A missing start boundary is a missing boundary, never a fresh clock."""

    projection = _projection(task_created_at=None)
    assert projection.task_created_at is None
    assert "⏱️ 耗时： 未知" in _card_text(render_delegation_card(projection))

    projection = append_round(projection, turn_key="dturn_a1")
    projection = projected_revision(projection, at="2026-08-26T10:00:00+00:00")
    projection = advance_round(projection, "dturn_a1", status="running")
    assert "⏱️ 耗时： 未知" in _card_text(render_delegation_card(projection))
    english = _projection(locale="en", task_created_at=None)
    assert "⏱️ Duration: Unknown" in _card_text(render_delegation_card(english))


def test_an_unavailable_task_start_survives_a_reload_as_unavailable():
    """A terminal elapsed value is frozen, and a restart re-reads the same one."""

    unavailable = append_round(
        _projection(task_created_at=None), turn_key="dturn_a1"
    )
    unavailable = advance_round(
        unavailable,
        "dturn_a1",
        status="completed",
        settled_at="2026-08-26T09:00:45+00:00",
    )
    # A later projection stamp moves neither a settled terminal nor an absence.
    unavailable = projected_revision(unavailable, at="2026-08-26T09:30:00+00:00")
    frozen = _card_text(render_delegation_card(unavailable))
    assert "⏱️ 耗时： 未知" in frozen

    reloaded = DelegateCardProjection.from_dict(unavailable.as_dict())
    assert reloaded.task_created_at is None
    assert _card_text(render_delegation_card(reloaded)) == frozen

    # Positive control: a Task whose start really is persisted keeps its frozen
    # numeric elapsed value across the same reload.
    trusted = append_round(_projection(), turn_key="dturn_a1")
    trusted = advance_round(
        trusted,
        "dturn_a1",
        status="completed",
        settled_at="2026-08-26T09:00:45+00:00",
    )
    trusted = projected_revision(trusted, at="2026-08-26T09:30:00+00:00")
    assert "⏱️ 耗时： 45秒" in _card_text(render_delegation_card(trusted))
    assert "⏱️ 耗时： 45秒" in _card_text(
        render_delegation_card(DelegateCardProjection.from_dict(trusted.as_dict()))
    )
