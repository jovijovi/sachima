# Sachima Fake-send Simulator Runbook

## Purpose

The fake-send simulator proves Sachima delivery and ACK semantics locally before any PE-2 or live delivery work. It receives `SachimaAdapter.send()` requests through a loopback `/send` endpoint, records sanitized transcript rows by surface, and returns ACKs only after a fake send request is received.

This is local test tooling only.

## Explicit boundaries

Not approved by this runbook or Phase B evidence:

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

Do not read `~/.hermes/config.yaml` or `.env` for this simulator. Do not stop, restart, or reload the running Gateway.

## Quick smoke

```bash
python scripts/sachima_fake_send_simulator_smoke.py
```

Expected marker:

```text
PHASE_B_FAKE_SEND_EVIDENCE_PASS outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json
```

The script allocates a dynamic `127.0.0.1` port and configures `SachimaAdapter` directly:

```python
SachimaAdapter(PlatformConfig(enabled=True, extra={"send_url": "http://127.0.0.1:<port>/send"}))
```

## Fake `/send` request shape

```json
{
  "chat_id": "phase-b-local-chat",
  "content": "safe user-visible summary or final text",
  "reply_to": "phase-b-local-message-1",
  "metadata": {
    "surface": "final_text",
    "delivery_ref": "runtime_delivery_2",
    "artifact_ref": "runtime_artifact_0",
    "intent_summary": "Phase B fake-send simulator proof",
    "idempotency_key": "phase-b-final"
  }
}
```

Allowed surfaces:

```text
progress_card
rich_card
final_text
media
artifact
```

## Fake `/send` response shape

Successful request:

```json
{
  "ok": true,
  "message_id": "fake-sachima-send-0001",
  "delivery_ref": "runtime_delivery_2",
  "surface": "final_text",
  "ack_ref": "runtime_event_delivery_ack_0001",
  "duplicate": false
}
```

Duplicate request with the same `idempotency_key` returns the same `message_id` and `ack_ref` with `duplicate=true`, without appending a second transcript row. If the same idempotency key is reused with different surface, delivery ref, artifact ref, or content digest, the simulator rejects it as `idempotency_conflict`.

Invalid or unsafe requests fail closed:

```json
{"ok": false, "error_code": "uninitialized_delivery_ref", "retryable": false}
```

## Transcript semantics

Each transcript row is sanitized and bounded:

```json
{
  "sequence": 1,
  "surface": "final_text",
  "message_id": "fake-sachima-send-0001",
  "delivery_ref": "runtime_delivery_2",
  "artifact_ref": "runtime_artifact_0",
  "reply_to_present": true,
  "content_digest": "sha256:<digest>",
  "content_preview": "最终回复：Phase B fake-send simulator proof",
  "ack_ref": "runtime_event_delivery_ack_0001",
  "status": "sent"
}
```

The transcript is a user-visible/evidence surface. It must not contain raw prompts, tool output, full card payloads, media bytes or paths, real platform IDs, credentials, callback payloads, or raw exceptions. The simulator rejects media-path shaped content, card-like structured content, and unknown delivery refs before recording transcript rows.

## Evidence path

```text
outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json
```

Expected count semantics:

- `adapter_send_attempts = 7`: five surfaces, one duplicate replay, one rejected uninitialized delivery ref.
- `transcript_rows = 5`: one row per accepted surface.
- `duplicates = 1`: duplicate replay reuses prior ACK.
- `rejected_uninitialized_refs = 1`: invalid delivery ref rejected without transcript row.
- `ack_updates = 5`: ACKs correspond exactly to accepted transcript rows.

## Verification bundle

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
assert data['counts']['ack_updates'] == 5
print('PHASE_B_FINAL_GATE_PASS')
PY
```

## Decision limit

Passing this runbook supports only:

```text
phase_b_fake_send_simulator_evidence_ready_for_pe2_design_packet_only
```

It still does not approve PE-2 implementation, live/default-on, real external ingress, real delivery control, production config writes, Gateway restart/reload, or production agent/tool execution expansion.
