from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIOS = ROOT / "scenarios" / "multi_intent_cases.jsonl"

MODE = "deterministic_parser_baseline"


def make_intent(intent_id: str, order_index: int, title: str, *, status: str = "pending", dependencies: list[str] | None = None) -> dict[str, Any]:
    return {
        "intent_id": intent_id,
        "order_index": order_index,
        "title": title,
        "status": status,
        "dependencies": dependencies or [],
    }


def load_scenarios(path: Path) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            scenarios.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
    return scenarios


def deterministic_plan(user_text: str) -> list[dict[str, Any]]:
    text = user_text.strip()

    if _is_ambiguous_deploy_request(text):
        return [make_intent("clarify_target", 0, "澄清目标仓库、环境或部署范围", status="blocked")]

    if "先分析" in text and "计划" in text and ("批准" in text or "再改" in text or "不要改" in text):
        return [
            make_intent("code_inspect", 0, "分析代码问题"),
            make_intent("implementation_plan", 1, "给出执行计划", dependencies=["code_inspect"]),
            make_intent("approval_wait", 2, "等待用户批准后再改代码", status="blocked", dependencies=["implementation_plan"]),
        ]

    if "天气" in text and "今天" in text and "明天" in text and ("比较" in text or "哪天" in text or "适合" in text):
        return [
            make_intent("weather_today", 0, "查询今天天气"),
            make_intent("weather_tomorrow", 1, "查询明天天气"),
            make_intent("weather_compare", 2, "比较两天天气并判断哪天更适合出门", dependencies=["weather_today", "weather_tomorrow"]),
        ]

    candidates: list[tuple[int, str, str, str]] = []
    _add_if(candidates, text, ["几点", "当前时间", "现在时间"], "current_time", "查询当前时间")
    _add_if(candidates, text, ["今晚", "今晚下雨", "今晚天气"], "weather_tonight", "查询今晚降雨或天气")
    _add_if(candidates, text, ["今天天气", "今天的天气", "今天 天气"], "weather_today", "查询今天天气")
    _add_if(candidates, text, ["明天天气", "明天的天气", "明天 天气"], "weather_tomorrow", "查询明天天气")
    _add_if(candidates, text, ["磁盘", "磁盘空间", "空间剩余"], "disk_status", "查询当前磁盘剩余空间")

    deduped: dict[str, tuple[int, str, str, str]] = {}
    for item in candidates:
        pos, intent_id, title, status = item
        if intent_id not in deduped or pos < deduped[intent_id][0]:
            deduped[intent_id] = item
    ordered = sorted(deduped.values(), key=lambda item: item[0])
    if not ordered:
        return [make_intent("clarify_target", 0, "澄清用户目标和执行范围", status="blocked")]
    intents = []
    for index, (_pos, intent_id, title, status) in enumerate(ordered):
        if intent_id == "disk_status" and ("权限不足" in text or "失败" in text):
            status = "failed"
        intents.append(make_intent(intent_id, index, title, status=status))
    return intents


def _add_if(candidates: list[tuple[int, str, str, str]], text: str, needles: list[str], intent_id: str, title: str) -> None:
    positions = [text.find(needle) for needle in needles if text.find(needle) >= 0]
    if positions:
        candidates.append((min(positions), intent_id, title, "pending"))


def _is_ambiguous_deploy_request(text: str) -> bool:
    return bool(re.search(r"部署|上线|发布", text)) and not any(
        marker in text for marker in ["仓库", "项目", "环境", "服务器", "路径", "branch", "repo", "production", "staging"]
    )


def compare_intents(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    expected_ids = [item["intent_id"] for item in expected]
    actual_ids = [item["intent_id"] for item in actual]
    if expected_ids != actual_ids:
        diff["expected_intent_ids"] = expected_ids
        diff["actual_intent_ids"] = actual_ids
    expected_status = {item["intent_id"]: item.get("status", "pending") for item in expected}
    actual_status = {item["intent_id"]: item.get("status", "pending") for item in actual}
    if expected_status != actual_status:
        diff["expected_status"] = expected_status
        diff["actual_status"] = actual_status
    expected_deps = {item["intent_id"]: item.get("dependencies", []) for item in expected}
    actual_deps = {item["intent_id"]: item.get("dependencies", []) for item in actual}
    if expected_deps != actual_deps:
        diff["expected_dependencies"] = expected_deps
        diff["actual_dependencies"] = actual_deps
    expected_order = [item.get("order_index") for item in expected]
    actual_order = [item.get("order_index") for item in actual]
    if expected_order != actual_order:
        diff["expected_order_index"] = expected_order
        diff["actual_order_index"] = actual_order
    return diff


def validate_scenarios(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for scenario in scenarios:
        actual = deterministic_plan(scenario["user_text"])
        expected = scenario["expected_intents"]
        diff = compare_intents(expected, actual)
        passed = not diff and scenario.get("expected_gate_c") == "pass"
        results.append(
            {
                "scenario_id": scenario["scenario_id"],
                "passed": passed,
                "diff": diff,
                "expected_intents": expected,
                "actual_intents": actual,
            }
        )
    total = len(results)
    failed = sum(1 for item in results if not item["passed"])
    return {
        "mode": MODE,
        "total": total,
        "passed": total - failed,
        "failed": failed,
        "gate_c_ready": failed == 0 and total > 0,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate FlowWeaver Phase 3 multi-intent scenarios.")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    args = parser.parse_args(argv)

    summary = validate_scenarios(load_scenarios(args.scenarios))
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"{summary['passed']}/{summary['total']} scenarios passed in {summary['mode']}")
        for item in summary["results"]:
            mark = "PASS" if item["passed"] else "FAIL"
            print(f"{mark} {item['scenario_id']}")
            if item["diff"]:
                print(json.dumps(item["diff"], ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
