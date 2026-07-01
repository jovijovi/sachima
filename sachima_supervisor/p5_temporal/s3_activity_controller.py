"""S3 — hermetic-local Temporal Activity body + caller-owned controller.

This module implements stage S3 of the Sachima agent-run-supervisor ↔ Temporal
integration as fixed by the S3 design packet
(``docs/plans/2026-06-30-sachima-s3-activity-controller-design-packet.md``): the
async Temporal **Activity body** that wraps the already-merged S2 local/offline
supervisor-adapter seam, and the caller-owned **controller** that drives
start / query / update / recover / retry / close against a no-throw control
surface.

It is pure, local/offline Python. Importing or calling it starts no Temporal
runtime / Worker / service / subprocess, constructs no Temporal client or agent
runner, opens no network connection, spawns no child process, and reaches no
Gateway / Feishu / live / delivery surface. The step body is the injected-fake S2
adapter only (``S2LocalOfflineSupervisorAdapter`` over an injected
``SupervisorSeam``); there is no real agent, no ``acpx``, and no ``npx``.

Contract (grounded in the design packet §3–§9):

  * **Activity body (the single fallible seam).** ``S3SupervisorActivityBody.run``
    is an async Activity-compatible body. It has its **own** default-off admission
    (``enabled is True`` + the exact S3 token) that fails closed with **zero**
    adapter / seam calls; an admitted body calls ``adapter.execute`` exactly once,
    returns the adapter's sanitized ``ActivityOutput`` on success, and otherwise
    raises a **bare stable code** — never raw input, exception text, repr, a
    traceback, a platform id, or any prompt / context / tool output.
  * **Controller (caller-owned, never the Gateway).** Maps a caller-owned
    ``intent_class`` through a *closed* read-only-role allowlist; unknown /
    arbitrary / platform-derived / write-ish intents fail closed **before** any
    control-surface / runtime call. ``start`` builds exactly one sanitized
    ``StartRequest`` + the deterministic ``p5wf_<48 hex>`` workflow id; ``query`` /
    ``recover`` / ``close`` are no-throw sanitized envelopes; ``update`` is pinned
    to ``{resume, request_cancel}`` and rejects delivery / approve / reject before
    the surface; ``retry`` re-enters ``start`` on the same deterministic id so a
    duplicate reconciles / replays and never relaunches.
"""

from __future__ import annotations

import inspect
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from . import contracts as C
from .activities import P5_STEP_ACTIVITY_NAME
from .s2_supervisor_adapter import ActivitySeamOutcome, S2LocalOfflineSupervisorAdapter

# --------------------------------------------------------------------------- #
# Exact S3 activity-body implementation approval token. Distinct from the S2
# seam token (sanity-pinned by the contract tests) and likewise encoding the
# in-force non-approvals so an accidental enable cannot widen scope: default-off,
# injected-fake deterministic body only, wrapping the merged S2 seam, no Temporal
# Worker / service / runtime / subprocess start, no real agent / runner execution,
# no write roles, no default-on, no public ingress, no external messaging surface,
# no production config, no real delivery.
# --------------------------------------------------------------------------- #
S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_s3_hermetic_local_temporal_activity_body_and_caller_owned_controller_"
    "implementation_default_off_injected_fake_deterministic_step_body_only_wrapping_merged_s2_local_offline_adapter_seam_"
    "no_temporal_worker_or_service_or_runtime_or_subprocess_start_no_real_agent_or_runner_execution_"
    "no_write_roles_no_default_on_no_public_ingress_no_external_messaging_surface_"
    "no_production_config_no_real_delivery"
)

# --------------------------------------------------------------------------- #
# Intent class → read-only role key (closed allowlist, fail closed off-list).
#
# Mirrors the merged Sachima step→artifact-kind read-only taxonomy
# (architect → architecture_packet, programmer_candidate →
# implementation_candidate_analysis, reviewer → blocker_review). Each value is a
# bare read-only role *key ref* — never a role definition and never a runtime
# authorization decision — and each passes ``contracts._safe_role_key`` (bare-id
# shape, no forbidden marker, no write/deliver/approve/reject/mutate marker).
# There is no default role, no permissive fallback, and no caller-supplied role.
# --------------------------------------------------------------------------- #
INTENT_CLASS_TO_ROLE_KEY: dict[str, str] = {
    "architecture_packet": "sachima_claude_read_only_architect",
    "programmer_candidate_review": "sachima_claude_read_only_programmer_candidate",
    "blocker_review": "sachima_codex_read_only_reviewer",
}


def _reject(op: str, code: str, *, workflow_id: str | None = None) -> dict[str, Any]:
    """Sanitized fail-closed envelope carrying only a stable code (no raw echo)."""

    safe_code = code if code in C.STABLE_CODES else C.INVALID_START_PAYLOAD
    return {
        "ok": False,
        "op": op,
        "workflow_id": workflow_id,
        "snapshot": None,
        "error_code": safe_code,
        "replayed": False,
    }


_RETRYABLE_ACTIVITY_ERROR_CODES = frozenset({C.RUNTIME_ERROR})


def _activity_failure(code: str) -> ApplicationError:
    """Temporal Activity failure carrying only a bare stable code.

    Deterministic fail-closed codes stay non-retryable. A transient
    ``runtime_error`` is retryable so an Activity retry can re-enter the resident
    claim and reconcile without relaunching real work.
    """

    safe_code = code if code in C.STABLE_CODES else C.RUNTIME_ERROR
    non_retryable = safe_code not in _RETRYABLE_ACTIVITY_ERROR_CODES
    return ApplicationError(safe_code, type=safe_code, non_retryable=non_retryable)


# --------------------------------------------------------------------------- #
# Async Activity body — wraps the merged S2 adapter (the only fallible seam)
# --------------------------------------------------------------------------- #
class S3SupervisorActivityBody:
    """Async Activity-compatible body wrapping ``S2LocalOfflineSupervisorAdapter``.

    The body owns its own default-off admission gate (independent of the adapter's
    gate) so a flag-off / token-mismatched body makes **zero** adapter / seam calls
    and fails closed with a stable code. An admitted body delegates to
    ``adapter.execute`` exactly once and returns the adapter's sanitized
    ``ActivityOutput`` on success; any failure becomes a bare stable code.
    """

    def __init__(self, *, adapter: Any, enabled: bool = False, approval_token: str = "") -> None:
        self._adapter = adapter
        self.enabled = enabled
        self.approval_token = approval_token

    # ------------------------------------------------------------------ #
    # Admission (default-off) — zero adapter/seam call when not admitted
    # ------------------------------------------------------------------ #
    def _admission_code(self) -> str | None:
        if self.enabled is not True:
            return C.RUNTIME_DISABLED
        if self.approval_token != S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN:
            return C.RUNTIME_APPROVAL_MISMATCH
        if self._adapter is None or type(self._adapter) is not S2LocalOfflineSupervisorAdapter:
            return C.RUNTIME_PRECONDITION_UNMET
        if not callable(getattr(self._adapter, "execute", None)):
            return C.RUNTIME_PRECONDITION_UNMET
        return None

    # ------------------------------------------------------------------ #
    # Activity body — async, single sanitized input, output or stable code
    # ------------------------------------------------------------------ #
    @activity.defn(name=P5_STEP_ACTIVITY_NAME)
    async def run(self, activity_input: Any) -> C.ActivityOutput:
        """Run the controlled-deterministic step body through the S2 adapter.

        Returns the adapter's sanitized ``ActivityOutput`` on success. On any
        admission / validation / seam failure it raises non-retryable Temporal
        ``ApplicationError`` typed with a bare stable code, so a failed activity
        carries a stable code into Temporal history — never raw material.
        """

        admission = self._admission_code()
        if admission is not None:
            # Not admitted → never touch the adapter (and therefore the seam).
            raise _activity_failure(admission)
        result = self._invoke_adapter(activity_input)
        if type(result) is C.ActivityOutput:
            return result
        code = result if isinstance(result, str) else C.RUNTIME_ERROR
        raise _activity_failure(code)

    def _invoke_adapter(self, activity_input: Any) -> C.ActivityOutput | str:
        try:
            outcome = self._adapter.execute(activity_input)
        except BaseException:  # noqa: BLE001 - no-throw toward history; never echo the exception
            # The merged adapter is no-throw by contract; collapse any unexpected
            # raw-looking exception to a stable code without referencing it.
            return C.RUNTIME_ERROR
        if type(outcome) is not ActivitySeamOutcome:
            return C.RUNTIME_ERROR
        if outcome.ok and type(outcome.output) is C.ActivityOutput:
            return _validated_output_or_code(outcome.output)
        return outcome.error_code if outcome.error_code in C.STABLE_CODES else C.RUNTIME_ERROR


def _validated_output_or_code(output: C.ActivityOutput) -> C.ActivityOutput | str:
    """Validate + SCAN the exact ActivityOutput before it enters history."""

    try:
        projection = _activity_output_projection(output)
        if C.scan_projection_for_leak(projection) is not None:
            return C.RUNTIME_HISTORY_LEAK_DETECTED
        C.validate_activity_output(output)
    except C.ContractError as exc:
        return exc.code if exc.code in C.STABLE_CODES else C.INVALID_START_PAYLOAD
    except BaseException:  # noqa: BLE001 - fail closed without raw details
        return C.RUNTIME_ERROR
    return output


def _activity_output_projection(output: C.ActivityOutput) -> dict[str, Any]:
    artifact = output.artifact_ref
    artifact_projection: dict[str, Any]
    if type(artifact) is C.StepArtifactRef:
        artifact_projection = C.step_artifact_ref_projection(artifact)
    else:
        artifact_projection = {"error_code": C.INVALID_START_PAYLOAD}
    return {
        "schema_version": output.schema_version,
        "status": output.status,
        "artifact_ref": artifact_projection,
        "evidence_ref": output.evidence_ref,
        "evidence_digest": output.evidence_digest,
    }


# --------------------------------------------------------------------------- #
# Caller-owned controller — drives the durable workflow via the control surface
# --------------------------------------------------------------------------- #
class S3TemporalActivityController:
    """Caller-owned controller over a no-throw control surface.

    Resolves a business ``intent_class`` to a read-only role key from the closed
    allowlist (fail closed off-list), builds the sanitized ``StartRequest`` and the
    deterministic workflow id, and drives start / query / update / recover / retry
    / close against the injected control surface. It owns the business intent and
    the role-key resolution only; it is **not** the Gateway, owns no Worker /
    task-queue / runtime lifecycle, and persists no raw material. Every method
    returns a sanitized envelope and never raises.
    """

    def __init__(self, *, control_surface: Any) -> None:
        self._control_surface = control_surface

    # ------------------------------------------------------------------ #
    # start / retry — build one sanitized StartRequest + deterministic id
    # ------------------------------------------------------------------ #
    async def start(
        self,
        *,
        intent_class: Any,
        run_ref: Any,
        workflow_ref: Any,
        step_ref: Any,
        attempt_index: Any,
        input_claim_refs: Any,
        idempotency_material: Any,
        lease_id: Any = None,
        lease_epoch: Any = 0,
    ) -> dict[str, Any]:
        try:
            role_key = _resolve_role_key(intent_class)
            start_request = C.build_start_request(
                run_ref=run_ref,
                workflow_ref=workflow_ref,
                step_ref=step_ref,
                attempt_index=attempt_index,
                role_keys=(role_key,),
                input_claim_refs=input_claim_refs,
                idempotency_material=idempotency_material,
                lease_id=lease_id,
                lease_epoch=lease_epoch,
            )
            workflow_id = C.deterministic_workflow_id(start_request)
        except C.ContractError as exc:
            # Role resolution / payload sanitization fails closed BEFORE any
            # control-surface or runtime call; the envelope never echoes the raw
            # / platform / write intent material.
            return _reject("start", exc.code)
        return await self._call_surface("start", "start", start_request, workflow_id=workflow_id)

    async def retry(self, *, intent_class: Any, **start_kwargs: Any) -> dict[str, Any]:
        # A retry re-enters start on the same deterministic (run_ref, step_ref) id;
        # the runtime's reject-duplicate start policy reconciles / replays the
        # resident outcome and never relaunches the work.
        return await self.start(intent_class=intent_class, **start_kwargs)

    # ------------------------------------------------------------------ #
    # query / recover — no-throw sanitized snapshots (reattach, no relaunch)
    # ------------------------------------------------------------------ #
    async def query(self, *, run_ref: Any, step_ref: Any) -> dict[str, Any]:
        try:
            workflow_id = _workflow_id(run_ref, step_ref)
        except C.ContractError as exc:
            return _reject("query", exc.code)
        return await self._call_surface("query", "query", workflow_id=workflow_id)

    async def recover(self, *, run_ref: Any, step_ref: Any) -> dict[str, Any]:
        try:
            workflow_id = _workflow_id(run_ref, step_ref)
        except C.ContractError as exc:
            return _reject("recover", exc.code)
        return await self._call_surface("recover", "recover", workflow_id=workflow_id)

    # ------------------------------------------------------------------ #
    # update — pinned to {resume, request_cancel}; reject delivery/approve/reject
    # ------------------------------------------------------------------ #
    async def update(
        self, *, run_ref: Any, step_ref: Any, event_key: Any, event_type: Any, ref: Any = None
    ) -> dict[str, Any]:
        try:
            workflow_id = _workflow_id(run_ref, step_ref)
            # build_update_payload accepts only the Slice 1 set; delivery / approve
            # / reject (and any malformed type) fail closed here, before the surface.
            payload = C.build_update_payload(event_key=event_key, event_type=event_type, ref=ref)
        except C.ContractError as exc:
            return _reject("update", exc.code)
        return await self._call_surface("update", "update", workflow_id=workflow_id, update=payload)

    # ------------------------------------------------------------------ #
    # close — sanitized marker; owns no Worker/runtime lifecycle
    # ------------------------------------------------------------------ #
    async def close(self) -> dict[str, Any]:
        return await self._call_surface("close", "close")

    # ------------------------------------------------------------------ #
    # No-throw surface guard + final SCAN-1 leak guard over the envelope
    # ------------------------------------------------------------------ #
    async def _call_surface(self, op: str, method_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            if self._control_surface is None:
                return _reject(op, C.RUNTIME_ERROR)
            method = getattr(self._control_surface, method_name, None)
            if not callable(method):
                return _reject(op, C.RUNTIME_ERROR)
            result = method(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
        except BaseException:  # noqa: BLE001 - controller is no-throw by contract
            return _reject(op, C.RUNTIME_ERROR)
        if not isinstance(result, dict):
            return _reject(op, C.RUNTIME_ERROR)
        if C.scan_projection_for_leak(result) is not None:
            return _reject(op, C.RUNTIME_HISTORY_LEAK_DETECTED)
        return result


# --------------------------------------------------------------------------- #
# Role / id helpers (fail closed before any control-surface call)
# --------------------------------------------------------------------------- #
def _resolve_role_key(intent_class: Any) -> str:
    """Resolve a caller-owned intent class to an allowlisted read-only role key.

    The mapping is a closed set: a known intent class resolves to exactly one
    committed read-only role key, or it fails closed. Platform-derived / raw intent
    material (a denylisted marker) maps to ``runtime_unsafe_material``; any other
    off-list / non-string intent to ``invalid_start_payload``. No default role, no
    permissive fallback, no caller-supplied role definition.
    """

    if isinstance(intent_class, str):
        role_key = INTENT_CLASS_TO_ROLE_KEY.get(intent_class)
        if role_key is not None:
            return role_key
        if C.scan_projection_for_leak({"intent_class": intent_class}) is not None:
            raise C.ContractError(C.RUNTIME_UNSAFE_MATERIAL)
    raise C.ContractError(C.INVALID_START_PAYLOAD)


def _workflow_id(run_ref: Any, step_ref: Any) -> str:
    """Deterministic ``p5wf_<48 hex>`` id from sanitized refs (rejects raw material).

    ``workflow_id_from_refs`` validates ``run_ref`` / ``step_ref`` as bare safe ids,
    so a raw path / URL / platform id fails closed here before any handle lookup.
    """

    return C.workflow_id_from_refs(run_ref, step_ref)


__all__ = [
    "S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN",
    "INTENT_CLASS_TO_ROLE_KEY",
    "S3SupervisorActivityBody",
    "S3TemporalActivityController",
]
