"""Default-off internal tool surface over the Sachima LS4 live-progress display.

This module makes the PR-LS4-B ``LiveProgressDisplayService`` reachable from the
tool-schema/config surface as ``sachima_live_progress_display`` — while keeping
the whole path **default-off** behind two independent gates:

1. **Availability gate** — the tool's ``check_fn`` only passes when
   ``SACHIMA_LIVE_PROGRESS_DISPLAY_SURFACE`` is set to exactly one of the LS4-A
   approved local/offline surfaces (``local_offline`` / ``hermes_internal``).
   Any other value (including ``1`` / ``true`` / ``gateway`` / ``feishu``) keeps
   the schema hidden. The ``sachima_live_progress`` toolset is additionally not
   part of ``_HERMES_CORE_TOOLS`` or any platform default toolset, so the tool
   never appears in a normal Feishu/IM session unless a profile explicitly
   names the toolset in its config **and** the env gate is enabled.
2. **Service gate** — the handler only consumes a host-bound
   ``LiveProgressDisplayService`` (see :func:`bind_live_progress_display_service`).
   With no bound service it fails closed with a stable code before touching any
   binding, reader, or artifact; the bound service itself still enforces the
   LS4-A default-off ``LiveProgressQueryActivationGate``.

The tool result is a sanitized ``live_progress_display.v1`` envelope: the frozen
refs/counts/status-only ``LiveProgressDisplay`` dict plus a deterministic
markdown fallback joined from its closed-template ``display_lines``. It never
carries raw stdout / stderr / agent text / tool output / transcripts / private
artifact paths, and it deliberately contains no gateway rich-result markers, so
it can never activate card delivery on its own. Every failure path returns a
stable code only — the offending input is never echoed.

Everything here is pure local/offline Python: importing, gating, or failing
closed starts no process, listener, Gateway, Feishu, IM/delivery surface, or
Temporal Worker, and the ``agent_run_supervisor`` library is never imported —
the producer is reached only through the reader already injected into the
host-bound service. Forbidden terms in this prose are no-leak / denied-surface
boundary canaries only, never behavior.
"""

from __future__ import annotations

import os
import threading
from typing import Any

from tools.registry import registry, tool_error, tool_result

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
SACHIMA_LIVE_PROGRESS_DISPLAY_DISABLED = "sachima_live_progress_display_disabled"
SACHIMA_LIVE_PROGRESS_DISPLAY_UNBOUND = "sachima_live_progress_display_unbound"
SACHIMA_LIVE_PROGRESS_DISPLAY_INVALID = "sachima_live_progress_display_invalid"

SACHIMA_LIVE_PROGRESS_DISPLAY_STABLE_CODES = frozenset(
    {
        SACHIMA_LIVE_PROGRESS_DISPLAY_DISABLED,
        SACHIMA_LIVE_PROGRESS_DISPLAY_UNBOUND,
        SACHIMA_LIVE_PROGRESS_DISPLAY_INVALID,
    }
)

#: Tool-level envelope type. The nested ``display`` dict keeps the spine's own
#: ``sachima.runtime_spine.live_progress_display.v1`` type.
LIVE_PROGRESS_DISPLAY_ENVELOPE_TYPE = "live_progress_display.v1"

#: Explicit activation env var. The value must be exactly one of the LS4-A
#: approved local/offline surfaces — mirroring APPROVED_QUERY_SURFACES without
#: importing the spine at module import time. Anything else stays closed.
SACHIMA_LIVE_PROGRESS_SURFACE_ENV = "SACHIMA_LIVE_PROGRESS_DISPLAY_SURFACE"
_APPROVED_TOOL_SURFACES = frozenset({"local_offline", "hermes_internal"})

TOOL_NAME = "sachima_live_progress_display"
TOOLSET_NAME = "sachima_live_progress"


def enabled_display_surface() -> str | None:
    """Return the activated surface token, or ``None`` when default-off.

    An exact allowlist over ``SACHIMA_LIVE_PROGRESS_DISPLAY_SURFACE``: unset,
    empty, truthy-looking (``1`` / ``true``), or denied (``gateway`` /
    ``feishu`` / anything else) values all keep the surface closed.
    """

    raw = os.environ.get(SACHIMA_LIVE_PROGRESS_SURFACE_ENV)
    if type(raw) is not str:
        return None
    value = raw.strip()
    if value not in _APPROVED_TOOL_SURFACES:
        return None
    return value


def check_live_progress_display_available() -> bool:
    """``check_fn`` for the registry: schema is hidden unless the env gate is on."""

    return enabled_display_surface() is not None


# --------------------------------------------------------------------------- #
# Host-bound display service seam (default: unbound → fails closed)
# --------------------------------------------------------------------------- #
_service_lock = threading.Lock()
_display_service: Any = None


def bind_live_progress_display_service(service: Any) -> None:
    """Bind the host-owned ``LiveProgressDisplayService`` consumed by the tool.

    The service must be an exact ``LiveProgressDisplayService`` (its own
    ``__post_init__`` already validated the wrapped query service); anything
    else fails closed with the module's stable invalid code. Binding wires no
    gate and reads nothing — the service's bundled LS4-A gate keeps deciding
    whether queries are activated.
    """

    from sachima_supervisor.runtime_spine import LiveProgressDisplayService, SpineError

    if type(service) is not LiveProgressDisplayService:
        raise SpineError(SACHIMA_LIVE_PROGRESS_DISPLAY_INVALID)
    with _service_lock:
        global _display_service
        _display_service = service


def unbind_live_progress_display_service() -> None:
    """Return the tool to its default unbound (fail-closed) posture."""

    with _service_lock:
        global _display_service
        _display_service = None


def _bound_service() -> Any:
    with _service_lock:
        return _display_service


# --------------------------------------------------------------------------- #
# Handler — gate, then consume only the safe display layer
# --------------------------------------------------------------------------- #
def _passthrough_stable_code(exc: Any) -> str:
    """Map a spine failure to a stable code, never echoing material.

    Only the three codes this surface can legitimately observe pass through
    (display invalid, query invalid, query disabled); anything unexpected
    collapses to the tool's own stable invalid code.
    """

    from sachima_supervisor.runtime_spine.live_progress_display import (
        LIVE_PROGRESS_DISPLAY_STABLE_CODES,
    )
    from sachima_supervisor.runtime_spine.live_progress_query import (
        LIVE_PROGRESS_QUERY_STABLE_CODES,
    )

    code = getattr(exc, "code", None)
    if code in LIVE_PROGRESS_DISPLAY_STABLE_CODES or code in LIVE_PROGRESS_QUERY_STABLE_CODES:
        return code
    return SACHIMA_LIVE_PROGRESS_DISPLAY_INVALID


def _handle_live_progress_display(args: dict, **kw) -> str:
    """Render one supervised session's live progress as a sanitized envelope.

    Fail-closed order: env gate → bound service → the service's own LS4-A gate
    and field validation. Every failure returns a stable code only.
    """

    if enabled_display_surface() is None:
        return tool_error(SACHIMA_LIVE_PROGRESS_DISPLAY_DISABLED)
    service = _bound_service()
    if service is None:
        return tool_error(SACHIMA_LIVE_PROGRESS_DISPLAY_UNBOUND)

    from sachima_supervisor.runtime_spine import SpineError, scan_for_leak

    if type(args) is not dict:
        return tool_error(SACHIMA_LIVE_PROGRESS_DISPLAY_INVALID)
    task_id = args.get("task_id")
    session_id = args.get("session_id")
    after_seq = args.get("after_seq")
    limit = args.get("limit", 100)

    try:
        display = service.display_task_live_progress(
            task_id, session_id, after_seq=after_seq, limit=limit
        )
        payload = display.as_dict()
    except SpineError as exc:
        return tool_error(_passthrough_stable_code(exc))
    except Exception:
        return tool_error(SACHIMA_LIVE_PROGRESS_DISPLAY_INVALID)

    envelope = {
        "type": LIVE_PROGRESS_DISPLAY_ENVELOPE_TYPE,
        "display": payload,
        "markdown": "\n".join(payload["display_lines"]),
    }
    # Defense in depth: the display dict is already refs/counts/status-only and
    # line-rerender-checked, but the envelope crosses a tool boundary — re-scan.
    if scan_for_leak(envelope) is not None:
        return tool_error(SACHIMA_LIVE_PROGRESS_DISPLAY_INVALID)
    return tool_result(envelope)


# --------------------------------------------------------------------------- #
# Schema + registration (hidden unless the env gate is enabled)
# --------------------------------------------------------------------------- #
LIVE_PROGRESS_DISPLAY_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "INTERNAL, default-off: render one Sachima-supervised session's live "
        "progress as a safe, bounded, refs/counts/status-only display "
        "(closed-vocabulary status tokens, event counts per family, resume "
        "cursor — never raw agent output or paths). Requires the explicit "
        f"{SACHIMA_LIVE_PROGRESS_SURFACE_ENV} gate and a host-bound display "
        "service; otherwise it fails closed with a stable code."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Sachima task id of the tracked session.",
            },
            "session_id": {
                "type": "string",
                "description": "Tracked session id (sess_...).",
            },
            "after_seq": {
                "type": "integer",
                "description": (
                    "Optional foreign resume cursor override for this one read; "
                    "defaults to the binding's last seen cursor."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max projected event records to aggregate (1-1000, default 100).",
            },
        },
        "required": ["task_id", "session_id"],
    },
}

registry.register(
    name=TOOL_NAME,
    toolset=TOOLSET_NAME,
    schema=LIVE_PROGRESS_DISPLAY_SCHEMA,
    handler=_handle_live_progress_display,
    check_fn=check_live_progress_display_available,
    emoji="📊",
)
