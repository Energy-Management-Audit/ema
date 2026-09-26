"""Hand-authored, request-bound replay recordings for the audit Draft agent (synthetic only)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ema.audit.draft_agent import (
    INSTRUCTIONS,
    PROMPT_VERSION,
    REPLAY_MODEL,
    DraftTools,
    recorded_facts,
)
from ema.audit.draft_checks import SUPPORT_PROMPT, SupportResult
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.core.jobs import create_job
from ema.core.llm.replay import request_hashes
from ema.core.review.fields import propose
from ema.core.review.models import Evidence, Manual
from ema.core.workspace import Workspace

CH2_DRAFT = SectionDraft(
    section="ch2.date_generale",
    status="drafted",
    paragraphs=[
        DraftText(
            text="Societatea {{f:audit.company_name}} are {{f:audit.employees}} angajați.",
            fact_ids=["audit.company_name", "audit.employees"],
        )
    ],
)


def audit_job_with_facts(ws: Workspace) -> str:
    """A synthetic audit job whose chapter 2 general data facts are supplied by hand."""
    job = create_job(ws, "audit", "synthetic", 2026)
    for key, value in (("audit.company_name", "Atelier Exemplu"), ("audit.employees", 85)):
        evidence = Evidence(
            id="synthetic:" + key,
            provenance="manual",
            locator=Manual(who="synthetic"),
            method="manual",
            retrieved_at=datetime.now(UTC),
            highlight="exact",
        )
        propose(ws, job, key, value, [evidence], state="supplied")
    return job


def write_recording(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text(
        json.dumps(
            {"source": "hand-authored", "format": "openai-chat-completions", "responses": rows},
            ensure_ascii=False,
        )
    )
    return path


def draft_recording(ws: Workspace, job: str, draft: SectionDraft, path: Path) -> Path:
    tools = DraftTools(ws, job, draft.section)
    specs = tuple(tool.spec for tool in tools.tools().values())
    messages: list[dict[str, Any]] = [{"role": "system", "content": INSTRUCTIONS}]
    rows: list[dict[str, Any]] = []
    calls = [
        ("read_facts", {}),
        ("read_style_guide", {}),
        ("write_section_draft", draft.model_dump()),
    ]
    for index, (name, args) in enumerate(calls):
        rows.append(
            {
                "request_hashes": request_hashes(
                    REPLAY_MODEL, messages, specs, None, 4096, PROMPT_VERSION
                ),
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": str(index),
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(args, ensure_ascii=False),
                                    },
                                }
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        )
        result = tools.tools()[name].execute(args)
        messages.append(
            {
                "role": "assistant",
                "tool_calls": [{"id": str(index), "name": name, "arguments": args}],
            }
        )
        messages.append(
            {"role": "tool", "name": name, "tool_call_id": str(index), "content": result}
        )
    assert tools.draft is not None
    rows.append(
        {
            "request_hashes": request_hashes(
                REPLAY_MODEL, messages, specs, None, 4096, PROMPT_VERSION
            ),
            "choices": [{"message": {"content": "Draft complete"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )
    return write_recording(path, rows)


def support_recording(
    ws: Workspace, job: str, draft: SectionDraft, path: Path, flagged: int | None
) -> Path:
    facts = recorded_facts(ws, job, draft.section)
    request = [
        {
            "location": f"paragraph:{index}",
            "text": paragraph.text,
            "facts": {key: str(facts[key].value) for key in paragraph.fact_ids},
        }
        for index, paragraph in enumerate(draft.paragraphs)
    ]
    content = json.dumps(request, ensure_ascii=False)
    messages = [
        {"role": "system", "content": SUPPORT_PROMPT},
        {"role": "user", "content": content},
    ]
    flags = (
        []
        if flagged is None
        else [
            {
                "location": f"paragraph:{flagged}",
                "sentence": draft.paragraphs[flagged].text,
                "reason": "The cited fact does not support a claim about efficiency.",
            }
        ]
    )
    row = {
        "request_hashes": request_hashes(
            REPLAY_MODEL,
            messages,
            (),
            SupportResult.model_json_schema(),
            4096,
            PROMPT_VERSION + "-support",
        ),
        "choices": [{"message": {"content": json.dumps({"flags": flags})}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    return write_recording(path, [row])
