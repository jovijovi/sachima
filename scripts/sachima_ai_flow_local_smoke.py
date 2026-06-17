#!/usr/bin/env python3
"""Sachima WP4 controlled AI FLOW local/offline self-test smoke (injected fakes).

Drives the **existing** WP4 orchestrator
(``sachima_supervisor.activity_ai_flow_orchestration``) through the canonical
bounded linear read-only flow (``architect -> programmer_candidate ->
reviewer``) using an **in-process injected fake executor only**. There is no
real workflow execution, no acpx/npx, no subprocess, no socket, no Gateway,
Feishu, IM delivery, live/default-on behavior, production config, or real
delivery — and slice 1 deliberately ships **no real mode**.

Scope boundary (local/offline only):

  * ``--self-test`` is the only supported mode. Without it the smoke exits ``2``
    because real controlled AI FLOW execution is not approved in this slice.
  * It writes nothing to disk and starts no service; it asserts lifecycle,
    gate, idempotency, cancellation-WATCH, and no-leak invariants in memory and
    prints a sanitized JSON summary.

Exit codes: ``0`` self-test PASS · ``1`` verification failure · ``2`` real mode
(not approved in slice 1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sachima_supervisor.activity_ai_flow_orchestration import (  # noqa: E402
    AI_FLOW_APPROVAL_TOKEN,
    StepAttemptRequest,
    WorkflowCancellationRequest,
    WorkflowRunRequest,
    create_workflow_run,
    list_workflow_steps,
    request_workflow_cancellation,
    step_workflow_run,
    summarize_workflow_run,
)
from sachima_supervisor.ai_flow_evidence import _walk_strings
from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.ai_flow_spec import (
    canonical_read_only_workflow_mapping,
    role_binding_digest,
    validate_workflow_spec,
    workflow_spec_digest,
)
from sachima_supervisor.ai_flow_store import AiFlowError, AiFlowRunStore

_FORBIDDEN_MARKERS = (
    "raw_prompt",
    "prompt_body",
    "media_path",
    "card_json",
    "signed_url",
    "tool_output",
    "bearer ",
    "api_key",
    "private_key",
    "traceback",
    "/tmp/",
    "media:",
)

_STEP_ORDER = ("architect", "programmer_candidate", "reviewer")


class SmokeError(Exception):
    pass


class _FakeStepExecutor:
    """Deterministic injected fake. Counts calls; produces contract artifacts."""

    def __init__(self, output_contracts: dict[str, str]) -> None:
        self._contracts = output_contracts
        self.calls = 0

    def execute(self, request, *, role_binding, resolved_inputs) -> StepExecutionOutcome:
        self.calls += 1
        kind = self._contracts[request.step_id]
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
            ok=True,
            step_status="completed",
            artifact_refs=(artifact,),
            evidence_ref=f"evidence_ref_{request.step_id}",
        )


def _spec_and_digests():
    spec = validate_workflow_spec(canonical_read_only_workflow_mapping())
    return spec, workflow_spec_digest(spec), role_binding_digest(spec)


def _run_request(spec, wsd, rbd, *, run_id, idem, gate_ref="admission_ref_ok"):
    return WorkflowRunRequest(
        run_id=run_id,
        workflow_id=spec.workflow_id,
        workflow_spec_digest=wsd,
        role_binding_digest=rbd,
        approval_ref=spec.approval_ref,
        transaction_ref="txn_smoke",
        operation_ref="op_smoke",
        idempotency_key=idem,
        admission_gate_ref=gate_ref,
        approval_token=AI_FLOW_APPROVAL_TOKEN,
        enabled=True,
        operator_gate=True,
    )


def _resolved_input_digests(spec, step_id) -> tuple[str, ...]:
    """The input artifact digests a step resolves from upstream producers.

    Mirrors the orchestrator's claim-check resolution and the fake executor's
    deterministic content digests so the smoke binds declared inputs to reality.
    """

    step = next(s for s in spec.steps if s.step_id == step_id)
    digests: list[str] = []
    for input_ref in step.input_refs:
        if not step.depends_on:
            continue  # root steps consume external inputs (resolve nothing)
        producer = next(s.step_id for s in spec.steps if s.output_contract == input_ref)
        body = f"deterministic {producer} body".encode()
        digests.append("sha256:" + hashlib.sha256(body).hexdigest())
    return tuple(digests)


def _step_request(
    wsd, rbd, *, run_id, step_id, pre="present", post="present", attempt_index=1,
    input_artifact_digests=(),
):
    return StepAttemptRequest(
        run_id=run_id,
        step_id=step_id,
        attempt_index=attempt_index,
        workflow_spec_digest=wsd,
        role_binding_digest=rbd,
        input_artifact_digests=input_artifact_digests,
        pre_step_gate_ref=f"pre_{step_id}" if pre == "present" else None,
        post_step_gate_ref=f"post_{step_id}" if post == "present" else None,
        transaction_ref="txn_smoke",
        operation_ref="op_smoke",
        idempotency_key=f"idem_{run_id}_{step_id}_{attempt_index}",
        approval_token=AI_FLOW_APPROVAL_TOKEN,
        enabled=True,
        operator_gate=True,
    )


def _assert_no_leak(payload: Any) -> None:
    rendered = "\n".join(_walk_strings(payload)).lower()
    for marker in _FORBIDDEN_MARKERS:
        if marker in rendered:
            raise SmokeError(f"leak marker present in evidence: {marker!r}")


def _scenario_happy_path(spec, wsd, rbd) -> dict[str, Any]:
    store = AiFlowRunStore()
    contracts = {s.step_id: s.output_contract for s in spec.steps}
    executor = _FakeStepExecutor(contracts)
    create_workflow_run(_run_request(spec, wsd, rbd, run_id="run_happy", idem="idem_happy"), spec=spec, store=store)
    for step_id in _STEP_ORDER:
        step_workflow_run(
            _step_request(
                wsd, rbd, run_id="run_happy", step_id=step_id,
                input_artifact_digests=_resolved_input_digests(spec, step_id),
            ),
            spec=spec, store=store, executor=executor,
        )
    evidence = summarize_workflow_run(store, run_id="run_happy")
    state = evidence.to_durable_state()
    _assert_no_leak(state)
    steps = list_workflow_steps(store, run_id="run_happy")
    return {
        "scenario": "happy_path",
        "executor_calls": executor.calls,
        "final_verdict": evidence.final_verdict,
        "all_steps_completed": all(s.status == "completed" for s in steps),
        "active_run_cancellation_watch": evidence.active_run_cancellation_watch,
        "evidence_sanitized": True,
    }


def _scenario_pre_step_gate_block(spec, wsd, rbd) -> dict[str, Any]:
    store = AiFlowRunStore()
    contracts = {s.step_id: s.output_contract for s in spec.steps}
    executor = _FakeStepExecutor(contracts)
    create_workflow_run(_run_request(spec, wsd, rbd, run_id="run_gate", idem="idem_gate"), spec=spec, store=store)
    result = step_workflow_run(
        _step_request(wsd, rbd, run_id="run_gate", step_id="architect", pre="missing"),
        spec=spec, store=store, executor=executor,
    )
    return {
        "scenario": "pre_step_gate_missing",
        "executor_calls": executor.calls,
        "step_status": result.status,
        "zero_calls": executor.calls == 0,
    }


def _scenario_idempotent_replay(spec, wsd, rbd) -> dict[str, Any]:
    store = AiFlowRunStore()
    contracts = {s.step_id: s.output_contract for s in spec.steps}
    executor = _FakeStepExecutor(contracts)
    create_workflow_run(_run_request(spec, wsd, rbd, run_id="run_replay", idem="idem_replay"), spec=spec, store=store)
    req = _step_request(wsd, rbd, run_id="run_replay", step_id="architect")
    first = step_workflow_run(req, spec=spec, store=store, executor=executor)
    second = step_workflow_run(req, spec=spec, store=store, executor=executor)
    conflict = False
    try:
        step_workflow_run(
            _step_request(wsd, rbd, run_id="run_replay", step_id="architect", attempt_index=2),
            spec=spec, store=store, executor=executor,
        )
    except AiFlowError:
        conflict = True
    return {
        "scenario": "idempotent_replay",
        "executor_calls": executor.calls,
        "replayed_without_second_call": executor.calls == 1
        and first.to_durable_state() == second.to_durable_state(),
        "conflict_failed_closed": conflict,
    }


def _scenario_between_step_cancel(spec, wsd, rbd) -> dict[str, Any]:
    store = AiFlowRunStore()
    contracts = {s.step_id: s.output_contract for s in spec.steps}
    executor = _FakeStepExecutor(contracts)
    create_workflow_run(_run_request(spec, wsd, rbd, run_id="run_cancel", idem="idem_cancel"), spec=spec, store=store)
    step_workflow_run(_step_request(wsd, rbd, run_id="run_cancel", step_id="architect"), spec=spec, store=store, executor=executor)
    cancel = request_workflow_cancellation(
        WorkflowCancellationRequest(
            cancel_id="cancel_between", run_id="run_cancel", scope="between_step",
            transaction_ref="txn_smoke", operation_ref="op_smoke", idempotency_key="idem_c1",
            approval_token=AI_FLOW_APPROVAL_TOKEN, enabled=True, operator_gate=True,
        ),
        store=store,
    )
    evidence = summarize_workflow_run(store, run_id="run_cancel")
    return {
        "scenario": "between_step_cancel",
        "cancel_status": cancel.status,
        "final_verdict": evidence.final_verdict,
        "active_run_cancellation_watch": evidence.active_run_cancellation_watch,
        "no_relaunch": executor.calls == 1,
    }


def _scenario_active_run_watch(spec, wsd, rbd) -> dict[str, Any]:
    store = AiFlowRunStore()
    create_workflow_run(_run_request(spec, wsd, rbd, run_id="run_watch", idem="idem_watch"), spec=spec, store=store)
    outcome = StepExecutionOutcome(
        ok=False, step_status="indeterminate", artifact_refs=(),
        interrupted=False, cleanup_verified=False, ambiguous=True,
    )
    cancel = request_workflow_cancellation(
        WorkflowCancellationRequest(
            cancel_id="cancel_active", run_id="run_watch", scope="active_run", step_id="architect",
            transaction_ref="txn_smoke", operation_ref="op_smoke", idempotency_key="idem_c2",
            approval_token=AI_FLOW_APPROVAL_TOKEN, enabled=True, operator_gate=True,
        ),
        store=store, interrupt_outcome=outcome,
    )
    evidence = summarize_workflow_run(store, run_id="run_watch")
    state = evidence.to_durable_state()
    return {
        "scenario": "active_run_cancellation_watch",
        "cancel_status": cancel.status,
        "cancel_error_code": cancel.error_code,
        "active_run_cancellation_watch": evidence.active_run_cancellation_watch,
        "final_verdict": evidence.final_verdict,
        "no_artifact_propagation": state["artifact_refs"] == [],
    }


def run_self_test() -> tuple[int, dict[str, Any]]:
    spec, wsd, rbd = _spec_and_digests()
    scenarios = [
        _scenario_happy_path(spec, wsd, rbd),
        _scenario_pre_step_gate_block(spec, wsd, rbd),
        _scenario_idempotent_replay(spec, wsd, rbd),
        _scenario_between_step_cancel(spec, wsd, rbd),
        _scenario_active_run_watch(spec, wsd, rbd),
    ]
    by_name = {s["scenario"]: s for s in scenarios}
    checks = {
        "happy_path_succeeded": by_name["happy_path"]["final_verdict"] == "succeeded"
        and by_name["happy_path"]["executor_calls"] == 3
        and by_name["happy_path"]["all_steps_completed"],
        "pre_step_gate_zero_calls": by_name["pre_step_gate_missing"]["zero_calls"]
        and by_name["pre_step_gate_missing"]["step_status"] == "gate_blocked",
        "idempotent_replay": by_name["idempotent_replay"]["replayed_without_second_call"]
        and by_name["idempotent_replay"]["conflict_failed_closed"],
        "between_step_cancel_deterministic": by_name["between_step_cancel"]["cancel_status"] == "cancelled"
        and by_name["between_step_cancel"]["final_verdict"] == "cancelled"
        and by_name["between_step_cancel"]["no_relaunch"]
        and by_name["between_step_cancel"]["active_run_cancellation_watch"] is False,
        "active_run_watch_preserved": by_name["active_run_cancellation_watch"]["cancel_status"] == "cancel_ambiguous"
        and by_name["active_run_cancellation_watch"]["cancel_error_code"] == "active_run_cancellation_watch"
        and by_name["active_run_cancellation_watch"]["active_run_cancellation_watch"] is True
        and by_name["active_run_cancellation_watch"]["no_artifact_propagation"],
    }
    ok = all(checks.values())
    summary = {
        "smoke": "sachima-wp4-controlled-ai-flow-local-self-test",
        "ok": ok,
        "mode": "self_test",
        "real_workflow_execution": False,
        "scenarios": scenarios,
        "checks": checks,
        "non_approvals_held": {
            "real_workflow_execution": False,
            "additional_acpx_invocation": False,
            "write_capable_roles": False,
            "auto_routing": False,
            "gateway_involvement_or_mutation": False,
            "feishu_or_im_delivery": False,
            "live_or_default_on_behavior": False,
            "production_config_write": False,
            "real_delivery": False,
        },
    }
    return (0 if ok else 1), summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sachima_ai_flow_local_smoke",
        description="Sachima WP4 controlled AI FLOW local/offline self-test smoke (injected fakes).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the deterministic injected-fakes self-test (the only supported mode in slice 1).",
    )
    args = parser.parse_args(argv)

    if not args.self_test:
        summary = {
            "smoke": "sachima-wp4-controlled-ai-flow-local-self-test",
            "ok": False,
            "mode": "real",
            "error": "real controlled AI FLOW execution is not approved in slice 1; pass --self-test",
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 2

    try:
        exit_code, summary = run_self_test()
    except SmokeError as exc:
        summary = {"smoke": "sachima-wp4-controlled-ai-flow-local-self-test", "ok": False, "error": str(exc)}
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
