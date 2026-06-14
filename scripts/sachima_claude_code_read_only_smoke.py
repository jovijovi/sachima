#!/usr/bin/env python3
"""WP1a deterministic self-test for the Claude Code read-only reviewer slice.

This script proves, with **injected fakes only**, that the controlled local
one-shot ``exec`` wrapper admits a pinned read-only Claude Code reviewer overlay
(``adapter_agent=claude``) through the same fail-closed gates as the Codex
reviewer, invokes the supervisor boundary exactly once, and keeps durable claim
state sanitized.

It is intentionally hermetic:

  * The only ``--self-test`` path runs entirely in-process. It writes a pinned
    Claude read-only role overlay (with a placeholder local ``acpx`` path so the
    no-fetch provenance gate is satisfied by *shape*, never by launching
    anything) into a temporary role root, builds a durable-state preflight
    record, and drives ``start_controlled_local_exec`` with a counting fake
    supervisor. No real ``acpx`` / agent CLI / shell / child process / network /
    delivery surface is ever touched.
  * Without ``--self-test`` it fails closed: the real Claude Code read-only
    smoke is WP1b and is not approved here, so it prints ``ok=false`` and exits
    ``2``.

Running a real Claude Code smoke (WP1b) remains a later, separately approved
phase.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sachima_supervisor.activity_controlled_exec import (  # noqa: E402
    CONTROLLED_EXEC_MODE,
    CONTROLLED_EXEC_ROLE_ADAPTER_AGENT,
    CONTROLLED_EXEC_ROLE_ALLOWLIST,
    CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN,
    ControlledLocalExecClaimStore,
    ControlledLocalExecRequest,
    start_controlled_local_exec,
)
from sachima_supervisor.activity_evidence import (  # noqa: E402
    build_controlled_local_dry_run_evidence,
)
from sachima_supervisor.activity_preflight import (  # noqa: E402
    DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
    DurableStatePreflightRequest,
    DurableStatePreflightStore,
    run_durable_state_preflight,
)
from sachima_supervisor.local_offline import (  # noqa: E402
    LocalOfflineSupervisorOutcome,
    LocalOfflineSupervisorRequest,
)

CLAUDE_ROLE_KEY = "sachima.claude.read_only_reviewer"
CLAUDE_ROLE_FILE_REF = CONTROLLED_EXEC_ROLE_ALLOWLIST[CLAUDE_ROLE_KEY]
#: Placeholder absolute local path only. The provenance gate validates the
#: *shape* of the pinned binary path; this script never executes it.
PINNED_PLACEHOLDER_BINARY = "/opt/sachima/runners/acpx-0.10.0/acpx"

_PREFLIGHT_ACTIVITY_ID = "activity_preflight_for_claude_self_test"
_TRANSACTION_REF = "claim_txn_claude_self_test"
_OPERATION_REF = "claim_op_claude_self_test"
_LEASE_ID = "lease_claude_self_test"
_LEASE_HOLDER_REF = "controller_ref_sachima_flowweaver"
_LEASE_EPOCH = 3


def _evidence_digest() -> str:
    return build_controlled_local_dry_run_evidence()["fixture_digest"]


def _claude_role_mapping() -> dict[str, Any]:
    """A pinned read-only Claude Code reviewer overlay (adapter_agent=claude)."""

    return {
        "schema_version": 1,
        "role_id": CLAUDE_ROLE_KEY,
        "display_name": "Sachima Claude Code read-only reviewer (read-only one-shot exec)",
        "description": "Read-only Claude Code reviewer for controlled local one-shot exec self-test.",
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


def _write_role(role_root: Path, mapping: dict[str, Any]) -> str:
    role_path = role_root / CLAUDE_ROLE_FILE_REF
    role_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(mapping, indent=2, sort_keys=True).encode("utf-8")
    role_path.write_bytes(payload)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _preflight_store(evidence_digest: str) -> DurableStatePreflightStore:
    request = DurableStatePreflightRequest(
        activity_id=_PREFLIGHT_ACTIVITY_ID,
        transaction_ref=_TRANSACTION_REF,
        operation_ref=_OPERATION_REF,
        idempotency_key="idem_preflight_for_claude_self_test",
        mode="exec_dry_run",
        role_key="sachima.primary_reviewer",
        approval_token=DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
        enabled=True,
        prompt_ref="claim_prompt_claude_self_test",
        context_refs=("claim_context_claude_self_test",),
        cwd_ref="workspace_ref_sachima_release",
        allowed_roots_ref="allowed_roots_ref_sachima_release",
        prior_dry_run_evidence_digest=evidence_digest,
        lease_id=_LEASE_ID,
        lease_epoch=_LEASE_EPOCH,
        lease_holder_ref=_LEASE_HOLDER_REF,
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


def _request(role_file_digest: str, evidence_digest: str) -> ControlledLocalExecRequest:
    return ControlledLocalExecRequest(
        activity_id="activity_controlled_claude_self_test",
        transaction_ref=_TRANSACTION_REF,
        operation_ref=_OPERATION_REF,
        idempotency_key="idem_controlled_claude_self_test",
        mode=CONTROLLED_EXEC_MODE,
        role_key=CLAUDE_ROLE_KEY,
        approval_token=CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN,
        enabled=True,
        prompt_ref="claim_prompt_claude_self_test",
        context_refs=("claim_context_claude_self_test",),
        cwd_ref="workspace_ref_sachima_release",
        allowed_roots_ref="allowed_roots_ref_sachima_release",
        role_file_digest=role_file_digest,
        prior_dry_run_evidence_digest=evidence_digest,
        preflight_activity_id=_PREFLIGHT_ACTIVITY_ID,
        lease_id=_LEASE_ID,
        lease_epoch=_LEASE_EPOCH,
        lease_holder_ref=_LEASE_HOLDER_REF,
        expected_state_version=0,
        operator_gate=True,
    )


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
        evidence_ref="local_offline_supervisor_evidence_claude_self_test",
        evidence_digest="sha256:" + "a" * 64,
        evidence_path=None,
        view_model={"status": "observed"},
    )


def run_self_test() -> dict[str, Any]:
    """Drive one injected-fakes Claude read-only controlled exec and summarize.

    Returns a sanitized summary carrying only stable codes, counts, and the
    held non-approvals. No raw prompt/output, platform-private id, path, or
    exception text ever enters this dict.
    """

    evidence_digest = _evidence_digest()
    counter: dict[str, Any] = {"calls": 0}

    def _fake_supervisor(
        seam_request: LocalOfflineSupervisorRequest,
    ) -> LocalOfflineSupervisorOutcome:
        counter["calls"] += 1
        return _success_outcome(seam_request)

    with tempfile.TemporaryDirectory() as tmp:
        role_root = Path(tmp)
        role_file_digest = _write_role(role_root, _claude_role_mapping())
        result = start_controlled_local_exec(
            _request(role_file_digest, evidence_digest),
            store=ControlledLocalExecClaimStore(),
            preflight_store=_preflight_store(evidence_digest),
            invoke_supervisor=_fake_supervisor,
            role_root=role_root,
        )

    state = result.to_durable_state()
    role_key = state["role_key"]
    return {
        "ok": (
            result.ok
            and result.status == "completed"
            and counter["calls"] == 1
            and role_key == CLAUDE_ROLE_KEY
        ),
        "mode": "self_test",
        "role_key": role_key,
        "adapter_agent": CONTROLLED_EXEC_ROLE_ADAPTER_AGENT[role_key],
        "supervisor_calls": counter["calls"],
        "status": result.status,
        "business_verdict": state["business_verdict"],
        "non_approvals_held": {
            "real_claude_smoke_wp1b": False,
        },
    }


def _refusal_summary() -> dict[str, Any]:
    return {
        "ok": False,
        "mode": "refused",
        "reason": (
            "real Claude Code read-only smoke (WP1b) is not approved here; "
            "rerun with --self-test for the deterministic injected-fakes self-test"
        ),
        "non_approvals_held": {
            "real_claude_smoke_wp1b": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in args:
        summary = run_self_test()
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0 if summary["ok"] else 1
    summary = _refusal_summary()
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
