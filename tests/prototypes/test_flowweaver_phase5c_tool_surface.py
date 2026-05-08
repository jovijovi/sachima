"""Default-off and forbidden-surface guards for FlowWeaver Phase 5C."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_BRANCH = "origin/feature/sachima-channel"
FORBIDDEN_PATHS = (
    "gateway/run.py",
    "run_agent.py",
    "model_tools.py",
    "toolsets.py",
    "tools/registry.py",
    "tools/mcp_tool.py",
)
FORBIDDEN_PREFIXES = (
    "gateway/platforms/",
)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def changed_files_against_merge_base() -> set[str]:
    merge_base = phase_diff_base()
    committed = set(_git("diff", "--name-only", f"{merge_base}..HEAD").splitlines())
    worktree = set(_git("diff", "--name-only").splitlines())
    cached = set(_git("diff", "--cached", "--name-only").splitlines())
    untracked = set(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return {name for name in committed | worktree | cached | untracked if name}


def phase_diff_base() -> str:
    parents = _git("rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parents) > 2:
        # Integration merge commits are not a single Phase 5C delta. Keep the
        # guard active for uncommitted edits while avoiding false positives from
        # already-approved later Sachima/FlowWeaver phases merged as a parent.
        return "HEAD"
    return _git("merge-base", BASE_BRANCH, "HEAD")


def test_phase5c_diff_does_not_touch_production_tool_or_gateway_surfaces() -> None:
    changed = changed_files_against_merge_base()
    forbidden = {
        path
        for path in changed
        if path in FORBIDDEN_PATHS or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)
    }

    assert forbidden == set()


def test_phase5c_does_not_add_a_production_registered_flowweaver_tool() -> None:
    changed = changed_files_against_merge_base()
    new_tool_files = {
        path
        for path in changed
        if path.startswith("tools/") and "flowweaver" in Path(path).name.lower()
    }

    assert new_tool_files == set()


def test_phase5c_runtime_prototype_does_not_write_mcp_config_or_runtime_config() -> None:
    changed = changed_files_against_merge_base()
    code_files = [
        ROOT / path
        for path in changed
        if path.startswith("prototypes/flowweaver_phase5c_runtime_client/") and path.endswith(".py")
    ]
    forbidden_write_markers = (
        "config.yaml",
        "mcp_servers:",
        "mcp_servers =",
        "mcp_servers]",
        "write_text(",
        "open(",
    )

    offenders: dict[str, list[str]] = {}
    for path in code_files:
        source = path.read_text(encoding="utf-8")
        matches = [marker for marker in forbidden_write_markers if marker in source]
        if matches:
            offenders[str(path.relative_to(ROOT))] = matches

    assert offenders == {}
