"""R4 Runtime Spine — platform-neutral task view model.

The task view model is a deterministic user-visible surface derived from the R1
Event Log / Status Projection. It is refs-only and platform-neutral: stable task
state, counters, mode flags, refs, permission-wait state, and stable error codes.
It appends no events, launches no work, and wires no external runtime surface.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

from .events import (
    STABLE_CODES,
    STATUS_VALUES,
    TERMINAL_STATUSES,
    SpineError,
    _safe_id,
    safe_task_id,
    scan_for_leak,
)
from .registry import TaskRegistry

RUNTIME_INVALID_VIEW_MODEL = "runtime_invalid_view_model"
VIEW_MODEL_STABLE_CODES = frozenset({RUNTIME_INVALID_VIEW_MODEL})
VIEW_MODEL_TYPE = "sachima.runtime_spine.task_view_model.v1"

_PERMISSION_STATES = frozenset({"none", "waiting"})
_STATUS_SURFACES = ("status",)
_PERMISSION_SURFACES = ("status", "permission")
_REQUIRED_FLAG_KEYS = {"needs_agent", "needs_durable"}


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_VIEW_MODEL)


def _safe_view_ref(value: Any) -> str:
    return _safe_id(value, code=RUNTIME_INVALID_VIEW_MODEL)


def _check_count(value: Any) -> int:
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
        values: dict[str, bool] = {}
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
        "status": view.status,
        "terminal": view.terminal,
        "last_seq": view.last_seq,
        "event_count": view.event_count,
        "flags": view.flags,
        "refs": view.refs,
        "surfaces": view.surfaces,
        "permission_state": view.permission_state,
        "requires_operator_decision": view.requires_operator_decision,
        "error_code": view.error_code,
    }


def _check_view_model_fields(view: Any, *, normalize: bool = False) -> None:
    try:
        view_type = view.type
        task_id = view.task_id
        status = view.status
        terminal = view.terminal
        last_seq = view.last_seq
        event_count = view.event_count
        flags = view.flags
        refs = view.refs
        surfaces = view.surfaces
        permission_state = view.permission_state
        requires_operator_decision = view.requires_operator_decision
        error_code = view.error_code
    except AttributeError:
        _invalid()

    if type(view_type) is not str or view_type != VIEW_MODEL_TYPE:
        _invalid()
    safe_task_id(task_id, code=RUNTIME_INVALID_VIEW_MODEL)
    if status is not None and (type(status) is not str or status not in STATUS_VALUES):
        _invalid()
    term = _check_bool(terminal)
    if term is not (status in TERMINAL_STATUSES):
        _invalid()
    last = _check_count(last_seq)
    count = _check_count(event_count)
    if last != count:
        _invalid()
    if type(permission_state) is not str or permission_state not in _PERMISSION_STATES:
        _invalid()
    needs_decision = _check_bool(requires_operator_decision)
    if permission_state == "waiting":
        if status != "permission_wait" or needs_decision is not True:
            _invalid()
    else:
        if needs_decision is not False:
            _invalid()

    safe_flags = _normalize_flags(flags, allow_input=normalize)
    safe_refs = _normalize_refs(refs, allow_input=normalize)
    safe_surfaces = _normalize_surfaces(surfaces, permission_state=permission_state, allow_input=normalize)
    if error_code is not None and (type(error_code) is not str or error_code not in STABLE_CODES):
        _invalid()

    if normalize:
        object.__setattr__(view, "flags", safe_flags)
        object.__setattr__(view, "refs", safe_refs)
        object.__setattr__(view, "surfaces", safe_surfaces)

    if scan_for_leak(_raw_view_dict(view)) is not None:
        _invalid()


@dataclass(frozen=True)
class TaskViewModel:
    """Frozen platform-neutral refs-only view of one task.

    Mapping/list inputs are normalized to immutable tuple shapes during
    construction so a caller cannot mutate a built view into echoing raw material.
    """

    type: str
    task_id: str
    status: str | None
    terminal: bool
    last_seq: int
    event_count: int
    flags: Any
    refs: Any
    surfaces: Any
    permission_state: str
    requires_operator_decision: bool
    error_code: str | None

    def __post_init__(self) -> None:
        _check_view_model_fields(self, normalize=True)

    def as_dict(self) -> dict[str, Any]:
        validate_task_view_model(self)
        return {
            "type": self.type,
            "task_id": self.task_id,
            "status": self.status,
            "terminal": self.terminal,
            "last_seq": self.last_seq,
            "event_count": self.event_count,
            "flags": _flags_dict(self.flags),
            "refs": list(self.refs),
            "surfaces": list(self.surfaces),
            "permission_state": self.permission_state,
            "requires_operator_decision": self.requires_operator_decision,
            "error_code": self.error_code,
        }


def validate_task_view_model(view: Any) -> TaskViewModel:
    if type(view) is not TaskViewModel:
        _invalid()
    _check_view_model_fields(view)
    return view


def build_task_view_model(registry: TaskRegistry, task_id: str) -> TaskViewModel:
    """Build a deterministic view from a registry-derived Status Projection."""

    if type(registry) is not TaskRegistry:
        _invalid()
    safe_task = safe_task_id(task_id, code=RUNTIME_INVALID_VIEW_MODEL)
    snapshot = registry.snapshot(safe_task)
    if snapshot is None:
        _invalid()

    status = snapshot["status"]
    permission_state = "waiting" if status == "permission_wait" else "none"
    requires_operator_decision = permission_state == "waiting"
    surfaces = _PERMISSION_SURFACES if permission_state == "waiting" else _STATUS_SURFACES
    view = TaskViewModel(
        type=VIEW_MODEL_TYPE,
        task_id=safe_task,
        status=status,
        terminal=snapshot["terminal"],
        last_seq=snapshot["last_seq"],
        event_count=snapshot["event_count"],
        flags=dict(snapshot["flags"]),
        refs=list(snapshot["refs"]),
        surfaces=list(surfaces),
        permission_state=permission_state,
        requires_operator_decision=requires_operator_decision,
        error_code=snapshot["error_code"],
    )
    validate_task_view_model(view)
    return view


def serialize_task_view_model(view: TaskViewModel) -> bytes:
    """Byte-stable canonical JSON serialization after full validation."""

    validated = validate_task_view_model(view)
    return json.dumps(validated.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
