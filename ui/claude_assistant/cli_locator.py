"""ui/claude_assistant/cli_locator.py — find the Claude Code CLI Data Brain uses.

A packaged build carries no claude.exe, so on every machine but the one that
built it the CLI has to be found wherever an install put it. The sign-in
console, the sign-in badge and the agent all take the path from here, so they
cannot disagree: a machine must not show "signed in" through one claude.exe
while its questions fail through another.

The search follows claude_agent_sdk's own order and adds one place the SDK
does not look: the claude.exe that npm's package ships beside its claude.cmd
shim. On Windows the shim itself is never returned -- the SDK refuses to spawn
a batch file, and CreateProcess cannot start one by the bare name "claude".

Qt-free on purpose.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_WINDOWS = sys.platform == "win32"
_EXE = "claude.exe" if _WINDOWS else "claude"

# What the "not found" dialog tells the user to run. npm is not offered on
# Windows: it installs the claude.cmd shim the SDK will not spawn.
INSTALL_HINT = (
    "Install it once, in PowerShell (no admin rights needed):\n"
    "    irm https://claude.ai/install.ps1 | iex"
    if _WINDOWS else
    "Install it once:\n"
    "    curl -fsSL https://claude.ai/install.sh | bash"
)


def _is_native(path: str) -> bool:
    """True for an image CreateProcess starts directly; a .cmd/.bat shim is not one."""
    if not _WINDOWS:
        return True
    name = os.path.basename(path).rstrip(". ").lower()
    return name.endswith((".exe", ".com"))


def _existing(path: str | Path) -> str:
    """`path` as a string when it names a file, else ""."""
    p = Path(path)
    return str(p) if p.is_file() else ""


def _bundled() -> str:
    """The claude.exe a claude_agent_sdk wheel carries. Absent in the packaged app."""
    try:
        import claude_agent_sdk
    except Exception:
        return ""
    return _existing(Path(claude_agent_sdk.__file__).parent / "_bundled" / _EXE)


def _beside_npm_shim(shim: str | Path) -> str:
    """The claude.exe that npm's claude.cmd in the same folder hands off to."""
    return _existing(Path(shim).parent / "node_modules" / "@anthropic-ai"
                     / "claude-code" / "bin" / _EXE)


def find_claude_cli() -> str:
    """Absolute path of a runnable Claude Code CLI, or "" when none is installed.

    Looked up afresh on every call -- a handful of stat calls. The native
    installer's folder is probed by path rather than through the PATH this
    process inherited at launch, so a CLI installed while the app is open is
    found on the next click, without restarting the app.
    """
    on_path = shutil.which("claude") or ""
    candidates = [_bundled(), on_path]
    if _WINDOWS:
        candidates.append(shutil.which("claude.exe") or "")
    candidates.append(str(Path.home() / ".local" / "bin" / _EXE))
    if _WINDOWS:
        if on_path:
            candidates.append(_beside_npm_shim(on_path))
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates.append(_beside_npm_shim(Path(appdata) / "npm" / "claude.cmd"))

    for candidate in candidates:
        if candidate and _is_native(candidate):
            found = _existing(candidate)
            if found:
                return found
    return ""
