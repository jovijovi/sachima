"""P1 offline Socket API v3 contract tests for the arsd adapter boundary.

Covers the ARS 0.7.6 Socket API v3 integration plan P1 slice
(``docs/plans/2026-08-17-ars-0.7.6-socket-api-v3-integration-plan.md``): the
default-off :class:`ArsdSupervisorConfig`, the injected
:class:`ArsdClientFacade` boundary with its lazy short-lived production
facade, stable request identity, exact request construction, the exact
``server_info`` / ``submit`` / ``run_status`` / ``run_events`` /
``run_cancel`` / ``session_status`` / ``session_list`` / ``agent_list``
validators, the admission-product pre-check, and the Sachima-owned stable
error mapping.

Every mirror in the contract module is drift-locked here against the
installed exact-pinned distribution: a mirror and the distribution that
disagree mean the mirror is the bug.

Everything here is hermetic and offline: the only sockets ever touched are
throwaway AF_UNIX fake-socket servers owned by this file. No real daemon, no
Runtime Spine / Gateway wiring, no external AGENT execution.
"""

from __future__ import annotations

import importlib
import re
import sys
import traceback
from pathlib import Path

import pytest

from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    ARSD_STABLE_CODES,
    RUNTIME_ARSD_BUSY,
    RUNTIME_ARSD_DISABLED,
    RUNTIME_ARSD_IDEMPOTENCY_CONFLICT,
    RUNTIME_ARSD_INTERNAL,
    RUNTIME_ARSD_INVALID_REQUEST,
    RUNTIME_ARSD_POLICY_DENIED,
    RUNTIME_ARSD_PROTOCOL_VIOLATION,
    RUNTIME_ARSD_SHUTTING_DOWN,
    RUNTIME_ARSD_SUBMISSION_INDETERMINATE,
    RUNTIME_ARSD_UNAVAILABLE,
    RUNTIME_ARSD_UNKNOWN_TARGET,
    RUNTIME_ARSD_VERSION_MISMATCH,
    RUNTIME_INVALID_ARSD_CONFIG,
    map_arsd_client_error_code,
)
from sachima_supervisor.runtime_spine.events import SpineError


def _assert_stable_code_only(excinfo, code: str) -> None:
    """The raised SpineError carries the stable code only — no raw text and
    no displayed exception chain."""

    err = excinfo.value
    assert err.code == code
    assert err.args == (code,)
    assert err.__cause__ is None
    assert err.__suppress_context__ or err.__context__ is None


def _rendered_chain(excinfo) -> str:
    """Every rendering surface of the raised error, including the formatted
    exception chain — where an unsuppressed ``__context__`` would resurface
    remote text."""

    err = excinfo.value
    return (
        repr(err)
        + str(err)
        + repr(err.args)
        + "".join(traceback.format_exception(err))
    )



# --------------------------------------------------------------------------- #
# Import purity — the contract module must never touch the ARS package or a
# socket at import/collection time.
# --------------------------------------------------------------------------- #
def test_contract_module_import_is_pure() -> None:
    """Importing the module never imports agent_run_supervisor or opens sockets."""

    for name in list(sys.modules):
        if name.startswith("agent_run_supervisor"):
            del sys.modules[name]
    importlib.import_module("sachima_supervisor.runtime_spine.arsd_socket_contract")
    leaked = [
        name for name in sys.modules if name.startswith("agent_run_supervisor")
    ]
    assert leaked == [], (
        "arsd_socket_contract must lazy-import agent_run_supervisor only "
        f"inside facade operations, never at module import: {leaked}"
    )


# --------------------------------------------------------------------------- #
# Stable error mapping (plan §9): closed Sachima-owned codes, no remote text.
# --------------------------------------------------------------------------- #
#: The exact wire→Sachima closed mapping. Every arsd v3 wire code must map to
#: one Sachima-owned stable code; anything off-contract collapses to INTERNAL.
_WIRE_TO_STABLE = {
    "UNSUPPORTED_API_VERSION": RUNTIME_ARSD_VERSION_MISMATCH,
    "UNKNOWN_OP": RUNTIME_ARSD_PROTOCOL_VIOLATION,
    "MALFORMED_FRAME": RUNTIME_ARSD_PROTOCOL_VIOLATION,
    "FRAME_TOO_LARGE": RUNTIME_ARSD_PROTOCOL_VIOLATION,
    "INVALID_REQUEST": RUNTIME_ARSD_INVALID_REQUEST,
    "UNAUTHENTICATED_PEER": RUNTIME_ARSD_POLICY_DENIED,
    "PEER_UID_DENIED": RUNTIME_ARSD_POLICY_DENIED,
    "OWNER_MISMATCH": RUNTIME_ARSD_POLICY_DENIED,
    "IDEMPOTENCY_CONFLICT": RUNTIME_ARSD_IDEMPOTENCY_CONFLICT,
    "SUBMISSION_INDETERMINATE": RUNTIME_ARSD_SUBMISSION_INDETERMINATE,
    "UNKNOWN_RUN": RUNTIME_ARSD_UNKNOWN_TARGET,
    "UNKNOWN_SESSION": RUNTIME_ARSD_UNKNOWN_TARGET,
    "SESSION_BUSY": RUNTIME_ARSD_BUSY,
    "CAPACITY_EXHAUSTED": RUNTIME_ARSD_BUSY,
    "EVENT_BACKLOG_EXCEEDED": RUNTIME_ARSD_BUSY,
    "SHUTTING_DOWN": RUNTIME_ARSD_SHUTTING_DOWN,
    "INTERNAL": RUNTIME_ARSD_INTERNAL,
    "CLIENT": RUNTIME_ARSD_UNAVAILABLE,
}


@pytest.mark.parametrize("wire_code,stable", sorted(_WIRE_TO_STABLE.items()))
def test_every_wire_code_maps_to_a_stable_sachima_code(
    wire_code: str, stable: str
) -> None:
    assert map_arsd_client_error_code(wire_code) == stable
    assert stable in ARSD_STABLE_CODES


def test_wire_mapping_covers_the_installed_client_error_set() -> None:
    """Contract with the real pinned distribution: no wire code is unmapped.

    Imports the real protocol module (test-time only) and asserts our closed
    mapping covers exactly ``ERROR_CODES`` plus the client-local ``CLIENT``
    code — a pin bump that adds/renames wire codes fails here instead of
    collapsing new codes to INTERNAL silently. The anchor moved from the
    retired ``ERROR_CODES_V1`` symbol at 0.7.x (Spec D-9); the 17-code set
    itself is unchanged.
    """

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    assert set(_WIRE_TO_STABLE) == set(protocol.ERROR_CODES) | {"CLIENT"}
    assert len(protocol.ERROR_CODES) == 17


@pytest.mark.parametrize(
    "off_contract",
    [None, 7, True, "", "NOT_A_CODE", "internal", "owner_mismatch", object()],
)
def test_unknown_or_unsafe_wire_codes_collapse_to_internal(off_contract) -> None:
    """Off-contract wire codes fail closed to INTERNAL — never echoed, never raised."""

    assert map_arsd_client_error_code(off_contract) == RUNTIME_ARSD_INTERNAL


def test_stable_code_set_is_closed_and_disjoint_from_wire_codes() -> None:
    """The Sachima set is small, stable, and never leaks raw wire tokens."""

    assert ARSD_STABLE_CODES == frozenset(
        {
            RUNTIME_ARSD_DISABLED,
            RUNTIME_INVALID_ARSD_CONFIG,
            RUNTIME_ARSD_UNAVAILABLE,
            RUNTIME_ARSD_VERSION_MISMATCH,
            RUNTIME_ARSD_PROTOCOL_VIOLATION,
            RUNTIME_ARSD_INVALID_REQUEST,
            RUNTIME_ARSD_POLICY_DENIED,
            RUNTIME_ARSD_UNKNOWN_TARGET,
            RUNTIME_ARSD_IDEMPOTENCY_CONFLICT,
            RUNTIME_ARSD_BUSY,
            RUNTIME_ARSD_SUBMISSION_INDETERMINATE,
            RUNTIME_ARSD_SHUTTING_DOWN,
            RUNTIME_ARSD_INTERNAL,
        }
    )
    for code in ARSD_STABLE_CODES:
        assert code.startswith("runtime_")
        assert code == code.lower()


def test_spine_error_from_mapping_never_carries_remote_text() -> None:
    """A mapped failure surfaces the stable code only — the message IS the code."""

    stable = map_arsd_client_error_code("OWNER_MISMATCH")
    err = SpineError(stable)
    assert str(err) == stable
    assert "OWNER_MISMATCH" not in str(err)


# --------------------------------------------------------------------------- #
# ArsdSupervisorConfig (plan §5.2): default-off, fail-closed, no-leak.
# --------------------------------------------------------------------------- #
SOCKET_CANARY = "/tmp/sachima-canary/arsd-private.sock"
WORKSPACE_CANARY = "/tmp/sachima-canary/private-workspace"
LEDGER_CANARY = "/tmp/sachima-canary/arsd-run-bindings.json"


def _valid_config_kwargs(**overrides):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_SUPERVISOR_CONFIG_TYPE,
    )

    kwargs = {
        "type": ARSD_SUPERVISOR_CONFIG_TYPE,
        "approval_ref": "approval_arsd_p1_offline",
        "owner": "sachima_host",
        "namespace": "sachima_tasks",
        "socket_path": SOCKET_CANARY,
        "binding_ledger_path": LEDGER_CANARY,
        "agent_by_policy_ref": {"policy_reader": "reader-agent"},
        "model_by_policy_ref": {"policy_reader": "claude-sonnet-5"},
        "effort_by_policy_ref": {"policy_reader": "medium"},
        "workspace_by_ref": {"ws_main": WORKSPACE_CANARY},
        "run_limits_by_policy_ref": {
            "policy_reader": {
                "startup_timeout_seconds": 60.0,
                "turn_timeout_seconds": 600.0,
                "cancel_grace_seconds": 10.0,
                "max_stderr_bytes": 262_144,
                "max_event_bytes": 65_536,
                "max_events": 10_000,
            }
        },
        "grant_ref": "grant_reader_v1",
        "grant_hash": "sha256:" + "a" * 64,
        "grant_role_hash": "sha256:" + "b" * 64,
        "grant_capabilities": ("read", "search"),
        "mcp_snapshot_hashes": ("sha256:" + "c" * 64,),
        "credential_refs": ("cred_reader_github",),
        "evidence_policy_hash": "sha256:" + "d" * 64,
        "recovery_policy_hash": "sha256:" + "e" * 64,
    }
    kwargs.update(overrides)
    return kwargs


def _make_config(**overrides):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ArsdSupervisorConfig,
    )

    return ArsdSupervisorConfig(**_valid_config_kwargs(**overrides))


def test_config_defaults_are_off_and_pinned_to_the_reviewed_contract() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_REQUIRED_API_VERSION,
    )
    from sachima_supervisor.supervisor_library import (
        EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
    )

    config = _make_config()
    assert config.enabled is False
    assert config.expected_package_version == EXPECTED_AGENT_RUN_SUPERVISOR_VERSION
    assert config.required_api_version == ARSD_REQUIRED_API_VERSION == 3


def test_enabled_gate_fails_closed_unless_exactly_true() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        RUNTIME_ARSD_DISABLED,
        require_enabled_arsd_supervisor_config,
    )

    disabled = _make_config()
    with pytest.raises(SpineError) as excinfo:
        require_enabled_arsd_supervisor_config(disabled)
    assert excinfo.value.code == RUNTIME_ARSD_DISABLED

    enabled = _make_config(enabled=True)
    assert require_enabled_arsd_supervisor_config(enabled) is enabled


def test_enabled_must_be_exactly_bool_true_not_truthy() -> None:
    with pytest.raises(SpineError) as excinfo:
        _make_config(enabled=1)
    assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "sachima.runtime_spine.other_config.v1"},
        {"type": 7},
        {"approval_ref": "not_prefixed"},
        {"approval_ref": "approval_"},
        {"approval_ref": ""},
        {"owner": ""},
        {"owner": "Bad-Owner"},
        {"namespace": None},
        {"socket_path": ""},
        {"socket_path": "relative/path.sock"},
        {"socket_path": 7},
        {"binding_ledger_path": ""},
        {"binding_ledger_path": "relative/ledger.json"},
        {"binding_ledger_path": 7},
        {"binding_ledger_path": None},
        {"agent_by_policy_ref": {}},
        {"agent_by_policy_ref": {"reader": "reader-agent"}},
        {"agent_by_policy_ref": {"policy_reader": ""}},
        {"agent_by_policy_ref": {"policy_reader": "bad agent id"}},
        {"model_by_policy_ref": {}},
        {"model_by_policy_ref": {"policy_reader": 7}},
        {"effort_by_policy_ref": {}},
        {"workspace_by_ref": {}},
        {"workspace_by_ref": {"main": WORKSPACE_CANARY}},
        {"workspace_by_ref": {"ws_main": "relative/dir"}},
        {"run_limits_by_policy_ref": {}},
        {"run_limits_by_policy_ref": {"policy_reader": {}}},
        {"run_limits_by_policy_ref": {"policy_reader": {"unknown_limit": 1}}},
        {"grant_ref": ""},
        {"grant_hash": "not-a-digest"},
        {"grant_role_hash": "sha256:" + "z" * 64},
        {"grant_capabilities": ("read", "move")},
        {"grant_capabilities": ("read", "deliver")},
        {"mcp_snapshot_hashes": ("plain",)},
        {"credential_refs": ("cred_ok", 7)},
        {"evidence_policy_hash": ""},
        {"recovery_policy_hash": None},
        {"expected_package_version": "0.1.7"},
        {"expected_package_version": "0.6.3"},
        {"expected_package_version": "9.9.9"},
        {"required_api_version": 1},
        {"required_api_version": 2},
        {"required_api_version": True},
    ],
)
def test_invalid_config_material_fails_closed_with_the_stable_code(
    overrides: dict,
) -> None:
    with pytest.raises(SpineError) as excinfo:
        _make_config(**overrides)
    assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG


@pytest.mark.parametrize(
    "huge_seconds", [10**10000, -(10**10000)], ids=["huge_positive", "huge_negative"]
)
def test_config_run_limit_overflow_fails_closed_with_the_stable_code(
    huge_seconds,
) -> None:
    """A float-overflowing seconds limit is invalid config — never a raw
    OverflowError."""

    limits = dict(_valid_config_kwargs()["run_limits_by_policy_ref"]["policy_reader"])
    limits["startup_timeout_seconds"] = huge_seconds
    with pytest.raises(SpineError) as excinfo:
        _make_config(run_limits_by_policy_ref={"policy_reader": limits})
    _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_CONFIG)


def test_config_repr_and_str_never_leak_private_values() -> None:
    config = _make_config()
    for rendering in (repr(config), str(config)):
        assert SOCKET_CANARY not in rendering
        assert WORKSPACE_CANARY not in rendering
        assert LEDGER_CANARY not in rendering
        assert "sachima-canary" not in rendering


def test_binding_ledger_path_is_private_and_outside_the_tracked_repo() -> None:
    """P1-f: the durable binding ledger P2 will consume is a private host path.

    It is carried like ``socket_path`` — validated by the one shared private
    path boundary, absent from every rendering surface, and refused when it
    would bind inside the tracked worktree.
    """

    from pathlib import Path

    config = _make_config()
    assert config.binding_ledger_path == LEDGER_CANARY

    repo_root = Path(
        __import__(
            "sachima_supervisor.runtime_spine.arsd_socket_contract",
            fromlist=["_REPO_ROOT"],
        )._REPO_ROOT
    )
    with pytest.raises(SpineError) as excinfo:
        _make_config(binding_ledger_path=str(repo_root / "arsd-bindings.json"))
    _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_CONFIG)


def test_config_has_no_serialize_surface() -> None:
    config = _make_config()
    for attr in ("as_dict", "to_dict", "serialize", "to_json", "dict"):
        assert not hasattr(config, attr)


def test_config_maps_are_owned_immutable_copies() -> None:
    """Caller-side mutation after construction can never drift the config."""

    agents = {"policy_reader": "reader-agent"}
    workspaces = {"ws_main": WORKSPACE_CANARY}
    config = _make_config(
        agent_by_policy_ref=agents, workspace_by_ref=workspaces
    )

    agents["policy_reader"] = "hostile-agent"
    agents["policy_new"] = "injected"
    workspaces["ws_main"] = "/tmp/hostile"

    assert dict(config.agent_by_policy_ref) == {"policy_reader": "reader-agent"}
    assert dict(config.workspace_by_ref) == {"ws_main": WORKSPACE_CANARY}
    with pytest.raises(TypeError):
        config.agent_by_policy_ref["policy_reader"] = "x"
    with pytest.raises(TypeError):
        config.workspace_by_ref["ws_main"] = "/x"


def test_run_limits_mirror_matches_the_installed_distribution() -> None:
    """Drift-lock: our closed RunLimits key mirror equals the real 0.7.6 spec."""

    import dataclasses

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        _INT_RUN_LIMIT_KEYS,
        _RUN_LIMIT_KEYS,
    )

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")
    real_fields = {field.name for field in dataclasses.fields(spec.RunLimits)}
    assert _RUN_LIMIT_KEYS == frozenset(real_fields)
    assert _INT_RUN_LIMIT_KEYS <= _RUN_LIMIT_KEYS


# --------------------------------------------------------------------------- #
# Grant capability allowlist: the AUTHOR vocabulary the deployed 0.7.6 role
# actually needs — ``read``/``search`` to observe and ``write``/``execute`` to
# author. One closed local allowlist, drift-locked against the entire pinned
# permission domain; every other pinned kind, and everything outside the
# domain, still fails closed.
# --------------------------------------------------------------------------- #
#: The exact capability vocabulary the configured author role requires. The
#: obsolete read/search-only projection could not express it, so a configured
#: author grant failed closed at construction and no delegated Run could
#: ever be admitted.
AUTHOR_GRANT_CAPABILITIES = frozenset({"read", "search", "write", "execute"})


@pytest.mark.parametrize(
    "capabilities",
    [
        ("delete",),
        ("terminal",),
        ("move",),
        ("fetch",),
        ("switch_mode",),
        ("other",),
        ("read", "delete"),
        ("write", "move"),
        # Outside the pinned permission domain entirely.
        ("deliver",),
        ("read", "bogus_capability"),
    ],
)
def test_capabilities_outside_the_author_vocabulary_fail_closed(capabilities) -> None:
    """A capability the configured role does not require is invalid config —
    even where the pinned wire protocol itself would accept it. Widening to the
    author vocabulary is not a licence to carry every pinned kind."""

    with pytest.raises(SpineError) as excinfo:
        _make_config(grant_capabilities=capabilities)
    _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_CONFIG)


def test_grant_capability_allowlist_drift_locks_the_pinned_permission_domain() -> None:
    """B-7: one closed allowlist, checked against every pinned permission kind.

    Imports the real 0.7.6 permission domain — ``native_acp.spec``, since the
    retired ``agent_run_supervisor.role`` anchor no longer exists (Spec D-10) —
    and asserts: the local allowlist is exactly the author vocabulary and stays
    inside the pinned domain, each allowlisted kind is admitted end-to-end
    (config plus the real ``parse_submit``), and every other pinned kind fails
    closed.
    """

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")
    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        _GRANTABLE_CAPABILITIES,
    )

    assert _GRANTABLE_CAPABILITIES == AUTHOR_GRANT_CAPABILITIES
    assert _GRANTABLE_CAPABILITIES < set(spec.PERMISSION_KINDS)
    # The kinds the author role does not need stay closed even though the
    # deployed daemon would admit them.
    assert {"delete", "move", "terminal"} & set(spec.PERMISSION_KINDS)
    assert not {"delete", "move", "terminal"} & _GRANTABLE_CAPABILITIES

    for kind in spec.PERMISSION_KINDS:
        if kind in _GRANTABLE_CAPABILITIES:
            config = _make_config(enabled=True, grant_capabilities=(kind,))
            assert config.grant_capabilities == (kind,)
            command = protocol.parse_submit(_build_payload(config=config))
            assert command.request.grant_capabilities == (kind,)
        else:
            with pytest.raises(SpineError) as excinfo:
                _make_config(grant_capabilities=(kind,))
            assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG


@pytest.mark.parametrize("unknown_kind", ["edit", "deliver", "approve", "mutate"])
def test_capabilities_outside_the_pinned_domain_fail_closed(unknown_kind) -> None:
    """A capability the deployed daemon has no vocabulary for fails closed at
    construction, before any socket call. ``edit`` is the trap: it is a real
    ACP *tool-call kind* upstream but never a *grant capability*, so admitting
    it would send the daemon a request it would refuse."""

    with pytest.raises(SpineError) as excinfo:
        _make_config(grant_capabilities=("read", unknown_kind))
    _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_CONFIG)


def test_author_grant_is_accepted_and_parses_under_the_pinned_protocol() -> None:
    """The configured author grant builds a payload the real 0.7.6 wire
    validator accepts unchanged — the whole point of the widening."""

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    capabilities = ("execute", "read", "search", "write")
    config = _make_config(enabled=True, grant_capabilities=capabilities)
    command = protocol.parse_submit(_build_payload(config=config))
    assert command.request.grant_capabilities == capabilities


def test_read_search_grant_is_accepted_and_parses_under_the_pinned_protocol() -> None:
    """Positive control: the narrower read/search grant still parses, so the
    widening never became a requirement to grant more."""

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    config = _make_config(enabled=True, grant_capabilities=("read", "search"))
    command = protocol.parse_submit(_build_payload(config=config))
    assert command.request.grant_capabilities == ("read", "search")


# --------------------------------------------------------------------------- #
# RunLimits bounds mirror (formal review blocker 2): every per-field min/max
# and the structural event budget of the installed 0.7.6 spec, enforced locally.
# --------------------------------------------------------------------------- #
def _limits_with(**overrides):
    limits = dict(_valid_config_kwargs()["run_limits_by_policy_ref"]["policy_reader"])
    limits.update(overrides)
    return limits


def test_run_limit_bounds_mirror_the_pinned_spec_constants() -> None:
    """B-11 drift-lock: the local per-field ceilings/floors equal the real
    0.7.6 spec constants exactly — no arbitrary local limits.

    The two values 0.7.2 moved (Δ-1, Δ-2) are asserted by name below; this
    lock is what makes the mirror follow the distribution rather than a
    number written in by hand.
    """

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        _INT_RUN_LIMIT_KEYS,
        _RUN_LIMIT_KEYS,
        _RUN_LIMIT_MAX,
        _RUN_LIMIT_MIN,
    )

    assert dict(_RUN_LIMIT_MAX) == {
        "startup_timeout_seconds": spec.LIMIT_STARTUP_TIMEOUT_SECONDS_MAX,
        "turn_timeout_seconds": spec.LIMIT_TURN_TIMEOUT_SECONDS_MAX,
        "cancel_grace_seconds": spec.LIMIT_CANCEL_GRACE_SECONDS_MAX,
        "max_stderr_bytes": spec.LIMIT_MAX_STDERR_BYTES_MAX,
        "max_event_bytes": spec.LIMIT_MAX_EVENT_BYTES_MAX,
        "max_events": spec.LIMIT_MAX_EVENTS_MAX,
    }
    assert set(_RUN_LIMIT_MAX) == set(_RUN_LIMIT_KEYS)
    assert set(_RUN_LIMIT_MIN) == set(_INT_RUN_LIMIT_KEYS)
    assert _RUN_LIMIT_MIN["max_event_bytes"] == spec.LIMIT_MAX_EVENT_BYTES_MIN
    # The two integer floors the spec keeps unnamed (minimum=1) are
    # behaviour-locked against the real RunLimits dataclass.
    for key in ("max_stderr_bytes", "max_events"):
        assert _RUN_LIMIT_MIN[key] == 1
        spec.RunLimits(**_limits_with(**{key: 1}))
        with pytest.raises(spec.SpecValidationError):
            spec.RunLimits(**_limits_with(**{key: 0}))


def test_run_limit_defaults_and_maxima_are_the_exact_installed_0_7_6_values() -> None:
    """B-11 / Δ-1 – Δ-3: the two values 0.7.2 moved, and the two pairs it did
    not, asserted against the installed distribution rather than written in.

    ``turn_timeout_seconds`` default ``21600.0`` (6 h) and the inclusive
    ``LIMIT_TURN_TIMEOUT_SECONDS_MAX`` ``604800.0`` (7 d) are read off the real
    module first, so this fails if the distribution ever disagrees with the
    numbers the Spec calibrated against. The startup-timeout and cancel-grace
    default/max pairs are asserted at their unchanged 0.7.1 values so a later
    silent move is caught rather than absorbed.
    """

    import dataclasses

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        _RUN_LIMIT_DEFAULTS,
        _RUN_LIMIT_MAX,
    )

    real_defaults = {
        field.name: field.default for field in dataclasses.fields(spec.RunLimits)
    }
    assert dict(_RUN_LIMIT_DEFAULTS) == real_defaults

    # Δ-1 / Δ-2 — the calibrated move, exact and inclusive.
    assert real_defaults["turn_timeout_seconds"] == 21_600.0
    assert spec.LIMIT_TURN_TIMEOUT_SECONDS_MAX == 604_800.0
    assert _RUN_LIMIT_DEFAULTS["turn_timeout_seconds"] == 21_600.0
    assert _RUN_LIMIT_MAX["turn_timeout_seconds"] == 604_800.0
    # Inclusive: the maximum itself is admissible, Sachima-side and upstream.
    _make_config(run_limits_by_policy_ref={"policy_reader": _limits_with(
        turn_timeout_seconds=604_800.0
    )})
    spec.RunLimits(**_limits_with(turn_timeout_seconds=604_800.0))

    # Δ-3 — recorded as unchanged so the timeout move is not over-read.
    assert real_defaults["startup_timeout_seconds"] == 60.0
    assert spec.LIMIT_STARTUP_TIMEOUT_SECONDS_MAX == 3_600.0
    assert real_defaults["cancel_grace_seconds"] == 10.0
    assert spec.LIMIT_CANCEL_GRACE_SECONDS_MAX == 300.0


def test_no_sachima_invented_number_lives_in_the_run_limit_mirror_set() -> None:
    """B-11's second half: every mirrored limit number is the distribution's.

    Each value in ``_RUN_LIMIT_MAX`` / ``_RUN_LIMIT_DEFAULTS`` must be present
    in the set of real spec values; a number Sachima chose for itself would not
    appear there and fails here.
    """

    import dataclasses

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES,
        _RUN_LIMIT_DEFAULTS,
        _RUN_LIMIT_MAX,
        _RUN_LIMIT_MIN,
    )

    real_values = {
        spec.LIMIT_STARTUP_TIMEOUT_SECONDS_MAX,
        spec.LIMIT_TURN_TIMEOUT_SECONDS_MAX,
        spec.LIMIT_CANCEL_GRACE_SECONDS_MAX,
        spec.LIMIT_MAX_STDERR_BYTES_MAX,
        spec.LIMIT_MAX_EVENT_BYTES_MAX,
        spec.LIMIT_MAX_EVENTS_MAX,
        spec.LIMIT_MAX_EVENT_BYTES_MIN,
        spec.STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES,
        1,  # the spec's unnamed integer floor (``minimum=1``)
    }
    real_values |= {
        field.default for field in dataclasses.fields(spec.RunLimits)
    }
    mirrored = (
        set(_RUN_LIMIT_MAX.values())
        | set(_RUN_LIMIT_MIN.values())
        | set(_RUN_LIMIT_DEFAULTS.values())
        | {ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES}
    )
    assert mirrored <= real_values


@pytest.mark.parametrize(
    "limit_field,value",
    [
        ("startup_timeout_seconds", 3601),
        ("startup_timeout_seconds", 3600.5),
        ("turn_timeout_seconds", 604_801),
        ("turn_timeout_seconds", 604_800.5),
        ("cancel_grace_seconds", 300.5),
        ("max_stderr_bytes", 67_108_865),
        ("max_event_bytes", 1_048_577),
        ("max_event_bytes", 255),
        ("max_events", 1_000_001),
    ],
)
def test_run_limits_above_the_mirrored_maximum_fail_closed_at_config_construction(
    limit_field, value
) -> None:
    """A limits policy the installed 0.7.6 daemon would refuse as
    INVALID_REQUEST is never admitted config — the reviewed repro is
    ``startup_timeout_seconds=3601``. The identical mapping on the wire is
    the oracle: the real ``parse_submit`` refuses it too."""

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")

    with pytest.raises(SpineError) as excinfo:
        _make_config(
            run_limits_by_policy_ref={
                "policy_reader": _limits_with(**{limit_field: value})
            }
        )
    _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_CONFIG)

    payload = _build_payload(config=_make_config(enabled=True))
    payload["request"]["limits"][limit_field] = value
    with pytest.raises(protocol.ProtocolError) as protocol_excinfo:
        protocol.parse_submit(payload)
    assert protocol_excinfo.value.code == protocol.INVALID_REQUEST


def test_run_limit_exact_boundaries_are_accepted_like_the_pinned_spec() -> None:
    """Positive control: exact per-field ceilings and floors are admitted
    locally and parse under the real pinned protocol."""

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    for limits in (
        {
            "startup_timeout_seconds": 3600.0,
            "turn_timeout_seconds": 604_800.0,
            "cancel_grace_seconds": 300.0,
            "max_stderr_bytes": 67_108_864,
            "max_event_bytes": 1_048_576,
            "max_events": 1024,
        },
        _limits_with(max_event_bytes=256, max_events=1),
        _limits_with(max_event_bytes=1024, max_events=1_000_000),
    ):
        config = _make_config(
            enabled=True, run_limits_by_policy_ref={"policy_reader": limits}
        )
        command = protocol.parse_submit(_build_payload(config=config))
        assert command.request.limits.max_events == limits["max_events"]


def test_structural_event_budget_is_mirrored_as_a_maximum_not_a_default() -> None:
    """B-12 / Δ-11: ``STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES`` is the product of
    the two per-field maxima, mirrored as a **maximum**.

    Asserted against the real module, and proven to behave as a maximum: the
    full per-field ceiling set — whose product *is* the structural maximum —
    is admissible under the real structural policy and as Sachima config. The
    4 GiB deployment default (Δ-9) is deliberately not equality-asserted
    anywhere; it is a daemon configuration value, and this test pins that no
    Sachima mirror carries it.
    """

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES,
        _RUN_LIMIT_MAX,
    )

    assert (
        ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES
        == spec.STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES
        == spec.LIMIT_MAX_EVENT_BYTES_MAX * spec.LIMIT_MAX_EVENTS_MAX
    )

    ceiling = _limits_with(
        max_event_bytes=_RUN_LIMIT_MAX["max_event_bytes"],
        max_events=_RUN_LIMIT_MAX["max_events"],
    )
    assert (
        ceiling["max_event_bytes"] * ceiling["max_events"]
        == ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES
    )
    # A maximum is inclusive: the structural policy admits the product itself.
    spec.RunLimits(**ceiling, event_budget_policy=spec.STRUCTURAL_EVENT_BUDGET_POLICY)
    _make_config(enabled=True, run_limits_by_policy_ref={"policy_reader": ceiling})

    # No mirror is the 4 GiB deployment default (Δ-9 / Spec §5.3.1).
    four_gib = 4 * 1024 * 1024 * 1024
    assert ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES != four_gib
    assert four_gib not in set(_RUN_LIMIT_MAX.values())


def test_boundary_validator_rejects_forgeries_and_returns_config_unchanged() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ArsdSupervisorConfig,
        validate_arsd_supervisor_config,
    )

    config = _make_config()
    assert validate_arsd_supervisor_config(config) is config

    forged = object.__new__(ArsdSupervisorConfig)
    with pytest.raises(SpineError) as excinfo:
        validate_arsd_supervisor_config(forged)
    assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG

    class Hostile(ArsdSupervisorConfig):
        pass

    hostile = object.__new__(Hostile)
    with pytest.raises(SpineError) as excinfo:
        validate_arsd_supervisor_config(hostile)
    assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG

    with pytest.raises(SpineError) as excinfo:
        validate_arsd_supervisor_config({"enabled": True})
    assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG


# --------------------------------------------------------------------------- #
# Stable request identity (plan §6.1): admitted dispatch identity, no clocks.
# --------------------------------------------------------------------------- #
PROMPT_CANARY = "RAW-PROMPT-CANARY do the private thing at /tmp/sachima-canary"


def test_request_id_is_deterministic_and_wire_safe() -> None:
    import re as _re

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        derive_arsd_request_id,
    )

    first = derive_arsd_request_id("task_alpha", "sess_alpha", "dispatch_0001")
    second = derive_arsd_request_id("task_alpha", "sess_alpha", "dispatch_0001")
    assert first == second
    assert first.startswith("sachima-")
    assert _re.fullmatch(r"[A-Za-z0-9._-]{1,128}", first)


def test_request_id_changes_with_any_identity_component() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        derive_arsd_request_id,
    )

    base = derive_arsd_request_id("task_alpha", "sess_alpha", "dispatch_0001")
    assert derive_arsd_request_id("task_beta", "sess_alpha", "dispatch_0001") != base
    assert derive_arsd_request_id("task_alpha", "sess_beta", "dispatch_0001") != base
    assert derive_arsd_request_id("task_alpha", "sess_alpha", "dispatch_0002") != base


def test_request_id_resists_component_boundary_shifts() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        derive_arsd_request_id,
    )

    assert derive_arsd_request_id("task_a", "b_sess", "dispatch_1") != (
        derive_arsd_request_id("task_a_b", "sess", "dispatch_1")
    )


@pytest.mark.parametrize(
    "task_id,session_id,dispatch_ref",
    [
        ("", "sess_a", "dispatch_1"),
        ("Task-A", "sess_a", "dispatch_1"),
        ("task_a", None, "dispatch_1"),
        ("task_a", "sess_a", "raw prompt text"),
        ("task_a", "sess_a", 7),
    ],
)
def test_request_id_rejects_unsafe_identity_components(
    task_id, session_id, dispatch_ref
) -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        derive_arsd_request_id,
    )

    with pytest.raises(SpineError) as excinfo:
        derive_arsd_request_id(task_id, session_id, dispatch_ref)
    assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST


# --------------------------------------------------------------------------- #
# Submit request construction (plan §6.2): exact wire shape, refs resolved
# through the closed config maps only.
# --------------------------------------------------------------------------- #
#: Sentinel for "this request key is structurally absent" in diff comparisons.
_ABSENT = object()


def _build_payload(config=None, **overrides):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        build_arsd_submit_payload,
    )

    if config is None:
        config = _make_config(enabled=True)
    kwargs = {
        "agent_policy_ref": "policy_reader",
        "model_policy_ref": "policy_reader",
        "effort_policy_ref": "policy_reader",
        "workspace_ref": "ws_main",
        "run_limits_policy_ref": "policy_reader",
        "prompt_text": PROMPT_CANARY,
    }
    kwargs.update(overrides)
    return build_arsd_submit_payload(config, **kwargs)


def test_submit_payload_has_the_exact_v3_wire_shape() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_SPEC_SCHEMA_VERSION,
    )

    payload = _build_payload()
    assert set(payload) == {
        "request",
        "prompt_text",
        "workspace_root",
        "cwd",
        "retry_of_run_id",
    }
    assert payload["prompt_text"] == PROMPT_CANARY
    assert payload["workspace_root"] == WORKSPACE_CANARY
    assert payload["cwd"] is None
    assert payload["retry_of_run_id"] is None

    request = payload["request"]
    assert request["owner"] == "sachima_host"
    assert request["namespace"] == "sachima_tasks"
    assert request["agent_id"] == "reader-agent"
    # Schema 3 retired the reuse mode entirely: the whole Session decision is
    # the presence of ``session_id`` (Spec D-7 / §6.2).
    assert "session_reuse" not in request
    assert "ars_session_id" not in request
    assert "session_id" not in request
    assert request["expected_binding_hash"] is None
    assert request["input_refs"] == []
    assert request["requested_model"] == "claude-sonnet-5"
    assert request["requested_effort"] == "medium"
    assert request["grant_ref"] == "grant_reader_v1"
    assert request["grant_hash"] == "sha256:" + "a" * 64
    assert request["grant_role_hash"] == "sha256:" + "b" * 64
    assert request["grant_capabilities"] == ["read", "search"]
    assert request["mcp_snapshot_hashes"] == ["sha256:" + "c" * 64]
    assert request["credential_refs"] == ["cred_reader_github"]
    assert request["limits"] == {
        "startup_timeout_seconds": 60.0,
        "turn_timeout_seconds": 600.0,
        "cancel_grace_seconds": 10.0,
        "max_stderr_bytes": 262_144,
        "max_event_bytes": 65_536,
        "max_events": 10_000,
    }
    assert request["evidence_policy_hash"] == "sha256:" + "d" * 64
    assert request["recovery_policy_hash"] == "sha256:" + "e" * 64
    assert request["schema_version"] == ARSD_SPEC_SCHEMA_VERSION == 3


def test_submit_payload_parses_under_the_real_pinned_protocol() -> None:
    """The built payload must satisfy the installed 0.7.6 ``parse_submit``.

    This is the exact-contract lock: Sachima's builder output round-trips
    through the real wire validator (test-time import only) so a field-name or
    shape drift fails here, not against a live daemon.
    """

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    payload = _build_payload()
    command = protocol.parse_submit(payload)
    assert command.request.owner == "sachima_host"
    assert command.request.schema_version == 3
    assert command.request.session_id is None
    assert command.prompt_text == PROMPT_CANARY


# --------------------------------------------------------------------------- #
# Session create vs. reuse (Spec §6.2 / A-5 / A-6): the whole Session decision
# is the *presence* of ``request.session_id``. Absent creates; present-valid
# reuses; present-null is INVALID_REQUEST and must never leave Sachima.
# --------------------------------------------------------------------------- #
REUSE_SESSION_ID = "sess-4f2a9c11b7d3"


def test_submit_payload_omits_the_session_key_entirely_on_create() -> None:
    """A-5: create says "I have no Session" by omitting the key.

    The real wire parser is the oracle for what an omitted key means, and the
    same request dict carrying an explicit ``None`` is refused by it — which
    is exactly why the builder may never produce one.
    """

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")

    payload = _build_payload()
    assert "session_id" not in payload["request"]
    assert protocol.parse_submit(payload).request.session_id is None

    # The oracle: present-null is a wire violation, not a tolerated create.
    present_null = _build_payload()
    present_null["request"]["session_id"] = None
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.parse_submit(present_null)
    assert excinfo.value.code == protocol.INVALID_REQUEST


def test_submit_payload_carries_a_valid_session_id_verbatim_on_reuse() -> None:
    """A-6: a valid id is carried through unchanged and parses upstream."""

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")

    payload = _build_payload(session_id=REUSE_SESSION_ID)
    assert payload["request"]["session_id"] == REUSE_SESSION_ID
    assert protocol.parse_submit(payload).request.session_id == REUSE_SESSION_ID

    # Reuse changes exactly one key relative to create — nothing else moves.
    create = _build_payload()
    differing = {
        key
        for key in set(create["request"]) | set(payload["request"])
        if create["request"].get(key, _ABSENT) != payload["request"].get(key, _ABSENT)
    }
    assert differing == {"session_id"}


def test_submit_payload_explicit_null_session_id_fails_closed() -> None:
    """A-5: a Sachima id lookup that returned ``None`` must not silently start
    a second conversation. Passing ``None`` explicitly is a fail-closed
    invalid request, and creating requires omitting the argument."""

    with pytest.raises(SpineError) as excinfo:
        _build_payload(session_id=None)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)


@pytest.mark.parametrize(
    "bad_session_id",
    [
        "sess.4f2a9c11",
        "run4abc.ephemeral",
        "_leading_underscore",
        "-leading-dash",
        "has space",
        "has/slash",
        "..",
        "",
        7,
        True,
        [],
        {},
    ],
)
def test_submit_payload_off_grammar_session_id_fails_closed_without_a_socket_call(
    bad_session_id,
) -> None:
    """A-6: an id violating ``[A-Za-z0-9][A-Za-z0-9_\\-]*`` — a dotted one
    included, which the retired wire-token grammar would have accepted — fails
    closed Sachima-side. The builder is pure, so no socket call is reachable
    from here at all."""

    with pytest.raises(SpineError) as excinfo:
        _build_payload(session_id=bad_session_id)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)


def test_submit_payload_rejects_unknown_refs_fail_closed() -> None:
    for overrides in (
        {"agent_policy_ref": "policy_missing"},
        {"model_policy_ref": "policy_missing"},
        {"effort_policy_ref": "policy_missing"},
        {"workspace_ref": "ws_missing"},
        {"run_limits_policy_ref": "policy_missing"},
        {"agent_policy_ref": "ws_main"},
    ):
        with pytest.raises(SpineError) as excinfo:
            _build_payload(**overrides)
        assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST


def test_submit_payload_requires_an_enabled_config() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        RUNTIME_ARSD_DISABLED,
    )

    with pytest.raises(SpineError) as excinfo:
        _build_payload(config=_make_config())
    assert excinfo.value.code == RUNTIME_ARSD_DISABLED


def test_submit_payload_prompt_byte_bound_matches_the_pinned_protocol() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_MAX_PROMPT_BYTES,
    )

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    assert ARSD_MAX_PROMPT_BYTES == protocol.MAX_PROMPT_BYTES

    at_bound = "€" * (ARSD_MAX_PROMPT_BYTES // 3)
    payload = _build_payload(prompt_text=at_bound)
    assert payload["prompt_text"] == at_bound

    over_bound = "€" * (ARSD_MAX_PROMPT_BYTES // 3) + "xx"
    with pytest.raises(SpineError) as excinfo:
        _build_payload(prompt_text=over_bound)
    assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST

    for bad_prompt in ("", None, 7):
        with pytest.raises(SpineError) as excinfo:
            _build_payload(prompt_text=bad_prompt)
        assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST


@pytest.mark.parametrize("bad_prompt", ["\ud800", "ok\udfff tail"])
def test_submit_payload_unencodable_prompt_is_invalid_request_not_a_crash(
    bad_prompt,
) -> None:
    """A lone-surrogate prompt fails closed — never a raw UnicodeEncodeError."""

    with pytest.raises(SpineError) as excinfo:
        _build_payload(prompt_text=bad_prompt)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)
    rendering = repr(excinfo.value) + str(excinfo.value) + repr(excinfo.value.args)
    assert "surrogate" not in rendering.lower()
    assert "\ud800" not in rendering and "\udfff" not in rendering


def test_submit_payload_input_refs_are_claim_checks_only() -> None:
    payload = _build_payload(
        input_refs=(("blob_input_one", "sha256:" + "1" * 64),)
    )
    assert payload["request"]["input_refs"] == [
        {"ref": "blob_input_one", "content_hash": "sha256:" + "1" * 64}
    ]

    for bad_refs in (
        (("blob_input_one",),),
        (("blob_input_one", "not-a-digest"),),
        (("bad ref!", "sha256:" + "1" * 64),),
        ("blob_input_one",),
    ):
        with pytest.raises(SpineError) as excinfo:
            _build_payload(input_refs=bad_refs)
        assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST


def test_submit_payload_is_byte_equivalent_across_rebuilds() -> None:
    """A retry of an uncertain submission reuses the exact same bytes."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        arsd_submit_payload_digest,
    )

    config = _make_config(enabled=True)
    first = _build_payload(config=config)
    second = _build_payload(config=config)
    assert first == second
    assert arsd_submit_payload_digest(first) == arsd_submit_payload_digest(second)

    different = _build_payload(config=config, prompt_text="other prompt text")
    assert arsd_submit_payload_digest(different) != arsd_submit_payload_digest(first)


def test_submit_payload_mutation_never_drifts_the_config() -> None:
    config = _make_config(enabled=True)
    payload = _build_payload(config=config)
    payload["request"]["limits"]["max_events"] = 1
    payload["request"]["grant_capabilities"].append("write")

    fresh = _build_payload(config=config)
    assert fresh["request"]["limits"]["max_events"] == 10_000
    assert fresh["request"]["grant_capabilities"] == ["read", "search"]


def test_builder_errors_never_echo_prompt_or_private_paths() -> None:
    try:
        _build_payload(workspace_ref="ws_missing", prompt_text=PROMPT_CANARY)
    except SpineError as err:
        rendering = repr(err) + str(err) + repr(err.args)
        assert PROMPT_CANARY not in rendering
        assert WORKSPACE_CANARY not in rendering
        assert "sachima-canary" not in rendering
    else:  # pragma: no cover - the call above must raise
        pytest.fail("expected SpineError")


def test_submit_payload_digest_conversion_failure_is_stable_and_unchained() -> None:
    """An unserializable payload fails closed with the stable code — the
    ``json`` conversion error never chains into the stable rendering."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        arsd_submit_payload_digest,
    )

    with pytest.raises(SpineError) as excinfo:
        arsd_submit_payload_digest({"request": object()})
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)
    rendered = _rendered_chain(excinfo)
    assert "serializable" not in rendered
    assert "TypeError" not in rendered


# --------------------------------------------------------------------------- #
# Malformed external path ingress: every external path value (config
# socket_path, workspace map values, request cwd) crosses the one shared
# boundary before any pathlib/filesystem operation — malformed material fails
# closed with the caller-selected stable code, never a raw pathlib error.
# --------------------------------------------------------------------------- #
NUL_PATH_TOKEN = "nul-path-canary-3c9e"


def _config_socket_path_ingress(bad_path) -> None:
    _make_config(socket_path=bad_path)


def _config_workspace_value_ingress(bad_path) -> None:
    _make_config(workspace_by_ref={"ws_main": bad_path})


def _request_cwd_ingress(bad_path) -> None:
    _build_payload(cwd=bad_path)


@pytest.mark.parametrize(
    "bad_path",
    [
        pytest.param(f"/tmp/{NUL_PATH_TOKEN}\x00/private.sock", id="nul_component"),
        pytest.param(f"/tmp/{NUL_PATH_TOKEN}/private.sock\x00", id="trailing_nul"),
        pytest.param(f"/\x00{NUL_PATH_TOKEN}", id="nul_after_root"),
        pytest.param(f"/tmp/{NUL_PATH_TOKEN}/\ud800", id="unencodable_surrogate"),
    ],
)
@pytest.mark.parametrize(
    "ingress,code",
    [
        (_config_socket_path_ingress, RUNTIME_INVALID_ARSD_CONFIG),
        (_config_workspace_value_ingress, RUNTIME_INVALID_ARSD_CONFIG),
        (_request_cwd_ingress, RUNTIME_ARSD_INVALID_REQUEST),
    ],
    ids=["config_socket_path", "config_workspace_value", "request_cwd"],
)
def test_malformed_external_paths_fail_closed_at_the_shared_boundary(
    ingress, code, bad_path
) -> None:
    """NUL-bearing (or otherwise pathlib-rejected) external path strings must
    fail closed with the caller-selected stable code — never escape
    ``Path.resolve()`` as a raw ``ValueError`` — and no rendering surface of
    the stable error's chain may carry the invalid material."""

    with pytest.raises(SpineError) as excinfo:
        ingress(bad_path)
    _assert_stable_code_only(excinfo, code)
    rendered = _rendered_chain(excinfo)
    assert NUL_PATH_TOKEN not in rendered
    assert "\x00" not in rendered
    assert "\ud800" not in rendered
    assert "ValueError" not in rendered
    assert "null byte" not in rendered
    assert "surrogate" not in rendered.lower()


def test_submit_payload_valid_cwd_is_preserved_through_the_path_boundary() -> None:
    """The repair must not narrow valid behavior: a well-formed private
    absolute cwd inside the bound workspace still passes through verbatim."""

    cwd = WORKSPACE_CANARY + "/task-cwd"
    assert _build_payload(cwd=cwd)["cwd"] == cwd


# --------------------------------------------------------------------------- #
# cwd containment (Δ-13 / Spec §10.6.2 / A-28): at 0.7.6 a read/search allow
# requires every declared path to resolve inside the bound workspace, so a cwd
# outside ``workspace_root`` turns a correctly configured Run into a
# guaranteed failure. That is checkable offline, before any socket call.
# --------------------------------------------------------------------------- #
class _ExplodingFacade:
    """A facade double whose every operation fails the test if reached."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _forbidden(self, op: str):
        self.calls.append(op)
        raise AssertionError(f"no facade call may be reachable here: {op}")

    def server_info(self):
        self._forbidden("server_info")

    def submit(self, *, request_id, payload):
        self._forbidden("submit")

    def run_status(self, run_id):
        self._forbidden("run_status")

    def run_events(self, run_id, *, from_seq, limit=None):
        self._forbidden("run_events")

    def run_cancel(self, run_id):
        self._forbidden("run_cancel")

    def session_status(self, session_id):
        self._forbidden("session_status")

    def session_list(self):
        self._forbidden("session_list")

    def agent_list(self):
        self._forbidden("agent_list")


def _build_then_submit(facade, config=None, **overrides):
    """Build a payload and hand it straight to the facade.

    This is the shape every later dispatch takes: construct, then submit. It
    exists so the "fails closed **before** any facade call" tests are not
    vacuous — with a valid payload the armed double is genuinely reached
    (proven by :func:`test_the_exploding_facade_double_is_armed`), so a test
    that never reaches it proves the builder refused first.
    """

    payload = _build_payload(config=config, **overrides)
    return facade.submit(request_id="sachima-offline-construction-probe", payload=payload)


def test_the_exploding_facade_double_is_armed() -> None:
    """Control for the two fail-closed-before-any-call tests below: a payload
    the builder accepts does reach ``facade.submit``."""

    facade = _ExplodingFacade()
    with pytest.raises(AssertionError):
        _build_then_submit(facade)
    assert facade.calls == ["submit"]


@pytest.mark.parametrize(
    "cwd",
    [
        "/tmp/sachima-canary/other-workspace",
        "/tmp/sachima-canary",
        "/tmp",
        "/tmp/sachima-canary/private-workspace-sibling",
        "/tmp/sachima-canary/private-workspace/../escape",
    ],
    ids=["sibling", "parent", "root", "prefix_lookalike", "traversal"],
)
def test_cwd_outside_workspace_root_fails_closed_before_any_facade_call(cwd) -> None:
    """A-28: the containment check runs inside the builder, so a submit that
    would make every read/search deny fail-closed never leaves Sachima.

    The facade double raises on any call; the builder is the only thing that
    runs, and it must refuse first. A path that merely shares a textual prefix
    with the workspace root is outside it, and traversal is resolved before
    the comparison rather than compared as text.
    """

    facade = _ExplodingFacade()
    with pytest.raises(SpineError) as excinfo:
        _build_then_submit(facade, cwd=cwd)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)
    assert facade.calls == []
    assert "sachima-canary" not in _rendered_chain(excinfo)


@pytest.mark.parametrize(
    "cwd",
    [
        WORKSPACE_CANARY,
        WORKSPACE_CANARY + "/task-cwd",
        WORKSPACE_CANARY + "/nested/deeper",
        WORKSPACE_CANARY + "/nested/../task-cwd",
    ],
    ids=["root_itself", "child", "grandchild", "traversal_back_inside"],
)
def test_cwd_inside_workspace_root_is_accepted(cwd) -> None:
    """A-28's other half: containment must not narrow valid behaviour. The
    workspace root itself is inside itself, and a path that resolves back
    inside is accepted."""

    assert _build_payload(cwd=cwd)["cwd"] == cwd


# --------------------------------------------------------------------------- #
# Per-Run configuration override (Spec §5.5 / A-25): model and effort come
# from the closed policy maps on every Run, and from nowhere else. These are
# **construction** proofs — a built request literal says what Sachima
# requested, never what the Run executed under (Spec §5.5.3, gate E-9).
# --------------------------------------------------------------------------- #
def _two_policy_config():
    return _make_config(
        enabled=True,
        agent_by_policy_ref={
            "policy_reader": "reader-agent",
            "policy_deep": "reader-agent",
        },
        model_by_policy_ref={
            "policy_reader": "claude-sonnet-5",
            "policy_deep": "claude-opus-5",
        },
        effort_by_policy_ref={
            "policy_reader": "medium",
            "policy_deep": "high",
        },
        run_limits_by_policy_ref={
            "policy_reader": _limits_with(),
            "policy_deep": _limits_with(),
        },
    )


def test_two_policy_refs_produce_payloads_differing_in_exactly_model_and_effort() -> None:
    """A-25: the maps are load-bearing, and their scope is exactly two values.

    A builder that ignored the refs produces an empty difference and fails
    here; one that leaked a ref into another field produces a wider difference
    and also fails.
    """

    config = _two_policy_config()
    first = _build_payload(
        config=config, model_policy_ref="policy_reader", effort_policy_ref="policy_reader"
    )
    second = _build_payload(
        config=config, model_policy_ref="policy_deep", effort_policy_ref="policy_deep"
    )

    differing = {
        key
        for key in set(first["request"]) | set(second["request"])
        if first["request"].get(key, _ABSENT) != second["request"].get(key, _ABSENT)
    }
    assert differing == {"requested_model", "requested_effort"}
    assert first["request"]["requested_model"] == "claude-sonnet-5"
    assert first["request"]["requested_effort"] == "medium"
    assert second["request"]["requested_model"] == "claude-opus-5"
    assert second["request"]["requested_effort"] == "high"
    # Outside ``request`` nothing moves either.
    for key in ("prompt_text", "workspace_root", "cwd", "retry_of_run_id"):
        assert first[key] == second[key]


def test_a_reuse_turn_carries_its_own_newly_resolved_pair() -> None:
    """A-25 / §5.5.4: model and effort are properties of the Run, not the
    Session. A second Run reusing one Session under a different policy ref
    carries the newly resolved pair — nothing is cached onto the binding."""

    config = _two_policy_config()
    first = _build_payload(
        config=config,
        model_policy_ref="policy_reader",
        effort_policy_ref="policy_reader",
    )
    reuse = _build_payload(
        config=config,
        session_id=REUSE_SESSION_ID,
        model_policy_ref="policy_deep",
        effort_policy_ref="policy_deep",
    )
    assert first["request"]["requested_model"] == "claude-sonnet-5"
    assert reuse["request"]["requested_model"] == "claude-opus-5"
    assert reuse["request"]["requested_effort"] == "high"
    assert reuse["request"]["session_id"] == REUSE_SESSION_ID


@pytest.mark.parametrize(
    "overrides",
    [
        {"model_policy_ref": "policy_unmapped"},
        {"effort_policy_ref": "policy_unmapped"},
    ],
)
def test_unmapped_model_or_effort_policy_ref_fails_closed_before_any_facade_call(
    overrides,
) -> None:
    """A-25 / §5.5.2 rule 3: no implicit fallback and no submit with a hole in
    it. The facade double raises on call; the builder refuses first."""

    facade = _ExplodingFacade()
    with pytest.raises(SpineError) as excinfo:
        _build_then_submit(facade, **overrides)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)
    assert facade.calls == []


def test_no_code_path_reads_last_effective_values_back_into_request_construction() -> None:
    """A-25 / R-5: ``session_status``'s ``last_effective_*`` are observations of
    a past Run. Nothing in the builder's construction surface names them, so
    the per-Run override cannot silently degrade into a Session-level setting.
    """

    import inspect

    import sachima_supervisor.runtime_spine.arsd_socket_contract as contract

    builder_source = inspect.getsource(contract.build_arsd_submit_payload)
    assert "last_effective" not in builder_source
    assert (
        "last_effective_model"
        not in inspect.signature(contract.build_arsd_submit_payload).parameters
    )

    # The session view carries the observations, and they are not accepted by
    # the builder under any keyword.
    with pytest.raises(TypeError):
        _build_payload(last_effective_model="claude-opus-5")


# --------------------------------------------------------------------------- #
# server_info negotiation validator (plan §5.4): exact preflight contract.
# --------------------------------------------------------------------------- #
#: The eight-operation closed set exactly as the daemon emits it
#: (``sorted(protocol.OPERATIONS)``); drift-locked below. ``agent_list`` is
#: 0.7.8's purely additive read-only roster operation — the wire stays v3.
V3_OPERATIONS = [
    "agent_list",
    "run_cancel",
    "run_events",
    "run_status",
    "server_info",
    "session_list",
    "session_status",
    "submit",
]

#: A plausible operator-configured negotiated event budget. Never the 4 GiB
#: deployment default: no test may equality-assert that (Δ-9 / A-22).
NEGOTIATED_EVENT_BUDGET = 2_147_483_648

V3_LIMITS = {
    "max_concurrent_runs": 4,
    "max_frame_bytes": 1_048_576,
    "max_prompt_bytes": 262_144,
    "events_page_limit": 256,
    "event_follow_queue_size": 1024,
    "max_run_event_budget_bytes": NEGOTIATED_EVENT_BUDGET,
}

#: The 0.7.1 five-key ``limits`` block — a protocol violation against a 0.7.6
#: daemon, not a tolerated older peer (Δ-8 / A-22).
V2_LIMITS = {key: value for key, value in V3_LIMITS.items()
             if key != "max_run_event_budget_bytes"}


def _server_info_payload(**overrides):
    payload = {
        "version": "0.7.8",
        "api_version": 3,
        "supported_api_versions": [3],
        "operations": list(V3_OPERATIONS),
        "limits": dict(V3_LIMITS),
    }
    payload.update(overrides)
    return payload


def _validate_server_info(payload, config=None):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        validate_arsd_server_info,
    )

    if config is None:
        config = _make_config(enabled=True)
    return validate_arsd_server_info(payload, config=config)


def _limits_override(**changes):
    limits = dict(V3_LIMITS)
    limits.update(changes)
    return {"limits": limits}


def test_server_info_negotiation_accepts_the_exact_078_v3_shape() -> None:
    info = _validate_server_info(_server_info_payload())
    assert info.version == "0.7.8"
    assert info.api_version == 3
    assert info.supported_api_versions == (3,)
    assert info.operations == tuple(V3_OPERATIONS)
    assert dict(info.limits) == dict(V3_LIMITS)
    # The negotiated budget is carried as a runtime observation, never
    # compared for equality against a mirrored default (Spec §5.3.1).
    assert info.max_run_event_budget_bytes == NEGOTIATED_EVENT_BUDGET


def test_server_info_fixture_daemon_version_tracks_the_reviewed_pin() -> None:
    """Drift-lock: the fake daemon speaks the version we actually negotiate.

    ``validate_arsd_server_info`` refuses any ``server_info.version`` that is
    not the reviewed pin exactly, so a fixture left behind on the previous
    release would silently turn every acceptance test in this file into a
    mismatch case. Bind the fixture literal to the one source of truth here so
    a pin advance fails on this named assertion instead of scattering
    ``runtime_arsd_version_mismatch`` across unrelated tests.
    """

    from sachima_supervisor.supervisor_library import (
        EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
    )

    assert _server_info_payload()["version"] == EXPECTED_AGENT_RUN_SUPERVISOR_VERSION


def test_server_info_exposes_the_negotiated_concurrency_limit() -> None:
    """The delegate coordinator's capacity comes from here and nowhere else.

    A typed accessor rather than a raw mapping read, for the same reason the
    event budget has one: the only admissible source of "how many Runs may be
    live at once" is a validated live negotiation. There is deliberately no
    mirrored default beside it to fall back to.
    """

    info = _validate_server_info(_server_info_payload(**_limits_override(max_concurrent_runs=10)))
    assert info.max_concurrent_runs == 10
    assert info.max_concurrent_runs == info.limits["max_concurrent_runs"]

    other = _validate_server_info(_server_info_payload())
    assert other.max_concurrent_runs == V3_LIMITS["max_concurrent_runs"] == 4


def test_no_mirrored_concurrency_default_exists_to_fall_back_to() -> None:
    """A constant beside the negotiated value is how a fallback gets born."""

    import sachima_supervisor.runtime_spine.arsd_socket_contract as contract_mod

    for name in dir(contract_mod):
        value = getattr(contract_mod, name)
        if "CONCURRENT" in name.upper() and isinstance(value, int):
            raise AssertionError(f"mirrored concurrency constant: {name}")


def test_server_info_top_level_key_set_is_still_exactly_five() -> None:
    """Δ-8 / A-22: only the nested ``limits`` block grew. The top-level key
    set is unchanged at five, and ``v2_only_operations`` is gone (A-3)."""

    payload = _server_info_payload()
    assert set(payload) == {
        "version",
        "api_version",
        "supported_api_versions",
        "operations",
        "limits",
    }
    assert len(payload) == 5
    _validate_server_info(payload)


def test_server_info_still_carrying_v2_only_operations_is_a_protocol_violation() -> None:
    """A-3: the retired v2 key is an extra key, not a tolerated leftover."""

    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(_server_info_payload(v2_only_operations=["submit"]))
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_PROTOCOL_VIOLATION)


def test_server_info_limits_requires_exactly_six_keys() -> None:
    """A-22 / Δ-8: the six-key block is accepted; the 0.7.1 five-key block and
    a seven-key block are each a protocol violation, not a tolerated peer.

    There is no compatibility window and no per-operation version matrix, so
    an older-shaped ``limits`` is a violation rather than a negotiated
    downgrade.
    """

    _validate_server_info(_server_info_payload())

    seven_keys = dict(V3_LIMITS)
    seven_keys["max_run_event_follow_bytes"] = 1024
    for bad_limits in (V2_LIMITS, seven_keys):
        with pytest.raises(SpineError) as excinfo:
            _validate_server_info(_server_info_payload(limits=dict(bad_limits)))
        _assert_stable_code_only(excinfo, RUNTIME_ARSD_PROTOCOL_VIOLATION)


def test_run_event_budget_is_read_as_negotiated_not_asserted_as_a_default() -> None:
    """A-22 / Δ-9: two different valid budgets both negotiate successfully.

    The operator owns this number. Sachima reads whatever the daemon reports,
    bounded only by the structural maximum, and no test anywhere
    equality-asserts the 4 GiB deployment default.
    """

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES,
    )

    for budget in (
        1,
        1_073_741_824,
        NEGOTIATED_EVENT_BUDGET,
        ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES,
    ):
        info = _validate_server_info(
            _server_info_payload(**_limits_override(max_run_event_budget_bytes=budget))
        )
        assert info.max_run_event_budget_bytes == budget


@pytest.mark.parametrize(
    "bad_budget",
    [0, -1, 1_048_576_000_001],
    ids=["zero", "negative", "above_structural_maximum"],
)
def test_server_info_out_of_range_event_budget_is_a_mismatch(bad_budget) -> None:
    """The negotiated budget must be a positive int at most the mirrored
    structural maximum — a daemon reporting otherwise is not a contract this
    adapter implements."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        RUNTIME_ARSD_VERSION_MISMATCH,
    )

    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(
            _server_info_payload(
                **_limits_override(max_run_event_budget_bytes=bad_budget)
            )
        )
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_VERSION_MISMATCH)


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": "0.1.7"},
        {"version": "0.6.3"},
        {"version": "0.7.5"},
        {"version": "0.7.7"},
        {"api_version": 2},
        {"api_version": 4},
        {"supported_api_versions": [2, 3]},
        {"supported_api_versions": [2]},
        {"operations": []},
        {"operations": sorted(V3_OPERATIONS + ["session_close"])},
        {"operations": sorted(set(V3_OPERATIONS) - {"run_cancel"})},
        # A roster-less daemon is refused outright: there is no degraded
        # admission path that tolerates a peer without ``agent_list``.
        {"operations": sorted(set(V3_OPERATIONS) - {"agent_list"})},
        {"operations": list(reversed(V3_OPERATIONS))},
        _limits_override(max_concurrent_runs=0),
        _limits_override(max_frame_bytes=999),
        _limits_override(max_prompt_bytes=1),
    ],
)
def test_server_info_incompatibility_is_one_stable_mismatch_code(
    overrides: dict,
) -> None:
    """Package/API/operation/limit mismatch → one stable backend-unavailable
    code. ``session_close`` does not exist in v3 and an eighth operation is a
    different contract, not an extension."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        RUNTIME_ARSD_VERSION_MISMATCH,
    )

    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(_server_info_payload(**overrides))
    assert excinfo.value.code == RUNTIME_ARSD_VERSION_MISMATCH


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "server info",
        {},
        _server_info_payload(version=7),
        _server_info_payload(api_version=True),
        _server_info_payload(api_version="3"),
        _server_info_payload(supported_api_versions="3"),
        _server_info_payload(supported_api_versions=[3, True]),
        _server_info_payload(operations="submit"),
        _server_info_payload(operations=[7]),
        _server_info_payload(limits=None),
        _server_info_payload(limits={}),
        _server_info_payload(extra_key=1),
        _server_info_payload(**_limits_override(surprise=1)),
        _server_info_payload(**_limits_override(max_concurrent_runs="4")),
        _server_info_payload(**_limits_override(max_run_event_budget_bytes=True)),
        _server_info_payload(**_limits_override(max_run_event_budget_bytes="1024")),
    ],
)
def test_malformed_server_info_is_a_protocol_violation(payload) -> None:
    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(payload)
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


REMOTE_OP_CANARY = "remote-detail-canary-7d9f"


@pytest.mark.parametrize(
    "operations",
    [
        sorted(V3_OPERATIONS + [REMOTE_OP_CANARY]),
        [REMOTE_OP_CANARY] + V3_OPERATIONS,
        [REMOTE_OP_CANARY],
        sorted(V3_OPERATIONS + ["submit"]),
        sorted(V3_OPERATIONS + ["session_close"]),
    ],
    ids=[
        "extra_canary",
        "canary_first",
        "canary_only",
        "duplicate",
        "retired_session_close",
    ],
)
def test_server_info_operations_must_be_exactly_the_closed_seven(operations) -> None:
    """Pinned 0.7.6 fact: exactly seven operations, sorted, and there is no
    ``session_close``. Extra, duplicate, or arbitrary remote entries are
    rejected before ``ArsdServerInfo`` exists — a remote token never reaches a
    repr surface."""

    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(_server_info_payload(operations=operations))
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_VERSION_MISMATCH)
    assert REMOTE_OP_CANARY not in _rendered_chain(excinfo)


@pytest.mark.parametrize(
    "bad_entry",
    ["remote detail canary 7d9f", "x" * 4096, "bad\nop-canary-7d9f", ""],
    ids=["spaces", "unbounded", "newline", "empty"],
)
def test_server_info_malformed_operation_entries_are_protocol_violations(
    bad_entry,
) -> None:
    """An off-grammar operation token is malformed shape, not a compat verdict."""

    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(
            _server_info_payload(operations=V3_OPERATIONS + [bad_entry])
        )
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_PROTOCOL_VIOLATION)
    rendered = _rendered_chain(excinfo)
    assert "x" * 64 not in rendered
    if bad_entry:
        assert bad_entry not in rendered


@pytest.mark.parametrize(
    "supported",
    [[3, 31337], [3, 2], [3, 3], [2], [3, 10**4000]],
    ids=["extra_version", "with_v2", "duplicate", "only_v2", "unbounded_int"],
)
def test_server_info_supported_versions_must_be_exactly_the_pinned_tuple(
    supported,
) -> None:
    """Pinned 0.7.6 fact: the daemon reports ``[3]`` exactly. Any other
    well-formed int list is a different contract — and an unbounded remote
    int never reaches the repr-safe observation."""

    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(_server_info_payload(supported_api_versions=supported))
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_VERSION_MISMATCH)
    rendered = _rendered_chain(excinfo)
    assert "31337" not in rendered
    assert str(10**4000) not in rendered


@pytest.mark.parametrize(
    "capacity_key",
    ["max_concurrent_runs", "events_page_limit", "event_follow_queue_size"],
)
def test_server_info_unbounded_capacity_limits_never_reach_the_observation(
    capacity_key,
) -> None:
    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(
            _server_info_payload(**_limits_override(**{capacity_key: 10**4000}))
        )
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_VERSION_MISMATCH)
    assert str(10**4000) not in _rendered_chain(excinfo)


def test_server_info_version_canary_never_survives_or_renders() -> None:
    """A regex-valid but off-pin version string is rejected with the stable
    mismatch code and never rendered anywhere."""

    off_pin_version = "0.7.6rc-canary-7d9f"
    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(_server_info_payload(version=off_pin_version))
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_VERSION_MISMATCH)
    assert off_pin_version not in _rendered_chain(excinfo)


def test_server_info_mirror_constants_match_the_pinned_protocol() -> None:
    """B-4: every protocol mirror is asserted against the imported real module.

    ``V2_ONLY_OPERATIONS`` is gone at v3 (Spec D-5); its absence is asserted
    so a re-introduction cannot pass unnoticed.
    """

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_MAX_ERROR_MESSAGE_CHARS,
        ARSD_MAX_FRAME_BYTES,
        ARSD_MAX_JSON_NESTING_DEPTH,
        ARSD_MAX_PROMPT_BYTES,
        ARSD_OPERATIONS,
        ARSD_REQUIRED_API_VERSION,
        _ARSD_SUPPORTED_API_VERSIONS,
    )

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    assert ARSD_MAX_FRAME_BYTES == protocol.MAX_FRAME_BYTES
    assert ARSD_MAX_PROMPT_BYTES == protocol.MAX_PROMPT_BYTES
    assert ARSD_MAX_JSON_NESTING_DEPTH == protocol.MAX_JSON_NESTING_DEPTH
    assert ARSD_MAX_ERROR_MESSAGE_CHARS == protocol.MAX_ERROR_MESSAGE_CHARS
    assert ARSD_REQUIRED_API_VERSION == protocol.ARSD_API_VERSION == 3
    assert ARSD_REQUIRED_API_VERSION in protocol.SUPPORTED_API_VERSIONS
    assert not hasattr(protocol, "V2_ONLY_OPERATIONS")

    # The closed negotiation mirrors equal the exact wire emission of the
    # pinned daemon (``list(...)`` / ``sorted(...)`` in its server_info).
    assert _ARSD_SUPPORTED_API_VERSIONS == tuple(protocol.SUPPORTED_API_VERSIONS) == (3,)
    assert ARSD_OPERATIONS == frozenset(protocol.OPERATIONS)
    assert len(ARSD_OPERATIONS) == 8
    assert "agent_list" in ARSD_OPERATIONS
    assert "session_close" not in ARSD_OPERATIONS
    assert V3_OPERATIONS == sorted(protocol.OPERATIONS)

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_SPEC_SCHEMA_VERSION,
    )

    assert ARSD_SPEC_SCHEMA_VERSION == spec.SPEC_SCHEMA_VERSION == 3


def test_request_field_set_and_required_split_match_the_real_dataclass() -> None:
    """B-6 schema drift: the built request's field set is exactly the real
    ``AgentRunRequest`` contract, and the per-Run override fields are named
    explicitly so an upstream rename or removal breaks the lock instead of
    silently emptying the override (Spec §5.5.5)."""

    import dataclasses

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")

    real_fields = {field.name for field in dataclasses.fields(spec.AgentRunRequest)}
    optional = {
        field.name
        for field in dataclasses.fields(spec.AgentRunRequest)
        if field.default is not dataclasses.MISSING
    }
    required = real_fields - optional

    assert {"requested_model", "requested_effort"} <= required
    assert optional == {"session_id", "schema_version"}

    create = _build_payload()["request"]
    assert set(create) == required | {"schema_version"}
    reuse = _build_payload(session_id=REUSE_SESSION_ID)["request"]
    assert set(reuse) == real_fields


def test_session_id_grammar_mirrors_the_real_session_pattern() -> None:
    """B-8: Sachima's session-id validator matches ``SESSION_ID_PATTERN``.

    Dots are the drift that matters — the retired wire-token grammar allowed
    them and the Session grammar does not (Spec D-12) — so the two validators
    are compared over a table that includes one.
    """

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_SESSION_ID_PATTERN,
        _safe_session_token,
    )

    session = pytest.importorskip("agent_run_supervisor.session")
    assert ARSD_SESSION_ID_PATTERN == session.SESSION_ID_PATTERN

    for candidate in (
        "sess-4f2a9c11b7d3",
        "a",
        "A0_-",
        session.SESSION_ID_PREFIX + "0" * 32,
        "sess.4f2a",
        "-lead",
        "_lead",
        "",
        "has space",
        "has/slash",
    ):
        theirs = session.is_valid_session_id(candidate)
        try:
            _safe_session_token(candidate)
        except SpineError:
            ours = False
        else:
            ours = True
        assert ours is theirs, candidate


def test_session_id_length_bound_matches_the_real_request_validator() -> None:
    """The bound Sachima applies to a remote session id is the distribution's
    own, proven behaviourally rather than copied from a private symbol."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_MAX_SESSION_ID_CHARS,
        _safe_session_token,
    )

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")

    def _request_with(session_id):
        return spec.AgentRunRequest(
            owner="sachima_host",
            namespace="sachima_tasks",
            agent_id="reader-agent",
            expected_binding_hash=None,
            input_refs=(),
            requested_model="claude-sonnet-5",
            requested_effort="medium",
            grant_ref="grant_reader_v1",
            grant_hash="sha256:" + "a" * 64,
            grant_role_hash="sha256:" + "b" * 64,
            grant_capabilities=("read", "search"),
            mcp_snapshot_hashes=(),
            credential_refs=(),
            limits=spec.RunLimits(),
            evidence_policy_hash="sha256:" + "d" * 64,
            recovery_policy_hash="sha256:" + "e" * 64,
            session_id=session_id,
        )

    at_bound = "s" * ARSD_MAX_SESSION_ID_CHARS
    over_bound = "s" * (ARSD_MAX_SESSION_ID_CHARS + 1)
    _request_with(at_bound)
    with pytest.raises(spec.SpecValidationError):
        _request_with(over_bound)

    assert _safe_session_token(at_bound) == at_bound
    with pytest.raises(SpineError) as excinfo:
        _safe_session_token(over_bound)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)


def test_terminal_status_vocabulary_mirrors_the_real_enum() -> None:
    """B-9: the five-member Run terminal vocabulary is anchored to the real
    enum, with no sixth member — a permission violation is a terminal
    *reason*, not a status (Δ-15 / §10.7)."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_TERMINAL_STATUSES,
        ARSD_PERMISSION_VIOLATION_REASON,
    )

    exit_classifier = pytest.importorskip("agent_run_supervisor.exit_classifier")
    real = tuple(status.value for status in exit_classifier.AgentRunStatus)
    assert ARSD_TERMINAL_STATUSES == real
    assert ARSD_TERMINAL_STATUSES == (
        "completed",
        "failed",
        "cancelled",
        "timed_out",
        "unknown",
    )
    assert len(ARSD_TERMINAL_STATUSES) == 5
    assert ARSD_PERMISSION_VIOLATION_REASON not in ARSD_TERMINAL_STATUSES


def test_transport_terminal_vocabulary_is_disjoint_from_canonical_status_values() -> None:
    """R-6: ``timed_out`` and ``unknown`` are transport tokens with no
    canonical counterpart, so neither can ever be appended as a Sachima
    status. The three that share a name are the three that legitimately map
    straight through."""

    from sachima_supervisor.runtime_spine import events as spine_events
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_TERMINAL_STATUSES,
    )

    assert "timed_out" not in spine_events.STATUS_VALUES
    assert "unknown" not in spine_events.STATUS_VALUES
    assert set(ARSD_TERMINAL_STATUSES) & set(spine_events.STATUS_VALUES) == {
        "completed",
        "failed",
        "cancelled",
    }


def test_permission_violation_terminal_reason_is_anchored_to_the_distribution() -> None:
    """B-13: the mirror is anchored to the real 0.7.6 detail code.

    The exact module path is resolved here against the installed
    distribution (gate E-2): at 0.7.6 the token is the categorical
    ``detail_code`` classification emitted by
    ``agent_run_supervisor.native_acp.run_task``, and it is not a module-level
    constant anywhere in the package. The module is imported directly rather
    than through ``importorskip`` so an absent or renamed anchor **fails**
    here instead of skipping.
    """

    import importlib
    import inspect

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_PERMISSION_VIOLATION_REASON,
    )

    pytest.importorskip("agent_run_supervisor")
    run_task = importlib.import_module("agent_run_supervisor.native_acp.run_task")
    source = inspect.getsource(run_task)

    assert ARSD_PERMISSION_VIOLATION_REASON == "PERMISSION_VIOLATION"
    assert (
        f'detail_code = "{ARSD_PERMISSION_VIOLATION_REASON}"' in source
    ), (
        "the 0.7.6 permission-violation terminal reason moved or was renamed — "
        "re-resolve the anchor rather than weakening this lock"
    )

    # It is a terminal *reason*, not an observation refusal and not a status.
    observation = importlib.import_module("agent_run_supervisor.native_acp.observation")
    assert ARSD_PERMISSION_VIOLATION_REASON not in observation.OBSERVATION_REFUSALS
    assert "CONFIG_FIDELITY" in observation.OBSERVATION_REFUSALS


def test_quarantine_mirrors_match_the_real_session_module() -> None:
    """R-5: the closed five-member quarantine reason vocabulary and the exact
    three evidence fields are the distribution's, not Sachima's."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        _QUARANTINE_EVIDENCE_KEYS,
        _QUARANTINE_REASON_CODES,
    )

    session = pytest.importorskip("agent_run_supervisor.session")
    assert _QUARANTINE_REASON_CODES == frozenset(session.QUARANTINE_REASON_CODES)
    assert len(_QUARANTINE_REASON_CODES) == 5
    assert _QUARANTINE_EVIDENCE_KEYS == frozenset(session.QUARANTINE_EVIDENCE_FIELDS)
    assert _QUARANTINE_EVIDENCE_KEYS == frozenset(
        {"reason_code", "source_run_id", "recorded_at"}
    )


def test_server_info_limit_key_mirror_matches_the_real_daemon_emission() -> None:
    """B-12 first half: the six-key ``limits`` mirror is the real key set the
    0.7.6 handler emits, read off its own source rather than transcribed."""

    import importlib
    import inspect

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        _SERVER_INFO_KEYS,
        _SERVER_INFO_LIMIT_KEYS,
    )

    pytest.importorskip("agent_run_supervisor")
    handlers = importlib.import_module("agent_run_supervisor.arsd.handlers")
    source = inspect.getsource(handlers.ArsdHandlers._server_info)

    assert len(_SERVER_INFO_LIMIT_KEYS) == 6
    for key in _SERVER_INFO_LIMIT_KEYS:
        assert f'"{key}"' in source, key
    for key in _SERVER_INFO_KEYS:
        assert f'"{key}"' in source, key
    assert "v2_only_operations" not in source


# --------------------------------------------------------------------------- #
# submit response validator: durable acceptance only, run_id stays private.
# --------------------------------------------------------------------------- #
def _validate_submit(payload):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        validate_arsd_submit_result,
    )

    return validate_arsd_submit_result(payload)


ACCEPTED_AT = "2026-08-17T10:00:00+00:00"


def _submit_ack(**overrides):
    ack = {
        "run_id": "1f2e3d4c5b6a",
        "session_id": REUSE_SESSION_ID,
        "accepted_at": ACCEPTED_AT,
    }
    ack.update(overrides)
    return ack


def test_submit_result_returns_accepted_identity() -> None:
    """A-4: the v3 ack is exactly ``{run_id, session_id, accepted_at}``."""

    accepted = _validate_submit(_submit_ack())
    assert accepted.run_id == "1f2e3d4c5b6a"
    assert accepted.session_id == REUSE_SESSION_ID
    assert accepted.accepted_at == ACCEPTED_AT


def test_submit_result_keeps_both_ids_out_of_repr() -> None:
    """A-4: ``run_id`` and ``session_id`` are both private locators."""

    accepted = _validate_submit(
        _submit_ack(run_id="private4runid", session_id="private4sessionid")
    )
    rendering = repr(accepted) + str(accepted)
    assert "private4runid" not in rendering
    assert "private4sessionid" not in rendering
    for attr in ("as_dict", "to_dict", "serialize", "to_json"):
        assert not hasattr(accepted, attr)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"run_id": "abc"},
        {"run_id": "abc", "accepted_at": ACCEPTED_AT},
        {"session_id": REUSE_SESSION_ID, "accepted_at": ACCEPTED_AT},
        {"run_id": "abc", "session_id": REUSE_SESSION_ID},
        _submit_ack(x=1),
        _submit_ack(run_id=""),
        _submit_ack(run_id=7),
        _submit_ack(run_id="bad run id"),
        _submit_ack(session_id=""),
        _submit_ack(session_id=None),
        _submit_ack(session_id="sess.dotted"),
        _submit_ack(session_id=7),
        _submit_ack(accepted_at="not a timestamp"),
        _submit_ack(accepted_at="2026-08-17T10:00:00"),
        _submit_ack(accepted_at=None),
        _submit_ack(accepted_at=ACCEPTED_AT + "\nx"),
    ],
)
def test_malformed_submit_result_is_a_protocol_violation(payload) -> None:
    """A-4: a missing ``session_id``, an extra key, an off-grammar id, or a
    bad timestamp is a protocol violation."""

    with pytest.raises(SpineError) as excinfo:
        _validate_submit(payload)
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


@pytest.mark.parametrize(
    "bad_timestamp",
    ["remote-detail-canary-7d9f", "2026-99-99T99:99:99+00:00"],
    ids=["token_canary", "unparseable_datetime"],
)
def test_submit_result_timestamp_parse_failure_never_chains_remote_text(
    bad_timestamp,
) -> None:
    """A stdlib parse failure translates to the stable code with ``from None``
    semantics — the remote string must not survive in the cause/context
    rendering of the stable error."""

    with pytest.raises(SpineError) as excinfo:
        _validate_submit(_submit_ack(run_id="run4abc", accepted_at=bad_timestamp))
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_PROTOCOL_VIOLATION)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True
    rendered = _rendered_chain(excinfo)
    assert "canary" not in rendered
    assert "isoformat" not in rendered
    assert "99:99" not in rendered
    assert "ValueError" not in rendered


# --------------------------------------------------------------------------- #
# run_status validator (A-11): the acceptance view and the active view are two
# exact shapes. A missing, extra, or off-contract key — including a ``state``
# value outside the contract — is a protocol violation, never a tolerated
# field.
# --------------------------------------------------------------------------- #
RUN_RESULT_CANARY = {"status": "completed", "detail": "remote result canary 7d9f"}
PROGRESS_CANARY = {"phase": "running", "note": "remote progress canary 7d9f"}


def _validate_run_status(payload, *, run_id="run4abc"):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        validate_arsd_run_status,
    )

    return validate_arsd_run_status(payload, run_id=run_id)


def test_run_status_acceptance_view_is_the_exact_four_key_shape() -> None:
    observed = _validate_run_status(
        {
            "run_id": "run4abc",
            "session_id": REUSE_SESSION_ID,
            "state": "accepted",
            "accepted_at": ACCEPTED_AT,
        }
    )
    assert observed.state == "accepted"
    assert observed.accepted_at == ACCEPTED_AT
    assert observed.progress is None
    assert observed.result is None
    assert observed.has_terminal_result is False


def test_run_status_active_view_carries_optional_progress_and_result() -> None:
    minimal = _validate_run_status(
        {"run_id": "run4abc", "session_id": REUSE_SESSION_ID}
    )
    assert minimal.state is None
    assert minimal.progress is None and minimal.result is None
    assert minimal.has_terminal_result is False

    progressing = _validate_run_status(
        {
            "run_id": "run4abc",
            "session_id": REUSE_SESSION_ID,
            "progress": dict(PROGRESS_CANARY),
        }
    )
    assert progressing.progress == PROGRESS_CANARY
    assert progressing.has_terminal_result is False

    terminal = _validate_run_status(
        {
            "run_id": "run4abc",
            "session_id": REUSE_SESSION_ID,
            "progress": dict(PROGRESS_CANARY),
            "result": dict(RUN_RESULT_CANARY),
        }
    )
    assert terminal.result == RUN_RESULT_CANARY
    assert terminal.has_terminal_result is True


def test_run_status_keeps_ids_and_raw_bodies_out_of_every_rendering() -> None:
    observed = _validate_run_status(
        {
            "run_id": "run4abc",
            "session_id": "private4sessionid",
            "progress": dict(PROGRESS_CANARY),
            "result": dict(RUN_RESULT_CANARY),
        }
    )
    rendering = repr(observed) + str(observed)
    assert "private4sessionid" not in rendering
    assert "canary" not in rendering
    for attr in ("as_dict", "to_dict", "serialize", "to_json"):
        assert not hasattr(observed, attr)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"run_id": "run4abc"},
        {"session_id": REUSE_SESSION_ID},
        {"run_id": "run4abc", "session_id": REUSE_SESSION_ID, "x": 1},
        {"run_id": "other4run", "session_id": REUSE_SESSION_ID},
        {"run_id": "run4abc", "session_id": "sess.dotted"},
        {"run_id": "run4abc", "session_id": None},
        {"run_id": "run4abc", "session_id": REUSE_SESSION_ID, "state": "accepted"},
        {
            "run_id": "run4abc",
            "session_id": REUSE_SESSION_ID,
            "state": "running",
            "accepted_at": ACCEPTED_AT,
        },
        {
            "run_id": "run4abc",
            "session_id": REUSE_SESSION_ID,
            "state": "accepted",
            "accepted_at": "not a timestamp",
        },
        {
            "run_id": "run4abc",
            "session_id": REUSE_SESSION_ID,
            "state": "accepted",
            "accepted_at": ACCEPTED_AT,
            "progress": {},
        },
        {"run_id": "run4abc", "session_id": REUSE_SESSION_ID, "progress": []},
        {"run_id": "run4abc", "session_id": REUSE_SESSION_ID, "result": "done"},
        {"run_id": "run4abc", "session_id": REUSE_SESSION_ID, "accepted_at": ACCEPTED_AT},
    ],
    ids=[
        "none",
        "list",
        "empty",
        "missing_session",
        "missing_run",
        "extra_key",
        "run_echo_mismatch",
        "dotted_session",
        "null_session",
        "accepted_without_timestamp",
        "off_contract_state",
        "bad_accepted_timestamp",
        "accepted_view_with_progress",
        "progress_not_a_mapping",
        "result_not_a_mapping",
        "timestamp_without_state",
    ],
)
def test_malformed_run_status_is_a_protocol_violation(payload) -> None:
    with pytest.raises(SpineError) as excinfo:
        _validate_run_status(payload)
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


# --------------------------------------------------------------------------- #
# run_cancel validator: the run echo alone, or the run echo plus trusted
# terminal evidence. ``cancelled`` is never claimed from the cancel call.
# --------------------------------------------------------------------------- #
def _validate_run_cancel(payload, *, run_id="run4abc"):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        validate_arsd_run_cancel_result,
    )

    return validate_arsd_run_cancel_result(payload, run_id=run_id)


def test_run_cancel_without_terminal_evidence_claims_nothing() -> None:
    observed = _validate_run_cancel({"run_id": "run4abc"})
    assert observed.status is None
    assert observed.result is None
    assert observed.has_terminal_result is False


def test_run_cancel_with_trusted_terminal_evidence_carries_the_status() -> None:
    observed = _validate_run_cancel(
        {
            "run_id": "run4abc",
            "status": "cancelled",
            "result": dict(RUN_RESULT_CANARY),
        }
    )
    assert observed.status == "cancelled"
    assert observed.has_terminal_result is True
    assert "canary" not in repr(observed) + str(observed)


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "timed_out", "unknown"])
def test_run_cancel_accepts_every_member_of_the_terminal_vocabulary(status) -> None:
    observed = _validate_run_cancel(
        {"run_id": "run4abc", "status": status, "result": {"status": status}}
    )
    assert observed.status == status


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"run_id": "other4run"},
        {"run_id": "run4abc", "x": 1},
        {"run_id": "run4abc", "status": "cancelled"},
        {"run_id": "run4abc", "result": dict(RUN_RESULT_CANARY)},
        {"run_id": "run4abc", "status": "accepted", "result": {}},
        {"run_id": "run4abc", "status": "PERMISSION_VIOLATION", "result": {}},
        {"run_id": "run4abc", "status": None, "result": {}},
        {"run_id": "run4abc", "status": "cancelled", "result": []},
    ],
    ids=[
        "none",
        "empty",
        "run_echo_mismatch",
        "extra_key",
        "status_without_result",
        "result_without_status",
        "off_vocabulary_status",
        "terminal_reason_is_not_a_status",
        "null_status",
        "result_not_a_mapping",
    ],
)
def test_malformed_run_cancel_is_a_protocol_violation(payload) -> None:
    with pytest.raises(SpineError) as excinfo:
        _validate_run_cancel(payload)
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


# --------------------------------------------------------------------------- #
# session_status / session_list validators (R-5): the exact ten-key view, the
# closed quarantine block, and a top level that is never a bare record.
# --------------------------------------------------------------------------- #
def _session_view(**overrides):
    view = {
        "session_id": REUSE_SESSION_ID,
        "owner": "sachima_host",
        "namespace": "sachima_tasks",
        "agent_id": "reader-agent",
        "profile_id": "reader-profile",
        "created_at": "2026-08-17T09:00:00+00:00",
        "updated_at": ACCEPTED_AT,
        "last_effective_model": "claude-sonnet-5",
        "last_effective_effort": "medium",
        "quarantine": None,
    }
    view.update(overrides)
    return view


def _validate_session_view(payload):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        validate_arsd_session_view,
    )

    return validate_arsd_session_view(payload)


def _validate_session_list(payload):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        validate_arsd_session_list,
    )

    return validate_arsd_session_list(payload)


def test_session_view_accepts_the_exact_ten_key_shape() -> None:
    view = _validate_session_view(_session_view())
    assert view.session_id == REUSE_SESSION_ID
    assert view.owner == "sachima_host"
    assert view.agent_id == "reader-agent"
    assert view.last_effective_model == "claude-sonnet-5"
    assert view.last_effective_effort == "medium"
    assert view.quarantine_reason_code is None
    assert view.is_reusable is True


def test_session_view_optionality_mirrors_the_real_session_record() -> None:
    """The ten-key set is exact; which of those ten may be null is the
    distribution's declaration, not Sachima's preference.

    A Session whose first Run has produced no observations, or a record
    predating a field, legitimately reports them absent. The daemon guarantees
    ``session_id``/``owner``/``namespace`` on every view it emits — it refuses
    or skips a record without them — so those three stay required here.
    """

    import dataclasses

    session = pytest.importorskip("agent_run_supervisor.session")
    optional_on_the_record = {
        field.name
        for field in dataclasses.fields(session.SessionRecord)
        if field.default is None
    }

    nullable_view_keys = {
        "agent_id": "native_agent_id",
        "profile_id": "native_profile_id",
        "created_at": "created_at",
        "updated_at": "updated_at",
        "last_effective_model": "last_effective_model",
        "last_effective_effort": "last_effective_effort",
    }
    for view_key, record_field in nullable_view_keys.items():
        assert record_field in optional_on_the_record, view_key
        view = _validate_session_view(_session_view(**{view_key: None}))
        assert getattr(view, view_key) is None

    # All of them absent at once is still a well-formed view.
    view = _validate_session_view(
        _session_view(**{key: None for key in nullable_view_keys})
    )
    assert view.session_id == REUSE_SESSION_ID
    assert view.owner == "sachima_host"
    assert view.is_reusable is True


def test_session_view_quarantine_blocks_reuse_and_stays_categorical() -> None:
    view = _validate_session_view(
        _session_view(
            quarantine={
                "reason_code": "UNTRUSTED_TERMINAL_EVIDENCE",
                "source_run_id": "private4runid",
                "recorded_at": ACCEPTED_AT,
            }
        )
    )
    assert view.is_reusable is False
    assert view.quarantine_reason_code == "UNTRUSTED_TERMINAL_EVIDENCE"
    rendering = repr(view) + str(view)
    assert "private4runid" not in rendering
    assert REUSE_SESSION_ID not in rendering
    for attr in ("as_dict", "to_dict", "serialize", "to_json"):
        assert not hasattr(view, attr)


@pytest.mark.parametrize(
    "reason_code",
    [
        "DISPATCH_OBSERVATION_LOST",
        "DISPATCH_WITHOUT_TRUSTWORTHY_TERMINAL",
        "UNTRUSTED_TERMINAL_EVIDENCE",
        "SWITCH_ROLLBACK_UNPROVEN",
        "RECONCILED_DISPATCH_WITHOUT_TERMINAL",
    ],
)
def test_session_view_accepts_every_closed_quarantine_reason(reason_code) -> None:
    view = _validate_session_view(
        _session_view(
            quarantine={
                "reason_code": reason_code,
                "source_run_id": "run4abc",
                "recorded_at": ACCEPTED_AT,
            }
        )
    )
    assert view.quarantine_reason_code == reason_code
    assert view.is_reusable is False


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        _session_view(extra=1),
        {k: v for k, v in _session_view().items() if k != "quarantine"},
        _session_view(session_id="sess.dotted"),
        _session_view(session_id=None),
        _session_view(owner=""),
        _session_view(agent_id="bad agent id"),
        _session_view(created_at="not a timestamp"),
        _session_view(updated_at="2026-08-17T10:00:00"),
        _session_view(owner=None),
        _session_view(namespace=None),
        _session_view(last_effective_model="model\nwith\nnewlines"),
        _session_view(quarantine={}),
        _session_view(quarantine={"reason_code": "UNTRUSTED_TERMINAL_EVIDENCE"}),
        _session_view(
            quarantine={
                "reason_code": "NOT_A_REASON",
                "source_run_id": "run4abc",
                "recorded_at": ACCEPTED_AT,
            }
        ),
        _session_view(
            quarantine={
                "reason_code": "UNTRUSTED_TERMINAL_EVIDENCE",
                "source_run_id": "run4abc",
                "recorded_at": ACCEPTED_AT,
                "message": "remote text",
            }
        ),
    ],
)
def test_malformed_session_view_is_a_protocol_violation(payload) -> None:
    with pytest.raises(SpineError) as excinfo:
        _validate_session_view(payload)
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


def test_session_list_accepts_an_empty_session_page() -> None:
    assert _validate_session_list({"sessions": []}) == ()


def test_session_list_validates_every_element_through_the_view_validator() -> None:
    views = _validate_session_list(
        {"sessions": [_session_view(), _session_view(session_id="sess-second")]}
    )
    assert len(views) == 2
    assert views[1].session_id == "sess-second"


@pytest.mark.parametrize(
    "payload",
    [
        _session_view(),
        {"sessions": _session_view()},
        {"sessions": None},
        {"sessions": [], "cursor": None},
        {"records": []},
        {"sessions": [_session_view(), _session_view(quarantine={})]},
        None,
        [],
    ],
    ids=[
        "bare_session_record",
        "sessions_is_a_record",
        "sessions_not_a_list",
        "extra_top_level_key",
        "wrong_top_level_key",
        "bad_element",
        "none",
        "list",
    ],
)
def test_malformed_session_list_is_a_protocol_violation(payload) -> None:
    """R-5: a bare session record at the top level is a protocol violation,
    never a tolerated shape."""

    with pytest.raises(SpineError) as excinfo:
        _validate_session_list(payload)
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


# --------------------------------------------------------------------------- #
# agent_list validator (0.7.8): the live roster of canonical agent ids.
#
# The daemon answers ``{"agent_ids": list(snapshot.ids())}`` and its snapshot
# accessor is ``tuple(sorted(entries))`` — so the wire order is ascending and
# the entries are unique by construction. Both are asserted as *contract*
# here, not as convenience: a reply that is unsorted or repeats an id did not
# come from the accessor this operation is defined by.
# --------------------------------------------------------------------------- #
#: What the deployed daemon actually answered in production.
PRODUCTION_ROSTER = ("claude", "codex", "cursor", "oh-my-pi", "opencode")


def _validate_agent_list(payload):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        validate_arsd_agent_list,
    )

    return validate_arsd_agent_list(payload)


def test_agent_list_accepts_the_observed_production_roster() -> None:
    assert _validate_agent_list({"agent_ids": list(PRODUCTION_ROSTER)}) == (
        PRODUCTION_ROSTER
    )


def test_agent_list_accepts_an_empty_roster() -> None:
    """A daemon that loaded no agent is registered-nothing, not unavailable."""

    assert _validate_agent_list({"agent_ids": []}) == ()


def test_agent_list_ids_match_the_pinned_canonical_grammar() -> None:
    """Drift-lock: the mirrored grammar is the distribution's own."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_AGENT_ID_PATTERN,
    )

    registration = pytest.importorskip(
        "agent_run_supervisor.native_acp.agent_registration"
    )
    assert ARSD_AGENT_ID_PATTERN == registration.AGENT_ID_RE.pattern
    for agent_id in PRODUCTION_ROSTER:
        assert registration.validate_agent_id(agent_id) == agent_id


@pytest.mark.parametrize(
    "payload",
    [
        {"agent_ids": ["codex", "claude"]},
        {"agent_ids": ["claude", "claude"]},
        {"agent_ids": ["Codex"]},
        {"agent_ids": ["codex "]},
        {"agent_ids": [" codex"]},
        {"agent_ids": ["-codex"]},
        {"agent_ids": ["codex\n"]},
        {"agent_ids": ["a" * 65]},
        {"agent_ids": [""]},
        {"agent_ids": [None]},
        {"agent_ids": [123]},
        {"agent_ids": [["codex"]]},
        {"agent_ids": ["codex"], "count": 1},
        {"agent_ids": "codex"},
        {"agent_ids": ("codex",)},
        {"agent_ids": None},
        {"agents": ["codex"]},
        {},
        ["codex"],
        None,
        "codex",
    ],
    ids=[
        "unsorted",
        "duplicate",
        "uppercase",
        "trailing_space",
        "leading_space",
        "leading_hyphen",
        "newline",
        "too_long",
        "empty_id",
        "none_id",
        "int_id",
        "nested_list_id",
        "extra_top_level_key",
        "ids_is_a_string",
        "ids_is_a_tuple",
        "ids_is_none",
        "wrong_top_level_key",
        "empty_mapping",
        "bare_list",
        "none",
        "bare_string",
    ],
)
def test_hostile_or_forged_agent_list_is_a_protocol_violation(payload) -> None:
    """Every deviation is the one stable code, and never echoes the input."""

    with pytest.raises(SpineError) as excinfo:
        _validate_agent_list(payload)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_PROTOCOL_VIOLATION)


def test_agent_list_never_echoes_a_forged_id() -> None:
    forged = "../../etc/passwd codex"
    with pytest.raises(SpineError) as excinfo:
        _validate_agent_list({"agent_ids": [forged]})
    rendered = _rendered_chain(excinfo)
    assert "passwd" not in rendered
    assert forged not in rendered


def test_agent_list_bound_refuses_an_implausible_roster() -> None:
    """A page is bounded: an unbounded roster is a protocol violation.

    The daemon's roster is a startup snapshot of a reviewed registry file, so
    a reply carrying thousands of ids is not a big deployment — it is a reply
    this integration declines to iterate.
    """

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_MAX_REGISTERED_AGENTS,
    )

    ok = [f"agent{index:04d}" for index in range(ARSD_MAX_REGISTERED_AGENTS)]
    assert _validate_agent_list({"agent_ids": ok}) == tuple(ok)

    too_many = ok + [f"agent{ARSD_MAX_REGISTERED_AGENTS:04d}"]
    with pytest.raises(SpineError) as excinfo:
        _validate_agent_list({"agent_ids": too_many})
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_PROTOCOL_VIOLATION)


def test_last_effective_values_are_never_read_back_into_request_construction() -> None:
    """R-5 / §5.5.4: the observations exist on the view and reach nothing.

    A payload built while holding a validated view that reports one pair is
    identical to one built without the view at all — the maps are the only
    source, so an observation cannot become the next Run's configuration.
    """

    view = _validate_session_view(
        _session_view(last_effective_model="claude-opus-5", last_effective_effort="high")
    )
    assert view.last_effective_model == "claude-opus-5"

    config = _two_policy_config()
    with_view = _build_payload(
        config=config,
        session_id=view.session_id,
        model_policy_ref="policy_reader",
        effort_policy_ref="policy_reader",
    )
    assert with_view["request"]["requested_model"] == "claude-sonnet-5"
    assert with_view["request"]["requested_effort"] == "medium"


# --------------------------------------------------------------------------- #
# Admission-product pre-check (Δ-10 / §5.6.2 / A-23): per-field validity does
# not imply admissibility. The negotiated budget is a parameter, so this is
# testable offline against injected budgets.
# --------------------------------------------------------------------------- #
def _check_admission(limits, budget):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        check_arsd_admission_event_budget,
    )

    return check_arsd_admission_event_budget(
        limits, max_run_event_budget_bytes=budget
    )


def test_run_limits_within_per_field_maxima_can_still_fail_the_admission_product() -> None:
    """A-23: the whole point — a structurally valid entry the daemon refuses.

    Every field of ``ceiling`` satisfies its per-field maximum and the config
    admits it; the product ``max_event_bytes * max_events`` nonetheless
    exceeds the negotiated budget, so the pre-check refuses before a submit is
    spent learning it. Omit the pre-check and this fails.
    """

    from sachima_supervisor.runtime_spine.arsd_socket_contract import _RUN_LIMIT_MAX

    ceiling = _limits_with(
        max_event_bytes=_RUN_LIMIT_MAX["max_event_bytes"],
        max_events=_RUN_LIMIT_MAX["max_events"],
    )
    config = _make_config(
        enabled=True, run_limits_by_policy_ref={"policy_reader": ceiling}
    )
    admitted = dict(config.run_limits_by_policy_ref["policy_reader"])
    product = admitted["max_event_bytes"] * admitted["max_events"]

    with pytest.raises(SpineError) as excinfo:
        _check_admission(admitted, NEGOTIATED_EVENT_BUDGET)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)

    # Inclusive at the budget, refused one byte over it.
    _check_admission(admitted, product)
    with pytest.raises(SpineError) as excinfo:
        _check_admission(admitted, product - 1)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)


def test_admission_pre_check_agrees_with_the_real_daemon_policy() -> None:
    """The pre-check is a guard, not a second policy: the real
    ``admit_event_budget`` reaches the same verdict for the same inputs."""

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")

    limits = _limits_with(max_event_bytes=1_048_576, max_events=4096)
    product = limits["max_event_bytes"] * limits["max_events"]

    for budget, admissible in ((product, True), (product - 1, False)):
        policy = spec.EventBudgetPolicy(max_run_event_budget_bytes=budget)
        real_limits = spec.RunLimits(
            **limits, event_budget_policy=spec.STRUCTURAL_EVENT_BUDGET_POLICY
        )
        if admissible:
            protocol.admit_event_budget(real_limits, policy)
            _check_admission(limits, budget)
        else:
            with pytest.raises(protocol.ProtocolError) as protocol_excinfo:
                protocol.admit_event_budget(real_limits, policy)
            assert protocol_excinfo.value.code == protocol.INVALID_REQUEST
            with pytest.raises(SpineError) as excinfo:
                _check_admission(limits, budget)
            _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)


@pytest.mark.parametrize(
    "budget",
    [0, -1, None, "1024", True, 1.5, 1_048_576_000_001],
    ids=[
        "zero",
        "negative",
        "none",
        "string",
        "bool",
        "float",
        "above_structural_maximum",
    ],
)
def test_admission_pre_check_refuses_an_unusable_negotiated_budget(budget) -> None:
    """A budget Sachima cannot trust is not a reason to submit anyway."""

    with pytest.raises(SpineError) as excinfo:
        _check_admission(_limits_with(), budget)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)


def test_admission_pre_check_refuses_an_off_contract_limits_mapping() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import _RUN_LIMIT_KEYS

    partial = {key: 1 for key in sorted(_RUN_LIMIT_KEYS)[:2]}
    for bad_limits in (None, [], {}, partial, {**_limits_with(), "surprise": 1}):
        with pytest.raises(SpineError) as excinfo:
            _check_admission(bad_limits, NEGOTIATED_EVENT_BUDGET)
        _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)


def test_retry_payload_is_byte_equivalent_across_a_changed_negotiated_budget() -> None:
    """A-24 / Δ-12: a retry re-sends the frozen payload unchanged.

    The builder has no negotiated-budget input at all, so a payload built
    after the operator lowered the budget is byte-identical to the original
    and carries the same digest. Re-tuning ``limits`` to fit a new budget
    would break byte-equivalence and earn ``IDEMPOTENCY_CONFLICT``, which
    §7.1 requires Sachima to fail closed on.
    """

    import inspect

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        arsd_submit_payload_digest,
        build_arsd_submit_payload,
        derive_arsd_request_id,
    )

    config = _make_config(enabled=True)
    original = _build_payload(config=config)
    original_digest = arsd_submit_payload_digest(original)

    # The negotiated budget moves between submit and retry (two different
    # valid negotiations); the frozen payload does not.
    high = _validate_server_info(
        _server_info_payload(**_limits_override(max_run_event_budget_bytes=2**31))
    )
    low = _validate_server_info(
        _server_info_payload(**_limits_override(max_run_event_budget_bytes=2**20))
    )
    assert high.max_run_event_budget_bytes != low.max_run_event_budget_bytes

    retry = _build_payload(config=config)
    assert retry == original
    assert arsd_submit_payload_digest(retry) == original_digest

    request_id = derive_arsd_request_id("task_alpha", "sess_alpha", "dispatch_0001")
    assert (
        derive_arsd_request_id("task_alpha", "sess_alpha", "dispatch_0001") == request_id
    )

    # Structural proof that no budget can reach the builder in the first
    # place: not as a parameter, and not as a name its code touches.
    parameters = inspect.signature(build_arsd_submit_payload).parameters
    assert not [name for name in parameters if "budget" in name]
    code = build_arsd_submit_payload.__code__
    touched = set(code.co_names) | set(code.co_varnames)
    assert not [name for name in touched if "budget" in name]


# --------------------------------------------------------------------------- #
# R-4 discard witness: ``MAX_ERROR_MESSAGE_CHARS`` is mirrored and has exactly
# one real consumer — the proof that a remote message at the true wire maximum
# reaches no Sachima surface at all.
# --------------------------------------------------------------------------- #
def test_remote_error_message_at_the_contract_maximum_is_fully_discarded() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_MAX_ERROR_MESSAGE_CHARS,
        map_arsd_client_error_code,
    )

    marker = "LEAKMARKER7d9f"
    message = (marker * (ARSD_MAX_ERROR_MESSAGE_CHARS // len(marker) + 1))[
        :ARSD_MAX_ERROR_MESSAGE_CHARS
    ]
    assert len(message) == ARSD_MAX_ERROR_MESSAGE_CHARS

    class _RemoteError(Exception):
        def __init__(self) -> None:
            super().__init__(message)
            self.code = "OWNER_MISMATCH"

    try:
        raise SpineError(map_arsd_client_error_code(_RemoteError().code)) from None
    except SpineError as err:
        rendered = (
            repr(err)
            + str(err)
            + repr(err.args)
            + "".join(traceback.format_exception(err))
        )
    assert marker not in rendered
    assert message not in rendered
    assert rendered.count("runtime_arsd_policy_denied") >= 1


# --------------------------------------------------------------------------- #
# run_events page validator (plan §7.1/§7.3): bounded pagination, foreign
# cursor translation, truncation-marker preservation.
# --------------------------------------------------------------------------- #
EVENT_BODY_CANARY = "raw model text canary — never in any repr"


def _validate_page(payload, *, run_id="run4abc", from_seq=0):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        validate_arsd_run_events_page,
    )

    return validate_arsd_run_events_page(payload, run_id=run_id, from_seq=from_seq)


def test_run_events_page_translates_the_foreign_cursor() -> None:
    page = _validate_page(
        {
            "run_id": "run4abc",
            "events": [
                {"seq": 5, "type": "agent_message_chunk", "text": EVENT_BODY_CANARY},
                {"seq": 7, "type": "turn_completed"},
            ],
            "next_from_seq": 7,
            "exhausted": False,
        },
        from_seq=4,
    )
    assert page.resume_cursor == 7
    assert page.has_more is True
    assert page.exhausted is False
    assert len(page.events) == 2
    assert page.events[0]["seq"] == 5
    assert page.has_truncation_marker is False


def test_run_events_empty_page_keeps_the_request_cursor() -> None:
    page = _validate_page(
        {"run_id": "run4abc", "events": [], "next_from_seq": 9, "exhausted": True},
        from_seq=9,
    )
    assert page.resume_cursor == 9
    assert page.has_more is False
    assert page.events == ()


def test_run_events_truncation_marker_page_shape_is_preserved() -> None:
    """A byte-budget page: one closed marker event and ``exhausted=False``."""

    marker = {
        "seq": 12,
        "type": "agent_message_chunk",
        "truncated": True,
        "truncate_reason": "response_budget",
    }
    page = _validate_page(
        {
            "run_id": "run4abc",
            "events": [marker],
            "next_from_seq": 12,
            "exhausted": False,
        },
        from_seq=11,
    )
    assert page.has_truncation_marker is True
    assert page.has_more is True
    assert page.resume_cursor == 12
    assert dict(page.events[0]) == marker


def test_run_events_marker_with_exhausted_true_is_off_contract() -> None:
    marker = {
        "seq": 12,
        "type": "agent_message_chunk",
        "truncated": True,
        "truncate_reason": "response_budget",
    }
    with pytest.raises(SpineError) as excinfo:
        _validate_page(
            {
                "run_id": "run4abc",
                "events": [marker],
                "next_from_seq": 12,
                "exhausted": True,
            },
            from_seq=11,
        )
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


@pytest.mark.parametrize(
    "payload,from_seq",
    [
        (None, 0),
        ([], 0),
        ({}, 0),
        ({"run_id": "other", "events": [], "next_from_seq": 0, "exhausted": True}, 0),
        ({"run_id": "run4abc", "events": [], "next_from_seq": 0}, 0),
        ({"run_id": "run4abc", "events": [], "next_from_seq": 0, "exhausted": True,
          "follow": True}, 0),
        ({"run_id": "run4abc", "events": {}, "next_from_seq": 0, "exhausted": True}, 0),
        ({"run_id": "run4abc", "events": [7], "next_from_seq": 0, "exhausted": True}, 0),
        ({"run_id": "run4abc", "events": [{"type": "x"}], "next_from_seq": 0,
          "exhausted": True}, 0),
        ({"run_id": "run4abc", "events": [{"seq": True, "type": "x"}],
          "next_from_seq": 1, "exhausted": True}, 0),
        ({"run_id": "run4abc", "events": [{"seq": 3, "type": "x"}],
          "next_from_seq": 3, "exhausted": True}, 3),
        ({"run_id": "run4abc", "events": [{"seq": 5, "type": "x"}, {"seq": 5, "type": "y"}],
          "next_from_seq": 5, "exhausted": True}, 0),
        ({"run_id": "run4abc", "events": [{"seq": 7, "type": "x"}, {"seq": 5, "type": "y"}],
          "next_from_seq": 5, "exhausted": True}, 0),
        ({"run_id": "run4abc", "events": [{"seq": 5, "type": "x"}],
          "next_from_seq": 9, "exhausted": True}, 0),
        ({"run_id": "run4abc", "events": [], "next_from_seq": 4, "exhausted": True}, 9),
        ({"run_id": "run4abc", "events": [], "next_from_seq": 9, "exhausted": "yes"}, 9),
    ],
)
def test_malformed_run_events_page_is_a_protocol_violation(payload, from_seq) -> None:
    with pytest.raises(SpineError) as excinfo:
        _validate_page(payload, from_seq=from_seq)
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


def test_run_events_unserializable_event_body_fails_closed_without_chaining() -> None:
    """A copy/conversion failure on a remote event body is the stable
    protocol-violation code — no ``TypeError`` chain, no evidence rendering."""

    payload = {
        "run_id": "run4abc",
        "events": [{"seq": 5, "type": "x", "blob": b"raw-bytes-evidence-canary"}],
        "next_from_seq": 5,
        "exhausted": True,
    }
    with pytest.raises(SpineError) as excinfo:
        _validate_page(payload)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_PROTOCOL_VIOLATION)
    rendered = _rendered_chain(excinfo)
    assert "canary" not in rendered
    assert "JSON serializable" not in rendered
    assert "TypeError" not in rendered


def test_run_events_pathological_event_nesting_is_a_stable_violation() -> None:
    """A depth bomb in a remote event body must surface the stable code —
    never a raw ``RecursionError`` escaping the validation boundary."""

    deep: dict = {"leaf": "raw-depth-canary"}
    for _ in range(100_000):
        deep = {"d": deep}
    payload = {
        "run_id": "run4abc",
        "events": [{"seq": 5, "type": "x", "body": deep}],
        "next_from_seq": 5,
        "exhausted": True,
    }
    with pytest.raises(SpineError) as excinfo:
        _validate_page(payload)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_PROTOCOL_VIOLATION)
    rendered = _rendered_chain(excinfo)
    assert "canary" not in rendered
    assert "recursion" not in rendered.lower()


def test_run_events_page_never_leaks_event_bodies() -> None:
    """Raw event evidence is private: absent from repr, no serialize surface."""

    page = _validate_page(
        {
            "run_id": "run4abc",
            "events": [
                {"seq": 5, "type": "agent_message_chunk", "text": EVENT_BODY_CANARY}
            ],
            "next_from_seq": 5,
            "exhausted": True,
        }
    )
    rendering = repr(page) + str(page)
    assert EVENT_BODY_CANARY not in rendering
    assert "run4abc" not in rendering
    for attr in ("as_dict", "to_dict", "serialize", "to_json"):
        assert not hasattr(page, attr)


# --------------------------------------------------------------------------- #
# Fake-socket contract tests (plan D1): the production facade + the REAL
# official ArsdClient against a hermetic in-test AF_UNIX server. No daemon.
# --------------------------------------------------------------------------- #
import json as _json
import shutil as _shutil
import socket as _socket
import tempfile as _tempfile
import threading as _threading


class _FakeArsdServer:
    """Minimal scripted NDJSON server on a throwaway AF_UNIX socket.

    One request frame per connection (mirroring the short-lived-client
    contract), replies via the injected handler, records every parsed request
    envelope and counts accepted connections. Owned entirely by the test —
    this is a fixture, not a daemon.
    """

    def __init__(self, handler) -> None:
        self._handler = handler
        self._dir = _tempfile.mkdtemp(prefix="arsd-fs-")
        self.socket_path = self._dir + "/s.sock"
        self.received: list[dict] = []
        self.connections = 0
        self._stop = _threading.Event()
        self._sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        self._sock.bind(self.socket_path)
        self._sock.listen(8)
        self._sock.settimeout(0.2)
        self._thread = _threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                continue
            self.connections += 1
            with conn:
                conn.settimeout(5.0)
                try:
                    buf = bytearray()
                    while b"\n" not in buf:
                        chunk = conn.recv(65_536)
                        if not chunk:
                            break
                        buf.extend(chunk)
                    if b"\n" not in buf:
                        continue
                    line, _, _ = bytes(buf).partition(b"\n")
                    envelope = _json.loads(line.decode("utf-8"))
                    self.received.append(envelope)
                    reply = self._handler(envelope)
                    if reply is not None:
                        conn.sendall(reply)
                except OSError:
                    continue

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5.0)
        self._sock.close()
        _shutil.rmtree(self._dir, ignore_errors=True)


@pytest.fixture
def fake_arsd_server():
    servers: list[_FakeArsdServer] = []

    def _start(handler) -> _FakeArsdServer:
        server = _FakeArsdServer(handler)
        servers.append(server)
        return server

    yield _start
    for server in servers:
        server.stop()


def _result_frame(request_id, result) -> bytes:
    return (_json.dumps({"request_id": request_id, "result": result}) + "\n").encode()


def _error_frame(request_id, code, message) -> bytes:
    return (
        _json.dumps(
            {"request_id": request_id, "error": {"code": code, "message": message}}
        )
        + "\n"
    ).encode()


def _facade_for(server, **config_overrides):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        DefaultArsdClientFacade,
    )

    config = _make_config(
        enabled=True, socket_path=server.socket_path, **config_overrides
    )
    return DefaultArsdClientFacade(config)


def test_default_facade_requires_an_enabled_config() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        DefaultArsdClientFacade,
        RUNTIME_ARSD_DISABLED,
    )

    with pytest.raises(SpineError) as excinfo:
        DefaultArsdClientFacade(_make_config())
    assert excinfo.value.code == RUNTIME_ARSD_DISABLED


def test_default_facade_satisfies_the_injected_boundary() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ArsdClientFacade,
        DefaultArsdClientFacade,
    )

    assert issubclass(DefaultArsdClientFacade, ArsdClientFacade)


def test_facade_surface_is_every_operation_this_integration_uses() -> None:
    """The facade gains ``run_status``/``run_cancel``/``session_status``/
    ``session_list``/``agent_list``. There is no ``session_close`` — the
    operation does not exist in v3 — and no ``follow`` path."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_OPERATIONS,
        DefaultArsdClientFacade,
    )

    exposed = {
        name
        for name in ARSD_OPERATIONS
        if callable(getattr(DefaultArsdClientFacade, name, None))
    }
    assert exposed == set(ARSD_OPERATIONS)
    assert not hasattr(DefaultArsdClientFacade, "session_close")
    assert not hasattr(DefaultArsdClientFacade, "run_events_follow")


def test_every_added_operation_uses_one_short_lived_connection(
    fake_arsd_server,
) -> None:
    """P1-e: the added read operations keep the existing per-operation
    lifecycle — one fresh client, one roundtrip, one close."""

    replies = {
        "run_status": {"run_id": "run4abc", "session_id": REUSE_SESSION_ID},
        "run_cancel": {"run_id": "run4abc"},
        "session_status": _session_view(),
        "session_list": {"sessions": []},
        "agent_list": {"agent_ids": list(PRODUCTION_ROSTER)},
    }
    server = fake_arsd_server(
        lambda envelope: _result_frame(
            envelope["request_id"], replies[envelope["op"]]
        )
    )
    facade = _facade_for(server)

    assert facade.run_status("run4abc")["run_id"] == "run4abc"
    assert facade.run_cancel("run4abc")["run_id"] == "run4abc"
    assert facade.session_status(REUSE_SESSION_ID)["session_id"] == REUSE_SESSION_ID
    assert facade.session_list() == {"sessions": []}
    assert facade.agent_list() == {"agent_ids": list(PRODUCTION_ROSTER)}

    assert server.connections == 5
    assert [env["op"] for env in server.received] == [
        "run_status",
        "run_cancel",
        "session_status",
        "session_list",
        "agent_list",
    ]
    assert all(env["api_version"] == 3 for env in server.received)
    # A roster read carries no arguments: an empty payload, like the daemon's
    # own ``_PAYLOAD_FIELDS["agent_list"] == frozenset()``.
    assert server.received[-1]["payload"] == {}


def test_facade_construction_never_connects(fake_arsd_server) -> None:
    """Composing the facade is not a daemon probe (plan §10: zero submits)."""

    server = fake_arsd_server(lambda envelope: None)
    _facade_for(server)
    assert server.connections == 0


def test_v3_negotiation_roundtrip_over_the_wire(fake_arsd_server) -> None:
    """server_info over real client + fake socket, validated exactly."""

    server = fake_arsd_server(
        lambda envelope: _result_frame(envelope["request_id"], _server_info_payload())
    )
    facade = _facade_for(server)
    info = _validate_server_info(
        facade.server_info(), config=_make_config(enabled=True)
    )
    assert info.version == "0.7.8"
    assert server.received[0]["op"] == "server_info"
    assert server.received[0]["api_version"] == 3
    assert server.received[0]["payload"] == {}


def test_each_bounded_operation_uses_a_short_lived_connection(
    fake_arsd_server,
) -> None:
    server = fake_arsd_server(
        lambda envelope: _result_frame(envelope["request_id"], _server_info_payload())
    )
    facade = _facade_for(server)
    facade.server_info()
    facade.server_info()
    facade.server_info()
    assert server.connections == 3


def test_submit_retry_reuses_identical_request_identity_and_bytes(
    fake_arsd_server,
) -> None:
    """Plan §6.1: a retry is the same request_id and byte-equivalent payload."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        arsd_submit_payload_digest,
        derive_arsd_request_id,
    )

    server = fake_arsd_server(
        lambda envelope: _result_frame(
            envelope["request_id"], _submit_ack(run_id="run4abc")
        )
    )
    facade = _facade_for(server)
    config = _make_config(enabled=True, socket_path=server.socket_path)
    request_id = derive_arsd_request_id("task_alpha", "sess_alpha", "dispatch_0001")

    first = _validate_submit(
        facade.submit(request_id=request_id, payload=_build_payload(config=config))
    )
    second = _validate_submit(
        facade.submit(request_id=request_id, payload=_build_payload(config=config))
    )

    assert first.run_id == second.run_id == "run4abc"
    assert first.session_id == second.session_id == REUSE_SESSION_ID
    assert [env["request_id"] for env in server.received] == [request_id, request_id]
    assert server.received[0]["op"] == "submit"
    wire_digests = {
        arsd_submit_payload_digest(env["payload"]) for env in server.received
    }
    assert len(wire_digests) == 1


def test_idempotency_conflict_fails_closed_without_resubmission(
    fake_arsd_server,
) -> None:
    """A digest conflict surfaces the stable code; no new id is generated."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        RUNTIME_ARSD_IDEMPOTENCY_CONFLICT,
        derive_arsd_request_id,
    )

    server = fake_arsd_server(
        lambda envelope: _error_frame(
            envelope["request_id"],
            "IDEMPOTENCY_CONFLICT",
            "remote conflict detail that must never surface",
        )
    )
    facade = _facade_for(server)
    config = _make_config(enabled=True, socket_path=server.socket_path)
    request_id = derive_arsd_request_id("task_alpha", "sess_alpha", "dispatch_0001")

    with pytest.raises(SpineError) as excinfo:
        facade.submit(request_id=request_id, payload=_build_payload(config=config))
    assert excinfo.value.code == RUNTIME_ARSD_IDEMPOTENCY_CONFLICT
    assert len(server.received) == 1
    rendering = repr(excinfo.value) + str(excinfo.value)
    assert "remote conflict detail" not in rendering


def test_pagination_over_the_wire_including_truncation_marker(
    fake_arsd_server,
) -> None:
    pages = {
        0: {
            "run_id": "run4abc",
            "events": [
                {"seq": 1, "type": "agent_message_chunk", "text": EVENT_BODY_CANARY},
                {"seq": 2, "type": "tool_call"},
            ],
            "next_from_seq": 2,
            "exhausted": False,
        },
        2: {
            "run_id": "run4abc",
            "events": [
                {
                    "seq": 3,
                    "type": "agent_message_chunk",
                    "truncated": True,
                    "truncate_reason": "response_budget",
                }
            ],
            "next_from_seq": 3,
            "exhausted": False,
        },
        3: {
            "run_id": "run4abc",
            "events": [],
            "next_from_seq": 3,
            "exhausted": True,
        },
    }

    def _handler(envelope):
        page = pages[envelope["payload"]["from_seq"]]
        return _result_frame(envelope["request_id"], page)

    server = fake_arsd_server(_handler)
    facade = _facade_for(server)

    first = _validate_page(facade.run_events("run4abc", from_seq=0, limit=64))
    assert first.has_more is True and first.has_truncation_marker is False

    second = _validate_page(
        facade.run_events("run4abc", from_seq=first.resume_cursor, limit=64),
        from_seq=first.resume_cursor,
    )
    assert second.has_truncation_marker is True
    assert second.has_more is True

    final = _validate_page(
        facade.run_events("run4abc", from_seq=second.resume_cursor, limit=64),
        from_seq=second.resume_cursor,
    )
    assert final.has_more is False
    assert final.events == ()

    seen = [
        event["seq"]
        for page in (first, second, final)
        for event in page.events
    ]
    assert seen == sorted(set(seen)) == [1, 2, 3]

    for envelope in server.received:
        assert envelope["payload"]["follow"] is False


def test_facade_never_issues_a_follow_subscription(fake_arsd_server) -> None:
    """D1 is bounded pagination only — no resident follow loop exists."""

    server = fake_arsd_server(
        lambda envelope: _result_frame(
            envelope["request_id"],
            {"run_id": "run4abc", "events": [], "next_from_seq": 0, "exhausted": True},
        )
    )
    facade = _facade_for(server)
    facade.run_events("run4abc", from_seq=0, limit=8)
    assert all(env["payload"]["follow"] is False for env in server.received)
    assert not hasattr(facade, "run_events_follow")


@pytest.mark.parametrize(
    "reply,expected_code_name",
    [
        (b"this is not json\n", "RUNTIME_ARSD_PROTOCOL_VIOLATION"),
        (b"[1, 2, 3]\n", "RUNTIME_ARSD_PROTOCOL_VIOLATION"),
        ("mismatched", "RUNTIME_ARSD_PROTOCOL_VIOLATION"),
        ("result_not_dict", "RUNTIME_ARSD_PROTOCOL_VIOLATION"),
        (b"x" * 1_200_000 + b"\n", "RUNTIME_ARSD_PROTOCOL_VIOLATION"),
        ("unknown_error_code", "RUNTIME_ARSD_INTERNAL"),
        ("unsupported_api_version", "RUNTIME_ARSD_VERSION_MISMATCH"),
    ],
)
def test_malformed_replies_map_to_stable_codes(
    fake_arsd_server, reply, expected_code_name
) -> None:
    import sachima_supervisor.runtime_spine.arsd_socket_contract as contract

    def _handler(envelope):
        if reply == "mismatched":
            return _result_frame("someone-else", _server_info_payload())
        if reply == "result_not_dict":
            return (
                _json.dumps(
                    {"request_id": envelope["request_id"], "result": [1, 2]}
                )
                + "\n"
            ).encode()
        if reply == "unknown_error_code":
            return _error_frame(envelope["request_id"], "TOTALLY_NEW", "x")
        if reply == "unsupported_api_version":
            return _error_frame(
                envelope["request_id"], "UNSUPPORTED_API_VERSION", "x"
            )
        return reply

    server = fake_arsd_server(_handler)
    facade = _facade_for(server)
    with pytest.raises(SpineError) as excinfo:
        facade.server_info()
    assert excinfo.value.code == getattr(contract, expected_code_name)


def test_disconnect_before_reply_is_internal_not_a_run_verdict(
    fake_arsd_server,
) -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        RUNTIME_ARSD_INTERNAL,
    )

    server = fake_arsd_server(lambda envelope: None)
    facade = _facade_for(server)
    with pytest.raises(SpineError) as excinfo:
        facade.server_info()
    assert excinfo.value.code == RUNTIME_ARSD_INTERNAL


def test_mid_frame_disconnect_is_a_protocol_violation(fake_arsd_server) -> None:
    server = fake_arsd_server(lambda envelope: b'{"request_id": "trunca')
    facade = _facade_for(server)
    with pytest.raises(SpineError) as excinfo:
        facade.server_info()
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


# --------------------------------------------------------------------------- #
# Operation-aware transport-loss mapping (formal review blocker 3): once a
# submit frame may have been sent, losing the transport before a complete
# reply is SUBMISSION-INDETERMINATE — never INTERNAL and never auto-retried.
# Read-type operations and daemon-declared verdicts keep their mapping.
# --------------------------------------------------------------------------- #
def _submit_over(server):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        derive_arsd_request_id,
    )

    facade = _facade_for(server)
    config = _make_config(enabled=True, socket_path=server.socket_path)
    request_id = derive_arsd_request_id("task_alpha", "sess_alpha", "dispatch_0001")
    return facade.submit(request_id=request_id, payload=_build_payload(config=config))


def test_submit_close_before_reply_is_submission_indeterminate(
    fake_arsd_server,
) -> None:
    """The fake server RECEIVES the submit frame and closes without replying:
    the daemon may already hold the run, so the stable verdict is
    indeterminate — and exactly one frame was sent (no retry, no replay)."""

    server = fake_arsd_server(lambda envelope: None)
    with pytest.raises(SpineError) as excinfo:
        _submit_over(server)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_SUBMISSION_INDETERMINATE)
    assert [env["op"] for env in server.received] == ["submit"]
    assert server.connections == 1


def test_submit_reply_truncated_by_connection_loss_is_submission_indeterminate(
    fake_arsd_server,
) -> None:
    """Transport loss mid-reply after the submit frame was received is the
    same indeterminate outcome — the run may exist server-side."""

    server = fake_arsd_server(lambda envelope: b'{"request_id": "trunca')
    with pytest.raises(SpineError) as excinfo:
        _submit_over(server)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_SUBMISSION_INDETERMINATE)
    assert [env["op"] for env in server.received] == ["submit"]


def test_submit_connect_phase_failure_stays_unavailable(tmp_path) -> None:
    """Positive control: before any frame can have been sent there is nothing
    indeterminate — a dead socket is the plain backend-unavailable code."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        DefaultArsdClientFacade,
        derive_arsd_request_id,
    )

    dead_path = str(tmp_path / "never-bound.sock")
    config = _make_config(enabled=True, socket_path=dead_path)
    facade = DefaultArsdClientFacade(config)
    with pytest.raises(SpineError) as excinfo:
        facade.submit(
            request_id=derive_arsd_request_id(
                "task_alpha", "sess_alpha", "dispatch_0001"
            ),
            payload=_build_payload(config=config),
        )
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_UNAVAILABLE)


def test_submit_daemon_declared_verdicts_keep_their_mapping(
    fake_arsd_server,
) -> None:
    """Positive control: a daemon that REPLIES with a typed error keeps the
    daemon-declared mapping — INTERNAL stays internal (not indeterminate) and
    the daemon's own SUBMISSION_INDETERMINATE still maps to indeterminate."""

    internal = fake_arsd_server(
        lambda envelope: _error_frame(envelope["request_id"], "INTERNAL", "x")
    )
    with pytest.raises(SpineError) as excinfo:
        _submit_over(internal)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INTERNAL)

    declared = fake_arsd_server(
        lambda envelope: _error_frame(
            envelope["request_id"], "SUBMISSION_INDETERMINATE", "x"
        )
    )
    with pytest.raises(SpineError) as excinfo:
        _submit_over(declared)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_SUBMISSION_INDETERMINATE)


def test_read_operation_disconnect_semantics_are_unchanged(
    fake_arsd_server,
) -> None:
    """Positive control: close-before-reply on a read-type operation stays
    INTERNAL and a truncated read reply stays a protocol violation — the
    indeterminate verdict is exclusive to submit."""

    dropped = fake_arsd_server(lambda envelope: None)
    with pytest.raises(SpineError) as excinfo:
        _facade_for(dropped).run_events("run4abc", from_seq=0, limit=8)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INTERNAL)

    truncated = fake_arsd_server(lambda envelope: b'{"request_id": "trunca')
    with pytest.raises(SpineError) as excinfo:
        _facade_for(truncated).run_events("run4abc", from_seq=0, limit=8)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_PROTOCOL_VIOLATION)


def test_connect_failure_is_backend_unavailable_and_leak_free(tmp_path) -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        DefaultArsdClientFacade,
        RUNTIME_ARSD_UNAVAILABLE,
    )

    dead_path = str(tmp_path / "never-bound.sock")
    config = _make_config(enabled=True, socket_path=dead_path)
    facade = DefaultArsdClientFacade(config)
    with pytest.raises(SpineError) as excinfo:
        facade.server_info()
    assert excinfo.value.code == RUNTIME_ARSD_UNAVAILABLE
    rendering = repr(excinfo.value) + str(excinfo.value) + repr(excinfo.value.args)
    assert dead_path not in rendering
    assert "never-bound" not in rendering


def test_fresh_connection_after_loss_no_silent_retry(fake_arsd_server) -> None:
    """After a disconnect error the next op succeeds on a fresh connection —
    and the failed op was never replayed behind the caller's back."""

    state = {"first": True}

    def _handler(envelope):
        if state["first"]:
            state["first"] = False
            return None
        return _result_frame(envelope["request_id"], _server_info_payload())

    server = fake_arsd_server(_handler)
    facade = _facade_for(server)

    with pytest.raises(SpineError):
        facade.server_info()
    info = _validate_server_info(
        facade.server_info(), config=_make_config(enabled=True)
    )
    assert info.api_version == 3
    assert server.connections == 2
    assert [env["op"] for env in server.received] == ["server_info", "server_info"]


def test_facade_rejects_invalid_local_inputs_before_any_connection(
    fake_arsd_server,
) -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        RUNTIME_ARSD_INVALID_REQUEST,
    )

    server = fake_arsd_server(
        lambda envelope: _result_frame(envelope["request_id"], {})
    )
    facade = _facade_for(server)
    for call in (
        lambda: facade.submit(request_id="bad id!", payload={"request": {}}),
        lambda: facade.submit(request_id="", payload={"request": {}}),
        lambda: facade.submit(request_id="ok-id", payload="not a mapping"),
        lambda: facade.run_events("bad run!", from_seq=0, limit=8),
        lambda: facade.run_events("run4abc", from_seq=-1, limit=8),
        lambda: facade.run_events("run4abc", from_seq=True, limit=8),
        lambda: facade.run_events("run4abc", from_seq=0, limit=0),
        lambda: facade.run_events("run4abc", from_seq=0, limit=True),
        lambda: facade.run_status("bad run!"),
        lambda: facade.run_status(7),
        lambda: facade.run_cancel("bad run!"),
        lambda: facade.run_cancel(None),
        lambda: facade.session_status("sess.dotted"),
        lambda: facade.session_status(""),
        lambda: facade.session_status(None),
    ):
        with pytest.raises(SpineError) as excinfo:
            call()
        assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST
    assert server.connections == 0


# --------------------------------------------------------------------------- #
# Facade lifecycle over a scripted client double: one guarded construct/
# connect/operate/cleanup path — close() is attempted for every constructed
# client, close failures surface as the stable local code, and an already
# active stable error is never masked (or chained) by cleanup.
# --------------------------------------------------------------------------- #
import types as _types

_SCRIPTED_DETAIL_CANARY = "scripted-client-detail-7f3a must never surface"


class _ScriptedClientError(Exception):
    """Double of the official client error: a code plus private detail text."""

    def __init__(self, code: str) -> None:
        super().__init__(_SCRIPTED_DETAIL_CANARY)
        self.code = code


def _install_scripted_client(
    monkeypatch,
    *,
    construct_error=None,
    connect_error=None,
    operate=None,
    close_error=None,
):
    """Install a scripted ``agent_run_supervisor.arsd.client`` double and
    return its lifecycle call log. ``operate`` is the ``server_info``
    behaviour: an exception instance to raise, else the mapping to return."""

    calls: list[str] = []

    class _ScriptedClient:
        def __init__(self, socket_path) -> None:
            calls.append("construct")
            if construct_error is not None:
                raise construct_error

        def connect(self) -> None:
            calls.append("connect")
            if connect_error is not None:
                raise connect_error

        def server_info(self):
            calls.append("server_info")
            if isinstance(operate, BaseException):
                raise operate
            return operate

        def close(self) -> None:
            calls.append("close")
            if close_error is not None:
                raise close_error

    module = _types.SimpleNamespace(
        ArsdClient=_ScriptedClient, ArsdClientError=_ScriptedClientError
    )
    monkeypatch.setitem(sys.modules, "agent_run_supervisor.arsd.client", module)
    return calls


def _scripted_facade():
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        DefaultArsdClientFacade,
    )

    return DefaultArsdClientFacade(_make_config(enabled=True))


def test_construction_failure_is_stable_unavailable_and_leak_free(
    monkeypatch,
) -> None:
    calls = _install_scripted_client(
        monkeypatch, construct_error=RuntimeError(_SCRIPTED_DETAIL_CANARY)
    )
    facade = _scripted_facade()
    with pytest.raises(SpineError) as excinfo:
        facade.server_info()
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_UNAVAILABLE)
    assert _SCRIPTED_DETAIL_CANARY not in repr(excinfo.value) + str(excinfo.value)
    assert calls == ["construct"]


def test_connect_failure_still_closes_the_constructed_client(monkeypatch) -> None:
    calls = _install_scripted_client(
        monkeypatch, connect_error=RuntimeError(_SCRIPTED_DETAIL_CANARY)
    )
    facade = _scripted_facade()
    with pytest.raises(SpineError) as excinfo:
        facade.server_info()
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_UNAVAILABLE)
    assert calls == ["construct", "connect", "close"]


def test_connect_failure_keeps_unavailable_even_if_close_also_fails(
    monkeypatch,
) -> None:
    calls = _install_scripted_client(
        monkeypatch,
        connect_error=RuntimeError(_SCRIPTED_DETAIL_CANARY),
        close_error=RuntimeError(_SCRIPTED_DETAIL_CANARY),
    )
    facade = _scripted_facade()
    with pytest.raises(SpineError) as excinfo:
        facade.server_info()
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_UNAVAILABLE)
    assert calls == ["construct", "connect", "close"]


def test_close_failure_after_success_is_stable_unavailable_not_raw(
    monkeypatch,
) -> None:
    calls = _install_scripted_client(
        monkeypatch,
        operate=_server_info_payload(),
        close_error=RuntimeError(_SCRIPTED_DETAIL_CANARY),
    )
    facade = _scripted_facade()
    with pytest.raises(SpineError) as excinfo:
        facade.server_info()
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_UNAVAILABLE)
    rendering = repr(excinfo.value) + str(excinfo.value) + repr(excinfo.value.args)
    assert _SCRIPTED_DETAIL_CANARY not in rendering
    assert calls == ["construct", "connect", "server_info", "close"]


@pytest.mark.parametrize(
    "operate,expected_code",
    [
        (_ScriptedClientError("SESSION_BUSY"), RUNTIME_ARSD_BUSY),
        (SpineError(RUNTIME_ARSD_PROTOCOL_VIOLATION), RUNTIME_ARSD_PROTOCOL_VIOLATION),
    ],
)
def test_close_failure_never_masks_an_active_stable_error(
    monkeypatch, operate, expected_code
) -> None:
    calls = _install_scripted_client(
        monkeypatch,
        operate=operate,
        close_error=RuntimeError(_SCRIPTED_DETAIL_CANARY),
    )
    facade = _scripted_facade()
    with pytest.raises(SpineError) as excinfo:
        facade.server_info()
    _assert_stable_code_only(excinfo, expected_code)
    rendering = repr(excinfo.value) + str(excinfo.value) + repr(excinfo.value.args)
    assert _SCRIPTED_DETAIL_CANARY not in rendering
    assert calls == ["construct", "connect", "server_info", "close"]


# --------------------------------------------------------------------------- #
# Package surface: the D1 contract is exported like every other spine module.
# --------------------------------------------------------------------------- #
def test_runtime_spine_package_exports_the_d1_contract_surface() -> None:
    import sachima_supervisor.runtime_spine as spine

    for name in (
        "ARSD_STABLE_CODES",
        "ARSD_SUPERVISOR_CONFIG_TYPE",
        "ArsdClientFacade",
        "ArsdRunEventsPage",
        "ArsdServerInfo",
        "ArsdSubmitAccepted",
        "ArsdSupervisorConfig",
        "DefaultArsdClientFacade",
        "arsd_submit_payload_digest",
        "build_arsd_submit_payload",
        "derive_arsd_request_id",
        "map_arsd_client_error_code",
        "require_enabled_arsd_supervisor_config",
        "validate_arsd_run_events_page",
        "validate_arsd_server_info",
        "validate_arsd_submit_result",
        "validate_arsd_supervisor_config",
    ):
        assert hasattr(spine, name), name
        assert name in spine.__all__, name


# --------------------------------------------------------------------------- #
# Bounded terminal projection (Milestone A, task 7): the four fields ARS 0.7.6
# already returns — status, final_message, truncated, truncate_reason — and
# nothing else. No artifact browsing, no API change, no rehydrate.
# --------------------------------------------------------------------------- #
FINAL_MESSAGE_CANARY = "the delegated agent finished and reported this"
RUN_DIR_CANARY = "/tmp/sachima-canary-terminal/private-run-dir"


def _project_terminal(result, *, status="completed"):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        project_arsd_terminal_result,
    )

    return project_arsd_terminal_result(result, status=status)


def _native_terminal_body(**overrides):
    """A trusted 0.7.6 ``result.json`` body, as ``run_status`` returns it."""

    body = {
        "run_id": "RUN-canary-terminal",
        "status": "completed",
        "business_verdict": None,
        "error_code": None,
        "detail_code": None,
        "origin": "acp",
        "retryable": False,
        "signal": None,
        "stop_reason": "end_turn",
        "usage": None,
        "final_message": FINAL_MESSAGE_CANARY,
        "truncated": False,
        "truncate_reason": None,
        "observed_effect": True,
        "run_dir": RUN_DIR_CANARY,
        "stderr_path": "stderr.log",
        "raw_event_path": "raw.jsonl",
        "redaction_report_path": "redaction-report.json",
    }
    body.update(overrides)
    return body


def test_terminal_projection_carries_the_bounded_final_message() -> None:
    projected = _project_terminal(_native_terminal_body())
    assert projected.status == "completed"
    assert projected.final_message == FINAL_MESSAGE_CANARY
    assert projected.truncated is False
    assert projected.truncate_reason is None


def test_terminal_projection_is_exactly_four_fields() -> None:
    """A projection that grew a fifth field is one that started browsing."""

    import dataclasses

    from sachima_supervisor.runtime_spine.arsd_socket_contract import ArsdTerminalResult

    names = [f.name for f in dataclasses.fields(ArsdTerminalResult)]
    assert names == ["status", "final_message", "truncated", "truncate_reason"]


def test_terminal_projection_never_carries_private_run_material() -> None:
    projected = _project_terminal(_native_terminal_body())
    rendered = repr(projected) + str(projected)
    assert RUN_DIR_CANARY not in rendered
    assert "RUN-canary-terminal" not in rendered
    # The free-form message is the payload, not a repr surface.
    assert FINAL_MESSAGE_CANARY not in repr(projected)


def test_terminal_projection_preserves_the_truncation_marker() -> None:
    projected = _project_terminal(
        _native_terminal_body(
            truncated=True, truncate_reason="max_final_message_bytes"
        )
    )
    assert projected.truncated is True
    assert projected.truncate_reason == "max_final_message_bytes"


def test_terminal_projection_drops_a_reason_that_marks_no_truncation() -> None:
    """A reason with ``truncated: false`` describes nothing that happened."""

    projected = _project_terminal(
        _native_terminal_body(truncated=False, truncate_reason="max_final_message_bytes")
    )
    assert projected.truncated is False
    assert projected.truncate_reason is None


@pytest.mark.parametrize("unreadable", [7, "", "Not A Token", "x" * 200, {"a": 1}])
def test_terminal_projection_never_carries_an_unreadable_reason(unreadable) -> None:
    """The marker is preserved; foreign free text beside it is not."""

    projected = _project_terminal(
        _native_terminal_body(truncated=True, truncate_reason=unreadable)
    )
    assert projected.truncated is True
    assert projected.truncate_reason is None


def test_terminal_projection_clips_an_oversized_final_message_and_says_so() -> None:
    """ARS already bounds this; mirroring the bound is defence in depth.

    A body that somehow arrives longer than the pinned ceiling is clipped here
    rather than carried onto a chat surface unbounded — and the clip is
    *declared*, because silently shortening an agent's answer is worse than a
    long one.
    """

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_FINAL_MESSAGE_TRUNCATE_REASON,
        ARSD_MAX_FINAL_MESSAGE_BYTES,
    )

    oversized = "任务" * ARSD_MAX_FINAL_MESSAGE_BYTES
    projected = _project_terminal(_native_terminal_body(final_message=oversized))
    encoded = projected.final_message.encode("utf-8")
    assert len(encoded) <= ARSD_MAX_FINAL_MESSAGE_BYTES
    # Clipped on a character boundary, never mid-codepoint.
    assert encoded.decode("utf-8") == projected.final_message
    assert projected.truncated is True
    assert projected.truncate_reason == ARSD_FINAL_MESSAGE_TRUNCATE_REASON


def test_terminal_projection_mirror_matches_the_pinned_final_message_ceiling() -> None:
    result_mod = pytest.importorskip("agent_run_supervisor.result")
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_FINAL_MESSAGE_TRUNCATE_REASON,
        ARSD_MAX_FINAL_MESSAGE_BYTES,
    )

    assert ARSD_MAX_FINAL_MESSAGE_BYTES == result_mod.MAX_FINAL_MESSAGE_BYTES
    run_task_src = Path(
        importlib.import_module("agent_run_supervisor.native_acp.run_task").__file__
    ).read_text(encoding="utf-8")
    assert f'truncate_reason = "{ARSD_FINAL_MESSAGE_TRUNCATE_REASON}"' in run_task_src


@pytest.mark.parametrize("missing", [None, 7, [], "not-a-mapping"])
def test_terminal_projection_refuses_a_body_it_cannot_read(missing) -> None:
    with pytest.raises(SpineError) as excinfo:
        _project_terminal(missing)
    assert excinfo.value.code == RUNTIME_ARSD_INTERNAL


@pytest.mark.parametrize("bad_status", ["running", "accepted", "", None, "COMPLETED"])
def test_terminal_projection_refuses_a_nonterminal_status(bad_status) -> None:
    """A projection is a *terminal* answer; there is no partial one."""

    with pytest.raises(SpineError) as excinfo:
        _project_terminal(_native_terminal_body(), status=bad_status)
    assert excinfo.value.code == RUNTIME_ARSD_INTERNAL


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled", "timed_out", "unknown"])
def test_terminal_projection_admits_every_neutral_terminal(terminal) -> None:
    projected = _project_terminal(_native_terminal_body(), status=terminal)
    assert projected.status == terminal


def test_terminal_projection_keeps_an_absent_final_message_empty() -> None:
    body = _native_terminal_body()
    del body["final_message"]
    projected = _project_terminal(body)
    assert projected.final_message == ""
    assert projected.truncated is False


# --------------------------------------------------------------------------- #
# Deployed caller namespace + configured model selector (adapter expressiveness)
#
# Two config values the deployed 0.7.6 daemon is actually configured with were
# unrepresentable here: the caller's registered namespace ``hermes/default``
# and the Claude selector ``opus[1m]``. Both are admitted by the pinned wire
# contract, which validates ``namespace``/``requested_model`` as bounded
# printable *text*, not as identifier-like tokens. The tests below pin that
# distinction in both directions: the pinned grammar is the source of truth,
# and the identifier-like validators around it stay exactly as narrow as they
# were.
# --------------------------------------------------------------------------- #
DEPLOYED_NAMESPACE = "hermes/default"
DEPLOYED_MODEL = "opus[1m]"

#: Values that are text-shaped but not printable/bounded, so neither the pinned
#: request nor Sachima may admit them. ``\x00`` is included deliberately: a NUL
#: is the classic path/wire smuggling byte and stays refused.
UNSAFE_FIELD_TEXT = (
    "",
    "line\nbreak",
    "tab\tseparated",
    "nul\x00byte",
    "carriage\rreturn",
)


def _real_agent_run_request(**overrides):
    """One real pinned ``AgentRunRequest``, defaulted to the deployed values."""

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")

    kwargs = {
        "owner": "hermes",
        "namespace": DEPLOYED_NAMESPACE,
        "agent_id": "reader-agent",
        "expected_binding_hash": None,
        "input_refs": (),
        "requested_model": DEPLOYED_MODEL,
        "requested_effort": "xhigh",
        "grant_ref": "grant_reader_v1",
        "grant_hash": "sha256:" + "a" * 64,
        "grant_role_hash": "sha256:" + "b" * 64,
        "grant_capabilities": ("read", "search"),
        "mcp_snapshot_hashes": ("sha256:" + "c" * 64,),
        "credential_refs": ("cred_reader_github",),
        "limits": spec.RunLimits(**_limits_with()),
        "evidence_policy_hash": "sha256:" + "d" * 64,
        "recovery_policy_hash": "sha256:" + "e" * 64,
    }
    kwargs.update(overrides)
    return spec.AgentRunRequest(**kwargs)


def test_deployed_namespace_and_model_selector_reach_the_built_request() -> None:
    """The exact deployed pair survives config construction and submit build.

    ``hermes/default`` is the ``(owner, namespace)`` half the daemon
    exact-matches in ``_require_owner``; ``opus[1m]`` is the configured Claude
    selector. Neither is expressible as a safe identifier, and both are
    admitted by the pinned request, so the adapter must carry them verbatim.
    """

    config = _make_config(
        enabled=True,
        namespace=DEPLOYED_NAMESPACE,
        model_by_policy_ref={"policy_reader": DEPLOYED_MODEL},
    )
    assert config.namespace == DEPLOYED_NAMESPACE
    assert config.model_by_policy_ref["policy_reader"] == DEPLOYED_MODEL

    request = _build_payload(config=config)["request"]
    assert request["namespace"] == DEPLOYED_NAMESPACE
    assert request["requested_model"] == DEPLOYED_MODEL
    # The identifier-like neighbours are carried unchanged by the same build.
    assert request["owner"] == "sachima_host"
    assert request["agent_id"] == "reader-agent"
    assert request["requested_effort"] == "medium"

    # And the pinned request admits exactly this pair, so the adapter is not
    # widening past the daemon: submission fails on nothing but the caller's
    # registration.
    real = _real_agent_run_request(
        namespace=request["namespace"], requested_model=request["requested_model"]
    )
    assert real.namespace == DEPLOYED_NAMESPACE
    assert real.requested_model == DEPLOYED_MODEL


def test_config_text_bound_mirrors_the_pinned_field_contract_both_ways() -> None:
    """Drift-lock: the local field bound/grammar equals the pinned one exactly.

    Asserted through the distribution's *public* behaviour — constructing a
    real ``AgentRunRequest`` — rather than by reading a private constant, so
    the lock follows the daemon rather than a number written in by hand.
    """

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_MAX_FIELD_CHARS,
    )

    at_bound = "n" * ARSD_MAX_FIELD_CHARS
    over_bound = "n" * (ARSD_MAX_FIELD_CHARS + 1)

    # The real request accepts exactly at the bound and refuses one past it.
    _real_agent_run_request(namespace=at_bound, requested_model=at_bound)
    for field_name in ("namespace", "requested_model"):
        with pytest.raises(spec.SpecValidationError):
            _real_agent_run_request(**{field_name: over_bound})
        for unsafe in UNSAFE_FIELD_TEXT:
            with pytest.raises(spec.SpecValidationError):
                _real_agent_run_request(**{field_name: unsafe})

    # Sachima admits the same at-bound text...
    config = _make_config(
        namespace=at_bound, model_by_policy_ref={"policy_reader": at_bound}
    )
    assert config.namespace == at_bound

    # ...and refuses exactly the same over-bound and non-printable text, with
    # the existing stable config code and no echo of the rejected material.
    for overrides in (
        {"namespace": over_bound},
        {"model_by_policy_ref": {"policy_reader": over_bound}},
    ):
        with pytest.raises(SpineError) as excinfo:
            _make_config(**overrides)
        assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG
        assert str(excinfo.value) == RUNTIME_INVALID_ARSD_CONFIG


@pytest.mark.parametrize("unsafe", UNSAFE_FIELD_TEXT)
def test_unsafe_namespace_and_model_config_text_still_fails_closed(unsafe) -> None:
    for overrides in (
        {"namespace": unsafe},
        {"model_by_policy_ref": {"policy_reader": unsafe}},
    ):
        with pytest.raises(SpineError) as excinfo:
            _make_config(**overrides)
        assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG
        # Never echoes rejected material: the message IS the stable code.
        assert str(excinfo.value) == RUNTIME_INVALID_ARSD_CONFIG
        assert unsafe not in str(excinfo.value) or unsafe == ""


@pytest.mark.parametrize("wrong_type", [None, 7, True, b"bytes", ["list"]])
def test_non_string_namespace_and_model_config_still_fails_closed(wrong_type) -> None:
    for overrides in (
        {"namespace": wrong_type},
        {"model_by_policy_ref": {"policy_reader": wrong_type}},
    ):
        with pytest.raises(SpineError) as excinfo:
            _make_config(**overrides)
        assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG


def test_session_view_reads_back_the_deployed_namespace_and_model() -> None:
    """The daemon echoes the deployed values, so the read side must admit them.

    ``namespace`` is echoed on every session view and ``last_effective_model``
    is the exact-readback-proven selector of the Session's last Run — for the
    deployed route, literally ``opus[1m]``. A read validator narrower than the
    daemon's own guarantee would fail closed on every healthy Session.
    """

    view = _validate_session_view(
        _session_view(
            namespace=DEPLOYED_NAMESPACE, last_effective_model=DEPLOYED_MODEL
        )
    )
    assert view.namespace == DEPLOYED_NAMESPACE
    assert view.last_effective_model == DEPLOYED_MODEL
    # Still an observation only, and the narrow neighbours are unchanged.
    assert view.owner == "sachima_host"
    assert view.last_effective_effort == "medium"
    assert view.is_reusable is True


@pytest.mark.parametrize("unsafe", UNSAFE_FIELD_TEXT)
def test_session_view_still_refuses_unsafe_namespace_and_model_text(unsafe) -> None:
    for overrides in ({"namespace": unsafe}, {"last_effective_model": unsafe}):
        with pytest.raises(SpineError) as excinfo:
            _validate_session_view(_session_view(**overrides))
        assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


def test_config_text_widening_does_not_reach_identifier_like_validators() -> None:
    """The narrow validators stay narrow: this is a separation, not a widening.

    Owner, agent id, effort, session id and the ref/digest families keep their
    exact grammars — every one of them refuses the very characters the two
    config-text fields now carry.
    """

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        _safe_config_ref,
        _safe_wire_token,
    )

    for narrow in (DEPLOYED_NAMESPACE, DEPLOYED_MODEL):
        with pytest.raises(SpineError):
            _safe_config_ref(narrow)
        with pytest.raises(SpineError):
            _safe_wire_token(narrow)

    # The same refusal, reached through real config/read surfaces.
    for overrides in (
        {"owner": DEPLOYED_NAMESPACE},
        {"owner": DEPLOYED_MODEL},
        {"agent_by_policy_ref": {"policy_reader": DEPLOYED_MODEL}},
        {"effort_by_policy_ref": {"policy_reader": DEPLOYED_MODEL}},
        {"grant_ref": DEPLOYED_NAMESPACE},
        {"credential_refs": (DEPLOYED_NAMESPACE,)},
    ):
        with pytest.raises(SpineError) as excinfo:
            _make_config(**overrides)
        assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG

    for overrides in (
        {"owner": DEPLOYED_NAMESPACE},
        {"agent_id": DEPLOYED_MODEL},
        {"last_effective_effort": DEPLOYED_MODEL},
        {"session_id": DEPLOYED_NAMESPACE},
        {"profile_id": DEPLOYED_MODEL},
    ):
        with pytest.raises(SpineError) as excinfo:
            _validate_session_view(_session_view(**overrides))
        assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


# --------------------------------------------------------------------------- #
# Per-policy sealed grants
#
# ``grant_capabilities`` is the set the daemon's permission bridge freezes for
# the Run, so it is the only thing that decides whether a Run can write. A
# host that runs a review AGENT and an implementation AGENT under one global
# grant gives both the union — the review Run receives ``write`` it was never
# meant to have. The per-policy map closes that: the exact capability set is
# resolved from the config, and the identity that names it is derived from it,
# so a narrowed grant can never travel under the identity of the wide one.
# --------------------------------------------------------------------------- #
REVIEW_CAPABILITIES = ("execute", "read", "search")
IMPLEMENTATION_CAPABILITIES = ("execute", "read", "search", "write")


def _author_config(**overrides):
    """A config whose global grant is the widest the operator approved."""

    kwargs = {
        "agent_by_policy_ref": {
            "policy_review": "reader-agent",
            "policy_author": "author-agent",
        },
        "model_by_policy_ref": {
            "policy_review": "claude-sonnet-5",
            "policy_author": "claude-sonnet-5",
        },
        "effort_by_policy_ref": {"policy_review": "medium", "policy_author": "medium"},
        "run_limits_by_policy_ref": {
            "policy_review": _valid_config_kwargs()["run_limits_by_policy_ref"][
                "policy_reader"
            ],
            "policy_author": _valid_config_kwargs()["run_limits_by_policy_ref"][
                "policy_reader"
            ],
        },
        "grant_capabilities": IMPLEMENTATION_CAPABILITIES,
        "enabled": True,
    }
    kwargs.update(overrides)
    return _make_config(**kwargs)


def _derive(config, capabilities):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        derive_arsd_sealed_grant,
    )

    return derive_arsd_sealed_grant(config, capabilities)


def test_a_grant_equal_to_the_configured_one_keeps_the_operators_identity() -> None:
    """Nothing is invented when nothing narrowed: the operator already sealed
    this exact set, and re-labelling it would lose their provenance."""

    config = _author_config()
    sealed = _derive(config, IMPLEMENTATION_CAPABILITIES)

    assert sealed.capabilities == IMPLEMENTATION_CAPABILITIES
    assert sealed.grant_ref == config.grant_ref
    assert sealed.grant_hash == config.grant_hash
    assert sealed.grant_role_hash == config.grant_role_hash


def test_a_narrowed_grant_gets_its_own_identity() -> None:
    config = _author_config()
    wide = _derive(config, IMPLEMENTATION_CAPABILITIES)
    narrow = _derive(config, REVIEW_CAPABILITIES)

    assert narrow.capabilities == REVIEW_CAPABILITIES
    assert narrow.grant_ref != wide.grant_ref
    assert narrow.grant_hash != wide.grant_hash
    assert narrow.grant_role_hash != wide.grant_role_hash
    # The derived identity still satisfies the shapes the daemon accepts.
    assert narrow.grant_ref.startswith(config.grant_ref)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", narrow.grant_hash)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", narrow.grant_role_hash)
    assert re.fullmatch(r"[a-z][a-z0-9_]{0,127}", narrow.grant_ref)


def test_the_derivation_is_deterministic_so_a_recovery_resends_the_same_bytes() -> None:
    config = _author_config()
    first = _derive(config, REVIEW_CAPABILITIES)
    second = _derive(config, ("search", "read", "execute"))
    assert first == second


def test_two_different_narrowings_never_share_an_identity() -> None:
    config = _author_config()
    seen = {
        _derive(config, caps).grant_ref
        for caps in (
            ("read", "search"),
            ("execute", "read", "search"),
            ("read", "search", "write"),
            ("execute", "read", "search", "write"),
        )
    }
    assert len(seen) == 4


@pytest.mark.parametrize(
    "capabilities",
    [
        ("execute", "read", "search", "write", "delete"),
        ("delete",),
        (),
        ("read", "read"),
        "read",
        None,
        ("Read",),
        (7,),
    ],
    ids=[
        "widens_past_the_operator_grant",
        "outside_the_operator_grant",
        "empty",
        "duplicate",
        "bare_string",
        "none",
        "wrong_case",
        "not_a_string",
    ],
)
def test_a_grant_that_is_not_a_narrowing_fails_closed(capabilities) -> None:
    """A preset chooses among what the operator approved; never above it."""

    config = _author_config(grant_capabilities=IMPLEMENTATION_CAPABILITIES)
    with pytest.raises(SpineError) as excinfo:
        _derive(config, capabilities)
    assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG


def test_the_payload_seals_the_per_policy_grant_rather_than_the_global_one() -> None:
    config = _author_config(
        grant_by_policy_ref={
            "policy_review": list(REVIEW_CAPABILITIES),
            "policy_author": list(IMPLEMENTATION_CAPABILITIES),
        }
    )

    review = _build_payload(
        config=config,
        agent_policy_ref="policy_review",
        model_policy_ref="policy_review",
        effort_policy_ref="policy_review",
        run_limits_policy_ref="policy_review",
    )["request"]
    author = _build_payload(
        config=config,
        agent_policy_ref="policy_author",
        model_policy_ref="policy_author",
        effort_policy_ref="policy_author",
        run_limits_policy_ref="policy_author",
    )["request"]

    assert review["grant_capabilities"] == list(REVIEW_CAPABILITIES)
    assert "write" not in review["grant_capabilities"]
    assert author["grant_capabilities"] == list(IMPLEMENTATION_CAPABILITIES)

    # Distinct capability sets never travel under one identity.
    assert review["grant_ref"] != author["grant_ref"]
    assert review["grant_hash"] != author["grant_hash"]
    assert review["grant_role_hash"] != author["grant_role_hash"]
    # The unnarrowed one keeps the operator's own identity.
    assert author["grant_ref"] == config.grant_ref
    assert author["grant_hash"] == config.grant_hash


def test_a_policy_with_no_per_policy_grant_keeps_the_configured_one() -> None:
    """Callers that never opted in are byte-identical to before."""

    config = _author_config(
        grant_by_policy_ref={"policy_review": list(REVIEW_CAPABILITIES)}
    )
    request = _build_payload(
        config=config,
        agent_policy_ref="policy_author",
        model_policy_ref="policy_author",
        effort_policy_ref="policy_author",
        run_limits_policy_ref="policy_author",
    )["request"]

    assert request["grant_capabilities"] == list(config.grant_capabilities)
    assert request["grant_ref"] == config.grant_ref


def test_a_per_policy_grant_that_widens_fails_the_config_closed() -> None:
    with pytest.raises(SpineError) as excinfo:
        _author_config(
            grant_capabilities=("read", "search"),
            grant_by_policy_ref={"policy_author": ["read", "search", "write"]},
        )
    assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG


@pytest.mark.parametrize(
    "mapping",
    [
        {"policy_author": []},
        {"policy_author": ["delete"]},
        {"policy_author": "read"},
        {"policy_author": None},
        {"POLICY_AUTHOR": ["read"]},
        {7: ["read"]},
        ["policy_author"],
        "policy_author",
    ],
)
def test_a_malformed_per_policy_grant_map_fails_the_config_closed(mapping) -> None:
    with pytest.raises(SpineError) as excinfo:
        _author_config(grant_by_policy_ref=mapping)
    assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG


def test_the_sealed_payload_still_parses_under_the_real_pinned_protocol() -> None:
    """A derived identity is text the daemon accepts, not a shape it refuses."""

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    config = _author_config(
        grant_by_policy_ref={"policy_review": list(REVIEW_CAPABILITIES)}
    )
    payload = _build_payload(
        config=config,
        agent_policy_ref="policy_review",
        model_policy_ref="policy_review",
        effort_policy_ref="policy_review",
        run_limits_policy_ref="policy_review",
    )
    command = protocol.parse_submit(payload)
    assert command.request.grant_capabilities == REVIEW_CAPABILITIES
    assert command.request.grant_ref == payload["request"]["grant_ref"]


# --------------------------------------------------------------------------- #
# The canonical "no effort selector" effort (model-only fidelity)
#
# Under the pinned distribution's model-only configuration fidelity an agent
# advertises no independent effort selector, so ``N/A`` is the one effort such a
# Run may request and the one effort its Session can report afterwards. It
# carries a ``/``, which the shared wire-token grammar has never admitted, so a
# real model-only route (Cursor's) failed closed on both the request side and
# the Session read-back.
# --------------------------------------------------------------------------- #
EFFORT_NA = "N/A"

#: Neither the sentinel nor an ordinary wire token. The punctuation, case and
#: whitespace variants the old grammar refused stay refused, and ``7`` keeps the
#: sentinel comparison from becoming a type-blind equality check.
REFUSED_EFFORTS = ("", "n/a", " N/A", "N/A ", "N / A", "N//A", "N/A\nmedium", "/", 7)


def test_the_effort_sentinel_mirrors_the_pinned_distribution() -> None:
    """Drift-lock: the mirrored literal is the distribution's own constant.

    It is mirrored rather than imported (module import purity forbids importing
    ``agent_run_supervisor`` in the spine), so this is what keeps it honest.
    """

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        _EFFORT_NOT_APPLICABLE,
    )

    fidelity = pytest.importorskip("agent_run_supervisor.native_acp.config_fidelity")
    assert _EFFORT_NOT_APPLICABLE == fidelity.EFFORT_NOT_APPLICABLE == EFFORT_NA
    # The pinned request admits it, so admitting it here is not a widening.
    assert _real_agent_run_request(requested_effort=EFFORT_NA).requested_effort == (
        EFFORT_NA
    )


@pytest.mark.parametrize("effort", [EFFORT_NA, "medium"])
def test_configured_effort_reaches_the_built_request_byte_identical(effort) -> None:
    """The sentinel joins the ordinary vocabulary and nothing normalizes it.

    The daemon compares the requested effort against its own constant by
    equality, so a value Sachima had trimmed or case-folded on the way through
    would be refused at admission instead of running.
    """

    config = _make_config(enabled=True, effort_by_policy_ref={"policy_reader": effort})
    assert config.effort_by_policy_ref["policy_reader"] == effort
    assert _build_payload(config=config)["request"]["requested_effort"] == effort


@pytest.mark.parametrize("effort", [EFFORT_NA, "medium", None])
def test_session_view_reads_back_the_last_effective_effort(effort) -> None:
    """A finished model-only Session must stay validatable and reusable.

    ``last_effective_effort`` is an observation of a Run that already
    completed, and on the live daemon every Session reporting ``N/A`` is a
    completed Cursor Run. Refusing it here made such a Session unvalidatable,
    so status and continuation failed at Sachima's boundary after a Run the
    agent had itself finished. ``None`` remains the "no completed Run" reading.
    """

    view = _validate_session_view(_session_view(last_effective_effort=effort))
    assert view.last_effective_effort == effort


@pytest.mark.parametrize("refused", REFUSED_EFFORTS)
def test_near_miss_effort_spellings_fail_closed_on_both_sides(refused) -> None:
    """Exact equality, not a ``/``-shaped hole in the effort field."""

    with pytest.raises(SpineError) as config_error:
        _make_config(enabled=True, effort_by_policy_ref={"policy_reader": refused})
    assert config_error.value.code == RUNTIME_INVALID_ARSD_CONFIG

    with pytest.raises(SpineError) as view_error:
        _validate_session_view(_session_view(last_effective_effort=refused))
    assert view_error.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


def test_the_effort_sentinel_is_admitted_in_the_effort_field_only() -> None:
    """A field-specific validator, not a widening of the shared grammar."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import _safe_wire_token

    with pytest.raises(SpineError):
        _safe_wire_token(EFFORT_NA)
    # ``NA`` and ``N.A`` were ordinary wire tokens before this change and still
    # are: the sentinel branch neither admits nor narrows them.
    for ordinary in ("NA", "N.A"):
        assert _safe_wire_token(ordinary) == ordinary

    with pytest.raises(SpineError) as config_error:
        _make_config(agent_by_policy_ref={"policy_reader": EFFORT_NA})
    assert config_error.value.code == RUNTIME_INVALID_ARSD_CONFIG

    with pytest.raises(SpineError) as view_error:
        _validate_session_view(_session_view(agent_id=EFFORT_NA))
    assert view_error.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION
