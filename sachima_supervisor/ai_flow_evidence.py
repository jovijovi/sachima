"""Controlled AI FLOW sanitized evidence projection (WP4 slice 1, FR7).

Local/offline only. ``build_workflow_evidence`` assembles a deterministic,
sanitized terminal evidence packet that proves the flow with refs/digests/codes
only — never raw prompts, model/tool output, exception strings, process/platform
ids, card JSON, message ids, credentials, webhook material, signed URLs, or raw
artifact bodies. It surfaces explicit non-approval flags and the WP3b active-run
cancellation WATCH marker when applicable, and a ``final_verdict`` in the allowed
set. The builder fails closed if any assembled string carries raw material.

Per the WP4 convention this module owns its own sanitization primitives.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

_EVIDENCE_TYPE = "sachima.supervisor.ai_flow_evidence.v1"
SCHEMA_VERSION = "sachima.ai_flow.local.v1"

FINAL_VERDICTS: tuple[str, ...] = (
    "succeeded",
    "failed",
    "cancelled",
    "parked",
    "ambiguous_fail_closed",
)

_UNSAFE_MARKERS: tuple[str, ...] = (
    "media_path",
    "raw_prompt",
    "prompt_body",
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


class AiFlowEvidenceError(Exception):
    """Fail-closed evidence-projection error carrying a stable code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
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


def _assert_no_leak(payload: Any) -> None:
    rendered = "\n".join(_walk_strings(payload)).lower()
    for marker in _UNSAFE_MARKERS:
        if marker in rendered:
            raise AiFlowEvidenceError(
                "activity_evidence_unsafe", "evidence projection carries raw material"
            )


def _digest_hex(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_non_approval_flags() -> dict[str, bool]:
    """Return the explicit WP4 non-approval flags (all ``False``)."""

    return {
        "real_workflow_execution": False,
        "additional_acpx_invocation": False,
        "additional_real_agent_execution": False,
        "write_capable_roles": False,
        "agent_to_agent_auto_routing": False,
        "worker_auto_routing": False,
        "gateway_involvement_or_mutation": False,
        "feishu_or_im_delivery": False,
        "live_or_default_on_behavior": False,
        "public_ingress": False,
        "production_config_write": False,
        "real_delivery": False,
    }


class WorkflowEvidence:
    """Sanitized, read-only view over a deterministic evidence projection."""

    def __init__(self, state: Mapping[str, Any]) -> None:
        self._state: dict[str, Any] = dict(state)

    @property
    def final_verdict(self) -> str:
        return self._state["final_verdict"]

    @property
    def workflow_spec_digest(self) -> str:
        return self._state["workflow_spec_digest"]

    @property
    def active_run_cancellation_watch(self) -> bool:
        return self._state["active_run_cancellation_watch"]

    @property
    def evidence_digest(self) -> str:
        return self._state["evidence_digest"]

    def to_durable_state(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._state))


def build_workflow_evidence(
    *,
    workflow_id: str,
    workflow_spec_digest: str,
    role_binding_digest: str,
    state_transitions: list[dict[str, Any]],
    step_fingerprints: dict[str, str],
    role_binding_refs: list[dict[str, Any]],
    gate_decisions: list[dict[str, Any]],
    artifact_refs: list[dict[str, Any]],
    error_codes: list[str],
    active_run_cancellation_watch: bool,
    final_verdict: str,
    retry_summary: dict[str, Any] | None = None,
    compensation_summary: dict[str, Any] | None = None,
    cancellation_summary: dict[str, Any] | None = None,
    non_approval_flags: dict[str, bool] | None = None,
) -> WorkflowEvidence:
    """Assemble a deterministic, sanitized terminal evidence packet."""

    if final_verdict not in FINAL_VERDICTS:
        raise AiFlowEvidenceError(
            "activity_evidence_invalid", "final_verdict is not in the allowed set"
        )

    derived_retry = retry_summary or {
        "max_attempt_index": max((t.get("attempt_index", 1) for t in state_transitions), default=0),
        "retried_steps": [t["step_id"] for t in state_transitions if t.get("attempt_index", 1) > 1],
    }
    derived_compensation = compensation_summary or {"orphaned_artifacts": [], "released_claims": []}
    derived_cancellation = dict(cancellation_summary or {"cancellations": []})
    derived_cancellation["active_run_cancellation_watch"] = bool(active_run_cancellation_watch)

    payload: dict[str, Any] = {
        "type": _EVIDENCE_TYPE,
        "schema_version": SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "workflow_spec_digest": workflow_spec_digest,
        "role_binding_digest": role_binding_digest,
        "state_transitions": list(state_transitions),
        "step_fingerprints": dict(sorted(step_fingerprints.items())),
        "role_binding_refs": list(role_binding_refs),
        "gate_decisions": list(gate_decisions),
        "artifact_refs": list(artifact_refs),
        "retry_summary": derived_retry,
        "compensation_summary": derived_compensation,
        "cancellation_summary": derived_cancellation,
        "error_codes": list(error_codes),
        "non_approval_flags": non_approval_flags or default_non_approval_flags(),
        "active_run_cancellation_watch": bool(active_run_cancellation_watch),
        "final_verdict": final_verdict,
    }
    _assert_no_leak(payload)
    payload["evidence_digest"] = _digest_hex(payload)
    return WorkflowEvidence(payload)
