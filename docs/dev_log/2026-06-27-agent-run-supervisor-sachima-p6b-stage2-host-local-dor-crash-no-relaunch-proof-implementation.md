# Dev log — P6-B Stage-2 host-local DoR / crash-no-relaunch proof implementation

Date: 2026-06-27
Branch: `feat/p6b-stage2-host-local-dor-proof`
Status: Implementation / proof-candidate branch. Local gates passed. No real agent, no real smoke. Hermes owns review/commit/push/PR.

## Scope binding

The user approved the host-local DoR / crash-no-relaunch proof gate recorded as the next safe
step after the Stage-2 readiness packet (PR #174), with the exact phrase:

```text
approve_agent_run_supervisor_sachima_p6b_stage2_host_local_dor_and_crash_no_relaunch_proof_pinned_local_runner_role_overlay_artifact_sink_evidence_only_no_real_agent_launch_no_real_smoke_no_write_no_git_no_network_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

This is the technical solution's **Option B — fail-closed host-local proof**, not real smoke and
not the Option-A durable cross-process claim store. It implements host-local DoR / proof tooling
only: read files, edit repo code/docs/tests, run local unit tests and temp/fake executable
version-probe tests. No real agent launch, real smoke, acpx-through-anything, npx/npm/network,
Gateway/Feishu/live ingress, production config, service restart, or real delivery.

## What was built

- `sachima_supervisor/p6b_host_local_dor.py` — default-off DoR surface: `P6BHostLocalDorRequest`,
  `assess_p6b_host_local_dor`, `prove_crash_no_relaunch`, `write_p6b_host_local_dor_evidence`, the
  exact Stage-2 DoR approval token (split literal), and additive `p6b_dor_*` stable codes. It
  reuses the merged `P6BReadOnlyRealAgentStepExecutor`, `ControlledLocalExecClaimStore`,
  `verify_pinned_local_acpx_binary`, and the role allowlist/adapter pins **unmodified**, and the
  no-leak `scan_projection_for_leak` contract. No subprocess/shell/network/runner lives in this
  supervisor source.
- `tools/p6b_host_local_dor.py` — CLI that writes a sanitized JSON evidence bundle under an
  out-of-repo evidence root and prints a sanitized summary. The only subprocess is an
  argv-list/no-shell `--version` probe used solely when `--probe` is passed against an
  operator-supplied binary. On this host (no acpx) the CLI completes as a controlled `blocked`
  evidence report (exit 0); it does not error and does not launch.
- `tests/sachima_supervisor/p6b_host_local_dor/**` — TDD unit tests (RED first, then GREEN).

## TDD / verification evidence

- RED first: the new test package was written against the intended API and run before the module
  existed; pytest failed collection with `ModuleNotFoundError: No module named
  'sachima_supervisor.p6b_host_local_dor'` across all 7 test modules.
- GREEN: after implementing the module + CLI, Hermes reran the gates and recorded:
  - `tests/sachima_supervisor/p6b_host_local_dor/` → `48 passed` after the Codex blocker regression fix.
  - Corrected focused gate (`p6b_host_local_dor`, `p6b_read_only_real_agent`,
    `test_activity_controlled_exec.py`, `test_ai_flow_orchestration.py`) → `339 passed`.
  - Full non-Temporal supervisor subset → `813 passed` before the two blocker-regression tests were added.
  - Temporal subset with `uv run --frozen --all-extras` → `53 passed`.
  - Full `tests/sachima_supervisor` with `uv run --frozen --all-extras` → `1012 passed`.
  - `ruff check` on touched Python → `All checks passed!`.
  - `python -m compileall` on touched Python → clean.
  - `git diff --check` → clean.
  - Changed-file allowlist, secret-shaped scan, forbidden live/runtime surface scan → clean.
  - CLI BLOCKED demo wrote sanitized out-of-repo evidence with crash proof pass and launch count 0.
- Verifier correction: direct `uv run --frozen pytest tests/sachima_supervisor -q` failed collection
  because optional `temporalio` was not active. This was classified as an optional-extra environment
  miss, then rerun with `--all-extras`, where the full supervisor suite passed after the blocker fix.
- Codex primary review initially returned `VERDICT: BLOCKERS`: present-but-invalid runner pins
  (`acpx_version="0.9.0"` or malformed `acpx_binary_sha256`) passed when no version probe was
  injected. Hermes added two RED regression tests, confirmed both failed before the fix, then fixed
  `_verify_binary_identity()` to validate the request version and sha pin before the no-probe path.
  Codex blocker-only re-review returned `VERDICT: PASS` / `BLOCKERS: None`; post-review diff hash
  stayed unchanged.
- `python tools/sync_roadmap_status.py --file docs/roadmap/current-status.md --check` →
  `machine status block is up to date` (exit 0). The machine-owned block was not edited by this
  branch; Hermes re-runs the live check before opening the PR.

## Proof result on this host (honest)

```text
crash_no_relaunch:           proven fail-closed (not_found / reattached_no_relaunch, launch count 0, execute not attempted)
runner_pinning:              BLOCKED (no acpx binary / role overlay pinned on this host)
real_execution_readiness:    not proven by this DoR alone
real_smoke:                  remains unapproved and BLOCKED
```

The crash proof addresses blocker **B1** only in its fail-closed Option-B form. The honest
limitation is recorded in every report: without a durable cross-process controlled-exec claim
store, recover-without-relaunch cannot be proven as reattachment to a live run; this DoR proves
only fail-closed no-relaunch recovery. Blocker **B2** now has tooling, but no real runner is
pinned on this host, so the runner-pinning track is a controlled `blocked`.

## Non-approvals preserved

No real agent launch; no real smoke; no real acpx/npx/Claude/Codex step body; no host-local acpx
provisioning beyond a temp `/bin/sh` fake in tests; no durable cross-process claim store; no write
roles; no file/git mutation by an agent step; no network; no Gateway/Feishu/IM/live/public ingress;
no production config; no service restart; no real delivery; no new dependencies; no edits to
WP4/P6-A/P5/controlled-exec/bridge source or committed roles. WP3b active-run cancellation remains
WATCH. Real smoke remains a separate Stage-2 approval.
