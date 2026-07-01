from __future__ import annotations

from pathlib import Path

import yaml


WORKFLOW = Path(".github/workflows/roadmap-status-sync.yml")


def test_roadmap_status_guard_workflow_is_read_only_and_does_not_push() -> None:
    payload = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    assert payload["name"] == "Roadmap status guard"
    assert payload["permissions"] == {"contents": "read"}
    job = payload["jobs"]["guard"]

    steps_text = "\n".join(str(step) for step in job["steps"])
    assert "tools/sync_roadmap_status.py" in steps_text
    assert "docs/roadmap/current-status.md" in steps_text
    assert "--check" in steps_text
    assert "--write" not in steps_text
    assert "git push" not in steps_text
    assert "git commit" not in steps_text
