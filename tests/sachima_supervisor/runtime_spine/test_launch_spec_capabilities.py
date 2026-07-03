"""R1 — static Capability Registry + typed LaunchSpec (design §4, §11; plan §5.5/5.6).

RED/GREEN tests for the static, non-plugin capability table keyed by
``agent_kind`` and the frozen, fail-closed ``LaunchSpec`` validated against it.
No dynamic imports, no env/config discovery, no live/write-capable material.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from sachima_supervisor.runtime_spine import (
    CAPABILITY_FIELDS,
    KNOWN_MODE_FLAGS,
    RUNTIME_INVALID_LAUNCH_SPEC,
    RUNTIME_UNKNOWN_CAPABILITY,
    STABLE_CODES,
    Capability,
    LaunchSpec,
    SpineError,
    build_launch_spec,
    get_capability,
    known_agent_kinds,
    validate_launch_spec,
)


# --------------------------------------------------------------------------- #
# E. Static Capability Registry
# --------------------------------------------------------------------------- #
def test_capability_fields_are_the_five_design_fields() -> None:
    assert set(CAPABILITY_FIELDS) == {
        "attach_resume",
        "permission_events",
        "workspace_isolation",
        "liveness",
        "stream_resume",
    }


def test_get_capability_returns_frozen_boolean_capability() -> None:
    cap = get_capability("local_agent")
    assert type(cap) is Capability
    assert dataclasses.is_dataclass(cap)
    for field in CAPABILITY_FIELDS:
        assert type(getattr(cap, field)) is bool
    with pytest.raises(dataclasses.FrozenInstanceError):
        cap.liveness = False  # type: ignore[misc]


def test_known_agent_kinds_are_static_and_include_core_kinds() -> None:
    kinds = known_agent_kinds()
    assert "inline_tool" in kinds
    assert "local_agent" in kinds
    # inline tools are the (false,false) lane — no live/attach/permission surface.
    inline = get_capability("inline_tool")
    assert inline.liveness is False
    assert inline.attach_resume is False
    assert inline.permission_events is False


@pytest.mark.parametrize(
    "unknown_kind",
    [
        "does_not_exist",
        "feishu_agent",       # platform-derived
        "chat_id_agent",      # platform id
        "write_agent",        # write-capable / write-ish
        "live_default_agent", # live-ish / default-on
        "Local_Agent",        # bad charset
        "",                   # empty
    ],
)
def test_get_capability_rejects_unknown_or_unsafe_kind(unknown_kind: str) -> None:
    with pytest.raises(SpineError) as exc:
        get_capability(unknown_kind)
    assert exc.value.code == RUNTIME_UNKNOWN_CAPABILITY


# --------------------------------------------------------------------------- #
# F. Typed LaunchSpec
# --------------------------------------------------------------------------- #
def _clean_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        task_id="task_alpha",
        agent_kind="local_agent",
        mode_flags={"needs_agent": True, "needs_durable": False},
        required_capabilities=("liveness", "stream_resume"),
        roles=("sachima_read_only_reviewer",),
        refs=("launch_ref_0",),
    )
    base.update(overrides)
    return base


def test_build_launch_spec_accepts_clean_and_is_frozen() -> None:
    spec = build_launch_spec(**_clean_kwargs())
    assert type(spec) is LaunchSpec
    assert spec.task_id == "task_alpha"
    assert spec.agent_kind == "local_agent"
    assert spec.needs_agent is True
    assert spec.needs_durable is False
    assert spec.required_capabilities == ("liveness", "stream_resume")
    assert spec.roles == ("sachima_read_only_reviewer",)
    assert spec.refs == ("launch_ref_0",)
    validate_launch_spec(spec)  # idempotent, no raise
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.agent_kind = "inline_tool"  # type: ignore[misc]


def test_known_mode_flags_pinned() -> None:
    assert set(KNOWN_MODE_FLAGS) == {"needs_agent", "needs_durable"}


def test_launch_spec_rejects_unknown_mode_flag() -> None:
    with pytest.raises(SpineError) as exc:
        build_launch_spec(**_clean_kwargs(mode_flags={"needs_agent": True, "needs_write": True}))
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


def test_launch_spec_rejects_non_bool_mode_flag() -> None:
    with pytest.raises(SpineError):
        build_launch_spec(**_clean_kwargs(mode_flags={"needs_agent": "true"}))


def test_launch_spec_rejects_unknown_agent_kind() -> None:
    with pytest.raises(SpineError) as exc:
        build_launch_spec(**_clean_kwargs(agent_kind="mystery_agent"))
    assert exc.value.code == RUNTIME_UNKNOWN_CAPABILITY


def test_launch_spec_rejects_unsupported_capability() -> None:
    # inline_tool supports none of the live/attach capabilities.
    with pytest.raises(SpineError) as exc:
        build_launch_spec(
            **_clean_kwargs(
                agent_kind="inline_tool",
                mode_flags={"needs_agent": False, "needs_durable": False},
                required_capabilities=("liveness",),
            )
        )
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


def test_launch_spec_rejects_unknown_capability_name() -> None:
    with pytest.raises(SpineError) as exc:
        build_launch_spec(**_clean_kwargs(required_capabilities=("teleport",)))
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


def test_launch_spec_flags_must_match_capability() -> None:
    # needs_agent requires a live-capable kind; inline_tool cannot host a live agent.
    with pytest.raises(SpineError) as exc:
        build_launch_spec(
            **_clean_kwargs(
                agent_kind="inline_tool",
                mode_flags={"needs_agent": True, "needs_durable": False},
                required_capabilities=(),
            )
        )
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


@pytest.mark.parametrize(
    "platform_value",
    [
        {"task_id": "chat_id_998877"},
        {"task_id": "oc_channel_1"},
        {"refs": ("ou_open_id_1",)},
        {"refs": ("card_json_ref",)},
        {"agent_kind": "feishu_agent"},
    ],
)
def test_launch_spec_rejects_platform_derived_values(platform_value: dict) -> None:
    with pytest.raises(SpineError) as exc:
        build_launch_spec(**_clean_kwargs(**platform_value))
    assert exc.value.code in STABLE_CODES


@pytest.mark.parametrize("write_role", ["writer_role", "deliver_role", "approve_role", "mutate_role"])
def test_launch_spec_rejects_write_capable_role_markers(write_role: str) -> None:
    with pytest.raises(SpineError) as exc:
        build_launch_spec(**_clean_kwargs(roles=(write_role,)))
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


def test_launch_spec_failures_carry_stable_code_only() -> None:
    with pytest.raises(SpineError) as exc:
        build_launch_spec(**_clean_kwargs(refs=("bearer secrettoken",)))
    assert exc.value.code in STABLE_CODES
    assert str(exc.value) == exc.value.code
    assert "secrettoken" not in str(exc.value)


def test_validate_launch_spec_rejects_hostile_subclass() -> None:
    class Evil(LaunchSpec):
        pass

    spec = build_launch_spec(**_clean_kwargs())
    evil = Evil(**dataclasses.asdict(spec))
    with pytest.raises(SpineError):
        validate_launch_spec(evil)


# --------------------------------------------------------------------------- #
# G. Direct LaunchSpec(...) construction is itself fail-closed
#
# Codex blocker: ``LaunchSpec`` is the exported typed launch surface, but the raw
# dataclass constructor was NOT validated — only ``build_launch_spec`` /
# ``validate_launch_spec`` were. A caller instantiating ``LaunchSpec(...)`` with
# non-bool mode flags, unsupported/unknown capability names, write-ish roles,
# platform-derived refs/task_id/agent_kind, or raw material got a "typed" object
# that skipped every check unless the consumer remembered to call
# ``validate_launch_spec``. Like ``TaskEvent``, the public constructor must
# enforce the invariant via ``__post_init__``.
# --------------------------------------------------------------------------- #
def _clean_direct(**overrides: Any) -> dict[str, Any]:
    """Kwargs for the raw ``LaunchSpec(...)`` constructor (mode flags are two
    separate bools here, not a ``mode_flags`` mapping)."""

    base: dict[str, Any] = dict(
        task_id="task_alpha",
        agent_kind="local_agent",
        needs_agent=True,
        needs_durable=False,
        required_capabilities=("liveness", "stream_resume"),
        roles=("sachima_read_only_reviewer",),
        refs=("launch_ref_0",),
    )
    base.update(overrides)
    return base


def test_direct_launch_spec_accepts_clean_and_is_frozen() -> None:
    spec = LaunchSpec(**_clean_direct())
    assert type(spec) is LaunchSpec
    assert spec.task_id == "task_alpha"
    assert spec.needs_agent is True
    assert spec.needs_durable is False
    assert spec.required_capabilities == ("liveness", "stream_resume")
    assert spec.roles == ("sachima_read_only_reviewer",)
    assert spec.refs == ("launch_ref_0",)
    validate_launch_spec(spec)  # idempotent, no raise
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.needs_agent = False  # type: ignore[misc]


def test_direct_launch_spec_rejects_unknown_capability_name() -> None:
    with pytest.raises(SpineError) as exc:
        LaunchSpec(**_clean_direct(required_capabilities=("teleport",)))
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


def test_direct_launch_spec_rejects_unsupported_capability() -> None:
    # inline_tool supports none of the live/attach capabilities.
    with pytest.raises(SpineError) as exc:
        LaunchSpec(
            **_clean_direct(
                agent_kind="inline_tool",
                needs_agent=False,
                needs_durable=False,
                required_capabilities=("liveness",),
            )
        )
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


@pytest.mark.parametrize(
    "bad_flag",
    [
        {"needs_agent": "true"},
        {"needs_agent": 1},
        {"needs_durable": 0},
        {"needs_durable": "false"},
        {"needs_agent": None},
    ],
)
def test_direct_launch_spec_rejects_non_bool_mode_flags(bad_flag: dict) -> None:
    with pytest.raises(SpineError) as exc:
        LaunchSpec(**_clean_direct(**bad_flag))
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


def test_direct_launch_spec_flags_must_match_capability() -> None:
    # needs_agent=True requires a live-capable kind; inline_tool cannot host one.
    with pytest.raises(SpineError) as exc:
        LaunchSpec(
            **_clean_direct(
                agent_kind="inline_tool",
                needs_agent=True,
                needs_durable=False,
                required_capabilities=(),
            )
        )
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


@pytest.mark.parametrize(
    "write_role", ["writer_role", "deliver_role", "approve_role", "reject_role", "mutate_role"]
)
def test_direct_launch_spec_rejects_write_capable_role_markers(write_role: str) -> None:
    with pytest.raises(SpineError) as exc:
        LaunchSpec(**_clean_direct(roles=(write_role,)))
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC


@pytest.mark.parametrize(
    "platform_value",
    [
        {"task_id": "chat_id_998877"},
        {"task_id": "oc_channel_1"},
        {"refs": ("ou_open_id_1",)},
        {"refs": ("card_json_ref",)},
        {"agent_kind": "feishu_agent"},
    ],
)
def test_direct_launch_spec_rejects_platform_derived_values(platform_value: dict) -> None:
    with pytest.raises(SpineError) as exc:
        LaunchSpec(**_clean_direct(**platform_value))
    assert exc.value.code in STABLE_CODES


def test_direct_launch_spec_failures_carry_stable_code_only() -> None:
    with pytest.raises(SpineError) as exc:
        LaunchSpec(**_clean_direct(refs=("bearer secrettoken",)))
    assert exc.value.code in STABLE_CODES
    assert str(exc.value) == exc.value.code
    assert "secrettoken" not in str(exc.value)


def test_direct_launch_spec_allows_clean_subclass_but_validate_rejects_it() -> None:
    # __post_init__ validates FIELDS (not concrete type), so a clean subclass can
    # still be built — but the identity gate in validate_launch_spec rejects it.
    class Evil(LaunchSpec):
        pass

    evil = Evil(**_clean_direct())  # clean fields → construction succeeds
    with pytest.raises(SpineError) as exc:
        validate_launch_spec(evil)
    assert exc.value.code == RUNTIME_INVALID_LAUNCH_SPEC
