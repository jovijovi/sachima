"""Phase E local/offline persistent-session lifecycle state-machine tests.

These exercise the caller-owned, default-off, injected-fakes-only session
lifecycle slice (Option A of the Phase E design packet). No real session
launch, supervisor session call, acpx, or cancellation execution exists here:
every work-like step is an explicitly injected fake outcome.
"""

from __future__ import annotations

import threading
import time
from inspect import signature
from typing import Any, Callable

import pytest

from sachima_supervisor.activity import ROLE_KEY_ALLOWLIST
from sachima_supervisor.activity_session_lifecycle import (
    SESSION_LIFECYCLE_APPROVAL_TOKEN,
    CancellationRequest,
    CancellationRequestResult,
    SessionAbortRequest,
    SessionCloseRequest,
    SessionCreateRequest,
    SessionLifecycleError,
    SessionLifecycleStore,
    SessionRecordResult,
    SessionSendRequest,
    SessionWorkOutcome,
    TurnRecordResult,
    abort_session,
    close_session,
    create_session,
    list_session_turns,
    list_sessions,
    query_session,
    request_cancellation,
    send_session_turn,
)

# --------------------------------------------------------------------------- #
# Constants / no-leak tokens
# --------------------------------------------------------------------------- #
EXPECTED_SESSION_STATE_KEYS = {
    "type",
    "ok",
    "lifecycle_state",
    "phase",
    "session_id",
    "activity_id",
    "transaction_ref",
    "operation_ref",
    "role_key",
    "role_file_digest",
    "session_binding",
    "idempotency_key",
    "request_fingerprint",
    "lease_id",
    "lease_epoch",
    "lease_holder_ref",
    "state_version",
    "turn_count",
    "open_turn_index",
    "max_turns",
    "max_artifacts_per_turn",
    "supervisor_status",
    "evidence_ref",
    "evidence_digest",
    "caller_verdict",
    "error_code",
    "view_model_ref",
}

EXPECTED_TURN_STATE_KEYS = {
    "type",
    "ok",
    "status",
    "session_id",
    "activity_id",
    "turn_index",
    "idempotency_key",
    "request_fingerprint",
    "prompt_ref",
    "lease_epoch_at_launch",
    "supervisor_status",
    "evidence_ref",
    "evidence_digest",
    "artifact_ref_count",
    "error_code",
    "view_model_ref",
}

EXPECTED_CANCEL_STATE_KEYS = {
    "type",
    "ok",
    "status",
    "cancel_id",
    "session_id",
    "activity_id",
    "transaction_ref",
    "operation_ref",
    "turn_index",
    "requested_by_ref",
    "operator_gate",
    "reason_code",
    "idempotency_key",
    "request_fingerprint",
    "lease_id",
    "lease_epoch",
    "lease_holder_ref",
    "evidence_ref",
    "evidence_digest",
    "error_code",
    "view_model_ref",
}

FORBIDDEN_RENDER_TOKENS = (
    "raw prompt",
    "prompt body",
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

ROLE_KEY = "sachima.session_worker"
SESSION_BINDING = "session_binding_ref_001"
EVIDENCE_DIGEST = "sha256:" + "a" * 64


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def _create_request(**overrides: Any) -> SessionCreateRequest:
    base: dict[str, Any] = {
        "activity_id": "activity_session_001",
        "transaction_ref": "claim_txn_session_001",
        "operation_ref": "claim_op_session_001",
        "session_id": "session_local_001",
        "idempotency_key": "idem_session_create_001",
        "role_key": ROLE_KEY,
        "approval_token": SESSION_LIFECYCLE_APPROVAL_TOKEN,
        "enabled": True,
        "role_file_digest": "sha256:" + "f" * 64,
        "prompt_ref": "claim_prompt_session_001",
        "context_refs": ("claim_context_session_001",),
        "cwd_ref": "workspace_ref_sachima_release",
        "allowed_roots_ref": "allowed_roots_ref_sachima_release",
        "lease_id": "lease_session_001",
        "lease_epoch": 3,
        "lease_holder_ref": "controller_ref_sachima_flowweaver",
        "expected_state_version": 0,
        "operator_gate": True,
        "max_turns": 4,
        "max_artifacts_per_turn": 8,
    }
    base.update(overrides)
    return SessionCreateRequest(**base)


def _send_request(**overrides: Any) -> SessionSendRequest:
    base: dict[str, Any] = {
        "activity_id": "activity_session_001",
        "session_id": "session_local_001",
        "transaction_ref": "claim_txn_session_001",
        "operation_ref": "claim_op_session_001",
        "idempotency_key": "idem_session_turn_001",
        "approval_token": SESSION_LIFECYCLE_APPROVAL_TOKEN,
        "enabled": True,
        "session_binding": SESSION_BINDING,
        "prompt_ref": "claim_prompt_turn_001",
        "context_refs": ("claim_context_turn_001",),
        "lease_id": "lease_session_001",
        "lease_epoch": 3,
        "lease_holder_ref": "controller_ref_sachima_flowweaver",
        "expected_state_version": 1,
        "operator_gate": True,
    }
    base.update(overrides)
    return SessionSendRequest(**base)


def _close_request(**overrides: Any) -> SessionCloseRequest:
    base: dict[str, Any] = {
        "activity_id": "activity_session_001",
        "session_id": "session_local_001",
        "transaction_ref": "claim_txn_session_001",
        "operation_ref": "claim_op_session_001",
        "idempotency_key": "idem_session_close_001",
        "approval_token": SESSION_LIFECYCLE_APPROVAL_TOKEN,
        "enabled": True,
        "session_binding": SESSION_BINDING,
        "lease_id": "lease_session_001",
        "lease_epoch": 3,
        "lease_holder_ref": "controller_ref_sachima_flowweaver",
        "expected_state_version": 1,
        "operator_gate": True,
    }
    base.update(overrides)
    return SessionCloseRequest(**base)


def _abort_request(**overrides: Any) -> SessionAbortRequest:
    base: dict[str, Any] = {
        "activity_id": "activity_session_001",
        "session_id": "session_local_001",
        "transaction_ref": "claim_txn_session_001",
        "operation_ref": "claim_op_session_001",
        "idempotency_key": "idem_session_abort_001",
        "approval_token": SESSION_LIFECYCLE_APPROVAL_TOKEN,
        "enabled": True,
        "session_binding": SESSION_BINDING,
        "lease_id": "lease_session_001",
        "lease_epoch": 3,
        "lease_holder_ref": "controller_ref_sachima_flowweaver",
        "expected_state_version": 1,
        "operator_gate": True,
    }
    base.update(overrides)
    return SessionAbortRequest(**base)


def _cancel_request(**overrides: Any) -> CancellationRequest:
    base: dict[str, Any] = {
        "cancel_id": "cancel_session_001",
        "activity_id": "activity_session_001",
        "session_id": "session_local_001",
        "transaction_ref": "claim_txn_session_001",
        "operation_ref": "claim_op_session_001",
        "idempotency_key": "idem_session_cancel_001",
        "approval_token": SESSION_LIFECYCLE_APPROVAL_TOKEN,
        "enabled": True,
        "session_binding": SESSION_BINDING,
        "requested_by_ref": "operator_ref_dog_brother",
        "reason_code": "operator_requested_stop",
        "turn_index": None,
        "lease_id": "lease_session_001",
        "lease_epoch": 3,
        "lease_holder_ref": "controller_ref_sachima_flowweaver",
        "operator_gate": True,
        "execute": False,
    }
    base.update(overrides)
    return CancellationRequest(**base)


def _store() -> SessionLifecycleStore:
    store = SessionLifecycleStore()
    store.grant_lease(
        activity_id="activity_session_001",
        lease_id="lease_session_001",
        lease_epoch=3,
        lease_holder_ref="controller_ref_sachima_flowweaver",
        state_version=0,
    )
    return store


def _open_ok(_request: SessionCreateRequest) -> SessionWorkOutcome:
    return SessionWorkOutcome(
        ok=True,
        supervisor_status="session_open",
        session_binding=SESSION_BINDING,
        evidence_ref="session_evidence_open_001",
        evidence_digest=EVIDENCE_DIGEST,
        artifact_ref_count=0,
    )


def _turn_ok(_request: SessionSendRequest) -> SessionWorkOutcome:
    return SessionWorkOutcome(
        ok=True,
        supervisor_status="turn_completed",
        evidence_ref="session_evidence_turn_001",
        evidence_digest=EVIDENCE_DIGEST,
        artifact_ref_count=1,
    )


def _close_ok(_request: SessionCloseRequest) -> SessionWorkOutcome:
    return SessionWorkOutcome(
        ok=True,
        supervisor_status="session_closed",
        evidence_ref="session_evidence_close_001",
        evidence_digest=EVIDENCE_DIGEST,
        artifact_ref_count=0,
    )


def _abort_ok(_request: SessionAbortRequest) -> SessionWorkOutcome:
    return SessionWorkOutcome(
        ok=True,
        supervisor_status="session_aborted",
        evidence_ref="session_evidence_abort_001",
        evidence_digest=EVIDENCE_DIGEST,
        artifact_ref_count=0,
    )


def _counting(
    counter: dict[str, Any], factory: Callable[[Any], SessionWorkOutcome]
) -> Callable[[Any], SessionWorkOutcome]:
    def _fake(request: Any) -> SessionWorkOutcome:
        counter["calls"] += 1
        counter["last_request"] = request
        return factory(request)

    return _fake


def _assert_no_leaks(state: dict[str, Any]) -> None:
    rendered = repr(state).lower()
    for token in FORBIDDEN_RENDER_TOKENS:
        assert token not in rendered, f"leak token present: {token}"


def _open_session(store: SessionLifecycleStore, counter: dict[str, Any] | None = None):
    counter = counter if counter is not None else {"calls": 0}
    return create_session(_create_request(), store=store, open_session=_counting(counter, _open_ok))


# --------------------------------------------------------------------------- #
# Approval token + default-off gates
# --------------------------------------------------------------------------- #
def test_approval_token_is_exactly_the_phase_e_state_machine_token() -> None:
    assert SESSION_LIFECYCLE_APPROVAL_TOKEN == (
        "approve_agent_run_supervisor_sachima_phase_e_persistent_session_lifecycle_"
        "preflight_state_machine_local_offline_implementation_no_real_session_launch_"
        "no_cancellation_execution_no_real_agent_execution_no_live_no_gateway_no_feishu_"
        "no_production_config_no_real_delivery"
    )


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"enabled": False}, "activity_session_disabled"),
        ({"approval_token": "approve_wrong_scope"}, "activity_session_approval_mismatch"),
        ({"approval_token": ""}, "activity_session_approval_mismatch"),
    ],
)
def test_create_default_off_and_approval_mismatch_fail_closed(
    overrides: dict[str, Any], error_code: str
) -> None:
    store = _store()
    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(SessionLifecycleError) as exc:
        create_session(
            _create_request(**overrides), store=store, open_session=_counting(counter, _open_ok)
        )
    assert exc.value.error_code == error_code
    assert counter["calls"] == 0
    with pytest.raises(SessionLifecycleError):
        query_session(store, activity_id="activity_session_001")


# --------------------------------------------------------------------------- #
# create_session happy path
# --------------------------------------------------------------------------- #
def test_create_opens_one_session_with_sanitized_projection() -> None:
    store = _store()
    counter: dict[str, Any] = {"calls": 0}

    result = create_session(
        _create_request(), store=store, open_session=_counting(counter, _open_ok)
    )
    state = result.to_durable_state()

    assert isinstance(result, SessionRecordResult)
    assert counter["calls"] == 1
    assert result.ok is True
    assert result.lifecycle_state == "session_open"
    assert set(state) == EXPECTED_SESSION_STATE_KEYS
    assert state["type"] == "sachima.supervisor.session_lifecycle_record.v1"
    assert state["phase"] == "session_lifecycle"
    assert state["session_id"] == "session_local_001"
    assert state["activity_id"] == "activity_session_001"
    assert state["transaction_ref"] == "claim_txn_session_001"
    assert state["operation_ref"] == "claim_op_session_001"
    assert state["role_key"] == ROLE_KEY
    assert state["role_file_digest"] == "sha256:" + "f" * 64
    assert state["session_binding"] == SESSION_BINDING
    assert state["idempotency_key"] == "idem_session_create_001"
    assert state["lease_id"] == "lease_session_001"
    assert state["lease_epoch"] == 3
    assert state["lease_holder_ref"] == "controller_ref_sachima_flowweaver"
    assert state["state_version"] == 1
    assert state["turn_count"] == 0
    assert state["open_turn_index"] is None
    assert state["max_turns"] == 4
    assert state["max_artifacts_per_turn"] == 8
    assert state["supervisor_status"] == "session_open"
    assert state["evidence_ref"] == "session_evidence_open_001"
    assert state["evidence_digest"] == EVIDENCE_DIGEST
    assert state["caller_verdict"] is None
    assert state["error_code"] is None
    assert state["view_model_ref"].startswith("session_lifecycle_view_")
    assert len(state["request_fingerprint"]) == 64
    _assert_no_leaks(state)

    assert query_session(store, activity_id="activity_session_001").to_durable_state() == state
    assert tuple(signature(create_session).parameters) == ("request", "store", "open_session")


def test_create_open_fake_failure_marks_session_failed() -> None:
    store = _store()

    def _open_fail(_request: SessionCreateRequest) -> SessionWorkOutcome:
        return SessionWorkOutcome(ok=False, supervisor_status=None, session_binding=None)

    result = create_session(_create_request(), store=store, open_session=_open_fail)
    state = result.to_durable_state()

    assert result.ok is False
    assert result.lifecycle_state == "session_failed"
    assert state["error_code"] == "activity_supervisor_failed"
    assert state["session_binding"] is None
    assert state["state_version"] == 1
    _assert_no_leaks(state)


def test_create_unsafe_open_binding_collapses_to_failed_without_leak() -> None:
    store = _store()

    def _open_unsafe(_request: SessionCreateRequest) -> SessionWorkOutcome:
        return SessionWorkOutcome(
            ok=True,
            supervisor_status="session_open",
            session_binding="oc_" + "privatechat123456",
        )

    result = create_session(_create_request(), store=store, open_session=_open_unsafe)
    state = result.to_durable_state()

    assert result.lifecycle_state == "session_failed"
    assert state["session_binding"] is None
    assert state["error_code"] == "activity_supervisor_failed"
    _assert_no_leaks(state)


# --------------------------------------------------------------------------- #
# create gates: role, material, budget, lease, state version
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "role_key",
    [
        "sachima.claude.architect",
        "sachima.codex.primary_reviewer",
        "../roles/session-worker.json",
        "sachima.unknown_role",
        "",
    ],
)
def test_create_role_not_in_allowlist_fails_closed(role_key: str) -> None:
    store = _store()
    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(SessionLifecycleError) as exc:
        create_session(
            _create_request(role_key=role_key),
            store=store,
            open_session=_counting(counter, _open_ok),
        )
    assert exc.value.error_code == "activity_unknown_role"
    assert counter["calls"] == 0


def test_create_role_allowlist_is_caller_owned_and_reuses_activity_allowlist() -> None:
    # No new session-capable role config is introduced by this slice; the
    # session binds an existing caller-owned role label only.
    assert ROLE_KEY in ROLE_KEY_ALLOWLIST


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("activity_id", "oc_" + "privatechat123456"),
        ("session_id", "ou_" + "privateuser123456"),
        ("transaction_ref", "claim_txn_with_secret_token"),
        ("operation_ref", "claim_op_with_card_json"),
        ("idempotency_key", "idem_with_media_path"),
        ("prompt_ref", "raw prompt body must not travel"),
        ("context_refs", ("claim_context_safe", "card_json_payload_ref")),
        ("context_refs", ["claim_context_not_a_tuple"]),
        ("cwd_ref", "/tmp/raw-media-path.png"),
        ("role_file_digest", "not-a-sha256-digest"),
        ("lease_id", "secret_token_lease"),
        ("lease_holder_ref", "om_" + "privatemsg123456"),
    ],
)
def test_create_unsafe_material_fails_closed(field: str, value: Any) -> None:
    store = _store()
    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(SessionLifecycleError) as exc:
        create_session(
            _create_request(**{field: value}),
            store=store,
            open_session=_counting(counter, _open_ok),
        )
    assert exc.value.error_code == "activity_unsafe_material"
    assert counter["calls"] == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_turns": 0},
        {"max_turns": -1},
        {"max_turns": "4"},
        {"max_artifacts_per_turn": -1},
        {"max_artifacts_per_turn": "8"},
    ],
)
def test_create_invalid_budget_fails_closed(overrides: dict[str, Any]) -> None:
    store = _store()
    with pytest.raises(SessionLifecycleError) as exc:
        create_session(_create_request(**overrides), store=store, open_session=_open_ok)
    assert exc.value.error_code == "activity_budget_exceeded"


@pytest.mark.parametrize(
    "overrides",
    [{"operator_gate": False}, {"operator_gate": "true"}, {"operator_gate": 1}],
)
def test_create_operator_gate_must_be_exact_true(overrides: dict[str, Any]) -> None:
    store = _store()
    with pytest.raises(SessionLifecycleError) as exc:
        create_session(_create_request(**overrides), store=store, open_session=_open_ok)
    assert exc.value.error_code == "activity_precondition_unmet"


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"lease_id": "lease_other"}, "activity_session_lease_lost"),
        ({"lease_holder_ref": "controller_other"}, "activity_session_lease_lost"),
        ({"lease_id": None}, "activity_session_lease_lost"),
        ({"lease_epoch": 4}, "activity_session_lease_lost"),
        ({"lease_epoch": 2}, "activity_session_stale_state"),
        ({"lease_epoch": "3"}, "activity_session_lease_lost"),
        ({"expected_state_version": 1}, "activity_session_stale_state"),
        ({"expected_state_version": "0"}, "activity_session_stale_state"),
    ],
)
def test_create_lease_and_state_version_binding_fails_closed(
    overrides: dict[str, Any], error_code: str
) -> None:
    store = _store()
    with pytest.raises(SessionLifecycleError) as exc:
        create_session(_create_request(**overrides), store=store, open_session=_open_ok)
    assert exc.value.error_code == error_code


def test_create_without_granted_lease_fails_closed() -> None:
    store = SessionLifecycleStore()
    with pytest.raises(SessionLifecycleError) as exc:
        create_session(_create_request(), store=store, open_session=_open_ok)
    assert exc.value.error_code == "activity_session_lease_lost"


# --------------------------------------------------------------------------- #
# create idempotency / single-session invariant
# --------------------------------------------------------------------------- #
def test_create_identical_replay_returns_resident_projection_without_relaunch() -> None:
    store = _store()
    counter: dict[str, Any] = {"calls": 0}
    fake = _counting(counter, _open_ok)

    first = create_session(_create_request(), store=store, open_session=fake)
    second = create_session(_create_request(), store=store, open_session=fake)

    assert counter["calls"] == 1
    assert second.to_durable_state() == first.to_durable_state()


def test_create_conflicting_fingerprint_same_idempotency_fails_closed() -> None:
    store = _store()
    counter: dict[str, Any] = {"calls": 0}
    create_session(_create_request(), store=store, open_session=_counting(counter, _open_ok))

    with pytest.raises(SessionLifecycleError) as exc:
        create_session(
            _create_request(prompt_ref="claim_prompt_session_conflicting"),
            store=store,
            open_session=_counting(counter, _open_ok),
        )
    assert exc.value.error_code == "activity_idempotency_conflict"
    assert counter["calls"] == 1


def test_create_second_non_terminal_session_for_same_activity_fails_closed() -> None:
    store = _store()
    counter: dict[str, Any] = {"calls": 0}
    create_session(_create_request(), store=store, open_session=_counting(counter, _open_ok))

    with pytest.raises(SessionLifecycleError) as exc:
        create_session(
            _create_request(
                idempotency_key="idem_session_create_002",
                session_id="session_local_002",
            ),
            store=store,
            open_session=_counting(counter, _open_ok),
        )
    assert exc.value.error_code == "activity_session_already_open"
    assert counter["calls"] == 1


# --------------------------------------------------------------------------- #
# send_session_turn happy path + lifecycle
# --------------------------------------------------------------------------- #
def test_send_completes_one_turn_and_returns_session_to_open() -> None:
    store = _store()
    _open_session(store)
    counter: dict[str, Any] = {"calls": 0}

    result = send_session_turn(
        _send_request(), store=store, run_turn=_counting(counter, _turn_ok)
    )
    turn_state = result.to_durable_state()

    assert isinstance(result, TurnRecordResult)
    assert counter["calls"] == 1
    assert result.ok is True
    assert result.status == "completed"
    assert set(turn_state) == EXPECTED_TURN_STATE_KEYS
    assert turn_state["type"] == "sachima.supervisor.session_turn_record.v1"
    assert turn_state["session_id"] == "session_local_001"
    assert turn_state["activity_id"] == "activity_session_001"
    assert turn_state["turn_index"] == 1
    assert turn_state["idempotency_key"] == "idem_session_turn_001"
    assert turn_state["prompt_ref"] == "claim_prompt_turn_001"
    assert turn_state["lease_epoch_at_launch"] == 3
    assert turn_state["supervisor_status"] == "turn_completed"
    assert turn_state["evidence_ref"] == "session_evidence_turn_001"
    assert turn_state["artifact_ref_count"] == 1
    assert turn_state["error_code"] is None
    assert turn_state["view_model_ref"].startswith("session_turn_view_")
    assert len(turn_state["request_fingerprint"]) == 64
    _assert_no_leaks(turn_state)

    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["lifecycle_state"] == "session_open"
    assert session["open_turn_index"] is None
    assert session["turn_count"] == 1
    assert session["state_version"] == 2

    turns = list_session_turns(store, activity_id="activity_session_001")
    assert [t.turn_index for t in turns] == [1]
    assert tuple(signature(send_session_turn).parameters) == ("request", "store", "run_turn")


def test_send_claims_turn_before_fake_invocation() -> None:
    store = _store()
    _open_session(store)
    observed: dict[str, Any] = {}

    def _observing(request: SessionSendRequest) -> SessionWorkOutcome:
        session = query_session(store, activity_id="activity_session_001").to_durable_state()
        observed["lifecycle"] = session["lifecycle_state"]
        observed["open_turn_index"] = session["open_turn_index"]
        return _turn_ok(request)

    send_session_turn(_send_request(), store=store, run_turn=_observing)

    assert observed["lifecycle"] == "session_turn"
    assert observed["open_turn_index"] == 1


def test_send_two_sequential_turns_increment_state_and_turn_count() -> None:
    store = _store()
    _open_session(store)

    send_session_turn(_send_request(), store=store, run_turn=_turn_ok)
    send_session_turn(
        _send_request(idempotency_key="idem_session_turn_002", expected_state_version=2),
        store=store,
        run_turn=_turn_ok,
    )

    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["turn_count"] == 2
    assert session["state_version"] == 3
    assert session["lifecycle_state"] == "session_open"
    assert [t.turn_index for t in list_session_turns(store, activity_id="activity_session_001")] == [1, 2]


def test_send_against_missing_session_fails_closed() -> None:
    store = _store()
    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(SessionLifecycleError) as exc:
        send_session_turn(_send_request(), store=store, run_turn=_counting(counter, _turn_ok))
    assert exc.value.error_code == "activity_not_found"
    assert counter["calls"] == 0


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("session_binding", "session_binding_other", "activity_session_binding_mismatch"),
        ("session_binding", None, "activity_session_binding_mismatch"),
        ("lease_id", "lease_other", "activity_session_lease_lost"),
        ("lease_epoch", 2, "activity_session_stale_state"),
        ("lease_epoch", 4, "activity_session_lease_lost"),
        ("expected_state_version", 0, "activity_session_stale_state"),
        ("expected_state_version", 2, "activity_session_stale_state"),
        ("operator_gate", False, "activity_precondition_unmet"),
        ("prompt_ref", "raw prompt body leak", "activity_unsafe_material"),
    ],
)
def test_send_binding_lease_state_and_gate_fail_closed(
    field: str, value: Any, error_code: str
) -> None:
    store = _store()
    _open_session(store)
    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(SessionLifecycleError) as exc:
        send_session_turn(
            _send_request(**{field: value}),
            store=store,
            run_turn=_counting(counter, _turn_ok),
        )
    assert exc.value.error_code == error_code
    assert counter["calls"] == 0


def test_send_identical_replay_returns_resident_turn_without_relaunch() -> None:
    store = _store()
    _open_session(store)
    counter: dict[str, Any] = {"calls": 0}
    fake = _counting(counter, _turn_ok)

    first = send_session_turn(_send_request(), store=store, run_turn=fake)
    second = send_session_turn(_send_request(), store=store, run_turn=fake)

    assert counter["calls"] == 1
    assert second.to_durable_state() == first.to_durable_state()


def test_send_conflicting_fingerprint_fails_closed() -> None:
    store = _store()
    _open_session(store)
    counter: dict[str, Any] = {"calls": 0}
    send_session_turn(_send_request(), store=store, run_turn=_counting(counter, _turn_ok))

    # Same idempotency key, different fingerprint, after the first turn completed.
    with pytest.raises(SessionLifecycleError) as exc:
        send_session_turn(
            _send_request(prompt_ref="claim_prompt_turn_conflicting", expected_state_version=2),
            store=store,
            run_turn=_counting(counter, _turn_ok),
        )
    assert exc.value.error_code == "activity_idempotency_conflict"
    assert counter["calls"] == 1


def test_send_budget_exceeded_fails_closed() -> None:
    store = _store()
    create_session(_create_request(max_turns=1), store=store, open_session=_open_ok)
    send_session_turn(_send_request(), store=store, run_turn=_turn_ok)

    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(SessionLifecycleError) as exc:
        send_session_turn(
            _send_request(idempotency_key="idem_session_turn_002", expected_state_version=2),
            store=store,
            run_turn=_counting(counter, _turn_ok),
        )
    assert exc.value.error_code == "activity_budget_exceeded"
    assert counter["calls"] == 0


def test_send_into_closed_session_fails_closed_without_launch() -> None:
    store = _store()
    _open_session(store)
    close_session(_close_request(), store=store, apply_close=_close_ok)

    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(SessionLifecycleError) as exc:
        send_session_turn(
            _send_request(idempotency_key="idem_session_turn_after_close", expected_state_version=2),
            store=store,
            run_turn=_counting(counter, _turn_ok),
        )
    assert exc.value.error_code == "activity_session_not_open"
    assert counter["calls"] == 0


def test_send_fake_failure_collapses_turn_and_returns_session_to_open() -> None:
    store = _store()
    _open_session(store)

    def _turn_raise(_request: SessionSendRequest) -> SessionWorkOutcome:
        raise RuntimeError("oc_privatechat123456 secret token at /tmp/leak.png traceback")

    result = send_session_turn(_send_request(), store=store, run_turn=_turn_raise)
    turn_state = result.to_durable_state()

    assert result.ok is False
    assert result.status == "failed_retryable"
    assert result.error_code == "activity_supervisor_failed"
    assert turn_state["evidence_ref"] is None
    assert turn_state["artifact_ref_count"] == 0
    _assert_no_leaks(turn_state)

    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["lifecycle_state"] == "session_open"
    assert session["open_turn_index"] is None
    assert session["turn_count"] == 1


def test_failed_turn_is_append_only_and_consumes_turn_budget() -> None:
    store = _store()
    create_session(_create_request(max_turns=2), store=store, open_session=_open_ok)

    def _turn_raise(_request: SessionSendRequest) -> SessionWorkOutcome:
        raise RuntimeError("synthetic runner failure")

    first = send_session_turn(_send_request(), store=store, run_turn=_turn_raise)
    second = send_session_turn(
        _send_request(idempotency_key="idem_session_turn_002", expected_state_version=2),
        store=store,
        run_turn=_turn_ok,
    )

    assert first.status == "failed_retryable"
    assert second.status == "completed"
    turns = list_session_turns(store, activity_id="activity_session_001")
    assert [(turn.turn_index, turn.status) for turn in turns] == [
        (1, "failed_retryable"),
        (2, "completed"),
    ]
    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["turn_count"] == 2


def test_failed_turn_at_budget_blocks_retry_without_overwrite() -> None:
    store = _store()
    create_session(_create_request(max_turns=1), store=store, open_session=_open_ok)

    def _turn_raise(_request: SessionSendRequest) -> SessionWorkOutcome:
        raise RuntimeError("synthetic runner failure")

    send_session_turn(_send_request(), store=store, run_turn=_turn_raise)

    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(SessionLifecycleError) as exc:
        send_session_turn(
            _send_request(idempotency_key="idem_session_turn_002", expected_state_version=2),
            store=store,
            run_turn=_counting(counter, _turn_ok),
        )
    assert exc.value.error_code == "activity_budget_exceeded"
    assert counter["calls"] == 0
    turns = list_session_turns(store, activity_id="activity_session_001")
    assert [(turn.turn_index, turn.status) for turn in turns] == [(1, "failed_retryable")]


def test_send_unsafe_outcome_collapses_to_failed_terminal_without_leak() -> None:
    store = _store()
    _open_session(store)

    def _turn_unsafe(_request: SessionSendRequest) -> SessionWorkOutcome:
        return SessionWorkOutcome(
            ok=True,
            supervisor_status="turn unsafe with secret token",
            evidence_ref="session_evidence_turn",
            evidence_digest="not-a-valid-digest",
            artifact_ref_count=-3,
        )

    result = send_session_turn(_send_request(), store=store, run_turn=_turn_unsafe)
    turn_state = result.to_durable_state()

    assert result.ok is False
    assert result.status == "failed_terminal"
    assert result.error_code == "activity_supervisor_failed"
    assert turn_state["supervisor_status"] is None
    assert turn_state["evidence_ref"] is None
    _assert_no_leaks(turn_state)


def test_send_enforces_max_artifacts_per_turn_budget() -> None:
    store = _store()
    create_session(_create_request(max_artifacts_per_turn=0), store=store, open_session=_open_ok)

    def _turn_with_too_many_artifacts(_request: SessionSendRequest) -> SessionWorkOutcome:
        return SessionWorkOutcome(
            ok=True,
            supervisor_status="turn_completed",
            evidence_ref="session_evidence_turn_001",
            evidence_digest=EVIDENCE_DIGEST,
            artifact_ref_count=99,
        )

    result = send_session_turn(_send_request(), store=store, run_turn=_turn_with_too_many_artifacts)
    turn_state = result.to_durable_state()

    assert result.status == "failed_terminal"
    assert result.error_code == "activity_supervisor_failed"
    assert turn_state["artifact_ref_count"] == 0
    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["turn_count"] == 1


# --------------------------------------------------------------------------- #
# session_query / session_list are read-only
# --------------------------------------------------------------------------- #
def test_query_missing_session_fails_closed() -> None:
    with pytest.raises(SessionLifecycleError) as exc:
        query_session(SessionLifecycleStore(), activity_id="activity_missing")
    assert exc.value.error_code == "activity_not_found"


def test_query_and_list_are_read_only_and_never_run_a_fake() -> None:
    store = _store()
    _open_session(store)
    send_session_turn(_send_request(), store=store, run_turn=_turn_ok)

    first = query_session(store, activity_id="activity_session_001").to_durable_state()
    second = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert first == second
    assert tuple(signature(query_session).parameters) == ("store", "activity_id")

    listed = list_sessions(store, transaction_ref="claim_txn_session_001")
    assert [s.activity_id for s in listed] == ["activity_session_001"]
    assert list_sessions(store, lifecycle_state="session_closed") == []
    assert list_sessions(store, transaction_ref="other_txn") == []


# --------------------------------------------------------------------------- #
# close_session
# --------------------------------------------------------------------------- #
def test_close_graceful_terminal_is_idempotent() -> None:
    store = _store()
    _open_session(store)
    counter: dict[str, Any] = {"calls": 0}

    first = close_session(_close_request(), store=store, apply_close=_counting(counter, _close_ok))
    state = first.to_durable_state()

    assert first.lifecycle_state == "session_closed"
    assert state["state_version"] == 2
    assert state["supervisor_status"] == "session_closed"
    assert counter["calls"] == 1
    _assert_no_leaks(state)

    # Idempotent terminal replay: no second supervisor close.
    second = close_session(
        _close_request(expected_state_version=2),
        store=store,
        apply_close=_counting(counter, _close_ok),
    )
    assert counter["calls"] == 1
    assert second.lifecycle_state == "session_closed"
    assert tuple(signature(close_session).parameters) == ("request", "store", "apply_close")


def test_close_with_in_flight_turn_fails_closed() -> None:
    store = _store()
    _open_session(store)
    close_codes: list[str] = []

    def _turn_blocks_then_close(request: SessionSendRequest) -> SessionWorkOutcome:
        try:
            close_session(
                _close_request(expected_state_version=1), store=store, apply_close=_close_ok
            )
        except SessionLifecycleError as exc:
            close_codes.append(exc.error_code)
        return _turn_ok(request)

    send_session_turn(_send_request(), store=store, run_turn=_turn_blocks_then_close)

    assert close_codes == ["activity_lifecycle_conflict"]


def test_close_of_aborted_session_fails_closed() -> None:
    store = _store()
    _open_session(store)
    abort_session(_abort_request(), store=store, apply_abort=_abort_ok)

    with pytest.raises(SessionLifecycleError) as exc:
        close_session(_close_request(expected_state_version=2), store=store, apply_close=_close_ok)
    assert exc.value.error_code == "activity_lifecycle_conflict"


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("enabled", False, "activity_session_disabled"),
        ("approval_token", "wrong", "activity_session_approval_mismatch"),
        ("session_binding", "session_binding_other", "activity_session_binding_mismatch"),
        ("operator_gate", False, "activity_precondition_unmet"),
        ("lease_epoch", 2, "activity_session_stale_state"),
    ],
)
def test_close_gates_fail_closed(field: str, value: Any, error_code: str) -> None:
    store = _store()
    _open_session(store)
    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(SessionLifecycleError) as exc:
        close_session(
            _close_request(**{field: value}), store=store, apply_close=_counting(counter, _close_ok)
        )
    assert exc.value.error_code == error_code
    assert counter["calls"] == 0


# --------------------------------------------------------------------------- #
# abort_session
# --------------------------------------------------------------------------- #
def test_abort_forced_terminal_is_operator_gated_and_idempotent() -> None:
    store = _store()
    _open_session(store)
    counter: dict[str, Any] = {"calls": 0}

    first = abort_session(_abort_request(), store=store, apply_abort=_counting(counter, _abort_ok))
    state = first.to_durable_state()

    assert first.lifecycle_state == "session_aborted"
    assert state["supervisor_status"] == "session_aborted"
    assert counter["calls"] == 1
    _assert_no_leaks(state)

    second = abort_session(
        _abort_request(expected_state_version=2),
        store=store,
        apply_abort=_counting(counter, _abort_ok),
    )
    assert counter["calls"] == 1
    assert second.lifecycle_state == "session_aborted"
    assert tuple(signature(abort_session).parameters) == ("request", "store", "apply_abort")


def test_abort_requires_operator_gate() -> None:
    store = _store()
    _open_session(store)
    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(SessionLifecycleError) as exc:
        abort_session(
            _abort_request(operator_gate=False),
            store=store,
            apply_abort=_counting(counter, _abort_ok),
        )
    assert exc.value.error_code == "activity_precondition_unmet"
    assert counter["calls"] == 0


def test_abort_is_valid_from_session_turn_in_flight() -> None:
    store = _store()
    _open_session(store)
    abort_states: list[str] = []

    def _turn_then_abort(request: SessionSendRequest) -> SessionWorkOutcome:
        result = abort_session(
            _abort_request(expected_state_version=1), store=store, apply_abort=_abort_ok
        )
        abort_states.append(result.lifecycle_state)
        return _turn_ok(request)

    # The in-flight turn finalize must fail closed because the session was
    # forced terminal underneath it; it must never duplicate-launch.
    with pytest.raises(SessionLifecycleError) as exc:
        send_session_turn(_send_request(), store=store, run_turn=_turn_then_abort)

    assert abort_states == ["session_aborted"]
    assert exc.value.error_code in {
        "activity_session_toctou_conflict",
        "activity_session_turn_ambiguous",
    }
    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["lifecycle_state"] == "session_aborted"


# --------------------------------------------------------------------------- #
# Finalize-time lease/state drift
# --------------------------------------------------------------------------- #
def test_create_finalize_lease_drift_marks_session_failed_not_opening() -> None:
    store = _store()

    def _open_steals_lease(request: SessionCreateRequest) -> SessionWorkOutcome:
        store.grant_lease(
            activity_id=request.activity_id,
            lease_id="lease_session_001",
            lease_epoch=4,
            lease_holder_ref="controller_ref_sachima_flowweaver",
            state_version=0,
        )
        return _open_ok(request)

    with pytest.raises(SessionLifecycleError) as exc:
        create_session(_create_request(), store=store, open_session=_open_steals_lease)
    assert exc.value.error_code == "activity_session_toctou_conflict"
    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["lifecycle_state"] == "session_failed"
    assert session["error_code"] == "activity_session_toctou_conflict"
    assert session["ok"] is False


def test_close_finalize_lease_drift_marks_session_failed_not_closing() -> None:
    store = _store()
    _open_session(store)

    def _close_steals_lease(request: SessionCloseRequest) -> SessionWorkOutcome:
        store.grant_lease(
            activity_id=request.activity_id,
            lease_id="lease_session_001",
            lease_epoch=4,
            lease_holder_ref="controller_ref_sachima_flowweaver",
            state_version=1,
        )
        return _close_ok(request)

    with pytest.raises(SessionLifecycleError) as exc:
        close_session(_close_request(), store=store, apply_close=_close_steals_lease)
    assert exc.value.error_code == "activity_session_toctou_conflict"
    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["lifecycle_state"] == "session_failed"
    assert session["error_code"] == "activity_session_toctou_conflict"
    assert session["ok"] is False


def test_abort_finalize_lease_drift_marks_session_failed_not_aborting() -> None:
    store = _store()
    _open_session(store)

    def _abort_steals_lease(request: SessionAbortRequest) -> SessionWorkOutcome:
        store.grant_lease(
            activity_id=request.activity_id,
            lease_id="lease_session_001",
            lease_epoch=4,
            lease_holder_ref="controller_ref_sachima_flowweaver",
            state_version=1,
        )
        return _abort_ok(request)

    with pytest.raises(SessionLifecycleError) as exc:
        abort_session(_abort_request(), store=store, apply_abort=_abort_steals_lease)
    assert exc.value.error_code == "activity_session_toctou_conflict"
    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["lifecycle_state"] == "session_failed"
    assert session["error_code"] == "activity_session_toctou_conflict"
    assert session["ok"] is False


def test_send_finalize_lease_drift_fails_closed_and_holds_turn_ambiguous() -> None:
    store = _store()
    _open_session(store)

    def _turn_steals_lease(request: SessionSendRequest) -> SessionWorkOutcome:
        # A lease steal/renewal during the in-flight turn must make finalize
        # fail closed instead of completing on a stale epoch.
        store.grant_lease(
            activity_id="activity_session_001",
            lease_id="lease_session_001",
            lease_epoch=4,
            lease_holder_ref="controller_ref_sachima_flowweaver",
            state_version=1,
        )
        return _turn_ok(request)

    with pytest.raises(SessionLifecycleError) as exc:
        send_session_turn(_send_request(), store=store, run_turn=_turn_steals_lease)
    assert exc.value.error_code == "activity_session_toctou_conflict"

    turns = list_session_turns(store, activity_id="activity_session_001")
    assert [t.status for t in turns] == ["turn_ambiguous"]
    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["error_code"] == "activity_session_toctou_conflict"


# --------------------------------------------------------------------------- #
# True concurrency
# --------------------------------------------------------------------------- #
_CONCURRENT = 8
_WAIT = 10.0


def _race(targets: list[Callable[[], Any]]) -> tuple[list[Any], list[str]]:
    total = len(targets)
    align = threading.Barrier(total)
    lock = threading.Lock()
    results: list[Any] = []
    errors: list[str] = []

    def _worker(target: Callable[[], Any]) -> None:
        align.wait(timeout=_WAIT)
        try:
            value = target()
        except SessionLifecycleError as exc:
            with lock:
                errors.append(exc.error_code)
        else:
            with lock:
                results.append(value)

    threads = [threading.Thread(target=_worker, args=(t,)) for t in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_WAIT)
    assert all(not thread.is_alive() for thread in threads)
    return results, errors


def _blocking_fake(
    counter: dict[str, Any],
    release: threading.Event,
    factory: Callable[[Any], SessionWorkOutcome],
) -> Callable[[Any], SessionWorkOutcome]:
    bookkeeping = threading.Lock()

    def _fake(request: Any) -> SessionWorkOutcome:
        with bookkeeping:
            counter["calls"] += 1
        release.wait(timeout=_WAIT)
        return factory(request)

    return _fake


def test_concurrent_identical_create_opens_exactly_one_session() -> None:
    store = _store()
    counter: dict[str, Any] = {"calls": 0}
    release = threading.Event()
    fake = _blocking_fake(counter, release, _open_ok)

    targets = [
        lambda: create_session(_create_request(), store=store, open_session=fake)
        for _ in range(_CONCURRENT)
    ]

    def _drive() -> None:
        deadline = time.monotonic() + _WAIT
        while time.monotonic() < deadline and counter["calls"] < 1:
            time.sleep(0.005)
        time.sleep(0.05)
        release.set()

    driver = threading.Thread(target=_drive)
    driver.start()
    results, errors = _race(targets)
    driver.join(timeout=_WAIT)

    assert counter["calls"] == 1
    assert errors == []
    assert len(results) == _CONCURRENT
    final = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert final["lifecycle_state"] == "session_open"


def test_concurrent_conflicting_create_for_same_activity_fails_closed() -> None:
    store = _store()
    counter: dict[str, Any] = {"calls": 0}
    release = threading.Event()
    fake = _blocking_fake(counter, release, _open_ok)

    targets = [
        (
            lambda i=i: create_session(
                _create_request(
                    idempotency_key=f"idem_create_concurrent_{i:03d}",
                    session_id=f"session_local_{i:03d}",
                ),
                store=store,
                open_session=fake,
            )
        )
        for i in range(_CONCURRENT)
    ]

    def _drive() -> None:
        deadline = time.monotonic() + _WAIT
        while time.monotonic() < deadline and counter["calls"] < 1:
            time.sleep(0.005)
        time.sleep(0.05)
        release.set()

    driver = threading.Thread(target=_drive)
    driver.start()
    results, errors = _race(targets)
    driver.join(timeout=_WAIT)

    assert counter["calls"] == 1
    assert len(results) == 1
    assert errors == ["activity_session_already_open"] * (_CONCURRENT - 1)


def test_concurrent_distinct_sends_launch_at_most_one_turn() -> None:
    store = _store()
    _open_session(store)
    counter: dict[str, Any] = {"calls": 0}
    release = threading.Event()
    fake = _blocking_fake(counter, release, _turn_ok)

    targets = [
        (
            lambda i=i: send_session_turn(
                _send_request(idempotency_key=f"idem_turn_concurrent_{i:03d}"),
                store=store,
                run_turn=fake,
            )
        )
        for i in range(_CONCURRENT)
    ]

    def _drive() -> None:
        deadline = time.monotonic() + _WAIT
        while time.monotonic() < deadline and counter["calls"] < 1:
            time.sleep(0.005)
        time.sleep(0.05)
        release.set()

    driver = threading.Thread(target=_drive)
    driver.start()
    results, errors = _race(targets)
    driver.join(timeout=_WAIT)

    assert counter["calls"] == 1
    completed = [r for r in results if r.status == "completed"]
    assert len(completed) == 1
    assert set(errors) <= {"activity_session_not_open"}
    assert len(errors) == _CONCURRENT - 1
    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["lifecycle_state"] == "session_open"
    assert session["turn_count"] == 1


def test_concurrent_identical_close_runs_one_fake_and_is_idempotent() -> None:
    store = _store()
    _open_session(store)
    counter: dict[str, Any] = {"calls": 0}
    release = threading.Event()
    fake = _blocking_fake(counter, release, _close_ok)

    targets = [
        lambda: close_session(_close_request(), store=store, apply_close=fake)
        for _ in range(_CONCURRENT)
    ]

    def _drive() -> None:
        deadline = time.monotonic() + _WAIT
        while time.monotonic() < deadline and counter["calls"] < 1:
            time.sleep(0.005)
        time.sleep(0.05)
        release.set()

    driver = threading.Thread(target=_drive)
    driver.start()
    results, errors = _race(targets)
    driver.join(timeout=_WAIT)

    assert counter["calls"] == 1
    assert errors == []
    assert all(r.lifecycle_state in {"session_closing", "session_closed"} for r in results)
    final = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert final["lifecycle_state"] == "session_closed"


def test_concurrent_identical_abort_runs_one_fake_and_is_idempotent() -> None:
    store = _store()
    _open_session(store)
    counter: dict[str, Any] = {"calls": 0}
    release = threading.Event()
    fake = _blocking_fake(counter, release, _abort_ok)

    targets = [
        lambda: abort_session(_abort_request(), store=store, apply_abort=fake)
        for _ in range(_CONCURRENT)
    ]

    def _drive() -> None:
        deadline = time.monotonic() + _WAIT
        while time.monotonic() < deadline and counter["calls"] < 1:
            time.sleep(0.005)
        time.sleep(0.05)
        release.set()

    driver = threading.Thread(target=_drive)
    driver.start()
    results, errors = _race(targets)
    driver.join(timeout=_WAIT)

    assert counter["calls"] == 1
    assert errors == []
    final = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert final["lifecycle_state"] == "session_aborted"


# --------------------------------------------------------------------------- #
# Cancellation request (request-state only; no execution)
# --------------------------------------------------------------------------- #
def test_cancel_request_records_durable_request_state_only() -> None:
    store = _store()
    _open_session(store)

    result = request_cancellation(_cancel_request(), store=store)
    state = result.to_durable_state()

    assert isinstance(result, CancellationRequestResult)
    assert result.status == "cancel_requested"
    assert set(state) == EXPECTED_CANCEL_STATE_KEYS
    assert state["type"] == "sachima.supervisor.session_cancel_request_record.v1"
    assert state["cancel_id"] == "cancel_session_001"
    assert state["session_id"] == "session_local_001"
    assert state["operator_gate"] is True
    assert state["reason_code"] == "operator_requested_stop"
    assert state["evidence_ref"] is None
    assert state["evidence_digest"] is None
    assert state["error_code"] is None
    assert state["view_model_ref"].startswith("session_cancel_view_")
    assert len(state["request_fingerprint"]) == 64
    _assert_no_leaks(state)

    # Cancellation request does NOT change session lifecycle (request-only).
    session = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert session["lifecycle_state"] == "session_open"
    assert tuple(signature(request_cancellation).parameters) == ("request", "store")


def test_cancel_execute_attempt_fails_closed_with_not_approved() -> None:
    store = _store()
    _open_session(store)

    with pytest.raises(SessionLifecycleError) as exc:
        request_cancellation(_cancel_request(execute=True), store=store)
    assert exc.value.error_code == "activity_cancel_not_approved"


def test_cancel_requires_operator_gate() -> None:
    store = _store()
    _open_session(store)
    with pytest.raises(SessionLifecycleError) as exc:
        request_cancellation(_cancel_request(operator_gate=False), store=store)
    assert exc.value.error_code == "activity_precondition_unmet"


def test_cancel_idempotent_replay_returns_resident_record() -> None:
    store = _store()
    _open_session(store)

    first = request_cancellation(_cancel_request(), store=store)
    second = request_cancellation(_cancel_request(), store=store)
    assert second.to_durable_state() == first.to_durable_state()


def test_cancel_conflicting_fingerprint_fails_closed() -> None:
    store = _store()
    _open_session(store)
    request_cancellation(_cancel_request(), store=store)

    with pytest.raises(SessionLifecycleError) as exc:
        request_cancellation(_cancel_request(reason_code="operator_emergency_stop"), store=store)
    assert exc.value.error_code == "activity_idempotency_conflict"


def test_cancel_against_terminal_session_is_recorded_as_rejected() -> None:
    store = _store()
    _open_session(store)
    close_session(_close_request(), store=store, apply_close=_close_ok)

    result = request_cancellation(_cancel_request(lease_epoch=3), store=store)
    assert result.status == "rejected"
    _assert_no_leaks(result.to_durable_state())


def test_cancel_against_missing_session_fails_closed() -> None:
    store = _store()
    with pytest.raises(SessionLifecycleError) as exc:
        request_cancellation(_cancel_request(), store=store)
    assert exc.value.error_code == "activity_not_found"


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("enabled", False, "activity_session_disabled"),
        ("approval_token", "wrong", "activity_session_approval_mismatch"),
        ("session_binding", "session_binding_other", "activity_session_binding_mismatch"),
        ("lease_epoch", 2, "activity_session_stale_state"),
        ("requested_by_ref", "oc_" + "privatechat123456", "activity_unsafe_material"),
        ("reason_code", "secret token reason", "activity_unsafe_material"),
    ],
)
def test_cancel_gates_fail_closed(field: str, value: Any, error_code: str) -> None:
    store = _store()
    _open_session(store)
    with pytest.raises(SessionLifecycleError) as exc:
        request_cancellation(_cancel_request(**{field: value}), store=store)
    assert exc.value.error_code == error_code


# --------------------------------------------------------------------------- #
# Store hardening / validate-on-read
# --------------------------------------------------------------------------- #
def test_query_rejects_poisoned_resident_session_state() -> None:
    store = _store()
    result = _open_session(store)
    poisoned = result.to_durable_state()
    poisoned["raw_prompt"] = "raw prompt body with secret token at /tmp/private/path"
    store._sessions["activity_session_001"] = poisoned

    with pytest.raises(SessionLifecycleError) as exc:
        query_session(store, activity_id="activity_session_001")
    assert exc.value.error_code == "activity_unsafe_material"


def test_query_accepts_exact_stored_error_code_without_weakening_string_scan() -> None:
    store = _store()
    result = _open_session(store)
    resident = result.to_durable_state()
    resident["ok"] = False
    resident["error_code"] = "activity_session_toctou_conflict"
    store._sessions["activity_session_001"] = resident

    queried = query_session(store, activity_id="activity_session_001").to_durable_state()
    assert queried["error_code"] == "activity_session_toctou_conflict"

    poisoned = dict(queried)
    poisoned["session_binding"] = "oc_" + "privatechat123456"
    store._sessions["activity_session_001"] = poisoned
    with pytest.raises(SessionLifecycleError) as exc:
        query_session(store, activity_id="activity_session_001")
    assert exc.value.error_code == "activity_unsafe_material"


def test_no_default_runner_fakes_are_required_keyword_only() -> None:
    store = _store()
    with pytest.raises(TypeError):
        create_session(_create_request(), store=store)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        send_session_turn(_send_request(), store=store)  # type: ignore[call-arg]


# --------------------------------------------------------------------------- #
# Forbidden source surface
# --------------------------------------------------------------------------- #
def test_session_lifecycle_source_has_no_forbidden_runtime_or_delivery_surface() -> None:
    from pathlib import Path

    import sachima_supervisor.activity_session_lifecycle as module

    import re

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    # The exact approval token deliberately *names* the surfaces it forbids
    # (``..._no_gateway_no_feishu_...``); it is split across adjacent string
    # fragments in the source, so join the fragments and strip the constant
    # before scanning, so the descriptive token text is not mistaken for a
    # real runtime/delivery surface.
    joined = re.sub(r'"\s*\n\s*"', "", source)
    joined = joined.replace(SESSION_LIFECYCLE_APPROVAL_TOKEN.lower(), "")
    source = joined
    for token in (
        "aiohttp",
        "httpx",
        "lark_oapi",
        "feishu",
        "gateway",
        "webhook",
        "temporalio",
        "subprocess",
        "docker",
        "systemctl",
        "os.system",
        "popen",
        "pexpect",
        "npx",
        "acpx",
        "shell=true",
        "codex exec",
        "claude exec",
    ):
        assert token not in source, f"forbidden runtime/delivery token: {token}"
    for statement in (
        "import requests",
        "from requests",
        "import socket",
        "from socket",
    ):
        assert statement not in source, f"forbidden import surface: {statement}"
