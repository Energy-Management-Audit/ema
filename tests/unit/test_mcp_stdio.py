"""The real `ema mcp` executable over stdio: the protocol stream is all that reaches stdout."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tests.mcp_client import refusal, structured, text

from ema import __version__

EMA = Path(sys.executable).with_name("ema.exe" if os.name == "nt" else "ema")
OUTSIDE = "Fișierul este în afara directoarelor de import."


def _environment(workspace: Path) -> dict[str, str]:
    return {**os.environ, "EMA_WORKSPACE": str(workspace)}


def test_stdio_session_lists_and_calls_tools(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"synthetic")
    parameters = StdioServerParameters(command=str(EMA), args=["mcp"], env=_environment(workspace))
    stray: list[object] = []

    async def record(message: object) -> None:
        if isinstance(message, Exception):
            stray.append(message)

    async def session() -> dict[str, Any]:
        with (tmp_path / "stderr.txt").open("w") as errlog:
            async with (
                stdio_client(parameters, errlog=errlog) as (read, write),
                ClientSession(read, write, message_handler=record) as client,
            ):
                initialized = await client.initialize()
                tools = (await client.list_tools()).tools
                info = structured(await client.call_tool("workspace_info", {}))
                arguments = {"client": "c", "year": 2025, "anexa": str(outside)}
                refused = text(await client.call_tool("piee_generate", arguments))
                return {"init": initialized, "tools": tools, "info": info, "refused": refused}

    seen = anyio.run(session)

    assert seen["init"].serverInfo.name == "ema"
    assert seen["init"].serverInfo.version == __version__
    assert len(seen["tools"]) == 10
    assert seen["info"]["workspace"] == str(workspace.resolve())
    assert seen["refused"] == refusal("piee_generate", "path_outside_roots", OUTSIDE)
    assert stray == []
    assert "Traceback" not in (tmp_path / "stderr.txt").read_text()


def test_stdio_stream_is_pure_json_rpc_and_closes_cleanly(tmp_path: Path) -> None:
    process = subprocess.Popen(
        [str(EMA), "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=_environment(tmp_path / "ws"),
    )
    assert process.stdin is not None and process.stdout is not None

    def send(message: dict[str, Any]) -> None:
        assert process.stdin is not None
        process.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
        process.stdin.flush()

    client = {"name": "synthetic", "version": "0"}
    send(
        {
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": client},
        }
    )
    lines = [process.stdout.readline()]
    send({"method": "notifications/initialized"})
    send({"id": 2, "method": "tools/list"})
    lines.append(process.stdout.readline())
    process.stdin.close()
    lines.extend(process.stdout.read().splitlines())
    stderr = process.stderr.read() if process.stderr is not None else ""

    assert process.wait(timeout=30) == 0
    messages = [json.loads(line) for line in lines if line.strip()]
    assert all(message["jsonrpc"] == "2.0" for message in messages)
    assert [message.get("id") for message in messages] == [1, 2]
    assert len(messages[1]["result"]["tools"]) == 10
    assert "Traceback" not in stderr
