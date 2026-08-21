"""P2 durable private Run/Session binding ledger for the ``arsd`` adapter.

This module is the ARS 0.7.6 Socket API v3 integration plan's P2 slice
(``docs/plans/2026-08-17-ars-0.7.6-socket-api-v3-integration-plan.md`` §8):
the restart-safe ``(task_id, session_id, dispatch_ref)`` ->
``(run_id, ars_session_id)`` binding a submit backend will later (P4) depend
on. It stores identity and nothing else. It opens no socket, imports no
``agent_run_supervisor``, starts nothing, and writes only to a host-owned
private file.

Boundaries:

* **Two states, one record.** A dispatch is written ``pending`` *before* the
  first submit and finalized **in place** to ``accepted`` by a validated ack.
  There is never a second record for the same key, and no accepted record
  exists without a preceding pending one (Spec §7.3.1). That is what makes a
  lost ack recoverable: an ack-only write leaves nothing durable to prove
  which ``request_id`` and payload digest were in flight.
* **Acceptance binds the pair, atomically.** An accepted record carries both
  ``run_id`` and ``ars_session_id`` or it is not accepted: the validated
  three-key ack supplies both, and one swap publishes both. Nothing attaches
  a Session id to an already-accepted record, so there is no window in which
  a crash could leave a durable Run that names no Session — a state restart
  recovery could not act on, since the next turn of that task must reuse the
  recorded Session verbatim and may never invent or recreate one.
* **Fail-closed, never inferring.** A record left ``pending`` is unresolved:
  :meth:`ArsdRunBindingLedger.resolve` refuses to read acceptance into it, and
  the ledger never deletes it, never finalizes it by inference, and never
  triggers a replay. Only an explicit recovery entry point (P4) may act on it.
* **One key contract.** The key is the full ``(task_id, session_id,
  dispatch_ref)`` triple — exactly :func:`derive_arsd_request_id`'s inputs
  (review closure R-2). ``(task_id, dispatch_ref)`` is not unique over a
  task's lifetime, because a reconstruct/attach cycle can mint a new spine
  ``session_id`` for the same task, so it would alias two distinct dispatches
  onto one binding. ``request_id`` rides along as a derived **witness**, not a
  second key, and a record whose witness disagrees with its own key fails
  closed on read.
* **Atomic and never silently reset.** Writes are serialize -> temp sibling ->
  ``os.replace``, flushed to disk before the swap, so ``begin_pending`` returns
  only once the intent has landed and no reader can observe a half-written
  ledger. A torn, empty, or unparseable file is
  ``runtime_invalid_arsd_binding``; the damaged bytes stay on disk.
* **No-leak.** The record holds refs and digests only: no prompt or payload
  text, credential value, socket path, or remote text, in either state. The
  raw ``run_id`` / ``ars_session_id`` are private (``repr=False``, absent from
  :meth:`ArsdRunBinding.as_dict`); ``run_ref`` is the public handle. They are
  persisted in the durable file — that is what a restart resumes from — and
  the file lives behind the same private-path boundary as ``socket_path``:
  absolute, host-owned, outside the tracked repo.
* **Never the canonical log.** Nothing here touches ``TaskEventLog``: raw ids
  are forbidden there (Spec §9.5), and the ledger is private identity, not an
  event.

Scope note: enforcing "at most one **active** Run per ``(task_id,
session_id)``" (Spec §7.4) needs terminal truth, which arrives with the
backend that observes it (P4). This ledger records ``pending`` and
``accepted`` only, so it deliberately makes no activity claim. Likewise
``retry_of_run_id`` is not a record field: it belongs to the explicit
recovery decision (P4), never to a timeout or disconnect path.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, NoReturn

from .arsd_socket_contract import (
    _private_abs_path,
    _safe_session_token,
    _safe_wire_token,
    _wire_timestamp,
    derive_arsd_request_id,
)
from .events import SpineError, _safe_digest, _safe_id

__all__ = [
    "ARSD_BINDING_ACCEPTED",
    "ARSD_BINDING_LEDGER_TYPE",
    "ARSD_BINDING_PENDING",
    "ARSD_BINDING_STABLE_CODES",
    "ARSD_BINDING_STATES",
    "RUNTIME_ARSD_BINDING_CONFLICT",
    "RUNTIME_INVALID_ARSD_BINDING",
    "ArsdRunBinding",
    "ArsdRunBindingLedger",
    "derive_arsd_binding_key",
    "derive_run_ref",
]

# --------------------------------------------------------------------------- #
# Stable codes (module-local; the message IS the code, never raw input)
# --------------------------------------------------------------------------- #
#: A malformed record, a torn/unparseable ledger file, or unsafe input.
RUNTIME_INVALID_ARSD_BINDING = "runtime_invalid_arsd_binding"
#: Two irreconcilable statements about one dispatch identity: a same-key
#: rewrite with different material, an accepted binding with no intent, a
#: replaced Session, or a stored ``request_id`` witness that disagrees with
#: its own key. The P4 recovery digest mismatch reuses this code — it is a
#: binding conflict, not a new failure family.
RUNTIME_ARSD_BINDING_CONFLICT = "runtime_arsd_binding_conflict"

ARSD_BINDING_STABLE_CODES = frozenset(
    {RUNTIME_INVALID_ARSD_BINDING, RUNTIME_ARSD_BINDING_CONFLICT}
)

ARSD_BINDING_LEDGER_TYPE = "sachima.runtime_spine.arsd_run_binding_ledger.v1"
ARSD_BINDING_PENDING = "pending"
ARSD_BINDING_ACCEPTED = "accepted"
#: The closed state vocabulary. There is no terminal state here on purpose:
#: run outcomes are ARS's truth, observed by the backend, not ledger state.
ARSD_BINDING_STATES = (ARSD_BINDING_PENDING, ARSD_BINDING_ACCEPTED)

_RUN_REF_PREFIX = "run_"
_RUN_REF_DIGEST_CHARS = 8

_LEDGER_DOCUMENT_KEYS = frozenset({"type", "bindings"})
_RECORD_KEYS = frozenset(
    {
        "task_id",
        "session_id",
        "dispatch_ref",
        "request_id",
        "payload_digest",
        "state",
        "resolver_refs",
        "run_ref",
        "accepted_at",
        "run_id",
        "ars_session_id",
    }
)


# Every stable raiser suppresses exception context (``from None`` semantics):
# validation runs inside ``except`` blocks around stdlib parsing, and an
# unsuppressed ``__context__`` would render the rejected material through the
# stable error's chain.
def _invalid_binding() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_ARSD_BINDING) from None


def _binding_conflict() -> NoReturn:
    raise SpineError(RUNTIME_ARSD_BINDING_CONFLICT) from None


def _safe_ref_value(value: Any) -> str:
    """One resolver ref: a safe spine ref or a sha256 digest, nothing else.

    This is the door free text would have to come through, and it is shut:
    prompt bodies, credential values, socket paths, and remote error text are
    none of these shapes.
    """

    try:
        return _safe_id(value, code=RUNTIME_INVALID_ARSD_BINDING)
    except SpineError:
        pass
    try:
        return _safe_digest(value, code=RUNTIME_INVALID_ARSD_BINDING)
    except SpineError:
        _invalid_binding()


def _owned_resolver_refs(value: Any) -> Mapping[str, str]:
    """The immutable ref set a resolver rebuilds the frozen payload from.

    Owned and copied, so caller-side mutation after the intent lands can never
    drift what recovery will rebuild. Empty is refused: an intent nothing can
    be rebuilt from is not a recoverable intent.
    """

    if not isinstance(value, Mapping) or not value:
        _invalid_binding()
    owned = {
        _safe_id(key, code=RUNTIME_INVALID_ARSD_BINDING): _safe_ref_value(item)
        for key, item in value.items()
    }
    return MappingProxyType(dict(sorted(owned.items())))


def _binding_timestamp(value: Any) -> str:
    """One bounded timezone-aware ack timestamp, on the ledger's own code."""

    try:
        return _wire_timestamp(value)
    except SpineError:
        _invalid_binding()


def derive_arsd_binding_key(
    task_id: Any, session_id: Any, dispatch_ref: Any
) -> tuple[str, str, str]:
    """The ledger key: the full triple, validated (review closure R-2).

    Deliberately the same three components :func:`derive_arsd_request_id`
    hashes, so ``derive_arsd_request_id(*key)`` is a checkable statement about
    every stored record.
    """

    return (
        _safe_id(task_id, code=RUNTIME_INVALID_ARSD_BINDING),
        _safe_id(session_id, code=RUNTIME_INVALID_ARSD_BINDING),
        _safe_id(dispatch_ref, code=RUNTIME_INVALID_ARSD_BINDING),
    )


def derive_run_ref(run_id: Any) -> str:
    """The safe public Run handle: ``run_<digest8>`` — never the raw id.

    ARS Run ids are opaque foreign tokens carrying uppercase/punctuation
    material and are not safe spine refs; the digest keeps the public handle
    stable and ``_safe_id``-shaped while the raw id stays private.
    """

    token = _safe_wire_token(run_id, code=RUNTIME_INVALID_ARSD_BINDING)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:_RUN_REF_DIGEST_CHARS]
    return _safe_id(
        _RUN_REF_PREFIX + digest, code=RUNTIME_INVALID_ARSD_BINDING
    )


def _check_binding_fields(binding: Any, *, normalize: bool = False) -> None:
    key = derive_arsd_binding_key(
        binding.task_id, binding.session_id, binding.dispatch_ref
    )
    request_id = _safe_wire_token(
        binding.request_id, code=RUNTIME_INVALID_ARSD_BINDING
    )
    # The witness is redundant with the key on purpose: the redundancy is what
    # makes the one-key contract checkable rather than merely asserted.
    if derive_arsd_request_id(*key) != request_id:
        _binding_conflict()

    _safe_digest(binding.payload_digest, code=RUNTIME_INVALID_ARSD_BINDING)
    if binding.state not in ARSD_BINDING_STATES:
        _invalid_binding()
    owned_refs = _owned_resolver_refs(binding.resolver_refs)

    if binding.state == ARSD_BINDING_PENDING:
        # Nothing accepted-only may exist before the ack that proves it.
        if (
            binding.run_id is not None
            or binding.run_ref is not None
            or binding.accepted_at is not None
            or binding.ars_session_id is not None
        ):
            _invalid_binding()
    else:
        run_id = _safe_wire_token(binding.run_id, code=RUNTIME_INVALID_ARSD_BINDING)
        if binding.run_ref != derive_run_ref(run_id):
            _invalid_binding()
        _binding_timestamp(binding.accepted_at)
        # The pair, or nothing: a record naming a Run with no Session is
        # unusable for reuse and unrecoverable after a restart, so it is
        # refused wherever an accepted record is admitted — construction and
        # file read alike.
        _safe_session_token(
            binding.ars_session_id, code=RUNTIME_INVALID_ARSD_BINDING
        )

    if normalize:
        object.__setattr__(binding, "resolver_refs", owned_refs)


@dataclass(frozen=True)
class ArsdRunBinding:
    """One durable dispatch identity, in exactly one of two states.

    Public material is refs and digests only. ``run_id`` / ``ars_session_id``
    are private: ``repr=False``, absent from :meth:`as_dict`, and represented
    publicly by ``run_ref``. They exist on the record because resuming a Run
    after a restart is the whole point of the ledger.
    """

    task_id: str
    session_id: str
    dispatch_ref: str
    #: Derived witness of the key, not a second key.
    request_id: str
    payload_digest: str
    state: str
    resolver_refs: Mapping[str, str]
    #: Accepted-only, and the public stand-in for ``run_id``.
    run_ref: str | None = None
    accepted_at: str | None = None
    #: Both are ``None`` while ``pending`` and both are required once
    #: ``accepted`` — the state carries the pair, never half of it.
    run_id: str | None = field(default=None, repr=False)
    ars_session_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _check_binding_fields(self, normalize=True)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.task_id, self.session_id, self.dispatch_ref)

    def as_dict(self) -> dict[str, Any]:
        """The refs-only projection. The private ids are not in it."""

        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "dispatch_ref": self.dispatch_ref,
            "request_id": self.request_id,
            "payload_digest": self.payload_digest,
            "state": self.state,
            "resolver_refs": dict(self.resolver_refs),
            "run_ref": self.run_ref,
            "accepted_at": self.accepted_at,
        }


def _record_document(binding: ArsdRunBinding) -> dict[str, Any]:
    """The durable form: the refs-only projection PLUS the private ids.

    The private ids are here and nowhere else. This is a host-owned file on a
    private absolute path outside the tracked repo — the same boundary
    ``socket_path`` sits behind — never a serialized public surface.
    """

    document = binding.as_dict()
    document["run_id"] = binding.run_id
    document["ars_session_id"] = binding.ars_session_id
    return document


def _binding_from_document(entry: Any) -> ArsdRunBinding:
    if not isinstance(entry, dict) or set(entry) != _RECORD_KEYS:
        _invalid_binding()
    return ArsdRunBinding(
        task_id=entry["task_id"],
        session_id=entry["session_id"],
        dispatch_ref=entry["dispatch_ref"],
        request_id=entry["request_id"],
        payload_digest=entry["payload_digest"],
        state=entry["state"],
        resolver_refs=entry["resolver_refs"],
        run_ref=entry["run_ref"],
        accepted_at=entry["accepted_at"],
        run_id=entry["run_id"],
        ars_session_id=entry["ars_session_id"],
    )


@dataclass
class ArsdRunBindingLedger:
    """The durable two-state binding store over one private host path.

    Every operation reads the file, so a fresh instance over the same path is
    the same ledger — that is the restart guarantee, with no in-memory cache
    able to disagree with what landed on disk.
    """

    path: str = field(repr=False)
    _lock: threading.RLock = field(
        default_factory=threading.RLock, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        self.path = _private_abs_path(self.path, code=RUNTIME_INVALID_ARSD_BINDING)

    # -- durable file ------------------------------------------------------- #
    def _read(self) -> dict[tuple[str, str, str], ArsdRunBinding]:
        """Load every record, or fail closed. An absent file is an empty
        ledger; an empty or torn one is not — that distinction is the whole
        difference between "nothing bound yet" and "we lost the bindings"."""

        try:
            raw = Path(self.path).read_bytes()
        except FileNotFoundError:
            return {}
        except OSError:
            _invalid_binding()
        if not raw:
            _invalid_binding()
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            _invalid_binding()
        if (
            not isinstance(document, dict)
            or set(document) != _LEDGER_DOCUMENT_KEYS
            or document["type"] != ARSD_BINDING_LEDGER_TYPE
            or not isinstance(document["bindings"], list)
        ):
            _invalid_binding()

        records: dict[tuple[str, str, str], ArsdRunBinding] = {}
        for entry in document["bindings"]:
            binding = _binding_from_document(entry)
            if binding.key in records:
                # No key ever holds two records, on disk either.
                _binding_conflict()
            records[binding.key] = binding
        return records

    def _write(self, records: Mapping[tuple[str, str, str], ArsdRunBinding]) -> None:
        """Serialize -> temp sibling -> ``os.replace``, durable before the swap.

        The caller is told the write landed only after ``os.replace`` returns,
        so P4 can write the pending intent and then submit knowing the intent
        is on disk.
        """

        document = {
            "type": ARSD_BINDING_LEDGER_TYPE,
            "bindings": [_record_document(records[key]) for key in sorted(records)],
        }
        payload = json.dumps(
            document, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

        path = Path(self.path)
        temp = path.with_name(path.name + ".tmp")
        try:
            with open(temp, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            try:
                os.unlink(temp)
            except OSError:
                pass
            _invalid_binding()

    def _require_unreplaced_session(
        self,
        records: Mapping[tuple[str, str, str], ArsdRunBinding],
        task_id: str,
        ars_session_id: str,
    ) -> None:
        """Spec §7.3 rule 3, scoped to the task: one task, one ARS Session.

        Checked across every record of the task rather than the one being
        written, because a task's Session outlives any single dispatch and a
        quarantined or unknown Session is never auto-recreated.
        """

        for other in records.values():
            if other.task_id != task_id:
                continue
            if (
                other.ars_session_id is not None
                and other.ars_session_id != ars_session_id
            ):
                _binding_conflict()

    # -- two-phase write ---------------------------------------------------- #
    def begin_pending(
        self,
        task_id: Any,
        session_id: Any,
        dispatch_ref: Any,
        *,
        request_id: Any,
        payload_digest: Any,
        resolver_refs: Any,
    ) -> ArsdRunBinding:
        """Write the submission intent, atomically, before any submit.

        Idempotent on the full key with byte-equivalent material. A same-key
        write with a different ``request_id``, ``payload_digest``, or
        ``resolver_refs`` fails closed and never overwrites (Spec §7.1: no new
        id, no resubmit), and an accepted record is never demoted back to an
        intent.
        """

        key = derive_arsd_binding_key(task_id, session_id, dispatch_ref)
        intent = ArsdRunBinding(
            task_id=key[0],
            session_id=key[1],
            dispatch_ref=key[2],
            request_id=request_id,
            payload_digest=payload_digest,
            state=ARSD_BINDING_PENDING,
            resolver_refs=resolver_refs,
        )
        with self._lock:
            records = self._read()
            existing = records.get(key)
            if existing is not None:
                if (
                    existing.state != ARSD_BINDING_PENDING
                    or existing.request_id != intent.request_id
                    or existing.payload_digest != intent.payload_digest
                    or dict(existing.resolver_refs) != dict(intent.resolver_refs)
                ):
                    _binding_conflict()
                return existing
            records[key] = intent
            self._write(records)
            return intent

    def finalize_accepted(
        self,
        task_id: Any,
        session_id: Any,
        dispatch_ref: Any,
        *,
        run_id: Any,
        ars_session_id: Any,
        accepted_at: Any,
    ) -> ArsdRunBinding:
        """Promote the existing intent to ``accepted``, in place.

        Adds ``run_id``, ``ars_session_id``, and ``accepted_at`` to the record
        the intent already wrote, carrying its ``request_id``,
        ``payload_digest``, and ``resolver_refs`` through untouched — exactly
        one logical record per dispatch, always (Spec §7.3.1). Finalizing a
        key with no intent, or one already accepted with different material,
        fails closed.

        All three come from the one validated three-key ack and land in a
        single atomic write. ``ars_session_id`` is required: this is the only
        place a Session id is ever recorded, so acceptance can never be
        published without it.
        """

        key = derive_arsd_binding_key(task_id, session_id, dispatch_ref)
        with self._lock:
            records = self._read()
            existing = records.get(key)
            if existing is None:
                _binding_conflict()
            accepted = replace(
                existing,
                state=ARSD_BINDING_ACCEPTED,
                run_id=_safe_wire_token(run_id, code=RUNTIME_INVALID_ARSD_BINDING),
                run_ref=derive_run_ref(run_id),
                accepted_at=accepted_at,
                ars_session_id=_safe_session_token(
                    ars_session_id, code=RUNTIME_INVALID_ARSD_BINDING
                ),
            )
            if existing.state == ARSD_BINDING_ACCEPTED:
                if (
                    existing.run_id != accepted.run_id
                    or existing.ars_session_id != accepted.ars_session_id
                    or existing.accepted_at != accepted.accepted_at
                ):
                    _binding_conflict()
                return existing
            # ``ars_session_id`` is optional on the record because a pending
            # one has none; on an accepted one it is required, and the
            # construction above has just re-validated that. It is read back
            # off the constructed record rather than reused from the argument,
            # so the id checked against the task's other records is exactly the
            # id about to be written. Absent here would mean the invariant was
            # bypassed — a forged record or a hostile subclass — so it fails
            # closed on the module's own malformed-record code instead of being
            # narrowed away.
            bound_session_id = accepted.ars_session_id
            if type(bound_session_id) is not str:  # pragma: no cover - __post_init__ enforces it
                _invalid_binding()
            self._require_unreplaced_session(records, key[0], bound_session_id)
            records[key] = accepted
            self._write(records)
            return accepted

    def record_session_id(
        self,
        task_id: Any,
        session_id: Any,
        dispatch_ref: Any,
        *,
        ars_session_id: Any,
    ) -> ArsdRunBinding:
        """Verify the Session id recorded at acceptance — never fill it in.

        The id is written exactly once, by :meth:`finalize_accepted`, in the
        same write that binds the Run. This is the reuse-path check the next
        turn makes before passing the recorded id verbatim: presenting the
        same id returns the binding unchanged, and presenting a different one
        fails closed rather than silently replacing a Session (Spec §7.3
        rule 3).

        It deliberately performs no write. A writer here would reopen the
        window acceptance closed, letting a durable record exist that names a
        Run but not the Session it runs in.
        """

        key = derive_arsd_binding_key(task_id, session_id, dispatch_ref)
        token = _safe_session_token(
            ars_session_id, code=RUNTIME_INVALID_ARSD_BINDING
        )
        with self._lock:
            existing = self._read().get(key)
        # A Session belongs to an admitted Run; an unadmitted intent has
        # nothing to verify against.
        if existing is None or existing.state != ARSD_BINDING_ACCEPTED:
            _binding_conflict()
        if existing.ars_session_id != token:
            _binding_conflict()
        return existing

    # -- reads -------------------------------------------------------------- #
    def resolve(
        self, task_id: Any, session_id: Any, dispatch_ref: Any
    ) -> ArsdRunBinding | None:
        """The accepted binding for this dispatch, or ``None``.

        A ``pending`` record reports unresolved. Acceptance is never inferred
        from an intent — only a validated ack can state it.
        """

        key = derive_arsd_binding_key(task_id, session_id, dispatch_ref)
        with self._lock:
            existing = self._read().get(key)
        if existing is None or existing.state != ARSD_BINDING_ACCEPTED:
            return None
        return existing

    def resolve_pending(
        self, task_id: Any, session_id: Any, dispatch_ref: Any
    ) -> ArsdRunBinding | None:
        """The unfinalized intent for this dispatch, or ``None``.

        The read side of recovery: it surfaces the intent without acting on
        it. Deciding what to do about one is an explicit P4 entry point.
        """

        key = derive_arsd_binding_key(task_id, session_id, dispatch_ref)
        with self._lock:
            existing = self._read().get(key)
        if existing is None or existing.state != ARSD_BINDING_PENDING:
            return None
        return existing

    def snapshot_exact(
        self, task_id: Any, backend_handle: Any, dispatch_ref: Any
    ) -> ArsdRunBinding | None:
        """The one record at this exact key, in whichever state it holds.

        This is the classification read, and it is deliberately *one* read: the
        whole ledger is validated and the exact record returned under a single
        ``_lock`` acquisition, so a caller can never observe a combination that
        never existed on disk. Asking :meth:`resolve_pending` and then
        :meth:`resolve` reads the file twice, and a ``finalize_accepted`` that
        lands between them answers "no intent" to the first and "no acceptance"
        to the second — a fabricated third state in which a durable Run appears
        to have been neither submitted nor accepted, which is exactly the
        evidence a coordinator would clean up on.

        ``backend_handle`` is the ledger key's second component. The stored
        field is still named ``session_id`` for record compatibility; it has
        never been the ARS Session id, and naming it honestly here keeps a
        caller from passing one.

        A stable ledger failure (torn, unparseable, or self-contradictory
        bytes) propagates as it does everywhere else: the damaged file is left
        exactly as it is, and the caller treats "I could not read it" as its own
        conservative disposition rather than as an absence.
        """

        key = derive_arsd_binding_key(task_id, backend_handle, dispatch_ref)
        with self._lock:
            return self._read().get(key)

    def resolve_for_task(self, task_id: Any) -> tuple[ArsdRunBinding, ...]:
        """Every record of one task, both states, in stable key order."""

        safe_task = _safe_id(task_id, code=RUNTIME_INVALID_ARSD_BINDING)
        with self._lock:
            records = self._read()
        return tuple(
            records[key] for key in sorted(records) if key[0] == safe_task
        )
