# P6-B Stage-2 bounded real-smoke readiness — PRD

Date: 2026-06-27
Status: Docs-only readiness/governance. Real smoke remains unapproved and currently blocked.

## 1. Background and live truth

P6-B Stage-1 merged in PR #171. It added a thin, default-off `P6BReadOnlyRealAgentStepExecutor` bridge over the already-merged `start_controlled_local_exec` wall. The bridge reuses the unmodified WP4 StepExecutor seam, the unmodified P6-A composition session, and the existing null-binary read-only controlled roles. It is non-runnable by default: `enabled` defaults false, approval token defaults empty, `prompt_materializer` and `artifact_sink` default `None`, and committed role files keep `acpx_binary: null`.

This PRD defines the next docs-only Stage-2 readiness/governance packet. It does not execute a real agent, invoke acpx/npx/Claude/Codex as a step body, provision host-local runtime, or approve real smoke.

## 2. Problem

The user wants the first real read-only planning/report step to be reviewed before execution: exact command class, read-only role, evidence sink, and crash/recovery/no-relaunch rules must be pinned and failure modes must be known. Stage-1 proves only the default-off bridge and injected-fake runner gates. It does not prove cross-process crash recovery and it does not pin the host-local runner/role overlay/evidence destination needed for a real smoke.

## 3. Goal

Produce a reviewable readiness package that answers whether a future single bounded read-only planning/report real smoke is ready to request execution approval.

The answer for this revision is:

```text
readiness_packet: PASS_WITH_WATCH
real_smoke_execution_request: BLOCKED
```

Real smoke execution remains blocked until the hard blockers in §7 are closed.

## 4. In scope for this docs-only branch

- Define the exact candidate smoke shape: command class, role, prompt/materializer, artifact sink, evidence layout, max turns/time, and no-write/no-network/no-live expectations.
- Record crash-after-claim / restart / recover-without-relaunch requirements.
- Record blockers and WATCH items from Claude Code architect review.
- Update roadmap/tail/boundary docs so later agents do not confuse readiness with execution approval.
- Prepare a user-facing review packet that asks for the next safe gate, not real smoke execution.

## 5. Explicit non-approvals

This branch approves none of:

```text
real smoke execution
real AGENT launch
real acpx/npx/Claude/Codex step-body invocation
host-local acpx provisioning
operator role overlay provisioning
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

## 6. Candidate first smoke shape to pin later

| Axis | Required later value | Current readiness status |
|---|---|---|
| Command class | Pinned local `acpx` one-shot exec via `agent_run_supervisor`; argv-list/no shell; no package runner or network fetch. | Class understood; exact binary path/version/sha not pinned in repo. |
| Role | Exactly one read-only role such as `sachima.codex.primary_reviewer` or `sachima.claude.read_only_reviewer`; capabilities subset `{read, search}`; adapter pin preserved. | Existing committed roles are null-binary and non-runnable; local overlay still needed. |
| Prompt/materializer | `materialize_p6b_planning_report_prompt`; fixture byte-match; raw prompt injected only after claim and never persisted. | Builder exists; DoR must re-run fixture/digest check. |
| Artifact sink | Caller-supplied out-of-repo sink returning exactly one sanitized `ArtifactRef`; bytes never enter durable state. | Sink not pinned; must be proven before smoke. |
| Evidence root | Out-of-repo timestamped evidence directory under the approved workspace output area. | Not yet selected for this smoke. |
| Bounds | Single workflow, single step, read-only report; max turns and wall time named in approval. | Role has upper bounds, but approval-specific bounds not pinned. |
| Post-run proof | Clean tracked worktree, no file/git/network/live/delivery side effects, no leftover acpx/codex/claude processes, no out-of-scratch writes. | Required but not yet executable. |

## 7. Hard blockers before real-smoke approval

### B1 — Cross-process crash / recover-without-relaunch is unproven

Stage-1 relies on `ControlledLocalExecClaimStore`, which is lock-guarded and in-process. It proves duplicate-start prevention within a resident process, but a real process crash after claim would lose resident claim state. Therefore a real crash-after-claim / restart / recover-without-relaunch proof cannot currently be claimed.

Before any real smoke, one of these must be true:

1. A separately approved durable/cross-process claim-store adapter is implemented and verified; or
2. a host-local DoR proof demonstrates fail-closed restart behavior with no relaunch after a simulated crash-after-claim condition.

Until then, real smoke execution is blocked.

### B2 — Smoke parameters are not pinned

The exact binary path, binary sha256, acpx version, role overlay digest, workflow id, step id, output contract, max turns/time, out-of-repo workdir, evidence root, and sink behavior are not yet pinned. A real-smoke approval phrase cannot be safely honored without those values.

## 8. WATCH items

- WP3b active-run cancellation remains WATCH. P6-B preserves ambiguity and must not claim clean active-run cancellation.
- The prompt currently asks the agent to read a committed fixture while role redaction/read policy may suppress reads. The DoR must resolve this affordance before launch, either by allowing one bounded file read or by passing a host-verified inline projection.
- Once a real role overlay is pinned, the null-binary safety net is intentionally removed. All other gates must be independently reverified.
- The artifact sink is caller-supplied; shape checks are not enough to prove it writes outside the repo. The future run must prove out-of-repo behavior.

## 9. Acceptance criteria for this readiness branch

- Docs-only changed-file allowlist passes.
- Manifest parses and all execution/live/write booleans remain false.
- `current-status.md`, `tail-register.md`, and `boundary-register.md` preserve real-smoke non-approval.
- Claude Code architect/docs review is recorded and labels real smoke BLOCKED.
- Codex primary read-only blocker review passes on the final docs revision or blockers are fixed and re-reviewed.
- Local docs gates pass: `git diff --check`, roadmap sync check before PR opening, stale wording scan, forbidden source/runtime mutation scan.

## 10. Next safe approval after this PR

If this docs-only PR is reviewed and merged, the next safe approval is not real smoke execution. The next safe request is a **host-local DoR / no-relaunch proof** gate that may pin and verify the runner, local role overlay, evidence sink, and crash/recovery behavior without launching a real AGENT step.
