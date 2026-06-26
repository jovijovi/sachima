"""Deterministic P6-B read-only planning/report prompt (smoke prerequisite).

Prepares — but never runs — the prompt material for a later, separately approved
bounded read-only real-agent planning/report step. It mirrors ``smoke_prompt.py``:
the canonical prompt lives in code, a committed fixture mirrors it byte-for-byte,
and the builder re-screens on every build so a drifted prompt fails closed instead
of materializing.

Boundaries:

  * The prompt is repo-controlled, deterministic, bounded, harmless, and
    read-only. It is never assembled from raw IM text, card JSON, media
    bytes/paths, tool output, environment dumps, credentials, platform ids,
    callback URLs, or host-private paths.
  * Only the digest/ref are meant for durable state. The raw string is handed to
    the controlled exec seam exclusively through the explicitly injected
    materializer, after the atomic pre-launch claim — never into durable claim
    state, fingerprints, or query projections.
  * Nothing here invokes a real runner, a supervisor, or any delivery surface.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .activity_controlled_exec import _has_exec_unsafe_marker
from .local_offline import _value_is_unsafe

P6B_PLANNING_REPORT_PROMPT_TYPE = "sachima.supervisor.p6b_planning_report_prompt.v1"
#: Claim-check-safe ref recorded in requests/evidence instead of raw text.
P6B_PLANNING_REPORT_PROMPT_REF = "p6b_planning_report_prompt_v1"
#: Hard upper bound; the controlled exec seam additionally enforces its own.
P6B_PLANNING_REPORT_PROMPT_MAX_CHARS = 2000
#: Committed fixture (relative to the repo root) that mirrors the build.
P6B_PLANNING_REPORT_PROMPT_FIXTURE_RELATIVE_PATH = (
    "tests/fixtures/sachima_supervisor/p6b_planning_report_prompt.v1.txt"
)

_PROMPT = (
    "Sachima P6-B deterministic read-only planning/report prompt v1.\n"
    "\n"
    "You are the read-only Sachima planning reviewer. Perform exactly one\n"
    "bounded, read-only review and nothing else:\n"
    "\n"
    "1. Read the committed fixture file\n"
    "   tests/fixtures/sachima_supervisor/controlled_local_activity_dry_run_evidence.v1.json\n"
    "   relative to the current workspace root.\n"
    '2. Confirm it parses as JSON and that its top-level "type" field equals\n'
    '   "sachima.supervisor.controlled_local_activity_dry_run_evidence.v1".\n'
    "\n"
    "Rules: do not modify any file, do not run commands, do not fetch\n"
    "resources, do not read any other file, and do not copy file contents\n"
    "into your reply.\n"
    "\n"
    "Produce a short plain-text planning/report summary. Begin with\n"
    '"VERDICT: PASS" when both checks hold, otherwise "VERDICT: BLOCKERS"\n'
    "followed by concrete findings.\n"
)


class P6BPlanningReportPromptError(Exception):
    """Fail-closed prompt-builder error carrying a stable, non-leaking code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


def build_p6b_planning_report_prompt() -> dict[str, Any]:
    """Build the deterministic P6-B planning/report prompt payload.

    Returns the prompt text, its sha256 digest, the claim-check-safe ref, and the
    mirrored fixture path. Deterministic: no timestamps, no randomness. The safety
    screen is re-checked on every build so a drifted prompt fails closed instead
    of materializing.
    """

    prompt = _PROMPT
    if (
        not prompt
        or len(prompt) > P6B_PLANNING_REPORT_PROMPT_MAX_CHARS
        or _value_is_unsafe(prompt)
        or _has_exec_unsafe_marker(prompt)
    ):
        raise P6BPlanningReportPromptError(
            "p6b_planning_report_prompt_unsafe", "planning/report prompt failed its safety screen"
        )
    return {
        "type": P6B_PLANNING_REPORT_PROMPT_TYPE,
        "prompt_ref": P6B_PLANNING_REPORT_PROMPT_REF,
        "prompt": prompt,
        "prompt_sha256": "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_chars": len(prompt),
        "fixture_relative_path": P6B_PLANNING_REPORT_PROMPT_FIXTURE_RELATIVE_PATH,
    }


def materialize_p6b_planning_report_prompt(_request: Any = None) -> str:
    """Prompt materializer shaped for the controlled exec seam.

    Accepts (and ignores) the controlled exec request so it can be passed directly
    as ``prompt_materializer=...``. Injection stays explicit: nothing wires this in
    by default.
    """

    return build_p6b_planning_report_prompt()["prompt"]


__all__ = [
    "P6B_PLANNING_REPORT_PROMPT_TYPE",
    "P6B_PLANNING_REPORT_PROMPT_REF",
    "P6B_PLANNING_REPORT_PROMPT_MAX_CHARS",
    "P6B_PLANNING_REPORT_PROMPT_FIXTURE_RELATIVE_PATH",
    "P6BPlanningReportPromptError",
    "build_p6b_planning_report_prompt",
    "materialize_p6b_planning_report_prompt",
]
