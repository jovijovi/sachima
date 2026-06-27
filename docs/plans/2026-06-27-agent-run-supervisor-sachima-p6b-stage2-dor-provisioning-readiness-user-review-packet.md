# P6-B Stage-2 DoR provisioning/readiness — user review packet

Date: 2026-06-27
Status: Ready for docs/status PR review. Real smoke remains blocked.

## Verdict

```text
provisioning/readiness packet: PASS_WITH_WATCH
host-local DoR validation with real pinned acpx: BLOCKED_NO_ACPX
real smoke execution approval: DO NOT REQUEST YET / BLOCKED
```

## What this packet does

It turns the merged PR #175 host-local DoR proof into an operator-ready validation contract:

- exact future DoR command shape;
- allowed read-only role keys and overlay invariants;
- out-of-repo evidence/artifact sink contract;
- crash/recovery/no-relaunch interpretation;
- explicit next approval choices.

It also records the live blocker: this host currently has no `acpx` binary, so a real pinned-acpx DoR validation cannot run yet.

## What this packet does not do

No `acpx` install, no `acpx` invocation, no `npx`, no real agent step, no real smoke, no write role, no file/git mutation by an agent step, no Gateway/Feishu/live behavior, no production config, no service restart, and no real delivery.

## Evidence already produced

A blocked DoR assessment was run with no runner parameters. It returned:

```text
status: blocked
runner_pinning_status: blocked
crash_proof_status: pass
blocker: p6b_dor_runner_params_missing
supervisor_launch_count: 0
```

That proves the current tooling still fails closed and does not launch when the runner packet is missing.

## Next safe choices after merge

Choose one — not both by accident:

1. **Option A:** implement a durable cross-process claim store for stronger crash/recover/no-relaunch semantics.
2. **Option B:** supply an already-available out-of-repo pinned `acpx@0.10.0` binary, create an out-of-repo read-only role overlay and artifact/evidence roots, then run `tools/p6b_host_local_dor.py --probe` for DoR validation only. Installing or fetching `acpx` is not approved by this packet.

Only after one path passes should Hermes ask for a separate single-run real-smoke approval.
