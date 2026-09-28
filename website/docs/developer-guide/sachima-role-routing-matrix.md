# Sachima shared role-routing matrix

One structured YAML file is the single authority for which **model and effort**
an external AGENT runs under for a given **role**. The Sachima delegation
coordinator reads it to build each Run's ARS request, and the memory side reads
the same file, through the same parser, to render and validate it. There is no
second model table to keep in sync.

The module is `gateway/sachima_agent_role_routing_matrix.py`. It is pure and
offline: it opens no socket, starts nothing, and writes nothing.

## Configuration

| Key | Meaning |
|---|---|
| `SACHIMA_ROLE_ROUTING_MATRIX_FILE` | Absolute path of `routing-matrix.yaml`. Read by both composition roots (`compose_delegate_coordinator` and the live-progress `arsd` binding). Optional. |

The path is explicit host configuration, never a hardcoded operator location,
and profiles do not share one implicitly. When the key is **absent**, nothing
routes by role: a role-bearing delegation is refused with
`sachima_role_routing_matrix_unconfigured`, and every non-role delegation
behaves exactly as before. When the key is **present**, the file is validated
once at composition (a file that does not validate fails the composition
closed, like the presets and role-policy documents) and then **re-read on every
role-bearing admission**, so an edit applies to the next new Run without a
Gateway restart. Changing the key itself is a restart.

## Accepted shape (`schema_version: 1`)

```yaml
schema_version: 1
default_agents:              # role_id -> canonical agent_id; policy metadata
  architect: claude
  lead_developer: claude
routes:
  - agent_id: claude         # canonical ARS roster id (claude, codex, cursor, ...)
    role_id: lead_developer  # exact role token (architect, lead_developer, ...)
    availability: Available  # Available | Paused
    model: "claude-fable-5-1[1m]"
    effort: xhigh
    fallback:                # null, or exactly {model, effort}
      model: "opus[1m]"
      effort: max
```

Rules, all fail-closed with the stable code `sachima_role_routing_matrix_invalid`:
keys are closed (unknown keys are refused, not ignored); ids and role tokens are
exact (no case folding, no aliases); `model` is bounded printable text and
`effort` is a wire token or exactly `N/A`, both preserved byte-for-byte
(context suffixes and Cursor's embedded selector included); a duplicate
`(agent_id, role_id)` pair fails the whole document; every `default_agents`
entry must name a pair that has a route.

Semantics: `Available` is policy eligibility, not proof of live authentication,
model access, or execution authorization. `Paused` refuses admission
(`sachima_role_route_paused`). `fallback` is rendered and reported; it grants no
automatic retry. `default_agents` is validated and rendered; it does not add a
tie-break to role selection, which stays a question for the user.

## What Sachima does with it

- **A supplied `role` on `create` or `continue`** selects the
  `(agent_id, role_id)` route for the AGENT being admitted and seals that
  route's exact `model`/`effort` into the Turn together with the matrix file's
  digest. The ARS `submit` carries those literals. An explicit `agent_id` plus a
  `role` runs the role's route, never the AGENT-wide preset.
- **A role with no Available route** is refused before anything durable exists
  (no payload, task, turn, card, or submit) with one of
  `sachima_role_routing_matrix_unconfigured`,
  `sachima_role_routing_matrix_invalid`, `sachima_role_route_missing`,
  `sachima_role_route_paused`. It is never quietly run under the AGENT-wide
  preset.
- **No `role`** is the AGENT-wide path, unchanged: the preset's policy refs
  resolve in the ARS config as before, and the matrix is not read.
- **Workspace, agent policy, run limits, grants, and launch refs** are the
  execution preset's; a route changes exactly two request fields.
- **An admitted Run stays pinned.** The literals live on the durable Turn
  record; the binding ledger records only their digests. A lost ack is recovered
  byte-identically under the original literals whatever the matrix says now,
  in-process or after a restart; a recovery handed different literals, or none
  where the Run sealed some, is refused with `runtime_arsd_binding_conflict`
  before any socket call. A restart restores an accepted Run without
  resubmitting.
- **A genuinely new Run** (a manual `continue`, or the one host-recorded
  authorized follow-up) resolves its route from the matrix as it is at that
  moment. The authorized follow-up pins its `(AGENT, role)` combination: the
  `continuation_role` the authorization named, or else the role the source
  round was sealed under; the model for that combination is the matrix's
  current value, not a literal frozen into the authorization.

The role policy document (`agent_id` → division and roles) is unchanged and
still drives the read-only `agents` discovery and role selection. The matrix is
the sole authority for role-bearing **admission**; keep the two consistent.

## Memory side: read, render, validate

```bash
python -m gateway.sachima_agent_role_routing_matrix --file routing-matrix.yaml            # Markdown table
python -m gateway.sachima_agent_role_routing_matrix --file routing-matrix.yaml --agent claude --role lead_developer
python -m gateway.sachima_agent_role_routing_matrix --file routing-matrix.yaml --availability Paused --format json
python -m gateway.sachima_agent_role_routing_matrix --file routing-matrix.yaml --validate # digest + counts, exit 1 on invalid
```

`--file` defaults to `SACHIMA_ROLE_ROUTING_MATRIX_FILE`. The table keeps the
original column order (`AGENT | Role | Model | Effort | Availability | Fallback Model / Effort`).
Invalid material is reported as the stable code only; file content is never
echoed. The Palace Markdown validator is unchanged; `--validate` is the narrow
check for this one YAML authority.
