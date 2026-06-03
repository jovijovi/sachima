# Dev Log — agent-run-supervisor × Sachima Supervised Local Activity — Controlled Local Dry-Run Evidence

Date: 2026-06-03
Branch: `feat/supervised-local-activity-dry-run-evidence`
Base: `release/sachima` @ `8152d09ee0f847d335a76e2ef90459642fb72e9d`
Approval: `approve_agent_run_supervisor_sachima_supervised_local_activity_controlled_local_dry_run_evidence_no_live_no_gateway_no_real_delivery_no_real_agent_execution`

## Scope

Added a deterministic, fixture-backed controlled local dry-run evidence document for the merged `exec_dry_run` Activity wrapper:

- injected/fake supervisor outcomes only;
- `exec_dry_run` only, against an in-memory `ActivityStateStore`;
- five scenarios proving role mapping, idempotency replay/conflict, sanitized state/query, and unsafe lower-outcome collapse;
- committed fixture so any drift is caught in CI;
- no Gateway, no live, no real delivery, no real AGENT execution, no controlled AI FLOW execution;
- the real supervisor runtime path is never imported or called.

## TDD Evidence

RED evidence before production code (Hermes-authored tests):

```text
python3 -m pytest tests/sachima_supervisor/test_activity_controlled_dry_run_evidence.py -q
2 failed — ModuleNotFoundError: No module named 'sachima_supervisor.activity_evidence'
```

Focused GREEN after implementation:

```text
python3 -m pytest tests/sachima_supervisor/test_activity_controlled_dry_run_evidence.py tests/sachima_supervisor/test_activity.py tests/sachima_supervisor/test_local_offline.py -q
68 passed in 0.54s
```

Compile / lint / diff hygiene:

```text
python3 -m py_compile sachima_supervisor/*.py tests/sachima_supervisor/test_activity_controlled_dry_run_evidence.py tests/sachima_supervisor/test_activity.py tests/sachima_supervisor/test_local_offline.py
# exit 0

python3 -m ruff check sachima_supervisor tests/sachima_supervisor/test_activity_controlled_dry_run_evidence.py tests/sachima_supervisor/test_activity.py
# All checks passed!

git diff --check
# exit 0
```

## Evidence Document

`build_controlled_local_dry_run_evidence()` is deterministic (no timestamps, no randomness) and equals the committed fixture
`tests/fixtures/sachima_supervisor/controlled_local_activity_dry_run_evidence.v1.json`.

Summary block:

```text
scenario_count: 5
real_supervisor_invocations: 0
injected_supervisor_invocations: 5
all_durable_states_sanitized: true
idempotency_replay_without_second_call: true
unsafe_lower_outcome_collapsed: true
```

Scenarios (in order): `docs_planner_success`, `verifier_success`, `idempotency_replay`, `idempotency_conflict`, `unsafe_supervisor_outcome`. Each records `mode = exec_dry_run` and `supervisor_source = injected_fake`.

## Implementation Notes

`sachima_supervisor/activity_evidence.py` runs each scenario through the real Activity `start`/`query` API with an injected counting fake. The injected-invocation total is `5`: one each for the two success scenarios and the unsafe scenario, one for the replay scenario (the identical-key retry replays stored state without a second call), and one for the conflict scenario (the first start invokes; the incompatible retry fails closed before any second call). `real_supervisor_invocations` is `0` because no real supervisor path is ever imported or called.

Durable states are read straight from `SupervisedLocalActivityResult.to_durable_state()`, which is already sanitized. The builder additionally self-verifies each durable state against the same no-leak markers asserted by the tests (`oc_`/`ou_`/`om_`, `card_json`, `media:`, `/tmp/`, `raw-`, `traceback`, `bearer `, `api_key`, `private_key`) and feeds the result into `all_durable_states_sanitized`.

`fixture_digest` is a SHA-256 over the canonical document body (excluding the digest field itself), so the fixture is self-describing and tamper-evident.

`write_controlled_local_dry_run_evidence(path)` serializes the same document and returns the `Path`. `sachima_supervisor/__init__.py` now exports `CONTROLLED_DRY_RUN_EVIDENCE_APPROVAL_MARKER`, `build_controlled_local_dry_run_evidence`, and `write_controlled_local_dry_run_evidence`.

## Forbidden-Surface Posture

`activity_evidence.py` contains none of the forbidden live/platform tokens (`aiohttp`, `httpx`, `lark_oapi`, `feishu`, `webhook`) and none of the forbidden runtime/live call surfaces (`import gateway`, `from gateway`, `import requests`, `from requests`, `invoke_local_offline_supervisor(`). This is asserted by `test_activity_evidence_source_has_no_live_gateway_or_real_supervisor_path`.

## Non-Approvals Preserved

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
real_agent_execution
controlled_ai_flow_execution
```

## Review Evidence

Hermes verification after Claude Code implementation:

```text
changed-file allowlist: 8 changed paths, 0 extra
manifest + fixture equality: pass
marker gate: pass
forbidden-surface scan: pass
secret-shaped scan: 0 findings
pytest: 68 passed
py_compile: pass
ruff: pass
git diff --check: pass
```

Codex primary review:

```text
VERDICT: PASS
BLOCKERS:
- None
```

Reviewer notes: inspected requested status, diffs, untracked files, roadmap preflight, canonical roadmap, docs, code, tests, and fixture; confirmed fresh evidence equals the fixture, with 0 real supervisor invocations and 5 injected supervisor invocations.

## Pending Gates

- GitHub PR creation, CI, and PR-number recording (PR number unknown until Hermes opens it).
