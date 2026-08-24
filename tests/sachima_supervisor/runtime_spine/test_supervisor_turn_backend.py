"""ARS 0.7.6 P3 — neutral validated turn backend contract acceptance tests.

Focused RED/GREEN tests for the P3 slice of the ARS 0.7.6 Socket API v3
integration plan (``docs/plans/2026-08-17-ars-0.7.6-socket-api-v3-integration-plan.md``
§9): one Sachima-owned neutral turn seam replaces both concrete-type couplings,
and the library-private ``turn_dir`` leaves the tree provably (review closure
R-3).

What is proven here:

* the **bare-identifier** absence guard for ``turn_dir`` over
  ``sachima_supervisor/``, ``gateway/``, and ``scripts/`` (§9.2 — the plural
  ``turn_dirs`` locals in the E2 smoke script are deliberately *not* hits);
* the neutral result carries exactly five safe fields — no path, no raw id —
  through its repr **and** its serialized projection;
* the private locator rides only on the dispatched handoff;
* the factory allowlist is an **exact-type** check: a protocol-shaped duck type
  and a hostile subclass are both refused at a composition root, while the
  allowlisted concrete backend is admitted;
* the closed library-to-neutral status collapse covers the whole library
  vocabulary and lands only inside the neutral set;
* every P3-touched module imports with **no** ``agent_run_supervisor`` import.

Everything is pure local/offline Python: no socket, no daemon, no network, no
``agent_run_supervisor`` import, no process or real AGENT. Forbidden terms below
are no-leak canaries only, never behavior.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

from sachima_supervisor.runtime_spine.events import SpineError, scan_for_leak

# --------------------------------------------------------------------------- #
# Lazy module handles — the P3 module must not be needed to collect this file,
# so the R-3 guard below fails for its own stated reason and never on import.
# --------------------------------------------------------------------------- #
_TURN_BACKEND_MODULE = "sachima_supervisor.runtime_spine.supervisor_turn_backend"
def _mod():
    return importlib.import_module(_TURN_BACKEND_MODULE)


def _repo_root() -> Path:
    # tests/sachima_supervisor/runtime_spine/<this file> -> repo root
    return Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- #
# A. R-3 — the turn_dir removal cannot pass vacuously
# --------------------------------------------------------------------------- #
#: The guard matches the BARE identifier only (§9.2). ``turn_dirs`` /
#: ``sorted_turn_dirs`` in scripts/ are a different defect with a different
#: owner (P5 / S-6) and a different guard (B-10) — calling them turn_dir hits
#: would simply be untrue.
_BARE_TURN_DIR = re.compile(r"(?<![A-Za-z0-9_])turn_dir(?![A-Za-z0-9_])")
_GUARD_ROOTS = ("sachima_supervisor", "gateway", "scripts")


def _bare_turn_dir_hits() -> list[str]:
    root = _repo_root()
    hits: list[str] = []
    for top in _GUARD_ROOTS:
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if _BARE_TURN_DIR.search(line) is not None:
                    hits.append(f"{path.relative_to(root)}:{lineno}")
    return hits


def test_no_turn_dir_reference_in_runtime_source() -> None:
    """No library- or daemon-private turn directory on Sachima's caller contract."""

    hits = _bare_turn_dir_hits()
    assert hits == [], (
        "bare-identifier `turn_dir` must not survive P3 anywhere under "
        f"{'/, '.join(_GUARD_ROOTS)}/: {hits}"
    )


def test_turn_dir_guard_matches_the_bare_identifier_and_not_the_plural() -> None:
    """The guard's own regex is the thing under test (§9.2)."""

    assert _BARE_TURN_DIR.search("outcome.turn_dir") is not None
    assert _BARE_TURN_DIR.search("turn_dir = x") is not None
    assert _BARE_TURN_DIR.search("turn_dirs = x") is None
    assert _BARE_TURN_DIR.search("sorted_turn_dirs") is None
    assert _BARE_TURN_DIR.search("my_turn_dir_2") is None


# --------------------------------------------------------------------------- #
# B. The neutral result — exactly five safe fields, no path, no raw id
# --------------------------------------------------------------------------- #
_SAFE_RUN_REF = "turn_1_ab12cd34"


def _result(mod, **overrides):
    fields = {
        "run_ref": _SAFE_RUN_REF,
        "source_kind": mod.SOURCE_KIND_ARTIFACT_FILE,
        "source_ref": _SAFE_RUN_REF,
        "supervisor_status": "completed",
        "foreign_cursor": None,
    }
    fields.update(overrides)
    return mod.SupervisorTurnResult(**fields)


def test_supervisor_turn_result_has_exactly_the_five_safe_fields() -> None:
    import dataclasses

    mod = _mod()
    names = tuple(f.name for f in dataclasses.fields(mod.SupervisorTurnResult))
    assert names == (
        "run_ref",
        "source_kind",
        "source_ref",
        "supervisor_status",
        "foreign_cursor",
    )
    result = _result(mod)
    assert result.as_dict() == {
        "run_ref": _SAFE_RUN_REF,
        "source_kind": "artifact_file",
        "source_ref": _SAFE_RUN_REF,
        "supervisor_status": "completed",
        "foreign_cursor": None,
    }
    # The removed field is structurally absent, not merely unset.
    assert not hasattr(result, "turn_dir")
    assert "turn_dir" not in result.as_dict()


def test_supervisor_turn_result_fails_closed_on_forged_fields() -> None:
    mod = _mod()
    for overrides in (
        {"run_ref": "/tmp/private/turns/turn_1"},  # a path is not a safe ref
        {"run_ref": "turn 1"},
        {"source_kind": "daemon_dir"},
        {"source_ref": ""},
        {"supervisor_status": "did_great"},
        {"supervisor_status": "no_op"},  # library vocabulary, not the neutral set
        {"foreign_cursor": -1},
        {"foreign_cursor": True},
        {"foreign_cursor": "3"},
    ):
        with pytest.raises(SpineError) as exc:
            _result(mod, **overrides)
        assert exc.value.code == mod.RUNTIME_INVALID_SUPERVISOR_TURN
        assert "did_great" not in str(exc.value)

    forged = object.__new__(mod.SupervisorTurnResult)
    object.__setattr__(forged, "run_ref", _SAFE_RUN_REF)
    object.__setattr__(forged, "source_kind", "daemon_dir")
    object.__setattr__(forged, "source_ref", _SAFE_RUN_REF)
    object.__setattr__(forged, "supervisor_status", "completed")
    object.__setattr__(forged, "foreign_cursor", None)
    with pytest.raises(SpineError):
        mod.validate_supervisor_turn_result(forged)


def test_private_locator_rides_only_on_the_dispatched_handoff() -> None:
    mod = _mod()
    private = "/tmp/private/ars-sessions/sess_a/turns/turn_001"
    result = _result(mod)
    handoff = mod.DispatchedSupervisorTurn(result=result, private_locator=private)

    assert handoff.private_locator == private
    # The safe half never carries it, in any surface.
    assert private not in repr(result)
    assert private not in str(result)
    assert private not in json.dumps(result.as_dict())
    blob = mod.serialize_supervisor_turn_result(result)
    assert private.encode("utf-8") not in blob
    for marker in (b"/tmp/", b"/home/", b"turns", b"turn_dir"):
        assert marker not in blob
    assert scan_for_leak(json.loads(blob)) is None
    # The handoff opts out of repr and offers no serialize surface at all.
    assert private not in repr(handoff)
    assert not hasattr(handoff, "as_dict")
    assert not hasattr(mod, "serialize_dispatched_supervisor_turn")
    # A missing/empty locator is refused; the safe half is re-validated.
    with pytest.raises(SpineError):
        mod.DispatchedSupervisorTurn(result=result, private_locator="")
    with pytest.raises(SpineError):
        mod.DispatchedSupervisorTurn(result=object(), private_locator=private)


# --------------------------------------------------------------------------- #
# C. The factory allowlist — exact type, never a duck type
# --------------------------------------------------------------------------- #
def _arsd_backend(tmp_path):
    """A really-composed ``arsd`` backend (the allowlist's only entry).

    Composed offline against an injected facade double: constructing the
    backend negotiates the contract and nothing else, so this opens no socket
    and reaches no daemon.
    """

    from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import (
        ArsdRunBindingLedger,
    )
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_SUPERVISOR_CONFIG_TYPE,
        ArsdSupervisorConfig,
    )

    arsd = importlib.import_module(
        "sachima_supervisor.runtime_spine.arsd_supervisor_backend"
    )
    work = tmp_path / "ws"
    work.mkdir(exist_ok=True)

    class _Facade:
        def server_info(self):
            return {
                "version": "0.7.8",
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
                    "max_concurrent_runs": 4,
                    "max_frame_bytes": 1_048_576,
                    "max_prompt_bytes": 262_144,
                    "events_page_limit": 256,
                    "event_follow_queue_size": 1024,
                    "max_run_event_budget_bytes": 2_147_483_648,
                },
            }

        def submit(self, *, request_id, payload):  # pragma: no cover - unused
            raise AssertionError("no submit in an allowlist test")

        def run_status(self, run_id):  # pragma: no cover - unused
            raise AssertionError("no observation in an allowlist test")

        def run_events(self, run_id, *, from_seq, limit=None):  # pragma: no cover
            raise AssertionError("no observation in an allowlist test")

        def run_cancel(self, run_id):  # pragma: no cover - unused
            raise AssertionError("no cancel in an allowlist test")

        def session_status(self, session_id):  # pragma: no cover - unused
            raise AssertionError("no session read in an allowlist test")

        def session_list(self):  # pragma: no cover - unused
            raise AssertionError("no session read in an allowlist test")

        def agent_list(self):  # pragma: no cover - unused
            raise AssertionError("no roster read in an allowlist test")

    config = ArsdSupervisorConfig(
        type=ARSD_SUPERVISOR_CONFIG_TYPE,
        approval_ref="approval_arsd_allowlist_offline",
        owner="sachima_host",
        namespace="sachima_tasks",
        socket_path=str(tmp_path / "private" / "arsd.sock"),
        binding_ledger_path=str(tmp_path / "arsd-run-bindings.json"),
        agent_by_policy_ref={"policy_agent": "reader-agent"},
        model_by_policy_ref={"policy_model": "claude-sonnet-5"},
        effort_by_policy_ref={"policy_effort": "medium"},
        workspace_by_ref={"ws_arsint": str(work)},
        run_limits_by_policy_ref={
            "policy_limits": {
                "startup_timeout_seconds": 60.0,
                "turn_timeout_seconds": 600.0,
                "cancel_grace_seconds": 10.0,
                "max_stderr_bytes": 262_144,
                "max_event_bytes": 65_536,
                "max_events": 10_000,
            }
        },
        grant_ref="grant_reader_v1",
        grant_hash="sha256:" + "a" * 64,
        grant_role_hash="sha256:" + "b" * 64,
        grant_capabilities=("read", "search"),
        mcp_snapshot_hashes=("sha256:" + "c" * 64,),
        credential_refs=("cred_reader_github",),
        evidence_policy_hash="sha256:" + "d" * 64,
        recovery_policy_hash="sha256:" + "e" * 64,
        enabled=True,
    )
    ledger = ArsdRunBindingLedger(str(tmp_path / "ledger.json"))
    return arsd.ArsdSupervisorBackend(config, _Facade(), ledger)


def test_factory_allowlist_admits_the_composed_arsd_backend(tmp_path) -> None:
    """Positive control: the allowlist is not vacuously refusing everything."""

    mod = _mod()
    backend = _arsd_backend(tmp_path)
    assert mod.validate_supervisor_turn_backend(backend) is backend


class _ProtocolShapedDuck:
    """Structurally a ``SupervisorTurnBackend``, and still not admissible."""

    def create_or_attach(self, task_id, refs): ...
    def attach_existing(self, task_id): ...
    def run_turn(self, task_id, *, turn_kind, payload_text, dispatch_ref, payload_ref): ...
    def recover_uncertain_submission(self, task_id, dispatch_ref): ...
    def latest_accepted_turn(self, task_id): ...
    def accepted_turn_for_binding(self, task_id, binding, *, session_ref): ...
    def rehydrate_pending_intent(self, task_id, dispatch_ref): ...
    def cancel_run(self, handle): ...

    @property
    def task_locks(self): ...

    def status(self, handle): ...
    def signal(self, handle, decision_ref): ...
    def kill(self, handle, reason_ref): ...
    def liveness(self, handle): ...


def test_factory_allowlist_refuses_a_protocol_shaped_duck_type() -> None:
    mod = _mod()
    duck = _ProtocolShapedDuck()
    # Non-vacuity: the duck really does satisfy the protocol structurally.
    assert isinstance(duck, mod.SupervisorTurnBackend)
    with pytest.raises(SpineError) as exc:
        mod.validate_supervisor_turn_backend(duck)
    assert exc.value.code == mod.RUNTIME_INVALID_SUPERVISOR_TURN
    assert "_ProtocolShapedDuck" not in str(exc.value)


def test_factory_allowlist_refuses_a_hostile_subclass(tmp_path) -> None:
    mod = _mod()
    arsd = importlib.import_module(
        "sachima_supervisor.runtime_spine.arsd_supervisor_backend"
    )

    class _HostileSubclass(arsd.ArsdSupervisorBackend):
        def run_turn(self, task_id, *, turn_kind, payload_text, dispatch_ref, payload_ref):
            raise AssertionError("a subclass must never reach a composition root")

    backend = _arsd_backend(tmp_path)
    hostile = object.__new__(_HostileSubclass)
    hostile.__dict__.update(backend.__dict__)
    assert isinstance(hostile, arsd.ArsdSupervisorBackend)
    with pytest.raises(SpineError) as exc:
        mod.validate_supervisor_turn_backend(hostile)
    assert exc.value.code == mod.RUNTIME_INVALID_SUPERVISOR_TURN

    for junk in (None, object(), arsd.ArsdSupervisorBackend):
        with pytest.raises(SpineError):
            mod.validate_supervisor_turn_backend(junk)


# --------------------------------------------------------------------------- #
# D. The retired library -> neutral status collapse
# --------------------------------------------------------------------------- #
def test_the_library_status_collapse_is_retired_with_its_backend() -> None:
    """No vocabulary survives its speaker.

    ``collapse_library_turn_status`` existed to translate the library backend's
    own turn statuses into the neutral set. That backend is retired (plan §11,
    seam S-1), so the translation is retired with it rather than left as a
    function nothing can produce input for. The neutral vocabulary itself is
    unchanged — it is the transport-neutral contract, not the library's.
    """

    mod = _mod()
    assert not hasattr(mod, "collapse_library_turn_status")
    assert not hasattr(mod, "_LIBRARY_TO_NEUTRAL_STATUS")
    assert "collapse_library_turn_status" not in mod.__all__

    assert set(mod.SUPERVISOR_TURN_STATUSES) == {
        "accepted",
        "completed",
        "failed",
        "cancelled",
        "timed_out",
        "unknown",
    }


def test_factory_allowlist_admits_the_arsd_backend_kind_without_enabling_it() -> None:
    """After P5 the allowlist is exactly one KIND — never an enabled backend."""

    mod = _mod()
    kinds = [kind for kind, _module, _attribute in mod._BACKEND_FACTORY_ALLOWLIST]
    assert kinds == ["arsd"]

    arsd = importlib.import_module(
        "sachima_supervisor.runtime_spine.arsd_supervisor_backend"
    )
    assert arsd.ArsdSupervisorBackend in mod._allowed_backend_types()

    # Admissible is not composed: a subclass of it is still refused, and no
    # composition root in the tree builds one.
    class _HostileArsd(arsd.ArsdSupervisorBackend):
        pass

    with pytest.raises(SpineError):
        mod.validate_supervisor_turn_backend(object.__new__(_HostileArsd))


def test_source_kinds_are_the_closed_tagged_pair() -> None:
    mod = _mod()
    assert mod.SOURCE_KIND_ARTIFACT_FILE == "artifact_file"
    assert mod.SOURCE_KIND_ARSD_RUN == "arsd_run"
    assert set(mod.SUPERVISOR_SOURCE_KINDS) == {"artifact_file", "arsd_run"}


def test_derive_turn_ref_is_owned_here_and_re_exported_compatibly() -> None:
    mod = _mod()
    dispatcher = importlib.import_module(
        "sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher"
    )
    spine = importlib.import_module("sachima_supervisor.runtime_spine")

    assert dispatcher.derive_turn_ref is mod.derive_turn_ref
    assert spine.derive_turn_ref is mod.derive_turn_ref
    assert "derive_turn_ref" in dispatcher.__all__
    assert "derive_turn_ref" in mod.__all__

    raw = "TURN_20260817T100000Z_AB12CD34"
    ref = mod.derive_turn_ref(1, raw)
    assert ref.startswith("turn_1_") and raw not in ref
    assert ref == mod.derive_turn_ref(1, raw)
    for bad in ((0, raw), (1, ""), ("1", raw), (1, None)):
        with pytest.raises(SpineError):
            mod.derive_turn_ref(*bad)


def test_turn_backend_stable_codes_are_closed_and_module_local() -> None:
    mod = _mod()
    assert mod.RUNTIME_INVALID_SUPERVISOR_TURN == "runtime_invalid_supervisor_turn"
    assert set(mod.SUPERVISOR_TURN_STABLE_CODES) == {"runtime_invalid_supervisor_turn"}


# --------------------------------------------------------------------------- #
# E. Import purity across every module P3 touches (extended in P4/P5)
# --------------------------------------------------------------------------- #
_TOUCHED_MODULES = (
    "sachima_supervisor.runtime_spine.supervisor_turn_backend",
    # Extended in P4: the arsd backend and the de-ARS'd offline reader.
    "sachima_supervisor.runtime_spine.arsd_supervisor_backend",
    "sachima_supervisor.runtime_spine.live_progress_projection",
    # Extended in P5: the migration seam, the retired offline seams, and the
    # composition root that now wires the socket adapter.
    "sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend",
    "sachima_supervisor.local_offline",
    "sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher",
    "sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding",
    "sachima_supervisor.runtime_spine.live_progress_sources",
    "sachima_supervisor.activity_session_real_execution",
)


def test_touched_modules_import_without_agent_run_supervisor() -> None:
    for name in list(sys.modules):
        if name.startswith("agent_run_supervisor"):
            del sys.modules[name]
    for name in _TOUCHED_MODULES:
        importlib.import_module(name)
    leaked = [name for name in sys.modules if name.startswith("agent_run_supervisor")]
    assert leaked == [], (
        "every P3-touched module must reach the library lazily, never at "
        f"import: {leaked}"
    )
