# Dev Log — Sachima Protocols Canonical Pointer

Date: 2026-05-13
Branch: `docs/sachima-protocols-canonical-pointer`
Base: `feature/sachima-channel @ ef790195e12856145011423a0c099b3940ab75ba`
Scope: docs-only canonical protocol repository pointer update

## 1. Request

Dog Brother approved creating `jovijovi/sachima-protocols` as the canonical protocol stack repository for Sachima protocol text, schemas, examples, fixtures, and lightweight SEP governance.

Working interpretation:

```text
Create/use the new protocol repository as the canonical protocol text home.
Update Sachima product repo docs to point to that canonical location.
Do not implement protocol behavior.
Do not restart/reload Gateway.
Do not write production config.
Do not enable live/default-on behavior.
Do not perform public ingress or real delivery.
```

## 2. Preflight

Read before changes:

- `AGENTS.md`
- `GOAL.md`
- `docs/roadmap/current-status.md`
- `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md`
- `docs/dev_log/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md`
- `docs/protocols/sachima-envelope-v1.md`

Current status at start:

```text
current_position: P4 design packet delivered — implementation not approved
next_allowed_request: Sachima Envelope v1 local conformance implementation only
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

## 3. Protocol repository result

Created and seeded:

```text
repo: jovijovi/sachima-protocols
url: https://github.com/jovijovi/sachima-protocols
initial_commit: 967dc3c4c6d1825870d1034a7651dd5fefb4d7e4
canonical_spec: protocols/envelope/v1.md
workflow: Validate
workflow_result: success
```

The protocol repository contains:

- `protocols/envelope/v1.md`
- `schemas/envelope-v1/*.schema.json`
- `examples/envelope-v1/*.json`
- `fixtures/envelope-v1/*.json`
- `seps/sep-0001-sachima-envelope-v1.md`
- `governance/*.md`
- `scripts/validate.py`
- `.github/workflows/validate.yml`

## 4. Files changed in Sachima

Planned docs-only changes:

- `AGENTS.md`
- `docs/protocols/README.md`
- `docs/protocols/sachima-envelope-v1.md`
- `docs/roadmap/current-status.md`
- `docs/dev_log/2026-05-13-sachima-protocols-canonical-pointer.md`

No source code, tests, workflow files, runtime config, Gateway lifecycle files, generated evidence, or outputs are intended for commit.

## 5. Design decision

The Sachima product repo no longer keeps a duplicate full copy of the canonical protocol text. It keeps a local pointer stub with stable reminders and non-approval boundaries.

Reason:

```text
Avoid split-brain protocol authority.
Keep current implementation roadmap in Sachima.
Keep current protocol text in sachima-protocols.
```

## 6. Verification plan

Before PR:

- `git diff --check`
- docs-only changed-file gate
- docs marker gate matching `.github/workflows/nix.yml`
- no secret-shaped literal scan over added lines
- source/config/runtime boundary gate
- independent Codex review
- independent Claude Code review

Final verification results will be appended before commit if review requires changes.

## 7. Review status

Independent read-only review results:

```text
Codex: PASS, blockers none.
Claude Code: PASS, blockers none.
```

Accepted notes:

- The local protocol document is now a pointer stub while preserving critical markers: Unix seconds, raw-body HMAC, `content` as deprecated migration alias, `SACHIMA_DELIVERY_URL`, callback `2xx`, conformance target, and the non-approval boundary.
- `docs/roadmap/current-status.md` preserves the P4 design-packet-delivered state and does not approve implementation/live/public ingress/real delivery.
- Scope remains docs-only: `AGENTS.md` and Markdown files under `docs/` only.

## 8. Final verification

Local gate status after review:

```text
SACHIMA_PROTOCOL_POINTER_CHANGED_FILE_GATE_PASS
SACHIMA_PROTOCOL_POINTER_MARKER_GATE_PASS
SACHIMA_PROTOCOL_POINTER_ADDED_LINES_NO_LEAK_GATE_PASS
```

`git diff --check` passed.

Changed-file scope remains docs-only and limited to:

```text
AGENTS.md
docs/dev_log/2026-05-13-sachima-protocols-canonical-pointer.md
docs/protocols/README.md
docs/protocols/sachima-envelope-v1.md
docs/roadmap/current-status.md
```

No source code, workflow files, runtime config, generated evidence, or service lifecycle files were changed.
