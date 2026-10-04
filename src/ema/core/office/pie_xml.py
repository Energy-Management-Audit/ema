"""Native 3D pie XML matching the approved PIEE presentation contract."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import Literal

from lxml import etree

from ema.core.office.package import C, R

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
PieKind = Literal["pv", "mix"]
COLOURS = ("4F81BD", "C0504D", "9BBB59", "8064A2", "4BACC6", "F79646", "2C4D75", "772C2A")


def _add(parent: etree._Element, space: str, name: str, **attrs: str) -> etree._Element:
    return etree.SubElement(parent, f"{{{space}}}{name}", attrib=attrs)


def _flag(parent: etree._Element, name: str, value: str) -> etree._Element:
    return _add(parent, C, name, val=value)


def _colour(parent: etree._Element, colour: str) -> None:
    _add(_add(parent, A, "solidFill"), A, "srgbClr", val=colour)


def _text_properties(parent: etree._Element, size: str, *, bold: bool = False) -> None:
    props = _add(parent, C, "txPr")
    _add(props, A, "bodyPr")
    _add(props, A, "lstStyle")
    paragraph = _add(props, A, "p")
    para_props = _add(paragraph, A, "pPr")
    run_props = _add(para_props, A, "defRPr", sz=size)
    if not bold:
        run_props.set("b", "0")
    _colour(run_props, "000000")
    _add(run_props, A, "latin", typeface="Times New Roman")
    _add(run_props, A, "cs", typeface="Times New Roman")
    _add(paragraph, A, "endParaRPr", lang="ro-RO")


def _cache(reference: etree._Element, kind: str, formula: str, values: tuple[str, ...]) -> None:
    _add(reference, C, "f").text = formula
    cache = _add(reference, C, kind)
    if kind == "numCache":
        _add(cache, C, "formatCode").text = "0.00%"
    _flag(cache, "ptCount", str(len(values)))
    for index, value in enumerate(values):
        _add(_add(cache, C, "pt", idx=str(index)), C, "v").text = value


def _series_data(
    series: etree._Element,
    labels: tuple[str, ...],
    values: tuple[float, ...],
    representation: str,
) -> None:
    last = len(labels) + 1
    category = _add(_add(series, C, "cat"), C, "strRef")
    _cache(category, "strCache", f"Sheet1!$A$2:$A${last}", labels)
    numbers = _add(_add(series, C, "val"), C, "numRef")
    _cache(numbers, "numCache", f"Sheet1!$B$2:$B${last}", tuple(repr(v) for v in values))
    if representation == "raw":
        cache = numbers.find(f"{{{C}}}numCache")
        if cache is not None:
            format_code = cache.find(f"{{{C}}}formatCode")
            if format_code is not None:
                format_code.text = "General"


def _labels(parent: etree._Element, kind: PieKind, *, styled: bool) -> None:
    labels = _add(parent, C, "dLbls")
    if styled:
        _add(labels, C, "numFmt", formatCode="0.00%", sourceLinked="0")
        shape = _add(labels, C, "spPr")
        if kind == "mix":
            _colour(shape, "D9D9D9")
        else:
            _add(shape, A, "noFill")
        _add(_add(shape, A, "ln"), A, "noFill")
        _text_properties(labels, "1000" if kind == "pv" else "800")
    for name, value in (
        ("showLegendKey", "0"),
        ("showVal", "0"),
        ("showCatName", "0"),
        ("showSerName", "0"),
        ("showPercent", "1"),
        ("showBubbleSize", "0"),
        ("showLeaderLines", "1"),
    ):
        _flag(labels, name, value)


def _points(series: etree._Element, kind: PieKind, count: int) -> None:
    if kind == "mix":
        _flag(series, "explosion", "20")
    for index in range(count):
        point = _add(series, C, "dPt")
        _flag(point, "idx", str(index))
        _flag(point, "bubble3D", "0")
        shape = _add(point, C, "spPr")
        _colour(shape, COLOURS[index])
        _add(_add(shape, A, "ln"), A, "noFill")


def _plot(
    chart: etree._Element,
    kind: PieKind,
    labels: tuple[str, ...],
    values: tuple[float, ...],
    representation: str,
) -> None:
    plot = _add(chart, C, "plotArea")
    layout = _add(_add(plot, C, "layout"), C, "manualLayout")
    _flag(layout, "layoutTarget", "inner")
    _flag(layout, "xMode", "edge")
    _flag(layout, "yMode", "edge")
    coordinates = (
        ("0.04", "0.12", "0.56", "0.8") if kind == "pv" else ("0.03", "0.1", "0.62", "0.85")
    )
    for name, value in zip(("x", "y", "w", "h"), coordinates, strict=True):
        _flag(layout, name, value)
    pie = _add(plot, C, "pie3DChart")
    _flag(pie, "varyColors", "1")
    series = _add(pie, C, "ser")
    _flag(series, "idx", "0")
    _flag(series, "order", "0")
    title = _add(_add(series, C, "tx"), C, "strRef")
    _cache(title, "strCache", "Sheet1!$B$1", ("Pondere",))
    _points(series, kind, len(values))
    _labels(series, kind, styled=True)
    _series_data(series, labels, values, representation)
    _labels(pie, kind, styled=False)
    shape = _add(plot, C, "spPr")
    _add(shape, A, "noFill")
    _add(_add(shape, A, "ln"), A, "noFill")


def pie_root(
    kind: PieKind,
    labels: tuple[str, ...],
    values: tuple[float, ...],
    *,
    representation: str = "normalized",
) -> etree._Element:
    """Build a native, editable chart from sourced positive carrier values."""
    if representation not in {"normalized", "raw"}:
        raise ValueError("unknown pie value representation")
    if (
        len(labels) != len(values)
        or not 2 <= len(values) <= len(COLOURS)
        or any(v < 0 for v in values)
    ):
        raise ValueError("pie requires two to eight nonnegative labelled values")
    root = etree.Element(f"{{{C}}}chartSpace", nsmap={"c": C, "a": A, "r": R})
    _flag(root, "date1904", "0")
    _add(root, C, "lang", val="ro-RO")
    _flag(root, "roundedCorners", "0")
    chart = _add(root, C, "chart")
    _flag(chart, "autoTitleDeleted", "1")
    view = _add(chart, C, "view3D")
    for name, val in (("rotX", "30"), ("rotY", "0"), ("rAngAx", "0"), ("perspective", "30")):
        _flag(view, name, val)
    for name in ("floor", "sideWall", "backWall"):
        _flag(_add(chart, C, name), "thickness", "0")
    _plot(chart, kind, labels, values, representation)
    legend = _add(chart, C, "legend")
    _flag(legend, "legendPos", "r")
    _flag(legend, "overlay", "0")
    _text_properties(legend, "1000" if kind == "pv" else "800")
    _flag(chart, "plotVisOnly", "1")
    _add(chart, C, "dispBlanksAs", val="gap")
    shape = _add(root, C, "spPr")
    _colour(shape, "FFFFFF")
    _colour(_add(shape, A, "ln", w="9525"), "D9D9D9" if kind == "pv" else "868686")
    _text_properties(root, "1000" if kind == "pv" else "800")
    external = _add(root, C, "externalData")
    external.set(f"{{{R}}}id", "rId1")
    _flag(external, "autoUpdate", "0")
    return root
