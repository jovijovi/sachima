"""ARS-INT — one-call execution binding bundle (port+dispatcher+display chain).

Tests for :func:`bind_agent_run_supervisor_execution`: the composition root
that builds the full formal seam (registry + real library backend + port +
turn dispatcher + source bindings + LS4-A-gated query service + display
service) from one validated config. Default-off posture is preserved at every
layer: a disabled config refuses to compose; a composed bundle without an
explicit activation gate keeps the query/display chain fail-closed. Pure
local/offline; the library is reached only through an injected facade double
(plus one real-reader test that skips when the pinned extra is absent).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sachima_supervisor.runtime_spine import (
    RUNTIME_LIVE_PROGRESS_QUERY_DISABLED,
    SpineError,
    build_launch_spec,
    hermes_internal_query_gate,
    scan_for_leak,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
    AgentRunSupervisorExecutionBinding,
    bind_agent_run_supervisor_execution,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend import (
    ARS_LIBRARY_CONFIG_TYPE,
    RUNTIME_ARS_LIBRARY_DISABLED,
    AgentRunSupervisorLibraryConfig,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_turn_dispatcher import (
    RUNTIME_INVALID_TURN_DISPATCH,
    TurnDispatchRequest,
)

# --------------------------------------------------------------------------- #
# Rig: config + facade double whose turns emit REAL synthetic artifacts
# --------------------------------------------------------------------------- #


def _role_mapping() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "role_id": "readonly-reviewer",
        "runner": {"type": "acpx", "acpx_version": "0.12.0", "acpx_binary": None},
        "permissions": {"read": True, "search": True},
        "session": {"strategy": "persistent"},
    }


def _config(tmp_path: Path, *, enabled: bool = True) -> AgentRunSupervisorLibraryConfig:
    binary = tmp_path / "bin" / "acpx"
    binary.parent.mkdir(exist_ok=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    return AgentRunSupervisorLibraryConfig(
        type=ARS_LIBRARY_CONFIG_TYPE,
        enabled=enabled,
        approval_ref="approval_arsint_s3",
        sessions_dir=str(tmp_path / "sessions"),
        workspace_by_ref={"ws_arsint": str(work)},
        role_by_ref={"policy_read_only": _role_mapping()},
        session_prefix="sachima",
        acpx_binary=str(binary),
        stale_after_seconds=900,
    )


def _view() -> SimpleNamespace:
    return SimpleNamespace(
        exists=True,
        state="open",
        lease_held=False,
        holder_liveness=None,
        lease_recoverable=False,
        latest_turn_status=None,
        progress=None,
    )


class _ArtifactFacade:
    """Facade double whose ``send`` writes a real synthetic ARS turn dir."""

    def __init__(self, turns_root: Path) -> None:
        self._turns_root = turns_root
        self.records: dict[str, SimpleNamespace] = {}
        self.views: dict[str, SimpleNamespace] = {}
        self.turn_seq = 0

    def load_role(self, mapping):
        return SimpleNamespace(role_id=mapping.get("role_id", "role"))

    def role_hash(self, role) -> str:
        return f"hash_{role.role_id}"

    def validate_workspace(self, role, work_dir: str):
        return SimpleNamespace(effective_cwd=work_dir)

    def open_record(self, sessions_dir, ars_session_id):
        return self.records.get(ars_session_id)

    def binding_matches(self, sessions_dir, record, role, workspace) -> bool:
        return True

    def create_session(self, sessions_dir, role, ars_session_id, session_name, work_dir):
        self.records[ars_session_id] = SimpleNamespace(
            state="open", role_hash=self.role_hash(role)
        )
        self.views.setdefault(ars_session_id, _view())

    def send(self, sessions_dir, role, ars_session_id, prompt, work_dir):
        self.turn_seq += 1
        turn_id = f"turn_20260709T10000{self.turn_seq}Z_ab12cd3{self.turn_seq}"
        turn_dir = self._turns_root / turn_id
        turn_dir.mkdir(parents=True)
        events = [
            {"seq": 1, "type": "run_started", "family": "run_started", "kind": None,
             "status": "running", "text_length": 0, "summary": "s"},
            {"seq": 2, "type": "agent_message", "family": "agent_message",
             "kind": "assistant", "status": "running", "text_length": len(prompt),
             "summary": "s"},
        ]
        (turn_dir / "normalized-events.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
        )
        (turn_dir / "progress.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "state": "completed",
                    "last_seq": 2,
                    "event_count": 2,
                    "updated_at": "2026-07-09T10:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        return (turn_id, str(turn_dir), "completed")

    def abort(self, sessions_dir, role, ars_session_id, work_dir) -> bool:
        return True

    def close(self, sessions_dir, role, ars_session_id, work_dir) -> None:
        record = self.records.get(ars_session_id)
        if record is not None:
            record.state = "closed"

    def compile_goal(self, role, goal_text: str) -> str:
        return f"[goal-contract/v1] Standing goal:\n\n{goal_text}"

    def inspect(self, sessions_dir, ars_session_id):
        return self.views.get(ars_session_id)


class _FakeReader:
    """Offline stand-in for the ARS caller events reader (same shapes)."""

    def load_progress(self, artifact_dir: str):
        payload = json.loads(
            (Path(artifact_dir) / "progress.json").read_text(encoding="utf-8")
        )
        return SimpleNamespace(**payload)

    def read_event_page(self, artifact_dir: str, *, after_seq=None, limit: int = 100):
        records = []
        events_file = Path(artifact_dir) / "normalized-events.jsonl"
        for line in events_file.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if after_seq is not None and event["seq"] <= after_seq:
                continue
            records.append(
                SimpleNamespace(
                    seq=event["seq"],
                    family=event["family"],
                    kind=event["kind"],
                    status=event["status"],
                    text_length=event["text_length"],
                    summary=event["summary"],
                )
            )
        page = records[:limit]
        return SimpleNamespace(
            records=tuple(page),
            next_cursor=page[-1].seq if page else after_seq,
            has_more=len(records) > limit,
        )


def _bundle(tmp_path: Path, *, gate=None, payload_resolver=None, reader=None):
    facade = _ArtifactFacade(tmp_path / "turns")
    bundle = bind_agent_run_supervisor_execution(
        _config(tmp_path),
        gate=gate,
        payload_resolver=payload_resolver,
        facade=facade,
        progress_reader=reader if reader is not None else _FakeReader(),
    )
    return bundle, facade


def _attach(bundle) -> Any:
    return bundle.port.create_or_attach(
        "task_alpha",
        build_launch_spec(
            task_id="task_alpha",
            agent_kind="local_agent",
            mode_flags={"needs_agent": True},
            roles=("read_only",),
            refs=("ws_arsint", "policy_read_only"),
        ),
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_disabled_config_refuses_to_compose(tmp_path: Path) -> None:
    with pytest.raises(SpineError) as exc:
        bind_agent_run_supervisor_execution(_config(tmp_path, enabled=False))
    assert exc.value.code == RUNTIME_ARS_LIBRARY_DISABLED


def test_bundle_composes_shared_spine_objects(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    assert isinstance(bundle, AgentRunSupervisorExecutionBinding)
    assert bundle.query_service.bindings is bundle.bindings
    assert bundle.query_service.registry is bundle.registry
    assert bundle.query_service.port is bundle.port
    assert bundle.display_service.query_service is bundle.query_service


def test_query_chain_stays_default_off_without_gate(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    with pytest.raises(SpineError) as exc:
        bundle.query_service.query_task_live_progress("task_alpha", "sess_1")
    assert exc.value.code == RUNTIME_LIVE_PROGRESS_QUERY_DISABLED


def test_dispatch_stays_fail_closed_without_payload_resolver(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path, gate=hermes_internal_query_gate())
    ref = _attach(bundle)
    request = TurnDispatchRequest(
        task_id="task_alpha",
        session_id=ref.session_id,
        turn_kind="goal",
        payload_ref="payload_goal_1",
    )
    with pytest.raises(SpineError) as exc:
        bundle.dispatcher.dispatch(request)
    assert exc.value.code == RUNTIME_INVALID_TURN_DISPATCH


def test_dispatched_turn_feeds_display_chain_end_to_end(tmp_path: Path) -> None:
    payloads = {"payload_goal_1": "ship the integration"}
    bundle, _ = _bundle(
        tmp_path, gate=hermes_internal_query_gate(), payload_resolver=payloads.__getitem__
    )
    ref = _attach(bundle)
    outcome = bundle.dispatcher.dispatch(
        TurnDispatchRequest(
            task_id="task_alpha",
            session_id=ref.session_id,
            turn_kind="goal",
            payload_ref="payload_goal_1",
        )
    )
    assert outcome.supervisor_status == "completed"

    display = bundle.display_service.display_task_live_progress(
        "task_alpha", ref.session_id
    )
    payload = display.as_dict()
    assert payload["task_id"] == "task_alpha"
    assert payload["session_id"] == ref.session_id
    assert payload["artifact_ref"] == outcome.artifact_ref
    assert payload["progress_available"] is True
    assert payload["observed_event_count"] == 2
    assert isinstance(payload["display_lines"], list) and payload["display_lines"]
    assert scan_for_leak(payload) is None
    assert str(tmp_path) not in json.dumps(payload)

    # Explicit cursor advancement stays the caller's move and the next
    # dispatch resets it with the fresh turn binding.
    bundle.bindings.update_last_seen_cursor("task_alpha", 2, ref.session_id)
    second = bundle.dispatcher.dispatch(
        TurnDispatchRequest(
            task_id="task_alpha",
            session_id=ref.session_id,
            turn_kind="goal",
            payload_ref="payload_goal_1",
        )
    )
    source = bundle.bindings.resolve_source("task_alpha", ref.session_id)
    assert source.artifact_ref == second.artifact_ref
    assert source.last_seen_cursor is None


def test_real_reader_display_chain(tmp_path: Path) -> None:
    pytest.importorskip(
        "agent_run_supervisor.hermes_caller.events",
        reason="pinned agent-run-supervisor extra not installed",
    )
    from sachima_supervisor.runtime_spine import DefaultLiveProgressReader

    payloads = {"payload_goal_1": "ship the integration"}
    bundle, _ = _bundle(
        tmp_path,
        gate=hermes_internal_query_gate(),
        payload_resolver=payloads.__getitem__,
        reader=DefaultLiveProgressReader(),
    )
    ref = _attach(bundle)
    outcome = bundle.dispatcher.dispatch(
        TurnDispatchRequest(
            task_id="task_alpha",
            session_id=ref.session_id,
            turn_kind="prompt",
            payload_ref="payload_goal_1",
        )
    )
    display = bundle.display_service.display_task_live_progress(
        "task_alpha", ref.session_id
    )
    payload = display.as_dict()
    assert payload["artifact_ref"] == outcome.artifact_ref
    assert payload["progress_available"] is True
    assert payload["observed_event_count"] == 2
    assert payload["resume_cursor"] in (2, None)
    assert scan_for_leak(payload) is None
