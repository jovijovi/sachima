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


def _record(record_id, *, ts, tool, success, prompt, content_summary=None, image=None, sequence=None):
    record = {
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
            "outputs": [{"output_index": 1, "kind": "image", "ref": image}] if success and image else [],
        },
        "error": None if success else {"error_type": "ValueError", "message": "failed"},
    }
    if sequence is not None:
        record["sequence"] = sequence
    return record


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


def test_image_history_returns_sequence_and_output_indices(monkeypatch, tmp_path):
    _write_manifest(
        monkeypatch,
        tmp_path,
        [
            _record(
                "multi-output",
                ts="2026-06-20T04:00:00Z",
                tool="image_generate",
                success=True,
                prompt="two cats",
                sequence=7,
            )
            | {
                "result": {
                    "success": True,
                    "duration_ms": 12,
                    "outputs": [
                        {"output_index": 1, "kind": "image", "ref": "cat-a.png"},
                        {"output_index": 2, "kind": "image", "ref": "cat-b.png"},
                    ],
                }
            }
        ],
    )

    from tools.image_history_tool import _handle_image_history

    payload = json.loads(_handle_image_history({"latest": True, "limit": 1}))

    assert payload["success"] is True
    record = payload["records"][0]
    assert record["sequence"] == 7
    assert record["image"] == "cat-a.png"
    assert record["outputs"] == [
        {"output_index": 1, "kind": "image", "ref": "cat-a.png"},
        {"output_index": 2, "kind": "image", "ref": "cat-b.png"},
    ]


def test_image_history_latest_breaks_same_timestamp_ties_by_sequence(monkeypatch, tmp_path):
    same_ts = "2026-06-20T04:00:00Z"
    _write_manifest(
        monkeypatch,
        tmp_path,
        [
            _record("old", ts=same_ts, tool="image_generate", success=True, prompt="old", sequence=1),
            _record("new", ts=same_ts, tool="image_generate", success=True, prompt="new", sequence=2),
        ],
    )

    from tools.image_history_tool import _handle_image_history

    payload = json.loads(_handle_image_history({"latest": True, "limit": 1}))

    assert payload["success"] is True
    assert [record["record_id"] for record in payload["records"]] == ["new"]


def test_image_history_latest_uses_file_order_for_legacy_same_timestamp_records(monkeypatch, tmp_path):
    same_ts = "2026-06-20T04:00:00Z"
    _write_manifest(
        monkeypatch,
        tmp_path,
        [
            _record("legacy-old", ts=same_ts, tool="image_generate", success=True, prompt="old"),
            _record("legacy-new", ts=same_ts, tool="image_generate", success=True, prompt="new"),
        ],
    )

    from tools.image_history_tool import _handle_image_history

    payload = json.loads(_handle_image_history({"latest": True, "limit": 2}))

    assert payload["success"] is True
    assert [record["record_id"] for record in payload["records"]] == ["legacy-new", "legacy-old"]


def test_image_history_latest_uses_file_order_as_duplicate_sequence_tiebreaker(monkeypatch, tmp_path):
    same_ts = "2026-06-20T04:00:00Z"
    _write_manifest(
        monkeypatch,
        tmp_path,
        [
            _record("duplicate-old", ts=same_ts, tool="image_generate", success=True, prompt="old", sequence=5),
            _record("duplicate-new", ts=same_ts, tool="image_generate", success=True, prompt="new", sequence=5),
        ],
    )

    from tools.image_history_tool import _handle_image_history

    payload = json.loads(_handle_image_history({"latest": True, "limit": 2}))

    assert payload["success"] is True
    assert [record["record_id"] for record in payload["records"]] == [
        "duplicate-new",
        "duplicate-old",
    ]


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
                    "prompt": "use https://user:pass@cdn.example.test/ref.png?token=secret and /home/alice/private/ref.png",
                    "content_summary": "data:image/png;base64,AAAASECRETDATA and C:\\Users\\alice\\Pictures\\ref.png",
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
                    "message": "Authorization: Bearer *** token=def456 password=hunter2 path=/tmp/private/fail.png",
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
    assert "/tmp/" not in text
    assert "C:\\Users" not in text
    assert "alice" not in text
    assert "private" not in text
    assert "abc123" not in text
    assert "def456" not in text
    assert "hunter2" not in text


def test_image_history_redacts_quoted_json_secret_fields_on_write_and_read(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_PROFILE", "unit-profile")

    from tools.image_manifest import append_image_manifest_record, query_image_history

    manifest_path = tmp_path / "manifest.jsonl"
    append_image_manifest_record(
        tool="image_generate",
        operation="generate",
        backend="fal",
        args={"prompt": "draw", "aspect_ratio": "square"},
        input_images=[],
        duration_ms=1,
        result_payload={
            "success": False,
            "error_type": "provider_exception",
            "error": '{"password":"hunter2","token":"abc123","api_key":"key123","secret":"sauce"}',
        },
        manifest_path=manifest_path,
    )

    raw_text = manifest_path.read_text(encoding="utf-8")
    history_text = json.dumps(query_image_history(manifest_path=manifest_path), sort_keys=True)
    combined = raw_text + history_text
    assert "hunter2" not in combined
    assert "abc123" not in combined
    assert "key123" not in combined
    assert "sauce" not in combined
    assert "[REDACTED]" in combined


def test_image_history_registered_under_image_gen_toolset():
    import tools.image_history_tool  # noqa: F401
    from tools.registry import registry

    entry = registry.get_entry("image_history")
    assert entry is not None
    assert entry.toolset == "image_gen"
