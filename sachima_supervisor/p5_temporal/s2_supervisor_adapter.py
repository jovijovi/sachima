"""S2 local/offline Activity-boundary → supervisor adapter seam (stage S2).

This module is the **fake/injected** seam between a Temporal Activity body and the
agent-run-supervisor supervised-step boundary. It is pure, local/offline Python:
importing or calling it starts no Temporal runtime, service, or lifecycle,
constructs no Temporal client or agent runner, opens no network connection, spawns
no child process, and reaches no external messaging surface. The real-agent binding
of this seam is a separate, later, separately-approved stage; S2 wires only a
deterministic, no-op-safe fake step body by **dependency injection**.

Contract (grounded in the S1 design packet §4 seam contract and §6 failure map):

  * **Activity-facing.** ``execute`` accepts a sanitized ``ActivityInput`` only and
    validates it *before* any seam call — exact type, schema version, safe
    ``run_ref`` / ``step_ref``, bounded ``attempt_index``, read-only ``role_key``
    (write/deliver/approve/reject/mutate role markers are rejected), and claim-check
    input refs. Unsafe material (raw prompt / platform / path / secret marker) fails
    closed with ``runtime_unsafe_material``; a malformed payload with
    ``invalid_start_payload`` — both before any seam call.
  * **Default-off + exact token + injected seam.** With the flag off, the token
    mismatched, or the injected seam missing, ``execute`` / ``query`` / ``recover``
    / ``cancel`` / ``close`` make **zero** seam calls and return a sanitized,
    no-throw rejection carrying a stable code.
  * **Injected body only.** The adapter never builds a runner, child process, shell,
    network client, or Temporal lifecycle object. It calls the caller-supplied
    ``SupervisorSeam.run_step`` and nothing else.
  * **Sanitized output.** A happy path returns a sanitized ``ActivityOutput`` —
    exactly one claim-check artifact ref (refs/digests only; bytes never enter
    state) plus an evidence ref/digest, and no caller-owned business verdict.
  * **No-throw toward history.** A raw-looking exception from the injected seam
    collapses to a stable ``runtime_error`` without echoing the exception text,
    repr, traceback, raw ids, or platform identifiers into any output / log /
    history projection.
  * **Duplicate / recover / no-relaunch.** An identical duplicate reconciles and
    replays the resident outcome without a second body call; a divergent duplicate
    fails closed with ``runtime_idempotency_conflict``; ``recover`` / ``query`` only
    reattach resident sanitized state and never relaunch uncertain work.
  * **Cancellation.** ``active_run`` cancellation stays a WP3b WATCH
    (``active_run_cancellation_watch`` → ``cancel_ambiguous``); the adapter never
    manufactures a clean cancel for S2 — it only reflects an already-proven
    interrupted + cleanup_verified lower-layer outcome.
  * **No-leak.** Local projections and serialized history bytes pass the SCAN-1 /
    SCAN-2 no-leak scanners; any projection that would leak is replaced by a
    sanitized rejected marker carrying only a stable code.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any, Protocol

from . import contracts as C

# --------------------------------------------------------------------------- #
# Exact S2 seam implementation approval token. It encodes the in-force
# non-approvals so an accidental enable cannot widen scope: default-off,
# injected-fake deterministic body only, no Temporal runtime/service/lifecycle
# start, no real agent or runner execution, no write roles, no external messaging
# surface, no production config, no real delivery.
# --------------------------------------------------------------------------- #
S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_s2_local_offline_activity_boundary_to_supervisor_adapter_seam_"
    "implementation_default_off_injected_fake_deterministic_step_body_only_dependency_injection_seam_"
    "no_temporal_runtime_or_service_or_lifecycle_start_no_real_agent_or_runner_execution_"
    "no_write_roles_no_default_on_no_public_ingress_no_external_messaging_surface_"
    "no_production_config_no_real_delivery"
)

_S2_OUTCOME_TYPE = "sachima.supervisor.s2_activity_seam_outcome.v1"
_S2_SNAPSHOT_TYPE = "sachima.supervisor.s2_activity_seam_snapshot.v1"
_S2_HISTORY_TYPE = "sachima.supervisor.s2_activity_seam_history.v1"

_RECOVERY_MARKER = "reattached_no_relaunch"


def _digest_ref(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Sanitized seam result + adapter outcome (frozen; refs / digests / codes only)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SupervisorStepResult:
    """Sanitized result returned by the injected supervisor seam — no verdict.

    Mirrors the agreed supervisor-status shape: ``ok`` + a normalized
    ``step_status``, at most one claim-check ``artifact_ref`` (refs/digests only;
    bytes never enter state), an ``evidence_ref`` + ``evidence_digest``, a stable
    ``error_code``, and the cancellation flags. It never carries a raw body or a
    caller-owned business verdict.
    """

    ok: bool
    step_status: str
    artifact_ref: C.StepArtifactRef | None = None
    evidence_ref: str | None = None
    evidence_digest: str | None = None
    error_code: str | None = None
    interrupted: bool = False
    cleanup_verified: bool = False
    ambiguous: bool = False


@dataclass(frozen=True)
class ActivitySeamOutcome:
    """Sanitized Activity-boundary outcome handed back to the Activity body."""

    ok: bool
    op: str
    error_code: str | None = None
    output: C.ActivityOutput | None = None
    replayed: bool = False
    active_run_watch: bool = False
    interrupted: bool = False
    cleanup_verified: bool = False
    ambiguous: bool = False
    step_status: str | None = None

    def to_projection(self) -> dict[str, Any]:
        """Sanitized projection for logs / evidence — refs, digests, codes only."""

        projection: dict[str, Any] = {
            "type": _S2_OUTCOME_TYPE,
            "schema_version": C.SCHEMA_VERSION,
            "ok": self.ok,
            "op": self.op,
            "error_code": self.error_code,
            "replayed": self.replayed,
            "active_run_watch": self.active_run_watch,
            "interrupted": self.interrupted,
            "cleanup_verified": self.cleanup_verified,
            "ambiguous": self.ambiguous,
            "step_status": self.step_status,
            "output": _activity_output_projection(self.output),
        }
        if C.scan_projection_for_leak(projection) is not None:
            return {
                "type": _S2_OUTCOME_TYPE,
                "schema_version": C.SCHEMA_VERSION,
                "ok": False,
                "op": self.op if _is_safe_op(self.op) else "execute",
                "error_code": C.RUNTIME_HISTORY_LEAK_DETECTED,
                "replayed": False,
                "active_run_watch": False,
                "interrupted": False,
                "cleanup_verified": False,
                "ambiguous": False,
                "step_status": "failed_terminal",
                "output": None,
            }
        return projection


def _is_safe_op(op: Any) -> bool:
    return isinstance(op, str) and C.scan_projection_for_leak({"op": op}) is None


def _safe_for_scan(value: Any) -> str:
    """Best-effort scan projection value that never calls an unsafe repr into history."""

    if type(value) is str:
        return value
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - validation projection must remain no-throw
        return "unrepresentable_value"


def _activity_output_projection(output: Any) -> dict[str, Any] | None:
    if type(output) is not C.ActivityOutput:
        return None
    if type(output.artifact_ref) is not C.StepArtifactRef:
        return None
    return {
        "schema_version": output.schema_version,
        "status": output.status,
        "artifact_ref": C.step_artifact_ref_projection(output.artifact_ref),
        "evidence_ref": output.evidence_ref,
        "evidence_digest": output.evidence_digest,
    }


# --------------------------------------------------------------------------- #
# Injected seam protocol + the default deterministic fake body
# --------------------------------------------------------------------------- #
class SupervisorSeam(Protocol):
    """Injected, caller-supplied supervisor step body. S2 binds only fakes.

    The adapter calls ``run_step`` and nothing else; the implementation is owned by
    the caller and dependency-injected. A real-agent binding is a later, separately
    approved stage.
    """

    def run_step(self, activity_input: C.ActivityInput) -> SupervisorStepResult: ...


class FakeDeterministicSupervisorSeam:
    """Default-path fake/offline supervisor body — deterministic, no real work.

    Produces a sanitized claim-check artifact ref + evidence purely from the
    sanitized ``ActivityInput``. It runs no real agent, builds no runner, opens no
    network connection, and spawns no child process — it is a pure function of its
    input, so it can never leak material into history.
    """

    def __init__(self) -> None:
        self.calls = 0

    def run_step(self, activity_input: C.ActivityInput) -> SupervisorStepResult:
        self.calls += 1
        artifact = C.build_step_artifact_ref(
            activity_input.run_ref,
            activity_input.step_ref,
            activity_input.attempt_index,
            activity_input.role_key,
        )
        evidence_ref, evidence_digest = C.deterministic_evidence_fields(
            activity_input.run_ref, activity_input.step_ref, activity_input.attempt_index
        )
        return SupervisorStepResult(
            ok=True,
            step_status="completed",
            artifact_ref=artifact,
            evidence_ref=evidence_ref,
            evidence_digest=evidence_digest,
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _failure(
    op: str,
    code: str,
    *,
    ambiguous: bool = False,
    interrupted: bool = False,
    active_run_watch: bool = False,
) -> ActivitySeamOutcome:
    return ActivitySeamOutcome(
        ok=False,
        op=op,
        error_code=code,
        output=None,
        replayed=False,
        active_run_watch=active_run_watch,
        interrupted=interrupted,
        cleanup_verified=False,
        ambiguous=ambiguous,
        step_status=C.CANCEL_AMBIGUOUS if ambiguous else "failed_terminal",
    )


# --------------------------------------------------------------------------- #
# The Activity-boundary → supervisor adapter
# --------------------------------------------------------------------------- #
class S2LocalOfflineSupervisorAdapter:
    """Default-off, fake/injected Activity-boundary → supervisor adapter seam."""

    def __init__(
        self,
        *,
        seam: Any = None,
        enabled: bool = False,
        approval_token: str = "",
        claim_store: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._seam = seam
        self.enabled = enabled
        self.approval_token = approval_token
        self._claim_store: dict[str, dict[str, Any]] = {} if claim_store is None else claim_store
        self._history: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Admission (default-off) — zero seam call when not admitted
    # ------------------------------------------------------------------ #
    def _admission_code(self) -> str | None:
        if self.enabled is not True:
            return C.RUNTIME_DISABLED
        if self.approval_token != S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN:
            return C.RUNTIME_APPROVAL_MISMATCH
        if self._seam is None or not callable(getattr(self._seam, "run_step", None)):
            return C.RUNTIME_PRECONDITION_UNMET
        return None

    # ------------------------------------------------------------------ #
    # Activity-facing execute
    # ------------------------------------------------------------------ #
    def execute(self, activity_input: Any) -> ActivitySeamOutcome:
        code = self._admission_code()
        if code is not None:
            self._record("execute_rejected", error_code=code)
            return _failure("execute", code)
        reject = self._validate_input(activity_input)
        if reject is not None:
            # Validation failed before any seam call: record only the stable code,
            # never the (possibly unsafe) input material.
            self._record("execute_rejected", error_code=reject)
            return _failure("execute", reject)

        run_ref = activity_input.run_ref
        step_ref = activity_input.step_ref
        key = C.workflow_id_from_refs(run_ref, step_ref)
        fingerprint = self._fingerprint(activity_input)

        with self._lock:
            record = self._claim_store.get(key)
            if record is not None:
                if record.get("fingerprint") != fingerprint:
                    # Divergent duplicate for the same (run_ref, step_ref): conflict,
                    # never a second body call.
                    self._record(
                        "execute_conflict", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_IDEMPOTENCY_CONFLICT
                    )
                    return _failure("execute", C.RUNTIME_IDEMPOTENCY_CONFLICT)
                # Identical duplicate: reconcile / replay resident outcome, no relaunch.
                self._record("execute_replayed", run_ref=run_ref, step_ref=step_ref)
                return self._replay_outcome(record)
            # Claim BEFORE delegation so a crash → recover/replay, never relaunch —
            # even if a fresh wrapper is recreated over the same caller-owned store.
            self._claim_store[key] = {"fingerprint": fingerprint, "run_ref": run_ref, "step_ref": step_ref}

        outcome = self._invoke_seam(activity_input, run_ref, step_ref)

        with self._lock:
            self._claim_store[key] = {
                "fingerprint": fingerprint,
                "run_ref": run_ref,
                "step_ref": step_ref,
                "outcome": outcome,
            }
        return outcome

    # ------------------------------------------------------------------ #
    # Validation (before any seam call)
    # ------------------------------------------------------------------ #
    def _validate_input(self, activity_input: Any) -> str | None:
        if type(activity_input) is not C.ActivityInput:
            return C.INVALID_START_PAYLOAD
        # Unsafe material (raw prompt / platform / path / secret marker) fails closed
        # first, so a denylisted marker is never collapsed into a safe-looking id.
        if C.scan_projection_for_leak(self._input_projection(activity_input)) is not None:
            return C.RUNTIME_UNSAFE_MATERIAL
        # Exact shape: type, schema version, safe run/step refs, bounded attempt,
        # read-only role key, claim-check input refs.
        try:
            C.validate_activity_input(activity_input)
        except C.ContractError:
            return C.INVALID_START_PAYLOAD
        return None

    @staticmethod
    def _input_projection(activity_input: C.ActivityInput) -> dict[str, Any]:
        refs: list[dict[str, Any]] = []
        raw_refs = activity_input.input_claim_refs
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
            "run_ref": _safe_for_scan(activity_input.run_ref),
            "step_ref": _safe_for_scan(activity_input.step_ref),
            "role_key": _safe_for_scan(activity_input.role_key),
            "input_claim_refs": refs,
        }

    @staticmethod
    def _fingerprint(activity_input: C.ActivityInput) -> str:
        material = {
            "schema_version": activity_input.schema_version,
            "run_ref": activity_input.run_ref,
            "step_ref": activity_input.step_ref,
            "attempt_index": activity_input.attempt_index,
            "role_key": activity_input.role_key,
            "input_claim_refs": sorted(
                [ref.ref, ref.digest, ref.kind, ref.byte_count] for ref in activity_input.input_claim_refs
            ),
        }
        return _digest_ref(material)

    # ------------------------------------------------------------------ #
    # Injected seam invocation (no-throw) + result mapping
    # ------------------------------------------------------------------ #
    def _invoke_seam(self, activity_input: C.ActivityInput, run_ref: str, step_ref: str) -> ActivitySeamOutcome:
        try:
            result = self._seam.run_step(activity_input)
        except BaseException:  # noqa: BLE001 - no-throw boundary; never bind/echo the exception
            # Collapse any raw-looking exception to a stable code; the exception
            # object is never referenced, so its text / repr / traceback cannot leak.
            self._record("execute_error", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_ERROR)
            return _failure("execute", C.RUNTIME_ERROR)
        return self._map_result(result, run_ref, step_ref)

    def _map_result(self, result: Any, run_ref: str, step_ref: str) -> ActivitySeamOutcome:
        if type(result) is not SupervisorStepResult:
            self._record("execute_rejected", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_ERROR)
            return _failure("execute", C.RUNTIME_ERROR)
        if result.ok is not True:
            code = result.error_code if result.error_code in C.STABLE_CODES else C.RUNTIME_ERROR
            self._record("execute_failed", run_ref=run_ref, step_ref=step_ref, error_code=code)
            return _failure("execute", code)
        output = self._build_output(result)
        if output is None:
            # Zero / extra / unsafe / oversized output ref → fail closed, no success.
            self._record("output_rejected", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_UNSAFE_MATERIAL)
            return _failure("execute", C.RUNTIME_UNSAFE_MATERIAL)
        # Defence in depth: the sanitized output projection must itself pass SCAN 1
        # (``validate_activity_output`` already rejects unsafe refs/kinds/digests).
        if C.scan_projection_for_leak(_activity_output_projection(output)) is not None:
            self._record("output_rejected", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_HISTORY_LEAK_DETECTED)
            return _failure("execute", C.RUNTIME_HISTORY_LEAK_DETECTED)
        outcome = ActivitySeamOutcome(ok=True, op="execute", error_code=None, output=output, step_status="completed")
        self._record("execute_completed", run_ref=run_ref, step_ref=step_ref)
        return outcome

    @staticmethod
    def _build_output(result: SupervisorStepResult) -> C.ActivityOutput | None:
        artifact = result.artifact_ref
        if type(artifact) is not C.StepArtifactRef:
            return None
        try:
            C.validate_step_artifact_ref(artifact)
            output = C.ActivityOutput(
                schema_version=C.SCHEMA_VERSION,
                status="completed",
                artifact_ref=artifact,
                evidence_ref=result.evidence_ref,
                evidence_digest=result.evidence_digest,
            )
            C.validate_activity_output(output)
        except C.ContractError:
            return None
        return output

    def _replay_outcome(self, record: dict[str, Any]) -> ActivitySeamOutcome:
        stored = record.get("outcome")
        if type(stored) is ActivitySeamOutcome:
            return ActivitySeamOutcome(
                ok=stored.ok,
                op="execute",
                error_code=stored.error_code,
                output=stored.output,
                replayed=True,
                active_run_watch=stored.active_run_watch,
                interrupted=stored.interrupted,
                cleanup_verified=stored.cleanup_verified,
                ambiguous=stored.ambiguous,
                step_status=stored.step_status,
            )
        # Pre-claim only (e.g. a crash before the body resolved): the work is
        # uncertain — reattach and WATCH; never relaunch.
        return ActivitySeamOutcome(
            ok=False,
            op="execute",
            error_code=C.ACTIVE_RUN_CANCELLATION_WATCH,
            output=None,
            replayed=True,
            active_run_watch=True,
            ambiguous=True,
            step_status=C.CANCEL_AMBIGUOUS,
        )

    # ------------------------------------------------------------------ #
    # Query / recover — reattach resident sanitized state, never relaunch
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
        # Reattach by resident claim id; never auto-relaunch uncertain work.
        return self._read_snapshot(run_id, step_id, event="recover", recovered=True)

    def _read_snapshot(self, run_id: str, step_id: str, *, event: str, recovered: bool) -> dict[str, Any]:
        try:
            run_ref = C.safe_ref(_safe_for_scan(run_id))
            step_ref = C.safe_ref(_safe_for_scan(step_id))
        except C.ContractError:
            return self._rejected_snapshot(run_id, step_id, C.RUNTIME_NOT_FOUND, event=f"{event}_rejected")
        key = C.workflow_id_from_refs(run_ref, step_ref)
        with self._lock:
            record = self._claim_store.get(key)
        if record is None:
            self._record(f"{event}_not_found", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_NOT_FOUND)
            return self._snapshot_marker(run_ref, step_ref, "not_found", C.RUNTIME_NOT_FOUND, recovered=recovered)
        state, artifact_refs, error_code = self._resident_state(record.get("outcome"))
        self._record(event, run_ref=run_ref, step_ref=step_ref, error_code=error_code)
        return self._snapshot_marker(
            run_ref, step_ref, state, error_code, recovered=recovered, artifact_refs=artifact_refs
        )

    @staticmethod
    def _resident_state(outcome: Any) -> tuple[str, list[dict[str, Any]], str | None]:
        if type(outcome) is ActivitySeamOutcome and outcome.ok and type(outcome.output) is C.ActivityOutput:
            return "completed", [C.step_artifact_ref_projection(outcome.output.artifact_ref)], None
        if type(outcome) is ActivitySeamOutcome and outcome.error_code is not None:
            code = outcome.error_code if outcome.error_code in C.STABLE_CODES else C.RUNTIME_ERROR
            return "store_invalid", [], code
        # Pre-claim only / no resolved outcome → in-flight; reattach, do not relaunch.
        return "running", [], None

    # ------------------------------------------------------------------ #
    # Cancel — active_run WATCH (no clean-cancel claim for S2)
    # ------------------------------------------------------------------ #
    def cancel(
        self,
        *,
        run_id: str,
        step_id: str,
        scope: str,
        idempotency_key: str,
        interrupt_outcome: Any = None,
    ) -> ActivitySeamOutcome:
        code = self._admission_code()
        if code is not None:
            self._record(
                "cancel_rejected",
                run_ref=self._best_effort_ref(run_id),
                step_ref=self._best_effort_ref(step_id),
                error_code=code,
            )
            return _failure("cancel", code)
        run_ref = self._best_effort_ref(run_id)
        step_ref = self._best_effort_ref(step_id)
        if scope != "active_run":
            self._record("cancel_rejected", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_CANCEL_SCOPE_UNSUPPORTED)
            return _failure("cancel", C.RUNTIME_CANCEL_SCOPE_UNSUPPORTED)
        if self._is_proven_interrupt(interrupt_outcome):
            # The single carve-out: reflect an already-proven interrupted +
            # cleanup_verified lower-layer outcome. The adapter proves nothing itself.
            self._record("cancel_confirmed", run_ref=run_ref, step_ref=step_ref)
            return ActivitySeamOutcome(
                ok=True,
                op="cancel",
                error_code=None,
                output=None,
                interrupted=True,
                cleanup_verified=True,
                step_status="cancelled",
            )
        # WP3b WATCH: never report a clean cancellation we cannot prove.
        self._record("cancel_watch", run_ref=run_ref, step_ref=step_ref, error_code=C.ACTIVE_RUN_CANCELLATION_WATCH)
        return _failure("cancel", C.ACTIVE_RUN_CANCELLATION_WATCH, ambiguous=True, active_run_watch=True)

    @staticmethod
    def _is_proven_interrupt(interrupt_outcome: Any) -> bool:
        return (
            interrupt_outcome is not None
            and getattr(interrupt_outcome, "interrupted", False) is True
            and getattr(interrupt_outcome, "cleanup_verified", False) is True
        )

    # ------------------------------------------------------------------ #
    # Close — sanitized marker
    # ------------------------------------------------------------------ #
    def close(self) -> dict[str, Any]:
        code = self._admission_code()
        if code is not None:
            self._record("close_rejected", error_code=code)
            return {
                "type": _S2_SNAPSHOT_TYPE,
                "state": "store_invalid",
                "snapshot_version": len(self._history),
                "error_code": code,
            }
        # Sanitized close marker only; the caller-owned store is not disconnected.
        self._record("closed")
        return {"type": _S2_SNAPSHOT_TYPE, "state": "closed", "snapshot_version": len(self._history)}

    # ------------------------------------------------------------------ #
    # Sanitized local history projection (SCAN 1 / SCAN 2 surfaces)
    # ------------------------------------------------------------------ #
    def history_projection(self) -> dict[str, Any]:
        with self._lock:
            return {
                "type": _S2_HISTORY_TYPE,
                "snapshot_version": len(self._history),
                "events": [dict(event) for event in self._history],
            }

    def serialized_history_bytes(self) -> bytes:
        return C.canonical_json_bytes(self.history_projection())

    # ------------------------------------------------------------------ #
    # Snapshot / history helpers
    # ------------------------------------------------------------------ #
    def _snapshot_marker(
        self,
        run_ref: str,
        step_ref: str,
        state: str,
        error_code: str | None,
        *,
        recovered: bool = False,
        artifact_refs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        marker: dict[str, Any] = {
            "type": _S2_SNAPSHOT_TYPE,
            "run_ref": run_ref,
            "step_ref": step_ref,
            "state": state,
            "snapshot_version": len(self._history),
            "artifact_refs": artifact_refs if artifact_refs is not None else [],
            "error_code": error_code,
        }
        if recovered:
            marker["recovery_marker"] = _RECOVERY_MARKER
        if C.scan_projection_for_leak(marker) is not None:
            return {
                "type": _S2_SNAPSHOT_TYPE,
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

    @staticmethod
    def _best_effort_ref(value: Any) -> str:
        try:
            return C.safe_ref(_safe_for_scan(value))
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
    "S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN",
    "SupervisorSeam",
    "SupervisorStepResult",
    "ActivitySeamOutcome",
    "FakeDeterministicSupervisorSeam",
    "S2LocalOfflineSupervisorAdapter",
]
