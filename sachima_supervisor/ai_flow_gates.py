"""Controlled AI FLOW operator gates (WP4 slice 1, FR2/FR6).

Local/offline only. Four fail-closed gate types (admission, pre_step, post_step,
terminal). A gate is granted only when the operator boolean is exactly ``True``
and the gate ref is present, safe, and (when an expected ref is supplied) an
exact match. Missing, malformed/ambiguous, or mismatched material never
auto-grants — the workflow halts. Each decision is persisted as a sanitized
``GateDecision`` record; an unsafe ref is never retained.

Per the WP4 convention this module owns its own sanitization primitives.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_GATE_RECORD_TYPE = "sachima.supervisor.ai_flow_gate_record.v1"

GATE_TYPES: tuple[str, ...] = ("admission", "pre_step", "post_step", "terminal")
GATE_STATUSES: tuple[str, ...] = ("granted", "missing", "mismatch", "ambiguous")

_REF_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_UNSAFE_MARKERS: tuple[str, ...] = (
    "media_path",
    "raw_prompt",
    "prompt_body",
    "card_json",
    "signed_url",
    "tool_output",
)


class AiFlowGateError(Exception):
    """Fail-closed gate error carrying a stable code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


@dataclass(frozen=True)
class GateDecision:
    gate_type: str
    gate_ref: str | None
    status: str
    step_id: str | None

    @property
    def granted(self) -> bool:
        return self.status == "granted"


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


def _is_safe_ref(value: Any) -> bool:
    if type(value) is not str or _REF_RE.fullmatch(value) is None:
        return False
    lowered = value.lower()
    return not any(marker in lowered for marker in _UNSAFE_MARKERS)


def check_gate(
    gate_type: str,
    *,
    operator_gate: Any,
    gate_ref: Any,
    expected_ref: str | None = None,
    step_id: str | None = None,
) -> GateDecision:
    """Return a fail-closed gate decision; never auto-grants.

    ``operator_gate`` must be exactly ``True``. ``gate_ref`` must be present and
    safe (and equal ``expected_ref`` when supplied) for a ``granted`` decision;
    otherwise the status is ``missing`` / ``ambiguous`` / ``mismatch`` and the
    unsafe ref is dropped from the record.
    """

    if gate_type not in GATE_TYPES:
        raise AiFlowGateError("activity_unknown_gate", "unknown operator gate type")
    if step_id is not None and not _is_safe_ref(step_id):
        raise AiFlowGateError("activity_unsafe_material", "unsafe gate step id")

    safe_ref = gate_ref if _is_safe_ref(gate_ref) else None
    if operator_gate is not True:
        status = "missing"
    elif gate_ref is None:
        status = "missing"
    elif safe_ref is None:
        status = "ambiguous"
    elif expected_ref is not None and gate_ref != expected_ref:
        status = "mismatch"
    else:
        status = "granted"

    return GateDecision(
        gate_type=gate_type,
        gate_ref=safe_ref if status in ("granted", "mismatch") else None,
        status=status,
        step_id=step_id,
    )


def gate_decision_projection(decision: GateDecision) -> dict[str, Any]:
    """Return the sanitized durable projection of a gate decision."""

    projection = {
        "type": _GATE_RECORD_TYPE,
        "gate_type": decision.gate_type,
        "gate_ref": decision.gate_ref,
        "status": decision.status,
        "step_id": decision.step_id,
    }
    rendered = "\n".join(_walk_strings(projection)).lower()
    if any(marker in rendered for marker in _UNSAFE_MARKERS):
        raise AiFlowGateError("activity_unsafe_material", "gate projection carries raw material")
    return projection
