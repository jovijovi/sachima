"""R4 — Workspace single-writer lease (design §4/§8/§11.8, plan §8).

RED/GREEN tests for the future ``workspace`` module. A run's Isolated Workspace
carries a **single-writer lease**: at most one writer may mutate one ``task_id``'s
workspace at a time. The lease is the *invariant*, not git — a git worktree is
merely one implementation for code tasks, so the store makes **no** filesystem,
Gateway, process, or platform assumption. Duplicate acquire by the same holder is
idempotent; a conflicting acquire fails closed without mutating state; release
requires the exact holder + token; expiry is deterministic and an expired lease is
reclaimable only through the explicit policy path.

The module under test is pure local/offline Python: importing/using it launches no
subprocess, opens no socket, touches no filesystem, and wires no Gateway/Feishu or
delivery surface. Forbidden terms appear only as no-leak canaries, never behavior.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path

import pytest

from sachima_supervisor.runtime_spine import (
    SpineError,
    TaskRegistry,
    scan_for_leak,
)

# The no-leak canaries the R4 gate requires a refs-only workspace surface to reject.
_LEAK_CANARIES = (
    "raw_prompt",
    "raw_context",
    "tool_output",
    "agent_stdout",
    "card_json",
    "chat_id",
    "oc_",
    "ou_",
    "/tmp/",
    "/home/",
    "sk" + "-",
    "bearer ",
    "feishu",
)


def _workspace_mod():
    return importlib.import_module("sachima_supervisor.runtime_spine.workspace")


def _new_store():
    mod = _workspace_mod()
    return mod, mod.WorkspaceLeaseStore()


def _acquire(mod, store, **overrides):
    kwargs = dict(
        task_id="task_alpha",
        holder="writer_alpha",
        workspace_ref="ws_ref_alpha",
        now=100,
        ttl=50,
    )
    kwargs.update(overrides)
    return mod.acquire_workspace_lease(store, **kwargs)


# --------------------------------------------------------------------------- #
# A. Public surface and stable error family
# --------------------------------------------------------------------------- #
def test_workspace_public_surface_is_exported() -> None:
    mod = _workspace_mod()
    assert mod.RUNTIME_INVALID_WORKSPACE_LEASE == "runtime_invalid_workspace_lease"
    assert mod.RUNTIME_WORKSPACE_LEASE_CONFLICT == "runtime_workspace_lease_conflict"
    assert mod.RUNTIME_INVALID_WORKSPACE_LEASE in mod.WORKSPACE_STABLE_CODES
    assert mod.RUNTIME_WORKSPACE_LEASE_CONFLICT in mod.WORKSPACE_STABLE_CODES
    for name in (
        "WorkspaceLease",
        "WorkspaceLeaseStore",
        "acquire_workspace_lease",
        "release_workspace_lease",
        "reclaim_expired_workspace_lease",
        "validate_workspace_lease",
    ):
        assert hasattr(mod, name)


def test_workspace_symbols_available_from_runtime_spine_package() -> None:
    runtime_spine = importlib.import_module("sachima_supervisor.runtime_spine")
    for name in (
        "RUNTIME_INVALID_WORKSPACE_LEASE",
        "RUNTIME_WORKSPACE_LEASE_CONFLICT",
        "WorkspaceLease",
        "WorkspaceLeaseStore",
        "acquire_workspace_lease",
        "release_workspace_lease",
        "reclaim_expired_workspace_lease",
    ):
        assert hasattr(runtime_spine, name)


def test_workspace_lease_store_is_zero_arg_local_offline() -> None:
    # The store owns its own state — no registry / clock / path / port injection.
    mod = _workspace_mod()
    store = mod.WorkspaceLeaseStore()
    assert store.active_count() == 0
    assert store.current("task_alpha") is None


# --------------------------------------------------------------------------- #
# B. Single-writer lease — at most one writer per task_id
# --------------------------------------------------------------------------- #
def test_acquire_grants_a_single_writer_lease() -> None:
    mod, store = _new_store()
    lease = _acquire(mod, store)
    assert type(lease) is mod.WorkspaceLease
    assert lease.task_id == "task_alpha"
    assert lease.holder == "writer_alpha"
    assert lease.workspace_ref == "ws_ref_alpha"
    assert lease.acquired_at == 100
    assert lease.expires_at == 150
    assert lease.token  # an opaque, refs-only lease token
    assert store.current("task_alpha") == lease
    assert store.active_count() == 1
    assert scan_for_leak(dataclasses.asdict(lease)) is None


def test_second_writer_conflicts_until_release() -> None:
    mod, store = _new_store()
    first = _acquire(mod, store, holder="writer_alpha")
    before = store.current("task_alpha")

    # A second, different writer cannot take the leased workspace.
    with pytest.raises(SpineError) as exc:
        _acquire(mod, store, holder="writer_beta")
    assert exc.value.code == mod.RUNTIME_WORKSPACE_LEASE_CONFLICT
    # Fail closed: the existing lease is untouched, still one active writer.
    assert store.current("task_alpha") == before == first
    assert store.active_count() == 1

    # Once the holder releases, the slot is free and the second writer wins.
    mod.release_workspace_lease(
        store, task_id="task_alpha", holder="writer_alpha", token=first.token
    )
    assert store.current("task_alpha") is None
    second = _acquire(mod, store, holder="writer_beta")
    assert second.holder == "writer_beta"
    assert store.active_count() == 1


def test_at_most_one_active_writer_across_repeated_conflicts() -> None:
    mod, store = _new_store()
    _acquire(mod, store, holder="writer_alpha")
    for other in ("writer_beta", "writer_gamma", "writer_delta"):
        with pytest.raises(SpineError) as exc:
            _acquire(mod, store, holder=other)
        assert exc.value.code in mod.WORKSPACE_STABLE_CODES
    assert store.active_count() == 1
    assert store.current("task_alpha").holder == "writer_alpha"


def test_lease_is_per_task_independent() -> None:
    mod, store = _new_store()
    a = _acquire(mod, store, task_id="task_alpha", holder="writer_alpha")
    b = _acquire(mod, store, task_id="task_beta", holder="writer_alpha")
    # Two different tasks each hold their own single-writer lease.
    assert a.task_id == "task_alpha"
    assert b.task_id == "task_beta"
    assert store.active_count() == 2
    assert store.current("task_alpha") == a
    assert store.current("task_beta") == b


# --------------------------------------------------------------------------- #
# C. Duplicate acquire by the same holder is idempotent / same lease
# --------------------------------------------------------------------------- #
def test_duplicate_acquire_same_holder_is_idempotent_same_lease() -> None:
    mod, store = _new_store()
    first = _acquire(mod, store, holder="writer_alpha", now=100, ttl=50)
    again = _acquire(mod, store, holder="writer_alpha", now=110, ttl=999)
    # Same lease returned — same token, same expiry (no silent renewal/mutation).
    assert again == first
    assert again.token == first.token
    assert again.expires_at == first.expires_at == 150
    assert store.active_count() == 1
    assert store.current("task_alpha") == first


def test_conflicting_acquire_fails_closed_and_does_not_mutate_state() -> None:
    mod, store = _new_store()
    first = _acquire(mod, store, holder="writer_alpha")
    before = store.current("task_alpha")
    with pytest.raises(SpineError) as exc:
        _acquire(mod, store, holder="writer_beta", workspace_ref="ws_ref_beta")
    assert exc.value.code == mod.RUNTIME_WORKSPACE_LEASE_CONFLICT
    # No state mutation on the fail-closed conflict path.
    assert store.current("task_alpha") == before == first
    assert store.active_count() == 1


# --------------------------------------------------------------------------- #
# D. Release semantics — wrong holder/token fails closed; correct holder releases
# --------------------------------------------------------------------------- #
def test_release_wrong_holder_fails_closed_no_mutation() -> None:
    mod, store = _new_store()
    lease = _acquire(mod, store, holder="writer_alpha")
    with pytest.raises(SpineError) as exc:
        mod.release_workspace_lease(
            store, task_id="task_alpha", holder="writer_beta", token=lease.token
        )
    assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE
    # The lease is still held by the original writer.
    assert store.current("task_alpha") == lease
    assert store.active_count() == 1


def test_release_wrong_token_fails_closed_no_mutation() -> None:
    mod, store = _new_store()
    lease = _acquire(mod, store, holder="writer_alpha")
    with pytest.raises(SpineError) as exc:
        mod.release_workspace_lease(
            store, task_id="task_alpha", holder="writer_alpha", token="lease_forged_999"
        )
    assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE
    assert store.current("task_alpha") == lease


def test_correct_holder_releases_and_frees_slot() -> None:
    mod, store = _new_store()
    lease = _acquire(mod, store, holder="writer_alpha")
    released = mod.release_workspace_lease(
        store, task_id="task_alpha", holder="writer_alpha", token=lease.token
    )
    assert released == lease
    assert store.current("task_alpha") is None
    assert store.active_count() == 0


def test_release_without_a_lease_fails_closed() -> None:
    mod, store = _new_store()
    with pytest.raises(SpineError) as exc:
        mod.release_workspace_lease(
            store, task_id="task_alpha", holder="writer_alpha", token="lease_1"
        )
    assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE


# --------------------------------------------------------------------------- #
# E. Expiry policy — deterministic + reclaim only via the explicit policy path
# --------------------------------------------------------------------------- #
def test_lease_expiry_is_deterministic() -> None:
    mod, store = _new_store()
    lease = _acquire(mod, store, now=100, ttl=50)  # expires_at == 150
    # Exact, pure boundary — no wall-clock, driven only by the passed logical tick.
    assert lease.is_expired(149) is False
    assert lease.is_expired(150) is True
    assert lease.is_expired(151) is True
    assert lease.is_expired(149) is False  # repeatable / side-effect free


def test_lease_expiry_rejects_invalid_logical_ticks() -> None:
    mod, store = _new_store()
    lease = _acquire(mod, store, now=100, ttl=50)
    for bad_now in (True, -1, 149.5, "raw_prompt_dump"):
        with pytest.raises(SpineError) as exc:
            lease.is_expired(bad_now)
        assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE
        assert "raw_prompt" not in str(exc.value)


def test_expired_lease_still_blocks_a_plain_acquire() -> None:
    mod, store = _new_store()
    lease = _acquire(mod, store, holder="writer_alpha", now=100, ttl=50)
    assert lease.is_expired(200) is True
    # An expired lease is NOT silently stolen by a plain acquire — it must be
    # reclaimed through the explicit policy path first.
    with pytest.raises(SpineError) as exc:
        _acquire(mod, store, holder="writer_beta", now=200, ttl=50)
    assert exc.value.code == mod.RUNTIME_WORKSPACE_LEASE_CONFLICT
    assert store.current("task_alpha") == lease


def test_expired_lease_reclaimed_only_by_policy_path() -> None:
    mod, store = _new_store()
    lease = _acquire(mod, store, holder="writer_alpha", now=100, ttl=50)
    reclaimed = mod.reclaim_expired_workspace_lease(store, task_id="task_alpha", now=200)
    assert reclaimed == lease
    assert store.current("task_alpha") is None
    assert store.active_count() == 0
    # After the explicit reclaim, a new writer may take the freed slot.
    fresh = _acquire(mod, store, holder="writer_beta", now=210, ttl=50)
    assert fresh.holder == "writer_beta"
    assert fresh.expires_at == 260


def test_reclaim_live_lease_fails_closed() -> None:
    mod, store = _new_store()
    lease = _acquire(mod, store, holder="writer_alpha", now=100, ttl=50)
    # The lease is not yet expired at now=149 — reclaim must refuse it.
    with pytest.raises(SpineError) as exc:
        mod.reclaim_expired_workspace_lease(store, task_id="task_alpha", now=149)
    assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE
    assert store.current("task_alpha") == lease
    assert store.active_count() == 1


def test_reclaim_without_a_lease_fails_closed() -> None:
    mod, store = _new_store()
    with pytest.raises(SpineError) as exc:
        mod.reclaim_expired_workspace_lease(store, task_id="task_alpha", now=200)
    assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE


# --------------------------------------------------------------------------- #
# F. Invariant, not git — refs-only, no filesystem / path / platform material
# --------------------------------------------------------------------------- #
def test_workspace_ref_is_a_ref_not_a_filesystem_path() -> None:
    mod, store = _new_store()
    # A path-like or platform-derived workspace ref is not a ref — fail closed.
    for bad_ref in ("/tmp/agent_ws/scratch", "/home/user/repo", "oc_open_chat_1"):
        with pytest.raises(SpineError) as exc:
            _acquire(mod, store, workspace_ref=bad_ref)
        assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE
        assert bad_ref not in str(exc.value)
    assert store.active_count() == 0


@pytest.mark.parametrize("canary", _LEAK_CANARIES)
def test_acquire_rejects_raw_or_platform_material_in_holder(canary: str) -> None:
    mod, store = _new_store()
    with pytest.raises(SpineError) as exc:
        _acquire(mod, store, holder=f"writer_{canary}_x")
    assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE
    assert str(exc.value) == mod.RUNTIME_INVALID_WORKSPACE_LEASE


def test_acquire_rejects_bad_now_or_ttl() -> None:
    mod, store = _new_store()
    # now must be a non-negative int, ttl a positive int; bool must not pose as int.
    for now, ttl in ((-1, 50), (100, 0), (100, -5), (True, 50), (100, True), (1.0, 50)):
        with pytest.raises(SpineError) as exc:
            _acquire(mod, store, now=now, ttl=ttl)
        assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE
    assert store.active_count() == 0


def test_acquire_rejects_unsafe_task_id() -> None:
    mod, store = _new_store()
    for bad in ("Task Alpha", "1bad", "", "task-alpha", "chat_id_1"):
        with pytest.raises(SpineError) as exc:
            _acquire(mod, store, task_id=bad)
        assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE


# --------------------------------------------------------------------------- #
# G. Trust boundary — hostile / forged / directly-built leases fail closed
# --------------------------------------------------------------------------- #
def test_workspace_lease_direct_construction_rejects_unsafe_fields() -> None:
    mod = _workspace_mod()
    with pytest.raises(SpineError) as exc:
        mod.WorkspaceLease(
            task_id="task_alpha",
            holder="writer_alpha",
            token="lease_1",
            workspace_ref="/tmp/agent_ws",  # a private path is not a ref
            acquired_at=100,
            expires_at=150,
        )
    assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE


def test_validate_workspace_lease_rejects_forged_instance() -> None:
    mod = _workspace_mod()
    forged = object.__new__(mod.WorkspaceLease)  # bypasses __post_init__
    for name, value in (
        ("task_id", "task_alpha"),
        ("holder", "writer_alpha"),
        ("token", "lease_1"),
        ("workspace_ref", "ref_raw_prompt"),  # a leaky ref — not allowlisted
        ("acquired_at", 100),
        ("expires_at", 150),
    ):
        object.__setattr__(forged, name, value)
    assert type(forged) is mod.WorkspaceLease  # passes a naive identity gate
    with pytest.raises(SpineError) as exc:
        mod.validate_workspace_lease(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE
    assert "raw_prompt" not in str(exc.value)


def test_validate_workspace_lease_rejects_bad_expiry_ordering() -> None:
    mod = _workspace_mod()
    forged = object.__new__(mod.WorkspaceLease)
    for name, value in (
        ("task_id", "task_alpha"),
        ("holder", "writer_alpha"),
        ("token", "lease_1"),
        ("workspace_ref", "ws_ref_alpha"),
        ("acquired_at", 150),
        ("expires_at", 100),  # expiry before acquisition — impossible
    ):
        object.__setattr__(forged, name, value)
    with pytest.raises(SpineError) as exc:
        mod.validate_workspace_lease(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE


def test_validate_workspace_lease_rejects_hostile_subclass() -> None:
    mod = _workspace_mod()

    class _Hostile(mod.WorkspaceLease):
        def __post_init__(self) -> None:  # skip fail-closed validation
            return None

    hostile = _Hostile(
        task_id="task_alpha",
        holder="writer_alpha",
        token="lease_1",
        workspace_ref="oc_open_chat_1",  # platform id smuggled past construction
        acquired_at=100,
        expires_at=150,
    )
    with pytest.raises(SpineError) as exc:
        mod.validate_workspace_lease(hostile)
    assert exc.value.code == mod.RUNTIME_INVALID_WORKSPACE_LEASE


# --------------------------------------------------------------------------- #
# H. R1/R2/R3 untouched — the lease store owns no registry/log/port lifecycle
# --------------------------------------------------------------------------- #
def test_lease_store_does_not_own_or_append_to_the_event_log() -> None:
    # The lease is a workspace invariant, not an event producer: driving the store
    # appends nothing to an independent R1 registry/log.
    mod, store = _new_store()
    registry = TaskRegistry()
    registry.create_task("task_alpha", needs_agent=True)
    seq_before = registry.log.last_seq("task_alpha")
    lease = _acquire(mod, store)
    mod.release_workspace_lease(
        store, task_id="task_alpha", holder="writer_alpha", token=lease.token
    )
    assert registry.log.last_seq("task_alpha") == seq_before


# --------------------------------------------------------------------------- #
# I. Structural guard — no filesystem / process / network / delivery wiring
# --------------------------------------------------------------------------- #
def test_workspace_source_has_no_forbidden_runtime_surface() -> None:
    path = Path("sachima_supervisor/runtime_spine/workspace.py")
    if not path.exists():
        pytest.skip("workspace.py not implemented yet; RED import tests cover absence")
    text = path.read_text(encoding="utf-8")
    forbidden = (
        "subprocess",
        "socket",
        ".Popen(",
        "os.system",
        "os.popen",
        "acpx",
        " npx",
        "gateway",
        "feishu",
        "lark",
        "send(",
        "GitPython",
        "import git",
    )
    assert [token for token in forbidden if token in text] == []
    import_lines = [
        ln for ln in text.splitlines() if ln.strip().startswith(("import ", "from "))
    ]
    denied_roots = (
        "subprocess",
        "socket",
        "pathlib",
        "temporal",
        "gateway",
        "feishu",
        "lark",
        "httpx",
        "requests",
        "urllib",
        "aiohttp",
        "docker",
        "multiprocessing",
        "asyncio",
    )
    for line in import_lines:
        for root in denied_roots:
            assert root not in line, f"forbidden import {root!r}: {line!r}"
