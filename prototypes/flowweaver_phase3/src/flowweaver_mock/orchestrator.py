from __future__ import annotations

import re
from typing import Any

from .models import (
    ALLOWED_ARTIFACT_KINDS,
    CONTRACT_VERSION,
    DELIVERY_SURFACES,
    HANDLE_TYPE,
    STATUS_BLOCKED,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    STATUS_SUCCEEDED,
    STATUS_VOCABULARY,
    TARGET_KINDS,
    TransactionRecord,
    sanitize_text,
    sanitize_value,
    slugify,
    utc_now,
)
from .store import InMemoryTransactionStore


class FlowWeaverMockOrchestrator:
    """Local-only FlowWeaver v0 mock orchestrator.

    It validates the Phase 3 transaction/artifact/delivery vocabulary without
    becoming a scheduler or a production Gateway dependency.
    """

    def __init__(self, store: InMemoryTransactionStore | None = None) -> None:
        self.store = store or InMemoryTransactionStore()
        self._counter = 0

    def create_transaction(self, *, source: dict[str, Any], title: str) -> str:
        self._counter += 1
        slug = slugify(title, default="transaction")
        tx_id = f"tx_{slug}_{self._counter}"
        record = TransactionRecord(
            transaction_id=tx_id,
            correlation_id=f"turn_{slug}_{self._counter}",
            snapshot_id=f"snap_{slug}_{self._counter}",
            title=sanitize_text(title, max_len=240),
            source=sanitize_value(source),
            created_at=utc_now(),
            final_text={
                "final_text_id": f"final_text_{slug}_{self._counter}",
                "status": STATUS_PENDING,
                "text": "",
                "covers_intent_ids": [],
            },
        )
        self.store.put(record)
        return tx_id

    def submit_intent_plan(self, transaction_id: str, intents: list[dict[str, Any]]) -> dict[str, Any]:
        if not intents:
            raise ValueError("intent plan must contain at least one intent")
        record = self.store.get(transaction_id)
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, raw_intent in enumerate(intents):
            intent_id = slugify(raw_intent.get("intent_id") or raw_intent.get("title") or f"intent_{index}")
            if intent_id in seen:
                raise ValueError(f"duplicate intent_id: {intent_id}")
            deps = [slugify(dep) for dep in raw_intent.get("dependencies", [])]
            missing_or_forward = [dep for dep in deps if dep not in seen]
            if missing_or_forward:
                raise ValueError("intent dependencies must point to earlier ordered intents")
            status = raw_intent.get("status", STATUS_PENDING)
            self._require_status(status)
            normalized.append(
                {
                    "intent_id": intent_id,
                    "order_index": index,
                    "title": sanitize_text(raw_intent.get("title", intent_id), max_len=120),
                    "status": status,
                    "dependencies": deps,
                }
            )
            seen.add(intent_id)
        record.intents = normalized
        record.status = self._derive_transaction_status(record)
        self.store.update(record)
        return self._snapshot(record)

    def record_artifact(self, transaction_id: str, intent_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
        record = self.store.get(transaction_id)
        intent = self._find_intent(record, intent_id)
        artifact_id = slugify(artifact.get("artifact_id") or f"artifact_{intent_id}", default="artifact")
        if not artifact_id.startswith("artifact_"):
            artifact_id = f"artifact_{artifact_id}"
        if any(existing["artifact_id"] == artifact_id for existing in record.artifacts):
            raise ValueError(f"duplicate artifact_id: {artifact_id}")
        status = artifact.get("status", STATUS_SUCCEEDED)
        self._require_status(status)
        kind = sanitize_text(artifact.get("kind", "text_result"), max_len=80)
        if kind not in ALLOWED_ARTIFACT_KINDS:
            raise ValueError(f"unsupported artifact kind: {kind}")
        clean_artifact = {
            "artifact_id": artifact_id,
            "intent_id": intent["intent_id"],
            "kind": kind,
            "status": status,
            "title": sanitize_text(artifact.get("title", artifact_id), max_len=120),
            "content_summary": sanitize_text(artifact.get("content_summary", "Generated artifact."), max_len=360),
            "covers_intent_ids": [slugify(value) for value in artifact.get("covers_intent_ids", [intent["intent_id"]])],
        }
        if "data" in artifact:
            clean_artifact["data"] = sanitize_value(artifact["data"], max_len=360)
        if "fallback_text" in artifact:
            clean_artifact["fallback_text"] = sanitize_text(artifact["fallback_text"], max_len=800)
        record.artifacts.append(clean_artifact)
        record.status = self._derive_transaction_status(record)
        self.store.update(record)
        return self._snapshot(record)

    def ack_delivery(self, transaction_id: str, delivery_record: dict[str, Any]) -> dict[str, Any]:
        record = self.store.get(transaction_id)
        clean = self._normalize_delivery(record, delivery_record)
        existing_by_key = {item["delivery_idempotency_key"]: item for item in record.deliveries}
        existing = existing_by_key.get(clean["delivery_idempotency_key"])
        if existing is not None:
            if not delivery_record.get("sent_at"):
                clean["sent_at"] = existing["sent_at"]
            if existing != clean:
                raise ValueError("duplicate delivery idempotency key has conflicting ACK payload")
        else:
            record.deliveries.append(clean)
            self._mark_delivery_target_succeeded(record, clean)
        record.status = self._derive_transaction_status(record)
        self.store.update(record)
        return self._snapshot(record)

    def record_final_text(self, transaction_id: str, text: str, *, covers_intent_ids: list[str], status: str = STATUS_PENDING) -> dict[str, Any]:
        self._require_status(status)
        record = self.store.get(transaction_id)
        covers = [slugify(intent_id) for intent_id in covers_intent_ids]
        for intent_id in covers:
            self._find_intent(record, intent_id)
        record.final_text = {
            "final_text_id": record.final_text.get("final_text_id") or f"final_text_{record.transaction_id.removeprefix('tx_')}",
            "status": status,
            "text": sanitize_text(text, max_len=1200),
            "covers_intent_ids": covers,
        }
        record.status = self._derive_transaction_status(record)
        self.store.update(record)
        return self._snapshot(record)

    def query_snapshot(self, transaction_id: str) -> dict[str, Any]:
        return self._snapshot(self.store.get(transaction_id))

    def _mark_delivery_target_succeeded(self, record: TransactionRecord, delivery: dict[str, Any]) -> None:
        target = delivery["target"]
        if target["kind"] == "artifact":
            artifact = self._artifact_by_id(record, target["id"])
            if not artifact or artifact.get("status") != STATUS_SUCCEEDED:
                raise ValueError("delivery ACK artifact target must have succeeded status")
            for covered_intent_id in artifact.get("covers_intent_ids", [artifact["intent_id"]]):
                intent = self._find_intent(record, covered_intent_id)
                if intent["status"] in {STATUS_PENDING, STATUS_RUNNING}:
                    intent["status"] = STATUS_SUCCEEDED
        elif target["kind"] == "final_text":
            if record.final_text.get("status") == STATUS_BLOCKED:
                return
            if record.final_text.get("status") not in {STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCEEDED}:
                raise ValueError("delivery ACK final_text target must be pending, running, succeeded, or blocked")
            record.final_text["status"] = STATUS_SUCCEEDED
            for covered_intent_id in record.final_text.get("covers_intent_ids", []):
                intent = self._find_intent(record, covered_intent_id)
                if intent["status"] in {STATUS_PENDING, STATUS_RUNNING}:
                    intent["status"] = STATUS_SUCCEEDED

    def cancel_transaction(self, transaction_id: str, reason: str) -> dict[str, Any]:
        record = self.store.get(transaction_id)
        record.status = STATUS_CANCELLED
        record.cancellation_reason = sanitize_text(reason, max_len=240)
        for intent in record.intents:
            if intent["status"] not in {STATUS_SUCCEEDED, STATUS_FAILED, STATUS_SKIPPED}:
                intent["status"] = STATUS_CANCELLED
        record.final_text["status"] = STATUS_CANCELLED
        record.final_text["text"] = f"Cancelled: {record.cancellation_reason}"
        self.store.update(record)
        return self._snapshot(record)

    def _artifact_by_id(self, record: TransactionRecord, artifact_id: str) -> dict[str, Any] | None:
        return next((item for item in record.artifacts if item["artifact_id"] == artifact_id), None)

    def _artifact_aliases(self, artifact: dict[str, Any]) -> set[str]:
        artifact_id = artifact["artifact_id"]
        aliases = {artifact_id}
        if artifact_id.startswith("artifact_"):
            aliases.add(artifact_id.removeprefix("artifact_"))
        aliases.add(artifact.get("intent_id", ""))
        aliases.update(artifact.get("covers_intent_ids", []))
        return {slugify(alias) for alias in aliases if alias}

    def _target_hint_matches(self, record: TransactionRecord, kind: str, target_id: str, hint: str) -> bool:
        hint = slugify(hint)
        if kind == "artifact":
            artifact = self._artifact_by_id(record, target_id)
            if not artifact or hint not in self._artifact_aliases(artifact):
                return False
            matching_artifact_ids = {
                item["artifact_id"]
                for item in record.artifacts
                if hint in self._artifact_aliases(item)
            }
            return matching_artifact_ids == {target_id}
        if kind == "final_text":
            aliases = {target_id, *record.final_text.get("covers_intent_ids", [])}
            return hint in {slugify(alias) for alias in aliases if alias}
        if kind == "snapshot":
            aliases = {record.snapshot_id, record.transaction_id, record.correlation_id}
            return hint in {slugify(alias) for alias in aliases if alias}
        if kind == "transaction":
            return hint == slugify(record.transaction_id)
        if kind == "intent":
            return hint == slugify(target_id)
        return False

    def _require_surface_target_compatibility(self, record: TransactionRecord, surface: str, kind: str, target_id: str) -> None:
        artifact = self._artifact_by_id(record, target_id) if kind == "artifact" else None
        if artifact is not None and artifact.get("status") != STATUS_SUCCEEDED:
            raise ValueError("delivery ACK artifact target must have succeeded status")
        if surface == "final_text" and kind != "final_text":
            raise ValueError("final_text delivery must target final_text")
        if surface == "progress_card" and kind != "snapshot":
            raise ValueError("progress_card delivery must target snapshot")
        if surface == "rich_card" and (kind != "artifact" or not artifact or artifact.get("kind") != "rich_card"):
            raise ValueError("rich_card delivery must target a rich_card artifact")
        if surface == "fallback_text" and (kind != "artifact" or not artifact or artifact.get("kind") != "fallback_text"):
            raise ValueError("fallback_text delivery must target a fallback_text artifact")
        if surface in {"media", "file", "voice"} and (kind != "artifact" or not artifact or artifact.get("kind") != surface):
            raise ValueError(f"{surface} delivery must target a matching artifact")

    def _normalize_delivery(self, record: TransactionRecord, delivery: dict[str, Any]) -> dict[str, Any]:
        if delivery.get("status") != "sent":
            raise ValueError("delivery ACK requires status='sent' after platform send/edit success")
        surface = delivery.get("surface")
        if surface not in DELIVERY_SURFACES:
            raise ValueError(f"unknown delivery surface: {surface}")
        platform = sanitize_text(delivery.get("platform", ""), max_len=40)
        if platform != "feishu":
            raise ValueError("delivery platform must be feishu in the v0 mock contract")
        key = sanitize_text(delivery.get("delivery_idempotency_key", ""), max_len=160)
        if not re.fullmatch(r"feishu:om_[a-z0-9_]+:[a-z_]+:[a-z0-9_]+", key):
            raise ValueError("delivery idempotency key must follow feishu:om_*:<surface>:<target>")
        message_id = sanitize_text(delivery.get("message_id", ""), max_len=120)
        if not re.fullmatch(r"om_[a-z0-9_]+", message_id):
            raise ValueError("delivery message_id must be a sanitized Feishu mock id")
        if delivery.get("reason") is not None:
            raise ValueError("sent delivery ACK reason must be null")
        target = delivery.get("target") or {}
        kind = target.get("kind")
        target_id = target.get("id")
        if kind not in TARGET_KINDS or not target_id:
            raise ValueError("delivery target must include supported kind and id")
        if kind == "artifact" and not any(item["artifact_id"] == target_id for item in record.artifacts):
            raise ValueError(f"delivery target artifact does not exist: {target_id}")
        if kind == "snapshot" and target_id != record.snapshot_id:
            raise ValueError(f"delivery target snapshot does not match: {target_id}")
        if kind == "final_text" and target_id != record.final_text.get("final_text_id"):
            raise ValueError(f"delivery target final_text does not match: {target_id}")
        if kind == "transaction" and target_id != record.transaction_id:
            raise ValueError(f"delivery target transaction does not match: {target_id}")
        if kind == "intent":
            self._find_intent(record, target_id)
        key_match = re.fullmatch(r"feishu:(om_[a-z0-9_]+):([a-z_]+):([a-z0-9_]+)", key)
        assert key_match is not None
        key_message_id, key_surface, key_target_hint = key_match.groups()
        if key_message_id != message_id or key_surface != surface:
            raise ValueError("delivery idempotency key components must match message_id and surface")
        if not self._target_hint_matches(record, kind, target_id, key_target_hint):
            raise ValueError("delivery idempotency key target hint must match delivery target")
        self._require_surface_target_compatibility(record, surface, kind, target_id)
        return {
            "delivery_idempotency_key": key,
            "surface": surface,
            "platform": platform,
            "status": "sent",
            "message_id": message_id,
            "target": {"kind": kind, "id": sanitize_text(target_id, max_len=160)},
            "reason": None,
            "sent_at": sanitize_text(delivery.get("sent_at") or utc_now(), max_len=40),
        }

    def _snapshot(self, record: TransactionRecord) -> dict[str, Any]:
        tx = {
            "transaction_id": record.transaction_id,
            "status": record.status,
            "user_request_summary": record.title,
            "intents": record.intents,
            "operations": record.operations,
            "artifacts": record.artifacts,
            "deliveries": record.deliveries,
            "intent_coverage": self._intent_coverage(record),
            "final_text": record.final_text,
        }
        progress = [
            {
                "intent_id": intent["intent_id"],
                "status": intent["status"],
                "summary": self._progress_summary(record, intent),
            }
            for intent in record.intents[:10]
        ]
        render_text = self._render_text(record, progress)
        return sanitize_value(
            {
                "type": HANDLE_TYPE,
                "transaction_id": record.transaction_id,
                "workflow_id": None,
                "run_id": None,
                "correlation_id": record.correlation_id,
                "snapshot_id": record.snapshot_id,
                "adapter": "mock",
                "created_at": record.created_at,
                "contract_version": CONTRACT_VERSION,
                "transaction": tx,
                "snapshot": {
                    "snapshot_id": record.snapshot_id,
                    "transaction_id": record.transaction_id,
                    "status": record.status,
                    "safe_to_render": True,
                    "ordered_intent_ids": [intent["intent_id"] for intent in record.intents],
                    "progress": progress,
                    "render_text": render_text,
                    "bounds": {"max_progress_items": 10, "max_render_text_chars": 1200},
                },
            }
        )

    def _intent_coverage(self, record: TransactionRecord) -> list[dict[str, Any]]:
        deliveries_by_artifact = {
            delivery["target"]["id"]: delivery
            for delivery in record.deliveries
            if delivery["target"]["kind"] == "artifact"
        }
        final_text_delivery = next(
            (
                delivery
                for delivery in record.deliveries
                if delivery["target"]["kind"] == "final_text"
                and delivery["target"]["id"] == record.final_text.get("final_text_id")
                and delivery["surface"] == "final_text"
            ),
            None,
        )
        final_text_covers = set(record.final_text.get("covers_intent_ids", []))
        coverage: list[dict[str, Any]] = []
        for intent in record.intents:
            intent_id = intent["intent_id"]
            artifacts = [item for item in record.artifacts if intent_id in item.get("covers_intent_ids", [item["intent_id"]])]
            delivered_pair = next(
                (
                    (item, deliveries_by_artifact[item["artifact_id"]])
                    for item in reversed(artifacts)
                    if item["artifact_id"] in deliveries_by_artifact
                    and deliveries_by_artifact[item["artifact_id"]]["surface"] in {"rich_card", "media", "file", "voice", "fallback_text"}
                ),
                None,
            )
            artifact = delivered_pair[0] if delivered_pair else (artifacts[0] if artifacts else None)
            delivered = delivered_pair[1] if delivered_pair else None
            delivered_blocked_prompt = final_text_delivery if intent_id in final_text_covers else None
            if intent["status"] == STATUS_CANCELLED:
                coverage.append({"intent_id": intent_id, "mode": "skipped", "artifact_id": None, "delivery_idempotency_key": None, "reason": record.cancellation_reason or "Cancelled."})
            elif intent["status"] == STATUS_BLOCKED:
                coverage.append({
                    "intent_id": intent_id,
                    "mode": "blocked_waiting_for_user",
                    "artifact_id": None,
                    "delivery_idempotency_key": delivered_blocked_prompt["delivery_idempotency_key"] if delivered_blocked_prompt else None,
                    "reason": "Waiting for user input or approval.",
                })
            elif intent["status"] == STATUS_FAILED:
                coverage.append({"intent_id": intent_id, "mode": "failed", "artifact_id": None, "delivery_idempotency_key": None, "reason": "Intent failed."})
            elif intent["status"] == STATUS_SKIPPED:
                coverage.append({"intent_id": intent_id, "mode": "skipped", "artifact_id": None, "delivery_idempotency_key": None, "reason": "Intent skipped."})
            elif final_text_delivery and record.final_text.get("status") == STATUS_SUCCEEDED and intent_id in final_text_covers:
                coverage.append({"intent_id": intent_id, "mode": "answered", "artifact_id": None, "delivery_idempotency_key": final_text_delivery["delivery_idempotency_key"], "reason": None})
            elif artifact and delivered and delivered["surface"] in {"rich_card", "media", "file", "voice"}:
                coverage.append({"intent_id": intent_id, "mode": "delivered_artifact", "artifact_id": artifact["artifact_id"], "delivery_idempotency_key": delivered["delivery_idempotency_key"], "reason": None})
            elif artifact and delivered and delivered["surface"] == "fallback_text":
                coverage.append({"intent_id": intent_id, "mode": "answered", "artifact_id": None, "delivery_idempotency_key": delivered["delivery_idempotency_key"], "reason": None})
            elif artifact:
                coverage.append({"intent_id": intent_id, "mode": "blocked_waiting_for_user", "artifact_id": artifact["artifact_id"], "delivery_idempotency_key": None, "reason": "Artifact generated but not delivered or covered by final text."})
            else:
                coverage.append({"intent_id": intent_id, "mode": "blocked_waiting_for_user", "artifact_id": None, "delivery_idempotency_key": None, "reason": "Work is not complete yet."})
        return coverage

    def _derive_transaction_status(self, record: TransactionRecord) -> str:
        if record.status == STATUS_CANCELLED:
            return STATUS_CANCELLED
        statuses = [intent["status"] for intent in record.intents]
        if not statuses:
            return STATUS_PENDING
        if any(status == STATUS_BLOCKED for status in statuses):
            return STATUS_BLOCKED
        if any(status == STATUS_FAILED for status in statuses):
            return STATUS_FAILED
        if all(status == STATUS_SUCCEEDED for status in statuses):
            return STATUS_SUCCEEDED
        if any(status == STATUS_RUNNING for status in statuses):
            return STATUS_RUNNING
        return STATUS_PENDING

    def _find_intent(self, record: TransactionRecord, intent_id: str) -> dict[str, Any]:
        wanted = slugify(intent_id)
        for intent in record.intents:
            if intent["intent_id"] == wanted:
                return intent
        raise ValueError(f"unknown intent_id: {intent_id}")

    def _require_status(self, status: str) -> None:
        if status not in STATUS_VOCABULARY:
            raise ValueError(f"unsupported status: {status}")

    def _progress_summary(self, record: TransactionRecord, intent: dict[str, Any]) -> str:
        if intent["status"] == STATUS_CANCELLED:
            return sanitize_text(record.cancellation_reason or "Cancelled.", max_len=180)
        if intent["status"] == STATUS_BLOCKED:
            return "Waiting for user input or approval."
        if intent["status"] == STATUS_SUCCEEDED:
            return f"{intent['title']} completed."
        return f"{intent['title']} is {intent['status']}."

    def _render_text(self, record: TransactionRecord, progress: list[dict[str, Any]]) -> str:
        completed = sum(1 for intent in record.intents if intent["status"] == STATUS_SUCCEEDED)
        total = len(record.intents)
        if total == 0:
            return f"Transaction created: {record.title}"
        if record.status == STATUS_CANCELLED:
            return sanitize_text(f"Transaction cancelled: {record.cancellation_reason}", max_len=1200)
        return sanitize_text(f"{completed} of {total} intents complete. Status: {record.status}.", max_len=1200)
