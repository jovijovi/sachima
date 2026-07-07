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

Optionally, ``SACHIMA_LIVE_PROGRESS_AGENT_RUN_SUPERVISOR_SRC_PATH`` (or the
plain ``AGENT_RUN_SUPERVISOR_SRC_PATH``) names a source checkout to prepend to
``sys.path`` so the reader's lazy ``agent_run_supervisor.hermes_caller.events``
import can resolve on hosts where the library is not installed. There is no
top-level (or any direct) ``agent_run_supervisor`` import here — the producer is
reached only through the injected lazy reader, which fails closed to a clean
``live_progress_unavailable`` display when the import is impossible.

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
import sys
from typing import Any

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Env knobs (explicit internal config only; nothing activates by default)
# --------------------------------------------------------------------------- #
SACHIMA_LIVE_PROGRESS_BINDINGS_FILE_ENV = "SACHIMA_LIVE_PROGRESS_BINDINGS_FILE"
SACHIMA_LIVE_PROGRESS_ARS_SRC_PATH_ENV = (
    "SACHIMA_LIVE_PROGRESS_AGENT_RUN_SUPERVISOR_SRC_PATH"
)
AGENT_RUN_SUPERVISOR_SRC_PATH_ENV = "AGENT_RUN_SUPERVISOR_SRC_PATH"

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
SACHIMA_LIVE_PROGRESS_ARS_SRC_PATH_IGNORED = "sachima_live_progress_ars_src_path_ignored"

SACHIMA_LIVE_PROGRESS_HOST_BINDING_STABLE_CODES = frozenset(
    {
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED,
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT,
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID,
        SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND,
        SACHIMA_LIVE_PROGRESS_ARS_SRC_PATH_IGNORED,
    }
)

#: LaunchSpec constants for host-bound read-only supervised sessions.
_HOST_BINDING_AGENT_KIND = "local_agent"
_HOST_BINDING_ROLES = ("read_only",)
_HOST_BINDING_REFS = ("ws_live_progress_host", "policy_read_only")


def _summary(code: str, bindings: tuple[dict[str, str], ...] = ()) -> dict[str, Any]:
    """A refs-only, JSON-friendly binding summary — never the private dir."""

    return {"code": code, "binding_count": len(bindings), "bindings": list(bindings)}


def _prepend_agent_run_supervisor_src_path() -> None:
    """Prepend the configured ARS source checkout to ``sys.path``, if valid.

    Reads the sachima-prefixed env first, then the plain fallback. A missing /
    blank value is the default no-op; a configured value that is not an existing
    directory logs the stable ignored code (never the path) and changes nothing.
    """

    raw = os.environ.get(SACHIMA_LIVE_PROGRESS_ARS_SRC_PATH_ENV) or os.environ.get(
        AGENT_RUN_SUPERVISOR_SRC_PATH_ENV
    )
    if type(raw) is not str:
        return
    path = raw.strip()
    if not path:
        return
    if not os.path.isdir(path):
        logger.warning(SACHIMA_LIVE_PROGRESS_ARS_SRC_PATH_IGNORED)
        return
    if path not in sys.path:
        sys.path.insert(0, path)


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

    Fail-closed order: surface gate → bindings file present → parse / compose /
    bind. Every failure path returns a stable-code summary and leaves (or puts)
    the tool in its unbound fail-closed posture; nothing here ever raises, so
    the gateway startup path cannot be broken by this optional internal feature.
    """

    import tools.sachima_live_progress_tool as tool_mod

    if tool_mod.enabled_display_surface() != _HERMES_INTERNAL_SURFACE:
        tool_mod.unbind_live_progress_display_service()
        return _summary(SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED)

    raw_file = os.environ.get(SACHIMA_LIVE_PROGRESS_BINDINGS_FILE_ENV)
    if type(raw_file) is not str or not raw_file.strip():
        tool_mod.unbind_live_progress_display_service()
        return _summary(SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT)

    _prepend_agent_run_supervisor_src_path()

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


__all__ = [
    "SACHIMA_LIVE_PROGRESS_BINDINGS_FILE_ENV",
    "SACHIMA_LIVE_PROGRESS_ARS_SRC_PATH_ENV",
    "AGENT_RUN_SUPERVISOR_SRC_PATH_ENV",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_DISABLED",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_ABSENT",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_INVALID",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_BOUND",
    "SACHIMA_LIVE_PROGRESS_ARS_SRC_PATH_IGNORED",
    "SACHIMA_LIVE_PROGRESS_HOST_BINDING_STABLE_CODES",
    "bind_live_progress_display_from_env",
]
