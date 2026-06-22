from __future__ import annotations

import json


def _json_text(value) -> str:
    return json.dumps(value, sort_keys=True)


def _all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def test_default_manifest_path_uses_profile_local_hermes_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))

    from tools.image_manifest import default_manifest_path

    assert (
        default_manifest_path()
        == tmp_path / "hermes-home" / "workspace" / "image-generation" / "manifest.jsonl"
    )


def test_build_record_shape_and_redaction(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "unit-profile")

    from tools.image_manifest import build_image_manifest_record

    record = build_image_manifest_record(
        tool="image_generate",
        operation="generate",
        backend="fal",
        args={
            "prompt": "draw a small red cabin",
            "aspect_ratio": "square",
            "content_summary": "red cabin concept art",
            "session_id": "session-should-not-be-recorded",
            "tool_call_id": "call-should-not-be-recorded",
        },
        input_images=[],
        duration_ms=42,
        result_payload={
            "success": True,
            "image": "https://cdn.example.test/out.png?X-Amz-Signature=secret&token=secret",
            "provider": "fal",
            "model": "fal-ai/test-model",
            "provider_raw_response": {"secret": "raw"},
            "sha256": "abc123",
            "session_id": "session-should-not-be-recorded",
        },
    )

    assert set(record) == {
        "schema_version",
        "record_id",
        "ts",
        "profile",
        "tool",
        "operation",
        "backend",
        "request",
        "input_images",
        "result",
        "error",
    }
    assert record["schema_version"] == 1
    assert record["profile"] == "unit-profile"
    assert record["tool"] == "image_generate"
    assert record["operation"] == "generate"
    assert record["backend"] == {
        "provider": "fal",
        "model": "fal-ai/test-model",
        "endpoint_kind": "generate",
    }
    assert record["input_images"] == []
    assert record["request"]["prompt"] == "draw a small red cabin"
    assert record["request"]["content_summary"] == "red cabin concept art"
    assert record["request"]["content_summary_source"] == "agent_supplied"
    assert record["request"]["content_summary_verified"] is False
    assert record["request"]["prompt_chars"] == len("draw a small red cabin")
    assert record["request"]["aspect_ratio"] == "square"
    assert record["result"] == {
        "success": True,
        "duration_ms": 42,
        "outputs": [
            {"output_index": 1, "kind": "image", "ref": "https://cdn.example.test/out.png"}
        ],
    }
    assert record["error"] is None

    text = _json_text(record)
    keys = set(_all_keys(record))
    assert "session_id" not in keys
    assert "tool_call_id" not in keys
    assert "sha256" not in keys
    assert "hash" not in keys
    assert "provider_raw_response" not in keys
    assert "X-Amz-Signature" not in text
    assert "token=secret" not in text


def test_input_image_metadata_redacts_data_uri_and_signed_url_query(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "unit-profile")

    from tools.image_manifest import build_image_manifest_record

    data_uri_record = build_image_manifest_record(
        tool="image_edit",
        operation="edit",
        backend="xai",
        args={
            "prompt": "make it blue",
            "image": "data:image/png;base64,AAAASECRETDATA",
            "aspect_ratio": "landscape",
        },
        duration_ms=7,
        result_payload={"success": False, "error": "provider rejected input", "error_type": "ValueError"},
    )

    assert data_uri_record["input_images"] == [
        {
            "kind": "data_uri",
            "mime_type": "image/png",
            "length_chars": len("data:image/png;base64,AAAASECRETDATA"),
        }
    ]
    assert "AAAASECRETDATA" not in _json_text(data_uri_record)

    signed_url_record = build_image_manifest_record(
        tool="image_edit",
        operation="edit",
        backend="xai",
        args={
            "prompt": "make it green",
            "image": "https://cdn.example.test/input.png?X-Amz-Signature=secret&token=secret",
            "aspect_ratio": "portrait",
        },
        duration_ms=9,
        result_payload={"success": True, "image": "/tmp/out.png"},
    )

    assert signed_url_record["input_images"] == [
        {
            "kind": "url",
            "scheme": "https",
            "host": "cdn.example.test",
            "path": "/input.png",
            "url": "https://cdn.example.test/input.png",
            "query_redacted": True,
        }
    ]
    text = _json_text(signed_url_record)
    assert "X-Amz-Signature" not in text
    assert "token=secret" not in text

    upper_data_record = build_image_manifest_record(
        tool="image_edit",
        operation="edit",
        backend="xai",
        args={
            "prompt": "make it red",
            "image": "DATA:image/png;base64,UPPERCASESECRETDATA",
            "aspect_ratio": "square",
        },
        duration_ms=3,
        result_payload={"success": False, "error": "provider rejected input"},
    )
    assert upper_data_record["input_images"] == [
        {
            "kind": "data_uri",
            "mime_type": "image/png",
            "length_chars": len("DATA:image/png;base64,UPPERCASESECRETDATA"),
        }
    ]
    assert "UPPERCASESECRETDATA" not in _json_text(upper_data_record)

    windows_path_record = build_image_manifest_record(
        tool="image_edit",
        operation="edit",
        backend="xai",
        args={
            "prompt": "make it red",
            "image": "C:\\Users\\alice\\Pictures\\secret.png",
            "aspect_ratio": "square",
        },
        duration_ms=3,
        result_payload={"success": False, "error": "provider rejected input"},
    )
    assert windows_path_record["input_images"] == [
        {"kind": "file", "name": "secret.png", "suffix": ".png", "is_absolute": True}
    ]
    text = _json_text(windows_path_record)
    assert "C:\\Users" not in text
    assert "alice" not in text


def test_url_userinfo_is_redacted_from_request_input_and_output(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "unit-profile")

    from tools.image_manifest import build_image_manifest_record, sanitize_input_image_metadata

    record = build_image_manifest_record(
        tool="image_edit",
        operation="edit",
        backend="xai",
        args={
            "prompt": "use https://user:pass@cdn.example.test/ref.png?token=secret",
            "content_summary": "ref https://user:pass@cdn.example.test/ref.png#frag",
            "image": "https://user:pass@cdn.example.test/input.png?X-Amz-Signature=secret",
            "aspect_ratio": "square",
        },
        duration_ms=11,
        result_payload={
            "success": True,
            "image": "https://user:pass@cdn.example.test/out.png?token=secret#frag",
        },
    )

    assert record["request"]["prompt"] == "use https://cdn.example.test/ref.png"
    assert record["request"]["content_summary"] == "ref https://cdn.example.test/ref.png"
    assert record["input_images"] == [
        {
            "kind": "url",
            "scheme": "https",
            "host": "cdn.example.test",
            "path": "/input.png",
            "url": "https://cdn.example.test/input.png",
            "query_redacted": True,
        }
    ]
    assert record["result"]["outputs"] == [
        {"output_index": 1, "kind": "image", "ref": "https://cdn.example.test/out.png"}
    ]
    text = _json_text(record)
    assert "user:pass" not in text
    assert "@cdn.example.test" not in text
    assert "token=secret" not in text
    assert "X-Amz-Signature" not in text

    assert sanitize_input_image_metadata(
        "https://user:pass@cdn.example.test/input-no-query.png"
    ) == {
        "kind": "url",
        "scheme": "https",
        "host": "cdn.example.test",
        "path": "/input-no-query.png",
        "url": "https://cdn.example.test/input-no-query.png",
        "query_redacted": True,
    }


def test_absolute_output_paths_are_reduced_to_safe_file_names(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "unit-profile")

    from tools.image_manifest import build_image_manifest_record

    record = build_image_manifest_record(
        tool="image_generate",
        operation="generate",
        backend="fal",
        args={"prompt": "draw", "aspect_ratio": "square"},
        input_images=[],
        duration_ms=5,
        result_payload={
            "success": True,
            "image": "/home/user/private/out.png",
            "images": [
                {"url": "/tmp/cache/edited.png"},
                "C:\\Users\\alice\\Pictures\\portrait.png",
            ],
        },
    )

    assert record["result"]["outputs"] == [
        {"output_index": 1, "kind": "image", "ref": "out.png"},
        {"output_index": 2, "kind": "image", "ref": "edited.png"},
        {"output_index": 3, "kind": "image", "ref": "portrait.png"},
    ]
    text = _json_text(record)
    assert "/home/" not in text
    assert "/tmp/" not in text
    assert "C:\\Users" not in text
    assert "private" not in text


def test_explicit_input_images_are_sanitized_before_recording(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "unit-profile")

    from tools.image_manifest import build_image_manifest_record

    record = build_image_manifest_record(
        tool="image_edit",
        operation="edit",
        backend="xai",
        args={"prompt": "edit", "aspect_ratio": "square"},
        input_images=[
            {
                "kind": "url",
                "url": "https://cdn.example.test/input.png?token=secret",
                "raw": "data:image/png;base64,AAAASECRETDATA",
                "sha256": "abc123",
            }
        ],
        duration_ms=4,
        result_payload={"success": True, "image": "/tmp/out.png"},
    )

    assert record["input_images"] == [
        {"kind": "url", "url": "https://cdn.example.test/input.png"}
    ]
    text = _json_text(record)
    assert "token=secret" not in text
    assert "AAAASECRETDATA" not in text
    assert "sha256" not in text
    assert "abc123" not in text


def test_request_text_redacts_embedded_data_uri_and_signed_url(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "unit-profile")

    from tools.image_manifest import build_image_manifest_record

    record = build_image_manifest_record(
        tool="image_generate",
        operation="generate",
        backend="fal",
        args={
            "prompt": "use data:image/png;base64,AAAASECRETDATA and https://cdn.example.test/ref.png?token=secret and /home/alice/private/ref.png",
            "aspect_ratio": "square",
            "content_summary": "ref https://cdn.example.test/ref.png?X-Amz-Signature=secret and C:\\Users\\alice\\Pictures\\ref.png",
        },
        input_images=[],
        duration_ms=2,
        result_payload={"success": True, "image": "/tmp/out.png"},
    )

    text = _json_text(record)
    assert "AAAASECRETDATA" not in text
    assert "token=secret" not in text
    assert "X-Amz-Signature" not in text
    assert "/home/" not in text
    assert "C:\\Users" not in text
    assert "alice" not in text
    assert "data:image/png;redacted" in record["request"]["prompt"]
    assert "https://cdn.example.test/ref.png" in record["request"]["prompt"]
    assert "ref.png" in record["request"]["prompt"]
    assert record["request"]["content_summary"] == "ref https://cdn.example.test/ref.png and ref.png"


def test_error_message_redacts_auth_and_secret_material(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "unit-profile")

    from tools.image_manifest import build_image_manifest_record

    record = build_image_manifest_record(
        tool="image_generate",
        operation="generate",
        backend="fal",
        args={"prompt": "draw", "aspect_ratio": "square"},
        input_images=[],
        duration_ms=2,
        result_payload={
            "success": False,
            "error_type": "provider_exception",
            "error": "Authorization: Bearer sk-secret-token api_key=abc123 token=def456 password=hunter2",
        },
    )

    message = record["error"]["message"]
    assert "sk-secret-token" not in message
    assert "abc123" not in message
    assert "def456" not in message
    assert "hunter2" not in message
    assert "Authorization: Bearer [REDACTED]" in message
    assert "api_key=[REDACTED]" in message
    assert "token=[REDACTED]" in message
    assert "password=[REDACTED]" in message


def test_append_manifest_record_is_best_effort(monkeypatch, tmp_path):
    from tools import image_manifest

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(image_manifest, "_write_jsonl_record", boom)

    image_manifest.append_image_manifest_record(
        tool="image_generate",
        operation="generate",
        backend="fal",
        args={"prompt": "draw a cat", "aspect_ratio": "square"},
        input_images=[],
        duration_ms=1,
        result_payload={"success": True, "image": "/tmp/cat.png"},
        manifest_path=tmp_path / "manifest.jsonl",
    )


def test_append_manifest_record_writes_one_json_line(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_PROFILE", "unit-profile")
    from tools.image_manifest import append_image_manifest_record

    manifest_path = tmp_path / "manifest.jsonl"

    append_image_manifest_record(
        tool="image_generate",
        operation="generate",
        backend="fal",
        args={"prompt": "draw a cat", "aspect_ratio": "square"},
        input_images=[],
        duration_ms=3,
        result_payload={"success": True, "image": "/tmp/cat.png"},
        manifest_path=manifest_path,
    )

    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["tool"] == "image_generate"
    assert record["profile"] == "unit-profile"


def test_append_manifest_record_assigns_sequence_and_output_indices(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_PROFILE", "unit-profile")
    from tools.image_manifest import append_image_manifest_record

    manifest_path = tmp_path / "manifest.jsonl"

    append_image_manifest_record(
        tool="image_generate",
        operation="generate",
        backend="fal",
        args={"prompt": "draw first", "aspect_ratio": "square"},
        input_images=[],
        duration_ms=3,
        result_payload={"success": True, "image": "/tmp/first.png"},
        manifest_path=manifest_path,
    )
    append_image_manifest_record(
        tool="image_generate",
        operation="generate",
        backend="fal",
        args={"prompt": "draw second", "aspect_ratio": "square"},
        input_images=[],
        duration_ms=4,
        result_payload={
            "success": True,
            "images": ["/tmp/second-a.png", "/tmp/second-b.png"],
        },
        manifest_path=manifest_path,
    )

    records = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    assert [record["sequence"] for record in records] == [1, 2]
    assert records[0]["result"]["outputs"] == [
        {"output_index": 1, "kind": "image", "ref": "first.png"}
    ]
    assert records[1]["result"]["outputs"] == [
        {"output_index": 1, "kind": "image", "ref": "second-a.png"},
        {"output_index": 2, "kind": "image", "ref": "second-b.png"},
    ]
