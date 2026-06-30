"""Caller-supplied Temporal client boundary (FR4, Gate D).

``P5TemporalRuntimeClient`` wraps a **caller-supplied connected**
``temporalio.client.Client``. It owns **no** lifecycle: it never calls
``Client.connect(...)``, never starts a subprocess / server / socket / Worker,
and never closes the caller's client. It maps duplicate-start / recovery / query
/ update / cancel / close to **no-throw sanitized** result envelopes, fails
closed on divergent duplicates, reattaches recovery by workflow id without ever
auto-relaunching uncertain work, and exposes the **real** serialized
event-history bytes for SCAN 2.

The same class runs against a hermetic ``WorkflowEnvironment`` client and against
an in-memory fake in unit tests — the only difference is the injected client.
"""

from __future__ import annotations

import asyncio
from typing import Any

from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from . import contracts as C
from .workflow import StepWorkflow

#: No-double-launch start policies (FR4). ``REJECT_DUPLICATE`` rejects a start
#: whose deterministic workflow id already has a *closed/terminal* run (instead of
#: the SDK default ``ALLOW_DUPLICATE``, which would create a brand-new execution),
#: and ``FAIL`` rejects a start whose id has a *running* run. Both surface as
#: ``WorkflowAlreadyStartedError`` so a same-id start always enters duplicate
#: reconciliation here rather than ever relaunching the work.
_NO_RELAUNCH_ID_REUSE_POLICY = WorkflowIDReusePolicy.REJECT_DUPLICATE
_NO_RELAUNCH_ID_CONFLICT_POLICY = WorkflowIDConflictPolicy.FAIL

#: States in which the controlled-deterministic step body has finished running.
_WORK_DONE_STATES = frozenset({"completed", "cancelled", "closed", "failed"})

#: Pinned Slice 1 update routing — exactly ``{resume, request_cancel}`` map to the
#: deterministic ``StepWorkflow`` update handlers. Any other (delivery / approval /
#: rejection / malformed) event type is rejected before any client call.
_UPDATE_FN_BY_EVENT_TYPE = {
    "resume": StepWorkflow.resume,
    "request_cancel": StepWorkflow.request_cancel,
}

# Query paths must not block on a workflow that intentionally stays open after
# completing its step body. A query failure may still inspect a terminal/closed
# result, but only with a short bound so open workflows fail closed instead of
# hanging the runtime boundary.
_QUERY_TIMEOUT_SECONDS = 1.0
_RESULT_FALLBACK_TIMEOUT_SECONDS = 1.0


def _ok(op: str, *, workflow_id: str | None = None, snapshot: Any = None, replayed: bool = False) -> dict[str, Any]:
    return {
        "ok": True,
        "op": op,
        "workflow_id": workflow_id,
        "snapshot": snapshot,
        "error_code": None,
        "replayed": replayed,
    }


def _err(op: str, code: str, *, workflow_id: str | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "op": op,
        "workflow_id": workflow_id,
        "snapshot": None,
        "error_code": code,
        "replayed": False,
    }


def _is_already_started(exc: BaseException) -> bool:
    return exc.__class__.__name__ == "WorkflowAlreadyStartedError"


class P5TemporalRuntimeClient:
    """No-throw sanitized facade over a caller-supplied connected Temporal client."""

    def __init__(self, temporal_client: Any, *, task_queue: str = C.P5_TEMPORAL_TASK_QUEUE) -> None:
        if temporal_client is None:
            raise C.ContractError(C.RUNTIME_PRECONDITION_UNMET)
        self._client = temporal_client
        self._task_queue = task_queue

    # ------------------------------------------------------------------ #
    # Start + duplicate-start reconciliation (FR4)
    # ------------------------------------------------------------------ #
    async def start(self, start_request: Any, *, workflow_id: str) -> dict[str, Any]:
        try:
            C.validate_start_request(start_request)
            workflow_id = C.workflow_id_for_start_request(start_request, supplied=workflow_id)
        except C.ContractError as exc:
            return _err("start", _stable(exc.code, C.INVALID_START_PAYLOAD))
        try:
            handle = await self._client.start_workflow(
                StepWorkflow.run,
                start_request,
                id=workflow_id,
                task_queue=self._task_queue,
                id_reuse_policy=_NO_RELAUNCH_ID_REUSE_POLICY,
                id_conflict_policy=_NO_RELAUNCH_ID_CONFLICT_POLICY,
            )
        except BaseException as exc:  # noqa: BLE001 - boundary maps every failure to a code
            if _is_already_started(exc):
                return await self._reconcile_duplicate(start_request, workflow_id=workflow_id)
            return _err("start", C.RUNTIME_ERROR, workflow_id=workflow_id)
        # The workflow stays open after the step work to remain controllable; read
        # the work-done snapshot by query rather than blocking on full completion.
        safe = await self._await_work_done(handle)
        if safe is None:
            return _err("start", C.RUNTIME_ERROR, workflow_id=workflow_id)
        return _ok("start", workflow_id=getattr(handle, "id", workflow_id), snapshot=safe)

    async def _await_work_done(self, handle: Any, *, attempts: int = 250) -> dict[str, Any] | None:
        last: dict[str, Any] | None = None
        for index in range(attempts):
            try:
                snapshot = await handle.query(StepWorkflow.snapshot)
            except BaseException:  # noqa: BLE001
                snapshot = None
            safe = self._sanitize(snapshot) if snapshot is not None else None
            if safe is not None:
                last = safe
                if safe.get("state") in _WORK_DONE_STATES:
                    return safe
            await asyncio.sleep(0.02)
        return last

    async def _reconcile_duplicate(self, start_request: Any, *, workflow_id: str) -> dict[str, Any]:
        # Query first: StepWorkflow intentionally stays open after the step body
        # completes, so awaiting handle.result() here would block until terminal
        # closure. Reconcile from the work-done query snapshot and return a no-throw
        # replay / conflict without waiting for the workflow to close (Gate D).
        snapshot = await self._read_snapshot(workflow_id, prefer_query=True)
        if snapshot is None:
            return _err("start", C.RUNTIME_ERROR, workflow_id=workflow_id)
        safe = self._sanitize(snapshot)
        if safe is None:
            return _err("start", C.RUNTIME_HISTORY_LEAK_DETECTED, workflow_id=workflow_id)
        # Divergence is detected by comparing the sanitized canonical payload —
        # the public digest is evidence, not a trust boundary. Identical → replay.
        if not _snapshot_matches_start(safe, start_request):
            return _err("start", C.RUNTIME_IDEMPOTENCY_CONFLICT, workflow_id=workflow_id)
        return _ok("start", workflow_id=workflow_id, snapshot=safe, replayed=True)

    # ------------------------------------------------------------------ #
    # Query / recover / cancel / close (all no-throw)
    # ------------------------------------------------------------------ #
    async def query(self, *, workflow_id: str) -> dict[str, Any]:
        try:
            workflow_id = C.validate_workflow_id(workflow_id)
        except C.ContractError as exc:
            return _err("query", _stable(exc.code, C.INVALID_START_PAYLOAD))
        snapshot = await self._read_snapshot(workflow_id, prefer_query=True)
        if snapshot is None:
            return _err("query", C.RUNTIME_NOT_FOUND, workflow_id=workflow_id)
        safe = self._sanitize(snapshot)
        if safe is None:
            return _err("query", C.RUNTIME_HISTORY_LEAK_DETECTED, workflow_id=workflow_id)
        return _ok("query", workflow_id=workflow_id, snapshot=safe)

    async def recover(self, *, workflow_id: str) -> dict[str, Any]:
        # Reattach by workflow id only; never auto-relaunch uncertain work.
        try:
            workflow_id = C.validate_workflow_id(workflow_id)
        except C.ContractError as exc:
            return _err("recover", _stable(exc.code, C.INVALID_START_PAYLOAD))
        snapshot = await self._read_snapshot(workflow_id, prefer_query=True)
        if snapshot is None:
            return _err("recover", C.RUNTIME_NOT_FOUND, workflow_id=workflow_id)
        safe = self._sanitize(snapshot)
        if safe is None:
            return _err("recover", C.RUNTIME_HISTORY_LEAK_DETECTED, workflow_id=workflow_id)
        return _ok("recover", workflow_id=workflow_id, snapshot=safe)

    async def signal_cancel(self, *, workflow_id: str, update: Any) -> dict[str, Any]:
        try:
            workflow_id = C.validate_workflow_id(workflow_id)
        except C.ContractError as exc:
            return _err("cancel", _stable(exc.code, C.INVALID_START_PAYLOAD))
        try:
            C.validate_update_payload(update)
        except C.ContractError as exc:
            return _err("cancel", _stable(exc.code, C.INVALID_START_PAYLOAD), workflow_id=workflow_id)
        if update.event_type != "request_cancel":
            return _err("cancel", C.INVALID_START_PAYLOAD, workflow_id=workflow_id)
        try:
            handle = self._client.get_workflow_handle(workflow_id)
            result = await handle.execute_update(StepWorkflow.request_cancel, update)
        except BaseException:  # noqa: BLE001 - cooperative cancel is best-effort, no-throw
            # The run may already be terminal; the executor preserves the WATCH.
            return _err("cancel", C.ACTIVE_RUN_CANCELLATION_WATCH, workflow_id=workflow_id)
        safe = self._sanitize(_extract_snapshot(result))
        if safe is None:
            return _err("cancel", C.RUNTIME_HISTORY_LEAK_DETECTED, workflow_id=workflow_id)
        return _ok("cancel", workflow_id=workflow_id, snapshot=safe)

    async def update(self, *, workflow_id: str, update: Any) -> dict[str, Any]:
        """No-throw pinned update — route ``{resume, request_cancel}`` to the workflow.

        Generic counterpart to ``signal_cancel`` (which stays request_cancel-only
        for compatibility). A malformed or off-list payload (incl. delivery /
        approval / rejection) fails closed before any client call; an
        ``execute_update`` failure collapses to a stable code without echoing the
        exception — ``request_cancel`` keeps the WP3b WATCH, ``resume`` maps to
        ``runtime_error``. Owns no Worker / task-queue lifecycle.
        """

        try:
            workflow_id = C.validate_workflow_id(workflow_id)
        except C.ContractError as exc:
            return _err("update", _stable(exc.code, C.INVALID_START_PAYLOAD))
        try:
            C.validate_update_payload(update)
        except C.ContractError as exc:
            return _err("update", _stable(exc.code, C.INVALID_START_PAYLOAD), workflow_id=workflow_id)
        update_fn = _UPDATE_FN_BY_EVENT_TYPE.get(update.event_type)
        if update_fn is None:
            return _err("update", C.INVALID_START_PAYLOAD, workflow_id=workflow_id)
        try:
            handle = self._client.get_workflow_handle(workflow_id)
            result = await handle.execute_update(update_fn, update)
        except BaseException:  # noqa: BLE001 - cooperative update is best-effort, no-throw
            code = C.ACTIVE_RUN_CANCELLATION_WATCH if update.event_type == "request_cancel" else C.RUNTIME_ERROR
            return _err("update", code, workflow_id=workflow_id)
        safe = self._sanitize(_extract_snapshot(result))
        if safe is None:
            return _err("update", C.RUNTIME_HISTORY_LEAK_DETECTED, workflow_id=workflow_id)
        return _ok("update", workflow_id=workflow_id, snapshot=safe)

    async def close(self) -> dict[str, Any]:
        # No hidden lifecycle: the caller owns the Temporal client; close is only a
        # sanitized marker and never disconnects/stops the caller-supplied client.
        return _ok("close", snapshot={"type": C.SNAPSHOT_TYPE, "state": "closed"})

    # ------------------------------------------------------------------ #
    # SCAN 2 — real serialized event-history bytes
    # ------------------------------------------------------------------ #
    async def serialized_event_history_bytes(self, *, workflow_id: str) -> bytes:
        import temporalio.api.history.v1

        workflow_id = C.validate_workflow_id(workflow_id)
        handle = self._client.get_workflow_handle(workflow_id)
        history = await handle.fetch_history()
        proto = temporalio.api.history.v1.History(events=history.events)
        return proto.SerializeToString()

    async def event_history_json(self, *, workflow_id: str) -> dict[str, Any]:
        workflow_id = C.validate_workflow_id(workflow_id)
        handle = self._client.get_workflow_handle(workflow_id)
        history = await handle.fetch_history()
        return history.to_json_dict()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    async def _read_snapshot(self, workflow_id: str, *, prefer_query: bool = False) -> Any:
        try:
            workflow_id = C.validate_workflow_id(workflow_id)
        except C.ContractError:
            return None
        handle = self._client.get_workflow_handle(workflow_id)
        if prefer_query:
            try:
                return await asyncio.wait_for(
                    handle.query(StepWorkflow.snapshot), timeout=_QUERY_TIMEOUT_SECONDS
                )
            except BaseException:  # noqa: BLE001
                pass
        # Completed workflows expose their final snapshot as the run result.
        try:
            timeout = _RESULT_FALLBACK_TIMEOUT_SECONDS if prefer_query else _QUERY_TIMEOUT_SECONDS
            return await asyncio.wait_for(handle.result(), timeout=timeout)
        except BaseException:  # noqa: BLE001
            pass
        if not prefer_query:
            try:
                return await asyncio.wait_for(
                    handle.query(StepWorkflow.snapshot), timeout=_QUERY_TIMEOUT_SECONDS
                )
            except BaseException:  # noqa: BLE001
                return None
        return None

    def _sanitize(self, snapshot: Any) -> dict[str, Any] | None:
        if not isinstance(snapshot, dict):
            return None
        if not set(snapshot).issubset(C.ALLOWED_SNAPSHOT_KEYS):
            return None
        if C.scan_projection_for_leak(snapshot) is not None:
            return None
        return snapshot


def _stable(code: str | None, default: str) -> str:
    return code if code in C.STABLE_CODES else default


def _extract_snapshot(update_result: Any) -> Any:
    if isinstance(update_result, dict) and isinstance(update_result.get("snapshot"), dict):
        return update_result["snapshot"]
    return update_result


def _snapshot_matches_start(snapshot: dict[str, Any], start_request: C.StartRequest) -> bool:
    if snapshot.get("schema_version") != start_request.schema_version:
        return False
    if snapshot.get("mode") != start_request.mode:
        return False
    if snapshot.get("run_ref") != start_request.run_ref:
        return False
    if snapshot.get("workflow_ref") != start_request.workflow_ref:
        return False
    if snapshot.get("step_ref") != start_request.step_ref:
        return False
    if snapshot.get("attempt_index") != start_request.attempt_index:
        return False
    if snapshot.get("idempotency_material") != start_request.idempotency_material:
        return False
    if tuple(snapshot.get("role_keys", ())) != tuple(start_request.role_keys):
        return False
    return _input_refs_match(snapshot.get("input_claim_refs", ()), start_request.input_claim_refs)


def _input_refs_match(snapshot_refs: Any, request_refs: tuple[C.ClaimCheckRef, ...]) -> bool:
    if not isinstance(snapshot_refs, (list, tuple)) or len(snapshot_refs) != len(request_refs):
        return False
    for observed, expected in zip(snapshot_refs, request_refs):
        if not isinstance(observed, dict):
            return False
        if (
            observed.get("ref") != expected.ref
            or observed.get("digest") != expected.digest
            or observed.get("kind") != expected.kind
            or observed.get("byte_count") != expected.byte_count
        ):
            return False
    return True


__all__ = ["P5TemporalRuntimeClient"]
