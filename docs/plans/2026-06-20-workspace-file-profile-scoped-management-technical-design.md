**1. VERDICT**

DESIGN_READY_FOR_CODE_REVIEW

No PRD change required after reviewer-blocker remediation. P2 questions are resolved with fail-closed defaults. Baseline focused tests are executable via `uv run --extra dev`; this worktree verified the existing test file passes (`11 passed`).

**2. Scope/Non-Approval Restatement**

Current roadmap position: P5 Temporal PR B pre-development governance is the current allowed docs-only gate; direct implementation/runtime remains separately gated. This workspace-file task is allowed only as technical design + implementation plan.

Non-approvals preserved: no Gateway restart/reload, no live profile config edits, no profile enablement changes, no broad `file`/`terminal`/network/search access, no media fetch/delivery/rendering/hosting, no production rollout, no recursive directory operations, no raw binary/base64 through JSON.

The requested later code slice should touch only:
- `tools/workspace_file_tool.py`
- `tests/tools/test_workspace_file_tool.py`
- optional minimal docs: `docs/runbooks/workspace-file-profile-scoped-management.md`

`toolsets.py` should not need a static-list edit: `get_toolset()` already merges registry names for existing toolsets. The implementation should rely on `registry.register(..., toolset="workspace_file")` and prove discoverability via tests.

`phase-gate-drift-control` is named by project guidance but is not available in this Codex skill set, so I applied the roadmap preflight manually.

**3. P2 Open-Question Decisions**

- OQ-1: Import applies source-root policy AND workspace destination policy; either rejection fails closed.
- OQ-2: Explicit `file_type_policy` wins over legacy `allowed_extensions`.
- OQ-3: Explicit config replaces defaults, not merges.
- OQ-4: Copy/move/import enforce destination extension policy; source policy also applies.
- OQ-5: `workspace_read` on binary/media returns metadata only, no marker implying hosting/delivery.
- OQ-6: Text/binary classification is extension-first. Known text only: `.md .txt .json .yaml .yml .csv`. Everything else is metadata-only for read/search, even in `mode: all`.
- OQ-7: Permanent delete disabled by default; allowed only with `delete.allow_permanent: true` plus `permanent=true`.
- OQ-8: Trash uses workspace-local `.trash/<original-parent>/<name>.deleted.<timestamp>.<token>` collision avoidance.
- OQ-9: Docs scope is one minimal runbook/policy page, no live profile config changes.

**4. Proposed Architecture And Helpers/Classes**

Keep one module: `tools/workspace_file_tool.py`.

Add:
- `@dataclass(frozen=True) FileTypePolicy(mode: str, extensions: frozenset[str])`
- `_DEFAULT_FILE_TYPE_EXTENSIONS`: exact FR-4 default set plus `.csv` to preserve current no-config compatibility; exclude optional formats.
- `_TEXT_LIKE_EXTENSIONS`: `.md .txt .json .yaml .yml .csv`
- `_normalize_extension(ext: object) -> str`
- `_parse_file_type_policy(raw, *, fallback_extensions, default_extensions) -> FileTypePolicy`
- `_effective_file_type_policy(cfg) -> FileTypePolicy`
- `_check_extension_allowed(path: Path, policy: FileTypePolicy, *, label: str) -> None`
- `_is_text_like_path(path: Path) -> bool`
- `_file_metadata(root: Path, target: Path, *, kind: str | None = None) -> dict`
- `_require_regular_file(path: Path) -> None`
- `_check_file_size(path: Path, cfg: dict[str, Any]) -> None`
- `_resolve_workspace_source(path, cfg=None) -> tuple[Path, Path, dict]`
- `_resolve_workspace_destination(path, cfg, *, overwrite) -> Path`
- `_resolve_import_source(source_root, source_path, cfg) -> tuple[Path, Path, FileTypePolicy]`
- `_atomic_binary_copy(src: Path, dst: Path) -> None`
- `_scan_text_file_for_copy(path: Path, cfg: dict) -> str | None`
- `_trash_target(root: Path, target: Path, cfg: dict) -> Path`

Update existing helpers:
- `_load_config()` parses `file_type_policy`, `import_roots`, and `delete`; malformed explicit policy fails closed.
- `_allowed_extensions()` becomes compatibility wrapper over `_effective_file_type_policy()` for existing callers or is replaced by policy checks.
- `_resolve_target()` gets an operation mode: existing write/patch require text-like paths; read/stat/copy/move/delete/import allow any policy-approved regular file.

**5. Tool/API Schema Plan**

Register under `workspace_file`. Do not edit `toolsets.py` unless implementation discovers a real static-registration gap; current `get_toolset()` merges registry tool names for existing toolsets. Do not add any new name to `_HERMES_CORE_TOOLS`.

New tools:
- `workspace_stat(path: str)` -> metadata only.
- `workspace_copy(src_path: str, dst_path: str, overwrite: bool = false)` -> `{success, action:"copied", src_path, dst_path, bytes, backup?}`.
- `workspace_move(src_path: str, dst_path: str, overwrite: bool = false)` -> metadata only; copy-then-unlink after validation.
- `workspace_delete(path: str, permanent: bool = false)` -> default trash; permanent only with config.
- `workspace_import(source_root: str, source_path: str, dst_path: str, overwrite: bool = false)` -> copy from configured read-only import root into workspace.

Existing tools:
- `workspace_list`: include all policy-allowed regular files, not content.
- `workspace_read`: text-like returns paginated content; binary/media returns metadata with `text: false`, no bytes/base64.
- `workspace_search`: searches text-like only; returns `skipped_binary` count.
- `workspace_write`/`workspace_patch`: remain text-only, scan text, reject media/binary extensions even when policy allows them for file management.

**6. Test Strategy Mapped To FR/AC IDs**

- FR-1, FR-10, AC-11: registration under `workspace_file`, not core.
- FR-2, AC-2: stat/copy/move/delete/import behavior tests.
- FR-3, FR-4, AC-3/4/5: policy precedence, normalization, modes, defaults including `.csv` compatibility, optional exclusions.
- FR-5, AC-6: binary/media read/search metadata-only tests.
- FR-6, AC-2/7/9: import root allowlist/intersection/traversal tests.
- FR-7, AC-2/10: trash default and permanent-delete config gate tests.
- FR-8, AC-7/8/9/10: traversal, symlink, regular-file-only, overwrite default, read-only mode.
- FR-9, AC-7/10: max size and text scan on copy/move/import.
- AC-1/12/13/14: existing tests, focused test command, static forbidden-surface scan, independent review.

**7. Bite-Sized TDD Implementation Tasks**

1. Policy parsing/defaults  
RED: add tests for explicit policy winning over legacy, lowercase/bare extension normalization, allowlist/denylist/all, FR-4 defaults plus `.csv` compatibility, optional `.svg/.psd/.tiff` excluded.  
Expected failure: media extensions rejected or helper/schema missing.  
GREEN: add `FileTypePolicy` and policy helpers; wire existing list/read/search through policy.  
Verify: `uv run --extra dev python -m pytest tests/tools/test_workspace_file_tool.py -q`.

2. Text/media read/search/stat  
RED: tests for `workspace_stat`, binary `workspace_read` metadata-only, `workspace_search` skips media with count.  
Expected failure: `workspace_stat` import missing; binary read dumps replacement text or errors.  
GREEN: add metadata helpers, `workspace_stat`, update read/search behavior.  
Verify focused file.

3. Shared source/destination safety  
RED: tests every new mutating op rejects absolute paths, `..`, `.` segments, symlinked source, symlinked destination parent, directories, and same src/dst.  
Expected failure: functions missing.  
GREEN: add `_resolve_workspace_source`, `_resolve_workspace_destination`, `_require_regular_file`; reuse in later ops.  
Verify focused file.

4. Copy  
RED: tests copy defaults `overwrite=false`, explicit overwrite, destination extension guard, size guard, text scan on copied `.md`, binary copy no content output.  
Expected failure: `workspace_copy` missing.  
GREEN: implement `workspace_copy` with atomic binary copy and optional backup on overwrite.  
Verify focused file.

5. Move  
RED: tests move preserves bytes, removes source only after successful destination write, rejects overwrite by default, rejects oversized source before unlink, honors read-only mode.  
Expected failure: `workspace_move` missing.  
GREEN: implement validated copy-then-unlink semantics.  
Verify focused file.

6. Delete  
RED: tests default trash path, collision-safe trash names, metadata-only output, permanent rejected by default, permanent allowed only with `delete.allow_permanent: true`, read-only mode blocks, symlinked `.trash`/trash-parent escape is rejected before source unlink.  
Expected failure: `workspace_delete` missing.  
GREEN: implement trash helper and delete policy parser.  
Verify focused file.

7. Import roots  
RED: tests unknown source root rejects, import-root config escape outside `HERMES_HOME` rejects, symlinked import root/parent rejects, source traversal rejects, source-root policy + workspace policy intersection, text import scan, binary import allowed by policy, no source mutation.  
Expected failure: `workspace_import` missing.  
GREEN: implement import root resolver and import copy path.  
Verify focused file.

8. Registration/docs  
RED: update registration test to expect existing five plus new five tools; assert dynamic `resolve_toolset("workspace_file")` sees registry names and none are in `_HERMES_CORE_TOOLS`; docs test optional via simple path/content assertion if project pattern accepts it.  
Expected failure: toolset lacks names.  
GREEN: add schemas/register calls and minimal runbook; avoid `toolsets.py` unless a real static-registration gap is proven.  
Verify focused file plus static scans.

**8. Verification Gates**

Use `uv run --extra dev` if the shared Hermes venv lacks pytest; this was verified in this worktree on 2026-06-20 (`11 passed`). The implementation gate can use either `uv run --extra dev python -m pytest ...` or `scripts/run_tests.sh ...` after a suitable project `.venv` exists:

```bash
uv run --extra dev python -m pytest tests/tools/test_workspace_file_tool.py -q
git diff --check
python - <<'PY'
from tools.registry import discover_builtin_tools, registry
from toolsets import _HERMES_CORE_TOOLS, resolve_toolset
discover_builtin_tools()
expected = {"workspace_list","workspace_read","workspace_search","workspace_write","workspace_patch","workspace_stat","workspace_copy","workspace_move","workspace_delete","workspace_import"}
assert expected <= set(resolve_toolset("workspace_file"))
assert not (expected & set(_HERMES_CORE_TOOLS))
for name in expected:
    assert registry.get_entry(name).toolset == "workspace_file"
PY
```

Targeted forbidden-surface scan:

```bash
git diff --name-only | rg -n '^(gateway/|plugins/|hermes_cli/profiles.py|.*config.yaml|.*\\.env|scripts/)' && exit 1 || true
git diff -U0 -- tools/workspace_file_tool.py tests/tools/test_workspace_file_tool.py docs/runbooks/workspace-file-profile-scoped-management.md \
  | rg '^\+.*\b(subprocess|socket|requests|httpx|aiohttp|urllib\.request|webbrowser|base64|b64encode|b64decode|gateway|platforms|send_message|media_fetch|terminal|execute_code|acpx|npx|SACHIMA_SEND_URL|FEISHU|restart|reload)\b' \
  && exit 1 || true
```

Baseline note from this pre-development run: `scripts/run_tests.sh tests/tools/test_workspace_file_tool.py` initially failed with the shared Hermes venv because `/home/ecs-user/.hermes/hermes-agent/venv/bin/python` has no `pytest`; `uv run --extra dev python -m pytest tests/tools/test_workspace_file_tool.py -q` created a worktree `.venv` and passed (`11 passed in 1.55s`).

**9. Risks/Tails**

- WATCH: `mode: all` must be reviewed carefully; it disables only extension filtering, not path/root/symlink/regular-file/size checks.
- NEXT_PHASE: profile enablement or live Samiya config changes remain separate approval.
- NEXT_PHASE: media download/render/delivery remains separate `media_fetch` or platform-delivery work.
- PARKED: recursive directory operations.
- BLOCKER: none for technical design.

Rollback/compatibility: no migration required. Reverting the later PR removes new schemas/helpers/toolset names. Existing legacy `allowed_extensions` configs keep working when `file_type_policy` is absent. Trash soft delete is operator-reversible; permanent delete remains opt-in.

**10. Exact Implementation Approval Phrase To Request Later**

Approve implementing the profile-scoped `workspace_file` management extension in a dedicated Sachima worktree, limited to tool code, tests, and minimal docs; no live config edits, no Gateway restart, no profile enablement changes, no broad file/terminal access, no network fetch, no media delivery, and no production rollout.