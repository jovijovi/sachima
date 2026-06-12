"""Tests for the deterministic Phase D smoke prompt fixture/builder.

The builder is a Phase D smoke *prerequisite*: it prepares a deterministic,
bounded, harmless, repo-controlled prompt plus a stable digest. Nothing here
runs a smoke, starts an AGENT, or touches acpx/npx/Gateway/Feishu/live paths.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import sachima_supervisor
from sachima_supervisor.local_offline import _value_is_unsafe
from sachima_supervisor.smoke_prompt import (
    PHASE_D_SMOKE_PROMPT_FIXTURE_RELATIVE_PATH,
    PHASE_D_SMOKE_PROMPT_MAX_CHARS,
    PHASE_D_SMOKE_PROMPT_REF,
    PHASE_D_SMOKE_PROMPT_TYPE,
    build_phase_d_smoke_prompt,
    materialize_phase_d_smoke_prompt,
)

_REF_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# Mirrors the no-leak render tokens asserted across the controlled-exec tests
# plus the exec-unsafe markers screened at the controlled exec boundary.
_FORBIDDEN_PROMPT_TOKENS = (
    "raw prompt",
    "prompt body",
    "raw_prompt",
    "prompt_body",
    "media_path",
    "media path",
    "card_json",
    "oc_private",
    "ou_private",
    "om_private",
    "/tmp/",
    "secret token",
    "traceback",
    "exception detail",
    "gateway",
    "feishu",
    "webhook",
    "api_key",
    "bearer ",
    "password",
)

_REPO_ROOT = Path(sachima_supervisor.__file__).resolve().parent.parent


def test_builder_is_deterministic_across_calls() -> None:
    first = build_phase_d_smoke_prompt()
    second = build_phase_d_smoke_prompt()

    assert first == second
    assert first is not second


def test_builder_payload_shape_and_stable_digest() -> None:
    payload = build_phase_d_smoke_prompt()

    assert set(payload) == {
        "type",
        "prompt_ref",
        "prompt",
        "prompt_sha256",
        "prompt_chars",
        "fixture_relative_path",
    }
    assert payload["type"] == PHASE_D_SMOKE_PROMPT_TYPE
    assert payload["type"] == "sachima.supervisor.phase_d_smoke_prompt.v1"
    assert payload["prompt_ref"] == PHASE_D_SMOKE_PROMPT_REF
    assert payload["fixture_relative_path"] == PHASE_D_SMOKE_PROMPT_FIXTURE_RELATIVE_PATH

    prompt = payload["prompt"]
    assert isinstance(prompt, str)
    assert payload["prompt_chars"] == len(prompt)
    assert _SHA256_DIGEST_RE.fullmatch(payload["prompt_sha256"]) is not None
    assert payload["prompt_sha256"] == (
        "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    )


def test_prompt_is_bounded_and_prompt_ref_is_claim_check_safe() -> None:
    payload = build_phase_d_smoke_prompt()

    assert 0 < payload["prompt_chars"] <= PHASE_D_SMOKE_PROMPT_MAX_CHARS
    assert _REF_RE.fullmatch(payload["prompt_ref"]) is not None


def test_prompt_content_is_safe_read_only_and_leak_free() -> None:
    prompt = build_phase_d_smoke_prompt()["prompt"]
    lowered = prompt.lower()

    assert not _value_is_unsafe(prompt)
    for token in _FORBIDDEN_PROMPT_TOKENS:
        assert token not in lowered, f"forbidden prompt token: {token}"
    # The prompt itself must instruct a read-only, bounded, non-mutating run.
    assert "read-only" in lowered
    assert "do not modify" in lowered
    assert "verdict: pass" in lowered


def test_prompt_targets_an_existing_committed_read_only_fixture() -> None:
    prompt = build_phase_d_smoke_prompt()["prompt"]
    target = (
        "tests/fixtures/sachima_supervisor/"
        "controlled_local_activity_dry_run_evidence.v1.json"
    )

    assert target in prompt
    assert (_REPO_ROOT / target).is_file()


def test_committed_fixture_mirrors_builder_output_exactly() -> None:
    payload = build_phase_d_smoke_prompt()
    fixture_path = _REPO_ROOT / PHASE_D_SMOKE_PROMPT_FIXTURE_RELATIVE_PATH

    assert fixture_path.is_file()
    assert fixture_path.read_bytes() == payload["prompt"].encode("utf-8")


def test_materializer_returns_the_builder_prompt_for_any_request() -> None:
    expected = build_phase_d_smoke_prompt()["prompt"]

    assert materialize_phase_d_smoke_prompt(None) == expected
    assert materialize_phase_d_smoke_prompt(object()) == expected
