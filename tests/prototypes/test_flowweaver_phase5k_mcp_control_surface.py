"""RED MCP stdio wrapper tests for FlowWeaver Phase 5K runtime control surface."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

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
        raise AssertionError("resources are out of scope for Phase 5K")

    def prompt(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - should never be called
        self.prompts.append((_args, _kwargs))
        raise AssertionError("prompts are out of scope for Phase 5K")

    def run(self, *, transport: str = "stdio") -> None:
        self.runs.append(transport)


class FakeRuntimeClient:
    async def query_snapshot(self, workflow_id: str) -> dict[str, object]:
        return {
            "ok": True,
            "operation": "query_snapshot",
            "workflow_id": workflow_id,
            "transaction_id": "runtime_tx_phase5k_mcp",
            "status": "running",
            "snapshot": {
                "type": "flowweaver.temporal_poc.snapshot.v0",
                "version": "flowweaver.temporal_poc.v0",
                "transaction_id": "runtime_tx_phase5k_mcp",
                "status": "running",
                "entry_count": 1,
                "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
                "start_signature": {
                    "type": "flowweaver.temporal_poc.start_signature.v0",
                    "version": "flowweaver.temporal_poc.v0",
                    "idempotency_key": "runtime_event_start_phase5k_mcp",
                    "event_contract_digest": "runtime_sig_" + "a" * 64,
                    "claim_policy_digest": "runtime_sig_" + "b" * 64,
                },
                "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
                "intent_statuses": {"runtime_intent_0": "pending"},
                "artifact_statuses": {"runtime_artifact_0": "available"},
                "delivery_statuses": {"runtime_delivery_0": "planned"},
                "applied_event_count": 0,
                "resume_count": 0,
                "side_effects": [],
            },
        }


def test_importing_mcp_control_server_does_not_auto_run_or_require_mcp() -> None:
    sys.modules.pop("flowweaver_runtime_client.mcp_control_server", None)
    sys.modules.pop("mcp", None)

    module = importlib.import_module("flowweaver_runtime_client.mcp_control_server")

    assert hasattr(module, "create_control_mcp_server")
    assert hasattr(module, "run_stdio_control_server")
    assert getattr(module, "AUTO_RUN_ON_IMPORT") is False
    assert "mcp" not in sys.modules


@pytest.mark.asyncio
async def test_control_mcp_server_exposes_exactly_one_stdio_tool_and_delegates_to_control_surface(monkeypatch) -> None:
    from flowweaver_runtime_client import mcp_control_server

    monkeypatch.setattr(mcp_control_server, "_load_fastmcp", lambda: FakeFastMCP)
    server = mcp_control_server.create_control_mcp_server(
        temporal_address="localhost:7233",
        runtime_client_factory=lambda: FakeRuntimeClient(),
    )

    assert isinstance(server, FakeFastMCP)
    assert server.name == "flowweaver-runtime-control"
    assert [name for name, _func in server.tools] == ["flowweaver_runtime_control"]
    assert server.resources == []
    assert server.prompts == []
    assert server.runs == []

    tool = server.tools[0][1]
    result = await tool(operation="query_transaction", workflow_id="runtime_tx_phase5k_mcp")
    assert result["ok"] is True
    assert result["operation"] == "query_transaction"
    assert result["runtime_operation"] == "query_snapshot"


def test_run_stdio_control_server_uses_stdio_transport_only(monkeypatch) -> None:
    from flowweaver_runtime_client import mcp_control_server

    monkeypatch.setattr(mcp_control_server, "_load_fastmcp", lambda: FakeFastMCP)
    server = mcp_control_server.run_stdio_control_server(
        temporal_address="127.0.0.1:7233",
        runtime_client_factory=lambda: FakeRuntimeClient(),
    )

    assert isinstance(server, FakeFastMCP)
    assert server.runs == ["stdio"]


def test_mcp_control_server_source_has_no_http_listener_resource_prompt_or_config_write_surface() -> None:
    source_path = PHASE5C_SRC / "flowweaver_runtime_client" / "mcp_control_server.py"
    assert source_path.exists(), "Phase 5K must add a default-off stdio control MCP wrapper"
    source = source_path.read_text(encoding="utf-8")
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
        "register_mcp_servers",
    )
    assert {marker for marker in forbidden if marker in lowered} == set()
