# FlowWeaver Phase 5B Temporal POC

Local-only prototype for proving FlowWeaver durable orchestration boundaries with the Temporal Python SDK.

This prototype is deliberately isolated under `prototypes/`:

- no Gateway wiring
- no platform adapter imports
- no production service auto-start
- no Docker requirement
- no payload-carrying Signals
- validated Updates only for payload-carrying external events

Use only for explicit local experiments and Phase 5B tests.
