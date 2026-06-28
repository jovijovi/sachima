# P6 Runtime Lifecycle / Controlled Attach Plan — No-code technical solution

Date: 2026-06-28
Status: **Docs-only no-code technical solution.** No source implementation, runtime start, Worker start, Gateway/Feishu/live behavior, production config, service restart, real delivery, or additional real agent/acpx/npx execution is approved here.

## 0. Architecture verdict

Build the next implementation as a **thin controlled-attach layer over the existing P6/P5 control surfaces**, not as a new runtime owner.

The core decision:

```text
P6RuntimeAttachSession (future)
  wraps existing P6ControlledAiFlowSession + P5TemporalControlSurface/P5TemporalStepExecutor
  validates caller-supplied runtime/control-surface handles
  exposes attach/start/query/update/cancel/recover/close health/rollback snapshots
  never starts Worker/service/Gateway/delivery surfaces
```

This is intentionally smaller than "real controlled AI FLOW execution". It prepares the operational lifecycle boundary needed before broader real execution.

## 1. Proposed future implementation surface

Allowed future source surface, if separately approved:

```text
sachima_supervisor/p6_runtime_attach.py              # new, default-off attach/control layer
tests/sachima_supervisor/p6_runtime_attach/unit/     # pure unit tests, no real runtime
tests/sachima_supervisor/p6_runtime_attach/hermetic/ # only if explicitly approved by the implementation gate
```

Reuse, do not rewrite:

- `sachima_supervisor/p6_controlled_ai_flow.py` — P6 admission, query/cancel/recover/close semantics.
- `sachima_supervisor/p5_temporal/control_surface.py` — no-throw sanitized dispatcher.
- `sachima_supervisor/p5_temporal/runtime_client.py` — caller-supplied Temporal client wrapper.
- `sachima_supervisor/p5_temporal/step_executor.py` — WP4 `StepExecutor` seam.
- `sachima_supervisor/activity_controlled_exec.py` — file-backed local controlled-exec claim store proof and P6-B one-shot evidence context.
- `sachima_supervisor/ai_flow_*` — WP4 store/spec/gates/evidence, unmodified unless a later implementation proves a narrow need.

Explicitly forbidden future source surface unless separately approved:

```text
gateway/
plugins/platforms/
Feishu/Lark adapters
production config files
systemd/Docker/service/socket lifecycle files
pyproject.toml / lockfiles for new runtime deps
new real-agent role configs with write permissions
```

## 2. Future data model, design labels only

A later implementation may add sanitized local dataclasses or dict schemas equivalent to:

```text
RuntimeAttachRequest
  enabled: bool
  approval_token: exact future token
  attach_ref: safe caller-owned control-surface ref
  runtime_kind: temporal-like | local-offline-like
  namespace_ref: safe ref, optional
  task_queue_ref: safe ref, optional
  operator_gate: bool
  lease: {lease_id, lease_epoch, holder_ref, state_version}

RuntimeAttachState
  attach_status: unattached | attached | attach_failed | detached
  runtime_health: healthy | degraded | unavailable | unknown
  backend_ref: safe opaque ref only
  error_code: stable code or null
  evidence_ref: safe ref or null
```

No field may contain a backend URL, token, connection string, hostname, raw platform id, raw prompt, raw output, raw exception, or private path.

## 3. Attach algorithm

Future `attach(request)` must:

1. validate `enabled=True` and exact approval token;
2. validate `operator_gate=True`;
3. validate the caller-supplied control surface object/capability shape without importing Gateway or starting anything;
4. record only a sanitized attach projection;
5. run a no-throw health probe if one is supplied as a safe read-only callback;
6. return `attached` or fail closed with stable code.

Stable failure codes:

```text
p6_attach_disabled
p6_attach_approval_mismatch
p6_attach_precondition_unmet
p6_attach_unsafe_material
p6_attach_backend_unavailable
p6_attach_health_degraded
```

## 4. Start/query/update/cancel/recover/close mapping

The future layer should be a lifecycle shell around existing operations:

| Operation | Future mapping | Hard rule |
|---|---|---|
| `start` | P6 `create_run` + `step` or bounded `run_linear` through attached executor | identical idempotency replays; divergent fails closed; **first-slice executor binding is deterministic/injected-fake/local-offline only and must NOT bind the reusable P6-B real-agent runner without a separate real-execution approval** |
| `query` | P6 `query` + P5 control-surface query snapshot | read-only, no execution |
| `update` | future caller-owned update gate only; no broad update surface in first slice unless necessary | stale lease/version fails closed |
| `cancel` | P6 `cancel`; active-run WATCH preserved | no clean active-run claim without proof |
| `recover` | P6 `recover` / P5 recover snapshot | never relaunch uncertain work |
| `close` | P6 `close`; detach marker if requested | no delivery, no client disconnect side effects unless caller-owned and approved |
| `detach` | mark attach state detached | must not stop Worker/service/Gateway |

## 5. Health and rollback design

Required future health gates:

- attach-state projection: attached/unattached/degraded/unavailable;
- backend/control-surface reachability safe code;
- task queue / namespace safe refs if Temporal is used;
- no-leak scan on health snapshot;
- no exception text in degraded health output;
- no automatic retry loop that can start work after operator disable.

Required future rollback controls:

```text
1. Disable P6 attach admission.
2. Detach caller-supplied control surface from the P6 session.
3. Route future starts to local/offline deterministic/fake adapter or reject with p6_attach_disabled.
4. Query existing durable runs without relaunching them.
5. Preserve ambiguous in-flight state as WATCH until operator resolution.
```

Rollback must not restart Gateway, mutate production config, stop a Worker, or terminate a workflow unless a separate ops approval names that operation.

## 6. No-duplicate-relaunch invariant

Future tests must prove:

- repeated identical `start` does not create a second run/step;
- repeated divergent `start` fails closed before executor/backend call;
- `recover` on existing state reattaches/query-only;
- `recover` on ambiguous/missing state returns `recover_ambiguous` or `not_found`, never starts work;
- `query` is read-only and never calls `execute`;
- process restart simulation does not lose the attach projection or claim state in ways that cause duplicate execution.

## 7. No-leak strategy

Use four surfaces:

1. attach-state JSON;
2. P6 control snapshots;
3. P5/WP4 runtime/evidence projections;
4. docs/dev-log/user-review packet.

Add a future canary test that injects forbidden markers at input/exception/health edges and asserts they do not appear anywhere:

```text
raw_prompt
Traceback
bearer token shape
/home/private/path
platform message id
card JSON
signed URL
```

Any hit is a critical blocker.

## 8. Boundary scans for future implementation

Expected future changed-file allowlist:

```bash
git diff --name-only sachima/release/sachima...HEAD   | rg -v '^(sachima_supervisor/p6_runtime_attach\.py$|tests/sachima_supervisor/p6_runtime_attach/|docs/)'
```

Expected forbidden-surface scan:

```bash
git diff --name-only sachima/release/sachima...HEAD   | rg '^(gateway/|plugins/platforms/|.*feishu.*|.*lark.*|pyproject\.toml$|uv\.lock$|.*systemd.*|.*docker.*)'
```

Expected added-line lifecycle scan:

```bash
git diff sachima/release/sachima...HEAD -- sachima_supervisor tests   | rg '^\+'   | rg -i '(systemctl|service restart|docker run|subprocess|Popen|socket\.listen|temporal server start|Worker\(|gateway|feishu|lark|send_message|delivery)'
```

These are future implementation gates; this docs-only PR runs docs-only equivalents.

## 9. Later TDD task plan

A later implementation PR should be small and TDD-first:

1. RED: disabled/mismatched attach makes zero control-surface/backend calls and cannot bind the P6-B real-agent runner.
2. GREEN: `RuntimeAttachRequest` + `attach()` fail-closed gate.
3. RED: unsafe attach material is rejected and not leaked.
4. GREEN: sanitized attach projection and health snapshot.
5. RED: start/query/recover cannot call executor when attach is missing/degraded.
6. GREEN: operation wrappers delegate only after attach and operator gate.
7. RED: duplicate/divergent start behavior around existing P6/P5 seams.
8. GREEN: idempotency/fingerprint replay checks.
9. RED: recover ambiguity never relaunches.
10. GREEN: query/recover read-only attach path.
11. RED/GREEN: active-run cancellation WATCH propagation.
12. RED/GREEN: no-leak canary and forbidden-surface scans.
13. Full focused suite + Codex exact-head blocker review.

## 10. Review handoff

This docs-only gate should be considered successful only if:

- Claude teach-back confirms the architecture and non-approvals;
- Codex blocker review finds no stale status, overclaim, or boundary hole;
- the user review packet asks for implementation approval separately;
- PR body and roadmap surfaces do not imply live/default-on behavior.
