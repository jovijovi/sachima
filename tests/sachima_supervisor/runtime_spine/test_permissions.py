"""R4 — Permission roundtrip + read-only/default-deny role policy (design §8, plan §8).

RED/GREEN tests for the future ``permissions`` module. A permission *request*
emits a refs-only ``permission_requested`` / ``permission_wait`` event through the
R1 Task Registry / Event Log (never raw prompt/context/tool output/platform
IDs/private paths). A permission *answer* returns only through the Hermes-controlled
``signal(task_id, decision/ref)`` model: the helper talks to the supervisor solely
across an ``ExecutionPort``-like signal boundary — never create/kill/stream. Role
policy is **default-deny**: read-only is the maximum capability, and unknown /
write-capable / mutation / delivery / approval roles fail closed.

The module under test is pure local/offline Python: it opens no socket, launches no
process, and wires no Gateway/Feishu, delivery, or IM send/edit surface. Forbidden
terms appear only as no-leak canaries, never behavior.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path
from typing import Any

import pytest

from sachima_supervisor.runtime_spine import (
    SpineError,
    TaskRegistry,
    event_projection,
    scan_for_leak,
)
from sachima_supervisor.runtime_spine.execution_port import (
    ExecutionPort,
    LivenessState,
    SessionRef,
    SessionStatus,
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
    "sk" + "-",
    "bearer ",
    "feishu",
)

# Roles that must fail closed under a read-only, default-deny policy.
_WRITE_CAPABLE_ROLES = (
    "writer",
    "write",
    "deliver",
    "delivery",
    "approve",
    "approver",
    "reject",
    "mutate",
    "mutator",
)
_UNKNOWN_ROLES = ("auditor", "admin", "superuser", "root", "operator", "owner")


def _permissions_mod():
    return importlib.import_module("sachima_supervisor.runtime_spine.permissions")


def _running_status(task_id: str = "task_alpha", session_id: str = "sess_1") -> SessionStatus:
    return SessionStatus(
        task_id=task_id,
        session_id=session_id,
        state="running",
        alive=True,
        terminal=False,
        last_seq=1,
        projected_status="running",
    )


class _SignalOnlyPort(ExecutionPort):
    """Spy port: only ``signal`` is a legal call. Everything else is an error.

    Models the R4 rule that the permission helper reaches the supervisor solely
    through the Hermes-controlled ``signal(task_id, decision/ref)`` boundary.
    """

    def __init__(self) -> None:
        self.signal_calls: list[tuple[str, str]] = []
        self.create_or_attach_calls = 0
        self.kill_calls = 0
        self.stream_calls = 0
        self.status_calls = 0
        self.liveness_calls = 0

    def create_or_attach(self, task_id: str, launch_spec: Any) -> SessionRef:
        self.create_or_attach_calls += 1
        raise AssertionError("permission answer must not create_or_attach")

    def stream(self, ref: str | SessionRef):
        self.stream_calls += 1
        raise AssertionError("permission answer must not stream")

    def signal(self, task_id: str, decision_ref: str) -> SessionStatus:
        self.signal_calls.append((task_id, decision_ref))
        return _running_status(task_id)

    def status(self, ref: str | SessionRef) -> SessionStatus:
        self.status_calls += 1
        raise AssertionError("permission answer must not query status")

    def kill(self, ref: str | SessionRef, reason_ref: str = "ref_cancelled") -> SessionStatus:
        self.kill_calls += 1
        raise AssertionError("permission answer must not kill")

    def liveness(self, ref: str | SessionRef) -> LivenessState:
        self.liveness_calls += 1
        raise AssertionError("permission answer must not probe liveness")


def _new_registry(task_id: str = "task_alpha") -> TaskRegistry:
    registry = TaskRegistry()
    registry.create_task(task_id, needs_agent=True)
    return registry


def _event_types(registry: TaskRegistry, task_id: str) -> list[str]:
    return [e.event_type for e in registry.log.events_for(task_id)]


# --------------------------------------------------------------------------- #
# A. Public surface and stable error family
# --------------------------------------------------------------------------- #
def test_permissions_public_surface_is_exported() -> None:
    mod = _permissions_mod()
    assert mod.RUNTIME_INVALID_PERMISSION == "runtime_invalid_permission"
    assert mod.RUNTIME_PERMISSION_ROLE_DENIED == "runtime_permission_role_denied"
    assert mod.RUNTIME_INVALID_PERMISSION in mod.PERMISSION_STABLE_CODES
    assert mod.RUNTIME_PERMISSION_ROLE_DENIED in mod.PERMISSION_STABLE_CODES
    for name in (
        "PermissionPolicy",
        "PermissionRequest",
        "PermissionDecision",
        "request_permission",
        "apply_permission_decision",
        "validate_role_policy",
        "validate_permission_request",
        "validate_permission_decision",
        "ALLOWED_PERMISSION_ROLES",
    ):
        assert hasattr(mod, name)


def test_permission_symbols_available_from_runtime_spine_package() -> None:
    runtime_spine = importlib.import_module("sachima_supervisor.runtime_spine")
    for name in (
        "RUNTIME_INVALID_PERMISSION",
        "RUNTIME_PERMISSION_ROLE_DENIED",
        "PermissionPolicy",
        "PermissionRequest",
        "PermissionDecision",
        "request_permission",
        "apply_permission_decision",
        "validate_role_policy",
    ):
        assert hasattr(runtime_spine, name)


# --------------------------------------------------------------------------- #
# B. request_permission — refs-only permission_requested / permission_wait event
# --------------------------------------------------------------------------- #
def test_request_permission_emits_refs_only_permission_wait_event() -> None:
    mod = _permissions_mod()
    registry = _new_registry()
    request = mod.request_permission(
        registry,
        task_id="task_alpha",
        prompt_ref="permission_prompt_ref_1",
        role="read_only",
        refs=("evidence_ref_context_1",),
    )
    assert type(request) is mod.PermissionRequest
    assert request.task_id == "task_alpha"
    assert request.prompt_ref == "permission_prompt_ref_1"
    assert request.role == "read_only"

    events = registry.log.events_for("task_alpha")
    assert [e.event_type for e in events] == ["task_created", "permission_requested"]
    emitted = events[-1]
    assert emitted.event_type == "permission_requested"
    assert emitted.status == "permission_wait"
    assert "permission_prompt_ref_1" in emitted.refs
    assert "evidence_ref_context_1" in emitted.refs
    # The projection/snapshot now reads permission_wait — an alive, expected state.
    snapshot = registry.snapshot("task_alpha")
    assert snapshot is not None
    assert snapshot["status"] == "permission_wait"
    assert scan_for_leak([e.__dict__ for e in events]) is None
    assert scan_for_leak(dataclasses.asdict(request)) is None


@pytest.mark.parametrize("canary", _LEAK_CANARIES)
def test_request_permission_rejects_raw_or_platform_prompt_ref(canary: str) -> None:
    mod = _permissions_mod()
    registry = _new_registry()
    with pytest.raises(SpineError) as exc:
        mod.request_permission(
            registry,
            task_id="task_alpha",
            prompt_ref=f"permission_prompt_{canary}_x",
            role="read_only",
        )
    assert exc.value.code == mod.RUNTIME_INVALID_PERMISSION
    assert str(exc.value) == mod.RUNTIME_INVALID_PERMISSION
    # Fail closed: no permission event leaked into the canonical log.
    assert "permission_requested" not in _event_types(registry, "task_alpha")


def test_request_permission_requires_an_existing_task() -> None:
    mod = _permissions_mod()
    registry = TaskRegistry()  # task never created
    with pytest.raises(SpineError) as exc:
        mod.request_permission(
            registry,
            task_id="task_missing",
            prompt_ref="permission_prompt_ref_1",
            role="read_only",
        )
    assert exc.value.code == mod.RUNTIME_INVALID_PERMISSION


def test_request_permission_takes_registry_only_never_a_supervisor_port() -> None:
    # The request path is a producer over the R1 registry boundary — it never holds
    # or drives an execution port. A port passed where the registry belongs fails
    # closed rather than being driven.
    mod = _permissions_mod()
    port = _SignalOnlyPort()
    with pytest.raises(SpineError) as exc:
        mod.request_permission(
            port,
            task_id="task_alpha",
            prompt_ref="permission_prompt_ref_1",
            role="read_only",
        )
    assert exc.value.code == mod.RUNTIME_INVALID_PERMISSION
    assert port.signal_calls == []


# --------------------------------------------------------------------------- #
# C. Answer returns via Hermes-controlled signal(task_id, decision/ref)
# --------------------------------------------------------------------------- #
def test_apply_permission_decision_returns_through_signal_only() -> None:
    mod = _permissions_mod()
    port = _SignalOnlyPort()
    decision = mod.PermissionDecision(
        task_id="task_alpha",
        decision="allow",
        decision_ref="decision_ref_allow_1",
    )
    status = mod.apply_permission_decision(port, decision)
    # The answer travelled the roundtrip solely as signal(task_id, decision/ref).
    assert port.signal_calls == [("task_alpha", "decision_ref_allow_1")]
    assert port.create_or_attach_calls == 0
    assert port.kill_calls == 0
    assert port.stream_calls == 0
    assert port.status_calls == 0
    assert port.liveness_calls == 0
    assert type(status) is SessionStatus
    assert status.task_id == "task_alpha"


def test_apply_permission_decision_allow_and_deny_both_route_via_signal() -> None:
    mod = _permissions_mod()
    for verdict, ref in (("allow", "decision_ref_allow_1"), ("deny", "decision_ref_deny_1")):
        port = _SignalOnlyPort()
        decision = mod.PermissionDecision(
            task_id="task_alpha", decision=verdict, decision_ref=ref
        )
        mod.apply_permission_decision(port, decision)
        assert port.signal_calls == [("task_alpha", ref)]


def test_apply_permission_decision_rejects_unknown_verdict() -> None:
    mod = _permissions_mod()
    port = _SignalOnlyPort()
    with pytest.raises(SpineError) as exc:
        mod.PermissionDecision(
            task_id="task_alpha",
            decision="exfiltrate",  # outside the closed allow/deny vocabulary
            decision_ref="decision_ref_1",
        )
    assert exc.value.code == mod.RUNTIME_INVALID_PERMISSION
    assert port.signal_calls == []


class _EqualitySpoof:
    def __init__(self, target: str) -> None:
        self.target = target

    def __hash__(self) -> int:
        return hash(self.target)

    def __eq__(self, other: object) -> bool:
        return other == self.target

    def __repr__(self) -> str:
        return "raw_prompt_spoof"


def test_permission_decision_rejects_equality_spoof_verdict_before_signal() -> None:
    mod = _permissions_mod()
    port = _SignalOnlyPort()
    with pytest.raises(SpineError) as exc:
        mod.PermissionDecision(
            task_id="task_alpha",
            decision=_EqualitySpoof("allow"),
            decision_ref="decision_ref_allow_1",
        )
    assert exc.value.code == mod.RUNTIME_INVALID_PERMISSION
    assert "raw_prompt" not in str(exc.value)
    assert port.signal_calls == []


def test_permission_policy_rejects_equality_spoof_read_only_role() -> None:
    mod = _permissions_mod()
    with pytest.raises(SpineError) as exc:
        mod.PermissionPolicy(allowed_roles=frozenset({_EqualitySpoof("read_only")}))
    assert exc.value.code in mod.PERMISSION_STABLE_CODES
    assert "raw_prompt" not in str(exc.value)


def test_apply_permission_decision_rejects_leaky_decision_ref() -> None:
    mod = _permissions_mod()
    for leaky in ("raw_prompt_dump", "chat_id", "oc_secret", "decision ref"):
        port = _SignalOnlyPort()
        with pytest.raises(SpineError) as exc:
            mod.PermissionDecision(
                task_id="task_alpha", decision="allow", decision_ref=leaky
            )
        assert exc.value.code == mod.RUNTIME_INVALID_PERMISSION
        assert "raw_prompt" not in str(exc.value)
        assert port.signal_calls == []


def test_apply_permission_decision_rejects_non_execution_port() -> None:
    mod = _permissions_mod()
    decision = mod.PermissionDecision(
        task_id="task_alpha", decision="allow", decision_ref="decision_ref_1"
    )
    for bad in (None, object(), {}, "signal"):
        with pytest.raises(SpineError) as exc:
            mod.apply_permission_decision(bad, decision)
        assert exc.value.code == mod.RUNTIME_INVALID_PERMISSION


# --------------------------------------------------------------------------- #
# D. Role policy — default-deny; read-only is the maximum capability
# --------------------------------------------------------------------------- #
def test_validate_role_policy_accepts_read_only() -> None:
    mod = _permissions_mod()
    assert mod.validate_role_policy("read_only") == "read_only"
    assert "read_only" in mod.ALLOWED_PERMISSION_ROLES


def test_read_only_is_the_maximum_allowed_role_capability() -> None:
    mod = _permissions_mod()
    # The allowlist is closed and read-only: no write/deliver/approve/mutate member.
    assert mod.ALLOWED_PERMISSION_ROLES
    forbidden_markers = ("write", "deliver", "approve", "reject", "mutate", "admin")
    for role in mod.ALLOWED_PERMISSION_ROLES:
        assert all(marker not in role for marker in forbidden_markers)


@pytest.mark.parametrize("role", _UNKNOWN_ROLES)
def test_validate_role_policy_denies_unknown_roles(role: str) -> None:
    mod = _permissions_mod()
    with pytest.raises(SpineError) as exc:
        mod.validate_role_policy(role)
    assert exc.value.code == mod.RUNTIME_PERMISSION_ROLE_DENIED


@pytest.mark.parametrize("role", _WRITE_CAPABLE_ROLES)
def test_validate_role_policy_denies_write_capable_roles(role: str) -> None:
    mod = _permissions_mod()
    with pytest.raises(SpineError) as exc:
        mod.validate_role_policy(role)
    assert exc.value.code == mod.RUNTIME_PERMISSION_ROLE_DENIED


@pytest.mark.parametrize("role", _WRITE_CAPABLE_ROLES + _UNKNOWN_ROLES)
def test_request_permission_denies_non_read_only_roles(role: str) -> None:
    mod = _permissions_mod()
    registry = _new_registry()
    with pytest.raises(SpineError) as exc:
        mod.request_permission(
            registry,
            task_id="task_alpha",
            prompt_ref="permission_prompt_ref_1",
            role=role,
        )
    assert exc.value.code == mod.RUNTIME_PERMISSION_ROLE_DENIED
    # Default-deny fails closed before any event is appended.
    assert "permission_requested" not in _event_types(registry, "task_alpha")


def test_permission_policy_default_is_read_only_default_deny() -> None:
    mod = _permissions_mod()
    policy = mod.PermissionPolicy()
    assert policy.validate_role("read_only") == "read_only"
    with pytest.raises(SpineError) as exc:
        policy.validate_role("writer")
    assert exc.value.code == mod.RUNTIME_PERMISSION_ROLE_DENIED


# --------------------------------------------------------------------------- #
# E. Trust boundary — hostile / forged / directly-built values fail closed
# --------------------------------------------------------------------------- #
def test_permission_request_direct_construction_rejects_unsafe_fields() -> None:
    mod = _permissions_mod()
    with pytest.raises(SpineError) as exc:
        mod.PermissionRequest(
            task_id="task_alpha",
            prompt_ref="raw_prompt_here",  # raw material, not a ref
            role="read_only",
            refs=(),
        )
    assert exc.value.code == mod.RUNTIME_INVALID_PERMISSION
    assert "raw_prompt" not in str(exc.value)


def test_permission_request_direct_construction_rejects_write_role() -> None:
    mod = _permissions_mod()
    with pytest.raises(SpineError) as exc:
        mod.PermissionRequest(
            task_id="task_alpha",
            prompt_ref="permission_prompt_ref_1",
            role="writer",
            refs=(),
        )
    assert exc.value.code in mod.PERMISSION_STABLE_CODES


def test_validate_forged_permission_request_fails_closed() -> None:
    mod = _permissions_mod()
    forged = object.__new__(mod.PermissionRequest)  # bypasses __post_init__
    for name, value in (
        ("task_id", "task_alpha"),
        ("prompt_ref", "ref_tool_output"),  # leaky ref
        ("role", "read_only"),
        ("refs", ()),
    ):
        object.__setattr__(forged, name, value)
    assert type(forged) is mod.PermissionRequest
    with pytest.raises(SpineError) as exc:
        mod.validate_permission_request(forged)
    assert exc.value.code == mod.RUNTIME_INVALID_PERMISSION
    assert "tool_output" not in str(exc.value)


def test_permission_decision_rejects_hostile_subclass_via_apply() -> None:
    mod = _permissions_mod()

    class _Hostile(mod.PermissionDecision):
        def __post_init__(self) -> None:  # skip fail-closed validation
            return None

    hostile = _Hostile(
        task_id="task_alpha",
        decision="allow",
        decision_ref="oc_open_chat_1",  # platform id smuggled past construction
    )
    port = _SignalOnlyPort()
    with pytest.raises(SpineError) as exc:
        mod.apply_permission_decision(port, hostile)
    assert exc.value.code == mod.RUNTIME_INVALID_PERMISSION
    assert port.signal_calls == []


# --------------------------------------------------------------------------- #
# F. R1/R2/R3 untouched — request uses the registry boundary; no leak
# --------------------------------------------------------------------------- #
def test_request_permission_event_is_refs_only_and_leak_free() -> None:
    mod = _permissions_mod()
    registry = _new_registry()
    mod.request_permission(
        registry,
        task_id="task_alpha",
        prompt_ref="permission_prompt_ref_1",
        role="read_only",
    )
    for event in registry.log.events_for("task_alpha"):
        assert scan_for_leak(event_projection(event)) is None


def test_apply_permission_decision_does_not_append_events_itself() -> None:
    # Answering is not a producer: the helper only calls signal; it appends no event
    # of its own to an independent registry.
    mod = _permissions_mod()
    registry = _new_registry()
    seq_before = registry.log.last_seq("task_alpha")
    port = _SignalOnlyPort()
    decision = mod.PermissionDecision(
        task_id="task_alpha", decision="allow", decision_ref="decision_ref_allow_1"
    )
    mod.apply_permission_decision(port, decision)
    assert registry.log.last_seq("task_alpha") == seq_before


# --------------------------------------------------------------------------- #
# G. Structural guard — no Gateway / delivery / IM send / process / network wiring
# --------------------------------------------------------------------------- #
def test_permissions_source_has_no_forbidden_delivery_surface() -> None:
    path = Path("sachima_supervisor/runtime_spine/permissions.py")
    if not path.exists():
        pytest.skip("permissions.py not implemented yet; RED import tests cover absence")
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
        "import temporalio",
    )
    assert [token for token in forbidden if token in text] == []
    import_lines = [
        ln for ln in text.splitlines() if ln.strip().startswith(("import ", "from "))
    ]
    denied_roots = (
        "subprocess",
        "socket",
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
