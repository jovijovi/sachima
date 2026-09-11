"""Sachima role-routing matrix — the one YAML authority for ``(AGENT, role)`` → model/effort.

Three catalogs already answer three questions. An **execution preset** says
which registered AGENT this host may run and under which approved workspace,
agent-policy, run-limits refs, and sealed grant. A **role policy** says which
division an AGENT belongs to and which roles it holds, for discovery. Neither
says that the same AGENT should do its Lead Developer work under one model and
its Code Reviewer work under another — and without that fact every
role-bearing delegation went out under the AGENT-wide preset, however
carefully the roles were configured.

This module carries exactly that fact, read from **one** structured YAML file
that the memory palace also renders from::

    schema_version: 1
    default_agents:            # role_id -> canonical agent_id (policy metadata)
      architect: claude
    routes:
      - agent_id: claude
        role_id: architect
        availability: Available   # Available | Paused
        model: "claude-fable-5-1[1m]"
        effort: max
        fallback:                 # null, or exactly {model, effort}
          model: "opus[1m]"
          effort: max

The rules are the ones the sibling catalogs keep:

* **exact identity** — no case folding, no substring, no nearest role, no
  inheritance: a route for ``(claude, lead_developer)`` says nothing about
  ``(claude, code_reviewer)`` or ``(codex, lead_developer)``;
* **literals are literal** — the model selector (context suffix, embedded
  effort/fast selector included) and the effort (``N/A`` included) are stored
  and submitted byte-for-byte; nothing normalizes them;
* **one answer per pair** — a duplicate ``(agent_id, role_id)`` fails the
  whole document closed rather than letting the first or last one win;
* **closed shape** — an unknown key is refused, not ignored;
* **absent means refuse** — a missing route, a ``Paused`` route, an unreadable
  or invalid file, and an unconfigured file each answer with their own stable
  code and **never** with the AGENT-wide preset's model.

``Available`` is stable policy eligibility, not proof of live auth or model
access, and not execution authorization. ``fallback`` is rendered and
reported; it grants no automatic retry. ``default_agents`` is validated and
rendered; it does not add a tie-break to role selection, which stays a
question for the user.

The file is **re-read on every resolution**, so an edit applies to the next
new admission with no Gateway restart, and a file that stops validating stops
routing on that same admission. What an already-admitted Run was sealed under
is the coordinator's durable record, not this file.

Pure local/offline: opens no socket, starts nothing, writes nothing. The
``main`` entry point is the bounded read/render/validate interface the memory
side uses; it prints tables or JSON of the same parsed authority and reports
invalid material as a stable code only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from gateway.sachima_agent_execution_presets import canonical_agent_id
from gateway.sachima_agent_role_policy import role_token

__all__ = [
    "ROUTE_AVAILABILITIES",
    "ROUTING_MATRIX_SCHEMA_VERSION",
    "SACHIMA_ROLE_ROUTE_MISSING",
    "SACHIMA_ROLE_ROUTE_PAUSED",
    "SACHIMA_ROLE_ROUTING_MATRIX_FILE_ENV",
    "SACHIMA_ROLE_ROUTING_MATRIX_INVALID",
    "SACHIMA_ROLE_ROUTING_MATRIX_UNCONFIGURED",
    "SACHIMA_ROLE_ROUTING_STABLE_CODES",
    "RoleRoute",
    "RoleRouteFallback",
    "RoleRouteResolution",
    "RoleRoutingMatrix",
    "RoleRoutingMatrixSource",
    "RoutingMatrixError",
    "build_routing_matrix",
    "configured_routing_matrix_source",
    "load_routing_matrix",
    "main",
    "parse_routing_matrix",
    "render_routing_matrix_table",
    "resolve_role_route",
]

ROUTING_MATRIX_SCHEMA_VERSION = 1

#: The one explicitly configured host path. Named, never defaulted: a product
#: that guessed an operator's memory-palace location would be a deployment
#: nobody declared, and profiles must not share one implicitly.
SACHIMA_ROLE_ROUTING_MATRIX_FILE_ENV = "SACHIMA_ROLE_ROUTING_MATRIX_FILE"

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
#: A role was supplied but this host composed no routing matrix at all.
SACHIMA_ROLE_ROUTING_MATRIX_UNCONFIGURED = "sachima_role_routing_matrix_unconfigured"
#: The matrix file cannot be read, is not valid YAML, or does not validate.
SACHIMA_ROLE_ROUTING_MATRIX_INVALID = "sachima_role_routing_matrix_invalid"
#: No route for this exact ``(agent_id, role_id)`` pair.
SACHIMA_ROLE_ROUTE_MISSING = "sachima_role_route_missing"
#: The route exists and is ``Paused``: not assignable until re-enabled.
SACHIMA_ROLE_ROUTE_PAUSED = "sachima_role_route_paused"

SACHIMA_ROLE_ROUTING_STABLE_CODES = frozenset(
    {
        SACHIMA_ROLE_ROUTING_MATRIX_UNCONFIGURED,
        SACHIMA_ROLE_ROUTING_MATRIX_INVALID,
        SACHIMA_ROLE_ROUTE_MISSING,
        SACHIMA_ROLE_ROUTE_PAUSED,
    }
)

ROUTE_AVAILABILITIES = ("Available", "Paused")
_AVAILABLE = "Available"

#: The model selector is bounded printable text, mirroring the ARS request's
#: own ``requested_model`` rule (non-empty, printable, at most 512 chars) so a
#: route this module accepts is one a submit could carry. Mirrored rather than
#: imported: this module stays importable with no spine module behind it.
_MAX_MODEL_CHARS = 512
#: The effort is an ordinary wire token, or exactly ``N/A`` — the canonical
#: "no separate effort selector" value ARS compares by exact equality.
_EFFORT_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_EFFORT_NOT_APPLICABLE = "N/A"

_MAX_ROUTES = 1024
_DOCUMENT_KEYS = frozenset({"schema_version", "default_agents", "routes"})
_ROUTE_KEYS = frozenset(
    {"agent_id", "role_id", "availability", "model", "effort", "fallback"}
)
_FALLBACK_KEYS = frozenset({"model", "effort"})

_TABLE_HEADER = "| AGENT | Role | Model | Effort | Availability | Fallback Model / Effort |"
_TABLE_DIVIDER = "|---|---|---|---|---|---|"


class RoutingMatrixError(ValueError):
    """A matrix failure whose message IS the stable code — never the material."""


def _invalid() -> "RoutingMatrixError":
    return RoutingMatrixError(SACHIMA_ROLE_ROUTING_MATRIX_INVALID)


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _model_literal(value: Any) -> str:
    if type(value) is not str or not value or len(value) > _MAX_MODEL_CHARS:
        raise _invalid()
    if not value.isprintable():
        raise _invalid()
    return value


def _effort_literal(value: Any) -> str:
    if type(value) is str and value == _EFFORT_NOT_APPLICABLE:
        return value
    if type(value) is not str or _EFFORT_TOKEN_RE.fullmatch(value) is None:
        raise _invalid()
    return value


def _required_agent_id(value: Any) -> str:
    agent_id = canonical_agent_id(value)
    if agent_id is None:
        raise _invalid()
    return agent_id


def _required_role_id(value: Any) -> str:
    role_id = role_token(value)
    if role_id is None:
        raise _invalid()
    return role_id


@dataclass(frozen=True)
class RoleRouteFallback:
    """The exact alternate pair a route names. Metadata, never retry authority."""

    model: str
    effort: str

    def as_dict(self) -> dict[str, str]:
        return {"model": self.model, "effort": self.effort}


@dataclass(frozen=True)
class RoleRoute:
    """One ``(agent_id, role_id)`` and the literal model/effort it runs under."""

    agent_id: str
    role_id: str
    availability: str
    model: str
    effort: str
    fallback: RoleRouteFallback | None = None

    @property
    def available(self) -> bool:
        return self.availability == _AVAILABLE

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role_id": self.role_id,
            "availability": self.availability,
            "model": self.model,
            "effort": self.effort,
            "fallback": None if self.fallback is None else self.fallback.as_dict(),
        }


@dataclass(frozen=True)
class RoleRoutingMatrix:
    """The validated matrix, its provenance digest, and the one lookup routing needs."""

    schema_version: int
    default_agents: Mapping[str, str]
    routes: tuple[RoleRoute, ...]
    #: ``sha256:`` digest of the exact source bytes. Provenance, not a
    #: cryptographic authorization boundary: it says which file version a
    #: Run was sealed from, so a later edit is distinguishable from it.
    source_digest: str

    def route(self, agent_id: Any, role_id: Any) -> RoleRoute | None:
        """The route for this exact pair, or ``None``. Exact identity only."""

        if type(agent_id) is not str or type(role_id) is not str:
            return None
        for route in self.routes:
            if route.agent_id == agent_id and route.role_id == role_id:
                return route
        return None

    def filter(
        self,
        *,
        agent_id: str | None = None,
        role_id: str | None = None,
        availability: str | None = None,
    ) -> tuple[RoleRoute, ...]:
        """Routes matching every supplied filter exactly, in document order."""

        return tuple(
            route
            for route in self.routes
            if (agent_id is None or route.agent_id == agent_id)
            and (role_id is None or route.role_id == role_id)
            and (availability is None or route.availability == availability)
        )

    def as_dict(self) -> dict[str, Any]:
        """The accepted document shape, exactly — what a file would contain."""

        return {
            "schema_version": self.schema_version,
            "default_agents": dict(self.default_agents),
            "routes": [route.as_dict() for route in self.routes],
        }


def _parse_fallback(value: Any) -> RoleRouteFallback | None:
    if value is None:
        return None
    if type(value) is not dict or set(value) != _FALLBACK_KEYS:
        raise _invalid()
    return RoleRouteFallback(
        model=_model_literal(value["model"]), effort=_effort_literal(value["effort"])
    )


def _parse_route(entry: Any) -> RoleRoute:
    if type(entry) is not dict or set(entry) != _ROUTE_KEYS:
        raise _invalid()
    availability = entry["availability"]
    if type(availability) is not str or availability not in ROUTE_AVAILABILITIES:
        raise _invalid()
    return RoleRoute(
        agent_id=_required_agent_id(entry["agent_id"]),
        role_id=_required_role_id(entry["role_id"]),
        availability=availability,
        model=_model_literal(entry["model"]),
        effort=_effort_literal(entry["effort"]),
        fallback=_parse_fallback(entry["fallback"]),
    )


def build_routing_matrix(document: Any, *, source_digest: Any) -> RoleRoutingMatrix:
    """Validate one already-parsed document, or fail closed."""

    if type(source_digest) is not str or _DIGEST_RE.fullmatch(source_digest) is None:
        raise _invalid()
    if type(document) is not dict or set(document) != _DOCUMENT_KEYS:
        raise _invalid()
    version = document["schema_version"]
    if type(version) is not int or version != ROUTING_MATRIX_SCHEMA_VERSION:
        raise _invalid()
    entries = document["routes"]
    if type(entries) is not list or not entries or len(entries) > _MAX_ROUTES:
        raise _invalid()

    routes: list[RoleRoute] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        route = _parse_route(entry)
        key = (route.agent_id, route.role_id)
        # One pair, one route: two would make "which model" a question with
        # two answers, and picking either is a guess.
        if key in seen:
            raise _invalid()
        seen.add(key)
        routes.append(route)

    defaults = document["default_agents"]
    if type(defaults) is not dict:
        raise _invalid()
    owned_defaults: dict[str, str] = {}
    for raw_role, raw_agent in defaults.items():
        role_id = _required_role_id(raw_role)
        agent_id = _required_agent_id(raw_agent)
        # A default names a pair the matrix actually routes. Its availability
        # is the route's own business; a default is metadata, not a route.
        if (agent_id, role_id) not in seen:
            raise _invalid()
        owned_defaults[role_id] = agent_id

    return RoleRoutingMatrix(
        schema_version=version,
        default_agents=MappingProxyType(dict(sorted(owned_defaults.items()))),
        routes=tuple(routes),
        source_digest=source_digest,
    )


def parse_routing_matrix(data: Any) -> RoleRoutingMatrix:
    """Parse the exact file bytes: digest them, load YAML safely, validate."""

    if type(data) is not bytes or not data:
        raise _invalid()
    try:
        import yaml

        document = yaml.safe_load(data.decode("utf-8"))
    except RoutingMatrixError:
        raise
    except Exception:
        # ``from None``: a YAML error message quotes the offending line, and a
        # decode error quotes the bytes. Neither may ride out on the chain.
        raise _invalid() from None
    return build_routing_matrix(document, source_digest=_digest(data))


def _configured_path(value: Any) -> str:
    if type(value) is not str or not value.strip():
        raise _invalid()
    return value.strip()


def load_routing_matrix(path: Any) -> RoleRoutingMatrix:
    """Read one file's bytes and parse them. Never echoes the path or content."""

    configured = _configured_path(path)
    try:
        with open(configured, "rb") as handle:
            data = handle.read()
    except Exception:
        raise _invalid() from None
    return parse_routing_matrix(data)


class RoleRoutingMatrixSource:
    """One explicitly configured matrix file, re-read on every ``load``.

    Holding the path rather than the parsed matrix is the whole point: a
    matrix edit applies to the next new admission without a Gateway restart,
    and a file that stops validating stops routing on that admission. The
    path is private host material and never appears on ``repr``/``str``.
    """

    __slots__ = ("_path",)

    def __init__(self, path: Any) -> None:
        self._path = _configured_path(path)

    def load(self) -> RoleRoutingMatrix:
        return load_routing_matrix(self._path)

    def __repr__(self) -> str:
        return "RoleRoutingMatrixSource(<configured>)"

    __str__ = __repr__


def configured_routing_matrix_source(
    env: Mapping[str, str] | None = None,
) -> RoleRoutingMatrixSource | None:
    """The host-declared matrix source, proven readable once — or ``None``.

    The one env key both composition roots read. Undeclared is a valid
    composition: nothing routes by role, and every non-role admission is
    exactly what it was. A declared file that does not validate raises, so a
    host that asked for role routing and cannot have it fails closed at
    composition rather than refusing every role admission later with nobody
    watching. The file is still re-read on every admission afterwards.
    """

    source_env = os.environ if env is None else env
    declared = source_env.get(SACHIMA_ROLE_ROUTING_MATRIX_FILE_ENV)
    if declared is None or (type(declared) is str and not declared.strip()):
        return None
    source = RoleRoutingMatrixSource(declared)
    source.load()
    return source


@dataclass(frozen=True)
class RoleRouteResolution:
    """One routing answer: a route with its provenance, or a stable refusal.

    A refused resolution carries no route and no digest, so nothing downstream
    can seal a Run from a refusal by reading past the code.
    """

    route: RoleRoute | None = None
    source_digest: str | None = None
    refusal: str | None = None

    @property
    def resolved(self) -> bool:
        return self.route is not None


def resolve_role_route(source: Any, agent_id: Any, role_id: Any) -> RoleRouteResolution:
    """The literal model/effort one ``(agent_id, role_id)`` runs under — or why not.

    Exactly one of four refusals, each its own stable code, because they need
    different things said to the user and different things done by the
    operator: nothing configured, a file that does not validate, a pair nobody
    routed, and a pair deliberately paused. None of them is an invitation to
    run under the AGENT-wide preset instead.
    """

    if source is None:
        return RoleRouteResolution(refusal=SACHIMA_ROLE_ROUTING_MATRIX_UNCONFIGURED)
    try:
        matrix = source.load()
    except RoutingMatrixError as error:
        return RoleRouteResolution(refusal=str(error))
    except Exception:
        return RoleRouteResolution(refusal=SACHIMA_ROLE_ROUTING_MATRIX_INVALID)
    if type(matrix) is not RoleRoutingMatrix:
        return RoleRouteResolution(refusal=SACHIMA_ROLE_ROUTING_MATRIX_INVALID)

    wanted_agent = canonical_agent_id(agent_id)
    wanted_role = role_token(role_id)
    if wanted_agent is None or wanted_role is None:
        # A filter that is not an id cannot match an id: a miss, not a repair.
        return RoleRouteResolution(refusal=SACHIMA_ROLE_ROUTE_MISSING)
    route = matrix.route(wanted_agent, wanted_role)
    if route is None:
        return RoleRouteResolution(refusal=SACHIMA_ROLE_ROUTE_MISSING)
    if not route.available:
        return RoleRouteResolution(refusal=SACHIMA_ROLE_ROUTE_PAUSED)
    return RoleRouteResolution(route=route, source_digest=matrix.source_digest)


# --------------------------------------------------------------------------- #
# Rendering — the memory side's human-readable view of the same authority
# --------------------------------------------------------------------------- #
def _cell(text: str) -> str:
    # A literal never contains a control character (validated), but a ``|``
    # would split the row; it is escaped as Markdown tables expect.
    return text.replace("|", "\\|")


def render_routing_matrix_table(
    matrix: RoleRoutingMatrix,
    *,
    agent_id: str | None = None,
    role_id: str | None = None,
    availability: str | None = None,
) -> str:
    """A Markdown table in the original matrix's column order, filtered exactly."""

    if type(matrix) is not RoleRoutingMatrix:
        raise _invalid()
    lines = [_TABLE_HEADER, _TABLE_DIVIDER]
    for route in matrix.filter(
        agent_id=agent_id, role_id=role_id, availability=availability
    ):
        fallback = (
            ""
            if route.fallback is None
            else f"`{_cell(route.fallback.model)} + {_cell(route.fallback.effort)}`"
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    _cell(route.agent_id),
                    _cell(route.role_id),
                    f"`{_cell(route.model)}`",
                    f"`{_cell(route.effort)}`",
                    route.availability,
                    fallback,
                )
            )
            + " |"
        )
    return "\n".join(lines)


def _rendered_json(
    matrix: RoleRoutingMatrix,
    *,
    agent_id: str | None,
    role_id: str | None,
    availability: str | None,
) -> str:
    document = matrix.as_dict()
    document["source_digest"] = matrix.source_digest
    document["routes"] = [
        route.as_dict()
        for route in matrix.filter(
            agent_id=agent_id, role_id=role_id, availability=availability
        )
    ]
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False)


def main(argv: Sequence[str] | None = None) -> int:
    """Validate, render, or filter one routing matrix file. Stable codes only.

    Exit status: ``0`` on success, ``1`` when the file is invalid, ``2`` for a
    usage error (including no file named and no ``SACHIMA_ROLE_ROUTING_MATRIX_FILE``).
    """

    parser = argparse.ArgumentParser(
        prog="sachima_agent_role_routing_matrix",
        description=(
            "Read the shared AGENT/role routing matrix (YAML) and render it, "
            "filtered, as a Markdown table or JSON; or only validate it."
        ),
    )
    parser.add_argument(
        "--file",
        help=f"path to routing-matrix.yaml (default: ${SACHIMA_ROLE_ROUTING_MATRIX_FILE_ENV})",
    )
    parser.add_argument("--agent", help="exact canonical agent_id filter")
    parser.add_argument("--role", help="exact role_id filter")
    parser.add_argument(
        "--availability", choices=ROUTE_AVAILABILITIES, help="exact availability filter"
    )
    parser.add_argument(
        "--format", choices=("table", "json"), default="table", help="output format"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="only validate; print the digest and counts, render nothing",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    path = args.file if args.file is not None else os.environ.get(SACHIMA_ROLE_ROUTING_MATRIX_FILE_ENV)
    if type(path) is not str or not path.strip():
        print(SACHIMA_ROLE_ROUTING_MATRIX_UNCONFIGURED, file=sys.stderr)
        return 2

    try:
        matrix = load_routing_matrix(path)
    except RoutingMatrixError as error:
        print(str(error), file=sys.stderr)
        return 1

    if args.validate:
        agents = {route.agent_id for route in matrix.routes}
        roles = {route.role_id for route in matrix.routes}
        print(
            "routing_matrix_ok "
            f"schema_version={matrix.schema_version} "
            f"routes={len(matrix.routes)} agents={len(agents)} roles={len(roles)} "
            f"digest={matrix.source_digest}"
        )
        return 0

    if args.format == "json":
        print(
            _rendered_json(
                matrix,
                agent_id=args.agent,
                role_id=args.role,
                availability=args.availability,
            )
        )
    else:
        print(
            render_routing_matrix_table(
                matrix,
                agent_id=args.agent,
                role_id=args.role,
                availability=args.availability,
            )
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
