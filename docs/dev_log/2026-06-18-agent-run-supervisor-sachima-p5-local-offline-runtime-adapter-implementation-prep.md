# P5 local/offline runtime adapter implementation-prep dev log

**Date:** 2026-06-18
**Branch:** `docs/p5-runtime-adapter-implementation-prep`
**Base:** `release/sachima` at `6c11a40d4de3e66981c3ff27905c1785b1709e0a` (PR #147 merge commit; latest non-status-sync base)
**Status:** Docs-only implementation-prep / scope charter — not source implementation. Pre-PR Codex blocker-only review PASS / BLOCKERS None on the local diff; rerun on the final pushed head if the branch changes before approval.

Short dev log; the charter (`docs/plans/2026-06-18-agent-run-supervisor-sachima-p5-local-offline-runtime-adapter-implementation-prep.md`) holds the detail and is not duplicated here.

## What this packet is

A narrow scope charter that fixes the shape, boundaries, preserved safety constraints, allowed code shape, and required tests of the **next** P5 implementation slice, plus a folded stale-status fix for PR #147. It adds no adapter code and starts no runtime.

The authoritative P5 contract is the **merged** PR #147 design/readiness packet (merge commit `6c11a40d4de3e66981c3ff27905c1785b1709e0a`, mergedAt 2026-06-18T03:36:51Z); this charter references it rather than repeating it.

## Approval boundary

User approved the exact prep-scope token (docs only; charter only; no implementation; no runtime/Worker start; no controlled AI FLOW execution; no live/Gateway/Feishu/production config/real delivery):

```text
approve_agent_run_supervisor_sachima_p5_local_offline_runtime_adapter_implementation_prep_docs_only_no_implementation_no_runtime_start_no_worker_start_no_controlled_ai_flow_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Quoted in the charter but **not granted** here: the next implementation token (local/offline, caller-owned, **fake/injected** runtime only, behind the WP4 executor Protocol seam, default-off, no real runtime/Worker start) and the separate external Temporal/Worker lifecycle token.

## Strongest allowed next PR

A local/offline, caller-owned runtime adapter behind the existing WP4 executor Protocol seam (`StepExecutor` in `sachima_supervisor/ai_flow_executor.py`), default-off / injected, binding a deterministic fake/injected runtime for tests only — no real external runtime/Worker/service/socket/subprocess start, no new approval surface beyond the implementation token. One small adapter slice, not the durable backend, not a real runtime, not P6.

## Preserved PR #147 safety constraints (not weakened)

Caller-owned control surface (Gateway never owns/auto-starts a runtime); cross-process transactional claim store required for durable claims (in-process CAS insufficient, kill-criterion K2); no-throw stable result/error taxonomy; runtime-history no-leak with SCAN 1 (JSON projection) **and** SCAN 2 (serialized event/history bytes); the seven probes; and the WP3b active-run cancellation **WATCH** held `cancel_ambiguous`, never overclaimed.

## Governance posture (reduction rule)

Safety governance stays strong (the next PR carries its own manifest, guard tests, both no-leak scans, forbidden-surface scan, and an independent blocker review). Status governance stays light: no standalone PR is opened just to record merge status; full non-approval paragraphs are not duplicated; the stale PR #147 "pre-merge" wording is folded into this same-scope PR.

## PR #147 stale-status fold (same PR, no standalone status PR)

Converted the PR #147 design/readiness plan doc, manifest, and dev log from candidate/pre-merge to merged truth, and updated the human-authored `docs/roadmap/current-status.md` P5 entries (legacy status keys, phase-map row, bridge-PR table, open-tails row, `current_position` prose) to record PR #147 merged and this branch as the next P5 runtime-adapter implementation-prep candidate. The machine-owned `sachima-status-sync` block already reflects PR #147 merged and was not edited.

## Files changed

```text
docs/plans/2026-06-18-agent-run-supervisor-sachima-p5-local-offline-runtime-adapter-implementation-prep.md            (new charter)
docs/plans/2026-06-18-agent-run-supervisor-sachima-p5-local-offline-runtime-adapter-implementation-prep-manifest.yaml (new manifest)
docs/dev_log/2026-06-18-agent-run-supervisor-sachima-p5-local-offline-runtime-adapter-implementation-prep.md          (this dev log)
docs/roadmap/current-status.md                                                                                       (P5 status -> merged + next prep candidate)
docs/plans/2026-06-18-agent-run-supervisor-sachima-p5-production-durable-runtime-integration-design-readiness.md      (PR #147 status -> merged)
docs/plans/2026-06-18-agent-run-supervisor-sachima-p5-production-durable-runtime-integration-design-readiness-manifest.yaml (PR #147 status -> merged)
docs/dev_log/2026-06-18-agent-run-supervisor-sachima-p5-production-durable-runtime-integration-design-readiness.md    (PR #147 status -> merged)
```

No source, test, script, role, config, Gateway, Feishu, platform, runtime, or production config files change.

## Verification (docs-only gate; Hermes-run)

Planned / run before commit/PR: YAML parse of the new manifest; `git diff --check`; `tools/sync_roadmap_status.py --check` (machine block already current, not edited); changed-file allowlist (docs/status only); stale PR #147 status scan; forbidden live/Gateway/Worker/Feishu/runtime-start surface scan on changed files (non-approval prose allowed); secret-shaped / no-leak scan; pre-PR Codex blocker-only review on the local diff returned PASS / BLOCKERS None. No runtime tests run; this PR approves no implementation/runtime start.

## Next gate after this PR

If merged, this charter makes the P5 **local/offline, caller-owned, fake-runtime adapter implementation** eligible to request with its own exact token (above). External Temporal/Worker lifecycle remains separately unapproved; controlled AI FLOW execution (P6) stays blocked until the P5 durable-runtime probe evidence passes.
