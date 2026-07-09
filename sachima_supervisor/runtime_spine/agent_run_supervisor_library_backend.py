"""ARS-INT Runtime Spine — real agent-run-supervisor *library* backend.

This module is the formal integration seam between the Sachima runtime spine
and the ``agent_run_supervisor`` Python library: a default-off, fail-closed
:class:`AgentRunSupervisorLibraryConfig` gate plus an
:class:`AgentRunSupervisorLibraryBackend` that implements the existing
``AgentRunSupervisorBackend`` protocol (``agent_run_supervisor_port.py``) over
in-process library calls — **never** a CLI subprocess, shellout, or acpx
invocation from Sachima's side. The supervisor library itself owns acpx.

Boundaries:

* **Default-off.** The backend is unconstructible unless the config carries an
  explicit ``enabled=True`` plus an ``approval_ref``; anything else fails
  closed with a stable module code. The deterministic fake backend stays the
  composition default everywhere.
* **Claim-check refs.** The port hands the backend safe ``ws_*`` / ``policy_*``
  refs only; this config resolves them to private workspace dirs and read-only
  role mappings. Private paths live in ``repr=False`` fields, are never
  serialized (no ``as_dict``/``to_dict`` surface), and never enter events,
  projections, or logs.
* **Read-only roles only.** A role mapping whose permissions grant anything
  beyond read/search, a non-persistent session strategy, a missing/launcher/
  non-local acpx pin, or any live-delivery surface marker fails validation
  closed. Write-capable roles are a separate, unapproved future.
* **Lazy library access.** ``agent_run_supervisor`` is imported only inside the
  injected facade's methods, never at module import time — importing this
  module (and validating configs) works on hosts without the pinned extra, and
  the default test path drives the backend entirely through injected doubles.
* **No business verdict.** Backend states are runtime observations mapped per
  the ARS-INT design §6.1; ``no_op`` is always a failure, a closed session
  without a decidable terminal turn is honestly ``ambiguous``, and orphan
  detection never fabricates certainty.

Forbidden terms below appear only as boundary canaries/denylists, never as
behavior.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, NoReturn

from .agent_run_supervisor_port import (
    RUNTIME_SUPERVISOR_BACKEND_FAILURE,
    RUNTIME_SUPERVISOR_POLICY_DENIED,
)
from .events import SpineError, _safe_id, safe_task_id
from .execution_port import RUNTIME_INVALID_SESSION

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
RUNTIME_ARS_LIBRARY_DISABLED = "runtime_ars_library_disabled"
RUNTIME_ARS_LIBRARY_UNAVAILABLE = "runtime_ars_library_unavailable"
RUNTIME_INVALID_ARS_LIBRARY_CONFIG = "runtime_invalid_ars_library_config"

ARS_LIBRARY_STABLE_CODES = frozenset(
    {
        RUNTIME_ARS_LIBRARY_DISABLED,
        RUNTIME_ARS_LIBRARY_UNAVAILABLE,
        RUNTIME_INVALID_ARS_LIBRARY_CONFIG,
    }
)

ARS_LIBRARY_CONFIG_TYPE = "sachima.runtime_spine.ars_library_config.v1"

#: Repo root of this committed tree: private runtime dirs must live outside it
#: so a real session can never write sessions/turns into the tracked worktree.
_REPO_ROOT = Path(__file__).resolve().parents[2]

_APPROVAL_REF_PREFIX = "approval_"
_WORKSPACE_REF_PREFIX = "ws_"
_POLICY_REF_PREFIX = "policy_"

_SESSION_PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_MAX_STALE_AFTER_SECONDS = 604_800  # one week

#: Only these role permissions may be truthy — everything else is a write-ish
#: or otherwise unapproved capability and fails validation closed.
_READ_ONLY_PERMISSIONS = frozenset({"read", "search"})

#: Live-delivery surface markers that must never appear anywhere in a role
#: mapping or configured path (denylist canaries; this slice is local-only).
_FORBIDDEN_SURFACE_MARKERS = (
    "gateway",
    "feishu",
    "lark_im",
    "webhook",
    "ingress",
    "im_delivery",
    "real_delivery",
)

#: Launcher basenames that must never be pinned as the acpx binary: they would
#: reintroduce a package-manager fetch / shell indirection path.
_FORBIDDEN_BINARY_BASENAMES = frozenset(
    {
        "npx",
        "npm",
        "pnpm",
        "yarn",
        "bunx",
        "bun",
        "node",
        "deno",
        "sh",
        "bash",
        "zsh",
        "dash",
        "fish",
        "env",
        "python",
        "python3",
        "uv",
        "uvx",
        "pipx",
    }
)


def _invalid_config() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_ARS_LIBRARY_CONFIG)


# --------------------------------------------------------------------------- #
# Field-level sanitizers (each fails closed with the module's invalid code)
# --------------------------------------------------------------------------- #
def _safe_config_ref(value: Any) -> str:
    return _safe_id(value, code=RUNTIME_INVALID_ARS_LIBRARY_CONFIG)


def _check_no_forbidden_surface(text: str) -> None:
    lowered = text.lower()
    for marker in _FORBIDDEN_SURFACE_MARKERS:
        if marker in lowered:
            _invalid_config()


def _private_abs_dir(value: Any) -> str:
    """A private absolute directory path outside the tracked repo.

    Private paths legitimately carry filesystem material, so they are validated
    here but never run through the refs-only no-leak scan and never serialized.
    """

    if type(value) is not str or not value:
        _invalid_config()
    path = Path(value)
    if not path.is_absolute():
        _invalid_config()
    _check_no_forbidden_surface(value)
    resolved = path.resolve()
    if resolved == _REPO_ROOT or resolved.is_relative_to(_REPO_ROOT):
        _invalid_config()
    return value


def _check_acpx_pin(value: Any) -> str:
    """Validate one pinned local acpx binary path (absolute, non-launcher, real)."""

    if type(value) is not str or not value:
        _invalid_config()
    if not os.path.isabs(value):
        _invalid_config()
    _check_no_forbidden_surface(value)
    if os.path.basename(value).lower() in _FORBIDDEN_BINARY_BASENAMES:
        _invalid_config()
    if not Path(value).is_file():
        _invalid_config()
    return value


def _canonical_mapping(value: Any) -> dict[str, Any]:
    """An owned deep copy of a JSON-shaped mapping (fail closed otherwise)."""

    if not isinstance(value, Mapping):
        _invalid_config()
    try:
        text = json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        _invalid_config()
    _check_no_forbidden_surface(text)
    return json.loads(text)


def _check_role_mapping(mapping: dict[str, Any], config_acpx_binary: str | None) -> None:
    """Read-only + persistent + pinned-binary gate for one role mapping."""

    session = mapping.get("session")
    strategy = session.get("strategy") if isinstance(session, dict) else None
    if strategy != "persistent":
        _invalid_config()

    permissions = mapping.get("permissions")
    if not isinstance(permissions, dict) or not permissions:
        _invalid_config()
    for capability, granted in permissions.items():
        if granted and capability not in _READ_ONLY_PERMISSIONS:
            _invalid_config()

    runner = mapping.get("runner")
    role_binary = runner.get("acpx_binary") if isinstance(runner, dict) else None
    if role_binary is None and config_acpx_binary is None:
        _invalid_config()
    if role_binary is not None:
        _check_acpx_pin(role_binary)
        if config_acpx_binary is not None and role_binary != config_acpx_binary:
            _invalid_config()


def _check_library_config_fields(config: Any, *, normalize: bool = False) -> None:
    """Exact fail-closed validation of a library config's fields.

    Runs from ``__post_init__`` (with ``normalize=True``, replacing the two
    caller-supplied mappings with owned immutable deep copies) and from
    :func:`validate_agent_run_supervisor_library_config` at trust boundaries.
    Never echoes rejected material.
    """

    try:
        config_type = config.type
        enabled = config.enabled
        approval_ref = config.approval_ref
        sessions_dir = config.sessions_dir
        workspace_by_ref = config.workspace_by_ref
        role_by_ref = config.role_by_ref
        session_prefix = config.session_prefix
        acpx_binary = config.acpx_binary
        stale_after_seconds = config.stale_after_seconds
    except AttributeError:
        _invalid_config()

    if type(config_type) is not str or config_type != ARS_LIBRARY_CONFIG_TYPE:
        _invalid_config()
    if type(enabled) is not bool:
        _invalid_config()
    ref = _safe_config_ref(approval_ref)
    if not ref.startswith(_APPROVAL_REF_PREFIX) or ref == _APPROVAL_REF_PREFIX:
        _invalid_config()
    _private_abs_dir(sessions_dir)
    if type(session_prefix) is not str or _SESSION_PREFIX_RE.fullmatch(session_prefix) is None:
        _invalid_config()
    if (
        type(stale_after_seconds) is not int
        or stale_after_seconds < 1
        or stale_after_seconds > _MAX_STALE_AFTER_SECONDS
    ):
        _invalid_config()
    if acpx_binary is not None:
        _check_acpx_pin(acpx_binary)

    if not isinstance(workspace_by_ref, Mapping) or not workspace_by_ref:
        _invalid_config()
    safe_workspaces: dict[str, str] = {}
    for key, value in workspace_by_ref.items():
        safe_key = _safe_config_ref(key)
        if not safe_key.startswith(_WORKSPACE_REF_PREFIX) or safe_key == _WORKSPACE_REF_PREFIX:
            _invalid_config()
        safe_workspaces[safe_key] = _private_abs_dir(value)

    if not isinstance(role_by_ref, Mapping) or not role_by_ref:
        _invalid_config()
    safe_roles: dict[str, dict[str, Any]] = {}
    for key, value in role_by_ref.items():
        safe_key = _safe_config_ref(key)
        if not safe_key.startswith(_POLICY_REF_PREFIX) or safe_key == _POLICY_REF_PREFIX:
            _invalid_config()
        mapping = _canonical_mapping(value)
        _check_role_mapping(mapping, acpx_binary)
        safe_roles[safe_key] = mapping

    if normalize:
        object.__setattr__(
            config, "workspace_by_ref", MappingProxyType(dict(sorted(safe_workspaces.items())))
        )
        object.__setattr__(
            config, "role_by_ref", MappingProxyType(dict(sorted(safe_roles.items())))
        )


@dataclass(frozen=True)
class AgentRunSupervisorLibraryConfig:
    """Frozen, default-off, claim-check config for the real library backend.

    ``enabled`` defaults to ``False`` and the backend refuses to construct
    unless it is exactly ``True`` — default-off holds at the type layer. The
    private surfaces (``sessions_dir`` / ``workspace_by_ref`` / ``role_by_ref``
    / ``acpx_binary``) are ``repr=False`` and there is deliberately no
    ``as_dict``/serialize method, so private paths cannot leak through routine
    logging or serialization. ``__post_init__`` re-runs the full allowlist and
    replaces the two caller-supplied mappings with owned immutable deep copies,
    so later caller-side mutation can never drift a validated config.
    """

    type: str
    approval_ref: str
    sessions_dir: str = field(repr=False)
    workspace_by_ref: Mapping[str, str] = field(repr=False)
    role_by_ref: Mapping[str, Mapping[str, Any]] = field(repr=False)
    session_prefix: str
    stale_after_seconds: int
    acpx_binary: str | None = field(default=None, repr=False)
    enabled: bool = False

    def __post_init__(self) -> None:
        _check_library_config_fields(self, normalize=True)


def validate_agent_run_supervisor_library_config(
    config: AgentRunSupervisorLibraryConfig,
) -> AgentRunSupervisorLibraryConfig:
    """Re-validate a config at a trust boundary and return it unchanged.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``: a non-exact type or any unsafe field fails closed with
    the stable ``runtime_invalid_ars_library_config`` code, never echoing the
    rejected material.
    """

    if type(config) is not AgentRunSupervisorLibraryConfig:
        _invalid_config()
    _check_library_config_fields(config)
    return config


# --------------------------------------------------------------------------- #
# Deterministic identity derivation (restart re-derivable, refs-only safe)
# --------------------------------------------------------------------------- #
def _task_digest(task_id: str) -> str:
    return hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:16]


def derive_ars_session_id(config: AgentRunSupervisorLibraryConfig, task_id: str) -> str:
    """The deterministic supervisor-side session id for one Sachima task."""

    safe_task = safe_task_id(task_id)
    return f"{config.session_prefix}_{_task_digest(safe_task)}"


def derive_backend_handle(task_id: str) -> str:
    """The deterministic, ``_safe_id``-shaped backend handle for one task."""

    safe_task = safe_task_id(task_id)
    return f"arsh_{_task_digest(safe_task)}"


# --------------------------------------------------------------------------- #
# Library access boundary
# --------------------------------------------------------------------------- #
class LibraryUnavailableError(Exception):
    """The pinned ``agent_run_supervisor`` distribution is not importable here.

    Raised (with no chained raw exception text) by the default facade when a
    lazy import fails; the backend collapses it to the stable
    ``runtime_ars_library_unavailable`` code.
    """


#: The supervisor's closed turn-status vocabulary (mirrors the pinned ARS
#: ``AgentRunStatus``). A facade reporting anything else is off-contract and
#: fails closed — an unknown token is never mapped, stored, or echoed.
_ARS_TURN_STATUSES = frozenset(
    {
        "completed",
        "no_op",
        "runner_error",
        "invalid_invocation",
        "timed_out",
        "no_session",
        "permission_denied",
        "interrupted",
        "protocol_error",
        "infrastructure_error",
        "policy_error",
    }
)

#: Turn statuses that synthesize a ``failed`` session state (design §6.1 row 2).
#: ``no_op`` is deliberately here: a silent exit-0 turn is never success.
_TURN_FAILURE_STATUSES = frozenset(
    {
        "runner_error",
        "invalid_invocation",
        "timed_out",
        "no_session",
        "permission_denied",
        "protocol_error",
        "infrastructure_error",
        "policy_error",
        "no_op",
    }
)

_RECORD_OPEN = "open"
_RECORD_CLOSED = "closed"


@dataclass(frozen=True)
class LibraryTurnResult:
    """One dispatched turn's identity, private artifact dir, and observation.

    ``turn_dir`` is a caller-private path (``repr=False``) handed to the host
    binding layer only; it must never be serialized into a public projection.
    ``status`` is a supervisor runtime observation, never a business verdict.
    """

    turn_id: str
    turn_dir: str = field(repr=False)
    status: str = "completed"
    turn_index: int = 0


@dataclass
class _SessionEntry:
    """In-memory ledger for one supervised task session (never serialized)."""

    task_id: str
    handle: str
    ars_session_id: str
    workspace_ref: str
    policy_ref: str
    last_turn_status: str | None = None
    killed: bool = False
    turn_count: int = 0


def _effective_role_mapping(
    config: AgentRunSupervisorLibraryConfig, policy_ref: str
) -> dict[str, Any]:
    """An owned role-mapping copy with the config-level acpx pin applied."""

    mapping = json.loads(json.dumps(config.role_by_ref[policy_ref]))
    runner = mapping.get("runner")
    if (
        isinstance(runner, dict)
        and runner.get("acpx_binary") is None
        and config.acpx_binary is not None
    ):
        runner["acpx_binary"] = config.acpx_binary
    return mapping


# --------------------------------------------------------------------------- #
# The backend
# --------------------------------------------------------------------------- #
class AgentRunSupervisorLibraryBackend:
    """``AgentRunSupervisorBackend`` implementation over the pinned ARS library.

    Constructing the backend is itself the activation gate: a forged/invalid
    config fails closed with ``runtime_invalid_ars_library_config`` and a
    disabled config with ``runtime_ars_library_disabled`` — the composition
    root falls back to the deterministic fake backend in both cases.

    All library access flows through one injected ``facade`` (tests supply
    deterministic doubles; the default lazily imports the pinned package per
    call). Every facade fault collapses to a stable code with no raw echo:
    ``runtime_ars_library_unavailable`` when the library is missing, else the
    port-family ``runtime_supervisor_backend_failure``. ``status``/``liveness``
    are pure local reads (record + lease + latest-turn observation) — the
    acpx-spawning ``status -s`` management query is never on this hot path.
    ``signal`` is phase-A fail-closed until the supervisor grows an
    interactive permission bridge.
    """

    def __init__(
        self,
        config: AgentRunSupervisorLibraryConfig,
        *,
        facade: Any | None = None,
        clock: Any | None = None,
    ) -> None:
        validate_agent_run_supervisor_library_config(config)
        if config.enabled is not True:
            raise SpineError(RUNTIME_ARS_LIBRARY_DISABLED)
        self._config = config
        self._facade = facade if facade is not None else _DefaultLibraryFacade()
        self._clock = clock if clock is not None else _utc_now
        self._lock = threading.RLock()
        self._by_handle: dict[str, _SessionEntry] = {}
        self._by_task: dict[str, _SessionEntry] = {}

    # -- protocol surface ---------------------------------------------------

    def create_or_attach(self, task_id: str, refs: tuple[str, ...]) -> str:
        safe_task = safe_task_id(task_id, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        workspace_ref, policy_ref = self._resolve_refs(refs)
        with self._lock:
            existing = self._by_task.get(safe_task)
            if existing is not None:
                if (
                    existing.workspace_ref != workspace_ref
                    or existing.policy_ref != policy_ref
                ):
                    raise SpineError(RUNTIME_SUPERVISOR_POLICY_DENIED)
                return existing.handle

        ars_session_id = derive_ars_session_id(self._config, safe_task)
        role, workspace = self._role_and_workspace(policy_ref, workspace_ref)
        record = self._call_facade(
            "open_record", self._config.sessions_dir, ars_session_id
        )
        if record is None:
            self._call_facade(
                "create_session",
                self._config.sessions_dir,
                role,
                ars_session_id,
                ars_session_id,
                self._config.workspace_by_ref[workspace_ref],
            )
        else:
            if getattr(record, "state", None) != _RECORD_OPEN:
                raise SpineError(RUNTIME_INVALID_SESSION)
            if (
                self._call_facade(
                    "binding_matches",
                    self._config.sessions_dir,
                    record,
                    role,
                    workspace,
                )
                is not True
            ):
                raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        return self._register_entry(safe_task, ars_session_id, workspace_ref, policy_ref)

    def attach_existing(self, task_id: str) -> str:
        safe_task = safe_task_id(task_id, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        with self._lock:
            existing = self._by_task.get(safe_task)
            if existing is not None:
                return existing.handle

        ars_session_id = derive_ars_session_id(self._config, safe_task)
        record = self._call_facade(
            "open_record", self._config.sessions_dir, ars_session_id
        )
        if record is None:
            # No persisted supervisor session: the port treats this stable code
            # as "no session" and fails closed — it never respawns from attach.
            raise SpineError(RUNTIME_INVALID_SESSION)
        workspace_ref, policy_ref = self._rebind_refs_from_record(record)
        return self._register_entry(safe_task, ars_session_id, workspace_ref, policy_ref)

    def status(self, handle: str) -> str:
        return self._synthesized_state(handle)

    def liveness(self, handle: str) -> str:
        return self._synthesized_state(handle)

    def signal(self, handle: str, decision_ref: str) -> str:
        self._require_entry(handle)
        _safe_id(decision_ref, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        # Phase A: the supervisor has no interactive permission bridge, so a
        # permission decision cannot be delivered. Fail closed; never pretend.
        raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)

    def kill(self, handle: str, reason_ref: str) -> str:
        entry = self._require_entry(handle)
        _safe_id(reason_ref, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        current = self._synthesized_state(handle)
        if current in ("completed", "failed", "cancelled", "ambiguous"):
            return current
        role, workspace = self._role_and_workspace(entry.policy_ref, entry.workspace_ref)
        _ = workspace
        work_dir = self._config.workspace_by_ref[entry.workspace_ref]
        try:
            self._facade.abort(
                self._config.sessions_dir, role, entry.ars_session_id, work_dir
            )
        except LibraryUnavailableError:
            raise SpineError(RUNTIME_ARS_LIBRARY_UNAVAILABLE) from None
        except SpineError:
            raise
        except BaseException:
            # Best-effort interrupt: an abort fault must not block the close.
            pass
        self._call_facade(
            "close", self._config.sessions_dir, role, entry.ars_session_id, work_dir
        )
        with self._lock:
            entry.killed = True
        return "cancelled"

    # -- dispatcher surface (not part of the port protocol) ------------------

    def run_turn(self, task_id: str, *, turn_kind: str, payload_text: str) -> LibraryTurnResult:
        """Run one prompt/goal turn through the library and update the ledger.

        The private ``payload_text`` is handed to the supervisor (which
        persists only redacted artifacts) and is never stored on the backend,
        echoed into an exception, or carried by the returned result.
        """

        safe_task = safe_task_id(task_id, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        if turn_kind not in ("goal", "prompt"):
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        if type(payload_text) is not str or not payload_text.strip():
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        with self._lock:
            entry = self._by_task.get(safe_task)
            if entry is None or entry.killed:
                raise SpineError(RUNTIME_INVALID_SESSION)
            workspace_ref = entry.workspace_ref
            policy_ref = entry.policy_ref
            ars_session_id = entry.ars_session_id

        role, _ = self._role_and_workspace(policy_ref, workspace_ref)
        prompt = (
            self._call_facade("compile_goal", role, payload_text)
            if turn_kind == "goal"
            else payload_text
        )
        turn = self._call_facade(
            "send",
            self._config.sessions_dir,
            role,
            ars_session_id,
            prompt,
            self._config.workspace_by_ref[workspace_ref],
        )
        try:
            turn_id, turn_dir, status = turn
        except (TypeError, ValueError):
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE) from None
        if (
            type(turn_id) is not str
            or not turn_id
            or type(turn_dir) is not str
            or not turn_dir
            or type(status) is not str
            or status not in _ARS_TURN_STATUSES
        ):
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        with self._lock:
            entry.last_turn_status = status
            entry.turn_count += 1
            turn_index = entry.turn_count
        return LibraryTurnResult(
            turn_id=turn_id, turn_dir=turn_dir, status=status, turn_index=turn_index
        )

    # -- internals ------------------------------------------------------------

    def _resolve_refs(self, refs: tuple[str, ...]) -> tuple[str, str]:
        safe_refs = tuple(
            _safe_id(ref, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE) for ref in refs
        )
        workspaces = [ref for ref in safe_refs if ref in self._config.workspace_by_ref]
        policies = [ref for ref in safe_refs if ref in self._config.role_by_ref]
        if len(workspaces) != 1 or len(policies) != 1:
            raise SpineError(RUNTIME_SUPERVISOR_POLICY_DENIED)
        return workspaces[0], policies[0]

    def _role_and_workspace(self, policy_ref: str, workspace_ref: str) -> tuple[Any, Any]:
        role = self._call_facade(
            "load_role", _effective_role_mapping(self._config, policy_ref)
        )
        workspace = self._call_facade(
            "validate_workspace", role, self._config.workspace_by_ref[workspace_ref]
        )
        return role, workspace

    def _rebind_refs_from_record(self, record: Any) -> tuple[str, str]:
        """Re-derive (workspace_ref, policy_ref) for a persisted record.

        Matches the record's pinned ``role_hash`` against the configured role
        mappings, then re-validates the store binding per workspace candidate.
        Unmatchable binding drift fails closed as a backend failure — attach
        never guesses and never respawns.
        """

        record_hash = getattr(record, "role_hash", None)
        for policy_ref in self._config.role_by_ref:
            try:
                role = self._facade.load_role(
                    _effective_role_mapping(self._config, policy_ref)
                )
                if self._facade.role_hash(role) != record_hash:
                    continue
                for workspace_ref, work_dir in self._config.workspace_by_ref.items():
                    workspace = self._facade.validate_workspace(role, work_dir)
                    if (
                        self._facade.binding_matches(
                            self._config.sessions_dir, record, role, workspace
                        )
                        is True
                    ):
                        return workspace_ref, policy_ref
            except LibraryUnavailableError:
                raise SpineError(RUNTIME_ARS_LIBRARY_UNAVAILABLE) from None
            except SpineError:
                raise
            except BaseException:
                continue  # candidate mismatch; keep searching, never echo
        raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)

    def _register_entry(
        self, safe_task: str, ars_session_id: str, workspace_ref: str, policy_ref: str
    ) -> str:
        handle = derive_backend_handle(safe_task)
        _safe_id(handle, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        with self._lock:
            existing = self._by_task.get(safe_task)
            if existing is not None:
                return existing.handle
            entry = _SessionEntry(
                task_id=safe_task,
                handle=handle,
                ars_session_id=ars_session_id,
                workspace_ref=workspace_ref,
                policy_ref=policy_ref,
            )
            self._by_task[safe_task] = entry
            self._by_handle[handle] = entry
            return handle

    def _require_entry(self, handle: str) -> _SessionEntry:
        safe_handle = _safe_id(handle, code=RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        with self._lock:
            entry = self._by_handle.get(safe_handle)
        if entry is None:
            raise SpineError(RUNTIME_INVALID_SESSION)
        return entry

    def _call_facade(self, method: str, *args: Any) -> Any:
        try:
            return getattr(self._facade, method)(*args)
        except LibraryUnavailableError:
            raise SpineError(RUNTIME_ARS_LIBRARY_UNAVAILABLE) from None
        except SpineError:
            raise
        except BaseException:
            # No-leak boundary: never chain or echo raw library/facade faults.
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE) from None

    def _synthesized_state(self, handle: str) -> str:
        entry = self._require_entry(handle)
        with self._lock:
            if entry.killed:
                return "cancelled"
            ledger_status = entry.last_turn_status
        view = self._call_facade(
            "inspect", self._config.sessions_dir, entry.ars_session_id
        )
        if view is None or getattr(view, "exists", None) is not True:
            raise SpineError(RUNTIME_SUPERVISOR_BACKEND_FAILURE)
        return self._map_view(ledger_status, view)

    def _map_view(self, ledger_status: str | None, view: Any) -> str:
        """Design §6.1 state synthesis — local observations only, no verdict."""

        turn_status = (
            ledger_status
            if ledger_status is not None
            else getattr(view, "latest_turn_status", None)
        )
        state = getattr(view, "state", None)
        if turn_status == "completed" and state == _RECORD_CLOSED:
            return "completed"
        if turn_status in _TURN_FAILURE_STATUSES:
            return "failed"
        if turn_status == "interrupted":
            return "cancelled"
        if state != _RECORD_OPEN:
            # Closed without a decidable terminal turn — or an unreadable
            # record — is honest ambiguity, never a fabricated verdict.
            return "ambiguous"
        if (
            getattr(view, "lease_held", False) is True
            and getattr(view, "holder_liveness", None) == "crashed"
            and getattr(view, "lease_recoverable", False) is True
        ):
            return "orphaned"
        progress = getattr(view, "progress", None)
        if progress is not None:
            progress_state = getattr(progress, "state", None)
            if progress_state == "waiting_for_permission":
                return "waiting_for_permission"
            if (
                getattr(view, "lease_held", False) is not True
                and progress_state == "running"
                and self._progress_stale(progress)
            ):
                return "orphaned"
        return "running"

    def _progress_stale(self, progress: Any) -> bool:
        updated_at = getattr(progress, "updated_at", None)
        if type(updated_at) is not str:
            return False
        try:
            moment = _dt.datetime.fromisoformat(updated_at)
        except ValueError:
            return False
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=_dt.timezone.utc)
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=_dt.timezone.utc)
        return (now - moment).total_seconds() > self._config.stale_after_seconds


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.timezone.utc)


# --------------------------------------------------------------------------- #
# Default facade — the ONLY place agent_run_supervisor is ever imported
# --------------------------------------------------------------------------- #
class _DefaultLibraryFacade:
    """Real library facade — every ``agent_run_supervisor`` import is lazy.

    Import failure collapses to :class:`LibraryUnavailableError` (no chained
    raw text). On a pinned distribution predating ``session_inspect`` the
    ``inspect`` surface degrades to the public ``SessionStore`` record + lease
    view (no latest-turn/progress observation) rather than guessing at the
    artifact layout.
    """

    @staticmethod
    def _module(name: str) -> Any:
        import importlib

        try:
            return importlib.import_module(name)
        except Exception:
            raise LibraryUnavailableError() from None

    def load_role(self, role_mapping: Mapping[str, Any]) -> Any:
        return self._module("agent_run_supervisor.role").load_role(dict(role_mapping))

    def role_hash(self, role: Any) -> str:
        return self._module("agent_run_supervisor.role").role_hash(role)

    def validate_workspace(self, role: Any, work_dir: str) -> Any:
        return self._module("agent_run_supervisor.workspace").validate_effective_cwd(
            role, work_dir
        )

    def _store(self, sessions_dir: str) -> Any:
        session_mod = self._module("agent_run_supervisor.session")
        return session_mod, session_mod.SessionStore(base_dir=Path(sessions_dir))

    def open_record(self, sessions_dir: str, ars_session_id: str) -> Any | None:
        session_mod, store = self._store(sessions_dir)
        try:
            return store.open_session(ars_session_id)
        except session_mod.SessionNotFoundError:
            return None

    def binding_matches(
        self, sessions_dir: str, record: Any, role: Any, workspace: Any
    ) -> bool:
        session_mod, store = self._store(sessions_dir)
        try:
            store.validate_binding(record, role=role, workspace_result=workspace)
        except session_mod.SessionBindingError:
            return False
        return True

    def _runtime(self, sessions_dir: str) -> Any:
        runtime_mod = self._module("agent_run_supervisor.session_runtime")
        return runtime_mod.SessionRuntime(sessions_dir=Path(sessions_dir))

    def create_session(
        self, sessions_dir: str, role: Any, ars_session_id: str, session_name: str, work_dir: str
    ) -> None:
        self._runtime(sessions_dir).create_session(
            role=role, session_id=ars_session_id, session_name=session_name, cwd=work_dir
        )

    def send(
        self, sessions_dir: str, role: Any, ars_session_id: str, prompt: str, work_dir: str
    ) -> tuple[str, str, str]:
        outcome = self._runtime(sessions_dir).send(
            role=role, session_id=ars_session_id, prompt=prompt, cwd=work_dir
        )
        status = getattr(outcome.status, "value", outcome.status)
        return (str(outcome.turn_id), str(outcome.turn_dir), str(status))

    def abort(self, sessions_dir: str, role: Any, ars_session_id: str, work_dir: str) -> bool:
        outcome = self._runtime(sessions_dir).abort(
            role=role, session_id=ars_session_id, cwd=work_dir
        )
        return getattr(outcome, "cancelled", False) is True

    def close(self, sessions_dir: str, role: Any, ars_session_id: str, work_dir: str) -> None:
        session_mod = self._module("agent_run_supervisor.session")
        try:
            self._runtime(sessions_dir).close(
                role=role, session_id=ars_session_id, cwd=work_dir
            )
        except session_mod.SessionClosedError:
            return  # already closed: the goal state already holds

    def compile_goal(self, role: Any, goal_text: str) -> str:
        goal_mod = self._module("agent_run_supervisor.goal")
        compiled = goal_mod.compile_goal_prompt(role, goal_mod.GoalSpec(goal_text=goal_text))
        return compiled.prompt

    def inspect(self, sessions_dir: str, ars_session_id: str) -> Any | None:
        import importlib

        try:
            inspect_mod = importlib.import_module("agent_run_supervisor.session_inspect")
        except Exception:
            return self._degraded_inspect(sessions_dir, ars_session_id)
        return inspect_mod.inspect_session(sessions_dir, ars_session_id)

    def _degraded_inspect(self, sessions_dir: str, ars_session_id: str) -> Any:
        """Record+lease-only view for pins predating ``session_inspect``.

        Reports no latest-turn/progress observation (those synthesis rows stay
        inactive) instead of hardcoding the supervisor's artifact layout.
        """

        from types import SimpleNamespace

        session_mod, store = self._store(sessions_dir)
        try:
            record = store.open_session(ars_session_id)
        except session_mod.SessionNotFoundError:
            return SimpleNamespace(
                exists=False,
                state=None,
                lease_held=False,
                holder_liveness=None,
                lease_recoverable=False,
                latest_turn_status=None,
                progress=None,
            )
        lease_held = False
        holder_liveness: str | None = None
        lease_recoverable = False
        try:
            for row in store.detect_stale_locks():
                if row.get("session_id") != ars_session_id:
                    continue
                lease_held = bool(row.get("lock_present")) and not bool(
                    row.get("lease_expired")
                )
                holder_liveness = row.get("holder_liveness")
                lease_recoverable = row.get("recoverable") is True
                break
        except Exception:
            lease_held, holder_liveness, lease_recoverable = False, None, False
        state = record.state if record.state in (_RECORD_OPEN, _RECORD_CLOSED) else None
        return SimpleNamespace(
            exists=True,
            state=state,
            lease_held=lease_held,
            holder_liveness=holder_liveness,
            lease_recoverable=lease_recoverable,
            latest_turn_status=None,
            progress=None,
        )


__all__ = [
    "ARS_LIBRARY_CONFIG_TYPE",
    "ARS_LIBRARY_STABLE_CODES",
    "RUNTIME_ARS_LIBRARY_DISABLED",
    "RUNTIME_ARS_LIBRARY_UNAVAILABLE",
    "RUNTIME_INVALID_ARS_LIBRARY_CONFIG",
    "AgentRunSupervisorLibraryBackend",
    "AgentRunSupervisorLibraryConfig",
    "LibraryTurnResult",
    "LibraryUnavailableError",
    "derive_ars_session_id",
    "derive_backend_handle",
    "validate_agent_run_supervisor_library_config",
]
