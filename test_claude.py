import asyncio
import sys

# Fix Windows terminal encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from claude_agent_sdk import query, ClaudeAgentOptions


async def main():
    async for message in query(
        prompt="Nói xin chào bằng tiếng Việt",
        options=ClaudeAgentOptions(allowed_tools=[], max_turns=1),
    ):
        print(message)


asyncio.run(main())
