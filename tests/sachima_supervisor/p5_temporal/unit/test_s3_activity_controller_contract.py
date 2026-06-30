"""S3 — hermetic-local Temporal Activity body + caller-owned controller contract.

RED contract tests for the *future* ``s3_activity_controller`` module (it does not
exist yet — importing it is the intended failing/erroring state). They pin, by
offline unit test and against the already-merged S2 local/offline supervisor
adapter seam, the calling relationship the S3 design packet fixes
(``docs/plans/2026-06-30-sachima-s3-activity-controller-design-packet.md``):

* the async Activity *body* wraps ``S2LocalOfflineSupervisorAdapter`` and returns a
  sanitized ``ActivityOutput`` on the happy path, with exactly one fake seam call;
* body admission (default-off / token-mismatch / missing-seam) fails closed with a
  stable code and **zero** seam calls — a raise carries only a stable code, no raw;
* the caller-owned *controller* maps an intent class to a read-only role key from a
  closed allowlist, and unknown / platform-derived / write-ish intents fail closed
  **before** any control-surface/runtime call;
* the controller drives a recording fake control surface: start builds one
  sanitized ``StartRequest``; query/recover/close are no-throw; update is pinned to
  ``{resume, request_cancel}`` and rejects delivery/approve/reject;
* duplicate / divergent / pre-claim recover semantics hold through the S3 body over
  a shared adapter claim store, never a second fake seam call;
* clean local history projection / serialized bytes pass the SCAN 1 / SCAN 2
  scanners, while planted ``raw_prompt`` / ``card_json`` / ``oc_`` / canary material
  is detected by the existing contracts scanners.

This module starts no Temporal runtime/Worker/service, runs no real agent, and
reaches no Gateway/Feishu/live/delivery surface — it is pure local/offline Python.
"""

from __future__ import annotations

import asyncio

import pytest

from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.s2_supervisor_adapter import (
    S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN,
    ActivitySeamOutcome,
    FakeDeterministicSupervisorSeam,
    S2LocalOfflineSupervisorAdapter,
)

# Future module under contract — RED: it is not implemented yet, so importing it
# here makes the whole file error/fail until the S3 source lands.
from sachima_supervisor.p5_temporal.s3_activity_controller import (
    INTENT_CLASS_TO_ROLE_KEY,
    S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN,
    S3SupervisorActivityBody,
    S3TemporalActivityController,
)

_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def _start_request(**over):
    base = dict(
        run_ref="run_s3_demo_0001",
        workflow_ref="tx_s3_demo_0001",
        step_ref="architect",
        attempt_index=1,
        role_keys=("sachima_claude_read_only_reviewer",),
        input_claim_refs=(
            {"ref": "claim_ref_input_0", "digest": _DIGEST_B, "kind": "input", "byte_count": 32},
        ),
        idempotency_material="idem_s3_demo_0001",
    )
    base.update(over)
    return C.build_start_request(**base)


def _activity_input(**over):
    return C.build_activity_input(_start_request(**over))


def _start_kwargs(**over):
    base = dict(
        run_ref="run_s3_demo_0001",
        workflow_ref="tx_s3_demo_0001",
        step_ref="architect",
        attempt_index=1,
        input_claim_refs=(
            {"ref": "claim_ref_input_0", "digest": _DIGEST_B, "kind": "input", "byte_count": 32},
        ),
        idempotency_material="idem_s3_demo_0001",
    )
    base.update(over)
    return base


def _admitted_adapter(seam, *, claim_store=None):
    return S2LocalOfflineSupervisorAdapter(
        seam=seam,
        enabled=True,
        approval_token=S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN,
        claim_store=claim_store,
    )


def _admitted_body(adapter):
    return S3SupervisorActivityBody(
        adapter=adapter,
        enabled=True,
        approval_token=S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN,
    )


def _output_projection(output) -> dict:
    """A scan-able dict projection of an ``ActivityOutput`` using public contracts."""

    return {
        "schema_version": output.schema_version,
        "status": output.status,
        "artifact_ref": C.step_artifact_ref_projection(output.artifact_ref),
        "evidence_ref": output.evidence_ref,
        "evidence_digest": output.evidence_digest,
    }


def _reject_code(body, activity_input) -> str:
    """Drive an async ``body.run`` that must fail closed and return its stable code.

    Accepts either the Temporal activity-failure idiom (``run`` raises an exception
    whose string is *only* a stable code) or a sanitized non-output return carrying
    a stable ``error_code`` — never a successful ``ActivityOutput`` and never any raw
    marker.
    """

    try:
        result = asyncio.run(body.run(activity_input))
    except BaseException as exc:  # noqa: BLE001 - probing the no-leak failure boundary
        typed_code = getattr(exc, "type", None)
        if typed_code in C.STABLE_CODES:
            assert getattr(exc, "non_retryable", True) is True
            assert C.scan_projection_for_leak({"error": typed_code}) is None
            return typed_code
        message = str(exc)
        assert message in C.STABLE_CODES, f"exception must be a bare stable code: {message!r}"
        assert C.scan_projection_for_leak({"error": message}) is None
        return message
    assert type(result) is not C.ActivityOutput
    code = result if isinstance(result, str) else getattr(result, "error_code", None)
    if code is None and isinstance(result, dict):
        code = result.get("error_code")
    assert code in C.STABLE_CODES
    assert C.scan_projection_for_leak({"error": code}) is None
    return code


# --------------------------------------------------------------------------- #
# Recording fake control surface (records calls; starts no runtime)
# --------------------------------------------------------------------------- #
class _FakeControlSurface:
    """Sanitized no-throw control surface double that records the controller's calls.

    Mirrors the merged ``P5TemporalControlSurface`` envelope shape. The controller
    routes every pinned update (``resume`` + ``request_cancel``) through ``update``;
    a non-pinned event must be rejected by the controller *before* reaching here.
    """

    def __init__(self) -> None:
        self.start_calls = 0
        self.query_calls = 0
        self.recover_calls = 0
        self.update_calls = 0
        self.close_calls = 0
        self.start_args: list[tuple] = []
        self.update_args: list[tuple] = []

    @staticmethod
    def _ok(op: str, *, workflow_id=None, snapshot=None) -> dict:
        return {
            "ok": True,
            "op": op,
            "workflow_id": workflow_id,
            "snapshot": snapshot,
            "error_code": None,
            "replayed": False,
        }

    async def start(self, start_request, *, workflow_id) -> dict:
        self.start_calls += 1
        self.start_args.append((start_request, workflow_id))
        return self._ok("start", workflow_id=workflow_id)

    async def query(self, *, workflow_id) -> dict:
        self.query_calls += 1
        return self._ok("query", workflow_id=workflow_id)

    async def recover(self, *, workflow_id) -> dict:
        self.recover_calls += 1
        return self._ok("recover", workflow_id=workflow_id)

    async def update(self, *, workflow_id, update) -> dict:
        self.update_calls += 1
        self.update_args.append((workflow_id, update))
        return self._ok("update", workflow_id=workflow_id)

    async def close(self) -> dict:
        self.close_calls += 1
        return self._ok("close")


# --------------------------------------------------------------------------- #
# 1) Async Activity body wraps the S2 adapter (happy path)
# --------------------------------------------------------------------------- #
def test_body_happy_path_returns_sanitized_activity_output():
    seam = FakeDeterministicSupervisorSeam()
    body = _admitted_body(_admitted_adapter(seam))

    out = asyncio.run(body.run(_activity_input()))

    assert seam.calls == 1
    assert type(out) is C.ActivityOutput
    C.validate_activity_output(out)
    assert out.status == "completed"
    assert C.scan_projection_for_leak(_output_projection(out)) is None


def test_body_run_is_registered_as_the_temporal_step_activity():
    definition = getattr(S3SupervisorActivityBody.run, "__temporal_activity_definition", None)
    assert definition is not None
    # StepWorkflow schedules this name; an ops-owned S3 Worker can register the
    # injected S3 body without changing workflow history semantics.
    assert definition.name == "p5_step_activity"
    assert definition.is_async is True


class _RogueAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, activity_input):  # pragma: no cover - must never be called
        self.calls += 1
        return ActivitySeamOutcome(
            ok=True,
            op="execute",
            output=C.build_activity_output(activity_input),
            step_status="completed",
        )


def test_body_requires_the_merged_s2_adapter_type_before_execute():
    rogue = _RogueAdapter()
    body = S3SupervisorActivityBody(
        adapter=rogue,
        enabled=True,
        approval_token=S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN,
    )

    assert _reject_code(body, _activity_input()) == C.RUNTIME_PRECONDITION_UNMET
    assert rogue.calls == 0


def test_body_revalidates_and_scans_adapter_output_before_temporal_return(monkeypatch):
    adapter = _admitted_adapter(FakeDeterministicSupervisorSeam())
    body = _admitted_body(adapter)
    bad_output = C.ActivityOutput(
        schema_version=C.SCHEMA_VERSION,
        status="completed",
        artifact_ref=C.build_step_artifact_ref("run_s3_demo_0001", "architect", 1, "sachima_claude_read_only_reviewer"),
        evidence_ref="raw_prompt_ref",
        evidence_digest="sha256:" + "d" * 64,
    )

    def _bad_execute(activity_input):
        return ActivitySeamOutcome(ok=True, op="execute", output=bad_output, step_status="completed")

    monkeypatch.setattr(adapter, "execute", _bad_execute)

    assert _reject_code(body, _activity_input()) == C.RUNTIME_HISTORY_LEAK_DETECTED


# --------------------------------------------------------------------------- #
# 2) Body admission — default-off / token-mismatch / missing-seam fail closed
# --------------------------------------------------------------------------- #
def test_body_default_off_rejects_with_zero_seam_calls():
    seam = FakeDeterministicSupervisorSeam()
    body = S3SupervisorActivityBody(
        adapter=_admitted_adapter(seam),
        enabled=False,
        approval_token=S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN,
    )
    assert _reject_code(body, _activity_input()) == C.RUNTIME_DISABLED
    assert seam.calls == 0


def test_body_token_mismatch_rejects_with_zero_seam_calls():
    seam = FakeDeterministicSupervisorSeam()
    body = S3SupervisorActivityBody(
        adapter=_admitted_adapter(seam),
        enabled=True,
        approval_token="not_the_exact_s3_token",
    )
    assert _reject_code(body, _activity_input()) == C.RUNTIME_APPROVAL_MISMATCH
    assert seam.calls == 0


def test_body_missing_seam_rejects_precondition_unmet():
    # The injected adapter has no seam: an admitted body still fails closed with a
    # stable code and never fabricates a success.
    adapter = S2LocalOfflineSupervisorAdapter(
        seam=None, enabled=True, approval_token=S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN
    )
    body = _admitted_body(adapter)
    assert _reject_code(body, _activity_input()) == C.RUNTIME_PRECONDITION_UNMET


# --------------------------------------------------------------------------- #
# 3) Controller intent-class → role-key closed allowlist (fail closed)
# --------------------------------------------------------------------------- #
def test_intent_class_allowlist_has_known_read_only_roles():
    known = ("architecture_packet", "programmer_candidate_review", "blocker_review")
    for intent in known:
        assert intent in INTENT_CLASS_TO_ROLE_KEY
        role_key = INTENT_CLASS_TO_ROLE_KEY[intent]
        # Every allowlisted role key must be a valid read-only role key — building a
        # StartRequest with it exercises `_safe_role_key` (no write/deliver/approve/
        # reject/mutate markers, bare-id shape).
        request = _start_request(role_keys=(role_key,))
        assert request.role_keys[0] == role_key


@pytest.mark.parametrize(
    "intent",
    [
        "unknown_intent_class",
        "oc_abc",
        "feishu_admin",
        "deliver_blocker_review",
        "write_architecture_packet",
    ],
    ids=["unknown", "platform_oc", "platform_feishu", "write_deliver", "write_write"],
)
def test_controller_start_fails_closed_before_surface_call(intent):
    surface = _FakeControlSurface()
    controller = S3TemporalActivityController(control_surface=surface)

    result = asyncio.run(controller.start(intent_class=intent, **_start_kwargs()))

    assert result["ok"] is False
    assert result["error_code"] in {C.INVALID_START_PAYLOAD, C.RUNTIME_UNSAFE_MATERIAL}
    # No control-surface / runtime call happens before role resolution fails closed.
    assert surface.start_calls == 0
    # The rejected envelope never echoes the raw/platform/write intent material.
    assert C.scan_projection_for_leak(result) is None


# --------------------------------------------------------------------------- #
# 4) Controller drives the recording fake control surface
# --------------------------------------------------------------------------- #
def test_controller_start_builds_sanitized_start_request_and_calls_start_once():
    surface = _FakeControlSurface()
    controller = S3TemporalActivityController(control_surface=surface)

    result = asyncio.run(controller.start(intent_class="architecture_packet", **_start_kwargs()))

    assert result["ok"] is True
    assert surface.start_calls == 1
    sent_request, sent_workflow_id = surface.start_args[0]
    # The controller handed the surface a sanitized StartRequest + the deterministic id.
    C.validate_start_request(sent_request)
    assert sent_request.role_keys[0] == INTENT_CLASS_TO_ROLE_KEY["architecture_packet"]
    assert sent_workflow_id == C.deterministic_workflow_id(sent_request)
    assert C.scan_projection_for_leak(result) is None


def test_controller_query_recover_close_are_no_throw():
    surface = _FakeControlSurface()
    controller = S3TemporalActivityController(control_surface=surface)

    queried = asyncio.run(controller.query(run_ref="run_s3_demo_0001", step_ref="architect"))
    recovered = asyncio.run(controller.recover(run_ref="run_s3_demo_0001", step_ref="architect"))
    closed = asyncio.run(controller.close())

    assert queried["ok"] is True and surface.query_calls == 1
    assert recovered["ok"] is True and surface.recover_calls == 1
    assert closed["ok"] is True and surface.close_calls == 1
    for envelope in (queried, recovered, closed):
        assert C.scan_projection_for_leak(envelope) is None


def test_controller_query_is_no_throw_on_raw_ref_without_surface_call():
    surface = _FakeControlSurface()
    controller = S3TemporalActivityController(control_surface=surface)

    result = asyncio.run(controller.query(run_ref="/home/ecs-user/private", step_ref="architect"))

    assert result["ok"] is False
    assert result["error_code"] in C.STABLE_CODES
    assert surface.query_calls == 0
    assert C.scan_projection_for_leak(result) is None


class _SyncRawRaisingSurface:
    def __getattr__(self, name):
        def _raise(*args, **kwargs):
            raise RuntimeError("raw_prompt=DO_NOT_LEAK card_json oc_abc")
        return _raise


def test_controller_missing_or_sync_raising_surface_is_no_throw_no_leak():
    clean_kwargs = _start_kwargs()
    none_controller = S3TemporalActivityController(control_surface=None)
    raw_controller = S3TemporalActivityController(control_surface=_SyncRawRaisingSurface())

    probes = [
        none_controller.start(intent_class="architecture_packet", **clean_kwargs),
        none_controller.query(run_ref="run_s3_demo_0001", step_ref="architect"),
        raw_controller.start(intent_class="architecture_packet", **clean_kwargs),
        raw_controller.query(run_ref="run_s3_demo_0001", step_ref="architect"),
        raw_controller.update(
            run_ref="run_s3_demo_0001", step_ref="architect", event_key="evt_s3_raw_0001", event_type="resume"
        ),
        raw_controller.recover(run_ref="run_s3_demo_0001", step_ref="architect"),
        raw_controller.close(),
    ]

    for probe in probes:
        result = asyncio.run(probe)
        assert result["ok"] is False
        assert result["error_code"] == C.RUNTIME_ERROR
        assert C.scan_projection_for_leak(result) is None


@pytest.mark.parametrize(
    "event_type,accepted",
    [
        ("resume", True),
        ("request_cancel", True),
        ("delivery", False),
        ("approve", False),
        ("reject", False),
    ],
)
def test_controller_update_pins_resume_and_request_cancel(event_type, accepted):
    surface = _FakeControlSurface()
    controller = S3TemporalActivityController(control_surface=surface)

    result = asyncio.run(
        controller.update(
            run_ref="run_s3_demo_0001",
            step_ref="architect",
            event_key="evt_s3_0001",
            event_type=event_type,
        )
    )

    if accepted:
        assert result["ok"] is True
        assert surface.update_calls == 1
        _, sent_update = surface.update_args[0]
        C.validate_update_payload(sent_update)
        assert sent_update.event_type == event_type
    else:
        assert result["ok"] is False
        assert result["error_code"] in C.STABLE_CODES
        # Off-list events (delivery/approve/reject) are rejected before the surface.
        assert surface.update_calls == 0
    assert C.scan_projection_for_leak(result) is None


# --------------------------------------------------------------------------- #
# 5) Duplicate / divergent / pre-claim recover through a shared adapter store
# --------------------------------------------------------------------------- #
def test_duplicate_divergent_preclaim_recover_through_shared_store():
    store: dict = {}
    seam = FakeDeterministicSupervisorSeam()
    adapter = _admitted_adapter(seam, claim_store=store)
    body = _admitted_body(adapter)

    # Identical duplicate → replay the resident outcome, no second fake seam call.
    first = asyncio.run(body.run(_activity_input()))
    second = asyncio.run(body.run(_activity_input()))
    assert type(first) is C.ActivityOutput and type(second) is C.ActivityOutput
    assert first == second
    assert seam.calls == 1

    # Divergent duplicate (same key, different fingerprint) → conflict, no relaunch.
    divergent_code = _reject_code(
        body,
        _activity_input(
            input_claim_refs=(
                {"ref": "claim_ref_input_9", "digest": _DIGEST_C, "kind": "input", "byte_count": 64},
            )
        ),
    )
    assert divergent_code == C.RUNTIME_IDEMPOTENCY_CONFLICT
    assert seam.calls == 1

    # Pre-claim crash window: the claim is written before delegation, so a recover
    # over the same shared store reattaches + WATCHes (running) without a seam call.
    calls_before = seam.calls
    key = C.workflow_id_from_refs("run_s3_preclaim_0001", "architect")
    store[key] = {
        "fingerprint": "sha256:" + "d" * 64,
        "run_ref": "run_s3_preclaim_0001",
        "step_ref": "architect",
    }
    recovered = adapter.recover(run_id="run_s3_preclaim_0001", step_id="architect")
    assert recovered["state"] == "running"
    assert recovered["recovery_marker"] == "reattached_no_relaunch"
    assert seam.calls == calls_before
    assert C.scan_projection_for_leak(recovered) is None


# --------------------------------------------------------------------------- #
# 6) No-leak scans — clean path passes; planted markers/canary are detected
# --------------------------------------------------------------------------- #
def test_history_scan_clean_then_detects_planted_markers_and_canary():
    seam = FakeDeterministicSupervisorSeam()
    adapter = _admitted_adapter(seam)
    body = _admitted_body(adapter)
    asyncio.run(body.run(_activity_input()))

    # Clean local history projection (SCAN 1) and serialized bytes (SCAN 2) pass.
    assert C.scan_projection_for_leak(adapter.history_projection()) is None
    clean_bytes = adapter.serialized_history_bytes()
    assert isinstance(clean_bytes, bytes)
    assert C.scan_bytes_for_leak(clean_bytes) is None
    assert C.scan_bytes_for_leak(clean_bytes, canaries=("super_secret_canary_42",)) is None

    # The existing contracts scanners have teeth against planted raw/platform material.
    assert C.scan_projection_for_leak({"x": "raw_prompt body"}) == C.RUNTIME_HISTORY_LEAK_DETECTED
    assert C.scan_projection_for_leak({"card_json": "{}"}) == C.RUNTIME_HISTORY_LEAK_DETECTED
    assert C.scan_projection_for_leak({"sender": "oc_abc123"}) == C.RUNTIME_HISTORY_LEAK_DETECTED
    assert C.scan_bytes_for_leak(b'{"k": "raw_prompt body"}') == C.RUNTIME_HISTORY_LEAK_DETECTED
    planted = clean_bytes + b"super_secret_canary_42"
    assert (
        C.scan_bytes_for_leak(planted, canaries=("super_secret_canary_42",))
        == C.RUNTIME_HISTORY_LEAK_DETECTED
    )


# --------------------------------------------------------------------------- #
# Token sanity — the S3 activity token is a distinct, in-force non-approval literal
# --------------------------------------------------------------------------- #
def test_s3_activity_token_is_distinct_nonempty_string():
    assert isinstance(S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN, str)
    assert S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN
    assert S3_SUPERVISOR_ACTIVITY_APPROVAL_TOKEN != S2_SUPERVISOR_ADAPTER_SEAM_APPROVAL_TOKEN
