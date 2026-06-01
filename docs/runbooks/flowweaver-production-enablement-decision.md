# FlowWeaver Production Enablement Decision Runbook

## Purpose

Use this runbook to interpret the Production Enablement Decision Packet after FlowWeaver Phase 33.

The packet is a decision gate. It is not an activation guide and does not authorize production config writes, Gateway restart/reload, platform adapter mutation, live delivery control, or production agent/tool execution.

## Verdict Semantics

| Verdict | Meaning |
|---|---|
| `conditional_go_for_pe1_controlled_sachima_production_shadow_observation` | Enough evidence exists to request a separate PE-1 phase for controlled Sachima shadow observation. |
| `not_ready_for_production_enablement` | Evidence is insufficient; remain in local/staging validation. |
| `production_enabled` | Forbidden in this packet. |
| `production_ready` | Forbidden in this packet. |

## How to Use the Packet

1. Confirm the packet is docs-only.
2. Confirm it names `feature/sachima-channel @ f5eaabe64` or a newer verified base as evidence.
3. Confirm it separates conditional shadow observation from default-on production behavior.
4. Confirm it lists operational approvals separately.
5. Confirm rollback can stop new observation starts by disabling config, removing allowlist, or removing the injected runtime surface.
6. Confirm no raw prompt/tool/card/media/platform/private id/callback/credential/raw exception material appears in docs evidence.
7. Ask 狗哥 for the PE-1 approval text before implementing anything operational.

## Required Approval Text

PE-1 may start only after explicit approval equivalent to:

```text
Approve PE-1 only: controlled Sachima production-shadow observation design/implementation, default-off and observation-only.
```

Operational changes still require separate explicit approvals:

```text
approve_production_config_write
approve_gateway_restart_or_reload
approve_sachima_platform_allowlist
approve_external_runtime_control_surface
approve_external_temporal_service_or_worker_if_used
```

## PE-1 Must Stay Observation-Only

PE-1 may observe sanitized real Gateway turns and mirror safe counters/refs into a caller-supplied runtime control surface.

PE-1 must not:

- control final text delivery;
- control rich-card/media delivery;
- invent ACKs;
- call production agent/tool executors;
- own Temporal service/Worker lifecycle;
- mutate platform adapters;
- alter adapter send behavior;
- default-enable itself.

## Rollback

Rollback must be one or more of:

1. Set `flowweaver.production_shadow_observation.enabled=false`.
2. Remove `sachima` from the allowlist.
3. Remove the injected runtime control surface.
4. Stop the externally managed runtime/Temporal Worker.
5. Revert the PE-1 PR or operational config change.

Rollback must not require raw payload inspection and must not mutate platform adapters.

## Verification Before PE-1 PR

Run focused and regression verification before claiming PE-1 readiness:

```bash
git diff --check
python -m pytest -q tests/gateway/test_flowweaver_production_shadow_observation.py
python -m pytest -o addopts= -n 4 -q tests/integration/test_flowweaver_phase21_production_shadow_observation.py tests/integration/test_flowweaver_phase33_ai_flow_pilot.py
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

Run blocker-only reviews focused on:

- default-off behavior;
- allowlist enforcement;
- no Gateway-owned lifecycle;
- no raw material in logs/history/snapshots/docs;
- no final-delivery behavior mutation;
- rollback completeness;
- operational approvals staying separate.
