# WP1a — Claude Code read-only role + capability-gate extension (local/offline, injected fakes only)

Date: 2026-06-14
Status: merged in PR #131 (`d2e8c49f7042715062ec755eb8177396d6df3bcd`)
Branch: `feature/wp1a-claude-code-read-only`
Base: `release/sachima` at `2cf507c3a8bd6cdba354dd7d699685fa146441a8`

## Scope

WP1a is the first concrete implementation gate recommended by the remaining-goals
plan merged in PR #128. It adds a **Sachima-side read-only Claude Code reviewer
role** plus the **minimal capability-gate extension** that lets the existing
controlled local one-shot `exec` wrapper admit it — with **injected fakes / a
deterministic self-test only**.

WP1a deliberately does **not** add real Claude Code execution. That is WP1b and
stays separately gated.

### Exact approval interpretation

```text
approve_agent_run_supervisor_sachima_claude_code_read_only_role_capability_extension_local_offline_implementation_injected_fakes_only_no_real_smoke_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

## What changed

1. `sachima_supervisor/activity_controlled_exec.py` (minimal delta):
   - Added the runnable allowlist entry
     `sachima.claude.read_only_reviewer -> roles/claude_code_read_only_reviewer_v1.json`.
   - Added `CONTROLLED_EXEC_ROLE_ADAPTER_AGENT`, a per-role required-adapter map
     pinned exactly to `{codex role: "codex", claude read-only role: "claude"}`.
     It is kept in lockstep with the runnable allowlist (same key set) and
     disjoint from `CONTROLLED_EXEC_FUTURE_ROLE_KEYS`.
   - `_check_role_capability` now requires the role file's
     `runner.adapter_agent` to equal `CONTROLLED_EXEC_ROLE_ADAPTER_AGENT[role_key]`,
     so a Codex role can never run under the Claude adapter and vice versa. Every
     read/search-only permission gate and the `session.strategy == exec` gate are
     unchanged.
2. `sachima_supervisor/roles/claude_code_read_only_reviewer_v1.json` — committed,
   **null `acpx_binary`** (non-runnable by construction), `adapter_agent: claude`,
   read/search-only, `session.strategy: exec`, no forbidden delivery/live wording.
3. `scripts/sachima_claude_code_read_only_smoke.py` — deterministic `--self-test`
   only. It exports `run_self_test()` and `main(argv=None)`, uses an injected fake
   supervisor + a temporary pinned role overlay (placeholder local `acpx` path),
   and never imports or touches subprocess / network / socket / Gateway / Feishu
   surface. Without `--self-test` it prints `ok=false` and exits `2` because the
   real Claude Code smoke (WP1b) is not approved.

## Non-runnable-by-construction posture

The committed Claude role keeps `acpx_binary: null`, exactly like the committed
Codex role. The provenance gate fails closed on a null binary, so the committed
config cannot launch anything until an operator pins a verified local `acpx`
through an out-of-tree overlay. The self-test exercises the admit path only via a
temporary overlay with a placeholder path whose **shape** satisfies provenance;
nothing is ever executed.

## Explicit non-approvals (held)

`real_claude_code_smoke` (WP1b), `additional_real_local_smoke_execution`,
`additional_real_agent_execution`, `additional_acpx_invocation`,
`npx_fallback_or_network_fetch`, `write_capable_claude_or_codex_roles`,
`multi_turn_or_persistent_sessions`, `cancellation_execution`,
`controlled_ai_flow_execution`, `satine_or_hermes_profile_acp_execution`,
`gateway_involvement_or_mutation`, `feishu_or_im_delivery`,
`live_or_default_on_behavior`, `public_ingress`, `production_config_write`,
`real_delivery`.

## Verification

```text
uv run --extra dev pytest tests/sachima_supervisor/test_activity_controlled_exec.py tests/sachima_supervisor/test_claude_code_read_only_role.py -q
uv run --extra dev python scripts/sachima_claude_code_read_only_smoke.py --self-test
uv run --extra dev pytest tests/sachima_supervisor -q
uv run --extra dev python -m compileall sachima_supervisor scripts/sachima_claude_code_read_only_smoke.py
git diff --check
codegraph status
```

Merged in PR #131. WP1b remains separately gated and is not approved by this implementation.
