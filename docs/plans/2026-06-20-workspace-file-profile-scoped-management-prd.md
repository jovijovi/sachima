# Workspace File Profile-Scoped Management PRD

> Status: PRD draft for pre-development governance. This document authorizes no implementation by itself.

## 1. Product outcome

Hermes companion/worker profiles need to organize their own local workspace files without receiving broad `file` or `terminal` access. The upgraded `workspace_file` toolset should let a configured profile list, inspect, copy, move, delete, and import profile-local text/media files inside a strict `$HERMES_HOME` workspace boundary.

## 2. Baseline / authority

Current implementation:

- Source: `tools/workspace_file_tool.py`
- Tests: `tests/tools/test_workspace_file_tool.py`
- Existing tools: `workspace_list`, `workspace_read`, `workspace_search`, `workspace_write`, `workspace_patch`
- Existing config: `workspace_file.root`, `mode`, `allowed_extensions`, `max_file_bytes`, `max_output_chars`, `backups`, `scan`
- Current default extensions: `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.csv`
- Current live profile usage checked on 2026-06-20: only Samiya Feishu enables `workspace_file`; default and Satine do not.

Governance references:

- `AGENTS.md`: non-trivial code work must use a dedicated worktree under `/home/ecs-user/workspace/hermes/worktrees/<project>/<branch-slug>`.
- `profile-scoped-tool-permissions` skill: companion profiles should receive narrow profile-scoped tools instead of full `file` or `terminal`.
- Latest user decision: extend the existing generic `workspace_file` toolset directly; do not create a separate Samiya-only tool or parallel `workspace_ops` surface.

## 3. Actors

- User/operator: approves scope, implementation, rollout, and profile config changes.
- Profile agent, especially Samiya: uses the narrow toolset from Feishu within its active profile home.
- Hermes runtime: exposes registered tools from the `workspace_file` toolset only when the platform/profile enables it.
- Reviewer agents: PRD reviewer, Claude Code architect, Codex CLI technical reviewer.
- Hermes controller: owns scope, repo state, verification, PR, and evidence arbitration.

## 4. User scenarios

- Scenario A — local media organization: Samiya receives or generates a private image cached under a configured profile-local import root such as `image_cache`; she imports it into `workspace/images/`, lists it, checks metadata, and can later move it into `workspace/archive/` without any broad filesystem access.
- Scenario B — safe cleanup: Samiya deletes an obsolete workspace media file; default behavior moves it into `.trash` and returns only action/path/byte metadata, so accidental deletion is reversible by an operator.
- Scenario C — text note continuity: existing text note workflows continue to work with `workspace_write`, `workspace_patch`, `workspace_read`, and `workspace_search`, including legacy `allowed_extensions` configs.

## 5. In scope

### FR-1: Keep `workspace_file` as the single generic toolset

Extend `tools/workspace_file_tool.py` and its tests. Do not add a persona-specific toolset.

### FR-2: Add file management operations

Add these tool-facing operations unless technical design finds a safer equivalent name:

- `workspace_stat(path)`
- `workspace_copy(src_path, dst_path, overwrite=false)`
- `workspace_move(src_path, dst_path, overwrite=false)`
- `workspace_delete(path, permanent=false)`
- `workspace_import(source_root, source_path, dst_path, overwrite=false)`

Existing tools must keep working.

### FR-3: Add `file_type_policy`

Support config:

```yaml
workspace_file:
  file_type_policy:
    mode: allowlist   # allowlist | denylist | all
    extensions: []
```

Compatibility requirement: legacy `allowed_extensions` must continue to work and map to an allowlist when `file_type_policy` is absent. If both `file_type_policy` and legacy `allowed_extensions` are present, the technical design must choose one deterministic precedence rule and test it; recommended default is that explicit `file_type_policy` wins, with legacy `allowed_extensions` serving only as backward-compatible fallback.

Extension handling requirements:

- Normalize extensions to lowercase.
- Require a leading dot in normalized policy entries, or normalize bare names safely.
- Compare paths case-insensitively by suffix.
- `mode: allowlist`: only configured extensions are allowed.
- `mode: denylist`: configured extensions are rejected; all other regular-file extensions are allowed.
- `mode: all`: extension check is disabled, but all path/root/symlink/size/operation checks still apply.

### FR-4: Default media/text allowlist

The default allowlist for this feature is:

```text
.md .txt .json .yaml .yml .csv
.png .jpg .jpeg .webp .gif .bmp .avif .heic .heif
.mp3 .wav .m4a .aac .ogg .opus .flac .amr
.mp4 .mov .m4v .webm .mkv .avi .3gp .3g2
```

Optional, not default:

```text
.svg .ico .tif .tiff .psd .ai .exr .weba .oga .aiff .aif .wma .mid .midi .mpeg .mpg .wmv .flv .ts .m2ts
```

`.svg` remains optional because it can carry scriptable content if rendered in a browser/frontend.

### FR-5: Text versus binary/media behavior

The toolset may operate on binary/media files for stat/list/copy/move/delete/import, but it must not dump raw binary bytes or base64 into model-visible text by default.

Requirements:

- `workspace_read` remains safe for text-like files.
- For binary/media files, `workspace_read` should return metadata or a safe media/file marker rather than raw bytes.
- `workspace_search` should search only text-like files and skip binary/media files with clear metadata when relevant.
- `workspace_write` and `workspace_patch` remain text-content tools unless the technical design introduces a separate safe binary-import/copy path. They must not accept arbitrary raw binary bytes in JSON arguments.

### FR-6: Import roots

Support configured read-only import roots under active profile `HERMES_HOME`, for example:

```yaml
workspace_file:
  import_roots:
    image_cache:
      path: image_cache
      file_type_policy:
        mode: allowlist
        extensions: [.png, .jpg, .jpeg, .webp, .gif, .bmp, .avif, .heic, .heif]
    media:
      path: workspace/media
      file_type_policy:
        mode: allowlist
        extensions: [.png, .jpg, .jpeg, .webp, .gif, .bmp, .avif, .heic, .heif, .mp3, .wav, .m4a, .aac, .ogg, .opus, .flac, .amr, .mp4, .mov, .m4v, .webm, .mkv, .avi, .3gp, .3g2]
```

Import roots are read-only sources. They may copy into the workspace root; they must not allow move, delete, write, or traversal outside their configured root.

### FR-7: Delete defaults to trash

`workspace_delete(path, permanent=false)` must default to soft delete. Recommended config:

```yaml
workspace_file:
  delete:
    mode: trash
    trash_dir: .trash
```

Trash behavior requirements:

- Move the file into a workspace-local trash location.
- Avoid overwriting existing trash files.
- Return path/bytes/action metadata only.
- `permanent=true` is allowed only if config permits permanent deletion or if technical design justifies a safe explicit override.

### FR-8: Preserve hard safety boundaries

All operations must keep existing boundary guarantees and extend them to new operations:

- Accept relative paths only.
- Reject absolute paths, empty path segments, `.`, `..`, and traversal before normalization.
- Resolve source, destination, and parent directories before action.
- Reject symlinked source files, symlinked destination parents, and any resolved path outside the configured root.
- Operate only on regular files; do not touch directories, sockets, devices, FIFOs, or recursive directory trees.
- Default `overwrite=false` for copy/move/import.
- Preserve read-only mode behavior for mutating operations.
- Keep audit/tool outputs to action, path labels, bytes, and status; never log or return file content for copy/move/delete/import.

### FR-9: Scanning and size limits

- Preserve `max_file_bytes` checks for every read/write/copy/move/import path.
- Preserve secret-shaped and optional prompt-injection scans for text writes/patches.
- For text copy/import into workspace, scan the materialized content when it is within `max_file_bytes`.
- Do not scan raw binary as text; rely on extension, size, root, and regular-file constraints.

### FR-10: Tool registration and docs

- Register all new tools under toolset `workspace_file`.
- Do not add `workspace_file` tools to `_HERMES_CORE_TOOLS`.
- Update tests so `resolve_toolset("workspace_file")` includes existing + new tool names.
- Update any minimal user/developer docs needed to explain profile-scoped workspace file policy.

## 6. Out of scope / explicit non-approvals

This PRD does not approve:

- Implementation work before PRD quality, architect teach-back, technical design, and user approval complete.
- Enabling `workspace_file` for default, Satine, Skywalker, or any new profile/platform.
- Editing live profile config files.
- Restarting any Gateway.
- Granting full `file`, `terminal`, `web`, `search`, GitHub, delegation, or messaging access to Samiya.
- Network download/fetch behavior. That belongs to `media_fetch` or a separately approved tool.
- Directory recursive copy/move/delete.
- Public hosting, upload, rendering, or delivery of media files.
- Raw binary/base64 read or write through model-visible JSON arguments.
- Production config writes, live/default-on rollout, or broad runtime behavior changes.

## 7. Non-functional requirements

- Profile isolation: every root resolves under active `HERMES_HOME` unless a separately approved config mode says otherwise; this feature should not create cross-profile access.
- Low intrusion: no Gateway, platform adapter, scheduler, or service lifecycle changes in the implementation slice unless later technical design proves they are needed and user approves.
- Backward compatibility: existing text workflows and legacy `allowed_extensions` configs keep working.
- Security posture: fail closed on malformed config, traversal, symlinks, oversized files, disallowed extensions, and unsafe source/destination paths.
- Evidence before claims: behavior is proven by focused pytest cases plus relevant local gates before PR/approval.

## 8. Acceptance criteria

A later implementation PR may request review only when all relevant criteria pass:

1. Existing `workspace_file` tests still pass.
2. RED/GREEN tests prove each new tool behavior: stat, copy, move, delete-to-trash, permanent-delete policy, import roots.
3. Tests prove config migration/normalization for `file_type_policy`, legacy `allowed_extensions`, lowercase suffix handling, `allowlist`, `denylist`, and `all`.
4. Tests prove default media/text allowlist preserves current `.csv` compatibility and includes `.jpeg`, `.webp`, `.wav`, and the full approved media set.
5. Tests prove optional formats are not default-allowed unless configured.
6. Tests prove binary/media read/search does not dump raw bytes/base64 into tool output.
7. Tests prove traversal and symlink escapes fail for every new source and destination path.
8. Tests prove regular-file-only behavior rejects directories and special files where portable.
9. Tests prove overwrite defaults to false for copy/move/import and requires explicit opt-in.
10. Tests prove read-only mode blocks mutating operations.
11. Toolset registration tests prove new tools are discoverable under `workspace_file` and remain out of core tools.
12. Focused command passes: `python -m pytest tests/tools/test_workspace_file_tool.py -q`.
13. Broader relevant gate passes before PR readiness: at minimum `python -m pytest tests/tools/test_workspace_file_tool.py -q`, `git diff --check`, tool registration discovery for `workspace_file`, and a targeted static scan proving no new `terminal`/shell/Gateway/platform/restart/network-download surface was added. Any unrelated baseline failure must be classified honestly before PR readiness.
14. Independent blocker-only review on the final pushed head reports no blockers.

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Binary files flood the model context | Return metadata/media markers only; no raw bytes/base64 by default. |
| Symlink or traversal escape | Apply existing root/path resolution checks to every source, destination, trash, and import root. |
| Delete is too destructive | Trash by default; permanent delete gated by config/explicit flag. |
| `mode: all` becomes filesystem free-for-all | `all` disables only extension filtering; path/root/symlink/regular-file/size/operation checks remain mandatory. |
| Legacy configs break | Treat `allowed_extensions` as compatibility input when `file_type_policy` is absent. |
| Media feature drifts into download/render/delivery | Keep network fetch and delivery out of scope; cite `media_fetch` and platform delivery as separate approvals. |

## 10. Open questions for architect teach-back

No P0 open questions are known. The architect should still teach back these design decisions before technical design:

- How to classify text-like versus binary/media files without creating an unsafe parser surface.
- Whether `workspace_read` should return a generic file marker or only metadata for binary/media files.
- Whether permanent delete should be config-disabled by default or allowed with `permanent=true` plus audit metadata.
- Whether docs changes should be limited to tool docs/tests or also profile configuration examples.

## 11. Suggested narrow approval phrase for later implementation

After PRD quality review, architect teach-back, technical design, and technical review pass, the implementation approval should be no broader than:

> Approve implementing the profile-scoped `workspace_file` management extension in a dedicated Sachima worktree, limited to tool code, tests, and minimal docs; no live config edits, no Gateway restart, no profile enablement changes, no broad file/terminal access, no network fetch, no media delivery, and no production rollout.
