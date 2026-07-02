# Sachima Architecture

Authoritative architecture references for the Sachima integration of **agent-run-supervisor**
and **Temporal**. These docs name and place components; they do not grant approvals or change
runtime behavior.

## Contents

- [`sachima-global-architecture-agent-run-supervisor-temporal.md`](sachima-global-architecture-agent-run-supervisor-temporal.md)
  — the first/authoritative architecture source. Contains: the component glossary (names
  first), the milestone-label (S0–S5 / P7) → actual-component/contract map, the context /
  container / component / sequence diagrams, the ownership matrix, the trust / no-leak
  boundary matrix, the current-state vs target-state gap list, and the configuration
  boundary model.

## How this fits with the other docs

```text
GOAL.md                         = final goal + north-star principles
docs/architecture/              = component names, boundaries, diagrams — the "what is it / where does it sit" map
docs/roadmap/current-status.md  = current phase/task dashboard + approvals (task truth)
docs/plans/ (S1–S5, P7)         = per-stage design contracts and approval gates
docs/runbooks/                  = operator workflows (e.g. P7 delivery/ACK, canary request)
GitHub                          = PR/commit/CI/merge authority
```

When an architecture doc and a named plan/runbook seem to disagree about a *contract detail*,
the named packet wins; when they disagree about *what a component is called or where it sits*,
the architecture doc is the intended source. Approvals and runtime behavior stay governed by
`current-status.md` and the named gates.
