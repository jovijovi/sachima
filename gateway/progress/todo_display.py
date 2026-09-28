"""Shared display policy for structured todo snapshots.

The task workbench renders a plan *leaf-first*: a top-level item that has direct
children is a group/summary node, and the work itself is the leaves — childless
top-level items plus every direct child. Only leaves are counted in the todo
headline and only leaves consume the display budget; a group header is structure,
not work.

This module owns that policy end to end (budget, retention bound, grouping and
selection maths) so the tracker, the persistence/read paths, the renderers, and
the tests all share one source of truth instead of re-deriving it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

# Leaf tasks a progress card renders before it summarizes the rest. Group
# headers never consume this budget, so a card can show more lines than this.
MAX_VISIBLE_TODO_LEAVES = 20

# Items a sanitized snapshot retains. This is a *retention* bound, not a display
# bound: leaf totals, per-group aggregates, and overflow counts are computed from
# the whole plan, so the snapshot must be able to carry the complete source list
# (``tools.todo_tool.MAX_TODO_ITEMS``) instead of a truncated head that would
# silently understate the work. Per-item text stays length-capped by the
# tracker/store/reader sanitizers, so a retained plan is still bounded.
MAX_SNAPSHOT_TODO_ITEMS = 256


def todo_depth(item: Any) -> int:
    """Return the clamped display depth of a todo item (0 or 1)."""

    try:
        return 1 if int(getattr(item, "depth", 0)) >= 1 else 0
    except Exception:
        return 0


def todo_status_key(item: Any) -> str:
    """Return an item's normalized status key ("" when absent/unusable)."""

    return str(getattr(item, "status", "") or "").strip().lower()


def todo_done_count(items: Iterable[Any]) -> int:
    return sum(1 for item in items or () if todo_status_key(item) == "completed")


def group_todo_blocks(items: Iterable[Any]) -> list[tuple[Any, list]]:
    """Group a flat todo snapshot into ordered two-level blocks.

    Returns ``(top_item, child_items)`` tuples preserving the input order. A
    depth-1 item whose ``parent_id`` resolves to a known top-level id is nested
    under that parent; roots and any orphaned/over-nested children each become
    their own block, so display never exceeds two levels.
    """

    materialized = [item for item in (items or ()) if item is not None]
    root_ids = {getattr(it, "id", "") for it in materialized if todo_depth(it) == 0 and getattr(it, "id", "")}
    children_by_parent: dict[str, list] = {}
    for it in materialized:
        if todo_depth(it) == 1:
            parent_id = getattr(it, "parent_id", None)
            if parent_id in root_ids:
                children_by_parent.setdefault(parent_id, []).append(it)

    blocks: list[tuple[Any, list]] = []
    for it in materialized:
        if todo_depth(it) == 1 and getattr(it, "parent_id", None) in root_ids:
            continue  # rendered under its parent block
        kids = children_by_parent.get(getattr(it, "id", ""), []) if todo_depth(it) == 0 else []
        blocks.append((it, kids))
    return blocks


@dataclass(frozen=True)
class TodoDisplayBlock:
    """One rendered block: a standalone leaf, or a group plus its shown children.

    ``child_total``/``child_completed`` aggregate *all* direct children, even the
    ones cut by the display budget, so a group header never reports a smaller
    plan than the one that exists. ``hidden_children`` is how many of this
    group's leaves were cut.
    """

    item: Any
    is_group: bool = False
    children: tuple[Any, ...] = ()
    child_total: int = 0
    child_completed: int = 0
    hidden_children: int = 0


@dataclass(frozen=True)
class TodoDisplayPlan:
    """Blocks to render plus the leaf statistics of the *whole* plan."""

    blocks: tuple[TodoDisplayBlock, ...] = ()
    leaf_total: int = 0
    leaf_completed: int = 0
    hidden_leaves: int = 0

    @property
    def completed_percent(self) -> int:
        if self.leaf_total <= 0:
            return 0
        return self.leaf_completed * 100 // self.leaf_total


def build_todo_display_plan(
    items: Iterable[Any],
    *,
    max_leaves: int = MAX_VISIBLE_TODO_LEAVES,
) -> TodoDisplayPlan:
    """Select the leaves a card shows and count the ones it cannot.

    Leaves are taken in plan order until ``max_leaves`` is spent. A group is
    emitted only when at least one of its children fits, so the card never shows
    a header with nothing under it; the leaves of a dropped group still count
    toward ``hidden_leaves``.
    """

    try:
        budget = max(0, int(max_leaves))
    except Exception:
        budget = MAX_VISIBLE_TODO_LEAVES

    grouped = group_todo_blocks(items)
    leaf_total = 0
    leaf_completed = 0
    for top, kids in grouped:
        leaves = kids if kids else [top]
        leaf_total += len(leaves)
        leaf_completed += todo_done_count(leaves)

    blocks: list[TodoDisplayBlock] = []
    shown = 0
    for top, kids in grouped:
        remaining = budget - shown
        if remaining <= 0:
            break
        if kids:
            visible = tuple(kids[:remaining])
            blocks.append(
                TodoDisplayBlock(
                    item=top,
                    is_group=True,
                    children=visible,
                    child_total=len(kids),
                    child_completed=todo_done_count(kids),
                    hidden_children=len(kids) - len(visible),
                )
            )
            shown += len(visible)
        else:
            blocks.append(TodoDisplayBlock(item=top))
            shown += 1

    return TodoDisplayPlan(
        blocks=tuple(blocks),
        leaf_total=leaf_total,
        leaf_completed=leaf_completed,
        hidden_leaves=max(0, leaf_total - shown),
    )
