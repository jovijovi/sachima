# Phase D Smoke Prerequisites Implementation — Dev Log

## 2026-06-12 — Slice opened

User approved preparing the Phase D smoke prerequisites only:

```text
批准准备 Phase D smoke prerequisites：实现并验证 pinned local acpx provenance、prompt materialization、
agent_run_supervisor 安装/固定方案；不执行真实 smoke，不启动 AGENT，不接入 Gateway/Feishu/live，
不写生产配置。遵循 AGENT 分工。
```

AGENT split: Hermes is PM/controller/verifier and owns git/PR; Claude Code is architect + main programmer + documentation engineer; Codex CLI is the independent primary reviewer.

Branch facts at start: `feat/phase-d-smoke-prerequisites` on `release/sachima` synced to PR #118 merge `b36dfb5f40d62334e94fbb2163eed4b9ee36abd6`; working tree clean; no open PRs against `release/sachima`; worktree-local CodeGraph initialized.

Host preflight facts (real environment preconditions, truthfully recorded, unchanged by this slice): `acpx` not on PATH; `agent_run_supervisor` not importable.

## 2026-06-12 — Architect / main programmer / docs pass (Claude Code)

### Roadmap preflight statement

- Current position: Phase C `exec_controlled` wrapper merged (PR #114); Phase D readiness gate docs-only merged (PR #117); real smoke BLOCKED on three provisioning prerequisites plus separate approval.
- Next allowed request: Definition-of-Ready provisioning / implementation planning for Phase D smoke — exactly this slice.
- Explicit non-approvals preserved: no smoke, no AGENT, no `acpx`/`npx`, no Gateway/Feishu/live, no production config.
- Open tails checked: `ROADMAP-NEXT-ARS-CTRL-EXEC-REAL-SMOKE` stays open/BLOCKED.

### Inputs read (read-only context)

`AGENTS.md`, `GOAL.md`, `docs/roadmap/current-status.md`, the Phase D readiness PRD / architecture packet / user review packet / manifest / dev log, `sachima_supervisor/activity_controlled_exec.py`, `sachima_supervisor/local_offline.py`, `sachima_supervisor/activity_evidence.py`, the committed role config, and the existing controlled-exec / local-offline test suites.

### Implemented (RED-first; new tests written and observed failing before code landed)

1. **Pinned local acpx provenance layer** — `verify_pinned_local_acpx_binary(...)` + `PinnedLocalAcpxProvenance` + `FORBIDDEN_RUNNER_BASENAMES` in `sachima_supervisor/activity_controlled_exec.py`. Absolute whitespace-free path; fetch/shell runner basenames rejected; regular-executable proof; executable sha256; **injected** version probe returning sanitized bounded single-line text containing the exact `0.10.0` pin; `expected_version` must equal `_REQUIRED_ACPX_VERSION`. Every miss fails closed as stable `activity_runner_provenance_unverified` with no raw detail. The module never executes the binary; tests use fake probes and fake binaries only. The committed role config stays `acpx_binary: null` and untouched. `.gitignore` now guards `sachima_supervisor/roles/local/` so future untracked local-only role overlays can never be committed.
2. **Prompt materialization layer** — new `sachima_supervisor/smoke_prompt.py` (`build_phase_d_smoke_prompt`, `materialize_phase_d_smoke_prompt`, stable ref/digest, safety-screened bounded read-only prompt) mirrored byte-for-byte by `tests/fixtures/sachima_supervisor/phase_d_smoke_prompt.v1.txt`; `start_controlled_local_exec(...)` gains an explicit `prompt_materializer` keyword (default `None` keeps Phase C `prompt=None`); materialization runs only after the acquired atomic pre-launch claim and before the single supervisor call; failed/unsafe materialization finalizes `failed_terminal` with stable `activity_prompt_materialization_failed` and zero supervisor invocations; raw prompt never enters durable claim state, fingerprints, or query projections (`_CLAIM_STATE_KEYS` unchanged); replay never rematerializes or relaunches.
3. **agent_run_supervisor install/pin layer** — new `sachima_supervisor/supervisor_library.py` with `check_supervisor_library_pin(...)` / `SupervisorLibraryPinStatus`; expected exact pin `0.0.0` (current agent-run-supervisor repo pyproject version); stable fail-closed codes; unsanitary observed versions dropped, never echoed; injected probes in tests. Deliberately **not** added to `pyproject.toml` — install/pin remains an operator provisioning step under the repo exact-pin dependency policy, validated at smoke time by this checker.

### Environment note (honest)

Neither the system `python3` nor the shared hermes venv on this host carries `pytest`; tests were run with a sibling Sachima worktree's Python 3.11 virtualenv (pytest 9.0.2), verified to resolve `sachima_supervisor` imports to **this** worktree before use.

### Verification (local, safe)

```text
python -m pytest -q tests/sachima_supervisor/        # 304 passed (baseline for the four
                                                     # pre-existing target files was 205)
python3 -m compileall -q sachima_supervisor tests/sachima_supervisor
git diff --check                                     # clean
static scans over changed files                      # no forbidden execution/delivery surface,
                                                     # no smoke-run claim, no Gateway/Feishu/live/
                                                     # production-config approval, no secrets or
                                                     # host-private paths committed
```

No real smoke, no AGENT launch, no `acpx`/`npx`/product-path `codex`/`claude` invocation, no network fetch, no Gateway/Feishu/IM/live surface, no service/runtime start, and no production config write occurred. Git/PR/merge remain Hermes-owned; Codex primary review is pending.

## 2026-06-12 — Codex blocker-only review round 1: BLOCK → narrow fixes (Claude Code)

Fresh-context Codex CLI blocker-only review returned **BLOCK** with two blockers, both confirmed against the source and fixed with minimal, scope-preserving changes (RED-first: the new negative tests were observed failing — every lookalike passed the old gates — before the fix landed).

1. **Exact version token, not substring** — `verify_pinned_local_acpx_binary(...)` checked `expected_version not in probe_text`, so `acpx 10.10.0` (contains `0.10.0` as a substring) and pre-release/build variants like `acpx 0.10.0-dev` wrongly satisfied the `0.10.0` pin. Fix: new `_probe_text_has_exact_version(...)` requires the pinned version as a standalone token (regex with version-extending boundary class `[A-Za-z0-9._+-]` on both sides); probe text stays sanitized/bounded/single-line with no raw detail on failure. New negative tests cover `10.10.0`, `00.10.0`, `0.10.01`, `0.10.0.1`, `0.10.0-dev`, `0.10.0-rc.1`, `0.10.0rc1`, `0.10.0+build.5`; new positive tests pin exact-token acceptance (`acpx 0.10.0`, `acpx/0.10.0`, bare `0.10.0`).
2. **Shared forbidden-runner predicate at the launch gate** — `_check_runner_provenance()` (the actual `start_controlled_local_exec` gate) only rejected `npx`-prefixed basenames, while the standalone verifier rejected the full `FORBIDDEN_RUNNER_BASENAMES` set; a future role overlay with `acpx_binary: /usr/bin/node` or `/usr/local/bin/npm` could have passed the launch gate. Fix: new shared `_is_forbidden_runner_basename(...)` (case-insensitive set membership + `npx`-prefix rule) now backs **both** the launch gate and the standalone verifier. New start-path failure tests prove `/usr/bin/node`, `/usr/local/bin/npm`, `/usr/local/bin/pnpm`, `/usr/bin/yarn`, `/usr/local/bin/bunx`, `/bin/sh`, `/bin/bash`, `/usr/bin/env`, and uppercase `/usr/local/bin/NPM` all fail closed (`activity_runner_provenance_unverified`, zero supervisor invocations, no claim written).

### Verification after fixes (local, safe)

```text
python -m pytest -q tests/sachima_supervisor/        # 325 passed (was 304 before this round;
                                                     # +21 review-fix tests, all observed RED first)
python3 -m compileall -q sachima_supervisor tests/sachima_supervisor
git diff --check                                     # clean
```

Scope unchanged: still prerequisites preparation only — no real smoke, no AGENT launch, no `acpx`/`npx` invocation, no Gateway/Feishu/live, no production config. Codex blocker-only re-review returned `VERDICT: PASS` / `BLOCKERS: None`.

## 2026-06-12 — Codex blocker-only re-review: PASS

Fresh-context Codex CLI re-reviewed only the two round-1 blockers plus the narrow fixes. It confirmed:

- exact version gate now uses standalone version-token matching and rejects substring/suffix/pre-release/build lookalikes;
- `_check_runner_provenance()` and `verify_pinned_local_acpx_binary()` share `_is_forbidden_runner_basename(...)`;
- start-path tests run through `start_controlled_local_exec()` and assert zero supervisor invocation / no claim write for forbidden runner basenames;
- scope remains prerequisites-only: no smoke, no AGENT, no `acpx`/`npx`, no Gateway/Feishu/live, no production config.

Codex reported it personally ran a targeted filtered test (`29 passed, 156 deselected`), the full `tests/sachima_supervisor/` suite (`325 passed`), and `git diff --check` (clean). The checksum guard excluding `.git`/`.codegraph` showed no repo-file modification during the re-review.
