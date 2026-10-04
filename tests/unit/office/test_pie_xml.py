"""Native PIEE pies retain editable caches and approved presentation settings."""

import pytest

from ema.core.office.package import C, R
from ema.core.office.pie_xml import A, pie_root


@pytest.mark.parametrize("kind,size", [("pv", "1000"), ("mix", "800")])
def test_native_pie_contains_editable_sourced_values(kind: str, size: str) -> None:
    root = pie_root(kind, ("Grid", "Gas"), (0.25, 0.75))
    assert root.xpath(".//c:pie3DChart", namespaces={"c": C})
    assert root.xpath(".//c:strCache/c:pt/c:v/text()", namespaces={"c": C})[-2:] == ["Grid", "Gas"]
    assert root.xpath(".//c:numCache/c:pt/c:v/text()", namespaces={"c": C}) == ["0.25", "0.75"]
    assert root.xpath(".//c:numCache/c:formatCode/text()", namespaces={"c": C}) == ["0.00%"]
    assert root.xpath(".//c:externalData", namespaces={"c": C})[0].get(f"{{{R}}}id") == "rId1"
    assert root.xpath(".//c:legend//a:defRPr", namespaces={"c": C, "a": A})[0].get("sz") == size
    if kind == "mix":
        assert root.xpath(".//c:ser/c:explosion/@val", namespaces={"c": C}) == ["20"]
    else:
        assert not root.xpath(".//c:ser/c:explosion", namespaces={"c": C})


def test_raw_pie_uses_general_number_format() -> None:
    root = pie_root("pv", ("Grid", "Gas"), (20, 80), representation="raw")
    assert root.xpath(".//c:numCache/c:formatCode/text()", namespaces={"c": C}) == ["General"]
    assert root.xpath(".//c:numCache/c:pt/c:v/text()", namespaces={"c": C}) == ["20", "80"]


@pytest.mark.parametrize(
    "labels,values,representation",
    [
        (("Only",), (1,), "normalized"),
        (("A", "B"), (1,), "normalized"),
        (("A", "B"), (-1, 2), "normalized"),
        (("A", "B"), (1, 2), "unknown"),
    ],
)
def test_pie_rejects_invalid_values(
    labels: tuple[str, ...], values: tuple[float, ...], representation: str
) -> None:
    with pytest.raises(ValueError):
        pie_root("pv", labels, values, representation=representation)


def test_pie_accepts_eight_slices_and_rejects_nine() -> None:
    labels = tuple(f"S{index}" for index in range(9))
    root = pie_root("mix", labels[:8], (0.125,) * 8)
    assert len(root.xpath(".//c:dPt", namespaces={"c": C})) == 8
    assert root.xpath(".//c:dPt//a:srgbClr/@val", namespaces={"c": C, "a": A})[5:] == [
        "F79646",
        "2C4D75",
        "772C2A",
    ]
    with pytest.raises(ValueError):
        pie_root("mix", labels, (1 / 9,) * 9)
