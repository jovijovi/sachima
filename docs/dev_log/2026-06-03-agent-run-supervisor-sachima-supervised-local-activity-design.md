# agent-run-supervisor × Sachima Supervised Local Activity Design — Dev Log

## Scope

User approved:

```text
清理 PR #97 分支/worktree，并批准开启 agent-run-supervisor × Sachima supervised local Activity design packet：no live, no Gateway, no real delivery
```

Interpretation:

- Clean up merged PR #97 branch/worktree.
- Create a docs-only design packet for the next Sachima-owned supervised local Activity layer.
- Do **not** implement runtime code.
- Do **not** touch Gateway, platform adapters, production config, live/default-on behavior, real ingress, or real delivery.

## Cleanup Evidence

PR #97 was verified merged before cleanup:

```text
PR #97 state: MERGED
head: feat/agent-run-supervisor-local-offline-integration
base: release/sachima
merge commit: 5affc2fbb68d483683cd61c0871cec528127388e
open PRs using head branch: 0
```

Cleanup result:

```text
remote branch remaining: 0
local branch remaining: 0
worktree remaining: no
canonical release/sachima: clean at 5affc2fbb68d483683cd61c0871cec528127388e
```

Audit log:

```text
/home/ecs-user/workspace/hermes/logs/sachima-pr97-cleanup-20260603-220742
```

## Design Basis

Read before drafting:

- `GOAL.md`
- `docs/roadmap/current-status.md`
- `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md`
- `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-implementation.md`
- `sachima_supervisor/local_offline.py`
- `agent-run-supervisor/GOAL.md`
- `agent-run-supervisor/docs/AI_FLOW.md`
- CodeGraph exploration of `CallerInvocationSpec`, `CallerResult`, `invoke_caller`, `AgentRoleSpec`, and session runtime structures

## Key Decision

The next layer is a **Sachima/FlowWeaver supervised local Activity**, not Gateway code.

It designs:

- Activity request and response contract;
- role/permission mapping;
- start/query/update/retry/close/cancel semantics;
- durable state shape;
- no-leak/logging rules;
- future implementation approval text.

It does not approve runtime implementation, real AGENT launch, controlled AI FLOW execution, live behavior, Gateway involvement, or real delivery.

## Files Changed

Expected docs-only file set:

```text
docs/plans/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-design.md
docs/plans/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-design-manifest.yaml
docs/dev_log/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-design.md
docs/roadmap/current-status.md
```

## Verification Plan

Run before PR:

```text
manifest YAML parse
required marker gate
changed-file allowlist
secret-shaped scan
forbidden approval/surface scan
git diff --check
Codex primary review
GitHub CI after PR
```

## Explicit Non-Approvals Preserved

```text
runtime_code_implementation
real_external_sachima_ingress
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
controlled_ai_flow_execution
```
