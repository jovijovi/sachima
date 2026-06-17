"""RED/GREEN tests for the WP4 controlled AI FLOW orchestrator (FR2/FR4/FR5/FR6).

Drives the create -> step -> query -> cancel -> summarize API over the canonical
bounded linear read-only flow using an injected fake executor only. Covers the
happy path + replay (T7) and the cancellation posture incl. the WP3b active-run
WATCH (T8).
"""

from __future__ import annotations

import hashlib

import pytest

from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.ai_flow_spec import (
    canonical_read_only_workflow_mapping,
    role_binding_digest,
    validate_workflow_spec,
    workflow_spec_digest,
)
from sachima_supervisor.ai_flow_store import (
    STEP_CLAIMED,
    AiFlowError,
    AiFlowRunStore,
    build_step_state,
    step_fingerprint,
)
from sachima_supervisor.activity_ai_flow_orchestration import (
    AI_FLOW_APPROVAL_TOKEN,
    AiFlowOrchestrationError,
    StepAttemptRequest,
    WorkflowCancellationRequest,
    WorkflowRunRequest,
    create_workflow_run,
    list_workflow_steps,
    query_workflow_run,
    request_workflow_cancellation,
    step_workflow_run,
    summarize_workflow_run,
)

_SPEC = validate_workflow_spec(canonical_read_only_workflow_mapping())
_WSD = workflow_spec_digest(_SPEC)
_RBD = role_binding_digest(_SPEC)
_OUTPUT_CONTRACT = {
    "architect": "architecture_packet",
    "programmer_candidate": "implementation_candidate_analysis",
    "reviewer": "blocker_review",
}
_STEP_ORDER = ("architect", "programmer_candidate", "reviewer")


def _artifact_digest(step_id: str) -> str:
    """Mirror the fake executor's deterministic artifact content digest."""

    body = f"deterministic {step_id} body".encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


#: The input artifact digests each step actually resolves from upstream
#: producers in the canonical linear flow (root steps resolve nothing).
_INPUT_DIGESTS = {
    "architect": (),
    "programmer_candidate": (_artifact_digest("architect"),),
    "reviewer": (_artifact_digest("programmer_candidate"),),
}


class FakeStepExecutor:
    """Configurable injected fake. Counts executor calls."""

    def __init__(self, *, mode: str = "success") -> None:
        self.mode = mode
        self.calls = 0

    def execute(self, request, *, role_binding, resolved_inputs) -> StepExecutionOutcome:
        self.calls += 1
        if self.mode == "retryable_failure":
            return StepExecutionOutcome(
                ok=False, step_status="failed_retryable", artifact_refs=(),
                error_code="activity_step_failed", retryable=True,
            )
        if self.mode == "terminal_failure":
            return StepExecutionOutcome(
                ok=False, step_status="failed_terminal", artifact_refs=(),
                error_code="activity_step_failed", retryable=False,
            )
        kind = _OUTPUT_CONTRACT[request.step_id]
        body = f"deterministic {request.step_id} body".encode()
        artifact = {
            "artifact_id": f"artifact_{request.step_id}",
            "producer_step_id": request.step_id,
            "content_digest": "sha256:" + hashlib.sha256(body).hexdigest(),
            "artifact_kind": kind,
            "byte_count": len(body),
            "created_at_ref": "created_at_ref_0001",
        }
        return StepExecutionOutcome(
            ok=True, step_status="completed", artifact_refs=(artifact,),
            evidence_ref=f"evidence_ref_{request.step_id}",
        )


def _run_request(**o) -> WorkflowRunRequest:
    base = dict(
        run_id="run_alpha", workflow_id=_SPEC.workflow_id, workflow_spec_digest=_WSD,
        role_binding_digest=_RBD, approval_ref=_SPEC.approval_ref,
        transaction_ref="txn_alpha", operation_ref="op_alpha", idempotency_key="idem_run",
        admission_gate_ref="admission_ref_ok", approval_token=AI_FLOW_APPROVAL_TOKEN,
        enabled=True, operator_gate=True,
    )
    base.update(o)
    return WorkflowRunRequest(**base)


def _step_request(step_id, **o) -> StepAttemptRequest:
    base = dict(
        run_id="run_alpha", step_id=step_id, attempt_index=1, workflow_spec_digest=_WSD,
        role_binding_digest=_RBD, input_artifact_digests=_INPUT_DIGESTS[step_id],
        pre_step_gate_ref=f"pre_{step_id}", post_step_gate_ref=f"post_{step_id}",
        transaction_ref="txn_alpha", operation_ref="op_alpha", idempotency_key=f"idem_{step_id}",
        approval_token=AI_FLOW_APPROVAL_TOKEN, enabled=True, operator_gate=True,
    )
    base.update(o)
    return StepAttemptRequest(**base)


def _drive_all(store, executor):
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    for step_id in _STEP_ORDER:
        step_workflow_run(_step_request(step_id), spec=_SPEC, store=store, executor=executor)


def _summarize_terminal(store):
    return summarize_workflow_run(
        store,
        run_id="run_alpha",
        operator_gate=True,
        terminal_gate_ref="terminal_ref_ok",
    )


# --------------------------------------------------------------------------- #
# T7 — happy path + replay
# --------------------------------------------------------------------------- #
def test_end_to_end_linear_flow_succeeds_with_exactly_three_calls() -> None:
    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    _drive_all(store, executor)
    assert executor.calls == 3
    evidence = _summarize_terminal(store)
    assert evidence.final_verdict == "succeeded"
    steps = list_workflow_steps(store, run_id="run_alpha")
    assert {s.step_id for s in steps} == set(_STEP_ORDER)
    assert all(s.status == "completed" for s in steps)


def test_admission_gate_missing_means_run_not_created() -> None:
    store = AiFlowRunStore()
    with pytest.raises(AiFlowOrchestrationError):
        create_workflow_run(_run_request(admission_gate_ref=None), spec=_SPEC, store=store)
    with pytest.raises(AiFlowOrchestrationError):
        query_workflow_run(store, run_id="run_alpha")


def test_disabled_or_wrong_token_fails_closed() -> None:
    store = AiFlowRunStore()
    with pytest.raises(AiFlowOrchestrationError):
        create_workflow_run(_run_request(enabled=False), spec=_SPEC, store=store)
    with pytest.raises(AiFlowOrchestrationError):
        create_workflow_run(_run_request(approval_token="wrong"), spec=_SPEC, store=store)


def test_pre_step_gate_missing_means_zero_executor_calls() -> None:
    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    result = step_workflow_run(
        _step_request("architect", pre_step_gate_ref=None), spec=_SPEC, store=store, executor=executor
    )
    assert executor.calls == 0
    assert result.status == "gate_blocked"


def test_post_step_gate_missing_blocks_propagation_and_downstream() -> None:
    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    # architect runs but its post-step gate is missing -> artifact not propagated
    step_workflow_run(
        _step_request("architect", post_step_gate_ref=None), spec=_SPEC, store=store, executor=executor
    )
    assert executor.calls == 1
    # downstream cannot resolve its input -> not scheduled, no executor call
    downstream = step_workflow_run(
        _step_request("programmer_candidate"), spec=_SPEC, store=store, executor=executor
    )
    assert executor.calls == 1
    assert downstream.ok is False


def test_idempotent_step_replay_does_not_call_executor_twice() -> None:
    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    first = step_workflow_run(_step_request("architect"), spec=_SPEC, store=store, executor=executor)
    second = step_workflow_run(_step_request("architect"), spec=_SPEC, store=store, executor=executor)
    assert executor.calls == 1
    assert first.to_durable_state() == second.to_durable_state()


def test_conflicting_step_replay_fails_closed_pre_execute() -> None:
    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    step_workflow_run(_step_request("architect"), spec=_SPEC, store=store, executor=executor)
    with pytest.raises(AiFlowError):
        # same idempotency key, different fingerprint (attempt_index)
        step_workflow_run(
            _step_request("architect", attempt_index=2), spec=_SPEC, store=store, executor=executor
        )
    assert executor.calls == 1


def test_terminal_executor_failure_is_recorded() -> None:
    store = AiFlowRunStore()
    executor = FakeStepExecutor(mode="terminal_failure")
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    result = step_workflow_run(_step_request("architect"), spec=_SPEC, store=store, executor=executor)
    assert result.ok is False
    assert result.status == "failed_terminal"
    evidence = _summarize_terminal(store)
    assert evidence.final_verdict == "failed"


def test_terminal_gate_missing_parks_completed_flow() -> None:
    """FR2 terminal gate: completed steps are not accepted without terminal
    operator material; summarization must park instead of succeeding."""

    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    _drive_all(store, executor)
    evidence = summarize_workflow_run(store, run_id="run_alpha")
    assert evidence.final_verdict == "parked"
    terminal_gates = [
        gate for gate in evidence.to_durable_state()["gate_decisions"]
        if gate["gate_type"] == "terminal"
    ]
    assert terminal_gates == [
        {"gate_type": "terminal", "gate_ref": None, "status": "missing", "step_id": None}
    ]


# --------------------------------------------------------------------------- #
# T8 — cancellation posture incl. WP3b active-run WATCH
# --------------------------------------------------------------------------- #
def _cancel_request(scope, **o) -> WorkflowCancellationRequest:
    base = dict(
        cancel_id="cancel_alpha", run_id="run_alpha", step_id=None, scope=scope,
        transaction_ref="txn_alpha", operation_ref="op_alpha", idempotency_key="idem_cancel",
        approval_token=AI_FLOW_APPROVAL_TOKEN, enabled=True, operator_gate=True,
    )
    base.update(o)
    return WorkflowCancellationRequest(**base)


def _claim_in_progress(store, step_id) -> None:
    """Seat a resident ``claimed_in_progress`` step (an active mid-step run)."""

    step = next(s for s in _SPEC.steps if s.step_id == step_id)
    binding = next(r for r in _SPEC.roles if r.logical_role == step.logical_role)
    idempotency_key = f"idem_{step_id}"
    fingerprint = step_fingerprint(
        run_id="run_alpha", step_id=step_id, workflow_spec_digest=_WSD,
        role_binding_digest=_RBD, input_artifact_digests=(),
        approval_ref=_SPEC.approval_ref, attempt_index=1,
    )
    state = build_step_state(
        status=STEP_CLAIMED, ok=False, run_id="run_alpha", step_id=step_id,
        logical_role=step.logical_role, role_key=binding.role_key,
        workflow_spec_digest=_WSD, role_binding_digest=_RBD,
        idempotency_key=idempotency_key, attempt_index=1, input_artifact_digests=(),
    )
    store.claim_step(
        run_id="run_alpha", step_id=step_id, idempotency_key=idempotency_key,
        fingerprint=fingerprint, state=state,
    )


def test_between_step_cancel_is_deterministic_terminal() -> None:
    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    step_workflow_run(_step_request("architect"), spec=_SPEC, store=store, executor=executor)
    calls_before = executor.calls
    result = request_workflow_cancellation(_cancel_request("between_step"), store=store)
    assert result.status == "cancelled"
    # no executor relaunch
    assert executor.calls == calls_before
    evidence = _summarize_terminal(store)
    assert evidence.final_verdict == "cancelled"
    assert evidence.active_run_cancellation_watch is False


def test_active_run_cancel_confirmed_records_cancelled() -> None:
    store = AiFlowRunStore()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    # A confirmed active-run cancel only records ``cancelled`` against a resident
    # in-progress step (Blocker 3): seat the claimed_in_progress step first.
    _claim_in_progress(store, "architect")
    outcome = StepExecutionOutcome(
        ok=False, step_status="cancelled", artifact_refs=(),
        interrupted=True, cleanup_verified=True,
    )
    result = request_workflow_cancellation(
        _cancel_request("active_run", step_id="architect"), store=store, interrupt_outcome=outcome
    )
    assert result.status == "cancelled"
    evidence = summarize_workflow_run(store, run_id="run_alpha")
    assert evidence.active_run_cancellation_watch is False


def test_active_run_cancel_unconfirmed_holds_watch() -> None:
    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    outcome = StepExecutionOutcome(
        ok=False, step_status="indeterminate", artifact_refs=(),
        interrupted=False, cleanup_verified=False, ambiguous=True,
    )
    result = request_workflow_cancellation(
        _cancel_request("active_run", step_id="architect"), store=store, interrupt_outcome=outcome
    )
    assert result.status == "cancel_ambiguous"
    assert result.error_code == "active_run_cancellation_watch"
    # no relaunch of the step
    assert executor.calls == 0
    evidence = summarize_workflow_run(store, run_id="run_alpha")
    assert evidence.active_run_cancellation_watch is True
    assert evidence.final_verdict == "ambiguous_fail_closed"
    # no artifact propagated by the indeterminate cancel
    assert summarize_workflow_run(store, run_id="run_alpha").to_durable_state()["artifact_refs"] == []


def test_active_run_cancel_without_outcome_holds_watch() -> None:
    store = AiFlowRunStore()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    result = request_workflow_cancellation(
        _cancel_request("active_run", step_id="architect"), store=store
    )
    assert result.status == "cancel_ambiguous"
    assert result.error_code == "active_run_cancellation_watch"


def test_cancel_id_conflict_cannot_downgrade_active_run_watch() -> None:
    """Final PR review blocker: a later same-cancel-id request must not
    overwrite a fail-closed active-run WATCH with a clean cancellation."""

    store = AiFlowRunStore()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    first = request_workflow_cancellation(
        _cancel_request("active_run", step_id="architect", idempotency_key="idem_cancel_watch"),
        store=store,
    )
    assert first.status == "cancel_ambiguous"
    assert first.error_code == "active_run_cancellation_watch"

    try:
        second = request_workflow_cancellation(
            _cancel_request("between_step", idempotency_key="idem_cancel_conflict"),
            store=store,
        )
    except AiFlowError as exc:
        assert exc.error_code == "activity_idempotency_conflict"
    else:
        assert second.status == "cancel_ambiguous"
        assert second.error_code == "active_run_cancellation_watch"

    cancel = store.get_cancellation("cancel_alpha")
    assert cancel is not None
    assert cancel["status"] == "cancel_ambiguous"
    assert cancel["error_code"] == "active_run_cancellation_watch"
    evidence = summarize_workflow_run(store, run_id="run_alpha")
    assert evidence.active_run_cancellation_watch is True
    assert evidence.final_verdict == "ambiguous_fail_closed"


def test_cancellation_requires_operator_gate() -> None:
    store = AiFlowRunStore()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    with pytest.raises(AiFlowOrchestrationError):
        request_workflow_cancellation(_cancel_request("between_step", operator_gate=False), store=store)


# --------------------------------------------------------------------------- #
# Codex blocker fix regressions
# --------------------------------------------------------------------------- #
def test_step_after_cancellation_rejected_zero_executor_no_artifact() -> None:
    """Blocker 1: a step attempt after the run is cancelled must be rejected
    before claim/executor — zero executor calls and no artifact propagation."""

    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    step_workflow_run(_step_request("architect"), spec=_SPEC, store=store, executor=executor)
    request_workflow_cancellation(_cancel_request("between_step"), store=store)
    assert query_workflow_run(store, run_id="run_alpha").status == "cancelled"

    calls_before = executor.calls
    artifacts_before = len(store.list_artifacts("run_alpha"))
    with pytest.raises(AiFlowOrchestrationError):
        step_workflow_run(
            _step_request("programmer_candidate"), spec=_SPEC, store=store, executor=executor
        )
    # no executor relaunch, no new artifact, no step record for the rejected step
    assert executor.calls == calls_before
    assert len(store.list_artifacts("run_alpha")) == artifacts_before
    step_ids = {s.step_id for s in list_workflow_steps(store, run_id="run_alpha")}
    assert "programmer_candidate" not in step_ids


def test_step_spec_digest_mismatch_rejected_before_claim() -> None:
    """Blocker 2: a step whose workflow_spec_digest does not bind the resident
    run / validated spec is rejected before claim/executor."""

    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    with pytest.raises(AiFlowOrchestrationError):
        step_workflow_run(
            _step_request("architect", workflow_spec_digest="sha256:" + "0" * 64),
            spec=_SPEC, store=store, executor=executor,
        )
    assert executor.calls == 0
    assert list_workflow_steps(store, run_id="run_alpha") == ()


def test_step_role_binding_digest_mismatch_rejected_before_claim() -> None:
    """Blocker 2: a step whose role_binding_digest does not bind the resident
    run / validated spec is rejected before claim/executor."""

    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    with pytest.raises(AiFlowOrchestrationError):
        step_workflow_run(
            _step_request("architect", role_binding_digest="sha256:" + "0" * 64),
            spec=_SPEC, store=store, executor=executor,
        )
    assert executor.calls == 0
    assert list_workflow_steps(store, run_id="run_alpha") == ()


def test_step_input_digest_mismatch_fails_closed_before_executor() -> None:
    """Blocker 2: a step whose declared input_artifact_digests do not match the
    actual resolved upstream artifact digests fails closed before the executor."""

    store = AiFlowRunStore()
    executor = FakeStepExecutor()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    step_workflow_run(_step_request("architect"), spec=_SPEC, store=store, executor=executor)
    assert executor.calls == 1
    result = step_workflow_run(
        _step_request("programmer_candidate", input_artifact_digests=("sha256:" + "0" * 64,)),
        spec=_SPEC, store=store, executor=executor,
    )
    # the mismatched step never reaches the executor and is recorded terminal
    assert executor.calls == 1
    assert result.ok is False
    assert result.status == "failed_terminal"


def test_active_run_cancel_confirmed_without_resident_claim_holds_watch() -> None:
    """Blocker 3: a confirmed interrupt outcome must NOT record ``cancelled``
    unless a matching step_id is resident in ``claimed_in_progress``; with no
    resident claim it fails closed and preserves the WATCH."""

    store = AiFlowRunStore()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    # No resident claimed_in_progress step exists for "architect".
    outcome = StepExecutionOutcome(
        ok=False, step_status="cancelled", artifact_refs=(),
        interrupted=True, cleanup_verified=True,
    )
    result = request_workflow_cancellation(
        _cancel_request("active_run", step_id="architect"), store=store, interrupt_outcome=outcome
    )
    assert result.status == "cancel_ambiguous"
    assert result.error_code == "active_run_cancellation_watch"
    evidence = summarize_workflow_run(store, run_id="run_alpha")
    assert evidence.active_run_cancellation_watch is True
    assert evidence.final_verdict == "ambiguous_fail_closed"


# --------------------------------------------------------------------------- #
# Final Codex blocker — mid-step cancellation race
# --------------------------------------------------------------------------- #
class MidStepCancellingExecutor:
    """Injected fake that requests a ``between_step`` cancellation *during* its
    ``execute()`` — i.e. while this step is still resident in
    ``claimed_in_progress`` — then returns a normal artifact-bearing success.

    This reproduces the race where a cancellation lands after the step claim but
    before the orchestrator finalizes the step.
    """

    def __init__(self, store) -> None:
        self.store = store
        self.calls = 0

    def execute(self, request, *, role_binding, resolved_inputs) -> StepExecutionOutcome:
        self.calls += 1
        # Cancellation arrives mid-step (after the claim, before finalization).
        request_workflow_cancellation(_cancel_request("between_step"), store=self.store)
        kind = _OUTPUT_CONTRACT[request.step_id]
        body = f"deterministic {request.step_id} body".encode()
        artifact = {
            "artifact_id": f"artifact_{request.step_id}",
            "producer_step_id": request.step_id,
            "content_digest": "sha256:" + hashlib.sha256(body).hexdigest(),
            "artifact_kind": kind,
            "byte_count": len(body),
            "created_at_ref": "created_at_ref_0001",
        }
        return StepExecutionOutcome(
            ok=True, step_status="completed", artifact_refs=(artifact,),
            evidence_ref=f"evidence_ref_{request.step_id}",
        )


def test_between_step_cancel_during_execute_holds_watch_no_artifact() -> None:
    """Final blocker: a ``between_step`` cancellation that races an in-flight step
    claim must NOT produce completed-step + clean-cancelled + propagated-artifact.

    The step finalizes fail-closed (WATCH/ambiguous), no artifact propagates, the
    cancellation reclassifies to WATCH/ambiguous (not clean cancelled), and the
    evidence surfaces ``active_run_cancellation_watch`` with verdict
    ``ambiguous_fail_closed``."""

    store = AiFlowRunStore()
    executor = MidStepCancellingExecutor(store)
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    result = step_workflow_run(
        _step_request("architect"), spec=_SPEC, store=store, executor=executor
    )
    assert executor.calls == 1
    # no post-step success and no artifact propagation
    assert result.ok is False
    assert result.status != "completed"
    assert store.list_artifacts("run_alpha") == ()
    # the cancellation reclassified to WATCH/ambiguous, not a clean cancelled
    cancel = store.get_cancellation("cancel_alpha")
    assert cancel["status"] == "cancel_ambiguous"
    assert cancel["error_code"] == "active_run_cancellation_watch"
    # evidence surfaces the WATCH and the ambiguous fail-closed verdict
    evidence = summarize_workflow_run(store, run_id="run_alpha")
    assert evidence.active_run_cancellation_watch is True
    assert evidence.final_verdict == "ambiguous_fail_closed"
    assert evidence.to_durable_state()["artifact_refs"] == []


def test_between_step_cancel_with_resident_claim_holds_watch() -> None:
    """Protection 1 (direct): a ``between_step`` cancellation requested while a
    step is resident in ``claimed_in_progress`` must record WATCH/ambiguous, not a
    clean ``cancelled`` — a step is actually in flight."""

    store = AiFlowRunStore()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    _claim_in_progress(store, "architect")
    result = request_workflow_cancellation(_cancel_request("between_step"), store=store)
    assert result.status == "cancel_ambiguous"
    assert result.error_code == "active_run_cancellation_watch"
    evidence = summarize_workflow_run(store, run_id="run_alpha")
    assert evidence.active_run_cancellation_watch is True
    assert evidence.final_verdict == "ambiguous_fail_closed"


class _PostRecheckCancellingArtifactRefs(tuple):
    def __new__(cls, store, refs):
        obj = super().__new__(cls, refs)
        obj.store = store  # type: ignore[attr-defined]
        obj.triggered = False  # type: ignore[attr-defined]
        return obj

    def _trigger_once(self) -> None:
        if not self.triggered:
            self.triggered = True
            request_workflow_cancellation(
                _cancel_request(
                    "between_step",
                    cancel_id="cancel_after_recheck",
                    idempotency_key="idem_cancel_after_recheck",
                ),
                store=self.store,  # type: ignore[attr-defined]
            )

    def __len__(self):
        self._trigger_once()
        return super().__len__()

    def __getitem__(self, item):
        self._trigger_once()
        return super().__getitem__(item)


class PostRecheckCancellingExecutor:
    """Injected fake that cancels after the orchestrator's first post-execute
    run-status recheck but before artifact propagation."""

    def __init__(self, store) -> None:
        self.store = store
        self.calls = 0
        self.artifact_refs = None

    def execute(self, request, *, role_binding, resolved_inputs) -> StepExecutionOutcome:
        self.calls += 1
        kind = _OUTPUT_CONTRACT[request.step_id]
        body = f"deterministic {request.step_id} body".encode()
        self.artifact_refs = _PostRecheckCancellingArtifactRefs(
            self.store,
            (
                {
                    "artifact_id": f"artifact_{request.step_id}",
                    "producer_step_id": request.step_id,
                    "content_digest": "sha256:" + hashlib.sha256(body).hexdigest(),
                    "artifact_kind": kind,
                    "byte_count": len(body),
                    "created_at_ref": "created_at_ref_0001",
                },
            ),
        )
        return StepExecutionOutcome(
            ok=True, step_status="completed", artifact_refs=self.artifact_refs,
            evidence_ref=f"evidence_ref_{request.step_id}",
        )


def test_between_step_cancel_after_recheck_before_artifact_holds_watch_no_artifact() -> None:
    """Final PR-review blocker: cancellation after the post-execute run recheck
    but before artifact persistence still must not propagate artifacts."""

    store = AiFlowRunStore()
    executor = PostRecheckCancellingExecutor(store)
    create_workflow_run(_run_request(), spec=_SPEC, store=store)
    result = step_workflow_run(
        _step_request("architect"), spec=_SPEC, store=store, executor=executor
    )
    assert executor.calls == 1
    assert executor.artifact_refs is not None
    assert executor.artifact_refs.triggered is True
    assert result.ok is False
    assert result.status == "cancel_ambiguous"
    assert store.list_artifacts("run_alpha") == ()
    cancel = store.get_cancellation("cancel_after_recheck")
    assert cancel is not None
    assert cancel["status"] == "cancel_ambiguous"
    assert cancel["error_code"] == "active_run_cancellation_watch"
    evidence = summarize_workflow_run(store, run_id="run_alpha")
    assert evidence.active_run_cancellation_watch is True
    assert evidence.final_verdict == "ambiguous_fail_closed"
