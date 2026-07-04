"""R5 Runtime Spine — bounded controlled-canary request packet + dry-run report.

R5 prepares *controlled product-hardening / canary material* without ever
converting the spine to live, default-on, or real-send behavior. This module owns
two frozen, refs-only value objects and their fail-closed trust-boundary
validators:

* :class:`CanaryRequestPacket` — a single, bounded, **default-off, dry-run-only**
  canary request. It is pinned to exactly one delivery surface (``final_text``)
  and exactly one attempt (``max_attempts == 1``); any attempt to widen the
  surface or the attempt bound fails closed. It carries ``target_ref`` and
  ``receiver_bridge_ref`` only as **opaque safe labels** — never a raw
  platform / chat / user id, a concrete receiver mapping, or a delivery URL — so
  the receiver-bridge boundary stays private and out of core history / logs.
* :class:`CanaryDryRunReport` — an observable, refs-only report that can only ever
  describe a *dry run*. It structurally cannot report a real send: ``send_attempts``
  is pinned to ``0`` and the ``sent`` counter is pinned to ``0``; a forged report
  that claims a send or exposes a receiver mapping fails closed.

Everything here is pure local/offline Python. Importing this module starts no
subprocess, socket, Docker, daemon, Temporal service / Worker / client, Gateway,
Feishu, network call, or delivery surface, launches no OS process or agent
(acpx / npx), and wires none of those surfaces. It reuses the R1
``runtime_spine.events`` safe-id sanitizers and the refs-only ``scan_for_leak``
no-leak scan; forbidden terms appear only as denylist canaries, never as behavior.
It does **not** authorize execution — a real bounded send remains a separate,
explicitly approved gate. See
``docs/architecture/private-hermes-runtime-spine-design.md`` and
``docs/plans/2026-07-04-sachima-r5-controlled-canary-product-hardening.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, NoReturn

from .events import (
    STABLE_CODES,
    SpineError,
    _safe_id,
    safe_task_id,
    scan_for_leak,
)

# --------------------------------------------------------------------------- #
# Stable error-code family (fail-closed; the message is the code, never input)
# --------------------------------------------------------------------------- #
RUNTIME_INVALID_CANARY_PACKET = "runtime_invalid_canary_packet"
RUNTIME_CANARY_NOT_AUTHORIZED = "runtime_canary_not_authorized"

CANARY_STABLE_CODES = frozenset(
    {RUNTIME_INVALID_CANARY_PACKET, RUNTIME_CANARY_NOT_AUTHORIZED}
)

# --------------------------------------------------------------------------- #
# Canonical type / posture constants (static allowlists — no dynamic discovery)
# --------------------------------------------------------------------------- #
CANARY_PACKET_TYPE = "sachima.runtime_spine.canary_request_packet.v1"
CANARY_REPORT_TYPE = "sachima.runtime_spine.canary_dry_run_report.v1"

#: The only authorized delivery surface. Widening past it fails closed.
CANARY_SURFACE = "final_text"

#: The only authorized attempt bound — exactly one. Widening past it fails closed.
CANARY_MAX_ATTEMPTS = 1

#: The only authorized report status. R5 can only describe a ready dry run.
CANARY_DRY_RUN_STATUS = "dry_run_ready"

#: Static, ordered stop-condition allowlist — the kill/rollback triggers that must
#: hold on every bounded canary request. Narrowing this set fails closed.
CANARY_STOP_CONDITIONS: tuple[str, ...] = (
    "approval_missing",
    "duplicate_attempt",
    "leak_detected",
    "receiver_unavailable",
    "unexpected_surface",
)

#: Pinned dry-run counters. A dry run is *ready* (1) and has never sent (0),
#: blocked (0), or rolled back (0). Any deviation fails closed.
CANARY_DRY_RUN_COUNTERS: dict[str, int] = {
    "blocked": 0,
    "dry_run_ready": 1,
    "rolled_back": 0,
    "sent": 0,
}

#: An observed report may carry a stable code only (never raw material). A ready
#: dry run carries none.
_ALLOWED_REPORT_ERROR_CODES = STABLE_CODES | CANARY_STABLE_CODES

#: Opaque safe-label prefix required of the trust-boundary refs (``target_ref`` /
#: ``receiver_bridge_ref``): they must be safe labels, never raw platform ids or a
#: concrete receiver mapping.
_SAFE_LABEL_PREFIX = "safe_"

#: Terms that would make a safe-looking label scope-creeping or platform-specific.
_FORBIDDEN_SAFE_LABEL_PARTS = frozenset(
    {
        "gateway",
        "feishu",
        "lark",
        "live",
        "platform",
        "write",
        "mutate",
        "approve",
        "reject",
        "default_on",
        "public_ingress",
    }
)


# --------------------------------------------------------------------------- #
# Fail-closed helpers (each carries a stable code only — never raw input)
# --------------------------------------------------------------------------- #
def _invalid() -> NoReturn:
    raise SpineError(RUNTIME_INVALID_CANARY_PACKET)


def _not_authorized() -> NoReturn:
    raise SpineError(RUNTIME_CANARY_NOT_AUTHORIZED)


def _safe_canary_ref(value: Any) -> str:
    """A refs-only canary field — a safe id, never raw / platform / path material."""

    return _safe_id(value, code=RUNTIME_INVALID_CANARY_PACKET)


def _safe_boundary_ref(value: Any) -> str:
    """A trust-boundary ref (``target_ref`` / ``receiver_bridge_ref``).

    In addition to the refs-only safe-id allowlist and the no-leak denylist (which
    already reject raw platform / chat / user ids and concrete receiver mappings),
    a boundary ref must be an **opaque safe label** — it must start with the
    ``safe`` marker — so the receiver-bridge mapping stays private and can never be
    a raw id smuggled through a legitimately-shaped identifier.
    """

    ref = _safe_id(value, code=RUNTIME_INVALID_CANARY_PACKET)
    if not ref.startswith(_SAFE_LABEL_PREFIX):
        _invalid()
    if any(part in ref for part in _FORBIDDEN_SAFE_LABEL_PARTS):
        _invalid()
    return ref


def _check_exact_str(value: Any, expected: str) -> None:
    """Exact primitive check before equality — rejects ``str`` subclasses too."""

    if type(value) is not str or value != expected:
        _not_authorized()


def _check_pinned_true(value: Any) -> None:
    if type(value) is not bool or value is not True:
        _not_authorized()


def _check_pinned_false(value: Any) -> None:
    if type(value) is not bool or value is not False:
        _not_authorized()


def _check_pinned_int(value: Any, expected: int) -> None:
    # bool is an int subclass — exclude it explicitly so a flag can't pose as an int.
    if type(value) is not int or value != expected:
        _not_authorized()


def _normalize_stop_conditions(value: Any, *, allow_input: bool) -> tuple[str, ...]:
    """Normalize the stop-condition set to the pinned immutable tuple, fail-closed.

    A mutable ``list`` is accepted only on construction (``allow_input``); a
    validated object must already carry the immutable ``tuple`` form. Malformed
    element types are :data:`RUNTIME_INVALID_CANARY_PACKET`; a well-typed but
    narrowed / reordered set is :data:`RUNTIME_CANARY_NOT_AUTHORIZED` (dropping a
    kill/rollback trigger is a widening of risk).
    """

    if type(value) is list:
        if not allow_input:
            _invalid()
        items: tuple[Any, ...] = tuple(value)
    elif type(value) is tuple:
        items = value
    else:
        _invalid()
    for item in items:
        if type(item) is not str:
            _invalid()
    if items != CANARY_STOP_CONDITIONS:
        _not_authorized()
    return CANARY_STOP_CONDITIONS


def _normalize_counters(value: Any, *, allow_input: bool) -> tuple[tuple[str, int], ...]:
    """Normalize dry-run counters to a canonical, byte-stable tuple-of-pairs.

    A mutable ``Mapping`` is accepted only on construction (``allow_input``); a
    validated object must already carry the immutable tuple-of-pairs form.
    Malformed shapes / types are :data:`RUNTIME_INVALID_CANARY_PACKET`. A dry-run
    report must never report a send, so a non-zero ``sent`` counter — or any
    deviation from the pinned dry-run counters — is
    :data:`RUNTIME_CANARY_NOT_AUTHORIZED`.
    """

    if type(value) is dict:
        if not allow_input:
            _invalid()
        pairs: list[Any] = list(value.items())
    elif type(value) is tuple:
        pairs = list(value)
    else:
        _invalid()

    counters: dict[str, int] = {}
    for pair in pairs:
        if type(pair) is not tuple or len(pair) != 2:
            _invalid()
        key, count = pair
        if type(key) is not str:
            _invalid()
        # bool is an int subclass — exclude it so a flag can't pose as a count.
        if type(count) is not int or count < 0:
            _invalid()
        if key in counters:
            _invalid()
        counters[key] = count

    # A dry run has never sent; fail closed before the full equality check so a
    # forged send surfaces as an authorization violation, not a shape mismatch.
    if counters.get("sent") != 0:
        _not_authorized()
    if counters != CANARY_DRY_RUN_COUNTERS:
        _not_authorized()
    return tuple(sorted(counters.items()))


# --------------------------------------------------------------------------- #
# Bounded canary request packet — default-off, dry-run-only, single surface
# --------------------------------------------------------------------------- #
def _raw_packet_dict(packet: Any) -> dict[str, Any]:
    return {
        "type": packet.type,
        "task_id": packet.task_id,
        "gate_ref": packet.gate_ref,
        "target_ref": packet.target_ref,
        "receiver_bridge_ref": packet.receiver_bridge_ref,
        "artifact_ref": packet.artifact_ref,
        "evidence_ref": packet.evidence_ref,
        "rollback_ref": packet.rollback_ref,
        "surface": packet.surface,
        "max_attempts": packet.max_attempts,
        "default_off": packet.default_off,
        "dry_run_only": packet.dry_run_only,
        "execution_authorized": packet.execution_authorized,
        "receiver_mapping_exposed": packet.receiver_mapping_exposed,
        "stop_conditions": packet.stop_conditions,
    }


def _check_packet_fields(packet: Any, *, normalize: bool = False) -> None:
    """Exact fail-closed validation of a canary packet's fields.

    Construction alone is never grounds for trust: this re-runs the full refs-only
    allowlist, the opaque-safe-label boundary check, and every pinned-posture
    invariant, so a directly constructed or ``object.__new__``-forged packet with
    unsafe refs, a widened surface / attempt bound, or a flipped posture flag
    (``execution_authorized`` / ``default_off`` / ``dry_run_only`` /
    ``receiver_mapping_exposed``) fails closed. A structural / ref / leak problem
    is :data:`RUNTIME_INVALID_CANARY_PACKET`; a widening / authorization problem is
    :data:`RUNTIME_CANARY_NOT_AUTHORIZED`.
    """

    try:
        p_type = packet.type
        task_id = packet.task_id
        gate_ref = packet.gate_ref
        target_ref = packet.target_ref
        receiver_bridge_ref = packet.receiver_bridge_ref
        artifact_ref = packet.artifact_ref
        evidence_ref = packet.evidence_ref
        rollback_ref = packet.rollback_ref
        surface = packet.surface
        max_attempts = packet.max_attempts
        default_off = packet.default_off
        dry_run_only = packet.dry_run_only
        execution_authorized = packet.execution_authorized
        receiver_mapping_exposed = packet.receiver_mapping_exposed
        stop_conditions = packet.stop_conditions
    except AttributeError:
        _invalid()

    if type(p_type) is not str or p_type != CANARY_PACKET_TYPE:
        _invalid()
    safe_task_id(task_id, code=RUNTIME_INVALID_CANARY_PACKET)
    _safe_canary_ref(gate_ref)
    _safe_boundary_ref(target_ref)
    _safe_boundary_ref(receiver_bridge_ref)
    _safe_canary_ref(artifact_ref)
    _safe_canary_ref(evidence_ref)
    _safe_canary_ref(rollback_ref)

    # Pinned posture — widening any of these fails closed as not-authorized.
    _check_exact_str(surface, CANARY_SURFACE)
    _check_pinned_int(max_attempts, CANARY_MAX_ATTEMPTS)
    _check_pinned_true(default_off)
    _check_pinned_true(dry_run_only)
    _check_pinned_false(execution_authorized)
    _check_pinned_false(receiver_mapping_exposed)

    safe_stops = _normalize_stop_conditions(stop_conditions, allow_input=normalize)
    if normalize:
        object.__setattr__(packet, "stop_conditions", safe_stops)

    # Defense in depth: the whole projected shape must pass the refs-only no-leak
    # scan — a raw / platform ref or receiver mapping smuggled into any field fails
    # closed even if it slipped an earlier per-field check.
    if scan_for_leak(_raw_packet_dict(packet)) is not None:
        _invalid()


@dataclass(frozen=True)
class CanaryRequestPacket:
    """A frozen, refs-only, default-off, dry-run-only bounded canary request.

    Exported public surface, so ``__post_init__`` re-runs the full trust-boundary
    validation and normalizes ``stop_conditions`` to the immutable pinned tuple: a
    direct ``CanaryRequestPacket(...)`` carrying raw / platform refs, a widened
    surface / attempt bound, or a flipped posture flag fails closed instead of
    being trusted. Boundary consumers additionally call
    :func:`validate_canary_request_packet` to defend against ``object.__new__``
    forgery and hostile subclasses that skip ``__post_init__``.
    """

    type: str
    task_id: str
    gate_ref: str
    target_ref: str
    receiver_bridge_ref: str
    artifact_ref: str
    evidence_ref: str
    rollback_ref: str
    surface: str
    max_attempts: int
    default_off: bool
    dry_run_only: bool
    execution_authorized: bool
    receiver_mapping_exposed: bool
    stop_conditions: Any

    def __post_init__(self) -> None:
        _check_packet_fields(self, normalize=True)

    def as_dict(self) -> dict[str, Any]:
        validate_canary_request_packet(self)
        return {
            "type": self.type,
            "task_id": self.task_id,
            "gate_ref": self.gate_ref,
            "target_ref": self.target_ref,
            "receiver_bridge_ref": self.receiver_bridge_ref,
            "artifact_ref": self.artifact_ref,
            "evidence_ref": self.evidence_ref,
            "rollback_ref": self.rollback_ref,
            "surface": self.surface,
            "max_attempts": self.max_attempts,
            "default_off": self.default_off,
            "dry_run_only": self.dry_run_only,
            "execution_authorized": self.execution_authorized,
            "receiver_mapping_exposed": self.receiver_mapping_exposed,
            "stop_conditions": list(self.stop_conditions),
        }


def validate_canary_request_packet(packet: Any) -> CanaryRequestPacket:
    """Re-validate a :class:`CanaryRequestPacket` at a trust boundary, unchanged."""

    if type(packet) is not CanaryRequestPacket:
        _invalid()
    _check_packet_fields(packet)
    return packet


def build_bounded_canary_packet(
    *,
    task_id: str,
    gate_ref: str,
    target_ref: str,
    receiver_bridge_ref: str,
    artifact_ref: str,
    evidence_ref: str,
    rollback_ref: str,
    surface: str = CANARY_SURFACE,
    max_attempts: int = CANARY_MAX_ATTEMPTS,
) -> CanaryRequestPacket:
    """Build the one bounded, default-off, dry-run-only canary request packet.

    All refs are validated as safe labels first (``target_ref`` and
    ``receiver_bridge_ref`` additionally as opaque safe labels), then the surface
    and attempt bound are checked against the single authorized values — widening
    either fails closed as :data:`RUNTIME_CANARY_NOT_AUTHORIZED`. The returned
    packet is always pinned to ``default_off`` / ``dry_run_only`` /
    ``execution_authorized = False`` / ``receiver_mapping_exposed = False``; it
    prepares evidence only and authorizes no send.
    """

    safe_task = safe_task_id(task_id, code=RUNTIME_INVALID_CANARY_PACKET)
    safe_gate = _safe_canary_ref(gate_ref)
    safe_target = _safe_boundary_ref(target_ref)
    safe_bridge = _safe_boundary_ref(receiver_bridge_ref)
    safe_artifact = _safe_canary_ref(artifact_ref)
    safe_evidence = _safe_canary_ref(evidence_ref)
    safe_rollback = _safe_canary_ref(rollback_ref)

    # Fail closed on any widening of the single authorized surface / attempt bound
    # before the posture is pinned.
    _check_exact_str(surface, CANARY_SURFACE)
    _check_pinned_int(max_attempts, CANARY_MAX_ATTEMPTS)

    packet = CanaryRequestPacket(
        type=CANARY_PACKET_TYPE,
        task_id=safe_task,
        gate_ref=safe_gate,
        target_ref=safe_target,
        receiver_bridge_ref=safe_bridge,
        artifact_ref=safe_artifact,
        evidence_ref=safe_evidence,
        rollback_ref=safe_rollback,
        surface=CANARY_SURFACE,
        max_attempts=CANARY_MAX_ATTEMPTS,
        default_off=True,
        dry_run_only=True,
        execution_authorized=False,
        receiver_mapping_exposed=False,
        stop_conditions=CANARY_STOP_CONDITIONS,
    )
    return validate_canary_request_packet(packet)


def serialize_canary_request_packet(packet: CanaryRequestPacket) -> bytes:
    """Byte-stable canonical JSON serialization after full validation."""

    validated = validate_canary_request_packet(packet)
    return json.dumps(validated.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


# --------------------------------------------------------------------------- #
# Canary dry-run report — observable refs-only; can never report a real send
# --------------------------------------------------------------------------- #
def _raw_report_dict(report: Any) -> dict[str, Any]:
    return {
        "type": report.type,
        "task_id": report.task_id,
        "report_ref": report.report_ref,
        "target_ref": report.target_ref,
        "surface": report.surface,
        "status": report.status,
        "max_attempts": report.max_attempts,
        "send_attempts": report.send_attempts,
        "receiver_mapping_exposed": report.receiver_mapping_exposed,
        "rollback_ref": report.rollback_ref,
        "evidence_ref": report.evidence_ref,
        "error_code": report.error_code,
        "counters": report.counters,
    }


def _check_report_fields(report: Any, *, normalize: bool = False) -> None:
    """Exact fail-closed validation of a dry-run report's fields.

    A dry-run report is structurally forbidden from describing a real send:
    ``send_attempts`` and the ``sent`` counter are pinned to ``0`` and a forged
    non-zero value fails closed as :data:`RUNTIME_CANARY_NOT_AUTHORIZED`. Structural
    / ref / leak problems are :data:`RUNTIME_INVALID_CANARY_PACKET`.
    """

    try:
        r_type = report.type
        task_id = report.task_id
        report_ref = report.report_ref
        target_ref = report.target_ref
        surface = report.surface
        status = report.status
        max_attempts = report.max_attempts
        send_attempts = report.send_attempts
        receiver_mapping_exposed = report.receiver_mapping_exposed
        rollback_ref = report.rollback_ref
        evidence_ref = report.evidence_ref
        error_code = report.error_code
        counters = report.counters
    except AttributeError:
        _invalid()

    if type(r_type) is not str or r_type != CANARY_REPORT_TYPE:
        _invalid()
    safe_task_id(task_id, code=RUNTIME_INVALID_CANARY_PACKET)
    _safe_canary_ref(report_ref)
    _safe_boundary_ref(target_ref)
    _safe_canary_ref(rollback_ref)
    _safe_canary_ref(evidence_ref)

    _check_exact_str(surface, CANARY_SURFACE)
    _check_exact_str(status, CANARY_DRY_RUN_STATUS)
    _check_pinned_int(max_attempts, CANARY_MAX_ATTEMPTS)
    # The core no-send invariant: a dry run has attempted no send.
    _check_pinned_int(send_attempts, 0)
    _check_pinned_false(receiver_mapping_exposed)

    if error_code is not None and (
        type(error_code) is not str or error_code not in _ALLOWED_REPORT_ERROR_CODES
    ):
        _invalid()

    safe_counters = _normalize_counters(counters, allow_input=normalize)
    if normalize:
        object.__setattr__(report, "counters", safe_counters)

    if scan_for_leak(_raw_report_dict(report)) is not None:
        _invalid()


@dataclass(frozen=True)
class CanaryDryRunReport:
    """A frozen, refs-only, observable dry-run report that never reports a send.

    Exported public surface, so ``__post_init__`` re-runs the full trust-boundary
    validation and normalizes ``counters`` to the immutable pinned tuple-of-pairs:
    a direct ``CanaryDryRunReport(...)`` claiming a send, exposing a receiver
    mapping, or carrying raw material fails closed. Boundary consumers additionally
    call :func:`validate_canary_dry_run_report` to defend against ``object.__new__``
    forgery and hostile subclasses that skip ``__post_init__``.
    """

    type: str
    task_id: str
    report_ref: str
    target_ref: str
    surface: str
    status: str
    max_attempts: int
    send_attempts: int
    receiver_mapping_exposed: bool
    rollback_ref: str
    evidence_ref: str
    error_code: str | None
    counters: Any

    def __post_init__(self) -> None:
        _check_report_fields(self, normalize=True)

    def as_dict(self) -> dict[str, Any]:
        validate_canary_dry_run_report(self)
        return {
            "type": self.type,
            "task_id": self.task_id,
            "report_ref": self.report_ref,
            "target_ref": self.target_ref,
            "surface": self.surface,
            "status": self.status,
            "max_attempts": self.max_attempts,
            "send_attempts": self.send_attempts,
            "receiver_mapping_exposed": self.receiver_mapping_exposed,
            "rollback_ref": self.rollback_ref,
            "evidence_ref": self.evidence_ref,
            "error_code": self.error_code,
            "counters": {key: value for key, value in self.counters},
        }


def validate_canary_dry_run_report(report: Any) -> CanaryDryRunReport:
    """Re-validate a :class:`CanaryDryRunReport` at a trust boundary, unchanged."""

    if type(report) is not CanaryDryRunReport:
        _invalid()
    _check_report_fields(report)
    return report


def build_canary_dry_run_report(
    packet: CanaryRequestPacket, *, report_ref: str
) -> CanaryDryRunReport:
    """Build the observable, refs-only dry-run report for a validated packet.

    The report echoes only safe labels from the (re-validated) packet — the same
    ``target_ref`` opaque label, the single surface, the attempt bound, the
    rollback / evidence refs — and pins ``send_attempts`` and the ``sent`` counter
    to ``0``. It reports a *ready dry run*; it never reports an actual send.
    """

    valid = validate_canary_request_packet(packet)
    safe_report_ref = _safe_canary_ref(report_ref)
    report = CanaryDryRunReport(
        type=CANARY_REPORT_TYPE,
        task_id=valid.task_id,
        report_ref=safe_report_ref,
        target_ref=valid.target_ref,
        surface=valid.surface,
        status=CANARY_DRY_RUN_STATUS,
        max_attempts=valid.max_attempts,
        send_attempts=0,
        receiver_mapping_exposed=False,
        rollback_ref=valid.rollback_ref,
        evidence_ref=valid.evidence_ref,
        error_code=None,
        counters=dict(CANARY_DRY_RUN_COUNTERS),
    )
    return validate_canary_dry_run_report(report)


def serialize_canary_dry_run_report(report: CanaryDryRunReport) -> bytes:
    """Byte-stable canonical JSON serialization after full validation."""

    validated = validate_canary_dry_run_report(report)
    return json.dumps(validated.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
