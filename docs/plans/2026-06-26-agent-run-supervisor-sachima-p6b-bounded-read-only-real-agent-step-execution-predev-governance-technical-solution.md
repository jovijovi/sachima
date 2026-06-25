# P6-B bounded read-only real-agent step execution — No-code technical solution

## 0. Status and non-approval boundary

Docs-only. No code, no runtime, no real agent, no `acpx`/`npx`/Claude/Codex launch, no Temporal service/Worker start, no Gateway/Feishu/platform/delivery, no production config, no service restart, no real smoke. Everything below proposes a **later, separately approved** P6-B implementation PR. Digests are evidence, not trust. WP3b active-run cancellation stays WATCH. Gateway/Feishu/platform/delivery/production stay closed.

## 1. Architecture verdict

**Sufficient — build P6-B as a thin, default-off *bridge* `StepExecutor` that adapts the already-merged one-shot controlled exec (`start_controlled_local_exec`) into the unmodified WP4 seam, injected into the unmodified P6-A `P6ControlledAiFlowSession`. Do not build a new runner, a new provenance gate, a new claim store, a new prompt machine, or modify WP4/P6-A/P5.**

Rationale: every hard wall already exists and is proven (some real-smoked under WP1b):

- WP4 `step_workflow_run(request, *, spec, store, executor)` already injects an executor and owns CAS claim, gates, input re-verification, mid-step race recheck, single-output claim-check, WATCH-no-downgrade, and "no business verdict from success."
- P6-A `P6ControlledAiFlowSession` already admits an executor via `evaluate_p6_admission` (`_executor_is_armed` requires `.enabled is True` + callable `.execute`) and maps `query/cancel/recover/close` onto the executor's control surface + WP4 entrypoints, preserving WATCH.
- `activity_controlled_exec.start_controlled_local_exec` already enforces: exact token + `enabled`; read-only role allowlist (`CONTROLLED_EXEC_ROLE_ALLOWLIST`) with write/future keys fail-closed (`CONTROLLED_EXEC_FUTURE_ROLE_KEYS`); pinned-local-acpx provenance (`_check_runner_provenance`, `FORBIDDEN_RUNNER_BASENAMES`, sha256, null/relative/launcher rejected); read-only capability (`_check_role_capability`: read/search true, write/execute/terminal/delete/move/fetch/switch_mode/other false); atomic pre-launch claim (`ControlledLocalExecClaimStore`) with replay/conflict fail-closed; `prompt_materializer` seam (default `None` ⇒ `prompt=None` ⇒ no run); sanitized claim state (no raw prompt/output/exception; `business_verdict` stays `None`).
- `P5TemporalStepExecutor` is the reference shape for an executor that admits default-off, translates only sanitized refs, and preserves WATCH in `acancel`.

So P6-B's new code is only: admission on a new P6-B token; WP4 `request`/`role_binding`/`resolved_inputs` → sanitized `ControlledLocalExecRequest` + injected deterministic `prompt_materializer`; one injected `artifact_sink` that turns the read-only run output into exactly one claim-check `ArtifactRef` (bytes never persisted); sanitized `ControlledLocalExecResult` → `StepExecutionOutcome`; WATCH-preserving `query/cancel/recover/close`.

## 2. Exact future implementation surfaces and changed-file allowlist

**New production source (prefer one module):**

- `sachima_supervisor/p6b_read_only_real_agent.py` — the only required new production module:
  - `P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN` (split-literal, value = §13 phrase) — **distinct** from the P6-A composition token and the controlled-exec/Phase-E2 tokens.
  - additive outer stable codes (wrap, never replace inner codes): `p6b_execution_disabled`, `p6b_approval_mismatch`, `p6b_precondition_unmet`, `p6b_role_not_read_only`, `p6b_runner_provenance_unverified`, `p6b_prompt_materialization_failed`, `p6b_output_unsafe`.
  - `P6BReadOnlyRealAgentStepExecutor` implementing the WP4 `StepExecutor` Protocol (`execute(request, *, role_binding, resolved_inputs) -> StepExecutionOutcome`) plus the oracle-conformant control surface (`query/cancel/recover/close`, `history_projection`/`serialized_history_bytes`) exactly as `P5TemporalStepExecutor` exposes them; carries `.enabled`.
  - the WP4→controlled-exec translation, the injected `prompt_materializer` and `artifact_sink` seams (both default `None` ⇒ fail closed), the `ControlledLocalExecResult` → `StepExecutionOutcome` mapping, and the WATCH-preserving cancel.
  - lazy import of `agent_run_supervisor` only inside the real backend method (mirroring `activity_session_real_execution`); no `temporalio` import on the real-runner path.

**New, allowlisted, optional:**

- `sachima_supervisor/p6b_planning_report_prompt.py` — deterministic, repo-controlled prompt builder + `materialize_*` materializer, mirroring `smoke_prompt.py` (digest/ref for durable state; raw prompt only via the injected materializer). May be folded into the executor module if small.
- `sachima_supervisor/roles/<name>_read_only_planning_report_v1.json` — a committed **null-binary** read-only role (permissions read/search true, all mutate/fetch false; `session.strategy="exec"`), added to `CONTROLLED_EXEC_ROLE_ALLOWLIST`/`CONTROLLED_EXEC_ROLE_ADAPTER_AGENT`. **Reuse `sachima.codex.primary_reviewer` / `sachima.claude.read_only_reviewer` if they fit; add a new role only if a distinct `output_contract`/instruction is needed.**
- `tests/fixtures/sachima_supervisor/p6b_planning_report_prompt.v1.txt` — byte-mirror of the prompt builder.

**New tests:**

- `tests/sachima_supervisor/p6b_read_only_real_agent/unit/test_admission.py`
- `…/unit/test_bridge_translation.py` (WP4 request → sanitized `ControlledLocalExecRequest`; unsafe/raw rejected pre-launch)
- `…/unit/test_role_read_only_enforcement.py` (capability/permissions/future-key/write-role fail-closed)
- `…/unit/test_runner_provenance.py` (null/relative/launcher/`npx`/sha-mismatch fail-closed; reuse `FORBIDDEN_RUNNER_BASENAMES`)
- `…/unit/test_prompt_materialization_no_leak.py`
- `…/unit/test_output_artifact_claim_check.py` (exactly one `ArtifactRef`; bytes never persisted; leak fails closed)
- `…/unit/test_outcome_mapping_no_weakening.py` (no `business_verdict`; gate/claim untouched; WP4 reused)
- `…/unit/test_control_path_watch.py` (query/recover no relaunch; cancel preserves WATCH; no clean-cancel overclaim)
- `…/unit/test_replay_idempotency.py` (WP4 replay ⇒ no execute; controlled-exec replay ⇒ no second launch)
- `…/unit/test_boundary_scan.py` (no Gateway/Feishu/platform/delivery/temporalio-top-level/`npx`/shell/write-role)
- `…/hermetic/test_p6_composition_with_fake_read_only_runner.py` (full P6-A session + WP4 + **injected fake** read-only runner; sanitized evidence)
- `…/hermetic/test_three_surface_no_leak_and_canary.py`
- reuse `tests/sachima_supervisor/p5_temporal/hermetic/test_determinism_replay.py` (controlled body)

**Reused unmodified:** all `sachima_supervisor/ai_flow_*.py`, `p6_controlled_ai_flow.py`, all `p5_temporal/*`, `activity_controlled_exec.py`, `activity_session_real_execution.py` provenance helpers, `activity_preflight.py`, `p5_temporal/contracts.py` leak scans.

**Changed-file allowlist (expect empty residue):**
```
git diff --name-only release/sachima...HEAD \
 | rg -v '^(sachima_supervisor/p6b_read_only_real_agent\.py$|sachima_supervisor/p6b_planning_report_prompt\.py$|sachima_supervisor/roles/[a-z0-9_]+_read_only_planning_report_v1\.json$|tests/sachima_supervisor/p6b_read_only_real_agent/|tests/fixtures/sachima_supervisor/p6b_planning_report_prompt\.v1\.txt$|docs/)'
```
**Forbidden residue (must be empty):** any diff under `gateway/`, `*/platforms/`, Feishu/Lark, delivery, production config, `pyproject.toml`/lockfiles (no new deps), service-lifecycle files, or any edit to `ai_flow_*`, `p6_controlled_ai_flow.py`, `p5_temporal/*`, `activity_controlled_exec.py`, `activity_session_real_execution.py`.

## 3. Control flow P6 → WP4 → P5 → read-only real runner (without weakening StepExecutor semantics)

```
caller/ops (never Gateway):
  spec = validate_workflow_spec(<single read-only planning/report step>)   # read/search-only roles
  store = AiFlowRunStore(...)                                              # in-process (local) or P5 durable claim store
  executor = P6BReadOnlyRealAgentStepExecutor(
                enabled=True,
                approval_token=P6B_..._APPROVAL_TOKEN,
                controlled_exec_store=ControlledLocalExecClaimStore(),
                preflight_store=...,
                prompt_materializer=materialize_p6b_planning_report_prompt,  # explicit; default None ⇒ fail closed
                artifact_sink=<caller out-of-repo claim-checker>,            # explicit; default None ⇒ fail closed
                runner=<pinned via operator role overlay>)                    # null committed ⇒ non-runnable
  session = P6ControlledAiFlowSession(spec, store, executor,
                enabled=True, approval_token=P6_..._APPROVAL_TOKEN, operator_gate=True)
  out = session.run_linear(run_request, [planning_report_step_request], terminal_gate_ref=...)
```

Per step, WP4 (`step_workflow_run`, **unmodified**) owns and keeps:

1. `_check_enabled_and_approved` (WP4 token) + run schedulable + spec/role-digest binding.
2. **CAS claim** `store.claim_step(... fingerprint ...)`. `disposition == "replayed"` ⇒ returns resident, **executor never called** (no real launch on replay).
3. pre-step gate (no executor call if not granted).
4. `_resolve_inputs` + re-verify upstream artifacts + bind `request.input_artifact_digests` to resolved digests (fail closed on divergence) — **before** the executor.
5. `executor.execute(request, role_binding=binding, resolved_inputs=...)` ← the only P6-B entry.
6. **mid-step race recheck** (`run_after` not schedulable ⇒ `cancel_ambiguous`/`active_run_cancellation_watch`, no propagation, no relaunch).
7. post-step gate; `_verify_single_output` (claim-check); `finalize_step_with_artifact_if_run_schedulable` (CAS finalize).

Inside `executor.execute` (the new P6-B code), in order, side-effect-free until the last step:

1. **admit** (mirror `P5TemporalStepExecutor._admit`): `enabled is True`, exact P6-B token, seams present ⇒ else sanitized `_failure(p6b_*)` (zero real-runner work).
2. **read-only re-check**: `role_binding.capabilities ⊆ {read, search}`; resolved role permissions write/execute/terminal/delete/move/fetch/switch_mode/other all false; role key ∉ `CONTROLLED_EXEC_FUTURE_ROLE_KEYS` ⇒ else `p6b_role_not_read_only` pre-launch.
3. **sanitized translation**: WP4 `request`/`role_binding`/`resolved_inputs` → a `ControlledLocalExecRequest` of claim-check refs/digests only (reuse the `_resolve_inputs` output, which is already re-verified claim-check artifacts); reject raw/unsafe via `C.scan_projection_for_leak` ⇒ `RUNTIME_UNSAFE_MATERIAL` pre-launch.
4. **delegate to the proven real path**: `start_controlled_local_exec(req, store=controlled_exec_store, preflight_store=..., prompt_materializer=<injected>)`. This enforces provenance, claim, capability, prompt screen, sanitized projection. With `prompt_materializer=None` it cannot launch.
5. **output claim-check** via injected `artifact_sink`: the read-only run's report is written to a caller-owned **out-of-repo** sink that returns exactly one sanitized `ArtifactRef` (`artifact_id, producer_step_id=step_id, content_digest, artifact_kind=step.output_contract, byte_count ≤ max_artifact_bytes, created_at_ref`); scan it; bytes never enter Sachima durable state. Default `None` ⇒ fail closed.
6. **map** `ControlledLocalExecResult` → `StepExecutionOutcome(ok, step_status, artifact_refs=(one ref,), evidence_ref, evidence_digest, error_code)`. **`business_verdict` is never set; success is never inferred** — WP4 records `STEP_COMPLETED` only after its own `_verify_single_output`.

Semantics preserved because the executor **only** returns a sanitized outcome: it never writes the store, never invents a verdict, never bypasses a gate, never relaunches on recover, and never claims a clean cancel it cannot prove.

## 4. Pre-launch claim / replay / lease / idempotency requirements

- **Authoritative pre-launch claim = WP4 `store.claim_step` CAS**, recorded before `executor.execute`. Identical replay (same idempotency key + fingerprint) ⇒ `disposition == "replayed"` ⇒ resident projection returned, **executor not called** (FR2: identical replay returns existing projection, no launch). Same key + divergent fingerprint, or same step under a divergent run/spec digest ⇒ fail closed before claim/executor.
- **Second wall inside the real path:** `ControlledLocalExecClaimStore.claim` is an atomic in-process check-and-set written **before** the supervisor boundary; `"replayed"` returns the resident sanitized projection and never starts a second run; conflicting fingerprint ⇒ `activity_idempotency_conflict`; different idempotency on a held activity ⇒ `activity_claim_conflict`. A crashed in-progress claim is **never auto-relaunched**.
- **Deterministic reattach id:** the bridge derives the controlled-exec `activity_id`/idempotency from sanitized WP4 refs + attempt index (so a crash between WP4 claim and finalize reattaches by id, never double-launches). Recovery uses `executor.recover` (reattach by id) — **never** re-invokes `step_workflow_run` (P6-A `recover` already enforces `reattached_no_relaunch`).
- **Lease/epoch/state-version:** WP4 `StepAttemptRequest` carries `lease_id/lease_epoch/lease_holder_ref/expected_state_version`; the bridge binds them to a durable preflight record via `activity_controlled_exec._check_preflight_binding` (stale epoch ⇒ `activity_stale_state`; lost lease ⇒ `activity_lease_lost`; drifted version ⇒ `activity_toctou_conflict`) **before** any launch.
- **Cross-process durable path** (hermetic/staging Temporal): the existing P5 deterministic `p5wf_<48hex>` workflow id + durable claim store provide the target shape for cross-process replay/recover without relaunch, but the later P6-B implementation must prove this concretely before any real smoke. Existing controlled-exec claim storage is in-process, so an implementation that cannot demonstrate crash-after-claim / restart / recover-without-relaunch evidence must fail closed and remain fake-only. No new durable store is introduced by this docs-only governance PR.

## 5. Read-only role / runner provenance (no `npx`/network fetch, no shell interpolation)

- **Pinned local runner only** (reuse `activity_controlled_exec._check_runner_provenance` + `verify_pinned_local_acpx_binary`): role file must carry a non-null **absolute** `acpx_binary` with no whitespace, basename ∉ `FORBIDDEN_RUNNER_BASENAMES` (`npx, npm, pnpm, yarn, bunx, bun, corepack, node, sh, bash, zsh, dash, ksh, fish, env`), exact `acpx_version`, and a request-supplied sha256 of the role file (and optionally of the binary). **Committed role keeps `acpx_binary: null` ⇒ non-runnable by construction; only an operator local overlay pins a verified local executable. There is no `npx`/network fallback** — a null/launcher/relative binary fails `activity_runner_provenance_unverified` before launch.
- **Read-only role enforcement (R1, Q1):** double wall — WP4 spec validation already restricts `capabilities` to `ALLOWED_CAPABILITIES = (read, search)` and rejects write/future role keys; the executor re-checks the resolved role permissions (write/execute/terminal/delete/move/fetch/switch_mode/other all false) and the per-role adapter pin. Runtime containment: `workspace.allowed_roots` + sandbox + role `redaction` (suppress_reads, redact_prompt/stderr/metadata/env); **work_dir is caller-owned and outside `_REPO_ROOT`** (`_require_offline_dir`). Smoke evidence (separate gate) must prove no enforcement gap: clean `git status`, no files written outside the out-of-repo scratch, no network egress.
- **No shell interpolation:** the runner is driven only through the `agent_run_supervisor`/acpx API as an argv list; the module must contain **no** `shell=True`, `os.system`, `os.popen`, `subprocess` with string commands, or f-string/`%`/`.format` command building. The prompt is passed as a bounded argument/stdin value, never concatenated into a command line.
- **Forbidden-surface markers** in role/paths reuse `_FORBIDDEN_SURFACE_MARKERS` (gateway, feishu, lark_im, webhook, ingress, im_delivery, real_delivery) ⇒ hard fail.

## 6. Prompt materialization and no-leak strategy

- **Deterministic, repo-controlled prompt** (mirror `smoke_prompt.py`): the prompt lives in code, a committed fixture mirrors it byte-for-byte, and the builder re-screens on every build (`_value_is_unsafe`, `_has_exec_unsafe_marker`, bounded length). It is **never** assembled from raw IM text, card JSON, media bytes/paths, tool output, Gateway payloads, env, credentials, platform ids, callback URLs, or host paths.
- **Inputs are claim-check refs only:** the prompt is parameterized solely by the sanitized claim-check refs/digests of the upstream high-density summary artifact (resolved + re-verified by WP4 `_resolve_inputs`) plus the committed template. Raw external input is claim-checked **upstream** of P6-B.
- **Injection is explicit and post-claim:** `prompt_materializer` defaults to `None` ⇒ `prompt=None` ⇒ the supervisor boundary fails closed on an empty exec prompt ⇒ **no agent run from the default path**. When injected, `_materialize_prompt` runs only after the acquired claim, screens + bounds the output, and the string lives only in the in-memory seam request — **never** in durable claim state, fingerprints, or query projections. A failed/unsafe materialization finalizes a terminal sanitized failure (`activity_prompt_materialization_failed`) with no supervisor call.
- **Three reused no-leak walls + the new bytes seam + a canary:**
  1. WP4 store/query/evidence — claim-check-only; `ai_flow_evidence._assert_no_leak`.
  2. Temporal JSON + serialized bytes (hermetic path) — `contracts.scan_projection_for_leak` (SCAN 1) + `scan_bytes_for_leak` (SCAN 2).
  3. P6 evidence packet — `build_p6_evidence_projection` re-scans before return (raises `RUNTIME_HISTORY_LEAK_DETECTED` on any hit).
  4. **Report-bytes seam** — the `artifact_sink` emits only `ArtifactRef` fields; the body is digested out-of-band and never persisted; the ref is SCAN-1 checked.
  5. **Canary:** seed `raw_prompt`, `signed_url`, `Traceback`, `bearer …`, `/home/…`, card JSON, media bytes at the input boundary; assert appearance in **none** of the four surfaces and a fail-closed stable code.

## 7. Progress / evidence shape

- **Progress** = P6-A control snapshots (`_control_snapshot`, SCAN-1 guarded) + the executor `history_projection()` (sanitized events: `event`, `sequence`, `run_ref`, `step_ref`, `error_code` only) — mirroring `P5TemporalStepExecutor`. No raw output, no model text.
- **Final evidence** = `build_p6_evidence_projection(admission=…, workflow_evidence=summarize_workflow_run(...))` carrying: `final_verdict`, `active_run_cancellation_watch`, `workflow_spec_digest`, `role_binding_digest`, `state_transitions`, `gate_decisions`, `artifact_refs` (the single claim-check ref), `error_codes` (outer `p6b_*` + inner WP4/`runtime_*`/`activity_*`), `control_markers`, optional sanitized real-run counts (turns, `artifact_ref_count`, duration bucket), and `evidence_digest`.
- **Never present:** raw prompt, final message, tool output, platform ids, card JSON, media bytes/paths, credentials, raw exception text, raw artifact/evidence file paths. The agent's `acpx_session_id` (if any) appears only as an opaque `_session_binding` hash. `business_verdict` stays `None`.

## 8. Cancellation / recovery semantics preserving WATCH

- **Executor cancel** mirrors `P5TemporalStepExecutor.acancel`: clean `cancelled` only when `interrupt_outcome.interrupted is True AND cleanup_verified is True`; otherwise `_failure(ACTIVE_RUN_CANCELLATION_WATCH, ambiguous=True)`, `step_status="cancel_ambiguous"`.
- **No real abort in P6-B.** A real cancellation is a *separate* WP3b gate: `execute_real_cancellation` requires `PHASE_E2_CANCEL_EXECUTION_APPROVAL_TOKEN` + lifecycle in-flight proof and otherwise fails closed (`activity_cancel_not_approved`). P6-B does **not** approve real cancellation execution; the bridge passes `interrupt_outcome=None` on active-run cancel, so it can only ever record/propagate WATCH.
- **WP4 keeps the locks:** between-step cancel is deterministic only when no step is `STEP_CLAIMED`; the mid-step race recheck and the cross-cancel-id no-downgrade ensure a prior WATCH/ambiguous can never be upgraded to clean `cancelled`.
- **Recover** = `executor.recover` reattach-by-id reconciled with `query_workflow_run`; **never** relaunch. P6-A `recover` already stamps `reattached_no_relaunch`.
- **Evidence** carries the `active_run_watch` marker; the user-review packet states plainly: **P6-B does not prove clean active-run cancellation; this remains WATCH.**

## 9. Forbidden-surface scans (merge-blocking)

```
# Implementation/runtime surface (expect empty)
git diff --name-only release/sachima...HEAD | rg '^(gateway/|.*/platforms/|pyproject\.toml$|uv\.lock$)'

# No edit to reused walls (expect empty)
git diff --name-only release/sachima...HEAD \
 | rg '^(sachima_supervisor/(ai_flow_.*|p6_controlled_ai_flow|activity_controlled_exec|activity_session_real_execution)\.py|sachima_supervisor/p5_temporal/)'

# Forbidden runner / shell / network / write-role / git-mutation on added lines (expect empty)
git diff release/sachima...HEAD -- sachima_supervisor/p6b_read_only_real_agent.py \
 | rg '^\+' | rg -i '\b(npx|npm|pnpm|yarn|bunx|node|network_fetch|shell\s*=\s*True|os\.system|os\.popen|subprocess|write_role|git\s+(commit|push)|gh\s+pr)\b'

# Committed role must stay null-binary (expect a match showing null)
rg '"acpx_binary"\s*:\s*null' sachima_supervisor/roles/*read_only_planning_report*.json

# Boundary import test asserts: no Gateway/Feishu/platform/delivery/public-ingress,
# no top-level temporalio on the real-runner path, agent_run_supervisor imported lazily only.
```
A static boundary test (extending `p5_temporal/unit/test_gateway_boundary.py` + `p6_controlled_ai_flow` boundary tests) asserts the P6-B import closure contains no Gateway/Feishu/platform/delivery/public-ingress reference and no production Worker/service auto-start.

## 10. TDD task plan (later P6-B implementation; each red→green, maps to a gate)

Tasks 1–10 use an **injected fake read-only runner — no real acpx/agent**; 11 reuses the hermetic controlled body; 12–13 are docs/review.

1. **Admission unit** — default-off / token / seams-present ⇒ zero real-runner work. (Gate: P6-B admission.)
2. **Bridge-translation unit** — WP4 `request`/`role_binding`/`resolved_inputs` → sanitized `ControlledLocalExecRequest`; raw/unsafe rejected pre-launch. (Gate: translation.)
3. **Read-only role enforcement unit** — capabilities ⊄ read/search, any mutate/fetch permission true, or a future/write role key ⇒ fail closed; per-role adapter pin. (Gate: read-only.)
4. **Runner provenance unit** — null/relative/launcher/`npx`/sha-mismatch fail closed; reuse `FORBIDDEN_RUNNER_BASENAMES`. (Gate: provenance.)
5. **Prompt materialization no-leak unit** — default `None` ⇒ no run; injected materializer screened/bounded; raw never in durable state. (Gate: no-leak.)
6. **Output artifact claim-check unit** — exactly one `ArtifactRef`; oversized/extra/zero ⇒ fail closed; bytes never persisted; leak fails closed. (Gate: claim-check.)
7. **Outcome-mapping no-weakening unit** — no `business_verdict`; WP4 gates/claim/verify reused; success only via WP4 `_verify_single_output`. (Gate: no-weakening.)
8. **Replay/idempotency unit** — WP4 replay ⇒ no execute; controlled-exec replay ⇒ no second launch; conflict fails closed; recover reattaches. (Gate: idempotency.)
9. **Control-path WATCH unit** — query/recover no relaunch; active-run cancel ⇒ WATCH, never clean. (Gate: WATCH.)
10. **Boundary + forbidden-runner scan unit** — imports + added-line scans. (Gate: boundary, merge-blocking.)
11. **Hermetic composition + three-surface no-leak + canary** — full P6-A session + WP4 + fake read-only runner; sanitized evidence; reuse determinism-replay (controlled body). (Gate: no-leak / composition, merge-blocking.)
12. **Docs/status stale-phrase scan** + `tools/sync_roadmap_status.py --check`. (Gate: docs.)
13. **Codex exact-head blocker review** at the implementation PR head. (Gate: review.)

## 11. Local / deterministic gates and exact review gates

**Local/deterministic (all with the injected fake read-only runner; CI-safe):**
```
uv run --frozen --extra dev python -m pytest tests/sachima_supervisor/p6b_read_only_real_agent/unit/ -q
uv run --frozen --extra dev python -m pytest \
  tests/sachima_supervisor/test_ai_flow_orchestration.py \
  tests/sachima_supervisor/p6_controlled_ai_flow/unit/ \
  tests/sachima_supervisor/test_controlled_local_exec.py -q          # reuse walls intact
uv run --frozen --extra dev --extra flowweaver-temporal python -m pytest \
  tests/sachima_supervisor/p6b_read_only_real_agent/hermetic/ \
  tests/sachima_supervisor/p5_temporal/hermetic/test_determinism_replay.py -q
uv run --frozen --extra dev ruff check sachima_supervisor/p6b_read_only_real_agent.py tests/sachima_supervisor/p6b_read_only_real_agent
git diff --check
python tools/sync_roadmap_status.py --check --base-remote sachima
# + the §2 changed-file allowlist and §9 forbidden-surface scans
```
(Hermetic Temporal suites run only where a dev server is available; guarded/skipped otherwise, same as P5/P6-A. No real acpx in any of the above.)

**Exact review gates:**
- This docs-only packet: independent Codex blocker review of PRD + this solution; **PASS or all blockers fixed and re-reviewed.**
- Later implementation PR: Codex exact-head blocker review **plus** these merge-blocking gates — no-leak (3 surfaces + canary), boundary/forbidden-runner scan, changed-file allowlist, reused-walls-untouched scan, read-only/provenance fail-closed suite, docs/status gates.
- Merge readiness stays **GitHub/live-head authoritative**; archived plans are not CI/merge authority.

## 12. Forbidden surfaces preserved (P6-B implementation must not add)

```
real agent execution without the separate real-smoke approval
real acpx/npx/Claude/Codex invocation from the default path
write-capable roles; file mutation; git commit/push/PR create/merge; external API/tool side effects
additional/unbounded persistent sessions; additional/unbounded cancellation execution
clean active-run cancellation claims beyond WATCH
Gateway involvement/mutation/restart/reload; Feishu/IM/live/default-on; platform-adapter mutation; public ingress
production config writes; production Temporal cluster/traffic; service restart/reload; real delivery
new dependencies; pyproject/lockfile changes; edits to WP4/P6-A/P5/controlled-exec/real-session modules
```

## 13. Implementation approval phrase and separate real-smoke approval split

**Stage 1 — source implementation only** (default-off; injected-fake runner gates only; **no real launch**). Exact phrase (= PRD §10), no broader:
```
approve_agent_run_supervisor_sachima_p6b_bounded_read_only_real_agent_step_execution_implementation_default_off_single_read_only_planning_report_step_pinned_local_runner_only_no_write_roles_no_file_mutation_no_git_mutation_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery_no_real_smoke_without_separate_approval
```
This authorizes only the new module/role/prompt/tests above. Because the committed role is null-binary and `prompt_materializer`/`artifact_sink`/`runner` default to unset, **no real agent can run even after merge.**

**Stage 2 — bounded real smoke** (separate, explicit, later). Must name exactly:
- runner: pinned local `acpx_binary` absolute path + sha256 + version;
- role key + adapter (read-only; write/execute/fetch=false);
- workflow id + the single step id + `output_contract`;
- max turns / max wall-time;
- repo identity + **out-of-repo** work_dir/scratch + **out-of-repo** evidence destination;
- explicit assertion of **no file mutation, no git mutation, no network, no delivery**, with post-run proof (clean `git status`, no out-of-scratch writes).

Suggested shape:
```
approve_agent_run_supervisor_sachima_p6b_bounded_read_only_real_agent_step_real_smoke_single_run_pinned_local_acpx_<sha>_role_<role_key>_workflow_<wf>_step_<step>_max_turns_<n>_max_seconds_<t>_out_of_repo_workdir_and_evidence_no_write_no_git_no_network_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Neither phrase authorizes Gateway/Feishu/live/production config/real delivery/write roles/multi-step/persistent sessions/real cancellation. WP3b active-run cancellation WATCH remains open and is not claimed clean by P6-B.
