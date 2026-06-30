"""S2 — local/offline Activity-boundary → supervisor adapter seam (stage S2).

These tests assert the *seam* by source/contract and offline unit tests with an
injected/fake step body — never a live Worker, never a real agent. They cover:

* default-off / approval-mismatch / missing-dependency → zero seam calls;
* invalid ``ActivityInput`` / malformed refs / write role → fail closed, zero call;
* unsafe material (raw prompt / platform / path / secret marker) → rejected, no leak;
* fake/injected happy path → sanitized ``ActivityOutput`` (claim-check refs only);
* an injected seam that raises a raw-looking exception → stable code, no leak;
* an injected seam that returns unsafe / no output → fail closed;
* identical duplicate → replay without a second fake body call;
* divergent duplicate → fail closed;
* recover / query → reattach sanitized fake state, never relaunch;
* active_run cancel → WATCH / ambiguous (no clean-cancel claim for S2);
* local history projection / serialized bytes pass the no-leak scanners;
* a static forbidden-surface scan over the newly added S2 source.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.s2_supervisor_adapter import (
    S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN,
    ActivitySeamOutcome,
    FakeDeterministicSupervisorSeam,
    S2LocalOfflineSupervisorAdapter,
    SupervisorStepResult,
)

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def _start_request(**over):
    base = dict(
        run_ref="run_s2_demo_0001",
        workflow_ref="tx_s2_demo_0001",
        step_ref="architect",
        attempt_index=1,
        role_keys=("sachima_claude_read_only_reviewer",),
        input_claim_refs=(
            {"ref": "claim_ref_input_0", "digest": _DIGEST_B, "kind": "input", "byte_count": 32},
        ),
        idempotency_material="idem_s2_demo_0001",
    )
    base.update(over)
    return C.build_start_request(**base)


def _activity_input(**over):
    return C.build_activity_input(_start_request(**over))


def _admitted(seam):
    return S2LocalOfflineSupervisorAdapter(
        seam=seam,
        enabled=True,
        approval_token=S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN,
    )


# --------------------------------------------------------------------------- #
# Test doubles for the injected supervisor seam
# --------------------------------------------------------------------------- #
class _TripwireSeam:
    """Any seam call is a contract violation on the not-admitted / fail-closed path."""

    def __init__(self) -> None:
        self.calls = 0

    def run_step(self, activity_input):  # pragma: no cover - must never run
        self.calls += 1
        raise AssertionError("supervisor seam must not be reached")


class _RaisingSeam:
    """A seam whose body raises a raw-looking exception carrying forbidden material."""

    raw = "raw_prompt=SUPER_SECRET_CANARY_42 /home/ecs-user/.ssh/id_rsa\nTraceback (most recent call last)"

    def __init__(self) -> None:
        self.calls = 0

    def run_step(self, activity_input):
        self.calls += 1
        raise RuntimeError(self.raw)


class _UnsafeKindSeam:
    """A seam that returns an artifact ref whose kind is a forbidden marker."""

    def run_step(self, activity_input):
        bad = C.StepArtifactRef(
            artifact_id="p5_artifact_unsafe",
            producer_step_id="architect",
            content_digest=_DIGEST_A,
            artifact_kind="raw_output",
            byte_count=1,
            created_at_ref="created_at_ref_s2_0001",
        )
        return SupervisorStepResult(
            ok=True,
            step_status="completed",
            artifact_ref=bad,
            evidence_ref="p5_evidence_unsafe",
            evidence_digest=_DIGEST_A,
        )


class _NoArtifactSeam:
    """A seam that claims success but produces no single claim-check artifact."""

    def run_step(self, activity_input):
        return SupervisorStepResult(
            ok=True,
            step_status="completed",
            artifact_ref=None,
            evidence_ref="p5_evidence_none",
            evidence_digest=_DIGEST_A,
        )


class _NonStableCodeSeam:
    """A failing seam whose error_code is a raw internal detail (not a stable code)."""

    def run_step(self, activity_input):
        return SupervisorStepResult(
            ok=False,
            step_status="failed_terminal",
            error_code="some_raw_internal_detail_42",
        )


# --------------------------------------------------------------------------- #
# Token
# --------------------------------------------------------------------------- #
def test_token_constant_is_exact_and_encodes_non_approvals():
    token = S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN
    assert token.startswith("approve_agent_run_supervisor_sachima_s2")
    for must in (
        "local_offline",
        "default_off",
        "injected_fake",
        "no_temporal_runtime",
        "no_real_agent",
        "no_write_roles",
        "no_production_config",
        "no_real_delivery",
    ):
        assert must in token, must


# --------------------------------------------------------------------------- #
# Admission — default-off / mismatch / missing dependency → zero seam calls
# --------------------------------------------------------------------------- #
def test_default_off_makes_zero_seam_calls():
    seam = _TripwireSeam()
    adapter = S2LocalOfflineSupervisorAdapter(
        seam=seam, enabled=False, approval_token=S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN
    )
    outcome = adapter.execute(_activity_input())
    assert isinstance(outcome, ActivitySeamOutcome)
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_DISABLED
    assert outcome.output is None
    assert seam.calls == 0
    assert C.scan_projection_for_leak(outcome.to_projection()) is None


def test_approval_mismatch_makes_zero_seam_calls():
    seam = _TripwireSeam()
    adapter = S2LocalOfflineSupervisorAdapter(seam=seam, enabled=True, approval_token="not_the_exact_token")
    outcome = adapter.execute(_activity_input())
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_APPROVAL_MISMATCH
    assert seam.calls == 0


def test_missing_seam_dependency_fails_closed():
    adapter = S2LocalOfflineSupervisorAdapter(
        seam=None, enabled=True, approval_token=S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN
    )
    outcome = adapter.execute(_activity_input())
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_PRECONDITION_UNMET
    assert outcome.output is None


def test_admission_zero_call_on_query_recover_cancel_close():
    seam = _TripwireSeam()
    adapter = S2LocalOfflineSupervisorAdapter(
        seam=seam, enabled=False, approval_token=S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN
    )
    snap_q = adapter.query(run_id="run_s2_demo_0001", step_id="architect")
    snap_r = adapter.recover(run_id="run_s2_demo_0001", step_id="architect")
    cancelled = adapter.cancel(
        run_id="run_s2_demo_0001", step_id="architect", scope="active_run", idempotency_key="idem_cancel_0001"
    )
    closed = adapter.close()
    assert snap_q["state"] == "store_invalid" and snap_q["error_code"] == C.RUNTIME_DISABLED
    assert snap_r["state"] == "store_invalid" and "recovery_marker" not in snap_r
    assert cancelled.ok is False and cancelled.error_code == C.RUNTIME_DISABLED
    assert closed["state"] == "store_invalid" and closed["error_code"] == C.RUNTIME_DISABLED
    assert seam.calls == 0


# --------------------------------------------------------------------------- #
# Validation — invalid input / write role / unsafe material → fail closed
# --------------------------------------------------------------------------- #
def test_invalid_activity_input_type_fails_closed_zero_call():
    seam = _TripwireSeam()
    adapter = _admitted(seam)
    outcome = adapter.execute(object())
    assert outcome.ok is False
    assert outcome.error_code == C.INVALID_START_PAYLOAD
    assert seam.calls == 0


def test_malformed_activity_input_fails_closed_zero_call():
    seam = _TripwireSeam()
    adapter = _admitted(seam)
    # Correct dataclass type but a wrong schema version → invalid, never reaches seam.
    bad = C.ActivityInput(
        schema_version=999,
        run_ref="run_s2_demo_0001",
        step_ref="architect",
        attempt_index=1,
        role_key="sachima_claude_read_only_reviewer",
        input_claim_refs=(),
    )
    outcome = adapter.execute(bad)
    assert outcome.ok is False
    assert outcome.error_code == C.INVALID_START_PAYLOAD
    assert seam.calls == 0


class _ExplodingString:
    def __str__(self):
        raise RuntimeError("raw_prompt=DO_NOT_LEAK /home/ecs-user/private")


def test_malformed_activity_input_with_hostile_stringifier_is_no_throw_zero_call():
    seam = _TripwireSeam()
    adapter = _admitted(seam)
    bad = C.ActivityInput(
        schema_version=C.SCHEMA_VERSION,
        run_ref=_ExplodingString(),  # type: ignore[arg-type]
        step_ref="architect",
        attempt_index=1,
        role_key="sachima_claude_read_only_reviewer",
        input_claim_refs=(),
    )

    outcome = adapter.execute(bad)

    assert outcome.ok is False
    assert outcome.error_code == C.INVALID_START_PAYLOAD
    assert seam.calls == 0
    rendered = repr(outcome.to_projection()) + repr(adapter.history_projection())
    assert "DO_NOT_LEAK" not in rendered
    assert "raw_prompt" not in rendered
    assert "/home/ecs-user/private" not in rendered
    assert C.scan_projection_for_leak(outcome.to_projection()) is None
    assert C.scan_projection_for_leak(adapter.history_projection()) is None


def test_write_capable_role_key_rejected_zero_call():
    seam = _TripwireSeam()
    adapter = _admitted(seam)
    # A write-capable role must never run a read-only-first S2 step.
    bad = C.ActivityInput(
        schema_version=C.SCHEMA_VERSION,
        run_ref="run_s2_demo_0001",
        step_ref="architect",
        attempt_index=1,
        role_key="sachima_claude_writer_role",
        input_claim_refs=(),
    )
    outcome = adapter.execute(bad)
    assert outcome.ok is False
    assert outcome.error_code in C.STABLE_CODES
    assert seam.calls == 0


@pytest.mark.parametrize(
    "run_ref",
    ["/home/ecs-user/secret_key_material", "post" + "gres://user:pw@host/db"],
    ids=["private_path", "connection_string"],
)
def test_unsafe_material_marker_rejected_and_no_leak(run_ref):
    seam = _TripwireSeam()
    adapter = _admitted(seam)
    unsafe = C.ActivityInput(
        schema_version=C.SCHEMA_VERSION,
        run_ref=run_ref,
        step_ref="architect",
        attempt_index=1,
        role_key="sachima_claude_read_only_reviewer",
        input_claim_refs=(),
    )
    outcome = adapter.execute(unsafe)
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_UNSAFE_MATERIAL
    assert seam.calls == 0
    # The rejected outcome projection and the local history must not echo the marker.
    assert C.scan_projection_for_leak(outcome.to_projection()) is None
    assert C.scan_projection_for_leak(adapter.history_projection()) is None
    assert C.scan_bytes_for_leak(adapter.serialized_history_bytes()) is None


def test_unsafe_claim_ref_rejected_and_no_leak():
    seam = _TripwireSeam()
    adapter = _admitted(seam)
    unsafe = C.ActivityInput(
        schema_version=C.SCHEMA_VERSION,
        run_ref="run_s2_demo_0001",
        step_ref="architect",
        attempt_index=1,
        role_key="sachima_claude_read_only_reviewer",
        input_claim_refs=(
            C.ClaimCheckRef(ref="api_key_leaked", digest=_DIGEST_A, kind="input", byte_count=1),
        ),
    )
    outcome = adapter.execute(unsafe)
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_UNSAFE_MATERIAL
    assert seam.calls == 0
    assert C.scan_projection_for_leak(outcome.to_projection()) is None


# --------------------------------------------------------------------------- #
# Happy path — fake/injected seam → sanitized ActivityOutput (no raw bytes)
# --------------------------------------------------------------------------- #
def test_happy_path_returns_sanitized_activity_output():
    seam = FakeDeterministicSupervisorSeam()
    adapter = _admitted(seam)
    outcome = adapter.execute(_activity_input())
    assert outcome.ok is True
    assert outcome.error_code is None
    assert seam.calls == 1
    out = outcome.output
    assert isinstance(out, C.ActivityOutput)
    # Sanitized: validates as a controlled activity output (one artifact ref, refs/digests only).
    C.validate_activity_output(out)
    assert out.status == "completed"
    assert isinstance(out.artifact_ref, C.StepArtifactRef)
    assert C._SHA256_DIGEST_RE.fullmatch(out.artifact_ref.content_digest)
    assert C._SHA256_DIGEST_RE.fullmatch(out.evidence_digest)
    # No business verdict is carried anywhere.
    assert not hasattr(out, "business_verdict")
    assert not hasattr(outcome, "business_verdict")
    # The returned projection carries refs/digests/codes only and passes the scan.
    assert C.scan_projection_for_leak(outcome.to_projection()) is None


def test_happy_path_equivalent_to_controlled_deterministic_body():
    # The default fake seam must reproduce the controlled-deterministic artifact, so the
    # seam is a faithful drop-in for the current activity body.
    seam = FakeDeterministicSupervisorSeam()
    adapter = _admitted(seam)
    activity_input = _activity_input()
    outcome = adapter.execute(activity_input)
    reference = C.build_activity_output(activity_input)
    assert outcome.output == reference


# --------------------------------------------------------------------------- #
# Injected seam raises a raw-looking exception → stable code, no leak
# --------------------------------------------------------------------------- #
def test_injected_seam_raw_exception_collapses_to_stable_code_no_leak():
    seam = _RaisingSeam()
    adapter = _admitted(seam)
    outcome = adapter.execute(_activity_input())
    assert outcome.ok is False
    assert outcome.error_code in C.STABLE_CODES
    assert outcome.error_code == C.RUNTIME_ERROR
    assert outcome.output is None
    # The raw exception text / canary / path / traceback must not surface anywhere.
    projection = outcome.to_projection()
    rendered = repr(projection) + repr(adapter.history_projection())
    assert "SUPER_SECRET_CANARY_42" not in rendered
    assert "raw_prompt" not in rendered
    assert "id_rsa" not in rendered
    assert "Traceback" not in rendered
    assert C.scan_projection_for_leak(projection) is None
    assert C.scan_projection_for_leak(adapter.history_projection()) is None
    assert C.scan_bytes_for_leak(adapter.serialized_history_bytes(), canaries=("super_secret_canary_42",)) is None


# --------------------------------------------------------------------------- #
# Injected seam returns unsafe / no output → fail closed
# --------------------------------------------------------------------------- #
def test_seam_unsafe_artifact_kind_fails_closed():
    adapter = _admitted(_UnsafeKindSeam())
    outcome = adapter.execute(_activity_input())
    assert outcome.ok is False
    assert outcome.error_code in {C.RUNTIME_UNSAFE_MATERIAL, C.RUNTIME_HISTORY_LEAK_DETECTED}
    assert outcome.output is None
    assert C.scan_projection_for_leak(outcome.to_projection()) is None


def test_seam_no_single_artifact_fails_closed():
    adapter = _admitted(_NoArtifactSeam())
    outcome = adapter.execute(_activity_input())
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_UNSAFE_MATERIAL
    assert outcome.output is None


def test_seam_non_stable_error_code_collapses():
    adapter = _admitted(_NonStableCodeSeam())
    outcome = adapter.execute(_activity_input())
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_ERROR
    assert C.scan_projection_for_leak(outcome.to_projection()) is None


# --------------------------------------------------------------------------- #
# Duplicate / recover / no-relaunch fake semantics
# --------------------------------------------------------------------------- #
def test_identical_duplicate_replays_without_second_seam_call():
    seam = FakeDeterministicSupervisorSeam()
    adapter = _admitted(seam)
    out1 = adapter.execute(_activity_input())
    out2 = adapter.execute(_activity_input())
    assert out1.ok is True and out2.ok is True
    # The fake body ran exactly once; the duplicate reconciled / replayed.
    assert seam.calls == 1
    assert out2.replayed is True
    assert out1.output == out2.output


def test_divergent_duplicate_fails_closed():
    seam = FakeDeterministicSupervisorSeam()
    adapter = _admitted(seam)
    first = adapter.execute(_activity_input())
    assert first.ok is True
    diverged = adapter.execute(
        _activity_input(
            input_claim_refs=(
                {"ref": "claim_ref_input_9", "digest": _DIGEST_C, "kind": "input", "byte_count": 64},
            )
        )
    )
    assert diverged.ok is False
    assert diverged.error_code == C.RUNTIME_IDEMPOTENCY_CONFLICT
    # No second body call on the divergent path.
    assert seam.calls == 1


def test_recover_reattaches_resident_state_without_relaunch():
    seam = FakeDeterministicSupervisorSeam()
    adapter = _admitted(seam)
    adapter.execute(_activity_input())
    recovered = adapter.recover(run_id="run_s2_demo_0001", step_id="architect")
    assert recovered["state"] == "completed"
    assert recovered["recovery_marker"] == "reattached_no_relaunch"
    assert len(recovered["artifact_refs"]) == 1
    # Recover queries resident state only — it never re-runs the fake body.
    assert seam.calls == 1
    assert C.scan_projection_for_leak(recovered) is None


def test_recover_unknown_run_is_not_found_without_relaunch():
    seam = _TripwireSeam()
    adapter = _admitted(seam)
    recovered = adapter.recover(run_id="run_unknown_0009", step_id="architect")
    assert recovered["state"] == "not_found"
    assert recovered["error_code"] == C.RUNTIME_NOT_FOUND
    assert seam.calls == 0


def test_query_recover_cancel_with_hostile_stringifier_are_no_throw_no_leak():
    seam = _TripwireSeam()
    adapter = _admitted(seam)

    query = adapter.query(run_id=_ExplodingString(), step_id="architect")  # type: ignore[arg-type]
    recover = adapter.recover(run_id=_ExplodingString(), step_id="architect")  # type: ignore[arg-type]
    cancel = adapter.cancel(
        run_id=_ExplodingString(),  # type: ignore[arg-type]
        step_id="architect",
        scope="active_run",
        idempotency_key="idem_cancel_hostile",
    )

    assert query["state"] == "not_found"
    assert recover["state"] == "not_found"
    assert cancel.ok is False and cancel.error_code == C.ACTIVE_RUN_CANCELLATION_WATCH
    assert seam.calls == 0
    rendered = repr(query) + repr(recover) + repr(cancel.to_projection()) + repr(adapter.history_projection())
    assert "DO_NOT_LEAK" not in rendered
    assert "raw_prompt" not in rendered
    assert "/home/ecs-user/private" not in rendered
    assert C.scan_projection_for_leak(adapter.history_projection()) is None


def test_query_returns_resident_state_or_not_found():
    seam = FakeDeterministicSupervisorSeam()
    adapter = _admitted(seam)
    adapter.execute(_activity_input())
    snap = adapter.query(run_id="run_s2_demo_0001", step_id="architect")
    assert snap["state"] == "completed"
    assert len(snap["artifact_refs"]) == 1
    unknown = adapter.query(run_id="run_unknown_0009", step_id="architect")
    assert unknown["state"] == "not_found"
    assert seam.calls == 1


def test_cross_instance_shared_store_does_not_relaunch():
    store: dict = {}
    seam_a = FakeDeterministicSupervisorSeam()
    adapter_a = S2LocalOfflineSupervisorAdapter(
        seam=seam_a, enabled=True, approval_token=S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN, claim_store=store
    )
    first = adapter_a.execute(_activity_input())
    assert first.ok is True and seam_a.calls == 1
    # A recreated wrapper over the same caller-owned store must replay, never relaunch.
    tripwire = _TripwireSeam()
    adapter_b = S2LocalOfflineSupervisorAdapter(
        seam=tripwire, enabled=True, approval_token=S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN, claim_store=store
    )
    second = adapter_b.execute(_activity_input())
    assert second.ok is True
    assert second.replayed is True
    assert tripwire.calls == 0


# --------------------------------------------------------------------------- #
# Cancellation — active_run WATCH / ambiguous (no clean-cancel claim for S2)
# --------------------------------------------------------------------------- #
def test_active_run_cancel_is_watch_ambiguous():
    seam = FakeDeterministicSupervisorSeam()
    adapter = _admitted(seam)
    adapter.execute(_activity_input())
    watch = adapter.cancel(
        run_id="run_s2_demo_0001",
        step_id="architect",
        scope="active_run",
        idempotency_key="idem_cancel_0001",
        interrupt_outcome=None,
    )
    assert watch.ok is False
    assert watch.ambiguous is True
    assert watch.step_status == C.CANCEL_AMBIGUOUS
    assert watch.error_code == C.ACTIVE_RUN_CANCELLATION_WATCH


def test_unsupported_cancel_scope_fails_closed():
    adapter = _admitted(FakeDeterministicSupervisorSeam())
    rejected = adapter.cancel(
        run_id="run_s2_demo_0001",
        step_id="architect",
        scope="between_step",
        idempotency_key="idem_cancel_0002",
    )
    assert rejected.ok is False
    assert rejected.error_code == C.RUNTIME_CANCEL_SCOPE_UNSUPPORTED


def test_cancel_passes_through_proven_lower_layer_interrupt_only():
    # The single carve-out: a proven interrupted + cleanup_verified lower-layer outcome
    # may be reflected; the adapter never manufactures a clean cancel itself.
    adapter = _admitted(FakeDeterministicSupervisorSeam())
    proven = SupervisorStepResult(
        ok=True, step_status="cancelled", interrupted=True, cleanup_verified=True
    )
    confirmed = adapter.cancel(
        run_id="run_s2_demo_0001",
        step_id="architect",
        scope="active_run",
        idempotency_key="idem_cancel_0003",
        interrupt_outcome=proven,
    )
    assert confirmed.ok is True
    assert confirmed.step_status == "cancelled"
    assert confirmed.interrupted is True and confirmed.cleanup_verified is True
    # An *unproven* interrupt outcome must stay a WATCH.
    unproven = SupervisorStepResult(ok=True, step_status="cancelled", interrupted=True, cleanup_verified=False)
    still_watch = adapter.cancel(
        run_id="run_s2_demo_0001",
        step_id="architect",
        scope="active_run",
        idempotency_key="idem_cancel_0004",
        interrupt_outcome=unproven,
    )
    assert still_watch.ok is False
    assert still_watch.ambiguous is True


# --------------------------------------------------------------------------- #
# History / close no-leak surfaces
# --------------------------------------------------------------------------- #
def test_close_returns_sanitized_marker():
    adapter = _admitted(FakeDeterministicSupervisorSeam())
    adapter.execute(_activity_input())
    closed = adapter.close()
    assert closed["state"] == "closed"
    assert C.scan_projection_for_leak(closed) is None


def test_history_projection_and_bytes_are_sanitized_after_mixed_ops():
    adapter = _admitted(FakeDeterministicSupervisorSeam())
    adapter.execute(_activity_input())
    adapter.execute(_activity_input())  # duplicate replay
    adapter.recover(run_id="run_s2_demo_0001", step_id="architect")
    adapter.cancel(
        run_id="run_s2_demo_0001", step_id="architect", scope="active_run", idempotency_key="idem_cancel_0005"
    )
    projection = adapter.history_projection()
    assert isinstance(projection, dict)
    assert C.scan_projection_for_leak(projection) is None
    raw = adapter.serialized_history_bytes()
    assert isinstance(raw, bytes)
    assert C.scan_bytes_for_leak(raw) is None


# --------------------------------------------------------------------------- #
# Static forbidden-surface scan over the newly added S2 source (merge-blocking)
# --------------------------------------------------------------------------- #
def _s2_source() -> str:
    import sachima_supervisor.p5_temporal.s2_supervisor_adapter as mod

    return pathlib.Path(mod.__file__).read_text(encoding="utf-8")


#: Lifecycle / runtime / real-agent / external-surface patterns that must never
#: appear in the local/offline S2 adapter source.
_FORBIDDEN_SURFACE = {
    "temporalio": re.compile(r"\btemporalio\b"),
    "temporal_worker": re.compile(r"\bWorker\b"),
    "client_connect": re.compile(r"Client\.connect"),
    "workflow_environment": re.compile(r"WorkflowEnvironment"),
    "start_workflow": re.compile(r"start_workflow"),
    "get_workflow_handle": re.compile(r"get_workflow_handle"),
    "execute_update": re.compile(r"execute_update"),
    "subprocess": re.compile(r"\bsubprocess\b"),
    "os_system": re.compile(r"os\.system"),
    "popen": re.compile(r"[Pp]open"),
    "socket": re.compile(r"\bsocket\b"),
    "http_server": re.compile(r"(HTTPServer|http\.server|socketserver)"),
    "dynamic_import": re.compile(r"(\bimportlib\b|__import__)"),
    "acpx": re.compile(r"\bac" r"px\b"),
    "npx": re.compile(r"\bn" r"px\b"),
    "codex": re.compile(r"\bcodex\b"),
    "claude_runner": re.compile(r"\bclaude\b", re.IGNORECASE),
    "gateway": re.compile(r"gate" r"way", re.IGNORECASE),
    "feishu": re.compile(r"fei" r"shu", re.IGNORECASE),
    "lark": re.compile(r"\blark\b", re.IGNORECASE),
    "live_word": re.compile(r"\blive\b", re.IGNORECASE),
    "send_word": re.compile(r"\bsend\b", re.IGNORECASE),
}


def test_forbidden_surface_detector_has_teeth():
    # Guard against a vacuously-passing scan.
    assert _FORBIDDEN_SURFACE["subprocess"].search("import subprocess")
    assert _FORBIDDEN_SURFACE["temporal_worker"].search("worker = Worker(client)")
    assert _FORBIDDEN_SURFACE["client_connect"].search("await Client.connect('localhost:7233')")


def test_s2_source_has_no_forbidden_runtime_or_agent_surface():
    src = _s2_source()
    hits = [name for name, pattern in _FORBIDDEN_SURFACE.items() if pattern.search(src)]
    assert not hits, "S2 adapter source must not reference forbidden surfaces: " + ", ".join(sorted(hits))


def test_s2_source_imports_are_local_offline_only():
    src = _s2_source()
    import_lines = [
        line.strip()
        for line in src.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    # Only pure local/offline imports are allowed (stdlib + the sanitized contracts).
    allowed_substrings = (
        "from __future__",
        "import dataclasses",
        "from dataclasses",
        "import hashlib",
        "import json",
        "import re",
        "import threading",
        "from collections",
        "from typing",
        "from . import contracts",
        "from .contracts",
    )
    offending = [line for line in import_lines if not any(s in line for s in allowed_substrings)]
    assert not offending, "S2 adapter must import local/offline only:\n" + "\n".join(offending)
