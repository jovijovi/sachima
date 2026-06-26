"""P6-B runner-provenance boundary (FR4 — pinned local only, no fetch/launcher).

The bridge builds no runner: provenance is enforced by the unmodified
controlled-exec wall and surfaced as the additive ``p6b_runner_provenance_unverified``
code. A null binary (the committed posture), a digest mismatch, a relative path,
or a fetch-shaped / launcher basename all fail closed before any launch.
"""

from __future__ import annotations

import pytest

from sachima_supervisor.p6b_read_only_real_agent import P6B_RUNNER_PROVENANCE_UNVERIFIED

from .._support import (
    CountingSupervisor,
    build_executor,
    role_binding,
    role_mapping,
    step_request,
)


def _execute(executor):
    return executor.execute(step_request(), role_binding=role_binding(), resolved_inputs=())


def test_null_committed_binary_is_non_runnable(tmp_path):
    supervisor = CountingSupervisor()
    executor = build_executor(
        tmp_path,
        invoke_supervisor=supervisor,
        role_mapping=role_mapping(runner={"acpx_binary": None}),
    )

    outcome = _execute(executor)

    assert outcome.ok is False
    assert outcome.error_code == P6B_RUNNER_PROVENANCE_UNVERIFIED
    assert supervisor.calls == 0


def test_role_file_digest_mismatch_fails_closed(tmp_path):
    supervisor = CountingSupervisor()
    executor = build_executor(
        tmp_path, invoke_supervisor=supervisor, role_file_digest="sha256:" + "0" * 64
    )

    outcome = _execute(executor)

    assert outcome.ok is False
    assert outcome.error_code == P6B_RUNNER_PROVENANCE_UNVERIFIED
    assert supervisor.calls == 0


@pytest.mark.parametrize(
    "binary",
    [
        "relative/acpx",  # not absolute
        "/usr/local/bin/npx",  # fetch-shaped launcher basename
        "/usr/bin/node",  # interpreter launcher basename
        "/opt/with space/acpx",  # whitespace in path
    ],
)
def test_unpinned_or_launcher_binary_fails_closed(tmp_path, binary):
    supervisor = CountingSupervisor()
    executor = build_executor(
        tmp_path,
        invoke_supervisor=supervisor,
        role_mapping=role_mapping(runner={"acpx_binary": binary}),
    )

    outcome = _execute(executor)

    assert outcome.ok is False
    assert outcome.error_code == P6B_RUNNER_PROVENANCE_UNVERIFIED
    assert supervisor.calls == 0
