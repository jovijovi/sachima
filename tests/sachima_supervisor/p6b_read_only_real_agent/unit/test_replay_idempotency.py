"""P6-B replay / idempotency (FR2 — controlled-exec replay never relaunches).

A second ``execute`` with the same controlled-exec store replays the resident
sanitized projection without a second read-only-runner launch. (The WP4-claim
replay path — executor never called — is proven in the hermetic composition.)
"""

from __future__ import annotations

from sachima_supervisor.activity_controlled_exec import (
    ControlledLocalExecClaimStore,
    FileControlledLocalExecClaimStore,
)

from .._support import (
    CountingArtifactSink,
    CountingSupervisor,
    build_executor,
    role_binding,
    step_request,
)


def test_controlled_exec_replay_does_not_launch_twice(tmp_path):
    supervisor = CountingSupervisor()
    sink = CountingArtifactSink()
    store = ControlledLocalExecClaimStore()
    executor = build_executor(
        tmp_path, invoke_supervisor=supervisor, artifact_sink=sink, controlled_exec_store=store
    )

    first = executor.execute(step_request(), role_binding=role_binding(), resolved_inputs=())
    second = executor.execute(step_request(), role_binding=role_binding(), resolved_inputs=())

    assert first.ok is True
    assert second.ok is True
    # The read-only runner launched exactly once across both attempts.
    assert supervisor.calls == 1
    # The replayed projection is identical (deterministic resident state).
    assert first.artifact_refs == second.artifact_refs
    assert first.evidence_ref == second.evidence_ref


def test_file_controlled_exec_replay_survives_executor_restart_without_second_launch(
    tmp_path,
):
    supervisor = CountingSupervisor()
    sink = CountingArtifactSink()
    store_path = tmp_path / "claim-store" / "controlled-local-exec.json"
    first_executor = build_executor(
        tmp_path,
        invoke_supervisor=supervisor,
        artifact_sink=sink,
        controlled_exec_store=FileControlledLocalExecClaimStore(store_path),
    )

    first = first_executor.execute(step_request(), role_binding=role_binding(), resolved_inputs=())
    restarted_executor = build_executor(
        tmp_path,
        invoke_supervisor=supervisor,
        artifact_sink=sink,
        controlled_exec_store=FileControlledLocalExecClaimStore(store_path),
    )
    second = restarted_executor.execute(
        step_request(), role_binding=role_binding(), resolved_inputs=()
    )

    assert first.ok is True
    assert second.ok is True
    assert supervisor.calls == 1
    assert first.artifact_refs == second.artifact_refs
    assert first.evidence_ref == second.evidence_ref
