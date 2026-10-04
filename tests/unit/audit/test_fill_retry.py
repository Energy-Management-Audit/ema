"""Fill v2: a failed extraction retry keeps what the first pass verified."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests.unit.audit.test_fill_extract import (
    COMPANY,
    LOCATION,
    OPENAI_MODEL,
    Scripted,
    extract,
    job,
    log_events,
    sections,
    values,
)

from ema.core.errors import EmaError
from ema.core.llm.types import Exchange


class Failing(Scripted):
    """Scripted, but an answer may be raw text (a cut-off reply) or an error to raise."""

    def __init__(self, script: list[Any]) -> None:
        super().__init__([item if isinstance(item, dict) else {} for item in script])
        self.script = script

    def respond(
        self, model: str, messages: list[dict[str, Any]], *args: Any, **kwargs: Any
    ) -> Exchange:
        answer = self.script[len(self.sent)]
        if isinstance(answer, Exception):
            self.sent.append(json.loads(json.dumps(messages)))
            raise answer
        if isinstance(answer, str):
            self.sent.append(json.loads(json.dumps(messages)))
            return Exchange(answer, (), 1000, 100)
        return super().respond(model, messages, *args, **kwargs)


def test_a_retry_cut_off_mid_answer_keeps_the_first_pass_facts(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    wrong = {**LOCATION, "quote": "Amplasament: zona industrială Est."}
    cut = '{"facts": [{"key": "audit.location", "value": "zona'
    provider = Failing([{"facts": [COMPANY, wrong], "missing": []}, cut, cut])

    summary = extract(ws, job_id, sections("ch2.date_generale", "ch2.localizare"), provider)

    assert values(ws, job_id)["audit.company_name"] == ("Firma Exemplu SRL", "found")
    assert "audit.location" in summary.missing
    assert [item["code"] for item in log_events(ws, job_id, "extract_retry_failed")] == [
        "ai_schema"
    ]


def test_credits_running_out_on_the_retry_still_stop_the_stage(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    wrong = {**LOCATION, "quote": "Amplasament: zona industrială Est."}
    credits = EmaError("ai_credits", "Creditul furnizorului AI s-a epuizat.", OPENAI_MODEL)
    provider = Failing([{"facts": [COMPANY, wrong], "missing": []}, credits])

    with pytest.raises(EmaError) as error:
        extract(ws, job_id, sections("ch2.date_generale", "ch2.localizare"), provider)
    assert error.value.code == "ai_credits"
