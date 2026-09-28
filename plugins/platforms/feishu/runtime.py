"""Profile-scoped runtime access to a connected Feishu adapter."""

from __future__ import annotations

import threading
import weakref
from typing import Any, Optional

from hermes_constants import hermes_home_key


_ACTIVE_ADAPTERS: "weakref.WeakValueDictionary[str, Any]" = weakref.WeakValueDictionary()
_ACTIVE_ADAPTERS_LOCK = threading.RLock()


def set_active_adapter(adapter: Any) -> str:
    """Register *adapter* for the current profile and return its scope key."""
    scope_key = hermes_home_key()
    with _ACTIVE_ADAPTERS_LOCK:
        _ACTIVE_ADAPTERS[scope_key] = adapter
    return scope_key


def clear_active_adapter(adapter: Any, scope_key: str = "") -> None:
    """Remove *adapter* without disturbing a newer connection in that scope."""
    key = scope_key or hermes_home_key()
    with _ACTIVE_ADAPTERS_LOCK:
        if _ACTIVE_ADAPTERS.get(key) is adapter:
            _ACTIVE_ADAPTERS.pop(key, None)


def get_active_adapter() -> Optional[Any]:
    """Return the connected adapter for the current profile, if one exists."""
    with _ACTIVE_ADAPTERS_LOCK:
        return _ACTIVE_ADAPTERS.get(hermes_home_key())
