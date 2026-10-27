"""``hermes postinstall`` command handler.

One-shot bootstrap for pip installs.  pip delivers the Python distribution
but none of the external programs Hermes shells out to, so a fresh
``pip install`` lands without node, a browser engine, ripgrep or ffmpeg.
This command closes that gap in one step, then hands straight over to the
setup wizard when the install has no inference provider configured yet —
so a pip user reaches a working agent from a single command.

The handler lives in its own module rather than in ``hermes_cli/main.py``
so it stays importable, and testable, without pulling in the whole CLI
module — the same shape ``fallback_cmd.py`` and ``gateway_enroll.py`` use.
The two helpers that do still live in ``main`` are imported inside the
function, which is how the rest of the package reaches back into it
without creating an import cycle.
"""

from __future__ import annotations

#: The non-Python programs pip cannot provide, in the order they are ensured.
#: Every name must be a package pinned in ``pm/lock.json`` (``agent-browser``
#: brings its Chromium with it); the set is pinned by a test.
POSTINSTALL_DEPENDENCIES = ("node", "agent-browser", "ripgrep", "ffmpeg")


def _stamp_install_method(method: str) -> None:
    """Write the code-scoped ``<install tree>/.install_method`` stamp, best-effort.

    The stamp lives next to the running code (the parent of ``hermes_cli/``),
    not in ``$HERMES_HOME``, so two installs sharing one data directory keep
    their own markers; ``hermes_cli.config.detect_install_method`` reads the
    same file. Upstream ships no stamping helper any more (its installers
    write the marker themselves), so the pip bootstrap owns this writer. A
    read-only install tree (an immutable image) silently no-ops and detection
    falls back to its other signals.
    """
    from hermes_cli.config import get_project_root

    try:
        root = get_project_root()
        root.mkdir(parents=True, exist_ok=True)
        (root / ".install_method").write_text(method + "\n", encoding="utf-8")
    except OSError:
        pass


def _ensure_dependencies() -> None:
    """Ensure every dependency through the package system, best-effort.

    Deliberately not short-circuited: a machine that already has ripgrep but
    no ffmpeg should still get ffmpeg, and a dependency that cannot be
    installed must not block the ones after it or the setup handover.
    """
    import pm
    from pm.install import lazy_installs_allowed, sealed

    # Sealed payloads ship their tools; the lazy-install policy (config or the
    # Docker/test bridge) means the user asked Hermes not to fetch on its own.
    if sealed() or not lazy_installs_allowed():
        print("  Dependency installs are disabled here; add them with `hermes pm install <name>`.")
        return
    for name in POSTINSTALL_DEPENDENCIES:
        try:
            pm.ensure(name, explicit=True)
        except (pm.InstallError, OSError) as exc:
            print(f"  ⚠ {name} was not installed: {exc}")
            print(f"    Retry with: hermes pm install {name}")


def cmd_postinstall(args) -> None:
    """One-shot bootstrap for pip users: install non-Python deps + run setup."""
    from hermes_cli.main import _has_any_provider_configured, cmd_setup

    _stamp_install_method("pip")

    print("⚕ Hermes post-install bootstrap")
    print()

    _ensure_dependencies()

    if not _has_any_provider_configured():
        print()
        cmd_setup(args)
    else:
        print()
        print("✓ Post-install complete.")
