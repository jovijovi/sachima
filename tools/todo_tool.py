#!/usr/bin/env python3
"""
Todo Tool Module - Planning & Task Management

Provides an in-memory task list the agent uses to decompose complex tasks,
track progress, and maintain focus across long conversations. The state
lives on the AIAgent instance (one per session) and is re-injected into
the conversation after context compression events.

Design:
- Single `todo` tool: provide `todos` param to write, omit to read
- Every call returns the full current list
- No system prompt mutation, no tool response modification
- Behavioral guidance lives entirely in the tool schema description
"""

import json
from typing import Dict, Any, List, Optional

from gateway.progress.todo_lifecycle import (
    normalize_owner_scope_ref,
    normalize_todo_lifecycle,
)


# Valid status values for todo items
VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}

# Bounds on persisted todo state. The todo list is a planning aid the model
# re-reads after every context-compression event (see format_for_injection),
# so unbounded item content or count defeats the compression it rides through.
# These caps keep a single oversized item (whether authored by the model or
# replayed from caller-supplied history on the API server) from inflating the
# re-injection block. Generous relative to real plans — a todo item is a short
# task description, and active lists are a handful of items, not hundreds.
MAX_TODO_CONTENT_CHARS = 4000
MAX_TODO_ITEMS = 256
_TRUNCATION_MARKER = "… [truncated]"


class TodoStore:
    """
    In-memory todo list. One instance per AIAgent (one per session).

    Items are ordered -- list position is priority. Each item has:
      - id: unique string identifier (agent-chosen)
      - content: task description
      - status: pending | in_progress | completed | cancelled
      - parent_id (optional): id of a sibling item this one groups under.
        Supports a single level of grouping for the task workbench display
        (parent + direct children); deeper nesting is not modelled here.
    """

    def __init__(self):
        self._items: List[Dict[str, str]] = []
        self._transaction_id: Optional[str] = None
        self._owner_scope_ref: Optional[Dict[str, str]] = None
        self._lifecycle_state: Optional[str] = None
        self._suspension_reason: Optional[str] = None
        self._next_action: Optional[str] = None

    def write(self, todos: List[Dict[str, Any]], merge: bool = False) -> List[Dict[str, str]]:
        """
        Write todos. Returns the full current list after writing.

        Args:
            todos: list of {id, content, status} dicts
            merge: if False, replace the entire list. If True, update
                   existing items by id and append new ones.
        """
        if not merge:
            # Replace mode: new list entirely
            self._items = [self._validate(t) for t in self._dedupe_by_id(todos)]
            self._lifecycle_state = None
            self._suspension_reason = None
            self._next_action = None
        else:
            # Merge mode: update existing items by id, append new ones
            existing = {item["id"]: item for item in self._items}
            for t in self._dedupe_by_id(todos):
                item_id = str(t.get("id", "")).strip()
                if not item_id:
                    continue  # Can't merge without an id

                if item_id in existing:
                    # Update only the fields the LLM actually provided
                    if "content" in t and t["content"]:
                        existing[item_id]["content"] = self._cap_content(str(t["content"]).strip())
                    if "status" in t and t["status"]:
                        status = str(t["status"]).strip().lower()
                        if status in VALID_STATUSES:
                            existing[item_id]["status"] = status
                    # Allow re-grouping: an explicit parent_id (even an empty one
                    # to detach) updates the link. Validity against the rest of
                    # the list is enforced by _prune_unknown_parents below.
                    if "parent_id" in t:
                        parent_id = self._sanitize_parent_id(t.get("parent_id"), own_id=item_id)
                        if parent_id is not None:
                            existing[item_id]["parent_id"] = parent_id
                        else:
                            existing[item_id].pop("parent_id", None)
                else:
                    # New item -- validate fully and append to end
                    validated = self._validate(t)
                    existing[validated["id"]] = validated
                    self._items.append(validated)
            # Rebuild _items preserving order for existing items
            seen = set()
            rebuilt = []
            for item in self._items:
                current = existing.get(item["id"], item)
                if current["id"] not in seen:
                    rebuilt.append(current)
                    seen.add(current["id"])
            self._items = rebuilt
        # Bound total item count so a replayed/oversized list can't grow the
        # re-injection block without limit. Keep the highest-priority head
        # (list order is priority).
        if len(self._items) > MAX_TODO_ITEMS:
            self._items = self._items[:MAX_TODO_ITEMS]
        # Drop parent links that point outside the surviving list (unknown or
        # truncated-away parents) so a child never references a missing group.
        self._prune_unknown_parents()
        return self.read()

    def read(self) -> List[Dict[str, str]]:
        """Return a copy of the current list.

        Each item carries ``id``/``content``/``status``; ``parent_id`` is
        included only when the item is grouped under another item.
        """
        return [item.copy() for item in self._items]

    def has_items(self) -> bool:
        """Check if there are any items in the list."""
        return bool(self._items)

    def bind_transaction(
        self,
        transaction_id: Optional[str],
        owner_scope_ref: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Bind the current todo list to a sanitized transaction/owner scope."""

        self._transaction_id = str(transaction_id or "").strip() or None
        owner = normalize_owner_scope_ref(owner_scope_ref)
        self._owner_scope_ref = owner.__dict__.copy() if owner is not None else None

    def mark_lifecycle(
        self,
        state: str,
        reason: Optional[str] = None,
        next_action: Optional[str] = None,
    ) -> None:
        """Set lifecycle metadata for the current todo list."""

        lifecycle = normalize_todo_lifecycle(
            {
                "state": state,
                "suspension_reason": reason,
                "next_action": next_action,
                "owner_scope_ref": self._owner_scope_ref,
            }
        )
        if lifecycle is None:
            self._lifecycle_state = None
            self._suspension_reason = None
            self._next_action = None
            return
        self._lifecycle_state = lifecycle.state
        self._suspension_reason = lifecycle.suspension_reason
        self._next_action = lifecycle.next_action

    def clear_for_new_transaction(self) -> None:
        """Clear items and lifecycle metadata for a clean unrelated task."""

        self._items = []
        self._transaction_id = None
        self._owner_scope_ref = None
        self._lifecycle_state = None
        self._suspension_reason = None
        self._next_action = None

    def read_lifecycle(self) -> Optional[Dict[str, Any]]:
        """Return a backward-compatible lifecycle envelope, if one is known."""

        if not self._items and not self._lifecycle_state and not self._transaction_id and not self._owner_scope_ref:
            return None
        completed = sum(1 for item in self._items if item["status"] == "completed")
        remaining = sum(1 for item in self._items if item["status"] in {"pending", "in_progress"})
        if self._lifecycle_state:
            state = self._lifecycle_state
        elif remaining > 0:
            state = "active"
        elif self._items and all(item["status"] == "cancelled" for item in self._items):
            state = "cancelled"
        else:
            state = "completed"
        lifecycle: Dict[str, Any] = {
            "state": state,
            "completed_count": completed,
            "remaining_count": remaining,
        }
        if self._transaction_id:
            lifecycle["transaction_id"] = self._transaction_id
        if self._suspension_reason:
            lifecycle["suspension_reason"] = self._suspension_reason
        if self._next_action:
            lifecycle["next_action"] = self._next_action
        if self._owner_scope_ref:
            lifecycle["owner_scope_ref"] = self._owner_scope_ref.copy()
        return lifecycle

    def read_snapshot(self) -> Dict[str, Any]:
        """Return todos, summary, and optional lifecycle metadata."""

        items = self.read()
        snapshot: Dict[str, Any] = {
            "todos": items,
            "summary": _summary_counts(items),
        }
        lifecycle = self.read_lifecycle()
        if lifecycle is not None:
            snapshot["todo_lifecycle"] = lifecycle
        return snapshot

    def format_for_injection(self) -> Optional[str]:
        """
        Render the todo list for post-compression injection.

        Returns a human-readable string to append to the compressed
        message history, or None if the list is empty.
        """
        if not self._items:
            return None
        if self._lifecycle_state in {"completed", "archived", "suspended", "cancelled"}:
            return None

        # Status markers for compact display
        markers = {
            "completed": "[x]",
            "in_progress": "[>]",
            "pending": "[ ]",
            "cancelled": "[~]",
        }

        # Only inject pending/in_progress items — completed/cancelled ones
        # cause the model to re-do finished work after compression.
        active_items = [
            item for item in self._items
            if item["status"] in {"pending", "in_progress"}
        ]
        if not active_items:
            return None

        lines = ["[Your active task list was preserved across context compression]"]
        for item in active_items:
            marker = markers.get(item["status"], "[?]")
            lines.append(f"- {marker} {item['id']}. {item['content']} ({item['status']})")

        return "\n".join(lines)

    @staticmethod
    def _cap_content(content: str) -> str:
        """Truncate oversized todo content to MAX_TODO_CONTENT_CHARS.

        A single huge item would otherwise inflate the post-compression
        re-injection block (format_for_injection) without bound. Keep the
        head — the actionable part of a task description — plus a marker.
        """
        if len(content) > MAX_TODO_CONTENT_CHARS:
            keep = MAX_TODO_CONTENT_CHARS - len(_TRUNCATION_MARKER)
            return content[:keep] + _TRUNCATION_MARKER
        return content

    def _prune_unknown_parents(self) -> None:
        """Drop parent links that are unknown or would create deeper nesting.

        Runs after every write so a child whose parent was never supplied, was
        dropped by the item-count cap, or is itself already a child falls back to
        a top-level item. This keeps the display's two-level grouping
        well-formed and prevents cycles from surviving in structured state.
        """
        known_ids = {item["id"] for item in self._items}
        valid_parent_by_id: Dict[str, Optional[str]] = {}
        for item in self._items:
            parent_id = item.get("parent_id")
            valid_parent_by_id[item["id"]] = (
                parent_id
                if parent_id is not None and parent_id != item["id"] and parent_id in known_ids
                else None
            )

        for item in self._items:
            parent_id = valid_parent_by_id[item["id"]]
            if parent_id is not None and valid_parent_by_id.get(parent_id) is None:
                item["parent_id"] = parent_id
            else:
                item.pop("parent_id", None)

    @staticmethod
    def _sanitize_parent_id(value: Any, *, own_id: str) -> Optional[str]:
        """Normalize a supplied ``parent_id`` to a safe value or ``None``.

        Empty/missing values and self-references are rejected (returned as
        ``None``); cross-item validity is checked later by
        :meth:`_prune_unknown_parents` once the whole list is known.
        """
        if value is None:
            return None
        parent_id = str(value).strip()
        if not parent_id or parent_id == own_id:
            return None
        return parent_id

    @staticmethod
    def _validate(item: Dict[str, Any]) -> Dict[str, str]:
        """
        Validate and normalize a todo item.

        Ensures required fields exist and status is valid. Returns a clean dict
        with {id, content, status}, plus {parent_id} only when a usable parent
        link was supplied.
        """
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            item_id = "?"

        content = str(item.get("content", "")).strip()
        if not content:
            content = "(no description)"
        else:
            content = TodoStore._cap_content(content)

        status = str(item.get("status", "pending")).strip().lower()
        if status not in VALID_STATUSES:
            status = "pending"

        validated = {"id": item_id, "content": content, "status": status}
        parent_id = TodoStore._sanitize_parent_id(item.get("parent_id"), own_id=item_id)
        if parent_id is not None:
            validated["parent_id"] = parent_id
        return validated

    @staticmethod
    def _dedupe_by_id(todos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collapse duplicate ids, keeping the last occurrence in its position."""
        last_index: Dict[str, int] = {}
        for i, item in enumerate(todos):
            item_id = str(item.get("id", "")).strip() or "?"
            last_index[item_id] = i
        return [todos[i] for i in sorted(last_index.values())]


def todo_tool(
    todos: Optional[List[Dict[str, Any]]] = None,
    merge: bool = False,
    store: Optional[TodoStore] = None,
) -> str:
    """
    Single entry point for the todo tool. Reads or writes depending on params.

    Args:
        todos: if provided, write these items. If None, read current list.
        merge: if True, update by id. If False (default), replace entire list.
        store: the TodoStore instance from the AIAgent.

    Returns:
        JSON string with the full current list and summary metadata.
    """
    if store is None:
        return tool_error("TodoStore not initialized")

    if todos is not None:
        store.write(todos, merge)

    return json.dumps(store.read_snapshot(), ensure_ascii=False)


def _summary_counts(items: List[Dict[str, str]]) -> Dict[str, int]:
    pending = sum(1 for i in items if i["status"] == "pending")
    in_progress = sum(1 for i in items if i["status"] == "in_progress")
    completed = sum(1 for i in items if i["status"] == "completed")
    cancelled = sum(1 for i in items if i["status"] == "cancelled")
    return {
        "total": len(items),
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "cancelled": cancelled,
    }


def check_todo_requirements() -> bool:
    """Todo tool has no external requirements -- always available."""
    return True


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================
# Behavioral guidance is baked into the description so it's part of the
# static tool schema (cached, never changes mid-conversation).

TODO_SCHEMA = {
    "name": "todo",
    "description": (
        "Manage your task list for the current session. Use for complex tasks "
        "with 3+ steps or when the user provides multiple tasks. "
        "Call with no parameters to read the current list.\n\n"
        "Writing:\n"
        "- Provide 'todos' array to create/update items\n"
        "- merge=false (default): replace the entire list with a fresh plan\n"
        "- merge=true: update existing items by id, add any new ones\n\n"
        "Each item: {id: string, content: string, "
        "status: pending|in_progress|completed|cancelled}\n"
        "Optionally set parent_id to the id of another item to group a few "
        "sub-steps under it (one level of grouping only).\n"
        "List order is priority. Only ONE item in_progress at a time.\n"
        "Mark items completed immediately when done. If something fails, "
        "cancel it and add a revised item.\n\n"
        "Always returns the full current list."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": "Task items to write. Omit to read current list.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Unique item identifier"
                        },
                        "content": {
                            "type": "string",
                            "description": "Task description"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "cancelled"],
                            "description": "Current status"
                        },
                        "parent_id": {
                            "type": "string",
                            "description": (
                                "Optional id of another item to group this one "
                                "under (single level of grouping only)."
                            )
                        }
                    },
                    "required": ["id", "content", "status"]
                }
            },
            "merge": {
                "type": "boolean",
                "description": (
                    "true: update existing items by id, add new ones. "
                    "false (default): replace the entire list."
                ),
                "default": False
            }
        },
        "required": []
    }
}


# --- Registry ---
from tools.registry import registry, tool_error

registry.register(
    name="todo",
    toolset="todo",
    schema=TODO_SCHEMA,
    handler=lambda args, **kw: todo_tool(
        todos=args.get("todos"), merge=args.get("merge", False), store=kw.get("store")),
    check_fn=check_todo_requirements,
    emoji="📋",
)
