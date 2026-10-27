"""Behavior tests for the strict CI aggregate gate (scripts/ci/required_results.py)."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "required_results.py"
CI = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yaml"

_spec = importlib.util.spec_from_file_location("required_results", SCRIPT)
required_results = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(required_results)

evaluate_gate = required_results.evaluate_gate


import pytest
from ruamel.yaml import YAML


@pytest.mark.parametrize("release", [False, True])
@pytest.mark.parametrize("job", ["tests", "osv-scanner", "history-check", "e2e-desktop", "tests-os"])
@pytest.mark.parametrize("result,ordinary,excluded", [
    ("success", True, True), ("skipped", False, True), ("failure", False, False),
    ("cancelled", False, False), ("with-status", False, False),
    ("action_required", False, False), ("unknown", False, False), (None, False, False),
])
def test_status_policy(job, result, ordinary, excluded, release):
    expected = excluded if job in ("history-check", "e2e-desktop", "tests-os") else ordinary
    if result == "skipped" and not release:
        expected = True
    verdict = evaluate_gate({job: {} if result is None else {"result": result}}, release=release)
    assert verdict == {"ok": expected, "failed": [] if expected else [job],
                       "allowed_skips": [job] if expected and result == "skipped" else []}


@pytest.mark.parametrize("lane,jobs", [
    ("python", ("tests",)),
    ("e2e", ("tests",)),
    ("e2e_upgrade", ("tests",)),
    ("e2e_desktop_update", ("e2e-desktop-update",)),
    ("remote_backends", ("remote-backends",)),
    ("catalog", ("catalog-tests",)),
])
@pytest.mark.parametrize("result", ["skipped", "absent", "success"])
def test_selected_update_consumers_must_succeed(lane, jobs, result):
    needs = {"detect": {"result": "success", "outputs": {lane: "true"}}}
    if result != "absent":
        needs.update({job: {"result": result} for job in jobs})
    verdict = evaluate_gate(needs)
    assert verdict["ok"] is (result == "success")
    assert verdict["failed"] == ([] if result == "success" else sorted(jobs))
    assert verdict["allowed_skips"] == []
    # False string outputs must not arm a job merely because they are truthy.
    needs["detect"]["outputs"][lane] = "false"
    assert evaluate_gate(needs)["ok"]


@pytest.mark.parametrize("release", [False, True])
@pytest.mark.parametrize("lane", ["python", "desktop_updater", "e2e", "e2e_upgrade"])
def test_no_lane_requires_the_forks_non_linux_lanes(lane, release):
    """Fork: tests-os (macOS/Windows) is never dispatched, so the lanes it consumed cannot require it."""
    needs = {"detect": {"result": "success", "outputs": {lane: "true"}}, "tests-os": {"result": "skipped"}}
    if lane != "desktop_updater":  # tests-os was its only consumer
        needs["tests"] = {"result": "success"}
    assert evaluate_gate(needs, release=release) == {"ok": True, "failed": [], "allowed_skips": ["tests-os"]}
    # Excluded is not accepted-when-red: one that somehow ran and failed still fails the gate.
    for result in ("failure", "cancelled"):
        needs["tests-os"] = {"result": result}
        assert evaluate_gate(needs, release=release)["failed"] == ["tests-os"]


def test_release_exclusion_policy():
    assert required_results.EXCLUDED_JOBS == {
        "history-check", "lockfile-diff", "prompt-surface-diff", "supply-chain", "e2e-desktop", "tests-os",
    }
    assert required_results.NON_LINUX_JOBS == ("tests-os",)


def _ci_jobs() -> dict:
    return YAML(typ="base").load(CI.read_text(encoding="utf-8"))["jobs"]


def test_only_jobs_ci_yaml_never_dispatches_are_excused_as_deferred_or_non_linux():
    """The gate's deferred / non-Linux names and ci.yaml's bare ``if: false`` jobs are one set: an
    exclusion cannot excuse a job that runs, and a disabled job cannot hide outside the gate."""
    jobs = _ci_jobs()
    disabled = {name for name, job in jobs.items() if job.get("if") == "false"}
    assert disabled == {*required_results.DEFERRED_JOBS, *required_results.NON_LINUX_JOBS}
    assert disabled <= set(jobs["all-checks-pass"]["needs"])


@pytest.mark.parametrize("release", [False, True])
def test_linux_only_scope_keeps_every_applicable_need_strict(release):
    """The real aggregate, every lane on: the non-Linux skip passes, an applicable need never does
    unless it fails, is cancelled, or (strict) skips outside the PR-only / deferred set."""
    jobs = _ci_jobs()
    names = list(jobs["all-checks-pass"]["needs"])
    lanes = {lane: "true" for lane in jobs["detect"]["outputs"] if lane != "event_name"}
    unrun = {*required_results.NON_LINUX_JOBS, *required_results.DEFERRED_JOBS,
             *(required_results.PR_ONLY_JOBS if release else ())}
    needs = {name: {"result": "skipped" if name in unrun else "success"} for name in names}
    needs["detect"]["outputs"] = lanes
    assert evaluate_gate(needs, release=release) == {"ok": True, "failed": [], "allowed_skips": sorted(unrun)}
    applicable = [name for name in names if name not in unrun]
    assert {"tests", "lint", "js-tests", "bootstrap-installer", "uv-lockfile"} <= set(applicable)
    for name in applicable:
        for result in ("failure", "cancelled"):
            verdict = evaluate_gate({**needs, name: {"result": result}}, release=release)
            assert verdict["failed"] == [name], (name, result)
        skipped = evaluate_gate({**needs, name: {"result": "skipped"}}, release=release)
        # Strict: only the excluded set may skip. PR: a lane-selected consumer may not.
        must_run = release and name not in required_results.EXCLUDED_JOBS
        selected = name in required_results._UPDATE_CONSUMER_LANES
        assert skipped["ok"] is not (must_run or selected), name


@pytest.mark.parametrize("needs", [{}, None])
@pytest.mark.parametrize("release", [False, True])
def test_empty_needs_fails_closed(needs, release):
    assert evaluate_gate(needs, release=release) == {
        "ok": False, "failed": ["<no-needs>"], "allowed_skips": [],
    }
    assert required_results.compact_results(needs) == {}


@pytest.mark.parametrize("release,results,code,report", [
    (True, {"detect": "success", "e2e-desktop": "skipped"}, 0, "All checks passed"),
    (True, {"tests": "skipped", "history-check": "skipped", "lint": "failure"},
     1, "::error::2 job(s) failed: lint, tests"),
    (False, {"tests": "failure"}, 1, "::error::1 job(s) failed: tests"),
])
def test_cli_stdin_exit_codes_and_output(tmp_path, release, results, code, report):
    output = tmp_path / "github-output.txt"
    needs = {name: {"result": result, "outputs": {"detail": "kept"}}
             for name, result in results.items()}
    child = subprocess.run(
        [sys.executable, str(SCRIPT), *(["--release"] if release else [])],
        input=json.dumps(needs), capture_output=True, text=True, timeout=30,
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        check=False,
    )
    assert child.returncode == code, child.stderr
    assert report in child.stdout
    key, value = output.read_text(encoding="utf-8-sig").strip().split("=", 1)
    assert key == "needs-json"
    assert json.loads(value) == results
    assert f"{key}={value}" in child.stdout
    for name, result in results.items():
        assert f"{name}: {result}" in child.stdout
