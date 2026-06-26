# P6-B Stage-2 bounded real-smoke readiness — User review packet

Date: 2026-06-27
Status: Ready for docs-only PR review. Real smoke execution remains blocked.

## Verdict

```text
readiness/governance packet: PASS_WITH_WATCH
real smoke execution approval: DO NOT REQUEST YET / BLOCKED
```

## What changed

This branch does not change source code. It records the Stage-2 readiness decision after inspecting the merged P6-B Stage-1 bridge.

The hard conclusion is blunt: the bridge shape is sound, but real smoke is not yet ready to ask you to approve. The current claim store is in-process, so crash-after-claim / restart / recover-without-relaunch is not proven across a real process restart. Also the exact runner, local role overlay, artifact sink, workdir, evidence root, and max bounds are not pinned.

## What remains explicitly unapproved

No real smoke, no AGENT/acpx/npx launch, no write roles, no file/git mutation by agent step, no network/live/Gateway/Feishu/production config/real delivery, no service restart, no broader controlled AI FLOW expansion, and no clean active-run cancellation claim.

## Required next gate

If this PR is merged, the next safe request is:

```text
approve_agent_run_supervisor_sachima_p6b_stage2_host_local_dor_and_crash_no_relaunch_proof_pinned_local_runner_role_overlay_artifact_sink_evidence_only_no_real_agent_launch_no_real_smoke_no_write_no_git_no_network_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

That next gate may verify/pin the local runner, local-only role overlay, artifact sink, and crash/no-relaunch proof, but still must not run the real agent step.

## Later real-smoke approval shape

Only after the DoR/proof gate is green should Hermes ask for a single-run smoke phrase like:

```text
approve_agent_run_supervisor_sachima_p6b_bounded_read_only_real_agent_step_real_smoke_single_run_pinned_local_acpx_<binary_sha256>_role_<role_key>_adapter_<claude_or_codex>_workflow_<wf_id>_step_<step_id>_output_contract_<contract>_max_turns_<n>_max_seconds_<t>_out_of_repo_workdir_<path>_evidence_<path>_no_write_no_git_no_network_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery_after_crash_no_relaunch_proof
```

This branch intentionally does not ask you to approve that yet.
