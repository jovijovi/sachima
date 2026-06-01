# Sachima Phase B Fake-send / Simulator UI Loop Plan Dev Log

## Scope

Planning-only change for Phase B after approval:

```text
approve_fake_send_or_simulator_target
```

This dev log records the design/implementation plan for the local fake-send target and simulator UI loop. It does not implement code, enable PE-2, switch live/default-on, call real external delivery, write production config, restart/reload Gateway, mutate platform adapters, expand production agent/tool execution, or create/own Temporal lifecycle.

## Inputs

- `GOAL.md`
- `docs/sachima-final-goal-gap-analysis.md`
- `docs/plans/2026-05-11-flowweaver-pe1d-pe2-readiness-decision-packet.md`
- PE-1D evidence at `/home/ubuntu/workspace/hermes/outputs/sachima/pe1d-longer-controlled-local-observation/pe1d_controlled_observation_summary.md`
- Existing code anchors:
  - `gateway/platforms/sachima.py`
  - `scripts/sachima_smoke.py`
  - `gateway/delivery_state.py`
  - `gateway/progress/task_titles.py`
  - `gateway/flowweaver_delivery_activity.py`
  - `tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py`

## Plan Artifact

- `docs/plans/2026-05-12-sachima-phase-b-fake-send-simulator-ui-loop-plan.md`

## Design Summary

Phase B should add a local-only `FakeSachimaSendSimulator` and fake `/send` endpoint that receives `SachimaAdapter.send()` payloads on loopback, records sanitized transcript rows by surface, and returns ACKs only after a fake-send request is received.

Required surfaces:

```text
progress_card
rich_card
final_text
media
artifact
```

Required guarantees:

- final text is not suppressed by rich/progress cards;
- ACKs are generated only from fake send responses;
- duplicate/replay sends are idempotent;
- uninitialized delivery refs are rejected;
- transcripts/evidence contain no raw prompt, tool output, card JSON, media path/bytes, platform IDs, secrets, or raw exceptions;
- no production config writes, Gateway restart/reload, real external delivery, PE-2 implementation, live/default-on, or production agent execution expansion.

## Tail Register

| ID | Class | Description | Blocks current phase? | Blocks next phase? | Required before | Acceptance method |
|---|---|---|---:|---:|---|---|
| PB-WATCH-8788 | WATCH | PE-1D exact default port `8788` was not exercised because a running Gateway owned it. Phase B must use dynamic loopback ports and not infer default-port behavior. | No | No | external ingress or live/default-on | Separate maintenance-window approval and exact-port rerun. |
| PB-NEXT-PE2-DESIGN | NEXT_PHASE | PE-2 design packet may consume Phase B evidence after implementation passes. | No | Yes | PE-2 implementation request | Fresh design packet + blocker reviews; implementation still separate. |

## Non-Approvals Preserved

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

## Independent Reviews

### Consistency / phase-gate review

```text
VERDICT: PASS
BLOCKERS: None
```

Reviewed against prior phase evidence and phase boundaries. Strongest allowed outcome remains PE-2 design packet readiness only, not PE-2 implementation/live/default-on.

### Security / low-intrusion review

```text
VERDICT: PASS
BLOCKERS: None
```

Reviewed for accidental live enablement, real external network calls, production config writes, Gateway restart/reload, platform adapter mutation, Temporal lifecycle, raw material leakage, and ACK invention.

## Verification Log

```text
PHASE_B_PLAN_DOC_GATE_PASS
```

Fresh verification performed after plan and review evidence were written:

```bash
git add -N docs/plans/2026-05-12-sachima-phase-b-fake-send-simulator-ui-loop-plan.md docs/dev_log/2026-05-12-sachima-phase-b-fake-send-simulator-ui-loop-plan.md
git diff --check
git check-ignore -v docs/plans/2026-05-12-sachima-phase-b-fake-send-simulator-ui-loop-plan.md docs/dev_log/2026-05-12-sachima-phase-b-fake-send-simulator-ui-loop-plan.md
python - <<'PY'
# Required marker, docs-only changed-path, and secret-literal gate.
PY
git reset -- docs/plans/2026-05-12-sachima-phase-b-fake-send-simulator-ui-loop-plan.md docs/dev_log/2026-05-12-sachima-phase-b-fake-send-simulator-ui-loop-plan.md
```

The final gate was rerun after appending this verification log.
