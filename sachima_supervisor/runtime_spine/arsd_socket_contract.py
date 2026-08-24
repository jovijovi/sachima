"""P1 offline Socket API v3 contract boundary for the external ``arsd`` daemon.

This module is the ARS 0.7.6 Socket API v3 integration plan's P1 slice
(``docs/plans/2026-08-17-ars-0.7.6-socket-api-v3-integration-plan.md``): the
pure, offline contract foundation Sachima will later (P2+) compose into a
Runtime Spine backend. It contains the default-off
:class:`ArsdSupervisorConfig`, the injected :class:`ArsdClientFacade` boundary
with its lazy short-lived :class:`DefaultArsdClientFacade`, stable request
identity, exact submit request construction, the exact ``server_info`` /
``submit`` / ``run_status`` / ``run_events`` / ``run_cancel`` /
``session_status`` / ``session_list`` / ``agent_list`` response validators, the
admission-product pre-check, and a small Sachima-owned stable error mapping.

Every protocol constant here is a **mirror** of the installed exact-pinned
distribution, drift-locked by the contract tests: if a mirror and the
distribution disagree, the mirror is the bug.

Boundaries:

* **Default-off.** ``ArsdSupervisorConfig.enabled`` defaults to ``False`` and
  :func:`require_enabled_arsd_supervisor_config` fails closed with a stable
  code unless it is exactly ``True``. Nothing here is wired into Runtime
  Spine, Gateway, or any composition root — that is P2+.
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
from .events import SpineError, _safe_digest, _safe_id

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
    "ARSD_AGENT_ID_PATTERN",
    "ARSD_FINAL_MESSAGE_TRUNCATE_REASON",
    "ARSD_MAX_ERROR_MESSAGE_CHARS",
    "ARSD_MAX_FIELD_CHARS",
    "ARSD_MAX_FINAL_MESSAGE_BYTES",
    "ARSD_MAX_FRAME_BYTES",
    "ARSD_MAX_JSON_NESTING_DEPTH",
    "ARSD_MAX_PROMPT_BYTES",
    "ARSD_MAX_REGISTERED_AGENTS",
    "ARSD_MAX_SESSION_ID_CHARS",
    "ARSD_OPERATIONS",
    "ARSD_PERMISSION_VIOLATION_REASON",
    "ARSD_SESSION_ID_PATTERN",
    "ARSD_SPEC_SCHEMA_VERSION",
    "ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES",
    "ARSD_TERMINAL_STATUSES",
    "ArsdClientFacade",
    "ArsdRunCancelObservation",
    "ArsdRunEventsPage",
    "ArsdRunStatusObservation",
    "ArsdServerInfo",
    "ArsdSessionView",
    "ArsdSealedGrant",
    "ArsdSubmitAccepted",
    "ArsdTerminalResult",
    "DefaultArsdClientFacade",
    "ArsdSupervisorConfig",
    "arsd_submit_payload_digest",
    "build_arsd_submit_payload",
    "check_arsd_admission_event_budget",
    "derive_arsd_request_id",
    "derive_arsd_sealed_grant",
    "map_arsd_client_error_code",
    "project_arsd_terminal_result",
    "require_enabled_arsd_supervisor_config",
    "validate_arsd_agent_list",
    "validate_arsd_run_cancel_result",
    "validate_arsd_run_events_page",
    "validate_arsd_run_status",
    "validate_arsd_server_info",
    "validate_arsd_session_list",
    "validate_arsd_session_view",
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
# Stable error mapping (Spec §13)
# --------------------------------------------------------------------------- #
#: Closed mapping from the arsd Socket API v3 wire error codes (plus the
#: official client's local ``CLIENT`` code) to Sachima-owned stable codes.
#: Mirrored from the pinned 0.7.6
#: ``agent_run_supervisor.arsd.protocol.ERROR_CODES`` — the contract test
#: imports the real set and fails on drift, so this mirror can never silently
#: fall behind a pin bump. The 17-code set is unchanged from 0.6.3; only the
#: symbol name moved (Spec D-9).
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
# ArsdSupervisorConfig (Spec §12.2)
# --------------------------------------------------------------------------- #
ARSD_SUPERVISOR_CONFIG_TYPE = "sachima.runtime_spine.arsd_supervisor_config.v1"

#: Socket API v3 is the only protocol contract this adapter implements. There
#: is no per-operation version matrix and no drain window: the verdict is
#: taken on the envelope (Spec §5.2).
ARSD_REQUIRED_API_VERSION = 3

#: The closed eight-operation set of Socket API v3. There is no
#: ``session_close`` — Runs terminate, Sessions do not close (Spec §5.1/§6.1).
#: Drift-locked against ``protocol.OPERATIONS``.
#:
#: ``agent_list`` arrived in 0.7.8 as a purely additive read-only roster
#: operation: the other seven kept their names and payload contracts, so the
#: wire stayed v3. It is required rather than optional here — a daemon whose
#: ``server_info`` omits it is refused at negotiation, because there is no
#: roster-less admission path to degrade into.
ARSD_OPERATIONS = frozenset(
    {
        "server_info",
        "submit",
        "run_status",
        "run_events",
        "run_cancel",
        "session_status",
        "session_list",
        "agent_list",
    }
)

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
#: grammar of (registered agent ids, effort levels, run ids).
#:
#: Model selectors are deliberately **not** in this family any more: the
#: pinned request validates ``requested_model`` as bounded printable text,
#: and the configured Claude selector ``opus[1m]`` is unspellable here. See
#: :func:`_safe_config_text`.
_WIRE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

#: The **canonical** ``agent_id`` grammar, mirrored verbatim from the pinned
#: distribution's ``native_acp.agent_registration.AGENT_ID_RE`` — the one
#: grammar the daemon shares between its registry parse and its admission. It
#: is narrower than :data:`_WIRE_TOKEN_RE` on purpose: an agent id is
#: lowercase-only and bounded at 64 characters, so ``Codex`` is not a spelling
#: of ``codex``, it is simply not an agent id. Drift-locked by the contract
#: tests against the imported real module.
ARSD_AGENT_ID_PATTERN = r"[a-z0-9][a-z0-9._-]{0,63}"
_AGENT_ID_RE = re.compile(ARSD_AGENT_ID_PATTERN)

#: The bound on one roster reply. The daemon's roster is a startup snapshot of
#: a reviewed registry file, so a reply carrying thousands of ids is not a
#: large deployment — it is a reply this integration declines to iterate.
#: Sachima-owned (the protocol states no bound), which is why it is generous
#: enough that no real registry meets it.
ARSD_MAX_REGISTERED_AGENTS = 256

#: The bound the pinned 0.7.6 ``AgentRunRequest`` applies to a plain text
#: field (``native_acp.spec._require_text``'s default). Mirrored, not
#: imported, and drift-locked behaviourally in the contract tests against a
#: real request rather than against a private symbol. It is the same pinned
#: bound :data:`ARSD_MAX_SESSION_ID_CHARS` mirrors for Session ids, kept as
#: its own name because the two fields are validated by different grammars.
ARSD_MAX_FIELD_CHARS = 512

#: Closed mirror of the pinned 0.7.6 ``native_acp.spec.RunLimits`` fields —
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
#: Closed per-field mirrors of the pinned 0.7.6 ``native_acp.spec`` RunLimits
#: defaults, ceilings, and integer floors — the contract test imports the real
#: constants/dataclass and fails on drift, so a limits policy the daemon would
#: refuse as INVALID_REQUEST is never admitted config, and no timeout or byte
#: number here is one Sachima chose for itself. ``turn_timeout_seconds``
#: moved in 0.7.2 (default 600.0 -> 21600.0, maximum 86400.0 -> 604800.0,
#: inclusive); startup-timeout and cancel-grace are unchanged.
_RUN_LIMIT_DEFAULTS: Mapping[str, int | float] = MappingProxyType(
    {
        "startup_timeout_seconds": 60.0,
        "turn_timeout_seconds": 21_600.0,
        "cancel_grace_seconds": 10.0,
        "max_stderr_bytes": 262_144,
        "max_event_bytes": 65_536,
        "max_events": 10_000,
    }
)
_RUN_LIMIT_MAX: Mapping[str, int | float] = MappingProxyType(
    {
        "startup_timeout_seconds": 3_600.0,
        "turn_timeout_seconds": 604_800.0,
        "cancel_grace_seconds": 300.0,
        "max_stderr_bytes": 67_108_864,
        "max_event_bytes": 1_048_576,
        "max_events": 1_000_000,
    }
)
_RUN_LIMIT_MIN: Mapping[str, int] = MappingProxyType(
    {"max_stderr_bytes": 1, "max_event_bytes": 256, "max_events": 1}
)

#: Mirror of ``native_acp.spec.STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES``, which
#: is ``LIMIT_MAX_EVENT_BYTES_MAX * LIMIT_MAX_EVENTS_MAX``. This is a
#: **maximum**, never a default: the daemon's *deployment* default is
#: operator-configured (4 GiB at 0.7.6) and is deliberately not mirrored,
#: because asserting it would fail against any validly reconfigured daemon.
#: The value a Run is actually admitted against is the negotiated
#: ``server_info.limits.max_run_event_budget_bytes`` (Spec §5.3.1).
ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES = 1_048_576_000_000
_MAX_LIMIT_COUNT = 1_000_000_000

#: Closed grant allowlist: the exact capability vocabulary the configured
#: **author** role requires — ``read``/``search`` to observe a workspace and
#: ``write``/``execute`` to author in it. It is a strict subset of the pinned
#: ``agent_run_supervisor.native_acp.spec.PERMISSION_KINDS`` domain, and the
#: contract tests drift-lock it against that domain in both directions.
#:
#: The earlier read/search-only projection is retired, not narrowed by accident:
#: it could not express the grant the deployed 0.7.6 role is configured with, so
#: every author config failed closed at construction and no supervised authoring
#: Run could be admitted at all. Widening to the author vocabulary is not a
#: licence to carry the rest of the domain — ``delete``, ``move``, ``terminal``,
#: ``fetch``, ``switch_mode`` and ``other`` are admitted by the daemon and
#: refused here, because this role does not require them.
_GRANTABLE_CAPABILITIES = frozenset({"read", "search", "write", "execute"})


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
    """One opaque single-line wire token (agent id / effort / run id)."""

    if type(value) is not str or _WIRE_TOKEN_RE.fullmatch(value) is None:
        raise SpineError(code) from None
    return value


def _safe_config_text(value: Any, *, code: str = RUNTIME_INVALID_ARSD_CONFIG) -> str:
    """One bounded printable wire **text** field (namespace / model selector).

    These two are not identifier-like and never were: the pinned 0.7.6
    request validates ``namespace`` and ``requested_model`` with
    ``native_acp.spec._require_text`` — non-empty, printable, at most
    :data:`ARSD_MAX_FIELD_CHARS` characters — and the daemon then
    exact-matches ``(owner, namespace)`` against the caller's registration.
    Validating them through the safe-id / wire-token grammars refused the
    values the deployed route is actually configured with (the registered
    namespace ``hermes/default`` and the selector ``opus[1m]``), so no
    deployable config could submit at all.

    This is a **separation, not a widening**: owner, agent id, effort,
    grant/approval/credential refs, digests, run ids and Session ids keep
    their exact narrow grammars, and the contract tests lock that split in
    both directions. Mirroring the pinned rule exactly is also what keeps
    the refusal honest — Sachima never admits text the daemon would reject.

    ``str.isprintable()`` is the pinned predicate and already excludes every
    control character (newline, tab, carriage return, NUL), so the field
    stays single-line without a second rule. Rejected material is never
    echoed: the raised message IS the stable code.
    """

    if type(value) is not str or not value or len(value) > ARSD_MAX_FIELD_CHARS:
        raise SpineError(code) from None
    if not value.isprintable():
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
    """One admitted grant capability: safe shape AND on the closed allowlist.

    The membership check is the whole gate. It deliberately does **not** run
    the launch-spec role heuristic on the way in: that heuristic refuses any
    identifier merely *containing* ``write``, which is right for a Sachima role
    key and wrong for a capability name the deployed daemon defines — it would
    refuse ``write`` itself, so the closed allowlist below could never admit the
    author vocabulary it names. An off-allowlist kind still fails closed, even
    where the pinned wire protocol would accept it.
    """

    token = _safe_id(value, code=RUNTIME_INVALID_ARSD_CONFIG)
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

    Every key of the pinned 0.7.6 ``RunLimits`` must be present — a partial
    policy would silently inherit daemon-side defaults, which is not an
    admitted bounded policy. Every field is bounded by the exact pinned
    per-field min/max, and the coupled ``max_event_bytes * max_events``
    product must stay within the structural maximum the daemon's own parse
    path applies.

    Per-field validity does **not** imply admissibility: whether *this*
    daemon accepts the product is a policy question against its negotiated
    ``max_run_event_budget_bytes``, answered per admission by
    :func:`check_arsd_admission_event_budget` (Spec §5.6.2).
    """

    if not isinstance(value, Mapping) or set(value) != _RUN_LIMIT_KEYS:
        _invalid_config()
    owned = {key: _limit_number(key, value[key]) for key in sorted(_RUN_LIMIT_KEYS)}
    if (
        owned["max_event_bytes"] * owned["max_events"]
        > ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES
    ):
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


def _owned_capability_set(value: Any) -> tuple[str, ...]:
    """One non-empty, duplicate-free capability set in canonical order.

    Sorted rather than as-written: the set *is* the identity a sealed grant is
    derived from, so two operators who typed the same capabilities in a
    different order must get the same grant, not two.
    """

    tokens = _owned_token_tuple(value, _grant_capability)
    if not tokens or len(set(tokens)) != len(tokens):
        _invalid_config()
    return tuple(sorted(tokens))


def _owned_grant_map(value: Any) -> Mapping[str, tuple[str, ...]]:
    """The optional per-policy grant map; an empty map is a real answer."""

    if isinstance(value, Mapping) and not value:
        return MappingProxyType({})
    return _owned_ref_map(
        value, key_prefix=_POLICY_REF_PREFIX, item=_owned_capability_set
    )


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
        binding_ledger_path = config.binding_ledger_path
        agent_by_policy_ref = config.agent_by_policy_ref
        model_by_policy_ref = config.model_by_policy_ref
        effort_by_policy_ref = config.effort_by_policy_ref
        workspace_by_ref = config.workspace_by_ref
        run_limits_by_policy_ref = config.run_limits_by_policy_ref
        grant_ref = config.grant_ref
        grant_hash = config.grant_hash
        grant_role_hash = config.grant_role_hash
        grant_capabilities = config.grant_capabilities
        grant_by_policy_ref = config.grant_by_policy_ref
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
    _safe_config_text(namespace)
    _private_abs_path(socket_path)
    _private_abs_path(binding_ledger_path)

    # One coherent installed/daemon version: the declared expectation must be
    # the reviewed pin exactly, and only Socket API v3 is implemented here.
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
        model_by_policy_ref, key_prefix=_POLICY_REF_PREFIX, item=_safe_config_text
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
    owned_grants = _owned_grant_map(grant_by_policy_ref)
    # A per-policy grant chooses among what the operator already approved
    # config-wide. It may narrow; it may never widen, and a set that tries is
    # a config error rather than a request the daemon gets to refuse.
    approved = set(owned_capabilities)
    for capabilities in owned_grants.values():
        if not set(capabilities).issubset(approved):
            _invalid_config()
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
        object.__setattr__(config, "grant_by_policy_ref", owned_grants)
        object.__setattr__(config, "mcp_snapshot_hashes", owned_mcp_hashes)
        object.__setattr__(config, "credential_refs", owned_credential_refs)


@dataclass(frozen=True)
class ArsdSupervisorConfig:
    """Frozen, default-off config for the arsd Socket API v3 adapter.

    Carries only host-owned/private mappings and stable policy references —
    never a credential value, prompt, argv, or environment material. The
    private surfaces (``socket_path`` / ``binding_ledger_path`` /
    ``workspace_by_ref``) are ``repr=False`` and there is deliberately no
    ``as_dict``/serialize method. ``__post_init__`` runs the full allowlist
    and replaces every caller-supplied container with an owned immutable copy,
    so later caller-side mutation can never drift a validated config.

    The field set does not grow for 0.7.6 beyond ``binding_ledger_path``: no
    profile-source, ACP-mode, or event-budget field exists here. Profile
    sources are operator territory and the event budget is read from
    ``server_info``, never declared by Sachima (Spec §12.2).
    """

    type: str
    approval_ref: str
    owner: str
    namespace: str
    socket_path: str = field(repr=False)
    #: Absolute host-owned private path, outside the tracked repo, for the
    #: durable ``(task_id, session_id, dispatch_ref)`` -> Run/Session binding
    #: ledger. P1 validates it; P2 owns the module that writes it.
    binding_ledger_path: str = field(repr=False)
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
    #: Optional per-``agent_policy_ref`` narrowings of ``grant_capabilities``.
    #: The capability set is what the daemon's permission bridge freezes for a
    #: Run, so one global grant would hand a review AGENT the same authority
    #: as an implementing one. An entry here is the exact set that policy's
    #: Runs are sealed under; a policy with no entry keeps the global grant.
    grant_by_policy_ref: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
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
# Stable request identity (Spec §7.1)
# --------------------------------------------------------------------------- #
#: Closed mirrors of the pinned 0.7.6 wire bounds/versions — contract tests
#: import the real protocol/spec modules and fail on drift.
ARSD_SPEC_SCHEMA_VERSION = 3
ARSD_MAX_PROMPT_BYTES = 262_144
ARSD_MAX_FRAME_BYTES = 1_048_576
#: Applies to every frame in both directions (``protocol.MAX_JSON_NESTING_DEPTH``).
ARSD_MAX_JSON_NESTING_DEPTH = 64
#: The true wire maximum for a remote ``error.message``. Sachima discards that
#: text entirely; the mirror exists so the discard witness in the contract
#: tests stays pinned to the real bound (review closure R-4).
ARSD_MAX_ERROR_MESSAGE_CHARS = 512

#: Mirror of ``agent_run_supervisor.session.SESSION_ID_PATTERN``. Note there
#: are **no dots**: the retired wire-token grammar accepted them and the
#: Session grammar does not, so Session ids need their own validator
#: (Spec D-12).
ARSD_SESSION_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_\-]*"
_SESSION_ID_RE = re.compile(ARSD_SESSION_ID_PATTERN)
#: The bound the real ``AgentRunRequest`` applies to ``session_id``; locked
#: behaviourally against the distribution rather than copied from a private
#: symbol, so an unbounded remote id never reaches a Sachima surface.
ARSD_MAX_SESSION_ID_CHARS = 512

#: Mirror of the five-member Native ACP terminal vocabulary
#: (``exit_classifier.AgentRunStatus``), in declaration order.
ARSD_TERMINAL_STATUSES = ("completed", "failed", "cancelled", "timed_out", "unknown")

#: The 0.7.6 terminal *reason* for a denied tool call later reported completed
#: (Δ-15). It is not a sixth terminal status and never becomes user-visible
#: text; it maps to a Sachima-owned stable failure category like any other
#: trusted terminal failure.
ARSD_PERMISSION_VIOLATION_REASON = "PERMISSION_VIOLATION"

#: Mirrors of the closed quarantine evidence vocabulary
#: (``session.QUARANTINE_REASON_CODES`` / ``QUARANTINE_EVIDENCE_FIELDS``).
_QUARANTINE_REASON_CODES = frozenset(
    {
        "DISPATCH_OBSERVATION_LOST",
        "DISPATCH_WITHOUT_TRUSTWORTHY_TERMINAL",
        "UNTRUSTED_TERMINAL_EVIDENCE",
        "SWITCH_ROLLBACK_UNPROVEN",
        "RECONCILED_DISPATCH_WITHOUT_TERMINAL",
    }
)
_QUARANTINE_EVIDENCE_KEYS = frozenset(
    {"reason_code", "source_run_id", "recorded_at"}
)

_REQUEST_ID_DERIVATION_TAG = b"sachima-arsd-request-id-v1"

#: The "I have no Session" statement. It is a distinct sentinel rather than
#: ``None`` so a Sachima id lookup that returned ``None`` fails closed instead
#: of silently starting a second conversation against the same agent — the
#: exact collapse Spec §6.2 forbids. On the wire it means the ``session_id``
#: key is structurally absent; a present null is ``INVALID_REQUEST``.
_CREATE_NEW_SESSION = object()


def _invalid_request() -> NoReturn:
    raise SpineError(RUNTIME_ARSD_INVALID_REQUEST) from None


def _safe_session_token(
    value: Any, *, code: str = RUNTIME_ARSD_INVALID_REQUEST
) -> str:
    """One ARS Session id, on the Session grammar exactly (no dots)."""

    if (
        type(value) is not str
        or len(value) > ARSD_MAX_SESSION_ID_CHARS
        or _SESSION_ID_RE.fullmatch(value) is None
    ):
        raise SpineError(code) from None
    return value


def derive_arsd_request_id(task_id: Any, session_id: Any, dispatch_ref: Any) -> str:
    """The stable ``request_id`` for one admitted Sachima dispatch identity.

    Derived from ``(task_id, session_id, dispatch_ref)`` only — never from
    wall-clock time — so a retry of an uncertain submission reuses the exact
    same id. Length-prefixed hashing makes component-boundary shifts
    non-colliding. The result satisfies the arsd request-id grammar.
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
# Submit request construction (Spec §6.2)
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


def _contained_cwd(cwd: Any, workspace_root: str) -> str:
    """One resolved ``cwd`` proven to sit inside the bound workspace root.

    At 0.7.6 a ``read``/``search`` allow requires every declared path to
    resolve, through symlinks, inside the bound workspace. A ``cwd`` outside
    ``workspace_root`` therefore makes every subsequent read/search deny
    fail-closed, turning a correctly configured Run into a guaranteed failure
    — so it is refused here, before any facade call (Spec §10.6.2).
    """

    value = _private_abs_path(cwd, code=RUNTIME_ARSD_INVALID_REQUEST)
    try:
        resolved = Path(value).resolve()
        root = Path(workspace_root).resolve()
    except (ValueError, OSError):
        raise SpineError(RUNTIME_ARSD_INVALID_REQUEST) from None
    if resolved != root and not resolved.is_relative_to(root):
        _invalid_request()
    return value


# --------------------------------------------------------------------------- #
# Sealed grants: one capability set, one identity that names it
# --------------------------------------------------------------------------- #
#: Domain separator for the derived identity. It is part of the digest input
#: so a Sachima-derived grant hash can never collide with a digest computed
#: for anything else, here or elsewhere.
_SEALED_GRANT_DOMAIN = "sachima.arsd.sealed_grant.v1"


@dataclass(frozen=True)
class ArsdSealedGrant:
    """One exact capability set, and the identity under which it travels.

    ``grant_capabilities`` is the only field the daemon acts on: its
    permission bridge freezes that set for the Run and gates every write-,
    execute- and read-family tool off it. The three identity fields are
    provenance — opaque text to the daemon, carried into the Run spec — and
    they exist so an audit can tell *which* grant a Run executed under.

    That is precisely why a narrowed set may not reuse the wide identity: two
    Runs with different authority that name the same grant are
    indistinguishable after the fact.
    """

    grant_ref: str
    grant_hash: str
    grant_role_hash: str
    capabilities: tuple[str, ...]


def _sealed_digest(payload: str, domain: str) -> str:
    return "sha256:" + hashlib.sha256(
        f"{payload}\n{domain}".encode("utf-8")
    ).hexdigest()


def derive_arsd_sealed_grant(config: Any, capabilities: Any) -> ArsdSealedGrant:
    """The sealed grant one exact capability set runs under.

    A set equal to the operator's own ``grant_capabilities`` keeps the
    operator's own identity verbatim: they already sealed exactly this, and
    re-labelling it would throw their provenance away.

    Any **narrowing** gets its own identity, derived deterministically from
    the operator's identity and the exact set. Deterministic matters twice
    over: a recovery rebuilds a byte-identical payload from durable refs, and
    an auditor can recompute the identity from the two inputs rather than
    trusting it.

    Widening is not a derivation, it is a refusal — a capability outside the
    operator's approved set fails closed with the stable config code, and so
    does an empty set, a duplicate, or a token off the closed allowlist.
    """

    validated = require_enabled_arsd_supervisor_config(config)
    owned = _owned_capability_set(capabilities)
    if not set(owned).issubset(set(validated.grant_capabilities)):
        _invalid_config()

    if owned == tuple(sorted(validated.grant_capabilities)):
        return ArsdSealedGrant(
            grant_ref=validated.grant_ref,
            grant_hash=validated.grant_hash,
            grant_role_hash=validated.grant_role_hash,
            capabilities=owned,
        )

    material = "\n".join(
        (
            _SEALED_GRANT_DOMAIN,
            validated.grant_ref,
            validated.grant_hash,
            validated.grant_role_hash,
            ",".join(owned),
        )
    )
    suffix = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    return ArsdSealedGrant(
        grant_ref=_safe_config_ref(f"{validated.grant_ref}_{suffix}"),
        grant_hash=_sealed_digest(material, "grant_hash"),
        grant_role_hash=_sealed_digest(material, "grant_role_hash"),
        capabilities=owned,
    )


def _grant_for_policy(config: ArsdSupervisorConfig, agent_policy_ref: str) -> ArsdSealedGrant:
    """The sealed grant this ``agent_policy_ref`` submits under.

    A policy with no per-policy entry keeps the config-wide grant unchanged,
    so every caller that predates the map is byte-identical to before.
    """

    capabilities = config.grant_by_policy_ref.get(agent_policy_ref)
    if capabilities is None:
        return ArsdSealedGrant(
            grant_ref=config.grant_ref,
            grant_hash=config.grant_hash,
            grant_role_hash=config.grant_role_hash,
            capabilities=tuple(config.grant_capabilities),
        )
    return derive_arsd_sealed_grant(config, capabilities)


def build_arsd_submit_payload(
    config: ArsdSupervisorConfig,
    *,
    agent_policy_ref: Any,
    model_policy_ref: Any,
    effort_policy_ref: Any,
    workspace_ref: Any,
    run_limits_policy_ref: Any,
    prompt_text: Any,
    session_id: Any = _CREATE_NEW_SESSION,
    expected_binding_hash: Any = None,
    input_refs: Any = (),
    cwd: Any = None,
    retry_of_run_id: Any = None,
) -> dict[str, Any]:
    """Build the exact Socket API v3 ``submit`` payload for one admitted turn.

    Every policy-facing value resolves through the enabled config's closed
    maps — an unknown ref fails closed; nothing is passed through verbatim.
    The result is caller-owned wire material (prompt text and private paths
    included): it must go to :meth:`ArsdClientFacade.submit` only and never
    into events, projections, logs, or serialized state. ``retry_of_run_id``
    is for an explicit recovery decision only — never an automatic retry.

    The whole Session decision is the presence of ``session_id``: omit the
    argument to create one new durable Session, or pass an existing id for
    existing-only reuse. Passing ``None`` is refused rather than treated as
    create, and the built dict never carries a present-null ``session_id``.

    ``requested_model`` / ``requested_effort`` are re-resolved from the policy
    maps on **every** call, including every reuse turn — they are properties
    of the Run, not of the Session, and nothing observed from a past Run feeds
    back in here. A built literal states what Sachima requested; only ARS's
    own read-back proves what a Run executed under (Spec §5.5.3).

    There is deliberately no negotiated-budget parameter. The payload is
    frozen at construction, so a retry after the operator changed the daemon's
    event budget re-sends byte-identical material rather than re-tuned
    ``limits`` (Spec §5.3.1 consequence 2). Whether *this* daemon will admit
    the frozen ``limits`` is the separate question
    :func:`check_arsd_admission_event_budget` answers per new admission.
    """

    validated = require_enabled_arsd_supervisor_config(config)

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
    workspace_root = _resolve_ref(validated.workspace_by_ref, workspace_ref)
    cwd_path = None if cwd is None else _contained_cwd(cwd, workspace_root)
    # The grant is resolved from the same closed config the rest of the
    # request is: the caller names a policy ref, never a capability. Resolving
    # the agent first also means an unknown ref fails closed before anything
    # is derived from it.
    agent_id = _resolve_ref(validated.agent_by_policy_ref, agent_policy_ref)
    grant = _grant_for_policy(validated, agent_policy_ref)

    request: dict[str, Any] = {
        "owner": validated.owner,
        "namespace": validated.namespace,
        "agent_id": agent_id,
        "expected_binding_hash": binding_hash,
        "input_refs": _wire_input_refs(input_refs),
        "requested_model": _resolve_ref(
            validated.model_by_policy_ref, model_policy_ref
        ),
        "requested_effort": _resolve_ref(
            validated.effort_by_policy_ref, effort_policy_ref
        ),
        "grant_ref": grant.grant_ref,
        "grant_hash": grant.grant_hash,
        "grant_role_hash": grant.grant_role_hash,
        "grant_capabilities": list(grant.capabilities),
        "mcp_snapshot_hashes": list(validated.mcp_snapshot_hashes),
        "credential_refs": list(validated.credential_refs),
        "limits": dict(
            _resolve_ref(validated.run_limits_by_policy_ref, run_limits_policy_ref)
        ),
        "evidence_policy_hash": validated.evidence_policy_hash,
        "recovery_policy_hash": validated.recovery_policy_hash,
        "schema_version": ARSD_SPEC_SCHEMA_VERSION,
    }
    # Reuse adds the key; create leaves it structurally absent. There is no
    # branch that can write ``None`` into it.
    if session_id is not _CREATE_NEW_SESSION:
        request["session_id"] = _safe_session_token(session_id)

    return {
        "request": request,
        "prompt_text": _wire_prompt_text(prompt_text),
        "workspace_root": workspace_root,
        "cwd": cwd_path,
        "retry_of_run_id": retry_token,
    }


def check_arsd_admission_event_budget(
    limits: Any, *, max_run_event_budget_bytes: Any
) -> None:
    """Pre-check one new admission's run limits against the negotiated budget.

    ``RunLimits`` keeps structural per-field maxima **and** the daemon
    separately refuses an admission whose
    ``max_event_bytes * max_events`` exceeds its configured
    ``max_run_event_budget_bytes`` (Δ-10). Per-field validity therefore does
    not imply admissibility, and this is the function that says so: it fails
    closed with the stable invalid-request code rather than spending a submit
    to learn the answer.

    ``max_run_event_budget_bytes`` is the value returned by the fresh
    ``server_info`` negotiation immediately preceding *this* new admission —
    never a cached one, and never a mirrored default (Spec §5.3.1).

    Scope is **new admissions only**. A recovery attempt for an uncertain
    submission — same ``request_id``, byte-equivalent frozen payload —
    performs no negotiation and is not pre-checked here; ARS resolves it from
    its durable admission record (Spec §5.6.2, Δ-12).

    This is a guard, not a re-implementation of daemon policy: the daemon
    remains the authority, and a refusal Sachima did not predict is still
    handled through the ordinary error mapping.
    """

    budget = max_run_event_budget_bytes
    if (
        isinstance(budget, bool)
        or type(budget) is not int
        or budget < 1
        or budget > ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES
    ):
        _invalid_request()
    if not isinstance(limits, Mapping) or set(limits) != _RUN_LIMIT_KEYS:
        _invalid_request()
    product = 1
    for key in ("max_event_bytes", "max_events"):
        value = limits[key]
        if isinstance(value, bool) or type(value) is not int or value < 1:
            _invalid_request()
        product *= value
    if product > budget:
        _invalid_request()


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
# Exact response validators (Spec §5.3 / §7.2 / §9)
# --------------------------------------------------------------------------- #
#: The **top-level** ``server_info`` key set is still exactly five at 0.7.6:
#: ``v2_only_operations`` retired and ``operations`` took its place. Only the
#: nested ``limits`` block grew (Δ-8).
_SERVER_INFO_KEYS = frozenset(
    {"version", "api_version", "supported_api_versions", "operations", "limits"}
)
#: Exact pinned 0.7.6 negotiation set, as the daemon's ``server_info`` emits it
#: (``list(SUPPORTED_API_VERSIONS)``) — closed: only this exact value ever
#: reaches the repr-safe :class:`ArsdServerInfo`. Drift-locked against the real
#: protocol module by the contract tests.
_ARSD_SUPPORTED_API_VERSIONS = (3,)
#: The daemon emits ``sorted(protocol.OPERATIONS)``.
_ARSD_SORTED_OPERATIONS = tuple(sorted(ARSD_OPERATIONS))
#: The **six** limits the 0.7.6 daemon reports. The two byte bounds are
#: protocol constants and must equal our mirrors exactly; the three capacity
#: limits are operator-configured and must be usable and bounded
#: (``1 <= value <= _MAX_LIMIT_COUNT``); the sixth is the negotiated per-Run
#: event budget, read as a runtime value and bounded only by the mirrored
#: structural maximum — never compared for equality against a default, which
#: would fail against any validly reconfigured daemon (Spec §5.3.1). An
#: unbounded remote int never reaches the repr-safe observation.
_SERVER_INFO_LIMIT_KEYS = frozenset(
    {
        "max_concurrent_runs",
        "max_frame_bytes",
        "max_prompt_bytes",
        "events_page_limit",
        "event_follow_queue_size",
        "max_run_event_budget_bytes",
    }
)
_SERVER_INFO_CAPACITY_KEYS = (
    "max_concurrent_runs",
    "events_page_limit",
    "event_follow_queue_size",
)
_SUBMIT_RESULT_KEYS = frozenset({"run_id", "session_id", "accepted_at"})
_RUN_STATUS_REQUIRED_KEYS = frozenset({"run_id", "session_id"})
_RUN_STATUS_ACCEPTED_KEYS = frozenset({"run_id", "session_id", "state", "accepted_at"})
_RUN_STATUS_OPTIONAL_KEYS = frozenset({"progress", "result"})
_RUN_STATUS_ACCEPTED_STATE = "accepted"
_RUN_CANCEL_REQUIRED_KEYS = frozenset({"run_id"})
_RUN_CANCEL_TERMINAL_KEYS = frozenset({"status", "result"})
_SESSION_VIEW_KEYS = frozenset(
    {
        "session_id",
        "owner",
        "namespace",
        "agent_id",
        "profile_id",
        "created_at",
        "updated_at",
        "last_effective_model",
        "last_effective_effort",
        "quarantine",
    }
)
_SESSION_LIST_KEYS = frozenset({"sessions"})
_AGENT_LIST_KEYS = frozenset({"agent_ids"})
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


def _wire_timestamp(value: Any) -> str:
    """One bounded, timezone-aware ISO timestamp; parse failures never chain."""

    if (
        type(value) is not str
        or not value
        or len(value) > _MAX_TIMESTAMP_CHARS
        or "\n" in value
        or "\r" in value
    ):
        _protocol_violation()
    try:
        moment = _dt.datetime.fromisoformat(value)
    except ValueError:
        _protocol_violation()
    if moment.tzinfo is None:
        _protocol_violation()
    return value


def _owned_wire_body(value: Any) -> dict[str, Any]:
    """One raw remote body, copied and owned, never read or echoed."""

    if not isinstance(value, Mapping):
        _protocol_violation()
    try:
        return json.loads(json.dumps(dict(value)))
    except (TypeError, ValueError, RecursionError):
        _protocol_violation()


@dataclass(frozen=True)
class ArsdServerInfo:
    """One validated, negotiation-passing ``server_info`` observation.

    Carries closed structural data only (versions and integer limits) — safe
    for reprs and diagnostics; still deliberately without a serialize surface.
    ``max_run_event_budget_bytes`` is the **negotiated runtime value** of the
    daemon that answered: authority for this admission's budget pre-check, and
    for nothing else. It is never carried forward to a later admission.
    """

    version: str
    api_version: int
    supported_api_versions: tuple[int, ...]
    operations: tuple[str, ...]
    limits: Mapping[str, int]

    @property
    def max_run_event_budget_bytes(self) -> int:
        return self.limits["max_run_event_budget_bytes"]

    @property
    def max_concurrent_runs(self) -> int:
        """How many Runs this daemon will hold at once, as it just said.

        A typed accessor for the same reason the event budget has one: it is
        the *only* admissible answer to that question. There is deliberately no
        mirrored default beside it — a constant here would be a fallback, and a
        fallback is how a host admits more work than the daemon accepted.
        """

        return self.limits["max_concurrent_runs"]


def validate_arsd_server_info(
    payload: Any, *, config: ArsdSupervisorConfig
) -> ArsdServerInfo:
    """Exact Socket API v3 preflight negotiation (Spec §5.3).

    Malformed shape → ``runtime_arsd_protocol_violation``. A structurally
    well-formed reply that fails package/API/operation/limit compatibility →
    the single stable ``runtime_arsd_version_mismatch`` backend-unavailable
    code. Never falls back silently. The negotiation sets are closed: only the
    exact pinned ``[3]`` / sorted seven-operation values ever reach
    :class:`ArsdServerInfo`, so no remote string survives into a repr surface.

    A five-key ``limits`` block — the 0.7.1 shape — is a protocol violation
    against a 0.7.6 daemon, not a tolerated older peer: there is no
    compatibility window and no per-operation version matrix. A seventh key is
    equally a violation.
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

    operations_raw = payload["operations"]
    if not isinstance(operations_raw, list):
        _protocol_violation()
    for op in operations_raw:
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
    if tuple(operations_raw) != _ARSD_SORTED_OPERATIONS:
        _version_mismatch()
    if limits["max_frame_bytes"] != ARSD_MAX_FRAME_BYTES:
        _version_mismatch()
    if limits["max_prompt_bytes"] != ARSD_MAX_PROMPT_BYTES:
        _version_mismatch()
    for capacity_key in _SERVER_INFO_CAPACITY_KEYS:
        if limits[capacity_key] < 1 or limits[capacity_key] > _MAX_LIMIT_COUNT:
            _version_mismatch()
    budget = limits["max_run_event_budget_bytes"]
    if budget < 1 or budget > ARSD_STRUCTURAL_MAX_RUN_EVENT_BUDGET_BYTES:
        _version_mismatch()

    return ArsdServerInfo(
        version=version,
        api_version=api_version,
        supported_api_versions=_ARSD_SUPPORTED_API_VERSIONS,
        operations=_ARSD_SORTED_OPERATIONS,
        limits=MappingProxyType(limits),
    )


@dataclass(frozen=True)
class ArsdSubmitAccepted:
    """Durable acceptance of one submit.

    Both ``run_id`` and ``session_id`` are private locators: neither is public
    status text, and neither is serialized anywhere. Public surfaces carry
    only Sachima-derived safe refs.
    """

    run_id: str = field(repr=False)
    session_id: str = field(repr=False)
    accepted_at: str


def validate_arsd_submit_result(payload: Any) -> ArsdSubmitAccepted:
    """Exact v3 ``submit`` ack shape: ``{run_id, session_id, accepted_at}``.

    The Session id is learned here and nowhere else — Sachima never derives
    it, guesses it, or reconstructs it from a ``run_id`` convention
    (Spec §6.3).
    """

    if not isinstance(payload, Mapping) or set(payload) != _SUBMIT_RESULT_KEYS:
        _protocol_violation()
    run_id = _safe_wire_token(
        payload["run_id"], code=RUNTIME_ARSD_PROTOCOL_VIOLATION
    )
    session_id = _safe_session_token(
        payload["session_id"], code=RUNTIME_ARSD_PROTOCOL_VIOLATION
    )
    return ArsdSubmitAccepted(
        run_id=run_id,
        session_id=session_id,
        accepted_at=_wire_timestamp(payload["accepted_at"]),
    )


@dataclass(frozen=True)
class ArsdRunStatusObservation:
    """One validated ``run_status`` reply.

    Two exact shapes, never a merge of them: the **acceptance** view
    (``state == "accepted"`` plus ``accepted_at``, no progress and no result)
    and the **active** view (the two ids plus optional ``progress`` and/or
    ``result``). Ids and raw remote bodies stay private.
    """

    run_id: str = field(repr=False)
    session_id: str = field(repr=False)
    state: str | None
    accepted_at: str | None
    progress: dict[str, Any] | None = field(repr=False)
    result: dict[str, Any] | None = field(repr=False)

    @property
    def has_terminal_result(self) -> bool:
        return self.result is not None


def validate_arsd_run_status(payload: Any, *, run_id: Any) -> ArsdRunStatusObservation:
    """Exact ``run_status`` validation (Spec §10.1, acceptance row A-11).

    A missing, extra, or off-contract key — including a ``state`` value
    outside the contract — is a protocol violation, not a tolerated field.
    The reply's ``run_id`` must echo the one asked about.
    """

    expected_run = _safe_wire_token(run_id, code=RUNTIME_ARSD_INVALID_REQUEST)
    if not isinstance(payload, Mapping):
        _protocol_violation()
    keys = set(payload)
    if not _RUN_STATUS_REQUIRED_KEYS <= keys:
        _protocol_violation()
    if payload["run_id"] != expected_run:
        _protocol_violation()
    session_id = _safe_session_token(
        payload["session_id"], code=RUNTIME_ARSD_PROTOCOL_VIOLATION
    )

    if "state" in keys or "accepted_at" in keys:
        # The acceptance view is all-or-nothing and carries nothing else.
        if keys != _RUN_STATUS_ACCEPTED_KEYS:
            _protocol_violation()
        if payload["state"] != _RUN_STATUS_ACCEPTED_STATE:
            _protocol_violation()
        return ArsdRunStatusObservation(
            run_id=expected_run,
            session_id=session_id,
            state=_RUN_STATUS_ACCEPTED_STATE,
            accepted_at=_wire_timestamp(payload["accepted_at"]),
            progress=None,
            result=None,
        )

    if not keys <= _RUN_STATUS_REQUIRED_KEYS | _RUN_STATUS_OPTIONAL_KEYS:
        _protocol_violation()
    return ArsdRunStatusObservation(
        run_id=expected_run,
        session_id=session_id,
        state=None,
        accepted_at=None,
        progress=_owned_wire_body(payload["progress"]) if "progress" in keys else None,
        result=_owned_wire_body(payload["result"]) if "result" in keys else None,
    )


#: Sachima's mirror of the pinned ARS final-message byte ceiling. It is a
#: bound, never a policy: ARS clips at exactly this ceiling and records that it
#: did, so mirroring it only decides what happens to a body that somehow
#: arrives longer — it gets clipped here too, rather than carried onward
#: unbounded. Drift-locked against ``agent_run_supervisor.result`` by the
#: contract tests.
ARSD_MAX_FINAL_MESSAGE_BYTES = 65_536
#: The exact reason token ARS records when it clipped a final message. Reused
#: rather than re-minted, so Sachima's own clip is legible as the same fact.
ARSD_FINAL_MESSAGE_TRUNCATE_REASON = "max_final_message_bytes"

#: The bounded token charset a truncation reason may use. Foreign free text
#: beside the marker is dropped; the marker itself is preserved.
_TRUNCATE_REASON_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_TERMINAL_RESULT_STATUS_KEY = "status"
_TERMINAL_RESULT_REASON_KEY = "reason"
_FINAL_MESSAGE_KEY = "final_message"
_TRUNCATED_KEY = "truncated"
_TRUNCATE_REASON_KEY = "truncate_reason"


def _clip_utf8(text: str, max_bytes: int) -> tuple[str, bool]:
    """Clip ``text`` to ``max_bytes`` on a character boundary."""

    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False
    clipped = encoded[:max_bytes]
    while clipped:
        try:
            return clipped.decode("utf-8"), True
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return "", True


@dataclass(frozen=True)
class ArsdTerminalResult:
    """The bounded terminal answer a finished Run already returned.

    Exactly the four fields ARS 0.7.6 puts on a trusted Native terminal that
    describe *the answer*: the neutral terminal status, the agent's own final
    message, and whether that message was clipped. Everything else on the
    terminal body — the Run id, the private run dir, the evidence paths, the
    usage block — is deliberately absent: reading them is artifact browsing,
    and this projection exists precisely so a delegated submission never has to
    do any.

    ``final_message`` is the one free-form field, so it is ``repr=False``: it
    is a payload to deliver to the chat that asked for it, never material for a
    log line or a diagnostic rendering.
    """

    status: str
    final_message: str = field(repr=False)
    truncated: bool
    truncate_reason: str | None


def project_arsd_terminal_result(result: Any, *, status: Any) -> ArsdTerminalResult:
    """Project one trusted terminal body into the bounded four-field answer.

    ``status`` is the **neutral** terminal the caller already derived through
    the R-6 mapping, not the body's own token: that mapping is where a
    ``PERMISSION_VIOLATION`` ``completed`` becomes ``failed``, and re-reading
    the raw status here would quietly undo it.

    A body that cannot be read, or a status outside the closed terminal
    vocabulary, is a contained internal failure — never a fabricated answer
    with an empty message, which would read as "it finished, silently".
    """

    if type(status) is not str or status not in ARSD_TERMINAL_STATUSES:
        raise SpineError(RUNTIME_ARSD_INTERNAL) from None
    if not isinstance(result, Mapping):
        raise SpineError(RUNTIME_ARSD_INTERNAL) from None

    raw_message = result.get(_FINAL_MESSAGE_KEY)
    message = raw_message if type(raw_message) is str else ""
    message, clipped = _clip_utf8(message, ARSD_MAX_FINAL_MESSAGE_BYTES)

    truncated = result.get(_TRUNCATED_KEY) is True or clipped
    reason: str | None = None
    if truncated:
        raw_reason = result.get(_TRUNCATE_REASON_KEY)
        if type(raw_reason) is str and _TRUNCATE_REASON_RE.fullmatch(raw_reason):
            reason = raw_reason
        elif clipped:
            # Sachima's own clip states its own reason; an unreadable remote
            # one is dropped rather than echoed or guessed at.
            reason = ARSD_FINAL_MESSAGE_TRUNCATE_REASON

    return ArsdTerminalResult(
        status=status,
        final_message=message,
        truncated=truncated,
        truncate_reason=reason,
    )


@dataclass(frozen=True)
class ArsdRunCancelObservation:
    """One validated ``run_cancel`` reply.

    A cancel that has not yet produced trusted terminal evidence carries the
    run echo alone. ``cancelled`` is projected only when such evidence
    follows; the cancel call itself never claims an outcome (Spec §10.4).
    """

    run_id: str = field(repr=False)
    status: str | None
    result: dict[str, Any] | None = field(repr=False)

    @property
    def has_terminal_result(self) -> bool:
        return self.result is not None


def validate_arsd_run_cancel_result(
    payload: Any, *, run_id: Any
) -> ArsdRunCancelObservation:
    """Exact ``run_cancel`` validation.

    ``status`` and ``result`` arrive together or not at all, and ``status``
    must be a member of the five-member terminal vocabulary — a terminal
    *reason* such as ``PERMISSION_VIOLATION`` is not a status (§10.7).
    """

    expected_run = _safe_wire_token(run_id, code=RUNTIME_ARSD_INVALID_REQUEST)
    if not isinstance(payload, Mapping):
        _protocol_violation()
    keys = set(payload)
    if not _RUN_CANCEL_REQUIRED_KEYS <= keys:
        _protocol_violation()
    if payload["run_id"] != expected_run:
        _protocol_violation()
    extra = keys - _RUN_CANCEL_REQUIRED_KEYS
    if extra and extra != _RUN_CANCEL_TERMINAL_KEYS:
        _protocol_violation()
    if not extra:
        return ArsdRunCancelObservation(run_id=expected_run, status=None, result=None)
    status = payload["status"]
    if type(status) is not str or status not in ARSD_TERMINAL_STATUSES:
        _protocol_violation()
    return ArsdRunCancelObservation(
        run_id=expected_run,
        status=status,
        result=_owned_wire_body(payload["result"]),
    )


@dataclass(frozen=True)
class ArsdSessionView:
    """One validated ``session_status`` / ``session_list`` record (R-5).

    A Session has identity, last-use observations, and optional quarantine
    evidence — and deliberately no lifecycle state to project. The id is
    private; the quarantine block is categorical by construction (no exception
    text, no agent text, no path).

    ``last_effective_model`` / ``last_effective_effort`` are observations of
    the Session's **last Run**. They are recorded here and fed into nothing:
    never into request construction, and never treated as the effective
    configuration of a Run other than the one that produced them (§5.5.4).

    Optionality mirrors the real record rather than Sachima's preference: the
    daemon guarantees ``session_id``/``owner``/``namespace`` on every view it
    emits, and declares the remaining observation fields optional, so those
    are accepted as ``None``. The ten-key set itself stays exact.
    """

    session_id: str = field(repr=False)
    owner: str
    namespace: str
    agent_id: str | None
    profile_id: str | None
    created_at: str | None
    updated_at: str | None
    last_effective_model: str | None
    last_effective_effort: str | None
    quarantine_reason_code: str | None

    @property
    def is_reusable(self) -> bool:
        """A quarantined Session still exists; it is refused for *reuse*."""

        return self.quarantine_reason_code is None


def _optional_wire_token(value: Any) -> str | None:
    if value is None:
        return None
    return _safe_wire_token(value, code=RUNTIME_ARSD_PROTOCOL_VIOLATION)


def _optional_config_text(value: Any) -> str | None:
    if value is None:
        return None
    return _safe_config_text(value, code=RUNTIME_ARSD_PROTOCOL_VIOLATION)


def _optional_wire_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    return _wire_timestamp(value)


def validate_arsd_session_view(payload: Any) -> ArsdSessionView:
    """Exact ten-key session view with the closed quarantine block (R-5)."""

    if not isinstance(payload, Mapping) or set(payload) != _SESSION_VIEW_KEYS:
        _protocol_violation()

    quarantine_raw = payload["quarantine"]
    reason_code: str | None = None
    if quarantine_raw is not None:
        if (
            not isinstance(quarantine_raw, Mapping)
            or set(quarantine_raw) != _QUARANTINE_EVIDENCE_KEYS
        ):
            _protocol_violation()
        reason_code = quarantine_raw["reason_code"]
        if type(reason_code) is not str or reason_code not in _QUARANTINE_REASON_CODES:
            _protocol_violation()
        # Read for shape only: the source run id is a private locator and the
        # timestamp is bounded. Neither reaches the returned view.
        _safe_wire_token(
            quarantine_raw["source_run_id"], code=RUNTIME_ARSD_PROTOCOL_VIOLATION
        )
        _wire_timestamp(quarantine_raw["recorded_at"])

    return ArsdSessionView(
        session_id=_safe_session_token(
            payload["session_id"], code=RUNTIME_ARSD_PROTOCOL_VIOLATION
        ),
        owner=_safe_id(payload["owner"], code=RUNTIME_ARSD_PROTOCOL_VIOLATION),
        namespace=_safe_config_text(
            payload["namespace"], code=RUNTIME_ARSD_PROTOCOL_VIOLATION
        ),
        agent_id=_optional_wire_token(payload["agent_id"]),
        profile_id=_optional_wire_token(payload["profile_id"]),
        created_at=_optional_wire_timestamp(payload["created_at"]),
        updated_at=_optional_wire_timestamp(payload["updated_at"]),
        last_effective_model=_optional_config_text(payload["last_effective_model"]),
        last_effective_effort=_optional_wire_token(payload["last_effective_effort"]),
        quarantine_reason_code=reason_code,
    )


def validate_arsd_session_list(payload: Any) -> tuple[ArsdSessionView, ...]:
    """Exact ``session_list`` page: ``{"sessions": [<session_view>, ...]}``.

    The top-level key set is exactly ``{"sessions"}`` and the value is a list.
    A bare session record at the top level is a protocol violation, never a
    tolerated shape.
    """

    if not isinstance(payload, Mapping) or set(payload) != _SESSION_LIST_KEYS:
        _protocol_violation()
    sessions_raw = payload["sessions"]
    if not isinstance(sessions_raw, list):
        _protocol_violation()
    return tuple(validate_arsd_session_view(item) for item in sessions_raw)


def validate_arsd_agent_list(payload: Any) -> tuple[str, ...]:
    """Exact ``agent_list`` reply: ``{"agent_ids": [<canonical id>, ...]}``.

    The live roster of canonical agent ids the connected daemon loaded at
    startup. Registration is all it is: not health, not readiness, not
    authorization, not execution eligibility — ``submit`` remains the
    admission boundary, and Sachima's own execution preset remains the other
    half of eligibility.

    Three properties are checked as **contract**, not as convenience, because
    the daemon derives them from one accessor
    (``tuple(sorted(snapshot.entries))``) and a reply that lacks them did not
    come from it:

    * the top-level key set is exactly ``{"agent_ids"}`` and the value is a
      list — a bare list, an extra key, or a tuple is a violation, not a
      tolerated shape;
    * every id matches the canonical grammar exactly. There is no case
      folding, no trimming, and no normalization: this is a validator, and
      repairing a malformed id here would be inventing a registration;
    * the ids are strictly ascending and therefore unique. A repeated or
      out-of-order id is a forged or off-contract reply.

    The reply is never echoed on failure — every deviation is the one stable
    ``runtime_arsd_protocol_violation`` code.
    """

    if not isinstance(payload, Mapping) or set(payload) != _AGENT_LIST_KEYS:
        _protocol_violation()
    raw = payload["agent_ids"]
    if type(raw) is not list or len(raw) > ARSD_MAX_REGISTERED_AGENTS:
        _protocol_violation()
    previous: str | None = None
    for item in raw:
        if type(item) is not str or _AGENT_ID_RE.fullmatch(item) is None:
            _protocol_violation()
        if previous is not None and item <= previous:
            _protocol_violation()
        previous = item
    return tuple(raw)


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
    read-model cursor translation (Spec §9.2): resuming with
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
    """Exact non-follow ``run_events`` page validation (Spec §9.1/§9.2).

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
    # daemon reports as not exhausted (mirrors the 0.7.6 handler).
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
# Injected client facade boundary (Spec §5.1)
# --------------------------------------------------------------------------- #
#: Mirror of the arsd request-id grammar (``[A-Za-z0-9._-]``, 1..128) —
#: unchanged at v3.
_WIRE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

#: The official client's *local* transport-loss raises during a roundtrip —
#: always its exact base class: ``INTERNAL`` for a socket write/read failure
#: or a clean close before any reply, ``MALFORMED_FRAME`` for a reply
#: truncated by connection loss. Daemon-declared errors arrive as typed
#: subclasses and therefore never match together with the base-class check.
_LOCAL_TRANSPORT_LOSS_CODES = frozenset({"INTERNAL", "MALFORMED_FRAME"})


@runtime_checkable
class ArsdClientFacade(Protocol):
    """The injected Socket API v3 client boundary the P2+ backend depends on.

    Implementations perform exactly one bounded daemon operation per call and
    return the raw result mapping; validation stays in the pure
    ``validate_arsd_*`` functions. Tests inject doubles; production uses
    :class:`DefaultArsdClientFacade`.

    Seven of the eight v3 operations appear here — every one this integration
    uses. There is no ``session_close`` (the operation does not exist) and no
    ``follow`` path.
    """

    def server_info(self) -> Mapping[str, Any]: ...

    def submit(
        self, *, request_id: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def run_status(self, run_id: str) -> Mapping[str, Any]: ...

    def run_events(
        self, run_id: str, *, from_seq: int, limit: int | None = None
    ) -> Mapping[str, Any]: ...

    def run_cancel(self, run_id: str) -> Mapping[str, Any]: ...

    def session_status(self, session_id: str) -> Mapping[str, Any]: ...

    def session_list(self) -> Mapping[str, Any]: ...

    def agent_list(self) -> Mapping[str, Any]: ...


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

    def run_status(self, run_id: str) -> Mapping[str, Any]:
        token = _safe_wire_token(run_id, code=RUNTIME_ARSD_INVALID_REQUEST)
        return self._operate(lambda client: client.run_status(token))

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

    def run_cancel(self, run_id: str) -> Mapping[str, Any]:
        token = _safe_wire_token(run_id, code=RUNTIME_ARSD_INVALID_REQUEST)
        return self._operate(lambda client: client.run_cancel(token))

    def session_status(self, session_id: str) -> Mapping[str, Any]:
        token = _safe_session_token(session_id)
        return self._operate(lambda client: client.session_status(token))

    def session_list(self) -> Mapping[str, Any]:
        return self._operate(lambda client: client.session_list())

    def agent_list(self) -> Mapping[str, Any]:
        return self._operate(lambda client: client.agent_list())
