"""Sachima ``/delegate [@AGENT] <task>`` — platform-neutral selector parsing.

``@AGENT`` is product notation for a **platform-native structured mention
occurrence**, not a new textual ``@name`` language and not a profile-id parser.
This module owns exactly one decision and nothing else: given the final message
text and the neutral :class:`~gateway.platforms.base.MentionOccurrence` list an
adapter supplied, does the command carry a *verified* explicit AGENT selector,
and what is the task text once the qualifying occurrence is removed?

The rules are the invariant, restated as code:

* only the occurrence that starts **immediately after** ``/delegate`` can
  select. Later mentions — including a second mention of the same display name
  — stay part of the task verbatim;
* identity is the adapter's stable platform user id. A rendered display name is
  presentation and is never read as identity;
* a leading selection-shaped ``@name`` with no matching structured occurrence is
  an **unverified selector**: it refuses. It never falls through to automatic
  routing, because "we could not verify who you meant" and "you did not name
  anyone" are different statements;
* a self mention or ``@all`` never selects. They are verified occurrences that
  simply are not AGENT selectors, so they stay in the task and the request routes
  automatically.

Pure local/offline text handling: this module opens nothing, sends nothing,
resolves no profile, and touches no Session, ledger, or durable state. Whether a
selected identity maps to an available AGENT is the routing policy's question,
asked next.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

__all__ = [
    "SACHIMA_DELEGATE_SELECTOR_STABLE_CODES",
    "SACHIMA_DELEGATE_UNVERIFIED_SELECTOR",
    "DelegateSelection",
    "parse_delegate_selection",
]

#: The one refusal this module can produce. A selection-shaped leading token
#: that no structured occurrence backs cannot be resolved to an identity, and
#: guessing from the rendered name is exactly what the invariant forbids.
SACHIMA_DELEGATE_UNVERIFIED_SELECTOR = "sachima_delegate_unverified_selector"

SACHIMA_DELEGATE_SELECTOR_STABLE_CODES = frozenset(
    {SACHIMA_DELEGATE_UNVERIFIED_SELECTOR}
)

#: What a *selection-shaped* leading token looks like. Deliberately shape-only:
#: matching it proves nothing about identity, it only tells the parser that the
#: user was trying to name someone, so silence would be the wrong answer.
_SELECTOR_SHAPE_RE = re.compile(r"@[^\s@]+")

#: The command word this parser understands. There is exactly one.
_COMMAND = "delegate"


@dataclass(frozen=True)
class DelegateSelection:
    """One parse: the task text plus at most one verified selector or refusal.

    Exactly one of the three states holds. ``refusal`` set means neither of the
    others is usable; ``platform_user_id`` set means an occurrence was verified;
    both unset means no selector was present and routing is automatic.
    """

    task_text: str
    platform_user_id: str | None = None
    refusal: str | None = None

    @property
    def refused(self) -> bool:
        return self.refusal is not None

    @property
    def has_selector(self) -> bool:
        return self.platform_user_id is not None


def _command_args_start(text: str) -> int | None:
    """Index just past ``/delegate`` in ``text``, or ``None`` if absent.

    Computed on the raw text rather than taken from ``get_command_args()``
    because occurrence coordinates are indices into *this* string: a re-derived
    argument copy has no positions to align to.
    """

    if type(text) is not str or not text.startswith("/"):
        return None
    index = 1
    while index < len(text) and not text[index].isspace():
        index += 1
    word = text[1:index]
    # Platform suffixes (``/delegate@bot``) resolve to the same command.
    if "@" in word:
        word = word.split("@", 1)[0]
    if word.lower() != _COMMAND:
        return None
    return index


def _leading_occurrence(
    occurrences: Sequence[Any], cursor: int
) -> Any | None:
    for occurrence in occurrences or ():
        if getattr(occurrence, "start", None) == cursor:
            return occurrence
    return None


def parse_delegate_selection(
    text: Any, occurrences: Sequence[Any] = ()
) -> DelegateSelection:
    """Parse ``/delegate [@AGENT] <task>`` into a selection decision.

    ``text`` is the **final** message text, and ``occurrences`` are positioned
    against that same string; an occurrence whose coordinates no longer describe
    what it says they describe is discarded rather than trusted, so a stale or
    forged position can never select an AGENT.
    """

    if type(text) is not str:
        return DelegateSelection(task_text="")
    start = _command_args_start(text)
    if start is None:
        return DelegateSelection(task_text="")

    verified = tuple(
        occurrence
        for occurrence in (occurrences or ())
        if _is_usable_occurrence(occurrence, text)
    )

    cursor = start
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1

    occurrence = _leading_occurrence(verified, cursor)
    if occurrence is not None:
        if occurrence.is_self or occurrence.is_all:
            # Verified, but never a selector: it stays in the task and the
            # request routes automatically.
            return DelegateSelection(task_text=text[cursor:].strip())
        identity = occurrence.platform_user_id
        if type(identity) is not str or not identity.strip():
            return DelegateSelection(
                task_text="", refusal=SACHIMA_DELEGATE_UNVERIFIED_SELECTOR
            )
        # Only the qualifying occurrence is removed. Everything after it —
        # including another mention of the same display name — is task text.
        return DelegateSelection(
            task_text=text[occurrence.end :].strip(),
            platform_user_id=identity.strip(),
        )

    shaped = _SELECTOR_SHAPE_RE.match(text, cursor)
    if shaped is not None:
        return DelegateSelection(
            task_text="", refusal=SACHIMA_DELEGATE_UNVERIFIED_SELECTOR
        )
    return DelegateSelection(task_text=text[cursor:].strip())


def _is_usable_occurrence(occurrence: Any, text: str) -> bool:
    try:
        return bool(occurrence.matches_text(text))
    except AttributeError:
        return False
