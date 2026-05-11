# FlowWeaver PE-1 Controlled Sachima Production-Shadow Observation Plan

## Status

Approved by 狗哥 in Feishu for PE-1 implementation only:

```text
controlled Sachima production-shadow observation design/implementation, default-off and observation-only
```

This plan does not approve production config writes, Gateway restart/reload, platform adapter mutation, production delivery control, production agent/tool execution, Gateway-owned Temporal lifecycle, or live/default-on rollout.

## Baseline

```text
Repository: jovijovi/sachima
Base branch: feature/sachima-channel
Base HEAD: c52dc8034b75
Worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-pe1-controlled-sachima-shadow-observation
```

Relevant prior verdict:

```text
conditional_go_for_pe1_controlled_sachima_production_shadow_observation
```

## Objective

Turn the generic default-off production-shadow sidecar into the first PE-1 production-facing gate by narrowing Gateway observation starts to an exact Sachima-only allowlist.

PE-1 may observe sanitized Sachima Gateway turns through an injected runtime control surface. PE-1 must not control delivery, invent ACKs, call production agent/tool executors, mutate platform adapters, write config, restart Gateway, or own runtime lifecycle.

## Implementation Shape

1. Add a PE-1 policy resolver:

```text
pe1_controlled_sachima_shadow_policy_from_config(config, platform=...)
```

2. Keep the existing read-only config shape:

```yaml
flowweaver:
  production_shadow_observation:
    enabled: false
    platform_allowlist: []
    timeout_ms: 250
```

3. Require the exact enabled shape for observation starts:

```yaml
flowweaver:
  production_shadow_observation:
    enabled: true
    platform_allowlist: [sachima]
    timeout_ms: 250
```

4. If the platform is not `sachima`, or if the allowlist is missing, empty, invalid, duplicated, reordered into a noncanonical list, or contains extra platforms, PE-1 returns an enabled-but-not-allowlisted policy that produces no runtime start.

5. Update Gateway's existing shadow sidecar hook to use the PE-1 policy resolver. The hook remains after response normalization and must not mutate `response`, `delivery_state`, `already_sent`, `should_skip_final_text()`, adapter send behavior, or ACK state.

6. Add PE-1 focused tests for:

- default-off behavior;
- exact Sachima allowlist gating;
- non-Sachima platforms being skipped even if operator configured them;
- runtime-control-surface injection only;
- start/query-only calls;
- no delivery ACK invention;
- final delivery state unchanged;
- no raw material in result/runtime request surfaces.

## Non-Goals

PE-1 does not include:

- production config write;
- Gateway restart/reload;
- platform adapter mutation;
- live delivery control;
- rich-card/media/final-text send control;
- real delivery ACK reconciliation;
- production agent/tool execution;
- Gateway-created Temporal Client, Worker, namespace, task queue, daemon, socket, Docker process, or subprocess lifecycle.

## Rollback / Kill Switch

Any one of these stops new PE-1 observation starts:

1. Set `flowweaver.production_shadow_observation.enabled=false`.
2. Remove `sachima` from `flowweaver.production_shadow_observation.platform_allowlist`.
3. Add any extra platform to the PE-1 allowlist, which fails closed for PE-1 starts.
4. Remove the injected runtime control surface.
5. Stop the externally managed runtime/Temporal Worker if one was separately approved.
6. Revert this PE-1 PR.

Rollback must not require raw payload inspection, mutate platform adapters, delete production data, invent ACKs, or alter final delivery behavior.

## Verification Plan

```bash
python -m pytest -q tests/gateway/test_flowweaver_pe1_controlled_sachima_shadow_observation.py
python -m pytest -q tests/gateway/test_flowweaver_production_shadow_observation.py tests/gateway/test_flowweaver_ai_flow_pilot.py
python -m pytest -o addopts= -n 4 -q tests/integration/test_flowweaver_phase21_production_shadow_observation.py tests/integration/test_flowweaver_phase33_ai_flow_pilot.py
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

Fresh-context blocker review must check default-off behavior, exact Sachima gating, no Gateway-owned lifecycle, no raw material, no final-delivery mutation, and operational approvals staying separate.
