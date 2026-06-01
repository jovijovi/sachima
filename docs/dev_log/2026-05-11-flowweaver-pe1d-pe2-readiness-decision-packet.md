# Dev Log — FlowWeaver PE-1D / PE-2 Readiness Decision Packet

## Scope

Decision packet only. This branch records the PE-1A/PE-1B/PE-1C evidence and decides whether to request PE-1D or PE-2 work next.

It does **not** enable PE-2, write production config, restart/reload Gateway, mutate platform adapters, enable real external ingress, control delivery, run production agent/tools, or create/own Temporal runtime lifecycle.

NO-GO remains explicit for PE-2 implementation, PE-2 live/default-on, real external ingress, production delivery control, and production agent/tool execution expansion.

Recommended next approval text preserved for handoff:

```text
approve_pe1d_longer_controlled_sachima_local_observation_window
```

Branch/worktree:

```text
feat/flowweaver-pe1d-pe2-readiness-decision-packet
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-pe1d-pe2-readiness-decision-packet
```

Base:

```text
feature/sachima-channel @ 0833544b2a4e
```

## Approval

狗哥 approved starting PE-1D / PE-2 readiness decision packet in Feishu.

This approval covers docs/decision work and exact guard maintenance only. It does not approve PE-2 implementation or live behavior.

## Evidence Read

Primary repository documents reviewed:

- `docs/plans/2026-05-11-flowweaver-production-enablement-decision-packet.md`
- `docs/runbooks/flowweaver-production-enablement-decision.md`
- `docs/dev_log/2026-05-11-flowweaver-production-enablement-decision-packet.md`
- `docs/plans/2026-05-11-flowweaver-pe1-controlled-sachima-shadow-observation.md`
- `docs/runbooks/flowweaver-pe1-controlled-sachima-shadow-observation.md`
- `docs/dev_log/2026-05-11-flowweaver-pe1-controlled-sachima-shadow-observation.md`

Primary operational evidence reviewed:

- `/home/ubuntu/workspace/hermes/outputs/sachima/pe1b_observation_evidence_20260511183216.json`
- `/home/ubuntu/workspace/hermes/outputs/sachima/pe1c_observation_evidence_packet_20260511184012.json`
- `/home/ubuntu/workspace/hermes/outputs/sachima/pe1c_observation_evidence_packet_20260511184012.md`

Safe evidence summary:

```text
PE-1B: observation_delta=3, workflow_delta=3, no_leak_scan=true, Temporal service/Worker=false
PE-1C: disabled allow_platforms=[], runtime_call_count=0, restored obs 4->5, workflows 4->5, no_leak_scan=true
```

## Drafted Artifacts

Created:

- `docs/plans/2026-05-11-flowweaver-pe1d-pe2-readiness-decision-packet.md`
- `docs/runbooks/flowweaver-pe1d-pe2-readiness-decision.md`
- `docs/dev_log/2026-05-11-flowweaver-pe1d-pe2-readiness-decision-packet.md`

Updated existing FlowWeaver changed-file guard allowlists to recognize those three decision-packet docs only. No production/runtime code changed.

## Decision Captured

```text
pe1d_readiness_conditional_go_for_longer_controlled_local_observation
pe2_design_conditional_go_for_design_packet_only
pe2_implementation_no_go
pe2_live_default_on_no_go
```

Meaning:

- PE-1D longer loopback-only controlled observation can be requested separately.
- PE-2 can be designed separately, but implementation/live/default-on is blocked.
- No delivery control, agent execution expansion, real external ingress, config write, restart/reload, adapter mutation, or Gateway-owned Temporal lifecycle is approved.

## Verification Log

```text
STATIC_DOC_GATE_PASS changed_count=17

git diff --check: PASS

python -m py_compile gateway/flowweaver_production_shadow_observation.py gateway/flowweaver_ai_flow_pilot.py
=> PASS

python -m pytest -q tests/gateway/test_flowweaver_pe1_controlled_sachima_shadow_observation.py
=> 4 passed in 3.01s

python -m pytest -q tests/gateway/test_flowweaver_production_shadow_observation.py tests/gateway/test_flowweaver_ai_flow_pilot.py
=> 22 passed in 3.28s

python -m pytest -o addopts= -n 4 -q tests/integration/test_flowweaver_phase21_production_shadow_observation.py tests/integration/test_flowweaver_phase33_ai_flow_pilot.py
=> 9 passed in 1.93s

scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
=> 715 passed in 6.26s

STATIC_NO_LEAK_AND_BOUNDARY_SCAN_PASS changed_count=17
```

## Review Status

Fresh-context blocker reviews: PASS, blockers none.

Review notes confirmed:

```text
- PE-1D only requests a separately approved longer loopback-only controlled observation window;
- PE-2 is limited to a separate design packet only;
- PE-2 implementation/live/default-on remains NO-GO;
- no real external ingress, production config write, Gateway restart/reload, adapter mutation, production delivery control, production agent/tool execution, or Gateway-owned Temporal lifecycle is approved;
- changed files are limited to three docs plus exact FlowWeaver guard allowlist maintenance;
- each guard file adds only the three PE-1D/PE-2 readiness doc paths;
- no raw payload, secret, private platform ID, or raw exception leakage was found.
```
