import os

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

SOCKET_MCP_PACKAGE = "@socketsecurity/mcp@latest"


def socket_mcp_config(api_token: str | None = None) -> dict:
    token = api_token or os.getenv("SOCKET_API_TOKEN") or os.getenv("SOCKET_API_KEY")
    env = {}
    if token:
        env["SOCKET_API_TOKEN"] = token
    return {
        "socket-mcp": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", SOCKET_MCP_PACKAGE],
            "env": env,
        }
    }


async def socket_tools(api_token: str | None = None):
    client = MultiServerMCPClient(socket_mcp_config(api_token=api_token))
    return await client.get_tools()
