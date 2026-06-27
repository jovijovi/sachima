# P6-B Stage-2 DoR provisioning/readiness packet

Date: 2026-06-27
Status: Docs-only provisioning/readiness packet. Host-local DoR validation with a real pinned `acpx` binary is still blocked on this host because no `acpx` binary is present.

## 1. Purpose

This packet turns the merged P6-B Stage-2 host-local DoR proof into an executable review contract for the next operator step. It fixes the future DoR validation command shape, allowed read-only role overlays, evidence contract, and crash/recovery/no-relaunch interpretation before any real smoke is requested.

It does **not** install `acpx`, invoke `acpx`, run a real agent, run a real smoke, add a write role, touch Gateway/Feishu/live surfaces, write production config, restart services, or perform real delivery.

## 2. Live truth at authoring time

```text
release/sachima local head == sachima/release/sachima
open PRs: 0
acpx on PATH: NOT_FOUND
codex CLI: available locally, but not enough without a pinned local acpx binary
Claude Code CLI: available locally, but not enough without a pinned local acpx binary
```

The authoring run executed only the repo's DoR assessment CLI without runner parameters. It wrote sanitized out-of-repo evidence and returned:

```text
status: blocked
runner_pinning_status: blocked
crash_proof_status: pass
blockers: [p6b_dor_runner_params_missing]
supervisor_launch_count: 0
execute_after_store_loss: not_approved_not_attempted
```

Evidence reference class: `p6b-stage2-dor-provisioning-readiness/20260627T093824Z/`.

## 3. Scope boundary

Allowed by this packet:

- docs/status/manifest updates;
- local read-only inspection of existing code, tests, and docs;
- running `tools/p6b_host_local_dor.py` **without** runner parameters to produce a controlled `blocked` report;
- future operator-controlled version probe of a pinned local `acpx` binary via argv-list/no-shell `--version`, but only after a separate approval supplies the binary, role overlay, artifact sink, and evidence root.

Still not approved:

```text
real smoke execution
real AGENT launch
real acpx/npx/Claude/Codex step-body invocation
installing or fetching acpx/npm/npx packages
write-capable roles
file writes or git mutation by the agent step
network access by the agent step
Gateway / Feishu / IM / live / public ingress
production config writes
service restart/reload
real delivery
broader controlled AI FLOW expansion
clean active-run cancellation claims beyond the existing WP3b WATCH
```

## 4. Future DoR validation command contract

The future host-local DoR validation command must be generated from an operator packet, not typed ad hoc. The shape is:

```text
uv run --frozen --all-extras python tools/p6b_host_local_dor.py   --enabled   --approval-token <exact P6-B host-local DoR approval token>   --repo-root <current sachima worktree>   --role-key <sachima.codex.primary_reviewer | sachima.claude.read_only_reviewer>   --role-overlay-path <out-of-repo role overlay JSON>   --role-overlay-digest sha256:<64 hex>   --acpx-binary <absolute out-of-repo pinned local acpx path>   --acpx-version 0.10.0   --acpx-binary-sha256 sha256:<64 hex>   --evidence-root <out-of-repo evidence root>   --artifact-sink-root <out-of-repo artifact sink root>   --probe
```

Validation rules:

- `--probe` may only run `[acpx_binary, "--version"]` with `shell=False`, bounded output, no package runner, and no network/fetch path.
- `acpx_binary` must be an absolute local path outside the repo, no whitespace, and its basename must not be a launcher such as `npx`, `npm`, `pnpm`, `yarn`, `bun`, `bunx`, `node`, `sh`, `bash`, or `env`.
- `acpx_version` must be exactly `0.10.0`.
- `acpx_binary_sha256` must match the probed binary digest.
- `role_overlay_path`, `evidence_root`, and `artifact_sink_root` must all resolve outside the repo.
- The command writes only sanitized DoR evidence; it must not call the real P6-B step executor as a smoke run.

## 5. Role overlay contract

The only role keys allowed for this DoR validation are:

| Role key | Adapter | Intended use |
|---|---|---|
| `sachima.codex.primary_reviewer` | `codex` | Preferred first P6-B read-only planning/report smoke candidate, because local Codex CLI is present. |
| `sachima.claude.read_only_reviewer` | `claude` | Alternate read-only candidate if the operator chooses Claude Code. |

The committed role configs stay portable and non-runnable (`acpx_binary: null`). The local overlay must be an out-of-repo JSON copy derived from one committed role config with only host-local runner fields filled.

Required overlay invariants:

```text
schema_version: 1
role_id: exact role key
runner.type: acpx
runner.acpx_version: 0.10.0
runner.adapter_agent: exact adapter for the role
runner.acpx_binary: absolute pinned local acpx path
permissions.read: true
permissions.search: true
permissions.write/execute/terminal/delete/move/fetch/switch_mode/other: false
session.strategy: exec
redaction.redact_prompt/stderr/metadata/env: true
```

Any overlay that enables write/execute/fetch/terminal-like capabilities, changes adapter, uses the wrong acpx version, or declares a different binary than the request must fail closed.

## 6. Evidence contract

The DoR evidence bundle may contain only:

- report type and schema version;
- status codes and stable blocker codes;
- role key, adapter, role overlay digest;
- binary version and sha256 digest;
- path digests, not raw local paths;
- crash proof states/counts;
- evidence/artifact sink outside-repo booleans;
- redaction/no-leak scan result.

It must not contain raw prompt text, raw model output, raw host paths, platform IDs, cards, media paths, tokens, environment variables, stdout/stderr walls, or raw exception text.

## 7. Crash/recovery/no-relaunch interpretation

The merged PR #175 proof and the blocked authoring run both prove the same narrow property:

```text
fresh empty in-process claim store after simulated restart
query_state: not_found
recover_state: not_found
recovery_marker: reattached_no_relaunch
supervisor_launch_count: 0
execute_after_store_loss: not_approved_not_attempted
```

This is a fail-closed no-relaunch proof, not reattachment to a live run. Without an Option-A durable cross-process claim store, recover-without-relaunch cannot honestly be called reattachment after a real process crash. A future real smoke may proceed only after either:

1. Option A implements and verifies the durable cross-process claim store; or
2. Option B runs this host-local DoR validation against an operator-supplied pinned `acpx` + role overlay + sink/evidence packet and still preserves a separate real-smoke approval gate.

## 8. Current outcome

```text
DoR provisioning/readiness packet: PASS_WITH_WATCH
Host-local DoR validation with real pinned acpx: BLOCKED_NO_ACPX
Real smoke execution request: BLOCKED / DO NOT REQUEST YET
```

## 9. Next safe approval after this packet

The next safe approval is still **not** real smoke. It is one of:

```text
Option A:
  approve implementation of a durable cross-process claim store for P6-B crash/recover/no-relaunch proof

Option B:
  approve an operator-supplied out-of-repo pinned acpx binary + read-only role overlay + artifact sink + evidence root,
  then run tools/p6b_host_local_dor.py --probe for DoR validation only,
  with no real agent step launch and no real smoke
```

A later real-smoke approval must name the exact binary digest, role key, adapter, workflow/step refs, output contract, max turns/time, workdir/evidence/sink refs, and no-write/no-live boundaries.
