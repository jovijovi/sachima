# Sachima Phase B Fake-send / Simulator UI Loop Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after Dog Brother explicitly approves implementation. This document is a design and implementation plan only.

**Goal:** Prove Sachima delivery behavior through a local fake-send target and simulator transcript without real external IM delivery.

**Architecture:** Add a low-intrusion local simulator module that receives `SachimaAdapter.send()` payloads through a loopback `/send` endpoint, records sanitized transcript entries by delivery surface, and emits ACKs only from actual fake-send HTTP responses. The simulator is test-only/local tooling: no production config write, no Gateway restart, no real external ingress, no PE-2 implementation, no production delivery control, and no production agent/tool execution expansion.

**Tech Stack:** Python, aiohttp loopback test server, `SachimaAdapter`, existing `gateway.delivery_state` surface semantics, existing `gateway.progress.task_titles` high-density task summarizer, pytest.

---

## Approval and Boundary

Approved text received:

```text
approve_fake_send_or_simulator_target
```

This approval allows planning for a fake/local send target and simulator UI loop only.

It does **not** approve:

```text
pe2_implementation
pe2_live_default_on
real_external_sachima_ingress
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
```

If a later implementation needs any of those, stop and request separate approval.

## Goal Trace

```text
Goal: Sachima becomes a safe IM workbench with visible progress, artifacts, and delivery state.
Gap: PE-1D proved observation-only ingress but intentionally kept SACHIMA_SEND_URL absent; delivery/ACK behavior is not proven.
Phase: Phase B — Fake-send / Simulator UI loop.
Task: Add local fake-send simulator design, tests, smoke script, docs, and evidence gate.
Test: Focused simulator tests, Sachima adapter tests, no-leak checks, duplicate/replay probes, doc guard.
Evidence: pytest output, smoke JSON evidence under outputs/sachima/phase-b-fake-send-simulator/, sanitized transcript, no-leak report.
Decision: May request PE-2 design packet only after Phase B implementation evidence passes; PE-2 implementation/live remains NO-GO.
```

## Level Selection

**Level 2 — Standard, escalated delivery-boundary checks.**

Reason: Phase B touches delivery semantics and ACK mapping, but only through a local fake target. It must not cross into real external delivery, production config, or Gateway lifecycle.

## Current Evidence Inputs

- `GOAL.md` requires delivery separation and no raw material in durable/user-visible evidence.
- `docs/sachima-final-goal-gap-analysis.md` marks fake-send/simulator as the safest next behavior-bearing proof before real delivery.
- `docs/plans/2026-05-11-flowweaver-pe1d-pe2-readiness-decision-packet.md` requires fake-send/simulator evidence before any PE-2 implementation request.
- PE-1D evidence: `/home/ubuntu/workspace/hermes/outputs/sachima/pe1d-longer-controlled-local-observation/pe1d_controlled_observation_summary.md`.
- Existing code anchors:
  - `gateway/platforms/sachima.py` — `SachimaAdapter.send()` posts to `send_url` or records local messages when absent.
  - `scripts/sachima_smoke.py` — current minimal fake `/send` example.
  - `gateway/delivery_state.py` — final text vs rich card/media delivery state helpers.
  - `gateway/progress/task_titles.py` — high-density task intent summarizer.
  - `gateway/flowweaver_delivery_activity.py` and `tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py` — existing surface/ACK semantics to mirror locally, not production-enable.

## Phase B Contract

### Allowed surfaces

```text
progress_card
rich_card
final_text
media
artifact
```

### Local fake-send request shape

The fake endpoint accepts the existing `SachimaAdapter.send()` payload plus simulator metadata:

```json
{
  "chat_id": "phase-b-local-chat",
  "content": "safe user-visible summary or final text",
  "reply_to": "phase-b-local-message-1",
  "metadata": {
    "surface": "final_text",
    "delivery_ref": "runtime_delivery_1",
    "artifact_ref": "runtime_artifact_0",
    "intent_summary": "Plan Phase B fake-send loop",
    "idempotency_key": "phase-b-turn-1-final-text"
  }
}
```

### Local fake-send response shape

ACKs are generated only after the fake endpoint receives a request:

```json
{
  "ok": true,
  "message_id": "fake-sachima-send-0001",
  "delivery_ref": "runtime_delivery_1",
  "surface": "final_text",
  "ack_ref": "runtime_event_delivery_ack_1",
  "duplicate": false
}
```

Duplicate requests with the same `idempotency_key` must return the same `message_id` and `duplicate=true`; they must not append a second transcript row.

### Sanitized transcript row

The simulator stores a safe transcript row, not raw platform payloads:

```json
{
  "sequence": 1,
  "surface": "final_text",
  "message_id": "fake-sachima-send-0001",
  "delivery_ref": "runtime_delivery_1",
  "artifact_ref": "runtime_artifact_0",
  "reply_to_present": true,
  "content_digest": "sha256:...",
  "content_preview": "完成：Phase B fake-send loop proof",
  "ack_ref": "runtime_event_delivery_ack_1",
  "status": "sent"
}
```

Forbidden in transcript/evidence:

```text
raw_prompt
raw tool output
card_json
media_path
media_bytes
platform payload
platform/chat/user/message identifiers from real platforms
callback payload
credentials, tokens, API keys, signatures, bearer headers
raw exception text / traceback
```

## Definition of Ready

- PE-1D evidence exists and passed with no-leak scan.
- Phase B approval text is present.
- Work is done in a clean worktree from `origin/feature/sachima-channel`.
- Scope remains fake/local send only.
- No production Gateway process is stopped, restarted, or reconfigured.
- No real `SACHIMA_SEND_URL` from user config is used; tests allocate their own loopback port.
- Planned files are not ignored by `.gitignore`.

## Definition of Done

Phase B implementation can be considered complete only when all are true:

- Fake `/send` endpoint receives local adapter sends and creates ACKs only from received requests.
- Simulator transcript shows `progress_card`, `rich_card`, `final_text`, `media`, and `artifact` surfaces as separate rows.
- Final text is not suppressed by rich/progress cards.
- ACK updates are a deterministic subset/prefix of initialized delivery slots; no invented ACKs.
- Duplicate/replay send attempts are idempotent.
- No raw prompt/card/media/tool output/platform ID/secret appears in transcript, evidence, logs, or returned results.
- Focused tests pass freshly.
- Smoke evidence is written under `outputs/sachima/phase-b-fake-send-simulator/`.
- Explicit non-approvals remain listed.
- Tail Register has no `BLOCKER` items.

## Kill Criteria

Stop the phase if any happens:

- A fake-send transcript or evidence file contains raw prompt, raw tool output, card JSON, media path/bytes, platform IDs, secrets, or raw exception text.
- Any test or script calls a non-loopback URL.
- Implementation reads or writes `~/.hermes/config.yaml`, `.env`, or production config.
- Implementation restarts or stops the running Gateway.
- ACKs are generated without a corresponding fake-send request.
- Rich/progress card delivery causes final text to be skipped.
- Duplicate replay produces a second delivery row for the same idempotency key.

## Blast Radius

- Environment: local test process only.
- Network: loopback only, dynamically allocated port.
- Delivery target: fake `/send` endpoint only.
- Runtime: no Temporal service/Worker; no production Gateway lifecycle.
- Data: synthetic local payloads only.
- Persistence: sanitized JSON evidence and docs only.

## Tail Register

| ID | Class | Description | Blocks current phase? | Blocks next phase? | Required before | Acceptance method |
|---|---|---|---:|---:|---|---|
| PB-WATCH-8788 | WATCH | PE-1D exact default port `8788` was not exercised because a running Gateway owned it. Phase B must use dynamic loopback ports and must not infer default-port behavior. | No | No | external ingress or live/default-on | Separate maintenance-window approval and exact-port rerun. |
| PB-NEXT-PE2-DESIGN | NEXT_PHASE | PE-2 design packet may consume Phase B evidence after implementation passes. | No | Yes | PE-2 implementation request | Fresh design packet + blocker reviews; implementation still separate. |

## Implementation Tasks

### Task 1: Add simulator contract tests

**Objective:** Define the fake-send simulator API before implementation.

**Files:**
- Create: `tests/gateway/test_sachima_fake_send_simulator.py`
- Later create: `gateway/sachima_fake_send_simulator.py`

**Step 1: Write failing tests**

Add tests for:

```python
def test_fake_send_records_surfaces_and_returns_ack_from_received_request():
    simulator = FakeSachimaSendSimulator()
    response = simulator.record_send({
        "chat_id": "phase-b-local-chat",
        "content": "任务：Phase B fake-send proof",
        "reply_to": "phase-b-local-message-1",
        "metadata": {
            "surface": "final_text",
            "delivery_ref": "runtime_delivery_1",
            "artifact_ref": "runtime_artifact_0",
            "intent_summary": "Phase B fake-send proof",
            "idempotency_key": "phase-b-turn-1-final-text",
        },
    })
    assert response["ok"] is True
    assert response["surface"] == "final_text"
    assert response["delivery_ref"] == "runtime_delivery_1"
    assert response["ack_ref"].startswith("runtime_event_delivery_ack_")
    assert simulator.transcript()[0]["surface"] == "final_text"
```

```python
def test_fake_send_duplicate_idempotency_key_reuses_ack_without_new_transcript_row():
    simulator = FakeSachimaSendSimulator()
    payload = {
        "chat_id": "phase-b-local-chat",
        "content": "任务：Phase B fake-send proof",
        "reply_to": "phase-b-local-message-1",
        "metadata": {"surface": "rich_card", "delivery_ref": "runtime_delivery_0", "idempotency_key": "same-key"},
    }
    first = simulator.record_send(payload)
    second = simulator.record_send(payload)
    assert second["duplicate"] is True
    assert second["message_id"] == first["message_id"]
    assert len(simulator.transcript()) == 1
```

```python
def test_fake_send_rejects_raw_or_secret_shaped_material():
    simulator = FakeSachimaSendSimulator()
    response = simulator.record_send({
        "chat_id": "oc_phase_b_private_chat",
        "content": "raw prompt phase b private value",
        "reply_to": "om_phase_b_private_message",
        "metadata": {"surface": "final_text", "delivery_ref": "runtime_delivery_0", "token": "unsafe-token-phase-b"},
    })
    assert response == {"ok": False, "error_code": "unsafe_material", "retryable": False}
    assert simulator.transcript() == []
```

**Step 2: Run test to verify failure**

Run:

```bash
python -m pytest -q tests/gateway/test_sachima_fake_send_simulator.py
```

Expected: FAIL because `gateway.sachima_fake_send_simulator` does not exist.

### Task 2: Implement pure in-memory fake-send simulator

**Objective:** Implement transcript, ACK generation, idempotency, and no-leak guards without network or Gateway lifecycle.

**Files:**
- Create: `gateway/sachima_fake_send_simulator.py`

**Step 1: Implement minimal module**

Core shape:

```python
from __future__ import annotations

import hashlib
import json
from typing import Any

ALLOWED_SURFACES = {"progress_card", "rich_card", "final_text", "media", "artifact"}
UNSAFE_MARKERS = (
    "raw_prompt", "tool_output", "card_json", "media_path", "media_bytes",
    "platform_payload", "callback_payload", "traceback", "runtimeerror:",
    "unsafe-token", "sk-", "bearer ", "oc_", "ou_", "om_",
)

class FakeSachimaSendSimulator:
    def __init__(self) -> None:
        self._rows: list[dict[str, object]] = []
        self._by_idempotency: dict[str, dict[str, object]] = {}
        self._counter = 0

    def record_send(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            return self._error("invalid_payload")
        if self._unsafe(payload):
            return self._error("unsafe_material")
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        surface = str(metadata.get("surface") or "final_text")
        if surface not in ALLOWED_SURFACES:
            return self._error("invalid_surface")
        delivery_ref = str(metadata.get("delivery_ref") or "")
        if not delivery_ref.startswith("runtime_delivery_"):
            return self._error("invalid_delivery_ref")
        key = str(metadata.get("idempotency_key") or "")
        if key and key in self._by_idempotency:
            prior = dict(self._by_idempotency[key])
            prior["duplicate"] = True
            return prior
        self._counter += 1
        message_id = f"fake-sachima-send-{self._counter:04d}"
        ack_ref = f"runtime_event_delivery_ack_{self._counter:04d}"
        row = {
            "sequence": self._counter,
            "surface": surface,
            "message_id": message_id,
            "delivery_ref": delivery_ref,
            "artifact_ref": metadata.get("artifact_ref"),
            "reply_to_present": bool(payload.get("reply_to")),
            "content_digest": self._digest(payload.get("content")),
            "content_preview": self._preview(payload.get("content")),
            "ack_ref": ack_ref,
            "status": "sent",
        }
        self._rows.append(row)
        response = {"ok": True, "message_id": message_id, "delivery_ref": delivery_ref, "surface": surface, "ack_ref": ack_ref, "duplicate": False}
        if key:
            self._by_idempotency[key] = dict(response)
        return response

    def transcript(self) -> list[dict[str, object]]:
        return [dict(row) for row in self._rows]
```

Keep helper methods safe, deterministic, and exception-free.

**Step 2: Run tests**

Run:

```bash
python -m pytest -q tests/gateway/test_sachima_fake_send_simulator.py
```

Expected: PASS.

### Task 3: Add aiohttp fake `/send` adapter wrapper

**Objective:** Let `SachimaAdapter.send()` hit the simulator through a real local HTTP response path.

**Files:**
- Modify: `gateway/sachima_fake_send_simulator.py`
- Modify: `tests/gateway/test_sachima_fake_send_simulator.py`

**Step 1: Add failing async test**

```python
@pytest.mark.asyncio
async def test_fake_send_aiohttp_app_returns_ack_header(aiohttp_client):
    simulator = FakeSachimaSendSimulator()
    app = create_fake_sachima_send_app(simulator)
    client = await aiohttp_client(app)
    response = await client.post("/send", json={
        "chat_id": "phase-b-local-chat",
        "content": "安全摘要",
        "metadata": {"surface": "final_text", "delivery_ref": "runtime_delivery_0", "idempotency_key": "k1"},
    })
    body = await response.json()
    assert response.status == 200
    assert body["ok"] is True
    assert response.headers["X-Sachima-Message-Id"] == body["message_id"]
```

If `aiohttp_client` is not available in this repo, use `aiohttp.web.AppRunner` and `TCPSite` like `scripts/sachima_smoke.py`.

**Step 2: Implement app factory**

```python
def create_fake_sachima_send_app(simulator: FakeSachimaSendSimulator):
    from aiohttp import web

    async def handle_send(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error_code": "invalid_json", "retryable": False}, status=400)
        result = simulator.record_send(payload)
        status = 200 if result.get("ok") else 400
        headers = {}
        if result.get("message_id"):
            headers["X-Sachima-Message-Id"] = str(result["message_id"])
        return web.json_response(result, status=status, headers=headers)

    app = web.Application()
    app.router.add_post("/send", handle_send)
    return app
```

**Step 3: Verify**

Run:

```bash
python -m pytest -q tests/gateway/test_sachima_fake_send_simulator.py
```

Expected: PASS.

### Task 4: Add surface contract tests with `SachimaAdapter.send()`

**Objective:** Prove adapter sends can create separate fake-send transcript rows for each surface.

**Files:**
- Create: `tests/gateway/test_sachima_fake_send_surface_contract.py`
- Use: `gateway/platforms/sachima.py`
- Use: `gateway/delivery_state.py`

**Step 1: Write async test with local server**

Test outline:

```python
@pytest.mark.asyncio
async def test_sachima_adapter_fake_send_surfaces_remain_separate(unused_tcp_port):
    simulator = FakeSachimaSendSimulator()
    runner, port = await start_simulator_server(simulator, unused_tcp_port)
    adapter = SachimaAdapter(PlatformConfig(enabled=True, extra={"send_url": f"http://127.0.0.1:{port}/send"}))
    try:
        await adapter.send("phase-b-local-chat", "任务：安全摘要", metadata={"surface": "progress_card", "delivery_ref": "runtime_delivery_0", "idempotency_key": "progress"})
        await adapter.send("phase-b-local-chat", "卡片：安全摘要", metadata={"surface": "rich_card", "delivery_ref": "runtime_delivery_1", "idempotency_key": "rich"})
        await adapter.send("phase-b-local-chat", "最终回复：安全摘要", metadata={"surface": "final_text", "delivery_ref": "runtime_delivery_2", "idempotency_key": "final"})
        rows = simulator.transcript()
        assert [row["surface"] for row in rows] == ["progress_card", "rich_card", "final_text"]
        assert rows[-1]["surface"] == "final_text"
    finally:
        await runner.cleanup()
```

**Step 2: Add final-text suppression test**

Use `gateway.delivery_state`:

```python
def test_rich_card_fake_send_does_not_mark_final_text_sent():
    result = {"final_response": "visible", "delivery_state": {}}
    record_rich_card_sent(result, result_type="sachima.rich_card.v0", message_id="fake-sachima-send-0001")
    assert should_skip_final_text(result) is False
```

**Step 3: Verify**

Run:

```bash
python -m pytest -q tests/gateway/test_sachima_fake_send_surface_contract.py
```

Expected: PASS.

### Task 5: Add duplicate/replay and initialized-slot ACK tests

**Objective:** Ensure ACKs are bounded by initialized delivery refs and duplicates remain idempotent.

**Files:**
- Modify: `tests/gateway/test_sachima_fake_send_surface_contract.py`
- Modify: `gateway/sachima_fake_send_simulator.py`

**Step 1: Add initialized slot API**

Extend simulator constructor:

```python
def __init__(self, initialized_delivery_refs: set[str] | None = None) -> None:
    self.initialized_delivery_refs = set(initialized_delivery_refs or set())
```

If `initialized_delivery_refs` is non-empty, reject any payload whose `delivery_ref` is not in it.

**Step 2: Add test**

```python
def test_fake_send_rejects_uninitialized_delivery_ref():
    simulator = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0"})
    result = simulator.record_send({
        "chat_id": "phase-b-local-chat",
        "content": "safe",
        "metadata": {"surface": "final_text", "delivery_ref": "runtime_delivery_99"},
    })
    assert result["ok"] is False
    assert result["error_code"] == "uninitialized_delivery_ref"
    assert simulator.transcript() == []
```

**Step 3: Verify**

Run:

```bash
python -m pytest -q tests/gateway/test_sachima_fake_send_surface_contract.py tests/gateway/test_sachima_fake_send_simulator.py
```

Expected: PASS.

### Task 6: Add deterministic smoke script and evidence writer

**Objective:** Produce Phase B evidence without real LLM, real external delivery, or running Gateway restart.

**Files:**
- Create: `scripts/sachima_fake_send_simulator_smoke.py`
- Create output at runtime only: `outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json`

**Step 1: Smoke behavior**

The smoke script should:

1. Start local fake `/send` server on a dynamic loopback port.
2. Configure `SachimaAdapter(PlatformConfig(... extra={"send_url": fake_url}))` directly.
3. Send one local progress card, one rich card, one final text, one media placeholder, and one artifact ref through `adapter.send()` with metadata surfaces.
4. Replay one duplicate idempotency key and prove transcript row count does not increase.
5. Try one uninitialized delivery ref and prove it is rejected without transcript row.
6. Write sanitized evidence JSON.

**Step 2: Evidence shape**

```json
{
  "type": "sachima.phase_b.fake_send_simulator_evidence.v0",
  "scope": {
    "loopback_only": true,
    "real_external_delivery": false,
    "gateway_restart_or_config_write": false,
    "pe2_implementation": false
  },
  "counts": {
    "send_requests": 6,
    "transcript_rows": 5,
    "duplicates": 1,
    "rejected_uninitialized_refs": 1,
    "ack_updates": 5
  },
  "surface_state": {
    "progress_card_sent": true,
    "rich_cards_sent": 1,
    "final_text_sent": true,
    "media_sent": 1,
    "artifact_refs_sent": 1
  },
  "no_leak_scan": {"passed": true, "raw_marker_hits": 0}
}
```

**Step 3: Verify**

Run:

```bash
python scripts/sachima_fake_send_simulator_smoke.py
python - <<'PY'
import json
from pathlib import Path
p = Path('outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json')
data = json.loads(p.read_text())
assert data['no_leak_scan']['passed'] is True
assert data['surface_state']['final_text_sent'] is True
assert data['counts']['ack_updates'] == 5
print('PHASE_B_FAKE_SEND_EVIDENCE_PASS')
PY
```

Expected: `PHASE_B_FAKE_SEND_EVIDENCE_PASS`.

### Task 7: Update docs and runbook notes

**Objective:** Document local simulator usage and boundaries.

**Files:**
- Modify: `docs/sachima-channel.md`
- Create: `docs/runbooks/sachima-fake-send-simulator.md`
- Create: `docs/dev_log/2026-05-12-sachima-phase-b-fake-send-simulator-ui-loop.md`

**Required doc content:**

- local-only setup command;
- fake `/send` request/response shape;
- simulator transcript semantics;
- surface separation rules;
- no-leak evidence path;
- explicit non-approvals;
- statement that this is not PE-2 implementation and not real delivery.

**Verification:**

```bash
git diff --check
python -m pytest -q tests/gateway/test_sachima_fake_send_simulator.py tests/gateway/test_sachima_fake_send_surface_contract.py tests/gateway/test_sachima_platform.py tests/gateway/platforms/test_sachima.py
python scripts/sachima_fake_send_simulator_smoke.py
```

## Review Requirements

Before requesting implementation merge:

1. Independent consistency review: check Phase B consumes PE-1D evidence and does not imply PE-2/live/default-on.
2. Security/low-intrusion review: check no real delivery, no config writes, no Gateway restart, no external ingress, no raw material leakage.
3. Blocker-only re-review after fixes if either review reports blockers.

## Implementation Handoff

After this plan is approved for execution, use this exact implementation approval text:

```text
approve_phase_b_fake_send_simulator_implementation_no_real_delivery
```

Without that approval, do not create implementation code beyond this plan.

## Suggested Verification Bundle for Implementation PR

```bash
git diff --check
python -m pytest -q tests/gateway/test_sachima_fake_send_simulator.py tests/gateway/test_sachima_fake_send_surface_contract.py
python -m pytest -q tests/gateway/test_sachima_platform.py tests/gateway/platforms/test_sachima.py
python scripts/sachima_fake_send_simulator_smoke.py
python - <<'PY'
import json
from pathlib import Path
p = Path('outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json')
data = json.loads(p.read_text())
assert data['no_leak_scan']['passed'] is True
assert data['scope']['real_external_delivery'] is False
assert data['scope']['gateway_restart_or_config_write'] is False
assert data['surface_state']['final_text_sent'] is True
print('PHASE_B_FINAL_GATE_PASS')
PY
```

## Phase Decision After Implementation

If the implementation PR passes, the strongest allowed verdict is:

```text
phase_b_fake_send_simulator_evidence_ready_for_pe2_design_packet_only
```

It still does not approve PE-2 implementation, live/default-on, real external ingress, real delivery control, production config writes, Gateway restart/reload, or production agent/tool execution expansion.
