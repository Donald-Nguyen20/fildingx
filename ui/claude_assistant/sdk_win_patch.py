"""ui/claude_assistant/sdk_win_patch.py

Ẩn cửa sổ console đen của Claude Code CLI trên Windows.

claude_agent_sdk spawn process `claude` qua `anyio.open_process(...)` nhưng không
truyền `creationflags`, nên trên Windows nó bung 1 cửa sổ console. Ta wrap lại
`anyio.open_process` để chèn cờ CREATE_NO_WINDOW. Không ảnh hưởng các nền tảng khác.
"""
from __future__ import annotations

import sys


def apply_no_console_patch() -> None:
    """Idempotent — gọi nhiều lần vẫn an toàn. Chỉ tác động trên Windows."""
    if sys.platform != "win32":
        return

    import subprocess
    import anyio

    _orig = anyio.open_process
    if getattr(_orig, "_no_window_patched", False):
        return

    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    async def _patched(command, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | create_no_window
        return await _orig(command, **kwargs)

    _patched._no_window_patched = True  # type: ignore[attr-defined]
    anyio.open_process = _patched
