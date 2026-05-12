# Sachima Phase B Fake-send Simulator Implementation Dev Log

## Scope

Approved implementation text:

```text
approve_phase_b_fake_send_simulator_implementation_no_real_delivery
```

Implementation scope is Phase B local fake-send / simulator UI loop only. It does not approve PE-2 implementation, live/default-on, real external Sachima ingress, production delivery control, production agent/tool execution expansion, production config writes, Gateway restart/reload, platform adapter mutation, Gateway-owned Temporal lifecycle, or real external send calls.

## Base

```text
feature/sachima-channel @ d1dc4602777a51570f5981b02c9c8a1b7c18847e
```

Worktree:

```text
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-phase-b-fake-send-simulator
```

## Implemented files

- `gateway/sachima_fake_send_simulator.py`
- `tests/gateway/test_sachima_fake_send_simulator.py`
- `tests/gateway/test_sachima_fake_send_surface_contract.py`
- `scripts/sachima_fake_send_simulator_smoke.py`
- `docs/runbooks/sachima-fake-send-simulator.md`
- `docs/sachima-channel.md`

## TDD evidence

RED:

```text
ModuleNotFoundError: No module named 'gateway.sachima_fake_send_simulator'
```

GREEN focused simulator gate:

```text
14 passed
```

Command:

```bash
python -m pytest -q tests/gateway/test_sachima_fake_send_simulator.py tests/gateway/test_sachima_fake_send_surface_contract.py
```

## Behavior implemented

- `FakeSachimaSendSimulator.record_send()` accepts synthetic local send payloads and returns ACKs only after a fake send request is received.
- Allowed surfaces are `progress_card`, `rich_card`, `final_text`, `media`, and `artifact`.
- Transcript rows are sanitized and contain only bounded delivery facts.
- Duplicate `idempotency_key` requests reuse the original fake `message_id` and `ack_ref` without appending a second transcript row.
- Uninitialized `delivery_ref` values are rejected with no transcript row.
- The default simulator initializes the Phase B surface refs `runtime_delivery_0` through `runtime_delivery_4`; unknown refs fail closed.
- Media-path shaped content, card-like structured content, and unsafe marker-shaped material are rejected before transcript recording.
- Reusing an `idempotency_key` with mismatched surface, delivery ref, artifact ref, or content digest is rejected as an idempotency conflict.
- `create_fake_sachima_send_app()` exposes a local aiohttp `/send` endpoint.
- `start_fake_sachima_send_server()` starts the app on `127.0.0.1` and can allocate a dynamic port.
- The smoke script writes sanitized evidence to `outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json`.

## Evidence counts

The plan artifact's sample count used `send_requests=6`, but the complete behavior-bearing smoke has seven adapter send attempts:

```text
5 accepted surface sends + 1 duplicate replay + 1 rejected uninitialized delivery ref = 7 attempts
```

The evidence therefore records:

```text
adapter_send_attempts: 7
send_requests: 7
accepted_send_requests: 5
transcript_rows: 5
duplicates: 1
rejected_uninitialized_refs: 1
ack_updates: 5
```

This preserves the important acceptance invariant: ACK updates equal accepted transcript rows and never include duplicate or rejected requests.

## Smoke evidence

Command:

```bash
python scripts/sachima_fake_send_simulator_smoke.py
```

Markers:

```text
PHASE_B_FAKE_SEND_EVIDENCE_PASS outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json
PHASE_B_FINAL_GATE_PASS
```

Evidence path:

```text
outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json
```

## Boundaries preserved

```text
loopback_only: true
real_external_delivery: false
gateway_restart_or_config_write: false
pe2_implementation: false
live_default_on: false
production_config_write: false
```

## Current tail register

| ID | Class | Description | Blocks current phase? | Blocks next phase? | Acceptance method |
|---|---|---|---:|---:|---|
| PB-WATCH-8788 | WATCH | Default port `8788` remains a separate exact-port concern because Phase B uses dynamic loopback ports and does not restart Gateway. | No | No | Separate maintenance-window approval before external ingress/live. |
| PB-NEXT-PE2-DESIGN | NEXT_PHASE | Phase B evidence may feed a PE-2 design packet only after implementation PR passes review and CI. | No | Yes | Fresh PE-2 design packet, no implementation/live approval implied. |

## Final verification

Fresh local verification before review:

```text
git diff --check: pass
Phase B focused tests: 14 passed
Existing Sachima adapter tests: 39 passed
Smoke marker: PHASE_B_FAKE_SEND_EVIDENCE_PASS
Evidence verifier: PHASE_B_FINAL_GATE_PASS
Changed-file/no-leak gate: PHASE_B_CHANGED_FILE_AND_NO_LEAK_GATE_PASS
```

Commands:

```bash
git diff --check
python -m pytest -q tests/gateway/test_sachima_fake_send_simulator.py tests/gateway/test_sachima_fake_send_surface_contract.py
python -m pytest -q tests/gateway/test_sachima_platform.py tests/gateway/platforms/test_sachima.py
python scripts/sachima_fake_send_simulator_smoke.py
PHASE_B_FINAL_GATE_PASS verifier
PHASE_B_CHANGED_FILE_AND_NO_LEAK_GATE_PASS verifier
```

Runtime evidence is intentionally not staged for commit:

```text
outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json
```

## Review status

Independent review results:

```text
consistency / phase-gate review: PASS, no blockers
security / low-intrusion review: REQUEST_CHANGES initially
blocker-only security re-review after fixes: PASS
```

Initial security blockers fixed:

1. Transcript/evidence guard now rejects media-path shaped content and card-like structured content before transcript recording.
2. Default simulator now accepts only Phase B initialized refs `runtime_delivery_0` through `runtime_delivery_4`; unknown refs fail closed.
3. Reused `idempotency_key` with mismatched surface, delivery ref, artifact ref, or content digest now returns `idempotency_conflict` and does not append a row.

Blocker regression evidence:

```text
Phase B focused tests after blocker fixes: 14 passed
blocker-only security re-review: PASS
```
