"""Optional stdio MCP wrapper for the FlowWeaver Phase 5K control surface."""

from __future__ import annotations

import argparse
from typing import Any, Callable

from flowweaver_runtime_client.control_surface import invoke_flowweaver_runtime_control

AUTO_RUN_ON_IMPORT = False
RuntimeClientFactory = Callable[[], Any]


def _load_fastmcp() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:
        raise RuntimeError("mcp_sdk_unavailable") from exc
    return FastMCP


def create_control_mcp_server(
    *, temporal_address: str, runtime_client_factory: RuntimeClientFactory | None = None
) -> Any:
    FastMCP = _load_fastmcp()
    server = FastMCP("flowweaver-runtime-control")

    @server.tool(name="flowweaver_runtime_control", description="Prototype-only FlowWeaver runtime control adapter")
    async def flowweaver_runtime_control(
        operation: str,
        workflow_id: str | None = None,
        start_payload: dict[str, Any] | None = None,
        update: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        request: dict[str, object] = {"operation": operation}
        if workflow_id is not None:
            request["workflow_id"] = workflow_id
        if start_payload is not None:
            request["start_payload"] = start_payload
        if update is not None:
            request["update"] = update
        return await invoke_flowweaver_runtime_control(
            request,
            temporal_address=temporal_address,
            runtime_client_factory=runtime_client_factory,
        )

    return server


def run_stdio_control_server(
    *, temporal_address: str, runtime_client_factory: RuntimeClientFactory | None = None
) -> Any:
    server = create_control_mcp_server(
        temporal_address=temporal_address,
        runtime_client_factory=runtime_client_factory,
    )
    getattr(server, "run")(transport="stdio")
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the FlowWeaver runtime control MCP stdio prototype.")
    parser.add_argument("--temporal-address", required=True, help="Explicit local Temporal endpoint, for example localhost:7233")
    args = parser.parse_args(argv)
    run_stdio_control_server(temporal_address=args.temporal_address)


if __name__ == "__main__":
    main()


__all__ = [
    "AUTO_RUN_ON_IMPORT",
    "create_control_mcp_server",
    "main",
    "run_stdio_control_server",
]
