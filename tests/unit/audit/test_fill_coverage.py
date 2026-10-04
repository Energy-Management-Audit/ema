"""Fill coverage of chapter 3 (#111 A): new catalogue facts, document guidance, process units."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit.audit.test_fill_extract import Scripted, extract, job, sections, values
from tests.unit.audit.test_fill_stage import OPENAI_MODEL, use_provider
from tests.workspace_jobs import create_job

from ema.audit.catalogue import CATALOGUE, AuditFact
from ema.audit.catalogue_labels import field_label
from ema.audit.catalogue_types import (
    MAX_PASSAGES,
    MAX_PROCESS_PASSAGES,
    PASSAGE_FACTS,
    fact_key,
    process_unit_name,
)
from ema.audit.dossier import dossier_documents
from ema.audit.draft_schema import SECTION_FACTS
from ema.audit.fill_extract import instructions
from ema.audit.fill_stage import fill_sections
from ema.audit.fill_tools import FillDocument, FillTools
from ema.audit.fill_units import record_unit_names
from ema.audit.process_units import ProcessUnits, passage_units, process_units, unit_of
from ema.core.review.fields import fields
from ema.core.review.models import Evidence, TextLoc
from ema.core.workspace import Workspace

UTILITIES = (
    "Regim de lucru: 3 schimburi, 7 zile pe săptămână.\n"
    "Centrala termică are două cazane pe gaz natural de câte 250 kW, care asigură apa caldă "
    "şi încălzirea halelor.\n"
    "Puterea instalată a centralei fotovoltaice este de 1.234,5 kWp, pusă în funcţiune în 2021.\n"
    "Gazul natural şi energia electrică sunt contorizate prin contoare proprii ale furnizorilor.\n"
    "Principalii consumatori sunt compresoarele de 75 kW şi cuptorul de polimerizare de 120 kW."
)
LINES = UTILITIES.splitlines()
COVERAGE = {"autorizatie.txt": FillDocument("autorizatie.txt", UTILITIES)}


def fact(key: str, value: str | int | float, line: int) -> dict[str, object]:
    return {"key": key, "value": value, "file": "F1", "page": 1, "quote": LINES[line]}


def test_the_new_facts_sit_where_her_audits_print_them() -> None:
    assert AuditFact.WORK_REGIME in SECTION_FACTS["ch2.date_generale"]
    assert {AuditFact.PV_POWER, AuditFact.PV_YEAR} <= SECTION_FACTS["ch3.electricitate"]
    assert AuditFact.HEATING in SECTION_FACTS["ch3.gaz"]
    assert AuditFact.METERING in SECTION_FACTS["ch3.contorizare"]
    assert AuditFact.EQUIPMENT in SECTION_FACTS["ch3.consumatori"]
    assert {AuditFact.HEATING, AuditFact.EQUIPMENT, AuditFact.METERING} <= PASSAGE_FACTS
    assert {key: field_label(key) for key in ("audit.work_regime", "audit.heating")} == {
        "audit.work_regime": "Regimul de lucru",
        "audit.heating": "Centrale termice",
    }
    assert field_label("audit.pv.power") == "Parcul propriu fotovoltaic – putere instalată"
    assert field_label("audit.pv.year") == "Parcul propriu fotovoltaic – anul punerii în funcţiune"
    assert field_label(process_unit_name(2)) == "Fluxul tehnologic 2 – denumire"
    gas = next(item for item in CATALOGUE if item.id == "ch3.gaz")
    assert {child.key for child in gas.applies_when.children} == {
        "audit.gas_supply",
        "audit.heating",
    }


def test_each_new_key_is_extracted_and_verified_in_its_type(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    wanted = sections("ch2.date_generale", "ch3.electricitate", "ch3.gaz", "ch3.contorizare")
    wanted += sections("ch3.consumatori")
    returned = [
        fact("audit.work_regime", "3 schimburi, 7 zile pe săptămână", 0),
        fact("audit.heating", "", 1),
        fact("audit.pv.power", "1.234,5", 2),
        fact("audit.pv.year", 2021, 2),
        fact("audit.metering", "", 3),
        fact("audit.equipment", "", 4),
    ]
    provider = Scripted([{"facts": returned, "missing": []}])

    summary = extract(ws, job_id, wanted, provider, COVERAGE)

    assert summary.rejected == {}
    stored = {item.key: item for item in fields(ws, job_id)}
    assert stored["audit.work_regime"].value == "3 schimburi, 7 zile pe săptămână"
    assert [stored[key].value for key in ("audit.heating", "audit.metering")] == LINES[1:4:2]
    assert stored["audit.equipment"].value == LINES[4]
    power, year = stored["audit.pv.power"], stored["audit.pv.year"]
    assert (power.value, power.value_type, power.unit) == (Decimal("1234.5"), "number", "kWp")
    assert (year.value, year.value_type, year.decimals) == (2021, "year", 0)
    assert all(stored[key].evidence for key in stored if stored[key].presence == "found")
    content = provider.sent[0][1]["content"]
    power_line = f"audit.pv.power — {field_label('audit.pv.power')} — ch3.electricitate"
    assert f"{power_line} — număr (kWp)\n" in content
    assert f"audit.pv.year — {field_label('audit.pv.year')} — ch3.electricitate — an\n" in content
    assert "audit.heating — Centrale termice — ch3.gaz — pasaj\n" in content


def test_a_typed_fact_that_is_not_a_number_is_rejected(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    words = fact("audit.pv.power", "o mie două sute", 2)
    provider = Scripted([{"facts": [words], "missing": []}, {"facts": [], "missing": []}])

    summary = extract(ws, job_id, sections("ch3.electricitate"), provider, COVERAGE)

    assert summary.rejected == {"audit.pv.power": "fact_type"}
    assert values(ws, job_id)["audit.pv.power"][1] == "not_found"


def test_the_prompt_says_where_each_section_s_facts_usually_are() -> None:
    text = instructions()
    guidance = text[text.index("Where each section's facts usually are:") :]
    for section in SECTION_FACTS:
        assert re.search(rf"[ ,]{re.escape(section)}[,:]", guidance), section
    for document in ("permit", "Necesar info", "flow schemes", "Fişa de date"):
        assert document in guidance
    # Generic document kinds only: never a file name.
    assert not re.search(r"\.(pdf|docx?|xlsx?|txt)\b", text, re.IGNORECASE)
    assert f"up to {MAX_PASSAGES} for one key and up to {MAX_PROCESS_PASSAGES} for " in text
    assert '"— număr (<unit>)"' in text and '"— an"' in text


PAGES = tuple(
    f"Etapa {number}. Piesele trec prin postul de lucru {number}." for number in range(15)
)


def test_the_process_flow_keeps_twelve_passages_and_other_keys_six(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    flow = {"flux.pdf": FillDocument("flux.pdf", "", page_texts=PAGES)}
    process = [
        {"key": "audit.process_sections", "value": "", "file": "F1", "page": page, "quote": text}
        for page, text in enumerate(PAGES, 1)
    ]
    heating = [{**item, "key": "audit.heating"} for item in process]
    provider = Scripted([{"facts": process + heating, "missing": []}])

    extract(ws, job_id, sections("ch3.process", "ch3.gaz"), provider, flow)

    found = values(ws, job_id)
    assert found["audit.process_sections.12"] == (PAGES[11], "found")
    assert "audit.process_sections.13" not in found
    assert found["audit.heating.6"] == (PAGES[5], "found")
    assert "audit.heating.7" not in found
    assert fact_key("audit.process_sections.12") == "audit.process_sections"
    assert fact_key("audit.heating.7") == "audit.heating.7"


def evidence(sha: str, quote: str) -> Evidence:
    return Evidence(
        id=quote,
        provenance="document",
        file_sha=sha,
        locator=TextLoc(span=quote),
        method="questionnaire",
        retrieved_at=datetime(2026, 10, 4, tzinfo=UTC),
        quote=quote,
        highlight="exact",
    )


SCHEMES = [
    ("5.10. Flux ambalare.pdf", "c"),
    ("5.2. Flux solvent.pdf", "b"),
    ("5.1. Flux vopsire.pdf", "a"),
    ("5.1. Flux vopsire anexa.pdf", "a2"),
    ("autorizatie.pdf", "permit"),
]


def test_a_three_scheme_plan_maps_each_passage_by_its_source_file() -> None:
    units = process_units(SCHEMES)

    assert (units.source, units.count) == ("schemes", 3)
    # Scheme ids sort as numbers: 5.10 is the third unit, after 5.2.
    assert [unit_of(evidence(sha, "x"), units) for sha in ("a", "a2", "b", "c")] == [1, 1, 2, 3]
    # The permit's text is the ch3.flux overview: it belongs to no unit.
    assert unit_of(evidence("permit", "x"), units) is None


FISA = (
    "Fişa de date a instalaţiei",
    "Societatea are două fluxuri tehnologice.",
    "Flux 1: vopsire în câmp electrostatic",
    "Piesele sunt degresate şi vopsite.",
    "Flux 2: recuperarea solvenţilor",
    "Solventul uzat este distilat.",
    "Descrierea utilităţilor",
)


def test_a_fisa_passage_belongs_to_the_flux_block_that_holds_its_quote() -> None:
    units = process_units([("Fisa de date.docx", "fisa")], ("fisa", FISA))

    assert (units.source, units.count) == ("fisa", 2)
    assert units.block(1) == FISA[2:4] and units.block(2) == FISA[4:]

    def unit(quote: str, sha: str = "fisa") -> int | None:
        return unit_of(evidence(sha, quote), units)

    assert unit("Piesele sunt degresate şi vopsite.") == 1
    assert unit("Flux 2: recuperarea solvenţilor\nSolventul uzat este distilat.") == 2
    assert unit("Societatea are două fluxuri tehnologice.") is None
    assert unit("Un text din tabelul fişei.") is None
    assert unit("Piesele sunt degresate şi vopsite.", sha="permit") is None
    assert unit_of(evidence("a", "x"), ProcessUnits()) is None


def scheme_dossier(tmp_path: Path) -> tuple[Workspace, str]:
    ws = Workspace(tmp_path / "workspace")
    job_id = create_job(ws, "audit", "made-up", 2026)
    texts = {
        "5.1. Flux vopsire.txt": "Linia de vopsire\nEtapa 1. Piesele sunt degresate.",
        "5.2. Flux solvent.txt": "Recuperarea solvenţilor\nEtapa 1. Solventul este distilat.",
        "5.3. Flux ambalare.txt": "Ambalare " * 40 + "\nEtapa 1. Piesele sunt ambalate.",
        "autorizatie.txt": "Instalaţia are trei fluxuri tehnologice.",
    }
    for name, text in texts.items():
        source = tmp_path / name
        source.write_text(text, encoding="utf-8")
        ws.set_slot(job_id, f"dossier/{name}", ws.add_file("made-up", source))
    return ws, job_id


def passage(name: str, quote: str) -> dict[str, object]:
    return {"key": "audit.process_sections", "value": "", "file": name, "page": 1, "quote": quote}


def test_fill_names_each_unit_and_the_passages_group_by_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    ws, job_id = scheme_dossier(tmp_path)
    returned = [
        passage("autorizatie.txt", "Instalaţia are trei fluxuri tehnologice."),
        passage("5.1. Flux vopsire.txt", "Etapa 1. Piesele sunt degresate."),
        passage("5.2. Flux solvent.txt", "Etapa 1. Solventul este distilat."),
    ]
    use_provider(monkeypatch, Scripted([{"facts": returned, "missing": []}]), OPENAI_MODEL)

    fill_sections(ws, job_id, ["ch3.process"])

    found = values(ws, job_id)
    assert found[process_unit_name(1)] == ("Linia de vopsire", "found")
    assert found[process_unit_name(2)] == ("Recuperarea solvenţilor", "found")
    # The third scheme's first line is a paragraph, not a title: its heading keeps the marker.
    assert found[process_unit_name(3)][1] == "not_found"
    by_key = {key: found[key][0] for key in found if key.startswith("audit.process_sections")}
    units = {by_key[key]: unit for key, unit in passage_units(ws, job_id).items()}
    assert units == {
        "Instalaţia are trei fluxuri tehnologice.": None,
        "Etapa 1. Piesele sunt degresate.": 1,
        "Etapa 1. Solventul este distilat.": 2,
    }
    # Unit 3 has no passage: nothing of another unit, nor the overview, is given to it.
    assert 3 not in units.values()


def test_a_rerun_with_fewer_units_drops_the_stale_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    ws, job_id = scheme_dossier(tmp_path)
    use_provider(monkeypatch, Scripted([{"facts": [], "missing": []}]), OPENAI_MODEL)
    fill_sections(ws, job_id, ["ch3.process"])
    assert values(ws, job_id)[process_unit_name(2)][1] == "found"
    documents = dossier_documents(ws, job_id)
    first = documents["5.1. Flux vopsire.txt"]
    tools = FillTools(ws, job_id, "ch3.process", documents)

    recorded = record_unit_names(tools, process_units([("5.1. Flux.txt", first.sha)]), documents)

    found = values(ws, job_id)
    assert recorded == 1
    assert found[process_unit_name(1)] == ("Linia de vopsire", "found")
    assert found[process_unit_name(2)][1] == found[process_unit_name(3)][1] == "not_found"
