"""Fill coverage of chapter 3 (#111 A): new catalogue facts, document guidance, process units."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit.audit.test_fill_extract import Scripted, extract, job, sections, values

from ema.audit.catalogue import CATALOGUE, AuditFact
from ema.audit.catalogue_labels import field_label
from ema.audit.catalogue_types import (
    MAX_PASSAGES,
    MAX_PROCESS_PASSAGES,
    PASSAGE_FACTS,
    fact_key,
    process_unit_name,
)
from ema.audit.draft_schema import SECTION_FACTS
from ema.audit.fill_extract import instructions
from ema.audit.fill_tools import FillDocument, FillTools
from ema.core.errors import EmaError
from ema.core.review.fields import fields

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


PV_LINES = (
    "Centrala fotovoltaică are o putere instalată de 1,2 MWp.",
    "Centrala fotovoltaică are o putere instalată de 1 MWp.",
    "Centrala fotovoltaică are o putere instalată de 800 kW.",
    "Puterea instalată a centralei fotovoltaice: 950.",
    "Centrala fotovoltaică are 1 MWp; fiecare panou are 1 kWp.",
)
PV = {"pv.txt": FillDocument("pv.txt", "\n".join(PV_LINES))}


def pv_power(value: str, line: int) -> dict[str, object]:
    return {"key": "audit.pv.power", "value": value, "name": "F1", "quote": PV_LINES[line]}


def test_a_power_in_mwp_is_converted_and_any_other_unit_is_rejected(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    tools = FillTools(ws, job_id, "ch3.electricitate", PV)

    # "1 MWp" is never recorded as 1 kWp; a unit other than kWp or MWp, or none, is rejected.
    # A value written with two units is ambiguous: neither 1 kWp nor 1 MWp is recorded.
    for args in (pv_power("800", 2), pv_power("950", 3), pv_power("1", 4)):
        with pytest.raises(EmaError) as error:
            tools.record_fact(args)
        assert error.value.code == "value_unverified"
    assert "audit.pv.power" not in values(ws, job_id)

    tools.record_fact(pv_power("1", 1))
    power = next(item for item in fields(ws, job_id) if item.key == "audit.pv.power")
    assert (power.value, power.unit) == (Decimal(1000), "kWp")
    assert power.derivation is not None
    assert power.derivation.formula_id == "unit.MWp_to_kWp"
    assert power.derivation.inputs == power.evidence

    tools.record_fact(pv_power("1,2", 0))
    assert values(ws, job_id)["audit.pv.power"] == ("1200.0", "found")


def test_a_missing_typed_fact_is_later_found_in_its_type(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    tools = FillTools(ws, job_id, "ch3.electricitate", COVERAGE)
    for key in ("audit.pv.power", "audit.pv.year"):
        tools.mark_missing({"key": key})
    missing = {item.key: item for item in fields(ws, job_id)}
    assert (missing["audit.pv.power"].value_type, missing["audit.pv.power"].unit) == (
        "number",
        "kWp",
    )
    assert missing["audit.pv.year"].value_type == "year"

    tools.record_fact({**fact("audit.pv.power", "1.234,5", 2), "name": "F1"})
    tools.record_fact({**fact("audit.pv.year", 2021, 2), "name": "F1"})

    found = {item.key: item for item in fields(ws, job_id)}
    assert (found["audit.pv.power"].value, found["audit.pv.power"].presence) == (
        Decimal("1234.5"),
        "found",
    )
    assert (found["audit.pv.year"].value, found["audit.pv.year"].presence) == (2021, "found")
