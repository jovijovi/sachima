"""R1 Runtime Spine — static Capability Registry.

A **static table** keyed by ``agent_kind`` (design §4). It is *not* a plugin
system: there is no dynamic import, no env/config discovery, no filesystem or
network lookup — just a frozen literal table validated on read. ``get_capability``
fails closed for unknown, platform-derived, write-ish, live-ish, or badly-charset
``agent_kind`` values. Each capability is five booleans matching the design:
``attach_resume``, ``permission_events``, ``workspace_isolation``, ``liveness``,
``stream_resume``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .events import RUNTIME_UNKNOWN_CAPABILITY, SpineError, _safe_kind

CAPABILITY_FIELDS = (
    "attach_resume",
    "permission_events",
    "workspace_isolation",
    "liveness",
    "stream_resume",
)


@dataclass(frozen=True)
class Capability:
    """Frozen capability row — the five static design fields, booleans only."""

    attach_resume: bool
    permission_events: bool
    workspace_isolation: bool
    liveness: bool
    stream_resume: bool


#: The static capability table. Keys are the only ``agent_kind`` values R1 knows.
#: ``inline_tool`` is the ``(needs_agent=false, needs_durable=false)`` lane with no
#: live/attach/permission surface; ``local_agent`` is the supervised external
#: local AGENT runtime (attach/stream/permission/workspace/liveness);
#: ``durable_activity`` is the attach-only durable lane (no live stream).
_CAPABILITY_TABLE: dict[str, Capability] = {
    "inline_tool": Capability(
        attach_resume=False,
        permission_events=False,
        workspace_isolation=False,
        liveness=False,
        stream_resume=False,
    ),
    "local_agent": Capability(
        attach_resume=True,
        permission_events=True,
        workspace_isolation=True,
        liveness=True,
        stream_resume=True,
    ),
    "durable_activity": Capability(
        attach_resume=True,
        permission_events=False,
        workspace_isolation=True,
        liveness=True,
        stream_resume=False,
    ),
}


def known_agent_kinds() -> frozenset[str]:
    """The static set of known ``agent_kind`` keys (no discovery)."""

    return frozenset(_CAPABILITY_TABLE)


def get_capability(agent_kind: str) -> Capability:
    """Return the static capability for a known, safe ``agent_kind`` or fail closed.

    Unknown, platform-derived, write-ish, live-ish, or badly-charset kinds all
    raise ``SpineError(runtime_unknown_capability)`` — the table is closed.
    """

    safe_kind = _safe_kind(agent_kind, code=RUNTIME_UNKNOWN_CAPABILITY)
    capability = _CAPABILITY_TABLE.get(safe_kind)
    if capability is None:
        raise SpineError(RUNTIME_UNKNOWN_CAPABILITY)
    return capability
