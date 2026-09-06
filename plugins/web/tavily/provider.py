"""Tavily search and extraction through Hermes' web-provider seam.

Tavily documents both endpoints as JSON POST requests authenticated with an
``Authorization: Bearer`` header. The provider deliberately remains a thin
HTTP adapter: it adds no new model tool and is only selected by the existing
``web.search_backend`` / ``web.extract_backend`` / ``web.backend`` config.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

from agent.web_search_provider import WebSearchProvider, get_provider_env

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.tavily.com"


def _tavily_request(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call one Tavily JSON endpoint without mutating or logging secrets."""
    api_key = get_provider_env("TAVILY_API_KEY")
    if not api_key:
        raise ValueError(
            "TAVILY_API_KEY is not configured. Get an API key at "
            "https://app.tavily.com/home or run `hermes tools`."
        )

    # Preserve the downstream override for existing installations while the
    # normal product path remains explicit backend selection in config.yaml.
    base_url = get_provider_env("TAVILY_BASE_URL") or _DEFAULT_BASE_URL
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    logger.info("Tavily %s request", endpoint)

    response = httpx.post(
        url,
        json=dict(payload),
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def _normalize_tavily_search_results(response: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize Tavily search results to Hermes' shared response contract."""
    web_results = []
    for index, result in enumerate(response.get("results", [])):
        web_results.append(
            {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "description": result.get("content", ""),
                "position": index + 1,
            }
        )
    return {"success": True, "data": {"web": web_results}}


def _normalize_tavily_documents(
    response: Dict[str, Any], fallback_url: str = ""
) -> List[Dict[str, Any]]:
    """Normalize successful and per-URL failed Tavily extract results."""
    documents: List[Dict[str, Any]] = []
    for result in response.get("results", []):
        url = result.get("url") or fallback_url
        raw = result.get("raw_content", "") or result.get("content", "")
        title = result.get("title", "")
        documents.append(
            {
                "url": url,
                "title": title,
                "content": raw,
                "raw_content": raw,
                "metadata": {"sourceURL": url, "title": title},
            }
        )

    for failure in response.get("failed_results", []):
        url = failure.get("url") or fallback_url
        documents.append(
            {
                "url": url,
                "title": "",
                "content": "",
                "raw_content": "",
                "error": failure.get("error", "extraction failed"),
                "metadata": {"sourceURL": url},
            }
        )
    # Older Tavily responses used a simple ``failed_urls`` collection. Keep
    # reading it so existing response fixtures and proxies remain compatible.
    for failure in response.get("failed_urls", []):
        url = failure if isinstance(failure, str) else str(failure)
        documents.append(
            {
                "url": url,
                "title": "",
                "content": "",
                "raw_content": "",
                "error": "extraction failed",
                "metadata": {"sourceURL": url},
            }
        )
    return documents


class TavilyWebSearchProvider(WebSearchProvider):
    """Tavily implementation of the shared search/extract contract."""

    @property
    def name(self) -> str:
        return "tavily"

    @property
    def display_name(self) -> str:
        return "Tavily"

    def is_available(self) -> bool:
        return bool(get_provider_env("TAVILY_API_KEY"))

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        try:
            from tools.interrupt import is_interrupted

            if is_interrupted():
                return {"success": False, "error": "Interrupted"}
            raw = _tavily_request(
                "search",
                {
                    "query": query,
                    "max_results": min(max(int(limit), 1), 20),
                    "include_raw_content": False,
                    "include_images": False,
                },
            )
            return _normalize_tavily_search_results(raw)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — vendor errors are tool results
            logger.warning("Tavily search failed: %s", exc)
            return {"success": False, "error": f"Tavily search failed: {exc}"}

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        try:
            from tools.interrupt import is_interrupted

            if is_interrupted():
                return [
                    {"url": url, "title": "", "content": "", "error": "Interrupted"}
                    for url in urls
                ]

            payload: Dict[str, Any] = {
                "urls": list(urls),
                "include_images": False,
            }
            output_format = str(kwargs.get("format") or "").strip().lower()
            if output_format in {"markdown", "text"}:
                payload["format"] = output_format
            raw = _tavily_request("extract", payload)
            return _normalize_tavily_documents(
                raw, fallback_url=urls[0] if urls else ""
            )
        except ValueError as exc:
            return [
                {"url": url, "title": "", "content": "", "error": str(exc)}
                for url in urls
            ]
        except Exception as exc:  # noqa: BLE001 — vendor errors are tool results
            logger.warning("Tavily extract failed: %s", exc)
            return [
                {
                    "url": url,
                    "title": "",
                    "content": "",
                    "error": f"Tavily extract failed: {exc}",
                }
                for url in urls
            ]

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Tavily",
            "badge": "free tier",
            "tag": "Search and extract with one provider.",
            "env_vars": [
                {
                    "key": "TAVILY_API_KEY",
                    "prompt": "Tavily API key",
                    "url": "https://app.tavily.com/home",
                }
            ],
        }
