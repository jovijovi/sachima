"""PR-LS1 Runtime Spine — ARS live-progress + task workbench composite view.

The live workbench view is a deterministic, read-only composition of two existing
safe surfaces for one locally tracked ``AgentRunSupervisorPort`` session:

* the PR4 :class:`AgentRunSupervisorWorkbenchView` — the R1 Status Projection +
  PR3 persistent-lifecycle facts (refs / counts / states / booleans / stable
  codes), and
* the PR3 :class:`LiveProgressProjection` — a refs-only, fail-closed read-model of
  the agent-run-supervisor artifact's live progress (a coarse observed state, a
  bounded record set, a foreign resume cursor, and a stable ``error_code``).

It carries only the two already-sanitized child dicts plus top-level mirror
fields — task & session identity, ``progress_available`` / ``progress_error_code``
/ ``resume_cursor`` / ``has_more`` / ``stale`` — never raw prompt / context /
stdout / tool output / card JSON / the ARS summary text / platform ids / private
paths / secrets / signed URLs.

Building or serializing the view is pure and side-effect-free: it appends no
event, launches no work, starts no runtime / Temporal / process, and calls no
Gateway / IM / delivery surface. It reuses ``build_agent_run_supervisor_workbench_view``
and ``build_live_progress_projection`` and validates both before composing, so an
untracked / forged session ref fails closed with the stable PR3
``runtime_invalid_session`` code inside the workbench half. The live progress
projection is always requested for the workbench's own ``task_id`` — a foreign or
forged projection whose non-``None`` ``task_id`` disagrees fails closed. If the
projection is unavailable / corrupt it still carries the safe ``task_id`` and
``artifact_ref`` and composes as unavailable / corrupt (observation only), never
faking success and never blocking the workbench. The supervisor's own terminal
state and the ARS resume cursor stay observation-only: the ARS cursor is a foreign
read-model cursor that is surfaced but never fed into ``TaskEventLog``.

``artifact_dir`` (a real path) is passed only to the injected progress reader and
is never stored or serialized; ``artifact_ref`` is the safe public handle. Every
composed value passes the same fail-closed allowlist + no-leak scan the rest of
the spine uses, and a directly-constructed or forged combined / nested view fails
closed with the stable ``runtime_invalid_live_workbench_view`` code rather than
being trusted. Forbidden terms in this prose are no-leak denylist boundaries only,
never behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, NoReturn

from .agent_run_supervisor_port import AgentRunSupervisorPort
from .agent_run_supervisor_workbench import (
    AgentRunSupervisorWorkbenchView,
    build_agent_run_supervisor_workbench_view,
    validate_agent_run_supervisor_workbench_view,
)
from .events import SpineError, safe_task_id, scan_for_leak
from .execution_port import LivenessState
from .live_progress_projection import (
    LIVE_PROGRESS_STABLE_CODES,
    LiveProgressEventRecord,
    LiveProgressProjection,
    LiveProgressReader,
    build_live_progress_projection,
    validate_live_progress_projection,
)
from .registry import TaskRegistry

RUNTIME_INVALID_LIVE_WORKBENCH_VIEW = "runtime_invalid_live_workbench_view"
LIVE_WORKBENCH_STABLE_CODES = frozenset({RUNTIME_INVALID_LIVE_WORKBENCH_VIEW})
LIVE_WORKBENCH_VIEW_TYPE = "sachima.runtime_spine.agent_run_supervisor_live_workbench_view.v1"


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_LIVE_WORKBENCH_VIEW)


def _check_bool(value: Any) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


# --------------------------------------------------------------------------- #
# Nested-child revalidation — accept each child either as its already-frozen value
# object or as its canonical dict, revalidate through the child's public boundary,
# and store the frozen value object internally. This keeps the combined dataclass
# from carrying mutable nested dict/list state while still emitting canonical dicts
# at the public serialization boundary. Any child failure (a forged / leaky /
# off-contract child) is collapsed to this module's stable code so the composite
# boundary never leaks the child's material.
# --------------------------------------------------------------------------- #
def _revalidated_workbench(raw: Any) -> AgentRunSupervisorWorkbenchView:
    try:
        if type(raw) is AgentRunSupervisorWorkbenchView:
            view = raw
        elif type(raw) is dict:
            view = AgentRunSupervisorWorkbenchView(**raw)
        else:
            _invalid()
        return validate_agent_run_supervisor_workbench_view(view)
    except SpineError:
        _invalid()
    except (TypeError, ValueError):
        _invalid()


def _reconstruct_record(raw: Any) -> LiveProgressEventRecord:
    if type(raw) is LiveProgressEventRecord:
        return raw
    if type(raw) is not dict:
        _invalid()
    return LiveProgressEventRecord(**raw)


def _revalidated_live_progress(raw: Any) -> LiveProgressProjection:
    try:
        if type(raw) is LiveProgressProjection:
            projection = raw
        elif type(raw) is dict and "records" in raw:
            raw_records = raw["records"]
            if type(raw_records) is not list:
                _invalid()
            records = tuple(_reconstruct_record(rec) for rec in raw_records)
            projection = LiveProgressProjection(
                records=records, **{key: raw[key] for key in raw if key != "records"}
            )
        else:
            _invalid()
        return validate_live_progress_projection(projection)
    except SpineError:
        _invalid()
    except (TypeError, ValueError):
        _invalid()


def _raw_live_workbench_dict(
    view: Any,
    workbench: AgentRunSupervisorWorkbenchView,
    live_progress: LiveProgressProjection,
) -> dict[str, Any]:
    return {
        "type": view.type,
        "task_id": view.task_id,
        "session_id": view.session_id,
        "workbench": workbench.as_dict(),
        "live_progress": live_progress.as_dict(),
        "progress_available": view.progress_available,
        "progress_error_code": view.progress_error_code,
        "resume_cursor": view.resume_cursor,
        "has_more": view.has_more,
        "stale": view.stale,
    }


def _check_live_workbench_fields(view: Any, *, normalize: bool = False) -> None:
    """Exact fail-closed validation of a combined view's fields.

    Fails closed on: a forged ``type``; a nested workbench / live-progress dict
    that does not revalidate through its own child validator; an unsafe top-level
    ``task_id`` / ``session_id`` or one that disagrees with the workbench half; a
    live projection ``task_id`` that disagrees with the workbench ``task_id``; a
    ``progress_available`` / ``progress_error_code`` / ``resume_cursor`` /
    ``has_more`` / ``stale`` field that does not mirror the live projection; or any
    forbidden marker anywhere in the view. It never echoes the rejected material.
    """

    try:
        view_type = view.type
        task_id = view.task_id
        session_id = view.session_id
        workbench = view.workbench
        live_progress = view.live_progress
        progress_available = view.progress_available
        progress_error_code = view.progress_error_code
        resume_cursor = view.resume_cursor
        has_more = view.has_more
        stale = view.stale
    except AttributeError:
        _invalid()

    if type(view_type) is not str or view_type != LIVE_WORKBENCH_VIEW_TYPE:
        _invalid()

    workbench_view = _revalidated_workbench(workbench)
    live_progress_view = _revalidated_live_progress(live_progress)
    wb_dict = workbench_view.as_dict()
    lp_dict = live_progress_view.as_dict()

    # Identity: the composite mirrors the workbench task/session, and the two
    # composed sources must agree on task_id — a disagreement is a forged input.
    safe_task_id(task_id, code=RUNTIME_INVALID_LIVE_WORKBENCH_VIEW)
    if task_id != wb_dict["task_id"]:
        _invalid()
    if type(session_id) is not str or session_id != wb_dict["session_id"]:
        _invalid()
    if lp_dict["task_id"] != wb_dict["task_id"]:
        _invalid()

    # Availability + error code mirror the live projection exactly.
    available = _check_bool(progress_available)
    if available is not lp_dict["available"]:
        _invalid()
    if progress_error_code is not None and type(progress_error_code) is not str:
        _invalid()
    if progress_error_code != lp_dict["error_code"]:
        _invalid()
    if available:
        if progress_error_code is not None:
            _invalid()
    elif progress_error_code is None or progress_error_code not in LIVE_PROGRESS_STABLE_CODES:
        _invalid()

    # Resume cursor / has_more / stale mirror the live projection.
    if resume_cursor is not None and type(resume_cursor) is not int:
        _invalid()
    if resume_cursor != lp_dict["resume_cursor"]:
        _invalid()
    if _check_bool(has_more) is not lp_dict["has_more"]:
        _invalid()
    if _check_bool(stale) is not lp_dict["stale"]:
        _invalid()

    if normalize:
        object.__setattr__(view, "workbench", workbench_view)
        object.__setattr__(view, "live_progress", live_progress_view)

    if scan_for_leak(_raw_live_workbench_dict(view, workbench_view, live_progress_view)) is not None:
        _invalid()


@dataclass(frozen=True)
class AgentRunSupervisorLiveWorkbenchView:
    """Frozen, refs-only combined workbench + live-progress view of one session.

    The ``workbench`` / ``live_progress`` inputs may be the two children's canonical
    dicts or already-frozen value objects; construction re-runs each child's own
    validator and normalizes them to frozen child objects so a caller cannot mutate
    a built view into echoing raw material.
    ``__post_init__`` re-runs the full fail-closed allowlist so a directly
    constructed or forged view fails closed instead of being trusted, and
    ``as_dict`` / ``serialize_...`` re-validate before emitting.
    """

    type: str
    task_id: str
    session_id: str
    workbench: Any
    live_progress: Any
    progress_available: bool
    progress_error_code: str | None
    resume_cursor: int | None
    has_more: bool
    stale: bool

    def __post_init__(self) -> None:
        _check_live_workbench_fields(self, normalize=True)

    def as_dict(self) -> dict[str, Any]:
        validated = validate_agent_run_supervisor_live_workbench_view(self)
        return {
            "type": validated.type,
            "task_id": validated.task_id,
            "session_id": validated.session_id,
            "workbench": validated.workbench.as_dict(),
            "live_progress": validated.live_progress.as_dict(),
            "progress_available": validated.progress_available,
            "progress_error_code": validated.progress_error_code,
            "resume_cursor": validated.resume_cursor,
            "has_more": validated.has_more,
            "stale": validated.stale,
        }


def validate_agent_run_supervisor_live_workbench_view(
    view: Any,
) -> AgentRunSupervisorLiveWorkbenchView:
    """Re-validate a combined view at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type or any unsafe / inconsistent field fails
    closed with the stable ``runtime_invalid_live_workbench_view`` code, never
    echoing material.
    """

    if type(view) is not AgentRunSupervisorLiveWorkbenchView:
        _invalid()
    _check_live_workbench_fields(view)
    return view


def _compose(
    workbench: AgentRunSupervisorWorkbenchView, live_progress: LiveProgressProjection
) -> AgentRunSupervisorLiveWorkbenchView:
    """Compose two already-validated children into one combined view."""

    wb_dict = workbench.as_dict()
    lp_dict = live_progress.as_dict()
    # The live projection is always requested for the workbench's task_id, so the
    # two must agree — a disagreement is a forged/mismatched input, not a view.
    if lp_dict["task_id"] != wb_dict["task_id"]:
        _invalid()
    return AgentRunSupervisorLiveWorkbenchView(
        type=LIVE_WORKBENCH_VIEW_TYPE,
        task_id=wb_dict["task_id"],
        session_id=wb_dict["session_id"],
        workbench=workbench,
        live_progress=live_progress,
        progress_available=lp_dict["available"],
        progress_error_code=lp_dict["error_code"],
        resume_cursor=lp_dict["resume_cursor"],
        has_more=lp_dict["has_more"],
        stale=lp_dict["stale"],
    )


def build_agent_run_supervisor_live_workbench_view(
    registry: TaskRegistry,
    port: AgentRunSupervisorPort,
    ref: Any,
    progress_reader: LiveProgressReader,
    artifact_dir: str,
    artifact_ref: str,
    *,
    after_seq: int | None = None,
    limit: int = 100,
    liveness: LivenessState | None = None,
) -> AgentRunSupervisorLiveWorkbenchView:
    """Build a deterministic, read-only combined workbench + live-progress view.

    The workbench half is built (and validated) first from ``registry`` / ``port``
    / ``ref``; an untracked/forged ref fails closed there with the stable PR3
    ``runtime_invalid_session`` code and mutates nothing. The live progress half is
    then requested for the workbench's own ``task_id`` via the injected
    ``progress_reader`` over ``artifact_dir`` (passed to the reader only, never
    stored) with ``artifact_ref`` as the safe handle; a missing / unavailable /
    corrupt projection composes as unavailable / corrupt rather than raising. Both
    children are validated before composition.
    """

    workbench = build_agent_run_supervisor_workbench_view(registry, port, ref, liveness=liveness)
    live_progress = build_live_progress_projection(
        progress_reader,
        artifact_dir,
        artifact_ref,
        task_id=workbench.task_id,
        after_seq=after_seq,
        limit=limit,
    )
    return validate_agent_run_supervisor_live_workbench_view(_compose(workbench, live_progress))


def serialize_agent_run_supervisor_live_workbench_view(
    view: AgentRunSupervisorLiveWorkbenchView,
) -> bytes:
    """Byte-stable canonical JSON serialization after full re-validation."""

    validated = validate_agent_run_supervisor_live_workbench_view(view)
    return json.dumps(validated.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


__all__ = [
    "RUNTIME_INVALID_LIVE_WORKBENCH_VIEW",
    "LIVE_WORKBENCH_STABLE_CODES",
    "LIVE_WORKBENCH_VIEW_TYPE",
    "AgentRunSupervisorLiveWorkbenchView",
    "build_agent_run_supervisor_live_workbench_view",
    "validate_agent_run_supervisor_live_workbench_view",
    "serialize_agent_run_supervisor_live_workbench_view",
]
