"""PR-LS4-B Runtime Spine — default-off live-progress display renderer.

This module is the Sachima-side **consumption/display surface** over the LS4-A
gated query output. It renders one PR-LS1
:class:`AgentRunSupervisorLiveWorkbenchView` into a frozen, refs-only
:class:`LiveProgressDisplay`: closed-vocabulary state tokens (the workbench task
status and the coarse supervisor observation), bounded counts, the foreign
resume cursor, ``has_more`` / ``stale`` observations, a per-``family`` event
aggregation, a stable ``error_code`` when the projection is unavailable /
corrupt, and deterministic ``display_lines`` built ONLY from a closed template
vocabulary plus already-validated tokens — never raw ARS ``summary`` free text,
platform ids, filesystem paths, secrets, exception text, or card JSON.

``display_task_live_progress`` composes the LS4-A default-off boundary with this
renderer: the activation gate is checked first inside
``query_task_live_progress`` — with no gate the display query fails closed with
the stable ``runtime_live_progress_query_disabled`` code and never calls the
injected reader, appends no ``TaskEventLog`` event, and updates no binding
cursor. Rendering itself is pure and read-only: the ARS cursor stays a foreign
read-model cursor that is displayed but never appended to ``TaskEventLog``, and
the supervisor's settled observation stays a runtime observation, never a
business verdict. ``display_lines`` are re-derived during validation from the
already-validated fields and compared for exact equality, so a forged or
tampered display carrying free text fails closed instead of being trusted.

Everything here is pure local/offline Python. Importing, rendering, validating,
or serializing starts no OS process, network listener, container, daemon,
durable Worker/service, Gateway, Feishu, or IM/delivery surface, and launches no
external runner — the producer library is reached only through the injected
reader the LS4-A query receives (no top-level ``agent_run_supervisor`` import).
Forbidden terms in this prose are no-leak / denied-surface boundary canaries
only, never behavior.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, NoReturn

from .agent_run_supervisor_live_workbench import (
    validate_agent_run_supervisor_live_workbench_view,
)
from .agent_run_supervisor_port import AgentRunSupervisorPort
from .events import TERMINAL_STATUSES, SpineError, _safe_id, safe_task_id, scan_for_leak
from .execution_port import LivenessState
from .live_progress_projection import (
    LIVE_PROGRESS_STABLE_CODES,
    SUPERVISOR_OBSERVED_STATES,
    LiveProgressReader,
)
from .live_progress_query import (
    LiveProgressQueryActivationGate,
    LiveProgressQueryService,
    query_task_live_progress,
)
from .live_progress_sources import LiveProgressSourceBindings
from .registry import TaskRegistry

# --------------------------------------------------------------------------- #
# Stable code (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY = "runtime_invalid_live_progress_display"
LIVE_PROGRESS_DISPLAY_STABLE_CODES = frozenset({RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY})
LIVE_PROGRESS_DISPLAY_TYPE = "sachima.runtime_spine.live_progress_display.v1"

#: The workbench's closed task-status vocabulary (the spine's existing stable
#: observed-state words); terminal-ness must agree with the spine's terminal set.
_DISPLAY_TASK_STATUSES = frozenset(
    {"running", "permission_wait", "completed", "failed", "cancelled"}
)

#: Bounded ARS ``family`` token charset (mirrors the projection's token rule).
_SAFE_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

#: Bound shared with the projection's cursors / counts.
_MAX_COUNT = 1_000_000_000


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY)


# --------------------------------------------------------------------------- #
# Field-level sanitizers (each fails closed with the module's stable code)
# --------------------------------------------------------------------------- #
def _check_bool(value: Any) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _check_count(value: Any) -> int:
    # bool is an int subclass — exclude it so a flag can't pose as a count.
    if type(value) is not int or value < 0 or value > _MAX_COUNT:
        _invalid()
    return value


def _check_optional_cursor(value: Any) -> int | None:
    if value is None:
        return None
    return _check_count(value)


def _safe_display_session_id(value: Any) -> str:
    if type(value) is not str or not value.startswith("sess_"):
        _invalid()
    return _safe_id(value, code=RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY)


def _check_family_counts(value: Any, *, observed_event_count: int) -> None:
    """Validate the closed per-``family`` aggregation.

    Fails closed on: a non-tuple; an entry that is not a ``(family, count)``
    pair; a family outside the bounded token charset or carrying a forbidden
    marker; a non-``int`` / ``bool`` / non-positive / oversized count; families
    not strictly sorted and unique; or counts that do not sum to the displayed
    ``observed_event_count``.
    """

    if type(value) is not tuple:
        _invalid()
    total = 0
    prev = ""
    for entry in value:
        if type(entry) is not tuple or len(entry) != 2:
            _invalid()
        family, count = entry
        if type(family) is not str or _SAFE_TOKEN_RE.fullmatch(family) is None:
            _invalid()
        if scan_for_leak(family) is not None:
            _invalid()
        # bool is rejected by the exact-type check, so a flag can't pose as a count.
        if type(count) is not int or count < 1 or count > _MAX_COUNT:
            _invalid()
        if family <= prev:  # strictly sorted + unique
            _invalid()
        prev = family
        total += count
    if total != observed_event_count:
        _invalid()


# --------------------------------------------------------------------------- #
# Canonical display lines — a closed template vocabulary over validated fields
# --------------------------------------------------------------------------- #
def _render_display_lines(
    *,
    task_id: str,
    session_id: str,
    task_status: str,
    supervisor_state: str,
    progress_available: bool,
    progress_error_code: str | None,
    progress_event_count: int,
    observed_event_count: int,
    resume_cursor: int | None,
    has_more: bool,
    stale: bool,
    family_counts: tuple[tuple[str, int], ...],
) -> tuple[str, ...]:
    """Deterministically render the closed-template display lines.

    Every substitution slot carries an already-validated closed token, safe id,
    or bounded int — free text structurally cannot enter a line. Validation
    re-runs this function and requires exact equality, so tampered lines fail
    closed.
    """

    lines = [f"task {task_id} session {session_id} status {task_status}"]
    if not progress_available:
        lines.append(f"live unavailable code {progress_error_code}")
        return tuple(lines)
    lines.append(
        f"live {supervisor_state} events {progress_event_count} shown {observed_event_count}"
    )
    cursor_word = "none" if resume_cursor is None else str(resume_cursor)
    more_word = "yes" if has_more else "no"
    lines.append(f"cursor {cursor_word} more {more_word}")
    if family_counts:
        lines.append(
            "families " + " ".join(f"{family} {count}" for family, count in family_counts)
        )
    if stale:
        lines.append("stale snapshot")
    return tuple(lines)


def _raw_display_dict(view: Any) -> dict[str, Any]:
    return {
        "type": view.type,
        "task_id": view.task_id,
        "session_id": view.session_id,
        "artifact_ref": view.artifact_ref,
        "task_status": view.task_status,
        "terminal": view.terminal,
        "supervisor_state": view.supervisor_state,
        "progress_available": view.progress_available,
        "progress_error_code": view.progress_error_code,
        "progress_event_count": view.progress_event_count,
        "observed_event_count": view.observed_event_count,
        "resume_cursor": view.resume_cursor,
        "has_more": view.has_more,
        "stale": view.stale,
        "family_counts": dict(view.family_counts),
        "display_lines": list(view.display_lines),
    }


def _check_display_fields(view: Any) -> None:
    """Exact fail-closed validation of a display's fields.

    Enforces the closed status vocabularies, the terminal agreement with the
    spine's terminal set, the available / unavailable cross-field invariants,
    the per-``family`` aggregation, exact equality of ``display_lines`` with
    their canonical re-render, and the no-leak scan over the whole surface. It
    never echoes the rejected material.
    """

    try:
        view_type = view.type
        task_id = view.task_id
        session_id = view.session_id
        artifact_ref = view.artifact_ref
        task_status = view.task_status
        terminal = view.terminal
        supervisor_state = view.supervisor_state
        progress_available = view.progress_available
        progress_error_code = view.progress_error_code
        progress_event_count = view.progress_event_count
        observed_event_count = view.observed_event_count
        resume_cursor = view.resume_cursor
        has_more = view.has_more
        stale = view.stale
        family_counts = view.family_counts
        display_lines = view.display_lines
    except AttributeError:
        _invalid()

    if type(view_type) is not str or view_type != LIVE_PROGRESS_DISPLAY_TYPE:
        _invalid()
    safe_task_id(task_id, code=RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY)
    _safe_display_session_id(session_id)
    _safe_id(artifact_ref, code=RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY)

    if type(task_status) is not str or task_status not in _DISPLAY_TASK_STATUSES:
        _invalid()
    if _check_bool(terminal) is not (task_status in TERMINAL_STATUSES):
        _invalid()
    if type(supervisor_state) is not str or supervisor_state not in SUPERVISOR_OBSERVED_STATES:
        _invalid()

    available = _check_bool(progress_available)
    if available:
        if progress_error_code is not None:
            _invalid()
    elif (
        type(progress_error_code) is not str
        or progress_error_code not in LIVE_PROGRESS_STABLE_CODES
    ):
        _invalid()

    _check_count(progress_event_count)
    observed = _check_count(observed_event_count)
    _check_optional_cursor(resume_cursor)
    has_more_b = _check_bool(has_more)
    stale_b = _check_bool(stale)
    _check_family_counts(family_counts, observed_event_count=observed)

    if not available and (
        supervisor_state != "unknown"
        or progress_event_count != 0
        or observed != 0
        or resume_cursor is not None
        or has_more_b is not False
        or stale_b is not False
        or family_counts != ()
    ):
        _invalid()

    if type(display_lines) is not tuple or any(type(line) is not str for line in display_lines):
        _invalid()
    if display_lines != _render_display_lines(
        task_id=task_id,
        session_id=session_id,
        task_status=task_status,
        supervisor_state=supervisor_state,
        progress_available=available,
        progress_error_code=progress_error_code,
        progress_event_count=progress_event_count,
        observed_event_count=observed,
        resume_cursor=resume_cursor,
        has_more=has_more_b,
        stale=stale_b,
        family_counts=family_counts,
    ):
        _invalid()

    if scan_for_leak(_raw_display_dict(view)) is not None:
        _invalid()


@dataclass(frozen=True)
class LiveProgressDisplay:
    """Frozen, refs-only display model of one supervised run's live progress.

    Carries only closed-vocabulary state tokens, bounded counts, the foreign
    resume cursor, the stable ``error_code`` on the unavailable path, the
    per-``family`` aggregation, and the canonical ``display_lines``.
    ``__post_init__`` re-runs the full fail-closed allowlist (including the
    exact line re-render check) so a directly constructed or forged display
    fails closed instead of being trusted, and ``as_dict`` / ``serialize_...``
    re-validate before emitting.
    """

    type: str
    task_id: str
    session_id: str
    artifact_ref: str
    task_status: str
    terminal: bool
    supervisor_state: str
    progress_available: bool
    progress_error_code: str | None
    progress_event_count: int
    observed_event_count: int
    resume_cursor: int | None
    has_more: bool
    stale: bool
    family_counts: Any
    display_lines: Any

    def __post_init__(self) -> None:
        _check_display_fields(self)

    def as_dict(self) -> dict[str, Any]:
        validate_live_progress_display(self)
        return _raw_display_dict(self)


def validate_live_progress_display(view: Any) -> LiveProgressDisplay:
    """Re-validate a display at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type, any unsafe / inconsistent field, or a
    tampered ``display_lines`` set fails closed with the stable
    ``runtime_invalid_live_progress_display`` code, never echoing material.
    """

    if type(view) is not LiveProgressDisplay:
        _invalid()
    _check_display_fields(view)
    return view


def serialize_live_progress_display(view: LiveProgressDisplay) -> bytes:
    """Byte-stable canonical JSON serialization after full re-validation."""

    validated = validate_live_progress_display(view)
    return json.dumps(validated.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


# --------------------------------------------------------------------------- #
# Renderer — pure, read-only consumption of the safe combined view
# --------------------------------------------------------------------------- #
def render_live_progress_display(view: Any) -> LiveProgressDisplay:
    """Render one validated combined workbench view into a display model.

    The input is re-validated through the PR-LS1 boundary first; a forged /
    non-view input fails closed with this module's stable code and never echoes
    material. Rendering consumes only the already-sanitized child dicts: the
    workbench task status (the spine's closed observed-state vocabulary, with
    ``completed`` / ``failed`` / ``cancelled`` as the terminal words), the
    coarse supervisor observation, bounded counts, the foreign resume cursor,
    and a per-``family`` aggregation of the projected event records. It mutates
    nothing and appends nothing.
    """

    try:
        validated = validate_agent_run_supervisor_live_workbench_view(view)
    except SpineError:
        _invalid()

    data = validated.as_dict()
    workbench = data["workbench"]
    live_progress = data["live_progress"]

    families: dict[str, int] = {}
    for record in live_progress["records"]:
        families[record["family"]] = families.get(record["family"], 0) + 1
    family_counts = tuple(sorted(families.items()))

    lines = _render_display_lines(
        task_id=data["task_id"],
        session_id=data["session_id"],
        task_status=workbench["status"],
        supervisor_state=live_progress["supervisor_state"],
        progress_available=data["progress_available"],
        progress_error_code=data["progress_error_code"],
        progress_event_count=live_progress["progress_event_count"],
        observed_event_count=live_progress["observed_event_count"],
        resume_cursor=data["resume_cursor"],
        has_more=data["has_more"],
        stale=data["stale"],
        family_counts=family_counts,
    )
    return validate_live_progress_display(
        LiveProgressDisplay(
            type=LIVE_PROGRESS_DISPLAY_TYPE,
            task_id=data["task_id"],
            session_id=data["session_id"],
            artifact_ref=live_progress["artifact_ref"],
            task_status=workbench["status"],
            terminal=workbench["terminal"],
            supervisor_state=live_progress["supervisor_state"],
            progress_available=data["progress_available"],
            progress_error_code=data["progress_error_code"],
            progress_event_count=live_progress["progress_event_count"],
            observed_event_count=live_progress["observed_event_count"],
            resume_cursor=data["resume_cursor"],
            has_more=data["has_more"],
            stale=data["stale"],
            family_counts=family_counts,
            display_lines=lines,
        )
    )


# --------------------------------------------------------------------------- #
# The gated display query — LS4-A default-off boundary + this renderer
# --------------------------------------------------------------------------- #
def display_task_live_progress(
    bindings: LiveProgressSourceBindings,
    registry: TaskRegistry,
    port: AgentRunSupervisorPort,
    progress_reader: LiveProgressReader,
    task_id: str,
    session_id: str,
    *,
    gate: LiveProgressQueryActivationGate | None = None,
    after_seq: int | None = None,
    limit: int = 100,
    liveness: LivenessState | None = None,
) -> LiveProgressDisplay:
    """Query one session's live progress through the LS4-A gate, then render it.

    The default-off activation ``gate`` is enforced first inside
    ``query_task_live_progress``: with no gate this fails closed with the stable
    ``runtime_live_progress_query_disabled`` code and never calls
    ``progress_reader``, appends no ``TaskEventLog`` event, and updates no
    binding cursor; a denied / forged gate fails closed with
    ``runtime_invalid_live_progress_query`` — again before any read. The
    rendered display is read-only: cursor advancement stays the caller's
    explicit PR-LS2 ``update_last_seen_cursor`` step.
    """

    view = query_task_live_progress(
        bindings,
        registry,
        port,
        progress_reader,
        task_id,
        session_id,
        gate=gate,
        after_seq=after_seq,
        limit=limit,
        liveness=liveness,
    )
    return render_live_progress_display(view)


@dataclass(frozen=True)
class LiveProgressDisplayService:
    """A default-off DI wrapper: the LS4-A query service plus this renderer.

    Wraps one :class:`LiveProgressQueryService`; the display service inherits its
    posture, so with the bundled service's ``gate=None`` (the default) every
    display query fails closed with ``runtime_live_progress_query_disabled``
    before any reader call. A non-service payload fails closed at construction.
    """

    query_service: LiveProgressQueryService

    def __post_init__(self) -> None:
        if type(self.query_service) is not LiveProgressQueryService:
            _invalid()

    def display_task_live_progress(
        self,
        task_id: str,
        session_id: str,
        *,
        after_seq: int | None = None,
        limit: int = 100,
        liveness: LivenessState | None = None,
    ) -> LiveProgressDisplay:
        """Query through the bundled default-off gate, then render the display."""

        return render_live_progress_display(
            self.query_service.query_task_live_progress(
                task_id, session_id, after_seq=after_seq, limit=limit, liveness=liveness
            )
        )


__all__ = [
    "RUNTIME_INVALID_LIVE_PROGRESS_DISPLAY",
    "LIVE_PROGRESS_DISPLAY_STABLE_CODES",
    "LIVE_PROGRESS_DISPLAY_TYPE",
    "LiveProgressDisplay",
    "LiveProgressDisplayService",
    "render_live_progress_display",
    "display_task_live_progress",
    "validate_live_progress_display",
    "serialize_live_progress_display",
]
