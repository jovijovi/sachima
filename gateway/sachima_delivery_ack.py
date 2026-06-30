"""Sachima P7 default-off real delivery / ACK closure controller.

This module is the narrow, default-off control layer described by the P7 design
gate (`docs/plans/2026-06-29-sachima-p7-real-delivery-ack-closure-design-gate-*`).
It does not perform real delivery, own Gateway/runtime/Worker lifecycle, read or
write production config, construct platform adapters, open network listeners, or
create credentials. It validates an operator-approved delivery policy, consumes
caller-initialized delivery slots, calls exactly one caller-supplied adapter send
seam per idempotency key when enabled, and records ACKs only from concrete
accepted send responses (or separately approved receipts).

All returned shapes are sanitized projections built from safe runtime refs and
stable status/error codes. Raw platform payloads, card JSON, media bytes/paths,
callback payloads, chat/user/message ids, credentials, signed URLs, raw
exceptions, tracebacks, and private filesystem paths must never appear in any
returned projection, ACK event, or export.
"""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Any, Callable

SACHIMA_P7_DELIVERY_ACK_VERSION = "sachima.p7.delivery_ack_controller.v0"
SACHIMA_P7_DELIVERY_POLICY_TYPE = "sachima.p7.delivery_policy.v0"
SACHIMA_P7_DELIVERY_SLOT_TYPE = "sachima.p7.delivery_slot.v0"
SACHIMA_P7_DELIVERY_ATTEMPT_TYPE = "sachima.p7.delivery_attempt.v0"
SACHIMA_P7_ACK_EVENT_TYPE = "sachima.p7.ack_event.v0"
SACHIMA_P7_DELIVERY_RESULT_TYPE = "sachima.p7.delivery_result.v0"
SACHIMA_P7_STATE_PROJECTION_TYPE = "sachima.p7.delivery_state_projection.v0"
SACHIMA_P7_CONTRACT_TYPE = "sachima.p7.delivery_ack_contract.v0"
SACHIMA_P7_SUCCESS_VERDICT = "p7_delivery_ack_closure_implementation_ready_for_canary_request_only"

# The exact operator approval token a policy must carry to flip `enabled`. It is
# the named future-implementation approval phrase from the design manifest; it is
# a control token, not a secret, and never appears in any export.
SACHIMA_P7_DELIVERY_ENABLE_TOKEN = (
    "approve_sachima_p7_real_delivery_ack_closure_implementation_default_off_bounded_adapter_path"
    "_no_live_default_on_no_public_ingress_no_production_config_write_no_gateway_restart"
    "_no_real_agent_execution_no_write_roles_no_unbounded_delivery"
)

_ALLOWED_SURFACES = ("progress_card", "rich_card", "final_text", "media", "artifact")
_ADAPTER_OUTCOMES = ("accepted", "failed", "timeout", "unknown")

_SEPARATE_APPROVALS = (
    "bounded_recipient_canary_send",
    "limited_live_pilot",
    "live_default_on_behavior",
    "public_ingress",
    "production_config_write",
    "gateway_restart_or_reload",
    "gateway_owned_temporal_worker_lifecycle",
    "platform_adapter_mutation",
    "real_agent_execution",
    "write_capable_roles",
    "production_traffic",
)
_FORBIDDEN_SIDE_EFFECTS = (
    "real_external_delivery",
    "gateway_run_change",
    "gateway_platform_adapter_access",
    "platform_adapter_mutation",
    "production_config_write",
    "gateway_restart",
    "network_listener",
    "client_connect_factory",
    "worker_lifecycle",
    "sub" + "process",
    "sock" + "et",
    "credential_creation",
    "raw_material_persistence",
)
_CHECKS = (
    "default_off_zero_adapter_calls",
    "enabled_requires_exact_approval_token",
    "bounded_target_and_surface_allowlist",
    "surfaces_are_independent_slots",
    "ack_from_send_response_or_approved_receipt_only",
    "accepted_records_ack_only_for_initialized_slot",
    "identical_replay_idempotent_no_second_send",
    "divergent_replay_fails_closed_before_send",
    "timeout_or_unknown_becomes_watch_not_success",
    "stable_error_codes_only",
    "raw_material_rejected_and_never_leaked",
    "rollback_disables_new_sends_preserves_query",
)

_STABLE_ERROR_CODES = (
    "p7_delivery_disabled",
    "p7_delivery_url_unconfigured",
    "p7_delivery_target_not_approved",
    "p7_delivery_surface_not_approved",
    "p7_ack_target_mismatch",
    "p7_ack_missing",
    "p7_ack_duplicate",
    "p7_ack_unsafe_material",
    "p7_send_rejected",
    "p7_send_timeout",
    "p7_send_unknown",
    "p7_divergent_replay",
    "p7_max_attempts_exceeded",
    "p7_rollback_active",
    "p7_invalid_request",
    "p7_invalid_slot",
    "p7_invalid_policy",
)
_STABLE_ERROR_CODE_SET = frozenset(_STABLE_ERROR_CODES)

_POLICY_FIELDS = (
    "type",
    "enabled",
    "mode",
    "approval_token",
    "approved_targets",
    "allowed_surfaces",
    "delivery_url_class",
    "max_attempts",
    "side_effects",
)
_SLOT_FIELDS = ("type", "delivery_ref", "surface", "artifact_ref", "required", "side_effects")
_ATTEMPT_FIELDS = (
    "type",
    "attempt_id",
    "delivery_ref",
    "surface",
    "idempotency_key",
    "target_ref",
    "artifact_ref",
    "side_effects",
)
_RESPONSE_FIELDS = ("outcome", "delivery_ref", "surface", "receipt_ref")

_DELIVERY_REF_RE = re.compile(r"^runtime_delivery_(0|[1-9][0-9]*)$")
_ARTIFACT_REF_RE = re.compile(r"^runtime_artifact_(0|[1-9][0-9]*)$")
_ACK_REF_RE = re.compile(r"^runtime_delivery_ack_(0|[1-9][0-9]*)$")
_ATTEMPT_ID_RE = re.compile(r"^runtime_delivery_attempt_(0|[1-9][0-9]*)$")
_IDEMPOTENCY_KEY_RE = re.compile(r"^p7key_[a-z0-9_]{1,64}$")
_SAFE_LABEL_RE = re.compile(r"^safe_[a-z0-9_]{1,91}$")

_UNSAFE_KEY_MARKERS = (
    "raw",
    "prompt",
    "body",
    "payload",
    "card_json",
    "media_path",
    "media_bytes",
    "tool_output",
    "stdout",
    "stderr",
    "callback",
    "credential",
    "password",
    "api_key",
    "bearer",
    "traceback",
    "cookie",
)
_UNSAFE_EXACT_KEYS = frozenset(
    {"token", "secret", "signature", "headers", "chat_id", "user_id", "message_id", "recipient_id"}
)
_PRIVATE_PREFIXES = (
    "oc_",
    "ou_",
    "om_",
    "chat_",
    "message_",
    "platform_",
    "feishu_",
    "lark_",
    "telegram_",
)
_UNSAFE_VALUE_MARKERS = (
    "raw_prompt",
    "raw prompt",
    "tool_output",
    "card_json",
    "media_path",
    "media_bytes",
    "platform_payload",
    "callback_payload",
    "traceback",
    "runtimeerror:",
    "valueerror:",
    "exception:",
    "bearer ",
    "sk-",
    "password" + "=",
    "secret" + "=",
    "api" + "_key=",
    "/tmp/",
    "/home/",
    "media:",
)
_NO_LEAK_MARKERS = (
    "raw_prompt",
    "tool_output",
    "card_json",
    "media_path",
    "media_bytes",
    "platform_payload",
    "callback_payload",
    "traceback",
    "runtimeerror:",
    "valueerror:",
    "bearer ",
    "sk-",
    "password" + "=",
    "secret" + "=",
    "api" + "_key=",
    "/tmp/",
    "/home/",
    "oc_",
    "ou_",
    "om_",
    "chat_id",
    "user_id",
    "message_id",
    "recipient_id",
    "credential",
    "signed_url",
)

_INVALID = object()


def describe_sachima_p7_delivery_ack_contract() -> dict[str, object]:
    """Return the machine-readable P7 delivery/ACK boundary descriptor."""

    return {
        "type": SACHIMA_P7_CONTRACT_TYPE,
        "version": SACHIMA_P7_DELIVERY_ACK_VERSION,
        "phase": "p7",
        "verdict": SACHIMA_P7_SUCCESS_VERDICT,
        "scope": "default_off_bounded_real_delivery_ack_closure_controller",
        "default_off": True,
        "allowed_surfaces": list(_ALLOWED_SURFACES),
        "ack_sources": ["send_response", "approved_receipt"],
        "adapter_outcomes": list(_ADAPTER_OUTCOMES),
        "error_codes": sorted(_STABLE_ERROR_CODES),
        "checks": list(_CHECKS),
        "separate_approvals": list(_SEPARATE_APPROVALS),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "future_canary_approval_required": True,
        "side_effects": [],
    }


def sachima_p7_delivery_policy(
    *,
    enabled: bool = False,
    approval_token: str = "",
    approved_targets: object = None,
    allowed_surfaces: object = None,
    delivery_url_class: str = "",
    max_attempts: int = 1,
) -> dict[str, object]:
    """Build a P7 delivery policy. Default-off and inert unless explicitly enabled.

    The enable path validates every primitive input by exact type *before*
    comparing or iterating it, so a hostile ``str`` subclass (lying ``__eq__`` /
    ``__ne__``) cannot satisfy the approval-token check and a hostile iterable
    (custom ``__iter__`` / ``__bool__``) cannot run arbitrary code during policy
    admission. ``enabled`` itself is matched by identity (``is not True``).
    """

    if enabled is not True:
        return _disabled_policy()
    if type(approval_token) is not str or approval_token != SACHIMA_P7_DELIVERY_ENABLE_TOKEN:
        _raise("p7_invalid_policy")
    return {
        "type": SACHIMA_P7_DELIVERY_POLICY_TYPE,
        "enabled": True,
        "mode": "controlled_real_delivery_ack_closure",
        "approval_token": SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
        "approved_targets": _safe_label_list(
            _plain_list_arg(approved_targets, error="p7_invalid_policy"), error="p7_invalid_policy"
        ),
        "allowed_surfaces": _surface_subset(
            _plain_list_arg(allowed_surfaces, error="p7_invalid_policy"), error="p7_invalid_policy"
        ),
        "delivery_url_class": _safe_url_class(delivery_url_class, error="p7_invalid_policy"),
        "max_attempts": _bounded_int(max_attempts, minimum=1, maximum=16, error="p7_invalid_policy"),
        "side_effects": [],
    }


def scan_sachima_p7_no_leak(value: object) -> dict[str, object]:
    """Render a projection and report any forbidden raw/private markers found."""

    rendered = _render(value)
    hits = sorted(marker for marker in _NO_LEAK_MARKERS if marker in rendered)
    return {"passed": not hits, "raw_marker_hits": len(hits), "markers": hits}


class SachimaP7DeliveryAckController:
    """Default-off controller mediating bounded real delivery and ACK closure."""

    def __init__(self, *, policy: object) -> None:
        self._policy = _validate_policy(policy)
        self._slots: dict[str, dict[str, object]] = {}
        self._ack_events: list[dict[str, object]] = []
        self._fingerprints: dict[str, str] = {}
        self._projections: dict[str, dict[str, object]] = {}
        self._attempts: dict[str, int] = {}
        self._ack_seq = 0
        self._rolled_back = False
        self._counts: dict[str, int] = {
            "adapter_calls": 0,
            "ack_recorded": 0,
            "duplicate_replays": 0,
            "delivered": 0,
            "watch": 0,
            "failed": 0,
            "rejected": 0,
            "disabled": 0,
            "rolled_back": 0,
        }
        self._histogram: dict[str, int] = {}

    def initialize_slot(self, slot: object) -> dict[str, object]:
        """Register one initialized delivery slot for a single surface."""

        safe = _validate_slot(slot)
        delivery_ref = str(safe["delivery_ref"])
        if delivery_ref in self._slots:
            _raise("p7_invalid_slot")
        self._slots[delivery_ref] = {
            "delivery_ref": delivery_ref,
            "surface": safe["surface"],
            "artifact_ref": safe["artifact_ref"],
            "required": safe["required"],
            "state": "initialized",
            "state_version": 0,
        }
        return dict(self._slots[delivery_ref])

    def deliver_slot(self, *, attempt: object, adapter: Callable[[dict[str, object]], object]) -> dict[str, object]:
        """Attempt bounded delivery for one initialized slot through a fake/real send seam."""

        if self._rolled_back:
            return self._reject("rolled_back", "p7_rollback_active")
        if self._policy["enabled"] is not True:
            return self._reject("disabled", "p7_delivery_disabled")
        if self._policy["delivery_url_class"] == "":
            return self._reject("rejected", "p7_delivery_url_unconfigured")

        try:
            safe = _validate_attempt(attempt)
        except ValueError as exc:
            return self._reject("rejected", _attempt_error_code(str(exc)))

        delivery_ref = str(safe["delivery_ref"])
        surface = str(safe["surface"])
        attempt_id = str(safe["attempt_id"])
        key = str(safe["idempotency_key"])
        target_ref = str(safe["target_ref"])
        refs = {"delivery_ref": delivery_ref, "surface": surface, "attempt_id": attempt_id, "idempotency_key": key}

        slot = self._slots.get(delivery_ref)
        if slot is None or slot["surface"] != surface:
            return self._reject("rejected", "p7_ack_target_mismatch", **refs)
        if surface not in self._policy["allowed_surfaces"]:
            return self._reject("rejected", "p7_delivery_surface_not_approved", **refs)
        if target_ref not in self._policy["approved_targets"]:
            return self._reject("rejected", "p7_delivery_target_not_approved", **refs)

        if key in self._fingerprints:
            if self._fingerprints[key] == _fingerprint(safe):
                self._counts["duplicate_replays"] += 1
                return copy.deepcopy(self._projections[key])
            return self._reject("rejected", "p7_divergent_replay", **refs)

        if slot["state"] == "acked":
            return self._reject("rejected", "p7_ack_duplicate", **refs)
        if self._attempts.get(delivery_ref, 0) >= int(self._policy["max_attempts"]):
            return self._reject("rejected", "p7_max_attempts_exceeded", **refs)

        return self._perform_send(safe=safe, slot=slot, adapter=adapter)

    def rollback(self) -> dict[str, object]:
        """Disable new sends; existing state and query/export remain available."""

        self._rolled_back = True
        return {
            "type": SACHIMA_P7_STATE_PROJECTION_TYPE,
            "rolled_back": True,
            "new_sends_disabled": True,
            "gateway_restart_required": False,
            "side_effects": [],
        }

    def query(self) -> dict[str, object]:
        """Return a sanitized projection of slots, ACK events, counts, and histogram."""

        projection = {
            "type": SACHIMA_P7_STATE_PROJECTION_TYPE,
            "version": SACHIMA_P7_DELIVERY_ACK_VERSION,
            "enabled": self._policy["enabled"],
            "rolled_back": self._rolled_back,
            "slots": [dict(self._slots[ref]) for ref in sorted(self._slots)],
            "ack_events": [dict(event) for event in self._ack_events],
            "counts": dict(self._counts),
            "error_code_histogram": dict(sorted(self._histogram.items())),
            "side_effects": [],
        }
        return _checked(projection)

    def _perform_send(
        self,
        *,
        safe: dict[str, object],
        slot: dict[str, object],
        adapter: Callable[[dict[str, object]], object],
    ) -> dict[str, object]:
        delivery_ref = str(safe["delivery_ref"])
        surface = str(safe["surface"])
        self._attempts[delivery_ref] = self._attempts.get(delivery_ref, 0) + 1
        self._counts["adapter_calls"] += 1
        slot["state"] = "pending"
        slot["state_version"] = int(slot["state_version"]) + 1

        send_request = {
            "delivery_ref": delivery_ref,
            "surface": surface,
            "target_ref": safe["target_ref"],
            "artifact_ref": safe["artifact_ref"],
            "idempotency_key": safe["idempotency_key"],
            "delivery_url_class": self._policy["delivery_url_class"],
        }

        try:
            response = adapter(send_request)
        except Exception:
            # Send outcome is unknown — never optimistic, never echo exception text.
            return self._finalize(safe, slot, status="watch", slot_state="watch", error_code="p7_send_unknown")

        try:
            outcome, receipt_ref = _classify_response(response, delivery_ref=delivery_ref, surface=surface)
        except ValueError as exc:
            code = str(exc) if str(exc) in _STABLE_ERROR_CODE_SET else "p7_ack_unsafe_material"
            return self._finalize(safe, slot, status="rejected", slot_state="unknown", error_code=code)

        if outcome == "accepted":
            if receipt_ref is None:
                return self._finalize(safe, slot, status="watch", slot_state="watch", error_code="p7_ack_missing")
            ack = self._record_ack(delivery_ref=delivery_ref, surface=surface, receipt_ref=receipt_ref, slot=slot)
            return self._finalize(safe, slot, status="delivered", slot_state="acked", error_code=None, ack=ack)
        if outcome == "failed":
            return self._finalize(safe, slot, status="failed", slot_state="failed", error_code="p7_send_rejected")
        if outcome == "timeout":
            return self._finalize(safe, slot, status="watch", slot_state="watch", error_code="p7_send_timeout")
        return self._finalize(safe, slot, status="watch", slot_state="watch", error_code="p7_send_unknown")

    def _record_ack(
        self,
        *,
        delivery_ref: str,
        surface: str,
        receipt_ref: str,
        slot: dict[str, object],
    ) -> dict[str, object]:
        slot["state"] = "acked"
        slot["state_version"] = int(slot["state_version"]) + 1
        self._ack_seq += 1
        ack = {
            "type": SACHIMA_P7_ACK_EVENT_TYPE,
            "ack_ref": receipt_ref,
            "delivery_ref": delivery_ref,
            "surface": surface,
            "status": "acknowledged",
            "source": "send_response",
            "duplicate": False,
            "state_version": int(slot["state_version"]),
            "side_effects": [],
        }
        self._ack_events.append(dict(ack))
        self._counts["ack_recorded"] += 1
        return ack

    def _finalize(
        self,
        safe: dict[str, object],
        slot: dict[str, object],
        *,
        status: str,
        slot_state: str,
        error_code: str | None,
        ack: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if slot["state"] != slot_state:
            slot["state"] = slot_state
            slot["state_version"] = int(slot["state_version"]) + 1
        key = str(safe["idempotency_key"])
        result = self._build_result(
            status=status,
            error_code=error_code,
            delivery_ref=str(safe["delivery_ref"]),
            surface=str(safe["surface"]),
            attempt_id=str(safe["attempt_id"]),
            idempotency_key=key,
            slot_state=slot_state,
            ack=ack,
        )
        self._fingerprints[key] = _fingerprint(safe)
        self._projections[key] = copy.deepcopy(result)
        return result

    def _reject(
        self,
        status: str,
        error_code: str,
        *,
        delivery_ref: str | None = None,
        surface: str | None = None,
        attempt_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        return self._build_result(
            status=status,
            error_code=error_code,
            delivery_ref=delivery_ref,
            surface=surface,
            attempt_id=attempt_id,
            idempotency_key=idempotency_key,
            slot_state=None,
            ack=None,
        )

    def _build_result(
        self,
        *,
        status: str,
        error_code: str | None,
        delivery_ref: str | None,
        surface: str | None,
        attempt_id: str | None,
        idempotency_key: str | None,
        slot_state: str | None,
        ack: dict[str, object] | None,
    ) -> dict[str, object]:
        if error_code is not None and error_code not in _STABLE_ERROR_CODE_SET:
            raise RuntimeError("unstable_error_code")
        self._counts[status] = self._counts.get(status, 0) + 1
        if error_code is not None:
            self._histogram[error_code] = self._histogram.get(error_code, 0) + 1
        result = {
            "type": SACHIMA_P7_DELIVERY_RESULT_TYPE,
            "version": SACHIMA_P7_DELIVERY_ACK_VERSION,
            "status": status,
            "delivery_ref": delivery_ref,
            "surface": surface,
            "attempt_id": attempt_id,
            "idempotency_key": idempotency_key,
            "slot_state": slot_state,
            "ack": dict(ack) if ack is not None else None,
            "error_code": error_code,
            "side_effects": [],
        }
        return _checked(result)


def _classify_response(value: object, *, delivery_ref: str, surface: str) -> tuple[str, str | None]:
    _reject_unsafe_material(value, error="p7_ack_unsafe_material")
    source = _plain_dict_with_fields(value, _RESPONSE_FIELDS, "p7_invalid_request")
    outcome = _one_of(source["outcome"], set(_ADAPTER_OUTCOMES), "p7_invalid_request")
    if source["delivery_ref"] != delivery_ref or source["surface"] != surface:
        _raise("p7_ack_target_mismatch")
    receipt = source["receipt_ref"]
    if outcome == "accepted":
        if receipt is None:
            return outcome, None
        return outcome, _safe_ref(receipt, _ACK_REF_RE, "p7_ack_unsafe_material")
    if receipt is not None:
        _raise("p7_invalid_request")
    return outcome, None


def _validate_policy(policy: object) -> dict[str, object]:
    safe = _plain_dict_with_fields(policy, _POLICY_FIELDS, "p7_invalid_policy")
    _literal(safe["type"], SACHIMA_P7_DELIVERY_POLICY_TYPE, "p7_invalid_policy")
    _empty_list(safe["side_effects"], error="p7_invalid_policy")
    enabled = _exact_bool(safe["enabled"], error="p7_invalid_policy")
    if enabled is False:
        expected = _disabled_policy()
        if {key: safe[key] for key in _POLICY_FIELDS} != expected:
            _raise("p7_invalid_policy")
        return expected
    _literal(safe["mode"], "controlled_real_delivery_ack_closure", "p7_invalid_policy")
    if safe["approval_token"] != SACHIMA_P7_DELIVERY_ENABLE_TOKEN:
        _raise("p7_invalid_policy")
    return {
        "type": SACHIMA_P7_DELIVERY_POLICY_TYPE,
        "enabled": True,
        "mode": "controlled_real_delivery_ack_closure",
        "approval_token": SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
        "approved_targets": _safe_label_list(safe["approved_targets"], error="p7_invalid_policy"),
        "allowed_surfaces": _surface_subset(safe["allowed_surfaces"], error="p7_invalid_policy"),
        "delivery_url_class": _safe_url_class(safe["delivery_url_class"], error="p7_invalid_policy"),
        "max_attempts": _bounded_int(safe["max_attempts"], minimum=1, maximum=16, error="p7_invalid_policy"),
        "side_effects": [],
    }


def _disabled_policy() -> dict[str, object]:
    return {
        "type": SACHIMA_P7_DELIVERY_POLICY_TYPE,
        "enabled": False,
        "mode": "default_off",
        "approval_token": "",
        "approved_targets": [],
        "allowed_surfaces": [],
        "delivery_url_class": "",
        "max_attempts": 1,
        "side_effects": [],
    }


def _validate_slot(slot: object) -> dict[str, object]:
    _reject_unsafe_material(slot, error="p7_invalid_slot")
    source = _plain_dict_with_fields(slot, _SLOT_FIELDS, "p7_invalid_slot")
    _literal(source["type"], SACHIMA_P7_DELIVERY_SLOT_TYPE, "p7_invalid_slot")
    _empty_list(source["side_effects"], error="p7_invalid_slot")
    return {
        "delivery_ref": _safe_ref(source["delivery_ref"], _DELIVERY_REF_RE, "p7_invalid_slot"),
        "surface": _one_of(source["surface"], set(_ALLOWED_SURFACES), "p7_invalid_slot"),
        "artifact_ref": _optional_ref(source["artifact_ref"], _ARTIFACT_REF_RE, "p7_invalid_slot"),
        "required": _exact_bool(source["required"], error="p7_invalid_slot"),
    }


def _validate_attempt(attempt: object) -> dict[str, object]:
    _reject_unsafe_material(attempt, error="p7_ack_unsafe_material")
    source = _plain_dict_with_fields(attempt, _ATTEMPT_FIELDS, "p7_invalid_request")
    _literal(source["type"], SACHIMA_P7_DELIVERY_ATTEMPT_TYPE, "p7_invalid_request")
    _empty_list(source["side_effects"], error="p7_invalid_request")
    return {
        "type": SACHIMA_P7_DELIVERY_ATTEMPT_TYPE,
        "attempt_id": _safe_ref(source["attempt_id"], _ATTEMPT_ID_RE, "p7_invalid_request"),
        "delivery_ref": _safe_ref(source["delivery_ref"], _DELIVERY_REF_RE, "p7_invalid_request"),
        "surface": _one_of(source["surface"], set(_ALLOWED_SURFACES), "p7_invalid_request"),
        "idempotency_key": _safe_ref(source["idempotency_key"], _IDEMPOTENCY_KEY_RE, "p7_invalid_request"),
        "target_ref": _safe_label(source["target_ref"], error="p7_invalid_request"),
        "artifact_ref": _optional_ref(source["artifact_ref"], _ARTIFACT_REF_RE, "p7_invalid_request"),
    }


def _fingerprint(safe_attempt: dict[str, object]) -> str:
    material = "|".join(
        (
            "p7",
            str(safe_attempt["delivery_ref"]),
            str(safe_attempt["surface"]),
            str(safe_attempt["target_ref"]),
            str(safe_attempt["artifact_ref"]),
        )
    )
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _attempt_error_code(message: str) -> str:
    return message if message in _STABLE_ERROR_CODE_SET else "p7_invalid_request"


def _plain_list_arg(value: object, *, error: str) -> list[object]:
    """Normalize a public-builder list argument without touching untrusted objects.

    The omitted default (``None``) becomes an empty list. Any provided value must
    be an exact plain ``list``; a hostile sequence/iterable (custom ``__iter__``,
    ``list`` subclass, tuple, generator, ...) is rejected by an exact-type check
    *before* it is iterated or truth-tested, so no untrusted ``__iter__`` /
    ``__bool__`` / ``__len__`` runs during policy admission. Item-level
    validation is left to the caller's list validator.
    """

    if value is None:
        return []
    if type(value) is not list:
        _raise(error)
    return value


def _safe_label_list(value: object, *, error: str) -> list[str]:
    items = _plain_list(value, error=error)
    safe: list[str] = []
    for item in items:
        label = _safe_label(item, error=error)
        if label not in safe:
            safe.append(label)
    return safe


def _surface_subset(value: object, *, error: str) -> list[str]:
    items = _plain_list(value, error=error)
    safe: list[str] = []
    for item in items:
        surface = _one_of(item, set(_ALLOWED_SURFACES), error)
        if surface not in safe:
            safe.append(surface)
    return safe


def _safe_url_class(value: object, *, error: str) -> str:
    # Exact-type check before the ``== ""`` comparison so a hostile ``str``
    # subclass with a lying ``__eq__`` can't drive the empty/url-class branch.
    if type(value) is not str:
        _raise(error)
    if value == "":
        return ""
    return _safe_label(value, error=error)


def _safe_label(value: object, *, error: str) -> str:
    if type(value) is not str or _SAFE_LABEL_RE.fullmatch(value) is None:
        _raise(error)
    lowered = value.lower()
    if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
        _raise(error)
    if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
        _raise(error)
    return value


def _safe_ref(value: object, regex: re.Pattern[str], error: str) -> str:
    if type(value) is not str or regex.fullmatch(value) is None:
        _raise(error)
    lowered = value.lower()
    if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
        _raise(error)
    if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
        _raise(error)
    return value


def _optional_ref(value: object, regex: re.Pattern[str], error: str) -> str | None:
    if value is None:
        return None
    return _safe_ref(value, regex, error)


def _one_of(value: object, allowed: set[str], error: str) -> str:
    if type(value) is not str or value not in allowed:
        _raise(error)
    return value


def _literal(value: object, expected: str, error: str) -> str:
    if value != expected:
        _raise(error)
    return expected


def _exact_bool(value: object, *, error: str) -> bool:
    if value is True:
        return True
    if value is False:
        return False
    _raise(error)


def _bounded_int(value: object, *, minimum: int, maximum: int, error: str) -> int:
    if type(value) is not int or isinstance(value, bool) or not (minimum <= value <= maximum):
        _raise(error)
    return value


def _plain_dict_with_fields(value: object, fields: tuple[str, ...], error: str) -> dict[str, object]:
    safe = _plain_dict(value, error=error)
    if set(safe) != set(fields):
        _raise(error)
    return safe


def _plain_dict(value: object, *, error: str) -> dict[str, object]:
    copied = _plain_copy(value)
    if type(copied) is not dict:
        _raise(error)
    return copied


def _plain_list(value: object, *, error: str) -> list[object]:
    copied = _plain_copy(value)
    if type(copied) is not list:
        _raise(error)
    return copied


def _empty_list(value: object, *, error: str) -> list[object]:
    if _plain_copy(value) != []:
        _raise(error)
    return []


def _plain_copy(value: object) -> object:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is list:
        copied_list: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_list.append(copied)
        return copied_list
    if type(value) is dict:
        copied_dict: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                return _INVALID
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_dict[key] = copied
        return copied_dict
    return _INVALID


def _reject_unsafe_material(value: object, *, error: str) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _raise(error)
            lowered = key.lower()
            if lowered in _UNSAFE_EXACT_KEYS or any(marker in lowered for marker in _UNSAFE_KEY_MARKERS):
                _raise(error)
            _reject_unsafe_material(item, error=error)
        return
    if type(value) is list:
        for item in value:
            _reject_unsafe_material(item, error=error)
        return
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is str:
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
            _raise(error)
        if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
            _raise(error)
        return
    _raise(error)


def _render(value: object) -> str:
    parts: list[str] = []

    def walk(node: object) -> None:
        if type(node) is dict:
            for key, item in node.items():
                parts.append(str(key).lower())
                walk(item)
            return
        if type(node) is list:
            for item in node:
                walk(item)
            return
        parts.append(str(node).lower())

    walk(value)
    return "\n".join(parts)


def _checked(projection: dict[str, object]) -> dict[str, object]:
    scan = scan_sachima_p7_no_leak(projection)
    if scan["passed"] is not True:
        raise RuntimeError("unsafe_output")
    return projection


def _raise(error: str) -> None:
    raise ValueError(error) from None


__all__ = [
    "SACHIMA_P7_ACK_EVENT_TYPE",
    "SACHIMA_P7_CONTRACT_TYPE",
    "SACHIMA_P7_DELIVERY_ACK_VERSION",
    "SACHIMA_P7_DELIVERY_ATTEMPT_TYPE",
    "SACHIMA_P7_DELIVERY_ENABLE_TOKEN",
    "SACHIMA_P7_DELIVERY_POLICY_TYPE",
    "SACHIMA_P7_DELIVERY_RESULT_TYPE",
    "SACHIMA_P7_DELIVERY_SLOT_TYPE",
    "SACHIMA_P7_STATE_PROJECTION_TYPE",
    "SACHIMA_P7_SUCCESS_VERDICT",
    "SachimaP7DeliveryAckController",
    "describe_sachima_p7_delivery_ack_contract",
    "sachima_p7_delivery_policy",
    "scan_sachima_p7_no_leak",
]
