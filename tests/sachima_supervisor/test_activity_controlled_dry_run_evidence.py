"""Controlled local dry-run evidence fixtures for supervised Activity.

This phase is local/offline only. It must use injected/fake supervisor outcomes
only and prove deterministic evidence for role mapping, idempotency, sanitized
state/query behavior, and unsafe lower-outcome collapse without live/Gateway/real
AGENT execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            out.extend(_walk_strings(str(key)))
            out.extend(_walk_strings(item))
        return out
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            out.extend(_walk_strings(item))
        return out
    return []


def _assert_no_raw_material(payload: dict[str, Any]) -> None:
    rendered = "\n".join(_walk_strings(payload)).lower()
    forbidden = (
        "oc_",
        "ou_",
        "om_",
        "card_json",
        "media:",
        "/tmp/",
        "raw-",
        "traceback",
        "bearer ",
        "api_key",
        "private_key",
    )
    for marker in forbidden:
        assert marker not in rendered, f"leaked forbidden marker: {marker}"


def test_controlled_local_dry_run_evidence_is_deterministic_and_fixture_backed(
    tmp_path: Path,
) -> None:
    from sachima_supervisor.activity_evidence import (
        CONTROLLED_DRY_RUN_EVIDENCE_APPROVAL_MARKER,
        build_controlled_local_dry_run_evidence,
        write_controlled_local_dry_run_evidence,
    )

    evidence = build_controlled_local_dry_run_evidence()

    assert evidence["type"] == (
        "sachima.supervisor.controlled_local_activity_dry_run_evidence.v1"
    )
    assert evidence["approval_marker"] == CONTROLLED_DRY_RUN_EVIDENCE_APPROVAL_MARKER
    assert evidence["scope"] == {
        "local_offline_only": True,
        "exec_dry_run_only": True,
        "injected_supervisor_only": True,
        "live_approved": False,
        "gateway_approved": False,
        "real_delivery_approved": False,
        "real_agent_execution_approved": False,
        "controlled_ai_flow_execution_approved": False,
    }
    assert evidence["summary"] == {
        "scenario_count": 5,
        "real_supervisor_invocations": 0,
        "injected_supervisor_invocations": 5,
        "all_durable_states_sanitized": True,
        "idempotency_replay_without_second_call": True,
        "unsafe_lower_outcome_collapsed": True,
    }
    assert [scenario["name"] for scenario in evidence["scenarios"]] == [
        "docs_planner_success",
        "verifier_success",
        "idempotency_replay",
        "idempotency_conflict",
        "unsafe_supervisor_outcome",
    ]
    assert evidence["fixture_digest"].startswith("sha256:")

    for scenario in evidence["scenarios"]:
        assert scenario["mode"] == "exec_dry_run"
        assert scenario["supervisor_source"] == "injected_fake"
        assert "durable_state" in scenario or "error_code" in scenario
        if "durable_state" in scenario:
            _assert_no_raw_material(scenario["durable_state"])

    fixture_path = Path(
        "tests/fixtures/sachima_supervisor/controlled_local_activity_dry_run_evidence.v1.json"
    )
    assert fixture_path.exists()
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture == evidence

    output_path = tmp_path / "controlled_local_activity_dry_run_evidence.v1.json"
    returned_path = write_controlled_local_dry_run_evidence(output_path)
    assert returned_path == output_path
    assert json.loads(output_path.read_text(encoding="utf-8")) == evidence


def test_activity_evidence_source_has_no_live_gateway_or_real_supervisor_path() -> None:
    import sachima_supervisor.activity_evidence as activity_evidence

    source = Path(activity_evidence.__file__).read_text(encoding="utf-8").lower()

    for token in ("aiohttp", "httpx", "lark_oapi", "feishu", "webhook"):
        assert token not in source, f"forbidden live/platform token: {token}"
    for statement in (
        "import gateway",
        "from gateway",
        "import requests",
        "from requests",
        "invoke_local_offline_supervisor(",
    ):
        assert statement not in source, f"forbidden runtime/live call surface: {statement}"
