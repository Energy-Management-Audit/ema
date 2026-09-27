"""Word COM calls against a fake object model."""

import json
from pathlib import Path

import pytest

from ema.windows.word_steps import perform


class Document:
    def __init__(self, events: list[tuple[str, object]], *, toc_count: int = 1) -> None:
        self.events = events
        self.TablesOfContents = Contents(events, toc_count)
        self.Tables = type("Tables", (), {"Count": 3})()

    def Save(self) -> None:  # noqa: N802 - COM method name
        self.events.append(("Save", None))

    def ExportAsFixedFormat(self, **kwargs: object) -> None:  # noqa: N802 - COM method name
        self.events.append(("ExportAsFixedFormat", kwargs))

    def SaveAs2(self, **kwargs: object) -> None:  # noqa: N802 - COM method name
        self.events.append(("SaveAs2", kwargs))

    def Close(self, **kwargs: object) -> None:  # noqa: N802 - COM method name
        self.events.append(("Close", kwargs))


class Contents:
    def __init__(self, events: list[tuple[str, object]], count: int) -> None:
        self.events = events
        self.Count = count

    def __call__(self, index: int) -> "Contents":
        assert index == 1
        return self

    def UpdatePageNumbers(self) -> None:  # noqa: N802 - COM method name
        self.events.append(("UpdatePageNumbers", None))


class Documents:
    def __init__(self, events: list[tuple[str, object]], toc_count: int) -> None:
        self.events = events
        self.toc_count = toc_count

    def Open(self, **kwargs: object) -> Document:  # noqa: N802 - COM method name
        self.events.append(("Open", kwargs))
        return Document(self.events, toc_count=self.toc_count)


class App:
    def __init__(self, toc_count: int = 1) -> None:
        self.events: list[tuple[str, object]] = []
        self.Documents = Documents(self.events, toc_count)
        self.Visible = True
        self.DisplayAlerts = 1
        self.AutomationSecurity = 0


@pytest.mark.parametrize("action", ["toc", "pdf", "docx", "text", "open"])
def test_steps_exact_calls(tmp_path: Path, action: str) -> None:
    input_name = "in.docx"
    output_name = {"pdf": "out.pdf", "docx": "out.docx", "text": "out.txt"}.get(action)
    (tmp_path / "request.json").write_text(
        json.dumps({"action": action, "input": input_name, "output": output_name})
    )
    app = App()
    result = perform(app, action, tmp_path)
    assert result == {"ok": True, "tables": 3 if action == "text" else None}
    assert (app.Visible, app.DisplayAlerts, app.AutomationSecurity) == (False, 0, 3)
    assert app.events[0] == (
        "Open",
        {
            "FileName": str(tmp_path / input_name),
            "ConfirmConversions": False,
            "ReadOnly": action != "toc",
            "AddToRecentFiles": False,
            "Visible": False,
            "OpenAndRepair": False,
            "NoEncodingDialog": True,
        },
    )
    assert app.events[-1] == ("Close", {"SaveChanges": 0})
    expected = {
        "toc": [("UpdatePageNumbers", None), ("Save", None)],
        "pdf": [
            (
                "ExportAsFixedFormat",
                {
                    "OutputFileName": str(tmp_path / "out.pdf"),
                    "ExportFormat": 17,
                    "OpenAfterExport": False,
                },
            )
        ],
        "docx": [("SaveAs2", {"FileName": str(tmp_path / "out.docx"), "FileFormat": 16})],
        "text": [("SaveAs2", {"FileName": str(tmp_path / "out.txt"), "FileFormat": 7})],
        "open": [],
    }
    assert app.events[1:-1] == expected[action]


def test_missing_toc_and_com_error_close(tmp_path: Path) -> None:
    (tmp_path / "request.json").write_text(
        json.dumps({"action": "toc", "input": "in.docx", "output": None})
    )
    app = App(toc_count=0)
    assert perform(app, "toc", tmp_path) == {
        "ok": False,
        "code": "word_automation",
        "detail": "no table of contents",
    }
    assert app.events[-1] == ("Close", {"SaveChanges": 0})

    def broken(**_kwargs: object) -> Document:
        raise RuntimeError("COM failed")

    app.Documents.Open = broken  # type: ignore[method-assign]
    assert perform(app, "toc", tmp_path) == {
        "ok": False,
        "code": "word_automation",
        "detail": "COM failed",
    }
