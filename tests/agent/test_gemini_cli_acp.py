"""Contracts for the supported Gemini CLI account integration.

Hermes must drive Google's official CLI through its documented ACP surface.
It must not import, persist, or replay the CLI's OAuth credentials itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


def test_provider_identity_and_legacy_aliases_are_preserved() -> None:
    from hermes_cli.auth import PROVIDER_REGISTRY, resolve_provider
    from hermes_cli.models import normalize_provider, provider_label
    from providers import get_provider_profile

    profile = get_provider_profile("google-gemini-cli")

    assert profile is not None
    assert profile.auth_type == "external_process"
    assert profile.base_url == "acp://gemini"
    assert resolve_provider("gemini-cli") == "google-gemini-cli"
    assert resolve_provider("gemini-oauth") == "google-gemini-cli"
    assert normalize_provider("gemini-cli") == "google-gemini-cli"
    assert provider_label("google-gemini-cli") == "Google Gemini CLI"
    assert PROVIDER_REGISTRY["google-gemini-cli"].inference_base_url == "acp://gemini"


def test_runtime_uses_official_cli_and_replaces_legacy_cloudcode_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hermes_cli.auth.shutil.which",
        lambda command: "/opt/google/bin/gemini" if command == "gemini" else None,
    )
    monkeypatch.setattr(
        "hermes_cli.runtime_provider._get_model_config",
        lambda: {
            "provider": "google-gemini-cli",
            "default": "gemini-3.1-pro-preview",
            "base_url": "cloudcode-pa://google",
        },
    )

    from hermes_cli.runtime_provider import resolve_runtime_provider

    runtime = resolve_runtime_provider(requested="gemini-oauth")

    assert runtime == {
        "provider": "google-gemini-cli",
        "api_mode": "chat_completions",
        "base_url": "acp://gemini",
        "api_key": "gemini-cli-acp",
        "command": "/opt/google/bin/gemini",
        "args": ["--acp"],
        "source": "process",
        "requested_provider": "gemini-oauth",
    }


def test_runtime_missing_cli_has_supported_login_remediation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hermes_cli.auth.shutil.which", lambda _command: None)

    from hermes_cli.auth import AuthError
    from hermes_cli.runtime_provider import resolve_runtime_provider

    with pytest.raises(AuthError) as caught:
        resolve_runtime_provider(requested="google-gemini-cli")

    assert caught.value.code == "missing_gemini_cli"
    message = str(caught.value)
    assert "@google/gemini-cli" in message
    assert "run `gemini`" in message
    assert "Sign in with Google" in message


def test_gemini_client_passes_specific_model_to_official_cli() -> None:
    from agent.gemini_acp_client import GeminiCLIACPClient

    client = GeminiCLIACPClient(acp_args=["--acp"])

    assert client._process_args("gemini-cli") == ["--acp"]
    assert client._process_args("google/gemini-3.1-pro-preview") == [
        "--acp",
        "--model",
        "gemini-3.1-pro-preview",
    ]


def test_gemini_client_does_not_let_ambient_api_keys_change_oauth_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.gemini_acp_client import GeminiCLIACPClient

    monkeypatch.setattr(
        "agent.copilot_acp_client._build_subprocess_env",
        lambda: {
            "HOME": "/profile-home",
            "GEMINI_API_KEY": "gemini-secret",
            "GOOGLE_API_KEY": "google-secret",
            "GOOGLE_CLOUD_PROJECT": "supported-project-context",
        },
    )

    env = GeminiCLIACPClient()._build_process_env()

    assert "GEMINI_API_KEY" not in env
    assert "GOOGLE_API_KEY" not in env
    assert env["GOOGLE_CLOUD_PROJECT"] == "supported-project-context"
    assert env["HOME"] == "/profile-home"


def _write_fake_acp_server(path: Path, capture_path: Path) -> None:
    path.write_text(
        """
import json
import sys

capture_path = sys.argv[1]

for line in sys.stdin:
    request = json.loads(line)
    with open(capture_path, "a", encoding="utf-8") as capture:
        capture.write(json.dumps(request) + "\\n")
    request_id = request["id"]
    method = request["method"]
    if method == "initialize":
        result = {
            "protocolVersion": 1,
            "authMethods": [{"id": "oauth-personal", "name": "Log in with Google"}],
        }
        print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}), flush=True)
    elif method == "session/new":
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"sessionId": "gemini-session"},
        }), flush=True)
    elif method == "session/prompt":
        print(json.dumps({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "gemini-session",
                "update": {
                    "sessionUpdate": "agent_thought_chunk",
                    "content": {"type": "text", "text": "reasoning"},
                },
            },
        }), flush=True)
        print(json.dumps({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "gemini-session",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {
                        "type": "text",
                        "text": "<tool_call>{\\\"id\\\":\\\"call_weather\\\",\\\"type\\\":\\\"function\\\",\\\"function\\\":{\\\"name\\\":\\\"weather\\\",\\\"arguments\\\":\\\"{\\\\\\\"city\\\\\\\":\\\\\\\"Paris\\\\\\\"}\\\"}}</tool_call>",
                    },
                },
            },
        }), flush=True)
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"stopReason": "end_turn"},
        }), flush=True)
""".lstrip(),
        encoding="utf-8",
    )


def test_real_acp_subprocess_bridges_messages_tools_reasoning_and_stream(
    tmp_path: Path,
) -> None:
    from agent.gemini_acp_client import GeminiCLIACPClient

    server = tmp_path / "fake_gemini_acp.py"
    capture = tmp_path / "requests.ndjson"
    _write_fake_acp_server(server, capture)
    client = GeminiCLIACPClient(
        acp_command=sys.executable,
        acp_args=[str(server), str(capture)],
        acp_cwd=str(tmp_path),
    )

    stream = client.chat.completions.create(
        model="gemini-cli",
        messages=[
            {"role": "system", "content": "Follow the contract."},
            {"role": "user", "content": "What is the weather?"},
            {"role": "assistant", "content": "I will check."},
            {"role": "tool", "content": "Previous tool context."},
        ],
        tools=[{
            "type": "function",
            "function": {
                "name": "weather",
                "description": "Fetch weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }],
        stream=True,
    )

    chunks = list(stream)
    tool_delta = chunks[0].choices[0].delta.tool_calls[0]
    assert chunks[0].choices[0].finish_reason == "tool_calls"
    assert chunks[0].choices[0].delta.reasoning == "reasoning"
    assert tool_delta.id == "call_weather"
    assert tool_delta.function.name == "weather"
    assert json.loads(tool_delta.function.arguments) == {"city": "Paris"}

    requests = [json.loads(line) for line in capture.read_text().splitlines()]
    assert [request["method"] for request in requests] == [
        "initialize",
        "session/new",
        "session/prompt",
    ]
    assert all(request["method"] != "authenticate" for request in requests)
    prompt = requests[-1]["params"]["prompt"][0]["text"]
    assert "System:\nFollow the contract." in prompt
    assert "User:\nWhat is the weather?" in prompt
    assert "Assistant:\nI will check." in prompt
    assert "Tool:\nPrevious tool context." in prompt
    assert '"name": "weather"' in prompt


def test_auth_failure_points_to_official_interactive_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.gemini_acp_client import GeminiCLIACPClient

    client = GeminiCLIACPClient()
    message = client._format_request_error(
        "session/new",
        "Authentication required.",
    )

    assert "Gemini CLI ACP session/new failed" in message
    assert "Run `gemini`" in message
    assert "Sign in with Google" in message
    assert "Hermes does not read or store" in message


def test_model_picker_lists_available_official_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hermes_cli.model_switch import list_authenticated_providers

    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    monkeypatch.setattr(
        "hermes_cli.auth.get_external_process_provider_status",
        lambda provider: {
            "configured": provider == "google-gemini-cli",
            "provider": provider,
        },
    )
    monkeypatch.setattr(
        "hermes_cli.model_switch._credential_pool_is_usable",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr("hermes_cli.auth._load_auth_store", lambda: {})

    rows = list_authenticated_providers(
        current_provider="google-gemini-cli",
        max_models=10,
        probe_custom_providers=False,
    )

    row = next(item for item in rows if item["slug"] == "google-gemini-cli")
    assert row["name"] == "Google Gemini CLI"
    assert row["models"] == ["gemini-cli"]
    assert row["is_current"] is True


def test_setup_flow_replaces_retired_direct_oauth_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hermes_cli.config import load_config, save_config
    from hermes_cli.model_setup_flows import _model_flow_google_gemini_cli

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    config = load_config()
    config["model"] = {
        "default": "gemini-2.5-pro",
        "provider": "google-gemini-cli",
        "base_url": "cloudcode-pa://google",
        "api_key": "retired-direct-oauth-marker",
    }
    save_config(config)

    monkeypatch.setattr(
        "hermes_cli.auth.shutil.which", lambda command: f"/bin/{command}"
    )
    monkeypatch.setattr(
        "hermes_cli.auth._prompt_model_selection",
        lambda *_args, **_kwargs: "gemini-cli",
    )

    _model_flow_google_gemini_cli(config, current_model="gemini-2.5-pro")

    model = load_config()["model"]
    assert model["provider"] == "google-gemini-cli"
    assert model["default"] == "gemini-cli"
    assert model["base_url"] == "acp://gemini"
    assert model["api_mode"] == "chat_completions"
    assert "api_key" not in model
