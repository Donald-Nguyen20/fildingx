"""ui/claude_assistant/agent.py — Tạo ClaudeAgentOptions cho claude_agent_sdk."""
from __future__ import annotations

from pathlib import Path
from claude_agent_sdk import ClaudeAgentOptions


def make_options(
    system_prompt: str = "",
    allowed_tools: list[str] | None = None,
    cwd: str | None = None,
    db_path: str = "",
) -> ClaudeAgentOptions:
    from paths import APP_DIR
    if db_path:
        # DB mode: dùng Bash để chạy db_query.py, bỏ file-browsing tools
        tools = allowed_tools or ["Bash", "WebSearch", "WebFetch"]
    else:
        tools = allowed_tools or ["Read", "Glob", "Grep", "WebSearch", "WebFetch"]
    return ClaudeAgentOptions(
        system_prompt=system_prompt or "Bạn là trợ lý thông minh, trả lời bằng tiếng Việt.",
        allowed_tools=tools,
        permission_mode="bypassPermissions",
        cwd=cwd or APP_DIR,
        max_turns=30,
    )
