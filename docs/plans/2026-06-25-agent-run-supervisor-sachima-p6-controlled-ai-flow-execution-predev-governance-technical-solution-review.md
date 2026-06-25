# P6 Controlled AI FLOW execution — Codex blocker review

Date: 2026-06-25
Reviewer: Codex CLI
Command shape: `codex exec --ignore-user-config --ignore-rules --sandbox read-only -m gpt-5.5 --output-last-message .hermes/tmp/p6_codex_review_output.txt -`
Review packet: `.hermes/tmp/p6_codex_review_prompt.md` (local ignored artifact)

## Verdict

VERDICT: PASS
SCORE: 92

## Blockers

- None.

## Non-blocking findings

- Manifest says Claude teach-back requires “no P0/P1 questions,” while the teach-back records P1 items that are resolved in the technical solution. This is not blocking because the P1s are explicitly resolved, but wording would be clearer as “no unresolved P0/P1 questions.”
- Manifest references future technical-review and user-review-packet files not shown in git status. This is resolved by adding this review artifact and the user review packet before final verification.

## Review notes

- Docs-only boundary is preserved: changed files are limited to `docs/roadmap`, `docs/plans`, and `docs/dev_log`; manifest explicitly forbids source, tests/scripts, runtime, config, Gateway/Feishu, and delivery changes.
- P6-A scope is narrow: Temporal-backed controlled AI FLOW execution only with controlled-deterministic or injected/fake step bodies, default-off, with separate later implementation approval required.
- Real `acpx`/`npx`/Claude/Codex runner launch, write roles, Gateway/Feishu/live/default-on behavior, production config, production traffic, and real delivery remain explicitly non-approved across PRD, teach-back, technical solution, manifest, dev log, and current-status diff.
- WP3b active-run cancellation WATCH is explicit and not overclaimed; technical solution states P6-A does not prove clean active-run cancellation and maps ambiguous cancellation to WATCH / fail-closed behavior.
- WP4/P5 boundary is not weakened. The solution correctly recognizes `P5TemporalStepExecutor` already matches `StepExecutor` and says not to build a redundant bridge/adapter.
- Gate suite is concrete enough for later implementation and review: changed-file allowlist, forbidden surface scans, no-real-runner scan, no-leak scans, Temporal SCAN 1/2, duplicate/divergent/recover/cancel probes, WP4 oracle/conformance, P5 executor integration, docs/status scan, and exact-head Codex review.
- Current-status wording updates post-P5 calibration to merged PR #167 and identifies this branch as current docs-only P6 governance, without implying implementation approval.
- Later approval phrase is narrow enough: P6-A only, default-off, controlled/fake steps only, no real agent execution, no write roles, no live/Gateway/Feishu/production config/real delivery.

## Sandbox note

Codex emitted a warning that its Linux sandbox uses bubblewrap and needs access to create user namespaces. The run still completed successfully under `--sandbox read-only`; no bwrap failure occurred in this review.
