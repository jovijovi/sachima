"""RED/GREEN tests for WP4 controlled AI FLOW artifact claim-check (FR3)."""

from __future__ import annotations

import hashlib

import pytest

from sachima_supervisor.ai_flow_artifacts import (
    _UNSAFE_MARKERS,
    AiFlowArtifactError,
    ArtifactRef,
    _walk_strings,
    artifact_ref_projection,
    verify_artifact_ref,
)

_BODY = b"deterministic architecture packet body"
_DIGEST = "sha256:" + hashlib.sha256(_BODY).hexdigest()


def _ref(**overrides) -> ArtifactRef:
    base = dict(
        artifact_id="artifact_architecture_packet",
        producer_step_id="architect",
        content_digest=_DIGEST,
        artifact_kind="architecture_packet",
        byte_count=len(_BODY),
        created_at_ref="created_at_ref_0001",
    )
    base.update(overrides)
    return ArtifactRef(**base)


def _resolver(body: bytes = _BODY):
    def _resolve(_ref: ArtifactRef) -> bytes:
        return body

    return _resolve


def test_accepts_valid_ref_with_rehash() -> None:
    ref = verify_artifact_ref(
        _ref(),
        expected_kind="architecture_packet",
        expected_producer="architect",
        max_bytes=65536,
        resolve_body=_resolver(),
    )
    assert isinstance(ref, ArtifactRef)
    assert ref.content_digest == _DIGEST


def test_accepts_valid_ref_without_rehash() -> None:
    ref = verify_artifact_ref(
        _ref(),
        expected_kind="architecture_packet",
        expected_producer="architect",
        max_bytes=65536,
    )
    assert ref.byte_count == len(_BODY)


def test_rejects_digest_format_error() -> None:
    with pytest.raises(AiFlowArtifactError):
        verify_artifact_ref(
            _ref(content_digest="not-a-sha256"),
            expected_kind="architecture_packet",
            expected_producer="architect",
            max_bytes=65536,
        )


def test_rejects_oversized_byte_count() -> None:
    with pytest.raises(AiFlowArtifactError):
        verify_artifact_ref(
            _ref(byte_count=65537),
            expected_kind="architecture_packet",
            expected_producer="architect",
            max_bytes=65536,
        )


def test_rejects_wrong_artifact_kind() -> None:
    with pytest.raises(AiFlowArtifactError):
        verify_artifact_ref(
            _ref(),
            expected_kind="blocker_review",
            expected_producer="architect",
            max_bytes=65536,
        )


def test_rejects_wrong_producer_step_id() -> None:
    with pytest.raises(AiFlowArtifactError):
        verify_artifact_ref(
            _ref(),
            expected_kind="architecture_packet",
            expected_producer="reviewer",
            max_bytes=65536,
        )


def test_rejects_rehash_mismatch() -> None:
    with pytest.raises(AiFlowArtifactError):
        verify_artifact_ref(
            _ref(),
            expected_kind="architecture_packet",
            expected_producer="architect",
            max_bytes=65536,
            resolve_body=_resolver(b"tampered body"),
        )


def test_rejects_unsafe_ref_field() -> None:
    with pytest.raises(AiFlowArtifactError):
        verify_artifact_ref(
            _ref(created_at_ref="raw_prompt_leak"),
            expected_kind="architecture_packet",
            expected_producer="architect",
            max_bytes=65536,
        )


def test_rejects_mapping_with_extra_keys() -> None:
    bad = {
        "artifact_id": "artifact_x",
        "producer_step_id": "architect",
        "content_digest": _DIGEST,
        "artifact_kind": "architecture_packet",
        "byte_count": len(_BODY),
        "created_at_ref": "created_at_ref_0001",
        "raw_prompt": "leak",
    }
    with pytest.raises(AiFlowArtifactError):
        verify_artifact_ref(
            bad,
            expected_kind="architecture_packet",
            expected_producer="architect",
            max_bytes=65536,
        )


def test_projection_has_no_unsafe_markers() -> None:
    projection = artifact_ref_projection(_ref())
    rendered = "\n".join(_walk_strings(projection)).lower()
    for marker in _UNSAFE_MARKERS:
        assert marker not in rendered
