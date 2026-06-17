"""RED/GREEN tests for the WP4 controlled AI FLOW executor seam (FR5).

Slice 1 ships only the Protocol + dataclass; real runners are a later gate. The
import-isolation test proves the seam never transitively pulls in subprocess /
socket / acpx / npx / a real runner (mirrors the bridge import-safety test).
"""

from __future__ import annotations

import subprocess
import sys

from sachima_supervisor.ai_flow_executor import (
    StepExecutionOutcome,
    StepExecutor,
)


class _FakeStepExecutor:
    """A minimal Protocol-satisfying fake (test-side only)."""

    def execute(self, request, *, role_binding, resolved_inputs) -> StepExecutionOutcome:
        return StepExecutionOutcome(ok=True, step_status="completed", artifact_refs=())


def test_outcome_defaults_are_default_off_and_clean() -> None:
    outcome = StepExecutionOutcome(ok=False, step_status=None, artifact_refs=())
    assert outcome.retryable is False
    assert outcome.interrupted is False
    assert outcome.cleanup_verified is False
    assert outcome.ambiguous is False
    assert outcome.evidence_ref is None
    assert outcome.error_code is None


def test_fake_executor_satisfies_protocol() -> None:
    executor: StepExecutor = _FakeStepExecutor()
    outcome = executor.execute(object(), role_binding=object(), resolved_inputs=())
    assert isinstance(outcome, StepExecutionOutcome)
    assert outcome.ok is True
    assert outcome.step_status == "completed"


def test_module_import_never_pulls_in_forbidden_surfaces() -> None:
    # The existing package transitively loads ``socket`` via stdlib
    # ``importlib.metadata`` (in the pre-existing supervisor_library, which WP4
    # does not touch). We therefore measure the *delta* the ai_flow seam itself
    # introduces, and additionally assert the genuinely-external runner surfaces
    # (agent_run_supervisor / acpx / npx) are never present at all.
    code = (
        "import sys, importlib\n"
        "import sachima_supervisor  # existing package baseline\n"
        "base = set(sys.modules)\n"
        "importlib.import_module('sachima_supervisor.ai_flow_executor')\n"
        "delta = sorted(k for k in sys.modules if k not in base)\n"
        "forbidden = ('subprocess', 'socket', 'asyncio', 'ssl', 'requests', 'httpx', 'urllib.request')\n"
        "leaked = [k for k in delta if k in forbidden or 'acpx' in k or k.startswith('npx')]\n"
        "assert not leaked, leaked\n"
        "runner = sorted(k for k in sys.modules if k.startswith('agent_run_supervisor') or 'acpx' in k)\n"
        "assert not runner, runner\n"
        "import sachima_supervisor.ai_flow_executor as m\n"
        "assert m.StepExecutionOutcome is not None\n"
        "print('import-ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "import-ok" in result.stdout
