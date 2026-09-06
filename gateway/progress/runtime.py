"""Runtime bridge from agent progress callbacks to the Task Workbench.

The tracker, renderer, and event-store modules stay pure.  This narrow bridge
owns the one mutable message/card for a logical gateway transaction, coalesces
worker-thread callbacks, and performs a visible final flush before teardown.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import logging
import queue
import threading
import time
from typing import Any, Callable

from gateway.progress.renderers import (
    detect_feishu_progress_card_language,
    render_feishu_progress_card,
    render_text_panel,
)
from gateway.progress.store import build_progress_event_store
from gateway.progress.tracker import ProgressTracker

logger = logging.getLogger(__name__)

_RENDER_SIGNAL = ("__task_workbench_render__",)
_FINAL_SIGNAL = ("__task_workbench_final__",)
_FEISHU_CARD_FALLBACK_NOTICE = "⚠️ 任务卡片更新失败，后台进度仍已记录。"


class TaskWorkbenchRuntime:
    """One progress projection shared by every frame of a logical turn."""

    def __init__(
        self,
        *,
        transaction_id: str,
        progress_queue: queue.Queue,
        config: Mapping[str, Any],
        platform: Any,
        message: Any,
        history: list[Any] | None,
    ) -> None:
        self.transaction_id = transaction_id
        self.progress_queue = progress_queue
        self.config = dict(config)
        self.platform = _platform_name(platform)
        requested_mode = str(self.config.get("mode", "text") or "text").strip().lower()
        self.mode = (
            "feishu_card"
            if requested_mode == "feishu_card" and self.platform == "feishu"
            else "text"
        )
        # Keep platform edits below the same rate used by the established
        # gateway progress loop. The terminal flush bypasses this delay so a
        # completed state is still visible before teardown.
        self.edit_interval = 2.0 if self.mode == "feishu_card" else 1.5
        self.max_operations = _safe_positive_int(
            self.config.get("max_operations"), default=12
        )
        self.max_length = _safe_positive_int(
            self.config.get("max_length"), default=3500
        )
        self.dashboard_url = self.config.get("dashboard_url")
        self.style = str(self.config.get("style", "lively") or "lively")
        self.emoji = _truthy(self.config.get("emoji"), default=True)
        self.language = detect_feishu_progress_card_language(
            message,
            self.config.get("language", "auto"),
            context_messages=history or (),
        )
        self.tool_progress_mode = str(
            self.config.get("tool_progress_mode", "all") or "all"
        )
        self.tracker = ProgressTracker(
            transaction_id=transaction_id,
            max_operations=self.max_operations,
        )
        self.event_store = build_progress_event_store(dict(self.config))
        self.reasoning_effort_display: Any = None
        self.service_tier_display: Any = None
        self._render_pending = False
        self._render_lock = threading.Lock()
        self._final_flushed = asyncio.Event()
        self._finalized = False

    @classmethod
    def get_or_create(
        cls,
        transaction: dict[str, Any],
        config: Mapping[str, Any],
        *,
        platform: Any,
        message: Any,
        history: list[Any] | None,
    ) -> "TaskWorkbenchRuntime":
        """Return the runtime already shared by a queued-follow-up chain."""

        existing = transaction.get("task_workbench")
        if isinstance(existing, cls):
            return existing
        progress_queue = transaction.get("queue")
        if progress_queue is None:
            progress_queue = queue.Queue()
            transaction["queue"] = progress_queue
        transaction_id = str(transaction.get("transaction_id") or "").strip()
        if not transaction_id:
            raise ValueError("Task Workbench transaction_id is required")
        runtime = cls(
            transaction_id=transaction_id,
            progress_queue=progress_queue,
            config=config,
            platform=platform,
            message=message,
            history=history,
        )
        transaction["task_workbench"] = runtime
        return runtime

    def set_model_config_display(
        self,
        reasoning_effort: Any,
        service_tier: Any,
    ) -> None:
        self.reasoning_effort_display = reasoning_effort
        self.service_tier_display = service_tier

    def refresh_from_agent(
        self,
        agent: Any,
        *,
        current_rounds: Any = None,
    ) -> None:
        """Copy only structured, sanitized runtime state into the tracker."""

        if agent is None:
            return
        try:
            self.tracker.update_display_metadata(
                model_display=getattr(agent, "model", None),
                reasoning_effort_display=self.reasoning_effort_display,
                service_tier_display=self.service_tier_display,
            )
        except Exception:
            logger.debug("Task Workbench model metadata refresh failed", exc_info=True)

        compressor = getattr(agent, "context_compressor", None)
        if compressor is not None:
            current = _safe_nonnegative_int(
                getattr(compressor, "last_prompt_tokens", 0)
            )
            peak = _safe_nonnegative_int(
                getattr(compressor, "peak_prompt_tokens", current)
            )
            compressions = _safe_nonnegative_int(
                getattr(compressor, "compression_count", 0)
            )
            if any((current, peak, compressions)):
                self.tracker.update_context_usage(
                    current_tokens=current,
                    context_window=getattr(compressor, "context_length", 0),
                    peak_tokens=max(current, peak),
                    compression_count=compressions,
                    threshold_tokens=getattr(compressor, "threshold_tokens", 0),
                )

        max_rounds = _safe_nonnegative_int(getattr(agent, "max_iterations", 0))
        if max_rounds:
            self.tracker.update_iteration_usage(
                current_rounds=(
                    current_rounds
                    if current_rounds is not None
                    else getattr(agent, "_api_call_count", 0)
                ),
                max_rounds=max_rounds,
            )

        try:
            copy_agent_todo_progress(self.tracker, agent)
        except Exception:
            logger.debug("Task Workbench TODO refresh failed", exc_info=True)

    def record_callback_event(
        self,
        agent: Any,
        event_type: str,
        tool_name: str | None = None,
        preview: Any = None,
        args: Any = None,
        **kwargs: Any,
    ) -> None:
        """Record one supported callback and request a coalesced projection."""

        if self._finalized:
            return
        self.refresh_from_agent(agent)
        recorded = self.tracker.record_callback_event(
            event_type,
            tool_name=tool_name,
            preview=preview,
            args=args,
            **kwargs,
        )
        if recorded is None:
            return
        if self.event_store is not None:
            try:
                self.event_store.append_operation(self.tracker.snapshot(), recorded)
            except Exception:
                logger.debug("Task Workbench event persistence failed", exc_info=True)
        self._queue_render()

    async def finalize(
        self,
        agent: Any,
        *,
        result: Any = None,
        is_error: bool = False,
        visible: bool = True,
        timeout: float = 3.0,
    ) -> None:
        """Persist and visibly flush the terminal snapshot exactly once."""

        if self._finalized:
            return
        self._finalized = True
        current_rounds = result.get("api_calls") if isinstance(result, dict) else None
        self._mark_todo_lifecycle(agent, is_error=is_error)
        self.refresh_from_agent(agent, current_rounds=current_rounds)
        self.tracker.mark_completed(is_error=is_error)
        if self.event_store is not None:
            try:
                self.event_store.append_snapshot(self.tracker.snapshot())
            except Exception:
                logger.debug("Task Workbench final persistence failed", exc_info=True)
        if not visible:
            return
        self.progress_queue.put(_FINAL_SIGNAL)
        try:
            await asyncio.wait_for(self._final_flushed.wait(), timeout=max(0.1, timeout))
        except asyncio.TimeoutError:
            logger.warning(
                "Timed out waiting for final Task Workbench flush: %s",
                self.transaction_id,
            )

    async def send_progress_messages(
        self,
        *,
        adapter: Any,
        chat_id: str,
        reply_to: Any,
        metadata: dict[str, Any] | None,
        cleanup_message_ids: list[str],
        is_current: Callable[[], bool],
    ) -> None:
        """Maintain one editable text panel or one Feishu card."""

        message_id: str | None = None
        card_suppressed = False
        fallback_notice_sent = False
        last_edit_at = 0.0

        async def track_send(result: Any) -> None:
            if (
                getattr(result, "success", False)
                and getattr(result, "message_id", None)
                and str(result.message_id) not in cleanup_message_ids
            ):
                cleanup_message_ids.append(str(result.message_id))

        async def compact_card_failure_notice() -> None:
            nonlocal fallback_notice_sent
            if fallback_notice_sent:
                return
            fallback_notice_sent = True
            try:
                result = await adapter.send(
                    chat_id=chat_id,
                    content=_FEISHU_CARD_FALLBACK_NOTICE,
                    reply_to=reply_to,
                    metadata=metadata,
                )
                await track_send(result)
            except Exception:
                logger.debug("Task Workbench card fallback failed", exc_info=True)

        while True:
            try:
                signal = self.progress_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.02)
                continue

            is_final = signal == _FINAL_SIGNAL
            if signal != _RENDER_SIGNAL and not is_final:
                # The shared queue can also receive stream-consumer reset
                # markers. They do not create additional Workbench surfaces.
                continue
            if signal == _RENDER_SIGNAL:
                with self._render_lock:
                    self._render_pending = False

            if not is_current():
                if is_final:
                    self._final_flushed.set()
                continue

            if not is_final:
                remaining = self.edit_interval - (time.monotonic() - last_edit_at)
                if remaining > 0:
                    await asyncio.sleep(remaining)

            if self.mode == "feishu_card":
                if card_suppressed:
                    if is_final:
                        self._final_flushed.set()
                    continue
                card = render_feishu_progress_card(
                    self.tracker.snapshot(),
                    tool_progress_mode=self.tool_progress_mode,
                    max_operations=self.max_operations,
                    dashboard_url=self.dashboard_url,
                    style=self.style,
                    emoji=self.emoji,
                    language=self.language,
                )
                try:
                    if message_id is None:
                        result = await adapter.send_interactive_card(
                            chat_id,
                            card,
                            reply_to=reply_to,
                            metadata=metadata,
                        )
                    else:
                        result = await adapter.patch_interactive_card(
                            chat_id,
                            message_id,
                            card,
                            finalize=is_final,
                        )
                except Exception as exc:
                    logger.warning("Task Workbench card update raised: %s", exc)
                    result = None

                if getattr(result, "success", False):
                    if message_id is None and getattr(result, "message_id", None):
                        message_id = str(result.message_id)
                        await track_send(result)
                elif not getattr(result, "retryable", False) or is_final:
                    card_suppressed = True
                    await compact_card_failure_notice()
            else:
                panel = render_text_panel(
                    self.tracker.snapshot(),
                    tool_progress_mode=self.tool_progress_mode,
                    max_length=self.max_length,
                    dashboard_url=self.dashboard_url,
                )
                try:
                    if message_id is None:
                        result = await adapter.send(
                            chat_id=chat_id,
                            content=panel,
                            reply_to=reply_to,
                            metadata=metadata,
                        )
                    else:
                        result = await adapter.edit_message(
                            chat_id=chat_id,
                            message_id=message_id,
                            content=panel,
                            **(
                                {"finalize": True}
                                if is_final
                                and getattr(adapter, "REQUIRES_EDIT_FINALIZE", False)
                                else {}
                            ),
                        )
                except Exception as exc:
                    logger.warning("Task Workbench text update raised: %s", exc)
                    result = None

                if getattr(result, "success", False):
                    if message_id is None and getattr(result, "message_id", None):
                        message_id = str(result.message_id)
                        await track_send(result)
                elif is_final and message_id is not None:
                    # A failed terminal edit must not leave a Running panel as
                    # the last visible state. Send one completed replacement.
                    try:
                        fallback = await adapter.send(
                            chat_id=chat_id,
                            content=panel,
                            reply_to=reply_to,
                            metadata=metadata,
                        )
                        await track_send(fallback)
                    except Exception:
                        logger.debug(
                            "Task Workbench final text fallback failed",
                            exc_info=True,
                        )

            last_edit_at = time.monotonic()
            if is_final:
                self._final_flushed.set()

    def _queue_render(self) -> None:
        with self._render_lock:
            if self._render_pending:
                return
            self._render_pending = True
        self.progress_queue.put(_RENDER_SIGNAL)

    @staticmethod
    def _mark_todo_lifecycle(agent: Any, *, is_error: bool) -> None:
        store = getattr(agent, "_todo_store", None) if agent is not None else None
        if store is None:
            return
        read = getattr(store, "read", None)
        mark = getattr(store, "mark_lifecycle", None)
        if not callable(read) or not callable(mark):
            return
        try:
            items = read()
            remaining = sum(
                1
                for item in items
                if isinstance(item, dict)
                and item.get("status") in {"pending", "in_progress"}
            )
            cancelled = sum(
                1
                for item in items
                if isinstance(item, dict) and item.get("status") == "cancelled"
            )
            if remaining:
                mark(
                    "suspended",
                    reason="failed_recoverable" if is_error else "paused",
                )
            elif items and cancelled == len(items):
                mark("cancelled")
            elif items:
                mark("completed")
        except Exception:
            logger.debug("Task Workbench TODO lifecycle finalization failed", exc_info=True)


def copy_agent_todo_progress(progress_tracker: Any, agent: Any) -> None:
    """Project a TodoStore snapshot into a tracker without text inference."""

    if progress_tracker is None or agent is None:
        return
    store = getattr(agent, "_todo_store", None)
    if store is None:
        return
    read_snapshot = getattr(store, "read_snapshot", None)
    if callable(read_snapshot):
        snapshot = read_snapshot() or {}
    else:
        read = getattr(store, "read", None)
        if not callable(read):
            return
        snapshot = {"todos": read()}
        read_lifecycle = getattr(store, "read_lifecycle", None)
        if callable(read_lifecycle):
            snapshot["todo_lifecycle"] = read_lifecycle()

    lifecycle = snapshot.get("todo_lifecycle")
    state = (
        str(lifecycle.get("state") or "").strip().lower()
        if isinstance(lifecycle, dict)
        else ""
    )
    transaction_id = (
        str(lifecycle.get("transaction_id") or "").strip()
        if isinstance(lifecycle, dict)
        else ""
    )
    current_transaction_id = str(
        getattr(agent, "_todo_transaction_id", None)
        or getattr(agent, "_current_task_id", None)
        or getattr(progress_tracker, "transaction_id", "")
        or ""
    ).strip()
    archive_prior_terminal = (
        state in {"completed", "cancelled"}
        and bool(transaction_id)
        and transaction_id != current_transaction_id
    )
    if state == "archived" or archive_prior_terminal:
        items: list[Any] = []
        if isinstance(lifecycle, dict) and state != "archived":
            lifecycle = {**lifecycle, "state": "archived"}
    else:
        raw_items = snapshot.get("todos", [])
        items = []
        for raw in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(raw, dict):
                items.append(raw)
                continue
            item = dict(raw)
            if "parent_id" not in item and item.get("parent"):
                item["parent_id"] = item["parent"]
            items.append(item)
    progress_tracker.update_todo_items(items)
    if hasattr(progress_tracker, "update_todo_lifecycle"):
        progress_tracker.update_todo_lifecycle(lifecycle)
    hint = snapshot.get("suspended_todo_hint")
    if hint is not None and hasattr(progress_tracker, "update_suspended_todo_hint"):
        progress_tracker.update_suspended_todo_hint(hint)


def _platform_name(platform: Any) -> str:
    return str(getattr(platform, "value", platform) or "").strip().lower()


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _safe_positive_int(value: Any, *, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _safe_nonnegative_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
