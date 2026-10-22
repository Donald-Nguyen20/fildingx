"""ui/claude_assistant/agent.py — Tạo ClaudeAgentOptions cho claude_agent_sdk."""
from __future__ import annotations

from pathlib import Path
from claude_agent_sdk import ClaudeAgentOptions

from ui.claude_assistant.cli_locator import find_claude_cli


def make_options(
    system_prompt: str = "",
    allowed_tools: list[str] | None = None,
    cwd: str | None = None,
    db_path: str = "",
    dcs_folder: str = "",
) -> ClaudeAgentOptions:
    from paths import APP_DIR
    if db_path or dcs_folder:
        # DB mode: dùng Bash để chạy db_query.py / logic_query.py, bỏ file-browsing
        # tools. Folder logic cũng cần Bash — không có thì công cụ tra logic vô dụng.
        tools = allowed_tools or ["Bash", "WebSearch", "WebFetch"]
    else:
        tools = allowed_tools or ["Read", "Glob", "Grep", "WebSearch", "WebFetch"]
    return ClaudeAgentOptions(
        system_prompt=system_prompt or "Bạn là trợ lý thông minh, trả lời bằng tiếng Việt.",
        allowed_tools=tools,
        permission_mode="bypassPermissions",
        cwd=cwd or APP_DIR,
        max_turns=30,
        # The same CLI the Login button signs in with; None lets the SDK
        # search for itself and raise its own "not found" explanation.
        cli_path=find_claude_cli() or None,
    )
