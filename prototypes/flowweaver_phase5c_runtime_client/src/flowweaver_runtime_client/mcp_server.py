"""Optional stdio MCP wrapper for the FlowWeaver Phase 5C runtime adapter."""

from __future__ import annotations

import argparse
from typing import Any, Callable

from flowweaver_runtime_client.tool_adapter import invoke_flowweaver_runtime

AUTO_RUN_ON_IMPORT = False
RuntimeClientFactory = Callable[[], Any]


def _load_fastmcp() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:
        raise RuntimeError("mcp_sdk_unavailable") from exc
    return FastMCP


def create_mcp_server(*, temporal_address: str, runtime_client_factory: RuntimeClientFactory | None = None) -> Any:
    FastMCP = _load_fastmcp()
    server = FastMCP("flowweaver-runtime")

    @server.tool(name="flowweaver_runtime", description="Prototype-only FlowWeaver runtime operation adapter")
    async def flowweaver_runtime(
        operation: str,
        workflow_id: str | None = None,
        start_payload: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        update: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        request: dict[str, object] = {"operation": operation}
        if workflow_id is not None:
            request["workflow_id"] = workflow_id
        if start_payload is not None:
            request["start_payload"] = start_payload
        if payload is not None:
            request["payload"] = payload
        if update is not None:
            request["update"] = update
        return await invoke_flowweaver_runtime(
            request,
            temporal_address=temporal_address,
            runtime_client_factory=runtime_client_factory,
        )

    return server


def run_stdio_server(*, temporal_address: str, runtime_client_factory: RuntimeClientFactory | None = None) -> Any:
    server = create_mcp_server(temporal_address=temporal_address, runtime_client_factory=runtime_client_factory)
    server.run(transport="stdio")
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the FlowWeaver runtime MCP stdio prototype.")
    parser.add_argument("--temporal-address", required=True, help="Explicit local Temporal endpoint, for example localhost:7233")
    args = parser.parse_args(argv)
    run_stdio_server(temporal_address=args.temporal_address)


if __name__ == "__main__":
    main()


__all__ = ["AUTO_RUN_ON_IMPORT", "create_mcp_server", "main", "run_stdio_server"]
