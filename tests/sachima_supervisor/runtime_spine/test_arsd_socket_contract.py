"""D1 offline Socket API v2 contract tests for the arsd adapter boundary.

Covers the ARS 0.6.3 Socket integration plan D1 slice
(``docs/plans/2026-08-05-ars-0.6.3-socket-integration-plan.md``): the
default-off :class:`ArsdSupervisorConfig`, the injected
:class:`ArsdClientFacade` boundary with its lazy short-lived production
facade, stable request identity, exact request construction, exact
``server_info`` / ``submit`` / ``run_events`` validators, and the
Sachima-owned stable error mapping.

Everything here is hermetic and offline: the only sockets ever touched are
throwaway AF_UNIX fake-socket servers owned by this file. No real daemon, no
Runtime Spine / Gateway wiring, no external AGENT execution.
"""

from __future__ import annotations

import importlib
import sys
import traceback

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
#: The exact wire→Sachima closed mapping. Every arsd v1 wire code must map to
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
    mapping covers exactly ``ERROR_CODES_V1`` plus the client-local ``CLIENT``
    code — a pin bump that adds/renames wire codes fails here instead of
    collapsing new codes to INTERNAL silently.
    """

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    assert set(_WIRE_TO_STABLE) == set(protocol.ERROR_CODES_V1) | {"CLIENT"}


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


def _valid_config_kwargs(**overrides):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_SUPERVISOR_CONFIG_TYPE,
    )

    kwargs = {
        "type": ARSD_SUPERVISOR_CONFIG_TYPE,
        "approval_ref": "approval_arsd_d1_offline",
        "owner": "sachima_host",
        "namespace": "sachima_tasks",
        "socket_path": SOCKET_CANARY,
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
    assert config.required_api_version == ARSD_REQUIRED_API_VERSION == 2


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
        {"grant_capabilities": ("read", "write")},
        {"grant_capabilities": ("read", "deliver")},
        {"mcp_snapshot_hashes": ("plain",)},
        {"credential_refs": ("cred_ok", 7)},
        {"evidence_policy_hash": ""},
        {"recovery_policy_hash": None},
        {"expected_package_version": "0.1.7"},
        {"expected_package_version": "9.9.9"},
        {"required_api_version": 1},
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
        assert "sachima-canary" not in rendering


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
    """Drift-lock: our closed RunLimits key mirror equals the real 0.6.3 spec."""

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
# D0+D1 grant capability allowlist (formal review blocker 1): the approved
# plan admits read/search observation capabilities only. One closed local
# allowlist, drift-locked against the entire pinned permission domain.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "capabilities",
    [
        ("delete",),
        ("execute",),
        ("terminal",),
        ("move",),
        ("fetch",),
        ("switch_mode",),
        ("other",),
        ("read", "delete"),
        ("search", "execute"),
    ],
)
def test_write_capable_grant_capabilities_fail_closed(capabilities) -> None:
    """A non-read/search capability is invalid config — even where the pinned
    wire protocol itself would accept it: the D0+D1 plan authorizes no
    write-capable role."""

    with pytest.raises(SpineError) as excinfo:
        _make_config(grant_capabilities=capabilities)
    _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_CONFIG)


def test_grant_capability_allowlist_drift_locks_the_pinned_permission_domain() -> None:
    """One closed allowlist, checked against every pinned permission kind.

    Imports the real 0.6.3 permission domain and asserts: the local allowlist
    is exactly ``{"read", "search"}`` and stays inside the pinned domain, each
    allowlisted kind is admitted end-to-end (config plus the real
    ``parse_submit``), and every other pinned kind fails closed. A pin bump
    that renames or extends the permission domain fails here instead of
    drifting silently.
    """

    role = pytest.importorskip("agent_run_supervisor.role")
    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        _GRANTABLE_CAPABILITIES,
    )

    assert _GRANTABLE_CAPABILITIES == frozenset({"read", "search"})
    assert _GRANTABLE_CAPABILITIES < set(role.PERMISSION_KINDS)

    for kind in role.PERMISSION_KINDS:
        if kind in _GRANTABLE_CAPABILITIES:
            config = _make_config(enabled=True, grant_capabilities=(kind,))
            assert config.grant_capabilities == (kind,)
            command = protocol.parse_submit(_build_payload(config=config))
            assert command.request.grant_capabilities == (kind,)
        else:
            with pytest.raises(SpineError) as excinfo:
                _make_config(grant_capabilities=(kind,))
            assert excinfo.value.code == RUNTIME_INVALID_ARSD_CONFIG


def test_read_search_grant_is_accepted_and_parses_under_the_pinned_protocol() -> None:
    """Positive control: the approved read/search grant builds a payload the
    real 0.6.3 wire validator accepts unchanged."""

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    config = _make_config(enabled=True, grant_capabilities=("read", "search"))
    command = protocol.parse_submit(_build_payload(config=config))
    assert command.request.grant_capabilities == ("read", "search")


# --------------------------------------------------------------------------- #
# RunLimits bounds mirror (formal review blocker 2): every per-field min/max
# and the coupled event budget of the installed 0.6.3 spec, enforced locally.
# --------------------------------------------------------------------------- #
def _limits_with(**overrides):
    limits = dict(_valid_config_kwargs()["run_limits_by_policy_ref"]["policy_reader"])
    limits.update(overrides)
    return limits


def test_run_limit_bounds_mirror_the_pinned_spec_constants() -> None:
    """Drift-lock: the local per-field ceilings/floors and the coupled event
    budget equal the real 0.6.3 spec constants exactly — no arbitrary local
    limits."""

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        _INT_RUN_LIMIT_KEYS,
        _RUN_LIMIT_EVENT_BUDGET_BYTES,
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
    assert _RUN_LIMIT_EVENT_BUDGET_BYTES == spec.LIMIT_EVENT_BUDGET_BYTES
    # The two integer floors the spec keeps unnamed (minimum=1) are
    # behaviour-locked against the real RunLimits dataclass.
    for key in ("max_stderr_bytes", "max_events"):
        assert _RUN_LIMIT_MIN[key] == 1
        spec.RunLimits(**_limits_with(**{key: 1}))
        with pytest.raises(spec.SpecValidationError):
            spec.RunLimits(**_limits_with(**{key: 0}))


@pytest.mark.parametrize(
    "limit_field,value",
    [
        ("startup_timeout_seconds", 3601),
        ("startup_timeout_seconds", 3600.5),
        ("turn_timeout_seconds", 86_401),
        ("cancel_grace_seconds", 300.5),
        ("max_stderr_bytes", 67_108_865),
        ("max_event_bytes", 1_048_577),
        ("max_event_bytes", 255),
        ("max_events", 1_000_001),
    ],
)
def test_run_limits_outside_the_pinned_bounds_fail_closed(limit_field, value) -> None:
    """A limits policy the installed 0.6.3 daemon would refuse as
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
    """Positive control: exact per-field ceilings and floors (with a
    satisfiable coupled budget) are admitted locally and parse under the real
    pinned protocol."""

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    for limits in (
        {
            "startup_timeout_seconds": 3600.0,
            "turn_timeout_seconds": 86_400.0,
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


def test_run_limit_event_budget_coupling_matches_the_pinned_spec() -> None:
    """The coupled ``max_event_bytes * max_events`` budget of the installed
    0.6.3 spec is enforced locally: the exact budget is admitted, one event
    over it fails closed, and the real ``parse_submit`` agrees."""

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    at_budget = _limits_with(max_event_bytes=1_048_576, max_events=1024)
    over_budget = _limits_with(max_event_bytes=1_048_576, max_events=1025)

    accepted = _make_config(
        enabled=True, run_limits_by_policy_ref={"policy_reader": at_budget}
    )
    protocol.parse_submit(_build_payload(config=accepted))

    with pytest.raises(SpineError) as excinfo:
        _make_config(run_limits_by_policy_ref={"policy_reader": over_budget})
    _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_CONFIG)

    payload = _build_payload(config=_make_config(enabled=True))
    payload["request"]["limits"].update(over_budget)
    with pytest.raises(protocol.ProtocolError) as protocol_excinfo:
        protocol.parse_submit(payload)
    assert protocol_excinfo.value.code == protocol.INVALID_REQUEST


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


def test_submit_payload_has_the_exact_v2_wire_shape() -> None:
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
    assert request["session_reuse"] == "none"
    assert request["ars_session_id"] is None
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
    assert request["schema_version"] == ARSD_SPEC_SCHEMA_VERSION == 2


def test_submit_payload_parses_under_the_real_pinned_protocol() -> None:
    """The built payload must satisfy the installed 0.6.3 ``parse_submit``.

    This is the exact-contract lock: Sachima's builder output round-trips
    through the real wire validator (test-time import only) so a field-name or
    shape drift fails here, not against a live daemon.
    """

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    payload = _build_payload()
    command = protocol.parse_submit(payload)
    assert command.request.owner == "sachima_host"
    assert command.request.schema_version == 2
    assert command.prompt_text == PROMPT_CANARY


def test_submit_payload_session_reuse_contract() -> None:
    reuse = _build_payload(
        session_reuse="reuse", ars_session_id="run-1234abcd-ephemeral"
    )
    assert reuse["request"]["session_reuse"] == "reuse"
    assert reuse["request"]["ars_session_id"] == "run-1234abcd-ephemeral"

    with pytest.raises(SpineError) as excinfo:
        _build_payload(session_reuse="reuse")
    assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST

    with pytest.raises(SpineError) as excinfo:
        _build_payload(session_reuse="attach")
    assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST

    with pytest.raises(SpineError) as excinfo:
        _build_payload(session_reuse="none", ars_session_id="run-1-ephemeral")
    assert excinfo.value.code == RUNTIME_ARSD_INVALID_REQUEST


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


@pytest.mark.parametrize("bad_reuse", [[], {}, ["none"]])
def test_submit_payload_unhashable_session_reuse_is_invalid_request_not_a_crash(
    bad_reuse,
) -> None:
    """An unhashable session_reuse fails closed — never a raw TypeError."""

    with pytest.raises(SpineError) as excinfo:
        _build_payload(session_reuse=bad_reuse)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_INVALID_REQUEST)


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
    absolute cwd still passes through verbatim."""

    cwd = "/tmp/sachima-canary/task-cwd"
    assert _build_payload(cwd=cwd)["cwd"] == cwd


# --------------------------------------------------------------------------- #
# server_info negotiation validator (plan §5.4): exact preflight contract.
# --------------------------------------------------------------------------- #
def _server_info_payload(**overrides):
    payload = {
        "version": "0.6.3",
        "api_version": 2,
        "supported_api_versions": [1, 2],
        "v2_only_operations": ["submit"],
        "limits": {
            "max_concurrent_runs": 4,
            "max_frame_bytes": 1_048_576,
            "max_prompt_bytes": 262_144,
            "events_page_limit": 256,
            "event_follow_queue_size": 1024,
        },
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


def test_server_info_negotiation_accepts_the_exact_063_v2_shape() -> None:
    info = _validate_server_info(_server_info_payload())
    assert info.version == "0.6.3"
    assert info.api_version == 2
    assert info.supported_api_versions == (1, 2)
    assert info.v2_only_operations == ("submit",)
    assert dict(info.limits) == {
        "max_concurrent_runs": 4,
        "max_frame_bytes": 1_048_576,
        "max_prompt_bytes": 262_144,
        "events_page_limit": 256,
        "event_follow_queue_size": 1024,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": "0.1.7"},
        {"version": "0.7.0"},
        {"api_version": 1},
        {"api_version": 3},
        {"supported_api_versions": [1]},
        {"v2_only_operations": []},
        {"v2_only_operations": ["run_events"]},
        {"limits": {"max_concurrent_runs": 0, "max_frame_bytes": 1_048_576,
                    "max_prompt_bytes": 262_144, "events_page_limit": 256,
                    "event_follow_queue_size": 1024}},
        {"limits": {"max_concurrent_runs": 4, "max_frame_bytes": 999,
                    "max_prompt_bytes": 262_144, "events_page_limit": 256,
                    "event_follow_queue_size": 1024}},
        {"limits": {"max_concurrent_runs": 4, "max_frame_bytes": 1_048_576,
                    "max_prompt_bytes": 1, "events_page_limit": 256,
                    "event_follow_queue_size": 1024}},
    ],
)
def test_server_info_incompatibility_is_one_stable_mismatch_code(
    overrides: dict,
) -> None:
    """Package/API/limit mismatch → one stable backend-unavailable code."""

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
        _server_info_payload(api_version="2"),
        _server_info_payload(supported_api_versions="12"),
        _server_info_payload(supported_api_versions=[1, True]),
        _server_info_payload(v2_only_operations="submit"),
        _server_info_payload(v2_only_operations=[7]),
        _server_info_payload(limits=None),
        _server_info_payload(limits={}),
        _server_info_payload(extra_key=1),
        _server_info_payload(
            limits={
                "max_concurrent_runs": 4,
                "max_frame_bytes": 1_048_576,
                "max_prompt_bytes": 262_144,
                "events_page_limit": 256,
                "event_follow_queue_size": 1024,
                "surprise": 1,
            }
        ),
        _server_info_payload(
            limits={
                "max_concurrent_runs": "4",
                "max_frame_bytes": 1_048_576,
                "max_prompt_bytes": 262_144,
                "events_page_limit": 256,
                "event_follow_queue_size": 1024,
            }
        ),
    ],
)
def test_malformed_server_info_is_a_protocol_violation(payload) -> None:
    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(payload)
    assert excinfo.value.code == RUNTIME_ARSD_PROTOCOL_VIOLATION


REMOTE_OP_CANARY = "remote-detail-canary-7d9f"


@pytest.mark.parametrize(
    "v2_only",
    [
        ["submit", REMOTE_OP_CANARY],
        [REMOTE_OP_CANARY, "submit"],
        [REMOTE_OP_CANARY],
        ["submit", "submit"],
        ["submit", "run_events"],
    ],
    ids=["extra_canary", "canary_first", "canary_only", "duplicate", "extra_known_op"],
)
def test_server_info_v2_only_operations_must_be_exactly_the_pinned_set(
    v2_only,
) -> None:
    """Pinned 0.6.3 fact: ``submit`` is the only v2-only operation. Extra,
    duplicate, or arbitrary remote entries are rejected before
    ``ArsdServerInfo`` exists — a remote token never reaches a repr surface."""

    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(_server_info_payload(v2_only_operations=v2_only))
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_VERSION_MISMATCH)
    assert REMOTE_OP_CANARY not in _rendered_chain(excinfo)


@pytest.mark.parametrize(
    "bad_entry",
    ["remote detail canary 7d9f", "x" * 4096, "bad\nop-canary-7d9f", ""],
    ids=["spaces", "unbounded", "newline", "empty"],
)
def test_server_info_malformed_v2_only_entries_are_protocol_violations(
    bad_entry,
) -> None:
    """An off-grammar operation token is malformed shape, not a compat verdict."""

    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(
            _server_info_payload(v2_only_operations=["submit", bad_entry])
        )
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_PROTOCOL_VIOLATION)
    rendered = _rendered_chain(excinfo)
    assert "x" * 64 not in rendered
    if bad_entry:
        assert bad_entry not in rendered


@pytest.mark.parametrize(
    "supported",
    [[1, 2, 31337], [2, 1], [1, 2, 2], [2], [1, 2, 10**4000]],
    ids=["extra_version", "reordered", "duplicate", "subset", "unbounded_int"],
)
def test_server_info_supported_versions_must_be_exactly_the_pinned_tuple(
    supported,
) -> None:
    """Pinned 0.6.3 fact: the daemon reports ``[1, 2]`` exactly. Any other
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
    limits = dict(_server_info_payload()["limits"])
    limits[capacity_key] = 10**4000
    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(_server_info_payload(limits=limits))
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_VERSION_MISMATCH)
    assert str(10**4000) not in _rendered_chain(excinfo)


def test_server_info_version_canary_never_survives_or_renders() -> None:
    """A regex-valid but off-pin version string is rejected with the stable
    mismatch code and never rendered anywhere."""

    off_pin_version = "0.6.3rc-canary-7d9f"
    with pytest.raises(SpineError) as excinfo:
        _validate_server_info(_server_info_payload(version=off_pin_version))
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_VERSION_MISMATCH)
    assert off_pin_version not in _rendered_chain(excinfo)


def test_server_info_mirror_constants_match_the_pinned_protocol() -> None:
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_MAX_FRAME_BYTES,
        ARSD_MAX_PROMPT_BYTES,
        ARSD_REQUIRED_API_VERSION,
    )

    protocol = pytest.importorskip("agent_run_supervisor.arsd.protocol")
    assert ARSD_MAX_FRAME_BYTES == protocol.MAX_FRAME_BYTES
    assert ARSD_MAX_PROMPT_BYTES == protocol.MAX_PROMPT_BYTES
    assert ARSD_REQUIRED_API_VERSION == protocol.ARSD_API_VERSION
    assert ARSD_REQUIRED_API_VERSION in protocol.SUPPORTED_API_VERSIONS
    assert "submit" in protocol.V2_ONLY_OPERATIONS

    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        _ARSD_SUPPORTED_API_VERSIONS,
        _ARSD_V2_ONLY_OPERATIONS,
    )

    # The closed negotiation mirrors equal the exact wire emission of the
    # pinned daemon (``list(...)`` / ``sorted(...)`` in its server_info).
    assert _ARSD_SUPPORTED_API_VERSIONS == tuple(protocol.SUPPORTED_API_VERSIONS)
    assert _ARSD_V2_ONLY_OPERATIONS == tuple(sorted(protocol.V2_ONLY_OPERATIONS))

    spec = pytest.importorskip("agent_run_supervisor.native_acp.spec")
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_SPEC_SCHEMA_VERSION,
    )

    assert ARSD_SPEC_SCHEMA_VERSION == spec.SPEC_SCHEMA_VERSION


# --------------------------------------------------------------------------- #
# submit response validator: durable acceptance only, run_id stays private.
# --------------------------------------------------------------------------- #
def _validate_submit(payload):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        validate_arsd_submit_result,
    )

    return validate_arsd_submit_result(payload)


def test_submit_result_returns_accepted_identity() -> None:
    accepted = _validate_submit(
        {"run_id": "1f2e3d4c5b6a", "accepted_at": "2026-08-05T10:00:00+00:00"}
    )
    assert accepted.run_id == "1f2e3d4c5b6a"
    assert accepted.accepted_at == "2026-08-05T10:00:00+00:00"


def test_submit_result_keeps_run_id_out_of_repr() -> None:
    accepted = _validate_submit(
        {"run_id": "private4runid", "accepted_at": "2026-08-05T10:00:00+00:00"}
    )
    rendering = repr(accepted) + str(accepted)
    assert "private4runid" not in rendering
    for attr in ("as_dict", "to_dict", "serialize", "to_json"):
        assert not hasattr(accepted, attr)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"run_id": "abc"},
        {"accepted_at": "2026-08-05T10:00:00+00:00"},
        {"run_id": "abc", "accepted_at": "2026-08-05T10:00:00+00:00", "x": 1},
        {"run_id": "", "accepted_at": "2026-08-05T10:00:00+00:00"},
        {"run_id": 7, "accepted_at": "2026-08-05T10:00:00+00:00"},
        {"run_id": "bad run id", "accepted_at": "2026-08-05T10:00:00+00:00"},
        {"run_id": "abc", "accepted_at": "not a timestamp"},
        {"run_id": "abc", "accepted_at": "2026-08-05T10:00:00"},
        {"run_id": "abc", "accepted_at": None},
        {"run_id": "abc", "accepted_at": "2026-08-05T10:00:00+00:00\nx"},
    ],
)
def test_malformed_submit_result_is_a_protocol_violation(payload) -> None:
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
        _validate_submit({"run_id": "run4abc", "accepted_at": bad_timestamp})
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_PROTOCOL_VIOLATION)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True
    rendered = _rendered_chain(excinfo)
    assert "canary" not in rendered
    assert "isoformat" not in rendered
    assert "99:99" not in rendered
    assert "ValueError" not in rendered


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


def test_facade_construction_never_connects(fake_arsd_server) -> None:
    """Composing the facade is not a daemon probe (plan §10: zero submits)."""

    server = fake_arsd_server(lambda envelope: None)
    _facade_for(server)
    assert server.connections == 0


def test_v2_negotiation_roundtrip_over_the_wire(fake_arsd_server) -> None:
    """server_info over real client + fake socket, validated exactly."""

    server = fake_arsd_server(
        lambda envelope: _result_frame(envelope["request_id"], _server_info_payload())
    )
    facade = _facade_for(server)
    info = _validate_server_info(
        facade.server_info(), config=_make_config(enabled=True)
    )
    assert info.version == "0.6.3"
    assert server.received[0]["op"] == "server_info"
    assert server.received[0]["api_version"] == 2
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
            envelope["request_id"],
            {"run_id": "run4abc", "accepted_at": "2026-08-05T10:00:00+00:00"},
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
    assert info.api_version == 2
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
