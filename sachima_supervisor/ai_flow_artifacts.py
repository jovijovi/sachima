"""Controlled AI FLOW artifact claim-check refs (WP4 slice 1, FR3).

Local/offline only. Step outputs live in an out-of-band, caller-owned artifact
store; durable workflow state stores only the sanitized ``ArtifactRef``
projection (id, producer, digest, kind, byte count, created-at ref). Raw bodies
never enter durable state. ``verify_artifact_ref`` is called at every handoff
and re-checks digest format, byte bound, artifact kind, producer, and — when a
body resolver is supplied — a re-hash match. Any mismatch is non-retryable and
fail-closed (integrity marker), and the artifact is not propagated.

Per the WP4 convention (architecture §1.3) this module keeps its own copies of
the sanitization primitives rather than importing private helpers.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

_ARTIFACT_REF_TYPE = "sachima.supervisor.ai_flow_artifact_ref.v1"

_REF_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

#: Raw-material substrings that must never appear in a durable artifact
#: projection. Mirrors the controlled-exec markers plus the WP4 additions.
_UNSAFE_MARKERS: tuple[str, ...] = (
    "media_path",
    "raw_prompt",
    "prompt_body",
    "card_json",
    "signed_url",
    "tool_output",
)

_ARTIFACT_KEYS = frozenset(
    {
        "artifact_id",
        "producer_step_id",
        "content_digest",
        "artifact_kind",
        "byte_count",
        "created_at_ref",
    }
)


class AiFlowArtifactError(Exception):
    """Fail-closed artifact claim-check error carrying a stable code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    producer_step_id: str
    content_digest: str
    artifact_kind: str
    byte_count: int
    created_at_ref: str


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        out: list[str] = []
        for key, item in value.items():
            out.extend(_walk_strings(str(key)))
            out.extend(_walk_strings(item))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_walk_strings(item))
        return out
    return []


def _is_safe_ref(value: Any) -> bool:
    if type(value) is not str or _REF_RE.fullmatch(value) is None:
        return False
    lowered = value.lower()
    return not any(marker in lowered for marker in _UNSAFE_MARKERS)


def _normalize(ref: ArtifactRef | Mapping[str, Any]) -> ArtifactRef:
    if isinstance(ref, ArtifactRef):
        return ref
    if type(ref) is not dict or set(ref) != _ARTIFACT_KEYS:
        raise AiFlowArtifactError(
            "artifact_ref_invalid", "artifact ref must be an exact ArtifactRef mapping"
        )
    return ArtifactRef(
        artifact_id=ref["artifact_id"],
        producer_step_id=ref["producer_step_id"],
        content_digest=ref["content_digest"],
        artifact_kind=ref["artifact_kind"],
        byte_count=ref["byte_count"],
        created_at_ref=ref["created_at_ref"],
    )


def verify_artifact_ref(
    ref: ArtifactRef | Mapping[str, Any],
    *,
    expected_kind: str,
    expected_producer: str,
    max_bytes: int,
    resolve_body: Callable[[ArtifactRef], bytes] | None = None,
) -> ArtifactRef:
    """Fail-closed claim-check verification of one artifact handoff.

    Re-checks safe refs, digest format, byte bound, artifact kind, and producer.
    When ``resolve_body`` is supplied, the resolved bytes are re-hashed and must
    match ``content_digest`` and ``byte_count``. Every miss raises
    ``AiFlowArtifactError`` and the artifact must not be propagated.
    """

    artifact = _normalize(ref)
    for field_value in (
        artifact.artifact_id,
        artifact.producer_step_id,
        artifact.artifact_kind,
        artifact.created_at_ref,
    ):
        if not _is_safe_ref(field_value):
            raise AiFlowArtifactError("artifact_ref_unsafe", "unsafe artifact ref field")
    if type(artifact.content_digest) is not str or _SHA256_DIGEST_RE.fullmatch(
        artifact.content_digest
    ) is None:
        raise AiFlowArtifactError(
            "artifact_digest_format_invalid", "content digest must be sha256:<64hex>"
        )
    if type(artifact.byte_count) is not int or artifact.byte_count < 0:
        raise AiFlowArtifactError("artifact_byte_count_invalid", "byte_count must be a non-negative int")
    if artifact.byte_count > max_bytes:
        raise AiFlowArtifactError("artifact_too_large", "artifact exceeds max_artifact_bytes")
    if artifact.artifact_kind != expected_kind:
        raise AiFlowArtifactError("artifact_kind_mismatch", "artifact kind does not match contract")
    if artifact.producer_step_id != expected_producer:
        raise AiFlowArtifactError("artifact_producer_mismatch", "artifact producer does not match")
    if resolve_body is not None:
        body = resolve_body(artifact)
        if type(body) is not bytes:
            raise AiFlowArtifactError("artifact_body_invalid", "resolved artifact body must be bytes")
        if len(body) != artifact.byte_count:
            raise AiFlowArtifactError("artifact_digest_mismatch", "resolved body length disagrees")
        rehash = "sha256:" + hashlib.sha256(body).hexdigest()
        if rehash != artifact.content_digest:
            raise AiFlowArtifactError("artifact_digest_mismatch", "re-hash does not match content digest")
    return artifact


def artifact_ref_projection(ref: ArtifactRef | Mapping[str, Any]) -> dict[str, Any]:
    """Return the sanitized durable projection of an artifact ref."""

    artifact = _normalize(ref)
    projection = {
        "type": _ARTIFACT_REF_TYPE,
        "artifact_id": artifact.artifact_id,
        "producer_step_id": artifact.producer_step_id,
        "content_digest": artifact.content_digest,
        "artifact_kind": artifact.artifact_kind,
        "byte_count": artifact.byte_count,
        "created_at_ref": artifact.created_at_ref,
    }
    rendered = "\n".join(_walk_strings(projection)).lower()
    if any(marker in rendered for marker in _UNSAFE_MARKERS):
        raise AiFlowArtifactError("artifact_ref_unsafe", "artifact projection carries raw material")
    return projection
