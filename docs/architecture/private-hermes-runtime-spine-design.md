# Private Hermes Runtime Spine — Final Design

## 1. Context

Each user runs exactly one **Private Hermes Agent** (a personal assistant). Requests
arrive from an IM/chat surface. Some are pure conversation or inline tool calls; some
need a real **external local AGENT** runtime that runs long, streams, and asks for
permission; some need **durable execution** that survives process restart.

Earlier drafts modeled this as four parallel lanes plus an Admission/Delivery/FlowWeaver
control plane. That is over-designed for a single-user personal agent. The final model
collapses everything onto **one `task_id` spine** and expresses the variability as **two
boolean mode flags**.

## 2. Scope / Non-goals

In scope (P0):
- One personal agent per user.
- A single canonical task spine keyed by `task_id`.
- Optional external local agent runs (`needs_agent`).
- Optional Temporal durable orchestration (`needs_durable`).

Non-goals:
- Not a multi-tenant AI control plane.
- No Admission / Delivery / FlowWeaver as first-class components.
- No plugin system; capabilities are a static table.
- No four-lane topology — lanes were a modeling mistake.

## 3. Core model: one spine, two flags

There is exactly one spine per task:

    User/IM -> Private Hermes Agent -> Thin Dispatcher -> Task Registry(task_id)
            -> Execution Port -> producers -> Task Event Log -> Status Projection -> User/IM

The 2×2 is **not** four code paths; it is two orthogonal flags on the *same* task:

| flag           | meaning                                                           |
|----------------|------------------------------------------------------------------|
| `needs_agent`   | task requires an external local AGENT runtime (attach/stream/signal/permission) |
| `needs_durable` | task requires Temporal durable execution (survives restart)      |

- `(false,false)` — inline tools only.
- `(true,false)`  — live agent via supervisor, no durability.
- `(false,true)`  — durable plain activities, no agent.
- `(true,true)`   — durable workflow that *attaches* an existing agent session.

Same registry, same event log, same projection for all four. The flags only change which
producers are wired in.

## 4. Components

- **Private Hermes Agent** — conversation, decision, and the only user-facing exit.
  Relays permission answers. Does **not** manage runtime details (no sessions, no process handles).
- **Thin Dispatcher** — stateless. Turns an intent into an `ExecutionPlan` + typed
  `LaunchSpec`, and sets `needs_agent` / `needs_durable`. No state, no side effects.
- **Tiny Capability Registry** — a static table keyed by `agent_kind`. Fields:
  `attach_resume`, `permission_events`, `workspace_isolation`, `liveness`, `stream_resume`.
  Not a plugin system; used only to validate a LaunchSpec.
- **Task Registry** — metadata, mode flags, current snapshot, refs per `task_id`. The
  snapshot is a derived/cached view for fast reads — **not a second source of truth**.
  Canonical truth is the Event Log.
- **Execution Port** — the single interface into producers:
  `create_or_attach / stream / signal / status / kill / liveness`.
- **Producers** — the only things that append events: inline tools, agent-run-supervisor,
  Temporal activities.
- **Task Event Log** — spine-owned canonical truth. Append-only. **Single monotonic `seq`
  authority per `task_id`.** Events carry refs, never raw output.
- **Evidence / Blob Store** — raw prompts, stdout, tool logs, artifacts, platform IDs.
  Canonical events/history carry only refs.
- **Status Projection** — deterministic consumer that reads the Event Log and drives IM
  edit / milestone / permission / query. Never writes the log; never on the launch path.
- **agent-run-supervisor** — owns the external local AGENT runtime:
  `create_or_attach / stream / signal / kill / liveness`. **At most one live session per
  `task_id`.** Requires an orphan reaper.
- **Temporal** — present only when `needs_durable=true`. The Workflow is an **orchestrator,
  not a producer**; it calls Plain Activities or an AgentRunActivity in parallel.
  Activities append; the workflow orchestrates.
- **AgentRunActivity** — **attach-existing mode only**. If no session exists it
  waits/retries/fails by policy; it never creates or spawns, never owns a process.
  Heartbeats carry `(cursor, phase, refs)` only; it does not re-append the agent's events.
- **Isolated Workspace** — per run, with a **single-writer lease**. A git worktree is just
  one implementation for code tasks.

## 5. Data flow

1. User message enters via IM to the Private Hermes Agent.
2. Hermes decides intent, calls the Thin Dispatcher.
3. Dispatcher emits `ExecutionPlan` + typed `LaunchSpec`, sets flags, validates against the
   Capability Registry.
4. Task Registry creates/updates the `task_id` record (metadata, flags, refs).
5. Execution Port routes to producers by flags: inline tools directly; supervisor
   `create_or_attach` for agent runs; Temporal workflow for durable runs.
6. Producers append events (refs only) to the Event Log under the single seq authority.
7. Status Projection reads the log, refreshes the Registry snapshot, drives IM.
8. Permission requests/answers travel the roundtrip (§8).

## 6. Event / Evidence / Projection model

- The Event Log is append-only and the only source of truth. Each `task_id` has exactly one
  monotonic `seq` authority; no other component may assign seq.
- Events are small and carry **refs** into the Evidence/Blob Store — never raw
  stdout/artifacts. This keeps the log replayable and cheap.
- The Evidence/Blob Store holds the heavy bytes: prompts, stdout, tool logs, artifacts,
  platform IDs.
- Status Projection is a **pure, deterministic function** of the event sequence: same
  events in → same projection out. It updates the snapshot cache and pushes IM. It never
  appends and never launches work.

## 7. AgentRunActivity boundary

The sharpest edge in the design — and the easiest to get wrong.

- **Attach-only.** AgentRunActivity attaches to an *existing* supervisor session for the
  `task_id`. It has **no create branch**.
- **No spawn.** It never launches an OS process and never owns the runtime; session
  lifecycle belongs to the supervisor.
- **No session → policy.** If no live session exists it waits/retries/fails per policy; it
  does not create one.
- **Heartbeat is refs-only.** Heartbeats carry `(cursor, phase, refs)`; it does not
  re-append the agent's own event stream — the supervisor is the producer for those.

Reason: the durable workflow must be a thin orchestrator over a runtime it does not own, so
a workflow replay or activity retry can never fork or duplicate a live agent process.

## 8. Liveness / permission / workspace

**Liveness.** The supervisor exposes `liveness`. A task blocked on a permission answer is
**alive, not stalled** — `permission-wait` is an expected live state. The orphan reaper
distinguishes a dead/orphaned session from one legitimately waiting.

**Permission roundtrip.**

    supervisor -> Task Event Log (permission_requested, refs)
               -> Status Projection -> User/IM (prompt)
    user answer -> Private Hermes Agent -> supervisor.signal(task_id, decision/ref)

The user never talks to the supervisor directly; Hermes is the only entry/exit. The answer
returns as `signal(task_id, decision/ref)`.

**Workspace.** Each run gets an Isolated Workspace with a **single-writer lease** — only one
writer may mutate it at a time. A git worktree is one implementation for code tasks; the
lease is the invariant, not git.

## 9. P0 implementation contract

Ship these, and only these, for P0:

1. **Spine** — one `task_id` spine end to end.
2. **Task Registry** — metadata, mode flags, snapshot (cache), refs.
3. **Task Event Log** — append-only, single monotonic seq authority per `task_id`, refs-only events.
4. **Status Projection** — deterministic, read-only consumer driving IM.
5. **Static Capability Registry** — table keyed by `agent_kind` (attach_resume, permission_events, workspace_isolation, liveness, stream_resume).
6. **Typed LaunchSpec** — produced by the Thin Dispatcher, validated against the registry.
7. **Supervisor Execution Port** — `create_or_attach / stream / signal / kill / liveness`, ≤1 live session per `task_id`.
8. **Orphan reaper** — reclaims dead sessions; treats permission-wait as alive.
9. **permission-wait = alive** — a modeled live state, never reaped as stalled.
10. **Workspace single-writer lease** — enforced per run.
11. **AgentRunActivity attach-not-spawn** — attach-existing only, no create branch, no OS process launch.
12. **Permission roundtrip** — supervisor → log → projection → user; answer via Hermes → supervisor signal.

## 10. Deferred capabilities (not P0)

- **B→D live promotion** — promoting a live (non-durable) agent run into a durable workflow mid-flight.
- **Agent-death respawn resume** — respawning a dead agent and resuming from cursor.
- **Heavy Admission / Delivery / FlowWeaver layers** — add only when actually needed:
  shared/team workspaces, real ACK/send delivery guarantees, quota/scheduler, compliance,
  plugin-risk isolation, complex multi-step DAG orchestration.

Until one of those is real, the single spine plus two flags is sufficient.

## 11. First tests

1. **Single seq authority** — concurrent appends to one `task_id` yield a strictly
   monotonic, gap-free seq; no second component can assign seq.
2. **Refs-only invariant** — no event body contains raw stdout/artifacts; every heavy
   payload is a ref into the Evidence store.
3. **Deterministic projection** — replaying the same event sequence yields identical
   projection/snapshot output.
4. **create_or_attach single session** — two `create_or_attach` calls for one `task_id`
   yield exactly one live session (second attaches, does not spawn).
5. **permission-wait not stalled** — a task waiting on permission reports alive; the orphan
   reaper does not reap it.
6. **Permission roundtrip** — a `permission_requested` event reaches IM, and a user answer
   arrives as `signal(task_id, decision/ref)` at the supervisor.
7. **AgentRunActivity attach-not-spawn** — with no existing session, the activity takes the
   wait/retry/fail branch and launches **no** OS process; assert no create branch is reachable.
8. **Workspace single-writer lease** — a second writer to a leased workspace is
   refused/blocked until the lease releases.
9. **Orphan reaper** — a genuinely dead session (no liveness, not permission-wait) is
   reclaimed and emits a terminal event.
