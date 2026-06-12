# agent-run-supervisor × Sachima Controlled Local Agent Execution — First Slice Implementation (Phase C)

> **For Hermes:** This implementation is local/offline only and default-off. It adds the Phase C controlled local **one-shot exec** wrapper (`exec_controlled`) over the existing `sachima_supervisor.local_offline` seam, with pinned local acpx runner provenance and an atomic pre-launch claim/CAS. It does not approve or perform live/default-on behavior, Gateway involvement or mutation, real external ingress, real IM/Feishu delivery, production config writes, Satine/Hermes-profile ACP execution, write-capable Claude/Codex roles, persistent sessions, cancellation execution, or controlled AI FLOW execution beyond this local proof line. **No real local agent smoke was run in this slice** (see Blocked Tails).

## Approval

Status markers:

```text
marker_note: no live / no gateway / no real delivery / no Satine / no write-capable roles / no persistent sessions
LOCAL_OFFLINE_ONLY
DEFAULT_OFF
CONTROLLED_ONE_SHOT_EXEC_FIRST_SLICE
PINNED_LOCAL_ACPX_PROVENANCE_REQUIRED
ATOMIC_PRE_LAUNCH_CLAIM_REQUIRED
READ_ONLY_CODEX_PRIMARY_REVIEWER_ONLY
REAL_LOCAL_SMOKE_NOT_RUN
NO_LIVE
NO_GATEWAY
NO_REAL_DELIVERY
NO_SATINE
NO_WRITE_CAPABLE_ROLES
NO_PERSISTENT_SESSIONS
CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED
```

Process basis (AGENT split preserved): Hermes PRD (2026-06-12) → Claude Code architecture → Codex CLI primary review (two blockers found: npx-is-not-offline, missing atomic pre-launch claim; both resolved; re-review `VERDICT: PASS`) → Hermes user review packet → user approval of the narrow first implementation slice. The PRD and user review packet are file-backed in the separate PRD worktree (`ars-controlled-local-agent-execution-prd`, docs dated 2026-06-12) and are referenced here without modification.

User-approved scope (per the review packet recommendation): controlled local agent execution first implementation slice only — local/offline, default-off, one-shot exec, pinned local acpx binary, read-only Codex primary reviewer, pre-launch claim/CAS, forbidden-surface scans; no Gateway, no real Feishu delivery, no live/default-on, no Satine, no write-capable roles.

Exact code-level approval token defined and required by this slice:

```text
approve_agent_run_supervisor_sachima_controlled_local_agent_execution_first_slice_one_shot_exec_pinned_local_acpx_read_only_codex_primary_reviewer_no_live_no_gateway_no_real_delivery_no_satine_no_write_roles_no_persistent_sessions
```

## Goal

Implement the Phase C caller-owned controlled local execution wrapper so a Sachima/FlowWeaver controller can request one controlled local one-shot exec through the public `invoke_local_offline_supervisor` boundary, with every durable precondition from the durable-runtime design packet (PR #102) and the durable-state preflight (PR #107) enforced fail-closed, and with the two Codex review blockers from the PRD gate structurally closed:

1. **No-fetch runner provenance:** a controlled exec request can only proceed when the allowlisted role file declares a non-null, absolute, whitespace-free local `acpx_binary` (npx-shaped basenames rejected) and the request carries the exact sha256 digest of that role file. A null binary — which would let the supervisor library fall back to its network-fetching `npx` prefix — fails closed before any supervisor call.
2. **Atomic pre-launch claim:** a `claimed_in_progress` claim is check-and-set into the durable claim store *before* the supervisor boundary is invoked, with the whole check-and-set serialized under a single in-process lock so concurrent identical starts resolve to exactly one acquisition and exactly one supervisor invocation. Identical replay of an in-progress or terminal claim returns the resident sanitized projection and launches nothing; conflicting replay (same idempotency key, different fingerprint; or same activity, different key) fails closed before launch — concurrently as well as sequentially; a crashed in-progress claim is never auto-relaunched. This locked store is the first-slice local in-process CAS; a transactional durable (cross-process) claim-store adapter remains a later, separately approved gate.

## Scope

Allowed changed areas:

- `sachima_supervisor/activity_controlled_exec.py` — controlled exec API, claim store, provenance/capability gates.
- `sachima_supervisor/roles/codex_primary_reviewer_exec_controlled_v1.json` — committed read-only Codex primary reviewer role config (truthfully `acpx_binary: null`; not runnable by construction).
- `sachima_supervisor/__init__.py` — public exports.
- `tests/sachima_supervisor/test_activity_controlled_exec.py` — contract, fail-closed, claim/CAS, no-leak, and forbidden-surface tests.
- This implementation plan and manifest.
- Matching dev log.
- `docs/roadmap/current-status.md` status and tail update.

## Implemented Boundary

```text
implemented_surface: controlled local one-shot exec wrapper only
implemented_mode: exec_controlled only (exec_dry_run path untouched; seam exec/session/cancel modes rejected)
runnable_role: sachima.codex.primary_reviewer only (read/search only; adapter_agent codex; session strategy exec)
future_role_keys_documented_not_runnable: sachima.claude.architect, sachima.claude.main_programmer,
                                          sachima.claude.docs_engineer, sachima.codex.blocker_only_reviewer
supervisor_boundary: public invoke_local_offline_supervisor (or injected equivalent in tests) only
runner_provenance: pinned local acpx_binary + exact role-file sha256 digest required; npx fetch path impossible
pre_launch_claim: atomic CAS (single in-process mutex around every check-and-set);
                  claimed_in_progress -> completed | failed_retryable | failed_terminal;
                  concurrent identical starts acquire exactly once, conflicts fail closed pre-launch
state_store: lock-guarded in-memory local/offline claim store with validate-on-read projection
             (cross-process transactional durable store adapter is a later, separately approved gate)
query: sanitized read-only projection; never re-invokes the supervisor
prompt_materialization: not implemented — seam request carries claim-check refs with prompt=None, and the
                        supervisor caller boundary fails closed on an empty exec prompt, so no agent process
                        can start from this slice even if fully wired
business_verdict: always null and caller-owned; a lower layer reporting one collapses to failed_terminal
real_local_smoke: NOT RUN (no pinned local acpx binary exists on this host; npx fetch not allowed)
persistent_sessions / cancellation / Satine / write-capable roles / Gateway / delivery: not present
```

The controlled exec requires all of the following before the claim is attempted, and the claim before any supervisor call:

- `enabled=True` and the exact approval token above;
- mode `exec_controlled`;
- role key in `CONTROLLED_EXEC_ROLE_ALLOWLIST` (exactly `sachima.codex.primary_reviewer`);
- safe claim-check refs only (platform-private/secret/card/media/raw-prompt-shaped values rejected);
- required prompt claim-check ref and preflight record reference;
- exact `operator_gate is True`;
- prior controlled dry-run evidence digest equal to `build_controlled_local_dry_run_evidence()["fixture_digest"]`;
- a durable-state preflight record (PR #107 surface) binding the same transaction/operation with matching lease id/epoch/holder and state version;
- pinned local runner provenance and exact role-file digest;
- read-only Codex one-shot role capability (any write/execute/terminal/delete/move/fetch/switch_mode/other permission, non-codex adapter, or persistent session strategy fails closed).

## Durable Claim State Projection

The durable claim state stores only:

```text
stable type/status/mode/phase codes (claimed_in_progress | completed | failed_retryable | failed_terminal)
caller-owned activity / transaction / operation refs and idempotency key
role key (never raw role JSON)
role-file sha256 digest and prior dry-run evidence sha256 digest
preflight view-model ref and stable approval ref marker
lease id / epoch / holder, state version, attempt index/count
sanitized supervisor status code, artifact ref count, evidence ref + sha256 digest
business_verdict (always null), caller verdict code, stable error code, retryable flag
view-model ref digest
```

It never stores raw prompt/context/model output, platform private ids, card JSON, media bytes/paths, tool output, raw acpx stdout, raw artifact/evidence paths, raw exception text, credentials, or Gateway/delivery data. Resident state is revalidated on every read so malicious resident material can never be projected.

## Failure Taxonomy Additions

On top of the PR #102 taxonomy (`activity_disabled`, `activity_approval_mismatch`, `activity_unsupported_mode`, `activity_unknown_role`, `activity_unsafe_material`, `activity_idempotency_conflict`, `activity_stale_state`, `activity_lease_lost`, `activity_toctou_conflict`, `activity_precondition_unmet`, `activity_supervisor_failed`, `activity_not_found`), this slice adds:

| Error code | Meaning |
|---|---|
| `activity_runner_provenance_unverified` | Role file missing/unparseable, role-file digest missing/mismatched, or `acpx_binary` null/relative/whitespace/npx-shaped — no-fetch local provenance cannot be proven. |
| `activity_role_capability_rejected` | Role config exceeds read-only Codex one-shot scope (write-capable permission, non-codex adapter, persistent session, role-id/schema mismatch). |
| `activity_claim_conflict` | Same activity already claimed under a different idempotency key, or a finalize does not match the resident in-progress claim. |

## Acceptance Gates

- [x] RED first: new test file failed with the module missing before implementation.
- [x] GREEN focused tests: `scripts/run_tests.sh tests/sachima_supervisor` → 5 files, 229 tests passed, 0 failed (112 new controlled-exec tests, including 4 true-concurrency claim/CAS tests).
- [x] Compile check: `.venv/bin/python -m compileall -q sachima_supervisor tests/sachima_supervisor` → exit 0.
- [x] `git diff --check` clean.
- [x] Changed-file allowlist respected (see manifest).
- [x] Forbidden-surface scan: test asserts the module source has no aiohttp/httpx/lark_oapi/feishu/webhook/temporalio/subprocess/docker/systemctl/os.system/popen/pexpect/`npx -y`/socket/requests/gateway-import/`codex exec`/`claude exec` surface.
- [x] Codex primary review blocker (unlocked in-memory claim check-and-set) fixed: single in-process mutex serializes every claim/finalize/read critical section; true concurrent tests prove exactly one supervisor invocation for identical concurrent starts and pre-launch fail-closed for concurrent conflicts; a lock-removal mutation check confirmed the concurrent store test fails without the mutex.
- [x] CodeGraph sync/status in this worktree.
- [x] Codex CLI primary re-review from a fresh context: `VERDICT: PASS`, `BLOCKERS: None` (Hermes-owned review-only retry after the known read-only sandbox `bwrap` failure).
- [x] PR opened: https://github.com/jovijovi/sachima/pull/114.
- [ ] CI / merge (awaiting checks and explicit merge decision).

Environment note: the shared `~/.hermes/hermes-agent/venv` lacked `pytest` (pre-existing environment gap), so a worktree-local `.venv` was created with the pinned dev test deps (`pytest==9.0.2`, `pytest-asyncio==1.3.0`, `pytest-timeout==2.4.0`); `scripts/run_tests.sh` picks it up first by design. The repo has no `tools/build_docs_index.py` or `tools/docs_drift_signal.py`, so those generator gates are N/A for this repository.

## Blocked Tails

```text
TAIL-ARS-CTRL-EXEC-REAL-SMOKE (NEXT_PHASE, currently BLOCKED):
  No pinned local acpx binary exists on this host (verified: `npx --no-install acpx` reports the
  package is not installed). The committed role config therefore truthfully keeps acpx_binary null
  and the provenance gate fails closed on it. A Phase D real local smoke additionally requires a
  separately gated prompt materialization step (the seam request deliberately carries prompt=None).
  Real smoke must NOT be claimed until: an operator pins a verified local acpx executable in the
  role config, prompt materialization is separately approved, and the smoke runs with no Gateway,
  no delivery, no public ingress, and sanitized evidence only.
```

## Still Not Approved

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

## Next Decision After This Slice

The next request may be the Codex CLI primary review of this slice, then Hermes-owned PR/CI/merge, then a separately approved Phase D deterministic real local smoke (pinned binary + prompt materialization gate). None of those are started or approved by this document.
