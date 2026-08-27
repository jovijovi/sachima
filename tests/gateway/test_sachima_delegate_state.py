"""S2 — durable delegate records, one atomic ledger snapshot, capacity, Session lookup.

What is proven here:

* ``ArsdRunBindingLedger.snapshot_exact`` is **one** whole observation: a
  ``finalize_accepted`` forced at exactly the old two-read race boundary yields
  either the intent or the acceptance and never a fabricated "neither", and the
  call reads the file once;
* a torn / corrupt ledger raises only the existing stable codes and leaves the
  damaged bytes on disk;
* composition hands the backend and the coordinator the **identical** ledger
  object, and never builds a second one;
* the durable store writes atomically to a private directory derived from the
  ledger's own path, survives a fresh process, refuses to rewrite a turn's
  identity, and fails closed with a stable code on damaged bytes — never a reset;
* capacity is one conservative permit per turn: reservation does not wait,
  admission does, and release is exactly once;
* the Gateway can resolve a Session by key as well as by id, so trusted context
  carries both.

Everything is pure local/offline: no adapter, socket, daemon, Session creation,
or AGENT. Forbidden terms in this prose are no-leak boundary canaries only,
never behavior.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from gateway.sachima_delegate_summary import (
    SUMMARY_REASON_SOURCE_EMPTY,
    DelegateResultSummary,
    compute_source_digest,
    pending_summary,
    ready_summary,
    unavailable_summary,
)
from gateway.sachima_delegate_state import (
    DELEGATE_STATE_VERSION,
    SACHIMA_DELEGATE_STATE_CONFLICT,
    SACHIMA_DELEGATE_STATE_INVALID,
    SACHIMA_DELEGATE_STATE_UNREADABLE,
    DelegateCapacity,
    DelegateOrigin,
    DelegateResultEvent,
    DelegateStateError,
    DelegateStateStore,
    DelegateTaskBinding,
    DelegateTurnRecord,
    delegate_state_root,
)
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import (
    ARSD_BINDING_ACCEPTED,
    ARSD_BINDING_PENDING,
    RUNTIME_INVALID_ARSD_BINDING,
    ArsdRunBindingLedger,
    derive_arsd_binding_key,
)
from sachima_supervisor.runtime_spine.arsd_socket_contract import derive_arsd_request_id
from sachima_supervisor.runtime_spine.events import SpineError

TASK_ID = "delegate_task_one"
HANDLE = "arsd_11223344"
DISPATCH = "dlg_" + "a" * 32
PAYLOAD_DIGEST = "sha256:" + "b" * 64


def _ledger(tmp_path: Path) -> ArsdRunBindingLedger:
    private = tmp_path / "private"
    private.mkdir(parents=True, exist_ok=True)
    return ArsdRunBindingLedger(str(private / "arsd-run-bindings.json"))


def _begin(ledger: ArsdRunBindingLedger):
    return ledger.begin_pending(
        TASK_ID,
        HANDLE,
        DISPATCH,
        request_id=derive_arsd_request_id(TASK_ID, HANDLE, DISPATCH),
        payload_digest=PAYLOAD_DIGEST,
        resolver_refs={"prompt_ref": DISPATCH},
    )


def _finalize(ledger: ArsdRunBindingLedger):
    return ledger.finalize_accepted(
        TASK_ID,
        HANDLE,
        DISPATCH,
        run_id="RUN-1",
        ars_session_id="ARSSESSION1",
        accepted_at="2026-08-19T04:05:06+00:00",
    )


# --------------------------------------------------------------------------- #
# A. The atomic exact-key snapshot (I2 / A7)
# --------------------------------------------------------------------------- #
def test_snapshot_exact_returns_the_pending_record_then_the_accepted_one(tmp_path):
    ledger = _ledger(tmp_path)
    assert ledger.snapshot_exact(TASK_ID, HANDLE, DISPATCH) is None

    _begin(ledger)
    pending = ledger.snapshot_exact(TASK_ID, HANDLE, DISPATCH)
    assert pending is not None and pending.state == ARSD_BINDING_PENDING
    assert pending.key == derive_arsd_binding_key(TASK_ID, HANDLE, DISPATCH)

    _finalize(ledger)
    accepted = ledger.snapshot_exact(TASK_ID, HANDLE, DISPATCH)
    assert accepted is not None and accepted.state == ARSD_BINDING_ACCEPTED
    assert accepted.run_ref is not None


def test_a_finalize_at_the_race_boundary_cannot_fabricate_a_third_state(tmp_path):
    """The old two-read classification had a window that reported neither.

    ``resolve_pending()`` then ``resolve()`` reads the file twice. A finalize
    landing between the two answers "not pending" to the first and — on a *fresh*
    read that the finalize has already changed — could answer inconsistently to
    the second. One read cannot: whatever it returns is a state that existed.
    """

    ledger = _ledger(tmp_path)
    _begin(ledger)

    original_read = ledger._read
    calls = {"n": 0}

    def _racing_read():
        calls["n"] += 1
        records = original_read()
        # Land the acceptance *while* the classification read is in flight.
        if calls["n"] == 1:
            ledger._read = original_read
            _finalize(ledger)
        return records

    ledger._read = _racing_read
    snapshot = ledger.snapshot_exact(TASK_ID, HANDLE, DISPATCH)
    ledger._read = original_read

    assert snapshot is not None
    assert snapshot.state in {ARSD_BINDING_PENDING, ARSD_BINDING_ACCEPTED}
    if snapshot.state == ARSD_BINDING_PENDING:
        assert snapshot.run_id is None and snapshot.run_ref is None
    else:
        assert snapshot.run_id is not None and snapshot.ars_session_id is not None


def test_snapshot_exact_reads_the_ledger_once(tmp_path):
    ledger = _ledger(tmp_path)
    _begin(ledger)
    original_read = ledger._read
    reads = {"n": 0}

    def _counted():
        reads["n"] += 1
        return original_read()

    ledger._read = _counted
    ledger.snapshot_exact(TASK_ID, HANDLE, DISPATCH)
    ledger._read = original_read
    assert reads["n"] == 1


def test_snapshot_exact_never_answers_about_another_key(tmp_path):
    ledger = _ledger(tmp_path)
    _begin(ledger)
    other = ledger.snapshot_exact(TASK_ID, HANDLE, "dlg_" + "c" * 32)
    assert other is None


def test_a_torn_ledger_is_a_stable_failure_with_its_bytes_left_alone(tmp_path):
    ledger = _ledger(tmp_path)
    _begin(ledger)
    damaged = b'{"type": "sachima.runtime_spine.arsd_run_binding_ledger.v1", "bind'
    Path(ledger.path).write_bytes(damaged)

    with pytest.raises(SpineError) as excinfo:
        ledger.snapshot_exact(TASK_ID, HANDLE, DISPATCH)
    assert excinfo.value.code == RUNTIME_INVALID_ARSD_BINDING
    assert Path(ledger.path).read_bytes() == damaged


# --------------------------------------------------------------------------- #
# B. One ledger object per composed graph (I2 / A7)
# --------------------------------------------------------------------------- #
def _config(tmp_path: Path, **overrides: Any):
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_SUPERVISOR_CONFIG_TYPE,
        ArsdSupervisorConfig,
    )

    private = tmp_path / "private"
    private.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {
        "type": ARSD_SUPERVISOR_CONFIG_TYPE,
        "approval_ref": "approval_delegate_offline",
        "owner": "sachima_host",
        "namespace": "sachima_tasks",
        "socket_path": str(private / "arsd.sock"),
        "binding_ledger_path": str(private / "arsd-run-bindings.json"),
        "agent_by_policy_ref": {"policy_author": "author-agent"},
        "model_by_policy_ref": {"policy_model": "claude-opus-5"},
        "effort_by_policy_ref": {"policy_effort": "xhigh"},
        "workspace_by_ref": {"ws_delegate": str(private / "workspace")},
        "run_limits_by_policy_ref": {
            "policy_limits": {
                "startup_timeout_seconds": 60.0,
                "turn_timeout_seconds": 600.0,
                "cancel_grace_seconds": 10.0,
                "max_stderr_bytes": 262_144,
                "max_event_bytes": 65_536,
                "max_events": 10_000,
            }
        },
        "grant_ref": "grant_author_v1",
        "grant_hash": "sha256:" + "a" * 64,
        "grant_role_hash": "sha256:" + "b" * 64,
        "grant_capabilities": ("read", "search"),
        "mcp_snapshot_hashes": ("sha256:" + "c" * 64,),
        "credential_refs": ("cred_author",),
        "evidence_policy_hash": "sha256:" + "d" * 64,
        "recovery_policy_hash": "sha256:" + "e" * 64,
        "enabled": True,
    }
    kwargs.update(overrides)
    return ArsdSupervisorConfig(**kwargs)


class _Facade:
    """The minimum daemon double a composition-time negotiation needs."""

    def server_info(self) -> dict[str, Any]:
        from sachima_supervisor.runtime_spine.arsd_socket_contract import (
            EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
        )

        return {
            "version": EXPECTED_AGENT_RUN_SUPERVISOR_VERSION,
            "api_version": 3,
            "supported_api_versions": [3],
            "operations": [
                "agent_list",
                "run_cancel",
                "run_events",
                "run_status",
                "server_info",
                "session_list",
                "session_status",
                "submit",
            ],
            "limits": {
                "max_concurrent_runs": 2,
                "max_frame_bytes": 1_048_576,
                "max_prompt_bytes": 262_144,
                "events_page_limit": 256,
                "event_follow_queue_size": 1024,
                "max_run_event_budget_bytes": 2_147_483_648,
            },
        }

    def submit(self, *, request_id: str, payload: Any) -> dict[str, Any]:
        raise AssertionError("composition must not submit")

    def run_status(self, run_id: str) -> dict[str, Any]:
        raise AssertionError("composition must not observe")

    def run_events(self, run_id: str, *, from_seq: int, limit: int | None = None):
        raise AssertionError("composition must not read events")

    def run_cancel(self, run_id: str) -> dict[str, Any]:
        raise AssertionError("composition must not cancel")

    def session_status(self, session_id: str) -> dict[str, Any]:
        raise AssertionError("composition must not inspect a Session")

    def session_list(self) -> dict[str, Any]:
        raise AssertionError("composition must not list Sessions")

    def agent_list(self) -> dict[str, Any]:
        raise AssertionError("composition must not read the roster")


def test_the_composed_bundle_exposes_the_one_ledger_the_backend_uses(tmp_path):
    from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
        bind_arsd_execution,
    )

    config = _config(tmp_path)
    ledger = ArsdRunBindingLedger(config.binding_ledger_path)
    bundle = bind_arsd_execution(config, facade=_Facade(), ledger=ledger)
    assert bundle.ledger is ledger
    assert bundle.backend._ledger is bundle.ledger


def test_a_bundle_composed_without_an_injected_ledger_builds_exactly_one(tmp_path):
    from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
        bind_arsd_execution,
    )

    config = _config(tmp_path)
    bundle = bind_arsd_execution(config, facade=_Facade())
    assert type(bundle.ledger) is ArsdRunBindingLedger
    assert bundle.backend._ledger is bundle.ledger
    assert bundle.ledger.path == config.binding_ledger_path


# --------------------------------------------------------------------------- #
# C. The durable store
# --------------------------------------------------------------------------- #
def _origin() -> DelegateOrigin:
    return DelegateOrigin(
        platform="feishu",
        chat_id="oc_chat",
        thread_id=None,
        session_key="feishu:oc_chat",
        session_id="20260819_000000_abcd1234",
    )


def _turn(store: DelegateStateStore, task_ref: str, payload_ref: str) -> DelegateTurnRecord:
    return DelegateTurnRecord(
        turn_key=store.new_turn_key(),
        task_ref=task_ref,
        task_id=TASK_ID,
        backend_handle=HANDLE,
        dispatch_ref=payload_ref,
        payload_ref=payload_ref,
        spine_session_id="sess_1",
        agent_id="oh-my-pi",
        launch_refs=("ws_delegate", "policy_author"),
        requested_agent="oh-my-pi",
        requested_model="claude-opus-5",
        requested_effort="xhigh",
        task_description="do the thing",
        accepted_at="2026-08-19T04:05:06+00:00",
        origin=_origin(),
    )


def test_the_state_root_is_derived_from_the_private_ledger_path(tmp_path):
    ledger_path = str(tmp_path / "private" / "arsd-run-bindings.json")
    assert delegate_state_root(ledger_path) == str(tmp_path / "private" / "delegate-state")
    with pytest.raises(DelegateStateError):
        delegate_state_root("relative/path.json")


def test_a_payload_survives_a_fresh_store_and_stays_private(tmp_path):
    root = str(tmp_path / "state")
    store = DelegateStateStore(root)
    text = "审计 the release notes and summarise"
    ref = store.put_payload(text)

    # A second store over the same root is what a restart looks like.
    assert DelegateStateStore(root).read_payload(ref) == text

    mode = stat.S_IMODE(os.stat(Path(root) / "payloads" / ref).st_mode)
    assert mode == 0o600
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700

    store.discard_payload(ref)
    with pytest.raises(DelegateStateError) as excinfo:
        store.read_payload(ref)
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_INVALID
    # Discarding twice is not an error: both cleanup paths can reach it.
    store.discard_payload(ref)


def test_an_unknown_or_malformed_payload_ref_never_echoes_itself(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    store.put_payload("private canary body")
    for bad in ["dlg_missing", "", "   ", "../escape", None, 7]:
        with pytest.raises(DelegateStateError) as excinfo:
            store.read_payload(bad)
        message = str(excinfo.value)
        assert message in {
            SACHIMA_DELEGATE_STATE_INVALID,
            SACHIMA_DELEGATE_STATE_UNREADABLE,
        }
        assert "canary" not in message


def test_task_turn_and_result_records_round_trip_through_a_fresh_store(tmp_path):
    root = str(tmp_path / "state")
    store = DelegateStateStore(root)
    payload_ref = store.put_payload("do the thing")
    task_ref = store.new_task_ref()
    turn = _turn(store, task_ref, payload_ref)
    store.put_turn(turn)
    binding = DelegateTaskBinding(
        task_ref=task_ref,
        task_id=TASK_ID,
        backend_handle=HANDLE,
        spine_session_id="sess_1",
        agent_id="oh-my-pi",
        origin=_origin(),
        turn_keys=(turn.turn_key,),
        current_turn_key=turn.turn_key,
    )
    store.put_task(binding)

    fresh = DelegateStateStore(root)
    assert fresh.read_task(task_ref) == binding
    assert fresh.read_turn(turn.turn_key) == turn
    assert fresh.read_turn(turn.turn_key).task_description == "do the thing"
    assert fresh.read_turn(turn.turn_key).accepted_at == "2026-08-19T04:05:06+00:00"
    assert fresh.read_turn(turn.turn_key).ledger_key == (TASK_ID, HANDLE, payload_ref)
    assert [record.turn_key for record in fresh.list_turns()] == [turn.turn_key]

    full_ref, clipped = fresh.put_full_result("the whole answer")
    assert clipped is False
    event = DelegateResultEvent(
        event_id=fresh.new_event_id(),
        turn_key=turn.turn_key,
        task_ref=task_ref,
        session_id=_origin().session_id,
        terminal="completed",
        full_result_ref=full_ref,
        terminal_at="2026-08-19T05:06:07+00:00",
    )
    fresh.put_result(event)
    assert DelegateStateStore(root).result_for_turn(turn.turn_key) == event
    assert DelegateStateStore(root).read_full_result(full_ref) == "the whole answer"


def test_a_turn_can_have_only_one_canonical_result_identity(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    payload_ref = store.put_payload("do the thing")
    task_ref = store.new_task_ref()
    turn = store.put_turn(_turn(store, task_ref, payload_ref))
    full_ref, _ = store.put_full_result("first answer")
    canonical = DelegateResultEvent(
        event_id=store.new_event_id(),
        turn_key=turn.turn_key,
        task_ref=task_ref,
        session_id=_origin().session_id,
        terminal="completed",
        full_result_ref=full_ref,
    )
    store.put_result(canonical)

    other_ref, _ = store.put_full_result("second answer")
    duplicate = DelegateResultEvent(
        event_id=store.new_event_id(),
        turn_key=turn.turn_key,
        task_ref=task_ref,
        session_id=_origin().session_id,
        terminal="failed",
        full_result_ref=other_ref,
    )
    with pytest.raises(DelegateStateError) as excinfo:
        store.put_result(duplicate)

    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_CONFLICT
    assert store.result_for_turn(turn.turn_key) == canonical
    assert store.list_results() == (canonical,)


def test_a_turns_identity_cannot_be_rewritten_by_an_update(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    payload_ref = store.put_payload("do the thing")
    turn = store.put_turn(_turn(store, store.new_task_ref(), payload_ref))

    updated = store.update_turn(turn.turn_key, lifecycle="admitted", receipt="confirmed")
    assert updated.lifecycle == "admitted" and updated.receipt == "confirmed"
    assert updated.ledger_key == turn.ledger_key

    with pytest.raises(DelegateStateError) as excinfo:
        store.update_turn(turn.turn_key, dispatch_ref="dlg_" + "f" * 32)
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_CONFLICT
    assert store.read_turn(turn.turn_key).ledger_key == turn.ledger_key


def test_a_damaged_record_is_a_stable_failure_that_keeps_its_bytes(tmp_path):
    root = str(tmp_path / "state")
    store = DelegateStateStore(root)
    payload_ref = store.put_payload("do the thing")
    turn = store.put_turn(_turn(store, store.new_task_ref(), payload_ref))

    damaged = b'{"version": 1, "kind": "turn", "record": {"turn_key"'
    (Path(root) / "turns" / turn.turn_key).write_bytes(damaged)
    with pytest.raises(DelegateStateError) as excinfo:
        store.read_turn(turn.turn_key)
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_UNREADABLE
    assert (Path(root) / "turns" / turn.turn_key).read_bytes() == damaged


def test_a_write_leaves_no_partial_file_behind(tmp_path):
    root = str(tmp_path / "state")
    store = DelegateStateStore(root)
    payload_ref = store.put_payload("do the thing")
    store.put_turn(_turn(store, store.new_task_ref(), payload_ref))
    assert list(Path(root).glob("**/*.tmp")) == []


def test_only_the_sanitized_display_description_reaches_the_turn_record(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    canary = "the private\n\tdelegate canary body"
    payload_ref = store.put_payload(canary)
    turn = store.put_turn(_turn(store, store.new_task_ref(), payload_ref))
    assert canary not in json.dumps(turn.as_dict())
    assert canary not in repr(turn)
    assert turn.task_description == "do the thing"
    assert store.read_payload(payload_ref) == canary


# --------------------------------------------------------------------------- #
# D. Capacity (I7 / A15)
# --------------------------------------------------------------------------- #
def test_reservation_does_not_wait_but_admission_does():
    capacity = DelegateCapacity(1)
    capacity.reserve("dturn_" + "a" * 32)
    assert capacity.held() == 1
    assert capacity.would_wait() is True

    async def _drive():
        admitted = asyncio.create_task(capacity.acquire("dturn_" + "b" * 32))
        await asyncio.sleep(0.01)
        assert not admitted.done()
        capacity.release("dturn_" + "a" * 32)
        await asyncio.wait_for(admitted, timeout=2)
        assert capacity.holds("dturn_" + "b" * 32)

    asyncio.run(_drive())


def test_a_permit_is_released_exactly_once():
    capacity = DelegateCapacity(2)
    key = "dturn_" + "c" * 32
    capacity.reserve(key)
    assert capacity.release(key) is True
    # The second release is a no-op, not a second free slot.
    assert capacity.release(key) is False
    assert capacity.held() == 0


def test_reserving_the_same_turn_twice_holds_one_permit():
    capacity = DelegateCapacity(2)
    key = "dturn_" + "d" * 32
    capacity.reserve(key)
    capacity.reserve(key)
    assert capacity.held() == 1


# --------------------------------------------------------------------------- #
# E. Trusted Session resolution (A5)
# --------------------------------------------------------------------------- #
def test_the_session_store_resolves_a_session_by_key_as_well_as_by_id(tmp_path):
    from gateway.config import GatewayConfig, Platform
    from gateway.session import SessionSource, SessionStore

    store = SessionStore(tmp_path / "sessions", GatewayConfig())
    source = SessionSource(
        platform=Platform.FEISHU, chat_id="oc_chat", chat_type="group", user_id="ou_a"
    )
    entry = store.get_or_create_session(source)

    assert store.lookup_by_session_key(entry.session_key) is entry
    assert store.lookup_by_session_id(entry.session_id) is entry
    assert store.lookup_by_session_key("no-such-key") is None
    assert store.lookup_by_session_key("") is None


# --------------------------------------------------------------------------- #
# Pre-rename durable records
#
# The sealed AGENT used to be written under ``profile_id``, whose grammar had
# no room for a canonical id like ``oh-my-pi``. The field is now ``agent_id``
# with the canonical grammar — a strict superset of every value the old one
# could hold — so an existing record is *read*, not migrated. Whether that
# AGENT is still eligible is a separate question, asked only when a new Run
# would be submitted.
# --------------------------------------------------------------------------- #
def _legacy_document(kind: str, record: dict) -> bytes:
    return json.dumps(
        {"version": DELEGATE_STATE_VERSION, "kind": kind, "record": record},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")


def test_a_record_written_before_the_rename_is_still_readable(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    root = Path(store.root)
    task_ref = store.new_task_ref()
    turn_key = store.new_turn_key()
    origin = _origin().as_dict()

    (root / "turns" / turn_key).write_bytes(
        _legacy_document(
            "turn",
            {
                "turn_key": turn_key,
                "task_ref": task_ref,
                "task_id": TASK_ID,
                "backend_handle": HANDLE,
                "dispatch_ref": "dlg_legacy",
                "payload_ref": "dlg_legacy",
                "spine_session_id": "sess_1",
                "profile_id": "default",
                "launch_refs": ["ws_delegate", "policy_author"],
                "requested_agent": "author-agent",
                "requested_model": "claude-opus-5",
                "requested_effort": "xhigh",
                "origin": origin,
                "lifecycle": "terminal",
                "cancellation": "none",
                "receipt": "confirmed",
                "observation": "terminal_seen",
                "turn_ref": None,
                "receipt_message_id": None,
                "diagnostic": None,
                "terminal_status": "completed",
            },
        )
    )
    (root / "tasks" / task_ref).write_bytes(
        _legacy_document(
            "task",
            {
                "task_ref": task_ref,
                "task_id": TASK_ID,
                "backend_handle": HANDLE,
                "spine_session_id": "sess_1",
                "profile_id": "default",
                "origin": origin,
                "turn_keys": [turn_key],
                "current_turn_key": turn_key,
                "terminal": True,
                "linked_from": None,
            },
        )
    )

    fresh = DelegateStateStore(str(tmp_path / "state"))
    binding = fresh.read_task(task_ref)
    turn = fresh.read_turn(turn_key)

    assert binding is not None and turn is not None
    assert binding.agent_id == "default"
    assert turn.agent_id == "default"
    assert binding.turn_keys == (turn_key,)
    assert turn.terminal_status == "completed"

    # Rewritten under the current key, with no second copy of the old one.
    fresh.put_task(binding)
    document = json.loads((root / "tasks" / task_ref).read_text(encoding="utf-8"))
    assert document["record"]["agent_id"] == "default"
    assert "profile_id" not in document["record"]


def test_a_canonical_id_the_old_ref_grammar_refused_is_now_durable(tmp_path):
    """``oh-my-pi`` is a real registered id, and hyphens are part of it."""

    store = DelegateStateStore(str(tmp_path / "state"))
    payload_ref = store.put_payload("do the thing")
    task_ref = store.new_task_ref()
    turn = store.put_turn(_turn(store, task_ref, payload_ref))
    assert store.read_turn(turn.turn_key).agent_id == "oh-my-pi"


# --------------------------------------------------------------------------- #
# E. The durable derived summary (S1)
# --------------------------------------------------------------------------- #
SOURCE_ANSWER_CANARY = "外部 AGENT 的完整原文 with the conclusion at the very end."
SUMMARY_TEXT_CANARY = "结论：可以合并；证据：受影响测试全绿。"


def _seeded_result(store: DelegateStateStore, *, answer: str = SOURCE_ANSWER_CANARY):
    """One durable terminal result, with its stored answer, ready to summarize."""

    payload_ref = store.put_payload("do the thing")
    task_ref = store.new_task_ref()
    turn = store.put_turn(_turn(store, task_ref, payload_ref))
    full_ref, _clipped = store.put_full_result(answer)
    event = store.put_result(
        DelegateResultEvent(
            event_id=store.new_event_id(),
            turn_key=turn.turn_key,
            task_ref=task_ref,
            session_id=_origin().session_id,
            terminal="completed",
            full_result_ref=full_ref,
        )
    )
    return event, full_ref


def test_a_summary_record_survives_a_fresh_store_and_is_found_by_its_result(tmp_path):
    root = str(tmp_path / "state")
    store = DelegateStateStore(root)
    event, full_ref = _seeded_result(store)
    digest = compute_source_digest(SOURCE_ANSWER_CANARY)

    pending = store.put_summary(
        pending_summary(
            event_id=event.event_id, full_result_ref=full_ref, source_digest=digest
        )
    )
    assert pending.summary_status == "pending"
    assert DelegateStateStore(root).summary_for_event(event.event_id) == pending

    claimed = store.claim_summary_attempt(pending.summary_ref)
    assert claimed.summary_status == "in_flight"
    settled = store.advance_summary(
        ready_summary(claimed, summary_text=SUMMARY_TEXT_CANARY, generator_ref="stub")
    )

    fresh = DelegateStateStore(root)
    restored = fresh.summary_for_event(event.event_id)
    assert restored == settled
    assert restored.summary_text == SUMMARY_TEXT_CANARY
    assert restored.source_digest == digest
    assert fresh.read_summary(pending.summary_ref) == settled
    assert [record.summary_ref for record in fresh.list_summaries()] == [
        pending.summary_ref
    ]


def test_one_result_identity_can_only_have_one_terminal_summary(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    event, full_ref = _seeded_result(store)
    digest = compute_source_digest(SOURCE_ANSWER_CANARY)
    pending = store.put_summary(
        pending_summary(
            event_id=event.event_id, full_result_ref=full_ref, source_digest=digest
        )
    )
    claimed = store.claim_summary_attempt(pending.summary_ref)
    settled = store.advance_summary(
        ready_summary(claimed, summary_text=SUMMARY_TEXT_CANARY)
    )

    # A second attempt cannot be claimed, and neither terminal can be rewritten.
    assert store.claim_summary_attempt(pending.summary_ref) is None
    with pytest.raises(DelegateStateError) as excinfo:
        store.advance_summary(
            DelegateResultSummary(
                summary_status="ready",
                summary_ref=pending.summary_ref,
                source_full_result_ref=full_ref,
                source_digest=digest,
                summary_text="a different reading of the same answer",
            )
        )
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_CONFLICT
    assert store.summary_for_event(event.event_id) == settled

    # Re-writing the identical terminal record is idempotent, not a conflict.
    assert store.advance_summary(settled) == settled


def test_a_summary_write_refuses_a_source_that_drifted(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    event, full_ref = _seeded_result(store)
    digest = compute_source_digest(SOURCE_ANSWER_CANARY)
    pending = store.put_summary(
        pending_summary(
            event_id=event.event_id, full_result_ref=full_ref, source_digest=digest
        )
    )
    claimed = store.claim_summary_attempt(pending.summary_ref)

    drifted_digest = replace(
        ready_summary(claimed, summary_text=SUMMARY_TEXT_CANARY),
        source_digest=compute_source_digest(SOURCE_ANSWER_CANARY + " drifted"),
    )
    drifted_ref = replace(
        ready_summary(claimed, summary_text=SUMMARY_TEXT_CANARY),
        source_full_result_ref="dres_" + "f" * 16,
    )
    for drifted in (drifted_digest, drifted_ref):
        with pytest.raises(DelegateStateError) as excinfo:
            store.advance_summary(drifted)
        assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_CONFLICT
    assert store.summary_for_event(event.event_id).summary_status == "in_flight"


def test_a_second_pending_summary_for_one_result_is_a_conflict(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    event, full_ref = _seeded_result(store)
    digest = compute_source_digest(SOURCE_ANSWER_CANARY)
    first = pending_summary(
        event_id=event.event_id, full_result_ref=full_ref, source_digest=digest
    )
    store.put_summary(first)
    # The identical record replays; a different binding under the same slot does
    # not.
    assert store.put_summary(first) == first
    with pytest.raises(DelegateStateError) as excinfo:
        store.put_summary(
            pending_summary(
                event_id=event.event_id,
                full_result_ref=full_ref,
                source_digest=compute_source_digest("something else entirely"),
            )
        )
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_CONFLICT


def test_advancing_a_summary_that_was_never_persisted_is_a_conflict(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    event, full_ref = _seeded_result(store)
    orphan = pending_summary(
        event_id=event.event_id,
        full_result_ref=full_ref,
        source_digest=compute_source_digest(SOURCE_ANSWER_CANARY),
    )
    with pytest.raises(DelegateStateError):
        store.advance_summary(
            unavailable_summary(orphan, reason=SUMMARY_REASON_SOURCE_EMPTY)
        )
    assert store.claim_summary_attempt(orphan.summary_ref) is None
    assert store.summary_for_event(event.event_id) is None


def test_a_damaged_or_widened_summary_record_fails_closed_and_keeps_its_bytes(tmp_path):
    root = str(tmp_path / "state")
    store = DelegateStateStore(root)
    event, full_ref = _seeded_result(store)
    pending = store.put_summary(
        pending_summary(
            event_id=event.event_id,
            full_result_ref=full_ref,
            source_digest=compute_source_digest(SOURCE_ANSWER_CANARY),
        )
    )
    path = Path(root) / "summaries" / (pending.summary_ref + ".json")

    widened = json.loads(path.read_text(encoding="utf-8"))
    widened["record"]["raw_provider_response"] = "the provider's whole reply"
    path.write_text(json.dumps(widened), encoding="utf-8")
    with pytest.raises(DelegateStateError) as excinfo:
        store.read_summary(pending.summary_ref)
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_UNREADABLE

    damaged = b'{"version": 1, "kind": "summary", "record": {"summary_status"'
    path.write_bytes(damaged)
    with pytest.raises(DelegateStateError) as excinfo:
        store.read_summary(pending.summary_ref)
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_UNREADABLE
    assert path.read_bytes() == damaged


def test_the_stored_summary_never_carries_the_source_answer(tmp_path):
    root = str(tmp_path / "state")
    store = DelegateStateStore(root)
    event, full_ref = _seeded_result(store)
    pending = store.put_summary(
        pending_summary(
            event_id=event.event_id,
            full_result_ref=full_ref,
            source_digest=compute_source_digest(SOURCE_ANSWER_CANARY),
        )
    )
    claimed = store.claim_summary_attempt(pending.summary_ref)
    settled = store.advance_summary(
        ready_summary(claimed, summary_text=SUMMARY_TEXT_CANARY)
    )
    serialized = (Path(root) / "summaries" / (settled.summary_ref + ".json")).read_text(
        encoding="utf-8"
    )
    assert SOURCE_ANSWER_CANARY not in serialized
    assert SUMMARY_TEXT_CANARY not in repr(settled)
    assert stat.S_IMODE(
        os.stat(Path(root) / "summaries" / (settled.summary_ref + ".json")).st_mode
    ) == 0o600
    # The original is still exactly where it was.
    assert store.read_full_result(full_ref) == SOURCE_ANSWER_CANARY


# --------------------------------------------------------------------------- #
# S1 — the durable Task-card projection
#
# The store is the atomic, private home of the card projection; the card module
# owns its invariants. What is proven here is that the two hold together across
# a fresh process: one card record per Task, an immutable creation boundary,
# stable append-only round numbering, revision monotonicity, a sealed origin,
# and no raw material on disk.
# --------------------------------------------------------------------------- #
CARD_TASK_REF = "dtask_" + "ab12cd34" * 4
CARD_CREATED_AT = "2026-08-26T09:00:00+00:00"


def _card_projection(**overrides):
    from gateway.sachima_delegate_card import new_card_projection

    base = dict(
        task_ref=CARD_TASK_REF,
        task_created_at=CARD_CREATED_AT,
        origin_platform="feishu",
        origin_chat_id="oc_private_chat",
        origin_session_id="sess_1",
        agent_id="oh-my-pi",
        model="glm-5.3",
        effort="max",
        task_description="验证 Session 复用",
    )
    base.update(overrides)
    return new_card_projection(**base)


def test_a_card_projection_survives_a_fresh_store(tmp_path):
    from gateway.sachima_delegate_card import advance_round, append_round

    root = str(tmp_path / "state")
    store = DelegateStateStore(root)
    projection = append_round(
        _card_projection(), turn_key="dturn_one", purpose="建立 Session 上下文"
    )
    projection = advance_round(
        projection,
        "dturn_one",
        status="completed",
        session_projection="new",
        result_summary="上下文已建立",
        settled_at="2026-08-26T09:00:40+00:00",
    )
    store.put_card(projection)

    fresh = DelegateStateStore(root)
    restored = fresh.read_card(CARD_TASK_REF)
    assert restored == projection
    assert fresh.list_cards() == (projection,)


def test_a_card_record_is_create_only_and_replays_identically(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    projection = _card_projection()
    store.put_card(projection)
    assert store.put_card(projection) == projection

    from dataclasses import replace as _replace

    with pytest.raises(DelegateStateError) as excinfo:
        store.put_card(_replace(projection, pre_accept_status="waiting"))
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_CONFLICT


def _forward(projection, **changes):
    """One card state moved forward: the changes, at the next revision."""

    from dataclasses import replace as _replace

    from gateway.sachima_delegate_card import next_projection_revision

    return next_projection_revision(_replace(projection, **changes))


def test_advancing_a_card_keeps_the_creation_boundary_and_the_origin(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    projection = store.put_card(_card_projection())
    moved = store.advance_card(_forward(projection, pre_accept_status="waiting"))
    assert moved.pre_accept_status == "waiting"
    assert moved.task_created_at == CARD_CREATED_AT

    # The immutable creation boundary cannot be rewritten under the same Task.
    with pytest.raises(DelegateStateError) as excinfo:
        store.advance_card(
            _forward(moved, task_created_at="2026-08-26T10:00:00+00:00")
        )
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_CONFLICT

    # Neither can the sealed origin: a restored Task cannot move conversations.
    with pytest.raises(DelegateStateError):
        store.advance_card(_forward(moved, origin_chat_id="oc_other_chat"))


def test_conflicting_card_state_at_an_equal_revision_never_overwrites(tmp_path):
    """Monotonic means *strictly* forward: an equal revision is not a licence.

    Two writers that read the same projection compute two different next states.
    Letting the later write win merely because its revision is not *smaller* is
    how an already-projected card state is silently replaced by another writer's
    view of it, so only the exact same record replays.
    """

    from dataclasses import replace as _replace

    store = DelegateStateStore(str(tmp_path / "state"))
    projection = store.put_card(_card_projection())
    moved = store.advance_card(_forward(projection, pre_accept_status="waiting"))

    # An exact duplicate of the accepted projection is a no-op, not a conflict.
    assert store.advance_card(moved) == moved

    with pytest.raises(DelegateStateError) as excinfo:
        store.advance_card(_replace(moved, pre_accept_status="submitting"))
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_CONFLICT
    assert store.read_card(CARD_TASK_REF) == moved


def test_a_card_revision_never_moves_backwards(tmp_path):
    from dataclasses import replace as _replace

    store = DelegateStateStore(str(tmp_path / "state"))
    from gateway.sachima_delegate_card import projected_revision

    projection = store.put_card(_card_projection())
    second = store.advance_card(
        projected_revision(projection, at="2026-08-26T09:00:10+00:00")
    )
    third = store.advance_card(
        projected_revision(second, at="2026-08-26T09:00:20+00:00")
    )
    assert third.revision == 2

    stale = _replace(third, revision=1, pre_accept_status="waiting")
    with pytest.raises(DelegateStateError) as excinfo:
        store.advance_card(stale)
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_CONFLICT
    # The newer state is still exactly what is on disk.
    assert store.read_card(CARD_TASK_REF).revision == 2


def test_advancing_a_card_that_was_never_persisted_is_a_conflict(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    with pytest.raises(DelegateStateError) as excinfo:
        store.advance_card(_card_projection())
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_CONFLICT


def test_a_damaged_card_record_fails_closed_and_keeps_its_bytes(tmp_path):
    root = str(tmp_path / "state")
    store = DelegateStateStore(root)
    store.put_card(_card_projection())
    path = Path(root) / "cards" / (CARD_TASK_REF + ".json")
    damaged = b'{"version": 1, "kind": "card", "record": {"task_ref"'
    path.write_bytes(damaged)
    with pytest.raises(DelegateStateError) as excinfo:
        store.read_card(CARD_TASK_REF)
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_UNREADABLE
    assert path.read_bytes() == damaged

    widened = {
        "version": DELEGATE_STATE_VERSION,
        "kind": "card",
        "record": {**_card_projection().as_dict(), "raw_card_json": "{...}"},
    }
    path.write_text(json.dumps(widened), encoding="utf-8")
    with pytest.raises(DelegateStateError):
        store.read_card(CARD_TASK_REF)


def test_the_stored_card_carries_no_raw_material_and_stays_private(tmp_path):
    from gateway.sachima_delegate_card import advance_round, append_round

    root = str(tmp_path / "state")
    store = DelegateStateStore(root)
    projection = append_round(_card_projection(), turn_key="dturn_one", purpose="第一步")
    projection = advance_round(
        projection, "dturn_one", status="running", run_ref="run_ab12cd34"
    )
    store.put_card(projection)
    path = Path(root) / "cards" / (CARD_TASK_REF + ".json")
    serialized = path.read_text(encoding="utf-8")
    for forbidden in ("dres_", "dlg_", "wide_screen_mode", "elements"):
        assert forbidden not in serialized
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_a_card_lookup_never_echoes_a_malformed_task_ref(tmp_path):
    store = DelegateStateStore(str(tmp_path / "state"))
    with pytest.raises(DelegateStateError) as excinfo:
        store.read_card("../../etc/passwd")
    assert str(excinfo.value) == SACHIMA_DELEGATE_STATE_INVALID
    assert store.read_card("dtask_" + "00" * 8) is None
