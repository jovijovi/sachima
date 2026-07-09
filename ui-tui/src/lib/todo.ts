import type { TodoItem } from '../types.js'

export type TodoTone = 'active' | 'body' | 'dim'

export const todoGlyph = (status: TodoItem['status']) =>
  status === 'completed' ? '[x]' : status === 'cancelled' ? '[-]' : status === 'in_progress' ? '[>]' : '[ ]'

export const todoTone = (status: TodoItem['status']): TodoTone =>
  status === 'in_progress' ? 'active' : status === 'pending' ? 'body' : 'dim'

// Display-boundary validation for the optional executor label, mirroring
// gateway/progress/todo_executor.py: the gateway already normalizes the
// field, but the panel re-validates fail-closed so a stale or hostile
// payload can never render links, mentions, or token-shaped strings.
const SAFE_TODO_EXECUTOR_RE = /^[a-z0-9][a-z0-9._-]{0,31}$/
const TOKEN_LIKE_EXECUTOR_PREFIXES = ['sk-', 'sk_', 'ghp_', 'gho_', 'github_pat_', 'xox', 'hf_', 'hf-', 'pat_']
// Canonical short forms for known long labels, applied after validation.
const TODO_EXECUTOR_ALIASES: Record<string, string> = { 'hermes-agent': 'hermes' }

export const displayTodoExecutor = (value: unknown): null | string => {
  if (typeof value !== 'string') {
    return null
  }

  const text = value.trim().toLowerCase()

  if (!text || !SAFE_TODO_EXECUTOR_RE.test(text)) {
    return null
  }

  if (TOKEN_LIKE_EXECUTOR_PREFIXES.some(prefix => text.startsWith(prefix))) {
    return null
  }

  return TODO_EXECUTOR_ALIASES[text] ?? text
}
