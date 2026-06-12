# agent-run-supervisor × Sachima Phase D Smoke Prerequisites — Implementation

> **Status: prerequisites preparation only.** This slice implements and verifies the three Phase D smoke *prerequisite layers* defined by the merged readiness gate (PR #117): pinned local `acpx` provenance verification, deterministic prompt materialization, and the `agent_run_supervisor` install/pin checker. It does **not** run a smoke, start any AGENT, invoke `acpx`/`npx`/`codex`/`claude` through any product path, touch Gateway/Feishu/IM/live delivery, or write production configuration. Real smoke execution remains separately blocked and separately approved.

## Approval captured for this slice

User approval, 2026-06-12:

```text
批准准备 Phase D smoke prerequisites：实现并验证 pinned local acpx provenance、prompt materialization、
agent_run_supervisor 安装/固定方案；不执行真实 smoke，不启动 AGENT，不接入 Gateway/Feishu/live，
不写生产配置。遵循 AGENT 分工。
```

AGENT split: Hermes is PM/controller/verifier and owns git/PR; Claude Code is architect + main programmer + documentation engineer for this slice; Codex CLI performs the independent primary review.

## Baseline

- Phase C controlled local exec wrapper merged in PR #114 (`21d1bafc22c6fcde2bb0af6fff6becfb0886cf4f`).
- Phase D deterministic real local smoke readiness gate (docs-only) merged in PR #117 (`eb7227301d715b40d4eb6628bf32fb800017bd42`).
- `release/sachima` synced to PR #118 merge `b36dfb5f40d62334e94fbb2163eed4b9ee36abd6` at branch start; no open PRs against `release/sachima`.
- Host preflight facts (unchanged, truthfully recorded): `acpx` not on PATH; `agent_run_supervisor` not importable. These are real environment preconditions, not failures — both stay operator-provisioning blockers for any later smoke.

## 1. Pinned local acpx provenance preparation layer

`sachima_supervisor/activity_controlled_exec.py` adds:

- `PinnedLocalAcpxProvenance` — frozen dataclass carrying only the verified absolute path, the executable's `sha256:` digest, the exact pinned version, and sanitized single-line probe text.
- `verify_pinned_local_acpx_binary(binary_path, *, version_probe, expected_version=_REQUIRED_ACPX_VERSION)`:
  - `expected_version` must equal `_REQUIRED_ACPX_VERSION` (`0.10.0`) or the check fails closed before anything else.
  - Path shape: must be a `str`, absolute (`/`-rooted), whitespace-free.
  - Basename: rejected when in `FORBIDDEN_RUNNER_BASENAMES` (`npx`, `npm`, `pnpm`, `yarn`, `bunx`, `bun`, `corepack`, `sh`, `bash`, `zsh`, `dash`, `ksh`, `fish`, `env`, `node`) or when `npx`-prefixed — fetch-shaped package runners and shell launchers can never be a pinned local binary.
  - File proof: must exist as a regular file and be executable; the executable bytes are hashed to `sha256:<hex>`.
  - Version/provenance proof: the **injected** `version_probe` callable is invoked with the path; its output must be a bounded, printable, single-line string that passes the existing unsafe-material screens and contains the exact pinned version. The module itself never executes the binary; producing real probe text is an out-of-band operator step under a later approval.
  - Every miss raises the stable `activity_runner_provenance_unverified` code with no raw exception/probe detail.
- The committed role config `sachima_supervisor/roles/codex_primary_reviewer_exec_controlled_v1.json` is untouched: `acpx_binary` stays `null`, portable, and fail-closed/not runnable by construction. No host-local path enters git.
- `.gitignore` now ignores `sachima_supervisor/roles/local/` so a future untracked local-only role overlay (readiness architecture §6) can never be committed.

## 2. Prompt materialization preparation layer

New module `sachima_supervisor/smoke_prompt.py` plus fixture `tests/fixtures/sachima_supervisor/phase_d_smoke_prompt.v1.txt`:

- `build_phase_d_smoke_prompt()` returns a deterministic payload: `type`, claim-check-safe `prompt_ref` (`phase_d_smoke_prompt_v1`), the bounded read-only `prompt` text, `prompt_sha256` digest, `prompt_chars`, and the mirrored fixture path. No timestamps, no randomness; the committed fixture mirrors the canonical in-code prompt byte-for-byte (the `build_controlled_local_dry_run_evidence` pattern).
- The prompt is harmless and bounded: it asks a read-only reviewer to inspect one committed JSON fixture and answer with a fixed `VERDICT:`-shaped summary. It contains no raw IM/card/media/tool/Gateway material, no environment dumps, no credentials, no platform ids, no callback URLs, and no host-private paths, and it passes the boundary unsafe-material screens. A drifted prompt fails the builder's own safety screen closed.
- `materialize_phase_d_smoke_prompt(request)` is a seam-shaped materializer that returns the builder prompt; nothing wires it in by default.

`sachima_supervisor/activity_controlled_exec.py` seam change:

- `start_controlled_local_exec(...)` gains an explicit `prompt_materializer` keyword (default `None`).
- Default path is byte-for-byte Phase C behavior: the seam request keeps `prompt=None`, so the supervisor caller boundary still fails closed on an empty exec prompt and no agent run can start.
- With an injected materializer, materialization happens **only after** the atomic pre-launch claim is resident and **before** the single `invoke_local_offline_supervisor(...)` call, exactly at the construction boundary fixed by the readiness architecture (§7.3/§8). The screened prompt exists only in the in-memory seam request.
- Raw prompt text never enters durable claim state, fingerprints, or query projections: `_CLAIM_STATE_KEYS` is unchanged and the projection validator still rejects any extra key.
- A raising materializer or non-string/empty/oversized/unsafe output finalizes the claim as a sanitized terminal failure with the stable code `activity_prompt_materialization_failed` and **zero** supervisor invocations. The durable-state projection validator accepts that code only on `failed_terminal` states; `failed_retryable` still requires the existing `activity_supervisor_failed` collapse code.
- Replay semantics are preserved and extended: an identical replay of an in-progress or terminal claim returns the resident projection without a second launch *and without a second materialization*; conflicting replays still fail closed pre-launch.

## 3. agent_run_supervisor install/pin preparation layer

New module `sachima_supervisor/supervisor_library.py`:

- `check_supervisor_library_pin(*, expected_version=EXPECTED_AGENT_RUN_SUPERVISOR_VERSION, import_probe=None, version_probe=None)` returns a frozen `SupervisorLibraryPinStatus` (`importable`, `version_pinned`, `expected_version`, `observed_version`, `error_code`, `ready`).
- Expected exact pin is `0.0.0`, matching the current agent-run-supervisor repo `pyproject.toml` version.
- Fail-closed checker, never raises: stable codes `supervisor_library_expected_version_invalid` (before any probe), `supervisor_library_unavailable` (import fails), `supervisor_library_version_unknown` (metadata missing/unsanitary — the raw value is dropped, never echoed), `supervisor_library_version_mismatch`.
- Probes are injectable; default probes use `importlib` only. Nothing is installed, fetched, or executed.
- **Deliberately not a dependency:** `agent-run-supervisor` is *not* added to this repo's `pyproject.toml`. Installing and pinning it on the smoke host is an operator provisioning step under the repo exact-pin dependency policy, validated at smoke time by this checker. This avoids coupling every checkout to a library only one future approved smoke needs.

## 4. What this slice does NOT change

- No real smoke, no AGENT launch, no `acpx`/`npx` invocation, no network fetch.
- No Gateway/Feishu/IM/live/public-ingress surface, no production config write, no service restart/reload, no platform adapter mutation.
- Committed role config stays `acpx_binary: null`; no host-local path, secret, token, credential, or raw log enters the repo.
- `pyproject.toml` unchanged.
- Existing Phase C gates, claim/CAS semantics, sanitized state keys, and `business_verdict ≡ null` are unchanged.

## 5. Execution blockers that remain (unchanged posture)

A real Phase D smoke remains blocked until **all** Definition-of-Ready items hold (readiness architecture §13), including:

1. an operator-verified pinned local `acpx` executable on the smoke host (this slice ships the verifier, not the binary);
2. an untracked local-only role overlay carrying that path (this slice ships only the `.gitignore` guard);
3. `agent_run_supervisor` installed/pinned on the host (this slice ships the checker, not the installation);
4. a separate, named user approval for the smoke itself, plus fresh review/CI.

## 6. Verification run for this slice

```text
python -m pytest -q tests/sachima_supervisor/   (sibling-worktree Python 3.11 venv; includes
  test_activity_controlled_exec.py, test_local_offline.py,
  test_activity_controlled_dry_run_evidence.py, test_activity_durable_state_preflight.py,
  test_activity.py, test_smoke_prompt.py, test_supervisor_library.py)
python3 -m compileall -q sachima_supervisor tests/sachima_supervisor
git diff --check
static scans over changed files (no forbidden execution/delivery surface, no smoke-run claim,
  no Gateway/Feishu/live/production-config approval claim, no secrets/host-private paths)
```

## 7. Non-approvals (restated, unchanged)

```text
real_local_smoke_execution
real_agent_process_launch
acpx_invocation
codex_or_claude_invocation_through_acpx
npx_fallback_or_network_fetch_evidence
persistent_session_execution
cancellation_execution
write_capable_claude_or_codex_roles
satine_or_hermes_profile_acp_execution
controlled_ai_flow_execution
gateway_involvement_or_mutation
feishu_or_im_delivery
live_or_default_on_behavior
public_ingress
production_durable_runtime_code_implementation
production_config_write
service_restart_or_reload
platform_adapter_mutation
```
