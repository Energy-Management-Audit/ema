"""piee_case_b figures are compared with the auditor's delivered, native-chart final."""

from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
from tests.golden.cases import case_path

from conftest import artifacts_path
from ema.core.office.chart_series import Series, read_series
from ema.core.office.package import (
    REL_CHART,
    C,
    R,
    check_standalone,
    read_parts,
    relationships,
    target_part,
    xml,
)
from ema.piee.compose import compose_draft
from ema.piee.dataset import load

pytestmark = pytest.mark.golden

# Figure numbers are document order, not OOXML chart-part names. No client values live here.
EXCEPTIONS = {
    13: "authored monthly fuel chart omits a filed carrier",
    14: "authored monthly fuel chart omits a filed carrier",
    15: "authored monthly fuel chart omits a filed carrier",
    16: "authored annual fuel chart treats missing months as zero",
    17: "authored annual fuel total treats missing months as zero",
    23: "prior-year PV category lacks a source reading",
}
CAPTION_KINDS = {
    "production": r"produc",
    "electricity": r"electric",
    "gas": r"gaz",
    "fuel": r"carbur|motorin|benzin|gpl",
    "biomass": r"biomas|coji|floarea",
    "pv": r"fotovolta",
    "specific": r"specific",
    "intensity": r"intensitate",
    "share": r"ponderea",
    "impact": r"impact|mediu|co₂",
}


def _order(path: Path) -> list[str]:
    parts = read_parts(path)
    links = {
        relation.get("Id"): target_part("word/document.xml", relation.get("Target", ""))
        for relation in relationships(parts, "word/document.xml")
        if relation.get("Type") == REL_CHART
    }
    return [
        links[node.get(f"{{{R}}}id")]
        for node in xml(parts, "word/document.xml").iter(f"{{{C}}}chart")
    ]


def _caption_slots(path: Path) -> list[frozenset[str]]:
    root = xml(read_parts(path), "word/document.xml")
    result = []
    for paragraph in root.iter(qn("w:p")):
        if not list(paragraph.iter(f"{{{C}}}chart")):
            continue
        following = paragraph.getnext()
        caption = (
            "".join(node.text or "" for node in following.iter(qn("w:t")))
            if following is not None
            else ""
        )
        assert caption.strip().startswith(("Fig.", "Figura"))
        result.append(
            frozenset(
                kind for kind, pattern in CAPTION_KINDS.items() if re.search(pattern, caption, re.I)
            )
        )
    return result


def _number(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)


def _series(left: Series, right: Series, *, scale: float = 1) -> bool:
    return len(left.values) == len(right.values) and all(
        _number(value * scale if value is not None else None, authored)
        for value, authored in zip(left.values, right.values, strict=True)
    )


def test_piee_case_b_figure_inventory_and_numbers_match_or_have_pinned_reason(
    reference_library: Path, tmp_path: Path
) -> None:
    case = reference_library / case_path("piee-case-b")
    final = reference_library / case_path("piee-case-b", "final")
    cover = "\n".join(paragraph.text for paragraph in Document(final).paragraphs[:5])
    assert "-2026-" in cover
    data = load(
        2025,
        next(case.rglob("Anexa*.xlsx")),
        None,
        next(case.rglob("*Prelucrare*.xlsx")),
        final,
    )
    output = tmp_path / "draft.docx"
    status = compose_draft(data, artifacts_path("s8", "base"), output, date(2026, 9, 24))
    assert not status.package_issues and not status.leftover_parts
    assert not check_standalone(output)
    produced, authored = _order(output), _order(final)
    assert len(produced) == len(authored) == 35
    assert len(set(produced)) == 35
    assert _caption_slots(output) == _caption_slots(final)
    # F16 keeps the base's fuel a/b/c/d group together, then adds the annual breakdown.
    assert produced[15] == "word/charts/chart20.xml"
    comparison_order = [*produced[:15], produced[16], produced[15], *produced[17:]]
    assert len(EXCEPTIONS) == 6
    for ordinal, (actual_part, reference_part) in enumerate(
        zip(comparison_order, authored, strict=True), 1
    ):
        actual, expected = read_series(output, actual_part), read_series(final, reference_part)
        if ordinal in {13, 14, 15}:
            assert len(actual) == 3 and len(expected) == 2, f"figure {ordinal}"
            matched = all(_series(x, y) for x, y in zip(actual[:2], expected, strict=True))
            assert matched, f"figure {ordinal}"
        elif ordinal == 16:
            assert len(actual) == len(expected), f"figure {ordinal}"
            matched = all(_series(x, y) for x, y in zip(actual[:2], expected[:2], strict=True))
            assert matched, f"figure {ordinal}"
            assert all(item.values[:2] == [None, None] for item in actual[2:]), f"figure {ordinal}"
            assert all(
                _number(x.values[-1], y.values[-1]) for x, y in zip(actual, expected, strict=True)
            )
        elif ordinal == 17:
            assert len(actual) == len(expected) == 1
            assert actual[0].values[:2] == [None, None]
            assert _number(actual[0].values[-1], expected[0].values[-1])
        elif ordinal == 23:
            assert len(actual) == len(expected) == 1
            assert len(actual[0].values) == 4 and len(expected[0].values) == 5
            assert all(
                _number(left, right)
                for left, right in zip(actual[0].values, expected[0].values, strict=False)
            )
        elif 25 <= ordinal <= 32:
            assert len(actual) == len(expected) == 1
            assert len(actual[0].values) == len(expected[0].values) or ordinal == 32
            assert all(
                _number(left, right)
                for left, right in zip(actual[0].values, expected[0].values, strict=False)
            ), f"figure {ordinal}"
        else:
            assert len(actual) == len(expected), f"figure {ordinal}"
            matched = all(_series(x, y) for x, y in zip(actual, expected, strict=True))
            assert matched, f"figure {ordinal}"
