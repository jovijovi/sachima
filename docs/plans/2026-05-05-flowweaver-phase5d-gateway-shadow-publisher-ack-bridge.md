# FlowWeaver Phase 5D Gateway Shadow Publisher / ACK Bridge Implementation Plan

> **For Hermes:** This document is the Phase 5D design gate. Do not write implementation code until the user explicitly approves this plan. After approval, use `subagent-driven-development` task-by-task with strict TDD and independent review.

**Goal:** Add a default-off Gateway shadow publisher / ACK bridge that converts already-safe FlowWeaver Gateway shadow material into runtime-start and delivery-ACK request shapes without changing visible IM behavior, starting services, or connecting production Gateway to Temporal by default.

**Architecture:** Keep Phase 5D as a Gateway-side shadow bridge first. A new pure helper builds a safe publication summary from the existing Phase 4H dry-run chain and Phase 5A runtime ingress envelope, plus sanitized `record_delivery_ack` update requests derived only from Gateway delivery-state booleans/counts. A tiny optional `gateway/run.py` hook may attach the summary under an explicit config flag, but it must not import Temporal/MCP/Phase 5C runtime client, start workers, write config, or send/edit/render/persist/log any new user-visible surface.

**Tech Stack:** Python, existing Gateway FlowWeaver helpers, pytest, `scripts/run_tests.sh`; no new runtime dependencies.

---

## Current Baseline

- Canonical repo: `/home/ubuntu/workspace/hermes/repo/sachima`
- Feature worktree: `/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge`
- Branch: `feat/flowweaver-phase5d-gateway-shadow-publisher-ack-bridge`
- Base branch: `feature/sachima-channel`
- Base commit: `ea8e6bf53008196768db24efedf21f8a585f6141` (PR #29 / Phase 5C merge)
- PR #29 is merged.
- Canonical repo has unrelated pre-existing untracked items; they must not be included in this phase:
  - `.hermes/`
  - `docs/plans/2026-04-24-sachima-channel.md`
  - `docs/superpowers/`

## Why Phase 5D

The Phase 5 architecture gate names the next sequence as:

```text
Phase 5A: durable runtime ingress contract, pure helper, no Temporal import
Phase 5B: local Temporal POC under prototypes/, no Gateway wiring, no service auto-start
Phase 5C: narrow native tool or MCP-facing runtime client, still default-off
Phase 5D: Gateway shadow publisher / ACK bridge, default-off and no visible behavior change
```

Phase 5C landed the prototype runtime client/MCP surface. The next safe move is therefore **not** full live Gateway → Temporal orchestration. It is a shadow bridge that proves Gateway can derive runtime-start and delivery-ACK requests from sanitized Gateway state while staying invisible and off by default.

## Critical Findings That Shape Phase 5D

1. Existing `gateway/run.py` already has a default-off FlowWeaver shadow/dry-run seam:
   - config resolved around `task_tracker.flowweaver_shadow` and `task_tracker.flowweaver_shadow_dry_run`;
   - shadow capture and dry-run attach after the agent result is produced;
   - no visible behavior change when only shadow collection is enabled.
2. `gateway/flowweaver_runtime_contract.py` can already project safe shadow descriptor/corpus/mock-durable/dry-run inputs into a Phase 5A runtime ingress envelope.
3. Phase 5C runtime client is prototype-only and lives under `prototypes/flowweaver_phase5c_runtime_client`. Production Gateway should not import it in Phase 5D.
4. Phase 5B/5C currently use a POC start payload model where `RuntimeStartPayload.transaction_id` is the fixed `runtime_tx_replay_corpus`. That is acceptable for a corpus POC, but it is **not** safe as a live per-turn publisher because multiple Gateway turns would collide. This is the big trap. Phase 5D should build **shadow publication requests and ACK bridge evidence**, not silently start real workflows from live Gateway turns.
5. Delivery ACK belongs to Gateway/platform delivery state. The bridge may derive safe ACK update requests from `delivery_state`, but it must never expose raw message IDs, chat IDs, user IDs, platform payloads, card JSON, or platform-specific ACK bodies.

## Scope Boundary

### In scope

1. A new pure Gateway helper module that builds a safe shadow runtime publication summary from already-safe FlowWeaver shadow/dry-run state.
2. A new ACK bridge projection that emits safe `record_delivery_ack` update request dictionaries using only synthetic IDs, surfaces, target kinds, target IDs, and statuses.
3. A default-off config helper that requires all prior gates plus an explicit Phase 5D flag.
4. A narrow optional `gateway/run.py` hook under the existing FlowWeaver shadow attach block, only to attach the safe summary into `agent_result` when explicitly enabled.
5. Focused Gateway tests for helper behavior, run-loop default-off behavior, no visible side effects, no raw payload leakage, and no runtime/service imports.
6. Dev log updates for Phase 5D.

### Out of scope for Phase 5D

1. No live Temporal publish from Gateway.
2. No direct import of `temporalio`, `flowweaver_runtime_client`, `flowweaver_temporal_poc`, `mcp`, or MCP server modules from Gateway code.
3. No worker, daemon, Docker, Temporal CLI, service startup, Gateway restart, or background process lifecycle changes.
4. No production Hermes tool registration.
5. No writes to `~/.hermes/config.yaml`, `mcp_servers`, or any real user config.
6. No changes to platform adapters under `gateway/platforms/**`.
7. No platform-specific ACK listener implementation.
8. No raw message IDs, chat IDs, user IDs, platform payloads, raw tool output, raw prompts, card JSON, credentials, tokens, or connection strings in docs, tests, logs, summaries, PR body, or tool-visible output.
9. No attempt to generalize Phase 5B variable transaction IDs in this phase. If reviewers decide that is required first, the phase must be revised before implementation.

## Design: Shadow Runtime Publication Summary

### New config key

Use a new explicit task-tracker flag:

```text
display.task_tracker.flowweaver_shadow_runtime_publish: true
```

The helper must return true only when all three are true:

```text
flowweaver_shadow == true
flowweaver_shadow_dry_run == true
flowweaver_shadow_runtime_publish == true
```

This keeps Phase 5D downstream of the existing safe shadow and dry-run gates.

### New agent-result key

Attach the summary only under:

```text
flowweaver_shadow_runtime_publication
```

The summary type should be:

```text
flowweaver.gateway.shadow_runtime_publication.v0
```

### Summary shape

The accepted summary should be narrow and safe:

```python
{
    "type": "flowweaver.gateway.shadow_runtime_publication.v0",
    "verdict": "ready",
    "reason": "ok",
    "runtime_model_version": "flowweaver.runtime.v0",
    "runtime_envelope_type": "flowweaver.gateway.runtime_ingress_envelope.v0",
    "transaction_id": "runtime_tx_replay_corpus",
    "workflow_id": "runtime_tx_replay_corpus",
    "start_request": {
        "operation": "start_transaction",
        "workflow_id": "runtime_tx_replay_corpus",
        "start_payload": {
            "transaction_id": "runtime_tx_replay_corpus",
            "idempotency_key": "runtime_event_start_runtime_tx_replay_corpus",
            "entry_count": 1,
            "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
            "allowed_runtime_events": ["start_transaction", "record_operation", "publish_artifact", "plan_delivery", "record_delivery_ack", "approve_intent", "reject_intent", "cancel_transaction", "resume_after_user_input"],
            "claim_check_policy": {"mode": "references_only", "allowed_reference_fields": ["ref", "kind", "count", "size", "checksum_hint"], "forbidden_material": [...]},
        },
    },
    "ack_bridge": {
        "status": "ready",
        "updates": [
            {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_final_text_0",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_0",
                "status": "sent",
            }
        ],
    },
    "checks": {
        "shadow_capture_present": True,
        "dry_run_summary_valid": True,
        "runtime_envelope_valid": True,
        "start_request_safe": True,
        "delivery_ack_updates_safe": True,
        "payloads_absent": True,
        "visible_side_effects_absent": True,
        "runtime_side_effects_absent": True,
    },
    "side_effects": [],
}
```

The actual implementation may trim fields further if tests prove a smaller shape is enough. It must not add raw source fields.

### Rejection shape

For invalid/missing inputs, return a safe rejection summary:

```python
{
    "type": "flowweaver.gateway.shadow_runtime_publication.v0",
    "verdict": "rejected",
    "reason": "invalid_shadow" | "dry_run_missing" | "runtime_envelope_rejected" | "unsafe_delivery_state",
    "runtime_model_version": "flowweaver.runtime.v0",
    "start_request": None,
    "ack_bridge": {"status": "rejected", "updates": []},
    "checks": {... booleans ...},
    "side_effects": [],
}
```

Never echo exception text or offending values into `reason`, `agent_result`, user-visible output, or logs. Gateway hook failures should log only a stable sanitized message such as `FlowWeaver shadow runtime publication attach failed` plus no raw exception string.

## ACK Bridge Rules

The ACK bridge maps Gateway-owned delivery state to safe `record_delivery_ack` updates.

Allowed inputs:

- `delivery_state.final_text.sent` boolean.
- `delivery_state.rich_cards_sent` count and bounded plain records only after message/platform IDs are ignored.
- Optional progress-card state only if it is already represented safely by the Gateway delivery state in this repo.

Allowed outputs:

- `event_type`: always `record_delivery_ack`.
- `delivery_key`: synthetic, starts with `runtime_event_delivery_ack_`.
- `surface`: closed set from Phase 5B (`final_text`, `rich_card`, `progress_card`, `media`, `prototype`).
- `target_kind`: `delivery`.
- `target_id`: synthetic, starts with `runtime_delivery_`.
- `status`: `sent`, `failed`, or `acknowledged`.

Forbidden:

- Platform message ID (`om_...`, `msg_...`, etc.).
- Chat/user/session/thread IDs.
- Full card JSON.
- Raw platform response.
- Raw adapter error text.
- Any secret-shaped string.

If the bridge cannot derive a safe ACK, it should omit that update and include only a safe count/reason such as `unsafe_delivery_state`, never the raw values.

## Proposed Files

### Create

- `gateway/flowweaver_shadow_publisher.py`
- `tests/gateway/test_flowweaver_shadow_publisher.py`
- `tests/gateway/test_flowweaver_shadow_publisher_run_hook.py` (only if a separate run-loop fixture is clearer than extending `test_run_progress_topics.py`)

### Modify

- `gateway/run.py` — only a tiny default-off hook under the existing FlowWeaver shadow/dry-run seam.
- `tests/gateway/test_run_progress_topics.py` — only if reusing its existing `GatewayRunner` test harness is cleaner than adding a new run-hook test file.
- `docs/dev_log/2026-05-05-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge.md`

### Must not modify

- `gateway/platforms/**`
- `run_agent.py`
- `model_tools.py`
- `toolsets.py`
- `tools/**`
- `mcp_serve.py`
- `prototypes/flowweaver_phase5c_runtime_client/**` unless Phase 5D is explicitly revised to include a prototype-only adapter change
- `~/.hermes/config.yaml`

## Implementation Tasks After Approval

### Task 1: Add RED tests for Phase 5D default-off and forbidden-surface boundaries

**Objective:** Prove the new publisher gate is opt-in and does not widen production runtime/tool/service behavior.

**Files:**
- Create: `tests/gateway/test_flowweaver_shadow_publisher.py`

**Tests to add:**
- `is_flowweaver_shadow_runtime_publish_enabled({}) is False`.
- Enabling only `flowweaver_shadow_runtime_publish` is not enough.
- Enabling shadow + publish without dry-run is not enough.
- Enabling shadow + dry-run + publish is true.
- Diff-hunk-aware source scan rejects **new Phase 5D additions** that import/call `temporalio`, `flowweaver_runtime_client`, `flowweaver_temporal_poc`, `mcp`, `subprocess`, `docker`, `Popen`, `Client.connect`, `Worker`, `start_workflow`, or `execute_update` in Gateway code. Existing baseline occurrences in unchanged `gateway/run.py` lines do not count; the scanner must compare against the merge-base/base branch or inspect `git diff -U0` added lines plus full content of brand-new files.
- Changed-file guard forbids edits under `gateway/platforms/**`, `tools/**`, `model_tools.py`, `toolsets.py`, `run_agent.py`, and config writes.

**Run:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher.py -q
```

**Expected RED:** import/module missing except for any guard tests that can pass before implementation.

### Task 2: Add RED tests for safe publication summary construction

**Objective:** Specify the exact safe summary produced from existing shadow/dry-run state.

**Files:**
- Modify: `tests/gateway/test_flowweaver_shadow_publisher.py`

**Tests to add:**
- Build a normal shadow `agent_result` using `attach_flowweaver_shadow_snapshot()` and `run_flowweaver_gateway_shadow_dry_run()` fixtures.
- Assert `build_flowweaver_shadow_runtime_publication(agent_result)` returns type `flowweaver.gateway.shadow_runtime_publication.v0`, verdict `ready`, safe runtime IDs, start request with closed operation `start_transaction`, and no side effects.
- Assert the summary includes a start payload derived from Phase 5A envelope fields only.
- Assert raw shadow snapshot/capture/full agent result is not copied into the summary.
- Assert rejection for missing shadow capture, missing dry-run, malformed dry-run, or failed dry-run is safe and does not echo raw values.

**Run:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher.py -q
```

**Expected RED:** helper missing.

### Task 3: Add RED tests for ACK bridge projection and redaction

**Objective:** Lock down safe delivery ACK update request generation.

**Files:**
- Modify: `tests/gateway/test_flowweaver_shadow_publisher.py`

**Tests to add:**
- `delivery_state.final_text.sent=True` yields one `record_delivery_ack` update with synthetic delivery key and `surface="final_text"`.
- Rich-card delivery records can contribute only safe `surface="rich_card"` ACK updates; message IDs are ignored.
- Unsafe delivery state containing `om_...`, `oc_...`, `ou_...`, `chat_id`, `user_id`, `message_id`, `card_json`, raw adapter errors, or secret-shaped strings does not appear in `repr(summary)`.
- Hostile `Mapping`, mutating keys, and post-validation flickering values are rejected or projected from safe copied data only.
- Duplicate ACK derivation is deterministic and idempotent.

**Run:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher.py -q
```

**Expected RED:** ACK bridge missing.

### Task 4: Implement `gateway/flowweaver_shadow_publisher.py`

**Objective:** Add the pure default-off shadow publisher/ACK bridge helper.

**Files:**
- Create: `gateway/flowweaver_shadow_publisher.py`

**Implementation notes:**
- Import only existing Gateway FlowWeaver helpers and stdlib.
- Use exact `type(...) is dict/list/str/int/bool` checks for external-ish data.
- Build outputs from sanitized constants, counts, and Phase 5A envelope fields; do not reuse raw nested input objects.
- Fail closed to stable `reason` strings.
- Keep `side_effects` as an empty list.
- Include `__all__` for public helper names.
- Do not import Phase 5B/5C prototype packages or Temporal/MCP.

**Run:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher.py -q
python -m py_compile gateway/flowweaver_shadow_publisher.py
```

**Expected GREEN:** helper tests pass.

### Task 5: Add RED run-loop hook tests

**Objective:** Prove Gateway attaches the summary only when the explicit Phase 5D gate is on, and remains invisible otherwise.

**Files:**
- Create: `tests/gateway/test_flowweaver_shadow_publisher_run_hook.py` or modify `tests/gateway/test_run_progress_topics.py`

**Tests to add:**
- With default config, no `flowweaver_shadow_runtime_publication` appears in the agent result.
- With shadow + dry-run enabled but Phase 5D publish flag absent, no publication summary appears.
- With all three flags enabled and a fake agent/tool callback, the returned `agent_result` has the publication summary.
- Adapter `sent`, `edits`, `cards_sent`, and `cards_patched` counts remain exactly the same as the pre-Phase-5D path except for existing task-tracker behavior when separately enabled.
- If the publisher helper raises, Gateway catches it, emits only a stable sanitized debug log message, and does not fail the user response. Add a `caplog` test where the raised exception contains raw IDs/secret-shaped text and assert those values do not appear in `agent_result`, adapter sends/edits/cards, or logs.

**Run:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher_run_hook.py -q
```

or, if extending existing harness:

```bash
scripts/run_tests.sh tests/gateway/test_run_progress_topics.py -q
```

**Expected RED:** run hook missing.

### Task 6: Implement the tiny `gateway/run.py` hook

**Objective:** Wire the pure helper into the existing FlowWeaver shadow block without changing visible behavior.

**Files:**
- Modify: `gateway/run.py`

**Implementation notes:**
- Add config resolution next to existing `flowweaver_shadow_enabled` and `flowweaver_shadow_dry_run_enabled`.
- Disable Phase 5D if tracker setup fails, just like shadow/dry-run.
- After dry-run attach succeeds, conditionally call `attach_flowweaver_shadow_runtime_publication(response, enabled=True)`.
- Wrap the attach call in `try/except Exception` and fail closed with a sanitized stable debug log message only; do not interpolate `str(exc)` or offending values.
- No async network call, no runtime client, no service, no config write.
- Keep the diff tiny; if the run hook grows beyond the existing seam, stop and re-plan.

**Run:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher.py tests/gateway/test_flowweaver_shadow_publisher_run_hook.py -q
python -m py_compile gateway/run.py gateway/flowweaver_shadow_publisher.py
```

**Expected GREEN:** helper and run-hook tests pass.

### Task 7: Regression, boundary gates, and dev log

**Objective:** Verify Phase 5D did not regress prior FlowWeaver gates or widen forbidden surfaces.

**Files:**
- Modify: `docs/dev_log/2026-05-05-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge.md`

**Commands:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_publisher_run_hook.py \
  -q
python -m py_compile gateway/flowweaver_shadow_publisher.py gateway/run.py
git diff --check
```

**Custom scans:**
- Changed-file allowlist includes only approved Phase 5D files.
- Forbidden surfaces unchanged.
- Diff-hunk-aware forbidden-source scan compares against the merge-base/base branch: it fails on any **new added line** in approved Gateway files or any brand-new Gateway file containing Temporal/MCP/runtime-client imports/calls, `subprocess`/`Popen`, Docker/service/daemon/process startup, `start_workflow`, `execute_update`, `Client.connect`, `Worker`, or config-write behavior. Pre-existing unchanged `gateway/run.py` occurrences are baseline noise, not Phase 5D approval.
- No sensitive material or secret-shaped strings in diff.
- No raw platform/private IDs in tests, docs, or output fixtures; split synthetic marker strings in tests when needed.

**Independent reviews:**
- Plan/spec implementation review: no blockers.
- Security/low-intrusion review: no blockers.
- If reviewers find blockers, add RED tests first, fix, rerun focused gates and blocker-only re-review.

## Approval Boundary for Implementation

If the user approves this plan, implementation approval covers only:

- `gateway/flowweaver_shadow_publisher.py`
- `tests/gateway/test_flowweaver_shadow_publisher.py`
- `tests/gateway/test_flowweaver_shadow_publisher_run_hook.py` or the narrow equivalent in `tests/gateway/test_run_progress_topics.py`
- the tiny existing-seam hook in `gateway/run.py`
- this Phase 5D dev log
- focused tests, `py_compile`, `git diff --check`, scans, independent review, commit, push, and PR creation

Implementation approval does **not** cover:

- live Temporal publishing from Gateway
- importing Phase 5C runtime client from Gateway
- starting workers/services/Docker/daemon/Temporal CLI
- editing platform adapters
- editing global Hermes tools/toolsets/registry
- writing real config or secrets
- Gateway restart
- PR merge
- remote branch deletion

## Risks / Tradeoffs

1. **Fixed POC transaction ID:** Phase 5B currently models one POC transaction ID. Phase 5D must not pretend this can safely publish arbitrary live Gateway turns. The safe move is shadow publication evidence only.
2. **`gateway/run.py` is large and high-risk:** Keep the hook tiny and entirely inside the existing FlowWeaver shadow block. If the hook needs broad refactoring, stop and re-plan.
3. **ACK semantics can get mushy fast:** Delivery ACK must remain Gateway-owned and synthetic. Do not pass platform message IDs or raw platform responses into runtime-shaped requests.
4. **False-positive scans:** Static boundary strings like `send`, `edit`, `persist`, and `temporal` can appear in forbidden-side-effect metadata, and `gateway/run.py` already has unrelated baseline `mcp`/process/service code. Scans must be diff-hunk-aware and distinguish existing baseline code/metadata from new Phase 5D imports, calls, or lifecycle behavior.
5. **No visible behavior change:** Phase 5D should not improve the UI. That is intentional. The only observable change under explicit flag is an internal safe summary in `agent_result` for tests/future runtime plumbing.

## Open Questions

1. Should Phase 5E be “variable synthetic runtime IDs + local runtime publish adapter” before any true Gateway → Temporal start? My recommendation: yes. Phase 5D should expose the fixed-ID limitation explicitly and not paper over it.
2. Should ACK updates represent both `final_text` and `rich_card` surfaces for the same synthetic delivery, or only the final text surface until artifact/delivery indexing is richer? My recommendation: start with final text plus bounded rich-card count projection; reject anything ambiguous.
3. Should the Phase 5D summary include full `start_request`, or only counts/checks and a claim-check ref to the request? My recommendation: include the full request because it is already safe, small, and directly validates the bridge contract.
