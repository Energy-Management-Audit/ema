"""An agent with no UI: a PIEE draft and an audit section draft, entirely through MCP tools."""

from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession
from tests.audit_replay import (
    CH2_DRAFT,
    audit_job_with_facts,
    draft_recording,
    support_recording,
)
from tests.mcp_client import imports_root, refusal, structured, text, with_client
from tests.piee_seams import stub_piee_seams, synthetic_inputs

from ema.core.workspace import Workspace

EXPORTS = {"export", "approve", "final", "undo", "delete", "done"}


def test_piee_draft_journey(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_piee_seams(monkeypatch, tmp_path)
    ws = Workspace(tmp_path / "ws")
    anexa, necesar, prelucrare = synthetic_inputs(imports_root(ws))

    async def journey(client: ClientSession) -> dict[str, Any]:
        seen: dict[str, Any] = {}
        seen["info"] = structured(await client.call_tool("workspace_info", {}))
        arguments = {
            "client": "synthetic",
            "year": 2025,
            "anexa": str(anexa),
            "necesar": str(necesar),
            "prelucrare": str(prelucrare),
        }
        seen["draft"] = draft = structured(await client.call_tool("piee_generate", arguments))
        job = {"job": draft["job"]}
        seen["status"] = structured(await client.call_tool("job_status", job))
        seen["fields"] = structured(await client.call_tool("job_fields", job))["fields"]
        field = next(item for item in seen["fields"] if item["key"] == "identity.name")
        decision = {"field_id": field["id"], "action": "accept", "on_revision": field["revision"]}
        seen["decision"] = structured(await client.call_tool("job_decide", {**job, **decision}))
        seen["checks"] = structured(await client.call_tool("job_checks", job))
        seen["tools"] = [tool.name for tool in (await client.list_tools()).tools]
        return seen

    seen = with_client(ws, journey)

    assert seen["info"]["import_roots"][0] == str(imports_root(ws))
    draft = Path(seen["draft"]["draft"])
    assert draft.suffix == ".docx" and draft.is_file() and draft.is_relative_to(ws.root)
    run = next(item for item in seen["status"]["runs"] if item["id"] == seen["draft"]["run"])
    assert (run["stage"], run["state"]) == ("piee_generate", "ready")
    assert seen["decision"]["actor"] == "agent"
    assert seen["checks"]["final_ok"] is False
    assert not [name for name in seen["tools"] if set(name.split("_")) & EXPORTS]


def test_audit_draft_replay_journey(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    root = imports_root(ws)
    drafts = draft_recording(ws, job, CH2_DRAFT, root / "draft.json")
    support = support_recording(ws, job, CH2_DRAFT, root / "support.json", None)

    async def journey(client: ClientSession) -> dict[str, Any]:
        seen: dict[str, Any] = {}
        seen["jobs"] = structured(await client.call_tool("job_list", {}))["jobs"]
        arguments = {
            "job": job,
            "section": "ch2.date_generale",
            "draft_recording": str(drafts),
            "support_recording": str(support),
        }
        seen["draft"] = structured(await client.call_tool("audit_draft_section", arguments))
        seen["sections"] = structured(await client.call_tool("audit_sections", {"job": job}))
        seen["checks"] = structured(await client.call_tool("job_checks", {"job": job}))
        live = {"job": job, "section": "ch3.flux"}
        seen["live"] = text(await client.call_tool("audit_draft_section", live))
        return seen

    seen = with_client(ws, journey)

    assert [item["id"] for item in seen["jobs"]] == [job]
    draft = seen["draft"]
    assert (draft["draft_status"], draft["coverage"]) == ("drafted", 1.0)
    assert Path(draft["draft_path"]).is_file() and Path(draft["review_path"]).is_file()
    section = next(
        item for item in seen["sections"]["sections"] if item["section_id"] == "ch2.date_generale"
    )
    assert section["status"] == "drafted" and section["title"]
    assert seen["checks"]["final_ok"] is False
    assert seen["live"] == refusal(
        "audit_draft_section",
        "ai_client_disabled",
        "Redactarea pe documente reale aşteaptă aprobarea.",
    )
