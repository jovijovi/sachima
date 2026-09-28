"""Sachima role/division policy — the deterministic half of "who does this?".

"Find an AGENT suited to architecture design" is two questions in one
sentence. *Which role does architecture design need?* is language, and Hermes
owns it. *Which registered, executable AGENT holds that role?* is arithmetic
over three explicit facts, and that is the whole of this module.

The three facts, and who owns each:

* the **live ARS roster** — what the daemon loaded. ARS owns it;
* the **execution preset** — whether this host may run that AGENT at all, and
  under which approved refs and sealed grant.
  :mod:`gateway.sachima_agent_execution_presets` owns it;
* the **role/division assignment** — which division an AGENT belongs to and
  which roles it holds. This module owns it.

They are kept in separate catalogs deliberately. A preset is a *permission to
execute*; the moment it also carried "who is good at what" it would become a
router, and a router grows priority fields, weights, aliases and a default
long before anyone notices. None of those exist here either:

* matching is **exact** — no case folding, no substring, no fuzzy resolution;
* there is no ranking of any kind, so a role held by two AGENTs is a question
  for the user rather than a tie to break;
* an AGENT with no assignment inherits nothing. It stays registered, possibly
  executable when named explicitly, and simply invisible to role routing.

Explicit selection by ``agent_id`` never comes through here at all — it goes
straight to execution eligibility, which is what keeps a named delegation
auditable.

Pure local/offline: this module opens no socket, starts nothing, reaches no
daemon, and writes nothing. :func:`build_agent_eligibility_view` and
:func:`select_agent_by_role` are decisions over their arguments; the one live
read that produces the roster belongs to the ``arsd`` backend.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Sequence

from gateway.sachima_agent_execution_presets import (
    AgentExecutionPresets,
    canonical_agent_id,
)

__all__ = [
    "AGENT_ROLE_POLICY_TYPE",
    "SACHIMA_AGENT_ROLE_AMBIGUOUS",
    "SACHIMA_AGENT_ROLE_INVALID_POLICY",
    "SACHIMA_AGENT_ROLE_NO_CANDIDATE",
    "SACHIMA_AGENT_ROLE_STABLE_CODES",
    "AgentEligibility",
    "AgentRoleAssignment",
    "AgentRolePolicy",
    "AgentRoleSelection",
    "RolePolicyError",
    "build_agent_eligibility_view",
    "build_agent_role_policy",
    "empty_agent_role_policy",
    "load_agent_role_policy",
    "select_agent_by_role",
]

AGENT_ROLE_POLICY_TYPE = "sachima.gateway.agent_role_policy.v1"

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
SACHIMA_AGENT_ROLE_INVALID_POLICY = "sachima_agent_role_invalid_policy"
SACHIMA_AGENT_ROLE_NO_CANDIDATE = "sachima_agent_role_no_candidate"
SACHIMA_AGENT_ROLE_AMBIGUOUS = "sachima_agent_role_ambiguous"

SACHIMA_AGENT_ROLE_STABLE_CODES = frozenset(
    {
        SACHIMA_AGENT_ROLE_INVALID_POLICY,
        SACHIMA_AGENT_ROLE_NO_CANDIDATE,
        SACHIMA_AGENT_ROLE_AMBIGUOUS,
    }
)

#: Division and role names are lowercase snake tokens. They are vocabulary an
#: operator writes and Hermes maps language onto — never free text, so a
#: catalog cannot smuggle prose, identity, or a sentence in as a "role".
_ROLE_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_MAX_ASSIGNMENTS = 64
_MAX_ROLES_PER_AGENT = 16

#: The assignment document's exact key set. A ranking, alias, or platform
#: field is refused rather than ignored: silently dropping it would let an
#: operator believe this catalog ranks when it does not.
_ASSIGNMENT_KEYS = frozenset({"agent_id", "division", "roles"})
_DOCUMENT_KEYS = frozenset({"type", "assignments"})


class RolePolicyError(ValueError):
    """A policy failure whose message IS the stable code — never the material."""


def _invalid() -> "RolePolicyError":
    return RolePolicyError(SACHIMA_AGENT_ROLE_INVALID_POLICY)


def role_token(value: Any) -> str | None:
    """``value`` if it is exactly a role/division token, else ``None``."""

    if type(value) is not str or _ROLE_TOKEN_RE.fullmatch(value) is None:
        return None
    return value


def _required_token(value: Any) -> str:
    token = role_token(value)
    if token is None:
        raise _invalid()
    return token


def _roles(value: Any) -> tuple[str, ...]:
    if type(value) is not list or not value or len(value) > _MAX_ROLES_PER_AGENT:
        raise _invalid()
    tokens = [_required_token(item) for item in value]
    if len(set(tokens)) != len(tokens):
        raise _invalid()
    # Sorted, so the catalog's own answer never depends on typing order.
    return tuple(sorted(tokens))


@dataclass(frozen=True)
class AgentRoleAssignment:
    """One AGENT's division and the roles it holds. No ranking, ever."""

    agent_id: str
    division: str
    roles: tuple[str, ...]

    def holds(self, *, role: str | None, division: str | None) -> bool:
        """Exact membership. Both filters, when given, must hold."""

        if role is not None and role not in self.roles:
            return False
        if division is not None and division != self.division:
            return False
        return True


@dataclass(frozen=True)
class AgentRolePolicy:
    """The validated assignment catalog, and the one lookup routing needs."""

    assignments: tuple[AgentRoleAssignment, ...] = ()

    def for_agent(self, agent_id: Any) -> AgentRoleAssignment | None:
        """This exact canonical id's assignment, or ``None``.

        Exact identity only, and no default entry: an AGENT nobody assigned a
        role stays unassigned rather than borrowing one.
        """

        if type(agent_id) is not str:
            return None
        for assignment in self.assignments:
            if assignment.agent_id == agent_id:
                return assignment
        return None


def empty_agent_role_policy() -> AgentRolePolicy:
    """The catalog of a host that configured none: nothing is role-routable.

    An answer, not a fallback. Every AGENT stays reachable by explicit name;
    none is reachable by role, which is the honest state of a host whose
    operator has not said who does what.
    """

    return AgentRolePolicy()


def build_agent_role_policy(document: Any) -> AgentRolePolicy:
    """Validate one role/division document, or fail closed."""

    if type(document) is not dict or set(document) != _DOCUMENT_KEYS:
        raise _invalid()
    if document["type"] != AGENT_ROLE_POLICY_TYPE:
        raise _invalid()
    entries = document["assignments"]
    if type(entries) is not list or not entries or len(entries) > _MAX_ASSIGNMENTS:
        raise _invalid()

    assignments: list[AgentRoleAssignment] = []
    seen: set[str] = set()
    for entry in entries:
        if type(entry) is not dict or set(entry) != _ASSIGNMENT_KEYS:
            raise _invalid()
        agent_id = canonical_agent_id(entry["agent_id"])
        if agent_id is None:
            raise _invalid()
        # One AGENT, one assignment: two would make "which division is it in"
        # a question with two answers.
        if agent_id in seen:
            raise _invalid()
        seen.add(agent_id)
        assignments.append(
            AgentRoleAssignment(
                agent_id=agent_id,
                division=_required_token(entry["division"]),
                roles=_roles(entry["roles"]),
            )
        )
    return AgentRolePolicy(assignments=tuple(assignments))


def load_agent_role_policy(policy_file: Any) -> AgentRolePolicy:
    """Read the private role/division file and validate it. Never echoes it."""

    if type(policy_file) is not str or not policy_file.strip():
        raise _invalid()
    try:
        with open(policy_file.strip(), encoding="utf-8") as handle:
            document = json.load(handle)
    except RolePolicyError:
        raise
    except Exception:
        raise _invalid() from None
    return build_agent_role_policy(document)


# --------------------------------------------------------------------------- #
# The eligibility view: the live roster, annotated with both halves
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgentEligibility:
    """What this host can truthfully say about one registered AGENT.

    Every field is a fact with a named owner: ``registered`` is the daemon's,
    ``executable`` is the execution preset's, ``division``/``roles`` are the
    role catalog's. They are reported separately rather than collapsed into
    one "available" flag, because "registered but this host cannot run it"
    and "runnable but holds no role" are different things to tell a user.
    """

    agent_id: str
    registered: bool
    executable: bool
    division: str | None
    roles: tuple[str, ...]

    @property
    def role_routable(self) -> bool:
        """Selectable *by role*: registered, executable, and holding a role.

        Missing either half is not a near miss to be rounded up. An AGENT the
        host cannot run is not a candidate however well its role matches, and
        one with no assignment is not a candidate however well it runs.
        """

        return self.registered and self.executable and bool(self.roles)

    def as_dict(self) -> dict[str, Any]:
        """Flags and closed-vocabulary tokens only — never refs or config."""

        return {
            "agent_id": self.agent_id,
            "registered": self.registered,
            "executable": self.executable,
            "division": self.division,
            "roles": list(self.roles),
            "role_routable": self.role_routable,
        }


def build_agent_eligibility_view(
    *,
    registered_agent_ids: Sequence[str],
    presets: Any,
    role_policy: Any,
) -> tuple[AgentEligibility, ...]:
    """The live roster, annotated with execution and role facts. Pure.

    The roster is the population: an assignment or preset for an AGENT the
    daemon never loaded does not appear at all, because this view describes
    what *is* registered rather than what someone configured.

    Order is the roster's own, which the contract validator already fixed as
    ascending. It is not a ranking and nothing downstream reads it as one.
    """

    catalog = presets if type(presets) is AgentExecutionPresets else None
    policy = role_policy if type(role_policy) is AgentRolePolicy else None
    view: list[AgentEligibility] = []
    for raw in registered_agent_ids or ():
        agent_id = canonical_agent_id(raw)
        if agent_id is None:
            continue
        assignment = policy.for_agent(agent_id) if policy is not None else None
        view.append(
            AgentEligibility(
                agent_id=agent_id,
                registered=True,
                executable=(
                    catalog is not None and catalog.preset(agent_id) is not None
                ),
                division=assignment.division if assignment is not None else None,
                roles=assignment.roles if assignment is not None else (),
            )
        )
    return tuple(view)


@dataclass(frozen=True)
class AgentRoleSelection:
    """One role-routing answer: a single AGENT, or a question to ask.

    ``candidates`` is populated on an ambiguous answer so Hermes can ask the
    user which one — it is the material for a clarification, never a shortlist
    for this layer to pick from.
    """

    agent_id: str | None = None
    refusal: str | None = None
    candidates: tuple[str, ...] = ()

    @property
    def selected(self) -> bool:
        return self.agent_id is not None


def select_agent_by_role(
    *,
    registered_agent_ids: Sequence[str],
    presets: Any,
    role_policy: Any,
    role: Any = None,
    division: Any = None,
) -> AgentRoleSelection:
    """The one AGENT an exact role/division names — or a question. Pure.

    Exactly one eligible candidate is selectable. Zero and several are both
    refusals with their own stable code, because they need different things
    said to the user: "nobody here does that" and "several do, which did you
    mean". Neither writes a task, a Session, or a Run.

    There is deliberately no tie-break. Priority, weight, alphabetical order
    and "the one that answered last time" are all ways of guessing which AGENT
    a person meant, and that guess belongs to the conversation.

    A call with neither filter selects nothing: "just pick one" is not a
    question this layer answers.
    """

    wanted_role = role_token(role) if role is not None else None
    wanted_division = role_token(division) if division is not None else None
    if (role is not None and wanted_role is None) or (
        division is not None and wanted_division is None
    ):
        # A filter that is not a token cannot match a token. It is a miss, not
        # an invitation to ignore the filter and match everything.
        return AgentRoleSelection(refusal=SACHIMA_AGENT_ROLE_NO_CANDIDATE)
    if wanted_role is None and wanted_division is None:
        return AgentRoleSelection(refusal=SACHIMA_AGENT_ROLE_NO_CANDIDATE)

    policy = role_policy if type(role_policy) is AgentRolePolicy else None
    if policy is None:
        return AgentRoleSelection(refusal=SACHIMA_AGENT_ROLE_NO_CANDIDATE)

    candidates = tuple(
        entry.agent_id
        for entry in build_agent_eligibility_view(
            registered_agent_ids=registered_agent_ids,
            presets=presets,
            role_policy=policy,
        )
        if entry.role_routable
        and _holds(policy, entry.agent_id, wanted_role, wanted_division)
    )
    if not candidates:
        return AgentRoleSelection(refusal=SACHIMA_AGENT_ROLE_NO_CANDIDATE)
    if len(candidates) > 1:
        return AgentRoleSelection(
            refusal=SACHIMA_AGENT_ROLE_AMBIGUOUS, candidates=candidates
        )
    return AgentRoleSelection(agent_id=candidates[0], candidates=candidates)


def _holds(
    policy: AgentRolePolicy,
    agent_id: str,
    role: str | None,
    division: str | None,
) -> bool:
    assignment = policy.for_agent(agent_id)
    return assignment is not None and assignment.holds(role=role, division=division)
