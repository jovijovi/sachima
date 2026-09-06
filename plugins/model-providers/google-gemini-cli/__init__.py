"""Google Gemini CLI provider profile.

The provider delegates to Google's official ``gemini --acp`` process. OAuth
and Code Assist access remain owned by that CLI; Hermes stores no Google token.
"""

from providers import register_provider
from providers.base import ProviderProfile


class GeminiCLIProfile(ProviderProfile):
    """Official Gemini CLI ACP process; there is no REST model catalog."""

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
    ) -> list[str] | None:
        del api_key, base_url, timeout
        return None


google_gemini_cli = GeminiCLIProfile(
    name="google-gemini-cli",
    aliases=("gemini-cli", "gemini-oauth"),
    display_name="Google Gemini CLI",
    description="Google account through the official Gemini CLI (ACP)",
    signup_url="https://github.com/google-gemini/gemini-cli",
    api_mode="chat_completions",
    env_vars=(),
    base_url="acp://gemini",
    auth_type="external_process",
    supports_health_check=False,
    fallback_models=("gemini-cli",),
)

register_provider(google_gemini_cli)
