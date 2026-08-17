"""Retired ``library`` backend — the one fail-closed migration seam.

This module is the ARS 0.7.6 Socket API v3 integration plan's P5-a slice
(``docs/plans/2026-08-17-ars-0.7.6-socket-api-v3-integration-plan.md`` §11,
seam S-1). It used to be the in-process ``agent_run_supervisor`` *library*
backend: a config gate, a session/turn backend, and a lazy facade over
``agent_run_supervisor.role``, ``agent_run_supervisor.workspace``,
``agent_run_supervisor.session_runtime``, ``agent_run_supervisor.session_inspect``
and ``agent_run_supervisor.goal``. The offline seams beside it reached
``agent_run_supervisor.caller`` and ``agent_run_supervisor.hermes_caller``.
Every one of those modules was removed upstream at 0.7.x, so the seam has
nothing left to call.

What replaced it is the ``arsd`` Socket API v3 adapter
(:mod:`~.arsd_supervisor_backend`), and the deterministic ``fake`` backend
remains the default everywhere. This module is what is left: **one** seam that
tells an operator, in one stable code, that the mode they selected is retired.

Boundaries:

* **A retirement, not a fallback.** :func:`library_backend_retired` raises the
  distinct :data:`RUNTIME_LIBRARY_BACKEND_RETIRED` code and nothing else. There
  is no silent rewrite to ``fake`` or ``arsd``, no CLI or package-manager
  launcher path, and no degraded emulation of the removed session-runtime or
  session-inspection surfaces. Nothing is composed, dispatched, launched, or
  mutated on the way to the raise.
* **Distinct on purpose.** The code is deliberately *not*
  ``runtime_arsd_unavailable`` and *not* a generic invalid-config code, so
  "you selected a retired mode" can never be read as "the daemon is down" or
  "your file is malformed".
* **Stable and non-echoing.** :data:`LIBRARY_MIGRATION_MESSAGE` names the two
  supported choices — ``fake`` and ``arsd`` — and is a fixed literal: it never
  carries the rejected value, a file path, a config body, or exception text.
* **Nothing is importable that could run.** The backend class, its config, its
  facade, and its library-unavailable error are gone rather than deprecated, so
  there is no half-working path left for a caller to reach.

The retired module names above are spelled in full here on purpose: this is the
one place the B-10 retired-module guard
(``test_no_retired_agent_run_supervisor_module_references``) admits them, so an
operator reading the migration seam learns exactly what went away. Nothing in
this module imports them.
"""

from __future__ import annotations

from typing import Any, NoReturn

from .events import SpineError

# --------------------------------------------------------------------------- #
# Stable code (module-local; distinct from every unavailable/invalid code)
# --------------------------------------------------------------------------- #
#: The selected supervisor backend is retired. Raised by this seam alone.
RUNTIME_LIBRARY_BACKEND_RETIRED = "runtime_library_backend_retired"

#: The closed failure surface of the retired seam: exactly one code, because
#: the seam does exactly one thing. The three codes this set used to carry
#: (``runtime_ars_library_disabled`` / ``..._unavailable`` /
#: ``runtime_invalid_ars_library_config``) went with the raisers that produced
#: them — an unraisable stable code is a claim about behavior that no longer
#: exists.
ARS_LIBRARY_STABLE_CODES = frozenset({RUNTIME_LIBRARY_BACKEND_RETIRED})

#: The document ``type`` a retired library config file carries. Kept so a
#: composition root can *recognize* one and answer with the migration code
#: instead of a generic parse failure. It is never parsed further.
ARS_LIBRARY_CONFIG_TYPE = "sachima.runtime_spine.ars_library_config.v1"

#: The only supported supervisor backends, in the order an operator should read
#: them: the deterministic default first, the socket adapter second.
SUPPORTED_SUPERVISOR_BACKENDS = ("fake", "arsd")

#: A fixed, non-echoing operator message. The code leads so a log line is
#: greppable; the supported choices follow so the next step is unambiguous.
LIBRARY_MIGRATION_MESSAGE = (
    RUNTIME_LIBRARY_BACKEND_RETIRED
    + ": the agent_run_supervisor library backend is retired; supported backends are "
    + ", ".join(SUPPORTED_SUPERVISOR_BACKENDS)
)


def library_backend_retired() -> NoReturn:
    """Fail closed on a retired ``library`` selection — always, and only.

    Takes no argument by design: there is no selection value, config body, or
    path worth carrying into a stable failure, and accepting one would create
    the echo this seam exists to prevent.
    """

    raise SpineError(RUNTIME_LIBRARY_BACKEND_RETIRED, LIBRARY_MIGRATION_MESSAGE)


def is_retired_library_config(payload: Any) -> bool:
    """True when a config document is a retired library config.

    A composition root calls this *before* it tries to read a payload as
    anything else, so an operator who points the new knob at the old file gets
    the migration code rather than a generic invalid-config verdict. It reads
    exactly one key and never retains, echoes, or validates the rest.
    """

    return (
        isinstance(payload, dict)
        and payload.get("type") == ARS_LIBRARY_CONFIG_TYPE
    )


__all__ = [
    "ARS_LIBRARY_CONFIG_TYPE",
    "ARS_LIBRARY_STABLE_CODES",
    "LIBRARY_MIGRATION_MESSAGE",
    "RUNTIME_LIBRARY_BACKEND_RETIRED",
    "SUPPORTED_SUPERVISOR_BACKENDS",
    "is_retired_library_config",
    "library_backend_retired",
]
