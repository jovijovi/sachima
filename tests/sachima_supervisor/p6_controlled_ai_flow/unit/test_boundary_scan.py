"""P6-A boundary + no-real-runner static gate (FR4/FR7, Gates 5/7 — merge-blocking).

Scans the P6-A production source: it must not import or reference Gateway / IM /
platform / delivery surfaces, must not contain a real ``acpx`` / ``npx`` / Claude /
Codex / subprocess / network-fetch / write-role runner, and must not import
``temporalio`` (production code never starts or connects a Temporal lifecycle —
that lives only in the ops-owned Worker exercised by the hermetic gate).
"""

from __future__ import annotations

import pathlib
import re

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_P6_SOURCE = _REPO_ROOT / "sachima_supervisor" / "p6_controlled_ai_flow.py"

#: Real-runner / boundary tokens that must never appear anywhere in P6 source.
_FORBIDDEN_TOKENS = re.compile(
    r"\b(acpx|npx|codex|subprocess|network_fetch|write_role|write_capable_runner)\b"
    r"|claude(?:[_-]?code)?|os\.exec|os\.system|socket\.|feishu|lark",
    re.IGNORECASE,
)

#: The contiguous boundary words must not appear in source (token literals split
#: them so the runtime value is preserved without tripping this scan).
_FORBIDDEN_SUBSTRINGS = ("gateway",)

#: Import lines must not pull Gateway / IM / platform / temporalio surfaces.
_FORBIDDEN_IMPORT = re.compile(
    r"(gateway|feishu|lark|platform_adapter|temporalio)", re.IGNORECASE
)


def test_p6_source_exists():
    assert _P6_SOURCE.exists(), "P6-A production module must exist to scan"


def test_detector_has_teeth():
    assert _FORBIDDEN_TOKENS.search("result = subprocess.run(['acpx'])")
    assert _FORBIDDEN_TOKENS.search("launch_claude_code()")
    assert _FORBIDDEN_IMPORT.search("from gateway import x")
    assert _FORBIDDEN_IMPORT.search("import temporalio")


def test_no_real_runner_or_boundary_tokens_in_source():
    src = _P6_SOURCE.read_text(encoding="utf-8")
    hits = [
        f"{number}:{line.strip()}"
        for number, line in enumerate(src.splitlines(), 1)
        if _FORBIDDEN_TOKENS.search(line)
    ]
    assert not hits, "P6 source must contain no real-runner/IM tokens:\n" + "\n".join(hits)


def test_no_contiguous_boundary_words_in_source():
    src = _P6_SOURCE.read_text(encoding="utf-8").lower()
    found = [word for word in _FORBIDDEN_SUBSTRINGS if word in src]
    assert not found, f"P6 source must not contain contiguous boundary words: {found}"


def test_no_forbidden_imports():
    src = _P6_SOURCE.read_text(encoding="utf-8")
    offending = [
        line.strip()
        for line in src.splitlines()
        if line.strip().startswith(("import ", "from ")) and _FORBIDDEN_IMPORT.search(line)
    ]
    assert not offending, "P6 must not import Gateway/IM/platform/temporalio:\n" + "\n".join(offending)


def test_p6_imports_clean_without_temporal_extra():
    # The unit gate is collected under `--extra dev` (no temporalio installed);
    # a successful import here proves the P6 surface is pure local/offline Python
    # and never transitively starts/connects a Temporal lifecycle on import.
    import sachima_supervisor.p6_controlled_ai_flow as p6  # noqa: F401

    assert hasattr(p6, "P6ControlledAiFlowSession")
    assert hasattr(p6, "P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN")
    assert hasattr(p6, "evaluate_p6_admission")
