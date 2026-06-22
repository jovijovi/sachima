# Weather Rich JSON Prefix Wrapper Dev Log

**Date:** 2026-05-03
**Branch:** `fix/weather-rich-json-prefix-wrapper`
**Base:** `origin/feature/sachima-channel`

## Problem

Feishu weather cards did not render for a weather query even though the weather helper was called directly with `--format hermes-json` and emitted `HERMES_RICH_RESULT_JSON_BEGIN/END` markers.

## Root Cause

The terminal tool content was no longer a pure JSON wrapper. Hermes appended subdirectory context after the terminal JSON result:

```text
{"output": "...HERMES_RICH_RESULT..."}

[Subdirectory context discovered: workspace/hermes/repo/sachima/AGENTS.md]
...
```

`gateway.rich_results._extract_rich_results_from_tool_content()` used `json.loads(content)`, which fails with `Extra data` when non-JSON text follows the wrapper. Manual reproduction showed `json.JSONDecoder().raw_decode(content)` can parse the leading JSON wrapper and then `extract_rich_results_from_text(wrapper["output"])` returns the weather result.

## Fix

Added `_parse_json_object_prefix()` in `gateway/rich_results.py`:

- first attempts strict `json.loads()`;
- falls back to `json.JSONDecoder().raw_decode()` for leading JSON object wrappers with appended context text;
- returns only dict wrappers;
- leaves trusted weather helper provenance checks unchanged.

## Tests

Added `test_extracts_weather_result_from_json_wrapper_with_appended_context_text()` to `tests/gateway/test_rich_results.py`.

Verification run:

```bash
python -m pytest tests/gateway/test_rich_results.py tests/gateway/test_rich_weather_delivery.py -q
python -m py_compile gateway/rich_results.py gateway/run.py
git diff --check
```

Result: `15 passed` and syntax/diff checks passed.

## Invasiveness

Production change is limited to `gateway/rich_results.py`; no changes to terminal execution, AGENTS context discovery, Feishu adapter, renderer, or tool provenance security.
