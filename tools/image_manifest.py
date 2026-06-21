"""Provider-agnostic image tool manifest helpers."""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_LIMIT = 10
MAX_LIMIT = 50

_FORBIDDEN_KEYS = {
    "auth",
    "authorization",
    "base64",
    "digest",
    "hash",
    "headers",
    "provider_raw_response",
    "raw",
    "raw_response",
    "session_id",
    "sha256",
    "source",
    "tool_call_id",
}

_DATA_URI_RE = re.compile(r"data:([^,\s]+),[^\s]+", re.IGNORECASE)
_EMBEDDED_URL_RE = re.compile(r"https?://[^\s<>'\"\])]+", re.IGNORECASE)
_AUTH_HEADER_RE = re.compile(
    r"\b(authorization\s*:\s*(?:bearer|basic)\s+)[^\s,;]+",
    re.IGNORECASE,
)
_SECRET_KV_RE = re.compile(
    r"\b(api[_-]?key|token|secret)\s*([:=])\s*([^\s,;]+)",
    re.IGNORECASE,
)


def default_manifest_path() -> Path:
    """Return the profile-local default image manifest path."""
    return get_hermes_home() / "workspace" / "image-generation" / "manifest.jsonl"


def _utc_now() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _profile_name() -> str:
    env_profile = os.environ.get("HERMES_PROFILE", "").strip()
    if env_profile:
        return env_profile
    home = get_hermes_home()
    if home.parent.name == "profiles" and home.name:
        return home.name
    return "default"


def _is_forbidden_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in _FORBIDDEN_KEYS or lowered.endswith("_hash")


def _safe_url_netloc(netloc: str) -> tuple[str, bool]:
    """Return URL netloc without userinfo plus whether credentials were present."""
    if "@" not in netloc:
        return netloc, False
    return netloc.rsplit("@", 1)[1], True


def _strip_url_query(value: str) -> tuple[str, bool]:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return value, False
    safe_netloc, userinfo_redacted = _safe_url_netloc(parsed.netloc)
    clean = urlunsplit((parsed.scheme, safe_netloc, parsed.path, "", ""))
    return clean, bool(parsed.query or parsed.fragment or userinfo_redacted)


def _redact_data_uri(match: re.Match[str]) -> str:
    mime = match.group(1).split(";", 1)[0] or "application/octet-stream"
    return f"data:{mime};redacted"


def _strip_embedded_url(match: re.Match[str]) -> str:
    clean, _ = _strip_url_query(match.group(0))
    return clean


def _sanitize_string(value: Any, *, max_chars: int = 2000) -> str:
    text = str(value)
    clean = _DATA_URI_RE.sub(_redact_data_uri, text)
    clean = _EMBEDDED_URL_RE.sub(_strip_embedded_url, clean)
    clean = _AUTH_HEADER_RE.sub(lambda m: f"{m.group(1)}[REDACTED]", clean)
    clean = _SECRET_KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", clean)
    if len(clean) > max_chars:
        return clean[:max_chars] + "...[truncated]"
    return clean


def _sanitize_image_ref(value: Any) -> str | None:
    if value is None:
        return None
    image_text = str(value)
    parsed = urlsplit(image_text)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        clean, _ = _strip_url_query(image_text)
        return _sanitize_string(clean, max_chars=2000)
    if image_text.startswith("data:"):
        return _sanitize_string(image_text, max_chars=2000)
    if Path(image_text).is_absolute():
        return Path(image_text).name or None
    if re.match(r"^[A-Za-z]:[\\/]", image_text):
        return PureWindowsPath(image_text).name or None
    return _sanitize_string(image_text, max_chars=2000)


def sanitize_input_image_metadata(image: Any) -> dict[str, Any] | None:
    """Return sanitized metadata for a single edit input image."""
    if image is None:
        return None
    image_text = str(image)
    if not image_text.strip():
        return None

    if image_text.startswith("data:"):
        header = image_text.split(",", 1)[0]
        mime_type = header[5:].split(";", 1)[0] or "application/octet-stream"
        return {
            "kind": "data_uri",
            "mime_type": mime_type,
            "length_chars": len(image_text),
        }

    parsed = urlsplit(image_text)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        safe_netloc, _ = _safe_url_netloc(parsed.netloc)
        clean = urlunsplit((parsed.scheme, safe_netloc, parsed.path, "", ""))
        return {
            "kind": "url",
            "scheme": parsed.scheme,
            "host": safe_netloc,
            "path": parsed.path or "/",
            "url": clean,
            "query_redacted": bool(parsed.query or parsed.fragment),
        }

    path = Path(image_text)
    metadata: dict[str, Any] = {
        "kind": "file",
        "name": path.name,
        "suffix": path.suffix,
        "is_absolute": path.is_absolute(),
    }
    try:
        metadata["exists"] = path.exists()
        if path.exists() and path.is_file():
            metadata["size_bytes"] = path.stat().st_size
    except OSError:
        metadata["exists"] = None
    return metadata


def _normalized_args(args: Mapping[str, Any]) -> dict[str, Any]:
    prompt = str(args.get("prompt", "") or "")
    normalized: dict[str, Any] = {
        "prompt_chars": len(prompt),
        "aspect_ratio": str(args.get("aspect_ratio", "landscape") or "landscape"),
    }
    if args.get("content_summary"):
        normalized["content_summary_chars"] = len(str(args.get("content_summary")))
    if args.get("image"):
        image_meta = sanitize_input_image_metadata(args.get("image"))
        if image_meta:
            normalized["input_image_kind"] = image_meta.get("kind")
    return normalized


def _parse_payload(response_text: str | None, result_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(result_payload, Mapping):
        return dict(result_payload)
    if not response_text:
        return {}
    try:
        parsed = json.loads(response_text)
    except (TypeError, json.JSONDecodeError):
        return {
            "success": False,
            "error": "Tool returned a non-JSON response",
            "error_type": "tool_contract",
        }
    return parsed if isinstance(parsed, dict) else {}


def _payload_success(payload: Mapping[str, Any]) -> bool:
    return bool(payload.get("success") is True)


def _coerce_duration_ms(duration_ms: int | float | None) -> int:
    try:
        return max(0, int(round(float(duration_ms or 0))))
    except (TypeError, ValueError):
        return 0


def _image_output(ref: Any) -> dict[str, str] | None:
    sanitized = _sanitize_image_ref(ref)
    if not sanitized:
        return None
    return {"kind": "image", "ref": sanitized}


def _outputs_from_payload(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    outputs: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(ref: Any) -> None:
        item = _image_output(ref)
        if not item:
            return
        ref_text = item["ref"]
        if ref_text in seen:
            return
        seen.add(ref_text)
        outputs.append(item)

    if "image" in payload:
        add(payload.get("image"))

    images = payload.get("images")
    if isinstance(images, list):
        for image in images:
            if isinstance(image, Mapping):
                add(image.get("url") or image.get("image") or image.get("path"))
            else:
                add(image)

    return outputs


def _result_from_payload(payload: Mapping[str, Any], duration_ms: int | float | None) -> dict[str, Any]:
    return {
        "success": _payload_success(payload),
        "duration_ms": _coerce_duration_ms(duration_ms),
        "outputs": _outputs_from_payload(payload),
    }


def _error_from_payload(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if _payload_success(payload):
        return None
    message = payload.get("error")
    error_type = payload.get("error_type")
    if message is None and error_type is None:
        return None
    error: dict[str, Any] = {}
    if error_type is not None:
        error["error_type"] = _sanitize_string(error_type, max_chars=200)
    if message is not None:
        error["message"] = _sanitize_string(message, max_chars=1000)
    return error


def _optional_backend_field(*values: Any) -> str | None:
    for value in values:
        if value is not None and str(value).strip():
            return _sanitize_string(value, max_chars=500)
    return None


def _backend_from_payload(
    backend: str | None,
    payload: Mapping[str, Any],
    *,
    operation: str,
    args: Mapping[str, Any],
) -> dict[str, Any]:
    backend_info: dict[str, Any] = {
        "provider": _optional_backend_field(backend, payload.get("provider")),
        "endpoint_kind": _sanitize_string(operation, max_chars=100),
    }
    model = _optional_backend_field(payload.get("model"), args.get("model"))
    if model:
        backend_info["model"] = model
    for key in ("resolution", "quality"):
        value = _optional_backend_field(payload.get(key), args.get(key))
        if value:
            backend_info[key] = value
    return {key: value for key, value in backend_info.items() if value is not None}


def _sanitize_manifest_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if _is_forbidden_key(key_text):
                continue
            sanitized[key_text] = _sanitize_manifest_value(child)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_manifest_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value, max_chars=2000)
    return value


def _input_images_for(tool: str, args: Mapping[str, Any], input_images: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if input_images is not None:
        sanitized_items: list[dict[str, Any]] = []
        for item in input_images:
            if not isinstance(item, Mapping):
                continue
            sanitized = _sanitize_manifest_value(item)
            if isinstance(sanitized, dict):
                sanitized_items.append(sanitized)
        return sanitized_items
    if tool == "image_edit":
        metadata = sanitize_input_image_metadata(args.get("image"))
        return [metadata] if metadata else []
    return []


def build_image_manifest_record(
    *,
    tool: str,
    operation: str,
    backend: str | None,
    args: Mapping[str, Any],
    input_images: Iterable[Mapping[str, Any]] | None = None,
    response_text: str | None = None,
    result_payload: Mapping[str, Any] | None = None,
    duration_ms: int | float | None = None,
) -> dict[str, Any]:
    """Build a sanitized v1 manifest record for an image tool call."""
    payload = _parse_payload(response_text, result_payload)
    prompt = str(args.get("prompt", "") or "")
    aspect_ratio = str(args.get("aspect_ratio", "landscape") or "landscape")

    request: dict[str, Any] = {
        "prompt": _sanitize_string(prompt, max_chars=8000),
        "prompt_chars": len(prompt),
        "aspect_ratio": aspect_ratio,
        "normalized_args": _normalized_args(args),
    }
    content_summary = args.get("content_summary")
    if content_summary is not None and str(content_summary).strip():
        request["content_summary"] = _sanitize_string(content_summary, max_chars=2000)
        request["content_summary_source"] = "agent_supplied"
        request["content_summary_verified"] = False

    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": str(uuid.uuid4()),
        "ts": _utc_now(),
        "profile": _profile_name(),
        "tool": tool,
        "operation": operation,
        "backend": _backend_from_payload(backend, payload, operation=operation, args=args),
        "request": request,
        "input_images": _input_images_for(tool, args, input_images),
        "result": _result_from_payload(payload, duration_ms),
        "error": _error_from_payload(payload),
    }


def _write_jsonl_record(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def append_image_manifest_record(
    *,
    tool: str,
    operation: str,
    backend: str | None,
    args: Mapping[str, Any],
    input_images: Iterable[Mapping[str, Any]] | None = None,
    response_text: str | None = None,
    result_payload: Mapping[str, Any] | None = None,
    duration_ms: int | float | None = None,
    manifest_path: Path | None = None,
) -> None:
    """Append one sanitized image manifest record, best-effort."""
    try:
        record = build_image_manifest_record(
            tool=tool,
            operation=operation,
            backend=backend,
            args=args,
            input_images=input_images,
            response_text=response_text,
            result_payload=result_payload,
            duration_ms=duration_ms,
        )
        _write_jsonl_record(Path(manifest_path) if manifest_path else default_manifest_path(), record)
    except Exception as exc:
        logger.debug("Image manifest append failed: %s", exc)


def _read_records(path: Path | None = None) -> list[dict[str, Any]]:
    manifest = Path(path) if path else default_manifest_path()
    if not manifest.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("schema_version") == SCHEMA_VERSION:
                records.append(parsed)
    except OSError as exc:
        logger.debug("Image manifest read failed: %s", exc)
    return records


def _record_success(record: Mapping[str, Any]) -> bool:
    result = record.get("result")
    return bool(isinstance(result, Mapping) and result.get("success") is True)


def _matches_content(record: Mapping[str, Any], needle: str | None) -> bool:
    if not needle:
        return True
    lowered = needle.lower()
    request_raw = record.get("request")
    result_raw = record.get("result")
    backend_raw = record.get("backend")
    error_raw = record.get("error")
    request: Mapping[str, Any] = request_raw if isinstance(request_raw, Mapping) else {}
    result: Mapping[str, Any] = result_raw if isinstance(result_raw, Mapping) else {}
    backend: Mapping[str, Any] = backend_raw if isinstance(backend_raw, Mapping) else {}
    error: Mapping[str, Any] = error_raw if isinstance(error_raw, Mapping) else {}
    outputs_raw = result.get("outputs")
    outputs: list[Any] = outputs_raw if isinstance(outputs_raw, list) else []
    haystack = " ".join(
        str(part or "")
        for part in (
            request.get("prompt"),
            request.get("content_summary"),
            backend.get("provider"),
            backend.get("model"),
            *(
                output.get("ref")
                for output in outputs
                if isinstance(output, Mapping)
            ),
            error.get("message"),
        )
    ).lower()
    return lowered in haystack


def _compact_record(record: Mapping[str, Any]) -> dict[str, Any]:
    request_raw = record.get("request")
    result_raw = record.get("result")
    error_raw = record.get("error")
    request: Mapping[str, Any] = request_raw if isinstance(request_raw, Mapping) else {}
    result: Mapping[str, Any] = result_raw if isinstance(result_raw, Mapping) else {}
    error: Mapping[str, Any] = error_raw if isinstance(error_raw, Mapping) else {}
    outputs_raw = result.get("outputs")
    outputs: list[Any] = outputs_raw if isinstance(outputs_raw, list) else []
    compact: dict[str, Any] = {
        "record_id": record.get("record_id"),
        "ts": record.get("ts"),
        "tool": record.get("tool"),
        "operation": record.get("operation"),
        "backend": record.get("backend"),
        "success": _record_success(record),
        "prompt": request.get("prompt"),
        "aspect_ratio": request.get("aspect_ratio"),
    }
    if request.get("content_summary"):
        compact["content_summary"] = request.get("content_summary")
    for output in outputs:
        if isinstance(output, Mapping) and output.get("ref"):
            compact["image"] = output.get("ref")
            break
    if error.get("error_type"):
        compact["error_type"] = error.get("error_type")
    if error.get("message"):
        compact["error"] = error.get("message")
    return compact


def query_image_history(
    *,
    latest: bool = True,
    limit: int = DEFAULT_LIMIT,
    tool: str | None = None,
    success: bool | None = None,
    content_search: str | None = None,
    manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return compact filtered image manifest records."""
    try:
        limit_int = int(limit)
    except (TypeError, ValueError):
        limit_int = DEFAULT_LIMIT
    limit_int = max(1, min(limit_int, MAX_LIMIT))

    records = _read_records(manifest_path)
    filtered: list[dict[str, Any]] = []
    for record in records:
        if tool and record.get("tool") != tool:
            continue
        if success is not None and _record_success(record) is not success:
            continue
        if not _matches_content(record, content_search):
            continue
        filtered.append(record)

    if latest:
        filtered.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)

    return [_compact_record(record) for record in filtered[:limit_int]]
