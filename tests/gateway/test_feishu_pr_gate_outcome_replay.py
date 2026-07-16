"""Regression tests: Feishu GitHub PR approval-gate outcomes must replay to the origin session.

Root cause (TOP1 emergency fault): PR approval cards persist the origin
``session_key``, but clicking a card resolves the approval in a separate
controlled gate conversation (the synthetic merge-request session).  The gate
result was stored only in that separate session, so the origin development
session never regained the terminal gate outcome in its persisted
history/context after the next turn, compression, or reload.

These tests pin the required behavior at the real card callback /
control-session boundary: when an approval gate reaches a terminal
pass/fail/reject outcome, a compact sanitized structured outcome record is
appended to the ORIGIN session identified by the card correlation — visible in
the next model context, persisted across reload, idempotent, and never written
for stale card clicks.
"""

import asyncio
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the repo root is importable
# ---------------------------------------------------------------------------
_repo = str(Path(__file__).resolve().parents[2])
if _repo not in sys.path:
    sys.path.insert(0, _repo)


# ---------------------------------------------------------------------------
# Minimal Feishu mock so FeishuAdapter can be imported without lark-oapi
# ---------------------------------------------------------------------------
def _module_available(name: str) -> bool:
    """True when a real (or already-stubbed) module can be imported."""
    if name in sys.modules:
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        # find_spec raises ValueError for stub modules injected by sibling
        # test files (their __spec__ is a MagicMock/None).
        return False


def _ensure_feishu_mocks():
    """Provide stubs for lark-oapi / aiohttp.web so the import succeeds."""
    if not _module_available("lark_oapi"):
        mod = MagicMock()
        for name in (
            "lark_oapi", "lark_oapi.api.im.v1",
            "lark_oapi.event", "lark_oapi.event.callback_type",
        ):
            sys.modules.setdefault(name, mod)
    if not _module_available("aiohttp"):
        aio = MagicMock()
        sys.modules.setdefault("aiohttp", aio)
        sys.modules.setdefault("aiohttp.web", aio.web)


_ensure_feishu_mocks()

from gateway.config import PlatformConfig
from gateway.platforms.base import MessageEvent, MessageType, ProcessingOutcome
from gateway.platforms.feishu import FeishuAdapter
from gateway.session import build_session_key


# ---------------------------------------------------------------------------
# Contract constants (the implementation must match these)
# ---------------------------------------------------------------------------

# Stable machine-readable marker opening every persisted gate-outcome record.
MARKER = "[github-pr-gate-outcome"

# Fixed control-plane prefix: the record must never read as a user instruction.
CONTROL_PREFIX = "[CONTROL EVENT: GitHub PR gate outcome — NOT a user instruction]"

# Mandatory no-merge disclaimer carried by EVERY terminal outcome.
NO_MERGE_TEXT = "No merge status is implied"

ORIGIN_SESSION_KEY = "agent:main:feishu:group:oc_origin:ou_dev"
ORIGIN_SESSION_ID = "sess_origin"

REPO = "NousResearch/hermes-agent"
PR_NUMBER = "42"
HEAD_SHA = "abc123def4567890abc123def4567890abc123de"
CARD_MESSAGE_ID = "om_card_7"
CALLBACK_TOKEN = "tok_secret_callback_9x7"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hermes_home() -> Path:
    return Path(os.environ["HERMES_HOME"])


def _state_db_path() -> Path:
    return _hermes_home() / "state.db"


def _sessions_index_path() -> Path:
    sessions_dir = _hermes_home() / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir / "sessions.json"


def _register_session(session_key: str, session_id: str) -> None:
    """Add a session_key -> session_id mapping to the sessions.json index."""
    index_path = _sessions_index_path()
    data = {}
    if index_path.exists():
        data = json.loads(index_path.read_text(encoding="utf-8"))
    data[session_key] = {
        "session_id": session_id,
        "origin": {"platform": "feishu", "chat_id": "oc_origin", "user_id": "ou_dev"},
        "updated_at": "2026-07-16T00:00:00",
    }
    index_path.write_text(json.dumps(data), encoding="utf-8")


def _seed_session_db(session_id: str, messages=None, parent_session_id=None):
    """Create a session row (and optional messages) in the tmp state.db."""
    from hermes_state import SessionDB

    db = SessionDB(db_path=_state_db_path())
    try:
        db.create_session(session_id, source="gateway", parent_session_id=parent_session_id)
        for role, content in messages or []:
            db.append_message(session_id=session_id, role=role, content=content)
    finally:
        db.close()


def _seed_origin_session():
    _register_session(ORIGIN_SESSION_KEY, ORIGIN_SESSION_ID)
    _seed_session_db(
        ORIGIN_SESSION_ID,
        messages=[
            ("user", "please open the PR and send me an approval card"),
            ("assistant", "PR #42 opened; approval card sent."),
        ],
    )


def _load_transcript(session_id: str):
    """Read a session transcript through a FRESH SessionDB connection."""
    from hermes_state import SessionDB

    db = SessionDB(db_path=_state_db_path())
    try:
        return db.get_messages_as_conversation(session_id)
    finally:
        db.close()


def _marker_rows(session_id: str):
    return [
        msg for msg in _load_transcript(session_id)
        if MARKER in str(msg.get("content") or "")
    ]


def _all_marker_rows():
    """Count gate-outcome rows across the whole messages table."""
    conn = sqlite3.connect(_state_db_path())
    try:
        rows = conn.execute("SELECT session_id, content FROM messages").fetchall()
    finally:
        conn.close()
    return [(sid, content) for sid, content in rows if MARKER in str(content or "")]


def _make_adapter() -> FeishuAdapter:
    config = PlatformConfig(enabled=True)
    adapter = FeishuAdapter(config)
    adapter._client = MagicMock()
    return adapter


def _seed_card_state(adapter: FeishuAdapter, approval_id: int = 7, **overrides):
    state = {
        "chat_id": "oc_gate",
        "message_id": CARD_MESSAGE_ID,
        "repo": REPO,
        "pr_number": PR_NUMBER,
        "title": "Fix the flux capacitor",
        "pr_url": f"https://github.com/{REPO}/pull/{PR_NUMBER}",
        "author": "octocat",
        "head_sha": HEAD_SHA,
        "base_ref": "main",
        "head_ref": "fix/flux-capacitor",
        "locale": "en",
        "session_key": ORIGIN_SESSION_KEY,
    }
    state.update(overrides)
    adapter._github_pr_approval_state[approval_id] = state
    key = (state["repo"].strip().lower(), str(state["pr_number"]).strip())
    adapter._github_pr_latest_approval_id_by_pr[key] = approval_id
    return state


def _make_gate_event(adapter: FeishuAdapter, state: dict, action: str = "approve") -> MessageEvent:
    """Build the synthetic gate MessageEvent the way the card callback does."""
    source = adapter.build_source(
        chat_id=state["chat_id"],
        chat_name="Gate Chat",
        chat_type="group",
        user_id="ou_admin",
        user_name="Dev A",
        thread_id=None,
    )
    return MessageEvent(
        text=f"批准合并 PR #{state['pr_number']}（Feishu 按钮审批）",
        message_type=MessageType.TEXT,
        source=source,
        raw_message={"github_pr_approval": dict(state), "action": action, "token": CALLBACK_TOKEN},
        message_id=state.get("message_id") or None,
    )


async def _click(adapter: FeishuAdapter, approval_id: int, action: str, **kwargs):
    await adapter._resolve_github_pr_approval(
        approval_id,
        action,
        kwargs.pop("user_name", "Dev A"),
        open_id=kwargs.pop("open_id", "ou_admin"),
        chat_id=kwargs.pop("chat_id", "oc_gate"),
        token=kwargs.pop("token", CALLBACK_TOKEN),
    )


@pytest.fixture(autouse=True)
def _quiet_feishu_reactions(monkeypatch):
    """Keep reaction side effects out of the on_processing_complete tests."""
    monkeypatch.setenv("FEISHU_REACTIONS", "false")


# ===========================================================================
# Terminal reject / ignore outcomes recorded at the callback boundary
# ===========================================================================

class TestRejectIgnoreOutcomeReplay:

    @pytest.mark.asyncio
    async def test_reject_click_records_terminal_outcome_in_origin_session(self):
        _seed_origin_session()
        adapter = _make_adapter()
        _seed_card_state(adapter, approval_id=7)

        await _click(adapter, 7, "reject")

        rows = _marker_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1, (
            "terminal reject outcome must be appended to the ORIGIN session "
            "identified by the card's persisted session_key"
        )
        content = str(rows[0]["content"])
        assert "result=reject" in content
        assert REPO in content
        assert f"pr=#{PR_NUMBER}" in content
        assert f"head={HEAD_SHA[:12]}" in content
        assert "Dev A" in content
        # Sanitized: no raw callback payload material.
        assert CALLBACK_TOKEN not in content
        # Control-plane record: replayable on the next turn, but NEVER as a
        # user turn (a user-role row could read as an instruction and merge
        # with the next real user message).
        assert rows[0]["role"] == "assistant"
        assert content.startswith(CONTROL_PREFIX)

    @pytest.mark.asyncio
    async def test_ignore_click_records_terminal_outcome_in_origin_session(self):
        _seed_origin_session()
        adapter = _make_adapter()
        _seed_card_state(adapter, approval_id=7)

        await _click(adapter, 7, "ignore")

        rows = _marker_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        content = str(rows[0]["content"])
        assert "result=ignore" in content
        assert "result=pass" not in content

    @pytest.mark.asyncio
    async def test_missing_origin_session_key_is_a_noop(self):
        _seed_origin_session()
        adapter = _make_adapter()
        _seed_card_state(adapter, approval_id=7, session_key="")

        await _click(adapter, 7, "reject")

        assert _all_marker_rows() == []


# ===========================================================================
# Approve path: gate conversation terminal outcome replayed to origin session
# ===========================================================================

class TestApproveGateOutcomeReplay:

    @pytest.mark.asyncio
    async def test_approve_gate_completion_records_pass_outcome_with_gate_result(self):
        _seed_origin_session()
        adapter = _make_adapter()
        _seed_card_state(adapter, approval_id=7)

        with (
            patch.object(
                adapter,
                "_resolve_sender_profile",
                new_callable=AsyncMock,
                return_value={"user_id": "ou_admin", "user_name": "Dev A", "user_id_alt": None},
            ),
            patch.object(
                adapter, "get_chat_info", new_callable=AsyncMock,
                return_value={"name": "Gate Chat"},
            ),
            patch.object(
                adapter, "_handle_message_with_guards", new_callable=AsyncMock,
            ) as mock_handle,
        ):
            await _click(adapter, 7, "approve")

        mock_handle.assert_awaited_once()
        gate_event = mock_handle.call_args[0][0]
        # Precondition (already true today): the synthetic gate event carries
        # the origin-session correlation.
        assert gate_event.raw_message["github_pr_approval"]["session_key"] == ORIGIN_SESSION_KEY

        # The controlled gate conversation runs in its own session.  Register
        # it with an assistant reply that CLAIMS a merge — the record must not
        # import that claim (arbitrary gate assistant text stays out of the
        # origin model context).
        gate_session_key = build_session_key(
            gate_event.source,
            group_sessions_per_user=adapter.config.extra.get("group_sessions_per_user", True),
            thread_sessions_per_user=adapter.config.extra.get("thread_sessions_per_user", False),
        )
        assert gate_session_key != ORIGIN_SESSION_KEY, "test setup must model the split-session fault"
        _register_session(gate_session_key, "sess_gate")
        _seed_session_db(
            "sess_gate",
            messages=[
                ("user", gate_event.text),
                ("assistant", "SENTINEL_GATE_TEXT: PR #42 merged at abc123def456."),
            ],
        )

        # Terminal completion of the gate turn at the dispatch boundary.
        await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)

        rows = _marker_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1, (
            "gate completion must append a structured outcome record to the "
            "origin session so the next model context regains the gate outcome"
        )
        content = str(rows[0]["content"])
        assert "result=pass" in content
        assert REPO in content
        assert f"pr=#{PR_NUMBER}" in content
        assert f"head={HEAD_SHA[:12]}" in content
        # ``pass`` = the gate run reached a terminal delivery state, nothing
        # more: no merge claim, and no copied gate assistant text.
        assert "SENTINEL_GATE_TEXT" not in content
        assert "merged" not in content.lower()
        assert NO_MERGE_TEXT in content
        assert CALLBACK_TOKEN not in content
        # The record targets the origin session only.
        assert _marker_rows("sess_gate") == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "outcome",
        [ProcessingOutcome.FAILURE, ProcessingOutcome.CANCELLED],
    )
    async def test_gate_failure_records_fail_outcome_not_success(self, outcome):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        gate_event = _make_gate_event(adapter, state)

        await adapter.on_processing_complete(gate_event, outcome)

        rows = _marker_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        content = str(rows[0]["content"])
        assert "result=fail" in content
        assert "result=pass" not in content
        assert f"head={HEAD_SHA[:12]}" in content
        # Fail is explicit no-merge: incomplete run + mandatory disclaimer.
        assert "did not complete" in content
        assert NO_MERGE_TEXT in content

    @pytest.mark.asyncio
    async def test_terminal_outcome_is_idempotent(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        gate_event = _make_gate_event(adapter, state)

        await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)
        await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)
        # A late duplicate with a different classification must not overwrite
        # or duplicate the first terminal record.
        await adapter.on_processing_complete(gate_event, ProcessingOutcome.FAILURE)

        rows = _marker_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        assert "result=pass" in str(rows[0]["content"])

    @pytest.mark.asyncio
    async def test_non_gate_events_write_nothing(self):
        _seed_origin_session()
        adapter = _make_adapter()
        source = adapter.build_source(chat_id="oc_gate", chat_type="group", user_id="ou_admin")
        plain_event = MessageEvent(text="hello", source=source, raw_message={"foo": "bar"})

        await adapter.on_processing_complete(plain_event, ProcessingOutcome.SUCCESS)

        assert _all_marker_rows() == []


# ===========================================================================
# Stale card clicks must not write a misleading outcome
# ===========================================================================

class TestStaleCardSafety:

    @pytest.mark.asyncio
    async def test_stale_card_click_writes_no_outcome(self):
        _seed_origin_session()
        adapter = _make_adapter()
        # Old card (approval 1) superseded by a newer card (approval 2) for
        # the same repo/PR — clicking the old card must be dropped entirely.
        _seed_card_state(adapter, approval_id=1, head_sha="0ldhead111" + "0" * 30)
        _seed_card_state(adapter, approval_id=2)

        with patch.object(
            adapter, "_handle_message_with_guards", new_callable=AsyncMock,
        ) as mock_handle:
            await _click(adapter, 1, "approve")

        mock_handle.assert_not_awaited()
        assert _all_marker_rows() == []


# ===========================================================================
# Persistence boundaries: reload, model-context replay, compression tip
# ===========================================================================

class TestPersistenceBoundaries:

    @pytest.mark.asyncio
    async def test_outcome_survives_reload_and_is_model_visible(self):
        _seed_origin_session()
        adapter = _make_adapter()
        _seed_card_state(adapter, approval_id=7)

        await _click(adapter, 7, "reject")

        # Reload through a fresh DB connection (as a gateway restart would).
        history = _load_transcript(ORIGIN_SESSION_ID)
        assert any(MARKER in str(m.get("content") or "") for m in history)

        # And through the gateway replay builder that produces the next model
        # context: the outcome record must survive as a replayed turn.
        from gateway.run import _build_gateway_agent_history

        agent_history, _observed = _build_gateway_agent_history(history)
        replayed = "\n".join(
            str(m.get("content") or "") for m in agent_history
        )
        assert MARKER in replayed
        assert "result=reject" in replayed
        # The replayed record must be a control/status entry, never a user turn.
        for entry in agent_history:
            if MARKER in str(entry.get("content") or ""):
                assert entry.get("role") != "user"

    @pytest.mark.asyncio
    async def test_outcome_lands_on_compression_tip_of_origin_session(self):
        from hermes_state import SessionDB

        # Origin session was compressed while the gate was pending: the index
        # still maps the session_key at the parent, but the live transcript is
        # the compression-continuation child.
        _register_session(ORIGIN_SESSION_KEY, "sess_parent")
        _seed_session_db("sess_parent", messages=[("user", "old context")])
        db = SessionDB(db_path=_state_db_path())
        try:
            db.end_session("sess_parent", "compression")
        finally:
            db.close()
        _seed_session_db(
            "sess_child",
            messages=[("assistant", "[compressed summary of earlier context]")],
            parent_session_id="sess_parent",
        )

        adapter = _make_adapter()
        _seed_card_state(adapter, approval_id=7)

        await _click(adapter, 7, "reject")

        assert _marker_rows("sess_child"), (
            "outcome must land on the compression-continuation tip so it is "
            "part of the live transcript after compression"
        )
        assert _marker_rows("sess_parent") == []


# ===========================================================================
# Control-plane safety: never a user turn, never a merge claim, never
# arbitrary gate text (independent review blockers)
# ===========================================================================

class TestControlPlaneSafety:

    @pytest.mark.asyncio
    async def test_outcome_is_control_event_not_user_turn(self):
        _seed_origin_session()
        adapter = _make_adapter()
        _seed_card_state(adapter, approval_id=7)

        await _click(adapter, 7, "reject")

        rows = _marker_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        assert rows[0]["role"] == "assistant"
        content = str(rows[0]["content"])
        assert content.startswith(CONTROL_PREFIX)
        assert "NOT a user instruction" in content

    @pytest.mark.asyncio
    async def test_outcome_cannot_merge_with_following_user_turn(self):
        _seed_origin_session()
        adapter = _make_adapter()
        _seed_card_state(adapter, approval_id=7)

        await _click(adapter, 7, "reject")

        # A real user message lands right after the control record.
        from hermes_state import SessionDB

        db = SessionDB(db_path=_state_db_path())
        try:
            db.append_message(
                session_id=ORIGIN_SESSION_ID, role="user",
                content="please deploy the release now",
            )
        finally:
            db.close()

        from gateway.run import _build_gateway_agent_history

        agent_history, _observed = _build_gateway_agent_history(
            _load_transcript(ORIGIN_SESSION_ID)
        )
        control_entries = [
            m for m in agent_history if MARKER in str(m.get("content") or "")
        ]
        assert len(control_entries) == 1
        assert control_entries[0].get("role") == "assistant"

        # Push the replayed history through the pre-API repair pass that
        # merges consecutive user turns — the control record must survive it
        # without being folded into (or absorbing) any user message.
        from agent.agent_runtime_helpers import repair_message_sequence

        repair_message_sequence(None, agent_history)

        # The control record and the user's message stay separate turns:
        # no replayed user entry may contain the control record.
        for entry in agent_history:
            if entry.get("role") == "user":
                entry_text = str(entry.get("content") or "")
                assert MARKER not in entry_text
                assert CONTROL_PREFIX not in entry_text
        # And the user's own text is still replayed as a user turn.
        assert any(
            entry.get("role") == "user"
            and "please deploy the release now" in str(entry.get("content") or "")
            for entry in agent_history
        )

    @pytest.mark.asyncio
    async def test_pass_with_no_gate_detail_never_claims_merge(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        gate_event = _make_gate_event(adapter, state)

        # No gate session registered at all — empty detail must not turn
        # into an implied success.
        await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)

        rows = _marker_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        content = str(rows[0]["content"])
        assert "result=pass" in content
        assert "merged" not in content.lower()
        assert "approved and completed" not in content.lower()
        assert NO_MERGE_TEXT in content
        # ``pass`` speaks only about the gate run's terminal delivery state.
        assert "terminal" in content.lower()

    @pytest.mark.asyncio
    async def test_every_terminal_outcome_carries_no_merge_disclaimer(self):
        _seed_origin_session()
        adapter = _make_adapter()

        for approval_id, action in ((11, "reject"), (12, "ignore")):
            _seed_card_state(
                adapter, approval_id=approval_id,
                pr_number=str(approval_id), message_id=f"om_card_{approval_id}",
            )
            await _click(adapter, approval_id, action)

        state = _seed_card_state(
            adapter, approval_id=13, pr_number="13", message_id="om_card_13",
        )
        await adapter.on_processing_complete(
            _make_gate_event(adapter, state), ProcessingOutcome.FAILURE
        )

        rows = _marker_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 3
        for row in rows:
            content = str(row["content"])
            assert NO_MERGE_TEXT in content
            assert row["role"] == "assistant"
        reject_content = next(c for c in map(str, (r["content"] for r in rows)) if "result=reject" in c)
        ignore_content = next(c for c in map(str, (r["content"] for r in rows)) if "result=ignore" in c)
        fail_content = next(c for c in map(str, (r["content"] for r in rows)) if "result=fail" in c)
        assert "no merge request was routed" in reject_content
        assert "no merge request was routed" in ignore_content
        assert "did not complete" in fail_content

    def test_recorder_only_renders_source_controlled_detail_codes(self):
        _seed_origin_session()
        from gateway.pr_gate_outcome import record_pr_gate_outcome

        ok = record_pr_gate_outcome(
            origin_session_key=ORIGIN_SESSION_KEY,
            result="pass",
            repo=REPO,
            pr_number=PR_NUMBER,
            head_sha=HEAD_SHA,
            correlation_id="om_card_7",
            actor="Dev A",
            # Arbitrary text (e.g. a raw gate excerpt or payload) must never
            # reach the persisted record — only fixed detail codes render.
            detail_code="RAW_GATE_TEXT: PR merged! token=tok_secret_callback_9x7",
        )
        assert ok is True

        rows = _marker_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        content = str(rows[0]["content"])
        assert "RAW_GATE_TEXT" not in content
        assert "tok_secret_callback_9x7" not in content
        assert "merged" not in content.lower()
        assert NO_MERGE_TEXT in content
