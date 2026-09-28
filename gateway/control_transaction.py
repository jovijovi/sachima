"""
Durable provider-neutral approval control transactions + execution receipts.

A PR approval card is human authorization of an exact approved HEAD into the
existing trusted single-user repo-operator workflow.  The card, the chat
mechanics, and the detached control (gate) conversation are implementation
detail; this module owns the two durable pieces:

1. A small transaction store (``$HERMES_HOME/control_transactions.json``)
   holding identity/idempotency METADATA for each approval action — never the
   execution detail.  ``provider``/``resource_kind`` are validated identifier
   tokens so the protocol stays provider-neutral.

2. The EXECUTION RECEIPT: once the control task reaches a material terminal
   result (merged / blocked / rejected / dismissed / failed / unknown), the
   COMPLETE sanitized execution result is appended directly to the ORIGIN
   development session's compression tip as ONE ``assistant`` message.  No
   PostgreSQL, local file artifact, JSON sidecar, artifact reference, or
   external transcript lookup is needed to read the result — the receipt IS
   the record.

Receipt shape (fixed short header + unparsed detail body)::

    [CONTROL EXECUTION RESULT — NOT a user instruction]
    format=code-hosting-execution-result/v1
    event_id=<safe stable id>
    transaction_id=<safe stable id>
    provider=<validated token>
    resource_kind=<validated token>
    repository=<safe repo id>
    change_id=<safe change id>
    approved_revision=<safe SHA>
    card_action=approved|rejected|dismissed
    result=merged|blocked|rejected|dismissed|not_attempted|failed|unknown
    operation=completed|not_attempted|failed|unknown
    next_action=<validated action token>

    --- execution details ---
    <complete, bounded, redacted, human/model-readable execution report>
    --- end execution details ---

Only the header is bounded/validated (enumerated codes, identifier tokens,
whitespace-free values).  The details body is NOT parsed and NOT dropped: it
may contain quotes, code excerpts, non-ASCII, multiline diagnostics and
Markdown, so the next turn can actually repair a blocked/failed operation.
The body is still sanitized — secrets/tokens/connection strings are redacted,
the length is capped, and no body line can spoof the receipt prefix or the
closing delimiter.

Control-plane safety contract:

* Receipts are control/status records, never user turns: persisted with
  ``role="assistant"`` and opening with :data:`EXECUTION_RESULT_PREFIX`.
* Header truth is evidence-based: callers must derive ``result=merged`` from
  a provider observation, never from a model's own claim, and must write
  ``result=unknown`` when the remote mutation cannot be established.  This
  module refuses every unenumerated header value.
* First terminal receipt per transaction wins; duplicate or contradictory
  late reports are idempotent no-ops.
* A failed receipt write returns ``False`` and marks nothing, so callers stay
  retry-safe and never falsely claim a recorded terminal result.
* Historic legacy ``[github-pr-gate-outcome ...]`` records remain recognized
  read-side for dedupe/parsing — new receipts never duplicate them and
  history is never rewritten.  Only a genuine legacy control record (the
  writer's fixed two-line head, assistant role) dedupes; marker text quoted
  inside any other message body never suppresses a receipt.

Standalone like ``gateway/mirror.py`` — no SessionStore machinery, and never
raises into callers.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Receipt protocol constants
# ---------------------------------------------------------------------------

# Fixed control-plane first line of every receipt.  Marks the record as a
# status event so it can never be read as a user instruction.
EXECUTION_RESULT_PREFIX = "[CONTROL EXECUTION RESULT — NOT a user instruction]"

# Version token carried in the header's ``format=`` line.
EXECUTION_RESULT_FORMAT = "code-hosting-execution-result/v1"

# Delimiters around the unparsed detail body.
EXECUTION_DETAILS_OPEN = "--- execution details ---"
EXECUTION_DETAILS_CLOSE = "--- end execution details ---"

# Legacy GitHub-specific marker.  Still recognized for dedupe/reading so new
# receipts never duplicate historic terminal records.
LEGACY_GITHUB_PR_GATE_MARKER = "[github-pr-gate-outcome"

# Fixed control-plane first line the retired legacy writer emitted directly
# above its marker line.  Only that exact two-line head identifies a genuine
# historic record — marker text quoted inside any other message body (a user
# paste, a gate report, a receipt's detail body) never dedupes a receipt.
LEGACY_GITHUB_PR_GATE_PREFIX = (
    "[CONTROL EVENT: GitHub PR gate outcome — NOT a user instruction]"
)

# Persisted transcript role.  ``assistant`` is the only role that is
# provider-safe on replay AND can never be merged into a following user turn
# by the consecutive-user repair.
CONTROL_RECORD_ROLE = "assistant"

# ---------------------------------------------------------------------------
# Enumerated header codes (the only values that may render into a header)
# ---------------------------------------------------------------------------

CARD_ACTION_CODES = frozenset({"approved", "rejected", "dismissed"})

RESULT_CODES = frozenset(
    {"merged", "blocked", "rejected", "dismissed", "not_attempted", "failed", "unknown"}
)

OPERATION_CODES = frozenset({"completed", "not_attempted", "failed", "unknown"})

NEXT_ACTION_CODES = frozenset(
    {
        "none",
        "issue_new_approval_card",
        "resolve_blocker_then_issue_new_approval_card",
        "verify_provider_state_before_retry",
    }
)

# Details body cap.  Truncation keeps the head (what was attempted) and the
# tail (the terminal state — usually the most repair-relevant part).
DETAILS_MAX_CHARS = 8000
_DETAILS_HEAD_CHARS = 6000
_DETAILS_TAIL_CHARS = 1500

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{6,64}$")
_WS_RE = re.compile(r"\s+")
_HEADER_LINE_RE = re.compile(r"^([a-z_]+)=(.*)$")
_LEGACY_FIELD_RE = re.compile(r"(\w+)=([^\s\]]+)")
# C0 control characters other than newline/tab (receipts are plain text).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_REDACTED = "[REDACTED]"
# Secret shapes that must never reach the origin transcript.  Ordered:
# multi-line blocks first, then bare token shapes, then key/value and URL
# credential shapes (which see already-redacted values harmlessly).
_REDACTION_PATTERNS = (
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
            r"[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)"
        ),
        "[REDACTED PRIVATE KEY]",
    ),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{8,}\b"), _REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}\b"), _REDACTED),
    (re.compile(r"\bxox[a-z]-[A-Za-z0-9-]{8,}\b"), _REDACTED),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), _REDACTED),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b"),
        _REDACTED,
    ),
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}\b"), _REDACTED),
    (
        re.compile(r"(?i)\b(authorization\s*[:=]\s*)(?:bearer\s+|basic\s+|token\s+)?\S+"),
        r"\1" + _REDACTED,
    ),
    (
        re.compile(
            r"(?i)([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|ACCESS_KEY"
            r"|PRIVATE_KEY|CLIENT_SECRET|CREDENTIALS?)[A-Z0-9_]*\s*[=:]\s*)[^\s'\"]+"
        ),
        r"\1" + _REDACTED,
    ),
    (
        re.compile(r"\b([a-z][a-z0-9+.-]*://[^/\s:@]+):[^@\s/]+@"),
        r"\1:" + _REDACTED + "@",
    ),
)

_STORE_LOCK = threading.Lock()
_STORE_VERSION = 2
# Terminal transactions are pruned oldest-first past this bound so the store
# stays small; the origin transcripts keep the durable audit trail.
_MAX_STORED_TRANSACTIONS = 500


def compact_text(text: Any, limit: int) -> str:
    """Collapse whitespace and bound length so metadata stays compact."""
    flattened = _WS_RE.sub(" ", str(text or "")).strip()
    if len(flattened) > limit:
        flattened = flattened[: limit - 1].rstrip() + "…"
    return flattened


def _header_value(value: Any, limit: int) -> str:
    """Single-line, whitespace-free, bounded header value."""
    return _WS_RE.sub("_", str(value or "").strip())[:limit]


def _normalize_transaction_id(transaction_id: Any) -> str:
    return _header_value(transaction_id, 80)


def _normalize_revision(revision: Any) -> str:
    return compact_text(revision, 64).replace(" ", "")


# ---------------------------------------------------------------------------
# Durable store (identity/idempotency metadata only — never execution detail)
# ---------------------------------------------------------------------------


def _store_path() -> Path:
    # Resolved at call time (not import time) so profile/env overrides and
    # test sandboxes are honored.
    return get_hermes_home() / "control_transactions.json"


def _load_store_unlocked() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"version": _STORE_VERSION, "transactions": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        logger.warning("control-transaction: unreadable store %s", path, exc_info=True)
        return {"version": _STORE_VERSION, "transactions": {}}
    if not isinstance(data, dict) or not isinstance(data.get("transactions"), dict):
        return {"version": _STORE_VERSION, "transactions": {}}
    return data


def _save_store_unlocked(store: Dict[str, Any]) -> None:
    transactions = store.get("transactions", {})
    if len(transactions) > _MAX_STORED_TRANSACTIONS:
        by_age = sorted(
            transactions.items(), key=lambda item: str(item[1].get("updated_at", ""))
        )
        for transaction_id, _txn in by_age[: len(transactions) - _MAX_STORED_TRANSACTIONS]:
            transactions.pop(transaction_id, None)
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=1)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _mutate_transaction(
    transaction_id: str, mutator: Callable[[Dict[str, Any]], None]
) -> Optional[Dict[str, Any]]:
    """Load-modify-save one transaction under the store lock; returns a copy."""
    with _STORE_LOCK:
        store = _load_store_unlocked()
        txn = store["transactions"].get(transaction_id)
        if not isinstance(txn, dict):
            return None
        mutator(txn)
        txn["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _save_store_unlocked(store)
        return dict(txn)


def get_control_transaction(transaction_id: Any) -> Optional[Dict[str, Any]]:
    """Return a copy of the persisted transaction, or None.  Never raises."""
    transaction_id = _normalize_transaction_id(transaction_id)
    if not transaction_id:
        return None
    try:
        with _STORE_LOCK:
            store = _load_store_unlocked()
            txn = store["transactions"].get(transaction_id)
            return dict(txn) if isinstance(txn, dict) else None
    except Exception:
        logger.warning("control-transaction: read failed", exc_info=True)
        return None


def begin_control_transaction(
    *,
    transaction_id: Any,
    provider: str,
    resource_kind: str,
    origin_session_key: str = "",
    repo: str = "",
    change_id: Any = "",
    bound_revision: str = "",
    actor: str = "",
) -> bool:
    """Create the durable transaction for an approval action.

    Idempotent: a second begin for the same id keeps the first binding (the
    approved revision must never be silently rebound).  ``provider`` and
    ``resource_kind`` are validated identifiers — the generic protocol never
    hard-codes a provider.  Never raises.
    """
    transaction_id = _normalize_transaction_id(transaction_id)
    provider = str(provider or "").strip()
    resource_kind = str(resource_kind or "").strip()
    if not transaction_id:
        logger.debug("control-transaction: refusing empty transaction id")
        return False
    if not _IDENT_RE.match(provider) or not _IDENT_RE.match(resource_kind):
        logger.debug(
            "control-transaction: refusing invalid provider/resource_kind identifiers"
        )
        return False
    try:
        now = datetime.now().isoformat(timespec="seconds")
        record = {
            "transaction_id": transaction_id,
            "provider": provider,
            "resource_kind": resource_kind,
            "origin_session_key": str(origin_session_key or "").strip(),
            "repo": compact_text(repo, 120),
            "change_id": compact_text(change_id, 40),
            "bound_revision": _normalize_revision(bound_revision),
            "actor": compact_text(actor, 80),
            "card_action": "pending",
            "result": "none",
            "operation": "none",
            "next_action": "none",
            "integration_commit": "",
            "receipt_recorded": False,
            "created_at": now,
            "updated_at": now,
        }
        with _STORE_LOCK:
            store = _load_store_unlocked()
            if transaction_id not in store["transactions"]:
                store["transactions"][transaction_id] = record
                _save_store_unlocked(store)
        return True
    except Exception:
        logger.warning("control-transaction: begin failed", exc_info=True)
        return False


def _ensure_transaction(
    transaction_id: str,
    *,
    provider: str = "",
    resource_kind: str = "",
    origin_session_key: str = "",
    repo: str = "",
    change_id: Any = "",
    bound_revision: str = "",
    actor: str = "",
) -> Optional[Dict[str, Any]]:
    """Fetch a transaction, lazily creating it from fallback identity fields.

    Lazy creation keeps old in-flight payloads (issued before the transaction
    store existed) working fail-closed: with no stored transaction and no
    valid fallback identity, callers get None and record nothing.
    """
    txn = get_control_transaction(transaction_id)
    if txn is not None:
        return txn
    if not begin_control_transaction(
        transaction_id=transaction_id,
        provider=provider,
        resource_kind=resource_kind,
        origin_session_key=origin_session_key,
        repo=repo,
        change_id=change_id,
        bound_revision=bound_revision,
        actor=actor,
    ):
        return None
    return get_control_transaction(transaction_id)


def record_card_action(
    transaction_id: Any,
    action: str,
    *,
    actor: str = "",
    provider: str = "",
    resource_kind: str = "",
    origin_session_key: str = "",
    repo: str = "",
    change_id: Any = "",
    bound_revision: str = "",
) -> bool:
    """Record the human's card disposition (state-only; first terminal wins).

    The card action is what the receipt's ``card_action`` header field
    reports; it may never be fabricated, so only enumerated values are
    accepted.  Never raises.
    """
    transaction_id = _normalize_transaction_id(transaction_id)
    action = str(action or "").strip().lower()
    if not transaction_id or action not in CARD_ACTION_CODES:
        logger.debug("control-transaction: refusing card action %r", action)
        return False
    try:
        txn = _ensure_transaction(
            transaction_id,
            provider=provider,
            resource_kind=resource_kind,
            origin_session_key=origin_session_key,
            repo=repo,
            change_id=change_id,
            bound_revision=bound_revision,
            actor=actor,
        )
        if txn is None:
            return False
        if txn.get("card_action") in CARD_ACTION_CODES:
            if txn["card_action"] != action:
                logger.debug(
                    "control-transaction: card action already %s; ignoring late %s",
                    txn["card_action"], action,
                )
            return True

        def _set(record: Dict[str, Any]) -> None:
            record["card_action"] = action
            if actor:
                record["actor"] = compact_text(actor, 80)

        return _mutate_transaction(transaction_id, _set) is not None
    except Exception:
        logger.warning("control-transaction: card action failed", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Details sanitization (redact + bound; never parse, never drop)
# ---------------------------------------------------------------------------


def sanitize_execution_details(details: Any) -> str:
    """Sanitize a detail body: redact secrets, cap length, guard delimiters.

    The body stays complete and human/model-readable — quotes, multiline
    diagnostics, Markdown and non-ASCII survive.  Only three transformations
    are applied: secret shapes are redacted, a body line that would collide
    with the receipt prefix/delimiters is quoted, and over-long bodies are
    truncated keeping head and tail.  Never raises.
    """
    try:
        text = str(details or "")
    except Exception:
        text = ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS_RE.sub("", text)
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)

    guarded_lines = []
    for line in text.split("\n"):
        if line.strip() in (
            EXECUTION_RESULT_PREFIX,
            EXECUTION_DETAILS_OPEN,
            EXECUTION_DETAILS_CLOSE,
        ):
            line = "> " + line.strip()
        guarded_lines.append(line.rstrip())
    text = "\n".join(guarded_lines).strip("\n")

    if len(text) > DETAILS_MAX_CHARS:
        dropped = len(text) - _DETAILS_HEAD_CHARS - _DETAILS_TAIL_CHARS
        text = (
            text[:_DETAILS_HEAD_CHARS].rstrip()
            + f"\n… [execution details truncated: {dropped} characters removed] …\n"
            + text[-_DETAILS_TAIL_CHARS:].lstrip()
        )
    if not text.strip():
        return "(no execution detail was captured for this control run)"
    return text


# ---------------------------------------------------------------------------
# The execution receipt
# ---------------------------------------------------------------------------


def _sessions_index_path() -> Path:
    return get_hermes_home() / "sessions" / "sessions.json"


def _state_db_path() -> Path:
    return get_hermes_home() / "state.db"


def resolve_session_id(session_key: str) -> Optional[str]:
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


def _receipt_transaction_id(content: str) -> str:
    """Transaction id from a persisted receipt's header, or ''.

    Only the header region (before the details delimiter) is read, so body
    text can never masquerade as another transaction's receipt.
    """
    if not content.startswith(EXECUTION_RESULT_PREFIX):
        return ""
    header = content.split(EXECUTION_DETAILS_OPEN, 1)[0]
    match = re.search(r"^transaction_id=(\S+)$", header, re.M)
    return match.group(1) if match else ""


def _legacy_record_transaction_id(content: str) -> str:
    """Correlation id from a genuine historic legacy gate-outcome record, or ''.

    The retired legacy writer always emitted the fixed control-event first
    line directly followed by the bracketed marker line; only that shape —
    and only its bracketed field region — identifies a historic terminal
    record.  Marker text appearing anywhere else in a message body is
    ordinary text and never dedupes a receipt.
    """
    head = content.split("\n", 2)
    if len(head) < 2 or head[0].strip() != LEGACY_GITHUB_PR_GATE_PREFIX:
        return ""
    marker_line = head[1].strip()
    if not marker_line.startswith(LEGACY_GITHUB_PR_GATE_MARKER):
        return ""
    marker = marker_line[len(LEGACY_GITHUB_PR_GATE_MARKER):].split("]", 1)[0]
    fields = dict(_LEGACY_FIELD_RE.findall(marker))
    return fields.get("corr", "")


def record_execution_result(
    transaction_id: Any,
    *,
    result: str,
    operation: str,
    next_action: str,
    details: str,
    event_id: str = "",
    integration_commit: str = "",
    card_action: str = "",
    actor: str = "",
    provider: str = "",
    resource_kind: str = "",
    origin_session_key: str = "",
    repo: str = "",
    change_id: Any = "",
    bound_revision: str = "",
) -> bool:
    """Write the COMPLETE execution receipt to the origin session.

    Appends exactly one ``assistant`` message (fixed validated header +
    sanitized unparsed details body) to the origin session's compression tip.
    Enumerated header values only — anything else is refused fail-closed.
    ``card_action`` comes from the stored transaction when recorded there,
    else from the caller; with neither, the receipt is refused (the human
    disposition may never be fabricated).

    Idempotent per transaction: once any receipt for the transaction exists
    in the origin transcript (including its compression lineage), later —
    even contradictory — reports are no-ops; a genuine historic legacy
    ``[github-pr-gate-outcome corr=...]`` control record counts as already
    recorded (marker text quoted inside ordinary message bodies does not).
    Returns True only when the receipt exists (written now or already
    present); a failed write returns False and marks nothing, so callers stay
    retry-safe.  Never raises.
    """
    transaction_id = _normalize_transaction_id(transaction_id)
    result = str(result or "").strip().lower()
    operation = str(operation or "").strip().lower()
    next_action = str(next_action or "").strip().lower()
    if not transaction_id:
        logger.debug("control-transaction: refusing receipt without transaction id")
        return False
    if result not in RESULT_CODES:
        logger.debug("control-transaction: refusing unenumerated result %r", result)
        return False
    if operation not in OPERATION_CODES:
        logger.debug("control-transaction: refusing unenumerated operation %r", operation)
        return False
    if next_action not in NEXT_ACTION_CODES:
        logger.debug(
            "control-transaction: refusing unenumerated next_action %r", next_action
        )
        return False
    try:
        txn = _ensure_transaction(
            transaction_id,
            provider=provider,
            resource_kind=resource_kind,
            origin_session_key=origin_session_key,
            repo=repo,
            change_id=change_id,
            bound_revision=bound_revision,
            actor=actor,
        )
        if txn is None:
            return False

        session_key = str(txn.get("origin_session_key") or "").strip()
        if not session_key:
            logger.debug(
                "control-transaction: no origin session key for txn=%s; refusing receipt",
                transaction_id,
            )
            return False
        session_id = resolve_session_id(session_key)
        if not session_id:
            logger.debug(
                "control-transaction: no session found for key %s", session_key
            )
            return False

        stored_action = str(txn.get("card_action") or "").strip().lower()
        param_action = str(card_action or "").strip().lower()
        if stored_action in CARD_ACTION_CODES:
            effective_action = stored_action
        elif param_action in CARD_ACTION_CODES:
            effective_action = param_action
        else:
            logger.debug(
                "control-transaction: no recorded card action for txn=%s; "
                "refusing to fabricate the human disposition", transaction_id,
            )
            return False

        commit = str(integration_commit or "").strip().lower()
        if commit and not _COMMIT_RE.match(commit):
            logger.debug(
                "control-transaction: dropping non-hash integration commit (%d chars)",
                len(commit),
            )
            commit = ""

        event_id = _header_value(event_id, 120) or f"{transaction_id}/execution-result"

        header_lines = [
            EXECUTION_RESULT_PREFIX,
            f"format={EXECUTION_RESULT_FORMAT}",
            f"event_id={event_id}",
            f"transaction_id={transaction_id}",
            f"provider={_header_value(txn.get('provider'), 64)}",
            f"resource_kind={_header_value(txn.get('resource_kind'), 64)}",
            f"repository={_header_value(txn.get('repo'), 120)}",
            f"change_id={_header_value(txn.get('change_id'), 40)}",
            f"approved_revision={_header_value(txn.get('bound_revision'), 64)}",
            f"card_action={effective_action}",
            f"result={result}",
            f"operation={operation}",
            f"next_action={next_action}",
        ]
        content = "\n".join(
            header_lines
            + [
                "",
                EXECUTION_DETAILS_OPEN,
                sanitize_execution_details(details),
                EXECUTION_DETAILS_CLOSE,
            ]
        )

        from hermes_state import SessionDB

        db = SessionDB(db_path=_state_db_path())
        try:
            # Land on the live transcript even if the origin session was
            # compressed while the control task was pending.
            target_id = db.get_compression_tip(session_id) or session_id
            for msg in db.get_messages_as_conversation(target_id, include_ancestors=True):
                existing = msg.get("content")
                if not isinstance(existing, str):
                    continue
                if _receipt_transaction_id(existing) == transaction_id:
                    logger.debug(
                        "control-transaction: receipt for txn=%s already recorded",
                        transaction_id,
                    )
                    return True
                if (
                    msg.get("role") == CONTROL_RECORD_ROLE
                    and _legacy_record_transaction_id(existing) == transaction_id
                ):
                    logger.debug(
                        "control-transaction: legacy terminal record for corr=%s "
                        "already present; not duplicating", transaction_id,
                    )
                    return True
            db.append_message(
                session_id=target_id, role=CONTROL_RECORD_ROLE, content=content
            )
        finally:
            db.close()

        def _mark(record: Dict[str, Any]) -> None:
            record["result"] = result
            record["operation"] = operation
            record["next_action"] = next_action
            record["integration_commit"] = commit
            if record.get("card_action") not in CARD_ACTION_CODES:
                record["card_action"] = effective_action
            if actor:
                record["actor"] = compact_text(actor, 80)
            record["receipt_recorded"] = True

        try:
            _mutate_transaction(transaction_id, _mark)
        except Exception:
            # The receipt exists; metadata bookkeeping must not undo that.
            logger.warning(
                "control-transaction: receipt written but store update failed",
                exc_info=True,
            )
        logger.info(
            "control-transaction: recorded execution receipt result=%s operation=%s "
            "for %s#%s into session %s (key=%s)",
            result, operation, txn.get("repo", ""), txn.get("change_id", ""),
            target_id, session_key,
        )
        return True
    except Exception:
        logger.warning("control-transaction: execution receipt failed", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Reading (new receipts and legacy GitHub records)
# ---------------------------------------------------------------------------

_RECEIPT_HEADER_FIELDS = (
    "format", "event_id", "transaction_id", "provider", "resource_kind",
    "repository", "change_id", "approved_revision", "card_action",
    "result", "operation", "next_action",
)


def parse_control_record(content: Any) -> Optional[Dict[str, str]]:
    """Parse a persisted control record (execution receipt or legacy marker).

    Returns the validated HEADER fields only — the details body is never
    parsed; reading is for correlation/classification.  Returns None when
    ``content`` holds no control record.  Never raises.
    """
    text = str(content or "")
    try:
        if EXECUTION_RESULT_PREFIX in text:
            _prefix, _sep, rest = text.partition(EXECUTION_RESULT_PREFIX)
            header = rest.split(EXECUTION_DETAILS_OPEN, 1)[0]
            fields: Dict[str, str] = {}
            for line in header.split("\n"):
                match = _HEADER_LINE_RE.match(line.strip())
                if match:
                    fields.setdefault(match.group(1), match.group(2))
            return {name: fields.get(name, "") for name in _RECEIPT_HEADER_FIELDS}
        if LEGACY_GITHUB_PR_GATE_MARKER in text:
            _prefix, _sep, rest = text.partition(LEGACY_GITHUB_PR_GATE_MARKER)
            marker = rest.split("]", 1)[0]
            fields = dict(_LEGACY_FIELD_RE.findall(marker))
            record = {name: "" for name in _RECEIPT_HEADER_FIELDS}
            record.update(
                {
                    "format": "legacy_github_pr_gate_outcome",
                    "transaction_id": fields.get("corr", ""),
                    "provider": "github",
                    "resource_kind": "pull_request",
                    "repository": fields.get("repo", ""),
                    "change_id": fields.get("pr", "").lstrip("#"),
                    "approved_revision": fields.get("head", ""),
                    "result": fields.get("result", ""),
                }
            )
            return record
    except Exception:
        logger.debug("control-transaction: unparseable control record", exc_info=True)
    return None
