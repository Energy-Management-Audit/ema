"""The frozen build copies exactly the package metadata in packaging/metadata.txt (ADR 0001).

A frozen one-folder bundle carries no distribution metadata unless the spec copies it, and it
must not rely on entry points. Each subprocess empties importlib.metadata down to the listed
names, then imports the CLI and lists the MCP tools in memory.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROBE = r"""
import importlib.metadata as metadata
import re
import sys
import tempfile
from pathlib import Path

allowed = set(sys.argv[1:])
discover = metadata.Distribution.discover


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def listed(cls, **kwargs):
    return (item for item in discover(**kwargs) if canonical(item.name) in allowed)


metadata.Distribution.discover = classmethod(listed)
metadata.entry_points = lambda **_: metadata.EntryPoints(())
metadata.distributions = lambda **_: iter(())
for name in ("pytest", "ema", "pydantic"):
    if name not in allowed:
        try:
            metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
        raise SystemExit(f"metadata of {name} is still visible")
assert not list(metadata.entry_points()) and not list(metadata.distributions())

import anyio
from mcp.shared.memory import create_connected_server_and_client_session

import ema.cli
from ema.core.workspace import Workspace
from ema.mcp.server import build_server


async def main():
    server = build_server(Workspace(Path(tempfile.mkdtemp())), ())
    async with create_connected_server_and_client_session(server) as client:
        return len((await client.list_tools()).tools)


print(anyio.run(main))
"""


def _listed() -> list[str]:
    lines = (ROOT / "packaging" / "metadata.txt").read_text(encoding="utf-8").splitlines()
    return [line.split("#", 1)[0].strip() for line in lines if line.split("#", 1)[0].strip()]


def _probe(names: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", PROBE, *names],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
        check=False,
    )


def test_metadata_list_and_readme_match_the_contract() -> None:
    assert _listed() == ["httpx2", "mcp"]
    readme = (ROOT / "packaging" / "README.md").read_text(encoding="utf-8")
    assert (
        "The spec copies the package metadata listed in `metadata.txt` (`copy_metadata`); "
        "a unit test keeps that list exact." in readme
    )


def test_listed_metadata_is_enough() -> None:
    probed = _probe(_listed())

    assert probed.returncode == 0, probed.stderr[-2000:]
    assert probed.stdout.strip() == "11"


@pytest.mark.parametrize("missing", ["httpx2", "mcp"])
def test_each_listed_name_is_needed(missing: str) -> None:
    probed = _probe([name for name in _listed() if name != missing])

    assert probed.returncode != 0
    assert "PackageNotFoundError" in probed.stderr
