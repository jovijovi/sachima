# P6-B bounded read-only real-agent step execution — Implementation

Date: 2026-06-26
Status: Implementation branch (default-off, fake-runner gates only). No real agent, no real smoke.
Approval phrase (exact, Stage 1 source implementation only):

```text
approve_agent_run_supervisor_sachima_p6b_bounded_read_only_real_agent_step_execution_implementation_default_off_single_read_only_planning_report_step_pinned_local_runner_only_no_write_roles_no_file_mutation_no_git_mutation_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery_no_real_smoke_without_separate_approval
```

## 1. What this branch adds

A thin, **default-off bridge** `StepExecutor` that adapts the already-merged one-shot
controlled local exec (`start_controlled_local_exec`) into the **unmodified** WP4 step
seam, injectable into the **unmodified** P6-A `P6ControlledAiFlowSession`. It builds no
new runner, claim store, provenance gate, or prompt machine, and edits no reused wall.

New production source (the only two new modules):

- `sachima_supervisor/p6b_read_only_real_agent.py` — `P6BReadOnlyRealAgentStepExecutor`
  implementing the WP4 `StepExecutor` protocol (`execute(request, *, role_binding,
  resolved_inputs) -> StepExecutionOutcome`) plus the oracle-conformant control surface
  (`query`/`recover`/`cancel`/`close`, `history_projection`/`serialized_history_bytes`),
  carrying `.enabled`. Contains the exact P6-B approval token (split literal) and the
  additive outer `p6b_*` codes.
- `sachima_supervisor/p6b_planning_report_prompt.py` — deterministic, repo-controlled
  planning/report prompt builder + `materialize_p6b_planning_report_prompt`, mirroring
  `smoke_prompt.py`; only the digest/ref are durable, the raw string is injected.
- `tests/fixtures/sachima_supervisor/p6b_planning_report_prompt.v1.txt` — byte-mirror of
  the prompt builder.

No committed role file was added: the bridge **reuses the existing read-only controlled
roles** (`sachima.claude.read_only_reviewer` / `sachima.codex.primary_reviewer`), which are
committed null-binary and therefore non-runnable by construction. `activity_controlled_exec.py`
is unchanged.

## 2. Control flow (no weakening of StepExecutor semantics)

```
caller/ops (never Gateway):
  spec  = validate_workflow_spec(<single read-only planning/report step>)   # read/search-only role
  store = AiFlowRunStore()
  executor = P6BReadOnlyRealAgentStepExecutor(
                enabled=True, approval_token=P6B_..._TOKEN,
                controlled_exec_store=ControlledLocalExecClaimStore(),
                preflight_store=<durable-state preflight record>,
                prompt_materializer=materialize_p6b_planning_report_prompt,   # default None ⇒ fail closed
                artifact_sink=<caller out-of-repo claim-checker>,             # default None ⇒ fail closed
                role_file_digest=<sha256 of pinned role file>,               # null-binary committed ⇒ non-runnable
                preflight_activity_id=..., prior_dry_run_evidence_digest=...)
  session = P6ControlledAiFlowSession(spec, store, executor, enabled=True,
                approval_token=P6_..._TOKEN, operator_gate=True)
  out = session.run_linear(run_request, [planning_report_step_request], terminal_gate_ref=...)
```

Inside `executor.execute` (the only new entry), side-effect-free until the final delegate:

1. **Admit** (default-off): `enabled is True`, exact P6-B token, required seams present
   (controlled-exec store, preflight store, prompt materializer, artifact sink) — else a
   sanitized `StepExecutionOutcome(ok=False, error_code=p6b_*)` with **zero** launch/sink calls.
2. **Read-only re-check**: `role_binding.capabilities ⊆ {read, search}`; role key is an
   existing read-only controlled role and not a write/future key — else `p6b_role_not_read_only`.
3. **Sanitized translation**: WP4 `request`/`role_binding`/`resolved_inputs` →
   `ControlledLocalExecRequest` of claim-check refs only (deterministic `p6b_exec_<48hex>`
   activity id; the prompt **ref**, never raw text; upstream inputs projected to claim-check
   refs). Raw/unsafe resolved-input material fails closed (`scan_projection_for_leak`).
4. **Delegate to the proven wall**: `start_controlled_local_exec(...)` enforces pinned-local
   provenance, the atomic pre-launch claim, read-only capability, the injected prompt screen,
   and the sanitized projection. With `prompt_materializer=None` it cannot launch; with the
   committed null-binary role it cannot launch.
5. **Output claim-check** via the injected sink: exactly one sanitized `ArtifactRef`
   projection (6 keys, refs/digests only); zero/extra/oversized/unsafe/wrong-producer fail
   closed (`p6b_output_unsafe`). Bytes never enter durable state.
6. **Map** `ControlledLocalExecResult` → `StepExecutionOutcome`. **No business verdict is set
   or inferred** — WP4 records `STEP_COMPLETED` only after its own `_verify_single_output`.

Outer `p6b_*` codes are **additive**: they wrap, never replace, the inner controlled-exec /
`runtime_*` codes.

## 3. Default-off / non-runnable by construction

- `enabled` defaults `False`; `approval_token` defaults `""`.
- `prompt_materializer` and `artifact_sink` default `None` ⇒ admission fails closed ⇒ no run.
- The reused committed role carries `acpx_binary: null` ⇒ the controlled-exec provenance wall
  fails closed before any launch; there is no `npx`/network fallback.
- The bridge contains no subprocess/shell/network/runner; the injected fake read-only runner
  is the only thing the tests ever exercise.

## 4. WATCH / cancellation / recovery

- Active-run cancellation preserves the WP3b WATCH: P6-B never returns a clean active-run
  `cancelled`, even if a caller supplies a confirmed-looking lower-layer interrupt outcome.
  P6-B performs no real abort; real cancellation proof stays behind the separate WP3b gate.
  It can only record/preserve the WATCH (`active_run_cancellation_watch`, `cancel_ambiguous`).
- `query`/`recover` read resident controlled-exec state only and never relaunch; `recover`
  stamps `reattached_no_relaunch`.
- **WATCH carried forward:** a later real smoke is a separate Stage-2 approval and requires
  concrete crash-after-claim / restart / recover-without-relaunch evidence; the existing
  controlled-exec claim store is in-process, so an implementation that cannot demonstrate
  cross-process no-relaunch must remain fake-only and fail closed.

## 5. Tests (TDD, injected fake read-only runner — no real acpx/agent)

`tests/sachima_supervisor/p6b_read_only_real_agent/`:

- `unit/test_admission.py` — default-off / token / missing-seam ⇒ zero launch.
- `unit/test_bridge_translation.py` — claim-check-only translation; raw/unsafe rejected pre-launch.
- `unit/test_role_read_only_enforcement.py` — capabilities/future/unknown role fail closed.
- `unit/test_runner_provenance.py` — null/relative/launcher/`npx`/digest-mismatch fail closed.
- `unit/test_prompt_materialization_no_leak.py` — default None ⇒ no run; fixture byte-mirror;
  raw prompt never in durable state.
- `unit/test_output_artifact_claim_check.py` — exactly one ref; zero/extra/oversized/unsafe/
  wrong-producer fail closed.
- `unit/test_outcome_mapping_no_weakening.py` — no business verdict; wrong ref-count distrusted;
  retryable preserved.
- `unit/test_replay_idempotency.py` — controlled-exec replay ⇒ no second launch.
- `unit/test_control_path_watch.py` — query/recover no relaunch; active-run cancel ⇒ WATCH.
- `unit/test_boundary_scan.py` — no real-runner/IM/temporalio tokens or imports; exact token value.
- `hermetic/test_p6_composition_with_fake_read_only_runner.py` — full P6-A session + WP4 +
  injected fake runner; success; WP4 replay ⇒ executor not re-invoked.
- `hermetic/test_three_surface_no_leak_and_canary.py` — canaries at every boundary appear in
  none of the executor history, durable claim state, or P6 evidence; each path fails closed.

## 6. Local verification (Hermes-run gates — see manifest)

Claude Code could not execute shell/test commands in the governed worktree, so Hermes ran the
focused gates after inspecting the diff. Passing live gates recorded in the manifest include:

- P6-B tests: `60 passed`.
- Reused-wall regression tests: `274 passed`.
- P6-B hermetic + P5 determinism replay: `7 passed`.
- Ruff: `All checks passed!`.
- `git diff --check`: passed.
- `tools/sync_roadmap_status.py --check --base-remote sachima`: machine status block up to date.
- Changed-file allowlist / forbidden-surface / source-forbidden / secret-shaped literal scans: passed.

No real acpx/agent ran in any gate.

## 7. Non-approvals preserved

No real agent execution; no real acpx/npx/Claude/Codex step bodies; no real smoke; no write
roles; no file/git mutation by agent steps; no external API/tool side effects; no Gateway/
Feishu/platform/delivery/public-ingress/production-config; no new dependencies; no edits to
WP4/P6-A/P5/controlled-exec/real-session modules. A later real smoke requires the separate
Stage-2 approval and crash/no-relaunch proof.
