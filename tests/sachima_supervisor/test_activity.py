"""Tests for the supervised local Activity wrapper around sachima_supervisor.

This first implementation slice is local/offline only. It proves an Activity
controller can validate caller-owned refs, resolve an allowlisted role, call an
injected supervisor seam for exec_dry_run, persist sanitized durable state, and
return queryable sanitized results without live/Gateway/real-delivery behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sachima_supervisor.local_offline import (
    IMPLEMENTATION_APPROVAL_TOKEN as LOCAL_OFFLINE_APPROVAL_TOKEN,
    LocalOfflineSupervisorOutcome,
    LocalOfflineSupervisorRequest,
)


ACTIVITY_APPROVAL = (
    "approve_agent_run_supervisor_sachima_supervised_local_activity_"
    "implementation_no_live_no_gateway_no_real_delivery"
)


def _supervisor_outcome(request: LocalOfflineSupervisorRequest) -> LocalOfflineSupervisorOutcome:
    return LocalOfflineSupervisorOutcome(
        status="observed",
        mode=request.mode,
        phase="dry_run",
        supervisor_status="config_preview",
        correlation_label=request.correlation_label,
        error_code=None,
        business_verdict=None,
        caller_verdict="caller_ready",
        artifact_ref_count=1,
        evidence_ref="local_offline_supervisor_evidence_abcdef0123456789",
        evidence_digest="sha256:" + "a" * 64,
        evidence_path="/tmp/raw-path-must-not-leak.json",
        view_model={
            "status": "observed",
            "mode": request.mode,
            "phase": "dry_run",
            "supervisor_status": "config_preview",
            "correlation_label": request.correlation_label,
            "error_code": None,
            "business_verdict": None,
            "caller_verdict": "caller_ready",
            "artifact_ref_count": 1,
            "evidence_ref": "local_offline_supervisor_evidence_abcdef0123456789",
            "evidence_digest": "sha256:" + "a" * 64,
        },
    )


def _request(**overrides: Any) -> Any:
    from sachima_supervisor.activity import SupervisedLocalActivityRequest

    base = {
        "activity_id": "activity-001",
        "transaction_ref": "claim_txn_001",
        "operation_ref": "claim_op_001",
        "idempotency_key": "idem-001",
        "mode": "exec_dry_run",
        "role_key": "sachima.docs_planner",
        "approval_token": ACTIVITY_APPROVAL,
        "enabled": True,
        "prompt_ref": "claim_prompt_001",
        "context_refs": ("claim_context_001",),
        "cwd_ref": "workspace_ref_sachima_release",
        "allowed_roots_ref": "allowed_roots_ref_sachima_release",
        "dry_run_first": True,
    }
    base.update(overrides)
    return SupervisedLocalActivityRequest(**base)


def test_exec_dry_run_activity_builds_local_offline_request_and_returns_sanitized_result() -> None:
    from sachima_supervisor.activity import (
        ActivityStateStore,
        start_supervised_local_activity,
    )

    calls: list[LocalOfflineSupervisorRequest] = []

    def injected_supervisor(request: LocalOfflineSupervisorRequest) -> LocalOfflineSupervisorOutcome:
        calls.append(request)
        return _supervisor_outcome(request)

    store = ActivityStateStore()
    result = start_supervised_local_activity(
        _request(), store=store, invoke_supervisor=injected_supervisor
    )

    assert result.ok is True
    assert result.status == "observed"
    assert result.supervisor_status == "config_preview"
    assert result.mode == "exec_dry_run"
    assert result.phase == "dry_run"
    assert result.activity_id == "activity-001"
    assert result.transaction_ref == "claim_txn_001"
    assert result.operation_ref == "claim_op_001"
    assert result.session_ref is None
    assert result.artifact_ref_count == 1
    assert result.evidence_ref == "local_offline_supervisor_evidence_abcdef0123456789"
    assert result.evidence_digest.startswith("sha256:")
    assert result.view_model_ref.startswith("supervised_local_activity_view_")

    assert len(calls) == 1
    local_request = calls[0]
    assert local_request.enabled is True
    assert local_request.approval_token == LOCAL_OFFLINE_APPROVAL_TOKEN
    assert local_request.mode == "exec_dry_run"
    assert local_request.role is None
    assert local_request.role_file == "roles/sachima/docs-planner.json"
    assert local_request.prompt is None
    assert local_request.context is None
    assert local_request.claim_check_refs == (
        "claim_txn_001",
        "claim_op_001",
        "claim_prompt_001",
        "claim_context_001",
    )

    rendered = repr(result.to_durable_state()).lower()
    assert "/tmp/raw-path" not in rendered
    assert "prompt body" not in rendered
    assert "card_json" not in rendered
    assert "gateway" not in rendered


def test_query_returns_stored_sanitized_state_without_reinvoking_supervisor() -> None:
    from sachima_supervisor.activity import (
        ActivityStateStore,
        query_supervised_local_activity,
        start_supervised_local_activity,
    )

    call_count = 0

    def injected_supervisor(request: LocalOfflineSupervisorRequest) -> LocalOfflineSupervisorOutcome:
        nonlocal call_count
        call_count += 1
        return _supervisor_outcome(request)

    store = ActivityStateStore()
    start_supervised_local_activity(
        _request(), store=store, invoke_supervisor=injected_supervisor
    )

    queried = query_supervised_local_activity(store, activity_id="activity-001")

    assert call_count == 1
    assert queried.ok is True
    assert queried.activity_id == "activity-001"
    assert queried.evidence_ref == "local_offline_supervisor_evidence_abcdef0123456789"
    assert "/tmp/raw-path" not in repr(queried.to_durable_state()).lower()


def test_same_idempotency_key_replays_existing_result_without_second_supervisor_call() -> None:
    from sachima_supervisor.activity import ActivityStateStore, start_supervised_local_activity

    call_count = 0

    def injected_supervisor(request: LocalOfflineSupervisorRequest) -> LocalOfflineSupervisorOutcome:
        nonlocal call_count
        call_count += 1
        return _supervisor_outcome(request)

    store = ActivityStateStore()
    first = start_supervised_local_activity(
        _request(), store=store, invoke_supervisor=injected_supervisor
    )
    second = start_supervised_local_activity(
        _request(), store=store, invoke_supervisor=injected_supervisor
    )

    assert call_count == 1
    assert second.to_durable_state() == first.to_durable_state()


def test_same_idempotency_key_with_different_request_fails_closed() -> None:
    from sachima_supervisor.activity import (
        ActivityStateStore,
        SupervisedLocalActivityError,
        start_supervised_local_activity,
    )

    store = ActivityStateStore()
    start_supervised_local_activity(
        _request(), store=store, invoke_supervisor=_supervisor_outcome
    )

    with pytest.raises(SupervisedLocalActivityError) as exc:
        start_supervised_local_activity(
            _request(operation_ref="claim_op_002"),
            store=store,
            invoke_supervisor=_supervisor_outcome,
        )

    assert exc.value.error_code == "activity_idempotency_conflict"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("role_key", "sachima.unknown_role"),
        ("role_key", "../roles/sachima/docs-planner.json"),
        ("role_key", "oc_" + "privatechat123"),
    ],
)
def test_role_key_must_resolve_through_activity_allowlist(field: str, value: str) -> None:
    from sachima_supervisor.activity import (
        ActivityStateStore,
        SupervisedLocalActivityError,
        start_supervised_local_activity,
    )

    with pytest.raises(SupervisedLocalActivityError) as exc:
        start_supervised_local_activity(
            _request(**{field: value}), store=ActivityStateStore(), invoke_supervisor=_supervisor_outcome
        )

    assert exc.value.error_code in {"activity_unknown_role", "activity_unsafe_material"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("transaction_ref", "oc_" + "privatechat123"),
        ("operation_ref", "claim_op_with_se" + "cret"),
        ("prompt_ref", "claim_prompt_with_to" + "ken"),
        ("context_refs", ("/tmp/private-image.png",)),
        ("cwd_ref", "workspace_ref_with_card" + "_json"),
    ],
)
def test_public_activity_inputs_reject_platform_private_or_secret_shaped_material(
    field: str, value: Any
) -> None:
    from sachima_supervisor.activity import (
        ActivityStateStore,
        SupervisedLocalActivityError,
        start_supervised_local_activity,
    )

    with pytest.raises(SupervisedLocalActivityError) as exc:
        start_supervised_local_activity(
            _request(**{field: value}), store=ActivityStateStore(), invoke_supervisor=_supervisor_outcome
        )

    assert exc.value.error_code == "activity_unsafe_material"


@pytest.mark.parametrize("mode", ["exec", "session_create", "session_send", "send", "gateway_send", "cancel"])
def test_first_activity_slice_accepts_only_exec_dry_run(mode: str) -> None:
    from sachima_supervisor.activity import (
        ActivityStateStore,
        SupervisedLocalActivityError,
        start_supervised_local_activity,
    )

    with pytest.raises(SupervisedLocalActivityError) as exc:
        start_supervised_local_activity(
            _request(mode=mode), store=ActivityStateStore(), invoke_supervisor=_supervisor_outcome
        )

    assert exc.value.error_code == "activity_unsupported_mode"


def test_activity_is_default_off_and_requires_exact_approval() -> None:
    from sachima_supervisor.activity import (
        ActivityStateStore,
        SupervisedLocalActivityError,
        start_supervised_local_activity,
    )

    with pytest.raises(SupervisedLocalActivityError) as disabled:
        start_supervised_local_activity(
            _request(enabled=False), store=ActivityStateStore(), invoke_supervisor=_supervisor_outcome
        )
    assert disabled.value.error_code == "activity_disabled"

    with pytest.raises(SupervisedLocalActivityError) as mismatch:
        start_supervised_local_activity(
            _request(approval_token="approve_" + "wrong_scope"),
            store=ActivityStateStore(),
            invoke_supervisor=_supervisor_outcome,
        )
    assert mismatch.value.error_code == "activity_approval_mismatch"


def test_activity_requires_injected_supervisor_for_first_slice() -> None:
    from sachima_supervisor.activity import (
        ActivityStateStore,
        SupervisedLocalActivityError,
        start_supervised_local_activity,
    )

    with pytest.raises(SupervisedLocalActivityError) as exc:
        start_supervised_local_activity(_request(), store=ActivityStateStore())

    assert exc.value.error_code == "activity_supervisor_injection_required"


def test_first_slice_requires_dry_run_first_flag() -> None:
    from sachima_supervisor.activity import (
        ActivityStateStore,
        SupervisedLocalActivityError,
        start_supervised_local_activity,
    )

    with pytest.raises(SupervisedLocalActivityError) as exc:
        start_supervised_local_activity(
            _request(dry_run_first=False),
            store=ActivityStateStore(),
            invoke_supervisor=_supervisor_outcome,
        )

    assert exc.value.error_code == "activity_dry_run_required"


def test_supervisor_exception_maps_to_stable_non_leaking_result_and_state() -> None:
    from sachima_supervisor.activity import ActivityStateStore, start_supervised_local_activity

    def boom(request: LocalOfflineSupervisorRequest) -> LocalOfflineSupervisorOutcome:
        raise RuntimeError("raw-" + "exception detail with se" + "cret token")

    store = ActivityStateStore()
    result = start_supervised_local_activity(_request(), store=store, invoke_supervisor=boom)

    assert result.ok is False
    assert result.status == "error"
    assert result.error_code == "activity_supervisor_failed"
    assert result.retryable is True
    rendered = repr(result.to_durable_state()).lower()
    assert "exception detail" not in rendered
    assert "traceback" not in rendered
    assert "secret token" not in rendered


def test_unsafe_supervisor_outcome_is_not_trusted_or_persisted() -> None:
    from sachima_supervisor.activity import ActivityStateStore, start_supervised_local_activity

    def unsafe_outcome(request: LocalOfflineSupervisorRequest) -> LocalOfflineSupervisorOutcome:
        return LocalOfflineSupervisorOutcome(
            status="RuntimeError raw-" + "exception unsafe-" + "token",
            mode=request.mode,
            phase="gateway_send",
            supervisor_status="completed unsafe-" + "token",
            correlation_label=request.correlation_label,
            error_code=None,
            business_verdict=None,
            caller_verdict="caller unsafe-" + "token",
            artifact_ref_count=-5,
            evidence_ref="/tmp/raw-evidence-path.json",
            evidence_digest="not-a-digest",
            evidence_path="/tmp/raw-path-must-not-leak.json",
            view_model={"raw": "se" + "cret token value"},
        )

    result = start_supervised_local_activity(
        _request(), store=ActivityStateStore(), invoke_supervisor=unsafe_outcome
    )

    assert result.ok is False
    assert result.status == "error"
    assert result.supervisor_status is None
    assert result.phase == "dry_run"
    assert result.artifact_ref_count == 0
    assert result.evidence_ref is None
    assert result.evidence_digest is None
    assert result.caller_verdict is None
    assert result.error_code == "activity_supervisor_failed"
    rendered = repr(result.to_durable_state()).lower()
    for forbidden in (
        "runtimeerror",
        "exception",
        "unsafe-token",
        "/tmp/raw",
        "secret token",
        "gateway_send",
    ):
        assert forbidden not in rendered


def test_activity_source_has_no_gateway_network_or_delivery_imports() -> None:
    import sachima_supervisor.activity as activity

    source = Path(activity.__file__).read_text(encoding="utf-8").lower()

    for token in ("aiohttp", "httpx", "lark_oapi", "feishu", "webhook"):
        assert token not in source, f"forbidden live/platform token: {token}"
    for statement in (
        "import gateway",
        "from gateway",
        "import requests",
        "from requests",
        "invoke_local_offline_supervisor(",
    ):
        assert statement not in source, f"forbidden runtime/live call surface: {statement}"
