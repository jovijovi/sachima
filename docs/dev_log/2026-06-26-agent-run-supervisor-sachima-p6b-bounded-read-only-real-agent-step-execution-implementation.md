# Dev log — P6-B bounded read-only real-agent step execution implementation

Date: 2026-06-26
Branch: `feat/p6b-read-only-real-agent-step-implementation`
Base: `sachima/release/sachima` at `7c303236fe65537c54f83ecf52ffc1bd8b3f126d`
Status: Implementation written by Claude Code (main programmer); Hermes local gates passed after controller fixups. Default-off, fake-runner gates only. No real agent, no real smoke.

## Scope binding

After PR #170 (P6-B docs-only pre-development governance) merged, the user instruction "OK，继续" was bound by Hermes to the narrow Stage-1 source implementation scope documented by PR #170 — exact phrase:

```text
approve_agent_run_supervisor_sachima_p6b_bounded_read_only_real_agent_step_execution_implementation_default_off_single_read_only_planning_report_step_pinned_local_runner_only_no_write_roles_no_file_mutation_no_git_mutation_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery_no_real_smoke_without_separate_approval
```

## Implementation provenance

Claude Code acted as main programmer with a strict TDD prompt. As with P6-A, Claude could not run shell/test commands inside the governed worktree (every `uv run` / `python` invocation required approval and was blocked), so **no test evidence is asserted by Claude**. Claude wrote the module, the deterministic prompt + fixture, and the full TDD test suite, and reasoned about RED/GREEN statically; **Hermes runs the focused RED/GREEN cycles and the gates** and records live results in the manifest.

## What was built

Additive, fake-safe source slice — preferred allowlist honored:

- `sachima_supervisor/p6b_read_only_real_agent.py` — the only required new production module:
  the `P6BReadOnlyRealAgentStepExecutor` bridge (WP4 `StepExecutor` protocol + oracle control
  surface), the exact P6-B approval token (split literal so the static boundary scan never sees
  the contiguous boundary words), and the additive outer `p6b_*` codes.
- `sachima_supervisor/p6b_planning_report_prompt.py` — deterministic planning/report prompt
  builder + materializer (mirrors `smoke_prompt.py`).
- `tests/fixtures/sachima_supervisor/p6b_planning_report_prompt.v1.txt` — byte-mirror fixture.
- `tests/sachima_supervisor/p6b_read_only_real_agent/**` — unit + hermetic-composition tests
  with an injected fake read-only runner (no real acpx/agent).

Decisions:

- **No new role file.** The bridge reuses the existing read-only controlled roles
  (`sachima.claude.read_only_reviewer` / `sachima.codex.primary_reviewer`). They are committed
  null-binary, so the path stays non-runnable by construction; `activity_controlled_exec.py`
  was NOT edited.
- **No reimplemented runner/claim/provenance/prompt machinery.** The bridge delegates to the
  unmodified `start_controlled_local_exec`, which owns provenance, the atomic pre-launch claim,
  read-only capability, the prompt screen, and the sanitized projection.
- **Output claim-check** is a thin injected `artifact_sink` seam returning exactly one
  sanitized `ArtifactRef`; bytes never enter durable state; WP4's `_verify_single_output`
  remains the authority on kind/producer/bytes.

## Reused walls left unmodified

`sachima_supervisor/ai_flow_*.py`, `p6_controlled_ai_flow.py`, `p5_temporal/**`,
`activity_controlled_exec.py`, `activity_session_real_execution.py`, `activity_preflight.py`.
Only additive files under the §2 allowlist + docs were touched.

## Hermes verification results

Hermes ran the focused gates after applying two controller fixups: removing a source-doc static
scan false positive and tightening P6-B active-run cancellation so even confirmed-looking lower
layer interrupt outcomes preserve WATCH instead of claiming a clean cancel. Passing live gates:

- P6-B tests: `60 passed`.
- Reused-wall regression tests: `274 passed`.
- P6-B hermetic + P5 determinism replay: `7 passed`.
- Ruff: `All checks passed!`.
- `git diff --check`: passed.
- Roadmap machine-status sync check: up to date.
- Changed-file allowlist, forbidden-surface, source-forbidden, and secret-shaped literal scans: passed.

## Open WATCH carried forward

A later real smoke is a separate Stage-2 approval. It requires concrete crash-after-claim /
restart / recover-without-relaunch evidence; the controlled-exec claim store is in-process, so
an implementation that cannot prove cross-process no-relaunch must remain fake-only and fail
closed. WP3b active-run cancellation WATCH remains open; P6-B does not claim clean active-run
cancellation.

## Non-approvals preserved

No real agent/acpx/npx/Claude/Codex step bodies; no real smoke; no write roles; no file/git
mutation by agent steps; no external side effects; no Gateway/Feishu/platform/delivery/public
ingress/production config; no new dependencies (`pyproject.toml`/`uv.lock` untouched); no edits
to the reused walls.
