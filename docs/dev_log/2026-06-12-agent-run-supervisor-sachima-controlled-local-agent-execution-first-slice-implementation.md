# Dev Log — agent-run-supervisor × Sachima Controlled Local Agent Execution First Slice Implementation (Phase C)

Date: 2026-06-12
Branch: `feature/ars-controlled-local-exec`
Base: `release/sachima` @ `a02c00008960fbaabdeb378ca4c85ea58aef9898`
PR: not opened (implementation author does not commit/push; Hermes owns repo operations)
Approval basis: user approval of the controlled local agent execution first implementation slice per the 2026-06-12 PRD → Claude architecture → Codex review → user review packet flow (PRD worktree `ars-controlled-local-agent-execution-prd`)

## AGENT Split

Preserved as designed: Hermes is PM/controller/verifier/repo operator; Claude Code (this log's author) is main programmer; Codex CLI is primary reviewer in a later, fresh review-only pass. No agent reviews or merges its own work. This implementation pass produced code/tests/docs only — no commit, push, merge, service restart, production config write, Gateway call, or IM delivery.

## Scope

Implemented the Phase C controlled local **one-shot exec** first slice around the merged local/offline seam:

- new `exec_controlled` mode (existing `exec_dry_run` path untouched; session/cancel/live/delivery-shaped modes rejected);
- exact Phase C approval token, default-off by construction;
- single runnable role `sachima.codex.primary_reviewer` (read/search only, adapter_agent `codex`, session strategy `exec`); Claude architect/main-programmer/docs and Codex blocker-only reviewer keys documented as future mainline, not runnable;
- pinned local acpx no-fetch runner provenance: role file must declare a non-null absolute whitespace-free `acpx_binary` (npx-shaped basenames rejected) and the request must carry the exact sha256 of the role file;
- committed role config `sachima_supervisor/roles/codex_primary_reviewer_exec_controlled_v1.json` truthfully keeps `acpx_binary: null` (no local acpx binary exists on this host), so the committed config fails closed on provenance and is not runnable by construction;
- atomic pre-launch claim/CAS (`claimed_in_progress -> completed | failed_retryable | failed_terminal`) via a lock-guarded in-process claim store (single mutex around every claim/finalize/read check-and-set); identical replay of in-progress/terminal claims returns the resident sanitized projection without relaunch; conflicting replay and same-activity/different-key requests fail closed before launch — under true concurrency as well as sequentially; crashed in-progress claims are never auto-relaunched; a transactional durable (cross-process) store adapter remains a later, separately approved gate;
- durable-state preflight binding: the request must reference an existing PR #107 preflight record with the same transaction/operation and matching lease id/epoch/holder and state version;
- prior controlled dry-run evidence digest and exact operator gate preconditions;
- sanitized claim state + read-only query projection with validate-on-read store hardening;
- stable error collapse (`activity_supervisor_failed`) for supervisor exceptions and unsafe outcome fields; `business_verdict` permanently null and caller-owned (a lower layer reporting one collapses to `failed_terminal`);
- seam request carries claim-check refs only with `prompt=None`; combined with the supervisor caller boundary's empty-prompt fail-closed check, no agent process can start from this slice even when fully wired — prompt materialization is a later, separately approved gate.

## TDD Evidence

- RED: `tests/sachima_supervisor/test_activity_controlled_exec.py` written first; run failed with `ModuleNotFoundError: No module named 'sachima_supervisor.activity_controlled_exec'`.
- GREEN: after implementing the module, role config, and exports — `108 passed in 0.80s` for the new file.

## Codex Primary Review Blocker Fix (same date, post-review)

The Codex CLI primary review (full-access review-only retry after the known bwrap loopback sandbox issue) returned `VERDICT: BLOCK` with one blocker: `ControlledLocalExecClaimStore.claim()` performed separate read/check/write steps with no lock, transaction, or durable compare-and-set, so concurrent starts could both observe no resident claim and launch, and the approved atomic pre-launch claim/CAS boundary was not actually satisfied.

Minimal fix applied in this worktree:

- `ControlledLocalExecClaimStore` now carries a single in-process `threading.RLock`; every `claim`/`finalize`/`get_by_activity`/`get_idempotent` check-and-set critical section runs entirely under that mutex, making the pre-launch claim a real atomic CAS for this local/offline in-process slice. Validate-on-read and the sanitized projection behavior are unchanged. The public scope is deliberately not widened: a transactional durable (cross-process) claim-store adapter with unique activity/idempotency constraints remains a later, separately approved gate.
- Four true-concurrency tests added (suite for the file: 108 → 112): (1) identical concurrent starts (8 threads, barrier-aligned, the single winning launch held in-progress inside the supervisor fake until all other callers settle) → exactly one supervisor invocation, every other caller receives the resident `claimed_in_progress` projection, final state `completed`; (2) concurrent same-activity/different-idempotency-key starts → exactly one launch, all others fail closed `activity_claim_conflict` pre-launch; (3) concurrent same-idempotency-key/different-fingerprint starts → exactly one launch, all others fail closed `activity_idempotency_conflict` pre-launch; (4) store-level race of 16 barrier-aligned identical `claim()` calls with the validate step slowed to widen the read/check/write window → exactly one `acquired`, fifteen `replayed`.
- Mutation check (not committed): replacing the `with self._lock:` sections with no-ops makes the store-level concurrent test fail with multiple acquisitions, confirming the tests detect the original unlocked defect; the lock was restored and the suite re-run green.
- Codex low-risk note addressed: the committed role JSON and the test fixture mapping now use the neutral portable placeholder `/workspace/sachima` for `workspace.default_cwd`/`allowed_roots` instead of host-specific home-directory paths (these fields are caller-documentation only; no gate validates them in this slice).

## Final Local Verification Evidence

```text
scripts/run_tests.sh tests/sachima_supervisor
=== Summary: 5 files, 229 tests passed, 0 failed (100% complete) ===
(117 pre-existing + 112 new controlled-exec tests, including 4 true-concurrency claim/CAS tests)

.venv/bin/python -m compileall -q sachima_supervisor tests/sachima_supervisor
# exit 0

git diff --check
# exit 0

codegraph sync && codegraph status
# run in this worktree; see PR notes
```

In-test forbidden-surface scan asserts the new module source contains no aiohttp/httpx/lark_oapi/feishu/webhook/temporalio/subprocess/docker/systemctl/os.system/popen/pexpect/`npx -y`/`shell=true`/`codex exec`/`claude exec` tokens and no requests/gateway/socket import surface.

## Environment Notes (exact, not faked)

- The shared `~/.hermes/hermes-agent/venv` (the fallback used by `scripts/run_tests.sh`) has no `pytest` installed — pre-existing environment gap. A worktree-local `.venv` (gitignored) was created with the pinned dev test deps from `pyproject.toml` (`pytest==9.0.2`, `pytest-asyncio==1.3.0`, `pytest-timeout==2.4.0`); the runner script probes `.venv` first by design. The shared venv was not modified.
- `tools/build_docs_index.py` and `tools/docs_drift_signal.py` do not exist in this repository (verified by filesystem search), so the docs index/drift generator gates are N/A here.
- No local acpx binary exists on this host: `npx --no-install acpx --version` reports the package is missing. This is why the committed role config keeps `acpx_binary: null` and why real local smoke is BLOCKED (see tails).

## Blocked / Open Tails

```text
TAIL-ARS-CTRL-EXEC-REAL-SMOKE — NEXT_PHASE, currently BLOCKED
  Real local Codex read-only smoke was NOT run and is NOT claimed. Blockers:
  (1) no pinned local acpx binary exists on this host (null in committed role config; provenance
      gate fails closed by design);
  (2) prompt materialization is deliberately unimplemented in this slice (seam prompt=None fails
      closed at the supervisor caller boundary).
  Unblocking requires an operator-pinned verified local acpx executable, a separately approved
  prompt materialization gate, and a Phase D smoke plan with sanitized evidence only.

Codex CLI primary re-review — PASS (Hermes-owned fresh review-only context; Codex output: `VERDICT: PASS`, `BLOCKERS: None`).
  First review returned VERDICT: BLOCK on the unlocked claim store check-and-set; the blocker is
  fixed in this worktree (locked in-process CAS + true concurrent tests, see the blocker-fix
  section above) and Codex confirmed it is fixed for the approved local/offline first slice.
PR — open: https://github.com/jovijovi/sachima/pull/114. CI / merge — awaiting checks and explicit merge decision.
```

## Non-Approvals Preserved

```text
real_external_sachima_ingress
production_durable_runtime_code_implementation
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
gateway_code_path_mutation
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
satine_or_hermes_profile_acp_execution
write_capable_claude_or_codex_roles
persistent_session_execution
cancellation_execution
controlled_ai_flow_execution
```
