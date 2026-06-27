# Sachima Boundary Register

> Full explicit non-approvals and drift-guard boundaries extracted from `current-status.md` during the 2026-06-26 status-dashboard slimdown. `current-status.md` keeps only the current high-signal summary.

## Explicit non-approvals

The current state does not approve any of the following outside the approved local/offline supervisor seam, the supervised local Activity first slice, the Phase C controlled local exec wrapper slice, the single approved Phase D read-only real local smoke, the Phase E local/offline lifecycle state-machine implementation, the separately approved Phase E-2 bounded real persistent-session execution merged in PR #127 plus its single minimal real smoke, WP1a's injected-fakes-only Claude Code read-only role/gate implementation, the single approved WP1b bounded Claude Code read-only real local smoke, the WP4 local/offline injected-fakes-only AI FLOW orchestrator implementation merged in PR #145, the P6-A default-off controlled-deterministic/injected-fake composition scope merged in PR #169, the P6-B Stage-1 default-off injected-fake read-only bridge source implementation merged in PR #171, and the single approved P6-B Stage-2 bounded read-only real smoke recorded by PR #181:

```text
real_external_sachima_ingress
additional_production_durable_runtime_code_expansion_beyond_p5_temporal_slice_1
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_involvement_or_mutation
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
reverse_proxy_or_tls_config_write
additional_real_local_smoke_execution
additional_real_agent_execution
additional_acpx_invocation
npx_fallback_or_network_fetch_evidence
feishu_or_im_delivery
unbounded_or_additional_persistent_session_execution
additional_or_unbounded_cancellation_execution
write_capable_claude_or_codex_roles
satine_or_hermes_profile_acp_execution
controlled_ai_flow_execution_beyond_p6a_controlled_deterministic_or_injected_fake_scope
additional_p6b_stage2_real_smoke_or_real_agent_execution_beyond_recorded_bounded_smoke_without_separate_approval
additional_p6b_stage2_real_smoke_without_cross_process_crash_no_relaunch_proof
additional_p6b_stage2_real_smoke_without_exact_runner_role_sink_evidence_pinning
```

> Scoped-grant note (2026-06-25, P5 Temporal Slice 1 + P6-A): the external Temporal service/Worker lifecycle token `approve_external_temporal_service_or_worker_lifecycle_for_sachima_p5_runtime` was granted for hermetic-local + staging namespace only and is ops-owned. PR #166 landed the code-bearing Slice 1 behind the caller-owned control surface. PR #168 then merged P6 pre-development governance, and PR #169 merged P6-A composition. P6-A may compose unmodified WP4 with the existing P5 StepExecutor seam and exercise hermetic-local controlled-deterministic/fake step bodies only; it does **not** lift the entries above for a production cluster (`sachima-p5-prod`), production traffic, a Gateway-owned or auto-started runtime lifecycle, P6 real agent/acpx/npx execution beyond recorded bounded smokes, live/default-on behavior, production config writes, or real delivery. PR #170 merged P6-B pre-development governance and PR #171 merged only the Stage-1 source implementation: default-off, injected-fake read-only runner gates only, no real launch. PR #174/#175/#178/#179 closed Stage-2 readiness, DoR, and durable claim-store prerequisites. PR #181 records the separately approved single bounded read-only P6-B real smoke as PASS. Additional P6-B/P6 real smoke, real acpx/npx/agent execution, write roles, file/git mutation by agent steps, broader controlled AI FLOW execution, Gateway/Feishu/live behavior, production config, service restart, and real delivery remain separate approvals.

The agent-run-supervisor Sachima local/offline integration design packet additionally carries, for its own scope, these non-approvals: `automatic_replies`, `worker_auto_routing`, `agent_to_agent_auto_routing`, `@all_fanout`, and `trusted_markdown_html_rendering`. See `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md`.
