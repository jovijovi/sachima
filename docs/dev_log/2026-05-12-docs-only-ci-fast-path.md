# Dev Log — Docs-only CI Fast Path

Date: 2026-05-12
Branch: `ci/docs-only-nix-fast-path`
Base: `feature/sachima-channel @ 466f2a62b6dc5abb9f81fd98a1ef24cf0bcb08c4`
Scope: GitHub Actions CI maintenance plus agent guidance

## 1. Request

Dog Brother approved implementing the CI split discussed in chat:

```text
docs-only: lightweight docs/no-leak/marker gates + heavy CI early exit
code/config/workflow: full CI
```

This changes repo CI configuration only. It does not approve Sachima Envelope v1 implementation, live/public ingress, real delivery, Gateway restart/reload, production config writes, platform adapter mutation, Temporal lifecycle, or runtime behavior changes.

## 2. Preflight

Read before changes:

- `AGENTS.md`
- `docs/roadmap/current-status.md`
- `GOAL.md`
- `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md`
- `docs/dev_log/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md`
- existing GitHub workflow files, especially `.github/workflows/nix.yml`

Current roadmap state remains:

```text
current_position: P4 design packet delivered — implementation not approved
next_allowed_request: Sachima Envelope v1 local conformance implementation only
```

This PR is workflow maintenance, not a phase implementation. `docs/roadmap/current-status.md` does not need a phase-state update; the PR body should state that explicitly.

## 3. Implementation summary

Planned changes:

- Add PR changed-file classification to `.github/workflows/nix.yml` using the existing pinned `actions/github-script` action.
- Treat Markdown/MDX docs under `docs/`, `website/`, `skills/`, `optional-skills/`, plus root project docs such as `AGENTS.md`, `GOAL.md`, and `README.md`, as docs-only.
- For docs-only PRs, keep the existing Nix matrix job names but skip the heavy Nix setup/flake/build steps.
- On Linux docs-only matrix runs, execute lightweight changed-file, secret-shaped literal, and critical-marker checks.
- Leave workflow, source, test, lockfile, generated output, runtime config, and non-Markdown docs-asset changes on the full CI path.
- Document the rule in `AGENTS.md` so future agents do not reintroduce workflow-level `paths-ignore` for required checks.

## 4. Verification plan

Before commit/PR:

- YAML parses.
- Embedded JavaScript parses.
- Embedded Python docs gate parses and passes sample positive/negative fixtures.
- Local diff changed-file gate allows only CI workflow/docs/dev-log guidance files.
- Secret-shaped literal scan over added lines reports no unsafe literal.
- `git diff --check` passes.
- Fresh read-only review checks branch-protection semantics, docs-only classification, and failure behavior.

## 5. Review notes

Claude Code initial review:

```text
VERDICT: PASS
BLOCKERS: NONE
```

Codex initial narrow review found one blocker:

```text
Docs-only classification ignored renamed files' previous_filename, allowing source/config/workflow content renamed into docs to be treated as docs-only.
```

Accepted fix:

- The GitHub Script classifier now requires both `filename` and `previous_filename` to be docs-only when `previous_filename` exists.
- The Python docs gate applies the same rule.
- Critical-marker checks consider both current and previous filenames, so protected docs such as `AGENTS.md`, `GOAL.md`, `docs/roadmap/current-status.md`, and `docs/protocols/sachima-envelope-v1.md` cannot be silently removed or renamed away under the docs-only fast path.

Final re-review:

```text
Codex: PASS, blockers none
Claude Code: PASS, blockers none
```

## 6. Final verification

Local verification markers before commit:

```text
DOCS_ONLY_GATE_RENAME_FIXTURES_PASS
CI_DOCS_FAST_PATH_CHANGED_FILE_GATE_PASS
CI_DOCS_FAST_PATH_ADDED_LINES_NO_LEAK_GATE_PASS
CI_DOCS_FAST_PATH_MARKER_GATE_PASS
```

`git diff --check` passed.

`scripts/run_tests.sh` note: the full local wrapper run was interrupted by the Hermes background process manager before summary. A bounded `scripts/run_tests.sh --maxfail=1 -q --tb=short` comparison failed on both this branch and a detached clean `origin/feature/sachima-channel` baseline with the same first failures:

```text
tests/agent/test_auxiliary_client.py::TestAuxiliaryPoolAwareness::test_try_nous_uses_pool_entry
tests/agent/test_unsupported_parameter_retry.py::TestMaxTokensRetryHardening::test_sync_max_tokens_retry_matches_generic_phrasing
tests/gateway/test_discord_free_response.py::test_discord_free_channel_skips_auto_thread
tests/cron/test_cron_script.py::TestBuildJobPromptWithScript::test_script_empty_output_noted
```

These failures are treated as existing local baseline noise for this workflow/docs-only PR. The PR intentionally changes workflow configuration, so GitHub Nix CI remains the merge gate.

Changed-file scope:

```text
.github/workflows/nix.yml
AGENTS.md
docs/dev_log/2026-05-12-docs-only-ci-fast-path.md
```

This PR intentionally changes workflow configuration, so it is not docs-only and should run the full Nix CI path.

## 7. Non-approvals preserved

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
