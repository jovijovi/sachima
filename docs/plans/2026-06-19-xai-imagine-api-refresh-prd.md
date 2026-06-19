# xAI Imagine API Refresh PRD and Implementation Plan

Date: 2026-06-19
Status: **Implementation approved by operator for this PR**
Branch: `feat/xai-imagine-api-refresh`
Base: `release/sachima` at `142e7795e6dc9621ccfc3b81351d4f014c8c183a`
Worktree: `/home/ecs-user/workspace/hermes/worktrees/sachima/feat-xai-imagine-api-refresh`

> For Hermes: use the governed Sachima role split. Hermes is PM/controller/verifier/repo operator. Claude Code is the main programmer and must be invoked with `--effort max` and `--max-turns 100` for this task. Codex CLI is the primary repo-aware read-only reviewer before PR approval.

## Scope of this artifact

This PRD defines a local code/test/docs implementation PR to refresh Sachima's bundled Hermes xAI image generation and image editing provider against the current official xAI Imagine API documentation.

The operator requested:

```text
制定PRD及详细要求、目标、提供完整上下文（含xAI的官方文档链接、你的结论）。走完整PR的开发流程。Claude Code 至少给100 turn、推理强度max。
```

This is implementation approval for the scoped repository change below. It does **not** authorize live API spending, Gateway restart/reload, profile config mutation, production config writes, Feishu live delivery tests, public URL publication for private user media, or any runtime rollout.

## Authority and baseline

Authority and live truth checked before drafting:

- `AGENTS.md` — worktree rule, CodeGraph rule, roadmap/non-approval rules.
- `GOAL.md` — Sachima final compass and live/prod non-approval boundaries.
- `docs/roadmap/current-status.md` — machine block checked by `python3 tools/sync_roadmap_status.py --check`; machine status is up to date. This xAI provider PR is not a P5 runtime/FlowWeaver phase claim.
- GitHub remote convention: `sachima` remote points to `jovijovi/sachima`; PRs target `release/sachima`.
- Preflight state:
  - canonical checkout clean on `release/sachima`;
  - `sachima/release/sachima` fetched and equals local base `142e7795e6dc9621ccfc3b81351d4f014c8c183a`;
  - no open PRs whose title/head matched xAI/image/Imagine/grok at preflight;
  - worktree created at `/home/ecs-user/workspace/hermes/worktrees/sachima/feat-xai-imagine-api-refresh`;
  - CodeGraph initialized in that exact worktree, status clean/up-to-date.

## Official xAI documentation sources

Use these official sources as the product/API authority for this PR:

1. Imagine Overview  
   https://docs.x.ai/developers/model-capabilities/imagine
2. Image Generation  
   https://docs.x.ai/developers/model-capabilities/images/generation
3. Image Editing  
   https://docs.x.ai/developers/model-capabilities/images/editing
4. Multi-Image Editing  
   https://docs.x.ai/developers/model-capabilities/images/multi-image-editing
5. REST API Reference — Images  
   https://docs.x.ai/developers/rest-api-reference/inference/images
6. Imagine Files API integration — inputs  
   https://docs.x.ai/developers/model-capabilities/imagine/files/inputs
7. Imagine Files API integration — outputs / `storage_options`  
   https://docs.x.ai/developers/model-capabilities/imagine/files/outputs
8. Models / Imagine pricing  
   https://docs.x.ai/developers/models#imagine-pricing
9. Release Notes  
   https://docs.x.ai/developers/release-notes
10. Priority Processing docs, for the unresolved `service_tier` note  
    https://docs.x.ai/developers/advanced-api-usage/priority-processing

## Official API facts extracted on 2026-06-19

### Current generation API

- Endpoint: `POST https://api.x.ai/v1/images/generations`.
- Recommended current model in examples: `grok-imagine-image-quality`.
- Pricing page also lists `grok-imagine-image` as a lower-cost model.
- `grok-imagine-image-pro` is officially warned as deprecated as of 2026-05-15; new requests should use `grok-imagine-image-quality`.
- Supported request fields include:
  - `model`;
  - `prompt`;
  - `n`;
  - `aspect_ratio` with official values `1:1`, `3:4`, `4:3`, `9:16`, `16:9`, `2:3`, `3:2`, `9:19.5`, `19.5:9`, `9:20`, `20:9`, `1:2`, `2:1`, `auto`;
  - `resolution`: `1k` or `2k`;
  - `response_format`: `url` or `b64_json`;
  - `storage_options`;
  - `user`.
- Default URL outputs are temporary. `b64_json` and/or local cache are safer for Feishu/profile delivery.

### Current editing API

- Endpoint: `POST https://api.x.ai/v1/images/edits`.
- xAI explicitly warns that OpenAI SDK `images.edit()` is not supported for xAI editing because it uses `multipart/form-data`, while xAI requires `application/json`.
- Single input image request shape is JSON object form:

```json
{
  "model": "grok-imagine-image-quality",
  "prompt": "Render this as a pencil sketch with detailed shading",
  "image": {
    "url": "https://docs.x.ai/assets/api-examples/images/style-realistic.png",
    "type": "image_url"
  }
}
```

- The image object can carry either:
  - `url`: public URL or base64 data URI; or
  - `file_id`: xAI Files API file id, mutually exclusive with `url`.
- Multi-image editing uses `images: [...]` and supports up to 3 source images. Prompts may refer to images by order, e.g. `<IMAGE_0>`, `<IMAGE_1>`.
- Multi-image editing default output aspect ratio follows the first input image; it can be overridden by `aspect_ratio`. For single-image editing, xAI docs say output respects the input image ratio, so code/docs should not overpromise that `aspect_ratio` controls single-image edit output.
- Edit request fields also include `n`, `resolution`, `response_format`, `storage_options`, and `user`.

### Files API / storage changes

- xAI now supports referencing stored files as Imagine inputs using `file_id` / `image_file_id` style input wrappers.
- xAI now supports `storage_options` on generation and edit requests:
  - persist generated output into Files API storage;
  - optionally create `public_url`;
  - optional expiry between 3600 seconds and 2592000 seconds (1 hour to 30 days);
  - `storage_options.filename` is required when storage is requested;
  - response may include `data[i].file_output` with `file_id`, `filename`, `expires_at`, `public_url`, `public_url_expires_at`, or `public_url_error`.
- Public URL creation can fail while file storage succeeds; this must be treated as partial success metadata, not necessarily as a generation failure.

### Inconsistent / unresolved official docs point

- Release Notes say `service_tier: "priority"` can apply to text, image, and video inference endpoints.
- The Images REST API reference inspected on 2026-06-19 does **not** list `service_tier` in image generation/editing request bodies.
- Therefore this PR must not add unconditional `service_tier` usage. If implemented at all, it must be optional, default-off, and covered by a test proving it is absent unless explicitly configured. A live smoke is out of scope for this PR.

## Current Sachima implementation summary

Current implementation files:

- `plugins/image_gen/xai/__init__.py`
- `tools/image_generation_tool.py`
- `tools/image_edit_tool.py`
- `agent/image_gen_provider.py`
- tests under `tests/plugins/image_gen/` and `tests/tools/`

Current behavior verified from source:

- xAI provider posts JSON with `requests.post(..., json=payload)`.
- Generation uses `/images/generations`.
- Editing uses `/images/edits`.
- Editing wraps single source as `image: {"url": ..., "type": "image_url"}`.
- Local edit inputs are validated and converted to data URIs.
- Both generation/edit request `response_format: "b64_json"` and cache returned bytes locally.
- URL responses are cached locally when possible; fallback may return bare URL if URL caching fails.
- Supported xAI models in catalog: `grok-imagine-image`, `grok-imagine-image-quality`.
- Current default model is `grok-imagine-image`, not the current official examples' `grok-imagine-image-quality`.
- Tool schemas expose only `landscape`, `square`, `portrait` aspect choices.
- xAI provider has mappings for `4:3`, `3:4`, `3:2`, `2:3`, but current shared `resolve_aspect_ratio()` clamps to `landscape/square/portrait`, making those mappings effectively unreachable through the provider call path.
- There is no `n` multi-output support in xAI provider; `_extract_and_cache_image()` only processes `data[0]`.
- There is no `images: [...]` multi-image edit support.
- There is no Files API input support for `file_id`.
- There is no `storage_options` support.
- The provider ignores `mime_type` when saving base64 output; `save_b64_image()` defaults to `.png`.
- The provider does not surface `file_output`, `storage_error`, `public_url_error`, `mime_type`, or `usage.cost_in_usd_ticks` in success metadata.

Focused baseline tests already pass before this PR's implementation work:

```bash
uv run --frozen pytest tests/plugins/image_gen/test_xai_provider.py tests/tools/test_image_edit_tool.py -q -o 'addopts='
# 44 passed
```

## Product goal

Refresh Sachima's xAI image generation/editing support so Hermes profiles using xAI Imagine can use the current official API surface safely and predictably while preserving stable local media delivery for Feishu/Samiya.

The result should be:

- official-model aligned;
- JSON edit compliant;
- multi-output capable;
- multi-image-edit capable;
- Files API input/output aware;
- privacy-preserving by default;
- backward-compatible for existing simple `image_generate(prompt, aspect_ratio)` and `image_edit(prompt, image)` flows.

## In scope

### Code

- Update `plugins/image_gen/xai/__init__.py` for current xAI Imagine API support.
- Update `tools/image_generation_tool.py` and `tools/image_edit_tool.py` only as needed to expose safe generic options and route them to providers.
- Update `agent/image_gen_provider.py` only if needed for shared helpers/response metadata; preserve the existing `image` first-output contract.
- Update tests for the xAI provider, image generation schema/dispatch, and edit schema/dispatch.

### Behavior

- Default xAI image model becomes `grok-imagine-image-quality`.
- `grok-imagine-image` remains selectable as the lower-cost/fast model.
- Deprecated `grok-imagine-image-pro` must not be the default. If it is still accepted at all, it must be marked deprecated and mapped only when explicitly configured; prefer rejecting or ignoring it with a safe fallback to `grok-imagine-image-quality`.
- Generation and edit can request `n` outputs and preserve `image` as the first output while adding `images` metadata for all outputs.
- xAI official aspect ratios are supported for xAI payloads. Existing user-facing aliases remain supported:
  - `landscape` -> `16:9`
  - `square` -> `1:1`
  - `portrait` -> `9:16`
- Official ratio strings must be accepted for xAI: `1:1`, `3:4`, `4:3`, `9:16`, `16:9`, `2:3`, `3:2`, `9:19.5`, `19.5:9`, `9:20`, `20:9`, `1:2`, `2:1`, `auto`.
- Non-xAI providers must not crash if a new ratio reaches them; they may safely clamp/fallback as before.
- Single-image edit keeps JSON `image` object shape and must not use OpenAI SDK multipart edit.
- Multi-image edit supports up to 3 inputs via `images: [...]` and rejects more than 3 with `invalid_input`.
- Edit inputs support local paths, http(s) URLs, data URIs, and xAI `file_id` values.
- `storage_options` can be passed to xAI generation/edit request bodies, but must be default-off and not create public URLs unless explicitly requested by the caller/config.
- Base64 outputs should be saved using an extension derived from response `mime_type` when present; fallback remains `.png`.
- Response metadata should preserve useful official fields without breaking the old contract:
  - `image`: first local path or URL;
  - `images`: list of all generated/cached output refs when `n > 1` or multiple outputs are returned;
  - `mime_type` / per-image `mime_type` when present;
  - `file_output` / per-image `file_output` when present;
  - `storage_error`, `public_url_error` if present;
  - `usage` or at minimum `usage.cost_in_usd_ticks` if present.

### Docs / evidence

- Keep this PRD as the main context pack.
- Add a dev log at `docs/dev_log/2026-06-19-xai-imagine-api-refresh.md` recording implementation/review/gate evidence.
- Do not update live profile config files in the repo or under `/data/agents/.hermes/profiles/*`.

## Out of scope / explicit non-approvals

```text
live_xai_api_smoke_with_real_spend
gateway_restart_or_reload
feishu_live_delivery_test
profile_config_mutation
production_config_write
public_url_publication_for_private_media_by_default
changing_samiya_or_default_profile_runtime_config
changing non-image xAI provider routes
video Imagine API changes
voice API changes
OAuth/auth storage changes
managed billing changes
P5 runtime/FlowWeaver phase claims
service_tier_priority_default_on
```

## Functional requirements

### FR1 — Model catalog and default

- `DEFAULT_MODEL` for xAI image provider must be `grok-imagine-image-quality`.
- `list_models()` must list `grok-imagine-image-quality` first unless there is a strong compatibility reason not to.
- `grok-imagine-image` remains selectable.
- Tests must prove default model resolution, explicit standard-model config/env selection, and unknown/deprecated model fallback behavior.

### FR2 — xAI aspect-ratio handling

- Add an xAI-specific aspect resolver that accepts both old aliases and official wire values.
- Do not depend on the shared three-value `resolve_aspect_ratio()` for xAI wire validation.
- Invalid values must soft-fallback to a safe default and not crash.
- Tests must prove payload mappings for:
  - `landscape` -> `16:9`;
  - `portrait` -> `9:16`;
  - `4:3` -> `4:3`;
  - `20:9` -> `20:9`;
  - `auto` -> `auto`;
  - invalid -> default.

### FR3 — Multi-output generation and edit

- Generation supports optional `n` when provided by direct/provider callers and, if safely exposed, by tool callers.
- Edit supports optional `n` similarly.
- All returned `data[]` items should be processed, not just `data[0]`.
- Preserve backward compatibility: `result["image"]` is still the first output.
- Add `result["images"]` containing all output refs when there is more than one output or when the provider returns multiple outputs.
- Tests must prove two returned b64 outputs are both cached and reported.

### FR4 — Single-image edit remains JSON compliant

- Single-image edit must continue to send:

```json
"image": {"url": "...", "type": "image_url"}
```

for URL/data-URI inputs.
- It must not send top-level `image_url`.
- It must not rely on OpenAI SDK `images.edit()`.
- Tests must keep this regression coverage.

### FR5 — File ID input support

- Single-image edit must accept xAI Files API ids and send:

```json
"image": {"file_id": "file_..."}
```

- Multi-image edit must allow each image entry to be a URL/data URI/local path/file id.
- Local paths are validated before conversion; xAI file ids must not be interpreted as local paths.
- Tests must cover file-id single input, mixed multi-inputs, and invalid empty file ids.

### FR6 — Multi-image edit

- Add optional `images` input handling for xAI edit, max 3 images.
- `image` and `images` must be mutually exclusive at the tool/provider boundary; ambiguous input returns `invalid_input`.
- More than 3 images returns `invalid_input` before network call.
- Tests must prove payload shape:

```json
"images": [
  {"url": "data:image/png;base64,...", "type": "image_url"},
  {"file_id": "file_..."}
]
```

### FR7 — Storage options support without public-by-default behavior

- Support passing `storage_options` through to xAI request bodies when explicitly provided.
- Do not add `storage_options` by default.
- Do not set `public_url: true` by default.
- Validate basic safe shape before sending:
  - object/dict only;
  - `filename` required if any storage option is provided;
  - optional integer `expires_after` within xAI-documented 3600..2592000 range;
  - optional `public_url` boolean or object;
  - optional `public_url.expires_after` within 3600..2592000 range.
- Tests must prove valid pass-through, invalid rejection, and default absence.

### FR8 — Response metadata and MIME-aware local cache

- When `data[i].b64_json` is present, save with extension from `data[i].mime_type` when available:
  - `image/png` -> `.png`;
  - `image/jpeg` / `image/jpg` -> `.jpg`;
  - `image/webp` -> `.webp`;
  - unknown -> `.png`.
- Preserve response metadata in result extras:
  - `mime_type` for first image if present;
  - `images[*].mime_type` if present;
  - `file_output` / `storage_error` / `public_url_error` if present;
  - `usage` if present.
- Tests must prove MIME extension selection and metadata preservation.

### FR9 — Priority processing stays explicitly default-off

- Do not add `service_tier` to image payloads by default.
- If support is added, it must be gated by explicit xAI image config and have tests proving absence by default.
- No live priority smoke in this PR.

### FR10 — Backward compatibility

Existing simple usage must keep working:

```python
provider.generate(prompt="A cat", aspect_ratio="square")
provider.edit(prompt="make it blue", image="/path/to/input.png")
```

Expected old-style success shape remains:

```json
{
  "success": true,
  "image": "/absolute/cache/path.png",
  "model": "grok-imagine-image-quality",
  "prompt": "...",
  "aspect_ratio": "square",
  "provider": "xai"
}
```

Additional keys are allowed but must not remove or rename existing keys.

## Non-functional requirements

- No secrets in code, docs, logs, tests, or prompts.
- No live API calls required by tests.
- Tests use mocks/fakes for HTTP responses.
- Use TDD: write/adjust failing tests first, run to confirm RED, then implement.
- Preserve profile isolation: no edits under `/data/agents/.hermes/profiles/*`.
- Preserve Gateway stability: no service restart or runtime config write.
- Keep implementation provider-local where practical; do not overgeneralize all image providers unless required for safe tool routing.
- Avoid broad refactors of unrelated FAL/OpenAI/Krea providers.

## Implementation task plan

### Task 1 — RED tests for model default and official ratio resolver

Files:

- Modify: `tests/plugins/image_gen/test_xai_provider.py`
- Modify: `plugins/image_gen/xai/__init__.py` only after RED is observed

Steps:

1. Add tests asserting default model is `grok-imagine-image-quality` and `provider.default_model()` returns quality.
2. Add tests for explicit `XAI_IMAGE_MODEL=grok-imagine-image` selection.
3. Add payload tests for official ratios `4:3`, `20:9`, `auto`, and alias `portrait`.
4. Run focused tests and confirm failures for default/ratio gaps.
5. Implement xAI-specific model/default/aspect resolver.
6. Rerun focused tests to GREEN.

### Task 2 — RED tests and implementation for multi-output `n`

Files:

- Modify: `tests/plugins/image_gen/test_xai_provider.py`
- Modify: `plugins/image_gen/xai/__init__.py`
- Modify: `tools/image_generation_tool.py` only if tool schema/dispatch changes are needed
- Modify: `tools/image_edit_tool.py` only if tool schema/dispatch changes are needed

Steps:

1. Add tests for `provider.generate(..., n=2)` producing payload `"n": 2` and returning `image` first plus `images` list of two cached refs.
2. Add analogous edit test if `n` applies to edit provider path.
3. Confirm RED.
4. Replace single-output extraction helper with multi-output-capable extraction while preserving first-output contract.
5. Rerun focused tests.

### Task 3 — RED tests and implementation for file-id input and multi-image edit

Files:

- Modify: `tests/plugins/image_gen/test_xai_provider.py`
- Modify: `tests/tools/test_image_edit_tool.py`
- Modify: `plugins/image_gen/xai/__init__.py`
- Modify: `tools/image_edit_tool.py`
- Modify: `agent/image_gen_provider.py` only if the abstract edit signature/schema docs need to describe `images`

Steps:

1. Add provider tests for single `file_...` input producing `image: {"file_id": "file_..."}`.
2. Add provider tests for mixed `images=[local_path, "file_...", "https://..."]` producing `images: [...]`.
3. Add invalid tests: both `image` and `images`, empty list, more than 3 images, bad local file.
4. Add tool-dispatch tests proving `image_edit` forwards optional `images` to provider and preserves old required `image` path.
5. Confirm RED.
6. Implement provider input normalization and tool forwarding.
7. Rerun focused tests.

### Task 4 — RED tests and implementation for `storage_options`

Files:

- Modify: `tests/plugins/image_gen/test_xai_provider.py`
- Modify: `plugins/image_gen/xai/__init__.py`
- Modify: `tools/image_generation_tool.py` / `tools/image_edit_tool.py` only if safe schema exposure is chosen

Steps:

1. Add tests proving no `storage_options` by default.
2. Add tests proving valid explicit storage options pass through.
3. Add invalid-shape tests: non-object, missing filename, out-of-range expiry, malformed public_url object.
4. Confirm RED.
5. Implement validation/pass-through in the xAI provider.
6. Rerun focused tests.

### Task 5 — RED tests and implementation for MIME/metadata preservation

Files:

- Modify: `tests/plugins/image_gen/test_xai_provider.py`
- Modify: `plugins/image_gen/xai/__init__.py`
- Modify: `agent/image_gen_provider.py` only if helper support is needed

Steps:

1. Add tests where response has `mime_type: "image/webp"` and `b64_json`; assert cache saver is called with extension `webp` or resulting path records webp.
2. Add tests where response has `file_output`, `storage_error`, `public_url_error`, and `usage`; assert result preserves metadata safely.
3. Confirm RED.
4. Implement metadata extraction/preservation.
5. Rerun focused tests.

### Task 6 — Tool schema / docs polish and compatibility gates

Files:

- Modify: `tools/image_generation_tool.py`
- Modify: `tools/image_edit_tool.py`
- Modify: `tests/tools/test_image_generation.py`
- Modify: `tests/tools/test_image_edit_tool.py`
- Modify: this PRD/dev log only as evidence is added

Steps:

1. If schema expands aspect ratios or adds `n`/`images`/`storage_options`, update tests that currently expect only the old minimal schema.
2. Ensure non-xAI providers still soft-fallback or ignore unsupported new fields without crashing.
3. Keep descriptions clear that backend support varies and public URL storage is explicit/default-off.
4. Run focused schema/dispatch tests.

## Required verification commands

Run from the worktree root:

```bash
uv run --frozen pytest tests/plugins/image_gen/test_xai_provider.py tests/tools/test_image_edit_tool.py tests/tools/test_image_generation.py tests/tools/test_image_generation_plugin_dispatch.py -q -o 'addopts='
python3 tools/sync_roadmap_status.py --check
git diff --check
```

If touched code imports compile-sensitive modules, also run:

```bash
uv run --frozen python -m py_compile plugins/image_gen/xai/__init__.py tools/image_edit_tool.py tools/image_generation_tool.py agent/image_gen_provider.py
```

Before PR, run changed-file safety checks:

```bash
git status --short --branch
git diff --name-status sachima/release/sachima...HEAD
git diff --stat sachima/release/sachima...HEAD
```

Secret/leak scan must check added lines and new files only. Synthetic secret-shaped literals in tests/docs should be split or avoided.

## Claude Code main-programmer context

Claude Code must receive this PRD path and the following constraints:

- Worktree: `/home/ecs-user/workspace/hermes/worktrees/sachima/feat-xai-imagine-api-refresh`.
- Role: main programmer for scoped implementation.
- Required flags: `--effort max`, `--max-turns 100` or higher if the CLI supports it; do not downshift effort.
- Do not push, merge, restart services, edit profile configs, or call live xAI APIs.
- Follow TDD: add RED tests first, verify failures, implement, rerun tests.
- Keep changes focused on xAI image provider/tool schema/tests/docs.
- Stop with `BLOCKED` and exact reason if any official docs or repo constraints contradict this PRD.

## Codex primary review context

After Claude Code implementation and Hermes deterministic gates, Codex CLI must perform a repo-aware read-only review on the final diff/head:

- inspect PR/diff plus relevant source/tests;
- verify official xAI docs alignment;
- verify no live/Gateway/profile/prod side effects;
- verify backward compatibility;
- return `VERDICT: PASS` or `BLOCK` with file/line evidence.

## PR closeout requirements

Before opening the PR:

- Worktree clean except intended committed changes.
- Focused tests pass.
- `git diff --check` passes.
- `tools/sync_roadmap_status.py --check` passes or any non-applicability is explained.
- Codex primary review blockers are zero.

PR target:

- repo: `jovijovi/sachima`
- base: `release/sachima`
- head: `feat/xai-imagine-api-refresh`

If PR CI passes and mergeability is clean, send a Feishu approval card bound to the live PR head SHA.
