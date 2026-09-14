"""Todo tool: in-memory, revisioned task list for multi-step work. State lives on the
AIAgent (one per session), is re-injected after context compression, and every write bumps
a monotonic revision so UI clients can reject stale updates. One ``todo_list`` tool: pass
``todos`` to write, omit to read; every call returns the full list. No system-prompt mutation."""

import json
from typing import Any, Dict, List, Optional

VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}
# The list is re-read after every compression (format_for_injection), so unbounded
# content/count would defeat the compression it rides through. Caps apply equally to
# model-authored items and caller-replayed API history.
MAX_TODO_CONTENT_CHARS = 4000
MAX_TODO_ITEMS = 256
# Max single todo tool-result payload accepted during history hydration, so a forged
# oversized result is dropped before parsing (AIAgent._hydrate_todo_store).
MAX_TODO_RESULT_CHARS = 512_000
_TRUNCATION_MARKER = "… [truncated]"
# Persisted as ordinary message content; ContextCompressor keys on this stable header to
# tell the synthetic post-compaction row from a real user message.
TODO_INJECTION_HEADER = "[Your active task list was preserved across context compression]"
_STATUS_MARKERS = {"completed": "[x]", "in_progress": "[>]", "pending": "[ ]", "cancelled": "[~]"}
_ACTIVE_STATUSES = {"pending", "in_progress"}


class TodoStore:
    """In-memory todo list, one per AIAgent. List position is priority; items are
    ``{id, content, status, parent?}`` — ``parent`` nests a subtask."""

    def __init__(self):
        self._items: List[Dict[str, str]] = []
        self._revision = 0
        # Sachima TODO lifecycle: one logical task (transaction) with a privacy-safe owner scope.
        self._transaction_id: Optional[str] = None
        self._owner_scope_ref: Optional[Dict[str, str]] = None
        self._lifecycle_state: Optional[str] = None
        self._suspension_reason: Optional[str] = None
        self._next_action: Optional[str] = None

    def _fresh_items(self, todos: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Validate, dedupe and order a whole new list (replace / restore)."""
        return self._normalize_order([self._validate(t) for t in self._dedupe_by_id(todos)])

    def write(self, todos: List[Dict[str, Any]], merge: bool = False) -> List[Dict[str, str]]:
        """Replace the list (default) or merge by id; returns the full list after writing."""
        before = self.read_snapshot(include_revision=False)
        if merge:
            self._merge(todos)
        else:
            self._items = self._fresh_items(todos)
            # A replacement is a fresh plan inside the currently bound transaction. Keep the owner
            # binding, but do not carry a terminal or suspended state onto the new items.
            self._lifecycle_state = None
            self._suspension_reason = None
            self._next_action = None
        del self._items[MAX_TODO_ITEMS:]  # keep the priority head; replays can't grow unbounded
        self._sanitize_parents(self._items)
        if self.read_snapshot(include_revision=False) != before:
            self._revision += 1
        return self.read()

    def _merge(self, todos: List[Dict[str, Any]]) -> None:
        """Update existing items only in the fields provided; append new ones (validated)."""
        existing = {item["id"]: item for item in self._items}
        for t in self._dedupe_by_id(todos):
            item_id = str(t.get("id", "")).strip()
            if not item_id:
                continue  # can't merge without an id
            cur = existing.get(item_id)
            if cur is None:
                validated = self._validate(t)
                existing[validated["id"]] = validated
                self._items.append(validated)
                continue
            if t.get("content"):
                cur["content"] = self._cap_content(str(t["content"]).strip())
            if t.get("status") and str(t["status"]).strip().lower() in VALID_STATUSES:
                cur["status"] = str(t["status"]).strip().lower()
            if "parent" in t:
                parent = str(t["parent"] or "").strip()
                if parent:
                    cur["parent"] = parent
                else:
                    cur.pop("parent", None)
            if "executor" in t:
                executor = self._normalize_executor(t.get("executor"))
                if executor is None:
                    cur.pop("executor", None)
                else:
                    cur["executor"] = executor
        # Rebuild preserving original order for existing items (first occurrence wins).
        rebuilt = {item["id"]: existing.get(item["id"], item) for item in self._items}
        self._items = self._normalize_order(list(rebuilt.values()))

    def read(self) -> List[Dict[str, str]]:
        return [item.copy() for item in self._items]

    def has_items(self) -> bool:
        return bool(self._items)

    def snapshot(self) -> Dict[str, Any]:
        """Full state clients can reconcile atomically."""
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

    def restore(self, todos: List[Dict[str, Any]], *, revision: Any = 0) -> List[Dict[str, str]]:
        """Restore a trusted snapshot without manufacturing a new revision."""
        self._items = self._fresh_items(todos)[:MAX_TODO_ITEMS]
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
        """Render the list for post-compression injection, or None if nothing active. Only
        pending/in_progress items are injected — finished ones make the model re-do work after
        compression. A parent is kept (with its real status marker) when any descendant is
        active so subtasks keep context."""
        if not self._items:
            return None
        if self._lifecycle_state in {"completed", "archived", "suspended", "cancelled"}:
            return None
        children: Dict[str, List[Dict[str, str]]] = {}
        for item in self._items:
            if item.get("parent"):
                children.setdefault(item["parent"], []).append(item)

        def render(item: Dict[str, str], depth: int, out: List[str]) -> bool:
            kid_lines: List[str] = []
            has_active_kid = False
            for kid in children.get(item["id"], []):
                has_active_kid |= render(kid, depth + 1, kid_lines)
            keep = item["status"] in _ACTIVE_STATUSES or has_active_kid
            if keep:
                marker = _STATUS_MARKERS.get(item["status"], "[?]")
                executor = f"[{item['executor']}] " if item.get("executor") else ""
                out.append(f"{'  ' * depth}- {marker} {item['id']}. "
                           f"{executor}{item['content']} ({item['status']})")
                out.extend(kid_lines)
            return keep

        lines = [TODO_INJECTION_HEADER]
        for item in self._items:
            if not item.get("parent"):
                render(item, 0, lines)
        return "\n".join(lines) if len(lines) > 1 else None

    @staticmethod
    def _cap_content(content: str) -> str:
        """Truncate to MAX_TODO_CONTENT_CHARS keeping the head (the actionable part) + marker."""
        if len(content) > MAX_TODO_CONTENT_CHARS:
            return content[:MAX_TODO_CONTENT_CHARS - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER
        return content

    @staticmethod
    def _validate(item: Dict[str, Any]) -> Dict[str, str]:
        """Normalize one item to ``{id, content, status, parent?}`` (placeholders when missing)."""
        if not isinstance(item, dict):
            return {"id": "?", "content": "(invalid item)", "status": "pending"}
        item_id = str(item.get("id", "")).strip() or "?"
        content = str(item.get("content", "")).strip()
        status = str(item.get("status", "pending")).strip().lower()
        result = {"id": item_id,
                  "content": TodoStore._cap_content(content) if content else "(no description)",
                  "status": status if status in VALID_STATUSES else "pending"}
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
            "in_progress": sum(1 for item in items if item["status"] == "in_progress"),
            "completed": sum(1 for item in items if item["status"] == "completed"),
            "cancelled": sum(1 for item in items if item["status"] == "cancelled"),
        }

    @staticmethod
    def _sanitize_parents(items: List[Dict[str, str]]) -> None:
        """Drop dangling parent refs and break cycles in place (such items become roots)."""
        by_id = {item["id"]: item for item in items}
        for item in items:
            if item.get("parent") and item["parent"] not in by_id:
                item.pop("parent", None)
        for item in items:
            seen, node = {item["id"]}, item
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
        for i, item in enumerate(todos):  # non-dicts get a synthetic key; _validate handles them
            key = str(item.get("id", "")).strip() if isinstance(item, dict) else f"__invalid_{i}"
            last_index[key or "?"] = i
        return [todos[i] for i in sorted(last_index.values())]

    @staticmethod
    def _normalize_order(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Lift the in_progress step ahead of any earlier pending placeholder. Nested lists
        keep authored order — reordering would tear a subtask from its siblings."""
        statuses = [item["status"] for item in items]
        if any(item.get("parent") for item in items) or "in_progress" not in statuses:
            return items
        active_index = statuses.index("in_progress")
        if "pending" not in statuses[:active_index]:
            return items
        normalized = items.copy()
        normalized.insert(statuses.index("pending"), normalized.pop(active_index))
        return normalized


def todo_tool(todos: Optional[List[Dict[str, Any]]] = None, merge: bool = False,
              store: Optional[TodoStore] = None) -> str:
    """Write ``todos`` (replace, or ``merge`` by id) or read when None -> list + summary JSON."""
    if store is None:
        return tool_error("TodoStore not initialized")
    if todos is not None:
        if isinstance(todos, str):  # LLMs sometimes send a JSON string instead of a list
            try:
                todos = json.loads(todos)
            except (json.JSONDecodeError, TypeError):
                return tool_error("todos must be a list of objects, got unparseable string")
        if not isinstance(todos, list):
            return tool_error(f"todos must be a list, got {type(todos).__name__}")
        store.write(todos, merge)
    # todos + revision + summary (+ todo_lifecycle when a transaction is bound), one atomic snapshot.
    return json.dumps(store.read_snapshot(), ensure_ascii=False)


def check_todo_requirements() -> bool:
    """Todo tool has no external requirements -- always available."""
    return True


# Behavioral guidance is baked into the (static, cached) description; item shape and merge
# semantics live ONLY in the parameter schema.
TODO_SCHEMA = {
    "name": "todo_list",
    "description": (
        # See #95681.
        "Track a task list for multi-step work (3+ steps). Use for complex tasks "
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


from tools.registry import registry, tool_error

registry.register(
    name="todo_list", toolset="todo", schema=TODO_SCHEMA, check_fn=check_todo_requirements,
    handler=lambda args, **kw: todo_tool(
        todos=args.get("todos"), merge=args.get("merge", False), store=kw.get("store")),
    emoji="📋")
