"""PR4 Runtime Spine — platform-neutral agent-run-supervisor workbench view.

The workbench view is a deterministic, read-only composition of the R1 Status
Projection surface (:class:`TaskViewModel`) with the PR3 persistent-lifecycle facts
(:class:`LifecycleSnapshot`) for a locally tracked ``AgentRunSupervisorPort``
session. It is the safe surface a future Hermes/IM task workbench can render: it
carries only refs / counts / states / booleans / stable codes — task & session
identity, status / terminal / liveness, the permission-wait + operator-decision
flags, the two mode flags, safe refs / surfaces, the resume cursor / ``last_seq`` /
``event_count`` / ``attach_count``, an optional ``reapable`` health hint, and the
stable ``error_code`` — never raw prompt / context / stdout / tool output / card
JSON / platform ids / private paths / secrets / signed URLs.

Building or serializing the view is pure and side-effect-free: it appends no event,
launches no work, starts no runtime / Temporal / process, and calls no Gateway / IM
/ delivery surface. It reuses ``build_task_view_model`` (the registry-derived Status
Projection) and ``AgentRunSupervisorPort.lifecycle_snapshot`` (persisted Sachima
state only — no backend call by PR3 design), so it is a stable read even while the
injected backend is unreachable. An untracked / forged ref fails closed with the
stable PR3 ``runtime_invalid_session`` code inside ``lifecycle_snapshot`` rather than
fabricating state, and every composed value passes the same fail-closed allowlist +
no-leak scan the rest of the spine uses.

Optional liveness: a caller that already holds a :class:`LivenessState` may pass it
to surface ``reapable``. An ``orphaned`` backend health signal is shown only as a
``reapable`` hint over the still-non-terminal projected lifecycle and is never
auto-written as a terminal event into the canonical log — the PR3 policy that an
orphan is a reaper's decision, not an auto-mark, is preserved by construction (the
builder mutates nothing and makes no backend call of its own).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

from .agent_run_supervisor_port import (
    AgentRunSupervisorPort,
    LifecycleSnapshot,
    validate_lifecycle_snapshot,
)
from .events import STABLE_CODES, SpineError, _safe_id, safe_task_id, scan_for_leak
from .execution_port import (
    LIVE_SESSION_STATES,
    LivenessState,
    validate_liveness_state,
)
from .registry import TaskRegistry
from .view_model import (
    TaskViewModel,
    build_task_view_model,
    validate_task_view_model,
)

RUNTIME_INVALID_WORKBENCH_VIEW = "runtime_invalid_workbench_view"
WORKBENCH_STABLE_CODES = frozenset({RUNTIME_INVALID_WORKBENCH_VIEW})
WORKBENCH_VIEW_TYPE = "sachima.runtime_spine.agent_run_supervisor_workbench_view.v1"

#: The lifecycle states a workbench view can carry — exactly the projection
#: statuses the adapter ever mirrors into the canonical log for a tracked session.
_LIFECYCLE_STATES = frozenset(
    {"running", "permission_wait", "completed", "failed", "cancelled"}
)
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
_PERMISSION_STATES = frozenset({"none", "waiting"})
_STATUS_SURFACES = ("status",)
_PERMISSION_SURFACES = ("status", "permission")
_REQUIRED_FLAG_KEYS = {"needs_agent", "needs_durable"}


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_WORKBENCH_VIEW)


def _safe_view_ref(value: Any) -> str:
    return _safe_id(value, code=RUNTIME_INVALID_WORKBENCH_VIEW)


def _check_count(value: Any) -> int:
    # bool is an int subclass — exclude it so a flag can't pose as a count.
    if type(value) is not int or value < 0:
        _invalid()
    return value


def _check_bool(value: Any) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _normalize_flags(flags: Any, *, allow_input: bool) -> tuple[tuple[str, bool], ...]:
    if isinstance(flags, Mapping):
        if not allow_input:
            _invalid()
        values: dict[str, bool] = {}
        for key, value in flags.items():
            if type(key) is not str or key in values:
                _invalid()
            values[key] = value
        if set(values) != _REQUIRED_FLAG_KEYS:
            _invalid()
    elif type(flags) is tuple:
        values = {}
        for pair in flags:
            if type(pair) is not tuple or len(pair) != 2:
                _invalid()
            key, value = pair
            if type(key) is not str or key in values:
                _invalid()
            values[key] = value
        if set(values) != _REQUIRED_FLAG_KEYS:
            _invalid()
    else:
        _invalid()
    for key, value in values.items():
        if key not in _REQUIRED_FLAG_KEYS or type(value) is not bool:
            _invalid()
    return (("needs_agent", values["needs_agent"]), ("needs_durable", values["needs_durable"]))


def _flags_dict(flags: tuple[tuple[str, bool], ...]) -> dict[str, bool]:
    return {key: value for key, value in flags}


def _normalize_refs(refs: Any, *, allow_input: bool) -> tuple[str, ...]:
    if type(refs) is list:
        if not allow_input:
            _invalid()
        items = refs
    elif type(refs) is tuple:
        items = list(refs)
    else:
        _invalid()
    safe_refs = tuple(_safe_view_ref(ref) for ref in items)
    if list(safe_refs) != sorted(set(safe_refs)):
        _invalid()
    return safe_refs


def _normalize_surfaces(surfaces: Any, *, permission_state: str, allow_input: bool) -> tuple[str, ...]:
    if type(surfaces) is list:
        if not allow_input:
            _invalid()
        items = tuple(surfaces)
    elif type(surfaces) is tuple:
        items = surfaces
    else:
        _invalid()
    for item in items:
        if type(item) is not str:
            _invalid()
    expected = _PERMISSION_SURFACES if permission_state == "waiting" else _STATUS_SURFACES
    if items != expected:
        _invalid()
    return tuple(items)


def _raw_view_dict(view: Any) -> dict[str, Any]:
    return {
        "type": view.type,
        "task_id": view.task_id,
        "session_id": view.session_id,
        "status": view.status,
        "terminal": view.terminal,
        "alive": view.alive,
        "resumable": view.resumable,
        "reapable": view.reapable,
        "permission_state": view.permission_state,
        "requires_operator_decision": view.requires_operator_decision,
        "flags": view.flags,
        "refs": view.refs,
        "surfaces": view.surfaces,
        "resume_cursor": view.resume_cursor,
        "last_seq": view.last_seq,
        "event_count": view.event_count,
        "attach_count": view.attach_count,
        "error_code": view.error_code,
    }


def _check_workbench_view_fields(view: Any, *, normalize: bool = False) -> None:
    """Exact fail-closed validation of a workbench view's fields.

    Fails closed on: a forged ``type``; an unsafe ``task_id`` / ``session_id``; a
    non-lifecycle ``status``; a non-``bool`` flag; a flag inconsistent with
    ``status`` (``terminal`` / ``alive`` / ``resumable``, or a ``reapable`` hint set
    over a non-live / terminal lifecycle); an inconsistent permission surface /
    operator-decision flag; a bad ``error_code``; a negative / non-``int`` counter or
    a broken resume invariant (``last_seq == event_count == resume_cursor``,
    ``1 <= attach_count <= event_count``); a malformed / unsorted ``flags`` /
    ``refs`` / ``surfaces`` set; or any forbidden marker anywhere in the view. It
    never echoes the rejected material.
    """

    try:
        view_type = view.type
        task_id = view.task_id
        session_id = view.session_id
        status = view.status
        terminal = view.terminal
        alive = view.alive
        resumable = view.resumable
        reapable = view.reapable
        permission_state = view.permission_state
        requires_operator_decision = view.requires_operator_decision
        flags = view.flags
        refs = view.refs
        surfaces = view.surfaces
        resume_cursor = view.resume_cursor
        last_seq = view.last_seq
        event_count = view.event_count
        attach_count = view.attach_count
        error_code = view.error_code
    except AttributeError:
        _invalid()

    if type(view_type) is not str or view_type != WORKBENCH_VIEW_TYPE:
        _invalid()
    safe_task_id(task_id, code=RUNTIME_INVALID_WORKBENCH_VIEW)
    if type(session_id) is not str or not session_id.startswith("sess_"):
        _invalid()
    _safe_id(session_id, code=RUNTIME_INVALID_WORKBENCH_VIEW)
    if type(status) is not str or status not in _LIFECYCLE_STATES:
        _invalid()

    term = _check_bool(terminal)
    is_alive = _check_bool(alive)
    is_resumable = _check_bool(resumable)
    is_reapable = _check_bool(reapable)
    if term is not (status in _TERMINAL_STATUSES):
        _invalid()
    if is_alive is not (status in LIVE_SESSION_STATES):
        _invalid()
    if is_resumable is not is_alive:
        _invalid()
    # An orphan/reapable health hint is only coherent over a live, non-terminal
    # projected lifecycle — an orphan is a reaper's decision, not a terminal mark.
    if is_reapable and (is_alive is not True or term is not False):
        _invalid()

    if type(permission_state) is not str or permission_state not in _PERMISSION_STATES:
        _invalid()
    needs_decision = _check_bool(requires_operator_decision)
    if (permission_state == "waiting") is not (status == "permission_wait"):
        _invalid()
    if permission_state == "waiting":
        if needs_decision is not True:
            _invalid()
    elif needs_decision is not False:
        _invalid()

    if error_code is not None and (type(error_code) is not str or error_code not in STABLE_CODES):
        _invalid()

    cursor = _check_count(resume_cursor)
    last = _check_count(last_seq)
    count = _check_count(event_count)
    attach = _check_count(attach_count)
    if last != count or cursor != last:
        _invalid()
    # A tracked supervised session always carries exactly one ``agent_attached``
    # event, so a workbench view has 1 <= attach_count <= event_count.
    if attach < 1 or attach > count:
        _invalid()

    safe_flags = _normalize_flags(flags, allow_input=normalize)
    safe_refs = _normalize_refs(refs, allow_input=normalize)
    safe_surfaces = _normalize_surfaces(surfaces, permission_state=permission_state, allow_input=normalize)

    if normalize:
        object.__setattr__(view, "flags", safe_flags)
        object.__setattr__(view, "refs", safe_refs)
        object.__setattr__(view, "surfaces", safe_surfaces)

    if scan_for_leak(_raw_view_dict(view)) is not None:
        _invalid()


@dataclass(frozen=True)
class AgentRunSupervisorWorkbenchView:
    """Frozen, refs-only workbench view of one locally tracked supervised task.

    Mapping/list inputs (``flags`` / ``refs`` / ``surfaces``) are normalized to
    immutable tuple shapes during construction so a caller cannot mutate a built
    view into echoing raw material. ``__post_init__`` re-runs the full fail-closed
    allowlist so a directly-constructed or forged view fails closed instead of being
    trusted, and ``as_dict`` / ``serialize_...`` re-validate before emitting.
    """

    type: str
    task_id: str
    session_id: str
    status: str
    terminal: bool
    alive: bool
    resumable: bool
    reapable: bool
    permission_state: str
    requires_operator_decision: bool
    flags: Any
    refs: Any
    surfaces: Any
    resume_cursor: int
    last_seq: int
    event_count: int
    attach_count: int
    error_code: str | None

    def __post_init__(self) -> None:
        _check_workbench_view_fields(self, normalize=True)

    def as_dict(self) -> dict[str, Any]:
        validate_agent_run_supervisor_workbench_view(self)
        return {
            "type": self.type,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "status": self.status,
            "terminal": self.terminal,
            "alive": self.alive,
            "resumable": self.resumable,
            "reapable": self.reapable,
            "permission_state": self.permission_state,
            "requires_operator_decision": self.requires_operator_decision,
            "flags": _flags_dict(self.flags),
            "refs": list(self.refs),
            "surfaces": list(self.surfaces),
            "resume_cursor": self.resume_cursor,
            "last_seq": self.last_seq,
            "event_count": self.event_count,
            "attach_count": self.attach_count,
            "error_code": self.error_code,
        }


def validate_agent_run_supervisor_workbench_view(
    view: Any,
) -> AgentRunSupervisorWorkbenchView:
    """Re-validate a workbench view at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type or any unsafe / inconsistent field fails
    closed with the stable ``runtime_invalid_workbench_view`` code, never echoing
    material.
    """

    if type(view) is not AgentRunSupervisorWorkbenchView:
        _invalid()
    _check_workbench_view_fields(view)
    return view


def _resolve_reapable(snapshot: LifecycleSnapshot, liveness: Any) -> bool:
    """Return the reapable health hint from an optional, matching liveness state."""

    if liveness is None:
        return False
    live = validate_liveness_state(liveness)
    if live.task_id != snapshot.task_id or live.session_id != snapshot.session_id:
        _invalid()
    return live.reapable


def _compose(
    view_model: TaskViewModel, snapshot: LifecycleSnapshot, reapable: bool
) -> AgentRunSupervisorWorkbenchView:
    """Compose an agreed Status Projection + lifecycle snapshot into one view."""

    # The two composed sources must agree — a mismatch (e.g. a registry that does
    # not own this session's log) is a forged/mismatched input, not a renderable
    # view.
    if (
        view_model.task_id != snapshot.task_id
        or view_model.status != snapshot.state
        or view_model.terminal != snapshot.terminal
        or view_model.last_seq != snapshot.last_seq
        or view_model.event_count != snapshot.event_count
    ):
        _invalid()
    permission_state = view_model.permission_state
    if (permission_state == "waiting") is not (snapshot.state == "permission_wait"):
        _invalid()

    return AgentRunSupervisorWorkbenchView(
        type=WORKBENCH_VIEW_TYPE,
        task_id=snapshot.task_id,
        session_id=snapshot.session_id,
        status=snapshot.state,
        terminal=snapshot.terminal,
        alive=snapshot.alive,
        resumable=snapshot.resumable,
        reapable=reapable,
        permission_state=permission_state,
        requires_operator_decision=view_model.requires_operator_decision,
        flags=_flags_dict(view_model.flags),
        refs=list(view_model.refs),
        surfaces=list(view_model.surfaces),
        resume_cursor=snapshot.last_seq,
        last_seq=snapshot.last_seq,
        event_count=snapshot.event_count,
        attach_count=snapshot.attach_count,
        error_code=view_model.error_code,
    )


def build_agent_run_supervisor_workbench_view(
    registry: TaskRegistry,
    port: AgentRunSupervisorPort,
    ref: Any,
    *,
    liveness: LivenessState | None = None,
) -> AgentRunSupervisorWorkbenchView:
    """Build a deterministic, read-only workbench view for one tracked session.

    The ``ref`` is the trust anchor: ``port.lifecycle_snapshot(ref)`` fails closed on
    an untracked/forged ref with the stable PR3 ``runtime_invalid_session`` code and
    makes no backend call and no mutation. The Status Projection surface is built
    from ``registry`` for the same ``task_id`` and the two are composed only if they
    agree. An optional, already-obtained ``liveness`` surfaces ``reapable`` without
    any mutation or backend call of this builder's own.
    """

    if type(registry) is not TaskRegistry:
        _invalid()
    if type(port) is not AgentRunSupervisorPort:
        _invalid()
    snapshot = validate_lifecycle_snapshot(port.lifecycle_snapshot(ref))
    view_model = validate_task_view_model(build_task_view_model(registry, snapshot.task_id))
    reapable = _resolve_reapable(snapshot, liveness)
    return validate_agent_run_supervisor_workbench_view(_compose(view_model, snapshot, reapable))


def serialize_agent_run_supervisor_workbench_view(
    view: AgentRunSupervisorWorkbenchView,
) -> bytes:
    """Byte-stable canonical JSON serialization after full re-validation."""

    validated = validate_agent_run_supervisor_workbench_view(view)
    return json.dumps(validated.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


__all__ = [
    "RUNTIME_INVALID_WORKBENCH_VIEW",
    "WORKBENCH_STABLE_CODES",
    "WORKBENCH_VIEW_TYPE",
    "AgentRunSupervisorWorkbenchView",
    "build_agent_run_supervisor_workbench_view",
    "validate_agent_run_supervisor_workbench_view",
    "serialize_agent_run_supervisor_workbench_view",
]
