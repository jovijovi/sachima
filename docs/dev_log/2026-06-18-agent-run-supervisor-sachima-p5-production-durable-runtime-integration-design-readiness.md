# P5 — Production durable runtime integration design & readiness dev log

**Date:** 2026-06-18
**Branch:** `docs/p5-durable-runtime-readiness`
**Base:** `release/sachima` at `41e645189aa4de889c95b97a61a6d4fbb76783cd` (latest non-status-sync base; branch tip is the status-sync self-commit `68a058dd3`)
**Status:** Candidate docs-only design / readiness gate; PR #147 open (`https://github.com/jovijovi/sachima/pull/147`); pending merge decision; Codex primary review PASS / BLOCKERS None.

## Approval boundary

User approved the exact design / readiness scope token:

```text
approve_agent_run_supervisor_sachima_p5_production_durable_runtime_integration_design_readiness_docs_only_no_implementation_no_runtime_start_no_worker_start_no_controlled_ai_flow_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Interpretation used by Hermes:

- P5 design + readiness only (the current roadmap `P5 — Production durable runtime integration` row).
- No implementation/source/test/script/config behavior changes.
- No runtime start or durable-backend attach; no Worker start or auto-start.
- No controlled AI FLOW execution (that is roadmap P6, which stays blocked until P5 evidence passes).
- No write-capable roles (roadmap P5 ≠ the remaining-goals plan's WP5 write roles).
- No Gateway involvement/mutation; no Gateway-owned or auto-started Temporal/Worker/service/socket/subprocess.
- No Feishu/IM delivery; no live/default-on; no public ingress; no production config writes; no real delivery.

Two tokens are quoted in the packet but **not granted** by this PR:

```text
# future local caller-owned runtime adapter implementation (NOT granted here)
approve_agent_run_supervisor_sachima_p5_production_durable_runtime_integration_local_caller_owned_runtime_adapter_implementation_no_gateway_owned_lifecycle_no_worker_auto_start_no_controlled_ai_flow_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery

# external Temporal service / Worker process lifecycle (separate token; NOT granted here)
approve_external_temporal_service_or_worker_lifecycle_for_sachima_p5_runtime
```

## Naming clarification (drift guard)

This packet is for **roadmap P5 — production durable runtime integration**. It is **not** the older remaining-goals plan's **WP5 — write-capable roles**. Topically, roadmap P5 corresponds to the remaining-goals plan's WP6 durable-runtime content. P5 introduces no write roles; all P5 roles stay read-only. Controlled AI FLOW execution is roadmap P6 and remains blocked until P5 durable-runtime evidence passes.

## Role split

- **Hermes:** PM / controller / verifier / repo operator / evidence arbiter. Constrains the approval boundary, runs local verification and the Codex primary review, and performs commit/push/PR as repo-transport steps outside this packet's content.
- **Claude Code:** architect + documentation engineer. Exact model smoke passed with `claude-opus-4-8[1m]` / `--effort max`. An initial long prompt timed out without artifacts; a narrower `acceptEdits` docs-only pass created the packet/manifest/dev-log/roadmap update before the outer terminal timeout. Hermes treats Claude's file edits as draft authoring evidence and still verifies every changed file independently.
- **Codex CLI:** primary blocker reviewer for the final docs-only diff. Review was repo-aware, read-only by instruction, bound to the uncommitted/untracked candidate in this worktree, and returned `VERDICT: PASS` / `BLOCKERS: None`. It inspected the changed-file set, manifest parse/candidate booleans, P5-vs-WP5 naming distinction, WP3b WATCH preservation, runtime ownership boundary, P6 blocking, cross-process claim-store requirement, no-throw/no-leak rules, and stale/contradictory current-status risk.

## Fresh state used

Preflight evidence before authoring (from the repo and the roadmap machine status block):

```text
repo: jovijovi/sachima
base branch: release/sachima
machine base_head (excludes status-sync self-commits): 41e645189aa4de889c95b97a61a6d4fbb76783cd (PR #146)
worktree branch: docs/p5-durable-runtime-readiness
worktree branch tip: 68a058dd3 (docs: sync machine roadmap status [skip status-sync])
WP4 design: PR #142 MERGED, merge commit bb5e5d9bf707fde7934939cc473544511bd65ffd
WP4 implementation slice 1: PR #145 MERGED, merge commit c4ce77ce52020015f37710025d601a9ecf021a13 (627 supervisor tests + self-test, CI, Codex PASS)
WP3b: PR #140 MERGED, merge commit 3fe18ab9451d290a70036697da118351d604be27; active-run host/ACP cancellation remains WATCH
```

This is a docs-only design / readiness gate; no CodeGraph index exists in this worktree and no CodeGraph evidence is claimed for this PR.

## Design decisions

1. **Goal.** Attach a real durable runtime behind a caller-supplied control surface so long Sachima/FlowWeaver workflows survive retries, restarts, queries, updates, cancellations, and recovery.
2. **Ownership.** Sachima/FlowWeaver (the caller) owns the durable runtime lifecycle, the control surface, and all durable state; the supervisor library only calls the control surface via the existing executor Protocol seam; the Gateway never owns or auto-starts a Temporal/Worker/service/socket/subprocess lifecycle; the runtime is caller-supplied.
3. **Control surface.** `start`, `query`, `update`, `cancel`, `recover`, `close`/terminalize, each with stable sanitized result/error codes and TOCTOU-safe lease/epoch + state_version binding.
4. **Durable records.** Runtime run / workflow / activity / session / step-attempt records; lease/epoch/state_version; idempotency key; query snapshot; cancellation record; recovery record; artifact refs (claim-check only).
5. **Cross-process transactional claim store is required** for any later production implementation; the merged in-process lock-guarded CAS (`ai_flow_store.py`) is single-process and insufficient for durable, cross-process, restart-surviving claims.
6. **No-throw wrappers + stable failure taxonomy.** Every control-surface operation catches backend exceptions and returns a stable code; no traceback/PID/backend detail crosses the boundary.
7. **Runtime-history no-leak.** Durable records, snapshots, evidence, **and** the runtime's serialized event-history bytes carry only refs/digests/stable codes/counts. Two scans are required: a JSON projection scan **and** a serialized event/history-bytes scan (because durable backends persist inputs/outputs in their own event history).
8. **Required probes.** Duplicate start, retry, timeout, cancellation, recovery, restart/replay, and query snapshot consistency — the durable-runtime evidence bar for a later implementation.
9. **Acceptance checklist, scoring rubric (≥ 18/20, no 0, no kill-criterion), kill criteria (K1–K8), and ordered implementation gates (G0–G8)** govern the later implementation.

## WP3b caveat carried forward

PR #140 merged the bounded cancellation bridge with verified deterministic self-test and fail-closed semantics, but real host/ACP `--cancel-during-turn` did not reliably prove active-run cancellation. P5 preserves that WATCH: between-step cancellation may be deterministic, but active-run cancellation stays best-effort/WATCH. When active-run interruption cannot be safely confirmed, the durable `CancellationRecord` is held `cancel_ambiguous` with the `active_run_watch` marker, never promoted to `cancelled`, and no artifact is propagated and no step relaunched. P5 records, probes, and evidence must not overclaim reliable active-run cancellation.

## Relationship to WP4 (merged) and P6 (blocked)

- WP4 merged a local/offline, injected-fakes-only controlled AI FLOW orchestrator (PR #142 design, PR #145 implementation) over an in-process CAS store with an executor Protocol seam that has no real runner.
- P5 (this gate, then a later implementation) attaches a caller-supplied durable runtime behind the control surface and **produces durable runtime evidence** (the probes).
- P6 (controlled AI FLOW real execution) stays **blocked** until the P5 durable-runtime evidence passes. P5 does not itself execute a controlled AI FLOW.

## Files changed

```text
docs/plans/2026-06-18-agent-run-supervisor-sachima-p5-production-durable-runtime-integration-design-readiness.md
docs/plans/2026-06-18-agent-run-supervisor-sachima-p5-production-durable-runtime-integration-design-readiness-manifest.yaml
docs/dev_log/2026-06-18-agent-run-supervisor-sachima-p5-production-durable-runtime-integration-design-readiness.md
docs/roadmap/current-status.md
```

No source, test, script, role, config, Gateway, Feishu, platform, runtime, or production config files change in this design / readiness PR.

## Verification (docs-only gate)

Hermes-run verification before commit/PR:

```text
changed_files: docs/plans/2026-06-18-...-p5-...-design-readiness.md; docs/plans/2026-06-18-...-p5-...-design-readiness-manifest.yaml; docs/dev_log/2026-06-18-...-p5-...-design-readiness.md; docs/roadmap/current-status.md
unexpected_changed_files: []
generated_status_json_block_edited: false (tools/sync_roadmap_status.py --check: machine status block up to date)
git_diff_check: ok
manifest_yaml_parse: ok
manifest_false_booleans_present: implementation/runtime_start/worker_start/controlled_ai_flow/gateway/feishu/live/production_config/real_delivery = false
manifest_candidate_fields: codex_primary_review: "PASS / BLOCKERS: None"; pr_number: 147; pr_url: https://github.com/jovijovi/sachima/pull/147; merge_commit: null; merged_at: null; ci_validation_source: live GitHub PR checks on the latest pushed head
status_markers_present: true
naming_clarification_present: true (P5 durable runtime != remaining-goals WP5 write roles)
wp3b_active_run_cancellation_watch_preserved: true
runtime_history_no_leak_two_scans_specified: true (JSON + serialized event/history bytes)
required_probes_listed: duplicate_start, retry, timeout, cancellation, recovery, restart_replay, query_snapshot_consistency
secret_shaped_scan: no hits in changed files
forbidden_changed_file_allowlist: docs/status only
Codex primary blocker review: VERDICT: PASS / BLOCKERS: None
post_review_status_field_patch_validation: manifest/dev-log/current-status updated from pending -> PASS and revalidated
```

No runtime tests are run by this PR because it is docs-only and approves no implementation/runtime start.

## Next gate after this PR

If merged, this packet makes a P5 **local caller-owned runtime-adapter implementation eligible to request** using:

```text
approve_agent_run_supervisor_sachima_p5_production_durable_runtime_integration_local_caller_owned_runtime_adapter_implementation_no_gateway_owned_lifecycle_no_worker_auto_start_no_controlled_ai_flow_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Any external Temporal service or Worker process lifecycle, if ever proposed, requires its own separate token (`approve_external_temporal_service_or_worker_lifecycle_for_sachima_p5_runtime`). Neither token is granted by this design / readiness gate, and controlled AI FLOW execution (P6) remains blocked until the P5 durable-runtime evidence passes.
