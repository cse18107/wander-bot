"""MCP client wiring.

Loads tools from the standalone Wanderbot MCP server via ``MultiServerMCPClient``
and converts them into LangGraph-compatible tools. The same agent then uses local
and remote (MCP) tools transparently.
"""

from __future__ import annotations

import shlex

from langchain_core.tools import BaseTool

from wanderbot.config import Settings, get_settings
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)


def _server_spec(settings: Settings) -> dict:
    parts = shlex.split(settings.mcp_server_cmd)
    return {
        "travel": {
            "command": parts[0],
            "args": parts[1:],
            "transport": "stdio",
        }
    }


async def load_mcp_tools(settings: Settings | None = None) -> list[BaseTool]:
    """Spawn the MCP server over stdio and return its tools as LangChain tools."""
    settings = settings or get_settings()
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(_server_spec(settings))
    tools = await client.get_tools()
    log.info("mcp_tools_loaded", count=len(tools), names=[t.name for t in tools])
    return tools
