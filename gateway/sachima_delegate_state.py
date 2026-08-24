"""Sachima delegation — the durable host state a submission is built on.

Everything a delegated task needs in order to survive one Gateway restart lives
here, and nothing else does. The layer owns five kinds of record:

* **payloads** — the exact task bytes, behind an opaque ``dlg_`` claim-check ref.
  The bytes are durable because a recovery has to rebuild the *identical* frozen
  request, and a process that died holding the only copy in memory could not;
* **task bindings** — one per delegated task: its sealed spine Session, its
  backend handle, the canonical ``agent_id`` it was admitted under, its ordered
  turns, and the link to a prior task when the user switched AGENT;
* **turn records** — one per Run attempt, carrying the immutable identity that
  derives the exact ledger key plus the four orthogonal mutable dimensions
  (lifecycle, cancellation, receipt, observation);
* **result events** — one canonical ``external_agent_result`` per settled
  terminal, with its two independent sink states;
* **full results** — the untruncated agent answer, behind its own claim-check
  ref, so the visible IM body can be bounded without the answer being lost.

Boundaries:

* **Atomic or absent.** Every write is serialize → temp sibling → ``os.replace``,
  fsynced before the swap, so a reader never sees half a record and a crash
  between two records leaves each of them whole.
* **Ordered, not transactional.** There is deliberately no cross-file
  transaction: crash consistency comes from *ordering* (identity before any
  possible submit) plus the ledger's own exact-key classification. A record that
  exists but was never submitted is recoverable; a submit with no record is not,
  which is why the order is the one it is.
* **Private, and derived.** The state directory is a sibling of the already
  private binding-ledger path — the same host-owned boundary, outside the
  tracked repo — so this introduces no new operator path to approve. Directories
  are ``0700`` and files ``0600``.
* **Task text never travels.** It lives in the payload file and is handed back
  to exactly one caller. It is absent from every other record, from every
  ``repr``, from receipts, status answers, envelopes, and logs.
* **Stable failures.** A torn, unreadable, or self-contradictory record raises
  :class:`DelegateStateError` whose message IS the stable code. The damaged
  bytes stay on disk: "we could not read it" is a disposition, not a licence to
  reset.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "CANCELLATION_STATES",
    "DELEGATE_PAYLOAD_REF_PREFIX",
    "DELEGATE_STATE_VERSION",
    "LIFECYCLE_STATES",
    "OBSERVATION_STATES",
    "RECEIPT_STATES",
    "SACHIMA_DELEGATE_STATE_CONFLICT",
    "SACHIMA_DELEGATE_STATE_INVALID",
    "SACHIMA_DELEGATE_STATE_STABLE_CODES",
    "SACHIMA_DELEGATE_STATE_UNREADABLE",
    "SINK_STATES",
    "DelegateCapacity",
    "DelegateOrigin",
    "DelegateResultEvent",
    "DelegateStateError",
    "DelegateStateStore",
    "DelegateTaskBinding",
    "DelegateTurnRecord",
    "delegate_state_root",
]

DELEGATE_STATE_VERSION = 1

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
SACHIMA_DELEGATE_STATE_INVALID = "sachima_delegate_state_invalid"
SACHIMA_DELEGATE_STATE_UNREADABLE = "sachima_delegate_state_unreadable"
SACHIMA_DELEGATE_STATE_CONFLICT = "sachima_delegate_state_conflict"

SACHIMA_DELEGATE_STATE_STABLE_CODES = frozenset(
    {
        SACHIMA_DELEGATE_STATE_INVALID,
        SACHIMA_DELEGATE_STATE_UNREADABLE,
        SACHIMA_DELEGATE_STATE_CONFLICT,
    }
)

#: The four orthogonal mutable dimensions of a turn (plan §5.1).
LIFECYCLE_STATES = (
    "prepared",
    "recovery_required",
    "admitted",
    "terminal",
    "admission_failed",
    "blocked",
)
CANCELLATION_STATES = ("none", "in_flight", "uncertain", "settled")
RECEIPT_STATES = ("pending", "in_flight", "confirmed", "failed", "uncertain")
OBSERVATION_STATES = ("unarmed", "armed", "terminal_seen")
#: The IM sink uses the full delivery vocabulary; the Hermes sink uses the
#: first three only, because a local handoff cannot fail the way a send can.
SINK_STATES = ("pending", "in_flight", "confirmed", "failed", "uncertain")

DELEGATE_PAYLOAD_REF_PREFIX = "dlg_"
_TASK_REF_PREFIX = "dtask_"
_TURN_KEY_PREFIX = "dturn_"
_EVENT_ID_PREFIX = "devt_"
_RESULT_REF_PREFIX = "dres_"

_SAFE_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
#: The canonical ARS ``agent_id`` grammar (see :func:`_safe_agent_id`).
_SAFE_AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_DIR_MODE = 0o700
_FILE_MODE = 0o600
#: A bound on one durable task text. It is the same order as the ARS prompt
#: bound, so a task this layer accepts is one a submit could carry.
_MAX_PAYLOAD_BYTES = 262_144
#: A bound on one stored full result. Larger answers are stored clipped, and the
#: envelope says so — a claim-check that silently held a partial answer would be
#: worse than one that admits it.
_MAX_RESULT_BYTES = 1_048_576


class DelegateStateError(ValueError):
    """A state failure whose message IS the stable code — never the material."""


def _invalid() -> DelegateStateError:
    return DelegateStateError(SACHIMA_DELEGATE_STATE_INVALID)


def _unreadable() -> DelegateStateError:
    return DelegateStateError(SACHIMA_DELEGATE_STATE_UNREADABLE)


def _conflict() -> DelegateStateError:
    return DelegateStateError(SACHIMA_DELEGATE_STATE_CONFLICT)


def _safe_ref(value: Any) -> str:
    if type(value) is not str or _SAFE_REF_RE.fullmatch(value) is None:
        raise _invalid()
    return value


def _optional_ref(value: Any) -> str | None:
    if value is None:
        return None
    return _safe_ref(value)


def _safe_agent_id(value: Any) -> str:
    """The canonical ARS ``agent_id`` sealed into a task.

    Its own grammar rather than :func:`_safe_ref`, because a canonical agent
    id may carry ``.`` and ``-`` (the deployed roster includes ``oh-my-pi``)
    which the internal ref grammar never allowed. It is a strict superset of
    every value the retired ``profile_id`` field could have held, so a record
    written before the rename still validates on read.
    """

    if type(value) is not str or _SAFE_AGENT_ID_RE.fullmatch(value) is None:
        raise _invalid()
    return value


def _recorded_agent_id(document: Mapping) -> Any:
    """The record's sealed AGENT, reading the pre-rename key when that is all
    there is.

    Records written before the execution-preset change carry the AGENT under
    ``profile_id``. They are read, not migrated: an old task must stay
    queryable, cancellable, recoverable, and readable for its result. Whether
    its AGENT is still eligible is a separate question, asked by admission at
    the moment a *new* Run would be submitted.
    """

    value = document.get("agent_id")
    return document.get("profile_id") if value is None else value


def _safe_text(value: Any, *, maximum: int = 512) -> str:
    if type(value) is not str or len(value) > maximum:
        raise _invalid()
    return value


def _optional_text(value: Any, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    return _safe_text(value, maximum=maximum)


def _member(value: Any, allowed: tuple[str, ...]) -> str:
    if type(value) is not str or value not in allowed:
        raise _invalid()
    return value


def _new_ref(prefix: str) -> str:
    return _safe_ref(prefix + uuid.uuid4().hex)


def delegate_state_root(ledger_path: Any) -> str:
    """The private state directory: a sibling of the binding ledger's own file.

    Derived rather than configured on purpose. The ledger path is already the
    reviewed private host location, so the state that has to survive beside it
    inherits that approval instead of asking for a second one.
    """

    if type(ledger_path) is not str or not ledger_path.strip():
        raise _invalid()
    path = Path(ledger_path.strip())
    if not path.is_absolute():
        raise _invalid()
    return str(path.parent / "delegate-state")


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DelegateOrigin:
    """Where one task came from, and which Hermes Session owns its result.

    Chat and thread are host routing material and the Session key is trusted
    Gateway context: both are ``repr``-excluded, and neither is ever handed to
    the spine or carried on a dispatch request.
    """

    platform: str
    chat_id: str = field(repr=False)
    thread_id: str | None = field(default=None, repr=False)
    session_key: str = field(default="", repr=False)
    session_id: str = ""
    reply_anchor: str | None = field(default=None, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "chat_id": self.chat_id,
            "thread_id": self.thread_id,
            "session_key": self.session_key,
            "session_id": self.session_id,
            "reply_anchor": self.reply_anchor,
        }

    @classmethod
    def from_dict(cls, document: Any) -> "DelegateOrigin":
        if not isinstance(document, Mapping):
            raise _invalid()
        return cls(
            platform=_safe_text(document.get("platform", "")),
            chat_id=_safe_text(document.get("chat_id", "")),
            thread_id=_optional_text(document.get("thread_id")),
            session_key=_safe_text(document.get("session_key", "")),
            session_id=_safe_text(document.get("session_id", "")),
            reply_anchor=_optional_text(document.get("reply_anchor")),
        )


@dataclass(frozen=True)
class DelegateTurnRecord:
    """One Run attempt: immutable identity plus four orthogonal dimensions.

    The identity half is what derives this turn's **exact ledger key** — the
    ``(task_id, backend_handle, dispatch_ref)`` triple — which is the only thing
    that makes a durable classification possible after a restart. The mutable
    half is deliberately four independent fields rather than one status: a Run
    can be admitted *and* have an uncertain cancellation *and* an unsettled
    receipt at the same time, and collapsing that into a single label is how a
    coordinator ends up reporting one of them as if it settled the others.
    """

    turn_key: str
    task_ref: str
    task_id: str
    backend_handle: str
    dispatch_ref: str
    payload_ref: str
    spine_session_id: str
    agent_id: str
    launch_refs: tuple[str, ...]
    requested_agent: str
    requested_model: str
    requested_effort: str
    origin: DelegateOrigin
    lifecycle: str = "prepared"
    cancellation: str = "none"
    receipt: str = "pending"
    observation: str = "unarmed"
    turn_ref: str | None = None
    receipt_message_id: str | None = field(default=None, repr=False)
    diagnostic: str | None = None
    terminal_status: str | None = None

    def __post_init__(self) -> None:
        _safe_ref(self.turn_key)
        _safe_ref(self.task_ref)
        _safe_ref(self.task_id)
        _safe_ref(self.backend_handle)
        _safe_ref(self.dispatch_ref)
        _safe_ref(self.payload_ref)
        _safe_ref(self.spine_session_id)
        _safe_agent_id(self.agent_id)
        if type(self.launch_refs) is not tuple or not self.launch_refs:
            raise _invalid()
        for ref in self.launch_refs:
            _safe_ref(ref)
        _safe_text(self.requested_agent)
        _safe_text(self.requested_model)
        _safe_text(self.requested_effort)
        if type(self.origin) is not DelegateOrigin:
            raise _invalid()
        _member(self.lifecycle, LIFECYCLE_STATES)
        _member(self.cancellation, CANCELLATION_STATES)
        _member(self.receipt, RECEIPT_STATES)
        _member(self.observation, OBSERVATION_STATES)
        _optional_ref(self.turn_ref)
        _optional_text(self.receipt_message_id)
        _optional_text(self.diagnostic)
        _optional_text(self.terminal_status)

    @property
    def ledger_key(self) -> tuple[str, str, str]:
        """The exact ledger key this turn classifies against."""

        return (self.task_id, self.backend_handle, self.dispatch_ref)

    def as_dict(self) -> dict[str, Any]:
        return {
            "turn_key": self.turn_key,
            "task_ref": self.task_ref,
            "task_id": self.task_id,
            "backend_handle": self.backend_handle,
            "dispatch_ref": self.dispatch_ref,
            "payload_ref": self.payload_ref,
            "spine_session_id": self.spine_session_id,
            "agent_id": self.agent_id,
            "launch_refs": list(self.launch_refs),
            "requested_agent": self.requested_agent,
            "requested_model": self.requested_model,
            "requested_effort": self.requested_effort,
            "origin": self.origin.as_dict(),
            "lifecycle": self.lifecycle,
            "cancellation": self.cancellation,
            "receipt": self.receipt,
            "observation": self.observation,
            "turn_ref": self.turn_ref,
            "receipt_message_id": self.receipt_message_id,
            "diagnostic": self.diagnostic,
            "terminal_status": self.terminal_status,
        }

    @classmethod
    def from_dict(cls, document: Any) -> "DelegateTurnRecord":
        if not isinstance(document, Mapping):
            raise _invalid()
        refs = document.get("launch_refs")
        if type(refs) is not list:
            raise _invalid()
        return cls(
            turn_key=document.get("turn_key"),
            task_ref=document.get("task_ref"),
            task_id=document.get("task_id"),
            backend_handle=document.get("backend_handle"),
            dispatch_ref=document.get("dispatch_ref"),
            payload_ref=document.get("payload_ref"),
            spine_session_id=document.get("spine_session_id"),
            agent_id=_recorded_agent_id(document),
            launch_refs=tuple(refs),
            requested_agent=document.get("requested_agent", ""),
            requested_model=document.get("requested_model", ""),
            requested_effort=document.get("requested_effort", ""),
            origin=DelegateOrigin.from_dict(document.get("origin")),
            lifecycle=document.get("lifecycle", "prepared"),
            cancellation=document.get("cancellation", "none"),
            receipt=document.get("receipt", "pending"),
            observation=document.get("observation", "unarmed"),
            turn_ref=document.get("turn_ref"),
            receipt_message_id=document.get("receipt_message_id"),
            diagnostic=document.get("diagnostic"),
            terminal_status=document.get("terminal_status"),
        )


@dataclass(frozen=True)
class DelegateTaskBinding:
    """One delegated task: sealed identity plus its ordered turns."""

    task_ref: str
    task_id: str
    backend_handle: str
    spine_session_id: str
    agent_id: str
    origin: DelegateOrigin
    turn_keys: tuple[str, ...] = ()
    current_turn_key: str | None = None
    terminal: bool = False
    linked_from: str | None = None

    def __post_init__(self) -> None:
        _safe_ref(self.task_ref)
        _safe_ref(self.task_id)
        _safe_ref(self.backend_handle)
        _safe_ref(self.spine_session_id)
        _safe_agent_id(self.agent_id)
        if type(self.origin) is not DelegateOrigin:
            raise _invalid()
        if type(self.turn_keys) is not tuple:
            raise _invalid()
        for key in self.turn_keys:
            _safe_ref(key)
        _optional_ref(self.current_turn_key)
        if type(self.terminal) is not bool:
            raise _invalid()
        _optional_ref(self.linked_from)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_ref": self.task_ref,
            "task_id": self.task_id,
            "backend_handle": self.backend_handle,
            "spine_session_id": self.spine_session_id,
            "agent_id": self.agent_id,
            "origin": self.origin.as_dict(),
            "turn_keys": list(self.turn_keys),
            "current_turn_key": self.current_turn_key,
            "terminal": self.terminal,
            "linked_from": self.linked_from,
        }

    @classmethod
    def from_dict(cls, document: Any) -> "DelegateTaskBinding":
        if not isinstance(document, Mapping):
            raise _invalid()
        keys = document.get("turn_keys")
        if type(keys) is not list:
            raise _invalid()
        return cls(
            task_ref=document.get("task_ref"),
            task_id=document.get("task_id"),
            backend_handle=document.get("backend_handle"),
            spine_session_id=document.get("spine_session_id"),
            agent_id=_recorded_agent_id(document),
            origin=DelegateOrigin.from_dict(document.get("origin")),
            turn_keys=tuple(keys),
            current_turn_key=document.get("current_turn_key"),
            terminal=document.get("terminal", False),
            linked_from=document.get("linked_from"),
        )


@dataclass(frozen=True)
class DelegateResultEvent:
    """One canonical result identity, with two independent sink states.

    ``(turn_ref, terminal)`` creates at most one of these, which is what makes
    "one terminal, one message" true across restarts as well as within a
    process. The two sinks are separate because they fail separately: an IM
    send that failed must not erase the next-turn Hermes projection, and a
    consumed Hermes handoff must not re-send anything to a chat.
    """

    event_id: str
    turn_key: str
    task_ref: str
    session_id: str
    terminal: str
    full_result_ref: str
    truncated: bool = False
    truncate_reason: str | None = None
    im_sink: str = "pending"
    hermes_sink: str = "pending"
    im_message_id: str | None = field(default=None, repr=False)
    im_diagnostic: str | None = None

    def __post_init__(self) -> None:
        _safe_ref(self.event_id)
        _safe_ref(self.turn_key)
        _safe_ref(self.task_ref)
        _safe_text(self.session_id)
        _safe_text(self.terminal, maximum=64)
        _safe_ref(self.full_result_ref)
        if type(self.truncated) is not bool:
            raise _invalid()
        _optional_text(self.truncate_reason, maximum=64)
        _member(self.im_sink, SINK_STATES)
        _member(self.hermes_sink, SINK_STATES[:3])
        _optional_text(self.im_message_id)
        _optional_text(self.im_diagnostic)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "turn_key": self.turn_key,
            "task_ref": self.task_ref,
            "session_id": self.session_id,
            "terminal": self.terminal,
            "full_result_ref": self.full_result_ref,
            "truncated": self.truncated,
            "truncate_reason": self.truncate_reason,
            "im_sink": self.im_sink,
            "hermes_sink": self.hermes_sink,
            "im_message_id": self.im_message_id,
            "im_diagnostic": self.im_diagnostic,
        }

    @classmethod
    def from_dict(cls, document: Any) -> "DelegateResultEvent":
        if not isinstance(document, Mapping):
            raise _invalid()
        return cls(
            event_id=document.get("event_id"),
            turn_key=document.get("turn_key"),
            task_ref=document.get("task_ref"),
            session_id=document.get("session_id", ""),
            terminal=document.get("terminal", ""),
            full_result_ref=document.get("full_result_ref"),
            truncated=document.get("truncated", False),
            truncate_reason=document.get("truncate_reason"),
            im_sink=document.get("im_sink", "pending"),
            hermes_sink=document.get("hermes_sink", "pending"),
            im_message_id=document.get("im_message_id"),
            im_diagnostic=document.get("im_diagnostic"),
        )


# --------------------------------------------------------------------------- #
# The store
# --------------------------------------------------------------------------- #
_RECORD_TYPES = {
    "task": DelegateTaskBinding,
    "turn": DelegateTurnRecord,
    "result": DelegateResultEvent,
}


class DelegateStateStore:
    """Atomic, private, refs-only durable state for delegated tasks."""

    def __init__(self, root: Any) -> None:
        if type(root) is not str or not root.strip():
            raise _invalid()
        self._root = Path(root.strip())
        self._lock = threading.RLock()
        for name in ("payloads", "tasks", "turns", "results"):
            (self._root / name).mkdir(parents=True, exist_ok=True)
            os.chmod(self._root / name, _DIR_MODE)
        os.chmod(self._root, _DIR_MODE)

    @property
    def root(self) -> str:
        return str(self._root)

    # -- primitives --------------------------------------------------------- #
    def _write_bytes(self, path: Path, payload: bytes) -> None:
        temp = path.with_name(path.name + ".tmp")
        try:
            with open(temp, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp, _FILE_MODE)
            os.replace(temp, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise _unreadable() from None

    def _read_bytes(self, path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            raise _unreadable() from None

    def _write_document(self, path: Path, kind: str, document: Mapping[str, Any]) -> None:
        payload = json.dumps(
            {"version": DELEGATE_STATE_VERSION, "kind": kind, "record": dict(document)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self._write_bytes(path, payload)

    def _read_document(self, path: Path, kind: str) -> Any:
        raw = self._read_bytes(path)
        if raw is None:
            return None
        if not raw:
            raise _unreadable()
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise _unreadable() from None
        if (
            not isinstance(document, dict)
            or document.get("version") != DELEGATE_STATE_VERSION
            or document.get("kind") != kind
        ):
            raise _unreadable()
        record = document.get("record")
        try:
            return _RECORD_TYPES[kind].from_dict(record)
        except DelegateStateError:
            raise _unreadable() from None

    # -- payloads ----------------------------------------------------------- #
    def put_payload(self, text: Any) -> str:
        """Store one task text durably and return its opaque ref."""

        if type(text) is not str or not text.strip():
            raise _invalid()
        encoded = text.encode("utf-8")
        if len(encoded) > _MAX_PAYLOAD_BYTES:
            raise _invalid()
        ref = _new_ref(DELEGATE_PAYLOAD_REF_PREFIX)
        self._write_bytes(self._root / "payloads" / ref, encoded)
        return ref

    def read_payload(self, payload_ref: Any) -> str:
        """The exact bytes for ``payload_ref``, or fail closed with no echo."""

        if type(payload_ref) is not str or _SAFE_REF_RE.fullmatch(payload_ref) is None:
            raise _invalid()
        raw = self._read_bytes(self._root / "payloads" / payload_ref)
        if raw is None:
            raise _invalid()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            raise _unreadable() from None

    def discard_payload(self, payload_ref: Any) -> None:
        """Forget one payload. Idempotent; never raises on an unknown ref."""

        if type(payload_ref) is not str or _SAFE_REF_RE.fullmatch(payload_ref) is None:
            return
        try:
            os.unlink(self._root / "payloads" / payload_ref)
        except OSError:
            return

    # -- tasks -------------------------------------------------------------- #
    def new_task_ref(self) -> str:
        return _new_ref(_TASK_REF_PREFIX)

    def new_turn_key(self) -> str:
        return _new_ref(_TURN_KEY_PREFIX)

    def put_task(self, binding: DelegateTaskBinding) -> DelegateTaskBinding:
        if type(binding) is not DelegateTaskBinding:
            raise _invalid()
        with self._lock:
            self._write_document(
                self._root / "tasks" / binding.task_ref, "task", binding.as_dict()
            )
        return binding

    def read_task(self, task_ref: Any) -> DelegateTaskBinding | None:
        return self._read_document(self._root / "tasks" / _safe_ref(task_ref), "task")

    def list_tasks(self) -> tuple[DelegateTaskBinding, ...]:
        return tuple(self._list("tasks", "task"))

    def update_task(self, task_ref: Any, **fields: Any) -> DelegateTaskBinding:
        with self._lock:
            existing = self.read_task(task_ref)
            if existing is None:
                raise _conflict()
            updated = replace(existing, **fields)
            self._write_document(
                self._root / "tasks" / updated.task_ref, "task", updated.as_dict()
            )
            return updated

    # -- turns -------------------------------------------------------------- #
    def put_turn(self, record: DelegateTurnRecord) -> DelegateTurnRecord:
        if type(record) is not DelegateTurnRecord:
            raise _invalid()
        with self._lock:
            self._write_document(
                self._root / "turns" / record.turn_key, "turn", record.as_dict()
            )
        return record

    def read_turn(self, turn_key: Any) -> DelegateTurnRecord | None:
        return self._read_document(self._root / "turns" / _safe_ref(turn_key), "turn")

    def list_turns(self) -> tuple[DelegateTurnRecord, ...]:
        return tuple(self._list("turns", "turn"))

    def update_turn(self, turn_key: Any, **fields: Any) -> DelegateTurnRecord:
        """Replace one turn's mutable dimensions, atomically.

        Identity fields are not writable here — a turn that could change its
        ledger key is a turn whose durable classification means nothing.
        """

        forbidden = {
            "turn_key",
            "task_ref",
            "task_id",
            "backend_handle",
            "dispatch_ref",
            "payload_ref",
            "spine_session_id",
            "launch_refs",
        }
        if set(fields) & forbidden:
            raise _conflict()
        with self._lock:
            existing = self.read_turn(turn_key)
            if existing is None:
                raise _conflict()
            updated = replace(existing, **fields)
            self._write_document(
                self._root / "turns" / updated.turn_key, "turn", updated.as_dict()
            )
            return updated

    def discard_turn(self, turn_key: Any) -> None:
        """Remove one turn record. Used only for a proven-safe cleanup."""

        try:
            os.unlink(self._root / "turns" / _safe_ref(turn_key))
        except OSError:
            return

    def discard_task(self, task_ref: Any) -> None:
        try:
            os.unlink(self._root / "tasks" / _safe_ref(task_ref))
        except OSError:
            return

    # -- results ------------------------------------------------------------ #
    def put_full_result(self, body: Any) -> tuple[str, bool]:
        """Store the untruncated answer and return ``(ref, clipped)``."""

        if type(body) is not str:
            raise _invalid()
        encoded = body.encode("utf-8")
        clipped = False
        if len(encoded) > _MAX_RESULT_BYTES:
            encoded = encoded[:_MAX_RESULT_BYTES]
            while encoded:
                try:
                    encoded.decode("utf-8")
                    break
                except UnicodeDecodeError:
                    encoded = encoded[:-1]
            clipped = True
        ref = _new_ref(_RESULT_REF_PREFIX)
        self._write_bytes(self._root / "results" / ref, encoded)
        return ref, clipped

    def read_full_result(self, full_result_ref: Any) -> str:
        raw = self._read_bytes(self._root / "results" / _safe_ref(full_result_ref))
        if raw is None:
            raise _invalid()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            raise _unreadable() from None

    def new_event_id(self) -> str:
        return _new_ref(_EVENT_ID_PREFIX)

    def put_result(self, event: DelegateResultEvent) -> DelegateResultEvent:
        if type(event) is not DelegateResultEvent:
            raise _invalid()
        with self._lock:
            by_id = self.read_result(event.event_id)
            if by_id is not None:
                if by_id == event:
                    return by_id
                raise _conflict()
            if any(existing.turn_key == event.turn_key for existing in self.list_results()):
                raise _conflict()
            self._write_document(
                self._root / "results" / (event.event_id + ".json"),
                "result",
                event.as_dict(),
            )
        return event

    def read_result(self, event_id: Any) -> DelegateResultEvent | None:
        return self._read_document(
            self._root / "results" / (_safe_ref(event_id) + ".json"), "result"
        )

    def result_for_turn(self, turn_key: Any) -> DelegateResultEvent | None:
        """The single canonical result of one turn, or ``None``.

        Looked up by turn rather than kept in an index: one turn has at most one
        result, so the record itself is the index and there is no second place
        for the two to disagree.
        """

        key = _safe_ref(turn_key)
        found: DelegateResultEvent | None = None
        for event in self.list_results():
            if event.turn_key == key:
                if found is not None:
                    # More than one result identity for a turn is corrupt
                    # durable state, never an ordering choice.
                    raise _conflict()
                found = event
        return found

    def list_results(self) -> tuple[DelegateResultEvent, ...]:
        events: list[DelegateResultEvent] = []
        turn_keys: set[str] = set()
        for path in sorted(self._root.glob("results/*.json")):
            record = self._read_document(path, "result")
            if record is not None:
                if record.turn_key in turn_keys:
                    raise _conflict()
                turn_keys.add(record.turn_key)
                events.append(record)
        return tuple(events)

    def update_result(self, event_id: Any, **fields: Any) -> DelegateResultEvent:
        with self._lock:
            existing = self.read_result(event_id)
            if existing is None:
                raise _conflict()
            updated = replace(existing, **fields)
            self._write_document(
                self._root / "results" / (updated.event_id + ".json"),
                "result",
                updated.as_dict(),
            )
            return updated

    # -- internals ---------------------------------------------------------- #
    def _list(self, folder: str, kind: str) -> list[Any]:
        records: list[Any] = []
        for path in sorted((self._root / folder).iterdir()):
            if path.name.endswith(".tmp") or path.name.endswith(".json"):
                continue
            record = self._read_document(path, kind)
            if record is not None:
                records.append(record)
        return records


# --------------------------------------------------------------------------- #
# Capacity
# --------------------------------------------------------------------------- #
class DelegateCapacity:
    """One conservative permit per turn that might still be consuming a Run.

    Two entry points, and the difference between them is the whole point.
    :meth:`acquire` is *admission*: it waits for a free slot, because admitting
    more concurrent Runs than the daemon said it will hold is over-admission.
    :meth:`reserve` is *restoration*: a Run that was already accepted before the
    restart is already consuming the daemon's capacity, so its permit is taken
    without waiting — refusing to reserve would not free the Run, it would only
    hide it.

    :meth:`release` is idempotent per turn, so the several paths that can reach
    a settled turn cannot release the same permit twice and let a second Run in.
    """

    def __init__(self, capacity: int) -> None:
        if isinstance(capacity, bool) or type(capacity) is not int or capacity < 1:
            raise _invalid()
        self._capacity = capacity
        self._held: set[str] = set()
        self._lock = threading.RLock()
        self._waiters: list[asyncio.Future] = []

    @property
    def capacity(self) -> int:
        return self._capacity

    def held(self) -> int:
        with self._lock:
            return len(self._held)

    def holds(self, turn_key: Any) -> bool:
        with self._lock:
            return turn_key in self._held

    def reserve(self, turn_key: Any) -> None:
        """Take one permit for restored work, without waiting."""

        key = _safe_ref(turn_key)
        with self._lock:
            self._held.add(key)

    def try_acquire(self, turn_key: Any) -> bool:
        key = _safe_ref(turn_key)
        with self._lock:
            if key in self._held:
                return True
            if len(self._held) >= self._capacity:
                return False
            self._held.add(key)
            return True

    async def acquire(self, turn_key: Any) -> None:
        """Wait for a free slot, then take it. Idempotent per turn."""

        while not self.try_acquire(turn_key):
            loop = asyncio.get_running_loop()
            waiter = loop.create_future()
            with self._lock:
                self._waiters.append(waiter)
            try:
                await waiter
            finally:
                with self._lock:
                    if waiter in self._waiters:
                        self._waiters.remove(waiter)

    def release(self, turn_key: Any) -> bool:
        """Give one permit back, at most once per turn."""

        key = _safe_ref(turn_key)
        with self._lock:
            if key not in self._held:
                return False
            self._held.discard(key)
            waiters = list(self._waiters)
            self._waiters.clear()
        for waiter in waiters:
            if not waiter.done():
                waiter.get_loop().call_soon_threadsafe(_resolve_waiter, waiter)
        return True

    def would_wait(self) -> bool:
        with self._lock:
            return len(self._held) >= self._capacity


def _resolve_waiter(waiter: asyncio.Future) -> None:
    if not waiter.done():
        waiter.set_result(None)
