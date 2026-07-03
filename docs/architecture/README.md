# Sachima Architecture

This directory holds durable architecture guidance for Sachima.

## Highest guiding principle

- `private-hermes-runtime-spine-design.md` — final Private Hermes runtime-spine design. This is the highest architecture guidance for Hermes, Claude Code, Codex CLI, and engineers when working on the current Sachima × agent-run-supervisor × Temporal mainline.
- `private-hermes-runtime-spine-architecture.svg` — visual architecture diagram for the same design.

Read these before proposing, implementing, or reviewing runtime-spine work. The design intentionally keeps the system minimal: one private Hermes Agent per user, one `task_id` spine, mode flags instead of four lanes, `agent-run-supervisor` for external local AGENT event streams, Temporal for durable runtime only when needed, and a spine-owned Task Event Log as canonical truth.

Deferred/heavy layers such as Admission, Delivery/ACK, and FlowWeaver orchestration return only when a concrete driver requires them.
