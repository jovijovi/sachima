# P6 Runtime Lifecycle / Controlled Attach Plan — Dev log

Date: 2026-06-28
Branch: `docs/runtime-lifecycle-controlled-attach-plan`
Status: Local docs-only gates, Claude teach-back, and Codex blocker review passed; PR/CI pending.

## Starting live truth

```text
base_branch: release/sachima
base_head: 890ed3f89b2a995dc3bf910d4a4a4cc57f54e7c9
open_prs_against_release_sachima: 0
PR #181: MERGED, bounded read-only real-smoke blocker fixes + PASS evidence
PR #182: MERGED, P6-B status closure
post_pr182_cleanup: local worktree/branch removed; audit under logs/sachima-post-pr182-cleanup-20260628T033153Z
```

## Scope

Docs-only governance for the next safe mainline: P6 runtime lifecycle / controlled attach plan. No implementation, no runtime start, no Worker start, no additional acpx/npx/agent execution, no Gateway/Feishu/live behavior, no production config, no service restart, no real delivery.

## Authority read

- `GOAL.md`
- `AGENTS.md`
- `docs/roadmap/current-status.md`
- `docs/roadmap/tail-register.md`
- `docs/roadmap/boundary-register.md`
- `docs/roadmap/phase-ledger.md`
- `docs/roadmap/evidence-index.md`
- P5/P6/P6-B plans and implementation records
- CodeGraph status/explore over P5/P6 runtime/control surfaces

## CodeGraph evidence

Worktree-local CodeGraph index initialized:

```text
files: 3903
nodes: 109092
edges: 315672
```

Key surfaces identified:

- `sachima_supervisor/p5_temporal/control_surface.py`
- `sachima_supervisor/p5_temporal/runtime_client.py`
- `sachima_supervisor/p5_temporal/step_executor.py`
- `sachima_supervisor/p6_controlled_ai_flow.py`
- `sachima_supervisor/p6b_read_only_real_agent.py`
- `sachima_supervisor/activity_controlled_exec.py`
- `sachima_supervisor/ai_flow_*`

## Artifacts

- PRD: `docs/plans/2026-06-28-agent-run-supervisor-sachima-p6-runtime-lifecycle-controlled-attach-plan-prd.md`
- Technical solution: `docs/plans/2026-06-28-agent-run-supervisor-sachima-p6-runtime-lifecycle-controlled-attach-plan-technical-solution.md`
- Manifest: `docs/plans/2026-06-28-agent-run-supervisor-sachima-p6-runtime-lifecycle-controlled-attach-plan-manifest.yaml`
- User review packet: `docs/plans/2026-06-28-agent-run-supervisor-sachima-p6-runtime-lifecycle-controlled-attach-plan-user-review-packet.md`

## Completed local gates

- Claude architecture teach-back: PASS after P1 doc-hardening fixes.
- Codex blocker review: PASS / no blockers / no worktree mutation.
- docs-only allowlist: PASS.
- YAML parse and manifest false-scope assertions: PASS.
- `git diff --check`: PASS.
- `tools/sync_roadmap_status.py --check`: PASS.
- stale wording scan: PASS.
- forbidden implementation/runtime/live surface scan: PASS.
- GitHub PR, CI, and head-SHA-bound approval card remain the next PR-stage gates.

## Claude architecture teach-back

Claude Code intended path: `claude-opus-4-8[1m]` / effort `max`.

Smoke result:

```text
CLAUDE_SMOKE_OK
```

First teach-back returned REQUEST_CHANGES with two P1 doc-hardening findings:

1. Point-of-use `start` mapping needed to explicitly forbid binding the P6-B real-agent runner without separate real-execution approval.
2. The `批准实施` framing needed to state it covers only this docs-only governance gate, not source implementation.

Hermes applied doc fixes in the PRD, technical solution, and user review packet. Claude re-review then returned PASS and confirmed all five prior hardening points resolved. Final teach-back is recorded in:

```text
docs/plans/2026-06-28-agent-run-supervisor-sachima-p6-runtime-lifecycle-controlled-attach-plan-claude-teach-back.md
```

## Codex blocker review

Codex CLI 0.142.2 was run as a read-only blocker reviewer using the established no-bwrap fallback because the local bubblewrap sandbox path is known unusable on this host. Hermes enforced read-only provenance with pre/post content hashes over the dirty/untracked working tree.

Final local review result:

```text
VERDICT: PASS
SCORE: 96
BLOCKERS:
- None
mutated: no
```

Codex WATCH items were non-blocking: the future approval phrase relies on the PRD non-goals coupling for exclusions such as public ingress, service restart, production traffic, platform-adapter mutation, and broader controlled AI FLOW; the PRD explicitly binds those exclusions.
