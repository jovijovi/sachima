"""R2 — Supervisor Execution Port interface + refs-only value objects.

RED/GREEN tests for the execution-port abstraction (design §4/§7/§8, plan §6):
the single producer-facing interface ``create_or_attach / stream / signal /
status / kill / liveness``, plus the frozen, fail-closed, refs-only value objects
it hands back (``SessionRef`` / ``LivenessState`` / ``SessionStatus``).

The module under test is pure local/offline Python. Importing it starts no
subprocess, socket, Docker, daemon, Temporal service/Worker/client, Gateway,
Feishu, or network call, and launches no OS process or real ``agent-run-supervisor``.
The forbidden terms below appear only as no-leak canaries, never as behavior.
"""

from __future__ import annotations

import abc

import pytest

from sachima_supervisor.runtime_spine import (
    STABLE_CODES,
    ExecutionPort,
    LivenessState,
    SessionRef,
    SessionStatus,
    SpineError,
)
from sachima_supervisor.runtime_spine.execution_port import (
    LIVE_SESSION_STATES,
    PORT_STABLE_CODES,
    REAPABLE_SESSION_STATES,
    RUNTIME_INVALID_SESSION,
    SESSION_STATES,
    TERMINAL_SESSION_STATES,
    validate_liveness_state,
    validate_session_ref,
    validate_session_status,
)


# --------------------------------------------------------------------------- #
# A. Stable-code family — a new, exported, disjoint port code
# --------------------------------------------------------------------------- #
def test_invalid_session_is_a_stable_string_code() -> None:
    assert RUNTIME_INVALID_SESSION == "runtime_invalid_session"
    assert RUNTIME_INVALID_SESSION in PORT_STABLE_CODES


def test_port_code_is_disjoint_from_r1_stable_codes() -> None:
    # The port code is raised, never stored as an event ``error_code`` — so it is
    # intentionally NOT a member of the R1 event-body ``STABLE_CODES`` allowlist.
    assert RUNTIME_INVALID_SESSION not in STABLE_CODES
    assert PORT_STABLE_CODES.isdisjoint(STABLE_CODES)


def test_session_state_vocabularies_are_partitioned() -> None:
    # Live / terminal / reapable are disjoint slices of the closed state set.
    assert LIVE_SESSION_STATES <= SESSION_STATES
    assert TERMINAL_SESSION_STATES <= SESSION_STATES
    assert REAPABLE_SESSION_STATES <= SESSION_STATES
    assert LIVE_SESSION_STATES.isdisjoint(TERMINAL_SESSION_STATES)
    assert LIVE_SESSION_STATES.isdisjoint(REAPABLE_SESSION_STATES)
    assert TERMINAL_SESSION_STATES.isdisjoint(REAPABLE_SESSION_STATES)
    # permission_wait is a LIVE state (never terminal, never reapable).
    assert "permission_wait" in LIVE_SESSION_STATES
    assert "running" in LIVE_SESSION_STATES


# --------------------------------------------------------------------------- #
# B. ExecutionPort is an abstract interface with exactly the six methods
# --------------------------------------------------------------------------- #
def test_execution_port_is_abstract_and_not_instantiable() -> None:
    assert issubclass(ExecutionPort, abc.ABC)
    with pytest.raises(TypeError):
        type.__call__(ExecutionPort)


def test_execution_port_declares_the_six_producer_methods() -> None:
    required = {"create_or_attach", "stream", "signal", "status", "kill", "liveness"}
    assert required <= set(ExecutionPort.__abstractmethods__)


def test_partial_subclass_stays_abstract() -> None:
    class _Partial(ExecutionPort):
        def create_or_attach(self, task_id, launch_spec):
            return SessionRef(task_id="task_alpha", session_id="sess_1")

    # Missing five abstract methods → still not instantiable.
    with pytest.raises(TypeError):
        type.__call__(_Partial)


def test_full_subclass_is_instantiable() -> None:
    class _Full(ExecutionPort):
        def create_or_attach(self, task_id, launch_spec):
            return SessionRef(task_id="task_alpha", session_id="sess_1")

        def stream(self, ref):
            return ()

        def signal(self, task_id, decision_ref):
            return SessionStatus(
                task_id="task_alpha",
                session_id="sess_1",
                state="running",
                alive=True,
                terminal=False,
                last_seq=1,
                projected_status="running",
            )

        def status(self, ref):
            return SessionStatus(
                task_id="task_alpha",
                session_id="sess_1",
                state="running",
                alive=True,
                terminal=False,
                last_seq=1,
                projected_status="running",
            )

        def kill(self, ref, reason_ref="ref_cancelled"):
            return SessionStatus(
                task_id="task_alpha",
                session_id="sess_1",
                state="cancelled",
                alive=False,
                terminal=True,
                last_seq=2,
                projected_status="cancelled",
            )

        def liveness(self, ref):
            return LivenessState(
                task_id="task_alpha",
                session_id="sess_1",
                state="running",
                alive=True,
                permission_wait=False,
                reapable=False,
            )

    port = _Full()
    assert isinstance(port, ExecutionPort)


# --------------------------------------------------------------------------- #
# C. SessionRef — frozen, refs-only, fail-closed, forgery-resistant
# --------------------------------------------------------------------------- #
def test_session_ref_valid_construction_and_frozen() -> None:
    ref = SessionRef(task_id="task_alpha", session_id="sess_1")
    assert ref.task_id == "task_alpha"
    assert ref.session_id == "sess_1"
    assert validate_session_ref(ref) is ref
    with pytest.raises(Exception):
        ref.session_id = "sess_2"  # type: ignore[misc]  # frozen


def test_session_ref_rejects_unsafe_task_id() -> None:
    for bad in ("Task Alpha", "chat_id_1", "1bad", "", "oc_leak"):
        with pytest.raises(SpineError) as exc:
            SessionRef(task_id=bad, session_id="sess_1")
        assert exc.value.code == RUNTIME_INVALID_SESSION
        assert str(exc.value) == RUNTIME_INVALID_SESSION


def test_session_ref_rejects_unshaped_or_leaky_session_id() -> None:
    # session_id must carry the ``sess_`` shape and no forbidden marker.
    for bad in ("handle_1", "sess", "SESS_1", "sess_oc_1", "sess_bearer ", 5, None):
        with pytest.raises(SpineError) as exc:
            SessionRef(task_id="task_alpha", session_id=bad)  # type: ignore[arg-type]
        assert exc.value.code == RUNTIME_INVALID_SESSION


def test_session_ref_no_raw_material_leaks_in_error() -> None:
    with pytest.raises(SpineError) as exc:
        SessionRef(task_id="task_alpha", session_id="sess_raw_prompt_leak")
    # A rejected session id must never be echoed back in the error text.
    assert "raw_prompt" not in str(exc.value)
    assert str(exc.value) == RUNTIME_INVALID_SESSION


def test_validate_session_ref_rejects_new_forged_instance() -> None:
    # object.__new__ bypasses __init__/__post_init__ but ``type() is SessionRef``
    # still holds — the trust boundary must RE-VALIDATE the fields.
    forged = object.__new__(SessionRef)
    object.__setattr__(forged, "task_id", "task_alpha")
    object.__setattr__(forged, "session_id", "chat_id_leak")
    assert type(forged) is SessionRef
    with pytest.raises(SpineError) as exc:
        validate_session_ref(forged)
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_validate_session_ref_rejects_partial_forged_instance() -> None:
    forged = object.__new__(SessionRef)
    object.__setattr__(forged, "task_id", "task_alpha")
    with pytest.raises(SpineError) as exc:
        validate_session_ref(forged)
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_validate_session_ref_rejects_hostile_subclass() -> None:
    class _HostileRef(SessionRef):
        def __post_init__(self) -> None:  # skip the fail-closed validation
            return None

    hostile = _HostileRef(task_id="task_alpha", session_id="not_a_session_handle")
    with pytest.raises(SpineError) as exc:
        validate_session_ref(hostile)
    assert exc.value.code == RUNTIME_INVALID_SESSION


# --------------------------------------------------------------------------- #
# D. LivenessState — cross-field invariants pin permission-wait = alive
# --------------------------------------------------------------------------- #
def test_liveness_state_permission_wait_is_alive_not_reapable() -> None:
    live = LivenessState(
        task_id="task_alpha",
        session_id="sess_1",
        state="permission_wait",
        alive=True,
        permission_wait=True,
        reapable=False,
    )
    assert live.alive is True
    assert live.permission_wait is True
    assert live.reapable is False
    assert validate_liveness_state(live) is live


def test_liveness_state_orphaned_is_dead_and_reapable() -> None:
    dead = LivenessState(
        task_id="task_alpha",
        session_id="sess_1",
        state="orphaned",
        alive=False,
        permission_wait=False,
        reapable=True,
    )
    assert dead.alive is False
    assert dead.reapable is True


def test_liveness_state_rejects_inconsistent_permission_wait_dead() -> None:
    # A forged "permission_wait but dead" or "permission_wait but reapable" liveness
    # is exactly the misclassification the reaper must never make — fail closed.
    for alive, reapable in ((False, False), (True, True)):
        with pytest.raises(SpineError) as exc:
            LivenessState(
                task_id="task_alpha",
                session_id="sess_1",
                state="permission_wait",
                alive=alive,
                permission_wait=True,
                reapable=reapable,
            )
        assert exc.value.code == RUNTIME_INVALID_SESSION


def test_liveness_state_rejects_unknown_state_and_nonbool_flags() -> None:
    with pytest.raises(SpineError):
        LivenessState(
            task_id="task_alpha",
            session_id="sess_1",
            state="zombie",
            alive=False,
            permission_wait=False,
            reapable=True,
        )
    with pytest.raises(SpineError):
        LivenessState(
            task_id="task_alpha",
            session_id="sess_1",
            state="running",
            alive=1,  # type: ignore[arg-type]  # bool-only
            permission_wait=False,
            reapable=False,
        )


def test_validate_liveness_state_rejects_forged_and_subclass() -> None:
    forged = object.__new__(LivenessState)
    object.__setattr__(forged, "task_id", "task_alpha")
    object.__setattr__(forged, "session_id", "sess_1")
    object.__setattr__(forged, "state", "running")
    object.__setattr__(forged, "alive", False)  # inconsistent: running must be alive
    object.__setattr__(forged, "permission_wait", False)
    object.__setattr__(forged, "reapable", False)
    with pytest.raises(SpineError):
        validate_liveness_state(forged)

    class _Hostile(LivenessState):
        def __post_init__(self) -> None:
            return None

    hostile = _Hostile(
        task_id="task_alpha",
        session_id="sess_1",
        state="running",
        alive=False,
        permission_wait=False,
        reapable=False,
    )
    with pytest.raises(SpineError):
        validate_liveness_state(hostile)


# --------------------------------------------------------------------------- #
# E. SessionStatus — projection-derived, fail-closed
# --------------------------------------------------------------------------- #
def test_session_status_valid_running() -> None:
    status = SessionStatus(
        task_id="task_alpha",
        session_id="sess_1",
        state="running",
        alive=True,
        terminal=False,
        last_seq=3,
        projected_status="running",
    )
    assert status.alive is True
    assert status.terminal is False
    assert validate_session_status(status) is status


def test_session_status_terminal_is_not_alive() -> None:
    status = SessionStatus(
        task_id="task_alpha",
        session_id="sess_1",
        state="cancelled",
        alive=False,
        terminal=True,
        last_seq=5,
        projected_status="cancelled",
    )
    assert status.terminal is True
    assert status.alive is False


def test_session_status_rejects_alive_and_terminal_contradiction() -> None:
    with pytest.raises(SpineError) as exc:
        SessionStatus(
            task_id="task_alpha",
            session_id="sess_1",
            state="completed",
            alive=True,  # terminal state cannot be alive
            terminal=True,
            last_seq=5,
            projected_status="completed",
        )
    assert exc.value.code == RUNTIME_INVALID_SESSION


def test_session_status_rejects_bad_last_seq_and_projected_status() -> None:
    with pytest.raises(SpineError):
        SessionStatus(
            task_id="task_alpha",
            session_id="sess_1",
            state="running",
            alive=True,
            terminal=False,
            last_seq=-1,
            projected_status="running",
        )
    with pytest.raises(SpineError):
        SessionStatus(
            task_id="task_alpha",
            session_id="sess_1",
            state="running",
            alive=True,
            terminal=False,
            last_seq=True,  # bool is not a seq
            projected_status="running",
        )
    with pytest.raises(SpineError):
        SessionStatus(
            task_id="task_alpha",
            session_id="sess_1",
            state="running",
            alive=True,
            terminal=False,
            last_seq=2,
            projected_status="not_a_status",
        )


def test_validate_session_status_rejects_forged_instance() -> None:
    forged = object.__new__(SessionStatus)
    object.__setattr__(forged, "task_id", "task_alpha")
    object.__setattr__(forged, "session_id", "sess_1")
    object.__setattr__(forged, "state", "running")
    object.__setattr__(forged, "alive", True)
    object.__setattr__(forged, "terminal", True)  # running is not terminal
    object.__setattr__(forged, "last_seq", 1)
    object.__setattr__(forged, "projected_status", "running")
    with pytest.raises(SpineError):
        validate_session_status(forged)
