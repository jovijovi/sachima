"""P6-B read-only role enforcement (R1/Q1 — fail closed before any launch).

The executor re-checks ``role_binding`` independently of the controlled-exec wall:
capabilities must be a non-empty subset of ``{read, search}`` and the role key must
be an existing read-only controlled role (never a write/future key). Any miss
returns ``p6b_role_not_read_only`` and performs zero launches.
"""

from __future__ import annotations

import pytest

from sachima_supervisor.p6b_read_only_real_agent import P6B_ROLE_NOT_READ_ONLY

from .._support import (
    CountingArtifactSink,
    CountingSupervisor,
    build_executor,
    role_binding,
    step_request,
)


def _execute(executor, binding):
    return executor.execute(step_request(), role_binding=binding, resolved_inputs=())


@pytest.mark.parametrize(
    "binding",
    [
        role_binding(capabilities=("read", "write")),
        role_binding(capabilities=("read", "execute")),
        role_binding(capabilities=("write",)),
        role_binding(capabilities=()),
        role_binding(role_key="sachima.claude.architect"),
        role_binding(role_key="sachima.claude.main_programmer"),
        role_binding(role_key="sachima.codex.blocker_only_reviewer"),
        role_binding(role_key="sachima.unknown.role"),
    ],
)
def test_non_read_only_role_binding_fails_closed(tmp_path, binding):
    supervisor, sink = CountingSupervisor(), CountingArtifactSink()
    executor = build_executor(tmp_path, invoke_supervisor=supervisor, artifact_sink=sink)

    outcome = _execute(executor, binding)

    assert outcome.ok is False
    assert outcome.error_code == P6B_ROLE_NOT_READ_ONLY
    assert supervisor.calls == 0
    assert sink.calls == 0


def test_read_only_role_binding_is_admitted_to_launch(tmp_path):
    supervisor = CountingSupervisor()
    executor = build_executor(tmp_path, invoke_supervisor=supervisor)

    outcome = _execute(executor, role_binding())

    assert outcome.ok is True
    assert supervisor.calls == 1
