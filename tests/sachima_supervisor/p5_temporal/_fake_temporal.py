"""In-memory fake of the narrow ``temporalio`` client surface used by the runtime
client, for unit tests (Gate E conformance, Gates D/A unit coverage).

The fake runs the SAME controlled-deterministic core as the real ``StepWorkflow``
(``contracts.deterministic_artifact_ref`` + the pinned ``{resume, request_cancel}``
update semantics), so ``P5TemporalRuntimeClient`` / ``P5TemporalControlSurface``
exercise identical mapping/dedup/conflict/recovery logic against the fake here and
against a real hermetic ``WorkflowEnvironment`` client in the hermetic suite.

It is test support only — it starts no service, Worker, subprocess, or socket.
"""

from __future__ import annotations

from typing import Any

from temporalio.exceptions import WorkflowAlreadyStartedError

from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.workflow import UPDATE_RESULT_TYPE


class _FakeRecord:
    def __init__(self, start_request: C.StartRequest) -> None:
        self.start_request = start_request
        self.resume_count = 0
        self.applied_event_keys: dict[str, tuple[str, ...]] = {}
        self.active_run_watch = False
        self.cancel_requested = False
        self.state = "completed"
        self.snapshot_version = 2

    def snapshot(self) -> dict[str, Any]:
        return C.build_query_snapshot(
            start_request=self.start_request,
            state=self.state,
            snapshot_version=self.snapshot_version,
            artifact_refs=(C.deterministic_artifact_ref(self.start_request),),
            active_run_watch=self.active_run_watch,
            applied_event_count=len(self.applied_event_keys),
            resume_count=self.resume_count,
        )

    def _update_result(self, status: str) -> dict[str, Any]:
        return {"type": UPDATE_RESULT_TYPE, "update_status": status, "snapshot": self.snapshot()}

    def resume(self, payload: C.UpdatePayload) -> dict[str, Any]:
        key = ("resume", payload.event_key, payload.ref or "")
        if self.applied_event_keys.get(payload.event_key) == key:
            return self._update_result("duplicate")
        self.applied_event_keys[payload.event_key] = key
        self.resume_count += 1
        self.snapshot_version += 1
        return self._update_result("applied")

    def request_cancel(self, payload: C.UpdatePayload) -> dict[str, Any]:
        key = ("request_cancel", payload.event_key)
        if self.applied_event_keys.get(payload.event_key) == key:
            return self._update_result("duplicate")
        self.applied_event_keys[payload.event_key] = key
        self.active_run_watch = True
        self.cancel_requested = True
        self.state = "cancelled"
        self.snapshot_version += 1
        return self._update_result("applied")


class _FakeHandle:
    def __init__(self, store: dict[str, _FakeRecord], workflow_id: str) -> None:
        self._store = store
        self.id = workflow_id

    def _record(self) -> _FakeRecord:
        record = self._store.get(self.id)
        if record is None:
            raise RuntimeError("workflow_not_found")
        return record

    async def query(self, query_fn: Any, *args: Any) -> dict[str, Any]:
        return self._record().snapshot()

    async def result(self) -> dict[str, Any]:
        return self._record().snapshot()

    async def execute_update(self, update_fn: Any, payload: Any) -> dict[str, Any]:
        record = self._record()
        name = getattr(update_fn, "__name__", "")
        if name == "resume":
            return record.resume(payload)
        if name == "request_cancel":
            return record.request_cancel(payload)
        raise RuntimeError("unsupported_update")

    async def cancel(self) -> None:  # pragma: no cover - native hard-cancel unused in slice 1
        return None


class FakeTemporalClient:
    """Narrow async fake of ``temporalio.client.Client`` for the runtime client.

    ``record_state`` sets the durable state a freshly launched record reports (the
    default ``"completed"`` models the open-after-work StepWorkflow; ``"closed"`` /
    ``"cancelled"`` model a *terminal* run, used to prove a terminal duplicate start
    reconciles instead of relaunching). The fake raises ``WorkflowAlreadyStartedError``
    on any same-id start — modeling the server's ``REJECT_DUPLICATE`` / ``FAIL`` id
    policies — so a duplicate is always reconciled, never relaunched.
    """

    def __init__(self, *, record_state: str = "completed") -> None:
        self._store: dict[str, _FakeRecord] = {}
        #: Count of *launches* (a duplicate start raises before a second launch).
        self.start_calls = 0
        #: Tripwire — the runtime client must never close the caller-supplied client.
        self.closed = False
        #: Captured per-start keyword args — proves the no-relaunch id policies
        #: (``id_reuse_policy`` / ``id_conflict_policy``) are forwarded to the client.
        self.start_kwargs: list[dict[str, Any]] = []
        self._record_state = record_state

    async def start_workflow(
        self, workflow: Any, arg: Any, *, id: str, task_queue: str, **kwargs: Any
    ) -> _FakeHandle:
        self.start_kwargs.append(dict(kwargs))
        if id in self._store:
            raise WorkflowAlreadyStartedError(id, "StepWorkflow")
        self.start_calls += 1
        record = _FakeRecord(arg)
        record.state = self._record_state
        self._store[id] = record
        return _FakeHandle(self._store, id)

    def get_workflow_handle(self, workflow_id: str) -> _FakeHandle:
        return _FakeHandle(self._store, workflow_id)

    async def close(self) -> None:  # pragma: no cover - must never be reached
        self.closed = True


__all__ = ["FakeTemporalClient"]
