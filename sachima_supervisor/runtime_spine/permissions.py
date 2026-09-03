"""R4 Runtime Spine — permission roundtrip + read-only/default-deny policy.

A permission *request* emits a refs-only ``permission_requested`` /
``permission_wait`` event through the R1 Task Registry / Event Log — never raw
prompt/context, tool output, platform ids, or private paths. A permission *answer*
returns solely through the Hermes-controlled ``signal(task_id, decision_ref)``
model: the helper reaches the supervisor only across the ``ExecutionPort`` signal
boundary — it never creates, attaches, streams, kills, probes, or queries status.
Role policy is **default-deny**: read-only is the maximum capability; unknown /
write-capable / mutation / delivery / approval roles all fail closed.

Everything here is pure local/offline Python: it opens no listener, launches no
process, and wires no platform or delivery surface. Forbidden material is rejected
at the trust boundary and never echoed back — only the stable code is surfaced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn

from .events import SpineError, _safe_id, build_event_body, safe_task_id
from .execution_port import ExecutionPort, SessionStatus, validate_session_status
from .registry import TaskRegistry

# --------------------------------------------------------------------------- #
# Stable error-code family (fail-closed; the message is the code, never input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_PERMISSION = "runtime_invalid_permission"
RUNTIME_PERMISSION_ROLE_DENIED = "runtime_permission_role_denied"

PERMISSION_STABLE_CODES = frozenset(
    {RUNTIME_INVALID_PERMISSION, RUNTIME_PERMISSION_ROLE_DENIED}
)

#: Closed, read-only role allowlist. Default-deny: read-only is the maximum
#: capability — there is no write / deliver / approve / reject / mutate / admin
#: member, so any role outside this set fails closed.
ALLOWED_PERMISSION_ROLES = frozenset({"read_only"})

#: Closed operator verdict vocabulary — the answer is allow or deny, nothing else.
PERMISSION_VERDICTS = frozenset({"allow", "deny"})


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_PERMISSION)


def _role_denied() -> NoReturn:
    raise SpineError(RUNTIME_PERMISSION_ROLE_DENIED)


def _safe_perm_ref(value: Any) -> str:
    """A refs-only permission field — a safe id, never raw/platform/path material."""

    return _safe_id(value, code=RUNTIME_INVALID_PERMISSION)


# --------------------------------------------------------------------------- #
# Role policy — default-deny; read-only is the maximum capability
# --------------------------------------------------------------------------- #
def validate_role_policy(role: Any) -> str:
    """Return ``role`` iff it is inside the closed read-only allowlist, else deny.

    Every role outside :data:`ALLOWED_PERMISSION_ROLES` — unknown, write-capable,
    mutation, delivery, or approval — fails closed with
    :data:`RUNTIME_PERMISSION_ROLE_DENIED`.
    """

    if type(role) is not str or role not in ALLOWED_PERMISSION_ROLES:
        _role_denied()
    return role


@dataclass(frozen=True)
class PermissionPolicy:
    """Default-deny, read-only role policy.

    The default allowlist is exactly the canonical read-only allowlist; a policy
    can only ever *narrow* it — a policy constructed with any role outside the
    canonical read-only allowlist fails closed at construction.
    """

    allowed_roles: frozenset[str] = ALLOWED_PERMISSION_ROLES

    def __post_init__(self) -> None:
        if type(self.allowed_roles) is not frozenset:
            _invalid()
        for role in self.allowed_roles:
            if type(role) is not str or role not in ALLOWED_PERMISSION_ROLES:
                _role_denied()

    def validate_role(self, role: Any) -> str:
        if type(role) is not str or role not in self.allowed_roles:
            _role_denied()
        return role


# --------------------------------------------------------------------------- #
# Permission request — refs-only producer over the R1 registry boundary
# --------------------------------------------------------------------------- #
def _check_request_fields(request: Any) -> None:
    """Exact fail-closed validation of a permission request's fields."""

    try:
        task_id = request.task_id
        prompt_ref = request.prompt_ref
        role = request.role
        refs = request.refs
    except AttributeError:
        _invalid()
    safe_task_id(task_id, code=RUNTIME_INVALID_PERMISSION)
    _safe_perm_ref(prompt_ref)
    if type(refs) is not tuple:
        _invalid()
    for ref in refs:
        _safe_perm_ref(ref)
    validate_role_policy(role)


@dataclass(frozen=True)
class PermissionRequest:
    """A refs-only permission request: a task, a prompt ref, a role, and refs.

    Exported public surface, so construction alone is never grounds for trust:
    ``__post_init__`` re-runs the refs-only allowlist and the read-only role policy
    so a direct ``PermissionRequest(...)`` carrying raw material or a write-capable
    role fails closed instead of being trusted.
    """

    task_id: str
    prompt_ref: str
    role: str
    refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _check_request_fields(self)


def validate_permission_request(request: Any) -> PermissionRequest:
    """Re-validate a :class:`PermissionRequest` at a trust boundary, unchanged."""

    if type(request) is not PermissionRequest:
        _invalid()
    _check_request_fields(request)
    return request


def request_permission(
    registry: TaskRegistry,
    *,
    task_id: str,
    prompt_ref: str,
    role: str,
    refs: tuple[str, ...] = (),
) -> PermissionRequest:
    """Append a refs-only ``permission_requested`` / ``permission_wait`` event.

    Requires the exact R1 ``TaskRegistry`` (never a supervisor execution port) and
    an existing task; enforces the read-only role policy and refs-only allowlist
    before anything is appended. Fails closed — with no event leaked into the
    canonical log — on a non-registry, a denied role, a missing task, or any raw /
    platform prompt/ref material.
    """

    if type(registry) is not TaskRegistry:
        _invalid()
    safe_role = validate_role_policy(role)
    safe_task = safe_task_id(task_id, code=RUNTIME_INVALID_PERMISSION)
    safe_prompt = _safe_perm_ref(prompt_ref)
    if type(refs) not in (tuple, list):
        _invalid()
    safe_refs = tuple(_safe_perm_ref(ref) for ref in refs)
    if not registry.has_task(safe_task):
        _invalid()

    request = PermissionRequest(
        task_id=safe_task, prompt_ref=safe_prompt, role=safe_role, refs=safe_refs
    )
    registry.append_event(
        safe_task,
        build_event_body(
            event_type="permission_requested",
            status="permission_wait",
            refs=(safe_prompt, *safe_refs),
        ),
    )
    return request


# --------------------------------------------------------------------------- #
# Permission answer — returns solely through the Hermes-controlled signal path
# --------------------------------------------------------------------------- #
def _check_decision_fields(decision: Any) -> None:
    """Exact fail-closed validation of a permission decision's fields."""

    try:
        task_id = decision.task_id
        verdict = decision.decision
        decision_ref = decision.decision_ref
    except AttributeError:
        _invalid()
    safe_task_id(task_id, code=RUNTIME_INVALID_PERMISSION)
    if type(verdict) is not str or verdict not in PERMISSION_VERDICTS:
        _invalid()
    _safe_perm_ref(decision_ref)


@dataclass(frozen=True)
class PermissionDecision:
    """A refs-only operator decision: a task, an allow/deny verdict, a decision ref.

    Exported public surface, so ``__post_init__`` re-runs the closed verdict
    vocabulary and the refs-only allowlist: a direct ``PermissionDecision(...)``
    with an unknown verdict or a raw/platform decision ref fails closed.
    """

    task_id: str
    decision: str
    decision_ref: str

    def __post_init__(self) -> None:
        _check_decision_fields(self)


def validate_permission_decision(decision: Any) -> PermissionDecision:
    """Re-validate a :class:`PermissionDecision` at a trust boundary, unchanged."""

    if type(decision) is not PermissionDecision:
        _invalid()
    _check_decision_fields(decision)
    return decision


def apply_permission_decision(port: ExecutionPort, decision: PermissionDecision) -> SessionStatus:
    """Route a validated decision back through ``signal(task_id, decision_ref)`` only.

    Requires a compatible ``ExecutionPort`` instance and a validated
    :class:`PermissionDecision`, then calls **only** ``port.signal`` — never
    create/attach, stream, status, kill, or liveness — and returns the port's
    (re-validated) session status. Appends no event of its own.
    """

    if not isinstance(port, ExecutionPort):
        _invalid()
    validated = validate_permission_decision(decision)
    status = port.signal(validated.task_id, validated.decision_ref)
    return validate_session_status(status)
