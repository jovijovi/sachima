# Phase D Deterministic Real Local Smoke — Dev Log

## 2026-06-12 — Host-local DoR and first real smoke attempt

After PR #119 and the follow-up status closures merged, the user separately approved host-local Phase D provisioning / Definition-of-Ready verification and then a real deterministic local smoke.

Host-local DoR evidence is stored outside the repo:

```text
/home/ubuntu/workspace/hermes/outputs/sachima/phase-d-smoke-host-provisioning-dor/host_local_dor_verification.json
```

The first real smoke attempt used a pinned local `acpx@0.10.0`, an untracked local-only role overlay, and an installed/pinned `agent_run_supervisor`. The execution pipeline completed, but the business task returned:

```text
VERDICT: BLOCKERS
```

Reason: the prompt asked Codex to read a committed JSON fixture while also forbidding commands, fetching, and the available file-reading mechanisms. That was a prompt-affordance contradiction, not an infrastructure failure.

No Gateway, Feishu/IM, live/public ingress, production config, persistent session, write-capable role, Satine/Hermes-profile ACP, or real delivery surface was touched.

## 2026-06-12 — Prompt-affordance repair and second real smoke PASS

The prompt was narrowed so Codex only validated an inline JSON projection. The host side separately verified that the projection came from the committed fixture:

```text
tests/fixtures/sachima_supervisor/controlled_local_activity_dry_run_evidence.v1.json
```

Second smoke result:

```text
execution_pipeline: PASS
business_task: VERDICT: PASS
```

Key evidence:

```text
summary: /home/ubuntu/workspace/hermes/outputs/sachima/phase-d-real-local-smoke/phase_d_smoke_v2_20260612165247_summary.json
post_verify: /home/ubuntu/workspace/hermes/outputs/sachima/phase-d-real-local-smoke/phase_d_smoke_v2_20260612165247_post_verify.json
final_validation: /home/ubuntu/workspace/hermes/outputs/sachima/phase-d-real-local-smoke/phase_d_smoke_v2_20260612165247_final_validation.json
run_dir: /home/ubuntu/workspace/hermes/outputs/sachima/phase-d-real-local-smoke/.agent-run-supervisor/runs/run_20260612T165247Z_638d9279
```

Verified properties:

- pinned local `acpx@0.10.0` was used;
- `contains_exec=true`, `contains_no_terminal=true`, `contains_npx=false`;
- `new_run_count=1` and `replay_created_extra_run=false`;
- `agent_run_supervisor` status was `completed`;
- Codex returned `VERDICT: PASS`;
- worktree ended clean after archiving the run artifacts outside the repo;
- no leftover `acpx` / `codex` processes remained;
- `pytest -q tests/sachima_supervisor` returned `325 passed in 2.00s`;
- `python3 -m compileall -q sachima_supervisor tests/sachima_supervisor` passed;
- `git diff --check` passed;
- CodeGraph status remained healthy.

This is a single local read-only smoke proof only. It does not approve additional real local smoke runs, persistent sessions, cancellation execution, write-capable roles, Satine/Hermes-profile ACP, controlled AI FLOW execution, Gateway/Feishu/live/public ingress, production config writes, service restarts, platform adapter mutation, or real delivery.
