"""Contract validation tests for FlowWeaver v0 golden snapshots.

These tests intentionally use only the Python standard library.  They validate the
small Phase 3 contract surface that later implementation phases can depend on
without requiring a JSON Schema dependency.
"""

from __future__ import annotations

import json
import re
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTO_ROOT = REPO_ROOT / "prototypes" / "flowweaver_phase3"
CONTRACT_PATH = PROTO_ROOT / "contracts" / "flowweaver.v0.schema.json"
SNAPSHOTS_DIR = PROTO_ROOT / "snapshots"

CONTRACT_VERSION = "flowweaver.v0"
HANDLE_TYPE = "flowweaver.handle.v0"
ENVELOPE_KEYS = [
    "type",
    "transaction_id",
    "workflow_id",
    "run_id",
    "correlation_id",
    "snapshot_id",
    "adapter",
    "created_at",
]
STATUS_VOCABULARY = {
    "pending",
    "running",
    "succeeded",
    "failed",
    "blocked",
    "cancelled",
    "skipped",
}
DELIVERY_SURFACES = {
    "progress_card",
    "rich_card",
    "final_text",
    "media",
    "file",
    "voice",
    "fallback_text",
}
TARGET_KINDS = {"artifact", "snapshot", "final_text", "transaction", "intent"}
COVERAGE_MODES = {
    "answered",
    "delivered_artifact",
    "failed",
    "skipped",
    "blocked_waiting_for_user",
}
REQUIRED_SNAPSHOTS = {
    "mixed_weather_time_disk.snapshot.json": [
        "weather_today",
        "current_time",
        "disk_status",
    ],
    "dependent_weather_compare.snapshot.json": [
        "weather_today",
        "weather_tomorrow",
        "weather_compare",
    ],
    "ai_flow_approval_wait.snapshot.json": [
        "ai_flow_inspect",
        "ai_flow_plan",
        "ai_flow_approval",
    ],
}
FORBIDDEN_KEY_FRAGMENTS = (
    "authorization",
    "api_key",
    "app_secret",
    "credential",
    "feishu_card_json",
    "full_tool_args",
    "lark_card_json",
    "password",
    "raw_args",
    "raw_command",
    "raw_output",
    "secret",
    "stderr",
    "stdout",
    "token",
)
FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{12,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]+", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    re.compile(r"Traceback \(most recent call last\):"),
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_utc(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


class FlowWeaverContractExamplesTest(unittest.TestCase):
    maxDiff = None

    def assert_no_sensitive_material(self, obj: Any, path: str = "$.") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                lower_key = key.lower()
                for fragment in FORBIDDEN_KEY_FRAGMENTS:
                    self.assertNotIn(fragment, lower_key, f"forbidden key fragment at {path}{key}")
                self.assert_no_sensitive_material(value, f"{path}{key}.")
        elif isinstance(obj, list):
            for index, value in enumerate(obj):
                self.assert_no_sensitive_material(value, f"{path}[{index}].")
        elif isinstance(obj, str):
            for pattern in FORBIDDEN_VALUE_PATTERNS:
                self.assertIsNone(pattern.search(obj), f"forbidden value pattern at {path}")

    def test_contract_schema_file_exists_and_declares_v0(self) -> None:
        self.assertTrue(CONTRACT_PATH.exists(), f"missing schema: {CONTRACT_PATH}")
        schema = load_json(CONTRACT_PATH)

        self.assertEqual(schema["$id"], "https://sachima.local/contracts/flowweaver.v0.schema.json")
        self.assertEqual(schema["x-flowweaver-version"], CONTRACT_VERSION)
        self.assertEqual(schema["type"], "object")
        for key in ENVELOPE_KEYS + ["contract_version", "transaction", "snapshot"]:
            self.assertIn(key, schema["required"])
        self.assertEqual(
            schema["properties"]["type"].get("const"),
            HANDLE_TYPE,
            "correlation envelope type must remain stable",
        )
        self.assertEqual(
            set(schema["$defs"]["intent_status"]["enum"]),
            STATUS_VOCABULARY,
        )
        self.assertEqual(
            set(schema["$defs"]["delivery_surface"]["enum"]),
            DELIVERY_SURFACES,
        )
        self.assertEqual(set(schema["$defs"]["target_kind"]["enum"]), TARGET_KINDS)

    def test_required_golden_examples_exist(self) -> None:
        self.assertTrue(SNAPSHOTS_DIR.exists(), f"missing snapshots directory: {SNAPSHOTS_DIR}")
        existing = {path.name for path in SNAPSHOTS_DIR.glob("*.json")}
        self.assertTrue(
            set(REQUIRED_SNAPSHOTS).issubset(existing),
            f"missing required golden snapshots: {set(REQUIRED_SNAPSHOTS) - existing}",
        )

    def test_golden_examples_validate_contract_invariants(self) -> None:
        snapshot_paths = sorted(SNAPSHOTS_DIR.glob("*.json"))
        self.assertTrue(snapshot_paths, f"no golden snapshots found in {SNAPSHOTS_DIR}")
        for path in snapshot_paths:
            with self.subTest(snapshot=path.name):
                doc = load_json(path)
                expected_intent_order = REQUIRED_SNAPSHOTS.get(path.name)
                if expected_intent_order is None:
                    expected_intent_order = [
                        item["intent_id"]
                        for item in sorted(
                            doc["transaction"]["intents"],
                            key=lambda item: item["order_index"],
                        )
                    ]
                self.assert_no_sensitive_material(doc)
                self.validate_envelope(doc)
                self.validate_transaction(doc, expected_intent_order)
                self.validate_snapshot(doc, expected_intent_order)

    def validate_envelope(self, doc: dict[str, Any]) -> None:
        self.assertEqual(list(doc)[: len(ENVELOPE_KEYS)], ENVELOPE_KEYS)
        self.assertEqual(doc["type"], HANDLE_TYPE)
        self.assertEqual(doc["contract_version"], CONTRACT_VERSION)
        self.assertRegex(doc["transaction_id"], r"^tx_[a-z0-9_]+$")
        self.assertIsNone(doc["workflow_id"])
        self.assertIsNone(doc["run_id"])
        self.assertRegex(doc["correlation_id"], r"^turn_[a-z0-9_]+$")
        self.assertRegex(doc["snapshot_id"], r"^snap_[a-z0-9_]+$")
        self.assertEqual(doc["adapter"], "mock")
        parse_utc(doc["created_at"])

    def validate_transaction(self, doc: dict[str, Any], expected_intent_order: list[str]) -> None:
        tx = doc["transaction"]
        self.assertEqual(tx["transaction_id"], doc["transaction_id"])
        self.assertIn(tx["status"], STATUS_VOCABULARY)
        self.assertLessEqual(len(tx.get("user_request_summary", "")), 240)

        intents = tx["intents"]
        self.assertEqual([intent["intent_id"] for intent in intents], expected_intent_order)
        self.assertEqual([intent["order_index"] for intent in intents], list(range(len(intents))))
        order_by_intent = {intent["intent_id"]: intent["order_index"] for intent in intents}
        self.assertEqual(len(order_by_intent), len(intents), "intent_id values must be unique")
        for intent in intents:
            self.assertTrue(intent["title"])
            self.assertIn(intent["status"], STATUS_VOCABULARY)
            self.assertIsInstance(intent.get("dependencies", []), list)
            for dependency in intent.get("dependencies", []):
                self.assertIn(dependency, order_by_intent)
                self.assertLess(
                    order_by_intent[dependency],
                    intent["order_index"],
                    "intent dependencies must point to earlier ordered intents",
                )

        operation_ids = self.validate_operations(tx, order_by_intent)
        artifacts_by_id = self.validate_artifacts(tx, order_by_intent)
        deliveries_by_key = self.validate_deliveries(
            doc, tx, order_by_intent, set(artifacts_by_id)
        )
        self.validate_coverage(tx, expected_intent_order, artifacts_by_id, deliveries_by_key)
        self.assertGreaterEqual(len(operation_ids), len(intents) - 1)

    def validate_operations(self, tx: dict[str, Any], order_by_intent: dict[str, int]) -> set[str]:
        operation_ids: set[str] = set()
        disallowed_delivery_keys = {"delivery_id", "delivery_idempotency_key", "message_id", "platform", "surface", "target"}
        for operation in tx["operations"]:
            for key in ["operation_id", "intent_id", "kind", "status", "attempted_at", "summary"]:
                self.assertIn(key, operation)
            self.assertTrue(disallowed_delivery_keys.isdisjoint(operation), operation)
            self.assertNotIn(operation["operation_id"], operation_ids)
            operation_ids.add(operation["operation_id"])
            self.assertIn(operation["intent_id"], order_by_intent)
            self.assertIn(operation["status"], STATUS_VOCABULARY)
            self.assertLessEqual(len(operation["summary"]), 280)
            parse_utc(operation["attempted_at"])
        return operation_ids

    def validate_artifacts(
        self, tx: dict[str, Any], order_by_intent: dict[str, int]
    ) -> dict[str, dict[str, Any]]:
        artifacts_by_id: dict[str, dict[str, Any]] = {}
        disallowed_delivery_keys = {"delivery_id", "delivery_idempotency_key", "message_id", "platform", "surface", "target"}
        for artifact in tx["artifacts"]:
            for key in ["artifact_id", "intent_id", "kind", "status", "title", "content_summary"]:
                self.assertIn(key, artifact)
            self.assertTrue(disallowed_delivery_keys.isdisjoint(artifact), artifact)
            self.assertNotIn(artifact["artifact_id"], artifacts_by_id)
            artifacts_by_id[artifact["artifact_id"]] = artifact
            self.assertIn(artifact["intent_id"], order_by_intent)
            self.assertIn(artifact["status"], STATUS_VOCABULARY)
            self.assertLessEqual(len(artifact["content_summary"]), 360)
            if artifact["kind"] == "fallback_text":
                self.assertTrue(artifact.get("fallback_text"))
                self.assertLessEqual(len(artifact["fallback_text"]), 800)
        return artifacts_by_id

    def validate_deliveries(
        self,
        doc: dict[str, Any],
        tx: dict[str, Any],
        order_by_intent: dict[str, int],
        artifact_ids: set[str],
    ) -> dict[str, dict[str, Any]]:
        final_text_id = tx.get("final_text", {}).get("final_text_id")
        deliveries_by_key: dict[str, dict[str, Any]] = {}
        required_ack_order = [
            "delivery_idempotency_key",
            "surface",
            "platform",
            "status",
            "message_id",
            "target",
            "reason",
        ]
        for delivery in tx["deliveries"]:
            self.assertEqual(list(delivery)[: len(required_ack_order)], required_ack_order)
            self.assertNotIn(delivery["delivery_idempotency_key"], deliveries_by_key)
            deliveries_by_key[delivery["delivery_idempotency_key"]] = delivery
            self.assertIn(delivery["surface"], DELIVERY_SURFACES)
            self.assertEqual(delivery["platform"], "feishu")
            self.assertEqual(delivery["status"], "sent", "v0 examples only record ACKs after send/edit success")
            self.assertRegex(delivery["message_id"], r"^om_[a-z0-9_]+$")
            self.assertIsNone(delivery["reason"])
            target = delivery["target"]
            self.assertIn(target["kind"], TARGET_KINDS)
            self.assertIsInstance(target["id"], str)
            if target["kind"] == "artifact":
                self.assertIn(target["id"], artifact_ids)
            elif target["kind"] == "snapshot":
                self.assertEqual(target["id"], doc["snapshot_id"])
            elif target["kind"] == "final_text":
                self.assertEqual(target["id"], final_text_id)
            elif target["kind"] == "transaction":
                self.assertEqual(target["id"], doc["transaction_id"])
            elif target["kind"] == "intent":
                self.assertIn(target["id"], order_by_intent)
        return deliveries_by_key

    def validate_coverage(
        self,
        tx: dict[str, Any],
        expected_intent_order: list[str],
        artifacts_by_id: dict[str, dict[str, Any]],
        deliveries_by_key: dict[str, dict[str, Any]],
    ) -> None:
        coverage = tx["intent_coverage"]
        self.assertEqual([item["intent_id"] for item in coverage], expected_intent_order)
        intent_status = {intent["intent_id"]: intent["status"] for intent in tx["intents"]}
        for item in coverage:
            self.assertIn(item["mode"], COVERAGE_MODES)
            mode = item["mode"]
            if mode == "delivered_artifact":
                artifact_id = item.get("artifact_id")
                delivery_key = item.get("delivery_idempotency_key")
                self.assertIn(artifact_id, artifacts_by_id)
                self.assertIn(
                    artifacts_by_id[artifact_id]["kind"],
                    {"rich_card", "media", "file", "voice"},
                    "delivered_artifact coverage must refer to a delivered rich/media/file/voice artifact",
                )
                self.assertIn(delivery_key, deliveries_by_key)
                self.assertIn(deliveries_by_key[delivery_key]["surface"], {"rich_card", "media", "file", "voice"})
                self.assertEqual(deliveries_by_key[delivery_key]["target"]["kind"], "artifact")
                self.assertEqual(deliveries_by_key[delivery_key]["target"]["id"], artifact_id)
                self.assertIsNone(item.get("reason"))
            elif mode == "answered":
                delivery_key = item.get("delivery_idempotency_key")
                self.assertIn(delivery_key, deliveries_by_key)
                self.assertIn(deliveries_by_key[delivery_key]["surface"], {"final_text", "fallback_text"})
                self.assertIsNone(item.get("reason"))
            elif mode == "failed":
                self.assertEqual(intent_status[item["intent_id"]], "failed")
                self.assertTrue(item.get("reason"))
            elif mode == "skipped":
                self.assertEqual(intent_status[item["intent_id"]], "skipped")
                self.assertTrue(item.get("reason"))
            elif mode == "blocked_waiting_for_user":
                self.assertEqual(intent_status[item["intent_id"]], "blocked")
                delivery_key = item.get("delivery_idempotency_key")
                if delivery_key is not None:
                    self.assertIn(delivery_key, deliveries_by_key)
                self.assertTrue(item.get("reason"))

    def validate_snapshot(self, doc: dict[str, Any], expected_intent_order: list[str]) -> None:
        snapshot = doc["snapshot"]
        self.assertEqual(snapshot["snapshot_id"], doc["snapshot_id"])
        self.assertEqual(snapshot["transaction_id"], doc["transaction_id"])
        self.assertIn(snapshot["status"], STATUS_VOCABULARY)
        self.assertTrue(snapshot["safe_to_render"])
        self.assertEqual(snapshot["ordered_intent_ids"], expected_intent_order)
        self.assertLessEqual(len(snapshot["progress"]), snapshot["bounds"]["max_progress_items"])
        self.assertLessEqual(len(snapshot["render_text"]), snapshot["bounds"]["max_render_text_chars"])
        self.assertEqual([item["intent_id"] for item in snapshot["progress"]], expected_intent_order)
        for item in snapshot["progress"]:
            self.assertIn(item["status"], STATUS_VOCABULARY)
            self.assertLessEqual(len(item["summary"]), 180)


if __name__ == "__main__":
    unittest.main()
