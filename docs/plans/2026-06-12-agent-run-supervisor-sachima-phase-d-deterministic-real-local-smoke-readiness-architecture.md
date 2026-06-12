# Phase D Deterministic Real Local Smoke — Readiness Architecture Packet

> **Status: docs-only readiness design.** This packet defines how a *separately approved* later branch could move from the Phase C wrapper to exactly one deterministic real local smoke. It does **not** approve or run a smoke, start any real AGENT, invoke `acpx`, fetch via `npx`, touch Gateway/Feishu/live delivery, or write production configuration. Everything below is a design constraint for a future gate, not an action taken here.

## 1. Scope and role

Architect / documentation-engineer pass over the readiness gate that Hermes opened with the Phase D PRD. Claude Code began this pass but hit a session-limit / 429 error after partial docs edits; Codex CLI is substituting for the architecture/docs authoring role here. This is **not** the fresh-context Codex primary review, which remains a separate later review gate. This packet:

- turns the PRD's two readiness schemes (pinned local `acpx_binary`; prompt materialization) into a real, code-grounded design;
- defines the exact smoke request construction boundary, sanitized evidence shape, replay / no-duplicate-launch proof, rollback/cleanup, and the test/probe plan for the later execution branch;
- records the Definition-of-Ready gate every future smoke must pass before launch.

It is anchored to the merged Phase C surface (`sachima_supervisor/activity_controlled_exec.py`, PR #114) and the local/offline seam (`sachima_supervisor/local_offline.py`). It changes no code.

## 2. What Phase C already guarantees (do not re-litigate)

The smoke design inherits, unchanged, every fail-closed gate already merged in `start_controlled_local_exec(...)`:

| Guarantee | Phase C mechanism |
|---|---|
| Default-off + exact approval | `_check_enabled_and_approved` against `CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN` |
| One mode only | `_check_mode` → `exec_controlled` only |
| One runnable role | `CONTROLLED_EXEC_ROLE_ALLOWLIST` = `{sachima.codex.primary_reviewer}` |
| No raw material | `_check_material` + `_value_is_unsafe` + `_has_exec_unsafe_marker` |
| Operator gate | `_check_operator_gate` (`operator_gate is True`) |
| Prior evidence digest | `_check_prior_evidence_digest` == `build_controlled_local_dry_run_evidence()["fixture_digest"]` |
| Preflight / lease / state-version binding | `_check_preflight_binding` against the PR #107 record |
| Pinned no-fetch runner provenance | `_check_runner_provenance` (role-file sha256 + non-null absolute non-`npx` binary) |
| Read-only Codex one-shot capability | `_check_role_capability` |
| Atomic pre-launch claim/CAS | `ControlledLocalExecClaimStore.claim` (single mutex; exactly one acquire) |
| Sanitized durable state only | `_validate_claim_state_projection` over `_CLAIM_STATE_KEYS` |
| `business_verdict` permanently null | enforced in `_build_claim_state` and validate-on-read |

The smoke does **not** weaken any of these. It supplies two wrapper-level inputs (a pinned binary and a materialized prompt) **plus** requires a pinned/importable `agent_run_supervisor` library on the host; only then may a later approved branch prove the end-to-end path once, with sanitized evidence.

## 3. Current provisioning reality (verified 2026-06-12, this worktree)

Read-only preflight on this host (no agent/runtime invoked):

```text
acpx                      : not found on PATH
codex                     : present on PATH
claude                    : present on PATH
npx                       : present on PATH (FORBIDDEN fetch path; see §5)
agent_run_supervisor (py) : NOT installed in any interpreter on this host
```

This yields **three independent execution blockers**, not two. A real smoke is impossible — and must not be claimed — until all three are resolved by an operator under a separate approval:

1. **No pinned local `acpx` binary.** The committed role config truthfully keeps `runner.acpx_binary: null`, so `_check_runner_provenance` fails closed with `activity_runner_provenance_unverified`.
2. **No prompt materialization.** `_build_local_offline_request(...)` hardcodes `prompt=None`; even fully wired, the supervisor caller boundary fails closed on an empty exec prompt.
3. **Supervisor library absent.** `agent_run_supervisor` is not importable, so `invoke_local_offline_supervisor` → `_resolve_spec_factory` / `_resolve_invoke_caller` would raise `supervisor_library_unavailable`. The Phase C test suite passes only because it injects a fake supervisor; a *real* smoke needs the real library installed (pinned per the repo dependency policy).

> Blocker (3) was new information surfaced by the architecture/docs pass. It is now recorded here, in the PRD, in the manifest blockers, in the user review packet, in the dev log, and in roadmap status so the operator sees the full provisioning surface before approving.

## 4. Pinned local `acpx_binary` provisioning and provenance verification

### 4.1 Operator provisioning (out of band, pre-smoke)

Before any smoke branch is opened, an operator must, on the smoke host:

1. Obtain a specific `acpx` build through an auditable channel (vendored release artifact or pinned install), **never** an at-invocation network fetch.
2. Record the binary's own provenance out of band: absolute path, a `sha256` of the executable file, and the sanitized text of a deterministic `acpx --version` probe. (`acpx --version` is the only `acpx` call allowed during provisioning — it must not start an agent. It stays out of scope for *this* readiness gate, which runs no `acpx` at all.)
3. Confirm the build matches the role's pinned `runner.acpx_version` (`0.10.0`, `_REQUIRED_ACPX_VERSION`).

### 4.2 In-gate provenance verification (already enforced by `_check_runner_provenance`)

At smoke time the existing gate re-derives trust from the role file and request — no new trust path is introduced:

- request carries `role_file_digest` matching `^sha256:[0-9a-f]{64}$`;
- the on-disk role file's actual `sha256` equals that digest (tamper-evident binding);
- role JSON parses, `runner.type == "acpx"`, `runner.acpx_version == "0.10.0"`;
- `runner.acpx_binary` is a **non-empty, absolute (`/`-rooted), whitespace-free** string whose basename does **not** start with `npx`;
- read-only capability holds (`_check_role_capability`: `read`/`search` true; `write/execute/terminal/delete/move/fetch/switch_mode/other` false; `adapter_agent == "codex"`; session strategy `exec`).

Any miss → `activity_runner_provenance_unverified` / `activity_role_capability_rejected`, fail-closed, before the claim and before any supervisor call.

## 5. Why `npx` / network fetch stays forbidden

`npx` (or any package-runner basename) is rejected structurally, and the rejection is load-bearing for three reasons:

1. **Not strict-offline.** `npx`/null-binary lets the supervisor library fall back to a network-fetching package-runner prefix. A run that fetches at invocation time cannot produce no-fetch offline evidence — the central claim of this phase line.
2. **Supply-chain surface.** A fetch-at-launch runner reintroduces exactly the attack surface the repo dependency-pinning policy was written to close (post-litellm, post–Mini Shai-Hulud worm): floating, unpinned, network-resolved executables. The pinned-path + sha256 model is the offline analogue of the repo's "commit-SHA / exact-pin" rule.
3. **Non-determinism.** A deterministic smoke requires a fixed binary at a fixed path with a recorded digest. A fetched runner is not reproducible across runs or hosts.

The gate enforces this two ways: a null `acpx_binary` fails closed (the committed config is null by design), and a non-null basename starting with `npx` fails closed. The forbidden-surface test additionally asserts the module source carries no `npx -y` / fetch tokens.

## 6. Committed role JSON must not carry host-local paths — use a local-only overlay

**Decision: committed role JSON stays portable and non-runnable. Prefer NO host-local path in committed source.**

The committed `sachima_supervisor/roles/codex_primary_reviewer_exec_controlled_v1.json` keeps `acpx_binary: null` and uses the portable placeholder `/workspace/sachima` for `workspace.default_cwd` / `allowed_roots`. A real host path such as `/home/<user>/.local/bin/acpx` is host-private and must never land in committed source: it leaks host layout, is wrong on every other checkout, and would make the committed config falsely "runnable."

The Phase C API already supports the clean alternative: `start_controlled_local_exec(..., role_root=...)`. The smoke design is therefore a **local-only generated role overlay**:

- A future smoke branch (or operator step) generates an **untracked** overlay role file — e.g. under a gitignored `sachima_supervisor/roles/local/` or under the runtime/runs dir — that is byte-identical to the committed role **except** `runner.acpx_binary` is set to the verified absolute local path.
- The smoke passes `role_root` (and the allowlist-relative ref) so the gate reads the overlay; the request's `role_file_digest` is the `sha256` of the overlay.
- The committed config is never mutated. `git status` stays clean of host paths; the overlay is `.gitignore`d and removed at cleanup (§10).
- This keeps the digest-binding model intact (the gate still verifies the on-disk file matches the request digest) while keeping host-private data out of version control and out of the PR payload.

No production config write occurs: the overlay is a local fixture, not a config the Gateway or any service reads.

## 7. Prompt materialization scheme

Phase C deliberately sends `prompt=None`. Phase D needs a deterministic, bounded, harmless prompt — and a digest — without ever letting raw material into durable state.

### 7.1 Source and builder

- **Source:** a small repo-controlled fixture or a deterministic builder, mirroring the existing `build_controlled_local_dry_run_evidence()` pattern (a versioned fixture with a stable digest). Suggested: `tests/fixtures/sachima_supervisor/phase_d_smoke_prompt.v1.txt` plus a `build_phase_d_smoke_prompt()` returning `{ "prompt": <str>, "prompt_digest": "sha256:..." }`.
- **NOT a source:** raw IM text, card JSON, media bytes/paths, tool output, Gateway payload, environment dumps, credentials, platform ids, callback URLs, or local paths.

### 7.2 Content rules

- Read-only and harmless: instructs the Codex reviewer to inspect a tiny in-repo fixture and return a fixed `VERDICT: PASS`-shaped summary (matches the role's `output_contract`).
- Bounded length; deterministic bytes; passes `_value_is_unsafe` and the `_EXEC_UNSAFE_MARKERS` (`media_path`/`raw_prompt`/`prompt_body`) screens.
- The materialized string is the only place real prompt text exists; it is **never** written to durable claim state. The claim state has no prompt field — only `prompt_ref` (a claim-check ref) and digests survive in `_CLAIM_STATE_KEYS`.

### 7.3 Where it enters

The current Phase C code builds the seam request only **after** an acquired atomic pre-launch claim:

```text
gates -> role provenance -> claim/CAS -> _build_local_offline_request(...) -> invoke_local_offline_supervisor(...)
```

Therefore the narrowest future implementation is a materialization-aware variant of `_build_local_offline_request(...)`: it loads/builds the deterministic prompt only after the claim is acquired and before `invoke_local_offline_supervisor(...)`. The request still carries only `prompt_ref` / digest-safe claim-check refs into the claim and fingerprint; raw prompt text never enters durable claim state. If a future implementer wants to materialize before the claim, that is a different construction boundary and must be explicitly reviewed and tested.

## 8. Exact smoke request construction boundary

This is the single, precise change surface for the later execution branch. Today `_build_local_offline_request(...)` sets `prompt=None`; the smoke flips exactly that, behind the existing gates.

**`ControlledLocalExecRequest` field map for the one approved smoke:**

```text
enabled                        = True
approval_marker                : CONTROLLED_LOCAL_EXEC_APPROVAL_TOKEN   # exact Phase C approval marker
mode                           = "exec_controlled"
role_key                       = "sachima.codex.primary_reviewer"        # the only runnable role
prompt_ref                     = <claim-check ref for the materialized prompt>   # safe ref, not the text
preflight_activity_id          = <existing PR #107 durable-state preflight record>
lease_id / lease_epoch /
  lease_holder_ref             = <must equal the preflight record's lease>
expected_state_version         = <must equal the preflight record's state_version>
role_file_digest               = "sha256:" + sha256(local role overlay)   # §6
prior_dry_run_evidence_digest  = build_controlled_local_dry_run_evidence()["fixture_digest"]
operator_gate                  = True
activity_id / transaction_ref /
  operation_ref / idempotency_key = caller-owned safe refs
```

**Construction boundary (one supervisor call):**

- The Phase D branch first constructs a `ControlledLocalExecRequest` using only safe refs and digests, including `prompt_ref`.
- `start_controlled_local_exec(...)` runs every existing gate, verifies the overlay role via `role_root`, writes the atomic `claimed_in_progress` claim, and only then builds the seam request.
- A materialization-aware `_build_local_offline_request(...)` variant sets `prompt=<materialized>` (and may set `evidence_dir` for sanitized evidence capture, §9). It still carries `role=None`, `role_file=str(<overlay path>)`, `enabled=True`, the `LOCAL_OFFLINE_APPROVAL_TOKEN` approval marker, and `claim_check_refs=(transaction_ref, operation_ref, prompt_ref, *context_refs)`.
- `invoke_local_offline_supervisor(...)` is then called **exactly once** with the materialized seam request.
- No other entrypoint, mode, role, or boundary is touched. No Gateway, no delivery, no session, no cancel.

## 9. Sanitized evidence shape

Two sanitized surfaces, both no-leak by construction:

1. **Durable claim projection** — already defined by `_validate_claim_state_projection` over `_CLAIM_STATE_KEYS`: stable `type/status/mode/phase`, caller refs, `role_file_digest`, `prior_dry_run_evidence_digest`, `preflight_view_ref`, `approval_ref`, lease id/epoch/holder, `state_version`, attempt index/count, `supervisor_status`, `artifact_ref_count`, `evidence_ref` + `evidence_digest`, `business_verdict` (always `null`), `caller_verdict`, stable `error_code`, `retryable`, `view_model_ref`. No raw prompt/output/paths/exceptions.
2. **Out-of-PR smoke evidence record** — written via the seam's `evidence_dir` / `_write_evidence` path (the same sanitized view-model writer used by the offline seam), stored under the runtime outputs tree like prior PE-1D/PE-2A evidence, **not** in the PR payload unless a phase explicitly approves versioning it. It captures: sanitized host preflight (acpx absolute path digest, sanitized `acpx --version` text, overlay digest, prompt fixture digest), the claim disposition timeline (`acquired → completed`), the replay proof (§10), and the forbidden-surface scan result.

Hard rule: no raw stdout/stderr, no tool output, no raw prompt text, no host-private paths, no credentials, no Gateway/delivery data in either surface.

## 10. Replay / no-duplicate-launch proof

The atomic claim/CAS is already the duplicate-launch control point. The smoke must *demonstrate* it on the real path, with a supervisor-invocation counter:

1. First start → `claim` disposition `"acquired"`, **exactly one** supervisor invocation, terminal state `completed`.
2. Replay with the identical `idempotency_key` + identical fingerprint → disposition `"replayed"`, resident sanitized projection returned, **zero** second invocation (counter still 1).
3. (Optional, fail-closed) same `activity_id` / different key → `activity_claim_conflict`; same key / different fingerprint → `activity_idempotency_conflict`; both before any launch.

A crashed in-progress claim is never auto-relaunched (replay returns the resident `claimed_in_progress` projection). The proof artifact is the invocation counter equalling 1 across steps 1–2.

## 11. Rollback / cleanup

The slice is intentionally cheap to unwind:

- **Local role overlay** (§6): untracked and `.gitignore`d; delete after evidence capture. Never commit the host path; the committed config stays `acpx_binary: null`.
- **Claim store:** the first-slice store is in-process and ephemeral — there is no durable cross-process write to roll back. A re-run requires a fresh `activity_id` / `idempotency_key`, or it will (correctly) replay instead of launching.
- **Evidence:** sanitized records live outside the PR payload (§9); nothing raw is persisted.
- **No production surface touched:** no Gateway, no service, no config write, no delivery — so there is nothing to restart or revert there.
- **Worktree:** if a throwaway worktree is used, `codegraph uninit --force` then `git worktree remove` per the repo worktree rule.

## 12. Test / probe plan for the later execution branch

For the *future* execution branch (not run here), RED-first, sanitized, and CI-safe:

- **Materialization tests:** `build_phase_d_smoke_prompt()` is deterministic, bounded, passes `_value_is_unsafe` / `_EXEC_UNSAFE_MARKERS`, and yields a stable `prompt_digest`.
- **Overlay provenance tests:** a generated overlay with a real absolute path passes `_check_runner_provenance`; null/relative/whitespace/`npx`-basename variants fail closed; committed config still fails closed.
- **Construction-boundary tests:** the materialization-aware request builder sets `prompt=<materialized>` and still passes the boundary; `prompt=None` still fails closed at the seam.
- **Replay / no-duplicate-launch test** on the real path: invocation counter == 1 across an identical replay (§10).
- **Evidence no-leak test:** both evidence surfaces contain only `_CLAIM_STATE_KEYS`-shaped sanitized fields; assert absence of raw prompt/output/path/exception tokens.
- **Forbidden-surface scan:** unchanged from Phase C (no aiohttp/httpx/lark_oapi/feishu/webhook/temporalio/subprocess/docker/systemctl/os.system/popen/pexpect/`npx -y`/socket/requests/gateway/`codex exec`/`claude exec`).
- **Gated real-smoke probe:** the single real-`acpx` smoke runs **only** when an explicit env marker AND a pinned binary AND the installed `agent_run_supervisor` library are all present; it is skipped by default so CI and other hosts never launch an agent. The existing 229-test suite stays green.

## 13. Definition of Ready (gate for any future smoke)

A real smoke may be requested only when **all** hold; otherwise it stays blocked:

```text
[ ] operator has a verified pinned local acpx binary (absolute path + sha256 + sanitized --version)
[ ] local-only role overlay generated (untracked) with that path; committed config stays null
[ ] agent_run_supervisor library installed and pinned per the repo dependency policy
[ ] prompt materialization fixture/builder landed and approved (deterministic, bounded, no-leak)
[ ] a real PR #107 durable-state preflight record exists with a held lease + state version
[ ] separate, named user approval for the Phase D smoke (see PRD recommended text)
[ ] Codex primary review PASS on the smoke branch; local checks + CI green
[ ] evidence plan = sanitized only, out of PR payload; no Gateway/Feishu/live/public ingress
```

## 14. Non-approvals (unchanged, restated)

This packet does not approve or perform: real local smoke execution; real AGENT launch; `acpx` invocation; `codex`/`claude` invocation through `acpx`; `npx` fallback or network-fetch evidence; persistent sessions; cancellation execution; write-capable Claude/Codex roles; Satine/Hermes-profile ACP execution; controlled AI FLOW execution; Gateway involvement or mutation; Feishu/IM delivery; live/default-on behavior; public ingress; production durable runtime code; production config writes; service restarts/reloads; platform adapter mutation.

## 15. Review gates (AGENT split)

- **Claude Code (architecture/docs):** attempted, then interrupted by session-limit / 429 after partial docs edits.
- **Codex CLI (architecture/docs substitute):** completing this packet in the architecture/docs authoring role (docs-only), under the same no-smoke/no-agent/no-acpx boundary.
- **Codex CLI (primary review):** fresh-context review first returned `VERDICT: BLOCK` on two docs consistency issues; after narrow fixes, blocker-only re-review returned `VERDICT: PASS / BLOCKERS: None`.
- **User (Dog Brother):** approval of the next phase via the PRD's recommended approval text — **pending**, after Codex PASS.
