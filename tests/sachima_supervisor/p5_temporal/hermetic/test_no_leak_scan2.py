"""T8 — No-leak SCAN 2 (serialized event-history bytes) + canary (FR7, Gate G).

Fetches the **real** Temporal event history for a completed run and scans BOTH
the ``json.loads``-decoded structure AND the serialized event-history bytes
(proto ``SerializeToString``) — not only JSON text — for forbidden markers and a
canary sentinel. All data crossing into history is sanitized contracts, so the
real history is clean; the scanner's teeth are asserted independently.
"""

from __future__ import annotations

from types import SimpleNamespace

from sachima_supervisor.p5_temporal import (
    P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    P5TemporalStepExecutor,
)
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.p5_temporal_worker import P5_TEMPORAL_WORKER_IDENTITY

from tests.sachima_supervisor.p5_temporal.hermetic._harness import (
    control_surface_for,
    make_start_request,
    p5_worker_env,
    run_async,
    runtime_client_for,
)

_SIGNED_URL_PREFIX = "https://example.test/object?" + "to" + "ken="

_CANARY = "CANARY_b91d22_scan2_secret_sentinel"
#: Request-ref canary that is NOT itself a denylist word, so the rejection is
#: proven to come from the raw-ref guard (URL/path syntax), not a marker match.
_REF_CANARY = "CANARY_b91d22_scan2_refsentinel"


def test_real_event_history_bytes_and_json_are_canary_free():
    async def scenario():
        async with p5_worker_env() as env:
            client = runtime_client_for(env)
            req = make_start_request(run_ref="run_p5_scan2_0001")
            wid = C.deterministic_workflow_id(req)
            started = await client.start(req, workflow_id=wid)
            raw = await client.serialized_event_history_bytes(workflow_id=wid)
            history_json = await client.event_history_json(workflow_id=wid)
            return started, raw, history_json

    started, raw, history_json = run_async(scenario())
    assert started["ok"] is True

    # SCAN 2: serialized event-history BYTES (not only JSON text).
    assert isinstance(raw, bytes) and len(raw) > 0
    assert C.scan_bytes_for_leak(raw, canaries=(_CANARY,)) is None
    # SCAN 2: also the json.loads-decoded structure.
    assert C.scan_projection_for_leak(history_json, canaries=(_CANARY,)) is None

    # FR2: the ops Worker identity is sanitized to a constant (no host/pid), so
    # worker-task history events carry no machine identity. (The caller/starter
    # client identity is likewise sanitized by ops per the staging runbook — that
    # client is caller-owned, not owned by this package.)
    assert P5_TEMPORAL_WORKER_IDENTITY.encode("utf-8") in raw


def test_scan2_detector_has_teeth():
    planted = b"event payload containing " + _CANARY.encode("utf-8")
    assert C.scan_bytes_for_leak(planted, canaries=(_CANARY,)) == C.RUNTIME_HISTORY_LEAK_DETECTED
    assert C.scan_bytes_for_leak(b"...Traceback (most recent call last)...") == C.RUNTIME_HISTORY_LEAK_DETECTED
    # canary-free clean bytes pass
    assert C.scan_bytes_for_leak(b"claim_ref_input_0 sha256:" + b"a" * 64) is None


def _role():
    return SimpleNamespace(role_key="sachima.claude.read_only_reviewer", logical_role="architect")


def _clean_inputs():
    return (
        {
            "artifact_id": "claim_ref_input_0",
            "producer_step_id": "root",
            "content_digest": "sha256:" + "a" * 64,
            "artifact_kind": "input",
            "byte_count": 64,
            "created_at_ref": "created_at_ref_p5_0001",
        },
    )


def test_signed_url_request_ref_fails_closed_before_temporal_history():
    """A signed-URL request ref carrying a canary must fail closed BEFORE any
    Temporal workflow is started — proving the request-ref leak path (blocker 1)
    never reaches real event history."""

    async def scenario():
        async with p5_worker_env() as env:
            executor = P5TemporalStepExecutor(
                control_surface=control_surface_for(env),
                enabled=True,
                approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
            )
            # Clean run/step refs so the would-be workflow id is computable for the
            # not-found probe; the canary rides in the idempotency_key as a signed
            # URL. Pre-fix it normalized into a safe-looking id and entered history.
            request = SimpleNamespace(
                run_id="run_p5_scan2_refguard_0001",
                step_id="architect",
                attempt_index=1,
                transaction_ref="tx_p5_scan2_0001",
                idempotency_key=_SIGNED_URL_PREFIX + _REF_CANARY,
                input_artifact_digests=("sha256:" + "a" * 64,),
            )
            outcome = await executor.aexecute(
                request, role_binding=_role(), resolved_inputs=_clean_inputs()
            )
            # Nothing should have launched: the clean (run, step) workflow id is unknown.
            probe = await runtime_client_for(env).query(
                workflow_id=C.workflow_id_from_refs("run_p5_scan2_refguard_0001", "architect")
            )
            return outcome, probe, executor.serialized_history_bytes()

    outcome, probe, history_bytes = run_async(scenario())
    # Fail closed at the trust boundary with a stable code, before any Temporal call.
    assert outcome.ok is False
    assert outcome.error_code == C.INVALID_START_PAYLOAD
    # No workflow was created => no Temporal history holds the canary.
    assert probe["ok"] is False and probe["error_code"] == C.RUNTIME_NOT_FOUND
    # The canary never entered the executor's serialized history bytes either.
    assert C.scan_bytes_for_leak(history_bytes, canaries=(_REF_CANARY,)) is None
