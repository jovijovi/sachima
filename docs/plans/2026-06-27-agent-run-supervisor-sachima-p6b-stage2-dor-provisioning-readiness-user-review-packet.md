# P6-B Stage-2 DoR provisioning/readiness — user review packet

Date: 2026-06-27
Status: Historical review packet. PR #179 later closed the durable claim-store option, and PR #181 later fixed the bounded real-smoke blockers and recorded the approved single-run read-only PASS.

## Verdict

```text
provisioning/readiness packet: PASS_WITH_WATCH
historical authoring-time host-local DoR validation: BLOCKED_NO_ACPX
later approved bounded read-only real smoke after PR #181: PASS
```

## What this packet does

It turns the merged PR #175 host-local DoR proof into an operator-ready validation contract:

- exact future DoR command shape;
- allowed read-only role keys and overlay invariants;
- out-of-repo evidence/artifact sink contract;
- crash/recovery/no-relaunch interpretation;
- explicit next approval choices.

At authoring time, it recorded the then-live blocker that this host had no `acpx` binary. That authoring-time blocker was later superseded by the PR #181 bounded read-only smoke PASS using pinned `acpx@0.10.0` evidence.

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

## Historical next safe choice after PR #179

PR #179 closed Option A by implementing the durable cross-process claim store. At that point the remaining safe choice was an operator-supplied pinned `acpx@0.10.0` packet plus DoR validation before any real smoke.

That later happened outside this historical packet: after the prerequisite fixes and separate approval, PR #181 records the bounded single-run read-only real-smoke PASS. The current next safe gate is now a docs-only runtime lifecycle / controlled attach plan; further real execution remains separately gated.
