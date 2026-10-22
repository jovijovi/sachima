from __future__ import annotations

import json

from agent.image_gen_provider import ImageGenProvider


class _EditProvider(ImageGenProvider):
    def __init__(self):
        self.received = None

    @property
    def name(self):
        return "editcap"

    def capabilities(self):
        return {"modalities": ["text", "image"], "max_reference_images": 2}

    def generate(
        self,
        prompt,
        aspect_ratio="landscape",
        *,
        image_url=None,
        reference_image_urls=None,
        **kwargs,
    ):
        self.received = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "image_url": image_url,
            "reference_image_urls": reference_image_urls,
            "kwargs": kwargs,
        }
        return {
            "success": True,
            "image": "/tmp/edited.png",
            "provider": self.name,
            "model": "edit-v1",
            "modality": "image",
        }


def _configure(monkeypatch, provider):
    from agent import image_gen_registry
    from hermes_cli import plugins
    from tools import image_generation_tool

    image_gen_registry._reset_for_tests()
    image_gen_registry.register_provider(provider)
    monkeypatch.setattr(plugins, "_ensure_plugins_discovered", lambda *a, **k: None)
    monkeypatch.setattr(image_generation_tool, "_read_configured_image_provider", lambda: provider.name)
    monkeypatch.setattr(image_generation_tool, "_read_configured_image_model", lambda: "edit-v1")
    monkeypatch.setattr(image_generation_tool, "check_image_generation_requirements", lambda: True)


def test_schema_and_registration_preserve_image_edit_surface():
    from tools.image_edit_tool import IMAGE_EDIT_SCHEMA
    from tools.registry import registry

    assert IMAGE_EDIT_SCHEMA["parameters"]["required"] == ["prompt", "image"]
    entry = registry.get_entry("image_edit")
    assert entry is not None
    assert entry.toolset == "image_gen"


def test_check_is_true_only_for_available_edit_capability(monkeypatch):
    provider = _EditProvider()
    _configure(monkeypatch, provider)
    from tools.image_edit_tool import check_image_edit_requirements

    assert check_image_edit_requirements() is True


def test_handler_delegates_to_unified_provider_and_keeps_summary_local(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_PROFILE", "images")
    provider = _EditProvider()
    _configure(monkeypatch, provider)
    from tools.image_edit_tool import _handle_image_edit

    payload = json.loads(
        _handle_image_edit(
            {
                "prompt": "make it blue",
                "image": "https://cdn.example.test/in.png?token=secret",
                "reference_image_urls": ["https://cdn.example.test/ref.png?sig=secret"],
                "aspect_ratio": "square",
                "content_summary": "blue product photo",
            }
        )
    )

    assert payload["success"] is True
    assert provider.received == {
        "prompt": "make it blue",
        "aspect_ratio": "square",
        "image_url": "https://cdn.example.test/in.png?token=secret",
        "reference_image_urls": ["https://cdn.example.test/ref.png?sig=secret"],
        "kwargs": {"model": "edit-v1"},
    }
    manifest = tmp_path / "workspace" / "image-generation" / "manifest.jsonl"
    record = json.loads(manifest.read_text(encoding="utf-8"))
    assert record["tool"] == "image_edit"
    assert record["operation"] == "edit"
    assert record["request"]["content_summary"] == "blue product photo"
    assert "token=secret" not in manifest.read_text(encoding="utf-8")
    assert "sig=secret" not in manifest.read_text(encoding="utf-8")


def test_handler_rejects_missing_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    provider = _EditProvider()
    _configure(monkeypatch, provider)
    from tools.image_edit_tool import _handle_image_edit

    assert "error" in json.loads(_handle_image_edit({"image": "https://x/in.png"}))
    assert "error" in json.loads(_handle_image_edit({"prompt": "edit"}))


def test_handler_does_not_call_text_only_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    provider = _EditProvider()
    _configure(monkeypatch, provider)
    from tools import image_edit_tool

    monkeypatch.setattr(
        image_edit_tool.generation,
        "_active_image_capabilities",
        lambda: {"modalities": ["text"], "provider": "text-only"},
    )
    payload = json.loads(
        image_edit_tool._handle_image_edit(
            {"prompt": "edit", "image": "https://x/in.png"}
        )
    )
    assert payload["success"] is False
    assert payload["error_type"] == "unsupported_capability"
    assert provider.received is None


def test_dynamic_schema_uses_active_reference_cap(monkeypatch):
    provider = _EditProvider()
    _configure(monkeypatch, provider)
    from tools.image_edit_tool import _build_dynamic_image_edit_schema

    props = _build_dynamic_image_edit_schema()["parameters"]["properties"]
    assert props["reference_image_urls"]["maxItems"] == 2
