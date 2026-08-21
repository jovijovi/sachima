"""Gateway host binding for the default-off ``sachima_live_progress_display`` tool.

This module is the **host-side composition seam** that makes the LS4
``LiveProgressDisplayService`` real inside the Gateway/Feishu host process. It
offers exactly two backends — ``fake`` and ``arsd`` — stays default-off behind
explicit, independent knobs, and fails closed on everything else:

1. **Surface gate** — the binding only activates when
   ``SACHIMA_LIVE_PROGRESS_DISPLAY_SURFACE`` is exactly ``hermes_internal`` (the
   existing LS4-A approved internal surface). Unset / denied / truthy-looking
   values — and even the approved ``local_offline`` tool surface, which belongs
   to offline harnesses, never to a gateway host — leave this a no-op.
2. **Backend selection** — ``SACHIMA_LIVE_PROGRESS_BACKEND``. Unset or blank is
   ``fake``. The retired ``library`` value answers with its own distinct stable
   migration code (P5-a), never a rewrite to another backend. Anything else is
   one stable invalid code.
3. **Mode config** — ``fake`` reads a private
   ``SACHIMA_LIVE_PROGRESS_BINDINGS_FILE`` of the shape
   ``{"bindings": [{"task_id", "artifact_dir", "artifact_ref"}, ...]}``;
   ``arsd`` reads a private ``SACHIMA_ARSD_CONFIG_FILE`` carrying the
   ``ArsdSupervisorConfig`` fields and additionally requires ``enabled`` to be
   exactly ``True``. With no file configured the binding reports ``..._absent``
   and the tool keeps failing closed with its own stable
   ``sachima_live_progress_display_unbound`` code.

With a surface gate and a mode config present the binding builds the full spine
composition — ``LiveProgressSourceBindings`` + ``TaskRegistry`` +
``AgentRunSupervisorPort`` + a read model + ``LiveProgressQueryService``
carrying the LS4-A ``hermes_internal`` gate + ``LiveProgressDisplayService`` —
and binds the service into ``tools.sachima_live_progress_tool``. Composing a
display service **submits nothing**: an ``arsd`` bundle's dispatcher stays
fail-closed until an internal caller injects a payload resolver, so a composed
host never starts a Run by existing. The returned summary carries only safe
refs (``task_id`` / ``session_id`` / ``artifact_ref``) and counts; the
configured private paths are handed to the spine only and are never returned,
logged, or serialized.

There is **no automatic fallback between backends**: a failed ``arsd``
composition never degrades to ``fake``, a retired ``library`` selection never
becomes either, and no path reaches a CLI or package-manager launcher. There is
no top-level (or any direct) ``agent_run_supervisor`` import here — the default
``fake`` path imports the producer distribution not at all, and the ``arsd``
path reaches the daemon only through the spine's own lazy client facade.

Failure policy (never crash gateway startup): a malformed / unreadable config
file, an unsafe ``task_id`` / ``artifact_ref``, an empty ``artifact_dir``, a
disabled config, or any composition error logs exactly one stable code — never
the offending value, path, or exception text — unbinds any previously bound
service, and returns the fail-closed summary. Importing this module starts no
process, listener, Gateway, Feishu / IM / delivery surface, socket, daemon, or
Temporal Worker; forbidden terms in this prose are no-leak / denied-surface
boundary canaries only, never behavior.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from gateway.sachima_delegate import (
    bind_delegate_coordinator,
    delegate_payload_resolver,
    unbind_delegate_coordinator,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Env knobs (explicit internal config only; nothing activates by default)
# --------------------------------------------------------------------------- #
SACHIMA_LIVE_PROGRESS_BINDINGS_FILE_ENV = "SACHIMA_LIVE_PROGRESS_BINDINGS_FILE"

#: Backend selection for the host binding. Unset / blank / ``fake`` keeps the
#: static-bindings-file composition over the deterministic fake backend (the
#: default, unchanged). ``arsd`` — combined with the surface gate AND an
#: explicit :data:`SACHIMA_ARSD_CONFIG_FILE_ENV` whose config is explicitly
#: enabled — composes the Socket API v3 execution bundle instead of a
#: hand-written bindings file. ``library`` is retired and answers with the
#: migration code. Any other value fails closed. Nothing here launches an
#: AGENT and no child process is spawned; the daemon is reached lazily inside
#: the spine facade only when turns are dispatched through the (separately
#: gated) dispatcher.
SACHIMA_LIVE_PROGRESS_BACKEND_ENV = "SACHIMA_LIVE_PROGRESS_BACKEND"

#: Private JSON file carrying the ``ArsdSupervisorConfig`` fields for ``arsd``
#: mode. Absent/blank → the binding reports ``..._absent`` and stays
#: fail-closed; a malformed/disabled/forged config collapses to the one stable
#: ``..._invalid`` code without echoing the file path or content. It replaces
#: the retired library-mode config knob outright — there is no read-compat for
#: the old name.
SACHIMA_ARSD_CONFIG_FILE_ENV = "SACHIMA_ARSD_CONFIG_FILE"

#: Private JSON file carrying the ``/delegate`` AGENT profiles. Absent → the
#: legacy single-profile synthesis, which reproduces today's behavior and is
#: available only when each ARS ref map offers exactly one choice. A malformed
#: policy fails the whole ``arsd`` binding closed rather than silently falling
#: back to the legacy profile: an operator who wrote a policy meant it.
SACHIMA_DELEGATE_POLICY_FILE_ENV = "SACHIMA_DELEGATE_POLICY_FILE"

_BACKEND_FAKE = "fake"
_BACKEND_ARSD = "arsd"
#: The complete backend vocabulary. ``library`` is deliberately absent: it is
#: not an admitted value that happens to fail, it is a retired one.
_VALID_BACKENDS = (_BACKEND_FAKE, _BACKEND_ARSD)
_BACKEND_LIBRARY = "library"

#: The only surface value that activates the HOST binding. Mirrors the spine's
#: HERMES_INTERNAL_QUERY_SURFACE without importing the spine on the default path.
_HERMES_INTERNAL_SURFACE = "hermes_internal"

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED = "sachima_live_progress_host_binding_disabled"
SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT = "sachima_live_progress_host_binding_absent"
SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID = "sachima_live_progress_host_binding_invalid"
SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND = "sachima_live_progress_host_binding_bound"

#: Mirrors the spine's one migration seam
#: (``agent_run_supervisor_library_backend.RUNTIME_LIBRARY_BACKEND_RETIRED``)
#: rather than minting a second code that could drift away from it; the
#: gateway's own test asserts the two are equal. Mirrored rather than imported
#: so the default ``fake`` path keeps importing no spine module at all.
SACHIMA_LIVE_PROGRESS_HOST_BINDING_RETIRED = "runtime_library_backend_retired"

SACHIMA_LIVE_PROGRESS_HOST_BINDING_STABLE_CODES = frozenset(
    {
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED,
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT,
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID,
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND,
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_RETIRED,
    }
)

#: LaunchSpec constants for host-bound read-only supervised sessions.
_HOST_BINDING_AGENT_KIND = "local_agent"
_HOST_BINDING_ROLES = ("read_only",)
_HOST_BINDING_REFS = ("ws_live_progress_host", "policy_read_only")

#: The exact ``ArsdSupervisorConfig`` field set a private config file may carry.
#: Unknown keys fail closed rather than being ignored: a typo that silently
#: dropped a grant field would widen the composition by accident.
_ARSD_CONFIG_KEYS = frozenset(
    {
        "type",
        "approval_ref",
        "owner",
        "namespace",
        "socket_path",
        "binding_ledger_path",
        "agent_by_policy_ref",
        "model_by_policy_ref",
        "effort_by_policy_ref",
        "workspace_by_ref",
        "run_limits_by_policy_ref",
        "grant_ref",
        "grant_hash",
        "grant_role_hash",
        "grant_capabilities",
        "mcp_snapshot_hashes",
        "credential_refs",
        "evidence_policy_hash",
        "recovery_policy_hash",
        "expected_package_version",
        "required_api_version",
        "enabled",
    }
)


def _summary(
    code: str,
    bindings: tuple[dict[str, str], ...] = (),
    *,
    backend: str = _BACKEND_FAKE,
) -> dict[str, Any]:
    """A refs-only, JSON-friendly binding summary — never the private paths."""

    return {
        "code": code,
        "backend": backend,
        "binding_count": len(bindings),
        "bindings": list(bindings),
    }


# --------------------------------------------------------------------------- #
# arsd-mode execution bundle (host-held; cleared on every unbind path)
# --------------------------------------------------------------------------- #
_execution_binding: Any | None = None


def bound_execution_binding() -> Any | None:
    """The currently bound ``arsd`` execution bundle, or ``None`` (fake mode)."""

    return _execution_binding


def _set_execution_binding(bundle: Any | None) -> None:
    global _execution_binding
    _execution_binding = bundle
    if bundle is None:
        # The delegate coordinator exists only for a live bundle. Clearing it
        # here — rather than at each of the five unbind call sites — is what
        # makes "no bundle" and "no coordinator" one fact instead of two that
        # can drift apart.
        unbind_delegate_coordinator()


class _RetiredBackendSelected(Exception):
    """A retired ``library`` selection, recognized from a config document.

    Carries nothing: the migration answer is a fixed code, and the document
    that triggered it is exactly what must not travel with it.
    """


def _build_arsd_execution_binding(config_file: str) -> tuple[Any, Any]:
    """Compose the ``arsd`` execution bundle from the private config file.

    Raises on any deviation (unreadable/malformed file, unknown keys, a
    forged/disabled config, an unreachable daemon); the caller collapses every
    raise to the single stable ``..._invalid`` code — the file path/content is
    never echoed. A recognized *retired library* config raises
    :class:`_RetiredBackendSelected` instead, so the operator gets the distinct
    migration code rather than a generic parse verdict.

    The LS4-A gate is the approved ``hermes_internal`` internal surface. The
    dispatcher is given the host's own claim-check resolver — the one seam by
    which a ``/delegate`` submission can turn an opaque ref back into the exact
    task text — and nothing else changes: composing the bundle resolves no ref,
    dispatches no turn, and submits no Run. It is a capability the bundle now
    *has*, not work it does.
    """

    from sachima_supervisor.runtime_spine import hermes_internal_query_gate
    from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
        bind_arsd_execution,
    )
    from sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend import (
        is_retired_library_config,
    )
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ArsdSupervisorConfig,
    )

    with open(config_file, encoding="utf-8") as fh:
        payload = json.load(fh)
    if is_retired_library_config(payload):
        raise _RetiredBackendSelected()
    if type(payload) is not dict:
        raise ValueError(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
    if not set(payload).issubset(_ARSD_CONFIG_KEYS):
        raise ValueError(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
    config = ArsdSupervisorConfig(**payload)
    bundle = bind_arsd_execution(
        config,
        gate=hermes_internal_query_gate(),
        payload_resolver=delegate_payload_resolver(),
    )
    return bundle, config


def _delegate_policy(config: Any) -> Any:
    """The ``/delegate`` routing policy for this composition.

    With ``SACHIMA_DELEGATE_POLICY_FILE`` set, the private policy is read and
    validated against the ARS config; without it, the legacy single profile is
    synthesized, which is exactly today's behavior. Neither path is a fallback
    for the other: a configured policy that does not validate fails the binding
    closed rather than quietly reverting to the legacy profile.
    """

    from gateway.sachima_delegate_policy import (
        load_delegate_policy,
        synthesize_legacy_policy,
    )

    raw = os.environ.get(SACHIMA_DELEGATE_POLICY_FILE_ENV)
    if type(raw) is str and raw.strip():
        return load_delegate_policy(raw.strip(), config)
    return synthesize_legacy_policy(config)


def _load_binding_entries(bindings_file: str) -> list[dict[str, Any]]:
    """Read and shape-check the private bindings file; raise on any deviation.

    The raised exception is caught by the caller and collapsed to the single
    stable ``..._invalid`` code — the file content / path is never echoed.
    """

    with open(bindings_file, encoding="utf-8") as fh:
        payload = json.load(fh)
    if type(payload) is not dict:
        raise ValueError(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
    entries = payload.get("bindings")
    if type(entries) is not list:
        raise ValueError(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
    for entry in entries:
        if type(entry) is not dict:
            raise ValueError(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
    return entries


def _build_display_service(entries: list[dict[str, Any]]) -> tuple[Any, tuple[dict[str, str], ...]]:
    """Compose the real spine service and bind every configured artifact entry.

    All-or-nothing: any unsafe field or composition failure raises (collapsed by
    the caller to the stable invalid code) and nothing global is mutated — the
    registry / port / bindings built here are local until the caller binds the
    returned service into the tool.
    """

    from sachima_supervisor.runtime_spine import (
        DefaultLiveProgressReader,
        LiveProgressDisplayService,
        LiveProgressQueryService,
        LiveProgressSourceBindings,
        TaskRegistry,
        build_launch_spec,
        hermes_internal_query_gate,
        scan_for_leak,
    )
    from sachima_supervisor.runtime_spine.agent_run_supervisor_port import (
        AgentRunSupervisorPort,
        DefaultAgentRunSupervisorBackend,
    )

    task_registry = TaskRegistry()
    port = AgentRunSupervisorPort(task_registry, DefaultAgentRunSupervisorBackend())
    bindings = LiveProgressSourceBindings()
    bound: list[dict[str, str]] = []
    for entry in entries:
        task_id = entry.get("task_id")
        spec = build_launch_spec(
            task_id=task_id,
            agent_kind=_HOST_BINDING_AGENT_KIND,
            mode_flags={"needs_agent": True},
            roles=_HOST_BINDING_ROLES,
            refs=_HOST_BINDING_REFS,
        )
        ref = port.create_or_attach(task_id, spec)
        source = bindings.bind(
            ref.task_id,
            ref.session_id,
            entry.get("artifact_dir"),
            entry.get("artifact_ref"),
        )
        bound.append(
            {
                "task_id": source.task_id,
                "session_id": source.session_id,
                "artifact_ref": source.artifact_ref,
            }
        )

    # Defense in depth: the summary crosses into logs / caller hands — re-scan.
    if scan_for_leak({"bindings": bound}) is not None:
        raise ValueError(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)

    service = LiveProgressDisplayService(
        query_service=LiveProgressQueryService(
            bindings,
            task_registry,
            port,
            DefaultLiveProgressReader(),
            gate=hermes_internal_query_gate(),
        )
    )
    return service, tuple(bound)


def bind_live_progress_display_from_env() -> dict[str, Any]:
    """Build and bind the host ``LiveProgressDisplayService`` from explicit env.

    Fail-closed order: surface gate → backend selection (``fake`` default /
    explicit ``arsd`` / retired ``library``) → mode-specific config present →
    parse / compose / bind. Every failure path returns a stable-code summary,
    leaves (or puts) the tool in its unbound fail-closed posture, and clears any
    previously bound execution bundle; nothing here ever raises, so the gateway
    startup path cannot be broken by this optional internal feature.
    """

    import tools.sachima_live_progress_tool as tool_mod

    if tool_mod.enabled_display_surface() != _HERMES_INTERNAL_SURFACE:
        return _unbind(tool_mod, SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED)

    raw_backend = os.environ.get(SACHIMA_LIVE_PROGRESS_BACKEND_ENV, "")
    backend = raw_backend.strip() if type(raw_backend) is str else ""
    backend = backend or _BACKEND_FAKE
    if backend == _BACKEND_LIBRARY:
        return _retired(tool_mod)
    if backend not in _VALID_BACKENDS:
        # One stable code only — the denied backend value is never echoed.
        logger.warning(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
        return _unbind(tool_mod, SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID, backend="unknown")

    if backend == _BACKEND_ARSD:
        return _bind_arsd_backend(tool_mod)
    return _bind_fake_backend(tool_mod)


def _unbind(
    tool_mod: Any, code: str, *, backend: str = _BACKEND_FAKE
) -> dict[str, Any]:
    """Put the host in its fail-closed posture and report one stable code."""

    _set_execution_binding(None)
    tool_mod.unbind_live_progress_display_service()
    return _summary(code, backend=backend)


def _retired(tool_mod: Any) -> dict[str, Any]:
    """The retired ``library`` selection: one distinct code, nothing composed.

    Deliberately reached *before* any config file is opened: a retired mode has
    no configuration to be right or wrong about, and reading one would invite a
    parse verdict to mask the migration answer. Nothing is bound, dispatched,
    launched, rewritten, or fallen back to.
    """

    from sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend import (
        LIBRARY_MIGRATION_MESSAGE,
    )

    logger.warning(LIBRARY_MIGRATION_MESSAGE)
    return _unbind(
        tool_mod,
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_RETIRED,
        backend=_BACKEND_LIBRARY,
    )


def _bind_fake_backend(tool_mod: Any) -> dict[str, Any]:
    """The default composition: static bindings file over the fake backend."""

    _set_execution_binding(None)  # fake mode never carries an execution bundle

    raw_file = os.environ.get(SACHIMA_LIVE_PROGRESS_BINDINGS_FILE_ENV)
    if type(raw_file) is not str or not raw_file.strip():
        tool_mod.unbind_live_progress_display_service()
        return _summary(SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT)

    try:
        entries = _load_binding_entries(raw_file.strip())
        service, bound = _build_display_service(entries)
        tool_mod.bind_live_progress_display_service(service)
    except Exception:
        # One stable code only — never the file path, content, or exception text.
        tool_mod.unbind_live_progress_display_service()
        logger.warning(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
        return _summary(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)

    logger.info("%s binding_count=%d", SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND, len(bound))
    return _summary(SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND, bound)


def _bind_arsd_backend(tool_mod: Any) -> dict[str, Any]:
    """The explicit Socket API v3 composition (triple default-off).

    Surface gate + explicit private config file + ``enabled`` exactly ``True``,
    all three required. A failure here is final: there is no fallback to the
    fake backend, to a retired library path, to a CLI, or to another API
    version.
    """

    raw_config = os.environ.get(SACHIMA_ARSD_CONFIG_FILE_ENV)
    if type(raw_config) is not str or not raw_config.strip():
        return _unbind(
            tool_mod, SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT, backend=_BACKEND_ARSD
        )

    try:
        bundle, config = _build_arsd_execution_binding(raw_config.strip())
        tool_mod.bind_live_progress_display_service(bundle.display_service)
        # The delegate coordinator is bound over the bundle that was just
        # composed, never beside it: one registry, backend, port, dispatcher,
        # ledger, and bindings store serve both the display chain and
        # `/delegate`. Binding arms the startup barrier: the coordinator
        # completes its restoration scans before it admits anything new.
        bind_delegate_coordinator(bundle, config, policy=_delegate_policy(config))
    except _RetiredBackendSelected:
        return _retired(tool_mod)
    except Exception:
        # One stable code only — never the file path, content, or exception text.
        logger.warning(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
        return _unbind(
            tool_mod, SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID, backend=_BACKEND_ARSD
        )

    _set_execution_binding(bundle)
    logger.info("%s backend=%s", SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND, _BACKEND_ARSD)
    return _summary(SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND, backend=_BACKEND_ARSD)


__all__ = [
    "SACHIMA_ARSD_CONFIG_FILE_ENV",
    "SACHIMA_DELEGATE_POLICY_FILE_ENV",
    "SACHIMA_LIVE_PROGRESS_BACKEND_ENV",
    "SACHIMA_LIVE_PROGRESS_BINDINGS_FILE_ENV",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_RETIRED",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_STABLE_CODES",
    "bind_live_progress_display_from_env",
    "bound_execution_binding",
]
