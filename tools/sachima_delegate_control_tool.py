"""Default-off internal tool surface over the Sachima delegate control service.

This is the **only** user-reachable path to an external AGENT, and it is
reached through conversation rather than through a command. Hermes understands
what the user asked for, picks or clarifies, and calls this tool with one
canonical ``agent_id``; creation plus ``status``, ``cancel``, ``continue``,
``recover``, and ``result`` are *actions of the one coordinator*, without a
slash command, an ARS operation, or a second lifecycle owner. Nothing here has
its own state machine.

The division of labour is the point:

* **Hermes owns understanding.** Which AGENT a sentence means, whether the
  candidate is unique, when to ask instead of guess, and what to make of "Tom
  is not an AGENT" all live in the conversation, upstream of here.
* **This surface owns the deterministic facts.** ``agents`` reports the live
  roster annotated with two independently owned facts — whether this host may
  run each AGENT, and which division/roles it holds — and, for an exact role,
  the single eligible candidate or a stable clarification code. It is
  read-only: a zero-or-several answer writes nothing.
* **This surface owns admission.** It resolves one id against the live
  roster — case-insensitively, otherwise exactly — and admits it only against
  ``live ARS roster ∩ execution preset``. There is no fuzzy match, no alias
  table, no candidate ranking, and no default AGENT: an id that does not
  admit is refused with a stable code before any task, payload, Session, or
  submit exists, and the canonical roster spelling is what gets stored.

Creation always names an ``agent_id``, including after a role lookup. That is
deliberate: a delegated Run should be attributable to an explicit choice in
the record, not to a query that happened to return one row.

Default-off behind two independent gates, mirroring the live-progress tool:

1. **Availability gate** — the tool's ``check_fn`` only passes when
   ``SACHIMA_LIVE_PROGRESS_DISPLAY_SURFACE`` is exactly ``hermes_internal``.
   The ``sachima_delegate_control`` toolset is additionally not part of the core
   tool list or any platform default toolset, so it never appears in an ordinary
   session unless a profile names the toolset *and* the env gate is on.
2. **Service gate** — the handler only consumes the host-bound coordinator. With
   none bound it fails closed with a stable code before touching any store,
   ledger, backend, or daemon.

Two boundaries are worth stating explicitly, because they are what make a
model-invoked control surface safe:

* **The caller's Session is trusted context, never an argument.** It comes from
  the Gateway's own ``HERMES_SESSION_ID`` (with a key lookup as the fallback for
  callers that only carry the key). A model-supplied session identifier is not
  accepted, so a model cannot act on a conversation it is not in. A *task* also
  belongs to a Session, and context compression forks a new physical one out
  from under a live conversation — so "is this task yours" is asked of
  ``gateway.session_continuity``, which admits this exact Session or a
  compression continuation of it proven hop by hop from persisted lineage.
  ``/new``, reset, ``/branch``, and subagent runs inherit nothing, and this
  surface holds no copy of that rule.
* **Task text never comes back.** Answers are refs, closed-vocabulary states,
  and stable codes. ``result`` is the one action that returns agent output, and
  it returns the durable result the user already received a bounded copy of.

Creation also states the two halves separately. ``task`` is the complete
instruction the AGENT executes; ``task_title`` is the one short line the status
card is displayed under. Both are required, because the alternative to a
supplied title is a clipped execution prompt — a sentence the user never wrote,
presented as the thing they asked for. The title is sealed with the Task: a
continuation adds a round, never a new headline.
"""

from __future__ import annotations

import os
from typing import Any

import logging

from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
SACHIMA_DELEGATE_CONTROL_DISABLED = "sachima_delegate_control_disabled"
SACHIMA_DELEGATE_CONTROL_UNBOUND = "sachima_delegate_control_unbound"
SACHIMA_DELEGATE_CONTROL_INVALID = "sachima_delegate_control_invalid"
SACHIMA_DELEGATE_CONTROL_FORBIDDEN = "sachima_delegate_control_forbidden"
SACHIMA_DELEGATE_CONTROL_NO_SESSION = "sachima_delegate_control_no_session"

SACHIMA_DELEGATE_CONTROL_STABLE_CODES = frozenset(
    {
        SACHIMA_DELEGATE_CONTROL_DISABLED,
        SACHIMA_DELEGATE_CONTROL_UNBOUND,
        SACHIMA_DELEGATE_CONTROL_INVALID,
        SACHIMA_DELEGATE_CONTROL_FORBIDDEN,
        SACHIMA_DELEGATE_CONTROL_NO_SESSION,
    }
)

DELEGATE_CONTROL_ENVELOPE_TYPE = "sachima_delegate_control.v1"

SACHIMA_LIVE_PROGRESS_SURFACE_ENV = "SACHIMA_LIVE_PROGRESS_DISPLAY_SURFACE"
#: Only the internal gateway surface. ``local_offline`` belongs to offline
#: harnesses; a control action that can cancel a Run is not one of those.
_APPROVED_CONTROL_SURFACES = frozenset({"hermes_internal"})

TOOL_NAME = "sachima_delegate_control"
TOOLSET_NAME = "sachima_delegate_control"

_ACTIONS = (
    "agents",
    "create",
    "status",
    "cancel",
    "continue",
    "recover",
    "result",
)

#: The one action that needs no task of its own, so it is also the one that
#: skips the "does this task belong to you" check below.
_TASKLESS_ACTIONS = frozenset({"agents", "create"})


def enabled_control_surface() -> str | None:
    """The activated surface token, or ``None`` when default-off."""

    raw = os.environ.get(SACHIMA_LIVE_PROGRESS_SURFACE_ENV)
    if type(raw) is not str:
        return None
    value = raw.strip()
    if value not in _APPROVED_CONTROL_SURFACES:
        return None
    return value


def check_delegate_control_available() -> bool:
    """``check_fn`` for the registry: schema hidden unless the env gate is on."""

    return enabled_control_surface() is not None


def _trusted_session() -> Any:
    """The caller's live conversation, from trusted Gateway context only.

    Never a tool argument. The Gateway sets both the id and the key, and the
    Session/Gateway authority in ``gateway.session_continuity`` resolves them —
    including the one legitimate disagreement, the window where context
    compression has already rotated the contextvar onto the continuation and the
    store still names the pre-compression parent. That window is admitted only
    on persisted, per-hop lineage proof; this surface holds no rule of its own.
    """

    from gateway.session_context import get_session_env
    from gateway.session_continuity import resolve_trusted_session

    store = _bound_session_store()
    if store is None:
        return None
    return resolve_trusted_session(
        store,
        session_id=(get_session_env("HERMES_SESSION_ID", "") or "").strip(),
        session_key=(get_session_env("HERMES_SESSION_KEY", "") or "").strip(),
    )


def _trusted_origin(trusted: Any) -> Any:
    """Rebuild a delegate origin from the persisted Session and turn context.

    The Session carried here is the one the conversation is *on* — after a
    compression split that is the continuation, so a task created now is
    attributed to the Session that actually holds the conversation rather than
    to the parent the store has not caught up with yet.
    """

    from gateway.sachima_delegate_state import DelegateOrigin
    from gateway.session_context import get_session_env

    entry = getattr(trusted, "entry", None)
    source = getattr(entry, "origin", None)
    platform_value = getattr(getattr(source, "platform", None), "value", None)
    if (
        source is None
        or type(platform_value) is not str
        or not getattr(source, "chat_id", None)
    ):
        return None
    message_id = (get_session_env("HERMES_SESSION_MESSAGE_ID", "") or "").strip()
    return DelegateOrigin(
        platform=platform_value,
        chat_id=str(source.chat_id),
        thread_id=(
            str(source.thread_id) if getattr(source, "thread_id", None) else None
        ),
        session_key=entry.session_key,
        session_id=trusted.session_id,
        reply_anchor=message_id or None,
    )


_session_store: Any = None


def bind_delegate_control_session_store(store: Any) -> None:
    """Bind the host ``SessionStore`` used for the key→id fallback."""

    global _session_store
    _session_store = store


def _bound_session_store() -> Any:
    return _session_store


def _refusal(admission: Any) -> dict:
    """One ineligibility answer: the stable code plus the two facts behind it.

    ``registered`` is reported separately so "this AGENT exists but this host
    cannot run it" stays distinguishable from "there is no such AGENT" —
    Hermes needs that difference to say something true. ``agent_id`` is the
    canonical roster spelling once the selection resolved, and otherwise the
    caller's own shape-valid text so Hermes can name what it could not find;
    a value that failed the shape check is never reflected back.
    """

    return {
        "refusal": admission.refusal,
        "agent_id": admission.agent_id,
        "registered": admission.registered,
    }


def _handle_delegate_control(args: dict, **kw) -> str:
    """Run one delegate control action for the caller's own Session.

    Fail-closed order: env gate → bound coordinator → trusted Session → the task
    belongs to that Session (except new creation) → for anything that would
    submit a Run, ``live roster ∩ execution preset`` → the coordinator's own
    state machine. Every failure returns a stable code only.
    """

    if enabled_control_surface() is None:
        return tool_error(SACHIMA_DELEGATE_CONTROL_DISABLED)

    from gateway.sachima_agent_execution_presets import (
        SACHIMA_AGENT_ROSTER_UNAVAILABLE,
    )
    from gateway.sachima_delegate import bound_delegate_coordinator

    coordinator = bound_delegate_coordinator()
    if coordinator is None:
        return tool_error(SACHIMA_DELEGATE_CONTROL_UNBOUND)
    if type(args) is not dict:
        return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)

    action = args.get("action")
    if type(action) is not str or action not in _ACTIONS:
        return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
    trusted = _trusted_session()
    if trusted is None:
        return tool_error(SACHIMA_DELEGATE_CONTROL_NO_SESSION)

    task_ref = args.get("task_ref")
    binding = None
    if action not in _TASKLESS_ACTIONS:
        if type(task_ref) is not str or not task_ref.strip():
            return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
        task_ref = task_ref.strip()
        try:
            binding = coordinator.state.read_task(task_ref)
        except Exception:
            return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
        if binding is None or not trusted.claims(binding.origin):
            # Unknown and not-yours answer the same way: a control surface that
            # distinguishes them is an enumeration oracle for other conversations.
            # "Yours" is the Session/Gateway authority's one rule: this exact
            # Session, or the compression continuation of it that the persisted
            # lineage proves. A branch, a subagent, and a ``/new`` all answer
            # here exactly as another conversation does.
            return tool_error(SACHIMA_DELEGATE_CONTROL_FORBIDDEN)

    agent_id = args.get("agent_id")
    if agent_id is not None and (type(agent_id) is not str or not agent_id):
        return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)

    try:
        if action == "agents":
            # Read-only discovery. It answers who is registered, who this host
            # may run, and who holds which role — and, for an exact role, the
            # one candidate or the question to ask. It writes nothing, so a
            # zero-or-several answer costs no durable state.
            try:
                view, selection = coordinator.agent_eligibility(
                    role=args.get("role"), division=args.get("division")
                )
            except Exception:
                logger.debug("delegate roster read failed", exc_info=True)
                payload = {"refusal": SACHIMA_AGENT_ROSTER_UNAVAILABLE}
            else:
                payload = {
                    "agents": [entry.as_dict() for entry in view],
                    "selection": (
                        None
                        if selection is None
                        else {
                            "agent_id": selection.agent_id,
                            "refusal": selection.refusal,
                            "candidates": list(selection.candidates),
                        }
                    ),
                }
        elif action == "create":
            from gateway.sachima_delegate_card import sanitize_card_line

            task_text = args.get("task")
            # The title is judged as the line it will actually render, using
            # the card layer's own sanitizer rather than a second rule that
            # could disagree with it. A value that survives only as control
            # characters is empty for display purposes, and calling it present
            # would submit a Run whose card then says nothing was provided.
            task_title = sanitize_card_line(args.get("task_title"))
            origin = _trusted_origin(trusted)
            if (
                type(task_text) is not str
                or not task_text.strip()
                or not task_title
                or agent_id is None
                or origin is None
            ):
                # Creation names its AGENT. There is no default to fall back
                # to, so an omitted id is invalid input rather than an
                # invitation to choose one. The displayed title is required for
                # the same reason: with none supplied the only alternatives are
                # a blank headline or a clipped execution prompt, and neither
                # is a sentence the user wrote.
                return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
            admission = coordinator.admit_agent(
                agent_id, task_text=task_text.strip()
            )
            if not admission.admitted:
                payload = _refusal(admission)
            else:
                payload = coordinator.run_on_lifecycle_loop(
                    lambda: coordinator.create(
                        task_text=task_text.strip(),
                        preset=admission.preset,
                        origin=origin,
                        # Sealed only when the validated role policy really
                        # assigns this role to this exact AGENT; otherwise the
                        # task carries none and the status card says so.
                        admitted_role=args.get("role"),
                        task_title=task_title,
                    )
                ).as_dict()
        elif action == "status":
            payload = coordinator.run_on_lifecycle_loop(
                lambda: coordinator.status(task_ref)
            ).as_dict()
        elif action == "cancel":
            payload = coordinator.run_on_lifecycle_loop(
                lambda: coordinator.cancel(task_ref)
            ).as_dict()
        elif action == "recover":
            payload = coordinator.run_on_lifecycle_loop(
                lambda: coordinator.recover(task_ref)
            ).as_dict()
        elif action == "continue":
            task_text = args.get("task")
            if type(task_text) is not str or not task_text.strip():
                return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
            # A continuation submits a Run, so it proves eligibility again —
            # for the task's own AGENT when the caller kept it, and for the
            # named one when the caller switched. An AGENT that has since left
            # the roster, or lost its preset, stops receiving Runs on a task
            # that was admitted under it earlier.
            admission = coordinator.admit_agent(
                binding.agent_id if agent_id is None else agent_id,
                task_text=task_text.strip(),
            )
            origin = _trusted_origin(trusted)
            if not admission.admitted:
                payload = _refusal(admission)
            elif origin is None:
                return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
            else:
                payload = coordinator.run_on_lifecycle_loop(
                    lambda: coordinator.continue_task(
                        task_ref,
                        task_text.strip(),
                        preset=admission.preset,
                        origin=origin,
                        admitted_role=args.get("role"),
                        # An AGENT switch links a new task, so the coordinator
                        # re-asks whether the caller is this task's conversation.
                        # It gets the same proven answer this surface used, not
                        # a second rule of its own.
                        continuity=trusted,
                    )
                ).as_dict()
        else:
            payload = coordinator.result(task_ref)
            if payload is None:
                return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
    except Exception:
        # One stable code only — never the raised text, which can carry private
        # config refs, chat ids, or remote message bodies.
        return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)

    return tool_result(
        {"type": DELEGATE_CONTROL_ENVELOPE_TYPE, "action": action, "result": payload}
    )


DELEGATE_CONTROL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "INTERNAL, default-off: discover which external AGENTs this host can "
        "run, then create or steer one delegated task in THIS conversation — "
        "agents (read-only: who is registered, who is runnable, who holds "
        "which role), create, status, cancel (the Run only), "
        "continue (a later Run in the same task and Session, or a linked new "
        "task when switching AGENT), recover (an uncertain submission), or "
        "result (the durable answer). Requires the explicit "
        f"{SACHIMA_LIVE_PROGRESS_SURFACE_ENV}=hermes_internal gate and a "
        "host-bound delegate coordinator; otherwise it fails closed with a "
        "stable code."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_ACTIONS),
                "description": "The control action to perform.",
            },
            "task_ref": {
                "type": "string",
                "description": "The delegated task ref (dtask_...) from the acceptance.",
            },
            "task": {
                "type": "string",
                "description": (
                    "For 'create' or 'continue': the complete task text the "
                    "AGENT executes. Write it in full — it is never shortened "
                    "for display."
                ),
            },
            "task_title": {
                "type": "string",
                "description": (
                    "Required for 'create': one short TODO-style sentence "
                    "naming what this task is, for the status card's 任务/Task "
                    "row only. Write the goal in the user's own terms, not a "
                    "clipped copy of 'task'. It is sealed with the task, so a "
                    "'continue' cannot change it and supplying one there does "
                    "nothing; switching AGENT carries this same title into the "
                    "linked task."
                ),
            },
            "role": {
                "type": "string",
                "description": (
                    "An exact configured role token (e.g. "
                    "'architecture_design'). Matching is exact — map the "
                    "user's words onto a role yourself. For 'agents', exactly "
                    "one eligible AGENT is returned as the selection; zero or "
                    "several come back as a stable code plus the candidates, "
                    "which is your cue to ask the user rather than pick. For "
                    "'create' or 'continue' it is optional and records which "
                    "role the AGENT was admitted under; a role the AGENT does "
                    "not actually hold is not sealed and changes nothing."
                ),
            },
            "division": {
                "type": "string",
                "description": (
                    "For 'agents': an exact configured division token, alone "
                    "or narrowing a role."
                ),
            },
            "agent_id": {
                "type": "string",
                "description": (
                    "The ARS agent id (e.g. 'codex'), matched exactly "
                    "against the live roster — letter case is forgiven, "
                    "nothing else is, and it is never a display name, "
                    "nickname, role word, or guess. "
                    "Required for 'create'. On 'continue' it is optional: "
                    "omitted or the same id continues this task, a different "
                    "id creates a linked new task under that AGENT. An id "
                    "that is not both registered with the daemon and covered "
                    "by an execution preset here is refused and nothing runs."
                ),
            },
        },
        "required": ["action"],
    },
}

registry.register(
    name=TOOL_NAME,
    toolset=TOOLSET_NAME,
    schema=DELEGATE_CONTROL_SCHEMA,
    handler=_handle_delegate_control,
    check_fn=check_delegate_control_available,
    emoji="🛰️",
)
