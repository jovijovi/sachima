/** Display-boundary validation for the optional per-item TODO executor label.
 *
 *  Mirrors gateway/progress/todo_executor.py: the backend already normalizes
 *  the field, but every display surface re-validates fail-closed so a stale
 *  or hostile payload can never render mentions, links, or token-shaped
 *  strings as an "executor" badge.
 */

const SAFE_TODO_EXECUTOR_RE = /^[a-z0-9][a-z0-9._-]{0,31}$/;

// Credential-shaped values must never render as an executor, even if they
// fit the charset.
const TOKEN_LIKE_EXECUTOR_PREFIXES = [
  "sk-",
  "sk_",
  "ghp_",
  "gho_",
  "github_pat_",
  "xox",
  "hf_",
  "hf-",
  "pat_",
];

// Canonical short forms for known long labels, applied after validation so
// an alias can never launder an otherwise-invalid value.
const TODO_EXECUTOR_ALIASES: Record<string, string> = {
  "hermes-agent": "hermes",
};

/** Return the safe display label for an executor value, or null to hide it. */
export function displayTodoExecutor(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim().toLowerCase();
  if (!text || !SAFE_TODO_EXECUTOR_RE.test(text)) return null;
  if (TOKEN_LIKE_EXECUTOR_PREFIXES.some((prefix) => text.startsWith(prefix))) return null;
  return TODO_EXECUTOR_ALIASES[text] ?? text;
}
