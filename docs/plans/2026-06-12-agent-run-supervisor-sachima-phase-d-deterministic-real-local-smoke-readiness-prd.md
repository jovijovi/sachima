# agent-run-supervisor × Sachima Phase D — Deterministic Real Local Smoke Readiness PRD

> **Status:** readiness gate only. This document prepares the next decision for a deterministic real local smoke. It does **not** approve or execute the smoke, start any real AGENT, invoke `acpx`, touch Gateway/Feishu/live delivery, or write production configuration.

## Approval captured for this readiness gate

User approval, 2026-06-12:

```text
批准准备 Phase D deterministic real local smoke readiness gate：先完成 pinned local acpx_binary 方案、prompt materialization 方案、Phase D PRD/评审包与风险边界；不执行真实 smoke，不启动真实 AGENT，不接入 Gateway/Feishu/live，不写生产配置。遵循 AGENT 分工：Hermes 总控，Claude Code 架构/文档，Codex 主审，完成后交我批准。若 Claude Code 因配额不足报错，则由 Codex CLI 顶上。
```

Execution-role note: Claude Code began the architecture/documentation pass but hit a session-limit / 429 error after partial docs edits. Codex CLI is substituting for that **architecture/docs authoring role** in this pass. That substitution is separate from, and does not satisfy, the later fresh-context Codex primary review gate.

## Current baseline

Phase C merged a controlled local one-shot exec wrapper in PR #114. The wrapper is local/offline, default-off, and guarded by pinned-local-acpx provenance, read-only Codex role capability checks, durable-state preflight binding, operator gate, and atomic pre-launch claim/CAS. Phase C deliberately did **not** run a real local smoke because:

1. this host has no pinned local `acpx` executable;
2. the committed role config truthfully keeps `runner.acpx_binary: null` and therefore fails closed;
3. prompt materialization is deliberately not implemented in the Phase C wrapper, so `_build_local_offline_request(...)` passes `prompt=None` and claim-check refs only;
4. the `agent_run_supervisor` Python library is not installed on this host, so the real seam would fail closed with `supervisor_library_unavailable`;
5. `npx` fallback is forbidden for strict-offline evidence.

Fresh preflight for this readiness gate confirmed:

```text
acpx: not found on PATH
codex: available
claude: available
CodeGraph: initialized in the Phase D readiness worktree
agent_run_supervisor: not importable in candidate interpreters
open PRs against release/sachima: none before this branch
```

## Product goal

Define the minimum safe path to a later deterministic local smoke proving that Sachima can request exactly one read-only Codex one-shot execution through the controlled local exec wrapper, using a pinned local `acpx_binary` and deterministic prompt materialization, with sanitized evidence only.

## In scope for this readiness gate

This PRD/plan may define:

- pinned local `acpx_binary` provisioning and verification requirements;
- local-only role overlay strategy for a later smoke branch;
- prompt materialization requirements and allowed source shape;
- deterministic smoke scenario and expected sanitized evidence shape;
- pre-launch, in-progress, terminal, and replay behavior that must be observed;
- no-leak, no-network-fetch, and forbidden-surface checks;
- review, CI, and user-approval gates for a later smoke execution;
- exact approval text for the next phase.

## Out of scope / explicit non-approvals

This readiness gate does **not** approve:

```text
real local smoke execution
real AGENT process launch
acpx invocation
codex/claude invocation through acpx
npx fallback or network-fetch evidence
persistent sessions
cancellation execution
write-capable Claude or Codex roles
Satine or Hermes-profile ACP execution
controlled AI FLOW execution
Gateway involvement or mutation
Feishu/IM delivery or send API calls
live/default-on behavior
public ingress
production durable runtime code implementation
production config writes
service restarts or reloads
platform adapter mutation
```

## Pinned local acpx_binary readiness scheme

A later smoke may proceed only if an operator supplies a local executable path that passes all checks below **before** the smoke branch changes any role file or invokes any supervisor path.

Required checks:

1. **Path shape:** absolute path; no whitespace; not `npx`, `npm`, `pnpm`, `yarn`, `bunx`, shell, or wrapper that fetches from the network by default.
2. **Executable proof:** file exists and is executable.
3. **Version/provenance proof:** command supports a deterministic version/provenance probe such as `acpx --version`; the output is captured as sanitized text without tokens or user-private data.
4. **No-fetch proof:** the smoke plan records why this executable does not fetch at invocation time. If that cannot be proven, the smoke stays blocked.
5. **Role-file binding:** an untracked local-only role overlay carries the exact local path, and the controlled exec request carries the exact sha256 of that overlay role file.
6. **Committed config stays non-runnable:** `sachima_supervisor/roles/codex_primary_reviewer_exec_controlled_v1.json` remains portable with `acpx_binary: null`; host-local paths do not enter git or production config.
7. **Rollback:** after the smoke evidence is captured, delete the untracked overlay. The committed role JSON must remain portable and non-runnable unless a later, separate portable binary provision model is approved.

## Prompt materialization readiness scheme

Phase C intentionally passes `prompt=None`; Phase D needs a minimal deterministic prompt materialization gate before any real run.

Allowed materialization model for the later smoke:

- Source is a small repo-controlled fixture or deterministic builder, not raw IM text, card JSON, media bytes, tool output, or Gateway payload.
- Prompt content is read-only and harmless, e.g. asks the Codex adapter to inspect a tiny repo fixture and return a fixed, non-secret summary.
- The materialized prompt is bounded in length and must not include credentials, platform ids, callback URLs, raw user text, private local paths, or environment dumps.
- The materialized prompt digest is recorded in sanitized evidence; raw prompt text is not stored in durable state unless the next phase explicitly approves a fixture file as source evidence.
- The request carries only `prompt_ref` / digest-safe claim-check refs before the pre-launch claim. Raw prompt materialization should occur in a materialization-aware seam request builder after an acquired claim and before `invoke_local_offline_supervisor(...)`, unless a future implementation explicitly changes that construction boundary and proves no unsafe raw material enters durable state.

## Later smoke scenario sketch

A separately approved Phase D execution branch should use the smallest deterministic scenario:

1. Build or load a safe prompt fixture ref/digest; raw prompt text is materialized only at the seam request construction point.
2. Verify pinned local `acpx_binary` and role-file digest.
3. Create a request for `sachima.codex.primary_reviewer` only.
4. Bind request to an existing durable-state preflight record and prior controlled dry-run evidence digest.
5. Acquire the atomic pre-launch claim before invoking the supervisor boundary.
6. Invoke the local/offline supervisor once.
7. Record sanitized result state only: status, stable error/success code, artifact ref count, evidence ref digest, business verdict `null`, no raw stdout/stderr/tool output.
8. Replay the identical idempotency key and prove it does not relaunch.

## Acceptance criteria for this readiness gate

This readiness gate is complete when:

- this PRD exists in the repo;
- an architecture/readiness packet defines pinned `acpx_binary` and prompt materialization gates;
- a user review packet states exact approval text and non-approvals;
- `docs/roadmap/current-status.md` records that the readiness gate is prepared but real smoke remains unapproved;
- Claude Code performs architecture/documentation work, unless unavailable due quota/usage failure;
- if Claude is unavailable, Codex substitution is explicitly recorded and a separate fresh-context Codex review still happens;
- Codex primary review returns `PASS` with no blockers;
- local deterministic checks and CI pass;
- no real smoke or real AGENT launch occurs.

## Recommended next approval text after this readiness PR

If this readiness gate passes and the full Definition of Ready is satisfied — including a verified pinned local `acpx` executable, installed/pinned `agent_run_supervisor`, landed/approved prompt materialization, and fresh review/CI — the next approval should be narrower than live rollout:

```text
批准执行 Phase D deterministic real local smoke：仅在完整 Definition of Ready 已满足后，使用已验证的 pinned local acpx_binary、已安装/固定的 agent_run_supervisor、repo-controlled prompt materialization fixture，运行一次 read-only Codex one-shot smoke；不接入 Gateway/Feishu/live，不写生产配置，不启用持久会话/取消执行/写权限角色/Satine/controlled AI FLOW；输出仅限 sanitized evidence，完成后交我审查。
```
