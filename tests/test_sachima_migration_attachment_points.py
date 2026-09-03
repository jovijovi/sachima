"""Pins the upstream entry points the remaining Sachima migration attaches to.

The migration adapts Sachima capability onto the upstream tree by symbol; it
never restores a downstream copy of an upstream file over it. That only works
while the symbols it attaches to keep their names and shapes. This guard names
them once, so an upstream rename shows up here — as one explicit failure with
the new baseline in hand — instead of as a surprise inside a later batch.

Three attachment points, one per later batch that needs one:

* ``tools.todo_tool.TodoStore``          — the TODO data source (task workbench)
* ``gateway.session``                    — the conversation Session trio
* the platform plugin registration path  — how a channel is registered

Nothing here asserts Sachima behaviour, and nothing here activates anything.
It is a shape guard over upstream symbols only.
"""

import inspect

import pytest


# ===========================================================================
# TODO — the data source, never overwritten by a downstream copy
# ===========================================================================

class TestTodoAttachmentPoint:

    def test_todo_store_exposes_the_read_write_and_snapshot_surface(self):
        from tools.todo_tool import TodoStore

        for method in ("write", "read", "has_items", "snapshot", "restore",
                       "format_for_injection"):
            assert callable(getattr(TodoStore, method, None)), (
                f"TodoStore.{method} is the upstream surface the task workbench "
                "reads; it must not be replaced by a downstream TodoStore"
            )

    def test_snapshot_and_restore_round_trip_carries_the_revision(self):
        """The workbench reconciles from a snapshot, so revision must survive."""
        from tools.todo_tool import TodoStore

        source = TodoStore()
        source.write([{"id": "a", "content": "first", "status": "pending"}])
        snapshot = source.snapshot()

        assert set(snapshot) == {"todos", "revision"}

        restored = TodoStore()
        restored.restore(snapshot["todos"], revision=snapshot["revision"])

        assert restored.snapshot() == snapshot

    def test_todo_tool_takes_an_injected_store(self):
        """A caller-supplied store is what keeps one task's TODOs its own."""
        from tools.todo_tool import todo_tool

        assert "store" in inspect.signature(todo_tool).parameters


# ===========================================================================
# Session — the conversation identity, distinct from every runtime identity
# ===========================================================================

class TestSessionAttachmentPoint:

    @pytest.mark.parametrize("symbol", [
        "SessionStore",
        "SessionEntry",
        "SessionSource",
        "SessionContext",
        "build_session_key",
    ])
    def test_session_symbol_is_present(self, symbol):
        import gateway.session as session

        assert hasattr(session, symbol), (
            f"gateway.session.{symbol} is an upstream attachment point for the "
            "migration; a rename here needs an explicit re-point, not a guess"
        )

    def test_build_session_key_is_the_keying_entry_point(self):
        from gateway.session import build_session_key

        assert callable(build_session_key)


# ===========================================================================
# Platform plugin registration — how a channel gets registered
# ===========================================================================

class TestPlatformRegistrationAttachmentPoint:

    def test_registry_singleton_and_entry_type_are_present(self):
        from gateway.platform_registry import (
            PlatformEntry,
            PlatformRegistry,
            platform_registry,
        )

        assert isinstance(platform_registry, PlatformRegistry)
        for method in ("register", "unregister", "get", "is_registered",
                       "create_adapter", "registered_names"):
            assert callable(getattr(PlatformRegistry, method, None))
        assert {"name", "label", "adapter_factory", "check_fn"} <= set(
            PlatformEntry.__dataclass_fields__
        )

    def test_plugin_context_registers_platforms_through_register_platform(self):
        """A bundled platform plugin registers via ``ctx.register_platform``."""
        from hermes_cli.plugins import PluginContext

        assert callable(getattr(PluginContext, "register_platform", None))
        params = inspect.signature(PluginContext.register_platform).parameters
        for required in ("name", "label", "adapter_factory", "check_fn"):
            assert required in params

    def test_a_bundled_platform_plugin_exposes_the_register_entry_point(self):
        """The shape a new platform package must copy: ``__init__`` re-exports
        ``register``, and ``register(ctx)`` is what the plugin host calls."""
        import plugins.platforms.feishu as feishu_plugin

        assert callable(getattr(feishu_plugin, "register", None))
        assert list(inspect.signature(feishu_plugin.register).parameters) == ["ctx"]
