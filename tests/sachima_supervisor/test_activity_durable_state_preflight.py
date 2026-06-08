from __future__ import annotations

from dataclasses import replace
from inspect import signature
from pathlib import Path
from typing import Any

import pytest

from sachima_supervisor.activity_evidence import build_controlled_local_dry_run_evidence
from sachima_supervisor.activity_preflight import (
    DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
    DurableStatePreflightError,
    DurableStatePreflightRequest,
    DurableStatePreflightStore,
    query_durable_state_preflight,
    run_durable_state_preflight,
)


EXPECTED_DURABLE_STATE_KEYS = {
    "type",
    "ok",
    "status",
    "phase",
    "activity_id",
    "transaction_ref",
    "operation_ref",
    "role_key",
    "mode",
    "idempotency_key",
    "prior_dry_run_evidence_digest",
    "lease_id",
    "lease_epoch",
    "lease_holder_ref",
    "state_version",
    "attempt_index",
    "attempt_count",
    "artifact_ref_count",
    "evidence_ref",
    "evidence_digest",
    "caller_verdict",
    "error_code",
    "retryable",
    "view_model_ref",
}


FORBIDDEN_RENDER_TOKENS = (
    "raw prompt",
    "prompt body",
    "platform_private",
    "oc_private",
    "ou_private",
    "om_private",
    "card_json",
    "media path",
    "/tmp/",
    "secret token",
    "traceback",
    "exception detail",
    "gateway",
    "feishu",
    "webhook",
)


def _prior_digest() -> str:
    digest = build_controlled_local_dry_run_evidence()["fixture_digest"]
    assert isinstance(digest, str)
    return digest


def _request(**overrides: Any) -> DurableStatePreflightRequest:
    base = {
        "activity_id": "activity_preflight_001",
        "transaction_ref": "claim_txn_preflight_001",
        "operation_ref": "claim_op_preflight_001",
        "idempotency_key": "idem_preflight_001",
        "mode": "exec_dry_run",
        "role_key": "sachima.docs_planner",
        "approval_token": DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
        "enabled": True,
        "prompt_ref": "claim_prompt_preflight_001",
        "context_refs": ("claim_context_preflight_001",),
        "cwd_ref": "workspace_ref_sachima_release",
        "allowed_roots_ref": "allowed_roots_ref_sachima_release",
        "prior_dry_run_evidence_digest": _prior_digest(),
        "lease_id": "lease_preflight_001",
        "lease_epoch": 3,
        "lease_holder_ref": "controller_ref_sachima_flowweaver",
        "expected_state_version": 0,
        "operator_gate": True,
        "max_attempts": 1,
        "max_artifact_refs": 0,
        "max_evidence_bytes": 0,
    }
    base.update(overrides)
    return DurableStatePreflightRequest(**base)


def _store_with_lease(
    request: DurableStatePreflightRequest | None = None,
    *,
    lease_id: str | None = None,
    lease_epoch: int | None = None,
    lease_holder_ref: str | None = None,
    state_version: int = 0,
) -> DurableStatePreflightStore:
    request = request or _request()
    store = DurableStatePreflightStore()
    store.grant_lease(
        activity_id=request.activity_id,
        lease_id=lease_id if lease_id is not None else request.lease_id,
        lease_epoch=lease_epoch if lease_epoch is not None else request.lease_epoch,
        lease_holder_ref=(
            lease_holder_ref
            if lease_holder_ref is not None
            else request.lease_holder_ref
        ),
        state_version=state_version,
    )
    return store


def _assert_error(
    request: DurableStatePreflightRequest,
    store: DurableStatePreflightStore,
    error_code: str,
) -> None:
    with pytest.raises(DurableStatePreflightError) as exc:
        run_durable_state_preflight(request, store)
    assert exc.value.error_code == error_code


def _assert_no_leaks(state: dict[str, Any]) -> None:
    rendered = repr(state).lower()
    for token in FORBIDDEN_RENDER_TOKENS:
        assert token not in rendered


def test_happy_path_passes_and_returns_sanitized_projection_without_runtime_surface() -> None:
    request = _request()
    store = _store_with_lease(request)

    result = run_durable_state_preflight(request, store)
    state = result.to_durable_state()

    assert result.ok is True
    assert result.status == "preflight_passed"
    assert result.phase == "durable_state_preflight"
    assert set(state) == EXPECTED_DURABLE_STATE_KEYS
    assert state["type"] == "sachima.supervisor.activity_durable_state_preflight.v1"
    assert state["activity_id"] == "activity_preflight_001"
    assert state["transaction_ref"] == "claim_txn_preflight_001"
    assert state["operation_ref"] == "claim_op_preflight_001"
    assert state["role_key"] == "sachima.docs_planner"
    assert state["mode"] == "exec_dry_run"
    assert state["idempotency_key"] == "idem_preflight_001"
    assert state["prior_dry_run_evidence_digest"] == request.prior_dry_run_evidence_digest
    assert state["lease_id"] == "lease_preflight_001"
    assert state["lease_epoch"] == 3
    assert state["lease_holder_ref"] == "controller_ref_sachima_flowweaver"
    assert state["state_version"] == 0
    assert state["attempt_index"] == 1
    assert state["attempt_count"] == 1
    assert state["artifact_ref_count"] == 0
    assert state["evidence_ref"] is None
    assert state["evidence_digest"] is None
    assert state["caller_verdict"] is None
    assert state["error_code"] is None
    assert state["retryable"] is False
    assert state["view_model_ref"].startswith("durable_state_preflight_view_")
    assert query_durable_state_preflight(
        store, activity_id="activity_preflight_001"
    ).to_durable_state() == state
    assert tuple(signature(run_durable_state_preflight).parameters) == ("request", "store")
    _assert_no_leaks(state)


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"enabled": False}, "activity_disabled"),
        (
            {"approval_token": "approve_wrong_scope"},
            "activity_approval_mismatch",
        ),
    ],
)
def test_default_off_and_approval_mismatch_fail_closed(
    overrides: dict[str, Any], error_code: str
) -> None:
    request = _request(**overrides)

    _assert_error(request, _store_with_lease(request), error_code)


@pytest.mark.parametrize(
    "digest",
    [None, "", "not-a-digest", "sha256:nothex", "sha256:" + "b" * 64],
)
def test_prior_dry_run_evidence_digest_missing_malformed_or_wrong_fails_closed(
    digest: str | None,
) -> None:
    request = _request(prior_dry_run_evidence_digest=digest)

    _assert_error(request, _store_with_lease(request), "activity_precondition_unmet")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("activity_id", "oc_" + "privatechat123456"),
        ("transaction_ref", "claim_txn_with_secret_token"),
        ("operation_ref", "claim_op_with_card_json"),
        ("idempotency_key", "idem_with_media_path"),
        ("prompt_ref", "raw prompt body must not travel"),
        ("context_refs", ("claim_context_safe", "card_json_payload_ref")),
        ("cwd_ref", "/tmp/raw-media-path.png"),
        ("allowed_roots_ref", "media_path_/tmp/raw-file.png"),
        ("lease_id", "secret_token_lease"),
        ("lease_holder_ref", "ou_" + "privateuser123456"),
    ],
)
def test_unsafe_refs_platform_private_card_media_or_secret_shaped_fail_closed(
    field: str, value: Any
) -> None:
    request = _request(**{field: value})

    _assert_error(request, _store_with_lease(request), "activity_unsafe_material")


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"role_key": "sachima.unknown_role"}, "activity_unknown_role"),
        ({"role_key": "../roles/sachima/docs-planner.json"}, "activity_unknown_role"),
        ({"mode": "exec"}, "activity_unsupported_mode"),
        ({"mode": "session_create"}, "activity_unsupported_mode"),
        ({"mode": "cancel"}, "activity_unsupported_mode"),
    ],
)
def test_unknown_role_and_unsupported_mode_fail_closed(
    overrides: dict[str, Any], error_code: str
) -> None:
    request = _request(**overrides)

    _assert_error(request, _store_with_lease(request), error_code)


def test_missing_lease_fails_closed() -> None:
    request = _request()

    _assert_error(request, DurableStatePreflightStore(), "activity_lease_lost")


@pytest.mark.parametrize("field", ["lease_id", "lease_holder_ref"])
def test_request_and_stored_none_lease_refs_fail_closed(field: str) -> None:
    request = _request(**{field: None})
    store = DurableStatePreflightStore()
    store.grant_lease(
        activity_id=request.activity_id,
        lease_id=request.lease_id,
        lease_epoch=request.lease_epoch,
        lease_holder_ref=request.lease_holder_ref,
        state_version=request.expected_state_version,
    )

    _assert_error(request, store, "activity_lease_lost")


@pytest.mark.parametrize("field", ["lease_id", "lease_holder_ref"])
def test_stored_none_lease_refs_fail_closed(field: str) -> None:
    request = _request()
    lease = {
        "lease_id": request.lease_id,
        "lease_holder_ref": request.lease_holder_ref,
    }
    lease[field] = None
    store = DurableStatePreflightStore()
    store.grant_lease(
        activity_id=request.activity_id,
        lease_id=lease["lease_id"],
        lease_epoch=request.lease_epoch,
        lease_holder_ref=lease["lease_holder_ref"],
        state_version=request.expected_state_version,
    )

    _assert_error(request, store, "activity_lease_lost")


@pytest.mark.parametrize(
    "lease_overrides",
    [
        {"lease_id": "lease_other"},
        {"lease_holder_ref": "controller_ref_other"},
    ],
)
def test_mismatched_lease_fails_closed(lease_overrides: dict[str, Any]) -> None:
    request = _request()

    _assert_error(
        request,
        _store_with_lease(request, **lease_overrides),
        "activity_lease_lost",
    )


def test_stale_lower_epoch_fails_closed() -> None:
    request = _request(lease_epoch=3)

    _assert_error(
        request,
        _store_with_lease(request, lease_epoch=4),
        "activity_stale_state",
    )


def test_expected_state_version_mismatch_fails_closed() -> None:
    request = _request(expected_state_version=0)

    _assert_error(
        request,
        _store_with_lease(request, state_version=1),
        "activity_toctou_conflict",
    )


def test_idempotent_replay_does_not_create_second_attempt() -> None:
    request = _request()
    store = _store_with_lease(request)

    first = run_durable_state_preflight(request, store)
    second = run_durable_state_preflight(request, store)

    assert second.to_durable_state() == first.to_durable_state()
    assert second.attempt_count == 1
    assert second.attempt_index == 1


def test_same_idempotency_key_with_different_fingerprint_fails_closed() -> None:
    first = _request()
    store = _store_with_lease(first)
    run_durable_state_preflight(first, store)

    conflicting = replace(first, operation_ref="claim_op_preflight_002")

    _assert_error(conflicting, store, "activity_idempotency_conflict")


@pytest.mark.parametrize(
    "overrides",
    [
        {"operator_gate": False},
        {"operator_gate": "true"},
    ],
)
def test_operator_gate_must_be_exact_true(overrides: dict[str, Any]) -> None:
    request = _request(**overrides)

    _assert_error(request, _store_with_lease(request), "activity_precondition_unmet")


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_attempts": 0},
        {"max_attempts": True},
        {"max_attempts": 1.0},
        {"max_artifact_refs": -1},
        {"max_artifact_refs": False},
        {"max_evidence_bytes": -1},
        {"max_evidence_bytes": 0.0},
    ],
)
def test_budget_values_must_be_exact_ints_within_bounds(
    overrides: dict[str, Any]
) -> None:
    request = _request(**overrides)

    _assert_error(request, _store_with_lease(request), "activity_budget_exceeded")


def test_query_is_read_only_and_never_rehydrates_raw_material() -> None:
    request = _request()
    store = _store_with_lease(request)
    state = run_durable_state_preflight(request, store).to_durable_state()

    first_query = query_durable_state_preflight(store, activity_id=request.activity_id)
    second_query = query_durable_state_preflight(store, activity_id=request.activity_id)

    assert first_query.to_durable_state() == state
    assert second_query.to_durable_state() == state
    assert first_query.attempt_count == 1
    _assert_no_leaks(first_query.to_durable_state())


def test_public_put_rejects_malicious_stored_state() -> None:
    request = _request()
    source_store = _store_with_lease(request)
    state = run_durable_state_preflight(request, source_store).to_durable_state()
    state["raw_prompt"] = "raw prompt with secret token at /tmp/private/path"
    store = DurableStatePreflightStore()

    with pytest.raises(DurableStatePreflightError) as exc:
        store.put(
            activity_id=request.activity_id,
            idempotency_key=request.idempotency_key,
            fingerprint="a" * 64,
            state=state,
        )

    assert exc.value.error_code == "activity_unsafe_material"


def test_query_rejects_malicious_resident_state() -> None:
    request = _request()
    source_store = _store_with_lease(request)
    state = run_durable_state_preflight(request, source_store).to_durable_state()
    state["lease_id"] = None
    state["raw_prompt"] = "raw prompt with secret token at /tmp/private/path"
    store = DurableStatePreflightStore()
    store._by_activity[request.activity_id] = state

    with pytest.raises(DurableStatePreflightError) as exc:
        query_durable_state_preflight(store, activity_id=request.activity_id)

    assert exc.value.error_code == "activity_unsafe_material"


def test_get_idempotent_rejects_malicious_resident_fingerprint() -> None:
    request = _request()
    source_store = _store_with_lease(request)
    state = run_durable_state_preflight(request, source_store).to_durable_state()
    store = DurableStatePreflightStore()
    store._by_idempotency[request.idempotency_key] = (
        "raw prompt secret token /tmp/private/path",
        state,
    )

    with pytest.raises(DurableStatePreflightError) as exc:
        store.get_idempotent(request.idempotency_key)

    assert exc.value.error_code == "activity_unsafe_material"


def test_query_missing_activity_fails_closed() -> None:
    with pytest.raises(DurableStatePreflightError) as exc:
        query_durable_state_preflight(
            DurableStatePreflightStore(), activity_id="activity_missing"
        )

    assert exc.value.error_code == "activity_not_found"


def test_activity_preflight_source_has_no_gateway_network_runtime_or_execution_surface() -> None:
    import sachima_supervisor.activity_preflight as activity_preflight

    source = Path(activity_preflight.__file__).read_text(encoding="utf-8").lower()

    for token in (
        "aiohttp",
        "httpx",
        "lark_oapi",
        "feishu",
        "webhook",
        "temporalio",
        "worker",
        "subprocess",
        "docker",
        "systemctl",
        "invoke_local_offline_supervisor(",
    ):
        assert token not in source, f"forbidden live/runtime token: {token}"
    for statement in (
        "import gateway",
        "from gateway",
        "import requests",
        "from requests",
    ):
        assert statement not in source, f"forbidden import/call surface: {statement}"
