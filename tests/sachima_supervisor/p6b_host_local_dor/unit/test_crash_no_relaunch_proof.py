"""Crash / restart fail-closed no-relaunch proof (the core P6-B Stage-2 claim).

After a simulated process restart — modeled as a *fresh empty* in-process
``ControlledLocalExecClaimStore`` that has lost all resident claim state — the
P6-B bridge's ``recover``/``query`` by run/step must return a sanitized
``not_found`` with no relaunch, the recover snapshot must carry
``recovery_marker=reattached_no_relaunch``, and the supervisor invoker must never
be called (launch count 0). ``execute`` is never called in the proof; a stale
execute after store loss is reported as not-approved / not-attempted.
"""

from __future__ import annotations

from sachima_supervisor.p6b_host_local_dor import (
    RECOVERY_MARKER_REATTACHED_NO_RELAUNCH,
    assess_p6b_host_local_dor,
    prove_crash_no_relaunch,
)
from sachima_supervisor.p5_temporal import contracts as C

from .._support import build_request


def test_prove_crash_no_relaunch_is_fail_closed():
    proof = prove_crash_no_relaunch()

    assert proof["passed"] is True
    assert proof["query_state"] == "not_found"
    assert proof["recover_state"] == "not_found"
    assert proof["recovery_marker"] == RECOVERY_MARKER_REATTACHED_NO_RELAUNCH
    assert proof["supervisor_launch_count"] == 0
    # The proof never calls execute; a stale execute after store loss is unproven.
    assert proof["execute_after_store_loss"] == "not_approved_not_attempted"


def test_crash_proof_projection_has_no_leak():
    proof = prove_crash_no_relaunch()

    assert C.scan_projection_for_leak(proof) is None


def test_assess_embeds_crash_proof():
    report = assess_p6b_host_local_dor(build_request())

    assert report.crash_proof_status == "pass"
    assert report.crash_proof["recovery_marker"] == RECOVERY_MARKER_REATTACHED_NO_RELAUNCH
    assert report.crash_proof["supervisor_launch_count"] == 0
    assert report.crash_proof["execute_after_store_loss"] == "not_approved_not_attempted"
