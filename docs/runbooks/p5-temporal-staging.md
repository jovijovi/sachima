# P5 Temporal staging runbook (`sachima-p5-staging`)

Status: **Parallel ops / canary track — NOT a PR B merge blocker (FR9).**
Scope: ops-owned Worker + `sachima-p5-staging` namespace only, under the PR A
lifecycle grant (`approve_external_temporal_service_or_worker_lifecycle_for_sachima_p5_runtime`,
hermetic-local + staging only). This runbook does **not** authorize production
cluster, production traffic, P6 real `acpx`/agent execution, Gateway-owned
lifecycle, Feishu/live behavior, production config writes, or real delivery.

The hermetic-local gate (`tests/sachima_supervisor/p5_temporal/hermetic/`) is the
merge blocker. Staging is run **after** merge and produces canary evidence only;
no staging evidence is required to merge PR B.

## What runs in staging

The same governed PR B package runs in staging as in the hermetic gate:

- `StepWorkflow` — deterministic, replay-safe; controlled-deterministic step body.
- `p5_step_activity` — claim-check artifact ref only; **no** real `acpx`/agent,
  no subprocess, no network, no raw stdout.
- `P5TemporalRuntimeClient` / `P5TemporalControlSurface` — over a caller-supplied
  connected client; sanitized no-throw results only.
- `build_p5_temporal_worker(...)` / `run_p5_temporal_worker(...)` — **ops-owned**
  Worker launcher. Never imported or started by Gateway / inbound / platform /
  Feishu code paths (enforced by `test_gateway_boundary.py`).

## Preconditions

1. Default-off by construction. The `P5TemporalStepExecutor` is enabled only with
   `enabled=True` **and** the exact approval token
   `P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN`. Absent either, zero
   Temporal calls are made and callers stay on the local/offline baseline.
2. Ops owns the connection. Ops connects a `temporalio.client.Client` to the
   staging endpoint (`<staging-temporal-host>:7233`, namespace
   `sachima-p5-staging`) and passes it in. The package never calls
   `Client.connect(...)`, never starts a server / subprocess / socket / Docker /
   systemd unit, and never closes the caller-supplied client.
3. Namespace isolation. Use the dedicated `sachima-p5-staging` namespace with a
   **30-day retention default**. Never the production namespace.
4. Bounded, controlled-deterministic runs only. No real agent execution.
5. Sanitized identities (FR2: no host/pid in history). The ops Worker already
   uses a sanitized constant identity (`P5_TEMPORAL_WORKER_IDENTITY`). Ops should
   also connect the caller-supplied client with a sanitized `identity=` (e.g.
   `"sachima-p5-temporal-client"`) so starter-side events carry no host/pid.

## Start the ops-owned Worker (ops host only)

```text
# Ops process — NOT a Gateway / inbound / platform / Feishu path.
# 1. Ops connects the client (ops-owned lifecycle).
client = await temporalio.client.Client.connect(
    "<staging-temporal-host>:7233", namespace="sachima-p5-staging"
)
# 2. Run the ops-owned Worker on the pinned task queue.
await sachima_supervisor.p5_temporal.run_p5_temporal_worker(client)
# task_queue defaults to contracts.P5_TEMPORAL_TASK_QUEUE ("sachima-p5-temporal-slice-1").
```

## Health checks (staging-scoped)

- Worker poller is reachable on `sachima-p5-staging` / the pinned task queue.
- A canary `StepWorkflow` reaches `state == "completed"` with exactly one
  claim-check artifact ref and a valid `sha256:` content digest.
- No-leak: the query snapshot and the serialized event-history bytes pass SCAN 1
  + SCAN 2 (allowlisted keys only; no forbidden markers; no seeded canary). Any
  hit maps to `runtime_history_leak_detected` and halts the canary.
- Determinism: a recorded staging history replays clean through
  `temporalio.worker.Replayer` (no non-determinism error).

## Kill switch / rollback (staging-scoped)

1. **Kill switch (instant):** flip the executor `enabled=False` (or clear the
   approval token). Callers immediately fall back to the local/offline baseline;
   no code revert is needed (the package is additive and default-off).
2. **Drain the Worker:** stop the ops-owned Worker process. The WP3b active-run
   cancellation WATCH means in-flight cancellation never overclaims a clean
   shutdown during drain.
3. **No production blast radius:** staging uses its own namespace and endpoint;
   rollback never touches production cluster, traffic, or config.

## Explicit non-approvals (carried verbatim)

```text
no production cluster enablement; no production traffic; no production config writes;
P6 real acpx/agent execution remains a separate future gate; no Gateway-owned lifecycle;
no Gateway/inbound/platform/Feishu import of the Worker/service lifecycle; no live;
no real delivery; no write-capable roles.
```
