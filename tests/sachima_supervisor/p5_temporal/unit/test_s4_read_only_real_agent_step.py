"""S4 read-only real-agent supervisor seam contract (RED first).

These tests pin the separately-approved S4 implementation gate: bind the already
merged S2/S3 Activity seam to one bounded read-only real-agent step through the
merged P6-B / controlled-exec wall, without widening the ActivityInput /
ActivityOutput contract or leaking raw material into history/query surfaces.

The tests are hermetic: they use injected fake supervisor/sink seams and never run
real acpx/npx/agents, Temporal-workers, gate/way, Fei/shu, live delivery, or
production config.
"""

from __future__ import annotations

import asyncio

from sachima_supervisor.activity_controlled_exec import (
    ControlledLocalExecClaimStore,
    FileControlledLocalExecClaimStore,
)
from sachima_supervisor.local_offline import LocalOfflineSupervisorOutcome
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.s2_supervisor_adapter import (
    S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN,
    S2LocalOfflineSupervisorAdapter,
    SupervisorStepResult,
)
from sachima_supervisor.p5_temporal.s3_activity_controller import (
    INTENT_CLASS_TO_ROLE_KEY,
    S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN,
    S3SupervisorActivityBody,
)
from sachima_supervisor.p5_temporal.s4_read_only_real_agent_step import (
    S4_HISTORY_SAFE_ROLE_TO_CONTROLLED_EXEC_ROLE,
    S4_READ_ONLY_REAL_AGENT_STEP_APPROVAL_TOKEN,
    S4ReadOnlyRealAgentSupervisorSeam,
    s4_activity_failure_for_code,
)
from tests.sachima_supervisor.p6b_read_only_real_agent._support import (
    CountingArtifactSink,
    CountingSupervisor,
    OP,
    PREFLIGHT_ACTIVITY_ID,
    STATE_VERSION,
    TXN,
    build_executor,
    evidence_digest,
    expected_activity_id,
    planning_report_ref,
    preflight_store_with_record,
    role_binding,
    role_mapping,
    step_request,
    write_role,
)

_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64
_SENTINEL = object()


def _claim(ref: str = "upstream_summary_artifact", *, digest: str = _DIGEST_B, kind: str = "input") -> dict:
    return {"ref": ref, "digest": digest, "kind": kind, "byte_count": 128}


def _activity_input(*, intent: str = "architecture_packet", step_ref: str = "architect", **overrides):
    base = dict(
        run_ref="run_s4_demo_0001",
        workflow_ref="tx_s4_demo_0001",
        step_ref=step_ref,
        attempt_index=1,
        role_keys=(INTENT_CLASS_TO_ROLE_KEY[intent],),
        input_claim_refs=(_claim(),),
        idempotency_material="idem_s4_demo_0001",
    )
    base.update(overrides)
    return C.build_activity_input(C.build_start_request(**base))


def _p5_artifact_sink(request, *, result, role_binding):
    artifact = C.build_step_artifact_ref(request.run_id, request.step_id, request.attempt_index, role_binding.role_key)
    return (C.step_artifact_ref_projection(artifact),)


def _admitted_seam(tmp_path, *, supervisor=None, sink=None, controlled_exec_store=_SENTINEL, **overrides):
    role_root, digest = write_role(tmp_path, role_mapping())
    if controlled_exec_store is _SENTINEL:
        controlled_exec_store = ControlledLocalExecClaimStore()
    defaults = dict(
        enabled=True,
        approval_token=S4_READ_ONLY_REAL_AGENT_STEP_APPROVAL_TOKEN,
        controlled_exec_store=controlled_exec_store,
        preflight_store=preflight_store_with_record(),
        prompt_materializer=lambda request: "bounded read-only S4 planning/report prompt",
        artifact_sink=sink or CountingArtifactSink(refs_factory=lambda request, result, binding: _p5_artifact_sink(request, result=result, role_binding=binding)),
        invoke_supervisor=supervisor or CountingSupervisor(),
        role_file_digest=digest,
        preflight_activity_id=PREFLIGHT_ACTIVITY_ID,
        prior_dry_run_evidence_digest=evidence_digest(),
        role_root=role_root,
        transaction_ref=TXN,
        operation_ref=OP,
        lease_id=None,
        lease_epoch=0,
        lease_holder_ref=None,
        expected_state_version=STATE_VERSION,
    )
    defaults.update(overrides)
    return S4ReadOnlyRealAgentSupervisorSeam(**defaults)


def _admitted_body(seam, *, claim_store=None):
    adapter = S2LocalOfflineSupervisorAdapter(
        seam=seam,
        enabled=True,
        approval_token=S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN,
        claim_store={} if claim_store is None else claim_store,
    )
    return S3SupervisorActivityBody(
        adapter=adapter,
        enabled=True,
        approval_token=S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN,
    ), adapter


def _reject_code(body, activity_input) -> str:
    try:
        result = asyncio.run(body.run(activity_input))
    except BaseException as exc:  # noqa: BLE001 - probing failure envelope only
        typed = getattr(exc, "type", None)
        code = typed if typed in C.STABLE_CODES else str(exc)
        assert code in C.STABLE_CODES
        assert C.scan_projection_for_leak({"error_code": code}) is None
        return code
    assert type(result) is not C.ActivityOutput
    code = result if isinstance(result, str) else getattr(result, "error_code", None)
    assert code in C.STABLE_CODES
    return code


def test_s4_history_safe_role_mapping_is_closed_and_read_only():
    assert S4_HISTORY_SAFE_ROLE_TO_CONTROLLED_EXEC_ROLE == {
        "sachima_claude_read_only_architect": "sachima.claude.read_only_reviewer",
        "sachima_claude_read_only_programmer_candidate": "sachima.claude.read_only_reviewer",
        "sachima_codex_read_only_reviewer": "sachima.codex.primary_reviewer",
    }
    for s3_role_key in INTENT_CLASS_TO_ROLE_KEY.values():
        assert s3_role_key in S4_HISTORY_SAFE_ROLE_TO_CONTROLLED_EXEC_ROLE


def test_s4_real_seam_default_off_token_mismatch_and_missing_store_zero_launch(tmp_path):
    supervisor = CountingSupervisor()
    sink = CountingArtifactSink()
    for seam, expected in [
        (
            _admitted_seam(tmp_path, supervisor=supervisor, sink=sink, enabled=False),
            C.RUNTIME_DISABLED,
        ),
        (
            _admitted_seam(tmp_path, supervisor=supervisor, sink=sink, approval_token="wrong_s4_token"),
            C.RUNTIME_APPROVAL_MISMATCH,
        ),
        (
            _admitted_seam(tmp_path, supervisor=supervisor, sink=sink, controlled_exec_store=None),
            C.RUNTIME_PRECONDITION_UNMET,
        ),
    ]:
        result = seam.run_step(_activity_input())
        assert type(result) is SupervisorStepResult
        assert result.ok is False
        assert result.error_code == expected
    assert supervisor.calls == 0
    assert sink.calls == 0


def test_s4_real_seam_happy_path_returns_sanitized_supervisor_step_result(tmp_path):
    supervisor = CountingSupervisor()
    seam = _admitted_seam(tmp_path, supervisor=supervisor)

    result = seam.run_step(_activity_input())

    assert supervisor.calls == 1
    assert type(result) is SupervisorStepResult
    assert result.ok is True
    assert result.step_status == "completed"
    assert type(result.artifact_ref) is C.StepArtifactRef
    assert result.artifact_ref.producer_step_id == "architect"
    assert result.evidence_ref == "local_offline_supervisor_evidence_p6b"
    assert result.evidence_digest is not None
    output = C.ActivityOutput(
        schema_version=C.SCHEMA_VERSION,
        status="completed",
        artifact_ref=result.artifact_ref,
        evidence_ref=result.evidence_ref,
        evidence_digest=result.evidence_digest,
    )
    C.validate_activity_output(output)
    assert C.scan_projection_for_leak(
        {"artifact_ref": C.step_artifact_ref_projection(result.artifact_ref), "evidence_ref": result.evidence_ref}
    ) is None


def test_s4_real_seam_fail_closes_unknown_platform_and_writeish_roles_before_launch(tmp_path):
    supervisor = CountingSupervisor()
    seam = _admitted_seam(tmp_path, supervisor=supervisor)

    for role_key in [
        "sachima_claude_architect",
        "sachima_claude_main_programmer",
        "sachima_codex_blocker_only_reviewer",
        "oc_platform_role",
        "write_architecture_packet",
    ]:
        activity_input = C.ActivityInput(
            schema_version=C.SCHEMA_VERSION,
            run_ref="run_s4_bad_role_0001",
            step_ref="architect",
            attempt_index=1,
            role_key=role_key,
            input_claim_refs=(C.ClaimCheckRef("upstream_summary_artifact", _DIGEST_B, "input", 128),),
        )
        result = seam.run_step(activity_input)
        assert result.ok is False
        assert result.error_code in {C.INVALID_START_PAYLOAD, C.RUNTIME_UNSAFE_MATERIAL, C.RUNTIME_PRECONDITION_UNMET}
    assert supervisor.calls == 0


def test_s4_body_duplicate_divergent_and_restart_replay_do_not_relaunch(tmp_path):
    supervisor = CountingSupervisor()
    store_path = tmp_path / "claim-store" / "controlled-local-exec.json"
    adapter_store: dict = {}
    seam = _admitted_seam(
        tmp_path,
        supervisor=supervisor,
        controlled_exec_store=FileControlledLocalExecClaimStore(store_path),
    )
    body, adapter = _admitted_body(seam, claim_store=adapter_store)

    first = asyncio.run(body.run(_activity_input()))
    second = asyncio.run(body.run(_activity_input()))

    assert type(first) is C.ActivityOutput
    assert second == first
    assert supervisor.calls == 1

    divergent = _activity_input(input_claim_refs=(_claim("other_input_ref", digest=_DIGEST_C),))
    assert _reject_code(body, divergent) == C.RUNTIME_IDEMPOTENCY_CONFLICT
    assert supervisor.calls == 1

    # A fresh seam over the same file-backed controlled-exec store replays the
    # resident controlled-exec claim, proving no relaunch after restart/recover.
    restarted = _admitted_seam(
        tmp_path,
        supervisor=supervisor,
        controlled_exec_store=FileControlledLocalExecClaimStore(store_path),
    )
    replay = restarted.run_step(_activity_input())
    assert replay.ok is True
    assert supervisor.calls == 1

    assert C.scan_projection_for_leak(adapter.history_projection()) is None
    assert C.scan_bytes_for_leak(adapter.serialized_history_bytes()) is None


def test_s4_real_seam_never_leaks_raw_supervisor_exception_or_output(tmp_path):
    class RawRaisingSupervisor:
        calls = 0

        def __call__(self, request):
            self.calls += 1
            raise RuntimeError("raw_prompt=DO_NOT_LEAK card_json oc_abc /home/private")

    supervisor = RawRaisingSupervisor()
    seam = _admitted_seam(tmp_path, supervisor=supervisor)
    result = seam.run_step(_activity_input())

    assert supervisor.calls == 1
    assert result.ok is False
    assert result.error_code in C.STABLE_CODES
    assert C.scan_projection_for_leak(result.__dict__) is None
    assert C.scan_projection_for_leak(seam.history_projection()) is None
    assert C.scan_bytes_for_leak(seam.serialized_history_bytes(), canaries=("DO_NOT_LEAK",)) is None


def test_s4_activity_failure_helper_splits_retryable_runtime_error_from_deterministic_codes():
    deterministic = s4_activity_failure_for_code(C.RUNTIME_PRECONDITION_UNMET)
    transient = s4_activity_failure_for_code(C.RUNTIME_ERROR)

    assert getattr(deterministic, "type", None) == C.RUNTIME_PRECONDITION_UNMET
    assert getattr(deterministic, "non_retryable", None) is True
    assert getattr(transient, "type", None) == C.RUNTIME_ERROR
    assert getattr(transient, "non_retryable", None) is False
    assert C.scan_projection_for_leak({"deterministic": str(deterministic), "transient": str(transient)}) is None


def test_s4_retryability_is_enforced_on_actual_s3_activity_path(tmp_path):
    class RawRaisingSupervisor:
        calls = 0

        def __call__(self, request):
            self.calls += 1
            raise RuntimeError("raw_prompt=DO_NOT_LEAK platform_id oc_abc")

    transient_supervisor = RawRaisingSupervisor()
    transient_body, _ = _admitted_body(_admitted_seam(tmp_path, supervisor=transient_supervisor))
    try:
        asyncio.run(transient_body.run(_activity_input()))
    except BaseException as exc:  # noqa: BLE001 - inspect sanitized Temporal failure envelope
        assert getattr(exc, "type", None) == C.RUNTIME_ERROR
        assert getattr(exc, "non_retryable", None) is False
        assert C.scan_projection_for_leak({"error": str(exc), "type": getattr(exc, "type", None)}) is None
    else:  # pragma: no cover - transient failure is required
        raise AssertionError("S4 transient runtime_error unexpectedly succeeded")
    assert transient_supervisor.calls == 1

    deterministic_body, _ = _admitted_body(_admitted_seam(tmp_path, controlled_exec_store=None))
    try:
        asyncio.run(deterministic_body.run(_activity_input()))
    except BaseException as exc:  # noqa: BLE001 - inspect sanitized Temporal failure envelope
        assert getattr(exc, "type", None) == C.RUNTIME_PRECONDITION_UNMET
        assert getattr(exc, "non_retryable", None) is True
    else:  # pragma: no cover - deterministic failure is required
        raise AssertionError("S4 deterministic fail-closed code unexpectedly succeeded")


def test_p6b_baseline_still_proves_bounded_read_only_executor_shape(tmp_path):
    # Guardrail against accidentally bypassing the proven P6-B wall: the S4 seam
    # must be compatible with the existing executor shape rather than inventing a
    # separate runner path.
    supervisor = CountingSupervisor()
    executor = build_executor(tmp_path, invoke_supervisor=supervisor, artifact_sink=CountingArtifactSink())
    outcome = executor.execute(step_request(), role_binding=role_binding(), resolved_inputs=())
    assert outcome.ok is True
    assert supervisor.calls == 1
    assert supervisor.last_request is not None
    assert expected_activity_id() in supervisor.last_request.correlation_label
    assert C.scan_projection_for_leak({"artifact_refs": list(outcome.artifact_refs), "evidence_ref": outcome.evidence_ref}) is None
