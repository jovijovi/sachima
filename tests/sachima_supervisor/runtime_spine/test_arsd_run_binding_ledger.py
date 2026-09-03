"""P2 durable private Run/Session binding ledger tests.

Covers the ARS 0.7.6 Socket API v3 integration plan P2 slice
(``docs/plans/2026-08-17-ars-0.7.6-socket-api-v3-integration-plan.md`` §8):
the two-state ``pending`` -> ``accepted`` binding record, its atomic
fail-closed durable file, the full ``(task_id, session_id, dispatch_ref)``
key contract, and the no-leak boundary over both record states.

Everything here is hermetic and offline. No daemon, no socket, no Runtime
Spine / Gateway wiring, no submit: the only facade in the file is a double
whose ``submit`` fails the test if the ledger ever reaches for it.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import (
    ARSD_BINDING_STABLE_CODES,
    RUNTIME_ARSD_BINDING_CONFLICT,
    RUNTIME_INVALID_ARSD_BINDING,
    ArsdRunBinding,
    ArsdRunBindingLedger,
    derive_arsd_binding_key,
    derive_run_ref,
)
from sachima_supervisor.runtime_spine.arsd_socket_contract import (
    derive_arsd_request_id,
)
from sachima_supervisor.runtime_spine.events import SpineError, scan_for_leak
from sachima_supervisor.runtime_spine.registry import TaskRegistry

# --------------------------------------------------------------------------- #
# Fixtures — one admitted dispatch identity, expressed only in safe refs.
# --------------------------------------------------------------------------- #
TASK_ID = "task_alpha"
SESSION_ID = "sess_alpha"
DISPATCH_REF = "turn_1_9f2c1a7b"
PAYLOAD_DIGEST = "sha256:" + "a" * 64
OTHER_PAYLOAD_DIGEST = "sha256:" + "c" * 64
RUN_ID = "RUN-canary-9f2c1a7b"
OTHER_RUN_ID = "RUN-canary-0e5d4c3b"
ARS_SESSION_ID = "SESSCANARY9f2c1a7b"
OTHER_ARS_SESSION_ID = "SESSCANARY0e5d4c3b"
ACCEPTED_AT = "2026-08-17T04:05:06+00:00"
OTHER_ACCEPTED_AT = "2026-08-17T05:06:07+00:00"

RESOLVER_REFS = {
    "agent_policy_ref": "policy_reader",
    "model_policy_ref": "policy_reader",
    "effort_policy_ref": "policy_reader",
    "workspace_ref": "ws_main",
    "run_limits_policy_ref": "policy_reader",
    "prompt_ref": "prompt_alpha",
    "grant_hash": "sha256:" + "b" * 64,
}

#: Material a binding ledger must never persist in EITHER record state.
PROMPT_CANARY = "sachima-canary-do-not-persist-this-prompt"
CREDENTIAL_CANARY = "sk-sachima-canary-credential-value"
SOCKET_CANARY = "/run/sachima-canary/arsd.sock"
REMOTE_TEXT_CANARY = "sachima-canary-remote-daemon-error-text"
LEAK_CANARIES = (
    PROMPT_CANARY,
    CREDENTIAL_CANARY,
    SOCKET_CANARY,
    REMOTE_TEXT_CANARY,
)


def _request_id(
    task_id: str = TASK_ID,
    session_id: str = SESSION_ID,
    dispatch_ref: str = DISPATCH_REF,
) -> str:
    return derive_arsd_request_id(task_id, session_id, dispatch_ref)


def _ledger_path(tmp_path: Path) -> str:
    return str(tmp_path / "arsd-bindings.json")


def _ledger(tmp_path: Path) -> ArsdRunBindingLedger:
    return ArsdRunBindingLedger(_ledger_path(tmp_path))


def _begin(
    ledger: ArsdRunBindingLedger,
    *,
    task_id: str = TASK_ID,
    session_id: str = SESSION_ID,
    dispatch_ref: str = DISPATCH_REF,
    request_id: str | None = None,
    payload_digest: str = PAYLOAD_DIGEST,
    resolver_refs: dict | None = None,
) -> ArsdRunBinding:
    return ledger.begin_pending(
        task_id,
        session_id,
        dispatch_ref,
        request_id=(
            _request_id(task_id, session_id, dispatch_ref)
            if request_id is None
            else request_id
        ),
        payload_digest=payload_digest,
        resolver_refs=dict(RESOLVER_REFS if resolver_refs is None else resolver_refs),
    )


def _finalize(
    ledger: ArsdRunBindingLedger,
    *,
    task_id: str = TASK_ID,
    session_id: str = SESSION_ID,
    dispatch_ref: str = DISPATCH_REF,
    run_id: str = RUN_ID,
    ars_session_id: str | None = ARS_SESSION_ID,
    accepted_at: str = ACCEPTED_AT,
) -> ArsdRunBinding:
    return ledger.finalize_accepted(
        task_id,
        session_id,
        dispatch_ref,
        run_id=run_id,
        ars_session_id=ars_session_id,
        accepted_at=accepted_at,
    )


def _assert_stable_code_only(excinfo, code: str) -> None:
    """The raised SpineError carries the stable code only — no raw material
    and no displayed exception chain."""

    err = excinfo.value
    assert err.code == code
    assert err.args == (code,)
    assert err.__cause__ is None
    assert err.__suppress_context__ or err.__context__ is None


class _SubmitRaisingFacade:
    """A facade double that fails the test if anything dispatches.

    The restart proof is only non-vacuous if a re-dispatch would be visible:
    every operation here raises, so a ledger that "recovered" by resubmitting
    fails loudly instead of quietly passing.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _refuse(self, name: str):
        def _call(*args, **kwargs):
            self.calls.append(name)
            raise AssertionError(
                f"the binding ledger must never reach the arsd facade: {name}"
            )

        return _call

    def __getattr__(self, name: str):
        return self._refuse(name)


class _AppendRaisingTaskRegistry(TaskRegistry):
    """A TaskRegistry whose canonical-log append raises on call (Spec §9.5)."""

    def append_event(self, task_id, body):  # type: ignore[override]
        raise AssertionError(
            "the binding ledger must never append to the TaskEventLog"
        )


# --------------------------------------------------------------------------- #
# Stable codes — module-local, closed, and never a foreign code.
# --------------------------------------------------------------------------- #
def test_ledger_stable_codes_are_closed_and_module_local() -> None:
    assert ARSD_BINDING_STABLE_CODES == frozenset(
        {RUNTIME_INVALID_ARSD_BINDING, RUNTIME_ARSD_BINDING_CONFLICT}
    )
    assert RUNTIME_INVALID_ARSD_BINDING == "runtime_invalid_arsd_binding"
    assert RUNTIME_ARSD_BINDING_CONFLICT == "runtime_arsd_binding_conflict"


# --------------------------------------------------------------------------- #
# R-2 — one key contract: the full triple, identical to the request-id inputs.
# --------------------------------------------------------------------------- #
def test_binding_key_is_exactly_the_request_id_derivation_inputs(tmp_path) -> None:
    """R-2: the ledger key IS ``(task_id, session_id, dispatch_ref)``.

    The stored ``request_id`` is a derived witness of that key, not a second
    key — so for every stored record the derivation must reproduce it, and a
    record whose stored witness disagrees fails closed on read.
    """

    ledger = _ledger(tmp_path)
    pending = _begin(ledger)
    accepted = _finalize(ledger)

    for binding in (pending, accepted):
        assert binding.key == (TASK_ID, SESSION_ID, DISPATCH_REF)
        assert derive_arsd_binding_key(*binding.key) == binding.key
        assert derive_arsd_request_id(*binding.key) == binding.request_id

    # A witness that disagrees with its own key is refused at construction ...
    with pytest.raises(SpineError) as excinfo:
        _begin(
            _ledger(tmp_path / "other"),
            request_id=_request_id(dispatch_ref="turn_2_0e5d4c3b"),
        )
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_BINDING_CONFLICT)

    # ... and on read, so a hand-edited file can never resolve.
    path = Path(_ledger_path(tmp_path))
    document = json.loads(path.read_bytes())
    document["bindings"][0]["request_id"] = _request_id(
        dispatch_ref="turn_2_0e5d4c3b"
    )
    path.write_bytes(json.dumps(document).encode("utf-8"))
    with pytest.raises(SpineError) as excinfo:
        _ledger(tmp_path).resolve(TASK_ID, SESSION_ID, DISPATCH_REF)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_BINDING_CONFLICT)


def test_same_dispatch_ref_under_two_spine_sessions_binds_two_records(
    tmp_path,
) -> None:
    """R-2: the alias a two-component ``(task_id, dispatch_ref)`` key would
    have created is proven absent.

    ``AgentRunSupervisorPort.create_or_attach`` can mint a new spine
    ``session_id`` for the same task across a reconstruct/attach cycle, so the
    same ``dispatch_ref`` legitimately recurs under a second spine session.
    Those are two distinct dispatches and must never collapse onto one
    binding.
    """

    ledger = _ledger(tmp_path)
    first = _begin(ledger, session_id="sess_alpha")
    second = _begin(ledger, session_id="sess_beta")

    assert first.request_id != second.request_id
    assert first.key != second.key

    _finalize(ledger, session_id="sess_alpha", run_id=RUN_ID)
    _finalize(ledger, session_id="sess_beta", run_id=OTHER_RUN_ID)

    records = ledger.resolve_for_task(TASK_ID)
    assert len(records) == 2
    assert {record.session_id for record in records} == {"sess_alpha", "sess_beta"}
    assert {record.run_id for record in records} == {RUN_ID, OTHER_RUN_ID}
    assert ledger.resolve(TASK_ID, "sess_alpha", DISPATCH_REF).run_id == RUN_ID
    assert ledger.resolve(TASK_ID, "sess_beta", DISPATCH_REF).run_id == OTHER_RUN_ID


# --------------------------------------------------------------------------- #
# R-1 — durable, restart-safe identity.
# --------------------------------------------------------------------------- #
def test_second_ledger_instance_resumes_without_redispatch(tmp_path) -> None:
    """R-1: a fresh ledger over the same path resolves the identical binding.

    Instance A writes the pending intent and finalizes it; A is dropped; a
    fresh instance reads the same private path with a submit-raising facade
    double in place. If any path had re-dispatched, the double would fail the
    test.
    """

    first = _ledger(tmp_path)
    _begin(first)
    accepted = _finalize(first)
    del first

    facade = _SubmitRaisingFacade()
    resumed = _ledger(tmp_path)
    resolved = resumed.resolve(TASK_ID, SESSION_ID, DISPATCH_REF)

    assert resolved is not None
    assert resolved.run_id == accepted.run_id == RUN_ID
    assert resolved.ars_session_id == accepted.ars_session_id == ARS_SESSION_ID
    assert resolved.run_ref == derive_run_ref(RUN_ID)
    assert resolved.request_id == _request_id()
    assert resolved.payload_digest == PAYLOAD_DIGEST
    assert dict(resolved.resolver_refs) == RESOLVER_REFS
    assert resolved.state == "accepted"
    assert facade.calls == []


def test_a_pending_record_survives_a_fresh_ledger_instance_and_stays_unresolved(
    tmp_path,
) -> None:
    """Durability plus fail-closed: the intent is readable, but not accepted.

    A record left ``pending`` is the whole point of writing before the submit
    — it must survive a restart with its recovery material intact while
    ``resolve()`` still refuses to infer acceptance from it.
    """

    _begin(_ledger(tmp_path))

    resumed = _ledger(tmp_path)
    pending = resumed.resolve_pending(TASK_ID, SESSION_ID, DISPATCH_REF)

    assert pending is not None
    assert pending.state == "pending"
    assert pending.request_id == _request_id()
    assert pending.payload_digest == PAYLOAD_DIGEST
    assert dict(pending.resolver_refs) == RESOLVER_REFS
    assert pending.run_id is None
    assert pending.ars_session_id is None
    assert pending.run_ref is None
    assert pending.accepted_at is None

    # Fail-closed: unresolved, never auto-finalized, never deleted.
    assert resumed.resolve(TASK_ID, SESSION_ID, DISPATCH_REF) is None
    again = _ledger(tmp_path)
    assert again.resolve(TASK_ID, SESSION_ID, DISPATCH_REF) is None
    assert again.resolve_pending(TASK_ID, SESSION_ID, DISPATCH_REF) is not None
    assert len(again.resolve_for_task(TASK_ID)) == 1


# --------------------------------------------------------------------------- #
# Pending -> accepted lifecycle: exactly one logical record per dispatch.
# --------------------------------------------------------------------------- #
def test_finalize_accepted_updates_the_pending_record_in_place_and_never_adds_a_second(
    tmp_path,
) -> None:
    """A-7: one key, one record, before and after.

    Finalization adds ``run_id`` / ``ars_session_id`` / ``accepted_at`` to the
    existing intent and flips its state; the intent's own material —
    ``request_id``, ``payload_digest``, ``resolver_refs`` — is carried through
    untouched.
    """

    ledger = _ledger(tmp_path)
    pending = _begin(ledger)
    assert len(ledger.resolve_for_task(TASK_ID)) == 1

    accepted = _finalize(ledger)

    assert len(ledger.resolve_for_task(TASK_ID)) == 1
    stored = json.loads(Path(_ledger_path(tmp_path)).read_bytes())["bindings"]
    assert len(stored) == 1

    assert accepted.state == "accepted"
    assert accepted.key == pending.key
    assert accepted.request_id == pending.request_id
    assert accepted.payload_digest == pending.payload_digest
    assert dict(accepted.resolver_refs) == dict(pending.resolver_refs)
    assert accepted.run_id == RUN_ID
    assert accepted.ars_session_id == ARS_SESSION_ID
    assert accepted.accepted_at == ACCEPTED_AT
    assert accepted.run_ref == derive_run_ref(RUN_ID)

    # The pending projection is gone precisely because it was promoted, not
    # duplicated.
    assert ledger.resolve_pending(TASK_ID, SESSION_ID, DISPATCH_REF) is None


def test_finalize_without_a_pending_intent_fails_closed(tmp_path) -> None:
    """An accepted binding can never appear without its intent."""

    ledger = _ledger(tmp_path)
    with pytest.raises(SpineError) as excinfo:
        _finalize(ledger)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_BINDING_CONFLICT)

    assert ledger.resolve(TASK_ID, SESSION_ID, DISPATCH_REF) is None
    assert ledger.resolve_for_task(TASK_ID) == ()
    assert not Path(_ledger_path(tmp_path)).exists()


def test_finalize_twice_with_different_material_fails_closed(tmp_path) -> None:
    """A second finalize never rewrites an accepted record."""

    ledger = _ledger(tmp_path)
    _begin(ledger)
    accepted = _finalize(ledger)

    # Byte-equivalent re-finalization is idempotent, not a rewrite.
    assert _finalize(ledger) == accepted

    for kwargs in (
        {"run_id": OTHER_RUN_ID},
        {"ars_session_id": OTHER_ARS_SESSION_ID},
        {"accepted_at": OTHER_ACCEPTED_AT},
    ):
        with pytest.raises(SpineError) as excinfo:
            _finalize(ledger, **kwargs)
        _assert_stable_code_only(excinfo, RUNTIME_ARSD_BINDING_CONFLICT)

    resolved = ledger.resolve(TASK_ID, SESSION_ID, DISPATCH_REF)
    assert resolved == accepted
    assert len(ledger.resolve_for_task(TASK_ID)) == 1


def test_finalize_accepted_binds_run_id_and_session_id_in_one_atomic_write(
    tmp_path, monkeypatch
) -> None:
    """An accepted binding is the ``(run_id, ars_session_id)`` PAIR, or it is
    not accepted.

    Acceptance and the Session binding land in the same swap. If the Session
    id could be attached afterwards, a crash between the two writes would
    leave a durable record naming a Run with no Session — restart recovery
    would hold a ``run_id`` it cannot reuse a Session for, and the next turn
    would have to invent one.
    """

    from sachima_supervisor.runtime_spine import arsd_run_binding_ledger as module

    ledger = _ledger(tmp_path)
    _begin(ledger)

    # The Session id is not optional at acceptance, by either route.
    with pytest.raises(TypeError):
        ledger.finalize_accepted(
            TASK_ID,
            SESSION_ID,
            DISPATCH_REF,
            run_id=RUN_ID,
            accepted_at=ACCEPTED_AT,
        )
    with pytest.raises(SpineError) as excinfo:
        _finalize(ledger, ars_session_id=None)
    _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_BINDING)

    # A refused acceptance leaves the intent pending, not half-accepted.
    assert ledger.resolve(TASK_ID, SESSION_ID, DISPATCH_REF) is None
    assert ledger.resolve_pending(TASK_ID, SESSION_ID, DISPATCH_REF) is not None

    swapped: list[bytes] = []
    real_replace = os.replace

    def _spy(src, dst):
        result = real_replace(src, dst)
        swapped.append(Path(dst).read_bytes())
        return result

    monkeypatch.setattr(module.os, "replace", _spy)
    accepted = _finalize(ledger)
    monkeypatch.undo()

    # Exactly one swap, and the bytes it published already carry both ids.
    assert len(swapped) == 1
    record = json.loads(swapped[0])["bindings"][0]
    assert record["state"] == "accepted"
    assert record["run_id"] == RUN_ID
    assert record["ars_session_id"] == ARS_SESSION_ID
    assert accepted.ars_session_id == ARS_SESSION_ID

    # A fresh instance resolves the pair immediately — no follow-up write.
    resolved = _ledger(tmp_path).resolve(TASK_ID, SESSION_ID, DISPATCH_REF)
    assert resolved.run_id == RUN_ID
    assert resolved.ars_session_id == ARS_SESSION_ID


def test_accepted_record_without_a_session_id_is_refused_on_build_and_on_read(
    tmp_path,
) -> None:
    """The pair invariant is enforced wherever an accepted record is admitted.

    Construction and file read go through the same allowlist, so a record that
    names a Run but no Session cannot be built in memory or resurrected from
    disk — including a ledger hand-edited into that shape.
    """

    with pytest.raises(SpineError) as excinfo:
        ArsdRunBinding(
            task_id=TASK_ID,
            session_id=SESSION_ID,
            dispatch_ref=DISPATCH_REF,
            request_id=_request_id(),
            payload_digest=PAYLOAD_DIGEST,
            state="accepted",
            resolver_refs=dict(RESOLVER_REFS),
            run_ref=derive_run_ref(RUN_ID),
            accepted_at=ACCEPTED_AT,
            run_id=RUN_ID,
            ars_session_id=None,
        )
    _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_BINDING)

    ledger = _ledger(tmp_path)
    _begin(ledger)
    _finalize(ledger)

    path = Path(_ledger_path(tmp_path))
    document = json.loads(path.read_bytes())
    document["bindings"][0]["ars_session_id"] = None
    path.write_bytes(json.dumps(document).encode("utf-8"))

    reopened = _ledger(tmp_path)
    for call in (
        lambda: reopened.resolve(TASK_ID, SESSION_ID, DISPATCH_REF),
        lambda: reopened.resolve_pending(TASK_ID, SESSION_ID, DISPATCH_REF),
        lambda: reopened.resolve_for_task(TASK_ID),
    ):
        with pytest.raises(SpineError) as excinfo:
            call()
        _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_BINDING)


def test_record_session_id_verifies_an_accepted_binding_and_never_writes(
    tmp_path, monkeypatch
) -> None:
    """The post-acceptance fill path is gone: verification only.

    Retaining a writer here would reopen the very gap the atomic finalize
    closes — an accepted record could still acquire its Session id after the
    fact. So this is the reuse-path check and nothing else: same id returns
    the binding unchanged, anything else fails closed, and no byte moves.
    """

    from sachima_supervisor.runtime_spine import arsd_run_binding_ledger as module

    ledger = _ledger(tmp_path)
    _begin(ledger)
    accepted = _finalize(ledger)
    _begin(ledger, dispatch_ref="turn_2_0e5d4c3b")

    path = Path(_ledger_path(tmp_path))
    before = path.read_bytes()

    swapped: list[str] = []
    real_replace = os.replace

    def _spy(src, dst):
        swapped.append(str(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(module.os, "replace", _spy)

    assert (
        ledger.record_session_id(
            TASK_ID, SESSION_ID, DISPATCH_REF, ars_session_id=ARS_SESSION_ID
        )
        == accepted
    )

    with pytest.raises(SpineError) as excinfo:
        ledger.record_session_id(
            TASK_ID, SESSION_ID, DISPATCH_REF, ars_session_id=OTHER_ARS_SESSION_ID
        )
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_BINDING_CONFLICT)

    with pytest.raises(SpineError) as excinfo:
        ledger.record_session_id(
            TASK_ID, SESSION_ID, DISPATCH_REF, ars_session_id=None
        )
    _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_BINDING)

    # A still-pending dispatch has no Session to verify against.
    with pytest.raises(SpineError) as excinfo:
        ledger.record_session_id(
            TASK_ID, SESSION_ID, "turn_2_0e5d4c3b", ars_session_id=ARS_SESSION_ID
        )
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_BINDING_CONFLICT)

    monkeypatch.undo()
    assert swapped == []
    assert path.read_bytes() == before


def test_idempotency_conflict_fails_closed_without_overwrite(tmp_path) -> None:
    """Spec §7.1: no new id, no resubmit — and no silent overwrite.

    A same-key pending write with byte-equivalent material is idempotent; one
    with a different ``request_id``, ``payload_digest``, or ``resolver_refs``
    fails closed and leaves the original intent byte-for-byte intact.
    """

    ledger = _ledger(tmp_path)
    intent = _begin(ledger)
    path = Path(_ledger_path(tmp_path))
    original = path.read_bytes()

    assert _begin(ledger) == intent
    assert path.read_bytes() == original

    drifted_refs = dict(RESOLVER_REFS, workspace_ref="ws_other")
    for kwargs in (
        {"request_id": _request_id(dispatch_ref="turn_2_0e5d4c3b")},
        {"payload_digest": OTHER_PAYLOAD_DIGEST},
        {"resolver_refs": drifted_refs},
    ):
        with pytest.raises(SpineError) as excinfo:
            _begin(ledger, **kwargs)
        _assert_stable_code_only(excinfo, RUNTIME_ARSD_BINDING_CONFLICT)
        assert path.read_bytes() == original

    # An accepted record is never demoted back to a fresh intent either.
    _finalize(ledger)
    with pytest.raises(SpineError) as excinfo:
        _begin(ledger)
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_BINDING_CONFLICT)
    assert ledger.resolve(TASK_ID, SESSION_ID, DISPATCH_REF).run_id == RUN_ID


def test_session_id_is_recorded_once_and_never_replaced(tmp_path) -> None:
    """Spec §7.3 rule 3: a Session is never silently replaced.

    The id is written exactly once — at acceptance, in the same write that
    binds the Run. A later turn presenting the same id is idempotent
    verification; one presenting a different id fails closed, across the whole
    task rather than just the one record, because a task has one ARS Session.
    """

    ledger = _ledger(tmp_path)
    _begin(ledger)
    bound = _finalize(ledger)
    assert bound.ars_session_id == ARS_SESSION_ID

    assert (
        ledger.record_session_id(
            TASK_ID, SESSION_ID, DISPATCH_REF, ars_session_id=ARS_SESSION_ID
        )
        == bound
    )

    with pytest.raises(SpineError) as excinfo:
        ledger.record_session_id(
            TASK_ID, SESSION_ID, DISPATCH_REF, ars_session_id=OTHER_ARS_SESSION_ID
        )
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_BINDING_CONFLICT)
    assert (
        ledger.resolve(TASK_ID, SESSION_ID, DISPATCH_REF).ars_session_id
        == ARS_SESSION_ID
    )

    # A second dispatch of the same task cannot bring a second Session in,
    # through either write path.
    _begin(ledger, dispatch_ref="turn_2_0e5d4c3b")
    with pytest.raises(SpineError) as excinfo:
        _finalize(
            ledger,
            dispatch_ref="turn_2_0e5d4c3b",
            run_id=OTHER_RUN_ID,
            ars_session_id=OTHER_ARS_SESSION_ID,
        )
    _assert_stable_code_only(excinfo, RUNTIME_ARSD_BINDING_CONFLICT)

    _finalize(
        ledger,
        dispatch_ref="turn_2_0e5d4c3b",
        run_id=OTHER_RUN_ID,
        ars_session_id=ARS_SESSION_ID,
    )
    assert {
        record.ars_session_id for record in ledger.resolve_for_task(TASK_ID)
    } == {ARS_SESSION_ID}


# --------------------------------------------------------------------------- #
# The durable file: atomic writes, fail-closed reads, private path.
# --------------------------------------------------------------------------- #
def test_ledger_writes_are_atomic_and_leave_no_temp_file(tmp_path, monkeypatch) -> None:
    """Serialize -> temp sibling -> ``os.replace``, and nothing left behind.

    Proven at the seam: when ``os.replace`` is called the destination still
    holds the *previous* bytes, so no reader can ever observe a half-written
    ledger.
    """

    from sachima_supervisor.runtime_spine import arsd_run_binding_ledger as module

    ledger = _ledger(tmp_path)
    _begin(ledger)
    path = Path(_ledger_path(tmp_path))
    before = path.read_bytes()

    observed: dict[str, object] = {}
    real_replace = os.replace

    def _spy(src, dst):
        observed["src"] = str(src)
        observed["dst"] = str(dst)
        observed["src_exists"] = Path(src).exists()
        observed["dst_bytes_at_replace"] = Path(dst).read_bytes()
        return real_replace(src, dst)

    monkeypatch.setattr(module.os, "replace", _spy)
    _finalize(ledger)
    monkeypatch.undo()

    assert observed["dst"] == str(path)
    assert observed["src"] != str(path)
    assert Path(str(observed["src"])).parent == path.parent
    assert observed["src_exists"] is True
    assert observed["dst_bytes_at_replace"] == before

    assert path.read_bytes() != before
    # No temp sibling survives the swap.
    siblings = sorted(
        entry.name for entry in tmp_path.iterdir() if entry.name.startswith(path.name)
    )
    assert siblings == [path.name]


def test_torn_ledger_file_fails_closed_and_is_not_reset(tmp_path) -> None:
    """A torn or unparseable ledger is ``runtime_invalid_arsd_binding``.

    It is never silently reset: the damaged bytes are still there afterwards,
    so an operator can recover them rather than discover a ledger that quietly
    forgot every binding.
    """

    ledger = _ledger(tmp_path)
    _begin(ledger)
    _finalize(ledger)

    path = Path(_ledger_path(tmp_path))
    intact = path.read_bytes()
    torn = intact[: len(intact) // 2]
    path.write_bytes(torn)

    reopened = _ledger(tmp_path)
    for call in (
        lambda: reopened.resolve(TASK_ID, SESSION_ID, DISPATCH_REF),
        lambda: reopened.resolve_pending(TASK_ID, SESSION_ID, DISPATCH_REF),
        lambda: reopened.resolve_for_task(TASK_ID),
        lambda: _begin(reopened),
        lambda: _finalize(reopened),
    ):
        with pytest.raises(SpineError) as excinfo:
            call()
        _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_BINDING)
        assert path.read_bytes() == torn

    # An empty file is torn too — it is not the same statement as "absent".
    path.write_bytes(b"")
    with pytest.raises(SpineError) as excinfo:
        _ledger(tmp_path).resolve(TASK_ID, SESSION_ID, DISPATCH_REF)
    _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_BINDING)


def test_ledger_path_inside_the_repo_is_refused(tmp_path) -> None:
    """The ledger is a host-owned private file, never tracked worktree state."""

    from sachima_supervisor.runtime_spine.arsd_socket_contract import _REPO_ROOT

    for candidate in (
        str(Path(_REPO_ROOT) / "arsd-bindings.json"),
        str(Path(_REPO_ROOT) / "sachima_supervisor" / "arsd-bindings.json"),
        "relative/arsd-bindings.json",
        "",
        7,
        None,
    ):
        with pytest.raises(SpineError) as excinfo:
            ArsdRunBindingLedger(candidate)
        _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_BINDING)

    # The private path itself never renders.
    ledger = _ledger(tmp_path)
    for rendering in (repr(ledger), str(ledger)):
        assert _ledger_path(tmp_path) not in rendering


# --------------------------------------------------------------------------- #
# A-20 — no-leak, over BOTH record states.
# --------------------------------------------------------------------------- #
def test_private_ids_are_absent_from_repr_and_as_dict(tmp_path) -> None:
    """The raw ``run_id`` / ``ars_session_id`` are private, ``run_ref`` is not.

    They ride on the record so a restart can resume the Run, and they appear
    on no rendering surface and in no serializable projection. The durable
    file is the one place they live, and it is a host-owned private path
    outside the repo — the same boundary ``socket_path`` sits behind.
    """

    ledger = _ledger(tmp_path)
    pending = _begin(ledger)
    accepted = _finalize(ledger)

    for binding in (pending, accepted):
        projection = binding.as_dict()
        surfaces = (
            repr(binding),
            str(binding),
            json.dumps(projection, sort_keys=True),
        )
        for surface in surfaces:
            assert RUN_ID not in surface
            assert ARS_SESSION_ID not in surface
        assert "run_id" not in projection
        assert "ars_session_id" not in projection
        assert scan_for_leak(projection, canaries=LEAK_CANARIES) is None

    assert accepted.as_dict()["run_ref"] == derive_run_ref(RUN_ID)
    assert derive_run_ref(RUN_ID).startswith("run_")
    assert RUN_ID not in derive_run_ref(RUN_ID)
    assert derive_run_ref(RUN_ID) != derive_run_ref(OTHER_RUN_ID)

    assert pending.as_dict()["run_ref"] is None
    assert pending.as_dict()["state"] == "pending"
    assert accepted.as_dict()["state"] == "accepted"

    # No serialize surface can smuggle the private ids back out.
    for attr in ("serialize", "to_json", "to_dict", "dict"):
        assert not hasattr(pending, attr)


def test_pending_record_persists_no_prompt_text_credential_socket_path_or_remote_text(
    tmp_path,
) -> None:
    """A-20: a leak sweep over the ledger file's BYTES in the pending state.

    The pending intent is written before any submit, so it is the record most
    tempting to fatten with the payload it describes. It carries refs and
    digests only: the resolver rebuilds the payload, the ledger never stores
    it.
    """

    ledger = _ledger(tmp_path)

    # Free text cannot enter through the one door that takes a mapping.
    for canary in LEAK_CANARIES:
        with pytest.raises(SpineError) as excinfo:
            _begin(ledger, resolver_refs=dict(RESOLVER_REFS, prompt_ref=canary))
        _assert_stable_code_only(excinfo, RUNTIME_INVALID_ARSD_BINDING)

    _begin(ledger)
    raw = Path(_ledger_path(tmp_path)).read_bytes()
    text = raw.decode("utf-8")

    for canary in LEAK_CANARIES:
        assert canary not in text
    assert scan_for_leak(json.loads(text), canaries=LEAK_CANARIES) is None
    # Nothing accepted-only exists yet, so the private ids are not even
    # present in the pending state's bytes.
    assert RUN_ID not in text
    assert ARS_SESSION_ID not in text
    assert _ledger_path(tmp_path) not in text


def test_ledger_never_appends_to_the_task_event_log(tmp_path) -> None:
    """Spec §9.5: the canonical log never carries the private binding.

    Driven with a ``TaskRegistry`` whose ``append_event`` raises, so a ledger
    that reached for the canonical log would fail rather than merely be
    unproven.
    """

    registry = _AppendRaisingTaskRegistry()
    registry.create_task(TASK_ID)
    before = registry.log.last_seq(TASK_ID)

    ledger = _ledger(tmp_path)
    _begin(ledger)
    _finalize(ledger)
    ledger.record_session_id(
        TASK_ID, SESSION_ID, DISPATCH_REF, ars_session_id=ARS_SESSION_ID
    )
    ledger.resolve(TASK_ID, SESSION_ID, DISPATCH_REF)
    ledger.resolve_pending(TASK_ID, SESSION_ID, DISPATCH_REF)
    ledger.resolve_for_task(TASK_ID)

    assert registry.log.last_seq(TASK_ID) == before
    with pytest.raises(AssertionError):
        registry.append_event(TASK_ID, {})

    # Structural: the module's CODE names no canonical-log surface at all —
    # walked as identifiers, so the boundary can still be stated in prose.
    from sachima_supervisor.runtime_spine import arsd_run_binding_ledger as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
        elif isinstance(node, ast.Import):
            referenced.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            referenced.add(node.module or "")
            referenced.update(alias.name for alias in node.names)
    for token in ("TaskEventLog", "TaskRegistry", "append_event", "build_event_body", "registry"):
        assert token not in referenced
