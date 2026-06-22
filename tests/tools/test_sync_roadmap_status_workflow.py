from __future__ import annotations

from pathlib import Path

import yaml


WORKFLOW = Path(".github/workflows/roadmap-status-sync.yml")


def test_roadmap_status_sync_workflow_is_bounded_to_machine_block() -> None:
    payload = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    assert payload["permissions"] == {"contents": "write", "pull-requests": "read"}
    job = payload["jobs"]["sync"]
    assert "[skip status-sync]" in job["if"]

    steps_text = "\n".join(str(step) for step in job["steps"])
    assert "tools/sync_roadmap_status.py" in steps_text
    assert "docs/roadmap/current-status.md" in steps_text
    assert "release/sachima" in steps_text
    assert "git push" in steps_text
    assert "docs: sync machine roadmap status [skip status-sync]" in steps_text
