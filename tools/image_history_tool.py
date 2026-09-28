"""Narrow query tool for profile-local image generation history."""

from __future__ import annotations

import json
from typing import Any, Dict

import tools.image_generation_tool  # noqa: F401 - anchor image_gen toolset check
from tools.image_manifest import query_image_history
from tools.registry import registry


def check_image_history_requirements() -> bool:
    return True


def _coerce_success(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _handle_image_history(args: Dict[str, Any], **kw: Any) -> str:
    try:
        records = query_image_history(
            latest=bool(args.get("latest", True)),
            limit=args.get("limit", 10),
            tool=args.get("tool") or None,
            success=_coerce_success(args.get("success")),
            content_search=args.get("content_search") or None,
        )
        return json.dumps(
            {
                "success": True,
                "count": len(records),
                "records": records,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {
                "success": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
            ensure_ascii=False,
        )


IMAGE_HISTORY_SCHEMA = {
    "name": "image_history",
    "description": (
        "Query recent profile-local image generation/edit history from the "
        "image manifest. Returns compact sanitized records only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "latest": {
                "type": "boolean",
                "description": "When true, return newest records first.",
                "default": True,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum records to return (1-50).",
                "default": 10,
            },
            "tool": {
                "type": "string",
                "enum": ["image_generate", "image_edit"],
                "description": "Optional tool filter.",
            },
            "success": {
                "type": "boolean",
                "description": "Optional success/failure filter.",
            },
            "content_search": {
                "type": "string",
                "description": "Case-insensitive search over prompt and content summary.",
            },
        },
    },
}


registry.register(
    name="image_history",
    toolset="image_gen",
    schema=IMAGE_HISTORY_SCHEMA,
    handler=_handle_image_history,
    check_fn=check_image_history_requirements,
    requires_env=[],
    is_async=False,
    emoji="",
)
