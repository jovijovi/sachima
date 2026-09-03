"""R1 Runtime Spine — refs-only Task Event Log + single seq authority.

This module is the spine's **canonical truth boundary**. It owns:

* the fail-closed ``SpineError`` + the stable R1 error-code family;
* the sanitizers and the refs-only no-leak scan (``scan_for_leak``) that every
  event body must pass — event bodies carry only refs / digests / counts / status
  / stable codes, never raw prompt / stdout / stderr / tool output / card JSON /
  platform ids / private paths / secrets / signed URLs / media paths;
* ``TaskEvent`` — a frozen, sanitized event record;
* ``TaskEventLog`` — an append-only, in-memory, lock-guarded log that is the
  **single monotonic ``seq`` authority per ``task_id``**. Callers never assign
  ``seq``; the log does, strictly ``1..N`` and gap-free, even under concurrency.

It is pure, local/offline Python. Importing it starts no subprocess, socket,
Docker, Temporal service/Worker/client, Gateway, Feishu, network call, or OS
process launch, and it wires none of those surfaces. The forbidden terms below
appear **only** as no-leak denylist canaries, never as behavior.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# Stable error-code family (fail-closed; message is the code, never raw input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_TASK_ID = "runtime_invalid_task_id"
RUNTIME_INVALID_EVENT = "runtime_invalid_event"
RUNTIME_SEQ_VIOLATION = "runtime_seq_violation"
RUNTIME_EVENT_LEAK_DETECTED = "runtime_event_leak_detected"
RUNTIME_INVALID_PROJECTION = "runtime_invalid_projection"
RUNTIME_INVALID_TASK_RECORD = "runtime_invalid_task_record"
RUNTIME_UNKNOWN_CAPABILITY = "runtime_unknown_capability"
RUNTIME_INVALID_LAUNCH_SPEC = "runtime_invalid_launch_spec"

STABLE_CODES = frozenset(
    {
        RUNTIME_INVALID_TASK_ID,
        RUNTIME_INVALID_EVENT,
        RUNTIME_SEQ_VIOLATION,
        RUNTIME_EVENT_LEAK_DETECTED,
        RUNTIME_INVALID_PROJECTION,
        RUNTIME_INVALID_TASK_RECORD,
        RUNTIME_UNKNOWN_CAPABILITY,
        RUNTIME_INVALID_LAUNCH_SPEC,
    }
)


class SpineError(Exception):
    """Fail-closed spine contract violation carrying a stable code only.

    The message is the stable code itself — never raw input, exception text, or a
    traceback — so a rejected event/spec can be surfaced without leaking material.
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


# --------------------------------------------------------------------------- #
# Charset / marker families
# --------------------------------------------------------------------------- #
_SAFE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SAFE_KIND_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

#: No-leak denylist (matched case-insensitively against the lowered string
#: rendering of any event key/value/ref). Kept specific so legitimate refs and
#: sha256 digests never false-positive. Includes every canary the R1 gate
#: requires: raw_prompt / agent_stdout / tool_output / card_json / chat_id /
#: oc_ / ou_ / /tmp/ / sk- / "bearer ".
FORBIDDEN_MARKERS: tuple[str, ...] = (
    "raw_prompt",
    "raw_context",
    "raw_output",
    "raw_command",
    "raw_response",
    "prompt_body",
    "model_output",
    "agent_stdout",
    "stdout",
    "stderr",
    "tool_output",
    "traceback",
    "card_json",
    "media_path",
    "media_bytes",
    "media:",
    "signed_url",
    "presigned",
    "x-amz-signature",
    "bearer ",
    "bearer_",
    "api_key",
    "apikey",
    "password",
    "secret",
    "credential",
    "private_key",
    "connection_string",
    "post" + "gres://",
    "redis" + "://",
    "sk-",
    "xox",
    "ghp_",
    "akia",
    "-----begin",
    "/home/",
    "/users/",
    "/tmp/",
    "/var/",
    "chat_id",
    "user_id",
    "message_id",
    "platform_id",
    "platform_payload",
    "delivery_payload",
    "im_body",
    "om_",
    "oc_",
    "ou_",
    "feishu",
    "lark",
    "private",
)

#: Roles that imply write capability are out of R1 (read-only roles only).
_FORBIDDEN_ROLE_MARKERS: tuple[str, ...] = ("write", "deliver", "approve", "reject", "mutate")

# --------------------------------------------------------------------------- #
# Event / status vocabularies (static allowlists — no dynamic discovery)
# --------------------------------------------------------------------------- #
EVENT_TYPES = frozenset(
    {
        "task_created",
        "agent_attach_requested",
        "agent_attached",
        "permission_requested",
        "permission_answered",
        "progress",
        "milestone",
        "completed",
        "failed",
        "cancelled",
        "terminal",
    }
)

STATUS_VALUES = frozenset(
    {"created", "running", "permission_wait", "completed", "failed", "cancelled"}
)
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

ALLOWED_EVENT_BODY_KEYS = frozenset(
    {"event_type", "status", "refs", "digests", "counts", "flags", "error_code"}
)
KNOWN_FLAG_KEYS = frozenset({"needs_agent", "needs_durable"})


# --------------------------------------------------------------------------- #
# No-leak scan
# --------------------------------------------------------------------------- #
def _has_forbidden_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in FORBIDDEN_MARKERS)


def _walk_strings(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            out.append(str(key))
            out.extend(_walk_strings(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            out.extend(_walk_strings(item))
    return out


def scan_for_leak(value: Any, *, canaries: tuple[str, ...] = ()) -> str | None:
    """Return ``runtime_event_leak_detected`` if any forbidden marker or seeded
    canary appears in a key or string value (recursively), else ``None``."""

    strings = _walk_strings(value)
    for text in strings:
        if _has_forbidden_marker(text):
            return RUNTIME_EVENT_LEAK_DETECTED
    if canaries:
        lowered_all = "\x1f".join(text.lower() for text in strings)
        for canary in canaries:
            if canary and canary.lower() in lowered_all:
                return RUNTIME_EVENT_LEAK_DETECTED
    return None


# --------------------------------------------------------------------------- #
# Sanitizers (each fails closed with a caller-chosen stable code)
# --------------------------------------------------------------------------- #
def _safe_id(value: Any, *, code: str = RUNTIME_INVALID_EVENT) -> str:
    if type(value) is not str or _SAFE_ID_RE.fullmatch(value) is None:
        raise SpineError(code)
    if _has_forbidden_marker(value):
        raise SpineError(code)
    return value


def _safe_kind(value: Any, *, code: str = RUNTIME_INVALID_EVENT) -> str:
    if type(value) is not str or _SAFE_KIND_RE.fullmatch(value) is None:
        raise SpineError(code)
    if _has_forbidden_marker(value):
        raise SpineError(code)
    return value


def _safe_digest(value: Any, *, code: str = RUNTIME_INVALID_EVENT) -> str:
    if type(value) is not str or _SHA256_DIGEST_RE.fullmatch(value) is None:
        raise SpineError(code)
    return value


def _safe_count(value: Any, *, code: str = RUNTIME_INVALID_EVENT) -> int:
    # bool is an int subclass — exclude it explicitly so a flag can't pose as a count.
    if type(value) is not int or value < 0 or value > 1_000_000_000:
        raise SpineError(code)
    return value


def safe_task_id(value: Any, *, code: str = RUNTIME_INVALID_TASK_ID) -> str:
    """Validate a spine ``task_id`` — a safe lowercase identifier, no raw/platform
    material."""

    return _safe_id(value, code=code)


def safe_role_key(value: Any, *, code: str = RUNTIME_INVALID_LAUNCH_SPEC) -> str:
    """Validate a read-only role key — rejects write-capable role markers."""

    role = _safe_id(value, code=code)
    if any(marker in role.lower() for marker in _FORBIDDEN_ROLE_MARKERS):
        raise SpineError(code)
    return role


def safe_error_code(value: Any, *, code: str = RUNTIME_INVALID_EVENT) -> str:
    if value not in STABLE_CODES:
        raise SpineError(code)
    return value


# --------------------------------------------------------------------------- #
# Frozen sanitized event record
# --------------------------------------------------------------------------- #
def _check_event_fields(event: Any) -> None:
    """Exact fail-closed validation of a normalized event's fields.

    Enforces the same allowlists as ``validate_event_body`` on the *normalized*
    (tuple-of-pairs) shape a ``TaskEvent`` carries, so a directly constructed or
    ``object.__new__``-forged event can never hold unsafe / non-allowlisted
    material. Fails closed on: an unsafe ``task_id``; a ``seq`` that is not an
    exact ``int >= 1`` (``bool`` excluded); an unknown ``event_type`` / ``status``
    / ``error_code``; a non-tuple / unsafe ref; a non-``sha256`` digest; a bad
    counts pair; an unknown flag key or non-``bool`` flag value.
    """

    try:
        task_id = event.task_id
        seq = event.seq
        event_type = event.event_type
        status = event.status
        refs = event.refs
        digests = event.digests
        counts = event.counts
        flags = event.flags
        error_code = event.error_code
    except AttributeError as exc:
        raise SpineError(RUNTIME_INVALID_EVENT) from exc

    safe_task_id(task_id)
    # bool is an int subclass — exclude it so a flag can't pose as a seq.
    if type(seq) is not int or seq < 1:
        raise SpineError(RUNTIME_INVALID_EVENT)
    if event_type not in EVENT_TYPES:
        raise SpineError(RUNTIME_INVALID_EVENT)
    if status is not None and status not in STATUS_VALUES:
        raise SpineError(RUNTIME_INVALID_EVENT)
    if type(refs) is not tuple or type(digests) is not tuple:
        raise SpineError(RUNTIME_INVALID_EVENT)
    for ref in refs:
        _safe_id(ref)
    for digest in digests:
        _safe_digest(digest)
    if type(counts) is not tuple or type(flags) is not tuple:
        raise SpineError(RUNTIME_INVALID_EVENT)
    for pair in counts:
        if type(pair) is not tuple or len(pair) != 2:
            raise SpineError(RUNTIME_INVALID_EVENT)
        _safe_kind(pair[0])
        _safe_count(pair[1])
    for pair in flags:
        if type(pair) is not tuple or len(pair) != 2:
            raise SpineError(RUNTIME_INVALID_EVENT)
        key, flag = pair
        if key not in KNOWN_FLAG_KEYS or type(flag) is not bool:
            raise SpineError(RUNTIME_INVALID_EVENT)
    if error_code is not None:
        safe_error_code(error_code)


@dataclass(frozen=True)
class TaskEvent:
    """A frozen, sanitized, refs-only event. ``seq`` is assigned by the log only.

    ``TaskEvent`` is exported public surface, so construction alone must never be
    grounds for trust: ``__post_init__`` re-runs the full refs-only allowlist so a
    direct ``TaskEvent(...)`` with unsafe / non-allowlisted fields fails closed
    instead of being projected. Boundary consumers additionally call
    ``validate_task_event`` to defend against ``object.__new__`` forgery and
    hostile subclasses that skip ``__post_init__``.
    """

    task_id: str
    seq: int
    event_type: str
    status: str | None = None
    refs: tuple[str, ...] = ()
    digests: tuple[str, ...] = ()
    counts: tuple[tuple[str, int], ...] = ()
    flags: tuple[tuple[str, bool], ...] = ()
    error_code: str | None = None

    def __post_init__(self) -> None:
        _check_event_fields(self)


def validate_task_event(event: TaskEvent) -> TaskEvent:
    """Re-validate a ``TaskEvent`` at a trust boundary and return it unchanged.

    ``__post_init__`` validates on normal construction, but an exported frozen
    dataclass can still be forged via ``object.__new__`` + ``object.__setattr__``
    or a subclass that overrides ``__post_init__`` to skip validation. Every
    consumer that trusts a ``TaskEvent`` (``event_projection`` and the
    ``project`` / ``verify_seq_contiguous`` replay path) calls this, so the
    event/projection surface stays fail-closed against a hostile or directly
    constructed instance and never relies on the append path alone.
    """

    if type(event) is not TaskEvent:
        raise SpineError(RUNTIME_INVALID_EVENT)
    _check_event_fields(event)
    return event


def event_projection(event: TaskEvent) -> dict[str, Any]:
    """Allowlist-only dict view of an event (refs/counts/status/codes only)."""

    validate_task_event(event)
    return {
        "task_id": event.task_id,
        "seq": event.seq,
        "event_type": event.event_type,
        "status": event.status,
        "refs": list(event.refs),
        "digests": list(event.digests),
        "counts": {k: v for k, v in event.counts},
        "flags": {k: v for k, v in event.flags},
        "error_code": event.error_code,
    }


# --------------------------------------------------------------------------- #
# Event-body validation (refs-only; seq is never a caller input)
# --------------------------------------------------------------------------- #
def _normalize_counts(value: Any) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, Mapping):
        raise SpineError(RUNTIME_INVALID_EVENT)
    pairs = [(_safe_kind(k), _safe_count(v)) for k, v in value.items()]
    return tuple(sorted(pairs, key=lambda p: p[0]))


def _normalize_flags(value: Any) -> tuple[tuple[str, bool], ...]:
    if not isinstance(value, Mapping):
        raise SpineError(RUNTIME_INVALID_EVENT)
    pairs: list[tuple[str, bool]] = []
    for key, flag in value.items():
        if key not in KNOWN_FLAG_KEYS or type(flag) is not bool:
            raise SpineError(RUNTIME_INVALID_EVENT)
        pairs.append((key, flag))
    return tuple(sorted(pairs, key=lambda p: p[0]))


def _normalize_ref_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise SpineError(RUNTIME_INVALID_EVENT)
    return tuple(_safe_id(ref) for ref in value)


def validate_event_body(body: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a refs-only event body and return normalized ``TaskEvent`` fields.

    Fails closed on: a non-mapping; any key outside the body allowlist (so
    caller-supplied ``seq`` / ``task_id`` material is rejected); any forbidden
    marker in a key or value; an unknown ``event_type`` / ``status`` /
    ``error_code``; a non-``sha256`` digest; a negative/non-int count. Pure — it
    assigns no seq and mutates nothing.
    """

    if not isinstance(body, Mapping):
        raise SpineError(RUNTIME_INVALID_EVENT)
    # No-leak scan first: catches unsafe KEYS (incl. a smuggled ``seq``/``chat_id``
    # key) and unsafe string VALUES before any per-field normalization.
    if scan_for_leak(body) is not None:
        raise SpineError(RUNTIME_EVENT_LEAK_DETECTED)
    keys = set(body)
    if not keys.issubset(ALLOWED_EVENT_BODY_KEYS) or "event_type" not in keys:
        raise SpineError(RUNTIME_INVALID_EVENT)

    event_type = body["event_type"]
    if event_type not in EVENT_TYPES:
        raise SpineError(RUNTIME_INVALID_EVENT)

    status = body.get("status")
    if status is not None and status not in STATUS_VALUES:
        raise SpineError(RUNTIME_INVALID_EVENT)

    error_code = body.get("error_code")
    if error_code is not None:
        safe_error_code(error_code)

    return {
        "event_type": event_type,
        "status": status,
        "refs": _normalize_ref_tuple(body.get("refs", ())),
        "digests": tuple(_safe_digest(d) for d in _as_seq(body.get("digests", ()))),
        "counts": _normalize_counts(body.get("counts", {})),
        "flags": _normalize_flags(body.get("flags", {})),
        "error_code": error_code,
    }


def _as_seq(value: Any) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise SpineError(RUNTIME_INVALID_EVENT)
    return value


def build_event_body(
    *,
    event_type: str,
    status: str | None = None,
    refs: Sequence[str] = (),
    digests: Sequence[str] = (),
    counts: Mapping[str, int] | None = None,
    flags: Mapping[str, bool] | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Convenience builder for a validated refs-only event body (no seq/task_id)."""

    body: dict[str, Any] = {"event_type": event_type}
    if status is not None:
        body["status"] = status
    if refs:
        body["refs"] = tuple(refs)
    if digests:
        body["digests"] = tuple(digests)
    if counts:
        body["counts"] = dict(counts)
    if flags:
        body["flags"] = dict(flags)
    if error_code is not None:
        body["error_code"] = error_code
    validate_event_body(body)
    return body


# --------------------------------------------------------------------------- #
# Seq contiguity verifier (used by projection replay)
# --------------------------------------------------------------------------- #
def verify_seq_contiguous(events: Sequence[TaskEvent], *, task_id: str | None = None) -> None:
    """Fail closed unless ``events`` are a single-task, strictly ``1..N``,
    gap-free, in-order, duplicate-free ``seq`` run."""

    expected = 1
    seen_task: str | None = None
    for event in events:
        # Fail closed on any hostile / forged event surface before trusting its
        # seq or task_id — the replay path must never rely on the append path.
        validate_task_event(event)
        if seen_task is None:
            seen_task = event.task_id
        if event.task_id != seen_task:
            raise SpineError(RUNTIME_SEQ_VIOLATION)
        if event.seq != expected:
            raise SpineError(RUNTIME_SEQ_VIOLATION)
        expected += 1
    if task_id is not None and seen_task is not None and seen_task != task_id:
        raise SpineError(RUNTIME_SEQ_VIOLATION)


# --------------------------------------------------------------------------- #
# Append-only Task Event Log — single monotonic seq authority per task_id
# --------------------------------------------------------------------------- #
@dataclass
class TaskEventLog:
    """In-memory, lock-guarded, append-only event log.

    The log is the sole ``seq`` authority: ``append`` assigns strictly increasing
    ``seq`` values ``1..N`` per ``task_id``. Callers cannot supply a ``seq``; the
    lock makes concurrent appends to one task monotonic and gap-free.

    Internal state (``_events`` / ``_lock``) is ``init=False`` — the log owns it
    and it is never a constructor parameter. A caller cannot seed ``_events`` with
    pre-numbered events (which would bypass the log as the single seq authority)
    or inject a lock (which would break the concurrency guarantee): the only
    construction is zero-arg ``TaskEventLog()``.
    """

    _events: dict[str, list[TaskEvent]] = field(default_factory=dict, init=False)
    _lock: threading.RLock = field(
        default_factory=threading.RLock, init=False, repr=False, compare=False
    )

    def append(self, task_id: str, body: Mapping[str, Any]) -> TaskEvent:
        safe_task = safe_task_id(task_id)
        fields = validate_event_body(body)
        with self._lock:
            events = self._events.setdefault(safe_task, [])
            seq = len(events) + 1
            event = TaskEvent(task_id=safe_task, seq=seq, **fields)
            events.append(event)
            return event

    def events_for(self, task_id: str) -> tuple[TaskEvent, ...]:
        safe_task = safe_task_id(task_id)
        with self._lock:
            return tuple(self._events.get(safe_task, ()))

    def last_seq(self, task_id: str) -> int:
        safe_task = safe_task_id(task_id)
        with self._lock:
            return len(self._events.get(safe_task, ()))

    def event_count(self, task_id: str) -> int:
        return self.last_seq(task_id)

    def has_task(self, task_id: str) -> bool:
        safe_task = safe_task_id(task_id)
        with self._lock:
            return safe_task in self._events
