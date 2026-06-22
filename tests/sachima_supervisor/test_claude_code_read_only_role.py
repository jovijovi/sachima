"""WP1a: committed read-only Claude Code reviewer role + capability-gate tests.

These tests cover the Sachima-side, injected-fakes-only WP1a slice:

  * the committed ``claude_code_read_only_reviewer_v1.json`` is null-binary
    (non-runnable by construction), declares ``adapter_agent=claude``, is
    read/search-only, uses ``session.strategy=exec``, and fails closed on
    runner provenance *before* any supervisor call;
  * the per-role adapter-agent map admits ``claude`` only for the new Claude
    role while Codex still requires ``codex``;
  * no raw prompt/output/tool output/exception/platform-private id leaks into
    durable claim state;
  * the committed role JSON and the self-test smoke script carry no
    Gateway/Feishu/webhook/npx/subprocess/socket/service-restart surface;
  * the self-test smoke wiring is deterministic (injected fakes only) and the
    real Claude smoke (WP1b) is refused here.

No real acpx/Claude execution happens anywhere in this module.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import pytest

import sachima_supervisor.activity_controlled_exec as activity_controlled_exec
from sachima_supervisor.activity_controlled_exec import (
    CONTROLLED_EXEC_FUTURE_ROLE_KEYS,
    CONTROLLED_EXEC_MODE,
    CONTROLLED_EXEC_ROLE_ADAPTER_AGENT,
    CONTROLLED_EXEC_ROLE_ALLOWLIST,
    CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN,
    ControlledLocalExecClaimStore,
    ControlledLocalExecError,
    ControlledLocalExecRequest,
    query_controlled_local_exec,
    start_controlled_local_exec,
)
from sachima_supervisor.activity_evidence import build_controlled_local_dry_run_evidence
from sachima_supervisor.activity_preflight import (
    DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
    DurableStatePreflightRequest,
    DurableStatePreflightStore,
    run_durable_state_preflight,
)
from sachima_supervisor.local_offline import (
    LocalOfflineSupervisorOutcome,
    LocalOfflineSupervisorRequest,
)

CLAUDE_ROLE_KEY = "sachima.claude.read_only_reviewer"
CLAUDE_ROLE_FILE_REF = "roles/claude_code_read_only_reviewer_v1.json"
PINNED_PLACEHOLDER_BINARY = "/opt/sachima/runners/acpx-0.10.0/acpx"

REPO_ROOT = Path(activity_controlled_exec.__file__).resolve().parent
COMMITTED_CLAUDE_ROLE = REPO_ROOT / CLAUDE_ROLE_FILE_REF
SMOKE_SCRIPT = REPO_ROOT.parent / "scripts" / "sachima_claude_code_read_only_smoke.py"

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


def _evidence_digest() -> str:
    digest = build_controlled_local_dry_run_evidence()["fixture_digest"]
    assert isinstance(digest, str)
    return digest


def _claude_role_mapping(**overrides: Any) -> dict[str, Any]:
    mapping: dict[str, Any] = {
        "schema_version": 1,
        "role_id": CLAUDE_ROLE_KEY,
        "display_name": "Sachima Claude Code read-only reviewer (read-only one-shot exec)",
        "description": "Read-only Claude Code reviewer for controlled local one-shot exec.",
        "runner": {
            "type": "acpx",
            "acpx_version": "0.10.0",
            "acpx_binary": PINNED_PLACEHOLDER_BINARY,
            "adapter_agent": "claude",
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
        "limits": {"timeout_seconds": 900, "max_turns": 8, "max_output_bytes": 2000000},
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
    role_path = tmp_path / CLAUDE_ROLE_FILE_REF
    role_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(mapping, indent=2, sort_keys=True).encode("utf-8")
    role_path.write_bytes(payload)
    return tmp_path, "sha256:" + hashlib.sha256(payload).hexdigest()


def _preflight_store_with_record() -> DurableStatePreflightStore:
    request = DurableStatePreflightRequest(
        activity_id="activity_preflight_for_claude_001",
        transaction_ref="claim_txn_claude_001",
        operation_ref="claim_op_claude_001",
        idempotency_key="idem_preflight_for_claude_001",
        mode="exec_dry_run",
        role_key="sachima.primary_reviewer",
        approval_token=DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
        enabled=True,
        prompt_ref="claim_prompt_claude_001",
        context_refs=("claim_context_claude_001",),
        cwd_ref="workspace_ref_sachima_release",
        allowed_roots_ref="allowed_roots_ref_sachima_release",
        prior_dry_run_evidence_digest=_evidence_digest(),
        lease_id="lease_claude_001",
        lease_epoch=3,
        lease_holder_ref="controller_ref_sachima_flowweaver",
        expected_state_version=0,
        operator_gate=True,
        max_attempts=1,
        max_artifact_refs=0,
        max_evidence_bytes=0,
    )
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
        "activity_id": "activity_controlled_claude_001",
        "transaction_ref": "claim_txn_claude_001",
        "operation_ref": "claim_op_claude_001",
        "idempotency_key": "idem_controlled_claude_001",
        "mode": CONTROLLED_EXEC_MODE,
        "role_key": CLAUDE_ROLE_KEY,
        "approval_token": CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN,
        "enabled": True,
        "prompt_ref": "claim_prompt_claude_001",
        "context_refs": ("claim_context_claude_001",),
        "cwd_ref": "workspace_ref_sachima_release",
        "allowed_roots_ref": "allowed_roots_ref_sachima_release",
        "role_file_digest": "sha256:" + "0" * 64,
        "prior_dry_run_evidence_digest": _evidence_digest(),
        "preflight_activity_id": "activity_preflight_for_claude_001",
        "lease_id": "lease_claude_001",
        "lease_epoch": 3,
        "lease_holder_ref": "controller_ref_sachima_flowweaver",
        "expected_state_version": 0,
        "operator_gate": True,
    }
    base.update(overrides)
    return ControlledLocalExecRequest(**base)


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
        evidence_ref="local_offline_supervisor_evidence_claude_exec",
        evidence_digest="sha256:" + "a" * 64,
        evidence_path=None,
        view_model={"status": "observed"},
    )


def _counting_fake(
    counter: dict[str, Any],
) -> Callable[[LocalOfflineSupervisorRequest], LocalOfflineSupervisorOutcome]:
    def _fake(seam_request: LocalOfflineSupervisorRequest) -> LocalOfflineSupervisorOutcome:
        counter["calls"] += 1
        counter["last_request"] = seam_request
        return _success_outcome(seam_request)

    return _fake


def _assert_no_leaks(state: dict[str, Any]) -> None:
    rendered = repr(state).lower()
    for token in FORBIDDEN_RENDER_TOKENS:
        assert token not in rendered


# --------------------------------------------------------------------------- #
# Committed role config
# --------------------------------------------------------------------------- #
def test_committed_claude_role_is_null_binary_claude_read_only_exec() -> None:
    payload = COMMITTED_CLAUDE_ROLE.read_bytes()
    mapping = json.loads(payload.decode("utf-8"))

    assert mapping["schema_version"] == 1
    assert mapping["role_id"] == CLAUDE_ROLE_KEY
    assert mapping["runner"]["type"] == "acpx"
    assert mapping["runner"]["acpx_version"] == "0.10.0"
    # Non-runnable by construction: no operator has pinned a local acpx here.
    assert mapping["runner"]["acpx_binary"] is None
    assert mapping["runner"]["adapter_agent"] == "claude"
    assert mapping["session"] == {"strategy": "exec"}
    assert mapping["permissions"]["read"] is True
    assert mapping["permissions"]["search"] is True
    for kind in ("write", "execute", "terminal", "delete", "move", "fetch", "switch_mode", "other"):
        assert mapping["permissions"][kind] is False


def test_committed_claude_role_fails_closed_on_provenance_before_supervisor_call() -> None:
    payload = COMMITTED_CLAUDE_ROLE.read_bytes()
    request = _request(role_file_digest="sha256:" + hashlib.sha256(payload).hexdigest())
    counter: dict[str, Any] = {"calls": 0}

    with pytest.raises(ControlledLocalExecError) as exc:
        start_controlled_local_exec(
            request,
            store=ControlledLocalExecClaimStore(),
            preflight_store=_preflight_store_with_record(),
            invoke_supervisor=_counting_fake(counter),
        )

    assert exc.value.error_code == "activity_runner_provenance_unverified"
    assert counter["calls"] == 0


def test_committed_claude_role_has_no_forbidden_delivery_surface() -> None:
    text = COMMITTED_CLAUDE_ROLE.read_text(encoding="utf-8").lower()
    for token in ("gateway", "feishu", "webhook", "npx", "public ingress", "production config", "real delivery"):
        assert token not in text, f"forbidden role wording: {token}"


# --------------------------------------------------------------------------- #
# Per-role adapter map (minimal admit-one-adapter delta)
# --------------------------------------------------------------------------- #
def test_role_adapter_agent_map_admits_claude_only_for_claude_role() -> None:
    assert CONTROLLED_EXEC_ROLE_ADAPTER_AGENT == {
        "sachima.codex.primary_reviewer": "codex",
        "sachima.claude.read_only_reviewer": "claude",
    }
    # The adapter map is in lockstep with the runnable allowlist: every runnable
    # role has exactly one required adapter, and no future role sneaks in.
    assert set(CONTROLLED_EXEC_ROLE_ADAPTER_AGENT) == set(CONTROLLED_EXEC_ROLE_ALLOWLIST)
    assert not (set(CONTROLLED_EXEC_ROLE_ADAPTER_AGENT) & CONTROLLED_EXEC_FUTURE_ROLE_KEYS)


def test_pinned_claude_overlay_admits_and_keeps_state_sanitized(tmp_path: Path) -> None:
    role_root, digest = _write_role(tmp_path, _claude_role_mapping())
    request = _request(role_file_digest=digest)
    store = ControlledLocalExecClaimStore()
    counter: dict[str, Any] = {"calls": 0}

    result = start_controlled_local_exec(
        request,
        store=store,
        preflight_store=_preflight_store_with_record(),
        invoke_supervisor=_counting_fake(counter),
        role_root=role_root,
    )
    state = result.to_durable_state()

    assert counter["calls"] == 1
    assert result.ok is True
    assert result.status == "completed"
    assert state["role_key"] == CLAUDE_ROLE_KEY
    assert state["business_verdict"] is None
    # Raw prompt/output/tool output never reach durable state.
    assert "prompt" not in {k.lower() for k in state} or "prompt_ref" not in state
    _assert_no_leaks(state)
    assert query_controlled_local_exec(
        store, activity_id=request.activity_id
    ).to_durable_state() == state


def test_supervisor_exception_on_claude_role_collapses_without_raw_leak(
    tmp_path: Path,
) -> None:
    role_root, digest = _write_role(tmp_path, _claude_role_mapping())
    request = _request(role_file_digest=digest)

    def _raising_fake(
        seam_request: LocalOfflineSupervisorRequest,
    ) -> LocalOfflineSupervisorOutcome:
        raise RuntimeError(
            "oc_privatechat123456 secret token at /tmp/leak.png with traceback detail"
        )

    result = start_controlled_local_exec(
        request,
        store=ControlledLocalExecClaimStore(),
        preflight_store=_preflight_store_with_record(),
        invoke_supervisor=_raising_fake,
        role_root=role_root,
    )
    state = result.to_durable_state()

    assert result.ok is False
    assert result.status == "failed_retryable"
    assert result.error_code == "activity_supervisor_failed"
    assert state["supervisor_status"] is None
    assert state["business_verdict"] is None
    _assert_no_leaks(state)


# --------------------------------------------------------------------------- #
# Self-test smoke wiring (injected fakes only; WP1b real smoke refused)
# --------------------------------------------------------------------------- #
def _import_smoke():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sachima_claude_code_read_only_smoke", SMOKE_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_self_test_reports_ok_single_supervisor_call_and_claude_adapter() -> None:
    smoke = _import_smoke()
    summary = smoke.run_self_test()

    assert summary["ok"] is True
    assert summary["mode"] == "self_test"
    assert summary["role_key"] == CLAUDE_ROLE_KEY
    assert summary["adapter_agent"] == "claude"
    assert summary["supervisor_calls"] == 1
    assert summary["status"] == "completed"
    assert summary["non_approvals_held"]["real_claude_smoke_wp1b"] is False
    _assert_no_leaks(summary)


def test_smoke_main_self_test_exits_zero_and_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    smoke = _import_smoke()

    exit_code = smoke.main(["--self-test"])

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True
    assert printed["mode"] == "self_test"
    assert printed["adapter_agent"] == "claude"
    assert printed["supervisor_calls"] == 1


def test_smoke_main_without_self_test_fails_closed_exit_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    smoke = _import_smoke()

    exit_code = smoke.main([])

    assert exit_code == 2
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is False
    rendered = json.dumps(printed).lower()
    assert "wp1b" in rendered
    assert "not approved" in rendered


def test_smoke_script_has_no_forbidden_execution_or_delivery_surface() -> None:
    source = SMOKE_SCRIPT.read_text(encoding="utf-8").lower()
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
