# FlowWeaver PE-1D / PE-2 Readiness Decision Runbook

## Purpose

Use this runbook to interpret the PE-1D / PE-2 readiness decision packet after PE-1A, PE-1B, and PE-1C.

Decision packet only. The packet is a decision gate. It is not an activation guide and does **not** enable PE-2 or authorize production config writes, Gateway restart/reload, platform adapter mutation, live delivery control, real external ingress, or production agent/tool execution.

## Verdict Semantics

| Verdict | Meaning |
|---|---|
| `pe1d_readiness_conditional_go_for_longer_controlled_local_observation` | PE-1 evidence supports requesting a longer loopback-only observation window. |
| `pe2_design_conditional_go_for_design_packet_only` | PE-2 may be designed as a separate docs/design phase, but implementation is not approved. |
| `pe2_implementation_no_go` | Do not build PE-2 behavior yet. |
| `pe2_live_default_on_no_go` | Do not enable live/default-on behavior. |

Forbidden verdicts in this packet:

```text
production_enabled
production_ready
pe2_enabled
pe2_live_default_on
real_external_ingress_enabled
production_delivery_control_enabled
```

## How to Use the Packet

1. Confirm the packet is docs plus exact changed-file guard maintenance only.
2. Confirm it cites PE-1A, PE-1B, and PE-1C evidence without raw payloads or secrets.
3. Confirm it separates PE-1D longer observation from PE-2 design and from PE-2 implementation.
4. Confirm PE-2 implementation/live/default-on remains NO-GO.
5. Confirm operational approvals remain separately named.
6. Confirm rollback and no-leak requirements remain explicit.
7. Ask 狗哥 for one exact next-step approval before doing behavior-bearing work.

## Recommended Next Approval

For the next behavior-bearing phase:

```text
approve_pe1d_longer_controlled_sachima_local_observation_window
```

Scope of that approval should remain:

- loopback-only Sachima ingress;
- HMAC required;
- narrow local allowed user;
- no real external ingress;
- no `SACHIMA_SEND_URL` unless a fake local simulator target is separately approved;
- observation-only `start_transaction` / `query_transaction`;
- no Temporal service/Worker startup;
- no delivery control or agent/tool execution expansion.

## PE-2 Design Approval

If 狗哥 wants design before more PE-1 observation, use:

```text
approve_pe2_design_packet_only_no_implementation
```

That approval permits docs/design only. It does not permit config writes, Gateway restart/reload, external ingress exposure, adapter mutation, delivery control, or Temporal Worker/runtime lifecycle changes.

## PE-2 Implementation Blockers

PE-2 implementation stays blocked until these are available:

- longer controlled PE-1D observation evidence;
- fake-send or simulator UI loop evidence;
- no-leak scans over all produced observation/runtime/fake-send artifacts;
- duplicate/replay evidence across same-session turns;
- operator rollback/restore runbook;
- separate approvals for external ingress, config write, restart/reload, runtime ownership, and fake/real delivery target;
- blocker-only fresh-context review with zero blockers.

## Rollback Requirements for Next Phases

Every later phase must preserve these PE-1 rollback levers:

1. Set `flowweaver.production_shadow_observation.enabled=false`.
2. Remove `sachima` from the allowlist.
3. Remove the injected runtime control surface.
4. Stop any separately approved fake/local simulator or external runtime surface.
5. Revert the relevant phase PR.

Rollback must not require raw payload inspection, delete production data, mutate platform adapters, invent ACKs, or alter final delivery behavior.

## Safe Evidence Rules

Evidence may include only:

- safe labels and phase names;
- counts and deltas;
- HTTP statuses for controlled probes;
- sanitized runtime operation names;
- boolean boundary flags;
- local evidence file paths;
- stable error codes.

Evidence must not include:

- HMAC secrets;
- raw webhook bodies;
- raw user text;
- platform/chat/user/message IDs from real platforms;
- card JSON;
- media paths or bytes;
- gateway log excerpts;
- raw exception text;
- credentials, tokens, passwords, API keys, or connection strings.
