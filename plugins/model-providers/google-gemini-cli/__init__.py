"""Google Gemini CLI provider profile.

The provider delegates to Google's official ``gemini --acp`` process. OAuth
and Code Assist access remain owned by that CLI; Hermes stores no Google token.
"""

from typing import Any

from providers import register_provider
from providers.base import ProviderProfile


class GeminiCLIProfile(ProviderProfile):
    """Official Gemini CLI ACP process; there is no REST model catalog.

    Hermes core keys external-process providers on ``auth_type`` and this profile's launch
    description (``process_command``/``process_args``); the client is supplied by
    :meth:`create_client` so no core edit names this provider.
    """

    # Consulted by hermes_cli.auth's generic external-process resolver: the remediation for a
    # missing CLI is the official interactive login, and the placeholder api_key names the lane.
    process_missing_cli_code = "missing_gemini_cli"
    process_missing_cli_message = (
        "Could not find the official Gemini CLI command 'gemini'. "
        "Install it with `npm install -g @google/gemini-cli`, then "
        "run `gemini` and choose \"Sign in with Google\"."
    )
    process_api_key_placeholder = "gemini-cli-acp"

    def create_client(self, **client_kwargs: Any) -> Any:
        """Build the Gemini CLI ACP stdio shim rather than an HTTP client."""
        from agent.gemini_acp_client import GeminiCLIACPClient

        return GeminiCLIACPClient(**client_kwargs)

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
    process_command="gemini",
    process_args=("--acp",),
)

register_provider(google_gemini_cli)
