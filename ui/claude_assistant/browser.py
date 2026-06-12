"""ui/claude_assistant/browser.py — Login worker cho Claude Assistant."""
from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

CLAUDE_URL = "https://claude.ai"


def _get_paths():
    from paths import APP_DIR
    base = Path(APP_DIR) / "claude_data"
    base.mkdir(parents=True, exist_ok=True)
    storage  = base / "storage_state.json"
    profile  = base / "browser_profile"
    profile.mkdir(parents=True, exist_ok=True)
    return storage, profile


def is_logged_in() -> bool:
    storage, _ = _get_paths()
    return storage.exists()


def logout() -> None:
    import shutil
    storage, profile = _get_paths()
    for p in (storage, profile):
        if p.is_file():
            p.unlink(missing_ok=True)
        elif p.is_dir():
            shutil.rmtree(p, ignore_errors=True)


class LoginWorker(QThread):
    done  = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._event = threading.Event()

    def confirm(self):
        """Gọi khi user bấm 'Lưu đăng nhập' — báo worker lưu session."""
        self._event.set()

    def run(self):
        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

            from playwright.sync_api import sync_playwright

            storage, profile = _get_paths()

            with sync_playwright() as pw:
                ctx = pw.chromium.launch_persistent_context(
                    user_data_dir=str(profile),
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--password-store=basic",
                    ],
                    ignore_default_args=["--enable-automation"],
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(CLAUDE_URL)

                # Chờ user bấm "Lưu đăng nhập" trong app
                self._event.wait()

                ctx.storage_state(path=str(storage))
                try:
                    storage.chmod(0o600)
                except Exception:
                    pass
                ctx.close()

            self.done.emit()

        except Exception as e:
            self.error.emit(str(e))
