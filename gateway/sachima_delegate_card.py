"""Sachima delegation — the one status card a delegated Task owns.

A native delegation is a durable **Task** thread, not one execution. One Feishu
card belongs to one ``dtask_*``; each continuation is a distinct Sachima Turn
backed by a distinct ARS Run and adds exactly one bounded round row to that same
card. Nothing here sends anything: this module owns the *projection* — the
durable record of what the card should say and what has actually been delivered
— plus the deterministic renderer that turns it into one native payload and one
compact Markdown fallback.

The layer is deliberately platform-neutral and pure. It imports no adapter, no
coordinator, and no supervisor: a projection is data, and a card is a function
of that data. That is what makes the four confirmed visual snapshots assertable
without a socket, and what keeps a Feishu outage from being able to alter Task
truth.

Four boundaries shape every function here:

**The card is a projection, never an authority.** ARS and Sachima durable state
own lifecycle. This record stores the card's message binding, its settled sink
state, and a monotonic revision — delivery facts, not execution facts.

**Persisted evidence only.** ``task_created_at`` is written once with the
durable Task/origin allocation and is the duration start boundary. The end
boundary is a persisted projection instant or a persisted terminal settlement —
never a render-time clock. A missing boundary — including a Task whose start
this host does not retain — renders an honest unavailable value; the renderer
never invents a duration.

**Safe conclusions, not evidence.** The complete ``dtask_*`` is the deliberate
user-facing exception. Round rows carry a sealed purpose, a bounded result line,
and one Session conclusion; ``dres_*``, ``turn_key``, ARS Run/Session ids,
prompts, credentials, and raw events are absent from every rendered surface and
refused at the durable boundary.

**Reuse is proven or it is not claimed.** ``Session：已确认复用`` requires the
same Task, two *different* Run identities, one *same* ARS Session identity, a
**settled** earlier round that recorded the create, and a recorded load now.
The create is traced across the Task's ordered rounds, never read off the row
immediately behind — that row is itself a load from the second continuation
onward. Anything less says so.

Forbidden terms in this prose are no-leak boundary canaries only, never behavior.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

__all__ = [
    "CARD_LOCALES",
    "CARD_ROUND_WINDOW",
    "CARD_SINK_STATES",
    "CARD_TEXT_BUDGET_CHARS",
    "PRE_ACCEPT_STATES",
    "ROUND_STATES",
    "RUNNING_PATCH_INTERVAL_FLOOR_SECONDS",
    "RUNNING_PATCH_INTERVAL_MAX_SECONDS",
    "RUNNING_PATCH_INTERVAL_SECONDS",
    "SACHIMA_DELEGATE_CARD_CONFLICT",
    "SACHIMA_DELEGATE_CARD_INVALID",
    "SACHIMA_DELEGATE_CARD_OVERSIZED",
    "SACHIMA_DELEGATE_CARD_STABLE_CODES",
    "SESSION_PROJECTIONS",
    "TERMINAL_ROUND_STATES",
    "DelegateCardError",
    "DelegateCardProjection",
    "DelegateCardRound",
    "advance_round",
    "append_round",
    "bind_card_message",
    "bounded_card_payload",
    "card_header_template",
    "card_state",
    "card_title",
    "derive_session_ref",
    "new_card_projection",
    "next_projection_revision",
    "normalize_running_patch_interval",
    "project_session_evidence",
    "projected_revision",
    "render_delegation_card",
    "render_delegation_markdown",
    "safe_card_instant",
    "safe_card_task_ref",
    "sanitize_card_line",
    "settle_card_sink",
]

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never the material)
# --------------------------------------------------------------------------- #
SACHIMA_DELEGATE_CARD_INVALID = "sachima_delegate_card_invalid"
SACHIMA_DELEGATE_CARD_CONFLICT = "sachima_delegate_card_conflict"
SACHIMA_DELEGATE_CARD_OVERSIZED = "sachima_delegate_card_oversized"

SACHIMA_DELEGATE_CARD_STABLE_CODES = frozenset(
    {
        SACHIMA_DELEGATE_CARD_INVALID,
        SACHIMA_DELEGATE_CARD_CONFLICT,
        SACHIMA_DELEGATE_CARD_OVERSIZED,
    }
)


class DelegateCardError(ValueError):
    """A card failure whose message IS the stable code — never the material."""


def _invalid() -> DelegateCardError:
    return DelegateCardError(SACHIMA_DELEGATE_CARD_INVALID)


def _conflict() -> DelegateCardError:
    return DelegateCardError(SACHIMA_DELEGATE_CARD_CONFLICT)


# --------------------------------------------------------------------------- #
# S0 numeric contracts — derived from existing source constants
#
# Every value below is arithmetic over a constant that already governs this
# path, and each input is drift-locked against its owning module by
# ``tests/gateway/test_sachima_delegate_card.py``. Importing those modules here
# would drag a platform adapter and the coordinator into a layer that must stay
# pure, so the inputs are mirrored *and* proven equal rather than imported.
# --------------------------------------------------------------------------- #
#: ``gateway/platforms/feishu.py::_FEISHU_SEND_ATTEMPTS`` — the adapter's own
#: transient-retry ladder for one ``im.v1.message.patch`` call.
_FEISHU_PATCH_ATTEMPTS = 3
#: ``gateway/sachima_delegate.py::_DEFAULT_OBSERVE_INTERVAL_SECONDS`` — the
#: cadence at which a running Run's state can even be learned.
_DELEGATE_OBSERVE_INTERVAL_SECONDS = 2.0
#: ``gateway/sachima_delegate.py::_MAX_CONSECUTIVE_OBSERVE_FAILURES`` — the
#: consecutive observation faults tolerated before Sachima says it is blind.
_DELEGATE_OBSERVE_FAILURE_BUDGET = 5

#: **Floor.** The adapter sleeps ``2**attempt`` seconds between patch attempts,
#: so one call can stay inside its own ladder for this long. A projection layer
#: that patched faster would open a second adapter call over the first.
RUNNING_PATCH_INTERVAL_FLOOR_SECONDS = float(
    sum(2**index for index in range(_FEISHU_PATCH_ATTEMPTS - 1))
)

#: **Default.** The smallest whole multiple of the observation cadence that
#: clears the floor. Unit: seconds. Scope: running-state patches of the Feishu
#: delegation status card only — it paces neither ARS observation, nor the
#: adapter's transport retry, nor the terminal flush (a settled terminal is
#: always projected immediately as the final revision). Restart semantics: read
#: once when the coordinator is constructed; changing it is a reviewed
#: code/config change plus a Gateway restart, and in-flight coalescing state is
#: in-memory and is rebuilt from the durable projection after a restart.
RUNNING_PATCH_INTERVAL_SECONDS = float(
    math.ceil(RUNNING_PATCH_INTERVAL_FLOOR_SECONDS / _DELEGATE_OBSERVE_INTERVAL_SECONDS)
    * _DELEGATE_OBSERVE_INTERVAL_SECONDS
)

#: **Allowed maximum.** The point at which the coordinator itself reports that
#: it has gone blind. A card cadence slower than that would keep asserting a
#: running state Sachima no longer trusts.
RUNNING_PATCH_INTERVAL_MAX_SECONDS = float(
    _DELEGATE_OBSERVE_FAILURE_BUDGET * _DELEGATE_OBSERVE_INTERVAL_SECONDS
)


def normalize_running_patch_interval(value: Any) -> float:
    """The cadence this host will actually use, for any supplied value.

    Invalid-value handling is deliberate rather than lenient: a non-number, a
    ``bool``, a non-finite value, or anything outside
    ``[floor, maximum]`` is answered with the default. The card is a fallible
    presentation surface, so a mis-typed cadence must not refuse to compose a
    Gateway — but it must also never be honoured, because both an unbounded
    patch storm and a cadence slower than the blindness budget are untruthful.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return RUNNING_PATCH_INTERVAL_SECONDS
    numeric = float(value)
    if not math.isfinite(numeric):
        return RUNNING_PATCH_INTERVAL_SECONDS
    if (
        numeric < RUNNING_PATCH_INTERVAL_FLOOR_SECONDS
        or numeric > RUNNING_PATCH_INTERVAL_MAX_SECONDS
    ):
        return RUNNING_PATCH_INTERVAL_SECONDS
    return numeric


#: The product's bounded-card display contract: round rows per Feishu card,
#: default and maximum alike. It is a readability decision, not a retention or
#: safety limit; changing it needs a reviewed config/code change plus a Gateway
#: restart. S0 verified the adapter's own one-message bound
#: (``FeishuAdapter.MAX_MESSAGE_LENGTH``) is far above a three-row card, so no
#: verified Feishu constraint requires lowering it.
CARD_ROUND_WINDOW = 3

#: One visible card line's bound, in characters. It is the existing delegation
#: task-description budget rather than a new number, so a purpose, a result
#: line, and a description are all bounded by one reviewed value.
CARD_TEXT_BUDGET_CHARS = 200


# --------------------------------------------------------------------------- #
# Closed vocabularies
# --------------------------------------------------------------------------- #
CARD_LOCALES = ("zh", "en")

#: Delivery states of the one card message a Task owns. ``uncertain`` exists
#: because a send that raised may still have landed, and guessing either way is
#: worse than recording the gap.
CARD_SINK_STATES = ("pending", "confirmed", "failed", "uncertain")

#: The Task-level pre-acceptance journey. It drives the title only while no
#: round row exists yet.
PRE_ACCEPT_STATES = ("created", "waiting", "submitting", "rejected", "omitted")

#: One round row's state. A round is one Sachima Turn backed by one ARS Run.
ROUND_STATES = (
    "submitting",
    "rejected",
    "accepted",
    "running",
    "recovering",
    "completed",
    "failed",
    "cancelled",
)

#: Rounds that are settled. A settled round's duration boundary and result line
#: are fixed until another continuation starts.
TERMINAL_ROUND_STATES = ("completed", "failed", "cancelled", "rejected")

#: The Session conclusion a round row may expose. ``pending`` is the honest
#: answer while a continuation is still running; ``unconfirmed`` is the honest
#: answer once it settled without trusted create-then-load evidence.
SESSION_PROJECTIONS = ("new", "reused", "pending", "unconfirmed", "omitted")

#: How a Run reached its ARS Session, as recorded by the admission that created
#: or reused it. Never inferred from model output or from equal task refs.
SESSION_ORIGINS = ("created", "loaded")


# --------------------------------------------------------------------------- #
# Validation primitives
# --------------------------------------------------------------------------- #
_TASK_REF_RE = re.compile(r"^dtask_[0-9a-f]{8,120}$")
_TURN_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9_:.-]{1,128}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_WHITESPACE_RUN_RE = re.compile(r"\s+")

#: Internal identities that must never reach a rendered surface. The complete
#: ``dtask_*`` is the deliberate exception and is rendered from its own field,
#: so it is redacted here too: a task ref inside free text is echoed material,
#: not the card's own identity line.
_INTERNAL_REF_RE = re.compile(
    r"\b(?:dtask_|dturn_|dres_|devt_|dlg_|run_|sess_)[0-9A-Za-z]{6,}\b"
)
_REDACTED = "[…]"


def safe_card_task_ref(value: Any) -> str:
    """The public ``dtask_*`` a card is keyed by, or fail closed with no echo.

    The durable store addresses a card file by this value, so the grammar is
    exact rather than merely "safe-looking": anything that is not the complete
    task ref never becomes a path component.
    """

    if type(value) is not str or _TASK_REF_RE.fullmatch(value) is None:
        raise _invalid()
    return value


_safe_task_ref = safe_card_task_ref


def _safe_turn_key(value: Any) -> str:
    if type(value) is not str or _TURN_KEY_RE.fullmatch(value) is None:
        raise _invalid()
    return value


def _safe_token(value: Any, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise _invalid()
    if not value:
        if allow_empty:
            return ""
        raise _invalid()
    if _TOKEN_RE.fullmatch(value) is None:
        raise _invalid()
    return value


def _optional_token(value: Any) -> str | None:
    if value is None:
        return None
    return _safe_token(value)


def _member(value: Any, allowed: tuple[str, ...]) -> str:
    if type(value) is not str or value not in allowed:
        raise _invalid()
    return value


def _bool(value: Any) -> bool:
    if type(value) is not bool:
        raise _invalid()
    return value


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise _invalid()
    return value


def _instant(value: Any) -> str:
    """One persisted UTC lifecycle boundary, or fail closed.

    Timestamps here are *evidence*, so the grammar is strict: a tz-aware UTC
    ISO-8601 string and nothing else. A naive or offset instant would make two
    boundaries incomparable, and an incomparable duration is exactly the kind of
    number this card must not invent.
    """

    if type(value) is not str or not value:
        raise _invalid()
    if _parse_instant(value) is None:
        raise _invalid()
    return value


def _optional_instant(value: Any) -> str | None:
    if value is None:
        return None
    return _instant(value)


def safe_card_instant(value: Any) -> str | None:
    """One persisted lifecycle boundary this layer will accept, or ``None``.

    Boundaries reach a durable record from more than one writer, so a producer
    reconstructing older state needs to ask whether an instant is usable
    *before* it builds a record around it. A boundary this layer would refuse
    is a **missing** boundary — which renders as an honest unavailable value —
    never an exception that would lose an otherwise safe reconstruction, and
    never a repaired guess.
    """

    if value is None:
        return None
    try:
        return _instant(value)
    except DelegateCardError:
        return None


def _parse_instant(value: Any) -> datetime | None:
    if type(value) is not str or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        return None
    return parsed.astimezone(timezone.utc)


def _private_text(value: Any) -> str:
    """Host routing material: bounded and type-checked, never rendered."""

    if type(value) is not str or len(value) > 512:
        raise _invalid()
    return value


def _optional_private_text(value: Any) -> str | None:
    if value is None:
        return None
    return _private_text(value)


def sanitize_card_line(value: Any) -> str | None:
    """One bounded, single-line, leak-free rendering of host text, or ``None``.

    Three things happen, in order: control characters are dropped, whitespace
    runs fold to single spaces, and every internal identity is redacted. The
    redaction is what lets a *producer* hand user- or result-derived text to the
    durable record safely — the record itself refuses anything that still
    carries a ref, so the two halves cannot drift into a leak.

    Returns ``None`` rather than an empty string when nothing survives, so a
    caller cannot render a blank row as if it were content.
    """

    if type(value) is not str:
        return None
    collapsed = _WHITESPACE_RUN_RE.sub(" ", _CONTROL_CHARS_RE.sub("", value)).strip()
    if not collapsed:
        return None
    redacted = _INTERNAL_REF_RE.sub(_REDACTED, collapsed).strip()
    if not redacted:
        return None
    return redacted[:CARD_TEXT_BUDGET_CHARS]


#: The exact key set each record document may carry. A widened document fails
#: closed rather than being read with its extra field ignored: a record that
#: grew a ``raw_*`` field is exactly the leak this layer exists to refuse.
_ROUND_KEYS = frozenset(
    {
        "turn_key",
        "round_number",
        "purpose",
        "admitted_role",
        "status",
        "session_projection",
        "run_ref",
        "session_ref",
        "session_origin",
        "started_at",
        "settled_at",
        "result_summary",
    }
)
_PROJECTION_KEYS = frozenset(
    {
        "task_ref",
        "task_created_at",
        "origin_platform",
        "origin_chat_id",
        "origin_session_id",
        "origin_thread_id",
        "locale",
        "agent_id",
        "model",
        "effort",
        "task_description",
        "card_message_id",
        "card_sink_state",
        "revision",
        "last_projected_at",
        "pre_accept_status",
        "degraded_notice",
        "rounds",
    }
)


def _closed_document(document: Any, keys: frozenset[str]) -> Mapping:
    if not isinstance(document, Mapping):
        raise _invalid()
    if not set(document).issubset(keys):
        raise _invalid()
    return document


def _visible_text(value: Any) -> str | None:
    """A visible line as the durable record will accept it, or fail closed.

    Unlike :func:`sanitize_card_line` this never repairs: a caller that skipped
    sanitization and handed over an internal ref, a control character, or an
    over-budget line gets a stable code. Fail-closed at the durable boundary,
    redact at the producer.
    """

    if value is None:
        return None
    if type(value) is not str or not value.strip():
        raise _invalid()
    if len(value) > CARD_TEXT_BUDGET_CHARS:
        raise _invalid()
    if _CONTROL_CHARS_RE.search(value) or "\n" in value or "\r" in value:
        raise _invalid()
    if _INTERNAL_REF_RE.search(value):
        raise _invalid()
    return value


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DelegateCardRound:
    """One round row: one Sachima Turn, one ARS Run, one independent terminal.

    ``run_ref`` / ``session_ref`` are safe derived handles kept for *evidence*
    — they are how "two different Runs on one Session" becomes provable across a
    restart — and they are never rendered. The row the user reads is the
    purpose, the Session conclusion, and one bounded result or status line.
    """

    turn_key: str
    round_number: int
    purpose: str | None = None
    admitted_role: str | None = None
    status: str = "submitting"
    session_projection: str = "omitted"
    run_ref: str | None = field(default=None, repr=False)
    session_ref: str | None = field(default=None, repr=False)
    session_origin: str | None = None
    started_at: str | None = None
    settled_at: str | None = None
    result_summary: str | None = None

    def __post_init__(self) -> None:
        _safe_turn_key(self.turn_key)
        if isinstance(self.round_number, bool) or type(self.round_number) is not int:
            raise _invalid()
        if self.round_number < 1:
            raise _invalid()
        _visible_text(self.purpose)
        _visible_text(self.admitted_role)
        _member(self.status, ROUND_STATES)
        _member(self.session_projection, SESSION_PROJECTIONS)
        _optional_token(self.run_ref)
        _optional_token(self.session_ref)
        if self.session_origin is not None:
            _member(self.session_origin, SESSION_ORIGINS)
        _optional_instant(self.started_at)
        _optional_instant(self.settled_at)
        _visible_text(self.result_summary)

    @property
    def settled(self) -> bool:
        return self.status in TERMINAL_ROUND_STATES

    def as_dict(self) -> dict[str, Any]:
        return {
            "turn_key": self.turn_key,
            "round_number": self.round_number,
            "purpose": self.purpose,
            "admitted_role": self.admitted_role,
            "status": self.status,
            "session_projection": self.session_projection,
            "run_ref": self.run_ref,
            "session_ref": self.session_ref,
            "session_origin": self.session_origin,
            "started_at": self.started_at,
            "settled_at": self.settled_at,
            "result_summary": self.result_summary,
        }

    @classmethod
    def from_dict(cls, document: Any) -> "DelegateCardRound":
        _closed_document(document, _ROUND_KEYS)
        return cls(
            turn_key=document.get("turn_key"),
            round_number=document.get("round_number"),
            purpose=document.get("purpose"),
            admitted_role=document.get("admitted_role"),
            status=document.get("status", "submitting"),
            session_projection=document.get("session_projection", "omitted"),
            run_ref=document.get("run_ref"),
            session_ref=document.get("session_ref"),
            session_origin=document.get("session_origin"),
            started_at=document.get("started_at"),
            settled_at=document.get("settled_at"),
            result_summary=document.get("result_summary"),
        )


@dataclass(frozen=True)
class DelegateCardProjection:
    """One Task's card: sealed identity, delivery binding, and ordered rounds.

    Chat id and the platform message id are host/platform routing material:
    both are ``repr``-excluded and neither is ever rendered. The origin triple
    is sealed at allocation so a restored Task cannot patch a card in another
    conversation.
    """

    task_ref: str
    #: The duration start boundary, or ``None`` when this host retains no
    #: trustworthy one. It is optional for exactly one reason: a Task that
    #: predates card projection may have rounds whose lifecycle boundaries were
    #: never persisted, and "now" would be a start such a Task demonstrably did
    #: not have. Absent renders the honest unavailable duration; it is never a
    #: licence to substitute a clock reading.
    task_created_at: str | None
    origin_platform: str
    origin_chat_id: str = field(repr=False)
    origin_session_id: str = field(repr=False)
    origin_thread_id: str | None = field(default=None, repr=False)
    locale: str = "zh"
    agent_id: str = ""
    model: str = ""
    effort: str = ""
    task_description: str | None = None
    card_message_id: str | None = field(default=None, repr=False)
    card_sink_state: str = "pending"
    revision: int = 0
    last_projected_at: str | None = None
    pre_accept_status: str = "created"
    degraded_notice: bool = False
    rounds: tuple[DelegateCardRound, ...] = ()

    def __post_init__(self) -> None:
        _safe_task_ref(self.task_ref)
        _optional_instant(self.task_created_at)
        _safe_token(self.origin_platform)
        _private_text(self.origin_chat_id)
        _private_text(self.origin_session_id)
        _optional_private_text(self.origin_thread_id)
        _member(self.locale, CARD_LOCALES)
        _safe_token(self.agent_id, allow_empty=True)
        _safe_token(self.model, allow_empty=True)
        _safe_token(self.effort, allow_empty=True)
        _visible_text(self.task_description)
        if self.card_message_id is not None and (
            type(self.card_message_id) is not str
            or _MESSAGE_ID_RE.fullmatch(self.card_message_id) is None
        ):
            raise _invalid()
        _member(self.card_sink_state, CARD_SINK_STATES)
        _non_negative_int(self.revision)
        _optional_instant(self.last_projected_at)
        _member(self.pre_accept_status, PRE_ACCEPT_STATES)
        _bool(self.degraded_notice)
        if type(self.rounds) is not tuple:
            raise _invalid()
        seen: set[str] = set()
        for index, row in enumerate(self.rounds):
            if type(row) is not DelegateCardRound:
                raise _invalid()
            if row.round_number != index + 1:
                # Round numbering is the durable ``turn_keys`` order. A record
                # whose numbers disagree with its own order is corrupt state,
                # never a display choice to reconcile at render time.
                raise _invalid()
            if row.turn_key in seen:
                raise _invalid()
            seen.add(row.turn_key)

    # -- identity ----------------------------------------------------------- #
    def owns_origin(
        self, *, platform: Any, chat_id: Any, session_id: Any
    ) -> bool:
        """Whether this card belongs to that exact conversation."""

        return (
            self.origin_platform == platform
            and self.origin_chat_id == chat_id
            and self.origin_session_id == session_id
        )

    def round_for(self, turn_key: Any) -> DelegateCardRound | None:
        for row in self.rounds:
            if row.turn_key == turn_key:
                return row
        return None

    @property
    def latest_round(self) -> DelegateCardRound | None:
        return self.rounds[-1] if self.rounds else None

    @property
    def bound(self) -> bool:
        return self.card_message_id is not None and self.card_sink_state == "confirmed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_ref": self.task_ref,
            "task_created_at": self.task_created_at,
            "origin_platform": self.origin_platform,
            "origin_chat_id": self.origin_chat_id,
            "origin_session_id": self.origin_session_id,
            "origin_thread_id": self.origin_thread_id,
            "locale": self.locale,
            "agent_id": self.agent_id,
            "model": self.model,
            "effort": self.effort,
            "task_description": self.task_description,
            "card_message_id": self.card_message_id,
            "card_sink_state": self.card_sink_state,
            "revision": self.revision,
            "last_projected_at": self.last_projected_at,
            "pre_accept_status": self.pre_accept_status,
            "degraded_notice": self.degraded_notice,
            "rounds": [row.as_dict() for row in self.rounds],
        }

    @classmethod
    def from_dict(cls, document: Any) -> "DelegateCardProjection":
        _closed_document(document, _PROJECTION_KEYS)
        rows = document.get("rounds")
        if type(rows) is not list:
            raise _invalid()
        return cls(
            task_ref=document.get("task_ref"),
            task_created_at=document.get("task_created_at"),
            origin_platform=document.get("origin_platform"),
            origin_chat_id=document.get("origin_chat_id"),
            origin_session_id=document.get("origin_session_id"),
            origin_thread_id=document.get("origin_thread_id"),
            locale=document.get("locale", "zh"),
            agent_id=document.get("agent_id", ""),
            model=document.get("model", ""),
            effort=document.get("effort", ""),
            task_description=document.get("task_description"),
            card_message_id=document.get("card_message_id"),
            card_sink_state=document.get("card_sink_state", "pending"),
            revision=document.get("revision", 0),
            last_projected_at=document.get("last_projected_at"),
            pre_accept_status=document.get("pre_accept_status", "created"),
            degraded_notice=document.get("degraded_notice", False),
            rounds=tuple(DelegateCardRound.from_dict(row) for row in rows),
        )


# --------------------------------------------------------------------------- #
# Projection transitions
# --------------------------------------------------------------------------- #
def new_card_projection(
    *,
    task_ref: str,
    task_created_at: str | None,
    origin_platform: str,
    origin_chat_id: str,
    origin_session_id: str,
    origin_thread_id: str | None = None,
    locale: str = "zh",
    agent_id: str = "",
    model: str = "",
    effort: str = "",
    task_description: Any = None,
) -> DelegateCardProjection:
    """The projection written with the durable Task/origin allocation.

    This is the *only* place ``task_created_at`` is set. It exists before queue
    waiting and before any ARS submission, which is what makes the first card
    snapshot — and therefore the complete copyable ``dtask_*`` — a thing the
    user can be shown before anything could have failed silently. A caller that
    cannot evidence the boundary passes ``None`` rather than a substitute: an
    unavailable duration is a fact, an invented one is not.
    """

    return DelegateCardProjection(
        task_ref=task_ref,
        task_created_at=task_created_at,
        origin_platform=origin_platform,
        origin_chat_id=origin_chat_id,
        origin_session_id=origin_session_id,
        origin_thread_id=origin_thread_id,
        locale=locale,
        agent_id=agent_id,
        model=model,
        effort=effort,
        task_description=task_description,
    )


def append_round(
    projection: DelegateCardProjection,
    *,
    turn_key: str,
    purpose: Any = None,
    admitted_role: Any = None,
    started_at: Any = None,
) -> DelegateCardProjection:
    """Add this Turn's round row, once.

    ``turn_key → round_number`` is stable, append-only, and idempotent: a
    duplicate accepted/terminal event finds the row already there and changes
    nothing, including the purpose, which is sealed at Turn creation. A
    duplicate that could rewrite the purpose would let opaque later text
    redefine what an earlier round was for.
    """

    if type(projection) is not DelegateCardProjection:
        raise _invalid()
    _safe_turn_key(turn_key)
    if projection.round_for(turn_key) is not None:
        return projection
    row = DelegateCardRound(
        turn_key=turn_key,
        round_number=len(projection.rounds) + 1,
        purpose=purpose,
        admitted_role=admitted_role,
        started_at=started_at,
    )
    return replace(projection, rounds=projection.rounds + (row,))


def advance_round(
    projection: DelegateCardProjection,
    turn_key: str,
    *,
    status: Any = None,
    session_projection: Any = None,
    session_ref: Any = None,
    run_ref: Any = None,
    session_origin: Any = None,
    admitted_role: Any = None,
    result_summary: Any = None,
    settled_at: Any = None,
) -> DelegateCardProjection:
    """Move one existing round row forward. Never appends, never reorders.

    A settled round is **sealed**: it keeps its terminal, the instant its
    duration stopped at, and the conclusion it was settled with. A later event
    may fill in evidence the row was still missing — that is how a delayed
    Session fact or summary reaches a row that already ended — but it can
    neither reopen the round nor rewrite anything already recorded, because a
    header that flipped back or a settlement instant that moved would make both
    "independently terminal" and the frozen terminal duration untrue.
    """

    if type(projection) is not DelegateCardProjection:
        raise _invalid()
    existing = projection.round_for(turn_key)
    if existing is None:
        raise _conflict()
    if status is not None and existing.settled and status != existing.status:
        raise _conflict()

    def _select(recorded: Any, incoming: Any, *, missing: Any = None) -> Any:
        """What the row keeps: sealed evidence wins, an absence is fillable."""

        if incoming is None:
            return recorded
        if existing.settled and recorded != missing:
            return recorded
        return incoming

    updated = replace(
        existing,
        status=existing.status if status is None else status,
        session_projection=_select(
            existing.session_projection, session_projection, missing="omitted"
        ),
        session_ref=_select(existing.session_ref, session_ref),
        run_ref=_select(existing.run_ref, run_ref),
        session_origin=_select(existing.session_origin, session_origin),
        admitted_role=_select(existing.admitted_role, admitted_role),
        result_summary=_select(existing.result_summary, result_summary),
        settled_at=_select(existing.settled_at, settled_at),
    )
    rows = tuple(
        updated if row.turn_key == turn_key else row for row in projection.rounds
    )
    return replace(projection, rounds=rows)


def next_projection_revision(
    projection: DelegateCardProjection,
) -> DelegateCardProjection:
    """The same card state, claimed as the next durable revision.

    Every durable change to a projection is its own revision, because the
    revision is what a writer proves it is moving *forward* from: a state
    computed over an older read carries that older number and is refused, rather
    than replacing a projection somebody else already moved. It is deliberately
    not :func:`projected_revision` — nothing has been rendered here, so the
    persisted projection instant, which is a duration boundary, must not move.
    """

    if type(projection) is not DelegateCardProjection:
        raise _invalid()
    return replace(projection, revision=projection.revision + 1)


def projected_revision(
    projection: DelegateCardProjection,
    *,
    at: str,
    revision: Any = None,
) -> DelegateCardProjection:
    """Select the next durable projection revision and its persisted instant.

    The revision is monotonic so an older retry can never overwrite a newer
    state, and ``last_projected_at`` is the persisted instant a running
    snapshot's duration is measured to — not a render-time clock.
    """

    if type(projection) is not DelegateCardProjection:
        raise _invalid()
    _instant(at)
    if revision is None:
        next_revision = projection.revision + 1
    else:
        next_revision = _non_negative_int(revision)
        if next_revision <= projection.revision:
            raise _conflict()
    return replace(projection, revision=next_revision, last_projected_at=at)


def bind_card_message(
    projection: DelegateCardProjection,
    *,
    message_id: str,
    revision: int,
    at: str,
) -> DelegateCardProjection:
    """Record the one confirmed card message this Task owns.

    At most one confirmed active binding per Task/origin. The identical binding
    replays; a *different* message id is a conflict rather than a rebind,
    because two confirmed cards for one Task is precisely the outcome this whole
    projection exists to prevent.
    """

    if type(projection) is not DelegateCardProjection:
        raise _invalid()
    if type(message_id) is not str or _MESSAGE_ID_RE.fullmatch(message_id) is None:
        raise _invalid()
    _instant(at)
    _non_negative_int(revision)
    if projection.card_message_id is not None:
        if projection.card_message_id != message_id:
            raise _conflict()
        if revision <= projection.revision:
            return replace(projection, card_sink_state="confirmed")
        return replace(
            projection,
            card_sink_state="confirmed",
            revision=revision,
            last_projected_at=at,
        )
    return replace(
        projection,
        card_message_id=message_id,
        card_sink_state="confirmed",
        revision=max(revision, projection.revision),
        last_projected_at=at,
    )


def settle_card_sink(
    projection: DelegateCardProjection,
    *,
    state: str,
    degraded_notice: Any = None,
) -> DelegateCardProjection:
    """Persist one delivery outcome for the card sink.

    A confirmed binding is never demoted to ``pending``: a failed patch of an
    existing card is a failed *projection*, not a lost card, and forgetting the
    binding is how a recovery ends up creating a second one.
    """

    _member(state, CARD_SINK_STATES)
    if state == "pending" and projection.card_message_id is not None:
        raise _conflict()
    return replace(
        projection,
        card_sink_state=state,
        degraded_notice=(
            projection.degraded_notice
            if degraded_notice is None
            else _bool(degraded_notice)
        ),
    )


def derive_session_ref(session_id: Any) -> str | None:
    """The safe comparable handle for one ARS Session, or ``None``.

    ARS Session ids are opaque foreign tokens. What the card layer needs is not
    the id but the *question* "is this the same Session as last round", so a
    stable digest answers it exactly while the raw token stays where it already
    lives — in the private binding ledger. The handle is evidence, never a
    rendered value.
    """

    if type(session_id) is not str or not session_id:
        return None
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:8]
    return "sess_" + digest


def _ordered_rounds(earlier_rounds: Any) -> tuple[DelegateCardRound, ...]:
    """The earlier rounds this layer will read as evidence, and nothing else.

    A malformed history is not an error here: evidence that cannot be read is
    absent evidence, and absent evidence is answered by refusing the claim
    rather than by refusing to render the card.
    """

    if type(earlier_rounds) not in (tuple, list):
        return ()
    return tuple(row for row in earlier_rounds if type(row) is DelegateCardRound)


def _recorded_session(earlier_rounds: Any) -> bool:
    """Whether any earlier round of this Task recorded an ARS Session at all.

    "This Task had no earlier round" and "its earlier rounds recorded no
    Session" are the same fact for a create: neither is a Session this round
    could have been served instead of creating one.
    """

    return any(row.session_ref is not None for row in _ordered_rounds(earlier_rounds))


def _creation_anchor(
    earlier_rounds: Any, *, session_ref: Any, run_ref: Any
) -> DelegateCardRound | None:
    """The round of this Task that canonically created this Session, if any.

    The whole ordered history is searched, not the row immediately behind:
    ``created → loaded → loaded`` is one Session used three times, and the
    second load's evidence is still round one's create. Reading only the
    previous row is what lets a *pair of loads* look like a reuse, because each
    load is only ever compared with another claim of the same kind.

    An anchor has to be complete. It recorded the create, on this same Session,
    under a Run identity of its own that is not this round's — one Run cannot
    prove reuse across two rounds — and its round actually ended, because a
    create still in flight has not yet proven a Session exists to be reused.
    """

    if session_ref is None or run_ref is None:
        return None
    for row in _ordered_rounds(earlier_rounds):
        if (
            row.session_origin == "created"
            and row.session_ref == session_ref
            and row.run_ref is not None
            and row.run_ref != run_ref
            and row.settled
        ):
            return row
    return None


def project_session_evidence(
    *,
    earlier_rounds: Any = (),
    session_ref: Any,
    run_ref: Any,
    session_origin: Any,
    settled: bool = True,
) -> str:
    """The one Session conclusion trusted evidence supports, and no more.

    ``reused`` requires all of it: one Task, one *same* ARS Session identity,
    two *different* Run identities, a settled earlier round that recorded the
    create, and a recorded load now that has itself settled. The create is
    traced across the Task's ordered rounds rather than read off the row behind,
    because that row is itself a load from the second continuation onward — and
    two loads with nothing that created the Session prove only that this host
    was told "loaded" twice.

    Equal task refs, similar text, model recall, and a successful response prove
    none of it, so anything short of the full set is ``unconfirmed`` — or, while
    the round is still running, ``pending``.
    """

    if session_origin == "created" and not _recorded_session(earlier_rounds):
        return "new"
    if not settled:
        return "pending"
    if (
        session_origin == "loaded"
        and _creation_anchor(earlier_rounds, session_ref=session_ref, run_ref=run_ref)
        is not None
    ):
        return "reused"
    return "unconfirmed"


# --------------------------------------------------------------------------- #
# Localization
# --------------------------------------------------------------------------- #
_TITLE_PREFIX = {"zh": "委派任务", "en": "Delegated Task"}
_TITLE_SEPARATOR = " · "

_TASKLESS_TITLE_STATE = {
    "zh": {"created": "已创建", "waiting": "等待执行槽位"},
    "en": {"created": "Created", "waiting": "Waiting for Execution Slot"},
}

_ROUND_TITLE_STATE = {
    "zh": {
        "submitting": "提交中",
        "rejected": "未受理",
        "accepted": "已受理",
        "running": "执行中",
        "recovering": "状态待恢复",
        "completed": "已完成",
        "failed": "已失败",
        "cancelled": "已取消",
    },
    "en": {
        "submitting": "Submitting",
        "rejected": "Not Admitted",
        "accepted": "Admitted",
        "running": "Running",
        "recovering": "Recovery Pending",
        "completed": "Completed",
        "failed": "Failed",
        "cancelled": "Cancelled",
    },
}

_FIELD_LABELS = {
    "zh": ("任务", "编号", "耗时", "执行", "角色"),
    "en": ("Task", "ID", "Duration", "Execution", "Role"),
}
_FIELD_EMOJI = ("💡", "🆔", "⏱️", "🤖", "👤")
#: A Chinese card uses a full-width colon and exactly one following space; an
#: English card an ASCII colon and exactly one following space.
_FIELD_SEPARATOR = {"zh": "：", "en": ":"}
#: Round sub-lines are tighter than the five summary fields: a Chinese card
#: writes ``Session：新建`` with no following space, an English card
#: ``Session: New`` with one, which is what the confirmed snapshots show.
_ROUND_SEPARATOR = {"zh": "：", "en": ": "}

_ROLE_FALLBACK = {"zh": "未指定", "en": "Not specified"}
_DESCRIPTION_FALLBACK = {"zh": "未提供", "en": "Not provided"}
#: The one honest "this host does not know" value. It answers a missing
#: duration boundary and an absent execution contract alike: both are facts the
#: card refuses to invent, and inventing two different words for one absence
#: would only suggest they differ.
_UNKNOWN_FALLBACK = {"zh": "未知", "en": "Unknown"}

_HISTORY_HEADER = {"zh": "执行记录", "en": "Execution Log"}
_HISTORY_EMPTY = {"zh": "⏳ 尚未开始", "en": "⏳ Not started"}

_SESSION_LABEL = "Session"
_SESSION_TEXT = {
    "zh": {
        "new": "新建",
        "reused": "已确认复用",
        "pending": "复用状态确认中",
        "unconfirmed": "复用状态未确认",
    },
    "en": {
        "new": "New",
        "reused": "Confirmed reuse",
        "pending": "Reuse pending",
        "unconfirmed": "Reuse unconfirmed",
    },
}

_RESULT_LABEL = {"zh": "结果", "en": "Result"}
_STATUS_LABEL = {"zh": "状态", "en": "Status"}

_ROUND_EMOJI = {
    "submitting": "▶️",
    "accepted": "▶️",
    "running": "▶️",
    "recovering": "▶️",
    "completed": "✅",
    "failed": "❌",
    "cancelled": "🚫",
    "rejected": "⚠️",
}

#: The confirmed native header templates are blue for ``已创建``, yellow for
#: ``执行中``, and green for ``已完成``. Every other state maps onto a template
#: the adapter already uses elsewhere; those choices are implementation details,
#: not new product states.
_HEADER_TEMPLATE = {
    "created": "blue",
    "waiting": "blue",
    "submitting": "blue",
    "accepted": "blue",
    "running": "yellow",
    "recovering": "orange",
    "completed": "green",
    "failed": "red",
    "cancelled": "orange",
    "rejected": "red",
}


def card_state(projection: DelegateCardProjection) -> tuple[str, int | None]:
    """The latest-round state the header projects, and its round number.

    A Task header is a projection of the *latest* round, never an irreversible
    Task terminal: round 1 completing is not the Task closing, and a
    continuation moves the same header forward again.
    """

    latest = projection.latest_round
    if latest is None:
        state = projection.pre_accept_status
        if state in ("created", "waiting"):
            return state, None
        if state in ("submitting", "rejected"):
            # A first turn that failed before its row could be written is still
            # a first round as far as the user is concerned, and saying
            # ``已创建`` about it would be the one untruthful option.
            return state, 1
        return "created", None
    return latest.status, latest.round_number


def card_title(state: str, round_number: int | None, *, locale: str = "zh") -> str:
    """``card type · latest round state`` — the one title form, localized."""

    _member(locale, CARD_LOCALES)
    if round_number is None:
        suffix = _TASKLESS_TITLE_STATE[locale].get(state)
        if suffix is None:
            raise _invalid()
    else:
        _non_negative_int(round_number)
        word = _ROUND_TITLE_STATE[locale].get(state)
        if word is None:
            raise _invalid()
        suffix = (
            f"第 {round_number} 轮{word}"
            if locale == "zh"
            else f"Round {round_number} {word}"
        )
    return _TITLE_PREFIX[locale] + _TITLE_SEPARATOR + suffix


def card_header_template(state: Any) -> str:
    """The Feishu header template one state renders under."""

    template = _HEADER_TEMPLATE.get(state)
    if template is None:
        raise _invalid()
    return template


# --------------------------------------------------------------------------- #
# Duration — persisted boundaries only
# --------------------------------------------------------------------------- #
def _duration_boundaries(
    projection: DelegateCardProjection,
) -> tuple[datetime | None, datetime | None]:
    start = _parse_instant(projection.task_created_at)
    latest = projection.latest_round
    if latest is not None and latest.settled:
        return start, _parse_instant(latest.settled_at)
    if latest is None and projection.last_projected_at is None:
        # Allocation-time snapshot: the Task's start *is* its current instant.
        return start, start
    return start, _parse_instant(projection.last_projected_at)


def _format_duration(seconds: int, locale: str) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, second = divmod(remainder, 60)
    if locale == "zh":
        if hours:
            return f"{hours}小时{minutes}分{second}秒"
        if minutes:
            return f"{minutes}分{second}秒"
        return f"{second}秒"
    if hours:
        return f"{hours}h {minutes}m {second}s"
    if minutes:
        return f"{minutes}m {second}s"
    return f"{second}s"


def _rendered_duration(projection: DelegateCardProjection) -> str:
    start, end = _duration_boundaries(projection)
    if start is None or end is None:
        return _UNKNOWN_FALLBACK[projection.locale]
    seconds = int((end - start).total_seconds())
    if seconds < 0:
        # Two boundaries that cannot both be true. "We do not know" is the only
        # honest answer; a clamped zero would assert a duration nobody observed.
        return _UNKNOWN_FALLBACK[projection.locale]
    return _format_duration(seconds, projection.locale)


def _execution_label(projection: DelegateCardProjection) -> str:
    parts = [
        part for part in (projection.agent_id, projection.model, projection.effort) if part
    ]
    return " · ".join(parts) if parts else _UNKNOWN_FALLBACK[projection.locale]


def _admitted_role(projection: DelegateCardProjection) -> str:
    """The role sealed into the round this card is currently projecting.

    Scanning back to an earlier round would be the one thing the contract
    forbids: a continuation admitted by direct AGENT selection holds no role,
    and re-showing the role a *previous* round was admitted under would present
    admission evidence this round does not have.
    """

    latest = projection.latest_round
    if latest is not None and latest.admitted_role:
        return latest.admitted_role
    return _ROLE_FALLBACK[projection.locale]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _summary_lines(projection: DelegateCardProjection) -> list[str]:
    locale = projection.locale
    separator = _FIELD_SEPARATOR[locale] + " "
    values = (
        projection.task_description or _DESCRIPTION_FALLBACK[locale],
        projection.task_ref,
        _rendered_duration(projection),
        _execution_label(projection),
        _admitted_role(projection),
    )
    return [
        f"{emoji} {label}{separator}{value}"
        for emoji, label, value in zip(_FIELD_EMOJI, _FIELD_LABELS[locale], values)
    ]


def _round_block(row: DelegateCardRound, locale: str) -> list[str]:
    separator = _ROUND_SEPARATOR[locale]
    emoji = _ROUND_EMOJI[row.status]
    if locale == "zh":
        heading = f"{emoji} 第 {row.round_number} 轮"
    else:
        heading = f"{emoji} Round {row.round_number}"
    if row.purpose:
        heading = f"{heading}{separator}{row.purpose}"
    lines = [heading]

    session_text = _SESSION_TEXT[locale].get(row.session_projection)
    if session_text is not None:
        lines.append(f"{_SESSION_LABEL}{separator}{session_text}")

    if row.settled:
        detail = row.result_summary or _ROUND_TITLE_STATE[locale][row.status]
        lines.append(f"{_RESULT_LABEL[locale]}{separator}{detail}")
    else:
        lines.append(
            f"{_STATUS_LABEL[locale]}{separator}"
            f"{_ROUND_TITLE_STATE[locale][row.status]}"
        )
    return lines


def _history_lines(projection: DelegateCardProjection, window: int) -> list[str]:
    locale = projection.locale
    lines = [_HISTORY_HEADER[locale]]
    if not projection.rounds:
        lines.append(_HISTORY_EMPTY[locale])
        return lines

    visible = projection.rounds[-window:] if window > 0 else ()
    hidden = len(projection.rounds) - len(visible)
    if hidden > 0:
        if locale == "zh":
            lines.append(f"另有 {hidden} 轮")
        else:
            lines.append(f"{hidden} more round" + ("s" if hidden != 1 else ""))
    for index, row in enumerate(visible):
        if index or hidden > 0:
            lines.append("")
        lines.extend(_round_block(row, locale))
    return lines


def _card_body(projection: DelegateCardProjection, window: int) -> str:
    """Everything below the header title, as one markdown block."""

    return "\n".join(
        _summary_lines(projection) + [""] + _history_lines(projection, window)
    )


def render_delegation_card(
    projection: DelegateCardProjection, *, window: int = CARD_ROUND_WINDOW
) -> dict[str, Any]:
    """One bounded, sanitized native Feishu card built from persisted state.

    Read-only by construction: the first slice emits no action element at all,
    so there is no button a stale round could carry.
    """

    if type(projection) is not DelegateCardProjection:
        raise _invalid()
    state, round_number = card_state(projection)
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": card_title(
                    state, round_number, locale=projection.locale
                ),
            },
            "template": card_header_template(state),
        },
        "elements": [
            {"tag": "markdown", "content": _card_body(projection, window)},
        ],
    }


def render_delegation_markdown(
    projection: DelegateCardProjection, *, window: int = CARD_ROUND_WINDOW
) -> str:
    """The compact Markdown fallback: the same card, as one plain block.

    Same wording, order, punctuation, duration semantics, and no-bullet layout
    as the native card — this is what a user sees when rich delivery failed, so
    it has to carry the complete copyable ``dtask_*`` too.
    """

    if type(projection) is not DelegateCardProjection:
        raise _invalid()
    state, round_number = card_state(projection)
    title = card_title(state, round_number, locale=projection.locale)
    return title + "\n\n" + _card_body(projection, window)


def bounded_card_payload(
    projection: DelegateCardProjection,
    *,
    limit: int,
    measure: Callable[[str], int] = len,
) -> tuple[dict[str, Any] | None, str]:
    """The largest card that fits, and the fallback that is always available.

    The bound is the adapter's own one-message limit, applied to the exact
    serialized string the SDK request body carries — the same value the delegate
    delivery already reads from ``single_message_text_limit()``. Compaction runs
    *before* the adapter call and fails closed: rows are dropped first, and a
    card that still does not fit is refused outright rather than sent for the
    API to reject. API rejection is not control flow.
    """

    if type(projection) is not DelegateCardProjection:
        raise _invalid()
    if isinstance(limit, bool) or type(limit) is not int or limit < 1:
        raise _invalid()

    fallback = render_delegation_markdown(projection)
    for window in range(CARD_ROUND_WINDOW, -1, -1):
        card = render_delegation_card(projection, window=window)
        payload = json.dumps(card, ensure_ascii=False)
        if measure(payload) <= limit:
            return card, fallback
    return None, fallback
