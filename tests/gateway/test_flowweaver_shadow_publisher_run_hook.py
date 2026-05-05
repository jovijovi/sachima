"""Run-loop tests for the FlowWeaver Phase 5D shadow runtime publisher hook."""

from __future__ import annotations

import logging

import pytest

from gateway.flowweaver_shadow_dry_run import FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY
from gateway.flowweaver_shadow_publisher import (
    FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY,
    FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_TYPE,
)
from tests.gateway.test_run_progress_topics import OptionalProgressAgent, _run_with_agent

PRIVATE_MESSAGE_ID = "om_" + "private_message"
PRIVATE_CHAT_ID = "oc_" + "private_chat"
SECRET_SHAPED = "sk-" + "123456789012"


def _shadow_config(*, dry_run: bool = False, publish: bool = False) -> dict[str, object]:
    tracker: dict[str, object] = {
        "enabled": False,
        "flowweaver_shadow": True,
    }
    if dry_run:
        tracker["flowweaver_shadow_dry_run"] = True
    if publish:
        tracker["flowweaver_shadow_runtime_publish"] = True
    return {"display": {"tool_progress": "off", "task_tracker": tracker}}


@pytest.mark.asyncio
async def test_shadow_runtime_publication_default_off_and_dry_run_only_stays_absent(monkeypatch, tmp_path) -> None:
    default_tmp = tmp_path / "default-off"
    default_tmp.mkdir()
    adapter_default, result_default = await _run_with_agent(
        monkeypatch,
        default_tmp,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-runtime-publish-default-off",
        config_data={"display": {"tool_progress": "off", "task_tracker": {"enabled": False}}},
    )
    assert FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY not in result_default
    assert adapter_default.sent == []
    assert adapter_default.edits == []

    dry_run_tmp = tmp_path / "dry-run-only"
    dry_run_tmp.mkdir()
    adapter_dry_run, result_dry_run = await _run_with_agent(
        monkeypatch,
        dry_run_tmp,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-runtime-publish-dry-run-only",
        config_data=_shadow_config(dry_run=True, publish=False),
    )

    assert FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY in result_dry_run
    assert FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY not in result_dry_run
    assert adapter_dry_run.sent == []
    assert adapter_dry_run.edits == []


@pytest.mark.asyncio
async def test_shadow_runtime_publication_attaches_only_with_full_phase5d_gate(monkeypatch, tmp_path) -> None:
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-runtime-publish-enabled",
        config_data=_shadow_config(dry_run=True, publish=True),
    )

    assert result[FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY]["type"] == FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_TYPE
    assert result[FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY]["verdict"] == "ready"
    assert result[FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY]["start_request"]["operation"] == "start_transaction"
    assert result[FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY]["ack_bridge"]["status"] == "ready"
    assert adapter.sent == []
    assert adapter.edits == []


@pytest.mark.asyncio
async def test_shadow_runtime_publication_hook_failure_is_sanitized_and_invisible(
    monkeypatch,
    tmp_path,
    caplog,
) -> None:
    import gateway.flowweaver_shadow_publisher as publisher

    def raise_with_private_values(*_args: object, **_kwargs: object) -> None:
        raise ValueError(
            "runtime attach exploded "
            + PRIVATE_MESSAGE_ID
            + " "
            + PRIVATE_CHAT_ID
            + " "
            + SECRET_SHAPED
        )

    monkeypatch.setattr(publisher, "attach_flowweaver_shadow_runtime_publication", raise_with_private_values)
    caplog.set_level(logging.DEBUG, logger="gateway.run")

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-runtime-publish-failure",
        config_data=_shadow_config(dry_run=True, publish=True),
    )
    rendered = repr(result).lower()
    logs = caplog.text.lower()

    assert FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY in result
    assert FLOWWEAVER_SHADOW_RUNTIME_PUBLICATION_RESULT_KEY not in result
    assert adapter.sent == []
    assert adapter.edits == []
    assert "flowweaver shadow runtime publication attach failed" in logs
    assert "runtime attach exploded" not in logs
    assert PRIVATE_MESSAGE_ID not in logs
    assert PRIVATE_CHAT_ID not in logs
    assert SECRET_SHAPED not in logs
    assert PRIVATE_MESSAGE_ID not in rendered
    assert PRIVATE_CHAT_ID not in rendered
    assert SECRET_SHAPED not in rendered
