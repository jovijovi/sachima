# Weather Rich Auto Hermes JSON Fix Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after human approval.

**Goal:** Make Feishu/Lark weather queries reliably emit weather rich-result markers/cards even when the model forgets `--format hermes-json`.

**Architecture:** Fix the brittle edge at the tool-dispatch boundary, not in the renderer. When the Feishu gateway agent is about to execute a trusted direct `weather_query.py` terminal command, normalize that command to request `--format hermes-json`. Keep rich-result extraction provenance-gated to trusted direct weather helper calls, and add regression coverage for the exact missed case.

**Tech Stack:** Python, Hermes Agent gateway, pytest, Feishu interactive card renderer.

**Created:** 2026-05-02 16:13 CST

---

## Context

- User-visible bug: weather answers in Feishu show as normal Markdown text plus the generic task-status card, not the dedicated weather rich-interaction card.
- Confirmed prior code supports weather cards when tool output contains `HERMES_RICH_RESULT_JSON_BEGIN/END` with `weather.v1` JSON.
- Confirmed prior regression tests pass for the already-covered case where the terminal command includes `--format hermes-json`:
  - `python -m pytest tests/gateway/test_rich_results.py tests/gateway/test_rich_weather_delivery.py tests/gateway/test_run_rich_weather.py -q`
  - Result observed before this plan: `19 passed in 2.65s`
- Actual missed behavior: the model can run the weather helper in default text mode, e.g.
  - `python3 /home/ubuntu/workspace/hermes/skills/productivity/weather-query/scripts/weather_query.py --lat ... --period today`
  - The helper defaults to `--format text`, so no rich marker exists for the gateway to extract.
- Existing skill wording was patched from “prefer” to “MUST”, but prompt/skill discipline alone is not a robust product fix.
- Current repo: `/home/ubuntu/workspace/hermes/repo/sachima`, branch `feature/sachima-channel`, remote `origin=https://github.com/jovijovi/sachima.git`.
- Local untracked planning/doc folders already exist: `.hermes/`, `docs/plans/`, `docs/superpowers/`. Do not broad-add them without diff inspection.
- The sachima repo itself has no `AI_FLOW.md`; applying the user’s required AI FLOW conventions from the Sachima workflow: approved plan first, narrow changes, tests, dev log, PR evidence, and reflection on missed coverage.

## Proposed approach

1. Add a small normalization helper for trusted direct weather helper terminal commands.
2. Apply it only for Feishu/Lark gateway sessions before terminal execution and before progress callbacks see the args.
3. Adjust rich-result provenance validation so a trusted direct weather helper command is trusted even if the original assistant tool call omitted `--format hermes-json`; security should still reject shell operators, pipes, aliases, fake paths, and non-terminal calls.
4. Add tests that fail before the implementation:
   - direct weather helper without `--format` gets normalized to `--format hermes-json` in Feishu context;
   - commands with explicit `--format text` are forced/replaced to `hermes-json` in Feishu context;
   - non-Feishu contexts are not normalized;
   - rich-result extraction accepts markers from a trusted direct weather helper command even if the original call omitted `--format`;
   - existing untrusted marker tests remain green.
5. Keep fallback behavior unchanged: if card send fails, render weather Markdown; if no rich marker exists, send normal text.

## Step-by-step plan

### Task 1: Add RED tests for command normalization

**Objective:** Prove the agent currently does not enforce `hermes-json` for Feishu weather helper terminal commands.

**Files:**
- Modify: `tests/run_agent/test_run_agent.py` or create `tests/run_agent/test_weather_rich_command_normalization.py`
- Likely import target after implementation: `run_agent._normalize_weather_rich_terminal_args` or equivalent helper.

**Test cases:**

```python
WEATHER_HELPER = "/home/ubuntu/workspace/hermes/skills/productivity/weather-query/scripts/weather_query.py"


def test_feishu_weather_helper_command_without_format_gets_hermes_json():
    args = {"command": f"python3 {WEATHER_HELPER} --lat 30.5728 --lon 104.0668 --period today"}

    normalized = _normalize_weather_rich_terminal_args("feishu", "terminal", args)

    assert normalized is not args
    assert normalized["command"].endswith("--format hermes-json")


def test_feishu_weather_helper_command_with_text_format_is_forced_to_hermes_json():
    args = {"command": f"python3 {WEATHER_HELPER} --location Chengdu --period today --format text"}

    normalized = _normalize_weather_rich_terminal_args("feishu", "terminal", args)

    assert "--format text" not in normalized["command"]
    assert "--format hermes-json" in normalized["command"]


def test_non_feishu_weather_helper_command_is_not_rewritten():
    args = {"command": f"python3 {WEATHER_HELPER} --location Chengdu --period today"}

    normalized = _normalize_weather_rich_terminal_args("telegram", "terminal", args)

    assert normalized == args
```

**Run to verify RED:**

```bash
python -m pytest tests/run_agent/test_weather_rich_command_normalization.py -q
```

Expected before implementation: import/function missing or assertions fail.

### Task 2: Implement minimal Feishu command normalization

**Objective:** Make Feishu gateway terminal calls to the direct weather helper request rich output automatically.

**Files:**
- Modify: `run_agent.py`

**Implementation shape:**

- Add constants/helper near existing tool-call utilities in `run_agent.py`:

```python
_WEATHER_HELPER_PATH = "/home/ubuntu/workspace/hermes/skills/productivity/weather-query/scripts/weather_query.py"
_FEISHU_RICH_PLATFORMS = {"feishu", "lark"}


def _normalize_weather_rich_terminal_args(platform: str | None, function_name: str, function_args: dict) -> dict:
    if function_name != "terminal" or str(platform or "").lower() not in _FEISHU_RICH_PLATFORMS:
        return function_args
    command = function_args.get("command")
    # parse with shlex; reject commands with shell operators/newlines using same safety posture as gateway.rich_results
    # accept only python/python3 + exact weather helper path
    # remove any existing --format / --format=<value>
    # append --format hermes-json
    # return shallow-copied args with rewritten command
```

- Use `shlex.split()` + `shlex.join()` to avoid brittle string edits.
- Reject shell operators/newlines/control chars before parsing. Do not rewrite chained/piped commands.
- Remove existing `--format`, `--format=text`, `--format=json`, or `--format=hermes-json`, then append `--format hermes-json`.
- Do not mutate the original dict in-place; return a copied dict only when changed.

**Hook points:**

- In `_execute_tool_calls_sequential()`, immediately after parsing `function_args` and before plugin hooks/progress callbacks/checkpoints.
- In `_execute_tool_calls_concurrent()`, immediately after parsing each `function_args` and before `parsed_calls.append(...)`, so callbacks and execution use normalized args.

**Run to verify GREEN for Task 1:**

```bash
python -m pytest tests/run_agent/test_weather_rich_command_normalization.py -q
```

Expected: pass.

### Task 3: Add RED test for rich extraction when original assistant call omitted `--format`

**Objective:** Ensure the gateway can still trust/extract the marker when the executed command was normalized but the stored assistant tool call may still show the original no-format command.

**Files:**
- Modify: `tests/gateway/test_rich_results.py`

**Test case:**

```python
def test_extracts_weather_result_from_direct_helper_without_format_when_tool_output_has_marker():
    payload = _weather_payload(summary="自动补齐后的天气")
    messages = _trusted_tool_messages_with_command(
        "python3 /home/ubuntu/workspace/hermes/skills/productivity/weather-query/scripts/weather_query.py --location Chengdu --period today",
        _marked(payload),
    )

    results = extract_rich_results_from_messages(messages)

    assert [r.type for r in results] == ["weather.v1"]
    assert results[0].payload["summary"] == "自动补齐后的天气"
```

If current test helpers only hardcode a command with `--format`, first extract a helper that accepts a command string.

**Run to verify RED:**

```bash
python -m pytest tests/gateway/test_rich_results.py::test_extracts_weather_result_from_direct_helper_without_format_when_tool_output_has_marker -q
```

Expected before implementation: fails because `_is_direct_weather_helper_command()` currently requires `--format hermes-json`.

### Task 4: Relax provenance gate safely for direct weather helper commands

**Objective:** Keep marker extraction secure while allowing normalized runs whose original assistant args omitted the format flag.

**Files:**
- Modify: `gateway/rich_results.py`
- Modify: `tests/gateway/test_rich_results.py` if helper refactor is needed

**Implementation shape:**

- Change `_is_direct_weather_helper_command(command)` so it verifies:
  - command is a string;
  - no shell operators/control chars;
  - `shlex.split(command)` succeeds;
  - first token is exactly `python` or `python3`;
  - second token is exactly `_WEATHER_HELPER_PATH`;
  - command is direct helper invocation, regardless of whether `--format hermes-json` is present.
- Keep existing rejection tests for echo, chained commands, pipes, fake python paths, missing ids, user/system/assistant-forged markers.
- Add an explicit test that `printf 'weather_query.py'`, shell chains, and fake paths remain rejected if not already precise enough.

**Run to verify GREEN:**

```bash
python -m pytest tests/gateway/test_rich_results.py -q
```

Expected: pass.

### Task 5: Add gateway-level regression for no-format weather helper card delivery

**Objective:** Prove the real rich delivery path can send a Feishu card when the tool output has a marker but original assistant args omitted `--format`.

**Files:**
- Modify: `tests/gateway/test_run_rich_weather.py`

**Test case:**

```python
@pytest.mark.asyncio
async def test_gateway_weather_rich_result_sends_card_for_direct_helper_without_format(monkeypatch):
    import gateway.run as gateway_run

    monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: {"display": {"rich_result_weather": "auto"}})
    adapter = WeatherCardAdapter(success=True)
    runner = _runner(adapter)
    agent_result = {"already_sent": False}

    response = await runner._maybe_deliver_weather_rich_result(
        event=_event(),
        source=_source(),
        response="final answer\n" + _marker(),
        agent_messages=_trusted_tool_messages(command="python3 ...weather_query.py --location Chengdu --period today"),
        agent_result=agent_result,
    )

    assert response == "final answer"
    assert agent_result["already_sent"] is True
    assert len(adapter.cards) == 1
```

**Run:**

```bash
python -m pytest tests/gateway/test_run_rich_weather.py -q
```

Expected: pass after Task 4.

### Task 6: Targeted verification

**Objective:** Verify the bugfix does not regress existing weather-card behavior.

**Run:**

```bash
python -m pytest \
  tests/run_agent/test_weather_rich_command_normalization.py \
  tests/gateway/test_rich_results.py \
  tests/gateway/test_rich_weather_delivery.py \
  tests/gateway/test_run_rich_weather.py \
  -q
```

Expected: all pass.

### Task 7: Manual local smoke check with real helper output

**Objective:** Verify the normalized command produces marker output the extractor can consume.

**Run:**

```bash
python3 /home/ubuntu/workspace/hermes/skills/productivity/weather-query/scripts/weather_query.py \
  --lat 30.5728 --lon 104.0668 --label '成都' --period today --format hermes-json
```

Expected:
- Human-readable summary appears.
- Output includes exactly one `HERMES_RICH_RESULT_JSON_BEGIN` / `HERMES_RICH_RESULT_JSON_END` block.
- JSON payload has `type: "weather.v1"`.

### Task 8: Dev log, reflection, and PR prep

**Objective:** Satisfy AI FLOW evidence and explicitly reflect on why prior coverage missed this.

**Files:**
- Create: `docs/dev_log/2026-05-02-weather-rich-auto-hermes-json.md`

**Required sections:**
- Task Background
- Problems Encountered
- Root Cause Analysis
- Solution
- Alternatives Considered
- Verification
- Follow-up Notes
- Missed Coverage Reflection

**Reflection to include:** Previous tests only covered the ideal path where the model already included `--format hermes-json`; they did not cover the real agent failure mode where the same weather helper was called in default text mode. The new tests must cover both the command-normalization boundary and the extraction/delivery boundary.

**PR body must include:**
- Summary
- Plan link: `docs/plans/2026-05-02-weather-rich-auto-hermes-json.md`
- Dev log link
- Verification commands/results
- Secret-safety statement: no secrets touched, no credentials committed

## Files likely to change

- `run_agent.py`
  - Add Feishu/Lark weather-helper terminal command normalization.
  - Apply normalization in both sequential and concurrent tool execution paths.
- `gateway/rich_results.py`
  - Relax direct weather helper provenance gate so format is not required for trust; keep direct-command safety checks.
- `tests/run_agent/test_weather_rich_command_normalization.py`
  - New tests for Feishu-only command normalization.
- `tests/gateway/test_rich_results.py`
  - Regression for extracting marker output when original command omitted format.
- `tests/gateway/test_run_rich_weather.py`
  - Gateway card-delivery regression for no-format direct weather helper calls.
- `docs/dev_log/2026-05-02-weather-rich-auto-hermes-json.md`
  - Required execution log and missed-coverage reflection.

## Verification

Minimum targeted gate:

```bash
python -m pytest \
  tests/run_agent/test_weather_rich_command_normalization.py \
  tests/gateway/test_rich_results.py \
  tests/gateway/test_rich_weather_delivery.py \
  tests/gateway/test_run_rich_weather.py \
  -q
```

Pre-PR broader sanity gate, time permitting:

```bash
python -m pytest tests/gateway/test_rich_results.py tests/gateway/test_rich_weather_delivery.py tests/gateway/test_run_rich_weather.py -q
python -m pytest tests/run_agent/test_run_agent.py tests/run_agent/test_weather_rich_command_normalization.py -q
python -m py_compile run_agent.py gateway/rich_results.py
```

Diff checks before commit:

```bash
git diff --stat
git diff --check
git status --short
```

## Risks and open questions

- **Risk: Mutating tool args after callbacks.** Mitigation: normalize before progress callbacks, `tool_start_callback`, checkpoints, and execution.
- **Risk: Assistant message still contains original no-format command.** Mitigation: rich-result provenance accepts direct weather helper commands without requiring the format flag, while still rejecting shell operators and fake paths.
- **Risk: Over-broad command rewriting.** Mitigation: only rewrite exact `python`/`python3` + exact weather helper path, only in Feishu/Lark platform sessions, and reject shell syntax.
- **Risk: `--format text` explicitly requested by user.** Product decision: in Feishu weather-card mode, rich output is required; the visible answer remains a fallback summary, so force `hermes-json` for direct helper calls.
- **Open question:** Whether to expose a user config switch to disable auto-normalization. Current plan does not add config; existing `display.rich_result_weather=off` already disables card delivery, but not helper output format normalization.

## Approval gate

Do not implement until the user explicitly approves this plan. After approval, use strict TDD: write failing tests first, verify RED, implement minimal code, verify GREEN, then document and PR.
