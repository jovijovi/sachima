"""R1 Runtime Spine — typed, fail-closed LaunchSpec.

A ``LaunchSpec`` is the frozen, sanitized object the Thin Dispatcher would emit
(design §4/§5): task id, agent kind, the two mode flags, the capability
requirements, read-only role keys, and refs. It is validated **against the static
Capability Registry** and fails closed on unknown mode flags, unknown/unsupported
capabilities, platform-derived values, and write-capable role markers. Failures
carry a stable code only — never raw material.

Pure local/offline Python: constructing/validating a LaunchSpec launches nothing.
There is no acpx/npx/agent launch, no subprocess, no supervisor/execution-port
wiring here — that is R2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .capabilities import CAPABILITY_FIELDS, Capability, get_capability
from .events import (
    RUNTIME_INVALID_LAUNCH_SPEC,
    SpineError,
    _safe_id,
    safe_role_key,
    safe_task_id,
)

KNOWN_MODE_FLAGS = ("needs_agent", "needs_durable")

#: A truthy mode flag requires the agent kind to actually support the lane:
#: a live agent needs liveness; a durable attach needs attach-resume.
_FLAG_REQUIRED_CAPABILITY = {"needs_agent": "liveness", "needs_durable": "attach_resume"}


@dataclass(frozen=True)
class LaunchSpec:
    """Frozen, sanitized launch specification validated against the registry.

    ``LaunchSpec`` is exported public surface, so construction alone must never be
    grounds for trust: ``__post_init__`` re-runs the full registry validation so a
    direct ``LaunchSpec(...)`` with non-bool mode flags, unknown/unsupported
    capabilities, write-ish roles, or platform-derived / raw material fails closed
    instead of yielding a "typed" but unvalidated spec. Boundary consumers
    additionally call :func:`validate_launch_spec` to defend against
    ``object.__new__`` forgery and hostile subclasses that skip ``__post_init__``.
    """

    task_id: str
    agent_kind: str
    needs_agent: bool
    needs_durable: bool
    required_capabilities: tuple[str, ...]
    roles: tuple[str, ...]
    refs: tuple[str, ...]

    def __post_init__(self) -> None:
        # Field-level validation only (NOT the concrete-type identity gate): a
        # clean subclass may still construct, but :func:`validate_launch_spec`
        # rejects it at the trust boundary.
        _check_launch_spec_fields(self)


def _normalize_mode_flags(mode_flags: Mapping[str, bool] | None) -> tuple[bool, bool]:
    if mode_flags is None:
        return (False, False)
    if not isinstance(mode_flags, Mapping):
        raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
    for key, value in mode_flags.items():
        if key not in KNOWN_MODE_FLAGS or type(value) is not bool:
            raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
    return (bool(mode_flags.get("needs_agent", False)), bool(mode_flags.get("needs_durable", False)))


def _check_capabilities(
    capability: Capability, *, required: tuple[str, ...], needs_agent: bool, needs_durable: bool
) -> None:
    for name in required:
        if name not in CAPABILITY_FIELDS:
            raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
        if getattr(capability, name) is not True:
            raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
    for flag_name, flag_value in (("needs_agent", needs_agent), ("needs_durable", needs_durable)):
        if flag_value and getattr(capability, _FLAG_REQUIRED_CAPABILITY[flag_name]) is not True:
            raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)


def build_launch_spec(
    *,
    task_id: str,
    agent_kind: str,
    mode_flags: Mapping[str, bool] | None = None,
    required_capabilities: tuple[str, ...] = (),
    roles: tuple[str, ...] = (),
    refs: tuple[str, ...] = (),
) -> LaunchSpec:
    """Build a sanitized ``LaunchSpec`` validated against the registry, or fail closed."""

    safe_task = safe_task_id(task_id)
    capability = get_capability(agent_kind)  # validates known/safe agent_kind
    needs_agent, needs_durable = _normalize_mode_flags(mode_flags)

    if not isinstance(required_capabilities, (list, tuple)):
        raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
    safe_required = tuple(_safe_id(name, code=RUNTIME_INVALID_LAUNCH_SPEC) for name in required_capabilities)
    _check_capabilities(
        capability, required=safe_required, needs_agent=needs_agent, needs_durable=needs_durable
    )

    if not isinstance(roles, (list, tuple)) or not isinstance(refs, (list, tuple)):
        raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
    safe_roles = tuple(safe_role_key(role, code=RUNTIME_INVALID_LAUNCH_SPEC) for role in roles)
    safe_refs = tuple(_safe_id(ref, code=RUNTIME_INVALID_LAUNCH_SPEC) for ref in refs)

    spec = LaunchSpec(
        task_id=safe_task,
        agent_kind=agent_kind,
        needs_agent=needs_agent,
        needs_durable=needs_durable,
        required_capabilities=safe_required,
        roles=safe_roles,
        refs=safe_refs,
    )
    validate_launch_spec(spec)
    return spec


def _check_launch_spec_fields(spec: LaunchSpec) -> None:
    """Exact fail-closed field validation shared by ``LaunchSpec.__post_init__``
    and :func:`validate_launch_spec`.

    Validates every field against the static registry — safe ``task_id``, a known
    ``agent_kind``, bool-only mode flags, known+supported capabilities, read-only
    (non-write-ish) roles, and safe refs — but does **not** check the concrete
    type. That identity gate lives in :func:`validate_launch_spec` so it can run
    from inside construction (where ``self`` may legitimately be a subclass)
    without breaking the ``TaskEvent``-style ``__post_init__`` pattern.
    """

    safe_task_id(spec.task_id)
    capability = get_capability(spec.agent_kind)
    if type(spec.needs_agent) is not bool or type(spec.needs_durable) is not bool:
        raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
    if not isinstance(spec.required_capabilities, tuple):
        raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
    for name in spec.required_capabilities:
        _safe_id(name, code=RUNTIME_INVALID_LAUNCH_SPEC)
    _check_capabilities(
        capability,
        required=spec.required_capabilities,
        needs_agent=spec.needs_agent,
        needs_durable=spec.needs_durable,
    )
    if not isinstance(spec.roles, tuple) or not isinstance(spec.refs, tuple):
        raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
    for role in spec.roles:
        safe_role_key(role, code=RUNTIME_INVALID_LAUNCH_SPEC)
    for ref in spec.refs:
        _safe_id(ref, code=RUNTIME_INVALID_LAUNCH_SPEC)


def validate_launch_spec(spec: LaunchSpec) -> None:
    """Exact re-validation — rejects hostile subclasses and any unsafe material.

    ``__post_init__`` validates fields on normal construction, but an exported
    frozen dataclass can still be forged via ``object.__new__`` +
    ``object.__setattr__`` or a subclass that overrides ``__post_init__``. Trust
    boundaries call this so the launch surface stays fail-closed against a hostile
    or directly constructed instance, never relying on the builder alone.
    """

    if type(spec) is not LaunchSpec:
        raise SpineError(RUNTIME_INVALID_LAUNCH_SPEC)
    _check_launch_spec_fields(spec)
