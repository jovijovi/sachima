# FlowWeaver PE-1D Tail Register

> This Tail Register is part of the `phase-gate-drift-control` skill validation for Sachima PE-1D. It prevents deferred work from becoming invisible. It does not approve PE-1D execution.

| ID | Class | Description | Risk | Owner / DRI | Blocks current validation? | Blocks PE-1D execution? | Required before | Acceptance method | Status |
|---|---|---|---|---|---:|---:|---|---|---|
| P1D-TAIL-001 | NEXT_PHASE | Run the actual PE-1D longer controlled local observation window after exact approval text is given. | Without the run, PE-1D remains unproven and P2 should not rely on longer-window evidence. | Hermes operator with Dog Brother approval | no | yes | P2 fake-send/simulator request | PE-1D evidence packet with positive/negative/duplicate/rollback/no-leak proof | carried |
| P1D-TAIL-002 | NEXT_PHASE | Produce PE-1D evidence packet and closure score after the real observation run. | Without closure score, phase completion can be confused with planning readiness. | Hermes operator | no | yes | PE-1D closure / next-phase request | Score >= 90, no critical boundary violation, fresh review blockers = 0 | carried |
| P1D-TAIL-003 | WATCH | Validate whether the local `validate_phase_gate.py` validator is too strict or too weak when real PE-1D evidence paths are added. | Validator false positives/false negatives could create either governance theater or unsafe pass. | Hermes operator | no | no | PE-1D closure | Record validator findings in PE-1D dev log; patch skill if needed | open |
| P1D-TAIL-004 | PARKED | PE-2 implementation, live/default-on, real external ingress, production delivery, and production agent/tool execution remain parked. | Accidentally treating PE-1D readiness as PE-2/live approval would violate GOAL.md boundaries. | Dog Brother approval required to reopen | no | no | Not applicable until separately approved | New explicit approval text plus separate phase gate | open |

## No Hidden Tail Statement

For this docs-only skill validation:

```text
Known tail items are listed above.
No BLOCKER tail remains open for validating the skill on PE-1D planning artifacts.
All PE-1D execution work is explicitly carried as NEXT_PHASE and still requires exact approval.
All PE-2/live/real delivery/external ingress work is PARKED.
```
