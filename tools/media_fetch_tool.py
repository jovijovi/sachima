#!/usr/bin/env python3
"""Profile-scoped media fetch tools.

This module exposes a narrow URL-to-local-media workflow for companion
profiles. It intentionally does not provide a general web client or filesystem
access: downloads are HTTPS-only, rooted under the active ``HERMES_HOME``, and
limited to common image/video formats.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

import yaml

from hermes_constants import get_hermes_home
from tools.registry import registry
from utils import atomic_replace

IMAGE_MAX_BYTES = 50 * 1024 * 1024
VIDEO_MAX_BYTES = 2 * 1024 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024
_DEFAULT_CONFIG = {
    "image_max_bytes": IMAGE_MAX_BYTES,
    "video_max_bytes": VIDEO_MAX_BYTES,
    "timeout_seconds": 30,
    "max_redirects": 3,
    "allowed_image_extensions": [".png", ".jpg", ".jpeg", ".webp", ".gif"],
    "allowed_video_extensions": [".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"],
    "allowed_image_mimes": ["image/png", "image/jpeg", "image/webp", "image/gif"],
    "allowed_video_mimes": [
        "video/mp4", "video/quicktime", "video/webm", "video/x-matroska",
        "video/x-msvideo", "video/avi", "application/octet-stream",
    ],
}

_IMAGE_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_VIDEO_MIME_BY_EXT = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _error(message: str, **extra: Any) -> str:
    payload = {"success": False, "error": message}
    payload.update(extra)
    return _json(payload)


def _load_config() -> dict[str, Any]:
    cfg = dict(_DEFAULT_CONFIG)
    config_path = get_hermes_home() / "config.yaml"
    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            section = raw.get("media_fetch") if isinstance(raw, dict) else None
            if isinstance(section, dict):
                cfg.update(section)
        except Exception:
            # Config parse failures must not weaken boundaries.
            pass

    for key in ("image_max_bytes", "video_max_bytes", "timeout_seconds", "max_redirects"):
        try:
            cfg[key] = int(cfg.get(key) or _DEFAULT_CONFIG[key])
        except (TypeError, ValueError):
            cfg[key] = _DEFAULT_CONFIG[key]
    for key in (
        "allowed_image_extensions", "allowed_video_extensions",
        "allowed_image_mimes", "allowed_video_mimes",
    ):
        if not isinstance(cfg.get(key), list):
            cfg[key] = _DEFAULT_CONFIG[key]
        cfg[key] = [str(v).lower() for v in cfg[key]]
    return cfg


def _media_root(cfg: dict[str, Any] | None = None) -> Path:
    home = get_hermes_home().resolve()
    raw_root = home / "workspace" / "media"
    current = home
    for part in raw_root.relative_to(home).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("media root cannot contain symlink components")
    root = raw_root.resolve()
    try:
        root.relative_to(home)
    except ValueError as exc:
        raise ValueError("media root must remain inside HERMES_HOME") from exc
    return root


def _safe_relative_path(path: str) -> Path:
    value = str(path or "").strip()
    if not value:
        raise ValueError("path is required")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("path traversal is not allowed")
    rel = Path(value)
    if rel.is_absolute():
        raise ValueError("absolute paths are not allowed")
    if any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError("path traversal is not allowed")
    return rel


def _resolve_media_path(path: str, *, must_exist: bool = False) -> tuple[Path, Path, dict[str, Any]]:
    cfg = _load_config()
    root = _media_root(cfg)
    root.mkdir(parents=True, exist_ok=True)
    rel = _safe_relative_path(path)
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes media root") from exc
    if must_exist and not target.exists():
        raise FileNotFoundError(path)
    if target.exists() and target.is_symlink():
        raise ValueError("symlink targets are not allowed")
    return root, target, cfg


def _is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return bool(ip.is_global and not ip.is_loopback and not ip.is_link_local and not ip.is_multicast)


def _resolve_public_host(hostname: str) -> list[str]:
    if not hostname:
        raise ValueError("URL host is required")
    try:
        # Literal IPs do not need DNS resolution.
        ipaddress.ip_address(hostname.strip("[]"))
        addresses: list[str] = [hostname.strip("[]")]
    except ValueError:
        addresses = sorted({str(item[4][0]) for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)})
    if not addresses:
        raise ValueError("URL host did not resolve")
    blocked = [addr for addr in addresses if not _is_public_ip(addr)]
    if blocked:
        raise ValueError("URL host must resolve only to public IP addresses")
    return addresses


def _validate_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.scheme.lower() != "https":
        raise ValueError("only https URLs are allowed")
    if not parsed.hostname:
        raise ValueError("URL host is required")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")
    _resolve_public_host(parsed.hostname)
    return parsed


class _PinnedHTTPSResponse:
    def __init__(self, response: http.client.HTTPResponse, sock: ssl.SSLSocket, url: str):
        self._response = response
        self._sock = sock
        self.url = url
        self.headers = response.headers
        self.status = response.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def read(self, size: int = -1) -> bytes:
        return self._response.read(size)

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._sock.close()


def _request_target(parsed: urllib.parse.ParseResult) -> str:
    return urllib.parse.urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))


def _open_once(parsed: urllib.parse.ParseResult, timeout: int, addresses: list[str]):
    hostname = parsed.hostname or ""
    port = parsed.port or 443
    target = _request_target(parsed)
    host_header = parsed.netloc
    last_exc: Exception | None = None
    context = ssl.create_default_context()
    for address in addresses:
        if not _is_public_ip(address):
            raise ValueError("URL host must resolve only to public IP addresses")
        raw_sock = None
        tls_sock = None
        try:
            raw_sock = socket.create_connection((address, port), timeout=timeout)
            tls_sock = context.wrap_socket(raw_sock, server_hostname=hostname)
            raw_sock = None
            request = (
                f"GET {target} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                "User-Agent: Hermes media_fetch/1.0\r\n"
                "Accept: */*\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            tls_sock.sendall(request)
            response = http.client.HTTPResponse(tls_sock)
            response.begin()
            return _PinnedHTTPSResponse(response, tls_sock, urllib.parse.urlunparse(parsed))
        except Exception as exc:
            last_exc = exc
            if tls_sock is not None:
                try:
                    tls_sock.close()
                except OSError:
                    pass
            if raw_sock is not None:
                try:
                    raw_sock.close()
                except OSError:
                    pass
    if last_exc:
        raise last_exc
    raise ValueError("URL host did not resolve")


def _open_validated_response(url: str, cfg: dict[str, Any]):
    current_url = url
    timeout = int(cfg["timeout_seconds"])
    max_redirects = max(int(cfg.get("max_redirects", 3)), 0)
    for _ in range(max_redirects + 1):
        parsed = _validate_url(current_url)
        addresses = _resolve_public_host(parsed.hostname or "")
        response = _open_once(parsed, timeout, addresses)
        status = int(getattr(response, "status", 200) or 200)
        if status in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("redirect response missing Location header")
            current_url = urllib.parse.urljoin(current_url, location)
            continue
        if status >= 400:
            response.close()
            raise urllib.error.HTTPError(current_url, status, "HTTP request failed", response.headers, None)
        final_url = getattr(response, "geturl", lambda: current_url)()
        final_parsed = _validate_url(final_url)
        return response, final_parsed
    raise ValueError("too many redirects")


def _safe_filename_from_url(parsed: urllib.parse.ParseResult, content_type: str) -> str:
    raw_name = Path(urllib.parse.unquote(parsed.path or "")).name or "download"
    raw_name = raw_name.split("?", 1)[0].split("#", 1)[0]
    name = _SAFE_NAME_RE.sub("_", raw_name).strip("._") or "download"
    stem = Path(name).stem or "download"
    suffix = Path(name).suffix.lower()
    if not suffix:
        suffix = _extension_for_mime(content_type) or ".bin"
    return f"{stem[:80]}{suffix}"


def _extension_for_mime(mime: str) -> str | None:
    mime = (mime or "").lower()
    for ext, candidate in {**_IMAGE_MIME_BY_EXT, **_VIDEO_MIME_BY_EXT}.items():
        if candidate == mime:
            return ext
    return None


def _kind_for_ext(ext: str, cfg: dict[str, Any]) -> str | None:
    ext = ext.lower()
    if ext in set(cfg["allowed_image_extensions"]):
        return "image"
    if ext in set(cfg["allowed_video_extensions"]):
        return "video"
    return None


def _max_bytes_for_kind(kind: str, cfg: dict[str, Any]) -> int:
    return int(cfg["image_max_bytes"] if kind == "image" else cfg["video_max_bytes"])


def _sniff_kind_magic(data: bytes) -> tuple[str | None, str | None]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image", "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image", "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video", "video/mp4"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "video", "video/webm"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"AVI ":
        return "video", "video/x-msvideo"
    return None, None


def _mime_allowed(kind: str, mime: str, cfg: dict[str, Any]) -> bool:
    mime = (mime or "application/octet-stream").lower()
    if mime == "application/octet-stream":
        return True
    allowed = cfg["allowed_image_mimes"] if kind == "image" else cfg["allowed_video_mimes"]
    return mime in set(allowed)


def _target_path(root: Path, filename: str, kind: str) -> Path:
    folder = "images" if kind == "image" else "videos"
    target = (root / folder / filename).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes media root") from exc
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        target = target.with_name(f"{stem}-{int(time.time())}{suffix}")
    return target


def _cleanup_empty_dirs(start: Path, stop: Path) -> None:
    current = start
    stop = stop.resolve()
    while current != stop and current.exists():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _content_type_from_headers(headers: Any) -> str:
    try:
        mime = headers.get_content_type()
    except Exception:
        mime = None
    if not mime:
        try:
            mime = headers.get("content-type")
        except Exception:
            mime = None
    return str(mime or "application/octet-stream").split(";", 1)[0].lower()


def _content_length_from_headers(headers: Any) -> int | None:
    try:
        value = headers.get("content-length")
    except Exception:
        value = None
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def media_fetch_url(url: str, task_id: str | None = None) -> str:
    """Download one HTTPS image/video URL into the active profile media workspace."""
    tmp_path: str | None = None
    target: Path | None = None
    root: Path | None = None
    try:
        cfg = _load_config()
        root = _media_root(cfg)
        response, final_parsed = _open_validated_response(url, cfg)
        with response:
            content_type = _content_type_from_headers(getattr(response, "headers", {}))
            filename = _safe_filename_from_url(final_parsed, content_type)
            ext = Path(filename).suffix.lower()
            kind = _kind_for_ext(ext, cfg)
            if not kind:
                raise ValueError("URL path must end with an allowed image or video extension")
            if not _mime_allowed(kind, content_type, cfg):
                raise ValueError(f"content-type {content_type} is not allowed for {kind}")
            max_bytes = _max_bytes_for_kind(kind, cfg)
            content_length = _content_length_from_headers(getattr(response, "headers", {}))
            if content_length is not None and content_length > max_bytes:
                raise ValueError(f"content-length exceeds configured {kind}_max_bytes")

            target = _target_path(root, filename, kind)
            fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
            total = 0
            first_bytes = b""
            digest = hashlib.sha256()
            try:
                with os.fdopen(fd, "wb") as out:
                    while True:
                        chunk = response.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError(f"download exceeds configured {kind}_max_bytes")
                        if len(first_bytes) < 64:
                            first_bytes = (first_bytes + chunk)[:64]
                        digest.update(chunk)
                        out.write(chunk)
                    out.flush()
                    os.fsync(out.fileno())
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                _cleanup_empty_dirs(target.parent, root)
                raise

            sniffed_kind, sniffed_mime = _sniff_kind_magic(first_bytes)
            if sniffed_kind != kind:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                _cleanup_empty_dirs(target.parent, root)
                raise ValueError("file magic does not match requested media kind")
            if sniffed_mime and not _mime_allowed(kind, sniffed_mime, cfg):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                _cleanup_empty_dirs(target.parent, root)
                raise ValueError("file magic MIME is not allowed")

            atomic_replace(tmp_path, target)
            tmp_path = None
            payload = {
                "success": True,
                "kind": kind,
                "path": str(target),
                "relative_path": target.relative_to(root).as_posix(),
                "media_marker": f"MEDIA:{target}",
                "mime": sniffed_mime or content_type,
                "bytes": total,
                "sha256": digest.hexdigest(),
                "max_bytes": max_bytes,
            }
            return _json(payload)
    except Exception as exc:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        if target is not None and root is not None:
            _cleanup_empty_dirs(target.parent, root)
        return _error(str(exc))


def media_list(path: str = "", task_id: str | None = None) -> str:
    """List downloaded media files under the active profile media workspace."""
    try:
        cfg = _load_config()
        root = _media_root(cfg)
        root.mkdir(parents=True, exist_ok=True)
        base = root if not path else (root / _safe_relative_path(path)).resolve()
        try:
            base.relative_to(root)
        except ValueError as exc:
            raise ValueError("path escapes media root") from exc
        if base.exists() and base.is_symlink():
            raise ValueError("symlink targets are not allowed")
        if not base.exists():
            return _json({"success": True, "root": str(root), "files": []})
        allowed = set(cfg["allowed_image_extensions"] + cfg["allowed_video_extensions"])
        candidates = [base] if base.is_file() else base.rglob("*")
        files = []
        for item in candidates:
            if not item.is_file() or item.is_symlink() or item.suffix.lower() not in allowed:
                continue
            rel = item.relative_to(root).as_posix()
            kind = "image" if rel.startswith("images/") else "video" if rel.startswith("videos/") else (_kind_for_ext(item.suffix.lower(), cfg) or "media")
            files.append({"path": rel, "kind": kind, "bytes": item.stat().st_size})
        return _json({"success": True, "root": str(root), "files": sorted(files, key=lambda x: x["path"])})
    except Exception as exc:
        return _error(str(exc))


def media_delete(path: str, task_id: str | None = None) -> str:
    """Delete one downloaded media file under the active profile media workspace."""
    try:
        root, target, cfg = _resolve_media_path(path, must_exist=True)
        if not target.is_file():
            raise ValueError("path is not a file")
        if target.suffix.lower() not in set(cfg["allowed_image_extensions"] + cfg["allowed_video_extensions"]):
            raise ValueError("file extension is not managed by media_fetch")
        size = target.stat().st_size
        rel = target.relative_to(root).as_posix()
        target.unlink()
        _cleanup_empty_dirs(target.parent, root)
        return _json({"success": True, "path": rel, "bytes": size})
    except Exception as exc:
        return _error(str(exc))


def check_media_fetch_requirements() -> bool:
    return True


MEDIA_FETCH_URL_SCHEMA = {
    "name": "media_fetch_url",
    "description": (
        "Download one HTTPS image/video URL into the active profile's private media workspace. "
        "Images are limited to 50 MiB by default; videos to 2 GiB. Returns a MEDIA: marker for callers that support media delivery."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "HTTPS URL of a common image or video file."},
        },
        "required": ["url"],
    },
}

MEDIA_LIST_SCHEMA = {
    "name": "media_list",
    "description": "List downloaded image/video files in the active profile's private media workspace.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Optional relative path under the media workspace."},
        },
        "required": [],
    },
}

MEDIA_DELETE_SCHEMA = {
    "name": "media_delete",
    "description": "Delete one downloaded image/video file from the active profile's private media workspace.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path under the media workspace, e.g. images/cat.png."},
        },
        "required": ["path"],
    },
}

registry.register(
    name="media_fetch_url",
    toolset="media_fetch",
    schema=MEDIA_FETCH_URL_SCHEMA,
    handler=lambda args, **kw: media_fetch_url(url=args.get("url", ""), task_id=kw.get("task_id")),
    check_fn=check_media_fetch_requirements,
    emoji="🖼️",
)

registry.register(
    name="media_list",
    toolset="media_fetch",
    schema=MEDIA_LIST_SCHEMA,
    handler=lambda args, **kw: media_list(path=args.get("path", ""), task_id=kw.get("task_id")),
    check_fn=check_media_fetch_requirements,
    emoji="🗃️",
)

registry.register(
    name="media_delete",
    toolset="media_fetch",
    schema=MEDIA_DELETE_SCHEMA,
    handler=lambda args, **kw: media_delete(path=args.get("path", ""), task_id=kw.get("task_id")),
    check_fn=check_media_fetch_requirements,
    emoji="🧹",
)
