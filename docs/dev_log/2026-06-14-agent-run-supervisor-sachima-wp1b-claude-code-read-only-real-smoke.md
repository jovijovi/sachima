# WP1b — Claude Code read-only bounded real local smoke

Date: 2026-06-14
Status: real smoke passed; status closure PR #134 merged (merge commit `2f8fe8d70119`)
Scope: local/offline only; one bounded read-only Claude Code one-shot through the Sachima controlled local exec wrapper

## Approval

```text
approve_agent_run_supervisor_sachima_claude_code_read_only_bounded_real_local_smoke_pinned_local_runner_only_single_run_no_unbounded_no_cancellation_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

## Evidence bundle

Evidence is intentionally outside the repository:

```text
/data/agents/workspace/hermes/outputs/sachima/wp1b-claude-readonly-smoke-20260614T162903Z
```

Key sanitized files:

```text
preflight-summary.json
fresh-acpx-provisioning.json
post-verify-summary.json
host-postverify-compact.json
host-postverify-processes.json
host-postverify-policy-redaction.json
```

## Result

```text
execution_pipeline: PASS
business_task: VERDICT: PASS
```

Host-side post-verify recorded:

- exactly one new `agent-run-supervisor` run directory;
- argv used the pinned local `acpx 0.10.0` path and `claude exec`;
- argv included `--json-strict` and `--no-terminal`;
- no forbidden package-runner fallback (`npx`, `npm exec`, `pnpm`, `yarn`, `bunx`) appeared in the argv;
- replay check did not call the prompt materializer or supervisor and created no extra run;
- repo worktree stayed clean;
- post-smoke process scan found no leftover `acpx` or `claude` process;
- generated permission policy was default-deny with read/search auto-approved and delete/edit/execute/fetch/move/other/switch_mode auto-denied;
- redaction report contained sensitive environment-key names only, with values redacted.

## Fresh host-local runner provisioning note

The older Phase D host-local DoR worktree that had held the pinned `acpx` install had already been cleaned up as stale local worktree state. Before the smoke, the operator reprovisioned `acpx@0.10.0` under this run's out-of-repo evidence directory, then verified the same pinned digest:

```text
version: 0.10.0
sha256: sha256:54d586ec3916fb55c7ea724df4b868d3a958492081e2cd21bdfb1ae8d67d46a6
```

This provisioning was a pre-smoke host-local setup step. The smoke itself used the absolute local `runner.acpx_binary` path and did not use `npx`, `npm exec`, `pnpm`, `yarn`, or `bunx` as the runner.

## What this proves

This proves exactly one bounded, local/offline, read-only Claude Code one-shot can pass through Sachima's controlled local exec wrapper with pinned local `acpx` provenance, sanitized durable state, out-of-repo artifacts, no duplicate replay launch, and no leftover local process.

## Non-approvals still held

This does not approve:

- additional real local smokes or additional real AGENT/acpx execution;
- persistent or unbounded sessions beyond separately approved gates;
- cancellation execution;
- write-capable Claude or Codex roles;
- controlled AI FLOW execution;
- Satine or Hermes-profile ACP execution;
- Gateway / Feishu / IM / public ingress / real delivery;
- production config writes, service restarts, or platform adapter mutation.

## Next gate

The next mainline gate is WP2 bounded multi-turn persistent session hardening, if separately approved.
