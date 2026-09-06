"""Contract tests for the shared TODO executor label normalizer.

These pin the *format rules* (charset, length, secret defenses), never a
closed list of known agent names — any token matching the contract is valid
without code changes.
"""

import pytest

from gateway.progress.todo_executor import (
    MAX_TODO_EXECUTOR_CHARS,
    normalize_todo_executor,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("claude", "claude"),
        ("codex", "codex"),
        ("hermes", "hermes"),
        ("other", "other"),
        ("gemini-cli", "gemini-cli"),
        ("qwen_coder.v2", "qwen_coder.v2"),
        ("a", "a"),
        ("0agent", "0agent"),
        ("a" * MAX_TODO_EXECUTOR_CHARS, "a" * MAX_TODO_EXECUTOR_CHARS),
    ],
)
def test_normalize_todo_executor_accepts_compact_tokens(value, expected):
    assert normalize_todo_executor(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Claude", "claude"),
        ("CODEX", "codex"),
        ("  gemini-cli  ", "gemini-cli"),
        ("\tClaude\n", "claude"),
    ],
)
def test_normalize_todo_executor_trims_and_lowercases(value, expected):
    assert normalize_todo_executor(value) == expected


@pytest.mark.parametrize(
    "value",
    ["hermes-agent", "Hermes-Agent", "  hermes-agent  ", "hermes"],
)
def test_normalize_todo_executor_aliases_hermes_agent_to_hermes(value):
    # Legacy stored labels display in the short form; the alias applies after
    # validation, so it can never launder an otherwise-invalid value.
    assert normalize_todo_executor(value) == "hermes"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        123,
        1.5,
        True,
        ["claude"],
        {"name": "claude"},
        "two words",  # whitespace inside
        "a" * (MAX_TODO_EXECUTOR_CHARS + 1),  # over-length → drop, not truncate
        "-leading-dash",  # must start alphanumeric
        ".leading-dot",
        "_leading-underscore",
        "https://evil.example/agent",  # URL-shaped
        "path/to/agent",  # path-shaped
        "agent:role",  # key:value-shaped
        "agent=value",
        "user@host",  # mention/email-shaped
        "<at id=ou_x>bot</at>",
        "[claude](https://evil.example)",  # markdown link
        "代理",  # non-ASCII
    ],
)
def test_normalize_todo_executor_drops_invalid_values(value):
    assert normalize_todo_executor(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "sk-" + "a" * 24,
        "sk-live-key",  # short but credential-prefixed
        "sk_test_key",
        "ghp_" + "b" * 24,
        "gho_token",
        "github_pat_" + "c" * 24,
        "xoxb-slack-token",
        "hf_" + "d" * 24,
        "hf-hub-token",
        "pat_token",
        "Bearer abc123",
    ],
)
def test_normalize_todo_executor_drops_credential_shaped_values(value):
    result = normalize_todo_executor(value)
    assert result is None


def test_normalize_todo_executor_drops_redacted_content():
    # A value the redaction layer rewrites must drop entirely, never render.
    leak = "sk-proj-" + "e" * 24
    assert normalize_todo_executor(leak) is None
    assert normalize_todo_executor(f"token={leak}") is None


def test_normalize_todo_executor_never_raises_on_hostile_objects():
    class Hostile:
        def __repr__(self):
            raise RuntimeError("boom")

    assert normalize_todo_executor(Hostile()) is None
