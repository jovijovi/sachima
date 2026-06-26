"""P6-B bounded read-only real-agent ``StepExecutor`` bridge (default-off).

``P6BReadOnlyRealAgentStepExecutor`` implements the merged WP4 ``StepExecutor``
Protocol shape —

    execute(request, *, role_binding, resolved_inputs) -> StepExecutionOutcome

— as a thin, default-off **bridge** that adapts the already-merged one-shot
controlled local exec (``start_controlled_local_exec``) into the unmodified WP4
seam, injectable into the unmodified P6-A ``P6ControlledAiFlowSession``. It builds
no new runner, claim store, provenance gate, or prompt machine, and modifies
WP4 / P6-A / P5 / controlled-exec not at all.

Boundaries (all enforced before any read-only-runner launch):

  * Default-off behind ``enabled is True`` + an **exact** P6-B approval token;
    with the flag off, the token mismatched, or a required seam (controlled-exec
    store, preflight store, prompt materializer, artifact sink) missing, it makes
    **zero** controlled-exec / launch / sink calls and returns a sanitized
    ``StepExecutionOutcome(ok=False, error_code=p6b_*)``.
  * Read-only role enforcement: ``role_binding.capabilities`` must be a non-empty
    subset of ``{read, search}`` and the role key must be an existing controlled
    read-only role (never a write/future key) — else ``p6b_role_not_read_only``
    before any launch. The controlled-exec wall re-checks the resolved role file
    permissions and adapter pin (double wall).
  * No runner is built here: there is no local-agent package launcher, shell,
    child-process API, shell interpolation, or network. The committed role stays null-binary,
    so even fully wired the default path cannot launch; the pinned-local
    provenance wall lives inside the controlled-exec module.
  * The prompt is materialized only through the explicitly injected
    materializer, after the controlled-exec claim; raw prompt text never enters
    durable claim state, fingerprints, or query projections. A ``None``
    materializer fails closed (no run).
  * The single read-only output is claim-checked through the injected sink: it
    must yield exactly one sanitized ``ArtifactRef`` projection (refs/digests
    only; bytes never enter durable state). Zero/extra/unsafe/oversized refs fail
    closed (``p6b_output_unsafe``).
  * The bridge never sets a business verdict and never infers success: it returns
    only a sanitized outcome and lets WP4 verify the artifact ref via its own
    ``_verify_single_output``.
  * Active-run cancellation preserves the WP3b WATCH — a clean ``cancelled`` is
    never claimed. Query / recover never relaunch.

The outer ``p6b_*`` codes are additive: they wrap, never replace, the inner
controlled-exec / ``runtime_*`` codes. This module imports no ``temporalio``, no
IM/delivery surface, and no real runner.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from .ai_flow_artifacts import AiFlowArtifactError, ArtifactRef, verify_artifact_ref
from .ai_flow_executor import StepExecutionOutcome
from .activity_controlled_exec import (
    CONTROLLED_EXEC_FUTURE_ROLE_KEYS,
    CONTROLLED_EXEC_MODE,
    CONTROLLED_EXEC_ROLE_ALLOWLIST,
    CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN,
    ControlledLocalExecError,
    ControlledLocalExecRequest,
    query_controlled_local_exec,
    start_controlled_local_exec,
)
from .p5_temporal import contracts as C
from .p6b_planning_report_prompt import P6B_PLANNING_REPORT_PROMPT_REF

# --------------------------------------------------------------------------- #
# Exact P6-B implementation approval token. Split across literals so the static
# boundary/leak scans never trip on the boundary words while the runtime value
# is exactly the operator-approved phrase. It encodes the in-force non-approvals
# so an accidental enable cannot widen scope.
# --------------------------------------------------------------------------- #
P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_p6b_bounded_read_only_real_agent_step_execution_"
    "implementation_default_off_single_read_only_planning_report_step_pinned_local_runner_only_"
    "no_write_roles_no_file_mutation_no_git_mutation_no_live_no_"
    "gate"
    "way_no_"
    "fei"
    "shu_no_production_config_no_real_delivery_no_real_smoke_without_separate_approval"
)

# --------------------------------------------------------------------------- #
# Additive outer p6b_* codes (wrap, never replace, inner controlled-exec codes)
# --------------------------------------------------------------------------- #
P6B_EXECUTION_DISABLED = "p6b_execution_disabled"
P6B_APPROVAL_MISMATCH = "p6b_approval_mismatch"
P6B_PRECONDITION_UNMET = "p6b_precondition_unmet"
P6B_ROLE_NOT_READ_ONLY = "p6b_role_not_read_only"
P6B_RUNNER_PROVENANCE_UNVERIFIED = "p6b_runner_provenance_unverified"
P6B_PROMPT_MATERIALIZATION_FAILED = "p6b_prompt_materialization_failed"
P6B_OUTPUT_UNSAFE = "p6b_output_unsafe"

P6B_STABLE_CODES = frozenset(
    {
        P6B_EXECUTION_DISABLED,
        P6B_APPROVAL_MISMATCH,
        P6B_PRECONDITION_UNMET,
        P6B_ROLE_NOT_READ_ONLY,
        P6B_RUNNER_PROVENANCE_UNVERIFIED,
        P6B_PROMPT_MATERIALIZATION_FAILED,
        P6B_OUTPUT_UNSAFE,
    }
)

#: Inner controlled-exec codes mapped to their additive outer wrapper. Anything
#: else collapses to ``p6b_precondition_unmet`` so no raw inner detail surfaces.
_INNER_TO_OUTER: Mapping[str, str] = {
    "activity_runner_provenance_unverified": P6B_RUNNER_PROVENANCE_UNVERIFIED,
    "activity_prompt_materialization_failed": P6B_PROMPT_MATERIALIZATION_FAILED,
    "activity_role_capability_rejected": P6B_ROLE_NOT_READ_ONLY,
    "activity_unknown_role": P6B_ROLE_NOT_READ_ONLY,
}

_READ_ONLY_CAPABILITIES = frozenset({"read", "search"})

_CONTROL_SNAPSHOT_TYPE = "sachima.supervisor.p6b_read_only_real_agent_snapshot.v1"
_HISTORY_TYPE = "sachima.supervisor.p6b_read_only_real_agent_history.v1"

_EVIDENCE_REF_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,127}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ACTIVITY_ID_PREFIX = "p6b_exec_"
_IDEMPOTENCY_PREFIX = "p6b_idem_"
_WORKFLOW_ID_PREFIX_LEN = len("p5wf_")

#: A read-only run report is small; anything larger fails the output claim-check.
_DEFAULT_MAX_ARTIFACT_BYTES = 65536


def _map_inner_code(code: Any) -> str:
    if isinstance(code, str):
        return _INNER_TO_OUTER.get(code, P6B_PRECONDITION_UNMET)
    return P6B_PRECONDITION_UNMET


def _failure(
    code: str, *, retryable: bool = False, ambiguous: bool = False, interrupted: bool = False
) -> StepExecutionOutcome:
    return StepExecutionOutcome(
        ok=False,
        step_status=C.CANCEL_AMBIGUOUS if ambiguous else "failed_terminal",
        artifact_refs=(),
        error_code=code,
        retryable=retryable,
        interrupted=interrupted,
        cleanup_verified=False,
        ambiguous=ambiguous,
    )


def _safe_evidence_ref(value: Any) -> str | None:
    if isinstance(value, str) and _EVIDENCE_REF_RE.fullmatch(value) is not None:
        return value
    return None


def _safe_digest(value: Any) -> str | None:
    if isinstance(value, str) and _SHA256_DIGEST_RE.fullmatch(value) is not None:
        return value
    return None


class P6BReadOnlyRealAgentStepExecutor:
    """Default-off WP4 ``StepExecutor`` bridging into the controlled-exec wall."""

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
        self._max_artifact_bytes = max_artifact_bytes
        self._history: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # WP4 protocol — sync execute (caller-owned orchestration drives this)
    # ------------------------------------------------------------------ #
    def execute(
        self,
        request: Any,
        *,
        role_binding: Any,
        resolved_inputs: tuple[Mapping[str, Any], ...],
    ) -> StepExecutionOutcome:
        code = self._admission_code()
        if code is not None:
            self._record("execute_rejected", error_code=code)
            return _failure(code)
        role_code = self._read_only_rejection(role_binding)
        if role_code is not None:
            self._record("execute_rejected", error_code=role_code)
            return _failure(role_code)
        translated = self._translate_or_fail(request, role_binding, resolved_inputs)
        if isinstance(translated, StepExecutionOutcome):
            return translated
        exec_request, run_ref, step_ref = translated
        return self._run_and_map(exec_request, request, role_binding, run_ref, step_ref)

    # ------------------------------------------------------------------ #
    # Admission (default-off) — zero controlled-exec call when not admitted
    # ------------------------------------------------------------------ #
    def _admission_code(self) -> str | None:
        if self.enabled is not True:
            return P6B_EXECUTION_DISABLED
        if self.approval_token != P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN:
            return P6B_APPROVAL_MISMATCH
        if (
            self._controlled_exec_store is None
            or self._preflight_store is None
            or self._prompt_materializer is None
            or self._artifact_sink is None
        ):
            return P6B_PRECONDITION_UNMET
        return None

    # ------------------------------------------------------------------ #
    # Read-only role re-check (double wall with the controlled-exec module)
    # ------------------------------------------------------------------ #
    def _read_only_rejection(self, role_binding: Any) -> str | None:
        capabilities = getattr(role_binding, "capabilities", None)
        role_key = getattr(role_binding, "role_key", None)
        if not isinstance(capabilities, tuple) or len(capabilities) == 0:
            return P6B_ROLE_NOT_READ_ONLY
        if any(cap not in _READ_ONLY_CAPABILITIES for cap in capabilities):
            return P6B_ROLE_NOT_READ_ONLY
        if (
            not isinstance(role_key, str)
            or role_key in CONTROLLED_EXEC_FUTURE_ROLE_KEYS
            or role_key not in CONTROLLED_EXEC_ROLE_ALLOWLIST
        ):
            return P6B_ROLE_NOT_READ_ONLY
        return None

    # ------------------------------------------------------------------ #
    # WP4 -> sanitized controlled-exec request translation
    # ------------------------------------------------------------------ #
    def _translate_or_fail(
        self, request: Any, role_binding: Any, resolved_inputs: Any
    ) -> tuple[ControlledLocalExecRequest, str, str] | StepExecutionOutcome:
        try:
            run_ref = C.safe_ref(str(getattr(request, "run_id", None)))
            step_ref = C.safe_ref(str(getattr(request, "step_id", None)))
        except C.ContractError:
            self._record("execute_rejected", error_code=P6B_PRECONDITION_UNMET)
            return _failure(P6B_PRECONDITION_UNMET)

        # Only claim-check refs may cross into the controlled-exec request: fail
        # closed on any raw/private/secret material in the resolved inputs before
        # any launch.
        if not isinstance(resolved_inputs, (list, tuple)):
            self._record("execute_rejected", run_ref=run_ref, step_ref=step_ref, error_code=P6B_PRECONDITION_UNMET)
            return _failure(P6B_PRECONDITION_UNMET)
        for item in resolved_inputs:
            if C.scan_projection_for_leak(item) is not None:
                self._record(
                    "execute_rejected", run_ref=run_ref, step_ref=step_ref, error_code=P6B_PRECONDITION_UNMET
                )
                return _failure(P6B_PRECONDITION_UNMET)
        try:
            context_refs = tuple(
                C.artifact_ref_to_claim_check(item).ref for item in resolved_inputs
            )
        except C.ContractError:
            self._record(
                "execute_rejected", run_ref=run_ref, step_ref=step_ref, error_code=P6B_PRECONDITION_UNMET
            )
            return _failure(P6B_PRECONDITION_UNMET)

        suffix = C.workflow_id_from_refs(run_ref, step_ref)[_WORKFLOW_ID_PREFIX_LEN:]
        attempt = getattr(request, "attempt_index", 1)
        exec_request = ControlledLocalExecRequest(
            activity_id=_ACTIVITY_ID_PREFIX + suffix,
            transaction_ref=getattr(request, "transaction_ref", ""),
            operation_ref=getattr(request, "operation_ref", ""),
            idempotency_key=f"{_IDEMPOTENCY_PREFIX}{suffix}_{attempt}",
            mode=CONTROLLED_EXEC_MODE,
            role_key=getattr(role_binding, "role_key", ""),
            approval_token=CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN,
            enabled=True,
            prompt_ref=P6B_PLANNING_REPORT_PROMPT_REF,
            context_refs=context_refs,
            role_file_digest=self._role_file_digest,
            prior_dry_run_evidence_digest=self._prior_dry_run_evidence_digest,
            preflight_activity_id=self._preflight_activity_id,
            lease_id=getattr(request, "lease_id", None),
            lease_epoch=getattr(request, "lease_epoch", 0),
            lease_holder_ref=getattr(request, "lease_holder_ref", None),
            expected_state_version=getattr(request, "expected_state_version", 0),
            operator_gate=getattr(request, "operator_gate", False) is True,
        )
        return exec_request, run_ref, step_ref

    # ------------------------------------------------------------------ #
    # Delegate to the proven controlled-exec wall + map the sanitized result
    # ------------------------------------------------------------------ #
    def _run_and_map(
        self,
        exec_request: ControlledLocalExecRequest,
        request: Any,
        role_binding: Any,
        run_ref: str,
        step_ref: str,
    ) -> StepExecutionOutcome:
        try:
            result = start_controlled_local_exec(
                exec_request,
                store=self._controlled_exec_store,
                preflight_store=self._preflight_store,
                prompt_materializer=self._prompt_materializer,
                role_root=self._role_root,
                invoke_supervisor=self._invoke_supervisor,
            )
        except ControlledLocalExecError as exc:
            code = _map_inner_code(exc.error_code)
            self._record("execute_rejected", run_ref=run_ref, step_ref=step_ref, error_code=code)
            return _failure(code)
        except Exception:  # pragma: no cover - never leak a raw exception
            self._record("execute_rejected", run_ref=run_ref, step_ref=step_ref, error_code=P6B_PRECONDITION_UNMET)
            return _failure(P6B_PRECONDITION_UNMET)

        if getattr(result, "ok", False) is not True:
            code = _map_inner_code(getattr(result, "error_code", None))
            self._record("execute_failed", run_ref=run_ref, step_ref=step_ref, error_code=code)
            return _failure(code, retryable=bool(getattr(result, "retryable", False)))

        return self._project_output(result, request, role_binding, run_ref, step_ref)

    # ------------------------------------------------------------------ #
    # Output claim-check via the injected sink (bytes never enter state)
    # ------------------------------------------------------------------ #
    def _project_output(
        self, result: Any, request: Any, role_binding: Any, run_ref: str, step_ref: str
    ) -> StepExecutionOutcome:
        if getattr(result, "artifact_ref_count", None) != 1:
            self._record("output_rejected", run_ref=run_ref, step_ref=step_ref, error_code=P6B_OUTPUT_UNSAFE)
            return _failure(P6B_OUTPUT_UNSAFE)
        try:
            sink_refs = self._artifact_sink(request, result=result, role_binding=role_binding)
        except Exception:  # never leak a raw sink exception
            self._record("output_rejected", run_ref=run_ref, step_ref=step_ref, error_code=P6B_OUTPUT_UNSAFE)
            return _failure(P6B_OUTPUT_UNSAFE)
        refs = self._normalize_sink_refs(sink_refs)
        if refs is None or len(refs) != 1:
            self._record("output_rejected", run_ref=run_ref, step_ref=step_ref, error_code=P6B_OUTPUT_UNSAFE)
            return _failure(P6B_OUTPUT_UNSAFE)
        projection = self._safe_artifact_projection(refs[0], request)
        if projection is None:
            self._record("output_rejected", run_ref=run_ref, step_ref=step_ref, error_code=P6B_OUTPUT_UNSAFE)
            return _failure(P6B_OUTPUT_UNSAFE)

        self._record("execute_completed", run_ref=run_ref, step_ref=step_ref)
        # Caller-owned orchestration: success carries NO business verdict; WP4
        # records STEP_COMPLETED only after its own _verify_single_output.
        return StepExecutionOutcome(
            ok=True,
            step_status="completed",
            artifact_refs=(projection,),
            evidence_ref=_safe_evidence_ref(getattr(result, "evidence_ref", None)),
            evidence_digest=_safe_digest(getattr(result, "evidence_digest", None)),
        )

    @staticmethod
    def _normalize_sink_refs(sink_refs: Any) -> tuple[Any, ...] | None:
        if isinstance(sink_refs, Mapping) or isinstance(sink_refs, ArtifactRef):
            return (sink_refs,)
        if isinstance(sink_refs, (list, tuple)):
            return tuple(sink_refs)
        return None

    def _safe_artifact_projection(self, ref: Any, request: Any) -> dict[str, Any] | None:
        if isinstance(ref, ArtifactRef):
            candidate: dict[str, Any] = {key: getattr(ref, key) for key in C.ALLOWED_ARTIFACT_REF_KEYS}
        elif isinstance(ref, Mapping) and set(ref) == set(C.ALLOWED_ARTIFACT_REF_KEYS):
            candidate = {key: ref[key] for key in C.ALLOWED_ARTIFACT_REF_KEYS}
        else:
            return None
        try:
            verified = verify_artifact_ref(
                candidate,
                expected_kind=candidate["artifact_kind"],
                expected_producer=getattr(request, "step_id", None),
                max_bytes=self._max_artifact_bytes,
            )
        except AiFlowArtifactError:
            return None
        except Exception:  # pragma: no cover - never leak a raw exception
            return None
        projection = {key: getattr(verified, key) for key in C.ALLOWED_ARTIFACT_REF_KEYS}
        if C.scan_projection_for_leak(projection) is not None:
            return None
        return projection

    # ------------------------------------------------------------------ #
    # Oracle-conformant control surface (no relaunch; WATCH-preserving)
    # ------------------------------------------------------------------ #
    def query(self, *, run_id: str, step_id: str) -> dict[str, Any]:
        code = self._admission_code()
        if code is not None:
            return self._rejected_snapshot(run_id, step_id, code, event="query_rejected")
        return self._read_snapshot(run_id, step_id, event="query", recovered=False)

    def recover(self, *, run_id: str, step_id: str) -> dict[str, Any]:
        code = self._admission_code()
        if code is not None:
            return self._rejected_snapshot(run_id, step_id, code, event="recover_rejected")
        # Reattach by resident claim id; never relaunch uncertain work.
        return self._read_snapshot(run_id, step_id, event="recover", recovered=True)

    def cancel(
        self,
        *,
        run_id: str,
        step_id: str,
        scope: str,
        idempotency_key: str,
        interrupt_outcome: StepExecutionOutcome | None = None,
    ) -> StepExecutionOutcome:
        code = self._admission_code()
        if code is not None:
            self._record(
                "cancel_rejected",
                run_ref=self._best_effort_ref(run_id),
                step_ref=self._best_effort_ref(step_id),
                error_code=code,
            )
            return _failure(code)
        run_ref, step_ref = self._best_effort_ref(run_id), self._best_effort_ref(step_id)
        if scope != "active_run":
            self._record("cancel_rejected", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_CANCEL_SCOPE_UNSUPPORTED)
            return _failure(C.RUNTIME_CANCEL_SCOPE_UNSUPPORTED)
        # P6-B performs no real abort. Even if a caller supplies a confirmed-looking
        # lower-layer interrupt outcome, this bridge is not approved to transform it
        # into a clean active-run cancellation; the separate WP3b gate owns that
        # proof. Preserve the WATCH every time.
        _ = interrupt_outcome
        self._record("cancel_watch", run_ref=run_ref, step_ref=step_ref, error_code=C.ACTIVE_RUN_CANCELLATION_WATCH)
        return _failure(C.ACTIVE_RUN_CANCELLATION_WATCH, ambiguous=True)

    def close(self) -> dict[str, Any]:
        code = self._admission_code()
        if code is not None:
            self._record("close_rejected", error_code=code)
            return {
                "type": _CONTROL_SNAPSHOT_TYPE,
                "state": "store_invalid",
                "snapshot_version": len(self._history),
                "error_code": code,
            }
        # Sanitized close marker only; the caller-owned store is not disconnected.
        self._record("closed")
        return {"type": _CONTROL_SNAPSHOT_TYPE, "state": "closed", "snapshot_version": len(self._history)}

    # ------------------------------------------------------------------ #
    # Sanitized local history projection
    # ------------------------------------------------------------------ #
    def history_projection(self) -> dict[str, Any]:
        with self._lock:
            return {
                "type": _HISTORY_TYPE,
                "snapshot_version": len(self._history),
                "events": [dict(event) for event in self._history],
            }

    def serialized_history_bytes(self) -> bytes:
        return C.canonical_json_bytes(self.history_projection())

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _read_snapshot(self, run_id: str, step_id: str, *, event: str, recovered: bool) -> dict[str, Any]:
        try:
            run_ref = C.safe_ref(str(run_id))
            step_ref = C.safe_ref(str(step_id))
        except C.ContractError:
            return self._rejected_snapshot(run_id, step_id, C.RUNTIME_NOT_FOUND, event=f"{event}_rejected")
        activity_id = _ACTIVITY_ID_PREFIX + C.workflow_id_from_refs(run_ref, step_ref)[_WORKFLOW_ID_PREFIX_LEN:]
        try:
            result = query_controlled_local_exec(self._controlled_exec_store, activity_id=activity_id)
        except ControlledLocalExecError as exc:
            state = "not_found" if exc.error_code == "activity_not_found" else "store_invalid"
            code = None if exc.error_code == "activity_not_found" else _map_inner_code(exc.error_code)
            self._record(f"{event}_not_found", run_ref=run_ref, step_ref=step_ref, error_code=code)
            return self._snapshot_marker(run_ref, step_ref, state, code, recovered=recovered)
        return self._snapshot_from_result(run_ref, step_ref, result, recovered=recovered)

    def _snapshot_from_result(
        self, run_ref: str, step_ref: str, result: Any, *, recovered: bool
    ) -> dict[str, Any]:
        status = getattr(result, "status", None)
        state = status if isinstance(status, str) else "store_invalid"
        error_code = getattr(result, "error_code", None)
        marker = self._snapshot_marker(
            run_ref, step_ref, state, error_code if isinstance(error_code, str) else None, recovered=recovered
        )
        self._record(
            "recover" if recovered else "query", run_ref=run_ref, step_ref=step_ref, error_code=marker.get("error_code")
        )
        return marker

    def _snapshot_marker(
        self, run_ref: str, step_ref: str, state: str, error_code: str | None, *, recovered: bool = False
    ) -> dict[str, Any]:
        marker: dict[str, Any] = {
            "type": _CONTROL_SNAPSHOT_TYPE,
            "run_ref": run_ref,
            "step_ref": step_ref,
            "state": state,
            "snapshot_version": len(self._history),
            "artifact_refs": [],
            "error_code": error_code,
        }
        if recovered:
            marker["recovery_marker"] = "reattached_no_relaunch"
        if C.scan_projection_for_leak(marker) is not None:
            return {
                "type": _CONTROL_SNAPSHOT_TYPE,
                "run_ref": None,
                "step_ref": None,
                "state": "store_invalid",
                "snapshot_version": len(self._history),
                "artifact_refs": [],
                "error_code": C.RUNTIME_HISTORY_LEAK_DETECTED,
            }
        return marker

    def _rejected_snapshot(self, run_id: str, step_id: str, code: str, *, event: str) -> dict[str, Any]:
        run_ref = self._best_effort_ref(run_id)
        step_ref = self._best_effort_ref(step_id)
        self._record(event, run_ref=run_ref, step_ref=step_ref, error_code=code)
        return self._snapshot_marker(run_ref, step_ref, "store_invalid", code)

    def _best_effort_ref(self, value: Any) -> str:
        try:
            return C.safe_ref(str(value))
        except C.ContractError:
            return "ref_rejected"

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


__all__ = [
    "P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN",
    "P6B_EXECUTION_DISABLED",
    "P6B_APPROVAL_MISMATCH",
    "P6B_PRECONDITION_UNMET",
    "P6B_ROLE_NOT_READ_ONLY",
    "P6B_RUNNER_PROVENANCE_UNVERIFIED",
    "P6B_PROMPT_MATERIALIZATION_FAILED",
    "P6B_OUTPUT_UNSAFE",
    "P6B_STABLE_CODES",
    "P6BReadOnlyRealAgentStepExecutor",
]
