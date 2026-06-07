"""xAI image generation backend.

Exposes xAI's ``grok-imagine-image`` model as an
:class:`ImageGenProvider` implementation.

Features:
- Text-to-image generation
- Multiple aspect ratios (1:1, 16:9, 9:16, etc.)
- Multiple resolutions (1K, 2K)
- Base64 output saved to cache

Selection precedence (first hit wins):
1. ``XAI_IMAGE_MODEL`` env var
2. ``image_gen.xai.model`` in ``config.yaml``
3. :data:`DEFAULT_MODEL`
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    is_data_uri,
    is_http_url,
    local_image_to_data_uri,
    resolve_aspect_ratio,
    save_b64_image,
    save_url_image,
    success_response,
)
from tools.xai_http import hermes_xai_user_agent, resolve_xai_http_credentials

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------

_MODELS: Dict[str, Dict[str, Any]] = {
    "grok-imagine-image": {
        "display": "Grok Imagine Image",
        "speed": "~5-10s",
        "strengths": "Fast, high-quality",
    },
    "grok-imagine-image-quality": {
        "display": "Grok Imagine Image (Quality)",
        "speed": "~10-20s",
        "strengths": "Higher fidelity / detail; slower than the standard model.",
    },
}

DEFAULT_MODEL = "grok-imagine-image"

# xAI aspect ratios (more options than FAL/OpenAI)
_XAI_ASPECT_RATIOS = {
    "landscape": "16:9",
    "square": "1:1",
    "portrait": "9:16",
    "4:3": "4:3",
    "3:4": "3:4",
    "3:2": "3:2",
    "2:3": "2:3",
}

# xAI resolutions
_XAI_RESOLUTIONS = {"1k", "2k"}

DEFAULT_RESOLUTION = "1k"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _load_xai_config() -> Dict[str, Any]:
    """Read ``image_gen.xai`` from config.yaml."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        xai_section = section.get("xai") if isinstance(section, dict) else None
        return xai_section if isinstance(xai_section, dict) else {}
    except Exception as exc:
        logger.debug("Could not load image_gen.xai config: %s", exc)
        return {}


def _resolve_model() -> Tuple[str, Dict[str, Any]]:
    """Decide which model to use and return ``(model_id, meta)``."""
    env_override = os.environ.get("XAI_IMAGE_MODEL")
    if env_override and env_override in _MODELS:
        return env_override, _MODELS[env_override]

    cfg = _load_xai_config()
    candidate = cfg.get("model") if isinstance(cfg.get("model"), str) else None
    if candidate and candidate in _MODELS:
        return candidate, _MODELS[candidate]

    return DEFAULT_MODEL, _MODELS[DEFAULT_MODEL]


def _resolve_resolution() -> str:
    """Get configured resolution."""
    cfg = _load_xai_config()
    res = cfg.get("resolution") if isinstance(cfg.get("resolution"), str) else None
    if res and res in _XAI_RESOLUTIONS:
        return res
    return DEFAULT_RESOLUTION


# ---------------------------------------------------------------------------
# Shared HTTP helpers (used by both generate and edit)
# ---------------------------------------------------------------------------


def _xai_headers(api_key: str) -> Dict[str, str]:
    """Build the JSON request headers for an xAI image endpoint."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": hermes_xai_user_agent(),
    }


def _post_xai_image(
    endpoint: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    *,
    op_label: str,
    provider_name: str,
    model_id: str,
    prompt: str,
    aspect: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """POST to an xAI image endpoint and return ``(result_json, error_dict)``.

    Exactly one slot is non-None. Centralizes the HTTP error / timeout /
    connection / invalid-JSON handling shared by image generation and image
    editing. ``op_label`` ("image generation" / "image edit") is woven into
    error messages so each surface reads naturally.
    """
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
    except requests.HTTPError as exc:
        response = exc.response
        status = response.status_code if response is not None else 0
        try:
            err_msg = response.json().get("error", {}).get("message", response.text[:300])
        except Exception:
            err_msg = response.text[:300] if response is not None else str(exc)
        logger.error("xAI %s failed (%d): %s", op_label, status, err_msg)
        return None, error_response(
            error=f"xAI {op_label} failed ({status}): {err_msg}",
            error_type="api_error",
            provider=provider_name,
            model=model_id,
            prompt=prompt,
            aspect_ratio=aspect,
        )
    except requests.Timeout:
        return None, error_response(
            error=f"xAI {op_label} timed out (120s)",
            error_type="timeout",
            provider=provider_name,
            model=model_id,
            prompt=prompt,
            aspect_ratio=aspect,
        )
    except requests.ConnectionError as exc:
        return None, error_response(
            error=f"xAI connection error: {exc}",
            error_type="connection_error",
            provider=provider_name,
            model=model_id,
            prompt=prompt,
            aspect_ratio=aspect,
        )

    try:
        return response.json(), None
    except Exception as exc:
        return None, error_response(
            error=f"xAI returned invalid JSON: {exc}",
            error_type="invalid_response",
            provider=provider_name,
            model=model_id,
            prompt=prompt,
            aspect_ratio=aspect,
        )


def _extract_and_cache_image(
    result: Dict[str, Any],
    *,
    provider_name: str,
    model_id: str,
    prompt: str,
    aspect: str,
    prefix: str,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Pull ``data[0]`` from an xAI image response and cache it locally.

    Returns ``(image_ref, error_dict)`` with exactly one slot non-None.
    ``b64_json`` is decoded and saved; a ``url`` is downloaded (falling back
    to the bare URL when the download fails, mirroring the generation path —
    xAI's ``imgen.x.ai`` URLs expire fast, so a cache miss must not become a
    hard tool error); anything else is an ``empty_response``.
    """
    data = result.get("data", [])
    if not data:
        return None, error_response(
            error="xAI returned no image data",
            error_type="empty_response",
            provider=provider_name,
            model=model_id,
            prompt=prompt,
            aspect_ratio=aspect,
        )

    first = data[0] if isinstance(data[0], dict) else {}
    b64 = first.get("b64_json")
    url = first.get("url")

    if b64:
        try:
            saved_path = save_b64_image(b64, prefix=prefix)
        except Exception as exc:
            return None, error_response(
                error=f"Could not save image to cache: {exc}",
                error_type="io_error",
                provider=provider_name,
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        return str(saved_path), None

    if url:
        try:
            saved_path = save_url_image(url, prefix=prefix)
        except Exception as exc:
            logger.warning(
                "xAI image URL %s could not be cached (%s); falling back to bare URL.",
                url,
                exc,
            )
            return url, None
        return str(saved_path), None

    return None, error_response(
        error="xAI response contained neither b64_json nor URL",
        error_type="empty_response",
        provider=provider_name,
        model=model_id,
        prompt=prompt,
        aspect_ratio=aspect,
    )


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class XAIImageGenProvider(ImageGenProvider):
    """xAI ``grok-imagine-image`` backend."""

    @property
    def name(self) -> str:
        return "xai"

    @property
    def display_name(self) -> str:
        return "xAI (Grok)"

    def is_available(self) -> bool:
        creds = resolve_xai_http_credentials()
        return bool(creds.get("api_key"))

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": model_id,
                "display": meta.get("display", model_id),
                "speed": meta.get("speed", ""),
                "strengths": meta.get("strengths", ""),
            }
            for model_id, meta in _MODELS.items()
        ]

    def get_setup_schema(self) -> Dict[str, Any]:
        # Auth resolution is delegated to the shared ``xai_grok`` post_setup
        # hook (``hermes_cli/tools_config.py``); identical to the TTS / video
        # gen entries so users see the same OAuth-or-API-key choice for every
        # xAI service.
        return {
            "name": "xAI Grok Imagine (image)",
            "badge": "paid",
            "tag": "grok-imagine-image — text-to-image; uses xAI Grok OAuth or XAI_API_KEY",
            "env_vars": [],
            "post_setup": "xai_grok",
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate an image using xAI's grok-imagine-image."""
        creds = resolve_xai_http_credentials()
        api_key = str(creds.get("api_key") or "").strip()
        provider_name = str(creds.get("provider") or "xai").strip() or "xai"
        if not api_key:
            return error_response(
                error="No xAI credentials found. Configure xAI OAuth in `hermes model` or set XAI_API_KEY.",
                error_type="missing_api_key",
                provider=provider_name,
                aspect_ratio=aspect_ratio,
            )

        model_id, meta = _resolve_model()
        aspect = resolve_aspect_ratio(aspect_ratio)
        xai_ar = _XAI_ASPECT_RATIOS.get(aspect, "1:1")
        resolution = _resolve_resolution()
        xai_res = resolution if resolution in _XAI_RESOLUTIONS else DEFAULT_RESOLUTION

        payload: Dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            "aspect_ratio": xai_ar,
            "resolution": xai_res,
            # Prefer inline bytes over xAI's temporary imgen.x.ai URL: the URL
            # path can be blocked by CDN/IP policy before Hermes can cache it.
            "response_format": "b64_json",
        }

        headers = _xai_headers(api_key)
        base_url = str(creds.get("base_url") or "https://api.x.ai/v1").strip().rstrip("/")

        result, error = _post_xai_image(
            f"{base_url}/images/generations",
            payload,
            headers,
            op_label="image generation",
            provider_name=provider_name,
            model_id=model_id,
            prompt=prompt,
            aspect=aspect,
        )
        if error is not None:
            return error

        # xAI's grok-imagine-image returns ephemeral ``imgen.x.ai/xai-tmp-*``
        # URLs that 404 within minutes (#26942); ``_extract_and_cache_image``
        # materialises the bytes locally so the gateway has a stable path.
        image_ref, error = _extract_and_cache_image(
            result,
            provider_name=provider_name,
            model_id=model_id,
            prompt=prompt,
            aspect=aspect,
            prefix=f"xai_{model_id}",
        )
        if error is not None:
            return error

        return success_response(
            image=image_ref,
            model=model_id,
            prompt=prompt,
            aspect_ratio=aspect,
            provider="xai",
            extra={"resolution": xai_res},
        )

    # ------------------------------------------------------------------
    # Image edit / image-to-image
    # ------------------------------------------------------------------

    def supports_edit(self) -> bool:
        return True

    def edit(
        self,
        prompt: str,
        image: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Edit an image with xAI's ``/v1/images/edits`` endpoint.

        ``image`` may be a local filesystem path (inlined as a base64 ``data:``
        URI after validation), an ``http(s)`` URL, or a ``data:`` URI. Per the
        official xAI docs the source image is always wrapped in an object —
        ``"image": {"url": "<url-or-data-uri>", "type": "image_url"}`` — where
        ``url`` accepts either a public URL or a base64-encoded data URI
        (https://docs.x.ai/developers/model-capabilities/images/editing).
        Reuses the same credential resolution, user-agent, error handling,
        and output caching as :meth:`generate`.
        """
        creds = resolve_xai_http_credentials()
        api_key = str(creds.get("api_key") or "").strip()
        provider_name = str(creds.get("provider") or "xai").strip() or "xai"
        aspect = resolve_aspect_ratio(aspect_ratio)

        if not api_key:
            return error_response(
                error="No xAI credentials found. Configure xAI OAuth in `hermes model` or set XAI_API_KEY.",
                error_type="missing_api_key",
                provider=provider_name,
                aspect_ratio=aspect,
            )

        if not prompt or not str(prompt).strip():
            return error_response(
                error="prompt is required and must be a non-empty string",
                error_type="invalid_input",
                provider=provider_name,
                aspect_ratio=aspect,
            )

        image_ref = str(image or "").strip()
        if not image_ref:
            return error_response(
                error="image is required (local path, http(s) URL, or data URI)",
                error_type="invalid_input",
                provider=provider_name,
                aspect_ratio=aspect,
            )

        model_id, _meta = _resolve_model()
        xai_ar = _XAI_ASPECT_RATIOS.get(aspect, "1:1")

        payload: Dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            # Output aspect mirrors the generation surface; "if xAI needs it"
            # per the schema contract. Cheap to drop should the edits endpoint
            # reject it.
            "aspect_ratio": xai_ar,
            # Prefer inline bytes over xAI's ephemeral imgen.x.ai URLs.
            "response_format": "b64_json",
        }

        # Resolve the input to a single ``url`` value: http(s) URLs and data
        # URIs are passed by reference, while local files are validated and
        # inlined as a base64 data URI so we never ship arbitrary file content.
        # All three then ride xAI's required object shape
        # ``{"url": ..., "type": "image_url"}`` (see method docstring).
        try:
            if is_http_url(image_ref) or is_data_uri(image_ref):
                source_url = image_ref
            else:
                source_url = local_image_to_data_uri(image_ref)
        except ValueError as exc:
            return error_response(
                error=str(exc),
                error_type="invalid_input",
                provider=provider_name,
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        payload["image"] = {"url": source_url, "type": "image_url"}

        headers = _xai_headers(api_key)
        base_url = str(creds.get("base_url") or "https://api.x.ai/v1").strip().rstrip("/")

        result, error = _post_xai_image(
            f"{base_url}/images/edits",
            payload,
            headers,
            op_label="image edit",
            provider_name=provider_name,
            model_id=model_id,
            prompt=prompt,
            aspect=aspect,
        )
        if error is not None:
            return error

        image_out, error = _extract_and_cache_image(
            result,
            provider_name=provider_name,
            model_id=model_id,
            prompt=prompt,
            aspect=aspect,
            prefix=f"xai_edit_{model_id}",
        )
        if error is not None:
            return error

        return success_response(
            image=image_out,
            model=model_id,
            prompt=prompt,
            aspect_ratio=aspect,
            provider="xai",
        )


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def register(ctx: Any) -> None:
    """Register this provider with the image gen registry."""
    ctx.register_image_gen_provider(XAIImageGenProvider())
