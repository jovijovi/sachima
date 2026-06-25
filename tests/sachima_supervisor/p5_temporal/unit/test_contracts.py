"""T1 — sanitized contracts + exact validators (Gate B, feeds SCAN 1).

These tests pin the production-grade history trust boundary for PR B: frozen,
schema-versioned, sanitized dataclasses with exact validators that reject hostile
subclasses, extra/missing fields, malformed refs, unsafe digests, and every
denylist marker (raw prompt/output, private paths, platform ids, card JSON,
credentials, connection strings, signed URLs, delivery payloads).

The module under test is local/offline pure Python — importing it starts no
Temporal service, Worker, subprocess, or network.
"""

from __future__ import annotations

import dataclasses

import pytest

from sachima_supervisor.p5_temporal import contracts as C


_POSTGRES_URL = "post" + "gres://user:" + "pw" + "@host/db"
_POSTGRESQL_URL = "postgresql" + "://user:" + "pw" + "@host:5432/db"
_REDIS_URL = "redis" + "://:" + "pass" + "word@host:6379/0"
_SIGNED_URL = "https://example.test/object?" + "X-Amz-" + "Signature=abc"
_TOKEN_URL = "https://example.test/object?" + "to" + "ken=opaque_value"
_S3_SIGNED_URL = "s3" + "://bucket/key?AWSAccessKeyId=AKIAEXAMPLE"


# --------------------------------------------------------------------------- #
# Clean baseline fields
# --------------------------------------------------------------------------- #
def _clean_claim_ref() -> dict:
    return {
        "ref": "claim_ref_input_0",
        "digest": "sha256:" + "a" * 64,
        "kind": "input",
        "byte_count": 128,
    }


def _clean_start_fields() -> dict:
    return {
        "run_ref": "run_p5_demo_0001",
        "workflow_ref": "tx_p5_demo_0001",
        "step_ref": "architect",
        "attempt_index": 1,
        "role_keys": ("sachima_claude_read_only_reviewer",),
        "input_claim_refs": (_clean_claim_ref(),),
        "idempotency_material": "idem_p5_demo_0001",
        "phase": "p5_temporal_slice_1",
    }


# --------------------------------------------------------------------------- #
# Stable code family (FR1/FR4/FR7 + WATCH)
# --------------------------------------------------------------------------- #
def test_stable_code_family_present_and_exact():
    assert C.RUNTIME_DISABLED == "runtime_disabled"
    assert C.RUNTIME_APPROVAL_MISMATCH == "runtime_approval_mismatch"
    assert C.RUNTIME_PRECONDITION_UNMET == "runtime_precondition_unmet"
    assert C.RUNTIME_IDEMPOTENCY_CONFLICT == "runtime_idempotency_conflict"
    assert C.INVALID_START_PAYLOAD == "invalid_start_payload"
    assert C.RUNTIME_HISTORY_LEAK_DETECTED == "runtime_history_leak_detected"
    assert C.ACTIVE_RUN_CANCELLATION_WATCH == "active_run_cancellation_watch"
    assert C.CANCEL_AMBIGUOUS == "cancel_ambiguous"


def test_schema_pins():
    assert C.SCHEMA_VERSION == 1
    assert C.MODE_CONTROLLED_DETERMINISTIC == "controlled_deterministic"
    # Slice 1 update set is pinned to exactly {resume, request_cancel}; delivery /
    # approval / rejection are deferred (P6 / Gateway / real delivery surface).
    assert set(C.SLICE_1_UPDATE_EVENT_TYPES) == {"resume", "request_cancel"}


# --------------------------------------------------------------------------- #
# build_start_request — accept clean, reject hostile
# --------------------------------------------------------------------------- #
def test_build_start_request_accepts_clean_fields():
    req = C.build_start_request(**_clean_start_fields())
    assert type(req) is C.StartRequest
    assert dataclasses.is_dataclass(req)
    assert req.schema_version == C.SCHEMA_VERSION
    assert req.mode == C.MODE_CONTROLLED_DETERMINISTIC
    assert req.run_ref == "run_p5_demo_0001"
    assert req.step_ref == "architect"
    assert req.attempt_index == 1
    assert req.role_keys == ("sachima_claude_read_only_reviewer",)
    assert len(req.input_claim_refs) == 1
    assert type(req.input_claim_refs[0]) is C.ClaimCheckRef
    assert req.input_claim_refs[0].digest == "sha256:" + "a" * 64
    # frozen
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.run_ref = "mutated"  # type: ignore[misc]


def test_validate_start_request_rejects_hostile_subclass():
    class Evil(C.StartRequest):  # type: ignore[misc]
        pass

    req = C.build_start_request(**_clean_start_fields())
    evil = Evil(**dataclasses.asdict(req) | {"input_claim_refs": req.input_claim_refs})
    with pytest.raises(C.ContractError) as exc:
        C.validate_start_request(evil)
    assert exc.value.code == C.INVALID_START_PAYLOAD


@pytest.mark.parametrize(
    "mutate",
    [
        {"run_ref": "raw_prompt_leak"},            # forbidden marker
        {"run_ref": "/home/ecs-user/secret"},      # private path
        {"step_ref": "card_json_blob"},            # card JSON marker
        {"workflow_ref": "chat_id_99887766"},      # platform id marker
        {"idempotency_material": "bearer abc"},     # credential marker
        {"run_ref": "om_private_open_id"},          # feishu/platform private id
        {"run_ref": ""},                            # empty
        {"attempt_index": 0},                       # < 1
        {"attempt_index": "1"},                     # wrong type
        {"role_keys": ()},                          # missing role
        {"role_keys": ("write_capable_role",)},     # write-capable not allowed slice 1
    ],
)
def test_build_start_request_rejects_unsafe(mutate):
    fields = _clean_start_fields()
    fields.update(mutate)
    with pytest.raises(C.ContractError) as exc:
        C.build_start_request(**fields)
    assert exc.value.code in {C.INVALID_START_PAYLOAD, C.RUNTIME_PRECONDITION_UNMET}


@pytest.mark.parametrize(
    "bad_digest",
    [
        "sha256:" + "a" * 63,        # too short
        "sha256:" + "a" * 65,        # too long
        "sha256:" + "A" * 64,        # uppercase out of charset
        "sha256:" + "g" * 64,        # non-hex
        "md5:" + "a" * 32,           # wrong algo
        "a" * 64,                    # missing prefix
    ],
)
def test_claim_ref_rejects_bad_digest(bad_digest):
    ref = _clean_claim_ref()
    ref["digest"] = bad_digest
    fields = _clean_start_fields()
    fields["input_claim_refs"] = (ref,)
    with pytest.raises(C.ContractError) as exc:
        C.build_start_request(**fields)
    assert exc.value.code == C.INVALID_START_PAYLOAD


@pytest.mark.parametrize(
    "unsafe_marker",
    [
        "raw_prompt",
        "card_json",
        "media_path",
        "tool_output",
        "signed_url",
        "/home/",
        "-----BEGIN",
        "sk" + "-livesecretkeymaterial000000",
    ],
)
def test_claim_ref_rejects_unsafe_material_in_ref(unsafe_marker):
    ref = _clean_claim_ref()
    ref["ref"] = "claim_ref_" + unsafe_marker
    fields = _clean_start_fields()
    fields["input_claim_refs"] = (ref,)
    with pytest.raises(C.ContractError):
        C.build_start_request(**fields)


def test_claim_ref_rejects_extra_and_missing_fields():
    extra = _clean_claim_ref()
    extra["raw_prompt"] = "leak"
    fields = _clean_start_fields()
    fields["input_claim_refs"] = (extra,)
    with pytest.raises(C.ContractError):
        C.build_start_request(**fields)

    missing = _clean_claim_ref()
    del missing["digest"]
    fields2 = _clean_start_fields()
    fields2["input_claim_refs"] = (missing,)
    with pytest.raises(C.ContractError):
        C.build_start_request(**fields2)


# --------------------------------------------------------------------------- #
# Deterministic ids / artifact projection
# --------------------------------------------------------------------------- #
def test_deterministic_workflow_id_stable_and_safe():
    req = C.build_start_request(**_clean_start_fields())
    wid1 = C.deterministic_workflow_id(req)
    wid2 = C.deterministic_workflow_id(req)
    assert wid1 == wid2
    assert wid1.startswith("p5wf_")
    # safe charset only
    assert all(ch.islower() or ch.isdigit() or ch == "_" for ch in wid1)
    # workflow id is keyed on (run_ref, step_ref); idempotency divergence must NOT
    # change it (so the same step maps to exactly one durable workflow).
    diverged = C.build_start_request(**(_clean_start_fields() | {"idempotency_material": "idem_other_0002"}))
    assert C.deterministic_workflow_id(diverged) == wid1
    # but a different step is a different workflow id
    other_step = C.build_start_request(**(_clean_start_fields() | {"step_ref": "reviewer"}))
    assert C.deterministic_workflow_id(other_step) != wid1


def test_workflow_id_contract_accepts_only_exact_deterministic_id():
    req = C.build_start_request(**_clean_start_fields())
    wid = C.deterministic_workflow_id(req)

    assert C.validate_workflow_id(wid) == wid
    assert C.workflow_id_for_start_request(req, supplied=wid) == wid
    assert C.workflow_id_for_start_request(req) == wid

    with pytest.raises(C.ContractError) as mismatch:
        C.workflow_id_for_start_request(req, supplied="p5wf_" + "1" * 48)
    assert mismatch.value.code == C.INVALID_START_PAYLOAD


@pytest.mark.parametrize(
    "raw_workflow_id",
    [
        "run_p5_demo_0001",
        "p5wf_" + "0" * 47,
        "p5wf_" + "g" * 48,
        "http://example.test/object?" + "to" + "ken=raw",
        "/home/ecs-user/private/workflow",
        "post" + "gres://user:pw@host/db",
        "p5wf_" + "0" * 48 + "?" + "X-Amz-" + "Signature=abc",
    ],
)
def test_validate_workflow_id_rejects_raw_or_non_deterministic_material(raw_workflow_id):
    with pytest.raises(C.ContractError) as exc:
        C.validate_workflow_id(raw_workflow_id)
    assert exc.value.code == C.INVALID_START_PAYLOAD


def test_deterministic_artifact_ref_is_claim_check_only():
    req = C.build_start_request(**_clean_start_fields())
    ref = C.deterministic_artifact_ref(req)
    assert set(ref) == {
        "artifact_id",
        "producer_step_id",
        "content_digest",
        "artifact_kind",
        "byte_count",
        "created_at_ref",
    }
    assert ref["producer_step_id"] == "architect"
    assert C._SHA256_DIGEST_RE.fullmatch(ref["content_digest"])
    assert type(ref["byte_count"]) is int
    # deterministic
    assert C.deterministic_artifact_ref(req) == ref


# --------------------------------------------------------------------------- #
# Update payloads — pinned slice-1 set only
# --------------------------------------------------------------------------- #
def test_build_update_payload_accepts_slice_1_events():
    resume = C.build_update_payload(event_key="evt_resume_0001", event_type="resume", ref="claim_ref_resume_0")
    assert type(resume) is C.UpdatePayload
    assert resume.event_type == "resume"
    cancel = C.build_update_payload(event_key="evt_cancel_0001", event_type="request_cancel", ref=None)
    assert cancel.event_type == "request_cancel"


@pytest.mark.parametrize("deferred", ["delivery", "approval", "rejection", "approve_intent"])
def test_build_update_payload_rejects_deferred_events(deferred):
    with pytest.raises(C.ContractError):
        C.build_update_payload(event_key="evt_x_0001", event_type=deferred, ref=None)


# --------------------------------------------------------------------------- #
# SCAN 1 helpers — allowlist / forbidden markers / canary
# --------------------------------------------------------------------------- #
def test_query_snapshot_projection_allowlist_only():
    req = C.build_start_request(**_clean_start_fields())
    snap = C.build_query_snapshot(
        start_request=req,
        state="completed",
        snapshot_version=1,
        artifact_refs=(C.deterministic_artifact_ref(req),),
        active_run_watch=False,
        error_code=None,
    )
    assert set(snap).issubset(C.ALLOWED_SNAPSHOT_KEYS)
    # no forbidden material in the rendered projection
    assert C.scan_projection_for_leak(snap) is None


def test_scan_projection_detects_forbidden_markers_and_canary():
    leaky = {"type": C.SNAPSHOT_TYPE, "note": "Traceback (most recent call last)"}
    assert C.scan_projection_for_leak(leaky) == C.RUNTIME_HISTORY_LEAK_DETECTED
    canary = {"type": C.SNAPSHOT_TYPE, "x": "CANARY_7e3f_secret_marker"}
    assert (
        C.scan_projection_for_leak(canary, canaries=("CANARY_7e3f_secret_marker",))
        == C.RUNTIME_HISTORY_LEAK_DETECTED
    )
    assert C.scan_projection_for_leak({"type": C.SNAPSHOT_TYPE, "x": "claim_ref_ok"}) is None


# --------------------------------------------------------------------------- #
# safe_ref — raw material rejected BEFORE normalization (Gate B/G blocker fix)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw",
    [
        _POSTGRES_URL,              # connection string
        _POSTGRESQL_URL,            # connection string (variant)
        _REDIS_URL,                 # connection string (credential)
        "/home/ecs-user/.ssh/id_rsa",               # unix private path
        "C:\\Users\\x\\.ssh\\id_rsa",               # windows private path
        _SIGNED_URL,                # signed URL
        _TOKEN_URL,                 # URL syntax, no denylist word
        _S3_SIGNED_URL,             # signed object URL
        "value with spaces",                        # whitespace is not ref material
    ],
)
def test_safe_ref_rejects_raw_forbidden_material_before_normalization(raw):
    # Pre-fix these normalized into safe-looking ids (`postgres__user_pw_host_db`,
    # `home_ecs_user__ssh_id_rsa`, …) and entered history. They must now fail closed
    # on the RAW value, before normalization can collapse the unsafe syntax away.
    with pytest.raises(C.ContractError) as exc:
        C.safe_ref(raw)
    assert exc.value.code == C.INVALID_START_PAYLOAD


def test_safe_ref_allows_wp4_dotted_dashed_colon_refs():
    # Normal WP4-style refs are dotted / dashed / colon identifiers and must still
    # normalize to the strict history charset.
    assert C.safe_ref("run.alpha-01") == "run_alpha_01"
    assert C.safe_ref("sachima.codex.primary_reviewer") == "sachima_codex_primary_reviewer"
    assert C.safe_ref("p5:step-1") == "p5_step_1"
    assert C.safe_ref("run_p5_demo_0001") == "run_p5_demo_0001"


@pytest.mark.parametrize(
    "empty",
    [
        "",          # empty string
        "   ",       # whitespace only
        "\t",        # tab only
        ".",         # single punctuation
        "...",       # all dots
        "---",       # all dashes
        ":::",       # all colons
        ".-:",       # mixed punctuation only
    ],
)
def test_safe_ref_rejects_empty_and_collapsing_refs(empty):
    # Pre-fix these collapsed into a safe-looking bare ``ref_`` id and entered
    # history. Empty / whitespace-only / all-punctuation material is never a ref and
    # must fail closed before (or at) normalization.
    with pytest.raises(C.ContractError) as exc:
        C.safe_ref(empty)
    assert exc.value.code == C.INVALID_START_PAYLOAD


@pytest.mark.parametrize("sentinel", ["None", "none", "NONE", " none ", "None "])
def test_safe_ref_rejects_stringified_none_sentinel(sentinel):
    # ``str(None)`` -> ``'None'`` (lowercased ``'none'``) is missing identity material
    # masquerading as a value; it must never normalize into a safe-looking id.
    with pytest.raises(C.ContractError) as exc:
        C.safe_ref(sentinel)
    assert exc.value.code == C.INVALID_START_PAYLOAD


@pytest.mark.parametrize("field", ["run_ref", "workflow_ref", "step_ref", "idempotency_material"])
def test_build_start_request_rejects_empty_identity_ref(field):
    # RED/GREEN: every required identity ref must fail closed when empty, so an empty
    # ref can never reach a StartRequest / Temporal start.
    fields = _clean_start_fields()
    fields[field] = ""
    with pytest.raises(C.ContractError) as exc:
        C.build_start_request(**fields)
    assert exc.value.code == C.INVALID_START_PAYLOAD


def test_build_start_request_still_accepts_clean_refs_after_empty_guard():
    # GREEN companion: the empty/none guard must not reject clean identity refs.
    req = C.build_start_request(**_clean_start_fields())
    assert req.run_ref == "run_p5_demo_0001"
    assert req.step_ref == "architect"
    assert req.idempotency_material == "idem_p5_demo_0001"


def test_artifact_ref_to_claim_check_rejects_raw_path_in_artifact_id():
    # The executor's resolved-input translation path also normalizes WP4 artifact
    # ids; a private path smuggled as an artifact_id must fail closed too.
    projection = {
        "artifact_id": "/home/ecs-user/.ssh/id_rsa",
        "content_digest": "sha256:" + "a" * 64,
        "artifact_kind": "input",
        "byte_count": 64,
    }
    with pytest.raises(C.ContractError):
        C.artifact_ref_to_claim_check(projection)
