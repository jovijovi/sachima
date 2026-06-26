# P6-B Stage-2 bounded real-smoke readiness — Claude Code architect review

Date: 2026-06-27
Role: Claude Code architect + documentation engineer
Mode: read-only inspection via safe-mode; tools limited to read/search/glob; Claude made no edits, ran no shell/test/service commands, launched no agent, and approved no smoke.
Worktree mutation check: Hermes separately ran pre/post git status and diff-hash verification around the Claude read-only review; the report was generated outside the repo first.

I now have a complete, verified picture of the P6-B Stage-1 implementation, the governance packets, the inner controlled-exec walls, and the committed role posture. Here is the readiness review.

---

# P6-B Stage-2 Readiness / Governance — Teach-back & Architecture Critique

**Role:** ARCHITECT + DOCUMENTATION ENGINEER · **Mode:** read-only inspection · **Repo:** `…/worktrees/sachima/p6b-stage2-readiness-governance` · branch `docs/p6b-stage2-readiness-governance`

## 1. VERDICT

**PASS_WITH_WATCH** for authoring the docs-only Stage-2 readiness/governance packet on this branch — it is the explicit "next allowed request" in `current-status.md`, and Stage-1 (PR #171) is a clean, default-off, fail-closed bridge.

**The real smoke itself is BLOCKED and I do not approve it.** There is one hard architectural prerequisite (cross-process crash / recover-without-relaunch is **not demonstrable** with the in-process claim store) plus a set of must-name-exactly parameters that are not yet pinned. Treat "ship the readiness packet" and "run the smoke" as two different decisions; this verdict greenlights only the former.

## 2. Teach-back — what Stage-2 readiness IS and IS NOT

**What Stage-1 already merged (PR #171) — the thing Stage-2 governs:** a thin, default-off `StepExecutor` *bridge* (`sachima_supervisor/p6b_read_only_real_agent.py`) that adapts the already-merged one-shot `start_controlled_local_exec` into the unmodified WP4 step seam, injectable into the unmodified P6-A session. It builds **no** new runner, claim store, provenance gate, or prompt machine. It is non-runnable by construction: `enabled` defaults `False`, `approval_token` defaults `""`, `prompt_materializer`/`artifact_sink` default `None` (each ⇒ fail closed), and the two committed reused roles carry `acpx_binary: null` (provenance wall fails closed). Tests exercise an **injected fake** runner only.

**Stage-2 readiness IS:**
- A docs-only "审死" (death-review) of *one* bounded real read-only planning/report step before any execution.
- A Definition-of-Ready: exact command/role/provenance/prompt/materializer/artifact-sink preflight, crash/recover/no-relaunch rules, kill criteria, evidence layout, and the precise later approval phrase.
- Roadmap/tail/boundary updates that keep the smoke classified `NEXT_PHASE` and unapproved.

**Stage-2 readiness IS NOT:**
- Not the smoke. Not approval to launch acpx/agent/npx, not enabling the flag, not pinning a real binary, not wiring a real supervisor.
- Not source change: this branch must stay docs/status-only (no edits to the bridge, WP4/P6-A/P5, controlled-exec, or role files).
- Not a write/live/delivery widening: no Gateway/Feishu/IM/network/production config/real delivery, no service restart, no broader controlled-AI-FLOW expansion, no clean active-run cancellation claim (WP3b stays WATCH).

## 3. Exact real-smoke candidate shape (for the packet to pin — not to run)

| Axis | Value found in code/docs | Status for DoR |
|---|---|---|
| **Command class** | Pinned local `acpx` one-shot `exec`, single read-only turn, driven via `agent_run_supervisor` argv API (lazy import). No shell/`subprocess`/`os.system`, no `npx/npm/node/bunx/...` (`FORBIDDEN_RUNNER_BASENAMES`), no network fetch. | Must name absolute `acpx_binary` path + sha256 + version `0.10.0`. Committed role is `null` ⇒ operator overlay required. |
| **Role key / capabilities** | `sachima.claude.read_only_reviewer` (adapter `claude`) or `sachima.codex.primary_reviewer` (adapter `codex`); capabilities exactly `("read","search")`; perms read/search `true`, write/execute/terminal/delete/move/fetch/switch_mode/other all `false`; `session.strategy="exec"`. Double wall: bridge `_read_only_rejection` + controlled-exec `_check_role_capability` (adapter pin). | Pin one role key + adapter. Must be in `CONTROLLED_EXEC_ROLE_ALLOWLIST`, not in `CONTROLLED_EXEC_FUTURE_ROLE_KEYS`. |
| **Prompt / materializer** | `materialize_p6b_planning_report_prompt` — deterministic, repo-controlled, ≤2000 chars, re-screened each build, byte-mirrored by `tests/fixtures/.../p6b_planning_report_prompt.v1.txt`. Durable state carries only ref `p6b_planning_report_prompt_v1` + sha256; raw text injected post-claim only. | Confirm fixture↔builder byte-match at exact head. |
| **Artifact sink** | Caller-supplied, **out-of-repo** claim-checker returning **exactly one** sanitized `ArtifactRef` (6 keys: `artifact_id`, `producer_step_id`=step_id, `content_digest`, `artifact_kind`=output_contract, `byte_count`≤cap, `created_at_ref`). Bytes never persisted; `None` ⇒ fail closed. | Sink is injected, not committed — its out-of-repo + one-ref discipline must be proven in the run. |
| **Evidence directory** | Out-of-repo, outside `_REPO_ROOT` (`_require_offline_dir`); work_dir + evidence both out-of-repo. Prior smokes used timestamped `/data/agents/workspace/hermes/outputs/sachima/<slice>/<UTC>/`. | Name exact out-of-repo workdir + evidence root. |
| **Max turns / time** | Role limits `timeout_seconds: 900`, `max_turns: 8`; workflow bounds `max_steps:1`, `max_runtime_seconds:900`, `max_artifact_bytes:65536`. | Stage-2 phrase must name exact max turns + max wall-seconds. |
| **No-write / no-network / no-live** | Read-only role (all mutate perms false); no shell; provenance blocks launcher/fetch basenames; bridge boundary scan forbids Gateway/Feishu/lark/platform/`temporalio`. | Post-run proof required: clean `git status`, zero out-of-scratch writes, no network egress, no leftover acpx/codex processes. |

## 4. Crash / recovery / no-relaunch rules that MUST be satisfied before execution approval

1. **WP4 CAS claim is authoritative**, recorded *before* `executor.execute`. Identical replay (same idempotency key + fingerprint) ⇒ `disposition=="replayed"` ⇒ **executor never called** (no relaunch).
2. **Inner second wall**: `ControlledLocalExecClaimStore.claim` is an atomic check-and-set written *before* the supervisor boundary (`activity_controlled_exec.py:495`, used at `:1227`). Replay returns resident; divergent fingerprint ⇒ `activity_idempotency_conflict`; same activity / different key ⇒ `activity_claim_conflict`. A crashed in-progress claim is **never auto-relaunched** (`:1233`).
3. **Deterministic reattach id**: bridge derives `p6b_exec_<48hex>` + `p6b_idem_<…>_<attempt>` from sanitized run/step refs, so a crash between claim and finalize reattaches by id. `recover()` reads resident state only and stamps `reattached_no_relaunch`; it **never** re-invokes `step_workflow_run`.
4. **Lease / epoch / state-version binding** via `_check_preflight_binding` *before* launch: stale epoch ⇒ `activity_stale_state`, lost lease ⇒ `activity_lease_lost`, drifted version ⇒ `activity_toctou_conflict`.
5. **Active-run cancellation stays WATCH**: `cancel()` returns `ACTIVE_RUN_CANCELLATION_WATCH` / `cancel_ambiguous` even when handed a confirmed-looking `interrupt_outcome` (verified in `test_control_path_watch.py::test_confirmed_external_interrupt_still_preserves_watch`). No clean `cancelled` is ever claimed.

**⛔ The blocker inside this list:** rule 2/3 are only provable **in-process today**. `ControlledLocalExecClaimStore` is a lock-guarded in-memory dict; its own docstring says "a transactional durable (cross-process) store adapter is a later, separately approved gate" (`:455-467`). On a *real* crash-after-claim + process restart, the resident claim is gone ⇒ `query`/`recover` return `not_found` ⇒ no durable evidence the claim survived, so "recover-without-relaunch across a crash" cannot be demonstrated. The manifest records this honestly: `cross_process_crash_no_relaunch_proof_required_before_real_smoke: open`. **Before execution approval, Stage-2 must either (a) attach a durable cross-process claim store (the P5 `p5wf_<48hex>` durable path — new code needing its own implementation gate, NOT in scope here), or (b) prove crash-after-claim FAILS CLOSED (no relaunch) on restart with concrete evidence.** Until one is shown, the real smoke must remain fake-only.

## 5. Required docs / manifest / dev-log / status artifacts to write in this branch

Mirror the established governance-packet shape (PR #170 predev, PR #155 Temporal PR B). All **docs/status-only**; changed-file allowlist must reduce to `docs/` (+ machine status block). No source/role/test edits on this branch.

1. **Stage-2 readiness PRD** — `docs/plans/2026-06-27-…-p6b-stage2-bounded-real-smoke-readiness-prd.md`: scope, the §3 axis table fully pinned, DoR, kill criteria, scoring, explicit non-approvals.
2. **No-code technical "审死" / readiness packet** — the section-4 crash/no-relaunch decision spelled out: durable-store-vs-fail-closed-proof choice, evidence layout, three-surface no-leak + canary expectation, and the exact Stage-2 approval phrase.
3. **Readiness manifest YAML** — `…-readiness-manifest.yaml` with all-false non-approval booleans, `open_tails` (cross-process no-relaunch; WP3b WATCH), and the DoR gate list; `stage_2_real_smoke: not_approved`.
4. **Dev log** — record this teach-back + critique, worker provenance, non-approvals preserved, and that no execution/agent/launch occurred.
5. **`docs/roadmap/current-status.md`** — keep `ROADMAP-NEXT-ARS-P6B-STAGE2-REAL-SMOKE` open; note the readiness packet exists; state next allowed request; do **not** mark smoke approved. (Machine block is git/GitHub evidence only.)
6. **`docs/roadmap/tail-register.md`** — sharpen `ROADMAP-NEXT-ARS-P6B-STAGE2-REAL-SMOKE`; add/cross-link the cross-process crash/no-relaunch sub-tail as the gating prerequisite.
7. **`docs/roadmap/boundary-register.md`** — preserve the `p6b_stage2_real_smoke…` non-approval; add the explicit boundary "in-process claim store ⇒ no cross-process no-relaunch proof yet."
8. **Independent Codex blocker review** of the packet at live PR head, and `tools/sync_roadmap_status.py --check` — both owned by the human/Hermes pipeline, not by me.

## 6. Blockers / WATCH items

**BLOCKERS (must clear before any real-smoke approval):**
- **B1 — Cross-process no-relaunch unproven.** In-process claim store can't survive a real crash; durable adapter or fail-closed-on-restart proof required (§4). Hard gate.
- **B2 — Smoke parameters not pinned.** Committed role is null-binary; `runner`/`materializer`/`sink`/`invoke_supervisor` default to None/null. The exact binary sha/path/version, role+adapter, workflow+step+`output_contract`, max turns/wall-time, and out-of-repo workdir+evidence are all unspecified. No approval phrase can be honored until named.

**WATCH:**
- **W1 — Last-wall thinning at arm time.** Once `enabled`+token+materializer+sink+a *real* pinned role are wired, `start_controlled_local_exec` defaults `invoke_supervisor=None` → the **real** `invoke_local_offline_supervisor` seam (`:1259`). So during the smoke the "non-runnable" null-binary safety net is deliberately removed; every *other* wall (token, read-only double-check, provenance sha, preflight/lease binding, prompt screen, output claim-check, crash/no-relaunch) must be independently re-verified at DoR — none may be load-bearing-by-accident.
- **W2 — Prompt affordance vs. read suppression.** The prompt tells the agent to *read* `controlled_local_activity_dry_run_evidence.v1.json`, but the role sets `redaction.suppress_reads: true`. Phase D smoke #1 returned BLOCKERS for exactly this contradiction and was fixed by passing a host-verified inline JSON projection. DoR must resolve read-affordance vs. enforcement before running.
- **W3 — `allowed_roots_security_boundary: false`** in both committed roles, with `allowed_roots: ["/workspace/sachima"]`. The operator overlay must repoint workdir/allowed_roots to an out-of-repo scratch and prove no write escaped; the `false` flag means containment leans on the supervisor sandbox, not the role.
- **W4 — Injected sink trust.** The artifact sink is caller-supplied and out-of-band; the bridge enforces shape (exactly one ref, byte cap, leak scan) but not the sink's out-of-repo behavior — prove it in the run.
- **W5 — Stage-1 evidence is Hermes-attested**, not reproduced by the authoring agent (manifest: "Claude Code could not run commands; Hermes ran gates"). Fine for docs-only; the smoke DoR should re-run the full local gate set at exact head before execution.
- **W6 — WP3b active-run cancellation** stays open; P6-B preserves, does not close it. Do not pivot to agentic-ui; FlowWeaver roadmap continuity preserved.

## 7. Suggested later approval-request wording (NOT an approval — for the user to issue when DoR is green)

> I am not requesting or granting this now. Offer it to the user only after B1 and B2 are closed.

Present it to the user as: *"When you are ready, and only after the readiness DoR is green (cross-process crash/recover-without-relaunch proven or fail-closed-demonstrated; runner/role/sink/evidence pinned), you can authorize the single bounded smoke with a phrase like:"*

```
approve_agent_run_supervisor_sachima_p6b_bounded_read_only_real_agent_step_real_smoke_single_run_pinned_local_acpx_<binary_sha256>_role_<role_key>_adapter_<claude|codex>_workflow_<wf_id>_step_<step_id>_output_contract_<contract>_max_turns_<n>_max_seconds_<t>_out_of_repo_workdir_<path>_evidence_<path>_no_write_no_git_no_network_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery_after_crash_no_relaunch_proof
```

Accompany it with the plain-language preconditions the user is affirming: one run only; pinned local acpx (no npx/network); read-only role; out-of-repo workdir + evidence; no file/git/network/delivery, with post-run proof (clean `git status`, no out-of-scratch writes, no leftover acpx/codex processes); WP3b active-run cancellation remains WATCH; and the smoke confers **no** Gateway/Feishu/live/production/write/multi-step/persistent-session/real-cancellation scope.

---

**Read-only review complete.** Claude edited no files, ran no shell/test/service commands, launched no agents, and approved no smoke; Hermes separately ran status/diff verification around the review. All Stage-1 non-approvals and the WP3b WATCH remain intact; the single hard prerequisite for any future smoke is the cross-process crash / recover-without-relaunch proof (B1).
