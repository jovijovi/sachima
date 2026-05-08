"""MCP server surface tests for FlowWeaver Phase 5C."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class FakeFastMCP:
    def __init__(self, name: str) -> None:
        self.name = name
        self.tools: list[tuple[str, Any]] = []
        self.resources: list[Any] = []
        self.prompts: list[Any] = []
        self.runs: list[str] = []

    def tool(self, name: str | None = None, **_kwargs: Any):
        def decorator(func: Any) -> Any:
            self.tools.append((name or func.__name__, func))
            return func

        return decorator

    def resource(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - should never be called
        self.resources.append((_args, _kwargs))
        raise AssertionError("resources are out of scope for Phase 5C")

    def prompt(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - should never be called
        self.prompts.append((_args, _kwargs))
        raise AssertionError("prompts are out of scope for Phase 5C")

    def run(self, *, transport: str = "stdio") -> None:
        self.runs.append(transport)


def test_importing_mcp_server_does_not_auto_run_or_require_mcp() -> None:
    sys.modules.pop("flowweaver_runtime_client.mcp_server", None)
    module = importlib.import_module("flowweaver_runtime_client.mcp_server")

    assert hasattr(module, "create_mcp_server")
    assert hasattr(module, "run_stdio_server")
    assert getattr(module, "AUTO_RUN_ON_IMPORT") is False


def test_mcp_server_exposes_exactly_one_stdio_tool_and_no_resources_or_prompts(monkeypatch) -> None:
    from flowweaver_runtime_client import mcp_server

    monkeypatch.setattr(mcp_server, "_load_fastmcp", lambda: FakeFastMCP)
    server = mcp_server.create_mcp_server(temporal_address="localhost:7233", runtime_client_factory=lambda: None)

    assert isinstance(server, FakeFastMCP)
    assert server.name == "flowweaver-runtime"
    assert [name for name, _func in server.tools] == ["flowweaver_runtime"]
    assert server.resources == []
    assert server.prompts == []
    assert server.runs == []


def test_run_stdio_server_uses_stdio_transport_only(monkeypatch) -> None:
    from flowweaver_runtime_client import mcp_server

    monkeypatch.setattr(mcp_server, "_load_fastmcp", lambda: FakeFastMCP)
    server = mcp_server.run_stdio_server(temporal_address="127.0.0.1:7233", runtime_client_factory=lambda: None)

    assert isinstance(server, FakeFastMCP)
    assert server.runs == ["stdio"]


def test_mcp_server_source_has_no_http_listener_resource_prompt_or_config_write_surface() -> None:
    source = (PHASE5C_SRC / "flowweaver_runtime_client" / "mcp_server.py").read_text(encoding="utf-8")
    lowered = source.lower()

    forbidden = (
        "transport=\"sse\"",
        "transport='sse'",
        "streamable-http",
        "uvicorn",
        "aiohttp",
        "fastapi",
        ".bind(",
        ".listen(",
        "add_resource",
        ".resource(",
        ".prompt(",
        "config.yaml",
        "mcp_servers",
    )
    assert {marker for marker in forbidden if marker in lowered} == set()
