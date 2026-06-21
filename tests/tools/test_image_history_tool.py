from __future__ import annotations

import json


def _write_manifest(monkeypatch, tmp_path, records):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from tools.image_manifest import default_manifest_path

    path = default_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def _record(record_id, *, ts, tool, success, prompt, content_summary=None, image=None):
    return {
        "schema_version": 1,
        "record_id": record_id,
        "ts": ts,
        "profile": "default",
        "tool": tool,
        "operation": "edit" if tool == "image_edit" else "generate",
        "backend": "fake",
        "request": {
            "prompt": prompt,
            "prompt_chars": len(prompt),
            "aspect_ratio": "square",
            "normalized_args": {"aspect_ratio": "square"},
            **({"content_summary": content_summary} if content_summary else {}),
        },
        "input_images": [],
        "result": {
            "success": success,
            "duration_ms": 12,
            "outputs": [{"kind": "image", "ref": image}] if success and image else [],
        },
        "error": None if success else {"error_type": "ValueError", "message": "failed"},
    }


def test_image_history_latest_and_limit(monkeypatch, tmp_path):
    _write_manifest(
        monkeypatch,
        tmp_path,
        [
            _record("old", ts="2026-06-20T01:00:00Z", tool="image_generate", success=True, prompt="old"),
            _record("mid", ts="2026-06-20T02:00:00Z", tool="image_edit", success=True, prompt="mid"),
            _record("new", ts="2026-06-20T03:00:00Z", tool="image_generate", success=True, prompt="new"),
        ],
    )

    from tools.image_history_tool import _handle_image_history

    payload = json.loads(_handle_image_history({"latest": True, "limit": 2}))

    assert payload["success"] is True
    assert payload["count"] == 2
    assert [record["record_id"] for record in payload["records"]] == ["new", "mid"]


def test_image_history_filters_by_tool_success_and_content_search(monkeypatch, tmp_path):
    _write_manifest(
        monkeypatch,
        tmp_path,
        [
            _record("dragon", ts="2026-06-20T01:00:00Z", tool="image_generate", success=True, prompt="red dragon"),
            _record(
                "blue-failure",
                ts="2026-06-20T02:00:00Z",
                tool="image_edit",
                success=False,
                prompt="fix logo",
                content_summary="blue logo draft",
            ),
            _record("green", ts="2026-06-20T03:00:00Z", tool="image_edit", success=True, prompt="green logo"),
        ],
    )

    from tools.image_history_tool import _handle_image_history

    payload = json.loads(
        _handle_image_history(
            {
                "tool": "image_edit",
                "success": False,
                "content_search": "blue",
                "limit": 10,
            }
        )
    )

    assert payload["success"] is True
    assert payload["count"] == 1
    assert payload["records"][0]["record_id"] == "blue-failure"
    assert payload["records"][0]["content_summary"] == "blue logo draft"
    assert payload["records"][0]["error_type"] == "ValueError"


def test_image_history_sanitizes_legacy_records_on_read(monkeypatch, tmp_path):
    _write_manifest(
        monkeypatch,
        tmp_path,
        [
            {
                "schema_version": 1,
                "record_id": "legacy-leaky",
                "ts": "2026-06-20T04:00:00Z",
                "profile": "default",
                "tool": "image_generate",
                "operation": "generate",
                "backend": {
                    "provider": "https://user:pass@provider.example.test/api?token=secret",
                    "api_key": "abc123",
                },
                "request": {
                    "prompt": "use https://user:pass@cdn.example.test/ref.png?token=secret",
                    "content_summary": "data:image/png;base64,AAAASECRETDATA",
                    "aspect_ratio": "square",
                    "normalized_args": {"aspect_ratio": "square"},
                },
                "input_images": [],
                "result": {
                    "success": True,
                    "duration_ms": 12,
                    "outputs": [{"kind": "image", "ref": "/home/user/private/out.png"}],
                },
                "error": {
                    "error_type": "provider_exception",
                    "message": "Authorization: Bearer *** token=def456",
                },
            }
        ],
    )

    from tools.image_history_tool import _handle_image_history

    payload = json.loads(_handle_image_history({"latest": True, "limit": 1}))

    assert payload["success"] is True
    assert payload["records"][0]["image"] == "out.png"
    text = json.dumps(payload, sort_keys=True)
    assert "user:pass" not in text
    assert "@cdn.example.test" not in text
    assert "token=secret" not in text
    assert "AAAASECRETDATA" not in text
    assert "/home/" not in text
    assert "private" not in text
    assert "abc123" not in text
    assert "def456" not in text


def test_image_history_registered_under_image_gen_toolset():
    import tools.image_history_tool  # noqa: F401
    from tools.registry import registry

    entry = registry.get_entry("image_history")
    assert entry is not None
    assert entry.toolset == "image_gen"
