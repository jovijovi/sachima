"""R4 — platform-neutral user-visible task view model (design §4/§6/§8, plan §8).

RED/GREEN tests for the future ``view_model`` module. The view model is the
user-visible, platform-neutral projection surface derived from the R1 Event Log /
Status Projection. It is deterministic and refs-only: it may expose stable status,
counts, flags, safe refs, permission-wait state, and stable error codes, but it
must never carry raw prompt/context/tool output/agent stdout/raw exception/card
JSON/platform IDs/private paths, nor call Gateway/Feishu/send/edit/delivery.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from sachima_supervisor.runtime_spine import (
    SpineError,
    TaskRegistry,
    build_event_body,
    scan_for_leak,
)

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


def _view_model_mod():
    return importlib.import_module("sachima_supervisor.runtime_spine.view_model")


def _registry_with_permission_wait() -> TaskRegistry:
    registry = TaskRegistry()
    registry.create_task("task_alpha", needs_agent=True, needs_durable=True, refs=("ref_plan",))
    registry.append_event(
        "task_alpha",
        build_event_body(
            event_type="agent_attached",
            status="running",
            refs=("sess_1", "ref_launch"),
        ),
    )
    registry.append_event(
        "task_alpha",
        build_event_body(
            event_type="permission_requested",
            status="permission_wait",
            refs=("sess_1", "permission_prompt_ref_1"),
        ),
    )
    return registry


# --------------------------------------------------------------------------- #
# A. Public surface and stable error family
# --------------------------------------------------------------------------- #
def test_view_model_public_surface_is_exported() -> None:
    mod = _view_model_mod()
    assert mod.RUNTIME_INVALID_VIEW_MODEL == "runtime_invalid_view_model"
    assert mod.RUNTIME_INVALID_VIEW_MODEL in mod.VIEW_MODEL_STABLE_CODES
    assert mod.VIEW_MODEL_TYPE == "sachima.runtime_spine.task_view_model.v1"
    for name in (
        "TaskViewModel",
        "build_task_view_model",
        "validate_task_view_model",
        "serialize_task_view_model",
    ):
        assert hasattr(mod, name)


def test_view_model_symbols_available_from_runtime_spine_package() -> None:
    runtime_spine = importlib.import_module("sachima_supervisor.runtime_spine")
    for name in (
        "RUNTIME_INVALID_VIEW_MODEL",
        "VIEW_MODEL_TYPE",
        "TaskViewModel",
        "build_task_view_model",
        "serialize_task_view_model",
    ):
        assert hasattr(runtime_spine, name)


# --------------------------------------------------------------------------- #
# B. Deterministic, platform-neutral projection surface
# --------------------------------------------------------------------------- #
def test_build_task_view_model_is_deterministic_from_event_log_projection() -> None:
    mod = _view_model_mod()
    registry = _registry_with_permission_wait()

    view1 = mod.build_task_view_model(registry, "task_alpha")
    view2 = mod.build_task_view_model(registry, "task_alpha")
    assert type(view1) is mod.TaskViewModel
    assert view1 == view2
    assert mod.serialize_task_view_model(view1) == mod.serialize_task_view_model(view2)

    data = view1.as_dict()
    assert data["type"] == mod.VIEW_MODEL_TYPE
    assert data["task_id"] == "task_alpha"
    assert data["status"] == "permission_wait"
    assert data["permission_state"] == "waiting"
    assert data["requires_operator_decision"] is True
    assert data["flags"] == {"needs_agent": True, "needs_durable": True}
    assert data["refs"] == sorted({"ref_plan", "ref_launch", "sess_1", "permission_prompt_ref_1"})
    assert data["surfaces"] == ["status", "permission"]
    assert scan_for_leak(data) is None


def test_view_model_for_completed_task_is_terminal_without_permission_surface() -> None:
    mod = _view_model_mod()
    registry = TaskRegistry()
    registry.create_task("task_alpha", needs_agent=True)
    registry.append_event(
        "task_alpha",
        build_event_body(
            event_type="completed",
            status="completed",
            refs=("sess_1", "result_ref_1"),
        ),
    )
    view = mod.build_task_view_model(registry, "task_alpha")
    data = view.as_dict()
    assert data["status"] == "completed"
    assert data["terminal"] is True
    assert data["permission_state"] == "none"
    assert data["requires_operator_decision"] is False
    assert data["surfaces"] == ["status"]


def test_build_task_view_model_unknown_task_fails_closed() -> None:
    mod = _view_model_mod()
    registry = TaskRegistry()
    with pytest.raises(SpineError) as exc:
        mod.build_task_view_model(registry, "task_missing")
    assert exc.value.code == mod.RUNTIME_INVALID_VIEW_MODEL


# --------------------------------------------------------------------------- #
# C. No-leak / platform-neutral trust boundary
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("canary", _LEAK_CANARIES)
def test_task_view_model_direct_construction_rejects_raw_or_platform_refs(canary: str) -> None:
    mod = _view_model_mod()
    with pytest.raises(SpineError) as exc:
        mod.TaskViewModel(
            type=mod.VIEW_MODEL_TYPE,
            task_id="task_alpha",
            status="running",
            terminal=False,
            last_seq=1,
            event_count=1,
            flags={"needs_agent": True, "needs_durable": False},
            refs=[f"ref_{canary}_x"],
            surfaces=["status"],
            permission_state="none",
            requires_operator_decision=False,
            error_code=None,
        )
    assert exc.value.code == mod.RUNTIME_INVALID_VIEW_MODEL
    assert canary not in str(exc.value)


def test_validate_task_view_model_rejects_forged_mutable_or_unsorted_shape() -> None:
    mod = _view_model_mod()
    forged = object.__new__(mod.TaskViewModel)
    for name, value in (
        ("type", mod.VIEW_MODEL_TYPE),
        ("task_id", "task_alpha"),
        ("status", "permission_wait"),
        ("terminal", False),
        ("last_seq", 3),
        ("event_count", 3),
        ("flags", {"needs_agent": True, "needs_durable": False}),
        ("refs", ["permission_prompt_ref_1", "ref_plan", "permission_prompt_ref_1"]),
        ("surfaces", ["permission", "status"]),
        ("permission_state", "waiting"),
        ("requires_operator_decision", True),
        ("error_code", None),
    ):
        object.__setattr__(forged, name, value)
    assert type(forged) is mod.TaskViewModel
    with pytest.raises(SpineError) as exc:
        mod.validate_task_view_model(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_VIEW_MODEL


def test_task_view_model_cannot_be_mutated_to_echo_raw_material() -> None:
    mod = _view_model_mod()
    registry = _registry_with_permission_wait()
    view = mod.build_task_view_model(registry, "task_alpha")
    with pytest.raises((AttributeError, TypeError, SpineError)):
        view.refs.append("raw_prompt_dump")
    assert "raw_prompt" not in str(view.as_dict())
    assert scan_for_leak(view.as_dict()) is None


class _EqualitySpoof:
    def __init__(self, target: str) -> None:
        self.target = target

    def __hash__(self) -> int:
        return hash(self.target)

    def __eq__(self, other: object) -> bool:
        return other == self.target

    def __repr__(self) -> str:
        return "raw_prompt_spoof"


@pytest.mark.parametrize(
    ("field", "target"),
    (
        ("type", "sachima.runtime_spine.task_view_model.v1"),
        ("status", "running"),
        ("permission_state", "none"),
        ("error_code", "runtime_invalid_event"),
    ),
)
def test_task_view_model_rejects_equality_spoof_string_fields(field: str, target: str) -> None:
    mod = _view_model_mod()
    values = {
        "type": mod.VIEW_MODEL_TYPE,
        "task_id": "task_alpha",
        "status": "running",
        "terminal": False,
        "last_seq": 1,
        "event_count": 1,
        "flags": {"needs_agent": True, "needs_durable": False},
        "refs": ["ref_plan"],
        "surfaces": ["status"],
        "permission_state": "none",
        "requires_operator_decision": False,
        "error_code": None,
    }
    values[field] = _EqualitySpoof(target)
    with pytest.raises(SpineError) as exc:
        mod.TaskViewModel(**values)
    assert exc.value.code == mod.RUNTIME_INVALID_VIEW_MODEL
    assert "raw_prompt" not in str(exc.value)


def test_task_view_model_rejects_equality_spoof_surface_and_flag_keys() -> None:
    mod = _view_model_mod()
    for values in (
        {
            "type": mod.VIEW_MODEL_TYPE,
            "task_id": "task_alpha",
            "status": "running",
            "terminal": False,
            "last_seq": 1,
            "event_count": 1,
            "flags": {_EqualitySpoof("needs_agent"): True, "needs_durable": False},
            "refs": ["ref_plan"],
            "surfaces": ["status"],
            "permission_state": "none",
            "requires_operator_decision": False,
            "error_code": None,
        },
        {
            "type": mod.VIEW_MODEL_TYPE,
            "task_id": "task_alpha",
            "status": "running",
            "terminal": False,
            "last_seq": 1,
            "event_count": 1,
            "flags": {"needs_agent": True, "needs_durable": False},
            "refs": ["ref_plan"],
            "surfaces": [_EqualitySpoof("status")],
            "permission_state": "none",
            "requires_operator_decision": False,
            "error_code": None,
        },
    ):
        with pytest.raises(SpineError) as exc:
            mod.TaskViewModel(**values)
        assert exc.value.code == mod.RUNTIME_INVALID_VIEW_MODEL
        assert "raw_prompt" not in str(exc.value)


def test_as_dict_revalidates_before_serializing_mutable_forgery() -> None:
    mod = _view_model_mod()
    forged = object.__new__(mod.TaskViewModel)
    for name, value in (
        ("type", mod.VIEW_MODEL_TYPE),
        ("task_id", "task_alpha"),
        ("status", "running"),
        ("terminal", False),
        ("last_seq", 1),
        ("event_count", 1),
        ("flags", {"needs_agent": True, "needs_durable": False}),
        ("refs", ["raw_prompt_dump"]),
        ("surfaces", ["status"]),
        ("permission_state", "none"),
        ("requires_operator_decision", False),
        ("error_code", None),
    ):
        object.__setattr__(forged, name, value)
    with pytest.raises(SpineError) as exc:
        forged.as_dict()
    assert exc.value.code == mod.RUNTIME_INVALID_VIEW_MODEL
    assert "raw_prompt" not in str(exc.value)


def test_serialize_task_view_model_revalidates_and_returns_byte_stable_json() -> None:
    mod = _view_model_mod()
    registry = _registry_with_permission_wait()
    view = mod.build_task_view_model(registry, "task_alpha")
    encoded = mod.serialize_task_view_model(view)
    assert type(encoded) is bytes
    assert encoded == mod.serialize_task_view_model(view)
    assert b"permission_prompt_ref_1" in encoded
    assert b"raw_prompt" not in encoded
    assert b"chat_id" not in encoded
    assert b"card_json" not in encoded


# --------------------------------------------------------------------------- #
# D. Boundary: no actual IM/Gateway/send/edit/delivery wiring
# --------------------------------------------------------------------------- #
def test_view_model_source_has_no_forbidden_runtime_or_delivery_surface() -> None:
    path = Path("sachima_supervisor/runtime_spine/view_model.py")
    if not path.exists():
        pytest.skip("view_model.py not implemented yet; RED import tests cover absence")
    text = path.read_text(encoding="utf-8")
    forbidden = (
        "subprocess",
        "socket",
        ".Popen(",
        "os.system",
        "acpx",
        " npx",
        "gateway",
        "feishu",
        "lark",
        "send(",
        "edit_message",
        "im_send",
        "delivery_payload",
        "import temporalio",
    )
    assert [token for token in forbidden if token in text] == []


def test_view_model_does_not_append_events_or_launch_work() -> None:
    mod = _view_model_mod()
    registry = _registry_with_permission_wait()
    before = registry.log.last_seq("task_alpha")
    mod.build_task_view_model(registry, "task_alpha")
    mod.build_task_view_model(registry, "task_alpha")
    assert registry.log.last_seq("task_alpha") == before
