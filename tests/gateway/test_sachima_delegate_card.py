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

    The native card carries the state title exactly once, in the header, and
    splits what follows into the Task's fixed fields and its execution log —
    two markdown blocks with the platform's own divider element between them.
    Recomposing the three here, writing that divider the way the Markdown
    fallback writes it, is what lets a snapshot assertion read like the card the
    user actually sees *and* stay comparable with the fallback.
    """

    elements = card["elements"]
    assert [element["tag"] for element in elements] == ["markdown", "hr", "markdown"]
    return "\n\n".join(
        (
            card["header"]["title"]["content"],
            elements[0]["content"],
            "---",
            elements[2]["content"],
        )
    )


def _log_block(card: dict) -> str:
    """Just the execution-log half of a native card."""

    return card["elements"][2]["content"]


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


#: What a *shipped* host actually put in a round row's ``purpose``: not a line
#: anybody composed for the card, but ``sanitize_card_line`` over the Turn's
#: execution prompt — the whole ask, clipped at the display budget. Spelled out
#: in full because it is the exact string the compatibility boundary exists to
#: keep off every rendered surface.
_LEGACY_CLIPPED_PURPOSE = (
    "请先阅读 gateway 下的委派卡片模块，弄清楚 round 行的渲染顺序，然后把执行记录"
    "里的耗时口径与 ARS 的观测周期对齐，注意不要改动任何"
)

#: One card record exactly as the shipped release writes it. The visible task
#: line has always been persisted under ``task_description``; what changed is
#: only *what is put there* — a supplied display title instead of the ask — so
#: the document shape is deliberately frozen here rather than migrated.
_SHIPPED_CARD_DOCUMENT = {
    "task_ref": TASK_REF,
    "task_created_at": CREATED_AT,
    "origin_platform": "feishu",
    "origin_chat_id": "oc_chat",
    "origin_session_id": "sess_1",
    "origin_thread_id": None,
    "locale": "zh",
    "agent_id": "oh-my-pi",
    "model": "glm-5.3",
    "effort": "max",
    "task_description": "验证 oh-my-pi 的 Session 复用",
    "card_message_id": "om_card",
    "card_sink_state": "confirmed",
    "revision": 3,
    "last_projected_at": "2026-08-26T09:00:20+00:00",
    "pre_accept_status": "submitting",
    "degraded_notice": False,
    "rounds": [
        {
            "turn_key": "dturn_a1",
            "round_number": 1,
            "purpose": _LEGACY_CLIPPED_PURPOSE,
            "admitted_role": None,
            "status": "running",
            "session_projection": "new",
            "run_ref": "run_one",
            "session_ref": "sess_abcd1234",
            "session_origin": "created",
            "started_at": "2026-08-26T09:00:05+00:00",
            "settled_at": None,
            "result_summary": None,
        }
    ],
}


def test_a_card_written_by_the_shipped_release_still_restores_and_renders():
    """An already-delivered card keeps working, unchanged, across this change.

    A projection this host cannot read is a card it can no longer patch: the
    Task's one bound message would freeze at whatever it last said. So the
    document is read as it stands — same keys, same Task headline, same
    binding, same round numbering — and the only thing that moved is which text
    a *new* Task puts there.
    """

    restored = DelegateCardProjection.from_dict(dict(_SHIPPED_CARD_DOCUMENT))

    assert restored.task_description == "验证 oh-my-pi 的 Session 复用"
    # Still bound, so the next revision patches the same message rather than
    # sending this Task a second card.
    assert restored.bound and restored.card_message_id == "om_card"
    assert "💡 **任务**： 验证 oh-my-pi 的 Session 复用" in _card_text(
        render_delegation_card(restored)
    )
    # The round itself is intact — number, Run/Session evidence, boundaries,
    # state — because none of that was ever in doubt.
    row = restored.rounds[0]
    assert (row.turn_key, row.round_number, row.status) == ("dturn_a1", 1, "running")
    assert (row.run_ref, row.session_ref, row.session_origin) == (
        "run_one",
        "sess_abcd1234",
        "created",
    )
    assert row.started_at == "2026-08-26T09:00:05+00:00"
    assert "task_title" not in restored.as_dict()


def test_a_caption_a_shipped_host_clipped_out_of_the_prompt_is_not_restored():
    """The one thing an old card does not keep: a caption nobody wrote for it.

    A shipped host filled ``purpose`` with the Turn's execution prompt cut at
    the display budget, so what is on disk is half an instruction presented as
    the round's goal. Reading it back is the compatibility boundary, and it is
    where the untrusted line stops: the row is restored without a caption, the
    log says which round it is and how it went, and nothing reaches for the
    complete ask sitting next to it.
    """

    restored = DelegateCardProjection.from_dict(dict(_SHIPPED_CARD_DOCUMENT))

    assert restored.rounds[0].purpose is None
    log = _log_block(render_delegation_card(restored))
    assert "▶️ 第 1 轮\n" in log
    assert "第 1 轮：" not in log
    assert _LEGACY_CLIPPED_PURPOSE[:20] not in _card_text(
        render_delegation_card(restored)
    )
    assert _LEGACY_CLIPPED_PURPOSE[:20] not in render_delegation_markdown(restored)
    # The row still says everything it can honestly say.
    assert "**Session**：新建" in log
    assert "**状态**：执行中" in log
    # And the drop is durable: what this host writes back no longer carries the
    # clipped prompt, so no later read can resurrect it.
    assert _LEGACY_CLIPPED_PURPOSE not in json.dumps(
        restored.as_dict(), ensure_ascii=False
    )
    # The write-back is that drop plus exactly one added key, and no other
    # difference at all. The document a round row is stored as could not carry
    # its own provenance before, so gaining ``purpose_origin`` is the whole
    # migration — an old *reader* now refuses this row, which costs a rolled-back
    # host the ability to patch this one card and is the price of being able to
    # tell an authored caption from a clipped prompt at all.
    written = restored.as_dict()["rounds"][0]
    shipped = dict(_SHIPPED_CARD_DOCUMENT["rounds"][0])
    assert set(written) - set(shipped) == {"purpose_origin"}
    assert written["purpose_origin"] is None
    assert {key: value for key, value in written.items() if key != "purpose_origin"} == {
        **shipped,
        "purpose": None,
    }


def test_a_round_line_this_host_sealed_survives_its_own_document():
    """A caption with a stated provenance round-trips; that is the whole point.

    Dropping every caption on read would be the easy way to obey the contract
    and would silently blank the execution log of every live card after one
    restart. The record therefore says where a caption came from, and a caption
    that came from the round's own supplied line is kept.
    """

    sealed = append_round(_projection(), turn_key="dturn_a1", purpose="核对第一轮的说明")
    document = sealed.as_dict()["rounds"][0]
    assert document["purpose"] == "核对第一轮的说明"
    assert document["purpose_origin"] == "round_title"

    restored = DelegateCardProjection.from_dict(sealed.as_dict())
    assert restored == sealed
    assert restored.rounds[0].purpose == "核对第一轮的说明"
    assert "第 1 轮：核对第一轮的说明" in _log_block(render_delegation_card(restored))


def test_the_durable_record_refuses_a_caption_with_no_stated_provenance():
    """Unattributed is refused, not quietly rendered.

    Dropping happens at exactly one place — the read of an older document —
    and nowhere else. Anywhere in-process, a caption whose origin the record
    cannot state is corrupt state and fails closed with the stable code, so a
    future writer cannot reintroduce the defect by omitting the provenance.
    """

    with pytest.raises(DelegateCardError) as excinfo:
        DelegateCardRound(turn_key="dturn_a1", round_number=1, purpose="来路不明")
    assert str(excinfo.value) == SACHIMA_DELEGATE_CARD_INVALID

    with pytest.raises(DelegateCardError):
        DelegateCardRound(
            turn_key="dturn_a1",
            round_number=1,
            purpose="来路不明",
            purpose_origin="task_description",
        )
    # A provenance with no caption is refused for the same reason: it claims an
    # attribution for a line that is not there.
    with pytest.raises(DelegateCardError):
        DelegateCardRound(
            turn_key="dturn_a1", round_number=1, purpose_origin="round_title"
        )


def test_one_card_can_hold_a_legacy_row_and_a_sealed_row_and_tell_them_apart():
    """The mixed card is the case a card-wide version marker would get wrong.

    An old card gains its next round on the upgraded host, so one document
    holds a clipped caption written before the split and a supplied line
    written after it. Provenance is per row because the difference is per row:
    round 1 loses its caption, round 2 keeps its own, and writing the card back
    does not bless the one it dropped.
    """

    restored = DelegateCardProjection.from_dict(dict(_SHIPPED_CARD_DOCUMENT))
    continued = append_round(restored, turn_key="dturn_b2", purpose="核对第二轮的说明")

    log = _log_block(render_delegation_card(continued))
    assert "▶️ 第 1 轮\n" in log
    assert "▶️ 第 2 轮：核对第二轮的说明" in log
    assert _LEGACY_CLIPPED_PURPOSE[:20] not in log

    rewritten = DelegateCardProjection.from_dict(continued.as_dict())
    assert rewritten == continued
    assert rewritten.rounds[0].purpose is None
    assert rewritten.rounds[1].purpose == "核对第二轮的说明"


@pytest.mark.parametrize(
    "value",
    [
        "带 dtask_0f3c9a11b2c34d5e6f70 的标题",
        "目" * (CARD_TEXT_BUDGET_CHARS + 1),
        "两行\n标题",
        "带\x07控制符",
        "   ",
    ],
)
def test_the_durable_title_boundary_fails_closed_on_unsafe_material(value):
    """The producer sanitizes; the record refuses. No repair, no echo."""

    with pytest.raises(DelegateCardError) as excinfo:
        _projection(task_description=value)
    assert str(excinfo.value) == SACHIMA_DELEGATE_CARD_INVALID


def test_a_sanitized_title_is_always_accepted_by_the_durable_boundary():
    """Drift lock: what the producer's sanitizer emits, the record takes."""

    cleaned = sanitize_card_line(
        "验证 dtask_0f3c9a11b2c34d5e6f70 的\n Session 复用 " + "长" * 500
    )
    assert len(cleaned) == CARD_TEXT_BUDGET_CHARS
    assert _projection(task_description=cleaned).task_description == cleaned


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
        ("submitting", 1, "委派任务 · 提交中", "Delegated Task · Submitting"),
        ("rejected", 1, "委派任务 · 未受理", "Delegated Task · Not Admitted"),
        ("accepted", 2, "委派任务 · 已受理", "Delegated Task · Admitted"),
        ("running", 2, "委派任务 · 执行中", "Delegated Task · Running"),
        ("completed", 2, "委派任务 · 已完成", "Delegated Task · Completed"),
        ("failed", 2, "委派任务 · 已失败", "Delegated Task · Failed"),
        ("cancelled", 2, "委派任务 · 已取消", "Delegated Task · Cancelled"),
        (
            "recovering",
            2,
            "委派任务 · 状态待恢复",
            "Delegated Task · Recovery Pending",
        ),
    ],
)
def test_every_required_title_state_renders_in_both_locales(state, round_number, zh, en):
    assert card_title(state, round_number, locale="zh") == zh
    assert card_title(state, round_number, locale="en") == en


def test_the_title_states_the_state_and_leaves_counting_to_the_log():
    """The headline names the Task and how it is doing — never which round.

    A round number in the title made the one line a person reads change for a
    reason they did not ask about, and said twice what the 执行记录 rows already
    say round by round. The count still exists; it exists *there*.
    """

    for number in (1, 2, 7):
        assert card_title("running", number, locale="zh") == "委派任务 · 执行中"
        assert card_title("running", number, locale="en") == "Delegated Task · Running"
    assert "轮" not in card_title("completed", 3, locale="zh")
    assert "Round" not in card_title("completed", 3, locale="en")
    # A round number is still the thing that says which vocabulary applies:
    # ``已创建`` is a Task that has no round yet, not a round state.
    assert card_title("created", None, locale="zh") == "委派任务 · 已创建"
    with pytest.raises(DelegateCardError):
        card_title("created", 1, locale="zh")
    with pytest.raises(DelegateCardError):
        card_title("running", None, locale="zh")


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
    assert lines[2] == "💡 **任务**： 验证 oh-my-pi 的 Session 复用"
    assert lines[3] == f"🆔 **编号**： {TASK_REF}"
    assert lines[4] == "⏱️ **耗时**： 0秒"
    assert lines[5] == "🤖 **执行**： oh-my-pi · glm-5.3 · max"
    assert lines[6] == "👤 **角色**： 未指定"
    # No bullets anywhere, and no blank line between the five field rows.
    for line in lines[2:7]:
        assert not line.startswith("-")
        assert not line.startswith("•")
        assert line.strip()


def test_english_summary_uses_ascii_colons_and_english_labels():
    projection = _projection(locale="en", task_description="Verify oh-my-pi session reuse")
    lines = _lines(_card_text(render_delegation_card(projection)))
    assert lines[0] == "Delegated Task · Created"
    assert lines[2] == "💡 **Task**: Verify oh-my-pi session reuse"
    assert lines[3] == f"🆔 **ID**: {TASK_REF}"
    assert lines[4] == "⏱️ **Duration**: 0s"
    assert lines[5] == "🤖 **Execution**: oh-my-pi · glm-5.3 · max"
    assert lines[6] == "👤 **Role**: Not specified"


def test_one_card_never_mixes_locales():
    for locale, foreign in (("zh", ("Task:", "Duration:")), ("en", ("任务：", "耗时："))):
        body = _card_text(render_delegation_card(_projection(locale=locale)))
        for token in foreign:
            assert token not in body


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        (
            "zh",
            (
                "💡 **任务**：",
                "🆔 **编号**：",
                "⏱️ **耗时**：",
                "🤖 **执行**：",
                "👤 **角色**：",
            ),
        ),
        (
            "en",
            (
                "💡 **Task**:",
                "🆔 **ID**:",
                "⏱️ **Duration**:",
                "🤖 **Execution**:",
                "👤 **Role**:",
            ),
        ),
    ],
)
def test_every_summary_field_name_is_bold_and_its_value_is_not(locale, expected):
    """The five field names carry the emphasis; the values stay plain weight.

    A value that emphasised itself would compete with the name it answers, and
    a card whose whole row is bold reads as one shouted line rather than as a
    label and a fact.
    """

    lines = _lines(_card_text(render_delegation_card(_projection(locale=locale))))[2:7]
    for line, prefix in zip(lines, expected):
        assert line.startswith(prefix), line
        value = line[len(prefix) :]
        assert value.strip()
        assert "*" not in value


def test_every_round_key_label_is_bold_and_its_value_is_not():
    """Session / 结果 / 状态 follow the summary rule, in both locales."""

    zh = _card_text(render_delegation_card(_two_round_projection()))
    assert "**Session**：新建" in zh
    assert "**结果**：上下文已建立" in zh
    assert "**状态**：执行中" not in zh  # round 2 has not opened a status yet
    zh_running = _card_text(
        render_delegation_card(
            advance_round(_two_round_projection(), "dturn_b2", status="running")
        )
    )
    assert "**状态**：执行中" in zh_running

    english = append_round(
        _projection(locale="en"), turn_key="dturn_e1", purpose="Establish context"
    )
    english = advance_round(
        english, "dturn_e1", status="running", session_projection="new"
    )
    body = _card_text(render_delegation_card(english))
    assert "**Session**: New" in body
    assert "**Status**: Running" in body
    # The round heading is not a key/value field, so it keeps its plain weight.
    assert "▶️ Round 1: Establish context" in body


def test_a_divider_separates_the_fixed_fields_from_the_execution_log():
    """Two things are on this card, so the card says so once, structurally.

    The Task's fixed fields answer "what is this"; the log answers "what has
    happened". Running them together as one block made a reader find that seam
    themselves on every glance. The native surface draws it with the platform's
    own divider element rather than with characters inside a text block.
    """

    card = render_delegation_card(_projection())
    assert [element["tag"] for element in card["elements"]] == [
        "markdown",
        "hr",
        "markdown",
    ]
    fields, _divider, log = card["elements"]
    assert fields["content"].startswith("💡 **任务**： ")
    assert fields["content"].endswith("👤 **角色**： 未指定")
    # The seam is the element boundary: neither half carries the other's text.
    assert "执行记录" not in fields["content"]
    assert "**任务**" not in log["content"]
    assert log["content"].startswith("**执行记录**\n")


def test_the_execution_log_header_is_bold_in_both_locales():
    """``执行记录`` names a section, so it carries the same weight as a key."""

    zh = _card_text(render_delegation_card(_projection()))
    assert "**执行记录**" in zh
    assert "\n执行记录\n" not in zh
    english = _card_text(render_delegation_card(_projection(locale="en")))
    assert "**Execution Log**" in english
    assert "\nExecution Log\n" not in english


def test_the_markdown_fallback_divides_and_emphasises_the_same_way():
    """Same meaning on the degraded surface, in that surface's own spelling.

    The fallback is plain text, so the divider is written rather than drawn.
    What must not differ is the reading: fields, a break, then the log under a
    heading of the same weight.
    """

    projection = _two_round_projection()
    fallback = render_delegation_markdown(projection)

    assert "\n\n---\n\n**执行记录**\n" in fallback
    assert fallback == _card_text(render_delegation_card(projection))
    english = render_delegation_markdown(_projection(locale="en"))
    assert "\n\n---\n\n**Execution Log**\n" in english


def test_a_value_can_neither_forge_the_log_header_nor_the_divider():
    """The section markers are the module's own; a value only ever says them."""

    projection = _projection(task_description="**执行记录**")
    projection = append_round(projection, turn_key="dturn_a1", purpose="--- 分割")
    body = _card_text(render_delegation_card(projection))

    assert "💡 **任务**： \\*\\*执行记录\\*\\*" in body
    # The module's own markers survive the pass that neutralised the value, and
    # the value's copy of them does not: one real header, one inert lookalike.
    assert body.count("\n\n---\n\n**执行记录**\n") == 1
    assert body.count("**执行记录**") == 1
    # ``---`` inside a value can never start a line, so it cannot rule either.
    assert "▶️ 第 1 轮：--- 分割" in body


def test_bold_field_names_never_leak_into_the_values_they_label():
    """One emphasis pair per rendered key, and none around any value."""

    projection = advance_round(
        _two_round_projection(),
        "dturn_b2",
        status="completed",
        session_projection="reused",
        result_summary="上下文验证通过",
        settled_at="2026-08-26T09:01:20+00:00",
    )
    for line in _lines(_card_text(render_delegation_card(projection))):
        assert line.count("**") in (0, 2), line


#: Host text that is markup, paired with the literal line it must render as.
#: The expectations are written out rather than computed from the renderer's
#: own helper, so a helper that stopped escaping could not agree with itself.
_MARKUP_VALUES = [
    ("**核对交付卡文案**", "\\*\\*核对交付卡文案\\*\\*"),
    ("_斜体_", "\\_斜体\\_"),
    ("~~删除线~~", "\\~\\~删除线\\~\\~"),
    ("`code`", "\\`code\\`"),
    ("[看这里](https://example.invalid)", "\\[看这里\\](https://example.invalid)"),
    ("<at id=all></at>", "\\<at id=all\\>\\</at\\>"),
    ("反斜杠 \\ 本身", "反斜杠 \\\\ 本身"),
]


@pytest.mark.parametrize(("raw", "shown"), _MARKUP_VALUES)
def test_a_task_title_that_looks_like_markup_is_shown_as_text(raw, shown):
    """A value says something; it never *does* something.

    The card body is one markdown block, so an unescaped value is markup: a
    title wrapped in ``**`` would render bold, competing with the field names
    that are deliberately the only emphasis on the card, and a link or a Feishu
    tag in a value would be worse than cosmetic.
    """

    projection = _projection(task_description=raw)
    line = _lines(_card_text(render_delegation_card(projection)))[2]

    assert line == f"💡 **任务**： {shown}"
    # The label keeps its own emphasis — exactly one pair, and it is the key's.
    assert line.count("**") == 2
    # One rule for both surfaces: the fallback is the same block, not a second
    # rendering with its own escaping.
    assert line in render_delegation_markdown(projection)


def test_a_result_summary_and_purpose_that_look_like_markup_are_shown_as_text():
    projection = append_round(_projection(), turn_key="dturn_a1", purpose="*重点*")
    projection = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        session_projection="new",
        result_summary="**已完成**",
        settled_at="2026-08-26T09:00:40+00:00",
    )
    lines = _lines(_card_text(render_delegation_card(projection)))

    assert "✅ 第 1 轮：\\*重点\\*" in lines
    assert "**结果**：\\*\\*已完成\\*\\*" in lines


def test_an_admitted_role_that_looks_like_markup_is_shown_as_text():
    projection = append_round(
        _projection(), turn_key="dturn_a1", admitted_role="`code_owner`"
    )
    body = _card_text(render_delegation_card(projection))
    # ``code_owner``'s underscore is intraword, so only the code fences move.
    assert "👤 **角色**： \\`code_owner\\`" in body


def test_an_intraword_underscore_is_never_escaped():
    """The copyable ID and snake_case tokens are rendered exactly as stored.

    A ``_`` between two alphanumerics cannot open or close emphasis, so
    escaping one would add a backslash to the two values a person is most
    likely to copy — the complete ``dtask_*`` and a configured role token —
    for no safety a reader could name.
    """

    projection = append_round(
        _projection(), turn_key="dturn_a1", admitted_role="session_reuse_verifier"
    )
    body = _card_text(render_delegation_card(projection))

    assert f"🆔 **编号**： {TASK_REF}" in body
    assert "👤 **角色**： session_reuse_verifier" in body
    assert "\\_" not in body
    # A value that wraps *itself* in underscores is still not italic.
    wrapped = _card_text(render_delegation_card(_projection(task_description="_全文_")))
    assert "💡 **任务**： \\_全文\\_" in wrapped


def test_every_dynamic_value_is_escaped_by_the_one_shared_rule():
    """Injection into any value leaves the card with the labels' emphasis only."""

    projection = _projection(task_description="**标题**")
    projection = append_round(
        projection, turn_key="dturn_a1", purpose="~~目的~~", admitted_role="*角色*"
    )
    projection = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        session_projection="new",
        result_summary="[结果](https://example.invalid)",
        settled_at="2026-08-26T09:00:40+00:00",
    )
    body = _card_text(render_delegation_card(projection))
    assert body == render_delegation_markdown(projection)

    for line in _lines(body):
        stripped = line.replace("**任务**", "").replace("**编号**", "")
        stripped = stripped.replace("**耗时**", "").replace("**执行**", "")
        stripped = stripped.replace("**角色**", "").replace("**Session**", "")
        stripped = stripped.replace("**结果**", "").replace("**状态**", "")
        stripped = stripped.replace("**执行记录**", "")
        # Whatever emphasis, code, link or tag character survives in a value is
        # escaped: it is preceded by a backslash that is not itself escaped.
        for index, char in enumerate(stripped):
            if char not in "*~`[]<>":
                continue
            assert index and stripped[index - 1] == "\\", line
            assert index < 2 or stripped[index - 2] != "\\", line


def test_the_full_task_id_is_shown_and_never_shortened():
    body = _card_text(render_delegation_card(_projection()))
    assert TASK_REF in body
    assert "…" not in body
    assert "..." not in body


def test_effort_is_omitted_rather_than_left_dangling():
    body = _card_text(render_delegation_card(_projection(effort="")))
    assert "🤖 **执行**： oh-my-pi · glm-5.3" in body
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
    assert "👤 **角色**： session_reuse_verifier" in body


def test_absent_role_renders_the_exact_honest_fallback():
    zh = _card_text(render_delegation_card(_projection()))
    assert "👤 **角色**： 未指定" in zh
    en = _card_text(render_delegation_card(_projection(locale="en")))
    assert "👤 **Role**: Not specified" in en


def test_missing_task_description_renders_an_honest_unavailable_value():
    zh = _card_text(render_delegation_card(_projection(task_description=None)))
    assert "💡 **任务**： 未提供" in zh
    en = _card_text(
        render_delegation_card(_projection(locale="en", task_description=None))
    )
    assert "💡 **Task**: Not provided" in en


# --------------------------------------------------------------------------- #
# S2 — duration from persisted lifecycle boundaries only
# --------------------------------------------------------------------------- #
def test_running_duration_uses_the_persisted_projection_instant():
    projection = projected_revision(
        append_round(_projection(), turn_key="dturn_a1"),
        at="2026-08-26T09:01:30+00:00",
    )
    projection = advance_round(projection, "dturn_a1", status="running")
    assert "⏱️ **耗时**： 1分30秒" in _card_text(render_delegation_card(projection))


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
    assert "⏱️ **耗时**： 45秒" in _card_text(render_delegation_card(projection))


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
    assert "⏱️ **耗时**： 1小时0分0秒" in _card_text(render_delegation_card(projection))


def test_a_missing_boundary_renders_an_honest_unavailable_duration():
    projection = append_round(_projection(), turn_key="dturn_a1")
    projection = advance_round(projection, "dturn_a1", status="running")
    # Nothing has been projected yet, so there is no persisted end boundary.
    assert "⏱️ **耗时**： 未知" in _card_text(render_delegation_card(projection))
    english = append_round(_projection(locale="en"), turn_key="dturn_a1")
    english = advance_round(english, "dturn_a1", status="running")
    assert "⏱️ **Duration**: Unknown" in _card_text(render_delegation_card(english))


def test_a_negative_interval_is_unavailable_rather_than_invented():
    projection = append_round(_projection(), turn_key="dturn_a1")
    projection = advance_round(
        projection,
        "dturn_a1",
        status="completed",
        settled_at="2026-08-26T08:00:00+00:00",
    )
    assert "⏱️ **耗时**： 未知" in _card_text(render_delegation_card(projection))


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
        "💡 **任务**： 验证 oh-my-pi 的 Session 复用\n"
        f"🆔 **编号**： {TASK_REF}\n"
        "⏱️ **耗时**： 0秒\n"
        "🤖 **执行**： oh-my-pi · glm-5.3 · max\n"
        "👤 **角色**： 未指定\n"
        "\n"
        "---\n"
        "\n"
        "**执行记录**\n"
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
        "委派任务 · 执行中\n"
        "\n"
        "💡 **任务**： 验证 oh-my-pi 的 Session 复用\n"
        f"🆔 **编号**： {TASK_REF}\n"
        "⏱️ **耗时**： 20秒\n"
        "🤖 **执行**： oh-my-pi · glm-5.3 · max\n"
        "👤 **角色**： 未指定\n"
        "\n"
        "---\n"
        "\n"
        "**执行记录**\n"
        "▶️ 第 1 轮：建立 Session 上下文\n"
        "**Session**：新建\n"
        "**状态**：执行中"
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
        "委派任务 · 执行中\n"
        "\n"
        "💡 **任务**： 验证 oh-my-pi 的 Session 复用\n"
        f"🆔 **编号**： {TASK_REF}\n"
        "⏱️ **耗时**： 1分0秒\n"
        "🤖 **执行**： oh-my-pi · glm-5.3 · max\n"
        "👤 **角色**： 未指定\n"
        "\n"
        "---\n"
        "\n"
        "**执行记录**\n"
        "✅ 第 1 轮：建立 Session 上下文\n"
        "**Session**：新建\n"
        "**结果**：上下文已建立\n"
        "\n"
        "▶️ 第 2 轮：验证 Session 上下文复用\n"
        "**Session**：复用状态确认中\n"
        "**状态**：执行中"
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
        "委派任务 · 已完成\n"
        "\n"
        "💡 **任务**： 验证 oh-my-pi 的 Session 复用\n"
        f"🆔 **编号**： {TASK_REF}\n"
        "⏱️ **耗时**： 1分20秒\n"
        "🤖 **执行**： oh-my-pi · glm-5.3 · max\n"
        "👤 **角色**： 未指定\n"
        "\n"
        "---\n"
        "\n"
        "**执行记录**\n"
        "✅ 第 1 轮：建立 Session 上下文\n"
        "**Session**：新建\n"
        "**结果**：上下文已建立\n"
        "\n"
        "✅ 第 2 轮：验证 Session 上下文复用\n"
        "**Session**：已确认复用\n"
        "**结果**：上下文验证通过"
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
    assert "**Session**：复用状态未确认" in body
    assert "已确认复用" not in body.split("第 2 轮")[1]


def test_an_omitted_session_projection_drops_the_line_entirely():
    projection = append_round(_projection(), turn_key="dturn_a1", purpose="第一步")
    projection = advance_round(
        projection, "dturn_a1", status="running", session_projection="omitted"
    )
    body = _card_text(render_delegation_card(projection))
    # The rendered key is gone — not merely its old unemphasised spelling.
    assert "**Session**" not in body
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
    assert "**Session**: New" in body
    assert "**Result**: Context established" in body
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
    # The emphasis is part of that text, so the degraded surface carries the
    # same bold field names as the card it stands in for.
    lines = _lines(markdown)
    assert lines[2] == "💡 **任务**： 验证 oh-my-pi 的 Session 复用"
    assert lines[6] == "👤 **角色**： 未指定"
    assert "**Session**：已确认复用" in markdown
    assert "**结果**：上下文验证通过" in markdown


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
    assert _log_block(full).count("轮：") == 3

    # A limit that only the compacted card fits keeps the card and drops rows.
    compacted, markdown = bounded_card_payload(projection, limit=900)
    assert compacted is not None
    assert _log_block(compacted).count("轮：") < 3
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
    assert _log_block(card).count("轮：") == CARD_ROUND_WINDOW


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
    assert "⏱️ **耗时**： 45秒" in frozen

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
    assert "👤 **角色**： session_reuse_verifier" in _card_text(
        render_delegation_card(projection)
    )

    # The continuation was admitted by direct AGENT selection, so this card must
    # say so rather than re-showing a role the current round does not hold.
    projection = append_round(projection, turn_key="dturn_b2")
    assert "👤 **角色**： 未指定" in _card_text(render_delegation_card(projection))


def test_a_task_with_no_trustworthy_start_renders_an_unavailable_duration():
    """A missing start boundary is a missing boundary, never a fresh clock."""

    projection = _projection(task_created_at=None)
    assert projection.task_created_at is None
    assert "⏱️ **耗时**： 未知" in _card_text(render_delegation_card(projection))

    projection = append_round(projection, turn_key="dturn_a1")
    projection = projected_revision(projection, at="2026-08-26T10:00:00+00:00")
    projection = advance_round(projection, "dturn_a1", status="running")
    assert "⏱️ **耗时**： 未知" in _card_text(render_delegation_card(projection))
    english = _projection(locale="en", task_created_at=None)
    assert "⏱️ **Duration**: Unknown" in _card_text(render_delegation_card(english))


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
    assert "⏱️ **耗时**： 未知" in frozen

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
    assert "⏱️ **耗时**： 45秒" in _card_text(render_delegation_card(trusted))
    assert "⏱️ **耗时**： 45秒" in _card_text(
        render_delegation_card(DelegateCardProjection.from_dict(trusted.as_dict()))
    )
