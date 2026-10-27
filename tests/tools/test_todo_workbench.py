"""Task-workbench extensions layered onto the upstream revisioned TodoStore."""

import json

from gateway.progress.todo_lifecycle import make_owner_scope_ref
from tools.todo_tool import TodoStore, todo_tool


def _owner() -> dict:
    return make_owner_scope_ref(
        profile="default",
        platform="feishu",
        conversation_id="chat-a",
        user_id="user-a",
    ).__dict__.copy()


def test_executor_and_legacy_parent_survive_without_losing_revisions():
    store = TodoStore()

    items = store.write(
        [
            {"id": "root", "content": "Ship", "status": "in_progress"},
            {
                "id": "review",
                "content": "Review",
                "status": "pending",
                "parent": "root",
                "executor": "Codex",
            },
        ]
    )

    assert items[1]["parent"] == "root"
    assert items[1]["executor"] == "codex"
    assert store.snapshot()["revision"] == 1

    store.write(items)
    assert store.snapshot()["revision"] == 1


def test_invalid_executor_is_omitted_without_dropping_the_item():
    store = TodoStore()

    item = store.write(
        [
            {
                "id": "one",
                "content": "Run tests",
                "status": "pending",
                "executor": "two words",
            }
        ]
    )[0]

    assert item["content"] == "Run tests"
    assert "executor" not in item


def test_lifecycle_snapshot_preserves_revision_and_owner_binding():
    store = TodoStore()
    store.write([{"id": "one", "content": "Run tests", "status": "pending"}])
    store.bind_transaction("tx-1", owner_scope_ref=_owner())
    store.mark_lifecycle("suspended", reason="waiting_external", next_action="Wait for CI")

    snapshot = store.read_snapshot()

    assert snapshot["revision"] >= 1
    assert snapshot["summary"]["pending"] == 1
    assert snapshot["todo_lifecycle"] == {
        "state": "suspended",
        "completed_count": 0,
        "remaining_count": 1,
        "transaction_id": "tx-1",
        "suspension_reason": "waiting_external",
        "next_action": "Wait for CI",
        "owner_scope_ref": _owner(),
    }
    assert json.loads(todo_tool(store=store))["todo_lifecycle"] == snapshot["todo_lifecycle"]
    assert store.format_for_injection() is None


def test_clear_for_new_transaction_removes_prior_todos_and_lifecycle():
    store = TodoStore()
    store.write([{"id": "old", "content": "Old task", "status": "pending"}])
    store.bind_transaction("tx-old", owner_scope_ref=_owner())
    store.mark_lifecycle("active")

    store.clear_for_new_transaction()

    assert store.read_snapshot() == {
        "todos": [],
        "revision": store.snapshot()["revision"],
        "summary": {
            "total": 0,
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "cancelled": 0,
        },
    }


def test_executor_badge_is_preserved_across_context_injection():
    store = TodoStore()
    store.write(
        [
            {
                "id": "review",
                "content": "Review candidate",
                "status": "in_progress",
                "executor": "hermes-agent",
            }
        ]
    )

    assert "[hermes] Review candidate" in store.format_for_injection()
