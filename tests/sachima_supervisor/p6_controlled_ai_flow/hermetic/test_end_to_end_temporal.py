"""P6-A hermetic end-to-end (FR5/FR8, merge-blocking).

Drives the unmodified WP4 orchestrator through a **real** ops-owned Temporal
Worker via the injected ``P5TemporalStepExecutor`` seam, with a controlled-
deterministic step body, and proves a small linear graph reaches a sanitized
``succeeded`` terminal evidence packet.
"""

from __future__ import annotations

from sachima_supervisor.p5_temporal import contracts as C

from tests.sachima_supervisor.p6_controlled_ai_flow._support import (
    STEP_ORDER,
    run_request,
    step_requests_in_order,
)
from tests.sachima_supervisor.p6_controlled_ai_flow.hermetic._harness import (
    in_thread,
    p5_worker_env,
    run_async,
    temporal_session,
)


def test_temporal_backed_linear_flow_succeeds_with_sanitized_evidence():
    async def scenario():
        async with p5_worker_env() as env:
            session, executor = temporal_session(env)
            outcome = await in_thread(
                session.run_linear,
                run_request(),
                step_requests_in_order(),
                terminal_gate_ref="terminal_ref_ok",
            )
            return outcome, executor.history_projection()

    outcome, history = run_async(scenario())

    assert outcome.admitted is True
    assert outcome.ok is True
    assert outcome.final_verdict == "succeeded"
    assert outcome.active_run_watch is False
    # Sanitized P6 evidence: claim-check refs / digests / codes only.
    ev = outcome.evidence
    assert C.scan_projection_for_leak(ev) is None
    assert ev["p6_admission"] == {"enabled": True, "approved": True, "admission_code": None}
    assert len(ev["artifact_refs"]) == 3
    assert tuple(sorted(t["step_id"] for t in ev["state_transitions"])) == tuple(sorted(STEP_ORDER))
    for ref in ev["artifact_refs"]:
        assert C._SHA256_DIGEST_RE.fullmatch(ref["content_digest"])
    # The executor's local history mediated real Temporal work, sanitized.
    assert C.scan_projection_for_leak(history) is None
    assert history["snapshot_version"] >= 3


def test_terminal_gate_absent_parks_through_real_worker():
    async def scenario():
        async with p5_worker_env() as env:
            session, _ = temporal_session(env)
            return await in_thread(
                session.run_linear,
                run_request(),
                step_requests_in_order(),
                terminal_gate_ref=None,
            )

    outcome = run_async(scenario())
    # WP4 terminal-gate enforcement survives the Temporal-backed path.
    assert outcome.final_verdict == "parked"
    assert outcome.ok is False
