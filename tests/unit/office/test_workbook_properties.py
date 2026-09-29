"""Every workbook writer publishes the firm identity and the neutral application name."""

import io
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree
from openpyxl import load_workbook
from tests.unit.energy_data.test_prelucrare_writer import _dataset
from tests.unit.reporting.test_report import _annex
from tests.unit.test_invoice_workbook_export import _invoice

from ema.core.config import Settings, load_settings
from ema.core.office.workbook import build_workbook
from ema.core.workspace import Workspace
from ema.energy_data.prelucrare_writer import write_prelucrare
from ema.invoices.export.exporter import OpenpyxlWorkbookExporter
from ema.reporting import generate, write_report


def _writers(tmp_path: Path) -> list[Path | io.BytesIO]:
    annex = tmp_path / "annex.xlsx"
    _annex(annex)
    report = write_report(generate([annex], (2025,)), tmp_path / "report.xlsx")
    prelucrare = tmp_path / "prelucrare.xlsx"
    write_prelucrare(_dataset(), (2024, 2025), prelucrare)
    invoice = OpenpyxlWorkbookExporter().export([_invoice()], tmp_path / "invoices.xlsx")
    root = etree.fromstring(
        b'<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">'
        b'<c:numRef><c:f>Values!$A$1</c:f><c:numCache><c:ptCount val="1"/>'
        b'<c:pt idx="0"><c:v>12.5</c:v></c:pt></c:numCache></c:numRef></c:chartSpace>'
    )
    return [report, prelucrare, invoice, io.BytesIO(build_workbook(root))]


@pytest.mark.parametrize("configured", [None, "FIRMĂ SINTETICĂ SRL"])
def test_all_four_writers_set_firm_properties_and_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: str | None
) -> None:
    monkeypatch.delenv("EMA_FIRM_NAME", raising=False)
    if configured:
        monkeypatch.setenv("EMA_FIRM_NAME", configured)
    expected = configured or "ENERGY MANAGEMENT & AUDIT SRL"
    assert Settings().firm_name == expected
    for target in _writers(tmp_path):
        book = load_workbook(target)
        assert book.properties.creator == expected
        assert book.properties.lastModifiedBy == expected
        with ZipFile(target) as archive:
            application = etree.fromstring(archive.read("docProps/app.xml"))
            assert (
                application.findtext(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Application"
                )
                == "Ema"
            )
        book.close()


def test_workspace_firm_name_and_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EMA_FIRM_NAME", raising=False)
    ws = Workspace(tmp_path / "ws")
    settings = load_settings(ws, workspace_values={"firm_name": "FIRMĂ DIN SETĂRI"})
    assert settings.firm_name == "FIRMĂ DIN SETĂRI"
    monkeypatch.setenv("EMA_FIRM_NAME", "FIRMĂ DIN MEDIU")
    assert (
        load_settings(ws, workspace_values={"firm_name": "FIRMĂ DIN SETĂRI"}).firm_name
        == "FIRMĂ DIN MEDIU"
    )
