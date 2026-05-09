# FlowWeaver Phase 21 Production-Shadow Observation-Only Plan

## Status

Approved by 狗哥 for implementation on 2026-05-09.

## Objective

Add the smallest production-shadow observation path for real Gateway turns: when explicitly enabled, Gateway reduces a completed turn to a sanitized observation envelope and mirrors it into the existing FlowWeaver runtime control surface using start/query only.

Strongest allowed verdict:

```text
ready_for_separate_delivery_or_agent_execution_design
```

This is intentionally weaker than production delivery or Temporal-backed agent execution.

## Approved Operational Shape

This phase uses the conservative Codex-reviewed shape:

- Gateway hook path: `GatewayRunner._handle_message_with_agent`, after final response normalization / rich-result handling and before the final `should_skip_final_text()` return decision.
- Enablement key: `flowweaver.production_shadow_observation.enabled`, default `false`.
- Narrow scope: enabled observation still requires an allowlisted platform via `flowweaver.production_shadow_observation.platform_allowlist`.
- Runtime handling: Gateway only uses a caller-supplied runtime control surface, expected on `GatewayRunner._flowweaver_runtime_control_surface` or in tests; Gateway does not create Temporal clients, Workers, task queues, namespaces, services, daemons, sockets, or subprocesses.
- Timeout: the hook is a bounded sidecar. Observation failure or timeout must return a sanitized counter/result and must not alter final response delivery behavior.
- Rollback/kill-switch: set the enablement flag false, remove the allowlist entry, or remove the injected runtime control surface. New observation starts stop immediately. Existing safe query evidence may still be checked through the externally managed runtime.
- Observability/logging: sanitized counters and stable codes only; no raw prompt, message text, platform/chat/user/message identifiers, card JSON, tool output, media path, callback payload, credential-shaped value, or raw exception text.

## Scope

Create:

- `gateway/flowweaver_production_shadow_observation.py`
- `tests/gateway/test_flowweaver_production_shadow_observation.py`
- `tests/integration/test_flowweaver_phase21_production_shadow_observation.py`
- `docs/runbooks/flowweaver-production-shadow-observation.md`
- `docs/dev_log/2026-05-11-flowweaver-phase21-production-shadow-observation-only.md`

Narrowly modify:

- `gateway/run.py` to call the bounded observation sidecar from the approved hook point.

May extend:

- `gateway/flowweaver_temporal_observation_bridge.py` only if the Phase 21 wrapper needs a safe public constant/export.

## Non-Goals

- No production Gateway restart.
- No production config write.
- No platform adapter mutation.
- No send/edit/render/callback behavior change.
- No delivery ACK reconciliation from real sends.
- No Temporal-backed agent/tool execution.
- No Gateway-owned Temporal Worker/service lifecycle.
- No remote branch deletion.

## TDD Plan

1. RED import/API test for the Phase 21 module and entrypoint.
2. RED default-off Gateway behavior test proving no runtime calls and unchanged response/delivery state.
3. RED enabled-path test proving exactly start/query observation calls with safe reduced envelopes only.
4. RED missing-runtime/runtime-failure/unsafe-output/timeout tests proving sanitized fail-closed results.
5. RED kill-switch test proving enabled observes once, disabled stops new starts, and existing query remains safe.
6. RED integration test against a local test-managed Temporal Worker proving history JSON and event bytes contain no forbidden material.
7. GREEN minimal implementation.
8. Static forbidden-surface/diff allowlist guard.
9. Codex blocker review before commit.

## Verification Commands

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_production_shadow_observation.py -q

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0   /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4   tests/integration/test_flowweaver_phase21_production_shadow_observation.py   tests/integration/test_flowweaver_phase20_temporal_observation_validation.py   tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py   -q

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile   gateway/flowweaver_production_shadow_observation.py   gateway/flowweaver_temporal_observation_bridge.py   tests/gateway/test_flowweaver_production_shadow_observation.py   tests/integration/test_flowweaver_phase21_production_shadow_observation.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check   gateway/flowweaver_production_shadow_observation.py   gateway/flowweaver_temporal_observation_bridge.py   tests/gateway/test_flowweaver_production_shadow_observation.py   tests/integration/test_flowweaver_phase21_production_shadow_observation.py

git diff --check
```

## Review Gate

Codex and Hermes verification must both return PASS for:

- default-off production behavior unchanged;
- enabled path observation-only;
- no Gateway-owned Worker/service lifecycle;
- no raw material in history/logs/snapshots/runtime requests;
- delivery surfaces remain separate;
- bounded sidecar timeout protects final delivery;
- kill-switch/rollback behavior tested;
- production config writes/restarts documented as separate approvals.
