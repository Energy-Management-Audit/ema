"""The MCP surface: fourteen tools, their schemas, no human action (R14)."""

import ast
import tomllib
from pathlib import Path
from typing import Any

from mcp import ClientSession
from tests.audit_replay import audit_job_with_facts
from tests.mcp_client import structured, with_client

from ema import __version__
from ema.core.review import fields
from ema.core.workspace import Workspace
from ema.mcp.server import INSTRUCTIONS, build_server

ROOT = Path(__file__).resolve().parents[2]
READ: dict[str, Any] = {"readOnlyHint": True}
WRITE: dict[str, Any] = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
STATUSES = [
    "pending",
    "uncertain",
    "accepted",
    "corrected",
    "rejected",
    "conflict",
    "missing",
    "needs_confirmation",
]
TOOLS: dict[str, tuple[str, dict[str, Any], list[str], list[str]]] = {
    "workspace_info": (
        "Workspace folder, number of jobs and the folders input files must be in.",
        READ,
        [],
        [],
    ),
    "job_list": ("List the jobs in the workspace.", READ, [], []),
    "job_status": ("A job's state, revision and stage runs.", READ, ["job"], ["job"]),
    "job_fields": (
        "A job's review fields with their values, evidence ids and revisions; "
        "optionally filtered by status.",
        READ,
        ["job", "status"],
        ["job"],
    ),
    "job_decide": (
        "Record a review decision on one field (accept, correct, reject, choose) "
        "at the field's current revision.",
        WRITE,
        ["job", "field_id", "action", "on_revision", "value", "alternative"],
        ["job", "field_id", "action", "on_revision"],
    ),
    "job_log": ("The job's decision log (Jurnal).", READ, ["job"], ["job"]),
    "job_checks": (
        "Readiness of the job: what blocks a draft or a final export.",
        READ,
        ["job"],
        ["job"],
    ),
    "audit_sections": ("Status of every audit section.", READ, ["job"], ["job"]),
    "audit_draft_section": (
        "Draft one audit section of chapter 2 or 3 from recorded facts, using recorded AI "
        "responses, or the live model when none are given and the live-AI switch is on.",
        WRITE,
        ["job", "section", "draft_recording", "support_recording", "recording"],
        ["job", "section"],
    ),
    "audit_visit": ("Register grouped meter and thermal visit photos.", WRITE, ["job"], ["job"]),
    "audit_readings": (
        "Read visit photos from a recording; live vision is disabled.",
        WRITE,
        ["job", "recording"],
        ["job"],
    ),
    "audit_measurements": (
        "Compose chapter-five measurements from confirmed readings.",
        WRITE,
        ["job"],
        ["job"],
    ),
    "audit_measures": (
        "Read the audit measures form and prepare chapter 6.",
        WRITE,
        ["job"],
        ["job"],
    ),
    "piee_generate": (
        "Create a PIEE job from an Anexa 2-3 (and optional Necesar info, Prelucrare date, "
        "previous PIEE) and generate its draft. Never produces a final.",
        WRITE,
        ["client", "year", "anexa", "necesar", "prelucrare", "previous_piee"],
        ["client", "year", "anexa"],
    ),
}
HUMAN_ONLY = {
    "approve_final",
    "export",
    "set_status",
    "patch_sections",
    "undo",
    "confirm_client",
    "start_word_render",
    "write_report",
    "backup",
    "restore",
}


def _enum(schema: dict[str, Any]) -> list[str]:
    options = schema.get("anyOf", [schema])
    return next(option["enum"] for option in options if "enum" in option)


def test_sdk_pin() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "mcp==1.30.0" in project["dependencies"]


def test_tools_match_the_contract_exactly(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")

    async def listed(client: ClientSession) -> Any:
        return await client.list_tools()

    tools = {tool.name: tool for tool in with_client(ws, listed).tools}

    assert list(tools) == list(TOOLS)
    for name, (description, annotations, properties, required) in TOOLS.items():
        tool = tools[name]
        assert tool.description == description, name
        assert tool.annotations is not None
        assert tool.annotations.model_dump(exclude_none=True) == annotations, name
        assert list(tool.inputSchema.get("properties", {})) == properties, name
        assert tool.inputSchema.get("required", []) == required, name
    assert _enum(tools["job_fields"].inputSchema["properties"]["status"]) == STATUSES
    assert _enum(tools["job_decide"].inputSchema["properties"]["action"]) == [
        "accept",
        "correct",
        "reject",
        "choose",
    ]


def test_server_identity_and_instructions(tmp_path: Path) -> None:
    server = build_server(Workspace(tmp_path / "ws"), ())
    options = server._mcp_server.create_initialization_options()  # pyright: ignore[reportPrivateUsage]

    assert (options.server_name, options.server_version) == ("ema", __version__)
    assert options.instructions == INSTRUCTIONS
    assert INSTRUCTIONS == (
        "Ema prepares energy-audit paperwork. Through these tools an agent can generate a PIEE "
        "draft, review fields and draft audit sections from recorded facts. Exporting a final "
        "document, marking a section done or n/a, undoing decisions and deleting are a human's "
        "actions in the Ema app and are not available here. Input files must be inside one of "
        "the folders listed by workspace_info."
    )


def test_mcp_source_never_acts_as_user_nor_imports_human_actions() -> None:
    for path in sorted((ROOT / "src" / "ema" / "mcp").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            assert not (isinstance(node, ast.Constant) and node.value == "user"), path.name
            if isinstance(node, ast.ImportFrom):
                imported = {alias.name for alias in node.names}
                assert not imported & HUMAN_ONLY, (path.name, imported & HUMAN_ONLY)


def test_decisions_are_recorded_as_the_agent(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    field = fields(ws, job)[0]

    async def body(client: ClientSession) -> tuple[dict[str, Any], dict[str, Any]]:
        decided = await client.call_tool(
            "job_decide",
            {"job": job, "field_id": field.id, "action": "accept", "on_revision": field.revision},
        )
        return structured(decided), structured(await client.call_tool("job_log", {"job": job}))

    decision, journal = with_client(ws, body)

    assert decision["actor"] == "agent"
    assert [entry["actor"] for entry in journal["decisions"]] == ["agent"]
