#!/usr/bin/env python3
"""
Todo Tool Module - Planning & Task Management

Provides an in-memory, revisioned task list the agent uses to decompose
complex tasks, track progress, and maintain focus across long conversations.
The state lives on the AIAgent instance (one per session), is re-injected into
the conversation after context compression events, and every write bumps a
monotonic revision so UI clients can reject stale updates.

Design:
- Single `todo` tool: provide `todos` param to write, omit to read
- Every call returns the full current list
- No system prompt mutation, no tool response modification
- Behavioral guidance lives entirely in the tool schema description
"""

import json
from typing import Any, Dict, List, Optional


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
# Upper bound on a single todo tool-result payload accepted during history
# hydration. The gateway/API server replays caller-supplied conversation
# history to rebuild the store, so an oversized forged result is dropped
# before it is parsed and re-injected (see AIAgent._hydrate_todo_store).
MAX_TODO_RESULT_CHARS = 512_000
_TRUNCATION_MARKER = "… [truncated]"
# Persisted as ordinary message content. ContextCompressor uses this stable
# header to distinguish the synthetic post-compaction row from a real user.
TODO_INJECTION_HEADER = (
    "[Your active task list was preserved across context compression]"
)


class TodoStore:
    """
    In-memory todo list. One instance per AIAgent (one per session).

    Items are ordered -- list position is priority. Each item has:
      - id: unique string identifier (agent-chosen)
      - content: task description
      - status: pending | in_progress | completed | cancelled
      - parent: optional id of another item, for nested subtasks
    """

    def __init__(self):
        self._items: List[Dict[str, str]] = []
        self._revision = 0
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
        before = self.read_snapshot(include_revision=False)
        if not merge:
            # Replace mode: new list entirely
            self._items = self._normalize_order(
                [self._validate(t) for t in self._dedupe_by_id(todos)]
            )
            # A replacement is a fresh plan inside the currently bound
            # transaction. Keep the owner binding, but do not carry a terminal
            # or suspended state onto the new items.
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
                    if "parent" in t:
                        parent = str(t["parent"] or "").strip()
                        if parent:
                            existing[item_id]["parent"] = parent
                        else:
                            existing[item_id].pop("parent", None)
                    if "executor" in t:
                        executor = self._normalize_executor(t.get("executor"))
                        if executor is None:
                            existing[item_id].pop("executor", None)
                        else:
                            existing[item_id]["executor"] = executor
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
            self._items = self._normalize_order(rebuilt)
        # Bound total item count so a replayed/oversized list can't grow the
        # re-injection block without limit. Keep the highest-priority head
        # (list order is priority).
        if len(self._items) > MAX_TODO_ITEMS:
            self._items = self._items[:MAX_TODO_ITEMS]
        self._sanitize_parents(self._items)
        if self.read_snapshot(include_revision=False) != before:
            self._revision += 1
        return self.read()

    def read(self) -> List[Dict[str, str]]:
        """Return a copy of the current list."""
        return [item.copy() for item in self._items]

    def has_items(self) -> bool:
        """Check if there are any items in the list."""
        return bool(self._items)

    def snapshot(self) -> Dict[str, Any]:
        """Return the full state clients can reconcile atomically."""
        return self.read_snapshot()

    def bind_transaction(
        self,
        transaction_id: Optional[str],
        owner_scope_ref: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Bind this plan to one task and a privacy-safe owner scope."""
        from gateway.progress.todo_lifecycle import normalize_owner_scope_ref

        tx_id = str(transaction_id or "").strip() or None
        owner = normalize_owner_scope_ref(owner_scope_ref)
        owner_dict = owner.__dict__.copy() if owner is not None else None
        if tx_id == self._transaction_id and owner_dict == self._owner_scope_ref:
            return
        self._transaction_id = tx_id
        self._owner_scope_ref = owner_dict
        self._revision += 1

    def mark_lifecycle(
        self,
        state: str,
        reason: Optional[str] = None,
        next_action: Optional[str] = None,
    ) -> None:
        """Update lifecycle metadata without altering task contents."""
        from gateway.progress.todo_lifecycle import normalize_todo_lifecycle

        lifecycle = normalize_todo_lifecycle(
            {
                "state": state,
                "suspension_reason": reason,
                "next_action": next_action,
                "owner_scope_ref": self._owner_scope_ref,
            }
        )
        values = (
            lifecycle.state if lifecycle is not None else None,
            lifecycle.suspension_reason if lifecycle is not None else None,
            lifecycle.next_action if lifecycle is not None else None,
        )
        if values == (
            self._lifecycle_state,
            self._suspension_reason,
            self._next_action,
        ):
            return
        self._lifecycle_state, self._suspension_reason, self._next_action = values
        self._revision += 1

    def clear_for_new_transaction(self) -> None:
        """Start an unrelated task with no TODO state from the prior task."""
        if not any(
            (
                self._items,
                self._transaction_id,
                self._owner_scope_ref,
                self._lifecycle_state,
                self._suspension_reason,
                self._next_action,
            )
        ):
            return
        self._items = []
        self._transaction_id = None
        self._owner_scope_ref = None
        self._lifecycle_state = None
        self._suspension_reason = None
        self._next_action = None
        self._revision += 1

    def read_lifecycle(self) -> Optional[Dict[str, Any]]:
        """Return the lifecycle envelope carried in persisted tool results."""
        if not any(
            (
                self._items,
                self._transaction_id,
                self._owner_scope_ref,
                self._lifecycle_state,
            )
        ):
            return None
        summary = self._summary_counts(self._items)
        if self._lifecycle_state:
            state = self._lifecycle_state
        elif summary["pending"] or summary["in_progress"]:
            state = "active"
        elif self._items and summary["cancelled"] == summary["total"]:
            state = "cancelled"
        else:
            state = "completed"
        lifecycle: Dict[str, Any] = {
            "state": state,
            "completed_count": summary["completed"],
            "remaining_count": summary["pending"] + summary["in_progress"],
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

    def read_snapshot(self, *, include_revision: bool = True) -> Dict[str, Any]:
        """Return TODOs, revision, summary, and optional lifecycle atomically."""
        items = self.read()
        result: Dict[str, Any] = {
            "todos": items,
            "summary": self._summary_counts(items),
        }
        if include_revision:
            result["revision"] = self._revision
        lifecycle = self.read_lifecycle()
        if lifecycle is not None:
            result["todo_lifecycle"] = lifecycle
        return result

    def restore(
        self,
        todos: List[Dict[str, Any]],
        *,
        revision: Any = 0,
    ) -> List[Dict[str, str]]:
        """Restore a trusted snapshot without manufacturing a new revision."""
        self._items = self._normalize_order(
            [self._validate(t) for t in self._dedupe_by_id(todos)]
        )[:MAX_TODO_ITEMS]
        self._transaction_id = None
        self._owner_scope_ref = None
        self._lifecycle_state = None
        self._suspension_reason = None
        self._next_action = None
        try:
            self._revision = max(0, int(revision or 0))
        except (TypeError, ValueError):
            self._revision = 0
        return self.read()

    def format_for_injection(self) -> Optional[str]:
        """
        Render the todo list for post-compression injection.

        Returns a human-readable string to append to the compressed
        message history, or None if the list is empty.
        """
        if not self._items:
            return None
        if self._lifecycle_state in {
            "completed",
            "archived",
            "suspended",
            "cancelled",
        }:
            return None

        # Status markers for compact display
        markers = {
            "completed": "[x]",
            "in_progress": "[>]",
            "pending": "[ ]",
            "cancelled": "[~]",
        }

        # Only inject pending/in_progress items — completed/cancelled ones
        # cause the model to re-do finished work after compression. A parent
        # is kept (with its real status marker) when any descendant is
        # active, so subtasks keep their context.
        active = {"pending", "in_progress"}
        children: Dict[str, List[Dict[str, str]]] = {}
        roots: List[Dict[str, str]] = []
        for item in self._items:
            parent = item.get("parent")
            if parent:
                children.setdefault(parent, []).append(item)
            else:
                roots.append(item)

        def render(item: Dict[str, str], depth: int, out: List[str]) -> bool:
            kid_lines: List[str] = []
            has_active_kid = False
            for kid in children.get(item["id"], []):
                has_active_kid |= render(kid, depth + 1, kid_lines)
            keep = item["status"] in active or has_active_kid
            if keep:
                marker = markers.get(item["status"], "[?]")
                executor = f"[{item['executor']}] " if item.get("executor") else ""
                out.append(
                    f"{'  ' * depth}- {marker} {item['id']}. "
                    f"{executor}{item['content']} ({item['status']})"
                )
                out.extend(kid_lines)
            return keep

        lines = [TODO_INJECTION_HEADER]
        for item in roots:
            render(item, 0, lines)
        if len(lines) == 1:
            return None

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

    @staticmethod
    def _validate(item: Dict[str, Any]) -> Dict[str, str]:
        """
        Validate and normalize a todo item.

        Ensures required fields exist and status is valid.
        Returns a clean dict with only {id, content, status}.
        """
        if not isinstance(item, dict):
            return {"id": "?", "content": "(invalid item)", "status": "pending"}

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

        result = {"id": item_id, "content": content, "status": status}
        parent = str(item.get("parent") or "").strip()
        if parent and parent != item_id:
            result["parent"] = parent
        executor = TodoStore._normalize_executor(item.get("executor"))
        if executor is not None:
            result["executor"] = executor
        return result

    @staticmethod
    def _normalize_executor(value: Any) -> Optional[str]:
        """Use the workbench's bounded display-label contract lazily."""
        from gateway.progress.todo_executor import normalize_todo_executor

        return normalize_todo_executor(value)

    @staticmethod
    def _summary_counts(items: List[Dict[str, str]]) -> Dict[str, int]:
        return {
            "total": len(items),
            "pending": sum(1 for item in items if item["status"] == "pending"),
            "in_progress": sum(
                1 for item in items if item["status"] == "in_progress"
            ),
            "completed": sum(1 for item in items if item["status"] == "completed"),
            "cancelled": sum(1 for item in items if item["status"] == "cancelled"),
        }

    @staticmethod
    def _sanitize_parents(items: List[Dict[str, str]]) -> None:
        """Drop dangling parent refs and break cycles (in place).

        A parent pointing at a missing id, or a chain that loops back on
        itself, would corrupt tree rendering — such items become roots.
        """
        ids = {item["id"] for item in items}
        by_id = {item["id"]: item for item in items}
        for item in items:
            parent = item.get("parent")
            if parent and parent not in ids:
                item.pop("parent", None)
        for item in items:
            seen = {item["id"]}
            node = item
            while node.get("parent"):
                if node["parent"] in seen:
                    item.pop("parent", None)
                    break
                seen.add(node["parent"])
                node = by_id[node["parent"]]

    @staticmethod
    def _dedupe_by_id(todos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collapse duplicate ids, keeping the last occurrence in its position."""
        last_index: Dict[str, int] = {}
        for i, item in enumerate(todos):
            if not isinstance(item, dict):
                # Non-dict items get a synthetic key so _validate can handle them
                last_index[f"__invalid_{i}"] = i
                continue
            item_id = str(item.get("id", "")).strip() or "?"
            last_index[item_id] = i
        return [todos[i] for i in sorted(last_index.values())]

    @staticmethod
    def _normalize_order(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Lift the active step ahead of any earlier unfinished placeholders."""
        # Nested lists keep authored order — reordering a flat position would
        # tear a subtask away from its siblings.
        if any(item.get("parent") for item in items):
            return items
        active_index = next(
            (i for i, item in enumerate(items) if item["status"] == "in_progress"),
            None,
        )
        if active_index is None:
            return items

        pending_index = next(
            (
                i for i, item in enumerate(items[:active_index])
                if item["status"] == "pending"
            ),
            None,
        )
        if pending_index is None:
            return items

        normalized = items.copy()
        active_item = normalized.pop(active_index)
        normalized.insert(pending_index, active_item)
        return normalized


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
        # Guard: LLM sometimes sends todos as a JSON string instead of a list
        if isinstance(todos, str):
            try:
                todos = json.loads(todos)
            except (json.JSONDecodeError, TypeError):
                return tool_error("todos must be a list of objects, got unparseable string")
        if not isinstance(todos, list):
            return tool_error(
                f"todos must be a list, got {type(todos).__name__}"
            )
        store.write(todos, merge)

    return json.dumps(store.read_snapshot(), ensure_ascii=False)


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
    # Dieted (#95681): the item shape and merge semantics live ONLY in the
    # parameter schema below — the description teaches behavior, not
    # structure the params already define.
    "description": (
        "Manage your task list for the current session. Use for complex tasks "
        "with 3+ steps or when the user provides multiple tasks. "
        "For 'all N items' tasks, enumerate every instance as its own checklist "
        "item so none are silently dropped. "
        "Call with no parameters to read the current list.\n"
        "List order is priority. Only ONE item in_progress at a time. "
        "Break large phases into subtasks via parent. "
        "Mark an item completed only after the work is verified done, never "
        "based on intent. If something fails, cancel it and add a revised "
        "item. Always returns the full current list."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": "Task items to write.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string"
                        },
                        "content": {
                            "type": "string",
                            "description": "Task description"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "cancelled"]
                        },
                        "parent": {
                            "type": "string",
                            "description": "Optional id of another item, making this a nested subtask. Omit for top-level."
                        },
                        "executor": {
                            "type": "string",
                            "description": (
                                "Optional executing-agent label for display "
                                "(for example codex, claude, or hermes). "
                                "This records assignment; it does not launch an agent."
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
                    "false (default): replace the entire list with a fresh plan."
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
