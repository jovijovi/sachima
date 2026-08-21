"""Sachima ``/delegate`` — private AGENT profiles and one deterministic route.

A delegate policy is a list of **profiles**. Each profile names exactly the five
ref categories the spine already understands — workspace, agent policy, model
policy, effort policy, run-limits policy — plus the presentation and admission
metadata routing needs: a safe profile id, enabled / auto-selectable flags,
capability tags, a task-size bound, a priority, a short user-facing summary, and
optional structured-mention mappings.

Two things this module deliberately is **not**:

* it is not a second ARS config. Every ref must resolve through the existing
  :class:`~sachima_supervisor.runtime_spine.arsd_socket_contract.ArsdSupervisorConfig`,
  and grants, credentials, socket paths, and the ledger path stay config-wide.
  A profile chooses *among* what the operator already approved; it can never
  widen it;
* it is not a dispatcher. :func:`resolve_route` is a pure decision over the
  policy and one request. It creates no Session, writes no state, and reaches no
  daemon.

One router serves both creation paths (the slash command and the gated control
service), which is what makes "the same request routes the same way" a property
of the code rather than a convention. Its order is fixed:

1. a **verified explicit selector** wins or refuses — never a fallback;
2. a **trusted requested profile id** wins or refuses — never a fallback;
3. otherwise the enabled, auto-selectable profiles are filtered by task size and
   required capabilities; no candidate refuses, one candidate wins, several
   candidates use highest priority only when that priority is unique, and a
   remaining tie asks for clarification instead of guessing.

With no policy file configured, :func:`synthesize_legacy_policy` reproduces
today's single-profile behavior — but *only* when each ARS ref map offers
exactly one choice, so a config that offers a choice still refuses rather than
having one picked for the operator. The synthesized profile carries no mention
mapping, so an explicit selector against it refuses instead of silently becoming
the legacy profile.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

__all__ = [
    "DELEGATE_POLICY_TYPE",
    "DEFAULT_MAX_TASK_BYTES",
    "SACHIMA_DELEGATE_AMBIGUOUS_ROUTE",
    "SACHIMA_DELEGATE_INVALID_POLICY",
    "SACHIMA_DELEGATE_NO_ROUTE",
    "SACHIMA_DELEGATE_POLICY_STABLE_CODES",
    "SACHIMA_DELEGATE_TASK_TOO_LARGE",
    "SACHIMA_DELEGATE_UNKNOWN_PROFILE",
    "SACHIMA_DELEGATE_UNKNOWN_SELECTOR",
    "DelegatePolicy",
    "DelegateProfile",
    "RouteDecision",
    "load_delegate_policy",
    "requested_configuration",
    "resolve_route",
    "synthesize_legacy_policy",
]

DELEGATE_POLICY_TYPE = "sachima.gateway.delegate_policy.v1"

#: The default per-profile task-size bound, in UTF-8 bytes. It is deliberately
#: below the ARS prompt bound so a task refused here is refused *before* a
#: Session exists, not after a submit was spent on learning it.
DEFAULT_MAX_TASK_BYTES = 32_768

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
SACHIMA_DELEGATE_INVALID_POLICY = "sachima_delegate_invalid_policy"
SACHIMA_DELEGATE_UNKNOWN_SELECTOR = "sachima_delegate_unknown_selector"
SACHIMA_DELEGATE_UNKNOWN_PROFILE = "sachima_delegate_unknown_profile"
SACHIMA_DELEGATE_NO_ROUTE = "sachima_delegate_no_route"
SACHIMA_DELEGATE_AMBIGUOUS_ROUTE = "sachima_delegate_ambiguous_route"
SACHIMA_DELEGATE_TASK_TOO_LARGE = "sachima_delegate_task_too_large"

SACHIMA_DELEGATE_POLICY_STABLE_CODES = frozenset(
    {
        SACHIMA_DELEGATE_INVALID_POLICY,
        SACHIMA_DELEGATE_UNKNOWN_SELECTOR,
        SACHIMA_DELEGATE_UNKNOWN_PROFILE,
        SACHIMA_DELEGATE_NO_ROUTE,
        SACHIMA_DELEGATE_AMBIGUOUS_ROUTE,
        SACHIMA_DELEGATE_TASK_TOO_LARGE,
    }
)

_SAFE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_WORKSPACE_REF_PREFIX = "ws_"
_POLICY_REF_PREFIX = "policy_"
_MAX_SUMMARY_CHARS = 120
_MAX_PROFILES = 64

#: The profile document's exact key set. Unknown keys fail closed rather than
#: being ignored: a typo that silently dropped ``enabled`` would widen the
#: policy by accident.
_PROFILE_KEYS = frozenset(
    {
        "profile_id",
        "workspace_ref",
        "agent_policy_ref",
        "model_policy_ref",
        "effort_policy_ref",
        "run_limits_policy_ref",
        "enabled",
        "auto_selectable",
        "capabilities",
        "max_task_bytes",
        "priority",
        "summary",
        "mentions",
    }
)
_POLICY_KEYS = frozenset({"type", "profiles"})
_MENTION_KEYS = frozenset({"platform", "platform_user_id"})


def _invalid_policy() -> "PolicyError":
    return PolicyError(SACHIMA_DELEGATE_INVALID_POLICY)


class PolicyError(ValueError):
    """A policy failure whose message IS the stable code — never the material."""


def _safe_token(value: Any) -> str:
    if type(value) is not str or _SAFE_ID_RE.fullmatch(value) is None:
        raise _invalid_policy()
    return value


def _prefixed_ref(value: Any, prefix: str) -> str:
    ref = _safe_token(value)
    if not ref.startswith(prefix):
        raise _invalid_policy()
    return ref


def _safe_summary(value: Any) -> str:
    if value is None:
        return ""
    if type(value) is not str or len(value) > _MAX_SUMMARY_CHARS:
        raise _invalid_policy()
    if "\n" in value or "\r" in value:
        raise _invalid_policy()
    return value.strip()


def _safe_flag(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if type(value) is not bool:
        raise _invalid_policy()
    return value


def _safe_count(value: Any, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or type(value) is not int:
        raise _invalid_policy()
    if value < 0 or value > maximum:
        raise _invalid_policy()
    return value


@dataclass(frozen=True)
class DelegateProfile:
    """One routable AGENT choice: five ref categories plus routing metadata.

    ``mention_ids`` is the structured-mention mapping — ``(platform,
    platform_user_id)`` pairs and nothing else. Display names are never stored,
    because a display name is not identity and a mapping keyed on one would
    route a task by whatever a user happens to have called themselves today.
    """

    profile_id: str
    workspace_ref: str
    agent_policy_ref: str
    model_policy_ref: str
    effort_policy_ref: str
    run_limits_policy_ref: str
    enabled: bool = True
    auto_selectable: bool = True
    capabilities: tuple[str, ...] = ()
    max_task_bytes: int = DEFAULT_MAX_TASK_BYTES
    priority: int = 0
    summary: str = ""
    mention_ids: tuple[tuple[str, str], ...] = field(default=())

    @property
    def launch_refs(self) -> tuple[str, ...]:
        """The distinct refs this profile's sessions are admitted under.

        First-seen order with duplicates collapsed: the backend matches the ref
        *set* against each of the five config maps and demands exactly one match
        per map, so one ref legitimately serving several categories must appear
        once, not five times.
        """

        refs: list[str] = []
        for ref in (
            self.workspace_ref,
            self.agent_policy_ref,
            self.model_policy_ref,
            self.effort_policy_ref,
            self.run_limits_policy_ref,
        ):
            if ref not in refs:
                refs.append(ref)
        return tuple(refs)

    def accepts(self, *, task_bytes: int, required: Sequence[str]) -> bool:
        if task_bytes > self.max_task_bytes:
            return False
        return all(tag in self.capabilities for tag in required)

    def choice_line(self) -> str:
        """One user-facing line naming this profile. Refs never appear."""

        return f"{self.profile_id}: {self.summary}" if self.summary else self.profile_id


@dataclass(frozen=True)
class DelegatePolicy:
    """The validated profile list, plus the two lookups routing needs."""

    profiles: tuple[DelegateProfile, ...]

    def profile(self, profile_id: Any) -> DelegateProfile | None:
        if type(profile_id) is not str:
            return None
        for profile in self.profiles:
            if profile.profile_id == profile_id:
                return profile
        return None

    def by_mention(self, platform: Any, platform_user_id: Any) -> DelegateProfile | None:
        """The profile a structured occurrence selects, or ``None``.

        Identity only: the pair must match exactly. There is no display-name
        tier and no case-folding fallback, so an unmapped occurrence stays
        unmapped instead of being resolved by resemblance.
        """

        if type(platform) is not str or type(platform_user_id) is not str:
            return None
        for profile in self.profiles:
            if (platform, platform_user_id) in profile.mention_ids:
                return profile
        return None

    def choices(self) -> tuple[str, ...]:
        """The available AGENT choices, for a refusal that is worth reading."""

        return tuple(
            profile.choice_line() for profile in self.profiles if profile.enabled
        )


@dataclass(frozen=True)
class RouteDecision:
    """One routing answer: a profile, or a refusal with the available choices."""

    profile: DelegateProfile | None = None
    refusal: str | None = None
    choices: tuple[str, ...] = ()

    @property
    def routed(self) -> bool:
        return self.profile is not None


# --------------------------------------------------------------------------- #
# Policy documents
# --------------------------------------------------------------------------- #
def _parse_mentions(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if type(value) is not list:
        raise _invalid_policy()
    pairs: list[tuple[str, str]] = []
    for entry in value:
        if type(entry) is not dict or set(entry) != _MENTION_KEYS:
            raise _invalid_policy()
        platform = entry["platform"]
        user_id = entry["platform_user_id"]
        if type(platform) is not str or not platform.strip():
            raise _invalid_policy()
        if type(user_id) is not str or not user_id.strip():
            raise _invalid_policy()
        pair = (platform.strip(), user_id.strip())
        if pair in pairs:
            raise _invalid_policy()
        pairs.append(pair)
    return tuple(pairs)


def _parse_capabilities(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if type(value) is not list:
        raise _invalid_policy()
    return tuple(_safe_token(item) for item in value)


def _parse_profile(entry: Any) -> DelegateProfile:
    if type(entry) is not dict or not set(entry).issubset(_PROFILE_KEYS):
        raise _invalid_policy()
    return DelegateProfile(
        profile_id=_safe_token(entry.get("profile_id")),
        workspace_ref=_prefixed_ref(entry.get("workspace_ref"), _WORKSPACE_REF_PREFIX),
        agent_policy_ref=_prefixed_ref(
            entry.get("agent_policy_ref"), _POLICY_REF_PREFIX
        ),
        model_policy_ref=_prefixed_ref(
            entry.get("model_policy_ref"), _POLICY_REF_PREFIX
        ),
        effort_policy_ref=_prefixed_ref(
            entry.get("effort_policy_ref"), _POLICY_REF_PREFIX
        ),
        run_limits_policy_ref=_prefixed_ref(
            entry.get("run_limits_policy_ref"), _POLICY_REF_PREFIX
        ),
        enabled=_safe_flag(entry.get("enabled"), default=True),
        auto_selectable=_safe_flag(entry.get("auto_selectable"), default=True),
        capabilities=_parse_capabilities(entry.get("capabilities")),
        max_task_bytes=_safe_count(
            entry.get("max_task_bytes"),
            default=DEFAULT_MAX_TASK_BYTES,
            maximum=DEFAULT_MAX_TASK_BYTES,
        ),
        priority=_safe_count(entry.get("priority"), default=0, maximum=1_000),
        summary=_safe_summary(entry.get("summary")),
        mention_ids=_parse_mentions(entry.get("mentions")),
    )


def _require_refs_resolve(profile: DelegateProfile, config: Any) -> None:
    """Every ref must be one the operator already approved in the ARS config."""

    for ref, mapping in (
        (profile.workspace_ref, getattr(config, "workspace_by_ref", None)),
        (profile.agent_policy_ref, getattr(config, "agent_by_policy_ref", None)),
        (profile.model_policy_ref, getattr(config, "model_by_policy_ref", None)),
        (profile.effort_policy_ref, getattr(config, "effort_by_policy_ref", None)),
        (
            profile.run_limits_policy_ref,
            getattr(config, "run_limits_by_policy_ref", None),
        ),
    ):
        if not isinstance(mapping, Mapping) or ref not in mapping:
            raise _invalid_policy()


def build_delegate_policy(document: Any, config: Any) -> DelegatePolicy:
    """Validate one policy document against the ARS config, or fail closed."""

    if type(document) is not dict or set(document) != _POLICY_KEYS:
        raise _invalid_policy()
    if document["type"] != DELEGATE_POLICY_TYPE:
        raise _invalid_policy()
    entries = document["profiles"]
    if type(entries) is not list or not entries or len(entries) > _MAX_PROFILES:
        raise _invalid_policy()

    profiles: list[DelegateProfile] = []
    seen_ids: set[str] = set()
    seen_mentions: set[tuple[str, str]] = set()
    for entry in entries:
        profile = _parse_profile(entry)
        if profile.profile_id in seen_ids:
            raise _invalid_policy()
        seen_ids.add(profile.profile_id)
        for pair in profile.mention_ids:
            # One occurrence must select at most one AGENT, or "explicit
            # selection never guesses" would be false by construction.
            if pair in seen_mentions:
                raise _invalid_policy()
            seen_mentions.add(pair)
        _require_refs_resolve(profile, config)
        profiles.append(profile)
    return DelegatePolicy(profiles=tuple(profiles))


def load_delegate_policy(policy_file: Any, config: Any) -> DelegatePolicy:
    """Read the private policy file and validate it. Never echoes the file."""

    if type(policy_file) is not str or not policy_file.strip():
        raise _invalid_policy()
    try:
        with open(policy_file.strip(), encoding="utf-8") as handle:
            document = json.load(handle)
    except PolicyError:
        raise
    except Exception:
        raise _invalid_policy() from None
    return build_delegate_policy(document, config)


def synthesize_legacy_policy(config: Any) -> DelegatePolicy:
    """The single profile today's ``/delegate`` already runs under.

    Synthesized only when each of the five ARS ref maps offers exactly one
    choice: a config that offers a choice is not one this path can honor, and it
    refuses rather than picking for the operator. The synthesized profile has no
    mention mapping on purpose — an explicit selector against a policy nobody
    wrote refuses instead of quietly becoming the legacy profile.
    """

    refs: list[str] = []
    for mapping in (
        getattr(config, "workspace_by_ref", None),
        getattr(config, "agent_by_policy_ref", None),
        getattr(config, "model_by_policy_ref", None),
        getattr(config, "effort_by_policy_ref", None),
        getattr(config, "run_limits_by_policy_ref", None),
    ):
        keys = list(mapping) if isinstance(mapping, Mapping) else []
        if len(keys) != 1:
            raise _invalid_policy()
        refs.append(keys[0])
    workspace, agent, model, effort, limits = refs
    return DelegatePolicy(
        profiles=(
            DelegateProfile(
                profile_id="default",
                workspace_ref=_prefixed_ref(workspace, _WORKSPACE_REF_PREFIX),
                agent_policy_ref=_prefixed_ref(agent, _POLICY_REF_PREFIX),
                model_policy_ref=_prefixed_ref(model, _POLICY_REF_PREFIX),
                effort_policy_ref=_prefixed_ref(effort, _POLICY_REF_PREFIX),
                run_limits_policy_ref=_prefixed_ref(limits, _POLICY_REF_PREFIX),
                summary="default",
            ),
        )
    )


def requested_configuration(config: Any, profile: DelegateProfile) -> tuple[str, str, str]:
    """The ``(agent, model, effort)`` triple this profile **requests**.

    Resolved from the config's own policy maps through the selected profile's
    refs, so a receipt states what Sachima asked for. It is never an effective
    readback: nothing here observes what a Run executed under.
    """

    try:
        agent = config.agent_by_policy_ref[profile.agent_policy_ref]
        model = config.model_by_policy_ref[profile.model_policy_ref]
        effort = config.effort_by_policy_ref[profile.effort_policy_ref]
    except (AttributeError, KeyError, TypeError):
        raise _invalid_policy() from None
    if type(agent) is not str or type(model) is not str or type(effort) is not str:
        raise _invalid_policy()
    return agent, model, effort


# --------------------------------------------------------------------------- #
# The one route decision, shared by every creation path
# --------------------------------------------------------------------------- #
def resolve_route(
    policy: DelegatePolicy,
    *,
    platform: str = "",
    selector_user_id: str | None = None,
    requested_profile_id: str | None = None,
    task_text: str = "",
    required_capabilities: Sequence[str] = (),
) -> RouteDecision:
    """Decide which profile serves one request — or refuse. Pure.

    ``selector_user_id`` is a **verified** occurrence identity (the selector
    parser already refused anything unverifiable) and ``requested_profile_id`` is
    a trusted control-service argument. Both are explicit statements, so both
    win or refuse; neither ever falls back to automatic routing.
    """

    if type(policy) is not DelegatePolicy:
        return RouteDecision(refusal=SACHIMA_DELEGATE_INVALID_POLICY)
    choices = policy.choices()
    task_bytes = len(task_text.encode("utf-8")) if type(task_text) is str else 0
    required = tuple(required_capabilities or ())

    if selector_user_id is not None:
        profile = policy.by_mention(platform, selector_user_id)
        if profile is None or not profile.enabled:
            return RouteDecision(
                refusal=SACHIMA_DELEGATE_UNKNOWN_SELECTOR, choices=choices
            )
        return _admit(profile, task_bytes=task_bytes, required=required, choices=choices)

    if requested_profile_id is not None:
        profile = policy.profile(requested_profile_id)
        if profile is None or not profile.enabled:
            return RouteDecision(
                refusal=SACHIMA_DELEGATE_UNKNOWN_PROFILE, choices=choices
            )
        return _admit(profile, task_bytes=task_bytes, required=required, choices=choices)

    candidates = [
        profile
        for profile in policy.profiles
        if profile.enabled
        and profile.auto_selectable
        and profile.accepts(task_bytes=task_bytes, required=required)
    ]
    if not candidates:
        return RouteDecision(refusal=SACHIMA_DELEGATE_NO_ROUTE, choices=choices)
    if len(candidates) == 1:
        return RouteDecision(profile=candidates[0], choices=choices)
    top = max(profile.priority for profile in candidates)
    leaders = [profile for profile in candidates if profile.priority == top]
    if len(leaders) != 1:
        # A tie is insufficient evidence, and guessing between two approved
        # AGENTs is exactly the failure this ordering exists to prevent.
        return RouteDecision(refusal=SACHIMA_DELEGATE_AMBIGUOUS_ROUTE, choices=choices)
    return RouteDecision(profile=leaders[0], choices=choices)


def _admit(
    profile: DelegateProfile,
    *,
    task_bytes: int,
    required: Sequence[str],
    choices: tuple[str, ...],
) -> RouteDecision:
    """An explicitly named profile still has to be able to take the task."""

    if task_bytes > profile.max_task_bytes:
        return RouteDecision(refusal=SACHIMA_DELEGATE_TASK_TOO_LARGE, choices=choices)
    if not all(tag in profile.capabilities for tag in required):
        return RouteDecision(refusal=SACHIMA_DELEGATE_NO_ROUTE, choices=choices)
    return RouteDecision(profile=profile, choices=choices)
