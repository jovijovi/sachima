import json
from pathlib import Path


def _parse(result: str) -> dict:
    return json.loads(result)


class FakeHeaders(dict):
    def get_content_type(self):
        return self.get("content-type", "application/octet-stream").split(";", 1)[0]


class FakeResponse:
    def __init__(self, body: bytes, *, url="https://example.com/cat.png", headers=None, status=200):
        self._body = body
        self._pos = 0
        self.url = url
        self.status = status
        self.headers = FakeHeaders(headers or {})

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            size = len(self._body) - self._pos
        chunk = self._body[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk

    def geturl(self):
        return self.url

    def getcode(self):
        return self.status

    def close(self):
        pass


def test_media_fetch_downloads_image_to_profile_workspace_with_media_marker(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    png = b"\x89PNG\r\n\x1a\n" + b"image-bytes"

    def fake_open(parsed, timeout=None, addresses=None):
        assert parsed.geturl() == "https://example.com/cat.png"
        assert addresses == ["93.184.216.34"]
        return FakeResponse(
            png,
            headers={"content-type": "image/png", "content-length": str(len(png))},
        )

    from tools import media_fetch_tool
    monkeypatch.setattr(media_fetch_tool, "_open_once", fake_open)
    monkeypatch.setattr(media_fetch_tool, "_resolve_public_host", lambda hostname: ["93.184.216.34"])

    result = _parse(media_fetch_tool.media_fetch_url("https://example.com/cat.png"))

    assert result["success"] is True
    assert result["kind"] == "image"
    assert result["mime"] == "image/png"
    assert result["bytes"] == len(png)
    assert result["path"].endswith("workspace/media/images/cat.png")
    assert result["media_marker"] == f"MEDIA:{result['path']}"
    assert Path(result["path"]).read_bytes() == png


def test_media_fetch_rejects_non_https_and_private_hosts(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profiles" / "samiya"))

    from tools import media_fetch_tool

    insecure = _parse(media_fetch_tool.media_fetch_url("http://example.com/cat.png"))
    assert insecure["success"] is False
    assert "https" in insecure["error"].lower()

    private = _parse(media_fetch_tool.media_fetch_url("https://127.0.0.1/cat.png"))
    assert private["success"] is False
    assert "public" in private["error"].lower() or "private" in private["error"].lower()


def test_media_fetch_connects_to_validated_public_ip_not_hostname(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profiles" / "samiya"))

    from tools import media_fetch_tool
    monkeypatch.setattr(media_fetch_tool, "_resolve_public_host", lambda hostname: ["93.184.216.34"])
    attempts = []

    def fake_create_connection(address, timeout=None):
        attempts.append(address)
        raise OSError("stop-before-network")

    monkeypatch.setattr(media_fetch_tool.socket, "create_connection", fake_create_connection)

    result = _parse(media_fetch_tool.media_fetch_url("https://example.com/cat.png"))

    assert result["success"] is False
    assert "stop-before-network" in result["error"]
    assert attempts == [("93.184.216.34", 443)]


def test_media_fetch_rejects_redirect_to_private_host(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profiles" / "samiya"))

    from tools import media_fetch_tool
    monkeypatch.setattr(media_fetch_tool, "_resolve_public_host", lambda hostname: ["93.184.216.34"] if hostname == "example.com" else (_ for _ in ()).throw(ValueError("URL host must resolve only to public IP addresses")))

    calls = []

    def fake_open(parsed, timeout=None, addresses=None):
        calls.append(parsed.geturl())
        return FakeResponse(
            b"",
            headers={"Location": "https://127.0.0.1/evil.png"},
            status=302,
        )

    monkeypatch.setattr(media_fetch_tool, "_open_once", fake_open)

    result = _parse(media_fetch_tool.media_fetch_url("https://example.com/cat.png"))

    assert result["success"] is False
    assert "public" in result["error"].lower()
    assert calls == ["https://example.com/cat.png"]


def test_media_fetch_rejects_oversized_content_length_before_download(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    profile_home.mkdir(parents=True)
    (profile_home / "config.yaml").write_text(
        "media_fetch:\n"
        "  image_max_bytes: 8\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools import media_fetch_tool
    monkeypatch.setattr(media_fetch_tool, "_resolve_public_host", lambda hostname: ["93.184.216.34"])

    opened = False

    def fake_open(parsed, timeout=None, addresses=None):
        nonlocal opened
        opened = True
        return FakeResponse(
            b"",
            headers={"content-type": "image/png", "content-length": "9"},
        )

    monkeypatch.setattr(media_fetch_tool, "_open_once", fake_open)

    result = _parse(media_fetch_tool.media_fetch_url("https://example.com/big.png"))

    assert opened is True
    assert result["success"] is False
    assert "exceeds" in result["error"]
    assert not list((profile_home / "workspace").glob("**/*"))


def test_media_fetch_rejects_magic_mismatch_and_cleans_temp_file(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools import media_fetch_tool
    monkeypatch.setattr(media_fetch_tool, "_resolve_public_host", lambda hostname: ["93.184.216.34"])
    monkeypatch.setattr(
        media_fetch_tool,
        "_open_once",
        lambda parsed, timeout=None, addresses=None: FakeResponse(
            b"not really a png",
            headers={"content-type": "image/png", "content-length": "16"},
        ),
    )

    result = _parse(media_fetch_tool.media_fetch_url("https://example.com/fake.png"))

    assert result["success"] is False
    assert "magic" in result["error"].lower() or "does not match" in result["error"].lower()
    media_root = profile_home / "workspace" / "media"
    assert not list(media_root.glob("**/*")) if media_root.exists() else True


def test_media_fetch_supports_video_with_2gib_default_limit(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"video-bytes"

    from tools import media_fetch_tool
    monkeypatch.setattr(media_fetch_tool, "_resolve_public_host", lambda hostname: ["93.184.216.34"])
    monkeypatch.setattr(
        media_fetch_tool,
        "_open_once",
        lambda parsed, timeout=None, addresses=None: FakeResponse(
            mp4,
            url="https://example.com/clip.mp4",
            headers={"content-type": "video/mp4", "content-length": str(len(mp4))},
        ),
    )

    result = _parse(media_fetch_tool.media_fetch_url("https://example.com/clip.mp4"))

    assert result["success"] is True
    assert result["kind"] == "video"
    assert result["max_bytes"] == 2 * 1024 * 1024 * 1024
    assert result["path"].endswith("workspace/media/videos/clip.mp4")
    assert Path(result["path"]).read_bytes() == mp4


def test_media_list_and_delete_are_scoped(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    media_dir = profile_home / "workspace" / "media" / "images"
    media_dir.mkdir(parents=True)
    target = media_dir / "cat.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\nbytes")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"nope")
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.media_fetch_tool import media_delete, media_list

    listed = _parse(media_list())
    escape = _parse(media_delete("../outside.png"))
    deleted = _parse(media_delete("images/cat.png"))

    assert listed["success"] is True
    assert listed["files"][0]["path"] == "images/cat.png"
    assert escape["success"] is False
    assert deleted["success"] is True
    assert not target.exists()
    assert outside.exists()


def test_media_fetch_root_is_canonical_and_rejects_symlinked_workspace(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    profile_home.mkdir(parents=True)
    (profile_home / "config.yaml").write_text(
        "media_fetch:\n"
        "  root: other-media\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    png = b"\x89PNG\r\n\x1a\n" + b"image-bytes"
    from tools import media_fetch_tool
    monkeypatch.setattr(media_fetch_tool, "_resolve_public_host", lambda hostname: ["93.184.216.34"])
    monkeypatch.setattr(
        media_fetch_tool,
        "_open_once",
        lambda parsed, timeout=None, addresses=None: FakeResponse(
            png,
            headers={"content-type": "image/png", "content-length": str(len(png))},
        ),
    )

    result = _parse(media_fetch_tool.media_fetch_url("https://example.com/cat.png"))

    assert result["success"] is True
    assert result["path"].endswith("workspace/media/images/cat.png")
    assert not (profile_home / "other-media").exists()

    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = profile_home / "workspace"
    for item in sorted(workspace.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        item.unlink() if item.is_file() else item.rmdir()
    workspace.rmdir()
    workspace.symlink_to(outside, target_is_directory=True)

    listed = _parse(media_fetch_tool.media_list())

    assert listed["success"] is False
    assert "symlink" in listed["error"].lower()


def test_media_fetch_rejects_broken_symlinked_workspace(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    profile_home.mkdir(parents=True)
    (profile_home / "workspace").symlink_to(profile_home / "missing-target", target_is_directory=True)
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools import media_fetch_tool

    listed = _parse(media_fetch_tool.media_list())

    assert listed["success"] is False
    assert "symlink" in listed["error"].lower()


def test_media_fetch_toolset_is_registered_but_not_core(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile"))

    from tools.registry import discover_builtin_tools, registry
    from toolsets import _HERMES_CORE_TOOLS, resolve_toolset

    discover_builtin_tools()

    resolved = resolve_toolset("media_fetch")
    assert set(resolved) == {"media_fetch_url", "media_list", "media_delete"}
    assert "media_fetch_url" not in _HERMES_CORE_TOOLS
    entry = registry.get_entry("media_fetch_url")
    assert entry is not None
    assert entry.toolset == "media_fetch"
