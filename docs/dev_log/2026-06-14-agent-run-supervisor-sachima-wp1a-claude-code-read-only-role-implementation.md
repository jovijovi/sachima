# Dev Log — WP1a Claude Code read-only role + capability-gate extension

Date: 2026-06-14
Branch: `feature/wp1a-claude-code-read-only`
Base: `release/sachima` at `2cf507c3a8bd6cdba354dd7d699685fa146441a8`
Worktree: `/data/agents/workspace/hermes/worktrees/sachima/wp1a-claude-code-read-only`
Status: PR #131 merged — local verification passed; Codex primary blocker review PASS / BLOCKERS None; PR checks passed; merge commit `d2e8c49f7042715062ec755eb8177396d6df3bcd`.

## Boundary

Approved scope (exact token):

```text
approve_agent_run_supervisor_sachima_claude_code_read_only_role_capability_extension_local_offline_implementation_injected_fakes_only_no_real_smoke_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

WP1a adds a Sachima-side **read-only Claude Code reviewer role** and the
**minimal capability-gate extension** that lets the existing controlled local
one-shot `exec` wrapper admit it, with **injected fakes / a deterministic
self-test only**. It holds every prior non-approval and adds none of:

- real Claude Code execution (that is WP1b, separately gated);
- additional real local smoke / real AGENT / additional `acpx` invocation;
- npx / network-fetch runnable fallback;
- write-capable Claude/Codex roles, multi-turn / persistent sessions,
  cancellation execution, controlled AI FLOW, or Satine / Hermes-profile ACP;
- live / default-on behavior, Gateway, Feishu / IM delivery, public ingress,
  production config writes, or real delivery.

## Design

The Phase C controlled local exec wrapper (`activity_controlled_exec`) already
owns the full fail-closed gate chain (approval, mode, role allowlist, material,
operator gate, prior-evidence digest, preflight/lease/state-version binding,
pinned no-fetch runner provenance, read-only capability), the atomic pre-launch
claim/CAS, and the sanitized durable claim state. WP1a does **not** add new
lifecycle semantics — it extends two surfaces minimally:

1. **Runnable allowlist** gains
   `sachima.claude.read_only_reviewer -> roles/claude_code_read_only_reviewer_v1.json`.
   The four write-capable Claude roles and the Codex blocker-only reviewer stay
   in `CONTROLLED_EXEC_FUTURE_ROLE_KEYS`, disjoint from the allowlist.
2. **Per-role adapter binding.** New `CONTROLLED_EXEC_ROLE_ADAPTER_AGENT` maps
   each runnable role key to its single required `runner.adapter_agent`
   (`codex -> codex`, `claude read-only -> claude`). `_check_role_capability`
   now compares the role file's adapter to `CONTROLLED_EXEC_ROLE_ADAPTER_AGENT[role_key]`
   instead of a single hard-coded `codex` constant. A Codex role declaring
   `adapter_agent=claude` (and vice versa) now fails closed with
   `activity_role_capability_rejected`. The map is asserted in lockstep with the
   allowlist (same key set) and disjoint from the future role keys, so a future
   role can never silently become runnable. All read/search-only permission gates
   and the `session.strategy == exec` gate are unchanged.

Committed role `sachima_supervisor/roles/claude_code_read_only_reviewer_v1.json`:
read-only, `session.strategy: exec`, `adapter_agent: claude`, `acpx_binary: null`,
`allowed_roots_security_boundary: false`. Like the committed Codex role, it is
**non-runnable by construction**: the provenance gate fails closed on the null
binary, so an operator must pin a verified local `acpx` through an out-of-tree
overlay before any real run. The committed role text carries no
Gateway/Feishu/webhook/npx/public-ingress/production-config/real-delivery wording.

Smoke `scripts/sachima_claude_code_read_only_smoke.py` is deterministic and
hermetic:

- `--self-test` writes a temporary pinned Claude overlay (placeholder local
  `acpx` path whose *shape* satisfies provenance — nothing is executed), builds a
  durable-state preflight record, and drives `start_controlled_local_exec` with a
  counting fake supervisor. It asserts exactly one supervisor call, a `completed`
  sanitized claim, `business_verdict=None`, the `claude` adapter, and the held
  non-approval `real_claude_smoke_wp1b=false`, then prints a sanitized JSON
  summary and exits `0`.
- Without `--self-test` it fails closed: prints `ok=false`, names WP1b as not
  approved, and exits `2`.
- It imports no subprocess / network / socket / Gateway / Feishu surface, and
  the no-leak/forbidden-surface tests assert the source and the summary stay
  clean.

## TDD notes

The RED tests were authored in a prior run:
`tests/sachima_supervisor/test_claude_code_read_only_role.py` (new) and the WP1a
additions in `tests/sachima_supervisor/test_activity_controlled_exec.py`. This
run implemented the production module delta, committed role, and self-test smoke
to turn them GREEN. No test expectation needed correction: the non-approval
wording the tests require (`wp1b` + `not approved` in the refusal JSON; the
held-non-approval flag in the self-test summary) is fully expressible without
tripping any forbidden-token assertion, so the smoke prints those strings and the
forbidden-surface scanners still pass.

## Local verification

(Recorded by the operator from this worktree; see the manifest for the exact
gate list.)

```text
uv run --extra dev pytest tests/sachima_supervisor/test_activity_controlled_exec.py tests/sachima_supervisor/test_claude_code_read_only_role.py -q
uv run --extra dev python scripts/sachima_claude_code_read_only_smoke.py --self-test
uv run --extra dev pytest tests/sachima_supervisor -q
uv run --extra dev python -m compileall sachima_supervisor scripts/sachima_claude_code_read_only_smoke.py
git diff --check
codegraph status
```

## Codex primary blocker review

```text
VERDICT: PASS
BLOCKERS:
- None
```

## Post-merge status

1. PR #131 merged after CI passed.
2. WP1a remains injected-fakes / deterministic self-test only.
3. WP1b (real read-only Claude Code smoke) stays a separate, later approval.
