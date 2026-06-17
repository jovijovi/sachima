"""Controlled AI FLOW step-executor seam (WP4 slice 1, FR5).

Local/offline only. Slice 1 ships **only** the ``StepExecutor`` Protocol and the
``StepExecutionOutcome`` dataclass — never a real runner, subprocess, socket,
acpx, or npx invocation. The orchestrator drives this seam with injected fakes
in tests; a real ``StepExecutor`` binding ``start_controlled_local_exec`` is a
separately approved later gate. The cancellation channel
(``interrupted`` / ``cleanup_verified`` / ``ambiguous``) mirrors
``SessionInterruptOutcome`` so the WP3b active-run WATCH posture is reusable
without inventing new semantics.

This module intentionally imports nothing beyond ``dataclasses`` / ``typing`` so
a clean import can never transitively load a forbidden surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class StepExecutionOutcome:
    """Sanitized outcome of one injected/real step execution.

    ``artifact_refs`` are sanitized ``ArtifactRef`` projections (mappings), never
    raw bodies. ``business_verdict`` is intentionally absent — WP4 never infers
    business success from an executor.
    """

    ok: bool
    step_status: str | None
    artifact_refs: tuple[Mapping[str, Any], ...] = ()
    evidence_ref: str | None = None
    evidence_digest: str | None = None
    error_code: str | None = None
    retryable: bool = False
    # Cancellation / interrupt channel (WP3b WATCH-aligned).
    interrupted: bool = False
    cleanup_verified: bool = False
    ambiguous: bool = False


class StepExecutor(Protocol):
    """Injected execution seam. Slice 1 has only test-side fakes."""

    def execute(
        self,
        request: Any,
        *,
        role_binding: Any,
        resolved_inputs: tuple[Mapping[str, Any], ...],
    ) -> StepExecutionOutcome: ...
