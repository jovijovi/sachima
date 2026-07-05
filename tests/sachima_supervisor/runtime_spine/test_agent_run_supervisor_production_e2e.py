"""PR5 — single-user production-shaped E2E over the agent-run-supervisor spine.

Focused tests for :mod:`agent_run_supervisor_production_e2e`. The E2E runner drives
the *real* PR1 :class:`AgentRunSupervisorPort` (over the deterministic in-memory
``DefaultAgentRunSupervisorBackend``) together with the PR3 persistent lifecycle and
the PR4 workbench view, and proves the required safe semantics refs-only and
fail-closed: one live session / no duplicate ``agent_attached`` across a reconstruct,
an optional deterministic permission-wait + operator-decision path, a renderable
workbench view before cleanup, deterministic kill / orphan-free cleanup / lease
release, a rollback-safe restart with no respawn, and no raw prompt / agent output /
platform id in Sachima state. The report is fail-closed validated, byte-stable, and
no-leak scanned; forged fixtures / reports fail closed and never echo bad material.

Everything here stays pure local/offline Python: no real agent / process / network /
durable service / delivery / listener is started, and no Gateway / Temporal Worker is
touched. Forbidden terms below are no-leak canaries only, never behavior.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from sachima_supervisor.runtime_spine import SpineError, scan_for_leak
from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
    DefaultAgentRunSupervisorBackend,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_production_e2e import (
    E2E_BACKEND_FAILURE,
    E2E_INVALID_FIXTURE,
    E2E_INVALID_REPORT,
    E2E_LEASE_UNAVAILABLE,
    E2E_REPORT_TYPE,
    E2E_STABLE_CODES,
    E2E_UNEXPECTED_LEAK,
    READ_ONLY_ROLE,
    ProductionE2EFixture,
    ProductionE2EReport,
    run_single_user_production_e2e,
    serialize_production_e2e_report,
    validate_production_e2e_fixture,
    validate_production_e2e_report,
)
from sachima_supervisor.runtime_spine.workspace import (
    WorkspaceLeaseStore,
    acquire_workspace_lease,
)

# Marker-shaped raw material the E2E must never leak. Built by concatenation so this
# test module carries no contiguous forbidden literal.
_NONCE = "e2eNonce" + "Zz9" + "Q7"
_RAW_PROMPT = "raw" + "_prompt " + _NONCE
_AGENT_STDOUT = "agent" + "_stdout " + _NONCE
_PLATFORM_ID = "oc" + "_" + "deadbeefcafef00d"
_MARKER_RAW_MATERIAL = (_RAW_PROMPT, _AGENT_STDOUT, _PLATFORM_ID, _NONCE)

_LEAK_CANARIES = (
    "raw_prompt",
    "raw_context",
    "tool_output",
    "agent_stdout",
    "card_json",
    "chat_id",
    "oc_",
    "ou_",
    "/tmp/",
    "/home/",
    "sk" + "-",
    "bearer ",
    "feishu",
)


def _e2e_mod():
    return importlib.import_module(
        "sachima_supervisor.runtime_spine.agent_run_supervisor_production_e2e"
    )


def _marker_fixture(**over) -> ProductionE2EFixture:
    return ProductionE2EFixture(raw_material=_MARKER_RAW_MATERIAL, **over)


def _valid_report_kwargs(**over):
    base = dict(
        status="pass",
        role=READ_ONLY_ROLE,
        task_ref="task_e2e_alpha",
        session_ref="sess_1",
        single_session=True,
        duplicate_attach_suppressed=True,
        attach_event_count=1,
        backend_session_count=1,
        workbench_renderable=True,
        permission_path_included=False,
        operator_decision_applied=False,
        cleanup_terminal=True,
        terminal_state="cancelled",
        orphan_free=True,
        lease_released=True,
        rollback_safe=True,
        no_leak=True,
        event_count=3,
        artifact_refs=["policy_read_only_default", "ref_planning_report", "ws_e2e_alpha"],
        projection_status="cancelled",
        checks={"single_session": "pass"},
        blockers=(),
    )
    base.update(over)
    return base


class _RaisingBackend(DefaultAgentRunSupervisorBackend):
    """Default backend whose ``create_or_attach`` raises with marker-laden text."""

    def create_or_attach(self, task_id, refs):
        raise RuntimeError("boom stderr chat_id oc_secret /tmp/x raw_prompt " + _NONCE)


# --------------------------------------------------------------------------- #
# A. Public surface
# --------------------------------------------------------------------------- #
def test_e2e_public_surface_is_exported() -> None:
    mod = _e2e_mod()
    assert mod.E2E_REPORT_TYPE == (
        "sachima.runtime_spine.agent_run_supervisor_production_e2e_report.v1"
    )
    assert mod.E2E_INVALID_FIXTURE in mod.E2E_STABLE_CODES
    assert mod.E2E_UNEXPECTED_LEAK in mod.E2E_STABLE_CODES
    for name in (
        "ProductionE2EFixture",
        "ProductionE2EReport",
        "run_single_user_production_e2e",
        "validate_production_e2e_fixture",
        "validate_production_e2e_report",
        "serialize_production_e2e_report",
    ):
        assert hasattr(mod, name)


def test_e2e_symbols_available_from_runtime_spine_package() -> None:
    runtime_spine = importlib.import_module("sachima_supervisor.runtime_spine")
    for name in (
        "E2E_REPORT_TYPE",
        "E2E_STABLE_CODES",
        "ProductionE2EFixture",
        "ProductionE2EReport",
        "run_single_user_production_e2e",
        "serialize_production_e2e_report",
    ):
        assert hasattr(runtime_spine, name)


# --------------------------------------------------------------------------- #
# B. Default run passes with the deterministic fake backend and no real runtime
# --------------------------------------------------------------------------- #
def test_default_run_passes_with_all_safety_invariants() -> None:
    report = run_single_user_production_e2e()
    assert report.status == "pass", report.blockers
    assert report.role == READ_ONLY_ROLE
    assert report.task_ref == "task_e2e_alpha"
    assert report.session_ref == "sess_1"
    assert report.single_session is True
    assert report.duplicate_attach_suppressed is True
    assert report.attach_event_count == 1
    assert report.backend_session_count == 1
    assert report.workbench_renderable is True
    assert report.cleanup_terminal is True
    assert report.terminal_state == "cancelled"
    assert report.orphan_free is True
    assert report.lease_released is True
    assert report.rollback_safe is True
    assert report.no_leak is True
    assert report.projection_status == "cancelled"
    assert report.permission_path_included is False
    assert report.operator_decision_applied is False
    assert not report.blockers


def test_default_run_drives_the_real_pr1_backend_once() -> None:
    backend = DefaultAgentRunSupervisorBackend()
    report = run_single_user_production_e2e(backend=backend)
    assert report.status == "pass", report.blockers
    # Exactly one supervisor session on the very backend passed in — a restart
    # re-attached rather than respawning.
    assert backend.session_count() == 1


def test_run_is_deterministic_and_report_is_leak_free() -> None:
    first = run_single_user_production_e2e(fixture=_marker_fixture()).to_projection()
    second = run_single_user_production_e2e(fixture=_marker_fixture()).to_projection()
    assert first == second
    assert first["status"] == "pass"
    assert scan_for_leak(first, canaries=_MARKER_RAW_MATERIAL) is None


# --------------------------------------------------------------------------- #
# C. One session / one agent_attached across reconstruct
# --------------------------------------------------------------------------- #
def test_reconstruct_keeps_one_session_and_one_attach() -> None:
    report = run_single_user_production_e2e()
    assert report.duplicate_attach_suppressed is True
    assert report.attach_event_count == 1
    assert report.backend_session_count == 1
    assert dict(report.checks)["single_session"] == "pass"
    assert dict(report.checks)["duplicate_attach_suppressed"] == "pass"


# --------------------------------------------------------------------------- #
# D. Workbench view renders refs-only fields before cleanup
# --------------------------------------------------------------------------- #
def test_workbench_renderable_before_cleanup_is_proven() -> None:
    report = run_single_user_production_e2e(fixture=_marker_fixture())
    assert report.workbench_renderable is True
    assert dict(report.checks)["workbench_renderable"] == "pass"
    assert scan_for_leak(report.to_projection(), canaries=_MARKER_RAW_MATERIAL) is None


# --------------------------------------------------------------------------- #
# E. Optional permission-wait + operator-decision path
# --------------------------------------------------------------------------- #
def test_permission_wait_and_operator_decision_path() -> None:
    report = run_single_user_production_e2e(
        fixture=ProductionE2EFixture(include_permission_wait=True)
    )
    assert report.status == "pass", report.blockers
    assert report.permission_path_included is True
    assert report.operator_decision_applied is True
    assert dict(report.checks)["permission_wait_surfaced"] == "pass"
    assert dict(report.checks)["operator_decision_applied"] == "pass"
    # The permission path added the two extra refs-only events (request + answer).
    assert report.event_count == 5


def test_permission_path_report_is_leak_free() -> None:
    report = run_single_user_production_e2e(
        fixture=_marker_fixture(include_permission_wait=True)
    )
    assert report.status == "pass", report.blockers
    assert scan_for_leak(report.to_projection(), canaries=_MARKER_RAW_MATERIAL) is None


# --------------------------------------------------------------------------- #
# F. Cleanup / orphan-free / lease / rollback proofs are true
# --------------------------------------------------------------------------- #
def test_cleanup_orphan_free_lease_and_rollback_checks_pass() -> None:
    report = run_single_user_production_e2e()
    for name in (
        "cleanup_terminal",
        "orphan_free",
        "lease_released",
        "rollback_safe",
        "no_raw_material_in_state",
        "artifact_ref_projected",
    ):
        assert dict(report.checks)[name] == "pass", (name, report.blockers)


# --------------------------------------------------------------------------- #
# G. Failure paths return blocked/failed sanitized reports (no echo)
# --------------------------------------------------------------------------- #
def test_raising_backend_yields_failed_report_without_echo() -> None:
    report = run_single_user_production_e2e(backend=_RaisingBackend())
    assert report.status == "failed"
    assert report.session_ref is None
    assert report.blockers == (E2E_BACKEND_FAILURE,)
    assert all(code in E2E_STABLE_CODES for code in report.blockers)
    # The backend's marker-laden failure text is never echoed into the report.
    projection = report.to_projection()
    assert scan_for_leak(projection, canaries=_MARKER_RAW_MATERIAL) is None
    assert scan_for_leak(projection, canaries=("oc_secret", "boom", _NONCE)) is None


def test_lease_conflict_yields_blocked_lease_report() -> None:
    store = WorkspaceLeaseStore()
    # A different holder already owns the single-writer lease for the task.
    acquire_workspace_lease(
        store,
        task_id="task_e2e_alpha",
        holder="ref_other_holder",
        workspace_ref="ws_e2e_alpha",
        now=0,
        ttl=3600,
    )
    report = run_single_user_production_e2e(lease_store=store)
    assert report.status == "failed"
    assert report.blockers == (E2E_LEASE_UNAVAILABLE,)
    assert report.session_ref is None


def test_forged_fixture_into_runner_is_blocked_without_echo() -> None:
    forged = object.__new__(ProductionE2EFixture)
    object.__setattr__(forged, "task_id", "task_e2e_alpha")
    object.__setattr__(forged, "workspace_ref", "ws_chat_id_leak")  # forbidden marker
    object.__setattr__(forged, "policy_ref", "policy_read_only_default")
    object.__setattr__(forged, "artifact_ref", "ref_planning_report")
    object.__setattr__(forged, "holder_ref", "ref_e2e_holder")
    object.__setattr__(forged, "decision_ref", "ref_e2e_decision_allow")
    object.__setattr__(forged, "cleanup_reason_ref", "ref_e2e_cleanup")
    object.__setattr__(forged, "include_permission_wait", False)
    object.__setattr__(forged, "raw_material", ())
    report = run_single_user_production_e2e(fixture=forged)
    assert report.status == "blocked"
    assert report.blockers == (E2E_INVALID_FIXTURE,)
    assert "chat_id" not in str(report.to_projection())


# --------------------------------------------------------------------------- #
# H. Fixture fails closed on unsafe / bad-prefix refs and never echoes material
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("canary", _LEAK_CANARIES)
def test_fixture_rejects_raw_or_platform_refs(canary: str) -> None:
    with pytest.raises(SpineError) as exc:
        ProductionE2EFixture(artifact_ref=f"ref_{canary}_x")
    assert exc.value.code == E2E_INVALID_FIXTURE
    assert canary not in str(exc.value)


def test_fixture_requires_workspace_and_policy_prefixes() -> None:
    with pytest.raises(SpineError) as exc:
        ProductionE2EFixture(workspace_ref="wrong_prefix")
    assert exc.value.code == E2E_INVALID_FIXTURE
    with pytest.raises(SpineError) as exc2:
        ProductionE2EFixture(policy_ref="ws_not_a_policy")
    assert exc2.value.code == E2E_INVALID_FIXTURE


def test_validate_fixture_rejects_forged_object_new() -> None:
    forged = object.__new__(ProductionE2EFixture)
    object.__setattr__(forged, "task_id", "task_e2e_alpha")
    object.__setattr__(forged, "workspace_ref", "ws_e2e_alpha")
    object.__setattr__(forged, "policy_ref", "policy_read_only_default")
    object.__setattr__(forged, "artifact_ref", "ref_planning_report")
    object.__setattr__(forged, "holder_ref", "ref_e2e_holder")
    object.__setattr__(forged, "decision_ref", "ref_e2e_decision_allow")
    object.__setattr__(forged, "cleanup_reason_ref", "ref_e2e_cleanup")
    object.__setattr__(forged, "include_permission_wait", "yes")  # not a bool
    object.__setattr__(forged, "raw_material", ())
    with pytest.raises(SpineError) as exc:
        validate_production_e2e_fixture(forged)
    assert exc.value.code == E2E_INVALID_FIXTURE


# --------------------------------------------------------------------------- #
# I. Report serialization is byte-stable, revalidating, and leak-free
# --------------------------------------------------------------------------- #
def test_serialize_report_is_byte_stable_and_leak_free() -> None:
    report = run_single_user_production_e2e(fixture=_marker_fixture())
    encoded = serialize_production_e2e_report(report)
    assert type(encoded) is bytes
    assert encoded == serialize_production_e2e_report(report)
    assert b"ws_e2e_alpha" in encoded and b"policy_read_only_default" in encoded
    for leak in (b"raw_prompt", b"chat_id", b"agent_stdout", b"/tmp/", _NONCE.encode()):
        assert leak not in encoded


def test_report_as_dict_matches_serialization_and_is_leak_free() -> None:
    report = run_single_user_production_e2e()
    data = report.as_dict()
    assert data["type"] == E2E_REPORT_TYPE
    assert data["schema_version"] == 1
    assert scan_for_leak(data) is None


# --------------------------------------------------------------------------- #
# J. Forged / mutated report fails closed and does not echo bad material
# --------------------------------------------------------------------------- #
def test_direct_report_construction_rejects_raw_refs() -> None:
    with pytest.raises(SpineError) as exc:
        ProductionE2EReport(**_valid_report_kwargs(artifact_refs=["raw_prompt_dump"]))
    assert exc.value.code == E2E_INVALID_REPORT
    assert "raw_prompt" not in str(exc.value)


def test_report_rejects_broken_pass_invariants() -> None:
    for bad in (
        {"status": "pass", "blockers": (E2E_UNEXPECTED_LEAK,)},  # pass with a blocker
        {"status": "pass", "orphan_free": False},                # pass w/ failed safety
        {"status": "pass", "attach_event_count": 2},             # pass w/ 2 attaches
        {"status": "failed", "blockers": ()},                    # non-pass w/ no blocker
        {"operator_decision_applied": True},                     # decision w/o path
        {"no_leak": False},                                      # leak flag w/o blocker
    ):
        with pytest.raises(SpineError) as exc:
            ProductionE2EReport(**_valid_report_kwargs(**bad))
        assert exc.value.code == E2E_INVALID_REPORT


def test_validate_report_rejects_forged_object_new() -> None:
    forged = object.__new__(ProductionE2EReport)
    # Immutable tuple containers so validation reaches the semantic invariant: a
    # ``pass`` whose ``no_leak`` is False is a shape a genuine report never emits.
    for name, value in _valid_report_kwargs(
        status="pass",
        no_leak=False,
        checks=(("single_session", "pass"),),
        artifact_refs=("policy_read_only_default", "ref_planning_report", "ws_e2e_alpha"),
        blockers=(),
    ).items():
        object.__setattr__(forged, name, value)
    object.__setattr__(forged, "type", E2E_REPORT_TYPE)
    object.__setattr__(forged, "schema_version", 1)
    with pytest.raises(SpineError) as exc:
        validate_production_e2e_report(forged)
    assert exc.value.code == E2E_INVALID_REPORT


def test_report_blockers_and_refs_are_immutable_tuples() -> None:
    report = run_single_user_production_e2e()
    assert type(report.blockers) is tuple
    assert type(report.artifact_refs) is tuple
    assert type(report.checks) is tuple
    with pytest.raises((AttributeError, TypeError)):
        report.blockers.append(E2E_UNEXPECTED_LEAK)  # type: ignore[attr-defined]


def test_serialize_revalidates_forged_report_without_echo() -> None:
    forged = object.__new__(ProductionE2EReport)
    for name, value in _valid_report_kwargs(artifact_refs=["chat_id_leak_ref"]).items():
        object.__setattr__(forged, name, value)
    object.__setattr__(forged, "type", E2E_REPORT_TYPE)
    object.__setattr__(forged, "schema_version", 1)
    with pytest.raises(SpineError) as exc:
        serialize_production_e2e_report(forged)
    assert exc.value.code == E2E_INVALID_REPORT
    assert "chat_id" not in str(exc.value)


def test_forged_report_to_projection_is_leak_safe_and_never_raises() -> None:
    forged = object.__new__(ProductionE2EReport)
    for name, value in _valid_report_kwargs(artifact_refs=["chat_id_leak_ref"]).items():
        object.__setattr__(forged, name, value)
    object.__setattr__(forged, "type", E2E_REPORT_TYPE)
    object.__setattr__(forged, "schema_version", 1)
    projection = forged.to_projection()  # never raises
    assert projection["status"] == "failed"
    assert projection["blockers"] == [E2E_UNEXPECTED_LEAK]
    assert scan_for_leak(projection, canaries=("chat_id",)) is None


# --------------------------------------------------------------------------- #
# K. No live ingress/delivery/prod behavior: no new backend session leaks
# --------------------------------------------------------------------------- #
def test_run_makes_no_extra_backend_sessions_or_active_leases() -> None:
    backend = DefaultAgentRunSupervisorBackend()
    store = WorkspaceLeaseStore()
    report = run_single_user_production_e2e(backend=backend, lease_store=store)
    assert report.status == "pass", report.blockers
    assert backend.session_count() == 1        # one session, terminal, not respawned
    assert store.active_count() == 0           # lease deterministically released


# --------------------------------------------------------------------------- #
# L. Static boundary scan — no real runtime / IM / delivery wiring in source
# --------------------------------------------------------------------------- #
_FORBIDDEN_SOURCE_TOKENS = (
    "subprocess",
    "socket",
    ".Popen(",
    "os.system",
    "create_subprocess",
    "import temporalio",
    "acpx",
    " npx",
    "asyncio.create",
    "gateway",
    "feishu",
    "lark",
    "send(",
    "edit_message",
    "im_send",
    "delivery_payload",
)


def test_e2e_source_wires_no_real_runtime_or_delivery_surface() -> None:
    mod = _e2e_mod()
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert [token for token in _FORBIDDEN_SOURCE_TOKENS if token in source] == []
    import_lines = [ln for ln in source.splitlines() if ln.startswith(("import ", "from "))]
    for line in import_lines:
        for root in (
            "subprocess",
            "socket",
            "temporal",
            "gateway",
            "feishu",
            "lark",
            "httpx",
            "requests",
            "urllib",
            "docker",
            "asyncio",
        ):
            assert root not in line, f"forbidden import {root!r}: {line!r}"
