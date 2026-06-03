"""Sachima x agent-run-supervisor local/offline integration seam (default-off).

Caller-owned, local/offline only. No live behavior, no Gateway involvement, no
real delivery. See ``sachima_supervisor.local_offline`` for the public API and
``docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md``
for the design boundaries.
"""

from __future__ import annotations

from sachima_supervisor.local_offline import (
    FORBIDDEN_METADATA_KEYS,
    IMPLEMENTATION_APPROVAL_TOKEN,
    SUPPORTED_MODES,
    LocalOfflineSupervisorError,
    LocalOfflineSupervisorOutcome,
    LocalOfflineSupervisorRequest,
    build_caller_invocation_spec,
    build_offline_view_model,
    invoke_local_offline_supervisor,
)

__all__ = [
    "FORBIDDEN_METADATA_KEYS",
    "IMPLEMENTATION_APPROVAL_TOKEN",
    "SUPPORTED_MODES",
    "LocalOfflineSupervisorError",
    "LocalOfflineSupervisorOutcome",
    "LocalOfflineSupervisorRequest",
    "build_caller_invocation_spec",
    "build_offline_view_model",
    "invoke_local_offline_supervisor",
]
