# P6-B Stage-2 host-local DoR / crash-no-relaunch proof — Implementation

Date: 2026-06-27
Status: Implementation / proof-candidate branch (default-off; injected-fake / temp-fake only). No real agent, no real smoke.
Approval phrase (exact, host-local DoR / crash-no-relaunch proof only):

```text
approve_agent_run_supervisor_sachima_p6b_stage2_host_local_dor_and_crash_no_relaunch_proof_pinned_local_runner_role_overlay_artifact_sink_evidence_only_no_real_agent_launch_no_real_smoke_no_write_no_git_no_network_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

## 1. What this branch adds

The Stage-2 readiness/governance packet (PR #174) labelled real smoke `BLOCKED` behind two
blockers: **B1** cross-process crash / recover-without-relaunch is unproven, and **B2** the exact
runner/role/sink/evidence values are not pinned. The technical solution offered **Option B — a
fail-closed host-local proof** as the safe next gate (no durable store, no real agent).

This branch implements that narrow Option-B surface and nothing else:

New production source (one new module):

- `sachima_supervisor/p6b_host_local_dor.py` — a small, default-off **definition-of-ready**
  surface that can (1) pin/validate a host-local runner + role overlay + artifact-sink +
  evidence-root *shape* without launching a real agent, and (2) prove the current in-process
  P6-B path is fail-closed after a simulated crash/restart. It contains the exact Stage-2 DoR
  approval token (split literal) and additive `p6b_dor_*` stable codes. It builds no runner,
  executes no binary, opens no network/Gateway/Feishu/live surface, and reuses the merged P6-B
  bridge + controlled-exec walls **unmodified**.

New tool (CLI):

- `tools/p6b_host_local_dor.py` — writes a sanitized JSON evidence bundle under an out-of-repo
  evidence root and prints a sanitized summary. On this host (no acpx provided) it completes as a
  controlled `blocked` evidence report — it does not error and does not launch. The optional
  `--probe` path runs an **argv-list / no-shell** version probe against an operator-supplied
  binary (tests pass a temp fake executable only).

No committed role file was added or changed: the committed read-only roles stay null-binary and
non-runnable by construction. `activity_controlled_exec.py`, `p6b_read_only_real_agent.py`,
WP4/P6-A/P5 are unchanged.

## 2. Surface 1 — host-local runner / role overlay / sink / evidence pinning (B2 tooling)

`assess_p6b_host_local_dor(request, *, repo_root=None, version_probe=None) -> P6BHostLocalDorReport`

1. **Admit** (default-off): `enabled is True`, exact Stage-2 DoR token, and every `allow_*`
   scope-widen flag `False`. A miss returns a controlled `blocked` report with **no** crash
   proof and **no** launch.
2. **Roots outside repo**: the role overlay, evidence root, and artifact-sink root each resolve
   **outside** the repo root or fail closed (`p6b_dor_root_inside_repo`). Paths are projected as
   digests only.
3. **Runner params present**: with the exact runner parameters absent/missing/unpinned, the
   runner-pinning track returns a controlled `blocked` (`p6b_dor_runner_params_missing`) — the
   expected posture on this host.
4. **Role overlay validation**: exact read-only role key (in the controlled allowlist), adapter
   pin (`CONTROLLED_EXEC_ROLE_ADAPTER_AGENT`), `acpx@0.10.0`, absolute non-whitespace
   non-launcher `acpx_binary` matching the request, `read`/`search` true, all of
   `write/execute/terminal/delete/move/fetch/switch_mode/other` false, and `session.strategy ==
   exec`. Digest mismatch ⇒ `p6b_dor_role_overlay_digest_mismatch`; shape miss ⇒
   `p6b_dor_role_overlay_invalid`; launcher/relative/whitespace/divergent binary ⇒
   `p6b_dor_runner_provenance_unverified`.
5. **Optional binary version probe**: when an argv-list/no-shell probe is injected it reuses the
   merged `verify_pinned_local_acpx_binary` to pin the version as an exact standalone token and
   the binary sha256 against the request pin. Tests use a **temp fake executable**, never real
   acpx. With no probe injected, the identity is recorded as pinned-but-not-reverified.

The report carries only sanitized refs/digests/counts/statuses. Raw host paths, the role overlay
body, prompts, outputs, platform ids, and secrets never appear; the projection is leak-scanned
by construction (`scan_projection_for_leak`).

## 3. Surface 2 — crash / restart fail-closed no-relaunch proof (B1, Option B)

`prove_crash_no_relaunch()` constructs the merged `P6BReadOnlyRealAgentStepExecutor` over a
**fresh empty** `ControlledLocalExecClaimStore` (modeling a process restart that lost all
resident in-process claim state) and a supervisor invoker that **raises/counts** if ever called.

- `query` and `recover` are called **by run/step only**; `execute` is **never** called.
- Both return a sanitized `not_found`; `recover` carries
  `recovery_marker=reattached_no_relaunch`; the supervisor launch count is `0`.
- A stale execute after store loss is recorded as `execute_after_store_loss =
  not_approved_not_attempted` — it is unsafe/unproven and deliberately not attempted.

The proof is independent of runner pinning, so it runs whenever the DoR is admitted (including
the on-this-host `blocked` runner case).

## 4. Explicit limitation (recorded in every report)

> Without a durable cross-process controlled-exec claim store, recover-without-relaunch cannot be
> proven as *reattachment* to a live run. This DoR proves only fail-closed no-relaunch recovery
> after resident in-process claim state is lost, not real execution readiness by itself.

So B1 is addressed only in its **Option B** (fail-closed) form; the **Option A** durable
cross-process claim store remains separately approved future work. B2 tooling now exists, but on
this host no real runner/overlay is pinned, so the DoR result here is **fail-closed no-relaunch
proven + runner pinning BLOCKED**. Real smoke remains unapproved and blocked.

## 5. Tests (TDD; injected-fake / temp-fake only — no real acpx/agent)

`tests/sachima_supervisor/p6b_host_local_dor/`:

- `unit/test_assess_admission_and_blocked.py` — default-off / token / scope-widen ⇒ `blocked`,
  skipped crash proof; missing runner params ⇒ `blocked`, zero launch, crash proof still runs.
- `unit/test_assess_runner_overlay.py` — valid read-only overlay passes; write-capable /
  dangerous-permission / read-false / wrong-adapter / wrong-version / non-`exec` session /
  unknown role / launcher / relative / whitespace binary / digest mismatch / request-vs-overlay
  divergence each fail closed.
- `unit/test_assess_version_probe.py` — temp-fake probe + sha pin pass; sha mismatch / wrong
  probe version fail closed; no-probe leaves the identity `skipped` but the overlay valid.
- `unit/test_assess_roots.py` — overlay/evidence/sink inside the repo fail closed; outside pass
  and project digests only.
- `unit/test_crash_no_relaunch_proof.py` — `not_found` / `reattached_no_relaunch`, launch count
  0, `execute` not attempted; projection leak-clean; embedded in the report.
- `unit/test_report_sanitization.py` — projection leak-clean and free of raw host paths;
  canonical JSON round-trips; limitation recorded.
- `unit/test_cli_evidence.py` — evidence writer refuses inside-repo and writes out-of-repo JSON;
  argv/no-shell default probe reads a temp fake executable; CLI default (no binary) is a
  controlled `blocked` evidence report (exit 0); full params + `--probe` pass; CLI does not
  mutate the repo.

## 6. Local verification (Hermes-run gates — see manifest)

- New DoR tests after the Codex blocker regression fix: `48 passed`.
- Corrected focused gate (new DoR + existing P6-B bridge + controlled-exec + AI-flow orchestration): `339 passed`.
- Full non-Temporal supervisor subset: `813 passed` before the two blocker-regression tests were added.
- Temporal subset under `--all-extras`: `53 passed`.
- Full `tests/sachima_supervisor` under `--all-extras` after the blocker fix: `1012 passed`.
- Ruff on touched Python: `All checks passed!`.
- `python -m compileall` on touched Python files: clean.
- `git diff --check`: clean.
- `tools/sync_roadmap_status.py --file docs/roadmap/current-status.md --check`: machine status block up to date.
- Changed-file allowlist, secret-shaped scan, and forbidden live/runtime surface scan: clean.
- CLI BLOCKED demo on this host wrote sanitized out-of-repo evidence with `status=blocked`, `runner_pinning_status=blocked`, `crash_proof_status=pass`, `supervisor_launch_count=0`, and `execute_after_store_loss=not_approved_not_attempted`.

One verifier issue was corrected during Hermes validation: direct `pytest tests/sachima_supervisor` without
`--all-extras` failed collection because the optional `flowweaver-temporal` extra was not active
(`ModuleNotFoundError: temporalio`). Re-running the full supervisor suite with `uv run --frozen --all-extras`
loaded `temporalio` from `uv.lock` and passed after the Codex blocker fix.

Codex primary review initially returned `VERDICT: BLOCKERS` on one real issue: present-but-invalid runner
pins (`acpx_version="0.9.0"` or malformed `acpx_binary_sha256`) could pass when no version probe was
injected. Hermes added RED regression tests for both cases, fixed `_verify_binary_identity()` to fail
closed before the no-probe path, and reran the gates above. Codex blocker-only re-review returned
`VERDICT: PASS` / `BLOCKERS: None` with post-review diff hash unchanged. A later live PR/head
review found a second blocker: the CLI printed the raw out-of-repo evidence path to stdout after
writing evidence. Hermes added a RED stdout regression test, changed the CLI to print only
`evidence_written_ref: <filename>`, reran the DoR/full supervisor gates, and confirmed the CLI
blocked demo no longer prints the raw evidence root. Codex live blocker-only re-review returned
`VERDICT: PASS` / `BLOCKERS: None` on head `1e3a0a60c6a23eb7c5e51089a2b198b0bee0aabb`.

No real acpx/agent ran in any gate; the only executable a test ever runs is a temp `/bin/sh`
fake that echoes a version line for the argv/no-shell probe.

## 7. Non-approvals preserved

No real agent launch; no real smoke; no real acpx/npx/Claude/Codex step body; no host-local acpx
provisioning beyond a temp fake in tests; no write roles; no file/git mutation by an agent step;
no network; no Gateway/Feishu/IM/live/public ingress; no production config; no service restart;
no real delivery; no new dependencies; no edits to WP4/P6-A/P5/controlled-exec/bridge source.
WP3b active-run cancellation remains WATCH. A real smoke is a separate Stage-2 approval and
additionally requires either the Option-A durable cross-process claim store or a host-pinned runner
the operator supplies out of repo.
