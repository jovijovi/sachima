# P6-B Stage-2 DoR provisioning/readiness — user review packet

Date: 2026-06-27
Status: Historical review packet. PR #179 later closed the durable claim-store option; real smoke remains blocked until host-local DoR passes with an operator-supplied pinned runner and a separate real-smoke approval.

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

## Next safe choice after PR #179

PR #179 closed Option A by implementing the durable cross-process claim store. The remaining next safe choice is:

1. Supply an already-available out-of-repo pinned `acpx@0.10.0` binary, create an out-of-repo read-only role overlay and artifact/evidence roots, then run `tools/p6b_host_local_dor.py --probe` for DoR validation only. Installing or fetching `acpx` is not approved by this packet.

Only after host-local DoR passes should Hermes ask for a separate single-run real-smoke approval.
