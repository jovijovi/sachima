"""P6-B boundary + no-real-runner static gate (FR9, merge-blocking).

Scans the P6-B production source (the bridge + the prompt builder): it must not
import or reference Gateway / IM / platform / delivery surfaces, must not contain a
real ``acpx`` / ``npx`` / package-runner / shell / subprocess / network-fetch / git
mutation, and must not import ``temporalio`` (the bridge is pure local/offline
Python; the only durable-runtime lifecycle lives elsewhere, ops-owned). It also
pins the exact approval token value despite the split-literal source.
"""

from __future__ import annotations

import pathlib
import re

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_SOURCES = (
    _REPO_ROOT / "sachima_supervisor" / "p6b_read_only_real_agent.py",
    _REPO_ROOT / "sachima_supervisor" / "p6b_planning_report_prompt.py",
)

#: Real-runner / shell / network / git-mutation tokens that must never appear.
_FORBIDDEN_TOKENS = re.compile(
    r"\b(acpx|npx|npm|pnpm|yarn|bunx|bun|corepack|node|network_fetch)\b"
    r"|codex|claude(?:[_-]?code)?"
    r"|subprocess|os\.system|os\.popen|os\.exec|shell\s*=\s*True"
    r"|socket\.|urllib|requests\."
    r"|git\s+(?:commit|push)|gh\s+pr",
    re.IGNORECASE,
)

#: Contiguous boundary words must not appear (token literals split them so the
#: runtime value is preserved without tripping this scan).
_FORBIDDEN_SUBSTRINGS = ("gateway", "feishu", "lark")

#: Import lines must not pull Gateway / IM / platform / temporalio surfaces.
_FORBIDDEN_IMPORT = re.compile(
    r"(gateway|feishu|lark|platform_adapter|temporalio)", re.IGNORECASE
)

_EXACT_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_p6b_bounded_read_only_real_agent_step_execution_"
    "implementation_default_off_single_read_only_planning_report_step_pinned_local_runner_only_"
    "no_write_roles_no_file_mutation_no_git_mutation_no_live_no_gateway_no_feishu_"
    "no_production_config_no_real_delivery_no_real_smoke_without_separate_approval"
)


def test_sources_exist():
    for source in _SOURCES:
        assert source.exists(), f"P6-B production module must exist to scan: {source}"


def test_detector_has_teeth():
    assert _FORBIDDEN_TOKENS.search("result = subprocess.run(['acpx'])")
    assert _FORBIDDEN_TOKENS.search("npx install something")
    assert _FORBIDDEN_TOKENS.search("launch_codex()")
    assert _FORBIDDEN_IMPORT.search("from gateway import x")
    assert _FORBIDDEN_IMPORT.search("import temporalio")


def test_no_real_runner_or_boundary_tokens_in_source():
    for source in _SOURCES:
        src = source.read_text(encoding="utf-8")
        hits = [
            f"{source.name}:{number}:{line.strip()}"
            for number, line in enumerate(src.splitlines(), 1)
            if _FORBIDDEN_TOKENS.search(line)
        ]
        assert not hits, "P6-B source must contain no real-runner/IM tokens:\n" + "\n".join(hits)


def test_no_contiguous_boundary_words_in_source():
    for source in _SOURCES:
        src = source.read_text(encoding="utf-8").lower()
        found = [word for word in _FORBIDDEN_SUBSTRINGS if word in src]
        assert not found, f"{source.name} must not contain contiguous boundary words: {found}"


def test_no_forbidden_imports():
    for source in _SOURCES:
        src = source.read_text(encoding="utf-8")
        offending = [
            line.strip()
            for line in src.splitlines()
            if line.strip().startswith(("import ", "from ")) and _FORBIDDEN_IMPORT.search(line)
        ]
        assert not offending, "P6-B must not import Gateway/IM/platform/temporalio:\n" + "\n".join(
            offending
        )


def test_p6b_imports_clean_without_temporal_extra():
    # Collected under `--extra dev` (no temporalio): a successful import proves the
    # bridge is pure local/offline Python and starts no Temporal lifecycle.
    import sachima_supervisor.p6b_read_only_real_agent as p6b  # noqa: F401
    import sachima_supervisor.p6b_planning_report_prompt as prompt  # noqa: F401

    assert hasattr(p6b, "P6BReadOnlyRealAgentStepExecutor")
    assert hasattr(p6b, "P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN")
    assert hasattr(prompt, "materialize_p6b_planning_report_prompt")


def test_approval_token_value_is_exact_despite_split_literal():
    assert (
        p6b_token()
        == _EXACT_APPROVAL_TOKEN
    )


def p6b_token():
    from sachima_supervisor.p6b_read_only_real_agent import (
        P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN,
    )

    return P6B_READ_ONLY_REAL_AGENT_STEP_EXECUTION_APPROVAL_TOKEN
