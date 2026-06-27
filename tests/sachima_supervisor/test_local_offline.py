"""Tests for the Sachima x agent-run-supervisor local/offline integration seam.

These cover the default-off gate, the exact approval token, the mode allowlist,
the prompt/context + metadata boundary, lazy optional-dependency import,
sanitized CallerResult mapping, and sanitized local evidence writing.

Secret-shaped literals are split with string concatenation so repo secret
scanners do not flag the tests themselves.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sachima_supervisor import local_offline
from sachima_supervisor.local_offline import (
    IMPLEMENTATION_APPROVAL_TOKEN,
    LocalOfflineSupervisorError,
    LocalOfflineSupervisorOutcome,
    LocalOfflineSupervisorRequest,
    build_caller_invocation_spec,
    build_offline_view_model,
    invoke_local_offline_supervisor,
)

# The full sanitized payload contract — both the view model and the evidence
# file must carry exactly these keys and nothing else.
_EXPECTED_PAYLOAD_KEYS = {
    "type",
    "mode",
    "phase",
    "status",
    "supervisor_status",
    "correlation_label",
    "error_code",
    "business_verdict",
    "caller_verdict",
    "artifact_ref_count",
    "evidence_ref",
    "evidence_digest",
}


# --------------------------------------------------------------------------- #
# Injected fakes — the seam must never need the real library in tests.
# --------------------------------------------------------------------------- #
@dataclass
class _FakeCallerResult:
    """Stand-in for agent_run_supervisor.caller.CallerResult."""

    status: str
    artifact_refs: tuple[str, ...] = ()
    business_verdict: Any = None
    summary: Any = None


class _RecordingSpecFactory:
    """Stand-in for CallerInvocationSpec — records the kwargs it is built with."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(kind="fake_caller_invocation_spec", **kwargs)


class _StrictCallerInvocationSpecFactory:
    """Signature-shaped fake matching agent_run_supervisor.caller.CallerInvocationSpec."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        *,
        mode: str,
        role: Any = None,
        role_file: str | Path | None = None,
        prompt: str | None = None,
        context: str | None = None,
        cwd: str | Path | None = None,
        runs_dir: str | Path | None = None,
        sessions_dir: str | Path | None = None,
        session_id: str | None = None,
        session_name: str | None = None,
    ) -> SimpleNamespace:
        call = {
            "mode": mode,
            "role": role,
            "role_file": role_file,
            "prompt": prompt,
            "context": context,
            "cwd": cwd,
            "runs_dir": runs_dir,
            "sessions_dir": sessions_dir,
            "session_id": session_id,
            "session_name": session_name,
        }
        self.calls.append(call)
        return SimpleNamespace(kind="strict_caller_invocation_spec", **call)


class _RecordingInvokeCaller:
    """Stand-in for invoke_caller — records the spec it is handed."""

    def __init__(self, result: _FakeCallerResult) -> None:
        self.result = result
        self.specs: list[Any] = []

    def __call__(self, spec: Any) -> _FakeCallerResult:
        self.specs.append(spec)
        return self.result


def _exploding(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("supervisor boundary must not be reached")


def _request(**overrides: Any) -> LocalOfflineSupervisorRequest:
    base: dict[str, Any] = {
        "mode": "exec_dry_run",
        "role": "sachima.planner",
        "correlation_label": "txn-label-abc123",
        "enabled": True,
        "approval_token": IMPLEMENTATION_APPROVAL_TOKEN,
    }
    base.update(overrides)
    return LocalOfflineSupervisorRequest(**base)


# --------------------------------------------------------------------------- #
# 1. Default-off gate
# --------------------------------------------------------------------------- #
def test_disabled_request_fails_closed_before_reaching_supervisor() -> None:
    request = _request(enabled=False)

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        invoke_local_offline_supervisor(
            request, spec_factory=_exploding, invoke_caller=_exploding
        )

    assert exc.value.error_code == "supervisor_disabled"


# --------------------------------------------------------------------------- #
# 2. Exact approval token required
# --------------------------------------------------------------------------- #
def test_exact_approval_token_required() -> None:
    request = _request(**{"approval_" + "token": "approve_" + "not_the_real_token"})

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        invoke_local_offline_supervisor(
            request, spec_factory=_exploding, invoke_caller=_exploding
        )

    assert exc.value.error_code == "approval_token_mismatch"


def test_empty_approval_token_fails_closed() -> None:
    request = _request(approval_token="")

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        invoke_local_offline_supervisor(
            request, spec_factory=_exploding, invoke_caller=_exploding
        )

    assert exc.value.error_code == "approval_token_mismatch"


# --------------------------------------------------------------------------- #
# 3. exec_dry_run builds a spec and calls the injected fake invoke_caller;
#    the returned view model is sanitized and business_verdict stays None.
# --------------------------------------------------------------------------- #
def test_exec_dry_run_builds_spec_and_invokes_injected_caller() -> None:
    spec_factory = _RecordingSpecFactory()
    invoke_caller = _RecordingInvokeCaller(
        _FakeCallerResult(
            status="config_preview",
            artifact_refs=("redacted_artifact_0",),
            business_verdict=None,
        )
    )
    request = _request(
        mode="exec_dry_run",
        prompt="raw-" + "planner prompt body",
        context="raw-" + "assembled context body",
        caller_verdict="caller_marked_ok",
    )

    outcome = invoke_local_offline_supervisor(
        request, spec_factory=spec_factory, invoke_caller=invoke_caller
    )

    # A spec was built from sanitized fields and handed to invoke_caller.
    assert len(spec_factory.calls) == 1
    assert spec_factory.calls[0]["role"] == "sachima.planner"
    assert spec_factory.calls[0]["mode"] == "exec_dry_run"
    assert len(invoke_caller.specs) == 1
    assert invoke_caller.specs[0].kind == "fake_caller_invocation_spec"

    # The library's verdict stays None; the supervisor status is mapped through.
    assert isinstance(outcome, LocalOfflineSupervisorOutcome)
    assert outcome.supervisor_status == "config_preview"
    assert outcome.status == "observed"
    assert outcome.business_verdict is None
    assert outcome.view_model["business_verdict"] is None
    assert outcome.view_model["supervisor_status"] == "config_preview"
    assert outcome.view_model["phase"] == "dry_run"
    assert outcome.artifact_ref_count == 1

    # Caller-owned verdict is carried separately.
    assert outcome.caller_verdict == "caller_marked_ok"
    assert outcome.view_model["caller_verdict"] == "caller_marked_ok"

    # No raw prompt/context leaks into the view model.
    rendered = repr(outcome.view_model).lower()
    assert "planner prompt body" not in rendered
    assert "assembled context body" not in rendered

    # The view model is a sanitized allowlisted dict.
    assert set(outcome.view_model.keys()) == _EXPECTED_PAYLOAD_KEYS


def test_build_spec_uses_agent_run_supervisor_public_caller_fields_only() -> None:
    spec_factory = _StrictCallerInvocationSpecFactory()
    request = _request(
        role=None,
        role_file="roles/sachima-planner.json",
        cwd="/safe/worktree",
        runs_dir="outputs/sachima/supervisor-runs",
        sessions_dir="outputs/sachima/supervisor-sessions",
        session_id="session-safe-001",
        session_name="session-safe-name",
        allowed_roots=("/safe/worktree",),
        metadata={"safe_label": "safe-value"},
    )

    spec = build_caller_invocation_spec(request, spec_factory=spec_factory)

    assert spec.kind == "strict_caller_invocation_spec"
    assert spec_factory.calls == [
        {
            "mode": "exec_dry_run",
            "role": None,
            "role_file": "roles/sachima-planner.json",
            "prompt": None,
            "context": None,
            "cwd": "/safe/worktree",
            "runs_dir": "outputs/sachima/supervisor-runs",
            "sessions_dir": "outputs/sachima/supervisor-sessions",
            "session_id": "session-safe-001",
            "session_name": "session-safe-name",
        }
    ]


def test_exactly_one_role_source_required() -> None:
    for request in (
        _request(role=None, role_file=None),
        _request(role="role-object", role_file="roles/sachima-planner.json"),
    ):
        with pytest.raises(LocalOfflineSupervisorError) as exc:
            build_caller_invocation_spec(request, spec_factory=_RecordingSpecFactory())
        assert exc.value.error_code == "role_source_required"


def test_build_offline_view_model_keeps_library_verdict_none_and_sanitized() -> None:
    request = _request(caller_verdict="caller_says_ok")
    caller_result = _FakeCallerResult(
        status="completed",
        artifact_refs=("redacted_artifact_0", "redacted_artifact_1"),
        business_verdict=None,
        summary="raw-" + "summary text that must not leak",
    )

    payload = build_offline_view_model(request, caller_result)

    assert set(payload.keys()) == _EXPECTED_PAYLOAD_KEYS
    assert payload["business_verdict"] is None
    assert payload["caller_verdict"] == "caller_says_ok"
    assert payload["supervisor_status"] == "completed"
    assert payload["artifact_ref_count"] == 2
    assert payload["evidence_digest"].startswith("sha256:")
    assert "summary text that must not leak" not in repr(payload).lower()


def test_build_offline_view_model_reads_actual_caller_result_shape_without_raw_refs() -> None:
    request = _request(caller_verdict="caller_says_ok", mode="session_send", session_id="session-safe-001")
    caller_result = SimpleNamespace(
        supervisor_status="completed",
        result={"status": "completed", "final_message": "raw-" + "final text"},
        artifact_dir="/safe/local/artifact-dir",
        run_dir="/safe/local/run-dir",
        session_dir=None,
        business_verdict=None,
    )

    payload = build_offline_view_model(request, caller_result)

    assert payload["supervisor_status"] == "completed"
    assert payload["artifact_ref_count"] == 2
    rendered = repr(payload).lower()
    assert "final text" not in rendered
    assert "/safe/local" not in rendered


def test_build_offline_view_model_counts_exec_artifact_and_run_dir_as_one_output() -> None:
    request = _request(caller_verdict="caller_says_ok", mode="exec")
    caller_result = SimpleNamespace(
        supervisor_status="completed",
        result={"status": "completed"},
        artifact_dir="/safe/local/artifact-dir",
        run_dir="/safe/local/run-dir",
        session_dir=None,
        business_verdict=None,
    )

    payload = build_offline_view_model(request, caller_result)

    assert payload["supervisor_status"] == "completed"
    assert payload["artifact_ref_count"] == 1
    rendered = repr(payload).lower()
    assert "/safe/local" not in rendered


def test_build_offline_view_model_deduplicates_exec_artifact_and_run_dir() -> None:
    request = _request(caller_verdict="caller_says_ok")
    caller_result = SimpleNamespace(
        supervisor_status="completed",
        result={"status": "completed"},
        artifact_dir="/safe/local/same-exec-run",
        run_dir="/safe/local/same-exec-run",
        session_dir=None,
        business_verdict=None,
    )

    payload = build_offline_view_model(request, caller_result)

    assert payload["supervisor_status"] == "completed"
    assert payload["artifact_ref_count"] == 1
    rendered = repr(payload).lower()
    assert "/safe/local" not in rendered


def test_malformed_supervisor_status_is_sanitized_without_raw_leak() -> None:
    request = _request()
    caller_result = SimpleNamespace(
        supervisor_status="RuntimeError raw-" + "exception with unsafe-" + "token",
        result={},
        artifact_dir=None,
        run_dir=None,
        session_dir=None,
        business_verdict=None,
    )

    payload = build_offline_view_model(request, caller_result)

    assert payload["supervisor_status"] == "invalid_supervisor_status"
    rendered = repr(payload).lower()
    assert "runtimeerror" not in rendered
    assert "exception" not in rendered
    assert "unsafe-token" not in rendered


# --------------------------------------------------------------------------- #
# 4. Evidence JSON excludes prompt/context/platform-ids/raw paths/secrets
#    and includes a stable ref/digest/status.
# --------------------------------------------------------------------------- #
def test_evidence_json_is_sanitized_with_stable_ref_and_digest(tmp_path: Path) -> None:
    invoke_caller = _RecordingInvokeCaller(
        _FakeCallerResult(status="config_preview", artifact_refs=("redacted_artifact_0",))
    )
    request = _request(
        prompt="raw-" + "private planner prompt body",
        context="raw-" + "private assembled context body",
        caller_verdict="caller_ok",
        evidence_dir=str(tmp_path),
    )

    outcome = invoke_local_offline_supervisor(
        request, spec_factory=_RecordingSpecFactory(), invoke_caller=invoke_caller
    )

    assert outcome.evidence_ref is not None
    assert outcome.evidence_digest.startswith("sha256:")
    assert outcome.evidence_path is not None

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    evidence = json.loads(files[0].read_text(encoding="utf-8"))

    # Stable sanitized metadata is present.
    assert evidence["evidence_ref"] == outcome.evidence_ref
    assert evidence["evidence_digest"] == outcome.evidence_digest
    assert evidence["status"] == outcome.status
    assert evidence["mode"] == "exec_dry_run"
    assert evidence["correlation_label"] == "txn-label-abc123"
    assert evidence["business_verdict"] is None

    # Exactly the sanitized allowlist — nothing more leaks.
    assert set(evidence.keys()) == _EXPECTED_PAYLOAD_KEYS

    # No raw prompt/context/traceback leaks into the evidence file.
    rendered = files[0].read_text(encoding="utf-8").lower()
    for marker in (
        "private planner prompt body",
        "private assembled context body",
        "traceback",
    ):
        assert marker not in rendered


def test_no_evidence_written_when_evidence_dir_absent(tmp_path: Path) -> None:
    invoke_caller = _RecordingInvokeCaller(_FakeCallerResult(status="config_preview"))
    request = _request()  # no evidence_dir

    outcome = invoke_local_offline_supervisor(
        request, spec_factory=_RecordingSpecFactory(), invoke_caller=invoke_caller
    )

    # The ref/digest label still exists, but no file is written.
    assert outcome.evidence_ref is not None
    assert outcome.evidence_path is None
    assert list(tmp_path.glob("*.json")) == []


# --------------------------------------------------------------------------- #
# 5. Unsafe metadata keys / material are rejected fail-closed.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "forbidden_key",
    ["chat" + "_id", "user" + "_id", "message" + "_id", "card" + "_json", "media" + "_path"],
)
def test_forbidden_metadata_key_rejected_fail_closed(forbidden_key: str) -> None:
    request = _request(metadata={forbidden_key: "redacted-value"})

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        invoke_local_offline_supervisor(
            request, spec_factory=_exploding, invoke_caller=_exploding
        )

    assert exc.value.error_code == "forbidden_metadata_key"


def test_secret_shaped_metadata_key_rejected_fail_closed() -> None:
    request = _request(metadata={"to" + "ken": "unsafe-" + "value"})

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        invoke_local_offline_supervisor(
            request, spec_factory=_exploding, invoke_caller=_exploding
        )

    assert exc.value.error_code == "forbidden_metadata_key"


def test_unsafe_material_in_prompt_rejected_fail_closed() -> None:
    request = _request(prompt="here is a se" + "cret to" + "ken: unsafe-" + "blob")

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        invoke_local_offline_supervisor(
            request, spec_factory=_exploding, invoke_caller=_exploding
        )

    assert exc.value.error_code == "unsafe_material"


def test_platform_id_shaped_metadata_value_rejected_fail_closed() -> None:
    request = _request(metadata={"label": "oc_" + "private_chat_id_value"})

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        invoke_local_offline_supervisor(
            request, spec_factory=_exploding, invoke_caller=_exploding
        )

    assert exc.value.error_code == "unsafe_material"


def test_media_path_in_context_rejected_fail_closed() -> None:
    request = _request(context="see attachment at " + "/tmp/" + "private-capture.png")

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        invoke_local_offline_supervisor(
            request, spec_factory=_exploding, invoke_caller=_exploding
        )

    assert exc.value.error_code == "unsafe_material"


def test_unsafe_caller_verdict_rejected_fail_closed() -> None:
    request = _request(caller_verdict="caller saw unsafe-" + "token" + " value")

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        invoke_local_offline_supervisor(
            request, spec_factory=_exploding, invoke_caller=_exploding
        )

    assert exc.value.error_code == "unsafe_material"


def test_public_view_model_builder_rejects_unsafe_caller_verdict() -> None:
    request = _request(caller_verdict="caller saw unsafe-" + "token" + " value")

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        build_offline_view_model(request, _FakeCallerResult(status="completed"))

    assert exc.value.error_code == "unsafe_material"


def test_public_view_model_builder_sanitizes_status_and_error_code_kwargs() -> None:
    request = _request()

    payload = build_offline_view_model(
        request,
        _FakeCallerResult(status="completed"),
        status="RuntimeError raw-" + "exception with unsafe-" + "token",
        error_code="raw-" + "exception unsafe-" + "token",
    )

    assert payload["status"] == "error"
    assert payload["error_code"] == "invalid_error_code"
    rendered = repr(payload).lower()
    assert "runtimeerror" not in rendered
    assert "exception" not in rendered
    assert "unsafe-token" not in rendered


# --------------------------------------------------------------------------- #
# 6. Unsupported modes (cancel/rollback/gateway_send/...) are rejected.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "mode",
    ["cancel", "rollback", "session_cancel", "gateway_send", "send", "exec_live", ""],
)
def test_unsupported_mode_rejected(mode: str) -> None:
    request = _request(mode=mode)

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        invoke_local_offline_supervisor(
            request, spec_factory=_exploding, invoke_caller=_exploding
        )

    assert exc.value.error_code == "unsupported_mode"


@pytest.mark.parametrize(
    "mode",
    ["exec_dry_run", "exec", "session_create", "session_send", "session_status", "session_close"],
)
def test_supported_modes_accepted(mode: str) -> None:
    spec_factory = _RecordingSpecFactory()
    invoke_caller = _RecordingInvokeCaller(_FakeCallerResult(status="config_preview"))
    request = _request(mode=mode)

    outcome = invoke_local_offline_supervisor(
        request, spec_factory=spec_factory, invoke_caller=invoke_caller
    )

    assert outcome.mode == mode
    assert spec_factory.calls[0]["mode"] == mode


# --------------------------------------------------------------------------- #
# 7. Module import works when agent_run_supervisor is not installed.
# --------------------------------------------------------------------------- #
def test_module_imports_without_agent_run_supervisor_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Block the optional library entirely (None in sys.modules -> ImportError).
    monkeypatch.setitem(sys.modules, "agent_run_supervisor", None)
    monkeypatch.setitem(sys.modules, "agent_run_supervisor.caller", None)

    module = importlib.import_module("sachima_supervisor.local_offline")

    assert hasattr(module, "build_caller_invocation_spec")
    assert hasattr(module, "invoke_local_offline_supervisor")


def test_missing_library_without_injection_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "agent_run_supervisor", None)
    monkeypatch.setitem(sys.modules, "agent_run_supervisor.caller", None)
    request = _request()

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        invoke_local_offline_supervisor(request)  # no injected fakes

    assert exc.value.error_code == "supervisor_library_unavailable"


# --------------------------------------------------------------------------- #
# 8. No-throw mapping: a supervisor exception becomes a stable error code with
#    no raw exception text leaking into the outcome or evidence.
# --------------------------------------------------------------------------- #
def test_supervisor_error_is_caught_and_mapped_without_raw_leak(tmp_path: Path) -> None:
    def boom(spec: Any) -> Any:
        raise RuntimeError("raw-" + "exception detail with se" + "cret token value")

    request = _request(evidence_dir=str(tmp_path))

    outcome = invoke_local_offline_supervisor(
        request, spec_factory=_RecordingSpecFactory(), invoke_caller=boom
    )

    assert outcome.status == "error"
    assert outcome.error_code == "supervisor_invocation_failed"
    assert outcome.supervisor_status is None
    assert outcome.business_verdict is None

    rendered = repr(outcome).lower()
    assert "exception detail" not in rendered
    assert "traceback" not in rendered

    evidence_text = list(tmp_path.glob("*.json"))[0].read_text(encoding="utf-8").lower()
    assert "exception detail" not in evidence_text
    assert "traceback" not in evidence_text


# --------------------------------------------------------------------------- #
# 9. A hostile non-None library business_verdict never propagates.
# --------------------------------------------------------------------------- #
def test_library_business_verdict_never_propagates(tmp_path: Path) -> None:
    invoke_caller = _RecordingInvokeCaller(
        _FakeCallerResult(
            status="completed",
            business_verdict="hostile-" + "library-verdict-value",
        )
    )
    request = _request(mode="exec", evidence_dir=str(tmp_path))

    outcome = invoke_local_offline_supervisor(
        request, spec_factory=_RecordingSpecFactory(), invoke_caller=invoke_caller
    )

    assert outcome.business_verdict is None
    assert outcome.view_model["business_verdict"] is None
    evidence_text = list(tmp_path.glob("*.json"))[0].read_text(encoding="utf-8")
    assert "hostile-" + "library-verdict-value" not in evidence_text


# --------------------------------------------------------------------------- #
# 10. Static property: the seam source must not import gateway/network/IM libs.
# --------------------------------------------------------------------------- #
def test_source_has_no_gateway_or_network_imports() -> None:
    source = Path(local_offline.__file__).read_text(encoding="utf-8")
    lowered = source.lower()

    # Bare module tokens that never appear in normal prose.
    for token in ("aiohttp", "httpx", "lark_oapi"):
        assert token not in lowered, f"forbidden module reference: {token}"

    # Import-form checks for words that do appear in prose ("gateway", "requests").
    for statement in ("import gateway", "from gateway", "import requests", "from requests"):
        assert statement not in lowered, f"forbidden import: {statement}"


def test_build_caller_invocation_spec_gate_runs_before_factory() -> None:
    # The default-off gate must reject before the spec factory is ever resolved.
    request = _request(enabled=False)

    with pytest.raises(LocalOfflineSupervisorError) as exc:
        build_caller_invocation_spec(request, spec_factory=_exploding)

    assert exc.value.error_code == "supervisor_disabled"
