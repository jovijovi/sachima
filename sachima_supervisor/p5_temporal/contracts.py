"""P5 Temporal PR B — sanitized, schema-versioned history trust boundary.

This module is the **single trust boundary into Temporal history** for the PR B
runtime slice. Everything that crosses into a workflow start payload, an update
payload, an activity I/O, or a query snapshot is an exact, frozen, sanitized
dataclass / projection validated here. Validators reject hostile subclasses,
extra/missing fields, malformed refs, non-``sha256`` digests, and every denylist
marker (raw prompt/context/output, raw acpx/agent stdout, tracebacks, PIDs/host
names, platform ids / card JSON / message ids, media bytes / private paths,
credentials / secrets / connection strings / signed URLs, delivery payloads).

It is pure, local/offline Python — importing it starts no Temporal service,
Worker, subprocess, socket, or network call, and it never imports WP4 / Gateway /
Feishu / platform surfaces. Activity / workflow modules consume **only** these
types so non-determinism and raw material can never enter workflow code.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# --------------------------------------------------------------------------- #
# Schema / mode / queue pins
# --------------------------------------------------------------------------- #
SCHEMA_VERSION = 1
MODE_CONTROLLED_DETERMINISTIC = "controlled_deterministic"
PHASE_SLICE_1 = "p5_temporal_slice_1"
P5_TEMPORAL_TASK_QUEUE = "sachima-p5-temporal-slice-1"

#: Slice 1 update set is pinned to exactly ``{resume, request_cancel}``.
#: ``delivery`` / ``approval`` / ``rejection`` are deferred — they imply P6 /
#: Gateway / real delivery, all non-approved for this slice.
SLICE_1_UPDATE_EVENT_TYPES = ("resume", "request_cancel")

SNAPSHOT_TYPE = "sachima.supervisor.p5_temporal_snapshot.v1"
HISTORY_TYPE = "sachima.supervisor.p5_temporal_history.v1"
ACTIVITY_INPUT_TYPE = "sachima.supervisor.p5_temporal_activity_input.v1"
ACTIVITY_OUTPUT_TYPE = "sachima.supervisor.p5_temporal_activity_output.v1"

# --------------------------------------------------------------------------- #
# Stable code family (FR1 / FR4 / FR7 + WP3b WATCH)
# --------------------------------------------------------------------------- #
RUNTIME_DISABLED = "runtime_disabled"
RUNTIME_APPROVAL_MISMATCH = "runtime_approval_mismatch"
RUNTIME_PRECONDITION_UNMET = "runtime_precondition_unmet"
RUNTIME_IDEMPOTENCY_CONFLICT = "runtime_idempotency_conflict"
INVALID_START_PAYLOAD = "invalid_start_payload"
RUNTIME_HISTORY_LEAK_DETECTED = "runtime_history_leak_detected"
RUNTIME_UNSAFE_MATERIAL = "runtime_unsafe_material"
RUNTIME_CANCEL_SCOPE_UNSUPPORTED = "runtime_cancel_scope_unsupported"
RUNTIME_NOT_FOUND = "runtime_not_found"
RUNTIME_ERROR = "runtime_error"
ACTIVE_RUN_CANCELLATION_WATCH = "active_run_cancellation_watch"
CANCEL_AMBIGUOUS = "cancel_ambiguous"

STABLE_CODES = frozenset(
    {
        RUNTIME_DISABLED,
        RUNTIME_APPROVAL_MISMATCH,
        RUNTIME_PRECONDITION_UNMET,
        RUNTIME_IDEMPOTENCY_CONFLICT,
        INVALID_START_PAYLOAD,
        RUNTIME_HISTORY_LEAK_DETECTED,
        RUNTIME_UNSAFE_MATERIAL,
        RUNTIME_CANCEL_SCOPE_UNSUPPORTED,
        RUNTIME_NOT_FOUND,
        RUNTIME_ERROR,
        ACTIVE_RUN_CANCELLATION_WATCH,
        CANCEL_AMBIGUOUS,
    }
)

# --------------------------------------------------------------------------- #
# Regex / marker families
# --------------------------------------------------------------------------- #
_SAFE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_KIND_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

#: Denylist markers (FR2). Matched case-insensitively against the lowered string
#: rendering of any field / projection. Kept deliberately specific so legitimate
#: claim-check refs and sha256 digests never false-positive.
FORBIDDEN_MARKERS: tuple[str, ...] = (
    "raw_prompt",
    "raw_context",
    "raw_output",
    "raw_command",
    "raw_capture",
    "raw_snapshot",
    "raw_response",
    "prompt_body",
    "model_output",
    "agent_stdout",
    "stdout",
    "stderr",
    "tool_output",
    "traceback",
    "card_json",
    "media_path",
    "media_bytes",
    "media:",
    "signed_url",
    "presigned",
    "bearer ",
    "bearer_",
    "api_key",
    "apikey",
    "password",
    "secret",
    "credential",
    "private_key",
    "connection_string",
    "post" + "gres://",
    "postgresql" + "://",
    "mysql" + "://",
    "redis" + "://",
    "amqp" + "://",
    "mongodb" + "://",
    "x-amz-signature",
    "sk-",
    "xox",
    "ghp_",
    "akia",
    "-----begin",
    "/home/",
    "/users/",
    "/tmp/",
    "/var/",
    "chat_id",
    "user_id",
    "message_id",
    "platform_id",
    "platform_payload",
    "delivery_payload",
    "delivery_ack_payload",
    "im_body",
    "om_",
    "oc_",
    "ou_",
    "feishu",
    "lark",
    "telegram",
    "private",
)

#: Roles that imply write capability are out of Slice 1 (read-only roles only).
_FORBIDDEN_ROLE_MARKERS: tuple[str, ...] = ("write", "deliver", "approve", "reject", "mutate")


class ContractError(Exception):
    """Fail-closed contract violation carrying a stable code only.

    The message is the stable code itself — never raw input, exception text, or a
    traceback — so a rejected payload can be surfaced without leaking material.
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


# --------------------------------------------------------------------------- #
# Frozen sanitized dataclasses (Temporal-converter-safe: plain str/int/tuple)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ClaimCheckRef:
    """A claim-check reference + sha256 digest only — never an inline payload."""

    ref: str
    digest: str
    kind: str
    byte_count: int


@dataclass(frozen=True)
class StartRequest:
    """Sanitized, schema-versioned workflow start payload.

    The single object the workflow ``run`` method decodes. Contains only opaque
    safe refs, role keys, claim-check refs + digests, counts/indices, and
    sanitized lease fields.
    """

    schema_version: int
    mode: str
    phase: str
    run_ref: str
    workflow_ref: str
    step_ref: str
    attempt_index: int
    role_keys: tuple[str, ...]
    input_claim_refs: tuple[ClaimCheckRef, ...]
    idempotency_material: str
    lease_id: str | None = None
    lease_epoch: int = 0


@dataclass(frozen=True)
class UpdatePayload:
    """Sanitized update payload — pinned Slice 1 event types only."""

    event_key: str
    event_type: str
    ref: str | None = None


@dataclass(frozen=True)
class ActivityInput:
    """Controlled-deterministic activity input — claim-check refs only."""

    schema_version: int
    run_ref: str
    step_ref: str
    attempt_index: int
    role_key: str
    input_claim_refs: tuple[ClaimCheckRef, ...] = ()


@dataclass(frozen=True)
class StepArtifactRef:
    """Sanitized WP4-shaped claim-check artifact ref (6 keys, refs + digest only)."""

    artifact_id: str
    producer_step_id: str
    content_digest: str
    artifact_kind: str
    byte_count: int
    created_at_ref: str


@dataclass(frozen=True)
class ActivityOutput:
    """Controlled-deterministic activity output — one claim-check artifact ref."""

    schema_version: int
    status: str
    artifact_ref: StepArtifactRef
    evidence_ref: str
    evidence_digest: str


# --------------------------------------------------------------------------- #
# Allowlist of snapshot / history projection keys (SCAN 1)
# --------------------------------------------------------------------------- #
ALLOWED_SNAPSHOT_KEYS = frozenset(
    {
        "type",
        "schema_version",
        "mode",
        "phase",
        "run_ref",
        "workflow_ref",
        "step_ref",
        "attempt_index",
        "idempotency_material",
        "state",
        "snapshot_version",
        "artifact_refs",
        "role_keys",
        "input_claim_refs",
        "applied_event_count",
        "resume_count",
        "active_run_watch",
        "recovery_marker",
        "error_code",
        "lease_id",
        "lease_epoch",
        "counts",
    }
)

ALLOWED_ARTIFACT_REF_KEYS = (
    "artifact_id",
    "producer_step_id",
    "content_digest",
    "artifact_kind",
    "byte_count",
    "created_at_ref",
)

_OUTPUT_KIND_BY_STEP: dict[str, str] = {
    "architect": "architecture_packet",
    "programmer_candidate": "implementation_candidate_analysis",
    "reviewer": "blocker_review",
}


# --------------------------------------------------------------------------- #
# Low-level sanitizers
# --------------------------------------------------------------------------- #
def _has_forbidden_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in FORBIDDEN_MARKERS)


def _safe_id(value: Any, *, code: str = INVALID_START_PAYLOAD) -> str:
    if type(value) is not str or _SAFE_ID_RE.fullmatch(value) is None:
        raise ContractError(code)
    if _has_forbidden_marker(value):
        raise ContractError(code)
    return value


def _safe_kind(value: Any, *, code: str = INVALID_START_PAYLOAD) -> str:
    if type(value) is not str or _SAFE_KIND_RE.fullmatch(value) is None:
        raise ContractError(code)
    if _has_forbidden_marker(value):
        raise ContractError(code)
    return value


def _safe_digest(value: Any, *, code: str = INVALID_START_PAYLOAD) -> str:
    if type(value) is not str or _SHA256_DIGEST_RE.fullmatch(value) is None:
        raise ContractError(code)
    return value


def _safe_role_key(value: Any, *, code: str = INVALID_START_PAYLOAD) -> str:
    role = _safe_id(value, code=code)
    lowered = role.lower()
    if any(marker in lowered for marker in _FORBIDDEN_ROLE_MARKERS):
        raise ContractError(code)
    return role


def _safe_byte_count(value: Any, *, code: str = INVALID_START_PAYLOAD) -> int:
    if type(value) is not int or value < 0 or value > 64 * 1024 * 1024:
        raise ContractError(code)
    return value


def _safe_attempt_index(value: Any, *, code: str = INVALID_START_PAYLOAD) -> int:
    if type(value) is not int or value < 1 or value > 1_000_000:
        raise ContractError(code)
    return value


def _digest_hex(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _digest_ref(payload: Any) -> str:
    return "sha256:" + _digest_hex(payload)


def canonical_json_bytes(value: Any) -> bytes:
    """Canonical sanitized JSON bytes for SCAN 1 serialized projections."""

    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


# --------------------------------------------------------------------------- #
# Claim-check ref builders / validators
# --------------------------------------------------------------------------- #
def build_claim_check_ref(value: Any, *, code: str = INVALID_START_PAYLOAD) -> ClaimCheckRef:
    if type(value) is ClaimCheckRef:
        validate_claim_check_ref(value, code=code)
        return value
    if not isinstance(value, Mapping):
        raise ContractError(code)
    keys = set(value)
    if keys != {"ref", "digest", "kind", "byte_count"}:
        raise ContractError(code)
    ref = ClaimCheckRef(
        ref=_safe_id(value["ref"], code=code),
        digest=_safe_digest(value["digest"], code=code),
        kind=_safe_kind(value["kind"], code=code),
        byte_count=_safe_byte_count(value["byte_count"], code=code),
    )
    validate_claim_check_ref(ref, code=code)
    return ref


def validate_claim_check_ref(ref: Any, *, code: str = INVALID_START_PAYLOAD) -> None:
    if type(ref) is not ClaimCheckRef:
        raise ContractError(code)
    _safe_id(ref.ref, code=code)
    _safe_digest(ref.digest, code=code)
    _safe_kind(ref.kind, code=code)
    _safe_byte_count(ref.byte_count, code=code)


def artifact_ref_to_claim_check(projection: Mapping[str, Any], *, code: str = INVALID_START_PAYLOAD) -> ClaimCheckRef:
    """Project a WP4 artifact-ref mapping down to a sanitized claim-check ref."""

    if not isinstance(projection, Mapping):
        raise ContractError(code)
    artifact_id = projection.get("artifact_id")
    digest = projection.get("content_digest")
    kind = projection.get("artifact_kind")
    byte_count = projection.get("byte_count")
    return ClaimCheckRef(
        ref=_safe_id(_normalize_ref(artifact_id, code=code), code=code),
        digest=_safe_digest(digest, code=code),
        kind=_safe_kind(_normalize_ref(kind, code=code), code=code),
        byte_count=_safe_byte_count(byte_count, code=code),
    )


#: A legitimate WP4 ref is a dotted / dashed / colon identifier (e.g.
#: ``run.alpha-01``, ``sachima.codex.primary_reviewer``, ``p5:step-1``). Anything
#: else — URL / path / query / connection-string punctuation (``/`` ``\`` ``?``
#: ``&`` ``=`` ``@`` ``%`` whitespace …) — is **never** a ref: normalization would
#: collapse it into a safe-looking id and smuggle a connection string, private
#: path, signed URL, or credential into Temporal history.
_RAW_REF_CHARSET_RE = re.compile(r"^[A-Za-z0-9._:\-]*$")


def _reject_unsafe_raw_ref(value: str, *, code: str) -> None:
    """Fail closed on empty / raw / private / secret ref material **before**
    normalization.

    Three independent teeth on the *raw* string: (0) empty / whitespace-only
    material and the stringified-``None`` sentinels (``none`` / ``None``) are never
    identity material — they must fail closed instead of collapsing into a
    safe-looking ``ref_`` / ``none`` id; (1) only dotted/dashed/colon identifier
    characters are allowed, so any URL/path/query/connection-string punctuation is
    rejected before it can be collapsed away; (2) the forbidden marker denylist is
    applied to the raw value, catching connection-string prefixes, signed-URL
    signatures, and platform ids that normalization would otherwise collapse away.
    """

    stripped = value.strip()
    if not stripped or stripped.lower() == "none":
        raise ContractError(code)
    if _RAW_REF_CHARSET_RE.fullmatch(value) is None:
        raise ContractError(code)
    if _has_forbidden_marker(value):
        raise ContractError(code)


def _normalize_ref(value: Any, *, code: str = INVALID_START_PAYLOAD) -> str:
    """Lowercase + collapse ``.``/``-``/``:`` to ``_`` so WP4 dotted ids fit the
    strict ``[a-z0-9_]`` history charset.

    Raw/private/secret material is rejected on the original string **before**
    normalization (``_reject_unsafe_raw_ref``); the normalized form is then
    re-validated by ``_safe_id`` downstream (defense in depth).
    """

    if type(value) is not str:
        raise ContractError(code)
    _reject_unsafe_raw_ref(value, code=code)
    lowered = value.lower()
    collapsed = re.sub(r"[.:\-]+", "_", lowered)
    collapsed = re.sub(r"[^a-z0-9_]+", "_", collapsed).strip("_")
    if not collapsed:
        # All-punctuation / collapse-to-nothing is never a safe id — fail closed
        # instead of fabricating a bare ``ref_`` placeholder from empty material.
        raise ContractError(code)
    if not collapsed[0].isalpha():
        collapsed = "ref_" + collapsed
    return collapsed[:128]


def safe_ref(value: Any, *, code: str = INVALID_START_PAYLOAD) -> str:
    """Normalize a (possibly dotted/dashed) WP4 ref to a safe history id.

    Empty / whitespace-only / stringified-``None`` and raw/private/secret material
    all fail closed **before** normalization (so missing identity material can never
    collapse into a bare ``ref_`` and a connection string / private path / signed
    URL can never be collapsed into a safe-looking id); the normalized form is then
    re-validated by the strict ``[a-z0-9_]`` + forbidden-marker ``_safe_id`` check.
    """

    return _safe_id(_normalize_ref(value, code=code), code=code)


def workflow_id_from_refs(run_ref: Any, step_ref: Any) -> str:
    """Deterministic workflow id directly from sanitized refs (no full request)."""

    seed = {
        "schema_version": SCHEMA_VERSION,
        "mode": MODE_CONTROLLED_DETERMINISTIC,
        "run_ref": _safe_id(run_ref),
        "step_ref": _safe_id(step_ref),
    }
    return "p5wf_" + _digest_hex(seed)[:48]


# --------------------------------------------------------------------------- #
# StartRequest builder / validator
# --------------------------------------------------------------------------- #
def build_start_request(
    *,
    run_ref: Any,
    workflow_ref: Any,
    step_ref: Any,
    attempt_index: Any,
    role_keys: Any,
    input_claim_refs: Any,
    idempotency_material: Any,
    phase: Any = PHASE_SLICE_1,
    lease_id: Any = None,
    lease_epoch: Any = 0,
) -> StartRequest:
    """Build the sanitized, schema-versioned ``StartRequest`` or fail closed."""

    if not isinstance(role_keys, (list, tuple)) or len(role_keys) == 0:
        raise ContractError(INVALID_START_PAYLOAD)
    safe_roles = tuple(_safe_role_key(role) for role in role_keys)

    if not isinstance(input_claim_refs, (list, tuple)):
        raise ContractError(INVALID_START_PAYLOAD)
    safe_refs = tuple(build_claim_check_ref(ref) for ref in input_claim_refs)

    if lease_id is not None:
        lease_id = _safe_id(lease_id)
    if type(lease_epoch) is not int or lease_epoch < 0:
        raise ContractError(INVALID_START_PAYLOAD)

    request = StartRequest(
        schema_version=SCHEMA_VERSION,
        mode=MODE_CONTROLLED_DETERMINISTIC,
        phase=_safe_id(phase),
        run_ref=_safe_id(run_ref),
        workflow_ref=_safe_id(workflow_ref),
        step_ref=_safe_id(step_ref),
        attempt_index=_safe_attempt_index(attempt_index),
        role_keys=safe_roles,
        input_claim_refs=safe_refs,
        idempotency_material=_safe_id(idempotency_material),
        lease_id=lease_id,
        lease_epoch=lease_epoch,
    )
    validate_start_request(request)
    return request


def validate_start_request(request: Any) -> None:
    """Exact validation — rejects hostile subclasses and any denylist material."""

    if type(request) is not StartRequest:
        raise ContractError(INVALID_START_PAYLOAD)
    if request.schema_version != SCHEMA_VERSION:
        raise ContractError(INVALID_START_PAYLOAD)
    if request.mode != MODE_CONTROLLED_DETERMINISTIC:
        raise ContractError(INVALID_START_PAYLOAD)
    _safe_id(request.phase)
    _safe_id(request.run_ref)
    _safe_id(request.workflow_ref)
    _safe_id(request.step_ref)
    _safe_attempt_index(request.attempt_index)
    if not isinstance(request.role_keys, tuple) or not request.role_keys:
        raise ContractError(INVALID_START_PAYLOAD)
    for role in request.role_keys:
        _safe_role_key(role)
    if not isinstance(request.input_claim_refs, tuple):
        raise ContractError(INVALID_START_PAYLOAD)
    for ref in request.input_claim_refs:
        validate_claim_check_ref(ref)
    _safe_id(request.idempotency_material)
    if request.lease_id is not None:
        _safe_id(request.lease_id)
    if type(request.lease_epoch) is not int or request.lease_epoch < 0:
        raise ContractError(INVALID_START_PAYLOAD)


# --------------------------------------------------------------------------- #
# Update payload builder / validator
# --------------------------------------------------------------------------- #
def build_update_payload(*, event_key: Any, event_type: Any, ref: Any = None) -> UpdatePayload:
    if type(event_type) is not str or event_type not in SLICE_1_UPDATE_EVENT_TYPES:
        raise ContractError(INVALID_START_PAYLOAD)
    safe_ref = None if ref is None else _safe_id(ref)
    payload = UpdatePayload(event_key=_safe_id(event_key), event_type=event_type, ref=safe_ref)
    validate_update_payload(payload)
    return payload


def validate_update_payload(payload: Any) -> None:
    if type(payload) is not UpdatePayload:
        raise ContractError(INVALID_START_PAYLOAD)
    _safe_id(payload.event_key)
    if payload.event_type not in SLICE_1_UPDATE_EVENT_TYPES:
        raise ContractError(INVALID_START_PAYLOAD)
    if payload.ref is not None:
        _safe_id(payload.ref)


# --------------------------------------------------------------------------- #
# Activity I/O builders / validators
# --------------------------------------------------------------------------- #
def build_activity_input(request: StartRequest) -> ActivityInput:
    validate_start_request(request)
    return ActivityInput(
        schema_version=SCHEMA_VERSION,
        run_ref=request.run_ref,
        step_ref=request.step_ref,
        attempt_index=request.attempt_index,
        role_key=request.role_keys[0],
        input_claim_refs=request.input_claim_refs,
    )


def validate_activity_input(value: Any) -> None:
    if type(value) is not ActivityInput:
        raise ContractError(INVALID_START_PAYLOAD)
    if value.schema_version != SCHEMA_VERSION:
        raise ContractError(INVALID_START_PAYLOAD)
    _safe_id(value.run_ref)
    _safe_id(value.step_ref)
    _safe_attempt_index(value.attempt_index)
    _safe_role_key(value.role_key)
    if not isinstance(value.input_claim_refs, tuple):
        raise ContractError(INVALID_START_PAYLOAD)
    for ref in value.input_claim_refs:
        validate_claim_check_ref(ref)


def validate_step_artifact_ref(value: Any, *, code: str = INVALID_START_PAYLOAD) -> None:
    if type(value) is not StepArtifactRef:
        raise ContractError(code)
    _safe_id(value.artifact_id, code=code)
    _safe_id(value.producer_step_id, code=code)
    _safe_digest(value.content_digest, code=code)
    _safe_kind(value.artifact_kind, code=code)
    _safe_byte_count(value.byte_count, code=code)
    _safe_id(value.created_at_ref, code=code)


def validate_activity_output(value: Any) -> None:
    if type(value) is not ActivityOutput:
        raise ContractError(INVALID_START_PAYLOAD)
    if value.schema_version != SCHEMA_VERSION:
        raise ContractError(INVALID_START_PAYLOAD)
    if value.status != "completed":
        raise ContractError(INVALID_START_PAYLOAD)
    validate_step_artifact_ref(value.artifact_ref)
    _safe_id(value.evidence_ref)
    _safe_digest(value.evidence_digest)


# --------------------------------------------------------------------------- #
# Deterministic ids / artifact projection (controlled-deterministic Slice 1)
# --------------------------------------------------------------------------- #
def deterministic_workflow_id(request: StartRequest) -> str:
    """Deterministic workflow id keyed on (run_ref, step_ref) + schema/mode.

    Idempotency divergence does **not** change the id, so a step maps to exactly
    one durable workflow; divergence is detected by payload reconciliation.
    """

    validate_start_request(request)
    return workflow_id_from_refs(request.run_ref, request.step_ref)


def safe_artifact_kind(step_ref: str) -> str:
    known = _OUTPUT_KIND_BY_STEP.get(step_ref)
    if known is not None:
        return known
    return _safe_kind(_normalize_ref(f"{step_ref}_artifact"))


def build_step_artifact_ref(run_ref: str, step_ref: str, attempt_index: int, role_key: str) -> StepArtifactRef:
    """Controlled-deterministic claim-check artifact ref from raw step fields.

    Shared by the workflow's step activity and the executor outcome projection so
    a real hermetic round-trip and the in-process oracle produce the same artifact.
    """

    kind = safe_artifact_kind(step_ref)
    body = {
        "run_ref": run_ref,
        "step_ref": step_ref,
        "attempt_index": attempt_index,
        "role_key": role_key,
        "kind": kind,
        "mode": MODE_CONTROLLED_DETERMINISTIC,
    }
    return StepArtifactRef(
        artifact_id=_safe_id(f"p5_artifact_{run_ref}_{step_ref}_{attempt_index}"[:128]),
        producer_step_id=step_ref,
        content_digest=_digest_ref(body),
        artifact_kind=kind,
        byte_count=len(json.dumps(body, sort_keys=True).encode("utf-8")),
        created_at_ref="created_at_ref_p5_temporal_0001",
    )


def step_artifact_ref_projection(artifact: StepArtifactRef) -> dict[str, Any]:
    if type(artifact) is not StepArtifactRef:
        raise ContractError(INVALID_START_PAYLOAD)
    return {
        "artifact_id": artifact.artifact_id,
        "producer_step_id": artifact.producer_step_id,
        "content_digest": artifact.content_digest,
        "artifact_kind": artifact.artifact_kind,
        "byte_count": artifact.byte_count,
        "created_at_ref": artifact.created_at_ref,
    }


def deterministic_artifact_ref(request: StartRequest) -> dict[str, Any]:
    """Controlled-deterministic claim-check artifact ref projection (6 keys)."""

    validate_start_request(request)
    artifact = build_step_artifact_ref(
        request.run_ref, request.step_ref, request.attempt_index, request.role_keys[0]
    )
    return step_artifact_ref_projection(artifact)


def deterministic_evidence(request: StartRequest) -> tuple[str, str]:
    return deterministic_evidence_fields(request.run_ref, request.step_ref, request.attempt_index)


def deterministic_evidence_fields(run_ref: str, step_ref: str, attempt_index: int) -> tuple[str, str]:
    base = {"run_ref": run_ref, "step_ref": step_ref, "mode": MODE_CONTROLLED_DETERMINISTIC}
    evidence_ref = f"p5_evidence_{_digest_hex(base)[:16]}"
    evidence_digest = _digest_ref({"evidence": base, "attempt_index": attempt_index})
    return _safe_id(evidence_ref), evidence_digest


def build_activity_output(value: ActivityInput) -> ActivityOutput:
    """Controlled-deterministic step body — produce one claim-check artifact ref.

    No real ``acpx``/agent, no subprocess, no network, no raw stdout/exception
    text. Pure function of the sanitized activity input.
    """

    validate_activity_input(value)
    artifact = build_step_artifact_ref(value.run_ref, value.step_ref, value.attempt_index, value.role_key)
    evidence_ref, evidence_digest = deterministic_evidence_fields(
        value.run_ref, value.step_ref, value.attempt_index
    )
    output = ActivityOutput(
        schema_version=SCHEMA_VERSION,
        status="completed",
        artifact_ref=artifact,
        evidence_ref=evidence_ref,
        evidence_digest=evidence_digest,
    )
    validate_activity_output(output)
    return output


# --------------------------------------------------------------------------- #
# Query snapshot projection (allowlist only)
# --------------------------------------------------------------------------- #
def build_query_snapshot(
    *,
    start_request: StartRequest,
    state: str,
    snapshot_version: int,
    artifact_refs: tuple[Mapping[str, Any], ...] = (),
    active_run_watch: bool = False,
    recovery_marker: str | None = None,
    error_code: str | None = None,
    applied_event_count: int = 0,
    resume_count: int = 0,
) -> dict[str, Any]:
    """Build a sanitized, allowlist-only query snapshot."""

    validate_start_request(start_request)
    safe_artifacts = [_clean_artifact_ref(ref) for ref in artifact_refs]
    snapshot: dict[str, Any] = {
        "type": SNAPSHOT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "mode": start_request.mode,
        "phase": start_request.phase,
        "run_ref": start_request.run_ref,
        "workflow_ref": start_request.workflow_ref,
        "step_ref": start_request.step_ref,
        "attempt_index": start_request.attempt_index,
        "idempotency_material": start_request.idempotency_material,
        "state": _safe_id(state),
        "snapshot_version": int(snapshot_version),
        "artifact_refs": safe_artifacts,
        "role_keys": list(start_request.role_keys),
        "input_claim_refs": [
            {"ref": ref.ref, "digest": ref.digest, "kind": ref.kind, "byte_count": ref.byte_count}
            for ref in start_request.input_claim_refs
        ],
        "applied_event_count": int(applied_event_count),
        "resume_count": int(resume_count),
        "active_run_watch": bool(active_run_watch),
        "counts": {
            "input_claim_refs": len(start_request.input_claim_refs),
            "artifact_refs": len(safe_artifacts),
        },
    }
    if start_request.lease_id is not None:
        snapshot["lease_id"] = start_request.lease_id
        snapshot["lease_epoch"] = start_request.lease_epoch
    if recovery_marker is not None:
        snapshot["recovery_marker"] = _safe_id(recovery_marker)
    if error_code is not None:
        if error_code not in STABLE_CODES:
            raise ContractError(INVALID_START_PAYLOAD)
        snapshot["error_code"] = error_code
    leak = scan_projection_for_leak(snapshot)
    if leak is not None:
        raise ContractError(RUNTIME_HISTORY_LEAK_DETECTED)
    if not set(snapshot).issubset(ALLOWED_SNAPSHOT_KEYS):
        raise ContractError(INVALID_START_PAYLOAD)
    return snapshot


def _clean_artifact_ref(projection: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(projection, Mapping):
        raise ContractError(INVALID_START_PAYLOAD)
    if set(projection) != set(ALLOWED_ARTIFACT_REF_KEYS):
        raise ContractError(INVALID_START_PAYLOAD)
    cleaned = {
        "artifact_id": _safe_id(_normalize_ref(projection["artifact_id"])),
        "producer_step_id": _safe_id(_normalize_ref(projection["producer_step_id"])),
        "content_digest": _safe_digest(projection["content_digest"]),
        "artifact_kind": _safe_kind(_normalize_ref(projection["artifact_kind"])),
        "byte_count": _safe_byte_count(projection["byte_count"]),
        "created_at_ref": _safe_id(_normalize_ref(projection["created_at_ref"])),
    }
    return cleaned


# --------------------------------------------------------------------------- #
# No-leak SCAN helpers (FR7 / SCAN 1)
# --------------------------------------------------------------------------- #
def _walk_strings(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            out.append(str(key))
            out.extend(_walk_strings(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            out.extend(_walk_strings(item))
    return out


def scan_projection_for_leak(projection: Any, *, canaries: tuple[str, ...] = ()) -> str | None:
    """SCAN 1 — return ``runtime_history_leak_detected`` on any forbidden marker
    or seeded canary in the JSON projection, else ``None``."""

    strings = _walk_strings(projection)
    for text in strings:
        if _has_forbidden_marker(text):
            return RUNTIME_HISTORY_LEAK_DETECTED
    if canaries:
        lowered_all = "\x1f".join(text.lower() for text in strings)
        for canary in canaries:
            if canary and canary.lower() in lowered_all:
                return RUNTIME_HISTORY_LEAK_DETECTED
    return None


def scan_bytes_for_leak(raw: bytes, *, canaries: tuple[str, ...] = ()) -> str | None:
    """SCAN 2 helper — scan serialized bytes (not only JSON text) for forbidden
    byte patterns / canaries. Returns the stable leak code or ``None``."""

    if not isinstance(raw, (bytes, bytearray)):
        raise ContractError(INVALID_START_PAYLOAD)
    lowered = bytes(raw).lower()
    for marker in FORBIDDEN_MARKERS:
        if marker.encode("utf-8") in lowered:
            return RUNTIME_HISTORY_LEAK_DETECTED
    for canary in canaries:
        if canary and canary.encode("utf-8").lower() in lowered:
            return RUNTIME_HISTORY_LEAK_DETECTED
    return None


__all__ = [
    "SCHEMA_VERSION",
    "MODE_CONTROLLED_DETERMINISTIC",
    "PHASE_SLICE_1",
    "P5_TEMPORAL_TASK_QUEUE",
    "SLICE_1_UPDATE_EVENT_TYPES",
    "SNAPSHOT_TYPE",
    "HISTORY_TYPE",
    "ACTIVITY_INPUT_TYPE",
    "ACTIVITY_OUTPUT_TYPE",
    "RUNTIME_DISABLED",
    "RUNTIME_APPROVAL_MISMATCH",
    "RUNTIME_PRECONDITION_UNMET",
    "RUNTIME_IDEMPOTENCY_CONFLICT",
    "INVALID_START_PAYLOAD",
    "RUNTIME_HISTORY_LEAK_DETECTED",
    "RUNTIME_UNSAFE_MATERIAL",
    "RUNTIME_CANCEL_SCOPE_UNSUPPORTED",
    "RUNTIME_NOT_FOUND",
    "RUNTIME_ERROR",
    "ACTIVE_RUN_CANCELLATION_WATCH",
    "CANCEL_AMBIGUOUS",
    "STABLE_CODES",
    "FORBIDDEN_MARKERS",
    "ALLOWED_SNAPSHOT_KEYS",
    "ALLOWED_ARTIFACT_REF_KEYS",
    "ContractError",
    "ClaimCheckRef",
    "StartRequest",
    "UpdatePayload",
    "ActivityInput",
    "ActivityOutput",
    "StepArtifactRef",
    "build_claim_check_ref",
    "validate_claim_check_ref",
    "artifact_ref_to_claim_check",
    "safe_ref",
    "workflow_id_from_refs",
    "build_start_request",
    "validate_start_request",
    "build_update_payload",
    "validate_update_payload",
    "build_activity_input",
    "validate_activity_input",
    "validate_activity_output",
    "validate_step_artifact_ref",
    "build_activity_output",
    "deterministic_workflow_id",
    "deterministic_artifact_ref",
    "build_step_artifact_ref",
    "step_artifact_ref_projection",
    "deterministic_evidence",
    "deterministic_evidence_fields",
    "safe_artifact_kind",
    "build_query_snapshot",
    "canonical_json_bytes",
    "scan_projection_for_leak",
    "scan_bytes_for_leak",
]
