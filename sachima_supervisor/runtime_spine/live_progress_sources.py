"""PR-LS2 Runtime Spine — host-owned live-progress source binding.

This module is the local/offline **binding seam** between a locally tracked
``AgentRunSupervisorPort`` session and the private artifact it reads live
progress from. It resolves a ``(task_id, session_id)`` / :class:`SessionRef`
identity to three things:

* a **tagged private locator** that is reader-only — under the default
  ``artifact_file`` kind it is an ``artifact_dir`` (a real filesystem path);
  under ``arsd_run`` it is a private ``run_id``. It is passed to the injected
  live-progress reader only and is **never** serialized, logged, or scanned
  into any public projection / source output;
* a **safe** ``artifact_ref`` (a bounded public handle, never a path); and
* a foreign ``last_seen_cursor`` — an agent-run-supervisor live-progress
  read-model cursor. Sachima's ``TaskEventLog`` stays the sole per-``task_id``
  seq authority; this cursor is surfaced/stored but is never appended to it.

The public :class:`LiveProgressSource` value object carries only the safe metadata
(``type`` / ``task_id`` / ``session_id`` / ``artifact_ref`` / ``last_seen_cursor``
/ ``source_kind``); it has no locator field, so it structurally cannot serialize
the private path or a raw ``run_id``. The host-owned :class:`LiveProgressSourceBindings` store holds the private
``artifact_dir`` alongside the safe source, hands the real path only to the
builder's reader, and returns only the safe metadata to any serialization path.

``build_agent_run_supervisor_live_workbench_from_source`` resolves a binding and
delegates to the PR-LS1 ``build_agent_run_supervisor_live_workbench_view`` — using
the bound ``artifact_dir`` for the reader, ``artifact_ref`` as the public handle,
and ``after_seq = last_seen_cursor`` — then leaves cursor advancement to the
explicit :meth:`LiveProgressSourceBindings.update_last_seen_cursor`. Binding,
resolving, building, and serializing are pure and side-effect-free: no event
append, no work launch, no runtime / Temporal / process start, and no Gateway /
IM / delivery call. There is no top-level ``agent_run_supervisor`` import — the
producer library is reached only through the injected reader the builder receives.
Forbidden terms below are no-leak denylist boundary prose, never behavior.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any, NoReturn

from .agent_run_supervisor_live_workbench import (
    AgentRunSupervisorLiveWorkbenchView,
    build_agent_run_supervisor_live_workbench_view,
)
from .agent_run_supervisor_port import AgentRunSupervisorPort
from .events import SpineError, _safe_id, safe_task_id, scan_for_leak
from .execution_port import LivenessState, SessionRef, validate_session_ref
from .live_progress_projection import LiveProgressReader
from .registry import TaskRegistry
from .supervisor_turn_backend import (
    SOURCE_KIND_ARTIFACT_FILE,
    SUPERVISOR_SOURCE_KINDS,
)

# --------------------------------------------------------------------------- #
# Stable code (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_LIVE_PROGRESS_SOURCE = "runtime_invalid_live_progress_source"
LIVE_PROGRESS_SOURCE_STABLE_CODES = frozenset({RUNTIME_INVALID_LIVE_PROGRESS_SOURCE})
LIVE_PROGRESS_SOURCE_TYPE = "sachima.runtime_spine.live_progress_source.v1"

#: Upper bound shared by the foreign read-model cursor (matches the projection).
_MAX_CURSOR = 1_000_000_000


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_LIVE_PROGRESS_SOURCE)


# --------------------------------------------------------------------------- #
# Field-level sanitizers (each fails closed with the module's invalid code)
# --------------------------------------------------------------------------- #
def _safe_source_task_id(value: Any) -> str:
    return safe_task_id(value, code=RUNTIME_INVALID_LIVE_PROGRESS_SOURCE)


def _safe_session_id(value: Any) -> str:
    if type(value) is not str or not value.startswith("sess_"):
        _invalid()
    return _safe_id(value, code=RUNTIME_INVALID_LIVE_PROGRESS_SOURCE)


def _safe_artifact_ref(value: Any) -> str:
    """A caller-supplied SAFE public handle (e.g. ``artifact_local_0``), never a path."""

    return _safe_id(value, code=RUNTIME_INVALID_LIVE_PROGRESS_SOURCE)


def _safe_cursor(value: Any) -> int | None:
    # bool is an int subclass — exclude it so a flag can't pose as a cursor.
    if value is None:
        return None
    if type(value) is not int or value < 0 or value > _MAX_CURSOR:
        _invalid()
    return value


def _safe_private_dir(value: Any) -> str:
    """Validate the PRIVATE reader-only locator.

    Rejected on: a non-string or an empty string. A private locator is
    legitimately allowed to carry filesystem material (an ``artifact_dir``) or a
    raw id (an ``arsd_run`` ``run_id``) — that is exactly why it is kept out of
    the serializable :class:`LiveProgressSource` and is only ever handed to the
    injected reader; it is never run through the no-leak scan or serialized.
    """

    if type(value) is not str or value == "":
        _invalid()
    return value


def _safe_source_kind(value: Any) -> str:
    """Validate the closed read-model source tag (``artifact_file``/``arsd_run``)."""

    if type(value) is not str or value not in SUPERVISOR_SOURCE_KINDS:
        _invalid()
    return value


# --------------------------------------------------------------------------- #
# Safe, serializable source metadata (NO artifact_dir field by construction)
# --------------------------------------------------------------------------- #
def _raw_source_dict(source: Any) -> dict[str, Any]:
    return {
        "type": source.type,
        "task_id": source.task_id,
        "session_id": source.session_id,
        "artifact_ref": source.artifact_ref,
        "last_seen_cursor": source.last_seen_cursor,
        "source_kind": source.source_kind,
    }


def _check_live_progress_source_fields(source: Any) -> None:
    """Exact fail-closed validation of a source's safe fields.

    Fails closed on: a forged ``type``; an unsafe ``task_id`` / ``session_id`` /
    ``artifact_ref``; a ``last_seen_cursor`` that is not ``None`` or an exact
    ``int`` in ``[0, _MAX_CURSOR]`` (``bool`` excluded); or any forbidden marker
    anywhere in the safe surface. It never echoes the rejected material.
    """

    try:
        source_type = source.type
        task_id = source.task_id
        session_id = source.session_id
        artifact_ref = source.artifact_ref
        last_seen_cursor = source.last_seen_cursor
        source_kind = source.source_kind
    except AttributeError:
        _invalid()

    if type(source_type) is not str or source_type != LIVE_PROGRESS_SOURCE_TYPE:
        _invalid()
    _safe_source_task_id(task_id)
    _safe_session_id(session_id)
    _safe_artifact_ref(artifact_ref)
    _safe_cursor(last_seen_cursor)
    _safe_source_kind(source_kind)

    if scan_for_leak(_raw_source_dict(source)) is not None:
        _invalid()


@dataclass(frozen=True)
class LiveProgressSource:
    """Frozen, refs-only, serializable source metadata for one bound session.

    Carries only the safe public signal — identity plus the ``source_kind`` tag,
    the safe ``artifact_ref`` handle (an ``artifact_``/``turn_`` handle under
    ``artifact_file``, a ``run_`` handle under ``arsd_run``), and the foreign
    ``last_seen_cursor``. It has **no** locator field, so it structurally cannot
    serialize the private reader path or a raw ``run_id``. ``__post_init__``
    re-runs the full allowlist so a directly-constructed or forged source fails
    closed, and ``as_dict`` / ``serialize_...`` re-validate before emitting.
    """

    type: str
    task_id: str
    session_id: str
    artifact_ref: str
    last_seen_cursor: int | None
    source_kind: str = SOURCE_KIND_ARTIFACT_FILE

    def __post_init__(self) -> None:
        _check_live_progress_source_fields(self)

    def as_dict(self) -> dict[str, Any]:
        validate_live_progress_source(self)
        return {
            "type": self.type,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "artifact_ref": self.artifact_ref,
            "last_seen_cursor": self.last_seen_cursor,
            "source_kind": self.source_kind,
        }


def validate_live_progress_source(source: Any) -> LiveProgressSource:
    """Re-validate a source at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type or any unsafe field fails closed with the
    stable ``runtime_invalid_live_progress_source`` code, never echoing material.
    """

    if type(source) is not LiveProgressSource:
        _invalid()
    _check_live_progress_source_fields(source)
    return source


def serialize_live_progress_source(source: LiveProgressSource) -> bytes:
    """Byte-stable canonical JSON serialization after full re-validation.

    Only the safe metadata is serialized; the private locator is not a field of
    :class:`LiveProgressSource` and cannot appear here.
    """

    validated = validate_live_progress_source(source)
    return json.dumps(validated.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


# --------------------------------------------------------------------------- #
# Private handoff — the safe source PLUS the reader-only private path
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, repr=False)
class ResolvedLiveProgressSource:
    """Host-owned handoff carrying the safe :class:`LiveProgressSource` plus the
    PRIVATE locator its ``source.source_kind`` tags.

    Under the default ``artifact_file`` kind the locator is a real reader-only
    path — hence the field name — and under ``arsd_run`` it is a private
    ``run_id``; either way it is meant only to be passed to the live-progress
    reader by the builder. This holder deliberately exposes no ``as_dict`` /
    ``serialize`` surface and opts out of dataclass ``repr`` so the private
    locator cannot leak through routine object logging. Serialize ``.source``
    when a public handle is needed.
    """

    source: LiveProgressSource
    artifact_dir: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", validate_live_progress_source(self.source))
        object.__setattr__(self, "artifact_dir", _safe_private_dir(self.artifact_dir))


# --------------------------------------------------------------------------- #
# Host-owned in-memory binding store
# --------------------------------------------------------------------------- #
def _coerce_key(ref: Any, session_id: Any) -> tuple[str, str]:
    """Resolve a lookup key from either a :class:`SessionRef` or a
    ``(task_id, session_id)`` pair, failing closed with the module's code."""

    if type(ref) is SessionRef:
        if session_id is not None:
            _invalid()
        try:
            validate_session_ref(ref)
        except SpineError:
            _invalid()
        return ref.task_id, ref.session_id
    return _safe_source_task_id(ref), _safe_session_id(session_id)


@dataclass
class LiveProgressSourceBindings:
    """In-memory, lock-guarded, host-owned map of session identity → source binding.

    Each binding stores the PRIVATE reader-only locator next to the safe
    :class:`LiveProgressSource`. ``resolve`` hands the private locator to the builder
    via a :class:`ResolvedLiveProgressSource`; ``resolve_source`` returns only the
    serializable safe metadata. The store owns its state (``_bindings`` / ``_lock``
    are ``init=False``), so the only construction is zero-arg
    ``LiveProgressSourceBindings()`` and no caller can seed a leaky binding through
    the constructor.
    """

    _bindings: dict[tuple[str, str], ResolvedLiveProgressSource] = field(
        default_factory=dict, init=False
    )
    _lock: threading.RLock = field(
        default_factory=threading.RLock, init=False, repr=False, compare=False
    )

    def bind(
        self,
        task_id: str,
        session_id: str,
        artifact_dir: str,
        artifact_ref: str,
        *,
        last_seen_cursor: int | None = None,
    ) -> LiveProgressSource:
        """Bind (upsert) a session identity to a private ``artifact_dir`` + safe source.

        The ``artifact_file`` special case of :meth:`bind_source`, kept as the
        name every offline/artifact caller already uses.
        """

        return self.bind_source(
            task_id,
            session_id,
            SOURCE_KIND_ARTIFACT_FILE,
            artifact_dir,
            artifact_ref,
            last_seen_cursor=last_seen_cursor,
        )

    def bind_source(
        self,
        task_id: str,
        session_id: str,
        source_kind: str,
        private_locator: str,
        artifact_ref: str,
        *,
        last_seen_cursor: int | None = None,
    ) -> LiveProgressSource:
        """Bind (upsert) a session identity to a tagged private locator + safe source.

        ``source_kind`` tags what the locator is: an ``artifact_dir`` under
        ``artifact_file``, a private ``run_id`` under ``arsd_run``. Validates
        every field, rejecting an unknown tag, a raw/leaky id/ref, or an
        empty/unsafe private locator before storing. Returns the safe
        :class:`LiveProgressSource`; the locator is held internally and never
        returned by any serialization path.
        """

        safe_task = _safe_source_task_id(task_id)
        safe_session = _safe_session_id(session_id)
        safe_kind = _safe_source_kind(source_kind)
        safe_locator = _safe_private_dir(private_locator)
        source = LiveProgressSource(
            type=LIVE_PROGRESS_SOURCE_TYPE,
            task_id=safe_task,
            session_id=safe_session,
            artifact_ref=_safe_artifact_ref(artifact_ref),
            last_seen_cursor=_safe_cursor(last_seen_cursor),
            source_kind=safe_kind,
        )
        with self._lock:
            self._bindings[(safe_task, safe_session)] = ResolvedLiveProgressSource(
                source=validate_live_progress_source(source), artifact_dir=safe_locator
            )
        return source

    def resolve(self, ref: Any, session_id: Any = None) -> ResolvedLiveProgressSource:
        """Resolve a :class:`SessionRef` / ``(task_id, session_id)`` to its binding.

        Returns the private handoff (safe source + reader-only locator). A
        missing / forged / mismatched key fails closed with the stable
        ``runtime_invalid_live_progress_source`` code and never echoes the key.
        """

        key = _coerce_key(ref, session_id)
        with self._lock:
            resolved = self._bindings.get(key)
        if resolved is None:
            _invalid()
        # Re-validate the safe half at the boundary; the locator stays private.
        validate_live_progress_source(resolved.source)
        return resolved

    def resolve_source(self, ref: Any, session_id: Any = None) -> LiveProgressSource:
        """Resolve only the safe, serializable :class:`LiveProgressSource` metadata."""

        return self.resolve(ref, session_id).source

    def update_last_seen_cursor(
        self, ref: Any, cursor: int | None, session_id: Any = None
    ) -> LiveProgressSource:
        """Explicitly record a new foreign ``last_seen_cursor`` for a binding.

        ``cursor`` comes from a freshly built view's ``resume_cursor`` — a foreign
        agent-run-supervisor read-model cursor. It is validated (``None`` or an
        exact non-negative bounded ``int``; ``bool`` rejected) and stored as the
        binding's ``last_seen_cursor``; it is never appended to ``TaskEventLog``.
        Returns the updated safe source.
        """

        key = _coerce_key(ref, session_id)
        safe_cursor = _safe_cursor(cursor)
        with self._lock:
            resolved = self._bindings.get(key)
            if resolved is None:
                _invalid()
            prior = resolved.source
            updated = LiveProgressSource(
                type=prior.type,
                task_id=prior.task_id,
                session_id=prior.session_id,
                artifact_ref=prior.artifact_ref,
                last_seen_cursor=safe_cursor,
                source_kind=prior.source_kind,
            )
            self._bindings[key] = ResolvedLiveProgressSource(
                source=updated, artifact_dir=resolved.artifact_dir
            )
        return updated


# --------------------------------------------------------------------------- #
# Builder — resolve a binding, then compose the PR-LS1 live workbench view
# --------------------------------------------------------------------------- #
def build_agent_run_supervisor_live_workbench_from_source(
    bindings: LiveProgressSourceBindings,
    registry: TaskRegistry,
    port: AgentRunSupervisorPort,
    ref: Any,
    progress_reader: LiveProgressReader,
    *,
    limit: int = 100,
    liveness: LivenessState | None = None,
) -> AgentRunSupervisorLiveWorkbenchView:
    """Build a PR-LS1 combined live workbench view from a resolved source binding.

    The binding is resolved for ``ref`` first: a missing/forged binding fails closed
    with the stable ``runtime_invalid_live_progress_source`` code. The PR-LS1
    ``build_agent_run_supervisor_live_workbench_view`` is then called with the bound
    private ``artifact_dir`` (passed to the injected reader only, never stored), the
    safe ``artifact_ref`` handle, and ``after_seq = source.last_seen_cursor``; that
    builder validates ``ref`` against ``registry`` / ``port`` and fails closed on an
    untracked/forged session with the stable PR3 ``runtime_invalid_session`` code.
    This function mutates nothing — cursor advancement is the caller's explicit
    :meth:`LiveProgressSourceBindings.update_last_seen_cursor` step, so the foreign
    read-model cursor never enters ``TaskEventLog``.
    """

    if type(bindings) is not LiveProgressSourceBindings:
        _invalid()
    resolved = bindings.resolve(ref)
    source = resolved.source
    return build_agent_run_supervisor_live_workbench_view(
        registry,
        port,
        ref,
        progress_reader,
        resolved.artifact_dir,
        source.artifact_ref,
        after_seq=source.last_seen_cursor,
        limit=limit,
        liveness=liveness,
    )


__all__ = [
    "RUNTIME_INVALID_LIVE_PROGRESS_SOURCE",
    "LIVE_PROGRESS_SOURCE_STABLE_CODES",
    "LIVE_PROGRESS_SOURCE_TYPE",
    "LiveProgressSource",
    "ResolvedLiveProgressSource",
    "LiveProgressSourceBindings",
    "build_agent_run_supervisor_live_workbench_from_source",
    "validate_live_progress_source",
    "serialize_live_progress_source",
]
