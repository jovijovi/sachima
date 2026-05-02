# Weather Rich Auto Hermes JSON Dev Log

**Date:** 2026-05-02
**Branch:** `fix/weather-rich-auto-hermes-json`
**Plan:** `docs/plans/2026-05-02-weather-rich-auto-hermes-json.md`

## Task Background

Feishu weather responses were still rendering as normal Markdown text plus the generic task-status card instead of the dedicated weather interactive card. The rich weather card code existed and passed tests when tool output contained `HERMES_RICH_RESULT_JSON_BEGIN/END`, but real turns could call the weather helper without `--format hermes-json`, producing only text output.

## Problems Encountered

- The previous test suite covered the ideal path where the assistant already included `--format hermes-json`.
- The actual failure mode was upstream of rendering: the helper defaulted to plain text, so the gateway had no rich-result marker to extract.
- A prompt/skill update alone was insufficient because future model calls could still omit the format flag.
- An early smoke-check command piped helper output into `python -`, which consumed stdin as Python source rather than data. It was replaced with a subprocess-based smoke check.

## Root Cause Analysis

The gateway weather card pipeline depends on a trusted terminal tool result containing a `weather.v1` rich-result marker. When the model invoked:

```bash
python3 /home/ubuntu/workspace/hermes/skills/productivity/weather-query/scripts/weather_query.py --lat ... --period today
```

instead of adding `--format hermes-json`, the helper emitted only Markdown text. The gateway therefore had no marker block and correctly fell back to normal text delivery. Existing tests missed this because they hardcoded assistant tool-call arguments with `--format hermes-json`.

## Solution

- Added Feishu/Lark terminal command normalization in `run_agent.py`:
  - only for `terminal` calls;
  - only when platform is `feishu` or `lark`;
  - only for exact direct `python`/`python3` invocation of `/home/ubuntu/workspace/hermes/skills/productivity/weather-query/scripts/weather_query.py`;
  - rejects shell operators, pipes, redirects, comments, `$`, newlines/control chars, fake paths, and other commands;
  - removes any existing `--format`/`--format=<value>` and appends `--format hermes-json`.
- Applied normalization before tool progress callbacks, tool-start callbacks, checkpoint checks, and execution in both sequential and concurrent tool-call paths.
- Relaxed `gateway/rich_results.py` provenance validation so exact direct weather helper commands are trusted even when the original assistant tool-call args omitted `--format`; safety checks remain strict.
- Added regression tests for:
  - Feishu no-format command normalization;
  - Feishu explicit `--format text` being forced to `hermes-json`;
  - Lark no-format command normalization;
  - non-Feishu commands not being rewritten;
  - shell/fake-path commands not being rewritten;
  - rich-result extraction from direct helper commands without format;
  - gateway Feishu card delivery for no-format direct helper calls.

## Alternatives Considered

- **Only update the skill/prompt wording:** rejected because it relies on the model remembering a convention.
- **Auto-generate cards from final answer text:** rejected because parsing prose would be brittle and could hallucinate structured weather data.
- **Change the helper default format to `hermes-json`:** rejected because CLI/plain-text weather usage should remain clean outside rich IM contexts.
- **Trust any marker from terminal output:** rejected for safety; provenance remains limited to the exact direct helper command.

## Verification

Commands run from `/home/ubuntu/workspace/hermes/worktrees/sachima/weather-rich-auto-hermes-json`:

```bash
python -m pytest \
  tests/run_agent/test_weather_rich_command_normalization.py \
  tests/gateway/test_rich_results.py \
  tests/gateway/test_rich_weather_delivery.py \
  tests/gateway/test_run_rich_weather.py \
  -q
```

Result:

```text
26 passed in 5.28s
```

```bash
python -m pytest tests/run_agent/test_run_agent.py tests/run_agent/test_weather_rich_command_normalization.py -q
```

Result:

```text
302 passed in 8.67s
```

```bash
python -m py_compile run_agent.py gateway/rich_results.py
```

Result: passed.

```bash
git diff --check
```

Result: passed.

Helper smoke check via Python subprocess:

```text
BEGIN markers: 1
END markers: 1
weather.v1: True
preview: 按 **成都** 查，当前时间：2026-05-02 16:31 CST。
```

Independent review:

```text
Verdict: APPROVED
Critical: None
Important: None
Minor: duplicate helper path/operator logic between run_agent.py and gateway/rich_results.py; acceptable for this fix, centralize later if it grows.
```

## Secret Safety

No secrets, tokens, credentials, cookies, or real webhook signing values were added. Test data uses public helper paths and dummy command strings only.

## Missed Coverage Reflection

The earlier weather-card implementation verified extraction and delivery only when the assistant already called the helper with `--format hermes-json`. That proved the renderer path but not the real agent behavior. The missing test was at the boundary where model-chosen terminal arguments enter execution. This bug slipped because coverage assumed perfect tool-call args instead of reproducing the failure mode: direct weather helper invocation in default text mode.

The new coverage now checks both boundaries:

1. `run_agent.py` normalizes direct Feishu/Lark weather helper terminal commands before execution.
2. `gateway/rich_results.py` can trust/extract marker output even if stored assistant args show the pre-normalized no-format command.
3. `gateway/run.py` card delivery sends the Feishu interactive card for that no-format scenario.

## Follow-up Notes

- If more rich-result helpers are added, consider centralizing direct-helper command validation to avoid drift between execution normalization and gateway provenance checks.
- `display.rich_result_weather=off` still controls card delivery; this fix only ensures Feishu/Lark helper output is rich-capable when direct weather helper calls occur.
