interface ProgressTodoLifecycleLike {
  state?: string | null;
}

interface ProgressSuspendedTodoHintLike {
  transaction_id?: string | null;
  title?: string | null;
  reason?: string | null;
  remaining_count?: number | null;
  next_action?: string | null;
}

export function shouldRenderProgressMainTodos<T extends object>(
  tx: T & { todo_lifecycle?: ProgressTodoLifecycleLike | null },
): boolean {
  const state = tx.todo_lifecycle?.state?.trim().toLowerCase();
  if (!state) return true;
  return ["created", "active", "resumed", "completed", "cancelled"].includes(state);
}

export function formatSuspendedTodoHint(
  hint?: ProgressSuspendedTodoHintLike | null,
): string | null {
  if (!hint) return null;
  const title = hint.title?.trim();
  if (!title) return null;
  const remaining = Math.max(0, Math.trunc(hint.remaining_count ?? 0));
  const nextAction = hint.next_action?.trim();
  let text = `${title} (${remaining} remaining)`;
  if (nextAction) text += `: ${nextAction}`;
  return text;
}
