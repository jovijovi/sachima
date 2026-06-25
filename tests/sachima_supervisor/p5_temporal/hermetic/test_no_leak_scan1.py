"""T8 — No-leak SCAN 1 (JSON projection) + canary (FR7, Gate G, merge-blocking).

Proves the durable JSON projection / query snapshot / executor history contain
only allowlisted keys and values, and that canary sentinels seeded into
controlled-body raw-like inputs never appear in the projection — they fail closed
at the trust boundary before any Temporal call.
"""

from __future__ import annotations

from types import SimpleNamespace

from sachima_supervisor.p5_temporal import (
    P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    P5TemporalStepExecutor,
)
from sachima_supervisor.p5_temporal import contracts as C

from tests.sachima_supervisor.p5_temporal.hermetic._harness import (
    control_surface_for,
    p5_worker_env,
    run_async,
    runtime_client_for,
)

_CANARY = "CANARY_7e3f9a_scan1_secret_sentinel"


def _request():
    return SimpleNamespace(
        run_id="run_p5_scan1_0001",
        step_id="architect",
        attempt_index=1,
        idempotency_key="idem_p5_scan1_0001",
        transaction_ref="tx_p5_scan1_0001",
        operation_ref="op_p5_scan1_0001",
        input_artifact_digests=("sha256:" + "a" * 64,),
    )


def _role():
    return SimpleNamespace(role_key="sachima.claude.read_only_reviewer", logical_role="architect")


def _clean_inputs():
    return (
        {
            "artifact_id": "claim_ref_input_0",
            "producer_step_id": "root",
            "content_digest": "sha256:" + "a" * 64,
            "artifact_kind": "input",
            "byte_count": 64,
            "created_at_ref": "created_at_ref_p5_0001",
        },
    )


def _canary_inputs():
    # Raw prompt / card JSON / tool output carrying canary sentinels — claim-check
    # payload that must NEVER cross into Temporal history.
    item = dict(_clean_inputs()[0])
    item["raw_prompt"] = f"system prompt with {_CANARY}"
    item["card_json"] = {"text": _CANARY}
    item["tool_output"] = _CANARY
    return (item,)


def test_clean_run_projection_is_allowlisted_and_canary_free():
    async def scenario():
        async with p5_worker_env() as env:
            executor = P5TemporalStepExecutor(
                control_surface=control_surface_for(env),
                enabled=True,
                approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
            )
            outcome = await executor.aexecute(_request(), role_binding=_role(), resolved_inputs=_clean_inputs())
            snapshot = (await runtime_client_for(env).query(workflow_id=C.workflow_id_from_refs("run_p5_scan1_0001", "architect")))["snapshot"]
            return outcome, snapshot, executor.history_projection()

    outcome, snapshot, history = run_async(scenario())
    assert outcome.ok is True
    # allowlist-only keys
    assert set(snapshot).issubset(C.ALLOWED_SNAPSHOT_KEYS)
    # no forbidden marker / canary in projection or history
    assert C.scan_projection_for_leak(snapshot, canaries=(_CANARY,)) is None
    assert C.scan_projection_for_leak(history, canaries=(_CANARY,)) is None


def test_canary_raw_inputs_fail_closed_and_never_reach_history():
    async def scenario():
        async with p5_worker_env() as env:
            executor = P5TemporalStepExecutor(
                control_surface=control_surface_for(env),
                enabled=True,
                approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
            )
            outcome = await executor.aexecute(_request(), role_binding=_role(), resolved_inputs=_canary_inputs())
            # Nothing should have been launched: the workflow id is unknown.
            recovered = await runtime_client_for(env).query(
                workflow_id=C.workflow_id_from_refs("run_p5_scan1_0001", "architect")
            )
            return outcome, recovered, executor.history_projection()

    outcome, recovered, history = run_async(scenario())
    # Fail closed at the trust boundary — no Temporal call, stable code only.
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_UNSAFE_MATERIAL
    assert recovered["ok"] is False and recovered["error_code"] == C.RUNTIME_NOT_FOUND
    # The canary never entered the executor history projection.
    assert C.scan_projection_for_leak(history, canaries=(_CANARY,)) is None


def test_scan1_detector_has_teeth():
    leaky = {"type": C.SNAPSHOT_TYPE, "x": f"value {_CANARY}"}
    assert C.scan_projection_for_leak(leaky, canaries=(_CANARY,)) == C.RUNTIME_HISTORY_LEAK_DETECTED
    assert C.scan_projection_for_leak({"note": "Traceback (most recent call last)"}) == C.RUNTIME_HISTORY_LEAK_DETECTED
