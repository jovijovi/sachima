#!/usr/bin/env python3
"""Compatibility surface for provider-agnostic image editing.

The current image provider contract routes both generation and editing through
``ImageGenProvider.generate``.  This module preserves the established
``image_edit`` tool name without reintroducing a second provider interface: it
validates the edit-specific contract, then delegates to the same execution
path as ``image_generate``.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict

from agent.image_gen_provider import DEFAULT_ASPECT_RATIO, VALID_ASPECT_RATIOS
from tools import image_generation_tool as generation
from tools.image_manifest import append_image_manifest_record
from tools.registry import registry, tool_error


def check_image_edit_requirements() -> bool:
    """Expose the compatibility tool only for an available edit backend."""
    try:
        return bool(
            generation.check_image_generation_requirements()
            and "image" in generation._active_image_capabilities().get("modalities", [])
        )
    except Exception:
        return False


def _unsupported_result(info: Dict[str, Any]) -> str:
    provider = info.get("provider") or "active image provider"
    return json.dumps(
        {
            "success": False,
            "image": None,
            "error": (
                f"{provider} does not support image editing. Choose an "
                "edit-capable image model in `hermes tools` → Image Generation."
            ),
            "error_type": "unsupported_capability",
            "provider": provider,
        },
        ensure_ascii=False,
    )


def _handle_image_edit(args: Dict[str, Any], **kw: Any) -> str:
    started_at = time.perf_counter()
    prompt = args.get("prompt", "")
    image = args.get("image", "")
    info = generation._active_image_capabilities()

    if not isinstance(prompt, str) or not prompt.strip():
        result = tool_error("prompt is required for image edit")
    elif not isinstance(image, str) or not image.strip():
        result = tool_error("image is required for image edit")
    elif "image" not in info.get("modalities", []):
        result = _unsupported_result(info)
    else:
        generate_args: Dict[str, Any] = {
            "prompt": prompt,
            "image_url": image,
            "aspect_ratio": args.get("aspect_ratio", DEFAULT_ASPECT_RATIO),
        }
        references = args.get("reference_image_urls")
        if isinstance(references, (list, tuple)):
            generate_args["reference_image_urls"] = list(references)
        if isinstance(args.get("upscale"), bool):
            generate_args["upscale"] = args["upscale"]
        result = generation._execute_image_generate(generate_args, **kw)

    manifest_args = dict(args)
    if info.get("model") and not manifest_args.get("model"):
        manifest_args["model"] = info["model"]
    input_images = [image] if isinstance(image, str) and image.strip() else []
    references = args.get("reference_image_urls")
    if isinstance(references, (list, tuple)):
        input_images.extend(
            ref.strip()
            for ref in references
            if isinstance(ref, str) and ref.strip()
        )
    append_image_manifest_record(
        tool="image_edit",
        operation="edit",
        backend=info.get("provider"),
        args=manifest_args,
        input_images=input_images,
        response_text=result,
        duration_ms=(time.perf_counter() - started_at) * 1000,
    )
    return result


IMAGE_EDIT_SCHEMA = {
    "name": "image_edit",
    "description": (
        "Edit or transform an existing image with the configured image "
        "provider. Uses the same provider/model selected for image_generate "
        "and is shown only when that model advertises image input support."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Instruction describing the desired edit.",
            },
            "image": {
                "type": "string",
                "description": "Source image URL, data URI, or conversation-local path.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": list(VALID_ASPECT_RATIOS),
                "default": DEFAULT_ASPECT_RATIO,
            },
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional additional reference images supported by the active model.",
            },
            "content_summary": {
                "type": "string",
                "description": "Optional profile-local history summary; never sent to the provider.",
            },
        },
        "required": ["prompt", "image"],
    },
}


def _build_dynamic_image_edit_schema() -> Dict[str, Any]:
    schema = {
        "description": IMAGE_EDIT_SCHEMA["description"],
        "parameters": {
            **IMAGE_EDIT_SCHEMA["parameters"],
            "properties": dict(IMAGE_EDIT_SCHEMA["parameters"]["properties"]),
        },
    }
    max_refs = int(generation._active_image_capabilities().get("max_reference_images") or 0)
    if max_refs > 1:
        schema["parameters"]["properties"]["reference_image_urls"] = {
            **schema["parameters"]["properties"]["reference_image_urls"],
            "maxItems": max_refs,
        }
    else:
        schema["parameters"]["properties"].pop("reference_image_urls", None)
    return schema


registry.register(
    name="image_edit",
    toolset="image_gen",
    schema=IMAGE_EDIT_SCHEMA,
    handler=_handle_image_edit,
    check_fn=check_image_edit_requirements,
    requires_env=[],
    is_async=False,
    emoji="🖌️",
    dynamic_schema_overrides=_build_dynamic_image_edit_schema,
)
