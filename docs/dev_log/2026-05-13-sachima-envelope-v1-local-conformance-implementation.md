# Dev Log — Sachima Envelope v1 Local Conformance Implementation

Date: 2026-05-13
Branch: `feat/sachima-envelope-v1-local-conformance`
Base: `feature/sachima-channel @ 44f0fe3d225ac507ea28400dd995a72368ed87f0`
Scope: Sachima-side local protocol conformance implementation

## 1. Request

Dog Brother approved starting implementation of the Sachima protocol in the `sachima` project.

Clarification captured before implementation:

```text
Sachima protocol work is a high-priority insertion.
It does not cancel, replace, or shelve the existing FlowWeaver roadmap.
```

Working interpretation:

```text
Implement Sachima Envelope v1 local conformance in the Sachima project only.
Do not implement agentic-ui changes in this PR.
Do not perform public ingress.
Do not perform real external delivery or real IM sends.
Do not restart/reload Gateway.
Do not write production config.
Do not expand production agent/tool execution.
Do not start external Temporal services or workers.
```

## 2. Preflight

Read before changes:

- `AGENTS.md`
- `GOAL.md`
- `docs/roadmap/current-status.md`
- `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md` P4 section
- `docs/dev_log/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md`
- `docs/dev_log/2026-05-13-sachima-protocols-canonical-pointer.md`
- `docs/protocols/sachima-envelope-v1.md`
- `jovijovi/sachima-protocols` → `protocols/envelope/v1.md`

Current status at start:

```text
current_position: P4 design packet delivered — implementation not approved; protocol text promoted to sachima-protocols
next_allowed_request: Sachima Envelope v1 local conformance implementation only
```

Explicit non-approvals preserved:

```text
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
reverse_proxy_or_tls_config_write
```

Canonical checkout has known local untracked workspace files, so implementation was made in a clean worktree:

```text
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-sachima-envelope-v1-local-conformance
```

## 3. Implementation summary

Sachima-side local conformance now includes:

- v1 ingress validation when `schema_version` is present;
- required `schema_version == sachima.v1`, `role == user`, non-empty `message_id`, `chat_id`, and `user_id`;
- `content` accepted only as deprecated ingress migration alias and normalized to canonical `text` before dispatch;
- configured `allowed_users` rejection before Hermes dispatch;
- v1 delivery callback envelopes for local fallback and configured callback URLs;
- canonical delivery fields: `schema_version`, `message_id`, `chat_id`, `user_id`, `role`, `text`, `reply_to_message_id`, `metadata`;
- `SACHIMA_DELIVERY_URL` env mapping, with deprecated `SACHIMA_SEND_URL` remaining as fallback alias;
- delivery callback HMAC headers when `webhook_secret` is configured;
- fake-send simulator acceptance of v1 `text` callbacks while preserving legacy fixture compatibility.

This PR intentionally keeps behavior local/default-off and does not expose public ingress.

## 4. Verification plan

Before PR:

- RED tests for v1 ingress alias/schema/role/identity validation;
- RED test for configured user allowlist rejection;
- RED test for `SACHIMA_DELIVERY_URL` env mapping;
- RED test for signed v1 delivery callback;
- HMAC replay/body-mismatch regression tests;
- focused Sachima adapter/fake-send tests;
- fake-send local smoke script;
- syntax check for changed Python files;
- changed-file / no-leak / non-approval gates;
- independent Codex review;
- independent Claude Code review.

## 5. Current verification status

Local focused tests:

```text
64 passed
```

Command:

```text
scripts/run_tests.sh tests/gateway/platforms/test_sachima.py tests/gateway/test_sachima_platform.py tests/gateway/test_sachima_fake_send_simulator.py tests/gateway/test_sachima_fake_send_surface_contract.py -q
```

Smoke:

```text
SACHIMA_SMOKE_V1_PASS
SACHIMA_SMOKE_V1_FINAL_PASS
PHASE_B_FAKE_SEND_EVIDENCE_PASS
```

Commands:

```text
python scripts/sachima_smoke.py
python scripts/sachima_fake_send_simulator_smoke.py
```

Generated runtime evidence under `outputs/` was removed before commit; runtime evidence is not PR payload for this phase.

Syntax / lint:

```text
python -m py_compile gateway/platforms/sachima.py gateway/config.py gateway/sachima_fake_send_simulator.py scripts/sachima_smoke.py scripts/sachima_gateway_smoke.py tests/gateway/platforms/test_sachima.py tests/gateway/test_sachima_fake_send_simulator.py tests/gateway/test_sachima_platform.py
python -m ruff check gateway/platforms/sachima.py gateway/config.py gateway/sachima_fake_send_simulator.py scripts/sachima_smoke.py scripts/sachima_gateway_smoke.py tests/gateway/platforms/test_sachima.py tests/gateway/test_sachima_fake_send_simulator.py tests/gateway/test_sachima_platform.py
```

Local Nix note:

```text
nix flake check --print-build-logs
```

could not run locally because `nix` is not installed in the execution environment. GitHub required Nix checks remain the authoritative Nix verification for this PR.

Broad `tests/gateway` note:

```text
A broad local tests/gateway run still hits existing phase-specific FlowWeaver changed-file guard tests because this PR intentionally changes Sachima protocol files, not those historical FlowWeaver phase allowlists. This is treated as a baseline/guard-scope note, not a Sachima protocol regression. Focused Sachima tests are the behavior gate for this PR.
```

## 6. Independent review

Codex read-only review:

```text
VERDICT: PASS
BLOCKERS: NONE
```

Codex non-blocking notes were useful and adopted before finalization:

- add a direct JSON reserialization-mismatch HMAC probe;
- add an explicit `SACHIMA_DELIVERY_URL` over deprecated `SACHIMA_SEND_URL` precedence test.

Claude Code read-only review:

```text
VERDICT: PASS
BLOCKERS: NONE
```

Claude specifically checked Unix-second timestamps, exact-body HMAC signing, delivery URL precedence, local-only loopback defaults, outbound `role=assistant`, and non-approval boundaries.

## 7. Final verification and re-review

Final local verification before PR:

```text
64 passed
SACHIMA_SMOKE_V1_FINAL_PASS
PHASE_B_FAKE_SEND_EVIDENCE_PASS
SACHIMA_ENV_V1_IMPL_FINAL_CHANGED_FILE_GATE_PASS
SACHIMA_ENV_V1_IMPL_FINAL_MARKER_GATE_PASS
SACHIMA_ENV_V1_IMPL_FINAL_POINTER_GATE_PASS
SACHIMA_ENV_V1_IMPL_FINAL_ADDED_LINES_NO_LEAK_GATE_PASS
SACHIMA_ENV_V1_IMPL_FINAL_NON_APPROVAL_GATE_PASS
```

Final narrow re-review after adopting Codex's two test suggestions:

```text
Codex rereview: PASS, BLOCKERS: NONE
Claude Code rereview: PASS, BLOCKERS: NONE
```

No reviewer reported blocker-level security, logic, protocol, or roadmap drift issues. agentic-ui/cross-repo conformance, public ingress, live/default-on behavior, Gateway restart/reload, production config writes, and real delivery remain out of scope.
