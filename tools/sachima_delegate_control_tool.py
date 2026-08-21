"""Default-off internal tool surface over the Sachima delegate control service.

This is the natural-language half of ``/delegate``: creation plus ``status``,
``cancel``, ``continue``, ``recover``, and ``result`` as *actions of the one
coordinator*, reachable from the tool system without adding a slash command,
an ARS operation, or a second lifecycle owner. Creation uses the same routing
decision as the slash path; nothing here has its own state machine.

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
  accepted, so a model cannot act on a conversation it is not in.
* **Task text never comes back.** Answers are refs, closed-vocabulary states,
  and stable codes. ``result`` is the one action that returns agent output, and
  it returns the durable result the user already received a bounded copy of.
"""

from __future__ import annotations

import os
from typing import Any

from tools.registry import registry, tool_error, tool_result

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

_ACTIONS = ("create", "status", "cancel", "continue", "recover", "result")


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


def _trusted_session_entry() -> Any:
    """The caller's persisted Session, from trusted Gateway context only.

    Never a tool argument. The Gateway sets both the id and the key; the key
    lookup is the fallback for a caller that only ever had one, and it goes
    through the store rather than being reconstructed.
    """

    from gateway.session_context import get_session_env

    store = _bound_session_store()
    if store is None:
        return None
    session_id = (get_session_env("HERMES_SESSION_ID", "") or "").strip()
    session_key = (get_session_env("HERMES_SESSION_KEY", "") or "").strip()
    try:
        entry = store.lookup_by_session_id(session_id) if session_id else None
        if entry is None and session_key:
            entry = store.lookup_by_session_key(session_key)
    except Exception:
        return None
    if entry is None:
        return None
    if session_id and entry.session_id != session_id:
        return None
    if session_key and entry.session_key != session_key:
        return None
    return entry


def _trusted_origin(session_entry: Any) -> Any:
    """Rebuild a delegate origin from the persisted Session and turn context."""

    from gateway.sachima_delegate_state import DelegateOrigin
    from gateway.session_context import get_session_env

    source = getattr(session_entry, "origin", None)
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
        session_key=session_entry.session_key,
        session_id=session_entry.session_id,
        reply_anchor=message_id or None,
    )


_session_store: Any = None


def bind_delegate_control_session_store(store: Any) -> None:
    """Bind the host ``SessionStore`` used for the key→id fallback."""

    global _session_store
    _session_store = store


def _bound_session_store() -> Any:
    return _session_store


def _handle_delegate_control(args: dict, **kw) -> str:
    """Run one delegate control action for the caller's own Session.

    Fail-closed order: env gate → bound coordinator → trusted Session → the task
    belongs to that Session (except new creation) → the coordinator's own state
    machine. Every failure returns a stable code only.
    """

    if enabled_control_surface() is None:
        return tool_error(SACHIMA_DELEGATE_CONTROL_DISABLED)

    from gateway.sachima_delegate import bound_delegate_coordinator

    coordinator = bound_delegate_coordinator()
    if coordinator is None:
        return tool_error(SACHIMA_DELEGATE_CONTROL_UNBOUND)
    if type(args) is not dict:
        return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)

    action = args.get("action")
    if type(action) is not str or action not in _ACTIONS:
        return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
    session_entry = _trusted_session_entry()
    if session_entry is None:
        return tool_error(SACHIMA_DELEGATE_CONTROL_NO_SESSION)

    task_ref = args.get("task_ref")
    binding = None
    if action != "create":
        if type(task_ref) is not str or not task_ref.strip():
            return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
        task_ref = task_ref.strip()
        try:
            binding = coordinator.state.read_task(task_ref)
        except Exception:
            return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
        if binding is None or binding.origin.session_id != session_entry.session_id:
            # Unknown and not-yours answer the same way: a control surface that
            # distinguishes them is an enumeration oracle for other conversations.
            return tool_error(SACHIMA_DELEGATE_CONTROL_FORBIDDEN)

    requested_profile_id = args.get("requested_profile_id")
    if requested_profile_id is not None:
        if type(requested_profile_id) is not str or not requested_profile_id.strip():
            return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
        requested_profile_id = requested_profile_id.strip()

    try:
        if action == "create":
            from gateway.sachima_delegate_policy import resolve_route

            task_text = args.get("task")
            origin = _trusted_origin(session_entry)
            if (
                type(task_text) is not str
                or not task_text.strip()
                or origin is None
            ):
                return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
            decision = resolve_route(
                coordinator.policy,
                platform=origin.platform,
                requested_profile_id=requested_profile_id,
                task_text=task_text.strip(),
            )
            if not decision.routed:
                payload = {
                    "refusal": decision.refusal,
                    "choices": list(decision.choices),
                }
            else:
                payload = coordinator.run_on_lifecycle_loop(
                    lambda: coordinator.create(
                        task_text=task_text.strip(),
                        profile=decision.profile,
                        origin=origin,
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
            if requested_profile_id is None:
                payload = coordinator.run_on_lifecycle_loop(
                    lambda: coordinator.continue_task(task_ref, task_text.strip())
                ).as_dict()
            else:
                from gateway.sachima_delegate_policy import resolve_route

                decision = resolve_route(
                    coordinator.policy,
                    platform=binding.origin.platform,
                    requested_profile_id=requested_profile_id,
                    task_text=task_text.strip(),
                )
                origin = _trusted_origin(session_entry)
                if not decision.routed:
                    payload = {
                        "refusal": decision.refusal,
                        "choices": list(decision.choices),
                    }
                elif origin is None:
                    return tool_error(SACHIMA_DELEGATE_CONTROL_INVALID)
                else:
                    payload = coordinator.run_on_lifecycle_loop(
                        lambda: coordinator.continue_task(
                            task_ref,
                            task_text.strip(),
                            profile=decision.profile,
                            origin=origin,
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
        "INTERNAL, default-off: inspect or steer one delegated external-AGENT "
        "task in THIS conversation — create, status, cancel (the Run only), "
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
                "description": "For 'create' or 'continue': the task text.",
            },
            "requested_profile_id": {
                "type": "string",
                "description": (
                    "Optional approved delegate profile. On continuation, a "
                    "different profile creates a linked new task."
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
