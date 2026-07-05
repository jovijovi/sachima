"""PR2 — host-local read-only AGENT smoke harness over the PR1 supervisor port.

Focused tests for :mod:`agent_run_supervisor_readonly_smoke`. The smoke harness
drives the *real* PR1 :class:`AgentRunSupervisorPort` through a bounded, read-only,
deterministic in-memory backend and proves the required safe semantics refs-only
and fail-closed: one run / no duplicate launch / sanitized artifact refs / no raw
prompt-stdout-platform-id in Sachima state / cleanup with no orphan. The readiness
probe proves fail-closed gating of a *real* supervisor-backed smoke: it reports
``blocked`` rather than fabricating one.

Forbidden terms below are no-leak canaries only, never behavior.
"""

from __future__ import annotations

import hashlib
import pathlib
import re

import pytest

from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    DefaultAgentRunSupervisorBackend,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_readonly_smoke import (
    AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN,
    READ_ONLY_ROLE,
    READ_ONLY_SMOKE_READINESS_LIMITATION,
    REQUIRED_RUNNER_VERSION,
    SMOKE_ARTIFACT_ROOT_INSIDE_REPO,
    SMOKE_READINESS_APPROVAL_MISMATCH,
    SMOKE_READINESS_DISABLED,
    SMOKE_READINESS_ROOT_INSIDE_REPO,
    SMOKE_READINESS_RUNNER_DIGEST_MISMATCH,
    SMOKE_READINESS_RUNNER_INVALID,
    SMOKE_READINESS_RUNNER_UNPINNED,
    SMOKE_READINESS_SCOPE_WIDENED,
    SMOKE_STABLE_CODES,
    ReadOnlySmokeFixture,
    ReadOnlySmokeReadinessRequest,
    assess_read_only_smoke_readiness,
    run_read_only_smoke,
)
from sachima_supervisor.runtime_spine.events import scan_for_leak

# A unique nonce and marker-shaped raw material the harness must never leak. Built
# by concatenation so this test module carries no contiguous forbidden literal.
_NONCE = "roSmokeNonce" + "Zz9" + "Q7"
_RAW_PROMPT = "raw" + "_prompt " + _NONCE
_AGENT_STDOUT = "agent" + "_stdout " + _NONCE
_PLATFORM_ID = "oc" + "_" + "deadbeefcafef00d"
_MARKER_RAW_MATERIAL = (_RAW_PROMPT, _AGENT_STDOUT, _PLATFORM_ID, _NONCE)

_VALID_SHA = "sha256:" + ("a" * 64)


def _write_runner(tmp_path: pathlib.Path, name: str = "runner") -> tuple[str, str]:
    path = tmp_path / name
    payload = b"local-supervisor-runner-fixture\n"
    path.write_bytes(payload)
    return str(path), "sha256:" + hashlib.sha256(payload).hexdigest()


def _marker_fixture() -> ReadOnlySmokeFixture:
    """Default deterministic fixture, but with marker-shaped raw canaries."""

    return ReadOnlySmokeFixture(raw_material=_MARKER_RAW_MATERIAL)


# --------------------------------------------------------------------------- #
# smoke — one run / no duplicate launch
# --------------------------------------------------------------------------- #
def test_smoke_passes_with_single_session_and_no_duplicate_launch():
    report = run_read_only_smoke()
    assert report.status == "pass", report.blockers
    assert report.role == READ_ONLY_ROLE
    assert report.single_session is True
    assert report.duplicate_launch_suppressed is True
    assert report.attached_event_count == 1
    assert report.backend_session_count == 1
    assert report.session_ref == "sess_1"
    assert report.checks["single_session"] == "pass"
    assert report.checks["duplicate_launch_suppressed"] == "pass"
    assert not report.blockers


def test_smoke_drives_the_real_pr1_backend_by_default():
    # An externally supplied Default backend proves the harness exercises the real
    # PR1 adapter surface (one session on that very backend), not a stub.
    backend = DefaultAgentRunSupervisorBackend()
    report = run_read_only_smoke(backend=backend)
    assert report.status == "pass", report.blockers
    assert backend.session_count() == 1


# --------------------------------------------------------------------------- #
# smoke — sanitized artifact refs
# --------------------------------------------------------------------------- #
def test_smoke_artifact_refs_are_sanitized_safe_ids():
    report = run_read_only_smoke()
    assert "ref_planning_report" in report.artifact_refs
    assert report.checks["artifact_refs_sanitized"] == "pass"
    safe = re.compile(r"[a-z][a-z0-9_]{0,127}")
    for ref in report.artifact_refs:
        assert safe.fullmatch(ref), ref
    # No raw material of any kind masquerading as an artifact ref.
    for canary in _MARKER_RAW_MATERIAL:
        assert canary not in report.artifact_refs


# --------------------------------------------------------------------------- #
# smoke — no raw prompt / stdout / platform id in Sachima state or projection
# --------------------------------------------------------------------------- #
def test_smoke_state_has_no_raw_prompt_stdout_or_platform_id():
    report = run_read_only_smoke(fixture=_marker_fixture())
    assert report.status == "pass", report.blockers
    assert report.no_leak is True
    assert report.checks["no_raw_material_in_state"] == "pass"
    # The sanitized report projection itself carries no seeded canary.
    projection = report.to_projection()
    assert scan_for_leak(projection, canaries=_MARKER_RAW_MATERIAL) is None


def test_smoke_report_projection_is_leak_scanned_and_deterministic():
    first = run_read_only_smoke().to_projection()
    second = run_read_only_smoke().to_projection()
    assert first == second
    assert scan_for_leak(first) is None
    assert first["status"] == "pass"


# --------------------------------------------------------------------------- #
# smoke — cleanup / no orphan
# --------------------------------------------------------------------------- #
def test_smoke_cleanup_leaves_no_orphan_and_releases_lease():
    report = run_read_only_smoke()
    assert report.terminal_state == "cancelled"
    assert report.orphan_free is True
    assert report.lease_released is True
    assert report.projection_status == "cancelled"
    assert report.checks["cleanup_no_orphan"] == "pass"
    assert report.checks["lease_released"] == "pass"


# --------------------------------------------------------------------------- #
# smoke — fail closed on smuggled raw material (no half-written state, no leak)
# --------------------------------------------------------------------------- #
def test_smoke_fails_closed_when_a_raw_ref_is_smuggled():
    smuggled = "raw" + "_prompt_body"  # a forbidden marker shaped as an id
    fixture = ReadOnlySmokeFixture(
        launch_refs=("ws_ro_smoke", "policy_read_only_default", smuggled)
    )
    report = run_read_only_smoke(fixture=fixture)
    assert report.status in {"failed", "blocked"}
    assert report.session_ref is None
    assert report.no_leak is True
    assert report.blockers
    assert all(code in SMOKE_STABLE_CODES for code in report.blockers)
    # The stable blocker never echoes the smuggled raw material.
    assert scan_for_leak(report.to_projection(), canaries=(smuggled,)) is None


def test_smoke_blocks_artifact_root_inside_repo():
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    fixture = ReadOnlySmokeFixture(artifact_root=str(repo_root / "sachima_supervisor"))
    report = run_read_only_smoke(fixture=fixture)
    assert report.status == "blocked"
    assert report.blockers == (SMOKE_ARTIFACT_ROOT_INSIDE_REPO,)
    assert report.session_ref is None


def test_smoke_allows_out_of_repo_artifact_root(tmp_path):
    fixture = ReadOnlySmokeFixture(artifact_root=str(tmp_path / "artifacts"))
    report = run_read_only_smoke(fixture=fixture)
    assert report.status == "pass", report.blockers
    # The raw host path never enters the sanitized report.
    assert scan_for_leak(report.to_projection()) is None


# --------------------------------------------------------------------------- #
# readiness probe — fail-closed, never fakes a real smoke
# --------------------------------------------------------------------------- #
def test_readiness_default_off_is_blocked():
    report = assess_read_only_smoke_readiness(ReadOnlySmokeReadinessRequest())
    assert report.status == "blocked"
    assert report.approval_ok is False
    assert report.blockers == (SMOKE_READINESS_DISABLED,)
    assert report.limitation == READ_ONLY_SMOKE_READINESS_LIMITATION


def test_readiness_approval_mismatch_is_blocked():
    report = assess_read_only_smoke_readiness(
        ReadOnlySmokeReadinessRequest(enabled=True, approval_token="wrong")
    )
    assert report.status == "blocked"
    assert report.blockers == (SMOKE_READINESS_APPROVAL_MISMATCH,)


def test_readiness_scope_widened_is_blocked():
    report = assess_read_only_smoke_readiness(
        ReadOnlySmokeReadinessRequest(
            enabled=True,
            approval_token=AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN,
            allow_real_agent_launch=True,
        )
    )
    assert report.status == "blocked"
    assert report.scope_ok is False
    assert report.blockers == (SMOKE_READINESS_SCOPE_WIDENED,)


def test_readiness_runner_unpinned_is_blocked_not_ready():
    report = assess_read_only_smoke_readiness(
        ReadOnlySmokeReadinessRequest(
            enabled=True,
            approval_token=AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN,
        )
    )
    assert report.status == "blocked"
    assert report.runner_pinning_status == "blocked"
    assert SMOKE_READINESS_RUNNER_UNPINNED in report.blockers


def test_readiness_in_repo_root_fails_closed(tmp_path):
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    runner_path, runner_digest = _write_runner(tmp_path)
    report = assess_read_only_smoke_readiness(
        ReadOnlySmokeReadinessRequest(
            enabled=True,
            approval_token=AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN,
            role_key=READ_ONLY_ROLE,
            cwd_root=str(repo_root / "sachima_supervisor"),
            artifact_root=str(tmp_path / "artifacts"),
            runner_binary_path=runner_path,
            runner_version=REQUIRED_RUNNER_VERSION,
            runner_binary_sha256=runner_digest,
        )
    )
    assert report.status == "failed"
    assert SMOKE_READINESS_ROOT_INSIDE_REPO in report.blockers


def test_readiness_wrong_role_or_version_fails_closed(tmp_path):
    runner_path, runner_digest = _write_runner(tmp_path)
    report = assess_read_only_smoke_readiness(
        ReadOnlySmokeReadinessRequest(
            enabled=True,
            approval_token=AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN,
            role_key="writer",
            cwd_root=str(tmp_path / "cwd"),
            artifact_root=str(tmp_path / "artifacts"),
            runner_binary_path=runner_path,
            runner_version="9_9_9",
            runner_binary_sha256=runner_digest,
        )
    )
    assert report.status == "failed"
    assert SMOKE_READINESS_RUNNER_INVALID in report.blockers


def test_readiness_digest_mismatch_fails_closed(tmp_path):
    runner_path, _runner_digest = _write_runner(tmp_path)
    report = assess_read_only_smoke_readiness(
        ReadOnlySmokeReadinessRequest(
            enabled=True,
            approval_token=AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN,
            role_key=READ_ONLY_ROLE,
            cwd_root=str(tmp_path / "cwd"),
            artifact_root=str(tmp_path / "artifacts"),
            runner_binary_path=runner_path,
            runner_version=REQUIRED_RUNNER_VERSION,
            runner_binary_sha256=_VALID_SHA,
        )
    )
    assert report.status == "failed"
    assert SMOKE_READINESS_RUNNER_DIGEST_MISMATCH in report.blockers
    projection_text = repr(report.to_projection())
    assert runner_path not in projection_text
    assert str(tmp_path) not in projection_text


def test_readiness_ready_only_when_fully_pinned_and_default_deny(tmp_path):
    runner_path, runner_digest = _write_runner(tmp_path)
    report = assess_read_only_smoke_readiness(
        ReadOnlySmokeReadinessRequest(
            enabled=True,
            approval_token=AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN,
            role_key=READ_ONLY_ROLE,
            cwd_root=str(tmp_path / "cwd"),
            artifact_root=str(tmp_path / "artifacts"),
            runner_binary_path=runner_path,
            runner_version=REQUIRED_RUNNER_VERSION,
            runner_binary_sha256=runner_digest,
        )
    )
    assert report.status == "ready"
    assert report.runner_pinning_status == "pass"
    assert not report.blockers
    # Even the ready report is leak-safe: raw host roots are digest-only.
    assert scan_for_leak(report.to_projection()) is None


def test_readiness_report_never_carries_raw_host_paths(tmp_path):
    runner_path, runner_digest = _write_runner(tmp_path)
    report = assess_read_only_smoke_readiness(
        ReadOnlySmokeReadinessRequest(
            enabled=True,
            approval_token=AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN,
            role_key=READ_ONLY_ROLE,
            cwd_root=str(tmp_path / "cwd"),
            artifact_root=str(tmp_path / "artifacts"),
            runner_binary_path=runner_path,
            runner_version=REQUIRED_RUNNER_VERSION,
            runner_binary_sha256=runner_digest,
        )
    )
    projection = report.to_projection()
    assert str(tmp_path) not in repr(projection)
    for root in projection["roots"].values():
        assert root["path_digest"].startswith("sha256:")


# --------------------------------------------------------------------------- #
# clean source additions — boundary + no-real-runner static gate
# --------------------------------------------------------------------------- #
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SOURCE = (
    _REPO_ROOT
    / "sachima_supervisor"
    / "runtime_spine"
    / "agent_run_supervisor_readonly_smoke.py"
)

_FORBIDDEN_TOKENS = re.compile(
    r"\b(acpx|npx|npm|pnpm|yarn|bunx|bun|corepack|node|network_fetch)\b"
    r"|codex|claude(?:[_-]?code)?"
    r"|subprocess|os\.system|os\.popen|os\.exec|shell\s*=\s*True"
    r"|socket\.|urllib|requests\."
    r"|git\s+(?:commit|push)|gh\s+pr",
    re.IGNORECASE,
)
_FORBIDDEN_SUBSTRINGS = ("gateway", "feishu", "lark")
_FORBIDDEN_IMPORT = re.compile(
    r"(gateway|feishu|lark|platform_adapter|temporalio)", re.IGNORECASE
)

_EXACT_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_pr2_host_local_read_only_real_agent_smoke_"
    "default_local_deterministic_single_read_only_role_policy_safe_cwd_artifact_dir_"
    "no_write_roles_no_file_mutation_no_git_mutation_no_live_no_gateway_no_feishu_"
    "no_temporal_worker_no_network_no_production_config_no_real_delivery_"
    "no_real_smoke_without_separate_approval"
)


def test_source_exists():
    assert _SOURCE.exists()


def test_no_real_runner_or_im_tokens_in_source():
    src = _SOURCE.read_text(encoding="utf-8")
    hits = [
        f"{number}:{line.strip()}"
        for number, line in enumerate(src.splitlines(), 1)
        if _FORBIDDEN_TOKENS.search(line)
    ]
    assert not hits, "PR2 source must contain no real-runner/IM tokens:\n" + "\n".join(hits)


def test_no_contiguous_boundary_words_in_source():
    src = _SOURCE.read_text(encoding="utf-8").lower()
    found = [word for word in _FORBIDDEN_SUBSTRINGS if word in src]
    assert not found, f"PR2 source must not contain contiguous boundary words: {found}"


def test_no_forbidden_imports_in_source():
    src = _SOURCE.read_text(encoding="utf-8")
    offending = [
        line.strip()
        for line in src.splitlines()
        if line.strip().startswith(("import ", "from ")) and _FORBIDDEN_IMPORT.search(line)
    ]
    assert not offending, "PR2 must not import Gateway/IM/platform/temporalio:\n" + "\n".join(
        offending
    )


def test_approval_token_value_is_exact_despite_split_literal():
    assert AGENT_RUN_SUPERVISOR_READ_ONLY_SMOKE_APPROVAL_TOKEN == _EXACT_APPROVAL_TOKEN
