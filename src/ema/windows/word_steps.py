"""Word object-model operations, kept testable without Windows COM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def perform(app: Any, action: str, folder: Path) -> dict[str, object]:
    request: dict[str, object]
    request = json.loads((folder / "request.json").read_text(encoding="utf-8"))
    source = folder / str(request["input"])
    output = folder / str(request["output"]) if request["output"] is not None else None
    document: Any = None
    try:
        app.Visible = False
        app.DisplayAlerts = 0
        app.AutomationSecurity = 3
        document = app.Documents.Open(
            FileName=str(source),
            ConfirmConversions=False,
            ReadOnly=action != "toc",
            AddToRecentFiles=False,
            Visible=False,
            OpenAndRepair=False,
            NoEncodingDialog=True,
        )
        if action == "toc":
            if document.TablesOfContents.Count < 1:
                return {"ok": False, "code": "word_automation", "detail": "no table of contents"}
            document.TablesOfContents(1).UpdatePageNumbers()
            document.Save()
        elif action == "pdf" and output is not None:
            document.ExportAsFixedFormat(
                OutputFileName=str(output), ExportFormat=17, OpenAfterExport=False
            )
        elif action == "docx" and output is not None:
            document.SaveAs2(FileName=str(output), FileFormat=16)
        elif action == "text" and output is not None:
            tables = int(document.Tables.Count)
            document.SaveAs2(FileName=str(output), FileFormat=7)
            return {"ok": True, "tables": tables}
        elif action != "open":
            raise ValueError(f"Unknown Word action: {action}")
        return {"ok": True, "tables": None}
    except Exception as exc:
        return {"ok": False, "code": "word_automation", "detail": str(exc)}
    finally:
        if document is not None:
            document.Close(SaveChanges=0)
