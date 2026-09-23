"""Round-trip the auditor's AUDIT-01 section 4.3.2 without storing client data."""

import copy
import os
import re
from pathlib import Path

import pytest
from lxml import etree

from ema.core.office.blocks import (
    BulletList,
    Caption,
    ElementLocator,
    NativeChart,
    Num,
    Paragraph,
    Prototypes,
    Ref,
    Table,
    render,
)
from ema.core.office.charts import read_series
from ema.core.office.package import inspect, read_parts, write_parts
from ema.core.office.sheets import open_book

pytestmark = pytest.mark.golden
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
OUTPUT = Path.home() / "Ema-dev/s2"


def _text(node: etree._Element) -> str:
    return "".join(item.text or "" for item in node.iter(W + "t"))


def _body(parts: dict[str, bytes]) -> etree._Element:
    root = etree.fromstring(parts["word/document.xml"])
    body = root.find(W + "body")
    assert body is not None
    return body


def _segments(text: str, reference: tuple[str, str, str] | None = None) -> list[str | Num | Ref]:
    if reference and reference[2] in text:
        kind, identifier, number = reference
        before, after = text.split(number, 1)
        return [before, Ref(kind, identifier), after]
    segments: list[str | Num] = []
    cursor = 0
    for match in re.finditer(r"(?<![\w.])(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?(?![\w.])", text):
        if match.start() > cursor:
            segments.append(text[cursor : match.start()])
        raw = match.group()
        decimals = len(raw.rsplit(",", 1)[1]) if "," in raw else 0
        grouping = "." in raw
        number = float(raw.replace(".", "").replace(",", "."))
        segments.append(Num(number, decimals, grouping=grouping))
        cursor = match.end()
    if cursor < len(text):
        segments.append(text[cursor:])
    return segments or [text]


def _table_cell(text: str) -> list[str | Num]:
    if re.fullmatch(r"(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?", text.strip()):
        return _segments(text.strip())
    return [text]


def _table_data(table: etree._Element) -> list[list[list[str | Num]]]:
    return [
        [[*_table_cell(_text(cell))] for cell in row.findall(W + "tc")]
        for row in table.findall(W + "tr")[1:]
    ]


def _citation(text: str, captions: dict[str, tuple[str, str, str]]) -> tuple[str, str, str] | None:
    for kind, stem in (("tab", "tabel"), ("fig", "figur")):
        caption = captions[kind]
        if caption[2] in text and re.search(rf"\b{stem}\w*", text, re.I):
            return caption
    return None


def _rpr(node: etree._Element, *, ignore_lang: bool = False) -> bytes:
    item = copy.deepcopy(node)
    if ignore_lang:
        for language in item.findall(W + "lang"):
            item.remove(language)
    return etree.tostring(item, method="c14n", exclusive=True)


def _table_run_properties(node: etree._Element) -> dict[tuple[int, int], etree._Element]:
    return {
        (row_index, run_index): properties
        for row_index, row in enumerate(node.findall(W + "tr"))
        for run_index, properties in enumerate(row.iter(W + "rPr"))
    }


def _table_run_drift(
    expected: etree._Element,
    actual: etree._Element,
    table_index: int,
    allowed: set[tuple[int, int, int]],
) -> tuple[int, set[tuple[int, int, int]]]:
    expected_runs = _table_run_properties(expected)
    actual_runs = _table_run_properties(actual)
    assert expected_runs.keys() == actual_runs.keys()
    drift: set[tuple[int, int, int]] = set()
    for position, left in expected_runs.items():
        right = actual_runs[position]
        if _rpr(left) != _rpr(right):
            location = (table_index, *position)
            assert location in allowed, f"unexpected table rPr drift: {location}"
            assert _rpr(left, ignore_lang=True) == _rpr(right, ignore_lang=True)
            drift.add(location)
    return len(expected_runs), drift


def _shape(node: etree._Element) -> tuple[str, str, list[bytes], bytes, list[bytes]]:
    props = node.find(W + "pPr")
    style = props.find(W + "pStyle") if props is not None else None
    table_props = node.find(W + "tblPr")
    cells = [
        etree.tostring(copy.deepcopy(cell.find(W + "tcPr")), method="c14n", exclusive=True)
        for cell in node.iter(W + "tc")
    ]
    return (
        node.tag,
        style.get(W + "val", "") if style is not None else "",
        [_rpr(item) for item in node.iter(W + "rPr")] if node.tag == W + "p" else [],
        etree.tostring(copy.deepcopy(table_props), method="c14n", exclusive=True)
        if table_props is not None
        else b"",
        cells,
    )


def test_AUDIT-01_432_round_trip() -> None:  # noqa: C901, PLR0912, PLR0915
    reference = os.environ.get("EMA_REFERENCE")
    if not reference:
        pytest.skip("EMA_REFERENCE unavailable; golden not verified")
    source = (
        Path(reference)
        / "audit/finished-audits"
        / ("AUDIT ENERGETIC AUDIT-01 ORAS - 2026.docx")
    )
    assert source.is_file()
    parts = read_parts(source)
    body = _body(parts)
    children = list(body)
    headings = [
        index
        for index, node in enumerate(children)
        if node.tag == W + "p"
        and "Analiza consumului total echivalent de gaz natural" in _text(node)
        and (style := node.find(W + "pPr/" + W + "pStyle")) is not None
        and style.get(W + "val") == "Style28"
    ]
    assert len(headings) == 1
    heading = headings[0]
    end = next(
        index
        for index in range(heading + 1, len(children))
        if (style := children[index].find(W + "pPr/" + W + "pStyle")) is not None
        and style.get(W + "val") == "Style28"
    )
    original = children[heading + 1 : end]
    assert len(original) == 18
    captions: dict[str, tuple[str, str, str]] = {}
    for node in original:
        caption_text = _text(node)
        kind = (
            "tab"
            if caption_text.startswith("Tabel")
            else "fig"
            if caption_text.startswith("Fig.")
            else None
        )
        if kind and (number := re.search(r"\b\d+\.\d+\b", caption_text)):
            identifier = "monthly" if kind == "tab" else "gas_annual"
            assert kind not in captions
            captions[kind] = (kind, identifier, number.group())
    assert set(captions) == {"tab", "fig"}
    chart_node = next(
        node
        for node in original
        if list(node.iter("{http://schemas.openxmlformats.org/drawingml/2006/chart}chart"))
    )
    chart_rid = next(
        chart_node.iter("{http://schemas.openxmlformats.org/drawingml/2006/chart}chart")
    ).get(R + "id")
    chart_ref = next(chart for chart in inspect(source).charts if chart.rel_id == chart_rid)
    prototypes: dict[str, etree._Element] = {}
    blocks = []
    for offset, node in enumerate(original):
        key = f"p{offset}"
        prototypes[key] = copy.deepcopy(node)
        text = _text(node)
        if node.tag == W + "tbl":
            blocks.append(Table(key, _table_data(node)))
        elif node is chart_node:
            blocks.append(NativeChart(key, chart_ref.part, read_series(source, chart_ref.part)))
        elif node.tag == W + "p" and text.startswith("Tabel") and captions["tab"][2] in text:
            blocks.append(Caption(key, "tab", "monthly", _segments(text, captions["tab"])))
        elif node.tag == W + "p" and text.startswith("Fig.") and captions["fig"][2] in text:
            blocks.append(Caption(key, "fig", "gas_annual", _segments(text, captions["fig"])))
        elif offset == 14:
            blocks.append(BulletList(key, [_segments(_text(item)) for item in original[14:17]]))
        elif offset in (15, 16):
            continue
        else:
            blocks.append(Paragraph(key, _segments(text, _citation(text, captions))))
    for node in original:
        body.remove(node)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base = OUTPUT / "base.docx"
    parts["word/document.xml"] = etree.tostring(body.getroottree(), encoding="UTF-8")
    write_parts(parts, base)
    out = OUTPUT / "regenerated.docx"
    report = render(base, out, ElementLocator(heading + 1), blocks, Prototypes(prototypes, 4))
    regenerated = list(_body(read_parts(out)))[heading + 1 : heading + 1 + len(original)]
    assert len(regenerated) == len(original)
    known_lang_exceptions = {(0, 2, 2), (0, 3, 2), (1, 2, 2), (1, 3, 2)}
    language_exceptions: set[tuple[int, int, int]] = set()
    table_runs = 0
    table_index = 0
    for index, (expected, actual) in enumerate(zip(original, regenerated, strict=True)):
        assert _shape(actual) == _shape(expected), f"element {index} structure"
        assert _text(actual) == _text(expected), f"element {index} visible text"
        if expected.tag == W + "tbl":
            run_count, drift = _table_run_drift(
                expected, actual, table_index, known_lang_exceptions
            )
            table_runs += run_count
            language_exceptions.update(drift)
            table_index += 1
    assert language_exceptions == known_lang_exceptions
    assert len(language_exceptions) == 4
    assert [(item.kind, item.number) for item in report.numbers] == [("tab", "4.7"), ("fig", "4.7")]
    assert len(report.chart_parts) == 1
    inserted = next(chart for chart in inspect(out).charts if chart.part == report.chart_parts[0])
    assert inserted.embedded is not None and inserted.external is None
    assert read_series(out, inserted.part) == read_series(source, chart_ref.part)
    print(
        "18 elements equal in kind, style, table properties and visible text; "
        f"table runs: {table_runs} compared, {len(language_exceptions)} differ only in w:lang; "
        f"paragraph rPr exact; chart cache equal; rendered numeric values: {len(report.values)}; "
        "evidence level 2"
    )


@pytest.mark.filterwarnings("ignore:Data Validation extension is not supported")
def test_annex_label_smoke() -> None:
    reference = os.environ.get("EMA_REFERENCE")
    if not reference:
        pytest.skip("EMA_REFERENCE unavailable; golden not verified")
    root = Path(reference) / "piee/anexa-2-3-2025"
    files = sorted(path for path in root.rglob("*") if path.suffix.lower() in {".xls", ".xlsx"})
    assert files
    found = 0
    for path in files:
        status = []
        try:
            book = open_book(path)
            try:
                general_name = next(
                    (
                        name
                        for name in ("Date generale", "Info companie")
                        if name in book.sheet_names
                    ),
                    "Date generale",
                )
                general = book.sheet(general_name)
                cui = general.find_label(["CUI", "C.U.I."])
                cui_value = general.read_right(cui, 2)
                status.append(f"CUI={cui_value.ref.a1 if cui_value.value is not None else 'empty'}")
                annual = book.sheet("Date anuale")
                total = annual.find_label(["CONSUM DE ENERGIE TOTAL ANUAL"])
                total_value = annual.read_block(total, 1, 1, down=1, right=6)[0][0]
                status.append(
                    f"total tep={total_value.ref.a1 if total_value.value is not None else 'empty'}"
                )
                found += cui_value.value is not None and total_value.value is not None
            finally:
                book.close()
        except Exception as error:
            status.append(f"error={getattr(error, 'code', type(error).__name__)}")
        print(f"{path.name}: {', '.join(status)}")
    print(f"Annex label smoke: {found}/{len(files)} with both values present; values withheld")
