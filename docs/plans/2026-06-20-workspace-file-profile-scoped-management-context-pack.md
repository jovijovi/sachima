# Workspace file implementation context pack

## Current code shape

`tools/workspace_file_tool.py` is a 506-line profile-scoped tool module.

Existing config defaults:

```python
_DEFAULT_CONFIG = {
    "root": "workspace",
    "mode": "read_write",
    "allowed_extensions": [".md", ".txt", ".json", ".yaml", ".yml", ".csv"],
    "max_file_bytes": 262_144,
    "max_output_chars": 20_000,
    "backups": True,
    "allow_absolute_root": False,
    "scan": {"secrets": True, "prompt_injection": False},
}
```

Important helpers:

- `_load_config()`: reads `$HERMES_HOME/config.yaml`, merges `workspace_file`, validates legacy `allowed_extensions`, int-casts size/output caps.
- `_workspace_root(cfg)`: resolves `root` under active `get_hermes_home()`, rejects root escape unless `allow_absolute_root` and still requires root under home.
- `_safe_relative_path(path)`: rejects empty, absolute, `.`/`..`, empty segments, traversal.
- `_allowed_extensions(cfg)`: returns set from legacy `allowed_extensions`.
- `_resolve_target(path, must_exist=False)`: loads config, checks suffix, creates root, resolves parent and target, rejects symlink target/escape.
- `_resolve_base(path, cfg=None)`: resolves list/search base, rejects symlink base/escape.
- `_check_write_mode(cfg)`: only `read_write` allows mutating text ops.
- `_scan_content(content,cfg)`: secret-shaped and optional prompt-injection scan.
- `_atomic_text_write(target, content)`: fsync temp + atomic replace.
- `_make_backup(target, enabled)`: safe text backup with O_EXCL.

Existing tools:

- `workspace_list(path="", recursive=True)`: lists allowed files by suffix.
- `workspace_read(path, offset=1, limit=500)`: reads text lines with pagination; assumes UTF-8 text.
- `workspace_search(pattern, path="", max_results=50)`: regex search text files.
- `workspace_write(path, content, overwrite=True)`: text write, scan, optional backup.
- `workspace_patch(path, old_string, new_string, replace_all=False)`: text patch, scan, backup.

Existing schemas/register calls are simple constants at bottom, all registered under toolset `workspace_file`. Test `test_workspace_toolset_is_registered_but_not_core` expects only the existing five tools and asserts `workspace_read` is not in `_HERMES_CORE_TOOLS`.

## Current tests

`tests/tools/test_workspace_file_tool.py` already covers:

- active profile `HERMES_HOME` scoping for write/read;
- configured relative root;
- path escape and symlink escape rejection;
- configured root escape and symlinked root escape rejection;
- disallowed extension and oversized write;
- secret-shaped content scan;
- patch backup and symlink backup safety;
- list/search;
- toolset registration and not-core assertion.

## Live config baseline checked 2026-06-20

- default profile: no `workspace_file`, no platform enables it.
- Samiya profile: `workspace_file` enabled for Feishu; legacy `allowed_extensions` currently text/csv only.
- Satine profile: no `workspace_file`, no platform enables it.

## Constraints from user/governance

- Extend existing generic `workspace_file` directly; no new Samiya-only or parallel `workspace_ops` toolset.
- New default allowlist includes common text/image/audio/video extensions from PRD while preserving current `.csv` compatibility.
- Optional formats remain optional (`.svg`, `.psd`, `.ai`, `.tif/.tiff`, `.exr`, `.ts/.m2ts`, etc.).
- Do not enable tools for profiles, edit live config, restart Gateway, or implement before user approval.
