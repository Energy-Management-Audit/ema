"""Chapter four's variable factors: one call per Draft run for the resources without a list (#162).

Electricity, PV, natural gas, fuel and water each get the factors that shape their consumption
curve, from the client's activity and processes, without numbers. A list is optional: with no
call, a failed call or no factor passing its checks, the resource prints her lead-in and the
missing marker.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from functools import cache

from pydantic import BaseModel

from ema.audit.ai_wording import ai_wording
from ema.audit.catalogue_types import AuditFact, fact_key
from ema.audit.chapter_four_comments import FACTOR_LEAD, factor_key
from ema.audit.draft_checks import ACRONYM, NAME, NAME_COMMON, NUMBER_WORD, folded, traced
from ema.audit.draft_plan import MAX_OUTPUT_TOKENS, THINKING_TOKENS, usable
from ema.audit.research_quote import in_quote
from ema.audit.sections import get_status
from ema.core.errors import EmaError
from ema.core.jobs import StageContext
from ema.core.llm import AgentContext, complete_json
from ema.core.llm.types import Provider
from ema.core.logging import write_event
from ema.core.resources import resource_path
from ema.core.review import propose
from ema.core.review.models import Evidence, Field, FieldSpec, Manual
from ema.core.review.section_transition import Status

PROMPT_VERSION = "audit-ch4-factors-v1"
MAX_FACTORS = 8
MAX_WORDS = 60
# A list is a few long bullets; its JSON, at about this many tokens, follows the thinking.
TOKENS_PER_LIST = 700
DIGITS = re.compile(r"\d")
RESOURCES = {
    "ch4.electricitate": "energie electrică",
    "ch4.electricitate_pv": "energie electrică din parcul fotovoltaic propriu",
    "ch4.gaz": "gaz natural",
    "ch4.carburant": "carburant",
    "ch4.apa": "apă",
}
SUPPLY = {
    "ch4.electricitate": (AuditFact.ELECTRICITY_SUPPLY,),
    "ch4.electricitate_pv": (),
    "ch4.gaz": (AuditFact.GAS_SUPPLY, AuditFact.HEATING),
    "ch4.carburant": (AuditFact.FUEL_SUPPLY, AuditFact.FLEET),
    "ch4.apa": (AuditFact.WATER_SUPPLY,),
}
CONTEXT = {
    "activity": (AuditFact.BUSINESS_ACTIVITY, AuditFact.CAEN_DESCRIPTION),
    "work_regime": (AuditFact.WORK_REGIME,),
    "processes": (AuditFact.PROCESS_SECTIONS,),
}


class FactorList(BaseModel):
    id: str
    factors: list[str]


class FactorLists(BaseModel):
    lists: list[FactorList]


@cache
def instructions() -> str:
    path = resource_path("audit", "prompts", "ch4_factors_v1.txt")
    return path.read_text(encoding="utf-8").strip()


def factor_sections(ctx: StageContext, facts: Mapping[str, Field]) -> list[str]:
    """The resources the audit analyses that have no list field yet: a rerun never proposes
    over one, which would make it a conflict."""
    result: list[str] = []
    for section in FACTOR_LEAD:
        state = get_status(ctx.ws, ctx.job, section)
        if state.applicability and state.status != Status.NA and factor_key(section) not in facts:
            result.append(section)
    return result


def _texts(facts: Mapping[str, Field], wanted: Sequence[AuditFact]) -> list[str]:
    return [
        str(field.value)
        for key, field in sorted(facts.items())
        if fact_key(key) in wanted and usable(field)
    ]


def factor_request(sections: Sequence[str], facts: Mapping[str, Field]) -> dict[str, object]:
    context = {name: texts for name, keys in CONTEXT.items() if (texts := _texts(facts, keys))}
    supply = {section: texts for section in sections if (texts := _texts(facts, SUPPLY[section]))}
    return {
        "resources": [{"id": section, "resource": RESOURCES[section]} for section in sections],
        **context,
        **({"supply": supply} if supply else {}),
    }


def factor_issues(text: str, sources: Sequence[str]) -> list[str]:
    """Why a factor cannot stand: AI wording, its length, any number, or a name the request
    does not show."""
    issues: list[str] = []
    if ai_wording(text):
        issues.append("ai_wording")
    if len(text.split()) > MAX_WORDS:
        issues.append("length")
    if DIGITS.search(text) or NUMBER_WORD.search(folded(text)):
        issues.append("literal_number")
    common = {name.casefold() for name in NAME_COMMON}
    known = [traced(value) for value in sources]
    # A capital that opens the factor starts it, not a name.
    marked = ". " + text
    if any(
        name.casefold() not in common and not any(in_quote(traced(name), value) for value in known)
        for name in (*NAME.findall(marked), *ACRONYM.findall(text))
    ):
        issues.append("literal_name")
    return issues


def _log(ctx: StageContext, event: str, **values: object) -> None:
    with ctx.ws.connect() as db, ctx.ws.job_log(db, ctx.job) as handle:
        write_event(handle, event, run=ctx.run_id, **values)


def _evidence(job: str, section: str, text: str, model_id: str) -> Evidence:
    return Evidence(
        id=hashlib.sha256(f"{job}:ch4-factors:{section}:{text}".encode()).hexdigest(),
        provenance="manual",
        locator=Manual(who="agent", note=f"{PROMPT_VERSION} {model_id}"),
        method="manual",
        retrieved_at=datetime.now(UTC),
        highlight="none",
    )


def _accepted(
    answer: FactorLists, sections: Sequence[str], sources: Sequence[str]
) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    """Each requested resource's passing factors, at most eight, and what was dropped."""
    kept: dict[str, list[str]] = {}
    dropped: list[dict[str, str]] = []
    for item in answer.lists:
        if item.id not in sections or item.id in kept:
            reason = "unknown" if item.id not in sections else "duplicate"
            dropped.append({"id": item.id, "reason": reason})
            continue
        factors: list[str] = []
        for factor in item.factors:
            text = " ".join(factor.split()).rstrip(";,.").strip()
            reason = ", ".join(factor_issues(text, sources)) if text else "blank"
            if reason:
                dropped.append({"id": item.id, "reason": reason})
            elif len(factors) < MAX_FACTORS:
                factors.append(text)
        kept[item.id] = factors
    return {section: factors for section, factors in kept.items() if factors}, dropped


def write_factors(
    ctx: StageContext, provider: Provider, model_id: str, facts: Mapping[str, Field]
) -> tuple[list[Field], list[str]]:
    """Ask once for every resource without a list, propose each list with a passing factor;
    the proposed fields and the stage warnings."""
    sections = factor_sections(ctx, facts)
    if not sections:
        return [], []
    request = factor_request(sections, facts)
    asked = [key for keys in CONTEXT.values() for key in keys]
    asked += [key for section in sections for key in SUPPLY[section]]
    sources = [*RESOURCES.values(), *_texts(facts, asked)]
    try:
        context = AgentContext(
            ctx.ws,
            ctx.job,
            "ch4:factors",
            provider,
            model_id,
            PROMPT_VERSION,
            client_live=provider.name != "replay",
        )
        answer = complete_json(
            context,
            FactorLists,
            instructions(),
            json.dumps(request, ensure_ascii=False),
            max_output_tokens=min(
                MAX_OUTPUT_TOKENS, THINKING_TOKENS + TOKENS_PER_LIST * len(sections)
            ),
            schema_retries=0,
            thinking_tokens=THINKING_TOKENS,
        )
    except (EmaError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, EmaError) else type(exc).__name__
        _log(ctx, "ch4_factors_failed", code=code, detail=str(exc))
        return [], [f"ch4.factors: {code}"]
    lists, dropped = _accepted(answer, sections, sources)
    if dropped:
        _log(ctx, "ch4_factors_dropped", factors=dropped)
    proposed = [
        propose(
            ctx.ws,
            ctx.job,
            FieldSpec(
                key=factor_key(section),
                label=f"Factori variabili – {RESOURCES[section]}",
                value_type="text",
                chapter="ch4",
            ),
            "\n".join(factors),
            [_evidence(ctx.job, section, "\n".join(factors), model_id)],
            state="enriched",
        )
        for section, factors in lists.items()
    ]
    return proposed, []
