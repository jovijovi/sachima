# agent-run-supervisor × Sachima Local/Offline Integration Implementation — Dev Log

## Scope

Received the user approval:

```text
approve_agent_run_supervisor_sachima_local_offline_integration_implementation_no_live_no_gateway_no_real_delivery
```

Interpretation: implement a default-off local/offline caller seam in Sachima. The caller is a local Sachima/FlowWeaver/Hermes controller or Activity wrapper, not the Gateway. No live behavior, Gateway involvement, real external ingress, real delivery, production config writes, platform adapter mutation, or Gateway restart/reload is approved.

## Role Split

```text
Hermes      — PM/controller, worktree/repo operator, deterministic verifier, evidence arbiter.
Claude Code — main programmer for the initial seam/tests.
Codex       — primary reviewer after deterministic gates pass.
```

Claude Code produced the first implementation candidate but the foreground wrapper timed out before a final JSON summary was written. Hermes verified no Claude process remained, inspected the diff, ran the tests, found failures, and applied narrow fixups for:

- pytest class identity mismatch caused by reloading `sachima_supervisor.local_offline` during the optional-dependency import test;
- public `CallerInvocationSpec` shape mismatch: the Sachima seam now builds only the actual public caller fields (`mode`, `role`, `role_file`, `prompt`, `context`, `cwd`, `runs_dir`, `sessions_dir`, `session_id`, `session_name`) rather than passing caller-private metadata;
- actual `CallerResult` mapping: `supervisor_status`, `artifact_dir`, `run_dir`, and `session_dir` are now recognized without leaking raw refs into the view model.

## Files Changed

Created:

- `sachima_supervisor/__init__.py`
- `sachima_supervisor/local_offline.py`
- `tests/sachima_supervisor/__init__.py`
- `tests/sachima_supervisor/test_local_offline.py`
- `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-implementation.md`
- `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-implementation-manifest.yaml`
- `docs/dev_log/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-implementation.md`

Updated:

- `pyproject.toml` — includes the new `sachima_supervisor` package in wheel/source package discovery.
- `docs/roadmap/current-status.md` — to be updated with this implementation candidate before PR.

## Implementation Notes

- The seam is default-off and requires exact approval token plus `enabled=True`.
- The mode allowlist excludes cancel/rollback.
- `agent_run_supervisor` is imported lazily only inside the invocation path; importing the Sachima seam does not require the external package.
- Tests inject fake spec/invoke functions so no external AGENT launches occur.
- The offline view model and evidence JSON are allowlisted dictionaries and exclude raw prompts, context, platform ids, card JSON, media paths, tool output, raw exceptions/tracebacks, and credentials.
- The library-owned `business_verdict` is always forced to `None`; caller-owned `caller_verdict` is separate.

## Verification So Far

```text
python3 -m pytest tests/sachima_supervisor/test_local_offline.py -q -o 'addopts='
initial candidate: 33 passed, 2 failed
post-public-caller-shape fix: 38 passed
post-Codex-blocker fixes: 42 passed

python3 -m py_compile sachima_supervisor/*.py tests/sachima_supervisor/test_local_offline.py
PASS

focused broader Sachima local/fake-surface set
110 passed

package/include + toolset regression subset
171 passed, 1 warning

actual agent-run-supervisor source smoke via PYTHONPATH
CallerInvocationSpec built; no metadata attr

changed-file allowlist / secret scan / forbidden-surface scan
0 violations / 0 findings / 0 findings

git diff --check
PASS
```

## Codex Primary Review

Codex primary review initially returned `BLOCK` for public payload leak surfaces:

1. `caller_verdict` could leak through view model/evidence.
2. malformed supervisor status could leak raw material.
3. public `status` / `error_code` kwargs could leak raw material.

Fixes added:

- boundary validation scans `caller_verdict`;
- `build_offline_view_model` revalidates mode, role source, and boundary;
- supervisor/public status and error codes are sanitized to stable code values;
- regression tests cover each blocker.

Final blocker-only Codex re-review:

```text
VERDICT: PASS
BLOCKERS: None
```

Remaining gates before merge:

```text
commit / push / PR / GitHub CI
```

## Explicit Non-Approvals Carried Forward

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
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
```
