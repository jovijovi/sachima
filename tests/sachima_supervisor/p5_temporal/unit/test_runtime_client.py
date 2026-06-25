"""T3 — caller-supplied runtime client: dup-start, recovery, no-throw (FR4, Gate D).

Driven against the in-memory fake client (the same ``P5TemporalRuntimeClient`` runs
against a real hermetic ``WorkflowEnvironment`` in the hermetic suite). Proves:

* identical duplicate start replays an idempotent projection and launches nothing
  twice;
* a divergent duplicate fails closed (``runtime_idempotency_conflict``);
* recover reattaches by workflow id and never auto-relaunches uncertain work;
* query/recover/cancel/close are no-throw sanitized envelopes;
* close never disconnects the caller-supplied client (no hidden lifecycle).
"""

from __future__ import annotations

import asyncio

from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.runtime_client import P5TemporalRuntimeClient
from tests.sachima_supervisor.p5_temporal._fake_temporal import FakeTemporalClient


def _start_request(idempotency: str = "idem_p5_demo_0001") -> C.StartRequest:
    return C.build_start_request(
        run_ref="run_p5_demo_0001",
        workflow_ref="tx_p5_demo_0001",
        step_ref="architect",
        attempt_index=1,
        role_keys=("sachima_claude_read_only_reviewer",),
        input_claim_refs=({"ref": "claim_ref_input_0", "digest": "sha256:" + "a" * 64, "kind": "input", "byte_count": 64},),
        idempotency_material=idempotency,
    )


def _client():
    fake = FakeTemporalClient()
    return fake, P5TemporalRuntimeClient(fake)


def test_start_returns_completed_claim_check_snapshot():
    fake, client = _client()
    req = _start_request()
    wid = C.deterministic_workflow_id(req)
    result = asyncio.run(client.start(req, workflow_id=wid))
    assert result["ok"] is True
    assert result["workflow_id"] == wid
    snap = result["snapshot"]
    assert snap["state"] == "completed"
    assert len(snap["artifact_refs"]) == 1
    assert C._SHA256_DIGEST_RE.fullmatch(snap["artifact_refs"][0]["content_digest"])
    assert C.scan_projection_for_leak(snap) is None
    assert fake.start_calls == 1


def test_duplicate_identical_start_replays_and_launches_once():
    fake, client = _client()
    req = _start_request()
    wid = C.deterministic_workflow_id(req)

    async def scenario():
        first = await client.start(req, workflow_id=wid)
        second = await client.start(req, workflow_id=wid)
        return first, second

    first, second = asyncio.run(scenario())
    assert first["ok"] is True
    assert second["ok"] is True
    assert second["replayed"] is True
    assert second["snapshot"]["run_ref"] == "run_p5_demo_0001"
    # nothing launched twice
    assert fake.start_calls == 1


def test_duplicate_divergent_start_fails_closed():
    fake, client = _client()
    req_a = _start_request("idem_p5_demo_0001")
    req_b = _start_request("idem_p5_demo_0002")  # divergent sanitized payload, same step
    wid = C.deterministic_workflow_id(req_a)
    assert C.deterministic_workflow_id(req_b) == wid  # same (run_ref, step_ref) key

    async def scenario():
        await client.start(req_a, workflow_id=wid)
        return await client.start(req_b, workflow_id=wid)

    diverged = asyncio.run(scenario())
    assert diverged["ok"] is False
    assert diverged["error_code"] == C.RUNTIME_IDEMPOTENCY_CONFLICT
    assert fake.start_calls == 1


def test_query_and_recover_after_start():
    fake, client = _client()
    req = _start_request()
    wid = C.deterministic_workflow_id(req)

    async def scenario():
        await client.start(req, workflow_id=wid)
        q = await client.query(workflow_id=wid)
        r = await client.recover(workflow_id=wid)
        return q, r

    q, r = asyncio.run(scenario())
    assert q["ok"] is True and q["snapshot"]["state"] == "completed"
    assert r["ok"] is True and r["op"] == "recover"
    # recover did NOT launch a second workflow
    assert fake.start_calls == 1


def test_query_unknown_workflow_is_no_throw_not_found():
    fake, client = _client()
    result = asyncio.run(client.query(workflow_id="p5wf_" + "0" * 48))
    assert result["ok"] is False
    assert result["error_code"] == C.RUNTIME_NOT_FOUND


def test_signal_cancel_is_no_throw_and_close_does_not_close_client():
    fake, client = _client()
    req = _start_request()
    wid = C.deterministic_workflow_id(req)
    update = C.build_update_payload(event_key="evt_cancel_0001", event_type="request_cancel", ref=None)

    async def scenario():
        await client.start(req, workflow_id=wid)
        cancelled = await client.signal_cancel(workflow_id=wid, update=update)
        closed = await client.close()
        return cancelled, closed

    cancelled, closed = asyncio.run(scenario())
    assert isinstance(cancelled, dict) and cancelled["op"] == "cancel"
    assert closed["ok"] is True and closed["op"] == "close"
    # Gate D: caller-supplied client lifecycle is never owned here.
    assert fake.closed is False


def test_runtime_client_requires_a_client():
    try:
        P5TemporalRuntimeClient(None)
    except C.ContractError as exc:
        assert exc.code == C.RUNTIME_PRECONDITION_UNMET
    else:  # pragma: no cover
        raise AssertionError("expected ContractError for None client")


# --------------------------------------------------------------------------- #
# No-double-launch id policies (Gate D blocker fix): the SDK default
# ALLOW_DUPLICATE would relaunch a *terminal/closed* deterministic id; the start
# must instead forward REJECT_DUPLICATE / FAIL so a same-id start always enters
# duplicate reconciliation (replay / conflict), never a second execution.
# --------------------------------------------------------------------------- #
def test_start_forwards_no_relaunch_id_policies_to_caller_client():
    fake, client = _client()
    req = _start_request()
    wid = C.deterministic_workflow_id(req)
    asyncio.run(client.start(req, workflow_id=wid))
    assert fake.start_kwargs, "start_workflow must be called on the caller-supplied client"
    kwargs = fake.start_kwargs[0]
    # Closed-id reuse is rejected (not the ALLOW_DUPLICATE default) and a running-id
    # conflict fails — both surface as WorkflowAlreadyStartedError -> reconciliation.
    assert kwargs["id_reuse_policy"] == WorkflowIDReusePolicy.REJECT_DUPLICATE
    assert kwargs["id_conflict_policy"] == WorkflowIDConflictPolicy.FAIL


def test_terminal_duplicate_start_reconciles_without_relaunch():
    # The first run reaches a TERMINAL/closed state; a same-id start must reconcile
    # via the closed snapshot and replay — it must never create a second execution.
    fake = FakeTemporalClient(record_state="closed")
    client = P5TemporalRuntimeClient(fake)
    req = _start_request()
    wid = C.deterministic_workflow_id(req)

    async def scenario():
        first = await client.start(req, workflow_id=wid)
        second = await client.start(req, workflow_id=wid)
        return first, second

    first, second = asyncio.run(scenario())
    assert first["ok"] is True
    assert first["snapshot"]["state"] == "closed"
    assert second["ok"] is True
    assert second["replayed"] is True
    assert second["snapshot"]["state"] == "closed"
    # Terminal duplicate reconciled, never relaunched.
    assert fake.start_calls == 1


def test_terminal_duplicate_divergent_start_conflicts_without_relaunch():
    # A divergent same-(run, step) start against a terminal/closed run must fail
    # closed with idempotency_conflict and still launch nothing twice.
    fake = FakeTemporalClient(record_state="closed")
    client = P5TemporalRuntimeClient(fake)
    req_a = _start_request("idem_p5_demo_0001")
    req_b = _start_request("idem_p5_demo_0002")
    wid = C.deterministic_workflow_id(req_a)
    assert C.deterministic_workflow_id(req_b) == wid  # same durable id

    async def scenario():
        await client.start(req_a, workflow_id=wid)
        return await client.start(req_b, workflow_id=wid)

    diverged = asyncio.run(scenario())
    assert diverged["ok"] is False
    assert diverged["error_code"] == C.RUNTIME_IDEMPOTENCY_CONFLICT
    assert fake.start_calls == 1


# --------------------------------------------------------------------------- #
# Duplicate-start reconciliation must query first (Gate D blocker fix)
# --------------------------------------------------------------------------- #
class _HangingResultHandle:
    """Handle for a completed-but-OPEN workflow: ``query()`` returns the completed
    snapshot, but ``result()`` never resolves (mirrors ``StepWorkflow`` staying open
    after the step body completes, waiting for cooperative terminalization).

    ``flags['result_awaited']`` records whether ``result()`` was ever entered, so a
    result-first reconciliation is observable even though the boundary's broad
    ``except`` would otherwise swallow a wait_for cancellation and recover.
    """

    def __init__(self, store: dict, workflow_id: str, flags: dict) -> None:
        self._store = store
        self.id = workflow_id
        self._flags = flags

    def _snapshot(self) -> dict:
        start_request = self._store[self.id]
        return C.build_query_snapshot(
            start_request=start_request,
            state="completed",
            snapshot_version=2,
            artifact_refs=(C.deterministic_artifact_ref(start_request),),
        )

    async def query(self, query_fn, *args) -> dict:
        return self._snapshot()

    async def result(self):
        self._flags["result_awaited"] = True
        await asyncio.Event().wait()  # never resolves: a completed-but-open workflow
        raise AssertionError("unreachable")  # pragma: no cover


class _HangingResultClient:
    """Fake whose started workflow stays open after work completion."""

    def __init__(self, flags: dict) -> None:
        self._store: dict = {}
        self._flags = flags
        self.start_calls = 0

    async def start_workflow(self, workflow, arg, *, id, task_queue, **_):
        if id in self._store:
            raise WorkflowAlreadyStartedError(id, "StepWorkflow")
        self.start_calls += 1
        self._store[id] = arg
        return _HangingResultHandle(self._store, id, self._flags)

    def get_workflow_handle(self, workflow_id: str) -> _HangingResultHandle:
        return _HangingResultHandle(self._store, workflow_id, self._flags)


def test_duplicate_start_completed_but_open_workflow_prefers_query():
    flags = {"result_awaited": False}
    fake = _HangingResultClient(flags)
    client = P5TemporalRuntimeClient(fake)
    req = _start_request()
    wid = C.deterministic_workflow_id(req)

    async def scenario():
        # asyncio.wait_for makes a result-first regression fail fast (timeout or a
        # result_awaited assertion) instead of hanging the suite forever.
        first = await asyncio.wait_for(client.start(req, workflow_id=wid), timeout=5)
        second = await asyncio.wait_for(client.start(req, workflow_id=wid), timeout=5)
        return first, second

    first, second = asyncio.run(scenario())
    assert first["ok"] is True
    assert first["snapshot"]["state"] == "completed"
    # Duplicate start reconciles via query (the completed snapshot) and replays —
    # it must never await handle.result() (which never resolves for an open workflow).
    assert second["ok"] is True
    assert second["replayed"] is True
    assert second["snapshot"]["run_ref"] == "run_p5_demo_0001"
    assert fake.start_calls == 1
    assert flags["result_awaited"] is False
