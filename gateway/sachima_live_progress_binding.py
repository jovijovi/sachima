"""Gateway host binding for the default-off ``sachima_live_progress_display`` tool.

This module is the **host-side composition seam** that makes the LS4
``LiveProgressDisplayService`` real inside the Gateway/Feishu host process. It
stays default-off behind two explicit, independent knobs and fails closed on
everything else:

1. **Surface gate** — the binding only activates when
   ``SACHIMA_LIVE_PROGRESS_DISPLAY_SURFACE`` is exactly ``hermes_internal`` (the
   existing LS4-A approved internal surface). Unset / denied / truthy-looking
   values — and even the approved ``local_offline`` tool surface, which belongs
   to offline harnesses, never to a gateway host — leave this a no-op.
2. **Bindings file** — ``SACHIMA_LIVE_PROGRESS_BINDINGS_FILE`` must point at a
   private local JSON file of the shape
   ``{"bindings": [{"task_id", "artifact_dir", "artifact_ref"}, ...]}``. With no
   file configured the binding reports ``..._absent`` and the tool keeps failing
   closed with its own stable ``sachima_live_progress_display_unbound`` code.

With both knobs present the binding builds the full spine composition —
``LiveProgressSourceBindings`` + ``TaskRegistry`` + ``AgentRunSupervisorPort``
over the deterministic default backend + the lazy ``DefaultLiveProgressReader``
+ ``LiveProgressQueryService`` carrying the LS4-A ``hermes_internal`` gate +
``LiveProgressDisplayService`` — creates one real Sachima task/session per
configured artifact binding via ``create_or_attach``, and binds the service into
``tools.sachima_live_progress_tool``. The returned summary carries only safe
refs (``task_id`` / ``session_id`` / ``artifact_ref``) and counts; the
configured ``artifact_dir`` is handed to the spine's binding store only and is
never returned, logged, or serialized.

The producer library resolves ONLY from the installed exact-pinned
``agent-run-supervisor`` distribution (the ``agent-run-supervisor`` /
``dev`` extra in ``pyproject.toml``); this module mutates no import path and
reads no source-checkout env — the historical source-path shim is retired so
a checkout can never shadow the reviewed pin. There is no top-level (or any
direct) ``agent_run_supervisor`` import here — the producer is reached only
through the injected lazy reader, which fails closed to a clean
``live_progress_unavailable`` display when the import is impossible (e.g. the
extra is not installed on this host).

Failure policy (never crash gateway startup): a malformed / unreadable bindings
file, an unsafe ``task_id`` / ``artifact_ref``, an empty ``artifact_dir``, or
any composition error logs exactly one stable ``..._invalid`` code — never the
offending value, path, or exception text — unbinds any previously bound service,
and returns the fail-closed summary. Importing this module starts no process,
listener, Gateway, Feishu / IM / delivery surface, or Temporal Worker; forbidden
terms in this prose are no-leak / denied-surface boundary canaries only, never
behavior.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Env knobs (explicit internal config only; nothing activates by default)
# --------------------------------------------------------------------------- #
SACHIMA_LIVE_PROGRESS_BINDINGS_FILE_ENV = "SACHIMA_LIVE_PROGRESS_BINDINGS_FILE"

#: Backend selection for the host binding. Unset / blank / ``fake`` keeps
#: today's static-bindings-file composition over the deterministic fake
#: backend (the default, unchanged). ``library`` — combined with the surface
#: gate AND an explicit :data:`SACHIMA_ARS_LIBRARY_CONFIG_FILE_ENV` — composes
#: the formal ARS-INT execution bundle (real library backend + turn dispatcher
#: + dispatcher-fed source bindings) instead of a hand-written bindings file.
#: Any other value fails closed. Nothing here launches an AGENT/acpx and no
#: child process is spawned; the library is reached lazily inside the spine
#: facade only when turns are dispatched through the (separately gated)
#: dispatcher.
SACHIMA_LIVE_PROGRESS_BACKEND_ENV = "SACHIMA_LIVE_PROGRESS_BACKEND"

#: Private JSON file carrying the ``AgentRunSupervisorLibraryConfig`` fields
#: for ``library`` mode. Absent/blank → the binding reports ``..._absent`` and
#: stays fail-closed; a malformed/disabled/forged config collapses to the one
#: stable ``..._invalid`` code without echoing the file path or content.
SACHIMA_ARS_LIBRARY_CONFIG_FILE_ENV = "SACHIMA_ARS_LIBRARY_CONFIG_FILE"

_BACKEND_FAKE = "fake"
_BACKEND_LIBRARY = "library"
_VALID_BACKENDS = (_BACKEND_FAKE, _BACKEND_LIBRARY)

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

SACHIMA_LIVE_PROGRESS_HOST_BINDING_STABLE_CODES = frozenset(
    {
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED,
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT,
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID,
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND,
    }
)

#: LaunchSpec constants for host-bound read-only supervised sessions.
_HOST_BINDING_AGENT_KIND = "local_agent"
_HOST_BINDING_ROLES = ("read_only",)
_HOST_BINDING_REFS = ("ws_live_progress_host", "policy_read_only")


def _summary(
    code: str,
    bindings: tuple[dict[str, str], ...] = (),
    *,
    backend: str = _BACKEND_FAKE,
) -> dict[str, Any]:
    """A refs-only, JSON-friendly binding summary — never the private dir."""

    return {
        "code": code,
        "backend": backend,
        "binding_count": len(bindings),
        "bindings": list(bindings),
    }


# --------------------------------------------------------------------------- #
# Library-mode execution bundle (host-held; cleared on every unbind path)
# --------------------------------------------------------------------------- #
_execution_binding: Any | None = None


def bound_execution_binding() -> Any | None:
    """The currently bound ARS-INT execution bundle, or ``None`` (fake mode)."""

    return _execution_binding


def _set_execution_binding(bundle: Any | None) -> None:
    global _execution_binding
    _execution_binding = bundle


def _build_library_execution_binding(config_file: str) -> Any:
    """Compose the formal execution bundle from the private library config file.

    Raises on any deviation (unreadable/malformed file, unknown keys, a
    forged/disabled config); the caller collapses every raise to the single
    stable ``..._invalid`` code — the file path/content is never echoed. The
    LS4-A gate is the approved ``hermes_internal`` internal surface; nothing
    live/default-on and no payload resolver is wired here, so the bundle's
    dispatcher stays fail-closed until an internal caller injects one.
    """

    from sachima_supervisor.runtime_spine import hermes_internal_query_gate
    from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
        bind_agent_run_supervisor_execution,
    )
    from sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend import (
        AgentRunSupervisorLibraryConfig,
    )

    with open(config_file, encoding="utf-8") as fh:
        payload = json.load(fh)
    if type(payload) is not dict:
        raise ValueError(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
    allowed_keys = {
        "type",
        "enabled",
        "approval_ref",
        "sessions_dir",
        "workspace_by_ref",
        "role_by_ref",
        "session_prefix",
        "acpx_binary",
        "stale_after_seconds",
    }
    if not set(payload).issubset(allowed_keys):
        raise ValueError(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
    config = AgentRunSupervisorLibraryConfig(**payload)
    return bind_agent_run_supervisor_execution(config, gate=hermes_internal_query_gate())


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
    explicit ``library``) → mode-specific config present → parse / compose /
    bind. Every failure path returns a stable-code summary, leaves (or puts)
    the tool in its unbound fail-closed posture, and clears any previously
    bound library execution bundle; nothing here ever raises, so the gateway
    startup path cannot be broken by this optional internal feature.
    """

    import tools.sachima_live_progress_tool as tool_mod

    if tool_mod.enabled_display_surface() != _HERMES_INTERNAL_SURFACE:
        _set_execution_binding(None)
        tool_mod.unbind_live_progress_display_service()
        return _summary(SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED)

    raw_backend = os.environ.get(SACHIMA_LIVE_PROGRESS_BACKEND_ENV, "")
    backend = raw_backend.strip() if type(raw_backend) is str else ""
    backend = backend or _BACKEND_FAKE
    if backend not in _VALID_BACKENDS:
        # One stable code only — the denied backend value is never echoed.
        _set_execution_binding(None)
        tool_mod.unbind_live_progress_display_service()
        logger.warning(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
        return _summary(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID, backend="unknown")

    if backend == _BACKEND_LIBRARY:
        return _bind_library_backend(tool_mod)
    return _bind_fake_backend(tool_mod)


def _bind_fake_backend(tool_mod: Any) -> dict[str, Any]:
    """The default composition: static bindings file over the fake backend."""

    _set_execution_binding(None)  # fake mode never carries a library bundle

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


def _bind_library_backend(tool_mod: Any) -> dict[str, Any]:
    """The explicit ARS-INT library composition (double default-off)."""

    raw_config = os.environ.get(SACHIMA_ARS_LIBRARY_CONFIG_FILE_ENV)
    if type(raw_config) is not str or not raw_config.strip():
        _set_execution_binding(None)
        tool_mod.unbind_live_progress_display_service()
        return _summary(
            SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT, backend=_BACKEND_LIBRARY
        )

    try:
        bundle = _build_library_execution_binding(raw_config.strip())
        tool_mod.bind_live_progress_display_service(bundle.display_service)
    except Exception:
        # One stable code only — never the file path, content, or exception text.
        _set_execution_binding(None)
        tool_mod.unbind_live_progress_display_service()
        logger.warning(SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID)
        return _summary(
            SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID, backend=_BACKEND_LIBRARY
        )

    _set_execution_binding(bundle)
    logger.info("%s backend=%s", SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND, _BACKEND_LIBRARY)
    return _summary(SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND, backend=_BACKEND_LIBRARY)


__all__ = [
    "SACHIMA_LIVE_PROGRESS_BINDINGS_FILE_ENV",
    "SACHIMA_LIVE_PROGRESS_BACKEND_ENV",
    "SACHIMA_ARS_LIBRARY_CONFIG_FILE_ENV",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_STABLE_CODES",
    "bind_live_progress_display_from_env",
    "bound_execution_binding",
]
