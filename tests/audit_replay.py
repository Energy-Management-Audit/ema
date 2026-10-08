"""Hand-authored, request-bound replay recordings for the audit Draft agent (synthetic only)."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.replay_models import REPLAY_MODEL
from tests.workspace_jobs import create_job

from ema.audit.draft_agent import chapter_groups
from ema.audit.draft_checks import DraftCheck, DraftReview
from ema.audit.draft_plan import Group
from ema.audit.draft_prompt import (
    PROMPT_VERSION,
    SUPPORT_VERSION,
    Used,
    chapter_request,
    instructions,
)
from ema.audit.draft_render import render_section, review_payload
from ema.audit.draft_schema import ChapterDraft, DraftText, SectionDraft
from ema.audit.draft_support import (
    SUPPORT_PROMPT,
    SupportVerdicts,
    support_allowance,
    support_request,
)
from ema.audit.sections import mark_drafted, recompute_ready
from ema.core.llm.replay import request_hashes
from ema.core.review.fields import propose
from ema.core.review.models import Evidence, Field, Manual
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
        ),
        encoding="utf-8",
    )
    return path


def section_group(ws: Workspace, job: str, section: str) -> Group:
    """The one-section group the single-section path drafts, as `draft_one` builds it."""
    (group,), _ = chapter_groups(ws, job, (section,))
    return replace(group, id=section)


def draft_recording(ws: Workspace, job: str, draft: SectionDraft, path: Path) -> Path:
    group = section_group(ws, job, draft.section)
    messages = [
        {"role": "system", "content": instructions()},
        {
            "role": "user",
            "content": json.dumps(chapter_request(group, Used()), ensure_ascii=False),
        },
    ]
    row = {
        "request_hashes": request_hashes(
            REPLAY_MODEL,
            messages,
            (),
            ChapterDraft.model_json_schema(),
            group.allowance,
            PROMPT_VERSION,
        ),
        "choices": [{"message": {"content": json.dumps({"sections": [draft.model_dump()]})}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    return write_recording(path, [row])


def support_recording(
    ws: Workspace, job: str, draft: SectionDraft, path: Path, flagged: int | None
) -> Path:
    """Every sentence supported, except those of paragraph `flagged`."""
    facts = section_group(ws, job, draft.section).sections[0].facts
    request = support_request([draft], facts)
    messages = [
        {"role": "system", "content": SUPPORT_PROMPT},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]
    verdicts = [
        {
            "location": item["location"],
            "sentence_index": item["sentence_index"],
            "kind": "client",
            "supported": item["location"] != f"{draft.section}:paragraph:{flagged}",
            "reason": "The cited fact does not support a claim about efficiency.",
        }
        for item in request
    ]
    row = {
        "request_hashes": request_hashes(
            REPLAY_MODEL,
            messages,
            (),
            SupportVerdicts.model_json_schema(),
            support_allowance(len(request)),
            SUPPORT_VERSION,
        ),
        "choices": [{"message": {"content": json.dumps({"verdicts": verdicts})}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    return write_recording(path, [row])


def mark_section_drafted(ws: Workspace, job: str, draft: SectionDraft) -> None:
    """Capture the exact fact dependency of a drafted section for staleness."""
    if draft.status == "drafted":
        recompute_ready(ws, job)
        keys = {key for paragraph in draft.paragraphs for key in paragraph.fact_ids}
        mark_drafted(ws, job, draft.section, "agent", tuple(f"fact:{key}" for key in sorted(keys)))


def render_draft_section(
    ws: Workspace,
    job: str,
    base: Path,
    output: Path,
    *,
    draft: SectionDraft,
    facts: dict[str, Field],
    flags: tuple[DraftReview, ...],
) -> DraftCheck:
    """Publish paragraph output and capture the exact fact dependency for staleness."""
    check = render_section(base, output, draft, facts, flags, job=job)
    review_path = output.with_suffix(".draft-review.json")
    review_path.write_text(
        json.dumps(review_payload(draft, check, flags), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    mark_section_drafted(ws, job, draft)
    return check
