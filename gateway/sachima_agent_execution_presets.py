"""Sachima execution presets — which registered AGENT this host may run, and how.

Delegation is a conversation before it is an execution. Hermes reads that
conversation: it understands "let Codex review this", clarifies when the user
named something that is not an AGENT, and hands exactly one canonical
``agent_id`` down. This module owns everything after that hand-off, and it
owns no language at all.

A **preset** binds one exact canonical ``agent_id`` to the approved execution
configuration: the five ARS ref categories the spine already understands
(workspace, agent policy, model policy, effort policy, run-limits policy),
the permission set that configuration runs under, and a task-size bound. It
carries nothing else. In particular there is no mention mapping, no platform
identity, no alias table, no fuzzy matching, no priority, no
``auto_selectable``, no capability ranking, and no default preset for an
unknown AGENT to inherit — a preset is a *permission to execute*, never a way
to be chosen.

Eligibility is exactly one intersection::

    live ARS roster  ∩  valid execution preset

Both halves are required and neither substitutes for the other:

* a registered AGENT with no preset is reported **registered and
  unavailable**. It never borrows another preset's workspace, model, effort,
  limits, or permissions, which is what keeps an AGENT that already runs
  under its own production configuration from being silently rewritten here;
* a preset whose ``agent_id`` is absent from the live roster is
  **unavailable**. Nothing reads ``agents.toml`` or any other registry file
  to argue with the daemon about what it loaded — the daemon's own
  ``agent_list`` reply is the fact.

Two lookups, deliberately different, because they answer different questions.
A **preset document** is configuration: its ids are canonical and lowercase,
and ``Codex`` in one is simply wrong. A **selection** is a person naming an
AGENT through Hermes, and a person writes ``Codex``; that resolves
case-insensitively but otherwise exactly against the live roster, and the
roster's own spelling is what gets admitted, submitted and stored. Case is the
only thing forgiven — ``codex ``, ``cod`` and ``code x`` resolve to nothing.
Anything past that is a guess, and guessing belongs to Hermes, upstream.

On permissions: the engineering baseline is ``read + search + execute``, and
an implementation preset adds ``write``. Delete/move, credentials, network
side effects, service lifecycle, and other privileged effects are not preset
defaults — they stay task-specific and separately approved. A preset's
``permissions`` is a **declaration checked against the operator's approved
grant**, never a widening of it and never an OS-level confinement: ``execute``
is a cooperative capability, so what actually bounds a Run is the task
contract plus its pre/post workspace guards. A review-only preset is
therefore expressed as "no retained mutation" (no ``write``), not as
"no commands".

Pure local/offline: this module opens no socket, starts nothing, reaches no
daemon, and imports no ``agent_run_supervisor``. :func:`admit_agent_execution`
is a pure decision over one catalog, one id, and one already-read roster; the
single live read that produces that roster belongs to the ``arsd`` backend.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

__all__ = [
    "AGENT_EXECUTION_PRESETS_TYPE",
    "DEFAULT_MAX_TASK_BYTES",
    "ENGINEERING_BASELINE_PERMISSIONS",
    "IMPLEMENTATION_PERMISSIONS",
    "PRESET_PERMISSIONS",
    "SACHIMA_AGENT_ID_PATTERN",
    "SACHIMA_SELECTION_ID_PATTERN",
    "SACHIMA_AGENT_INVALID_ID",
    "SACHIMA_AGENT_INVALID_PRESETS",
    "SACHIMA_AGENT_NO_PRESET",
    "SACHIMA_AGENT_NOT_REGISTERED",
    "SACHIMA_AGENT_PRESET_STABLE_CODES",
    "SACHIMA_AGENT_ROSTER_UNAVAILABLE",
    "SACHIMA_AGENT_TASK_TOO_LARGE",
    "AgentAdmission",
    "AgentExecutionPreset",
    "AgentExecutionPresets",
    "PresetError",
    "admit_agent_execution",
    "build_agent_execution_presets",
    "canonical_agent_id",
    "empty_agent_execution_presets",
    "load_agent_execution_presets",
    "requested_configuration",
    "resolve_selected_agent_id",
    "selection_shaped_agent_id",
]

AGENT_EXECUTION_PRESETS_TYPE = "sachima.gateway.agent_execution_presets.v1"

#: The default per-preset task-size bound, in UTF-8 bytes, and its ceiling.
#: It is deliberately below the ARS prompt bound so a task refused here is
#: refused *before* a Session exists, not after a submit was spent learning it.
DEFAULT_MAX_TASK_BYTES = 32_768

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
SACHIMA_AGENT_INVALID_PRESETS = "sachima_agent_invalid_presets"
SACHIMA_AGENT_INVALID_ID = "sachima_agent_invalid_id"
SACHIMA_AGENT_NOT_REGISTERED = "sachima_agent_not_registered"
SACHIMA_AGENT_NO_PRESET = "sachima_agent_no_preset"
SACHIMA_AGENT_ROSTER_UNAVAILABLE = "sachima_agent_roster_unavailable"
SACHIMA_AGENT_TASK_TOO_LARGE = "sachima_agent_task_too_large"

SACHIMA_AGENT_PRESET_STABLE_CODES = frozenset(
    {
        SACHIMA_AGENT_INVALID_PRESETS,
        SACHIMA_AGENT_INVALID_ID,
        SACHIMA_AGENT_NOT_REGISTERED,
        SACHIMA_AGENT_NO_PRESET,
        SACHIMA_AGENT_ROSTER_UNAVAILABLE,
        SACHIMA_AGENT_TASK_TOO_LARGE,
    }
)

#: The canonical ``agent_id`` grammar, mirrored from the ARS contract module's
#: own mirror of ``native_acp.agent_registration.AGENT_ID_RE``. Mirrored
#: rather than imported so this module stays importable with no spine module
#: behind it; the drift-lock test asserts the two are equal.
SACHIMA_AGENT_ID_PATTERN = r"[a-z0-9][a-z0-9._-]{0,63}"
_AGENT_ID_RE = re.compile(SACHIMA_AGENT_ID_PATTERN)

#: The same grammar with the case restriction lifted — and *only* that. It
#: is the shape a selection may arrive in, never the shape an id is stored
#: in: :func:`resolve_selected_agent_id` maps it onto the roster's own
#: canonical spelling before anything downstream sees it.
SACHIMA_SELECTION_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
_SELECTION_ID_RE = re.compile(SACHIMA_SELECTION_ID_PATTERN)

#: The closed permission vocabulary a preset may declare. Delete/move,
#: credentials, network side effects, and service lifecycle are deliberately
#: absent: they are task-specific grants, not preset defaults.
PRESET_PERMISSIONS = frozenset({"read", "search", "execute", "write"})

#: Every preset carries at least the engineering baseline. ``execute`` is part
#: of it because a development AGENT that cannot build, test, or lint is not
#: doing development — read-only means *no retained mutation*, proven by the
#: task's pre/post workspace guards, not "no commands".
ENGINEERING_BASELINE_PERMISSIONS = ("execute", "read", "search")

#: An implementation preset adds workspace authorship on top of the baseline.
IMPLEMENTATION_PERMISSIONS = ("execute", "read", "search", "write")

_WORKSPACE_REF_PREFIX = "ws_"
_POLICY_REF_PREFIX = "policy_"
_SAFE_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_PRESETS = 64

#: The preset document's exact key set. Unknown keys fail closed rather than
#: being ignored: a typo, or a retired routing field copied over from the old
#: policy document, must be refused rather than silently accepted and dropped.
_PRESET_KEYS = frozenset(
    {
        "agent_id",
        "workspace_ref",
        "agent_policy_ref",
        "model_policy_ref",
        "effort_policy_ref",
        "run_limits_policy_ref",
        "permissions",
        "max_task_bytes",
    }
)
_REQUIRED_PRESET_KEYS = _PRESET_KEYS - {"max_task_bytes"}
_DOCUMENT_KEYS = frozenset({"type", "presets"})


class PresetError(ValueError):
    """A preset failure whose message IS the stable code — never the material."""


def _invalid() -> "PresetError":
    return PresetError(SACHIMA_AGENT_INVALID_PRESETS)


def canonical_agent_id(value: Any) -> str | None:
    """``value`` if it is exactly a canonical ``agent_id``, else ``None``.

    No trimming, no case folding, no repair. A value that is not an agent id
    is not a misspelled one — deciding what the user meant is Hermes's job,
    upstream of this boundary.
    """

    if type(value) is not str or _AGENT_ID_RE.fullmatch(value) is None:
        return None
    return value


def _preset_agent_id(value: Any) -> str:
    agent_id = canonical_agent_id(value)
    if agent_id is None:
        raise _invalid()
    return agent_id


def selection_shaped_agent_id(value: Any) -> str | None:
    """``value`` if it is an agent id *as a person would type one*, else ``None``.

    The canonical grammar with the case restriction lifted, and nothing else
    lifted: no trimming, no interior spaces, no wildcards, no length relief.
    It says only "this could be an agent id"; whether it *is* one is
    :func:`resolve_selected_agent_id`'s question, asked against the live
    roster.
    """

    if type(value) is not str or _SELECTION_ID_RE.fullmatch(value) is None:
        return None
    return value


def resolve_selected_agent_id(
    value: Any, registered_agent_ids: Sequence[str]
) -> str | None:
    """The canonical roster spelling one selection names, or ``None``.

    Two different questions were being answered by one grammar. A preset
    document is configuration: its ids are canonical, lowercase, and simply
    wrong when they are not. A *selection* is a person naming an AGENT through
    Hermes, and a person writes ``Codex``. Case is the only difference this
    forgives — matching is otherwise exact, so ``cod``, ``codexx``, ``codex ``
    and ``code x`` all resolve to nothing.

    The answer is always the roster's own spelling, never the caller's, so the
    id that is admitted, submitted and stored is the canonical one.

    A roster holding two ids that differ only by case fails closed: neither
    can be "the one they meant". The contract validator already refuses such a
    roster, which is exactly why this is a backstop rather than a policy.
    """

    selected = selection_shaped_agent_id(value)
    if selected is None:
        return None
    folded = selected.casefold()
    matches = [
        agent_id
        for agent_id in registered_agent_ids
        if type(agent_id) is str and agent_id.casefold() == folded
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _prefixed_ref(value: Any, prefix: str) -> str:
    if type(value) is not str or _SAFE_REF_RE.fullmatch(value) is None:
        raise _invalid()
    if not value.startswith(prefix):
        raise _invalid()
    return value


def _sealed_grant_for(config: Any, agent_policy_ref: str) -> tuple[str, ...]:
    """The exact capability set this policy's Runs are submitted under.

    Read from the ARS config's own ``grant_by_policy_ref``, because that is
    what the submit payload seals and what the daemon's permission bridge
    freezes. A policy with no entry there has no sealed grant, and a preset
    over it would produce Runs carrying the config-wide capabilities instead
    of the ones its document declares — so it fails closed rather than
    over-granting quietly.
    """

    mapping = getattr(config, "grant_by_policy_ref", None)
    if not isinstance(mapping, Mapping):
        raise _invalid()
    sealed = mapping.get(agent_policy_ref)
    if not isinstance(sealed, (tuple, list)) or not sealed:
        raise _invalid()
    return tuple(sorted(str(token) for token in sealed))


def _permissions(value: Any, *, granted: Any, sealed: tuple[str, ...]) -> tuple[str, ...]:
    if type(value) is not list or not value:
        raise _invalid()
    seen: set[str] = set()
    for token in value:
        if type(token) is not str or token not in PRESET_PERMISSIONS:
            raise _invalid()
        if token in seen:
            raise _invalid()
        seen.add(token)
    if not seen.issuperset(ENGINEERING_BASELINE_PERMISSIONS):
        raise _invalid()
    # A preset chooses among what the operator already approved config-wide;
    # it can never widen it.
    approved = granted if isinstance(granted, (tuple, list)) else ()
    if not seen.issubset({token for token in approved if type(token) is str}):
        raise _invalid()
    # The declaration and the sealed grant are the same fact stated twice.
    # A preset that disagrees with the grant its Runs would carry is a preset
    # whose review said one thing and whose execution does another.
    if tuple(sorted(seen)) != sealed:
        raise _invalid()
    return tuple(sorted(seen))


def _max_task_bytes(value: Any) -> int:
    if value is None:
        return DEFAULT_MAX_TASK_BYTES
    if isinstance(value, bool) or type(value) is not int:
        raise _invalid()
    if value < 1 or value > DEFAULT_MAX_TASK_BYTES:
        raise _invalid()
    return value


@dataclass(frozen=True)
class AgentExecutionPreset:
    """One canonical AGENT this host may execute, and the terms it runs under."""

    agent_id: str
    workspace_ref: str
    agent_policy_ref: str
    model_policy_ref: str
    effort_policy_ref: str
    run_limits_policy_ref: str
    permissions: tuple[str, ...]
    max_task_bytes: int = DEFAULT_MAX_TASK_BYTES

    @property
    def launch_refs(self) -> tuple[str, ...]:
        """The distinct refs this preset's sessions are admitted under.

        First-seen order with duplicates collapsed: the backend matches the
        ref *set* against each of the five config maps and demands exactly one
        match per map, so one ref legitimately serving several categories must
        appear once, not five times.
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

    @property
    def writes_workspace(self) -> bool:
        """True for an implementation preset, false for a review-only one."""

        return "write" in self.permissions

    def accepts(self, task_bytes: int) -> bool:
        return task_bytes <= self.max_task_bytes


@dataclass(frozen=True)
class AgentExecutionPresets:
    """The validated preset catalog, and the one lookup admission needs."""

    presets: tuple[AgentExecutionPreset, ...] = ()

    def preset(self, agent_id: Any) -> AgentExecutionPreset | None:
        """The preset for this exact canonical id, or ``None``.

        Exact identity only. There is no case-folded tier, no trimming tier,
        and no default entry, so an id nobody wrote a preset for stays without
        one instead of being resolved by resemblance or by inheritance.
        """

        if type(agent_id) is not str:
            return None
        for preset in self.presets:
            if preset.agent_id == agent_id:
                return preset
        return None

    def agent_ids(self) -> tuple[str, ...]:
        return tuple(preset.agent_id for preset in self.presets)


def empty_agent_execution_presets() -> AgentExecutionPresets:
    """The catalog of a host that configured none: nothing is eligible.

    This is an answer, not a fallback. Synthesizing a single preset from
    whatever the ARS config happens to offer is precisely the "inherit the
    default configuration" behavior the intersection exists to remove.
    """

    return AgentExecutionPresets()


# --------------------------------------------------------------------------- #
# Preset documents
# --------------------------------------------------------------------------- #
def _parse_preset(entry: Any, config: Any) -> AgentExecutionPreset:
    if type(entry) is not dict:
        raise _invalid()
    keys = set(entry)
    if not _REQUIRED_PRESET_KEYS <= keys <= _PRESET_KEYS:
        raise _invalid()
    agent_policy_ref = _prefixed_ref(
        entry.get("agent_policy_ref"), _POLICY_REF_PREFIX
    )
    preset = AgentExecutionPreset(
        agent_id=_preset_agent_id(entry.get("agent_id")),
        workspace_ref=_prefixed_ref(entry.get("workspace_ref"), _WORKSPACE_REF_PREFIX),
        agent_policy_ref=agent_policy_ref,
        model_policy_ref=_prefixed_ref(
            entry.get("model_policy_ref"), _POLICY_REF_PREFIX
        ),
        effort_policy_ref=_prefixed_ref(
            entry.get("effort_policy_ref"), _POLICY_REF_PREFIX
        ),
        run_limits_policy_ref=_prefixed_ref(
            entry.get("run_limits_policy_ref"), _POLICY_REF_PREFIX
        ),
        permissions=_permissions(
            entry.get("permissions"),
            granted=getattr(config, "grant_capabilities", None),
            sealed=_sealed_grant_for(config, agent_policy_ref),
        ),
        max_task_bytes=_max_task_bytes(entry.get("max_task_bytes")),
    )
    _require_refs_resolve(preset, config)
    _require_agent_policy_names_the_agent(preset, config)
    return preset


def _require_refs_resolve(preset: AgentExecutionPreset, config: Any) -> None:
    """Every ref must be one the operator already approved in the ARS config."""

    for ref, mapping in (
        (preset.workspace_ref, getattr(config, "workspace_by_ref", None)),
        (preset.agent_policy_ref, getattr(config, "agent_by_policy_ref", None)),
        (preset.model_policy_ref, getattr(config, "model_by_policy_ref", None)),
        (preset.effort_policy_ref, getattr(config, "effort_by_policy_ref", None)),
        (
            preset.run_limits_policy_ref,
            getattr(config, "run_limits_by_policy_ref", None),
        ),
    ):
        if not isinstance(mapping, Mapping) or ref not in mapping:
            raise _invalid()


def _require_agent_policy_names_the_agent(
    preset: AgentExecutionPreset, config: Any
) -> None:
    """The preset's id and the AGENT its submit would run must be the same one.

    ``agent_id`` is what the roster reports and what the user and Hermes
    talk about; the AGENT a Run actually executes under comes from
    ``agent_by_policy_ref``. A preset where those disagree would name one
    AGENT and run another — a mismatch no downstream check could catch,
    because both halves are individually valid.
    """

    mapping = getattr(config, "agent_by_policy_ref", None)
    if not isinstance(mapping, Mapping):
        raise _invalid()
    if mapping.get(preset.agent_policy_ref) != preset.agent_id:
        raise _invalid()


def build_agent_execution_presets(
    document: Any, config: Any
) -> AgentExecutionPresets:
    """Validate one preset document against the ARS config, or fail closed."""

    if type(document) is not dict or set(document) != _DOCUMENT_KEYS:
        raise _invalid()
    if document["type"] != AGENT_EXECUTION_PRESETS_TYPE:
        raise _invalid()
    entries = document["presets"]
    if type(entries) is not list or not entries or len(entries) > _MAX_PRESETS:
        raise _invalid()

    presets: list[AgentExecutionPreset] = []
    seen: set[str] = set()
    for entry in entries:
        preset = _parse_preset(entry, config)
        # One canonical id must select at most one preset, or "eligibility is
        # exactly the intersection" would be ambiguous by construction.
        if preset.agent_id in seen:
            raise _invalid()
        seen.add(preset.agent_id)
        presets.append(preset)
    return AgentExecutionPresets(presets=tuple(presets))


def load_agent_execution_presets(
    presets_file: Any, config: Any
) -> AgentExecutionPresets:
    """Read the private preset file and validate it. Never echoes the file."""

    if type(presets_file) is not str or not presets_file.strip():
        raise _invalid()
    try:
        with open(presets_file.strip(), encoding="utf-8") as handle:
            document = json.load(handle)
    except PresetError:
        raise
    except Exception:
        raise _invalid() from None
    return build_agent_execution_presets(document, config)


def requested_configuration(
    config: Any, preset: AgentExecutionPreset
) -> tuple[str, str, str]:
    """The ``(agent, model, effort)`` triple this preset **requests**.

    Resolved from the config's own policy maps through the preset's refs, so
    a receipt states what Sachima asked for. It is never an effective
    readback: nothing here observes what a Run executed under.
    """

    try:
        agent = config.agent_by_policy_ref[preset.agent_policy_ref]
        model = config.model_by_policy_ref[preset.model_policy_ref]
        effort = config.effort_by_policy_ref[preset.effort_policy_ref]
    except (AttributeError, KeyError, TypeError):
        raise _invalid() from None
    if type(agent) is not str or type(model) is not str or type(effort) is not str:
        raise _invalid()
    return agent, model, effort


# --------------------------------------------------------------------------- #
# Admission — the one intersection, as a pure decision
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgentAdmission:
    """One eligibility answer: a preset, or a refusal that says which half failed.

    ``registered`` is reported separately from the refusal on purpose. "This
    AGENT exists but this host cannot run it" and "there is no such AGENT" are
    different facts, and Hermes needs the difference to say something true to
    the user.

    ``agent_id`` is the **roster's** canonical spelling once the selection
    resolved, so what is admitted, submitted and stored is always canonical.
    When nothing resolved it is the caller's own shape-valid text, so Hermes
    can name the AGENT it could not find; a value that failed the shape check
    is never carried back out at all.
    """

    preset: AgentExecutionPreset | None = None
    refusal: str | None = None
    agent_id: str | None = None
    registered: bool = False

    @property
    def admitted(self) -> bool:
        return self.preset is not None


def admit_agent_execution(
    presets: Any,
    *,
    agent_id: Any,
    registered_agent_ids: Sequence[str],
    task_text: str = "",
) -> AgentAdmission:
    """Decide whether one canonical ``agent_id`` may execute here. Pure.

    ``registered_agent_ids`` is the live roster as the contract validator
    returned it — a tuple of canonical ids. Anything else is treated as no
    roster at all rather than trusted, so an unvalidated sequence produces a
    refusal instead of an admission built on unchecked material.

    Order is the contract: shape, then registration, then preset, then the
    task bound. Registration is asked first because "we could not find that
    AGENT" is the honest answer to a name the daemon never loaded, whether or
    not this host happens to hold a preset for it.

    Resolution against the roster is case-insensitive **exact**
    (:func:`resolve_selected_agent_id`), because the caller upstream is a
    person writing ``Codex``. Everything from here on uses the roster's own
    canonical spelling.
    """

    if type(presets) is not AgentExecutionPresets:
        return AgentAdmission(refusal=SACHIMA_AGENT_INVALID_PRESETS)

    selected = selection_shaped_agent_id(agent_id)
    if selected is None:
        return AgentAdmission(refusal=SACHIMA_AGENT_INVALID_ID)

    roster = (
        registered_agent_ids
        if type(registered_agent_ids) is tuple
        and all(canonical_agent_id(item) is not None for item in registered_agent_ids)
        else ()
    )
    canonical = resolve_selected_agent_id(selected, roster)
    if canonical is None:
        return AgentAdmission(refusal=SACHIMA_AGENT_NOT_REGISTERED, agent_id=selected)

    preset = presets.preset(canonical)
    if preset is None:
        return AgentAdmission(
            refusal=SACHIMA_AGENT_NO_PRESET, agent_id=canonical, registered=True
        )

    task_bytes = len(task_text.encode("utf-8")) if type(task_text) is str else 0
    if not preset.accepts(task_bytes):
        return AgentAdmission(
            refusal=SACHIMA_AGENT_TASK_TOO_LARGE, agent_id=canonical, registered=True
        )
    return AgentAdmission(preset=preset, agent_id=canonical, registered=True)
