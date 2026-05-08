"""Tests for preserving explicit model.context_length during overflow compression."""

from unittest.mock import patch


from run_agent import _resolve_context_overflow_context_length


def test_preserves_explicit_context_length_when_overflow_has_no_parsed_limit():
    """Generic overflow should compress without stepping down a user override."""
    resolution = _resolve_context_overflow_context_length(
        old_ctx=400_000,
        parsed_limit=None,
        minimax_delta_only_overflow=False,
        config_context_length=400_000,
        preserve_explicit_context_length=True,
    )

    assert resolution.context_length == 400_000
    assert resolution.should_update_context_length is False
    assert resolution.persistable is False
    assert resolution.reason == "preserve_explicit_context_length"


def test_provider_parsed_lower_limit_overrides_preserve_explicit_context_length():
    """A real lower provider limit must still shrink the runtime context."""
    resolution = _resolve_context_overflow_context_length(
        old_ctx=400_000,
        parsed_limit=256_000,
        minimax_delta_only_overflow=False,
        config_context_length=400_000,
        preserve_explicit_context_length=True,
    )

    assert resolution.context_length == 256_000
    assert resolution.should_update_context_length is True
    assert resolution.persistable is True
    assert resolution.reason == "parsed_limit"


def test_can_opt_out_and_use_probe_stepdown_even_with_explicit_context_length():
    """The safety valve should preserve the old probe-tier behavior."""
    resolution = _resolve_context_overflow_context_length(
        old_ctx=400_000,
        parsed_limit=None,
        minimax_delta_only_overflow=False,
        config_context_length=400_000,
        preserve_explicit_context_length=False,
    )

    assert resolution.context_length == 256_000
    assert resolution.should_update_context_length is True
    assert resolution.persistable is False
    assert resolution.reason == "probe_tier"


def _build_agent(config):
    with (
        patch("hermes_cli.config.load_config", return_value=config),
        patch("run_agent.get_tool_definitions", return_value=[]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        from run_agent import AIAgent

        return AIAgent(
            model="gpt-5.5",
            provider="custom",
            base_url="http://localhost:4000/v1",
            api_key="test-" + "key-1234567890",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )


def test_preserve_explicit_context_length_defaults_enabled():
    agent = _build_agent({"model": {"context_length": 400_000}})

    assert agent._config_context_length == 400_000
    assert agent._preserve_explicit_context_length is True


def test_preserve_explicit_context_length_can_be_disabled():
    agent = _build_agent({
        "model": {"context_length": 400_000},
        "context": {"preserve_explicit_context_length": False},
    })

    assert agent._config_context_length == 400_000
    assert agent._preserve_explicit_context_length is False
