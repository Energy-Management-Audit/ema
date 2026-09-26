"""Drive the MCP server in memory from sync pytest functions (no asyncio mode is configured)."""

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent

from ema.core.workspace import Workspace
from ema.mcp.server import build_server


def imports_root(ws: Workspace) -> Path:
    folder = ws.root / "imports"
    folder.mkdir(parents=True, exist_ok=True)
    return folder.resolve()


def with_client[T](
    ws: Workspace, body: Callable[[ClientSession], Awaitable[T]], *extra_roots: Path
) -> T:
    roots = (imports_root(ws), *(root.resolve() for root in extra_roots))

    async def main() -> T:
        async with create_connected_server_and_client_session(build_server(ws, roots)) as client:
            return await body(client)

    return anyio.run(main)


def structured(result: CallToolResult) -> dict[str, Any]:
    assert not result.isError, text(result)
    assert result.structuredContent is not None
    return result.structuredContent


def text(result: CallToolResult) -> str:
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


def refusal(tool: str, code: str, message: str) -> str:
    body = json.dumps({"code": code, "message": message}, ensure_ascii=False)
    return f"Error executing tool {tool}: {body}"
