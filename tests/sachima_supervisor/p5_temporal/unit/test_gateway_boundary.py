"""T7 — static Gateway boundary gate (FR6, Gate F, merge-blocking).

Gateway, inbound-message paths, platform adapters, and Feishu code must not
import, instantiate, start, stop, scale, drain, or hold a handle to the P5
Temporal Worker, Temporal service lifecycle, task-queue admin, or the runtime
package's lifecycle surfaces. This static scan fails the build on any such
reference. The reverse is also asserted: the ops-owned Worker / runtime modules
never import Gateway / Feishu / platform code (one-directional boundary).
"""

from __future__ import annotations

import pathlib
import re

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_GATEWAY_ROOT = _REPO_ROOT / "gateway"
_P5_TEMPORAL_ROOT = _REPO_ROOT / "sachima_supervisor" / "p5_temporal"

#: Forbidden references in any Gateway / inbound / platform / Feishu source file.
#: Precise on the P5 Temporal lifecycle surface so the scan never false-positives
#: on unrelated gateway worker/queue concepts.
_FORBIDDEN_IN_GATEWAY = re.compile(
    r"(p5_temporal_worker"
    r"|build_p5_temporal_worker"
    r"|run_p5_temporal_worker"
    r"|sachima_supervisor\.p5_temporal"
    r"|P5TemporalControlSurface"
    r"|P5TemporalRuntimeClient"
    r"|P5TemporalStepExecutor"
    r"|\bStepWorkflow\b"
    r"|temporalio\.worker"
    r"|WorkflowEnvironment"
    r"|temporal\s+server\s+start-dev)"
)

#: The ops-owned Worker / runtime modules must not reach back into Gateway/Feishu.
_FORBIDDEN_IN_RUNTIME = re.compile(r"(^|[^a-z_])(gateway|feishu|lark|platform_adapter)([^a-z_]|$)", re.IGNORECASE)


def _py_files(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(root.rglob("*.py")) if root.exists() else []


def test_detector_has_teeth():
    # Guard against a vacuously-passing scan: the detector must match a known bad line.
    assert _FORBIDDEN_IN_GATEWAY.search("from sachima_supervisor.p5_temporal import build_p5_temporal_worker")
    assert _FORBIDDEN_IN_GATEWAY.search("worker = build_p5_temporal_worker(client)")


def test_gateway_root_exists():
    assert _GATEWAY_ROOT.exists(), "gateway/ surface must exist to scan the boundary"


def test_gateway_does_not_reference_p5_temporal_lifecycle():
    hits: list[str] = []
    for path in _py_files(_GATEWAY_ROOT):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if _FORBIDDEN_IN_GATEWAY.search(line):
                hits.append(f"{path.relative_to(_REPO_ROOT)}:{number}:{line.strip()}")
    assert not hits, "Gateway/Feishu/platform must not reference P5 Temporal lifecycle:\n" + "\n".join(hits)


def test_p5_temporal_worker_module_exists_and_is_ops_only():
    worker = _P5_TEMPORAL_ROOT / "p5_temporal_worker.py"
    assert worker.exists()
    text = worker.read_text(encoding="utf-8")
    # The ops-owned Worker builder must never import Gateway / Feishu / platform code.
    offending = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith(("import ", "from "))
        and _FORBIDDEN_IN_RUNTIME.search(line)
    ]
    assert not offending, "p5_temporal_worker must not import Gateway/Feishu/platform:\n" + "\n".join(offending)


@pytest.mark.parametrize("module", ["runtime_client.py", "control_surface.py", "workflow.py", "activities.py", "step_executor.py", "contracts.py"])
def test_runtime_modules_do_not_import_gateway_or_feishu(module):
    path = _P5_TEMPORAL_ROOT / module
    text = path.read_text(encoding="utf-8")
    offending = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith(("import ", "from ")) and _FORBIDDEN_IN_RUNTIME.search(line)
    ]
    assert not offending, f"{module} must not import Gateway/Feishu/platform:\n" + "\n".join(offending)
