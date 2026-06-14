# Feishu GitHub PR approval card

Date: 2026-06-15
Branch: `feature/feishu-pr-approval-card`
Base: `release/sachima`

## Goal

Make recurring GitHub PR merge approvals available as a Feishu interactive card so the user can click **批准**, **拒绝**, or **忽略** instead of typing `批准合并 PR #N`.

## Scope

- Update the GitHub PR workflow skill with Feishu approval-card rules.
- Add Feishu card rendering for PR approval requests.
- Add Feishu card action handling for three choices:
  - approve: route a guarded synthetic user approval back into the same chat/session.
  - reject: record a rejected/declined card result; do not merge.
  - ignore: record an ignored card result; do not merge.
- Support localized PR approval cards (`locale: auto | zh-CN | en`). In Feishu, `auto` currently resolves to Chinese.
- Preserve PR metadata in the resolved card after approve/reject/ignore so the user can still see repo/title/head SHA/URL.
- Preserve existing dangerous-command approval buttons and update prompt buttons unchanged.

## First-slice behavior

The first implementation intentionally routes approval clicks back into Hermes as a synthetic user message instead of merging directly in the callback. This keeps the existing agent pre-merge gate, GitHub checks, Codex review policy, post-merge cleanup discipline, and user-visible audit trail in the normal workflow.

The synthetic approve command must include the repo, PR number, and expected head SHA so the agent can re-check live PR state before merge.

## Non-goals

- No direct deterministic merge worker in this slice.
- No production Gateway restart in this PR.
- No bypass of pre-merge verification.
- No broad approval framework for deploys/restarts/config writes.
- No changes to GitHub credentials or Feishu secrets.

## Acceptance criteria

1. Feishu card payload contains PR repo, number, URL, title, base/head branch, and required head SHA.
2. Button values carry a distinct `hermes_github_pr_action` and `github_pr_approval_id`; PR metadata is stored server-side in the adapter.
3. The tool accepts optional `locale` (`auto`, `zh-CN`, `en`) and rejects unsupported locale values before sending.
4. Initial and resolved cards render localized text for Chinese and English.
5. Resolved approve/reject/ignore cards preserve original PR repo/title/base/head/head SHA/URL instead of replacing the card with status-only text.
6. Approve click schedules a synthetic `批准合并 PR #N` user message through existing guarded Feishu message handling.
7. Reject/ignore clicks do not schedule a merge command and return a resolved card.
8. Unauthorized clickers, chat mismatch, and already-resolved/unknown approval IDs do nothing.
9. Existing command approval and update prompt card tests remain green.
10. Skill documents when to send the card and the required fresh-check rules.

## Verification plan

- RED/GREEN focused tests in `tests/gateway/test_feishu_approval_buttons.py`.
- `python -m compileall` for changed Python files.
- Focused pytest for Feishu approval buttons, approval-card tool, and toolset exposure.
- Existing GitHub/PR workflow skill gains a Feishu approval-card section.
- Codex blocker-only review before PR.
