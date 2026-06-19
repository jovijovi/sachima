# xAI Imagine API Refresh Dev Log

Date: 2026-06-19
Branch: `feat/xai-imagine-api-refresh`
Base: `release/sachima` at `142e7795e6dc9621ccfc3b81351d4f014c8c183a`
Worktree: `/home/ecs-user/workspace/hermes/worktrees/sachima/feat-xai-imagine-api-refresh`

## Scope

Refresh Sachima's bundled Hermes xAI image generation/editing provider against current official xAI Imagine API docs.

## Operator instruction

The operator approved a full PR development flow with PRD, full context, xAI official docs links, implementation, review, PR, and Claude Code main-programmer run with at least 100 turns and max reasoning effort.

## Preflight evidence

- Canonical checkout: `/home/ecs-user/workspace/hermes/repo/sachima`.
- Base branch: `release/sachima`.
- Base head at worktree creation: `142e7795e6dc9621ccfc3b81351d4f014c8c183a`.
- Remote convention verified:
  - `origin` -> `NousResearch/hermes-agent`
  - `sachima` -> `jovijovi/sachima`
- `gh auth status` succeeded for `jovijovi` with repo/workflow scopes; secret value not recorded.
- No matching open xAI/image/Imagine/grok PRs were found at preflight.
- Worktree created: `/home/ecs-user/workspace/hermes/worktrees/sachima/feat-xai-imagine-api-refresh`.
- CodeGraph initialized in the feature worktree and reported up-to-date.
- `python3 tools/sync_roadmap_status.py --check` reported the machine status block is up to date.

## Baseline focused tests

Before implementation, the existing focused xAI/edit tests passed:

```text
uv run --frozen pytest tests/plugins/image_gen/test_xai_provider.py tests/tools/test_image_edit_tool.py -q -o 'addopts='
44 passed
```

## PRD / context pack

Main PRD path:

- `docs/plans/2026-06-19-xai-imagine-api-refresh-prd.md`

It contains:

- official xAI docs links;
- official API facts extracted on 2026-06-19;
- current Sachima implementation summary;
- gap analysis;
- explicit in-scope / out-of-scope boundaries;
- functional requirements FR1-FR10;
- TDD implementation task plan;
- Claude Code run contract;
- Codex review contract;
- PR closeout requirements.

## Implementation evidence

### Approach

RED tests for FR1-FR10 were already present in the worktree
(`tests/plugins/image_gen/test_xai_provider.py`, +578 lines; and the
`_FakeEditProvider.edit` fixture signature in
`tests/tools/test_image_edit_tool.py`). The focused run confirmed RED first
(**51 failed, 104 passed**), then implementation was added to drive them GREEN.

### Files changed

- `plugins/image_gen/xai/__init__.py` — the only production source change.
- `tests/plugins/image_gen/test_xai_provider.py` — pre-supplied RED tests
  (not authored in this implementation pass; satisfied by the code change).
- `tests/tools/test_image_edit_tool.py` — pre-supplied fixture-signature
  update (`edit(... image=None, *, images=None ...)`) so the fake provider
  matches the new provider contract.
- `docs/dev_log/2026-06-19-xai-imagine-api-refresh.md` — this log.

`agent/image_gen_provider.py`, `tools/image_generation_tool.py`, and
`tools/image_edit_tool.py` were inspected and left unchanged: the FAL tool
schema test pins the agent surface to `prompt` + `aspect_ratio` (3-value enum)
and keeps `image` required, so the new options stay provider-local and
reachable by direct/provider callers, not widened into the agent schema.

### FR mapping (all provider-local in `plugins/image_gen/xai/__init__.py`)

- FR1 — `DEFAULT_MODEL = "grok-imagine-image-quality"`; catalog lists quality
  first (so `default_model()` returns it); `grok-imagine-image` stays
  selectable; deprecated `grok-imagine-image-pro` is absent from the catalog,
  so unknown/deprecated ids soft-fall back to quality via `_resolve_model()`.
- FR2 — new `_resolve_xai_aspect_ratio()` maps Hermes aliases and the official
  wire ratios (`1:1`,`4:3`,`16:9`,`9:16`,`20:9`,`9:19.5`,`auto`, ...); invalid
  input soft-falls back to `16:9`. `_echo_aspect_ratio()` keeps the caller's
  alias in the result (backward-compat) independent of the wire value.
- FR3 — optional positive-int `n` added to the payload; new
  `_extract_and_cache_images()` processes every `data[i]`; first output stays
  in `result["image"]`; all outputs reported in `result["images"]` when >1.
- FR4 — single-image URL/data-URI input keeps the JSON object shape
  `{"url": ..., "type": "image_url"}`; no top-level `image_url`; no OpenAI SDK.
- FR5 — `_build_xai_image_ref()` maps `file_...` ids to `{"file_id": ...}`
  (never probed on disk); empty `file_` rejected as `invalid_input`.
- FR6 — keyword-only `images=[...]` (max 3) builds `images: [...]`; `image`
  and `images` mutually exclusive; empty list / >3 / bad local path rejected
  as `invalid_input` before any network call.
- FR7 — `_validate_storage_options()` pass-through, default-off; requires
  `filename`; bounds `expires_after`/`public_url.expires_after` to
  3600..2592000; never injects `public_url` (privacy default preserved).
- FR8 — b64 saved with extension derived from `mime_type`
  (png/jpg/webp, else png); result preserves first-image `mime_type` /
  `file_output`, top-level `storage_error` / `public_url_error` / `usage`, and
  per-image `mime_type` / `file_output` in `images[*]`.
- FR9 — `service_tier` is never added to any payload (default-off; not
  implemented, so it is provably absent — covered by FR9 tests).
- FR10 — `result["image"]` first-output contract and the existing success
  keys are unchanged; all new metadata is additive via `success_response`
  `extra` (setdefault, never overwrites core keys).

## Review evidence

Pending (Codex primary repo-aware read-only review).

## Final verification

Required gate commands run from the worktree root (xAI scope GREEN):

```text
uv run --frozen pytest tests/plugins/image_gen/test_xai_provider.py \
  tests/tools/test_image_edit_tool.py tests/tools/test_image_generation.py \
  tests/tools/test_image_generation_plugin_dispatch.py -q -o 'addopts='
# 152 passed, 3 failed
#   - test_xai_provider.py ............................ all pass (FR1-FR10)
#   - test_image_edit_tool.py ........................ all pass
#   - test_image_generation_plugin_dispatch.py ....... all pass
#   - test_image_generation.py: 3 FAILED — pre-existing/environmental only

uv run --frozen python -m py_compile plugins/image_gen/xai/__init__.py \
  tools/image_edit_tool.py tools/image_generation_tool.py \
  agent/image_gen_provider.py            # exit 0

python3 tools/sync_roadmap_status.py --check
# docs/roadmap/current-status.md: machine status block is up to date

git diff --check                          # clean
```

### Pre-existing environmental failures (NOT in xAI scope, NOT caused by this change)

The 3 failures are all in the unmodified FAL test class
`tests/tools/test_image_generation.py::TestManagedGatewayErrorTranslation`
(`test_4xx_translates_to_value_error_with_remediation`, `test_5xx_is_not_translated`,
`test_non_http_exception_from_managed_bubbles_up`). They fail in
`tools.fal_common.import_fal_client` -> `tools.lazy_deps.ensure("image.fal")`,
before any FAL/xAI logic runs.

Evidence they are environmental and independent of this change:

- They failed identically in the RED baseline before any source edit.
- This change touches only `plugins/image_gen/xai/__init__.py`; the FAL path,
  `agent/image_gen_provider.py`, and the FAL test file are untouched.
- `fal_client` 0.13.1 imports fine and a fresh process resolves the feature
  (`feature_missing("image.fal") => ()`, `metadata.version("fal-client") =>
  0.13.1`), but under pytest the lazy-deps importability probe reports the
  package missing — a harness `importlib.metadata` resolution quirk
  (`VIRTUAL_ENV` points at `.hermes/.../venv` while `uv run` uses `.venv`).
- With this change stashed, the same FAL/OpenAI tests fail identically.

Out-of-scope sweep note: running the whole `tests/plugins/image_gen/`
directory also surfaces 6 OpenAI provider failures (`test_openai_provider.py`,
`test_openai_codex_provider.py`) on `is_available()` — these require
`OPENAI_API_KEY`/Codex credentials absent from this environment and are
likewise pre-existing (confirmed identical with this change stashed). They are
outside the required gate and outside this PR's scope.

### Secret/leak scan

Added source lines scanned for secret-shaped literals: none found. No API
keys, tokens, or raw logs added to code or this dev log.

## Claude Code run note

- First Claude invocation: `claude -p --model claude-opus-4-8[1m] --effort max --max-turns 100 --permission-mode acceptEdits` was stopped by Hermes after ~14 minutes with zero stdout, zero log bytes, and no file edits beyond pre-existing PRD/dev-log artifacts. It spawned project/user MCP helpers and appeared idle in `ep_poll`; no implementation evidence was produced. Relaunching with safe-mode/no custom MCP and bypass permissions inside the isolated worktree.
- Relaunch (safe-mode, no custom MCP): main-programmer implementation completed.
  Followed TDD against the pre-supplied RED tests — confirmed RED
  (51 failed / 104 passed) before editing, then implemented FR1-FR10
  provider-locally in `plugins/image_gen/xai/__init__.py` to GREEN
  (152 passed in the four focused files; the only remaining failures are the
  3 pre-existing/environmental FAL lazy-deps tests documented above). No push,
  merge, service restart, profile/config edit, live xAI call, or production
  config write was performed; changes left in the worktree for Hermes to
  inspect/verify/commit, and for Codex primary review.

## Hermes verifier follow-up

Claude Code's implementation satisfied the xAI provider tests, but the required combined focused gate initially reported `152 passed, 3 failed` in `tests/tools/test_image_generation.py::TestManagedGatewayErrorTranslation`. The failures were on the FAL managed-gateway path, not xAI, and occurred before the mocked managed client was invoked because `_submit_fal_request()` eagerly loaded `fal_client` before deciding whether the managed gateway path was active.

Hermes applied a narrow gate-hygiene fix in `tools/image_generation_tool.py`: `_submit_fal_request()` now resolves the managed gateway first and only lazy-loads `fal_client` on the direct FAL path; the real managed path still loads `fal_client` inside `_get_managed_fal_client()`. This preserves production behavior while allowing tests that inject a managed client to avoid unrelated local `fal-client` metadata probes.

Verification after the follow-up fix:

```text
uv run --frozen pytest tests/tools/test_image_generation.py::TestManagedGatewayErrorTranslation -q -o 'addopts='
4 passed

uv run --frozen pytest tests/plugins/image_gen/test_xai_provider.py tests/tools/test_image_edit_tool.py tests/tools/test_image_generation.py tests/tools/test_image_generation_plugin_dispatch.py -q -o 'addopts='
155 passed

uv run --frozen python -m py_compile plugins/image_gen/xai/__init__.py tools/image_edit_tool.py tools/image_generation_tool.py agent/image_gen_provider.py
exit 0

python3 tools/sync_roadmap_status.py --check
docs/roadmap/current-status.md: machine status block is up to date

git diff --check
exit 0
```

## Codex primary review

Codex CLI was run as the repo-aware read-only primary reviewer after Hermes local gates.

```text
VERDICT: PASS
BLOCKERS:
- None.
```

Codex notes: roadmap preflight stayed clean; the PR does not claim P5/runtime/live/Gateway/Feishu/production scope; implementation matches the checked xAI docs for quality default, JSON edits, `file_id`, multi-image `images[]`, `storage_options`, and priority default-off behavior.
