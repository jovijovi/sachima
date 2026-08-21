"""P3 neutral, validated supervisor turn backend contract.

This module is the ARS 0.7.6 Socket API v3 integration plan's P3 slice
(``docs/plans/2026-08-17-ars-0.7.6-socket-api-v3-integration-plan.md`` §9): one
Sachima-owned turn contract that replaces both concrete-backend couplings — the
turn dispatcher's and the execution binding's — and that structurally cannot
carry a library- or daemon-private turn directory.

Boundaries:

* **Five safe fields, no path, no raw id.** :class:`SupervisorTurnResult`
  carries ``run_ref`` (a Sachima-derived safe handle, never the raw run/turn
  id), the ``source_kind`` tag, the safe ``source_ref``, the neutral
  ``supervisor_status``, and the foreign ``foreign_cursor``. Daemon-private
  storage layout is not caller contract: ``arsd`` owns its own run directories
  and Sachima must not read, name, or model them (Spec §8.2).
* **The private locator rides on the handoff only.**
  :class:`DispatchedSupervisorTurn` pairs the safe result with the private
  locator (an artifact directory under ``artifact_file``, a raw ``run_id``
  under ``arsd_run``), opts out of ``repr``, and deliberately exposes no
  ``as_dict``/serialize surface — mirroring the in-tree
  ``ResolvedLiveProgressSource`` idiom for "safe object + private sibling".
* **Exact-type factory allowlist.** :func:`validate_supervisor_turn_backend`
  admits only the concrete types a Sachima factory composes. A protocol-shaped
  duck type satisfies :class:`SupervisorTurnBackend` structurally and is still
  refused, and so is a subclass of an allowlisted type: a production
  composition root does not accept arbitrary objects (Spec §8.1).
* **One closed status vocabulary.** :data:`SUPERVISOR_TURN_STATUSES` is the
  transport-neutral set (Spec §8.3). A backend's own vocabulary is collapsed
  into it before it reaches a caller; nothing outside the set is published.
* **``dispatch_ref`` and ``payload_ref`` are both mandatory.** ``dispatch_ref``
  is the durable Run/Session binding key and ``payload_ref`` is the prompt's
  claim-check handle (Spec §8.1). They were optional only while the retired
  ``library`` backend — which predates the ledger and had neither — still
  implemented this protocol. A dispatch that cannot name itself cannot be
  bound, and one that cannot name its prompt cannot be recovered, so a caller
  supplies both or does not dispatch. Where a caller holds only one ref, the
  same ref serves as both.
* **One task operation critical section, published on the contract.**
  :class:`TaskOperationLocks` hands out one reentrant lock per task, and every
  layer that acts on that task takes *that* lock: the backend's admission and
  cancel, and the composition root's dispatch, recovery, and rehydration —
  continuously, from precondition through durable acceptance to canonical
  publication. Two layers with two lock maps leave a seam between "the daemon
  accepted" and "Sachima said so", which is exactly where a concurrent cancel
  lands.

  So the provider is not something a caller passes to both and hopes it
  matched: a backend **publishes** its own on
  :attr:`SupervisorTurnBackend.task_locks`, and a composition root derives it
  from there. Sharing it stops being a convention a future caller can get wrong
  once and becomes an invariant the graph enforces. The lock is reentrant so an
  inner layer re-enters the section an outer one already holds — but reentrant
  means thread-affine, so the section is never held across a thread hand-off.
* **Recovery and rehydration are on the contract, not on a concrete type.**
  :meth:`SupervisorTurnBackend.recover_uncertain_submission` is the explicit,
  never-automatic entry point for an uncertain submit, and
  :meth:`SupervisorTurnBackend.latest_accepted_turn` is the durable handoff a
  restart rebinds a read-model source from. Both return the same
  :class:`DispatchedSupervisorTurn` an ordinary acceptance does, so a
  composition root publishes all three through one code path.

Pure local/offline Python: importing this module starts no process, socket,
daemon, Gateway, or Temporal surface, performs no ``agent_run_supervisor``
import (the allowlist resolves its factories lazily), and enables nothing.
Forbidden terms in this prose are no-leak boundary canaries only, never
behavior.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, NoReturn, Protocol, runtime_checkable

from .events import SpineError, _safe_id, scan_for_leak

__all__ = [
    "RUNTIME_INVALID_SUPERVISOR_TURN",
    "SOURCE_KIND_ARSD_RUN",
    "SOURCE_KIND_ARTIFACT_FILE",
    "SUPERVISOR_SOURCE_KINDS",
    "SUPERVISOR_TURN_STABLE_CODES",
    "SUPERVISOR_TURN_STATUSES",
    "DispatchedSupervisorTurn",
    "SupervisorTurnBackend",
    "SupervisorTurnResult",
    "TaskOperationLocks",
    "derive_turn_ref",
    "serialize_supervisor_turn_result",
    "validate_supervisor_turn_backend",
    "validate_supervisor_turn_result",
]

# --------------------------------------------------------------------------- #
# Stable code (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_SUPERVISOR_TURN = "runtime_invalid_supervisor_turn"
SUPERVISOR_TURN_STABLE_CODES = frozenset({RUNTIME_INVALID_SUPERVISOR_TURN})

# --------------------------------------------------------------------------- #
# Closed vocabularies
# --------------------------------------------------------------------------- #
#: The tagged read-model source kinds (Spec §8.4). ``artifact_file`` reads a
#: private artifact directory; ``arsd_run`` reads a private ``run_id`` through
#: the socket. Nothing else is a source.
SOURCE_KIND_ARTIFACT_FILE = "artifact_file"
SOURCE_KIND_ARSD_RUN = "arsd_run"
SUPERVISOR_SOURCE_KINDS = frozenset({SOURCE_KIND_ARTIFACT_FILE, SOURCE_KIND_ARSD_RUN})

#: The transport-neutral turn vocabulary (Spec §8.3). ``accepted`` is a durable
#: submit acknowledgement, not a terminal: terminal truth arrives later through
#: status observation. These tokens are deliberately disjoint from Sachima's
#: canonical ``STATUS_VALUES`` — none of them is ever appended as a status.
SUPERVISOR_TURN_STATUSES = frozenset(
    {"accepted", "completed", "failed", "cancelled", "timed_out", "unknown"}
)

#: Upper bound for the foreign read-model cursor (matches the projection).
_MAX_FOREIGN_CURSOR = 1_000_000_000

_TURN_REF_DIGEST_CHARS = 8


def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_SUPERVISOR_TURN)


# --------------------------------------------------------------------------- #
# Field-level sanitizers (each fails closed with the module's invalid code)
# --------------------------------------------------------------------------- #
def _safe_turn_ref(value: Any) -> str:
    """A SAFE public handle (``turn_1_ab12cd34`` / ``run_ab12cd34``), never a path."""

    return _safe_id(value, code=RUNTIME_INVALID_SUPERVISOR_TURN)


def _safe_source_kind(value: Any) -> str:
    if type(value) is not str or value not in SUPERVISOR_SOURCE_KINDS:
        _invalid()
    return value


def _safe_supervisor_status(value: Any) -> str:
    if type(value) is not str or value not in SUPERVISOR_TURN_STATUSES:
        _invalid()
    return value


def _safe_foreign_cursor(value: Any) -> int | None:
    """``None`` or an exact bounded non-negative ``int`` (``bool`` excluded).

    This is a *foreign* read-model position. It is surfaced and stored, and it
    is never appended to, mapped into, or reconciled with ``TaskEventLog.seq``.
    """

    if value is None:
        return None
    if type(value) is not int or value < 0 or value > _MAX_FOREIGN_CURSOR:
        _invalid()
    return value


def _safe_private_locator(value: Any) -> str:
    """Validate the PRIVATE, tagged locator carried by the dispatched handoff.

    Rejected on: a non-string or an empty string. A private locator is
    legitimately allowed to carry filesystem material or a raw id — that is
    exactly why it is kept off :class:`SupervisorTurnResult` and is only ever
    handed to a reader/binding layer; it is never scanned or serialized.
    """

    if type(value) is not str or value == "":
        _invalid()
    return value


# --------------------------------------------------------------------------- #
# The neutral result — five safe fields, by construction
# --------------------------------------------------------------------------- #
def _raw_result_dict(result: Any) -> dict[str, Any]:
    return {
        "run_ref": result.run_ref,
        "source_kind": result.source_kind,
        "source_ref": result.source_ref,
        "supervisor_status": result.supervisor_status,
        "foreign_cursor": result.foreign_cursor,
    }


def _check_supervisor_turn_result_fields(result: Any) -> None:
    """Exact fail-closed validation of a result's safe fields.

    Defends against ``object.__new__`` forgery and hostile subclasses that skip
    ``__post_init__``. Never echoes the rejected material.
    """

    try:
        run_ref = result.run_ref
        source_kind = result.source_kind
        source_ref = result.source_ref
        supervisor_status = result.supervisor_status
        foreign_cursor = result.foreign_cursor
    except AttributeError:
        _invalid()

    _safe_turn_ref(run_ref)
    _safe_source_kind(source_kind)
    _safe_turn_ref(source_ref)
    _safe_supervisor_status(supervisor_status)
    _safe_foreign_cursor(foreign_cursor)

    if scan_for_leak(_raw_result_dict(result)) is not None:
        _invalid()


@dataclass(frozen=True)
class SupervisorTurnResult:
    """One dispatched turn's safe, transport-neutral observation.

    Five safe fields and nothing else: there is **no** turn-directory field, so
    a library- or daemon-private path structurally cannot be constructed onto,
    logged from, or serialized out of this object. ``supervisor_status`` is a
    supervisor runtime observation, never a business verdict.
    """

    run_ref: str
    source_kind: str
    source_ref: str
    supervisor_status: str
    foreign_cursor: int | None

    def __post_init__(self) -> None:
        _check_supervisor_turn_result_fields(self)

    def as_dict(self) -> dict[str, Any]:
        validate_supervisor_turn_result(self)
        return {
            "run_ref": self.run_ref,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "supervisor_status": self.supervisor_status,
            "foreign_cursor": self.foreign_cursor,
        }


def validate_supervisor_turn_result(result: Any) -> SupervisorTurnResult:
    """Re-validate a result at a trust boundary and return it unchanged."""

    if type(result) is not SupervisorTurnResult:
        _invalid()
    _check_supervisor_turn_result_fields(result)
    return result


def serialize_supervisor_turn_result(result: SupervisorTurnResult) -> bytes:
    """Byte-stable canonical JSON serialization after full re-validation."""

    validated = validate_supervisor_turn_result(result)
    return json.dumps(validated.as_dict(), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


# --------------------------------------------------------------------------- #
# Private handoff — the safe result PLUS the tagged private locator
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, repr=False)
class DispatchedSupervisorTurn:
    """Host-owned handoff: the safe :class:`SupervisorTurnResult` plus the
    PRIVATE locator its ``source_kind`` tags.

    The locator is an artifact directory under ``artifact_file`` and a raw
    ``run_id`` under ``arsd_run``. It is meant only to be handed to the
    host-owned binding store. This holder deliberately exposes no
    ``as_dict``/serialize surface and opts out of dataclass ``repr`` so the
    private locator cannot leak through routine object logging. Serialize
    ``.result`` when a public handle is needed.
    """

    result: SupervisorTurnResult
    private_locator: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "result", validate_supervisor_turn_result(self.result))
        object.__setattr__(
            self, "private_locator", _safe_private_locator(self.private_locator)
        )


# --------------------------------------------------------------------------- #
# The neutral backend contract
# --------------------------------------------------------------------------- #
@runtime_checkable
class SupervisorTurnBackend(Protocol):
    """The Sachima-owned turn/lifecycle surface a composition root may drive.

    Structural conformance is necessary and **not** sufficient: every
    composition root additionally passes the object through
    :func:`validate_supervisor_turn_backend`.

    ``run_turn`` takes the whole identity of a dispatch, and every part of it
    is **required**: ``dispatch_ref`` is the durable binding key,
    ``payload_ref`` is the prompt's claim-check handle (Spec §8.1), and
    ``session_ref`` is the canonical Sachima Session the turn belongs to. A
    submit backend cannot write its pending intent without the first, cannot
    rebuild the frozen payload for a recovery without the second, and cannot
    prove a later recovery is a recovery *of this dispatch* without the third.
    :meth:`recover_uncertain_submission` is handed the same identity back and
    refuses anything that does not match it.

    Three surfaces exist for the *restart* case, and each of them names what it
    acts on rather than letting the backend choose:
    :meth:`rehydrate_pending_intent` rebuilds one exact pending dispatch without
    any I/O, :meth:`accepted_turn_for_binding` returns the handoff for one exact
    accepted record (never the task's latest), and :meth:`cancel_run` is the
    Run-scoped cancel — the one that leaves the Session reusable, as distinct
    from :meth:`kill`, which ends the task.
    """

    def create_or_attach(self, task_id: str, refs: tuple[str, ...]) -> str: ...

    def attach_existing(self, task_id: str) -> str: ...

    def run_turn(
        self,
        task_id: str,
        *,
        turn_kind: str,
        payload_text: str,
        dispatch_ref: str,
        payload_ref: str,
        session_ref: str,
    ) -> DispatchedSupervisorTurn: ...

    def recover_uncertain_submission(
        self, task_id: str, dispatch_ref: str, *, session_ref: str, turn_kind: str
    ) -> DispatchedSupervisorTurn: ...

    def latest_accepted_turn(
        self, task_id: str, *, session_ref: str
    ) -> DispatchedSupervisorTurn | None: ...

    def accepted_turn_for_binding(
        self, task_id: str, binding: Any, *, session_ref: str
    ) -> DispatchedSupervisorTurn: ...

    def rehydrate_pending_intent(self, task_id: str, dispatch_ref: str) -> str: ...

    def cancel_run(self, handle: str) -> Any: ...

    @property
    def task_locks(self) -> TaskOperationLocks:
        """The task operation lock provider this backend guards its work with.

        Published so a composition root can *derive* the shared section rather
        than be trusted to pass the same object twice.
        """
        ...

    def status(self, handle: str) -> str: ...

    def signal(self, handle: str, decision_ref: str) -> str: ...

    def kill(self, handle: str, reason_ref: str) -> str: ...

    def liveness(self, handle: str) -> str: ...


#: The exact-type factory allowlist: ``(factory kind, module, attribute)``.
#: Resolved lazily so this module stays importable by the very backends it
#: admits, and so importing it pulls in no backend machinery. After P5 the
#: ``arsd`` adapter is the only turn backend there is: the ``library`` entry is
#: retired with the backend it named, and the deterministic ``fake`` backend
#: runs no turns and therefore never reaches this gate. Admissibility is not
#: enablement: an ``arsd`` backend still cannot be constructed without an
#: explicitly enabled config.
_BACKEND_FACTORY_ALLOWLIST: tuple[tuple[str, str, str], ...] = (
    (
        "arsd",
        "sachima_supervisor.runtime_spine.arsd_supervisor_backend",
        "ArsdSupervisorBackend",
    ),
)


def _allowed_backend_types() -> tuple[type, ...]:
    import importlib

    allowed: list[type] = []
    for _kind, module_name, attribute in _BACKEND_FACTORY_ALLOWLIST:
        try:
            module = importlib.import_module(module_name)
        except BaseException:
            # An unresolvable factory admits nothing; it never widens the gate.
            continue
        candidate = getattr(module, attribute, None)
        if type(candidate) is type:
            allowed.append(candidate)
    return tuple(allowed)


def validate_supervisor_turn_backend(backend: Any) -> Any:
    """Admit only an allowlisted concrete backend, and return it unchanged.

    An **exact-type** check, not a duck-type check: a protocol-shaped object and
    a subclass of an allowlisted type are both refused, so neither an arbitrary
    injected object nor a hostile subclass overriding a validated method can
    reach a production composition root (Spec §8.1). Never echoes the rejected
    object.
    """

    if type(backend) not in _allowed_backend_types():
        _invalid()
    return backend


# --------------------------------------------------------------------------- #
# One task operation critical section, shared by every layer
# --------------------------------------------------------------------------- #
class TaskOperationLocks:
    """One reentrant lock per task, handed to every layer that acts on it.

    Acting on a task is not one layer's business. A submit backend admits a
    Run, ends one, and reconciles terminal truth; a composition root binds the
    read-model source and appends the canonical events that say the turn
    happened. Those are steps of a single operation, and if each layer guards
    its own steps with its own lock there is a seam between them — the one
    where a durable acceptance exists and Sachima has not published it yet.
    A cancel that lands in that seam ends a task that then starts running.

    So there is one provider, injected into both layers, and one lock per
    task. It is **reentrant** because the inner layer legitimately re-enters
    the section the outer one already holds, and it is per task because one
    task's daemon wait must not hold every other task's operations behind it.

    Locks are created on demand and kept: a task's identity outlives any one
    operation, and the map is bounded by the tasks a host actually touches.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}

    def for_task(self, task_id: Any) -> threading.RLock:
        """This task's lock, created once and returned forever after."""

        safe_task = _safe_id(task_id, code=RUNTIME_INVALID_SUPERVISOR_TURN)
        with self._guard:
            lock = self._locks.get(safe_task)
            if lock is None:
                lock = threading.RLock()
                self._locks[safe_task] = lock
            return lock

    @contextmanager
    def hold(self, task_id: Any) -> Iterator[None]:
        """Hold this task's operation lock for the duration of the block."""

        with self.for_task(task_id):
            yield


# --------------------------------------------------------------------------- #
# Derivations
# --------------------------------------------------------------------------- #
def derive_turn_ref(turn_index: int, turn_id: str) -> str:
    """The safe public turn ref: ``turn_<n>_<digest8>`` — never the raw id.

    Supervisor turn ids carry uppercase timestamp material and are not safe
    spine refs; the digest keeps the public handle stable, unique, and
    ``_safe_id``-shaped.
    """

    if type(turn_index) is not int or turn_index < 1:
        _invalid()
    if type(turn_id) is not str or not turn_id:
        _invalid()
    digest = hashlib.sha256(turn_id.encode("utf-8")).hexdigest()[:_TURN_REF_DIGEST_CHARS]
    return _safe_turn_ref(f"turn_{turn_index}_{digest}")
