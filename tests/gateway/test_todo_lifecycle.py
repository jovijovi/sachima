"""Tests for transaction-scoped TODO lifecycle helpers."""

from __future__ import annotations


def test_normalize_lifecycle_rejects_unknown_state():
    from gateway.progress.todo_lifecycle import normalize_todo_lifecycle

    lifecycle = normalize_todo_lifecycle(
        {
            "state": "blocked",
            "suspension_reason": "waiting_external",
            "completed_count": "3",
            "remaining_count": "2",
            "next_action": "wait for /api/progress",
        }
    )

    assert lifecycle is None


def test_owner_scope_ref_hashes_raw_ids_and_does_not_render_raw_values():
    from gateway.progress.todo_lifecycle import make_owner_scope_ref

    owner = make_owner_scope_ref(
        profile="default",
        platform="feishu",
        conversation_id="chat-raw-secret-123",
        user_id="user-raw-secret-456",
        thread_id="thread-raw-secret-789",
        topic_id="topic-raw-secret-000",
    )

    rendered = repr(owner)
    assert owner.profile == "default"
    assert owner.platform == "feishu"
    assert owner.conversation
    assert owner.user
    assert "chat-raw-secret-123" not in rendered
    assert "user-raw-secret-456" not in rendered
    assert "thread-raw-secret-789" not in rendered
    assert "topic-raw-secret-000" not in rendered


def test_resume_signal_requires_single_same_owner_candidate():
    from gateway.progress.todo_lifecycle import (
        SuspendedTodoHint,
        make_owner_scope_ref,
        select_resume_candidate,
    )

    owner = make_owner_scope_ref(
        profile="default",
        platform="feishu",
        conversation_id="raw-chat-id-a",
        user_id="raw-user-id-a",
    )
    hint = SuspendedTodoHint(
        transaction_id="tx-old",
        title="wait for CI",
        reason="waiting_external",
        remaining_count=1,
        owner_scope_ref=owner,
    )

    assert select_resume_candidate("继续", [hint], owner).transaction_id == "tx-old"
    assert select_resume_candidate("continue previous task", [hint], owner).transaction_id == "tx-old"


def test_resume_signal_rejects_cross_owner_candidate():
    from gateway.progress.todo_lifecycle import (
        SuspendedTodoHint,
        make_owner_scope_ref,
        select_resume_candidate,
    )

    requester = make_owner_scope_ref(
        profile="default",
        platform="feishu",
        conversation_id="raw-chat-id-a",
        user_id="raw-user-id-a",
    )
    other_owner = make_owner_scope_ref(
        profile="default",
        platform="feishu",
        conversation_id="raw-chat-id-b",
        user_id="raw-user-id-a",
    )
    hint = SuspendedTodoHint(
        transaction_id="tx-other",
        title="other chat work",
        reason="waiting_user",
        remaining_count=2,
        owner_scope_ref=other_owner,
    )

    assert select_resume_candidate("继续上一任务", [hint], requester) is None


def test_bare_continue_is_ambiguous_with_multiple_candidates():
    from gateway.progress.todo_lifecycle import (
        SuspendedTodoHint,
        make_owner_scope_ref,
        select_resume_candidate,
    )

    owner = make_owner_scope_ref(
        profile="default",
        platform="feishu",
        conversation_id="raw-chat-id-a",
        user_id="raw-user-id-a",
    )
    hints = [
        SuspendedTodoHint(
            transaction_id="tx-one",
            title="first",
            reason="waiting_external",
            remaining_count=1,
            owner_scope_ref=owner,
        ),
        SuspendedTodoHint(
            transaction_id="tx-two",
            title="second",
            reason="waiting_user",
            remaining_count=1,
            owner_scope_ref=owner,
        ),
    ]

    assert select_resume_candidate("继续", hints, owner) is None
    assert select_resume_candidate("继续上一任务", hints, owner) is None
