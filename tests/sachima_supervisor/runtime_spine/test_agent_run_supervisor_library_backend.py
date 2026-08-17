"""The retired ``library`` backend — the one fail-closed migration seam.

Focused acceptance tests for P5-a/P5-b/P5-d of the ARS 0.7.6 Socket API v3
integration plan (``docs/plans/2026-08-17-ars-0.7.6-socket-api-v3-integration-plan.md``
§11, seams S-1 … S-14).

This file used to drive the in-process ``agent_run_supervisor`` library backend
through an injected facade double. That backend, its config, its facade, and
its degraded ``session_inspect`` emulation are gone: 0.7.x removed every module
they called. What is proven here now is the retirement itself —

* one **distinct** stable code, ``runtime_library_backend_retired``, that an
  operator can tell apart from "the daemon is down" and from "your config is
  malformed" (A-18);
* a fixed, non-echoing message naming the two supported backends, ``fake`` and
  ``arsd``;
* nothing importable that could still run: no backend class, no config class,
  no facade, no emulation, no fallback;
* **B-10** — the retired-module guard: no path under ``sachima_supervisor/``,
  ``gateway/``, ``scripts/`` or ``tools/`` names a removed
  ``agent_run_supervisor`` submodule, in code, comment, or docstring, outside
  the migration seam itself. This is what stops a retirement from being
  partial.

Pure local/offline: importing anything here starts no process, socket, daemon,
Gateway, or Temporal surface, and reaches no ``agent_run_supervisor`` module.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import sachima_supervisor.runtime_spine as spine
import sachima_supervisor.runtime_spine.agent_run_supervisor_library_backend as seam
from sachima_supervisor.runtime_spine.events import SpineError

REPO_ROOT = Path(__file__).resolve().parents[3]

#: The ``agent_run_supervisor`` submodules 0.7.x removed with the legacy
#: library surface. Every one of them is a hard error anywhere in Sachima's own
#: source outside the retirement seam.
RETIRED_MODULES = (
    "role",
    "workspace",
    "session_runtime",
    "session_inspect",
    "goal",
    "caller",
    "hermes_caller",
)

#: The one file allowed to name them: the migration seam, whose whole job is to
#: tell an operator what went away.
MIGRATION_SEAM = Path(seam.__file__).resolve()

#: The guard's scope — every tree that is Sachima's own source.
GUARDED_TREES = ("sachima_supervisor", "gateway", "scripts", "tools")

#: Both spellings a submodule reference can take. The alternation is anchored
#: with ``\b`` so ``session_runtime`` and ``session_inspect`` cannot be masked
#: by the surviving ``session`` module, and vice versa.
_ATTRIBUTE_RE = re.compile(
    r"agent_run_supervisor\.(" + "|".join(RETIRED_MODULES) + r")\b"
)
_FROM_IMPORT_RE = re.compile(
    r"from\s+agent_run_supervisor\s+import\s+[^\n]*\b("
    + "|".join(RETIRED_MODULES)
    + r")\b"
)


def _guarded_sources() -> list[Path]:
    files: list[Path] = []
    for tree in GUARDED_TREES:
        root = REPO_ROOT / tree
        if not root.exists():
            continue
        files.extend(
            path
            for path in sorted(root.rglob("*.py"))
            if "__pycache__" not in path.parts
        )
    return files


# --------------------------------------------------------------------------- #
# A. The migration code and message (P5-a, A-18)
# --------------------------------------------------------------------------- #
def test_the_migration_code_is_distinct_and_the_only_code_of_this_seam() -> None:
    assert seam.RUNTIME_LIBRARY_BACKEND_RETIRED == "runtime_library_backend_retired"
    assert seam.ARS_LIBRARY_STABLE_CODES == frozenset(
        {seam.RUNTIME_LIBRARY_BACKEND_RETIRED}
    )
    # Deliberately neither the daemon-unavailable code nor a generic
    # invalid-config code: an operator must be able to tell them apart.
    assert seam.RUNTIME_LIBRARY_BACKEND_RETIRED not in spine.ARSD_STABLE_CODES
    assert seam.RUNTIME_LIBRARY_BACKEND_RETIRED != spine.RUNTIME_ARSD_UNAVAILABLE
    assert seam.RUNTIME_LIBRARY_BACKEND_RETIRED != spine.RUNTIME_INVALID_ARSD_CONFIG


def test_selecting_the_retired_backend_fails_closed_naming_fake_and_arsd() -> None:
    with pytest.raises(SpineError) as exc:
        seam.library_backend_retired()
    assert exc.value.code == seam.RUNTIME_LIBRARY_BACKEND_RETIRED
    assert str(exc.value) == seam.LIBRARY_MIGRATION_MESSAGE
    assert seam.SUPPORTED_SUPERVISOR_BACKENDS == ("fake", "arsd")
    for choice in seam.SUPPORTED_SUPERVISOR_BACKENDS:
        assert choice in seam.LIBRARY_MIGRATION_MESSAGE
    assert seam.LIBRARY_MIGRATION_MESSAGE.startswith(
        seam.RUNTIME_LIBRARY_BACKEND_RETIRED
    )


def test_the_migration_message_is_a_fixed_literal_that_echoes_nothing() -> None:
    """It takes no argument, so there is nothing it could echo."""

    import inspect

    assert inspect.signature(seam.library_backend_retired).parameters == {}
    for canary in ("/", "\\", "sk-", "bearer ", "chat_id", "raw_prompt"):
        assert canary not in seam.LIBRARY_MIGRATION_MESSAGE, canary


def test_a_retired_library_config_document_is_recognized_not_parsed() -> None:
    assert seam.is_retired_library_config({"type": seam.ARS_LIBRARY_CONFIG_TYPE}) is True
    for other in (
        {"type": spine.ARSD_SUPERVISOR_CONFIG_TYPE},
        {"type": "something else"},
        {},
        ["not", "a", "document"],
        None,
        "{}",
    ):
        assert seam.is_retired_library_config(other) is False


# --------------------------------------------------------------------------- #
# B. Nothing importable can still run (P5-b, S-1)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name",
    [
        "AgentRunSupervisorLibraryBackend",
        "AgentRunSupervisorLibraryConfig",
        "LibraryUnavailableError",
        "validate_agent_run_supervisor_library_config",
        "derive_ars_session_id",
        "derive_backend_handle",
        "RUNTIME_ARS_LIBRARY_DISABLED",
        "RUNTIME_ARS_LIBRARY_UNAVAILABLE",
        "RUNTIME_INVALID_ARS_LIBRARY_CONFIG",
        "collapse_library_turn_status",
    ],
)
def test_the_retired_surface_is_gone_from_the_seam_and_the_package(name: str) -> None:
    assert not hasattr(seam, name), name
    assert not hasattr(spine, name), name
    assert name not in spine.__all__, name


def test_the_seam_exports_exactly_the_migration_surface() -> None:
    assert sorted(seam.__all__) == [
        "ARS_LIBRARY_CONFIG_TYPE",
        "ARS_LIBRARY_STABLE_CODES",
        "LIBRARY_MIGRATION_MESSAGE",
        "RUNTIME_LIBRARY_BACKEND_RETIRED",
        "SUPPORTED_SUPERVISOR_BACKENDS",
        "is_retired_library_config",
        "library_backend_retired",
    ]
    for name in seam.__all__:
        assert hasattr(seam, name), name


def test_the_seam_emulates_nothing_and_falls_back_to_nothing() -> None:
    src = MIGRATION_SEAM.read_text(encoding="utf-8")
    # No import of the producer distribution, lazy or otherwise.
    assert re.search(r"(?m)^\s*(import|from)\s+agent_run_supervisor", src) is None
    # No CLI / package-manager / shell indirection reintroduced as a fallback.
    for launcher in ("acpx", "npx", "subprocess", "os.system", "popen"):
        assert launcher not in src.lower(), launcher
    # The one turn backend the factory allowlist admits is the socket adapter.
    from sachima_supervisor.runtime_spine import supervisor_turn_backend as turns

    assert [kind for kind, _module, _attr in turns._BACKEND_FACTORY_ALLOWLIST] == ["arsd"]


# --------------------------------------------------------------------------- #
# C. B-10 — the retired-module guard (P5-d)
# --------------------------------------------------------------------------- #
def test_no_retired_agent_run_supervisor_module_references() -> None:
    """No Sachima path outside the retirement seam names a removed module.

    Comments and docstrings count: a stale reference in prose is how a reader
    learns that a dead path still exists, and it is how a partial retirement
    survives review. The migration seam is the single exception, because
    naming what went away is the entire point of a migration message.
    """

    offenders: list[str] = []
    for path in _guarded_sources():
        if path.resolve() == MIGRATION_SEAM:
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _ATTRIBUTE_RE.search(line) or _FROM_IMPORT_RE.search(line):
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number}: {line.strip()}"
                )
    assert offenders == [], "retired agent_run_supervisor modules referenced:\n" + "\n".join(
        offenders
    )


def test_the_guard_is_not_vacuous() -> None:
    """It scans real files, and it really does match the retired names.

    A guard that silently scanned nothing, or whose pattern matched nothing,
    would pass forever. Both halves are checked here: the file sweep is
    non-empty and covers all four trees, and the seam — the one file the guard
    exempts — is a file the pattern would otherwise have caught.
    """

    sources = _guarded_sources()
    assert len(sources) > 100
    for tree in GUARDED_TREES:
        assert any(
            str(path.relative_to(REPO_ROOT)).startswith(tree + "/") for path in sources
        ), tree

    seam_text = MIGRATION_SEAM.read_text(encoding="utf-8")
    matched = {match.group(1) for match in _ATTRIBUTE_RE.finditer(seam_text)}
    assert matched == set(RETIRED_MODULES), matched

    # The surviving modules Sachima really does consume are NOT matched.
    for survivor in (
        "agent_run_supervisor.session",
        "agent_run_supervisor.arsd.client",
        "agent_run_supervisor.arsd.protocol",
        "agent_run_supervisor.native_acp.spec",
        "agent_run_supervisor.exit_classifier",
    ):
        assert _ATTRIBUTE_RE.search(survivor) is None, survivor


# --------------------------------------------------------------------------- #
# D. The roadmap must not point at what P5 deleted
# --------------------------------------------------------------------------- #
_DOC_PATH_RE = re.compile(
    r"`((?:scripts|sachima_supervisor|gateway|tools|tests)/[A-Za-z0-9_./-]+\.py)`"
)


def test_roadmap_docs_name_no_deleted_source_path() -> None:
    """A retirement that leaves a live-looking pointer behind is half done.

    The roadmap is where an operator looks up "which file does this?", so a
    path that no longer exists is worse than no path: it reads as current.
    Retired work is described as retired, and pointed at the plan that retired
    it — never at a file that is gone.
    """

    roadmap = REPO_ROOT / "docs" / "roadmap"
    offenders: list[str] = []
    scanned = 0
    for doc in sorted(roadmap.glob("*.md")):
        scanned += 1
        for line_number, line in enumerate(
            doc.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for match in _DOC_PATH_RE.finditer(line):
                if not (REPO_ROOT / match.group(1)).exists():
                    offenders.append(f"{doc.name}:{line_number}: {match.group(1)}")

    assert scanned >= 3, "the roadmap sweep found no documents to scan"
    assert offenders == [], "roadmap points at deleted source:\n" + "\n".join(offenders)


def test_the_guard_would_catch_a_deleted_path() -> None:
    """Non-vacuity: the pattern really matches a repo path in a backtick span."""

    live = "see `sachima_supervisor/runtime_spine/arsd_supervisor_backend.py` for the backend"
    dead = "see `scripts/sachima_phase_e2_persistent_session_smoke.py` for the smoke"

    live_match = _DOC_PATH_RE.search(live)
    assert live_match is not None
    assert (REPO_ROOT / live_match.group(1)).exists()

    dead_match = _DOC_PATH_RE.search(dead)
    assert dead_match is not None
    assert not (REPO_ROOT / dead_match.group(1)).exists()
