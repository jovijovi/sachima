"""T2 — no-throw control surface dispatch + leak guard (FR4/FR7, Gates D + G)."""

from __future__ import annotations

import asyncio

from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.control_surface import P5TemporalControlSurface
from sachima_supervisor.p5_temporal.runtime_client import P5TemporalRuntimeClient
from tests.sachima_supervisor.p5_temporal._fake_temporal import FakeTemporalClient


def _start_request() -> C.StartRequest:
    return C.build_start_request(
        run_ref="run_p5_demo_0001",
        workflow_ref="tx_p5_demo_0001",
        step_ref="architect",
        attempt_index=1,
        role_keys=("sachima_claude_read_only_reviewer",),
        input_claim_refs=({"ref": "claim_ref_input_0", "digest": "sha256:" + "b" * 64, "kind": "input", "byte_count": 32},),
        idempotency_material="idem_p5_demo_0001",
    )


def _surface():
    fake = FakeTemporalClient()
    return fake, P5TemporalControlSurface(P5TemporalRuntimeClient(fake))


def test_surface_dispatches_start_query_recover_close():
    fake, surface = _surface()
    req = _start_request()
    wid = C.deterministic_workflow_id(req)

    async def scenario():
        started = await surface.start(req, workflow_id=wid)
        queried = await surface.query(workflow_id=wid)
        recovered = await surface.recover(workflow_id=wid)
        closed = await surface.close()
        return started, queried, recovered, closed

    started, queried, recovered, closed = asyncio.run(scenario())
    assert started["ok"] is True and started["op"] == "start"
    assert queried["ok"] is True and queried["snapshot"]["state"] == "completed"
    assert recovered["ok"] is True
    assert closed["ok"] is True


def test_surface_is_no_throw_on_bad_input():
    fake, surface = _surface()

    async def scenario():
        # an invalid start request object → sanitized error envelope, never raises
        bad = await surface.start(object(), workflow_id="p5wf_" + "0" * 48)
        # unknown operation via generic handle
        unknown = await surface.handle({"operation": "explode", "workflow_id": "p5wf_" + "0" * 48})
        not_a_dict = await surface.handle(["not", "a", "dict"])
        return bad, unknown, not_a_dict

    bad, unknown, not_a_dict = asyncio.run(scenario())
    assert bad["ok"] is False and bad["error_code"] in C.STABLE_CODES
    assert unknown["ok"] is False and unknown["error_code"] == C.RUNTIME_ERROR
    assert not_a_dict["ok"] is False


def test_surface_handle_routes_operations():
    fake, surface = _surface()
    req = _start_request()
    wid = C.deterministic_workflow_id(req)

    async def scenario():
        started = await surface.handle({"operation": "start", "workflow_id": wid, "start_request": req})
        queried = await surface.handle({"operation": "query", "workflow_id": wid})
        return started, queried

    started, queried = asyncio.run(scenario())
    assert started["ok"] is True
    assert queried["ok"] is True and queried["snapshot"]["step_ref"] == "architect"


class _LeakyRuntimeClient:
    """A runtime client whose result smuggles a forbidden marker."""

    async def query(self, *, workflow_id):
        return {"ok": True, "op": "query", "workflow_id": workflow_id, "snapshot": {"leak": "raw_prompt body"}, "error_code": None}


def test_surface_leak_guard_collapses_to_stable_code():
    surface = P5TemporalControlSurface(_LeakyRuntimeClient())
    result = asyncio.run(surface.query(workflow_id="p5wf_" + "0" * 48))
    assert result["ok"] is False
    assert result["error_code"] == C.RUNTIME_HISTORY_LEAK_DETECTED
