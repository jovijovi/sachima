"""OpenAI-compatible facade for Google's official Gemini CLI ACP mode.

This module intentionally contains no Google OAuth implementation and never
reads Gemini CLI credential files. Users authenticate with the official CLI;
Hermes launches ``gemini --acp`` and speaks the documented JSON-RPC protocol
over stdio:

https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/acp-mode.md
"""

from __future__ import annotations

from typing import Any

from agent.copilot_acp_client import CopilotACPClient

GEMINI_ACP_MARKER_BASE_URL = "acp://gemini"
GEMINI_ACP_SENTINEL_API_KEY = "gemini-cli-acp"


class GeminiCLIACPClient(CopilotACPClient):
    """Hermes chat facade backed by the official ``gemini --acp`` process."""

    product_name = "Gemini CLI ACP"
    default_model_name = "gemini-cli"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        acp_command: str | None = None,
        acp_args: list[str] | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        resolved_args = acp_args if acp_args is not None else args
        super().__init__(
            api_key=api_key or GEMINI_ACP_SENTINEL_API_KEY,
            base_url=base_url or GEMINI_ACP_MARKER_BASE_URL,
            acp_command=acp_command or command or "gemini",
            acp_args=list(resolved_args) if resolved_args is not None else ["--acp"],
            **kwargs,
        )

    def _process_args(self, model: str | None = None) -> list[str]:
        args = list(self._acp_args)
        requested = str(model or "").strip()
        if requested.lower() in {
            "",
            "auto",
            "default",
            "gemini-cli",
            "google-gemini-cli",
        }:
            return args
        if requested.lower().startswith("google/"):
            requested = requested.split("/", 1)[1]
        if any(
            arg == "--model" or arg == "-m" or arg.startswith("--model=")
            for arg in args
        ):
            return args
        return [*args, "--model", requested]

    def _build_process_env(self) -> dict[str, str]:
        env = super()._build_process_env()
        # This provider specifically represents the Google-account / Code
        # Assist lane. Ambient API keys belonging to Hermes' separate
        # ``gemini`` provider must not silently change the official CLI's auth
        # selection. Project/ADC context remains intact.
        env.pop("GEMINI_API_KEY", None)
        env.pop("GOOGLE_API_KEY", None)
        return env

    def _unsupported_transport_error(self, args: list[str]) -> str:
        preview = " ".join(args[:3]) if args else "(none)"
        return (
            f"ACP transport not supported by '{self._acp_command}': "
            f"`{preview}` is not available. Install or update the official "
            "Gemini CLI (`npm install -g @google/gemini-cli`) and verify "
            "that `gemini --help` advertises `--acp`."
        )

    def _missing_command_error(self) -> str:
        return (
            f"Could not start Gemini CLI ACP command '{self._acp_command}'. "
            "Install the official CLI with `npm install -g "
            "@google/gemini-cli`, then run `gemini` and choose "
            "\"Sign in with Google\" before using Hermes."
        )

    def _format_request_error(self, method: str, message: Any) -> str:
        rendered = super()._format_request_error(method, message)
        if method in {"session/new", "session/prompt"} and any(
            marker in str(message).lower()
            for marker in ("auth", "credential", "login", "sign in")
        ):
            rendered += (
                " Run `gemini` interactively and choose \"Sign in with Google\", "
                "then retry Hermes. Hermes does not read or store the Gemini "
                "CLI's OAuth credentials."
            )
        return rendered

    def _deprecated_cli_error(self, stderr_text: str) -> str | None:
        del stderr_text
        return None

    def _process_exit_error(self, stderr_text: str) -> str:
        rendered = f"{self.product_name} process exited early: {stderr_text}"
        if any(
            marker in stderr_text.lower()
            for marker in ("auth", "credential", "login", "sign in")
        ):
            rendered += (
                " Run `gemini` interactively and choose \"Sign in with Google\" "
                "before retrying Hermes."
            )
        return rendered
