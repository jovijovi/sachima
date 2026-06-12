from __future__ import annotations

import hashlib
import json
import threading
import time
from inspect import signature
from pathlib import Path
from typing import Any, Callable

import pytest

from sachima_supervisor.activity_controlled_exec import (
    CONTROLLED_EXEC_FUTURE_ROLE_KEYS,
    CONTROLLED_EXEC_MODE,
    CONTROLLED_EXEC_MODES,
    CONTROLLED_EXEC_ROLE_ALLOWLIST,
    CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN,
    FORBIDDEN_RUNNER_BASENAMES,
    ControlledLocalExecClaimStore,
    ControlledLocalExecError,
    ControlledLocalExecRequest,
    PinnedLocalAcpxProvenance,
    query_controlled_local_exec,
    start_controlled_local_exec,
    verify_pinned_local_acpx_binary,
)
from sachima_supervisor.activity_evidence import build_controlled_local_dry_run_evidence
from sachima_supervisor.activity_preflight import (
    DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
    DurableStatePreflightRequest,
    DurableStatePreflightStore,
    run_durable_state_preflight,
)
from sachima_supervisor.local_offline import (
    IMPLEMENTATION_APPROVAL_TOKEN as LOCAL_OFFLINE_APPROVAL_TOKEN,
    LocalOfflineSupervisorOutcome,
    LocalOfflineSupervisorRequest,
)


EXPECTED_CLAIM_STATE_KEYS = {
    "type",
    "ok",
    "status",
    "mode",
    "phase",
    "activity_id",
    "transaction_ref",
    "operation_ref",
    "role_key",
    "idempotency_key",
    "role_file_digest",
    "prior_dry_run_evidence_digest",
    "preflight_view_ref",
    "approval_ref",
    "lease_id",
    "lease_epoch",
    "lease_holder_ref",
    "state_version",
    "attempt_index",
    "attempt_count",
    "supervisor_status",
    "artifact_ref_count",
    "evidence_ref",
    "evidence_digest",
    "business_verdict",
    "caller_verdict",
    "error_code",
    "retryable",
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

ROLE_FILE_REF = CONTROLLED_EXEC_ROLE_ALLOWLIST["sachima.codex.primary_reviewer"]

PINNED_PLACEHOLDER_BINARY = "/opt/sachima/runners/acpx-0.10.0/acpx"


def _evidence_digest() -> str:
    digest = build_controlled_local_dry_run_evidence()["fixture_digest"]
    assert isinstance(digest, str)
    return digest


def _role_mapping(**overrides: Any) -> dict[str, Any]:
    mapping: dict[str, Any] = {
        "schema_version": 1,
        "role_id": "sachima.codex.primary_reviewer",
        "display_name": "Sachima Codex primary reviewer (read-only one-shot exec)",
        "description": "Read-only Codex primary reviewer for controlled local one-shot exec.",
        "runner": {
            "type": "acpx",
            "acpx_version": "0.10.0",
            "acpx_binary": PINNED_PLACEHOLDER_BINARY,
            "adapter_agent": "codex",
            "model": None,
        },
        "workspace": {
            "default_cwd": "/workspace/sachima",
            "allowed_roots": ["/workspace/sachima"],
            "allowed_roots_security_boundary": False,
        },
        "permissions": {
            "read": True,
            "search": True,
            "write": False,
            "execute": False,
            "terminal": False,
            "delete": False,
            "move": False,
            "fetch": False,
            "switch_mode": False,
            "other": False,
        },
        "session": {"strategy": "exec"},
        "limits": {
            "timeout_seconds": 900,
            "max_turns": 8,
            "max_output_bytes": 2000000,
        },
        "prompt": {
            "role_instruction": "Review the referenced sanitized material read-only.",
            "output_contract": "Report VERDICT: PASS or VERDICT: BLOCKERS with findings.",
        },
        "redaction": {
            "suppress_reads": True,
            "redact_prompt": True,
            "redact_stderr": True,
            "redact_metadata": True,
            "redact_env": True,
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(mapping.get(key), dict):
            mapping[key] = {**mapping[key], **value}
        else:
            mapping[key] = value
    return mapping


def _write_role(tmp_path: Path, mapping: dict[str, Any]) -> tuple[Path, str]:
    role_path = tmp_path / ROLE_FILE_REF
    role_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(mapping, indent=2, sort_keys=True).encode("utf-8")
    role_path.write_bytes(payload)
    return tmp_path, "sha256:" + hashlib.sha256(payload).hexdigest()


def _preflight_request(**overrides: Any) -> DurableStatePreflightRequest:
    base: dict[str, Any] = {
        "activity_id": "activity_preflight_for_exec_001",
        "transaction_ref": "claim_txn_exec_001",
        "operation_ref": "claim_op_exec_001",
        "idempotency_key": "idem_preflight_for_exec_001",
        "mode": "exec_dry_run",
        "role_key": "sachima.primary_reviewer",
        "approval_token": DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
        "enabled": True,
        "prompt_ref": "claim_prompt_exec_001",
        "context_refs": ("claim_context_exec_001",),
        "cwd_ref": "workspace_ref_sachima_release",
        "allowed_roots_ref": "allowed_roots_ref_sachima_release",
        "prior_dry_run_evidence_digest": _evidence_digest(),
        "lease_id": "lease_exec_001",
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


def _preflight_store_with_record() -> DurableStatePreflightStore:
    request = _preflight_request()
    store = DurableStatePreflightStore()
    store.grant_lease(
        activity_id=request.activity_id,
        lease_id=request.lease_id,
        lease_epoch=request.lease_epoch,
        lease_holder_ref=request.lease_holder_ref,
        state_version=0,
    )
    run_durable_state_preflight(request, store)
    return store


def _request(**overrides: Any) -> ControlledLocalExecRequest:
    base: dict[str, Any] = {
        "activity_id": "activity_controlled_exec_001",
        "transaction_ref": "claim_txn_exec_001",
        "operation_ref": "claim_op_exec_001",
        "idempotency_key": "idem_controlled_exec_001",
        "mode": CONTROLLED_EXEC_MODE,
        "role_key": "sachima.codex.primary_reviewer",
        "approval_token": CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN,
        "enabled": True,
        "prompt_ref": "claim_prompt_exec_001",
        "context_refs": ("claim_context_exec_001",),
        "cwd_ref": "workspace_ref_sachima_release",
        "allowed_roots_ref": "allowed_roots_ref_sachima_release",
        "role_file_digest": "sha256:" + "0" * 64,
        "prior_dry_run_evidence_digest": _evidence_digest(),
        "preflight_activity_id": "activity_preflight_for_exec_001",
        "lease_id": "lease_exec_001",
        "lease_epoch": 3,
        "lease_holder_ref": "controller_ref_sachima_flowweaver",
        "expected_state_version": 0,
        "operator_gate": True,
    }
    base.update(overrides)
    return ControlledLocalExecRequest(**base)


def _env(
    tmp_path: Path,
    *,
    role_mapping: dict[str, Any] | None = None,
    **request_overrides: Any,
) -> tuple[
    ControlledLocalExecRequest,
    ControlledLocalExecClaimStore,
    DurableStatePreflightStore,
    Path,
]:
    mapping = role_mapping if role_mapping is not None else _role_mapping()
    role_root, digest = _write_role(tmp_path, mapping)
    overrides: dict[str, Any] = {"role_file_digest": digest}
    overrides.update(request_overrides)
    request = _request(**overrides)
    return request, ControlledLocalExecClaimStore(), _preflight_store_with_record(), role_root


def _success_outcome(
    seam_request: LocalOfflineSupervisorRequest,
) -> LocalOfflineSupervisorOutcome:
    return LocalOfflineSupervisorOutcome(
        status="observed",
        mode=seam_request.mode,
        phase="exec",
        supervisor_status="completed",
        correlation_label=seam_request.correlation_label,
        error_code=None,
        business_verdict=None,
        caller_verdict=None,
        artifact_ref_count=1,
        evidence_ref="local_offline_supervisor_evidence_controlled_exec",
        evidence_digest="sha256:" + "a" * 64,
        evidence_path=None,
        view_model={"status": "observed"},
    )


def _counting_fake(
    counter: dict[str, Any],
    outcome_factory: Callable[[LocalOfflineSupervisorRequest], LocalOfflineSupervisorOutcome],
) -> Callable[[LocalOfflineSupervisorRequest], LocalOfflineSupervisorOutcome]:
    def _fake(seam_request: LocalOfflineSupervisorRequest) -> LocalOfflineSupervisorOutcome:
        counter["calls"] += 1
        counter["last_request"] = seam_request
        return outcome_factory(seam_request)

    return _fake


def _start(
    request: ControlledLocalExecRequest,
    store: ControlledLocalExecClaimStore,
    preflight_store: DurableStatePreflightStore,
    role_root: Path,
    fake: Callable[[LocalOfflineSupervisorRequest], LocalOfflineSupervisorOutcome],
):
    return start_controlled_local_exec(
        request,
        store=store,
        preflight_store=preflight_store,
        invoke_supervisor=fake,
        role_root=role_root,
    )


def _assert_fails_closed_before_launch(
    request: ControlledLocalExecRequest,
    store: ControlledLocalExecClaimStore,
    preflight_store: DurableStatePreflightStore,
    role_root: Path,
    error_code: str,
) -> None:
    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(ControlledLocalExecError) as exc:
        _start(request, store, preflight_store, role_root, _counting_fake(counter, _success_outcome))
    assert exc.value.error_code == error_code
    assert counter["calls"] == 0
    assert store.get_by_activity(request.activity_id) is None


def _assert_no_leaks(state: dict[str, Any]) -> None:
    rendered = repr(state).lower()
    for token in FORBIDDEN_RENDER_TOKENS:
        assert token not in rendered


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_happy_path_completed_claim_is_sanitized_and_seam_request_is_ref_only(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}

    result = _start(request, store, preflight_store, role_root, _counting_fake(counter, _success_outcome))
    state = result.to_durable_state()

    assert counter["calls"] == 1
    assert result.ok is True
    assert result.status == "completed"
    assert result.business_verdict is None
    assert set(state) == EXPECTED_CLAIM_STATE_KEYS
    assert state["type"] == "sachima.supervisor.controlled_local_exec_claim.v1"
    assert state["mode"] == "exec_controlled"
    assert state["phase"] == "controlled_exec"
    assert state["activity_id"] == "activity_controlled_exec_001"
    assert state["transaction_ref"] == "claim_txn_exec_001"
    assert state["operation_ref"] == "claim_op_exec_001"
    assert state["role_key"] == "sachima.codex.primary_reviewer"
    assert state["idempotency_key"] == "idem_controlled_exec_001"
    assert state["role_file_digest"] == request.role_file_digest
    assert state["prior_dry_run_evidence_digest"] == request.prior_dry_run_evidence_digest
    assert state["preflight_view_ref"].startswith("durable_state_preflight_view_")
    assert state["approval_ref"] == "controlled_local_exec_approval_v1"
    assert state["lease_id"] == "lease_exec_001"
    assert state["lease_epoch"] == 3
    assert state["lease_holder_ref"] == "controller_ref_sachima_flowweaver"
    assert state["state_version"] == 0
    assert state["attempt_index"] == 1
    assert state["attempt_count"] == 1
    assert state["supervisor_status"] == "completed"
    assert state["artifact_ref_count"] == 1
    assert state["evidence_ref"] == "local_offline_supervisor_evidence_controlled_exec"
    assert state["evidence_digest"] == "sha256:" + "a" * 64
    assert state["business_verdict"] is None
    assert state["caller_verdict"] is None
    assert state["error_code"] is None
    assert state["retryable"] is False
    assert state["view_model_ref"].startswith("controlled_local_exec_view_")
    _assert_no_leaks(state)

    seam_request = counter["last_request"]
    assert seam_request.mode == "exec"
    assert seam_request.enabled is True
    assert seam_request.approval_token == LOCAL_OFFLINE_APPROVAL_TOKEN
    assert seam_request.correlation_label == "activity_controlled_exec_001"
    assert seam_request.role is None
    assert seam_request.role_file == str(role_root / ROLE_FILE_REF)
    # Claim-check discipline: only refs travel; raw prompt/context never do.
    assert seam_request.prompt is None
    assert seam_request.context is None
    assert seam_request.claim_check_refs == (
        "claim_txn_exec_001",
        "claim_op_exec_001",
        "claim_prompt_exec_001",
        "claim_context_exec_001",
    )

    assert query_controlled_local_exec(
        store, activity_id="activity_controlled_exec_001"
    ).to_durable_state() == state
    assert tuple(signature(start_controlled_local_exec).parameters) == (
        "request",
        "store",
        "preflight_store",
        "invoke_supervisor",
        "role_root",
        "prompt_materializer",
    )


# --------------------------------------------------------------------------- #
# Default-off / approval / mode / role gates
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"enabled": False}, "activity_disabled"),
        ({"approval_token": "approve_wrong_scope"}, "activity_approval_mismatch"),
        (
            {"approval_token": DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN},
            "activity_approval_mismatch",
        ),
    ],
)
def test_default_off_and_approval_mismatch_fail_closed(
    tmp_path: Path, overrides: dict[str, Any], error_code: str
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path, **overrides)

    _assert_fails_closed_before_launch(request, store, preflight_store, role_root, error_code)


@pytest.mark.parametrize(
    "mode",
    [
        "exec_dry_run",
        "exec",
        "session_create",
        "session_send",
        "session_status",
        "session_close",
        "cancel",
        "rollback",
        "live",
        "deliver",
        "gateway_restart",
        "",
    ],
)
def test_mode_allowlist_rejects_dry_run_session_cancel_live_and_delivery_modes(
    tmp_path: Path, mode: str
) -> None:
    assert CONTROLLED_EXEC_MODES == frozenset({"exec_controlled"})
    request, store, preflight_store, role_root = _env(tmp_path, mode=mode)

    _assert_fails_closed_before_launch(
        request, store, preflight_store, role_root, "activity_unsupported_mode"
    )


@pytest.mark.parametrize(
    "role_key",
    [
        "sachima.claude.architect",
        "sachima.claude.main_programmer",
        "sachima.claude.docs_engineer",
        "sachima.codex.blocker_only_reviewer",
        "sachima.primary_reviewer",
        "sachima.docs_planner",
        "sachima.coding_worker",
        "sachima.session_worker",
        "../roles/codex_primary_reviewer_exec_controlled_v1.json",
        "sachima.unknown_role",
    ],
)
def test_first_slice_runs_only_read_only_codex_primary_reviewer_role(
    tmp_path: Path, role_key: str
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path, role_key=role_key)

    _assert_fails_closed_before_launch(
        request, store, preflight_store, role_root, "activity_unknown_role"
    )


def test_role_allowlist_is_exactly_codex_primary_reviewer_and_future_roles_are_disjoint() -> None:
    assert set(CONTROLLED_EXEC_ROLE_ALLOWLIST) == {"sachima.codex.primary_reviewer"}
    assert CONTROLLED_EXEC_FUTURE_ROLE_KEYS == frozenset(
        {
            "sachima.claude.architect",
            "sachima.claude.main_programmer",
            "sachima.claude.docs_engineer",
            "sachima.codex.blocker_only_reviewer",
        }
    )
    assert not (CONTROLLED_EXEC_FUTURE_ROLE_KEYS & set(CONTROLLED_EXEC_ROLE_ALLOWLIST))


# --------------------------------------------------------------------------- #
# Material / claim-check / operator-gate / prior-evidence gates
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("activity_id", "oc_" + "privatechat123456"),
        ("transaction_ref", "claim_txn_with_secret_token"),
        ("operation_ref", "claim_op_with_card_json"),
        ("idempotency_key", "idem_with_media_path"),
        ("prompt_ref", "raw prompt body must not travel"),
        ("context_refs", ("claim_context_safe", "card_json_payload_ref")),
        ("context_refs", ["claim_context_not_a_tuple"]),
        ("cwd_ref", "/tmp/raw-media-path.png"),
        ("allowed_roots_ref", "media_path_/tmp/raw-file.png"),
        ("preflight_activity_id", "ou_" + "privateuser123456"),
        ("lease_id", "secret_token_lease"),
        ("lease_holder_ref", "om_" + "privatemsg123456"),
    ],
)
def test_unsafe_refs_platform_private_card_media_or_secret_shaped_fail_closed(
    tmp_path: Path, field: str, value: Any
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path, **{field: value})

    _assert_fails_closed_before_launch(
        request, store, preflight_store, role_root, "activity_unsafe_material"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"prompt_ref": None},
        {"preflight_activity_id": None},
    ],
)
def test_required_claim_check_refs_missing_fail_closed(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path, **overrides)

    _assert_fails_closed_before_launch(
        request, store, preflight_store, role_root, "activity_precondition_unmet"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"operator_gate": False},
        {"operator_gate": "true"},
        {"operator_gate": 1},
    ],
)
def test_operator_gate_must_be_exact_true(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path, **overrides)

    _assert_fails_closed_before_launch(
        request, store, preflight_store, role_root, "activity_precondition_unmet"
    )


@pytest.mark.parametrize(
    "digest",
    [None, "", "not-a-digest", "sha256:nothex", "sha256:" + "b" * 64],
)
def test_prior_dry_run_evidence_digest_missing_malformed_or_wrong_fails_closed(
    tmp_path: Path, digest: str | None
) -> None:
    request, store, preflight_store, role_root = _env(
        tmp_path, prior_dry_run_evidence_digest=digest
    )

    _assert_fails_closed_before_launch(
        request, store, preflight_store, role_root, "activity_precondition_unmet"
    )


# --------------------------------------------------------------------------- #
# Durable preflight binding (record, lease, state version)
# --------------------------------------------------------------------------- #
def test_missing_preflight_record_fails_closed(tmp_path: Path) -> None:
    request, store, _unused, role_root = _env(tmp_path)

    _assert_fails_closed_before_launch(
        request, store, DurableStatePreflightStore(), role_root, "activity_precondition_unmet"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"preflight_activity_id": "activity_preflight_other"},
        {"transaction_ref": "claim_txn_exec_other"},
        {"operation_ref": "claim_op_exec_other"},
    ],
)
def test_preflight_record_binding_mismatch_fails_closed(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path, **overrides)

    _assert_fails_closed_before_launch(
        request, store, preflight_store, role_root, "activity_precondition_unmet"
    )


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"lease_id": "lease_exec_other"}, "activity_lease_lost"),
        ({"lease_holder_ref": "controller_ref_other"}, "activity_lease_lost"),
        ({"lease_id": None}, "activity_lease_lost"),
        ({"lease_holder_ref": None}, "activity_lease_lost"),
        ({"lease_epoch": 2}, "activity_stale_state"),
        ({"lease_epoch": 4}, "activity_lease_lost"),
        ({"lease_epoch": "3"}, "activity_lease_lost"),
        ({"expected_state_version": 1}, "activity_toctou_conflict"),
        ({"expected_state_version": "0"}, "activity_toctou_conflict"),
    ],
)
def test_lease_and_state_version_binding_fails_closed(
    tmp_path: Path, overrides: dict[str, Any], error_code: str
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path, **overrides)

    _assert_fails_closed_before_launch(
        request, store, preflight_store, role_root, error_code
    )


# --------------------------------------------------------------------------- #
# Pinned local acpx runner provenance
# --------------------------------------------------------------------------- #
def test_committed_role_config_is_null_binary_read_only_and_fails_closed_on_provenance() -> None:
    import sachima_supervisor.activity_controlled_exec as activity_controlled_exec

    committed = (
        Path(activity_controlled_exec.__file__).resolve().parent / ROLE_FILE_REF
    )
    payload = committed.read_bytes()
    mapping = json.loads(payload.decode("utf-8"))

    # The committed config is truthful: no local acpx binary exists on this
    # host yet, so the pinned binary stays null and the gate must fail closed.
    assert mapping["runner"]["acpx_binary"] is None
    assert mapping["runner"]["adapter_agent"] == "codex"
    assert mapping["runner"]["type"] == "acpx"
    assert mapping["runner"]["acpx_version"] == "0.10.0"
    assert mapping["session"] == {"strategy": "exec"}
    assert mapping["permissions"]["read"] is True
    assert mapping["permissions"]["search"] is True
    for kind in ("write", "execute", "terminal", "delete", "move", "fetch", "switch_mode", "other"):
        assert mapping["permissions"][kind] is False

    request = _request(
        role_file_digest="sha256:" + hashlib.sha256(payload).hexdigest()
    )
    counter: dict[str, Any] = {"calls": 0}
    with pytest.raises(ControlledLocalExecError) as exc:
        start_controlled_local_exec(
            request,
            store=ControlledLocalExecClaimStore(),
            preflight_store=_preflight_store_with_record(),
            invoke_supervisor=_counting_fake(counter, _success_outcome),
        )
    assert exc.value.error_code == "activity_runner_provenance_unverified"
    assert counter["calls"] == 0


@pytest.mark.parametrize(
    "runner_overrides",
    [
        {"acpx_binary": None},
        {"acpx_binary": ""},
        {"acpx_binary": 7},
        {"acpx_binary": "relative/path/acpx"},
        {"acpx_binary": "/opt/acpx with spaces/acpx -y"},
        {"acpx_binary": "/usr/local/bin/npx"},
        {"acpx_binary": "/usr/bin/node"},
        {"acpx_binary": "/usr/local/bin/npm"},
        {"acpx_binary": "/usr/local/bin/pnpm"},
        {"acpx_binary": "/usr/bin/yarn"},
        {"acpx_binary": "/usr/local/bin/bunx"},
        {"acpx_binary": "/bin/sh"},
        {"acpx_binary": "/bin/bash"},
        {"acpx_binary": "/usr/bin/env"},
        {"acpx_binary": "/usr/local/bin/NPM"},
        {"type": "shell"},
        {"acpx_version": "0.9.0"},
    ],
)
def test_unpinned_or_fetch_shaped_runner_provenance_fails_closed(
    tmp_path: Path, runner_overrides: dict[str, Any]
) -> None:
    request, store, preflight_store, role_root = _env(
        tmp_path, role_mapping=_role_mapping(runner=runner_overrides)
    )

    _assert_fails_closed_before_launch(
        request, store, preflight_store, role_root, "activity_runner_provenance_unverified"
    )


def test_missing_role_file_fails_closed(tmp_path: Path) -> None:
    request = _request()

    _assert_fails_closed_before_launch(
        request,
        ControlledLocalExecClaimStore(),
        _preflight_store_with_record(),
        tmp_path,
        "activity_runner_provenance_unverified",
    )


def test_unparseable_role_file_fails_closed(tmp_path: Path) -> None:
    role_path = tmp_path / ROLE_FILE_REF
    role_path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"{not json"
    role_path.write_bytes(payload)
    request = _request(role_file_digest="sha256:" + hashlib.sha256(payload).hexdigest())

    _assert_fails_closed_before_launch(
        request,
        ControlledLocalExecClaimStore(),
        _preflight_store_with_record(),
        tmp_path,
        "activity_runner_provenance_unverified",
    )


@pytest.mark.parametrize(
    "digest",
    [None, "", "not-a-digest", "sha256:" + "c" * 64],
)
def test_role_file_digest_missing_or_mismatched_fails_closed(
    tmp_path: Path, digest: str | None
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path, role_file_digest=digest)

    _assert_fails_closed_before_launch(
        request, store, preflight_store, role_root, "activity_runner_provenance_unverified"
    )


# --------------------------------------------------------------------------- #
# Read-only role capability gate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "role_overrides",
    [
        {"role_id": "sachima.codex.other_role"},
        {"schema_version": 2},
        {"runner": {"adapter_agent": "claude"}},
        {"runner": {"adapter_agent": "hermes --profile satine acp"}},
        {"permissions": {"write": True}},
        {"permissions": {"execute": True}},
        {"permissions": {"terminal": True}},
        {"permissions": {"delete": True}},
        {"permissions": {"move": True}},
        {"permissions": {"fetch": True}},
        {"permissions": {"switch_mode": True}},
        {"permissions": {"other": True}},
        {"permissions": {"read": False}},
        {"permissions": {"search": False}},
        {"session": {"strategy": "persistent"}},
    ],
)
def test_write_capable_non_codex_or_persistent_role_files_fail_closed(
    tmp_path: Path, role_overrides: dict[str, Any]
) -> None:
    request, store, preflight_store, role_root = _env(
        tmp_path, role_mapping=_role_mapping(**role_overrides)
    )

    _assert_fails_closed_before_launch(
        request, store, preflight_store, role_root, "activity_role_capability_rejected"
    )


# --------------------------------------------------------------------------- #
# Atomic pre-launch claim / CAS
# --------------------------------------------------------------------------- #
def test_claim_is_written_before_supervisor_invocation(tmp_path: Path) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    observed: dict[str, Any] = {}

    def _observing_fake(
        seam_request: LocalOfflineSupervisorRequest,
    ) -> LocalOfflineSupervisorOutcome:
        resident = store.get_by_activity(request.activity_id)
        observed["status_during_invocation"] = None if resident is None else resident["status"]
        return _success_outcome(seam_request)

    result = _start(request, store, preflight_store, role_root, _observing_fake)

    assert observed["status_during_invocation"] == "claimed_in_progress"
    assert result.status == "completed"


def test_identical_replay_of_completed_claim_returns_projection_without_relaunch(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}
    fake = _counting_fake(counter, _success_outcome)

    first = _start(request, store, preflight_store, role_root, fake)
    second = _start(request, store, preflight_store, role_root, fake)

    assert counter["calls"] == 1
    assert second.to_durable_state() == first.to_durable_state()


def test_identical_replay_of_in_progress_claim_returns_projection_without_relaunch(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}
    inner_states: list[dict[str, Any]] = []

    def _reentrant_fake(
        seam_request: LocalOfflineSupervisorRequest,
    ) -> LocalOfflineSupervisorOutcome:
        counter["calls"] += 1
        # An identical replay arriving while the claim is still in progress
        # (e.g. after a crash) must return the resident projection and must
        # not start a second run.
        inner = _start(
            request, store, preflight_store, role_root, _counting_fake(counter, _success_outcome)
        )
        inner_states.append(inner.to_durable_state())
        return _success_outcome(seam_request)

    result = _start(request, store, preflight_store, role_root, _reentrant_fake)

    assert counter["calls"] == 1
    assert len(inner_states) == 1
    assert inner_states[0]["status"] == "claimed_in_progress"
    assert inner_states[0]["ok"] is False
    assert inner_states[0]["error_code"] is None
    assert inner_states[0]["retryable"] is False
    assert result.status == "completed"
    _assert_no_leaks(inner_states[0])


def test_conflicting_replay_after_completion_fails_closed_before_launch(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}
    fake = _counting_fake(counter, _success_outcome)
    _start(request, store, preflight_store, role_root, fake)

    conflicting = _request(
        role_file_digest=request.role_file_digest,
        prompt_ref="claim_prompt_exec_conflicting",
    )
    with pytest.raises(ControlledLocalExecError) as exc:
        _start(conflicting, store, preflight_store, role_root, fake)

    assert exc.value.error_code == "activity_idempotency_conflict"
    assert counter["calls"] == 1


def test_conflicting_replay_against_in_progress_claim_fails_closed_before_launch(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}
    conflict_codes: list[str] = []

    def _conflicting_fake(
        seam_request: LocalOfflineSupervisorRequest,
    ) -> LocalOfflineSupervisorOutcome:
        counter["calls"] += 1
        conflicting = _request(
            role_file_digest=request.role_file_digest,
            prompt_ref="claim_prompt_exec_conflicting",
        )
        try:
            _start(
                conflicting,
                store,
                preflight_store,
                role_root,
                _counting_fake(counter, _success_outcome),
            )
        except ControlledLocalExecError as inner_exc:
            conflict_codes.append(inner_exc.error_code)
        return _success_outcome(seam_request)

    result = _start(request, store, preflight_store, role_root, _conflicting_fake)

    assert counter["calls"] == 1
    assert conflict_codes == ["activity_idempotency_conflict"]
    assert result.status == "completed"


def test_same_activity_under_different_idempotency_key_fails_closed_before_launch(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}
    fake = _counting_fake(counter, _success_outcome)
    _start(request, store, preflight_store, role_root, fake)

    duplicate = _request(
        role_file_digest=request.role_file_digest,
        idempotency_key="idem_controlled_exec_002",
    )
    with pytest.raises(ControlledLocalExecError) as exc:
        _start(duplicate, store, preflight_store, role_root, fake)

    assert exc.value.error_code == "activity_claim_conflict"
    assert counter["calls"] == 1


# --------------------------------------------------------------------------- #
# True concurrency: locked CAS under simultaneous starts
# --------------------------------------------------------------------------- #
_CONCURRENT_STARTS = 8
_CONCURRENT_WAIT_SECONDS = 10.0


def _run_concurrent_starts(
    requests: list[ControlledLocalExecRequest],
    store: ControlledLocalExecClaimStore,
    preflight_store: DurableStatePreflightStore,
    role_root: Path,
) -> tuple[int, list[dict[str, Any]], list[str]]:
    """Race ``len(requests)`` start calls against one shared claim store.

    The supervisor fake blocks the single winning launch until every other
    start has settled (replayed projection or fail-closed error), so the
    in-progress claim window deterministically overlaps all concurrent
    callers. Returns ``(supervisor_calls, result_states, error_codes)``.
    """

    total = len(requests)
    bookkeeping_lock = threading.Lock()
    supervisor_calls = 0
    release_winner = threading.Event()
    align_start = threading.Barrier(total)
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    def _blocking_fake(
        seam_request: LocalOfflineSupervisorRequest,
    ) -> LocalOfflineSupervisorOutcome:
        nonlocal supervisor_calls
        with bookkeeping_lock:
            supervisor_calls += 1
        release_winner.wait(timeout=_CONCURRENT_WAIT_SECONDS)
        return _success_outcome(seam_request)

    def _worker(request: ControlledLocalExecRequest) -> None:
        align_start.wait(timeout=_CONCURRENT_WAIT_SECONDS)
        try:
            result = _start(request, store, preflight_store, role_root, _blocking_fake)
        except ControlledLocalExecError as exc:
            with bookkeeping_lock:
                errors.append(exc.error_code)
        else:
            with bookkeeping_lock:
                results.append(result.to_durable_state())

    threads = [threading.Thread(target=_worker, args=(request,)) for request in requests]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + _CONCURRENT_WAIT_SECONDS
    while time.monotonic() < deadline:
        with bookkeeping_lock:
            if len(results) + len(errors) >= total - 1:
                break
        time.sleep(0.005)
    release_winner.set()
    for thread in threads:
        thread.join(timeout=_CONCURRENT_WAIT_SECONDS)
    assert all(not thread.is_alive() for thread in threads)
    return supervisor_calls, results, errors


def test_concurrent_identical_starts_invoke_supervisor_exactly_once(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    requests = [request] * _CONCURRENT_STARTS

    supervisor_calls, results, errors = _run_concurrent_starts(
        requests, store, preflight_store, role_root
    )

    assert supervisor_calls == 1
    assert errors == []
    assert len(results) == _CONCURRENT_STARTS
    # Exactly one caller launched and completed; every other caller received
    # the resident in-progress projection without a duplicate launch.
    statuses = sorted(state["status"] for state in results)
    assert statuses == ["claimed_in_progress"] * (_CONCURRENT_STARTS - 1) + ["completed"]
    for state in results:
        assert state["activity_id"] == request.activity_id
        assert state["idempotency_key"] == request.idempotency_key
        _assert_no_leaks(state)
    final = query_controlled_local_exec(
        store, activity_id=request.activity_id
    ).to_durable_state()
    assert final["status"] == "completed"


def test_concurrent_conflicting_idempotency_keys_fail_closed_with_single_launch(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    requests = [
        _request(
            role_file_digest=request.role_file_digest,
            idempotency_key=f"idem_controlled_exec_concurrent_{index:03d}",
        )
        for index in range(_CONCURRENT_STARTS)
    ]

    supervisor_calls, results, errors = _run_concurrent_starts(
        requests, store, preflight_store, role_root
    )

    assert supervisor_calls == 1
    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert errors == ["activity_claim_conflict"] * (_CONCURRENT_STARTS - 1)


def test_concurrent_same_idempotency_different_fingerprint_fails_closed_with_single_launch(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    requests = [
        _request(
            role_file_digest=request.role_file_digest,
            prompt_ref=f"claim_prompt_exec_variant_{index:03d}",
        )
        for index in range(_CONCURRENT_STARTS)
    ]

    supervisor_calls, results, errors = _run_concurrent_starts(
        requests, store, preflight_store, role_root
    )

    assert supervisor_calls == 1
    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert errors == ["activity_idempotency_conflict"] * (_CONCURRENT_STARTS - 1)


def test_claim_store_concurrent_identical_claims_acquire_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sachima_supervisor.activity_controlled_exec as activity_controlled_exec

    request, store, preflight_store, role_root = _env(tmp_path)
    captured: dict[str, Any] = {}

    def _capturing_fake(
        seam_request: LocalOfflineSupervisorRequest,
    ) -> LocalOfflineSupervisorOutcome:
        captured["in_progress"] = store.get_by_activity(request.activity_id)
        return _success_outcome(seam_request)

    _start(request, store, preflight_store, role_root, _capturing_fake)
    claimed_state = captured["in_progress"]
    assert claimed_state["status"] == "claimed_in_progress"

    # Widen the read/check/write window inside ``claim`` so an unlocked
    # check-and-set would let every racer pass the existence checks before
    # any write and acquire more than once.
    real_validate = activity_controlled_exec._validate_claim_state_projection

    def _slow_validate(state: dict[str, Any]) -> dict[str, Any]:
        time.sleep(0.01)
        return real_validate(state)

    monkeypatch.setattr(
        activity_controlled_exec, "_validate_claim_state_projection", _slow_validate
    )

    fresh = ControlledLocalExecClaimStore()
    total = 16
    align_start = threading.Barrier(total)
    dispositions: list[tuple[str, str]] = []
    dispositions_lock = threading.Lock()

    def _worker() -> None:
        align_start.wait(timeout=_CONCURRENT_WAIT_SECONDS)
        disposition, state = fresh.claim(
            activity_id=request.activity_id,
            idempotency_key=request.idempotency_key,
            fingerprint="a" * 64,
            state=claimed_state,
        )
        with dispositions_lock:
            dispositions.append((disposition, state["status"]))

    threads = [threading.Thread(target=_worker) for _ in range(total)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_CONCURRENT_WAIT_SECONDS)
    assert all(not thread.is_alive() for thread in threads)
    assert len(dispositions) == total
    assert all(status == "claimed_in_progress" for _, status in dispositions)
    acquired = [disposition for disposition, _ in dispositions if disposition == "acquired"]
    replayed = [disposition for disposition, _ in dispositions if disposition == "replayed"]
    assert len(acquired) == 1
    assert len(replayed) == total - 1


# --------------------------------------------------------------------------- #
# Supervisor failure / unsafe outcome collapse
# --------------------------------------------------------------------------- #
def test_supervisor_exception_collapses_to_stable_retryable_error_without_raw_leak(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)

    def _raising_fake(seam_request: LocalOfflineSupervisorRequest) -> LocalOfflineSupervisorOutcome:
        raise RuntimeError(
            "oc_privatechat123456 secret token at /tmp/leak.png with traceback detail"
        )

    result = _start(request, store, preflight_store, role_root, _raising_fake)
    state = result.to_durable_state()

    assert result.ok is False
    assert result.status == "failed_retryable"
    assert result.error_code == "activity_supervisor_failed"
    assert result.retryable is True
    assert state["supervisor_status"] is None
    assert state["artifact_ref_count"] == 0
    assert state["evidence_ref"] is None
    assert state["evidence_digest"] is None
    assert state["business_verdict"] is None
    _assert_no_leaks(state)
    assert query_controlled_local_exec(
        store, activity_id=request.activity_id
    ).to_durable_state() == state


def test_unsafe_supervisor_outcome_fields_collapse_to_failed_terminal_without_raw_leak(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)

    def _unsafe_outcome(
        seam_request: LocalOfflineSupervisorRequest,
    ) -> LocalOfflineSupervisorOutcome:
        return LocalOfflineSupervisorOutcome(
            status="unsafe outcome with secret token",
            mode=seam_request.mode,
            phase="exec",
            supervisor_status="completed",
            correlation_label=seam_request.correlation_label,
            error_code=None,
            business_verdict=None,
            caller_verdict="caller_ready",
            artifact_ref_count=-3,
            evidence_ref="local_offline_supervisor_evidence_unsafe",
            evidence_digest="not-a-valid-digest",
            evidence_path=None,
            view_model={"unsafe": "dropped"},
        )

    result = _start(request, store, preflight_store, role_root, _unsafe_outcome)
    state = result.to_durable_state()

    assert result.ok is False
    assert result.status == "failed_terminal"
    assert result.error_code == "activity_supervisor_failed"
    assert result.retryable is False
    assert state["supervisor_status"] is None
    assert state["artifact_ref_count"] == 0
    assert state["evidence_ref"] is None
    assert state["evidence_digest"] is None
    _assert_no_leaks(state)


def test_lower_business_verdict_is_never_accepted(tmp_path: Path) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)

    def _verdict_outcome(
        seam_request: LocalOfflineSupervisorRequest,
    ) -> LocalOfflineSupervisorOutcome:
        outcome = _success_outcome(seam_request)
        object.__setattr__(outcome, "business_verdict", "success")
        return outcome

    result = _start(request, store, preflight_store, role_root, _verdict_outcome)

    assert result.status == "failed_terminal"
    assert result.business_verdict is None
    assert result.to_durable_state()["business_verdict"] is None


def test_seam_error_outcome_collapses_to_failed_retryable(tmp_path: Path) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)

    def _error_outcome(
        seam_request: LocalOfflineSupervisorRequest,
    ) -> LocalOfflineSupervisorOutcome:
        return LocalOfflineSupervisorOutcome(
            status="error",
            mode=seam_request.mode,
            phase="exec",
            supervisor_status=None,
            correlation_label=seam_request.correlation_label,
            error_code="supervisor_invocation_failed",
            business_verdict=None,
            caller_verdict=None,
            artifact_ref_count=0,
            evidence_ref=None,
            evidence_digest=None,
            evidence_path=None,
            view_model={"status": "error"},
        )

    result = _start(request, store, preflight_store, role_root, _error_outcome)

    assert result.ok is False
    assert result.status == "failed_retryable"
    assert result.error_code == "activity_supervisor_failed"
    assert result.retryable is True


# --------------------------------------------------------------------------- #
# Query path
# --------------------------------------------------------------------------- #
def test_query_is_read_only_and_never_reinvokes_supervisor(tmp_path: Path) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}
    state = _start(
        request, store, preflight_store, role_root, _counting_fake(counter, _success_outcome)
    ).to_durable_state()

    first_query = query_controlled_local_exec(store, activity_id=request.activity_id)
    second_query = query_controlled_local_exec(store, activity_id=request.activity_id)

    assert counter["calls"] == 1
    assert first_query.to_durable_state() == state
    assert second_query.to_durable_state() == state
    assert tuple(signature(query_controlled_local_exec).parameters) == (
        "store",
        "activity_id",
    )
    _assert_no_leaks(first_query.to_durable_state())


def test_query_missing_activity_fails_closed() -> None:
    with pytest.raises(ControlledLocalExecError) as exc:
        query_controlled_local_exec(
            ControlledLocalExecClaimStore(), activity_id="activity_missing"
        )

    assert exc.value.error_code == "activity_not_found"


# --------------------------------------------------------------------------- #
# Claim store hardening
# --------------------------------------------------------------------------- #
def test_claim_store_rejects_malicious_state_on_claim(tmp_path: Path) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    state = _start(
        request, store, preflight_store, role_root, _counting_fake({"calls": 0}, _success_outcome)
    ).to_durable_state()
    state["raw_prompt"] = "raw prompt with secret token at /tmp/private/path"

    with pytest.raises(ControlledLocalExecError) as exc:
        ControlledLocalExecClaimStore().claim(
            activity_id=request.activity_id,
            idempotency_key=request.idempotency_key,
            fingerprint="a" * 64,
            state=state,
        )

    assert exc.value.error_code == "activity_unsafe_material"


def test_query_rejects_malicious_resident_state(tmp_path: Path) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    state = _start(
        request, store, preflight_store, role_root, _counting_fake({"calls": 0}, _success_outcome)
    ).to_durable_state()
    state["raw_prompt"] = "raw prompt with secret token at /tmp/private/path"
    poisoned = ControlledLocalExecClaimStore()
    poisoned._by_activity[request.activity_id] = state

    with pytest.raises(ControlledLocalExecError) as exc:
        query_controlled_local_exec(poisoned, activity_id=request.activity_id)

    assert exc.value.error_code == "activity_unsafe_material"


def test_get_idempotent_rejects_malicious_resident_fingerprint(tmp_path: Path) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    state = _start(
        request, store, preflight_store, role_root, _counting_fake({"calls": 0}, _success_outcome)
    ).to_durable_state()
    poisoned = ControlledLocalExecClaimStore()
    poisoned._by_idempotency[request.idempotency_key] = (
        "raw prompt secret token /tmp/private/path",
        state,
    )

    with pytest.raises(ControlledLocalExecError) as exc:
        poisoned.get_idempotent(request.idempotency_key)

    assert exc.value.error_code == "activity_unsafe_material"


# --------------------------------------------------------------------------- #
# Pinned local acpx binary provenance helper (Phase D smoke prerequisite)
# --------------------------------------------------------------------------- #
def _fake_pinned_binary(
    tmp_path: Path, *, name: str = "acpx", executable: bool = True
) -> Path:
    binary = tmp_path / "runners" / name
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"#!/bin/false\nfake pinned local acpx placeholder bytes\n")
    binary.chmod(0o755 if executable else 0o644)
    return binary


def _counting_probe(
    calls: list[str], text: Any = "acpx 0.10.0 (pinned local build)"
) -> Callable[[str], Any]:
    def _probe(binary_path: str) -> Any:
        calls.append(binary_path)
        if isinstance(text, Exception):
            raise text
        return text

    return _probe


def test_verify_pinned_local_acpx_binary_happy_path_with_injected_probe(
    tmp_path: Path,
) -> None:
    binary = _fake_pinned_binary(tmp_path)
    calls: list[str] = []

    provenance = verify_pinned_local_acpx_binary(
        str(binary), version_probe=_counting_probe(calls)
    )

    assert isinstance(provenance, PinnedLocalAcpxProvenance)
    assert provenance.binary_path == str(binary)
    assert provenance.binary_sha256 == (
        "sha256:" + hashlib.sha256(binary.read_bytes()).hexdigest()
    )
    assert provenance.acpx_version == "0.10.0"
    assert provenance.probe_text == "acpx 0.10.0 (pinned local build)"
    assert calls == [str(binary)]


@pytest.mark.parametrize(
    "binary_path",
    [None, 7, "", "relative/path/acpx", "./acpx", "/opt/acpx dir/acpx", "/opt/\tacpx"],
)
def test_acpx_provenance_invalid_path_shape_fails_closed_before_probe(
    binary_path: Any,
) -> None:
    calls: list[str] = []

    with pytest.raises(ControlledLocalExecError) as exc:
        verify_pinned_local_acpx_binary(binary_path, version_probe=_counting_probe(calls))

    assert exc.value.error_code == "activity_runner_provenance_unverified"
    assert calls == []


@pytest.mark.parametrize(
    "name",
    ["npx", "npx-wrapper", "npm", "pnpm", "yarn", "bunx", "bun", "corepack",
     "sh", "bash", "zsh", "dash", "fish", "env", "node"],
)
def test_acpx_provenance_fetch_or_shell_runner_basenames_fail_closed(
    tmp_path: Path, name: str
) -> None:
    binary = _fake_pinned_binary(tmp_path, name=name)
    calls: list[str] = []

    with pytest.raises(ControlledLocalExecError) as exc:
        verify_pinned_local_acpx_binary(
            str(binary), version_probe=_counting_probe(calls)
        )

    assert exc.value.error_code == "activity_runner_provenance_unverified"
    assert calls == []


def test_acpx_provenance_forbidden_basename_set_is_explicit() -> None:
    assert {
        "npx", "npm", "pnpm", "yarn", "bunx", "bun", "corepack",
        "sh", "bash", "zsh", "dash", "ksh", "fish", "env", "node",
    } <= set(FORBIDDEN_RUNNER_BASENAMES)


def test_acpx_provenance_missing_or_non_executable_file_fails_closed(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    with pytest.raises(ControlledLocalExecError) as exc:
        verify_pinned_local_acpx_binary(
            str(tmp_path / "runners" / "acpx"), version_probe=_counting_probe(calls)
        )
    assert exc.value.error_code == "activity_runner_provenance_unverified"

    non_executable = _fake_pinned_binary(tmp_path, executable=False)
    with pytest.raises(ControlledLocalExecError) as exc:
        verify_pinned_local_acpx_binary(
            str(non_executable), version_probe=_counting_probe(calls)
        )
    assert exc.value.error_code == "activity_runner_provenance_unverified"
    assert calls == []


def test_acpx_provenance_directory_path_fails_closed(tmp_path: Path) -> None:
    directory = tmp_path / "runners" / "acpx"
    directory.mkdir(parents=True)
    calls: list[str] = []

    with pytest.raises(ControlledLocalExecError) as exc:
        verify_pinned_local_acpx_binary(
            str(directory), version_probe=_counting_probe(calls)
        )

    assert exc.value.error_code == "activity_runner_provenance_unverified"
    assert calls == []


def test_acpx_provenance_probe_exception_is_collapsed_without_raw_leak(
    tmp_path: Path,
) -> None:
    binary = _fake_pinned_binary(tmp_path)
    boom = RuntimeError("se" + "cret to" + "ken at /private/leak with traceback detail")

    with pytest.raises(ControlledLocalExecError) as exc:
        verify_pinned_local_acpx_binary(
            str(binary), version_probe=_counting_probe([], boom)
        )

    assert exc.value.error_code == "activity_runner_provenance_unverified"
    rendered = str(exc.value).lower()
    assert "se" + "cret" not in rendered
    assert "/private/leak" not in rendered
    assert "traceback" not in rendered


@pytest.mark.parametrize(
    "probe_text",
    [
        None,
        7,
        "",
        "acpx 0.9.9",
        "acpx 0.10.0\nsecond line",
        "acpx 0.10.0 unsafe to" + "ken text",
        "acpx 0.10.0 " + "x" * 300,
    ],
)
def test_acpx_provenance_unsafe_or_mismatched_probe_text_fails_closed(
    tmp_path: Path, probe_text: Any
) -> None:
    binary = _fake_pinned_binary(tmp_path)

    with pytest.raises(ControlledLocalExecError) as exc:
        verify_pinned_local_acpx_binary(
            str(binary), version_probe=_counting_probe([], probe_text)
        )

    assert exc.value.error_code == "activity_runner_provenance_unverified"


@pytest.mark.parametrize(
    "probe_text",
    [
        "acpx 10.10.0",
        "acpx 00.10.0",
        "acpx 0.10.01",
        "acpx 0.10.0.1",
        "acpx 0.10.0-dev",
        "acpx 0.10.0-rc.1",
        "acpx 0.10.0rc1",
        "acpx 0.10.0+build.5",
    ],
)
def test_acpx_provenance_version_substring_or_prerelease_lookalikes_fail_closed(
    tmp_path: Path, probe_text: str
) -> None:
    """The pinned version must match as an exact token, never as a substring.

    ``0.10.0`` is a substring of ``10.10.0`` and a prefix of pre-release /
    build-metadata variants like ``0.10.0-dev``; none of these are the pinned
    release and all must fail closed.
    """

    binary = _fake_pinned_binary(tmp_path)

    with pytest.raises(ControlledLocalExecError) as exc:
        verify_pinned_local_acpx_binary(
            str(binary), version_probe=_counting_probe([], probe_text)
        )

    assert exc.value.error_code == "activity_runner_provenance_unverified"


@pytest.mark.parametrize(
    "probe_text",
    [
        "acpx 0.10.0",
        "acpx 0.10.0 (pinned local build)",
        "acpx/0.10.0",
        "0.10.0",
    ],
)
def test_acpx_provenance_exact_version_token_probe_text_is_accepted(
    tmp_path: Path, probe_text: str
) -> None:
    binary = _fake_pinned_binary(tmp_path)

    provenance = verify_pinned_local_acpx_binary(
        str(binary), version_probe=_counting_probe([], probe_text)
    )

    assert provenance.probe_text == probe_text
    assert provenance.acpx_version == "0.10.0"


@pytest.mark.parametrize("expected_version", ["0.9.0", "", None, "0.10.1"])
def test_acpx_provenance_expected_version_must_match_required_pin(
    tmp_path: Path, expected_version: Any
) -> None:
    binary = _fake_pinned_binary(tmp_path)
    calls: list[str] = []

    with pytest.raises(ControlledLocalExecError) as exc:
        verify_pinned_local_acpx_binary(
            str(binary),
            version_probe=_counting_probe(calls),
            expected_version=expected_version,
        )

    assert exc.value.error_code == "activity_runner_provenance_unverified"
    assert calls == []


def test_acpx_provenance_explicit_required_version_is_accepted(tmp_path: Path) -> None:
    binary = _fake_pinned_binary(tmp_path)

    provenance = verify_pinned_local_acpx_binary(
        str(binary),
        version_probe=_counting_probe([]),
        expected_version="0.10.0",
    )

    assert provenance.acpx_version == "0.10.0"


# --------------------------------------------------------------------------- #
# Prompt materializer seam (Phase D smoke prerequisite)
# --------------------------------------------------------------------------- #
_SAFE_MATERIALIZED_PROMPT = (
    "Phase D deterministic read-only check material v1. Reply with plain "
    "text starting with VERDICT: PASS or VERDICT: BLOCKERS."
)


def test_default_path_without_materializer_keeps_seam_prompt_none(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}

    result = _start(
        request, store, preflight_store, role_root, _counting_fake(counter, _success_outcome)
    )

    assert result.status == "completed"
    assert counter["last_request"].prompt is None
    assert counter["last_request"].context is None


def test_materializer_runs_after_acquired_claim_and_injects_seam_prompt(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}
    materializer_calls: dict[str, Any] = {"count": 0, "status_during": "missing"}

    def _materializer(seen_request: ControlledLocalExecRequest) -> str:
        materializer_calls["count"] += 1
        resident = store.get_by_activity(request.activity_id)
        materializer_calls["status_during"] = (
            None if resident is None else resident["status"]
        )
        assert seen_request is request
        return _SAFE_MATERIALIZED_PROMPT

    result = start_controlled_local_exec(
        request,
        store=store,
        preflight_store=preflight_store,
        invoke_supervisor=_counting_fake(counter, _success_outcome),
        role_root=role_root,
        prompt_materializer=_materializer,
    )
    state = result.to_durable_state()

    assert result.status == "completed"
    assert counter["calls"] == 1
    assert materializer_calls["count"] == 1
    # The raw prompt is materialized only after the atomic pre-launch claim
    # is already resident, and only into the seam request.
    assert materializer_calls["status_during"] == "claimed_in_progress"
    assert counter["last_request"].prompt == _SAFE_MATERIALIZED_PROMPT
    assert counter["last_request"].context is None
    # Durable claim state stays sanitized: same key set, no prompt text.
    assert set(state) == EXPECTED_CLAIM_STATE_KEYS
    assert "deterministic read-only check material" not in repr(state).lower()
    _assert_no_leaks(state)


def test_phase_d_smoke_prompt_builder_is_accepted_by_the_materializer_seam(
    tmp_path: Path,
) -> None:
    from sachima_supervisor.smoke_prompt import (
        build_phase_d_smoke_prompt,
        materialize_phase_d_smoke_prompt,
    )

    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}

    result = start_controlled_local_exec(
        request,
        store=store,
        preflight_store=preflight_store,
        invoke_supervisor=_counting_fake(counter, _success_outcome),
        role_root=role_root,
        prompt_materializer=materialize_phase_d_smoke_prompt,
    )

    assert result.status == "completed"
    assert counter["calls"] == 1
    assert counter["last_request"].prompt == build_phase_d_smoke_prompt()["prompt"]
    _assert_no_leaks(result.to_durable_state())


def test_materializer_exception_fails_closed_terminal_without_supervisor_call(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}

    def _raising_materializer(_request: ControlledLocalExecRequest) -> str:
        raise RuntimeError(
            "se" + "cret to" + "ken at /private/prompt-leak with traceback detail"
        )

    result = start_controlled_local_exec(
        request,
        store=store,
        preflight_store=preflight_store,
        invoke_supervisor=_counting_fake(counter, _success_outcome),
        role_root=role_root,
        prompt_materializer=_raising_materializer,
    )
    state = result.to_durable_state()

    assert counter["calls"] == 0
    assert result.ok is False
    assert result.status == "failed_terminal"
    assert result.error_code == "activity_prompt_materialization_failed"
    assert result.retryable is False
    assert state["supervisor_status"] is None
    assert state["artifact_ref_count"] == 0
    assert state["evidence_ref"] is None
    assert state["evidence_digest"] is None
    assert state["business_verdict"] is None
    assert "se" + "cret" not in repr(state).lower()
    assert "/private/prompt-leak" not in repr(state)
    _assert_no_leaks(state)
    assert query_controlled_local_exec(
        store, activity_id=request.activity_id
    ).to_durable_state() == state


@pytest.mark.parametrize(
    "materialized",
    [
        None,
        7,
        b"bytes-not-str",
        "",
        "prompt with se" + "cret to" + "ken material",
        "prompt with raw_" + "prompt marker",
        "p" * 5000,
    ],
)
def test_materializer_unsafe_output_fails_closed_terminal_without_supervisor_call(
    tmp_path: Path, materialized: Any
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}

    result = start_controlled_local_exec(
        request,
        store=store,
        preflight_store=preflight_store,
        invoke_supervisor=_counting_fake(counter, _success_outcome),
        role_root=role_root,
        prompt_materializer=lambda _request: materialized,
    )

    assert counter["calls"] == 0
    assert result.status == "failed_terminal"
    assert result.error_code == "activity_prompt_materialization_failed"
    _assert_no_leaks(result.to_durable_state())


def test_replay_of_completed_claim_never_rematerializes_or_relaunches(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}
    materializer_calls = {"count": 0}

    def _materializer(_request: ControlledLocalExecRequest) -> str:
        materializer_calls["count"] += 1
        return _SAFE_MATERIALIZED_PROMPT

    def _start_with_materializer():
        return start_controlled_local_exec(
            request,
            store=store,
            preflight_store=preflight_store,
            invoke_supervisor=_counting_fake(counter, _success_outcome),
            role_root=role_root,
            prompt_materializer=_materializer,
        )

    first = _start_with_materializer()
    second = _start_with_materializer()

    assert first.status == "completed"
    assert counter["calls"] == 1
    assert materializer_calls["count"] == 1
    assert second.to_durable_state() == first.to_durable_state()


def test_replay_after_materialization_failure_returns_resident_terminal_state(
    tmp_path: Path,
) -> None:
    request, store, preflight_store, role_root = _env(tmp_path)
    counter: dict[str, Any] = {"calls": 0}
    materializer_calls = {"count": 0}

    def _failing_materializer(_request: ControlledLocalExecRequest) -> str:
        materializer_calls["count"] += 1
        raise RuntimeError("materialization failure")

    def _start_with_materializer():
        return start_controlled_local_exec(
            request,
            store=store,
            preflight_store=preflight_store,
            invoke_supervisor=_counting_fake(counter, _success_outcome),
            role_root=role_root,
            prompt_materializer=_failing_materializer,
        )

    first = _start_with_materializer()
    second = _start_with_materializer()

    assert first.status == "failed_terminal"
    assert first.error_code == "activity_prompt_materialization_failed"
    assert materializer_calls["count"] == 1
    assert counter["calls"] == 0
    assert second.to_durable_state() == first.to_durable_state()


# --------------------------------------------------------------------------- #
# Forbidden source surface
# --------------------------------------------------------------------------- #
def test_controlled_exec_source_has_no_forbidden_execution_or_delivery_surface() -> None:
    import sachima_supervisor.activity_controlled_exec as activity_controlled_exec

    source = Path(activity_controlled_exec.__file__).read_text(encoding="utf-8").lower()

    for token in (
        "aiohttp",
        "httpx",
        "lark_oapi",
        "feishu",
        "webhook",
        "temporalio",
        "subprocess",
        "docker",
        "systemctl",
        "os.system",
        "popen",
        "pexpect",
        "npx -y",
        "shell=true",
        "codex exec",
        "claude exec",
    ):
        assert token not in source, f"forbidden live/runtime token: {token}"
    for statement in (
        "import gateway",
        "from gateway",
        "import requests",
        "from requests",
        "import socket",
        "from socket",
    ):
        assert statement not in source, f"forbidden import/call surface: {statement}"
