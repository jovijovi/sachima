# P6-B bounded read-only real-agent step execution — PRD

Date: 2026-06-26
Status: Draft PRD for docs-only pre-development governance.

## 1. Background and live truth

PR #169 merged P6-A into `release/sachima` with merge commit `6a447840e35b538075c09b989d8eb357aa20087e`. P6-A adds a default-off P6 admission/composition layer over unmodified WP4 controlled AI FLOW orchestration and the existing P5 StepExecutor seam. It proves controlled-deterministic / injected-fake step bodies only, sanitized P6 evidence, hermetic-local Temporal proof, and active-run cancellation WATCH preservation.

The default Sachima runtime checkout was fast-forwarded to a later `release/sachima` head that contains PR #169, and the default Gateway was restarted and self-checked. That operational rollout does not approve live Sachima user traffic, Feishu/IM delivery, Gateway-owned runtime lifecycle, production config writes, real external delivery, write roles, or default-on behavior.

This P6-B governance packet folds the post-PR #169 merged-state wording tail into the next substantive planning PR. It is not a standalone bookkeeping PR and it is not source implementation.

## 2. Problem

P6-A still uses controlled-deterministic or injected/fake step bodies. Sachima cannot yet run a selected AI FLOW step through a real Codex/Claude/acpx agent while preserving the existing P6/WP4/P5 boundaries:

- default-off exact approval gates;
- caller-owned runtime/control surface;
- claim-check-only durable state;
- sanitized progress/evidence;
- active-run cancellation WATCH semantics;
- no unapproved writes, delivery, Gateway mutation, or live/default-on behavior.

The next useful product step is a bounded read-only real-agent step under the same control surface, starting with planning/report generation rather than code mutation.

## 3. Goal

Define the governance, architecture, and acceptance criteria for a later P6-B implementation that can execute exactly one bounded read-only real-agent AI FLOW step behind the P6 control surface, with explicit operator approval and fail-closed evidence, without enabling write roles, live delivery, Gateway ownership, production config, or real external effects.

## 4. In scope for this PR

This PR is docs-only pre-development governance:

1. PRD for P6-B bounded read-only real-agent step execution.
2. Claude Code architect teach-back and no-code technical solution.
3. Independent Codex blocker review of the PRD / solution packet.
4. Roadmap/current-status cleanup for PR #169 merged truth and the P6-B next allowed request.
5. User review packet with an exact later implementation approval phrase.

## 5. Out of scope / non-approvals

This PR approves none of:

```text
source implementation
real agent execution
real acpx/npx/Claude/Codex invocation
write-capable roles
file writes by agent steps
git commits, pushes, PR creation, or PR merge by agent steps
external API/tool side effects
Gateway involvement or mutation
Gateway restart/reload
Feishu/IM/live/default-on behavior
platform adapter mutation
production config writes
production Temporal cluster/traffic
real external delivery
additional or unbounded persistent-session execution
additional or unbounded cancellation execution
clean active-run cancellation claims beyond WATCH
```

## 6. Later P6-B implementation intent

A later separately approved implementation may add a narrow real-agent step execution seam if and only if it remains:

- default-off behind a new P6-B exact approval token;
- limited to read-only role(s) and a selected workflow/step class;
- local/offline or hermetic/staging only;
- backed by an atomic pre-launch claim / replay guard before any real launch;
- no-shell / argv-list / pinned local runner only; no `npx` network fetch evidence;
- no raw prompt, platform IDs, tool output, card JSON, media bytes/paths, credentials, or raw exception text in durable state/history/progress/cards/evidence;
- no write roles, no file mutation, no git mutation, no external delivery;
- no Gateway-owned lifecycle or production config writes.

## 7. Candidate first workflow

The first P6-B workflow should be a read-only planning/report step, not code mutation. Recommended candidate:

```text
bounded_read_only_planning_report
```

It should consume claim-checked inputs and produce a sanitized report artifact reference plus bounded summary evidence. It may inspect repo files only through an approved read-only role/tool policy and must not write files, commit, push, create PRs, call delivery APIs, or mutate runtime config.

## 8. Functional requirements

- **FR1 — P6-B admission:** exact token + enabled flag + operator gate must fail closed before any real-agent launch.
- **FR2 — pre-launch claim:** an atomic durable claim must be recorded before real launch; identical replay returns existing projection and conflicting replay fails closed before launch.
- **FR3 — read-only role binding:** only explicitly approved read-only Codex/Claude/acpx role specs are allowed; write roles are rejected before launch.
- **FR4 — runner provenance:** runner path/version/provenance must be pinned and locally verified; `npx`/network-fetch fallback is forbidden.
- **FR5 — sanitized prompt materialization:** raw inputs are transformed into claim-checked refs/digests and bounded prompt material; no raw platform material is stored in durable state.
- **FR6 — StepExecutor seam preservation:** real-agent step result must still return a `StepExecutionOutcome`-compatible sanitized projection; WP4/WP5 contracts are not weakened.
- **FR7 — progress/evidence:** progress snapshots and final evidence expose refs/counts/statuses/stable codes only.
- **FR8 — cancellation/recovery:** active-run cancellation remains WATCH unless cleanup is proven by existing approved semantics; no clean active-run cancellation overclaim.
- **FR9 — no live/delivery/Gateway:** implementation must not import or mutate Gateway, Feishu, platform adapters, delivery, production config, services, or public ingress.
- **FR10 — separate real-smoke approval:** even after implementation, any actual bounded real-agent smoke requires a separate explicit approval unless the implementation approval phrase names the exact smoke.

## 9. Acceptance criteria for this docs-only governance PR

- PR #169 merged truth is reflected in active roadmap/status surfaces.
- P6-B scope, non-approvals, and risk axes are explicit.
- Claude teach-back identifies no P0/P1 misunderstandings.
- No-code technical solution defines exact candidate surfaces, gates, tests, and approval split.
- Codex blocker review returns PASS or all blockers are fixed and re-reviewed.
- Docs/status gates pass: YAML parse, diff check, stale P6-A wording scan, docs-only changed-file allowlist, forbidden source/runtime changes scan.

## 10. Later implementation approval phrase

If this governance PR passes and the user wants source implementation, use a phrase like:

```text
approve_agent_run_supervisor_sachima_p6b_bounded_read_only_real_agent_step_execution_implementation_default_off_single_read_only_planning_report_step_pinned_local_runner_only_no_write_roles_no_file_mutation_no_git_mutation_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery_no_real_smoke_without_separate_approval
```

A later bounded real-smoke approval, if desired, must name the exact runner, role, workflow, max turns/time, repo/workdir, and evidence destination.
