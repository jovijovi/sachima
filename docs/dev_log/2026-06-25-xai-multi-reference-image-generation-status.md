# xAI Multi-Reference Image Generation Status Snapshot

Date: 2026-06-25
Branch: `release/sachima`
Repository: `jovijovi/sachima`
Runtime checkout inspected: `/home/ecs-user/workspace/hermes/repo/sachima`
Current inspected head: `c63891538b7c`
Status: documentation snapshot for future development; no code/config/runtime mutation in this document.

## Scope

This document records the current state and progress of the xAI/Grok Imagine
multi-reference image generation feature in the Sachima release line.

The key question is:

> Can Hermes/Sachima generate or edit an image with multiple reference images
> through the xAI image provider, and what remains before future development can
> safely continue?

This is a **capability/status reference**, not a new approval. It does not
authorize live xAI spend, profile credential changes, Gateway restarts,
production config writes, public hosting of private reference images, or new
P5/FlowWeaver phase claims.

## Executive conclusion

The code-level capability is merged in `release/sachima`.

The current supported user-facing path is:

```python
image_generate(
    prompt="...",
    image_url="<primary source image>",
    reference_image_urls=["<reference 1>", "<reference 2>"]
)
```

For xAI, this routes through the provider's `/v1/images/edits` path and sends a
multi-image `images: [...]` payload when more than one source image is supplied.
The provider advertises `max_reference_images = 3`.

Important caveat: the separate `image_edit` tool surface is still single-image
at the schema layer. Do not tell future developers that `image_edit(images=[...])`
is live unless a later change explicitly adds that schema and handler support.

As of this snapshot, unit/focused integration tests for the provider/tool
routing are green, and the Gateway processes are running the inspected checkout,
but a real end-to-end multi-reference xAI smoke with supplied reference images,
manifest/history verification, and Feishu delivery remains unproven.

## Layer model: do not collapse these states

Future status reports must keep these layers separate:

1. Upstream xAI API capability.
2. Sachima/Hermes provider implementation.
3. Agent-callable tool schema.
4. Runtime profile configuration and credentials.
5. Real provider call success.
6. Manifest/history provenance.
7. Gateway/Feishu media delivery.

A merge or unit test only proves layers 2-3. A live user-visible feature claim
requires layers 4-7 to be checked in the target profile.

## Official upstream API facts

Official xAI documentation remains the authority for API shape:

- Image Editing: https://docs.x.ai/developers/model-capabilities/images/editing
- Multi-Image Editing: https://docs.x.ai/developers/model-capabilities/images/multi-image-editing
- Image Generation: https://docs.x.ai/developers/model-capabilities/images/generation
- Images REST API reference: https://docs.x.ai/developers/rest-api-reference/inference/images
- Imagine Files API inputs: https://docs.x.ai/developers/model-capabilities/imagine/files/inputs
- Imagine Files API outputs / `storage_options`: https://docs.x.ai/developers/model-capabilities/imagine/files/outputs

Facts rechecked on 2026-06-25 from the official `.md` documentation endpoint:

- Multi-image editing supports **up to three source images** for one image edit.
- Source images are ordered by request order.
- By default, output aspect ratio follows the first input image.
- `aspect_ratio` can override that default, e.g. `"1:1"` or `"16:9"`.
- Each source image may be a public URL, a base64 data URI, or a `file_id` from
  the xAI Files API.
- Single-image edit uses JSON, not OpenAI SDK multipart form upload.

## Implementation timeline and PR map

### PR #152 — `feat: refresh xAI Imagine image provider`

URL: https://github.com/jovijovi/sachima/pull/152
Merged: 2026-06-19
Merge commit: `3458c3649294`

What it established:

- Default xAI image model changed to `grok-imagine-image-quality`.
- `grok-imagine-image` remains selectable.
- Generation and edit support optional multi-output `n` for direct/provider callers.
- xAI edit supports:
  - single image object input;
  - xAI Files API `file_id` input;
  - multi-image `images[]` up to three sources.
- `storage_options` is explicit/default-off.
- b64 outputs are cached locally with MIME-derived extensions and metadata.
- Official xAI docs links and PRD/dev-log evidence were added.

Relevant existing docs:

- `docs/plans/2026-06-19-xai-imagine-api-refresh-prd.md`
- `docs/dev_log/2026-06-19-xai-imagine-api-refresh.md`

### PR #153 — `fix: honor xAI edit resolution config`

URL: https://github.com/jovijovi/sachima/pull/153
Merged: 2026-06-19
Merge commit: `1e84ed198340`

What it established:

- xAI edit requests now honor `image_gen.xai.resolution` the same way generation
  requests do.
- `/images/edits` payloads include configured literal `resolution` (`1k`/`2k`).
- Edit success metadata echoes the applied resolution.
- The PR body recorded a live xAI edit smoke using default profile config where
  `image_gen.xai.resolution=2k` produced a 2816x1584 16:9 output.

### PR #157 — `feat: add image manifest history`

URL: https://github.com/jovijovi/sachima/pull/157
Merged: 2026-06-21
Merge commit: `8dc1e5ac9f7b`

What it established:

- Profile-local image manifest logging for `image_generate` and `image_edit`.
- Log-only `content_summary` schema support; it is not forwarded to providers.
- `image_history` query tool under the `image_gen` toolset.
- Manifest redaction rules: no raw data URI/base64, signed URL query, provider
  raw response, auth/header/secret, SHA/hash/digest/session/tool-call raw fields.

Boundary explicitly recorded in the PR body:

- PR #157 did not implement xAI multi-image reference support; it added
  observability around generation/editing calls.

### PR #158 — `feat: add image manifest sequence indices`

URL: https://github.com/jovijovi/sachima/pull/158
Merged: 2026-06-22
Merge commit: `dbe86f2731cb`

What it established:

- 1-based `sequence` numbers for manifest records.
- 1-based `output_index` metadata for image outputs.
- Deterministic `image_history(latest=True)` sorting for same-timestamp records.

### PR #159 — upstream v2026.6.19 merge into Sachima release

URL: https://github.com/jovijovi/sachima/pull/159
Merged: 2026-06-22
Merge commit: `0a55f782f00d`

What it preserved:

- Image generation/edit/history manifest provenance.
- xAI/reference-image semantics across plugin and tool-layer dispatch.
- Sanitized input image refs.
- Sachima downstream customizations.

### PR #164 — Feishu TODO card lifecycle fix

URL: https://github.com/jovijovi/sachima/pull/164
Merged: 2026-06-24
Merge commit: `dc46af8d33a9`

No xAI multi-reference behavior change, but it is the latest non-machine merged
PR on `release/sachima` at the time of this snapshot.

## Current code contract

### Provider capability declaration

`plugins/image_gen/xai/__init__.py:546-550`

The xAI provider declares both text and image modalities:

```python
return {"modalities": ["text", "image"], "max_reference_images": 3}
```

Meaning:

- text-to-image is supported;
- image-to-image/editing is supported;
- at most three total source/reference images should be sent to xAI.

### Unified `image_generate` routes to xAI edit when images are present

`plugins/image_gen/xai/__init__.py:552-600`

Provider `generate()` accepts:

- `image_url: Optional[str]`
- `reference_image_urls: Optional[List[str]]`

It builds an ordered `source_images` list:

1. primary `image_url` first, if supplied;
2. normalized `reference_image_urls` after that.

If `source_images` is non-empty:

- one source image -> `self.edit(prompt=..., image=source_images[0], ...)`;
- more than one source image -> `self.edit(prompt=..., images=source_images, ...)`.

This is the main user-facing path for xAI multi-reference generation/editing.

### xAI edit provider builds the correct JSON payload

`plugins/image_gen/xai/__init__.py:680-836`

Provider `edit()` supports:

- single `image` input;
- keyword-only `images=[...]` multi-image input;
- local filesystem path;
- `http(s)` URL;
- base64 `data:` URI;
- xAI `file_...` id.

Validation behavior:

- `image` and `images` are mutually exclusive.
- `images` must be a non-empty list.
- more than three images returns `invalid_input` before network call.
- bad local paths return `invalid_input` before network call.

Payload behavior:

- single input sends top-level `image: {...}`;
- multi-input sends top-level `images: [...]` and **does not** send `image`;
- `aspect_ratio`, `resolution`, and `response_format: "b64_json"` are included;
- optional `n` and `storage_options` are supported for direct/provider callers.

### Agent-callable `image_generate` schema exposes multi-reference inputs

`tools/image_generation_tool.py:1188-1247`

The base `IMAGE_GENERATE_SCHEMA` exposes:

- `prompt`
- `aspect_ratio`
- `image_url`
- `reference_image_urls`
- `content_summary`

The description explicitly states:

- pass `image_url` to edit/transform a source image;
- add `reference_image_urls` for style/composition references;
- omit both for text-to-image.

Dynamic schema overrides add active-backend text such as:

```text
Active backend: xAI (Grok) · model: grok-imagine-image-quality
- supports both text-to-image (omit image_url) and image-to-image / editing
  (pass image_url); up to 3 reference image(s) via reference_image_urls — routes automatically
```

Note: `_build_dynamic_image_schema()` returns only description overrides; the
actual parameters still come from `IMAGE_GENERATE_SCHEMA`. Do not misread a
probe of the dynamic override object as proof that parameters are missing.

### Plugin dispatch forwards image references

`tools/image_generation_tool.py:1289-1416`

When `image_gen.provider` is explicitly configured, plugin dispatch forwards:

- `image_url`
- normalized `reference_image_urls`
- configured model, if present.

If a legacy provider has a narrow `generate()` signature that cannot accept
`image_url` or `reference_image_urls`, the dispatch returns a clear
`modality_unsupported` error instead of silently dropping images.

### Manifest logging captures input references

`tools/image_generation_tool.py:1419-1462`

The `image_generate` handler builds `input_images` from:

1. `image_url`;
2. every string in `reference_image_urls`.

It appends a manifest record for both success and failure. Input refs are
sanitized by `tools/image_manifest.py` before being written.

### Separate `image_edit` tool remains single-image

`tools/image_edit_tool.py:196-233`

Current `IMAGE_EDIT_SCHEMA` exposes:

- `prompt`
- `image`
- `aspect_ratio`
- `content_summary`

It does **not** expose `images`.

`tools/image_edit_tool.py:151-189` also validates only `image` and dispatches:

```python
provider.edit(prompt=prompt, image=image, aspect_ratio=aspect_ratio)
```

So future development must treat these as different layers:

- xAI provider internals support `images=[...]`;
- `image_generate` exposes a multi-reference path;
- `image_edit` does not yet expose a direct multi-image path.

## Current test coverage

### Provider multi-image edit tests

`tests/plugins/image_gen/test_xai_provider.py:792-846`

Coverage includes:

- mixed inputs build `images: [...]`;
- top-level `image` is absent for multi-image edit;
- local file becomes data URI;
- `file_id` remains `{"file_id": ...}`;
- URL becomes `{"url": ..., "type": "image_url"}`;
- `image` + `images` together is invalid;
- empty `images` is invalid;
- more than three images is invalid before network.

### Tool-level image-to-image routing tests

`tests/tools/test_image_generation_image_to_image.py:111-145`

Coverage includes:

- `image_url` routes FAL editable models to their edit endpoint.
- `reference_image_urls` are clamped to the selected model cap.
- text-only models reject image input with a clear image-to-image error.

`tests/tools/test_image_generation_image_to_image.py:226-247`

Coverage includes plugin dispatch forwarding:

- `image_url` reaches provider `generate()`;
- `reference_image_urls` reaches provider `generate()`.

### `image_edit` schema tests

`tests/tools/test_image_edit_tool.py:65-80`

Coverage intentionally asserts the current single-image schema shape and notes
that `mask` is omitted until xAI edit-mask semantics are clear. There is no
current assertion that `images` exists in `image_edit`.

## Verification run on 2026-06-25

Command run from `/home/ecs-user/workspace/hermes/repo/sachima`:

```bash
uv run --frozen --extra dev python -m pytest \
  tests/plugins/image_gen/test_xai_provider.py \
  tests/tools/test_image_generation_image_to_image.py \
  tests/tools/test_image_edit_tool.py \
  -q -o 'addopts='
```

Observed result:

```text
114 passed in 1.92s
```

This proves the current code contract and mocked provider/tool routing. It does
not prove a real xAI call or Feishu delivery.

## Runtime/profile snapshot on 2026-06-25

Profile checks were performed with explicit `HERMES_HOME` values. Do not reuse
these as permanent truth; recheck before future work.

### default profile

- `image_gen.provider`: `xai`
- `image_gen.model`: `grok-imagine-image-quality`
- `image_gen.xai.resolution`: `2k`
- Feishu toolsets include `image_gen`.
- Direct shell `provider.is_available()` probe returned `False` in this
  snapshot, while the active Feishu session exposed an xAI-backed
  `image_generate` tool. Treat this as a profile/runtime credential-context
  ambiguity, not as a code absence.

Future work must force the exact profile/runtime environment before claiming
whether default can make a live xAI call.

### Samiya profile

- `image_gen.provider`: `xai`
- `image_gen.model`: `grok-imagine-image-quality`
- `image_gen.xai.resolution`: `2k`
- Feishu toolsets include `image_gen`.
- Direct shell `provider.is_available()` probe returned `True`.
- Provider capabilities returned `{"modalities": ["text", "image"], "max_reference_images": 3}`.

Samiya is currently the strongest candidate profile for a real multi-reference
xAI smoke, subject to user approval and supplied reference images.

### Satine profile

- No xAI image provider configured in this snapshot.
- Feishu toolsets include `image_gen`, but provider selection/credentials do not
  imply xAI multi-reference availability.

## Gateway/runtime status snapshot on 2026-06-25

After an all-gateway restart/self-check, status was:

```text
default: active/running, working directory /home/ecs-user/workspace/hermes/repo/sachima
Samiya:  active/running, working directory /data/agents/.hermes/profiles/samiya
Satine:  active/running, working directory /data/agents/.hermes/profiles/satine
API:     HTTP 200 {"status": "ok", "platform": "hermes-agent", "version": "0.17.0"}
```

This proves the services were healthy after restart. It does not by itself prove
that the current conversation has a refreshed tool schema or that xAI credentials
work in every profile.

## Manifest/history status snapshot

The `image_history` tool returned recent default-profile `image_generate` records,
including one successful xAI text-to-image generation with:

- provider: `xai`
- model: `grok-imagine-image-quality`
- resolution: `2k`
- success: `true`

It returned zero `image_edit` records in this snapshot.

There was no recorded real multi-reference `image_generate` smoke in the queried
history at this point.

## Remaining gaps before claiming full E2E readiness

### G1 — Real multi-reference xAI smoke

Need a real call using supplied or explicitly approved reference images.

Minimum proof:

1. Pick target profile and force its `HERMES_HOME`.
2. Call `image_generate` with:
   - one `image_url` primary source;
   - one or two `reference_image_urls`;
   - a concise `content_summary`.
3. Confirm provider result succeeds.
4. Query `image_history(latest=True)` and verify:
   - new manifest record exists;
   - `input_images` includes all supplied refs in sanitized form;
   - output includes `output_index` and a stable local/cache reference;
   - no signed query strings, base64 payloads, secrets, or private absolute paths
     leak into the compact record.
5. Confirm Feishu/Gateway delivers the media once, not zero times and not double.

### G2 — Direct `image_edit.images` schema, if desired

If future development wants direct multi-image editing through `image_edit`, the
current work is not enough. Required changes:

- Add optional `images: array[string]` to `IMAGE_EDIT_SCHEMA`.
- Update `_handle_image_edit()` validation:
  - require either `image` or `images`;
  - reject both together;
  - reject empty list;
  - enforce an active-provider cap or let the provider reject with clear error.
- Update `_dispatch_image_edit()` to pass `images=...` to provider when supplied.
- Update manifest logging so `input_images` records every `images[*]` ref, not
  only a single `image`.
- Add RED/GREEN tests in `tests/tools/test_image_edit_tool.py` for schema,
  dispatch, manifest input refs, and failure cases.
- Confirm `image_edit` stays hidden unless an edit-capable provider is available.

Until this is done, the sanctioned multi-reference path remains `image_generate`.

### G3 — Profile credential ambiguity

The default profile had a selected xAI provider but a direct shell availability
probe returned false. Future work must not infer default-profile live readiness
from the current session's visible tool description.

Recommended check:

```bash
HERMES_HOME=/data/agents/.hermes python - <<'PY'
from hermes_cli.plugins import _ensure_plugins_discovered
from agent.image_gen_registry import get_provider
_ensure_plugins_discovered()
provider = get_provider('xai')
print('registered=', bool(provider))
print('available=', provider.is_available() if provider else None)
print('caps=', provider.capabilities() if provider else None)
PY
```

If `available=False`, diagnose credentials/profile routing. Do not borrow Samiya
credentials into default.

### G4 — Upstream docs drift

xAI's Imagine docs are fast-moving. Before future code changes, refresh official
`.md` docs and compare against the existing PRD facts. Do not rely only on the
2026-06-19 PRD or this 2026-06-25 snapshot.

## Recommended future-development checklist

Before editing code:

1. Read this snapshot.
2. Read `docs/plans/2026-06-19-xai-imagine-api-refresh-prd.md`.
3. Read `docs/dev_log/2026-06-19-xai-imagine-api-refresh.md`.
4. Refresh official xAI docs listed above.
5. Fresh-check repo state:

```bash
cd /home/ecs-user/workspace/hermes/repo/sachima
git status --short --branch
git log --oneline --decorate -S 'reference_image_urls' -- \
  tools/image_generation_tool.py plugins/image_gen/xai/__init__.py tests | sed -n '1,80p'
```

6. Force the target runtime profile with `HERMES_HOME` before any capability
   claim.
7. Run focused tests:

```bash
uv run --frozen --extra dev python -m pytest \
  tests/plugins/image_gen/test_xai_provider.py \
  tests/tools/test_image_generation_image_to_image.py \
  tests/tools/test_image_edit_tool.py \
  -q -o 'addopts='
```

8. If touching manifest/history, add or run manifest privacy tests. The record
   must not leak raw base64, signed URL queries/fragments, URL userinfo,
   secret-shaped path segments, raw provider responses, or private absolute
   paths in compact user-facing history.
9. If touching Gateway/Feishu delivery, separate provider success from media
   delivery success and verify duplicate-delivery counts.

## Safe example invocation shape

Use this pattern when the user supplies approved reference images:

```python
image_generate(
    prompt=(
        "Use the first image as the primary subject/composition. Use the second "
        "and third images only as style/reference guidance. Preserve identity "
        "and avoid adding text or watermarks."
    ),
    aspect_ratio="square",
    image_url="/absolute/local/or/approved/url/primary.png",
    reference_image_urls=[
        "/absolute/local/or/approved/url/ref-style.png",
        "/absolute/local/or/approved/url/ref-composition.png",
    ],
    content_summary=(
        "xAI multi-reference smoke: primary subject plus style/composition refs; "
        "square output; identity-preserving; no text/watermark."
    ),
)
```

Privacy rule: for user/private portrait refs, prefer local paths or data URIs and
avoid public hosts unless explicitly approved.

## Non-approvals and safety boundaries

This feature status does not approve:

```text
public_url_publication_for_private_media
profile_config_mutation
credential_copy_between_profiles
live_xai_spend_without_current user approval or clear task need
gateway_restart_or_reload_outside_explicit_ops_request
production_config_write
claiming P5/FlowWeaver runtime progress from image-provider work
reporting image_edit.images as live before schema support exists
```

## Quick status answer for future agents

Use this concise form when asked later:

> Code support is merged. xAI provider supports up to 3 source/reference images
> via `/v1/images/edits`. In this Sachima release, the agent-facing multi-ref
> path is `image_generate(image_url=..., reference_image_urls=[...])`; `image_edit`
> remains single-image at schema level. Focused tests passed on 2026-06-25
> (`114 passed`). Full E2E still needs a real target-profile smoke with supplied
> refs, `image_history` provenance check, and Feishu delivery verification.
