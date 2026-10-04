"""PIEE source spans retain their wording and mark only unavailable values."""

from datetime import date, datetime

import pytest
from docx import Document

from ema.core.office.cell_text import set_paragraph_text
from ema.core.office.run_range import TextSpan, replace_spans
from ema.core.office.sheets import CellRef
from ema.core.review.models import Field
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.source import Located
from ema.piee.body_text import _sourced_text
from ema.piee.identity import SpanText, audit_year, ownership
from ema.piee.review_workflow import _ownership_issues


def _anexa(state: str | None = None, private: str | None = None) -> AnexaData:
    identity = {
        f"ownership_{side}": Located(value, CellRef("Anexa", 1, column))
        for side, value, column in (("state", state, 1), ("private", private, 2))
        if value is not None
    }
    return AnexaData(identity=identity)


def _runs(line: SpanText | None) -> tuple[str, list[tuple[str, str | None]]]:
    paragraph = Document().add_paragraph("synthetic base")
    if line is None:
        set_paragraph_text(paragraph._p, "n.d.", missing=True)
    else:
        set_paragraph_text(paragraph._p, line.text)
        replace_spans(
            paragraph._p,
            tuple(TextSpan(start, end, "n.d.", True) for start, end in line.missing),
        )
    return paragraph.text, [
        (run.text, str(run.font.color.rgb) if run.font.color and run.font.color.rgb else None)
        for run in paragraph.runs
        if run.text
    ]


@pytest.mark.parametrize(
    "state,private,expected,missing",
    [
        ("0%", "100%", "Companie cu capital integral privat: 100% capital privat.", False),
        ("100%", "0%", "Companie cu capital integral de stat: 100% capital de stat.", False),
        (
            "30%",
            "70%",
            "Companie cu capital mixt: 30% capital de stat și 70% capital privat.",
            False,
        ),
        (None, "100%", "Companie cu capital integral privat: 100% capital privat.", False),
        ("100%", None, "Companie cu capital integral de stat: 100% capital de stat.", False),
        (
            None,
            "70%",
            "Companie cu capital mixt: n.d. capital de stat și 70% capital privat.",
            True,
        ),
        (
            "30%",
            None,
            "Companie cu capital mixt: 30% capital de stat și n.d. capital privat.",
            True,
        ),
        ("0%", None, "Companie cu capital integral privat: n.d. capital privat.", True),
        (None, "0%", "Companie cu capital integral de stat: n.d. capital de stat.", True),
        (None, None, "n.d.", True),
    ],
)
def test_ownership_lines_and_missing_runs(
    state: str | None, private: str | None, expected: str, missing: bool
) -> None:
    line = ownership(_anexa(state, private))
    text, runs = _runs(line)
    assert text == expected
    assert isinstance(line, SpanText) if line is not None else state is private is None
    red = "".join(part for part, colour in runs if colour == "FF0000")
    assert red == ("n.d." if missing else "")
    assert all(colour != "FF0000" for part, colour in runs if part != "n.d.")
    if line is not None:
        assert tuple((text[start:end] for start, end in line.missing)) == (
            ("n.d.",) if missing else ()
        )


@pytest.mark.parametrize(
    "raw,expected",
    [
        (datetime(2025, 3, 30), "2025"),
        (date(2025, 3, 30), "2025"),
        ("30.03.2025", "2025"),
        ("2022; text", "2022"),
        ("2021 și 2023", None),
        (None, None),
        (2024, "2024"),
        (1989, None),
    ],
)
def test_audit_year(raw: datetime | date | str | int | None, expected: str | None) -> None:
    anexa = AnexaData(
        audit={"last_audit": Located(raw, CellRef("Audit energetic", 1, 1))}
        if raw is not None
        else {}
    )
    assert audit_year(anexa) == expected


@pytest.mark.parametrize(
    "values,expected,red",
    [
        (
            {"client": "Client", "auditor": "Auditor", "year": "2025"},
            "Audit energetic pe întregul contur aparținând Client "
            "realizat de Auditor în anul 2025,",
            "",
        ),
        (
            {"client": "Client", "auditor": None, "year": "2025"},
            "Audit energetic pe întregul contur aparținând Client realizat de n.d. în anul 2025,",
            "n.d.",
        ),
        ({"client": None, "auditor": None, "year": None}, "n.d.", "n.d."),
    ],
)
def test_audit_history_sourced_spans(
    values: dict[str, str | None], expected: str, red: str
) -> None:
    line = _sourced_text(
        "Audit energetic pe întregul contur aparținând {client} realizat de {auditor} "
        "în anul {year},",
        values,
    )
    text, runs = _runs(line)
    assert text == expected
    assert "".join(part for part, colour in runs if colour == "FF0000") == red


@pytest.mark.parametrize(
    "client,year,expected,red",
    [
        (
            "Client",
            "2025",
            "Reprezentanții Client dau importanță eficienței energetice, fapt dovedit "
            "și prin realizarea lucrării de Audit energetic pe întregul contur energetic "
            "în anul 2025 ce aparține societății pentru încadrarea în obligațiile legii 121/2014.",
            "",
        ),
        (
            None,
            "2025",
            "Reprezentanții n.d. dau importanță eficienței energetice, fapt dovedit "
            "și prin realizarea lucrării de Audit energetic pe întregul contur energetic "
            "în anul 2025 ce aparține societății pentru încadrarea în obligațiile legii 121/2014.",
            "n.d.",
        ),
        (None, None, "n.d.", "n.d."),
    ],
)
def test_audit_narrative_template(
    client: str | None, year: str | None, expected: str, red: str
) -> None:
    values = {"client": client, "auditor": None, "year": year}
    line = _sourced_text(
        "Reprezentanții {client} dau importanță eficienței energetice, fapt dovedit "
        "și prin realizarea lucrării de Audit energetic pe întregul contur energetic "
        "în anul {year} ce aparține societății pentru încadrarea în obligațiile legii 121/2014.",
        values,
    )
    text, runs = _runs(line)
    assert text == expected
    assert "".join(part for part, colour in runs if colour == "FF0000") == red


def _field(side: str, value: str | None, review: str = "pending") -> Field:
    return Field(
        id=side,
        job_id="synthetic",
        key=f"identity.ownership_{side}",
        label=side,
        value_type="text",
        value=value,
        state="extracted",
        presence="found" if value is not None else "not_found",
        review=review,
    )


@pytest.mark.parametrize(
    "state,private,rejected,missing",
    [
        (None, "100%", False, set()),
        (None, "100,00%", False, set()),
        ("100%", None, False, set()),
        (None, "70%", False, {"state"}),
        ("30%", None, False, {"private"}),
        ("0%", None, False, {"private"}),
        (None, None, False, {"state", "private"}),
        ("30%", "70%", True, {"state"}),
    ],
)
def test_ownership_review_follows_rendered_gaps(
    state: str | None, private: str | None, rejected: bool, missing: set[str]
) -> None:
    fields = [
        _field("state", state, "rejected" if rejected else "pending"),
        _field("private", private),
    ]
    assert {issue.field_id for issue in _ownership_issues(fields)} == missing
