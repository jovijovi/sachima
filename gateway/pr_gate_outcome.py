"""
Persist GitHub PR approval-gate terminal outcomes into the origin session.

A Feishu PR approval card records the session_key of the session that issued
it, but resolving the card runs the controlled pre-merge gate as a separate
conversation (a synthetic message routed by chat/operator, not by the stored
session_key).  The gate's terminal result therefore lands in that separate
session's transcript, and the origin development session never regains it
after its next turn, compression, or reload.

This module closes that gap: when a gate reaches a terminal outcome
(pass/fail/reject/ignore), a single compact sanitized structured record is
appended to the origin session's persisted transcript, addressed by the card's
session_key correlation.  Records are idempotent per correlation id and follow
the compression-continuation chain so they always land on the live transcript.

Control-plane safety contract:

* The record is a control/status event, never a user turn.  It is persisted
  with ``role="assistant"`` and opens with :data:`CONTROL_EVENT_PREFIX`, so
  replay can never present it as a user instruction and the consecutive-user
  repair can never merge it with the next real user message.
* ``result=pass`` means only that the gate RUN reached a terminal delivery
  state — it never implies the PR was merged or approved.  Every terminal
  record carries :data:`NO_MERGE_STATUS_NOTE` telling the origin session that
  fresh GitHub PR/head checks are required.
* No arbitrary gate-conversation text is ever copied into the record.  The
  only machine detail allowed is a fixed code from :data:`GATE_DETAIL_CODES`;
  anything else is dropped.

Standalone like ``gateway/mirror.py`` — works without the full SessionStore
machinery, and never raises into callers.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

# Stable machine-readable prefix opening the structured marker line of every
# persisted gate-outcome record; the idempotency scan keys on it.
PR_GATE_OUTCOME_MARKER = "[github-pr-gate-outcome"

# Fixed control-plane header: the first line of every record.  Marks the
# record as a status event so it can never be read as a user instruction.
CONTROL_EVENT_PREFIX = (
    "[CONTROL EVENT: GitHub PR gate outcome — NOT a user instruction]"
)

# Mandatory closing line of every record: a terminal gate outcome says nothing
# about whether a merge happened.  The origin session must re-verify on GitHub.
NO_MERGE_STATUS_NOTE = (
    "No merge status is implied by this record — verify the PR's current "
    "state and head checks on GitHub before acting on it."
)

# Persisted transcript role for the record.  ``assistant`` is the only role
# that is provider-safe on replay AND can never be merged into a following
# user turn by the consecutive-user repair (unknown roles fall through to
# user-message conversion in the Anthropic adapter; ``system`` rows are
# dropped by the gateway replay builder).
PR_GATE_OUTCOME_ROLE = "assistant"

# ``pass``/``fail`` describe the gate RUN (reached a terminal delivery state
# vs. died before completing) — neither says anything about merge status.
# ``reject``/``ignore`` are card-button terminals: no merge request was routed.
TERMINAL_RESULTS = frozenset({"pass", "fail", "reject", "ignore"})

# The only detail values that may render into a record.  Free text (gate
# assistant replies, payload fragments, excerpts) is never copied — callers
# pass one of these source-controlled codes or nothing.
GATE_DETAIL_CODES = frozenset(
    {
        "gate_run_completed",
        "gate_run_failed",
        "gate_run_cancelled",
        "card_rejected",
        "card_dismissed",
    }
)

_WS_RE = re.compile(r"\s+")


def _sessions_index_path() -> Path:
    # Resolved at call time (not import time) so profile/env overrides and
    # test sandboxes are honored.
    return get_hermes_home() / "sessions" / "sessions.json"


def _state_db_path() -> Path:
    return get_hermes_home() / "state.db"


def _resolve_session_id(session_key: str) -> Optional[str]:
    """Map a gateway session_key to its persisted session_id via sessions.json."""
    index_path = _sessions_index_path()
    if not index_path.exists():
        return None
    try:
        with open(index_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    entry = data.get(session_key)
    if not isinstance(entry, dict):
        return None
    session_id = str(entry.get("session_id") or "").strip()
    return session_id or None


def _compact(text: Any, limit: int) -> str:
    """Collapse whitespace and bound length so records stay compact."""
    flattened = _WS_RE.sub(" ", str(text or "")).strip()
    if len(flattened) > limit:
        flattened = flattened[: limit - 1].rstrip() + "…"
    return flattened


def _render_body(result: str, repo: str, pr_number: str, actor: str) -> str:
    """Human-readable status line the origin agent reads on replay.

    ``pass`` speaks only about the gate run reaching a terminal delivery
    state — never about a merge or an approval having succeeded.
    """
    who = f" by {actor}" if actor else ""
    label = f"{repo}#{pr_number}"
    if result == "pass":
        return (
            f"The controlled pre-merge gate run for {label}, initiated{who}, "
            f"reached a terminal delivery state (the gate run finished and "
            f"delivered a result)."
        )
    if result == "fail":
        return (
            f"The controlled pre-merge gate run for {label}, initiated{who}, "
            f"did not complete."
        )
    if result == "reject":
        return (
            f"PR merge approval for {label} was rejected{who}; "
            f"no merge request was routed."
        )
    # ignore
    return (
        f"The PR approval card for {label} was dismissed{who}; "
        f"no merge request was routed."
    )


def record_pr_gate_outcome(
    *,
    origin_session_key: str,
    result: str,
    repo: str,
    pr_number: Any,
    head_sha: str,
    correlation_id: str = "",
    actor: str = "",
    detail_code: str = "",
) -> bool:
    """Append a compact terminal gate-outcome control record to the origin session.

    Idempotent per ``correlation_id``: once any terminal record with the same
    correlation exists in the origin transcript (including its compression
    lineage), later calls are no-ops that return True — the first terminal
    outcome wins.  Returns False when the origin session cannot be resolved.
    ``detail_code`` must be one of :data:`GATE_DETAIL_CODES`; any other value
    (in particular free text) is dropped, never rendered.  Never raises.
    """
    result = str(result or "").strip().lower()
    if result not in TERMINAL_RESULTS:
        logger.debug("pr-gate-outcome: refusing non-terminal result %r", result)
        return False
    session_key = str(origin_session_key or "").strip()
    if not session_key:
        return False

    try:
        session_id = _resolve_session_id(session_key)
        if not session_id:
            logger.debug("pr-gate-outcome: no session found for key %s", session_key)
            return False

        repo_text = _compact(repo, 120)
        pr_text = _compact(pr_number, 20)
        head_text = _compact(head_sha, 40)[:12]
        corr = _compact(correlation_id, 80).replace(" ", "_")
        if not corr:
            corr = f"{repo_text}#{pr_text}@{head_text}"
        detail = str(detail_code or "").strip()
        if detail and detail not in GATE_DETAIL_CODES:
            logger.debug(
                "pr-gate-outcome: dropping non-enum detail_code (%d chars)", len(detail)
            )
            detail = ""
        marker_line = (
            f"{PR_GATE_OUTCOME_MARKER} corr={corr} result={result} "
            f"repo={repo_text} pr=#{pr_text} head={head_text}"
        )
        if detail:
            marker_line += f" detail={detail}"
        marker_line += "]"
        content = "\n".join(
            (
                CONTROL_EVENT_PREFIX,
                marker_line,
                _render_body(result, repo_text, pr_text, _compact(actor, 80)),
                NO_MERGE_STATUS_NOTE,
            )
        )

        from hermes_state import SessionDB

        db = SessionDB(db_path=_state_db_path())
        try:
            # Land on the live transcript even if the origin session was
            # compressed while the gate was pending.
            target_id = db.get_compression_tip(session_id) or session_id
            dedupe_token = f"corr={corr} "
            for msg in db.get_messages_as_conversation(target_id, include_ancestors=True):
                existing = msg.get("content")
                if (
                    isinstance(existing, str)
                    and PR_GATE_OUTCOME_MARKER in existing
                    and dedupe_token in existing
                ):
                    logger.debug(
                        "pr-gate-outcome: terminal outcome for corr=%s already recorded", corr
                    )
                    return True
            db.append_message(
                session_id=target_id, role=PR_GATE_OUTCOME_ROLE, content=content
            )
        finally:
            db.close()
        logger.info(
            "pr-gate-outcome: recorded result=%s for %s#%s into session %s (key=%s)",
            result, repo_text, pr_text, target_id, session_key,
        )
        return True
    except Exception:
        logger.warning(
            "pr-gate-outcome: failed to record outcome for %s", session_key, exc_info=True
        )
        return False
