"""PR5 single-user production-shaped E2E over the agent-run-supervisor spine.

This module is the final agent-run-supervisor integration slice: a bounded,
single-user, **default-off, local/offline** E2E proof that the already-merged
PR1-PR4 pieces compose safely behind a deterministic fixture. It is NOT a
production rollout — it starts no real agent/process/network/durable service,
opens no listener, touches no committed repo file, writes no production config,
and calls no Gateway / IM / delivery surface. Importing it starts nothing.

It reuses the merged surfaces rather than duplicating logic:

* the *real* PR1 :class:`AgentRunSupervisorPort` over the deterministic in-memory
  :class:`DefaultAgentRunSupervisorBackend`;
* the R1 :class:`TaskRegistry` + refs-only projection helpers;
* the R4 :class:`WorkspaceLeaseStore` single-writer lease;
* the PR4 :func:`build_agent_run_supervisor_workbench_view` renderable surface.

The bounded E2E flow, refs-only and fail-closed:

1. bind exactly one read-only role/policy launch spec + a single-writer lease;
2. ``create_or_attach`` twice **and** reconstruct the port over the same registry
   + backend, proving one live session and exactly one ``agent_attached`` event
   (a supervisor restart re-attaches; it never respawns / duplicates);
3. optionally drive a deterministic ``permission_wait`` + operator ``signal``
   decision path if the fixture asks for it (refs-only, no raw material);
4. build the workbench view **before** cleanup and prove it is renderable through
   safe refs-only fields with no leak;
5. ``kill`` -> terminal / orphan-free, then ``release`` the lease deterministically;
6. prove rollback-safety — after cleanup a reconstructed port re-attaches to the
   already-terminal session with no respawn / no new event and no lease/session
   leak — and summarize everything in a sanitized :class:`ProductionE2EReport`.

The report is a frozen, refs-only value object that is fail-closed validated,
byte-stable serializable, and no-leak scanned: a forged fixture / report or any
raw material fails closed with a stable code only and is never echoed. The runner
never fakes a pass — an invariant miss is a recorded ``failed`` / ``blocked``
report, and a raising / mismatched backend or an unavailable lease collapses to a
stable blocker code with no half-written state surfaced.

This module does **not** authorize production上线, live ingress, real delivery,
Gateway behavior, Temporal Worker startup, or production config; those remain
separate, explicitly-approved gates. Forbidden terms appear only as inherited R1
no-leak denylist canaries, never as behavior.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, NoReturn

from .agent_run_supervisor_port import (
    RUNTIME_SUPERVISOR_BACKEND_FAILURE,
    AgentRunSupervisorBackend,
    AgentRunSupervisorPort,
    DefaultAgentRunSupervisorBackend,
)
from .agent_run_supervisor_workbench import (
    build_agent_run_supervisor_workbench_view,
    serialize_agent_run_supervisor_workbench_view,
)
from .events import (
    SpineError,
    _safe_id,
    event_projection,
    safe_task_id,
    scan_for_leak,
)
from .execution_port import TERMINAL_SESSION_STATES
from .launch_spec import build_launch_spec
from .projection import project, serialize_projection
from .registry import TaskRegistry
from .workspace import (
    RUNTIME_INVALID_WORKSPACE_LEASE,
    RUNTIME_WORKSPACE_LEASE_CONFLICT,
    WorkspaceLeaseStore,
    acquire_workspace_lease,
    release_workspace_lease,
)

# --------------------------------------------------------------------------- #
# The one read-only role/policy this E2E will ever bind — matches the PR1
# adapter's sole admitted role and the R4 default-deny permission allowlist.
# --------------------------------------------------------------------------- #
READ_ONLY_ROLE = "read_only"
_SUPERVISOR_AGENT_KIND = "local_agent"
_WORKSPACE_REF_PREFIX = "ws_"
_POLICY_REF_PREFIX = "policy_"

# --------------------------------------------------------------------------- #
# Stable error-code family (lowercase, <=64 chars; safe to surface in evidence)
# --------------------------------------------------------------------------- #
E2E_INVALID_FIXTURE = "e2e_invalid_fixture"
E2E_INVALID_REPORT = "e2e_invalid_report"
E2E_INVARIANT_VIOLATION = "e2e_invariant_violation"
E2E_UNEXPECTED_LEAK = "e2e_unexpected_leak"
E2E_BACKEND_FAILURE = "e2e_backend_failure"
E2E_LEASE_UNAVAILABLE = "e2e_lease_unavailable"

E2E_STABLE_CODES = frozenset(
    {
        E2E_INVALID_FIXTURE,
        E2E_INVALID_REPORT,
        E2E_INVARIANT_VIOLATION,
        E2E_UNEXPECTED_LEAK,
        E2E_BACKEND_FAILURE,
        E2E_LEASE_UNAVAILABLE,
    }
)

E2E_REPORT_TYPE = "sachima.runtime_spine.agent_run_supervisor_production_e2e_report.v1"

#: Closed report status / check-value / terminal-state / projected-status
#: allowlists — a validated report can only ever carry these.
_REPORT_STATUSES = frozenset({"pass", "failed", "blocked"})
_CHECK_VALUES = frozenset({"pass", "fail", "blocked", "skip"})
_PROJECTED_STATUSES = frozenset(
    {"created", "running", "permission_wait", "completed", "failed", "cancelled"}
)

#: The safety invariants a *passing* single-user E2E always holds.
_PASS_REQUIRED_FLAGS = (
    "single_session",
    "duplicate_attach_suppressed",
    "workbench_renderable",
    "cleanup_terminal",
    "orphan_free",
    "lease_released",
    "rollback_safe",
    "no_leak",
)

#: Spine stable codes a caught :class:`SpineError` maps onto, so a report's
#: blockers stay inside the closed :data:`E2E_STABLE_CODES` allowlist.
_SPINE_CODE_TO_E2E = {
    RUNTIME_SUPERVISOR_BACKEND_FAILURE: E2E_BACKEND_FAILURE,
    RUNTIME_WORKSPACE_LEASE_CONFLICT: E2E_LEASE_UNAVAILABLE,
    RUNTIME_INVALID_WORKSPACE_LEASE: E2E_LEASE_UNAVAILABLE,
}


def _invalid_fixture() -> NoReturn:
    raise SpineError(E2E_INVALID_FIXTURE)


def _invalid_report() -> NoReturn:
    raise SpineError(E2E_INVALID_REPORT)


def _safe_fixture_ref(value: Any) -> str:
    """A refs-only fixture field — a safe id, never raw / platform / path material."""

    return _safe_id(value, code=E2E_INVALID_FIXTURE)


# --------------------------------------------------------------------------- #
# Deterministic single-user fixture. Every forwarded field is a sanitized safe
# id; ``raw_material`` is the set of sensitive strings the E2E must NEVER forward
# into the adapter/state (raw prompt / agent output / platform id stand-ins). They
# are seeded as no-leak canaries, so the proof fails if any reaches Sachima state.
# --------------------------------------------------------------------------- #
_DEFAULT_RAW_MATERIAL = (
    "e2e_prompt_body_nonce_a1b2c3d4",
    "e2e_agent_output_nonce_e5f6a7b8",
    "e2e_platform_id_nonce_c9d0e1f2",
)


def _check_fixture_fields(fixture: Any) -> None:
    """Exact fail-closed validation of a fixture's fields.

    Fails closed on: an unsafe ``task_id``; an unsafe / path / platform / raw
    workspace / policy / artifact / holder / decision / cleanup ref; a
    ``workspace_ref`` / ``policy_ref`` that does not carry the required prefix (so
    the PR1 admission always sees a workspace + policy ref); a non-``bool``
    ``include_permission_wait``; a non-tuple / non-``str`` ``raw_material``; or any
    forbidden marker in a forwarded (non-canary) field. ``raw_material`` is
    deliberately excluded from the no-leak scan — it *is* the material the proof
    shows never leaks — and is never a forwarded field. Never echoes rejected
    material.
    """

    try:
        task_id = fixture.task_id
        workspace_ref = fixture.workspace_ref
        policy_ref = fixture.policy_ref
        artifact_ref = fixture.artifact_ref
        holder_ref = fixture.holder_ref
        decision_ref = fixture.decision_ref
        cleanup_reason_ref = fixture.cleanup_reason_ref
        include_permission_wait = fixture.include_permission_wait
        raw_material = fixture.raw_material
    except AttributeError:
        _invalid_fixture()

    safe_task_id(task_id, code=E2E_INVALID_FIXTURE)
    workspace = _safe_fixture_ref(workspace_ref)
    policy = _safe_fixture_ref(policy_ref)
    _safe_fixture_ref(artifact_ref)
    _safe_fixture_ref(holder_ref)
    _safe_fixture_ref(decision_ref)
    _safe_fixture_ref(cleanup_reason_ref)
    if not workspace.startswith(_WORKSPACE_REF_PREFIX):
        _invalid_fixture()
    if not policy.startswith(_POLICY_REF_PREFIX):
        _invalid_fixture()

    if type(include_permission_wait) is not bool:
        _invalid_fixture()

    if type(raw_material) is not tuple:
        _invalid_fixture()
    for item in raw_material:
        if type(item) is not str:
            _invalid_fixture()

    # Defense in depth: only the *forwarded* fields are leak-scanned (the canaries
    # are intentionally raw and are never forwarded anywhere).
    if scan_for_leak(_forwarded_fixture_dict(fixture)) is not None:
        _invalid_fixture()


def _forwarded_fixture_dict(fixture: Any) -> dict[str, Any]:
    """The safe, forwarded fixture fields only — excludes the raw canaries."""

    return {
        "task_id": fixture.task_id,
        "workspace_ref": fixture.workspace_ref,
        "policy_ref": fixture.policy_ref,
        "artifact_ref": fixture.artifact_ref,
        "holder_ref": fixture.holder_ref,
        "decision_ref": fixture.decision_ref,
        "cleanup_reason_ref": fixture.cleanup_reason_ref,
        "include_permission_wait": fixture.include_permission_wait,
    }


@dataclass(frozen=True)
class ProductionE2EFixture:
    """One deterministic, refs-only single-user E2E fixture (safe fields + canaries).

    Exported public surface, so construction alone is never grounds for trust:
    ``__post_init__`` re-runs the exact-type refs-only allowlist so a direct
    ``ProductionE2EFixture(...)`` carrying a raw / platform ref or a bad prefix
    fails closed. Boundary consumers additionally call
    :func:`validate_production_e2e_fixture` to defend against ``object.__new__``
    forgery and hostile subclasses that skip ``__post_init__``.
    """

    task_id: str = "task_e2e_alpha"
    workspace_ref: str = "ws_e2e_alpha"
    policy_ref: str = "policy_read_only_default"
    artifact_ref: str = "ref_planning_report"
    holder_ref: str = "ref_e2e_holder"
    decision_ref: str = "ref_e2e_decision_allow"
    cleanup_reason_ref: str = "ref_e2e_cleanup"
    include_permission_wait: bool = False
    raw_material: tuple[str, ...] = _DEFAULT_RAW_MATERIAL

    def __post_init__(self) -> None:
        _check_fixture_fields(self)

    @property
    def launch_refs(self) -> tuple[str, ...]:
        """The refs the PR1 admission sees — a workspace, a policy, an artifact ref."""

        return (self.workspace_ref, self.policy_ref, self.artifact_ref)


def validate_production_e2e_fixture(fixture: Any) -> ProductionE2EFixture:
    """Re-validate a fixture at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type or any unsafe / bad-prefix field fails
    closed with the stable ``e2e_invalid_fixture`` code, never echoing material.
    """

    if type(fixture) is not ProductionE2EFixture:
        _invalid_fixture()
    _check_fixture_fields(fixture)
    return fixture


# --------------------------------------------------------------------------- #
# Sanitized, fail-closed, byte-stable E2E report
# --------------------------------------------------------------------------- #
def _check_count(value: Any) -> int:
    # bool is an int subclass — exclude it so a flag can't pose as a count.
    if type(value) is not int or value < 0:
        _invalid_report()
    return value


def _check_bool(value: Any) -> bool:
    if type(value) is not bool:
        _invalid_report()
    return value


def _normalize_checks(value: Any, *, allow_input: bool) -> tuple[tuple[str, str], ...]:
    """Normalize the checks map to a canonical, byte-stable tuple-of-pairs.

    A mutable ``Mapping`` is accepted only on construction (``allow_input``); a
    validated report must already carry the immutable tuple-of-pairs form. Every
    key is a safe id and every value is in the closed :data:`_CHECK_VALUES` set;
    anything else fails closed as :data:`E2E_INVALID_REPORT`.
    """

    if isinstance(value, Mapping):
        if not allow_input:
            _invalid_report()
        pairs: list[tuple[Any, Any]] = list(value.items())
    elif type(value) is tuple:
        pairs = list(value)
    else:
        _invalid_report()

    seen: dict[str, str] = {}
    for pair in pairs:
        if type(pair) is not tuple or len(pair) != 2:
            _invalid_report()
        key, val = pair
        safe_key = _safe_id(key, code=E2E_INVALID_REPORT)
        if safe_key in seen:
            _invalid_report()
        if type(val) is not str or val not in _CHECK_VALUES:
            _invalid_report()
        seen[safe_key] = val
    return tuple(sorted(seen.items()))


def _normalize_blockers(value: Any, *, allow_input: bool) -> tuple[str, ...]:
    """Normalize blockers to an immutable tuple of closed stable codes, fail-closed."""

    if type(value) is list:
        if not allow_input:
            _invalid_report()
        items = tuple(value)
    elif type(value) is tuple:
        items = value
    else:
        _invalid_report()
    for code in items:
        if type(code) is not str or code not in E2E_STABLE_CODES:
            _invalid_report()
    return tuple(items)


def _normalize_artifact_refs(value: Any, *, allow_input: bool) -> tuple[str, ...]:
    """Normalize artifact refs to a sorted-unique tuple of safe ids, fail-closed."""

    if type(value) is list:
        if not allow_input:
            _invalid_report()
        items = value
    elif type(value) is tuple:
        items = list(value)
    else:
        _invalid_report()
    safe_refs = tuple(_safe_id(ref, code=E2E_INVALID_REPORT) for ref in items)
    # project()-style canonical order: de-duped, sorted — a duplicate / unsorted
    # list is a forged shape a genuine report never emits.
    if list(safe_refs) != sorted(set(safe_refs)):
        _invalid_report()
    return safe_refs


def _raw_report_dict(report: Any) -> dict[str, Any]:
    return {
        "type": report.type,
        "schema_version": report.schema_version,
        "status": report.status,
        "role": report.role,
        "task_ref": report.task_ref,
        "session_ref": report.session_ref,
        "single_session": report.single_session,
        "duplicate_attach_suppressed": report.duplicate_attach_suppressed,
        "attach_event_count": report.attach_event_count,
        "backend_session_count": report.backend_session_count,
        "workbench_renderable": report.workbench_renderable,
        "permission_path_included": report.permission_path_included,
        "operator_decision_applied": report.operator_decision_applied,
        "cleanup_terminal": report.cleanup_terminal,
        "terminal_state": report.terminal_state,
        "orphan_free": report.orphan_free,
        "lease_released": report.lease_released,
        "rollback_safe": report.rollback_safe,
        "no_leak": report.no_leak,
        "event_count": report.event_count,
        "artifact_refs": report.artifact_refs,
        "projection_status": report.projection_status,
        "checks": report.checks,
        "blockers": report.blockers,
    }


def _check_report_fields(report: Any, *, normalize: bool = False) -> None:
    """Exact fail-closed validation of an E2E report's fields.

    Fails closed on: a forged ``type`` / ``schema_version``; a status / role /
    terminal-state / projected-status outside its closed allowlist; an unsafe
    ``task_ref`` / ``session_ref``; a non-``bool`` flag; a negative / non-``int``
    count; a malformed ``checks`` / ``artifact_refs`` / ``blockers`` set; a broken
    cross-field invariant (a ``pass`` with a blocker or a missing safety flag; a
    non-``pass`` with no blocker; ``no_leak`` inconsistent with the leak blocker;
    an operator decision without the permission path); or any forbidden marker
    anywhere in the report. Never echoes the rejected material.
    """

    try:
        r_type = report.type
        schema_version = report.schema_version
        status = report.status
        role = report.role
        task_ref = report.task_ref
        session_ref = report.session_ref
        single_session = report.single_session
        duplicate_attach_suppressed = report.duplicate_attach_suppressed
        attach_event_count = report.attach_event_count
        backend_session_count = report.backend_session_count
        workbench_renderable = report.workbench_renderable
        permission_path_included = report.permission_path_included
        operator_decision_applied = report.operator_decision_applied
        cleanup_terminal = report.cleanup_terminal
        terminal_state = report.terminal_state
        orphan_free = report.orphan_free
        lease_released = report.lease_released
        rollback_safe = report.rollback_safe
        no_leak = report.no_leak
        event_count = report.event_count
        artifact_refs = report.artifact_refs
        projection_status = report.projection_status
        checks = report.checks
        blockers = report.blockers
    except AttributeError:
        _invalid_report()

    if type(r_type) is not str or r_type != E2E_REPORT_TYPE:
        _invalid_report()
    if type(schema_version) is not int or schema_version != 1:
        _invalid_report()
    if type(status) is not str or status not in _REPORT_STATUSES:
        _invalid_report()
    if type(role) is not str or role != READ_ONLY_ROLE:
        _invalid_report()

    if task_ref is not None:
        safe_task_id(task_ref, code=E2E_INVALID_REPORT)
    if session_ref is not None:
        if type(session_ref) is not str or not session_ref.startswith("sess_"):
            _invalid_report()
        _safe_id(session_ref, code=E2E_INVALID_REPORT)

    flags = {
        "single_session": _check_bool(single_session),
        "duplicate_attach_suppressed": _check_bool(duplicate_attach_suppressed),
        "workbench_renderable": _check_bool(workbench_renderable),
        "permission_path_included": _check_bool(permission_path_included),
        "operator_decision_applied": _check_bool(operator_decision_applied),
        "cleanup_terminal": _check_bool(cleanup_terminal),
        "orphan_free": _check_bool(orphan_free),
        "lease_released": _check_bool(lease_released),
        "rollback_safe": _check_bool(rollback_safe),
        "no_leak": _check_bool(no_leak),
    }
    _check_count(attach_event_count)
    _check_count(backend_session_count)
    _check_count(event_count)

    if terminal_state is not None and (
        type(terminal_state) is not str or terminal_state not in TERMINAL_SESSION_STATES
    ):
        _invalid_report()
    if projection_status is not None and (
        type(projection_status) is not str or projection_status not in _PROJECTED_STATUSES
    ):
        _invalid_report()

    safe_checks = _normalize_checks(checks, allow_input=normalize)
    safe_refs = _normalize_artifact_refs(artifact_refs, allow_input=normalize)
    safe_blockers = _normalize_blockers(blockers, allow_input=normalize)

    # Cross-field invariants a genuine report always holds.
    if status == "pass":
        if safe_blockers:
            _invalid_report()
        for name in _PASS_REQUIRED_FLAGS:
            if flags[name] is not True:
                _invalid_report()
        if task_ref is None or session_ref is None:
            _invalid_report()
        if attach_event_count != 1 or backend_session_count != 1:
            _invalid_report()
        if permission_path_included and operator_decision_applied is not True:
            _invalid_report()
    else:
        if not safe_blockers:
            _invalid_report()
    # An operator decision can only have been applied through the permission path.
    if flags["operator_decision_applied"] and flags["permission_path_included"] is not True:
        _invalid_report()
    # ``no_leak`` must agree with the presence of the leak blocker.
    if (E2E_UNEXPECTED_LEAK in safe_blockers) is flags["no_leak"]:
        _invalid_report()

    if normalize:
        object.__setattr__(report, "checks", safe_checks)
        object.__setattr__(report, "artifact_refs", safe_refs)
        object.__setattr__(report, "blockers", safe_blockers)

    if scan_for_leak(_raw_report_dict(report)) is not None:
        _invalid_report()


@dataclass(frozen=True)
class ProductionE2EReport:
    """Frozen, refs-only, fail-closed single-user E2E report.

    Mapping/list inputs (``checks`` / ``artifact_refs`` / ``blockers``) are
    normalized to immutable tuple shapes during construction so a caller cannot
    mutate a built report into echoing raw material. ``__post_init__`` re-runs the
    full fail-closed allowlist so a directly-constructed or forged report fails
    closed instead of being trusted; ``as_dict`` / ``serialize_...`` re-validate
    before emitting, and ``to_projection`` is a never-raising observable surface
    that falls back to a leak-safe shape.
    """

    status: str
    role: str
    task_ref: str | None
    session_ref: str | None
    single_session: bool
    duplicate_attach_suppressed: bool
    attach_event_count: int
    backend_session_count: int
    workbench_renderable: bool
    permission_path_included: bool
    operator_decision_applied: bool
    cleanup_terminal: bool
    terminal_state: str | None
    orphan_free: bool
    lease_released: bool
    rollback_safe: bool
    no_leak: bool
    event_count: int
    artifact_refs: Any
    projection_status: str | None
    checks: Any = field(default_factory=dict)
    blockers: Any = ()
    type: str = E2E_REPORT_TYPE
    schema_version: int = 1

    def __post_init__(self) -> None:
        _check_report_fields(self, normalize=True)

    def as_dict(self) -> dict[str, Any]:
        validate_production_e2e_report(self)
        return {
            "type": self.type,
            "schema_version": self.schema_version,
            "status": self.status,
            "role": self.role,
            "task_ref": self.task_ref,
            "session_ref": self.session_ref,
            "single_session": self.single_session,
            "duplicate_attach_suppressed": self.duplicate_attach_suppressed,
            "attach_event_count": self.attach_event_count,
            "backend_session_count": self.backend_session_count,
            "workbench_renderable": self.workbench_renderable,
            "permission_path_included": self.permission_path_included,
            "operator_decision_applied": self.operator_decision_applied,
            "cleanup_terminal": self.cleanup_terminal,
            "terminal_state": self.terminal_state,
            "orphan_free": self.orphan_free,
            "lease_released": self.lease_released,
            "rollback_safe": self.rollback_safe,
            "no_leak": self.no_leak,
            "event_count": self.event_count,
            "artifact_refs": list(self.artifact_refs),
            "projection_status": self.projection_status,
            "checks": {key: value for key, value in self.checks},
            "blockers": list(self.blockers),
        }

    def to_projection(self) -> dict[str, Any]:
        """Never-raising observable projection; leak-safe fallback on any problem."""

        try:
            return self.as_dict()
        except SpineError:
            return _leak_safe_e2e_projection(self)


def _leak_safe_e2e_projection(report: ProductionE2EReport) -> dict[str, Any]:
    return {
        "type": E2E_REPORT_TYPE,
        "schema_version": 1,
        "status": "failed",
        "role": READ_ONLY_ROLE,
        "task_ref": None,
        "session_ref": None,
        "single_session": False,
        "duplicate_attach_suppressed": False,
        "attach_event_count": 0,
        "backend_session_count": 0,
        "workbench_renderable": False,
        "permission_path_included": False,
        "operator_decision_applied": False,
        "cleanup_terminal": False,
        "terminal_state": None,
        "orphan_free": False,
        "lease_released": False,
        "rollback_safe": False,
        "no_leak": False,
        "event_count": 0,
        "artifact_refs": [],
        "projection_status": None,
        "checks": {},
        "blockers": [E2E_UNEXPECTED_LEAK],
    }


def validate_production_e2e_report(report: Any) -> ProductionE2EReport:
    """Re-validate an E2E report at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type or any unsafe / inconsistent field fails
    closed with the stable ``e2e_invalid_report`` code, never echoing material.
    """

    if type(report) is not ProductionE2EReport:
        _invalid_report()
    _check_report_fields(report)
    return report


def serialize_production_e2e_report(report: ProductionE2EReport) -> bytes:
    """Byte-stable canonical JSON serialization after full re-validation."""

    validated = validate_production_e2e_report(report)
    return json.dumps(validated.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


# --------------------------------------------------------------------------- #
# The bounded single-user production-shaped E2E
# --------------------------------------------------------------------------- #
def run_single_user_production_e2e(
    *,
    backend: AgentRunSupervisorBackend | None = None,
    fixture: ProductionE2EFixture | None = None,
    lease_store: WorkspaceLeaseStore | None = None,
) -> ProductionE2EReport:
    """Drive the real PR1-PR4 pieces through the bounded single-user E2E, once.

    The default backend is the deterministic in-memory
    :class:`DefaultAgentRunSupervisorBackend` and the default stores are fresh
    in-memory objects — no real agent, process, network, durable service, Gateway,
    or delivery surface. A caller may inject a deterministic backend / fixture /
    lease store for tests, but the default path stays local and deterministic.
    Returns a sanitized :class:`ProductionE2EReport`; it never raises on an
    invariant miss and never fakes a pass.
    """

    try:
        fixture = validate_production_e2e_fixture(
            fixture if fixture is not None else ProductionE2EFixture()
        )
    except SpineError:
        # A forged / unsafe fixture never even starts the flow — and its material
        # is never echoed (only the stable admission code is surfaced).
        return _blocked_e2e_report(
            None, code=E2E_INVALID_FIXTURE, checks={"fixture_admitted": "fail"}
        )

    backend = backend if backend is not None else DefaultAgentRunSupervisorBackend()
    registry = TaskRegistry()
    lease_store = lease_store if lease_store is not None else WorkspaceLeaseStore()
    port = AgentRunSupervisorPort(registry, backend)

    try:
        return _execute_e2e(fixture, backend, registry, port, lease_store)
    except SpineError as exc:
        code = exc.code if exc.code in E2E_STABLE_CODES else _SPINE_CODE_TO_E2E.get(
            exc.code, E2E_INVARIANT_VIOLATION
        )
        return _blocked_e2e_report(
            fixture, code=code, checks={"e2e_completed": "fail"}, status="failed"
        )


def _execute_e2e(
    fixture: ProductionE2EFixture,
    backend: AgentRunSupervisorBackend,
    registry: TaskRegistry,
    port: AgentRunSupervisorPort,
    lease_store: WorkspaceLeaseStore,
) -> ProductionE2EReport:
    checks: dict[str, str] = {}
    blockers: list[str] = []

    # 1. Bind exactly one read-only role/policy launch spec + single-writer lease.
    spec = build_launch_spec(
        task_id=fixture.task_id,
        agent_kind=_SUPERVISOR_AGENT_KIND,
        mode_flags={"needs_agent": True},
        roles=(READ_ONLY_ROLE,),
        refs=fixture.launch_refs,
    )
    lease = acquire_workspace_lease(
        lease_store,
        task_id=fixture.task_id,
        holder=fixture.holder_ref,
        workspace_ref=fixture.workspace_ref,
        now=0,
        ttl=3600,
    )

    # 2. create_or_attach twice, then reconstruct the port over the SAME registry +
    #    backend (a supervisor restart) — one live session, one agent_attached.
    ref_first = port.create_or_attach(fixture.task_id, spec)
    ref_second = port.create_or_attach(fixture.task_id, spec)
    reconstructed = AgentRunSupervisorPort(registry, backend)
    ref_reattach = reconstructed.create_or_attach(fixture.task_id, spec)

    attach_events = _attach_event_count(registry, fixture.task_id)
    backend_sessions = _session_count(backend)
    duplicate_attach_suppressed = (
        ref_first == ref_second == ref_reattach
        and attach_events == 1
        and backend_sessions == 1
    )
    single_session = (
        port.session_count() == 1
        and reconstructed.session_count() == 1
        and backend_sessions == 1
    )
    _record(checks, blockers, "single_session", single_session)
    _record(checks, blockers, "duplicate_attach_suppressed", duplicate_attach_suppressed)

    # 3. Optional deterministic permission-wait + operator-decision path (refs-only).
    permission_path_included = fixture.include_permission_wait
    operator_decision_applied = False
    if permission_path_included:
        backend.fake_enter_permission_wait(fixture.task_id)
        waiting = port.status(ref_first)  # persist permission_wait into the log
        wait_view = build_agent_run_supervisor_workbench_view(registry, port, ref_first)
        permission_surfaced = (
            waiting.state == "permission_wait"
            and wait_view.permission_state == "waiting"
            and wait_view.requires_operator_decision is True
        )
        _record(checks, blockers, "permission_wait_surfaced", permission_surfaced)
        resumed = port.signal(fixture.task_id, fixture.decision_ref)
        operator_decision_applied = resumed.state == "running"
        _record(checks, blockers, "operator_decision_applied", operator_decision_applied)

    # 4. Build the workbench view BEFORE cleanup — renderable through refs-only fields.
    live_status = port.status(ref_first)
    view = build_agent_run_supervisor_workbench_view(registry, port, ref_first)
    view_dict = view.as_dict()
    serialized_view = serialize_agent_run_supervisor_workbench_view(view)
    workbench_renderable = (
        live_status.alive
        and not live_status.terminal
        and view_dict["task_id"] == fixture.task_id
        and view_dict["session_id"] == ref_first.session_id
        and view_dict["attach_count"] == 1
        and scan_for_leak(view_dict, canaries=fixture.raw_material) is None
    )
    _record(checks, blockers, "workbench_renderable", workbench_renderable)

    # Exercise stream — confirm it returns only refs-only projections.
    stream_events = tuple(port.stream(ref_first))

    # 5. Cleanup: kill -> terminal / orphan-free, then release the lease.
    killed = port.kill(ref_first, fixture.cleanup_reason_ref)
    liveness = port.liveness(ref_first)
    cleanup_terminal = (
        killed.terminal
        and not killed.alive
        and killed.state in TERMINAL_SESSION_STATES
    )
    orphan_free = (
        cleanup_terminal
        and not liveness.reapable
        and liveness.state in TERMINAL_SESSION_STATES
    )
    _record(checks, blockers, "cleanup_terminal", cleanup_terminal)
    _record(checks, blockers, "orphan_free", orphan_free)

    release_workspace_lease(
        lease_store,
        task_id=fixture.task_id,
        holder=fixture.holder_ref,
        token=lease.token,
    )
    lease_released = lease_store.active_count() == 0
    _record(checks, blockers, "lease_released", lease_released)

    # 6. Rollback safety — a reconstructed port after cleanup re-attaches to the
    #    already-terminal session with no respawn / no new event and no leak.
    seq_after_cleanup = registry.log.last_seq(fixture.task_id)
    rollback_port = AgentRunSupervisorPort(registry, backend)
    rollback_ref = rollback_port.create_or_attach(fixture.task_id, spec)
    rollback_status = rollback_port.status(rollback_ref)
    rollback_safe = (
        rollback_ref == ref_first
        and registry.log.last_seq(fixture.task_id) == seq_after_cleanup
        and _attach_event_count(registry, fixture.task_id) == 1
        and _session_count(backend) == 1
        and rollback_status.terminal
        and lease_store.active_count() == 0
    )
    _record(checks, blockers, "rollback_safe", rollback_safe)

    # Collect the full sanitized Sachima state and prove no raw material leaked.
    events = registry.log.events_for(fixture.task_id)
    event_projections = [event_projection(event) for event in events]
    status_projection = project(events, task_id=fixture.task_id)
    serialized_projection = serialize_projection(status_projection).decode("utf-8")
    leak = scan_for_leak(
        [
            event_projections,
            status_projection,
            serialized_projection,
            view_dict,
            serialized_view.decode("utf-8"),
            [dict(chunk) for chunk in stream_events],
        ],
        canaries=fixture.raw_material,
    )
    no_leak = leak is None
    _record(checks, blockers, "no_raw_material_in_state", no_leak)
    if not no_leak:
        _add(blockers, E2E_UNEXPECTED_LEAK)

    artifact_refs = tuple(status_projection["refs"])
    artifact_ref_present = fixture.artifact_ref in artifact_refs
    _record(checks, blockers, "artifact_ref_projected", artifact_ref_present)

    status = "pass" if not blockers else "failed"
    return ProductionE2EReport(
        status=status,
        role=READ_ONLY_ROLE,
        task_ref=fixture.task_id,
        session_ref=ref_first.session_id,
        single_session=single_session,
        duplicate_attach_suppressed=duplicate_attach_suppressed,
        attach_event_count=attach_events,
        backend_session_count=backend_sessions,
        workbench_renderable=workbench_renderable,
        permission_path_included=permission_path_included,
        operator_decision_applied=operator_decision_applied,
        cleanup_terminal=cleanup_terminal,
        terminal_state=killed.state,
        orphan_free=orphan_free,
        lease_released=lease_released,
        rollback_safe=rollback_safe,
        no_leak=no_leak,
        event_count=registry.log.last_seq(fixture.task_id),
        artifact_refs=artifact_refs,
        projection_status=status_projection["status"],
        checks=checks,
        blockers=tuple(blockers),
    )


def _blocked_e2e_report(
    fixture: ProductionE2EFixture | None,
    *,
    code: str,
    checks: Mapping[str, str],
    status: str = "blocked",
) -> ProductionE2EReport:
    """A fully-safe blocked/failed report — no partial state, no leak."""

    return ProductionE2EReport(
        status=status,
        role=READ_ONLY_ROLE,
        task_ref=fixture.task_id if fixture is not None else None,
        session_ref=None,
        single_session=False,
        duplicate_attach_suppressed=False,
        attach_event_count=0,
        backend_session_count=0,
        workbench_renderable=False,
        permission_path_included=(
            fixture.include_permission_wait if fixture is not None else False
        ),
        operator_decision_applied=False,
        cleanup_terminal=False,
        terminal_state=None,
        orphan_free=False,
        lease_released=False,
        rollback_safe=False,
        no_leak=True,
        event_count=0,
        artifact_refs=(),
        projection_status=None,
        checks=dict(checks),
        blockers=(code,),
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _record(checks: dict[str, str], blockers: list[str], name: str, ok: bool) -> None:
    checks[name] = "pass" if ok else "fail"
    if not ok:
        _add(blockers, E2E_INVARIANT_VIOLATION)


def _add(blockers: list[str], code: str) -> None:
    if code not in blockers:
        blockers.append(code)


def _attach_event_count(registry: TaskRegistry, task_id: str) -> int:
    return sum(
        1
        for event in registry.log.events_for(task_id)
        if event.event_type == "agent_attached"
    )


def _session_count(backend: AgentRunSupervisorBackend) -> int:
    counter = getattr(backend, "session_count", None)
    if callable(counter):
        value = counter()
        if type(value) is int and value >= 0:
            return value
    return -1


__all__ = [
    "READ_ONLY_ROLE",
    "E2E_INVALID_FIXTURE",
    "E2E_INVALID_REPORT",
    "E2E_INVARIANT_VIOLATION",
    "E2E_UNEXPECTED_LEAK",
    "E2E_BACKEND_FAILURE",
    "E2E_LEASE_UNAVAILABLE",
    "E2E_STABLE_CODES",
    "E2E_REPORT_TYPE",
    "ProductionE2EFixture",
    "ProductionE2EReport",
    "validate_production_e2e_fixture",
    "validate_production_e2e_report",
    "serialize_production_e2e_report",
    "run_single_user_production_e2e",
]
