"""Rewritten charts discard stale authored scale bounds."""

import pytest
from lxml import etree

from ema.core.office.chart_rewrite import _axes
from ema.core.office.package import C


def test_value_axis_resets_stale_scale_and_layout() -> None:
    root = etree.fromstring(
        f'<c:chartSpace xmlns:c="{C}"><c:chart><c:plotArea>'
        '<c:layout/><c:valAx><c:axId val="1"/><c:scaling>'
        '<c:max val="40"/><c:min val="5"/></c:scaling><c:majorUnit val="10"/>'
        '<c:minorUnit val="2"/><c:title><c:layout/></c:title></c:valAx>'
        "</c:plotArea></c:chart></c:chartSpace>"
    )
    _axes(root)
    ns = {"c": C}
    assert not root.xpath(".//c:plotArea/c:layout", namespaces=ns)
    assert not root.xpath(".//c:valAx/c:majorUnit|.//c:valAx/c:minorUnit", namespaces=ns)
    assert not root.xpath(".//c:valAx/c:scaling/c:max", namespaces=ns)
    assert root.xpath(".//c:valAx/c:scaling/c:min/@val", namespaces=ns) == ["0"]
    assert not root.xpath(".//c:valAx/c:title/c:layout", namespaces=ns)


def test_axes_refuse_chart_without_plot_area() -> None:
    root = etree.fromstring(f'<c:chartSpace xmlns:c="{C}"/>')
    with pytest.raises(ValueError, match="no plot area"):
        _axes(root)
