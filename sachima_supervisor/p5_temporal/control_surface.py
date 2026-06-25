"""No-throw control surface for the P5 Temporal runtime (FR4/FR7, Gates D + G).

``P5TemporalControlSurface`` is the **no-throw public dispatcher** the
``StepExecutor`` bridge talks to. It delegates start / query / cancel / recover /
close to ``P5TemporalRuntimeClient`` and adds a final SCAN-1 leak guard over the
rendered result: any forbidden marker that somehow reached an envelope collapses
to ``runtime_history_leak_detected`` rather than surfacing. Every public method
returns a sanitized result envelope and never raises.
"""

from __future__ import annotations

from typing import Any

from . import contracts as C


def _err(op: str, code: str, *, workflow_id: str | None = None) -> dict[str, Any]:
    return {"ok": False, "op": op, "workflow_id": workflow_id, "snapshot": None, "error_code": code, "replayed": False}


class P5TemporalControlSurface:
    """Sanitized, no-throw dispatcher over the runtime client."""

    def __init__(self, runtime_client: Any) -> None:
        self._runtime_client = runtime_client

    async def start(self, start_request: Any, *, workflow_id: str) -> dict[str, Any]:
        return await self._guard("start", self._runtime_client.start(start_request, workflow_id=workflow_id))

    async def query(self, *, workflow_id: str) -> dict[str, Any]:
        return await self._guard("query", self._runtime_client.query(workflow_id=workflow_id))

    async def cancel(self, *, workflow_id: str, update: Any) -> dict[str, Any]:
        return await self._guard("cancel", self._runtime_client.signal_cancel(workflow_id=workflow_id, update=update))

    async def recover(self, *, workflow_id: str) -> dict[str, Any]:
        return await self._guard("recover", self._runtime_client.recover(workflow_id=workflow_id))

    async def close(self) -> dict[str, Any]:
        return await self._guard("close", self._runtime_client.close())

    async def handle(self, request: Any) -> dict[str, Any]:
        """Generic safe dispatch over an operation request mapping."""

        if not isinstance(request, dict):
            return _err("dispatch", C.RUNTIME_ERROR)
        operation = request.get("operation")
        workflow_id = request.get("workflow_id")
        if operation == "start":
            return await self.start(request.get("start_request"), workflow_id=workflow_id)
        if operation == "query":
            return await self.query(workflow_id=workflow_id)
        if operation == "cancel":
            return await self.cancel(workflow_id=workflow_id, update=request.get("update"))
        if operation == "recover":
            return await self.recover(workflow_id=workflow_id)
        if operation == "close":
            return await self.close()
        return _err("dispatch", C.RUNTIME_ERROR, workflow_id=workflow_id if isinstance(workflow_id, str) else None)

    async def _guard(self, op: str, coro: Any) -> dict[str, Any]:
        try:
            result = await coro
        except BaseException:  # noqa: BLE001 - dispatcher is no-throw by contract
            return _err(op, C.RUNTIME_ERROR)
        if not isinstance(result, dict):
            return _err(op, C.RUNTIME_ERROR)
        if C.scan_projection_for_leak(result) is not None:
            return _err(result.get("op", op) if isinstance(result.get("op"), str) else op, C.RUNTIME_HISTORY_LEAK_DETECTED)
        return result


__all__ = ["P5TemporalControlSurface"]
