"""PR-LS3 Runtime Spine — agent-run-supervisor caller-API compatibility smoke.

A thin **local/offline** seam that reads already-written **synthetic** artifacts
(a ``progress.json`` summary + a ``normalized-events.jsonl`` cursor stream) through
the **real** ``agent_run_supervisor.hermes_caller.events`` caller/read API and maps
them into Sachima's existing refs-only, fail-closed read-models — the PR3
:class:`LiveProgressProjection` and the PR-LS1 combined live workbench view — plus
a small stable :class:`LiveProgressSmokeReport` that records only the smoke's
coarse outcome (``available`` / ``unavailable`` / ``corrupt``) and the already-safe
mirror fields.

This module is a **compatibility smoke, not a runtime feature**. It is pure and
side-effect-free: it reads files only, through the injected reader, and never
writes an artifact, appends a ``TaskEventLog`` event, launches a real AGENT /
runner / OS process, opens a network listener, starts a runtime / Temporal
service, or calls a Gateway / Feishu / IM / delivery surface. The producer library
is reached **only** lazily inside the existing :class:`DefaultLiveProgressReader`
(no top-level ``agent_run_supervisor`` import here) and resolves only from the
installed exact-pinned ``agent-run-supervisor`` distribution, so on an
environment without the extra every helper fails closed to a clean
``live_progress_unavailable`` report / projection without leaking the raw
import-error text.

Every public surface reuses the existing builders/validators and carries only the
already-sanitized safe signal: refs / safe handles / bounded counts / coarse
observed states / booleans / a foreign resume cursor / a stable ``error_code``.
The ARS ``summary`` free text, raw ``text`` / ``content`` / ``message`` / ``body``,
artifact filesystem paths, platform ids, secrets, and raw exception / import-error
strings are never carried. The foreign ARS ``seq`` / cursor stays a read-model
cursor and never enters Sachima's canonical ``TaskEventLog``. Forbidden terms in
this prose are no-leak / forbidden-surface boundary canaries only, never behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, NoReturn

from .agent_run_supervisor_live_workbench import (
    AgentRunSupervisorLiveWorkbenchView,
    build_agent_run_supervisor_live_workbench_view,
)
from .agent_run_supervisor_port import AgentRunSupervisorPort
from .events import SpineError, _safe_count, _safe_id, safe_task_id, scan_for_leak
from .execution_port import LivenessState
from .live_progress_projection import (
    LIVE_PROGRESS_CORRUPT,
    LIVE_PROGRESS_STABLE_CODES,
    LIVE_PROGRESS_UNAVAILABLE,
    DefaultLiveProgressReader,
    LiveProgressProjection,
    LiveProgressReader,
    build_live_progress_projection,
    validate_live_progress_projection,
)
from .registry import TaskRegistry

# --------------------------------------------------------------------------- #
# Stable codes / vocabulary (module-local; the message IS the code, never input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_LIVE_PROGRESS_SMOKE = "runtime_invalid_live_progress_smoke"
LIVE_PROGRESS_SMOKE_STABLE_CODES = frozenset({RUNTIME_INVALID_LIVE_PROGRESS_SMOKE})
LIVE_PROGRESS_SMOKE_REPORT_TYPE = (
    "sachima.runtime_spine.agent_run_supervisor_live_progress_smoke_report.v1"
)

#: Closed coarse outcome vocabulary for a smoke run (mirrors the projection's
#: availability / stable-code split; never a business verdict).
SMOKE_OUTCOMES = frozenset({"available", "unavailable", "corrupt"})

#: Bound shared with the projection's counts / cursors.
_MAX_COUNT = 1_000_000_000


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_LIVE_PROGRESS_SMOKE)


def _check_bool(value: Any) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _safe_artifact_ref(value: Any) -> str:
    """A caller-supplied SAFE handle (e.g. ``artifact_local_0``) — never a path."""

    return _safe_id(value, code=RUNTIME_INVALID_LIVE_PROGRESS_SMOKE)


def _safe_optional_cursor(value: Any) -> int | None:
    # bool is an int subclass — exclude it so a flag can't pose as a cursor.
    if value is None:
        return None
    if type(value) is not int or value < 0 or value > _MAX_COUNT:
        _invalid()
    return value


# --------------------------------------------------------------------------- #
# Stable smoke report
# --------------------------------------------------------------------------- #
def _raw_report_dict(report: Any) -> dict[str, Any]:
    return {
        "type": report.type,
        "outcome": report.outcome,
        "available": report.available,
        "error_code": report.error_code,
        "artifact_ref": report.artifact_ref,
        "task_id": report.task_id,
        "observed_event_count": report.observed_event_count,
        "resume_cursor": report.resume_cursor,
        "has_more": report.has_more,
        "stale": report.stale,
    }


def _check_smoke_report_fields(report: Any) -> None:
    """Exact fail-closed validation of a smoke report's fields.

    Fails closed on: a forged ``type``; an ``outcome`` outside the closed
    :data:`SMOKE_OUTCOMES`; an ``error_code`` that is not ``None`` or a projection
    stable code; an unsafe ``artifact_ref`` / ``task_id``; a negative / ``bool`` /
    oversized ``observed_event_count`` or ``resume_cursor``; an ``outcome`` /
    ``available`` / ``error_code`` cross-field disagreement; a non-``available``
    report that still carries an observed frontier; or any forbidden marker
    anywhere in the report. It never echoes the rejected material.
    """

    try:
        report_type = report.type
        outcome = report.outcome
        available = report.available
        error_code = report.error_code
        artifact_ref = report.artifact_ref
        task_id = report.task_id
        observed_event_count = report.observed_event_count
        resume_cursor = report.resume_cursor
        has_more = report.has_more
        stale = report.stale
    except AttributeError:
        _invalid()

    if type(report_type) is not str or report_type != LIVE_PROGRESS_SMOKE_REPORT_TYPE:
        _invalid()
    if type(outcome) is not str or outcome not in SMOKE_OUTCOMES:
        _invalid()
    is_available = _check_bool(available)
    if error_code is not None and (
        type(error_code) is not str or error_code not in LIVE_PROGRESS_STABLE_CODES
    ):
        _invalid()
    _safe_artifact_ref(artifact_ref)
    if task_id is not None:
        safe_task_id(task_id, code=RUNTIME_INVALID_LIVE_PROGRESS_SMOKE)
    _safe_count(observed_event_count, code=RUNTIME_INVALID_LIVE_PROGRESS_SMOKE)
    _safe_optional_cursor(resume_cursor)
    has_more_b = _check_bool(has_more)
    stale_b = _check_bool(stale)

    # outcome ⇄ available ⇄ error_code are a closed, mutually-consistent triple.
    if is_available:
        if outcome != "available" or error_code is not None:
            _invalid()
    else:
        if error_code == LIVE_PROGRESS_UNAVAILABLE:
            if outcome != "unavailable":
                _invalid()
        elif error_code == LIVE_PROGRESS_CORRUPT:
            if outcome != "corrupt":
                _invalid()
        else:
            _invalid()
        # An unavailable / corrupt smoke carries no observed frontier.
        if (
            observed_event_count != 0
            or resume_cursor is not None
            or has_more_b is not False
            or stale_b is not False
        ):
            _invalid()

    if scan_for_leak(_raw_report_dict(report)) is not None:
        _invalid()


@dataclass(frozen=True)
class LiveProgressSmokeReport:
    """Frozen, refs-only stable outcome report of one caller-API compatibility smoke.

    Carries only the coarse outcome plus the already-safe mirror fields of the
    underlying :class:`LiveProgressProjection` (identity handle, bounded observed
    count, foreign resume cursor, booleans, stable ``error_code``). It never carries
    the artifact path, the ARS ``summary`` / raw text, or a raw exception / import
    error. ``__post_init__`` re-runs the full allowlist so a directly constructed or
    forged report fails closed, and ``as_dict`` / ``serialize_...`` re-validate
    before emitting.
    """

    type: str
    outcome: str
    available: bool
    error_code: str | None
    artifact_ref: str
    task_id: str | None
    observed_event_count: int
    resume_cursor: int | None
    has_more: bool
    stale: bool

    def __post_init__(self) -> None:
        _check_smoke_report_fields(self)

    def as_dict(self) -> dict[str, Any]:
        validate_live_progress_smoke_report(self)
        return {
            "type": self.type,
            "outcome": self.outcome,
            "available": self.available,
            "error_code": self.error_code,
            "artifact_ref": self.artifact_ref,
            "task_id": self.task_id,
            "observed_event_count": self.observed_event_count,
            "resume_cursor": self.resume_cursor,
            "has_more": self.has_more,
            "stale": self.stale,
        }


def validate_live_progress_smoke_report(report: Any) -> LiveProgressSmokeReport:
    """Re-validate a report at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type or any unsafe / inconsistent field fails
    closed with the stable ``runtime_invalid_live_progress_smoke`` code, never
    echoing material.
    """

    if type(report) is not LiveProgressSmokeReport:
        _invalid()
    _check_smoke_report_fields(report)
    return report


def build_live_progress_smoke_report(projection: Any) -> LiveProgressSmokeReport:
    """Reduce a validated :class:`LiveProgressProjection` to a stable smoke report.

    The projection is re-validated first (a forged / leaky projection fails closed),
    then its availability / stable ``error_code`` is mapped to the closed
    :data:`SMOKE_OUTCOMES`. An available smoke mirrors the projection's observed
    frontier; an unavailable / corrupt smoke carries only the coarse outcome and no
    frontier. No raw material is read or echoed.
    """

    proj = validate_live_progress_projection(projection)
    if proj.available:
        outcome = "available"
        error_code = None
        observed_event_count = proj.observed_event_count
        resume_cursor = proj.resume_cursor
        has_more = proj.has_more
        stale = proj.stale
    else:
        if proj.error_code == LIVE_PROGRESS_UNAVAILABLE:
            outcome = "unavailable"
        elif proj.error_code == LIVE_PROGRESS_CORRUPT:
            outcome = "corrupt"
        else:
            _invalid()
        error_code = proj.error_code
        observed_event_count = 0
        resume_cursor = None
        has_more = False
        stale = False

    return validate_live_progress_smoke_report(
        LiveProgressSmokeReport(
            type=LIVE_PROGRESS_SMOKE_REPORT_TYPE,
            outcome=outcome,
            available=proj.available,
            error_code=error_code,
            artifact_ref=proj.artifact_ref,
            task_id=proj.task_id,
            observed_event_count=observed_event_count,
            resume_cursor=resume_cursor,
            has_more=has_more,
            stale=stale,
        )
    )


def serialize_live_progress_smoke_report(report: LiveProgressSmokeReport) -> bytes:
    """Byte-stable canonical JSON serialization after full re-validation."""

    validated = validate_live_progress_smoke_report(report)
    return json.dumps(validated.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


# --------------------------------------------------------------------------- #
# Smoke entry points — real caller API by default, injectable reader for tests
# --------------------------------------------------------------------------- #
def _resolve_reader(reader: Any) -> LiveProgressReader:
    """Default to the real lazy caller reader; accept an injected one for tests.

    With ``reader=None`` the smoke wires the existing
    :class:`DefaultLiveProgressReader`, which lazily imports the real
    ``agent_run_supervisor.hermes_caller.events`` caller API per call and fails
    closed to ``live_progress_unavailable`` when the library is absent. An injected
    reader (an in-test fake) lets the safety / fail-closed paths run without the
    real library.
    """

    return DefaultLiveProgressReader() if reader is None else reader


def smoke_live_progress_projection(
    artifact_dir: str,
    artifact_ref: str,
    *,
    reader: LiveProgressReader | None = None,
    task_id: str | None = None,
    after_seq: int | None = None,
    limit: int = 100,
) -> LiveProgressProjection:
    """Read one synthetic artifact dir through the caller API into a projection.

    ``artifact_dir`` (a real path) is passed to the reader only and never stored or
    scanned; ``artifact_ref`` is the safe public handle. Missing progress / an
    absent library yields a ``live_progress_unavailable`` projection; a corrupt
    ``progress.json`` / off-contract event yields a ``live_progress_corrupt``
    projection — never a raised exception, never a raw echo.
    """

    return build_live_progress_projection(
        _resolve_reader(reader),
        artifact_dir,
        artifact_ref,
        task_id=task_id,
        after_seq=after_seq,
        limit=limit,
    )


def smoke_live_workbench_view(
    registry: TaskRegistry,
    port: AgentRunSupervisorPort,
    ref: Any,
    artifact_dir: str,
    artifact_ref: str,
    *,
    reader: LiveProgressReader | None = None,
    after_seq: int | None = None,
    limit: int = 100,
    liveness: LivenessState | None = None,
) -> AgentRunSupervisorLiveWorkbenchView:
    """Compose the PR-LS1 combined workbench + live-progress view over the caller API.

    The workbench half is built from ``registry`` / ``port`` / ``ref``; the live
    half reads the synthetic artifact dir through the caller API for the workbench's
    own ``task_id``. Degraded live progress composes as unavailable / corrupt over a
    still-valid workbench, never faking success.
    """

    return build_agent_run_supervisor_live_workbench_view(
        registry,
        port,
        ref,
        _resolve_reader(reader),
        artifact_dir,
        artifact_ref,
        after_seq=after_seq,
        limit=limit,
        liveness=liveness,
    )


def smoke_live_progress_report(
    artifact_dir: str,
    artifact_ref: str,
    *,
    reader: LiveProgressReader | None = None,
    task_id: str | None = None,
    after_seq: int | None = None,
    limit: int = 100,
) -> LiveProgressSmokeReport:
    """Read one synthetic artifact dir through the caller API into a stable report.

    A convenience over :func:`smoke_live_progress_projection` +
    :func:`build_live_progress_smoke_report`: the single stable outcome surface for
    the ``available`` / ``unavailable`` (library absent / missing progress) /
    ``corrupt`` compatibility outcomes, with no raw import-error text or path.
    """

    return build_live_progress_smoke_report(
        smoke_live_progress_projection(
            artifact_dir,
            artifact_ref,
            reader=reader,
            task_id=task_id,
            after_seq=after_seq,
            limit=limit,
        )
    )


__all__ = [
    "RUNTIME_INVALID_LIVE_PROGRESS_SMOKE",
    "LIVE_PROGRESS_SMOKE_STABLE_CODES",
    "LIVE_PROGRESS_SMOKE_REPORT_TYPE",
    "SMOKE_OUTCOMES",
    "LiveProgressSmokeReport",
    "smoke_live_progress_projection",
    "smoke_live_workbench_view",
    "smoke_live_progress_report",
    "build_live_progress_smoke_report",
    "validate_live_progress_smoke_report",
    "serialize_live_progress_smoke_report",
]
