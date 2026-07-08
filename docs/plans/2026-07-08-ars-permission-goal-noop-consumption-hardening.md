# ARS S2 permission / goal / no-op consumption hardening (Sachima side)

- Date: 2026-07-08
- Scope: `sachima_supervisor/activity_session_real_execution.py` + its test module only.
- Status: implemented on branch `feat/ars-0-2-permission-goal-20260708` (local slice; unmerged).
- Upstream basis: agent-run-supervisor S2 branch `feat/permissioned-persistent-goal-20260708`
  (role-derived `--permission-policy` for persistent prompt turns, fail-closed `no_op`
  status, additive `observed_effect` result key, `goal.py` `/goal` composition,
  plan `docs/plans/active/2026-07-08-permissioned-session-goal-noop.md` in that repo).

## Incident driver

A supervised persistent-session `/goal …` prompt turn ran under the upstream hardcoded
`--deny-all` block, exited `0` with no agent output and no tool events, was classified
`completed` upstream, and was therefore consumed as a successful turn here. Two layers
must fail closed: upstream classification (fixed in ARS S2) and this consumer boundary
(this slice).

## Changes (TDD; tests first in
`tests/sachima_supervisor/test_activity_session_real_execution.py`)

1. **Upstream `no_op` consumption** — `run_real_persistent_session_turn` maps a turn
   whose supervisor status label is `no_op` to the new stable failure code
   `activity_turn_no_op` (previously the generic `activity_supervisor_failed`).
2. **Empty-completed guard (defense in depth)** — `_RuntimeTurnResult` gains
   `observed_effect: bool | None`; the backend reads the additive
   `observed_effect` key from the ARS turn result payload. A turn reported
   `completed` with `observed_effect=False` fails closed as `activity_turn_no_op`.
   `None` (the pinned `agent-run-supervisor==0.1.3` payload shape, which predates the
   key) stays allowed so the pinned release keeps working; real empty-completed
   protection activates automatically with the pin bump.
3. **Goal-turn composition delegate** — `compose_goal_turn_prompt(goal_text)` lazily
   delegates to `agent_run_supervisor.goal.compose_goal_prompt` (ships after 0.1.3).
   Missing module → fail closed `activity_goal_unsupported` (never sends unvalidated
   text); upstream rejection → `activity_goal_rejected`. Module import stays free of
   any `agent_run_supervisor` dependency.

## Boundaries (unchanged)

No live/default-on behavior, no Gateway/Feishu surface, no production config, no real
delivery, no write-capable roles, no real agent/acpx/npx execution in tests (injected
fake backend only), and the packaged-dependency boundary from
`docs/roadmap/boundary-register.md` (2026-07-07 note) holds: ARS is consumed only as
the exact-pinned installed distribution.

## Pin / lock follow-up (deliberately NOT done in this slice)

`agent-run-supervisor==0.1.3` remains the pin: the S2 upstream capabilities are not
yet released, and per the packaged-dependency boundary unreleased ARS is validated
only via a locally built wheel in an isolated environment. After ARS ships a release
containing S2 (e.g. `0.1.4`):

```bash
# edit pyproject.toml: agent-run-supervisor==0.1.4 (both extras) and bump the
# exclude-newer-package date for agent-run-supervisor accordingly, then:
uv lock
uv run pytest tests/sachima_supervisor/test_activity_session_real_execution.py -q
```

**Executed 2026-07-08** (branch `feat/ars-0-1-4-package-upgrade-20260708`): upstream
released `agent-run-supervisor==0.1.4` (S2 capabilities; PyPI upload
2026-07-08T07:13:38Z). Both pyproject extras and
`EXPECTED_AGENT_RUN_SUPERVISOR_VERSION` now pin `0.1.4`, the
`[tool.uv].exclude-newer-package` override for `agent-run-supervisor` moved to
`2026-07-08T07:20:00Z` (global `exclude-newer` window untouched), and `uv.lock`
was regenerated via `uv lock --upgrade-package agent-run-supervisor`. The
`observed_effect` empty-completed guard is live against real payloads from this
pin onward; the `activity_goal_unsupported` / missing-goal-module path remains
as fail-closed protection for mis-provisioned environments.

## Verification commands (blocked in the implementing session; run before merge)

```bash
uv run pytest tests/sachima_supervisor/test_activity_session_real_execution.py -q
uv run pytest tests/sachima_supervisor -q
```

Expected RED→GREEN evidence: before the source change, the four new no-op/observed-effect
tests fail (`_RuntimeTurnResult` lacks `observed_effect`; `activity_turn_no_op` code and
`compose_goal_turn_prompt` do not exist); after it, the module's full test file passes.
