"""S5 downstream delivery reconnect over the default-off P7 ACK controller.

This module is the separately approved S5 implementation gate: it consumes the
already-sanitized S4 ``ActivityOutput`` and reconnects it to the already-merged
P7 delivery/ACK controller through a caller-injected fake send seam. It performs
no real delivery, constructs no platform adapter, starts no Worker/service/runtime
or subprocess, and gives the Gateway no Temporal/lifecycle ownership.

The extra S5-owned safety boundary is a durable pre-claim written before calling
``SachimaP7DeliveryAckController.deliver_slot(...)``. A resident claim reconciles
Temporal retries/recovery without relaunching a send; an uncertain pre-claimed
outcome is WATCH, never an optimistic delivery and never a second send.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
from typing import Any, Callable

from temporalio.exceptions import ApplicationError

from gateway.sachima_delivery_ack import (
    SACHIMA_P7_ACK_EVENT_TYPE,
    SACHIMA_P7_DELIVERY_ACK_VERSION,
    SACHIMA_P7_DELIVERY_ATTEMPT_TYPE,
    SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
    SACHIMA_P7_DELIVERY_RESULT_TYPE,
    SACHIMA_P7_DELIVERY_SLOT_TYPE,
    SachimaP7DeliveryAckController,
    sachima_p7_delivery_policy,
    scan_sachima_p7_no_leak,
)

from . import contracts as C

S5_DOWNSTREAM_DELIVERY_RECONNECT_APPROVAL_TOKEN = (
    "approve_sachima_s5_downstream_delivery_reconnect_implementation_default_off_"
    "injected_fake_send_seam_only_s5_owned_durable_preclaim_before_deliver_slot_"
    "no_real_send_no_gateway_feishu_live_default_on_public_ingress_no_production_config_"
    "no_write_roles_gateway_not_temporal_caller_lifecycle_owner_or_worker_owner"
)

S5_RECONNECT_CONTRACT_TYPE = "sachima.s5.downstream_delivery_reconnect_contract.v0"
S5_RECONNECT_REQUEST_TYPE = "sachima.s5.downstream_delivery_reconnect_request.v0"
S5_RECONNECT_CLAIM_TYPE = "sachima.s5.downstream_delivery_claim.v0"
S5_RECONNECT_STATE_TYPE = "sachima.s5.downstream_delivery_state.v0"
S5_RECONNECT_VERSION = "sachima.s5.downstream_delivery_reconnect.v0"

_ALLOWED_ARTIFACT_KINDS = frozenset(
    {"architecture_packet", "implementation_candidate_analysis", "blocker_review"}
)
_ALLOWED_INTENTS = frozenset(_ALLOWED_ARTIFACT_KINDS)
_ALLOWED_SURFACES = frozenset({"final_text", "rich_card"})
_ALLOWED_DELIVERY_ROLES = frozenset({"sachima_delivery_read_only_reporter"})
_SAFE_LABEL_RE = re.compile(r"^safe_[a-z0-9_]{1,91}$")
_DELIVERY_REF_RE = re.compile(r"^runtime_delivery_(0|[1-9][0-9]*)$")
_ATTEMPT_ID_RE = re.compile(r"^runtime_delivery_attempt_(0|[1-9][0-9]*)$")
_ACK_REF_RE = re.compile(r"^runtime_delivery_ack_(0|[1-9][0-9]*)$")
_RUNTIME_ARTIFACT_RE = re.compile(r"^runtime_artifact_(0|[1-9][0-9]*)$")
_IDEMPOTENCY_KEY_RE = re.compile(r"^p7key_[a-z0-9_]{1,64}$")
_SLOT_KEYS = frozenset({"type", "delivery_ref", "surface", "artifact_ref", "required", "side_effects"})
_ATTEMPT_KEYS = frozenset(
    {"type", "attempt_id", "delivery_ref", "surface", "idempotency_key", "target_ref", "artifact_ref", "side_effects"}
)
_RESULT_PROJECTION_KEYS = frozenset(
    {"type", "version", "status", "delivery_ref", "surface", "attempt_id", "idempotency_key", "slot_state", "ack", "error_code", "side_effects"}
)
_ACK_EVENT_KEYS = frozenset(
    {"type", "ack_ref", "delivery_ref", "surface", "status", "source", "duplicate", "state_version", "side_effects"}
)
_RESULT_STATUSES = frozenset({"delivered", "watch", "failed"})
_FORBIDDEN_SAFE_LABEL_PARTS = (
    "default_on",
    "live",
    "platform",
    "gateway",
    "feishu",
    "lark",
    "write",
    "mutate",
    "approve",
    "reject",
    "public_ingress",
)
_S5_NO_LEAK_MARKERS = (
    "raw_prompt",
    "raw prompt",
    "tool_output",
    "agent_stdout",
    "stdout",
    "stderr",
    "card_json",
    "platform_payload",
    "callback_payload",
    "traceback",
    "runtimeerror:",
    "valueerror:",
    "oc_",
    "ou_",
    "om_",
    "chat_id",
    "user_id",
    "message_id",
    "recipient_id",
    "bearer ",
    "sk-",
    "password" + "=",
    "secret" + "=",
    "api" + "_key=",
    "/tmp/",
    "/home/",
)
_TRANSIENT_RETRYABLE_CODES = frozenset({"p7_send_timeout", "p7_send_unknown"})
_NON_RETRYABLE_CODES = frozenset(
    {
        "p7_delivery_disabled",
        "p7_invalid_policy",
        "p7_invalid_request",
        "p7_invalid_slot",
        "p7_delivery_target_not_approved",
        "p7_delivery_surface_not_approved",
        "p7_delivery_url_unconfigured",
        "p7_ack_target_mismatch",
        "p7_ack_duplicate",
        "p7_ack_unsafe_material",
        "p7_divergent_replay",
        "p7_max_attempts_exceeded",
        "p7_rollback_active",
        "p7_send_rejected",
        "p7_ack_missing",
        "delivery_cancelled",
    }
)


def describe_sachima_s5_downstream_delivery_reconnect_contract() -> dict[str, object]:
    """Return the machine-readable S5 reconnect boundary descriptor."""

    return {
        "type": S5_RECONNECT_CONTRACT_TYPE,
        "version": S5_RECONNECT_VERSION,
        "phase": "s5_downstream_delivery_reconnect",
        "default_off": True,
        "send_seam": "injected_fake_only",
        "preclaim_before_deliver_slot": True,
        "gateway_temporal_caller": False,
        "gateway_lifecycle_owner": False,
        "gateway_worker_owner": False,
        "platform_adapter_constructed": False,
        "worker_started_by_s5": False,
        "real_send_approved": False,
        "allowed_artifact_kinds": sorted(_ALLOWED_ARTIFACT_KINDS),
        "allowed_surfaces": sorted(_ALLOWED_SURFACES),
        "allowed_delivery_roles": sorted(_ALLOWED_DELIVERY_ROLES),
        "forbidden_side_effects": [
            "gateway_restart",
            "gateway_reload",
            "platform_adapter_construction",
            "platform_adapter_mutation",
            "public_ingress",
            "production_config_write",
            "write_capable_roles",
            "worker_lifecycle",
            "service_startup",
            "subprocess_start",
            "network_listener",
            "real_send",
        ],
        "side_effects": [],
    }


def build_s5_delivery_reconnect_request(
    *,
    activity_output: object,
    intent_class: object,
    target_ref: object,
    surfaces: object,
    delivery_role_key: object,
    idempotency_key: object | None = None,
) -> dict[str, object]:
    """Build a sanitized S5 reconnect request from S4 ``ActivityOutput``.

    The returned request carries only claim-check refs/digests, safe delivery
    labels, deterministic P7 runtime refs, and an idempotency key. Raw content,
    platform ids, card JSON, and recipient ids are rejected before construction.
    """

    output = _activity_output(activity_output)
    artifact = output.artifact_ref
    artifact_kind = _artifact_kind(artifact.artifact_kind)
    intent = _one_of(intent_class, _ALLOWED_INTENTS, "invalid_intent")
    if intent != artifact_kind:
        _raise("invalid_intent")
    role = _one_of(delivery_role_key, _ALLOWED_DELIVERY_ROLES, "invalid_delivery_role")
    target = _safe_target(target_ref)
    safe_surfaces = _surfaces(surfaces)
    key = _idempotency_key(idempotency_key) if idempotency_key is not None else _default_idempotency_key(safe_surfaces[0])
    artifact_projection = C.step_artifact_ref_projection(artifact)
    delivery_slots = []
    delivery_attempts = []
    for index, surface in enumerate(safe_surfaces):
        delivery_ref = f"runtime_delivery_{index}"
        delivery_slots.append(
            {
                "type": SACHIMA_P7_DELIVERY_SLOT_TYPE,
                "delivery_ref": delivery_ref,
                "surface": surface,
                "artifact_ref": "runtime_artifact_0",
                "required": True,
                "side_effects": [],
            }
        )
        attempt_key = key if index == 0 else _default_idempotency_key(surface, index=index)
        delivery_attempts.append(
            {
                "type": SACHIMA_P7_DELIVERY_ATTEMPT_TYPE,
                "attempt_id": f"runtime_delivery_attempt_{index}",
                "delivery_ref": delivery_ref,
                "surface": surface,
                "idempotency_key": attempt_key,
                "target_ref": target,
                "artifact_ref": "runtime_artifact_0",
                "side_effects": [],
            }
        )
    request = {
        "type": S5_RECONNECT_REQUEST_TYPE,
        "version": S5_RECONNECT_VERSION,
        "phase": "s5_downstream_delivery_reconnect",
        "intent_class": intent,
        "target_ref": target,
        "surfaces": safe_surfaces,
        "delivery_role_key": role,
        "artifact_ref": "runtime_artifact_0",
        "artifact_claim_ref": artifact_projection,
        "evidence_ref": output.evidence_ref,
        "evidence_digest": output.evidence_digest,
        "delivery_slots": delivery_slots,
        "delivery_attempts": delivery_attempts,
        "side_effects": [],
    }
    _ensure_clean(request)
    return request


class S5DurableDeliveryClaimStore:
    """In-memory durable-claim seam for S5 tests / local injection.

    The interface is intentionally plain and copy-based so production persistence
    can replace it later without changing controller semantics. S5 writes the
    claim before calling P7; resident claims reconcile recovery without resending.
    """

    def __init__(self, initial: dict[str, object] | None = None) -> None:
        self._lock = threading.Lock()
        self._claims: dict[str, dict[str, object]] = copy.deepcopy(initial or {})

    def preclaim(self, *, idempotency_key: str, fingerprint: str) -> dict[str, object]:
        with self._lock:
            existing = self._claims.get(idempotency_key)
            if existing is not None:
                if existing.get("fingerprint") != fingerprint:
                    return {
                        "type": S5_RECONNECT_CLAIM_TYPE,
                        "idempotency_key": idempotency_key,
                        "state": "divergent",
                        "terminal": False,
                        "preexisting": True,
                        "projection": None,
                        "error_code": "p7_divergent_replay",
                        "side_effects": [],
                    }
                resident = copy.deepcopy(existing)
                resident["preexisting"] = True
                return resident
            record = {
                "type": S5_RECONNECT_CLAIM_TYPE,
                "idempotency_key": idempotency_key,
                "fingerprint": fingerprint,
                "state": "claimed",
                "terminal": False,
                "preexisting": False,
                "projection": None,
                "error_code": None,
                "side_effects": [],
            }
            self._claims[idempotency_key] = copy.deepcopy(record)
            return copy.deepcopy(record)

    def peek(self, *, idempotency_key: str) -> dict[str, object] | None:
        """Return a copy of a resident claim without writing or mutating it."""

        with self._lock:
            existing = self._claims.get(idempotency_key)
            if existing is None:
                return None
            resident = copy.deepcopy(existing)
            resident["preexisting"] = True
            return resident

    def finalize(self, *, idempotency_key: str, fingerprint: str, projection: dict[str, object]) -> dict[str, object]:
        _ensure_clean(projection)
        with self._lock:
            existing = self._claims.get(idempotency_key)
            if existing is not None and existing.get("fingerprint") != fingerprint:
                return {
                    "type": S5_RECONNECT_CLAIM_TYPE,
                    "idempotency_key": idempotency_key,
                    "state": "divergent",
                    "terminal": False,
                    "projection": None,
                    "error_code": "p7_divergent_replay",
                    "side_effects": [],
                }
            record = {
                "type": S5_RECONNECT_CLAIM_TYPE,
                "idempotency_key": idempotency_key,
                "fingerprint": fingerprint,
                "state": "terminal",
                "terminal": True,
                "projection": copy.deepcopy(projection),
                "error_code": projection.get("error_code"),
                "side_effects": [],
            }
            self._claims[idempotency_key] = copy.deepcopy(record)
            return copy.deepcopy(record)

    def query(self) -> dict[str, object]:
        with self._lock:
            projection = {
                "type": S5_RECONNECT_STATE_TYPE,
                "version": S5_RECONNECT_VERSION,
                "claims": copy.deepcopy(dict(sorted(self._claims.items()))),
                "side_effects": [],
            }
        _ensure_clean(projection)
        return projection


class S5DeliveryReconnectController:
    """Caller-owned S5 reconnect controller over the P7 controller."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        approval_token: str = "",
        claim_store: S5DurableDeliveryClaimStore | None = None,
        approved_targets: object = (),
        allowed_surfaces: object = (),
        delivery_url_class: object = "",
        max_attempts: int = 1,
    ) -> None:
        self.enabled = enabled
        self.approval_token = approval_token
        self.claim_store = claim_store or S5DurableDeliveryClaimStore()
        self.approved_targets = tuple(_safe_target(target) for target in _plain_sequence(approved_targets))
        self.allowed_surfaces = tuple(_one_of(surface, _ALLOWED_SURFACES, "p7_delivery_surface_not_approved") for surface in _plain_sequence(allowed_surfaces))
        self.delivery_url_class = _safe_delivery_url_class(delivery_url_class)
        if type(max_attempts) is not int or max_attempts < 1 or max_attempts > 16:
            _raise("p7_invalid_policy")
        self.max_attempts = max_attempts

    def preclaim(self, *, request: object) -> dict[str, object]:
        safe_request = _validate_request(request)
        key = _first_key(safe_request)
        return self.claim_store.preclaim(idempotency_key=key, fingerprint=_fingerprint(safe_request))

    def deliver(self, *, request: object, adapter: Callable[[dict[str, object]], object] | None) -> dict[str, object]:
        try:
            safe_request = _validate_request(request)
        except ValueError:
            return _result(status="rejected", error_code="p7_invalid_request")
        refs = _result_refs(safe_request)
        if not self._admitted():
            return _result(status="disabled", error_code="p7_delivery_disabled", **refs)
        if not callable(adapter):
            return _result(status="rejected", error_code="p7_invalid_request", **refs)

        policy_error = self._policy_error_for_request(safe_request)
        if policy_error is not None:
            return _result(status="rejected", error_code=policy_error, **refs)

        fingerprint = _fingerprint(safe_request)
        claim_records: list[tuple[str, dict[str, object]]] = []
        attempts = safe_request["delivery_attempts"]
        for attempt in attempts:
            key = _idempotency_key(attempt["idempotency_key"])
            claim = self.claim_store.preclaim(idempotency_key=key, fingerprint=fingerprint)
            if claim["state"] == "divergent":
                return _result(status="rejected", error_code="p7_divergent_replay", **refs)
            claim_records.append((key, claim))

        replay = _resident_terminal_replay([claim for _, claim in claim_records], refs, attempts)
        if replay is not None:
            return replay
        if any(_claim_preexisted_without_terminal(claim) for _, claim in claim_records):
            return _result(status="watch", error_code="p7_send_unknown", **refs)

        p7 = SachimaP7DeliveryAckController(
            policy=sachima_p7_delivery_policy(
                enabled=True,
                approval_token=SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
                approved_targets=list(self.approved_targets),
                allowed_surfaces=list(self.allowed_surfaces),
                delivery_url_class=self.delivery_url_class,
                max_attempts=self.max_attempts,
            )
        )
        for slot in safe_request["delivery_slots"]:
            p7.initialize_slot(slot)
        result: dict[str, object] | None = None
        for attempt in safe_request["delivery_attempts"]:
            key = _idempotency_key(attempt["idempotency_key"])
            result = p7.deliver_slot(attempt=attempt, adapter=adapter)
            _ensure_clean(result)
            self.claim_store.finalize(idempotency_key=key, fingerprint=fingerprint, projection=result)
            if result.get("status") not in {"delivered"}:
                break
        if result is None:
            result = _result(status="rejected", error_code="p7_invalid_request", **refs)
        _ensure_clean(result)
        return result

    def _policy_error_for_request(self, safe_request: dict[str, object]) -> str | None:
        slots = safe_request["delivery_slots"]
        attempts = safe_request["delivery_attempts"]
        surfaces = safe_request["surfaces"]
        if not isinstance(slots, list) or not isinstance(attempts, list) or not isinstance(surfaces, list):
            return "p7_invalid_request"
        for index, (slot, attempt) in enumerate(zip(slots, attempts, strict=True)):
            if type(slot) is not dict or type(attempt) is not dict:
                return "p7_invalid_request"
            if set(slot) != _SLOT_KEYS or set(attempt) != _ATTEMPT_KEYS:
                return "p7_invalid_request"
            if slot.get("type") != SACHIMA_P7_DELIVERY_SLOT_TYPE or attempt.get("type") != SACHIMA_P7_DELIVERY_ATTEMPT_TYPE:
                return "p7_invalid_request"
            if slot.get("side_effects") != [] or attempt.get("side_effects") != []:
                return "p7_invalid_request"
            if slot.get("required") is not True:
                return "p7_invalid_slot"
            slot_ref = slot.get("delivery_ref")
            attempt_ref = attempt.get("delivery_ref")
            attempt_id = attempt.get("attempt_id")
            if type(slot_ref) is not str or _DELIVERY_REF_RE.fullmatch(slot_ref) is None:
                return "p7_invalid_slot"
            if type(attempt_ref) is not str or _DELIVERY_REF_RE.fullmatch(attempt_ref) is None:
                return "p7_invalid_request"
            if type(attempt_id) is not str or _ATTEMPT_ID_RE.fullmatch(attempt_id) is None:
                return "p7_invalid_request"
            surface = surfaces[index]
            if slot.get("surface") != surface or attempt.get("surface") != surface:
                return "p7_ack_target_mismatch"
            if slot_ref != attempt_ref:
                return "p7_ack_target_mismatch"
            if slot.get("artifact_ref") != "runtime_artifact_0" or attempt.get("artifact_ref") != "runtime_artifact_0":
                return "p7_invalid_request"
            if surface not in self.allowed_surfaces:
                return "p7_delivery_surface_not_approved"
            try:
                target = _safe_target(attempt.get("target_ref"))
                _idempotency_key(attempt.get("idempotency_key"))
            except ValueError:
                return "p7_invalid_request"
            if target not in self.approved_targets:
                return "p7_delivery_target_not_approved"
        return None

    def cancel(self, *, request: object) -> dict[str, object]:
        try:
            safe_request = _validate_request(request)
            attempts = safe_request["delivery_attempts"]
            keys = [_idempotency_key(attempt["idempotency_key"]) for attempt in attempts]
        except (ValueError, KeyError):
            return _result(status="cancelled", error_code="delivery_cancelled")
        refs = _result_refs(safe_request)
        fingerprint = _fingerprint(safe_request)
        residents = []
        for key in keys:
            resident = self.claim_store.peek(idempotency_key=key)
            if resident is not None and resident.get("fingerprint") != fingerprint:
                return _result(status="rejected", error_code="p7_divergent_replay", **refs)
            residents.append(resident)
        if all(claim is None for claim in residents):
            return _result(status="cancelled", error_code="delivery_cancelled", **refs)
        replay = _resident_terminal_replay(residents, refs, attempts)
        if replay is not None:
            return replay
        return _result(status="watch", error_code="p7_send_unknown", **refs)

    def query(self) -> dict[str, object]:
        return self.claim_store.query()

    def export_state(self) -> dict[str, object]:
        return self.claim_store.query()

    def _admitted(self) -> bool:
        return self.enabled is True and self.approval_token == S5_DOWNSTREAM_DELIVERY_RECONNECT_APPROVAL_TOKEN


def scan_sachima_s5_no_leak(value: object) -> dict[str, object]:
    rendered = _render(value)
    markers = sorted(marker for marker in _S5_NO_LEAK_MARKERS if marker in rendered)
    p7_scan = scan_sachima_p7_no_leak(value)
    markers.extend(marker for marker in p7_scan.get("markers", []) if marker not in markers)
    if C.scan_projection_for_leak(value) is not None and "runtime_history_leak_detected" not in markers:
        markers.append("runtime_history_leak_detected")
    return {"passed": not markers, "raw_marker_hits": len(markers), "markers": sorted(markers)}


def s5_delivery_failure_for_code(code: str) -> ApplicationError:
    safe = code if code in _NON_RETRYABLE_CODES or code in _TRANSIENT_RETRYABLE_CODES else "p7_invalid_request"
    return ApplicationError(safe, type=safe, non_retryable=safe not in _TRANSIENT_RETRYABLE_CODES)


def _activity_output(value: object) -> C.ActivityOutput:
    try:
        C.validate_activity_output(value)
        projection = {
            "artifact_ref": C.step_artifact_ref_projection(value.artifact_ref),
            "evidence_ref": value.evidence_ref,
            "evidence_digest": value.evidence_digest,
            "status": value.status,
        }
        _ensure_clean(projection)
    except Exception as exc:  # noqa: BLE001 - fail closed, never echo raw material
        raise ValueError("invalid_activity_output") from exc
    return value


def _artifact_kind(value: object) -> str:
    return _one_of(value, _ALLOWED_ARTIFACT_KINDS, "invalid_artifact_kind")


def _one_of(value: object, allowed: frozenset[str], code: str) -> str:
    if type(value) is not str or value not in allowed:
        _raise(code)
    return value


def _plain_sequence(value: object) -> tuple[object, ...]:
    if type(value) not in {tuple, list}:
        _raise("p7_invalid_request")
    return tuple(value)


def _surfaces(value: object) -> list[str]:
    items = _plain_sequence(value)
    if not items:
        _raise("p7_delivery_surface_not_approved")
    surfaces = [_one_of(item, _ALLOWED_SURFACES, "p7_delivery_surface_not_approved") for item in items]
    if len(set(surfaces)) != len(surfaces):
        _raise("p7_invalid_request")
    return surfaces


def _safe_target(value: object) -> str:
    if type(value) is not str or _SAFE_LABEL_RE.fullmatch(value) is None:
        _raise("p7_delivery_target_not_approved")
    text = str(value)
    if _has_forbidden_safe_label_token(text):
        _raise("p7_delivery_target_not_approved")
    return text


def _safe_delivery_url_class(value: object) -> str:
    if type(value) is not str or _SAFE_LABEL_RE.fullmatch(value) is None:
        _raise("p7_invalid_policy")
    text = str(value)
    if _has_forbidden_safe_label_token(text):
        _raise("p7_invalid_policy")
    return text


def _has_forbidden_safe_label_token(value: str) -> bool:
    lowered = value.lower()
    tokens = lowered.split("_")
    forbidden_tokens = {"live", "platform", "gateway", "feishu", "lark", "write", "mutate", "approve", "reject"}
    if any(token in forbidden_tokens for token in tokens):
        return True
    return "default_on" in lowered or "public_ingress" in lowered


def _idempotency_key(value: object) -> str:
    if type(value) is not str or _IDEMPOTENCY_KEY_RE.fullmatch(value) is None:
        _raise("p7_invalid_request")
    if C.scan_projection_for_leak({"idempotency_key": value}) is not None:
        _raise("p7_invalid_request")
    return value


def _default_idempotency_key(surface: str, *, index: int = 0) -> str:
    safe = surface.replace("_", "")[:24]
    return f"p7key_s5_{safe}_{index}"


def _validate_request(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _raise("p7_invalid_request")
    required = {
        "type",
        "version",
        "phase",
        "intent_class",
        "target_ref",
        "surfaces",
        "delivery_role_key",
        "artifact_ref",
        "artifact_claim_ref",
        "evidence_ref",
        "evidence_digest",
        "delivery_slots",
        "delivery_attempts",
        "side_effects",
    }
    if set(value) != required:
        _raise("p7_invalid_request")
    if value["type"] != S5_RECONNECT_REQUEST_TYPE or value["version"] != S5_RECONNECT_VERSION:
        _raise("p7_invalid_request")
    if value["phase"] != "s5_downstream_delivery_reconnect":
        _raise("p7_invalid_request")
    intent = _one_of(value["intent_class"], _ALLOWED_INTENTS, "p7_invalid_request")
    target = _safe_target(value["target_ref"])
    surfaces = _surfaces(value["surfaces"])
    role = _one_of(value["delivery_role_key"], _ALLOWED_DELIVERY_ROLES, "p7_invalid_request")
    artifact_claim_ref = _artifact_claim_ref(value["artifact_claim_ref"])
    C._safe_id(value["evidence_ref"])  # noqa: SLF001 - reuse the existing S3/S4 trust-boundary validator.
    C._safe_digest(value["evidence_digest"])  # noqa: SLF001
    slots = _plain_dicts(value["delivery_slots"])
    attempts = _plain_dicts(value["delivery_attempts"])
    if len(slots) != len(attempts) or len(slots) != len(surfaces):
        _raise("p7_invalid_request")
    if value["artifact_ref"] != "runtime_artifact_0":
        _raise("p7_invalid_request")
    if value["side_effects"] != []:
        _raise("p7_invalid_request")
    safe = {
        "type": S5_RECONNECT_REQUEST_TYPE,
        "version": S5_RECONNECT_VERSION,
        "phase": "s5_downstream_delivery_reconnect",
        "intent_class": intent,
        "target_ref": target,
        "surfaces": surfaces,
        "delivery_role_key": role,
        "artifact_ref": "runtime_artifact_0",
        "artifact_claim_ref": artifact_claim_ref,
        "evidence_ref": value["evidence_ref"],
        "evidence_digest": value["evidence_digest"],
        "delivery_slots": copy.deepcopy(slots),
        "delivery_attempts": copy.deepcopy(attempts),
        "side_effects": [],
    }
    _ensure_clean(safe)
    return safe


def _artifact_claim_ref(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _raise("p7_invalid_request")
    cleaned = C._clean_artifact_ref(value)  # noqa: SLF001 - public projection validator is intentionally reused here.
    if cleaned["artifact_kind"] not in _ALLOWED_ARTIFACT_KINDS:
        _raise("p7_invalid_request")
    return cleaned


def _plain_dicts(value: object) -> list[dict[str, object]]:
    if type(value) is not list or not value:
        _raise("p7_invalid_request")
    out: list[dict[str, object]] = []
    for item in value:
        if type(item) is not dict:
            _raise("p7_invalid_request")
        out.append(copy.deepcopy(item))
    return out


def _first_key(request: dict[str, object]) -> str:
    attempts = request["delivery_attempts"]
    if not isinstance(attempts, list) or not attempts or type(attempts[0]) is not dict:
        _raise("p7_invalid_request")
    return _idempotency_key(attempts[0]["idempotency_key"])


def _fingerprint(request: dict[str, object]) -> str:
    material = json.dumps(request, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _resident_terminal_replay(
    claims: list[dict[str, object] | None], refs: dict[str, object], expected_attempts: object
) -> dict[str, object] | None:
    if any(claim is None for claim in claims):
        return None
    if type(expected_attempts) is not list or len(expected_attempts) != len(claims):
        return _result(
            status="watch",
            error_code="p7_send_unknown",
            delivery_ref=refs.get("delivery_ref"),
            surface=refs.get("surface"),
            attempt_id=refs.get("attempt_id"),
            idempotency_key=refs.get("idempotency_key"),
        )
    resident_claims = [claim for claim in claims if claim is not None]
    if any(claim.get("terminal") is not True for claim in resident_claims):
        return None
    safe_projections: list[dict[str, object]] = []
    for claim, expected_attempt in zip(resident_claims, expected_attempts, strict=True):
        projection = claim.get("projection")
        if (
            not isinstance(projection, dict)
            or type(expected_attempt) is not dict
            or not _terminal_projection_is_well_formed(projection, claim=claim, expected_attempt=expected_attempt)
        ):
            return _result(
                status="watch",
                error_code="p7_send_unknown",
                delivery_ref=refs.get("delivery_ref"),
                surface=refs.get("surface"),
                attempt_id=refs.get("attempt_id"),
                idempotency_key=refs.get("idempotency_key"),
            )
        try:
            _ensure_clean(projection)
        except ValueError:
            return _result(
                status="watch",
                error_code="p7_send_unknown",
                delivery_ref=refs.get("delivery_ref"),
                surface=refs.get("surface"),
                attempt_id=refs.get("attempt_id"),
                idempotency_key=refs.get("idempotency_key"),
            )
        safe_projections.append(projection)
    return copy.deepcopy(safe_projections[-1])


def _terminal_projection_is_well_formed(
    projection: dict[str, object], *, claim: dict[str, object], expected_attempt: dict[str, object]
) -> bool:
    if set(projection) != _RESULT_PROJECTION_KEYS:
        return False
    if projection.get("type") != SACHIMA_P7_DELIVERY_RESULT_TYPE:
        return False
    if projection.get("version") != SACHIMA_P7_DELIVERY_ACK_VERSION:
        return False
    status = projection.get("status")
    if type(status) is not str or status not in _RESULT_STATUSES:
        return False
    if projection.get("side_effects") != []:
        return False
    error_code = projection.get("error_code")
    if error_code is not None and (
        type(error_code) is not str
        or error_code == "delivery_cancelled"
        or (error_code not in _NON_RETRYABLE_CODES and error_code not in _TRANSIENT_RETRYABLE_CODES)
    ):
        return False
    for key in ("delivery_ref", "surface", "attempt_id", "idempotency_key", "slot_state"):
        value = projection.get(key)
        if value is not None and type(value) is not str:
            return False
    delivery_ref = projection.get("delivery_ref")
    surface = projection.get("surface")
    attempt_id = projection.get("attempt_id")
    idempotency_key = projection.get("idempotency_key")
    if type(delivery_ref) is not str or _DELIVERY_REF_RE.fullmatch(delivery_ref) is None:
        return False
    if surface not in _ALLOWED_SURFACES:
        return False
    if type(attempt_id) is not str or _ATTEMPT_ID_RE.fullmatch(attempt_id) is None:
        return False
    if type(idempotency_key) is not str or _IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key) is None:
        return False
    if claim.get("idempotency_key") != idempotency_key:
        return False
    if delivery_ref != expected_attempt.get("delivery_ref"):
        return False
    if surface != expected_attempt.get("surface"):
        return False
    if attempt_id != expected_attempt.get("attempt_id"):
        return False
    if idempotency_key != expected_attempt.get("idempotency_key"):
        return False
    ack = projection.get("ack")
    if status == "delivered":
        if projection.get("slot_state") != "acked":
            return False
        if type(ack) is not dict or not _ack_event_is_well_formed(ack, projection):
            return False
        if error_code is not None:
            return False
    elif ack is not None:
        return False
    elif status == "watch":
        if projection.get("slot_state") != "watch" or error_code not in _TRANSIENT_RETRYABLE_CODES:
            return False
    elif status == "failed":
        if projection.get("slot_state") != "failed" or error_code != "p7_send_rejected":
            return False
    elif status == "rejected":
        if projection.get("slot_state") not in {None, "unknown"} or error_code is None:
            return False
    return True


def _ack_event_is_well_formed(ack: dict[str, object], projection: dict[str, object]) -> bool:
    if set(ack) != _ACK_EVENT_KEYS:
        return False
    if ack.get("type") != SACHIMA_P7_ACK_EVENT_TYPE:
        return False
    ack_ref = ack.get("ack_ref")
    if type(ack_ref) is not str or _ACK_REF_RE.fullmatch(ack_ref) is None:
        return False
    if ack.get("delivery_ref") != projection.get("delivery_ref"):
        return False
    if ack.get("surface") != projection.get("surface"):
        return False
    if ack.get("status") != "acknowledged" or ack.get("source") != "send_response":
        return False
    if ack.get("duplicate") is not False:
        return False
    state_version = ack.get("state_version")
    if type(state_version) is not int or state_version < 0:
        return False
    if ack.get("side_effects") != []:
        return False
    return True


def _claim_preexisted_without_terminal(claim: dict[str, object]) -> bool:
    return claim.get("preexisting") is True and claim.get("state") == "claimed" and claim.get("terminal") is False and claim.get("projection") is None


def _result_refs(request: dict[str, object]) -> dict[str, object]:
    attempts = request.get("delivery_attempts")
    if isinstance(attempts, list) and attempts and isinstance(attempts[0], dict):
        return {
            "delivery_ref": attempts[0].get("delivery_ref"),
            "surface": attempts[0].get("surface"),
            "attempt_id": attempts[0].get("attempt_id"),
            "idempotency_key": attempts[0].get("idempotency_key"),
        }
    return {}


def _result(
    *,
    status: str,
    error_code: str | None,
    delivery_ref: object | None = None,
    surface: object | None = None,
    attempt_id: object | None = None,
    idempotency_key: object | None = None,
    ack: dict[str, object] | None = None,
) -> dict[str, object]:
    result = {
        "type": SACHIMA_P7_DELIVERY_RESULT_TYPE,
        "version": "sachima.s5.downstream_delivery_reconnect.result.v0",
        "status": status,
        "delivery_ref": delivery_ref,
        "surface": surface,
        "attempt_id": attempt_id,
        "idempotency_key": idempotency_key,
        "slot_state": "watch" if status == "watch" else None,
        "ack": dict(ack) if ack is not None else None,
        "error_code": error_code,
        "side_effects": [],
    }
    _ensure_clean(result)
    return result


def _ensure_clean(value: object) -> None:
    if scan_sachima_s5_no_leak(value)["passed"] is not True:
        _raise("p7_ack_unsafe_material")


def scan_sachima_s5_no_leak_without_contract(value: object) -> dict[str, object]:
    rendered = _render(value)
    markers = sorted(marker for marker in _S5_NO_LEAK_MARKERS if marker in rendered)
    p7_scan = scan_sachima_p7_no_leak(value)
    markers.extend(marker for marker in p7_scan.get("markers", []) if marker not in markers)
    return {"passed": not markers, "raw_marker_hits": len(markers), "markers": sorted(markers)}


def _render(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=str).lower()
    except Exception:  # noqa: BLE001 - scanner must not echo raw repr exceptions
        return "unrenderable_projection"


def _raise(code: str) -> None:
    raise ValueError(code)


__all__ = [
    "S5_DOWNSTREAM_DELIVERY_RECONNECT_APPROVAL_TOKEN",
    "S5DeliveryReconnectController",
    "S5DurableDeliveryClaimStore",
    "build_s5_delivery_reconnect_request",
    "describe_sachima_s5_downstream_delivery_reconnect_contract",
    "s5_delivery_failure_for_code",
    "scan_sachima_s5_no_leak",
]
