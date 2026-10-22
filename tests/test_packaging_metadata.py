"""Independent core/optional dependency and reviewed CVE policies."""
import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_test_dependencies_are_group_only_in_manifest_and_lock():
    manifest = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    hermes = next(package for package in lock["package"] if package["name"] == manifest["project"]["name"])
    assert manifest["tool"]["uv"]["default-groups"] == []
    assert "dev" in manifest["dependency-groups"]
    assert "dev" not in manifest["project"]["optional-dependencies"]
    assert "dev" in hermes["dev-dependencies"]
    assert "dev" not in hermes.get("optional-dependencies", {})


def test_core_and_optional_speech_dependencies():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    core = {Requirement(dep).name for dep in project["dependencies"]}
    assert "packaging" in core  # Runtime code imports it directly, not transitively.
    assert "faster-whisper" not in core
    assert "faster-whisper" in {
        Requirement(dep).name for dep in project["optional-dependencies"]["stt-whisper"]
    }


def test_starlette_server_pins_and_lock_exclude_cve_2026_48710():
    # BadHost's reviewed fixed boundary is independent of today's exact pin.
    floor = Version("1.0.1")
    metadata = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    found = set()
    for extra, specs in metadata["project"]["optional-dependencies"].items():
        for requirement in map(Requirement, specs):
            if requirement.name != "starlette":
                continue
            pins = list(requirement.specifier)
            assert len(pins) == 1 and pins[0].operator == "==", (extra, requirement)
            assert Version(pins[0].version) >= floor, (extra, requirement)
            found.add(extra)
    assert {"web", "mcp", "computer-use"} <= found
    dev = [req for req in map(Requirement, metadata["dependency-groups"]["dev"])
           if req.name == "starlette"]
    assert len(dev) == 1
    pins = list(dev[0].specifier)
    assert len(pins) == 1 and pins[0].operator == "==" and Version(pins[0].version) >= floor
    versions = [Version(row["version"]) for row in lock["package"] if row["name"] == "starlette"]
    assert versions and all(version >= floor for version in versions)


# ===========================================================================
# agent-run-supervisor — one pin, three places (Sachima)
# ===========================================================================

def _distribution_name(requirement: str) -> str:
    """Extract the PEP 508 distribution name from a requirement string.

    Robust to markers (``; python_version < '3.12'``), direct references
    (``name @ https://...``), extras (``name[extra]``) and every version
    operator (``==``, ``>=``, ``<=``, ``~=``, ``!=``, ``<``, ``>``), so a
    future dep declared with any valid specifier shape doesn't silently
    mis-parse here.
    """
    spec = requirement.split(";", 1)[0]  # drop environment markers
    spec = spec.split("@", 1)[0]  # drop direct-reference URLs
    spec = spec.split("[", 1)[0]  # drop extras
    spec = re.split(r"[=<>!~]", spec, maxsplit=1)[0]  # drop any version operator
    return spec.strip().lower()


def _canonical(name: str) -> str:
    # PEP 503 normalization so e.g. discord.py / discord-py compare equal.
    return re.sub(r"[-_.]+", "-", name).lower()


def _locked_versions(package: str) -> set[str]:
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {
        pkg["version"]
        for pkg in lock.get("package", [])
        if _canonical(pkg["name"]) == _canonical(package)
    }


def test_agent_run_supervisor_pin_consistent_across_pyproject_and_checker():
    """The agent-run-supervisor pin has exactly one source of truth.

    The external agent-run-supervisor AGENT execution/event-stream subsystem is
    consumed only as an exact-pinned PyPI distribution: declared in the
    dedicated ``agent-run-supervisor`` extra (opt-in provisioning) and mirrored
    into the ``dev`` dependency group (so a ``--group dev`` sync installs the
    distribution and the offline contract drift locks run against it instead
    of skipping; upstream moved dev tooling from an extra to
    ``[dependency-groups]``). The runtime checker constant
    ``EXPECTED_AGENT_RUN_SUPERVISOR_VERSION`` must equal that pin, and the
    package must stay out of core dependencies and out of ``[all]``. A bump
    that misses any of these places fails here instead of drifting.
    """
    from sachima_supervisor import EXPECTED_AGENT_RUN_SUPERVISOR_VERSION

    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    pin = f"agent-run-supervisor=={EXPECTED_AGENT_RUN_SUPERVISOR_VERSION}"

    assert extras.get("agent-run-supervisor") == [pin], (
        "pyproject must declare the dedicated extra "
        f"agent-run-supervisor = [{pin!r}] (exact pin, no ranges)"
    )
    assert pin in data.get("dependency-groups", {}).get("dev", []), (
        f"the dev dependency group must mirror {pin!r} so a dev sync installs the distribution"
    )

    core_names = {_distribution_name(dep) for dep in data["project"]["dependencies"]}
    assert "agent-run-supervisor" not in core_names, (
        "agent-run-supervisor is opt-in (default-off supervisor spine) and "
        "must never be a core dependency"
    )
    assert not any(
        "agent-run-supervisor" in spec for spec in extras.get("all", [])
    ), "agent-run-supervisor must stay out of the [all] extra"


def test_locked_agent_run_supervisor_matches_expected_pin():
    """The committed uv.lock must resolve agent-run-supervisor to the exact pin.

    pyproject declares the pin, but hash-verified installs (``uv sync
    --locked`` / ``--frozen``) pull what the lockfile resolved. A pin bump (or
    the initial extra introduction) without a matching lock entry fails here
    instead of shipping a stale or missing resolution.
    """
    from sachima_supervisor import EXPECTED_AGENT_RUN_SUPERVISOR_VERSION

    assert _locked_versions("agent-run-supervisor") == {
        EXPECTED_AGENT_RUN_SUPERVISOR_VERSION
    }, (
        "uv.lock must resolve agent-run-supervisor to exactly "
        f"{EXPECTED_AGENT_RUN_SUPERVISOR_VERSION} (found "
        f"{sorted(_locked_versions('agent-run-supervisor')) or 'nothing'})"
    )


def test_agent_run_supervisor_exclude_newer_cutoff_admits_the_locked_release():
    """The date policy must actually admit the pinned release.

    agent-run-supervisor pin advances have landed inside the relative
    ``exclude-newer`` window before, so the pin was installable only while a
    per-package cutoff admitted it. Every dependency is now held to one
    release-age window with no per-package exemption
    (``test_every_dependency_is_held_to_one_three_day_release_age``), so that
    window is the only thing that admits the reviewed release: every locked
    artifact of the pinned version must have been uploaded at least one window
    ago. Assert it explicitly here so the one pin Sachima owns cannot move to a
    release the window still filters, or regain an exemption, without a named
    failure.
    """
    from datetime import UTC, datetime, timedelta

    from sachima_supervisor import EXPECTED_AGENT_RUN_SUPERVISOR_VERSION

    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "agent-run-supervisor" not in data["tool"]["uv"].get("exclude-newer-package", {}), (
        "agent-run-supervisor must be admitted by the shared release-age window, "
        "not by a per-package exemption"
    )

    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    span = lock["options"].get("exclude-newer-span", "")
    window = re.fullmatch(r"P(\d+)D", span)
    assert window, f"uv.lock records no day-based exclude-newer-span (found {span!r})"
    cutoff = datetime.now(UTC) - timedelta(days=int(window.group(1)))

    (package,) = [
        pkg
        for pkg in lock["package"]
        if _canonical(pkg["name"]) == "agent-run-supervisor"
        and pkg["version"] == EXPECTED_AGENT_RUN_SUPERVISOR_VERSION
    ]
    for artifact in (package["sdist"], *package["wheels"]):
        uploaded = datetime.fromisoformat(artifact["upload-time"])
        assert uploaded <= cutoff, (
            f"locked agent-run-supervisor {EXPECTED_AGENT_RUN_SUPERVISOR_VERSION} artifact "
            f"{artifact['url'].rsplit('/', 1)[-1]} was uploaded {artifact['upload-time']}, "
            f"inside the {span} release-age window"
        )


#: Directories a repo-wide source scan skips: not our code, or not code.
_SCAN_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
    }
)


def _tracked_python_sources():
    """Every first-party Python source file in the tree."""

    for path in REPO_ROOT.rglob("*.py"):
        if _SCAN_SKIP_DIRS.intersection(path.relative_to(REPO_ROOT).parts):
            continue
        yield path


def _import_patterns(dotted: str, text: str):
    """Every real import of ``dotted`` in ``text``.

    Import statements only, not any mention: a module named inside a docstring
    or in a negative assertion (``assert "X" not in source``) is the seam
    being *forbidden*, not used, and flagging those would make the guard fire
    on the code that enforces it.
    """

    escaped = re.escape(dotted)
    leaf = escaped.rsplit(r"\.", 1)[-1]
    for pattern in (
        rf"(?m)^\s*import\s+{escaped}\b",
        rf"(?m)^\s*from\s+{escaped}\b",
        rf"(?m)^\s*from\s+[\w.]+\s+import\s+[^\n]*\b{leaf}\b",
        rf"import_module\(\s*[\"']{escaped}[\"']",
    ):
        yield from re.finditer(pattern, text)


#: A source checkout of agent-run-supervisor reached by path rather than by
#: distribution. Each pattern is a way that channel has actually been opened:
#: a sys.path/PYTHONPATH entry pointing at a checkout, or a repo-relative
#: import root for the package.
_SOURCE_PATH_PATTERNS = (
    re.compile(r"sys\.path[^\n]*agent[-_]run[-_]supervisor", re.IGNORECASE),
    re.compile(r"PYTHONPATH[^\n]*agent[-_]run[-_]supervisor", re.IGNORECASE),
    re.compile(r"agent[-_]run[-_]supervisor[^\n]*sys\.path", re.IGNORECASE),
    re.compile(r"(?:\.\./|/)[\w./-]*agent-run-supervisor/(?:src|agent_run_supervisor)\b"),
)


def test_no_agent_run_supervisor_source_path_references():
    """The exact-pinned distribution is the only channel to the subsystem.

    A source checkout reached over ``sys.path`` / ``PYTHONPATH`` — or a
    repo-relative import root for it — is a second, unreviewed channel: it
    silently wins over the installed distribution, so the version the daemon
    handshake compares against stops being the version actually running. The
    pin then guarantees nothing. There is one way in, and it is
    ``agent-run-supervisor==EXPECTED_AGENT_RUN_SUPERVISOR_VERSION`` installed
    as a distribution.

    This is a source-level scan on purpose: an import-time check would only
    see the channel once something opened it.
    """
    offenders = []
    for path in _tracked_python_sources():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "agent" not in text:
            continue
        for pattern in _SOURCE_PATH_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}")

    assert offenders == [], (
        "agent-run-supervisor must be reached only as the exact-pinned "
        "distribution — no source checkout, sys.path shim, or PYTHONPATH "
        "entry:\n  " + "\n  ".join(sorted(set(offenders)))
    )


def test_agent_run_supervisor_is_never_a_path_or_editable_dependency():
    """The pin must resolve to a registry release, not to a local directory.

    The same second channel, opened through packaging instead of ``sys.path``:
    a path/editable source declares the distribution name the version check
    trusts while serving whatever happens to be in that directory.
    """
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    data = tomllib.loads(pyproject)
    sources = data.get("tool", {}).get("uv", {}).get("sources", {})
    assert "agent-run-supervisor" not in sources, (
        "[tool.uv.sources] must not redirect agent-run-supervisor to a path, "
        "editable, git or workspace source"
    )

    lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    blocks = [
        block
        for block in lock.split("[[package]]")
        # Line-anchored: a dependency *reference* elsewhere in the lock is
        # `{ name = "agent-run-supervisor" }` and declares no source.
        if re.search(r'^name = "agent-run-supervisor"$', block, re.MULTILINE)
    ]
    assert blocks, "uv.lock declares no agent-run-supervisor package block"
    for block in blocks:
        assert "source = { registry" in block or "source = { url" in block, (
            "uv.lock must resolve agent-run-supervisor from a registry, not "
            "from a directory/editable/git source"
        )
        for forbidden in ("source = { editable", "source = { directory", "source = { git"):
            assert forbidden not in block, (
                f"uv.lock resolves agent-run-supervisor via {forbidden!r} — the "
                "pinned distribution is the only sanctioned channel"
            )


#: Submodules the 0.7.x distribution removed with its legacy library surface.
#: Referencing one is a hard ImportError against the pinned distribution, not
#: a soft degradation, so the reference must not survive anywhere in the tree.
_REMOVED_ARS_SUBMODULES = (
    "agent_run_supervisor.role",
    "agent_run_supervisor.workspace",
    "agent_run_supervisor.session_runtime",
    "agent_run_supervisor.session_inspect",
    "agent_run_supervisor.goal",
    "agent_run_supervisor.hermes_caller",
)


def test_no_removed_agent_run_supervisor_submodule_references_survive():
    """No reference to a submodule 0.7.x removed survives in the tree.

    The in-process ``library`` backend that consumed these is retired, not
    deprecated: there is no shim, no fallback, and no degraded emulation. A
    surviving reference would therefore fail closed at the worst moment — on
    first use against a real daemon — rather than here.
    """
    offenders = []
    for path in _tracked_python_sources():
        if path == Path(__file__):  # this guard names them to forbid them
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "agent_run_supervisor" not in text:
            continue
        for module in _REMOVED_ARS_SUBMODULES:
            for match in _import_patterns(module, text):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line} -> {module}")

    assert offenders == [], (
        "these import agent-run-supervisor submodules removed in 0.7.x:\n  "
        + "\n  ".join(sorted(set(offenders)))
    )


#: The only modules the spine reaches the daemon through. The socket adapter
#: resolves the first one lazily inside its facade; nothing else is consumed.
_CONSUMED_ARS_MODULES = (
    "agent_run_supervisor.arsd.client",
    "agent_run_supervisor.arsd.protocol",
)


def _ars_distribution_installed() -> bool:
    import importlib.metadata

    try:
        importlib.metadata.version("agent-run-supervisor")
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


@pytest.mark.skipif(
    not _ars_distribution_installed(),
    reason=(
        "agent-run-supervisor distribution not installed — provision via "
        "`uv sync --group dev` (or --extra agent-run-supervisor)"
    ),
)
def test_removed_submodule_list_drift_locks_against_the_pinned_distribution():
    """The guard's removed-module list is checked against the real package.

    A static scan can only be as good as its list. With the pinned
    distribution installed, the list is verified from the other side: every
    module named as removed really is absent, and the modules the spine does
    consume really are present. If a future pin restores one of these, the
    list is stale and this fails rather than the guard silently weakening.

    Importing is safe by contract — the adapter opens sockets only when an
    operation is made — so this reaches no daemon.
    """
    import importlib

    for module_name in _CONSUMED_ARS_MODULES:
        module = importlib.import_module(module_name)
        assert module.__name__ == module_name

    client = importlib.import_module("agent_run_supervisor.arsd.client")
    assert isinstance(getattr(client, "ArsdClient", None), type), (
        "agent_run_supervisor.arsd.client.ArsdClient must be a class in the "
        "pinned distribution — the Socket API v3 adapter depends on it"
    )

    still_present = []
    for module_name in _REMOVED_ARS_SUBMODULES:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        except Exception:  # importable but broken is still "present"
            pass
        still_present.append(module_name)

    assert still_present == [], (
        "these are listed as removed in 0.7.x but exist in the installed "
        f"distribution — the guard's list is stale: {still_present}"
    )


def test_the_retired_library_backend_seam_is_absent_not_merely_unused():
    """The retired library seam is deleted, and nothing re-creates it.

    Dropping the fallback means the modules are gone, not that they survive
    unreferenced: a present-but-unused seam is one import away from becoming a
    live second execution path again. Fail-closed is preserved by absence.
    """
    for retired in (
        "sachima_supervisor/runtime_spine/agent_run_supervisor_library_backend.py",
        "sachima_supervisor/supervisor_library.py",
    ):
        assert not (REPO_ROOT / retired).exists(), (
            f"{retired} is a retired library-backend seam and must not exist"
        )

    offenders = []
    for path in _tracked_python_sources():
        if path == Path(__file__):  # this guard names them to forbid them
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for token in (
            "agent_run_supervisor_library_backend",
            "sachima_supervisor.supervisor_library",
        ):
            for match in _import_patterns(token, text):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line} -> {token}")

    assert offenders == [], (
        "the retired library backend must have no surviving importers:\n  "
        + "\n  ".join(sorted(set(offenders)))
    )


def test_every_dependency_is_held_to_one_three_day_release_age():
    """Hermes's deps must be >= 3 days old when locked, exact pins included (Teknium ruling).

    A per-package exemption or date would quietly let a fresh release into the lock; the
    check runs at lock time only, so users never need a mirror that serves upload times.
    """
    manifest = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    uv = manifest["tool"]["uv"]
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert uv["exclude-newer"] == "3 days"
    assert "exclude-newer-package" not in uv
    assert lock["options"].get("exclude-newer-span") == "P3D"
    assert "exclude-newer-package" not in lock["options"]


def test_httpx2_pins_and_lock_exclude_ghsa_7mj9_2mp8_4m2p_family():
    # 2.12.0 is the first httpx2/httpcore2 release clear of GHSA-7mj9-2mp8-4m2p,
    # GHSA-f2fp-rgf2-35cp, GHSA-h4x7-gw46-3wm6, GHSA-pf96-p4fj-6566 and
    # GHSA-8xx6-hgc6-gc2m; the boundary is independent of today's exact pin.
    floor = Version("2.12.0")
    metadata = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    declared = dict(metadata["project"]["optional-dependencies"])
    declared["group:dev"] = metadata["dependency-groups"]["dev"]
    found = set()
    for where, specs in declared.items():
        for requirement in map(Requirement, specs):
            if requirement.name != "httpx2":
                continue
            pins = list(requirement.specifier)
            assert len(pins) == 1 and pins[0].operator == "==", (where, requirement)
            assert Version(pins[0].version) >= floor, (where, requirement)
            found.add(where)
    assert {"mcp", "computer-use", "group:dev"} <= found
    for name in ("httpx2", "httpcore2"):
        versions = [Version(row["version"]) for row in lock["package"] if row["name"] == name]
        assert versions and all(version >= floor for version in versions), (name, versions)
