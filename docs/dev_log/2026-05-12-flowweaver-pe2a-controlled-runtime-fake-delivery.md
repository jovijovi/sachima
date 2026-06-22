# FlowWeaver PE-2A Controlled Runtime + Fake Delivery Implementation Dev Log

## Scope

User approval received:

```text
approve_pe2a_controlled_runtime_fake_delivery_implementation_no_live_no_real_external_ingress
```

Approved scope:

- implement PE-2A controlled runtime + fake delivery bridge;
- use sanitized Sachima ingress envelopes only;
- call a caller-supplied runtime control surface only;
- use Phase B fake-send simulator semantics only;
- record ACKs only after fake-send accepts a request;
- produce sanitized local evidence and runbook;
- use TDD, independent review, Codex read-only review, CI, PR, and post-merge verification.

Still not approved:

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
```

## Base / Worktree

```text
origin/feature/sachima-channel @ 84f6a9010d72fe6ab3a0dac4ecaea3c3fb252ddf
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-pe2a-controlled-runtime-fake-delivery
branch: feat/pe2a-controlled-runtime-fake-delivery
```

Canonical checkout had local untracked files, so implementation and verification use the clean workspace worktree.

## Context preflight

This is a high-context PR/CI/review task. Use concise Feishu progress only, keep raw logs out of chat, and persist state here, in the runbook, evidence, and PR body. At phase boundaries, prefer handoff/compression over carrying another large phase in chat.

## TDD Log

RED:

```text
python -m pytest tests/gateway/test_flowweaver_pe2_controlled_runtime_delivery_bridge.py -q
ModuleNotFoundError: gateway.flowweaver_pe2_controlled_runtime_delivery_bridge
```

GREEN focused:

```text
python -m pytest tests/gateway/test_flowweaver_pe2_controlled_runtime_delivery_bridge.py -q
10 passed
```

Fixes during GREEN:

- allowed fake response `message_id` only in fake response validation; the bridge result/evidence still does not expose it;
- accepted Phase B ACK refs with four-digit sequence format such as `runtime_event_delivery_ack_0001`;
- preserved fail-closed behavior for unsafe runtime output, missing fake surface, disabled policy, private/raw material, rejected delivery refs, and duplicate ingress.

## Files Changed

- `gateway/flowweaver_pe2_controlled_runtime_delivery_bridge.py`
- `tests/gateway/test_flowweaver_pe2_controlled_runtime_delivery_bridge.py`
- `scripts/flowweaver_pe2_controlled_runtime_fake_delivery_smoke.py`
- `docs/runbooks/flowweaver-pe2-controlled-runtime-fake-delivery.md`
- `docs/dev_log/2026-05-12-flowweaver-pe2a-controlled-runtime-fake-delivery.md`

## Verification Status

Local verification passed before review:

```text
git diff --check: pass
PE-2A focused tests: 10 passed
existing Sachima fake-send/platform focused tests: 54 passed
PE2A_CONTROLLED_RUNTIME_FAKE_DELIVERY_EVIDENCE_PASS
PE2A_FINAL_GATE_PASS
PE2A_CHANGED_FILE_AND_NO_LEAK_GATE_PASS
```

Independent review round 1:

```text
consistency / phase-gate review: PASS
security / low-intrusion review: BLOCK
```

Security blockers found and fixed:

1. Partial fake-send failure could record earlier runtime ACKs before a later fake-send rejection. Fix: collect and validate all fake-send ACKs first, then record runtime ACKs only after all sends are accepted; added regression `test_later_fake_send_rejection_does_not_record_partial_runtime_ack`.
2. Runtime ACK responses could omit target fields and still count as ACK updates. Fix: require exact `workflow_id`, `transaction_id`, `delivery_ref`, `ack_ref`, and `surface` echoes; added regression `test_runtime_ack_response_must_echo_ack_target_fields`.
3. Evidence builder trusted caller-supplied counts. Fix: require checked result type/version/ok, exact side-effect empty list, runtime operation count consistency, ACK-ref count consistency, and derive fake-send request / ACK / duplicate / rejection counts from sanitized `delivery_events`, `duplicate_ingress_refs`, and `rejected_probe_codes`; added regressions `test_evidence_builder_rejects_forged_ack_counts` and `test_evidence_builder_rejects_forged_fake_send_overclaim`.

Fresh verification after blocker fixes:

```text
git diff --check: pass
PE-2A focused tests: 15 passed
existing Sachima fake-send/platform focused tests: 54 passed
PE2A_CONTROLLED_RUNTIME_FAKE_DELIVERY_EVIDENCE_PASS
PE2A_FINAL_GATE_PASS
PE2A_CHANGED_FILE_AND_NO_LEAK_GATE_PASS
```

Evidence:

```text
repo-local runtime artifact: outputs/sachima/pe2a-controlled-runtime-fake-delivery/pe2a_controlled_runtime_fake_delivery_evidence.json
workspace durable copy: /home/ubuntu/workspace/hermes/outputs/sachima/pe2a-controlled-runtime-fake-delivery/pe2a_controlled_runtime_fake_delivery_evidence.json
```

Evidence counts:

```text
accepted_ingress_envelopes: 2
duplicates: 1
fake_send_requests: 5
runtime_ack_updates: 4
runtime_delivery_plan_requests: 3
runtime_start_requests: 3
rejected_probes: 2
no_leak_scan: pass, raw_marker_hits=0
```

Codex read-only review round 1:

```text
BLOCK
```

Codex blocker and fix:

- Blocker: stateless helper reuse with the same fake-send simulator can receive duplicate fake-send ACKs from Phase B idempotency semantics. The bridge skipped runtime ACKs for duplicate fake-send responses but still built success delivery events from the full delivery plan, which raised a raw `delivery_event_count_mismatch` runtime error.
- Fix: represent duplicate fake-send responses as sanitized delivery events with `duplicate=true`, count them as duplicate fake-send events, skip runtime ACK recording for them, and return a stable sanitized success result; added regression `test_stateless_helper_handles_duplicate_fake_send_without_raw_exception`.

Fresh focused verification after Codex blocker fix:

```text
PE-2A focused tests: 15 passed
PE2A_CONTROLLED_RUNTIME_FAKE_DELIVERY_EVIDENCE_PASS
PE2A_FINAL_GATE_PASS
```

Codex blocker-only re-review:

```text
PASS
```

Final pre-PR local gate:

```text
git diff --check: pass
PE-2A focused tests: 15 passed
existing Sachima fake-send/platform focused tests: 54 passed
PE2A_CONTROLLED_RUNTIME_FAKE_DELIVERY_EVIDENCE_PASS
PE2A_FINAL_GATE_PASS
PE2A_CHANGED_FILE_AND_NO_LEAK_GATE_PASS
```

Remaining before PR:

```text
commit / push / PR / GitHub CI
```
