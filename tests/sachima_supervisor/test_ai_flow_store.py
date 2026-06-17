"""RED/GREEN tests for the WP4 controlled AI FLOW CAS step store (FR4).

Includes a real-threads concurrency proof: N identical concurrent claims
resolve to exactly one acquisition (mirrors the Phase C true-concurrency CAS
tests).
"""

from __future__ import annotations

import threading

import pytest

from sachima_supervisor.ai_flow_store import (
    STEP_CLAIMED,
    STEP_COMPLETED,
    AiFlowError,
    AiFlowRunStore,
    build_step_state,
    step_fingerprint,
)

_WSD = "sha256:" + "a" * 64
_RBD = "sha256:" + "b" * 64


def _claim_state(**overrides):
    base = dict(
        status=STEP_CLAIMED,
        ok=False,
        run_id="run_alpha",
        step_id="architect",
        logical_role="architect",
        role_key="sachima.claude.read_only_reviewer",
        workflow_spec_digest=_WSD,
        role_binding_digest=_RBD,
        idempotency_key="idem_architect_1",
        attempt_index=1,
        input_artifact_digests=(),
    )
    base.update(overrides)
    return build_step_state(**base)


def _fingerprint(**overrides) -> str:
    base = dict(
        run_id="run_alpha",
        step_id="architect",
        workflow_spec_digest=_WSD,
        role_binding_digest=_RBD,
        input_artifact_digests=(),
        approval_ref="controlled_ai_flow_approval_v1",
        attempt_index=1,
    )
    base.update(overrides)
    return step_fingerprint(**base)


def test_fresh_claim_returns_acquired() -> None:
    store = AiFlowRunStore()
    disposition, state = store.claim_step(
        run_id="run_alpha",
        step_id="architect",
        idempotency_key="idem_architect_1",
        fingerprint=_fingerprint(),
        state=_claim_state(),
    )
    assert disposition == "acquired"
    assert state["status"] == STEP_CLAIMED


def test_identical_replay_returns_replayed_same_projection() -> None:
    store = AiFlowRunStore()
    fp = _fingerprint()
    first = store.claim_step(
        run_id="run_alpha", step_id="architect", idempotency_key="idem_architect_1",
        fingerprint=fp, state=_claim_state(),
    )
    second = store.claim_step(
        run_id="run_alpha", step_id="architect", idempotency_key="idem_architect_1",
        fingerprint=fp, state=_claim_state(),
    )
    assert first[0] == "acquired"
    assert second[0] == "replayed"
    assert second[1] == first[1]


def test_same_key_different_fingerprint_conflicts() -> None:
    store = AiFlowRunStore()
    store.claim_step(
        run_id="run_alpha", step_id="architect", idempotency_key="idem_architect_1",
        fingerprint=_fingerprint(), state=_claim_state(),
    )
    with pytest.raises(AiFlowError) as exc:
        store.claim_step(
            run_id="run_alpha", step_id="architect", idempotency_key="idem_architect_1",
            fingerprint=_fingerprint(attempt_index=2), state=_claim_state(attempt_index=2),
        )
    assert exc.value.error_code == "activity_idempotency_conflict"


def test_same_step_different_key_conflicts() -> None:
    store = AiFlowRunStore()
    store.claim_step(
        run_id="run_alpha", step_id="architect", idempotency_key="idem_architect_1",
        fingerprint=_fingerprint(), state=_claim_state(),
    )
    with pytest.raises(AiFlowError) as exc:
        store.claim_step(
            run_id="run_alpha", step_id="architect", idempotency_key="idem_architect_2",
            fingerprint=_fingerprint(), state=_claim_state(idempotency_key="idem_architect_2"),
        )
    assert exc.value.error_code == "activity_claim_conflict"


def test_finalize_transitions_to_terminal() -> None:
    store = AiFlowRunStore()
    fp = _fingerprint()
    store.claim_step(
        run_id="run_alpha", step_id="architect", idempotency_key="idem_architect_1",
        fingerprint=fp, state=_claim_state(),
    )
    terminal = build_step_state(
        status=STEP_COMPLETED, ok=True, run_id="run_alpha", step_id="architect",
        logical_role="architect", role_key="sachima.claude.read_only_reviewer",
        workflow_spec_digest=_WSD, role_binding_digest=_RBD,
        idempotency_key="idem_architect_1", attempt_index=1, input_artifact_digests=(),
        artifact_ref_count=1, output_artifact_id="artifact_architecture_packet",
        output_artifact_digest=_WSD, output_artifact_kind="architecture_packet",
    )
    store.finalize_step(
        run_id="run_alpha", step_id="architect", idempotency_key="idem_architect_1",
        fingerprint=fp, state=terminal,
    )
    got = store.get_step("run_alpha", "architect")
    assert got["status"] == STEP_COMPLETED
    assert got["ok"] is True


def test_resident_unsafe_state_rejected_on_read() -> None:
    store = AiFlowRunStore()
    store.claim_step(
        run_id="run_alpha", step_id="architect", idempotency_key="idem_architect_1",
        fingerprint=_fingerprint(), state=_claim_state(),
    )
    # Corrupt the resident state out-of-band with raw material.
    store._steps[("run_alpha", "architect")]["logical_role"] = "raw_prompt_leak"
    with pytest.raises(AiFlowError):
        store.get_step("run_alpha", "architect")


def test_unsafe_fingerprint_rejected() -> None:
    store = AiFlowRunStore()
    with pytest.raises(AiFlowError):
        store.claim_step(
            run_id="run_alpha", step_id="architect", idempotency_key="idem_architect_1",
            fingerprint="not-a-fingerprint", state=_claim_state(),
        )


def test_concurrent_identical_claims_acquire_exactly_once() -> None:
    store = AiFlowRunStore()
    fp = _fingerprint()
    n = 32
    barrier = threading.Barrier(n)
    results: list[str] = []
    results_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        try:
            disposition, _ = store.claim_step(
                run_id="run_alpha", step_id="architect",
                idempotency_key="idem_architect_1", fingerprint=fp, state=_claim_state(),
            )
        except AiFlowError:
            disposition = "error"
        with results_lock:
            results.append(disposition)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("acquired") == 1
    assert results.count("replayed") == n - 1
    assert "error" not in results
