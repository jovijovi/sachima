"""P6-A hermetic dup / divergent / recover / cancel probes (FR5, merge-blocking).

Through a **real** ops-owned Temporal Worker and the P6-A composition:

* duplicate-identical step replay is idempotent (the executor is not re-run);
* a divergent step attempt fails closed before any new durable work;
* recover reattaches by workflow id without relaunching uncertain work;
* an active-run cancellation that cannot be proven clean preserves the WP3b WATCH
  (``active_run_cancellation_watch`` / ``cancel_ambiguous``), never upgraded.
"""

from __future__ import annotations

import pytest

from sachima_supervisor.ai_flow_store import AiFlowError
from sachima_supervisor.p5_temporal import contracts as C

from tests.sachima_supervisor.p6_controlled_ai_flow._support import (
    cancel_request,
    run_request,
    step_request,
)
from tests.sachima_supervisor.p6_controlled_ai_flow.hermetic._harness import (
    in_thread,
    p5_worker_env,
    run_async,
    temporal_session,
)


def test_duplicate_identical_step_is_idempotent_and_runs_once():
    def drive(session):
        session.create_run(run_request())
        first = session.step(step_request("architect"))
        second = session.step(step_request("architect"))
        return first, second

    async def scenario():
        async with p5_worker_env() as env:
            session, executor = temporal_session(env)
            (first, second) = await in_thread(drive, session)
            return first, second, executor.history_projection()

    first, second, history = run_async(scenario())
    assert first.status == "completed"
    assert first.durable_state == second.durable_state
    # The executor mediated exactly one real Temporal step body (one completion).
    completions = [e for e in history["events"] if e["event"] == "execute_completed"]
    assert len(completions) == 1


def test_divergent_step_attempt_fails_closed():
    def drive(session):
        session.create_run(run_request())
        session.step(step_request("architect"))
        # Same idempotency key, divergent fingerprint (attempt_index) -> conflict.
        return session.step(step_request("architect", attempt_index=2))

    async def scenario():
        async with p5_worker_env() as env:
            session, _ = temporal_session(env)
            return await in_thread(drive, session)

    with pytest.raises(AiFlowError):
        run_async(scenario())


def test_recover_reattaches_without_relaunch():
    def drive(session):
        session.create_run(run_request())
        session.step(step_request("architect"))
        return session.recover(run_id="run_p6_alpha", step_id="architect")

    async def scenario():
        async with p5_worker_env() as env:
            session, executor = temporal_session(env)
            out = await in_thread(drive, session)
            return out, executor.history_projection()

    out, history = run_async(scenario())
    assert out.ok is True and out.op == "recover"
    assert C.scan_projection_for_leak(out.snapshot) is None
    assert out.snapshot["recovery_marker"] == "reattached_no_relaunch"
    # Reattach only: exactly one real step completion ever happened.
    completions = [e for e in history["events"] if e["event"] == "execute_completed"]
    assert len(completions) == 1


def test_active_run_cancellation_preserves_watch():
    def drive(session):
        session.create_run(run_request())
        session.step(step_request("architect"))
        return session.cancel(cancel_request(scope="active_run", step_id="architect"))

    async def scenario():
        async with p5_worker_env() as env:
            session, _ = temporal_session(env)
            return await in_thread(drive, session)

    out = run_async(scenario())
    assert out.ok is False
    assert out.active_run_watch is True
    assert out.error_code == C.ACTIVE_RUN_CANCELLATION_WATCH
    assert out.snapshot["status"] == "cancel_ambiguous"
