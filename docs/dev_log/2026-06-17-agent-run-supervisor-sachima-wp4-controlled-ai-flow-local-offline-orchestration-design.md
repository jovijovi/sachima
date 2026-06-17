# WP4 — Controlled AI FLOW local/offline orchestration design dev log

**Date:** 2026-06-17
**Branch:** `docs/ars-wp4-controlled-ai-flow-design`
**Base:** `release/sachima` at `6261303970e5bde05e0c5ed8db50c994c63f36af`
**Status:** Candidate docs-only design gate; PR pending.

## Approval boundary

User approved the exact design-only token:

```text
approve_agent_run_supervisor_sachima_controlled_ai_flow_local_offline_orchestration_design_docs_only_no_implementation_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Interpretation used by Hermes:

- WP4 design only.
- No implementation/source/test/script behavior changes.
- No real workflow execution, no `acpx` invocation, no new real AGENT run.
- No write roles, no auto-routing, no `@all`, no automatic replies, no worker auto-routing.
- No Gateway/Feishu/live/public ingress/production config/real delivery.

## Role split

- **Hermes:** PM/controller/verifier/repo operator; created the worktree, verified live GitHub/repo state, constrained the approval boundary, landed the design docs, ran local verification and review loops; commit/push/PR are repo transport steps outside the WP4 design content.
- **Claude Code:** architect + documentation engineer. Intended model path `claude-opus-4-8[1m]` / effort max. Exact-model smoke passed. A tool-enabled file-edit attempt produced no artifact after turn/timeout limits, so Hermes used a tools-disabled Claude architect consultation packet and independently landed the files.
- **Codex CLI:** primary blocker reviewer for the final docs-only diff. Initial review returned `VERDICT: BLOCKED` on two roadmap-status freshness issues (`last_updated` stale and PR #140 missing from the latest phase / bridge PR table). Hermes fixed both, then Codex blocker-only re-review returned `VERDICT: PASS` / `BLOCKERS: None`.

## Fresh state used

Preflight evidence before authoring:

```text
repo: jovijovi/sachima
base branch: release/sachima
canonical checkout: clean and tracking sachima/release/sachima
open PR count: 0
worktree branch: docs/ars-wp4-controlled-ai-flow-design
worktree base: 6261303970e5bde05e0c5ed8db50c994c63f36af
PR #140: MERGED, title "feat: add bounded real cancellation execution", merge commit 3fe18ab9451d290a70036697da118351d604be27, CI success
```

CodeGraph initialization in the new worktree was attempted but blocked by the
terminal safety-confirmation path and therefore was not retried. This is a docs-only
design gate; no CodeGraph evidence is claimed for this PR.

## Design decisions

1. WP4 starts with a schema-versioned, caller-owned static workflow graph.
2. The first future implementation slice should be a bounded read-only linear flow
   such as `architect -> programmer_candidate(read-only) -> reviewer`.
3. Role output cannot choose the successor step; there is no auto-routing.
4. Operator gates are required for workflow admission, pre-step, post-step, and terminal acceptance.
5. Durable state stores claim-check refs/digests/codes/counts only; raw artifacts stay out of durable state and operator projections.
6. Per-step idempotency binds the workflow spec digest, role binding digest, input artifact digests, approval ref, and attempt index.
7. Between-step cancellation is deterministic; active-run cancellation inherits the WP3b WATCH caveat.
8. Read-only compensation is bookkeeping now, preserving a seam for WP5 sandbox rollback later.

## WP3b caveat carried forward

PR #140 merged the bounded cancellation bridge and fail-closed logic, but the PR
body recorded that real host/ACP `--cancel-during-turn` did not reliably prove
active-run cancellation. WP4 design therefore does not claim active-run cancellation
success. If active-run cancellation cannot be safely confirmed, the in-flight step
must become `indeterminate` / WATCH and must not propagate artifacts downstream.

## Files changed

```text
docs/plans/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design.md
docs/plans/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design-manifest.yaml
docs/dev_log/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design.md
docs/roadmap/current-status.md
```

No source, test, script, Gateway, Feishu, platform, runtime, or production config
files should change in this design PR.

## Verification results

Final local verification before commit:

```text
changed_files: docs/roadmap/current-status.md; docs/plans/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design.md; docs/plans/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design-manifest.yaml; docs/dev_log/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design.md
unexpected_changed_files: []
machine_status_json_ok: true
manifest_scope_ok: true
missing_plan_sections: []
status_checks: last_updated_2026_06_17=true; pr140_latest_table=true; wp4_tail_candidate=true; no_wp3b_separately_gated=true
active_run_cancellation_watch_ok: true
secret_hits: []
forbidden_positive_claims: []
docs_static_validation: ok
git_diff_check: ok
Codex blocker-only re-review: VERDICT: PASS / BLOCKERS: None
```

No source, test, script, Gateway, Feishu, platform, runtime, or production config
files changed in this design PR.

## Next gate after this PR

This design PR, if merged, makes WP4 implementation eligible to request using:

```text
approve_agent_run_supervisor_sachima_controlled_ai_flow_local_offline_orchestration_implementation_read_only_roles_only_bounded_steps_no_write_roles_no_auto_routing_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

That implementation approval is not granted by this design gate.
