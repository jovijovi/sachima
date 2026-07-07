"""PR3 Runtime Spine — Sachima live progress safe projection.

This module is a **local/offline, refs-only read-model** over an
agent-run-supervisor run's already-merged caller cursor API shape: a
``load_progress(artifact_dir) -> ProgressSnapshot | None`` summary plus one
``read_event_page(artifact_dir, *, after_seq, limit) -> EventPage`` cursor page.
It maps those into a frozen, validated, byte-stable :class:`LiveProgressProjection`
that carries only refs / counts / coarse observed states / booleans / a resume
cursor / a stable ``error_code`` — never raw ``text`` / ``content`` / ``message``
/ ``body``, the ARS ``summary`` free text, artifact filesystem paths, platform
ids, secrets, exception text, or tracebacks.

It is deliberately **not** live IM progress, Gateway behavior, production
progress, real AGENT execution, or a business verdict. The supervisor's own
terminal states are collapsed to a coarse, non-verdict ``settled`` observation;
Sachima's ``TaskEventLog`` remains the sole per-``task_id`` seq + verdict
authority, and this projection never appends to it — the ARS ``seq`` / cursor is
a foreign read-model cursor only.

The producer library (``agent_run_supervisor``) resolves only from the
installed exact-pinned ``agent-run-supervisor`` distribution (the
``agent-run-supervisor`` / ``dev`` extra in ``pyproject.toml``) and the reader
is **injected**: the default :class:`DefaultLiveProgressReader` lazily imports
the ARS caller events module inside each call and fails closed to a
``live_progress_unavailable`` projection when the extra is not installed —
there is no top-level ``agent_run_supervisor`` import anywhere in this module
and no source-path / ``sys.path`` fallback anywhere in the repo. Building and
serializing are pure and side-effect-free: no process, socket, Gateway / IM /
delivery, durable Worker/service, or agent launch. Forbidden terms below appear
only as no-leak denylist boundary prose, never as behavior.
"""

from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass
from typing import Any, NoReturn, Protocol, runtime_checkable

from .events import (
    SpineError,
    _safe_count,
    _safe_id,
    safe_task_id,
    scan_for_leak,
)

# --------------------------------------------------------------------------- #
# Stable codes (module-local; message IS the code, never raw input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_LIVE_PROGRESS = "runtime_invalid_live_progress"
LIVE_PROGRESS_UNAVAILABLE = "live_progress_unavailable"
LIVE_PROGRESS_CORRUPT = "live_progress_corrupt"
LIVE_PROGRESS_STABLE_CODES = frozenset(
    {RUNTIME_INVALID_LIVE_PROGRESS, LIVE_PROGRESS_UNAVAILABLE, LIVE_PROGRESS_CORRUPT}
)
LIVE_PROGRESS_PROJECTION_TYPE = "sachima.runtime_spine.live_progress_projection.v1"

#: Coarse, non-verdict observation vocabulary (both supervisor state and per-event
#: status collapse into exactly these four safe tokens).
SUPERVISOR_OBSERVED_STATES = frozenset({"active", "waiting", "settled", "unknown"})
OBSERVED_EVENT_STATUSES = frozenset({"active", "waiting", "settled", "unknown"})

#: Closed map from an ARS state/status token to a coarse observation. Every
#: terminal-ish supervisor state collapses to a single **non-verdict** ``settled``
#: (NO success/failure distinction). Anything else / missing → ``unknown``; an
#: unmapped or leaky token is never echoed.
_ARS_STATE_TO_OBSERVED = {
    "running": "active",
    "active": "active",
    "in_progress": "active",
    "started": "active",
    "permission_wait": "waiting",
    "waiting": "waiting",
    "waiting_for_permission": "waiting",
    "blocked": "waiting",
    "completed": "settled",
    "succeeded": "settled",
    "failed": "settled",
    "cancelled": "settled",
    "killed": "settled",
    "exited": "settled",
    "done": "settled",
}

#: Token charset tuned to the ARS ``family`` / ``kind`` fields: bounded lowercase
#: ``[a-z0-9]`` plus ``_`` / ``-``. A token outside this charset is a fail-closed
#: corrupt page, not a silent transform.
_SAFE_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

#: Bound shared by cursors/counts read from the foreign artifact.
_MAX_COUNT = 1_000_000_000

#: Lazy import target — reached only inside :func:`_import_caller_events`, never
#: as a top-level ``import agent_run_supervisor``.
_ARS_CALLER_EVENTS_MODULE = "agent_run_supervisor.hermes_caller.events"


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_LIVE_PROGRESS)


# --------------------------------------------------------------------------- #
# Field-level sanitizers (each fails closed with the module's invalid code)
# --------------------------------------------------------------------------- #
def _safe_artifact_ref(value: Any) -> str:
    """A caller-supplied SAFE handle (e.g. ``artifact_local_0``) — never a path."""

    return _safe_id(value, code=RUNTIME_INVALID_LIVE_PROGRESS)


def _safe_token(value: Any) -> str:
    """A bounded ARS ``family`` / ``kind`` token; scans for forbidden markers."""

    if type(value) is not str or _SAFE_TOKEN_RE.fullmatch(value) is None:
        _invalid()
    if scan_for_leak(value) is not None:
        _invalid()
    return value


def _safe_seq(value: Any) -> int:
    # bool is an int subclass — exclude it so a flag can't pose as a seq.
    if type(value) is not int or value < 1 or value > _MAX_COUNT:
        _invalid()
    return value


def _safe_optional_cursor(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0 or value > _MAX_COUNT:
        _invalid()
    return value


def _check_count(value: Any) -> int:
    # bool is an int subclass — exclude it so a flag can't pose as a count. The
    # upper bound matches _safe_count / _safe_optional_cursor so a directly
    # constructed or forged projection cannot carry an unbounded top-level count.
    if type(value) is not int or value < 0 or value > _MAX_COUNT:
        _invalid()
    return value


def _check_bool(value: Any) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _map_observed_state(value: Any) -> str:
    """Collapse an ARS state/status token to a coarse observation.

    A non-string, missing, unmapped, or otherwise unexpected token maps to
    ``unknown`` and is never echoed — the coarse vocabulary is closed.
    """

    if type(value) is not str:
        return "unknown"
    return _ARS_STATE_TO_OBSERVED.get(value, "unknown")


# --------------------------------------------------------------------------- #
# Safe per-event record
# --------------------------------------------------------------------------- #
def _raw_record_dict(rec: Any) -> dict[str, Any]:
    return {
        "seq": rec.seq,
        "family": rec.family,
        "kind": rec.kind,
        "observed_status": rec.observed_status,
        "text_length": rec.text_length,
    }


def _check_live_progress_record_fields(rec: Any) -> None:
    """Exact fail-closed validation of one refs-only event record.

    Fails closed on: a missing field; a ``seq`` that is not an exact ``int >= 1``
    (``bool`` excluded); a ``family`` / ``kind`` outside the bounded ARS token
    charset or carrying a forbidden marker; an ``observed_status`` outside the
    closed observation vocabulary; a negative / non-``int`` / oversized
    ``text_length``; or any forbidden marker anywhere in the record. It never
    echoes the rejected material.
    """

    try:
        seq = rec.seq
        family = rec.family
        kind = rec.kind
        observed_status = rec.observed_status
        text_length = rec.text_length
    except AttributeError:
        _invalid()

    _safe_seq(seq)
    _safe_token(family)
    _safe_token(kind)
    if type(observed_status) is not str or observed_status not in OBSERVED_EVENT_STATUSES:
        _invalid()
    _safe_count(text_length, code=RUNTIME_INVALID_LIVE_PROGRESS)
    if scan_for_leak(_raw_record_dict(rec)) is not None:
        _invalid()


@dataclass(frozen=True)
class LiveProgressEventRecord:
    """Frozen, refs-only projection of one ARS event page record.

    Carries only the safe signal — ``seq`` (opaque monotonic, ``>= 1``, NOT
    required gap-free), a bounded ``family`` / ``kind`` token, a coarse
    ``observed_status``, and ``text_length`` (the only text signal). The ARS
    ``summary`` / raw text is never read or carried. ``__post_init__`` re-runs the
    full allowlist so a directly constructed or forged record fails closed.
    """

    seq: int
    family: str
    kind: str
    observed_status: str
    text_length: int

    def __post_init__(self) -> None:
        _check_live_progress_record_fields(self)

    def as_dict(self) -> dict[str, Any]:
        validate_live_progress_event_record(self)
        return {
            "seq": self.seq,
            "family": self.family,
            "kind": self.kind,
            "observed_status": self.observed_status,
            "text_length": self.text_length,
        }


def validate_live_progress_event_record(rec: Any) -> LiveProgressEventRecord:
    """Re-validate a record at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type or any unsafe field fails closed with the
    stable ``runtime_invalid_live_progress`` code, never echoing material.
    """

    if type(rec) is not LiveProgressEventRecord:
        _invalid()
    _check_live_progress_record_fields(rec)
    return rec


# --------------------------------------------------------------------------- #
# Top-level projection
# --------------------------------------------------------------------------- #
def _normalize_records(records: Any, *, allow_input: bool) -> tuple[LiveProgressEventRecord, ...]:
    if type(records) is list:
        if not allow_input:
            _invalid()
        items: Any = records
    elif type(records) is tuple:
        items = records
    else:
        _invalid()
    return tuple(validate_live_progress_event_record(rec) for rec in items)


def _raw_projection_dict(obj: Any) -> dict[str, Any]:
    return {
        "type": obj.type,
        "task_id": obj.task_id,
        "artifact_ref": obj.artifact_ref,
        "available": obj.available,
        "supervisor_state": obj.supervisor_state,
        "schema_version": obj.schema_version,
        "progress_last_seq": obj.progress_last_seq,
        "progress_event_count": obj.progress_event_count,
        "observed_last_seq": obj.observed_last_seq,
        "observed_event_count": obj.observed_event_count,
        "resume_cursor": obj.resume_cursor,
        "has_more": obj.has_more,
        "stale": obj.stale,
        "records": [_raw_record_dict(rec) for rec in obj.records],
        "error_code": obj.error_code,
    }


def _expected_stale(*, progress_last_seq: int, observed_last_seq: int, has_more: bool) -> bool:
    """The canonical stale rule (plan §5.4): the durable, clock-free frontier check.

    Stale when the progress summary is behind the observed frontier, or when an
    exhausted read stream (``has_more`` False) is behind the summary's claim — the
    data is shown but must not be trusted as the fresh frontier.
    """

    return progress_last_seq < observed_last_seq or (
        has_more is False and progress_last_seq > observed_last_seq
    )


def _check_live_progress_fields(obj: Any, *, normalize: bool = False) -> None:
    """Exact fail-closed validation of a projection's fields.

    Enforces the full refs-only allowlist, the closed observation vocabulary, the
    record set (strictly increasing ``seq``, ``observed_last_seq`` / count
    agreement), the canonical ``stale`` rule, and the available / unavailable
    cross-field invariants, then runs ``scan_for_leak`` over the whole surface. It
    never echoes rejected material.
    """

    try:
        type_ = obj.type
        task_id = obj.task_id
        artifact_ref = obj.artifact_ref
        available = obj.available
        supervisor_state = obj.supervisor_state
        schema_version = obj.schema_version
        progress_last_seq = obj.progress_last_seq
        progress_event_count = obj.progress_event_count
        observed_last_seq = obj.observed_last_seq
        observed_event_count = obj.observed_event_count
        resume_cursor = obj.resume_cursor
        has_more = obj.has_more
        stale = obj.stale
        records = obj.records
        error_code = obj.error_code
    except AttributeError:
        _invalid()

    if type(type_) is not str or type_ != LIVE_PROGRESS_PROJECTION_TYPE:
        _invalid()
    if task_id is not None:
        safe_task_id(task_id, code=RUNTIME_INVALID_LIVE_PROGRESS)
    _safe_artifact_ref(artifact_ref)
    is_available = _check_bool(available)
    if type(supervisor_state) is not str or supervisor_state not in SUPERVISOR_OBSERVED_STATES:
        _invalid()
    schema_version = _check_count(schema_version)
    progress_last_seq = _check_count(progress_last_seq)
    progress_event_count = _check_count(progress_event_count)
    observed_last_seq = _check_count(observed_last_seq)
    observed_event_count = _check_count(observed_event_count)
    if resume_cursor is not None:
        _check_count(resume_cursor)
    has_more_b = _check_bool(has_more)
    stale_b = _check_bool(stale)
    if error_code is not None and (type(error_code) is not str or error_code not in LIVE_PROGRESS_STABLE_CODES):
        _invalid()

    safe_records = _normalize_records(records, allow_input=normalize)
    if len(safe_records) != observed_event_count:
        _invalid()
    prev = 0
    for rec in safe_records:
        if rec.seq <= prev:  # strictly increasing across the page
            _invalid()
        prev = rec.seq
    if observed_last_seq != (safe_records[-1].seq if safe_records else 0):
        _invalid()

    if is_available:
        if error_code is not None:
            _invalid()
        if stale_b is not _expected_stale(
            progress_last_seq=progress_last_seq,
            observed_last_seq=observed_last_seq,
            has_more=has_more_b,
        ):
            _invalid()
        if not safe_records and (
            observed_last_seq != 0
            or observed_event_count != 0
            or resume_cursor is not None
            or has_more_b is not False
        ):
            _invalid()
    else:
        if error_code is None or error_code not in LIVE_PROGRESS_STABLE_CODES:
            _invalid()
        if (
            safe_records
            or observed_last_seq != 0
            or observed_event_count != 0
            or resume_cursor is not None
            or has_more_b is not False
            or stale_b is not False
            or supervisor_state != "unknown"
            or schema_version != 0
            or progress_last_seq != 0
            or progress_event_count != 0
        ):
            _invalid()

    if normalize:
        object.__setattr__(obj, "records", safe_records)

    if scan_for_leak(_raw_projection_dict(obj)) is not None:
        _invalid()


@dataclass(frozen=True)
class LiveProgressProjection:
    """Frozen, refs-only safe read-model of one supervised run's live progress.

    A ``list`` of ``records`` supplied to the constructor is normalized to an
    immutable tuple of validated :class:`LiveProgressEventRecord` during
    construction, and ``__post_init__`` re-runs the full fail-closed allowlist so a
    directly-constructed or forged projection fails closed instead of being
    trusted. ``as_dict`` / ``serialize_...`` re-validate before emitting.
    """

    type: str
    task_id: str | None
    artifact_ref: str
    available: bool
    supervisor_state: str
    schema_version: int
    progress_last_seq: int
    progress_event_count: int
    observed_last_seq: int
    observed_event_count: int
    resume_cursor: int | None
    has_more: bool
    stale: bool
    records: Any
    error_code: str | None

    def __post_init__(self) -> None:
        _check_live_progress_fields(self, normalize=True)

    def as_dict(self) -> dict[str, Any]:
        validate_live_progress_projection(self)
        return {
            "type": self.type,
            "task_id": self.task_id,
            "artifact_ref": self.artifact_ref,
            "available": self.available,
            "supervisor_state": self.supervisor_state,
            "schema_version": self.schema_version,
            "progress_last_seq": self.progress_last_seq,
            "progress_event_count": self.progress_event_count,
            "observed_last_seq": self.observed_last_seq,
            "observed_event_count": self.observed_event_count,
            "resume_cursor": self.resume_cursor,
            "has_more": self.has_more,
            "stale": self.stale,
            "records": [rec.as_dict() for rec in self.records],
            "error_code": self.error_code,
        }


def validate_live_progress_projection(obj: Any) -> LiveProgressProjection:
    """Re-validate a projection at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type or any unsafe / inconsistent field fails
    closed with the stable ``runtime_invalid_live_progress`` code, never echoing
    material.
    """

    if type(obj) is not LiveProgressProjection:
        _invalid()
    _check_live_progress_fields(obj)
    return obj


# --------------------------------------------------------------------------- #
# Injected reader boundary
# --------------------------------------------------------------------------- #
class _ReaderUnavailable(Exception):
    """Module-local: the ARS caller library is not importable on this host.

    The builder maps it to a ``live_progress_unavailable`` projection so no
    ``ImportError`` ever escapes to the caller.
    """


def _import_caller_events() -> Any:
    """Lazily import the ARS caller events module — NEVER at module top level.

    Any import failure (an environment without the ``agent-run-supervisor``
    extra installed) is collapsed to :class:`_ReaderUnavailable` with no
    chained raw exception text.
    """

    try:
        return importlib.import_module(_ARS_CALLER_EVENTS_MODULE)
    except Exception:
        raise _ReaderUnavailable from None


@runtime_checkable
class LiveProgressReader(Protocol):
    """The injected read-only boundary over ARS artifact progress + event pages."""

    def load_progress(self, artifact_dir: str) -> Any | None: ...

    def read_event_page(
        self, artifact_dir: str, *, after_seq: int | None = None, limit: int = 100
    ) -> Any: ...


class DefaultLiveProgressReader:
    """Default reader that lazily imports the ARS caller events module per call.

    The module resolves from the installed ``agent-run-supervisor``
    distribution; on an environment without the extra both methods fail closed
    via :class:`_ReaderUnavailable`, which the builder turns into a clean
    ``live_progress_unavailable`` projection. There is no top-level
    ``agent_run_supervisor`` import — a top-level import would break package import
    everywhere the library is missing.
    """

    def load_progress(self, artifact_dir: str) -> Any | None:
        return _import_caller_events().load_progress(artifact_dir)

    def read_event_page(
        self, artifact_dir: str, *, after_seq: int | None = None, limit: int = 100
    ) -> Any:
        return _import_caller_events().read_event_page(
            artifact_dir, after_seq=after_seq, limit=limit
        )


# --------------------------------------------------------------------------- #
# Builder
# --------------------------------------------------------------------------- #
def _validate_after_seq(after_seq: Any) -> int | None:
    if after_seq is None:
        return None
    # bool is an int subclass — exclude it so a flag can't pose as a cursor.
    if type(after_seq) is not int or after_seq < 0 or after_seq > _MAX_COUNT:
        _invalid()
    return after_seq


def _validate_limit(limit: Any) -> int:
    if type(limit) is not int or limit < 1 or limit > 1000:
        _invalid()
    return limit


def _unavailable(artifact_ref: str, task_id: str | None, error_code: str) -> LiveProgressProjection:
    return LiveProgressProjection(
        type=LIVE_PROGRESS_PROJECTION_TYPE,
        task_id=task_id,
        artifact_ref=artifact_ref,
        available=False,
        supervisor_state="unknown",
        schema_version=0,
        progress_last_seq=0,
        progress_event_count=0,
        observed_last_seq=0,
        observed_event_count=0,
        resume_cursor=None,
        has_more=False,
        stale=False,
        records=(),
        error_code=error_code,
    )


def _normalize_kind(value: Any) -> str:
    """Normalize the producer's nullable ``kind`` to a safe closed token.

    The ARS ``EventRecord`` declares ``kind`` nullable (lifecycle records like
    ``run_started`` / ``run_completed`` omit it), so a missing / ``None`` value
    normalizes to the safe closed token ``unknown`` — never echoed raw material. A
    present token still runs the full :func:`_safe_token` allowlist, so a
    leaky / off-charset ``kind`` remains a fail-closed corrupt page.
    """

    if value is None:
        return "unknown"
    return _safe_token(value)


def _normalize_text_length(value: Any) -> int:
    """Normalize the producer's nullable ``text_length`` to a bounded int.

    ``text_length`` is nullable in the ARS shape (records without a text delta omit
    it), so a missing / ``None`` value normalizes to ``0``. A present value still
    runs :func:`_safe_count`, so a negative / ``bool`` / oversized / non-``int``
    ``text_length`` remains a fail-closed corrupt page.
    """

    if value is None:
        return 0
    return _safe_count(value, code=RUNTIME_INVALID_LIVE_PROGRESS)


def _map_record(raw: Any) -> LiveProgressEventRecord:
    # ``seq`` / ``family`` are required and safe; ``kind`` / ``status`` /
    # ``text_length`` are nullable in the ARS producer shape and normalize to
    # closed safe tokens rather than failing the page.
    try:
        seq = raw.seq
        family = raw.family
    except AttributeError:
        _invalid()
    return LiveProgressEventRecord(
        seq=_safe_seq(seq),
        family=_safe_token(family),
        kind=_normalize_kind(getattr(raw, "kind", None)),
        observed_status=_map_observed_state(getattr(raw, "status", None)),
        text_length=_normalize_text_length(getattr(raw, "text_length", None)),
    )


def _map_records(raw_records: Any, *, after_seq: int | None) -> tuple[LiveProgressEventRecord, ...]:
    if type(raw_records) not in (tuple, list):
        _invalid()
    out: list[LiveProgressEventRecord] = []
    # after_seq is exclusive: the first record must be strictly greater than it.
    prev = after_seq if after_seq is not None else 0
    for raw in raw_records:
        rec = _map_record(raw)
        if rec.seq <= prev:  # strictly increasing, all > cursor; gaps allowed
            _invalid()
        prev = rec.seq
        out.append(rec)
    return tuple(out)


def _build_available(
    reader: Any,
    artifact_dir: str,
    artifact_ref: str,
    task_id: str | None,
    progress: Any,
    after_seq: int | None,
    limit: int,
) -> LiveProgressProjection:
    schema_version = _safe_count(progress.schema_version, code=RUNTIME_INVALID_LIVE_PROGRESS)
    supervisor_state = _map_observed_state(progress.state)
    progress_last_seq = _safe_count(progress.last_seq, code=RUNTIME_INVALID_LIVE_PROGRESS)
    progress_event_count = _safe_count(progress.event_count, code=RUNTIME_INVALID_LIVE_PROGRESS)

    page = reader.read_event_page(artifact_dir, after_seq=after_seq, limit=limit)
    records = _map_records(page.records, after_seq=after_seq)
    observed_event_count = len(records)
    observed_last_seq = records[-1].seq if records else 0

    if records:
        resume_cursor = _safe_optional_cursor(page.next_cursor)
        has_more = _check_bool(page.has_more)
    else:
        # A legitimate "just started" page carries no resumable frontier.
        resume_cursor = None
        has_more = False

    stale = _expected_stale(
        progress_last_seq=progress_last_seq,
        observed_last_seq=observed_last_seq,
        has_more=has_more,
    )

    return validate_live_progress_projection(
        LiveProgressProjection(
            type=LIVE_PROGRESS_PROJECTION_TYPE,
            task_id=task_id,
            artifact_ref=artifact_ref,
            available=True,
            supervisor_state=supervisor_state,
            schema_version=schema_version,
            progress_last_seq=progress_last_seq,
            progress_event_count=progress_event_count,
            observed_last_seq=observed_last_seq,
            observed_event_count=observed_event_count,
            resume_cursor=resume_cursor,
            has_more=has_more,
            stale=stale,
            records=records,
            error_code=None,
        )
    )


def build_live_progress_projection(
    reader: LiveProgressReader,
    artifact_dir: str,
    artifact_ref: str,
    *,
    task_id: str | None = None,
    after_seq: int | None = None,
    limit: int = 100,
) -> LiveProgressProjection:
    """Build a refs-only projection of one cursor page + progress summary.

    ``artifact_dir`` (a real path) is passed to ``reader`` only and never stored or
    scanned; ``artifact_ref`` is the safe public handle. Missing progress or an
    unavailable reader (the default host path — the ARS library is absent) yields a
    ``live_progress_unavailable`` projection; a ``ValueError`` / reader exception /
    off-contract record yields a ``live_progress_corrupt`` projection — never a
    raised exception and never a raw echo of the offending material. The ARS
    ``seq`` / ``next_cursor`` is a foreign read-model cursor: it is surfaced as the
    resume cursor but never fed into ``TaskEventLog``.
    """

    safe_ref = _safe_artifact_ref(artifact_ref)
    safe_task = None if task_id is None else safe_task_id(task_id, code=RUNTIME_INVALID_LIVE_PROGRESS)
    if type(artifact_dir) is not str or artifact_dir == "":
        _invalid()
    safe_after = _validate_after_seq(after_seq)
    safe_limit = _validate_limit(limit)

    try:
        progress = reader.load_progress(artifact_dir)
    except _ReaderUnavailable:
        return _unavailable(safe_ref, safe_task, LIVE_PROGRESS_UNAVAILABLE)
    except Exception:
        return _unavailable(safe_ref, safe_task, LIVE_PROGRESS_CORRUPT)

    if progress is None:
        return _unavailable(safe_ref, safe_task, LIVE_PROGRESS_UNAVAILABLE)

    try:
        return _build_available(reader, artifact_dir, safe_ref, safe_task, progress, safe_after, safe_limit)
    except _ReaderUnavailable:
        return _unavailable(safe_ref, safe_task, LIVE_PROGRESS_UNAVAILABLE)
    except Exception:
        return _unavailable(safe_ref, safe_task, LIVE_PROGRESS_CORRUPT)


def serialize_live_progress_projection(obj: LiveProgressProjection) -> bytes:
    """Byte-stable canonical JSON serialization after full re-validation."""

    validated = validate_live_progress_projection(obj)
    return json.dumps(validated.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


__all__ = [
    "RUNTIME_INVALID_LIVE_PROGRESS",
    "LIVE_PROGRESS_UNAVAILABLE",
    "LIVE_PROGRESS_CORRUPT",
    "LIVE_PROGRESS_STABLE_CODES",
    "LIVE_PROGRESS_PROJECTION_TYPE",
    "SUPERVISOR_OBSERVED_STATES",
    "OBSERVED_EVENT_STATUSES",
    "LiveProgressReader",
    "DefaultLiveProgressReader",
    "LiveProgressEventRecord",
    "LiveProgressProjection",
    "build_live_progress_projection",
    "validate_live_progress_projection",
    "validate_live_progress_event_record",
    "serialize_live_progress_projection",
]
