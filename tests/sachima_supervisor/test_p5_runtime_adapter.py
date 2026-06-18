"""RED tests for the P5 local/offline, caller-owned, fake/injected runtime adapter.

These tests pin the *desired* API of the next P5 implementation slice: a
deterministic, local/offline runtime adapter that binds behind the existing WP4
``StepExecutor`` Protocol seam (``sachima_supervisor/ai_flow_executor.py``),
default-off / injected, **fake/injected runtime only** — never a real runtime,
Worker, service, socket, subprocess, ``acpx`` or ``npx`` invocation.

Authority:
- docs/plans/2026-06-18-agent-run-supervisor-sachima-p5-local-offline-runtime-adapter-implementation-prep.md
- docs/plans/2026-06-18-agent-run-supervisor-sachima-p5-production-durable-runtime-integration-design-readiness.md

RED-only run: the production module ``sachima_supervisor.p5_runtime_adapter``
does not exist yet, so every behavior test below fails when it lazily imports it
(``ModuleNotFoundError``) — the intended RED signal (missing module / API). The
adapter module is imported *inside* each test (via :func:`_adapter_module`) so
this file still collects cleanly and the failures show as FAILED, not as a
collection ERROR. The forbidden-surface static guard skips while the source is
absent rather than falsely reporting the scan as passed.

The adapter is driven over the real seam types (``StepAttemptRequest`` /
``StepExecutionOutcome``) so a passing implementation is a genuine drop-in
``StepExecutor``; no separate sanitized request type is required by these tests.
"""

from __future__ import annotations

import importlib
import json
import pathlib
from types import SimpleNamespace

import pytest

from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.ai_flow_store import AiFlowRunStore
from sachima_supervisor.ai_flow_spec import (
    RoleBinding,
    canonical_read_only_workflow_mapping,
    role_binding_digest,
    validate_workflow_spec,
    workflow_spec_digest,
)
from sachima_supervisor.activity_ai_flow_orchestration import (
    AI_FLOW_APPROVAL_TOKEN,
    StepAttemptRequest,
    WorkflowRunRequest,
    create_workflow_run,
    step_workflow_run,
    summarize_workflow_run,
)

# --------------------------------------------------------------------------- #
# Canonical local/offline spec context (same bounded linear read-only flow the
# WP4 orchestration tests drive).
# --------------------------------------------------------------------------- #
_SPEC = validate_workflow_spec(canonical_read_only_workflow_mapping())
_WSD = workflow_spec_digest(_SPEC)
_RBD = role_binding_digest(_SPEC)

#: The exact P5 implementation approval token the adapter module must expose as
#: ``P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN``. Split across literals to
#: match the source style; the boundary underscores are part of the token.
_EXPECTED_IMPLEMENTATION_TOKEN = (
    "approve_agent_run_supervisor_sachima_p5_local_offline_caller_owned_runtime_adapter_"
    "implementation_fake_or_injected_runtime_only_behind_executor_protocol_seam_default_off_"
    "no_real_runtime_start_no_worker_auto_start_no_gateway_owned_lifecycle_no_controlled_"
    "ai_flow_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery"
)

_MODULE_NAME = "sachima_supervisor.p5_runtime_adapter"
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "sachima_supervisor" / "p5_runtime_adapter.py"

#: Sanitized artifact-ref keys (claim-check projection — never raw bodies).
_SAFE_ARTIFACT_KEYS = (
    "artifact_id",
    "producer_step_id",
    "content_digest",
    "artifact_kind",
    "byte_count",
    "created_at_ref",
)

#: Input keys that must never cross the seam: raw prompts/cards/media/tool output
#: /signed URLs are claim-check payload, not refs. Any of these in an input
#: mapping must be rejected (``runtime_unsafe_material``) and must never appear in
#: the sanitized JSON projection (SCAN 1) or the serialized history bytes (SCAN 2).
_UNSAFE_INPUT_KEYS = ("raw_prompt", "card_json", "media_path", "tool_output", "signed_url")


# --------------------------------------------------------------------------- #
# Lazy module access + builders (kept out of import time so this file collects).
# --------------------------------------------------------------------------- #
def _adapter_module():
    """Import the not-yet-existing adapter module (RED: ``ModuleNotFoundError``)."""

    return importlib.import_module(_MODULE_NAME)


def _make_adapter(mod, **overrides):
    """Construct a default-off-by-config adapter, enabled with the exact token."""

    base = dict(
        approval_token=mod.P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN,
        enabled=True,
    )
    base.update(overrides)
    return mod.P5LocalOfflineRuntimeAdapter(**base)


def _run_request(**overrides) -> WorkflowRunRequest:
    base = dict(
        run_id="run_p5",
        workflow_id=_SPEC.workflow_id,
        workflow_spec_digest=_WSD,
        role_binding_digest=_RBD,
        approval_ref=_SPEC.approval_ref,
        transaction_ref="txn_p5",
        operation_ref="op_p5",
        idempotency_key="idem_run_p5",
        admission_gate_ref="admission_ref_ok",
        approval_token=AI_FLOW_APPROVAL_TOKEN,
        enabled=True,
        operator_gate=True,
    )
    base.update(overrides)
    return WorkflowRunRequest(**base)


def _step_request(step_id: str, **overrides) -> StepAttemptRequest:
    base = dict(
        run_id="run_p5",
        step_id=step_id,
        attempt_index=1,
        workflow_spec_digest=_WSD,
        role_binding_digest=_RBD,
        input_artifact_digests=(),
        pre_step_gate_ref=f"pre_{step_id}",
        post_step_gate_ref=f"post_{step_id}",
        transaction_ref="txn_p5",
        operation_ref="op_p5",
        idempotency_key=f"idem_{step_id}",
        approval_token=AI_FLOW_APPROVAL_TOKEN,
        enabled=True,
        operator_gate=True,
    )
    base.update(overrides)
    return StepAttemptRequest(**base)


def _binding_for(step_id: str) -> RoleBinding:
    logical_role = next(s.logical_role for s in _SPEC.steps if s.step_id == step_id)
    return next(r for r in _SPEC.roles if r.logical_role == logical_role)


def _safe_input_ref(step_id: str = "architect") -> dict:
    return {
        "artifact_id": f"artifact_{step_id}",
        "producer_step_id": step_id,
        "content_digest": "sha256:" + "a" * 64,
        "artifact_kind": "architecture_packet",
        "byte_count": 11,
        "created_at_ref": "created_at_ref_0001",
    }


# --------------------------------------------------------------------------- #
# 1 — exact approval token / disabled: no-throw fail-closed, zero fake launches
# --------------------------------------------------------------------------- #
def test_constant_equals_exact_implementation_approval_token() -> None:
    mod = _adapter_module()
    assert mod.P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN == _EXPECTED_IMPLEMENTATION_TOKEN


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"approval_token": "wrong_token"}, "runtime_adapter_approval_mismatch"),
        ({"approval_token": ""}, "runtime_adapter_approval_mismatch"),
        ({"enabled": False}, "runtime_adapter_disabled"),
    ],
)
def test_missing_wrong_token_or_disabled_fails_closed_no_launch(overrides, expected_code) -> None:
    mod = _adapter_module()
    adapter = _make_adapter(mod, **overrides)
    outcome = adapter.execute(
        _step_request("architect"), role_binding=_binding_for("architect"), resolved_inputs=()
    )
    # No-throw, fail-closed, stable code, and no fake runtime started.
    assert isinstance(outcome, StepExecutionOutcome)
    assert outcome.ok is False
    assert outcome.error_code == expected_code
    assert adapter.launch_count == 0


# --------------------------------------------------------------------------- #
# 2 — duplicate start / idempotent replay: one fake start, identical projection
# --------------------------------------------------------------------------- #
def test_duplicate_start_converges_to_one_launch_identical_projection() -> None:
    mod = _adapter_module()
    adapter = _make_adapter(mod)
    request = _step_request("architect")
    binding = _binding_for("architect")

    first = adapter.execute(request, role_binding=binding, resolved_inputs=())
    second = adapter.execute(request, role_binding=binding, resolved_inputs=())

    assert first.ok is True
    assert second.ok is True
    # Two identical starts converge to exactly one fake runtime launch.
    assert adapter.launch_count == 1
    # Slice-1 produces exactly one sanitized artifact ref, identical on replay.
    assert len(first.artifact_refs) == 1
    assert first.artifact_refs == second.artifact_refs
    # The projection carries only sanitized keys — never a raw body.
    assert set(first.artifact_refs[0]).issubset(set(_SAFE_ARTIFACT_KEYS))


def test_adapter_drives_wp4_orchestrator_as_step_executor() -> None:
    mod = _adapter_module()
    adapter = _make_adapter(mod)
    store = AiFlowRunStore()
    create_workflow_run(_run_request(), spec=_SPEC, store=store)

    input_digests: tuple[str, ...] = ()
    for step_id in ("architect", "programmer_candidate", "reviewer"):
        result = step_workflow_run(
            _step_request(step_id, input_artifact_digests=input_digests),
            spec=_SPEC,
            store=store,
            executor=adapter,
        )
        assert result.status == "completed"
        produced = [
            artifact for artifact in store.list_artifacts("run_p5")
            if artifact["producer_step_id"] == step_id
        ]
        assert len(produced) == 1
        input_digests = (produced[0]["content_digest"],)

    evidence = summarize_workflow_run(
        store,
        run_id="run_p5",
        spec=_SPEC,
        operator_gate=True,
        terminal_gate_ref="terminal_ref_ok",
    )
    assert adapter.launch_count == 3
    assert evidence.final_verdict == "succeeded"


# --------------------------------------------------------------------------- #
# 3 — conflict fail-closed: same idempotency key, incompatible fingerprint
# --------------------------------------------------------------------------- #
def test_conflicting_replay_fails_closed_no_second_launch() -> None:
    mod = _adapter_module()
    adapter = _make_adapter(mod)
    binding = _binding_for("architect")

    adapter.execute(_step_request("architect"), role_binding=binding, resolved_inputs=())
    # Same idempotency key (``idem_architect``) but an incompatible fingerprint
    # (different attempt_index) must fail closed with a stable code, no relaunch.
    conflict = adapter.execute(
        _step_request("architect", attempt_index=2), role_binding=binding, resolved_inputs=()
    )

    assert isinstance(conflict, StepExecutionOutcome)
    assert conflict.ok is False
    assert conflict.error_code == "runtime_adapter_idempotency_conflict"
    assert adapter.launch_count == 1


# --------------------------------------------------------------------------- #
# 4 — query snapshot consistency: stable snapshot_version, no re-invocation
# --------------------------------------------------------------------------- #
def test_query_snapshot_is_consistent_without_reinvoking_runtime() -> None:
    mod = _adapter_module()
    adapter = _make_adapter(mod)
    request = _step_request("architect")
    adapter.execute(request, role_binding=_binding_for("architect"), resolved_inputs=())

    snapshot_one = adapter.query(run_id=request.run_id, step_id=request.step_id)
    launches_after_first_query = adapter.launch_count
    snapshot_two = adapter.query(run_id=request.run_id, step_id=request.step_id)

    # Querying never re-invokes the fake runtime.
    assert adapter.launch_count == launches_after_first_query == 1
    # Snapshot is stable and carries a sanitized stable state + snapshot_version.
    assert snapshot_one == snapshot_two
    assert isinstance(snapshot_one["snapshot_version"], int)
    assert isinstance(snapshot_one["state"], str)


# --------------------------------------------------------------------------- #
# 5 — unsafe material rejection + no-leak (SCAN 1 JSON projection, SCAN 2 bytes)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("unsafe_key", _UNSAFE_INPUT_KEYS)
def test_unsafe_material_rejected_and_never_leaked(unsafe_key) -> None:
    mod = _adapter_module()
    adapter = _make_adapter(mod)
    # Canary value is assembled at runtime (no secret-shaped literal) so the
    # no-leak assertions test the projection, not a scanner false positive.
    canary = "leak" + "-canary-" + unsafe_key + "-" + "do-not-store"
    unsafe_inputs = ({**_safe_input_ref(), unsafe_key: canary},)

    outcome = adapter.execute(
        _step_request("architect"), role_binding=_binding_for("architect"),
        resolved_inputs=unsafe_inputs,
    )

    # Rejected fail-closed before any fake runtime starts.
    assert outcome.ok is False
    assert outcome.error_code == "runtime_unsafe_material"
    assert adapter.launch_count == 0
    # SCAN 2 — serialized event/history bytes never contain the raw unsafe value.
    history_bytes = adapter.serialized_history_bytes()
    assert isinstance(history_bytes, (bytes, bytearray))
    assert canary.encode("utf-8") not in history_bytes
    # SCAN 1 — sanitized JSON projection contains neither the value nor the key.
    projection_json = json.dumps(adapter.history_projection())
    assert canary not in projection_json
    assert unsafe_key not in projection_json


@pytest.mark.parametrize(
    "unsafe_run_id",
    ["raw_prompt_secret", "raw-prompt-secret", "raw prompt secret", "raw/prompt/secret"],
)
def test_unsafe_request_identifier_rejected_and_not_projected(unsafe_run_id) -> None:
    mod = _adapter_module()
    adapter = _make_adapter(mod)
    unsafe_key = "raw_prompt"

    outcome = adapter.execute(
        _step_request("architect", run_id=unsafe_run_id),
        role_binding=_binding_for("architect"),
        resolved_inputs=(),
    )

    assert outcome.ok is False
    assert outcome.error_code == "runtime_unsafe_material"
    assert adapter.launch_count == 0
    history_json = json.dumps(adapter.history_projection())
    assert unsafe_run_id not in history_json
    assert unsafe_key not in history_json
    snapshot = adapter.query(run_id=unsafe_run_id, step_id="architect")
    snapshot_json = json.dumps(snapshot)
    assert unsafe_run_id not in snapshot_json
    assert unsafe_key not in snapshot_json


def test_controls_are_no_throw_for_malformed_identifiers() -> None:
    mod = _adapter_module()
    adapter = _make_adapter(mod)
    malformed = object()

    snapshot = adapter.query(run_id=malformed, step_id=None)  # type: ignore[arg-type]
    recovered = adapter.recover(run_id=None, step_id=malformed)  # type: ignore[arg-type]
    cancelled = adapter.cancel(
        run_id=malformed,  # type: ignore[arg-type]
        step_id=None,  # type: ignore[arg-type]
        scope="between_step",
        idempotency_key=malformed,  # type: ignore[arg-type]
    )

    assert snapshot["state"] == "not_found"
    assert recovered["state"] == "not_found"
    assert isinstance(cancelled, StepExecutionOutcome)
    assert cancelled.ok is False


@pytest.mark.parametrize(
    ("request_overrides", "resolved_inputs"),
    [
        ({"input_artifact_digests": object()}, ()),
        ({"attempt_index": "not_an_int"}, ()),
        ({}, (object(),)),
        ({}, ({"artifact_id": "artifact_architect"}, object())),
        ({}, ({"artifact_id": object()},)),
    ],
)
def test_execute_is_no_throw_for_malformed_request_or_inputs(
    request_overrides, resolved_inputs
) -> None:
    mod = _adapter_module()
    adapter = _make_adapter(mod)
    base = _step_request("architect", **request_overrides)
    request = SimpleNamespace(**base.__dict__)

    outcome = adapter.execute(
        request,
        role_binding=_binding_for("architect"),
        resolved_inputs=resolved_inputs,  # type: ignore[arg-type]
    )

    assert isinstance(outcome, StepExecutionOutcome)
    assert outcome.ok is False
    assert outcome.error_code == "runtime_adapter_invalid_request"
    assert adapter.launch_count == 0


# --------------------------------------------------------------------------- #
# 6 — durable claim-store / restart-recovery: local/offline only
# --------------------------------------------------------------------------- #
def test_durable_claim_store_replays_after_adapter_restart(tmp_path) -> None:
    mod = _adapter_module()
    store_path = tmp_path / "p5_claim_store.json"
    request = _step_request("architect")
    binding = _binding_for("architect")

    first_adapter = _make_adapter(
        mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path)
    )
    first = first_adapter.execute(request, role_binding=binding, resolved_inputs=())

    restarted_adapter = _make_adapter(
        mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path)
    )
    replay = restarted_adapter.execute(request, role_binding=binding, resolved_inputs=())

    assert first.ok is True
    assert replay.ok is True
    assert first.artifact_refs == replay.artifact_refs
    assert first_adapter.launch_count == 1
    # Recovered idempotent replay must not relaunch after process/object restart.
    assert restarted_adapter.launch_count == 0
    snapshot = restarted_adapter.query(run_id=request.run_id, step_id=request.step_id)
    assert snapshot["state"] == "completed"
    assert snapshot["artifact_refs"] == [dict(first.artifact_refs[0])]


def test_durable_claim_store_forged_persisted_outcome_after_restart_fails_closed(tmp_path) -> None:
    mod = _adapter_module()
    store_path = tmp_path / "p5_claim_store.json"
    request = _step_request("architect")
    binding = _binding_for("architect")

    first_adapter = _make_adapter(
        mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path)
    )
    first = first_adapter.execute(request, role_binding=binding, resolved_inputs=())
    assert first.ok is True

    data = json.loads(store_path.read_text(encoding="utf-8"))
    data["records"][0]["outcome"]["artifact_refs"][0]["artifact_id"] = "p5_artifact_forged_safe_id"
    data["records"][0]["outcome"]["artifact_refs"][0]["content_digest"] = "sha256:" + "b" * 64
    store_path.write_text(json.dumps(data), encoding="utf-8")

    restarted_adapter = _make_adapter(
        mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path)
    )
    replay = restarted_adapter.execute(request, role_binding=binding, resolved_inputs=())

    assert replay.ok is False
    assert replay.error_code == "runtime_adapter_store_invalid"
    assert restarted_adapter.launch_count == 0
    snapshot = restarted_adapter.query(run_id=request.run_id, step_id=request.step_id)
    assert snapshot["state"] == "store_invalid"
    assert snapshot["error_code"] == "runtime_adapter_store_invalid"


def test_durable_claim_store_conflict_after_restart_fails_closed_no_launch(tmp_path) -> None:
    mod = _adapter_module()
    store_path = tmp_path / "p5_claim_store.json"
    binding = _binding_for("architect")

    first_adapter = _make_adapter(
        mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path)
    )
    first_adapter.execute(_step_request("architect"), role_binding=binding, resolved_inputs=())

    restarted_adapter = _make_adapter(
        mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path)
    )
    conflict = restarted_adapter.execute(
        _step_request("architect", attempt_index=2), role_binding=binding, resolved_inputs=()
    )

    assert conflict.ok is False
    assert conflict.error_code == "runtime_adapter_idempotency_conflict"
    assert restarted_adapter.launch_count == 0


def test_durable_claim_store_same_step_new_idempotency_after_restart_fails_closed(tmp_path) -> None:
    mod = _adapter_module()
    store_path = tmp_path / "p5_claim_store.json"
    binding = _binding_for("architect")

    first_adapter = _make_adapter(
        mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path)
    )
    first = first_adapter.execute(_step_request("architect"), role_binding=binding, resolved_inputs=())
    assert first.ok is True

    restarted_adapter = _make_adapter(
        mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path)
    )
    conflict = restarted_adapter.execute(
        _step_request("architect", idempotency_key="idem_architect_second"),
        role_binding=binding,
        resolved_inputs=(),
    )

    assert conflict.ok is False
    assert conflict.error_code == "runtime_adapter_step_conflict"
    assert restarted_adapter.launch_count == 0
    assert mod.P5LocalOfflineDurableClaimStore(store_path).load_error_code is None
    snapshot = restarted_adapter.query(run_id="run_p5", step_id="architect")
    assert snapshot["state"] == "completed"
    assert snapshot["artifact_refs"] == [dict(first.artifact_refs[0])]


def test_durable_claim_store_recover_after_restart_no_reinvoke(tmp_path) -> None:
    mod = _adapter_module()
    store_path = tmp_path / "p5_claim_store.json"
    request = _step_request("architect")
    first_adapter = _make_adapter(
        mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path)
    )
    first_adapter.execute(request, role_binding=_binding_for("architect"), resolved_inputs=())

    restarted_adapter = _make_adapter(
        mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path)
    )
    recovered = restarted_adapter.recover(run_id=request.run_id, step_id=request.step_id)

    assert recovered["state"] == "completed"
    assert restarted_adapter.launch_count == 0


def test_durable_claim_store_dirty_resident_state_fails_closed_no_launch(tmp_path) -> None:
    mod = _adapter_module()
    store_path = tmp_path / "p5_claim_store.json"
    store_path.write_text(
        json.dumps(
            {
                "type": "sachima.supervisor.p5_runtime_adapter_claim_store.v1",
                "schema_version": 1,
                "records": [
                    {
                        "idempotency_key": "idem_architect",
                        "run_id": "raw_prompt_secret",
                        "step_id": "architect",
                        "fingerprint": "f" * 64,
                        "state": "completed",
                        "snapshot_version": 1,
                        "outcome": {"ok": True, "step_status": "completed", "artifact_refs": []},
                    }
                ],
                "history": [],
            }
        ),
        encoding="utf-8",
    )

    adapter = _make_adapter(mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path))
    outcome = adapter.execute(
        _step_request("architect"), role_binding=_binding_for("architect"), resolved_inputs=()
    )

    assert outcome.ok is False
    assert outcome.error_code == "runtime_adapter_store_invalid"
    assert adapter.launch_count == 0
    projection_json = json.dumps(adapter.history_projection())
    assert "raw_prompt" not in projection_json


def test_durable_claim_store_file_bytes_never_contain_unsafe_rejected_values(tmp_path) -> None:
    mod = _adapter_module()
    store_path = tmp_path / "p5_claim_store.json"
    adapter = _make_adapter(mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path))
    unsafe_key = "raw_prompt"
    canary = "leak" + "-canary-" + unsafe_key + "-" + "do-not-store"

    outcome = adapter.execute(
        _step_request("architect"),
        role_binding=_binding_for("architect"),
        resolved_inputs=({**_safe_input_ref(), unsafe_key: canary},),
    )

    assert outcome.ok is False
    assert outcome.error_code == "runtime_unsafe_material"
    assert canary.encode("utf-8") not in adapter.serialized_history_bytes()
    assert canary.encode("utf-8") not in store_path.read_bytes()


def test_durable_claim_store_write_failure_fails_closed_without_launch(tmp_path) -> None:
    mod = _adapter_module()
    blocked_parent = tmp_path / "blocked_parent"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    store_path = blocked_parent / "p5_claim_store.json"
    adapter = _make_adapter(mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path))

    outcome = adapter.execute(
        _step_request("architect"), role_binding=_binding_for("architect"), resolved_inputs=()
    )

    assert outcome.ok is False
    assert outcome.error_code == "runtime_adapter_store_write_failed"
    assert adapter.launch_count == 0
    snapshot = adapter.query(run_id="run_p5", step_id="architect")
    assert snapshot["state"] == "store_invalid"
    assert snapshot["error_code"] == "runtime_adapter_store_write_failed"


def test_durable_claim_store_duplicate_step_records_fail_closed(tmp_path) -> None:
    mod = _adapter_module()
    store_path = tmp_path / "p5_claim_store.json"
    adapter = _make_adapter(mod, claim_store=mod.P5LocalOfflineDurableClaimStore(store_path))
    first = adapter.execute(
        _step_request("architect"), role_binding=_binding_for("architect"), resolved_inputs=()
    )
    assert first.ok is True

    data = json.loads(store_path.read_text(encoding="utf-8"))
    duplicate = dict(data["records"][0])
    duplicate["idempotency_key"] = "idem_architect_duplicate"
    duplicate["fingerprint"] = "e" * 64
    duplicate["outcome"] = dict(data["records"][0]["outcome"])
    duplicate["outcome"]["artifact_refs"] = [
        dict(data["records"][0]["outcome"]["artifact_refs"][0])
    ]
    duplicate["outcome"]["artifact_refs"][0]["artifact_id"] = "p5_artifact_run_p5_architect_2"
    data["records"].append(duplicate)
    store_path.write_text(json.dumps(data), encoding="utf-8")

    dirty_store = mod.P5LocalOfflineDurableClaimStore(store_path)
    assert dirty_store.load_error_code == "runtime_adapter_store_invalid"
    restarted = _make_adapter(mod, claim_store=dirty_store)
    outcome = restarted.execute(
        _step_request("architect"), role_binding=_binding_for("architect"), resolved_inputs=()
    )
    assert outcome.ok is False
    assert outcome.error_code == "runtime_adapter_store_invalid"
    assert restarted.launch_count == 0


def test_durable_claim_store_dirty_history_event_fails_closed(tmp_path) -> None:
    mod = _adapter_module()
    store_path = tmp_path / "p5_claim_store.json"
    store_path.write_text(
        json.dumps(
            {
                "type": "sachima.supervisor.p5_runtime_adapter_claim_store.v1",
                "schema_version": 1,
                "records": [],
                "history": [
                    {
                        "event": "not a safe ref",
                        "sequence": 1,
                        "run_id": "run with spaces",
                        "step_id": None,
                        "error_code": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    dirty_store = mod.P5LocalOfflineDurableClaimStore(store_path)
    assert dirty_store.load_error_code == "runtime_adapter_store_invalid"
    adapter = _make_adapter(mod, claim_store=dirty_store)
    outcome = adapter.execute(
        _step_request("architect"), role_binding=_binding_for("architect"), resolved_inputs=()
    )
    assert outcome.ok is False
    assert outcome.error_code == "runtime_adapter_store_invalid"
    assert adapter.launch_count == 0


# --------------------------------------------------------------------------- #
# 7 — active-run cancellation WATCH (WP3b): unconfirmed never promotes to clean
# --------------------------------------------------------------------------- #
def test_unconfirmed_active_run_cancel_holds_watch_never_cancelled() -> None:
    mod = _adapter_module()
    adapter = _make_adapter(mod)
    request = _step_request("architect")
    adapter.execute(request, role_binding=_binding_for("architect"), resolved_inputs=())

    # No confirmed interrupt outcome (no interrupted + cleanup_verified): the
    # active-run cancel is unconfirmed and must hold the WATCH, never cancelled.
    result = adapter.cancel(
        run_id=request.run_id,
        step_id=request.step_id,
        scope="active_run",
        idempotency_key="idem_cancel_p5",
    )

    assert isinstance(result, StepExecutionOutcome)
    assert result.ok is False
    assert result.ambiguous is True
    assert result.interrupted is False
    assert result.step_status == "cancel_ambiguous"
    assert result.step_status != "cancelled"
    assert result.error_code == "active_run_cancellation_watch"
    # No artifact propagation and no relaunch from the ambiguous cancel.
    assert result.artifact_refs == ()
    assert adapter.launch_count == 1


# --------------------------------------------------------------------------- #
# 7 — forbidden-surface static guard (skips while the source is absent in RED)
# --------------------------------------------------------------------------- #
def test_adapter_source_has_no_forbidden_runtime_surface() -> None:
    if not _MODULE_PATH.exists():
        pytest.skip(
            "p5_runtime_adapter source not implemented yet (RED) — static guard "
            "cannot scan absent source; not reporting it as passed coverage"
        )
    source = _MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "subprocess", "socket", "temporalio", "acpx", "npx",
        "Gateway", "gateway", "Feishu", "feishu",
    )
    present = [token for token in forbidden if token in source]
    assert present == [], f"forbidden runtime surface in adapter source: {present}"
