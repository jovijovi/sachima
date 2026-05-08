# Sachima FlowWeaver Mock Contracts

This mock project contains the Phase 3 Task 3.1 FlowWeaver v0 contract and golden snapshots. It is intentionally isolated from production Sachima code.

## Versioning

- Current contract version: `flowweaver.v0`.
- Stable envelope type: `flowweaver.handle.v0`.
- The schema file is `contracts/flowweaver.v0.schema.json`.
- Golden snapshots live in `snapshots/*.snapshot.json` and should remain append-only fixtures for later phases.
- Breaking changes must create a new versioned schema and snapshots instead of mutating v0 semantics.

## v0 invariants

1. A transaction owns ordered intent records.
2. Each intent has a stable `intent_id`, `order_index`, `title`, `status`, and explicit `dependencies` list.
3. Intent, operation, artifact, transaction, final text, and snapshot lifecycle states use: `pending`, `running`, `succeeded`, `failed`, `blocked`, `cancelled`, `skipped`.
4. Operation records describe work attempted for an intent. They must not contain platform delivery fields or raw tool input/output.
5. Artifact records describe generated result data or fallback text. They must not contain delivery ACK fields.
6. Delivery records are unified ACK records for platform send/edit success and point at an artifact, snapshot, final text, transaction, or intent.
7. Snapshots are sanitized, bounded, ordered, and safe to render in IM.
8. Delivery ACKs are recorded only after platform send/edit success.
9. Final coverage is explicit and ordered: each user intent is answered by delivered final/fallback text, represented by a delivered rich/media/file/voice artifact, failed, skipped with a reason, or blocked waiting for user input.

## Golden snapshots

- `mixed_weather_time_disk.snapshot.json`: multi-intent request covering weather, time, and disk status.
- `dependent_weather_compare.snapshot.json`: weather today + weather tomorrow + dependent synthesis comparison.
- `ai_flow_approval_wait.snapshot.json`: AI FLOW inspection and planning blocked at a user approval gate.

## Safety rules

Snapshots are contract fixtures, not logs. They must not store real credentials, full tool arguments, raw command output, or Feishu/Lark card JSON. Use concise summaries and fake mock identifiers only.

## Validation

From the repository root, run the repo wrapper tests and deterministic Gate C harness:

```bash
scripts/run_tests.sh tests/flowweaver_phase3 -q
python -m py_compile prototypes/flowweaver_phase3/src/flowweaver_mock/*.py prototypes/flowweaver_phase3/scripts/validate_scenarios.py tests/flowweaver_phase3/test_contract_examples.py tests/flowweaver_phase3/test_mock_orchestrator.py tests/flowweaver_phase3/test_scenarios.py
cd prototypes/flowweaver_phase3 && python scripts/validate_scenarios.py
```
