"""Tests for the ``hermes postinstall`` command.

``postinstall`` is the one-shot bootstrap a pip install needs: pip ships the
Python distribution but not node, a browser engine, ripgrep or ffmpeg, so a
fresh install cannot browse, search or speak until those land.  The command
stamps the install method, ensures each of those programs, and then either
hands over to the setup wizard (no inference provider configured yet) or
reports completion.

Everything external is patched: no dependency is installed, no network is
touched, no wizard is launched, and no real user config is written.  The
handler's own module is imported directly, so the behaviour tests do not
depend on the CLI god-file being importable.
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from hermes_cli.postinstall_cmd import POSTINSTALL_DEPENDENCIES, cmd_postinstall
from hermes_cli.subcommands.postinstall import build_postinstall_parser


# ===========================================================================
# Registration — the command is reachable as ``hermes postinstall``
# ===========================================================================

def _sentinel_handler(args):  # pragma: no cover - only identity is asserted
    return "postinstall-handler"


def _build():
    parser = argparse.ArgumentParser(prog="hermes")
    subparsers = parser.add_subparsers(dest="command")
    build_postinstall_parser(subparsers, cmd_postinstall=_sentinel_handler)
    return parser


class TestRegistration:

    def test_builder_attaches_the_subcommand_and_wires_the_injected_handler(self):
        ns = _build().parse_args(["postinstall"])

        assert ns.command == "postinstall"
        assert ns.func is _sentinel_handler

    def test_subcommand_takes_no_arguments(self):
        """A one-shot bootstrap has nothing to configure."""
        parser = _build()

        with pytest.raises(SystemExit):
            parser.parse_args(["postinstall", "--unexpected"])

    def test_help_names_the_dependencies_it_bootstraps(self):
        parser = _build()
        action = next(
            a for a in parser._subparsers._group_actions[0]._choices_actions
            if a.dest == "postinstall"
        )

        for dep in ("node", "browser", "ripgrep", "ffmpeg"):
            assert dep in action.help

    def test_main_registers_the_real_handler_not_a_stub(self):
        """``main`` must inject the module handler, not shadow it locally."""
        import hermes_cli.main as main
        import hermes_cli.postinstall_cmd as postinstall_cmd

        assert main.cmd_postinstall is postinstall_cmd.cmd_postinstall
        assert main.build_postinstall_parser is build_postinstall_parser

    def test_postinstall_is_a_known_builtin_subcommand(self):
        """Otherwise the pre-parse fast path treats it as a plugin command."""
        from hermes_cli.main import _BUILTIN_SUBCOMMANDS

        assert "postinstall" in _BUILTIN_SUBCOMMANDS

    def test_main_actually_calls_the_builder(self, capsys, monkeypatch):
        """End-to-end: importing the builder is not the same as calling it.

        Every other registration test here passes even if the
        ``build_postinstall_parser(...)`` call is missing from ``main()``.
        This one drives the real argparse tree; ``--help`` makes argparse
        exit before any handler runs, so nothing is installed or launched.
        """
        from hermes_cli.main import main

        monkeypatch.setattr("sys.argv", ["hermes", "postinstall", "--help"])

        with pytest.raises(SystemExit) as exc:
            main()

        assert exc.value.code == 0
        assert "usage: hermes postinstall" in capsys.readouterr().out


# ===========================================================================
# Behaviour
# ===========================================================================

class _Recorder:
    """Captures the calls the handler makes, without performing any of them."""

    def __init__(self, *, provider_configured: bool, ensure_result: bool = True):
        self.provider_configured = provider_configured
        self.ensure_result = ensure_result
        self.stamped: list[str] = []
        self.ensured: list[str] = []
        self.setup_calls: list[object] = []

    def stamp_install_method(self, method, project_root=None):
        self.stamped.append(method)

    def ensure_dependency(self, dep, interactive=True):
        self.ensured.append(dep)
        return self.ensure_result

    def has_any_provider_configured(self):
        return self.provider_configured

    def cmd_setup(self, args):
        self.setup_calls.append(args)


def _run(recorder, args=None):
    """Run the handler with every external effect replaced by ``recorder``."""
    args = args if args is not None else argparse.Namespace(command="postinstall")
    with patch("hermes_cli.config.stamp_install_method", recorder.stamp_install_method), \
         patch("hermes_cli.dep_ensure.ensure_dependency", recorder.ensure_dependency), \
         patch("hermes_cli.main._has_any_provider_configured", recorder.has_any_provider_configured), \
         patch("hermes_cli.main.cmd_setup", recorder.cmd_setup):
        cmd_postinstall(args)
    return args


class TestPostinstallBehaviour:

    def test_stamps_the_install_method_as_pip(self, capsys):
        """Detection has to know this tree was installed by pip, not git."""
        recorder = _Recorder(provider_configured=True)

        _run(recorder)
        capsys.readouterr()

        assert recorder.stamped == ["pip"]

    def test_ensures_every_non_python_dependency_in_order(self, capsys):
        recorder = _Recorder(provider_configured=True)

        _run(recorder)
        capsys.readouterr()

        assert recorder.ensured == ["node", "browser", "ripgrep", "ffmpeg"]
        assert recorder.ensured == list(POSTINSTALL_DEPENDENCIES)

    def test_unconfigured_install_hands_over_to_setup(self, capsys):
        """The whole point: pip user reaches a working agent in one command."""
        recorder = _Recorder(provider_configured=False)

        args = _run(recorder)
        out = capsys.readouterr().out

        assert recorder.setup_calls == [args], "setup must receive the same args namespace"
        assert "Post-install complete." not in out, (
            "completion must not be claimed when setup was just handed the install"
        )

    def test_configured_install_reports_completion_without_launching_setup(self, capsys):
        """A provider is already configured — re-running the wizard would be wrong."""
        recorder = _Recorder(provider_configured=True)

        _run(recorder)
        out = capsys.readouterr().out

        assert recorder.setup_calls == []
        assert "Post-install complete." in out

    def test_a_dependency_that_cannot_be_installed_does_not_abort_the_rest(self, capsys):
        """Best-effort: no ffmpeg must not cost the user the setup handover."""
        recorder = _Recorder(provider_configured=False, ensure_result=False)

        args = _run(recorder)
        capsys.readouterr()

        assert recorder.ensured == list(POSTINSTALL_DEPENDENCIES)
        assert recorder.setup_calls == [args]

    def test_announces_itself_before_doing_any_work(self, capsys):
        recorder = _Recorder(provider_configured=True)

        _run(recorder)
        out = capsys.readouterr().out

        assert "Hermes post-install bootstrap" in out


# ===========================================================================
# Attachment point — the dependency names must stay real
# ===========================================================================

def test_every_bootstrapped_dependency_is_a_known_dep_ensure_target():
    """``ensure_dependency`` silently no-ops on an unknown name.

    An upstream rename would therefore turn this command into a no-op with no
    error at all, so the names are pinned against the checks table itself.
    """
    from hermes_cli.dep_ensure import _DEP_CHECKS

    unknown = [dep for dep in POSTINSTALL_DEPENDENCIES if dep not in _DEP_CHECKS]

    assert not unknown, (
        f"{unknown} are no longer known to hermes_cli.dep_ensure._DEP_CHECKS; "
        "ensure_dependency would silently skip them"
    )
