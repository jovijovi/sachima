"""One conversation, one rule — across a context-compression split.

Context compression ends the live Session and forks a continuation child with a
new physical ``session_id``. Everything the Gateway binds to a conversation by
that id — the delegate control grant, the result a finished external AGENT owes
the next ordinary turn — would otherwise be cut off by a split the user never
asked for and cannot see.

This module is the **only** place that answers "is this still the same
conversation?", and it answers it in exactly two ways:

1. the ids are the same Session, or
2. the persisted Session lineage proves, hop by hop, that the current Session is
   a *compression continuation* of the one on the record — and the record's
   platform, chat, thread, and Session key still match the caller's.

Both halves are required for (2). The lineage half is
:meth:`hermes_state.SessionDB.is_compression_continuation`, which only counts a
parent → child edge when the parent ended with ``end_reason='compression'`` and
the child started at or after that: ``/new``, auto-reset, ``/branch`` children,
and delegate subagent runs never satisfy it. The identity half is what stops a
proven-but-relocated Session from carrying a grant into a different chat.

What this module deliberately does not do, because each would turn a narrow
continuity rule into a wide one:

* it never admits an arbitrary descendant, only a proven continuation chain;
* it never admits on the Session *key* alone — a key outlives ``/new``;
* it never walks backwards: a parent does not inherit its continuation's work;
* it never falls back to ``os.environ``, retries, or reconstructs a Session that
  the store and the persisted lineage do not agree on;
* it never rewrites a stored ``session_id``. The original stays as persisted,
  which is what keeps old records auditable.

Consumers hold a :class:`TrustedSession` and ask it ``claims(origin)``. There is
no second copy of the rule in the control surface or in result re-injection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


def _text(value: Any) -> str:
    """A comparable string, or ``""`` — never a repr of something else."""

    if type(value) is str:
        return value
    if value is None:
        return ""
    inner = getattr(value, "value", None)
    return inner if type(inner) is str else ""


def _optional_text(value: Any) -> str:
    """``None`` and ``""`` are the same absent thread, and must compare equal.

    Routing ids reach here as the host's own type on one side (an ``int`` thread
    id, say) and as the text the record persisted on the other, so both are
    compared as text.
    """

    if value is None:
        return ""
    if type(value) is str:
        return value
    return _text(value) or str(value)


@dataclass(frozen=True)
class TrustedSession:
    """The caller's live conversation, resolved from trusted Gateway context.

    ``session_id`` is the Session this turn is actually on — normally the store
    entry's own, and during a compression split the continuation the agent
    worker already rotated onto, once the persisted lineage has proven it.
    ``entry`` stays the Gateway's own record, so the platform, chat, thread, and
    Session key all keep coming from the host rather than from a caller.
    """

    entry: Any
    session_id: str
    session_db: Any = None

    @property
    def session_key(self) -> str:
        return _text(getattr(self.entry, "session_key", ""))

    @property
    def platform(self) -> str:
        return _text(getattr(getattr(self.entry, "origin", None), "platform", None))

    @property
    def chat_id(self) -> str:
        source = getattr(self.entry, "origin", None)
        return _optional_text(getattr(source, "chat_id", None))

    @property
    def thread_id(self) -> str:
        source = getattr(self.entry, "origin", None)
        return _optional_text(getattr(source, "thread_id", None))

    def claims(self, origin: Any) -> bool:
        """May this turn act on something recorded against *origin*?

        Exact Session first, and unchanged: a record bound to the Session this
        turn is on belongs to it, whatever else the record does or does not
        carry. Only the continuation path adds conditions, and it adds all of
        them — same platform, chat, thread, and Session key, plus a persisted
        per-hop compression chain from the record's Session to this one.
        """

        if origin is None:
            return False
        recorded = _text(getattr(origin, "session_id", ""))
        if not recorded:
            return False
        if recorded == self.session_id:
            return True
        if not self._same_conversation(origin):
            return False
        return self._continues(recorded)

    # -- the two halves ----------------------------------------------------- #
    def _same_conversation(self, origin: Any) -> bool:
        """The routing identity a continuation must still match, exactly."""

        return (
            _text(getattr(origin, "platform", "")) == self.platform
            and _optional_text(getattr(origin, "chat_id", None)) == self.chat_id
            and _optional_text(getattr(origin, "thread_id", None)) == self.thread_id
            and _text(getattr(origin, "session_key", "")) == self.session_key
        )

    def _continues(self, recorded_session_id: str) -> bool:
        """Persisted, per-hop proof that this Session continues *recorded*."""

        return is_compression_continuation(
            self.session_db,
            ancestor_session_id=recorded_session_id,
            descendant_session_id=self.session_id,
        )


def is_compression_continuation(
    session_db: Any, *, ancestor_session_id: str, descendant_session_id: str
) -> bool:
    """The lineage half, fail-closed when there is nothing to read it from."""

    if session_db is None or not ancestor_session_id or not descendant_session_id:
        return False
    try:
        return bool(
            session_db.is_compression_continuation(
                ancestor_session_id=ancestor_session_id,
                descendant_session_id=descendant_session_id,
            )
        )
    except Exception:
        logger.debug("session lineage read failed", exc_info=True)
        return False


def resolve_trusted_session(
    store: Any, *, session_id: str = "", session_key: str = ""
) -> TrustedSession | None:
    """The caller's own Session, from trusted Gateway context only.

    The id and the key both come from the host. The exact paths are the ones
    that already existed: resolve the id, or fall back to the key for a caller
    that only ever had one, and refuse when the two disagree.

    What is new is the one window where they *legitimately* disagree. Context
    compression rotates the Session on the agent worker thread, mid-Run; the
    Gateway propagates the new id onto its ``SessionEntry`` only after that Run
    returns. In between, the contextvar names the continuation and the store
    still names the parent, and a control action in that window used to find no
    Session at all. It is admitted here only when the persisted lineage proves
    the contextvar's Session is a compression continuation of *this entry's own*
    Session — not because the key matched, not on a retry, and not from a
    process-global fallback. When it is admitted, the continuation leads: it is
    the Session the conversation is actually on.
    """

    if store is None:
        return None
    session_id = (session_id or "").strip()
    session_key = (session_key or "").strip()
    try:
        entry = store.lookup_by_session_id(session_id) if session_id else None
        if entry is None and session_key:
            entry = store.lookup_by_session_key(session_key)
    except Exception:
        logger.debug("trusted session lookup failed", exc_info=True)
        return None
    if entry is None:
        return None
    if session_key and _text(getattr(entry, "session_key", "")) != session_key:
        return None

    session_db = getattr(store, "session_db", None)
    entry_session_id = _text(getattr(entry, "session_id", ""))
    if not session_id or session_id == entry_session_id:
        return TrustedSession(
            entry=entry, session_id=entry_session_id, session_db=session_db
        )
    if not is_compression_continuation(
        session_db,
        ancestor_session_id=entry_session_id,
        descendant_session_id=session_id,
    ):
        return None
    return TrustedSession(entry=entry, session_id=session_id, session_db=session_db)
