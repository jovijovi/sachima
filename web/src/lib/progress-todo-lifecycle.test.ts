import { describe, expect, it } from "vitest";

import {
  formatSuspendedTodoHint,
  shouldRenderProgressMainTodos,
} from "./progress-todo-lifecycle";

describe("progress TODO lifecycle helpers", () => {
  it("keeps legacy todo snapshots visible but hides archived and suspended lifecycle snapshots", () => {
    expect(shouldRenderProgressMainTodos({ todo_items: [{ id: "1" }] })).toBe(true);
    expect(
      shouldRenderProgressMainTodos({
        todo_items: [{ id: "1" }],
        todo_lifecycle: { state: "active" },
      }),
    ).toBe(true);
    expect(
      shouldRenderProgressMainTodos({
        todo_items: [{ id: "1" }],
        todo_lifecycle: { state: "resumed" },
      }),
    ).toBe(true);
    expect(
      shouldRenderProgressMainTodos({
        todo_items: [{ id: "1" }],
        todo_lifecycle: { state: "completed" },
      }),
    ).toBe(true);
    expect(
      shouldRenderProgressMainTodos({
        todo_items: [{ id: "1" }],
        todo_lifecycle: { state: "archived" },
      }),
    ).toBe(false);
    expect(
      shouldRenderProgressMainTodos({
        todo_items: [{ id: "1" }],
        todo_lifecycle: { state: "suspended" },
      }),
    ).toBe(false);
  });

  it("formats suspended hints separately from current todos", () => {
    expect(
      formatSuspendedTodoHint({
        transaction_id: "tx-old",
        title: "Wait for CI",
        reason: "waiting_external",
        remaining_count: 1,
        next_action: "continue previous task",
      }),
    ).toBe("Wait for CI (1 remaining): continue previous task");
    expect(formatSuspendedTodoHint(null)).toBeNull();
  });
});
