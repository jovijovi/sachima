import json
from pathlib import Path


def _parse(result: str) -> dict:
    return json.loads(result)


def test_workspace_write_and_read_are_scoped_to_active_profile_home(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.workspace_file_tool import workspace_read, workspace_write

    written = _parse(workspace_write("notes/hello.md", "# Hello\n\nPrivate scratch note."))

    assert written["success"] is True
    assert written["path"] == "notes/hello.md"
    target = profile_home / "workspace" / "notes" / "hello.md"
    assert target.read_text(encoding="utf-8") == "# Hello\n\nPrivate scratch note."

    read = _parse(workspace_read("notes/hello.md"))

    assert read["success"] is True
    assert read["path"] == "notes/hello.md"
    assert "Private scratch note" in read["content"]


def test_workspace_uses_configured_relative_root(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    profile_home.mkdir(parents=True)
    (profile_home / "config.yaml").write_text(
        "workspace_file:\n"
        "  root: private-desk\n"
        "  max_file_bytes: 1024\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.workspace_file_tool import workspace_write

    result = _parse(workspace_write("note.txt", "configured root"))

    assert result["success"] is True
    assert (profile_home / "private-desk" / "note.txt").exists()
    assert not (profile_home / "workspace" / "note.txt").exists()


def test_workspace_rejects_path_escape_and_symlink_escape(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    workspace_root = profile_home / "workspace"
    workspace_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace_root / "escape").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.workspace_file_tool import workspace_write

    absolute = _parse(workspace_write(str(outside / "evil.md"), "nope"))
    traversal = _parse(workspace_write("../evil.md", "nope"))
    dot_segment = _parse(workspace_write("notes/./evil.md", "nope"))
    symlink = _parse(workspace_write("escape/evil.md", "nope"))

    assert absolute["success"] is False
    assert traversal["success"] is False
    assert dot_segment["success"] is False
    assert symlink["success"] is False
    assert not (outside / "evil.md").exists()


def test_workspace_rejects_configured_root_escape(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    profile_home.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (profile_home / "config.yaml").write_text(
        "workspace_file:\n"
        "  root: ../../outside\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.workspace_file_tool import workspace_write

    result = _parse(workspace_write("evil.md", "nope"))

    assert result["success"] is False
    assert not (outside / "evil.md").exists()


def test_workspace_rejects_symlinked_root_escape(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    outside = tmp_path / "outside"
    outside.mkdir()
    (profile_home).mkdir(parents=True)
    (profile_home / "workspace").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.workspace_file_tool import workspace_write

    result = _parse(workspace_write("evil.md", "nope"))

    assert result["success"] is False
    assert not (outside / "evil.md").exists()


def test_workspace_rejects_disallowed_extensions_and_oversized_writes(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    profile_home.mkdir(parents=True)
    (profile_home / "config.yaml").write_text(
        "workspace_file:\n"
        "  max_file_bytes: 8\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.workspace_file_tool import workspace_write

    disallowed = _parse(workspace_write("script.py", "print('nope')"))
    oversized = _parse(workspace_write("notes.txt", "0123456789"))

    assert disallowed["success"] is False
    assert oversized["success"] is False


def test_workspace_rejects_secret_shaped_content_when_scan_enabled(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.workspace_file_tool import workspace_write

    secret_value = "OPENAI_" + "API_" + "KEY=" + "synthetic-secret-value"
    secret = _parse(workspace_write("secret.md", secret_value))

    assert secret["success"] is False
    assert not (profile_home / "workspace" / "secret.md").exists()


def test_workspace_patch_creates_backup_and_updates_unique_text(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.workspace_file_tool import workspace_patch, workspace_write

    assert _parse(workspace_write("notes/comfort.md", "old phrase"))["success"] is True

    patched = _parse(workspace_patch("notes/comfort.md", "old phrase", "new phrase"))

    assert patched["success"] is True
    target = profile_home / "workspace" / "notes" / "comfort.md"
    assert target.read_text(encoding="utf-8") == "new phrase"
    assert list(target.parent.glob("comfort.md.bak.*"))


def test_workspace_backup_avoids_preexisting_symlink_path(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools import workspace_file_tool

    target_dir = profile_home / "workspace" / "notes"
    target_dir.mkdir(parents=True)
    target = target_dir / "comfort.md"
    target.write_text("old phrase", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside original", encoding="utf-8")
    planted = target_dir / "comfort.md.bak.1234.badc0de0"
    planted.symlink_to(outside)
    tokens = iter(["badc0de0", "cafebabe"])
    monkeypatch.setattr(workspace_file_tool.time, "time", lambda: 1234)
    monkeypatch.setattr(workspace_file_tool.secrets, "token_hex", lambda n: next(tokens))

    patched = _parse(workspace_file_tool.workspace_patch("notes/comfort.md", "old phrase", "new phrase"))

    assert patched["success"] is True
    assert target.read_text(encoding="utf-8") == "new phrase"
    assert outside.read_text(encoding="utf-8") == "outside original"
    assert (target_dir / "comfort.md.bak.1234.cafebabe").read_text(encoding="utf-8") == "old phrase"


def test_workspace_list_and_search(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.workspace_file_tool import workspace_list, workspace_search, workspace_write

    assert _parse(workspace_write("notes/a.md", "alpha\nneedle"))["success"] is True
    assert _parse(workspace_write("notes/b.txt", "beta"))["success"] is True

    listed = _parse(workspace_list())
    searched = _parse(workspace_search("needle"))

    assert listed["success"] is True
    assert listed["files"] == ["notes/a.md", "notes/b.txt"]
    assert searched["success"] is True
    assert searched["matches"] == [{"path": "notes/a.md", "line": 2, "content": "needle"}]


def test_workspace_toolset_is_registered_but_not_core(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile"))

    from tools.registry import discover_builtin_tools, registry
    from toolsets import _HERMES_CORE_TOOLS, resolve_toolset

    discover_builtin_tools()

    resolved = resolve_toolset("workspace_file")
    assert set(resolved) == {
        "workspace_list",
        "workspace_read",
        "workspace_search",
        "workspace_write",
        "workspace_patch",
    }
    assert "workspace_read" not in _HERMES_CORE_TOOLS
    entry = registry.get_entry("workspace_read")
    assert entry is not None
    assert entry.toolset == "workspace_file"
