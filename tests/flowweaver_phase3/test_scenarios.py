from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "prototypes" / "flowweaver_phase3"
SCENARIOS = ROOT / "scenarios" / "multi_intent_cases.jsonl"
SCRIPT = ROOT / "scripts" / "validate_scenarios.py"

REQUIRED_SCENARIOS = {
    "mixed_time_weather_disk_tomorrow",
    "dependent_weather_compare",
    "ai_flow_plan_approval_wait",
    "weather_time_disk_rich_final_coverage",
    "partial_failure_keeps_successes",
    "ambiguous_requires_clarification",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_scenario_corpus_contains_required_gate_c_cases() -> None:
    scenarios = load_jsonl(SCENARIOS)

    assert {item["scenario_id"] for item in scenarios} == REQUIRED_SCENARIOS
    for scenario in scenarios:
        assert scenario["user_text"]
        assert scenario["expected_intents"]
        assert [intent["order_index"] for intent in scenario["expected_intents"]] == list(range(len(scenario["expected_intents"])))
        assert "expected_gate_c" in scenario
        assert "fake-" not in repr(scenario)


def test_validate_scenarios_json_summary_passes_all_required_cases() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    summary = json.loads(result.stdout)

    assert summary["total"] == 6
    assert summary["passed"] == 6
    assert summary["failed"] == 0
    assert summary["gate_c_ready"] is True
    assert summary["mode"] == "deterministic_parser_baseline"


def test_validate_scenarios_reports_compact_diff_for_bad_expected_fixture(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.jsonl"
    scenario = {
        "scenario_id": "bad_fixture",
        "user_text": "现在几点了？今天天气怎样？",
        "expected_gate_c": "pass",
        "expected_intents": [
            {"intent_id": "current_time", "order_index": 0, "title": "查询当前时间", "status": "pending", "dependencies": []}
        ],
    }
    bad_file.write_text(json.dumps(scenario, ensure_ascii=False) + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--scenarios", str(bad_file), "--json"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    summary = json.loads(result.stdout)

    assert result.returncode == 1
    assert summary["failed"] == 1
    assert summary["results"][0]["passed"] is False
    assert "expected_intent_ids" in summary["results"][0]["diff"]
    assert "actual_intent_ids" in summary["results"][0]["diff"]


def test_ambiguity_and_partial_failure_do_not_collapse_to_fake_success() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    summary = json.loads(result.stdout)
    by_id = {item["scenario_id"]: item for item in summary["results"]}

    ambiguous = by_id["ambiguous_requires_clarification"]["actual_intents"]
    assert ambiguous[0]["status"] == "blocked"
    assert ambiguous[0]["intent_id"] == "clarify_target"

    partial = by_id["partial_failure_keeps_successes"]["actual_intents"]
    statuses = {intent["intent_id"]: intent["status"] for intent in partial}
    assert statuses["current_time"] == "pending"
    assert statuses["disk_status"] == "failed"
    assert statuses["weather_today"] == "pending"
