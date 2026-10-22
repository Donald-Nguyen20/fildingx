"""ui/claude_assistant/worker.py — QThread chạy claude_agent_sdk async generator."""
from __future__ import annotations

import asyncio
import dataclasses
import sys
from collections import deque

import claude_agent_sdk
from PySide6.QtCore import QThread, Signal
from claude_agent_sdk import ProcessError, query, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage

from ui.claude_assistant.sdk_win_patch import apply_no_console_patch

# Ẩn cửa sổ console của Claude CLI trên Windows
apply_no_console_patch()

# When the CLI dies before it answers, the SDK reports only "Command failed
# with exit code 1 ... Check stderr output for details" -- the reason itself
# went to the CLI's stderr, which nothing was reading. Keep its tail so the
# error line can show it.
_STDERR_KEEP = 200        # lines held while the CLI runs
_STDERR_SHOW = 8          # lines appended to the error message
_STDERR_LINE_MAX = 300    # chars per shown line

# ResultError is newer than SDK 0.2.99; with an older SDK nothing matches it.
_ResultError = getattr(claude_agent_sdk, "ResultError", ())


def _error_text(exc: Exception, stderr_tail: deque[str]) -> str:
    """The error message, with the CLI's last stderr lines when it failed on its own.

    A ResultError already carries the CLI's own explanation, so only a bare
    ProcessError gets the tail -- in place of the SDK's placeholder line.
    """
    msg = str(exc)
    if not isinstance(exc, ProcessError) or isinstance(exc, _ResultError) or not stderr_tail:
        return msg
    head = msg.split("\nError output:", 1)[0]
    lines = [ln if len(ln) <= _STDERR_LINE_MAX else ln[:_STDERR_LINE_MAX] + "…"
             for ln in list(stderr_tail)[-_STDERR_SHOW:]]
    return head + "\nClaude CLI output:\n" + "\n".join(lines)


class AgentWorker(QThread):
    text_chunk = Signal(str)   # text streaming từng đoạn
    tool_used  = Signal(str)   # tên tool đang dùng
    # tool_used says only which tool ran; tool_call carries the arguments too,
    # so web research can audit the URLs WebFetch actually opened against the
    # ones the answer cites. Both fire -- tool_used keeps its existing slots.
    tool_call  = Signal(str, dict)
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
        stderr_tail: deque[str] = deque(maxlen=_STDERR_KEEP)
        options = self._options
        if options.stderr is None:
            # A copy, so the caller's options are left as they were given.
            options = dataclasses.replace(options, stderr=stderr_tail.append)
        try:
            async for message in query(prompt=self._prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if hasattr(block, "text") and block.text:
                            self.text_chunk.emit(block.text)
                        elif hasattr(block, "name"):
                            self.tool_used.emit(block.name)
                            args = getattr(block, "input", None)
                            self.tool_call.emit(
                                block.name, args if isinstance(args, dict) else {})
            self.done.emit()
        except Exception as e:
            self.error.emit(_error_text(e, stderr_tail))
