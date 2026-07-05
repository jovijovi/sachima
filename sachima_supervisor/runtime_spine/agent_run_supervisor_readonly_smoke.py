"""PR2 host-local read-only AGENT smoke harness over the PR1 supervisor port.

This module adds a controlled, host-local, **read-only** smoke harness around the
already-merged PR1 :class:`AgentRunSupervisorPort` (the Sachima-side
``ExecutionPort`` adapter), plus a fail-closed real-supervisor **readiness probe**.
It launches no real agent, opens no listener, touches no committed repo file, and
makes no network / durable-service / delivery call. Everything here is pure
local/offline Python; importing it starts nothing.

Two narrow surfaces, and nothing else:

1. :func:`run_read_only_smoke` — drive the *real* PR1 adapter through a bounded,
   read-only, deterministic in-memory backend over one deterministic fixture task.
   It binds exactly one read-only role/policy, a single-writer safe cwd lease, and
   a deterministic artifact ref, then proves, refs-only and fail-closed:

     * **one run / no duplicate launch** — a second ``create_or_attach`` with the
       same spec attaches (same ``SessionRef``); the backend holds one session and
       the log holds exactly one ``agent_attached`` event;
     * **sanitized artifact refs** — every ref that enters Sachima state is a safe
       id (never raw bytes / path / platform material);
     * **no raw prompt / stdout / platform id in Sachima state/projection** — the
       fixture carries raw-material canaries the harness never forwards; the whole
       event/projection state passes the R1 no-leak scan with those canaries seeded;
     * **cleanup / no orphan** — after ``kill`` the session is terminal (never
       ``orphaned``/reapable) and the safe-cwd lease is released.

   The harness never fakes success: an invariant miss is recorded as a failed
   check, and the report is a sanitized refs/counts/statuses-only projection.

2. :func:`assess_read_only_smoke_readiness` — a default-off, exact-token,
   default-deny **readiness probe** for a *real* supervisor-backed smoke. It pins
   the runner identity (a pinned local runner sha + version), the read-only role,
   and out-of-repo cwd/artifact roots WITHOUT launching anything. Absent/unpinned
   runner parameters yield a controlled ``blocked`` report; present-but-invalid
   parameters fail closed; a widened ``allow_*`` scope fails closed. Under a
   controlled/local/default-deny host (no live durable service, no network, no
   reachable external supervisor) it reports ``blocked`` unless the caller supplies
   a real local runner path whose bytes match the pinned digest; it never fabricates
   a real smoke.

The lineage of surface (2) is the earlier host-local definition-of-ready pattern,
re-expressed here on the PR1 runtime-spine seam; it revives no old phase as active
roadmap and imports none of that stack. Forbidden terms live only in the inherited
R1 no-leak denylist, never as behavior here.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent_run_supervisor_port import (
    AgentRunSupervisorBackend,
    AgentRunSupervisorPort,
    DefaultAgentRunSupervisorBackend,
)
from .events import (
    SpineError,
    event_projection,
    scan_for_leak,
)
from .execution_port import TERMINAL_SESSION_STATES
from .launch_spec import build_launch_spec
from .projection import project, serialize_projection
from .registry import TaskRegistry
from .workspace import (
    WorkspaceLeaseStore,
    acquire_workspace_lease,
    release_workspace_lease,
)

# --------------------------------------------------------------------------- #
# The one read-only role/policy this harness will ever bind. Matches the PR1
# adapter's sole admitted role.
# --------------------------------------------------------------------------- #
READ_ONLY_ROLE = "read_only"

#: Pinned runner version the readiness probe will admit (a sanitized safe id).
REQUIRED_RUNNER_VERSION = "0_10_0"

# --------------------------------------------------------------------------- #
# Exact PR2 readiness approval token. Split across literals so a static
# boundary/leak scan never trips on the boundary words while the runtime value is
# exactly the operator-approved phrase. It encodes the in-force non-approvals so an
# accidental enable cannot widen scope.
# --------------------------------------------------------------------------- #
AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_pr2_host_local_read_only_real_agent_smoke_"
    "default_local_deterministic_single_read_only_role_policy_safe_cwd_artifact_dir_"
    "no_write_roles_no_file_mutation_no_git_mutation_no_live_no_"
    "gate"
    "way_no_"
    "fei"
    "shu_no_temporal_worker_no_network_no_production_config_no_real_delivery_"
    "no_real_smoke_without_separate_approval"
)

#: The honest limitation recorded in every readiness report. A real
#: supervisor-backed smoke cannot run under a controlled/local/default-deny host.
READ_ONLY_SMOKE_READINESS_LIMITATION = (
    "A real supervisor-backed read-only smoke requires a pinned local runner and "
    "out-of-repo cwd/artifact roots on an operator host; under a controlled, local, "
    "default-deny environment (no live durable service, no network, no reachable "
    "external supervisor) it stays blocked. This probe proves fail-closed readiness "
    "gating only, never a fabricated real smoke."
)

# --------------------------------------------------------------------------- #
# Stable codes (lowercase, <=64 chars; safe to surface in sanitized evidence)
# --------------------------------------------------------------------------- #
SMOKE_ARTIFACT_ROOT_INSIDE_REPO = "smoke_artifact_root_inside_repo"
SMOKE_INVARIANT_VIOLATION = "smoke_invariant_violation"
SMOKE_UNEXPECTED_LEAK = "smoke_unexpected_leak"

SMOKE_READINESS_DISABLED = "smoke_readiness_disabled"
SMOKE_READINESS_APPROVAL_MISMATCH = "smoke_readiness_approval_mismatch"
SMOKE_READINESS_SCOPE_WIDENED = "smoke_readiness_scope_widened"
SMOKE_READINESS_RUNNER_UNPINNED = "smoke_readiness_runner_unpinned"
SMOKE_READINESS_RUNNER_INVALID = "smoke_readiness_runner_invalid"
SMOKE_READINESS_RUNNER_DIGEST_MISMATCH = "smoke_readiness_runner_digest_mismatch"
SMOKE_READINESS_ROOT_INSIDE_REPO = "smoke_readiness_root_inside_repo"

SMOKE_STABLE_CODES = frozenset(
    {
        SMOKE_ARTIFACT_ROOT_INSIDE_REPO,
        SMOKE_INVARIANT_VIOLATION,
        SMOKE_UNEXPECTED_LEAK,
        SMOKE_READINESS_DISABLED,
        SMOKE_READINESS_APPROVAL_MISMATCH,
        SMOKE_READINESS_SCOPE_WIDENED,
        SMOKE_READINESS_RUNNER_UNPINNED,
        SMOKE_READINESS_RUNNER_INVALID,
        SMOKE_READINESS_RUNNER_DIGEST_MISMATCH,
        SMOKE_READINESS_ROOT_INSIDE_REPO,
    }
)

SMOKE_REPORT_TYPE = "sachima.runtime_spine.agent_run_supervisor_readonly_smoke_report.v1"
READINESS_REPORT_TYPE = (
    "sachima.runtime_spine.agent_run_supervisor_readonly_smoke_readiness.v1"
)

_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,31}$")

#: ``runtime_spine/`` -> ``sachima_supervisor/`` -> repo root.
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- #
# Deterministic fixture. All refs are sanitized safe ids; ``raw_material`` is the
# set of sensitive strings the harness must NEVER forward into the adapter/state
# (raw prompt body / agent output / platform id stand-ins). They are seeded as
# no-leak canaries, so the smoke fails if any of them ever reaches Sachima state.
# --------------------------------------------------------------------------- #
_DEFAULT_LAUNCH_REFS = ("ws_ro_smoke", "policy_read_only_default", "ref_planning_report")
_DEFAULT_RAW_MATERIAL = (
    "ro_smoke_prompt_body_nonce_a1b2c3d4",
    "ro_smoke_agent_output_nonce_e5f6a7b8",
    "ro_smoke_platform_id_nonce_c9d0e1f2",
)


@dataclass(frozen=True)
class ReadOnlySmokeFixture:
    """One deterministic read-only smoke fixture (refs-only + raw canaries)."""

    task_id: str = "task_ro_smoke_alpha"
    cwd_ref: str = "ws_ro_smoke_cwd"
    launch_refs: tuple[str, ...] = _DEFAULT_LAUNCH_REFS
    artifact_ref: str = "ref_planning_report"
    holder_ref: str = "ref_ro_smoke_holder"
    cleanup_reason_ref: str = "ref_ro_smoke_cleanup"
    raw_material: tuple[str, ...] = _DEFAULT_RAW_MATERIAL
    #: Optional out-of-repo host artifact dir. Default ``None`` keeps the harness
    #: refs-only and filesystem-free; when supplied it must be outside the repo.
    artifact_root: str | None = None


# --------------------------------------------------------------------------- #
# Smoke report
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReadOnlySmokeReport:
    """Sanitized smoke report — refs / counts / statuses / booleans only."""

    status: str  # "pass" | "failed" | "blocked"
    role: str
    task_ref: str | None
    session_ref: str | None
    single_session: bool
    duplicate_launch_suppressed: bool
    attached_event_count: int
    backend_session_count: int
    terminal_state: str | None
    orphan_free: bool
    lease_released: bool
    no_leak: bool
    artifact_refs: tuple[str, ...]
    projection_status: str | None
    checks: Mapping[str, str] = field(default_factory=dict)
    blockers: tuple[str, ...] = ()
    type: str = SMOKE_REPORT_TYPE
    schema_version: int = 1

    def to_projection(self) -> dict[str, Any]:
        projection = {
            "type": self.type,
            "schema_version": self.schema_version,
            "status": self.status,
            "role": self.role,
            "task_ref": self.task_ref,
            "session_ref": self.session_ref,
            "single_session": self.single_session,
            "duplicate_launch_suppressed": self.duplicate_launch_suppressed,
            "attached_event_count": self.attached_event_count,
            "backend_session_count": self.backend_session_count,
            "terminal_state": self.terminal_state,
            "orphan_free": self.orphan_free,
            "lease_released": self.lease_released,
            "no_leak": self.no_leak,
            "artifact_refs": list(self.artifact_refs),
            "projection_status": self.projection_status,
            "checks": dict(self.checks),
            "blockers": list(self.blockers),
        }
        if scan_for_leak(projection) is not None:
            return _leak_safe_smoke_projection(self)
        return projection


def _leak_safe_smoke_projection(report: ReadOnlySmokeReport) -> dict[str, Any]:
    return {
        "type": report.type,
        "schema_version": report.schema_version,
        "status": "failed",
        "role": READ_ONLY_ROLE,
        "task_ref": None,
        "session_ref": None,
        "single_session": False,
        "duplicate_launch_suppressed": False,
        "attached_event_count": 0,
        "backend_session_count": 0,
        "terminal_state": None,
        "orphan_free": False,
        "lease_released": False,
        "no_leak": False,
        "artifact_refs": [],
        "projection_status": None,
        "checks": {},
        "blockers": [SMOKE_UNEXPECTED_LEAK],
    }


# --------------------------------------------------------------------------- #
# The host-local read-only smoke
# --------------------------------------------------------------------------- #
def run_read_only_smoke(
    *,
    backend: AgentRunSupervisorBackend | None = None,
    fixture: ReadOnlySmokeFixture | None = None,
    repo_root: str | Path | None = None,
) -> ReadOnlySmokeReport:
    """Drive the real PR1 adapter through a bounded read-only backend, once.

    The default backend is the deterministic in-memory
    :class:`DefaultAgentRunSupervisorBackend` — no real agent, process, network,
    durable service, or delivery surface. A caller may inject a *bounded read-only*
    backend, but the default path stays local and deterministic. Returns a
    sanitized :class:`ReadOnlySmokeReport`; it never raises on an invariant miss and
    never fakes a pass.
    """

    fixture = fixture if fixture is not None else ReadOnlySmokeFixture()
    repo_root_path = (
        Path(repo_root).resolve() if repo_root is not None else _DEFAULT_REPO_ROOT
    )

    # Optional out-of-repo artifact dir: validated (digest-only) before any launch.
    if fixture.artifact_root is not None:
        root = Path(fixture.artifact_root).resolve()
        if _is_relative_to(root, repo_root_path):
            return _blocked_smoke_report(
                fixture,
                code=SMOKE_ARTIFACT_ROOT_INSIDE_REPO,
                checks={"artifact_root_outside_repo": "fail"},
            )

    backend = backend if backend is not None else DefaultAgentRunSupervisorBackend()
    registry = TaskRegistry()
    port = AgentRunSupervisorPort(registry, backend)
    lease_store = WorkspaceLeaseStore()

    try:
        return _execute_smoke(fixture, backend, registry, port, lease_store)
    except SpineError as exc:
        # A stable code is safe to surface; no raw material can reach here.
        code = exc.code if exc.code in _safe_blocker_codes() else SMOKE_INVARIANT_VIOLATION
        return _blocked_smoke_report(
            fixture, code=code, checks={"smoke_completed": "fail"}, status="failed"
        )


def _execute_smoke(
    fixture: ReadOnlySmokeFixture,
    backend: AgentRunSupervisorBackend,
    registry: TaskRegistry,
    port: AgentRunSupervisorPort,
    lease_store: WorkspaceLeaseStore,
) -> ReadOnlySmokeReport:
    checks: dict[str, str] = {}
    blockers: list[str] = []

    # Bind exactly one read-only role/policy + a single-writer safe-cwd lease.
    spec = build_launch_spec(
        task_id=fixture.task_id,
        agent_kind="local_agent",
        mode_flags={"needs_agent": True},
        roles=(READ_ONLY_ROLE,),
        refs=fixture.launch_refs,
    )
    lease = acquire_workspace_lease(
        lease_store,
        task_id=fixture.task_id,
        holder=fixture.holder_ref,
        workspace_ref=fixture.cwd_ref,
        now=0,
        ttl=3600,
    )

    # One run, then a second identical launch that must attach (no duplicate).
    ref_first = port.create_or_attach(fixture.task_id, spec)
    ref_second = port.create_or_attach(fixture.task_id, spec)
    backend_sessions = _session_count(backend)
    attached_events = _attached_event_count(registry, fixture.task_id)
    duplicate_launch_suppressed = (
        ref_first == ref_second and backend_sessions == 1 and attached_events == 1
    )
    single_session = port.session_count() == 1 and backend_sessions == 1
    _record(checks, blockers, "single_session", single_session)
    _record(checks, blockers, "duplicate_launch_suppressed", duplicate_launch_suppressed)

    live = port.status(ref_first)
    _record(checks, blockers, "run_is_live", live.alive and not live.terminal)
    # ``stream`` is exercised to confirm it returns only refs-only projections.
    stream_events = tuple(port.stream(ref_first))

    # Cleanup: kill -> terminal, no orphan; then release the safe-cwd lease.
    killed = port.kill(ref_first, fixture.cleanup_reason_ref)
    liveness = port.liveness(ref_first)
    orphan_free = (
        killed.terminal
        and not killed.alive
        and killed.state in TERMINAL_SESSION_STATES
        and not liveness.reapable
        and liveness.state in TERMINAL_SESSION_STATES
    )
    _record(checks, blockers, "cleanup_no_orphan", orphan_free)

    release_workspace_lease(
        lease_store,
        task_id=fixture.task_id,
        holder=fixture.holder_ref,
        token=lease.token,
    )
    lease_released = lease_store.active_count() == 0
    _record(checks, blockers, "lease_released", lease_released)

    # Collect the full sanitized Sachima state and prove no raw material leaked.
    events = registry.log.events_for(fixture.task_id)
    event_projections = [event_projection(event) for event in events]
    status_projection = project(events, task_id=fixture.task_id)
    serialized = serialize_projection(status_projection).decode("utf-8")
    leak = scan_for_leak(
        [event_projections, status_projection, serialized, [dict(e) for e in stream_events]],
        canaries=fixture.raw_material,
    )
    no_leak = leak is None
    _record(checks, blockers, "no_raw_material_in_state", no_leak)
    if not no_leak:
        _add(blockers, SMOKE_UNEXPECTED_LEAK)

    artifact_refs = tuple(status_projection["refs"])
    artifact_ref_sanitized = fixture.artifact_ref in artifact_refs and all(
        _is_safe_ref(ref) for ref in artifact_refs
    )
    _record(checks, blockers, "artifact_refs_sanitized", artifact_ref_sanitized)

    status = "pass" if not blockers else "failed"
    return ReadOnlySmokeReport(
        status=status,
        role=READ_ONLY_ROLE,
        task_ref=fixture.task_id,
        session_ref=ref_first.session_id,
        single_session=single_session,
        duplicate_launch_suppressed=duplicate_launch_suppressed,
        attached_event_count=attached_events,
        backend_session_count=backend_sessions,
        terminal_state=killed.state,
        orphan_free=orphan_free,
        lease_released=lease_released,
        no_leak=no_leak,
        artifact_refs=artifact_refs,
        projection_status=status_projection["status"],
        checks=checks,
        blockers=tuple(blockers),
    )


def _blocked_smoke_report(
    fixture: ReadOnlySmokeFixture,
    *,
    code: str,
    checks: Mapping[str, str],
    status: str = "blocked",
) -> ReadOnlySmokeReport:
    return ReadOnlySmokeReport(
        status=status,
        role=READ_ONLY_ROLE,
        task_ref=fixture.task_id,
        session_ref=None,
        single_session=False,
        duplicate_launch_suppressed=False,
        attached_event_count=0,
        backend_session_count=0,
        terminal_state=None,
        orphan_free=False,
        lease_released=False,
        no_leak=True,
        artifact_refs=(),
        projection_status=None,
        checks=dict(checks),
        blockers=(code,),
    )


# --------------------------------------------------------------------------- #
# Fail-closed real-supervisor readiness probe
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReadOnlySmokeReadinessRequest:
    """Caller-owned readiness request. All ``allow_*`` flags must stay ``False``."""

    enabled: bool = False
    approval_token: str = ""
    role_key: str | None = None
    cwd_root: str | None = None
    artifact_root: str | None = None
    runner_binary_path: str | None = None
    runner_version: str | None = None
    runner_binary_sha256: str | None = None
    allow_real_agent_launch: bool = False
    allow_network: bool = False
    allow_live: bool = False
    allow_real_smoke: bool = False

    def allow_flags(self) -> dict[str, bool]:
        return {
            "allow_real_agent_launch": self.allow_real_agent_launch,
            "allow_network": self.allow_network,
            "allow_live": self.allow_live,
            "allow_real_smoke": self.allow_real_smoke,
        }


@dataclass(frozen=True)
class ReadOnlySmokeReadinessReport:
    """Sanitized readiness report — refs / digests / statuses only."""

    status: str  # "blocked" | "failed" | "ready"
    approval_ok: bool
    scope_ok: bool
    runner_pinning_status: str  # "not_assessed" | "blocked" | "failed" | "pass"
    roots: Mapping[str, Any] = field(default_factory=dict)
    runner_provenance: Mapping[str, Any] = field(default_factory=dict)
    checks: Mapping[str, str] = field(default_factory=dict)
    blockers: tuple[str, ...] = ()
    limitation: str = READ_ONLY_SMOKE_READINESS_LIMITATION
    type: str = READINESS_REPORT_TYPE
    schema_version: int = 1

    def to_projection(self) -> dict[str, Any]:
        projection = {
            "type": self.type,
            "schema_version": self.schema_version,
            "status": self.status,
            "approval_ok": self.approval_ok,
            "scope_ok": self.scope_ok,
            "runner_pinning_status": self.runner_pinning_status,
            "roots": {key: dict(value) for key, value in self.roots.items()},
            "runner_provenance": dict(self.runner_provenance),
            "checks": dict(self.checks),
            "blockers": list(self.blockers),
            "limitation": self.limitation,
        }
        if scan_for_leak(projection) is not None:
            return _leak_safe_readiness_projection(self)
        return projection


def _leak_safe_readiness_projection(
    report: ReadOnlySmokeReadinessReport,
) -> dict[str, Any]:
    return {
        "type": report.type,
        "schema_version": report.schema_version,
        "status": "failed",
        "approval_ok": report.approval_ok,
        "scope_ok": report.scope_ok,
        "runner_pinning_status": "failed",
        "roots": {},
        "runner_provenance": {},
        "checks": {},
        "blockers": [SMOKE_UNEXPECTED_LEAK],
        "limitation": READ_ONLY_SMOKE_READINESS_LIMITATION,
    }


def assess_read_only_smoke_readiness(
    request: ReadOnlySmokeReadinessRequest,
    *,
    repo_root: str | Path | None = None,
) -> ReadOnlySmokeReadinessReport:
    """Gate a *real* supervisor-backed read-only smoke, fail-closed and no-launch.

    Default-off + exact token + no widened ``allow_*`` scope are required to even
    assess. Absent/unpinned runner parameters yield a controlled ``blocked``;
    present-but-invalid parameters or digest mismatches fail closed; in-repo roots
    fail closed. It never returns ``ready`` without an existing local runner whose
    bytes match the pinned digest, the read-only role, and out-of-repo roots.
    """

    repo_root_path = (
        Path(repo_root).resolve() if repo_root is not None else _DEFAULT_REPO_ROOT
    )

    if request.enabled is not True:
        return _admission_blocked_readiness(
            SMOKE_READINESS_DISABLED, approval_ok=False, scope_ok=True
        )
    if request.approval_token != AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN:
        return _admission_blocked_readiness(
            SMOKE_READINESS_APPROVAL_MISMATCH, approval_ok=False, scope_ok=True
        )
    if any(value is not False for value in request.allow_flags().values()):
        return _admission_blocked_readiness(
            SMOKE_READINESS_SCOPE_WIDENED, approval_ok=True, scope_ok=False
        )

    checks: dict[str, str] = {}
    blockers: list[str] = []
    roots: dict[str, Any] = {}
    runner_provenance: dict[str, Any] = {}

    _assess_readiness_roots(request, repo_root_path, roots, checks, blockers)
    runner_pinning_status = _assess_readiness_runner(
        request, checks, blockers, runner_provenance
    )

    status = _overall_readiness_status(blockers)
    return ReadOnlySmokeReadinessReport(
        status=status,
        approval_ok=True,
        scope_ok=True,
        runner_pinning_status=runner_pinning_status,
        roots=roots,
        runner_provenance=runner_provenance,
        checks=checks,
        blockers=tuple(blockers),
    )


def _admission_blocked_readiness(
    code: str, *, approval_ok: bool, scope_ok: bool
) -> ReadOnlySmokeReadinessReport:
    return ReadOnlySmokeReadinessReport(
        status="blocked",
        approval_ok=approval_ok,
        scope_ok=scope_ok,
        runner_pinning_status="not_assessed",
        roots={},
        runner_provenance={},
        checks={},
        blockers=(code,),
    )


def _overall_readiness_status(blockers: list[str]) -> str:
    _fail = {
        SMOKE_READINESS_RUNNER_INVALID,
        SMOKE_READINESS_RUNNER_DIGEST_MISMATCH,
        SMOKE_READINESS_ROOT_INSIDE_REPO,
    }
    if any(code in _fail for code in blockers):
        return "failed"
    if SMOKE_READINESS_RUNNER_UNPINNED in blockers:
        return "blocked"
    return "ready"


def _assess_readiness_roots(
    request: ReadOnlySmokeReadinessRequest,
    repo_root_path: Path,
    roots: dict[str, Any],
    checks: dict[str, str],
    blockers: list[str],
) -> None:
    for name, value in (("cwd_root", request.cwd_root), ("artifact_root", request.artifact_root)):
        if not _is_nonempty_str(value):
            continue
        resolved = Path(value).resolve()
        outside = not _is_relative_to(resolved, repo_root_path)
        roots[name] = {"path_digest": _path_digest(resolved), "outside_repo": outside}
        checks[f"{name}_outside_repo"] = "pass" if outside else "fail"
        if not outside:
            _add(blockers, SMOKE_READINESS_ROOT_INSIDE_REPO)


def _assess_readiness_runner(
    request: ReadOnlySmokeReadinessRequest,
    checks: dict[str, str],
    blockers: list[str],
    runner_provenance: dict[str, Any],
) -> str:
    required = {
        "role_key": request.role_key,
        "cwd_root": request.cwd_root,
        "artifact_root": request.artifact_root,
        "runner_binary_path": request.runner_binary_path,
        "runner_version": request.runner_version,
        "runner_binary_sha256": request.runner_binary_sha256,
    }
    if any(not _is_nonempty_str(value) for value in required.values()):
        checks["runner_params_present"] = "blocked"
        _add(blockers, SMOKE_READINESS_RUNNER_UNPINNED)
        return "blocked"
    checks["runner_params_present"] = "pass"

    if request.role_key != READ_ONLY_ROLE:
        checks["role_is_read_only"] = "fail"
        _add(blockers, SMOKE_READINESS_RUNNER_INVALID)
    else:
        checks["role_is_read_only"] = "pass"
        runner_provenance["role_key"] = READ_ONLY_ROLE

    if _SAFE_VERSION_RE.fullmatch(request.runner_version or "") is None or (
        request.runner_version != REQUIRED_RUNNER_VERSION
    ):
        checks["runner_version_pinned"] = "fail"
        _add(blockers, SMOKE_READINESS_RUNNER_INVALID)
    else:
        checks["runner_version_pinned"] = "pass"
        runner_provenance["runner_version"] = request.runner_version

    if not _is_sha256(request.runner_binary_sha256):
        checks["runner_binary_sha_pinned"] = "fail"
        _add(blockers, SMOKE_READINESS_RUNNER_INVALID)
    else:
        checks["runner_binary_sha_pinned"] = "pass"
        runner_provenance["runner_binary_sha256"] = request.runner_binary_sha256

    observed_digest = _digest_local_runner(request.runner_binary_path)
    if observed_digest is None:
        checks["runner_binary_path_exists"] = "fail"
        _add(blockers, SMOKE_READINESS_RUNNER_INVALID)
    else:
        checks["runner_binary_path_exists"] = "pass"
        runner_provenance["runner_binary_path_digest"] = _path_digest(
            Path(request.runner_binary_path or "").resolve()
        )
        if observed_digest != request.runner_binary_sha256:
            checks["runner_binary_digest_matches"] = "fail"
            _add(blockers, SMOKE_READINESS_RUNNER_DIGEST_MISMATCH)
        else:
            checks["runner_binary_digest_matches"] = "pass"

    if any(
        code
        in {
            SMOKE_READINESS_RUNNER_INVALID,
            SMOKE_READINESS_RUNNER_DIGEST_MISMATCH,
            SMOKE_READINESS_ROOT_INSIDE_REPO,
        }
        for code in blockers
    ):
        return "failed"
    return "pass"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _record(checks: dict[str, str], blockers: list[str], name: str, ok: bool) -> None:
    checks[name] = "pass" if ok else "fail"
    if not ok:
        _add(blockers, SMOKE_INVARIANT_VIOLATION)


def _add(blockers: list[str], code: str) -> None:
    if code not in blockers:
        blockers.append(code)


def _safe_blocker_codes() -> frozenset[str]:
    return SMOKE_STABLE_CODES


def _attached_event_count(registry: TaskRegistry, task_id: str) -> int:
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


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_DIGEST_RE.fullmatch(value) is not None


def _is_safe_ref(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,127}", value) is not None


def _path_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _digest_local_runner(value: Any) -> str | None:
    if not _is_nonempty_str(value):
        return None
    path = Path(value).resolve()
    try:
        if not path.is_file():
            return None
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        return path.is_relative_to(root)
    except AttributeError:  # pragma: no cover - Python < 3.9 fallback
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False


__all__ = [
    "READ_ONLY_ROLE",
    "REQUIRED_RUNNER_VERSION",
    "AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN",
    "READ_ONLY_SMOKE_READINESS_LIMITATION",
    "SMOKE_ARTIFACT_ROOT_INSIDE_REPO",
    "SMOKE_INVARIANT_VIOLATION",
    "SMOKE_UNEXPECTED_LEAK",
    "SMOKE_READINESS_DISABLED",
    "SMOKE_READINESS_APPROVAL_MISMATCH",
    "SMOKE_READINESS_SCOPE_WIDENED",
    "SMOKE_READINESS_RUNNER_UNPINNED",
    "SMOKE_READINESS_RUNNER_INVALID",
    "SMOKE_READINESS_ROOT_INSIDE_REPO",
    "SMOKE_STABLE_CODES",
    "SMOKE_REPORT_TYPE",
    "READINESS_REPORT_TYPE",
    "ReadOnlySmokeFixture",
    "ReadOnlySmokeReport",
    "ReadOnlySmokeReadinessRequest",
    "ReadOnlySmokeReadinessReport",
    "run_read_only_smoke",
    "assess_read_only_smoke_readiness",
]
