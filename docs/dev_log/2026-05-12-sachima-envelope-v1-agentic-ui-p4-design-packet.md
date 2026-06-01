# Dev Log — Sachima Envelope v1 / agentic-ui P4 Design Packet

Date: 2026-05-12
Branch: `docs/sachima-envelope-v1-design-packet`
Base: `feature/sachima-channel @ 5387aead7e9935a031c3478e79df80debb89fdd5`
Scope: docs-only P4 protocol/design packet

## 1. Request

Dog Brother approved starting the canonical protocol/design packet after agreeing that the formal protocol should live in Sachima, not agentic-ui.

Working interpretation:

```text
Create canonical Sachima Envelope v1 docs and P4 agentic-ui controlled external ingress design packet.
Do not implement code.
Do not restart/reload Gateway.
Do not write production config.
Do not enable live/default-on behavior.
Do not perform real external ingress or real delivery.
```

## 2. Preflight

Read before changes:

- `AGENTS.md`
- `docs/roadmap/current-status.md`
- `GOAL.md`
- `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md` P4 section

Current status at start:

```text
current_position: P4 next — Controlled external ingress design packet
next_allowed_request: P4 controlled external ingress design packet only
```

Explicit non-approvals preserved:

```text
real_external_sachima_ingress
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
reverse_proxy_or_tls_config_write
```

Canonical checkout had local untracked workspace files, so changes were made in a clean worktree:

```text
/home/ubuntu/workspace/hermes/worktrees/sachima/docs-sachima-envelope-v1-design-packet
```

## 3. Prior reviewer meeting incorporated

Before this PR, Codex and Claude Code independently reviewed the protocol ownership proposal.

Accepted decision:

```text
Sachima owns the external wire protocol.
agentic-ui is the first conformance target.
Sachima Envelope v1 is the canonical protocol basis for P4 controlled external ingress design.
```

Accepted findings:

- agentic-ui currently uses Unix-millisecond HMAC timestamps; Sachima validates Unix seconds.
- Sachima delivery callback currently lacks v1 HMAC headers.
- agentic-ui outbound uses `content`; v1 canonical field must be `text`.
- HTTP 2xx from a delivery callback means receiver acceptance only, not user-visible/browser-visible delivery.
- `SACHIMA_SEND_URL` is directionally ambiguous and should be deprecated behind direction-specific names.

## 4. Files changed

Planned docs-only changes:

- Create `docs/protocols/README.md`
- Create `docs/protocols/sachima-envelope-v1.md`
- Create `docs/plans/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md`
- Create `docs/dev_log/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md`
- Update `docs/roadmap/current-status.md`
- Update `AGENTS.md`
- Update `docs/sachima-channel.md`
- Update `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md`

No source code, tests, gateway config, runtime evidence, or generated outputs are intended for commit.

## 5. Design content summary

The new protocol doc defines:

- protocol ownership and scope;
- two surfaces: external client ingress and Sachima delivery callback;
- HMAC signing with Unix seconds and raw-body signing;
- required `schema_version`, `message_id`, `chat_id`, `user_id`, `role`, and `text` semantics;
- `content` as a deprecated migration alias only;
- v1 image-only attachment stance and SSRF/size/no-leak requirements;
- direction-specific environment naming;
- migration order;
- required future conformance probes;
- agentic-ui as first conformance target but not protocol owner;
- explicit tails for implementation, real ACK closure, and richer media.

The design packet defines:

- why this is allowed under P4 design-only scope;
- what remains unapproved;
- accepted Codex/Claude findings;
- compatibility gaps;
- future implementation requirements for Sachima and agentic-ui;
- local-only first execution model;
- acceptance checklist and design score.

## 6. Verification plan

Before commit/PR:

- `git diff --check`
- changed-file allowlist gate
- docs marker gate
- non-approval preservation gate
- no secret-shaped literal scan over added lines / new docs
- no source/config/runtime/generated output changes
- independent Codex review
- independent Claude Code review
- patch any blocker and rerun final doc gate after evidence append

## 7. Review status

Initial protocol meeting before docs:

- Codex: PASS
- Claude Code: PASS with required fixes

Post-doc review:

- Codex: PASS, blockers none. Required future work: local conformance probes before implementation; no implementation tests required for docs-only merge.
- Claude Code: PASS, blockers none. Required future work: v1 conformance probes, `SACHIMA_DELIVERY_URL` precedence/warning tests during implementation, and legacy `sachima-channel.md` examples clearly documented as legacy.

Accepted post-doc note:

- `docs/sachima-channel.md` legacy outbound `content` / deprecated `SACHIMA_SEND_URL` behavior is now explicitly marked as legacy implementation documentation, not the canonical external protocol.

## 8. Final verification

Local docs gate status after review patch:

```text
SACHIMA_ENV_V1_DOC_MARKERS_PASS
SACHIMA_ENV_V1_CHANGED_FILE_GATE_PASS
SACHIMA_ENV_V1_ADDED_LINES_NO_LEAK_GATE_PASS
SACHIMA_ENV_V1_NON_APPROVAL_GATE_PASS
```

`git diff --check` passed.

Changed-file scope remained docs-only and limited to:

```text
AGENTS.md
docs/dev_log/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md
docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md
docs/plans/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md
docs/protocols/README.md
docs/protocols/sachima-envelope-v1.md
docs/roadmap/current-status.md
docs/sachima-channel.md
```

No source code, runtime config, generated evidence, or service lifecycle files were changed.
