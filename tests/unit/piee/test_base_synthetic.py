"""PIEE base classification refuses unknown versions and finds synthetic variable content."""

import json
from pathlib import Path

import pytest
from docx import Document

from ema.core.office.anchors import AnchorLedger
from ema.core.office.base_map import classify, inventory, stamp_base
from ema.core.office.package import read_parts, write_parts
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import EnergyDataset
from ema.energy_data.necesar_model import NecesarInfo
from ema.piee.annual_check import AnnualCheck
from ema.piee.base import (
    _groups,
    _numeric_leftovers,
    _variable_selectors,
    build_local_base,
    identity_terms,
)
from ema.piee.body_spans import (
    PREVIOUS_YEAR,
    TABLE_NUMBERS,
    build_body_spans,
    build_unsourced_slots,
    render_body_spans,
)
from ema.piee.body_text import remove_unsourced_recommendation, render_body_text
from ema.piee.dataset import PieeData
from ema.piee.identity_map import build_identity_spans, render_identity
from ema.piee.number_spans import (
    GROUPS,
    YEAR_PARAGRAPHS,
    build_number_spans,
    build_year_spans,
    render_number_spans,
    render_year_spans,
)
from ema.piee.trends import OTHER_TREND_CHARTS, TREND_CHARTS, build_trend_spans, render_trends
from ema.piee.water import render_missing_water


def _base(path: Path) -> None:  # noqa: C901, PLR0912
    document = Document()
    annual_indices = {index for indices, _key, _decimals in GROUPS for index in indices}
    for index in range(1, 422):
        text = "Fixed methodology"
        if index == 1:
            text = "Plan energetic în cadrul Acme Fabric SRL - 2025"
        elif index == 9:
            text = "Adresă: Strada Exemplu 123, Oraș Test"
        elif index == 11:
            text = "J01/123/2025"
        elif index == 12:
            text = "12345678"
        elif index == 16:
            text = "+40 123 456 789"
        elif index == 17:
            text = "https://example.test"
        elif index == 30:
            text = "cantitatea de hârtie, 100 tone"
        elif index == 48:
            text = "Client Acme Fabric SRL used 1234 MWh"
        elif index in PREVIOUS_YEAR:
            text = "În anul 2023"
        elif index in TABLE_NUMBERS:
            text = "Tabelul 8"
        elif index == 218:
            text = "conform tabelul numărul 7"
        elif index == 405:
            text = "Recomandare nesusținută 2025"
        elif index in TREND_CHARTS or index in OTHER_TREND_CHARTS:
            text = "Se observă o creștere în 2025"
        elif index in annual_indices:
            text = "2025: 10 MWh/an"
        elif index in YEAR_PARAGRAPHS:
            text = "Analiză 2025"
        document.add_paragraph(text)
    document.save(path)
    parts = read_parts(path)
    footer = (
        b'<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        + b"<w:p/><w:p><w:r><w:t>Acme address</w:t></w:r></w:p>"
        + b"<w:p><w:r><w:t>Phone: 123; Fax: 456</w:t></w:r></w:p><w:p/></w:ftr>"
    )
    for number in (1, 3):
        parts[f"word/footer{number}.xml"] = footer
    write_parts(parts, path)


def test_synthetic_base_identifies_identity_numbers_and_section_boundaries(  # noqa: PLR0915
    tmp_path: Path,
) -> None:
    path = tmp_path / "base.docx"
    _base(path)
    parts = read_parts(path)
    terms = identity_terms(parts)
    assert "Acme Fabric SRL" in terms
    assert "12345678" in terms
    selectors = _variable_selectors(parts, terms, inventory(path))
    assert any(slot == "body_48" for slot in selectors.values())
    assert any(slot == "footer_contact_3" for slot in selectors.values())
    mapping = classify(path, selectors)
    assert _groups(parts, mapping)["natural_gas"] == ("body_165", "section_natural_gas_end")
    assert not _numeric_leftovers(parts, mapping)

    numbers_path = tmp_path / "numbers.json"
    years_path = tmp_path / "years.json"
    build_number_spans(parts, mapping, numbers_path)
    build_year_spans(parts, mapping, years_path)
    trends_path = tmp_path / "trends.json"
    build_trend_spans(parts, mapping, trends_path)
    body_path = tmp_path / "body.json"
    build_body_spans(parts, mapping, body_path)
    unsourced_path = tmp_path / "unsourced.json"
    build_unsourced_slots(parts, mapping, unsourced_path)
    identities = build_identity_spans(parts, mapping, tmp_path / "identities.json")
    numbers = json.loads(numbers_path.read_text(encoding="utf-8"))
    years = json.loads(years_path.read_text(encoding="utf-8"))
    assert len(numbers) == sum(len(indices) for indices, _key, _decimals in GROUPS)
    assert {item["year_offset"] for item in numbers} == {-2, -1, 0}
    assert len(years) == len(YEAR_PARAGRAPHS)
    assert len(json.loads(trends_path.read_text(encoding="utf-8"))) == len(TREND_CHARTS)
    assert len(json.loads(body_path.read_text(encoding="utf-8"))) == len(PREVIOUS_YEAR) + len(
        TABLE_NUMBERS
    )
    assert len(json.loads(unsourced_path.read_text(encoding="utf-8"))) == 1
    assert {item.key for item in identities} >= {"client_name", "address", "cui", "phone", "fax"}

    stamped = tmp_path / "stamped.docx"
    rendered = tmp_path / "rendered.docx"
    stamp_base(path, mapping, stamped)
    ledger = AnchorLedger(mapping.variable_slots)
    render_identity(
        stamped,
        tmp_path / "identities.json",
        {"client_name": "Replacement Company", "phone": "+40 100"},
        rendered,
        ledger,
    )
    rendered_parts = read_parts(rendered)
    assert "Replacement Company" in rendered_parts["word/document.xml"].decode()
    assert "n.d." in rendered_parts["word/footer1.xml"].decode()
    assert ledger.written

    empty = PieeData(
        2026,
        AnexaData(),
        NecesarInfo(),
        None,
        EnergyDataset((2024, 2025, 2026), {}),
        FACTORS_2026,
        (),
        AnnualCheck("missing", None, None),
    )
    numbers_rendered = tmp_path / "numbers-rendered.docx"
    years_rendered = tmp_path / "years-rendered.docx"
    render_number_spans(stamped, numbers_path, empty, numbers_rendered, ledger)
    render_year_spans(numbers_rendered, years_path, empty, years_rendered, ledger)
    text = read_parts(years_rendered)["word/document.xml"].decode()
    assert "n.d." in text
    assert "Analiză 2026" in text

    body_spans_rendered = tmp_path / "body-spans-rendered.docx"
    render_body_spans(stamped, body_path, empty, body_spans_rendered, ledger, water_missing=True)
    spans_xml = read_parts(body_spans_rendered)["word/document.xml"].decode()
    assert "În anul 2025." in spans_xml
    assert "tabelul numărul 5" in spans_xml
    assert "Tabelul 6" in spans_xml

    sections = tmp_path / "sections.json"
    sections.write_text(json.dumps(_groups(parts, mapping)), encoding="utf-8")
    water_rendered = tmp_path / "water-rendered.docx"
    render_missing_water(stamped, empty, sections, water_rendered, ledger)
    water_xml = read_parts(water_rendered)["word/document.xml"].decode()
    assert "Date indisponibile pentru perioada de analiză 2024 – 2026" in water_xml
    assert "Analiza consumului de apă industrială" in water_xml

    body_rendered = tmp_path / "body-rendered.docx"
    render_body_text(stamped, empty, body_rendered, ledger)
    assert "n.d." in read_parts(body_rendered)["word/document.xml"].decode()
    unsourced = tmp_path / "unsourced.json"
    unsourced.write_text(json.dumps(["body_124"]), encoding="utf-8")
    recommendation_removed = tmp_path / "recommendation-removed.docx"
    remove_unsourced_recommendation(stamped, unsourced, recommendation_removed, ledger)
    assert b"_ema_body_124" not in read_parts(recommendation_removed)["word/document.xml"]
    assert "body_124" in ledger.removed

    trends_rendered = tmp_path / "trends-rendered.docx"
    render_trends(stamped, trends_path, empty, trends_rendered, ledger)
    trends_xml = read_parts(trends_rendered)["word/document.xml"].decode()
    assert "n.d." in trends_xml
    assert "Se observă o creștere în 2025" not in trends_xml

    with pytest.raises(ValueError, match="unsupported PIEE base version"):
        build_local_base(path, tmp_path / "output")
    assert not (tmp_path / "output").exists()
