# Phase D Deterministic Real Local Smoke — User Review Packet

> **For the user (Dog Brother), presented by Hermes.** This packet asks you to approve **only** the readiness gate that is already prepared, and to see the exact, narrower approval that would come *next* if and when you want a real smoke. Approving this packet does **not** run a smoke, start an AGENT, or touch Gateway/Feishu/live/production config. No real smoke has been run.

## 1. One-paragraph summary

Phase C merged a default-off controlled local one-shot exec wrapper (PR #114) but deliberately never ran a real agent. This readiness gate prepares — docs-only — the design for a *future* single deterministic real local smoke: a pinned local `acpx` binary scheme, a prompt materialization scheme, the exact request-construction boundary, the sanitized evidence shape, the replay/no-duplicate-launch proof, rollback, and a full test plan. It executes nothing. It exists so that, when you choose, the next decision is small, well-bounded, and already reviewed.

## 2. What was prepared in this gate (docs-only)

- **PRD** — `...-phase-d-deterministic-real-local-smoke-readiness-prd.md` (Hermes, product/controller).
- **Architecture/readiness packet** — `...-architecture.md` (Claude Code attempted; Codex CLI completed the architecture/docs authoring substitution after Claude hit session-limit / 429; technical design grounded in the merged Phase C code).
- **This user review packet** — `...-user-review-packet.md`.
- **Manifest** — `...-manifest.yaml` (machine-readable scope, blockers, non-approvals, review gates).
- **Dev log** — `docs/dev_log/...-phase-d-deterministic-real-local-smoke-readiness.md`.
- **Roadmap status** — `docs/roadmap/current-status.md` updated minimally to record this gate as prepared/docs-only while keeping execution **BLOCKED**.

## 3. Current recommendation

**Prepare only. Do not execute a Phase D smoke yet.** Three independent provisioning facts each block a real smoke today (verified read-only on this host, 2026-06-12):

| # | Blocker | Evidence |
|---|---|---|
| 1 | No pinned local `acpx` binary | `acpx` not found on PATH; committed role keeps `acpx_binary: null`; provenance gate fails closed |
| 2 | Prompt materialization not implemented | seam request hardcodes `prompt=None`; empty exec prompt fails closed |
| 3 | Supervisor library not installed | `agent_run_supervisor` not importable in any interpreter on this host |

Blocker #3 was newly surfaced by the architecture pass; the earlier baseline listed only #1 and #2. All three must be resolved by an operator, under a separate named approval, before a smoke is even buildable.

## 4. Definition of Ready (must all hold before a smoke is requested)

```text
[ ] verified pinned local acpx binary (absolute path + sha256 + sanitized --version)
[ ] local-only role overlay generated (untracked) with that path; committed config stays null
[ ] agent_run_supervisor library installed and pinned per the repo dependency policy
[ ] prompt materialization fixture/builder landed + approved (deterministic, bounded, no-leak)
[ ] real durable-state preflight record (PR #107) with a held lease + state version
[ ] this packet + a separate named user approval for the smoke
[ ] Codex primary review PASS on the smoke branch; local checks + CI green
[ ] evidence = sanitized only, out of PR payload; no Gateway/Feishu/live/public ingress
```

## 5. Key design decisions you are being asked to endorse

1. **`npx`/network fetch stays forbidden** — a fetch-at-launch runner is not strict-offline, reopens the supply-chain surface the repo dependency policy closed, and is non-deterministic. Only a pinned absolute local path with a recorded `sha256` is allowed.
2. **Committed role JSON stays portable and non-runnable** — the real host `acpx` path lives only in an untracked, local-only role overlay (the Phase C API already supports this via `role_root`). No host-private path enters git or the PR; no production config is written.
3. **Prompt is a small repo-controlled fixture/builder**, bounded and harmless (a read-only "inspect this tiny fixture, return a fixed verdict" prompt). Only its digest reaches durable state; raw text never does.
4. **One supervisor call, one role, sanitized evidence only** — exactly `sachima.codex.primary_reviewer`, read-only, through the existing public boundary, with a replay check proving exactly one launch.

## 6. Residual risks and how they are bounded

| Risk | Bound |
|---|---|
| Host path leak into git | local-only overlay is untracked/`.gitignore`d; committed config stays null; cleanup deletes it |
| Raw prompt/output leak | durable state has no prompt field; `_validate_claim_state_projection` allows only sanitized keys; evidence is sanitized and out of PR |
| Duplicate launch | atomic claim/CAS; replay proof asserts invocation counter == 1 |
| Accidental scope creep (sessions/Gateway/live) | mode allowlist (`exec_controlled` only), single role, explicit non-approvals; no Gateway/delivery surface in the path |
| Supply chain via runner | pinned absolute binary + sha256; `npx`/null fail closed; pinned library per dependency policy |

## 7. Not approved by this packet

```text
real local smoke execution
real AGENT launch
acpx invocation; codex/claude invocation through acpx
npx fallback or network-fetch evidence
persistent sessions; cancellation execution
write-capable Claude or Codex roles
Satine/Hermes-profile ACP execution
controlled AI FLOW execution
Gateway involvement or mutation
Feishu/IM delivery or send API calls
live/default-on behavior; public ingress
production durable runtime code; production config writes
service restarts/reloads; platform adapter mutation
```

## 8. Review gates (AGENT split)

- **Claude Code (architecture/docs):** attempted, then interrupted by session-limit / 429 after partial docs edits.
- **Codex CLI (architecture/docs substitute):** completed this authoring pass under the architecture/docs role. This is docs-only and did not run a smoke, AGENT, `acpx`, Gateway, Feishu/IM, service/runtime, or production config path.
- **Codex CLI (primary review):** PASS — fresh-context review first found two docs blockers; after narrow fixes, blocker-only re-review returned `VERDICT: PASS / BLOCKERS: None`.
- **User (Dog Brother):** pending — after Codex PASS, you decide whether to (a) accept the readiness gate as-is, and separately (b) later approve a real smoke via the text below.

## 9. Proposed next approval text (only when you want a real smoke, after readiness is ready)

```text
批准执行 Phase D deterministic real local smoke：仅在完整 Definition of Ready 已满足后，使用已验证的 pinned local acpx_binary、已安装/固定的 agent_run_supervisor、repo-controlled prompt materialization fixture，运行一次 read-only Codex one-shot smoke；不接入 Gateway/Feishu/live，不写生产配置，不启用持久会话/取消执行/写权限角色/Satine/controlled AI FLOW；输出仅限 sanitized evidence，完成后交我审查。
```

Approving *this* packet is not that approval. The text above is the separate, narrower decision for a later branch, gated by the Definition of Ready in §4.
