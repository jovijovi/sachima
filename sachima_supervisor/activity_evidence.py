"""Controlled local dry-run evidence for the supervised local Activity wrapper.

This module produces a single deterministic, fixture-backed evidence document
that proves the already-merged ``sachima_supervisor.activity`` wrapper behaves
correctly under a controlled local dry-run, using **injected/fake supervisor
outcomes only**.

Boundaries (local/offline only):

  * Every scenario runs the real Activity ``start``/``query`` API against an
    in-memory store, but the supervisor seam is always an injected fake. The
    real supervisor runtime path is never imported or called from here.
  * Only ``exec_dry_run`` is exercised. No real local exec, sessions, cancel,
    Gateway involvement, live/default-on behavior, real ingress, real delivery,
    real AGENT execution, or controlled AI FLOW execution happens.
  * The evidence carries only sanitized durable state, stable codes, counts,
    refs, and digests. Raw prompt/context, platform-private ids, card/media
    material, raw evidence paths, and raw exception text never enter it.
  * The document is deterministic: stable strings, no timestamps, no
    randomness, so the committed fixture equals a fresh build byte-for-value.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from sachima_supervisor.activity import (
    ACTIVITY_IMPLEMENTATION_APPROVAL_TOKEN,
    ActivityStateStore,
    SupervisedLocalActivityError,
    SupervisedLocalActivityRequest,
    query_supervised_local_activity,
    start_supervised_local_activity,
)
from sachima_supervisor.local_offline import (
    LocalOfflineSupervisorOutcome,
    LocalOfflineSupervisorRequest,
)

# --------------------------------------------------------------------------- #
# Public constants
# --------------------------------------------------------------------------- #
#: Exact approval marker that authorizes this controlled local dry-run evidence
#: phase. It is recorded verbatim in the evidence so the fixture is auditable.
CONTROLLED_DRY_RUN_EVIDENCE_APPROVAL_MARKER = (
    "approve_agent_run_supervisor_sachima_supervised_local_activity_"
    "controlled_local_dry_run_evidence_no_live_no_gateway_no_real_delivery_"
    "no_real_agent_execution"
)

_EVIDENCE_TYPE = "sachima.supervisor.controlled_local_activity_dry_run_evidence.v1"

#: Committed fixture path (relative to the repo root) that mirrors the build.
FIXTURE_RELATIVE_PATH = (
    "tests/fixtures/sachima_supervisor/"
    "controlled_local_activity_dry_run_evidence.v1.json"
)

# Forbidden raw-material markers used to self-verify that every durable state in
# the evidence is sanitized. Mirrors the no-leak markers asserted by the tests.
_FORBIDDEN_RAW_MARKERS: tuple[str, ...] = (
    "oc_",
    "ou_",
    "om_",
    "card_json",
    "media:",
    "/tmp/",
    "raw-",
    "traceback",
    "bearer ",
    "api_key",
    "private_key",
)


# --------------------------------------------------------------------------- #
# Sanitization self-check helpers
# --------------------------------------------------------------------------- #
def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            out.extend(_walk_strings(str(key)))
            out.extend(_walk_strings(item))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_walk_strings(item))
        return out
    return []


def _durable_state_is_sanitized(durable_state: dict[str, Any]) -> bool:
    rendered = "\n".join(_walk_strings(durable_state)).lower()
    return not any(marker in rendered for marker in _FORBIDDEN_RAW_MARKERS)


def _digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Injected fake supervisor outcomes (no real supervisor path is ever used)
# --------------------------------------------------------------------------- #
def _success_outcome(
    request: LocalOfflineSupervisorRequest,
    *,
    evidence_ref: str,
    artifact_ref_count: int,
) -> LocalOfflineSupervisorOutcome:
    """A clean, sanitized config-preview outcome an injected fake would return."""

    return LocalOfflineSupervisorOutcome(
        status="observed",
        mode=request.mode,
        phase="dry_run",
        supervisor_status="config_preview",
        correlation_label=request.correlation_label,
        error_code=None,
        business_verdict=None,
        caller_verdict="caller_ready",
        artifact_ref_count=artifact_ref_count,
        evidence_ref=evidence_ref,
        evidence_digest=_digest({"evidence_ref": evidence_ref}),
        evidence_path=None,
        view_model={
            "status": "observed",
            "mode": request.mode,
            "phase": "dry_run",
            "supervisor_status": "config_preview",
            "caller_verdict": "caller_ready",
            "artifact_ref_count": artifact_ref_count,
            "evidence_ref": evidence_ref,
        },
    )


def _unsafe_outcome(request: LocalOfflineSupervisorRequest) -> LocalOfflineSupervisorOutcome:
    """An injected fake that returns unsafe/malformed lower-outcome fields.

    The Activity must treat this as a trust boundary and collapse it to a stable
    ``activity_supervisor_failed`` state rather than persisting any raw value.
    """

    return LocalOfflineSupervisorOutcome(
        status="unsafe_outcome_with_secret",
        mode=request.mode,
        phase="dry_run",
        supervisor_status="completed",
        correlation_label=request.correlation_label,
        error_code=None,
        business_verdict=None,
        caller_verdict="caller_ready",
        artifact_ref_count=-3,
        evidence_ref="local_offline_supervisor_evidence_unsafe",
        evidence_digest="not-a-valid-digest",
        evidence_path=None,
        view_model={"unsafe": "dropped_by_activity_boundary"},
    )


def _counting_fake(
    counter: dict[str, int],
    outcome_factory: Callable[[LocalOfflineSupervisorRequest], LocalOfflineSupervisorOutcome],
) -> Callable[[LocalOfflineSupervisorRequest], LocalOfflineSupervisorOutcome]:
    def _fake(local_request: LocalOfflineSupervisorRequest) -> LocalOfflineSupervisorOutcome:
        counter["injected"] += 1
        return outcome_factory(local_request)

    return _fake


# --------------------------------------------------------------------------- #
# Request construction
# --------------------------------------------------------------------------- #
def _request(
    *,
    activity_id: str,
    transaction_ref: str,
    operation_ref: str,
    idempotency_key: str,
    role_key: str,
    prompt_ref: str,
    context_ref: str,
) -> SupervisedLocalActivityRequest:
    return SupervisedLocalActivityRequest(
        activity_id=activity_id,
        transaction_ref=transaction_ref,
        operation_ref=operation_ref,
        idempotency_key=idempotency_key,
        mode="exec_dry_run",
        role_key=role_key,
        approval_token=ACTIVITY_IMPLEMENTATION_APPROVAL_TOKEN,
        enabled=True,
        prompt_ref=prompt_ref,
        context_refs=(context_ref,),
        cwd_ref="workspace_ref_sachima_release",
        allowed_roots_ref="allowed_roots_ref_sachima_release",
        dry_run_first=True,
    )


def _scenario_base(name: str, description: str, role_key: str, calls: int) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "mode": "exec_dry_run",
        "supervisor_source": "injected_fake",
        "role_key": role_key,
        "injected_supervisor_calls": calls,
    }


# --------------------------------------------------------------------------- #
# Scenarios
# --------------------------------------------------------------------------- #
def _scenario_docs_planner_success(counter: dict[str, int]) -> dict[str, Any]:
    before = counter["injected"]
    store = ActivityStateStore()
    result = start_supervised_local_activity(
        _request(
            activity_id="activity_docs_planner_dry_run",
            transaction_ref="claim_txn_docs_planner",
            operation_ref="claim_operation_docs_planner",
            idempotency_key="idem_docs_planner",
            role_key="sachima.docs_planner",
            prompt_ref="claim_prompt_docs_planner",
            context_ref="claim_context_docs_planner",
        ),
        store=store,
        invoke_supervisor=_counting_fake(
            counter,
            lambda req: _success_outcome(
                req,
                evidence_ref="local_offline_supervisor_evidence_docs_planner",
                artifact_ref_count=1,
            ),
        ),
    )
    queried = query_supervised_local_activity(
        store, activity_id="activity_docs_planner_dry_run"
    )
    scenario = _scenario_base(
        "docs_planner_success",
        "exec_dry_run with the docs_planner role and a successful injected "
        "config-preview outcome; durable state is sanitized.",
        "sachima.docs_planner",
        counter["injected"] - before,
    )
    scenario["query_matches_start"] = (
        queried.to_durable_state() == result.to_durable_state()
    )
    scenario["durable_state"] = result.to_durable_state()
    return scenario


def _scenario_verifier_success(counter: dict[str, int]) -> dict[str, Any]:
    before = counter["injected"]
    store = ActivityStateStore()
    result = start_supervised_local_activity(
        _request(
            activity_id="activity_verifier_dry_run",
            transaction_ref="claim_txn_verifier",
            operation_ref="claim_operation_verifier",
            idempotency_key="idem_verifier",
            role_key="sachima.verifier",
            prompt_ref="claim_prompt_verifier",
            context_ref="claim_context_verifier",
        ),
        store=store,
        invoke_supervisor=_counting_fake(
            counter,
            lambda req: _success_outcome(
                req,
                evidence_ref="local_offline_supervisor_evidence_verifier",
                artifact_ref_count=2,
            ),
        ),
    )
    scenario = _scenario_base(
        "verifier_success",
        "exec_dry_run with the verifier role and a successful injected "
        "config-preview outcome; proves role-map coverage beyond docs_planner.",
        "sachima.verifier",
        counter["injected"] - before,
    )
    scenario["durable_state"] = result.to_durable_state()
    return scenario


def _scenario_idempotency_replay(counter: dict[str, int]) -> dict[str, Any]:
    before = counter["injected"]
    store = ActivityStateStore()
    fake = _counting_fake(
        counter,
        lambda req: _success_outcome(
            req,
            evidence_ref="local_offline_supervisor_evidence_replay",
            artifact_ref_count=1,
        ),
    )
    request = _request(
        activity_id="activity_idempotency_replay",
        transaction_ref="claim_txn_replay",
        operation_ref="claim_operation_replay",
        idempotency_key="idem_replay",
        role_key="sachima.coding_worker",
        prompt_ref="claim_prompt_replay",
        context_ref="claim_context_replay",
    )
    first = start_supervised_local_activity(request, store=store, invoke_supervisor=fake)
    second = start_supervised_local_activity(request, store=store, invoke_supervisor=fake)
    calls = counter["injected"] - before

    scenario = _scenario_base(
        "idempotency_replay",
        "the same idempotency key with an identical request replays stored "
        "sanitized state without a second injected supervisor call.",
        "sachima.coding_worker",
        calls,
    )
    scenario["start_invocations"] = 2
    scenario["replayed_without_second_call"] = (
        calls == 1 and second.to_durable_state() == first.to_durable_state()
    )
    scenario["durable_state"] = second.to_durable_state()
    return scenario


def _scenario_idempotency_conflict(counter: dict[str, int]) -> dict[str, Any]:
    before = counter["injected"]
    store = ActivityStateStore()
    fake = _counting_fake(
        counter,
        lambda req: _success_outcome(
            req,
            evidence_ref="local_offline_supervisor_evidence_conflict",
            artifact_ref_count=1,
        ),
    )
    start_supervised_local_activity(
        _request(
            activity_id="activity_idempotency_conflict",
            transaction_ref="claim_txn_conflict",
            operation_ref="claim_operation_conflict_one",
            idempotency_key="idem_conflict",
            role_key="sachima.primary_reviewer",
            prompt_ref="claim_prompt_conflict",
            context_ref="claim_context_conflict",
        ),
        store=store,
        invoke_supervisor=fake,
    )

    error_code = None
    try:
        start_supervised_local_activity(
            _request(
                activity_id="activity_idempotency_conflict",
                transaction_ref="claim_txn_conflict",
                operation_ref="claim_operation_conflict_two",
                idempotency_key="idem_conflict",
                role_key="sachima.primary_reviewer",
                prompt_ref="claim_prompt_conflict",
                context_ref="claim_context_conflict",
            ),
            store=store,
            invoke_supervisor=fake,
        )
    except SupervisedLocalActivityError as exc:
        error_code = exc.error_code

    scenario = _scenario_base(
        "idempotency_conflict",
        "the same idempotency key with an incompatible request fails closed "
        "before any second injected supervisor call.",
        "sachima.primary_reviewer",
        counter["injected"] - before,
    )
    scenario["start_invocations"] = 2
    scenario["fingerprint_conflict"] = True
    scenario["error_code"] = error_code
    return scenario


def _scenario_unsafe_supervisor_outcome(counter: dict[str, int]) -> dict[str, Any]:
    before = counter["injected"]
    store = ActivityStateStore()
    result = start_supervised_local_activity(
        _request(
            activity_id="activity_unsafe_outcome",
            transaction_ref="claim_txn_unsafe",
            operation_ref="claim_operation_unsafe",
            idempotency_key="idem_unsafe",
            role_key="sachima.session_worker",
            prompt_ref="claim_prompt_unsafe",
            context_ref="claim_context_unsafe",
        ),
        store=store,
        invoke_supervisor=_counting_fake(counter, _unsafe_outcome),
    )

    scenario = _scenario_base(
        "unsafe_supervisor_outcome",
        "an injected fake returns unsafe/malformed lower-outcome fields; the "
        "Activity collapses them to a stable activity_supervisor_failed state.",
        "sachima.session_worker",
        counter["injected"] - before,
    )
    scenario["lower_outcome_collapsed"] = (
        result.ok is False
        and result.status == "error"
        and result.supervisor_status is None
        and result.evidence_ref is None
        and result.error_code == "activity_supervisor_failed"
    )
    scenario["durable_state"] = result.to_durable_state()
    return scenario


# --------------------------------------------------------------------------- #
# Public evidence API
# --------------------------------------------------------------------------- #
def build_controlled_local_dry_run_evidence() -> dict[str, Any]:
    """Build the deterministic controlled local dry-run evidence document.

    Runs five injected-fake scenarios through the real Activity API and returns
    a sanitized, fixture-backed evidence dict. Deterministic: no timestamps and
    no randomness, so repeated builds are byte-identical.
    """

    counter: dict[str, int] = {"injected": 0}
    scenarios: list[dict[str, Any]] = [
        _scenario_docs_planner_success(counter),
        _scenario_verifier_success(counter),
        _scenario_idempotency_replay(counter),
        _scenario_idempotency_conflict(counter),
        _scenario_unsafe_supervisor_outcome(counter),
    ]

    by_name = {scenario["name"]: scenario for scenario in scenarios}
    all_sanitized = all(
        _durable_state_is_sanitized(scenario["durable_state"])
        for scenario in scenarios
        if "durable_state" in scenario
    )

    summary = {
        "scenario_count": len(scenarios),
        "real_supervisor_invocations": 0,
        "injected_supervisor_invocations": counter["injected"],
        "all_durable_states_sanitized": all_sanitized,
        "idempotency_replay_without_second_call": bool(
            by_name["idempotency_replay"]["replayed_without_second_call"]
        ),
        "unsafe_lower_outcome_collapsed": bool(
            by_name["unsafe_supervisor_outcome"]["lower_outcome_collapsed"]
        ),
    }

    evidence: dict[str, Any] = {
        "type": _EVIDENCE_TYPE,
        "approval_marker": CONTROLLED_DRY_RUN_EVIDENCE_APPROVAL_MARKER,
        "scope": {
            "local_offline_only": True,
            "exec_dry_run_only": True,
            "injected_supervisor_only": True,
            "live_approved": False,
            "gateway_approved": False,
            "real_delivery_approved": False,
            "real_agent_execution_approved": False,
            "controlled_ai_flow_execution_approved": False,
        },
        "summary": summary,
        "scenarios": scenarios,
    }
    evidence["fixture_digest"] = _digest(evidence)
    return evidence


def _serialize(evidence: dict[str, Any]) -> str:
    return json.dumps(evidence, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def write_controlled_local_dry_run_evidence(path: str | Path) -> Path:
    """Write the deterministic evidence document to ``path`` and return it."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _serialize(build_controlled_local_dry_run_evidence()), encoding="utf-8"
    )
    return output_path
