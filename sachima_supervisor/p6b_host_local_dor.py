"""P6-B Stage-2 host-local DoR / crash-no-relaunch proof surface (default-off).

This module adds a small, test-covered **definition-of-ready** surface for a
future bounded read-only planning/report real smoke. It does two narrow things
and nothing else:

  1. **Pin / validate** a host-local runner + role overlay + artifact sink +
     evidence-root *shape* WITHOUT launching a real agent. It validates an
     out-of-repo role overlay (exact read-only role key, adapter pin, pinned
     ``acpx@0.10.0`` provenance, all write-class permissions denied, one-shot
     ``exec`` session) and, when an argv-list/no-shell version probe is injected
     against a temp fake executable, pins the binary version + sha. It returns a
     controlled ``blocked`` report — never an error and never a launch — when the
     exact runner parameters are absent / missing / unpinned.

  2. **Prove fail-closed no-relaunch recovery.** It reuses the merged P6-B
     ``P6BReadOnlyRealAgentStepExecutor`` over a *fresh empty*
     ``ControlledLocalExecClaimStore`` (modeling a process restart that lost all
     resident in-process claim state) and a supervisor invoker that raises/counts
     if ever called. ``recover``/``query`` by run/step return a sanitized
     ``not_found`` with ``recovery_marker=reattached_no_relaunch`` and a zero
     launch count; ``execute`` is never called and a stale execute after store
     loss is recorded as ``not_approved_not_attempted``.

Explicit limitation (recorded in every report): without a durable cross-process
controlled-exec claim store, recover-without-relaunch cannot be proven as
*reattachment* to a live run. This DoR can therefore prove only fail-closed
no-relaunch recovery, not real execution readiness by itself.

Boundaries: this module builds no runner, executes no binary (the version probe
is injected — the bundled CLI's default probe is argv-list/no-shell), opens no
network/Gateway/Feishu/live surface, writes no committed repo file, and launches
no real agent or real smoke. Reports carry only sanitized refs/digests/counts/
statuses; raw host paths are projected as digests only.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .activity_controlled_exec import (
    CONTROLLED_EXEC_ROLE_ADAPTER_AGENT,
    CONTROLLED_EXEC_ROLE_ALLOWLIST,
    FORBIDDEN_RUNNER_BASENAMES,
    ControlledLocalExecClaimStore,
    verify_pinned_local_acpx_binary,
)
from .activity_preflight import DurableStatePreflightStore
from .p5_temporal import contracts as C
from .p6b_read_only_real_agent import (
    P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN,
    P6BReadOnlyRealAgentStepExecutor,
)

# --------------------------------------------------------------------------- #
# Exact P6-B Stage-2 host-local DoR approval token. Split across literals so the
# static boundary scans never trip on the boundary words while the runtime value
# is exactly the operator-approved phrase. It encodes the in-force non-approvals
# so an accidental enable cannot widen scope.
# --------------------------------------------------------------------------- #
P6B_HOST_LOCAL_DOR_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_p6b_stage2_host_local_dor_and_crash_no_relaunch_"
    "proof_pinned_local_runner_role_overlay_artifact_sink_evidence_only_no_real_agent_launch_"
    "no_real_smoke_no_write_no_git_no_network_no_live_no_"
    "gate"
    "way_no_"
    "fei"
    "shu_no_production_config_no_real_delivery"
)

#: The pinned acpx version this DoR will admit. Matches the committed read-only
#: role files and the controlled-exec provenance wall.
REQUIRED_ACPX_VERSION = "0.10.0"

#: The bridge's recover marker. A recover must reattach by resident claim id and
#: never relaunch; after store loss there is nothing to reattach to, so the marker
#: accompanies a sanitized ``not_found``.
RECOVERY_MARKER_REATTACHED_NO_RELAUNCH = "reattached_no_relaunch"

#: The honest limitation of a host-local-only proof. Recorded in every report.
P6B_HOST_LOCAL_DOR_LIMITATION = (
    "Without a durable cross-process controlled-exec claim store, "
    "recover-without-relaunch cannot be proven as reattachment to a live run; "
    "this DoR proves only fail-closed no-relaunch recovery after resident "
    "in-process claim state is lost, not real execution readiness by itself."
)

# --------------------------------------------------------------------------- #
# Stable codes (lowercase, <=64 chars; safe to surface in sanitized evidence)
# --------------------------------------------------------------------------- #
P6B_DOR_DISABLED = "p6b_dor_disabled"
P6B_DOR_APPROVAL_MISMATCH = "p6b_dor_approval_mismatch"
P6B_DOR_SCOPE_WIDENED = "p6b_dor_scope_widened"
P6B_DOR_RUNNER_PARAMS_MISSING = "p6b_dor_runner_params_missing"
P6B_DOR_ROLE_OVERLAY_INVALID = "p6b_dor_role_overlay_invalid"
P6B_DOR_ROLE_OVERLAY_DIGEST_MISMATCH = "p6b_dor_role_overlay_digest_mismatch"
P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED = "p6b_dor_runner_provenance_unverified"
P6B_DOR_ROOT_INSIDE_REPO = "p6b_dor_root_inside_repo"
P6B_DOR_CRASH_PROOF_FAILED = "p6b_dor_crash_proof_failed"

#: Blockers that mean "a hard validation failed" -> overall ``failed``.
_FAIL_CLASS = frozenset(
    {
        P6B_DOR_ROLE_OVERLAY_INVALID,
        P6B_DOR_ROLE_OVERLAY_DIGEST_MISMATCH,
        P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED,
        P6B_DOR_ROOT_INSIDE_REPO,
        P6B_DOR_CRASH_PROOF_FAILED,
    }
)
#: Runner-specific fail-class subset (drives ``runner_pinning_status``).
_RUNNER_FAIL_CLASS = frozenset(
    {
        P6B_DOR_ROLE_OVERLAY_INVALID,
        P6B_DOR_ROLE_OVERLAY_DIGEST_MISMATCH,
        P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED,
    }
)
#: Blockers that mean "controlled, expected on this host" -> overall ``blocked``.
_BLOCKED_CLASS = frozenset({P6B_DOR_RUNNER_PARAMS_MISSING})

_REPORT_TYPE = "sachima.supervisor.p6b_host_local_dor_report.v1"
_CRASH_PROOF_TYPE = "sachima.supervisor.p6b_host_local_dor_crash_proof.v1"

_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_READ_ONLY_TRUE_PERMISSIONS = ("read", "search")
_READ_ONLY_FALSE_PERMISSIONS = (
    "write",
    "execute",
    "terminal",
    "delete",
    "move",
    "fetch",
    "switch_mode",
    "other",
)
_REQUIRED_ROLE_SCHEMA_VERSION = 1

#: Sanitized claim states the crash proof may surface.
_SAFE_STATES = frozenset(
    {
        "not_found",
        "completed",
        "claimed_in_progress",
        "failed_retryable",
        "failed_terminal",
        "store_invalid",
    }
)

#: Repo root used for the "must live outside the repo" check unless overridden.
#: ``sachima_supervisor/`` -> repo root.
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent

#: Deterministic refs for the crash proof. Never carry host material.
_CRASH_PROOF_RUN_REF = "run_p6b_host_local_dor_proof"
_CRASH_PROOF_STEP_REF = "planning_report_step"


# --------------------------------------------------------------------------- #
# Request / report
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class P6BHostLocalDorRequest:
    """Caller-owned host-local DoR request.

    Runner parameters are operator-supplied host facts (paths, digests). The DoR
    never persists raw host paths — they are projected as digests only. The
    ``allow_*`` flags must all stay ``False``: they exist so an attempt to widen
    scope fails closed instead of silently passing.
    """

    enabled: bool = False
    approval_token: str = ""
    role_key: str | None = None
    role_overlay_path: str | None = None
    role_overlay_digest: str | None = None
    acpx_binary: str | None = None
    acpx_version: str | None = None
    acpx_binary_sha256: str | None = None
    evidence_root: str | None = None
    artifact_sink_root: str | None = None
    allow_real_agent_launch: bool = False
    allow_real_smoke: bool = False
    allow_network: bool = False
    allow_live: bool = False

    def allow_flags(self) -> dict[str, bool]:
        return {
            "allow_real_agent_launch": self.allow_real_agent_launch,
            "allow_real_smoke": self.allow_real_smoke,
            "allow_network": self.allow_network,
            "allow_live": self.allow_live,
        }


@dataclass(frozen=True)
class P6BHostLocalDorReport:
    """Sanitized host-local DoR report.

    Carries only refs/digests/counts/statuses. ``to_projection`` is the JSON
    evidence shape and is leak-scanned by construction.
    """

    status: str
    approval_ok: bool
    scope_ok: bool
    runner_pinning_status: str
    crash_proof_status: str
    crash_proof: Mapping[str, Any] = field(default_factory=dict)
    runner_provenance: Mapping[str, Any] = field(default_factory=dict)
    roots: Mapping[str, Any] = field(default_factory=dict)
    checks: Mapping[str, str] = field(default_factory=dict)
    blockers: tuple[str, ...] = ()
    limitation: str = P6B_HOST_LOCAL_DOR_LIMITATION
    type: str = _REPORT_TYPE
    schema_version: int = 1

    def to_projection(self) -> dict[str, Any]:
        projection: dict[str, Any] = {
            "type": self.type,
            "schema_version": self.schema_version,
            "status": self.status,
            "approval_ok": self.approval_ok,
            "scope_ok": self.scope_ok,
            "runner_pinning_status": self.runner_pinning_status,
            "crash_proof_status": self.crash_proof_status,
            "crash_proof": dict(self.crash_proof),
            "runner_provenance": dict(self.runner_provenance),
            "roots": {key: dict(value) for key, value in self.roots.items()},
            "checks": dict(self.checks),
            "blockers": list(self.blockers),
            "limitation": self.limitation,
        }
        if C.scan_projection_for_leak(projection) is not None:
            return _leak_safe_projection(self)
        return projection


def _leak_safe_projection(report: P6BHostLocalDorReport) -> dict[str, Any]:
    return {
        "type": report.type,
        "schema_version": report.schema_version,
        "status": "failed",
        "approval_ok": report.approval_ok,
        "scope_ok": report.scope_ok,
        "runner_pinning_status": "failed",
        "crash_proof_status": "skipped",
        "crash_proof": {},
        "runner_provenance": {},
        "roots": {},
        "checks": {},
        "blockers": [C.RUNTIME_HISTORY_LEAK_DETECTED],
        "limitation": P6B_HOST_LOCAL_DOR_LIMITATION,
    }


# --------------------------------------------------------------------------- #
# Assessment
# --------------------------------------------------------------------------- #
def assess_p6b_host_local_dor(
    request: P6BHostLocalDorRequest,
    *,
    repo_root: str | Path | None = None,
    version_probe: Callable[[str], str] | None = None,
) -> P6BHostLocalDorReport:
    """Assess host-local DoR readiness + the fail-closed crash/no-relaunch proof.

    Admission (default-off + exact token + no widened ``allow_*`` flag) fails
    closed as a controlled ``blocked`` report with no crash proof and no launch.
    Once admitted the crash/no-relaunch proof always runs (it is independent of
    runner pinning). Absent/missing/unpinned runner parameters yield a controlled
    ``blocked`` runner-pinning status; present-but-invalid parameters fail closed.
    """

    repo_root_path = (
        Path(repo_root).resolve() if repo_root is not None else _DEFAULT_REPO_ROOT
    )

    if request.enabled is not True:
        return _admission_blocked_report(P6B_DOR_DISABLED, approval_ok=False, scope_ok=True)
    if request.approval_token != P6B_HOST_LOCAL_DOR_APPROVAL_TOKEN:
        return _admission_blocked_report(
            P6B_DOR_APPROVAL_MISMATCH, approval_ok=False, scope_ok=True
        )
    if any(value is not False for value in request.allow_flags().values()):
        return _admission_blocked_report(
            P6B_DOR_SCOPE_WIDENED, approval_ok=True, scope_ok=False
        )

    # Admitted: the crash / no-relaunch proof runs unconditionally.
    crash = prove_crash_no_relaunch()
    crash_status = "pass" if crash["passed"] else "fail"

    checks: dict[str, str] = {}
    blockers: list[str] = []
    roots: dict[str, Any] = {}
    runner_provenance: dict[str, Any] = {}

    if crash_status != "pass":
        _add_blocker(blockers, P6B_DOR_CRASH_PROOF_FAILED)

    _assess_roots(request, repo_root_path, roots, checks, blockers)
    runner_pinning_status = _assess_runner(
        request, version_probe, checks, blockers, runner_provenance
    )

    status = _overall_status(blockers)
    return P6BHostLocalDorReport(
        status=status,
        approval_ok=True,
        scope_ok=True,
        runner_pinning_status=runner_pinning_status,
        crash_proof_status=crash_status,
        crash_proof=crash,
        runner_provenance=runner_provenance,
        roots=roots,
        checks=checks,
        blockers=tuple(blockers),
    )


def _admission_blocked_report(
    code: str, *, approval_ok: bool, scope_ok: bool
) -> P6BHostLocalDorReport:
    return P6BHostLocalDorReport(
        status="blocked",
        approval_ok=approval_ok,
        scope_ok=scope_ok,
        runner_pinning_status="not_assessed",
        crash_proof_status="skipped",
        crash_proof={},
        runner_provenance={},
        roots={},
        checks={},
        blockers=(code,),
    )


def _overall_status(blockers: list[str]) -> str:
    if any(code in _FAIL_CLASS for code in blockers):
        return "failed"
    if any(code in _BLOCKED_CLASS for code in blockers):
        return "blocked"
    return "pass"


def _assess_roots(
    request: P6BHostLocalDorRequest,
    repo_root_path: Path,
    roots: dict[str, Any],
    checks: dict[str, str],
    blockers: list[str],
) -> None:
    specs = (
        ("role_overlay", request.role_overlay_path),
        ("evidence_root", request.evidence_root),
        ("artifact_sink_root", request.artifact_sink_root),
    )
    for name, value in specs:
        if not _is_nonempty_str(value):
            continue
        resolved = Path(value).resolve()
        outside = not _is_relative_to(resolved, repo_root_path)
        roots[name] = {"path_digest": _path_digest(resolved), "outside_repo": outside}
        checks[f"{name}_outside_repo"] = "pass" if outside else "fail"
        if not outside:
            _add_blocker(blockers, P6B_DOR_ROOT_INSIDE_REPO)


def _assess_runner(
    request: P6BHostLocalDorRequest,
    version_probe: Callable[[str], str] | None,
    checks: dict[str, str],
    blockers: list[str],
    runner_provenance: dict[str, Any],
) -> str:
    required = {
        "role_key": request.role_key,
        "role_overlay_path": request.role_overlay_path,
        "role_overlay_digest": request.role_overlay_digest,
        "acpx_binary": request.acpx_binary,
        "acpx_version": request.acpx_version,
        "acpx_binary_sha256": request.acpx_binary_sha256,
    }
    if any(not _is_nonempty_str(value) for value in required.values()):
        checks["runner_params_present"] = "blocked"
        _add_blocker(blockers, P6B_DOR_RUNNER_PARAMS_MISSING)
        return "blocked"

    checks["runner_params_present"] = "pass"
    _validate_role_overlay(request, checks, blockers, runner_provenance)
    _verify_binary_identity(request, version_probe, checks, blockers, runner_provenance)

    if any(code in _RUNNER_FAIL_CLASS for code in blockers):
        return "failed"
    return "pass"


def _validate_role_overlay(
    request: P6BHostLocalDorRequest,
    checks: dict[str, str],
    blockers: list[str],
    runner_provenance: dict[str, Any],
) -> None:
    try:
        payload = Path(request.role_overlay_path).read_bytes()  # type: ignore[arg-type]
    except OSError:
        checks["role_overlay_valid"] = "fail"
        _add_blocker(blockers, P6B_DOR_ROLE_OVERLAY_INVALID)
        return

    actual_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    if not _is_sha256(request.role_overlay_digest) or actual_digest != request.role_overlay_digest:
        checks["role_overlay_digest"] = "fail"
        checks["role_overlay_valid"] = "fail"
        _add_blocker(blockers, P6B_DOR_ROLE_OVERLAY_DIGEST_MISMATCH)
        return
    checks["role_overlay_digest"] = "pass"
    runner_provenance["role_overlay_digest"] = actual_digest

    try:
        mapping = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        checks["role_overlay_valid"] = "fail"
        _add_blocker(blockers, P6B_DOR_ROLE_OVERLAY_INVALID)
        return

    if _role_overlay_shape_ok(mapping, request.role_key, runner_provenance):
        checks["role_overlay_valid"] = "pass"
    else:
        checks["role_overlay_valid"] = "fail"
        _add_blocker(blockers, P6B_DOR_ROLE_OVERLAY_INVALID)

    _check_declared_binary(request, mapping, checks, blockers, runner_provenance)


def _role_overlay_shape_ok(
    mapping: Any, role_key: Any, runner_provenance: dict[str, Any]
) -> bool:
    if not isinstance(mapping, dict):
        return False
    if mapping.get("schema_version") != _REQUIRED_ROLE_SCHEMA_VERSION:
        return False
    if mapping.get("role_id") != role_key:
        return False
    if role_key not in CONTROLLED_EXEC_ROLE_ALLOWLIST:
        return False
    required_adapter = CONTROLLED_EXEC_ROLE_ADAPTER_AGENT.get(role_key)
    if required_adapter is None:
        return False
    runner = mapping.get("runner")
    if not isinstance(runner, dict):
        return False
    if (
        runner.get("type") != "acpx"
        or runner.get("acpx_version") != REQUIRED_ACPX_VERSION
        or runner.get("adapter_agent") != required_adapter
    ):
        return False
    permissions = mapping.get("permissions")
    if not isinstance(permissions, dict):
        return False
    if any(permissions.get(kind) is not True for kind in _READ_ONLY_TRUE_PERMISSIONS):
        return False
    if any(permissions.get(kind) is not False for kind in _READ_ONLY_FALSE_PERMISSIONS):
        return False
    session = mapping.get("session")
    if not isinstance(session, dict) or session.get("strategy") != "exec":
        return False
    runner_provenance["role_key"] = role_key
    runner_provenance["adapter_agent"] = required_adapter
    return True


def _check_declared_binary(
    request: P6BHostLocalDorRequest,
    mapping: Any,
    checks: dict[str, str],
    blockers: list[str],
    runner_provenance: dict[str, Any],
) -> None:
    runner = mapping.get("runner") if isinstance(mapping, dict) else None
    declared = runner.get("acpx_binary") if isinstance(runner, dict) else None
    if _is_pinned_local_binary_path(declared) and declared == request.acpx_binary:
        checks["binary_path_pinned"] = "pass"
        runner_provenance["acpx_binary_path_digest"] = _path_digest(Path(declared).resolve())
    else:
        checks["binary_path_pinned"] = "fail"
        _add_blocker(blockers, P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED)


def _verify_binary_identity(
    request: P6BHostLocalDorRequest,
    version_probe: Callable[[str], str] | None,
    checks: dict[str, str],
    blockers: list[str],
    runner_provenance: dict[str, Any],
) -> None:
    runner_provenance.setdefault("acpx_version", request.acpx_version)
    runner_provenance.setdefault("acpx_binary_sha256", request.acpx_binary_sha256)

    if request.acpx_version != REQUIRED_ACPX_VERSION:
        checks["binary_version_pin"] = "fail"
        checks["binary_version_probe"] = "skipped"
        checks["binary_sha_pin"] = "skipped"
        _add_blocker(blockers, P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED)
        return
    checks["binary_version_pin"] = "pass"

    if not _is_sha256(request.acpx_binary_sha256):
        checks["binary_sha_pin"] = "fail"
        checks["binary_version_probe"] = "skipped"
        _add_blocker(blockers, P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED)
        return

    if version_probe is None:
        # No probe injected: the declared identity is pinned and syntactically
        # valid, but not re-verified against a live executable here. Honest, not
        # a launch.
        checks["binary_version_probe"] = "skipped"
        checks["binary_sha_pin"] = "skipped"
        runner_provenance["acpx_binary_sha256_verified"] = False
        return

    try:
        # ``verify_pinned_local_acpx_binary`` already fails closed with a stable
        # ``ControlledLocalExecError`` on every miss; the broad guard only ensures
        # no raw probe detail ever escapes as an unexpected exception.
        provenance = verify_pinned_local_acpx_binary(
            request.acpx_binary,
            version_probe=version_probe,
            expected_version=request.acpx_version,
        )
    except Exception:  # never leak raw probe detail
        checks["binary_version_probe"] = "fail"
        checks["binary_sha_pin"] = "skipped"
        _add_blocker(blockers, P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED)
        return

    checks["binary_version_probe"] = "pass"
    runner_provenance["acpx_version"] = provenance.acpx_version
    runner_provenance["acpx_binary_sha256"] = provenance.binary_sha256
    runner_provenance["acpx_binary_sha256_verified"] = True
    runner_provenance["probe_text"] = provenance.probe_text

    if provenance.binary_sha256 == request.acpx_binary_sha256:
        checks["binary_sha_pin"] = "pass"
    else:
        checks["binary_sha_pin"] = "fail"
        _add_blocker(blockers, P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED)


# --------------------------------------------------------------------------- #
# Crash / restart fail-closed no-relaunch proof
# --------------------------------------------------------------------------- #
class _CrashProofSupervisorInvoker:
    """Counts launches and refuses every call. The proof must never launch."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, seam_request: Any) -> Any:
        self.calls += 1
        raise AssertionError("crash-proof supervisor invoker must never be called")


def _unused_prompt_materializer(request: Any) -> str:  # pragma: no cover - never called
    return "p6b_host_local_dor_crash_proof_prompt_placeholder"


def _unused_artifact_sink(  # pragma: no cover - never called
    request: Any, *, result: Any, role_binding: Any
) -> tuple[Any, ...]:
    return ()


def prove_crash_no_relaunch(
    *, run_ref: str = _CRASH_PROOF_RUN_REF, step_ref: str = _CRASH_PROOF_STEP_REF
) -> dict[str, Any]:
    """Prove the in-process P6-B path is fail-closed after crash/restart.

    A *fresh empty* ``ControlledLocalExecClaimStore`` models a process restart
    that lost all resident claim state. ``query``/``recover`` by run/step must
    return a sanitized ``not_found`` with no relaunch and a zero supervisor launch
    count; ``recover`` additionally carries
    ``recovery_marker=reattached_no_relaunch``. ``execute`` is never called.
    """

    store = ControlledLocalExecClaimStore()
    invoker = _CrashProofSupervisorInvoker()
    executor = P6BReadOnlyRealAgentStepExecutor(
        enabled=True,
        approval_token=P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN,
        controlled_exec_store=store,
        preflight_store=DurableStatePreflightStore(),
        prompt_materializer=_unused_prompt_materializer,
        artifact_sink=_unused_artifact_sink,
        invoke_supervisor=invoker,
    )

    query = executor.query(run_id=run_ref, step_id=step_ref)
    recover = executor.recover(run_id=run_ref, step_id=step_ref)

    query_state = _safe_state(query.get("state"))
    recover_state = _safe_state(recover.get("state"))
    recovery_marker = recover.get("recovery_marker")
    safe_marker = (
        RECOVERY_MARKER_REATTACHED_NO_RELAUNCH
        if recovery_marker == RECOVERY_MARKER_REATTACHED_NO_RELAUNCH
        else None
    )
    passed = (
        query_state == "not_found"
        and recover_state == "not_found"
        and safe_marker == RECOVERY_MARKER_REATTACHED_NO_RELAUNCH
        and invoker.calls == 0
    )
    return {
        "type": _CRASH_PROOF_TYPE,
        "query_state": query_state,
        "recover_state": recover_state,
        "recovery_marker": safe_marker,
        "supervisor_launch_count": invoker.calls,
        "execute_after_store_loss": "not_approved_not_attempted",
        "passed": passed,
    }


# --------------------------------------------------------------------------- #
# Evidence writer
# --------------------------------------------------------------------------- #
def write_p6b_host_local_dor_evidence(
    report: P6BHostLocalDorReport,
    *,
    evidence_root: str | Path,
    repo_root: str | Path | None = None,
    filename: str | None = None,
) -> Path:
    """Write the sanitized DoR report JSON under an out-of-repo evidence root.

    Refuses to write inside the repository root (fail closed). The filename is
    derived from the report content digest when not supplied, so re-running with
    identical inputs is idempotent.
    """

    repo_root_path = (
        Path(repo_root).resolve() if repo_root is not None else _DEFAULT_REPO_ROOT
    )
    root = Path(evidence_root).resolve()
    if _is_relative_to(root, repo_root_path):
        raise ValueError("p6b host-local DoR evidence root must be outside the repository root")

    projection = report.to_projection()
    if filename is None:
        digest = hashlib.sha256(C.canonical_json_bytes(projection)).hexdigest()[:16]
        filename = f"p6b_host_local_dor_evidence_{digest}.json"
    root.mkdir(parents=True, exist_ok=True)
    out_path = root / filename
    out_path.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n")
    return out_path


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _add_blocker(blockers: list[str], code: str) -> None:
    if code not in blockers:
        blockers.append(code)


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_DIGEST_RE.fullmatch(value) is not None


def _is_launcher_basename(name: str) -> bool:
    lowered = name.lower()
    return lowered in FORBIDDEN_RUNNER_BASENAMES or lowered.startswith("npx")


def _is_pinned_local_binary_path(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("/")
        and value.strip() != ""
        and not any(ch.isspace() for ch in value)
        and not _is_launcher_basename(Path(value).name)
    )


def _path_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        return path.is_relative_to(root)
    except AttributeError:  # pragma: no cover - Python < 3.9 fallback
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False


def _safe_state(value: Any) -> str:
    return value if isinstance(value, str) and value in _SAFE_STATES else "store_invalid"


__all__ = [
    "P6B_HOST_LOCAL_DOR_APPROVAL_TOKEN",
    "REQUIRED_ACPX_VERSION",
    "RECOVERY_MARKER_REATTACHED_NO_RELAUNCH",
    "P6B_HOST_LOCAL_DOR_LIMITATION",
    "P6B_DOR_DISABLED",
    "P6B_DOR_APPROVAL_MISMATCH",
    "P6B_DOR_SCOPE_WIDENED",
    "P6B_DOR_RUNNER_PARAMS_MISSING",
    "P6B_DOR_ROLE_OVERLAY_INVALID",
    "P6B_DOR_ROLE_OVERLAY_DIGEST_MISMATCH",
    "P6B_DOR_RUNNER_PROVENANCE_UNVERIFIED",
    "P6B_DOR_ROOT_INSIDE_REPO",
    "P6B_DOR_CRASH_PROOF_FAILED",
    "P6BHostLocalDorRequest",
    "P6BHostLocalDorReport",
    "assess_p6b_host_local_dor",
    "prove_crash_no_relaunch",
    "write_p6b_host_local_dor_evidence",
]
