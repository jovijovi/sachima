"""One logical conversation survives compression; nothing else inherits it.

Context compression ends the live Session and forks a continuation child with a
fresh physical ``session_id``. Everything Sachima binds to a conversation —
the ``dtask_*`` control grant and the not-yet-claimed result owed to the next
ordinary turn — was keyed on that physical id, so a compression split silently
cut the user off from their own delegated task.

What is proven here:

* the continuation edge is proven **per hop** from persisted Session lineage
  (parent ``end_reason='compression'`` + child started at/after the parent
  ended), so ``/new``, reset, ``/branch``, and delegate subagents — all of which
  can also carry a ``parent_session_id`` — inherit nothing;
* every control action (``status``/``result``/``cancel``/``recover``/
  ``continue``, including the AGENT switch) answers in the compression child,
  after one compression and after several;
* the reachable ``sachima_delegate_control_no_session`` window — the agent
  worker has rotated the contextvar, the Gateway's ``SessionStore`` still names
  the parent — resolves from that same persisted lineage rather than from a
  key-only pass, a retry, or a process-global fallback;
* a parent-bound, unclaimed settled result completes
  pending → in_flight → confirmed (and → pending again when interrupted) for the
  compression child, through the Gateway's own turn seams;
* the original physical ``session_id`` is never rewritten — old records stay
  exactly as persisted and stay controllable.

Everything is offline: no socket, no daemon, no adapter connection, no AGENT.
The Session lineage is written with the *production* calls the compression owner
makes (``SessionDB.end_session`` / ``create_session`` /
``set_current_session_id``), and every permission and re-injection assertion
goes through the real control tool or the real Gateway seam.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

import gateway.sachima_delegate as delegate_mod
import hermes_state
import tools.sachima_delegate_control_tool as control_mod
from tests.gateway.test_sachima_delegate_coordinator import (
    CARD_TITLE_CANARY,
    TASK_TEXT_CANARY,
    _catalog,
    _config,
)
from tests.gateway.test_sachima_delegate_gateway import (
    GATEWAY_SUMMARY_CANARY,
    _adapter_delivery,
    _await_composed,
    _bind,
    _Host,
    _source,
    _summary_is_settled,
    _until,
)

AGENT_ID = "codex"


# --------------------------------------------------------------------------- #
# The persisted lineage, written exactly the way the compression owner writes it
# --------------------------------------------------------------------------- #
def _new_session_id() -> str:
    """The id shape ``agent/conversation_compression.py`` mints on rotation."""

    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def _compress(db, *, parent_id: str, source: str = "telegram") -> str:
    """End *parent_id* by compression and fork its continuation child.

    The two durable writes are the compression owner's own
    (``end_session(..., "compression")`` then ``create_session(...,
    parent_session_id=...)``), in that order — the ordering *is* the
    discriminator, because a child that starts before its parent ended is a
    subagent or a branch, not a continuation.
    """

    db.end_session(parent_id, "compression")
    child_id = _new_session_id()
    db.create_session(
        session_id=child_id, source=source, parent_session_id=parent_id
    )
    return child_id


def _branch(db, *, parent_id: str, source: str = "telegram") -> str:
    """A ``/branch`` child: same parent link, ``branched`` end reason."""

    db.end_session(parent_id, "branched")
    child_id = _new_session_id()
    db.create_session(
        session_id=child_id, source=source, parent_session_id=parent_id
    )
    return child_id


def _branch_in_the_window(db, *, parent_id: str, source: str = "telegram") -> str:
    """A ``/branch`` taken while the parent is *already* compression-ended.

    ``/branch`` links to ``session_store``'s current entry, and this fix's own
    window is the one where that entry still names the session compression has
    already ended (likewise after a restart between the two writes). The child
    is then born with the ``_branched_from`` marker, a parent whose
    ``end_reason`` is ``'compression'``, and a later ``started_at`` — the exact
    three facts the continuation edge looks for. It is still a branch, and a
    branch inherits nothing.
    """

    db.end_session(parent_id, "compression")
    child_id = _new_session_id()
    db.create_session(
        session_id=child_id,
        source=source,
        parent_session_id=parent_id,
        model_config={"_branched_from": parent_id},
    )
    return child_id


def _subagent(db, *, parent_id: str, source: str = "telegram") -> str:
    """A delegate subagent run: parent link, but the parent is still live."""

    child_id = _new_session_id()
    db.create_session(
        session_id=child_id, source=source, parent_session_id=parent_id
    )
    return child_id


@pytest.fixture
def lineage(tmp_path, monkeypatch):
    """One state.db, pinned, shared by the test and by every ``SessionStore``.

    ``DEFAULT_DB_PATH`` is a module constant resolved at import, so pinning it
    is what keeps ``SessionStore``'s own ``SessionDB()`` on this file.
    """

    db_path = tmp_path / "state.db"
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", db_path)
    db = hermes_state.SessionDB(db_path)
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# A. The edge itself: one rule, proven hop by hop from persisted lineage
# --------------------------------------------------------------------------- #
def test_a_compression_child_continues_its_parent(lineage) -> None:
    lineage.create_session(session_id="root", source="telegram")
    child = _compress(lineage, parent_id="root")

    assert lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id=child
    )


def test_a_multi_hop_chain_still_continues_the_root(lineage) -> None:
    lineage.create_session(session_id="root", source="telegram")
    first = _compress(lineage, parent_id="root")
    second = _compress(lineage, parent_id=first)
    third = _compress(lineage, parent_id=second)

    assert lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id=third
    )
    assert lineage.is_compression_continuation(
        ancestor_session_id=first, descendant_session_id=third
    )


def test_the_edge_is_forward_only(lineage) -> None:
    """A parent never inherits its own continuation's conversation."""

    lineage.create_session(session_id="root", source="telegram")
    child = _compress(lineage, parent_id="root")

    assert not lineage.is_compression_continuation(
        ancestor_session_id=child, descendant_session_id="root"
    )
    assert not lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id="root"
    )


def test_a_branch_child_never_continues_its_parent(lineage) -> None:
    lineage.create_session(session_id="root", source="telegram")
    branched = _branch(lineage, parent_id="root")

    assert not lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id=branched
    )


def test_a_branch_off_a_compressed_parent_never_continues_it(lineage) -> None:
    """A branch is a branch even when its parent was ended by compression.

    The continuation edge alone cannot tell these apart — the parent really did
    end with ``end_reason='compression'`` and the child really did start after
    it. The ``_branched_from`` marker is what distinguishes them, and the
    permission-grade answer has to honour it or ``/branch`` inherits the
    conversation's delegated tasks.
    """

    lineage.create_session(session_id="root", source="telegram")
    branched = _branch_in_the_window(lineage, parent_id="root")

    assert not lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id=branched
    )


def test_a_branch_in_the_window_does_not_break_a_real_continuation(lineage) -> None:
    """Excluding branches must not cost the continuation its own chain."""

    lineage.create_session(session_id="root", source="telegram")
    tip = _compress(lineage, parent_id="root")
    sibling = _new_session_id()
    lineage.create_session(
        session_id=sibling,
        source="telegram",
        parent_session_id="root",
        model_config={"_branched_from": "root"},
    )

    assert lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id=tip
    )
    assert not lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id=sibling
    )


def test_a_subagent_child_never_continues_its_parent(lineage) -> None:
    lineage.create_session(session_id="root", source="telegram")
    sub = _subagent(lineage, parent_id="root")
    # The parent ends later, by compression — the subagent still started first,
    # which is exactly the case a naive descendant walk would get wrong.
    lineage.end_session("root", "compression")

    assert not lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id=sub
    )


def test_a_reset_successor_never_continues_the_session_it_replaced(lineage) -> None:
    """``/new`` and auto-reset mint an unrelated root: no parent link at all."""

    lineage.create_session(session_id="root", source="telegram")
    lineage.end_session("root", "session_reset")
    lineage.create_session(session_id="fresh", source="telegram")

    assert not lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id="fresh"
    )


def test_a_broken_hop_stops_the_chain(lineage) -> None:
    """Every hop must hold: one branch hop mid-chain cuts the continuation."""

    lineage.create_session(session_id="root", source="telegram")
    branched = _branch(lineage, parent_id="root")
    tip = _compress(lineage, parent_id=branched)

    assert lineage.is_compression_continuation(
        ancestor_session_id=branched, descendant_session_id=tip
    )
    assert not lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id=tip
    )


def test_an_unknown_or_empty_session_never_continues_anything(lineage) -> None:
    lineage.create_session(session_id="root", source="telegram")

    assert not lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id="never_persisted"
    )
    assert not lineage.is_compression_continuation(
        ancestor_session_id="", descendant_session_id="root"
    )
    assert not lineage.is_compression_continuation(
        ancestor_session_id="root", descendant_session_id=""
    )


# --------------------------------------------------------------------------- #
# The real control surface, over a real Gateway ``SessionStore``
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _isolate():
    """No coordinator, no bound store, and no leaked process-global id."""

    delegate_mod.unbind_delegate_coordinator()
    try:
        yield
    finally:
        delegate_mod.unbind_delegate_coordinator()
        control_mod.bind_delegate_control_session_store(None)
        os.environ.pop("HERMES_SESSION_ID", None)


async def _workbench(tmp_path, monkeypatch, *agent_ids: str):
    """The host seams a control action really crosses: gate, store, coordinator."""

    agent_ids = agent_ids or (AGENT_ID,)
    monkeypatch.setenv(control_mod.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    config = _config(
        tmp_path,
        agent_by_policy_ref={f"policy_{name}": name for name in agent_ids},
        model_by_policy_ref={"policy_model": "claude-opus-5"},
        effort_by_policy_ref={"policy_effort": "xhigh"},
    )
    runner = _Host(tmp_path)
    coordinator, facade = _bind(
        tmp_path, config=config, presets=_catalog(config, *agent_ids)
    )
    coordinator.bind_lifecycle_loop(asyncio.get_running_loop())
    await coordinator.restore()
    coordinator._delivery_factory = _adapter_delivery(runner)
    control_mod.bind_delegate_control_session_store(runner.host.session_store)
    return SimpleNamespace(
        runner=runner,
        store=runner.host.session_store,
        coordinator=coordinator,
        facade=facade,
        config=config,
    )


class _Turn:
    """One ordinary turn's trusted Gateway context, exactly as the runner sets it.

    The turn opens on the Session the store currently holds, which is what
    ``_handle_message_with_agent`` does. ``rotate`` is the only way the Session
    moves inside it, because that is the only way it moves in production.
    """

    def __init__(self, entry, *, message_id: str = "m-1"):
        self._entry = entry
        self._message_id = message_id
        self._tokens: list = []

    def __enter__(self):
        from gateway.session_context import set_session_vars

        origin = self._entry.origin
        self._tokens = set_session_vars(
            platform=origin.platform.value,
            chat_id=str(origin.chat_id),
            user_id=str(origin.user_id or ""),
            session_key=self._entry.session_key,
            session_id=self._entry.session_id,
            message_id=self._message_id,
        )
        return self

    def __exit__(self, *exc):
        from gateway.session_context import clear_session_vars

        clear_session_vars(self._tokens)
        return False

    def rotate(self, session_id: str) -> None:
        """The agent worker's half of a compression split, mid-Run.

        ``set_current_session_id`` is the production call the compression owner
        makes the moment it forks the continuation
        (``agent/conversation_compression.py``). The contextvar moves here; the
        Gateway propagates onto the ``SessionEntry`` only after the Run returns,
        and everything between the two is the window under test.
        """

        from gateway.session_context import set_current_session_id

        set_current_session_id(session_id)


def _control(**args):
    """One real control call, off the loop thread the way the runner makes it."""

    return _await_composed(
        asyncio.to_thread(control_mod._handle_delegate_control, dict(args))
    )


async def _call(**args) -> dict[str, Any]:
    """One control call that is expected to be admitted; refusals name themselves."""

    answer = json.loads(await _control(**args))
    assert "error" not in answer, f"{args.get('action')} refused: {answer['error']}"
    return answer


def _rotate_entry(store, entry, session_id: str) -> None:
    """The Gateway's half of a compression split, after the Run returns.

    Mirrors ``gateway/run.py``: the agent thread already moved the contextvar,
    the runner propagates the new id onto the ``SessionEntry`` and saves.
    """

    entry.session_id = session_id
    store._save()


async def _terminal_task(bench, *, agent_id: str = AGENT_ID, index: int = 0) -> str:
    """One created task driven to its terminal, so a continuation is legal."""

    created = await _call(
        action="create",
        agent_id=agent_id,
        task=TASK_TEXT_CANARY,
        task_title=CARD_TITLE_CANARY,
    )
    task_ref = created["result"]["task_ref"]
    bench.facade.terminalize(index)
    key = bench.coordinator.state.read_task(task_ref).current_turn_key
    assert await _until(
        lambda: bench.coordinator.state.read_turn(key).lifecycle == "terminal"
    )
    return task_ref


# --------------------------------------------------------------------------- #
# B. Control follows the conversation through compression
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_every_control_action_answers_in_the_compression_child(
    tmp_path, monkeypatch, lineage
) -> None:
    """The whole control surface keeps working across one compression split."""

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)

    child_id = _compress(lineage, parent_id=parent_id)
    _rotate_entry(bench.store, entry, child_id)

    with _Turn(entry, message_id="m-after-compression"):
        status = await _call(action="status", task_ref=task_ref)
        result = await _call(action="result", task_ref=task_ref)
        recovered = await _call(action="recover", task_ref=task_ref)
        continued = await _call(
            action="continue", task_ref=task_ref, task="carry on after compression"
        )
        bench.facade.terminalize(1)
        second_key = bench.coordinator.state.read_task(task_ref).current_turn_key
        assert await _until(
            lambda: bench.coordinator.state.read_turn(second_key).lifecycle == "terminal"
        )
        cancelled = await _call(action="cancel", task_ref=task_ref)

    assert status["result"]["task_ref"] == task_ref
    assert status["result"]["lifecycle"] == "terminal"
    assert result["result"]["terminal"] == "completed"
    assert recovered["result"]["task_ref"] == task_ref
    assert continued["result"]["task_ref"] == task_ref
    assert cancelled["result"]["task_ref"] == task_ref
    assert bench.facade.submit_count() == 2
    # The physical Session the task was created under is never rewritten: the
    # record stays exactly as persisted, and remains the audit anchor.
    assert bench.coordinator.state.read_task(task_ref).origin.session_id == parent_id


@pytest.mark.asyncio
async def test_control_survives_several_compressions(
    tmp_path, monkeypatch, lineage
) -> None:
    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)

    current = parent_id
    for _ in range(3):
        current = _compress(lineage, parent_id=current)
        _rotate_entry(bench.store, entry, current)

    with _Turn(entry, message_id="m-third-compression"):
        status = await _call(action="status", task_ref=task_ref)

    assert current != parent_id
    assert status["result"]["task_ref"] == task_ref
    assert bench.coordinator.state.read_task(task_ref).origin.session_id == parent_id


@pytest.mark.asyncio
async def test_a_switch_still_links_a_new_task_after_compression(
    tmp_path, monkeypatch, lineage
) -> None:
    """Switching AGENT is a control action too, and it re-proves the caller."""

    bench = await _workbench(tmp_path, monkeypatch, "codex", "cursor")
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)

    child_id = _compress(lineage, parent_id=parent_id)
    _rotate_entry(bench.store, entry, child_id)

    with _Turn(entry, message_id="m-switch"):
        switched = await _call(
            action="continue",
            task_ref=task_ref,
            agent_id="cursor",
            task="review the completed work",
        )

    linked_ref = switched["result"]["task_ref"]
    linked = bench.coordinator.state.read_task(linked_ref)
    assert linked_ref != task_ref
    assert linked.agent_id == "cursor"
    # The linked task belongs to the conversation as it stands now.
    assert linked.origin.session_id == child_id
    assert bench.coordinator.state.read_task(task_ref).origin.session_id == parent_id


# --------------------------------------------------------------------------- #
# C. Nothing else inherits the conversation
#
# Each negative repoints the *same* ``SessionEntry`` — same platform, chat,
# thread, and session key — so the only thing that can refuse is the persisted
# lineage. A negative that also changed the chat would prove nothing about it.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_new_session_cannot_control_the_previous_conversations_task(
    tmp_path, monkeypatch, lineage
) -> None:
    """``/new`` really resets the store entry — and inherits no control."""

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    with _Turn(entry):
        task_ref = await _terminal_task(bench)

    fresh = bench.store.reset_session(entry.session_key)
    assert fresh.session_id != entry.session_id

    with _Turn(fresh, message_id="m-new"):
        answer = await _control(action="status", task_ref=task_ref)

    assert control_mod.SACHIMA_DELEGATE_CONTROL_FORBIDDEN in answer


@pytest.mark.asyncio
async def test_a_branch_child_cannot_control_the_parents_task(
    tmp_path, monkeypatch, lineage
) -> None:
    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)

    branched = _branch(lineage, parent_id=parent_id)
    _rotate_entry(bench.store, entry, branched)

    with _Turn(entry, message_id="m-branch"):
        answer = await _control(action="status", task_ref=task_ref)

    assert control_mod.SACHIMA_DELEGATE_CONTROL_FORBIDDEN in answer


@pytest.mark.asyncio
async def test_a_branch_taken_in_the_compression_window_cannot_control_the_task(
    tmp_path, monkeypatch, lineage
) -> None:
    """The one branch shape the continuation edge cannot recognise on its own.

    Same platform, chat, thread, and session key, and a parent that genuinely
    ended by compression — so only the branch marker can refuse this, and it
    must, at the real control surface rather than at a helper.
    """

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)

    branched = _branch_in_the_window(lineage, parent_id=parent_id)
    _rotate_entry(bench.store, entry, branched)

    with _Turn(entry, message_id="m-branch-in-window"):
        answer = await _control(action="status", task_ref=task_ref)

    assert control_mod.SACHIMA_DELEGATE_CONTROL_FORBIDDEN in answer


@pytest.mark.asyncio
async def test_a_subagent_child_cannot_control_the_parents_task(
    tmp_path, monkeypatch, lineage
) -> None:
    """A subagent run carries a parent link but started while the parent lived."""

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)

    sub = _subagent(lineage, parent_id=parent_id)
    lineage.end_session(parent_id, "compression")
    _rotate_entry(bench.store, entry, sub)

    with _Turn(entry, message_id="m-subagent"):
        answer = await _control(action="status", task_ref=task_ref)

    assert control_mod.SACHIMA_DELEGATE_CONTROL_FORBIDDEN in answer


@pytest.mark.asyncio
async def test_another_conversations_compression_child_is_still_refused(
    tmp_path, monkeypatch, lineage
) -> None:
    """Continuity is not a skeleton key: it only opens its own conversation."""

    bench = await _workbench(tmp_path, monkeypatch)
    mine = bench.store.get_or_create_session(_source())
    with _Turn(mine):
        task_ref = await _terminal_task(bench)

    theirs = bench.store.get_or_create_session(_source(chat_id="chat-2"))
    their_child = _compress(lineage, parent_id=theirs.session_id)
    _rotate_entry(bench.store, theirs, their_child)

    with _Turn(theirs, message_id="m-other"):
        answer = await _control(action="status", task_ref=task_ref)

    assert control_mod.SACHIMA_DELEGATE_CONTROL_FORBIDDEN in answer


@pytest.mark.asyncio
async def test_a_host_without_a_persisted_session_store_stays_exact(
    tmp_path, monkeypatch, lineage
) -> None:
    """No lineage to read means no continuation — never a guess in its place.

    ``SessionStore`` degrades to the JSONL path when SQLite is unavailable. With
    nothing to prove a split from, the rule collapses to the exact Session it
    always was rather than opening on the Session key.
    """

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)

    child_id = _compress(lineage, parent_id=parent_id)
    _rotate_entry(bench.store, entry, child_id)
    monkeypatch.setattr(bench.store, "_db", None)

    with _Turn(entry, message_id="m-no-db"):
        answer = await _control(action="status", task_ref=task_ref)

    assert control_mod.SACHIMA_DELEGATE_CONTROL_FORBIDDEN in answer


# --------------------------------------------------------------------------- #
# D. Records written before any of this stay exactly as they are
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_legacy_origin_without_a_session_key_still_answers_for_its_session(
    tmp_path, monkeypatch, lineage
) -> None:
    """An old binding that never recorded a session key is not made unreachable."""

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    with _Turn(entry):
        task_ref = await _terminal_task(bench)
    _strip_session_key(bench.coordinator, task_ref)

    with _Turn(entry, message_id="m-legacy"):
        status = await _call(action="status", task_ref=task_ref)

    assert status["result"]["task_ref"] == task_ref


@pytest.mark.asyncio
async def test_a_legacy_origin_without_a_session_key_is_not_carried_forward(
    tmp_path, monkeypatch, lineage
) -> None:
    """The continuation admits only origins that still match this conversation."""

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)
    _strip_session_key(bench.coordinator, task_ref)

    child_id = _compress(lineage, parent_id=parent_id)
    _rotate_entry(bench.store, entry, child_id)

    with _Turn(entry, message_id="m-legacy-compressed"):
        answer = await _control(action="status", task_ref=task_ref)

    assert control_mod.SACHIMA_DELEGATE_CONTROL_FORBIDDEN in answer


# --------------------------------------------------------------------------- #
# E. The window inside one Run: contextvar rotated, SessionEntry not yet
#
# Preflight compression fires part-way through a turn, on the agent worker
# thread. From that instant until the Run returns, the trusted contextvar names
# the continuation and the Gateway's ``SessionEntry`` still names the parent —
# and a control action landing in between used to find no Session at all.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_control_call_inside_the_compression_window_finds_its_session(
    tmp_path, monkeypatch, lineage
) -> None:
    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)

    with _Turn(entry, message_id="m-preflight") as turn:
        # Preflight compression, mid-Run. The store deliberately still holds the
        # parent: the Gateway propagates only after this Run returns.
        child_id = _compress(lineage, parent_id=parent_id)
        turn.rotate(child_id)
        assert bench.store.lookup_by_session_key(entry.session_key).session_id == parent_id
        status = await _call(action="status", task_ref=task_ref)

    assert status["result"]["task_ref"] == task_ref


@pytest.mark.asyncio
async def test_a_task_created_inside_the_window_belongs_to_the_continuation(
    tmp_path, monkeypatch, lineage
) -> None:
    """A Run that compresses and then delegates attributes the task correctly."""

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id

    with _Turn(entry, message_id="m-create-after-preflight") as turn:
        child_id = _compress(lineage, parent_id=parent_id)
        turn.rotate(child_id)
        created = await _call(
            action="create",
            agent_id=AGENT_ID,
            task=TASK_TEXT_CANARY,
            task_title=CARD_TITLE_CANARY,
        )

    task_ref = created["result"]["task_ref"]
    assert bench.coordinator.state.read_task(task_ref).origin.session_id == child_id
    bench.facade.terminalize(0)


@pytest.mark.parametrize(
    "shape", ["unrelated_root", "branch_child", "never_persisted", "subagent_child"]
)
@pytest.mark.asyncio
async def test_the_window_never_admits_an_unproven_session(
    tmp_path, monkeypatch, lineage, shape
) -> None:
    """The Session key still matches; only the lineage decides, and it refuses.

    This is the shape the fix must not take: admitting on the key alone, or on
    "the ids disagree, so ignore one of them", would let any rotation at all
    inherit the conversation.
    """

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)

    if shape == "unrelated_root":
        rotated = _new_session_id()
        lineage.create_session(session_id=rotated, source="telegram")
    elif shape == "branch_child":
        rotated = _branch(lineage, parent_id=parent_id)
    elif shape == "subagent_child":
        rotated = _subagent(lineage, parent_id=parent_id)
        lineage.end_session(parent_id, "compression")
    else:
        rotated = _new_session_id()

    with _Turn(entry, message_id="m-unproven") as turn:
        turn.rotate(rotated)
        answer = await _control(action="status", task_ref=task_ref)

    assert control_mod.SACHIMA_DELEGATE_CONTROL_NO_SESSION in answer


# --------------------------------------------------------------------------- #
# F. The result owed to the next ordinary turn, when that turn is in the child
#
# A task can finish while the user is away. The result is bound to the Session
# that created it and waits, unclaimed, for the next ordinary turn — and that
# turn can be the first one after a compression split. These go through the
# Gateway's own consume/settle seams, not through the coordinator directly.
# --------------------------------------------------------------------------- #
async def _settled_result(bench, task_ref: str):
    """The one settled result event of *task_ref*, once it is projectable."""

    binding = bench.coordinator.state.read_task(task_ref)
    turn_key = binding.current_turn_key
    assert await _until(
        lambda: _summary_is_settled(bench.coordinator, turn_key)
    ), "the delegated result never settled its summary"
    return bench.coordinator.state.result_for_turn(turn_key)


def _hermes_sink(bench, event) -> str:
    return bench.coordinator.state.read_result(event.event_id).hermes_sink


@pytest.mark.asyncio
async def test_a_parent_bound_result_is_owed_to_the_compression_child(
    tmp_path, monkeypatch, lineage
) -> None:
    """pending → in_flight → confirmed, claimed by the continuation."""

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)
    event = await _settled_result(bench, task_ref)
    assert event.session_id == parent_id
    assert _hermes_sink(bench, event) == "pending"

    # The conversation compressed before the user's next message arrived.
    child_id = _compress(lineage, parent_id=parent_id)
    _rotate_entry(bench.store, entry, child_id)

    host = bench.runner.host
    continuity = host._delegate_result_continuity(entry)
    text = host._consume_delegate_result_context(
        entry.session_id, continuity=continuity
    )

    assert GATEWAY_SUMMARY_CANARY in text
    assert event.full_result_ref in text
    assert _hermes_sink(bench, event) == "in_flight"
    # Taking it twice does not hand one result to two turns.
    assert host._consume_delegate_result_context(
        entry.session_id, continuity=continuity
    ) == ""

    host._settle_delegate_result_context(
        entry.session_id, consumed=True, continuity=continuity
    )
    assert _hermes_sink(bench, event) == "confirmed"
    # The event keeps the Session it was produced under: audit, not migration.
    assert bench.coordinator.state.read_result(event.event_id).session_id == parent_id


@pytest.mark.asyncio
async def test_an_interrupted_child_handoff_returns_to_pending(
    tmp_path, monkeypatch, lineage
) -> None:
    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)
    event = await _settled_result(bench, task_ref)

    child_id = _compress(lineage, parent_id=parent_id)
    _rotate_entry(bench.store, entry, child_id)

    host = bench.runner.host
    continuity = host._delegate_result_continuity(entry)
    assert host._consume_delegate_result_context(
        entry.session_id, continuity=continuity
    )
    assert _hermes_sink(bench, event) == "in_flight"

    host._settle_delegate_result_context(
        entry.session_id, consumed=False, continuity=continuity
    )
    assert _hermes_sink(bench, event) == "pending"
    # Still owed, so a later turn in the same conversation still sees it.
    assert GATEWAY_SUMMARY_CANARY in host._consume_delegate_result_context(
        entry.session_id, continuity=continuity
    )


@pytest.mark.asyncio
async def test_a_result_survives_several_compressions_before_it_is_claimed(
    tmp_path, monkeypatch, lineage
) -> None:
    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)
    event = await _settled_result(bench, task_ref)

    current = parent_id
    for _ in range(2):
        current = _compress(lineage, parent_id=current)
        _rotate_entry(bench.store, entry, current)

    host = bench.runner.host
    continuity = host._delegate_result_continuity(entry)
    assert GATEWAY_SUMMARY_CANARY in host._consume_delegate_result_context(
        entry.session_id, continuity=continuity
    )
    host._settle_delegate_result_context(
        entry.session_id, consumed=True, continuity=continuity
    )
    assert _hermes_sink(bench, event) == "confirmed"


@pytest.mark.parametrize(
    "shape",
    ["new_session", "branch_child", "branch_in_window", "subagent_child"],
)
@pytest.mark.asyncio
async def test_a_session_that_is_not_the_continuation_is_owed_nothing(
    tmp_path, monkeypatch, lineage, shape
) -> None:
    """A conversation that was started, branched, or spawned inherits no result."""

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)
    event = await _settled_result(bench, task_ref)

    if shape == "new_session":
        successor = bench.store.reset_session(entry.session_key)
    else:
        if shape == "branch_child":
            rotated = _branch(lineage, parent_id=parent_id)
        elif shape == "branch_in_window":
            rotated = _branch_in_the_window(lineage, parent_id=parent_id)
        else:
            rotated = _subagent(lineage, parent_id=parent_id)
            lineage.end_session(parent_id, "compression")
        _rotate_entry(bench.store, entry, rotated)
        successor = entry

    host = bench.runner.host
    continuity = host._delegate_result_continuity(successor)
    text = host._consume_delegate_result_context(
        successor.session_id, continuity=continuity
    )

    assert text == ""
    assert _hermes_sink(bench, event) == "pending"


# --------------------------------------------------------------------------- #
# G. A restart re-reads the proof; it does not remember it
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_restarted_gateway_still_proves_the_same_continuity(
    tmp_path, monkeypatch, lineage
) -> None:
    """Nothing is cached in the process: the store and the lineage are on disk."""

    bench = await _workbench(tmp_path, monkeypatch)
    entry = bench.store.get_or_create_session(_source())
    parent_id = entry.session_id
    with _Turn(entry):
        task_ref = await _terminal_task(bench)
    event = await _settled_result(bench, task_ref)

    child_id = _compress(lineage, parent_id=parent_id)
    _rotate_entry(bench.store, entry, child_id)

    # A fresh Gateway process: a new SessionStore over the same sessions.json
    # and a new SessionDB over the same state.db. The coordinator's durable
    # delegate state is untouched.
    restarted = _Host(tmp_path)
    control_mod.bind_delegate_control_session_store(restarted.host.session_store)
    reloaded = restarted.host.session_store.lookup_by_session_key(entry.session_key)
    assert reloaded.session_id == child_id

    with _Turn(reloaded, message_id="m-restarted"):
        status = await _call(action="status", task_ref=task_ref)
    assert status["result"]["task_ref"] == task_ref

    continuity = restarted.host._delegate_result_continuity(reloaded)
    assert GATEWAY_SUMMARY_CANARY in restarted.host._consume_delegate_result_context(
        reloaded.session_id, continuity=continuity
    )
    restarted.host._settle_delegate_result_context(
        reloaded.session_id, consumed=True, continuity=continuity
    )
    assert _hermes_sink(bench, event) == "confirmed"


def _strip_session_key(coordinator, task_ref: str) -> None:
    """Rewrite one binding to the pre-``session_key`` origin shape on disk."""

    binding = coordinator.state.read_task(task_ref)
    origin = binding.origin
    coordinator.state.put_task(
        type(binding)(
            **{
                field: getattr(binding, field)
                for field in (
                    "task_ref",
                    "task_id",
                    "backend_handle",
                    "spine_session_id",
                    "agent_id",
                    "turn_keys",
                    "current_turn_key",
                    "terminal",
                    "linked_from",
                    "task_title",
                )
            },
            origin=type(origin)(
                platform=origin.platform,
                chat_id=origin.chat_id,
                thread_id=origin.thread_id,
                session_key="",
                session_id=origin.session_id,
                reply_anchor=origin.reply_anchor,
            ),
        )
    )
