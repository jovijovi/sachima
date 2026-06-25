"""T-worker — exported ops-owned launcher semantics (FR6, Gate F).

``run_p5_temporal_worker`` must start the Worker with the SDK's single
"run until shut down" entry point (``Worker.run()``) exactly once. Temporal's
``async with worker:`` context manager is itself a wrapper that *also* calls
``run()`` in a background task, so combining the two would double-start the
Worker ("Already started"). These tests pin that semantics with an injected fake
Worker — no real Temporal client, service, subprocess, or socket is created.
"""

from __future__ import annotations

import asyncio

import pytest

from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal import p5_temporal_worker as worker_mod


class _FakeWorker:
    """Records lifecycle calls so we can prove the helper starts the worker once.

    ``__aenter__`` mirrors the real SDK Worker, whose context manager runs the
    worker; if the helper entered it *and* called ``run()`` the worker would start
    twice, so reaching ``__aenter__`` here is itself the regression signal.
    """

    def __init__(self) -> None:
        self.run_calls = 0
        self.aenter_calls = 0
        self.aexit_calls = 0

    async def run(self) -> None:
        self.run_calls += 1

    async def __aenter__(self):  # pragma: no cover - reached only on a regression
        self.aenter_calls += 1
        return self

    async def __aexit__(self, *exc):  # pragma: no cover - reached only on a regression
        self.aexit_calls += 1
        return False


def test_run_helper_starts_worker_exactly_once_without_context_manager(monkeypatch):
    fake = _FakeWorker()
    captured: dict = {}

    def _fake_build(client, **kwargs):
        captured["client"] = client
        captured["kwargs"] = kwargs
        return fake

    monkeypatch.setattr(worker_mod, "build_p5_temporal_worker", _fake_build)

    sentinel_client = object()
    asyncio.run(
        worker_mod.run_p5_temporal_worker(sentinel_client, task_queue=C.P5_TEMPORAL_TASK_QUEUE)
    )

    # Started exactly once via run(); never via the context manager (no double-start).
    assert fake.run_calls == 1
    assert fake.aenter_calls == 0
    assert fake.aexit_calls == 0
    # The caller-supplied client + task queue are passed straight to the builder.
    assert captured["client"] is sentinel_client
    assert captured["kwargs"]["task_queue"] == C.P5_TEMPORAL_TASK_QUEUE


def test_run_helper_forwards_worker_kwargs(monkeypatch):
    fake = _FakeWorker()
    captured: dict = {}

    def _fake_build(client, **kwargs):
        captured.update(kwargs)
        return fake

    monkeypatch.setattr(worker_mod, "build_p5_temporal_worker", _fake_build)

    asyncio.run(worker_mod.run_p5_temporal_worker(object(), identity="sachima-p5-temporal-worker"))

    assert fake.run_calls == 1
    assert captured["identity"] == "sachima-p5-temporal-worker"


def test_build_worker_requires_a_caller_supplied_client():
    # The launcher owns no connection lifecycle: a missing client fails closed
    # with the stable precondition code and never self-connects.
    with pytest.raises(C.ContractError) as exc:
        worker_mod.build_p5_temporal_worker(None)
    assert exc.value.code == C.RUNTIME_PRECONDITION_UNMET
