"""
Tests for Issue #4 — the sandbox terminal's shell abstraction. The persistent
shell's command wrapper (`{ command; } > out 2> err`, `$?`, `pwd`) is POSIX
shell syntax; these tests verify a POSIX-capable shell is always what
actually gets used, and that the cmd.exe-only fallback is refused with a
clear error rather than silently fed the POSIX wrapper.
"""
from __future__ import annotations

import sys

import pytest

from backend.services.sandbox_manager import (
    PersistentShellSession,
    ShellKind,
    UnsupportedShellError,
    find_shell_command,
)


def test_find_shell_command_returns_shell_kind_tuple():
    argv, kind = find_shell_command()
    assert isinstance(argv, list) and len(argv) > 0
    assert isinstance(kind, ShellKind)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific shell resolution")
def test_find_shell_command_resolves_posix_shell_on_this_machine():
    """This dev environment has Git for Windows installed, so resolution
    must prefer it over the cmd.exe fallback."""
    argv, kind = find_shell_command()
    assert kind is ShellKind.POSIX
    assert argv[0].lower().endswith((".exe", "bash", "sh")) or argv[0] in ("bash", "sh")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only shell resolution")
def test_find_shell_command_always_posix_on_linux():
    argv, kind = find_shell_command()
    assert kind is ShellKind.POSIX


@pytest.mark.asyncio
async def test_persistent_shell_session_rejects_cmd_only_shell(monkeypatch, tmp_path):
    """
    Simulates "no POSIX shell available" (e.g. Windows without Git Bash) by
    monkeypatching shell resolution to return the cmd.exe fallback, and
    asserts initialize() refuses to start rather than silently running the
    POSIX command wrapper through cmd.exe.
    """
    import backend.services.sandbox_manager as sandbox_manager_module

    monkeypatch.setattr(
        sandbox_manager_module,
        "find_shell_command",
        lambda: (["cmd.exe"], ShellKind.CMD),
    )

    session = PersistentShellSession(
        session_id="test-session",
        run_id="test-run",
        worktree_path=tmp_path,
        env={},
    )
    with pytest.raises(UnsupportedShellError):
        await session.initialize()
