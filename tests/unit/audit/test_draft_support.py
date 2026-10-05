"""The support pass thinks at a bounded level and asks a large group in batches (#153)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from google.genai import types
from tests.unit.audit.test_draft_structured import SECTION, SupportProvider
from tests.unit.audit.test_section_body import FACTS
from tests.workspace_jobs import create_job

from ema.audit.draft_schema import DraftText, SectionDraft
from ema.audit.draft_support import (
    MAX_VERDICT_TOKENS,
    THINKING_TOKENS,
    VERDICT_TOKENS,
    support_allowance,
    support_pass,
)
from ema.core.llm import AgentContext
from ema.core.llm.models import default_model
from ema.core.llm.providers import GeminiProvider
from ema.core.llm.types import Provider
from ema.core.workspace import Workspace

SENTENCE = "Societatea {{f:audit.company_name}} produce ambalaje."


def _draft(sentences: int) -> SectionDraft:
    return SectionDraft(
        section=SECTION,
        status="drafted",
        paragraphs=[
            DraftText(text=SENTENCE, fact_ids=["audit.company_name"]) for _ in range(sentences)
        ],
    )


def _context(tmp_path: Path, provider: Provider, model_id: str) -> AgentContext:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    return AgentContext(ws, job, "support:3", provider, model_id, "v1", synthetic=True)


def test_the_support_call_thinks_at_a_low_level_on_gemini_3(tmp_path: Path) -> None:
    configs: list[types.GenerateContentConfig] = []
    verdict = {"location": f"{SECTION}:paragraph:0", "sentence_index": 0, "kind": "client"}

    class Models:
        def generate_content(self, **kwargs: object) -> object:
            configs.append(kwargs["config"])  # type: ignore[arg-type]
            return SimpleNamespace(
                function_calls=[],
                text=json.dumps({"verdicts": [verdict | {"supported": True}]}),
                usage_metadata=None,
                candidates=[SimpleNamespace(content=None, finish_reason=types.FinishReason.STOP)],
            )

    provider = GeminiProvider.__new__(GeminiProvider)
    provider._client = SimpleNamespace(models=Models())
    flags = support_pass(_context(tmp_path, provider, "gemini-3.8-flash"), [_draft(1)], FACTS)
    assert flags == {SECTION: ()}
    (config,) = configs
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert config.max_output_tokens == support_allowance(1) == THINKING_TOKENS + 120


def test_a_verdict_is_allowed_120_tokens() -> None:
    assert VERDICT_TOKENS == 120
    assert support_allowance(10) - support_allowance(9) == 120


def test_a_large_group_is_asked_in_batches_and_its_verdicts_merge_in_order(
    tmp_path: Path,
) -> None:
    refused = frozenset({(f"{SECTION}:paragraph:5", 0), (f"{SECTION}:paragraph:300", 0)})
    support = SupportProvider(refused=refused)
    context = _context(tmp_path, support, default_model("openai").id)
    flags = support_pass(context, [_draft(400)], FACTS)
    size = MAX_VERDICT_TOKENS // VERDICT_TOKENS
    assert [len(request) for request in support.requests] == [size, 400 - size]
    assert all(VERDICT_TOKENS * len(request) <= 32_000 for request in support.requests)
    assert support.limits == [support_allowance(size), support_allowance(400 - size)]
    asked = [item["location"] for request in support.requests for item in request]
    assert asked == [f"{SECTION}:paragraph:{index}" for index in range(400)]
    assert [flag.location for flag in flags[SECTION]] == ["paragraph:5", "paragraph:300"]
