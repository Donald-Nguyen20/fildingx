"""ui/claude_assistant/worker.py — QThread chạy claude_agent_sdk async generator."""
from __future__ import annotations

import asyncio
import sys

from PySide6.QtCore import QThread, Signal
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage

from ui.claude_assistant.sdk_win_patch import apply_no_console_patch

# Ẩn cửa sổ console của Claude CLI trên Windows
apply_no_console_patch()


class AgentWorker(QThread):
    text_chunk = Signal(str)   # text streaming từng đoạn
    tool_used  = Signal(str)   # tên tool đang dùng
    done       = Signal()
    error      = Signal(str)

    def __init__(self, prompt: str, options: ClaudeAgentOptions):
        super().__init__()
        self._prompt  = prompt
        self._options = options

    def run(self):
        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
            asyncio.run(self._run_async())
        except Exception as e:
            self.error.emit(str(e))

    async def _run_async(self):
        try:
            async for message in query(prompt=self._prompt, options=self._options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if hasattr(block, "text") and block.text:
                            self.text_chunk.emit(block.text)
                        elif hasattr(block, "name"):
                            self.tool_used.emit(block.name)
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))
