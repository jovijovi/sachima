"""D1 offline Socket API v2 contract boundary for the external ``arsd`` daemon.

This module is the ARS 0.6.3 Socket integration plan's D1 slice
(``docs/plans/2026-08-05-ars-0.6.3-socket-integration-plan.md``): the pure,
offline contract foundation Sachima will later (D2+) compose into a Runtime
Spine backend. It contains the default-off :class:`ArsdSupervisorConfig`, the
injected :class:`ArsdClientFacade` boundary with its lazy short-lived
:class:`DefaultArsdClientFacade`, stable request identity, exact submit
request construction, exact ``server_info`` / ``submit`` / ``run_events``
response validators, and a small Sachima-owned stable error mapping.

Boundaries:

* **Default-off.** ``ArsdSupervisorConfig.enabled`` defaults to ``False`` and
  :func:`require_enabled_arsd_supervisor_config` fails closed with a stable
  code unless it is exactly ``True``. Nothing here is wired into Runtime
  Spine, Gateway, or any composition root — that is D2+.
* **Offline.** Importing this module never imports ``agent_run_supervisor``
  and never opens a socket. Only :class:`DefaultArsdClientFacade` operations
  lazily import the official client and open one short-lived connection per
  bounded operation; a fresh client is used after any loss. There is no
  silent fallback to the library backend or a CLI.
* **No-leak.** Private values (``socket_path``, workspace paths, prompt text,
  raw event evidence) live in ``repr=False`` fields with no serialize
  surface, and every failure raises :class:`SpineError` whose message IS the
  stable code — remote error text, exception text, and payload material are
  never propagated.
* **Foreign cursor only.** ``run_events`` pagination stays a foreign
  read-model cursor (``resume_cursor`` / ``has_more``); it never becomes
  Sachima ``TaskEventLog.seq``.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, NoReturn, Protocol, runtime_checkable

from ..supervisor_library import EXPECTED_AGENT_RUN_SUPERVISOR_VERSION
from .events import SpineError, _safe_digest, _safe_id, safe_role_key

__all__ = [
    "ARSD_STABLE_CODES",
    "RUNTIME_ARSD_BUSY",
    "RUNTIME_ARSD_DISABLED",
    "RUNTIME_ARSD_IDEMPOTENCY_CONFLICT",
    "RUNTIME_ARSD_INTERNAL",
    "RUNTIME_ARSD_INVALID_REQUEST",
    "RUNTIME_ARSD_POLICY_DENIED",
    "RUNTIME_ARSD_PROTOCOL_VIOLATION",
    "RUNTIME_ARSD_SHUTTING_DOWN",
    "RUNTIME_ARSD_SUBMISSION_INDETERMINATE",
    "RUNTIME_ARSD_UNAVAILABLE",
    "RUNTIME_ARSD_UNKNOWN_TARGET",
    "RUNTIME_ARSD_VERSION_MISMATCH",
    "RUNTIME_INVALID_ARSD_CONFIG",
    "ARSD_SUPERVISOR_CONFIG_TYPE",
    "ARSD_REQUIRED_API_VERSION",
    "ARSD_MAX_FRAME_BYTES",
    "ARSD_MAX_PROMPT_BYTES",
    "ARSD_SPEC_SCHEMA_VERSION",
    "ArsdClientFacade",
    "ArsdRunEventsPage",
    "ArsdServerInfo",
    "ArsdSubmitAccepted",
    "DefaultArsdClientFacade",
    "ArsdSupervisorConfig",
    "arsd_submit_payload_digest",
    "build_arsd_submit_payload",
    "derive_arsd_request_id",
    "map_arsd_client_error_code",
    "require_enabled_arsd_supervisor_config",
    "validate_arsd_run_events_page",
    "validate_arsd_server_info",
    "validate_arsd_submit_result",
    "validate_arsd_supervisor_config",
]

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
RUNTIME_ARSD_DISABLED = "runtime_arsd_disabled"
RUNTIME_INVALID_ARSD_CONFIG = "runtime_invalid_arsd_config"
RUNTIME_ARSD_UNAVAILABLE = "runtime_arsd_unavailable"
RUNTIME_ARSD_VERSION_MISMATCH = "runtime_arsd_version_mismatch"
RUNTIME_ARSD_PROTOCOL_VIOLATION = "runtime_arsd_protocol_violation"
RUNTIME_ARSD_INVALID_REQUEST = "runtime_arsd_invalid_request"
RUNTIME_ARSD_POLICY_DENIED = "runtime_arsd_policy_denied"
RUNTIME_ARSD_UNKNOWN_TARGET = "runtime_arsd_unknown_target"
RUNTIME_ARSD_IDEMPOTENCY_CONFLICT = "runtime_arsd_idempotency_conflict"
RUNTIME_ARSD_BUSY = "runtime_arsd_busy"
RUNTIME_ARSD_SUBMISSION_INDETERMINATE = "runtime_arsd_submission_indeterminate"
RUNTIME_ARSD_SHUTTING_DOWN = "runtime_arsd_shutting_down"
RUNTIME_ARSD_INTERNAL = "runtime_arsd_internal"

ARSD_STABLE_CODES = frozenset(
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

# --------------------------------------------------------------------------- #
# Stable error mapping (plan §9)
# --------------------------------------------------------------------------- #
#: Closed mapping from the arsd v1 wire error codes (plus the official
#: client's local ``CLIENT`` code) to Sachima-owned stable codes. Mirrored
#: from the pinned 0.6.3 ``agent_run_supervisor.arsd.protocol.ERROR_CODES_V1``
#: — the contract test imports the real set and fails on drift, so this
#: mirror can never silently fall behind a pin bump.
_WIRE_CODE_TO_STABLE: dict[str, str] = {
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


def map_arsd_client_error_code(wire_code: Any) -> str:
    """Map one typed ``ArsdClientError.code`` to a Sachima-owned stable code.

    Anything off the closed wire set — wrong type, unknown token, casing
    drift — collapses to ``runtime_arsd_internal`` (fail closed). The input
    is never echoed, raised, or stored.
    """

    if type(wire_code) is not str:
        return RUNTIME_ARSD_INTERNAL
    return _WIRE_CODE_TO_STABLE.get(wire_code, RUNTIME_ARSD_INTERNAL)


# --------------------------------------------------------------------------- #
# ArsdSupervisorConfig (plan §5.2)
# --------------------------------------------------------------------------- #
ARSD_SUPERVISOR_CONFIG_TYPE = "sachima.runtime_spine.arsd_supervisor_config.v1"

#: Socket API v2 is the only protocol contract this adapter implements.
ARSD_REQUIRED_API_VERSION = 2

#: Repo root of this committed tree: private socket/workspace paths must live
#: outside it so daemon surfaces can never bind into the tracked worktree.
_REPO_ROOT = Path(__file__).resolve().parents[2]

_APPROVAL_REF_PREFIX = "approval_"
_WORKSPACE_REF_PREFIX = "ws_"
_POLICY_REF_PREFIX = "policy_"

#: Sanitized version shape for the expected daemon package version (mirrors
#: ``supervisor_library._VERSION_RE`` bounds).
_VERSION_RE = re.compile(r"^[0-9][0-9A-Za-z._+-]{0,31}$")

#: Opaque single-line wire tokens Sachima forwards but does not own the
#: grammar of (registered agent ids, model names, effort levels).
_WIRE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

#: Closed mirror of the pinned 0.6.3 ``native_acp.spec.RunLimits`` fields —
#: the contract test imports the real dataclass and fails on drift.
_RUN_LIMIT_KEYS = frozenset(
    {
        "startup_timeout_seconds",
        "turn_timeout_seconds",
        "cancel_grace_seconds",
        "max_stderr_bytes",
        "max_event_bytes",
        "max_events",
    }
)
_INT_RUN_LIMIT_KEYS = frozenset({"max_stderr_bytes", "max_event_bytes", "max_events"})
#: Closed per-field mirrors of the pinned 0.6.3 ``native_acp.spec`` RunLimits
#: ceilings, integer floors, and the coupled ``max_event_bytes * max_events``
#: byte budget — the contract test imports the real constants/dataclass and
#: fails on drift, so a limits policy the daemon would refuse as
#: INVALID_REQUEST is never admitted config.
_RUN_LIMIT_MAX: Mapping[str, int | float] = MappingProxyType(
    {
        "startup_timeout_seconds": 3_600.0,
        "turn_timeout_seconds": 86_400.0,
        "cancel_grace_seconds": 300.0,
        "max_stderr_bytes": 67_108_864,
        "max_event_bytes": 1_048_576,
        "max_events": 1_000_000,
    }
)
_RUN_LIMIT_MIN: Mapping[str, int] = MappingProxyType(
    {"max_stderr_bytes": 1, "max_event_bytes": 256, "max_events": 1}
)
_RUN_LIMIT_EVENT_BUDGET_BYTES = 1_073_741_824
_MAX_LIMIT_COUNT = 1_000_000_000

#: Closed D0+D1 grant allowlist: the approved plan admits read/search
#: observation capabilities only — never a write-capable kind, even where the
#: pinned wire protocol itself would accept one. Membership in the pinned
#: ``agent_run_supervisor.role.PERMISSION_KINDS`` domain is drift-locked by
#: the contract tests.
_GRANTABLE_CAPABILITIES = frozenset({"read", "search"})


# Every stable raiser suppresses exception context (``from None`` semantics):
# validation runs inside ``except`` blocks around stdlib parsing, and an
# unsuppressed ``__context__`` would render remote exception text through the
# stable error's chain.
def _invalid_config() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_ARSD_CONFIG) from None


def _safe_config_ref(value: Any) -> str:
    return _safe_id(value, code=RUNTIME_INVALID_ARSD_CONFIG)


def _safe_config_digest(value: Any) -> str:
    return _safe_digest(value, code=RUNTIME_INVALID_ARSD_CONFIG)


def _safe_wire_token(value: Any, *, code: str = RUNTIME_INVALID_ARSD_CONFIG) -> str:
    """One opaque single-line wire token (agent id / model / effort / run id)."""

    if type(value) is not str or _WIRE_TOKEN_RE.fullmatch(value) is None:
        raise SpineError(code) from None
    return value


def _private_abs_path(value: Any, *, code: str = RUNTIME_INVALID_ARSD_CONFIG) -> str:
    """A private absolute path outside the tracked repo.

    Private paths legitimately carry filesystem material, so they are
    validated here but never serialized and never run through the refs-only
    no-leak scan. This is the one shared ingress boundary for every external
    path value (config socket_path, workspace map values, request cwd):
    malformed path material — an embedded NUL, an unencodable component —
    fails closed with the caller-selected stable code instead of escaping
    ``pathlib`` as a raw ``ValueError``.
    """

    if type(value) is not str or not value or "\x00" in value:
        raise SpineError(code) from None
    path = Path(value)
    if not path.is_absolute():
        raise SpineError(code) from None
    try:
        resolved = path.resolve()
    except (ValueError, OSError):
        raise SpineError(code) from None
    if resolved == _REPO_ROOT or resolved.is_relative_to(_REPO_ROOT):
        raise SpineError(code) from None
    return value


def _prefixed_ref(value: Any, prefix: str) -> str:
    ref = _safe_config_ref(value)
    if not ref.startswith(prefix) or ref == prefix:
        _invalid_config()
    return ref


def _grant_capability(value: Any) -> str:
    """One admitted grant capability: safe shape AND on the closed read/search
    allowlist — an off-allowlist kind fails closed even where the pinned wire
    protocol would accept it."""

    token = safe_role_key(value, code=RUNTIME_INVALID_ARSD_CONFIG)
    if token not in _GRANTABLE_CAPABILITIES:
        _invalid_config()
    return token


def _limit_number(key: str, value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _invalid_config()
    maximum = _RUN_LIMIT_MAX[key]
    if key in _INT_RUN_LIMIT_KEYS:
        if not isinstance(value, int) or value < _RUN_LIMIT_MIN[key] or value > maximum:
            _invalid_config()
        return value
    try:
        number = float(value)
    except OverflowError:
        raise SpineError(RUNTIME_INVALID_ARSD_CONFIG) from None
    if not math.isfinite(number) or number <= 0 or number > maximum:
        _invalid_config()
    return number


def _owned_run_limits(value: Any) -> Mapping[str, int | float]:
    """One fully explicit, closed RunLimits-shaped mapping (owned copy).

    Every key of the pinned 0.6.3 ``RunLimits`` must be present — a partial
    policy would silently inherit daemon-side defaults, which is not an
    admitted bounded policy. Every field is bounded by the exact pinned
    per-field min/max, and the two event limits must also satisfy the pinned
    coupled byte budget.
    """

    if not isinstance(value, Mapping) or set(value) != _RUN_LIMIT_KEYS:
        _invalid_config()
    owned = {key: _limit_number(key, value[key]) for key in sorted(_RUN_LIMIT_KEYS)}
    if owned["max_event_bytes"] * owned["max_events"] > _RUN_LIMIT_EVENT_BUDGET_BYTES:
        _invalid_config()
    return MappingProxyType(owned)


def _owned_ref_map(value: Any, *, key_prefix: str, item: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        _invalid_config()
    owned: dict[str, Any] = {}
    for key, raw in value.items():
        owned[_prefixed_ref(key, key_prefix)] = item(raw)
    return MappingProxyType(dict(sorted(owned.items())))


def _owned_token_tuple(value: Any, item: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        _invalid_config()
    return tuple(item(entry) for entry in value)


def _check_arsd_config_fields(config: Any, *, normalize: bool = False) -> None:
    """Exact fail-closed validation of every config field.

    Runs from ``__post_init__`` (with ``normalize=True``, replacing every
    caller-supplied container with an owned immutable copy) and from
    :func:`validate_arsd_supervisor_config` at trust boundaries. Never echoes
    rejected material.
    """

    try:
        config_type = config.type
        approval_ref = config.approval_ref
        owner = config.owner
        namespace = config.namespace
        socket_path = config.socket_path
        agent_by_policy_ref = config.agent_by_policy_ref
        model_by_policy_ref = config.model_by_policy_ref
        effort_by_policy_ref = config.effort_by_policy_ref
        workspace_by_ref = config.workspace_by_ref
        run_limits_by_policy_ref = config.run_limits_by_policy_ref
        grant_ref = config.grant_ref
        grant_hash = config.grant_hash
        grant_role_hash = config.grant_role_hash
        grant_capabilities = config.grant_capabilities
        mcp_snapshot_hashes = config.mcp_snapshot_hashes
        credential_refs = config.credential_refs
        evidence_policy_hash = config.evidence_policy_hash
        recovery_policy_hash = config.recovery_policy_hash
        expected_package_version = config.expected_package_version
        required_api_version = config.required_api_version
        enabled = config.enabled
    except AttributeError:
        _invalid_config()

    if type(config_type) is not str or config_type != ARSD_SUPERVISOR_CONFIG_TYPE:
        _invalid_config()
    if type(enabled) is not bool:
        _invalid_config()
    _prefixed_ref(approval_ref, _APPROVAL_REF_PREFIX)
    _safe_config_ref(owner)
    _safe_config_ref(namespace)
    _private_abs_path(socket_path)

    # One coherent installed/daemon version: the declared expectation must be
    # the reviewed pin exactly, and only Socket API v2 is implemented here.
    if (
        type(expected_package_version) is not str
        or _VERSION_RE.fullmatch(expected_package_version) is None
        or expected_package_version != EXPECTED_AGENT_RUN_SUPERVISOR_VERSION
    ):
        _invalid_config()
    if (
        isinstance(required_api_version, bool)
        or type(required_api_version) is not int
        or required_api_version != ARSD_REQUIRED_API_VERSION
    ):
        _invalid_config()

    owned_agents = _owned_ref_map(
        agent_by_policy_ref, key_prefix=_POLICY_REF_PREFIX, item=_safe_wire_token
    )
    owned_models = _owned_ref_map(
        model_by_policy_ref, key_prefix=_POLICY_REF_PREFIX, item=_safe_wire_token
    )
    owned_efforts = _owned_ref_map(
        effort_by_policy_ref, key_prefix=_POLICY_REF_PREFIX, item=_safe_wire_token
    )
    owned_workspaces = _owned_ref_map(
        workspace_by_ref, key_prefix=_WORKSPACE_REF_PREFIX, item=_private_abs_path
    )
    owned_limits = _owned_ref_map(
        run_limits_by_policy_ref, key_prefix=_POLICY_REF_PREFIX, item=_owned_run_limits
    )

    _safe_config_ref(grant_ref)
    _safe_config_digest(grant_hash)
    _safe_config_digest(grant_role_hash)
    owned_capabilities = _owned_token_tuple(grant_capabilities, _grant_capability)
    owned_mcp_hashes = _owned_token_tuple(mcp_snapshot_hashes, _safe_config_digest)
    owned_credential_refs = _owned_token_tuple(credential_refs, _safe_config_ref)
    _safe_config_digest(evidence_policy_hash)
    _safe_config_digest(recovery_policy_hash)

    if normalize:
        object.__setattr__(config, "agent_by_policy_ref", owned_agents)
        object.__setattr__(config, "model_by_policy_ref", owned_models)
        object.__setattr__(config, "effort_by_policy_ref", owned_efforts)
        object.__setattr__(config, "workspace_by_ref", owned_workspaces)
        object.__setattr__(config, "run_limits_by_policy_ref", owned_limits)
        object.__setattr__(config, "grant_capabilities", owned_capabilities)
        object.__setattr__(config, "mcp_snapshot_hashes", owned_mcp_hashes)
        object.__setattr__(config, "credential_refs", owned_credential_refs)


@dataclass(frozen=True)
class ArsdSupervisorConfig:
    """Frozen, default-off config for the arsd Socket API v2 adapter.

    Carries only host-owned/private mappings and stable policy references —
    never a credential value, prompt, argv, or environment material. The
    private surfaces (``socket_path`` / ``workspace_by_ref``) are
    ``repr=False`` and there is deliberately no ``as_dict``/serialize method.
    ``__post_init__`` runs the full allowlist and replaces every
    caller-supplied container with an owned immutable copy, so later
    caller-side mutation can never drift a validated config.
    """

    type: str
    approval_ref: str
    owner: str
    namespace: str
    socket_path: str = field(repr=False)
    agent_by_policy_ref: Mapping[str, str]
    model_by_policy_ref: Mapping[str, str]
    effort_by_policy_ref: Mapping[str, str]
    workspace_by_ref: Mapping[str, str] = field(repr=False)
    run_limits_by_policy_ref: Mapping[str, Mapping[str, int | float]]
    grant_ref: str
    grant_hash: str
    grant_role_hash: str
    grant_capabilities: tuple[str, ...]
    mcp_snapshot_hashes: tuple[str, ...]
    credential_refs: tuple[str, ...]
    evidence_policy_hash: str
    recovery_policy_hash: str
    expected_package_version: str = EXPECTED_AGENT_RUN_SUPERVISOR_VERSION
    required_api_version: int = ARSD_REQUIRED_API_VERSION
    enabled: bool = False

    def __post_init__(self) -> None:
        _check_arsd_config_fields(self, normalize=True)


def validate_arsd_supervisor_config(config: Any) -> ArsdSupervisorConfig:
    """Re-validate a config at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that
    skip ``__post_init__``: a non-exact type or any unsafe field fails closed
    with the stable ``runtime_invalid_arsd_config`` code, never echoing the
    rejected material.
    """

    if type(config) is not ArsdSupervisorConfig:
        _invalid_config()
    _check_arsd_config_fields(config)
    return config


def require_enabled_arsd_supervisor_config(config: Any) -> ArsdSupervisorConfig:
    """The default-off gate: fail closed unless ``enabled`` is exactly True."""

    validated = validate_arsd_supervisor_config(config)
    if validated.enabled is not True:
        raise SpineError(RUNTIME_ARSD_DISABLED)
    return validated


# --------------------------------------------------------------------------- #
# Stable request identity (plan §6.1)
# --------------------------------------------------------------------------- #
#: Closed mirrors of the pinned 0.6.3 wire bounds/versions — contract tests
#: import the real protocol/spec modules and fail on drift.
ARSD_SPEC_SCHEMA_VERSION = 2
ARSD_MAX_PROMPT_BYTES = 262_144
ARSD_MAX_FRAME_BYTES = 1_048_576

_REQUEST_ID_DERIVATION_TAG = b"sachima-arsd-request-id-v1"
_SESSION_REUSE_MODES = frozenset({"none", "reuse"})


def _invalid_request() -> NoReturn:
    raise SpineError(RUNTIME_ARSD_INVALID_REQUEST) from None


def derive_arsd_request_id(task_id: Any, session_id: Any, dispatch_ref: Any) -> str:
    """The stable ``request_id`` for one admitted Sachima dispatch identity.

    Derived from ``(task_id, session_id, dispatch_ref)`` only — never from
    wall-clock time — so a retry of an uncertain submission reuses the exact
    same id. Length-prefixed hashing makes component-boundary shifts
    non-colliding. The result satisfies the arsd v1 request-id grammar.
    """

    parts = (
        _safe_id(task_id, code=RUNTIME_ARSD_INVALID_REQUEST),
        _safe_id(session_id, code=RUNTIME_ARSD_INVALID_REQUEST),
        _safe_id(dispatch_ref, code=RUNTIME_ARSD_INVALID_REQUEST),
    )
    material = bytearray(_REQUEST_ID_DERIVATION_TAG)
    for part in parts:
        encoded = part.encode("utf-8")
        material += len(encoded).to_bytes(8, "big")
        material += encoded
    return "sachima-" + hashlib.sha256(bytes(material)).hexdigest()


# --------------------------------------------------------------------------- #
# Submit request construction (plan §6.2)
# --------------------------------------------------------------------------- #
def _resolve_ref(mapping: Mapping[str, Any], ref: Any) -> Any:
    key = _safe_id(ref, code=RUNTIME_ARSD_INVALID_REQUEST)
    if key not in mapping:
        _invalid_request()
    return mapping[key]


def _wire_prompt_text(value: Any) -> str:
    if type(value) is not str or not value:
        _invalid_request()
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise SpineError(RUNTIME_ARSD_INVALID_REQUEST) from None
    if len(encoded) > ARSD_MAX_PROMPT_BYTES:
        _invalid_request()
    return value


def _wire_input_refs(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)):
        _invalid_request()
    refs: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            _invalid_request()
        ref, content_hash = item
        refs.append(
            {
                "ref": _safe_id(ref, code=RUNTIME_ARSD_INVALID_REQUEST),
                "content_hash": _safe_digest(
                    content_hash, code=RUNTIME_ARSD_INVALID_REQUEST
                ),
            }
        )
    return refs


def build_arsd_submit_payload(
    config: ArsdSupervisorConfig,
    *,
    agent_policy_ref: Any,
    model_policy_ref: Any,
    effort_policy_ref: Any,
    workspace_ref: Any,
    run_limits_policy_ref: Any,
    prompt_text: Any,
    session_reuse: Any = "none",
    ars_session_id: Any = None,
    expected_binding_hash: Any = None,
    input_refs: Any = (),
    cwd: Any = None,
    retry_of_run_id: Any = None,
) -> dict[str, Any]:
    """Build the exact Socket API v2 ``submit`` payload for one admitted turn.

    Every policy-facing value resolves through the enabled config's closed
    maps — an unknown ref fails closed; nothing is passed through verbatim.
    The result is caller-owned wire material (prompt text and private paths
    included): it must go to :meth:`ArsdClientFacade.submit` only and never
    into events, projections, logs, or serialized state. ``retry_of_run_id``
    is for an explicit recovery decision only — never an automatic retry.
    """

    validated = require_enabled_arsd_supervisor_config(config)

    reuse = session_reuse
    if type(reuse) is not str or reuse not in _SESSION_REUSE_MODES:
        _invalid_request()
    session_token: str | None
    if reuse == "reuse":
        session_token = _safe_wire_token(
            ars_session_id, code=RUNTIME_ARSD_INVALID_REQUEST
        )
    else:
        if ars_session_id is not None:
            _invalid_request()
        session_token = None

    binding_hash = (
        None
        if expected_binding_hash is None
        else _safe_digest(expected_binding_hash, code=RUNTIME_ARSD_INVALID_REQUEST)
    )
    retry_token = (
        None
        if retry_of_run_id is None
        else _safe_wire_token(retry_of_run_id, code=RUNTIME_ARSD_INVALID_REQUEST)
    )
    cwd_path = (
        None if cwd is None else _private_abs_path(cwd, code=RUNTIME_ARSD_INVALID_REQUEST)
    )

    request: dict[str, Any] = {
        "owner": validated.owner,
        "namespace": validated.namespace,
        "agent_id": _resolve_ref(validated.agent_by_policy_ref, agent_policy_ref),
        "session_reuse": reuse,
        "ars_session_id": session_token,
        "expected_binding_hash": binding_hash,
        "input_refs": _wire_input_refs(input_refs),
        "requested_model": _resolve_ref(
            validated.model_by_policy_ref, model_policy_ref
        ),
        "requested_effort": _resolve_ref(
            validated.effort_by_policy_ref, effort_policy_ref
        ),
        "grant_ref": validated.grant_ref,
        "grant_hash": validated.grant_hash,
        "grant_role_hash": validated.grant_role_hash,
        "grant_capabilities": list(validated.grant_capabilities),
        "mcp_snapshot_hashes": list(validated.mcp_snapshot_hashes),
        "credential_refs": list(validated.credential_refs),
        "limits": dict(
            _resolve_ref(validated.run_limits_by_policy_ref, run_limits_policy_ref)
        ),
        "evidence_policy_hash": validated.evidence_policy_hash,
        "recovery_policy_hash": validated.recovery_policy_hash,
        "schema_version": ARSD_SPEC_SCHEMA_VERSION,
    }
    return {
        "request": request,
        "prompt_text": _wire_prompt_text(prompt_text),
        "workspace_root": _resolve_ref(validated.workspace_by_ref, workspace_ref),
        "cwd": cwd_path,
        "retry_of_run_id": retry_token,
    }


def arsd_submit_payload_digest(payload: Mapping[str, Any]) -> str:
    """Canonical digest of one submit payload (byte-equivalence witness).

    A retry of an uncertain submission must reuse a byte-equivalent request;
    comparing digests proves equivalence without persisting the private
    payload anywhere.
    """

    if not isinstance(payload, Mapping):
        _invalid_request()
    try:
        text = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        _invalid_request()
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Exact response validators (plan §5.4 / §7.1 / §7.3)
# --------------------------------------------------------------------------- #
_SERVER_INFO_KEYS = frozenset(
    {"version", "api_version", "supported_api_versions", "v2_only_operations", "limits"}
)
#: Exact pinned 0.6.3 negotiation sets, as the daemon's ``server_info`` emits
#: them (``list(SUPPORTED_API_VERSIONS)`` / ``sorted(V2_ONLY_OPERATIONS)``) —
#: closed: only these exact values ever reach the repr-safe
#: :class:`ArsdServerInfo`. Drift-locked against the real protocol module by
#: the contract tests.
_ARSD_SUPPORTED_API_VERSIONS = (1, 2)
_ARSD_V2_ONLY_OPERATIONS = ("submit",)
#: The five limits the 0.6.3 daemon reports. The two byte bounds are protocol
#: constants and must equal our mirrors exactly; the three capacity limits are
#: operator-configured and must be usable and bounded
#: (``1 <= value <= _MAX_LIMIT_COUNT``) — an unbounded remote int never
#: reaches the repr-safe observation.
_SERVER_INFO_LIMIT_KEYS = frozenset(
    {
        "max_concurrent_runs",
        "max_frame_bytes",
        "max_prompt_bytes",
        "events_page_limit",
        "event_follow_queue_size",
    }
)
_SUBMIT_RESULT_KEYS = frozenset({"run_id", "accepted_at"})
_RUN_EVENTS_PAGE_KEYS = frozenset({"run_id", "events", "next_from_seq", "exhausted"})
_TRUNCATION_MARKER_KEYS = frozenset({"seq", "type", "truncated", "truncate_reason"})
_TRUNCATION_MARKER_REASON = "response_budget"
_MAX_TIMESTAMP_CHARS = 64


def _protocol_violation() -> NoReturn:
    raise SpineError(RUNTIME_ARSD_PROTOCOL_VIOLATION) from None


def _version_mismatch() -> NoReturn:
    raise SpineError(RUNTIME_ARSD_VERSION_MISMATCH) from None


def _wire_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _protocol_violation()
    return value


@dataclass(frozen=True)
class ArsdServerInfo:
    """One validated, negotiation-passing ``server_info`` observation.

    Carries closed structural data only (versions and integer limits) — safe
    for reprs and diagnostics; still deliberately without a serialize surface.
    """

    version: str
    api_version: int
    supported_api_versions: tuple[int, ...]
    v2_only_operations: tuple[str, ...]
    limits: Mapping[str, int]


def validate_arsd_server_info(
    payload: Any, *, config: ArsdSupervisorConfig
) -> ArsdServerInfo:
    """Exact Socket API v2 preflight negotiation (plan §5.4).

    Malformed shape → ``runtime_arsd_protocol_violation``. A structurally
    well-formed reply that fails package/API/limit compatibility → the single
    stable ``runtime_arsd_version_mismatch`` backend-unavailable code. Never
    falls back silently. The negotiation sets are closed: only the exact
    pinned ``[1, 2]`` / ``["submit"]`` values ever reach
    :class:`ArsdServerInfo`, so no remote string survives into a repr surface.
    """

    validated = validate_arsd_supervisor_config(config)
    if not isinstance(payload, Mapping) or set(payload) != _SERVER_INFO_KEYS:
        _protocol_violation()

    version = payload["version"]
    if type(version) is not str or _VERSION_RE.fullmatch(version) is None:
        _protocol_violation()

    api_version = _wire_int(payload["api_version"])

    supported_raw = payload["supported_api_versions"]
    if not isinstance(supported_raw, list) or not supported_raw:
        _protocol_violation()
    supported = tuple(_wire_int(item) for item in supported_raw)

    v2_only_raw = payload["v2_only_operations"]
    if not isinstance(v2_only_raw, list):
        _protocol_violation()
    for op in v2_only_raw:
        if type(op) is not str or _WIRE_TOKEN_RE.fullmatch(op) is None:
            _protocol_violation()

    limits_raw = payload["limits"]
    if not isinstance(limits_raw, Mapping) or set(limits_raw) != _SERVER_INFO_LIMIT_KEYS:
        _protocol_violation()
    limits = {key: _wire_int(limits_raw[key]) for key in sorted(_SERVER_INFO_LIMIT_KEYS)}

    # Compatibility verdicts (well-formed but not the contract we implement).
    if version != validated.expected_package_version:
        _version_mismatch()
    if api_version != validated.required_api_version:
        _version_mismatch()
    if supported != _ARSD_SUPPORTED_API_VERSIONS:
        _version_mismatch()
    if tuple(v2_only_raw) != _ARSD_V2_ONLY_OPERATIONS:
        _version_mismatch()
    if limits["max_frame_bytes"] != ARSD_MAX_FRAME_BYTES:
        _version_mismatch()
    if limits["max_prompt_bytes"] != ARSD_MAX_PROMPT_BYTES:
        _version_mismatch()
    for capacity_key in (
        "max_concurrent_runs",
        "events_page_limit",
        "event_follow_queue_size",
    ):
        if limits[capacity_key] < 1 or limits[capacity_key] > _MAX_LIMIT_COUNT:
            _version_mismatch()

    return ArsdServerInfo(
        version=version,
        api_version=api_version,
        supported_api_versions=_ARSD_SUPPORTED_API_VERSIONS,
        v2_only_operations=_ARSD_V2_ONLY_OPERATIONS,
        limits=MappingProxyType(limits),
    )


@dataclass(frozen=True)
class ArsdSubmitAccepted:
    """Durable acceptance of one submit: ``run_id`` stays a private locator."""

    run_id: str = field(repr=False)
    accepted_at: str


def validate_arsd_submit_result(payload: Any) -> ArsdSubmitAccepted:
    """Exact ``submit`` result shape: ``{run_id, accepted_at}`` only."""

    if not isinstance(payload, Mapping) or set(payload) != _SUBMIT_RESULT_KEYS:
        _protocol_violation()
    run_id = _safe_wire_token(
        payload["run_id"], code=RUNTIME_ARSD_PROTOCOL_VIOLATION
    )
    accepted_at = payload["accepted_at"]
    if (
        type(accepted_at) is not str
        or not accepted_at
        or len(accepted_at) > _MAX_TIMESTAMP_CHARS
        or "\n" in accepted_at
        or "\r" in accepted_at
    ):
        _protocol_violation()
    try:
        moment = _dt.datetime.fromisoformat(accepted_at)
    except ValueError:
        _protocol_violation()
    if moment.tzinfo is None:
        _protocol_violation()
    return ArsdSubmitAccepted(run_id=run_id, accepted_at=accepted_at)


def _is_truncation_marker(event: Mapping[str, Any]) -> bool:
    return (
        set(event) == _TRUNCATION_MARKER_KEYS
        and event["truncated"] is True
        and event["truncate_reason"] == _TRUNCATION_MARKER_REASON
        and type(event["type"]) is str
    )


@dataclass(frozen=True)
class ArsdRunEventsPage:
    """One validated bounded ``run_events`` page.

    ``run_id`` and the raw event evidence are private (``repr=False``, no
    serialize surface). ``resume_cursor`` / ``has_more`` are the foreign
    read-model cursor translation (plan §7.3): resuming with
    ``from_seq=resume_cursor`` neither duplicates nor drops records. The
    cursor never becomes Sachima ``TaskEventLog.seq``.
    """

    run_id: str = field(repr=False)
    events: tuple[dict[str, Any], ...] = field(repr=False)
    next_from_seq: int
    exhausted: bool
    has_truncation_marker: bool

    @property
    def resume_cursor(self) -> int:
        return self.next_from_seq

    @property
    def has_more(self) -> bool:
        return not self.exhausted


def validate_arsd_run_events_page(
    payload: Any, *, run_id: Any, from_seq: Any
) -> ArsdRunEventsPage:
    """Exact non-follow ``run_events`` page validation (plan §7.1/§7.3).

    Verifies the run echo, the closed page shape, strictly ascending post-
    cursor sequences, exact ``next_from_seq`` semantics (highest returned
    sequence; the request cursor on an empty page), and byte-budget
    truncation-marker pages (one closed marker event with
    ``exhausted=False``). Raw event bodies are copied, owned, and kept
    private — validation never reads or echoes their content.
    """

    expected_run = _safe_wire_token(run_id, code=RUNTIME_ARSD_INVALID_REQUEST)
    if isinstance(from_seq, bool) or not isinstance(from_seq, int) or from_seq < 0:
        _invalid_request()

    if not isinstance(payload, Mapping) or set(payload) != _RUN_EVENTS_PAGE_KEYS:
        _protocol_violation()
    if payload["run_id"] != expected_run:
        _protocol_violation()

    events_raw = payload["events"]
    if not isinstance(events_raw, list):
        _protocol_violation()

    owned_events: list[dict[str, Any]] = []
    last_seq = from_seq
    marker_count = 0
    for event in events_raw:
        if not isinstance(event, Mapping):
            _protocol_violation()
        seq = event.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int):
            _protocol_violation()
        if seq <= last_seq:
            _protocol_violation()
        last_seq = seq
        try:
            owned = json.loads(json.dumps(dict(event)))
        except (TypeError, ValueError, RecursionError):
            _protocol_violation()
        if _is_truncation_marker(owned):
            marker_count += 1
        owned_events.append(owned)

    next_from_seq = payload["next_from_seq"]
    if isinstance(next_from_seq, bool) or not isinstance(next_from_seq, int):
        _protocol_violation()
    if next_from_seq != last_seq:
        _protocol_violation()

    exhausted = payload["exhausted"]
    if type(exhausted) is not bool:
        _protocol_violation()

    # A byte-budget truncation marker only ever stands alone on a page the
    # daemon reports as not exhausted (mirrors the 0.6.3 handler).
    if marker_count and (marker_count != 1 or len(owned_events) != 1 or exhausted):
        _protocol_violation()

    return ArsdRunEventsPage(
        run_id=expected_run,
        events=tuple(owned_events),
        next_from_seq=next_from_seq,
        exhausted=exhausted,
        has_truncation_marker=marker_count == 1,
    )


# --------------------------------------------------------------------------- #
# Injected client facade boundary (plan §5.3)
# --------------------------------------------------------------------------- #
#: Mirror of the arsd v1 request-id grammar (``[A-Za-z0-9._-]``, 1..128).
_WIRE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

#: The official client's *local* transport-loss raises during a roundtrip —
#: always its exact base class: ``INTERNAL`` for a socket write/read failure
#: or a clean close before any reply, ``MALFORMED_FRAME`` for a reply
#: truncated by connection loss. Daemon-declared errors arrive as typed
#: subclasses and therefore never match together with the base-class check.
_LOCAL_TRANSPORT_LOSS_CODES = frozenset({"INTERNAL", "MALFORMED_FRAME"})


@runtime_checkable
class ArsdClientFacade(Protocol):
    """The injected Socket API v2 client boundary the D2+ backend depends on.

    Implementations perform exactly one bounded daemon operation per call and
    return the raw result mapping; validation stays in the pure
    ``validate_arsd_*`` functions. Tests inject doubles; production uses
    :class:`DefaultArsdClientFacade`.
    """

    def server_info(self) -> Mapping[str, Any]: ...

    def submit(
        self, *, request_id: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def run_events(
        self, run_id: str, *, from_seq: int, limit: int | None = None
    ) -> Mapping[str, Any]: ...


class DefaultArsdClientFacade:
    """Production facade over the official ``ArsdClient`` — lazy and short-lived.

    * ``agent_run_supervisor.arsd.client`` is imported only inside operations,
      never at module import; an import failure is the stable
      ``runtime_arsd_unavailable`` code.
    * Every bounded operation opens one fresh official client, performs one
      request/response roundtrip with ``follow=False`` semantics only, and
      closes the connection — no client is retained, so a fresh client after
      connection loss holds structurally and closing never cancels a Run.
    * Typed client failures are collapsed to Sachima stable codes through
      :func:`map_arsd_client_error_code`; connect-phase failures are
      ``runtime_arsd_unavailable``. The mapping is operation-aware: once a
      ``submit`` frame may have been sent, a local transport loss before a
      complete reply is ``runtime_arsd_submission_indeterminate`` — the
      daemon may already hold the run, so the outcome is surfaced for an
      explicit recovery decision and never retried here. Remote/exception
      text is never chained, echoed, or stored, and there is no silent
      fallback to the library backend or a CLI.
    """

    def __init__(self, config: ArsdSupervisorConfig) -> None:
        self._config = require_enabled_arsd_supervisor_config(config)

    @staticmethod
    def _client_module() -> Any:
        import importlib

        try:
            return importlib.import_module("agent_run_supervisor.arsd.client")
        except Exception:
            raise SpineError(RUNTIME_ARSD_UNAVAILABLE) from None

    def _operate(self, op: Any, *, submission: bool = False) -> dict[str, Any]:
        module = self._client_module()
        try:
            client = module.ArsdClient(self._config.socket_path)
        except Exception:
            raise SpineError(RUNTIME_ARSD_UNAVAILABLE) from None
        # One guarded lifecycle: after construction, close() is attempted
        # exactly once no matter what; a close failure surfaces as the stable
        # local code only when no stable error is already active.
        error: SpineError | None = None
        result: Any = None
        try:
            client.connect()
        except Exception:
            error = SpineError(RUNTIME_ARSD_UNAVAILABLE)
        if error is None:
            try:
                result = op(client)
            except SpineError as spine_error:
                error = spine_error
            except Exception as err:
                # The official client raises its exact base class for *local*
                # integrity failures; a daemon-declared error always arrives
                # as a typed subclass. A base-class INVALID_REQUEST is
                # therefore a response-correlation failure (an off-contract
                # reply), never a daemon verdict on our admitted request. A
                # base-class transport-loss code during a submission means
                # the frame may have reached the daemon with its verdict
                # unread: that outcome is indeterminate — never internal,
                # never retried here.
                code = getattr(err, "code", None)
                if type(err) is getattr(module, "ArsdClientError", None):
                    if code == "INVALID_REQUEST":
                        error = SpineError(RUNTIME_ARSD_PROTOCOL_VIOLATION)
                    elif submission and code in _LOCAL_TRANSPORT_LOSS_CODES:
                        error = SpineError(RUNTIME_ARSD_SUBMISSION_INDETERMINATE)
                    else:
                        error = SpineError(map_arsd_client_error_code(code))
                else:
                    error = SpineError(map_arsd_client_error_code(code))
        try:
            client.close()
        except Exception:
            if error is None:
                error = SpineError(RUNTIME_ARSD_UNAVAILABLE)
        if error is not None:
            raise error
        if not isinstance(result, dict):
            _protocol_violation()
        return result

    def server_info(self) -> Mapping[str, Any]:
        return self._operate(lambda client: client.server_info())

    def submit(
        self, *, request_id: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if type(request_id) is not str or _WIRE_REQUEST_ID_RE.fullmatch(request_id) is None:
            _invalid_request()
        if not isinstance(payload, Mapping):
            _invalid_request()
        return self._operate(
            lambda client: client.submit(request_id=request_id, payload=payload),
            submission=True,
        )

    def run_events(
        self, run_id: str, *, from_seq: int, limit: int | None = None
    ) -> Mapping[str, Any]:
        token = _safe_wire_token(run_id, code=RUNTIME_ARSD_INVALID_REQUEST)
        if isinstance(from_seq, bool) or not isinstance(from_seq, int) or from_seq < 0:
            _invalid_request()
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
        ):
            _invalid_request()
        return self._operate(
            lambda client: client.run_events(
                token, from_seq=from_seq, limit=limit, follow=False
            )
        )
