"""Deterministic P5 Temporal Slice 1 workflow (FR3, Gate C).

``StepWorkflow`` keeps workflow code **deterministic and replay-safe**: it
performs no file / network / subprocess / Gateway / Temporal-client operations,
uses no wall-clock or randomness, and consumes **only** the sanitized
``contracts`` types — it never imports WP4 / ``ai_flow_executor`` internals. All
non-determinism (the controlled-deterministic step body) lives in the activity.

Updates are pinned to the Slice 1 set ``{resume, request_cancel}`` with event-key
idempotency; delivery / approval / rejection are deferred (P6 / Gateway / real
delivery). The contracts module is imported through Temporal's
``imports_passed_through`` so the deterministic trust boundary is shared with the
host instead of sandbox-reloaded.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from . import contracts as C

UPDATE_RESULT_TYPE = "sachima.supervisor.p5_temporal_update_result.v1"
_ACTIVITY_START_TO_CLOSE = timedelta(seconds=30)


@workflow.defn
class StepWorkflow:
    """Deterministic durable state for one controlled AI FLOW step."""

    def __init__(self) -> None:
        self._start_request: C.StartRequest | None = None
        self._state = "created"
        self._snapshot_version = 0
        self._artifact_refs: tuple[dict[str, Any], ...] = ()
        self._applied_event_keys: dict[str, tuple[str, ...]] = {}
        self._resume_count = 0
        self._cancel_requested = False
        self._active_run_watch = False
        self._terminal = False

    @workflow.run
    async def run(self, start_request: C.StartRequest) -> dict[str, Any]:
        # Initialized fully before the first await, so queries between awaits
        # always see a sanitized snapshot.
        C.validate_start_request(start_request)
        self._start_request = start_request
        self._state = "running"
        self._snapshot_version = 1

        activity_input = C.build_activity_input(start_request)
        output = await workflow.execute_activity(
            "p5_step_activity",
            activity_input,
            start_to_close_timeout=_ACTIVITY_START_TO_CLOSE,
            result_type=C.ActivityOutput,
        )
        C.validate_activity_output(output)

        self._artifact_refs = (C.step_artifact_ref_projection(output.artifact_ref),)
        self._state = "completed"
        self._snapshot_version += 1

        # Stay open so the orchestrator can query / resume / request_cancel the
        # step. Terminalization is caller-owned and cooperative — there is NO
        # wall-clock auto-terminate (deterministic; nothing for the test server to
        # time-skip), so the work-done snapshot is observed via query.
        await workflow.wait_condition(lambda: self._terminal)
        self._state = "cancelled" if self._cancel_requested else "closed"
        self._snapshot_version += 1
        return self._snapshot()

    # ------------------------------------------------------------------ #
    # Query — sanitized snapshot
    # ------------------------------------------------------------------ #
    @workflow.query
    def snapshot(self) -> dict[str, Any]:
        return self._snapshot()

    # ------------------------------------------------------------------ #
    # Pinned Slice 1 updates — {resume, request_cancel}, event-key idempotent
    # ------------------------------------------------------------------ #
    @workflow.update
    async def resume(self, payload: C.UpdatePayload) -> dict[str, Any]:
        event_key = ("resume", payload.event_key, payload.ref or "")
        if self._applied_event_keys.get(payload.event_key) == event_key:
            return self._update_result("duplicate")
        self._applied_event_keys[payload.event_key] = event_key
        self._resume_count += 1
        return self._update_result("applied")

    @resume.validator
    def _validate_resume(self, payload: C.UpdatePayload) -> None:
        C.validate_update_payload(payload)
        if payload.event_type != "resume":
            raise ValueError("invalid_update_event_type")
        self._reject_event_key_divergence(payload, ("resume", payload.event_key, payload.ref or ""))

    @workflow.update
    async def request_cancel(self, payload: C.UpdatePayload) -> dict[str, Any]:
        event_key = ("request_cancel", payload.event_key)
        if self._applied_event_keys.get(payload.event_key) == event_key:
            return self._update_result("duplicate")
        self._applied_event_keys[payload.event_key] = event_key
        # Cooperative cancellation request: mark the WATCH and terminalize; never
        # claim a clean cancellation from the workflow itself (proof lives outside
        # the workflow — the executor preserves the WP3b WATCH).
        self._cancel_requested = True
        self._active_run_watch = True
        self._terminal = True
        return self._update_result("applied")

    @request_cancel.validator
    def _validate_request_cancel(self, payload: C.UpdatePayload) -> None:
        C.validate_update_payload(payload)
        if payload.event_type != "request_cancel":
            raise ValueError("invalid_update_event_type")
        self._reject_event_key_divergence(payload, ("request_cancel", payload.event_key))

    # ------------------------------------------------------------------ #
    # Helpers (deterministic, pure)
    # ------------------------------------------------------------------ #
    def _reject_event_key_divergence(self, payload: C.UpdatePayload, event_key: tuple[str, ...]) -> None:
        existing = self._applied_event_keys.get(payload.event_key)
        if existing is not None and existing != event_key:
            raise ValueError("invalid_update_event_key")

    def _snapshot(self) -> dict[str, Any]:
        if self._start_request is None:
            # Before run() initialization — return a minimal sanitized marker.
            return {"type": C.SNAPSHOT_TYPE, "schema_version": C.SCHEMA_VERSION, "state": "created"}
        return C.build_query_snapshot(
            start_request=self._start_request,
            state=self._state,
            snapshot_version=self._snapshot_version,
            artifact_refs=self._artifact_refs,
            active_run_watch=self._active_run_watch,
            applied_event_count=len(self._applied_event_keys),
            resume_count=self._resume_count,
        )

    def _update_result(self, update_status: str) -> dict[str, Any]:
        return {
            "type": UPDATE_RESULT_TYPE,
            "update_status": update_status,
            "snapshot": self._snapshot(),
        }


__all__ = ["StepWorkflow", "UPDATE_RESULT_TYPE"]
