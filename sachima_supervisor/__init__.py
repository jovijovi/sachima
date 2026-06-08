"""Sachima x agent-run-supervisor local/offline integration seam (default-off).

Caller-owned, local/offline only. No live behavior, no Gateway involvement, no
real delivery. See ``sachima_supervisor.local_offline`` for the public API and
``docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md``
for the design boundaries.
"""

from __future__ import annotations

from sachima_supervisor.activity import (
    ACTIVITY_IMPLEMENTATION_APPROVAL_TOKEN,
    FIRST_SLICE_MODES,
    ROLE_KEY_ALLOWLIST,
    ActivityStateStore,
    SupervisedLocalActivityError,
    SupervisedLocalActivityRequest,
    SupervisedLocalActivityResult,
    query_supervised_local_activity,
    start_supervised_local_activity,
)
from sachima_supervisor.activity_evidence import (
    CONTROLLED_DRY_RUN_EVIDENCE_APPROVAL_MARKER,
    build_controlled_local_dry_run_evidence,
    write_controlled_local_dry_run_evidence,
)
from sachima_supervisor.activity_preflight import (
    DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN,
    DurableStatePreflightError,
    DurableStatePreflightRequest,
    DurableStatePreflightResult,
    DurableStatePreflightStore,
    query_durable_state_preflight,
    run_durable_state_preflight,
)
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
    # local/offline seam (PR #97)
    "FORBIDDEN_METADATA_KEYS",
    "IMPLEMENTATION_APPROVAL_TOKEN",
    "SUPPORTED_MODES",
    "LocalOfflineSupervisorError",
    "LocalOfflineSupervisorOutcome",
    "LocalOfflineSupervisorRequest",
    "build_caller_invocation_spec",
    "build_offline_view_model",
    "invoke_local_offline_supervisor",
    # supervised local Activity wrapper (first slice)
    "ACTIVITY_IMPLEMENTATION_APPROVAL_TOKEN",
    "FIRST_SLICE_MODES",
    "ROLE_KEY_ALLOWLIST",
    "ActivityStateStore",
    "SupervisedLocalActivityError",
    "SupervisedLocalActivityRequest",
    "SupervisedLocalActivityResult",
    "query_supervised_local_activity",
    "start_supervised_local_activity",
    # controlled local Activity dry-run evidence (PR #100)
    "CONTROLLED_DRY_RUN_EVIDENCE_APPROVAL_MARKER",
    "build_controlled_local_dry_run_evidence",
    "write_controlled_local_dry_run_evidence",
    # durable-state preflight (local/offline)
    "DURABLE_STATE_PREFLIGHT_APPROVAL_TOKEN",
    "DurableStatePreflightError",
    "DurableStatePreflightRequest",
    "DurableStatePreflightResult",
    "DurableStatePreflightStore",
    "query_durable_state_preflight",
    "run_durable_state_preflight",
]
