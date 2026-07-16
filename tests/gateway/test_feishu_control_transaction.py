"""Feishu GitHub PR approval flow writes full execution receipts to the origin session.

The PR approval card is human authorization of an exact approved HEAD into the
existing trusted single-user repo-operator workflow.  The separate control
(gate) conversation may execute after the origin chat turn ended; when it
reaches a material terminal result, the origin development session must
receive ONE assistant message carrying the COMPLETE sanitized execution
result — fixed validated header plus unparsed detail body (the receipt
contract itself is pinned in tests/gateway/test_control_transaction.py).

These tests pin the adapter boundary:

* sending a card begins the durable control transaction;
* approve records the human card action and routes the trusted repo-operator
  gate turn — with NO model-facing self-report tool in the routing prompt;
* reject/dismiss immediately write complete not-attempted receipts;
* gate-turn completion composes the receipt from the gate run's execution
  report plus a fresh provider observation: merged / blocked / failed /
  unknown are provider-established, never model-asserted — including when
  the gate turn ran inside the origin session itself (the freeform gate
  response there never substitutes for the structured receipt);
* duplicate callbacks stay idempotent, stale cards write nothing, historic
  legacy ``[github-pr-gate-outcome ...]`` records are never duplicated, and
  old in-flight card payloads (no transaction id) still produce receipts.
"""

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
    if name in sys.modules:
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _ensure_feishu_mocks():
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
from gateway.platforms.base import MessageEvent, MessageType, ProcessingOutcome, SendResult
from gateway.platforms.feishu import FeishuAdapter
from gateway.session import build_session_key


RECEIPT_PREFIX = "[CONTROL EXECUTION RESULT — NOT a user instruction]"
DETAILS_OPEN = "--- execution details ---"
DETAILS_CLOSE = "--- end execution details ---"
LEGACY_MARKER = "[github-pr-gate-outcome"

ORIGIN_SESSION_KEY = "agent:main:feishu:group:oc_origin:ou_dev"
ORIGIN_SESSION_ID = "sess_origin"

REPO = "NousResearch/hermes-agent"
PR_NUMBER = "42"
HEAD_SHA = "abc123def4567890abc123def4567890abc123de"
MERGE_COMMIT = "9997770001112223334445556667778889990001"
CARD_MESSAGE_ID = "om_card_7"
CALLBACK_TOKEN = "tok_secret_callback_9x7"

OBSERVED_MERGED = {
    "observed": True, "merged": True, "state": "closed",
    "merge_commit": MERGE_COMMIT, "head_sha": HEAD_SHA, "mergeable_state": "",
}
OBSERVED_OPEN = {
    "observed": True, "merged": False, "state": "open",
    "merge_commit": "", "head_sha": HEAD_SHA, "mergeable_state": "blocked",
}
UNOBSERVED = {"observed": False, "reason": "provider api unreachable"}


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
    from hermes_state import SessionDB

    db = SessionDB(db_path=_state_db_path())
    try:
        return db.get_messages_as_conversation(session_id)
    finally:
        db.close()


def _append_origin_messages(*messages):
    from hermes_state import SessionDB

    db = SessionDB(db_path=_state_db_path())
    try:
        for role, content in messages:
            db.append_message(session_id=ORIGIN_SESSION_ID, role=role, content=content)
    finally:
        db.close()


def _receipt_rows(session_id: str):
    return [
        msg for msg in _load_transcript(session_id)
        if RECEIPT_PREFIX in str(msg.get("content") or "")
    ]


def _all_receipt_rows():
    conn = sqlite3.connect(_state_db_path())
    try:
        rows = conn.execute("SELECT session_id, content FROM messages").fetchall()
    finally:
        conn.close()
    return [(sid, content) for sid, content in rows if RECEIPT_PREFIX in str(content or "")]


def _header_region(content: str) -> str:
    return content.split(DETAILS_OPEN, 1)[0]


def _body_region(content: str) -> str:
    after = content.split(DETAILS_OPEN, 1)[1]
    return after.rsplit(DETAILS_CLOSE, 1)[0]


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
        "control_transaction_id": CARD_MESSAGE_ID,
    }
    state.update(overrides)
    adapter._github_pr_approval_state[approval_id] = state
    key = (state["repo"].strip().lower(), str(state["pr_number"]).strip())
    adapter._github_pr_latest_approval_id_by_pr[key] = approval_id
    return state


def _begin_card_transaction(state):
    from gateway.control_transaction import begin_control_transaction

    assert begin_control_transaction(
        transaction_id=state["control_transaction_id"],
        provider="github",
        resource_kind="pull_request",
        origin_session_key=state["session_key"],
        repo=state["repo"],
        change_id=state["pr_number"],
        bound_revision=state["head_sha"],
        actor=state.get("author", ""),
    ) is True


def _make_gate_event(
    adapter: FeishuAdapter, state: dict, action: str = "approve", user_id: str = "ou_admin",
) -> MessageEvent:
    source = adapter.build_source(
        chat_id=state["chat_id"],
        chat_name="Gate Chat",
        chat_type="group",
        user_id=user_id,
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


def _gate_session_key(adapter: FeishuAdapter, gate_event: MessageEvent) -> str:
    return build_session_key(
        gate_event.source,
        group_sessions_per_user=adapter.config.extra.get("group_sessions_per_user", True),
        thread_sessions_per_user=adapter.config.extra.get("thread_sessions_per_user", False),
    )


def _seed_gate_session(adapter: FeishuAdapter, gate_event: MessageEvent, report: str):
    gate_key = _gate_session_key(adapter, gate_event)
    assert gate_key != ORIGIN_SESSION_KEY, "test setup must model the split-session flow"
    _register_session(gate_key, "sess_gate")
    _seed_session_db(
        "sess_gate",
        messages=[("user", gate_event.text), ("assistant", report)],
    )
    return gate_key


async def _click(adapter: FeishuAdapter, approval_id: int, action: str, **kwargs):
    await adapter._resolve_github_pr_approval(
        approval_id,
        action,
        kwargs.pop("user_name", "Dev A"),
        open_id=kwargs.pop("open_id", "ou_admin"),
        chat_id=kwargs.pop("chat_id", "oc_gate"),
        token=kwargs.pop("token", CALLBACK_TOKEN),
    )


async def _approve_click(adapter: FeishuAdapter, approval_id: int = 7):
    """Approve click with the sender/chat lookups mocked; returns the gate event."""
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
        await _click(adapter, approval_id, "approve")
    mock_handle.assert_awaited_once()
    return mock_handle.call_args[0][0]


def _observe(result):
    return patch("gateway.platforms.feishu._observe_github_pr_state", return_value=result)


@pytest.fixture(autouse=True)
def _quiet_feishu_reactions(monkeypatch):
    monkeypatch.setenv("FEISHU_REACTIONS", "false")


# ===========================================================================
# Card send begins the durable transaction
# ===========================================================================

class TestCardSendBeginsTransaction:

    @pytest.mark.asyncio
    async def test_card_send_begins_durable_transaction(self):
        from gateway.control_transaction import get_control_transaction

        _seed_origin_session()
        adapter = _make_adapter()

        with (
            patch.object(
                adapter, "_feishu_send_with_retry", new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch.object(
                adapter, "_finalize_send_result",
                return_value=SendResult(success=True, message_id=CARD_MESSAGE_ID),
            ),
        ):
            result = await adapter.send_github_pr_approval_card(
                chat_id="oc_gate",
                repo=REPO,
                pr_number=PR_NUMBER,
                title="Fix the flux capacitor",
                head_sha=HEAD_SHA,
                session_key=ORIGIN_SESSION_KEY,
            )

        assert result.success is True
        txn = get_control_transaction(CARD_MESSAGE_ID)
        assert txn is not None
        assert txn["provider"] == "github"
        assert txn["resource_kind"] == "pull_request"
        assert txn["origin_session_key"] == ORIGIN_SESSION_KEY
        assert txn["repo"] == REPO
        assert txn["change_id"] == PR_NUMBER
        assert txn["bound_revision"] == HEAD_SHA

        states = list(adapter._github_pr_approval_state.values())
        assert states and states[0].get("control_transaction_id") == CARD_MESSAGE_ID


# ===========================================================================
# Approve click: human card action recorded, trusted gate turn routed
# ===========================================================================

class TestApproveClick:

    @pytest.mark.asyncio
    async def test_approve_click_records_card_action_and_routes_gate_turn(self):
        from gateway.control_transaction import get_control_transaction

        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        _begin_card_transaction(state)

        gate_event = await _approve_click(adapter, 7)

        assert get_control_transaction(CARD_MESSAGE_ID)["card_action"] == "approved"
        # No receipt yet: the material terminal result hasn't been reached.
        assert _receipt_rows(ORIGIN_SESSION_ID) == []

        carried = gate_event.raw_message["github_pr_approval"]
        assert carried["session_key"] == ORIGIN_SESSION_KEY
        assert carried["control_transaction_id"] == CARD_MESSAGE_ID
        # The gate turn is the existing trusted repo-operator workflow: it
        # fresh-checks and merges with its normal tooling.  There is NO
        # model-facing self-report tool through which it could assert the
        # operation result as canonical truth.
        assert "github_pr_operation_report" not in gate_event.text
        assert "fresh-check" in gate_event.text


# ===========================================================================
# Reject / dismiss: complete not-attempted receipts at the callback boundary
# ===========================================================================

class TestRejectDismissReceipts:

    @pytest.mark.asyncio
    async def test_reject_click_writes_complete_not_attempted_receipt(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        _begin_card_transaction(state)

        await _click(adapter, 7, "reject")

        rows = _receipt_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1, (
            "terminal reject must append the complete execution receipt to "
            "the ORIGIN session identified by the card's persisted session_key"
        )
        assert rows[0]["role"] == "assistant"
        content = str(rows[0]["content"])
        assert content.startswith(RECEIPT_PREFIX)
        header = _header_region(content)
        assert f"transaction_id={CARD_MESSAGE_ID}" in header
        assert "card_action=rejected" in header
        assert "result=rejected" in header
        assert "operation=not_attempted" in header
        body = _body_region(content)
        assert "Dev A" in body
        assert "not attempted" in body
        assert CALLBACK_TOKEN not in content

    @pytest.mark.asyncio
    async def test_ignore_click_writes_dismissed_receipt_requiring_new_card(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        _begin_card_transaction(state)

        await _click(adapter, 7, "ignore")

        rows = _receipt_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        content = str(rows[0]["content"])
        header = _header_region(content)
        assert "card_action=dismissed" in header
        assert "result=dismissed" in header
        assert "operation=not_attempted" in header
        body = _body_region(content)
        assert "not attempted" in body
        assert "new approval card" in body

    @pytest.mark.asyncio
    async def test_missing_origin_session_key_writes_no_receipt(self):
        _seed_origin_session()
        adapter = _make_adapter()
        _seed_card_state(adapter, approval_id=7, session_key="")

        await _click(adapter, 7, "reject")

        assert _all_receipt_rows() == []


# ===========================================================================
# Approve + gate completion: receipt composed from gate report + provider read
# ===========================================================================

GATE_REPORT_MERGED = (
    "Fresh-check 完成：head SHA matched the approved revision.\n"
    '"CI": all required checks green.\n'
    f"Ran `gh pr merge {PR_NUMBER} --squash` — merged as {MERGE_COMMIT[:12]}.\n"
    "GITHUB_TOKEN=ghp_AbCdEfGh123456789012345678901234 (from env)\n"
    "SENTINEL_GATE_REPORT_MERGED ✅"
)

GATE_REPORT_BLOCKED = (
    "Fresh-check found blockers; merge was NOT attempted:\n"
    "- required check `build (3.12)` failing (owner: @jovijovi)\n"
    "- branch protection requires 2 approving reviews, has 1\n"
    "SENTINEL_GATE_REPORT_BLOCKED"
)


class TestGateCompletionReceipts:

    @pytest.mark.asyncio
    async def test_merged_receipt_carries_complete_report_and_provider_commit(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        _begin_card_transaction(state)

        gate_event = await _approve_click(adapter, 7)
        _seed_gate_session(adapter, gate_event, GATE_REPORT_MERGED)

        with _observe(OBSERVED_MERGED):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)

        rows = _receipt_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        assert rows[0]["role"] == "assistant"
        content = str(rows[0]["content"])
        header = _header_region(content)
        assert "card_action=approved" in header
        assert "result=merged" in header
        assert "operation=completed" in header
        assert "next_action=none" in header
        assert f"approved_revision={HEAD_SHA}" in header

        body = _body_region(content)
        # COMPLETE execution detail: the gate run's report (quotes, non-ASCII
        # and all) plus the provider-observed integration commit.
        assert "SENTINEL_GATE_REPORT_MERGED ✅" in body
        assert "Fresh-check 完成：head SHA matched the approved revision." in body
        assert '"CI": all required checks green.' in body
        assert MERGE_COMMIT in body
        # ... but redacted and free of raw callback material.
        assert "ghp_AbCdEfGh123456789012345678901234" not in content
        assert CALLBACK_TOKEN not in content

        # The receipt targets the origin session only.
        assert _receipt_rows("sess_gate") == []

    @pytest.mark.asyncio
    async def test_blocked_receipt_carries_actionable_blockers(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        _begin_card_transaction(state)

        gate_event = await _approve_click(adapter, 7)
        _seed_gate_session(adapter, gate_event, GATE_REPORT_BLOCKED)

        with _observe(OBSERVED_OPEN):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)

        rows = _receipt_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        content = str(rows[0]["content"])
        header = _header_region(content)
        assert "result=blocked" in header
        assert "operation=not_attempted" in header
        assert "next_action=resolve_blocker_then_issue_new_approval_card" in header
        body = _body_region(content)
        assert "required check `build (3.12)` failing (owner: @jovijovi)" in body
        assert "branch protection requires 2 approving reviews, has 1" in body

    @pytest.mark.asyncio
    async def test_ambiguous_provider_state_yields_unknown_receipt(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        _begin_card_transaction(state)

        gate_event = await _approve_click(adapter, 7)
        _seed_gate_session(
            adapter, gate_event,
            "I merged the PR successfully!",  # model claim without provider proof
        )

        with _observe(UNOBSERVED):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)

        rows = _receipt_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        content = str(rows[0]["content"])
        header = _header_region(content)
        # The gate model's own success claim must NOT become the canonical
        # result: without a provider observation the result is unknown.
        assert "result=unknown" in header
        assert "operation=unknown" in header
        assert "next_action=verify_provider_state_before_retry" in header
        assert "fresh provider read" in _body_region(content)

    @pytest.mark.asyncio
    async def test_gate_run_failure_with_no_mutation_yields_failed_receipt(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        _begin_card_transaction(state)

        gate_event = await _approve_click(adapter, 7)

        with _observe(OBSERVED_OPEN):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.FAILURE)

        rows = _receipt_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        content = str(rows[0]["content"])
        header = _header_region(content)
        assert "result=failed" in header
        assert "result=merged" not in header

    @pytest.mark.asyncio
    async def test_gate_run_crash_after_remote_merge_reports_merged(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        _begin_card_transaction(state)

        gate_event = await _approve_click(adapter, 7)

        # The run crashed AFTER the remote mutation happened: the provider
        # observation, not the delivery outcome, is the truth source.
        with _observe(OBSERVED_MERGED):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.FAILURE)

        rows = _receipt_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        header = _header_region(str(rows[0]["content"]))
        assert "result=merged" in header
        assert "operation=completed" in header

    @pytest.mark.asyncio
    async def test_duplicate_completion_callbacks_write_one_receipt(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        _begin_card_transaction(state)

        gate_event = await _approve_click(adapter, 7)

        with _observe(OBSERVED_MERGED):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)
        # A late contradictory completion must not rewrite the first terminal.
        with _observe(OBSERVED_OPEN):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.FAILURE)

        rows = _receipt_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        assert "result=merged" in _header_region(str(rows[0]["content"]))

    @pytest.mark.asyncio
    async def test_same_session_completion_writes_one_provider_observed_receipt(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7, chat_id="oc_origin")
        _begin_card_transaction(state)
        # The gate turn ran inside the origin session itself (same chat, same
        # operator): still a material terminal approval-card result.  The
        # freeform gate response already in the origin transcript may stay,
        # but it can never substitute for the structured receipt.
        gate_event = _make_gate_event(adapter, state, user_id="ou_dev")
        assert _gate_session_key(adapter, gate_event) == ORIGIN_SESSION_KEY
        _append_origin_messages(
            ("user", gate_event.text), ("assistant", GATE_REPORT_MERGED),
        )

        with _observe(OBSERVED_MERGED):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)

        rows = _receipt_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1, (
            "same-session gate completion must write exactly ONE structured "
            "execution receipt to the origin session"
        )
        assert rows[0]["role"] == "assistant"
        content = str(rows[0]["content"])
        assert content.startswith(RECEIPT_PREFIX)
        assert DETAILS_OPEN in content
        assert content.split("\n")[-1] == DETAILS_CLOSE
        header = _header_region(content)
        assert f"transaction_id={CARD_MESSAGE_ID}" in header
        assert "card_action=approved" in header
        # Provider-observed classification with the complete sanitized report.
        assert "result=merged" in header
        assert "operation=completed" in header
        body = _body_region(content)
        assert MERGE_COMMIT in body
        assert "SENTINEL_GATE_REPORT_MERGED ✅" in body
        assert "ghp_AbCdEfGh123456789012345678901234" not in content
        # The pre-existing freeform gate response remains in the transcript.
        assert any(
            "SENTINEL_GATE_REPORT_MERGED" in str(m.get("content") or "")
            and RECEIPT_PREFIX not in str(m.get("content") or "")
            for m in _load_transcript(ORIGIN_SESSION_ID)
        )

        # A replayed completion callback stays idempotent.
        with _observe(OBSERVED_MERGED):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)
        assert len(_receipt_rows(ORIGIN_SESSION_ID)) == 1

    @pytest.mark.asyncio
    async def test_same_session_model_claim_never_sets_result_without_provider_read(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7, chat_id="oc_origin")
        _begin_card_transaction(state)
        gate_event = _make_gate_event(adapter, state, user_id="ou_dev")
        assert _gate_session_key(adapter, gate_event) == ORIGIN_SESSION_KEY
        _append_origin_messages(
            ("assistant", "I merged the PR successfully! Everything is done."),
        )

        with _observe(UNOBSERVED):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)

        rows = _receipt_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        header = _header_region(str(rows[0]["content"]))
        # The gate model's own success claim in the shared transcript must
        # not become the canonical result.
        assert "result=unknown" in header
        assert "result=merged" not in header
        assert "next_action=verify_provider_state_before_retry" in header

    @pytest.mark.asyncio
    async def test_non_gate_events_write_nothing(self):
        _seed_origin_session()
        adapter = _make_adapter()
        source = adapter.build_source(chat_id="oc_gate", chat_type="group", user_id="ou_admin")
        plain_event = MessageEvent(text="hello", source=source, raw_message={"foo": "bar"})

        with _observe(OBSERVED_MERGED):
            await adapter.on_processing_complete(plain_event, ProcessingOutcome.SUCCESS)

        assert _all_receipt_rows() == []

    @pytest.mark.asyncio
    async def test_stale_card_click_writes_nothing(self):
        _seed_origin_session()
        adapter = _make_adapter()
        _seed_card_state(adapter, approval_id=1, head_sha="0ldhead111" + "0" * 30)
        _seed_card_state(adapter, approval_id=2)

        with patch.object(
            adapter, "_handle_message_with_guards", new_callable=AsyncMock,
        ) as mock_handle:
            await _click(adapter, 1, "approve")

        mock_handle.assert_not_awaited()
        assert _all_receipt_rows() == []


# ===========================================================================
# Old in-flight card payloads and historic legacy records
# ===========================================================================

class TestLegacyAndInFlightPayloads:

    @pytest.mark.asyncio
    async def test_receipt_still_written_without_transaction_id(self):
        _seed_origin_session()
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        state.pop("control_transaction_id", None)
        gate_event = _make_gate_event(adapter, state)

        with _observe(UNOBSERVED):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)

        rows = _receipt_rows(ORIGIN_SESSION_ID)
        assert len(rows) == 1
        header = _header_region(str(rows[0]["content"]))
        # Falls back to the legacy card correlation for the transaction id.
        assert f"transaction_id={CARD_MESSAGE_ID}" in header
        assert "card_action=approved" in header

    @pytest.mark.asyncio
    async def test_historic_legacy_record_is_not_duplicated(self):
        legacy_record = "\n".join(
            (
                "[CONTROL EVENT: GitHub PR gate outcome — NOT a user instruction]",
                f"[github-pr-gate-outcome corr={CARD_MESSAGE_ID} result=pass "
                f"repo={REPO} pr=#{PR_NUMBER} head={HEAD_SHA[:12]}]",
                "The controlled pre-merge gate run reached a terminal delivery state.",
                "No merge status is implied by this record.",
            )
        )
        _register_session(ORIGIN_SESSION_KEY, ORIGIN_SESSION_ID)
        _seed_session_db(
            ORIGIN_SESSION_ID,
            messages=[("assistant", legacy_record)],
        )
        adapter = _make_adapter()
        state = _seed_card_state(adapter, approval_id=7)
        state.pop("control_transaction_id", None)
        gate_event = _make_gate_event(adapter, state)

        with _observe(OBSERVED_MERGED):
            await adapter.on_processing_complete(gate_event, ProcessingOutcome.SUCCESS)

        assert _receipt_rows(ORIGIN_SESSION_ID) == []
        legacy_rows = [
            m for m in _load_transcript(ORIGIN_SESSION_ID)
            if LEGACY_MARKER in str(m.get("content") or "")
        ]
        assert len(legacy_rows) == 1


# ===========================================================================
# Persistence boundary at the adapter level: compression tip
# ===========================================================================

class TestPersistenceBoundaries:

    @pytest.mark.asyncio
    async def test_receipt_lands_on_compression_tip_of_origin_session(self):
        from hermes_state import SessionDB

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
        state = _seed_card_state(adapter, approval_id=7)
        _begin_card_transaction(state)

        await _click(adapter, 7, "reject")

        assert _receipt_rows("sess_child"), (
            "receipt must land on the compression-continuation tip so it is "
            "part of the live transcript after compression"
        )
        assert _receipt_rows("sess_parent") == []
