"""Tests for registering the Sachima custom IM channel."""

from unittest.mock import MagicMock

from gateway.config import GatewayConfig, Platform, PlatformConfig, _apply_env_overrides
from gateway.run import GatewayRunner


def test_sachima_platform_value_is_stable():
    """Sachima should be addressable by the stable public platform value."""
    assert Platform("sachima") is Platform.SACHIMA
    assert Platform.SACHIMA.value == "sachima"


def test_sachima_env_override_enables_platform(monkeypatch):
    """SACHIMA_ENABLED=true should create and enable the platform config."""
    monkeypatch.setenv("SACHIMA_ENABLED", "true")
    monkeypatch.setenv("SACHIMA_WEBHOOK_SECRET", "dev-secret")
    monkeypatch.setenv("SACHIMA_WEBHOOK_HOST", "127.0.0.1")
    monkeypatch.setenv("SACHIMA_WEBHOOK_PORT", "8788")
    monkeypatch.setenv("SACHIMA_WEBHOOK_PATH", "/webhook/sachima")
    monkeypatch.setenv("SACHIMA_SEND_URL", "http://127.0.0.1:9000/send")
    monkeypatch.setenv("SACHIMA_ALLOWED_USERS", "dog,cat")

    config = GatewayConfig()
    _apply_env_overrides(config)

    sachima_config = config.platforms[Platform.SACHIMA]
    assert sachima_config.enabled is True
    assert sachima_config.extra["webhook_secret"] == "dev-secret"
    assert sachima_config.extra["webhook_host"] == "127.0.0.1"
    assert sachima_config.extra["webhook_port"] == 8788
    assert sachima_config.extra["webhook_path"] == "/webhook/sachima"
    assert sachima_config.extra["send_url"] == "http://127.0.0.1:9000/send"
    assert sachima_config.extra["allowed_users"] == ["dog", "cat"]
    assert Platform.SACHIMA in config.get_connected_platforms()


def test_gateway_runner_creates_sachima_adapter():
    """GatewayRunner should create a SachimaAdapter for Platform.SACHIMA."""
    from gateway.platforms.sachima import SachimaAdapter

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.SACHIMA: PlatformConfig(enabled=True)}
    )
    runner.delivery_router = MagicMock()

    platform_config = PlatformConfig(enabled=True, extra={"local_mode": True})
    adapter = runner._create_adapter(Platform.SACHIMA, platform_config)

    assert isinstance(adapter, SachimaAdapter)
    assert adapter.platform is Platform.SACHIMA
    assert platform_config.extra["group_sessions_per_user"] is True


def test_sachima_prompt_hint_describes_text_im_channel():
    """Sachima should tell the agent that it is replying in a text IM channel."""
    from agent.prompt_builder import PLATFORM_HINTS

    hint = PLATFORM_HINTS["sachima"]

    assert "Sachima" in hint
    assert "text" in hint.lower()
    assert "IM" in hint


def test_sachima_is_registered_for_platform_tool_defaults():
    """The agent runtime should resolve default tools for the sachima platform."""
    from hermes_cli.platforms import PLATFORMS
    from hermes_cli.tools_config import _get_platform_tools
    from toolsets import resolve_toolset

    assert PLATFORMS["sachima"].default_toolset == "hermes-sachima"
    assert "terminal" in resolve_toolset("hermes-sachima")
    assert "terminal" in _get_platform_tools({}, "sachima")
