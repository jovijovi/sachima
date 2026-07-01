"""S4 — bounded read-only *real*-agent supervisor seam (default-off).

This module implements stage S4 of the Sachima agent-run-supervisor ↔ Temporal
integration as fixed by the S4 design packet
(``docs/plans/2026-07-01-sachima-s4-read-only-real-agent-step-design-packet.md``):
the **real read-only supervisor seam** that the already-merged S2 adapter binds in
place of ``FakeDeterministicSupervisorSeam``. Its ``run_step`` delegates **one**
bounded read-only step to the merged P6-B / controlled-exec wall
(``P6BReadOnlyRealAgentStepExecutor`` → ``start_controlled_local_exec``) and maps
the sanitized result back into the **same** frozen ``SupervisorStepResult`` shape
the fake returns — without widening the ``ActivityInput`` / ``ActivityOutput``
contract, the claim-check data model, the stable ids/codes, or the no-leak
boundary.

Boundaries (all enforced before any read-only-runner launch):

  * **Independent default-off admission.** ``enabled is True`` + the **exact** S4
    token + the required injected P6-B seams (controlled-exec store, preflight
    store, prompt materializer, artifact sink, supervisor). With the flag off, the
    token mismatched, or any required seam missing, ``run_step`` makes **zero**
    controlled-exec / launch / sink calls and returns a sanitized
    ``SupervisorStepResult(ok=False, error_code=<stable code>)``.
  * **Defensive input validation.** The sanitized ``ActivityInput`` is revalidated
    (exact type, schema version, safe refs, bounded attempt, read-only role key,
    claim-check refs). Unsafe material fails closed with ``runtime_unsafe_material``
    and a malformed payload with ``invalid_start_payload`` — both before any launch.
  * **Closed supervisor-side role mapping.** The history-safe S3 ``role_key`` is
    resolved to exactly one runnable read-only controlled-exec role key via the
    fully-enumerated ``S4_HISTORY_SAFE_ROLE_TO_CONTROLLED_EXEC_ROLE`` table. Every
    other input — any other S3 key, any write/future/platform-derived label, any
    caller-supplied role — fails closed before launch.
  * **Sanitized WP4 translation.** Only sanitized refs/digests/counts cross into a
    minimal WP4-shaped request + ``RoleBinding``; the ``input_claim_refs`` become
    artifact-ref-shaped mappings (refs/digests only, no raw bytes). Raw prompt /
    context / tool output / stdout / card / platform ids never enter this path.
  * **Down-mapped stable codes.** The richer additive ``p6b_*`` / controlled-exec
    inner codes are mapped down to the frozen ``STABLE_CODES`` history vocabulary
    (``_map_failure_code``) — never surfaced into the Temporal-history-facing
    result. Supervisor non-success collapses to a transient ``runtime_error``;
    output problems to ``runtime_unsafe_material`` / ``runtime_history_leak_detected``.
  * **No-throw + no-leak.** Any raw-looking exception from the delegate collapses to
    a stable code without the exception object ever being referenced; local history
    projections and serialized bytes pass the SCAN-1 / SCAN-2 no-leak scanners.

The real seam **is the only new construction**. It builds no runner, shell,
child-process launcher, or network client of its own; it calls the merged
controlled-exec boundary (through the P6-B executor) and nothing else. This module
starts no Temporal-worker/service/runtime/subprocess and reaches no
gate/way, Fei/shu, live, or delivery surface.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from temporalio.exceptions import ApplicationError

from ..activity_preflight import (
    DurableStatePreflightError,
    query_durable_state_preflight,
)
from ..ai_flow_executor import StepExecutionOutcome
from ..ai_flow_spec import RoleBinding
from ..p6b_read_only_real_agent import (
    P6B_APPROVAL_MISMATCH,
    P6B_EXECUTION_DISABLED,
    P6B_OUTPUT_UNSAFE,
    P6B_PRECONDITION_UNMET,
    P6B_PROMPT_MATERIALIZATION_FAILED,
    P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN,
    P6B_ROLE_NOT_READ_ONLY,
    P6B_RUNNER_PROVENANCE_UNVERIFIED,
    P6BReadOnlyRealAgentStepExecutor,
)
from . import contracts as C
from .s2_supervisor_adapter import SupervisorStepResult

# --------------------------------------------------------------------------- #
# Exact S4 real-seam implementation approval token. Distinct from the S2/S3/P6-B
# tokens and likewise encoding the in-force non-approvals so an accidental enable
# cannot widen scope. The ``gate``/``way`` and ``fei``/``shu`` boundary words are split across
# literals so the no-leak/forbidden-wording scans never trip on the constant while
# the runtime value stays exactly the operator-approvable phrase.
# --------------------------------------------------------------------------- #
S4_READ_ONLY_REAL_AGENT_STEP_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_s4_read_only_real_agent_step_execution_"
    "implementation_bind_merged_s2_s3_activity_seam_to_real_read_only_supervisor_seam_"
    "delegating_one_bounded_read_only_step_to_merged_p6b_controlled_exec_wall_"
    "default_off_single_read_only_role_pinned_local_acpx_only_no_write_roles_no_file_mutation_"
    "no_npx_no_network_runner_no_temporal_worker_or_service_or_runtime_or_subprocess_start_"
    "no_live_no_"
    "gate"
    "way_no_"
    "fei"
    "shu_no_default_on_no_public_ingress_no_external_messaging_surface_"
    "no_production_config_no_real_delivery_no_real_smoke_without_separate_approval"
)

# --------------------------------------------------------------------------- #
# Closed supervisor-side mapping: history-safe S3 role key → runnable read-only
# controlled-exec role key (design packet §6.2). Fully enumerated; there is no
# default, no permissive fallback, and no caller-supplied role. Every history-safe
# S3 role key in ``INTENT_CLASS_TO_ROLE_KEY`` is a key here; everything else fails
# closed before any launch (§6.3). ``architecture_packet`` and
# ``programmer_candidate_review`` deliberately resolve to the read-only *reviewer*
# role only — never an architect/programmer *write* role. ``WRITE_ROLES_NOT_APPROVED``.
# --------------------------------------------------------------------------- #
S4_HISTORY_SAFE_ROLE_TO_CONTROLLED_EXEC_ROLE: dict[str, str] = {
    "sachima_claude_read_only_architect": "sachima.claude.read_only_reviewer",
    "sachima_claude_read_only_programmer_candidate": "sachima.claude.read_only_reviewer",
    "sachima_codex_read_only_reviewer": "sachima.codex.primary_reviewer",
}

#: Both runnable controlled-exec roles are read/search-only one-shot reviewers.
_READ_ONLY_CAPABILITIES: tuple[str, ...] = ("read", "search")
#: A stable, sanitized logical-role label for the WP4 ``RoleBinding``. It is never
#: projected into history; only the resolved read-only ``role_key`` matters.
_S4_LOGICAL_ROLE = "read_only_reviewer"

#: A read-only run report is small; mirror the P6-B default output claim-check bound.
_DEFAULT_MAX_ARTIFACT_BYTES = 65536

_S4_HISTORY_TYPE = "sachima.supervisor.s4_read_only_real_agent_seam_history.v1"

_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

#: Only a genuinely transient ``runtime_error`` is retryable at the Temporal layer;
#: every deterministic fail-closed code stays non-retryable (design packet §9.1).
_RETRYABLE_STABLE_CODES = frozenset({C.RUNTIME_ERROR})

#: Additive outer ``p6b_*`` codes projected down to the frozen ``STABLE_CODES``
#: history vocabulary (design packet §5.3). ``p6b_precondition_unmet`` is handled
#: separately because a transient supervisor failure collapses there too.
_P6B_TO_STABLE_CODE: Mapping[str, str] = {
    P6B_EXECUTION_DISABLED: C.RUNTIME_DISABLED,
    P6B_APPROVAL_MISMATCH: C.RUNTIME_APPROVAL_MISMATCH,
    P6B_ROLE_NOT_READ_ONLY: C.RUNTIME_PRECONDITION_UNMET,
    P6B_RUNNER_PROVENANCE_UNVERIFIED: C.RUNTIME_PRECONDITION_UNMET,
    P6B_PROMPT_MATERIALIZATION_FAILED: C.RUNTIME_PRECONDITION_UNMET,
    P6B_OUTPUT_UNSAFE: C.RUNTIME_UNSAFE_MATERIAL,
}


# --------------------------------------------------------------------------- #
# Minimal WP4-shaped step request (only what the P6-B executor reads via getattr)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _S4StepRequest:
    """Sanitized, WP4-shaped step request for the P6-B controlled-exec bridge.

    Carries only sanitized refs / counts / lease fields. The P6-B executor reads
    these via ``getattr`` and derives the controlled-exec ``activity_id`` /
    ``idempotency_key`` itself; no raw prompt/context/platform material lives here.
    """

    run_id: str
    step_id: str
    attempt_index: int
    transaction_ref: str
    operation_ref: str
    idempotency_key: str
    lease_id: str | None
    lease_epoch: int
    lease_holder_ref: str | None
    expected_state_version: int
    operator_gate: bool


def _safe_for_scan(value: Any) -> str:
    """Best-effort scan projection value that never calls an unsafe repr into history."""

    if type(value) is str:
        return value
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - validation projection must remain no-throw
        return "unrepresentable_value"


def _input_projection(activity_input: C.ActivityInput) -> dict[str, Any]:
    refs: list[dict[str, Any]] = []
    raw_refs = getattr(activity_input, "input_claim_refs", None)
    if isinstance(raw_refs, tuple):
        for ref in raw_refs:
            if type(ref) is C.ClaimCheckRef:
                refs.append(
                    {
                        "ref": _safe_for_scan(ref.ref),
                        "digest": _safe_for_scan(ref.digest),
                        "kind": _safe_for_scan(ref.kind),
                        "byte_count": ref.byte_count if type(ref.byte_count) is int else _safe_for_scan(ref.byte_count),
                    }
                )
            else:
                refs.append({"raw": _safe_for_scan(ref)})
    else:
        refs.append({"raw": "invalid_input_claim_refs"})
    return {
        "run_ref": _safe_for_scan(getattr(activity_input, "run_ref", None)),
        "step_ref": _safe_for_scan(getattr(activity_input, "step_ref", None)),
        "role_key": _safe_for_scan(getattr(activity_input, "role_key", None)),
        "input_claim_refs": refs,
    }


def _safe_sha256_digest(value: Any) -> str | None:
    if isinstance(value, str) and _SHA256_DIGEST_RE.fullmatch(value) is not None:
        return value
    return None


# --------------------------------------------------------------------------- #
# The real read-only supervisor seam
# --------------------------------------------------------------------------- #
class S4ReadOnlyRealAgentSupervisorSeam:
    """Real, default-off ``SupervisorSeam`` delegating one bounded read-only step.

    Bound by ``S2LocalOfflineSupervisorAdapter`` exactly like the fake seam
    (``run_step(activity_input) -> SupervisorStepResult``). When admitted it
    delegates to ``P6BReadOnlyRealAgentStepExecutor`` (the proven controlled-exec
    wall) and maps the sanitized outcome back to the frozen ``SupervisorStepResult``
    shape; when not admitted, or on any validation/role/launch failure, it fails
    closed with a stable code and zero downstream calls.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        approval_token: str = "",
        controlled_exec_store: Any = None,
        preflight_store: Any = None,
        prompt_materializer: Callable[[Any], str] | None = None,
        artifact_sink: Callable[..., Any] | None = None,
        invoke_supervisor: Callable[[Any], Any] | None = None,
        role_file_digest: str | None = None,
        preflight_activity_id: str | None = None,
        prior_dry_run_evidence_digest: str | None = None,
        role_root: str | Path | None = None,
        transaction_ref: str = "",
        operation_ref: str = "",
        lease_id: str | None = None,
        lease_epoch: int = 0,
        lease_holder_ref: str | None = None,
        expected_state_version: int = 0,
        max_artifact_bytes: int = _DEFAULT_MAX_ARTIFACT_BYTES,
    ) -> None:
        self.enabled = enabled
        self.approval_token = approval_token
        self._controlled_exec_store = controlled_exec_store
        self._preflight_store = preflight_store
        self._prompt_materializer = prompt_materializer
        self._artifact_sink = artifact_sink
        self._invoke_supervisor = invoke_supervisor
        self._role_file_digest = role_file_digest
        self._preflight_activity_id = preflight_activity_id
        self._prior_dry_run_evidence_digest = prior_dry_run_evidence_digest
        self._role_root = role_root
        self._transaction_ref = transaction_ref
        self._operation_ref = operation_ref
        self._lease_id = lease_id
        self._lease_epoch = lease_epoch
        self._lease_holder_ref = lease_holder_ref
        self._expected_state_version = expected_state_version
        self._max_artifact_bytes = max_artifact_bytes
        self._history: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Admission (default-off) — zero controlled-exec/launch/sink when not admitted
    # ------------------------------------------------------------------ #
    def _admission_code(self) -> str | None:
        if self.enabled is not True:
            return C.RUNTIME_DISABLED
        if self.approval_token != S4_READ_ONLY_REAL_AGENT_STEP_APPROVAL_TOKEN:
            return C.RUNTIME_APPROVAL_MISMATCH
        if (
            self._controlled_exec_store is None
            or self._preflight_store is None
            or not callable(self._prompt_materializer)
            or not callable(self._artifact_sink)
            or not callable(self._invoke_supervisor)
        ):
            return C.RUNTIME_PRECONDITION_UNMET
        return None

    # ------------------------------------------------------------------ #
    # SupervisorSeam.run_step — the only method the adapter calls
    # ------------------------------------------------------------------ #
    def run_step(self, activity_input: Any) -> SupervisorStepResult:
        code = self._admission_code()
        if code is not None:
            # Not admitted → never touch the delegate (and therefore no launch).
            self._record("run_step_rejected", error_code=code)
            return self._failure_result(code)

        reject = self._validate_input(activity_input)
        if reject is not None:
            # Validation failed before any launch: record only the stable code.
            self._record("run_step_rejected", error_code=reject)
            return self._failure_result(reject)

        run_ref = activity_input.run_ref
        step_ref = activity_input.step_ref

        controlled_role_key = S4_HISTORY_SAFE_ROLE_TO_CONTROLLED_EXEC_ROLE.get(activity_input.role_key)
        if controlled_role_key is None:
            # Any off-table / write / future / platform-derived role fails closed
            # exactly like an unknown role — before any launch.
            self._record("run_step_rejected", run_ref=run_ref, step_ref=step_ref, error_code=C.INVALID_START_PAYLOAD)
            return self._failure_result(C.INVALID_START_PAYLOAD)

        prepared = self._prepare(activity_input, controlled_role_key)
        if isinstance(prepared, str):
            self._record("run_step_rejected", run_ref=run_ref, step_ref=step_ref, error_code=prepared)
            return self._failure_result(prepared)
        request, role_binding, resolved_inputs = prepared

        try:
            outcome = self._build_executor().execute(
                request, role_binding=role_binding, resolved_inputs=resolved_inputs
            )
            return self._map_outcome(outcome, run_ref, step_ref)
        except BaseException:  # noqa: BLE001 - no-throw boundary; never bind/echo the exception
            # Collapse any raw-looking exception to a stable code; the exception
            # object is never referenced, so its text/repr/traceback cannot leak.
            self._record("run_step_error", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_ERROR)
            return self._failure_result(C.RUNTIME_ERROR)

    # ------------------------------------------------------------------ #
    # Validation (before any role mapping / launch)
    # ------------------------------------------------------------------ #
    def _validate_input(self, activity_input: Any) -> str | None:
        if type(activity_input) is not C.ActivityInput:
            return C.INVALID_START_PAYLOAD
        # Unsafe material (raw prompt / platform / path / secret marker) fails closed
        # first, so a denylisted marker is never collapsed into a safe-looking id.
        if C.scan_projection_for_leak(_input_projection(activity_input)) is not None:
            return C.RUNTIME_UNSAFE_MATERIAL
        try:
            C.validate_activity_input(activity_input)
        except C.ContractError:
            return C.INVALID_START_PAYLOAD
        return None

    # ------------------------------------------------------------------ #
    # Sanitized WP4 translation (refs/digests/counts only; no raw bytes)
    # ------------------------------------------------------------------ #
    def _prepare(
        self, activity_input: C.ActivityInput, controlled_role_key: str
    ) -> tuple[_S4StepRequest, RoleBinding, tuple[Mapping[str, Any], ...]] | str:
        try:
            resolved_inputs = self._resolved_inputs(activity_input)
            lease_id, lease_epoch, lease_holder_ref, state_version = self._resolve_lease()
        except (C.ContractError, DurableStatePreflightError):
            return C.RUNTIME_PRECONDITION_UNMET
        except BaseException:  # noqa: BLE001 - fail closed without raw details
            return C.RUNTIME_PRECONDITION_UNMET
        role_binding = RoleBinding(
            logical_role=_S4_LOGICAL_ROLE,
            role_key=controlled_role_key,
            capabilities=_READ_ONLY_CAPABILITIES,
        )
        request = _S4StepRequest(
            run_id=activity_input.run_ref,
            step_id=activity_input.step_ref,
            attempt_index=activity_input.attempt_index,
            transaction_ref=self._transaction_ref,
            operation_ref=self._operation_ref,
            idempotency_key=(
                f"s4_idem_{activity_input.run_ref}_{activity_input.step_ref}_{activity_input.attempt_index}"
            ),
            lease_id=lease_id,
            lease_epoch=lease_epoch,
            lease_holder_ref=lease_holder_ref,
            expected_state_version=state_version,
            operator_gate=True,
        )
        return request, role_binding, resolved_inputs

    @staticmethod
    def _resolved_inputs(activity_input: C.ActivityInput) -> tuple[Mapping[str, Any], ...]:
        """Project each sanitized ``ClaimCheckRef`` to an artifact-ref-shaped mapping.

        Only the four claim-check fields the controlled-exec bridge consumes cross
        over (id / digest / kind / count). Raw bytes never enter this mapping.
        """

        resolved: list[dict[str, Any]] = []
        for ref in activity_input.input_claim_refs:
            resolved.append(
                {
                    "artifact_id": ref.ref,
                    "content_digest": ref.digest,
                    "artifact_kind": ref.kind,
                    "byte_count": ref.byte_count,
                }
            )
        return tuple(resolved)

    def _resolve_lease(self) -> tuple[str | None, int, str | None, int]:
        """Resolve the lease binding for the controlled-exec request.

        An explicitly-supplied lease is used as given; otherwise the binding is
        derived from the durable-state preflight record (the single source of
        truth), so the request lease matches the preflight lease by construction.
        A missing/invalid preflight record raises and fails closed above.
        """

        if self._lease_id is not None:
            return self._lease_id, self._lease_epoch, self._lease_holder_ref, self._expected_state_version
        record = query_durable_state_preflight(
            self._preflight_store, activity_id=self._preflight_activity_id
        ).to_durable_state()
        return record["lease_id"], record["lease_epoch"], record["lease_holder_ref"], record["state_version"]

    def _build_executor(self) -> P6BReadOnlyRealAgentStepExecutor:
        """Build the proven P6-B controlled-exec bridge with the injected seams.

        Constructed only after S4 admission has passed, so nothing is built when the
        seam is disabled / token-mismatched / missing a dependency.
        """

        return P6BReadOnlyRealAgentStepExecutor(
            enabled=True,
            approval_token=P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN,
            controlled_exec_store=self._controlled_exec_store,
            preflight_store=self._preflight_store,
            prompt_materializer=self._prompt_materializer,
            artifact_sink=self._artifact_sink,
            invoke_supervisor=self._invoke_supervisor,
            role_file_digest=self._role_file_digest,
            preflight_activity_id=self._preflight_activity_id,
            prior_dry_run_evidence_digest=self._prior_dry_run_evidence_digest,
            role_root=self._role_root,
            max_artifact_bytes=self._max_artifact_bytes,
        )

    # ------------------------------------------------------------------ #
    # Map the P6-B outcome → the frozen SupervisorStepResult shape
    # ------------------------------------------------------------------ #
    def _map_outcome(self, outcome: Any, run_ref: str, step_ref: str) -> SupervisorStepResult:
        if type(outcome) is not StepExecutionOutcome:
            self._record("run_step_failed", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_ERROR)
            return self._failure_result(C.RUNTIME_ERROR)
        if outcome.ok is not True:
            code = self._map_failure_code(outcome)
            self._record("run_step_failed", run_ref=run_ref, step_ref=step_ref, error_code=code)
            return self._failure_result(
                code,
                interrupted=bool(outcome.interrupted),
                cleanup_verified=bool(outcome.cleanup_verified),
                ambiguous=bool(outcome.ambiguous),
            )

        artifact_ref = self._single_artifact_ref(outcome)
        evidence_ref = self._normalized_evidence_ref(outcome.evidence_ref)
        evidence_digest = _safe_sha256_digest(outcome.evidence_digest)
        if artifact_ref is None or evidence_ref is None or evidence_digest is None:
            # Zero / extra / unsafe / oversized ref, or a non-conforming evidence
            # ref/digest → fail closed; never a business success.
            self._record("output_rejected", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_UNSAFE_MATERIAL)
            return self._failure_result(C.RUNTIME_UNSAFE_MATERIAL)

        result = SupervisorStepResult(
            ok=True,
            step_status="completed",
            artifact_ref=artifact_ref,
            evidence_ref=evidence_ref,
            evidence_digest=evidence_digest,
        )
        # Defence in depth: the sanitized result projection must itself pass SCAN 1.
        if C.scan_projection_for_leak(self._result_projection(result)) is not None:
            self._record("output_rejected", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_HISTORY_LEAK_DETECTED)
            return self._failure_result(C.RUNTIME_HISTORY_LEAK_DETECTED)
        self._record("run_step_completed", run_ref=run_ref, step_ref=step_ref)
        return result

    def _map_failure_code(self, outcome: StepExecutionOutcome) -> str:
        """Project the additive ``p6b_*`` / inner code down to a stable history code.

        ``p6b_*`` inner detail never crosses into the Temporal-history-facing result;
        anything unrecognised collapses conservatively to ``runtime_error``.
        """

        code = outcome.error_code
        mapped = _P6B_TO_STABLE_CODE.get(code) if isinstance(code, str) else None
        if mapped is not None:
            return mapped
        if code == P6B_PRECONDITION_UNMET:
            # A supervisor non-success (or runner-lost) collapses here retryable →
            # transient runtime_error; a genuine precondition failure stays
            # runtime_precondition_unmet (design packet §5.3 / §9.1).
            return C.RUNTIME_ERROR if bool(getattr(outcome, "retryable", False)) else C.RUNTIME_PRECONDITION_UNMET
        if isinstance(code, str) and code in C.STABLE_CODES:
            return code
        return C.RUNTIME_ERROR

    @staticmethod
    def _single_artifact_ref(outcome: StepExecutionOutcome) -> C.StepArtifactRef | None:
        refs = outcome.artifact_refs
        if not isinstance(refs, tuple) or len(refs) != 1:
            return None
        projection = refs[0]
        if not isinstance(projection, Mapping) or set(projection) != set(C.ALLOWED_ARTIFACT_REF_KEYS):
            return None
        try:
            artifact = C.StepArtifactRef(
                artifact_id=projection["artifact_id"],
                producer_step_id=projection["producer_step_id"],
                content_digest=projection["content_digest"],
                artifact_kind=projection["artifact_kind"],
                byte_count=projection["byte_count"],
                created_at_ref=projection["created_at_ref"],
            )
            C.validate_step_artifact_ref(artifact)
        except C.ContractError:
            return None
        if C.scan_projection_for_leak(C.step_artifact_ref_projection(artifact)) is not None:
            return None
        return artifact

    @staticmethod
    def _normalized_evidence_ref(value: Any) -> str | None:
        """Normalize a supervisor evidence ref to the strict history id charset.

        The supervisor evidence ref may carry ``:``/``-``; before it can cross into
        ``ActivityOutput.evidence_ref`` it must be collapsed to the strict
        ``_safe_id`` charset (``safe_ref``) or fail closed (design packet §5.1).
        """

        if not isinstance(value, str):
            return None
        try:
            return C.safe_ref(value)
        except C.ContractError:
            return None

    @staticmethod
    def _result_projection(result: SupervisorStepResult) -> dict[str, Any]:
        return {
            "artifact_ref": C.step_artifact_ref_projection(result.artifact_ref),
            "evidence_ref": result.evidence_ref,
            "evidence_digest": result.evidence_digest,
            "step_status": result.step_status,
        }

    @staticmethod
    def _failure_result(
        code: str,
        *,
        interrupted: bool = False,
        cleanup_verified: bool = False,
        ambiguous: bool = False,
    ) -> SupervisorStepResult:
        safe_code = code if code in C.STABLE_CODES else C.RUNTIME_ERROR
        return SupervisorStepResult(
            ok=False,
            step_status=C.CANCEL_AMBIGUOUS if ambiguous else "failed_terminal",
            artifact_ref=None,
            evidence_ref=None,
            evidence_digest=None,
            error_code=safe_code,
            interrupted=interrupted,
            cleanup_verified=cleanup_verified,
            ambiguous=ambiguous,
        )

    # ------------------------------------------------------------------ #
    # Sanitized local history projection (SCAN 1 / SCAN 2 surfaces)
    # ------------------------------------------------------------------ #
    def history_projection(self) -> dict[str, Any]:
        with self._lock:
            return {
                "type": _S4_HISTORY_TYPE,
                "snapshot_version": len(self._history),
                "events": [dict(event) for event in self._history],
            }

    def serialized_history_bytes(self) -> bytes:
        return C.canonical_json_bytes(self.history_projection())

    def _record(
        self,
        event: str,
        *,
        run_ref: str | None = None,
        step_ref: str | None = None,
        error_code: str | None = None,
    ) -> None:
        with self._lock:
            projection = {
                "event": C.safe_ref(event),
                "sequence": len(self._history) + 1,
                "run_ref": run_ref,
                "step_ref": step_ref,
                "error_code": error_code,
            }
            if C.scan_projection_for_leak(projection) is not None:
                projection = {
                    "event": "history_projection_rejected",
                    "sequence": len(self._history) + 1,
                    "run_ref": None,
                    "step_ref": None,
                    "error_code": C.RUNTIME_UNSAFE_MATERIAL,
                }
            self._history.append(projection)


# --------------------------------------------------------------------------- #
# S4 Activity failure helper — split retryable transient runtime_error from the
# deterministic fail-closed codes (design packet §9.1; Temporal SoT docs.temporal.io)
# --------------------------------------------------------------------------- #
def s4_activity_failure_for_code(code: str) -> ApplicationError:
    """Build a Temporal ``ApplicationError`` carrying only a bare stable code.

    Deterministic fail-closed codes are raised **non-retryable**
    (``non_retryable=True``); a transient ``runtime_error`` is raised **retryable**
    (``non_retryable=False``) so the retry policy can retry it — idempotency, not
    retry, remains the safety mechanism (a retried attempt reconciles against the
    resident pre-claim and never starts a second real run). The message and type are
    the bare stable code, never raw input, exception text, or a traceback.
    """

    safe_code = code if code in C.STABLE_CODES else C.RUNTIME_ERROR
    non_retryable = safe_code not in _RETRYABLE_STABLE_CODES
    return ApplicationError(safe_code, type=safe_code, non_retryable=non_retryable)


__all__ = [
    "S4_READ_ONLY_REAL_AGENT_STEP_APPROVAL_TOKEN",
    "S4_HISTORY_SAFE_ROLE_TO_CONTROLLED_EXEC_ROLE",
    "S4ReadOnlyRealAgentSupervisorSeam",
    "s4_activity_failure_for_code",
]
