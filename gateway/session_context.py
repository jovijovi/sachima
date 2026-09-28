"""Session-scoped context variables for the Hermes gateway.

Replaces the old ``os.environ``-based ``HERMES_SESSION_*`` state with task-local ``ContextVar``s
(inherited by ``run_in_executor`` threads), so concurrently handled messages no longer clobber each
other's routing ids.  ``get_session_env`` is a drop-in for ``os.getenv``.
"""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator

# "Never set here" (falls back to os.environ for CLI/cron) vs "" = explicitly cleared (no fallback).
_UNSET: Any = object()

# Process-level latch: has set_session_vars() ever bound a session?  When engaged, the subprocess
# env bridge treats ContextVars as authoritative and an _UNSET var as "no session in THIS task".
_session_context_engaged: bool = False


def session_context_engaged() -> bool:
    """True if any session has been bound via set_session_vars in this process."""
    return _session_context_engaged


# --- Per-task session variables: bound by set_session_vars / cleared to "" by clear_session_vars;
# tuple ORDER is the positional order of ``values`` in set_session_vars (zipped).
# * SCOPE_ID: platform-neutral scope (guild / workspace / Matrix server) so async producers can
#   persist a completion's full routing origin (relay egress guards need it).
# * UI_SESSION_ID: in-process UI tab id, separate from the durable SESSION_ID, so a stale/rotated
#   durable key is not consumed by the wrong poller.
# * MESSAGE_ID: reply anchor keeping notifications inside the originating Telegram topic.
# * CRON_SESSION: tri-state — _UNSET = legacy env fallback; "1" = cron; "" = non-cron, masks env.
_SESSION_VARS = (
    _SESSION_PLATFORM, _SESSION_SOURCE, _SESSION_CHAT_ID, _SESSION_CHAT_TYPE,
    _SESSION_CHAT_NAME, _SESSION_THREAD_ID, _SESSION_USER_ID, _SESSION_USER_ID_ALT,
    _SESSION_USER_NAME, _SESSION_SCOPE_ID, _SESSION_KEY, _SESSION_ID,
    _SESSION_UI_SESSION_ID, _SESSION_MESSAGE_ID, _SESSION_PROFILE,
    _BROWSER_CONTROL_PRINCIPAL, _BROWSER_CONTROL_TRANSPORT_FAMILY, _CRON_SESSION, _SESSION_PARENT_CHAT_ID,
) = tuple(ContextVar(name, default=_UNSET) for name in (
    "HERMES_SESSION_PLATFORM", "HERMES_SESSION_SOURCE", "HERMES_SESSION_CHAT_ID",
    "HERMES_SESSION_CHAT_TYPE", "HERMES_SESSION_CHAT_NAME", "HERMES_SESSION_THREAD_ID",
    "HERMES_SESSION_USER_ID", "HERMES_SESSION_USER_ID_ALT", "HERMES_SESSION_USER_NAME",
    "HERMES_SESSION_SCOPE_ID", "HERMES_SESSION_KEY", "HERMES_SESSION_ID",
    "HERMES_UI_SESSION_ID", "HERMES_SESSION_MESSAGE_ID", "HERMES_SESSION_PROFILE",
    "HERMES_BROWSER_CONTROL_PRINCIPAL", "HERMES_BROWSER_CONTROL_TRANSPORT_FAMILY",
    "HERMES_CRON_SESSION", "HERMES_SESSION_PARENT_CHAT_ID",
))

# Whether this channel can route an ASYNC completion back AFTER the turn ends (see
# ``async_delivery_supported()``).  _UNSET => supported (CLI, contextvar-unaware paths); stateless
# adapters (API server, Kanban workers) opt OUT via ``supports_async_delivery = False`` at bind.
_SESSION_ASYNC_DELIVERY = ContextVar("HERMES_SESSION_ASYNC_DELIVERY", default=_UNSET)

# Request-local proof that the client resumes SessionDB history. No env fallback
# or child-process export: a bound id alone cannot authorize detached delivery.
_SESSION_HISTORY_DELIVERY = ContextVar("HERMES_SESSION_HISTORY_DELIVERY", default=_UNSET)

# Host-set turn provenance used by authorization-sensitive internal controls.
# Deliberately not in _VAR_MAP and with no os.environ fallback: a process
# environment value must never make a synthetic event look natural.
_SESSION_INPUT_INTERNAL: ContextVar = ContextVar("hermes_session_input_internal", default=_UNSET)

# Cron auto-delivery vars, set per-job in run_job() so concurrent jobs don't clobber.
_CRON_AUTO_DELIVER_PLATFORM = ContextVar("HERMES_CRON_AUTO_DELIVER_PLATFORM", default=_UNSET)
_CRON_AUTO_DELIVER_CHAT_ID = ContextVar("HERMES_CRON_AUTO_DELIVER_CHAT_ID", default=_UNSET)
_CRON_AUTO_DELIVER_THREAD_ID = ContextVar("HERMES_CRON_AUTO_DELIVER_THREAD_ID", default=_UNSET)

# Legacy env-var name -> ContextVar for get_session_env (_SESSION_ASYNC_DELIVERY deliberately
# absent: it is a bool capability, read via async_delivery_supported).
_VAR_MAP = {var.name: var for var in (
    *_SESSION_VARS, _CRON_AUTO_DELIVER_PLATFORM, _CRON_AUTO_DELIVER_CHAT_ID,
    _CRON_AUTO_DELIVER_THREAD_ID,
)}


def _runtime_cwd(func: str, *args: Any) -> None:
    """Best-effort call of ``agent.runtime_cwd.<func>``; import/runtime failures are ignored."""
    try:
        from agent import runtime_cwd
        getattr(runtime_cwd, func)(*args)
    except Exception:
        pass


def set_current_session_id(session_id: str) -> None:
    """Synchronize ``HERMES_SESSION_ID`` across ContextVar and ``os.environ`` (tools read it
    with an os.environ fallback).  Delegated subagent children (built in the parent process)
    get ONLY the task-local write, or they would clobber the parent's id."""
    _SESSION_ID.set(session_id)
    try:
        from agent.delegation_context import is_delegated_child_context
        if is_delegated_child_context():
            return
    except Exception:
        pass
    os.environ["HERMES_SESSION_ID"] = session_id


@contextmanager
def scoped_current_session_id(session_id: str | None = None) -> Iterator[None]:
    """Bind a task-local session id and restore the prior value on exit; never touches
    ``os.environ``.  ``session_id=None`` is a pure save/restore boundary."""
    previous = _SESSION_ID.get()
    if session_id is not None:
        _SESSION_ID.set(session_id)
    try:
        yield
    finally:
        _SESSION_ID.set(previous)


def source_route_metadata(source: Any, metadata: dict | None) -> dict | None:
    """Keep inbound route anchors for durable deliveries after the source is gone."""
    anchors = {key: str(value) for key in ("scope_id", "parent_chat_id")
               if (value := getattr(source, key, None))}
    return {**(metadata or {}), **anchors} if anchors else metadata


def set_session_vars(
    platform: str = "", source: str = "", chat_id: str = "", chat_type: str = "",
    chat_name: str = "", thread_id: str = "", user_id: str = "", user_id_alt: str = "",
    user_name: str = "", scope_id: str = "", session_key: str = "", session_id: str = "",
    message_id: str = "", profile: str = "", browser_control_principal: str = "",
    browser_control_transport_family: str = "", cwd: str = "", async_delivery: bool = True,
    ui_session_id: str = "", cron_session: Any = _UNSET, parent_chat_id: str = "",
    session_history_delivery: str | None = None, input_internal: bool = False,
) -> list:
    """Set all session context variables and return reset tokens.  Call
    ``clear_session_vars(tokens)`` in a ``finally``; not nestable, clearing resets every var
    to ``""`` rather than restoring prior values (tokens are accepted only for API compat).

    ``session_history_delivery`` declares whether the bound chat id is one the client can address again:
    ``"1"`` (audited producers — explicit session-id header, native API sessions, /v1/runs) or
    ``""`` / omitted (default-deny, #98619).  ``None`` leaves the var at ``_UNSET`` ("never
    declared"), which ``session_history_delivery_supported()`` treats as NOT capable — an omitted declaration
    cannot grant wake authority.

    ``input_internal`` is private host provenance for this turn. It has no
    process-environment fallback and is not included in provider context."""
    global _session_context_engaged
    _session_context_engaged = True
    values = (
        platform, source, chat_id, chat_type, chat_name, thread_id, user_id, user_id_alt,
        user_name, scope_id, session_key, session_id, ui_session_id, message_id, profile,
        browser_control_principal, browser_control_transport_family, cron_session, parent_chat_id,
    )
    tokens = [var.set(value) for var, value in zip(_SESSION_VARS, values)]
    tokens.append(_SESSION_ASYNC_DELIVERY.set(bool(async_delivery)))
    tokens.append(_SESSION_HISTORY_DELIVERY.set(_UNSET if session_history_delivery is None else session_history_delivery))
    tokens.append(_SESSION_INPUT_INTERNAL.set(input_internal is True))
    _runtime_cwd("set_session_cwd", cwd)
    return tokens


def clear_session_vars(tokens: list) -> None:
    """Mark session context variables as explicitly cleared (``""``, not ``_UNSET``), so
    ``get_session_env`` returns empty instead of stale ``os.environ`` values.  Async-delivery
    goes back to ``_UNSET``: a cleared context is default-supported, not opted-out.  Wake
    capability goes back to ``_UNSET`` too — but for the opposite reason: a cleared context has
    declared nothing, and an undeclared capability FAILS CLOSED (#98619)."""
    for var in _SESSION_VARS:
        var.set("")
    _SESSION_ASYNC_DELIVERY.set(_UNSET)
    _SESSION_HISTORY_DELIVERY.set(_UNSET)
    _SESSION_INPUT_INTERNAL.set(False)
    _runtime_cwd("clear_session_cwd")


def reset_session_vars() -> None:
    """Reset every session var to ``_UNSET`` ("never bound here") for THIS context.  Call at
    the top of a fresh task *before* it binds: ``create_task`` snapshots the context, so B's
    task inherits A's already-set vars and a subprocess spawned before B binds would read A's
    identity.  ``_SESSION_ASYNC_DELIVERY`` and ``_SESSION_HISTORY_DELIVERY`` (outside ``_VAR_MAP``)
    are reset explicitly too."""
    for var in _VAR_MAP.values():
        var.set(_UNSET)
    _SESSION_ASYNC_DELIVERY.set(_UNSET)
    _SESSION_HISTORY_DELIVERY.set(_UNSET)
    _SESSION_INPUT_INTERNAL.set(_UNSET)
    _runtime_cwd("clear_session_cwd")


def get_session_env(name: str, default: str = "") -> str:
    """Read a session var by legacy ``HERMES_SESSION_*`` name; drop-in for os.getenv.  The
    ContextVar wins if ever set here (even to ``""``); else ``os.environ``; else *default*."""
    var = _VAR_MAP.get(name)
    if var is not None and (value := var.get()) is not _UNSET:
        return value
    return os.getenv(name, default)


def session_input_is_internal() -> bool:
    """Return host-bound provenance for the currently executing Gateway turn."""

    return _SESSION_INPUT_INTERNAL.get() is True


# ---------------------------------------------------------------------------
# Trusted Session resolution across a compression split
# ---------------------------------------------------------------------------
# The vars above answer "what Session is this turn on".  Context compression
# ends the live Session mid-Run and forks a continuation child with a new
# physical ``session_id``, which splits that answer in two for one window: the
# agent worker has already moved ``set_current_session_id`` onto the child,
# while the gateway propagates the new id onto its ``SessionEntry`` only after
# the Run returns.  Anything the gateway binds to a conversation by physical id
# is cut off in that window by a split the user never asked for and cannot see.
#
# The rule below is the *only* place that answers "is this still the same
# conversation?", and it answers it in exactly two ways:
#
#   1. the ids are the same Session, or
#   2. the persisted Session lineage proves, hop by hop, that the current
#      Session is a compression continuation of the one on the record — and the
#      record's platform, chat, thread, and Session key still match the caller's.
#
# Both halves are required for (2).  The lineage half is
# ``hermes_state.SessionDB.is_compression_continuation`` (Sachima's own method,
# hosted on ``hermes_state_compression.SessionCompressionMixin``); the identity
# half is what stops a proven-but-relocated Session from carrying a grant into
# a different chat.
#
# What this deliberately does not do, because each would turn a narrow
# continuity rule into a wide one: it never admits an arbitrary descendant, only
# a proven continuation chain; it never admits on the Session *key* alone (a key
# outlives ``/new``); it never walks backwards, so a parent does not inherit its
# continuation's work; it never falls back to ``os.environ``, retries, or
# reconstructs a Session the store and the persisted lineage do not agree on;
# and it never rewrites a stored ``session_id``, which is what keeps old records
# auditable.


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


def _session_lineage(store: Any) -> Any:
    """The persisted lineage reader behind a ``SessionStore``, or ``None``.

    ``SessionStore`` resolves its handle per active profile scope through the
    private ``_db`` property; ``session_db`` is accepted too so a caller that
    owns a plain reader can pass one without a store.  Absent either, the
    lineage half has nothing to read and every continuation fails closed.
    """

    for name in ("session_db", "_db"):
        try:
            source = getattr(store, name, None)
        except Exception:
            _continuity_logger().debug("session lineage handle failed", exc_info=True)
            return None
        if source is not None:
            return source
    return None


def _continuity_logger():
    import logging

    return logging.getLogger(__name__)


@dataclass(frozen=True)
class TrustedSession:
    """The caller's live conversation, resolved from trusted gateway context.

    ``session_id`` is the Session this turn is actually on — normally the store
    entry's own, and during a compression split the continuation the agent
    worker already rotated onto, once the persisted lineage has proven it.
    ``entry`` stays the gateway's own record, so the platform, chat, thread, and
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
        return is_compression_continuation(
            self.session_db,
            ancestor_session_id=recorded,
            descendant_session_id=self.session_id,
        )

    def _same_conversation(self, origin: Any) -> bool:
        """The routing identity a continuation must still match, exactly."""

        return (
            _text(getattr(origin, "platform", "")) == self.platform
            and _optional_text(getattr(origin, "chat_id", None)) == self.chat_id
            and _optional_text(getattr(origin, "thread_id", None)) == self.thread_id
            and _text(getattr(origin, "session_key", "")) == self.session_key
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
        _continuity_logger().debug("session lineage read failed", exc_info=True)
        return False


def resolve_trusted_session(
    store: Any, *, session_id: str = "", session_key: str = ""
) -> "TrustedSession | None":
    """The caller's own Session, from trusted gateway context only.

    The id and the key both come from the host. The exact paths are the ones
    that already existed: resolve the id, or fall back to the key for a caller
    that only ever had one, and refuse when the two disagree.

    What is new is the one window where they *legitimately* disagree. Context
    compression rotates the Session on the agent worker thread, mid-Run; the
    gateway propagates the new id onto its ``SessionEntry`` only after that Run
    returns. In between, the contextvar names the continuation and the store
    still names the parent, and a lookup in that window used to find no Session
    at all. It is admitted here only when the persisted lineage proves the
    contextvar's Session is a compression continuation of *this entry's own*
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
        _continuity_logger().debug("trusted session lookup failed", exc_info=True)
        return None
    if entry is None:
        return None
    if session_key and _text(getattr(entry, "session_key", "")) != session_key:
        return None

    session_db = _session_lineage(store)
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


# Surfaces that are not a human chat channel (gateway binds HERMES_SESSION_PLATFORM, CLI/TUI/
# desktop bind HERMES_SESSION_SOURCE, so both are consulted).  Default-deny: an unrecognized
# identity counts as messaging.  Mirrors LOCAL_SESSION_SOURCE_IDS in apps/desktop session-source.ts.
NON_MESSAGING_SESSION_SURFACES = frozenset({
    "", "api_server", "cli", "codex", "desktop", "gateway", "kanban", "local",
    "msgraph_webhook", "tool", "tui", "webhook",
})


def session_is_messaging_surface() -> bool:
    """Whether this turn is delivered over a human messaging channel (checks
    ``HERMES_PLATFORM``, then the session platform, then the session source)."""
    platform = os.getenv("HERMES_PLATFORM") or get_session_env("HERMES_SESSION_PLATFORM", "")
    idents = (platform, get_session_env("HERMES_SESSION_SOURCE", ""))
    idents = (str(v or "").strip().lower() for v in idents)
    return any(ident and ident not in NON_MESSAGING_SESSION_SURFACES for ident in idents)


def declare_stateless_channel() -> None:
    """Declare that this session cannot receive an async background completion.  Unlike
    ``set_session_vars(async_delivery=False)`` this does NOT latch ``_session_context_engaged``
    (flipping the subprocess env bridge), which a one-shot CLI must not do as a side effect.

    See NousResearch/hermes-agent#53027 and #63142.
    """
    _SESSION_ASYNC_DELIVERY.set(False)


def async_delivery_supported() -> bool:
    """Whether the current session can deliver a background completion later.  False for
    stateless channels (:func:`declare_stateless_channel`) and Kanban workers
    (``HERMES_KANBAN_TASK``: one-shot subprocesses whose parent disappears after the turn)."""
    if os.environ.get("HERMES_KANBAN_TASK"):
        return False
    value = _SESSION_ASYNC_DELIVERY.get()
    return True if value is _UNSET else bool(value)


def session_history_delivery_supported() -> bool:
    """Whether this request declares a server-history consumer for detached results.

    Fail closed on omitted bindings; never borrow authority from the environment."""
    return _SESSION_HISTORY_DELIVERY.get() == "1"
